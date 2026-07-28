#!/usr/bin/env python3
"""Schritt 5: Im Depot handeln - mit derselben Engine wie in der Simulation.

WICHTIG zum Stand der Dinge:

Dieses Skript pruefe die INFRASTRUKTUR - Datenabruf, Entscheidungspfad,
Risikoregeln, PDT-Pruefung, Orderausfuehrung, Protokollierung. Das ist
notwendig und sinnvoll.

Die STRATEGIE hat dagegen bislang keinen nachgewiesenen Vorsprung. Der
Historienlauf (scripts/10_simulate.py) lag deutlich hinter Buy & Hold,
und das Faktor-Labor (scripts/11_factor_lab.py) hat gezeigt, dass die
meisten Bausteine reine Beta-Stellvertreter sind.

Solange das so ist, gilt: Im Papierdepot laufen lassen, Protokoll
auswerten, Ausfuehrungsqualitaet messen - aber KEIN echtes Geld.

    python scripts/05_paper_trade.py                  # Vorschau, nichts wird gesendet
    python scripts/05_paper_trade.py --live           # Orders im Papierdepot senden
    python scripts/05_paper_trade.py --universe broad_liquid --max-new 3
"""

from __future__ import annotations

import argparse
import sys

from alpaca_bot import account, live, universe
from alpaca_bot.config import get_settings
from alpaca_bot.engine import EngineConfig


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--universe", default="broad_liquid",
                   choices=list(universe.BENCHMARK_SETS))
    p.add_argument("--symbols", nargs="*", default=None,
                   help="Eigene Liste statt eines Universums")
    p.add_argument("--positions", type=int, default=12,
                   help="Maximale Anzahl gleichzeitiger Positionen")
    p.add_argument("--max-new", type=int, default=3,
                   help="Maximal so viele Kaeufe je Lauf")
    p.add_argument("--min-score", type=float, default=0.55)
    p.add_argument("--live", action="store_true",
                   help="Orders wirklich senden (im Papierdepot)")
    args = p.parse_args()

    s = get_settings()
    dry = not args.live
    symbols = (
        [x.upper() for x in args.symbols]
        if args.symbols
        else universe.BENCHMARK_SETS[args.universe]
    )

    print("=" * 72)
    print(f"  {'VORSCHAU (keine Orders)' if dry else 'ORDERS WERDEN GESENDET'}"
          f"   |   Konto: {'PAPIER' if s.paper else 'LIVE - ECHTES GELD'}")
    print("=" * 72)

    if not s.paper and args.live:
        print("\n  Die Strategie hat keinen nachgewiesenen Vorsprung.")
        print("  Echtes Geld ist an dieser Stelle nicht vertretbar.")
        confirm = input("  Zum Fortfahren tippe 'ICH WEISS WAS ICH TUE': ")
        if confirm.strip() != "ICH WEISS WAS ICH TUE":
            print("  Abgebrochen.")
            return 1

    clock = account.market_clock()
    print(f"\n  Boerse: {'OFFEN' if clock['is_open'] else 'geschlossen'}"
          f"  |  naechste Oeffnung {clock['next_open']:%d.%m.%Y %H:%M %Z}")
    if not clock["is_open"]:
        print("  Market-Orders werden zur naechsten Eroeffnung ausgefuehrt.")

    print(f"\n  Universum: {len(symbols)} Symbole")
    print(f"  Engine   : max. {args.positions} Positionen, "
          f"Score-Schwelle {args.min_score}, max. {args.max_new} Kaeufe je Lauf")
    print()

    cfg = EngineConfig(max_positions=args.positions, min_score=args.min_score)
    try:
        result = live.run_once(
            symbols, cfg, dry_run=dry, max_new_positions=args.max_new
        )
    except Exception as e:  # noqa: BLE001
        print(f"\n  FEHLER: {type(e).__name__}: {e}")
        return 1

    print("\n" + "-" * 72)
    if dry:
        print("  Das war die Vorschau. Mit --live werden die Orders gesendet.")
    else:
        print(f"  {result.executed} Order(s) gesendet, {result.blocked} blockiert.")
    print(f"  Protokolliert. Auswertung: python scripts/07_journal_report.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
