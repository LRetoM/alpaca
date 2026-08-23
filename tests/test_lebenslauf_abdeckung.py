"""Jeder Ausstiegsgrund landet im Lebenslauf - auch der Intraday-Stop (§G21).

**Der Fund vom 23.08.2026.** `daemon._record_lifecycle` haengt am
normalen `sell`-Pfad. Der am 15.08.2026 ergaenzte Intraday-Stop
(`live.pruefe_stops_intraday`) schreibt seinen Ausstieg direkt ueber
`state.record_exit` und ging daran vorbei. Abdeckung des Lebenslaufs je
Ausstiegsgrund, gemessen am Produktivbestand:

    zeitausstieg              39/39   100 %
    these_traegt_nicht_mehr   11/11   100 %
    gewinnziel_erreicht        4/4    100 %
    stop_ausgeloest            2/2    100 %
    stop_intraday              0/2      0 %   <- fehlte vollstaendig

**Die Richtung wiegt schwerer als die Groesse.** Der Intraday-Stop feuert
per Konstruktion bei scharfen Einbruechen - er trifft fast nur
Verlusttrades. Die beiden fehlenden lagen bei -8,9 % und -7,8 %, die 56
erfassten im Mittel bei +3,34 %. Der Lernbericht war dadurch systematisch
zu gut (+3,34 % statt +2,94 %) und nannte `stop_ausgeloest` (-5,5 %) den
schlechtesten Ausstiegsgrund, obwohl `stop_intraday` (-8,3 %) schlechter
war und gar nicht erst auftauchte.

Dass es nur 0,4 Prozentpunkte waren, lag allein an n=2. Der Fehler waechst
mit jedem Intraday-Stop und immer in dieselbe Richtung.

**Warum der alte Waechter ihn nicht fand:** Er verglich nur
`len(exits) > len(trades) + 1`. Zwei fehlende von 58 sehen nach
Zeitversatz aus. Die Wahrheit stand in der Aufschluesselung je Grund -
eine Gesamtzahl kann einen ausgefallenen Schreibpfad nicht zeigen.
"""

from __future__ import annotations

import pandas as pd
import pytest

from alpaca_bot import data_integrity as di
from alpaca_bot.lifecycle import Lifecycle, eintrag_anlegen, handelstage


@pytest.fixture
def lauf(tmp_path):
    return Lifecycle(tmp_path / "lifecycle.sqlite")


META = {"entry_date": "2026-08-17", "entry_price": 100.0,
        "stop_price": 94.0, "target_price": 110.0, "entry_score": 0.87,
        "reasons": {"rsi2": True}}


class TestGemeinsameEintragsfunktion:
    """Ein Ort fuer alle Ausstiege - sonst driftet der naechste Pfad wieder."""

    def test_legt_eintrag_an(self, lauf):
        eintrag_anlegen(symbol="AVGO", meta=META, exit_price=360.0,
                        exit_reason="stop_intraday", return_pct=-0.089,
                        exit_ts=pd.Timestamp("2026-08-19", tz="UTC"),
                        bars_held=2, store=lauf)
        t = lauf.table()
        assert len(t) == 1
        z = t.iloc[0]
        assert z["symbol"] == "AVGO"
        assert z["exit_reason"] == "stop_intraday"
        assert z["return_pct"] == pytest.approx(-0.089)

    def test_uebernimmt_die_einstiegsdaten(self, lauf):
        """Ohne Stop, Ziel und Score ist der Trade spaeter nicht deutbar."""
        eintrag_anlegen(symbol="SIG", meta=META, exit_price=79.6,
                        exit_reason="stop_intraday", return_pct=-0.078,
                        exit_ts=pd.Timestamp("2026-08-20", tz="UTC"),
                        bars_held=3, store=lauf)
        z = lauf.table().iloc[0]
        assert z["entry_price"] == pytest.approx(100.0)
        assert z["planned_stop"] == pytest.approx(94.0)
        assert z["planned_target"] == pytest.approx(110.0)
        assert z["entry_score"] == pytest.approx(0.87)

    def test_nachlauf_bleibt_leer(self, lauf):
        """MAE/MFE/Nachlauf existieren zum Ausstiegszeitpunkt noch nicht."""
        eintrag_anlegen(symbol="X", meta=META, exit_price=99.0,
                        exit_reason="stop_intraday", return_pct=-0.01,
                        bars_held=1, store=lauf)
        z = lauf.table().iloc[0]
        for feld in ("mae_pct", "mfe_pct", "after_1d", "after_5d", "after_10d"):
            assert pd.isna(z[feld])

    def test_ohne_einstand_wird_nichts_erfunden(self, lauf):
        """Lieber gar kein Eintrag als ein erfundener (§G13 Fund 2).

        Die Aufrufer fangen das ab und melden es - ein Ausfall hier darf
        den Verkauf nicht rueckgaengig machen.
        """
        import sqlite3

        with pytest.raises(sqlite3.IntegrityError):
            eintrag_anlegen(symbol="X", meta={}, exit_price=9.0,
                            exit_reason="stop_intraday", return_pct=-0.05,
                            bars_held=1, store=lauf)


class TestHandelstage:
    """Die Rechnung ist nach `lifecycle` gewandert - beide Pfade teilen sie."""

    def test_freitag_bis_montag_ist_ein_handelstag(self):
        assert handelstage(pd.Timestamp("2026-08-21", tz="UTC"),
                           pd.Timestamp("2026-08-24", tz="UTC")) == 1

    def test_ohne_eingangsdatum_kein_wert(self):
        """`None` ist ehrlich - eine 0 saehe wie eine Messung aus."""
        assert handelstage(None, pd.Timestamp("2026-08-24", tz="UTC")) is None

    def test_daemon_nutzt_dieselbe_funktion(self):
        from alpaca_bot.daemon import _handelstage

        assert _handelstage is handelstage


class TestIntradayStopSchreibtDenLebenslauf:
    """Der Pfad, der die Luecke gerissen hat - jetzt am echten Aufruf geprueft.

    `test_ausfuehrung.TestIntradayStop` fuhr bisher immer mit
    `dry_run=True`; der Lebenslauf entsteht aber im Zweig
    `if not dry_run`. Genau deshalb blieb die Luecke unbemerkt: Es gab
    Tests des Intraday-Stops, nur keinen, der bis zum Schreiben kam.
    """

    def _stop_ausloesen(self, tmp_path, monkeypatch):
        from unittest.mock import patch

        from alpaca_bot import live
        from alpaca_bot.journal import Journal
        from alpaca_bot.live import Referenzpreis

        lc = Lifecycle(tmp_path / "lifecycle.sqlite")
        monkeypatch.setattr("alpaca_bot.lifecycle.Lifecycle",
                            lambda *a, **k: lc)

        gehalten = {"A": {"stop_price": 95.0, "entry_price": 100.0,
                          "entry_date": "2026-08-17", "target_price": 110.0,
                          "entry_score": 0.8, "reasons": '{"rsi2": true}'}}
        geschrieben = {}

        class S:
            def load_positions(self): return gehalten
            def record_exit(self, sym, **k): geschrieben[sym] = k
            def drop_position(self, *a, **k): pass

        class Res:
            id, status = "o1", "filled"

        pos = pd.DataFrame({"qty": [10.0], "avg_entry": [100.0]}, index=["A"])
        with patch.object(live.account, "positions", return_value=pos), \
             patch("alpaca_bot.state.Store", S), \
             patch.object(live, "Journal",
                          lambda *a, **k: Journal(tmp_path / "j.sqlite")), \
             patch.object(live.trading, "close_position", return_value=Res()), \
             patch.object(live, "_reference_price",
                          side_effect=lambda s, side, fallback:
                          Referenzpreis(90.0, "quote")):
            verkauft = live.pruefe_stops_intraday(dry_run=False, verbose=False)
        return verkauft, lc, geschrieben

    def test_ausstieg_landet_im_lebenslauf(self, tmp_path, monkeypatch):
        verkauft, lc, _ = self._stop_ausloesen(tmp_path, monkeypatch)
        assert verkauft == ["A"]
        t = lc.table()
        assert len(t) == 1, (
            "Der Intraday-Stop muss einen Lebenslauf-Eintrag anlegen. Bis "
            "zum 23.08.2026 tat er es nicht - und weil er bei Einbruechen "
            "feuert, fehlten dem Lernbericht die Verlusttrades (§G21)."
        )
        z = t.iloc[0]
        assert z["symbol"] == "A"
        assert z["exit_reason"] == "stop_intraday"
        assert z["entry_price"] == pytest.approx(100.0)
        assert z["return_pct"] < 0

    def test_zustand_und_lebenslauf_stimmen_ueberein(self, tmp_path, monkeypatch):
        """Beide Tabellen muessen dieselbe Haltedauer nennen.

        Vorher uebernahm `record_exit` `meta["bars_held"]` - den Wert, der
        beim Anlegen auf 0 gesetzt und nie erhoeht wird. Jetzt rechnen
        beide Seiten dieselbe Zahl aus `entry_date` (§G13 Fund 2).
        """
        _, lc, geschrieben = self._stop_ausloesen(tmp_path, monkeypatch)
        assert geschrieben["A"]["bars_held"] == lc.table().iloc[0]["bars_held"]
        assert geschrieben["A"]["bars_held"] is not None


class TestWaechterFindetAusgefallenenSchreibpfad:
    """Der Anteil JE GRUND zeigt, was eine Gesamtzahl verdeckt."""

    def _exits(self, zeilen):
        return pd.DataFrame([
            {"symbol": s, "exit_date": d, "exit_reason": g, "return_pct": r,
             "exit_price": 10.0, "entry_price": 11.0, "bars_held": 2}
            for s, d, g, r in zeilen
        ])

    def _pruefen(self, monkeypatch, exits, trades, tmp_path):
        lc = Lifecycle(tmp_path / "l.sqlite")
        for t in trades:
            eintrag_anlegen(symbol=t[0], meta=META, exit_price=10.0,
                            exit_reason=t[2], return_pct=t[3],
                            exit_ts=pd.Timestamp(t[1], tz="UTC"),
                            bars_held=2, store=lc)

        class _Store:
            def recent_exits(self, days=30):
                return exits

        monkeypatch.setattr("alpaca_bot.state.Store", lambda *a, **k: _Store())
        monkeypatch.setattr("alpaca_bot.lifecycle.Lifecycle",
                            lambda *a, **k: lc)
        r = di.IntegrityReport()
        di.check_lifecycle_coverage(r)
        return r

    def test_laufender_ausfall_ist_ein_fehler(self, monkeypatch, tmp_path):
        """Fehlender Eintrag NEUER als der juengste vorhandene = Pfad kaputt."""
        zeilen = [("A", "2026-08-10", "zeitausstieg", 0.02),
                  ("B", "2026-08-11", "zeitausstieg", 0.03),
                  ("AVGO", "2026-08-19", "stop_intraday", -0.089),
                  ("SIG", "2026-08-20", "stop_intraday", -0.078)]
        r = self._pruefen(monkeypatch, self._exits(zeilen), zeilen[:2], tmp_path)
        treffer = [f for f in r.findings if "stop_intraday" in f.check]
        assert treffer, (
            "Ein Ausstiegsgrund mit 0 % Abdeckung muss auffallen. Der alte "
            "Waechter verglich nur Gesamtzahlen - 2 von 58 sah nach "
            "Zeitversatz aus."
        )
        assert treffer[0].severity == "fehler"
        assert "-8" in treffer[0].detail, (
            "Die mittlere Rendite der fehlenden Trades gehoert in den "
            "Befund - sie zeigt, in welche Richtung der Bericht verzerrt."
        )

    def test_vollstaendige_abdeckung_bleibt_still(self, monkeypatch, tmp_path):
        zeilen = [("A", "2026-08-10", "zeitausstieg", 0.02),
                  ("AVGO", "2026-08-19", "stop_intraday", -0.089)]
        r = self._pruefen(monkeypatch, self._exits(zeilen), zeilen, tmp_path)
        assert not r.findings

    def test_altlast_ist_kein_fehler_sondern_eine_anmerkung(
            self, monkeypatch, tmp_path):
        """Sonst leuchtete der Health-Check dauerhaft ROT (§G18 Fund 4).

        Die zwei historischen Zeilen lassen sich nicht nachtragen -
        `position_meta` ist beim Verkauf geloescht. Und BETRIEBSPLAN §8
        macht aus zweimal ROT "Handel aus". Massgeblich ist deshalb, ob
        ein fehlender Eintrag NEUER ist als der juengste vorhandene:
        Dann hat der Lebenslauf seither geschrieben, nur fuer diesen
        Ausstieg nicht.
        """
        zeilen = [("AVGO", "2026-08-19", "stop_intraday", -0.089),
                  ("SIG", "2026-08-20", "stop_intraday", -0.078),
                  ("NEU", "2026-08-25", "zeitausstieg", 0.02)]
        r = self._pruefen(monkeypatch, self._exits(zeilen), zeilen[2:], tmp_path)
        assert not [f for f in r.findings if f.severity == "fehler"], (
            "Eine nicht nachtragbare Altlast darf den Health-Check nicht "
            "dauerhaft rot halten - die Warnung waere nicht abstellbar."
        )
        rest = [f for f in r.findings if f.severity == "auffaellig"]
        assert rest and "AVGO" in rest[0].detail and "SIG" in rest[0].detail
        assert "Altlast" in rest[0].check

    def test_neuer_ausfall_faellt_trotz_hoher_quote_auf(
            self, monkeypatch, tmp_path):
        """Nicht der Anteil entscheidet, sondern die Zeitfolge."""
        zeilen = [("A", "2026-08-10", "zeitausstieg", 0.02),
                  ("B", "2026-08-11", "zeitausstieg", 0.03),
                  ("C", "2026-08-12", "zeitausstieg", 0.01),
                  ("D", "2026-08-26", "zeitausstieg", -0.02)]
        r = self._pruefen(monkeypatch, self._exits(zeilen), zeilen[:3], tmp_path)
        assert [f for f in r.findings if f.severity == "fehler"], (
            "3 von 4 erfasst sind 75 % - aber der fehlende ist NEUER als "
            "der juengste vorhandene Eintrag. Das ist die Signatur eines "
            "gerade ausgefallenen Schreibpfads."
        )
