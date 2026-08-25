#!/usr/bin/env python3
"""Lernlauf: alle Bots ueber die Historie, Jahresscheibe fuer Jahresscheibe.

**Wozu (24.08.2026).** Der Vorwaertsbetrieb liefert einen Handelstag pro
Tag. Bei 25 Jahren Historie liegen ~6.300 Handelstage bereit - dieselbe
Datenmenge, die der Schatten in 25 Jahren sammeln wuerde. Wer eine Idee
verwerfen will, muss darauf nicht warten.

**Aber nicht so, wie es naheliegt.** "Alle Bots ueber alles laufen lassen
und die besten behalten" ist die Maschine, die Scheingewinner herstellt.
`BEFUNDE` §B2: Bei N Auswertungen liegt das erwartete Maximum allein
durch Zufall bei `sqrt(2 ln N)`. Bei 11 Bots x 25 Jahresscheiben sind das
275 Auswertungen und ein Zufallsmaximum von **t = 3,35** - bevor ein
einziger echter Effekt im Spiel ist. §B4 zeigt denselben Mechanismus an
echten Daten: PEAD sah auf 60 Symbolen aus wie der beste Faktor des
Projekts (t = 6,7) und brach auf 800 vollstaendig zusammen.

**Deshalb Walk-Forward.** Die Auswahl trifft immer nur, was VOR dem
Bewertungsfenster liegt:

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

    python scripts/32_lernlauf.py --jahre 15
    python scripts/32_lernlauf.py --jahre 25 --symbole 600
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from alpaca_bot import simulate, universe  # noqa: E402
from alpaca_bot.config import DATA_DIR  # noqa: E402
from alpaca_bot.engine import EngineConfig  # noqa: E402

ERGEBNIS_DB = DATA_DIR / "lernlauf.sqlite"

# Die Achsen, die geprueft werden. Jede unterscheidet sich in GENAU EINEM
# Feld von der Basis - dieselbe Disziplin wie in der Flotte (§J Regel 5),
# denn sonst ist ein Unterschied keinem Parameter zuzuordnen.
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
}
"""`exit_score` und `trail_after_atr` sind bewusst dabei: §G19 haelt fest,
dass beide nie gegengeprueft wurden, obwohl §E den `exit_score` als den
Wert ausweist, der `target_atr` wirkungslos macht."""

# Die LIVE-Konfiguration, gegen die verglichen wird. Nicht `for_reversal()`
# pur: Der Live-Bot laeuft seit dem 30.07.2026 mit deploy_to_target und
# allow_topup (§G6). Ein Vergleich gegen die Vorgaben waere ein Vergleich
# gegen etwas, das nirgends laeuft.
LIVE_BASIS = {"deploy_to_target": True, "allow_topup": True}


def signal_schluessel(over: dict) -> str:
    """Bots mit gleichem Schluessel teilen sich die Signalberechnung.

    Nur `reversal_weights` und `strategy` gehen in die Signale ein - Stop,
    Ziel, Frist und Schwellen wirken erst danach. Ohne diese Gruppierung
    rechnet der Lauf die teuerste Stufe fuer jeden Bot neu (dieselbe
    Ersparnis wie `fleet.signal_schluessel`).
    """
    cfg = EngineConfig.for_reversal(**{**LIVE_BASIS, **over})
    w = cfg.reversal_weights
    return json.dumps({"strategy": cfg.strategy, "rueckgang": w.rueckgang,
                       "rsi2": w.rsi2, "ausverkauf": w.ausverkauf,
                       "band_unten": w.band_unten, "news": w.news,
                       "regime": w.market_regime_filter}, sort_keys=True)


def jahresscheiben(kalender: pd.DatetimeIndex) -> list[tuple[int, pd.Timestamp, pd.Timestamp]]:
    jahre = sorted({d.year for d in kalender})
    out = []
    for j in jahre:
        tage = kalender[kalender.year == j]
        if len(tage) >= 100:          # angebrochene Jahre nicht als Scheibe zaehlen
            out.append((j, tage[0], tage[-1]))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--jahre", type=float, default=15.0)
    ap.add_argument("--symbole", type=int, default=800)
    ap.add_argument("--kapital", type=float, default=30_000.0)
    ap.add_argument("--min-auswahl-jahre", type=int, default=3,
                    help="So viele Jahre muessen vor der ersten Auswahl liegen")
    args = ap.parse_args()

    from alpaca_bot.shadow_daten import MARKET_SYMBOL, lade_bars

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
        w = EngineConfig.for_reversal(
            **{**LIVE_BASIS, **BOTS[gruppen[schluessel][0]]}).reversal_weights
        print(f"  Berechne Signale fuer Gruppe {len(rahmen_je_gruppe)+1}"
              f"/{len(gruppen)} ...", flush=True)
        rahmen_je_gruppe[schluessel] = {
            s: build_reversal_frame(df, markt, w) for s, df in per_symbol.items()}

    # --- Jeder Bot ueber die ganze Historie, Equity je Tag -----------------
    kurven: dict[str, pd.Series] = {}
    for i, (name, over) in enumerate(BOTS.items(), 1):
        cfg = EngineConfig.for_reversal(**{**LIVE_BASIS, **over})
        res = simulate.run(bars, engine_config=cfg, sim_config=scfg,
                           market=markt, verbose=False,
                           signal_frames=rahmen_je_gruppe[signal_schluessel(over)])
        eq = pd.Series(dict(res.equity_curve)) if isinstance(res.equity_curve, list) \
            else pd.Series(res.equity_curve)
        eq.index = pd.to_datetime(eq.index)
        kurven[name] = eq
        print(f"  [{i:2d}/{len(BOTS)}] {name:<20} "
              f"{eq.iloc[-1]/eq.iloc[0]-1:>+8.1%}  {len(res.trades):>5} Trades",
              flush=True)

    kalender = kurven["basis"].index
    scheiben = jahresscheiben(kalender)
    print(f"\n  {len(scheiben)} vollstaendige Jahresscheiben: "
          f"{scheiben[0][0]}-{scheiben[-1][0]}")

    # --- Ergebnis je Bot und Jahr ------------------------------------------
    tab = {}
    for name, eq in kurven.items():
        r = eq.pct_change()
        tab[name] = {j: float((1 + r[(r.index >= a) & (r.index <= b)]).prod() - 1)
                     for j, a, b in scheiben}
    jahres = pd.DataFrame(tab).T
    print("\n" + "=" * 78)
    print("  ERGEBNIS JE BOT UND JAHR (in %)")
    print("=" * 78)
    print((jahres * 100).round(1).to_string())

    # --- Walk-Forward: traegt die Auswahl ins naechste Jahr? ---------------
    print("\n" + "=" * 78)
    print("  WALK-FORWARD - Auswahl nur aus der Vergangenheit")
    print("=" * 78)
    print(f"  {'Jahr':<6} {'gewaehlt (aus Vorjahren)':<24} {'sein Jahr':>10} "
          f"{'Basis':>9} {'Differenz':>10}")
    zeilen = []
    for idx, (j, _, _) in enumerate(scheiben):
        if idx < args.min_auswahl_jahre:
            continue
        vorher = [s[0] for s in scheiben[:idx]]
        # Auswahl: bester mittlerer Jahresertrag ueber ALLE Vorjahre.
        mittel = jahres[vorher].mean(axis=1)
        gewaehlt = str(mittel.idxmax())
        e_gew = float(jahres.loc[gewaehlt, j])
        e_bas = float(jahres.loc["basis", j])
        zeilen.append({"jahr": j, "bot": gewaehlt, "gewaehlt": e_gew,
                       "basis": e_bas, "diff": e_gew - e_bas})
        print(f"  {j:<6} {gewaehlt:<24} {e_gew*100:>+9.1f}% {e_bas*100:>+8.1f}% "
              f"{(e_gew-e_bas)*100:>+9.1f}pp")

    if len(zeilen) >= 3:
        d = np.array([z["diff"] for z in zeilen])
        t = d.mean() / (d.std(ddof=1) / np.sqrt(len(d)))
        print(f"\n  Ueber {len(d)} ungesehene Jahre:")
        print(f"    mittlere Differenz : {d.mean()*100:+.2f} Prozentpunkte/Jahr")
        print(f"    Jahre mit Vorsprung: {(d > 0).sum()} von {len(d)}")
        print(f"    t = {t:+.2f}   (Schwelle 2, und das ist die MILDE Huerde)")
        print()
        if abs(t) < 2:
            print("  KEIN BEFUND. Die aus der Historie getroffene Auswahl traegt")
            print("  nicht nachweisbar ins naechste Jahr. Das ist eine Aussage")
            print("  ueber das VERFAHREN, nicht ueber die einzelnen Bots - und")
            print("  sie gilt fuer jede kuenftige Auswahl nach demselben Muster.")
        elif t > 0:
            print("  Die Auswahl traegt. ACHTUNG: Survivorship (2-4 pp/Jahr,")
            print("  §G11) ist hier NICHT abgezogen - bei absoluten Renditen")
            print("  voll wirksam, bei der Differenz weitgehend gekuerzt.")
        else:
            print("  Die Auswahl schadet - sie waehlt systematisch schlechter")
            print("  als der unveraenderte Basis-Bot.")

    # --- Stabilitaet: wie oft wechselt die Auswahl? ------------------------
    if len(zeilen) >= 2:
        wechsel = sum(1 for a, b in zip(zeilen, zeilen[1:]) if a["bot"] != b["bot"])
        print(f"\n  Die Auswahl wechselte in {wechsel} von {len(zeilen)-1} "
              f"Uebergaengen den Bot.")
        print("  Ein haeufiger Wechsel heisst: Die Rangfolge ist nicht stabil,")
        print("  also war der jeweilige Sieger ueberwiegend Zufall (§B2).")

    jahres.to_csv(DATA_DIR / "lernlauf_jahre.csv")
    print(f"\n  Jahrestabelle gespeichert: {DATA_DIR / 'lernlauf_jahre.csv'}")
    print("\n  Dieser Lauf darf eine Idee VERWERFEN, nicht abnehmen")
    print("  (Survivorship, fehlender Nachrichtenfaktor - siehe Modulkopf).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
