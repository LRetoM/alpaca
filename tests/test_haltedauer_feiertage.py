"""Haltedauer zaehlt echte Handelstage, nicht Werktage (§G38).

**Der Fund (26.08.2026).** Die Haltedauer, an der `max_hold_days` haengt,
wurde an fuenf Stellen mit `pd.bdate_range` gerechnet - Montag bis
Freitag, Boersenfeiertage eingeschlossen. Simulation und Schattenbetrieb
zaehlen dagegen Bars, und am Feiertag gibt es keine.

Folge: In jeder Feiertagswoche verkaufte der Live-Bot einen Handelstag
FRUEHER als jede Messung, gegen die er verglichen wird. `max_hold_days=5`
war live faktisch eine 4-Tage-Regel - aber nur manchmal, was schlimmer
ist als immer.

**Behoben am 26.08.2026**, bevor es zum ersten Mal greifen konnte: Der
Live-Bot handelt seit Ende Juli, und bis heute lag kein
US-Boersenfeiertag. Der erste waere Labor Day am 07.09.2026 gewesen.

Diese Datei ersetzt die Fassung, die bewusst den falschen Ist-Zustand
festschrieb. Sie hat beim Umbau angeschlagen - genau dafuer war sie da.
"""

from __future__ import annotations

import pandas as pd

from alpaca_bot import handelskalender
from alpaca_bot.lifecycle import handelstage

LABOR_DAY_2026 = "2026-09-07"
"""Montag. NYSE und Nasdaq geschlossen."""


def test_labor_day_ist_ein_werktag_aber_kein_handelstag():
    """Die Ausgangslage - warum `bdate_range` hier nicht taugt."""
    assert pd.Timestamp(LABOR_DAY_2026) in pd.bdate_range("2026-09-03", "2026-09-10")
    kal = handelskalender.handelstage()
    if kal is not None:
        assert pd.Timestamp(LABOR_DAY_2026) not in kal


def test_haltedauer_ueberspringt_den_feiertag():
    """Der eigentliche Fix. Einstieg Do 03.09., Stichtag Do 10.09.

    Echte Handelstage: 04.09. (Fr), 08.09. (Di), 09.09. (Mi), 10.09. (Do).
    Das sind VIER. `pd.bdate_range` lieferte hier fuenf.
    """
    assert handelstage("2026-09-03", "2026-09-10") == 4, (
        "Der Feiertag wird wieder mitgezaehlt - §G38 ist zurueck")
    assert len(pd.bdate_range("2026-09-03", "2026-09-10")) - 1 == 5, (
        "Gegenprobe: die alte Rechnung lieferte fuenf")


def test_woche_ohne_feiertag_bleibt_unveraendert():
    """Der Fix darf NUR am Feiertag etwas aendern. Waere er ein
    genereller Off-by-one, wuerde er jede Haltedauer verschieben."""
    assert handelstage("2026-09-17", "2026-09-24") == 5
    assert len(pd.bdate_range("2026-09-17", "2026-09-24")) - 1 == 5


def test_wochenende_zaehlt_weiterhin_nicht():
    """Freitag bis Montag ist ein Handelstag, nicht drei."""
    assert handelstage("2026-09-18", "2026-09-21") == 1


def test_einstiegstag_zaehlt_nicht_mit():
    """Unveraenderte Zaehlweise: der Einstiegstag zaehlt nicht, der
    Stichtag schon. Eine Aenderung hier waere eine stille Verschiebung
    JEDER Haltedauer, nicht nur der in Feiertagswochen."""
    assert handelstage("2026-09-17", "2026-09-17") == 0
    assert handelstage("2026-09-17", "2026-09-18") == 1


def test_max_hold_days_greift_jetzt_zur_richtigen_zeit():
    """Die wirtschaftliche Folge. `engine` prueft `bars_held >= max_hold_days`.

    Ueber Labor Day ist die Bedingung jetzt erst nach dem 5. echten
    Handelstag erfuellt - wie in Simulation und Schatten, nicht mehr
    einen Tag frueher.
    """
    from alpaca_bot.engine import EngineConfig

    cfg = EngineConfig.for_reversal()
    assert handelstage("2026-09-03", "2026-09-10") < cfg.max_hold_days
    assert handelstage("2026-09-03", "2026-09-11") == cfg.max_hold_days


def test_rueckfall_auf_werktage_ausserhalb_des_kalenders():
    """Ein Datum jenseits des bekannten Kalenders darf keine Ausnahme
    werfen. Eine Haltedauer, die nicht berechnet werden kann, liesse die
    Position unbegrenzt offen - das waere schlimmer als eine ungenaue."""
    assert handelskalender.zwischen("2049-01-04", "2049-01-11") == 5


def test_verkehrte_reihenfolge_gibt_null():
    assert handelskalender.zwischen("2026-09-10", "2026-09-03") == 0


def test_keine_zweite_zaehlweise_im_quelltext():
    """Fuenf Stellen rechneten dieselbe Groesse verschieden. Kommt eine
    zurueck, faellt es hier auf."""
    from pathlib import Path

    import ast

    src = Path(__file__).resolve().parents[1] / "src" / "alpaca_bot"
    # `handelskalender` darf: dort steht der bewusste Rueckfall.
    # `selfcheck` darf: erzeugt Testdaten, misst keine Haltedauer.
    erlaubt = {"handelskalender.py", "selfcheck.py"}

    treffer = []
    for f in src.glob("*.py"):
        if f.name in erlaubt:
            continue
        # Ueber den Syntaxbaum, nicht ueber den Text - sonst schlaegt
        # jede Erwaehnung in einem Docstring an, und die Erklaerung des
        # Befunds selbst wuerde den Test brechen.
        for knoten in ast.walk(ast.parse(f.read_text())):
            if (isinstance(knoten, ast.Attribute)
                    and knoten.attr == "bdate_range"):
                treffer.append(f"{f.name}:{knoten.lineno}")

    assert not treffer, (
        f"{treffer} zaehlt wieder Werktage statt Handelstage (§G38)")
