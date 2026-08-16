#!/usr/bin/env python3
"""Schritt 22: ALLE Tests - Forschungsschicht und Betriebsschicht.

Der eine Befehl, der nach jeder Codeaenderung laufen muss, BEVOR die
Dienste neu gestartet werden.

    python scripts/22_tests.py            # alles
    python scripts/22_tests.py --schnell  # nur die Betriebsschicht (Sekunden)

Warum zwei Schichten:

    00_selftest.py  Forschung  - Indikatoren, Backtest, ML, Lookahead
    tests/          Betrieb    - Handelslogik, Risiko, Protokoll, Konsistenz

Die Betriebsschicht entstand am 16.08.2026, nachdem jede gezielte
Nachfrage einen Fehler zutage gefoerdert hatte, den der Selbsttest nicht
fand - er prueft die Forschungsschicht, waehrend Handelslogik und
Protokollierung ungetestet waren (siehe docs/TESTPLAN.md).
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

WURZEL = Path(__file__).resolve().parents[1]
PYTHON = WURZEL / ".venv" / "bin" / "python"


def lauf(titel: str, befehl: list[str]) -> bool:
    print(f"\n{'=' * 74}\n  {titel}\n{'=' * 74}")
    return subprocess.run(befehl, cwd=WURZEL).returncode == 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--schnell", action="store_true",
                   help="Nur die Betriebsschicht (pytest, wenige Sekunden)")
    args = p.parse_args()

    ergebnisse: list[tuple[str, bool]] = []

    ergebnisse.append(("Betriebsschicht (pytest)",
                       lauf("BETRIEBSSCHICHT — Handelslogik, Risiko, Protokoll",
                            [str(PYTHON), "-m", "pytest", "tests/", "-q",
                             "--no-header", "-p", "no:warnings"])))

    if not args.schnell:
        ergebnisse.append(("Forschungsschicht (00_selftest)",
                           lauf("FORSCHUNGSSCHICHT — Indikatoren, Backtest, ML",
                                [str(PYTHON), "scripts/00_selftest.py"])))

    print(f"\n{'=' * 74}")
    for name, ok in ergebnisse:
        print(f"  {'BESTANDEN' if ok else 'FEHLGESCHLAGEN':<16} {name}")
    print("=" * 74)

    if all(ok for _, ok in ergebnisse):
        print("\n  Alles gruen. Dienste koennen neu gestartet werden.")
        return 0
    print("\n  NICHT neu starten, bevor das behoben ist.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
