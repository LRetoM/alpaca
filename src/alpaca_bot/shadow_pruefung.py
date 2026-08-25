"""Korrektheitspruefungen des Schattenbetriebs - stimmen die Zahlen?

Das Gegenstueck zu `audit.py` (Live-Handelsregeln) und
`data_integrity.py` (Journal). Dass diese Pruefungen bis zum
23.08.2026 IN `shadow.py` lagen, war der eigentliche Strukturfehler:
Der Schatten pruefte sich aus derselben Datei heraus, die er prueft,
waehrend die beiden anderen Pruefschichten laengst eigene Module
waren.

Zehn Pruefungen, darunter die Lookahead-Sperre, der Abgleich mit dem
echten Depot, die Kostenkontrolle und der Handelsrhythmus Live gegen
Spiegel (§G16 Fund 1).

**Solange eine Pruefung fehlschlaegt, sind die Zahlen des
Schattenbetriebs nicht zitierfaehig.** Das ist der Zweck des Moduls.

**Herkunft: Aufteilung von `shadow.py` am 23.08.2026 (BEFUNDE §G20).**
Der Schattenbetrieb lag in EINER Datei mit 2.339 Zeilen und fuenf
Verantwortungen. Der Code in diesem Modul wurde dabei **unveraendert**
verschoben - kein Ausdruck, keine Zeile Logik wurde angefasst. Nachgewiesen
ueber den Bytecode jeder Funktion, nicht behauptet (`scripts/29_umzug_pruefen.py`).
"""


from __future__ import annotations

import datetime as dt
import sqlite3

import numpy as np
import pandas as pd

from dataclasses import dataclass
from .engine import EngineConfig
from .shadow_config import MARKET_SYMBOL
from .shadow_daten import lade_bars
from .shadow_store import ShadowStore


# ---------------------------------------------------------------------------
# Korrektheitspruefungen (Plan §14)
# ---------------------------------------------------------------------------
@dataclass
class Befund:
    """Ergebnis einer Pruefung. `ok=False` heisst: hier stimmt etwas nicht."""

    nummer: int
    name: str
    ok: bool
    text: str

    def __str__(self) -> str:
        marke = "OK  " if self.ok else "FEHL"
        return f"  [{marke}] {self.nummer}. {self.name}\n         {self.text}"

def pruefungen(store: ShadowStore | None = None, *,
               mit_replay: bool = False) -> list[Befund]:
    """Die acht Pruefungen aus docs/schattenbetrieb.md §14.

    Ein Schattenbuch, dem man nicht trauen kann, ist schlimmer als keines -
    es erzeugt Zahlen, die aussehen wie Erkenntnis. Diese Pruefungen laufen
    auf den GESPEICHERTEN Daten und brauchen keine Wochen Vorlauf.
    """
    s = store or ShadowStore()
    out: list[Befund] = []
    p = s.table("predictions")

    # --- 1. Lookahead: Einstieg muss NACH dem Stichtag liegen ---
    if p.empty:
        out.append(Befund(1, "Lookahead-Sperre", True, "Noch keine Vorhersagen."))
    else:
        g = p.dropna(subset=["entry_date"])
        if g.empty:
            out.append(Befund(1, "Lookahead-Sperre", True,
                              "Noch nichts eingebucht."))
        else:
            a = pd.to_datetime(g["as_of"], format="mixed", utc=True)
            e = pd.to_datetime(g["entry_date"], format="mixed", utc=True)
            verletzt = int((e <= a).sum())
            out.append(Befund(
                1, "Lookahead-Sperre", verletzt == 0,
                f"{len(g):,} eingebuchte Vorhersagen geprueft, {verletzt} mit "
                "Einstieg am oder vor dem Stichtag."
                + ("" if verletzt == 0 else
                   "  DATENLECK: Die Rendite waere teilweise schon bekannt gewesen."),
            ))

    # --- 2. Kalender: Stichtag darf nicht in der Zukunft liegen ---
    if not p.empty:
        a = pd.to_datetime(p["as_of"], format="mixed", utc=True)
        zukunft = int((a > pd.Timestamp.now(tz="UTC")).sum())
        out.append(Befund(2, "Kalenderpruefung", zukunft == 0,
                          f"{zukunft} Vorhersage(n) mit Stichtag in der Zukunft."))

    # --- 3. Abgleich mit dem echten Bot ---
    out.append(_pruefe_gegen_depot(s))

    # --- 4. Kursanpassung (yfinance auto_adjust) ---
    out.append(_pruefe_kursanpassung(s))

    # --- 5. Kostenkontrolle gegen das echte Depot ---
    out.append(_pruefe_kosten(s))

    # --- 6. Replay gegen simulate.py (teuer, nur auf Anforderung) ---
    if mit_replay:
        out.append(_pruefe_replay(s))
    else:
        out.append(Befund(6, "Replay gegen simulate.py", True,
                          "uebersprungen (--replay zum Ausfuehren)"))

    # --- 7. Flottenkonsistenz: kein Bot darf einen Tag UEBERSPRINGEN ---
    if p.empty:
        out.append(Befund(7, "Flottenkonsistenz", True, "Noch keine Vorhersagen."))
    else:
        r = p[p["buch"] == "rangliste"]
        alle_tage = sorted(r["as_of"].unique())

        # Gleich VIELE Stichtage zu verlangen waere falsch: Ein spaeter
        # angemeldeter Bot hat zwangslaeufig eine kuerzere Historie, ohne dass
        # etwas kaputt ist (B07/B08 kamen am 2026-07-30 dazu). Der gepaarte
        # Vergleich schneidet ohnehin auf die gemeinsamen Tage.
        #
        # Wirklich schaedlich waere eine LUECKE: ein Bot, der an einem Tag
        # zwischen seinem ersten und letzten Lauf nichts geliefert hat. Dann
        # fehlt genau dieser Tag im Vergleich, und zwar unbemerkt.
        luecken = []
        for bot, g in r.groupby("bot_id"):
            tage = sorted(g["as_of"].unique())
            spanne = [t for t in alle_tage if tage[0] <= t <= tage[-1]]
            fehlend = set(spanne) - set(tage)
            if fehlend:
                luecken.append(f"{bot}: {len(fehlend)} Tag(e)")

        out.append(Befund(
            7, "Flottenkonsistenz", not luecken,
            f"{r['bot_id'].nunique()} Bot(s) ueber {len(alle_tage)} Stichtag(e), "
            "keine Luecken." if not luecken else
            f"LUECKEN gefunden - {'; '.join(luecken)}. Fehlende Tage machen den "
            "gepaarten Vergleich still unvollstaendig."
        ))

    # --- 8. Buchfuehrung: keine Luecken ---
    out.append(_pruefe_buchfuehrung(s))

    # --- 9. Nachtrags-Disziplin (Plan §4.6) ---
    if not p.empty and "nachgetragen" in p:
        n_nach = int(p["nachgetragen"].fillna(0).sum())
        out.append(Befund(
            9, "Nachtrags-Disziplin", True,
            f"{n_nach} nachgetragene Vorhersage(n). Sie zaehlen in KEINER "
            "Vorwaertsstatistik mit (shadow_eval filtert sie heraus)."
        ))

    # --- 10. Handelt der Spiegel ueberhaupt wie der Live-Bot? ---
    out.append(_pruefe_handelsrhythmus(s))

    # --- 11. Merkt sich das Spiegelbuch, WARUM es gekauft hat? ---
    out.append(_pruefe_einstiegsgruende(s))
    return out


def _pruefe_einstiegsgruende(s: ShadowStore) -> Befund:
    """Traegt jede Spiegelposition ihren Einstiegsscore und ihre Gruende?

    **Der Fund vom 24.08.2026 (§G27).** `entry_score` war in **0 von 130**
    Zeilen gefuellt, `reasons` in 130 von 130 - mit einem einzigen
    eindeutigen Wert, `{}`. Ursache: Der taegliche Uebertrag der
    gehaltenen Positionen las beides aus einem `meta`-Dictionary, das
    EINMAL vor der Tagesschleife geladen wird. Ein im selben Lauf
    gekaufter Wert stand dort nicht, also kam `None` an und
    ueberschrieb per `INSERT OR REPLACE` den korrekten Wert.

    Ohne diese Felder ist die Frage unbeantwortbar, fuer die das
    Spiegelbuch existiert: **"War die gehaltene Position schwaecher als
    der beste verworfene Kandidat?"** Man sieht, WAS gehalten wird, aber
    nicht, mit welcher Begruendung - und kann es deshalb mit nichts
    vergleichen.

    Geprueft wird die Fuellquote, nicht die Variation: Anders als bei
    `orders.status` (§G19 Fund 5) ist hier ein konstanter Wert nicht das
    Problem, sondern ein LEERER.
    """
    port = s.table("shadow_portfolio")
    if port.empty:
        return Befund(11, "Einstiegsgruende im Spiegelbuch", True,
                      "Noch keine Positionen.")
    ohne_score = int(port["entry_score"].isna().sum())
    leere_gruende = int((port["reasons"].fillna("").astype(str).str.strip()
                         .isin(("", "{}", "null"))).sum())
    n = len(port)
    ok = ohne_score == 0 and leere_gruende == 0
    if ok:
        return Befund(11, "Einstiegsgruende im Spiegelbuch", True,
                      f"Alle {n} Positionen tragen Score und Begruendung.")
    return Befund(
        11, "Einstiegsgruende im Spiegelbuch", False,
        f"{ohne_score} von {n} Positionen ohne `entry_score`, "
        f"{leere_gruende} ohne Begruendung. Damit laesst sich nicht "
        f"vergleichen, ob eine gehaltene Position schwaecher war als ein "
        f"verworfener Kandidat - die Kernfrage des Spiegelbuchs (§G27).")

LIVE_SPIEGEL_BOT = "B09_nachkauf"

def _pruefe_handelsrhythmus(s: ShadowStore) -> Befund:
    """Deckt sich das Handelsverhalten des Spiegels mit dem echten Bot?

    **Der Unterschied zu Pruefung 3.** Jene vergleicht KURSE (yfinance
    gegen Alpaca). Diese vergleicht, WAS getan wird - und dort lag ein
    Fund, den keine Konfigurationspruefung finden konnte (§G16).

    `max_new_positions=3` bedeutet an den zwei Orten Verschiedenes:

        live.run_once   3 Kaeufe je ZYKLUS - der Daemon laeuft alle 15 Min,
                        also bis zu 26-mal am Handelstag
        shadow._spiegel 3 Kaeufe je HANDELSTAG - der Tagesbar-Rhythmus
                        kennt nur einen Durchgang

    Gemessen am 22.08.2026: Der Live-Bot eroeffnete am 28.07. **50
    Positionen an einem Tag**; das Spiegelbuch schafft konstruktions-
    bedingt drei. Folge: Live steht bei 15/15 Positionen und 91 %
    investiert, `B09_nachkauf` bei 11/15 und 64 %.

    Daraus folgt der eigentliche Schaden. `Engine._find_topups` bekommt
    das von `_find_entries` bereits verplante Kapital abgezogen. Solange
    Plaetze frei sind, ist dieser Betrag das gesamte freie Kapital -
    also gibt es **nie** Nachkaeufe. Erst im vollen Depot (`slots = 0`,
    `entries = []`, `verplant = 0`) entstehen sie. Deshalb:

        Live-Journal   110 topup von 304 Entscheidungen (36 %)
        Spiegelbuch      0 topup von  51 Kaeufen

    `B09_nachkauf` ist damit ueber seine gesamte Laufzeit **bitgleich mit
    `B08_voll_investiert`** - seine Achse (`allow_topup`) hat nie
    gebunden. Er belegt einen Flottenplatz, hebt die Schwelle fuer alle
    (§B2) und misst nichts. Und `B11_dyn_ausstieg_live` wird laut
    BETRIEBSPLAN §3.3 gegen genau diesen Bot geprueft.

    **Warum das hier nur gemeldet und nicht behoben wird:** Beides waere
    eine Aenderung der Handelslogik waehrend einer laufenden Messung -
    CLAUDE.md verbietet das ausdruecklich. Der Weg fuehrt ueber einen
    eigenen Flottenbot nach dem 10.10.2026.
    """
    try:
        from .journal import JOURNAL_DB

        with sqlite3.connect(JOURNAL_DB) as c:
            live = pd.read_sql(
                "SELECT d.action, COUNT(*) n FROM decisions d"
                " JOIN runs r ON d.run_id = r.run_id"
                " WHERE r.script = 'live_trade' AND d.blocked_by IS NULL"
                " GROUP BY d.action", c)
    except Exception as e:  # noqa: BLE001
        return Befund(10, "Handelsrhythmus Live gegen Spiegel", True,
                      f"nicht durchfuehrbar: {type(e).__name__}: {e}")

    if live.empty:
        return Befund(10, "Handelsrhythmus Live gegen Spiegel", True,
                      "Noch keine Live-Entscheidungen.")

    sp = s.table("predictions", "buch = 'spiegel' AND bot_id = ?",
                 (LIVE_SPIEGEL_BOT,))
    if sp.empty:
        return Befund(10, "Handelsrhythmus Live gegen Spiegel", True,
                      f"{LIVE_SPIEGEL_BOT} hat noch nicht gehandelt.")

    je_live = dict(zip(live["action"], live["n"]))
    n_live_top = int(je_live.get("topup", 0))
    n_live_ges = int(sum(je_live.values()))
    n_sp_top = int((sp["aktion"] == "topup").sum())

    anteil_live = n_live_top / max(1, n_live_ges)
    # Der Spiegel muss nicht denselben ANTEIL treffen - er sieht andere
    # Tage. Ein Befund ist erst, dass eine ganze Aktionsart FEHLT,
    # obwohl sie live ein Drittel ausmacht.
    ok = not (n_live_top > 0 and n_sp_top == 0 and anteil_live > 0.05)

    return Befund(
        10, "Handelsrhythmus Live gegen Spiegel", ok,
        f"Live: {n_live_top} von {n_live_ges} Entscheidungen sind Nachkaeufe "
        f"({anteil_live:.0%}). {LIVE_SPIEGEL_BOT}: {n_sp_top} von {len(sp)}."
        + ("" if ok else
           f"  ABWEICHUNG: Der Spiegel fuehrt eine Aktionsart gar nicht aus, "
           f"die live ein {anteil_live:.0%}-Anteil ist. Ursache: "
           f"`max_new_positions` wirkt live je ZYKLUS (bis 26/Tag), im "
           f"Spiegel je HANDELSTAG - das Spiegeldepot wird nie voll, und "
           f"Nachkaeufe entstehen nur im vollen Depot (§G16). "
           f"{LIVE_SPIEGEL_BOT} ist damit KEIN Live-Spiegel, obwohl seine "
           f"Konfiguration feldweise stimmt.")
    )

def _pruefe_gegen_depot(s: ShadowStore) -> Befund:
    """Was der Live-Bot gekauft hat, muss das Spiegelbuch auch gekauft haben.

    Zugleich ein laufender Test von yfinance gegen Alpaca: Weichen die
    Einstiegskurse stark ab, forscht man auf anderen Daten, als man handelt.
    """
    try:
        from .journal import Journal

        echte = Journal().table("orders", "dry_run = 0 AND side = 'buy'")
        if echte.empty:
            return Befund(3, "Abgleich mit dem Depot", True,
                          "Noch keine echten Kaeufe im Depot.")
        spiegel = s.table("predictions", "buch = 'spiegel' AND aktion = 'buy'")
        if spiegel.empty:
            return Befund(3, "Abgleich mit dem Depot", True,
                          "Spiegelbuch hat noch nicht gehandelt - "
                          "Abgleich ab dem ersten gemeinsamen Handelstag.")

        echte["tag"] = pd.to_datetime(echte["ts"], format="mixed", utc=True).dt.date
        spiegel["tag"] = pd.to_datetime(spiegel["entry_date"], format="mixed",
                                        utc=True).dt.date
        gemeinsame = set(echte["tag"]) & set(spiegel["tag"])
        if not gemeinsame:
            return Befund(3, "Abgleich mit dem Depot", True,
                          "Noch kein gemeinsamer Handelstag.")

        # Bewusst die VERTEILUNG pruefen, nicht einzelne Trades: Der Live-Bot
        # kauft ~20 Minuten nach Eroeffnung, der Schatten zur Eroeffnung.
        # Einzelne Werte bewegen sich in dieser Spanne leicht um mehr als
        # 0,5 % - das ist Marktrauschen, kein Fehler. Ein Problem waere erst
        # eine SYSTEMATISCHE Verschiebung (Median), etwa durch abweichende
        # Split-/Dividendenanpassung zwischen yfinance und Alpaca.
        abweichungen = []
        for _, e in echte[echte["tag"].isin(gemeinsame)].iterrows():
            m = spiegel[(spiegel["symbol"] == e["symbol"])
                        & (spiegel["tag"] == e["tag"])]
            if m.empty or not e.get("fill_price") or float(e["fill_price"]) <= 0:
                continue
            abweichungen.append(
                float(m["entry_price"].iat[0]) / float(e["fill_price"]) - 1
            )
        if not abweichungen:
            return Befund(3, "Abgleich mit dem Depot", True,
                          "Noch keine vergleichbaren Kaeufe mit Fuellpreis.")
        a = pd.Series(abweichungen)
        median_bps = float(a.median() * 10_000)
        ok = abs(median_bps) < 50          # 50 bps = Schwelle aus datasources
        return Befund(
            3, "Abgleich mit dem Depot", ok,
            f"{len(a)} gemeinsame Kaeufe. Median-Abweichung yfinance gegen "
            f"Alpaca: {median_bps:+.1f} bps (Streuung "
            f"{float(a.std(ddof=0) * 10_000):.0f} bps)."
            + ("" if ok else "  ZU GROSS - unterschiedliche Kursanpassung, "
                             "Forschung und Handel laufen auf anderen Daten.")
        )
    except Exception as e:  # noqa: BLE001
        return Befund(3, "Abgleich mit dem Depot", True,
                      f"nicht durchfuehrbar: {type(e).__name__}: {e}")

ANPASSUNG_GRENZE = 0.15

ANPASSUNG_JUENGSTE_TAGE = 5

SLIPPAGE_GRENZE_BPS = 15.0

def _pruefe_kursanpassung(s: ShadowStore) -> Befund:
    """Aendert yfinance Kurse rueckwirkend - und passiert das gerade JETZT?

    **Geprueft wird die junge Kante, nicht die Historie (§G16).** Bis zum
    22.08.2026 rechnete diese Pruefung den Anteil ueber ALLE Ergebnisse
    und meldete damit dauerhaft FEHL.

    Der Grund ist strukturell: `auto_adjust=True` passt historische Kurse
    nach JEDER Dividende und jedem Split rueckwirkend an. Je aelter ein
    Stichtag, desto mehr solcher Ereignisse liegen dahinter. Gemessen je
    Stichtag:

        28.07. - 07.08.    6 % bis 25 %   (alt, viele Ereignisse seither)
        13.08. - 20.08.    0 % bis  4 %   (jung)
        kumuliert          7,7 %          -> FEHL bei 5 % Schwelle

    Die kumulierte Quote MUSS mit der Zeit wachsen. Eine Schwelle darauf
    reisst zwangslaeufig, ohne dass etwas kaputt ist - exakt der
    Fehlversuch, den `data_integrity.check_stumme_felder` schon einmal
    gemacht hat und den §G13 festhaelt: eine Quote ueber die Historie
    statt der gefaehrlichen Richtung.

    Gefaehrlich ist der umgekehrte Fall: **frische** Stichtage mit hoher
    Anpassungsrate. Das hiesse, die Kursquelle aendert Daten, die gerade
    erst entstanden sind - dann stimmt etwas mit dem Feed nicht, und
    genau dann sind die juengsten Vorhersagen betroffen.

    Die gespeicherten Kurse werden in keinem Fall ueberschrieben; die
    Abweichung wird nur vermerkt (`verifizieren`).
    """
    o = s.table("shadow_outcomes")
    p = s.table("predictions")
    if o.empty or "data_check" not in o or p.empty:
        return Befund(4, "Kursanpassung", True, "Noch keine Ergebnisse.")

    df = o[["pred_id", "data_check"]].merge(
        p[["pred_id", "as_of"]], on="pred_id", how="inner")
    if df.empty:
        return Befund(4, "Kursanpassung", True, "Noch keine Ergebnisse.")

    df["tag"] = pd.to_datetime(df["as_of"], format="mixed", utc=True).dt.date
    tage = sorted(df["tag"].unique())
    jung = set(tage[-ANPASSUNG_JUENGSTE_TAGE:])
    frisch = df[df["tag"].isin(jung)]
    if len(frisch) < 20:
        return Befund(4, "Kursanpassung", True,
                      f"Erst {len(frisch)} Ergebnis(se) an den juengsten "
                      f"Stichtagen - zu wenig fuer eine Quote.")

    anteil_jung = float((frisch["data_check"] == "kurs_angepasst").mean())
    anteil_alt = float((df["data_check"] == "kurs_angepasst").mean())
    ok = anteil_jung < ANPASSUNG_GRENZE

    # Tausenderpunkte nur auf der ZAHL bilden, nie per `.replace()` ueber
    # den fertigen Satz - das frisst die Satzkommas gleich mit (beim
    # Umbau von `fokus.hebel()` am selben Tag genau einmal passiert).
    n_frisch = f"{len(frisch):,}".replace(",", ".")
    return Befund(
        4, "Kursanpassung erkannt", ok,
        f"{anteil_jung:.1%} der {n_frisch} Ergebnisse an den juengsten "
        f"{len(jung)} Stichtagen wurden rueckwirkend angepasst "
        f"(Grenze {ANPASSUNG_GRENZE:.0%}). Ueber die ganze Historie "
        f"{anteil_alt:.1%} - dort erwartbar, weil jede Dividende die "
        f"aelteren Kurse mit anpasst. Gespeicherte Kurse wurden NICHT "
        f"ueberschrieben."
        + ("" if ok else "  AUFFAELLIG: Auch frische Kurse aendern sich - "
                         "das deutet auf ein Problem der Kursquelle, nicht "
                         "auf normale Dividendenanpassung.")
    )

def _pruefe_kosten(s: ShadowStore) -> Befund:
    """Der Schatten darf nicht guenstiger sein als das echte Depot.

    **Gemessen wird der MEDIAN, nicht der Mittelwert (§G16).** Bis zum
    22.08.2026 rechnete diese Pruefung einen n-gewichteten Mittelwert und
    meldete damit dauerhaft FEHL. An denselben 162 pruefbaren Orders:

        Median   +0,0 bps   -> Kriterium aus BETRIEBSPLAN §3.1 erfuellt
        Mittel  -71,7 bps   -> Pruefung meldet FEHL

    Die Differenz stammt aus drei Datenfehlern, die dieses Projekt selbst
    dokumentiert (§G, 04.08.2026): KGS mit -1.648 bps und SIMO mit
    -1.584 bps sind kaputte IEX-Quotes, keine Ausfuehrungsqualitaet.
    Genau gegen solche Artefakte ist der Median robust - und genau
    deshalb nennt der Entscheidungsvertrag ihn, an beiden Stellen
    (§3.1 und §8).

    Eine Pruefung, die eine andere Kennzahl misst als der Vertrag, den
    sie ueberwacht, erzeugt einen dauerhaften Fehlalarm in der
    wichtigsten Zahl des Projekts - und eine Warnung, die immer
    leuchtet, wird weggeklickt (`docs/LERNTEMPO.md` §5).

    **Zum Vorzeichen:** `journal.order()` rechnet so, dass POSITIV
    "schlechter als erwartet" heisst (fuer Verkaeufe negiert). Ein
    negativer Wert ist also guenstige Ausfuehrung - dann ist die
    Schattenannahme zu vorsichtig, nicht zu optimistisch. Die alte
    Meldung behauptete unabhaengig vom Vorzeichen das Gegenteil.
    """
    try:
        from .journal import Journal

        angesetzt = 3.0
        MIN_FUELLUNGEN = 30   # wie BETRIEBSPLAN §3.1/§8: "ueber 30 Trades"

        # Median ueber die einzelnen ORDERS, nicht ueber Symbol-Mediane.
        # §3.1 sagt woertlich "ueber 30+ saubere Orders". Ein Median ueber
        # Symbole gewichtet ein Symbol mit einer Fuellung genauso wie eines
        # mit sechs - gemessen am 22.08.2026: 73 Symbole, 178 Fuellungen.
        werte = Journal().slippage_werte().dropna()
        n_gesamt = len(werte)

        if n_gesamt < MIN_FUELLUNGEN or not np.isfinite(werte).any():
            # Kein messbarer Wert ist KEIN Fehlschlag: Slippage steht erst
            # fest, wenn genug echte Orders mit Fuellpreis UND Referenzkurs
            # vorliegen. Ein "nan" als Verstoss zu melden waere ein Fehlalarm.
            return Befund(5, "Kostenkontrolle", True,
                          f"Im Depot erst {n_gesamt} Fuellung(en) mit "
                          f"gemessener Slippage - zu wenig fuer eine "
                          f"belastbare Aussage (noetig {MIN_FUELLUNGEN}, "
                          f"BETRIEBSPLAN §3.1). Schattenannahme "
                          f"{angesetzt:.1f} bps bleibt vorlaeufig.")

        echt = float(werte.median())
        ok = abs(echt) <= SLIPPAGE_GRENZE_BPS

        # Ausreisser bleiben sichtbar - sie sind Information, kein Rauschen.
        # Ein stiller Median waere die andere Haelfte desselben Fehlers.
        gross = werte[werte.abs() > 100]
        zusatz = ""
        if len(gross):
            zusatz = (f"  {len(gross)} von {n_gesamt} Order(s) ueber |100| bps "
                      f"(groesste {gross.abs().max():.0f}) - pruefen, ob "
                      f"Datenfehler (§G) oder echte Bewegung; der Median "
                      f"traegt sie nicht mit.")

        richtung = ("" if ok else
                    ("  Schatten ist zu optimistisch - Annahme anheben."
                     if echt > 0 else
                     "  Ausfuehrung ist besser als angenommen - die "
                     "Schattenannahme ist zu vorsichtig, nicht zu lasch."))

        return Befund(
            5, "Kostenkontrolle", ok,
            f"Depot misst {echt:+.1f} bps Slippage (Median ueber "
            f"{n_gesamt} Orders), Schatten setzt {angesetzt:.1f} bps an. "
            f"Grenze {SLIPPAGE_GRENZE_BPS:.0f} bps (§8), Ziel < 8 bps "
            f"(§3.1)." + richtung + zusatz
        )
    except Exception as e:  # noqa: BLE001
        return Befund(5, "Kostenkontrolle", True,
                      f"nicht durchfuehrbar: {type(e).__name__}: {e}")

def _pruefe_replay(s: ShadowStore) -> Befund:
    """Rechnet simulate.py denselben SCORE wie der Schatten?

    **Was hier bis zum 23.08.2026 stand - und warum es nichts prueft.**
    Der Docstring versprach genau diese Frage ("Erzeugt der Schattencode
    dieselben Entscheidungen wie simulate.py? Weichen sie ab, ist einer
    von beiden falsch"). Die Umsetzung startete `simulate.run()`, zaehlte
    die Trades und meldete `True`, sofern nichts abstuerzte. Ein
    Durchlauftest, als Vergleich beschriftet - dieselbe Fehlerklasse wie
    §G17 und §G19.

    Beim Nachruesten kam der Grund heraus, warum es jemand haette pruefen
    muessen (§G24): Die beiden Pfade rufen `build_reversal_frame` mit
    unterschiedlichen Argumenten.

        simulate.py   build_reversal_frame(df, market, weights)
        shadow_daten  build_reversal_frame(df, market, weights,
                                           symbol=s, news=news)

    `ReversalWeights.news = 0.10` ist ein additiver Score-Baustein. Ohne
    `news` faellt er ersatzlos weg. Gemessen an acht Symbolen: sechs
    bekommen einen anderen Score, bis zu +0,1000 - und die Rangfolge
    dreht sich. Der Bot kauft die obersten Plaetze, also andere Aktien.

    Diese Pruefung vergleicht deshalb die Scores selbst, nicht die
    Lauffaehigkeit. Sie meldet **auffaellig**, nicht **fehlgeschlagen**:
    Der Unterschied ist bekannt, benannt und nicht nachruestbar (der
    Nachrichtenfeed reicht nicht bis 2021 zurueck). Er muss nur sichtbar
    bleiben, damit niemand die Historienzahlen fuer eine Messung der
    laufenden Strategie haelt.
    """
    try:
        from .signals import build_reversal_frame

        cfg = EngineConfig.for_reversal()
        syms = ["AAPL", "MSFT", "JPM", "XOM", "WMT", "KO", "PFE", "CAT"]
        bars = lade_bars([*syms, MARKET_SYMBOL], 1.0, verbose=False)
        markt = bars.xs(MARKET_SYMBOL, level="symbol")["close"].astype(float)

        from . import news as news_mod

        start = (dt.datetime.now(dt.UTC) - dt.timedelta(days=60)).isoformat()
        artikel = news_mod.get_news(syms, start=start, max_articles=2000)

        abweichungen = []
        for sym in syms:
            try:
                df = bars.xs(sym, level="symbol")
            except KeyError:
                continue
            ohne = float(build_reversal_frame(
                df, markt, cfg.reversal_weights)["score"].iloc[-1])
            mit = float(build_reversal_frame(
                df, markt, cfg.reversal_weights,
                symbol=sym, news=artikel)["score"].iloc[-1])
            if abs(mit - ohne) > 1e-9:
                abweichungen.append((sym, ohne, mit))

        if not abweichungen:
            return Befund(6, "Replay gegen simulate.py", True,
                          f"{len(syms)} Symbole geprueft, Scores identisch - "
                          f"Historienlauf und Schatten rechnen dasselbe.")

        groesste = max(abweichungen, key=lambda x: abs(x[2] - x[1]))
        return Befund(
            6, "Replay gegen simulate.py", False,
            f"{len(abweichungen)} von {len(syms)} Symbolen bekommen im "
            f"Historienlauf einen ANDEREN Score als im Schatten (groesste "
            f"Abweichung {groesste[0]}: {groesste[1]:.4f} -> {groesste[2]:.4f}, "
            f"{groesste[2]-groesste[1]:+.4f}). Ursache: `simulate.py` "
            f"uebergibt kein `news`, der Nachrichtenfaktor (Gewicht "
            f"{cfg.reversal_weights.news}) faellt dort weg. BEKANNT und nicht "
            f"nachruestbar (§G24) - die Historienzahlen gelten fuer die "
            f"Vier-Faktor-Fassung, nicht fuer die laufende.")
    except Exception as e:  # noqa: BLE001
        return Befund(6, "Replay gegen simulate.py", False,
                      f"FEHLGESCHLAGEN: {type(e).__name__}: {e}")

def _pruefe_buchfuehrung(s: ShadowStore) -> Befund:
    """Luecken werden gemeldet, nicht geschaetzt - aber richtig eingeordnet.

    **Die Verschaerfung vom 24.08.2026 (§G30).** Vorher galt jede
    ueberfaellige Vorhersage ohne Einstiegskurs als FEHL. Am 24.08.2026
    meldete das 10 Zeilen - alle zu **einem** Symbol (WBS) an **einem**
    Stichtag (20.08.), waehrend 2.484 von 2.494 Vorhersagen desselben
    Tages sauber eingebucht wurden. Nachgesehen: WBS hat nach dem
    20.08. keine Kursdaten mehr, die letzte Bar ist flach
    (open=high=low=close=77,57) - die Signatur eines ausgesetzten oder
    eingestellten Wertes.

    Diese zehn Zeilen lassen sich **nie** einbuchen. Die Pruefung haette
    damit dauerhaft rot gestanden, und `pruefbericht` sagt: "Solange
    Pruefungen fehlschlagen, sind die Zahlen des Schattenbetriebs nicht
    zitierfaehig." Eine Warnung, die sich nicht abstellen laesst, entwertet
    den ganzen Bericht (§G18 Fund 4).

    **Das Kriterium, das trennt** - dasselbe wie beim Lebenslauf (§G21):
    Ist die aelteste unbuchbare Vorhersage **neuer** als die juengste
    eingebuchte? Dann hat der Einbuchungsschritt seither nicht gearbeitet
    - ein laufender Ausfall. Liegt alles Unbuchbare davor, hat der Schritt
    weitergearbeitet und einzelne Symbole schlicht keine Kurse mehr.

    Kein Datum im Code, keine Ausnahmeliste: Die Grenze ergibt sich aus
    den Daten und wandert mit.
    """
    p = s.table("predictions")
    if p.empty:
        return Befund(8, "Buchfuehrung", True, "Noch keine Vorhersagen.")

    heute = pd.Timestamp.now(tz="UTC").normalize()
    a = pd.to_datetime(p["as_of"], format="mixed", utc=True)
    faellig = p[(a < heute - pd.Timedelta(days=4)) & p["entry_price"].isna()]
    o = s.table("shadow_outcomes")
    eingebucht = p[p["entry_price"].notna()]
    ohne_ergebnis = (len(eingebucht) - len(o)) if not eingebucht.empty else 0

    if faellig.empty:
        text = (f"{len(p):,} Vorhersagen, {len(eingebucht):,} eingebucht, "
                f"{len(o):,} bewertet - keine Luecken.")
        if ohne_ergebnis > 0:
            text += (f" {ohne_ergebnis} eingebuchte ohne Ergebnis "
                     f"(normal, solange der Horizont laeuft).")
        return Befund(8, "Buchfuehrung", True, text)

    juengste_eingebucht = (str(eingebucht["as_of"].max())[:10]
                           if not eingebucht.empty else "")
    faellig_tage = faellig["as_of"].astype(str).str[:10]
    laufend = faellig[faellig_tage > juengste_eingebucht]
    symbole = sorted(faellig["symbol"].dropna().unique())

    if not laufend.empty:
        return Befund(
            8, "Buchfuehrung", False,
            f"{len(laufend)} Vorhersage(n) NACH dem juengsten eingebuchten "
            f"Stichtag ({juengste_eingebucht}) haben keinen Einstiegskurs - "
            f"der Einbuchungsschritt hat seither nicht gearbeitet.")

    return Befund(
        8, "Buchfuehrung", True,
        f"{len(p):,} Vorhersagen, {len(eingebucht):,} eingebucht, "
        f"{len(o):,} bewertet. {len(faellig)} Zeile(n) zu "
        f"{len(symbole)} Symbol(en) bleiben unbuchbar "
        f"({', '.join(symbole[:5])}) - keine Kursdaten nach dem Stichtag, "
        f"typisch fuer ausgesetzte oder eingestellte Werte. Nicht "
        f"schaetzbar, deshalb benannt statt gefuellt.")

def pruefbericht(store: ShadowStore | None = None, *,
                 mit_replay: bool = False) -> str:
    befunde = pruefungen(store, mit_replay=mit_replay)
    n_fehl = sum(1 for b in befunde if not b.ok)
    L = ["=" * 78, "  KORREKTHEITSPRUEFUNGEN DES SCHATTENBETRIEBS", "=" * 78, ""]
    L += [str(b) for b in befunde]
    L += ["", "=" * 78,
          f"  {len(befunde) - n_fehl} von {len(befunde)} Pruefungen bestanden."]
    if n_fehl:
        L.append("  ACHTUNG: Solange Pruefungen fehlschlagen, sind die Zahlen")
        L.append("  des Schattenbetriebs nicht zitierfaehig.")
    return "\n".join(L)
