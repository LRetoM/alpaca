"""Regressionstests fuer den Querschnitt-DQN (`rl/pooled.py`).

Der Lauf ist die letzte nicht ausgeschoepfte Lernvariante (BEFUNDE §G50).
Genau deshalb muss die Auswertung streng sein:

  * Das Bewertungsfenster liegt IMMER nach dem Trainingsfenster.
  * Der gepoolte Merkmals-Scaler kommt nur aus dem Trainingsfenster.
  * Ein einzelnes auswendig gelerntes Fenster (die SYRE-Lehre aus §G50)
    darf das Gesamturteil NICHT auf "Koennen" kippen - verlangt sind ein
    Median ueber Symbole UND ein Mindestanteil koennender Symbole.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from alpaca_bot.rl.dqn import DQNConfig
from alpaca_bot.rl.env import EnvConfig, RewardConfig
from alpaca_bot.rl.pooled import (
    PooledReport,
    PooledSymbolResult,
    _kalender,
    train_pooled_walk_forward,
)


# ---------------------------------------------------------------------------
def _reihe(n: int, seed: int, start: str = "2015-01-02"):
    rng = np.random.default_rng(seed)
    idx = pd.date_range(start, periods=n, freq="B", tz="UTC")
    ret = rng.normal(0.0003, 0.018, n)
    close = pd.Series(50.0 * np.cumprod(1 + ret), index=idx)
    feats = pd.DataFrame({
        "f_ret1": close.pct_change().fillna(0.0),
        "f_ret5": close.pct_change(5).fillna(0.0),
        "f_vol": close.pct_change().rolling(20).std().bfill().fillna(0.0),
        "f_rsi": rng.normal(0, 1, n),
    }, index=idx)
    return feats, close


def _row(sym: str, timing: float, agent: float, matched: float, fold: int = 1):
    return PooledSymbolResult(
        fold=fold, symbol=sym, test_from="2020-01-02", test_to="2021-01-02",
        agent_return=agent, matched_constant_return=matched,
        percentile_vs_random=50.0, avg_exposure=0.5,
        timing_percentile=timing, n_trades=10,
    )


class TestUrteilslogik:
    def test_rauschen_ergibt_kein_koennen(self):
        rep = PooledReport(symbol_rows=[
            _row(f"S{i}", timing=50 + (i % 5), agent=0.05, matched=0.05)
            for i in range(12)
        ])
        assert "KEIN nachweisbares" in rep.verdict()

    def test_breites_koennen_wird_erkannt(self):
        rep = PooledReport(symbol_rows=[
            _row(f"S{i}", timing=98.0, agent=0.20, matched=0.05)
            for i in range(12)
        ])
        v = rep.verdict()
        assert "NACHWEISBARES Timing-Koennen" in v

    def test_ein_auswendig_gelerntes_fenster_kippt_das_urteil_nicht(self):
        # 1 Symbol mit Perfekt-Timing und riesiger Rendite, 11 mit Rauschen.
        # Das ist der SYRE-Fall aus §G50 - das Gesamturteil muss KEIN bleiben.
        rows = [_row("GLUECK", timing=100.0, agent=32.0, matched=0.1)]
        rows += [_row(f"S{i}", timing=50.0, agent=0.02, matched=0.03)
                 for i in range(11)]
        rep = PooledReport(symbol_rows=rows)
        assert "KEIN nachweisbares" in rep.verdict()
        assert rep.overall_frac_skill() < 0.5
        assert rep.overall_median_timing() < 80

    def test_schwacher_hinweis_zwischenbereich(self):
        rep = PooledReport(symbol_rows=[
            _row(f"S{i}", timing=85.0, agent=0.1, matched=0.08)
            for i in range(10)
        ])
        assert "schwacher Hinweis" in rep.verdict()


class TestKalender:
    def test_union_ist_sortiert_und_vollstaendig(self):
        a = _reihe(100, seed=1, start="2015-01-02")
        b = _reihe(100, seed=2, start="2015-03-02")
        kal = _kalender({"A": a, "B": b})
        assert list(kal) == sorted(kal)
        assert set(kal) == set(a[0].index) | set(b[0].index)


class TestWalkForwardEndeZuEnde:
    @pytest.fixture
    def reihen(self):
        return {f"SYM{i}": _reihe(700, seed=10 + i) for i in range(5)}

    def test_bewertung_liegt_nach_dem_training(self, reihen):
        rep = train_pooled_walk_forward(
            reihen, n_folds=2, episodes_per_symbol_per_fold=1,
            min_train_frac=0.5, min_train_bars=200, min_test_bars=20,
            env_config=EnvConfig(reward=RewardConfig()),
            dqn_config=DQNConfig(warmup=40, batch_size=16, buffer_size=3000,
                                 eps_decay_steps=300),
            n_random=5, seed=0, verbose=False,
        )
        t = rep.table()
        assert not t.empty
        # Fenster 2 wird spaeter getestet als Fenster 1.
        f1 = t[t["fold"] == 1]["test_from"].min()
        f2 = t[t["fold"] == 2]["test_from"].min()
        assert f2 > f1
        # kein Test beginnt vor dem 45%-Punkt des gemeinsamen Kalenders
        kal = _kalender(reihen)
        frueheste_erlaubt = kal[int(len(kal) * 0.5)].date().isoformat()
        assert t["test_from"].min() >= frueheste_erlaubt

    def test_liefert_zeilen_je_symbol_und_ein_urteil(self, reihen):
        rep = train_pooled_walk_forward(
            reihen, n_folds=2, episodes_per_symbol_per_fold=1,
            min_train_frac=0.5, min_train_bars=200, min_test_bars=20,
            env_config=EnvConfig(),
            dqn_config=DQNConfig(warmup=40, batch_size=16, buffer_size=3000,
                                 eps_decay_steps=300),
            n_random=5, seed=1, verbose=False,
        )
        assert rep.fold_summaries
        assert set(rep.table()["symbol"]).issubset(set(reihen))
        assert isinstance(rep.verdict(), str) and len(rep.verdict()) > 50
        # Ohne echtes Signal darf das synthetische Ergebnis kein Koennen zeigen.
        assert "NACHWEISBARES Timing-Koennen" not in rep.verdict()
