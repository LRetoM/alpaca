#!/usr/bin/env python3
"""Selbsttest OHNE API-Keys.

Prueft Indikatoren, Backtester, Strategien und ML-Pipeline auf
synthetischen Kursdaten. Laeuft sofort, auch bevor die .env existiert.

    python scripts/00_selftest.py
"""

from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

import numpy as np
import pandas as pd


def synthetic_ohlcv(n: int = 1500, seed: int = 7) -> pd.DataFrame:
    """Random Walk mit leichtem Aufwaertsdrift und Volatilitaets-Clustern."""
    rng = np.random.default_rng(seed)
    vol = 0.01 * (1 + 0.5 * np.sin(np.arange(n) / 90))
    ret = rng.normal(0.0004, 1, n) * vol
    close = 100 * np.exp(np.cumsum(ret))
    idx = pd.bdate_range("2019-01-02", periods=n, tz="UTC")
    high = close * (1 + np.abs(rng.normal(0, 0.004, n)))
    low = close * (1 - np.abs(rng.normal(0, 0.004, n)))
    return pd.DataFrame(
        {
            "open": np.r_[close[0], close[:-1]],
            "high": np.maximum(high, close),
            "low": np.minimum(low, close),
            "close": close,
            "volume": rng.integers(1_000_000, 9_000_000, n).astype(float),
        },
        index=idx,
    )


def main() -> int:
    ok, fail = 0, 0

    def check(label: str, cond: bool, extra: str = "") -> None:
        nonlocal ok, fail
        if cond:
            ok += 1
            print(f"  [OK]   {label}{'  ' + extra if extra else ''}")
        else:
            fail += 1
            print(f"  [FEHL] {label}{'  ' + extra if extra else ''}")

    print("=" * 70)
    print("  SELBSTTEST (synthetische Daten, keine API noetig)")
    print("=" * 70)

    df = synthetic_ohlcv()
    print(f"\nTestdaten: {len(df)} Bars, Kurs {df['close'].iloc[0]:.1f} "
          f"-> {df['close'].iloc[-1]:.1f}")

    # --- Indikatoren ---
    print("\n[1] Indikatoren")
    from alpaca_bot import indicators as ind

    r = ind.rsi(df["close"])
    check("RSI im Bereich 0-100", bool(r.min() >= 0 and r.max() <= 100),
          f"min={r.min():.1f} max={r.max():.1f}")
    check("SMA20 hat korrekte Warmlaufphase", int(ind.sma(df["close"], 20).isna().sum()) == 19)
    a = ind.atr(df)
    check("ATR positiv", bool(a.dropna().gt(0).all()), f"mittel={a.mean():.2f}")
    full = ind.add_all(df)
    check("add_all liefert alle Indikatoren", full.shape[1] > 15,
          f"{full.shape[1]} Spalten")

    # Kausalitaet: aendert ein zukuenftiger Wert einen vergangenen Indikator?
    df2 = df.copy()
    df2.iloc[-1, df2.columns.get_loc("close")] *= 5
    check("Indikatoren schauen nicht in die Zukunft",
          bool(np.allclose(ind.rsi(df["close"]).iloc[:-1],
                           ind.rsi(df2["close"]).iloc[:-1], equal_nan=True)))

    # --- Backtester ---
    print("\n[2] Backtester")
    from alpaca_bot import backtest as bt

    always_long = pd.Series(1.0, index=df.index)
    res = bt.backtest(df["close"], always_long, fee_bps=0, slippage_bps=0)
    bh = float(df["close"].iloc[-1] / df["close"].iloc[0] - 1)
    check("Dauer-Long entspricht Buy & Hold",
          abs(res.metrics["total_return"] - bh) < 0.01,
          f"{res.metrics['total_return']:.2%} vs {bh:.2%}")

    flat = bt.backtest(df["close"], pd.Series(0.0, index=df.index))
    check("Null-Position -> 0 % Rendite", abs(flat.metrics["total_return"]) < 1e-9)

    # Lookahead-Probe: Ein Signal, das aus zukuenftigen Kursen gebaut wurde,
    # liefert absurde Renditen. Der shift() im Backtester kann das NICHT
    # verhindern - er schuetzt nur davor, das Signal von Bar t auf die
    # Rendite von Bar t selbst anzuwenden. Merke: eine Renditezahl in dieser
    # Groessenordnung bedeutet immer ein Datenleck, nie eine gute Strategie.
    cheat = (df["close"].shift(-1) > df["close"]).astype(float)
    cheat_res = bt.backtest(df["close"], cheat, fee_bps=0, slippage_bps=0)
    honest = bt.backtest(df["close"], cheat.shift(1).fillna(0),
                         fee_bps=0, slippage_bps=0)
    check("Zukunftswissen faellt als absurde Rendite auf (Leck-Probe)",
          cheat_res.metrics["total_return"] > 10 * abs(honest.metrics["total_return"]),
          f"mit Leck {cheat_res.metrics['total_return']:>9.1%} | "
          f"ohne Leck {honest.metrics['total_return']:.1%}")

    costs = bt.backtest(df["close"], cheat, fee_bps=5, slippage_bps=20)
    check("Kosten reduzieren die Rendite",
          costs.metrics["total_return"] < cheat_res.metrics["total_return"],
          f"{costs.metrics['total_return']:.1%} statt "
          f"{cheat_res.metrics['total_return']:.1%}")

    # --- Strategien ---
    print("\n[3] Strategien")
    from alpaca_bot import strategies

    for name in strategies.REGISTRY:
        sig = strategies.get(name).generate_signals(df)
        r = bt.backtest(df["close"], sig)
        check(f"{name:<20}", sig.notna().all() and len(sig) == len(df),
              f"Rendite {r.metrics['total_return']:>7.1%} | "
              f"Sharpe {r.metrics['sharpe']:>5.2f} | "
              f"Trades {r.metrics['n_trades']:>3}")

    # --- ML ---
    print("\n[4] ML-Pipeline")
    from alpaca_bot import features, ml

    X, y = features.prepare(df, horizon=5, kind="binary")
    check("Features gebaut", X.shape[1] > 20 and len(X) > 1000,
          f"{X.shape[1]} Features x {len(X)} Zeilen")
    check("keine NaN/Inf in den Features",
          bool(np.isfinite(X.to_numpy(dtype=float)).all()))

    wf = ml.walk_forward_predict(X, y, "gbm", n_splits=3, embargo=5, min_train=400)
    check("Walk-Forward liefert Out-of-Sample-Vorhersagen",
          len(wf.predictions) > 200, f"{len(wf.predictions)} Vorhersagen")
    check("Accuracy nahe Zufall auf Random-Walk-Daten",
          0.35 < wf.accuracy < 0.75,
          f"acc={wf.accuracy:.3f} auc={wf.auc:.3f} (Zufall erwartet - korrekt!)")

    sig = ml.signal_from_predictions(wf.predictions, 0.55)
    ml_res = bt.backtest(df["close"].loc[sig.index], sig)
    check("ML-Signal ist backtestbar", np.isfinite(ml_res.metrics["sharpe"]),
          f"Sharpe {ml_res.metrics['sharpe']:.2f}")

    # --- Point-in-Time-Waechter ---
    print("\n[5] Point-in-Time-Waechter")
    from alpaca_bot import pit

    clean = pit.audit_feature_function(features.build_features, df, n_checks=3)
    check("echte Feature-Funktion ist dicht", clean.clean,
          f"{clean.n_checks} Abschneidepunkte geprueft")

    def leaky(d):
        out = pd.DataFrame(index=d.index)
        out["ok"] = d["close"].rolling(20).mean() / d["close"]
        out["LECK_zscore"] = (d["close"] - d["close"].mean()) / d["close"].std()
        out["LECK_bfill"] = d["close"].shift(-3).bfill() / d["close"]
        return out

    leak = pit.audit_feature_function(leaky, df, n_checks=3)
    check("erkennt eingebautes Leck", not leak.clean and len(leak.leaking_columns) == 2,
          f"gefunden: {', '.join(sorted(leak.leaking_columns))}")
    check("verdaechtigt saubere Spalte NICHT", "ok" not in leak.leaking_columns)
    check("Stichprobenrechnung stimmt", 550 < pit.required_sample_size(0.05) < 700,
          f"5%%-Vorsprung -> {pit.required_sample_size(0.05)} Beobachtungen")

    env = pit.Envelope()
    try:
        env.vault(df)
        check("Tresor ist gesperrt", False)
    except PermissionError:
        check("Tresor ist gesperrt", True, "nur mit confirm=True zu oeffnen")

    # --- Ereignisstudie ---
    print("\n[6] Ereignisstudie")
    from alpaca_bot import events

    bars = pd.concat({"TEST": df}, names=["symbol", "timestamp"])
    cfg = events.EventConfig(threshold=0.15, window=30, lookback=60, blackout=3,
                             min_dollar_volume=0)
    ev = events.find_events(bars, cfg)
    check("findet Ereignisse", len(ev) > 0, f"{len(ev)} Bewegungen ueber +15%%")
    if len(ev) > 1:
        gaps = ev["index_pos"].diff().dropna()
        check("Ereignisse ueberlappen nicht", bool((gaps >= cfg.cooldown).all()),
              f"kleinster Abstand {int(gaps.min())} Bars (Sperre {cfg.cooldown})")
    win = events.observation_window(bars, "TEST", ev.iloc[0]["t0"], cfg) if len(ev) else None
    check("Beobachtungsfenster endet vor dem Ereignis",
          win is not None and win.index[-1] < ev.iloc[0]["t0"],
          f"letzter Bar {win.index[-1].date()} vs t0 {ev.iloc[0]['t0'].date()}" if win is not None else "")
    check("leere Kontrollgruppe stuerzt nicht ab",
          len(events.sample_controls(bars, ev.head(0), cfg, n_per_event=0)) == 0)

    # --- Kosten ---
    print("\n[7] Kostenmodell")
    from alpaca_bot import costs

    buy = costs.estimate_costs("buy", 100, last=100.0, spread_bps=5)
    sell = costs.estimate_costs("sell", 100, last=100.0, spread_bps=5)
    check("Kauf laeuft ueber den Briefkurs", buy.effective_price > 100.0,
          f"{buy.effective_price:.4f}")
    check("Verkauf laeuft ueber den Geldkurs", sell.effective_price < 100.0,
          f"{sell.effective_price:.4f}")
    check("SEC/FINRA nur beim Verkauf",
          buy.sec_fee == 0 and buy.finra_taf == 0 and sell.sec_fee > 0)
    rt = costs.round_trip(100, 100.0, 101.0, spread_bps=5)
    check("echter Gewinn < gedachter Gewinn",
          rt["echter_gewinn"] < rt["naiver_gewinn"],
          f"{rt['echter_gewinn']:.2f}$ statt {rt['naiver_gewinn']:.2f}$ "
          f"({rt['anteil_weg']:.0%} weg)")
    check("Break-even liegt ueber dem Einstieg", rt["breakeven_kurs"] > 100.0,
          f"{rt['breakeven_kurs']:.4f}")

    # --- Broker-Regeln ---
    print("\n[8] Broker-Regeln (PDT)")
    from alpaca_bot import compliance

    small = compliance.check_account(
        {"equity": 8000, "portfolio_value": 8000, "daytrade_count": 3,
         "trading_blocked": False, "pattern_day_trader": False})
    big = compliance.check_account(
        {"equity": 50000, "portfolio_value": 50000, "daytrade_count": 9,
         "trading_blocked": False, "pattern_day_trader": False})
    check("PDT blockt unter 25.000 $ ab 3 Daytrades", not small.ok and small.is_pdt_restricted)
    check("ueber 25.000 $ keine PDT-Grenze", big.ok and not big.is_pdt_restricted)
    check("erkennt Daytrade korrekt",
          compliance.would_be_day_trade("AAPL", "sell", {"AAPL": "buy"})
          and not compliance.would_be_day_trade("AAPL", "sell", {}))

    # --- Rate-Limits ---
    print("\n[9] Rate-Limits")
    from alpaca_bot.ratelimit import QUOTAS, RateLimiter

    check("alle Quellen haben ein Limit",
          all(q.per_minute or q.per_second or q.per_day or q.per_hour
              for q in QUOTAS.values()),
          f"{len(QUOTAS)} Quellen erfasst")
    check("alle Quellen sind datiert", all(q.verified for q in QUOTAS.values()))
    av = RateLimiter("alphavantage")
    check("Tageskontingent wird gefuehrt", av.remaining_today() is not None,
          f"Alpha Vantage: {av.remaining_today()} von 25 frei")
    t0 = time.monotonic()
    lim = RateLimiter("sec_edgar")
    for _ in range(20):
        lim.acquire()
    check("Drossel bremst tatsaechlich", time.monotonic() - t0 > 1.0,
          f"20 Requests bei 8/s -> {time.monotonic() - t0:.1f}s")

    # --- Protokoll ---
    print("\n[10] Protokoll (Journal)")
    from alpaca_bot.journal import Journal, make_price_lookup

    jpath = Path(tempfile.mkdtemp()) / "test.sqlite"
    j = Journal(jpath)
    with j.run("selbsttest", config={"x": 1}) as run:
        for i in range(20):
            d = run.decision("TEST", "buy", ts=df.index[100 + i * 5],
                             reasons={"grund_a": True}, price=float(df["close"].iloc[100 + i * 5]))
            # `referenz_quelle="quote"` ist seit dem 23.08.2026 Pflicht,
            # damit die Zeile in der Slippage-Auswertung mitzaehlt: Die
            # Bereinigung nimmt nur noch Zeilen mit VERIFIZIERTER Referenz
            # (§G19 Fund 3). Ohne dieses Argument bildet der Selbsttest
            # den echten Schreibpfad nicht mehr ab - `live.py` setzt es
            # bei jeder Order.
            run.order(d, symbol="TEST", side="buy", status="filled", qty=1,
                      dry_run=False, expected_price=100.0, fill_price=100.05,
                      referenz_quelle="quote")
    check("Lauf, Entscheidungen und Orders gespeichert",
          len(j.table("runs")) == 1 and len(j.table("decisions")) == 20
          and len(j.table("orders")) == 20)
    n_out = j.evaluate_outcomes(make_price_lookup(bars), horizons=(1, 5))
    check("Ergebnisse werden Entscheidungen zugeordnet", n_out > 0,
          f"{n_out} Bewertungen")
    # `script` ausdruecklich mitgeben: Seit dem 22.08.2026 liefert
    # `decision_quality` per Vorgabe NUR den Live-Bot (§G13). Dass dieser
    # Lauf hier unter "selbsttest" laeuft und ohne das Argument leer
    # zurueckkaeme, ist genau die gewollte Wirkung - die Zeile darunter
    # prueft beide Richtungen.
    check("Entscheidungsqualitaet je Begruendung auswertbar",
          not j.decision_quality(5, script="selbsttest").empty)
    check("Fremde Laeufe bleiben aus der Auswertung",
          j.decision_quality(5).empty and j.decision_quality(5, script=None).shape[0] > 0)
    check("Slippage wird gemessen", not j.slippage_report().empty,
          f"{j.slippage_report()['mittel'].iloc[0]:.1f} bps")
    check("Integritaetspruefung meldet keine Luecke", len(j.integrity_check()) == 0)

    # --- Selbstpruefung ---
    print("\n[11] Selbstpruefung gegen die Projektverfassung")
    from alpaca_bot import selfcheck

    rep = selfcheck.run_all()
    check("Projekt haelt seine eigenen Regeln ein", rep.ok,
          f"{rep.checks_run} Pruefungen, {len(rep.violations)} Verstoesse")

    # --- Config ---
    print("\n[12] Konfiguration")
    from alpaca_bot.config import ConfigError, get_settings

    try:
        s = get_settings()
        check("*.env gefunden und Keys gesetzt", True,
              f"Modus={'PAPER' if s.paper else 'LIVE'} Feed={s.data_feed}")
    except ConfigError:
        check("*.env noch nicht angelegt", True,
              "-> .env.example nach .env kopieren und Keys eintragen")

    print("\n" + "=" * 70)
    print(f"  {ok} Pruefungen bestanden, {fail} fehlgeschlagen")
    print("=" * 70)
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
