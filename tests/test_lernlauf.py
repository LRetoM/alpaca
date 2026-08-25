"""Der Lernlauf: gepaarter Test, Trennschaerfe, und vor allem Walk-Forward.

**Warum dieser letzte Punkt eigens gesichert wird.** `docs/UMBAUPLAN.md`
§4 nennt ihn den wichtigsten Abnahmepunkt des ganzen Umbaus: "Ohne ihn
ist die Trennung eine Behauptung." Die Auswahl fuer ein Bewertungsjahr
darf ausschliesslich fruehere Jahre sehen - sonst waere der Lernlauf
nicht schneller als der Vorwaertsbetrieb, sondern nur ein Rueckblick, der
sich selbst bestaetigt.

`TestWalkForwardSiehtBewertungsjahrNicht` ist bewusst so konstruiert,
dass ein einziges konkretes Datenbeispiel zwei verschiedene Antworten
gibt, je nachdem, ob das Bewertungsjahr in die Auswahl einfliesst:

    korrekt (nur Vorjahre)      -> Bot A gewaehlt
    Leck (inkl. Bewertungsjahr) -> Bot B gewaehlt

Eine Mutation, die `scheiben[:idx]` zu `scheiben[:idx + 1]` macht,
wechselt damit `zeilen[0].gewaehlt` von "A" zu "B" - der Test wird rot.
Siehe `scripts/23_mutationstest.py`, Abschnitt "Lernlauf: Walk-Forward".
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from alpaca_bot import lernlauf_eval
from alpaca_bot.lernlauf_store import LernlaufStore


# ---------------------------------------------------------------------------
# Walk-Forward
# ---------------------------------------------------------------------------
class TestWalkForwardSiehtBewertungsjahrNicht:
    def _jahres(self) -> pd.DataFrame:
        # basis: konstant 0 - macht "diff" gleich der Rendite des gewaehlten
        # Bots und die Auswahl leicht nachvollziehbar.
        # A: stark in 2020-2022, bricht 2023 ein.
        # B: schwach in 2020-2022, glaenzt 2023.
        return pd.DataFrame({
            2020: {"basis": 0.0, "A": 0.10, "B": -0.10},
            2021: {"basis": 0.0, "A": 0.10, "B": -0.10},
            2022: {"basis": 0.0, "A": 0.10, "B": -0.10},
            2023: {"basis": 0.0, "A": -0.50, "B": 0.50},
        })

    def _scheiben(self):
        return [(j, None, None) for j in (2020, 2021, 2022, 2023)]

    def test_waehlt_nach_vorjahren_nicht_nach_dem_bewertungsjahr_selbst(self):
        zeilen = lernlauf_eval.walk_forward_auswahl(
            self._jahres(), self._scheiben(), min_auswahl_jahre=3, basis="basis")

        assert len(zeilen) == 1
        z = zeilen[0]
        assert z.jahr == 2023
        # Mit nur 2020-2022 sichtbar ist A (Mittel +0.10) klar vor B
        # (Mittel -0.10) und vor der Basis (0.0) - A wird gewaehlt.
        assert z.gewaehlt == "A"
        assert z.rendite_gewaehlt == pytest.approx(-0.50)
        assert z.diff == pytest.approx(-0.50)

    def test_mutation_die_das_bewertungsjahr_mit_ansieht_waere_falsch(self):
        """Dieselbe Rechnung, aber mit dem LECK von Hand nachgebaut - als
        Beleg, dass die korrekte und die durchgesickerte Antwort wirklich
        verschieden sind (sonst waere die obige Prüfung zufällig blind)."""
        jahres = self._jahres()
        # Nachbau der Mutation: Mittel ueber scheiben[:idx + 1] statt
        # scheiben[:idx] - das Bewertungsjahr fliesst in die eigene Auswahl ein.
        mittel_mit_leck = jahres[[2020, 2021, 2022, 2023]].mean(axis=1)
        assert mittel_mit_leck.idxmax() == "B"          # falsch: B statt A

        mittel_korrekt = jahres[[2020, 2021, 2022]].mean(axis=1)
        assert mittel_korrekt.idxmax() == "A"            # richtig

    def test_min_auswahl_jahre_wird_eingehalten(self):
        jahres = self._jahres()
        scheiben = self._scheiben()
        # Mit min_auswahl_jahre=4 gibt es keine Zelle mehr, die genug
        # Vorjahre hat (nur 4 Jahre insgesamt vorhanden).
        zeilen = lernlauf_eval.walk_forward_auswahl(
            jahres, scheiben, min_auswahl_jahre=4, basis="basis")
        assert zeilen == []

    def test_zeilen_bleiben_chronologisch(self):
        jahres = pd.DataFrame({
            j: {"basis": 0.0, "A": 0.01 * j} for j in range(2000, 2010)
        })
        scheiben = [(j, None, None) for j in range(2000, 2010)]
        zeilen = lernlauf_eval.walk_forward_auswahl(
            jahres, scheiben, min_auswahl_jahre=3, basis="basis")
        jahre = [z.jahr for z in zeilen]
        assert jahre == sorted(jahre)


class TestWalkForwardTest:
    def test_zu_wenig_jahre_liefert_keinen_t_wert(self):
        zeilen = [lernlauf_eval.WalkForwardZeile(2020, "A", 0.1, 0.0, 0.1),
                 lernlauf_eval.WalkForwardZeile(2021, "A", 0.1, 0.0, 0.1)]
        t = lernlauf_eval.walk_forward_test(zeilen)
        assert t.t_wert is None
        assert t.hinweis

    def test_konstante_differenz_ergibt_keinen_t_wert_bei_streuung_null(self):
        # Alle Differenzen identisch -> Standardabweichung 0 -> t undefiniert,
        # nicht "unendlich" oder ein Absturz.
        zeilen = [lernlauf_eval.WalkForwardZeile(j, "A", 0.1, 0.0, 0.1)
                 for j in range(2020, 2025)]
        t = lernlauf_eval.walk_forward_test(zeilen)
        assert t.t_wert is None

    def test_wechsel_zaehlt_bot_uebergaenge(self):
        zeilen = [
            lernlauf_eval.WalkForwardZeile(2020, "A", 0.1, 0.0, 0.1),
            lernlauf_eval.WalkForwardZeile(2021, "A", 0.1, 0.0, 0.1),
            lernlauf_eval.WalkForwardZeile(2022, "B", 0.2, 0.0, 0.2),
            lernlauf_eval.WalkForwardZeile(2023, "C", -0.1, 0.0, -0.1),
        ]
        t = lernlauf_eval.walk_forward_test(zeilen)
        assert t.wechsel == 2


# ---------------------------------------------------------------------------
# Gepaarter Test / Trennschaerfe - dieselbe Rechnung wie shadow_eval,
# hier gegen von Hand vorgegebene Kurven statt gegen eine ShadowStore-DB.
# ---------------------------------------------------------------------------
class TestPaarweiserTest:
    def test_rechnet_den_einfachen_t_wert_richtig(self):
        tage = pd.bdate_range("2024-01-01", periods=12)
        a = pd.Series([100.0, 101.0] * 6, index=tage)
        b = pd.Series([100.0] * 12, index=tage)
        erg = lernlauf_eval.paarweiser_test(a, b, schwelle=2.0)

        d = a.pct_change().dropna() - b.pct_change().dropna()
        erwartet_t = d.mean() / (d.std(ddof=1) / math.sqrt(len(d)))
        assert erg.t_wert == pytest.approx(erwartet_t, abs=1e-4)
        assert erg.n_tage == len(d)

    def test_zu_wenig_tage_liefert_kein_ergebnis(self):
        tage = pd.bdate_range("2024-01-01", periods=2)
        erg = lernlauf_eval.paarweiser_test(
            pd.Series([100.0, 101.0], index=tage),
            pd.Series([100.0, 100.0], index=tage), schwelle=2.0)
        assert erg.t_wert is None
        assert erg.hinweis

    def test_bitgleiche_kurven_ergeben_keinen_t_wert(self):
        tage = pd.bdate_range("2024-01-01", periods=25)
        a = pd.Series(np.linspace(100, 110, 25), index=tage)
        erg = lernlauf_eval.paarweiser_test(a, a.copy(), schwelle=2.0)
        assert erg.t_wert is None

    def test_belastbar_braucht_schwelle_und_mindestlaenge(self):
        tage = pd.bdate_range("2024-01-01", periods=30)
        # Stark unterschiedliche, aber wenig streuende Differenz -> hoher t.
        a = pd.Series([100 * 1.01 ** i for i in range(30)], index=tage)
        b = pd.Series([100.0] * 30, index=tage)
        erg = lernlauf_eval.paarweiser_test(a, b, schwelle=2.0, min_tage=20)
        assert erg.belastbar is True
        erg_streng = lernlauf_eval.paarweiser_test(a, b, schwelle=2.0, min_tage=100)
        assert erg_streng.belastbar is False       # zu wenig Tage trotz hohem t


class TestTrennschaerfe:
    def test_formel_stimmt_mit_dokumentiertem_ansatz_ueberein(self):
        tage = pd.bdate_range("2024-01-01", periods=20)
        a = pd.Series([100.0, 101.0] * 10, index=tage)
        b = pd.Series([100.0] * 20, index=tage)
        schwelle = 2.85
        erg = lernlauf_eval.trennschaerfe(a, b, schwelle)

        erwartet_gerade = schwelle * erg.streuung / math.sqrt(erg.n_tage)
        erwartet_80 = (schwelle + lernlauf_eval.Z_GUETE_80) * erg.streuung / math.sqrt(erg.n_tage)
        assert erg.gerade_noch == pytest.approx(erwartet_gerade, abs=1e-6)
        assert erg.mit_80_prozent == pytest.approx(erwartet_80, abs=1e-6)
        assert erg.mit_80_prozent > erg.gerade_noch

    def test_bitgleiche_kurven_melden_das_explizit(self):
        tage = pd.bdate_range("2024-01-01", periods=20)
        a = pd.Series(np.linspace(100, 105, 20), index=tage)
        erg = lernlauf_eval.trennschaerfe(a, a.copy(), schwelle=2.0)
        assert erg.mit_80_prozent is None
        assert "bitgleich" in erg.hinweis


def test_schwelle_sigma_waechst_mit_der_rasterzahl():
    klein = lernlauf_eval.schwelle_sigma(14)
    gross = lernlauf_eval.schwelle_sigma(14 * 12)
    assert gross > klein


# ---------------------------------------------------------------------------
# Persistenz
# ---------------------------------------------------------------------------
def test_lernlauf_store_schreibt_und_liest_alle_tabellen(tmp_path):
    store = LernlaufStore(tmp_path / "lernlauf.sqlite")
    lauf_id = store.lauf_anlegen(code_version="abc123", jahre=15.0, symbole=800,
                                 kapital=30_000.0, min_auswahl_jahre=3,
                                 n_jahresscheiben=12, n_signalgruppen=2)
    assert store.table("laeufe")["lauf_id"].tolist() == [lauf_id]

    store.jahresergebnis_schreiben(lauf_id, "basis", 2020, 0.05, 40, None, None)
    ja = store.table("jahresergebnisse")
    assert len(ja) == 1 and ja.iloc[0]["rendite"] == pytest.approx(0.05)

    paar = lernlauf_eval.PaarVergleich(20, 0.001, 0.01, 1.5, 2.0, False, 20)
    streuung = lernlauf_eval.Trennschaerfe(20, 0.01, 20, 2.0, 0.004, 0.006, 0.12)
    store.bot_vergleich_schreiben(lauf_id, "stop_eng", "basis", paar, streuung)
    bv = store.table("bot_vergleiche")
    assert bv.iloc[0]["t_wert"] == pytest.approx(1.5)

    zeile = lernlauf_eval.WalkForwardZeile(2023, "A", -0.5, 0.0, -0.5)
    store.walkforward_zeile_schreiben(lauf_id, zeile)
    wf = store.table("walkforward_zeilen")
    assert wf.iloc[0]["gewaehlt"] == "A"

    test = lernlauf_eval.WalkForwardTest(1, -0.5, None, 0, 0, hinweis="zu wenig")
    store.walkforward_test_schreiben(lauf_id, test, schwelle=3.0)
    laeufe = store.table("laeufe")
    assert laeufe.iloc[0]["wf_schwelle"] == pytest.approx(3.0)
    assert laeufe.iloc[0]["beendet_am"] is not None
