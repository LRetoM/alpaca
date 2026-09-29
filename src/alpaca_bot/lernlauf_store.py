"""Persistenz des Lernlaufs: lernlauf.sqlite.

**Warum es das jetzt gibt (24./25.08.2026, `docs/UMBAUPLAN.md` Schritt 4).**
`scripts/32_lernlauf.py` schrieb bis dahin nur eine CSV mit den
Jahresrenditen weg - jeder Lauf ueberschrieb den vorigen, und es gab
keine Moeglichkeit, zwei Laeufe (etwa vor/nach einer Codeaenderung) zu
vergleichen. Ohne `code_version` je Zeile waere ausserdem nicht mehr
feststellbar, welcher Codestand welches Ergebnis erzeugt hat - derselbe
Fehler wie in `docs/BEFUNDE.md` §G5, dort zwei Monate lang unbemerkt.

Bewusst eine EIGENE Datenbank, getrennt von `shadow.sqlite`: Der Lernlauf
ist kein Vorwaertstest und hat keinen Versuchszaehler-Bezug zur Flotte
(§2.2 des Umbauplans: ein Historienlauf kostet einen Zaehler-Platz erst,
wenn ein Kandidat daraus ins Kandidatenregister geht - nicht schon beim
blossen Rechnen). Eine gemeinsame Datei wuerde diese Trennung verwischen.

Liegt wie `shadow.sqlite` in `DATA_DIR`, NICHT unter `~/Documents`
(macOS-TCC blockiert Hintergrunddienste dort, `CLAUDE.md`).
"""

from __future__ import annotations

import datetime as dt
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import pandas as pd

from .config import DATA_DIR

LERNLAUF_DB = DATA_DIR / "lernlauf.sqlite"

SCHEMA = """
CREATE TABLE IF NOT EXISTS laeufe (
    lauf_id            TEXT PRIMARY KEY,
    gestartet_am       TEXT NOT NULL,
    code_version       TEXT,
    jahre              REAL,
    symbole            INTEGER,
    kapital            REAL,
    min_auswahl_jahre  INTEGER,
    n_jahresscheiben   INTEGER,
    n_signalgruppen    INTEGER,
    wf_n_jahre         INTEGER,
    wf_mittel_diff     REAL,
    wf_t               REAL,
    wf_schwelle        REAL,
    wf_jahre_mit_vorsprung INTEGER,
    wf_wechsel         INTEGER,
    beendet_am         TEXT
);

CREATE TABLE IF NOT EXISTS jahresergebnisse (
    lauf_id      TEXT NOT NULL,
    bot          TEXT NOT NULL,
    jahr         INTEGER NOT NULL,
    rendite      REAL,
    n_trades     INTEGER,
    achse        TEXT,
    wert         TEXT,
    PRIMARY KEY (lauf_id, bot, jahr)
);

CREATE TABLE IF NOT EXISTS bot_vergleiche (
    lauf_id      TEXT NOT NULL,
    bot          TEXT NOT NULL,
    basis        TEXT NOT NULL,
    n_tage       INTEGER,
    diff_mittel  REAL,
    diff_std     REAL,
    t_wert       REAL,
    schwelle     REAL,
    belastbar    INTEGER,
    streuung           REAL,
    nachweisbar_80     REAL,
    nachweisbar_kumuliert_80 REAL,
    PRIMARY KEY (lauf_id, bot)
);

CREATE TABLE IF NOT EXISTS walkforward_zeilen (
    lauf_id            TEXT NOT NULL,
    jahr               INTEGER NOT NULL,
    gewaehlt           TEXT,
    rendite_gewaehlt   REAL,
    rendite_basis      REAL,
    diff               REAL,
    PRIMARY KEY (lauf_id, jahr)
);

CREATE TABLE IF NOT EXISTS kandidaten (
    kandidat_id           TEXT PRIMARY KEY,
    achse                 TEXT NOT NULL,
    wert                  TEXT NOT NULL,
    hypothese             TEXT NOT NULL,
    entdeckt_am           TEXT NOT NULL,
    code_version           TEXT,
    hist_effekt_pro_tag   REAL,
    hist_t                REAL,
    hist_fenster          INTEGER,
    walkforward_t         REAL,
    n_varianten_getestet  INTEGER NOT NULL,
    status                TEXT NOT NULL,
    aktualisiert_am       TEXT
);
"""


class LernlaufStore:
    """Zugriff auf lernlauf.sqlite. Gleiches Muster wie `shadow.ShadowStore`."""

    TABELLEN = {"laeufe", "jahresergebnisse", "bot_vergleiche",
               "walkforward_zeilen", "kandidaten"}

    def __init__(self, path: Path = LERNLAUF_DB):
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

    def table(self, name: str, where: str = "", params: tuple = ()) -> pd.DataFrame:
        if name not in self.TABELLEN:
            raise ValueError(f"Unbekannte Tabelle {name!r}. Erlaubt: {sorted(self.TABELLEN)}")
        sql = f"SELECT * FROM {name}" + (f" WHERE {where}" if where else "")
        with self._conn() as c:
            return pd.read_sql_query(sql, c, params=params)

    # ------------------------------------------------------------------
    # Laeufe
    # ------------------------------------------------------------------
    def lauf_anlegen(self, *, code_version: str, jahre: float, symbole: int,
                     kapital: float, min_auswahl_jahre: int,
                     n_jahresscheiben: int, n_signalgruppen: int) -> str:
        lauf_id = uuid.uuid4().hex[:12]
        with self._conn() as c:
            c.execute(
                "INSERT INTO laeufe (lauf_id, gestartet_am, code_version, jahre,"
                " symbole, kapital, min_auswahl_jahre, n_jahresscheiben,"
                " n_signalgruppen) VALUES (?,?,?,?,?,?,?,?,?)",
                (lauf_id, dt.datetime.now(dt.UTC).isoformat(), code_version,
                 jahre, symbole, kapital, min_auswahl_jahre, n_jahresscheiben,
                 n_signalgruppen),
            )
        return lauf_id

    def jahresergebnis_schreiben(self, lauf_id: str, bot: str, jahr: int,
                                 rendite: float, n_trades: int,
                                 achse: str | None, wert: str | None) -> None:
        with self._conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO jahresergebnisse (lauf_id, bot, jahr,"
                " rendite, n_trades, achse, wert) VALUES (?,?,?,?,?,?,?)",
                (lauf_id, bot, int(jahr), rendite, n_trades, achse, wert),
            )

    def bot_vergleich_schreiben(self, lauf_id: str, bot: str, basis: str,
                                paar, streuung_erg) -> None:
        """`paar`: `lernlauf_eval.PaarVergleich`. `streuung_erg`:
        `lernlauf_eval.Trennschaerfe`."""
        with self._conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO bot_vergleiche (lauf_id, bot, basis,"
                " n_tage, diff_mittel, diff_std, t_wert, schwelle, belastbar,"
                " streuung, nachweisbar_80, nachweisbar_kumuliert_80)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (lauf_id, bot, basis, paar.n_tage, paar.diff_mittel,
                 paar.diff_std, paar.t_wert, paar.schwelle, int(paar.belastbar),
                 streuung_erg.streuung, streuung_erg.mit_80_prozent,
                 streuung_erg.kumuliert_80),
            )

    def walkforward_zeile_schreiben(self, lauf_id: str, zeile) -> None:
        """`zeile`: `lernlauf_eval.WalkForwardZeile`."""
        with self._conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO walkforward_zeilen (lauf_id, jahr,"
                " gewaehlt, rendite_gewaehlt, rendite_basis, diff)"
                " VALUES (?,?,?,?,?,?)",
                (lauf_id, int(zeile.jahr), zeile.gewaehlt,
                 zeile.rendite_gewaehlt, zeile.rendite_basis, zeile.diff),
            )

    def walkforward_test_schreiben(self, lauf_id: str, test, schwelle: float) -> None:
        """`test`: `lernlauf_eval.WalkForwardTest`."""
        with self._conn() as c:
            c.execute(
                "UPDATE laeufe SET wf_n_jahre=?, wf_mittel_diff=?, wf_t=?,"
                " wf_schwelle=?, wf_jahre_mit_vorsprung=?, wf_wechsel=?,"
                " beendet_am=? WHERE lauf_id=?",
                (test.n_jahre, test.mittel_diff, test.t_wert, schwelle,
                 test.jahre_mit_vorsprung, test.wechsel,
                 dt.datetime.now(dt.UTC).isoformat(), lauf_id),
            )
