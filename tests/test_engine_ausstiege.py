"""Ausstiegsregeln - wann wird verkauft, und aus welchem Grund?

Der Ausstieg entscheidet ueber das Ergebnis staerker als der Einstieg:
Gemessen am 15.08.2026 sind 15 von 24 Ausstiegen im Schattenbetrieb
Zeitausstiege (62 %). Ein Fehler in der REIHENFOLGE der Regeln aendert
nicht ob, sondern WARUM verkauft wird - und verfaelscht damit still jede
Auswertung nach Ausstiegsgruenden, ohne dass eine Zahl auffaellig wird.
"""

from __future__ import annotations

import pandas as pd
import pytest

from alpaca_bot.engine import Engine, EngineConfig


def grund(engine, snap, portfolio) -> str | None:
    d = engine._check_exits(snap, portfolio)
    return d[0].reasons["ausstiegsgrund"] if d else None


# ---------------------------------------------------------------- Reihenfolge
class TestReihenfolge:
    """Die Regeln sind bewusst geordnet: Stop schlaegt Ziel schlaegt Zeit
    schlaegt Score. Wer die Reihenfolge dreht, bekommt dieselben Verkaeufe
    mit anderen Etiketten - und eine unbrauchbare Statistik."""

    def test_stop_schlaegt_alles(self, snapshot_fabrik, position_fabrik,
                                 portfolio_fabrik):
        snap = snapshot_fabrik({"X": {"kurs": 70.0, "score": 0.01}})
        pos = position_fabrik(stop=80.0, ziel=60.0, gehalten=99)
        e = Engine(EngineConfig.for_reversal())
        assert grund(e, snap, portfolio_fabrik([pos])) == "stop_ausgeloest"

    def test_ziel_schlaegt_zeit_und_score(self, snapshot_fabrik,
                                          position_fabrik, portfolio_fabrik):
        snap = snapshot_fabrik({"X": {"kurs": 210.0, "score": 0.01}})
        pos = position_fabrik(stop=50.0, ziel=200.0, gehalten=99)
        e = Engine(EngineConfig.for_reversal())
        assert grund(e, snap, portfolio_fabrik([pos])) == "gewinnziel_erreicht"

    def test_zeit_schlaegt_score(self, snapshot_fabrik, position_fabrik,
                                 portfolio_fabrik):
        snap = snapshot_fabrik({"X": {"kurs": 100.0, "score": 0.01}})
        pos = position_fabrik(stop=50.0, ziel=500.0, gehalten=5)
        e = Engine(EngineConfig.for_reversal(max_hold_days=5))
        assert grund(e, snap, portfolio_fabrik([pos])) == "zeitausstieg"

    def test_score_greift_zuletzt(self, snapshot_fabrik, position_fabrik,
                                  portfolio_fabrik):
        snap = snapshot_fabrik({"X": {"kurs": 100.0, "score": 0.01}})
        pos = position_fabrik(stop=50.0, ziel=500.0, gehalten=1)
        e = Engine(EngineConfig.for_reversal(max_hold_days=5, exit_score=0.10))
        assert grund(e, snap, portfolio_fabrik([pos])) == "these_traegt_nicht_mehr"

    def test_nichts_erfuellt_haelt(self, snapshot_fabrik, position_fabrik,
                                   portfolio_fabrik):
        snap = snapshot_fabrik({"X": {"kurs": 100.0, "score": 0.9}})
        pos = position_fabrik(stop=50.0, ziel=500.0, gehalten=1)
        e = Engine(EngineConfig.for_reversal(max_hold_days=5))
        assert grund(e, snap, portfolio_fabrik([pos])) is None


# ------------------------------------------------- Dynamischer Zeitausstieg
class TestDynamischerZeitausstieg:
    """Verlaengert die Haltefrist NUR fuer Positionen, die noch laufen.

    Kalibrierung (15.08.2026): Eine feste 2-%-Schwelle haette an 27,5 %
    aller Positionstage ausgeloest - Umkehr-Kandidaten haben einen
    Median-ATR von 5,16 %. Deshalb ATR-basiert, nicht prozentual.
    """

    @staticmethod
    def _cfg(**kw):
        basis = dict(zeitausstieg_dynamisch=True, max_hold_days=5,
                     trend_rueckfall_atr=1.0, max_hold_days_hart=20,
                     exit_score=0.10)
        basis.update(kw)
        return EngineConfig.for_reversal(**basis)

    def test_am_hoch_wird_gehalten(self, snapshot_fabrik, position_fabrik,
                                   portfolio_fabrik):
        snap = snapshot_fabrik({"X": {"kurs": 110.0, "score": 0.5, "atr": 5.0}})
        pos = position_fabrik(einstand=100.0, hoechst=110.0, gehalten=5,
                              stop=50.0, ziel=500.0)
        assert grund(Engine(self._cfg()), snap, portfolio_fabrik([pos])) is None

    def test_kleiner_ruecksetzer_haelt(self, snapshot_fabrik, position_fabrik,
                                       portfolio_fabrik):
        # 3 Punkte unter Hoch bei ATR 5 -> unter 1x ATR -> Trend intakt
        snap = snapshot_fabrik({"X": {"kurs": 107.0, "score": 0.5, "atr": 5.0}})
        pos = position_fabrik(einstand=100.0, hoechst=110.0, gehalten=5,
                              stop=50.0, ziel=500.0)
        assert grund(Engine(self._cfg()), snap, portfolio_fabrik([pos])) is None

    def test_grosser_ruecksetzer_verkauft(self, snapshot_fabrik,
                                          position_fabrik, portfolio_fabrik):
        # 6 Punkte unter Hoch bei ATR 5 -> ueber 1x ATR -> Trend gebrochen
        snap = snapshot_fabrik({"X": {"kurs": 104.0, "score": 0.5, "atr": 5.0}})
        pos = position_fabrik(einstand=100.0, hoechst=110.0, gehalten=5,
                              stop=50.0, ziel=500.0)
        assert grund(Engine(self._cfg()), snap,
                     portfolio_fabrik([pos])) == "zeitausstieg"

    def test_schwelle_skaliert_mit_volatilitaet(self, snapshot_fabrik,
                                                position_fabrik,
                                                portfolio_fabrik):
        """DER Kernpunkt der ATR-Umstellung: Derselbe Rueckfall von 3
        Punkten ist bei einem volatilen Wert Rauschen und bei einem ruhigen
        ein Trendbruch. Ein fester Prozentsatz kann das nicht."""
        pos = position_fabrik(einstand=100.0, hoechst=110.0, gehalten=5,
                              stop=50.0, ziel=500.0)
        volatil = snapshot_fabrik({"X": {"kurs": 107.0, "score": 0.5, "atr": 5.0}})
        ruhig = snapshot_fabrik({"X": {"kurs": 107.0, "score": 0.5, "atr": 1.0}})
        assert grund(Engine(self._cfg()), volatil, portfolio_fabrik([pos])) is None
        assert grund(Engine(self._cfg()), ruhig,
                     portfolio_fabrik([pos])) == "zeitausstieg"

    def test_im_minus_wird_nie_verlaengert(self, snapshot_fabrik,
                                           position_fabrik, portfolio_fabrik):
        """Eine Verlustposition laenger zu halten ist Hoffnung, keine Regel."""
        snap = snapshot_fabrik({"X": {"kurs": 95.0, "score": 0.5, "atr": 5.0}})
        pos = position_fabrik(einstand=100.0, hoechst=110.0, gehalten=5,
                              stop=50.0, ziel=500.0)
        assert grund(Engine(self._cfg()), snap,
                     portfolio_fabrik([pos])) == "zeitausstieg"

    def test_fehlender_atr_verlaengert_nicht(self, snapshot_fabrik,
                                             position_fabrik, portfolio_fabrik):
        """Ohne Volatilitaetsmass laesst sich Rauschen nicht von einer
        Trendwende unterscheiden. Im Zweifel gilt die urspruengliche Regel -
        eine Verlaengerung muss positiv begruendet sein, nicht durch
        fehlende Daten entstehen."""
        snap = snapshot_fabrik({"X": {"kurs": 110.0, "score": 0.5, "atr": 0.0}})
        pos = position_fabrik(einstand=100.0, hoechst=110.0, gehalten=5,
                              stop=50.0, ziel=500.0)
        assert grund(Engine(self._cfg()), snap,
                     portfolio_fabrik([pos])) == "zeitausstieg"

    def test_harte_grenze_beendet_auch_intakten_trend(self, snapshot_fabrik,
                                                      position_fabrik,
                                                      portfolio_fabrik):
        """Sonst wird aus einem Umkehr-Trade unbemerkt ein Momentum-Trade -
        genau der Fehler, der den ersten Anlauf des Projekts ruiniert hat."""
        snap = snapshot_fabrik({"X": {"kurs": 130.0, "score": 0.5, "atr": 5.0}})
        pos = position_fabrik(einstand=100.0, hoechst=130.0, gehalten=20,
                              stop=50.0, ziel=500.0)
        assert grund(Engine(self._cfg()), snap,
                     portfolio_fabrik([pos])) == "zeitausstieg_hart"

    def test_score_gilt_auch_fuer_verlaengerte(self, snapshot_fabrik,
                                               position_fabrik,
                                               portfolio_fabrik):
        """Sonst waere eine verlaengerte Position gegen genau die Regel
        immun, die sie sonst geschlossen haette."""
        snap = snapshot_fabrik({"X": {"kurs": 110.0, "score": 0.05, "atr": 5.0}})
        pos = position_fabrik(einstand=100.0, hoechst=110.0, gehalten=5,
                              stop=50.0, ziel=500.0)
        assert grund(Engine(self._cfg()), snap,
                     portfolio_fabrik([pos])) == "these_traegt_nicht_mehr"


# ------------------------------------------------------- Schalter-Isolation
class TestSchalterIsolation:
    """REGRESSION (16.08.2026): `max_hold_days_hart` wurde geprueft, BEVOR
    feststand, ob die Verlaengerung ueberhaupt aktiv ist. Folge: Der
    Live-Bot (dynamisch=False) haette ab Tag 20 den Grund
    'zeitausstieg_hart' statt 'zeitausstieg' protokolliert - bei der
    Momentum-Konfiguration (max_hold_days=60 >= 20) sogar immer.

    Gleiche Handelsentscheidung, anderer Grund im Protokoll - und damit
    eine still verfaelschte Auswertung nach Ausstiegsgruenden."""

    @pytest.mark.parametrize("gehalten", [5, 19, 20, 25, 60])
    def test_live_meldet_immer_zeitausstieg(self, gehalten, snapshot_fabrik,
                                            position_fabrik, portfolio_fabrik):
        snap = snapshot_fabrik({"X": {"kurs": 110.0, "score": 0.5, "atr": 5.0}})
        pos = position_fabrik(einstand=100.0, hoechst=110.0,
                              gehalten=gehalten, stop=50.0, ziel=500.0)
        e = Engine(EngineConfig.for_reversal())  # dynamisch AUS = live
        assert grund(e, snap, portfolio_fabrik([pos])) == "zeitausstieg"

    def test_momentum_konfiguration_unveraendert(self, snapshot_fabrik,
                                                 position_fabrik,
                                                 portfolio_fabrik):
        """max_hold_days=60 gegen max_hold_days_hart=20: Ohne Isolation
        haette die harte Grenze hier IMMER gegriffen."""
        snap = snapshot_fabrik({"X": {"kurs": 110.0, "score": 0.5, "atr": 5.0}})
        e = Engine(EngineConfig())  # Standard: max_hold_days=60
        vorher = position_fabrik(einstand=100.0, hoechst=110.0, gehalten=59,
                                 stop=50.0, ziel=500.0)
        nachher = position_fabrik(einstand=100.0, hoechst=110.0, gehalten=60,
                                  stop=50.0, ziel=500.0)
        assert grund(e, snap, portfolio_fabrik([vorher])) is None
        assert grund(e, snap, portfolio_fabrik([nachher])) == "zeitausstieg"


# ------------------------------------------------------------- Lookahead
class TestLookahead:
    """Die strukturelle Sperre gegen Zukunftswissen. Sie ist der Grund,
    warum Backtest-Ergebnisse ueberhaupt etwas bedeuten."""

    def test_daten_nach_stichtag_werfen(self, idx):
        from alpaca_bot.engine import MarketSnapshot

        from .conftest import mach_bars

        bars = mach_bars(idx)
        snap = MarketSnapshot(as_of=idx[-5], bars={"X": bars})
        with pytest.raises(ValueError, match="LOOKAHEAD"):
            snap.validate()

    def test_saubere_momentaufnahme_passiert(self, idx):
        from alpaca_bot.engine import MarketSnapshot

        from .conftest import mach_bars

        snap = MarketSnapshot(as_of=idx[-1], bars={"X": mach_bars(idx)})
        snap.validate()  # darf nicht werfen
