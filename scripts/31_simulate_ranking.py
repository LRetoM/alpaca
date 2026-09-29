#!/usr/bin/env python3
"""Schritt 31: Die Strategie 'ranking' durch die ECHTE Engine schicken.

scripts/22 misst vektorisiert und schnell. Aber gehandelt wird, was
`Engine.decide()` tut - mit Positionsgroessen, Stops, Mindesthaltedauer,
Sperrfristen, Kurslücken und den Kosten aus costs.py (Spread, Slippage,
SEC, FINRA). Dieses Skript laesst genau diesen Pfad Tag fuer Tag ueber die
Historie laufen (`simulate.run`) und stellt das Ergebnis neben SPY.

Weichen 22_ und 31_ stark voneinander ab, ist EINER von beiden falsch -
das ist der Replay-Test aus docs/schattenbetrieb.md §12.

    python scripts/31_simulate_ranking.py --panel qlib --start 2010-01-01 --symbole 600
    python scripts/31_simulate_ranking.py --panel sp500_close --start 2016-01-01   # ohne Volumen: vol_ruhig entfaellt
    python scripts/31_simulate_ranking.py --panel projekt --symbole 800

Ergebnis: results/labor/simulate_ranking_<panel>.csv (Trades) + Konsole.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from alpaca_bot import labor, simulate  # noqa: E402
from alpaca_bot.config import PROJECT_ROOT  # noqa: E402
from alpaca_bot.engine import EngineConfig  # noqa: E402
from alpaca_bot.signals import RankingWeights  # noqa: E402

LABOR_DIR = PROJECT_ROOT / "data" / "labor"
OUT_DIR = PROJECT_ROOT / "results" / "labor"


def panel_zu_bars(p: labor.Panel, symbole: list[str]) -> pd.DataFrame:
    frames = []
    for s in symbole:
        df = pd.DataFrame({"close": p.close[s]})
        for f in ("open", "high", "low"):
            df[f] = getattr(p, f)[s] if getattr(p, f) is not None else p.close[s]
        df["volume"] = p.volume[s] if p.volume is not None else 1e7
        df = df.dropna(subset=["close"])
        df.index = pd.DatetimeIndex(df.index).tz_localize("UTC")
        df["symbol"] = s
        frames.append(df[["symbol", "open", "high", "low", "close", "volume"]])
    out = pd.concat(frames)
    out.index.name = "timestamp"
    return out.set_index("symbol", append=True).swaplevel().sort_index()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--panel", required=True)
    ap.add_argument("--start", default=None)
    ap.add_argument("--ende", default=None)
    ap.add_argument("--symbole", type=int, default=600, help="liquideste N nach mittlerem Umsatz")
    ap.add_argument("--positions", type=int, default=50)
    ap.add_argument("--kapital", type=float, default=100_000)
    ap.add_argument("--spread-bps", type=float, default=5.0)
    ap.add_argument("--slippage-bps", type=float, default=5.0)
    ap.add_argument("--min-dollar-volume", type=float, default=25_000_000)
    ap.add_argument("--ohne-regime", action="store_true")
    ap.add_argument("--stop-atr", type=float, default=3.0,
                    help="Stop-Abstand in ATR; 99 = praktisch kein Stop (nur Rang und Zeit)")
    ap.add_argument("--min-hold", type=int, default=21)
    ap.add_argument("--max-hold", type=int, default=63)
    ap.add_argument("--exit-rank", type=float, default=0.50)
    ap.add_argument("--min-rank", type=float, default=0.90)
    args = ap.parse_args()

    t0 = time.time()
    panel = labor.panel_aus_cache(LABOR_DIR / args.panel).schneiden(args.start, args.ende)
    print(f"  {panel.beschreibung()}")
    etfs = {"SPY", "QQQ", "IWM", "DIA", "VTI", "EEM", "EFA", "TLT", "GLD", "HYG", "USO", "BNO"}
    aktien = [s for s in panel.symbole if s not in etfs]
    if panel.volume is not None:
        dv = (panel.volume * (panel.raw_close if panel.raw_close is not None else panel.close))
        rang = dv[aktien].median().sort_values(ascending=False)
        symbole = list(rang.index[: args.symbole])
    else:
        symbole = aktien[: args.symbole]
    spy = panel.close["SPY"] if "SPY" in panel.close.columns else None
    if spy is not None:
        spy = spy.copy()
        spy.index = pd.DatetimeIndex(spy.index).tz_localize("UTC")

    bars = panel_zu_bars(panel, symbole)
    print(f"  {len(symbole)} Symbole, {len(bars):,} Bars")

    weights = RankingWeights(market_regime_filter=not args.ohne_regime)
    if panel.volume is None:
        weights = RankingWeights(vol_ruhig=0.0, market_regime_filter=not args.ohne_regime)
        print("  Panel ohne Volumen: vol_ruhig = 0, Universum ohne Umsatzfilter")
    ecfg = EngineConfig.for_ranking(
        max_positions=args.positions, ranking_weights=weights,
        min_dollar_volume=(args.min_dollar_volume if panel.volume is not None else 0.0),
        max_position_pct=0.05 if args.positions >= 40 else 0.10,
        stop_atr=args.stop_atr, min_hold_days=args.min_hold, max_hold_days=args.max_hold,
        exit_rank_pct=args.exit_rank, min_rank_pct=args.min_rank,
    )
    print(f"  Engine: Stop {args.stop_atr} ATR, Haltedauer {args.min_hold}-{args.max_hold}, "
          f"Kauf ab Perzentil {args.min_rank}, Ausstieg unter {args.exit_rank}")
    scfg = simulate.SimConfig(initial_cash=args.kapital, spread_bps=args.spread_bps,
                              slippage_bps=args.slippage_bps, log_to_journal=False)
    res = simulate.run(bars, ecfg, scfg, market=spy, verbose=True)
    print(res.summary())

    eq = res.equity_curve
    r = eq.pct_change().dropna()
    if spy is not None:
        b = spy.pct_change().reindex(r.index).fillna(0.0)
        rows = []
        for y, g in r.groupby(r.index.year):
            rows.append({"jahr": int(y), "engine": float((1 + g).prod() - 1),
                         "spy": float((1 + b.loc[g.index]).prod() - 1),
                         "maxdd": labor._maxdd(g), "tage": len(g)})
        print("\n  JAHRESTABELLE (Engine-Pfad, alle Kosten):")
        print(pd.DataFrame(rows).set_index("jahr").round(3).to_string())
        kb = labor._kennzahlen(b)
        print(f"\n  SPY im selben Zeitraum: CAGR {kb['cagr']:.1%}  MaxDD {kb['max_drawdown']:.1%}")
    m = res.metrics()
    print(f"  Engine: CAGR {m.get('cagr', float('nan')):.1%}  Sharpe {m.get('sharpe', float('nan')):.2f}  "
          f"MaxDD {m.get('max_drawdown', float('nan')):.1%}  Trades {m.get('n_trades', 0)}  "
          f"Haltedauer Ø {m.get('mittlere_haltedauer', float('nan')):.0f}  Kosten {m.get('kosten_gesamt', 0):,.0f} $")
    if not res.trades.empty:
        print("  Ausstiegsgruende:", res.trades["exit_reason"].value_counts().to_dict())
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    tag = (f"simulate_ranking_{args.panel}_stop{args.stop_atr:g}"
           f"_h{args.min_hold}-{args.max_hold}_x{args.exit_rank:g}")
    res.trades.to_csv(OUT_DIR / f"{tag}.csv", index=False)
    eq.rename("kapital").to_csv(OUT_DIR / f"{tag}_kapital.csv")
    print(f"  gespeichert: {OUT_DIR / tag}.csv (+ _kapital.csv)")
    from alpaca_bot import befunde

    kz = {"cagr": m.get("cagr"), "sharpe": m.get("sharpe"), "max_drawdown": m.get("max_drawdown"),
          "n_trades": m.get("n_trades"), "trefferquote": m.get("trefferquote"),
          "erwartungswert_pro_trade": m.get("erwartungswert_pro_trade"),
          "mittlere_haltedauer": m.get("mittlere_haltedauer"), "kosten_gesamt": m.get("kosten_gesamt")}
    if spy is not None:
        kz["bench_cagr"], kz["bench_maxdd"] = kb["cagr"], kb["max_drawdown"]
    urteil, lehre = befunde.urteil_portfolio(kz)
    befunde.eintragen(skript="31", panel=args.panel, variante="ranking_engine", zeitraum=f"{eq.index[0].year}-{eq.index[-1].year}",
                      parameter={"regime": "kein" if args.ohne_regime else "trend_ok", "haltedauer": f"{args.min_hold}-{args.max_hold}",
                                 "kosten_bps": args.spread_bps * 2 + args.slippage_bps * 2, "top_n": args.positions,
                                 "stop_atr": args.stop_atr, "symbole": len(symbole), "min_rank": args.min_rank,
                                 "exit_rank": args.exit_rank},
                      kennzahlen=kz, urteil=urteil,
                      lehre=lehre + f"; Ausstiege {res.trades['exit_reason'].value_counts().to_dict() if not res.trades.empty else {}}",
                      hypothese="HYP-2027-20" if args.stop_atr >= 5 else None)
    print("  Befund ins Register geschrieben")
    print(f"\n  ({time.time() - t0:.0f} s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
