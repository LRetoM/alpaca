"""Tests fuer das Gate (scripts/53_ausbruch_gate.py).

Das Gate ist die Stelle, an der eine Idee zum Flottenbot wird oder
nicht. Ein Fehler hier ist teurer als ein Fehler in der Suche: Die
Suche findet nur Kandidaten, das Gate spricht sie frei.

Geprueft wird deshalb nicht, ob das Gate etwas durchlaesst, sondern ob
es in den gefaehrlichen Faellen **zumacht**:

1. Ein NaN-Wert darf nie als bestanden durchgehen (§G63 - NaN-Vergleiche
   sind in Python immer False, ein falsch herum geschriebener Test
   verwandelt "unbekannt" damit in "in Ordnung").
2. Ohne verteilbaren Gewinn gibt es keine bestandene Konzentrations-
   pruefung, auch wenn die Division formal ein kleines Ergebnis liefert.
3. Die Haelften des Prueffensters sind Zeitraeume, keine Trade-Haelften.
4. Rasterwerte behalten ihren Typ - `halten_bars = 52.0` statt `52`
   wuerde erst mitten im Lauf als TypeError auffallen.
"""

from __future__ import annotations

import sys
from importlib import import_module
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

gate = import_module("53_ausbruch_gate")


def _trades(n=10, symbole=None, start="2025-09-01", rendite=1.0, gewinn=100.0):
    symbole = symbole or [f"S{i}" for i in range(n)]
    ts = pd.date_range(start, periods=n, freq="D", tz="UTC")
    return pd.DataFrame({
        "symbol": symbole,
        "einstieg_ts": ts,
        "rendite_pct": [rendite] * n,
        "gewinn_usd": [gewinn] * n,
    })


def _kennzahlen(**kw):
    basis = {"t_wert": 5.0, "n_handelstage": 80, "n_trades": 300,
             "rendite_pct": 12.0, "max_drawdown_pct": -8.0}
    basis.update(kw)
    return basis


def _bewerten(k12=None, k30=None, trades=None, **kw):
    # Bewusst `is None` statt `or`: Ein leeres dict ist falsy, ein `or`
    # wuerde den Fall "gar keine Kennzahlen" still durch gueltige
    # ersetzen - der Test haette dann etwas anderes geprueft als er
    # behauptet (beim Schreiben dieser Datei genau so passiert).
    args = {"schwelle": 4.1, "dd_grenze": 15.0,
            "haelfte_grenze": pd.Timestamp("2025-09-06", tz="UTC")}
    args.update(kw)
    return gate.gate_bewerten(
        _kennzahlen() if k12 is None else k12,
        _kennzahlen() if k30 is None else k30,
        _trades() if trades is None else trades, **args)


# --- 1. NaN faellt durch, immer (§G63) -------------------------------

def test_nan_t_wert_faellt_durch_statt_zu_bestehen():
    """Der Kern der §G63-Lektion: unbekannt ist nicht in Ordnung."""
    k = _bewerten(k12=_kennzahlen(t_wert=float("nan")))
    assert k[0].bestanden is False


def test_nan_bei_strenger_spanne_faellt_durch():
    k = _bewerten(k30=_kennzahlen(t_wert=float("nan")))
    assert k[2].bestanden is False


def test_nan_drawdown_faellt_durch():
    k = _bewerten(k12=_kennzahlen(max_drawdown_pct=float("nan")))
    assert k[5].bestanden is False


def test_fehlende_kennzahl_faellt_durch_statt_abzustuerzen():
    """Ein leeres Kennzahlen-dict darf kein KeyError sein - und erst
    recht kein bestandenes Gate."""
    k = _bewerten(k12={}, k30={})
    assert all(not x.bestanden for x in k[:3])


# --- 2. Konzentration ------------------------------------------------

def test_ohne_gewinn_keine_bestandene_konzentration():
    """Bei Gesamtverlust ist der Top-5-Anteil nicht definiert. Frueher
    haette eine Division mit negativem Nenner hier eine kleine Zahl
    geliefert - und damit ein bestandenes Kriterium."""
    t = _trades(n=10, gewinn=-50.0)
    anteil, _ = gate.konzentration(t)
    assert not np.isfinite(anteil) or anteil > gate.TOP_ANTEIL_MAX
    k = _bewerten(trades=t)
    assert k[4].bestanden is False


def test_konzentration_erkennt_fuenf_traeger():
    """Fuenf Symbole tragen fast alles: muss auffallen."""
    t = pd.concat([
        _trades(n=5, symbole=[f"GROSS{i}" for i in range(5)], gewinn=1000.0),
        _trades(n=20, symbole=[f"KLEIN{i}" for i in range(20)], gewinn=5.0),
    ], ignore_index=True)
    anteil, top = gate.konzentration(t)
    assert anteil > 90.0
    assert len(top) == 5


def test_konzentration_breit_getragen_besteht():
    t = _trades(n=50, gewinn=100.0)
    anteil, _ = gate.konzentration(t)
    assert anteil == pytest.approx(10.0)


# --- 3. Haelften sind Zeitraeume, keine Trade-Haelften ---------------

def test_haelften_teilen_nach_zeit_nicht_nach_anzahl():
    """40 Trades im ersten Monat, 2 im zweiten: die zweite Haelfte hat
    dann 2 Trades - nicht 21."""
    viel = _trades(n=40, start="2025-09-01")
    wenig = _trades(n=2, start="2025-12-01")
    t = pd.concat([viel, wenig], ignore_index=True)
    _m1, _m2, n1, n2 = gate.haelften(t, pd.Timestamp("2025-11-01", tz="UTC"))
    assert (n1, n2) == (40, 2)


def test_haelfte_ohne_trades_faellt_durch():
    """Keine Trades in der zweiten Haelfte heisst nicht 'bestanden'."""
    t = _trades(n=10, start="2025-09-01")
    k = _bewerten(trades=t,
                  haelfte_grenze=pd.Timestamp("2026-01-01", tz="UTC"))
    assert k[3].bestanden is False


def test_nur_eine_haelfte_positiv_faellt_durch():
    a = _trades(n=10, start="2025-09-01", rendite=2.0)
    b = _trades(n=10, start="2025-12-01", rendite=-1.0)
    t = pd.concat([a, b], ignore_index=True)
    k = _bewerten(trades=t,
                  haelfte_grenze=pd.Timestamp("2025-11-01", tz="UTC"))
    assert k[3].bestanden is False


# --- 4. Rasterwerte behalten ihren Typ -------------------------------

def test_raum_wert_macht_aus_52_punkt_0_wieder_ein_int():
    wert = gate._raum_wert("halten_bars", 52.0)
    assert wert == 52
    assert isinstance(wert, int)


def test_raum_wert_behandelt_bool_achse_als_bool():
    assert gate._raum_wert("zeitausstieg_nur_bei_verlust", 0) is False
    assert gate._raum_wert("zeitausstieg_nur_bei_verlust", 1) is True


def test_raum_wert_laesst_unbekannte_achse_unveraendert():
    assert gate._raum_wert("gibt_es_nicht", 7) == 7


def test_normieren_zieht_leeres_zeitfenster_gerade():
    c = gate._normieren({"tageszeit_von_bar": 8, "tageszeit_bis_bar": 4})
    assert c["tageszeit_bis_bar"] == 8


# --- 5. Das vollstaendige Gate ---------------------------------------

def test_sauberer_kandidat_besteht_alle_sechs():
    """Gegenprobe: Das Gate darf nicht grundsaetzlich alles ablehnen."""
    t = _trades(n=60, start="2025-09-01", rendite=0.8, gewinn=80.0)
    k = _bewerten(trades=t,
                  haelfte_grenze=pd.Timestamp("2025-10-01", tz="UTC"))
    assert all(x.bestanden for x in k), [x.name for x in k if not x.bestanden]


def test_t_knapp_unter_schwelle_faellt_durch():
    k = _bewerten(k12=_kennzahlen(t_wert=4.09), schwelle=4.1)
    assert k[0].bestanden is False


def test_zu_wenige_handelstage_faellt_durch_trotz_hohem_t():
    """Massgeblich sind Handelstage, nicht Trades (§B1)."""
    k = _bewerten(k12=_kennzahlen(t_wert=9.9, n_handelstage=12))
    assert k[0].bestanden is False


def test_zu_wenige_trades_faellt_durch():
    k = _bewerten(k12=_kennzahlen(n_trades=199))
    assert k[1].bestanden is False


def test_gate_gibt_genau_sechs_kriterien():
    assert len(_bewerten()) == 6
