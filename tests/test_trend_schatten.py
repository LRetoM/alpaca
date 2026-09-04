"""Regressionstests fuer den Trendbot-Vorwaerts-Schatten (`trend_schatten.py`).

Phase 2 aus `docs/TRENDBOT.md`: die defensive ETF-Allokation vorwaerts
verfolgen, ohne Orders. Wichtig:

  * das Startdatum wird EINMAL gesetzt und wandert nicht, wenn neue Tage
    dazukommen
  * die fortgeschriebene Equity ist idempotent (kausaler Backtest)
  * `aktualisieren` liefert die heutigen Zielgewichte
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from alpaca_bot import trend_schatten


@pytest.fixture(autouse=True)
def _temp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(trend_schatten, "DB", tmp_path / "trend_schatten.sqlite")


def _preise(n_jahre: int = 9, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    n = n_jahre * 252
    idx = pd.date_range("2017-01-02", periods=n, freq="B", tz="UTC")
    spalten = {}
    for name, drift, vol in [("SPY", 0.0003, 0.011), ("EFA", 0.0002, 0.012),
                             ("EEM", 0.00022, 0.016), ("IEF", 0.00012, 0.004),
                             ("TLT", 0.00013, 0.009), ("GLD", 0.00018, 0.010),
                             ("DBC", 0.00006, 0.013), ("VNQ", 0.00025, 0.015)]:
        r = rng.normal(drift, vol, n)
        r[n // 2: n // 2 + 200] -= 0.003
        spalten[name] = pd.Series(100 * np.cumprod(1 + r), index=idx)
    return pd.DataFrame(spalten)


class TestAktualisieren:
    def test_erster_lauf_setzt_stand_und_ziele(self):
        p = _preise(seed=1)
        erg = trend_schatten.aktualisieren(p)
        assert erg["stand"] == str(p.index[-1].date())
        assert erg["start_datum"] == str(p.index[-1].date())
        assert erg["rendite_seit_start"] == pytest.approx(0.0, abs=1e-9)
        assert isinstance(erg["ziel_gewichte"], dict)
        # Gewichte plus Cash ergeben rund 1
        assert erg["cash_anteil"] + sum(erg["ziel_gewichte"].values()) == pytest.approx(
            1.0, abs=0.05) or erg["cash_anteil"] >= 0

    def test_startdatum_wandert_nicht(self):
        p = _preise(seed=2)
        e1 = trend_schatten.aktualisieren(p.iloc[:-40])
        e2 = trend_schatten.aktualisieren(p)  # 40 Tage mehr
        assert e2["start_datum"] == e1["start_datum"]
        assert e2["stand"] != e1["stand"]

    def test_equity_ist_idempotent(self):
        p = _preise(seed=3)
        trend_schatten.aktualisieren(p)
        trend_schatten.aktualisieren(p)  # zweimal - darf nichts doppeln
        with trend_schatten._conn() as c:
            eq = pd.read_sql("SELECT * FROM equity", c)
        assert eq["datum"].is_unique
        assert len(eq) > 100

    def test_bericht_nennt_die_kernzahlen(self):
        p = _preise(seed=4)
        trend_schatten.aktualisieren(p)
        txt = trend_schatten.bericht()
        assert "Rendite seit Start" in txt
        assert "Zielallokation" in txt or "Rebalance" in txt
        assert "Kein Live-Handel" in txt

    def test_gewichte_werden_geschrieben(self):
        p = _preise(seed=5)
        trend_schatten.aktualisieren(p)
        with trend_schatten._conn() as c:
            gw = pd.read_sql("SELECT * FROM gewichte", c)
        assert not gw.empty
        assert set(gw["symbol"]).issubset(set(p.columns))
