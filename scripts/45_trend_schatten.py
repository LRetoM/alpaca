#!/usr/bin/env python3
"""Taeglicher Vorwaerts-Schatten der defensiven ETF-Allokation (Trendbot Phase 2).

Zieht die aktuellen ETF-Tageskurse von Alpaca (split-/dividendenbereinigt =
Total Return), rechnet die festgeschriebene Konfiguration
(`trend_schatten.PHASE2_CONFIG`) durch und schreibt Equity + Zielgewichte
nach `trend_schatten.sqlite` fort. **Sendet keine Orders.**

    python scripts/45_trend_schatten.py            # einmal aktualisieren
    python scripts/45_trend_schatten.py --bericht  # nur Stand ansehen

Gedacht als LaunchAgent `de.local.alpacatrend`, werktags nach US-Schluss.
"""

from __future__ import annotations

import argparse
import sys

import pandas as pd
from alpaca.data.enums import Adjustment

from alpaca_bot import data, trend, trend_schatten


def _preise(symbols: list[str], lookback_days: int = 3200) -> pd.DataFrame:
    """Total-Return-Schlusskurse je ETF von Alpaca, DataFrame Datum x Asset."""
    spalten = {}
    for sym in symbols:
        try:
            b = data.get_bars(sym, "1D", lookback_days=lookback_days,
                              adjustment=Adjustment.ALL, use_cache=False)
        except Exception as e:  # noqa: BLE001
            print(f"  {sym}: {type(e).__name__}: {e}")
            continue
        if b.empty:
            continue
        s = b.xs(sym, level="symbol")["close"].dropna()
        if len(s) > 200:
            spalten[sym] = s
    if not spalten:
        return pd.DataFrame()
    return pd.DataFrame(spalten).sort_index()


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--bericht", action="store_true", help="nur Stand ansehen")
    args = p.parse_args()

    if args.bericht:
        print(trend_schatten.bericht())
        return 0

    syms = trend.UNIVERSEN["broad"]
    print(f"[1/2] Lade {len(syms)} ETFs von Alpaca (Total Return) ...")
    prices = _preise(syms)
    if prices.empty or prices.shape[1] < 3:
        print("  Zu wenig Daten - Schatten nicht aktualisiert.")
        return 1
    print(f"      {prices.shape[1]} ETFs, {prices.index[0].date()} .. "
          f"{prices.index[-1].date()} ({len(prices)} Tage)")

    print("[2/2] Konfiguration durchrechnen und fortschreiben ...")
    erg = trend_schatten.aktualisieren(prices)
    if "fehler" in erg:
        print(f"  {erg['fehler']}")
        return 1

    print()
    print(f"  Stand {erg['stand']}  (Schatten seit {erg['start_datum']})")
    print(f"  Simulierte Equity     ${erg['equity']:>12,.0f}")
    print(f"  Rendite seit Start    {erg['rendite_seit_start']:>12.2%}")
    print(f"  Max Drawdown          {erg['max_drawdown_seit_start']:>12.1%}")
    print(f"  {erg['n_equity_punkte']} Equity-Punkte gespeichert")
    print()
    print("  Zielallokation JETZT:")
    for sym, g in sorted(erg["ziel_gewichte"].items(), key=lambda x: -x[1]):
        print(f"    {sym:<6} {g:>7.1%}")
    print(f"    {'Cash':<6} {erg['cash_anteil']:>7.1%}")
    print()
    print("  Kein Live-Handel. Entscheidung folgt in TRENDBOT.md Phase 3.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
