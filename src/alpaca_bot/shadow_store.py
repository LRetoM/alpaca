"""Persistenz des Schattenbetriebs: shadow.sqlite und ihr Schema.

Die unterste Schicht - sie importiert nichts aus den anderen
Schattenmodulen. Fuenfzehn Tabellen: Vorhersagen, Ergebnisse, die
Spiegeldepots je Bot, Flottenregistrierung, Musterspeicher,
Versuchszaehler.

Bewusst getrennt von `journal.sqlite`: Bei ~1.000 Schattenvorhersagen
taeglich gegen ~60 echte Entscheidungen waere jede vergessene
`WHERE script=`-Bedingung eine still falsche Kennzahl - und genau
dieser Mechanismus hat schon einmal versagt (§G13 Fund 1).

**Herkunft: Aufteilung von `shadow.py` am 23.08.2026 (BEFUNDE §G20).**
Der Schattenbetrieb lag in EINER Datei mit 2.339 Zeilen und fuenf
Verantwortungen. Der Code in diesem Modul wurde dabei **unveraendert**
verschoben - kein Ausdruck, keine Zeile Logik wurde angefasst. Nachgewiesen
ueber den Bytecode jeder Funktion, nicht behauptet (`scripts/29_umzug_pruefen.py`).
"""


from __future__ import annotations

import datetime as dt
import json
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import numpy as np
import pandas as pd

from .config import DATA_DIR
from .engine import Position


SHADOW_DB = DATA_DIR / "shadow.sqlite"

SCHEMA = """
CREATE TABLE IF NOT EXISTS shadow_runs (
    run_id       TEXT PRIMARY KEY,
    schritt      TEXT NOT NULL,
    started_at   TEXT NOT NULL,
    ended_at     TEXT,
    status       TEXT,
    as_of        TEXT,
    data_source  TEXT,
    n_symbols    INTEGER,
    universum    TEXT,
    engine_config TEXT,
    code_version TEXT NOT NULL,
    fehler       TEXT
);
CREATE TABLE IF NOT EXISTS predictions (
    pred_id          TEXT PRIMARY KEY,
    run_id           TEXT NOT NULL,
    bot_id           TEXT NOT NULL,
    buch             TEXT NOT NULL,
    as_of            TEXT NOT NULL,
    decided_at       TEXT NOT NULL,
    symbol           TEXT NOT NULL,
    aktion           TEXT NOT NULL DEFAULT 'buy',
    rang             INTEGER,
    score            REAL,
    decision_price   REAL NOT NULL,
    entry_date       TEXT,
    entry_price_open REAL,
    entry_price      REAL,
    entry_price_eff  REAL,
    entry_timing     TEXT,
    planned_stop     REAL,
    planned_target   REAL,
    planned_hold_days INTEGER,
    notional         REAL,
    reasons          TEXT,
    regime_markt     TEXT,
    regime_vola      TEXT,
    regime_breite    REAL,
    atr_pct          REAL,
    liquiditaet      REAL,
    -- Nachrichten-Kontext (Plan §10.2a/b). Seit 03.08.2026 IMMER aktiv, Teil
    -- des normalen Starts fuer beide Bots (Handel und Schatten) - kein Flag
    -- mehr noetig. news_z/news_5d/news_erstabdeckung/news_tage_her sind die
    -- Werte, die tatsaechlich in den Score eingeflossen sind (ReversalWeights.
    -- news); news_ereignis/news_ton sind reine Zusatzbeobachtung ohne
    -- Wirkung auf die Entscheidung (siehe _news_kontext). news_aktiv trennt
    -- Entscheidungen VOR/NACH der News-Einfuehrung im Auswertung.
    news_z           REAL,
    news_5d          REAL,
    news_erstabdeckung REAL,
    news_tage_her    REAL,
    news_ereignis    TEXT,
    news_ton         REAL,
    news_aktiv       INTEGER,
    wuerde_gehandelt INTEGER DEFAULT 0,
    code_version     TEXT NOT NULL,
    nachgetragen     INTEGER DEFAULT 0,
    UNIQUE (as_of, symbol, bot_id, buch)
);
CREATE TABLE IF NOT EXISTS shadow_outcomes (
    pred_id       TEXT PRIMARY KEY,
    exit_date     TEXT,
    exit_price    REAL,
    exit_price_eff REAL,
    exit_reason   TEXT,
    return_pct    REAL,
    return_brutto REAL,
    kosten        REAL,
    bars_held     INTEGER,
    mae_pct       REAL,
    mfe_pct       REAL,
    fwd_1d REAL, fwd_3d REAL, fwd_5d REAL, fwd_10d REAL, fwd_20d REAL,
    bench_fwd_5d     REAL,
    universum_fwd_5d REAL,
    ueberschuss_5d   REAL,
    ziel_erreicht INTEGER,
    stop_erreicht INTEGER,
    evaluated_at  TEXT,
    data_check    TEXT
);
CREATE INDEX IF NOT EXISTS idx_pred_asof   ON predictions(as_of);
CREATE INDEX IF NOT EXISTS idx_pred_symbol ON predictions(symbol);
CREATE INDEX IF NOT EXISTS idx_pred_bot    ON predictions(bot_id, buch);

-- ---------------------------------------------------------------- Spiegelbuch
-- Virtuelles Depot je Bot. Anders als beim Live-Bot gibt es hier keinen
-- Broker, der die Wahrheit haelt - diese Tabellen SIND die Wahrheit.
CREATE TABLE IF NOT EXISTS shadow_portfolio (
    bot_id       TEXT NOT NULL,
    symbol       TEXT NOT NULL,
    qty          REAL NOT NULL,
    entry_price  REAL NOT NULL,
    entry_date   TEXT NOT NULL,
    stop_price   REAL NOT NULL,
    target_price REAL NOT NULL,
    bars_held    INTEGER DEFAULT 0,
    high_water   REAL NOT NULL,
    entry_score  REAL,
    reasons      TEXT,
    PRIMARY KEY (bot_id, symbol)
);
CREATE TABLE IF NOT EXISTS shadow_cash (
    bot_id      TEXT PRIMARY KEY,
    cash        REAL NOT NULL,
    equity      REAL NOT NULL,
    startwert   REAL NOT NULL,
    letzter_tag TEXT,
    updated_at  TEXT NOT NULL
);
-- Entschieden wird am Abend von T, ausgefuehrt am Morgen von T+1. Zwischen
-- beiden Zeitpunkten muss die Absicht einen Prozessneustart ueberleben -
-- sonst gingen genau die Entscheidungen verloren, die noch nichts bewirkt
-- haben, und das Spiegelbuch wiche vom Live-Verhalten ab.
CREATE TABLE IF NOT EXISTS spiegel_pending (
    bot_id        TEXT NOT NULL,
    symbol        TEXT NOT NULL,
    aktion        TEXT NOT NULL,
    notional      REAL,
    stop_price    REAL,
    target_price  REAL,
    score         REAL,
    reasons       TEXT,
    -- HANDELSTAG der Entscheidung, nicht die Wanduhrzeit. Wird als `as_of`
    -- der spaeteren Vorhersage gespeichert; ohne ihn stuende beim Nachholen
    -- fehlender Tage der letzte Stichtag dort, und der Einstieg laege
    -- formal VOR der Entscheidung - ein scheinbares Datenleck.
    as_of         TEXT NOT NULL,
    entschieden_am TEXT NOT NULL,
    PRIMARY KEY (bot_id, symbol, aktion)
);
-- Eigene Ausstiegshistorie fuer die Sperrfrist. Der Live-Bot nutzt dafuer
-- state.sqlite; sie hier mitzubenutzen wuerde Live-Zustand in den Schatten
-- lecken und beide Buecher verfaelschen.
CREATE TABLE IF NOT EXISTS shadow_exits (
    bot_id      TEXT NOT NULL,
    symbol      TEXT NOT NULL,
    exit_date   TEXT NOT NULL,
    exit_price  REAL,
    exit_reason TEXT,
    entry_price REAL,
    return_pct  REAL,
    bars_held   INTEGER,
    PRIMARY KEY (bot_id, symbol, exit_date)
);
CREATE TABLE IF NOT EXISTS equity_kurve (
    bot_id TEXT NOT NULL,
    tag    TEXT NOT NULL,
    equity REAL NOT NULL,
    cash   REAL,
    n_pos  INTEGER,
    PRIMARY KEY (bot_id, tag)
);

-- ---------------------------------------------------------------- Flotte
CREATE TABLE IF NOT EXISTS bots (
    bot_id        TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    familie       TEXT NOT NULL,
    basis_bot     TEXT,
    achse         TEXT,
    wert          TEXT,
    config_json   TEXT NOT NULL,
    hypothese     TEXT NOT NULL,
    quelle        TEXT,
    angemeldet_am TEXT NOT NULL,
    aktiv_ab      TEXT,
    aktiv_bis     TEXT,
    status        TEXT NOT NULL,
    startkapital  REAL DEFAULT 100000
);
-- Zaehlt ALLE je gestarteten Versuche, auch verworfene. Einen Verlierer zu
-- loeschen und zu vergessen ist der haeufigste Weg der Selbsttaeuschung.
CREATE TABLE IF NOT EXISTS versuchszaehler (
    id             INTEGER PRIMARY KEY CHECK (id = 1),
    n_bots_gesamt  INTEGER DEFAULT 0,
    n_hypothesen   INTEGER DEFAULT 0,
    n_vergleiche   INTEGER DEFAULT 0,
    aktualisiert   TEXT
);

-- Kleine Schluessel/Wert-Ablage fuer Laufzustaende, die keine eigene
-- Tabelle rechtfertigen (z. B. bis zu welchem Stichtag der Lernschritt
-- gelaufen ist). Bewusst getrennt von `scoreboard`, das ein festes
-- Auswertungsschema hat.
CREATE TABLE IF NOT EXISTS merker (
    schluessel  TEXT PRIMARY KEY,
    wert        TEXT,
    geaendert   TEXT
);

-- ---------------------------------------------------------------- Auswertung
CREATE TABLE IF NOT EXISTS scoreboard (
    kohorte       TEXT NOT NULL,
    bot_id        TEXT NOT NULL,
    buch          TEXT NOT NULL,
    regime        TEXT NOT NULL,
    code_version  TEXT,
    n_vorhersagen INTEGER,
    n_tage        INTEGER,
    ic_5d         REAL,
    ic_t_stat     REAL,
    trefferquote  REAL,
    basisrate     REAL,
    ueberschuss   REAL,
    rendite_netto REAL,
    umschlag      REAL,
    kalibrierung  REAL,
    erstellt_am   TEXT,
    PRIMARY KEY (kohorte, bot_id, buch, regime)
);
CREATE TABLE IF NOT EXISTS vergleiche (
    kohorte     TEXT NOT NULL,
    bot_a       TEXT NOT NULL,
    bot_b       TEXT NOT NULL,
    n_tage      INTEGER,
    diff_mittel REAL,
    diff_std    REAL,
    t_wert      REAL,
    schwelle    REAL,
    belastbar   INTEGER,
    attribution TEXT,
    erstellt_am TEXT,
    PRIMARY KEY (kohorte, bot_a, bot_b)
);

-- ---------------------------------------------------------------- Musterspeicher
CREATE TABLE IF NOT EXISTS muster (
    muster_id          TEXT PRIMARY KEY,
    beschreibung       TEXT NOT NULL,
    bedingung          TEXT NOT NULL,
    wirkung            TEXT NOT NULL,
    entdeckt_am        TEXT NOT NULL,
    entdeckt_aus       TEXT NOT NULL,
    n_tage             INTEGER,
    effekt             REAL,
    t_wert             REAL,
    schwelle           REAL,
    sperrzone_effekt   REAL,
    status             TEXT NOT NULL,
    zuletzt_geprueft   TEXT,
    zuletzt_bestaetigt TEXT,
    zerfallen_seit     TEXT,
    fehlschlaege       INTEGER DEFAULT 0,
    angewendet_in      TEXT
);

-- ---------------------------------------------------------------- Hypothesen
CREATE TABLE IF NOT EXISTS hypothesen (
    hyp_id              TEXT PRIMARY KEY,
    behauptung          TEXT NOT NULL,
    quelle              TEXT NOT NULL,
    quelle_typ          TEXT NOT NULL,
    veroeffentlicht     TEXT,
    behaupteter_effekt  TEXT,
    erfasst_am          TEXT NOT NULL,
    operationalisierung TEXT,
    testbar             INTEGER,
    hist_ic             REAL,
    hist_t              REAL,
    hist_ic_vor_veroeff REAL,
    hist_ic_nach_veroeff REAL,
    fwd_ic              REAL,
    fwd_t               REAL,
    fwd_n_tage          INTEGER,
    status              TEXT NOT NULL,
    entschieden_am      TEXT
);
"""

def code_version() -> str:
    """Git-Commit dieses Laufs. Delegiert an `config.code_version`.

    Stand frueher hier mit `cwd=DATA_DIR.parent` - nach dem Umzug der
    Datenbanken nach ~/Library/Application Support zeigte das auf ein
    Verzeichnis ohne Git und lieferte stumm 'unbekannt' (zwei Drittel
    aller Vorhersagen betroffen). Jetzt eine gemeinsame Quelle fuer
    Schatten- UND Handelspfad, damit beide dieselbe Version melden und
    vergleichbar bleiben.
    """
    from .config import code_version as _cv

    return _cv()

def _json(obj) -> str:
    def default(o):
        if isinstance(o, (np.integer,)):
            return int(o)
        if isinstance(o, (np.floating,)):
            return None if np.isnan(o) else float(o)
        if isinstance(o, (np.bool_,)):
            return bool(o)
        if isinstance(o, (pd.Timestamp, dt.datetime, dt.date)):
            return o.isoformat()
        return str(o)

    return json.dumps(obj, default=default, ensure_ascii=False)

# ---------------------------------------------------------------------------
# Speicher
# ---------------------------------------------------------------------------
class ShadowStore:
    """Zugriff auf shadow.sqlite. Bewusst getrennt von Journal und Store."""

    def __init__(self, path: Path = SHADOW_DB):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.sicherung_dir = self.path.parent / "shadow_sicherung"
        with self._conn() as c:
            c.executescript(SCHEMA)
        self._migrate()

    def sichern(self, behalten: int = 7) -> Path | None:
        """Legt eine konsistente Kopie der Schattendatenbank an.

        **Der Anlass (23.08.2026, BEFUNDE §G19 Fund 7).** Hier stand
        vorher `RAW_DIR.mkdir(...)` - ein Verzeichnis `shadow_raw`, das
        bei jedem `ShadowStore()` angelegt und **nie beschrieben** wurde.
        Seit dem 31.07.2026 leer. Es sah aus wie das Gegenstueck zu
        `journal_raw`, war aber keines.

        Das ist nicht nur unordentlich. `shadow.sqlite` traegt 26 MB:
        20.690 Vorhersagen, die gesamte Flottenmessung, den
        Musterspeicher und den Versuchszaehler - die Datengrundlage der
        Entscheidung vom 10.10.2026. Dafuer gab es keinerlei Sicherung,
        nur ein leeres Verzeichnis, das eine vortaeuschte.

        **Warum eine SQLite-Kopie und kein JSONL.** `journal.py` schreibt
        JSONL, weil dort jede Zeile einzeln entsteht und der Verlust der
        LAUFENDEN Aufzeichnung das Risiko ist. Der Schatten schreibt in
        Schueben, einmal je Handelstag. Ein `.backup()` liefert dafuer
        das Bessere: eine transaktionskonsistente, sofort benutzbare
        Datenbank statt eines Rohstroms, den erst jemand zurueckspielen
        muesste. Und es ist die einzige Form von Sicherung, die auch
        wirklich einmal geprueft wurde - `sqlite3` uebernimmt das.

        `behalten` begrenzt den Platzbedarf. Sieben Staende decken eine
        Woche ab; wer einen Schaden laenger als eine Woche nicht bemerkt,
        hat ein anderes Problem als die Zahl der Kopien.

        Gibt den Pfad der Kopie zurueck, oder `None`, wenn die Sicherung
        fehlschlug. **Geworfen wird nicht:** Der Ausfall der Sicherung
        darf den Schattenbetrieb nicht stoppen - dieselbe Abwaegung wie
        bei `journal._write_raw` (§G18 Fund 2). Gemeldet wird er
        trotzdem, denn eine Sicherung, die still ausfaellt, ist genau
        das, was hier gerade behoben wird.
        """
        import shutil

        try:
            self.sicherung_dir.mkdir(parents=True, exist_ok=True)
            stempel = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
            ziel = self.sicherung_dir / f"shadow_{stempel}.sqlite"

            # `sqlite3.Connection.backup` statt `shutil.copy`: Eine
            # Dateikopie waehrend eines laufenden Schreibvorgangs kann
            # eine halb geschriebene Transaktion erwischen. Die
            # Sicherung waere dann da und unbrauchbar - schlimmer als
            # keine, weil man sich auf sie verlaesst.
            quelle = sqlite3.connect(self.path, timeout=30)
            kopie = sqlite3.connect(ziel)
            try:
                quelle.backup(kopie)
            finally:
                kopie.close()
                quelle.close()

            staende = sorted(self.sicherung_dir.glob("shadow_*.sqlite"))
            for alt in staende[:-behalten] if behalten > 0 else []:
                alt.unlink(missing_ok=True)
            return ziel
        except (OSError, sqlite3.Error, shutil.Error) as e:
            print(f"  [Schatten] SICHERUNG FAELLT AUS: {type(e).__name__}: {e}. "
                  f"Der Schattenbetrieb laeuft weiter, aber shadow.sqlite "
                  f"hat derzeit keine Kopie.")
            return None

    def _migrate(self) -> None:
        """Ergaenzt fehlende Spalten in bereits bestehenden Datenbanken.

        `CREATE TABLE IF NOT EXISTS` legt eine vorhandene Tabelle nicht neu an -
        neue Spalten muessen nachtraeglich hinzu. Ohne das laeuft jeder
        Schreibzugriff mit den neuen Feldern auf einen Fehler, und zwar erst
        im laufenden Betrieb. Dieselbe Vorsorge wie in `journal.py`.
        """
        gewuenscht = {
            "predictions": {
                "aktion": "TEXT DEFAULT 'buy'",
                "news_z": "REAL", "news_5d": "REAL",
                "news_erstabdeckung": "REAL", "news_tage_her": "REAL",
                "news_ereignis": "TEXT", "news_ton": "REAL",
                "news_aktiv": "INTEGER",
            },
            "shadow_cash": {"letzter_tag": "TEXT"},
            "shadow_runs": {"universum": "TEXT", "engine_config": "TEXT"},
            "spiegel_pending": {"as_of": "TEXT"},
        }
        with self._conn() as c:
            for tabelle, spalten in gewuenscht.items():
                da = {r[1] for r in c.execute(f"PRAGMA table_info({tabelle})")}
                if not da:
                    continue
                for name, typ in spalten.items():
                    if name not in da:
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

    # --- Laeufe ---
    def start_run(self, schritt: str, *, as_of=None, n_symbols=None,
                  universum: str | None = None, engine: dict | None = None) -> str:
        """Beginnt einen Lauf.

        `engine` sind die VOLLSTAENDIGEN geltenden Regeln, nicht nur ein paar
        Eckwerte. Ohne sie laesst sich spaeter nicht pruefen, ob eine
        Vorhersage den DAMALS geltenden Regeln entsprach - Parameter aendern
        sich, und ein Abgleich gegen die heutige Konfiguration wuerde alte
        Vorhersagen faelschlich als abweichend ausweisen.
        """
        run_id = f"{dt.datetime.now():%Y%m%d_%H%M%S}_{uuid.uuid4().hex[:6]}"
        with self._conn() as c:
            c.execute(
                "INSERT INTO shadow_runs (run_id, schritt, started_at, status,"
                " as_of, data_source, n_symbols, universum, engine_config,"
                " code_version) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (run_id, schritt, dt.datetime.now(dt.UTC).isoformat(), "laeuft",
                 str(as_of) if as_of is not None else None, "yfinance",
                 n_symbols, universum, _json(engine) if engine else None,
                 code_version()),
            )
        return run_id

    def finish_run(self, run_id: str, status: str, fehler: str | None = None) -> None:
        with self._conn() as c:
            c.execute(
                "UPDATE shadow_runs SET ended_at=?, status=?, fehler=? WHERE run_id=?",
                (dt.datetime.now(dt.UTC).isoformat(), status, fehler, run_id),
            )

    # --- Vorhersagen ---
    def save_prediction(self, row: dict) -> None:
        cols = [
            "pred_id", "run_id", "bot_id", "buch", "as_of", "decided_at", "symbol",
            "aktion", "rang", "score", "decision_price", "entry_date",
            "entry_price_open", "entry_price", "entry_price_eff", "entry_timing",
            "planned_stop", "planned_target", "planned_hold_days", "notional",
            "reasons", "regime_markt", "regime_vola", "regime_breite", "atr_pct",
            "liquiditaet",
            # news_z/news_5d/news_erstabdeckung/news_tage_her/news_aktiv fehlten
            # hier - die Spalten existieren zwar seit Plan §10.2a/b in der
            # Tabelle (siehe _migrate), aber save_prediction() liess sie beim
            # Schreiben still unter den Tisch fallen. Das erklaert, warum
            # der Schattenbetrieb selbst mit --mit-news frueher 0 gefuellte
            # news_5d-Werte hatte (Befund 03.08.2026) - nicht ein
            # Ranglisten-Problem, sondern dieses Feld fehlte hier schlicht.
            "news_z", "news_5d", "news_erstabdeckung", "news_tage_her",
            "news_ereignis", "news_ton", "news_aktiv",
            "wuerde_gehandelt", "code_version", "nachgetragen",
        ]
        with self._conn() as c:
            c.execute(
                f"INSERT OR IGNORE INTO predictions ({','.join(cols)})"
                f" VALUES ({','.join('?' * len(cols))})",
                [row.get(k) for k in cols],
            )

    # Whitelist statt freier Tabellennamen: `name` fliesst in den SQL-Text
    # ein und waere sonst eine Einfallstelle fuer Injection.
    TABELLEN = {
        "shadow_runs", "predictions", "shadow_outcomes",
        "shadow_portfolio", "shadow_cash", "shadow_exits", "equity_kurve",
        "bots", "versuchszaehler", "scoreboard", "vergleiche",
        "muster", "hypothesen",
    }

    def table(self, name: str, where: str = "", params: tuple = ()) -> pd.DataFrame:
        if name not in self.TABELLEN:
            raise ValueError(
                f"Unbekannte Tabelle {name!r}. Erlaubt: {sorted(self.TABELLEN)}"
            )
        sql = f"SELECT * FROM {name}" + (f" WHERE {where}" if where else "")
        with self._conn() as c:
            return pd.read_sql_query(sql, c, params=params)

    def offene_einbuchungen(self) -> pd.DataFrame:
        """Vorhersagen, deren Einstiegskurs noch fehlt."""
        return self.table("predictions", "entry_price IS NULL")

    def offene_ergebnisse(self) -> pd.DataFrame:
        """Eingebuchte Vorhersagen ohne (vollstaendiges) Ergebnis.

        Liefert `evaluated_at` mit. Der Zeitstempel ist der Schluessel
        dazu, im Dauerbetrieb nicht stuendlich dasselbe neu zu rechnen -
        siehe `verifizieren()`.
        """
        with self._conn() as c:
            return pd.read_sql_query(
                "SELECT p.*, o.evaluated_at AS evaluated_at FROM predictions p"
                " LEFT JOIN shadow_outcomes o ON p.pred_id = o.pred_id"
                " WHERE p.entry_price IS NOT NULL"
                "   AND (o.pred_id IS NULL OR o.fwd_20d IS NULL)",
                c,
            )

    def letzter_lerntag(self) -> str:
        """Stichtag, bis zu dem der Lernschritt gelaufen ist ('' = nie).

        Liegt in `scoreboard` als einfaches Schluessel/Wert-Paar, damit
        dafuer keine eigene Tabelle noetig ist.
        """
        with self._conn() as c:
            try:
                row = c.execute(
                    "SELECT wert FROM merker WHERE schluessel='letzter_lerntag'"
                ).fetchone()
            except Exception:  # noqa: BLE001 - alte Datenbanken ohne die Tabelle
                return ""
        return (row["wert"] if row else "") or ""

    def setze_lerntag(self, tag: str) -> None:
        with self._conn() as c:
            c.execute("INSERT OR REPLACE INTO merker (schluessel, wert, geaendert)"
                      " VALUES ('letzter_lerntag', ?, ?)",
                      (tag, dt.datetime.now(dt.UTC).isoformat()))

    def save_fill(self, pred_id: str, **vals) -> None:
        sets = ", ".join(f"{k}=?" for k in vals)
        with self._conn() as c:
            c.execute(f"UPDATE predictions SET {sets} WHERE pred_id=?",
                      [*vals.values(), pred_id])

    def save_outcome(self, row: dict) -> None:
        cols = [
            "pred_id", "exit_date", "exit_price", "exit_price_eff", "exit_reason",
            "return_pct", "return_brutto", "kosten", "bars_held", "mae_pct",
            "mfe_pct", "fwd_1d", "fwd_3d", "fwd_5d", "fwd_10d", "fwd_20d",
            "bench_fwd_5d", "universum_fwd_5d", "ueberschuss_5d",
            "ziel_erreicht", "stop_erreicht", "evaluated_at", "data_check",
        ]
        with self._conn() as c:
            c.execute(
                f"INSERT OR REPLACE INTO shadow_outcomes ({','.join(cols)})"
                f" VALUES ({','.join('?' * len(cols))})",
                [row.get(k) for k in cols],
            )

    # --- Spiegelbuch: virtuelles Depot ---
    def depot_init(self, bot_id: str, startkapital: float) -> None:
        with self._conn() as c:
            c.execute(
                "INSERT OR IGNORE INTO shadow_cash (bot_id, cash, equity,"
                " startwert, letzter_tag, updated_at) VALUES (?,?,?,?,NULL,?)",
                (bot_id, startkapital, startkapital, startkapital,
                 dt.datetime.now(dt.UTC).isoformat()),
            )

    def depot_stand(self, bot_id: str) -> dict:
        with self._conn() as c:
            row = c.execute("SELECT * FROM shadow_cash WHERE bot_id=?",
                            (bot_id,)).fetchone()
        return dict(row) if row else {}

    def depot_positionen(self, bot_id: str) -> dict[str, dict]:
        with self._conn() as c:
            rows = c.execute("SELECT * FROM shadow_portfolio WHERE bot_id=?",
                             (bot_id,)).fetchall()
        return {r["symbol"]: dict(r) for r in rows}

    def depot_speichern(self, bot_id: str, pos: Position, *,
                        entry_score: float | None = None,
                        reasons: dict | None = None) -> None:
        """Schreibt eine Spiegelposition fort - OHNE die Einstiegsgruende zu verlieren.

        **Der Fund vom 24.08.2026 (BEFUNDE §G27).** Hier stand
        `INSERT OR REPLACE` mit den uebergebenen Werten. Von den drei
        Aufrufern in `shadow_schritte._spiegel` gibt aber nur der Kauf
        `entry_score` und `reasons` mit; der **taegliche Uebertrag** der
        gehaltenen Positionen liest sie aus `meta` - und `meta` wird
        EINMAL vor der Tagesschleife geladen. Ein im selben Lauf
        gekaufter Wert steht dort nicht, also kam `None` an und
        ueberschrieb den korrekten Wert vom Vortag.

        Gemessen: `entry_score` in **0 von 130** Zeilen gefuellt,
        `reasons` in 130 von 130 - mit **einem** eindeutigen Wert, `{}`.
        Jede Position wird mindestens einmal uebertragen, also verliert
        jede ihre Begruendung.

        **Was dadurch unbeantwortbar war:** "War die gehaltene Position
        schwaecher als der beste verworfene Kandidat?" Genau die Frage,
        fuer die das Spiegelbuch existiert.

        Deshalb jetzt `ON CONFLICT ... DO UPDATE` mit `COALESCE`: Ein
        `None` laesst den bestehenden Wert stehen, statt ihn zu loeschen.
        Eine Fortschreibung darf nie weniger Information hinterlassen als
        sie vorfand - dieselbe Abwaegung wie bei `live.reconcile_fills`
        (§G19 Fund 5).
        """
        with self._conn() as c:
            c.execute(
                "INSERT INTO shadow_portfolio (bot_id, symbol, qty,"
                " entry_price, entry_date, stop_price, target_price, bars_held,"
                " high_water, entry_score, reasons) VALUES (?,?,?,?,?,?,?,?,?,?,?)"
                " ON CONFLICT(bot_id, symbol) DO UPDATE SET"
                "   qty=excluded.qty, entry_price=excluded.entry_price,"
                "   entry_date=excluded.entry_date, stop_price=excluded.stop_price,"
                "   target_price=excluded.target_price, bars_held=excluded.bars_held,"
                "   high_water=excluded.high_water,"
                "   entry_score=COALESCE(excluded.entry_score, entry_score),"
                "   reasons=COALESCE(excluded.reasons, reasons)",
                (bot_id, pos.symbol, pos.qty, pos.entry_price,
                 pd.Timestamp(pos.entry_date).isoformat(), pos.stop_price,
                 pos.target_price, pos.bars_held, pos.high_water,
                 entry_score,
                 # `None` statt `{}`, damit COALESCE greifen kann. Ein
                 # leeres Dictionary waere ein WERT und wuerde die echten
                 # Gruende ueberschreiben - genau der alte Fehler.
                 _json(reasons) if reasons else None),
            )

    def depot_loeschen(self, bot_id: str, symbol: str) -> None:
        with self._conn() as c:
            c.execute("DELETE FROM shadow_portfolio WHERE bot_id=? AND symbol=?",
                      (bot_id, symbol))

    def depot_cash(self, bot_id: str, cash: float, equity: float,
                   letzter_tag=None) -> None:
        with self._conn() as c:
            c.execute(
                "UPDATE shadow_cash SET cash=?, equity=?, updated_at=?"
                + (", letzter_tag=?" if letzter_tag is not None else "")
                + " WHERE bot_id=?",
                ([cash, equity, dt.datetime.now(dt.UTC).isoformat()]
                 + ([str(letzter_tag)] if letzter_tag is not None else [])
                 + [bot_id]),
            )

    def equity_punkt(self, bot_id: str, tag, equity: float, cash: float,
                     n_pos: int) -> None:
        with self._conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO equity_kurve VALUES (?,?,?,?,?)",
                (bot_id, str(tag), equity, cash, n_pos),
            )

    def ausstieg_merken(self, bot_id: str, symbol: str, *, exit_date,
                        exit_price=None, exit_reason="", entry_price=None,
                        return_pct=None, bars_held=None) -> None:
        with self._conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO shadow_exits VALUES (?,?,?,?,?,?,?,?)",
                (bot_id, symbol, str(exit_date), exit_price, exit_reason,
                 entry_price, return_pct, bars_held),
            )

    def symbole_in_sperrfrist(self, bot_id: str, days: int, as_of) -> set[str]:
        """Symbole, die dieser Bot innerhalb der letzten `days` Handelstage
        verkauft hat. Gerechnet in Handelstagen, nicht Kalendertagen - sonst
        waere eine Sperre ueber ein Wochenende faktisch aufgehoben."""
        if days <= 0:
            return set()
        now = pd.Timestamp(as_of)
        if now.tz is None:
            now = now.tz_localize("UTC")
        cutoff = (now.normalize() - pd.tseries.offsets.BDay(days)).isoformat()
        with self._conn() as c:
            rows = c.execute(
                "SELECT DISTINCT symbol FROM shadow_exits"
                " WHERE bot_id=? AND exit_date >= ?", (bot_id, cutoff)
            ).fetchall()
        return {r["symbol"] for r in rows}

    # --- Spiegelbuch: aufgeschobene Orders ---
    def pending_setzen(self, bot_id: str, decisions: list, as_of) -> None:
        with self._conn() as c:
            c.execute("DELETE FROM spiegel_pending WHERE bot_id=?", (bot_id,))
            for d in decisions:
                c.execute(
                    "INSERT OR REPLACE INTO spiegel_pending"
                    " VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (bot_id, d.symbol, d.action, d.target_notional, d.stop_price,
                     d.target_price, d.conviction, _json(d.reasons),
                     pd.Timestamp(as_of).isoformat(),
                     dt.datetime.now(dt.UTC).isoformat()),
                )

    def pending_holen(self, bot_id: str) -> list[dict]:
        with self._conn() as c:
            return [dict(r) for r in c.execute(
                "SELECT * FROM spiegel_pending WHERE bot_id=?", (bot_id,)
            ).fetchall()]

    def pending_leeren(self, bot_id: str) -> None:
        with self._conn() as c:
            c.execute("DELETE FROM spiegel_pending WHERE bot_id=?", (bot_id,))

    # --- Uebersicht ---
    def status_text(self) -> str:
        p = self.table("predictions")
        o = self.table("shadow_outcomes")
        r = self.table("shadow_runs")
        lines = ["=" * 64, "  SCHATTENBETRIEB", "=" * 64]
        if p.empty:
            lines.append("  Noch keine Vorhersagen.")
            return "\n".join(lines)

        tage = p["as_of"].nunique()
        lines += [
            f"  Vorhersagen       : {len(p):>7,}",
            f"  davon eingebucht  : {int(p['entry_price'].notna().sum()):>7,}",
            f"  Ergebnisse        : {len(o):>7,}",
            f"  Handelstage       : {tage:>7}   <- die statistisch zaehlende Zahl",
            f"  Zeitraum          : {p['as_of'].min()[:10]} bis {p['as_of'].max()[:10]}",
            f"  Laeufe            : {len(r):>7}"
            + (f"  ({int((r['status'] == 'fehler').sum())} mit Fehler)" if len(r) else ""),
        ]
        if not o.empty and o["fwd_5d"].notna().any():
            g = o["fwd_5d"].dropna()
            lines += [
                "",
                f"  5-Tage-Rendite    : {g.mean():+.3%} im Mittel ueber {len(g):,} Faelle",
                f"  Trefferquote      : {(g > 0).mean():.1%}",
            ]
            if o["ueberschuss_5d"].notna().any():
                u = o["ueberschuss_5d"].dropna()
                lines.append(
                    f"  UEBERSCHUSS       : {u.mean():+.3%}  <- gegen Universum, "
                    "nur DIESE Zahl zaehlt"
                )
        if tage < 60:
            lines += [
                "",
                f"  HINWEIS: {tage} von 60 Handelstagen. Unter 60 Tagen ist jeder",
                "  Befund eine Momentaufnahme und rechtfertigt keine Regelaenderung.",
            ]
        return "\n".join(lines)
