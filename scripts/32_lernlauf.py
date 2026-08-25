#!/usr/bin/env python3
"""Lernlauf: alle Bots ueber die Historie, Jahresscheibe fuer Jahresscheibe.

**Wozu (24.08.2026).** Der Vorwaertsbetrieb liefert einen Handelstag pro
Tag. Bei 15 Jahren Historie liegen ~3.780 Handelstage bereit - dieselbe
Datenmenge, die der Schatten in 15 Jahren sammeln wuerde. Wer eine Idee
verwerfen will, muss darauf nicht warten.

**Aber nicht so, wie es naheliegt.** "Alle Bots ueber alles laufen lassen
und die besten behalten" ist die Maschine, die Scheingewinner herstellt.
`BEFUNDE` §B2: Bei N Auswertungen liegt das erwartete Maximum allein
durch Zufall bei `sqrt(2 ln N)`. Bei 15 Bots x 12 Jahresscheiben (15-
Jahre-Standard) sind das 180 Auswertungen und ein Zufallsmaximum von
t ~ 3,4 - bevor ein einziger echter Effekt im Spiel ist. §B4 zeigt
denselben Mechanismus an echten Daten: PEAD sah auf 60 Symbolen aus wie
der beste Faktor des Projekts (t = 6,7) und brach auf 800 vollstaendig
zusammen.

**Deshalb Walk-Forward.** Die Auswahl trifft immer nur, was VOR dem
Bewertungsfenster liegt (`alpaca_bot.lernlauf_eval.walk_forward_auswahl`):

    Auswahl auf Jahr 1..k-1   ->   Bewertung in Jahr k   (nie gesehen)
    Auswahl auf Jahr 1..k     ->   Bewertung in Jahr k+1
    ...

Damit misst dieser Lauf nicht "welcher Bot war rueckblickend am besten"
(das weiss man immer), sondern die Frage, auf die es ankommt:

    **Traegt eine aus der Historie getroffene Auswahl in das naechste,
    ungesehene Jahr?**

Faellt die Antwort negativ aus, ist das ein Befund ueber das VERFAHREN -
und wichtiger als jedes einzelne Botergebnis.

**Was dieser Lauf nicht darf.** Eine Live-Schaltung begruenden. Zwei
Gruende bleiben auch bei sauberem Walk-Forward bestehen:

  * **Survivorship.** Das Universum kennt nur heute gelistete Symbole;
    der Schein-Vorteil betraegt 2-4 Prozentpunkte pro Jahr (§G11). Bei
    einem GEPAARTEN Vergleich kuerzt er sich weitgehend heraus - fuer
    absolute Renditen gilt er voll.
  * **Der Nachrichtenfaktor fehlt** (§G24). `simulate.py` uebergibt kein
    `news`; der Historienlauf rechnet die Vier-Faktor-Fassung, live
    laeuft die Fuenf-Faktor-Fassung.

**Was seit dem Umbau (25.08.2026, `docs/UMBAUPLAN.md` Schritt 4) dazu
kam:**

  * Ergebnisse werden nach `lernlauf.sqlite` geschrieben (Laeufe,
    Jahresergebnisse je Bot, gepaarter Vergleich je Bot, Walk-Forward-
    Zeilen) statt nur in eine ueberschriebene CSV.
  * Jeder Bot bekommt einen gepaarten TAGES-Vergleich gegen die Basis
    (`lernlauf_eval.paarweiser_test`) UND eine Trennschaerfe-Angabe
    (`lernlauf_eval.trennschaerfe`) - ein "kein Unterschied" ohne
    Nachweisgrenze ist eine irrefuehrende Auswertung (§G22).
  * Mindestens ein Bot (`ohne_regime`) aendert die SIGNALGEWICHTE statt
    nur Stop/Ziel/Frist - damit die Gruppierung nach Signalgruppe
    (`signal_schluessel`) mit mehr als einer Gruppe getestet ist, nicht
    nur mit vierzehn Bots in derselben.
  * **Zeitraum-Entscheidung (Schritt 3, Punkt 3):** 15 Jahre sind der
    Standard, nicht 25. Gemessen 24.08.2026: 25 Jahre erreichen nur 63 %
    der Universumssymbole, 15 Jahre 78 %. Der Ausschlag gaben die
    juengeren, naeher an der heutigen Marktstruktur liegenden Regime -
    das Argument fuer 25 Jahre (mehr Bewertungsfenster fuer den Walk-
    Forward-Test) ist real, aber 12 statt 22 Jahresscheiben liefern
    immer noch genug fuer einen t-Wert (>= 3 Uebergaenge noetig, >= ~8
    fuer eine belastbare Streuungsschaetzung).

    python scripts/32_lernlauf.py                      # 15 Jahre, Standard
    python scripts/32_lernlauf.py --jahre 25 --symbole 600
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from alpaca_bot import lernlauf_eval, simulate, universe  # noqa: E402
from alpaca_bot.config import DATA_DIR, code_version  # noqa: E402
from alpaca_bot.engine import EngineConfig  # noqa: E402
from alpaca_bot.lernlauf_store import LernlaufStore  # noqa: E402

ERGEBNIS_DB = DATA_DIR / "lernlauf.sqlite"

# Die Achsen, die geprueft werden. Jede unterscheidet sich in GENAU EINEM
# Feld von der Basis - dieselbe Disziplin wie in der Flotte (§J Regel 5),
# denn sonst ist ein Unterschied keinem Parameter zuzuordnen. Ein Eintrag
# darf ENTWEDER gewoehnliche `EngineConfig`-Felder setzen ODER (exklusiv,
# ueber den Sonderschluessel "_weights") genau ein Feld der Signalgewichte
# `ReversalWeights` - nie beides, aus demselben Grund wie oben.
BOTS: dict[str, dict] = {
    "basis":            {},
    "stop_eng":         {"stop_atr": 1.5},
    "stop_weit":        {"stop_atr": 3.0},
    "ziel_weit":        {"target_atr": 3.0},
    "halten_lang":      {"max_hold_days": 10},
    "halten_kurz":      {"max_hold_days": 3},
    "mehr_positionen":  {"max_positions": 25},
    "weniger_positionen": {"max_positions": 8},
    "schwelle_hoch":    {"min_score": 0.80},
    "dyn_ausstieg":     {"zeitausstieg_dynamisch": True},
    "exit_score_hoch":  {"exit_score": 0.30},
    "exit_score_null":  {"exit_score": 0.0},
    "kein_cooldown":    {"reenter_cooldown_days": 0},
    "trailing":         {"trail_after_atr": 1.5},
    # Signalgewicht statt EngineConfig-Feld - spiegelt den laufenden
    # Flottenbot B06_ohne_regime (siehe BEFUNDE §E) und ist zugleich die
    # einzige Achse, die die Signalgruppierung mit einer ZWEITEN Gruppe
    # testet (Umbauplan Schritt 4, Punkt 4). Ueber 15 Jahre kommen sowohl
    # Bullen- als auch Baermaerkte vor - die Frage "traegt der Filter"
    # ist damit hier in Minuten beantwortbar, waehrend der Live-Bot laut
    # BEFUNDE §G8 auf den naechsten Regimewechsel warten muss.
    "ohne_regime":      {"_weights": {"market_regime_filter": False}},
}
"""`exit_score` und `trail_after_atr` sind bewusst dabei: §G19 haelt fest,
dass beide nie gegengeprueft wurden, obwohl §E den `exit_score` als den
Wert ausweist, der `target_atr` wirkungslos macht."""

# Die LIVE-Konfiguration, gegen die verglichen wird. Nicht `for_reversal()`
# pur: Der Live-Bot laeuft seit dem 30.07.2026 mit deploy_to_target und
# allow_topup (§G6). Ein Vergleich gegen die Vorgaben waere ein Vergleich
# gegen etwas, das nirgends laeuft.
LIVE_BASIS = {"deploy_to_target": True, "allow_topup": True}


def konfiguration(over: dict) -> EngineConfig:
    """Baut die EngineConfig eines Bots - inklusive optionaler Gewichtsachse.

    `over["_weights"]`, falls vorhanden, wird NICHT an `EngineConfig`
    durchgereicht (die kennt das Feld nicht), sondern nach dem Bau per
    `copy.replace` auf `reversal_weights` angewandt - dasselbe Muster wie
    `fleet._bot_aus_zeile` fuer `B06_ohne_regime`.
    """
    rest = {k: v for k, v in over.items() if k != "_weights"}
    cfg = EngineConfig.for_reversal(**{**LIVE_BASIS, **rest})
    if "_weights" in over:
        cfg.reversal_weights = copy.replace(cfg.reversal_weights, **over["_weights"])
    return cfg


def achse_und_wert(over: dict) -> tuple[str | None, str | None]:
    """Name und Wert der EINEN geaenderten Achse - fuers Protokoll."""
    if not over:
        return None, None
    if "_weights" in over:
        (k, v), = over["_weights"].items()
        return k, str(v)
    (k, v), = over.items()
    return k, str(v)


def signal_schluessel(over: dict) -> str:
    """Bots mit gleichem Schluessel teilen sich die Signalberechnung.

    Nur `reversal_weights` und `strategy` gehen in die Signale ein - Stop,
    Ziel, Frist und Schwellen wirken erst danach. Ohne diese Gruppierung
    rechnet der Lauf die teuerste Stufe fuer jeden Bot neu (dieselbe
    Ersparnis wie `fleet.signal_schluessel`).
    """
    w = konfiguration(over).reversal_weights
    return json.dumps({"rueckgang": w.rueckgang, "rsi2": w.rsi2,
                       "ausverkauf": w.ausverkauf, "band_unten": w.band_unten,
                       "news": w.news, "regime": w.market_regime_filter},
                      sort_keys=True)


def jahresscheiben(kalender: pd.DatetimeIndex) -> list[tuple[int, pd.Timestamp, pd.Timestamp]]:
    jahre = sorted({d.year for d in kalender})
    out = []
    for j in jahre:
        tage = kalender[kalender.year == j]
        if len(tage) >= 100:          # angebrochene Jahre nicht als Scheibe zaehlen
            out.append((j, tage[0], tage[-1]))
    return out


def trades_je_jahr(trades: pd.DataFrame) -> dict[int, int]:
    """Wie viele Trades endeten in welchem Jahr? Offene Positionen zaehlen
    ueber ihr Einstiegsjahr, sonst wuerden sie in keinem Jahr auftauchen."""
    if trades.empty:
        return {}
    dat = pd.to_datetime(trades["exit_date"].fillna(trades["entry_date"]))
    return dat.dt.year.value_counts().to_dict()


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--jahre", type=float, default=15.0)
    ap.add_argument("--symbole", type=int, default=800)
    ap.add_argument("--kapital", type=float, default=30_000.0)
    ap.add_argument("--min-auswahl-jahre", type=int, default=3,
                    help="So viele Jahre muessen vor der ersten Auswahl liegen")
    ap.add_argument("--keine-persistenz", action="store_true",
                    help="Nicht nach lernlauf.sqlite schreiben (fuer Testlaeufe)")
    args = ap.parse_args()

    from alpaca_bot.shadow_daten import MARKET_SYMBOL, lade_bars

    version = code_version()
    print(f"  Code-Version: {version}")
    syms = universe.load_universe(max_symbols=args.symbole)
    print(f"  Universum : {len(syms)} Symbole")
    print(f"  Historie  : {args.jahre} Jahre")
    bars = lade_bars([*syms, MARKET_SYMBOL], args.jahre, verbose=True)
    markt = bars.xs(MARKET_SYMBOL, level="symbol")["close"].astype(float)
    scfg = simulate.SimConfig(initial_cash=args.kapital, log_to_journal=False)

    # --- Signale einmal je Signalgruppe ------------------------------------
    gruppen: dict[str, list[str]] = {}
    for name, over in BOTS.items():
        gruppen.setdefault(signal_schluessel(over), []).append(name)
    print(f"\n  {len(BOTS)} Bots in {len(gruppen)} Signalgruppe(n) - "
          f"die teure Stufe laeuft {len(gruppen)}x statt {len(BOTS)}x")

    from alpaca_bot.signals import build_reversal_frame

    per_symbol = {}
    for sym in bars.index.get_level_values("symbol").unique():
        df = bars.xs(sym, level="symbol").sort_index()
        if len(df) > scfg.warmup_bars:
            per_symbol[sym] = df
    print(f"  {len(per_symbol)} Symbole mit ausreichender Historie")

    rahmen_je_gruppe = {}
    for schluessel in gruppen:
        w = konfiguration(BOTS[gruppen[schluessel][0]]).reversal_weights
        print(f"  Berechne Signale fuer Gruppe {len(rahmen_je_gruppe)+1}"
              f"/{len(gruppen)} ...", flush=True)
        rahmen_je_gruppe[schluessel] = {
            s: build_reversal_frame(df, markt, w) for s, df in per_symbol.items()}

    # --- Jeder Bot ueber die ganze Historie, Equity je Tag -----------------
    kurven: dict[str, pd.Series] = {}
    trades_je_bot: dict[str, pd.DataFrame] = {}
    for i, (name, over) in enumerate(BOTS.items(), 1):
        cfg = konfiguration(over)
        res = simulate.run(bars, engine_config=cfg, sim_config=scfg,
                           market=markt, verbose=False,
                           signal_frames=rahmen_je_gruppe[signal_schluessel(over)])
        eq = pd.Series(dict(res.equity_curve)) if isinstance(res.equity_curve, list) \
            else pd.Series(res.equity_curve)
        eq.index = pd.to_datetime(eq.index)
        kurven[name] = eq
        trades_je_bot[name] = res.trades
        print(f"  [{i:2d}/{len(BOTS)}] {name:<20} "
              f"{eq.iloc[-1]/eq.iloc[0]-1:>+8.1%}  {len(res.trades):>5} Trades",
              flush=True)

    kalender = kurven["basis"].index
    scheiben = jahresscheiben(kalender)
    print(f"\n  {len(scheiben)} vollstaendige Jahresscheiben: "
          f"{scheiben[0][0]}-{scheiben[-1][0]}")

    # --- Persistenz: Lauf anlegen -------------------------------------------
    store = None if args.keine_persistenz else LernlaufStore(ERGEBNIS_DB)
    lauf_id = None
    if store is not None:
        lauf_id = store.lauf_anlegen(
            code_version=version, jahre=args.jahre, symbole=len(per_symbol),
            kapital=args.kapital, min_auswahl_jahre=args.min_auswahl_jahre,
            n_jahresscheiben=len(scheiben), n_signalgruppen=len(gruppen))
        print(f"  Lauf-ID   : {lauf_id}  (lernlauf.sqlite: {ERGEBNIS_DB})")

    # --- Ergebnis je Bot und Jahr, plus Persistenz --------------------------
    tab = {}
    for name, eq in kurven.items():
        r = eq.pct_change()
        jahre_trades = trades_je_jahr(trades_je_bot[name])
        achse, wert = achse_und_wert(BOTS[name])
        zeile = {}
        for j, a, b in scheiben:
            rendite = float((1 + r[(r.index >= a) & (r.index <= b)]).prod() - 1)
            zeile[j] = rendite
            if store is not None:
                store.jahresergebnis_schreiben(
                    lauf_id, name, j, rendite, int(jahre_trades.get(j, 0)),
                    achse, wert)
        tab[name] = zeile
    jahres = pd.DataFrame(tab).T
    print("\n" + "=" * 78)
    print("  ERGEBNIS JE BOT UND JAHR (in %)")
    print("=" * 78)
    print((jahres * 100).round(1).to_string())

    # --- Gepaarter Tages-Vergleich + Trennschaerfe je Bot gegen Basis ------
    n_versuche_raster = len(BOTS) * max(len(scheiben), 1)
    schwelle = lernlauf_eval.schwelle_sigma(n_versuche_raster)
    print("\n" + "=" * 78)
    print(f"  GEPAARTER VERGLEICH GEGEN 'basis'   (Zufallsschwelle bei "
          f"{n_versuche_raster} Zellen: |t| > {schwelle})")
    print("=" * 78)
    print(f"  {'Bot':<20} {'t':>8} {'n_Tage':>7}  {'nachweisbar ab (80%)':>22}  Bemerkung")
    for name, eq in kurven.items():
        if name == "basis":
            continue
        paar = lernlauf_eval.paarweiser_test(eq, kurven["basis"], schwelle)
        streuung = lernlauf_eval.trennschaerfe(eq, kurven["basis"], schwelle)
        if store is not None:
            store.bot_vergleich_schreiben(lauf_id, name, "basis", paar, streuung)
        if paar.t_wert is None:
            print(f"  {name:<20} {'--':>8} {paar.n_tage:>7}  {'--':>22}  {paar.hinweis}")
        else:
            bemerkung = "BELASTBAR" if paar.belastbar else ""
            nachweisbar = (f"{streuung.mit_80_prozent*100:.3f} %/Tag"
                           if streuung.mit_80_prozent else "--")
            print(f"  {name:<20} {paar.t_wert:>8.2f} {paar.n_tage:>7}  "
                 f"{nachweisbar:>22}  {bemerkung}")

    # --- Walk-Forward: traegt die Auswahl ins naechste Jahr? ---------------
    print("\n" + "=" * 78)
    print("  WALK-FORWARD - Auswahl nur aus der Vergangenheit")
    print("=" * 78)
    print(f"  {'Jahr':<6} {'gewaehlt (aus Vorjahren)':<24} {'sein Jahr':>10} "
          f"{'Basis':>9} {'Differenz':>10}")
    zeilen = lernlauf_eval.walk_forward_auswahl(
        jahres, scheiben, args.min_auswahl_jahre, basis="basis")
    for z in zeilen:
        if store is not None:
            store.walkforward_zeile_schreiben(lauf_id, z)
        print(f"  {z.jahr:<6} {z.gewaehlt:<24} {z.rendite_gewaehlt*100:>+9.1f}% "
              f"{z.rendite_basis*100:>+8.1f}% {z.diff*100:>+9.1f}pp")

    test = lernlauf_eval.walk_forward_test(zeilen)
    if store is not None:
        store.walkforward_test_schreiben(lauf_id, test, schwelle)
    if test.t_wert is None:
        print(f"\n  {test.hinweis}")
    else:
        print(f"\n  Ueber {test.n_jahre} ungesehene Jahre:")
        print(f"    mittlere Differenz : {test.mittel_diff*100:+.2f} Prozentpunkte/Jahr")
        print(f"    Jahre mit Vorsprung: {test.jahre_mit_vorsprung} von {test.n_jahre}")
        print(f"    t = {test.t_wert:+.2f}   (Schwelle {schwelle} nach sqrt(2 ln N), "
              f"N = Bots x Jahresscheiben)")
        print()
        if abs(test.t_wert) < schwelle:
            print("  KEIN BEFUND. Die aus der Historie getroffene Auswahl traegt")
            print("  nicht nachweisbar ins naechste Jahr. Das ist eine Aussage")
            print("  ueber das VERFAHREN, nicht ueber die einzelnen Bots - und")
            print("  sie gilt fuer jede kuenftige Auswahl nach demselben Muster.")
        elif test.t_wert > 0:
            print("  Die Auswahl traegt. ACHTUNG: Survivorship (2-4 pp/Jahr,")
            print("  §G11) ist hier NICHT abgezogen - bei absoluten Renditen")
            print("  voll wirksam, bei der Differenz weitgehend gekuerzt.")
        else:
            print("  Die Auswahl schadet - sie waehlt systematisch schlechter")
            print("  als der unveraenderte Basis-Bot.")

    if test.wechsel and len(zeilen) >= 2:
        print(f"\n  Die Auswahl wechselte in {test.wechsel} von {len(zeilen)-1} "
              f"Uebergaengen den Bot.")
        print("  Ein haeufiger Wechsel heisst: Die Rangfolge ist nicht stabil,")
        print("  also war der jeweilige Sieger ueberwiegend Zufall (§B2).")

    jahres.to_csv(DATA_DIR / "lernlauf_jahre.csv")
    print(f"\n  Jahrestabelle (CSV): {DATA_DIR / 'lernlauf_jahre.csv'}")
    if store is not None:
        print(f"  Vollstaendiges Ergebnis: {ERGEBNIS_DB}  (Lauf {lauf_id})")
    print("\n  Dieser Lauf darf eine Idee VERWERFEN, nicht abnehmen")
    print("  (Survivorship, fehlender Nachrichtenfaktor - siehe Modulkopf).")
    print("  Was ihn ueberlebt, geht ins Kandidatenregister"
          " (alpaca_bot.kandidatenregister), NICHT direkt in die Flotte.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
