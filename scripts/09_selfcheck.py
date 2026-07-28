#!/usr/bin/env python3
"""Selbstpruefung - VOR jeder groesseren Aenderung ausfuehren.

Prueft den Code gegen die Projektverfassung: Rate-Limits verdrahtet,
dry_run als Standard, keine Zeitreihen-Mischung, keine Zugangsdaten im
Code, Features ohne Zukunftslecks, Gebuehrensaetze aktuell.

    python scripts/09_selfcheck.py
    python scripts/09_selfcheck.py --charter     # nur die Verfassung zeigen
    python scripts/09_selfcheck.py --progress    # werden wir besser?
"""

from __future__ import annotations

import argparse
import sys

from alpaca_bot import selfcheck


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--charter", action="store_true")
    p.add_argument("--progress", action="store_true")
    p.add_argument("--horizon", type=int, default=5)
    args = p.parse_args()

    if args.charter:
        print(selfcheck.charter_text())
        return 0

    if args.progress:
        print(selfcheck.progress_report(args.horizon))
        return 0

    print(selfcheck.charter_text())
    print()
    report = selfcheck.run_all()
    print(report)
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
