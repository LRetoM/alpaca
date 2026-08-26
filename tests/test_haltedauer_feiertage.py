"""Haltedauer: Live zaehlt Werktage, Simulation und Schatten Handelstage (§G38).

**Der Fund (26.08.2026).** Die Haltedauer, an der `max_hold_days`
haengt, wird auf zwei verschiedene Arten gezaehlt:

    live.build_portfolio()   len(pd.bdate_range(einstieg, heute)) - 1
    lifecycle.handelstage()  dieselbe Rechnung
    simulate / shadow        engine.update_position(), einmal je BAR

`pd.bdate_range` zaehlt Montag bis Freitag. Es kennt keine
Boersenfeiertage. Die Simulation dagegen laeuft ueber den echten
Bar-Kalender - ein Feiertag existiert dort schlicht nicht.

**Folge:** In jeder Woche mit einem Feiertag haelt der Live-Bot eine
Position einen Handelstag KUERZER als Simulation und Schatten, weil der
geschlossene Tag live mitgezaehlt wird. Die Achse `max_hold_days=5` ist
damit live faktisch eine 4-Tage-Regel - aber nur in Feiertagswochen.

**Warum dieser Test die falsche Zahl festschreibt.** Der Fehler ist am
26.08.2026 dokumentiert und BEWUSST nicht sofort behoben worden: Eine
Korrektur verschiebt live den Verkaufszeitpunkt und ist damit eine
Aenderung an der Handelslogik (CLAUDE.md). Dieser Test haelt den
Ist-Zustand fest, damit die Abweichung nicht unbemerkt bleibt und damit
eine spaetere Korrektur hier sichtbar auffliegt statt still zu passieren.

Erster Feiertag im laufenden Betrieb: **Labor Day, Montag 07.09.2026.**
Bis dahin ist der Fehler nie aufgetreten - der Live-Bot handelt seit
Ende Juli 2026, und dazwischen lag kein Boersenfeiertag.
"""

from __future__ import annotations

import pandas as pd

from alpaca_bot.lifecycle import handelstage

LABOR_DAY_2026 = "2026-09-07"
"""Montag. NYSE und Nasdaq geschlossen - `pd.bdate_range` zaehlt ihn mit."""


def test_bdate_range_zaehlt_den_feiertag_mit():
    """Der Kern: Labor Day ist ein Werktag, aber kein Handelstag."""
    werktage = pd.bdate_range("2026-09-03", "2026-09-10")
    assert pd.Timestamp(LABOR_DAY_2026) in werktage, (
        "pd.bdate_range kennt keine Boersenfeiertage - faellt das weg, "
        "ist §G38 behoben und dieser Test gehoert angepasst"
    )


def test_live_zaehlweise_ueber_labor_day():
    """Einstieg Do 03.09., Stichtag Do 10.09.

    Echte Handelstage dazwischen: 04.09. (Fr), 08.09. (Di), 09.09. (Mi),
    10.09. (Do) = **4**. Der Montag faellt aus.
    `lifecycle.handelstage` - dieselbe Rechnung wie `build_portfolio` -
    liefert **5**.
    """
    assert handelstage("2026-09-03", "2026-09-10") == 5, (
        "Die Live-Zaehlweise liefert nicht mehr 5 - entweder ist §G38 "
        "behoben (dann diesen Test und §G4 nachziehen) oder die "
        "Zaehlweise hat sich unbemerkt geaendert"
    )


def test_abweichung_betrifft_genau_die_feiertagswoche():
    """Ohne Feiertag stimmen beide Zaehlweisen ueberein.

    Damit ist belegt, dass der Unterschied AM FEIERTAG haengt und nicht
    an einem generellen Off-by-one - sonst waere der Befund harmlos.
    """
    # Do 17.09. bis Do 24.09.2026 - kein Feiertag.
    assert handelstage("2026-09-17", "2026-09-24") == 5

    # Dieselbe Kalenderspanne ueber Labor Day - ebenfalls 5, obwohl
    # nur 4 Handelstage stattfinden.
    assert handelstage("2026-09-03", "2026-09-10") == 5


def test_max_hold_days_greift_live_einen_tag_frueher():
    """Die wirtschaftliche Folge, an einer konkreten Zahl.

    `EngineConfig.for_reversal().max_hold_days` ist 5 und wird gegen
    `pos.bars_held >= max_hold_days` geprueft (engine.py). Live ist die
    Bedingung nach dem 4. echten Handelstag erfuellt, in Simulation und
    Schatten erst nach dem 5.
    """
    from alpaca_bot.engine import EngineConfig

    cfg = EngineConfig.for_reversal()
    live_zaehlung = handelstage("2026-09-03", "2026-09-10")
    echte_handelstage = 4  # 04.09., 08.09., 09.09., 10.09.

    assert live_zaehlung >= cfg.max_hold_days
    assert echte_handelstage < cfg.max_hold_days, (
        "Live steigt aus, Simulation und Schatten halten noch - "
        "genau die Divergenz aus §G38"
    )
