#!/usr/bin/env python3
"""Schritt 27: Hypothesenkatalog 2027 im Register voranmelden.

Traegt alle Eintraege aus `alpaca_bot.hypothesen_2027.KATALOG` ueber
`hypotheses.erfassen()` in die Schattendatenbank ein - mit Zeitstempel VOR
jedem Test. Bereits erfasste IDs werden uebersprungen. Der Versuchszaehler
steigt je Hypothese; das ist Absicht (jede Hypothese hebt die
Signifikanzschwelle fuer alle).

    python scripts/27_hypothesen_anmelden.py            # nur anzeigen
    python scripts/27_hypothesen_anmelden.py --anmelden # in shadow.sqlite schreiben
    python scripts/27_hypothesen_anmelden.py --prio 1
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from alpaca_bot import hypothesen_2027 as kat  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--anmelden", action="store_true")
    p.add_argument("--prio", type=int, default=None)
    p.add_argument("--db", default=None, help="abweichende shadow.sqlite (Tests)")
    args = p.parse_args()

    eintraege = kat.nach_prio(args.prio)
    if not args.anmelden:
        print(kat.tabelle() if args.prio is None else
              "\n".join(f"{h['hyp_id']} [P{h['prio']}] {h['behauptung']}" for h in eintraege))
        print(f"\n  {len(eintraege)} Hypothesen. Mit --anmelden ins Register schreiben.")
        return 0

    from alpaca_bot import hypotheses
    from alpaca_bot.shadow import ShadowStore

    store = ShadowStore(Path(args.db)) if args.db else ShadowStore()
    n = 0
    for h in eintraege:
        msg = hypotheses.erfassen(
            h["hyp_id"], h["behauptung"], quelle=h["quelle"], quelle_typ=h["quelle_typ"],
            operationalisierung=h["operationalisierung"], veroeffentlicht=h.get("veroeffentlicht"),
            behaupteter_effekt=h["erwartung"], store=store,
        )
        n += "erfasst (" in msg
        print(f"  {msg}")
    print(f"\n  {n} neu angemeldet. Register: python scripts/17_shadow_report.py --hypothesen")
    return 0


if __name__ == "__main__":
    sys.exit(main())
