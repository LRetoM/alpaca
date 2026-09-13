"""Tests fuer den Marktregime-Filter (`AusbruchConfig.regime_symbol`).

Ein Filter, der den Markt kennt, ist die gefaehrlichste Art von
Zusatzinformation: Er sieht aus wie Wissen und ist in der falschen
Fassung schlicht ein Blick in die Zukunft. Geprueft wird deshalb vor
allem die Richtung des Bar-Versatzes.

Der entscheidende Test ist `test_filter_schaut_nicht_auf_den_eigenen_bar`:
Eingestiegen wird zum OPEN von Bar i, der CLOSE von Bar i ist zu diesem
Zeitpunkt Zukunft. Wer ihn benutzt, weiss an jedem Einstieg, ob der
Markt in genau dieser Viertelstunde steigt (§4.1, §G62).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from alpaca_bot import ausbruch
from tests.test_ausbruch import _handelszeit_index


def _reihe(werte, idx):
    """DataFrame aus Schlusskursen - open = vorheriger close."""
    c = np.asarray(werte, dtype=float)
    o = np.concatenate([[c[0]], c[:-1]])
    return pd.DataFrame(
        {"open": o, "high": np.maximum(o, c) * 1.001,
         "low": np.minimum(o, c) * 0.999, "close": c,
         "volume": np.full(len(c), 1_000_000.0)},
        index=idx)


def _kursdaten(spalten: dict) -> ausbruch.Kursdaten:
    return ausbruch.Kursdaten.aus_bars(spalten)


def test_ohne_einstellung_kein_filter():
    """Vorgabe bleibt aus - die laufende Suche darf sich nicht aendern."""
    idx = _handelszeit_index(200)
    kd = _kursdaten({"AAA": _reihe(np.linspace(10, 20, 200), idx)})
    assert ausbruch.regime_maske(kd, ausbruch.AusbruchConfig()) is None


def test_unbekanntes_symbol_ist_ein_fehler_kein_stilles_aus():
    """Ein Filter, der ins Leere zeigt, muss auffallen. Sonst laeuft ein
    Versuch als 'mit Filter' durch, der gar keinen hatte."""
    idx = _handelszeit_index(200)
    kd = _kursdaten({"AAA": _reihe(np.linspace(10, 20, 200), idx)})
    cfg = ausbruch.AusbruchConfig(regime_symbol="GIBTESNICHT",
                                  regime_sma_bars=26)
    with pytest.raises(ValueError, match="nicht im Universum"):
        ausbruch.regime_maske(kd, cfg)


def test_maske_ist_wahr_im_aufwaertstrend_und_falsch_im_abwaerts():
    idx = _handelszeit_index(300)
    hoch = np.concatenate([np.linspace(100, 200, 150),
                           np.linspace(200, 100, 150)])
    kd = _kursdaten({"IDX": _reihe(hoch, idx)})
    cfg = ausbruch.AusbruchConfig(regime_symbol="IDX", regime_sma_bars=26)
    m = ausbruch.regime_maske(kd, cfg)
    assert m[100] == True   # noqa: E712 - steigender Teil
    assert m[290] == False  # noqa: E712 - fallender Teil


def test_maske_bleibt_falsch_solange_das_mittel_nicht_voll_ist():
    """Lieber keine Einstiege als Einstiege auf halber Datenbasis."""
    idx = _handelszeit_index(200)
    kd = _kursdaten({"IDX": _reihe(np.linspace(100, 200, 200), idx)})
    cfg = ausbruch.AusbruchConfig(regime_symbol="IDX", regime_sma_bars=52)
    m = ausbruch.regime_maske(kd, cfg)
    assert not m[:52].any()


def test_filter_schaut_nicht_auf_den_eigenen_bar():
    """DER Test. Ein Kurs, der genau an einem Bar einbricht.

    Bar i-1 steht noch ueber dem Mittel, Bar i stuerzt darunter. Eine
    Maske, die Bar i benutzt, waere an dieser Stelle False - sie wuesste
    vom Einbruch, bevor er handelbar ist. Richtig ist True: Zum Open von
    Bar i ist der Einbruch noch nicht bekannt.
    """
    n = 200
    idx = _handelszeit_index(n)
    werte = np.full(n, 100.0)
    werte[:100] = np.linspace(90, 110, 100)   # steigt, liegt ueber dem Mittel
    werte[100:] = 50.0                        # bricht bei Bar 100 ein
    kd = _kursdaten({"IDX": _reihe(werte, idx)})
    cfg = ausbruch.AusbruchConfig(regime_symbol="IDX", regime_sma_bars=26)
    m = ausbruch.regime_maske(kd, cfg)

    assert m[100] == True, (  # noqa: E712
        "Der Filter kennt den Einbruch von Bar 100 bereits an Bar 100 - "
        "das ist Lookahead.")
    assert m[101] == False  # noqa: E712 - ab dem Folgebar ist er bekannt


def test_filter_verhindert_einstiege_im_abwaertsmarkt():
    """Vollstaendiger Lauf: derselbe Ausbruch, einmal mit fallendem und
    einmal mit steigendem Referenzwert."""
    n = 400
    idx = _handelszeit_index(n)
    kurs = np.full(n, 50.0)
    kurs[200:] = 70.0          # +40 % Ausbruch bei Bar 200
    ware = _reihe(kurs, idx)
    ware["volume"] = 5_000_000.0

    cfg_basis = dict(anstieg_pct=20, fenster_bars=8, min_preis=5,
                     min_dollar_volumen=1_000_000.0, min_rel_volumen=0,
                     halten_bars=26, regime_sma_bars=26)

    runter = _reihe(np.linspace(200, 100, n), idx)
    erg_runter = ausbruch.lauf(
        _kursdaten({"WARE": ware, "IDX": runter}),
        ausbruch.AusbruchConfig(regime_symbol="IDX", **cfg_basis))

    hoch = _reihe(np.linspace(100, 200, n), idx)
    erg_hoch = ausbruch.lauf(
        _kursdaten({"WARE": ware, "IDX": hoch}),
        ausbruch.AusbruchConfig(regime_symbol="IDX", **cfg_basis))

    assert len(erg_runter.trades) == 0, "Im Abwaertsmarkt darf nichts kaufen"
    assert len(erg_hoch.trades) > 0, "Im Aufwaertsmarkt muss gekauft werden"


def test_referenzwert_wird_nicht_selbst_gehandelt():
    """Ein Massstab, auf den man zugleich wettet, ist keiner."""
    n = 400
    idx = _handelszeit_index(n)
    # Der Referenzwert macht selbst einen Ausbruch.
    idx_kurs = np.full(n, 50.0)
    idx_kurs[200:] = 70.0
    ref = _reihe(idx_kurs, idx)
    ref["volume"] = 5_000_000.0

    erg = ausbruch.lauf(
        _kursdaten({"IDX": ref}),
        ausbruch.AusbruchConfig(
            regime_symbol="IDX", regime_sma_bars=26, anstieg_pct=20,
            fenster_bars=8, min_preis=5, min_dollar_volumen=1_000_000.0,
            min_rel_volumen=0, halten_bars=26))
    assert "IDX" not in set(erg.trades.get("symbol", []))


def test_filter_aus_aendert_das_ergebnis_nicht():
    """Rueckwaertskompatibilitaet: Ohne Einstellung muss derselbe Lauf
    dieselben Trades liefern wie vor dem Einbau."""
    n = 400
    idx = _handelszeit_index(n)
    kurs = np.full(n, 50.0)
    kurs[200:] = 70.0
    ware = _reihe(kurs, idx)
    ware["volume"] = 5_000_000.0
    kd = _kursdaten({"WARE": ware, "IDX": _reihe(np.linspace(100, 200, n), idx)})

    basis = dict(anstieg_pct=20, fenster_bars=8, min_preis=5,
                 min_dollar_volumen=1_000_000.0, min_rel_volumen=0,
                 halten_bars=26)
    a = ausbruch.lauf(kd, ausbruch.AusbruchConfig(**basis))
    b = ausbruch.lauf(kd, ausbruch.AusbruchConfig(regime_symbol="",
                                                  regime_sma_bars=26, **basis))
    assert len(a.trades) == len(b.trades)
    assert a.kennzahlen["rendite_pct"] == pytest.approx(
        b.kennzahlen["rendite_pct"])
