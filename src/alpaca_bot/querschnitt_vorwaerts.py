"""Vorwaertsprotokoll fuer Querschnitt-Strategien: Koerbe festschreiben, bevor es Ergebnisse gibt.

**Warum das ueberhaupt noetig ist.** §G79 hat ausgerechnet, dass in
dieser Werkstatt rueckwaerts nichts mehr zu beweisen ist: Die
projektweite Zufallsschwelle liegt bei 4,90, und bei sechs Jahren Daten
braeuchte man dafuer einen Sharpe von 2,0. Ein einzelner, **vorab
angemeldeter** Test vorwaerts hat dagegen eine Huerde von rund 2,0 - weil
er ein Test ist und nicht der 470.001-te.

**Warum nicht ueber `fleet.anmelden`.** Die Flotte ist fuer Varianten des
Umkehr-Engines gebaut: `EngineConfig.for_reversal()` plus genau eine
geaenderte Achse. Eine Querschnitt-Strategie ist kein anderer Parameter,
sondern ein anderes Programm - und sie braucht Short-Positionen, die es
im Projekt nirgends gibt (geprueft 12.09.2026). Sie in die Flotte zu
pressen waere eine Scheinanmeldung.

**Was hier stattdessen passiert - und warum das sauber ist.** An jedem
Rebalance-Stichtag wird der gewaehlte Korb in eine Datenbank geschrieben:
Symbol, Seite, Kurs, Zeitstempel. Erst Wochen spaeter wird ausgewertet,
was er getan hat.

    Der Korb existiert, bevor sein Ergebnis existiert.

Das ist konstruktiv lookahead-frei - nicht, weil ein Test es prueft,
sondern weil die Zukunft zum Zeitpunkt des Schreibens noch nicht
stattgefunden hat. Kein Backtest kann das von sich behaupten.

**Ehrlich zur Dauer.** Bei einem Sharpe von 0,48 (§G78) braucht ein
t-Wert von 2,0 rund **17 Jahre**. Dieses Protokoll beweist die Strategie
also nicht in absehbarer Zeit. Es tut etwas anderes, das trotzdem etwas
wert ist: Es haelt fest, was vorab behauptet wurde, damit spaeter niemand
- auch nicht wir selbst - die Geschichte nachtraeglich zurechtlegen kann.
Und es faellt sofort auf, wenn die Strategie vorwaerts deutlich
schlechter laeuft als rueckwaerts. Das ist der haeufigste Fall.
"""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

import numpy as np
import pandas as pd

from .config import DATA_DIR

__all__ = ["Vorwaerts", "SCHEMA"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS anmeldung (
    id           TEXT PRIMARY KEY,
    angemeldet_am TEXT NOT NULL,
    name         TEXT NOT NULL,
    hypothese    TEXT NOT NULL,
    config_json  TEXT NOT NULL,
    kriterien_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS koerbe (
    anmeldung_id TEXT NOT NULL,
    stichtag     TEXT NOT NULL,
    erfasst_am   TEXT NOT NULL,
    symbol       TEXT NOT NULL,
    seite        TEXT NOT NULL,
    kurs         REAL NOT NULL,
    signalwert   REAL,
    PRIMARY KEY (anmeldung_id, stichtag, symbol)
);
CREATE TABLE IF NOT EXISTS ergebnisse (
    anmeldung_id TEXT NOT NULL,
    stichtag     TEXT NOT NULL,
    ausgewertet_am TEXT NOT NULL,
    ende         TEXT NOT NULL,
    r_long       REAL,
    r_short      REAL,
    brutto_pct   REAL,
    netto_pct    REAL,
    n_long       INTEGER,
    n_short      INTEGER,
    fehlend      INTEGER,
    PRIMARY KEY (anmeldung_id, stichtag)
);
"""


class Vorwaerts:
    """Die Datenbank. Eine Anmeldung, viele Koerbe, spaeter Ergebnisse."""

    def __init__(self, pfad: Path | None = None) -> None:
        self.pfad = Path(pfad) if pfad else (
            DATA_DIR / "querschnitt_vorwaerts.sqlite")
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

    # --- Anmeldung ---------------------------------------------------

    def anmelden(self, *, id: str, name: str, hypothese: str,
                 config: dict, kriterien: dict) -> str:
        """Schreibt die Voranmeldung. Einmal, dann unveraenderlich.

        Die Hypothese ist Pflicht und muss erklaeren, WARUM das tragen
        soll - dieselbe Disziplin wie `fleet.anmelden`. Ohne sie ist ein
        spaeterer Treffer nicht von einer nachtraeglichen Erzaehlung zu
        unterscheiden (§J.2).
        """
        if len(hypothese.strip()) < 20:
            raise ValueError(
                "Die Hypothese ist Pflicht und muss erklaeren, WARUM diese "
                "Strategie tragen sollte.")
        with self._conn() as c:
            vorhanden = c.execute(
                "SELECT angemeldet_am FROM anmeldung WHERE id=?",
                (id,)).fetchone()
            if vorhanden:
                raise ValueError(
                    f"Anmeldung {id!r} existiert seit {vorhanden[0]}. Eine "
                    f"Voranmeldung wird nicht ueberschrieben - sonst waere "
                    f"sie keine.")
            c.execute(
                "INSERT INTO anmeldung VALUES (?,?,?,?,?,?)",
                (id, dt.datetime.now(dt.UTC).isoformat(), name,
                 hypothese.strip(), json.dumps(config, default=str),
                 json.dumps(kriterien, default=str)))
        return id

    def anmeldung(self, id: str) -> dict | None:
        with self._conn() as c:
            r = c.execute("SELECT id, angemeldet_am, name, hypothese, "
                          "config_json, kriterien_json FROM anmeldung "
                          "WHERE id=?", (id,)).fetchone()
        if not r:
            return None
        return {"id": r[0], "angemeldet_am": r[1], "name": r[2],
                "hypothese": r[3], "config": json.loads(r[4]),
                "kriterien": json.loads(r[5])}

    # --- Koerbe ------------------------------------------------------

    def korb_schreiben(self, anmeldung_id: str, stichtag,
                       long_seite: pd.Series, short_seite: pd.Series,
                       kurse: pd.Series) -> int:
        """Legt einen Korb ab. Ein bestehender Stichtag wird NICHT ersetzt.

        Das ist die entscheidende Eigenschaft: Wer einen Korb nachtraeglich
        aendern koennte, koennte ihn nach dem Ergebnis aendern.
        """
        tag = pd.Timestamp(stichtag).date().isoformat()
        jetzt = dt.datetime.now(dt.UTC).isoformat()
        zeilen = []
        for seite, werte in (("long", long_seite), ("short", short_seite)):
            for sym, signal in werte.items():
                kurs = float(kurse.get(sym, float("nan")))
                if not np.isfinite(kurs) or kurs <= 0:
                    continue
                zeilen.append((anmeldung_id, tag, jetzt, str(sym), seite,
                               kurs, float(signal)))
        if not zeilen:
            return 0
        with self._conn() as c:
            schon = c.execute(
                "SELECT COUNT(*) FROM koerbe WHERE anmeldung_id=? AND "
                "stichtag=?", (anmeldung_id, tag)).fetchone()[0]
            if schon:
                raise ValueError(
                    f"Fuer {tag} liegen schon {schon} Zeilen vor. Ein Korb "
                    f"wird nicht neu geschrieben.")
            c.executemany("INSERT INTO koerbe VALUES (?,?,?,?,?,?,?)", zeilen)
        return len(zeilen)

    def stichtage(self, anmeldung_id: str) -> list[str]:
        with self._conn() as c:
            return [r[0] for r in c.execute(
                "SELECT DISTINCT stichtag FROM koerbe WHERE anmeldung_id=? "
                "ORDER BY stichtag", (anmeldung_id,))]

    def korb(self, anmeldung_id: str, stichtag: str) -> pd.DataFrame:
        with self._conn() as c:
            return pd.read_sql(
                "SELECT symbol, seite, kurs, signalwert, erfasst_am FROM "
                "koerbe WHERE anmeldung_id=? AND stichtag=?",
                c, params=(anmeldung_id, stichtag))

    def offene(self, anmeldung_id: str) -> list[str]:
        """Stichtage mit Korb, aber ohne Ergebnis."""
        with self._conn() as c:
            return [r[0] for r in c.execute(
                "SELECT DISTINCT k.stichtag FROM koerbe k LEFT JOIN "
                "ergebnisse e ON e.anmeldung_id=k.anmeldung_id AND "
                "e.stichtag=k.stichtag WHERE k.anmeldung_id=? AND "
                "e.stichtag IS NULL ORDER BY k.stichtag", (anmeldung_id,))]

    # --- Ergebnisse --------------------------------------------------

    def ergebnis_schreiben(self, anmeldung_id: str, stichtag: str,
                           **felder) -> None:
        with self._conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO ergebnisse VALUES "
                "(?,?,?,?,?,?,?,?,?,?,?)",
                (anmeldung_id, stichtag, dt.datetime.now(dt.UTC).isoformat(),
                 str(felder.get("ende", "")),
                 felder.get("r_long"), felder.get("r_short"),
                 felder.get("brutto_pct"), felder.get("netto_pct"),
                 int(felder.get("n_long", 0)), int(felder.get("n_short", 0)),
                 int(felder.get("fehlend", 0))))

    def ergebnisse(self, anmeldung_id: str) -> pd.DataFrame:
        with self._conn() as c:
            return pd.read_sql(
                "SELECT * FROM ergebnisse WHERE anmeldung_id=? "
                "ORDER BY stichtag", c, params=(anmeldung_id,))
