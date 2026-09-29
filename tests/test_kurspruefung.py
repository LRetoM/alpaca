"""Kein falscher Brokerkurs kommt in den Zustand des Bots (§G29).

**Der Fund vom 24.08.2026.** Alpaca markiert eine Position mit
`lastday_price x (1 + change_today)`. Fuer DKS lieferte `change_today`
-17,01 %, obwohl der Wert an diesem Tag zwischen 175,87 und 185,21 lief -
der Kurs 148,82 kam in **219 Minutenbars kein einziges Mal** vor.
Ursache ist der IEX-Feed mit ~2 % Volumenabdeckung, derselbe Mechanismus
wie bei SIMO/KGS am 04.08.2026.

**Warum das gefaehrlich ist.** `build_portfolio` schrieb den Wert in
`high_water` - und das ist ein `max()`. Ein einmal zu HOCH gesetzter
Hoechststand kommt **nie wieder herunter** und verschiebt dauerhaft den
nachziehenden Stop und die Verlaengerungsregel von B11.

**Warum gegen `snapshots()['last']` geprueft wird und nicht gegen die
Tagesbar:** Die Bar traegt den Schlusskurs von GESTERN. Eine echte
Kursluecke (Zahlen, Uebernahme) waere davon nicht zu unterscheiden. Der
letzte Trade ist eine zeitgleiche Beobachtung - dieselbe Ueberlegung wie
in `_quote_plausibel`.
"""

from __future__ import annotations

from unittest.mock import patch

import pandas as pd
import pytest

from alpaca_bot import live
from alpaca_bot.live import _MAX_POSITIONSPREIS_ABWEICHUNG


def _positionen(current_price: float) -> pd.DataFrame:
    return pd.DataFrame(
        {"qty": [10.0], "avg_entry": [180.0], "current_price": [current_price],
         "market_value": [10 * current_price]}, index=["DKS"])


def _snap(last: float) -> pd.DataFrame:
    return pd.DataFrame({"last": [last]}, index=["DKS"])


def _bauen(current_price, last, tmp_path, monkeypatch, high_water=180.0):
    from alpaca_bot.engine import MarketSnapshot

    idx = pd.date_range("2026-08-01", periods=300, freq="B", tz="UTC")
    bars = pd.DataFrame({"open": 180.0, "high": 181.0, "low": 179.0,
                         "close": 180.0, "volume": 1e6}, index=idx)
    snapshot = MarketSnapshot(as_of=idx[-1], bars={"DKS": bars},
                              signals={}, market=None)

    class S:
        def load_positions(self):
            return {"DKS": {"entry_date": "2026-08-20T00:00:00+00:00",
                            "stop_price": 166.0, "target_price": 195.0,
                            "high_water": high_water}}

    with patch.object(live.account, "account_summary",
                      return_value={"cash": 1000.0, "portfolio_value": 100000.0,
                                    "daytrade_count": 0}), \
         patch.object(live.account, "positions",
                      return_value=_positionen(current_price)), \
         patch.object(live.data, "snapshots", return_value=_snap(last)), \
         patch("alpaca_bot.state.Store", S):
        return live.build_portfolio(snapshot)


class TestFalscherBrokerkursWirdVerworfen:

    def test_der_dks_fall(self, tmp_path, monkeypatch):
        """Broker 148,82 gegen letzten Trade 179,64 - der echte Fall."""
        p = _bauen(148.82, 179.64, tmp_path, monkeypatch)
        assert p.positions["DKS"].high_water == pytest.approx(180.0), (
            "Der falsche Kurs darf `high_water` nicht setzen. Er war hier "
            "zu NIEDRIG; waere er zu hoch, bliebe der Fehler dauerhaft - "
            "`high_water` ist ein max() und kommt nie zurueck."
        )

    def test_zu_hoher_kurs_verseucht_high_water_nicht(self, tmp_path, monkeypatch):
        """Die gefaehrliche Richtung: ein max() vergisst nicht."""
        p = _bauen(260.0, 180.0, tmp_path, monkeypatch)
        assert p.positions["DKS"].high_water == pytest.approx(180.0), (
            "Ein um 44 % zu hoher Kurs wuerde den Hoechststand dauerhaft "
            "verschieben und Stop wie Verlaengerungsregel verfaelschen."
        )

    def test_echte_bewegung_kommt_durch(self, tmp_path, monkeypatch):
        """Unter der Schwelle bleibt der Brokerkurs massgeblich."""
        p = _bauen(186.0, 184.0, tmp_path, monkeypatch)   # +1,1 %
        assert p.positions["DKS"].high_water == pytest.approx(186.0)

    def test_schwelle_laesst_kursluecken_durch(self):
        """5 % ist bewusst milder als die 2 % im Handelspfad."""
        assert _MAX_POSITIONSPREIS_ABWEICHUNG == pytest.approx(0.05), (
            "Zu streng wuerde eine echte Kursluecke nach Zahlen "
            "abschneiden - dann rechnete der Bot mit einem Kurs, den es "
            "nicht mehr gibt."
        )

    def test_ohne_gegenprobe_laeuft_es_weiter(self, tmp_path, monkeypatch):
        """Ein Ausfall des Kursabrufs darf den Handel nie stoppen."""
        from alpaca_bot.engine import MarketSnapshot

        idx = pd.date_range("2026-08-01", periods=300, freq="B", tz="UTC")
        bars = pd.DataFrame({"open": 180.0, "high": 181.0, "low": 179.0,
                             "close": 180.0, "volume": 1e6}, index=idx)
        snapshot = MarketSnapshot(as_of=idx[-1], bars={"DKS": bars},
                                  signals={}, market=None)

        class S:
            def load_positions(self):
                return {}

        with patch.object(live.account, "account_summary",
                          return_value={"cash": 1000.0,
                                        "portfolio_value": 100000.0,
                                        "daytrade_count": 0}), \
             patch.object(live.account, "positions",
                          return_value=_positionen(148.82)), \
             patch.object(live.data, "snapshots",
                          side_effect=RuntimeError("API weg")), \
             patch("alpaca_bot.state.Store", S):
            p = live.build_portfolio(snapshot)
        assert "DKS" in p.positions, (
            "Faellt die Gegenprobe aus, muss der Bot weiterlaufen - eine "
            "fehlende Pruefung darf keine Position verschwinden lassen."
        )
