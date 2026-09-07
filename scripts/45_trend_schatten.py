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

    print(f"[2/2] {len(trend_schatten.PHASE2_KANDIDATEN)} Strategien "
          f"durchrechnen und fortschreiben ...")
    erg = trend_schatten.aktualisieren(prices)

    print()
    print(f"  Stand {erg['stand']}  (Schatten seit {erg['start_datum']}, "
          f"{erg['tage_vorwaerts']} Kalendertage)")
    print()
    print(f"  {'Strategie':<22}{'Rendite':>10}{'Max-DD':>9}  Allokation jetzt")
    for name, snap in sorted(erg["kandidaten"].items(),
                             key=lambda x: -x[1].get("rendite_seit_start", -9)):
        if "fehler" in snap:
            print(f"  {name:<22}  {snap['fehler']}")
            continue
        alloc = " ".join(f"{s}{g*100:.0f}" for s, g in
                         sorted(snap["ziel_gewichte"].items(), key=lambda x: -x[1]))
        if snap["cash_anteil"] > 0.01:
            alloc += f" Cash{snap['cash_anteil']*100:.0f}"
        print(f"  {name:<22}{snap['rendite_seit_start']:>10.2%}"
              f"{snap['max_drawdown_seit_start']:>9.1%}  {alloc}")
    print()
    print("  Kein Live-Handel. Rennen laeuft bis Dez (TRENDBOT.md §6a).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
