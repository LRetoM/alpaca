#!/usr/bin/env python3
"""Schritt 33: Kandidatenregister - die Zwischenstufe vor dem Schatten.

Verwaltet `alpaca_bot.kandidatenregister` von der Kommandozeile aus. Siehe
`docs/UMBAUPLAN.md` Schritt 5/6 fuer den Vertrag, dem dieses Register folgt.

    python scripts/33_kandidaten.py                         # Liste (Standard)
    python scripts/33_kandidaten.py --anmelden K01_min_score_045 \\
        --achse min_score --wert 0.45 --varianten 14 \\
        --hypothese "Historienlauf: t=+2.1 ueber 12 Jahresscheiben"
    python scripts/33_kandidaten.py --status K01_min_score_045 im_schatten
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from alpaca_bot import kandidatenregister as kr  # noqa: E402
from alpaca_bot.config import code_version  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--anmelden", metavar="KANDIDAT_ID",
                    help="Meldet einen neuen Kandidaten an")
    ap.add_argument("--achse")
    ap.add_argument("--wert")
    ap.add_argument("--hypothese")
    ap.add_argument("--varianten", type=int,
                    help="n_varianten_getestet - Pflicht bei --anmelden")
    ap.add_argument("--status", nargs=2, metavar=("KANDIDAT_ID", "STATUS"),
                    help=f"Status setzen. Erlaubt: {sorted(kr.STATUS)}")
    args = ap.parse_args()

    if args.anmelden:
        fehlt = [n for n, v in [("--achse", args.achse), ("--wert", args.wert),
                                ("--hypothese", args.hypothese),
                                ("--varianten", args.varianten)] if v is None]
        if fehlt:
            ap.error(f"--anmelden braucht zusaetzlich: {', '.join(fehlt)}")
        print(kr.anmelden(args.anmelden, achse=args.achse, wert=args.wert,
                          hypothese=args.hypothese,
                          n_varianten_getestet=args.varianten,
                          code_version=code_version()))
        return 0

    if args.status:
        kid, status = args.status
        print(kr.status_setzen(kid, status))
        return 0

    print(kr.bericht())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
