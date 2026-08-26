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

-- ------------------------------------------------------------- Risiko-Dach
-- Die Sperre ist bewusst EINE Zeile mit fester id: Es kann immer nur einen
-- Sperrzustand geben. Waere sie eine Ereignisliste, muesste jeder Leser
-- selbst entscheiden, welcher Eintrag noch gilt - und ein vergessener
-- Filter hiesse, dass der Bot trotz Sperre weiterhandelt.
CREATE TABLE IF NOT EXISTS risiko_sperre (
    id           INTEGER PRIMARY KEY CHECK (id = 1),
    aktiv        INTEGER NOT NULL DEFAULT 0,
    grund        TEXT,
    kennzahlen   TEXT,
    gesetzt_am   TEXT,
    geloest_am   TEXT,
    geloest_von  TEXT
);

-- Equity je Zyklus. `heartbeat` haelt nur den LETZTEN Wert - ohne diese
-- Tabelle laesst sich im Nachhinein nicht sagen, wann ein Drawdown begann.
CREATE TABLE IF NOT EXISTS kapital_verlauf (
    ts            TEXT PRIMARY KEY,
    equity        REAL NOT NULL,
    cash          REAL NOT NULL,
    exposure      REAL NOT NULL,
    n_positionen  INTEGER NOT NULL,
    hoechststand  REAL NOT NULL,
    drawdown_pct  REAL NOT NULL,
    einzahlungen_kumuliert REAL NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_kapital_ts ON kapital_verlauf(ts);

-- Ein- und Auszahlungen. Der Alpaca-Aktivitaets-`id` ist der Schluessel:
-- Nur so kann derselbe Fluss nicht zweimal gebucht werden, egal wie oft
-- der Abgleich laeuft.
CREATE TABLE IF NOT EXISTS kapitalfluesse (
    id          TEXT PRIMARY KEY,
    ts          TEXT NOT NULL,
    art         TEXT NOT NULL,
    betrag      REAL NOT NULL,
    erkannt_am  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_fluesse_ts ON kapitalfluesse(ts);

-- Verdaechtigte, aber noch nicht bestaetigte Verwaisung (BEFUNDE §G37,
-- 26.08.2026). Ueberlebt Neustarts absichtlich: Der Fehler, den sie
-- verhindert, geschah GENAU bei einem Neustart.
CREATE TABLE IF NOT EXISTS verdacht_verwaist (
    symbol TEXT PRIMARY KEY,
    seit   TEXT NOT NULL
);
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

        **Erst nach ZWEI aufeinanderfolgenden Aufrufen loeschen** (BEFUNDE
        §G37, 26.08.2026). Anlass: `account.positions()` liess RMBS - eine
        einzige Order vom 20.08., nie verkauft, siehe `account.orders()` -
        in seiner Antwort aus. Die Marken wurden daraufhin SOFORT geloescht,
        und die Position blieb mehrere Tage ohne Stop, weil der naechste
        Abgleich (`missing`-Ergaenzung in `daemon.recover()`) das Symbol
        ebenfalls nicht als fehlend sah - der Broker-Read liess es
        wiederholt aus, nicht nur einmal. Ein einzelnes Fehlen wird deshalb
        nur vorgemerkt (Tabelle `verdacht_verwaist`, ueberlebt Neustarts -
        genau bei einem Neustart geschah der urspruengliche Fehler). Erst
        wer beim naechsten Aufruf IMMER NOCH fehlt, gilt als bestaetigt
        verwaist. Taucht ein vorgemerktes Symbol dazwischen wieder auf,
        wird der Verdacht automatisch verworfen (es steht dann nicht mehr
        in `fehlend`).
        """
        stored = set(self.load_positions())
        fehlend = stored - broker_symbols

        with self._conn() as c:
            vorher = {r["symbol"] for r in
                      c.execute("SELECT symbol FROM verdacht_verwaist").fetchall()}

            bestaetigt = sorted(fehlend & vorher)
            for sym in bestaetigt:
                self.drop_position(sym)

            neu_verdaechtig = sorted(fehlend - set(bestaetigt))
            c.execute("DELETE FROM verdacht_verwaist")
            c.executemany(
                "INSERT INTO verdacht_verwaist VALUES (?,?)",
                [(s, dt.datetime.now(dt.UTC).isoformat()) for s in neu_verdaechtig],
            )

        return bestaetigt

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

    # --- Risiko-Sperre -----------------------------------------------------
    def sperre_lesen(self) -> dict:
        with self._conn() as c:
            row = c.execute("SELECT * FROM risiko_sperre WHERE id = 1").fetchone()
        return dict(row) if row else {"aktiv": 0}

    def sperre_setzen(self, grund: str, kennzahlen: dict | None = None) -> None:
        """Setzt die Sperre. Idempotent - eine bestehende Sperre bleibt mit
        ihrem URSPRUENGLICHEN Grund und Zeitpunkt stehen.

        Warum nicht ueberschreiben: Der erste Ausloeser ist der
        interessante. Wuerde jeder Zyklus den Grund neu schreiben, stuende
        am Ende der zuletzt gepruefte dort - und die Frage "womit fing es
        an" waere nicht mehr beantwortbar.
        """
        with self._conn() as c:
            vorhanden = c.execute(
                "SELECT aktiv FROM risiko_sperre WHERE id = 1"
            ).fetchone()
            if vorhanden and int(vorhanden["aktiv"]) == 1:
                return
            c.execute(
                "INSERT INTO risiko_sperre (id, aktiv, grund, kennzahlen,"
                " gesetzt_am, geloest_am, geloest_von) VALUES (1,1,?,?,?,NULL,NULL)"
                " ON CONFLICT(id) DO UPDATE SET aktiv=1, grund=excluded.grund,"
                " kennzahlen=excluded.kennzahlen, gesetzt_am=excluded.gesetzt_am,"
                " geloest_am=NULL, geloest_von=NULL",
                (grund, json.dumps(kennzahlen or {}, ensure_ascii=False),
                 dt.datetime.now(dt.UTC).isoformat()),
            )

    def sperre_loesen(self, von: str) -> None:
        with self._conn() as c:
            c.execute(
                "UPDATE risiko_sperre SET aktiv=0, geloest_am=?, geloest_von=?"
                " WHERE id = 1",
                (dt.datetime.now(dt.UTC).isoformat(), von),
            )

    # --- Kapitalverlauf und Kapitalfluesse ---------------------------------
    def kapital_punkt(self, *, equity: float, cash: float, exposure: float,
                      n_positionen: int, hoechststand: float,
                      drawdown_pct: float, einzahlungen: float) -> None:
        with self._conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO kapital_verlauf VALUES (?,?,?,?,?,?,?,?)",
                (dt.datetime.now(dt.UTC).isoformat(), float(equity), float(cash),
                 float(exposure), int(n_positionen), float(hoechststand),
                 float(drawdown_pct), float(einzahlungen)),
            )

    def kapital_verlauf(self, tage: int = 90) -> pd.DataFrame:
        cutoff = (pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=tage)).isoformat()
        with self._conn() as c:
            return pd.read_sql_query(
                "SELECT * FROM kapital_verlauf WHERE ts >= ? ORDER BY ts",
                c, params=(cutoff,),
            )

    def fluss_buchen(self, fluss_id: str, ts, art: str, betrag: float) -> bool:
        """Bucht einen Kapitalfluss. Gibt True zurueck, wenn er NEU war.

        Der Alpaca-Aktivitaets-`id` ist der Primaerschluessel - derselbe
        Fluss kann dadurch nicht zweimal gezaehlt werden, egal wie oft der
        Abgleich laeuft. Ohne diese Zusicherung wuerde jede Wiederholung
        den Hoechststand des Drawdown-Zaehlers weiter verschieben.
        """
        with self._conn() as c:
            vorher = c.execute(
                "SELECT 1 FROM kapitalfluesse WHERE id = ?", (fluss_id,)
            ).fetchone()
            if vorher:
                return False
            c.execute(
                "INSERT INTO kapitalfluesse VALUES (?,?,?,?,?)",
                (fluss_id, pd.Timestamp(ts).isoformat(), art, float(betrag),
                 dt.datetime.now(dt.UTC).isoformat()),
            )
        return True

    def kapitalfluesse(self) -> pd.DataFrame:
        with self._conn() as c:
            return pd.read_sql_query(
                "SELECT * FROM kapitalfluesse ORDER BY ts", c
            )

    def einzahlungen_summe(self) -> float:
        """Summe aller Ein- minus Auszahlungen. Bezugsgroesse fuer den
        einzahlungsbereinigten Hoechststand."""
        with self._conn() as c:
            row = c.execute(
                "SELECT COALESCE(SUM(betrag), 0) AS s FROM kapitalfluesse"
            ).fetchone()
        return float(row["s"] or 0.0)

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
