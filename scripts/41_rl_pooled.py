#!/usr/bin/env python3
"""Querschnitt-DQN: einen Agenten ueber viele Symbole zugleich trainieren.

Die letzte nicht ausgeschoepfte Lernvariante (`docs/BEFUNDE.md` §G50):
Breite statt Tiefe. Ein einziger Agent lernt eine Ziel-Positionsgroesse
(0/25/50/100 %) aus den Merkmalen VIELER Symbole gemeinsam, walk-forward
bewertet, Urteil am Timing-Test je Symbol - und ein einzelnes auswendig
gelerntes Fenster darf das Gesamturteil nicht tragen.

Reiner Offline-Lauf, keine Handelslogik, kein Versuchszaehlerplatz
(BETRIEBSPLAN §4). Gebuehren und Slippage stecken in der Umgebung und
fallen bei jeder Positionsaenderung an.

    python scripts/41_rl_pooled.py --universe live --max-symbols 40 --hochvola --jahre 10
    python scripts/41_rl_pooled.py --symbols AAPL,NVDA,TSLA,AMD,SMCI --jahre 8 --folds 3
"""

from __future__ import annotations

import argparse
import json
import sys

import numpy as np
import pandas as pd

from alpaca_bot import data, features, pit, universe
from alpaca_bot.config import RESULTS_DIR
from alpaca_bot.journal import Journal
from alpaca_bot.rl.dqn import DQNConfig
from alpaca_bot.rl.env import EnvConfig, RewardConfig
from alpaca_bot.rl.pooled import train_pooled_walk_forward


def _symbolliste(args) -> list[str]:
    if args.symbols:
        return [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    syms = universe.load_universe(max_symbols=args.max_symbols)
    return syms


def _hochvola_filter(reihen: dict, anteil: float = 0.66) -> dict:
    atrp = {}
    for sym, (feats, prices) in reihen.items():
        r = prices.pct_change().tail(500)
        if len(r) > 100:
            atrp[sym] = float(r.std())
    if not atrp:
        return reihen
    grenze = np.percentile(list(atrp.values()), anteil * 100)
    return {s: v for s, v in reihen.items()
            if atrp.get(s, 0.0) >= grenze}


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--symbols", default=None,
                   help="Kommaliste; sonst --universe live")
    p.add_argument("--universe", default="live")
    p.add_argument("--max-symbols", type=int, default=40)
    p.add_argument("--jahre", type=float, default=10.0)
    p.add_argument("--hochvola", action="store_true",
                   help="Universum auf das oberste Vola-Terzil eindampfen")
    p.add_argument("--folds", type=int, default=3)
    p.add_argument("--episodes", type=int, default=5,
                   help="Trainingsrunden je Symbol und Fenster")
    p.add_argument("--cash", type=float, default=100_000)
    p.add_argument("--slippage", type=float, default=3.0)
    p.add_argument("--turnover-penalty", type=float, default=0.5)
    p.add_argument("--drawdown-penalty", type=float, default=2.0)
    p.add_argument("--gamma", type=float, default=0.97)
    p.add_argument("--seed", type=int, default=0)
    args = p.parse_args()

    syms = _symbolliste(args)
    print(f"[1/4] Lade {len(syms)} Symbole, {args.jahre:g} Jahre ...")
    reihen: dict[str, tuple[pd.DataFrame, pd.Series]] = {}
    fehl = 0
    for i, sym in enumerate(syms, 1):
        try:
            bars = data.get_bars(sym, "1D", lookback_days=int(args.jahre * 365),
                                 use_cache=True)
            if bars.empty:
                fehl += 1
                continue
            df = data.ohlcv(bars, sym)
            if len(df) < 400:
                fehl += 1
                continue
            X = features.build_features(df).ffill().fillna(0.0)
            reihen[sym] = (X, df["close"])
        except Exception as e:  # noqa: BLE001
            fehl += 1
            if i <= 5:
                print(f"      {sym}: {type(e).__name__}")
        if i % 20 == 0:
            print(f"      {i}/{len(syms)} ({len(reihen)} nutzbar)")
    if len(reihen) < 5:
        print(f"Zu wenige nutzbare Symbole ({len(reihen)}).")
        return 1
    print(f"      {len(reihen)} nutzbare Reihen, {fehl} verworfen")

    if args.hochvola:
        reihen = _hochvola_filter(reihen)
        print(f"      Hochvola-Filter: {len(reihen)} Symbole")

    print("[2/4] Pruefe die Merkmalsfunktion auf Zukunftslecks ...")
    bsp = next(iter(reihen))
    df_bsp = data.ohlcv(
        data.get_bars(bsp, "1D", lookback_days=int(args.jahre * 365), use_cache=True),
        bsp)
    audit = pit.audit_feature_function(features.build_features, df_bsp)
    print(f"      {audit}")
    if not audit.clean:
        print("      ABBRUCH: undichte Merkmale.")
        return 1

    env_cfg = EnvConfig(
        initial_cash=args.cash, slippage_bps=args.slippage,
        reward=RewardConfig(turnover_penalty=args.turnover_penalty,
                            drawdown_penalty=args.drawdown_penalty),
    )

    journal = Journal()
    with journal.run("41_rl_pooled", config=vars(args)) as run:
        run.log("daten", symbole=len(reihen), jahre=args.jahre)
        print(f"[3/4] Querschnitt-Training: {len(reihen)} Symbole, "
              f"{args.folds} Fenster, {args.episodes} Runden je Symbol/Fenster ...")
        report = train_pooled_walk_forward(
            reihen, n_folds=args.folds,
            episodes_per_symbol_per_fold=args.episodes,
            env_config=env_cfg, dqn_config=DQNConfig(gamma=args.gamma),
            seed=args.seed, verbose=True,
        )

        print("\n[4/4] Auswertung\n")
        ft = report.fold_table()
        if not ft.empty:
            print("  FENSTER-UEBERSICHT")
            print(ft.to_string(index=False))
            print()
        st = report.table()
        if not st.empty:
            # die auffaelligsten Symbole zeigen
            top = st.sort_values("timing_percentile", ascending=False).head(12)
            print("  SYMBOLE MIT DEM HOECHSTEN TIMING-PERZENTIL")
            print(top[["fold", "symbol", "test_from", "test_to", "agent_return",
                       "matched_constant_return", "avg_exposure",
                       "timing_percentile"]].to_string(index=False))
            print()
        print(report.verdict())

        run.snapshot("rl_pooled_symbole", st)
        run.log("rl_pooled_urteil",
                median_timing=report.overall_median_timing(),
                frac_skill=report.overall_frac_skill(),
                frac_beat_matched=report.frac_beat_matched())

    RESULTS_DIR.joinpath("rl_pooled").mkdir(parents=True, exist_ok=True)
    pfad = RESULTS_DIR / "rl_pooled" / f"lauf_{args.seed}_{len(reihen)}sym.json"
    pfad.write_text(json.dumps({
        "symbole": len(reihen), "jahre": args.jahre, "folds": args.folds,
        "median_timing": report.overall_median_timing(),
        "frac_skill": report.overall_frac_skill(),
        "frac_beat_matched": report.frac_beat_matched(),
        "fenster": ft.to_dict("records") if not ft.empty else [],
    }, indent=2, default=str), encoding="utf-8")
    print(f"\n  Geschrieben: {pfad}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
