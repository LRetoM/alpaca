"""Protokoll, Lebenslauf, Kapitalfluesse - die Lernschicht.

**Warum diese Tests so zahlreich sind:** Die meisten Fehler dieses
Projekts waren Protokoll- und Auswertungsfehler, keine Handelsfehler
(BEFUNDE §G). Der Bot handelte korrekt, aber die Messung log. Das ist
gefaehrlicher als ein Absturz - ein Absturz meldet sich.
"""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
import pytest


# ------------------------------------------------------------------ Journal
class TestJournalVersion:
    """REGRESSION: `code_version` war vom 30.07. bis 15.08.2026 kaputt.
    `shadow.code_version()` suchte git in `DATA_DIR.parent` - nach dem
    Umzug der Datenbanken zeigte das auf ein Verzeichnis ohne Git.
    8.278 von 12.516 Vorhersagen (66 %) ohne Zuordnung, ohne jede
    Fehlermeldung."""

    def test_lauf_bekommt_version(self, temp_journal):
        with temp_journal.run("test", config={}) as r:
            r.log("probe")
        runs = temp_journal.table("runs")
        assert runs["code_version"].notna().all()
        assert runs.iloc[0]["code_version"] != "unbekannt"

    def test_version_findet_git_im_projekt(self):
        from alpaca_bot.config import code_version

        v = code_version()
        assert v != "unbekannt", "git-Bezug muss auf PROJECT_ROOT zeigen"

    def test_beide_pfade_melden_dasselbe(self):
        """Live und Schatten muessen dieselbe Version melden, sonst sind
        ihre Daten nicht vergleichbar."""
        from alpaca_bot.config import code_version as live
        from alpaca_bot.shadow import code_version as schatten

        assert live() == schatten()


class TestJournalOrders:
    def test_dry_run_orders_ueberschreiben_sich_nicht(self, temp_journal):
        """REGRESSION: `OrderResult.id` ist im Trockenlauf immer der feste
        String 'dry-run'. Da `order_id` PRIMARY KEY ist und mit INSERT OR
        REPLACE geschrieben wird, ueberschrieb jede weitere Dry-Run-Order
        die vorherige - nur die letzte ueberlebte."""
        with temp_journal.run("test") as r:
            for sym in ("A", "B", "C"):
                did = r.decision(sym, "buy", reasons={}, price=1.0)
                r.order(did, symbol=sym, side="buy", status="ok",
                        order_id=None, dry_run=True)
        assert len(temp_journal.table("orders")) == 3

    def test_referenz_quelle_wird_gespeichert(self, temp_journal):
        with temp_journal.run("test") as r:
            did = r.decision("X", "buy", reasons={}, price=1.0)
            r.order(did, symbol="X", side="buy", status="ok",
                    dry_run=False, order_id="echt1",
                    expected_price=10.0, referenz_quelle="quote")
        o = temp_journal.table("orders")
        assert o.iloc[0]["referenz_quelle"] == "quote"

    def test_entscheidung_bleibt_mit_order_verknuepft(self, temp_journal):
        with temp_journal.run("test") as r:
            did = r.decision("X", "buy", reasons={"grund": "test"}, price=1.0)
            r.order(did, symbol="X", side="buy", status="ok", dry_run=False,
                    order_id="e1")
        o = temp_journal.table("orders")
        d = temp_journal.table("decisions")
        assert o.iloc[0]["decision_id"] == d.iloc[0]["decision_id"]


class TestSlippageBereinigung:
    """REGRESSION: Der unbereinigte Mittelwert (-20 bps) sah harmlos aus,
    weil drei kaputte Legacy-Zeilen (+2400 bps) den echten, negativen Rest
    verdeckten. Bereinigt: -258,7 bps."""

    def _order(self, j, order_id, status, fill, expected, quelle=None):
        with j.run("t") as r:
            did = r.decision("X", "sell", reasons={}, price=fill)
            r.order(did, symbol="X", side="sell", status=status,
                    order_id=order_id, dry_run=False, fill_price=fill,
                    expected_price=expected, referenz_quelle=quelle)

    def test_legacy_zeilen_ausgeschlossen(self, temp_journal):
        # Status-Text "X geschlossen" = vor dem close_position()-Fix
        self._order(temp_journal, "alt", "AMKR geschlossen", 45.0, 60.0)
        self._order(temp_journal, "neu", "filled", 100.0, 100.5, "quote")
        rep = temp_journal.slippage_report()
        assert rep["n"].sum() == 1, "Legacy-Zeile muss ausgeschlossen sein"

    def test_fallback_zeilen_ausgeschlossen(self, temp_journal):
        self._order(temp_journal, "fb", "filled", 45.0, 60.0, "fallback")
        self._order(temp_journal, "ok", "filled", 100.0, 100.5, "quote")
        assert temp_journal.slippage_report()["n"].sum() == 1

    def test_unbereinigt_zeigt_alles(self, temp_journal):
        self._order(temp_journal, "alt", "AMKR geschlossen", 45.0, 60.0)
        self._order(temp_journal, "neu", "filled", 100.0, 100.5, "quote")
        assert temp_journal.slippage_report(nur_bereinigt=False)["n"].sum() == 2


# ---------------------------------------------------------------- Lifecycle
class TestLifecycle:
    def test_pending_erfasst_after_10d(self, temp_lifecycle):
        """REGRESSION: `pending_analysis` fragte nur `after_5d IS NULL`.
        Sobald der 5-Tage-Wert gefuellt war, verliess der Trade die
        Warteschlange - `after_10d` wurde NIE nachgetragen. 36 von 36
        Trades betroffen."""
        temp_lifecycle.record({
            "trade_id": "t1", "symbol": "X", "entry_date": "2026-01-01",
            "entry_price": 100.0, "exit_date": "2026-01-08",
            "after_1d": 0.01, "after_5d": 0.02, "after_10d": None,
        })
        assert "t1" in temp_lifecycle.pending_analysis()

    def test_vollstaendiger_trade_nicht_mehr_pending(self, temp_lifecycle):
        temp_lifecycle.record({
            "trade_id": "t2", "symbol": "X", "entry_date": "2026-01-01",
            "entry_price": 100.0, "exit_date": "2026-01-08",
            "after_1d": 0.01, "after_5d": 0.02, "after_10d": 0.03,
        })
        assert "t2" not in temp_lifecycle.pending_analysis()

    def test_score_vorzeichen_wird_geprueft(self):
        """REGRESSION: `analyse()` meldete 'Score sortiert in die richtige
        Richtung' auch bei NEGATIVER Korrelation - nur der Betrag wurde
        geprueft. Gemessen wurde -0,133 und trotzdem gelobt."""
        from alpaca_bot.lifecycle import analyse

        # Konstruiert: hoher Score -> schlechtes Ergebnis
        n = 30
        df = pd.DataFrame({
            "exit_date": ["2026-01-01"] * n,
            "exit_reason": ["zeitausstieg"] * n,
            "return_pct": np.linspace(0.10, -0.10, n),
            "entry_score": np.linspace(0.1, 0.9, n),
            "mae_pct": [-0.02] * n, "mfe_pct": [0.05] * n,
            "after_5d": [0.0] * n,
        })
        texte = [i.vorschlag for i in analyse(df)
                 if i.thema == "Aussagekraft des Scores"]
        assert texte, "Score-Befund muss erzeugt werden"
        assert "ACHTUNG" in texte[0] and "NEGATIV" in texte[0]

    def test_bars_held_wird_aus_daten_gerechnet(self):
        """REGRESSION: `bars_held` war in JEDEM Lebenslauf 0.
        `position_meta.bars_held` wird beim Anlegen auf 0 gesetzt und nie
        erhoeht; `_record_lifecycle` uebernahm die 0 blind."""
        from alpaca_bot.daemon import _handelstage

        # Mo 05.01.2026 bis Fr 09.01.2026 = 4 Handelstage
        assert _handelstage("2026-01-05", pd.Timestamp("2026-01-09", tz="UTC")) == 4

    def test_handelstage_zaehlen_kein_wochenende(self):
        """Fr -> Mo sind drei Kalendertage, aber nur EIN Handelstag.
        Zwei Zaehlweisen im selben System machen jede Auswertung nach
        Haltedauer unvergleichbar."""
        from alpaca_bot.daemon import _handelstage

        assert _handelstage("2026-01-09", pd.Timestamp("2026-01-12", tz="UTC")) == 1


# --------------------------------------------------------------- Kapital
class TestKapitalfluesse:
    def test_derselbe_fluss_nur_einmal(self, temp_store):
        """Ohne diese Zusicherung wuerde jede Wiederholung des Abgleichs
        den Hoechststand des Drawdown-Zaehlers weiter verschieben."""
        ts = pd.Timestamp.now(tz="UTC")
        assert temp_store.fluss_buchen("a1", ts, "CSD", 1000.) is True
        assert temp_store.fluss_buchen("a1", ts, "CSD", 1000.) is False
        assert temp_store.einzahlungen_summe() == pytest.approx(1000.)

    def test_vorzeichen_vereinheitlicht(self):
        """Alpaca liefert `net_amount` je nach Typ unterschiedlich
        signiert. Wer das nicht vereinheitlicht, addiert Auszahlungen zur
        Einzahlungssumme."""
        from alpaca_bot.kapital import _betrag

        assert _betrag({"net_amount": "500"}, "CSD") == 500.0
        assert _betrag({"net_amount": "-500"}, "CSD") == 500.0
        assert _betrag({"net_amount": "500"}, "CSW") == -500.0
        assert _betrag({"net_amount": "-500"}, "CSW") == -500.0

    def test_nur_csd_und_csw_gelten_als_fluss(self):
        """Dividenden und Zinsen sind echter Ertrag - wer sie
        herausrechnet, macht das System schlechter, als es ist."""
        from alpaca_bot.kapital import FLUSS_TYPEN

        assert set(FLUSS_TYPEN) == {"CSD", "CSW"}

    def test_twr_ignoriert_einzahlung(self, temp_store):
        """Naiv sieht eine Einzahlung wie Gewinn aus. Nur die
        zeitgewichtete Rendite ist mit Buy & Hold vergleichbar."""
        from alpaca_bot import kapital

        def punkt(eq, einzahlungen=0.0):
            temp_store.kapital_punkt(equity=eq, cash=eq * 0.1, exposure=0.9,
                                     n_positionen=5, hoechststand=eq,
                                     drawdown_pct=0.0,
                                     einzahlungen=einzahlungen)

        punkt(100_000.)
        import time
        time.sleep(0.01)
        temp_store.fluss_buchen("d1", pd.Timestamp.now(tz="UTC"), "CSD", 50_000.)
        punkt(150_000., 50_000.)

        r = kapital.zeitgewichtete_rendite(temp_store)
        assert r["naiv"] == pytest.approx(0.50, abs=0.01), "naiv sieht +50 %"
        assert r["twr"] == pytest.approx(0.0, abs=0.01), "echt: keine Leistung"
