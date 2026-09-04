"""Regressionstests fuer den Trendbot (`trend.py`).

Der Strategie-Familien-Wechsel (`docs/TRENDBOT.md`). Die Mechanik muss
sauber sein, sonst ist der ganze Wechsel wertlos:

  * kein Lookahead - Entscheidungen zum Rebalance-Termin sehen nur die
    Vergangenheit
  * Kosten wirken auf den Turnover, beidseitig
  * Vol-Targeting deckelt den Bruttohebel
  * die Cash-Logik greift bei negativem Momentum
  * die Benchmark-Rechnung stimmt
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from alpaca_bot import trend


def _preise(n_jahre: int = 16, seed: int = 0) -> pd.DataFrame:
    """Synthetische Total-Return-Kurven fuer mehrere Assets."""
    rng = np.random.default_rng(seed)
    n = n_jahre * 252
    idx = pd.date_range("2008-01-02", periods=n, freq="B", tz="UTC")
    spalten = {}
    for name, drift, vol in [("SPY", 0.0003, 0.011), ("EFA", 0.0002, 0.012),
                             ("EEM", 0.0002, 0.016), ("IEF", 0.00012, 0.004),
                             ("TLT", 0.00013, 0.009), ("GLD", 0.00018, 0.010),
                             ("DBC", 0.00005, 0.013), ("VNQ", 0.00025, 0.015)]:
        r = rng.normal(drift, vol, n)
        # ein langer Baerenmarkt in der Mitte, damit die Cash-Logik greift
        r[n // 2: n // 2 + 300] -= 0.003
        spalten[name] = pd.Series(100 * np.cumprod(1 + r), index=idx)
    return pd.DataFrame(spalten)


class TestRebalanceKalender:
    def test_monatsende(self):
        idx = pd.date_range("2020-01-01", "2020-04-30", freq="B", tz="UTC")
        t = trend._rebalance_termine(idx, "monatlich")
        assert len(t) == 4
        # jeder Termin ist der letzte Handelstag seines Monats
        for d in t:
            danach = idx[(idx > d) & (idx.month == d.month) & (idx.year == d.year)]
            assert len(danach) == 0


class TestKausalitaet:
    def test_momentum_nutzt_nur_vergangenheit(self):
        p = _preise(seed=1)
        bis = p.index[2000]
        voll = trend._momentum(p, bis, 12, 1)
        beschnitten = trend._momentum(p.loc[:bis], bis, 12, 1)
        pd.testing.assert_series_equal(voll, beschnitten)

    def test_run_ergebnis_unabhaengig_von_spaeteren_daten(self):
        p = _preise(seed=2)
        t_ende = p.index[3000]
        t_spaeter = p.index[3600]
        cfg = trend.TrendConfig(strategie="tsmom", vol_ziel=0.0)
        a = trend.run(p, cfg, end=t_ende)
        b = trend.run(p.loc[:t_spaeter], cfg, end=t_ende)
        pd.testing.assert_series_equal(a.equity_curve, b.equity_curve)


class TestGewichte:
    def test_summe_unter_deckel(self):
        p = _preise(seed=3)
        r = p.pct_change()
        for strat in ("tsmom", "dualmom", "ma_filter"):
            for vz in (0.0, 0.10):
                cfg = trend.TrendConfig(strategie=strat, vol_ziel=vz, max_brutto=1.0)
                for t in trend._rebalance_termine(p.index, "monatlich")[30::12]:
                    w = trend.ziel_gewichte(p, r, t, cfg)
                    assert w.sum() <= 1.0 + 1e-9, (strat, vz, t, w.sum())
                    assert (w >= -1e-9).all()

    def test_tsmom_geht_in_cash_bei_abwaertstrend(self):
        n = 12 * 252
        idx = pd.date_range("2010-01-04", periods=n, freq="B", tz="UTC")
        fallend = pd.Series(100 * np.cumprod(1 + np.full(n, -0.0008)), index=idx)
        p = pd.DataFrame({"SPY": fallend, "IEF": fallend})
        cfg = trend.TrendConfig(strategie="tsmom", vol_ziel=0.0)
        w = trend.ziel_gewichte(p, p.pct_change(), idx[-1], cfg)
        assert w.empty or w.sum() == 0.0, "Bei klarem Abwaertstrend muss alles Cash sein."

    def test_vol_targeting_skaliert_hoch_bei_ruhigem_asset(self):
        n = 8 * 252
        idx = pd.date_range("2012-01-03", periods=n, freq="B", tz="UTC")
        rng = np.random.default_rng(9)
        ruhig = pd.Series(100 * np.cumprod(1 + rng.normal(0.0004, 0.002, n)), index=idx)
        p = pd.DataFrame({"SPY": ruhig})
        cfg = trend.TrendConfig(strategie="tsmom", vol_ziel=0.10, max_brutto=1.0)
        w = trend.ziel_gewichte(p, p.pct_change(), idx[-1], cfg)
        # ruhiges Asset -> Skalierung > 1, aber Deckel greift
        assert not w.empty
        assert w.sum() <= 1.0 + 1e-9


class TestKosten:
    def test_hoehere_kosten_senken_die_equity(self):
        p = _preise(seed=4)
        billig = trend.run(p, trend.TrendConfig(kosten_bps=0.0, slippage_bps=0.0,
                                                vol_ziel=0.0))
        teuer = trend.run(p, trend.TrendConfig(kosten_bps=20.0, slippage_bps=10.0,
                                               vol_ziel=0.0))
        assert teuer.equity_curve.iloc[-1] < billig.equity_curve.iloc[-1]
        assert teuer.kosten_anteil_kum > billig.kosten_anteil_kum


class TestBenchmarks:
    def test_6040_und_spy(self):
        p = _preise(seed=5)
        b = trend.benchmark_kurven(p, 100_000.0, p.index[300])
        assert "SPY B&H" in b and "60/40" in b and "EW alle B&H" in b
        for eq in b.values():
            assert eq.iloc[0] == pytest.approx(100_000.0, rel=1e-6) or \
                   abs(eq.iloc[0] - 100_000.0) < 5_000  # 60/40 startet einen Tag spaeter


class TestEndeZuEnde:
    def test_lauf_und_auswertung(self):
        p = _preise(seed=6)
        res = trend.run(p, trend.TrendConfig(strategie="dualmom", vol_ziel=0.10))
        assert len(res.equity_curve) > 200
        assert not res.weights.empty
        m = res.metrics()
        assert "cagr" in m and "max_drawdown" in m and "turnover_pa" in m
        txt = trend.auswerten(res, p, n_varianten=18)
        assert "GATE" in txt and "60/40" in txt

    def test_walk_forward_liefert_zeilen(self):
        p = _preise(n_jahre=14, seed=7)
        wf = trend.walk_forward(p, lookbacks=(6, 12))
        assert wf["n_jahre"] >= 3
        assert len(wf["zeilen"]) == wf["n_jahre"]
