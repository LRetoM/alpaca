"""Datenbank fuer die Ausbruch-Versuche.

**Wozu speichern.** Wer eine Oberflaeche zum Herumprobieren baut, baut
zwangslaeufig eine Maschine, die Scheingewinner herstellt (§B2: bei N
Versuchen liegt das Zufallsmaximum bei `sqrt(2 ln N)`). Das laesst sich
nicht verhindern - aber es laesst sich **zaehlen**.

Deshalb schreibt jeder Lauf in `ausbruch.sqlite`:

* `laeufe`      - Konfiguration und Kennzahlen, ein Datensatz je Lauf
* `trades`      - jeder Einzeltrade, fuer Nachrechnen und Fehlersuche
* `equity`      - die Depotkurve, ausgeduennt
* `symbol_stat` - je Symbol: wie oft, wie erfolgreich (die Bestenliste)

Aus `laeufe` folgt die Zahl der Versuche und damit die Schwelle, ueber
der ein t-Wert ueberhaupt etwas heisst. **Diese Zaehlung ist der
eigentliche Zweck der Datenbank** - die Trades sind Beiwerk.

**Getrennt vom Flotten-Zaehler.** `fleet.schwelle_sigma()` zaehlt
angemeldete Vorwaertsbots. Historienlaeufe kosten dort bewusst keinen
Platz (`BETRIEBSPLAN` §4) - sonst waere billiges Vorfiltern teuer. Hier
laeuft ein eigener Zaehler fuer eine eigene Frage.
"""

from __future__ import annotations

import datetime as dt
import json
import math
import sqlite3
import uuid
from contextlib import contextmanager

import pandas as pd

from .config import DATA_DIR

DB = DATA_DIR / "ausbruch.sqlite"

SCHEMA = """
CREATE TABLE IF NOT EXISTS laeufe (
    lauf_id        TEXT PRIMARY KEY,
    gestartet_am   TEXT NOT NULL,
    beendet_am     TEXT,
    notiz          TEXT,
    jahr           INTEGER,
    raster         TEXT,
    n_symbole      INTEGER,
    config_json    TEXT NOT NULL,
    kennzahlen_json TEXT,
    status         TEXT DEFAULT 'laeuft'
);
CREATE TABLE IF NOT EXISTS trades (
    lauf_id     TEXT NOT NULL,
    symbol      TEXT NOT NULL,
    einstieg_ts TEXT, einstieg_kurs REAL,
    ausstieg_ts TEXT, ausstieg_kurs REAL,
    grund       TEXT, stueck REAL,
    rendite_pct REAL, rendite_brutto_pct REAL,
    gehalten_bars INTEGER,
    ausloeser_anstieg_pct REAL, rel_volumen REAL, gewinn_usd REAL
);
CREATE INDEX IF NOT EXISTS idx_trades_lauf ON trades(lauf_id);
CREATE TABLE IF NOT EXISTS equity (
    lauf_id TEXT NOT NULL, ts TEXT NOT NULL, wert REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_equity_lauf ON equity(lauf_id);
CREATE TABLE IF NOT EXISTS symbol_stat (
    lauf_id TEXT NOT NULL, symbol TEXT NOT NULL,
    n_trades INTEGER, treffer_pct REAL, mittel_pct REAL,
    median_pct REAL, summe_usd REAL, bester_pct REAL, schlechtester_pct REAL
);
CREATE INDEX IF NOT EXISTS idx_symstat_lauf ON symbol_stat(lauf_id);
CREATE TABLE IF NOT EXISTS suchversuche (
    lauf_id TEXT PRIMARY KEY, n INTEGER NOT NULL, gebucht_am TEXT
);
"""

__all__ = ["DB", "neuer_lauf", "abschliessen", "speichern", "n_versuche",
           "schwelle_sigma", "laeufe", "trades_von", "bestenliste",
           "lauf_loeschen", "suchversuche_buchen"]


@contextmanager
def _conn():
    DB.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB)
    try:
        c.executescript(SCHEMA)
        yield c
        c.commit()
    finally:
        c.close()


def neuer_lauf(config: dict, *, jahr: int, raster: str, n_symbole: int,
               notiz: str = "") -> str:
    """Meldet einen Lauf an, BEVOR er rechnet.

    Die Reihenfolge ist Absicht: Ein Lauf, der erst nach dem Ergebnis
    gezaehlt wuerde, liesse sich stillschweigend verwerfen, wenn er
    nicht gefaellt. Genau das ist die Luecke, gegen die §B2 existiert.
    """
    lauf_id = uuid.uuid4().hex[:12]
    with _conn() as c:
        c.execute(
            "INSERT INTO laeufe (lauf_id, gestartet_am, notiz, jahr, raster,"
            " n_symbole, config_json, status) VALUES (?,?,?,?,?,?,?,'laeuft')",
            (lauf_id, dt.datetime.now(dt.UTC).isoformat(), notiz, jahr,
             raster, n_symbole, json.dumps(config, default=str)),
        )
    return lauf_id


def abschliessen(lauf_id: str, kennzahlen: dict, status: str = "fertig") -> None:
    with _conn() as c:
        c.execute(
            "UPDATE laeufe SET beendet_am=?, kennzahlen_json=?, status=?"
            " WHERE lauf_id=?",
            (dt.datetime.now(dt.UTC).isoformat(),
             json.dumps(kennzahlen, default=str), status, lauf_id),
        )


def speichern(lauf_id: str, trades: pd.DataFrame, equity: pd.Series,
              *, equity_punkte: int = 2000) -> None:
    """Legt Trades, Depotkurve und Symbol-Bestenliste ab."""
    with _conn() as c:
        if not trades.empty:
            t = trades.copy()
            t.insert(0, "lauf_id", lauf_id)
            for sp in ("einstieg_ts", "ausstieg_ts"):
                if sp in t:
                    t[sp] = t[sp].astype(str)
            t.to_sql("trades", c, if_exists="append", index=False)

            g = t.groupby("symbol")["rendite_pct"]
            stat = pd.DataFrame({
                "n_trades": g.size(),
                "treffer_pct": g.apply(lambda s: (s > 0).mean() * 100.0),
                "mittel_pct": g.mean(),
                "median_pct": g.median(),
                "bester_pct": g.max(),
                "schlechtester_pct": g.min(),
                "summe_usd": t.groupby("symbol")["gewinn_usd"].sum(),
            }).reset_index()
            stat.insert(0, "lauf_id", lauf_id)
            stat.to_sql("symbol_stat", c, if_exists="append", index=False)

        if equity is not None and len(equity):
            # Ausduennen: 8.000 Punkte je Lauf braucht niemand, und eine
            # Datenbank, die bei Lauf 200 traege wird, wird nicht benutzt.
            schritt = max(1, len(equity) // equity_punkte)
            e = equity.iloc[::schritt]
            pd.DataFrame({"lauf_id": lauf_id,
                          "ts": [str(x) for x in e.index],
                          "wert": e.to_numpy(dtype=float)}
                         ).to_sql("equity", c, if_exists="append", index=False)


def suchversuche_buchen(lauf_id: str, n: int) -> None:
    """Traegt die Teilversuche einer automatischen Suche nach.

    Eine Suche ist EIN Eintrag in `laeufe`, hat die Daten aber
    n-mal befragt. Ohne diese Buchung wuerde eine Suche mit 3.000
    Durchlaeufen die Schwelle um denselben Betrag heben wie ein
    einziger Handlauf - und genau daran wuerde die ganze Zaehlung
    wertlos.
    """
    with _conn() as c:
        c.execute("INSERT OR REPLACE INTO suchversuche VALUES (?,?,?)",
                  (lauf_id, int(n), dt.datetime.now(dt.UTC).isoformat()))


def n_versuche() -> int:
    """Wie oft die Historie fuer diese Strategiefamilie befragt wurde.

    **Handlaeufe plus alle Teilversuche automatischer Suchen.** Das ist
    die unbequeme, aber einzige ehrliche Zaehlung: Eine Suche mit 3.000
    Durchlaeufen hat die Daten 3.000-mal gesehen, und keine spaetere
    Auswertung kann so tun, als waere sie die erste. Die Schwelle steigt
    entsprechend fuer ALLE - auch fuer Handlaeufe in der Werkstatt.

    Gezaehlt werden auch abgebrochene und verworfene Laeufe: Ein Lauf,
    den man ansieht und wegwirft, hat die Historie genauso befragt wie
    einer, den man behaelt.
    """
    with _conn() as c:
        hand = int(c.execute("SELECT COUNT(*) FROM laeufe").fetchone()[0])
        # Eine Suche zaehlt als ihre Teilversuche, nicht zusaetzlich als
        # eigener Lauf - sonst waere sie um eins zu teuer.
        such_n = c.execute(
            "SELECT COALESCE(SUM(n), 0), COUNT(*) FROM suchversuche"
        ).fetchone()
    return hand - int(such_n[1]) + int(such_n[0])


def schwelle_sigma(n: int | None = None) -> float:
    """Ab welchem t-Wert ein Ergebnis ueber Zufall hinausgeht.

    `sqrt(2 ln N)` - das erwartete Maximum aus N unabhaengigen Versuchen
    (§B2). Untergrenze 2,0, damit der erste Lauf keine laecherlich
    niedrige Huerde bekommt.
    """
    n = n_versuche() if n is None else n
    return max(2.0, math.sqrt(2.0 * math.log(max(n, 2))))


def laeufe(limit: int = 200) -> pd.DataFrame:
    with _conn() as c:
        df = pd.read_sql(
            "SELECT * FROM laeufe ORDER BY gestartet_am DESC LIMIT ?",
            c, params=(limit,))
    if df.empty:
        return df
    kz = df["kennzahlen_json"].apply(
        lambda s: json.loads(s) if s else {})
    for feld in ("rendite_pct", "n_trades", "trefferquote_pct", "t_wert",
                 "max_drawdown_pct", "n_handelstage", "profit_faktor"):
        df[feld] = kz.apply(lambda d, f=feld: d.get(f))
    return df


def trades_von(lauf_id: str) -> pd.DataFrame:
    with _conn() as c:
        return pd.read_sql("SELECT * FROM trades WHERE lauf_id=?", c,
                           params=(lauf_id,))


def bestenliste(lauf_id: str | None = None, *, min_trades: int = 3,
                limit: int = 50) -> pd.DataFrame:
    """Welche Symbole trugen - ueber einen Lauf oder ueber alle.

    **Vorsicht mit dieser Tabelle.** Sie ist die verfuehrerischste
    Ansicht des ganzen Werkzeugs: Bei 1.200 Symbolen steht oben immer
    etwas Beeindruckendes, auch wenn die Strategie nichts kann. Der
    `min_trades`-Filter daempft das, beseitigt es aber nicht - §B4 zeigt
    den Mechanismus an echten Daten (PEAD: t=6,7 auf 60 Symbolen, tot
    auf 800).
    """
    where = "WHERE lauf_id=?" if lauf_id else ""
    args: tuple = (lauf_id,) if lauf_id else ()
    with _conn() as c:
        df = pd.read_sql(f"""
            SELECT symbol,
                   SUM(n_trades) AS n_trades,
                   SUM(summe_usd) AS summe_usd,
                   AVG(mittel_pct) AS mittel_pct,
                   AVG(treffer_pct) AS treffer_pct,
                   MAX(bester_pct) AS bester_pct,
                   MIN(schlechtester_pct) AS schlechtester_pct
            FROM symbol_stat {where}
            GROUP BY symbol HAVING SUM(n_trades) >= ?
            ORDER BY summe_usd DESC LIMIT ?
        """, c, params=(*args, min_trades, limit))
    return df


def lauf_loeschen(lauf_id: str) -> None:
    """Entfernt Trades, Equity und Statistik - **nicht** den Zaehlereintrag.

    Der Lauf bleibt in `laeufe` mit `status='verworfen'` stehen. Ein
    Versuch, der aus dem Zaehler verschwindet, senkt die Schwelle
    nachtraeglich - genau die Aufweichung, die §B2 verbietet.
    """
    with _conn() as c:
        for tab in ("trades", "equity", "symbol_stat"):
            c.execute(f"DELETE FROM {tab} WHERE lauf_id=?", (lauf_id,))
        c.execute("UPDATE laeufe SET status='verworfen' WHERE lauf_id=?",
                  (lauf_id,))
