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


def test_vorlauf_wartet_nicht_auf_unbenutzten_gleitenden_durchschnitt():
    """Regressionstest fuer den Vorfall vom 13.09.2026 (BEFUNDE §G93).

    `warmup` addierte `ma_tage` (200 Tage) fuer JEDE Strategie - obwohl
    nur `ma_filter` einen gleitenden Durchschnitt berechnet. dualmom
    wartete damit zehn Monate auf nichts, und der Backtest auf dem
    eigenen Vorrat begann im Februar 2022 statt im Fruehjahr 2021.
    """
    import numpy as np
    import pandas as pd
    from alpaca_bot import trend

    r = np.random.default_rng(1)
    idx = pd.bdate_range("2020-07-27", periods=700, tz="UTC")
    px = pd.DataFrame(
        {s: 100 * np.exp(np.cumsum(r.normal(0.0003, 0.01, 700)))
         for s in ("A", "B", "C", "D")}, index=idx)

    dm = trend.run(px, trend.TrendConfig(strategie="dualmom",
                                         lookback_monate=9, vol_ziel=0.10))
    ma = trend.run(px, trend.TrendConfig(strategie="ma_filter",
                                         ma_tage=200, vol_ziel=0.10))
    # dualmom braucht 9 Monate (~189 Tage) plus Puffer - keine 400.
    assert dm.equity_curve.index[0] < idx[260], (
        f"dualmom startet erst an Tag "
        f"{idx.get_loc(dm.equity_curve.index[0])} - wartet es auf ma_tage?")
    # ma_filter braucht die 200 Tage wirklich.
    assert ma.equity_curve.index[0] >= idx[200]


# --- Ensemble ueber Lookbacks und Tranchen-Versatz (13.09.2026) ---------

def _px(n=700, saat=2, k=6):
    import numpy as np
    import pandas as pd
    r = np.random.default_rng(saat)
    idx = pd.bdate_range("2020-07-27", periods=n, tz="UTC")
    return pd.DataFrame(
        {f"A{i}": 100 * np.exp(np.cumsum(r.normal(0.0003 * (i - 2), 0.01, n)))
         for i in range(k)}, index=idx)


def test_ohne_lookbacks_exakt_wie_vorher():
    """Das Ensemble darf das Standardverhalten nicht anfassen."""
    from alpaca_bot import trend
    px = _px()
    a = trend.run(px, trend.TrendConfig(strategie="dualmom", lookback_monate=9))
    b = trend.run(px, trend.TrendConfig(strategie="dualmom", lookback_monate=9,
                                        lookbacks=()))
    assert a.equity_curve.equals(b.equity_curve)


def test_ensemble_mittelt_die_gewichte():
    """Ein Asset, das nur bei einem von drei Horizonten qualifiziert,
    bekommt ein Drittel seines Gewichts - nicht alles, nicht nichts."""
    import pandas as pd
    from alpaca_bot import trend
    px = _px()
    ret = px.pct_change()
    bis = px.index[-1]
    cfg = trend.TrendConfig(strategie="dualmom", vol_ziel=0.0,
                            lookbacks=(6, 9, 12))
    ens = trend.ziel_gewichte(px, ret, bis, cfg)
    einzel = [trend.ziel_gewichte(px, ret, bis, trend.TrendConfig(
        strategie="dualmom", vol_ziel=0.0, lookback_monate=lb))
        for lb in (6, 9, 12)]
    alle = sorted(set().union(*(e.index for e in einzel)))
    erwartet = sum(e.reindex(alle).fillna(0.0) for e in einzel) / 3
    pd.testing.assert_series_equal(ens.reindex(alle).fillna(0.0), erwartet)


def test_ensemble_sieht_keine_zukunft():
    from alpaca_bot import trend
    px = _px()
    ret = px.pct_change()
    bis = px.index[400]
    cfg = trend.TrendConfig(strategie="dualmom", lookbacks=(6, 9, 12))
    vorher = trend.ziel_gewichte(px, ret, bis, cfg)
    px2 = px.copy(); px2.iloc[401:, 0] *= 3.0
    nachher = trend.ziel_gewichte(px2, px2.pct_change(), bis, cfg)
    assert vorher.equals(nachher)


def test_vorlauf_richtet_sich_nach_dem_laengsten_lookback():
    from alpaca_bot import trend
    px = _px(n=700)
    r = trend.run(px, trend.TrendConfig(strategie="dualmom", lookbacks=(6, 9, 12)))
    # 12 Monate ~ 252 Tage: vor Tag 250 darf nichts starten.
    assert r.equity_curve.index[0] >= px.index[250]


def test_versatz_verschiebt_die_termine_auf_handelstage():
    from alpaca_bot import trend
    px = _px()
    t0 = trend._rebalance_termine(px.index, "monatlich", 0)
    t7 = trend._rebalance_termine(px.index, "monatlich", 7)
    assert len(t7) >= len(t0) - 1
    assert all(t in px.index for t in t7), "Termine muessen Handelstage sein"
    # Jeder versetzte Termin liegt 7 Handelstage nach einem Monatsende.
    pos0 = set(px.index.searchsorted(t0))
    for t in t7:
        assert (px.index.searchsorted(t) - 7) in pos0


def test_tranchen_liefern_verschiedene_kurven():
    """Drei versetzte Laeufe sind drei verschiedene Depots - sonst waere
    das Mitteln sinnlos."""
    from alpaca_bot import trend
    px = _px()
    kurven = [trend.run(px, trend.TrendConfig(
        strategie="dualmom", lookback_monate=9, rebalance_versatz_tage=v))
        .equity_curve for v in (0, 7, 14)]
    assert not kurven[0].equals(kurven[1])
    assert not kurven[1].equals(kurven[2])


def test_unbrauchbarer_lookback_im_ensemble_wird_abgelehnt():
    import pytest
    from alpaca_bot import trend
    with pytest.raises(ValueError, match="lookbacks"):
        trend.TrendConfig(strategie="dualmom", skip_monate=1,
                          lookbacks=(1, 9)).pruefe()


# --- Cash-Verzinsung ueber eine echte Kursreihe (13.09.2026) -------------

def test_cash_symbol_taucht_nie_in_den_gewichten_auf():
    """Der Massstab fuer 'nicht investiert' ist kein Kandidat."""
    import numpy as np
    from alpaca_bot import trend
    px = _px(n=600, k=5)
    px["CASH"] = 100 * np.exp(np.linspace(0, 0.10, 600))   # steigt stetig
    r = trend.run(px, trend.TrendConfig(strategie="dualmom", lookback_monate=6,
                                        cash_symbol="CASH"))
    assert "CASH" not in r.weights.columns
    assert not (r.weights.get("CASH", 0) != 0).any() if "CASH" in r.weights else True


def test_cash_symbol_verzinst_den_cash_anteil():
    """Alles in Cash (kein Asset qualifiziert): die Equity folgt exakt der
    Cash-Reihe."""
    import numpy as np
    import pandas as pd
    from alpaca_bot import trend
    n = 500
    idx = pd.bdate_range("2021-01-04", periods=n, tz="UTC")
    fallend = 100 * np.exp(np.linspace(0, -0.5, n))       # nichts qualifiziert
    px = pd.DataFrame({f"A{i}": fallend * (1 + i * 0.01) for i in range(4)}, index=idx)
    px["CASH"] = 100 * np.exp(np.linspace(0, 0.08, n))
    r = trend.run(px, trend.TrendConfig(strategie="dualmom", lookback_monate=6,
                                        vol_ziel=0.0, cash_symbol="CASH",
                                        kosten_bps=0.0, slippage_bps=0.0))
    eq = r.equity_curve
    cash = px["CASH"].reindex(eq.index)
    erwartet = cash / cash.iloc[0] * eq.iloc[0]
    assert np.allclose(eq.values, erwartet.values, rtol=1e-6)


def test_fehlendes_cash_symbol_ist_ein_fehler():
    import pytest
    from alpaca_bot import trend
    px = _px(n=400)
    with pytest.raises(ValueError, match="cash_symbol"):
        trend.run(px, trend.TrendConfig(strategie="dualmom", cash_symbol="GIBTESNICHT"))


def test_ohne_cash_symbol_wie_vorher():
    from alpaca_bot import trend
    px = _px(n=500)
    a = trend.run(px, trend.TrendConfig(strategie="dualmom", lookback_monate=6))
    b = trend.run(px, trend.TrendConfig(strategie="dualmom", lookback_monate=6,
                                        cash_symbol=""))
    assert a.equity_curve.equals(b.equity_curve)


def test_huerde_folgt_der_cash_reihe():
    """Mit Cash-Reihe wird 'besser als Cash' an ihrem echten Ertrag
    gemessen. Eine stark steigende Cash-Reihe muss die Huerde heben und
    schwache Assets aussortieren."""
    import numpy as np
    import pandas as pd
    from alpaca_bot import trend
    n = 500
    idx = pd.bdate_range("2021-01-04", periods=n, tz="UTC")
    # Assets steigen 3 % im Jahr - ueber der 2-%-Pauschale, unter 8 % Cash.
    px = pd.DataFrame({f"A{i}": 100 * np.exp(np.linspace(0, 0.03 * n / 252, n))
                       for i in range(4)}, index=idx)
    cash = pd.Series(100 * np.exp(np.linspace(0, 0.08 * n / 252, n)), index=idx)
    ret = px.pct_change()
    bis = idx[-1]
    cfg = trend.TrendConfig(strategie="dualmom", lookback_monate=6, vol_ziel=0.0)
    ohne = trend.ziel_gewichte(px, ret, bis, cfg)
    mit = trend.ziel_gewichte(px, ret, bis, cfg, cash_kurse=cash)
    assert not ohne.empty, "gegen 2 % Pauschale qualifizieren die Assets"
    assert mit.empty, "gegen 8 % echten Cash-Ertrag qualifiziert nichts"


def test_depot_vol_ziel_nutzt_die_diversifikation():
    """Bei unkorrelierten Assets ist die Depotvola kleiner als jede
    Einzelvola - die Depot-Skalierung investiert deshalb MEHR als die
    Asset-Skalierung, um dasselbe Ziel zu treffen."""
    import numpy as np
    import pandas as pd
    from alpaca_bot import trend
    r = np.random.default_rng(8)
    n = 500
    idx = pd.bdate_range("2021-01-04", periods=n, tz="UTC")
    # Deutlich steigend, damit ALLE vier die Momentum-Huerde nehmen und
    # der Korb mehr als ein Asset hat - sonst gibt es nichts zu
    # diversifizieren, und die Depot-Skalierung greift korrekt nicht.
    px = pd.DataFrame({f"A{i}": 100 * np.exp(np.cumsum(r.normal(0.002, 0.012, n)))
                       for i in range(4)}, index=idx)
    ret = px.pct_change(); bis = idx[-1]
    for lauf in (trend.ziel_gewichte(px, ret, bis, trend.TrendConfig(
            strategie="dualmom", lookback_monate=6, vol_ziel=0.0)),):
        assert len(lauf) >= 2, "Testdaten muessen mehrere Assets qualifizieren"
    asset = trend.ziel_gewichte(px, ret, bis, trend.TrendConfig(
        strategie="dualmom", lookback_monate=6, vol_ziel=0.10, vol_ebene="asset",
        max_brutto=5.0))
    depot = trend.ziel_gewichte(px, ret, bis, trend.TrendConfig(
        strategie="dualmom", lookback_monate=6, vol_ziel=0.10, vol_ebene="depot",
        max_brutto=5.0))
    assert depot.sum() > asset.sum() * 1.2


def test_depot_vol_ziel_respektiert_den_deckel():
    import numpy as np
    import pandas as pd
    from alpaca_bot import trend
    r = np.random.default_rng(9)
    n = 500
    idx = pd.bdate_range("2021-01-04", periods=n, tz="UTC")
    px = pd.DataFrame({f"A{i}": 100 * np.exp(np.cumsum(r.normal(0.0008, 0.005, n)))
                       for i in range(4)}, index=idx)     # sehr ruhig -> will hebeln
    w = trend.ziel_gewichte(px, px.pct_change(), idx[-1], trend.TrendConfig(
        strategie="dualmom", lookback_monate=6, vol_ziel=0.10, vol_ebene="depot"))
    assert w.sum() <= 1.0 + 1e-9


def test_vol_ebene_asset_bleibt_wie_vorher():
    from alpaca_bot import trend
    px = _px(n=500)
    a = trend.run(px, trend.TrendConfig(strategie="dualmom", lookback_monate=6))
    b = trend.run(px, trend.TrendConfig(strategie="dualmom", lookback_monate=6,
                                        vol_ebene="asset"))
    assert a.equity_curve.equals(b.equity_curve)


def test_ziel_gewichte_nimmt_cash_symbol_selbst_aus_der_rangliste():
    """Regressionstest 13.09.2026: Ein direkter Aufrufer (der Schatten)
    uebergab die Kurse MIT Cash-ETF, und 'BIL49' stand in der Allokation
    von tsmom. Das waere die Kaufliste des Live-Bots gewesen."""
    import numpy as np
    import pandas as pd
    from alpaca_bot import trend
    px = _px(n=500, k=4)
    px["BIL"] = 100 * np.exp(np.linspace(0, 0.5, 500))   # steigt kraeftig - wuerde tsmom qualifizieren
    for strat in ("tsmom", "dualmom", "ma_filter", "gem", "risk_parity"):
        w = trend.ziel_gewichte(px, px.pct_change(), px.index[-1],
                                trend.TrendConfig(strategie=strat, lookback_monate=6,
                                                  cash_symbol="BIL"))
        assert "BIL" not in w.index, strat
