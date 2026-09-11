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
    # Beide Schwellen muessen genannt sein - und die Pruefschwelle als
    # die massgebliche. Stuende hier nur eine Zahl, waere nicht zu
    # erkennen, gegen welche der Pruefwert eigentlich antritt.
    assert "Lernschwelle" in text
    assert "Pruefschwelle" in text
    assert "massgeblich" in text


def test_bergsteigen_faellt_nicht_auf_wuerfeln_zurueck():
    """Regression: Die erste Fassung kletterte nur vom GLOBAL Besten.

    War dessen Nachbarschaft abgesucht, wurde jeder weitere Versuch ein
    "Neustart" - gemessen 1.198 Neustarts bei 1.448 Versuchen, also
    praktisch kein Bergsteigen mehr. Richtig ist die Trennung zwischen
    dem Punkt, von dem geklettert wird, und dem global Besten.
    """
    bars = {f"S{i}": _bars(saat=i) for i in range(3)}
    lern, pruef, _ = su.teilen(bars, 0.7)
    s = su.Suche(lern, pruef, min_trades=1, erkundung_n=5, saat=11,
                 raum={"anstieg_pct": [1, 2, 3, 4], "fenster_bars": [2, 4, 8],
                       "halten_bars": [4, 13, 26], "gewinn_pct": [0, 5, 10]})
    n = []
    for v in s.laufen(lambda: len(n) >= 60):
        n.append(v)

    berg = sum(1 for v in n if v.phase == "Bergsteigen")
    neu = sum(1 for v in n if v.phase == "Neustart")
    assert berg > neu, (
        f"Nur {berg} Kletterschritte gegen {neu} Neustarts - die Suche "
        f"wuerfelt statt zu klettern."
    )


def test_globaler_bester_ueberlebt_einen_neustart():
    """Ein Neustart darf den besten gefundenen Punkt nie verlieren."""
    bars = {f"S{i}": _bars(saat=i) for i in range(3)}
    lern, pruef, _ = su.teilen(bars, 0.7)
    s = su.Suche(lern, pruef, min_trades=1, erkundung_n=3, saat=4, geduld=1,
                 raum={"anstieg_pct": [1, 2], "fenster_bars": [2, 4]})
    beste = []
    n = []
    for v in s.laufen(lambda: len(n) >= 12):
        n.append(v)
        if s.stand.beste_score > float("-inf"):
            beste.append(s.stand.beste_score)
    # Der beste Wert darf nie sinken.
    assert all(b >= a for a, b in zip(beste, beste[1:])), (
        "Der globale Beste ist unterwegs schlechter geworden."
    )


def test_abgesuchter_raum_beendet_die_suche_statt_zu_haengen():
    """Regression (11.09.2026): Ist jede Kombination durch, zog die
    Schleife endlos schon Gesehenes und kehrte nie zurueck.

    In der Praxis erreichbar mit einem kleinen Raster oder vielen
    festgehaltenen Achsen - dann haengt das Terminal ohne Fehlermeldung.
    """
    bars = {f"S{i}": _bars(saat=i) for i in range(2)}
    lern, pruef, _ = su.teilen(bars, 0.7)
    # Nur 2 x 2 = 4 Kombinationen.
    s = su.Suche(lern, pruef, min_trades=1, erkundung_n=2, saat=1,
                 raum={"anstieg_pct": [1, 2], "fenster_bars": [2, 4]})

    n = list(s.laufen(lambda: False))     # KEIN Stoppkriterium von aussen
    assert len(n) <= 4
    assert s.stand.phase == "abgesucht"


# ------------------------------------------------- Schwellen-Trennung
def test_pruefschwelle_haengt_an_den_pruefungen_nicht_an_den_versuchen():
    """Der wichtigste methodische Punkt der ganzen Suche.

    Die Auswahl ueber N Versuche findet NUR im Lernfenster statt. Das
    Prueffenster sieht nur die wenigen Gewinner - jede dieser
    Bewertungen ist ein sauberer Einzeltest auf Daten, die an keiner
    Auswahl beteiligt waren. Die Vielfachtestung ist auf der Lernseite
    bereits bezahlt.

    Wuerde man den Pruefwert gegen die Lernschwelle stellen, waere das
    Verfahren bei 940.000 Versuchen (Schwelle 5,24) per Konstruktion
    unfaehig, jemals etwas zu finden - auch bei einem echten Effekt.
    """
    st = su.Stand()
    st.versuche = 940_000
    st.pruef_bewertungen = 50

    assert st.schwelle == pytest.approx(5.24, abs=0.02)
    assert st.pruef_schwelle == pytest.approx(2.80, abs=0.02)
    assert st.pruef_schwelle < st.schwelle


def test_pruefschwelle_steigt_mit_wiederholten_pruefungen():
    """Wer die Suche zehnmal wiederholt und sich den besten Pruefwert
    heraussucht, hebt damit seine eigene Huerde - genau wie es §B2
    verlangt."""
    st = su.Stand()
    st.pruef_bewertungen = 20
    niedrig = st.pruef_schwelle
    st.pruef_bewertungen = 2000
    assert st.pruef_schwelle > niedrig


def test_pruefungen_werden_gezaehlt():
    """Ohne Zaehler keine Schwelle - und ohne Schwelle kein Urteil."""
    bars = {f"S{i}": _bars(saat=i) for i in range(3)}
    lern, pruef, _ = su.teilen(bars, 0.7)
    s = su.Suche(lern, pruef, min_trades=1, erkundung_n=3, saat=7,
                 pruef_stichprobe=0.0,
                 raum={"anstieg_pct": [1, 2], "fenster_bars": [4, 8]})
    n = []
    for v in s.laufen(lambda: len(n) >= 4):
        n.append(v)
    treffer = sum(1 for v in n if v.besser)
    assert s.stand.pruef_bewertungen == treffer, (
        "Jeder neue Beste muss genau eine Pruefung ausloesen."
    )


# ----------------------------------------------------- Elite-Austausch
def test_elite_wird_nur_bei_besserem_wert_ueberschrieben(tmp_path, monkeypatch):
    """Ein schlechterer Fund darf den gemeinsamen Bestwert nicht kippen -
    sonst zieht die langsamste Instanz alle anderen herunter."""
    import alpaca_bot.config as cfg
    monkeypatch.setattr(cfg, "DATA_DIR", tmp_path)

    assert su.elite_schreiben(3.0, {"a": 1}, "a") is True
    assert su.elite_schreiben(1.0, {"a": 2}, "b") is False
    assert su.elite_lesen()["score"] == 3.0
    assert su.elite_schreiben(4.5, {"a": 3}, "c") is True
    assert su.elite_lesen()["score"] == 4.5
    assert su.elite_lesen()["instanz"] == "c"


def test_elite_uebernahme_startet_in_der_umgebung_nicht_exakt(tmp_path, monkeypatch):
    """Genau beim Bestwert anzusetzen brachte nichts - dessen
    Nachbarschaft ist bereits abgesucht. Zwei Achsen werden verstellt."""
    import alpaca_bot.config as cfg
    monkeypatch.setattr(cfg, "DATA_DIR", tmp_path)
    raum = {"a": [1, 2, 3, 4], "b": [10, 20, 30], "c": [5, 6, 7]}
    beste = {"a": 1, "b": 10, "c": 5}
    su.elite_schreiben(9.0, beste, "x")

    s = su.Suche({}, {}, raum=raum, elite_anteil=1.0, saat=3)
    punkte = [s._neustartpunkt() for _ in range(20)]

    assert s.stand.elite_uebernahmen == 20
    abweichungen = [sum(1 for k in raum if p[k] != beste[k]) for p in punkte]
    assert max(abweichungen) >= 1, "Nie verstellt - waere nur Wiederholung."
    assert all(a <= 2 for a in abweichungen), (
        "Mehr als zwei Achsen verstellt - dann ist es kein Ansetzen am "
        "Bestwert mehr, sondern ein Zufallspunkt."
    )


def test_ohne_elite_datei_wird_zufaellig_gestartet(tmp_path, monkeypatch):
    """Beim allerersten Lauf gibt es noch keinen gemeinsamen Bestwert."""
    import alpaca_bot.config as cfg
    monkeypatch.setattr(cfg, "DATA_DIR", tmp_path)
    s = su.Suche({}, {}, raum={"a": [1, 2], "b": [3, 4]}, elite_anteil=1.0)
    p = s._neustartpunkt()
    assert set(p) == {"a", "b"}
    assert s.stand.elite_uebernahmen == 0


def test_elite_anteil_null_nutzt_nie_die_elite(tmp_path, monkeypatch):
    """Vier Instanzen, die alle beim selben Punkt ansetzen, sind nur
    noch eine Suche mit vierfachem Stromverbrauch - deshalb muss sich
    das abschalten lassen."""
    import alpaca_bot.config as cfg
    monkeypatch.setattr(cfg, "DATA_DIR", tmp_path)
    su.elite_schreiben(9.0, {"a": 1, "b": 3}, "x")
    s = su.Suche({}, {}, raum={"a": [1, 2], "b": [3, 4]}, elite_anteil=0.0)
    for _ in range(10):
        s._neustartpunkt()
    assert s.stand.elite_uebernahmen == 0
