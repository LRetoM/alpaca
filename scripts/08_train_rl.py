#!/usr/bin/env python3
"""Schritt 8: DQN-Agent trainieren - mit ehrlicher Bewertung.

Der Agent lernt eine Ziel-Positionsgroesse (0 / 25 / 50 / 100 %), nicht
"kaufen oder verkaufen". Belohnt wird das Wachstum des Kontos, bestraft
werden Umschichten, neue Tiefs und Regelverstoesse.

Das Urteil haengt NICHT an der Rendite, sondern am Timing-Test: Die
Positionsfolge des Agenten wird zeitlich verschoben und erneut bewertet.
Nur wenn die echte Reihenfolge deutlich besser abschneidet als ihre
verschobenen Kopien, steckt echtes Timing dahinter.

    python scripts/08_train_rl.py SPY --years 10
    python scripts/08_train_rl.py AAPL --episodes 40 --folds 5
"""

from __future__ import annotations

import argparse
import sys

from alpaca_bot import data, features, pit
from alpaca_bot.config import RESULTS_DIR
from alpaca_bot.journal import Journal
from alpaca_bot.rl import DQNConfig, train_walk_forward
from alpaca_bot.rl.env import EnvConfig, RewardConfig


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("symbol", nargs="?", default="SPY")
    p.add_argument("--years", type=float, default=10.0)
    p.add_argument("--folds", type=int, default=4)
    p.add_argument("--episodes", type=int, default=25)
    p.add_argument("--cash", type=float, default=100_000)
    p.add_argument("--slippage", type=float, default=3.0)
    p.add_argument("--turnover-penalty", type=float, default=0.5)
    p.add_argument("--drawdown-penalty", type=float, default=2.0)
    p.add_argument("--gamma", type=float, default=0.99)
    p.add_argument("--save", action="store_true")
    args = p.parse_args()

    sym = args.symbol.upper()
    journal = Journal()

    with journal.run("08_train_rl", config=vars(args)) as run:
        print(f"[1/3] Lade {sym} ({args.years:g} Jahre) ...")
        bars = data.get_bars(sym, "1D", lookback_days=int(args.years * 365))
        if bars.empty:
            print("Keine Daten erhalten.")
            return 1
        df = data.ohlcv(bars, sym)
        print(f"      {len(df)} Handelstage")

        print("[2/3] Baue Merkmale und pruefe auf Zukunftslecks ...")
        audit = pit.audit_feature_function(features.build_features, df)
        print(f"      {audit}")
        if not audit.clean:
            print("      ABBRUCH: Undichte Merkmale.")
            return 1
        X = features.build_features(df).ffill().fillna(0.0)
        run.log("merkmale", n=X.shape[1], bars=len(X), pit_sauber=True)

        print(f"[3/3] Walk-Forward-Training ({args.folds} Fenster, "
              f"{args.episodes} Episoden je Fenster) ...")
        env_cfg = EnvConfig(
            initial_cash=args.cash,
            slippage_bps=args.slippage,
            reward=RewardConfig(
                turnover_penalty=args.turnover_penalty,
                drawdown_penalty=args.drawdown_penalty,
            ),
        )
        report = train_walk_forward(
            X, df["close"],
            n_folds=args.folds,
            episodes_per_fold=args.episodes,
            env_config=env_cfg,
            dqn_config=DQNConfig(gamma=args.gamma),
        )

        table = report.table()
        print("\n" + "=" * 100)
        print(table[[
            "fold", "test_from", "test_to", "agent_return", "buy_hold_return",
            "matched_constant_return", "avg_exposure", "timing_percentile",
            "n_trades", "max_drawdown",
        ]].to_string(index=False))
        print()
        print(report.verdict())

        run.snapshot("rl_fenster", table)
        run.log("rl_urteil",
                timing=float(table["timing_percentile"].mean()),
                rendite=float(table["agent_return"].mean()))

        if args.save and report.agent:
            path = report.agent.save(RESULTS_DIR / f"dqn_{sym}.pt")
            print(f"\n  Modell gespeichert: {path}")
            print("  ACHTUNG: Ein gespeichertes Modell ohne nachgewiesenes")
            print("  Timing-Koennen darf NICHT zum Handeln verwendet werden.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
