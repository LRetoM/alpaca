#!/usr/bin/env python3
"""Schritt 5: Eine Strategie im Paper-Konto handeln lassen.

Laeuft einmal durch: Daten holen -> Signal berechnen -> Portfolio
angleichen. Fuer den taeglichen Betrieb per cron/launchd aufrufen.

WICHTIG: Ohne --live wird NICHTS gesendet, nur angezeigt.

    python scripts/05_paper_trade.py                        # Vorschau
    python scripts/05_paper_trade.py --live                 # wirklich handeln
    python scripts/05_paper_trade.py --symbols SPY QQQ --strategy trend_filtered
"""

from __future__ import annotations

import argparse
import sys

from alpaca_bot import account, data, strategies, trading
from alpaca_bot.config import get_settings


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--symbols", nargs="+", default=["SPY"])
    p.add_argument("--strategy", default="trend_filtered")
    p.add_argument("--allocation", type=float, default=0.20,
                   help="Anteil des Portfolios pro Signal (0.20 = 20 %%)")
    p.add_argument("--live", action="store_true",
                   help="Orders wirklich senden (im Paper-Konto)")
    args = p.parse_args()

    s = get_settings()
    dry = not args.live
    symbols = [x.upper() for x in args.symbols]

    print("=" * 70)
    print(f"  {'VORSCHAU (keine Orders)' if dry else 'ORDERS WERDEN GESENDET'}"
          f"  |  Konto: {'PAPER' if s.paper else 'LIVE - ECHTES GELD'}")
    print("=" * 70)

    if not s.paper and args.live:
        confirm = input("\nDu handelst mit ECHTEM GELD. Tippe 'JA ICH WILL': ")
        if confirm.strip() != "JA ICH WILL":
            print("Abgebrochen.")
            return 1

    clock = account.market_clock()
    if not clock["is_open"]:
        print(f"\nHinweis: Boerse geschlossen. Naechste Oeffnung: "
              f"{clock['next_open']:%d.%m.%Y %H:%M %Z}")
        print("Market-Orders werden dann zur Eroeffnung ausgefuehrt.\n")

    acct = account.account_summary()
    equity = acct["portfolio_value"]
    held = account.positions()
    print(f"\nKontowert: ${equity:,.2f} | Cash: ${acct['cash']:,.2f} "
          f"| Positionen: {len(held)}")

    strat = strategies.get(args.strategy)
    print(f"Strategie: {strat!r}\n")

    bars = data.get_bars(symbols, "1D", lookback_days=500)

    for sym in symbols:
        try:
            df = data.ohlcv(bars, sym)
        except KeyError:
            print(f"{sym:<6} keine Daten - uebersprungen")
            continue

        signal = strat.generate_signals(df)
        target = float(signal.iloc[-1])
        price = float(df["close"].iloc[-1])
        has_position = sym in held.index
        current_qty = float(held.loc[sym, "qty"]) if has_position else 0.0

        print(f"{sym:<6} Kurs ${price:>8.2f} | Signal: "
              f"{'LONG' if target > 0 else 'CASH'} | im Depot: {current_qty:g}")

        # --- Einstieg ---
        if target > 0 and not has_position:
            notional = round(equity * args.allocation * target, 2)
            try:
                order = trading.market_order(
                    sym, notional=notional, side="buy", dry_run=dry
                )
                print(f"       -> KAUF  {order}")
            except trading.RiskError as e:
                print(f"       -> blockiert: {e}")

        # --- Ausstieg ---
        elif target <= 0 and has_position:
            print(f"       -> VERKAUF {trading.close_position(sym, dry_run=dry)}")

        else:
            print("       -> keine Aenderung noetig")

    if dry:
        print("\n" + "-" * 70)
        print("Das war nur die Vorschau. Mit --live werden die Orders gesendet.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
