"""Das Spiegelbuch vergisst nicht, warum es gekauft hat (§G27).

**Der Fund vom 24.08.2026.** Anlass war die Frage, ob der Bot eine
schwache Position gegen einen besseren Kandidaten tauschen sollte. Um sie
zu beantworten, braucht man den Score der gehaltenen Position - und der
war nicht da:

    entry_score   0 von 130 Zeilen gefuellt
    reasons     130 von 130 gefuellt, EIN eindeutiger Wert: {}

**Die Ursache.** `shadow_schritte._spiegel` ruft `depot_speichern` an drei
Stellen. Nur der Kauf gibt `entry_score` und `reasons` mit. Der
**taegliche Uebertrag** der gehaltenen Positionen liest sie aus einem
`meta`-Dictionary - und das wird EINMAL vor der Tagesschleife geladen.
Ein im selben Lauf gekaufter Wert steht dort nicht, also kam `None` an
und ueberschrieb per `INSERT OR REPLACE` den korrekten Wert vom Vortag.

Jede Position wird mindestens einmal uebertragen. Also verlor jede ihre
Begruendung - zuverlaessig und lueckenlos.

**Was dadurch unbeantwortbar war:** genau die Frage, fuer die das
Spiegelbuch existiert - "war die gehaltene Position schwaecher als der
beste verworfene Kandidat?". Man sah, WAS gehalten wurde, aber nicht,
mit welcher Begruendung.
"""

from __future__ import annotations

import pandas as pd
import pytest

from alpaca_bot import shadow_pruefung as sp
from alpaca_bot.engine import Position
from alpaca_bot.shadow import ShadowStore


@pytest.fixture
def buch(tmp_path):
    return ShadowStore(tmp_path / "shadow.sqlite")


def _pos(symbol="X", bars_held=0, qty=10.0) -> Position:
    return Position(symbol=symbol, qty=qty, entry_price=100.0,
                    entry_date=pd.Timestamp("2026-08-17", tz="UTC"),
                    stop_price=94.0, target_price=110.0,
                    bars_held=bars_held, high_water=100.0)


class TestFortschreibungVerliertNichts:
    """Eine Fortschreibung darf nie weniger Information hinterlassen."""

    def test_kauf_speichert_score_und_gruende(self, buch):
        buch.depot_speichern("B00", _pos(), entry_score=0.87,
                             reasons={"rsi2": True})
        z = buch.depot_positionen("B00")["X"]
        assert z["entry_score"] == pytest.approx(0.87)
        assert "rsi2" in z["reasons"]

    def test_taeglicher_uebertrag_erhaelt_den_score(self, buch):
        """DER Fund: der Uebertrag ueberschrieb ihn mit None."""
        buch.depot_speichern("B00", _pos(), entry_score=0.87,
                             reasons={"rsi2": True})
        buch.depot_speichern("B00", _pos(bars_held=1), entry_score=None)
        z = buch.depot_positionen("B00")["X"]
        assert z["entry_score"] == pytest.approx(0.87), (
            "Der taegliche Uebertrag darf den Einstiegsscore nicht "
            "loeschen. Gemessen am 24.08.2026: 0 von 130 Positionen "
            "hatten noch einen."
        )
        assert "rsi2" in z["reasons"]
        assert z["bars_held"] == 1, "Die Haltedauer MUSS fortgeschrieben werden"

    def test_leeres_dictionary_ueberschreibt_nicht(self, buch):
        """`{}` ist kein Wert, sondern das Fehlen eines Wertes."""
        buch.depot_speichern("B00", _pos(), entry_score=0.87,
                             reasons={"rsi2": True})
        buch.depot_speichern("B00", _pos(bars_held=2), reasons={})
        assert "rsi2" in buch.depot_positionen("B00")["X"]["reasons"]

    def test_neue_gruende_gewinnen(self, buch):
        """Ein echter neuer Wert MUSS durchkommen - sonst friert die Zeile ein."""
        buch.depot_speichern("B00", _pos(), entry_score=0.87,
                             reasons={"rsi2": True})
        buch.depot_speichern("B00", _pos(bars_held=3), entry_score=0.95,
                             reasons={"nachkauf": True})
        z = buch.depot_positionen("B00")["X"]
        assert z["entry_score"] == pytest.approx(0.95)
        assert "nachkauf" in z["reasons"]

    def test_kurswerte_werden_immer_fortgeschrieben(self, buch):
        """Nur Score und Gruende sind geschuetzt, nicht die Kennzahlen."""
        buch.depot_speichern("B00", _pos(), entry_score=0.87,
                             reasons={"a": 1})
        p = _pos(bars_held=4, qty=20.0)
        p.high_water = 123.0
        buch.depot_speichern("B00", p)
        z = buch.depot_positionen("B00")["X"]
        assert z["qty"] == pytest.approx(20.0)
        assert z["high_water"] == pytest.approx(123.0)
        assert z["bars_held"] == 4

    def test_bots_stoeren_sich_nicht(self, buch):
        buch.depot_speichern("B00", _pos(), entry_score=0.87)
        buch.depot_speichern("B04", _pos(), entry_score=0.42)
        assert buch.depot_positionen("B00")["X"]["entry_score"] == pytest.approx(0.87)
        assert buch.depot_positionen("B04")["X"]["entry_score"] == pytest.approx(0.42)


class TestWaechterMeldetVergesseneGruende:
    """Pruefung 11 - damit es nicht wieder monatelang unbemerkt bleibt."""

    def test_meldet_fehlenden_score(self, buch):
        buch.depot_speichern("B00", _pos(), entry_score=None, reasons=None)
        b = sp._pruefe_einstiegsgruende(buch)
        assert not b.ok
        assert "entry_score" in b.text

    def test_meldet_leere_gruende(self, buch):
        """`{}` sieht gefuellt aus und ist es nicht - §G19 Fund 5 in Gruen."""
        buch.depot_speichern("B00", _pos(), entry_score=0.9, reasons=None)
        b = sp._pruefe_einstiegsgruende(buch)
        assert not b.ok and "Begruendung" in b.text

    def test_schweigt_bei_vollstaendigen_daten(self, buch):
        buch.depot_speichern("B00", _pos(), entry_score=0.9,
                             reasons={"rsi2": True})
        assert sp._pruefe_einstiegsgruende(buch).ok

    def test_leeres_buch_ist_kein_befund(self, buch):
        assert sp._pruefe_einstiegsgruende(buch).ok

    def test_nennt_die_kernfrage(self, buch):
        """Ein Befund ohne Folgeangabe wird als Formalie abgetan."""
        buch.depot_speichern("B00", _pos(), entry_score=None, reasons=None)
        b = sp._pruefe_einstiegsgruende(buch)
        assert "verworfener Kandidat" in b.text
