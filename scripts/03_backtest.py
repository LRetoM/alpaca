#!/usr/bin/env python3
"""Schritt 3: Strategien auf historischen Daten testen.

    python scripts/03_backtest.py                    # SPY, alle Strategien
    python scripts/03_backtest.py AAPL --years 8
    python scripts/03_backtest.py QQQ --strategy trend_filtered --plot
"""

from __future__ import annotations

import argparse
import sys

import pandas as pd

from alpaca_bot import backtest as bt
from alpaca_bot import data, strategies
from alpaca_bot.config import RESULTS_DIR


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("symbol", nargs="?", default="SPY")
    p.add_argument("--years", type=float, default=5.0)
    p.add_argument("--strategy", default="all", help="Name oder 'all'")
    p.add_argument("--cash", type=float, default=100_000)
    p.add_argument("--slippage", type=float, default=3.0, help="Basispunkte")
    p.add_argument("--plot", action="store_true")
    args = p.parse_args()

    sym = args.symbol.upper()
    print(f"Lade {sym} ({args.years} Jahre Tagesdaten) ...")
    bars = data.get_bars(sym, "1D", lookback_days=int(args.years * 365))
    if bars.empty:
        print("Keine Daten erhalten.")
        return 1
    df = data.ohlcv(bars, sym)
    print(f"  {len(df)} Handelstage: {df.index[0]:%d.%m.%Y} bis {df.index[-1]:%d.%m.%Y}\n")

    names = list(strategies.REGISTRY) if args.strategy == "all" else [args.strategy]
    results, overview = {}, []

    for name in names:
        strat = strategies.get(name)
        signal = strat.generate_signals(df)
        res = bt.backtest(
            df["close"], signal, slippage_bps=args.slippage, initial_cash=args.cash
        )
        results[name] = res
        m = res.metrics
        overview.append(
            {
                "Strategie": name,
                "Rendite %": round(m["total_return"] * 100, 1),
                "p.a. %": round(m["cagr"] * 100, 1),
                "Sharpe": round(m["sharpe"], 2),
                "MaxDD %": round(m["max_drawdown"] * 100, 1),
                "Trades": m["n_trades"],
                "Exposure %": round(m["exposure"] * 100, 0),
                "Endwert $": round(m["final_equity"]),
            }
        )

    table = pd.DataFrame(overview).sort_values("Sharpe", ascending=False)
    print("=" * 90)
    print(f"  BACKTEST-VERGLEICH  {sym}   (Slippage {args.slippage} bps)")
    print("=" * 90)
    print(table.to_string(index=False))

    best = table.iloc[0]["Strategie"]
    print(f"\n--- Detail: {best} (beste Sharpe Ratio) ---")
    print(results[best].summary())

    print("\nSo liest du die Tabelle:")
    print("  Sharpe > 1.0  : ordentlich | > 1.5 : gut | > 2.0 : bei Tagesdaten verdaechtig")
    print("  MaxDD         : den musst du real aussitzen koennen, nicht nur in Excel")
    print("  Trades        : viele Trades = Kosten und Steuern fressen die Rendite")
    print("  Vergleiche IMMER mit Buy & Hold - sonst ist die Zahl bedeutungslos.")

    if args.plot:
        for name, res in results.items():
            path = RESULTS_DIR / f"backtest_{sym}_{name}.png"
            bt.plot(res, f"{sym} - {name}", save_path=path)
        print(f"\nCharts gespeichert in {RESULTS_DIR}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
