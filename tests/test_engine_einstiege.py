"""Einstiege, Positionsgroessen, Sperrfrist, Regimefilter.

Die Groessenberechnung ist der Ort, an dem stille Fehler am teuersten
sind: Sie erzeugen keinen Absturz, sondern lassen Kapital liegen oder
setzen zu viel ein - und beides faellt monatelang nicht auf.
"""

from __future__ import annotations

from unittest.mock import patch

import numpy as np
import pytest

from alpaca_bot.engine import Engine, EngineConfig, verteile_kapital


class TestKapitalverteilung:
    """`verteile_kapital` muss drei Bedingungen gleichzeitig erfuellen:
    Summe ausschoepfen, Deckel einhalten, Kleinstpositionen vermeiden."""

    def test_summe_wird_ausgeschoepft(self):
        g = verteile_kapital({"A": 1.0, "B": 1.0, "C": 1.0},
                             frei=30_000., deckel=15_000., mindest=100.)
        assert sum(g.values()) == pytest.approx(30_000.)

    def test_deckel_wird_eingehalten(self):
        g = verteile_kapital({"A": 5.0, "B": 1.0},
                             frei=30_000., deckel=10_000., mindest=100.)
        assert all(v <= 10_000. + 1e-6 for v in g.values())

    def test_abgeschnittenes_kapital_wird_verteilt(self):
        """Wer proportional verteilt und danach deckelt, laesst das
        abgeschnittene Kapital liegen. Die Wasserfuellung verhindert das."""
        g = verteile_kapital({"A": 10.0, "B": 1.0, "C": 1.0},
                             frei=30_000., deckel=12_000., mindest=100.)
        assert sum(g.values()) == pytest.approx(30_000., abs=1.0)
        assert g["A"] == pytest.approx(12_000.)

    def test_zu_kleine_positionen_fliegen_raus(self):
        """Bei 50 Kandidaten und 3.000 $ Mindestgroesse bekaeme jeder
        1.800 $ - alle unter der Grenze. Ohne Vorabbegrenzung bliebe
        NICHTS uebrig."""
        gewichte = {f"S{i}": 1.0 for i in range(50)}
        g = verteile_kapital(gewichte, frei=90_000., deckel=50_000.,
                             mindest=3_000.)
        assert g, "es muss etwas uebrig bleiben"
        assert all(v >= 3_000. - 1e-6 for v in g.values())
        assert len(g) <= 30

    def test_leere_eingabe(self):
        assert verteile_kapital({}, frei=1000., deckel=100., mindest=10.) == {}
        assert verteile_kapital({"A": 1.0}, frei=0., deckel=100.,
                                mindest=10.) == {}

    def test_deckel_je_symbol(self):
        """Der Nachkauf braucht symbolabhaengige Deckel - die Restluft
        bis `max_position_pct` ist fuer jede Position eine andere."""
        g = verteile_kapital({"A": 1.0, "B": 1.0}, frei=10_000.,
                             deckel={"A": 2_000., "B": 50_000.}, mindest=100.)
        assert g["A"] == pytest.approx(2_000.)
        assert g["B"] == pytest.approx(8_000.)


class TestPositionsgroessen:
    def test_deckel_wird_nie_ueberschritten(self, snapshot_fabrik,
                                            portfolio_fabrik):
        snap = snapshot_fabrik({f"S{i}": {"kurs": 100.0, "score": 0.9}
                                for i in range(5)})
        cfg = EngineConfig.for_reversal(max_position_pct=0.10,
                                        deploy_to_target=True)
        with patch.object(Engine, "_cooldown_symbols", return_value=set()):
            d = Engine(cfg)._find_entries(snap, portfolio_fabrik(kapital=100_000.),
                                          set(), set())
        deckel = 100_000. * 0.10
        assert d and all(x.target_notional <= deckel + 1 for x in d)

    def test_keine_kaeufe_ohne_freie_plaetze(self, snapshot_fabrik,
                                             position_fabrik, portfolio_fabrik):
        gehalten = [position_fabrik(symbol=f"H{i}") for i in range(15)]
        snap = snapshot_fabrik({f"S{i}": {"kurs": 100.0, "score": 0.9}
                                for i in range(5)})
        cfg = EngineConfig.for_reversal(max_positions=15)
        with patch.object(Engine, "_cooldown_symbols", return_value=set()):
            d = Engine(cfg)._find_entries(snap, portfolio_fabrik(gehalten), set(), set())
        assert d == []

    def test_score_unter_schwelle_wird_uebergangen(self, snapshot_fabrik,
                                                   portfolio_fabrik):
        snap = snapshot_fabrik({"X": {"kurs": 100.0, "score": 0.10}})
        cfg = EngineConfig.for_reversal(min_score=0.35)
        with patch.object(Engine, "_cooldown_symbols", return_value=set()):
            d = Engine(cfg)._find_entries(snap, portfolio_fabrik(), set(), set())
        assert d == []

    def test_zu_geringes_volumen_wird_uebergangen(self, snapshot_fabrik,
                                                  portfolio_fabrik):
        """Was nicht handelbar ist, ist kein Signal - eine Aktie mit
        50.000 $ Tagesumsatz zeigt schoene Backtest-Renditen, die beim
        echten Kauf am eigenen Marktimpact verschwinden."""
        snap = snapshot_fabrik({"X": {"kurs": 100.0, "score": 0.9}})
        snap.signals["X"]["dollar_volume"] = 1_000.0
        cfg = EngineConfig.for_reversal(min_dollar_volume=1_000_000)
        with patch.object(Engine, "_cooldown_symbols", return_value=set()):
            d = Engine(cfg)._find_entries(snap, portfolio_fabrik(), set(), set())
        assert d == []


class TestSperrfrist:
    """REGRESSION (29.07.2026): Ohne Sperre verkaufte der Bot AMKR am Ziel
    und kaufte es im SELBEN Durchgang zurueck, weil der Score unveraendert
    hoch war - dreimal in 90 Minuten, jedes Mal mit identischem Stop und
    Ziel. Es entstand keine neue These, nur doppelte Kosten."""

    def test_gesperrtes_symbol_wird_nicht_gekauft(self, snapshot_fabrik,
                                                  portfolio_fabrik):
        snap = snapshot_fabrik({"X": {"kurs": 100.0, "score": 0.9}})
        cfg = EngineConfig.for_reversal()
        with patch.object(Engine, "_cooldown_symbols", return_value={"X"}):
            d = Engine(cfg)._find_entries(snap, portfolio_fabrik(), set(), {"X"})
        assert d == []

    def test_gerade_verkauftes_gibt_platz_frei_bleibt_aber_gesperrt(
            self, snapshot_fabrik, position_fabrik, portfolio_fabrik):
        """Kapazitaets- und Zulassungsfrage sind bewusst getrennt: Der
        Platz wird frei, das Symbol bleibt trotzdem gesperrt."""
        snap = snapshot_fabrik({"X": {"kurs": 100.0, "score": 0.9},
                                "Y": {"kurs": 100.0, "score": 0.8}})
        cfg = EngineConfig.for_reversal(max_positions=1)
        gehalten = [position_fabrik(symbol="X")]
        with patch.object(Engine, "_cooldown_symbols", return_value=set()):
            d = Engine(cfg)._find_entries(snap, portfolio_fabrik(gehalten),
                                          being_sold={"X"}, blocked={"X"})
        gekauft = {x.symbol for x in d}
        assert "X" not in gekauft, "gerade verkauft = gesperrt"
        assert "Y" in gekauft, "der frei gewordene Platz muss nutzbar sein"


class TestRegimefilter:
    """BEFUND G7 (16.08.2026): Der Filter sperrt nicht nur Kaeufe, sondern
    setzt den Score ALLER Symbole auf 0 - und derselbe Score entscheidet
    ueber den Ausstieg. Kippt der Markt, wird das gesamte Depot in einem
    Zyklus liquidiert.

    Dieser Test haelt das dokumentierte IST-Verhalten fest. Aendert es
    sich, muss das eine bewusste Entscheidung sein - kein Nebeneffekt."""

    def _snap_mit_regime(self, idx, markt_steigend: bool):
        from alpaca_bot.engine import MarketSnapshot

        from .conftest import mach_bars

        kurs = np.concatenate([np.full(280, 100.0), np.linspace(100, 70, 20)])
        markt = (np.linspace(400, 500, len(idx)) if markt_steigend
                 else np.linspace(500, 400, len(idx)))
        import pandas as pd

        return MarketSnapshot(as_of=idx[-1], bars={"X": mach_bars(idx, kurs)},
                              market=pd.Series(markt, index=idx))

    def test_baerenmarkt_verkauft_bestand(self, idx, position_fabrik,
                                          portfolio_fabrik):
        snap = self._snap_mit_regime(idx, markt_steigend=False)
        pos = position_fabrik(einstand=100.0, stop=50.0, ziel=500.0, gehalten=2)
        d = Engine(EngineConfig.for_reversal())._check_exits(
            snap, portfolio_fabrik([pos]))
        assert d, "dokumentiertes Verhalten: Regimefilter loest Verkauf aus"
        assert d[0].reasons["ausstiegsgrund"] == "these_traegt_nicht_mehr"
        assert d[0].reasons["score_jetzt"] == pytest.approx(0.0)

    def test_bullenmarkt_haelt_bestand(self, idx, position_fabrik,
                                       portfolio_fabrik):
        snap = self._snap_mit_regime(idx, markt_steigend=True)
        pos = position_fabrik(einstand=100.0, stop=50.0, ziel=500.0, gehalten=2)
        d = Engine(EngineConfig.for_reversal())._check_exits(
            snap, portfolio_fabrik([pos]))
        assert d == [] or d[0].reasons["ausstiegsgrund"] != "these_traegt_nicht_mehr"


class TestNachkauf:
    def test_nur_in_gewinner(self, snapshot_fabrik, position_fabrik,
                             portfolio_fabrik):
        """In eine verlustreiche Position nachzukaufen ist Average-Down
        und macht aus einem begrenzten Verlust einen groesseren."""
        snap = snapshot_fabrik({"X": {"kurs": 90.0, "score": 0.9}})
        pos = position_fabrik(symbol="X", einstand=100.0, qty=10.0)
        cfg = EngineConfig.for_reversal(allow_topup=True, topup_min_gain_pct=0.0)
        d = Engine(cfg)._find_topups(snap, portfolio_fabrik([pos], cash=50_000.),
                                     set())
        assert d == []

    def test_gewinner_wird_aufgestockt(self, snapshot_fabrik, position_fabrik,
                                       portfolio_fabrik):
        snap = snapshot_fabrik({"X": {"kurs": 110.0, "score": 0.9}})
        pos = position_fabrik(symbol="X", einstand=100.0, qty=10.0)
        cfg = EngineConfig.for_reversal(allow_topup=True, topup_min_gain_pct=0.0)
        d = Engine(cfg)._find_topups(snap, portfolio_fabrik([pos], cash=50_000.),
                                     set())
        assert d and d[0].action == "topup"

    def test_stop_und_ziel_bleiben_unveraendert(self, snapshot_fabrik,
                                                position_fabrik,
                                                portfolio_fabrik):
        """Der Nachkauf verstaerkt eine bestehende These, er stellt keine
        neue auf - Stop und Ziel laufen der Position nicht hinterher."""
        snap = snapshot_fabrik({"X": {"kurs": 110.0, "score": 0.9}})
        pos = position_fabrik(symbol="X", einstand=100.0, qty=10.0,
                              stop=85.0, ziel=130.0)
        cfg = EngineConfig.for_reversal(allow_topup=True)
        d = Engine(cfg)._find_topups(snap, portfolio_fabrik([pos], cash=50_000.),
                                     set())
        assert d[0].stop_price == pytest.approx(85.0)
        assert d[0].target_price == pytest.approx(130.0)

    def test_schwacher_score_wird_nicht_aufgestockt(self, snapshot_fabrik,
                                                    position_fabrik,
                                                    portfolio_fabrik):
        """Eine angeschlagene These bekommt kein zusaetzliches Kapital."""
        snap = snapshot_fabrik({"X": {"kurs": 110.0, "score": 0.20}})
        pos = position_fabrik(symbol="X", einstand=100.0, qty=10.0)
        cfg = EngineConfig.for_reversal(allow_topup=True, min_score=0.35)
        d = Engine(cfg)._find_topups(snap, portfolio_fabrik([pos], cash=50_000.),
                                     set())
        assert d == []
