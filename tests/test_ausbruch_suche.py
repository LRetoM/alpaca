"""Tests fuer die automatische Konfigurationssuche.

Eine Suche ueber Millionen Kombinationen ist die gefaehrlichste Maschine
im Projekt: Bei N Versuchen liegt das Zufallsmaximum bei
`sqrt(2 ln N)` (§B2). Diese Tests pruefen deshalb nicht, ob die Suche
gute Werte findet - das tut sie immer, auch auf Rauschen -, sondern ob
die **Gegenmittel** greifen:

1. Das Prueffenster wird nie zur Auswahl benutzt und ueberlappt zeitlich
   nicht mit dem Lernfenster.
2. Jeder Teilversuch hebt die Zufallsschwelle.
3. Bergsteigen aendert genau EINE Achse je Schritt.
4. Konfigurationen mit zu wenigen Trades bekommen keinen Score.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from alpaca_bot import ausbruch_store, ausbruch_suche as su


def _bars(n=1200, saat=7):
    r = np.random.default_rng(saat)
    idx = pd.date_range("2025-01-02 14:30", periods=n, freq="15min", tz="UTC")
    c = 100 * np.exp(np.cumsum(r.normal(0, 0.004, n)))
    o = np.concatenate([[c[0]], c[:-1]])
    return pd.DataFrame(
        {"open": o, "high": np.maximum(o, c) * 1.001,
         "low": np.minimum(o, c) * 0.999, "close": c,
         "volume": r.lognormal(13, 1, n)}, index=idx)


# ------------------------------------------------------- Fenster-Trennung
def test_fenster_ueberlappen_zeitlich_nicht():
    """Der Kern des ganzen Verfahrens. Ueberlappen die Fenster, hat die
    Suche das Prueffenster mitoptimiert und es ist wertlos."""
    bars = {f"S{i}": _bars(saat=i) for i in range(4)}
    lern, pruef, grenze = su.teilen(bars, 0.7)

    for s in lern:
        assert lern[s].index.max() < grenze
    for s in pruef:
        assert pruef[s].index.min() >= grenze


def test_schnitt_liegt_fuer_alle_symbole_gleich():
    """Ein symbolweise verschobener Schnitt haette fuer verschiedene
    Symbole verschiedene Marktphasen im Prueffenster - dann misst der
    Vergleich die Phase, nicht die Konfiguration."""
    bars = {f"S{i}": _bars(n=900 + i * 50, saat=i) for i in range(4)}
    lern, pruef, grenze = su.teilen(bars, 0.7)
    assert all(d.index.max() < grenze for d in lern.values())
    assert all(d.index.min() >= grenze for d in pruef.values())


def test_teilen_verlangt_genug_daten():
    with pytest.raises(ValueError):
        su.teilen({"A": _bars(n=50)}, 0.7)


# ------------------------------------------------------------ Bergsteigen
def test_nachbarn_aendern_genau_eine_achse():
    """Dieselbe Regel wie fuer Flottenbots (CLAUDE.md): Zwei gleichzeitig
    geaenderte Achsen machen eine Verbesserung nicht zuordenbar."""
    s = su.Suche({}, {}, raum={"a": [1, 2, 3], "b": [10, 20], "c": [5, 6]})
    start = {"a": 1, "b": 10, "c": 5}
    for n in s._nachbarn(start):
        anders = [k for k in start if n[k] != start[k]]
        assert len(anders) == 1, f"{anders} Achsen geaendert statt genau einer"


def test_nachbarn_sind_vollstaendig():
    """Jeder Nachbar muss erreichbar sein - sonst bleibt ein Teil des
    Raums systematisch unbesucht, ohne dass es auffaellt."""
    raum = {"a": [1, 2, 3], "b": [10, 20]}
    s = su.Suche({}, {}, raum=raum)
    n = s._nachbarn({"a": 1, "b": 10})
    assert len(n) == (3 - 1) + (2 - 1)


def test_festgehaltene_achsen_werden_nicht_variiert():
    s = su.Suche({}, {}, raum={"a": [1, 2], "b": [3, 4]}, fest={"b": 99})
    assert "b" not in s.raum
    for n in s._nachbarn({"a": 1}):
        assert "b" not in n


# ------------------------------------------------------------- Bewertung
def test_zu_wenige_trades_bekommen_keinen_score():
    """Sonst schlaegt eine Konfiguration mit 3 Gluecks-Trades jede mit
    300 soliden - genau die Falle aus §B4."""
    s = su.Suche({}, {}, min_trades=1000)
    score, k = s._bewerten({"anstieg_pct": 50, "fenster_bars": 4},
                           {"A": _bars()})
    assert score == float("-inf")


def test_unsinnige_kombination_stuerzt_nicht_ab():
    """Ein Suchraum erzeugt zwangslaeufig Unsinn. Der darf einen Lauf
    ueber Stunden nicht kippen."""
    s = su.Suche({}, {}, min_trades=1)
    score, _ = s._bewerten({"anstieg_pct": -5, "fenster_bars": 0},
                           {"A": _bars()})
    assert score == float("-inf")


def test_tageszeitfenster_wird_zurechtgebogen_statt_zu_werfen():
    """`bis < von` ist im Raster moeglich und ergibt keinen Sinn -
    die Suche gleicht es an, statt den Versuch zu verlieren."""
    s = su.Suche({}, {}, min_trades=1)
    score, k = s._bewerten(
        {"anstieg_pct": 1, "fenster_bars": 4,
         "tageszeit_von_bar": 20, "tageszeit_bis_bar": 4,
         "min_rel_volumen": 0, "min_dollar_volumen": 0},
        {"A": _bars()})
    assert score != float("-inf") or k is not None    # kein Absturz


# -------------------------------------------------------------- Schwelle
def test_schwelle_steigt_mit_der_zahl_der_versuche():
    s = su.Stand()
    s.versuche = 10
    niedrig = s.schwelle
    s.versuche = 5000
    assert s.schwelle > niedrig
    assert s.schwelle == pytest.approx(4.13, abs=0.02)


def test_schwelle_hat_eine_untergrenze():
    """Der erste Versuch darf keine laecherlich niedrige Huerde bekommen."""
    s = su.Stand()
    s.versuche = 1
    assert s.schwelle >= 2.0


def test_suchversuche_heben_den_gemeinsamen_zaehler(tmp_path, monkeypatch):
    """Eine Suche mit 3.000 Durchlaeufen muss die Schwelle fuer ALLE
    Auswertungen heben - auch fuer Handlaeufe in der Werkstatt. Sonst
    ist die Zaehlung wertlos."""
    monkeypatch.setattr(ausbruch_store, "DB", tmp_path / "t.sqlite")
    vorher = ausbruch_store.n_versuche()
    lid = ausbruch_store.neuer_lauf({}, jahr=2025, raster="15Min",
                                    n_symbole=1, notiz="Suche")
    assert ausbruch_store.n_versuche() == vorher + 1

    ausbruch_store.suchversuche_buchen(lid, 3000)
    # Die Suche zaehlt als ihre Teilversuche, nicht zusaetzlich als Lauf.
    assert ausbruch_store.n_versuche() == vorher + 3000
    # sqrt(2 * ln 3000) = 4,00 - eine Suche dieser Groesse macht die
    # Huerde fuer JEDE spaetere Auswertung deutlich hoeher.
    assert ausbruch_store.schwelle_sigma() == pytest.approx(4.00, abs=0.02)


def test_verworfener_lauf_bleibt_im_zaehler(tmp_path, monkeypatch):
    """Ein Zaehler, aus dem man Versuche entfernen kann, senkt
    nachtraeglich die Huerde, gegen die er messen soll (§B2)."""
    monkeypatch.setattr(ausbruch_store, "DB", tmp_path / "t.sqlite")
    lid = ausbruch_store.neuer_lauf({}, jahr=2025, raster="15Min", n_symbole=1)
    n = ausbruch_store.n_versuche()
    ausbruch_store.lauf_loeschen(lid)
    assert ausbruch_store.n_versuche() == n


# ---------------------------------------------------------------- Ablauf
def test_suche_liefert_versuche_und_haelt_an():
    """Ende-zu-Ende: Die Suche muss anhalten, wenn sie soll - sonst
    laeuft sie nach Strg+C weiter."""
    bars = {f"S{i}": _bars(saat=i) for i in range(3)}
    lern, pruef, _ = su.teilen(bars, 0.7)
    s = su.Suche(lern, pruef, min_trades=1, erkundung_n=3, saat=1,
                 raum={"anstieg_pct": [1, 2, 3], "fenster_bars": [4, 8],
                       "halten_bars": [4, 26]})

    gesehen = []
    for v in s.laufen(lambda: len(gesehen) >= 6):
        gesehen.append(v)
    assert len(gesehen) == 6
    assert s.stand.versuche == 6
    assert all(v.nr == i + 1 for i, v in enumerate(gesehen))


def test_keine_konfiguration_wird_zweimal_gerechnet():
    """Sonst verbrennt die Suche Zeit und zaehlt Versuche doppelt."""
    bars = {f"S{i}": _bars(saat=i) for i in range(2)}
    lern, pruef, _ = su.teilen(bars, 0.7)
    s = su.Suche(lern, pruef, min_trades=1, erkundung_n=2, saat=3,
                 raum={"anstieg_pct": [1, 2], "fenster_bars": [4, 8]})
    gesehen = []
    for v in s.laufen(lambda: len(gesehen) >= 4):
        gesehen.append(tuple(sorted(v.config.items())))
    assert len(set(gesehen)) == len(gesehen)


def test_bericht_nennt_das_prueffenster_und_nicht_den_besten_wert():
    """Das Urteil muss am Prueffenster haengen. Ein Bericht, der den
    besten Lernwert feiert, ist genau die Erzaehlung, gegen die das
    ganze Verfahren gebaut ist."""
    bars = {f"S{i}": _bars(saat=i) for i in range(3)}
    lern, pruef, _ = su.teilen(bars, 0.7)
    s = su.Suche(lern, pruef, min_trades=1, erkundung_n=2, saat=5,
                 raum={"anstieg_pct": [1, 2], "fenster_bars": [4, 8]})
    n = []
    for v in s.laufen(lambda: len(n) >= 4):
        n.append(v)
    text = s.bericht()
    assert "Prueffenster" in text
    assert "URTEIL" in text
    assert "Zufallsschwelle" in text
