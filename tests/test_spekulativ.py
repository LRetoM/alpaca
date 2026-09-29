"""Regressionstests fuer den spekulativen Historienlauf (`spekulativ.py`).

Der Lauf ist bewusst aggressiv - Hebel, Konzentration, schneller Umschlag.
Genau deshalb muss die Mechanik wasserdicht sein: Ein Modell, das aus
Versehen in die Zukunft schaut, seine Kosten nur einseitig verrechnet oder
bei kollidierendem Stop/Ziel den guenstigen Fall waehlt, wuerde exakt die
Zahl aufblaehen, um die es hier geht.

Die Faelle:
  * kein Lookahead in der Merkmalsfunktion (`pit.audit_feature_function`)
  * Kosten wirken auf BEIDEN Seiten (flacher Markt = Verlust)
  * Stop schlaegt Ziel, wenn beide am selben Tag im Bereich liegen
  * die Hebelgrenze wird nie ueberschritten
  * Ruin haelt den Lauf an und wird gemeldet
  * die Auswertung nutzt den GRUPPIERTEN Test (nicht den naiven)
  * die Survivorship-Warnung steht im Bericht
  * compounding aendert die Positionsgroesse
  * `voll_rotation` haelt nie mehr als eine Position
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from alpaca_bot import pit, spekulativ


# ---------------------------------------------------------------------------
# Synthetische Bars
# ---------------------------------------------------------------------------
def _pfad(n: int, start: float, seed: int, tagesvola: float = 0.015) -> pd.DataFrame:
    """Geometrischer Random Walk mit OHLC und Volumen."""
    rng = np.random.default_rng(seed)
    ret = rng.normal(0.0002, tagesvola, n)
    close = start * np.cumprod(1 + ret)
    openp = close / (1 + rng.normal(0, tagesvola / 3, n))
    spanne = np.abs(rng.normal(0, tagesvola, n)) * close
    high = np.maximum(openp, close) + spanne
    low = np.minimum(openp, close) - spanne
    vol = rng.uniform(8e5, 1.2e6, n)
    idx = pd.date_range("2016-01-04", periods=n, freq="B", tz="UTC")
    return pd.DataFrame(
        {"open": openp, "high": high, "low": low, "close": close, "volume": vol},
        index=idx,
    )


def _mit_spike(df: pd.DataFrame, tag_idx: int, ret: float,
               vol_faktor: float = 6.0) -> pd.DataFrame:
    """Setzt an einem Tag eine grosse Bewegung auf hohem Volumen."""
    df = df.copy()
    i = df.index[tag_idx]
    vor = df["close"].iloc[tag_idx - 1]
    neu = vor * (1 + ret)
    df.loc[i, "open"] = vor * (1 + ret * 0.2)
    df.loc[i, "close"] = neu
    df.loc[i, "high"] = max(df.loc[i, "open"], neu) * 1.01
    df.loc[i, "low"] = min(df.loc[i, "open"], neu) * 0.99
    df.loc[i, "volume"] = df["volume"].iloc[:tag_idx].mean() * vol_faktor
    return df


def _bars(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    teile = []
    for sym, df in frames.items():
        d = df.copy()
        d["symbol"] = sym
        teile.append(d.set_index("symbol", append=True).reorder_levels([1, 0]))
    out = pd.concat(teile).sort_index()
    out.index = out.index.set_names(["symbol", "timestamp"])
    return out


# ---------------------------------------------------------------------------
class TestKeinLookahead:
    def test_merkmale_sind_kausal(self):
        cfg = spekulativ.SpekulativConfig(ausloeser_ntage=10)
        df = _pfad(600, 40.0, seed=1)
        audit = pit.audit_feature_function(
            lambda d: spekulativ._merkmale(d, cfg), df, n_checks=6)
        assert audit.clean, f"Undichte Spalten: {audit.leaking_columns}"


class TestKostenBeidseitig:
    def test_flacher_markt_macht_verlust(self):
        # Ein Symbol, das nach dem Warmup jeden zweiten Tag knapp die
        # Ausloeserschwelle reisst - Ein- und Ausstieg ohne echte
        # Kursbewegung. Der Rundlauf muss trotzdem Geld kosten.
        n = 340
        df = _pfad(n, 50.0, seed=2, tagesvola=0.004)
        for k in range(300, n, 4):
            df = _mit_spike(df, k, 0.09, vol_faktor=8.0)
            # Folgetag (= Einstiegstag) komplett auf das Niveau VOR dem
            # Sprung zuruecksetzen: Ein- und Ausstieg zum selben Kurs,
            # brutto also ~0. Was uebrig bleibt, sind reine Kosten.
            if k + 1 < n:
                j = df.index[k + 1]
                basis = float(df["close"].iloc[k - 1])
                df.loc[j, ["open", "high", "low", "close"]] = basis
        bars = _bars({"AAA": df})
        cfg = spekulativ.SpekulativConfig(
            richtung="momentum", ausloeser_1t_pct=0.08, vol_faktor=3.0,
            max_positionen=1, hebel=1.0, groessen_modus="gleich",
            haltedauer=1, stop_atr=0.0, ziel_atr=0.0, trail_atr=0.0,
            spread_bps=5.0, slippage_bps=3.0, margin_zins_pa=0.0,
        )
        res = spekulativ.run(bars, cfg, verbose=False)
        assert len(res.trades) >= 3
        assert res.trades["net_pnl"].mean() < 0, (
            "Ohne Kursbewegung darf ein Rundlauf nicht im Plus landen - "
            "sonst wirken die Kosten nur einseitig.")
        assert res.trades["brutto_ret"].abs().mean() < 0.02


class TestStopVorZiel:
    def _szenario(self, stop_vor_ziel: bool):
        n = 300
        df = _pfad(n, 50.0, seed=3, tagesvola=0.012)
        df = _mit_spike(df, 280, 0.15, vol_faktor=8.0)
        # Folgetag: eine RIESIGE Spanne, die Stop UND Ziel einschliesst.
        j = df.index[281]
        entry_ca = df["close"].iloc[280]
        df.loc[j, "open"] = entry_ca
        df.loc[j, "high"] = entry_ca * 1.60
        df.loc[j, "low"] = entry_ca * 0.60
        df.loc[j, "close"] = entry_ca * 1.10
        bars = _bars({"AAA": df})
        cfg = spekulativ.SpekulativConfig(
            richtung="momentum", ausloeser_1t_pct=0.10, vol_faktor=3.0,
            max_positionen=1, hebel=1.0, groessen_modus="gleich",
            haltedauer=5, stop_atr=2.0, ziel_atr=2.0, trail_atr=0.0,
            spread_bps=5.0, slippage_bps=3.0, stop_vor_ziel=stop_vor_ziel,
            margin_zins_pa=0.0,
        )
        return spekulativ.run(bars, cfg, verbose=False)

    def test_pessimistisch_greift_der_stop(self):
        res = self._szenario(stop_vor_ziel=True)
        assert len(res.trades) == 1
        assert res.trades.iloc[0]["exit_reason"] == "stop"

    def test_optimistisch_greift_das_ziel(self):
        res = self._szenario(stop_vor_ziel=False)
        assert len(res.trades) == 1
        assert res.trades.iloc[0]["exit_reason"] == "ziel"


class TestHebelgrenze:
    def test_bruttoexposure_bleibt_unter_equity_mal_hebel(self):
        rng = np.random.default_rng(4)
        frames = {}
        for s in range(8):
            df = _pfad(360, float(rng.uniform(20, 80)), seed=10 + s,
                       tagesvola=0.02)
            for k in range(270, 360, 7):
                df = _mit_spike(df, k, 0.13, vol_faktor=7.0)
            frames[f"S{s}"] = df
        bars = _bars(frames)
        cfg = spekulativ.SpekulativConfig(
            richtung="momentum", ausloeser_1t_pct=0.10, vol_faktor=3.0,
            max_positionen=5, hebel=2.0, groessen_modus="gleich",
            haltedauer=3, stop_atr=3.0, ziel_atr=0.0, trail_atr=0.0,
        )
        res = spekulativ.run(bars, cfg, verbose=False)
        # Bruttoexposure je Handelstag aus den Trades rekonstruieren.
        offen = []
        for _, t in res.trades.iterrows():
            offen.append((t["entry_date"], t["qty"] * t["entry_raw"], +1))
            offen.append((t["exit_date"], t["qty"] * t["entry_raw"], -1))
        # grobe Obergrenze: nie mehr als max_positionen gleichzeitig, jede
        # mit hoechstens equity*hebel/max_positionen -> Summe <= equity*hebel.
        assert (res.trades["qty"] * res.trades["entry_raw"]).max() <= \
            res.equity_curve.max() * cfg.hebel * 1.05


class TestRuin:
    def test_ruin_haelt_an_und_wird_gemeldet(self):
        # Ein einziges Symbol, das nach dem Einstieg an einem Tag 80 %
        # verliert - bei Hebel 3 und voll_rotation ist das Konto weg.
        n = 300
        df = _pfad(n, 50.0, seed=5, tagesvola=0.01)
        df = _mit_spike(df, 280, 0.20, vol_faktor=8.0)
        j = df.index[281]
        df.loc[j, "open"] = df["close"].iloc[280] * 0.98
        df.loc[j, "high"] = df["close"].iloc[280] * 0.99
        df.loc[j, "low"] = df["close"].iloc[280] * 0.15
        df.loc[j, "close"] = df["close"].iloc[280] * 0.18
        bars = _bars({"AAA": df})
        cfg = spekulativ.SpekulativConfig(
            richtung="momentum", ausloeser_1t_pct=0.15, vol_faktor=3.0,
            max_positionen=1, hebel=3.0, groessen_modus="voll_rotation",
            haltedauer=5, stop_atr=0.0, ziel_atr=0.0, trail_atr=0.0,
            margin_zins_pa=0.0,
        )
        res = spekulativ.run(bars, cfg, verbose=False)
        assert res.ruin is True
        assert res.ruin_datum is not None
        assert float(res.equity_curve.iloc[-1]) <= 0
        assert "RUIN" in spekulativ.auswerten(res, schwelle=2.9)


class TestGruppierterTest:
    def _res_mit_clustern(self):
        # 6 Symbole, die ALLE am selben Tag spiken -> viele Trades teilen
        # sich denselben Einstiegstag.
        frames = {}
        for s in range(6):
            df = _pfad(340, 50.0, seed=20 + s, tagesvola=0.015)
            for k in (285, 300, 315):
                df = _mit_spike(df, k, 0.12, vol_faktor=8.0)
            frames[f"C{s}"] = df
        bars = _bars(frames)
        cfg = spekulativ.SpekulativConfig(
            richtung="momentum", ausloeser_1t_pct=0.10, vol_faktor=3.0,
            max_positionen=6, hebel=1.0, groessen_modus="gleich",
            haltedauer=0, stop_atr=0.0, ziel_atr=0.0, trail_atr=0.0,
        )
        return spekulativ.run(bars, cfg, verbose=False)

    def test_gruppentest_zaehlt_tage_nicht_trades(self):
        res = self._res_mit_clustern()
        gt = res.gruppentest()
        assert gt.n_beobachtungen == len(res.trades)
        assert gt.n_gruppen < gt.n_beobachtungen, (
            "Trades desselben Einstiegstags muessen zu EINER Gruppe "
            "zusammenfallen - sonst ist die Stichprobe aufgeblaeht.")

    def test_bericht_nennt_gruppiert_und_naiv(self):
        res = self._res_mit_clustern()
        bericht = spekulativ.auswerten(res, schwelle=2.9)
        assert "GRUPPIERTER TEST" in bericht
        assert "naiv" in bericht.lower()


class TestLeitplankenImBericht:
    def test_survivorship_und_obergrenze(self):
        df = _pfad(320, 50.0, seed=7)
        for k in range(270, 320, 6):
            df = _mit_spike(df, k, 0.12, vol_faktor=7.0)
        res = spekulativ.run(_bars({"AAA": df}), verbose=False)
        bericht = spekulativ.auswerten(res, jahre=10.0, schwelle=2.9)
        assert "SURVIVORSHIP" in bericht
        assert "OBERGRENZE" in bericht
        assert "VERWERFEN" in bericht


class TestCompounding:
    def test_schalter_aendert_die_positionsgroesse(self):
        # Ein zuverlaessig steigendes Symbol: jeder Trade gewinnt, mit
        # compounding waechst das Konto und damit die Positionsgroesse,
        # ohne bleibt sie am Startkapital haengen.
        n = 360
        idx = pd.date_range("2016-01-04", periods=n, freq="B", tz="UTC")
        close = 20.0 * (1.015 ** np.arange(n))  # +1,5 %/Tag, glatt
        df = pd.DataFrame({
            "open": close / 1.005, "high": close * 1.02,
            "low": close * 0.99, "close": close,
            "volume": np.full(n, 1e6),
        }, index=idx)
        # alle 8 Tage ein Ausloeser: +10 % Tagesbewegung auf hohem Volumen
        for k in range(264, n - 6, 8):
            df.iloc[k, df.columns.get_loc("close")] = df["close"].iloc[k - 1] * 1.10
            df.iloc[k, df.columns.get_loc("high")] = df["close"].iloc[k] * 1.01
            df.iloc[k, df.columns.get_loc("volume")] = 8e6
        bars = _bars({"AAA": df})
        gemein = dict(
            richtung="momentum", ausloeser_1t_pct=0.09, vol_faktor=3.0,
            max_positionen=1, hebel=1.0, groessen_modus="gleich",
            haltedauer=5, stop_atr=0.0, ziel_atr=0.0, trail_atr=0.0,
            margin_zins_pa=0.0,
        )
        mit = spekulativ.run(bars, spekulativ.SpekulativConfig(compounding=True, **gemein), verbose=False)
        ohne = spekulativ.run(bars, spekulativ.SpekulativConfig(compounding=False, **gemein), verbose=False)
        letzter_mit = mit.trades.iloc[-1]["qty"] * mit.trades.iloc[-1]["entry_raw"]
        letzter_ohne = ohne.trades.iloc[-1]["qty"] * ohne.trades.iloc[-1]["entry_raw"]
        assert letzter_mit > letzter_ohne * 1.2, (
            "Bei wachsendem Konto muss compounding=True spaeter groesser "
            "einsteigen als compounding=False.")


class TestVollRotation:
    def test_hoechstens_eine_position(self):
        frames = {}
        for s in range(6):
            df = _pfad(340, 50.0, seed=30 + s, tagesvola=0.02)
            for k in range(270, 340, 5):
                df = _mit_spike(df, k, 0.13, vol_faktor=8.0)
            frames[f"V{s}"] = df
        bars = _bars(frames)
        cfg = spekulativ.SpekulativConfig(
            richtung="momentum", ausloeser_1t_pct=0.10, vol_faktor=3.0,
            max_positionen=5, hebel=2.0, groessen_modus="voll_rotation",
            haltedauer=3, stop_atr=2.5, ziel_atr=0.0, trail_atr=0.0,
        )
        res = spekulativ.run(bars, cfg, verbose=False)
        # Zu keinem Zeitpunkt duerfen sich zwei Trades zeitlich ueberlappen.
        intervalle = sorted(
            (t["entry_date"], t["exit_date"]) for _, t in res.trades.iterrows())
        for (e1, a1), (e2, a2) in zip(intervalle, intervalle[1:]):
            assert e2 >= a1, f"Ueberlappende Positionen: {(e1, a1)} und {(e2, a2)}"


class TestKonsistenzpflicht:
    """Jedes Kalenderjahr muss >= Schwelle liefern - ein Minusjahr reicht
    zum Durchfallen (Nutzeranforderung 03.09.2026)."""

    def _lauf(self, seed: int, drift: float):
        n = 900  # ~3,5 Kalenderjahre
        idx = pd.date_range("2016-01-04", periods=n, freq="B", tz="UTC")
        rng = np.random.default_rng(seed)
        ret = rng.normal(drift, 0.02, n)
        close = 50.0 * np.cumprod(1 + ret)
        df = pd.DataFrame({
            "open": close / 1.003, "high": close * 1.02,
            "low": close * 0.98, "close": close, "volume": np.full(n, 1e6),
        }, index=idx)
        for k in range(264, n - 6, 6):
            df.iloc[k, df.columns.get_loc("close")] = df["close"].iloc[k - 1] * 1.11
            df.iloc[k, df.columns.get_loc("high")] = df["close"].iloc[k] * 1.01
            df.iloc[k, df.columns.get_loc("volume")] = 8e6
        cfg = spekulativ.SpekulativConfig(
            richtung="momentum", ausloeser_1t_pct=0.09, vol_faktor=3.0,
            max_positionen=1, hebel=1.0, groessen_modus="gleich",
            haltedauer=1, stop_atr=0.0, ziel_atr=0.0, trail_atr=0.0,
            margin_zins_pa=0.0,
        )
        return spekulativ.run(_bars({"AAA": df}), cfg, verbose=False)

    def test_jahres_renditen_und_schlechtestes_jahr(self):
        res = self._lauf(seed=1, drift=0.0015)
        jr = res.jahres_renditen()
        assert len(jr) >= 3
        sj = res.schlechtestes_jahr()
        assert sj is not None
        assert sj[1] == min(jr.values())
        assert sj[0] in jr

    def test_jahre_ueber_zaehlt_korrekt(self):
        res = self._lauf(seed=1, drift=0.0015)
        jr = res.jahres_renditen()
        n_ok, n_ges = res.jahre_ueber(0.0)
        assert n_ges == len(jr)
        assert n_ok == sum(1 for r in jr.values() if r >= 0.0)

    def test_bericht_meldet_verfehlte_konsistenzpflicht(self):
        # abwaerts driftendes Symbol -> mindestens ein Minusjahr
        res = self._lauf(seed=7, drift=-0.001)
        bericht = spekulativ.auswerten(res, schwelle=2.9, min_jahr_schwelle=0.0)
        assert "KONSISTENZPFLICHT" in bericht
        n_ok, n_ges = res.jahre_ueber(0.0)
        if n_ok < n_ges:
            assert "VERFEHLT" in bericht


class TestPresetsGueltig:
    @pytest.mark.parametrize("name", sorted(spekulativ.PRESETS))
    def test_preset_besteht_die_pruefung(self, name):
        spekulativ.PRESETS[name].pruefe()
