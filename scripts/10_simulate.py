#!/usr/bin/env python3
"""Schritt 10: Historien-Simulation - exakt der Ablauf des spaeteren Live-Betriebs.

Spielt die Vergangenheit Tag fuer Tag durch und ruft dabei dieselbe
`Engine.decide()` auf, die spaeter im Paper- und Live-Handel entscheidet.
Kein vektorisierter Backtest, kein zweiter Strategie-Code.

Enthalten: Ausfuehrung erst am Folgetag, Spread und Gebuehren, PDT-Regel,
Kursluecken bei Stops, lueckenloses Protokoll.

    python scripts/10_simulate.py
    python scripts/10_simulate.py --years 9 --cash 30000 --positions 12
    python scripts/10_simulate.py --insider          # mit SEC-Form-4-Daten (langsam)
"""

from __future__ import annotations

import argparse
import sys

import numpy as np
import pandas as pd

from alpaca_bot import compliance, data, pit, signals, simulate, universe
from alpaca_bot.config import RESULTS_DIR
from alpaca_bot.engine import EngineConfig


def yearly_breakdown(result, benchmark: pd.Series | None) -> pd.DataFrame:
    """Jahr fuer Jahr - haelt die Strategie ueber die Zeit, oder kam alles
    aus einem einzigen guten Jahr?"""
    eq = result.equity_curve
    rows = []
    for year, grp in eq.groupby(eq.index.year):
        if len(grp) < 2:
            continue
        r = float(grp.iloc[-1] / grp.iloc[0] - 1)
        row = {"Jahr": year, "Strategie": r}
        if benchmark is not None:
            b = benchmark.reindex(grp.index).ffill().dropna()
            if len(b) > 1:
                row["Buy&Hold SPY"] = float(b.iloc[-1] / b.iloc[0] - 1)
        rows.append(row)
    df = pd.DataFrame(rows)
    if "Buy&Hold SPY" in df.columns:
        df["Differenz"] = df["Strategie"] - df["Buy&Hold SPY"]
    return df


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--universe", default="broad_liquid")
    p.add_argument("--years", type=float, default=9.0)
    p.add_argument("--cash", type=float, default=30_000)
    p.add_argument("--positions", type=int, default=12)
    p.add_argument("--min-score", type=float, default=0.55)
    p.add_argument("--spread", type=float, default=5.0)
    p.add_argument("--slippage", type=float, default=3.0)
    p.add_argument("--insider", action="store_true",
                   help="SEC-Form-4-Daten einbeziehen (dauert beim ersten Lauf)")
    p.add_argument("--split", default="2023-01-01",
                   help="Ab hier gilt der Zeitraum als unberuehrte Validierung")
    args = p.parse_args()

    syms = universe.BENCHMARK_SETS.get(args.universe)
    if syms is None:
        print(f"Unbekanntes Universum. Verfuegbar: "
              f"{', '.join(universe.BENCHMARK_SETS)}")
        return 1

    print(compliance.preflight(len(syms) + 1, args.years, "1D"))
    print()

    # --- 1. Daten ---
    print(f"[1/5] Lade {len(syms)} Symbole + SPY, {args.years:g} Jahre ...")
    bars = data.get_bars(
        sorted(set(syms) | {"SPY"}), "1D", lookback_days=int(args.years * 365)
    )
    if bars.empty:
        print("Keine Daten erhalten.")
        return 1
    n_sym = bars.index.get_level_values("symbol").nunique()
    print(f"      {len(bars):,} Bars, {n_sym} Symbole")
    print()
    print(universe.survivorship_warning(n_sym, args.years, "large_cap"))

    spy = data.ohlcv(bars, "SPY")["close"] if "SPY" in bars.index.get_level_values("symbol") else None
    tradable = bars.drop("SPY", level="symbol", errors="ignore")

    # --- 2. Kausalitaet pruefen, BEVOR simuliert wird ---
    print(f"\n[2/5] Pruefe die Signalfunktion auf Zukunftslecks ...")
    probe = data.ohlcv(bars, syms[0])
    audit = pit.audit_feature_function(signals.build_signal_frame, probe, n_checks=5)
    print(f"      {audit}")
    if not audit.clean:
        print("      ABBRUCH: Undichte Signale - jedes Ergebnis waere wertlos.")
        return 1

    # --- 3. Optional: Insiderdaten ---
    insider = {}
    if args.insider:
        from alpaca_bot import edgar

        print(f"\n[3/5] Lade SEC-Form-4-Daten fuer {len(syms)} Symbole ...")
        print("      (erster Lauf dauert, danach aus dem Cache)")
        for i, sym in enumerate(syms, 1):
            try:
                df_sym = data.ohlcv(bars, sym)
                trades = edgar.insider_trades(sym, since="2016-01-01", max_filings=120)
                if not trades.empty:
                    insider[sym] = edgar.insider_features(trades, df_sym.index, sym)
                if i % 10 == 0:
                    print(f"      {i}/{len(syms)} ...")
            except Exception as e:  # noqa: BLE001
                print(f"      {sym}: {type(e).__name__}")
        with_buys = sum(
            1 for f in insider.values()
            if f.get("insider_buyers_90d", pd.Series([0])).max() > 0
        )
        print(f"      {len(insider)} Symbole mit Daten, davon {with_buys} "
              f"mit echten Marktkaeufen")
    else:
        print(f"\n[3/5] Insiderdaten uebersprungen (--insider zum Aktivieren)")

    # --- 4. Simulation ---
    ecfg = EngineConfig(
        max_positions=args.positions,
        min_score=args.min_score,
    )
    scfg = simulate.SimConfig(
        initial_cash=args.cash,
        spread_bps=args.spread,
        slippage_bps=args.slippage,
    )
    print(f"\n[4/5] Simuliere Tag fuer Tag "
          f"(max. {args.positions} Positionen, Score-Schwelle {args.min_score}) ...")
    result = simulate.run(tradable, ecfg, scfg, insider=insider, verbose=True)

    # --- 5. Auswertung ---
    print()
    print(result.summary())

    if spy is not None:
        eq = result.equity_curve
        b = spy.reindex(eq.index).ffill().dropna()
        if len(b) > 1:
            bh = float(b.iloc[-1] / b.iloc[0] - 1)
            print()
            print(f"  Buy & Hold SPY        : {bh:>13.2%}")
            print(f"  Differenz             : {result.total_return - bh:>13.2%}")

    print("\n" + "=" * 66)
    print("  JAHR FUER JAHR")
    print("=" * 66)
    yb = yearly_breakdown(result, spy)
    if not yb.empty:
        fmt = yb.copy()
        for c in fmt.columns:
            if c != "Jahr":
                fmt[c] = fmt[c].map(lambda v: f"{v:>8.2%}")
        print(fmt.to_string(index=False))

    # --- Unberuehrter Zeitraum ---
    split = pd.Timestamp(args.split, tz="UTC")
    eq = result.equity_curve
    dev, val = eq[eq.index < split], eq[eq.index >= split]
    print("\n" + "=" * 66)
    print("  ENTWICKLUNG GEGEN VALIDIERUNG")
    print("=" * 66)
    if len(dev) > 1 and len(val) > 1:
        r_dev = float(dev.iloc[-1] / dev.iloc[0] - 1)
        r_val = float(val.iloc[-1] / val.iloc[0] - 1)
        print(f"  bis {args.split}  : {r_dev:>8.2%}  ({len(dev)} Tage)")
        print(f"  ab  {args.split}  : {r_val:>8.2%}  ({len(val)} Tage)")
        print()
        if r_dev > 0 and r_val < 0:
            print("  WARNUNG: Funktioniert nur im Entwicklungszeitraum. Das ist")
            print("  das klassische Muster einer ueberangepassten Strategie.")
        elif r_val > 0 and r_dev > 0:
            print("  Beide Zeitraeume positiv - erstes gutes Zeichen.")
        else:
            print("  Kein tragfaehiges Ergebnis in beiden Zeitraeumen.")

    # --- Ausstiegsgruende und Signalqualitaet ---
    if not result.trades.empty:
        t = result.trades
        print("\n" + "=" * 66)
        print("  WORAN DIE TRADES ENDETEN")
        print("=" * 66)
        by_reason = t.groupby("exit_reason").agg(
            n=("return_pct", "size"),
            mittel=("return_pct", "mean"),
            summe_pnl=("net_pnl", "sum"),
        ).sort_values("n", ascending=False)
        print(by_reason.round(4).to_string())

        print("\n  Score beim Einstieg vs. Ergebnis:")
        t2 = t.copy()
        t2["score_gruppe"] = pd.cut(t2["entry_score"], bins=4)
        print(t2.groupby("score_gruppe", observed=True).agg(
            n=("return_pct", "size"), mittel=("return_pct", "mean")
        ).round(4).to_string())
        print("\n  Wenn hoehere Scores NICHT bessere Ergebnisse liefern,")
        print("  misst der Score nichts Verwertbares.")

    out = RESULTS_DIR / "simulation"
    out.mkdir(exist_ok=True)
    result.equity_curve.to_csv(out / "kapitalkurve.csv")
    result.trades.to_csv(out / "trades.csv", index=False)
    print(f"\n  Ergebnisse gespeichert: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
