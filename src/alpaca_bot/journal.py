"""Lueckenloses Audit-System: jeder Schritt, jede Entscheidung, jedes Ergebnis.

Der Bot ist die eine Haelfte des Projekts, dieses Modul die andere. Ein
Handelssystem ohne Protokoll kann nicht besser werden, weil niemand sagen
kann, WARUM etwas funktioniert hat oder nicht.

Der entscheidende Punkt ist nicht das Speichern - das ist einfach. Es ist
die **Verknuepfung von Entscheidung und Ergebnis**. Erst wenn jede
Entscheidung ihre Begruendung mitfuehrt und spaeter ihr tatsaechliches
Resultat zugeordnet bekommt, entsteht daraus Lernen statt Buchhaltung:

    Entscheidung  ->  Begruendung  ->  Order  ->  Ergebnis nach 1/5/20 Tagen
         |               |                            |
         +---------------+----------------------------+
                    auswertbar nach Begruendung

Damit lassen sich Fragen beantworten, die sonst unbeantwortbar bleiben:
  * Welche Begruendung war ueber 200 Trades hinweg tatsaechlich richtig?
  * Verliert das System in bestimmten Marktphasen systematisch?
  * Ist die tatsaechliche Ausfuehrung schlechter als im Backtest angenommen?
  * Wurden Entscheidungen getroffen, die der Plan gar nicht vorsah?

Speicherung: SQLite (Standardbibliothek, keine neue Abhaengigkeit) plus
eine JSONL-Datei je Lauf als menschenlesbares Rohprotokoll. SQLite ist die
Auswertungsschicht, JSONL die Sicherung - waere die Datenbank je beschaedigt,
liesse sie sich daraus vollstaendig rekonstruieren.
"""

from __future__ import annotations

import datetime as dt
import json
import platform
import sqlite3
import sys
import traceback
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

import numpy as np
import pandas as pd

from .config import DATA_DIR, RESULTS_DIR

JOURNAL_DB = DATA_DIR / "journal.sqlite"

RAW_DIR = DATA_DIR / "journal_raw"
"""Standardort der JSONL-Sicherung - NUR fuer das Produktivjournal.

Kein `mkdir` mehr beim Import und keine Verwendung mehr im Schreibpfad:
Beides war der Fund vom 23.08.2026 (BEFUNDE §G19 Fund 4). Massgeblich
ist `Journal.raw_dir`, das neben der jeweiligen Datenbank liegt. Diese
Konstante bleibt als Ortsangabe fuer Werkzeuge stehen, die den
Produktivbestand aufraeumen."""


def _json_default(o: Any) -> Any:
    """numpy/pandas-Typen JSON-tauglich machen - sonst bricht das Protokoll."""
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return None if np.isnan(o) else float(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, (np.ndarray,)):
        return o.tolist()
    if isinstance(o, (pd.Timestamp, dt.datetime, dt.date)):
        return o.isoformat()
    if isinstance(o, pd.Series):
        return o.to_dict()
    if isinstance(o, (set, frozenset)):
        return list(o)
    return str(o)


def _dumps(obj: Any) -> str:
    return json.dumps(obj, default=_json_default, ensure_ascii=False)


SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id      TEXT PRIMARY KEY,
    script      TEXT NOT NULL,
    started_at  TEXT NOT NULL,
    ended_at    TEXT,
    status      TEXT,
    config      TEXT,
    environment TEXT,
    error       TEXT
);
CREATE TABLE IF NOT EXISTS steps (
    step_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id    TEXT NOT NULL,
    ts        TEXT NOT NULL,
    kind      TEXT NOT NULL,
    level     TEXT DEFAULT 'info',
    message   TEXT,
    payload   TEXT,
    FOREIGN KEY (run_id) REFERENCES runs(run_id)
);
CREATE TABLE IF NOT EXISTS decisions (
    decision_id TEXT PRIMARY KEY,
    run_id      TEXT NOT NULL,
    ts          TEXT NOT NULL,
    symbol      TEXT NOT NULL,
    action      TEXT NOT NULL,
    conviction  REAL,
    price_at    REAL,
    reasons     TEXT,
    features    TEXT,
    strategy    TEXT,
    executed    INTEGER DEFAULT 0,
    blocked_by  TEXT,
    FOREIGN KEY (run_id) REFERENCES runs(run_id)
);
CREATE TABLE IF NOT EXISTS orders (
    order_id    TEXT PRIMARY KEY,
    decision_id TEXT,
    run_id      TEXT,
    ts          TEXT NOT NULL,
    symbol      TEXT,
    side        TEXT,
    qty         REAL,
    notional    REAL,
    status      TEXT,
    dry_run     INTEGER,
    fill_price  REAL,
    expected_price REAL,
    decision_price REAL,
    slippage_bps REAL,
    decision_drift_bps REAL,
    raw         TEXT
);
CREATE TABLE IF NOT EXISTS outcomes (
    decision_id TEXT NOT NULL,
    horizon     INTEGER NOT NULL,
    fwd_return  REAL,
    evaluated_at TEXT,
    PRIMARY KEY (decision_id, horizon)
);
CREATE INDEX IF NOT EXISTS idx_steps_run ON steps(run_id);
CREATE INDEX IF NOT EXISTS idx_dec_run ON decisions(run_id);
CREATE INDEX IF NOT EXISTS idx_dec_symbol ON decisions(symbol, ts);
"""


class Journal:
    """Zugriff auf das Protokoll. Threadsicher genug fuer den Einzelbetrieb."""

    def __init__(self, path: Path = JOURNAL_DB):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Die JSONL-Sicherung liegt NEBEN ihrer Datenbank, nicht an einem
        # festen Ort. Bis zum 23.08.2026 war `RAW_DIR` ein Modul-Global:
        # `Journal(tmp_path/...)` isolierte die SQLite sauber, der
        # RunLogger schrieb die JSONL aber weiter ins Produktivverzeichnis.
        #
        # Gemessene Folge (BEFUNDE §G19 Fund 4): 2.146 der 2.618 Dateien
        # dort gehoerten zu KEINEM Lauf im Journal - 28,6 % aller Zeilen,
        # 84 Dateien mit Symbol TEST. Das Modul verspricht ueber diese
        # Dateien: "waere die Datenbank je beschaedigt, liesse sie sich
        # daraus vollstaendig rekonstruieren." Eine Rekonstruktion haette
        # Testtrades als echte eingespielt.
        #
        # Dass genau dieser Fehler schon einmal die SQLite traf, steht in
        # `scripts/14_journal_bereinigen.py`: Es existiert, weil Symbol
        # TEST in die Produktivdatenbank lief. Geraeumt wurde damals die
        # Datenbank - das Leck blieb offen.
        self.raw_dir = self.path.parent / "journal_raw"
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.executescript(SCHEMA)
        self._migrate()

    def _migrate(self) -> None:
        """Ergaenzt fehlende Spalten in bereits bestehenden Datenbanken.

        CREATE TABLE IF NOT EXISTS legt eine vorhandene Tabelle nicht neu an -
        neue Spalten muessen also nachtraeglich hinzugefuegt werden. Ohne
        das laeuft jeder Schreibzugriff mit den neuen Feldern auf einen
        Fehler, und zwar erst im Live-Betrieb.
        """
        wanted = {
            "orders": {
                "decision_price": "REAL",
                "decision_drift_bps": "REAL",
                # 'quote' = echte Bid/Ask-Quote zum Ausfuehrungszeitpunkt,
                # 'fallback' = keine Quote verfuegbar, Entscheidungskurs als
                # Notloesung eingesetzt. Ohne dieses Feld liesse sich nicht
                # unterscheiden, ob eine Zeile echte Ausfuehrungsqualitaet
                # misst oder nur Kursdrift seit der Entscheidung - siehe
                # live._reference_price().
                "referenz_quelle": "TEXT",
            },
            # Ohne die Codeversion je Lauf laesst sich spaeter nicht sagen,
            # ob ein schlechteres Ergebnis an einer Aenderung lag oder am
            # Markt - und damit auch nicht, auf welchen Stand man
            # zurueckrollen muesste. Siehe config.code_version().
            "runs": {"code_version": "TEXT"},
        }
        with self._conn() as c:
            for table, columns in wanted.items():
                have = {r[1] for r in c.execute(f"PRAGMA table_info({table})")}
                for name, typ in columns.items():
                    if name not in have:
                        c.execute(f"ALTER TABLE {table} ADD COLUMN {name} {typ}")

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    # --- Lauf-Kontext -----------------------------------------------------
    @contextmanager
    def run(self, script: str, config: dict | None = None) -> Iterator[RunLogger]:
        """Klammert einen kompletten Lauf. Faengt auch Abstuerze ein.

            with Journal().run("05_paper_trade", config=vars(args)) as run:
                run.log("start", symbols=symbols)
        """
        run_id = f"{dt.datetime.now():%Y%m%d_%H%M%S}_{uuid.uuid4().hex[:6]}"
        env = {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "argv": sys.argv,
        }
        from .config import code_version

        with self._conn() as c:
            c.execute(
                "INSERT INTO runs (run_id, script, started_at, status, config,"
                " environment, code_version) VALUES (?,?,?,?,?,?,?)",
                (run_id, script, dt.datetime.now(dt.UTC).isoformat(), "running",
                 _dumps(config or {}), _dumps(env), code_version()),
            )
        logger = RunLogger(self, run_id, script)
        try:
            yield logger
        except BaseException as e:
            self._finish(run_id, "failed", f"{type(e).__name__}: {e}\n{traceback.format_exc()}")
            logger.log("crash", level="error", message=str(e), type=type(e).__name__)
            raise
        else:
            self._finish(run_id, "ok", None)

    def _finish(self, run_id: str, status: str, error: str | None) -> None:
        with self._conn() as c:
            c.execute(
                "UPDATE runs SET ended_at=?, status=?, error=? WHERE run_id=?",
                (dt.datetime.now(dt.UTC).isoformat(), status, error, run_id),
            )

    # --- Auswertung -------------------------------------------------------
    def table(self, name: str, where: str = "", params: tuple = ()) -> pd.DataFrame:
        allowed = {"runs", "steps", "decisions", "orders", "outcomes"}
        if name not in allowed:
            raise ValueError(f"Unbekannte Tabelle {name!r}. Erlaubt: {allowed}")
        sql = f"SELECT * FROM {name}" + (f" WHERE {where}" if where else "")
        with self._conn() as c:
            return pd.read_sql_query(sql, c, params=params)

    def evaluate_outcomes(
        self,
        price_lookup,
        horizons: tuple[int, ...] = (1, 5, 20),
        only_missing: bool = True,
    ) -> int:
        """Ordnet jeder Entscheidung ihr tatsaechliches Ergebnis zu.

        DAS ist der Schritt, der aus Protokoll Lernen macht.

        Args:
            price_lookup: Funktion (symbol, ts, horizon) -> Vorwaertsrendite
                oder None, wenn noch nicht bestimmbar.
        """
        dec = self.table("decisions")
        if dec.empty:
            return 0
        done = self.table("outcomes")
        written = 0

        for _, d in dec.iterrows():
            for h in horizons:
                if only_missing and not done.empty:
                    exists = (
                        (done["decision_id"] == d["decision_id"]) & (done["horizon"] == h)
                    ).any()
                    if exists:
                        continue
                try:
                    r = price_lookup(d["symbol"], pd.Timestamp(d["ts"]), h)
                except Exception:
                    r = None
                if r is None or (isinstance(r, float) and not np.isfinite(r)):
                    continue
                with self._conn() as c:
                    c.execute(
                        "INSERT OR REPLACE INTO outcomes VALUES (?,?,?,?)",
                        (d["decision_id"], int(h), float(r),
                         dt.datetime.now(dt.UTC).isoformat()),
                    )
                written += 1
        return written

    def decision_quality(self, horizon: int = 5,
                         script: str | None = "live_trade") -> pd.DataFrame:
        """Welche Begruendung hat sich tatsaechlich bewaehrt?

        Die wichtigste Auswertung im ganzen System. Sie beantwortet nicht
        "hat der Bot Geld verdient", sondern "welcher Teil seiner Logik
        war richtig" - und nur das laesst sich gezielt verbessern.

        **`script` ist per Vorgabe `"live_trade"`** - also nur der echte
        Bot. Bis zum 22.08.2026 war die Vorgabe `None` (alles), und die
        Trennung musste jeder Aufrufer selbst mitgeben. Von vier
        Aufrufern tat das genau einer:

            scripts/13_tagesbericht.py   script="live_trade"   richtig
            scripts/07_journal_report.py  -                    gemischt
            src/alpaca_bot/selfcheck.py   -                    gemischt

        Im Live-Journal standen zu dem Zeitpunkt 304 echte
        Entscheidungen und 18.118 aus Simulationslaeufen, teils mit
        Zeitstempeln bis 2021 zurueck. **98,4 % der Zeilen waren
        Simulation** - die beiden ungefilterten Berichte beschrieben
        damit praktisch ausschliesslich den Backtest und nannten es die
        Entscheidungsqualitaet des Bots.

        Die gefaehrliche Richtung braucht deshalb jetzt eine bewusste
        Angabe: `script=None` liefert weiterhin alles, aber wer es
        schreibt, hat es gewollt.
        """
        # `script` trennt Live-Betrieb von Simulation. Ohne diese Trennung
        # mischt die Auswertung tausende Backtest-Entscheidungen mit den
        # wenigen echten - und die Kennzahl beschreibt dann die Simulation,
        # nicht das Depot.
        sql = (
            "SELECT d.decision_id, d.symbol, d.action, d.strategy, d.reasons,"
            "       d.conviction, d.executed, o.fwd_return"
            " FROM decisions d"
            " JOIN outcomes o ON d.decision_id = o.decision_id"
            " JOIN runs r ON d.run_id = r.run_id"
            " WHERE o.horizon = ?"
        )
        params: tuple = (horizon,)
        if script:
            sql += " AND r.script = ?"
            params = (horizon, script)
        with self._conn() as c:
            df = pd.read_sql_query(sql, c, params=params)
        if df.empty:
            return pd.DataFrame()

        # Gruppiert wird nach Begruendung UND ihrem Wert.
        #
        # Nach dem blossen Namen zu gruppieren waere sinnlos: Jede
        # Kaufentscheidung enthaelt jeden Schluessel, also bekaemen alle
        # Begruendungen exakt dieselbe Kennzahl. Erst der Wert trennt -
        # "ausstiegsgrund = stop_ausgeloest" gegen "= gewinnziel_erreicht",
        # oder "score 0.9-1.0" gegen "score 0.3-0.5".
        rows = []
        for _, r in df.iterrows():
            try:
                reasons = json.loads(r["reasons"] or "{}")
            except json.JSONDecodeError:
                reasons = {}
            if not isinstance(reasons, dict) or not reasons:
                rows.append({"grund": "(ohne Begruendung)", "wert": "-",
                             "fwd_return": r["fwd_return"]})
                continue
            for key, value in reasons.items():
                rows.append({"grund": key, "wert": _bucket(value),
                             "fwd_return": r["fwd_return"]})

        long = pd.DataFrame(rows)
        if long.empty:
            return pd.DataFrame()

        agg = long.groupby(["grund", "wert"])["fwd_return"].agg(
            n="size", mittel="mean", median="median",
            trefferquote=lambda s: (s > 0).mean(),
        )
        # Gruppen mit sehr wenigen Faellen sind Rauschen.
        agg = agg[agg["n"] >= 5]
        return agg.sort_values(["grund", "mittel"], ascending=[True, False]).round(4)

    def slippage_werte(self, *, nur_bereinigt: bool = True) -> pd.Series:
        """Die EINZELNEN Slippage-Werte je Order - nicht je Symbol.

        `slippage_report()` verdichtet auf Symbole. Fuer den Median ist das
        die falsche Ebene: `docs/BETRIEBSPLAN.md` §3.1 verlangt den
        "Slippage-Median ueber 30+ saubere **Orders**", nicht ueber
        Symbole. Der Unterschied ist nicht akademisch - gemessen am
        22.08.2026 lagen 73 Symbole mit 1 bis 6 Fuellungen vor; ein Median
        ueber Symbol-Mediane gewichtet ein Symbol mit einer Fuellung
        genauso wie eines mit sechs (§G16).

        Beide Funktionen teilen sich bewusst dieselbe Bereinigung
        (`_slippage_basis`): Wuerden sie getrennt filtern, koennten
        Bericht und Pruefung auf verschiedenen Grundmengen rechnen und
        widersprechende Zahlen liefern.
        """
        o = self._slippage_basis(nur_bereinigt=nur_bereinigt, still=True)
        return o["slippage_bps"] if not o.empty else pd.Series(dtype=float)

    def _slippage_basis(self, *, nur_bereinigt: bool = True,
                        still: bool = False) -> pd.DataFrame:
        """Die bereinigte Ordermenge samt gerechneter Slippage.

        Gemeinsame Grundlage von `slippage_report` und `slippage_werte` -
        siehe dort, warum die Trennung gefaehrlich waere.
        """
        o = self.table("orders", "dry_run = 0 AND fill_price IS NOT NULL")
        if o.empty:
            return o

        legacy = o["status"].astype(str).str.endswith(" geschlossen")
        if nur_bereinigt:
            # Positivliste statt Ausschlussliste - der Fund vom 23.08.2026
            # (BEFUNDE §G19 Fund 3).
            #
            # Hier stand bis dahin `o["referenz_quelle"] == "fallback"`.
            # Der Wert existiert in den Daten NICHT ein einziges Mal: Die
            # Spalte kam erst am 04.08.2026 per `_migrate` dazu, alle
            # aelteren Zeilen tragen NULL. Und `NULL != "fallback"` - der
            # Filter, der Zeilen ohne echte Marktquote fernhalten sollte,
            # hat null Zeilen entfernt.
            #
            # Betroffen waren 31 der 162 auswertbaren Orders (19 %), alle
            # aus 28.07.-04.08.2026, darunter genau die Ausreisser, die
            # §G bereits als Datenfehler fuehrt: KGS -1.648, SIMO -1.584,
            # TGTX -1.258 bps. Wirkung auf die Kennzahl:
            #
            #     mit den NULL-Zeilen : n=162  Median +0,0  Mittel -71,7 bps
            #     nur verifizierte Ref: n=131  Median +0,0  Mittel -27,4 bps
            #
            # Der MEDIAN ist unveraendert - der Schluss aus BETRIEBSPLAN
            # §3.1 ("Ausfuehrungsbedingung erfuellt") bleibt also gueltig.
            # Falsch war die Grundmenge, nicht das Urteil. Genau deshalb
            # ist die Positivliste die richtige Form: Eine Ausschlussliste
            # muss jeden schlechten Wert kennen, eine Positivliste nur die
            # guten - und ein spaeter hinzukommender Wert (oder wieder
            # eine neue Spalte voller NULL) faellt automatisch heraus,
            # statt automatisch durchzurutschen.
            VERIFIZIERTE_REFERENZ = {"quote", "quote_verworfen"}
            ohne_referenz = ~o["referenz_quelle"].isin(VERIFIZIERTE_REFERENZ)
            ausgeschlossen = legacy | ohne_referenz
            if ausgeschlossen.any() and not still:
                n_null = int((o["referenz_quelle"].isna() & ~legacy).sum())
                print(f"  [slippage_report] {int(legacy.sum())} Legacy-Zeile(n) "
                      f"(vor dem close_position()-Fix) und "
                      f"{int((ohne_referenz & ~legacy).sum())} Zeile(n) ohne "
                      f"verifizierte Referenzquelle ausgeschlossen von "
                      f"{len(o)} gesamt (davon {n_null} aus der Zeit vor "
                      f"der Spalte `referenz_quelle`, 04.08.2026).")
            o = o[~ausgeschlossen]
        if o.empty:
            return o

        o = o.copy()
        o["slippage_bps"] = (
            (o["fill_price"] - o["expected_price"]) / o["expected_price"] * 10_000
        ).where(o["side"] == "buy", lambda s: -s)
        return o

    def slippage_report(self, *, nur_bereinigt: bool = True) -> pd.DataFrame:
        """Erwarteter gegen tatsaechlichen Ausfuehrungspreis.

        Die Luecke zwischen Backtest und Realitaet. Wenn sie systematisch
        groesser ist als die im Backtest angesetzten Basispunkte, sind alle
        Backtest-Ergebnisse zu optimistisch - und zwar genau um diesen Betrag.

        Zwei Arten von Zeilen verzerren dieses Bild, wenn man sie mitzaehlt:

        1. **Legacy-Datensaetze aus der Zeit vor dem `close_position()`-Fix**
           (Commit 9c26b6a, 03.08.2026). Vorher gab `close_position()` reinen
           Text zurueck ("AMKR geschlossen") statt eines echten Broker-Status
           - genau dieser Text steht noch im `status`-Feld alter Zeilen und
           macht sie strukturell erkennbar, ohne auf ein Datum raten zu
           muessen. Konkret beobachtet: drei AMKR-Verkaeufe vom 28.07.2026
           mit `expected_price=60.74` bei Fuellpreisen um 45-46 - eine
           Verzerrung von ueber +2000 bps, die den gesamten Mittelwert
           uebertoent.
        2. **Zeilen ohne verifizierte Marktquote.** Gezaehlt wird nur, was
           `live._reference_price` ausdruecklich als echten, zeitgleichen
           Marktpreis ausgewiesen hat - `referenz_quelle` in
           {`quote`, `quote_verworfen`}. Alles andere faellt heraus:

             * `fallback` - dort ist `expected_price` der
               Entscheidungskurs, keine Marktbeobachtung. Die "Slippage"
               waere in Wahrheit Kursdrift seit der Entscheidung, genau
               die Vermischung, die dieses Modul verhindern soll.
             * `NULL` - Zeilen aus der Zeit VOR dem 04.08.2026, als es die
               Spalte noch nicht gab. Was ihr `expected_price` bedeutet,
               ist nicht mehr feststellbar. Eine Zeile unbekannter
               Herkunft ist keine Messung (BEFUNDE §G19 Fund 3).

           `quote_verworfen` zaehlt bewusst MIT: Dort wich die Bid/Ask-
           Quote zu stark vom letzten echten Trade ab und wurde durch
           diesen ersetzt (beobachtet bei SIMO/KGS am 04.08.2026, Quote
           11-14 % neben Fuellpreis UND Entscheidungskurs). Der verwendete
           Wert ist dann ein echter, zeitgleicher Marktpreis.

        `nur_bereinigt=True` (Standard) schliesst Legacy-Zeilen und alles
        ohne verifizierte Referenz aus. `False` zeigt alles - auch die
        bekannten Ausreisser - fuer die Nachvollziehbarkeit.
        """
        o = self._slippage_basis(nur_bereinigt=nur_bereinigt)
        if o.empty:
            return pd.DataFrame()
        return (
            o.groupby("symbol")["slippage_bps"]
            .agg(n="size", mittel="mean", median="median", max="max")
            .round(1)
            .sort_values("mittel", ascending=False)
        )

    def integrity_check(self) -> list[str]:
        """Sucht Luecken im Protokoll selbst. Ein Audit-System, dem man nicht
        trauen kann, ist schlimmer als keines."""
        problems = []
        with self._conn() as c:
            n_orphan = c.execute(
                "SELECT COUNT(*) FROM orders WHERE decision_id NOT IN"
                " (SELECT decision_id FROM decisions)"
            ).fetchone()[0]
            if n_orphan:
                problems.append(
                    f"{n_orphan} Order(s) ohne zugehoerige Entscheidung - "
                    "es wurde gehandelt, ohne die Begruendung zu protokollieren."
                )
            n_unfinished = c.execute(
                "SELECT COUNT(*) FROM runs WHERE ended_at IS NULL"
            ).fetchone()[0]
            if n_unfinished:
                problems.append(
                    f"{n_unfinished} Lauf/Laeufe ohne Abschluss - abgestuerzt "
                    "oder hart abgebrochen."
                )
            n_failed = c.execute(
                "SELECT COUNT(*) FROM runs WHERE status='failed'"
            ).fetchone()[0]
            if n_failed:
                problems.append(f"{n_failed} Lauf/Laeufe mit Fehler beendet.")
            # Nur LIVE-Entscheidungen. Simulationslaeufe schreiben
            # zehntausende Zeilen in dieselbe Tabelle; sie brauchen keine
            # `outcomes` und wuerden diese Warnung dauerhaft leuchten
            # lassen (gemessen 22.08.2026: 17.100 davon 18.118 aus
            # Simulationen). Eine Warnung, die immer leuchtet, wird
            # weggeklickt - und dann faellt die echte nicht mehr auf.
            n_no_outcome = c.execute(
                "SELECT COUNT(*) FROM decisions d"
                " JOIN runs r ON d.run_id = r.run_id"
                " WHERE r.script = 'live_trade'"
                "   AND d.decision_id NOT IN (SELECT decision_id FROM outcomes)"
            ).fetchone()[0]
            if n_no_outcome:
                problems.append(
                    f"{n_no_outcome} Entscheidung(en) ohne bewertetes Ergebnis - "
                    "evaluate_outcomes() ausfuehren, sonst wird daraus nicht gelernt."
                )
        return problems

    def summary(self) -> str:
        """Der Protokollkopf - LIVE und Simulation getrennt ausgewiesen.

        **Warum getrennt (23.08.2026, BEFUNDE §G19 Fund 8).** Hier stand
        vorher eine einzige Spalte ueber alle Quellen:

            Entscheidungen  :  18425  (183 ausgefuehrt)

        Das las sich wie eine Ausfuehrungsquote von 1 %. In Wahrheit
        stammten 18.118 der Zeilen aus vier Simulationslaeufen mit
        rueckdatierten Zeitstempeln bis 2021 (§G13 Fund 1), die nie
        ausgefuehrt werden sollten. §G13 hat `decision_quality` und
        `integrity_check` auf `live_trade` gefiltert - der Kopf DIESES
        Berichts blieb ungefiltert. Er stand damit direkt ueber einem
        Befund, der korrekt 62 statt 17.100 meldete, ohne dass der
        Unterschied erklaerbar war.

        `Zeitraum` verschaerfte es: Er kommt aus `runs.started_at` (echte
        Uhrzeit) und zeigte 2026-07-28 bis 2026-08-21, waehrend die
        Entscheidungen bis 2021 zurueckreichen.
        """
        runs = self.table("runs")
        dec = self.table("decisions")
        orders = self.table("orders")
        out = self.table("outcomes")

        live_runs = set(runs.loc[runs["script"] == "live_trade", "run_id"]) \
            if not runs.empty else set()
        dec_live = dec[dec["run_id"].isin(live_runs)] if not dec.empty else dec
        n_sim = len(dec) - len(dec_live)

        lines = [
            "=" * 62,
            "  PROTOKOLL-UEBERSICHT",
            "=" * 62,
            f"  Laeufe          : {len(runs):>6}"
            + (f"  ({(runs['status'] == 'failed').sum()} fehlgeschlagen)" if len(runs) else ""),
            f"  Schritte        : {len(self.table('steps')):>6}",
            f"  Entscheidungen  : {len(dec_live):>6}  LIVE"
            + (f"  ({int(dec_live['executed'].sum())} ausgefuehrt)"
               if len(dec_live) else ""),
            f"  + aus Simulation: {n_sim:>6}  (zaehlen in KEINER Live-Auswertung"
            f" mit, §G13)",
            f"  Orders          : {len(orders):>6}"
            + (f"  ({int((orders['dry_run'] == 0).sum())} echt)" if len(orders) else ""),
            f"  Bewertete Ergeb.: {len(out):>6}",
        ]
        if not runs.empty:
            lines.append(f"  Zeitraum (Laeufe): {runs['started_at'].min()[:10]} "
                         f"bis {runs['started_at'].max()[:10]}")
        # Der Entscheidungszeitraum ist NICHT der Laufzeitraum. Simulationen
        # schreiben rueckdatierte Zeitstempel; ohne diese Zeile sieht das
        # Protokoll drei Wochen alt aus, obwohl es Zeilen von 2021 traegt.
        if not dec.empty and n_sim:
            ts = pd.to_datetime(dec["ts"], format="mixed", utc=True,
                                errors="coerce").dropna()
            if not ts.empty:
                lines.append(f"  Zeitraum (Entsch.): {ts.min().date()} "
                             f"bis {ts.max().date()}  <- reicht durch die "
                             f"Simulationen weiter zurueck")
        problems = self.integrity_check()
        lines.append("")
        if problems:
            lines.append("  BEFUNDE:")
            lines.extend(f"    - {p}" for p in problems)
        else:
            lines.append("  Keine Luecken im Protokoll gefunden.")
        return "\n".join(lines)


@dataclass
class RunLogger:
    """Schreibzugriff waehrend eines Laufs."""

    journal: Journal
    run_id: str
    script: str
    _raw: Any = field(default=None, init=False)

    def __post_init__(self):
        self._raw = (self.journal.raw_dir
                     / f"{self.run_id}.jsonl").open("a", encoding="utf-8")

    # --- Schritte ---------------------------------------------------------
    def log(self, kind: str, message: str = "", level: str = "info", **payload) -> None:
        """Protokolliert einen beliebigen Arbeitsschritt.

            run.log("daten_geladen", symbols=len(syms), bars=len(df))
        """
        ts = dt.datetime.now(dt.UTC).isoformat()
        with self.journal._conn() as c:
            c.execute(
                "INSERT INTO steps (run_id, ts, kind, level, message, payload)"
                " VALUES (?,?,?,?,?,?)",
                (self.run_id, ts, kind, level, message, _dumps(payload)),
            )
        self._write_raw({"ts": ts, "kind": kind, "level": level,
                         "message": message, **payload})

    def warn(self, message: str, **payload) -> None:
        self.log("warnung", message, level="warning", **payload)

    def error(self, message: str, **payload) -> None:
        self.log("fehler", message, level="error", **payload)

    # --- Entscheidungen ---------------------------------------------------
    def decision(
        self,
        symbol: str,
        action: str,
        *,
        reasons: dict[str, Any],
        features: dict[str, Any] | pd.Series | None = None,
        conviction: float | None = None,
        price: float | None = None,
        strategy: str = "",
        executed: bool = False,
        blocked_by: str | None = None,
        ts: pd.Timestamp | str | None = None,
    ) -> str:
        """Protokolliert eine Handelsentscheidung MIT Begruendung.

        `reasons` ist kein Freitext, sondern ein Dictionary benannter
        Gruende mit ihren Werten:

            reasons={"trend_ueber_sma200": True, "rsi": 34.2,
                     "news_z": 3.1, "insider_kaeufe_30d": 2}

        Nur so laesst sich spaeter auswerten, WELCHER Grund funktioniert
        hat. Ein Freitext-Log kann das nicht.

        Wichtig: Auch NICHT ausgefuehrte Entscheidungen gehoeren hierher.
        Die von einer Risikoregel blockierten Trades sind oft die
        lehrreichsten - waeren sie gut gewesen, ist die Regel zu streng.

        `ts` ueberschreibt den Zeitstempel. Noetig, wenn Entscheidungen
        aus einem Backtest oder einer Ereignisstudie protokolliert werden -
        dort gehoert der historische Zeitpunkt ins Protokoll, nicht der
        Zeitpunkt der Auswertung. Sonst findet `evaluate_outcomes` keine
        Kurse und das Lernen bleibt aus.
        """
        decision_id = uuid.uuid4().hex
        ts = (
            pd.Timestamp(ts).isoformat()
            if ts is not None
            else dt.datetime.now(dt.UTC).isoformat()
        )
        feat = (
            features.to_dict() if isinstance(features, pd.Series) else (features or {})
        )
        with self.journal._conn() as c:
            c.execute(
                "INSERT INTO decisions (decision_id, run_id, ts, symbol, action,"
                " conviction, price_at, reasons, features, strategy, executed, blocked_by)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (decision_id, self.run_id, ts, symbol, action, conviction, price,
                 _dumps(reasons), _dumps(feat), strategy, int(executed), blocked_by),
            )
        self._write_raw({"ts": ts, "kind": "entscheidung", "decision_id": decision_id,
                         "symbol": symbol, "action": action, "reasons": reasons,
                         "executed": executed, "blocked_by": blocked_by})
        return decision_id

    def order(
        self,
        decision_id: str | None,
        *,
        symbol: str,
        side: str,
        status: str,
        order_id: str | None = None,
        qty: float | None = None,
        notional: float | None = None,
        dry_run: bool = True,
        expected_price: float | None = None,
        decision_price: float | None = None,
        fill_price: float | None = None,
        referenz_quelle: str | None = None,
        raw: Any = None,
    ) -> None:
        """Protokolliert eine Order und verknuepft sie mit ihrer Entscheidung.

        Zwei getrennte Bezugspreise, weil sie zwei verschiedene Dinge messen:

            expected_price   Marktkurs im Moment der Order  -> Slippage,
                             also die AUSFUEHRUNGSqualitaet
            decision_price   Kurs, auf dem die Entscheidung beruhte (meist
                             der Schlusskurs des Vortages) -> Kursdrift
                             zwischen Entscheidung und Ausfuehrung

        Beides zu vermischen war ein Fehler: Die Drift ueber Nacht wurde als
        Slippage ausgewiesen und ergab Werte wie -2452 Basispunkte.

        `referenz_quelle` ('quote'|'quote_verworfen'|'fallback', siehe
        live._reference_price) haelt fest, ob `expected_price` aus einer
        echten, plausiblen Bid/Ask-Quote stammt, aus dem letzten Trade (weil
        die Quote selbst unglaubwuerdig war), oder nur der Entscheidungskurs
        als Notloesung war. `slippage_report()` nutzt das, um Kursdrift
        nicht faelschlich als Slippage zu zaehlen.
        """
        oid = order_id or f"local_{uuid.uuid4().hex[:10]}"

        slip = None
        if expected_price and fill_price and expected_price > 0:
            slip = (fill_price - expected_price) / expected_price * 10_000
            if side == "sell":
                slip = -slip

        drift = None
        if decision_price and fill_price and decision_price > 0:
            drift = (fill_price - decision_price) / decision_price * 10_000
            if side == "sell":
                drift = -drift

        ts = dt.datetime.now(dt.UTC).isoformat()
        with self.journal._conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO orders (order_id, decision_id, run_id, ts,"
                " symbol, side, qty, notional, status, dry_run, fill_price,"
                " expected_price, decision_price, slippage_bps, decision_drift_bps,"
                " referenz_quelle, raw) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                # `raw` bleibt SQL-NULL, wenn nichts uebergeben wurde -
                # NICHT der String 'null'. Bis zum 23.08.2026 stand
                # `_dumps(raw)` hier unbedingt, und weil kein Aufrufer je
                # ein `raw` uebergab, trugen 183 von 183 echten Zeilen
                # den Text 'null' (BEFUNDE §G19 Fund 5). Eine Spalte, die
                # zu 100 % gefuellt aussieht und nichts enthaelt, ist
                # genau die Falle aus §G13 Fund 2: "Eine Null sieht wie
                # eine Messung aus. Ein NULL waere aufgefallen."
                # Gefuellt wird sie beim Broker-Abgleich
                # (`live.reconcile_fills`), wo die Gegenseite vorliegt.
                (oid, decision_id, self.run_id, ts, symbol, side, qty, notional,
                 status, int(dry_run), fill_price, expected_price, decision_price,
                 slip, drift, referenz_quelle,
                 _dumps(raw) if raw is not None else None),
            )
            if decision_id:
                c.execute(
                    "UPDATE decisions SET executed=? WHERE decision_id=?",
                    (int(not dry_run), decision_id),
                )
        self._write_raw({"ts": ts, "kind": "order", "order_id": oid,
                         "decision_id": decision_id, "symbol": symbol, "side": side,
                         "status": status, "dry_run": dry_run})

    def snapshot(self, name: str, df: pd.DataFrame) -> Path:
        """Sichert eine Tabelle (Signale, Kennzahlen, Ranking) zum Lauf.

        Damit laesst sich spaeter rekonstruieren, was das System zum
        Zeitpunkt der Entscheidung tatsaechlich gesehen hat.
        """
        path = self.journal.raw_dir / f"{self.run_id}__{name}.csv"
        df.to_csv(path)
        self.log("snapshot", name, datei=str(path), zeilen=len(df))
        return path

    _raw_defekt: bool = field(default=False, init=False)
    """Ist die JSONL-Sicherung fuer diesen Lauf ausgefallen?"""

    def _write_raw(self, obj: dict) -> None:
        """Schreibt ins JSONL-Rohprotokoll - die zweite Aufzeichnung.

        **Warum das nicht still scheitern darf (§G18).** Das Modul
        beschreibt die Aufgabenteilung so: "SQLite ist die
        Auswertungsschicht, JSONL die Sicherung - waere die Datenbank je
        beschaedigt, liesse sie sich daraus vollstaendig rekonstruieren."

        Ein `except: pass` machte daraus eine Sicherung, die man fuer
        vorhanden haelt, waehrend sie nicht mehr geschrieben wird - genau
        die Fehlerklasse aus §G15 (gebaut, laeuft nicht, meldet sich
        nie). Ein voller Datentraeger oder eine entzogene
        Schreibberechtigung faellt sonst erst auf, wenn man die Sicherung
        BRAUCHT.

        Der Ausfall darf den Handel weiterhin nicht stoppen - deshalb
        wird gemeldet, nicht geworfen. Und nur EINMAL je Lauf: Eine
        Meldung bei jeder Zeile waere Laerm, und Laerm wird ueberlesen.
        """
        try:
            self._raw.write(_dumps(obj) + "\n")
            self._raw.flush()
        except (OSError, ValueError) as e:
            if not self._raw_defekt:
                self._raw_defekt = True
                print(f"  [Journal] ROHPROTOKOLL FAELLT AUS: "
                      f"{type(e).__name__}: {e}. Die SQLite-Aufzeichnung "
                      f"laeuft weiter, aber die JSONL-Sicherung dieses "
                      f"Laufs ist unvollstaendig.")


def _bucket(value) -> str:
    """Fasst einen Begruendungswert zu einer auswertbaren Gruppe zusammen.

    Zahlen werden in Baender gelegt, weil jeder einzelne Messwert sonst
    seine eigene Gruppe mit n=1 bilden wuerde - daraus laesst sich nichts
    lernen. Wahrheitswerte und Text bleiben, wie sie sind.
    """
    if isinstance(value, bool):
        return "ja" if value else "nein"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        v = float(value)
        if not np.isfinite(v):
            return "n/a"
        if -1e-9 <= v <= 1 + 1e-9:
            lo = int(v * 5) / 5  # Fuenftel-Baender fuer 0..1-Werte
            return f"{min(lo, 0.8):.1f}-{min(lo + 0.2, 1.0):.1f}"
        if abs(v) < 1:
            return f"{'+' if v >= 0 else '-'}{abs(v):.0%}-Bereich"
        return f"{'niedrig' if abs(v) < 10 else 'mittel' if abs(v) < 100 else 'hoch'}"
    return str(value)[:30]


def make_price_lookup(bars: pd.DataFrame):
    """Baut die `price_lookup`-Funktion fuer `evaluate_outcomes` aus Bar-Daten."""

    def lookup(symbol: str, ts: pd.Timestamp, horizon: int) -> float | None:
        try:
            df = (
                bars.xs(symbol, level="symbol")
                if isinstance(bars.index, pd.MultiIndex)
                else bars
            )
        except KeyError:
            return None
        idx = pd.DatetimeIndex(df.index)
        t = pd.Timestamp(ts)
        if t.tz is None:
            t = t.tz_localize("UTC")
        if idx.tz is None:
            idx = idx.tz_localize("UTC")
        pos = int(idx.searchsorted(t))
        if pos >= len(df) or pos + horizon >= len(df):
            return None
        close = df["close"].astype(float)
        return float(close.iloc[pos + horizon] / close.iloc[pos] - 1)

    return lookup
