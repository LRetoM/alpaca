"""Auswertung des Schattenbetriebs - mit eingebauter Ehrlichkeit.

Dieses Modul beantwortet die Fragen, wegen derer der Schattenbetrieb
ueberhaupt existiert:

    Sortiert der Score?              -> ic(), kalibrierung()
    Wird es besser?                  -> kohorten()
    Welcher Bot fuehrt?              -> vergleich_gepaart()
    Woran lag es?                    -> attribution()
    Unterscheiden sich die Bots ueberhaupt?  -> divergenz()

**Drei Regeln sind technisch erzwungen, nicht nur empfohlen:**

1. **Referenz statt Rohwert.** Jede Renditekennzahl wird gegen den
   Universums-Median desselben Tages gerechnet. Ein Schattenbuch mit +3 %
   in einer Woche, in der das Universum +4 % machte, ist ein Verlust. Die
   Rohzahl steht daneben, aber `ueberschuss` ist die Zahl, die zaehlt.

2. **Tage statt Beobachtungen.** Alle Vorhersagen eines Tages sind vom
   selben Marktfaktor getrieben; 200 Kandidaten an einem Tag sind naeher an
   EINER Beobachtung als an 200. Gerechnet wird deshalb ueber die Zeitreihe
   der Tages-ICs, und jede Ausgabe nennt `n_tage` - die Zahl, die zaehlt.

3. **Sperrzone.** Die letzten 20 % der Zeitreihe werden standardmaessig
   abgeschnitten. Ihr Wert haengt vollstaendig daran, dass niemand vorher
   hineinschaut; `sperrzone_oeffnen=True` muss ausdruecklich gesetzt werden.
"""

from __future__ import annotations

import datetime as dt
import json
import math
import re

import numpy as np
import pandas as pd

from . import statistik
from .shadow import ShadowStore

SPERRZONE_ANTEIL = 0.20
MIN_TAGE = 60
"""Unter dieser Zahl unabhaengiger Handelstage gilt jeder Befund als
Momentaufnahme und rechtfertigt keine Regelaenderung."""


# ---------------------------------------------------------------------------
# Datenbeschaffung
# ---------------------------------------------------------------------------
def datensatz(store: ShadowStore | None = None, *, buch: str = "rangliste",
              bot_id: str | None = None, sperrzone_oeffnen: bool = False
              ) -> pd.DataFrame:
    """Vorhersagen mit Ergebnis, standardmaessig OHNE Sperrzone.

    Die Sperrzone (letzte 20 % der Handelstage) bleibt unberuehrt, bis eine
    Entscheidung gefallen ist. Wer sie beim Suchen mit anschaut, verliert
    genau die unabhaengige Pruefung, fuer die sie da ist.
    """
    s = store or ShadowStore()
    with s._conn() as c:
        df = pd.read_sql_query(
            "SELECT p.*, o.fwd_1d, o.fwd_3d, o.fwd_5d, o.fwd_10d, o.fwd_20d,"
            "       o.return_pct, o.mae_pct, o.mfe_pct, o.exit_reason,"
            "       o.bench_fwd_5d, o.universum_fwd_5d, o.ueberschuss_5d,"
            "       o.ziel_erreicht, o.stop_erreicht"
            " FROM predictions p"
            " JOIN shadow_outcomes o ON p.pred_id = o.pred_id"
            " WHERE p.buch = ?" + (" AND p.bot_id = ?" if bot_id else ""),
            c, params=(buch, bot_id) if bot_id else (buch,),
        )
    if df.empty:
        return df

    # Nachgetragene Laeufe mit abweichender Code-Version sind Backtest,
    # kein Vorwaertstest (Plan §4.6) - sie fliegen aus jeder Statistik.
    if "nachgetragen" in df.columns:
        df = df[df["nachgetragen"].fillna(0) == 0]

    df["tag"] = pd.to_datetime(df["as_of"], format="mixed", utc=True).dt.date
    if not sperrzone_oeffnen:
        tage = sorted(df["tag"].unique())
        if len(tage) >= 5:
            grenze = tage[int(len(tage) * (1 - SPERRZONE_ANTEIL))]
            df = df[df["tag"] < grenze]
    return df


# ---------------------------------------------------------------------------
# Signalguete
# ---------------------------------------------------------------------------
def _horizont_tage(spalte: str) -> int:
    """Liest die Fensterlaenge aus einem Spaltennamen wie 'fwd_5d'.

    Der Horizont steckt im Namen und nirgends sonst. Ihn zu raten waere
    gefaehrlich: zu klein gewaehlt bleibt die Ueberlappung teilweise
    stehen, zu gross wird der Test unnoetig streng. Ist nichts lesbar,
    wird 1 zurueckgegeben - also KEINE Korrektur, und das faellt in der
    Ausgabe als `aufblaehung 1.0` auf.
    """
    m = re.search(r"(\d+)", spalte or "")
    return int(m.group(1)) if m else 1


def ic(df: pd.DataFrame, horizont: str = "fwd_5d") -> dict:
    """Information Coefficient: sortiert der Score die Kandidaten richtig?

    Querschnittlich JE TAG gerechnet, dann ueber die Tage gemittelt - genauso
    wie `research.py` es fuer die Historie tut. Ein globaler IC ueber alle
    Zeilen wuerde zu grossen Teilen messen, ob ein Monat besser war als ein
    anderer (also den Markt), nicht ob der Faktor an EINEM Tag trennt.

    **Der zurueckgegebene `t` ist um die Ueberlappung korrigiert** (§G12).
    Bei `fwd_5d` teilen benachbarte Tage vier Fuenftel ihres
    Renditefensters; der unkorrigierte Wert faellt dadurch systematisch
    zu hoch aus (gemessen: Fehlalarmquote 39,5 % statt 5 %). Der rohe
    Wert steht als `t_roh` daneben - er ist zum Vergleich da, nicht zum
    Zitieren.

    Der korrigierte Wert liegt bewusst unter dem eingefuehrten Schluessel
    `t`: Jeder bestehende Verbraucher (Schattenbericht, Musterspeicher)
    bekommt damit automatisch den richtigen, ohne selbst daran zu denken.
    """
    if df.empty or horizont not in df:
        return {"n_tage": 0, "ic": np.nan, "t": np.nan}

    paare = []
    for tag, g in df.groupby("tag"):
        g = g.dropna(subset=["score", horizont])
        if len(g) < 5 or g["score"].nunique() < 2:
            continue
        paare.append((tag, g["score"].corr(g[horizont], method="spearman")))

    # Chronologisch: Newey-West liest die Autokorrelation aus der
    # Reihenfolge. `groupby` sortiert zwar, aber die Zusicherung gehoert
    # sichtbar hierher, nicht in eine Annahme ueber pandas.
    paare.sort(key=lambda x: x[0])
    tages_ic = pd.Series([x for _, x in paare if np.isfinite(x)])
    if len(tages_ic) < 2:
        return {"n_tage": len(tages_ic), "ic": np.nan, "t": np.nan}

    mittel = float(tages_ic.mean())
    t_roh = mittel / (tages_ic.std(ddof=1) / math.sqrt(len(tages_ic)))
    h = _horizont_tage(horizont)
    if h > 1:
        t_korr, aufbl = statistik.newey_west_t(tages_ic.to_numpy(), lag=h - 1)
    else:
        t_korr, aufbl = float(t_roh), 1.0
    # Nicht berechenbar heisst NICHT "dann eben der rohe Wert". Bei einem
    # 10-Tage-Fenster ueber 8 Handelstage gibt es keinen gueltigen t-Wert -
    # der rohe waere die optimistischste aller Antworten und saehe wie ein
    # Ergebnis aus. `nan` ist hier die einzige ehrliche Zahl.
    ergebnis = {"n_tage": int(len(tages_ic)), "ic": round(mittel, 5),
                "t_roh": round(float(t_roh), 2), "horizont": h}
    if np.isfinite(t_korr):
        ergebnis |= {"t": round(float(t_korr), 2),
                     "aufblaehung": round(float(aufbl), 2)}
    else:
        ergebnis |= {"t": np.nan, "aufblaehung": np.nan,
                     "hinweis": f"{len(tages_ic)} Tage sind fuer einen "
                                f"{h}-Tage-Horizont zu wenig - kein t-Wert"}
    ergebnis["ic_std"] = round(float(tages_ic.std(ddof=1)), 4)
    return ergebnis


def kalibrierung(df: pd.DataFrame, horizont: str = "fwd_5d",
                 n_baender: int = 5) -> pd.DataFrame:
    """Erreichen hohe Scores tatsaechlich mehr als niedrige?

    Eine Rangliste, die nicht monoton ist, sortiert nicht - dann ist der
    Score als Auswahlkriterium wertlos, egal wie gut der Mittelwert aussieht.
    """
    if df.empty or horizont not in df:
        return pd.DataFrame()
    d = df.dropna(subset=["score", horizont]).copy()
    if len(d) < n_baender * 5:
        return pd.DataFrame()
    try:
        d["band"] = pd.qcut(d["score"], n_baender, duplicates="drop")
    except ValueError:
        return pd.DataFrame()

    agg = d.groupby("band", observed=True).agg(
        n=("score", "size"),
        score_mittel=("score", "mean"),
        rendite=(horizont, "mean"),
        trefferquote=(horizont, lambda s: float((s > 0).mean())),
    )
    if "ueberschuss_5d" in d:
        agg["ueberschuss"] = d.groupby("band", observed=True)["ueberschuss_5d"].mean()
    return agg.round(5)


def basisrate(df: pd.DataFrame, horizont: str = "fwd_5d") -> float:
    """Anteil ALLER erfassten Werte, die gestiegen sind.

    Die einzig sinnvolle Referenz fuer eine Trefferquote. Gegen 50 % zu
    vergleichen ist falsch: In einem steigenden Markt liegt die Basisrate
    deutlich darueber, und eine Trefferquote von 55 % waere dann schlecht.
    """
    if df.empty or horizont not in df:
        return float("nan")
    s = df[horizont].dropna()
    return float((s > 0).mean()) if len(s) else float("nan")


# ---------------------------------------------------------------------------
# Kohorten - wird es besser?
# ---------------------------------------------------------------------------
def kohorten(store: ShadowStore | None = None, *, buch: str = "rangliste",
             schreiben: bool = True, sperrzone_oeffnen: bool = False
             ) -> pd.DataFrame:
    """Wochenweise Kennzahlen je Bot - die Lernkurve.

    Ohne Code-Version waere die Frage "ist es besser geworden?" nicht
    beantwortbar, weil sich Regimewechsel und Codeaenderungen vermischen.
    Deshalb ist sie Teil des Schluessels.
    """
    s = store or ShadowStore()
    df = datensatz(s, buch=buch, sperrzone_oeffnen=sperrzone_oeffnen)
    if df.empty:
        return pd.DataFrame()

    df["kohorte"] = pd.to_datetime(df["tag"]).dt.strftime("%G-W%V")
    zeilen = []
    for (kohorte, bot), g in df.groupby(["kohorte", "bot_id"]):
        kennz = ic(g)
        zeilen.append({
            "kohorte": kohorte, "bot_id": bot, "buch": buch, "regime": "alle",
            "code_version": g["code_version"].mode().iat[0] if len(g) else None,
            "n_vorhersagen": len(g), "n_tage": kennz["n_tage"],
            "ic_5d": kennz["ic"], "ic_t_stat": kennz["t"],
            "trefferquote": round(float((g["fwd_5d"] > 0).mean()), 4)
            if g["fwd_5d"].notna().any() else None,
            "basisrate": round(basisrate(g), 4),
            "ueberschuss": round(float(g["ueberschuss_5d"].mean()), 5)
            if g["ueberschuss_5d"].notna().any() else None,
            "rendite_netto": round(float(g["return_pct"].mean()), 5)
            if g["return_pct"].notna().any() else None,
            "umschlag": len(g),
            "kalibrierung": _monotonie(g),
            "erstellt_am": dt.datetime.now(dt.UTC).isoformat(),
        })

    out = pd.DataFrame(zeilen)
    if schreiben and not out.empty:
        with s._conn() as c:
            for _, r in out.iterrows():
                c.execute(
                    "INSERT OR REPLACE INTO scoreboard (kohorte, bot_id, buch,"
                    " regime, code_version, n_vorhersagen, n_tage, ic_5d,"
                    " ic_t_stat, trefferquote, basisrate, ueberschuss,"
                    " rendite_netto, umschlag, kalibrierung, erstellt_am)"
                    " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    tuple(r[k] for k in [
                        "kohorte", "bot_id", "buch", "regime", "code_version",
                        "n_vorhersagen", "n_tage", "ic_5d", "ic_t_stat",
                        "trefferquote", "basisrate", "ueberschuss",
                        "rendite_netto", "umschlag", "kalibrierung", "erstellt_am"]),
                )
    return out


def _monotonie(g: pd.DataFrame) -> float | None:
    """Rangkorrelation zwischen Score-Band und mittlerer Rendite.

    +1 = perfekt sortiert, 0 = keine Ordnung, -1 = genau verkehrt herum.
    """
    k = kalibrierung(g)
    if k.empty or len(k) < 3:
        return None
    r = pd.Series(range(len(k))).corr(k["rendite"].reset_index(drop=True),
                                     method="spearman")
    return round(float(r), 3) if np.isfinite(r) else None


# ---------------------------------------------------------------------------
# Flotte: gepaarter Vergleich
# ---------------------------------------------------------------------------
def vergleich_gepaart(bot_a: str, bot_b: str, store: ShadowStore | None = None,
                      *, schreiben: bool = True,
                      sperrzone_oeffnen: bool = False) -> dict:
    """Bot A gegen Bot B - ueber die TAGESDIFFERENZ, nicht ueber Gesamtrenditen.

    **Immer auf dem Spiegelbuch.** Bis zum 22.08.2026 nahm diese Funktion
    einen Parameter `buch="spiegel"` entgegen und benutzte ihn nirgends -
    gerechnet wurde stets auf `equity_kurve`. `scripts/21_fleet.py` bot
    ihn als `--buch {spiegel,rangliste}` an und reichte ihn durch: Wer
    `--buch rangliste` waehlte, bekam still das Spiegelbuch-Ergebnis
    (§G16).

    Der Parameter ist ersatzlos entfallen, weil er konzeptionell nicht
    erfuellbar ist: Verglichen werden Equity-Kurven, und ein Depot hat
    nur das Spiegelbuch. Das Ranglisten-Buch zeichnet Kandidaten ohne
    Kapitalgrenze auf - es gibt dort keine Kurve, die man vergleichen
    koennte. Ein Parameter, dessen zweiter Wert unmoeglich ist, gehoert
    nicht in die Signatur.

    Beide Bots sehen dieselben Tage, Symbole und Kurse. Verglichen wird
    deshalb d_t = rendite_A(t) - rendite_B(t); der Marktfaktor kuerzt sich
    heraus. Die Streuung von d ist typisch 3-5x kleiner als die der
    Einzelrenditen, und weil die noetige Tageszahl quadratisch davon
    abhaengt, sinkt sie um den Faktor 10-25.

    Praktische Folge: "A schlaegt B" ist nach 6-10 Wochen entscheidbar,
    nicht erst nach 9 Monaten. Das ist der Grund, warum die Flotte der
    schnellere Erkenntnisweg ist.
    """
    from . import fleet

    s = store or ShadowStore()
    eq = s.table("equity_kurve")
    if eq.empty:
        return {"n_tage": 0, "t_wert": np.nan, "hinweis": "keine Equity-Kurve"}

    piv = eq.pivot(index="tag", columns="bot_id", values="equity")
    if bot_a not in piv or bot_b not in piv:
        return {"n_tage": 0, "t_wert": np.nan,
                "hinweis": f"{bot_a} oder {bot_b} hat keine Kurve"}

    ra = piv[bot_a].astype(float).pct_change()
    rb = piv[bot_b].astype(float).pct_change()
    d = (ra - rb).dropna()

    if not sperrzone_oeffnen and len(d) >= 5:
        d = d.iloc[: int(len(d) * (1 - SPERRZONE_ANTEIL))]

    if len(d) < 3:
        return {"n_tage": len(d), "t_wert": np.nan, "hinweis": "zu wenig Tage"}

    mittel, std = float(d.mean()), float(d.std(ddof=1))
    t = mittel / (std / math.sqrt(len(d))) if std > 0 else np.nan
    schwelle = fleet.schwelle_sigma(s)
    belastbar = bool(np.isfinite(t) and abs(t) > schwelle and len(d) >= MIN_TAGE)

    erg = {
        "bot_a": bot_a, "bot_b": bot_b, "n_tage": int(len(d)),
        "diff_mittel": round(mittel, 6), "diff_std": round(std, 6),
        "t_wert": round(float(t), 2) if np.isfinite(t) else None,
        "schwelle": schwelle, "belastbar": belastbar,
    }
    if schreiben:
        kohorte = str(d.index.max())[:10]
        with s._conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO vergleiche (kohorte, bot_a, bot_b,"
                " n_tage, diff_mittel, diff_std, t_wert, schwelle, belastbar,"
                " attribution, erstellt_am) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (kohorte, bot_a, bot_b, erg["n_tage"], erg["diff_mittel"],
                 erg["diff_std"], erg["t_wert"], schwelle, int(belastbar),
                 json.dumps(attribution(bot_a, bot_b, s), ensure_ascii=False),
                 dt.datetime.now(dt.UTC).isoformat()),
            )
    return erg


# Bandbreite fuer die Verlaengerungsquote aus BETRIEBSPLAN §3.3 Kriterium 3.
VERLAENGERUNG_MIN = 0.10
VERLAENGERUNG_MAX = 0.60
KRITERIUM_MIN_TAGE = 20


def referenz_bot(bot_id: str, store: ShadowStore | None = None) -> str:
    """Die bei der ANMELDUNG hinterlegte Vergleichsbasis eines Bots.

    **Auslöser (23.08.2026, BEFUNDE §G19 Fund 1).** Diese Funktion gibt es,
    weil dieselbe Frage vier Antworten hatte:

        BETRIEBSPLAN §3.3 (Vertragstext)  ->  B00_basis
        Flottenregistrierung in der DB    ->  B09_nachkauf
        `21_fleet.py --basis` (Standard)  ->  B00_basis
        `fokus.offene_fragen`             ->  B09_nachkauf

    Gemessen an B11_dyn_ausstieg_live am 23.08.2026: t = 0,99 gegen B00,
    t = 1,24 gegen B09. Es ist also KEINE Formalie, welche Referenz das
    Abnahmekommando nimmt - beide Zahlen tragen denselben Namen und
    entscheiden ueber denselben Vertrag.

    **Warum die Registrierung gewinnt und nicht der Dokumenttext.**
    BEFUNDE §G6 hat `B00_basis` am 16.08.2026 als Live-Referenz
    widerlegt: Der Live-Bot laeuft seit dem 30.07.2026 mit
    `deploy_to_target=True` und `allow_topup=True`, `B00_basis` steht bei
    `False`/`False`. `B11_dyn_ausstieg_live` wurde daraufhin eigens gegen
    `B09_nachkauf` angemeldet - genau deshalb traegt er den Zusatz "gegen
    echte Live-Basis" im Namen. Eine Registrierung ist unveraenderlich;
    ein Dokumentsatz ist es nicht. Maszgeblich ist deshalb, was bei der
    Anmeldung festgelegt wurde, nie eine spaeter abgeschriebene Zahl -
    dasselbe Prinzip, das BETRIEBSPLAN §3.2 fuer `schwelle_sigma()`
    aufstellt.

    Faellt auf `B00_basis` zurueck, wenn ein Bot ohne `basis_bot`
    registriert ist (`B00_basis` selbst ist der einzige solche Fall).
    """
    from . import fleet

    b = fleet.bot(bot_id, store or ShadowStore())
    return (b.basis_bot if b and b.basis_bot else "B00_basis")


def kriterien_pruefen(bot_id: str, basis_bot: str | None = None,
                      store: ShadowStore | None = None) -> dict:
    """Prueft die vier vorab festgelegten Kriterien aus BETRIEBSPLAN §3.3.

    Diese vier Kriterien sind der ENTSCHEIDUNGSVERTRAG - so am 21.08.2026
    festgelegt (siehe BEFUNDE §G10). `MIN_TAGE` (60) ist eine davon
    getrennte, strengere Hausmarke von `vergleich_gepaart`; sie ist ein
    Hinweis, kein Veto. Ohne diese Trennung waere der Termin nicht
    einhaltbar: 60 nutzbare Tage erreicht ein am 18.08. gestarteter Bot
    erst Ende November.

    `basis_bot=None` (Standard) nimmt die bei der Anmeldung hinterlegte
    Referenz (`referenz_bot`). Bis zum 23.08.2026 stand hier fest
    `"B00_basis"` - eine hartkodierte Vorgabe, die der Registrierung von
    B11 widersprach und damit den Entscheidungsvertrag auf eine bereits
    widerlegte Referenz stellte (BEFUNDE §G19 Fund 1). Ein ausdruecklich
    uebergebener Wert gewinnt weiterhin, damit sich eine Gegenprobe
    ("was saehe man gegen B00?") von Hand rechnen laesst.

    Ein Kriterium hat drei moegliche Zustaende, nicht zwei:

        True   erfuellt
        False  durchgefallen -> laut §3.3 bleibt es beim Zeitausstieg
        None   noch nicht entscheidbar (zu wenig Daten)

    `None` darf NIE als Bestehen durchgehen. Genau diese Verwechslung
    macht aus einem unfertigen Versuch ein Ergebnis.

    Kriterium 3 und 4 fragen nach "verlaengerten" Positionen. Die Engine
    fuehrt `verlaengert` nur als lokale Variable; sie protokolliert das
    Merkmal zwar abgeleitet als `nach_verlaengerung` in den
    Entscheidungsgruenden (`engine.py:815`), aber `shadow_exits` hat gar
    keine Spalte fuer Gruende. Hier wird deshalb dieselbe Formel noch
    einmal gebildet - `bars_held > max_hold_days`, wortgleich zur Engine.
    Der Nenner ist bewusst NICHT die Zahl aller Ausstiege, sondern nur
    derer, die die Frist ueberhaupt erreicht haben: eine nach zwei Tagen
    ausgestoppte Position hatte nie die Gelegenheit, verlaengert zu
    werden, und wuerde die Quote sonst kuenstlich druecken.
    """
    from . import fleet

    s = store or ShadowStore()
    if basis_bot is None:
        basis_bot = referenz_bot(bot_id, s)
    erg: dict = {"bot": bot_id, "basis": basis_bot}

    v = vergleich_gepaart(bot_id, basis_bot, s, schreiben=False)
    t = v.get("t_wert")
    schwelle = fleet.schwelle_sigma(s)
    n_tage = int(v.get("n_tage", 0))

    erg["1_t_ueber_schwelle"] = {
        "wert": t, "soll": f"> {schwelle}",
        "erfuellt": None if t is None else bool(t > schwelle),
    }
    erg["2_genug_tage"] = {
        # Nicht schlicht "nach Sperrzone": `vergleich_gepaart` zieht die
        # Sperrzone erst ab 5 Tagen ab (sonst bliebe von einer
        # Dreitagesreihe nichts uebrig). Unter 5 Tagen ist `n_tage` also
        # roh - eine Beschriftung, die das verschweigt, behauptet eine
        # Bereinigung, die nicht stattgefunden hat.
        "wert": n_tage,
        "soll": f">= {KRITERIUM_MIN_TAGE} (Sperrzone ab 5 Tagen abgezogen)",
        "erfuellt": n_tage >= KRITERIUM_MIN_TAGE,
    }

    b = fleet.bot(bot_id, s)
    frist = b.config.max_hold_days if b else None
    # §3.3 nimmt den DYNAMISCHEN Ausstieg ab. Ein Bot mit
    # `zeitausstieg_dynamisch=False` verkauft exakt bei `max_hold_days` und
    # kann konstruktionsbedingt nie verlaengern - fuer ihn ist die Quote
    # nicht "0 % und damit durchgefallen", sondern gar keine Frage. Ohne
    # diese Trennung meldete die Pruefung am 21.08.2026 fuer
    # B04_halten_lang "DURCHGEFALLEN, ist: 0.0". Falsche Aussage, und die
    # gefaehrliche Richtung: sie sieht nach Messergebnis aus.
    dynamisch = bool(b.config.zeitausstieg_dynamisch) if b else False
    ex = s.table("shadow_exits")
    ex = ex[ex["bot_id"] == bot_id] if not ex.empty else ex

    if b is None or not dynamisch or ex.empty:
        erreicht = verlaengert = pd.DataFrame()
    else:
        erreicht = ex[ex["bars_held"] >= frist]
        verlaengert = ex[ex["bars_held"] > frist]

    nicht_anwendbar = "entfaellt: Bot hat keinen dynamischen Ausstieg"
    quote = len(verlaengert) / len(erreicht) if len(erreicht) else None
    erg["3_verlaengerungsquote"] = {
        "wert": round(quote, 3) if quote is not None else None,
        "soll": (f"{VERLAENGERUNG_MIN:.0%} - {VERLAENGERUNG_MAX:.0%}"
                 if dynamisch else nicht_anwendbar),
        "n_erreicht_frist": len(erreicht), "n_verlaengert": len(verlaengert),
        "erfuellt": None if quote is None
        else bool(VERLAENGERUNG_MIN <= quote <= VERLAENGERUNG_MAX),
    }

    # Kriterium 4 haengt an Kriterium 3: ohne verlaengerte Trades gibt es
    # keinen Median, und "kein Median" ist nicht dasselbe wie "negativ".
    median = (float(verlaengert["return_pct"].median())
              if len(verlaengert) else None)
    erg["4_median_positiv"] = {
        "wert": round(median, 5) if median is not None else None,
        "soll": "> 0" if dynamisch else nicht_anwendbar,
        "n": len(verlaengert),
        "erfuellt": None if median is None else bool(median > 0),
    }

    zustaende = [erg[k]["erfuellt"] for k in erg if k[0].isdigit()]
    erg["bestanden"] = all(z is True for z in zustaende)
    erg["entscheidbar"] = None not in zustaende
    erg["hinweis_min_tage"] = (
        f"{n_tage} von {MIN_TAGE} Tagen der strengeren Hausmarke "
        f"(`MIN_TAGE`) - laut §3.3 kein Veto."
        if n_tage < MIN_TAGE else ""
    )
    return erg


def kriterien_text(bot_id: str, basis_bot: str | None = None,
                   store: ShadowStore | None = None) -> str:
    """Die vier Kriterien als lesbare Abnahmeliste.

    `basis_bot=None` nimmt die registrierte Referenz - siehe
    `referenz_bot` fuer den Grund (BEFUNDE §G19 Fund 1).
    """
    k = kriterien_pruefen(bot_id, basis_bot, store)
    zeichen = {True: "ERFUELLT   ", False: "DURCHGEFALLEN", None: "offen      "}
    # Die Herkunft der Referenz steht im Kopf, nicht nur ihr Name. Vom
    # 16.08. bis 23.08.2026 nannten Vertragstext und Abnahmekommando
    # verschiedene Bots, ohne dass die Ausgabe das verraten haette
    # (BEFUNDE §G19 Fund 1). Wer die Zahl zitiert, sieht jetzt mit,
    # woher sie kommt.
    registriert = referenz_bot(k["bot"], store)
    herkunft = ("registrierte Basis dieses Bots"
                if k["basis"] == registriert
                else f"VON HAND GESETZT - registriert ist {registriert}")
    L = ["=" * 78,
         f"  KRITERIEN AUS BETRIEBSPLAN §3.3: {k['bot']} gegen {k['basis']}",
         f"  Referenz: {herkunft}",
         "=" * 78, ""]
    titel = {
        "1_t_ueber_schwelle": "1. t ueber Zufallsschwelle",
        "2_genug_tage": "2. genug Handelstage",
        "3_verlaengerungsquote": "3. Verlaengerungsquote in Bandbreite",
        "4_median_positiv": "4. Median der verlaengerten Trades positiv",
    }
    for schluessel, name in titel.items():
        f = k[schluessel]
        L.append(f"  [{zeichen[f['erfuellt']]}] {name}")
        L.append(f"        ist: {f['wert']}   soll: {f['soll']}")
    L.append("")
    if not k["entscheidbar"]:
        L.append("  NOCH NICHT ENTSCHEIDBAR - mindestens ein Kriterium hat")
        L.append("  keine Datengrundlage. 'offen' ist KEIN Bestehen.")
    elif k["bestanden"]:
        L.append("  ALLE VIER ERFUELLT - laut §3.3 bestanden.")
    else:
        L.append("  MINDESTENS EINES DURCHGEFALLEN - laut §3.3 bleibt es")
        L.append("  beim Zeitausstieg nach `max_hold_days`.")
    if k["hinweis_min_tage"]:
        L += ["", "  " + k["hinweis_min_tage"]]
    return "\n".join(L)


def divergenz(store: ShadowStore | None = None) -> pd.DataFrame:
    """Unterscheiden sich die Bots ueberhaupt? (Plan §12.2, vorwaerts)

    Zwei Bots, deren Buecher identisch sind, liefern keine Information -
    sie belegen nur einen Flottenplatz und heben die Zufallsschwelle fuer
    ALLE anderen (siehe fleet.schwelle_sigma). Diese Diagnose findet solche
    Doubletten, BEVOR Wochen an Rechenzeit hineinlaufen.

    Beispiel aus dem ersten Lauf: `B03_ziel_weit` (target_atr 3.0 statt 2.0)
    war ueber 39 Tage cent-genau identisch mit `B00_basis` - bei
    max_hold_days=5 ueberlebt kaum eine Position lange genug, um das
    weitere Ziel zu erreichen. Die Variante ist damit wirkungslos.
    """
    s = store or ShadowStore()
    eq = s.table("equity_kurve")
    if eq.empty:
        return pd.DataFrame()
    piv = eq.pivot(index="tag", columns="bot_id", values="equity").astype(float)
    bots = list(piv.columns)

    zeilen = []
    for i, a in enumerate(bots):
        for b in bots[i + 1:]:
            d = (piv[a].pct_change() - piv[b].pct_change()).dropna()
            zeilen.append({
                "bot_a": a, "bot_b": b, "n_tage": len(d),
                "max_abweichung_bps": round(float(d.abs().max() * 10_000), 2)
                if len(d) else 0.0,
                "tage_verschieden": int((d.abs() > 1e-9).sum()),
                "identisch": bool(len(d) and (d.abs() < 1e-9).all()),
            })
    out = pd.DataFrame(zeilen)
    return out.sort_values("max_abweichung_bps") if not out.empty else out


# ---------------------------------------------------------------------------
# Attribution - woran lag es?
# ---------------------------------------------------------------------------
def attribution(bot_a: str, bot_b: str, store: ShadowStore | None = None) -> dict:
    """Zerlegt die Differenz zwischen zwei Bots in ihre Quellen.

    "A ist besser" ist die unbrauchbarste aller Antworten. Weil jede
    Vorhersage ihre reinen Horizontrenditen mitfuehrt - unabhaengig von
    Stop und Ziel -, laesst sich mechanisch trennen:

        Auswahl    kauft A andere Symbole?
        Zeitpunkt  gleiches Symbol, anderer Tag?
        Ausstieg   gleiche Einstiege, andere Ausstiege?

    Ist `nur_A` deutlich besser als `nur_B`, kommt A's Vorsprung aus der
    Auswahl. Ist die Schnittmenge gleich gut und die Ergebnisse
    unterscheiden sich trotzdem, liegt es am Ausstieg.
    """
    s = store or ShadowStore()
    a = datensatz(s, buch="spiegel", bot_id=bot_a, sperrzone_oeffnen=True)
    b = datensatz(s, buch="spiegel", bot_id=bot_b, sperrzone_oeffnen=True)
    if a.empty or b.empty:
        return {"hinweis": "zu wenig Daten"}

    sa = set(zip(a["symbol"], a["tag"]))
    sb = set(zip(b["symbol"], b["tag"]))
    gemeinsam, nur_a, nur_b = sa & sb, sa - sb, sb - sa

    def _mittel(df, menge, spalte):
        if not menge:
            return None
        m = df[[(x, y) in menge for x, y in zip(df["symbol"], df["tag"])]]
        v = m[spalte].dropna()
        return round(float(v.mean()), 5) if len(v) else None

    return {
        "n_gemeinsam": len(gemeinsam), "n_nur_a": len(nur_a), "n_nur_b": len(nur_b),
        # Auswahl: wie gut waren die Titel, die NUR A bzw. NUR B hatte?
        "auswahl_nur_a_fwd5": _mittel(a, nur_a, "fwd_5d"),
        "auswahl_nur_b_fwd5": _mittel(b, nur_b, "fwd_5d"),
        # Ausstieg: gleiche Titel, aber unterschiedlich realisiert?
        "ausstieg_a_netto": _mittel(a, gemeinsam, "return_pct"),
        "ausstieg_b_netto": _mittel(b, gemeinsam, "return_pct"),
        # Zur Einordnung: auf der Schnittmenge ist die reine Kursbewegung
        # per Definition gleich - Unterschiede dort sind reiner Ausstieg.
        "referenz_gemeinsam_fwd5": _mittel(a, gemeinsam, "fwd_5d"),
    }


# ---------------------------------------------------------------------------
# Bericht
# ---------------------------------------------------------------------------
def bericht(store: ShadowStore | None = None, *, buch: str = "rangliste",
            sperrzone_oeffnen: bool = False) -> str:
    from . import fleet

    s = store or ShadowStore()
    df = datensatz(s, buch=buch, sperrzone_oeffnen=sperrzone_oeffnen)

    L = ["=" * 78, f"  SCHATTEN-AUSWERTUNG  (Buch: {buch})", "=" * 78]
    if df.empty:
        L += ["  Noch keine bewerteten Vorhersagen.", "",
              "  Der Schattenbetrieb braucht mindestens einen Handelstag",
              "  Vorlauf, bevor Ergebnisse entstehen koennen."]
        return "\n".join(L)

    n_tage = df["tag"].nunique()
    L += [f"  Vorhersagen mit Ergebnis : {len(df):,}",
          f"  Unabhaengige Handelstage : {n_tage}   <- die zaehlende Zahl",
          f"  Sperrzone                : "
          + ("GEOEFFNET (!)" if sperrzone_oeffnen else "geschlossen (letzte 20 %)"),
          ""]

    for bot, g in df.groupby("bot_id"):
        k = ic(g)
        tq = float((g["fwd_5d"] > 0).mean()) if g["fwd_5d"].notna().any() else np.nan
        br = basisrate(g)
        ue = float(g["ueberschuss_5d"].mean()) if g["ueberschuss_5d"].notna().any() else np.nan
        L.append(f"  {bot}")
        if k["n_tage"] == 0:
            # Ein Querschnitts-IC braucht mindestens 5 bewertete Kandidaten
            # am selben Tag. Das Spiegelbuch haelt nur ~3 Positionen - dort
            # ist der IC prinzipiell nicht messbar. Genau deshalb gibt es
            # das Ranglisten-Buch.
            L.append("     IC(5T) nicht messbar - zu wenige Kandidaten je Tag."
                     + ("  (im Spiegelbuch normal, dafuer gibt es 'rangliste')"
                        if buch == "spiegel" else ""))
        elif k.get("hinweis"):
            # Kein t-Wert ist eine Aussage, kein Formatierungsproblem: Bei
            # einem 5-Tage-Fenster ueber 13 Handelstage laesst sich die
            # Ueberlappung nicht schaetzen (§G12). Ein "nan" waere hier das
            # schlechteste Ergebnis - es sieht nach Panne aus und laedt
            # dazu ein, ersatzweise den rohen Wert zu zitieren.
            L.append(f"     IC(5T) {k['ic']}  ueber {k['n_tage']} Tage")
            L.append(f"     kein t-Wert: {k['hinweis']}")
            L.append(f"     (roh waere {k['t_roh']} - NICHT zitieren, "
                     f"er unterstellt Unabhaengigkeit, die es nicht gibt)")
        else:
            L.append(f"     IC(5T) {k['ic']}  t={k['t']}  ueber {k['n_tage']} Tage"
                     + (f"  (roh {k['t_roh']}, {k['aufblaehung']}x)"
                        if k.get("aufblaehung") and k["aufblaehung"] != 1.0 else ""))
        L.append(f"     Trefferquote {tq:.1%} gegen Basisrate {br:.1%}"
                 f"  ->  {tq - br:+.1%}")
        L.append(f"     UEBERSCHUSS {ue:+.3%}   <- gegen Universums-Median")

    L += ["", "-" * 78, f"  Zufallsschwelle bei {fleet.n_versuche(s)} Versuchen: "
          f"|t| > {fleet.schwelle_sigma(s)}"]
    if n_tage < MIN_TAGE:
        L += [f"  ACHTUNG: {n_tage} von {MIN_TAGE} Tagen der Hausmarke.",
              "  Ein hier auffallender Befund ist eine Momentaufnahme und",
              "  rechtfertigt KEINE Regelaenderung. Eine Regelaenderung wird",
              "  ausschliesslich ueber BETRIEBSPLAN §3.3 abgenommen",
              "  (`21_fleet.py --kriterien`), nie ueber diesen Bericht."]
    return "\n".join(L)
