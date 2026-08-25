"""Das Kandidatenregister: die Zwischenstufe aus `docs/UMBAUPLAN.md` Schritt 5.

Drei Dinge muss es erzwingen, sonst ist es nur eine Tabelle:

  1. Keine Voranmeldung ohne Hypothese (§J Regel 2).
  2. Keine doppelte Anmeldung derselben `kandidat_id` - eine Voranmeldung,
     die sich ueberschreiben liesse, waere keine.
  3. Kein Sprung im Statusvertrag (z. B. "gefunden" direkt zu "abgenommen") -
     das wuerde Schattenbot und Abnahme nach BETRIEBSPLAN §3.3 umgehen.
"""

from __future__ import annotations

import pytest

from alpaca_bot import kandidatenregister as kr
from alpaca_bot.lernlauf_store import LernlaufStore


@pytest.fixture
def store(tmp_path):
    return LernlaufStore(tmp_path / "lernlauf.sqlite")


def test_anmelden_und_liste(store):
    kr.anmelden("K01", achse="min_score", wert="0.45",
               hypothese="Historienlauf: t=+2.1 ueber 12 Jahresscheiben",
               n_varianten_getestet=14, store=store)
    df = kr.liste(store)
    assert len(df) == 1
    assert df.iloc[0]["status"] == "gefunden"
    assert df.iloc[0]["n_varianten_getestet"] == 14


def test_anmelden_ohne_hypothese_schlaegt_fehl(store):
    with pytest.raises(ValueError, match="Hypothese"):
        kr.anmelden("K02", achse="x", wert="1", hypothese="  ",
                   n_varianten_getestet=1, store=store)


def test_doppelte_anmeldung_schlaegt_fehl(store):
    kr.anmelden("K03", achse="x", wert="1", hypothese="erste Anmeldung",
               n_varianten_getestet=1, store=store)
    with pytest.raises(ValueError, match="bereits angemeldet"):
        kr.anmelden("K03", achse="x", wert="2", hypothese="zweite Anmeldung",
                   n_varianten_getestet=1, store=store)


def test_erlaubter_statusweg(store):
    kr.anmelden("K04", achse="x", wert="1", hypothese="h", n_varianten_getestet=1,
               store=store)
    kr.status_setzen("K04", "im_schatten", store=store)
    kr.status_setzen("K04", "abgenommen", store=store)
    df = kr.liste(store)
    assert df.iloc[0]["status"] == "abgenommen"


def test_uebersprungener_status_schlaegt_fehl(store):
    """gefunden -> abgenommen ohne Schattenbot und Abnahme ist verboten."""
    kr.anmelden("K05", achse="x", wert="1", hypothese="h", n_varianten_getestet=1,
               store=store)
    with pytest.raises(ValueError, match="nicht erlaubt"):
        kr.status_setzen("K05", "abgenommen", store=store)


def test_endzustand_hat_keinen_weiteren_uebergang(store):
    kr.anmelden("K06", achse="x", wert="1", hypothese="h", n_varianten_getestet=1,
               store=store)
    kr.status_setzen("K06", "verworfen", store=store)
    with pytest.raises(ValueError, match="nicht erlaubt"):
        kr.status_setzen("K06", "im_schatten", store=store)


def test_status_setzen_auf_unbekannten_kandidaten_schlaegt_fehl(store):
    with pytest.raises(ValueError, match="nicht angemeldet"):
        kr.status_setzen("UNBEKANNT", "im_schatten", store=store)


def test_ergebnis_eintragen_aktualisiert_nur_uebergebene_felder(store):
    kr.anmelden("K07", achse="x", wert="1", hypothese="h", n_varianten_getestet=1,
               store=store)
    kr.ergebnis_eintragen("K07", hist_t=2.4, store=store)
    df = kr.liste(store)
    assert df.iloc[0]["hist_t"] == pytest.approx(2.4)
    assert df.iloc[0]["hist_effekt_pro_tag"] is None

    kr.ergebnis_eintragen("K07", hist_effekt_pro_tag=0.001, store=store)
    df = kr.liste(store)
    # hist_t bleibt erhalten, obwohl es beim zweiten Aufruf nicht uebergeben wurde.
    assert df.iloc[0]["hist_t"] == pytest.approx(2.4)
    assert df.iloc[0]["hist_effekt_pro_tag"] == pytest.approx(0.001)


def test_bericht_mit_nur_t_wert_ohne_effekt_stuerzt_nicht_ab(store):
    """Vorfall vom 25.08.2026 (K02_trailing_15j): `ergebnis_eintragen` nur
    mit `hist_t` aufgerufen, `hist_effekt_pro_tag` blieb NULL. `bericht()`
    prüfte nur `hist_t` auf NaN und formatierte danach `hist_effekt_pro_tag`
    ungeprüft - TypeError bei jedem Kandidaten in genau dieser Lage."""
    kr.anmelden("K08", achse="trail_after_atr", wert="1.5", hypothese="h",
               n_varianten_getestet=14, store=store)
    kr.ergebnis_eintragen("K08", hist_t=-3.53, hist_fenster=15, store=store)

    text = kr.bericht(store)

    assert "K08" in text
    assert "t=-3.53" in text
    assert "Fenster=15 Jahre" in text
    assert "/Tag" not in text.split("K08")[1].split("K0")[0]  # kein Effekt-Anteil erfunden


def test_bericht_ohne_jedes_historiefeld_zeigt_keine_hist_zeile(store):
    kr.anmelden("K09", achse="x", wert="1", hypothese="h", n_varianten_getestet=1,
               store=store)
    text = kr.bericht(store)
    assert "hist:" not in text
