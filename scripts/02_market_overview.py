#!/usr/bin/env python3
"""Schritt 2: Taeglicher Marktueberblick.

Zeigt fuer eine Watchlist: aktuelle Kurse, Trendlage, RSI, Volatilitaet
und die Korrelation der Werte untereinander.

    python scripts/02_market_overview.py
    python scripts/02_market_overview.py NVDA AMD TSLA
"""

from __future__ import annotations

import sys

import pandas as pd

from alpaca_bot import data, indicators as ind
from alpaca_bot.account import account_summary, market_clock, positions

WATCHLIST = ["SPY", "QQQ", "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA"]


def trend_label(row) -> str:
    if pd.isna(row["sma_200"]):
        return "zu wenig Daten"
    if row["close"] > row["sma_50"] > row["sma_200"]:
        return "Aufwaerts (stark)"
    if row["close"] > row["sma_200"]:
        return "Aufwaerts"
    if row["close"] < row["sma_50"] < row["sma_200"]:
        return "Abwaerts (stark)"
    return "Abwaerts"


def main(symbols: list[str]) -> int:
    pd.set_option("display.width", 200)

    clock = market_clock()
    acct = account_summary()
    print("=" * 78)
    print(f"  MARKTUEBERBLICK  |  Boerse: {'OFFEN' if clock['is_open'] else 'geschlossen'}"
          f"  |  Konto: ${acct['portfolio_value']:,.2f}")
    print("=" * 78)

    bars = data.get_bars(symbols, "1D", lookback_days=400)
    if bars.empty:
        print("Keine Daten erhalten.")
        return 1

    rows = []
    for sym in symbols:
        try:
            df = ind.add_all(data.ohlcv(bars, sym))
        except KeyError:
            continue
        last = df.iloc[-1]
        rows.append(
            {
                "Symbol": sym,
                "Kurs": round(last["close"], 2),
                "1T %": round(last["ret_1"] * 100, 2),
                "5T %": round((last["close"] / df["close"].iloc[-6] - 1) * 100, 2),
                "1M %": round((last["close"] / df["close"].iloc[-22] - 1) * 100, 2),
                "RSI": round(last["rsi_14"], 1),
                "vs SMA200 %": round(last["dist_sma200"] * 100, 1),
                "Vola p.a. %": round(last["vol_20"] * 100, 1),
                "ATR %": round(last["atr_pct"] * 100, 2),
                "Trend": trend_label(last),
            }
        )

    table = pd.DataFrame(rows).set_index("Symbol")
    print("\n" + table.to_string())

    print("\n--- Auffaelligkeiten ---")
    overbought = table[table["RSI"] > 70]
    oversold = table[table["RSI"] < 30]
    if not overbought.empty:
        print(f"  Ueberkauft (RSI>70): {', '.join(overbought.index)}")
    if not oversold.empty:
        print(f"  Ueberverkauft (RSI<30): {', '.join(oversold.index)}")
    strong = table[table["Trend"] == "Aufwaerts (stark)"]
    if not strong.empty:
        print(f"  Intakter Aufwaertstrend: {', '.join(strong.index)}")
    weak = table[table["Trend"].str.startswith("Abwaerts")]
    if not weak.empty:
        print(f"  Unter dem 200-Tage-Schnitt: {', '.join(weak.index)}")

    # Korrelation: zeigt, ob eine Watchlist wirklich diversifiziert ist.
    closes = data.close_matrix(bars).pct_change().dropna()
    if len(closes.columns) > 1:
        print("\n--- Korrelation der Tagesrenditen (letzte 400 Tage) ---")
        print((closes.corr().round(2)).to_string())
        print("\n  Hinweis: Werte > 0.8 bedeuten, dass diese Positionen im Crash")
        print("  gemeinsam fallen - das ist keine Diversifikation.")

    pos = positions()
    if not pos.empty:
        print("\n--- Deine Positionen ---")
        print(pos.to_string())

    return 0


if __name__ == "__main__":
    args = sys.argv[1:]
    sys.exit(main([s.upper() for s in args] if args else WATCHLIST))
