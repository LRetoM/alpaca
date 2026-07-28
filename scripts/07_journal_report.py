#!/usr/bin/env python3
"""Schritt 7: Auswertung des Handelsprotokolls - was haben wir gelernt?

Beantwortet die Fragen, wegen derer ueberhaupt protokolliert wird:
  * Welche Begruendung war tatsaechlich richtig?
  * Ist die Ausfuehrung schlechter als im Backtest angenommen?
  * Gibt es Luecken im Protokoll?
  * Halten wir uns noch an den Plan?

    python scripts/07_journal_report.py
    python scripts/07_journal_report.py --evaluate --horizon 5
"""

from __future__ import annotations

import argparse
import sys

import pandas as pd

from alpaca_bot import data, selfcheck
from alpaca_bot.journal import Journal, make_price_lookup


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--evaluate", action="store_true",
                   help="Ergebnisse zu Entscheidungen nachtragen (laedt Kurse)")
    p.add_argument("--horizon", type=int, default=5)
    p.add_argument("--expected-slippage", type=float, default=3.0)
    args = p.parse_args()

    j = Journal()
    print(j.summary())

    dec = j.table("decisions")
    if dec.empty:
        print("\nNoch keine Entscheidungen protokolliert.")
        print("  -> scripts/05_paper_trade.py oder 06_event_study.py laufen lassen.")
        return 0

    # --- Ergebnisse nachtragen ---
    if args.evaluate:
        symbols = sorted(dec["symbol"].unique())
        print(f"\nLade Kurse fuer {len(symbols)} Symbole zur Bewertung ...")
        bars = data.get_bars(symbols, "1D", lookback_days=400)
        n = j.evaluate_outcomes(make_price_lookup(bars), horizons=(1, 5, 20))
        print(f"  {n} Ergebnisse nachgetragen.")

    # --- Entscheidungsqualitaet ---
    print("\n" + "=" * 70)
    print(f"  ENTSCHEIDUNGSQUALITAET NACH BEGRUENDUNG (Horizont {args.horizon} Tage)")
    print("=" * 70)
    q = j.decision_quality(args.horizon)
    if q.empty:
        print("  Noch keine bewerteten Ergebnisse. Mit --evaluate nachtragen.")
    else:
        print(q.to_string())
        print()
        print("  'mittel' = durchschnittliche Folgerendite, wenn diese Begruendung zutraf.")
        print("  Begruendungen mit negativem Mittel ueber >30 Faelle gehoeren entfernt.")
        weak = q[(q["mittel"] < 0) & (q["n"] >= 30)]
        if not weak.empty:
            print(f"\n  KANDIDATEN ZUM ENTFERNEN: {', '.join(weak.index)}")

    # --- Ausfuehrungsqualitaet ---
    print("\n" + "=" * 70)
    print("  AUSFUEHRUNG: ANNAHME GEGEN REALITAET")
    print("=" * 70)
    slip = j.slippage_report()
    if slip.empty:
        print("  Noch keine echten Ausfuehrungen (nur dry-run oder Paper).")
        print("  Diese Auswertung wird erst im Live-Betrieb aussagekraeftig -")
        print("  aber genau dort entscheidet sie ueber Gewinn und Verlust.")
    else:
        print(slip.to_string())
        from alpaca_bot import costs

        print()
        print(costs.reconcile(args.expected_slippage, slip))

    # --- Blockierte Entscheidungen ---
    blocked = dec[dec["blocked_by"].notna()]
    if not blocked.empty:
        print("\n" + "=" * 70)
        print("  VON REGELN BLOCKIERTE ENTSCHEIDUNGEN")
        print("=" * 70)
        print(blocked.groupby("blocked_by").size().to_string())
        print("\n  Diese sind die lehrreichsten: Waeren sie gut gewesen, ist die")
        print("  Regel zu streng. Waren sie schlecht, hat die Regel Geld gespart.")

    # --- Halten wir uns an den Plan? ---
    print("\n" + "=" * 70)
    print("  PLANTREUE")
    print("=" * 70)
    report = selfcheck.run_all()
    print(report)

    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
