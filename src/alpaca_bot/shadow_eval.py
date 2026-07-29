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

import numpy as np
import pandas as pd

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
def ic(df: pd.DataFrame, horizont: str = "fwd_5d") -> dict:
    """Information Coefficient: sortiert der Score die Kandidaten richtig?

    Querschnittlich JE TAG gerechnet, dann ueber die Tage gemittelt - genauso
    wie `research.py` es fuer die Historie tut. Ein globaler IC ueber alle
    Zeilen wuerde zu grossen Teilen messen, ob ein Monat besser war als ein
    anderer (also den Markt), nicht ob der Faktor an EINEM Tag trennt.
    """
    if df.empty or horizont not in df:
        return {"n_tage": 0, "ic": np.nan, "t": np.nan}

    tages_ic = []
    for tag, g in df.groupby("tag"):
        g = g.dropna(subset=["score", horizont])
        if len(g) < 5 or g["score"].nunique() < 2:
            continue
        tages_ic.append(g["score"].corr(g[horizont], method="spearman"))

    tages_ic = pd.Series([x for x in tages_ic if np.isfinite(x)])
    if len(tages_ic) < 2:
        return {"n_tage": len(tages_ic), "ic": np.nan, "t": np.nan}

    mittel = float(tages_ic.mean())
    t = mittel / (tages_ic.std(ddof=1) / math.sqrt(len(tages_ic)))
    return {"n_tage": int(len(tages_ic)), "ic": round(mittel, 5),
            "t": round(float(t), 2), "ic_std": round(float(tages_ic.std(ddof=1)), 4)}


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
                      *, buch: str = "spiegel", schreiben: bool = True,
                      sperrzone_oeffnen: bool = False) -> dict:
    """Bot A gegen Bot B - ueber die TAGESDIFFERENZ, nicht ueber Gesamtrenditen.

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
        else:
            L.append(f"     IC(5T) {k['ic']}  t={k['t']}  ueber {k['n_tage']} Tage")
        L.append(f"     Trefferquote {tq:.1%} gegen Basisrate {br:.1%}"
                 f"  ->  {tq - br:+.1%}")
        L.append(f"     UEBERSCHUSS {ue:+.3%}   <- gegen Universums-Median")

    L += ["", "-" * 78, f"  Zufallsschwelle bei {fleet.n_versuche(s)} Versuchen: "
          f"|t| > {fleet.schwelle_sigma(s)}"]
    if n_tage < MIN_TAGE:
        L += [f"  ACHTUNG: {n_tage} von {MIN_TAGE} noetigen Handelstagen.",
              "  Jeder Befund ist eine Momentaufnahme und rechtfertigt",
              "  KEINE Regelaenderung."]
    return "\n".join(L)
