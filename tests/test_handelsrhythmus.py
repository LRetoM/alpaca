"""Live gegen Spiegel: gleiche Konfiguration, anderes Verhalten (§G16).

**Der Fund vom 22.08.2026.** `tests/test_konsistenz.py` sichert seit §G11,
dass `B09_nachkauf` **feldweise** die Live-Konfiguration traegt. Das war
richtig - und reichte nicht. Gemessen an dem, was beide tatsaechlich TUN:

    Live-Journal   110 topup von 304 Entscheidungen (36 %)
    Spiegelbuch      0 topup von  51 Kaeufen

Die Ursache ist kein Parameter, sondern der Aufrufrhythmus.
`max_new_positions=3` bedeutet an beiden Orten Verschiedenes:

    live.run_once     3 Kaeufe je ZYKLUS   - Daemon-Takt 15 Min, bis 26/Tag
    shadow._spiegel   3 Kaeufe je HANDELSTAG

Am 28.07.2026 eroeffnete der Live-Bot **50 Positionen an einem Tag**. Der
Spiegel schafft konstruktionsbedingt drei. Folge: Live steht bei 15/15
Positionen, B09 bei 11/15.

Und daran haengt der eigentliche Schaden: `Engine._find_topups` zieht das
von `_find_entries` verplante Kapital ab. Solange Plaetze frei sind, ist
das der gesamte freie Betrag - es gibt **nie** Nachkaeufe. Erst im vollen
Depot (`slots = 0`, `entries = []`, `verplant = 0`) entstehen sie.

Damit ist `B09_nachkauf` ueber seine ganze Laufzeit bitgleich mit
`B08_voll_investiert` - und `B11_dyn_ausstieg_live` wird laut
BETRIEBSPLAN §3.3 gegen genau diesen Bot abgenommen.

**Diese Tests beheben nichts.** Eine Aenderung waere Handelslogik
waehrend einer laufenden Messung (CLAUDE.md). Sie halten den Mechanismus
fest, damit er nicht ein zweites Mal unbemerkt entsteht - und damit die
Abweichung bei jeder Pruefung sichtbar bleibt.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from alpaca_bot.engine import (Engine, EngineConfig, MarketSnapshot,
                               PortfolioState, Position)

IDX = pd.date_range("2024-01-01", periods=300, freq="B", tz="UTC")


def _umkehrkandidat(seed: int) -> pd.DataFrame:
    """Bar-Reihe, die am letzten Tag ein echtes Umkehr-Setup zeigt."""
    rng = np.random.default_rng(seed)
    c = 100 * np.exp(np.cumsum(rng.normal(0.0004, 0.012, len(IDX))))
    c[-3:] = c[-4] * np.array([0.96, 0.93, 0.90])
    v = np.full(len(IDX), 4e6)
    v[-3:] = 2.0e7
    return pd.DataFrame({"open": c, "high": c * 1.01, "low": c * 0.99,
                         "close": c, "volume": v}, index=IDX)


@pytest.fixture
def welt():
    syms = [f"S{i:02d}" for i in range(20)]
    bars = {s: _umkehrkandidat(i) for i, s in enumerate(syms)}
    markt = pd.Series(np.linspace(300, 420, len(IDX)), index=IDX)
    return syms, bars, MarketSnapshot(as_of=IDX[-1], bars=bars, market=markt)


def _depot(syms, bars, n_pos: int, cash: float, equity: float):
    """Konsistentes Depot: equity = cash + Positionswert."""
    pos = {}
    for s in syms[:n_pos]:
        p = float(bars[s]["close"].iloc[-1])
        pos[s] = Position(s, ((equity - cash) / n_pos) / p, p * 0.9,
                          IDX[-3], p * 0.5, p * 2, bars_held=1, high_water=p)
    return PortfolioState(cash=cash, equity=equity, positions=pos)


def _engine():
    return Engine(EngineConfig.for_reversal(
        max_positions=15, deploy_to_target=True, allow_topup=True))


class TestNachkaufBrauchtEinVollesDepot:
    """Der Mechanismus, der B09 vom Live-Bot trennt."""

    def test_freie_plaetze_verhindern_jeden_nachkauf(self, welt):
        """B09s reale Lage: 11 von 15 Plaetzen, 36 % Cash - null Nachkaeufe."""
        syms, bars, snap = welt
        pf = _depot(syms, bars, n_pos=11, cash=38_204.0, equity=106_303.0)
        d = _engine().decide(snap, pf)
        assert sum(1 for x in d if x.action == "buy") > 0
        assert sum(1 for x in d if x.action == "topup") == 0, (
            "solange Plaetze frei sind, verplant _find_entries das gesamte "
            "freie Kapital - fuer Nachkaeufe bleibt nichts")

    def test_volles_depot_erzeugt_nachkaeufe(self, welt):
        """Live steht bei 15/15 - deshalb entstehen dort 110 topups."""
        syms, bars, snap = welt
        pf = _depot(syms, bars, n_pos=15, cash=38_204.0, equity=106_303.0)
        d = _engine().decide(snap, pf)
        assert sum(1 for x in d if x.action == "buy") == 0
        assert sum(1 for x in d if x.action == "topup") > 0

    def test_verplant_ist_der_hebel(self, welt):
        """Ohne den Abzug waeren es sofort Nachkaeufe - der Beleg, dass
        `verplant` die Ursache ist und nicht die Kapitaldecke."""
        syms, bars, snap = welt
        pf = _depot(syms, bars, n_pos=11, cash=38_204.0, equity=106_303.0)
        e = _engine()
        ent = e._find_entries(snap, pf, set(), set())
        verplant = sum(x.target_notional for x in ent)
        assert len(e._find_topups(snap, pf, set(), verplant)) == 0
        assert len(e._find_topups(snap, pf, set(), 0.0)) > 0

    def test_engine_kennt_max_new_positions_nicht(self):
        """Der Kern: Die Engine verplant fuer ALLE Vorschlaege, der
        Aufrufer fuehrt nur `max_new_positions` davon aus. Die Differenz
        bleibt liegen - und blockiert zugleich den Nachkauf."""
        import inspect

        quelle = inspect.getsource(Engine.decide)
        assert "max_new_positions" not in quelle
        assert "verplant" in quelle


class TestPruefungMeldetDieAbweichung:
    """Sichtbar bleiben ist das Ziel - nicht stillschweigend richtig sein."""

    def test_pruefung_10_existiert(self):
        from alpaca_bot import shadow

        befunde = shadow.pruefungen()
        nummern = {b.nummer for b in befunde}
        assert 10 in nummern, (
            "die Verhaltensabweichung braucht eine eigene Pruefung - "
            "Pruefung 3 vergleicht nur Kurse, nicht Aktionen")

    def test_fehlende_aktionsart_faellt_auf(self):
        from alpaca_bot.shadow import _pruefe_handelsrhythmus

        import inspect
        quelle = inspect.getsource(_pruefe_handelsrhythmus)
        assert "n_sp_top == 0" in quelle, (
            "geprueft wird, dass eine ganze Aktionsart FEHLT - nicht, dass "
            "die Anteile exakt gleich sind (der Spiegel sieht andere Tage)")

    def test_meldung_nennt_die_ursache(self):
        """Ein Befund ohne Mechanismus wird als Rauschen abgetan."""
        from alpaca_bot.shadow import _pruefe_handelsrhythmus

        import inspect
        quelle = inspect.getsource(_pruefe_handelsrhythmus)
        assert "ZYKLUS" in quelle and "HANDELSTAG" in quelle
