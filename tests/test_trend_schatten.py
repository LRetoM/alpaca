"""Regressionstests fuer den Trendbot-Vorwaerts-Schatten (`trend_schatten.py`).

Phase 2 aus `docs/TRENDBOT.md`: mehrere defensive ETF-Allokationen
parallel vorwaerts verfolgen, ohne Orders. Wichtig:

  * das Startdatum wird EINMAL gesetzt und wandert nicht
  * jede Strategie startet mit Rendite 0 (heutiger Stand = Nulllinie)
  * die fortgeschriebene Equity ist idempotent
  * `aktualisieren` liefert je Strategie die heutigen Zielgewichte
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from alpaca_bot import trend, trend_schatten


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
    # Cash-ETF (§G96): ruhig, leicht steigend - verzinst den Cash-Anteil.
    spalten["BIL"] = pd.Series(100 * np.exp(np.linspace(0, 0.03 * n_jahre, n)),
                               index=idx)
    return pd.DataFrame(spalten)


class TestAktualisieren:
    def test_erster_lauf_alle_kandidaten_bei_null(self):
        p = _preise(seed=1)
        erg = trend_schatten.aktualisieren(p)
        assert set(erg["kandidaten"]) == set(trend_schatten.PHASE2_KANDIDATEN)
        for name, snap in erg["kandidaten"].items():
            assert "fehler" not in snap, (name, snap)
            assert snap["rendite_seit_start"] == pytest.approx(0.0, abs=1e-9)
            assert isinstance(snap["ziel_gewichte"], dict)
        # rueckwaertskompatible Felder oben (primaerer Kandidat)
        assert "ziel_gewichte" in erg and "rendite_seit_start" in erg

    def test_startdatum_wandert_nicht(self):
        p = _preise(seed=2)
        e1 = trend_schatten.aktualisieren(p.iloc[:-40])
        e2 = trend_schatten.aktualisieren(p)
        assert e2["start_datum"] == e1["start_datum"]
        assert e2["stand"] != e1["stand"]

    def test_equity_ist_idempotent(self):
        p = _preise(seed=3)
        trend_schatten.aktualisieren(p)
        trend_schatten.aktualisieren(p)
        with trend_schatten._conn() as c:
            eq = pd.read_sql("SELECT * FROM equity", c)
        assert not eq.duplicated(subset=["strategie", "datum"]).any()
        assert eq["strategie"].nunique() == len(trend_schatten.PHASE2_KANDIDATEN)

    def test_bericht_zeigt_das_rennen(self):
        p = _preise(seed=4)
        trend_schatten.aktualisieren(p)
        txt = trend_schatten.bericht()
        assert "Pferderennen" in txt
        assert "dualmom" in txt and "risk_parity" in txt
        assert "Kein Live-Handel" in txt

    def test_gewichte_werden_je_strategie_geschrieben(self):
        p = _preise(seed=5)
        trend_schatten.aktualisieren(p)
        with trend_schatten._conn() as c:
            gw = pd.read_sql("SELECT * FROM gewichte", c)
        assert not gw.empty
        assert gw["strategie"].nunique() >= 4
        assert set(gw["symbol"]).issubset(set(p.columns))


class TestNeueStrategien:
    def test_risk_parity_ist_immer_investiert(self):
        p = _preise(seed=6)
        r = p.pct_change()
        cfg = trend.TrendConfig(strategie="risk_parity", vol_fenster_tage=60)
        w = trend.ziel_gewichte(p, r, p.index[-1], cfg)
        assert len(w) >= 4
        assert w.sum() == pytest.approx(1.0, abs=1e-6)

    def test_gem_haelt_hoechstens_ein_asset(self):
        p = _preise(seed=7)
        r = p.pct_change()
        cfg = trend.TrendConfig(strategie="gem", lookback_monate=12, vol_ziel=0.0)
        w = trend.ziel_gewichte(p, r, p.index[-1], cfg)
        assert len(w) <= 1

    @pytest.mark.parametrize("strat", ["gem", "risk_parity"])
    def test_neue_strategien_bestehen_pruefung(self, strat):
        trend.TrendConfig(strategie=strat).pruefe()



# --- Startdatum je Strategie, BIL-Rueckfall (13.09.2026) -----------------

class TestStartdatumJeStrategie:
    def test_nachzuegler_startet_nicht_rueckwirkend(self):
        """Ein spaeter hinzugefuegter Kandidat bekommt den Tag seines
        ersten Laufs als Start - nie den Rennstart. Sonst waere sein
        'Vorwaerts' zum Teil rueckwaerts."""
        px = _preise()
        erste = {k: v for k, v in trend_schatten.PHASE2_KANDIDATEN.items()
                 if k in ("dualmom", "tsmom")}
        e1 = trend_schatten.aktualisieren(px.iloc[:-30], erste)
        alle = dict(erste)
        alle["gem_15"] = trend_schatten.PHASE2_KANDIDATEN["gem_15"]
        e2 = trend_schatten.aktualisieren(px, alle)
        assert e2["start_datum"] == e1["start_datum"], "Rennstart wandert nicht"
        assert e2["kandidaten"]["gem_15"]["start_datum"] == str(px.index[-1].date())
        assert e2["kandidaten"]["dualmom"]["start_datum"] == e1["start_datum"]
        # Der Nachzuegler startet bei null - nicht mit 30 Tagen Vorsprung.
        assert abs(e2["kandidaten"]["gem_15"]["rendite_seit_start"]) < 1e-9

    def test_nulllinie_kommt_aus_der_kurve(self):
        """Aendert sich die Verbuchung, darf kein Sprung entstehen: Stand
        heute und Stand am Start stammen aus derselben Rechnung."""
        px = _preise()
        k = {"dualmom": trend_schatten.PHASE2_KANDIDATEN["dualmom"]}
        trend_schatten.aktualisieren(px.iloc[:-40], k)
        # Zweiter Lauf mit ANDERER Cash-Verbuchung (Pauschale statt BIL).
        from dataclasses import replace
        k2 = {"dualmom": replace(k["dualmom"], cash_symbol="")}
        e = trend_schatten.aktualisieren(px, k2)
        snap = e["kandidaten"]["dualmom"]
        # Nachrechnen aus der frisch berechneten Kurve:
        eq = trend.run(px, k2["dualmom"]).equity_curve
        sd = pd.Timestamp(snap["start_datum"], tz=eq.index.tz)
        erwartet = float(eq.iloc[-1] / eq.asof(sd) - 1)
        assert snap["rendite_seit_start"] == pytest.approx(erwartet, abs=1e-12)

    def test_fehlendes_bil_faellt_sichtbar_zurueck(self):
        """Fehlt der Cash-ETF, laeuft der Schatten weiter - aber der
        Snapshot sagt es. Ein stiller Rueckfall waere ein Messfehler."""
        px = _preise().drop(columns=["BIL"])
        e = trend_schatten.aktualisieren(px, {"dualmom_15": trend_schatten.PHASE2_CONFIG})
        snap = e["kandidaten"]["dualmom_15"]
        assert "fehler" not in snap
        assert "FEHLT" in snap["cash_quelle"]

    def test_mit_bil_ist_die_cash_quelle_bil(self):
        e = trend_schatten.aktualisieren(_preise(), {"dualmom_15": trend_schatten.PHASE2_CONFIG})
        assert e["kandidaten"]["dualmom_15"]["cash_quelle"] == "BIL"

    def test_primaer_ist_dualmom_15(self):
        assert trend_schatten.PHASE2_KANDIDATEN["dualmom_15"] is trend_schatten.PHASE2_CONFIG
        assert trend_schatten.PHASE2_CONFIG.vol_ziel == pytest.approx(0.15)
        assert trend_schatten.PHASE2_CONFIG.cash_symbol == "BIL"
        assert all(c.cash_symbol == "BIL" for c in trend_schatten.PHASE2_KANDIDATEN.values())


def test_nachzuegler_hat_am_ersten_tag_exakt_null_rendite():
    """Regressionstest 13.09.2026: 0,17 % am ersten Tag war ein
    Zeitzonen-Off-by-one - asof(Mitternacht) griff den Vortag."""
    px = _preise()
    e = trend_schatten.aktualisieren(px, {"gem_15": trend_schatten.PHASE2_KANDIDATEN["gem_15"]})
    assert e["kandidaten"]["gem_15"]["rendite_seit_start"] == 0.0


def test_cash_etf_steht_nie_in_den_zielgewichten():
    e = trend_schatten.aktualisieren(_preise())
    for name, snap in e["kandidaten"].items():
        assert "BIL" not in snap["ziel_gewichte"], name
