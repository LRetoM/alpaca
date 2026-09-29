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
            run.order(d, symbol="TEST", side="buy", status="filled", qty=1,
                      dry_run=False, expected_price=100.0, fill_price=100.05)
    check("Lauf, Entscheidungen und Orders gespeichert",
          len(j.table("runs")) == 1 and len(j.table("decisions")) == 20
          and len(j.table("orders")) == 20)
    n_out = j.evaluate_outcomes(make_price_lookup(bars), horizons=(1, 5))
    check("Ergebnisse werden Entscheidungen zugeordnet", n_out > 0,
          f"{n_out} Bewertungen")
    check("Entscheidungsqualitaet je Begruendung auswertbar",
          not j.decision_quality(5).empty)
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
    print("\n[13] Strategie 'ranking' (Querschnitts-Score, Rangverlust, Mindesthaltedauer)")
    from alpaca_bot.engine import Engine, EngineConfig, MarketSnapshot, PortfolioState, Position

    rng = np.random.default_rng(2)
    idx = pd.bdate_range("2018-01-01", periods=600, tz="UTC")
    bars = {}
    for i in range(120):
        c = 40 * np.cumprod(1 + rng.normal(0.0003 * (i % 5), 0.02, 600))
        bars[f"S{i:03d}"] = pd.DataFrame(
            {"open": c, "high": c * 1.01, "low": c * 0.99, "close": c,
             "volume": rng.integers(2_000_000, 5_000_000, 600)}, index=idx)
    spy = pd.Series(100 * np.cumprod(1 + rng.normal(0.0005, 0.01, 600)), index=idx)
    snap = MarketSnapshot(as_of=idx[-1], bars=bars, market=spy)
    eng = Engine(EngineConfig.for_ranking(max_positions=10, min_dollar_volume=1e6))
    dec = eng.decide(snap, PortfolioState(cash=100_000, equity=100_000))
    check("Ranking kauft aus dem obersten Dezil, hoechstens max_positions",
          0 < len(dec) <= 10 and all(d.reasons["rang_pct"] >= 0.9 for d in dec),
          f"{len(dec)} Kaeufe")
    check("Score entsteht im Querschnitt (Z-Score-Mix, Perzentil 0..1)",
          all(0 <= d.reasons["rang_pct"] <= 1 for d in dec) and len(eng._qs) >= 30)
    schlecht = min(eng._qs, key=lambda s: eng._qs[s]["pct"])
    alt = PortfolioState(cash=50_000, equity=100_000, positions={
        schlecht: Position(schlecht, 100, 40.0, idx[-40], 30.0, 999.0, bars_held=30, high_water=40.0)})
    verk = [d for d in eng.decide(snap, alt) if d.action == "sell"]
    check("Rangverlust nach Mindesthaltedauer verkauft",
          len(verk) == 1 and verk[0].reasons["ausstiegsgrund"] == "rangverlust")
    jung = PortfolioState(cash=50_000, equity=100_000, positions={
        schlecht: Position(schlecht, 100, 40.0, idx[-5], 30.0, 999.0, bars_held=5, high_water=40.0)})
    check("Kein Rangverlust-Ausstieg vor der Mindesthaltedauer",
          not [d for d in eng.decide(snap, jung) if d.action == "sell"])
    check("Regeln der Strategie vollstaendig protokollierbar",
          {"min_hold_days", "min_rank_pct", "exit_rank_pct"} <= set(eng.cfg.as_dict()))
    # Verlaengerung: am Zeitausstieg bleibt, wer noch im Kaufbereich steht
    bester = max(eng._qs, key=lambda s: eng._qs[s]["pct"])
    eng_v = Engine(EngineConfig.for_ranking(max_positions=10, min_dollar_volume=1e6, renew_rank_pct=0.9))
    reif = PortfolioState(cash=50_000, equity=100_000, positions={
        bester: Position(bester, 100, 40.0, idx[-70], 30.0, 999.0, bars_held=63, high_water=40.0),
        schlecht: Position(schlecht, 100, 40.0, idx[-70], 30.0, 999.0, bars_held=63, high_water=40.0)})
    verk_v = {d.symbol: d.reasons["ausstiegsgrund"] for d in eng_v.decide(snap, reif) if d.action == "sell"}
    check("Verlaengerung: Top-Position bleibt nach max_hold, schwache geht (zeitausstieg)",
          bester not in verk_v and verk_v.get(schlecht) == "zeitausstieg", str(verk_v))
    check("Ohne Verlaengerung: beide gehen am Zeitausstieg",
          len([d for d in eng.decide(snap, reif) if d.action == "sell"]) == 2)
    eng_n = Engine(EngineConfig.for_ranking(max_positions=10, min_dollar_volume=1e6, max_new_per_day=3))
    check("Tagesdeckel: hoechstens max_new_per_day neue Positionen je Tag (gestaffelte Kohorten)",
          len(eng_n.decide(snap, PortfolioState(cash=100_000, equity=100_000))) == 3)
    # Score-Quelle "ml": die Vorhersage IST der Rang - und ohne Spalte gibt es keine Kaeufe
    from alpaca_bot.signals import build_ranking_frame
    frames = {s: build_ranking_frame(df, spy, eng.cfg.ranking_weights) for s, df in bars.items()}
    ml_rang = {s: float(i) for i, s in enumerate(sorted(frames))}     # S119 bekommt den hoechsten Wert
    for s, fr in frames.items():
        fr["ml_score"] = ml_rang[s]
    snap_ml = MarketSnapshot(as_of=idx[-1], bars=bars, market=spy, signals=frames)
    eng_ml = Engine(EngineConfig.for_ranking(max_positions=10, min_dollar_volume=1e6, score_quelle="ml"))
    dec_ml = eng_ml.decide(snap_ml, PortfolioState(cash=100_000, equity=100_000))
    gekauft = {d.symbol for d in dec_ml}
    erwartet = set(sorted(frames)[-len(gekauft):]) if gekauft else set()
    check("Score-Quelle ml: Kaufliste folgt der Vorhersage, nicht dem Handmix",
          len(gekauft) > 0 and gekauft == erwartet, f"{len(gekauft)} Kaeufe")
    for fr in frames.values():
        fr["ml_score"] = float("nan")
    snap_leer = MarketSnapshot(as_of=idx[-1], bars=bars, market=spy, signals=frames)
    check("Score-Quelle ml ohne Vorhersagen: keine Kaeufe (sicherer Ausfall)",
          not eng_ml.decide(snap_leer, PortfolioState(cash=100_000, equity=100_000)))

    print("\n[14] Risiko-Dach (Drawdown-Sperre, Tagesverlust, Einzahlungen)")
    from alpaca_bot import risiko

    with tempfile.TemporaryDirectory() as tmp:
        import datetime as _dt
        d = risiko.RisikoDach(Path(tmp) / "state.sqlite")
        t0 = _dt.datetime(2026, 10, 1, 15, 0, tzinfo=_dt.UTC)
        d.pruefe_konto(100_000, ts=t0)
        f1 = d.pruefe_konto(94_000, ts=t0 + _dt.timedelta(hours=1))
        check("Tagesverlust > 5 % bremst neue Kaeufe, keine Vollsperre",
              not f1.ok and not f1.sperre_aktiv)
        f2 = d.pruefe_konto(79_000, ts=t0 + _dt.timedelta(days=2))
        check("Drawdown > 20 % setzt die persistente Vollsperre", not f2.ok and f2.sperre_aktiv)
        f3 = d.pruefe_konto(96_000, ts=t0 + _dt.timedelta(days=3))
        check("Erholung loest die Sperre nicht von selbst", f3.sperre_aktiv)
        d.sperre_loesen(risiko.BESTAETIGUNG)
        f4 = d.pruefe_konto(96_500, ts=t0 + _dt.timedelta(days=4))
        check("Sperre nur mit woertlicher Bestaetigung loesbar, Hoechststand neu", f4.ok)

    print("\n[15] Befundregister (Gedaechtnis: eintragen, laden, Urteil, Versuchszaehler)")
    from alpaca_bot import befunde

    with tempfile.TemporaryDirectory() as tmp:
        alt_register = befunde.REGISTER
        befunde.REGISTER = Path(tmp) / "befunde.jsonl"
        try:
            u1, _ = befunde.urteil_portfolio({"cagr": 0.10, "bench_cagr": 0.09, "univ_cagr": 0.08,
                                              "max_drawdown": -0.20, "bench_maxdd": -0.40})
            u2, _ = befunde.urteil_portfolio({"cagr": 0.02, "bench_cagr": 0.09, "univ_cagr": 0.08,
                                              "max_drawdown": -0.50, "bench_maxdd": -0.40})
            check("Urteil: CAGR >= SPY, DD <= 0,8 x SPY, >= Universum -> bestanden", u1 == "bestanden")
            check("Urteil: alles verfehlt -> verworfen", u2 == "verworfen")
            befunde.eintragen(skript="00", panel="test", variante="a", zeitraum="2020-2021",
                              parameter={"regime": "kein", "haltedauer": 21, "kosten_bps": 20.0, "top_n": 50},
                              kennzahlen={"cagr": 0.1, "bench_cagr": 0.09, "sharpe": float("nan")},
                              urteil=u1, lehre="Selbsttest")
            befunde.eintragen(skript="00", panel="test", variante="b", zeitraum="2020-2021",
                              parameter={"regime": "kein", "haltedauer": 21, "kosten_bps": 20.0, "top_n": 50},
                              kennzahlen={"cagr": 0.02, "bench_cagr": 0.09}, urteil=u2)
            df = befunde.laden()
            check("Register additiv, Kennzahlen/Parameter aufgefaltet, NaN -> null",
                  len(df) == 2 and "k_cagr" in df.columns and "p_haltedauer" in df.columns
                  and df["k_sharpe"].isna().all())
            vz = befunde.versuchszaehler()
            check("Versuchszaehler zaehlt Varianten und liefert Zufallsschwelle sqrt(2 ln N)+0,5",
                  vz["varianten"] == 2 and abs(vz["schwelle_sigma"] - 1.68) < 0.02)
            try:
                befunde.eintragen(skript="00", panel="t", variante="c", zeitraum="", parameter={},
                                  kennzahlen={}, urteil="super")
                check("Unbekanntes Urteil wird abgelehnt", False)
            except ValueError:
                check("Unbekanntes Urteil wird abgelehnt", True)
        finally:
            befunde.REGISTER = alt_register

    print("\n[16] Prognosemodell (LightGBM: gepflanztes Signal, Nulltest, Embargo, Speichern, Live-Signale)")
    from alpaca_bot import modell as _modell

    check("modell.selftest: Signal wird OOS gefunden, ohne Signal nichts, Embargo, Laden identisch",
          _modell.selftest(leise=True))
    _fak, _fwd, _maske = _modell._synthetisches_panel(n_sym=60, n_tage=700, signal=0.02, seed=3)
    _lang = _modell.merkmalstabelle(_fak, _maske, ziel=_fwd)
    _m = _modell.trainieren(_lang, ["m1", "m2", "rausch"], horizont=5,
                            parameter={**_modell.LGBM_PARAMETER, "n_estimators": 40})
    _m.merkmale = ["mom_konsistenz", "mom_12_1", "reversal_5d"]   # Zoo-Namen, damit signale_fuer_snapshot sie findet
    _sig = _modell.signale_fuer_snapshot(bars, spy, _m, min_preis=1.0, min_dollar_volume=1e6)
    check("signale_fuer_snapshot: ml_score nur in der letzten Zeile, fuer zugelassene Symbole",
          all("ml_score" in fr.columns for fr in _sig.values())
          and sum(fr["ml_score"].iloc[-1] == fr["ml_score"].iloc[-1] for fr in _sig.values()) >= 30
          and all(fr["ml_score"].iloc[:-1].isna().all() for fr in _sig.values()))

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
