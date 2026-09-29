#!/usr/bin/env python3
"""Jahresbot-Historienlauf: einmal im Jahr auswaehlen, halten, rotieren.

Nutzeridee (04.09.2026): querschnittliche Aktienauswahl mit sehr wenigen
Trades pro Jahr - der Horizont, bei dem die gemessene Spanne (§G51, ~12 bps)
kaum noch zaehlt. Reiner Offline-Backtest, kein Handelsbot, kein
Versuchszaehlerplatz.

    python scripts/44_jahresbot.py --top-n 20 --signal momentum --jahre 12
    python scripts/44_jahresbot.py --vergleich --jahre 12
    python scripts/44_jahresbot.py --signal momentum_vola --walk-forward --kosten-check
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace

import numpy as np
import pandas as pd

from alpaca_bot import jahresbot, pit, universe
from alpaca_bot.config import RESULTS_DIR


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--max-symbols", type=int, default=600)
    p.add_argument("--jahre", type=float, default=12.0)
    p.add_argument("--quelle", choices=("alpaca", "yf"), default="alpaca",
                   help="alpaca = IEX-Cache (reicht kaum vor 2017); "
                        "yf = yfinance, ~20 Jahre (inoffiziell, weiter "
                        "survivorship-verzerrt, aber genug Jahresbeobachtungen)")
    p.add_argument("--no-cache", action="store_true")
    p.add_argument("--split", default=None)
    p.add_argument("--signal", default="momentum",
                   choices=("momentum", "tief_vola", "momentum_vola"))
    p.add_argument("--top-n", dest="top_n", type=int, default=20)
    p.add_argument("--lookback", type=int, default=12)
    p.add_argument("--rebalance-monat", dest="rebalance_monat", type=int, default=1)
    p.add_argument("--stop-pct", dest="stop_pct", type=float, default=0.25)
    p.add_argument("--kein-gewinner-laufen", action="store_true")
    p.add_argument("--kosten", dest="kosten_bps", type=float, default=12.0)
    p.add_argument("--slippage", dest="slippage_bps", type=float, default=3.0)
    p.add_argument("--vergleich", action="store_true")
    p.add_argument("--walk-forward", action="store_true")
    p.add_argument("--kosten-check", action="store_true")
    args = p.parse_args()

    syms = universe.load_universe(max_symbols=args.max_symbols)
    print(f"[1/3] Lade {len(syms)} Symbole + SPY, {args.jahre:g} Jahre "
          f"ueber {args.quelle} ...")
    ziel = sorted(set(syms) | {"SPY"})
    if args.quelle == "yf":
        bars = _lade_yf(ziel, args.jahre)
    else:
        bars = universe.fetch_history(ziel, years=args.jahre,
                                      verbose=len(syms) > 300,
                                      use_cache=not args.no_cache)
    if bars.empty:
        print("Keine Daten.")
        return 1
    n_sym = bars.index.get_level_values("symbol").nunique()
    print(f"      {len(bars):,} Bars, {n_sym} Symbole")

    print("[2/3] Pruefe die Merkmalsfunktion auf Zukunftslecks ...")
    probe_sym = bars.drop("SPY", level="symbol", errors="ignore") \
        .index.get_level_values("symbol")[0]
    probe = bars.xs(probe_sym, level="symbol").sort_index()
    audit = pit.audit_feature_function(
        lambda d: jahresbot._merkmale(d, jahresbot.JahresConfig(signal=args.signal)),
        probe, n_checks=5)
    print(f"      {audit}")
    if not audit.clean:
        print("      ABBRUCH: undichte Merkmale.")
        return 1

    basis = jahresbot.JahresConfig(
        signal=args.signal, top_n=args.top_n, lookback_monate=args.lookback,
        rebalance_monat=args.rebalance_monat, stop_pct=args.stop_pct,
        gewinner_laufen_lassen=not args.kein_gewinner_laufen,
        kosten_bps=args.kosten_bps, slippage_bps=args.slippage_bps)

    RESULTS_DIR.joinpath("jahresbot").mkdir(parents=True, exist_ok=True)

    if args.vergleich:
        print("[3/3] Vergleich: Signale x Top-N x Stop ...")
        zeilen = []
        kombis = [(sig, tn, st)
                  for sig in ("momentum", "tief_vola", "momentum_vola")
                  for tn in (10, 20, 40)
                  for st in (0.0, 0.25)]
        for sig, tn, st in kombis:
            cfg = replace(basis, signal=sig, top_n=tn, stop_pct=st)
            try:
                r = jahresbot.run(bars, cfg, start=args.split)
            except Exception as e:  # noqa: BLE001
                print(f"      {sig}/{tn}/{st}: {type(e).__name__}")
                continue
            m = r.metrics()
            zeilen.append({"signal": sig, "top_n": tn,
                           "stop": "aus" if st == 0 else f"-{st:.0%}",
                           "CAGR": m.get("cagr", float("nan")),
                           "MaxDD": m.get("max_drawdown", float("nan")),
                           "Sharpe": m.get("sharpe", float("nan")),
                           "TO_pa": m.get("trades_pro_jahr", float("nan"))})
        tab = pd.DataFrame(zeilen).sort_values("Sharpe", ascending=False)
        print("\n  RANGLISTE (nach Sharpe)")
        print(tab.to_string(index=False, float_format=lambda x: f"{x:.3f}"))
        best = tab.iloc[0]
        cfg_b = replace(basis, signal=best["signal"], top_n=int(best["top_n"]),
                        stop_pct=0.0 if best["stop"] == "aus" else 0.25)
        r = jahresbot.run(bars, cfg_b, start=args.split)
        print()
        print(jahresbot.auswerten(r, bars, n_varianten=len(zeilen)))
        if args.walk_forward:
            _wf(bars, cfg_b, args)
        _json("vergleich", {"tabelle": zeilen})
        return 0

    print(f"[3/3] Einzellauf: {args.signal}, Top {args.top_n}")
    r = jahresbot.run(bars, basis, start=args.split, verbose=True)
    print()
    print(jahresbot.auswerten(r, bars, n_varianten=1))

    if args.kosten_check:
        print("\n  KOSTEN-CHECK - echte Neulaeufe:")
        for kb in (0.0, 6.0, 25.0):
            r2 = jahresbot.run(bars, replace(basis, kosten_bps=kb, slippage_bps=0.0),
                               start=args.split)
            m2 = r2.metrics()
            print(f"    {kb:>4.0f} bps  ->  CAGR {m2.get('cagr', 0):+.2%}  "
                  f"MaxDD {m2.get('max_drawdown', 0):.1%}")

    if args.walk_forward:
        _wf(bars, basis, args)

    _json("einzeln", {"config": vars(args), "metriken": r.metrics(),
                      "total_return": r.total_return})
    print("[3/3] fertig.")
    return 0


def _lade_yf(symbols: list[str], jahre: float) -> pd.DataFrame:
    """OHLCV je Symbol via yfinance, MultiIndex (symbol, timestamp),
    split-/dividendenbereinigt. In Baendern, damit ein grosser Abruf nicht
    in Zeitueberschreitungen laeuft."""
    import yfinance as yf

    from alpaca_bot.ratelimit import RateLimiter

    lim = RateLimiter("yfinance")
    start = (pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=int(jahre * 365))).date()
    teile = []
    schritt = 40  # unter dem yfinance-Minutenlimit, damit ein Batch in ein Fenster passt
    for i in range(0, len(symbols), schritt):
        chunk = symbols[i:i + schritt]
        lim.acquire(len(chunk))
        roh = yf.download(chunk, start=str(start), auto_adjust=True,
                          group_by="ticker", progress=False, threads=True)
        if roh is None or roh.empty:
            continue
        for sym in chunk:
            try:
                sub = roh[sym] if len(chunk) > 1 else roh
                sub = sub.rename(columns=str.lower)[
                    ["open", "high", "low", "close", "volume"]].dropna()
            except (KeyError, TypeError):
                continue
            if len(sub) < 260:
                continue
            sub.index = pd.to_datetime(sub.index, utc=True)
            sub["symbol"] = sym
            teile.append(sub.set_index("symbol", append=True).reorder_levels([1, 0]))
        print(f"      yfinance {min(i + schritt, len(symbols))}/{len(symbols)}",
              flush=True)
    if not teile:
        return pd.DataFrame()
    out = pd.concat(teile).sort_index()
    out.index = out.index.set_names(["symbol", "timestamp"])
    return out


def _wf(bars, cfg, args) -> None:
    print("\n  WALK-FORWARD (Auswahlregel fix, Jahr fuer Jahr gegen SPY)")
    wf = jahresbot.walk_forward(bars, cfg, start=args.split)
    for z in wf["zeilen"]:
        print(f"    {z['jahr']}: Bot {z['bot']:+.1%}  SPY {z['spy']:+.1%}  "
              f"Diff {z['diff']:+.1%}")
    print(f"    -> {wf['jahre_mit_vorsprung']}/{wf['n_jahre']} Jahre mit "
          f"Vorsprung, mittlere Diff {wf['mittel_diff']:+.1%}, t = {wf['t']:+.2f}")


def _json(name, obj) -> None:
    (RESULTS_DIR / "jahresbot" / f"{name}.json").write_text(
        json.dumps(obj, indent=2, default=str), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
