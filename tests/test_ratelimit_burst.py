"""RateLimiter.acquire(n) mit grossem n darf nicht abstuerzen (04.09.2026).

**Der Vorfall.** `scripts/44_jahresbot.py --quelle yf` rief
`RateLimiter("yfinance").acquire(120)` auf - ein Batch von 120 Symbolen.
Das yfinance-Minutenlimit ist 60. `acquire` konnte `recent + n <= allowed`
nie erfuellen (120 > 54) und lief in `wait = window - (now -
counter.events[0])` gegen einen LEEREN deque:

    IndexError: deque index out of range

**Der Fix.** Ein einzelner Aufruf fuer mehr als ein volles Fenster kann
nie regulaer durchgehen - dann laeuft das Fenster leer und `acquire`
ueberschreitet bewusst (Aufruferfehler, aber besser als Absturz oder
Endlosschleife). Der Aufrufer in `44_jahresbot.py` wurde zusaetzlich auf
Batches < Limit umgestellt.
"""

from __future__ import annotations

import threading

import pytest

from alpaca_bot.ratelimit import QUOTAS, RateLimiter


@pytest.fixture(autouse=True)
def _leerer_zaehler():
    """Der Minuten-/Sekundenzaehler von RateLimiter ist klassenweit geteilt.
    Vor jedem Test leeren, sonst vergiften sich die Tests gegenseitig."""
    RateLimiter._counters.pop("yfinance", None)
    yield
    RateLimiter._counters.pop("yfinance", None)


def _mit_timeout(fn, sekunden=5.0):
    fehler = []
    t = threading.Thread(target=lambda: fehler.append(_lauf(fn)), daemon=True)
    t.start()
    t.join(sekunden)
    assert not t.is_alive(), "acquire() haengt - Endlosschleife"
    if fehler and fehler[0] is not None:
        raise fehler[0]


def _lauf(fn):
    try:
        fn()
        return None
    except Exception as e:  # noqa: BLE001
        return e


def test_grosser_burst_stuerzt_nicht_ab():
    lim = RateLimiter("yfinance")
    minuten_limit = QUOTAS["yfinance"].per_minute or 60
    _mit_timeout(lambda: lim.acquire(minuten_limit * 3))


def test_normale_bursts_weiter_ok():
    lim = RateLimiter("yfinance")
    _mit_timeout(lambda: lim.acquire(1))
    _mit_timeout(lambda: lim.acquire(5))


def test_tageskontingent_bleibt_hart():
    lim = RateLimiter("yfinance")
    tag = QUOTAS["yfinance"].per_day
    if tag is None:
        pytest.skip("kein Tageslimit")
    from alpaca_bot.ratelimit import RateLimitExceeded
    with pytest.raises(RateLimitExceeded):
        lim.acquire(tag * 5)
