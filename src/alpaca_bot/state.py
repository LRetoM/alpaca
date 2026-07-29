"""Zustandspersistenz: was ein Neustart nicht verlieren darf.

Alpaca kennt Symbol, Stueckzahl und Einstandskurs einer Position - mehr
nicht. Stop-Marke, Gewinnziel, Einstiegsdatum, Hoechststand und die
Begruendung des Kaufs existieren nur im Bot.

Ohne Persistenz wuerde ein Neustart diese Werte verlieren und sie
schaetzen muessen (bisher: `entry * 0.90`). Die Folge waere ein Bot, der
nach jedem Neustart andere Ausstiegsschwellen verwendet als vor dem
Absturz - und dessen Verhalten damit nicht mehr dem entspricht, was
simuliert wurde.

Der Entwurf ist bewusst so gebaut, dass **Alpaca die Wahrheit ueber das
Depot bleibt**: Welche Positionen existieren, sagt der Broker. Diese
Tabelle liefert nur die Zusatzangaben dazu. Findet sich beim Start eine
Position ohne gespeicherte Metadaten (etwa manuell gekauft), wird sie
uebernommen und konservativ ergaenzt - nie ignoriert.
"""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import pandas as pd

from .config import DATA_DIR

STATE_DB = DATA_DIR / "state.sqlite"

SCHEMA = """
CREATE TABLE IF NOT EXISTS position_meta (
    symbol        TEXT PRIMARY KEY,
    entry_price   REAL NOT NULL,
    entry_date    TEXT NOT NULL,
    stop_price    REAL NOT NULL,
    target_price  REAL NOT NULL,
    high_water    REAL NOT NULL,
    bars_held     INTEGER DEFAULT 0,
    entry_score   REAL,
    reasons       TEXT,
    updated_at    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS heartbeat (
    id            INTEGER PRIMARY KEY CHECK (id = 1),
    last_run      TEXT,
    last_ok       TEXT,
    runs_total    INTEGER DEFAULT 0,
    errors_total  INTEGER DEFAULT 0,
    last_error    TEXT,
    equity        REAL,
    positions     INTEGER
);
CREATE TABLE IF NOT EXISTS day_trades (
    trade_date TEXT NOT NULL,
    symbol     TEXT NOT NULL,
    PRIMARY KEY (trade_date, symbol)
);
CREATE TABLE IF NOT EXISTS exits (
    symbol      TEXT NOT NULL,
    exit_date   TEXT NOT NULL,
    exit_price  REAL,
    exit_reason TEXT,
    entry_price REAL,
    return_pct  REAL,
    bars_held   INTEGER,
    PRIMARY KEY (symbol, exit_date)
);
CREATE INDEX IF NOT EXISTS idx_exits_date ON exits(exit_date);
"""


class Store:
    """Dauerhafter Zustand ueber Neustarts hinweg."""

    def __init__(self, path: Path = STATE_DB):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.executescript(SCHEMA)

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    # --- Positions-Metadaten ----------------------------------------------
    def save_position(
        self, symbol: str, *, entry_price: float, entry_date, stop_price: float,
        target_price: float, high_water: float, bars_held: int = 0,
        entry_score: float | None = None, reasons: dict | None = None,
    ) -> None:
        with self._conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO position_meta VALUES (?,?,?,?,?,?,?,?,?,?)",
                (symbol, float(entry_price), pd.Timestamp(entry_date).isoformat(),
                 float(stop_price), float(target_price), float(high_water),
                 int(bars_held), entry_score,
                 json.dumps(reasons or {}, ensure_ascii=False),
                 dt.datetime.now(dt.UTC).isoformat()),
            )

    def load_positions(self) -> dict[str, dict]:
        with self._conn() as c:
            rows = c.execute("SELECT * FROM position_meta").fetchall()
        return {r["symbol"]: dict(r) for r in rows}

    def drop_position(self, symbol: str) -> None:
        with self._conn() as c:
            c.execute("DELETE FROM position_meta WHERE symbol = ?", (symbol,))

    def sync_with_broker(self, broker_symbols: set[str]) -> list[str]:
        """Entfernt Metadaten zu Positionen, die es beim Broker nicht mehr gibt.

        Notwendig, weil eine Position auch ausserhalb des Bots geschlossen
        werden kann - durch eine Bracket-Order, manuell im Dashboard oder
        durch einen Broker-Eingriff. Verwaiste Metadaten wuerden den Bot
        sonst glauben lassen, er halte etwas, das laengst verkauft ist.
        """
        stored = set(self.load_positions())
        orphans = stored - broker_symbols
        for sym in orphans:
            self.drop_position(sym)
        return sorted(orphans)

    # --- Ausstiege und Sperrfrist ------------------------------------------
    def record_exit(
        self, symbol: str, *, exit_price: float | None = None,
        exit_reason: str = "", entry_price: float | None = None,
        return_pct: float | None = None, bars_held: int | None = None,
        when=None,
    ) -> None:
        """Haelt fest, dass eine Position geschlossen wurde.

        Zwei Zwecke: Sperrfrist gegen sofortigen Rueckkauf, und Rohdaten
        fuer die spaetere Auswertung, welche Ausstiegsgruende sich
        bewaehrt haben.
        """
        ts = pd.Timestamp(when or pd.Timestamp.now(tz="UTC"))
        with self._conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO exits VALUES (?,?,?,?,?,?,?)",
                (symbol, ts.isoformat(), exit_price, exit_reason,
                 entry_price, return_pct, bars_held),
            )

    def symbols_in_cooldown(self, days: int, as_of=None) -> set[str]:
        """Symbole, die innerhalb der letzten `days` Handelstage verkauft wurden.

        Gerechnet wird in Handelstagen, nicht Kalendertagen - sonst waere
        eine Sperre ueber ein Wochenende faktisch aufgehoben.
        """
        if days <= 0:
            return set()
        now = pd.Timestamp(as_of or pd.Timestamp.now(tz="UTC"))
        if now.tz is None:
            now = now.tz_localize("UTC")
        cutoff = (now.normalize() - pd.tseries.offsets.BDay(days)).isoformat()
        with self._conn() as c:
            rows = c.execute(
                "SELECT DISTINCT symbol FROM exits WHERE exit_date >= ?", (cutoff,)
            ).fetchall()
        return {r["symbol"] for r in rows}

    def recent_exits(self, days: int = 30) -> pd.DataFrame:
        cutoff = (pd.Timestamp.now(tz="UTC").normalize()
                  - pd.Timedelta(days=days)).isoformat()
        with self._conn() as c:
            return pd.read_sql_query(
                "SELECT * FROM exits WHERE exit_date >= ? ORDER BY exit_date DESC",
                c, params=(cutoff,),
            )

    # --- Daytrade-Zaehler (PDT) -------------------------------------------
    def record_day_trade(self, symbol: str, when=None) -> None:
        day = pd.Timestamp(when or pd.Timestamp.now(tz="UTC")).strftime("%Y-%m-%d")
        with self._conn() as c:
            c.execute("INSERT OR IGNORE INTO day_trades VALUES (?,?)", (day, symbol))

    def day_trades_last(self, business_days: int = 5) -> int:
        cutoff = (pd.Timestamp.now(tz="UTC").normalize()
                  - pd.tseries.offsets.BDay(business_days)).strftime("%Y-%m-%d")
        with self._conn() as c:
            row = c.execute(
                "SELECT COUNT(*) AS n FROM day_trades WHERE trade_date >= ?", (cutoff,)
            ).fetchone()
        return int(row["n"])

    # --- Lebenszeichen -----------------------------------------------------
    def heartbeat(
        self, *, ok: bool, equity: float | None = None,
        positions: int | None = None, error: str | None = None,
    ) -> None:
        now = dt.datetime.now(dt.UTC).isoformat()
        with self._conn() as c:
            c.execute(
                "INSERT INTO heartbeat (id, last_run, last_ok, runs_total,"
                " errors_total, last_error, equity, positions)"
                " VALUES (1, ?, ?, 1, ?, ?, ?, ?)"
                " ON CONFLICT(id) DO UPDATE SET"
                "   last_run = excluded.last_run,"
                "   last_ok = CASE WHEN ? THEN excluded.last_run ELSE heartbeat.last_ok END,"
                "   runs_total = heartbeat.runs_total + 1,"
                "   errors_total = heartbeat.errors_total + ?,"
                "   last_error = COALESCE(excluded.last_error, heartbeat.last_error),"
                "   equity = COALESCE(excluded.equity, heartbeat.equity),"
                "   positions = COALESCE(excluded.positions, heartbeat.positions)",
                (now, now if ok else None, 0 if ok else 1, error, equity, positions,
                 1 if ok else 0, 0 if ok else 1),
            )

    def status(self) -> dict:
        with self._conn() as c:
            row = c.execute("SELECT * FROM heartbeat WHERE id = 1").fetchone()
        return dict(row) if row else {}

    def status_text(self) -> str:
        s = self.status()
        if not s:
            return "Noch kein Lauf protokolliert."
        pos = self.load_positions()
        lines = [
            "=" * 60,
            "  BOT-STATUS",
            "=" * 60,
            f"  Letzter Lauf      : {s.get('last_run', '-')}",
            f"  Letzter Erfolg    : {s.get('last_ok', '-')}",
            f"  Laeufe gesamt     : {s.get('runs_total', 0)}",
            f"  Fehler gesamt     : {s.get('errors_total', 0)}",
            f"  Kapital           : ${(s.get('equity') or 0):,.2f}",
            f"  Positionen        : {s.get('positions', 0)}"
            f"  (gespeicherte Metadaten: {len(pos)})",
        ]
        if s.get("last_error"):
            lines.append(f"  Letzter Fehler    : {s['last_error'][:120]}")
        if pos:
            lines.append("")
            lines.append("  Offene Positionen mit Zustand:")
            today = pd.Timestamp.now(tz="UTC").normalize()
            for sym, m in sorted(pos.items()):
                # Haltedauer aus dem Einstiegsdatum rechnen, nicht aus dem
                # gespeicherten Zaehler: Der Zaehler ist der Stand vom
                # Zeitpunkt des Schreibens und altert nicht mit. Angezeigt
                # werden muss derselbe Wert, den die Engine fuer den
                # Zeitausstieg verwendet - sonst zeigt der Status "0 Tage",
                # waehrend die Position tatsaechlich vor dem Ausstieg steht.
                entry = pd.Timestamp(m["entry_date"])
                if entry.tz is None:
                    entry = entry.tz_localize("UTC")
                held = max(0, len(pd.bdate_range(entry.normalize(), today)) - 1)
                lines.append(
                    f"    {sym:<6} Einstieg {m['entry_price']:>9.2f} | "
                    f"Stop {m['stop_price']:>9.2f} | Ziel {m['target_price']:>9.2f} | "
                    f"{held:>2} Tage"
                )
        return "\n".join(lines)
