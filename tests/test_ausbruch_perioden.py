"""Tests fuer den Zeitraum-Schnitt (`Kursdaten.zeitraum`).

Grundlage der Auswertung je Periode (`scripts/55_ausbruch_perioden.py`).
Zwei Eigenschaften muessen stimmen, sonst ist jede Jahreszahl falsch:

1. **Keine Ueberlappung, keine Luecke.** Grenzt ein Jahr an das naechste,
   darf kein Bar doppelt gezaehlt werden und keiner fehlen - sonst
   taucht derselbe Trade in zwei Jahren auf.
2. **Sicht statt Kopie.** Sechs Jahre aus einem Datensatz von knapp
   einem Gigabyte duerfen nicht sechs Kopien erzeugen.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from alpaca_bot import ausbruch
from tests.test_ausbruch import _handelszeit_index


def _kursdaten(n=600):
    idx = _handelszeit_index(n)
    c = np.linspace(10.0, 20.0, n)
    df = pd.DataFrame(
        {"open": c, "high": c * 1.001, "low": c * 0.999, "close": c,
         "volume": np.full(n, 1e6)}, index=idx)
    return ausbruch.Kursdaten.aus_bars({"AAA": df})


def test_angrenzende_zeitraeume_ueberlappen_nicht_und_lassen_keine_luecke():
    kd = _kursdaten()
    mitte = kd.achse[kd.n_bars // 2]
    a = kd.zeitraum(None, mitte)
    b = kd.zeitraum(mitte, None)
    assert a.n_bars + b.n_bars == kd.n_bars
    assert a.achse[-1] < mitte <= b.achse[0]


def test_zeitraum_ist_eine_sicht_keine_kopie():
    kd = _kursdaten()
    teil = kd.zeitraum(kd.achse[10], kd.achse[100])
    assert np.shares_memory(teil.arrays["AAA"][3], kd.arrays["AAA"][3])


def test_offene_grenzen_liefern_den_ganzen_bestand():
    kd = _kursdaten()
    assert kd.zeitraum(None, None).n_bars == kd.n_bars


def test_leerer_zeitraum_ist_ein_fehler():
    """Ein Jahr ohne Daten muss auffallen, nicht still 0 Trades liefern."""
    kd = _kursdaten()
    with pytest.raises(ValueError, match="Leerer Zeitraum"):
        kd.zeitraum(kd.achse[-1] + pd.Timedelta(days=1),
                    kd.achse[-1] + pd.Timedelta(days=2))


def test_naive_zeitangabe_wird_angenommen():
    """Die Achse ist zeitzonenbehaftet, die Eingabe oft nicht - das darf
    kein TypeError sein."""
    kd = _kursdaten()
    jahr = int(kd.achse[0].year)
    teil = kd.zeitraum(f"{jahr}-01-01", f"{jahr + 5}-01-01")
    assert teil.n_bars > 0


def test_tagesraster_wird_mitgeschnitten():
    """`bar_im_tag` und `letzter_des_tages` muessen zur Achse passen -
    sonst laufen Tageszeit-Filter und Tagesschluss auf falschen Bars."""
    kd = _kursdaten()
    teil = kd.zeitraum(kd.achse[50], kd.achse[200])
    assert len(teil.bar_im_tag) == teil.n_bars
    assert len(teil.letzter_des_tages) == teil.n_bars
    assert np.array_equal(teil.bar_im_tag, kd.bar_im_tag[50:200])
