"""Was koennte der Vergleich zeigen - und rechnet er ueberhaupt richtig? (§G22)

**Der Anlass vom 23.08.2026.** Vor der Auswertung am 10.10.2026 wurde
geprueft, ob Kriterium 1 aus `BETRIEBSPLAN` §3.3 korrekt rechnet. Zwei
Ergebnisse, eines beruhigend, eines nicht:

**Der t-Wert ist NICHT aufgeblaeht.** 600 Laeufe auf reinem Rauschen,
beide Depots mit identischer Rangliste und ueberlappenden Positionen:

    Perzentil     gemessen   t-Verteilung
        90 %         1,71         1,69
        95 %         2,04         2,03
      97,5 %         2,42         2,35
        99 %         2,70         2,73

Kolmogorow-Smirnow gegen t(34): p = 0,16. Anders als bei den
ueberlappenden Renditefenstern in §G12 gibt es hier kein
Mehrtages-Fenster - d_t ist eine Eintages-Differenz.

**Die Zeitplanannahme dagegen hielt nicht.** `vergleich_gepaart`
behauptete "Streuung 3-5x kleiner, entscheidbar nach 6-10 Wochen".
Gemessen: B08/B00 3,6x, B04/B00 2,4x, **B11/B09 1,1x**, B07/B00 0,8x.
Fuer den Bot, der am 10.10. entschieden wird, bringt der gepaarte
Vergleich also fast keine Reduktion - und der Zeitbedarf waechst
quadratisch damit.

**Folge:** Ein durchgefallenes Kriterium 1 ohne Trennschaerfe laesst
"nicht besser" und "nicht zeigbar" gleich aussehen. Nur eines davon
rechtfertigt, eine Idee zu verwerfen.
"""

from __future__ import annotations

import math

import pytest

from alpaca_bot import fleet, shadow_eval
from alpaca_bot.shadow import ShadowStore


@pytest.fixture
def buch(tmp_path):
    s = ShadowStore(tmp_path / "shadow.sqlite")
    fleet.anmelden("B00_basis", name="Basis", familie="basis",
                   hypothese="Der unveraenderte Ausgangsstand als Referenz.",
                   basis_bot=None, store=s)
    fleet.anmelden("BX", name="Kandidat", familie="ausstieg",
                   achse="zeitausstieg_dynamisch", wert="True",
                   aenderung={"zeitausstieg_dynamisch": True},
                   hypothese="Gewinner laufen lassen statt fester Frist.",
                   basis_bot="B00_basis", store=s)
    return s


def _kurve(s, bot, werte, ab="2026-01-01"):
    import pandas as pd

    tage = pd.bdate_range(ab, periods=len(werte))
    with s._conn() as c:
        for tag, w in zip(tage, werte):
            c.execute("INSERT OR REPLACE INTO equity_kurve VALUES (?,?,?,?,?)",
                      (bot, tag.strftime("%Y-%m-%d"), float(w), 0.0, 0))


class TestTrennschaerfeRechnung:
    """Die Formel: (schwelle + 0.84) * s / sqrt(n)."""

    def test_rechnet_die_dokumentierte_formel(self, buch):
        # Konstruiert: B schwankt gar nicht, A schwankt gleichmaessig.
        a = [100.0, 101.0, 100.0, 101.0, 100.0, 101.0, 100.0, 101.0,
             100.0, 101.0, 100.0, 101.0]
        _kurve(buch, "BX", a)
        _kurve(buch, "B00_basis", [100.0] * len(a))
        t = shadow_eval.trennschaerfe("BX", "B00_basis", buch)

        erwartet = ((t["schwelle"] + shadow_eval.Z_GUETE_80)
                    * t["streuung"] / math.sqrt(t["n_tage"]))
        # `abs=` statt `rel=`: Beide Werte sind auf 6 Stellen gerundet -
        # das ist Absicht (Lesbarkeit), erlaubt aber keinen exakten
        # Vergleich mit der aus der gerundeten Streuung nachgebauten Zahl.
        assert t["mit_80_prozent"] == pytest.approx(erwartet, abs=1e-6)
        assert t["gerade_noch"] == pytest.approx(
            t["schwelle"] * t["streuung"] / math.sqrt(t["n_tage"]), abs=1e-6)

    def test_achtzig_prozent_ist_strenger_als_gerade_noch(self, buch):
        """Ein Effekt genau auf der Schwelle wird nur in 50 % gefunden."""
        _kurve(buch, "BX", [100 + (i % 2) for i in range(12)])
        _kurve(buch, "B00_basis", [100.0] * 12)
        t = shadow_eval.trennschaerfe("BX", "B00_basis", buch)
        assert t["mit_80_prozent"] > t["gerade_noch"]

    def test_mehr_tage_senken_die_huerde_mit_wurzel_n(self, buch):
        _kurve(buch, "BX", [100 + (i % 2) for i in range(12)])
        _kurve(buch, "B00_basis", [100.0] * 12)
        klein = shadow_eval.trennschaerfe("BX", "B00_basis", buch, n_tage=25)
        gross = shadow_eval.trennschaerfe("BX", "B00_basis", buch, n_tage=100)
        assert gross["mit_80_prozent"] == pytest.approx(
            klein["mit_80_prozent"] / 2, rel=1e-6), (
            "Vierfache Tageszahl muss die Huerde halbieren - sonst stimmt "
            "die Wurzel-n-Abhaengigkeit nicht."
        )

    def test_kumuliert_ist_effekt_mal_tage(self, buch):
        _kurve(buch, "BX", [100 + (i % 2) for i in range(12)])
        _kurve(buch, "B00_basis", [100.0] * 12)
        t = shadow_eval.trennschaerfe("BX", "B00_basis", buch, n_tage=31)
        assert t["kumuliert_80"] == pytest.approx(
            t["mit_80_prozent"] * 31, rel=1e-6)

    def test_hoehere_streuung_hebt_die_huerde(self, buch):
        _kurve(buch, "BX", [100 + (i % 2) for i in range(12)])
        _kurve(buch, "B00_basis", [100.0] * 12)
        leise = shadow_eval.trennschaerfe("BX", "B00_basis", buch, n_tage=31)

        s2 = ShadowStore(buch.path.parent / "laut.sqlite")
        _kurve(s2, "BX", [100 + 5 * (i % 2) for i in range(12)])
        _kurve(s2, "B00_basis", [100.0] * 12)
        laut = shadow_eval.trennschaerfe("BX", "B00_basis", s2, n_tage=31)
        assert laut["mit_80_prozent"] > leise["mit_80_prozent"]


class TestTrennschaerfeGrenzfaelle:
    """Was passiert, wenn nichts zu messen ist."""

    def test_bitgleiche_bots_werden_benannt(self, buch):
        """B09/B08 und B05/B00 waren genau das (§G16 Fund 1)."""
        _kurve(buch, "BX", [100.0, 101.0, 102.0, 103.0, 104.0, 105.0])
        _kurve(buch, "B00_basis", [100.0, 101.0, 102.0, 103.0, 104.0, 105.0])
        t = shadow_eval.trennschaerfe("BX", "B00_basis", buch)
        assert t["mit_80_prozent"] is None
        assert "bitgleich" in t["hinweis"], (
            "Streuung 0 heisst NICHT 'beliebig kleiner Effekt nachweisbar', "
            "sondern 'die Bots sind identisch'. Ohne Hinweis saehe die "
            "Ausgabe wie perfekte Trennschaerfe aus."
        )

    def test_ohne_kurve_kein_ergebnis(self, buch):
        t = shadow_eval.trennschaerfe("BX", "B00_basis", buch)
        assert t["mit_80_prozent"] is None and t["hinweis"]

    def test_zu_wenige_tage_werden_benannt(self, buch):
        _kurve(buch, "BX", [100.0, 101.0])
        _kurve(buch, "B00_basis", [100.0, 100.0])
        t = shadow_eval.trennschaerfe("BX", "B00_basis", buch)
        assert t["mit_80_prozent"] is None
        assert "Tage" in t["hinweis"]

    def test_nutzt_die_registrierte_basis(self, buch):
        """Wie `kriterien_pruefen` - kein hartkodierter Standard (§G19)."""
        _kurve(buch, "BX", [100 + (i % 2) for i in range(12)])
        _kurve(buch, "B00_basis", [100.0] * 12)
        assert shadow_eval.trennschaerfe("BX", store=buch)["basis"] == "B00_basis"


class TestAbnahmeZeigtDieTrennschaerfe:
    """Ein 'durchgefallen' ohne diese Zahl ist eine irrefuehrende Auswertung."""

    def test_text_nennt_die_nachweisgrenze(self, buch):
        _kurve(buch, "BX", [100 + (i % 2) for i in range(12)])
        _kurve(buch, "B00_basis", [100.0] * 12)
        text = shadow_eval.kriterien_text("BX", "B00_basis", buch)
        assert "TRENNSCHAERFE" in text
        assert "%/Tag" in text

    def test_text_warnt_vor_der_verwechslung(self, buch):
        """'Nicht zeigbar' ist nicht 'widerlegt'."""
        _kurve(buch, "BX", [100 + (i % 2) for i in range(12)])
        _kurve(buch, "B00_basis", [100.0] * 12)
        text = shadow_eval.kriterien_text("BX", "B00_basis", buch)
        assert "NICHT WEISBAR" in text and "WIDERLEGT" in text

    def test_auch_bei_bitgleichen_bots_verstaendlich(self, buch):
        _kurve(buch, "BX", [100.0, 101.0, 102.0, 103.0, 104.0, 105.0])
        _kurve(buch, "B00_basis", [100.0, 101.0, 102.0, 103.0, 104.0, 105.0])
        text = shadow_eval.kriterien_text("BX", "B00_basis", buch)
        assert "bitgleich" in text
