"""Regressionstests fuer den Jahresbot (`jahresbot.py`).

Jaehrliche querschnittliche Auswahl, ~1 Umschlag je Position und Jahr.
Die Mechanik muss sauber sein:

  * kein Lookahead in der Merkmalsfunktion und im Lauf
  * jaehrliches Rebalancing trifft die richtigen Termine
  * der Verlust-Stop greift gegen das Tagestief
  * Kosten fallen bei jedem Kauf/Verkauf an
  * "Gewinner laufen lassen" haelt einen noch platzierten Namen
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from alpaca_bot import jahresbot, pit


def _sym(n: int, start: float, drift: float, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    ret = rng.normal(drift, 0.018, n)
    close = start * np.cumprod(1 + ret)
    openp = close / (1 + rng.normal(0, 0.005, n))
    high = np.maximum(openp, close) * (1 + np.abs(rng.normal(0, 0.01, n)))
    low = np.minimum(openp, close) * (1 - np.abs(rng.normal(0, 0.01, n)))
    vol = rng.uniform(2e6, 4e6, n)
    idx = pd.date_range("2011-01-03", periods=n, freq="B", tz="UTC")
    return pd.DataFrame({"open": openp, "high": high, "low": low,
                         "close": close, "volume": vol}, index=idx)


def _bars(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    teile = []
    for s, d in frames.items():
        x = d.copy()
        x["symbol"] = s
        teile.append(x.set_index("symbol", append=True).reorder_levels([1, 0]))
    out = pd.concat(teile).sort_index()
    out.index = out.index.set_names(["symbol", "timestamp"])
    return out


def _universum(n_jahre: int = 13, n_syms: int = 30, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    n = n_jahre * 252
    frames = {"SPY": _sym(n, 100, 0.0003, 999)}
    for k in range(n_syms):
        frames[f"S{k:02d}"] = _sym(n, float(rng.uniform(10, 120)),
                                   float(rng.uniform(-0.0002, 0.0006)), 10 + k)
    return _bars(frames)


class TestKausalitaet:
    def test_merkmale_sind_kausal(self):
        d = _sym(2500, 50, 0.0003, 1)
        cfg = jahresbot.JahresConfig(signal="momentum_vola")
        a = pit.audit_feature_function(lambda x: jahresbot._merkmale(x, cfg), d, n_checks=5)
        assert a.clean, a.leaking_columns

    def test_lauf_unabhaengig_von_spaeteren_daten(self):
        bars = _universum(seed=2)
        alle = bars.index.get_level_values("timestamp").unique().sort_values()
        t_ende = str(alle[6 * 252].date())
        t_spaet = str(alle[9 * 252].date())
        cfg = jahresbot.JahresConfig(top_n=10, stop_pct=0.0)
        a = jahresbot.run(bars, cfg, end=t_ende)
        b = jahresbot.run(
            bars[bars.index.get_level_values("timestamp") <= alle[9 * 252 + 5]],
            cfg, end=t_ende)
        pd.testing.assert_series_equal(a.equity_curve, b.equity_curve)


class TestRebalance:
    def test_ein_rebalance_je_jahr(self):
        bars = _universum(n_jahre=13, seed=3)
        r = jahresbot.run(bars, jahresbot.JahresConfig(top_n=10, stop_pct=0.0))
        # Warmup schluckt ~1 Jahr -> ~11 Rebalances bei 13 Jahren Daten
        assert 9 <= r.rebalances <= 13
        assert not r.trades.empty


class TestStop:
    def test_verlust_stop_greift(self):
        n = 6 * 252
        idx = pd.date_range("2011-01-03", periods=n, freq="B", tz="UTC")
        # ein Gewinner (kommt in die Auswahl), der dann abstuerzt
        c = np.concatenate([np.linspace(20, 60, n // 2),
                            np.linspace(60, 20, n - n // 2)])
        absturz = pd.DataFrame({"open": c, "high": c * 1.01, "low": c * 0.985,
                                "close": c, "volume": np.full(n, 3e6)}, index=idx)
        stabil = _sym(n, 30, 0.00005, 5)
        bars = _bars({"SPY": _sym(n, 100, 0.0002, 7),
                      "CRASH": absturz, "RUHIG": stabil})
        cfg = jahresbot.JahresConfig(top_n=1, stop_pct=0.25, lookback_monate=6,
                                     gewinner_laufen_lassen=False)
        r = jahresbot.run(bars, cfg)
        assert "stop" in set(r.trades["exit_reason"]), r.trades["exit_reason"].tolist()


class TestKosten:
    def test_hoehere_kosten_senken_equity(self):
        bars = _universum(seed=4)
        billig = jahresbot.run(bars, jahresbot.JahresConfig(top_n=15, kosten_bps=0.0,
                                                            slippage_bps=0.0))
        teuer = jahresbot.run(bars, jahresbot.JahresConfig(top_n=15, kosten_bps=80.0,
                                                           slippage_bps=20.0))
        assert teuer.equity_curve.iloc[-1] < billig.equity_curve.iloc[-1]


class TestGewinnerLaufenLassen:
    def test_platzierter_name_wird_nicht_verkauft(self):
        # Zwei Namen mit dauerhaft starkem Momentum: sie bleiben Jahr fuer
        # Jahr in den Top - mit gewinner_laufen_lassen darf keiner davon
        # als "rebalance" verkauft werden.
        n = 13 * 252
        idx = pd.date_range("2011-01-03", periods=n, freq="B", tz="UTC")
        # ueberwaeltigend starker, rauschfreier Trend - kein verrauschter
        # Fueller kann den 12-Monats-Momentum-Wettlauf gewinnen.
        stark = pd.DataFrame({"open": 10 * 1.0018 ** np.arange(n)}, index=idx)
        for spalte in ("high", "low", "close"):
            stark[spalte] = stark["open"] * {"high": 1.005, "low": 0.997,
                                             "close": 1.0}[spalte]
        stark["volume"] = 3e6
        frames = {"SPY": _sym(n, 100, 0.0002, 1),
                  "A": stark.copy(), "B": stark.copy()}
        rng = np.random.default_rng(4)
        for k in range(10):
            # nahezu flache, ruhige Fueller (Tagesvola 0,3 %)
            c = 40 * np.cumprod(1 + rng.normal(0.0, 0.003, n))
            frames[f"F{k}"] = pd.DataFrame(
                {"open": c, "high": c * 1.003, "low": c * 0.997,
                 "close": c, "volume": np.full(n, 3e6)}, index=idx)
        bars = _bars(frames)
        r = jahresbot.run(bars, jahresbot.JahresConfig(
            top_n=3, lookback_monate=12, gewinner_laufen_lassen=True, stop_pct=0.0))
        reb_verkaeufe = r.trades[(r.trades["exit_reason"] == "rebalance")
                                 & (r.trades["symbol"].isin(["A", "B"]))]
        assert reb_verkaeufe.empty, "Starke Dauergewinner duerfen nicht rausrotiert werden."


class TestEndeZuEnde:
    def test_lauf_und_auswertung(self):
        bars = _universum(seed=6)
        r = jahresbot.run(bars, jahresbot.JahresConfig(signal="momentum", top_n=20))
        m = r.metrics()
        assert "cagr" in m and m["trades_pro_jahr"] < 60
        txt = jahresbot.auswerten(r, bars, n_varianten=18)
        assert "SURVIVORSHIP" in txt.upper() and "SPY" in txt
        wf = jahresbot.walk_forward(bars, jahresbot.JahresConfig(top_n=20))
        assert wf["n_jahre"] >= 3
