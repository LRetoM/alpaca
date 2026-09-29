#!/usr/bin/env python3
"""Trennt fremde JSONL-Dateien vom Rohprotokoll des Live-Journals.

**Der Anlass (23.08.2026, BEFUNDE §G19 Fund 4).** `journal.py` beschreibt
seine Aufgabenteilung so:

    "SQLite ist die Auswertungsschicht, JSONL die Sicherung - waere die
     Datenbank je beschaedigt, liesse sie sich daraus vollstaendig
     rekonstruieren."

Gemessen am 23.08.2026 im Produktivverzeichnis:

    JSONL-Dateien gesamt      2.618
      Lauf im Journal            472
      KEIN Lauf im Journal     2.146   <- 28,6 % aller Zeilen
      davon Symbol TEST           84

Ursache war ein Modul-Global: `Journal(pfad)` isolierte die SQLite,
`RunLogger` schrieb die JSONL aber immer nach `DATA_DIR/journal_raw`.
Jeder Testlauf legte dort ab. **Das Leck ist seit dem 23.08.2026
geschlossen** (`Journal.raw_dir` haengt jetzt an der Datenbank) - dieses
Skript raeumt den Bestand, der bis dahin entstanden ist.

**Warum nicht loeschen.** Eine Datei, die zu keinem Lauf gehoert, ist
nicht zwingend wertlos: Sie kann auch aus einem Lauf stammen, dessen
SQLite-Zeile spaeter bereinigt wurde (`14_journal_bereinigen.py` hat
genau das getan). Verschoben wird deshalb nach `journal_raw/fremd/`.
Wer sicher ist, loescht dort von Hand.

**Das Kriterium.** Eine Datei gehoert dazu, wenn ihr Dateiname (= die
`run_id`) in `runs` steht. Das ist eine Eigenschaft der Daten selbst,
kein Datumsraten - dieselbe Ueberlegung wie bei den Legacy-Zeilen in
`journal._slippage_basis`, die sich am `status`-Text erkennen lassen.

    python scripts/28_rohprotokoll_bereinigen.py              # Vorschau
    python scripts/28_rohprotokoll_bereinigen.py --ausfuehren
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from alpaca_bot.journal import JOURNAL_DB, RAW_DIR  # noqa: E402

ZIEL = RAW_DIR / "fremd"


def bekannte_laeufe(db: Path) -> set[str]:
    if not db.exists():
        return set()
    with sqlite3.connect(f"file:{db}?mode=ro", uri=True) as c:
        return {r[0] for r in c.execute("SELECT run_id FROM runs")}


def einordnen(raw_dir: Path, laeufe: set[str]) -> tuple[list[Path], list[Path]]:
    """Teilt die Dateien in (gehoert dazu, fremd) auf.

    Der Dateiname ist `<run_id>.jsonl` oder `<run_id>__<name>.csv` - die
    Snapshot-Dateien gehoeren demselben Lauf und werden mitgezaehlt,
    sonst bliebe die Sicherung eines Laufs halb hier und halb dort.
    """
    dazu: list[Path] = []
    fremd: list[Path] = []
    for p in sorted(raw_dir.iterdir()):
        if p.is_dir():
            continue
        run_id = p.stem.split("__")[0]
        (dazu if run_id in laeufe else fremd).append(p)
    return dazu, fremd


def zeilen(pfade: list[Path]) -> int:
    n = 0
    for p in pfade:
        if p.suffix != ".jsonl":
            continue
        try:
            with p.open(encoding="utf-8") as f:
                n += sum(1 for _ in f)
        except OSError:
            pass
    return n


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ausfuehren", action="store_true",
                    help="Verschieben. Ohne dieses Flag nur Vorschau.")
    args = ap.parse_args()

    if not RAW_DIR.exists():
        print(f"  {RAW_DIR} gibt es nicht - nichts zu tun.")
        return 0

    laeufe = bekannte_laeufe(JOURNAL_DB)
    dazu, fremd = einordnen(RAW_DIR, laeufe)
    z_dazu, z_fremd = zeilen(dazu), zeilen(fremd)
    gesamt = z_dazu + z_fremd

    print("=" * 74)
    print("  ROHPROTOKOLL - GEHOERT ES ZUM JOURNAL?")
    print("=" * 74)
    print(f"  Verzeichnis    : {RAW_DIR}")
    print(f"  Laeufe in runs : {len(laeufe)}")
    print()
    print(f"  Dateien gesamt : {len(dazu) + len(fremd)}")
    print(f"    zugeordnet   : {len(dazu):>6}   {z_dazu:>7} Zeilen")
    print(f"    FREMD        : {len(fremd):>6}   {z_fremd:>7} Zeilen"
          f"   ({z_fremd / gesamt:.1%})" if gesamt else "")
    print()

    if not fremd:
        print("  Nichts Fremdes gefunden - die Sicherung ist sortenrein.")
        return 0

    mit_test = sum(
        1 for p in fremd if p.suffix == ".jsonl"
        and '"symbol": "TEST"' in p.read_text(encoding="utf-8", errors="ignore")
    )
    print(f"  Davon mit Symbol TEST: {mit_test}")
    print()
    print("  Beispiele:")
    for p in fremd[:5]:
        print(f"    {p.name}  ({p.stat().st_size} Byte)")
    if len(fremd) > 5:
        print(f"    ... und {len(fremd) - 5} weitere")
    print()

    if not args.ausfuehren:
        print(f"  VORSCHAU - es wurde nichts verschoben.")
        print(f"  Ziel waere: {ZIEL}")
        print("  Ausfuehren mit --ausfuehren")
        return 0

    ZIEL.mkdir(parents=True, exist_ok=True)
    verschoben = 0
    for p in fremd:
        try:
            shutil.move(str(p), str(ZIEL / p.name))
            verschoben += 1
        except OSError as e:
            print(f"    [!] {p.name}: {type(e).__name__}: {e}")

    print(f"  {verschoben} Datei(en) verschoben nach {ZIEL}")
    print()
    print("  Sie sind NICHT geloescht. Wer sicher ist, dass nichts davon")
    print("  gebraucht wird, entfernt das Verzeichnis von Hand.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
