#!/usr/bin/env python3
"""Schritt 1: Pruefen, ob Keys, Konto und Marktdaten funktionieren.

    python scripts/01_check_setup.py
"""

from __future__ import annotations

import sys

from alpaca_bot import account, data
from alpaca_bot.config import ConfigError, get_settings


def main() -> int:
    print("=" * 62)
    print("  ALPACA SETUP-CHECK")
    print("=" * 62)

    # --- 1. Konfiguration -------------------------------------------------
    try:
        s = get_settings()
    except ConfigError as e:
        print(f"\n[FEHLER] {e}")
        return 1

    modus = "PAPER (Spielgeld)" if s.paper else "!!! LIVE (echtes Geld) !!!"
    print(f"\n[1/4] Konfiguration")
    print(f"      Modus       : {modus}")
    print(f"      API-Key     : {s.api_key[:6]}...{s.api_key[-3:]}")
    print(f"      Datenfeed   : {s.data_feed}")
    print(f"      Max/Position: {s.max_position_pct:.0%} | Max/Order: ${s.max_order_notional:,.0f}")

    # --- 2. Konto ---------------------------------------------------------
    print(f"\n[2/4] Verbindung zum Konto")
    try:
        a = account.account_summary()
    except Exception as e:
        print(f"      [FEHLER] {type(e).__name__}: {e}")
        print("      -> Keys falsch, oder Live-Keys mit ALPACA_PAPER=true gemischt?")
        return 1
    print(f"      Konto-Nr.   : {a['account_number']}  ({a['status']})")
    print(f"      Kontowert   : ${a['portfolio_value']:>12,.2f}")
    print(f"      Cash        : ${a['cash']:>12,.2f}")
    print(f"      Kaufkraft   : ${a['buying_power']:>12,.2f}")
    print(f"      Shorts      : {'erlaubt' if a['shorting_enabled'] else 'gesperrt'}")

    # --- 3. Marktstatus ---------------------------------------------------
    print(f"\n[3/4] Marktstatus")
    clock = account.market_clock()
    print(f"      Boerse ist  : {'OFFEN' if clock['is_open'] else 'geschlossen'}")
    print(f"      Naechste Oeffnung : {clock['next_open']:%d.%m.%Y %H:%M %Z}")

    # --- 4. Marktdaten ----------------------------------------------------
    print(f"\n[4/4] Marktdaten")
    try:
        bars = data.get_bars(["AAPL", "MSFT", "SPY"], "1D", lookback_days=30)
        print(f"      Tages-Bars  : {len(bars)} Zeilen fuer 3 Symbole geladen")
        snap = data.snapshots(["AAPL", "SPY"])
        for sym, row in snap.iterrows():
            chg = f"{row['change_pct']:+.2f}%" if row["change_pct"] is not None else "n/a"
            print(f"      {sym:<5}: {row['last']:>8.2f} USD  ({chg})")
    except Exception as e:
        print(f"      [FEHLER] {type(e).__name__}: {e}")
        return 1

    # --- Positionen -------------------------------------------------------
    pos = account.positions()
    print(f"\n      Offene Positionen: {len(pos)}")
    if not pos.empty:
        print(pos.to_string())

    print("\n" + "=" * 62)
    print("  ALLES OK - du kannst loslegen.")
    print("  Naechster Schritt: python scripts/02_market_overview.py")
    print("=" * 62)
    return 0


if __name__ == "__main__":
    sys.exit(main())
