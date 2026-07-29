#!/usr/bin/env python3
"""Schritt 15: Was haben wir aus den abgeschlossenen Trades gelernt?

Wertet den Lebenslauf jedes geschlossenen Trades aus - nicht nur Ein- und
Ausstieg, sondern auch den Verlauf dazwischen und danach:

  * War der Stop zu eng? (Wie oft lief es nach dem Ausstoppen doch hoch?)
  * War das Ziel zu niedrig? (Wie viel Gewinn blieb liegen?)
  * Wie tief lagen erfolgreiche Trades zwischenzeitlich im Minus?
  * Sortiert der Einstiegs-Score ueberhaupt richtig?

Jeder Befund traegt seine Grundlage mit. Unterhalb der Mindestanzahl
gelten sie als 'zu duenn' und duerfen KEINE Regelaenderung ausloesen -
bei zwanzig Trades ist jedes Muster Rauschen.

    python scripts/15_lernbericht.py
    python scripts/15_lernbericht.py --mindestanzahl 50
"""

from __future__ import annotations

import argparse
import sys

import pandas as pd

from alpaca_bot.lifecycle import Lifecycle, report


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mindestanzahl", type=int, default=30,
                   help="Ab wie vielen Trades gilt ein Befund als belastbar")
    p.add_argument("--details", action="store_true",
                   help="Alle Trades einzeln auflisten")
    args = p.parse_args()

    lc = Lifecycle()
    trades = lc.table()

    print(report(trades, args.mindestanzahl))

    if args.details and not trades.empty:
        print("\n" + "=" * 74)
        print("  EINZELNE TRADES")
        print("=" * 74)
        cols = ["symbol", "entry_date", "exit_date", "entry_price", "exit_price",
                "return_pct", "mae_pct", "mfe_pct", "after_5d", "exit_reason",
                "entry_score"]
        show = trades[[c for c in cols if c in trades.columns]].copy()
        for c in ("entry_date", "exit_date"):
            if c in show:
                show[c] = pd.to_datetime(show[c], errors="coerce", utc=True)
                show[c] = show[c].dt.strftime("%d.%m")
        print(show.to_string(index=False))
        print()
        print("  mae_pct  = tiefster Punkt waehrend der Haltezeit")
        print("  mfe_pct  = hoechster Punkt waehrend der Haltezeit")
        print("  after_5d = Kursbewegung 5 Tage NACH dem Ausstieg")

    if trades.empty:
        print("\n  Noch keine abgeschlossenen Trades erfasst.")
        print("  Der Lebenslauf wird beim ersten Verkauf des Bots angelegt.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
