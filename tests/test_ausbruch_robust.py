"""Tests fuer die Streuung ueber Symbole und den Score `t_robust`.

Anlass ist §G66: Der beste Kandidat fiel im Gate mit einem Top-5-Anteil
von 129,9 % durch - ohne seine fuenf besten Symbole war er im Minus. Der
gewoehnliche t-Wert konnte das nicht sehen, weil er Renditen kennt, aber
nicht deren Herkunft.

Geprueft wird deshalb genau diese Unterscheidung: Zwei Ergebnisse mit
derselben Gesamtrendite muessen verschieden bewertet werden, wenn das
eine breit getragen ist und das andere an fuenf Symbolen haengt.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from alpaca_bot import ausbruch
from alpaca_bot import ausbruch_suche as su


def _trades(symbole, gewinne, renditen=None, start="2025-01-02"):
    """Ein Trade je Eintrag, je an einem eigenen Handelstag."""
    n = len(symbole)
    tage = pd.bdate_range(start, periods=n, tz="UTC")
    renditen = gewinne if renditen is None else renditen
    return pd.DataFrame({
        "symbol": list(symbole),
        "einstieg_ts": tage,
        "rendite_pct": [float(r) for r in renditen],
        "gewinn_usd": [float(g) for g in gewinne],
    })


# --- Der Anteil der fuenf Groessten -----------------------------------

def test_breit_getragen_gibt_kleinen_anteil():
    t = _trades([f"S{i}" for i in range(50)], [100.0] * 50)
    k = ausbruch._streuung_ueber_symbole(t)
    assert k["top5_anteil_pct"] == pytest.approx(10.0)


def test_fuenf_traeger_geben_hohen_anteil():
    symbole = [f"GROSS{i}" for i in range(5)] + [f"KLEIN{i}" for i in range(45)]
    gewinne = [1000.0] * 5 + [10.0] * 45
    k = ausbruch._streuung_ueber_symbole(_trades(symbole, gewinne))
    assert k["top5_anteil_pct"] > 90.0


def test_anteil_ueber_hundert_wenn_der_rest_verliert():
    """Der Fall aus §G66: Ohne die fuenf Besten ist die Strategie im
    Minus - dann liegt ihr Anteil ueber 100 %."""
    symbole = [f"GROSS{i}" for i in range(5)] + [f"KLEIN{i}" for i in range(45)]
    gewinne = [1000.0] * 5 + [-50.0] * 45
    k = ausbruch._streuung_ueber_symbole(_trades(symbole, gewinne))
    assert k["top5_anteil_pct"] > 100.0


def test_gesamtverlust_gibt_inf_statt_kleiner_zahl():
    """Bei negativem Nenner koennte eine Division sonst zufaellig einen
    unauffaelligen Wert liefern."""
    k = ausbruch._streuung_ueber_symbole(
        _trades([f"S{i}" for i in range(20)], [-10.0] * 20))
    assert k["top5_anteil_pct"] == float("inf")


def test_leere_trades_stuerzen_nicht_ab():
    k = ausbruch._streuung_ueber_symbole(pd.DataFrame())
    assert np.isnan(k["top5_anteil_pct"])
    assert np.isnan(k["t_ohne_top5"])


# --- t ohne die fuenf Groessten ---------------------------------------

def test_t_ohne_top5_bleibt_bei_breitem_effekt_erhalten():
    """40 Symbole, alle im Schnitt leicht positiv: Das Entfernen von
    fuenf darf den t-Wert nicht wesentlich aendern.

    Mit Streuung, nicht mit glatten Werten: Ohne Rauschen kaeme ein
    t-Wert von 65 heraus, und der faellt zu Recht in die Kappung gegen
    entartete Werte (§G61). Ein Test auf unrealistischen Daten prueft
    die Kappung, nicht die Sache.
    """
    r = np.random.default_rng(7)
    symbole = [f"S{i}" for i in range(40)]
    renditen = r.normal(1.0, 1.0, 40)
    k = ausbruch._streuung_ueber_symbole(_trades(symbole, renditen))
    assert np.isfinite(k["t_ohne_top5"])
    assert k["t_ohne_top5"] > 2.0


def test_t_ohne_top5_bricht_ein_wenn_fuenf_alles_tragen():
    r = np.random.default_rng(11)
    symbole = [f"GROSS{i}" for i in range(5)] + [f"KLEIN{i}" for i in range(40)]
    renditen = np.concatenate([np.full(5, 40.0), r.normal(-1.0, 1.0, 40)])
    k = ausbruch._streuung_ueber_symbole(_trades(symbole, renditen))
    assert k["t_ohne_top5"] < 0


def test_zu_wenig_rest_gibt_nan_statt_zufallszahl():
    """Bleiben nach dem Abzug kaum Trades, ist die Zahl nicht
    aussagekraeftig - dann NaN statt einer beliebigen Zahl."""
    k = ausbruch._streuung_ueber_symbole(
        _trades([f"S{i}" for i in range(7)], [10.0] * 7))
    assert np.isnan(k["t_ohne_top5"])


# --- Der Score --------------------------------------------------------

def test_score_robust_nimmt_den_schlechteren_wert():
    assert su.SCORES["t_robust"]({"t_wert": 6.0, "t_ohne_top5": 1.2}) == 1.2
    assert su.SCORES["t_robust"]({"t_wert": 1.5, "t_ohne_top5": 4.0}) == 1.5


def test_score_robust_verwirft_nicht_berechenbare():
    """Zu schmal, um breit zu sein - das ist selbst ein Befund."""
    s = su.SCORES["t_robust"]({"t_wert": 9.9, "t_ohne_top5": float("nan")})
    assert s == float("-inf")


def test_score_robust_verwirft_nan_t():
    s = su.SCORES["t_robust"]({"t_wert": float("nan"), "t_ohne_top5": 3.0})
    assert s == float("-inf")


def test_score_robust_trennt_was_t_nicht_trennt():
    """Der Kern: Zwei Konfigurationen, die `t` gleich bewertet, muessen
    unter `t_robust` verschieden ausfallen."""
    breit = {"t_wert": 5.0, "t_ohne_top5": 4.7}
    schmal = {"t_wert": 5.0, "t_ohne_top5": -0.3}
    assert su.SCORES["t"](breit) == su.SCORES["t"](schmal)
    assert su.SCORES["t_robust"](breit) > su.SCORES["t_robust"](schmal)


def test_score_steht_im_dienst_zur_auswahl():
    """Ohne Eintrag in SCORES waere der Score per --score nicht
    erreichbar - und damit nur Zierde."""
    assert "t_robust" in su.SCORES


# --- Getrennte Elite je Score-Funktion (§G6-Fehlerklasse) -------------

def test_elite_ist_je_score_getrennt(tmp_path, monkeypatch):
    """Zwei Massstaebe duerfen sich keine Bestenliste teilen.

    `t_robust` liegt bauartbedingt nie ueber `t`. In einer gemeinsamen
    Datei wuerde eine t_robust-Instanz deshalb nie einen Bestwert
    eintragen - und zugleich immer wieder an einem Punkt ansetzen, der
    fuer ein anderes Ziel optimiert wurde.
    """
    from alpaca_bot import config as cfgmod
    monkeypatch.setattr(cfgmod, "DATA_DIR", tmp_path)

    assert su.elite_schreiben(7.6, {"a": 1}, "a", score_name="t") is True
    assert su.elite_schreiben(2.1, {"a": 2}, "e", score_name="t_robust") is True

    assert su.elite_lesen("t")["score"] == 7.6
    assert su.elite_lesen("t_robust")["score"] == 2.1
    assert su.elite_lesen("t")["config"] == {"a": 1}
    assert su.elite_lesen("t_robust")["config"] == {"a": 2}


def test_elite_dateien_haben_verschiedene_namen(tmp_path, monkeypatch):
    from alpaca_bot import config as cfgmod
    monkeypatch.setattr(cfgmod, "DATA_DIR", tmp_path)
    assert su._elite_pfad("t") != su._elite_pfad("t_robust")
    # `t` behaelt den bisherigen Namen - laufende Instanzen sollen ihre
    # Elite nicht verlieren.
    assert su._elite_pfad("t").name == "ausbruch_elite.json"


def test_elite_trennt_auch_nach_datenumfang(tmp_path, monkeypatch):
    """Ein t-Wert aus sechs Jahren ist nicht derselbe wie einer aus vier.

    Zwei Instanzen mit gleichem Score aber verschiedenen Jahren duerfen
    sich keine Elite teilen - sonst vergleichen sie Zeitraeume statt
    Konfigurationen (§G74).
    """
    from alpaca_bot import config as cfgmod
    monkeypatch.setattr(cfgmod, "DATA_DIR", tmp_path)

    assert su.elite_schreiben(2.7, {"a": 1}, "e", score_name="t_robust",
                              basis="2023-2026") is True
    assert su.elite_schreiben(1.9, {"a": 2}, "f", score_name="t_robust",
                              basis="2021-2026") is True

    assert su.elite_lesen("t_robust", "2023-2026")["score"] == 2.7
    assert su.elite_lesen("t_robust", "2021-2026")["score"] == 1.9
    assert su._elite_pfad("t_robust", "2021-2026") != \
        su._elite_pfad("t_robust", "2023-2026")


def test_laufende_flotte_behaelt_ihren_dateinamen(tmp_path, monkeypatch):
    """Die dauerhaft laufende Kombination darf beim Neustart ihre
    gesammelte Elite nicht verlieren."""
    from alpaca_bot import config as cfgmod
    monkeypatch.setattr(cfgmod, "DATA_DIR", tmp_path)
    assert su._elite_pfad(*su.ELITE_ALTBESTAND).name == "ausbruch_elite.json"
    assert su._elite_pfad("t", "").name == "ausbruch_elite.json"
