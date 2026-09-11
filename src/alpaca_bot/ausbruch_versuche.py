"""Versuchsprotokoll der Ausbruch-Suche - jede gepruefte Konfiguration.

**Warum jeder Versuch gespeichert wird, nicht nur der beste.** Der beste
Fund einer Suche ueber eine Million Konfigurationen ist per Konstruktion
ein Ausreisser (§B2). Die eigentliche Erkenntnis steckt woanders:

    Nicht "welche Konfiguration hat gewonnen",
    sondern "welche Achsenwerte schneiden ueber TAUSENDE Versuche
    hinweg systematisch besser ab".

Das Zweite ist robust, das Erste ist Rauschen. Dafuer braucht es das
vollstaendige Protokoll - `scripts/52_ausbruch_auswertung.py` rechnet
daraus die Randverteilung je Achse.

**Eine Datei je Instanz, bewusst.** Vier Prozesse, die gleichzeitig in
dieselbe SQLite schreiben, blockieren sich (`database is locked`). Bei
5,4 Versuchen je Sekunde ueber 48 Stunden waere das ein Dauerproblem.
Getrennte Dateien haben keine Sperren; `zusammenfuehren()` liest sie am
Ende in einem Rutsch.
"""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

import pandas as pd

from .config import DATA_DIR

__all__ = ["Protokoll", "zusammenfuehren", "instanzen"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS versuche (
    nr           INTEGER,
    instanz      TEXT,
    ts           TEXT,
    phase        TEXT,
    score        REAL,
    n_trades     INTEGER,
    t_lern       REAL,
    rendite_lern REAL,
    mittel_lern  REAL,
    dd_lern      REAL,
    tage_lern    INTEGER,
    t_pruef      REAL,
    rendite_pruef REAL,
    mittel_pruef REAL,
    pruef_grund  TEXT,
    besser       INTEGER,
    config       TEXT
);
CREATE INDEX IF NOT EXISTS idx_v_score ON versuche(score);
CREATE INDEX IF NOT EXISTS idx_v_pruef ON versuche(t_pruef);
"""


def _datei(instanz: str) -> Path:
    return DATA_DIR / f"ausbruch_versuche_{instanz}.sqlite"


def instanzen() -> list[str]:
    """Welche Instanz-Protokolle liegen vor?"""
    return sorted(p.stem.rsplit("_", 1)[-1]
                  for p in DATA_DIR.glob("ausbruch_versuche_*.sqlite"))


class Protokoll:
    """Sammelt Versuche und schreibt sie gebuendelt weg.

    Gebuendelt, weil bei 5 Versuchen je Sekunde ein einzelnes INSERT je
    Versuch die Suche spuerbar bremsen wuerde - und weil ein Absturz
    zwischen zwei Buendeln hoechstens `bundel` Zeilen kostet, nicht den
    Lauf.
    """

    def __init__(self, instanz: str, *, bundel: int = 250) -> None:
        self.instanz = instanz
        self.pfad = _datei(instanz)
        self.bundel = bundel
        self._puffer: list[tuple] = []
        self.pfad.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.executescript(SCHEMA)

    @contextmanager
    def _conn(self):
        c = sqlite3.connect(self.pfad, timeout=30)
        try:
            yield c
            c.commit()
        finally:
            c.close()

    def merken(self, v, pruef_kennzahlen: dict | None = None,
               pruef_grund: str = "") -> None:
        """Einen Versuch in den Puffer legen.

        Args:
            v: der `Versuch` aus `ausbruch_suche`.
            pruef_kennzahlen: nur gefuellt, wenn das Prueffenster fuer
                diesen Versuch ueberhaupt gerechnet wurde.
            pruef_grund: warum es gerechnet wurde - "bester" (neuer
                globaler Bestwert) oder "stichprobe" (Zufallsauswahl
                fuer die spaetere Auswertung). Die Unterscheidung ist
                wichtig: Nur "bester" traegt die Auswahl, "stichprobe"
                ist unverzerrt und beschreibt den Zusammenhang zwischen
                Lern- und Pruefwert.
        """
        k = v.kennzahlen or {}
        pk = pruef_kennzahlen or {}
        self._puffer.append((
            int(v.nr), self.instanz, dt.datetime.now(dt.UTC).isoformat(),
            v.phase,
            None if v.score == float("-inf") else float(v.score),
            int(k.get("n_trades", 0) or 0),
            _z(k.get("t_wert")), _z(k.get("rendite_pct")),
            _z(k.get("mittel_pct")), _z(k.get("max_drawdown_pct")),
            int(k.get("n_handelstage", 0) or 0),
            _z(pk.get("t_wert")), _z(pk.get("rendite_pct")),
            _z(pk.get("mittel_pct")),
            pruef_grund or None,
            1 if v.besser else 0,
            json.dumps(v.config, default=str),
        ))
        if len(self._puffer) >= self.bundel:
            self.leeren()

    def leeren(self) -> int:
        """Puffer wegschreiben. Gibt die Zahl geschriebener Zeilen zurueck."""
        if not self._puffer:
            return 0
        n = len(self._puffer)
        with self._conn() as c:
            c.executemany(
                "INSERT INTO versuche VALUES (" + ",".join("?" * 17) + ")",
                self._puffer)
        self._puffer.clear()
        return n

    def anzahl(self) -> int:
        with self._conn() as c:
            return int(c.execute("SELECT COUNT(*) FROM versuche").fetchone()[0])


def _z(x) -> float | None:
    """NaN und Inf sind in SQLite wertlos - lieber ehrlich NULL."""
    if x is None:
        return None
    try:
        f = float(x)
    except (TypeError, ValueError):
        return None
    return None if (f != f or f in (float("inf"), float("-inf"))) else f


def zusammenfuehren(instanzen_: list[str] | None = None) -> pd.DataFrame:
    """Alle Instanz-Protokolle in eine Tabelle.

    Die Config-Spalte wird dabei in einzelne Spalten aufgefaltet - erst
    dann laesst sich fragen, welcher Achsenwert systematisch besser
    abschneidet.
    """
    aus = []
    for i in (instanzen_ or instanzen()):
        p = _datei(i)
        if not p.exists():
            continue
        c = sqlite3.connect(p)
        try:
            aus.append(pd.read_sql("SELECT * FROM versuche", c))
        finally:
            c.close()
    if not aus:
        return pd.DataFrame()
    df = pd.concat(aus, ignore_index=True)
    if "config" in df.columns and len(df):
        entfaltet = pd.DataFrame(
            [json.loads(s) if s else {} for s in df["config"]],
            index=df.index).add_prefix("k_")
        df = pd.concat([df.drop(columns=["config"]), entfaltet], axis=1)
    return df
