"""Tests fuer das Versuchsprotokoll der Ausbruch-Suche.

Das Protokoll ist die Grundlage jeder spaeteren Auswertung. Geht dabei
etwas verloren oder wird falsch zugeordnet, ist ein 48-Stunden-Lauf
wertlos - und man merkt es erst am Ende. Deshalb Tests auf genau die
Stellen, an denen das passieren kann.
"""

from __future__ import annotations

import pytest

from alpaca_bot import ausbruch_versuche as av
from alpaca_bot.ausbruch_suche import Versuch


@pytest.fixture(autouse=True)
def _eigenes_verzeichnis(tmp_path, monkeypatch):
    """Niemals in den echten Datenbestand schreiben."""
    import alpaca_bot.config as cfg
    monkeypatch.setattr(cfg, "DATA_DIR", tmp_path)
    monkeypatch.setattr(av, "DATA_DIR", tmp_path)


def _versuch(nr: int = 1, score: float = 1.5, besser: bool = False) -> Versuch:
    return Versuch(
        nr=nr, phase="Bergsteigen", config={"anstieg_pct": 10, "halten_bars": 26},
        score=score, besser=besser,
        kennzahlen={"n_trades": 120, "t_wert": score, "rendite_pct": 12.3,
                    "mittel_pct": 0.4, "max_drawdown_pct": -8.0,
                    "n_handelstage": 90},
    )


def test_versuche_werden_vollstaendig_gespeichert():
    """Kein Versuch darf verloren gehen - er ist die Datengrundlage."""
    p = av.Protokoll("t", bundel=1000)
    for i in range(250):
        p.merken(_versuch(nr=i + 1))
    p.leeren()
    assert p.anzahl() == 250


def test_puffer_wird_bei_erreichter_buendelgroesse_selbst_geleert():
    """Sonst haelt ein 48-Stunden-Lauf eine Million Zeilen im Speicher."""
    p = av.Protokoll("t", bundel=50)
    for i in range(120):
        p.merken(_versuch(nr=i + 1))
    # 120 Versuche, Buendel 50 -> zweimal automatisch geschrieben.
    assert p.anzahl() == 100
    p.leeren()
    assert p.anzahl() == 120


def test_pruefwerte_werden_mit_ihrem_grund_gespeichert():
    """Die Unterscheidung traegt die ganze Auswertung: 'bester' ist eine
    schiefe Auswahl, 'stichprobe' ist unverzerrt. Wer beides vermischt,
    rechnet den Zusammenhang zwischen Lern- und Pruefwert falsch."""
    p = av.Protokoll("t", bundel=1000)
    p.merken(_versuch(1, besser=True), {"t_wert": 2.0, "rendite_pct": 5.0},
             "bester")
    p.merken(_versuch(2), {"t_wert": -0.4, "rendite_pct": -1.0}, "stichprobe")
    p.merken(_versuch(3))          # ohne Pruefung
    p.leeren()

    df = av.zusammenfuehren(["t"])
    assert len(df) == 3
    assert set(df["pruef_grund"].dropna()) == {"bester", "stichprobe"}
    assert df["t_pruef"].notna().sum() == 2
    assert df.loc[df["pruef_grund"] == "bester", "t_pruef"].iloc[0] == 2.0


def test_config_wird_in_spalten_entfaltet():
    """Ohne Entfaltung laesst sich nicht fragen, welcher Achsenwert
    systematisch besser abschneidet - das ist der Hauptzweck."""
    p = av.Protokoll("t", bundel=1000)
    p.merken(_versuch(1))
    p.leeren()
    df = av.zusammenfuehren(["t"])
    assert "k_anstieg_pct" in df.columns
    assert "k_halten_bars" in df.columns
    assert df["k_anstieg_pct"].iloc[0] == 10


def test_mehrere_instanzen_werden_zusammengefuehrt():
    """Vier parallele Instanzen, eine Auswertung."""
    for inst, n in (("a", 10), ("b", 7), ("c", 3)):
        p = av.Protokoll(inst, bundel=1000)
        for i in range(n):
            p.merken(_versuch(nr=i + 1))
        p.leeren()

    assert set(av.instanzen()) == {"a", "b", "c"}
    df = av.zusammenfuehren()
    assert len(df) == 20
    assert set(df["instanz"]) == {"a", "b", "c"}
    assert dict(df.groupby("instanz").size()) == {"a": 10, "b": 7, "c": 3}


def test_getrennte_dateien_je_instanz():
    """Vier Prozesse in EINER SQLite blockieren sich gegenseitig
    ('database is locked'). Bei 5 Versuchen je Sekunde ueber 48 Stunden
    waere das ein Dauerproblem - deshalb eine Datei je Instanz."""
    av.Protokoll("a").leeren()
    av.Protokoll("b").leeren()
    assert av._datei("a") != av._datei("b")
    assert av._datei("a").exists() and av._datei("b").exists()


def test_unendliche_werte_werden_zu_null():
    """`-inf` als Score ist in SQLite wertlos und verfaelscht jede
    Mittelwertbildung. Lieber ehrlich NULL."""
    p = av.Protokoll("t", bundel=1000)
    v = _versuch(1)
    v.score = float("-inf")
    v.kennzahlen["t_wert"] = float("nan")
    p.merken(v)
    p.leeren()
    df = av.zusammenfuehren(["t"])
    assert df["score"].isna().all()
    assert df["t_lern"].isna().all()


def test_leeres_protokoll_liefert_leere_tabelle():
    """Die Auswertung darf am ersten Tag nicht abstuerzen."""
    assert av.zusammenfuehren().empty
    assert av.instanzen() == []


def test_protokoll_ueberlebt_neuanlage():
    """Nach einem Neustart des Dienstes muss angehaengt werden, nicht
    ueberschrieben - sonst kostet jeder Absturz alle bisherigen Daten."""
    p1 = av.Protokoll("t", bundel=1000)
    for i in range(5):
        p1.merken(_versuch(nr=i + 1))
    p1.leeren()

    p2 = av.Protokoll("t", bundel=1000)      # wie nach einem Neustart
    assert p2.anzahl() == 5
    p2.merken(_versuch(nr=6))
    p2.leeren()
    assert p2.anzahl() == 6
