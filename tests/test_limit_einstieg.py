"""Limitorder-Einstieg im Historienlauf (25.08.2026, BEFUNDE §G34).

**Warum es diesen Pfad gibt.** Der Spread ist 54 % der Rundlaufkosten
(5,00 von 9,22 $ je 10.000-$-Rundlauf). Eine Marktorder zahlt ihn per
Konstruktion. Faellt der effektive Spread von 5 auf 3 bps, sinkt der
Breakeven von 0,1423 % auf 0,1022 % - und die Luecke zum gemessenen
Vorsprung von +0,11 % je Trade (§A) schliesst sich vollstaendig.

**Warum das Modell hier und nicht im Papierdepot geprueft wird.**
Alpacas Simulator fuellt Limitorders laut eigener Dokumentation
grosszuegig, sobald der Kurs die Marke beruehrt, ohne
Warteschlangenposition. Genau der Teil, der bei Limitorders entscheidet,
ist dort unrealistisch optimistisch.

**Die Falle, gegen die diese Tests gebaut sind:** dass das eigene Modell
denselben Fehler macht. Ein Fuellmodell, das jeden Beruehrer als
Ausfuehrung zaehlt, laesst Limitorders kuenstlich gut aussehen - es
kassiert die gesparte Spanne und uebersieht die verpassten Einstiege.
Deshalb pruefen die Tests unten BEIDE Richtungen: dass gefuellt wird,
wenn es sein muss, und dass NICHT gefuellt wird, wenn die Marke nur
knapp verfehlt oder exakt beruehrt wird.
"""

from __future__ import annotations

import pandas as pd
import pytest

from alpaca_bot.simulate import SimConfig, _kaufkosten, limit_fuellung


def _bar(open_, low, high=None, close=None) -> pd.Series:
    return pd.Series({"open": open_, "low": low,
                      "high": high if high is not None else max(open_, low) * 1.02,
                      "close": close if close is not None else open_,
                      "volume": 1e6})


@pytest.fixture
def cfg() -> SimConfig:
    return SimConfig(limit_einstieg=True, limit_offset_bps=10.0,
                     limit_puffer_bps=2.0, log_to_journal=False)


class TestFuellregel:
    def test_tief_klar_unter_der_marke_wird_gefuellt(self, cfg):
        # Entscheidungskurs 100 -> Marke 99.90, Schwelle 99.88.
        fuell, marke = limit_fuellung(100.0, _bar(open_=100.0, low=99.0), cfg)
        assert marke == pytest.approx(99.90)
        assert fuell == pytest.approx(99.90), (
            "Bei Tief deutlich unter der Marke wird zur Marke ausgefuehrt."
        )

    def test_tief_ueber_der_marke_wird_nicht_gefuellt(self, cfg):
        fuell, _ = limit_fuellung(100.0, _bar(open_=100.5, low=100.1), cfg)
        assert fuell is None, (
            "Der Kurs kam nie an die Marke - dieser Einstieg entfaellt. "
            "Das sind die Opportunitaetskosten der Limitorder."
        )

    def test_blosses_beruehren_zaehlt_nicht_als_ausfuehrung(self, cfg):
        """**Der wichtigste Test dieser Datei.**

        Genau hier macht Alpacas Papierdepot seinen Fehler (§G34): Es
        fuellt, sobald der Kurs die Marke beruehrt. Ob man an der Reihe
        gewesen waere, haengt an der Warteschlangenposition - die kennt
        keine Simulation. Ohne den Puffer wuerde dieses Modell
        Limitorders kuenstlich gut aussehen lassen.
        """
        marke = 100.0 * (1 - 10 / 10_000)          # 99.90
        fuell, _ = limit_fuellung(100.0, _bar(open_=100.0, low=marke), cfg)
        assert fuell is None, (
            "Tief == Marke ist KEINE sichere Ausfuehrung. Im Zweifel "
            "lieber eine Ausfuehrung zu wenig als eine zu viel."
        )

    def test_knapp_unter_der_marke_aber_ueber_dem_puffer_faellt_durch(self, cfg):
        marke = 100.0 * (1 - 10 / 10_000)          # 99.90
        knapp = marke * (1 - 1 / 10_000)           # 1 bps drunter, Puffer 2
        fuell, _ = limit_fuellung(100.0, _bar(open_=100.0, low=knapp), cfg)
        assert fuell is None

    def test_eroeffnung_unter_der_marke_liefert_die_eroeffnung(self, cfg):
        """Kurslueckte nach unten: Man bekommt die Eroeffnung, nicht die Marke.

        Fuer einen Kaeufer ist das der bessere Kurs - und zugleich genau
        der Fall, in dem etwas passiert ist. So entsteht adverse
        Selektion; sie wird hier nicht wegdefiniert, sondern faellt in
        die Trade-Ergebnisse.
        """
        fuell, marke = limit_fuellung(100.0, _bar(open_=95.0, low=94.0), cfg)
        assert fuell == pytest.approx(95.0)
        assert fuell < marke

    def test_groesserer_offset_wird_seltener_gefuellt(self, cfg):
        """Die eigentliche Abwaegung: tiefere Marke, mehr Ersparnis,
        weniger Ausfuehrungen."""
        bar = _bar(open_=100.0, low=99.85)
        nah, _ = limit_fuellung(100.0, bar, cfg)                    # Marke 99.90
        cfg_tief = SimConfig(limit_einstieg=True, limit_offset_bps=50.0,
                             limit_puffer_bps=2.0, log_to_journal=False)
        tief, _ = limit_fuellung(100.0, bar, cfg_tief)              # Marke 99.50
        assert nah is not None
        assert tief is None


class TestKostenmodell:
    """Der ganze Punkt der Limitorder steckt im Wegfall von Spread und
    Slippage. Faellt dieser Unterschied weg, misst der Lauf nichts."""

    def test_limitkauf_zahlt_weder_spread_noch_slippage(self, cfg):
        markt = _kaufkosten(100, 100.0, cfg, limit=False)
        lim = _kaufkosten(100, 100.0, cfg, limit=True)

        assert lim.spread_cost == pytest.approx(0.0)
        assert lim.slippage == pytest.approx(0.0)
        assert markt.spread_cost > 0
        assert lim.total_cost < markt.total_cost

    def test_limitkauf_bekommt_genau_seinen_kurs(self, cfg):
        lim = _kaufkosten(100, 99.90, cfg, limit=True)
        assert lim.effective_price == pytest.approx(99.90), (
            "Eine ausgefuehrte Limitorder bekommt ihre Marke oder besser - "
            "nie einen Aufschlag."
        )

    def test_gebuehren_bleiben_in_beiden_faellen(self, cfg):
        """SEC und FINRA haengen am Volumen, nicht am Ordertyp. Sie
        duerfen nicht mit dem Spread verschwinden."""
        lim = _kaufkosten(100, 100.0, cfg, limit=True)
        markt = _kaufkosten(100, 100.0, cfg, limit=False)
        assert lim.sec_fee == pytest.approx(markt.sec_fee)
        assert lim.finra_taf == pytest.approx(markt.finra_taf)


def test_marktorder_bleibt_der_standard():
    """`limit_einstieg` ist bewusst aus. Der Historienlauf muss ohne
    ausdrueckliche Angabe weiterhin das messen, was der Live-Bot tut -
    und der sendet ausschliesslich Marktorders."""
    assert SimConfig().limit_einstieg is False


def test_puffer_null_faellt_auf_das_beruehrmodell_zurueck():
    """Dokumentiert, was `limit_puffer_bps=0` bedeutet: dasselbe
    optimistische Modell wie im Papierdepot. Nur fuer Vergleichslaeufe,
    nie als Grundlage einer Entscheidung."""
    cfg = SimConfig(limit_einstieg=True, limit_offset_bps=10.0,
                    limit_puffer_bps=0.0, log_to_journal=False)
    marke = 100.0 * (1 - 10 / 10_000)
    fuell, _ = limit_fuellung(100.0, _bar(open_=100.0, low=marke), cfg)
    assert fuell == pytest.approx(marke)
