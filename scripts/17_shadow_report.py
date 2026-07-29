#!/usr/bin/env python3
"""Schritt 17: Auswertung und Pruefung des Schattenbetriebs.

Beantwortet die Fragen, wegen derer der Schattenbetrieb existiert - und
weist bei jeder Zahl aus, wie belastbar sie ist.

DREI EHRLICHKEITSREGELN SIND FEST EINGEBAUT:

  1. Jede Renditekennzahl wird gegen den Universums-Median desselben Tages
     gerechnet. Ein Buch mit +3 % in einer Woche, in der das Universum +4 %
     machte, ist ein Verlust.
  2. Ausgewiesen wird `n_tage`, nicht nur `n`. Alle Vorhersagen eines Tages
     sind vom selben Marktfaktor getrieben - 200 Kandidaten an einem Tag
     sind naeher an EINER Beobachtung als an 200.
  3. Die Sperrzone (letzte 20 % der Tage) bleibt abgeschnitten, bis eine
     Entscheidung gefallen ist. `--sperrzone-oeffnen` muss ausdruecklich
     gesetzt werden und wird mit ausgegeben.

    python scripts/17_shadow_report.py                 # Auswertung
    python scripts/17_shadow_report.py --pruefen       # die 9 Pruefungen
    python scripts/17_shadow_report.py --pruefen --replay
    python scripts/17_shadow_report.py --kohorten      # Lernkurve je Woche
    python scripts/17_shadow_report.py --kalibrierung  # sortiert der Score?
    python scripts/17_shadow_report.py --muster        # Musterspeicher
    python scripts/17_shadow_report.py --muster-suchen # Kandidaten suchen
    python scripts/17_shadow_report.py --muster-pruefen # Verfallspruefung
    python scripts/17_shadow_report.py --hypothesen
"""

from __future__ import annotations

import argparse
import sys

import pandas as pd

from alpaca_bot import hypotheses, patterns, shadow_eval
from alpaca_bot.shadow import ShadowStore, pruefbericht


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--buch", default="rangliste", choices=["rangliste", "spiegel"])
    p.add_argument("--pruefen", action="store_true", help="Die 9 Korrektheitspruefungen")
    p.add_argument("--replay", action="store_true", help="Replay-Test mitlaufen lassen")
    p.add_argument("--kohorten", action="store_true", help="Wochenkohorten (Lernkurve)")
    p.add_argument("--kalibrierung", action="store_true", help="Sortiert der Score?")
    p.add_argument("--muster", action="store_true")
    p.add_argument("--muster-suchen", action="store_true")
    p.add_argument("--muster-pruefen", action="store_true")
    p.add_argument("--hypothesen", action="store_true")
    p.add_argument("--sperrzone-oeffnen", action="store_true",
                   help="ACHTUNG: hebt die unabhaengige Pruefung auf")
    args = p.parse_args()

    store = ShadowStore()

    if args.pruefen:
        print(pruefbericht(store, mit_replay=args.replay))
        return 0

    if args.muster:
        print(patterns.bericht(store))
        return 0

    if args.muster_suchen:
        print("=" * 78)
        print("  KANDIDATENSUCHE IN DEN REGIME-DIMENSIONEN")
        print("=" * 78)
        patterns.kandidaten_suchen(store, anlegen=False)
        return 0

    if args.muster_pruefen:
        print("=" * 78)
        print("  VERFALLSPRUEFUNG DER MUSTER")
        print("=" * 78)
        df = patterns.pruefen(store)
        if df.empty:
            print("  Keine Muster erfasst.")
        return 0

    if args.hypothesen:
        print(hypotheses.bericht(store))
        return 0

    if args.sperrzone_oeffnen:
        print("!" * 78)
        print("  SPERRZONE GEOEFFNET. Ab jetzt ist sie als unabhaengige")
        print("  Pruefung verbraucht - jede Entscheidung, die diese Zahlen")
        print("  mitbenutzt, ist nicht mehr unabhaengig bestaetigbar.")
        print("!" * 78)
        print()

    print(shadow_eval.bericht(store, buch=args.buch,
                              sperrzone_oeffnen=args.sperrzone_oeffnen))

    if args.kalibrierung:
        df = shadow_eval.datensatz(store, buch=args.buch,
                                   sperrzone_oeffnen=args.sperrzone_oeffnen)
        print()
        print("=" * 78)
        print("  KALIBRIERUNG: erreichen hohe Scores wirklich mehr?")
        print("=" * 78)
        for bot, g in df.groupby("bot_id"):
            k = shadow_eval.kalibrierung(g)
            if k.empty:
                continue
            print(f"\n  {bot}")
            print(k.to_string())
        print()
        print("  Eine Rangliste, die nicht monoton steigt, sortiert nicht -")
        print("  dann ist der Score als Auswahlkriterium wertlos.")

    if args.kohorten:
        k = shadow_eval.kohorten(store, buch=args.buch,
                                 sperrzone_oeffnen=args.sperrzone_oeffnen)
        print()
        print("=" * 78)
        print("  WOCHENKOHORTEN - wird es besser?")
        print("=" * 78)
        if k.empty:
            print("  Noch keine Kohorten.")
        else:
            with pd.option_context("display.width", 200, "display.max_columns", 30):
                print(k[["kohorte", "bot_id", "n_tage", "n_vorhersagen", "ic_5d",
                         "ic_t_stat", "trefferquote", "basisrate", "ueberschuss",
                         "kalibrierung"]].to_string(index=False))
            print()
            print("  Vergleiche NUR gleiche Code-Versionen miteinander -")
            print("  sonst vermischen sich Regimewechsel und Codeaenderungen.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
