#!/usr/bin/env python3
"""Schritt 20: Forschungspanels bauen - einmal, dann aus dem Cache.

Baut breite Kursmatrizen (Tage x Symbole) fuer das Labor 2027 und legt sie
unter data/labor/<name>/ ab. Danach laufen alle 21_-26_-Skripte ohne
erneutes Laden.

Quellen (siehe labor.py):

    projekt     der Projektcache auf DEINEM Mac:
                data/cache/bars/yfinance_2168_*_8y.parquet
                -> das ist die Hauptquelle fuer alle echten Messungen
    qlib        Qlib-US-Sammlung (8.994 Symbole, OHLCV, 2000 - 11/2020),
                frei ueber GitHub-Releases; Ersatz, wenn Yahoo gesperrt ist
    data_stock  S&P-500-Schlusskurse 2016 - 2026 (nur Close, survivorship)
    lean        SPY/QQQ/IWM OHLCV 1998 - 03/2021 (Beispieldaten QuantConnect)
    csv         ein CSV je Symbol (Kaggle/yfinance-Stil)

Beispiele:
    python scripts/20_labor_daten.py --quelle projekt --pfad data/cache/bars/yfinance_2168_XXXX_8y.parquet --name projekt
    python scripts/20_labor_daten.py --quelle qlib --pfad data/extern/qlib_us --name qlib --start 2005-01-01
    python scripts/20_labor_daten.py --quelle data_stock --pfad data/extern/Actual_Stock.parquet --name sp500_close
    python scripts/20_labor_daten.py --quelle csv --pfad data/extern/lean --name lean
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from alpaca_bot import labor  # noqa: E402
from alpaca_bot.config import PROJECT_ROOT  # noqa: E402

LABOR_DIR = PROJECT_ROOT / "data" / "labor"


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--quelle", required=True,
                   choices=["projekt", "parquet", "qlib", "data_stock", "csv"])
    p.add_argument("--pfad", required=True)
    p.add_argument("--name", required=True, help="Cache-Name unter data/labor/")
    p.add_argument("--start", default="2005-01-01", help="nur qlib: fruehester Tag")
    p.add_argument("--min-tage", type=int, default=250)
    args = p.parse_args()

    t0 = time.time()
    if args.quelle == "qlib":
        panel = labor.panel_aus_qlib(args.pfad, start=args.start, min_tage=args.min_tage)
    elif args.quelle == "csv":
        panel = labor.panel_aus_csv_verzeichnis(args.pfad)
    else:
        panel = labor.panel_laden(args.quelle, args.pfad)

    panel = labor.panel_bereinigen(panel)
    ziel = LABOR_DIR / args.name
    labor.panel_speichern(panel, ziel)
    print(f"  {panel.beschreibung()}")
    print(f"  gespeichert unter {ziel}  ({time.time() - t0:.0f} s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
