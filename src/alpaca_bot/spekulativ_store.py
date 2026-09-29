"""Persistenz des spekulativen Historienlaufs: spekulativ.sqlite.

Gleiches Muster wie `lernlauf_store.LernlaufStore`. Eine EIGENE Datenbank,
weil dieser Lauf - wie der Lernlauf - kein Vorwaertstest ist und keinen
Versuchszaehler-Bezug zur Flotte hat, solange nichts angemeldet wird.

Liegt in `DATA_DIR`, NICHT unter `~/Documents` (macOS-TCC, `CLAUDE.md`).
Zweck: zwei Sweeps (etwa vor/nach einer Codeaenderung, oder mit anderem
Universum) vergleichbar halten, statt eine CSV zu ueberschreiben.
"""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import pandas as pd

from .config import DATA_DIR

SPEKULATIV_DB = DATA_DIR / "spekulativ.sqlite"

SCHEMA = """
CREATE TABLE IF NOT EXISTS laeufe (
    lauf_id       TEXT PRIMARY KEY,
    gestartet_am  TEXT NOT NULL,
    code_version  TEXT,
    art           TEXT,              -- 'einzeln' | 'sweep' | 'walkforward'
    jahre         REAL,
    symbole       INTEGER,
    universum     TEXT,
    quelle        TEXT,
    n_konfigs     INTEGER,
    schwelle      REAL,
    notiz         TEXT,
    beendet_am    TEXT
);

CREATE TABLE IF NOT EXISTS ergebnisse (
    lauf_id            TEXT NOT NULL,
    zeile             INTEGER NOT NULL,
    belegung_json     TEXT,           -- die gesetzten Achsen dieser Zeile
    config_json       TEXT,
    total_return      REAL,
    cagr              REAL,
    max_drawdown      REAL,
    sharpe            REAL,
    n_trades          INTEGER,
    trades_pro_tag    REAL,
    ertrag_je_trade   REAL,
    t_gruppiert       REAL,
    t_naiv            REAL,
    n_handelstage     INTEGER,
    min_jahr_rendite  REAL,
    jahre_positiv     INTEGER,
    jahre_gesamt      INTEGER,
    ruin              INTEGER,
    bs_p05            REAL,
    bs_p50            REAL,
    bs_p95            REAL,
    bs_prob_verlust   REAL,
    bs_prob_ruin      REAL,
    PRIMARY KEY (lauf_id, zeile)
);

CREATE TABLE IF NOT EXISTS walkforward_zeilen (
    lauf_id          TEXT NOT NULL,
    jahr             INTEGER NOT NULL,
    gewaehlt_json    TEXT,
    rendite_gewaehlt REAL,
    rendite_basis    REAL,
    diff             REAL,
    PRIMARY KEY (lauf_id, jahr)
);
"""


class SpekulativStore:
    """Zugriff auf spekulativ.sqlite."""

    TABELLEN = {"laeufe", "ergebnisse", "walkforward_zeilen"}

    # Spalten, die spaeter dazukamen - fuer bestehende Dateien nachziehen.
    # `CREATE TABLE IF NOT EXISTS` aendert eine vorhandene Tabelle nicht.
    _NACHRUESTEN = {
        "ergebnisse": {
            "min_jahr_rendite": "REAL",
            "jahre_positiv": "INTEGER",
            "jahre_gesamt": "INTEGER",
        },
    }

    def __init__(self, path: Path = SPEKULATIV_DB):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.executescript(SCHEMA)
            for tabelle, spalten in self._NACHRUESTEN.items():
                vorhanden = {row[1] for row in
                             c.execute(f"PRAGMA table_info({tabelle})")}
                for name, typ in spalten.items():
                    if name not in vorhanden:
                        c.execute(f"ALTER TABLE {tabelle} ADD COLUMN {name} {typ}")

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def table(self, name: str, where: str = "", params: tuple = ()) -> pd.DataFrame:
        if name not in self.TABELLEN:
            raise ValueError(f"Unbekannte Tabelle {name!r}. Erlaubt: {sorted(self.TABELLEN)}")
        sql = f"SELECT * FROM {name}" + (f" WHERE {where}" if where else "")
        with self._conn() as c:
            return pd.read_sql_query(sql, c, params=params)

    # ------------------------------------------------------------------
    def lauf_anlegen(self, *, code_version: str, art: str, jahre: float,
                     symbole: int, universum: str, quelle: str,
                     n_konfigs: int, schwelle: float,
                     notiz: str = "") -> str:
        lauf_id = uuid.uuid4().hex[:12]
        with self._conn() as c:
            c.execute(
                "INSERT INTO laeufe (lauf_id, gestartet_am, code_version, art,"
                " jahre, symbole, universum, quelle, n_konfigs, schwelle, notiz)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (lauf_id, dt.datetime.now(dt.UTC).isoformat(), code_version, art,
                 jahre, symbole, universum, quelle, n_konfigs, schwelle, notiz),
            )
        return lauf_id

    def lauf_beenden(self, lauf_id: str) -> None:
        with self._conn() as c:
            c.execute("UPDATE laeufe SET beendet_am=? WHERE lauf_id=?",
                      (dt.datetime.now(dt.UTC).isoformat(), lauf_id))

    def ergebnis_schreiben(self, lauf_id: str, zeile: int, *, belegung: dict,
                           config: dict, metriken: dict, gruppentest,
                           bootstrap: dict, n_handelstage: int,
                           min_jahr_rendite: float | None = None,
                           jahre_positiv: int | None = None,
                           jahre_gesamt: int | None = None) -> None:
        massgeblich = (gruppentest.t_ueberlappung
                       if gruppentest is not None
                       and gruppentest.t_ueberlappung == gruppentest.t_ueberlappung
                       else (gruppentest.t if gruppentest is not None else None))
        with self._conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO ergebnisse (lauf_id, zeile, belegung_json,"
                " config_json, total_return, cagr, max_drawdown, sharpe, n_trades,"
                " trades_pro_tag, ertrag_je_trade, t_gruppiert, t_naiv,"
                " n_handelstage, min_jahr_rendite, jahre_positiv, jahre_gesamt,"
                " ruin, bs_p05, bs_p50, bs_p95, bs_prob_verlust,"
                " bs_prob_ruin) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (lauf_id, int(zeile), json.dumps(belegung, default=str),
                 json.dumps(config, default=str),
                 metriken.get("total_return"), metriken.get("cagr"),
                 metriken.get("max_drawdown"), metriken.get("sharpe"),
                 metriken.get("n_trades"), metriken.get("trades_pro_tag"),
                 metriken.get("ertrag_je_trade"),
                 float(massgeblich) if massgeblich is not None else None,
                 float(gruppentest.t_naiv) if gruppentest is not None else None,
                 int(n_handelstage),
                 min_jahr_rendite, jahre_positiv, jahre_gesamt,
                 int(bool(metriken.get("ruin"))),
                 bootstrap.get("p05"), bootstrap.get("p50"), bootstrap.get("p95"),
                 bootstrap.get("prob_verlust"), bootstrap.get("prob_ruin_80pct")),
            )

    def walkforward_zeile_schreiben(self, lauf_id: str, jahr: int, *,
                                    gewaehlt: dict, rendite_gewaehlt: float,
                                    rendite_basis: float) -> None:
        with self._conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO walkforward_zeilen (lauf_id, jahr,"
                " gewaehlt_json, rendite_gewaehlt, rendite_basis, diff)"
                " VALUES (?,?,?,?,?,?)",
                (lauf_id, int(jahr), json.dumps(gewaehlt, default=str),
                 float(rendite_gewaehlt), float(rendite_basis),
                 float(rendite_gewaehlt - rendite_basis)),
            )
