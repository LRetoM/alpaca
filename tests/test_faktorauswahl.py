"""Faktorauswahl: das Versprechen der Signatur muss der Rumpf einlösen (§G16).

**Anlass (22.08.2026).** `research.select_factors` nimmt zwei Parameter
entgegen, die es im Rumpf **an keiner Stelle** benutzt:

    max_correlation: float = 0.7
    factor_data: dict[str, pd.DataFrame] | None = None

Es wählt schlicht die Top-N nach t-Wert. Ein Korrelationsfilter findet
nicht statt — dieselbe Fehlerklasse wie `hypotheses.historientest`, wo
`horizont` ebenfalls nur in der Signatur stand (§G16 Fund 3).

**Warum das hier besonders wiegt.** Das Projekt weiß, dass seine
Faktoren korreliert sind, und schreibt es an drei Stellen auf:

    research.py       "Der Wert entsteht erst durch Kombination
                       schwacher, moeglichst wenig korrelierter Anzeichen"
    ReversalWeights   "Die Bausteine messen im Kern dasselbe und sind
                       entsprechend stark korreliert. Die Gewichtung dient
                       der Glaettung, nicht der Addition unabhaengiger
                       Information - fuenf Messungen desselben Effekts
                       sind nicht fuenfmal so viel Signal."
    BEFUNDE §A        "Die fuenf Umkehr-Bausteine messen im Kern DASSELBE"

`select_factors` ist die Stelle, an der aus einer Messung eine Strategie
wird. Der Mechanismus, der genau diese Redundanz verhindern soll, war
nicht implementiert.

Das Fundamentalgesetz `IR = IC * sqrt(BR)` setzt **unabhängige** Signale
voraus. Fünf korrelierte Faktoren liefern nicht die Breite von fünf.
"""

from __future__ import annotations

import inspect

import numpy as np
import pandas as pd
import pytest

from alpaca_bot import research


def _ergebnisse(faktoren: list[str], t_werte: list[float]) -> pd.DataFrame:
    return pd.DataFrame({
        "factor": faktoren,
        "horizon": 5,
        "ic_mean": [0.02] * len(faktoren),
        "t_stat": t_werte,
        "t_korrigiert": t_werte,
        "aufblaehung": 1.0,
    })


def _panels(spalten: dict[str, np.ndarray], n: int = 200) -> dict[str, pd.DataFrame]:
    """Faktorpanels je Symbol - Form wie `measure_factors` sie intern hält."""
    idx = pd.date_range("2024-01-01", periods=n, freq="B")
    return {"S1": pd.DataFrame(spalten, index=idx)}


class TestKorrelationsfilterExistiert:
    def test_parameter_werden_im_rumpf_benutzt(self):
        """Der Fund selbst: deklariert, nie verwendet."""
        quelle = inspect.getsource(research.select_factors)
        rumpf = quelle.split('"""')[-1]
        assert "max_correlation" in rumpf, (
            "eine Signatur, die einen Filter verspricht, der nicht "
            "stattfindet, beruhigt beim Lesen - genau wie §G16 Fund 3")
        assert "factor_data" in rumpf


class TestFilterWirkt:
    def test_redundanter_faktor_fliegt_raus(self):
        rng = np.random.default_rng(3)
        basis = rng.normal(size=200)
        panels = _panels({
            "a": basis,
            "a_klon": basis * 1.001 + rng.normal(0, 0.001, 200),  # ~identisch
            "b": rng.normal(size=200),                             # unabhaengig
        })
        gewaehlt = research.select_factors(
            _ergebnisse(["a", "a_klon", "b"], [5.0, 4.9, 4.0]),
            horizon=5, min_t=3.0, max_correlation=0.7, factor_data=panels)

        assert "a" in gewaehlt, "der staerkste bleibt"
        assert "a_klon" not in gewaehlt, (
            "ein Faktor, der dasselbe misst, bringt keine zusaetzliche "
            "Breite - IR = IC*sqrt(BR) setzt Unabhaengigkeit voraus")
        assert "b" in gewaehlt, "der unabhaengige bleibt"

    def test_unkorrelierte_bleiben_alle(self):
        rng = np.random.default_rng(4)
        panels = _panels({n: rng.normal(size=200) for n in ("a", "b", "c")})
        gewaehlt = research.select_factors(
            _ergebnisse(["a", "b", "c"], [5.0, 4.5, 4.0]),
            horizon=5, min_t=3.0, max_correlation=0.7, factor_data=panels)
        assert set(gewaehlt) == {"a", "b", "c"}

    def test_der_staerkere_gewinnt_das_duell(self):
        """Bei zwei korrelierten Faktoren bleibt der mit dem höheren t."""
        rng = np.random.default_rng(5)
        basis = rng.normal(size=200)
        panels = _panels({"schwach": basis, "stark": basis * 0.999 + rng.normal(0, 0.001, 200)})
        gewaehlt = research.select_factors(
            _ergebnisse(["schwach", "stark"], [3.5, 6.0]),
            horizon=5, min_t=3.0, max_correlation=0.7, factor_data=panels)
        assert gewaehlt == ["stark"]

    def test_negative_korrelation_zaehlt_auch(self):
        """Ein invertierter Klon ist genauso redundant wie ein Klon."""
        rng = np.random.default_rng(6)
        basis = rng.normal(size=200)
        panels = _panels({"a": basis, "a_invers": -basis + rng.normal(0, 0.001, 200)})
        gewaehlt = research.select_factors(
            _ergebnisse(["a", "a_invers"], [5.0, 4.0]),
            horizon=5, min_t=3.0, max_correlation=0.7, factor_data=panels)
        assert gewaehlt == ["a"]


class TestOhneDatenKeineStilleZusicherung:
    """Fehlen die Panels, darf der Filter nicht stillschweigend entfallen."""

    def test_ohne_factor_data_wird_gewarnt(self, capsys):
        gewaehlt = research.select_factors(
            _ergebnisse(["a", "b"], [5.0, 4.0]), horizon=5, min_t=3.0)
        assert gewaehlt == ["a", "b"], "die Auswahl bleibt, nur ungefiltert"
        ausgabe = capsys.readouterr().out.lower()
        assert "korrelation" in ausgabe and (
            "ohne" in ausgabe or "nicht" in ausgabe), (
            "ein entfallener Filter muss sichtbar sein - sonst haelt man "
            "die Auswahl fuer geprueft")

    def test_max_correlation_none_schaltet_bewusst_ab(self, capsys):
        """Ausdrücklich abschalten ist erlaubt und erzeugt keine Warnung."""
        gewaehlt = research.select_factors(
            _ergebnisse(["a", "b"], [5.0, 4.0]), horizon=5, min_t=3.0,
            max_correlation=None)
        assert gewaehlt == ["a", "b"]
        assert "korrelation" not in capsys.readouterr().out.lower()


class TestBestehendeZusicherungenBleiben:
    def test_schwelle_und_vorzeichen_wirken_weiter(self):
        r = _ergebnisse(["stark", "schwach"], [5.0, 1.0])
        assert research.select_factors(r, horizon=5, min_t=3.0) == ["stark"]

    def test_negativer_ic_wird_nicht_invertiert(self):
        r = _ergebnisse(["a", "b"], [5.0, 5.0])
        r.loc[r["factor"] == "b", "ic_mean"] = -0.02
        assert research.select_factors(r, horizon=5, min_t=3.0) == ["a"]

    def test_max_factors_wird_eingehalten(self):
        rng = np.random.default_rng(7)
        namen = [f"f{i}" for i in range(8)]
        panels = _panels({n: rng.normal(size=200) for n in namen})
        gewaehlt = research.select_factors(
            _ergebnisse(namen, [9.0 - i for i in range(8)]),
            horizon=5, min_t=3.0, max_factors=3, factor_data=panels)
        assert len(gewaehlt) == 3


class TestEffektiveBreite:
    """Paarweise Korrelation reicht nicht - vier Faktoren können paarweise
    alle unter der Schwelle liegen und gemeinsam fast dasselbe messen.

    **Gemessen am 22.08.2026** auf 198.038 echten Beobachtungen über 396
    Symbole, für die vier Bausteine, die tatsächlich in den Score eingehen:

        f_rueckgang  f_rsi2  f_ausverkauf  f_band_unten
              1.00    0.69          0.57          0.50
              0.69    1.00          0.42          0.49
              0.57    0.42          1.00          0.32
              0.50    0.49          0.32          1.00

    **Kein einziges Paar über 0,7** - der Paarfilter hätte nichts
    verworfen. Die effektive Zahl unabhängiger Bausteine liegt aber bei
    **1,53 von 4**.

    Das quantifiziert BEFUNDE §A ("die Summe ist NICHT fünfmal so viel
    Signal") erstmals mit einer Zahl: Es ist rund anderthalbmal so viel,
    nicht viermal.
    """

    def test_identische_faktoren_ergeben_eins(self):
        rng = np.random.default_rng(21)
        basis = rng.normal(size=400)
        panels = _panels({"a": basis, "b": basis.copy(), "c": basis.copy()}, n=400)
        eff = research.effektive_breite(["a", "b", "c"], panels)
        assert eff == pytest.approx(1.0, abs=0.05), (
            "drei identische Faktoren tragen die Information von einem")

    def test_unabhaengige_faktoren_ergeben_ihre_zahl(self):
        rng = np.random.default_rng(22)
        panels = _panels({n: rng.normal(size=2000) for n in ("a", "b", "c")},
                         n=2000)
        eff = research.effektive_breite(["a", "b", "c"], panels)
        assert eff == pytest.approx(3.0, abs=0.25)

    def test_teilweise_korreliert_liegt_dazwischen(self):
        rng = np.random.default_rng(23)
        basis = rng.normal(size=2000)
        panels = _panels({
            "a": basis,
            "b": 0.7 * basis + 0.7 * rng.normal(size=2000),
            "c": rng.normal(size=2000),
        }, n=2000)
        eff = research.effektive_breite(["a", "b", "c"], panels)
        assert 1.5 < eff < 3.0

    def test_gewichte_werden_beruecksichtigt(self):
        """Ein Faktor mit Gewicht 0 darf die Breite nicht mitbestimmen."""
        rng = np.random.default_rng(24)
        basis = rng.normal(size=2000)
        panels = _panels({"a": basis, "klon": basis.copy(),
                          "c": rng.normal(size=2000)}, n=2000)
        # Ohne Gewichte zaehlt der Klon mit und drueckt die Breite.
        ohne = research.effektive_breite(["a", "klon", "c"], panels)
        mit = research.effektive_breite(["a", "klon", "c"], panels,
                                        gewichte={"a": 0.5, "klon": 0.0, "c": 0.5})
        assert mit > ohne

    def test_auswahl_meldet_die_effektive_breite(self, capsys):
        """Der reale Fall: paarweise sauber, gemeinsam redundant.

        Die Kopplung ist bewusst so gewaehlt, dass ALLE Paare unter 0,7
        liegen und den Filter passieren - genau die Lage der vier
        Score-Bausteine (0,32 bis 0,69). Ohne die Breite-Meldung saehe
        eine solche Auswahl geprueft aus.
        """
        rng = np.random.default_rng(25)
        basis = rng.normal(size=3000)
        panels = _panels({
            "a": 0.62 * basis + 0.78 * rng.normal(size=3000),
            "b": 0.62 * basis + 0.78 * rng.normal(size=3000),
            "c": 0.62 * basis + 0.78 * rng.normal(size=3000),
        }, n=3000)

        korr = research._faktor_korrelationen(["a", "b", "c"], panels)
        assert all(abs(v) < 0.7 for v in korr.values()), (
            f"Testaufbau: alle Paare muessen den Filter passieren, "
            f"gemessen {[round(v, 2) for v in korr.values()]}")

        gewaehlt = research.select_factors(
            _ergebnisse(["a", "b", "c"], [5.0, 4.5, 4.0]),
            horizon=5, min_t=3.0, factor_data=panels)
        assert len(gewaehlt) == 3, "der Paarfilter darf hier nichts verwerfen"
        assert research.effektive_breite(gewaehlt, panels) < 2.5, (
            "drei so gekoppelte Faktoren tragen keine drei Signale")

        ausgabe = capsys.readouterr().out.lower()
        assert "effektiv" in ausgabe, (
            "Faktoren koennen paarweise sauber sein und gemeinsam fast "
            "dasselbe messen - das muss dastehen")

    def test_leere_eingabe_stuerzt_nicht_ab(self):
        assert np.isnan(research.effektive_breite([], {}))
        assert research.effektive_breite(["a"], _panels({"a": np.arange(100.0)}, 100)) == 1.0
