"""Schritt 26: Der Lernkern - Modell gegen Score, auf der echten Historie.

**Die eine Frage, die dieser Lauf beantwortet:**

    Sortiert ein gelerntes Modell die Kandidaten besser als der
    handgebaute Score - gemessen ueber Handelstage, nach Korrektur
    der Ueberlappung, gegen die Zufallsschwelle der Flotte?

Warum die Historie und nicht der Schatten: Gemessen am 22.08.2026 hat
der Schatten 20.690 Vorhersagen, aber **19** unabhaengige Handelstage.
Die Historie hat rund 969. Ein Effekt der Groesse, die dieses Projekt
real misst (IC ~0,02), braucht ueber 900 Handelstage bis zur Schwelle -
der Schatten kann diese Frage heute nicht tragen, egal wie oft man
rechnet (BEFUNDE §G14, docs/LERNTEMPO.md §5a).

**Was dieser Lauf NICHT darf.** Er nimmt nichts ab. Survivorship allein
schenkt 2-4 Prozentpunkte im Jahr - mehr, als die Strategie je verdienen
wird (BEFUNDE §G11). Jedes Ergebnis ist eine Obergrenze und ein Filter:
Was hier durchfaellt, braucht keinen Flottenplatz. Was besteht, ist eine
Hypothese fuer den Schatten, kein Signal.

    python scripts/26_lernkern.py                 # Lauf ueber die Historie
    python scripts/26_lernkern.py --bericht       # Registry ansehen
    python scripts/26_lernkern.py --symbole 300   # kleiner Probelauf
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd

from alpaca_bot import dataset, fleet, lernkern, nutzung, universe
from alpaca_bot.data import get_bars


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--symbole", type=int, default=1200,
                    help="Universumsgroesse (Vorgabe 1200 = wie der Live-Bot)")
    ap.add_argument("--jahre", type=float, default=7.0)
    ap.add_argument("--horizont", type=int, default=5,
                    help="Renditefenster in Handelstagen (Vorgabe 5, siehe §A)")
    ap.add_argument("--modell", default="gbm", choices=["gbm", "rf", "logreg"])
    ap.add_argument("--falten", type=int, default=5)
    ap.add_argument("--bericht", action="store_true", help="nur Registry zeigen")
    ap.add_argument("--kein-cache", action="store_true")
    args = ap.parse_args()

    if args.bericht:
        print(lernkern.bericht())
        return 0

    print("=" * 78)
    print("  LERNKERN - Modell gegen Score auf der Historie")
    print("=" * 78)
    print(f"  Schwelle dieser Messung: t > {fleet.schwelle_sigma():.2f} "
          f"({fleet.n_versuche()} Versuche)")
    print()

    print(f"  [1/5] Universum ({args.symbole} Symbole) ...")
    syms = universe.load_universe(max_symbols=args.symbole)
    print(f"        {len(syms)} Symbole")

    print(f"  [2/5] Bars ({args.jahre} Jahre, "
          f"{'Cache an' if not args.kein_cache else 'Cache aus'}) ...")
    bars = universe.fetch_history(syms, years=args.jahre, verbose=len(syms) > 300,
                                  use_cache=not args.kein_cache)
    print(f"        {len(bars):,} Bars".replace(",", "."))

    # SPY ist nicht optional: ohne ihn faellt der Regimefilter im Score
    # ersatzlos aus (BEFUNDE §G11 Fund 2) - der Vergleich waere dann
    # gegen einen Score gefahren, den der Bot nie benutzt.
    print("  [3/5] SPY (Marktbezug, Pflicht) ...")
    # Bevorzugt aus demselben Frame - dann stimmen die Zeitstempel per
    # Konstruktion (so macht es scripts/10_simulate.py:241).
    if "SPY" in bars.index.get_level_values("symbol"):
        spy = bars.xs("SPY", level="symbol")["close"]
        quelle_spy = "aus dem Bars-Frame"
    else:
        spy = get_bars("SPY", "1D", lookback_days=int(args.jahre * 365),
                       use_cache=not args.kein_cache)
        spy = spy.xs("SPY", level="symbol")["close"]
        quelle_spy = "separat geladen"
    print(f"        {len(spy)} Tage ({quelle_spy})")

    print("  [4/5] Modell trainieren und bewerten ...")
    nutzung.melden("lernkern.trainieren", 1,
                   signatur=f"{args.symbole}s_{args.jahre}j_{args.modell}")
    v, g_modell = lernkern.trainieren(
        bars, quelle="historie", horizont=args.horizont, market=spy,
        model_kind=args.modell, n_falten=args.falten, verbose=True)

    print("  [5/5] Denselben Massstab an den bestehenden Score anlegen ...")
    panel = dataset.baue_panel(bars, horizont=args.horizont, market=spy,
                               verbose=False)
    score = dataset.baue_score(bars, panel, market=spy, verbose=True)
    ueber = panel.roh_rendite - panel.roh_rendite.groupby(panel.tage).transform("median")
    g_score = dataset.guete(score, ueber, panel.tage, name="Score (Bot heute)",
                            horizont=args.horizont, schwelle=v.schwelle)

    print()
    print(dataset.vergleichsbericht(
        [g_modell, g_score],
        frage="Sortiert das gelernte Modell besser als der handgebaute Score?"))

    print()
    # verbose=False: Das Skript druckt den Rueckgabewert selbst.
    print(lernkern.abnehmen(v.model_version, verbose=False))
    print()
    print("  Dieser Lauf ist ein FILTER, keine Abnahme (BEFUNDE §G11):")
    print("  Survivorship schenkt 2-4 pp im Jahr. Jedes Ergebnis ist eine")
    print("  Obergrenze. Der Weg in die Handelslogik fuehrt ueber eine")
    print("  Voranmeldung in der Flotte - fruehestens nach dem 10.10.2026.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
