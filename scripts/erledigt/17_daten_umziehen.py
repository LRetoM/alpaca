#!/usr/bin/env python3
"""Einmaliger Umzug der Datenbanken aus dem TCC-geschuetzten Documents-Ordner.

Grund: `~/Documents/alpaca/data` liegt unter macOS' TCC-Dateischutz fuer den
"Dokumente"-Ordner. Ein interaktives Terminal darf dort schreiben, ein von
launchd headless gestarteter Hintergrunddienst nicht zuverlaessig - das hat
am 30./31.07.2026 den Handelsbot abstuerzen lassen (state.sqlite liess sich
nicht mehr oeffnen). config.py zeigt jetzt auf
~/Library/Application Support/alpaca-bot/data - dieses Skript verschiebt die
bestehenden Dateien dorthin, ohne etwas zu verlieren.

    python scripts/17_daten_umziehen.py --vorschau
    python scripts/17_daten_umziehen.py --ausfuehren
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

OLD_DIR = Path(__file__).resolve().parents[1] / "data"


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--ausfuehren", action="store_true",
                   help="Ohne diesen Schalter passiert nichts")
    args = p.parse_args()

    from alpaca_bot.config import DATA_DIR as NEW_DIR

    print("=" * 70)
    print("  DATEN-UMZUG")
    print("=" * 70)
    print(f"  Alt : {OLD_DIR}")
    print(f"  Neu : {NEW_DIR}")
    print()

    if not OLD_DIR.exists():
        print("  Kein alter Datenordner vorhanden - nichts zu tun.")
        return 0

    to_move = list(OLD_DIR.rglob("*"))
    files = [f for f in to_move if f.is_file()]
    print(f"  {len(files)} Datei(en) gefunden:")
    for f in sorted(files):
        rel = f.relative_to(OLD_DIR)
        ziel = NEW_DIR / rel
        kollision = " (existiert bereits im Ziel!)" if ziel.exists() else ""
        print(f"    {rel}{kollision}")

    if not args.ausfuehren:
        print("\n  VORSCHAU - es wurde nichts verschoben.")
        print("  Zum Ausfuehren: python scripts/17_daten_umziehen.py --ausfuehren")
        return 0

    verschoben = uebersprungen = 0
    for f in files:
        rel = f.relative_to(OLD_DIR)
        ziel = NEW_DIR / rel
        ziel.parent.mkdir(parents=True, exist_ok=True)
        if ziel.exists():
            print(f"  UEBERSPRUNGEN (existiert bereits): {rel}")
            uebersprungen += 1
            continue
        shutil.move(str(f), str(ziel))
        verschoben += 1

    print(f"\n  {verschoben} verschoben, {uebersprungen} uebersprungen.")

    # Alten Ordner nur entfernen, wenn er jetzt wirklich leer ist -
    # nichts erzwingen, falls doch noch etwas drinsteht.
    restdateien = [f for f in OLD_DIR.rglob("*") if f.is_file()]
    if not restdateien:
        shutil.rmtree(OLD_DIR)
        print(f"  Alter, jetzt leerer Ordner entfernt: {OLD_DIR}")
    else:
        print(f"  Alter Ordner behalten - enthaelt noch {len(restdateien)} Datei(en).")

    return 0


if __name__ == "__main__":
    sys.exit(main())
