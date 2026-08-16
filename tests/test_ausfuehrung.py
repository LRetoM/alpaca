"""Referenzpreis, Statistik, Nachbetrachtung - die Auswertungsschicht.

Ein falscher Referenzpreis macht die Slippage-Messung unbrauchbar, und
eine falsch gerechnete Statistik macht aus Rauschen einen Befund. Beides
ist gefaehrlicher als ein Handelsfehler: Es fuehrt zu FALSCHEN
ENTSCHEIDUNGEN mit echtem Geld, ohne dass eine Zahl auffaellig wird.
"""

from __future__ import annotations

from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest


# ------------------------------------------------------------ Referenzpreis
class TestReferenzpreis:
    """REGRESSION-Sammlung: An dieser Funktion hingen drei Fehler."""

    def _quote(self, bid, ask):
        return pd.DataFrame({"bid": [bid], "ask": [ask]}, index=["X"])

    def _snap(self, last):
        return pd.DataFrame({"last": [last]}, index=["X"])

    def test_kauf_nimmt_briefkurs(self):
        from alpaca_bot import live

        with patch.object(live.data, "latest_quotes",
                          return_value=self._quote(99.0, 101.0)), \
             patch.object(live.data, "snapshots", return_value=self._snap(100.0)):
            r = live._reference_price("X", "buy", fallback=0.0)
        assert r.preis == 101.0 and r.quelle == "quote"

    def test_verkauf_nimmt_geldkurs(self):
        from alpaca_bot import live

        with patch.object(live.data, "latest_quotes",
                          return_value=self._quote(99.0, 101.0)), \
             patch.object(live.data, "snapshots", return_value=self._snap(100.0)):
            r = live._reference_price("X", "sell", fallback=0.0)
        assert r.preis == 99.0

    def test_fehlende_seite_kein_scheinmittelwert(self):
        """REGRESSION (31.07.2026): Der Mittelwert aus echter und
        fehlender Seite ergab (0+45,54)/2 = 22,77 - eine Verfaelschung um
        50 %, die einen Kurssturz meldete, der nie stattfand."""
        from alpaca_bot import live

        with patch.object(live.data, "latest_quotes",
                          return_value=self._quote(45.54, 0.0)), \
             patch.object(live.data, "snapshots", return_value=self._snap(45.5)):
            r = live._reference_price("X", "buy", fallback=0.0)
        assert r.preis == pytest.approx(45.54), "muss die vorhandene Seite nehmen"

    def test_unplausible_quote_wird_verworfen(self):
        """REGRESSION (04.08.2026): SIMO wurde mit Quote 225 gemeldet,
        waehrend echte Trades bei 261-262 liefen. Ein Stop-Verkauf auf so
        einen Wert waere ein realer Verlust aus einem Datenfehler."""
        from alpaca_bot import live

        with patch.object(live.data, "latest_quotes",
                          return_value=self._quote(225.0, 225.5)), \
             patch.object(live.data, "snapshots", return_value=self._snap(261.0)):
            r = live._reference_price("X", "sell", fallback=0.0)
        assert r.quelle == "quote_verworfen"
        assert r.preis == pytest.approx(261.0), "letzter echter Trade gilt"

    def test_kleine_abweichung_bleibt_gueltig(self):
        """Die Schwelle wurde am 15.08. von 5 % auf 2 % verschaerft, weil
        acht Ausreisser mit 2,1-4,9 % durchgerutscht waren."""
        from alpaca_bot import live

        with patch.object(live.data, "latest_quotes",
                          return_value=self._quote(100.5, 101.0)), \
             patch.object(live.data, "snapshots", return_value=self._snap(100.0)):
            r = live._reference_price("X", "sell", fallback=0.0)
        assert r.quelle == "quote"

    def test_schwelle_ist_zwei_prozent(self):
        from alpaca_bot.live import _MAX_QUOTE_ABWEICHUNG

        assert _MAX_QUOTE_ABWEICHUNG == pytest.approx(0.02)

    def test_ohne_quote_fallback(self):
        from alpaca_bot import live

        with patch.object(live.data, "latest_quotes",
                          side_effect=RuntimeError("API weg")):
            r = live._reference_price("X", "buy", fallback=77.0)
        assert r.preis == 77.0 and r.quelle == "fallback"


class TestIntradayStop:
    """Der Stop darf NIE auf einer unzuverlaessigen Quote feuern - sonst
    verkauft ein Datenfehler eine gesunde Position."""

    def _lauf(self, refs, positionen, stops, tmp_path):
        from alpaca_bot import live
        from alpaca_bot.journal import Journal

        class S:
            def load_positions(self): return stops
            def record_exit(self, *a, **k): pass
            def drop_position(self, *a, **k): pass

        with patch.object(live.account, "positions", return_value=positionen), \
             patch("alpaca_bot.state.Store", S), \
             patch.object(live, "Journal",
                          lambda *a, **k: Journal(tmp_path / "j.sqlite")), \
             patch.object(live, "_reference_price",
                          side_effect=lambda s, side, fallback: refs[s]):
            return live.pruefe_stops_intraday(dry_run=True, verbose=False)

    def test_ueber_stop_wird_gehalten(self, tmp_path):
        from alpaca_bot.live import Referenzpreis

        pos = pd.DataFrame({"qty": [10.], "avg_entry": [100.]}, index=["A"])
        v = self._lauf({"A": Referenzpreis(95.0, "quote")}, pos,
                       {"A": {"stop_price": 90.0, "entry_price": 100.0}},
                       tmp_path)
        assert v == []

    def test_unter_stop_wird_verkauft(self, tmp_path):
        from alpaca_bot.live import Referenzpreis

        pos = pd.DataFrame({"qty": [10.], "avg_entry": [100.]}, index=["A"])
        v = self._lauf({"A": Referenzpreis(78.0, "quote")}, pos,
                       {"A": {"stop_price": 90.0, "entry_price": 100.0}},
                       tmp_path)
        assert v == ["A"]

    def test_fallback_quote_loest_nicht_aus(self, tmp_path):
        """Der entscheidende Schutz: Lieber gar nicht handeln als auf
        einen Datenfehler hin verkaufen."""
        from alpaca_bot.live import Referenzpreis

        pos = pd.DataFrame({"qty": [10.], "avg_entry": [100.]}, index=["A"])
        v = self._lauf({"A": Referenzpreis(50.0, "fallback")}, pos,
                       {"A": {"stop_price": 90.0, "entry_price": 100.0}},
                       tmp_path)
        assert v == [], "Fallback-Quote darf keinen Verkauf ausloesen"


# ---------------------------------------------------------------- Statistik
class TestGruppierterTest:
    """REGRESSION (15.08.2026): Dieselben Daten ergaben naiv t=2,63
    (scheinbar belastbar) und tagesgeclustert t=1,45 (Rauschen).
    Massgeblich ist die Zahl der GRUPPEN, nie die der Einzelwerte."""

    def test_gruppen_zaehlen_nicht_einzelwerte(self):
        from alpaca_bot.statistik import gruppierter_test

        # 300 Werte, aber nur 3 Tage: pro Tag identisch -> 3 Beobachtungen
        werte = pd.Series([0.02] * 100 + [0.01] * 100 + [-0.01] * 100)
        tage = pd.Series(["A"] * 100 + ["B"] * 100 + ["C"] * 100)
        r = gruppierter_test(werte, tage)
        assert r.n_beobachtungen == 300
        assert r.n_gruppen == 3
        assert not r.belastbar, "3 Gruppen sind nie belastbar"

    def test_naiver_wert_wird_mitgeliefert(self):
        """Nur wenn beide nebeneinander stehen, faellt der Unterschied auf."""
        from alpaca_bot.statistik import gruppierter_test

        rng = np.random.default_rng(0)
        werte = pd.Series(rng.normal(0.01, 0.05, 500))
        tage = pd.Series([f"T{i // 25}" for i in range(500)])
        r = gruppierter_test(werte, tage)
        assert np.isfinite(r.t_naiv) and np.isfinite(r.t)

    def test_wenige_gruppen_nie_belastbar(self):
        """Ein hoher t-Wert aus fuenf Gruppen ist genauso wenig belastbar
        wie ein niedriger aus hundert."""
        from alpaca_bot.statistik import gruppierter_test

        werte = pd.Series([0.05, 0.051, 0.049, 0.05, 0.0505])
        tage = pd.Series(["A", "B", "C", "D", "E"])
        r = gruppierter_test(werte, tage)
        assert abs(r.t) > 2, "t ist rechnerisch hoch"
        assert not r.belastbar, "aber 5 Gruppen reichen nie"

    def test_genug_gruppen_und_effekt_ist_belastbar(self):
        from alpaca_bot.statistik import gruppierter_test

        rng = np.random.default_rng(1)
        mittel = rng.normal(0.03, 0.01, 30)
        werte = pd.Series(np.repeat(mittel, 5))
        tage = pd.Series(np.repeat([f"T{i}" for i in range(30)], 5))
        r = gruppierter_test(werte, tage)
        assert r.n_gruppen == 30 and r.belastbar

    def test_noetige_gruppen_rechnung(self):
        from alpaca_bot.statistik import noetige_gruppen

        assert noetige_gruppen(effekt=0.01, streuung=0.05, t_ziel=2.0) == 100


# ----------------------------------------------------------- Nachbetrachtung
class TestWiedereinstiege:
    """Wiedereinstieg und Nachkauf sehen im Orderbuch gleich aus - beide
    sind eine weitere 'buy'-Zeile. Wer sie vermengt, zaehlt 50 Nachkaeufe
    als 50 Fehlentscheidungen."""

    def _orders(self, zeilen):
        return pd.DataFrame(zeilen)

    def test_nachkauf_ist_kein_wiedereinstieg(self):
        from alpaca_bot.nachbetrachtung import wiedereinstiege

        o = self._orders([
            {"ts": "2026-01-05T14:00:00+00:00", "symbol": "X", "side": "buy",
             "fill_price": 100.0},
            {"ts": "2026-01-06T14:00:00+00:00", "symbol": "X", "side": "buy",
             "fill_price": 102.0},  # Nachkauf, Position blieb offen
        ])
        assert wiedereinstiege(o).empty

    def test_echter_wiedereinstieg_wird_erkannt(self):
        from alpaca_bot.nachbetrachtung import wiedereinstiege

        o = self._orders([
            {"ts": "2026-01-05T14:00:00+00:00", "symbol": "X", "side": "buy",
             "fill_price": 100.0},
            {"ts": "2026-01-06T14:00:00+00:00", "symbol": "X", "side": "sell",
             "fill_price": 105.0},
            {"ts": "2026-01-12T14:00:00+00:00", "symbol": "X", "side": "buy",
             "fill_price": 108.0},
        ])
        w = wiedereinstiege(o)
        assert len(w) == 1
        assert w.iloc[0]["zwischenkosten_pct"] == pytest.approx(108 / 105 - 1)

    def test_sperrfristverletzung_wird_markiert(self):
        from alpaca_bot.nachbetrachtung import wiedereinstiege

        o = self._orders([
            {"ts": "2026-01-05T14:00:00+00:00", "symbol": "X", "side": "buy",
             "fill_price": 100.0},
            {"ts": "2026-01-05T15:00:00+00:00", "symbol": "X", "side": "sell",
             "fill_price": 105.0},
            {"ts": "2026-01-05T16:00:00+00:00", "symbol": "X", "side": "buy",
             "fill_price": 104.0},  # selber Tag -> Verstoss
        ])
        w = wiedereinstiege(o, sperrfrist=3)
        assert len(w) == 1 and bool(w.iloc[0]["sperrfrist_verletzt"])
