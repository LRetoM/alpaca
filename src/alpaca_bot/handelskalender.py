"""Echte Handelstage statt Werktage (BEFUNDE §G38).

**Warum es dieses Modul gibt.** Die Haltedauer, an der `max_hold_days`
haengt, wurde live mit `pd.bdate_range` gezaehlt - also Montag bis
Freitag, Boersenfeiertage eingeschlossen. Simulation und Schattenbetrieb
zaehlen dagegen echte Bars, denn ein Feiertag existiert im Kursraster
schlicht nicht.

Folge: In jeder Woche mit einem Feiertag verkaufte der Live-Bot einen
Handelstag frueher als jede Messung, gegen die er verglichen wird.
`max_hold_days = 5` war live in Feiertagswochen faktisch eine
4-Tage-Regel.

**Warum eine feste Feiertagsliste die falsche Loesung waere.** Sie
veraltet still - genau die Fehlerklasse, gegen die dieses Projekt seine
Waechter gebaut hat (§G15). Der Kalender kommt deshalb von Alpaca
selbst, also von derselben Stelle, die auch den Handel ausfuehrt.

**Die Faelle, in denen es trotzdem `bdate_range` bleibt.** Ist der
Kalender nicht abrufbar und nichts zwischengespeichert, faellt die
Rechnung auf Werktage zurueck. Das ist schlechter, aber nie schlimmer
als der Zustand vor dem 26.08.2026 - und ein Abbruch waere hier die
gefaehrlichere Wahl: Eine Haltedauer, die nicht berechnet werden kann,
haelt Positionen unbegrenzt offen.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pandas as pd

from .config import DATA_DIR

CACHE = DATA_DIR / "handelskalender.json"
"""Plattencache. Der Boersenkalender aendert sich hoechstens jaehrlich -
ein Abruf je Woche reicht voellig, und offline muss es auch gehen."""

MAX_ALTER_TAGE = 7

_SPEICHER: dict | None = None


def _laden() -> dict[str, list[str]]:
    """Kalender aus dem Cache, notfalls frisch von Alpaca."""
    global _SPEICHER
    if _SPEICHER is not None:
        return _SPEICHER

    if CACHE.exists():
        try:
            roh = json.loads(CACHE.read_text())
            geholt = dt.date.fromisoformat(roh["geholt_am"])
            if (dt.date.today() - geholt).days <= MAX_ALTER_TAGE:
                _SPEICHER = roh
                return roh
        except Exception:  # noqa: BLE001 - kaputter Cache wird neu geholt
            pass

    frisch = _abrufen()
    if frisch:
        _SPEICHER = frisch
        try:
            CACHE.parent.mkdir(parents=True, exist_ok=True)
            CACHE.write_text(json.dumps(frisch))
        except Exception:  # noqa: BLE001 - Cache ist Bequemlichkeit, kein Muss
            pass
        return frisch

    # Netz weg UND kein frischer Cache: einen abgelaufenen nehmen wir
    # trotzdem - ein Kalender von letzter Woche ist besser als Werktage.
    if CACHE.exists():
        try:
            _SPEICHER = json.loads(CACHE.read_text())
            return _SPEICHER
        except Exception:  # noqa: BLE001
            pass
    return {}


def _abrufen() -> dict:
    """Handelstage von Alpaca, grosszuegiges Fenster in beide Richtungen."""
    try:
        from alpaca.trading.requests import GetCalendarRequest

        from .clients import trading_client

        heute = dt.date.today()
        req = GetCalendarRequest(start=heute - dt.timedelta(days=365 * 12),
                                 end=heute + dt.timedelta(days=400))
        tage = trading_client().get_calendar(req)
        return {"geholt_am": heute.isoformat(),
                "tage": sorted({str(t.date) for t in tage})}
    except Exception:  # noqa: BLE001 - Kalenderausfall darf nichts stoppen
        return {}


def handelstage() -> pd.DatetimeIndex | None:
    """Alle bekannten Handelstage, oder None wenn keiner verfuegbar ist."""
    daten = _laden()
    if not daten.get("tage"):
        return None
    return pd.DatetimeIndex(pd.to_datetime(daten["tage"])).normalize()


def zwischen(start, ende) -> int:
    """Handelstage NACH `start` bis einschliesslich `ende`.

    Dieselbe Zaehlweise wie bisher `len(pd.bdate_range(start, ende)) - 1`
    - der Einstiegstag zaehlt nicht mit, der Stichtag schon. Nur eben
    ueber echte Handelstage.

        zwischen("2026-09-03", "2026-09-10") == 4   # Labor Day faellt weg
        len(pd.bdate_range(...)) - 1              == 5   # zaehlt ihn mit
    """
    a = pd.Timestamp(start)
    b = pd.Timestamp(ende)
    a = (a.tz_localize(None) if a.tz is not None else a).normalize()
    b = (b.tz_localize(None) if b.tz is not None else b).normalize()
    if b < a:
        return 0

    kal = handelstage()
    if kal is None or len(kal) == 0 or a < kal[0] or b > kal[-1]:
        # Ausserhalb des bekannten Kalenders bleibt es bei Werktagen -
        # sichtbar schlechter, aber nie schlechter als frueher.
        return max(0, len(pd.bdate_range(a, b)) - 1)

    return int(((kal > a) & (kal <= b)).sum())
