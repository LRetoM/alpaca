"""handelskalender.py muss die Alpaca-API gedrosselt aufrufen (27.08.2026).

Beim Bau des Moduls (§G38) fehlte `RateLimiter("alpaca_trading").acquire()`
vor `trading_client().get_calendar(...)` - `09_selfcheck.py` (Regel "Jeder
API-Aufruf durch die Drossel") hat das beim naechsten Lauf sofort als
Verstoss gemeldet.

**Warum hier funktional getestet wird, nicht per Textsuche.** Ein Test,
der nur prueft, ob das WORT "RateLimiter" in der Datei vorkommt, faengt
genau diesen Fehler nicht: Der `import` bleibt stehen, auch wenn der
eigentliche `acquire()`-Aufruf verschwindet. Massgeblich ist, dass die
Drossel bei jedem Abruf tatsaechlich AUSGELOEST wird.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import alpaca_bot.handelskalender as hk


def test_abrufen_loest_die_drossel_tatsaechlich_aus(monkeypatch):
    """Der eigentliche Fix: `_abrufen()` ruft `RateLimiter.acquire()`
    auf, bevor `trading_client().get_calendar()` geht."""
    aufgerufen = []

    class FakeLimiter:
        def __init__(self, quelle):
            self.quelle = quelle

        def acquire(self):
            aufgerufen.append(self.quelle)

    fake_client = MagicMock()
    fake_client.get_calendar.return_value = []

    monkeypatch.setattr(hk, "RateLimiter", FakeLimiter, raising=False)
    monkeypatch.setattr("alpaca_bot.ratelimit.RateLimiter", FakeLimiter)
    monkeypatch.setattr("alpaca_bot.clients.trading_client", lambda: fake_client)

    hk._abrufen()

    assert aufgerufen == ["alpaca_trading"], (
        "trading_client().get_calendar() lief OHNE Drossel - "
        "genau der Regelverstoss, den 09_selfcheck.py meldet")
    fake_client.get_calendar.assert_called_once()


def test_selfcheck_meldet_keinen_verstoss_mehr():
    from alpaca_bot import selfcheck

    report = selfcheck.CheckReport()
    selfcheck.check_rate_limiting(report)
    betroffen = [v for v in report.violations if "handelskalender" in v.detail]
    assert not betroffen, betroffen
