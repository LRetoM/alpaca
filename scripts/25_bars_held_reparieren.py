#!/usr/bin/env python3
"""Schritt 25: Die falschen `bars_held`-Nullen aus der Zeit vor dem 15.08. beheben.

**Der Befund** (22.08.2026, `docs/BEFUNDE.md` §G13): 36 von 56
abgeschlossenen Trades tragen `bars_held = 0`, obwohl ihre Ein- und
Ausstiegsdaten 2 bis 5 Handelstage hergeben. Alle stammen aus der Zeit
vor dem 17.08. - Rueckstand des am 15.08. behobenen Fehlers (§G).

**Warum das repariert gehoert und nicht nur dokumentiert:** Eine Null
sieht wie eine Messung aus. Sie geht in jeden Mittelwert ein, ohne
aufzufallen - der Median der Haltedauer lag dadurch bei 0 statt bei 5.
Ein fehlender Wert waere harmlos gewesen, ein falscher ist es nicht.

**Warum die Rekonstruktion belastbar ist:** Die 20 Trades, die nach der
Reparatur entstanden sind, stimmen mit `np.busday_count(einstieg,
ausstieg)` **exakt** ueberein - groesste Abweichung 0 Tage. Die Formel
ist damit an echten Daten dieses Bots geprueft, nicht angenommen.

**Herkunft bleibt sichtbar.** Die Spalte `bars_held_quelle` haelt fest,
welcher Wert gemessen und welcher rekonstruiert ist. Ohne diesen Vermerk
waere spaeter nicht mehr unterscheidbar, was Messung und was Nachtrag
ist - genau der Fehler, der die Simulation monatelang unbemerkt liess
(§G11: eine `trades.csv` ohne `lauf.json` ist wertlos).

    python scripts/25_bars_held_reparieren.py            # Trockenlauf
    python scripts/25_bars_held_reparieren.py --schreiben
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from alpaca_bot.lifecycle import LIFECYCLE_DB  # noqa: E402

TOLERANZ = 1
"""Ein Handelstag Spiel - `busday_count` kennt keine Boersenfeiertage."""


def analysieren(db: Path) -> pd.DataFrame:
    """Welche Zeilen widersprechen ihren eigenen Datumsangaben?"""
    with sqlite3.connect(db) as c:
        t = pd.read_sql("SELECT rowid, trade_id, symbol, entry_date, exit_date,"
                        " bars_held FROM trades WHERE exit_date IS NOT NULL", c)
    if t.empty:
        return t

    ein = pd.to_datetime(t["entry_date"], format="mixed", utc=True, errors="coerce")
    aus = pd.to_datetime(t["exit_date"], format="mixed", utc=True, errors="coerce")
    t["_bh"] = pd.to_numeric(t["bars_held"], errors="coerce")
    t = t[ein.notna() & aus.notna() & t["_bh"].notna()].copy()
    ein, aus = ein[t.index], aus[t.index]

    t["erwartet"] = [np.busday_count(a.date(), b.date()) for a, b in zip(ein, aus)]
    t["abweichung"] = (t["_bh"] - t["erwartet"]).abs()
    return t


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--schreiben", action="store_true",
                   help="Aenderungen wirklich speichern (Vorgabe: Trockenlauf)")
    args = p.parse_args()

    db = Path(LIFECYCLE_DB)
    if not db.exists():
        print(f"Keine Datenbank unter {db}")
        return 1

    t = analysieren(db)
    if t.empty:
        print("Keine abgeschlossenen Trades.")
        return 0

    falsch = t[t["abweichung"] > TOLERANZ]
    print("=" * 74)
    print("  BARS_HELD GEGEN DIE DATUMSANGABEN")
    print("=" * 74)
    print(f"  Abgeschlossene Trades : {len(t)}")
    print(f"  Stimmig               : {len(t) - len(falsch)}")
    print(f"  Widerspruechlich      : {len(falsch)}")

    if falsch.empty:
        print("\n  Nichts zu reparieren.")
        return 0

    print(f"\n  {'Symbol':<8}{'ist':>5}{'soll':>6}  Einstieg      Ausstieg")
    print("  " + "-" * 60)
    for _, r in falsch.head(10).iterrows():
        print(f"  {r['symbol']:<8}{r['_bh']:>5.0f}{r['erwartet']:>6.0f}  "
              f"{str(r['entry_date'])[:10]}    {str(r['exit_date'])[:10]}")
    if len(falsch) > 10:
        print(f"  ... und {len(falsch) - 10} weitere")

    print(f"\n  Neuer Median der Haltedauer: {t['_bh'].median():.0f} -> "
          f"{pd.concat([t.loc[~t.index.isin(falsch.index), '_bh'], falsch['erwartet']]).median():.0f}")

    if not args.schreiben:
        print("\n  TROCKENLAUF - nichts geaendert.")
        print("  Zum Schreiben: python scripts/25_bars_held_reparieren.py --schreiben")
        return 0

    sicherung = db.with_suffix(f".vor_bars_held_reparatur.sqlite")
    shutil.copy2(db, sicherung)
    print(f"\n  Sicherung: {sicherung}")

    with sqlite3.connect(db) as c:
        spalten = {r[1] for r in c.execute("PRAGMA table_info(trades)")}
        if "bars_held_quelle" not in spalten:
            c.execute("ALTER TABLE trades ADD COLUMN bars_held_quelle TEXT")
            # Alles Bestehende gilt zunaechst als gemessen; die reparierten
            # Zeilen werden gleich danach ueberschrieben.
            c.execute("UPDATE trades SET bars_held_quelle='gemessen'"
                      " WHERE bars_held IS NOT NULL")
        for _, r in falsch.iterrows():
            c.execute("UPDATE trades SET bars_held=?, bars_held_quelle='rekonstruiert'"
                      " WHERE rowid=?", (int(r["erwartet"]), int(r["rowid"])))
        c.commit()

    print(f"  {len(falsch)} Zeilen rekonstruiert, als 'rekonstruiert' markiert.")
    print("  Gegenprobe:")
    nach = analysieren(db)
    print(f"    verbleibende Widersprueche: {(nach['abweichung'] > TOLERANZ).sum()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
