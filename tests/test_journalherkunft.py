"""Woher stammt eine Journalzeile - und misst sie ueberhaupt etwas? (§G19)

Vier Funde vom 23.08.2026, alle aus derselben Familie: Eine Zahl sieht
nach Messung aus und ist keine.

**Fund 1 - die Sicherung war zu 28,6 % Fremddaten.** `journal.RAW_DIR`
war ein Modul-Global. `Journal(tmp_path)` isolierte die SQLite sauber,
`RunLogger` schrieb die JSONL aber immer ins Produktivverzeichnis:

    JSONL-Dateien gesamt      2.618
      Lauf im Journal            472
      KEIN Lauf im Journal     2.146   <- 28,6 % aller Zeilen
      davon Symbol TEST           84

Und ueber genau diese Dateien sagt das Modul: *"waere die Datenbank je
beschaedigt, liesse sie sich daraus vollstaendig rekonstruieren."*

**Fund 4 - die Slippage-Bereinigung filterte auf einen Wert, den es
nicht gab.** `referenz_quelle == "fallback"` - die Spalte kam erst am
04.08.2026 dazu, aeltere Zeilen tragen NULL, und `NULL != "fallback"`.
31 der 162 Orders (19 %) blieben drin, darunter die Ausreisser, die §G
schon als Datenfehler fuehrt (KGS -1.648, SIMO -1.584 bps).

**Fund 5 - zwei stumme Spalten.** `raw` trug in 183 von 183 echten
Zeilen den String `'null'`, `status` in 178 von 183 `pending_new` - den
Wert bei Abgabe, nie den endgueltigen.

**Fund 8 - der Protokollkopf mischte Simulation und Live.**
"Entscheidungen: 18425 (183 ausgefuehrt)" las sich wie 1 %
Ausfuehrungsquote; 18.118 Zeilen stammten aus Simulationen (§G13).
"""

from __future__ import annotations

import json

import pytest

from alpaca_bot.journal import RAW_DIR, Journal


@pytest.fixture
def buch(tmp_path):
    return Journal(tmp_path / "journal.sqlite")


class TestSicherungBleibtBeiIhrerDatenbank:
    """Fund 1: Die JSONL liegt neben der DB, nicht an einem festen Ort."""

    def test_raw_dir_haengt_an_der_instanz(self, buch, tmp_path):
        assert buch.raw_dir == tmp_path / "journal_raw"
        assert buch.raw_dir != RAW_DIR

    def test_lauf_schreibt_in_das_eigene_verzeichnis(self, buch):
        with buch.run("test") as run:
            run.log("probe", "Zeile")
        dateien = list(buch.raw_dir.glob("*.jsonl"))
        assert len(dateien) == 1
        assert "probe" in dateien[0].read_text(encoding="utf-8")

    def test_produktivverzeichnis_bleibt_unberuehrt(self, buch):
        """Der eigentliche Fund: 2.146 Fremddateien entstanden genau so."""
        vorher = {p.name for p in RAW_DIR.glob("*")} if RAW_DIR.exists() else set()
        with buch.run("test") as run:
            run.decision(symbol="TEST", action="buy", conviction=0.9,
                         reasons={"grund": True})
        nachher = {p.name for p in RAW_DIR.glob("*")} if RAW_DIR.exists() else set()
        assert vorher == nachher, (
            "Ein Testlauf hat ins Produktivverzeichnis geschrieben. Genau so "
            "sind 2.146 Fremddateien entstanden, und die JSONL ist die "
            "Sicherung, aus der sich das Journal rekonstruieren lassen soll."
        )

    def test_snapshot_landet_ebenfalls_lokal(self, buch):
        import pandas as pd

        with buch.run("test") as run:
            pfad = run.snapshot("kennzahlen", pd.DataFrame({"a": [1, 2]}))
        assert pfad.parent == buch.raw_dir

    def test_zwei_journale_teilen_keine_sicherung(self, tmp_path):
        a = Journal(tmp_path / "a" / "journal.sqlite")
        b = Journal(tmp_path / "b" / "journal.sqlite")
        assert a.raw_dir != b.raw_dir
        with a.run("test") as run:
            run.log("nur_in_a")
        assert list(a.raw_dir.glob("*.jsonl"))
        assert not list(b.raw_dir.glob("*.jsonl"))


class TestSlippageNurMitVerifizierterReferenz:
    """Fund 4: Positivliste statt Ausschlussliste."""

    def _order(self, run, symbol, quelle, erwartet=100.0, fuell=101.0):
        did = run.decision(symbol=symbol, action="buy", conviction=0.9,
                           reasons={"x": True})
        run.order(did, symbol=symbol, side="buy", status="filled",
                  dry_run=False, expected_price=erwartet, fill_price=fuell,
                  referenz_quelle=quelle)

    def test_null_referenz_faellt_heraus(self, buch):
        """DER Fund: `NULL != 'fallback'`, also blieb sie drin."""
        with buch.run("live_trade") as run:
            self._order(run, "GUT", "quote")
            self._order(run, "ALT", None, erwartet=100.0, fuell=50.0)
        o = buch._slippage_basis(still=True)
        assert set(o["symbol"]) == {"GUT"}, (
            "Eine Zeile ohne `referenz_quelle` stammt aus der Zeit vor dem "
            "04.08.2026. Was ihr `expected_price` bedeutet, ist nicht mehr "
            "feststellbar - sie ist keine Messung."
        )

    def test_fallback_faellt_heraus(self, buch):
        with buch.run("live_trade") as run:
            self._order(run, "GUT", "quote")
            self._order(run, "FALL", "fallback")
        assert set(buch._slippage_basis(still=True)["symbol"]) == {"GUT"}

    def test_quote_verworfen_zaehlt_mit(self, buch):
        """Der letzte echte Trade IST eine Marktbeobachtung."""
        with buch.run("live_trade") as run:
            self._order(run, "A", "quote")
            self._order(run, "B", "quote_verworfen")
        assert set(buch._slippage_basis(still=True)["symbol"]) == {"A", "B"}

    def test_unbekannte_neue_quelle_faellt_heraus(self, buch):
        """Der Grund fuer die Positivliste: Neues rutscht nicht durch."""
        with buch.run("live_trade") as run:
            self._order(run, "GUT", "quote")
            self._order(run, "NEU", "irgendwas_neues")
        assert set(buch._slippage_basis(still=True)["symbol"]) == {"GUT"}

    def test_legacy_zeilen_fallen_weiter_heraus(self, buch):
        with buch.run("live_trade") as run:
            self._order(run, "GUT", "quote")
            did = run.decision(symbol="AMKR", action="sell", conviction=0.1,
                               reasons={"x": True})
            run.order(did, symbol="AMKR", side="sell",
                      status="AMKR geschlossen", dry_run=False,
                      expected_price=60.74, fill_price=45.59,
                      referenz_quelle="quote")
        assert set(buch._slippage_basis(still=True)["symbol"]) == {"GUT"}

    def test_ohne_bereinigung_bleibt_alles(self, buch):
        """`nur_bereinigt=False` muss die Nachvollziehbarkeit erhalten."""
        with buch.run("live_trade") as run:
            self._order(run, "GUT", "quote")
            self._order(run, "ALT", None)
        assert len(buch._slippage_basis(nur_bereinigt=False, still=True)) == 2


class TestOrderspaltenTragenInformation:
    """Fund 5: 'gefuellt' ist nicht dasselbe wie 'aussagekraeftig'."""

    def test_raw_ohne_uebergabe_ist_sql_null(self, buch):
        """Nicht der String 'null' - der sieht wie Inhalt aus (§G13 Fund 2)."""
        with buch.run("live_trade") as run:
            did = run.decision(symbol="X", action="buy", conviction=0.9,
                               reasons={"x": True})
            run.order(did, symbol="X", side="buy", status="filled",
                      dry_run=False, fill_price=10.0)
        o = buch.table("orders")
        assert o["raw"].isna().all(), (
            "`raw` muss SQL-NULL bleiben, wenn nichts uebergeben wurde. "
            "Der Text 'null' laesst eine Spalte zu 100 % gefuellt aussehen, "
            "die nichts enthaelt."
        )

    def test_raw_mit_uebergabe_wird_gespeichert(self, buch):
        with buch.run("live_trade") as run:
            did = run.decision(symbol="X", action="buy", conviction=0.9,
                               reasons={"x": True})
            run.order(did, symbol="X", side="buy", status="filled",
                      dry_run=False, fill_price=10.0,
                      raw={"filled_qty": 3, "status": "filled"})
        gespeichert = json.loads(buch.table("orders")["raw"].iloc[0])
        assert gespeichert["filled_qty"] == 3

    def test_waechter_meldet_konstante_spalte(self, buch):
        """Der Waechter, den es fuer `orders` bisher nicht gab."""
        from alpaca_bot import data_integrity as di

        with buch.run("live_trade") as run:
            for i in range(30):
                did = run.decision(symbol=f"S{i}", action="buy", conviction=0.9,
                                   reasons={"x": True})
                run.order(did, symbol=f"S{i}", side="buy",
                          status="pending_new", dry_run=False,
                          expected_price=100.0, fill_price=100.0,
                          referenz_quelle="quote")
        report = di.IntegrityReport()
        di.check_stumme_orderspalten(buch, report)
        treffer = [f for f in report.findings if "status" in f.check]
        assert treffer, (
            "Eine Spalte, die in 30 von 30 Orders 'pending_new' zeigt, "
            "traegt keine Information - genau der Zustand bis 23.08.2026."
        )

    def test_waechter_schweigt_bei_echter_variation(self, buch):
        from alpaca_bot import data_integrity as di

        with buch.run("live_trade") as run:
            for i in range(30):
                did = run.decision(symbol=f"S{i}", action="buy", conviction=0.9,
                                   reasons={"x": True})
                run.order(did, symbol=f"S{i}", side="buy",
                          status="filled" if i % 2 else "canceled",
                          dry_run=False, expected_price=100.0,
                          fill_price=100.0, referenz_quelle="quote",
                          raw={"status": "filled"})
        report = di.IntegrityReport()
        di.check_stumme_orderspalten(buch, report)
        assert not [f for f in report.findings if "status" in f.check]


class TestProtokollkopfTrenntQuellen:
    """Fund 8: Live und Simulation in einer Zeile ist keine Kennzahl."""

    def test_live_und_simulation_getrennt(self, buch):
        with buch.run("live_trade") as run:
            run.decision(symbol="A", action="buy", conviction=0.9,
                         reasons={"x": True})
        with buch.run("simulate") as run:
            for i in range(50):
                run.decision(symbol=f"S{i}", action="buy", conviction=0.9,
                             reasons={"x": True})
        text = buch.summary()
        assert "1  LIVE" in text
        assert "50" in text and "aus Simulation" in text, (
            "18.425 Entscheidungen mit 183 Ausfuehrungen sah nach 1 % "
            "Ausfuehrungsquote aus. 18.118 davon waren Simulationszeilen."
        )

    def test_entscheidungszeitraum_wird_ausgewiesen(self, buch):
        """Rueckdatierte Simulationszeilen duerfen sich nicht verstecken."""
        import datetime as dt
        import sqlite3

        with buch.run("live_trade") as run:
            run.decision(symbol="A", action="buy", conviction=0.9,
                         reasons={"x": True})
        with buch.run("simulate") as run:
            did = run.decision(symbol="B", action="buy", conviction=0.9,
                               reasons={"x": True})
        with sqlite3.connect(buch.path) as c:
            c.execute("UPDATE decisions SET ts=? WHERE decision_id=?",
                      (dt.datetime(2021, 7, 8, tzinfo=dt.UTC).isoformat(), did))
        text = buch.summary()
        assert "2021-07-08" in text, (
            "Der Laufzeitraum verschweigt, dass Entscheidungen bis 2021 "
            "zurueckreichen - das Protokoll sah drei Wochen alt aus."
        )
