"""Positionsgroessen als Achse - und die Vorgabe aendert nichts (§G42).

**Warum es diese Achse gibt.** Bis zum 26.08.2026 war die Verteilung des
freien Kapitals fest verdrahtet: `_vola_gewicht(atr_pct)`, also
Risikoparitaet. Keiner der 13 Flottenbots und keine der 14
Lernlauf-Achsen hat sie je variiert. Der Score entschied, OB gekauft wird
und in welcher Reihenfolge - nicht, wieviel.

**Warum diese Tests hart sein muessen.** Die Aenderung greift in die
Handelslogik ein, und zwar an einer Stelle, die jede Order betrifft. Die
Vorgabe `inverse_vola` MUSS deshalb rechnerisch identisch zum alten
`_vola_gewicht` sein - sonst wird eine laufende Messung stillschweigend
zu einer anderen Messung. Dieselbe Beweislast wie beim §G20-Split.
"""

from __future__ import annotations

import pytest

from alpaca_bot.engine import EngineConfig, _vola_gewicht, kandidatengewicht


@pytest.mark.parametrize("atr_pct", [0.005, 0.01, 0.02, 0.03, 0.05, 0.10, 0.25])
@pytest.mark.parametrize("score", [0.0, 0.35, 0.5, 0.9, 1.0])
def test_vorgabe_ist_bitgleich_zum_alten_verhalten(atr_pct, score):
    """Der wichtigste Test der Datei: Die Vorgabe darf NICHTS aendern."""
    assert kandidatengewicht(atr_pct, score, "inverse_vola") == _vola_gewicht(atr_pct)


def test_vorgabe_der_konfiguration_ist_inverse_vola():
    """Wer `EngineConfig()` baut, bekommt das alte Verhalten."""
    assert EngineConfig().groessen_modus == "inverse_vola"
    assert EngineConfig.for_reversal().groessen_modus == "inverse_vola"


def test_unbekannter_modus_faellt_auf_die_vorgabe_zurueck():
    """Ein Tippfehler darf keine stille Gleichgewichtung erzeugen - er
    muss auf dem bisherigen Verhalten landen, nicht auf einem neuen."""
    assert kandidatengewicht(0.03, 0.8, "tippfehler") == _vola_gewicht(0.03)


def test_gleichgewicht_ignoriert_volatilitaet_und_score():
    g = [kandidatengewicht(a, s, "gleich")
         for a in (0.01, 0.05, 0.20) for s in (0.1, 0.9)]
    assert set(g) == {1.0}


def test_score_gewicht_folgt_dem_score():
    """Doppelter Score bei gleicher Vola heisst doppeltes Gewicht."""
    assert kandidatengewicht(0.03, 0.80, "score") == pytest.approx(
        2 * kandidatengewicht(0.03, 0.40, "score"))


def test_score_gewicht_wird_nie_null():
    """Ein Gewicht von 0 wuerde die Position stumm streichen statt sie
    klein zu machen - `verteile_kapital` normiert relativ."""
    for modus in ("score", "score_vola"):
        assert kandidatengewicht(0.03, 0.0, modus) > 0


def test_score_vola_ist_das_produkt():
    a = kandidatengewicht(0.04, 0.7, "score_vola")
    b = kandidatengewicht(0.04, 0.7, "score") * _vola_gewicht(0.04)
    assert a == pytest.approx(b)


def test_modus_steht_im_protokoll():
    """Ohne Eintrag im Konfigurations-Abzug waere spaeter nicht mehr
    feststellbar, mit welcher Groessenregel ein Lauf entstanden ist -
    genau die Luecke aus §G5 (code_version zwei Monate kaputt)."""
    d = EngineConfig.for_reversal(groessen_modus="score").as_dict()
    assert d["groessen_modus"] == "score"


def test_lernlauf_kennt_die_drei_achsen():
    """Die Achse ist nur dann gemessen, wenn sie auch im Raster steht."""
    import re
    from pathlib import Path

    text = (Path(__file__).resolve().parents[1] / "scripts" / "32_lernlauf.py").read_text()
    for name in ("gleichgewicht", "score_gewicht", "score_mal_vola"):
        assert re.search(rf'"{name}":\s*{{"groessen_modus"', text), (
            f"Achse {name} fehlt im Lernlauf-Raster")
