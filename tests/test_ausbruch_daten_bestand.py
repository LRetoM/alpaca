"""Tests fuer die Bestandsverwaltung des Kursvorrats.

Anlass (12.09.2026): Ein abgebrochener Download liess einen **leeren**
Jahresordner `15Min_2016` zurueck. `jahre_vorhanden()` zaehlte ihn mit,
und damit war die Schnittmenge ueber alle Jahre **null** - jedes Skript
ohne ausdrueckliche Jahresangabe haette ins Leere gegriffen, ohne dass
der Grund sichtbar gewesen waere.
"""

from __future__ import annotations

import pandas as pd
import pytest

from alpaca_bot import ausbruch_daten as ad


@pytest.fixture
def vorrat(tmp_path, monkeypatch):
    monkeypatch.setattr(ad, "VORRAT", tmp_path)
    return tmp_path


def _jahr_anlegen(vorrat, jahr, symbole, raster="15Min"):
    d = vorrat / f"{raster}_{jahr}"
    d.mkdir(parents=True, exist_ok=True)
    for s in symbole:
        df = pd.DataFrame({"open": [1.0], "high": [1.0], "low": [1.0],
                           "close": [1.0], "volume": [1.0]},
                          index=pd.to_datetime(["2020-01-02 14:30:00+00:00"]))
        df.to_parquet(d / f"{s}.parquet")
    return d


def test_leerer_jahresordner_zaehlt_nicht(vorrat):
    """DER Test. Ein angelegter, aber nie gefuellter Ordner ist kein Jahr."""
    _jahr_anlegen(vorrat, 2021, ["AAA", "BBB"])
    (vorrat / "15Min_2016").mkdir()          # abgebrochener Download
    assert ad.jahre_vorhanden("15Min") == [2021]


def test_leerer_ordner_zerstoert_die_schnittmenge_nicht(vorrat):
    """Die eigentliche Folge des Fehlers: Schnittmenge wird null."""
    _jahr_anlegen(vorrat, 2021, ["AAA", "BBB"])
    _jahr_anlegen(vorrat, 2022, ["AAA", "BBB"])
    (vorrat / "15Min_2016").mkdir()
    jahre = ad.jahre_vorhanden("15Min")
    assert ad.symbole_vorhanden("15Min", jahre) == ["AAA", "BBB"]


def test_schnitt_und_vereinigung_unterscheiden_sich(vorrat):
    _jahr_anlegen(vorrat, 2021, ["ALT", "BEIDE"])
    _jahr_anlegen(vorrat, 2022, ["BEIDE", "NEU"])
    jahre = ad.jahre_vorhanden("15Min")
    assert ad.symbole_vorhanden("15Min", jahre, modus="schnitt") == ["BEIDE"]
    assert ad.symbole_vorhanden("15Min", jahre,
                                modus="vereinigung") == ["ALT", "BEIDE", "NEU"]


def test_ohne_vorrat_keine_jahre(vorrat):
    assert ad.jahre_vorhanden("15Min") == []
    assert ad.symbole_vorhanden("15Min") == []


def test_fremdes_raster_wird_ignoriert(vorrat):
    _jahr_anlegen(vorrat, 2021, ["AAA"], raster="15Min")
    _jahr_anlegen(vorrat, 2021, ["AAA"], raster="1Day")
    assert ad.jahre_vorhanden("15Min") == [2021]
    assert ad.jahre_vorhanden("1Day") == [2021]
