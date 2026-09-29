"""Makro- und GDELT-Regimedaten: Zeitpunktsicherheit und Bandtest.

**Die wichtigste Zusicherung, die hier gesichert wird:** Kein Merkmal
darf einen Wert benutzen, der am jeweiligen Tag noch nicht bekannt war.
Bei Makrodaten gibt es dafuer zwei Wege ins Verderben, und beide werden
hier geprueft:

  1. `bfill` statt `ffill` - ein Wert von morgen wird auf heute gelegt.
  2. Zentrierte statt rollende Fenster - der Mittelwert eines Fensters,
     das in die Zukunft reicht.

Dazu die Strukturentscheidung aus `makro.py`: Wirtschaftsstatistik wird
revidiert und ist ohne ALFRED-Vintages nicht zeitpunktsicher. Der Test
`test_revidierte_reihen_werden_nicht_geladen` haelt fest, dass diese
Reihen bewusst draussen bleiben - damit niemand sie spaeter arglos
dazunimmt.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from alpaca_bot import gdelt, makro


@pytest.fixture
def reihen() -> pd.DataFrame:
    """600 Handelstage synthetische Makroreihen."""
    idx = pd.bdate_range("2022-01-03", periods=600)
    rng = np.random.default_rng(7)
    return pd.DataFrame({
        "vix": 15 + rng.normal(0, 3, len(idx)).cumsum() * 0.05 + 5,
        "zins_10j": 3 + rng.normal(0, 0.05, len(idx)).cumsum() * 0.1,
        "zins_3m": 2 + rng.normal(0, 0.05, len(idx)).cumsum() * 0.1,
        "hy_spread": 4 + rng.normal(0, 0.1, len(idx)).cumsum() * 0.05,
    }, index=idx)


# ---------------------------------------------------------------------------
# Zeitpunktsicherheit
# ---------------------------------------------------------------------------
class TestKeinLookahead:
    def test_merkmale_aendern_sich_nicht_wenn_die_zukunft_wegfaellt(self, reihen):
        """Der Kern: Ein Merkmal an Tag t darf nur von Tagen <= t abhaengen.

        Wird die Reihe nach Tag t abgeschnitten, muessen alle Werte bis t
        exakt gleich bleiben. Ein zentriertes Fenster oder ein `bfill`
        wuerde hier sofort auffallen.
        """
        voll = makro.regime_merkmale(reihen)
        schnitt = 400
        gekuerzt = makro.regime_merkmale(reihen.iloc[:schnitt])

        for spalte in gekuerzt.columns:
            a = voll[spalte].iloc[:schnitt]
            b = gekuerzt[spalte]
            pd.testing.assert_series_equal(a, b, check_names=False,
                                           check_freq=False)

    def test_reindex_auf_kalender_fuellt_nur_vorwaerts(self, reihen):
        """Ein Handelstag ohne Makrowert bekommt den LETZTEN bekannten -
        nie den naechsten."""
        # Kalender mit einem Tag, der vor dem Beginn der Reihe liegt.
        kalender = pd.DatetimeIndex(
            [pd.Timestamp("2021-12-01"), *reihen.index[:50]])
        m = makro.regime_merkmale(reihen, kalender)
        # Vor dem ersten bekannten Wert darf NICHTS stehen (kein bfill).
        assert m.iloc[0].isna().all()

    def test_gdelt_merkmale_sind_ebenfalls_rueckwaertsgewandt(self):
        idx = pd.bdate_range("2022-01-03", periods=400)
        rng = np.random.default_rng(3)
        roh = pd.DataFrame({"stress_ton": rng.normal(0, 1, len(idx)),
                           "stress_artikel": rng.integers(10, 500, len(idx))},
                          index=idx)
        voll = gdelt.merkmale(roh)
        gekuerzt = gdelt.merkmale(roh.iloc[:300])
        for spalte in gekuerzt.columns:
            pd.testing.assert_series_equal(
                voll[spalte].iloc[:300], gekuerzt[spalte],
                check_names=False, check_freq=False)


def test_revidierte_reihen_werden_nicht_geladen():
    """Wirtschaftsstatistik ist ohne ALFRED-Vintages nicht zeitpunktsicher.

    Sie steht in `REIHEN_REVIDIERT` als Merkposten, darf aber in
    `REIHEN_OHNE_REVISION` nicht auftauchen - sonst wuerde `lade_reihen`
    sie ziehen und still Lookahead einbauen.
    """
    ueberschneidung = set(makro.REIHEN_REVIDIERT) & set(makro.REIHEN_OHNE_REVISION)
    assert not ueberschneidung, (
        f"Revidierte Reihen in der zeitpunktsicheren Liste: {ueberschneidung}")


def test_jede_revisionsfreie_reihe_nennt_grund_und_quelle():
    """Eine Reihe ohne Begruendung ist eine geratene Reihe (§J Regel 2)."""
    for name, cfg in makro.REIHEN_OHNE_REVISION.items():
        assert cfg.get("was"), f"{name}: keine Beschreibung"
        assert cfg.get("warum"), f"{name}: keine Begruendung"
        assert cfg.get("fred") or cfg.get("yf"), f"{name}: keine Quelle"


# ---------------------------------------------------------------------------
# Regimetest
# ---------------------------------------------------------------------------
class TestRegimeAuswertung:
    def test_findet_einen_eingebauten_regimeunterschied(self):
        """Konstruiert: Das Merkmal des VORTAGS sagt die Rendite voraus.

        Wegen `lag=1` muss das Merkmal um einen Tag versetzt eingebaut
        werden - sonst findet der Test es korrekterweise NICHT.
        """
        idx = pd.bdate_range("2020-01-01", periods=500)
        rng = np.random.default_rng(11)
        merkmal = pd.Series(rng.uniform(0, 1, len(idx)), index=idx)
        # Die Rendite von Tag t haengt am Merkmal von Tag t-1.
        rendite = pd.Series(
            np.where(merkmal.shift(1) > 0.5, 0.004, -0.004)
            + rng.normal(0, 0.001, len(idx)), index=idx).dropna()

        tab = makro.regime_auswertung(rendite, merkmal, n_baender=2)
        assert len(tab) == 2
        assert tab["mittel"].max() > 0
        assert tab["mittel"].min() < 0
        assert tab["t"].abs().min() > 2

    def test_gleichzeitiger_zusammenhang_wird_mit_lag_nicht_gefunden(self):
        """**Der wichtigste Test dieses Moduls** (25.08.2026).

        Konstruiert wird ein rein GLEICHZEITIGER Zusammenhang: Die
        Rendite von Tag t haengt am Merkmal von Tag t, aber der Vortag
        sagt nichts. Genau so verhaelt sich ein Marktmass wie die
        VIX-Aenderung - ein steigender VIX IST ein fallender Markt.

        Mit `lag=0` sieht das nach einem gewaltigen Befund aus; mit dem
        Standard `lag=1` darf NICHTS uebrig bleiben. Faellt dieser Test
        um, ist die Tautologie zurueck.
        """
        idx = pd.bdate_range("2020-01-01", periods=600)
        rng = np.random.default_rng(17)
        merkmal = pd.Series(rng.uniform(0, 1, len(idx)), index=idx)
        rendite = pd.Series(
            np.where(merkmal > 0.5, 0.004, -0.004) + rng.normal(0, 0.0005, len(idx)),
            index=idx)

        gleichzeitig = makro.regime_auswertung(rendite, merkmal, n_baender=2, lag=0)
        versetzt = makro.regime_auswertung(rendite, merkmal, n_baender=2, lag=1)

        # Gleichzeitig: riesiger Effekt (die eingebaute Tautologie).
        assert gleichzeitig["t"].abs().min() > 5
        # Versetzt: nichts davon uebrig - der Vortag weiss es nicht.
        assert versetzt["t"].abs().max() < 3

    def test_ohne_echten_unterschied_kein_auffaelliger_t_wert(self):
        """Reines Rauschen darf keine Baender mit hohem t erzeugen."""
        idx = pd.bdate_range("2020-01-01", periods=500)
        rng = np.random.default_rng(23)
        merkmal = pd.Series(rng.uniform(0, 1, len(idx)), index=idx)
        rendite = pd.Series(rng.normal(0, 0.01, len(idx)), index=idx)

        tab = makro.regime_auswertung(rendite, merkmal, n_baender=4)
        assert not tab.empty
        # Bei reinem Rauschen sollte kein Band deutlich ueber 2 liegen.
        assert tab["t"].abs().max() < 3.0

    def test_zu_wenig_daten_liefert_leere_tabelle_statt_zahlen(self):
        idx = pd.bdate_range("2020-01-01", periods=30)
        rng = np.random.default_rng(5)
        tab = makro.regime_auswertung(
            pd.Series(rng.normal(0, 0.01, len(idx)), index=idx),
            pd.Series(rng.uniform(0, 1, len(idx)), index=idx), n_baender=4)
        assert tab.empty

    def test_gruppiert_nach_monat_nicht_nach_tag(self):
        """Massgeblich ist die Zahl der Monate - sonst waeren benachbarte
        Tage faelschlich unabhaengige Beobachtungen (§B1)."""
        idx = pd.bdate_range("2020-01-01", periods=500)
        rng = np.random.default_rng(31)
        tab = makro.regime_auswertung(
            pd.Series(rng.normal(0.001, 0.01, len(idx)), index=idx),
            pd.Series(rng.uniform(0, 1, len(idx)), index=idx), n_baender=2)
        assert "n_monate" in tab.columns
        # 500 Handelstage sind ~24 Monate, verteilt auf 2 Baender.
        assert tab["n_monate"].max() < tab["n_tage"].max()


# ---------------------------------------------------------------------------
# GDELT-Namensdisziplin
# ---------------------------------------------------------------------------
def test_gdelt_kennt_nur_eindeutige_firmennamen():
    """Mehrdeutige Namen wuerden fremde Artikel zaehlen - kein schwaches
    Signal, sondern ein falsches."""
    mehrdeutig = {"AAPL", "TGT", "GPS", "V", "F", "GAP", "KEY", "ALL"}
    treffer = mehrdeutig & set(gdelt.FIRMENNAMEN)
    assert not treffer, f"Mehrdeutige Symbole in FIRMENNAMEN: {treffer}"


def test_gdelt_ueberspringt_unbekannte_symbole_ohne_zu_raten():
    out = gdelt.je_symbol(["EIN_SYMBOL_DAS_ES_NICHT_GIBT"], verbose=False)
    assert out == {}


def test_gdelt_leeres_ergebnis_ergibt_leeren_frame():
    assert gdelt._als_frame({}).empty
    assert gdelt._als_frame({"timeline": []}).empty
    assert gdelt._als_frame({"timeline": [{"data": []}]}).empty


def test_gdelt_legt_keine_stumme_artikelspalte_an():
    """§G13-Fehlerklasse: eine Spalte, die immer NaN ist, sieht wie eine
    Messgroesse aus und ist keine.

    Der Modus `timelinetone` liefert KEINE Artikelzahl. Die erste Fassung
    legte trotzdem `artikel` an und fuellte sie mit NaN - gemessen am
    25.08.2026: 923 von 923 Tagen leer.
    """
    roh = {"timeline": [{"data": [
        {"date": "2024-01-01T00:00:00Z", "value": -1.5},
        {"date": "2024-01-02T00:00:00Z", "value": -0.8},
    ]}]}
    df = gdelt._als_frame(roh)

    assert list(df.columns) == ["tag", "ton"]
    assert "artikel" not in df.columns
    # Und keine Spalte darf durchgehend leer sein.
    assert not any(df[c].isna().all() for c in df.columns)
