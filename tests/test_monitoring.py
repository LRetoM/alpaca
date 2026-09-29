"""Auswertungskontext - Regime, Sektor, Liquiditaetsdezil.

Diese Felder beeinflussen KEINE Entscheidung. Sie machen im Nachhinein
beantwortbar, was sonst unbeantwortbar bliebe:

  * In welcher Marktlage traegt die Strategie? (`regime_markt`)
  * Klumpt das Depot in einem Sektor? (`sektor`)
  * Funktioniert es bei Neben- oder Standardwerten? (`liq_dezil`)
  * War der Kauf Rang 1 von 200 oder von 3? (`kandidaten_gesamt`)

Der letzte Punkt ist subtil: Ein Score von 0,9 bedeutet etwas voellig
anderes, wenn er der beste von drei Kandidaten war, als wenn er sich
gegen 200 durchgesetzt hat.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from alpaca_bot.engine import Engine, EngineConfig


class TestKontextImProtokoll:
    def test_regime_landet_in_der_begruendung(self, snapshot_fabrik,
                                              portfolio_fabrik):
        snap = snapshot_fabrik({"X": {"kurs": 100.0, "score": 0.9}})
        snap.regime = {"regime_markt": "bullisch", "regime_vola": "ruhig"}
        with patch.object(Engine, "_cooldown_symbols", return_value=set()):
            d = Engine(EngineConfig.for_reversal())._find_entries(
                snap, portfolio_fabrik(), set(), set())
        assert d and d[0].reasons["regime_markt"] == "bullisch"
        assert d[0].reasons["regime_vola"] == "ruhig"

    def test_sektor_und_dezil_landen_in_der_begruendung(self, snapshot_fabrik,
                                                        portfolio_fabrik):
        snap = snapshot_fabrik({"X": {"kurs": 100.0, "score": 0.9}})
        snap.kontext = {"X": {"sektor": "Technology", "liq_dezil": 3}}
        with patch.object(Engine, "_cooldown_symbols", return_value=set()):
            d = Engine(EngineConfig.for_reversal())._find_entries(
                snap, portfolio_fabrik(), set(), set())
        assert d[0].reasons["sektor"] == "Technology"
        assert d[0].reasons["liq_dezil"] == 3

    def test_kandidatenzahl_wird_erfasst(self, snapshot_fabrik,
                                         portfolio_fabrik):
        """Rang 1 von 200 ist etwas anderes als Rang 1 von 3."""
        snap = snapshot_fabrik({f"S{i}": {"kurs": 100.0, "score": 0.9 - i * 0.01}
                                for i in range(7)})
        with patch.object(Engine, "_cooldown_symbols", return_value=set()):
            d = Engine(EngineConfig.for_reversal())._find_entries(
                snap, portfolio_fabrik(), set(), set())
        assert d and all(x.reasons["kandidaten_gesamt"] == 7 for x in d)

    def test_fehlender_kontext_bricht_nicht(self, snapshot_fabrik,
                                            portfolio_fabrik):
        """Ein Protokollfeld darf den Handel nie verhindern."""
        snap = snapshot_fabrik({"X": {"kurs": 100.0, "score": 0.9}})
        with patch.object(Engine, "_cooldown_symbols", return_value=set()):
            d = Engine(EngineConfig.for_reversal())._find_entries(
                snap, portfolio_fabrik(), set(), set())
        assert d, "ohne Kontext muss trotzdem gekauft werden"
        assert "sektor" not in d[0].reasons


class TestKontextAendertKeineEntscheidung:
    """DER wichtigste Test dieses Moduls: Der Kontext ist reine
    Protokollierung. Wuerde er die Auswahl beeinflussen, waere das eine
    ungetestete Strategieaenderung - und die laufende 20-Tage-Messung
    waere entwertet."""

    def test_gleiche_auswahl_mit_und_ohne_kontext(self, snapshot_fabrik,
                                                  portfolio_fabrik):
        symbole = {f"S{i}": {"kurs": 100.0, "score": 0.9 - i * 0.05}
                   for i in range(6)}

        ohne = snapshot_fabrik(symbole)
        mit = snapshot_fabrik(symbole)
        mit.regime = {"regime_markt": "baerisch", "regime_vola": "unruhig"}
        mit.kontext = {s: {"sektor": "Energy", "liq_dezil": 9} for s in symbole}

        with patch.object(Engine, "_cooldown_symbols", return_value=set()):
            e = Engine(EngineConfig.for_reversal())
            a = e._find_entries(ohne, portfolio_fabrik(), set(), set())
            b = e._find_entries(mit, portfolio_fabrik(), set(), set())

        assert [x.symbol for x in a] == [x.symbol for x in b]
        assert [round(x.target_notional, 2) for x in a] == \
               [round(x.target_notional, 2) for x in b]


class TestLiquiditaetsdezile:
    def test_liquideste_bekommen_dezil_eins(self):
        from alpaca_bot import universe

        d = universe.liquiditaets_dezile(["AAPL", "NVDA"])
        if d:  # nur pruefen, wenn das Universum vorhanden ist
            assert all(v == 1 for v in d.values()), \
                "AAPL/NVDA muessen im liquidesten Dezil liegen"

    def test_unbekannte_symbole_fehlen_still(self):
        from alpaca_bot import universe

        d = universe.liquiditaets_dezile(["GIBTESNICHT123"])
        assert "GIBTESNICHT123" not in d

    def test_dezile_liegen_im_gueltigen_bereich(self):
        from alpaca_bot import universe
        from alpaca_bot.universe import UNIVERSE_FILE

        if not UNIVERSE_FILE.exists():
            pytest.skip("Universum noch nicht aufgebaut")
        import pandas as pd

        alle = pd.read_csv(UNIVERSE_FILE)["symbol"].astype(str).tolist()
        d = universe.liquiditaets_dezile(alle)
        assert d and all(1 <= v <= 10 for v in d.values())
