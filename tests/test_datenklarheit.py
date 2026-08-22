"""Stumme Felder und vermischte Quellen (BEFUNDE §G13).

REGRESSION 22.08.2026. Die Chronik dieses Projekts besteht ueberwiegend
aus einem einzigen Fehlermuster: Ein Feld wird angelegt, sieht plausibel
aus und ist in Wahrheit leer, konstant oder falsch. Nichts stuerzt ab.
Gefunden wurde jeder dieser Faelle nur, weil jemand zufaellig gezielt
nachsah:

    bars_held        in jedem Trade 0             (15.08.)
    after_10d        nie gefuellt                 (15.08.)
    code_version     zwei Monate 'unbekannt'      (15.08., 66 % der Daten)
    Bar-Cache        nie getroffen                (21.08.)
    decisions        98,4 % Simulationszeilen     (22.08.)

Diese Tests sichern die Pruefungen, die daraus eine Routine machen.
"""

from __future__ import annotations

import datetime as dt
import json
import sqlite3

import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def journal_db(tmp_path, monkeypatch):
    """Ein Journal mit zwei Quellen - live und Simulation."""
    db = tmp_path / "journal.sqlite"
    c = sqlite3.connect(db)
    c.execute("CREATE TABLE runs (run_id TEXT PRIMARY KEY, script TEXT,"
              " started_at TEXT, status TEXT, ended_at TEXT, code_version TEXT)")
    c.execute("CREATE TABLE decisions (decision_id TEXT PRIMARY KEY, run_id TEXT,"
              " ts TEXT, symbol TEXT, action TEXT, reasons TEXT, strategy TEXT)")
    c.execute("CREATE TABLE outcomes (decision_id TEXT, horizon INT,"
              " fwd_return REAL, ts TEXT)")
    c.execute("INSERT INTO runs VALUES ('live1','live_trade','2026-08-20',"
              "'ok','2026-08-20','abc123')")
    c.execute("INSERT INTO runs VALUES ('sim1','simulate','2026-08-21',"
              "'ok','2026-08-21','abc123')")
    c.commit()
    return db, c


def _schreibe(c, run_id, n, action="buy", kontext=True, start_tag=20):
    for i in range(n):
        gruende = {"score": 0.9}
        if kontext:
            gruende |= {"regime_markt": "bullisch", "regime_vola": "ruhig",
                        "sektor": f"S{i % 3}", "liq_dezil": i % 10}
        c.execute("INSERT INTO decisions VALUES (?,?,?,?,?,?,?)",
                  (f"{run_id}_{action}_{start_tag}_{i}", run_id,
                   f"2026-08-{start_tag:02d}T14:{i % 60:02d}:00+00:00",
                   f"SYM{i}", action, json.dumps(gruende), "engine"))
    c.commit()


class TestStummeFelderWaechter:
    """`data_integrity.check_stumme_felder`."""

    def test_ausfall_eines_feldes_wird_gemeldet(self, journal_db, monkeypatch):
        """Der Kernfall: ein Feld, das aufhoert, sich zu fuellen."""
        db, c = journal_db
        _schreibe(c, "live1", 40, kontext=True, start_tag=18)   # aeltere: gefuellt
        _schreibe(c, "live1", 25, kontext=False, start_tag=21)  # juengste: leer

        from alpaca_bot import data_integrity as di
        monkeypatch.setattr(di, "JOURNAL_DB", db)
        r = di.IntegrityReport()
        di.check_stumme_felder(None, r)

        namen = [f.check for f in r.findings]
        assert any("regime_markt" in n and "nicht mehr" in n for n in namen)
        assert any(f.severity == "fehler" for f in r.findings)

    def test_neu_eingefuehrtes_feld_loest_nichts_aus(self, journal_db, monkeypatch):
        """Die Falle, in die der erste Entwurf lief.

        Ein Feld, das es frueher nicht gab und seit gestern lueckenlos
        gefuellt wird, ist gesund. Meldete der Check das, leuchtete er
        ~30 Tage lang gelb - und eine Warnung, die immer leuchtet, wird
        weggeklickt.
        """
        db, c = journal_db
        _schreibe(c, "live1", 40, kontext=False, start_tag=18)  # aeltere: leer
        _schreibe(c, "live1", 25, kontext=True, start_tag=21)   # juengste: gefuellt

        from alpaca_bot import data_integrity as di
        monkeypatch.setattr(di, "JOURNAL_DB", db)
        r = di.IntegrityReport()
        di.check_stumme_felder(None, r)

        assert not [f for f in r.findings if f.severity == "fehler"]

    def test_simulationszeilen_zaehlen_nicht_mit(self, journal_db, monkeypatch):
        """Der zweite Fehlalarm: fremde Zeilen fuellten die Stichprobe.

        Simulationslaeufe fuehren die Kontextfelder nicht. Ohne den
        Filter auf `runs.script='live_trade'` melden sie einen Ausfall,
        den es nicht gibt - im echten Journal stellten sie 98,4 % der
        Zeilen.
        """
        db, c = journal_db
        _schreibe(c, "live1", 25, kontext=True, start_tag=21)
        _schreibe(c, "sim1", 300, kontext=False, start_tag=21)

        from alpaca_bot import data_integrity as di
        monkeypatch.setattr(di, "JOURNAL_DB", db)
        r = di.IntegrityReport()
        di.check_stumme_felder(None, r)

        assert not [f for f in r.findings if f.severity == "fehler"]

    def test_konstantes_feld_wird_als_solches_benannt(self, journal_db, monkeypatch):
        """Kein Fehler, aber keine Auswertungsachse - das muss dastehen."""
        db, c = journal_db
        _schreibe(c, "live1", 30, kontext=True, start_tag=21)

        from alpaca_bot import data_integrity as di
        monkeypatch.setattr(di, "JOURNAL_DB", db)
        r = di.IntegrityReport()
        di.check_stumme_felder(None, r)

        konst = [f for f in r.findings if "konstant" in f.check]
        assert any("regime_markt" in f.check for f in konst)
        assert all(f.severity == "auffaellig" for f in konst)

    def test_aktionsarten_werden_getrennt_geprueft(self, journal_db, monkeypatch):
        """Ein Topf aus ungleichen Dingen verdeckt echte Ausfaelle.

        `topup` fuehrt den Kontext gar nicht. Lagen alle Aktionen in
        einem Topf, verwaesserten die vielen topup-Zeilen einen echten
        Ausfall bei `buy` - und meldeten zugleich einen, den es nicht gab.
        """
        db, c = journal_db
        _schreibe(c, "live1", 25, action="buy", kontext=True, start_tag=21)
        _schreibe(c, "live1", 300, action="topup", kontext=False, start_tag=21)

        from alpaca_bot import data_integrity as di
        monkeypatch.setattr(di, "JOURNAL_DB", db)
        r = di.IntegrityReport()
        di.check_stumme_felder(None, r)

        assert not [f for f in r.findings if f.severity == "fehler"]


class TestBarsHeldStimmigkeit:
    """`data_integrity.check_bars_held_stimmig`."""

    def _lifecycle(self, monkeypatch, zeilen):
        from alpaca_bot import data_integrity as di

        class FakeLifecycle:
            def table(self):
                return pd.DataFrame(zeilen)

        import alpaca_bot.lifecycle as lc
        monkeypatch.setattr(lc, "Lifecycle", FakeLifecycle)
        r = di.IntegrityReport()
        di.check_bars_held_stimmig(r)
        return r

    def test_falsche_null_wird_gefunden(self, monkeypatch):
        """Der reale Fall: 36 von 56 Trades meldeten 0 statt 2-5 Tagen."""
        zeilen = [{"symbol": "CHRW", "entry_date": "2026-07-28T00:00:00+00:00",
                   "exit_date": "2026-07-31T14:02:00+00:00", "bars_held": 0}]
        r = self._lifecycle(monkeypatch, zeilen)
        assert [f for f in r.findings if f.severity == "fehler"]
        assert "widerspricht" in r.findings[0].check

    def test_stimmige_werte_melden_nichts(self, monkeypatch):
        """Die 20 Trades nach der Reparatur stimmten exakt - Abweichung 0."""
        zeilen = [{"symbol": "MOS", "entry_date": "2026-08-17T14:00:00+00:00",
                   "exit_date": "2026-08-21T14:00:00+00:00", "bars_held": 4}]
        r = self._lifecycle(monkeypatch, zeilen)
        assert not r.findings

    def test_ein_tag_toleranz_fuer_feiertage(self, monkeypatch):
        """`busday_count` kennt keine Boersenfeiertage - ein Tag Spiel."""
        zeilen = [{"symbol": "X", "entry_date": "2026-08-17T14:00:00+00:00",
                   "exit_date": "2026-08-21T14:00:00+00:00", "bars_held": 3}]
        r = self._lifecycle(monkeypatch, zeilen)
        assert not r.findings

    def test_offene_position_wird_uebersprungen(self, monkeypatch):
        """Ohne Ausstieg gibt es nichts zu vergleichen."""
        zeilen = [{"symbol": "X", "entry_date": "2026-08-17T14:00:00+00:00",
                   "exit_date": None, "bars_held": 0}]
        r = self._lifecycle(monkeypatch, zeilen)
        assert not r.findings


class TestJournalTrenntLiveVonSimulation:
    """`journal.decision_quality` - sicher per Vorgabe."""

    def test_vorgabe_ist_nur_live(self):
        """Die gefaehrliche Richtung muss die bewusste Angabe sein.

        Von vier Aufrufern gab genau einer `script=` mit. Die anderen
        beschrieben damit den Backtest und nannten es die
        Entscheidungsqualitaet des Bots.
        """
        import inspect

        from alpaca_bot.journal import Journal

        sig = inspect.signature(Journal.decision_quality)
        assert sig.parameters["script"].default == "live_trade"

    def test_alles_bleibt_erreichbar(self):
        """`script=None` muss weiterhin die Gesamtsicht liefern."""
        import inspect

        from alpaca_bot.journal import Journal

        quelle = inspect.getsource(Journal.decision_quality)
        assert "if script:" in quelle
