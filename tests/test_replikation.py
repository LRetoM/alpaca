"""Unabhaengige Replikation derselben Hypothese (§G43).

**Die Luecke.** Bis zum 26.08.2026 zaehlte jeder Test als eigener
Versuch - auch wenn zweimal DIESELBE Frage auf verschiedenen Daten
gestellt wurde. `halten_lang` steht im Schatten bei t=+1,16 und im
15-Jahre-Historienlauf bei t=+2,05. Nach alter Rechnung waren das zwei
Versuche, die beide die Huerde fuer alle anderen erhoehten. Richtig ist
das Gegenteil: Zwei uebereinstimmende Laeufe auf getrennten Daten sind
ein staerkerer Beleg als einer.

**Was diese Tests festhalten:** Die Kombination darf die Schwelle NICHT
senken (sie wird uebergeben, nicht gerechnet), und sie darf einen
Vorzeichenwiderspruch nicht als Replikation ausgeben.
"""

from __future__ import annotations

import pytest

from alpaca_bot import statistik


def test_zwei_gleichgerichtete_laeufe_sind_staerker_als_jeder_einzelne():
    """Der eigentliche Zweck - halten_lang als konkreter Fall."""
    r = statistik.kombiniere_unabhaengig([1.16, 2.05], schwelle=2.85)
    assert r.t_kombiniert == pytest.approx(2.27, abs=0.01)
    assert r.t_kombiniert > max(1.16, 2.05)


def test_die_schwelle_wird_nicht_gesenkt():
    """Replikation spart einen Zaehlerplatz, keine Huerde. halten_lang
    faellt auch kombiniert durch - das ist die richtige Antwort."""
    r = statistik.kombiniere_unabhaengig([1.16, 2.05], schwelle=2.85)
    assert r.schwelle == 2.85
    assert r.belastbar is False


def test_widerspruch_im_vorzeichen_ist_keine_replikation():
    """Zwei Laeufe, die sich widersprechen, duerfen nie 'belastbar'
    ergeben - egal wie der kombinierte Wert ausfaellt."""
    r = statistik.kombiniere_unabhaengig([3.5, -3.4], schwelle=1.0)
    assert r.belastbar is False
    assert "Vorzeichen" in r.hinweis


def test_ein_einzelner_lauf_ist_keine_replikation():
    r = statistik.kombiniere_unabhaengig([3.0], schwelle=2.85)
    assert r.n_laeufe == 1
    assert "keine Replikation" in r.hinweis
    assert r.belastbar is True   # ueber der Schwelle bleibt ueber der Schwelle


def test_gewichtung_nach_gruppenzahl_zaehlt_den_grossen_lauf_hoeher():
    """Ein Lauf ueber 3.767 Handelstage wiegt mehr als einer ueber 16.
    Mit Gewichtung faellt der kombinierte Wert hier NIEDRIGER aus, weil
    der schwache Wert aus dem grossen Lauf dominiert - genau richtig."""
    ohne = statistik.kombiniere_unabhaengig([2.05, 1.16], schwelle=2.85)
    mit = statistik.kombiniere_unabhaengig(
        [2.05, 1.16], schwelle=2.85, gewichte=[3767 ** 0.5, 16 ** 0.5])
    assert mit.t_kombiniert < ohne.t_kombiniert


def test_gleiche_laeufe_skalieren_mit_wurzel_n():
    """Vier identische Laeufe mit t=1 ergeben t=2, nicht t=4."""
    r = statistik.kombiniere_unabhaengig([1.0] * 4, schwelle=2.85)
    assert r.t_kombiniert == pytest.approx(2.0)


def test_ungueltige_gewichte_werden_abgelehnt():
    with pytest.raises(ValueError):
        statistik.kombiniere_unabhaengig([1.0, 2.0], 2.85, gewichte=[1.0, 0.0])
    with pytest.raises(ValueError):
        statistik.kombiniere_unabhaengig([1.0, 2.0], 2.85, gewichte=[1.0])
