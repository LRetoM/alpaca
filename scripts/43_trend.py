#!/usr/bin/env python3
"""Trendbot-Historienlauf: Time-Series-Momentum / Dual-Momentum auf ETFs.

Der Strategie-Familien-Wechsel (`docs/TRENDBOT.md`). Reiner Offline-
Backtest auf Altdaten (yfinance, Total-Return), kein Handelsbot, kein
Versuchszaehlerplatz. Kosten fallen beidseitig auf den Turnover je
Rebalance an.

    python scripts/43_trend.py --vergleich --jahre 20
    python scripts/43_trend.py --strategie tsmom --lookback 12 --vol-ziel 0.10
    python scripts/43_trend.py --vergleich --walk-forward --universe broad
    python scripts/43_trend.py --strategie dualmom --kosten-check
"""

from __future__ import annotations

import argparse
import json
import sys

import numpy as np
import pandas as pd

from alpaca_bot import trend
from alpaca_bot.config import RESULTS_DIR


def lade_etf_historie(symbols: list[str], jahre: float,
                      verbose: bool = True) -> pd.DataFrame:
    """Total-Return-Schlusskurse je ETF, DataFrame Datum x Asset.

    `auto_adjust=True` rechnet Dividenden ein - bei Anleihen-ETFs ist die
    Ausschuettung der Grossteil der Rendite, ohne das waere der Vergleich
    verzerrt.
    """
    import yfinance as yf

    from alpaca_bot.ratelimit import RateLimiter

    RateLimiter("yfinance").acquire(len(symbols))
    start = (pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=int(jahre * 365))).date()
    roh = yf.download(symbols, start=str(start), auto_adjust=True,
                      progress=False, group_by="ticker", threads=True)
    if roh is None or roh.empty:
        return pd.DataFrame()
    spalten = {}
    for sym in symbols:
        try:
            sub = roh[sym] if len(symbols) > 1 else roh
            s = sub["Close"].dropna() if "Close" in sub else sub["close"].dropna()
        except (KeyError, TypeError):
            continue
        if len(s) > 200:
            spalten[sym] = s
        elif verbose:
            print(f"      {sym}: nur {len(s)} Tage - verworfen")
    if not spalten:
        return pd.DataFrame()
    df = pd.DataFrame(spalten)
    df.index = pd.to_datetime(df.index, utc=True)
    return df.sort_index()


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--universe", default="broad",
                   choices=sorted(trend.UNIVERSEN))
    p.add_argument("--jahre", type=float, default=20.0)
    p.add_argument("--split", default=None,
                   help="nur Zeitraum ab hier auswerten (Rest = Vorlauf)")
    p.add_argument("--strategie", default="tsmom",
                   choices=("tsmom", "dualmom", "ma_filter"))
    p.add_argument("--lookback", type=int, default=12)
    p.add_argument("--vol-ziel", dest="vol_ziel", type=float, default=0.10)
    p.add_argument("--top-n", dest="top_n", type=int, default=3)
    p.add_argument("--kosten", dest="kosten_bps", type=float, default=2.0)
    p.add_argument("--slippage", dest="slippage_bps", type=float, default=1.0)
    p.add_argument("--rebalance", default="monatlich",
                   choices=("monatlich", "woechentlich"))
    p.add_argument("--vergleich", action="store_true",
                   help="alle Strategien x Lookbacks x Vol-Ziele + Benchmarks")
    p.add_argument("--walk-forward", action="store_true")
    p.add_argument("--kosten-check", action="store_true",
                   help="Einzellauf zusaetzlich bei 0 / 4 / 8 bps echt neu rechnen")
    args = p.parse_args()

    syms = trend.UNIVERSEN[args.universe]
    print(f"[1/3] Lade {len(syms)} ETFs ({', '.join(syms)}), {args.jahre:g} Jahre "
          f"ueber yfinance ...")
    prices = lade_etf_historie(syms, args.jahre)
    if prices.empty or prices.shape[1] < 2:
        print("Zu wenig Daten.")
        return 1
    abdeckung = prices.notna().all(axis=1)
    voll_ab = prices.index[abdeckung][0] if abdeckung.any() else prices.index[0]
    print(f"      {prices.shape[0]} Tage x {prices.shape[1]} Assets, "
          f"{prices.index[0].date()} .. {prices.index[-1].date()}")
    print(f"      volle Abdeckung aller Assets ab {voll_ab.date()}")

    RESULTS_DIR.joinpath("trend").mkdir(parents=True, exist_ok=True)
    basis = trend.TrendConfig(
        strategie=args.strategie, lookback_monate=args.lookback,
        vol_ziel=args.vol_ziel, top_n=args.top_n, kosten_bps=args.kosten_bps,
        slippage_bps=args.slippage_bps, rebalance=args.rebalance)

    # ---------------- VERGLEICH ----------------
    if args.vergleich:
        print("[2/3] Vergleich: alle Strategien x Lookbacks x Vol-Ziele ...")
        tab = trend.vergleich(prices, basis=basis, start=args.split)
        n_var = len(tab)
        pd.set_option("display.width", 200)
        print("\n  RANGLISTE (nach Sharpe)")
        print(tab.to_string(index=False, float_format=lambda x: f"{x:.3f}"))

        # Benchmarks daneben
        ab = prices.index[prices.index >= (pd.Timestamp(args.split, tz=prices.index.tz)
                                           if args.split else prices.index[0])][0]
        bench = trend.benchmark_kurven(prices, 100_000.0, ab)
        print("\n  BENCHMARKS")
        for name, eq in bench.items():
            m = trend._kennz(eq)
            print(f"    {name:<14} CAGR {m.get('cagr', 0):>7.2%}  "
                  f"MaxDD {m.get('max_drawdown', 0):>7.1%}  "
                  f"Sharpe {m.get('sharpe', 0):>5.2f}")

        # bestes vollstaendig auswerten
        best = tab.iloc[0]
        print(f"\n[3/3] Beste Variante voll auswerten: {best['strategie']} "
              f"lookback {int(best['lookback'])} vol {best['vol_ziel']}")
        from dataclasses import replace
        cfg_best = replace(basis, strategie=best["strategie"],
                           lookback_monate=int(best["lookback"]),
                           vol_ziel=0.0 if best["vol_ziel"] == "aus" else 0.10)
        res = trend.run(prices, cfg_best, start=args.split)
        print()
        print(trend.auswerten(res, prices, n_varianten=n_var))

        if args.walk_forward:
            _wf(prices, cfg_best, args)

        _json("vergleich", {
            "universe": args.universe, "jahre": args.jahre,
            "tabelle": tab.to_dict("records"),
            "beste": {k: (v if not isinstance(v, float) else round(v, 4))
                      for k, v in best.to_dict().items()},
        })
        return 0

    # ---------------- EINZELLAUF ----------------
    print(f"[2/3] Einzellauf: {args.strategie}, lookback {args.lookback}, "
          f"vol-ziel {args.vol_ziel}")
    res = trend.run(prices, basis, start=args.split)
    print()
    print(trend.auswerten(res, prices, n_varianten=1))

    if args.kosten_check:
        print("\n  KOSTEN-CHECK - echte Neulaeufe:")
        from dataclasses import replace
        for kb in (0.0, 4.0, 8.0):
            r2 = trend.run(prices, replace(basis, kosten_bps=kb, slippage_bps=0.0),
                           start=args.split)
            m2 = r2.metrics()
            print(f"    {kb:>4.0f} bps  ->  CAGR {m2.get('cagr', 0):+.2%}  "
                  f"MaxDD {m2.get('max_drawdown', 0):.1%}  "
                  f"Sharpe {m2.get('sharpe', 0):.2f}")

    if args.walk_forward:
        _wf(prices, basis, args)

    _json("einzeln", {"config": vars(args), "metriken": res.metrics(),
                      "total_return": res.total_return})
    print("[3/3] fertig.")
    return 0


def _wf(prices, cfg, args) -> None:
    print("\n  WALK-FORWARD (Lookback-Auswahl je Jahr auf Vergangenheit)")
    wf = trend.walk_forward(prices, basis=cfg, start=args.split)
    for z in wf["zeilen"]:
        print(f"    {z['jahr']}: lookback {z['lookback']:>2}M -> "
              f"{z['strat_rendite']:+.1%}  (60/40 {z['b6040']:+.1%}, "
              f"Diff {z['diff']:+.1%})")
    print(f"    -> {wf['jahre_mit_vorsprung']}/{wf['n_jahre']} Jahre mit "
          f"Vorsprung, mittlere Diff {wf['mittel_diff']:+.1%}, t = {wf['t']:+.2f}")
    print("    Rueckwaerts ist kein Vorwaertstest - das darf verwerfen, nicht abnehmen.")


def _json(name: str, obj: dict) -> None:
    (RESULTS_DIR / "trend" / f"{name}.json").write_text(
        json.dumps(obj, indent=2, default=str), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
