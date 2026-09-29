"""Das Hypothesenregister - der letzte Ort mit unkorrigiertem t-Wert (§G12).

**Anlass (22.08.2026).** §G12 hat die Ueberlappung zwischen benachbarten
Handelstagen an vier Stellen behoben: `statistik`, `research`,
`shadow_eval` und `nachbetrachtung`. `hypotheses.historientest` blieb
uebrig - und ist ausgerechnet die Stelle, an der ein t-Wert einen STATUS
setzt:

    status = "im_test" if abs(t) > 2 else "widerlegt"

Bei `horizont=5` liegt die Fehlalarmquote unkorrigiert bei **39,5 %**
statt 5 % (§G12). Vier von zehn "widerlegt"-Urteilen waeren also
Rauschen gewesen - in beide Richtungen: eine gute Idee verworfen oder
eine wertlose in den teuren Vorwaertstest geschickt.

Verschaerfend: Die Funktion nahm `horizont` als Parameter entgegen und
**benutzte ihn im Rumpf an keiner Stelle**. Eine Signatur, die eine
Korrektur verspricht, die es nicht gibt, ist schlimmer als gar keine -
sie beruhigt beim Lesen.
"""

from __future__ import annotations

import inspect

import numpy as np
import pandas as pd
import pytest

from alpaca_bot import hypotheses
from alpaca_bot.shadow import ShadowStore


@pytest.fixture
def store(tmp_path) -> ShadowStore:
    return ShadowStore(tmp_path / "shadow.sqlite")


def _panel(n_tage: int, n_sym: int = 40, effekt: float = 0.0, seed: int = 11):
    """Faktor- und Renditepanel mit einstellbarem echten Effekt."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2020-01-01", periods=n_tage, freq="B")
    spalten = [f"S{i:02d}" for i in range(n_sym)]
    f = pd.DataFrame(rng.normal(size=(n_tage, n_sym)), index=idx, columns=spalten)
    # Gleitendes 5-Tage-Fenster: benachbarte Zeilen teilen 4/5 ihres
    # Renditefensters - genau die Ueberlappung aus §G12.
    roh = pd.DataFrame(rng.normal(0, 0.02, size=(n_tage + 5, n_sym)),
                       index=pd.date_range("2020-01-01", periods=n_tage + 5,
                                           freq="B"), columns=spalten)
    r = roh.rolling(5).sum().iloc[5:].set_axis(idx) + effekt * f
    return f, r


class TestHorizontIstKeinToterParameter:
    def test_horizont_wird_im_rumpf_verwendet(self):
        """Der Fund selbst: deklariert, nie benutzt."""
        quelle = inspect.getsource(hypotheses.historientest)
        rumpf = quelle.split('"""')[-1]
        assert "horizont" in rumpf, (
            "`horizont` war ein toter Parameter - die Signatur versprach "
            "eine Korrektur, die im Rumpf nicht stattfand")

    def test_nutzt_die_gemeinsame_statistik(self):
        """Nicht von Hand rechnen - `statistik` ist die eine Quelle."""
        quelle = inspect.getsource(hypotheses.historientest)
        assert "newey_west_t" in quelle or "gruppierter_test" in quelle


class TestUeberlappungWirdKorrigiert:
    def test_korrigierter_wert_liegt_unter_dem_rohen(self, store):
        hypotheses.erfassen("H_T1", "Testbehauptung fuer die Messung",
                            quelle="intern", quelle_typ="eigene_messung",
                            operationalisierung="synthetisch", store=store)
        f, r = _panel(400, effekt=0.15)
        erg = hypotheses.historientest("H_T1", f, r, store=store, horizont=5)

        assert "t_roh" in erg, "der rohe Wert gehoert zum Vergleich daneben"
        assert np.isfinite(erg["t"])
        assert abs(erg["t"]) < abs(erg["t_roh"]), (
            "bei ueberlappenden 5-Tage-Fenstern MUSS der korrigierte Wert "
            "kleiner sein - sonst wurde nicht korrigiert")

    def test_horizont_1_bleibt_unveraendert(self, store):
        """Kontrollfall: ohne Ueberlappung darf sich nichts aendern."""
        hypotheses.erfassen("H_T2", "Testbehauptung fuer die Messung",
                            quelle="intern", quelle_typ="eigene_messung",
                            operationalisierung="synthetisch", store=store)
        f, r = _panel(300, effekt=0.10)
        erg = hypotheses.historientest("H_T2", f, r, store=store, horizont=1)
        assert erg["t"] == pytest.approx(erg["t_roh"], abs=1e-9)

    def test_status_haengt_am_korrigierten_wert(self, store):
        """Die teuerste Stelle: hier wird aus einer Zahl ein Urteil."""
        quelle = inspect.getsource(hypotheses.historientest)
        i_status = quelle.index('"im_test"')
        umfeld = quelle[max(0, i_status - 400):i_status + 200]
        assert "t_roh" not in umfeld.split("erg[")[0] or "korr" in umfeld, (
            "das Urteil darf nicht am rohen t-Wert haengen (§G12)")

    def test_zu_kurze_reihe_liefert_keinen_t_wert(self, store):
        """Entarteter Schaetzer: lieber `nan` als eine spektakulaere Zahl.

        An echten Daten lieferte `newey_west_t` bei 8 Tagen und einem
        10-Tage-Fenster ein t von 14,57 gegen 5,30 roh (§G14). Der rohe
        darf dann NICHT ersatzweise einspringen.
        """
        hypotheses.erfassen("H_T3", "Testbehauptung fuer die Messung",
                            quelle="intern", quelle_typ="eigene_messung",
                            operationalisierung="synthetisch", store=store)
        f, r = _panel(9, n_sym=30)
        erg = hypotheses.historientest("H_T3", f, r, store=store, horizont=5)
        assert not np.isfinite(erg.get("t", np.nan))
        assert erg.get("t") != erg.get("t_roh")

    def test_ohne_t_wert_wird_NICHT_geurteilt(self, store):
        """Der eigentliche Schaden - und das, was der Mutationstest fand.

        Zu pruefen, dass `t` NaN ist, reicht nicht: Entscheidend ist, was
        daraus im STATUS wird. Ohne gueltigen t-Wert auf `widerlegt` zu
        springen hiesse, eine Idee auf Basis einer Nichtmessung zu
        verwerfen. `offen` ist die einzige ehrliche Antwort - dieselbe
        Drei-Zustaende-Regel wie in `shadow_eval.kriterien_pruefen`:
        erfuellt / durchgefallen / offen, und `offen` ist kein Urteil.
        """
        hypotheses.erfassen("H_T4", "Testbehauptung fuer die Messung",
                            quelle="intern", quelle_typ="eigene_messung",
                            operationalisierung="synthetisch", store=store)
        f, r = _panel(9, n_sym=30)
        hypotheses.historientest("H_T4", f, r, store=store, horizont=5)

        zeile = store.table("hypothesen").set_index("hyp_id").loc["H_T4"]
        assert zeile["status"] == "offen", (
            f"ohne gueltigen t-Wert darf kein Urteil fallen, war "
            f"'{zeile['status']}'")
        assert zeile["hist_t"] is None or pd.isna(zeile["hist_t"]), (
            "ein NaN gehoert als NULL in die Datenbank - gespeichert als "
            "Zahl liest es sich spaeter als 0,0")


class TestKalibrierung:
    """Die Kette muss bei Rauschen schweigen und bei Signal sprechen."""

    def test_schweigt_bei_reinem_rauschen(self, store):
        hypotheses.erfassen("H_N", "Testbehauptung fuer die Messung",
                            quelle="intern", quelle_typ="eigene_messung",
                            operationalisierung="synthetisch", store=store)
        f, r = _panel(500, effekt=0.0, seed=99)
        erg = hypotheses.historientest("H_N", f, r, store=store, horizont=5)
        assert abs(erg["t"]) < 3.0

    def test_spricht_bei_starkem_signal(self, store):
        hypotheses.erfassen("H_S", "Testbehauptung fuer die Messung",
                            quelle="intern", quelle_typ="eigene_messung",
                            operationalisierung="synthetisch", store=store)
        f, r = _panel(500, effekt=0.60, seed=99)
        erg = hypotheses.historientest("H_S", f, r, store=store, horizont=5)
        assert abs(erg["t"]) > 3.0
