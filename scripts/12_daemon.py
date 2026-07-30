#!/usr/bin/env python3
"""Schritt 12: Autonomer Dauerbetrieb.

Der Bot entscheidet selbstaendig, solange er laeuft. Stirbt der Prozess,
startet ihn der Systemdienst neu (scripts/install_service.sh). Nach dem
Neustart holt er den aktuellen Stand von Alpaca plus die gespeicherten
Positionsmarken und macht weiter.

STAND DER STRATEGIE: Die Umkehr-Strategie hat einen gemessenen, ueber
9 Jahre stabilen Vorsprung (IC ~0.017, +0.11 % je Trade) - aber die
Simulation zeigt, dass die Kosten ihn bei diesem Umschlag aufzehren.
Deshalb ist `--dry-run` Standard und `--live` nur fuer das Papierdepot
gedacht: Es geht darum, Ausfuehrungsqualitaet und Betriebsstabilitaet zu
messen, nicht darum, Geld zu verdienen.

    python scripts/12_daemon.py                    # Vorschau, nichts wird gesendet
    python scripts/12_daemon.py --live             # Orders im Papierdepot
    python scripts/12_daemon.py --status           # Zustand ansehen, nicht starten
    python scripts/12_daemon.py --once             # nur ein Durchgang
"""

from __future__ import annotations

import argparse
import sys

from alpaca_bot import universe
from alpaca_bot.config import get_settings
from alpaca_bot.daemon import Daemon, DaemonConfig
from alpaca_bot.engine import EngineConfig
from alpaca_bot.state import Store


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--universe", default="gemessen",
                   help="'gemessen' = die 2.100+ Werte aus dem Faktor-Labor "
                        "(dort wurde die Strategie validiert), sonst eine "
                        f"feste Liste: {', '.join(universe.BENCHMARK_SETS)}")
    p.add_argument("--max-symbols", type=int, default=1200,
                   help="Obergrenze beim gemessenen Universum (Laufzeit je Durchgang)")
    p.add_argument("--symbols", nargs="*", default=None)
    p.add_argument("--live", action="store_true",
                   help="Orders wirklich senden (im Papierdepot)")
    p.add_argument("--once", action="store_true", help="Nur ein Durchgang")
    p.add_argument("--status", action="store_true", help="Nur Zustand anzeigen")
    p.add_argument("--interval", type=int, default=900,
                   help="Sekunden zwischen Laeufen waehrend der Handelszeit")
    p.add_argument("--positions", type=int, default=15)
    p.add_argument("--max-new", type=int, default=3)
    p.add_argument("--strategy", default="reversal", choices=["reversal", "momentum"])
    p.add_argument("--voll-investiert", action="store_true",
                   help="Verteilt das freie Kapital so, dass der Zielanteil "
                        "(target_invested, 90 %%) tatsaechlich erreicht wird. "
                        "Ohne diesen Schalter wirkt die Volatilitaets-"
                        "Skalierung absolut und laesst bei volatilen "
                        "Umkehr-Kandidaten Kapital ungenutzt (gemessen: "
                        "53,9 %% statt 90 %% bei vollen 15 Positionen). "
                        "ACHTUNG: verstaerkt Gewinne UND Verluste.")
    args = p.parse_args()

    if args.status:
        print(Store().status_text())
        return 0

    s = get_settings()
    if args.live and not s.paper:
        print("  Dieses Skript ist fuer das Papierdepot gedacht.")
        print("  Die Strategie hat keinen kostentragfaehigen Vorsprung -")
        print("  echtes Geld waere hier nicht vertretbar.")
        return 1

    if args.symbols:
        symbols = [x.upper() for x in args.symbols]
    elif args.universe == "gemessen":
        try:
            symbols = universe.load_universe(max_symbols=args.max_symbols)
        except FileNotFoundError as e:
            print(f"  {e}")
            return 1
    else:
        symbols = universe.BENCHMARK_SETS[args.universe]

    engine = (
        EngineConfig.for_reversal(max_positions=args.positions,
                                  deploy_to_target=args.voll_investiert)
        if args.strategy == "reversal"
        else EngineConfig(max_positions=args.positions,
                          deploy_to_target=args.voll_investiert)
    )

    cfg = DaemonConfig(
        symbols=symbols,
        dry_run=not args.live,
        interval_seconds=args.interval,
        max_new_positions=args.max_new,
        engine=engine,
    )

    daemon = Daemon(cfg)
    if args.once:
        print("  Einzelner Durchgang:\n")
        state = daemon.recover()
        for k, v in state.items():
            print(f"    {k:<26} {v}")
        print()
        ok = daemon.step()
        print()
        print(Store().status_text())
        return 0 if ok else 1

    return daemon.run_forever()


if __name__ == "__main__":
    sys.exit(main())
