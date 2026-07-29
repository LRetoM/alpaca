#!/usr/bin/env python3
"""Einmalige Bereinigung des Protokolls nach den Messfehlern vom 28.07.2026.

Zwei Altlasten werden entfernt:

  1. **Testdaten** (Symbol TEST) aus Entwicklungslaeufen, die in dieselbe
     Produktionsdatenbank geschrieben wurden.

  2. **Falsch berechnete Slippage.** Bis zur Korrektur wurde als
     Bezugspreis der Schlusskurs des Vortages gespeichert - also der Kurs,
     auf dem die ENTSCHEIDUNG beruhte, nicht der Marktkurs im Moment der
     Order. Die daraus berechneten Werte (bis -2452 Basispunkte) messen
     die Kursbewegung ueber Nacht, nicht die Ausfuehrungsqualitaet.

     Diese Werte werden nicht korrigiert, sondern als unmessbar markiert:
     Der echte Referenzkurs von damals laesst sich nachtraeglich nicht
     rekonstruieren. Der gespeicherte Wert wandert dorthin, wo er
     hingehoert - nach `decision_price` - und `slippage_bps` wird geleert.
     Eine falsche Zahl zu behalten waere schlimmer als gar keine.

Vor dem Loeschen wird eine Sicherungskopie angelegt.

    python scripts/14_journal_bereinigen.py --vorschau
    python scripts/14_journal_bereinigen.py --ausfuehren
"""

from __future__ import annotations

import argparse
import shutil
import sys
from datetime import datetime

from alpaca_bot.journal import JOURNAL_DB, Journal


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--ausfuehren", action="store_true",
                   help="Ohne diesen Schalter passiert nichts")
    args = p.parse_args()

    if not JOURNAL_DB.exists():
        print("Kein Protokoll vorhanden - nichts zu tun.")
        return 0

    j = Journal()
    with j._conn() as c:
        n_test_orders = c.execute(
            "SELECT COUNT(*) FROM orders WHERE symbol='TEST'").fetchone()[0]
        n_test_dec = c.execute(
            "SELECT COUNT(*) FROM decisions WHERE symbol='TEST'").fetchone()[0]
        n_bad_slip = c.execute(
            "SELECT COUNT(*) FROM orders WHERE dry_run=0 AND symbol!='TEST'"
            " AND slippage_bps IS NOT NULL AND decision_price IS NULL"
        ).fetchone()[0]

    print("=" * 70)
    print("  PROTOKOLL-BEREINIGUNG")
    print("=" * 70)
    print(f"  Testdaten (Symbol TEST)      : {n_test_orders} Orders, "
          f"{n_test_dec} Entscheidungen")
    print(f"  Orders mit falscher Slippage : {n_bad_slip}")
    print()

    if not args.ausfuehren:
        print("  VORSCHAU - es wurde nichts geaendert.")
        print("  Zum Ausfuehren: python scripts/14_journal_bereinigen.py --ausfuehren")
        return 0

    backup = JOURNAL_DB.with_name(
        f"journal_vor_bereinigung_{datetime.now():%Y%m%d_%H%M%S}.sqlite")
    shutil.copy2(JOURNAL_DB, backup)
    print(f"  Sicherungskopie: {backup.name}")

    with j._conn() as c:
        # 1. Testdaten entfernen - Reihenfolge wegen der Verknuepfungen
        c.execute("DELETE FROM outcomes WHERE decision_id IN"
                  " (SELECT decision_id FROM decisions WHERE symbol='TEST')")
        c.execute("DELETE FROM orders WHERE symbol='TEST'")
        c.execute("DELETE FROM decisions WHERE symbol='TEST'")
        c.execute("DELETE FROM runs WHERE run_id NOT IN"
                  " (SELECT DISTINCT run_id FROM decisions)"
                  " AND script NOT IN ('live_trade','simulate')")

        # 2. Falsche Slippage richtigstellen: Der gespeicherte Bezugspreis
        #    war der Entscheidungskurs - dorthin gehoert er auch.
        c.execute(
            "UPDATE orders SET decision_price = expected_price,"
            " decision_drift_bps = slippage_bps,"
            " expected_price = NULL, slippage_bps = NULL"
            " WHERE dry_run=0 AND decision_price IS NULL"
            " AND slippage_bps IS NOT NULL"
        )

    with j._conn() as c:
        rest_test = c.execute(
            "SELECT COUNT(*) FROM orders WHERE symbol='TEST'").fetchone()[0]
        rest_slip = c.execute(
            "SELECT COUNT(*) FROM orders WHERE slippage_bps IS NOT NULL"
        ).fetchone()[0]
        echte = c.execute(
            "SELECT COUNT(*) FROM orders WHERE dry_run=0").fetchone()[0]

    print()
    print(f"  Testdaten verbleibend        : {rest_test}")
    print(f"  Echte Orders erhalten        : {echte}")
    print(f"  Orders mit Slippage-Wert     : {rest_slip}"
          "  (0 ist richtig - ab jetzt wird sie korrekt gemessen)")
    print()
    print("  Fertig. Die Kursdrift der Altorders bleibt unter")
    print("  'decision_drift_bps' erhalten und ist weiterhin auswertbar.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
