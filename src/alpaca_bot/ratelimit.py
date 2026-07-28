"""Zentraler Rate-Limit-Waechter fuer ALLE externen APIs.

Ein einziger Ort, an dem jedes Limit steht. Kein Modul im Projekt darf
eine externe API ohne diesen Waechter aufrufen.

Warum das mehr ist als Hoeflichkeit:
  * Ein Backtest ueber 5000 Symbole macht schnell 50.000 Requests. Ohne
    Drossel ist das Konto nach 90 Sekunden gesperrt - mitten im Lauf,
    mit halb geladenen Daten, und der Datensatz ist still korrupt.
  * Tageslimits (Alpha Vantage: 25/Tag) sind nach einem Fehlversuch
    verbraucht. Deshalb wird der Zaehler auf Platte gehalten und
    ueberlebt Neustarts.

Zwei Mechanismen:
  1. Gleitendes Fenster pro Minute/Sekunde - blockiert, bis wieder Platz ist.
  2. Persistenter Tageszaehler in data/.ratelimit_state.json.

Zusaetzlich wird ein Sicherheitspuffer abgezogen (Standard 10 %), weil
Serveruhr und lokale Uhr nie exakt gleich laufen.
"""

from __future__ import annotations

import functools
import json
import random
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Callable

from .config import DATA_DIR

STATE_FILE = DATA_DIR / ".ratelimit_state.json"


@dataclass(frozen=True)
class Quota:
    """Limits einer API-Quelle.

    `verified` = Datum, an dem der Wert zuletzt gegen die offizielle
    Dokumentation geprueft wurde. Anbieter aendern Limits ohne Ankuendigung -
    wenn dieses Datum alt ist, nachpruefen.
    """

    name: str
    per_second: float | None = None
    per_minute: int | None = None
    per_hour: int | None = None
    per_day: int | None = None
    note: str = ""
    verified: str = ""
    docs: str = ""


# ---------------------------------------------------------------------------
# Die Wahrheit ueber alle Limits an genau einer Stelle.
# ---------------------------------------------------------------------------
QUOTAS: dict[str, Quota] = {
    "alpaca_trading": Quota(
        name="Alpaca Trading API",
        per_minute=200,
        note="200/min pro Konto. Paper und Live zaehlen getrennt.",
        verified="2026-07-28",
        docs="https://docs.alpaca.markets/us/docs/about-market-data-api",
    ),
    "alpaca_data": Quota(
        name="Alpaca Market Data (Basic/kostenlos)",
        per_minute=200,
        note=(
            "200/min. Historie ab 2016, die letzten 15 Minuten fehlen. "
            "Real-time nur IEX. Algo Trader Plus ($99/Mon) = 10.000/min."
        ),
        verified="2026-07-28",
        docs="https://docs.alpaca.markets/us/docs/about-market-data-api",
    ),
    "alpaca_news": Quota(
        name="Alpaca News API (Benzinga)",
        per_minute=200,
        note="Teilt sich das Market-Data-Kontingent. Historie ab ca. 2015.",
        verified="2026-07-28",
    ),
    "sec_edgar": Quota(
        name="SEC EDGAR",
        per_second=10,
        note=(
            "10/Sekunde pro IP, hart durchgesetzt. User-Agent mit Name und "
            "E-Mail ist PFLICHT - ohne kommt 403. Wir fahren 8/s."
        ),
        verified="2026-07-28",
        docs="https://www.sec.gov/os/webmaster-faq#developers",
    ),
    "fred": Quota(
        name="FRED (St. Louis Fed)",
        per_minute=120,
        note="Kein hartes veroeffentlichtes Limit, 120/min ist sicher. Key noetig, gratis.",
        verified="2026-07-28",
    ),
    "yfinance": Quota(
        name="yfinance (inoffiziell)",
        per_minute=60,
        per_day=2000,
        note=(
            "KEIN offizielles Limit - inoffizielle Yahoo-Schnittstelle. "
            "Seit 2024 aggressives Blocking. Bewusst konservativ. "
            "Nie fuer produktionskritische Pfade verwenden."
        ),
        verified="2026-07-28",
    ),
    "gdelt": Quota(
        name="GDELT DOC API",
        per_minute=30,
        note="Kein offizielles Limit. BigQuery-Variante: 1 TB Abfragen/Monat gratis.",
        verified="2026-07-28",
    ),
    "wikipedia": Quota(
        name="Wikimedia Pageviews API",
        per_second=50,
        note="200/s erlaubt, wir fahren 50/s. User-Agent erwuenscht.",
        verified="2026-07-28",
    ),
    "alphavantage": Quota(
        name="Alpha Vantage (kostenlos)",
        per_minute=5,
        per_day=25,
        note="25/TAG. Extrem knapp - nur fuer Einzelabfragen, nie in Schleifen.",
        verified="2026-07-28",
    ),
    "fmp": Quota(
        name="Financial Modeling Prep (kostenlos)",
        per_day=250,
        note="250/Tag.",
        verified="2026-07-28",
    ),
    "tiingo": Quota(
        name="Tiingo (kostenlos)",
        per_hour=50,
        per_day=500,
        note="50/Stunde und 500/Tag, max. 1000 verschiedene Symbole pro Monat.",
        verified="2026-07-28",
    ),
    "finnhub": Quota(
        name="Finnhub (kostenlos)",
        per_minute=60,
        note="60/min.",
        verified="2026-07-28",
    ),
}


class RateLimitExceeded(RuntimeError):
    """Tageskontingent aufgebraucht - warten hilft nicht mehr."""


@dataclass
class _Counter:
    events: deque = field(default_factory=deque)
    lock: threading.Lock = field(default_factory=threading.Lock)


class RateLimiter:
    """Drossel fuer eine Quelle. Threadsicher, prozessuebergreifend fuer Tageslimits."""

    _counters: dict[str, _Counter] = {}
    _state_lock = threading.Lock()

    def __init__(self, source: str, safety: float = 0.9, verbose: bool = False):
        if source not in QUOTAS:
            raise KeyError(
                f"Unbekannte Quelle {source!r}. Bekannt: {', '.join(sorted(QUOTAS))}. "
                "Neue APIs zuerst in QUOTAS eintragen - keine Ausnahmen."
            )
        self.source = source
        self.quota = QUOTAS[source]
        self.safety = safety
        self.verbose = verbose
        self._counters.setdefault(source, _Counter())

    # --- Tageszaehler auf Platte ------------------------------------------
    @classmethod
    def _load_state(cls) -> dict:
        if not STATE_FILE.exists():
            return {}
        try:
            return json.loads(STATE_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            return {}

    @classmethod
    def _save_state(cls, state: dict) -> None:
        try:
            STATE_FILE.write_text(json.dumps(state, indent=2))
        except OSError:
            pass  # Zaehler ist Komfort, kein Grund den Lauf abzubrechen

    def _bump_daily(self, n: int = 1) -> int:
        """Erhoeht den Tageszaehler und gibt den neuen Stand zurueck."""
        today = date.today().isoformat()
        with self._state_lock:
            state = self._load_state()
            entry = state.get(self.source, {})
            if entry.get("date") != today:
                entry = {"date": today, "count": 0}
            entry["count"] += n
            state[self.source] = entry
            self._save_state(state)
            return entry["count"]

    def used_today(self) -> int:
        entry = self._load_state().get(self.source, {})
        return entry.get("count", 0) if entry.get("date") == date.today().isoformat() else 0

    def remaining_today(self) -> int | None:
        if self.quota.per_day is None:
            return None
        return max(0, int(self.quota.per_day * self.safety) - self.used_today())

    # --- Hauptmethode ------------------------------------------------------
    def acquire(self, n: int = 1) -> None:
        """Blockiert, bis `n` Requests erlaubt sind. Zaehlt sie danach."""
        if self.quota.per_day is not None:
            limit = int(self.quota.per_day * self.safety)
            if self.used_today() + n > limit:
                raise RateLimitExceeded(
                    f"{self.quota.name}: Tageskontingent erschoepft "
                    f"({self.used_today()}/{limit}). "
                    f"Zuruecksetzung um Mitternacht. Hinweis: {self.quota.note}"
                )

        counter = self._counters[self.source]
        for window, limit in (
            (1.0, self.quota.per_second),
            (60.0, self.quota.per_minute),
            (3600.0, self.quota.per_hour),
        ):
            if limit is None:
                continue
            allowed = max(1, int(limit * self.safety))
            while True:
                with counter.lock:
                    now = time.monotonic()
                    while counter.events and now - counter.events[0] > window:
                        counter.events.popleft()
                    recent = sum(1 for t in counter.events if now - t <= window)
                    if recent + n <= allowed:
                        break
                    wait = window - (now - counter.events[0]) + 0.01
                if self.verbose:
                    print(f"  [Drossel] {self.quota.name}: warte {wait:.1f}s "
                          f"({recent}/{allowed} im {window:.0f}s-Fenster)")
                time.sleep(min(wait, window))

        with counter.lock:
            now = time.monotonic()
            counter.events.extend([now] * n)
        if self.quota.per_day is not None:
            self._bump_daily(n)

    def __enter__(self) -> RateLimiter:
        self.acquire()
        return self

    def __exit__(self, *exc) -> None:
        return None


def throttled(source: str, safety: float = 0.9, verbose: bool = False) -> Callable:
    """Dekorator: drosselt jeden Aufruf der Funktion.

        @throttled("alpaca_data")
        def hole_bars(...): ...
    """

    def decorator(fn: Callable) -> Callable:
        limiter = RateLimiter(source, safety=safety, verbose=verbose)

        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            limiter.acquire()
            return fn(*args, **kwargs)

        wrapper.limiter = limiter  # type: ignore[attr-defined]
        return wrapper

    return decorator


def with_retry(
    fn: Callable, *args, retries: int = 4, base_delay: float = 2.0, **kwargs
):
    """Fuehrt `fn` aus und wiederholt bei 429/Netzwerkfehlern mit Backoff.

    Wartezeit: 2s, 4s, 8s, 16s plus Zufallsanteil (Jitter), damit
    parallele Prozesse nicht synchron erneut anklopfen.
    """
    last = None
    for attempt in range(retries + 1):
        try:
            return fn(*args, **kwargs)
        except RateLimitExceeded:
            raise  # Tageslimit - warten ist sinnlos
        except Exception as e:  # noqa: BLE001 - Anbieter werfen sehr verschiedene Typen
            msg = str(e).lower()
            transient = any(
                k in msg
                for k in ("429", "rate limit", "too many requests", "timeout",
                          "connection", "502", "503", "504")
            )
            if not transient or attempt == retries:
                raise
            delay = base_delay * (2**attempt) + random.uniform(0, 1)
            print(f"  [Wiederholung {attempt + 1}/{retries}] {type(e).__name__} "
                  f"- warte {delay:.1f}s")
            last = e
            time.sleep(delay)
    if last:
        raise last


def budget_report() -> str:
    """Zeigt fuer alle Quellen Limit und heutigen Verbrauch."""
    lines = [
        f"{'Quelle':<34}{'pro Min':>9}{'pro Tag':>9}{'heute':>8}{'frei':>8}",
        "-" * 68,
    ]
    for key in sorted(QUOTAS):
        lim = RateLimiter(key)
        q = lim.quota
        pm = str(q.per_minute) if q.per_minute else (f"{q.per_second}/s" if q.per_second else "-")
        pd_ = str(q.per_day) if q.per_day else "-"
        used = lim.used_today() if q.per_day else 0
        rem = lim.remaining_today()
        lines.append(
            f"{q.name[:33]:<34}{pm:>9}{pd_:>9}"
            f"{(str(used) if q.per_day else '-'):>8}"
            f"{(str(rem) if rem is not None else '-'):>8}"
        )
    lines.append("")
    lines.append("Anmerkungen:")
    for key in sorted(QUOTAS):
        q = QUOTAS[key]
        if q.note:
            lines.append(f"  {key:<16} {q.note}")
    return "\n".join(lines)


def estimate_runtime(source: str, n_requests: int) -> str:
    """Wie lange dauert ein Lauf mit n Requests - und passt er ins Tageslimit?"""
    lim = RateLimiter(source)
    q = lim.quota
    rate = (q.per_minute * lim.safety / 60) if q.per_minute else (
        q.per_second * lim.safety if q.per_second else 10.0
    )
    seconds = n_requests / rate
    txt = (f"{q.name}: {n_requests:,} Requests bei {rate:.1f}/s "
           f"= {seconds / 60:.1f} Minuten")
    if q.per_day and n_requests > q.per_day * lim.safety:
        tage = n_requests / (q.per_day * lim.safety)
        txt += f"\n  ACHTUNG: uebersteigt das Tageslimit - braucht {tage:.1f} Tage."
    return txt
