"""Der Intraday-Stop protokolliert seinen Auswertungskontext (25.08.2026).

**Der Fund.** `18_health_check.py` meldete am 25.08.2026 ROT: 19 von 20
der juengsten `sell`-Entscheidungen trugen kein `regime_markt`, keinen
`sektor` und kein `liq_dezil`. Ursache waren zwei Dinge, die sich
ueberlagerten:

  * Altbestand. Bis Commit `dd16334` (22.08.2026) hing der Kontextblock
    nur an der Kaufschleife; `sell` und `topup` bekamen nichts. Das ist
    seitdem behoben, aber die alten Zeilen bleiben natuerlich leer.
  * **Ein echter, weiterhin offener Pfad:** `live.pruefe_stops_intraday`
    baut gar keinen `MarketSnapshot` und rief deshalb `_mit_kontext` nie
    auf. Der Intraday-Stop schrieb seine Verkaeufe blind.

Der zweite Punkt ist derselbe Mechanismus wie §G21 (dort fehlte
demselben Pfad der Lebenslauf) und §G13 Fund 3 (dort fehlte `topup` der
Kontext): Eine Verbesserung wird an der Hauptstrasse eingebaut und im
Sonderpfad vergessen.

**Warum das mehr als Kosmetik ist.** Der Intraday-Stop feuert per
Konstruktion im Einbruch. Ohne `regime_markt` fehlen der Auswertung
ausgerechnet die Verlusttrades der schlechten Marktphasen - also die
Zeilen, die die Frage "in welcher Marktlage traegt die Strategie?"
ueberhaupt erst beantworten koennten.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pandas as pd
import pytest

from alpaca_bot import live
from alpaca_bot.journal import Journal
from alpaca_bot.live import Referenzpreis


def _stop_ausloesen(tmp_path, monkeypatch, *, markt_reihe=None, sektor="Tech"):
    """Loest einen Intraday-Stop aus und gibt das Journal zurueck."""
    gehalten = {"A": {"stop_price": 95.0, "entry_price": 100.0,
                      "entry_date": "2026-08-17", "target_price": 110.0,
                      "entry_score": 0.8, "reasons": "{}"}}

    class S:
        def load_positions(self): return gehalten
        def record_exit(self, sym, **k): pass
        def drop_position(self, *a, **k): pass

    class Res:
        id, status = "o1", "filled"

    journal = Journal(tmp_path / "j.sqlite")
    pos = pd.DataFrame({"qty": [10.0], "avg_entry": [100.0]}, index=["A"])

    monkeypatch.setattr(live, "_markt_reihe_fuer_regime",
                        lambda *a, **k: markt_reihe)
    monkeypatch.setattr(live, "_symbolkontext",
                        lambda syms, **k: {s: {"sektor": sektor, "liq_dezil": 3}
                                           for s in syms})

    with patch.object(live.account, "positions", return_value=pos), \
         patch("alpaca_bot.state.Store", S), \
         patch.object(live, "Journal", lambda *a, **k: journal), \
         patch.object(live.trading, "close_position", return_value=Res()), \
         patch.object(live, "_reference_price",
                      side_effect=lambda s, side, fallback:
                      Referenzpreis(90.0, "quote")):
        live.pruefe_stops_intraday(dry_run=True, verbose=False)

    with journal._conn() as c:
        df = pd.read_sql_query(
            "SELECT symbol, action, reasons FROM decisions WHERE action='sell'", c)
    assert len(df) == 1, "Der Stop haette genau eine Entscheidung schreiben muessen"
    return json.loads(df.iloc[0]["reasons"])


def _markt(ueber_sma: bool = True) -> pd.Series:
    """SPY-Reihe, die klar ueber bzw. unter ihrem 200-Tage-Schnitt liegt."""
    idx = pd.bdate_range("2024-01-01", periods=300)
    if ueber_sma:
        werte = list(range(100, 100 + len(idx)))          # steigend
    else:
        werte = list(range(100 + len(idx), 100, -1))[:len(idx)]   # fallend
    return pd.Series([float(w) for w in werte], index=idx)


class TestIntradayStopSchreibtKontext:
    def test_sektor_und_liquiditaetsdezil_stehen_in_der_begruendung(
            self, tmp_path, monkeypatch):
        gruende = _stop_ausloesen(tmp_path, monkeypatch, markt_reihe=_markt())

        assert gruende["sektor"] == "Tech", (
            "Ohne `sektor` ist eine Auswertung der Sektorkonzentration bei "
            "Stop-Verkaeufen unmoeglich (§G13 Fund 3)."
        )
        assert gruende["liq_dezil"] == 3

    def test_marktregime_steht_in_der_begruendung(self, tmp_path, monkeypatch):
        gruende = _stop_ausloesen(tmp_path, monkeypatch, markt_reihe=_markt(True))
        assert gruende["regime_markt"] == "bullisch"
        assert "regime_vola" in gruende

    def test_baerisches_regime_wird_als_solches_erkannt(self, tmp_path, monkeypatch):
        gruende = _stop_ausloesen(tmp_path, monkeypatch,
                                  markt_reihe=_markt(ueber_sma=False))
        assert gruende["regime_markt"] == "baerisch"

    def test_der_eigentliche_ausstiegsgrund_bleibt_erhalten(
            self, tmp_path, monkeypatch):
        """Der Kontext darf die fachlichen Felder nicht ueberschreiben."""
        gruende = _stop_ausloesen(tmp_path, monkeypatch, markt_reihe=_markt())
        assert gruende["ausstiegsgrund"] == "stop_intraday"
        assert gruende["stop"] == pytest.approx(95.0)
        assert gruende["kurs_jetzt"] == pytest.approx(90.0)
        assert gruende["referenz_quelle"] == "quote"


class TestKontextAusfallStopptDenHandelNicht:
    """Ein fehlendes Protokollfeld darf NIE einen Stop-Verkauf verhindern.

    Das ist die Gegenrichtung zur Reparatur: Wer Kontext ergaenzt, baut
    zwei neue Fehlerquellen (Marktabruf, Sektor-Nachschlag) in einen
    Pfad ein, dessen einzige Aufgabe eine Notbremse ist.
    """

    def test_ohne_marktreihe_wird_trotzdem_verkauft(self, tmp_path, monkeypatch):
        gruende = _stop_ausloesen(tmp_path, monkeypatch, markt_reihe=None)
        assert gruende["ausstiegsgrund"] == "stop_intraday"
        # Kein Regime, aber der Verkauf steht.
        assert "regime_markt" not in gruende

    def test_werfender_kontextabruf_verhindert_den_verkauf_nicht(
            self, tmp_path, monkeypatch):
        def _explodiert(*a, **k):
            raise RuntimeError("Sektor-Nachschlag kaputt")

        # `_symbolkontext` faengt selbst ab; hier wird geprueft, dass die
        # ECHTE Funktion das auch tut und nicht nur der Testdouble.
        monkeypatch.setattr("alpaca_bot.universe.sektoren", _explodiert)
        assert live._symbolkontext(["A"], verbose=False) == {}

    def test_regime_aus_kaputter_reihe_wirft_nicht(self):
        assert live._regime_aus_markt(None, verbose=False) == {}

    def test_leere_reihe_erfindet_kein_volatilitaetsband(self):
        """**Gefunden von genau diesem Test am 25.08.2026.**

        Bei leerer Reihe ist die Volatilitaet NaN. `NaN < 0.15` und
        `NaN > 0.30` sind BEIDE False - der Wert fiel deshalb still auf
        `"normal"` durch. Eine erfundene Angabe, die in der Auswertung
        wie eine Messung aussieht: dieselbe Fehlerrichtung wie die
        "erfundene Null" aus §G10, die fuer B04 ein "DURCHGEFALLEN"
        meldete, wo gar nichts messbar war.
        """
        regime = live._regime_aus_markt(pd.Series(dtype=float), verbose=False)
        assert regime.get("regime_vola") == "unbekannt", (
            "Ohne Daten muss 'unbekannt' stehen, nicht 'normal'."
        )
        assert regime.get("regime_markt") == "unbekannt"


def test_kurze_marktreihe_meldet_unbekannt_statt_zu_raten():
    """Unter 200 Bars laesst sich 'ueber SMA200' nicht bestimmen.

    Wichtig, dass hier `unbekannt` steht und nicht `baerisch`: Eine
    erfundene Null sieht wie ein Messergebnis aus - genau der Fehler aus
    §G10 ('eine erfundene Null').
    """
    kurz = pd.Series([100.0] * 50, index=pd.bdate_range("2026-01-01", periods=50))
    regime = live._regime_aus_markt(kurz, verbose=False)
    assert regime["regime_markt"] == "unbekannt"
