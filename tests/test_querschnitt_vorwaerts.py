"""Tests fuer das Vorwaertsprotokoll.

Der Wert dieses Protokolls haengt an genau einer Eigenschaft: **ein
geschriebener Korb ist unveraenderlich**. Waere er es nicht, koennte er
nach dem Ergebnis angepasst werden - und dann waere das Ganze ein
Backtest mit zusaetzlichen Schritten.

Geprueft wird darum vor allem, dass Ueberschreiben nicht geht.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from alpaca_bot.querschnitt_vorwaerts import Vorwaerts


@pytest.fixture
def db(tmp_path):
    return Vorwaerts(tmp_path / "vw.sqlite")


def _korb():
    long = pd.Series({"AAA": 2.5, "BBB": 2.1})
    short = pd.Series({"YYY": -1.8, "ZZZ": -2.2})
    kurse = pd.Series({"AAA": 100.0, "BBB": 50.0, "YYY": 20.0, "ZZZ": 30.0})
    return long, short, kurse


def _anmelden(db, id="Q01"):
    return db.anmelden(
        id=id, name="Quartals-Momentum",
        hypothese="Querschnitt-Momentum ueber 120 Tage traegt auch nach "
                  "Kosten, weil bei 63 Tagen Haltedauer die Spanne kaum "
                  "ins Gewicht faellt.",
        config={"signal": "momentum", "halten_tage": 63},
        kriterien={"t_schwelle": 2.0, "min_perioden": 20})


# --- Anmeldung --------------------------------------------------------

def test_anmeldung_wird_gespeichert(db):
    _anmelden(db)
    a = db.anmeldung("Q01")
    assert a["name"] == "Quartals-Momentum"
    assert a["config"]["halten_tage"] == 63
    assert a["kriterien"]["t_schwelle"] == 2.0


def test_anmeldung_ohne_hypothese_wird_abgelehnt(db):
    with pytest.raises(ValueError, match="Hypothese"):
        db.anmelden(id="X", name="X", hypothese="zu kurz",
                    config={}, kriterien={})


def test_anmeldung_wird_nicht_ueberschrieben(db):
    """Eine Voranmeldung, die man ersetzen kann, ist keine."""
    _anmelden(db)
    with pytest.raises(ValueError, match="existiert seit"):
        _anmelden(db)


# --- Koerbe: das Kernversprechen --------------------------------------

def test_korb_wird_geschrieben(db):
    _anmelden(db)
    long, short, kurse = _korb()
    n = db.korb_schreiben("Q01", "2026-09-12", long, short, kurse)
    assert n == 4
    k = db.korb("Q01", "2026-09-12")
    assert set(k["seite"]) == {"long", "short"}
    assert len(k) == 4


def test_korb_kann_nicht_ueberschrieben_werden(db):
    """DER Test. Wer einen Korb nachtraeglich aendern kann, kann ihn nach
    dem Ergebnis aendern - und dann ist das Protokoll wertlos."""
    _anmelden(db)
    long, short, kurse = _korb()
    db.korb_schreiben("Q01", "2026-09-12", long, short, kurse)

    anders_long = pd.Series({"GEWINNER": 9.9})
    anders_kurse = pd.Series({"GEWINNER": 10.0})
    with pytest.raises(ValueError, match="wird nicht neu geschrieben"):
        db.korb_schreiben("Q01", "2026-09-12", anders_long,
                          pd.Series(dtype=float), anders_kurse)

    # Der alte Korb steht unveraendert
    k = db.korb("Q01", "2026-09-12")
    assert "GEWINNER" not in set(k["symbol"])
    assert len(k) == 4


def test_symbole_ohne_kurs_fallen_heraus(db):
    _anmelden(db)
    long = pd.Series({"AAA": 2.5, "OHNE_KURS": 2.4})
    kurse = pd.Series({"AAA": 100.0})
    n = db.korb_schreiben("Q01", "2026-09-12", long,
                          pd.Series(dtype=float), kurse)
    assert n == 1


def test_mehrere_stichtage_nebeneinander(db):
    _anmelden(db)
    long, short, kurse = _korb()
    db.korb_schreiben("Q01", "2026-06-12", long, short, kurse)
    db.korb_schreiben("Q01", "2026-09-12", long, short, kurse)
    assert db.stichtage("Q01") == ["2026-06-12", "2026-09-12"]


# --- Offene und Ergebnisse --------------------------------------------

def test_offene_stichtage_sind_die_ohne_ergebnis(db):
    _anmelden(db)
    long, short, kurse = _korb()
    db.korb_schreiben("Q01", "2026-06-12", long, short, kurse)
    db.korb_schreiben("Q01", "2026-09-12", long, short, kurse)
    assert len(db.offene("Q01")) == 2

    db.ergebnis_schreiben("Q01", "2026-06-12", ende="2026-09-10",
                          r_long=3.0, r_short=1.0, brutto_pct=2.0,
                          netto_pct=1.4, n_long=2, n_short=2, fehlend=0)
    assert db.offene("Q01") == ["2026-09-12"]


def test_ergebnisse_kommen_als_tabelle_zurueck(db):
    _anmelden(db)
    long, short, kurse = _korb()
    db.korb_schreiben("Q01", "2026-06-12", long, short, kurse)
    db.ergebnis_schreiben("Q01", "2026-06-12", ende="2026-09-10",
                          r_long=3.0, r_short=1.0, brutto_pct=2.0,
                          netto_pct=1.4, n_long=2, n_short=2, fehlend=0)
    e = db.ergebnisse("Q01")
    assert len(e) == 1
    assert e["netto_pct"].iloc[0] == pytest.approx(1.4)


def test_erfassungszeitpunkt_wird_mitgeschrieben(db):
    """Ohne Zeitstempel waere nicht nachweisbar, dass der Korb vor dem
    Ergebnis existierte."""
    _anmelden(db)
    long, short, kurse = _korb()
    db.korb_schreiben("Q01", "2026-09-12", long, short, kurse)
    k = db.korb("Q01", "2026-09-12")
    assert k["erfasst_am"].notna().all()
    assert k["erfasst_am"].str.startswith("20").all()
