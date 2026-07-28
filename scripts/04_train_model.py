#!/usr/bin/env python3
"""Schritt 4: ML-Modell trainieren und ehrlich bewerten.

Ablauf:
  1. Features bauen (nur Vergangenheitsdaten)
  2. Label: steigt der Kurs in den naechsten N Tagen?
  3. Walk-Forward-Validierung mit Embargo (kein Datenleck)
  4. Vorhersagen in eine Strategie uebersetzen und gegen Buy & Hold testen

    python scripts/04_train_model.py SPY --horizon 5
    python scripts/04_train_model.py AAPL --model rf --threshold 0.6
"""

from __future__ import annotations

import argparse
import sys

import pandas as pd

from alpaca_bot import backtest as bt
from alpaca_bot import data, features, ml
from alpaca_bot.config import RESULTS_DIR


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("symbol", nargs="?", default="SPY")
    p.add_argument("--years", type=float, default=10.0)
    p.add_argument("--horizon", type=int, default=5, help="Prognosehorizont in Tagen")
    p.add_argument("--model", default="gbm", choices=["gbm", "rf", "logreg"])
    p.add_argument("--threshold", type=float, default=0.55)
    p.add_argument("--splits", type=int, default=5)
    p.add_argument("--plot", action="store_true")
    args = p.parse_args()

    sym = args.symbol.upper()

    # --- Daten: Zielwert + Markt-Referenz fuer relative Staerke ----------
    print(f"[1/5] Lade Daten fuer {sym} und SPY (Marktreferenz) ...")
    symbols = list({sym, "SPY"})
    bars = data.get_bars(symbols, "1D", lookback_days=int(args.years * 365))
    df = data.ohlcv(bars, sym)
    market = data.ohlcv(bars, "SPY")["close"] if sym != "SPY" else None
    print(f"      {len(df)} Handelstage")

    # --- Features & Label ------------------------------------------------
    print(f"[2/5] Baue Features, Label = Rendite ueber {args.horizon} Tage > 0 ...")
    X, y = features.prepare(df, horizon=args.horizon, kind="binary", market=market)
    print(f"      {X.shape[1]} Features, {len(X)} verwendbare Zeilen")
    print(f"      Basisrate (Anteil steigender Perioden): {y.mean():.1%}")
    print(f"      -> Ein Modell muss DIESE Quote schlagen, nicht 50 %.")

    # --- Walk-Forward ----------------------------------------------------
    print(f"[3/5] Walk-Forward-Validierung ({args.splits} Folds, "
          f"Embargo {args.horizon} Tage) ...")
    res = ml.walk_forward_predict(
        X, y, model_kind=args.model, n_splits=args.splits, embargo=args.horizon
    )
    print()
    print(res.fold_scores.to_string(index=False))
    print()
    print(res.summary())

    # --- Wichtigste Features ---------------------------------------------
    print(f"\n[4/5] Welche Features tragen wirklich bei?")
    imp = ml.feature_importance(res, X, y, n_repeats=5)
    print(imp.head(12).to_string(index=False))

    # --- Aus Vorhersagen wird eine Strategie -----------------------------
    print(f"\n[5/5] Backtest der Modell-Signale (Schwelle {args.threshold}) ...")
    signal = ml.signal_from_predictions(res.predictions, long_threshold=args.threshold)
    prices = df["close"].loc[signal.index]
    result = bt.backtest(prices, signal)

    print()
    print(result.summary())

    acc, base = res.accuracy, float(y.loc[res.predictions.index].mean())
    print("\n--- Einordnung ---")
    if acc <= base + 0.005:
        print(f"  Das Modell ({acc:.1%}) schlaegt die Basisrate ({base:.1%}) NICHT.")
        print("  Das ist der Normalfall und kein Grund zur Sorge - es heisst:")
        print("  diese Features/dieser Horizont enthalten kein nutzbares Signal.")
        print("  Naechste Idee: laengerer Horizont (20 Tage), mehrere Symbole")
        print("  gemeinsam trainieren, oder Volatilitaet statt Richtung vorhersagen.")
    elif acc > base + 0.10:
        print(f"  {acc:.1%} vs. Basisrate {base:.1%} ist verdaechtig hoch.")
        print("  Bevor du dich freust: nach einem Datenleck suchen.")
    else:
        print(f"  {acc:.1%} vs. Basisrate {base:.1%} - ein kleiner, plausibler Vorsprung.")
        print("  Genau so sieht ein echtes (schwaches) Signal aus.")
    print(f"  Entscheidend ist aber die Zeile 'Sharpe Ratio' oben, nicht die Accuracy:")
    print(f"  ein Modell kann oft richtig liegen und trotzdem Geld verlieren.")

    if args.plot:
        path = RESULTS_DIR / f"ml_{sym}_{args.model}_h{args.horizon}.png"
        bt.plot(result, f"{sym} - ML {args.model} (h={args.horizon})", save_path=path)
        imp.to_csv(RESULTS_DIR / f"ml_{sym}_features.csv", index=False)
        print(f"\nChart + Feature-Ranking gespeichert in {RESULTS_DIR}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
