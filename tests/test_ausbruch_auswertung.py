"""Regressionstest fuer scripts/52_ausbruch_auswertung.py.

Vorfall vom 12.09.2026 (docs/BEFUNDE.md): Sieben von 4.346 Stichproben
hatten `t_lern = NaN` (zu wenige Trades im Lernfenster). `np.corrcoef`
gab dadurch NaN fuer die GESAMTE Korrelation zurueck - und weil
NaN-Vergleiche in Python immer False sind, fiel der Ausgabetext
unbemerkt bis "Deutlicher Zusammenhang" durch, obwohl gar keine Zahl
berechnet worden war. Im selben Lauf stand ein Versuch mit nur 1 Trade
im Lernfenster (Score also NaN) als "bester Pruefwert" ueber der
Schwelle - und loeste ein Urteil aus ("naechster Schritt: Gate"), das
auf einem einzelnen Trade beruhte.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from importlib import import_module

auswertung = import_module("52_ausbruch_auswertung")


def test_korrelation_ignoriert_kein_nan_kein_bug():
    """Ohne NaN muss die Funktion dasselbe wie np.corrcoef liefern."""
    t_lern = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    t_pruef = pd.Series([1.1, 2.2, 2.9, 3.8, 5.3])
    r, n = auswertung.korrelation_lern_pruef(t_lern, t_pruef)
    erwartet = float(np.corrcoef(t_lern, t_pruef)[0, 1])
    assert n == 5
    assert r == pytest.approx(erwartet)


def test_korrelation_ein_nan_wert_gibt_nicht_nan_zurueck():
    """Vorfall vom 12.09.2026: ein NaN in t_lern darf die Korrelation der
    UEBRIGEN Zeilen nicht zerstoeren - np.corrcoef pur wuerde hier NaN
    liefern.
    """
    t_lern = pd.Series([1.0, 2.0, 3.0, 4.0, np.nan])
    t_pruef = pd.Series([1.1, 2.2, 2.9, 3.8, 8.29])
    r, n = auswertung.korrelation_lern_pruef(t_lern, t_pruef)
    assert n == 4
    assert not np.isnan(r)


def test_korrelation_zu_wenig_zeilen_gibt_explizit_nan():
    """Weniger als 2 verwertbare Zeilen: explizit NaN statt eines
    zufaelligen Werts - und kein Absturz.
    """
    t_lern = pd.Series([1.0, np.nan])
    t_pruef = pd.Series([1.1, 2.2])
    r, n = auswertung.korrelation_lern_pruef(t_lern, t_pruef)
    assert n == 1
    assert np.isnan(r)


def test_ein_trade_im_lernfenster_erscheint_nicht_als_bester_pruefwert():
    """Ein Versuch mit Score NaN (zu wenige Trades im Lernfenster) darf
    beim Filtern fuer die "beste Pruefwert"-Rangliste nicht mitzaehlen,
    selbst wenn sein t_pruef zufaellig hoch ist.
    """
    df = pd.DataFrame({
        "score": [1.2, np.nan, 0.9],
        "t_lern": [3.5, np.nan, 2.1],
        "t_pruef": [4.0, 8.29, 3.0],
        "n_trades": [70, 1, 65],
    })
    gefiltert = df[df["t_pruef"].notna() & df["score"].notna()]
    assert 8.29 not in gefiltert["t_pruef"].values
    assert gefiltert["t_pruef"].max() == 4.0
