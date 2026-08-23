"""Schattenbetrieb: lernen, ohne zu handeln (Phase 1 aus docs/schattenbetrieb.md).

Der Engpass des Projekts ist nicht Rechenzeit, sondern BEOBACHTUNGEN. Der
Live-Bot kauft hoechstens 3 Werte je Lauf und verwirft dabei ~200 Kandidaten,
ueber die niemand je erfaehrt, was aus ihnen geworden waere. Genau das ist
aber die wichtigste Frage: **sortiert unsere Rangliste richtig?**

Dieses Modul beantwortet sie, indem es taeglich JEDEN Kandidaten aufzeichnet
und spaeter nachhaelt, was tatsaechlich passiert ist - ohne eine einzige
Order zu senden.

**Der entscheidende Wert liegt nicht in "mehr Trades":**

    Jeder Backtest in diesem Projekt ist potenziell dadurch verdorben, dass
    die Strategie ausgewaehlt wurde, NACHDEM man diese Historie gesehen hat.
    Vorwaerts erzeugte Schattenvorhersagen sind gegen diesen Fehler immun.
    Sie sind die einzigen wirklich unbekannten Daten, die das Projekt bekommt.

**Trennung vom Handelspfad - strukturell, nicht diszipliniert:**

    journal.sqlite   Depot und Simulation   (unberuehrt von diesem Modul)
    shadow.sqlite    Schattenbetrieb        (eigene Datei)

Eine Abfrage gegen `journal.sqlite` KANN keine Schattendaten liefern. Das ist
Absicht: Bei ~1.000 Schattenvorhersagen taeglich gegen ~60 echte Entscheidungen
waere jede vergessene `WHERE script=`-Bedingung eine still falsche Kennzahl -
und genau dieser Mechanismus hat schon einmal versagt (14_journal_bereinigen.py).

Dieses Modul importiert bewusst **kein** `trading.py`. Es kann konstruktions-
bedingt keine Order senden, nicht nur "darf nicht".

**Geteilt wird dagegen `Engine.decide()`** - derselbe Grundsatz wie im ganzen
Projekt: eine Entscheidungslogik, verschiedene Datenquellen.

    simulate.py  ->  Historie, bei Tag T abgeschnitten
    live.py      ->  Alpaca-Depot
    shadow.py    ->  yfinance, virtuelles Buch          <- hier

Drei Arbeitsschritte mit unterschiedlichem Rhythmus:

    entscheiden()   nach US-Schluss: Kandidaten des Tages festhalten
    einbuchen()     naechster Handelstag: Eroeffnungskurs nachtragen
    verifizieren()  laufend: was ist tatsaechlich daraus geworden
"""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
import subprocess
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

import numpy as np
import pandas as pd

from .config import CACHE_DIR, DATA_DIR
from .costs import DEFAULT_FEES, estimate_costs
from .engine import (
    Decision,
    Engine,
    EngineConfig,
    MarketSnapshot,
    PortfolioState,
    Position,
)

SHADOW_DB = DATA_DIR / "shadow.sqlite"
SHADOW_CACHE = CACHE_DIR / "shadow_bars"

# `RAW_DIR = DATA_DIR / "shadow_raw"` stand hier bis zum 23.08.2026 und
# wurde bei jedem `ShadowStore()` angelegt - aber NIE beschrieben. Seit
# dem 31.07.2026 leer, und es sah aus wie das Gegenstueck zu
# `journal_raw`. Ersetzt durch `ShadowStore.sichern()`, das eine echte,
# transaktionskonsistente Kopie ablegt (BEFUNDE §G19 Fund 7).

MARKET_SYMBOL = "SPY"

# Horizonte, auf denen jede Vorhersage nachgehalten wird. Bewusst UNABHAENGIG
# von Stop und Ziel: Sie sind die Grundlage jeder kontrafaktischen Rechnung
# (Plan §7.2) - "waere Bot A's Auswahl mit Bot B's Ausstieg besser gewesen?"
HORIZONTE = (1, 3, 5, 10, 20)


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


class ShadowEngine(Engine):
    """Engine fuer den Schattenbetrieb - mit EIGENER Sperrfrist-Quelle.

    `Engine._cooldown_symbols()` liest die Sperrfrist fest aus `state.sqlite`,
    also aus dem Zustand des LIVE-Bots. Fuer das Spiegelbuch waere das ein
    stiller Fehler in beide Richtungen: Der Schatten wuerde Symbole meiden,
    die nur der echte Bot verkauft hat, und umgekehrt seine eigenen Verkaeufe
    nicht beruecksichtigen. Beide Buecher wuerden dadurch etwas anderes
    messen, als sie zu messen vorgeben.

    Deshalb wird die Quelle hier ueberschrieben statt `engine.py` zu aendern -
    der Handelspfad bleibt unberuehrt.
    """

    def __init__(self, config: EngineConfig, store: "ShadowStore", bot_id: str):
        super().__init__(config)
        self._store = store
        self._bot_id = bot_id

    def _cooldown_symbols(self, as_of: pd.Timestamp) -> set[str]:
        days = self.cfg.reenter_cooldown_days
        if days <= 0:
            return set()
        return self._store.symbole_in_sperrfrist(self._bot_id, days, as_of)


@dataclass
class ShadowConfig:
    """Einstellungen des Schattenbetriebs."""

    universe: str = "gemessen"
    max_symbols: int = 800
    """Obergrenze. Kleiner als beim Live-Bot, weil hier JEDER Kandidat
    aufgezeichnet wird und die Laufzeit linear mitwaechst."""

    years: float = 2.0
    """Historie je Lauf. 2 Jahre reichen fuer die 260-Bar-Vorlaufzeit der
    Signale und halten den Download ertraeglich."""

    spread_bps: float = 5.0
    slippage_bps: float = 3.0
    """Identisch mit SimConfig - sonst waeren Schatten und Simulation nicht
    vergleichbar. Ein Schattentrade ohne Kosten sieht systematisch besser aus
    als jeder echte, und zwar genau in die Richtung, die einem gefaellt."""

    news_max_symbole: int = 200
    """Nur die bestbewerteten Kandidaten bekommen den zusaetzlichen
    Tonalitaets-/Ereignis-Kontext (news_ton/news_ereignis, _news_kontext) -
    dieser zweite Feed-Abruf ist zu langsam fuer 800 Symbole je Lauf.

    Betrifft NICHT den eigentlichen Score-Faktor (ReversalWeights.news):
    Der laeuft seit 03.08.2026 immer, ueber das GANZE Universum, als Teil
    des normalen Starts (siehe baue_snapshot) - kein Flag, keine Grenze."""

    max_new_positions: int = 3
    """Kaeufe je Lauf im Spiegelbuch - identisch mit dem Live-Bot. Im
    Ranglisten-Buch bestimmt der Wert nur, welche Kandidaten das Kennzeichen
    `wuerde_gehandelt` bekommen; erfasst werden dort alle."""

    engine: EngineConfig = field(default_factory=EngineConfig.for_reversal)
    bot_id: str = "B00_basis"


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
        with self._conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO shadow_portfolio (bot_id, symbol, qty,"
                " entry_price, entry_date, stop_price, target_price, bars_held,"
                " high_water, entry_score, reasons) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (bot_id, pos.symbol, pos.qty, pos.entry_price,
                 pd.Timestamp(pos.entry_date).isoformat(), pos.stop_price,
                 pos.target_price, pos.bars_held, pos.high_water,
                 entry_score, _json(reasons or {})),
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


# ---------------------------------------------------------------------------
# Daten
# ---------------------------------------------------------------------------
def _universum_symbole(cfg: ShadowConfig) -> list[str]:
    """Das STABILE Tagesuniversum - identisch fuer alle drei Schritte.

    Wichtig fuer den Tages-Cache in `lade_bars()`: Der Cache-Schluessel haengt
    vom exakten Symbolset ab. `einbuchen()`/`verifizieren()` bauten frueher
    ihre Liste aus den noch offenen Vorhersagen - einer Menge, die mit jeder
    abgearbeiteten Vorhersage SCHRUMPFT. Der Schluessel aenderte sich dadurch
    bei praktisch jedem Durchlauf, der Cache griff nie, und es wurde JEDE
    STUNDE neu von yfinance geladen (gemessen: ~8 offene Dateien je
    Download-Aufruf, die yfinance nicht zuverlaessig schliesst - genau das
    hat am 2026-07-29 nach einigen Stunden das Datei-Limit gerissen).

    Alle Symbole, die einbuchen/verifizieren je brauchen, sind eine
    Teilmenge dieses Universums. Mit einem STABILEN Symbolset trifft der
    Cache zuverlaessig, und es gibt nur noch EINEN echten Download-Zyklus
    je Kalendertag statt bis zu 24.
    """
    from . import universe

    if cfg.universe == "gemessen":
        symbols = universe.load_universe(max_symbols=cfg.max_symbols)
    else:
        symbols = universe.BENCHMARK_SETS[cfg.universe]
    return list(dict.fromkeys([*symbols, MARKET_SYMBOL]))


def lade_bars(symbols: list[str], years: float, *, verbose: bool = True) -> pd.DataFrame:
    """Tagesbars von yfinance, mit TAGESGENAUEM Cache.

    Bewusst NICHT `datasources.get_history(use_cache=True)`: Dessen
    Cache-Schluessel enthaelt kein Datum (`_cache_path` -> source_key_years),
    ein taeglich laufender Dienst bekaeme also stillschweigend ewig dieselben
    Daten. Hier steht das Datum im Dateinamen, ein neuer Tag laedt neu.
    """
    from .datasources import get_history

    SHADOW_CACHE.mkdir(parents=True, exist_ok=True)
    heute = dt.date.today().isoformat()
    # hashlib statt Pythons eingebautem hash(): Der ist pro Prozessstart
    # zufaellig gesalzen (Hash-Randomisierung seit Python 3.3) - nach jedem
    # Neustart des Daemons haette derselbe Symbol-Tag einen anderen
    # Schluessel ergeben und den Tages-Cache fuer den ganzen Tag entwertet.
    import hashlib

    digest = hashlib.sha256("|".join(sorted(symbols)).encode()).hexdigest()[:10]
    key = f"{len(symbols)}_{digest}"
    pfad = SHADOW_CACHE / f"{heute}_{key}_{years:g}y.parquet"

    if pfad.exists():
        if verbose:
            print(f"      aus Tages-Cache: {pfad.name}")
        return pd.read_parquet(pfad)

    bars = get_history(symbols, years=years, source="yfinance",
                       use_cache=False, verbose=verbose)
    if not bars.empty:
        bars.to_parquet(pfad)
        # Aeltere Tages-Caches aufraeumen, sonst waechst der Ordner unbegrenzt.
        for alt in sorted(SHADOW_CACHE.glob("*.parquet"))[:-3]:
            alt.unlink(missing_ok=True)
    return bars


def _regime(market: pd.Series, per_symbol: dict[str, pd.DataFrame],
            as_of: pd.Timestamp) -> dict:
    """Marktkontext zum Entscheidungszeitpunkt.

    Ohne diesen Kontext laesst sich spaeter nicht auswerten, UNTER WELCHEN
    BEDINGUNGEN der Vorsprung traegt - und genau dort liegt laut Plan §13 der
    aussichtsreichste Hebel.
    """
    out = {"regime_markt": "unbekannt", "regime_vola": "unbekannt",
           "regime_breite": None}
    if market is None or len(market) < 200:
        return out

    m = market.astype(float)
    sma200 = m.rolling(200).mean().iloc[-1]
    trend = "auf" if m.iloc[-1] > sma200 else "ab"

    ret = m.pct_change().dropna()
    vola20 = ret.tail(20).std() * np.sqrt(252)
    hist = ret.rolling(20).std().dropna() * np.sqrt(252)
    if len(hist) > 60:
        pct = float((hist.tail(504) < vola20).mean())
        band = "niedrig" if pct < 0.33 else ("mittel" if pct < 0.67 else "hoch")
    else:
        band = "unbekannt"

    ueber_sma50 = []
    for df in per_symbol.values():
        if len(df) < 50:
            continue
        c = df["close"].astype(float)
        ueber_sma50.append(float(c.iloc[-1] > c.rolling(50).mean().iloc[-1]))

    out["regime_markt"] = f"{trend}waerts"
    out["regime_vola"] = band
    out["regime_breite"] = round(float(np.mean(ueber_sma50)), 3) if ueber_sma50 else None
    return out


def baue_snapshot(bars: pd.DataFrame, *, min_bars: int = 260,
                  verbose: bool = True) -> tuple[MarketSnapshot, dict]:
    """Baut die Momentaufnahme aus yfinance-Bars.

    `as_of` ist der letzte Tag mit Daten. Anders als im Live-Betrieb muss hier
    keine unfertige Tagesbar verworfen werden: Der Lauf findet nach US-Schluss
    statt, und yfinance liefert Tagesbars erst, wenn der Tag abgeschlossen ist.
    Die Kalenderpruefung in `entscheiden()` stellt das sicher.
    """
    per_symbol: dict[str, pd.DataFrame] = {}
    for sym in bars.index.get_level_values("symbol").unique():
        df = bars.xs(sym, level="symbol").sort_index()
        if len(df) >= min_bars:
            per_symbol[sym] = df

    if not per_symbol:
        raise RuntimeError(
            f"Kein Symbol mit mindestens {min_bars} Bars - zu wenig Historie."
        )

    markt_df = per_symbol.pop(MARKET_SYMBOL, None)
    if markt_df is None:
        raise RuntimeError(
            f"{MARKET_SYMBOL} fehlt. Ohne Marktreferenz waere der Regime-Filter "
            "inaktiv und der Schatten wiche vom Live-Verhalten ab."
        )
    market = markt_df["close"].astype(float)

    as_of = max(pd.Timestamp(df.index[-1]) for df in per_symbol.values())
    if as_of.tz is None:
        as_of = as_of.tz_localize("UTC")

    # Nur Symbole, die bis zum Stichtag reichen - sonst entscheidet die Engine
    # auf veralteten Kursen (delistet, Handelsaussetzung).
    def _letzter(df: pd.DataFrame) -> pd.Timestamp:
        t = pd.Timestamp(df.index[-1])
        return t.tz_localize("UTC") if t.tz is None else t

    aktuell = {
        s: df for s, df in per_symbol.items()
        if _letzter(df) >= as_of - pd.Timedelta(days=5)
    }

    # --- Nachrichten fuer die Signalberechnung (Faktor ReversalWeights.news) ---
    # EIN Abruf fuer das ganze Universum, wie im Handelsbot (live.py) - sonst
    # wuerde die Rangfolge, die ueber die Kandidatenauswahl fuer den
    # News-Kontext unten entscheidet, selbst schon ohne News gebildet, und
    # der Faktor koennte nie mitentscheiden, wer ueberhaupt in Frage kommt.
    # Defensiv: ein Ausfall der News-API darf den Schattenbetrieb niemals
    # stoppen (siehe _news_kontext).
    news_df = None
    try:
        from . import news as news_mod

        start = (as_of - pd.Timedelta(days=90)).strftime("%Y-%m-%d")
        news_df = news_mod.get_news(
            list(aktuell), start=start, end=as_of.strftime("%Y-%m-%d"),
            max_articles=5_000,
        )
        if verbose:
            print(f"      Nachrichten: {len(news_df)} Artikel geladen")
    except Exception as e:  # noqa: BLE001
        if verbose:
            print(f"      Nachrichten nicht ladbar ({type(e).__name__}) - "
                  "Schattenbetrieb faehrt ohne Nachrichtenfaktor fort.")
        news_df = None

    if verbose:
        print(f"      Stichtag: {as_of.date()} | {len(aktuell)} Symbole "
              f"| Marktfilter: {MARKET_SYMBOL}")

    snap = MarketSnapshot(as_of=as_of, bars=aktuell, market=market.loc[:as_of],
                          news=news_df)
    snap.validate()
    return snap, {"markt": market}


# ---------------------------------------------------------------------------
# Schritt 1: Entscheiden - beide Buecher, alle Bots der Flotte
# ---------------------------------------------------------------------------
def _signalrahmen(per_symbol: dict[str, pd.DataFrame], market: pd.Series,
                  cfg: EngineConfig, news: pd.DataFrame | None = None,
                  ) -> dict[str, pd.DataFrame]:
    """Berechnet die Signale je Symbol EINMAL fuer eine Signalkonfiguration.

    Die meisten Flottenvarianten aendern nur Ausstiegsparameter (stop_atr,
    target_atr, max_hold_days, min_score) - die beruehren die
    Signalberechnung nicht. Sieben Bots brauchen dadurch zwei Durchlaeufe
    statt sieben; das ist die Voraussetzung dafuer, die Flotte ueberhaupt
    taeglich ueber ~800 Symbole laufen zu lassen.

    `news` wird unveraendert an `build_reversal_frame` durchgereicht - die
    Zeitpunktsicherheit (Verfuegbarkeit = Veroeffentlichung + Verzug) passiert
    dort je Symbol, nicht hier (siehe signals.build_reversal_frame).
    """
    from .signals import build_reversal_frame, build_signal_frame

    if cfg.strategy == "reversal":
        return {s: build_reversal_frame(df, market, cfg.reversal_weights,
                                        symbol=s, news=news)
                for s, df in per_symbol.items()}
    return {s: build_signal_frame(df, None, cfg.weights)
            for s, df in per_symbol.items()}


def _news_kontext(symbole: list[str], stichtag: pd.Timestamp,
                  verbose: bool = False) -> dict[str, dict]:
    """Zusaetzlicher Tonalitaets-/Ereignis-Kontext je Symbol - nur Metadaten.

    Anders als `news_z`/`news_5d`/`news_tage_her`/`news_erstabdeckung` (die
    kommen jetzt aus `signals.build_reversal_frame` und beeinflussen den
    Score aktiv, siehe ReversalWeights.news) liefert diese Funktion NUR
    `news_ton` und `news_ereignis` - eine zweite, unabhaengige Einordnung
    (Tonalitaet/Ereignistyp) ueber `news_features.py`, fuer die es in
    `news.py`s Score-Pfad keine Entsprechung gibt. Bewusst kein Gate, keine
    Wirkung auf die Entscheidung - reine Zusatzbeobachtung fuer die
    spaetere Auswertung. Darf den Lauf niemals stoppen.
    """
    try:
        from .news_features import kontext_fuer_stichtag

        df = kontext_fuer_stichtag(symbole, stichtag, verbose=verbose)
        if df.empty:
            return {}
        if verbose:
            print(f"      News-Kontext fuer {len(df)} von {len(symbole)} Symbolen")
        return df.to_dict(orient="index")
    except Exception as e:  # noqa: BLE001
        if verbose:
            print(f"      News-Kontext uebersprungen: {type(e).__name__}: {e}")
        return {}


def _rangliste(bot, snap: MarketSnapshot, store: ShadowStore, run_id: str,
               regime: dict, cv: str, max_new: int = 3,
               news: dict[str, dict] | None = None) -> int:
    """Buch 'rangliste': jeder Kandidat, ohne Kapitalgrenze.

    `Engine.decide()` bleibt die einzige Quelle fuer Bewertung und Filterung
    (Liquiditaet, Mindestkurs, min_score). Nur die KAPITALlogik wird
    neutralisiert - das ist genau die Definition dieses Buchs. Ohne
    `min_position_pct=0` fiele `per_slot` bei vielen Kandidaten unter die
    Mindestgroesse und die Engine liefe leer.
    """
    ecfg = EngineConfig(**{**bot.config.as_dict(),
                           "max_positions": 10_000, "min_position_pct": 0.0})
    ecfg.reversal_weights = bot.config.reversal_weights
    ecfg.weights = bot.config.weights

    decisions = Engine(ecfg).decide(snap, PortfolioState(cash=1e9, equity=1e9))
    buys = [d for d in decisions if d.action == "buy"]

    jetzt = dt.datetime.now(dt.UTC).isoformat()
    news = news or {}
    for i, d in enumerate(buys, start=1):
        n = news.get(d.symbol, {})
        store.save_prediction({
            "pred_id": uuid.uuid4().hex, "run_id": run_id, "bot_id": bot.bot_id,
            "buch": "rangliste", "as_of": snap.as_of.isoformat(),
            "decided_at": jetzt, "symbol": d.symbol, "aktion": "buy",
            "rang": i, "score": d.conviction, "decision_price": d.price,
            "planned_stop": d.stop_price, "planned_target": d.target_price,
            "planned_hold_days": bot.config.max_hold_days,
            "notional": d.target_notional, "reasons": _json(d.reasons),
            "atr_pct": d.reasons.get("atr_pct"),
            "liquiditaet": d.reasons.get("dollar_volume"),
            "wuerde_gehandelt": int(i <= max_new),
            "code_version": cv, "nachgetragen": 0,
            # news_z/news_5d/news_tage_her/news_erstabdeckung sind genau die
            # Werte, die auch in den Score eingeflossen sind (aus d.reasons,
            # von signals.build_reversal_frame) - nicht separat neu berechnet,
            # sonst koennten Anzeige und Entscheidung auseinanderlaufen.
            # news_ton/news_ereignis kommen weiterhin aus dem eigenstaendigen
            # Tonalitaets-/Ereignis-Kontext (news_features.py, wirkungslos
            # auf den Score - siehe _news_kontext).
            "news_z": d.reasons.get("news_z"),
            "news_5d": d.reasons.get("news_5d"),
            "news_erstabdeckung": d.reasons.get("news_erstabdeckung"),
            "news_tage_her": d.reasons.get("news_tage_her"),
            "news_aktiv": int(bool(d.reasons.get("news_aktiv"))),
            "news_ereignis": n.get("news_ereignis"),
            "news_ton": n.get("news_ton"),
            **regime,
        })
    return len(buys)


def _spiegel(bot, snap: MarketSnapshot, per_symbol: dict[str, pd.DataFrame],
             signale: dict[str, pd.DataFrame], store: ShadowStore, run_id: str,
             regime: dict, cv: str, cfg: ShadowConfig,
             verbose: bool = False) -> dict:
    """Buch 'spiegel': bildet den echten Bot exakt nach.

    Aufgeschobene Ausfuehrung wie in `simulate.py`: Entschieden wird auf dem
    Schlusskurs von Tag T, ausgefuehrt zur Eroeffnung von T+1. Kapitalgrenzen,
    Positionslimit, Sperrfrist und Kosten wirken vollstaendig.

    Der Lauf holt fehlende Handelstage nach (Wochenende, Ausfall). Er ist
    idempotent: `letzter_tag` in `shadow_cash` verhindert, dass ein Tag
    zweimal ausgefuehrt wird - sonst wuerde jede Wiederholung des Daemons
    dieselben Kaeufe erneut buchen.
    """
    store.depot_init(bot.bot_id, bot.startkapital)
    stand = store.depot_stand(bot.bot_id)
    cash = float(stand["cash"])

    kalender = [t for t in sorted({t for df in per_symbol.values() for t in df.index})]
    kalender = [pd.Timestamp(t) for t in kalender]
    kalender = [t.tz_localize("UTC") if t.tz is None else t for t in kalender]

    letzter = stand.get("letzter_tag")
    if letzter:
        lt = pd.Timestamp(letzter)
        lt = lt.tz_localize("UTC") if lt.tz is None else lt
        offen = [t for t in kalender if t > lt and t <= snap.as_of]
    else:
        # Erster Lauf: nur den aktuellen Tag entscheiden, nichts ausfuehren.
        # Rueckwirkend zu handeln waere kein Vorwaertstest (Plan §4.6).
        offen = [snap.as_of]

    # Positionen laden
    positionen: dict[str, Position] = {}
    meta: dict[str, dict] = {}
    for sym, m in store.depot_positionen(bot.bot_id).items():
        ed = pd.Timestamp(m["entry_date"])
        positionen[sym] = Position(
            symbol=sym, qty=float(m["qty"]), entry_price=float(m["entry_price"]),
            entry_date=ed.tz_localize("UTC") if ed.tz is None else ed,
            stop_price=float(m["stop_price"]), target_price=float(m["target_price"]),
            bars_held=int(m["bars_held"] or 0), high_water=float(m["high_water"]),
        )
        meta[sym] = m

    engine = ShadowEngine(bot.config, store, bot.bot_id)
    stat = {"kaeufe": 0, "verkaeufe": 0, "tage": 0}
    jetzt = dt.datetime.now(dt.UTC).isoformat()

    for tag in offen:
        stat["tage"] += 1

        # ---------- 1. Aufgeschobene Orders von gestern ausfuehren ----------
        for p in store.pending_holen(bot.bot_id):
            df = per_symbol.get(p["symbol"])
            if df is None or tag not in df.index:
                continue
            bar = df.loc[tag]
            fill = float(bar["open"])
            if not np.isfinite(fill) or fill <= 0:
                continue

            if p["aktion"] == "buy":
                if p["symbol"] in positionen:
                    continue
                qty = int((p["notional"] or 0) / fill)
                if qty <= 0:
                    continue
                k = estimate_costs("buy", qty, last=fill,
                                   spread_bps=cfg.spread_bps,
                                   slippage_bps=cfg.slippage_bps, fees=DEFAULT_FEES)
                if k.net_proceeds > cash:
                    qty = int(cash * 0.98 / (fill * 1.01))
                    if qty <= 0:
                        continue
                    k = estimate_costs("buy", qty, last=fill,
                                       spread_bps=cfg.spread_bps,
                                       slippage_bps=cfg.slippage_bps,
                                       fees=DEFAULT_FEES)
                cash -= k.net_proceeds
                pos = Position(
                    symbol=p["symbol"], qty=qty,
                    entry_price=float(k.effective_price), entry_date=tag,
                    stop_price=float(p["stop_price"] or 0),
                    target_price=float(p["target_price"] or 0),
                    bars_held=0, high_water=float(k.effective_price),
                )
                positionen[p["symbol"]] = pos
                store.depot_speichern(bot.bot_id, pos,
                                      entry_score=p["score"],
                                      reasons=json.loads(p["reasons"] or "{}"))
                store.save_prediction({
                    "pred_id": uuid.uuid4().hex, "run_id": run_id,
                    "bot_id": bot.bot_id, "buch": "spiegel",
                    # Der Stichtag ist der Tag der ENTSCHEIDUNG, nicht der
                    # letzte Tag des Laufs - sonst laege beim Nachholen der
                    # Einstieg formal vor dem Stichtag (Pruefung 1).
                    "as_of": p["as_of"], "decided_at": jetzt,
                    "symbol": p["symbol"], "aktion": "buy", "score": p["score"],
                    "decision_price": fill, "entry_date": tag.isoformat(),
                    "entry_price_open": fill, "entry_price": fill,
                    "entry_price_eff": float(k.effective_price),
                    "entry_timing": "open",
                    "planned_stop": p["stop_price"], "planned_target": p["target_price"],
                    "planned_hold_days": bot.config.max_hold_days,
                    "notional": qty * fill, "reasons": p["reasons"],
                    "wuerde_gehandelt": 1, "code_version": cv,
                    "nachgetragen": 0, **regime,
                })
                stat["kaeufe"] += 1

            elif p["aktion"] == "topup" and p["symbol"] in positionen:
                # Nachkauf: Stueckzahl waechst, Einstand wird zum Mischkurs.
                # Stop, Ziel und bars_held bleiben unveraendert - der Nachkauf
                # verstaerkt eine These, er stellt keine neue auf.
                pos = positionen[p["symbol"]]

                # Sicherheitscheck ZUM AUSFUEHRUNGSZEITPUNKT (heutige
                # Eroeffnung), nicht nur bei der Entscheidung (gestriger
                # Schluss). Dazwischen kann eine Kursluecke einen gestrigen
                # Gewinner in einen heutigen Verlierer verwandeln - siehe
                # live.py fuer den Fund (CHRW: +2,1% -> -5,4%).
                if pos.entry_price > 0 and (fill / pos.entry_price - 1) < bot.config.topup_min_gain_pct:
                    continue

                # Groesse ZUM AUSFUEHRUNGSKURS gegen den Deckel pruefen,
                # nicht die am Vortag beschlossene Notional blind uebernehmen
                # - siehe live.py fuer die ausfuehrliche Begruendung (CHRW-
                # Fund: derselbe Fehler kann eine Position je nach
                # Kursrichtung faelschlich blockieren oder ueber den Deckel
                # hinaus vergroessern).
                eq_schaetzung = float(stand.get("equity", cash) or cash)
                deckel = eq_schaetzung * bot.config.max_position_pct
                ist_wert = pos.qty * fill
                erlaubt = max(0.0, deckel - ist_wert)
                notional = min(float(p["notional"] or 0), erlaubt)

                qty = int(notional / fill)
                if qty <= 0:
                    continue
                k = estimate_costs("buy", qty, last=fill,
                                   spread_bps=cfg.spread_bps,
                                   slippage_bps=cfg.slippage_bps, fees=DEFAULT_FEES)
                if k.net_proceeds > cash:
                    qty = int(cash * 0.98 / (fill * 1.01))
                    if qty <= 0:
                        continue
                    k = estimate_costs("buy", qty, last=fill,
                                       spread_bps=cfg.spread_bps,
                                       slippage_bps=cfg.slippage_bps,
                                       fees=DEFAULT_FEES)
                cash -= k.net_proceeds
                neu_qty = pos.qty + qty
                pos.entry_price = (
                    (pos.qty * pos.entry_price + qty * float(k.effective_price))
                    / neu_qty
                )
                pos.qty = neu_qty
                pos.high_water = max(pos.high_water, float(k.effective_price))
                store.depot_speichern(bot.bot_id, pos,
                                      entry_score=p["score"],
                                      reasons=json.loads(p["reasons"] or "{}"))
                store.save_prediction({
                    "pred_id": uuid.uuid4().hex, "run_id": run_id,
                    "bot_id": bot.bot_id, "buch": "spiegel",
                    "as_of": p["as_of"], "decided_at": jetzt,
                    "symbol": p["symbol"], "aktion": "topup", "score": p["score"],
                    "decision_price": fill, "entry_date": tag.isoformat(),
                    "entry_price_open": fill, "entry_price": fill,
                    "entry_price_eff": float(k.effective_price),
                    "entry_timing": "open",
                    "planned_stop": p["stop_price"], "planned_target": p["target_price"],
                    "planned_hold_days": bot.config.max_hold_days,
                    "notional": qty * fill, "reasons": p["reasons"],
                    "wuerde_gehandelt": 1, "code_version": cv,
                    "nachgetragen": 0, **regime,
                })
                stat["nachkaeufe"] = stat.get("nachkaeufe", 0) + 1

            elif p["aktion"] == "sell" and p["symbol"] in positionen:
                pos = positionen.pop(p["symbol"])
                k = estimate_costs("sell", pos.qty, last=fill,
                                   spread_bps=cfg.spread_bps,
                                   slippage_bps=cfg.slippage_bps, fees=DEFAULT_FEES)
                cash += k.net_proceeds
                rendite = float(k.effective_price) / pos.entry_price - 1
                store.ausstieg_merken(
                    bot.bot_id, pos.symbol, exit_date=tag.isoformat(),
                    exit_price=float(k.effective_price),
                    exit_reason=str(json.loads(p["reasons"] or "{}")
                                    .get("ausstiegsgrund", "signal")),
                    entry_price=pos.entry_price, return_pct=round(rendite, 5),
                    bars_held=pos.bars_held,
                )
                store.depot_loeschen(bot.bot_id, pos.symbol)
                meta.pop(pos.symbol, None)
                stat["verkaeufe"] += 1
        store.pending_leeren(bot.bot_id)

        # ---------- 2. Offene Positionen pflegen ----------
        for sym, pos in list(positionen.items()):
            df = per_symbol.get(sym)
            if df is None or tag not in df.index:
                continue
            bar = df.loc[tag]
            frame = signale.get(sym)
            atr = 0.0
            if frame is not None:
                bis = frame.loc[:tag]
                if len(bis):
                    atr = float(bis.iloc[-1].get("atr", 0) or 0)
            engine.update_position(pos, float(bar["close"]), atr)

            # Intraday-Stop: im Tagesverlauf gerissen?
            if float(bar["low"]) <= pos.stop_price:
                fill = min(pos.stop_price, float(bar["open"]))
                k = estimate_costs("sell", pos.qty, last=fill,
                                   spread_bps=cfg.spread_bps,
                                   slippage_bps=cfg.slippage_bps, fees=DEFAULT_FEES)
                cash += k.net_proceeds
                store.ausstieg_merken(
                    bot.bot_id, sym, exit_date=tag.isoformat(),
                    exit_price=float(k.effective_price), exit_reason="stop_intraday",
                    entry_price=pos.entry_price,
                    return_pct=round(float(k.effective_price) / pos.entry_price - 1, 5),
                    bars_held=pos.bars_held,
                )
                store.depot_loeschen(bot.bot_id, sym)
                positionen.pop(sym, None)
                stat["verkaeufe"] += 1
            else:
                store.depot_speichern(bot.bot_id, pos,
                                      entry_score=(meta.get(sym) or {}).get("entry_score"))

        # ---------- 3. Kontowert ----------
        equity = cash
        for sym, pos in positionen.items():
            df = per_symbol.get(sym)
            kurs = (float(df.loc[tag, "close"])
                    if df is not None and tag in df.index else pos.entry_price)
            equity += pos.qty * kurs
        store.equity_punkt(bot.bot_id, tag.date(), equity, cash, len(positionen))

        # ---------- 4. Entscheiden fuer morgen ----------
        aktive = {s: df.loc[:tag] for s, df in per_symbol.items()
                  if tag in df.index and len(df.loc[:tag]) >= 260}
        if not aktive:
            continue
        tages_snap = MarketSnapshot(
            as_of=tag, bars=aktive,
            market=snap.market.loc[:tag] if snap.market is not None else None,
            signals={s: signale[s].loc[:tag] for s in aktive if s in signale},
        )
        pf = PortfolioState(cash=cash, equity=equity, positions=dict(positionen))
        neue = engine.decide(tages_snap, pf)
        verkaeufe = [d for d in neue if d.action == "sell"]
        kaeufe = [d for d in neue if d.action == "buy"][:cfg.max_new_positions]
        # Nachkaeufe zaehlen NICHT gegen max_new_positions - sie eroeffnen
        # keine neue These, sondern verstaerken eine bestehende. Jede bleibt
        # einzeln durch max_position_pct gedeckelt.
        nachkaeufe = [d for d in neue if d.action == "topup"]
        store.pending_setzen(bot.bot_id, [*verkaeufe, *kaeufe, *nachkaeufe],
                             as_of=tag)

        store.depot_cash(bot.bot_id, cash, equity, letzter_tag=tag.isoformat())

    if verbose:
        extra = (f", {stat['nachkaeufe']} Nachkauf/-kaeufe"
                 if stat.get("nachkaeufe") else "")
        print(f"      {bot.bot_id:<18} Spiegel: {stat['tage']} Tag(e), "
              f"{stat['kaeufe']} Kauf/Kaeufe, {stat['verkaeufe']} Verkauf/Verkaeufe"
              f"{extra}, {len(positionen)} Positionen")
    return stat


def entscheiden(cfg: ShadowConfig, store: ShadowStore | None = None,
                *, verbose: bool = True) -> int:
    """Ein Entscheidungslauf fuer die ganze Flotte, beide Buecher.

    Die teure Arbeit - Kursdaten laden und Signale rechnen - passiert EINMAL
    und wird von allen Bots geteilt. Zusaetzlicher Nutzen: Alle Bots sehen
    garantiert dieselben Kurse an denselben Tagen, die Voraussetzung fuer den
    gepaarten Vergleich (Plan §6.2).
    """
    from . import fleet

    store = store or ShadowStore()
    symbols = _universum_symbole(cfg)

    bots = fleet.aktive_bots(store)
    if not bots:
        raise RuntimeError(
            "Keine Bots angemeldet. Zuerst die Startaufstellung anlegen:\n"
            "  python scripts/21_fleet.py --startaufstellung"
        )

    run_id = store.start_run("entscheiden", n_symbols=len(symbols),
                             universum=cfg.universe, engine=cfg.engine.as_dict())
    try:
        bars = lade_bars(symbols, cfg.years, verbose=verbose)
        if bars.empty:
            raise RuntimeError("Keine Kursdaten erhalten.")
        snap, extra = baue_snapshot(bars, verbose=verbose)

        # --- Kalenderpruefung (Plan §14.2) ---
        heute = pd.Timestamp.now(tz="UTC").normalize()
        if snap.as_of > heute:
            raise RuntimeError(f"Stichtag {snap.as_of.date()} liegt in der Zukunft.")

        regime = _regime(extra["markt"], snap.bars, snap.as_of)
        cv = code_version()
        if verbose:
            print(f"      Regime: {regime['regime_markt']}, "
                  f"Vola {regime['regime_vola']}, Breite {regime['regime_breite']}")

        # --- Signale je EINDEUTIGER Signalkonfiguration, nicht je Bot ---
        # snap.news geht an JEDEN Durchlauf - der Score-Faktor
        # (ReversalWeights.news) ist seit 03.08.2026 immer aktiv, fuer alle
        # Bots gleich, kein Flag mehr.
        cache: dict[str, dict] = {}
        for b in bots:
            k = b.signal_schluessel()
            if k not in cache:
                cache[k] = _signalrahmen(snap.bars, extra["markt"], b.config,
                                         news=snap.news)
        if verbose:
            print(f"      {len(cache)} Signaldurchlauf/-laeufe fuer {len(bots)} Bots")

        # Zusaetzlicher Tonalitaets-/Ereignis-Kontext (reine Metadaten, siehe
        # _news_kontext) fuer die besten Kandidaten des Basis-Bots - dessen
        # Rangliste beruecksichtigt den Score-Faktor jetzt bereits mit.
        basis_signale = cache[bots[0].signal_schluessel()]
        kand = sorted(
            ((float(f.iloc[-1].get("score", 0) or 0), s)
             for s, f in basis_signale.items() if len(f)),
            reverse=True,
        )[: cfg.news_max_symbole]
        news_ctx = _news_kontext([s for _, s in kand], snap.as_of,
                                 verbose=verbose)

        gesamt = 0
        for b in bots:
            signale = cache[b.signal_schluessel()]
            bot_snap = MarketSnapshot(
                as_of=snap.as_of, bars=snap.bars, market=snap.market,
                signals={s: f.loc[:snap.as_of] for s, f in signale.items()},
            )

            schon_da = store.table(
                "predictions",
                "as_of = ? AND bot_id = ? AND buch = 'rangliste'",
                (snap.as_of.isoformat(), b.bot_id),
            )
            if schon_da.empty:
                n = _rangliste(b, bot_snap, store, run_id, regime, cv,
                               max_new=cfg.max_new_positions, news=news_ctx)
                gesamt += n
                if verbose:
                    print(f"      {b.bot_id:<18} Rangliste: {n} Kandidaten")
            elif verbose:
                print(f"      {b.bot_id:<18} Rangliste: bereits erfasst")

            _spiegel(b, bot_snap, snap.bars, signale, store, run_id, regime, cv,
                     cfg, verbose=verbose)

        store.finish_run(run_id, "ok")
        return gesamt
    except Exception as e:  # noqa: BLE001
        store.finish_run(run_id, "fehler", f"{type(e).__name__}: {e}")
        raise


# ---------------------------------------------------------------------------
# Schritt 2: Einbuchen
# ---------------------------------------------------------------------------
def einbuchen(cfg: ShadowConfig, store: ShadowStore | None = None,
              *, verbose: bool = True) -> int:
    """Traegt den tatsaechlichen Einstiegskurs nach.

    Entschieden wird auf dem Schlusskurs von Tag T, eingebucht zur Eroeffnung
    von T+1. Wer die Rendite ab dem Schlusskurs von T rechnet, auf dem die
    Entscheidung beruhte, hat ein Datenleck und misst einen Vorsprung, den es
    nicht gibt.
    """
    store = store or ShadowStore()
    offen = store.offene_einbuchungen()
    if offen.empty:
        if verbose:
            print("      nichts einzubuchen")
        return 0

    # STABILES Universum laden statt der schrumpfenden Teilmenge der offenen
    # Vorhersagen - sonst trifft der Tages-Cache nie und es wird bei jedem
    # stuendlichen Durchlauf neu von yfinance geladen (siehe
    # `_universum_symbole`). Alle benoetigten Symbole sind darin enthalten,
    # weil jeder Kandidat aus genau diesem Universum stammt.
    symbols = _universum_symbole(cfg)
    run_id = store.start_run("einbuchen", n_symbols=len(symbols))
    try:
        bars = lade_bars(symbols, cfg.years, verbose=verbose)
        n = 0
        for _, p in offen.iterrows():
            try:
                df = bars.xs(p["symbol"], level="symbol").sort_index()
            except KeyError:
                continue
            as_of = pd.Timestamp(p["as_of"])
            if as_of.tz is None:
                as_of = as_of.tz_localize("UTC")

            idx = pd.DatetimeIndex(df.index)
            if idx.tz is None:
                idx = idx.tz_localize("UTC")
            spaeter = idx[idx > as_of]
            if len(spaeter) == 0:
                continue                      # naechster Handelstag noch nicht da
            entry_date = spaeter[0]
            bar = df.loc[df.index[idx.get_loc(entry_date)]]

            p_open = float(bar["open"])
            if not np.isfinite(p_open) or p_open <= 0:
                continue

            # Kosten wie in der Simulation - ohne sie waere der Schatten
            # systematisch besser als jeder echte Trade.
            qty = max(1, int((p["notional"] or p_open) / p_open))
            k = estimate_costs("buy", qty, last=p_open,
                               spread_bps=cfg.spread_bps,
                               slippage_bps=cfg.slippage_bps, fees=DEFAULT_FEES)

            store.save_fill(
                p["pred_id"],
                entry_date=entry_date.isoformat(),
                entry_price_open=p_open,
                entry_price=p_open,
                entry_price_eff=float(k.effective_price),
                # Phase 1 bucht zur Eroeffnung. Der Live-Bot handelt ~20 Min
                # spaeter; §0.1 hat diese Differenz mit -0,58 bps (t=-0,18)
                # als unerheblich gemessen. Phase 2 (Spiegelbuch) verfeinert.
                entry_timing="open",
            )
            n += 1
        store.finish_run(run_id, "ok")
        if verbose:
            print(f"      {n} Vorhersage(n) eingebucht")
        return n
    except Exception as e:  # noqa: BLE001
        store.finish_run(run_id, "fehler", f"{type(e).__name__}: {e}")
        raise


# ---------------------------------------------------------------------------
# Schritt 3: Verifizieren
# ---------------------------------------------------------------------------
def lernen(cfg: ShadowConfig, store: ShadowStore | None = None,
           *, verbose: bool = True) -> int:
    """Der Lernschritt: Muster pruefen, Kandidaten suchen, Zerfall melden.

    **Warum das ein eigener Schritt im Dauerbetrieb ist.** Der
    Musterspeicher (`patterns.py`) war vollstaendig gebaut - mit
    Verfallspruefung auf ausschliesslich NEUEN Daten, Mindestzahl an
    Handelstagen und Zerfallsmeldung. Er wurde nur nie aufgerufen: Am
    22.08.2026 enthielt die Tabelle `muster` **null Zeilen**. Der Daemon
    kannte nur einbuchen/verifizieren/entscheiden.

    Das ist der Unterschied zwischen "das System koennte lernen" und "das
    System lernt".

    **Warum er nur bei neuen Daten laeuft.** Zweimal am selben Tag
    gerechnet liefert er bitgleich dasselbe - er wuerde nur Rechenzeit und
    Protokollzeilen erzeugen. Gesteuert ueber denselben Gedanken wie der
    Aktualitaetsfilter in `verifizieren`: Ohne neuen Handelstag gibt es
    nichts Neues zu lernen.

    **Was er ausdruecklich NICHT tut:** Er aendert keine Handelsregel. Ein
    bestaetigtes Muster ist eine Beobachtung mit Beleg und Verfallsdatum,
    kein Signal. Der Weg von dort in die Handelslogik fuehrt weiterhin
    ueber eine Voranmeldung in der Flotte (CLAUDE.md).
    """
    from . import patterns

    store = store or ShadowStore()
    letzter = store.letzter_lerntag()
    with store._conn() as c:
        row = c.execute("SELECT MAX(as_of) FROM predictions").fetchone()
    neuester = (row[0] or "")[:10]
    if not neuester:
        return 0
    if letzter == neuester:
        if verbose:
            print(f"      kein neuer Handelstag seit {letzter} - nichts zu lernen")
        return 0

    run_id = store.start_run("lernen")
    try:
        gepruefte = patterns.pruefen(store, verbose=verbose)
        kandidaten = patterns.kandidaten_suchen(store, anlegen=True, verbose=verbose)
        store.setze_lerntag(neuester)
        n = len(gepruefte) + len(kandidaten)
        if verbose:
            zerfallen = (gepruefte["status"] == "zerfallen").sum() if not gepruefte.empty else 0
            print(f"      {len(gepruefte)} Muster geprueft, {zerfallen} zerfallen, "
                  f"{len(kandidaten)} Kandidatenschnitte")
        store.finish_run(run_id, "ok")
        return int(n)
    except Exception as e:  # noqa: BLE001
        store.finish_run(run_id, "fehler", f"{type(e).__name__}: {e}")
        raise


def verifizieren(cfg: ShadowConfig, store: ShadowStore | None = None,
                 *, verbose: bool = True) -> int:
    """Was ist tatsaechlich daraus geworden?

    Berechnet drei Dinge getrennt:

      1. Horizontrenditen (1/3/5/10/20 Tage) - UNABHAENGIG von Stop und Ziel.
         Grundlage jeder kontrafaktischen Rechnung (Plan §7.2).
      2. Den Ausstieg nach den geplanten Regeln (Stop/Ziel/Zeit) inkl. Kosten.
      3. Die Referenzen: SPY und Universums-Median ueber denselben Zeitraum.
         Ohne sie ist die Rendite bedeutungslos - ein Schattenbuch mit +3 % in
         einer Woche, in der das Universum +4 % machte, ist ein Verlust.
    """
    store = store or ShadowStore()
    offen = store.offene_ergebnisse()
    if offen.empty:
        if verbose:
            print("      nichts zu verifizieren")
        return 0

    # STABILES Universum statt der schrumpfenden Teilmenge - siehe Begruendung
    # in `einbuchen()` und `_universum_symbole()`.
    symbols = _universum_symbole(cfg)
    run_id = store.start_run("verifizieren", n_symbols=len(symbols))
    try:
        bars = lade_bars(symbols, cfg.years, verbose=verbose)
        try:
            spy = bars.xs(MARKET_SYMBOL, level="symbol").sort_index()["close"].astype(float)
        except KeyError:
            spy = None

        # --- Nur rechnen, was sich seit der letzten Auswertung aendern KONNTE ---
        #
        # Eine Vorhersage bleibt offen, bis `fwd_20d` gefuellt ist - also
        # 20 Handelstage lang. Der Dauerbetrieb lief bis zum 22.08.2026
        # stuendlich ueber ALLE offenen Vorhersagen: gemessen 19.788 Stueck,
        # rund 24-mal am Tag, also ~475.000 Auswertungen taeglich fuer
        # NULL neue Information. Ein Ergebnis kann sich nur aendern, wenn
        # eine neue Tagesbar dazugekommen ist; innerhalb eines Handelstages
        # ist jede Wiederholung bitgleich.
        #
        # Verglichen wird gegen den juengsten geladenen Bar, nicht gegen die
        # Uhrzeit: Am Wochenende und an Feiertagen kommt keine Bar dazu, und
        # eine kalendarische Regel wuerde dort weiter sinnlos rechnen.
        offen_gesamt = len(offen)
        try:
            neuester_bar = pd.DatetimeIndex(
                bars.index.get_level_values("timestamp")).max()
            if neuester_bar.tzinfo is None:
                neuester_bar = neuester_bar.tz_localize("UTC")
            bewertet = pd.to_datetime(offen.get("evaluated_at"), format="mixed",
                                      utc=True, errors="coerce")
            # `>=` waere falsch: eine Auswertung GENAU zum Bar-Zeitstempel
            # hat diesen Bar noch nicht gesehen.
            aktuell = bewertet.notna() & (bewertet > neuester_bar)
            offen = offen[~aktuell]
        except Exception as e:  # noqa: BLE001 - im Zweifel lieber alles rechnen
            if verbose:
                print(f"      Aktualitaetsfilter uebersprungen ({type(e).__name__})")

        if verbose and offen_gesamt:
            print(f"      {len(offen):,} von {offen_gesamt:,} offenen Vorhersagen "
                  f"koennen sich geaendert haben")
        if offen.empty:
            store.finish_run(run_id, "ok")
            return 0

        # Universums-Median je Stichtag: die Referenz, gegen die der
        # Ueberschuss gerechnet wird (Plan §3.1).
        uni_median: dict[str, float] = {}
        jetzt = dt.datetime.now(dt.UTC).isoformat()
        n = 0

        for _, p in offen.iterrows():
            try:
                df = bars.xs(p["symbol"], level="symbol").sort_index()
            except KeyError:
                continue
            idx = pd.DatetimeIndex(df.index)
            if idx.tz is None:
                idx = idx.tz_localize("UTC")
            df = df.copy()
            df.index = idx

            entry_date = pd.Timestamp(p["entry_date"])
            if entry_date.tz is None:
                entry_date = entry_date.tz_localize("UTC")
            if entry_date not in df.index:
                continue
            pos = int(df.index.get_loc(entry_date))
            close = df["close"].astype(float)
            entry = float(p["entry_price"])
            if entry <= 0:
                continue

            # --- Datenpruefung: wurde der Kurs rueckwirkend angepasst? ---
            # yfinance laedt mit auto_adjust=True; nach Dividende oder Split
            # aendern sich HISTORISCHE Kurse. Der gespeicherte Wert wird
            # deshalb NIE ueberschrieben, die Abweichung nur vermerkt.
            check = "ok"
            neu_open = float(df["open"].iloc[pos])
            if p["entry_price_open"] and abs(neu_open / float(p["entry_price_open"]) - 1) > 0.005:
                check = "kurs_angepasst"

            # --- 1. Horizontrenditen, unabhaengig von Stop/Ziel ---
            fwd = {}
            for h in HORIZONTE:
                fwd[f"fwd_{h}d"] = (
                    round(float(close.iloc[pos + h] / entry - 1), 5)
                    if pos + h < len(close) else None
                )

            # --- 2. Ausstieg nach den geplanten Regeln ---
            stop = float(p["planned_stop"] or 0)
            ziel = float(p["planned_target"] or 0)
            halte = int(p["planned_hold_days"] or 5)
            exit_date = exit_price = None
            grund = None
            ziel_erreicht = stop_erreicht = 0
            mae = mfe = None

            fenster = df.iloc[pos: pos + halte + 1]
            if len(fenster) > 1:
                lows = fenster["low"].astype(float)
                highs = fenster["high"].astype(float)
                mae = round(float(lows.min() / entry - 1), 5)
                mfe = round(float(highs.max() / entry - 1), 5)

                for j in range(1, len(fenster)):
                    tag = fenster.iloc[j]
                    lo, hi = float(tag["low"]), float(tag["high"])
                    if stop > 0 and lo <= stop:
                        # Kursluecke: nicht besser als die Eroeffnung
                        exit_price = min(stop, float(tag["open"]))
                        grund, stop_erreicht = "stop_ausgeloest", 1
                    elif ziel > 0 and hi >= ziel:
                        exit_price = max(ziel, float(tag["open"]))
                        grund, ziel_erreicht = "gewinnziel_erreicht", 1
                    if grund:
                        exit_date = fenster.index[j]
                        break
                if grund is None and len(fenster) > halte:
                    exit_date = fenster.index[-1]
                    exit_price = float(fenster["close"].iloc[-1])
                    grund = "zeitausstieg"

            row = {"pred_id": p["pred_id"], "evaluated_at": jetzt,
                   "data_check": check, "mae_pct": mae, "mfe_pct": mfe,
                   "ziel_erreicht": ziel_erreicht, "stop_erreicht": stop_erreicht,
                   **fwd}

            if exit_price and exit_date is not None:
                qty = max(1, int((p["notional"] or entry) / entry))
                k = estimate_costs("sell", qty, last=exit_price,
                                   spread_bps=cfg.spread_bps,
                                   slippage_bps=cfg.slippage_bps, fees=DEFAULT_FEES)
                eff_in = float(p["entry_price_eff"] or entry)
                eff_out = float(k.effective_price)
                row.update({
                    "exit_date": exit_date.isoformat(),
                    "exit_price": exit_price,
                    "exit_price_eff": eff_out,
                    "exit_reason": grund,
                    "return_brutto": round(exit_price / entry - 1, 5),
                    "return_pct": round(eff_out / eff_in - 1, 5),
                    "kosten": round(abs(eff_out - exit_price) + abs(eff_in - entry), 4),
                    "bars_held": int(df.index.get_loc(exit_date) - pos),
                })

            # --- 3. Referenzen ---
            if spy is not None and fwd.get("fwd_5d") is not None:
                s_idx = pd.DatetimeIndex(spy.index)
                if s_idx.tz is None:
                    s_idx = s_idx.tz_localize("UTC")
                sp = spy.copy()
                sp.index = s_idx
                if entry_date in sp.index:
                    sp_pos = int(sp.index.get_loc(entry_date))
                    if sp_pos + 5 < len(sp):
                        row["bench_fwd_5d"] = round(
                            float(sp.iloc[sp_pos + 5] / sp.iloc[sp_pos] - 1), 5)

            store.save_outcome(row)
            n += 1

        # --- Universums-Median und Ueberschuss nachtragen ---
        _trage_ueberschuss_nach(store)

        store.finish_run(run_id, "ok")
        if verbose:
            print(f"      {n} Ergebnis(se) bewertet")
        return n
    except Exception as e:  # noqa: BLE001
        store.finish_run(run_id, "fehler", f"{type(e).__name__}: {e}")
        raise


def _trage_ueberschuss_nach(store: ShadowStore) -> None:
    """Ueberschuss = eigene Rendite minus Median des Universums am selben Tag.

    Muss NACH allen Einzelergebnissen laufen, weil der Median erst feststeht,
    wenn alle Vorhersagen eines Stichtags bewertet sind.
    """
    with store._conn() as c:
        df = pd.read_sql_query(
            "SELECT o.pred_id, o.fwd_5d, p.as_of FROM shadow_outcomes o"
            " JOIN predictions p ON o.pred_id = p.pred_id"
            " WHERE o.fwd_5d IS NOT NULL",
            c,
        )
        if df.empty:
            return
        med = df.groupby("as_of")["fwd_5d"].median()
        for _, r in df.iterrows():
            m = float(med.loc[r["as_of"]])
            c.execute(
                "UPDATE shadow_outcomes SET universum_fwd_5d=?, ueberschuss_5d=?"
                " WHERE pred_id=?",
                (round(m, 5), round(float(r["fwd_5d"]) - m, 5), r["pred_id"]),
            )


# ---------------------------------------------------------------------------
# Korrektheitspruefungen (Plan §14)
# ---------------------------------------------------------------------------
@dataclass
class Befund:
    """Ergebnis einer Pruefung. `ok=False` heisst: hier stimmt etwas nicht."""

    nummer: int
    name: str
    ok: bool
    text: str

    def __str__(self) -> str:
        marke = "OK  " if self.ok else "FEHL"
        return f"  [{marke}] {self.nummer}. {self.name}\n         {self.text}"


def pruefungen(store: ShadowStore | None = None, *,
               mit_replay: bool = False) -> list[Befund]:
    """Die acht Pruefungen aus docs/schattenbetrieb.md §14.

    Ein Schattenbuch, dem man nicht trauen kann, ist schlimmer als keines -
    es erzeugt Zahlen, die aussehen wie Erkenntnis. Diese Pruefungen laufen
    auf den GESPEICHERTEN Daten und brauchen keine Wochen Vorlauf.
    """
    s = store or ShadowStore()
    out: list[Befund] = []
    p = s.table("predictions")

    # --- 1. Lookahead: Einstieg muss NACH dem Stichtag liegen ---
    if p.empty:
        out.append(Befund(1, "Lookahead-Sperre", True, "Noch keine Vorhersagen."))
    else:
        g = p.dropna(subset=["entry_date"])
        if g.empty:
            out.append(Befund(1, "Lookahead-Sperre", True,
                              "Noch nichts eingebucht."))
        else:
            a = pd.to_datetime(g["as_of"], format="mixed", utc=True)
            e = pd.to_datetime(g["entry_date"], format="mixed", utc=True)
            verletzt = int((e <= a).sum())
            out.append(Befund(
                1, "Lookahead-Sperre", verletzt == 0,
                f"{len(g):,} eingebuchte Vorhersagen geprueft, {verletzt} mit "
                "Einstieg am oder vor dem Stichtag."
                + ("" if verletzt == 0 else
                   "  DATENLECK: Die Rendite waere teilweise schon bekannt gewesen."),
            ))

    # --- 2. Kalender: Stichtag darf nicht in der Zukunft liegen ---
    if not p.empty:
        a = pd.to_datetime(p["as_of"], format="mixed", utc=True)
        zukunft = int((a > pd.Timestamp.now(tz="UTC")).sum())
        out.append(Befund(2, "Kalenderpruefung", zukunft == 0,
                          f"{zukunft} Vorhersage(n) mit Stichtag in der Zukunft."))

    # --- 3. Abgleich mit dem echten Bot ---
    out.append(_pruefe_gegen_depot(s))

    # --- 4. Kursanpassung (yfinance auto_adjust) ---
    out.append(_pruefe_kursanpassung(s))

    # --- 5. Kostenkontrolle gegen das echte Depot ---
    out.append(_pruefe_kosten(s))

    # --- 6. Replay gegen simulate.py (teuer, nur auf Anforderung) ---
    if mit_replay:
        out.append(_pruefe_replay(s))
    else:
        out.append(Befund(6, "Replay gegen simulate.py", True,
                          "uebersprungen (--replay zum Ausfuehren)"))

    # --- 7. Flottenkonsistenz: kein Bot darf einen Tag UEBERSPRINGEN ---
    if p.empty:
        out.append(Befund(7, "Flottenkonsistenz", True, "Noch keine Vorhersagen."))
    else:
        r = p[p["buch"] == "rangliste"]
        alle_tage = sorted(r["as_of"].unique())

        # Gleich VIELE Stichtage zu verlangen waere falsch: Ein spaeter
        # angemeldeter Bot hat zwangslaeufig eine kuerzere Historie, ohne dass
        # etwas kaputt ist (B07/B08 kamen am 2026-07-30 dazu). Der gepaarte
        # Vergleich schneidet ohnehin auf die gemeinsamen Tage.
        #
        # Wirklich schaedlich waere eine LUECKE: ein Bot, der an einem Tag
        # zwischen seinem ersten und letzten Lauf nichts geliefert hat. Dann
        # fehlt genau dieser Tag im Vergleich, und zwar unbemerkt.
        luecken = []
        for bot, g in r.groupby("bot_id"):
            tage = sorted(g["as_of"].unique())
            spanne = [t for t in alle_tage if tage[0] <= t <= tage[-1]]
            fehlend = set(spanne) - set(tage)
            if fehlend:
                luecken.append(f"{bot}: {len(fehlend)} Tag(e)")

        out.append(Befund(
            7, "Flottenkonsistenz", not luecken,
            f"{r['bot_id'].nunique()} Bot(s) ueber {len(alle_tage)} Stichtag(e), "
            "keine Luecken." if not luecken else
            f"LUECKEN gefunden - {'; '.join(luecken)}. Fehlende Tage machen den "
            "gepaarten Vergleich still unvollstaendig."
        ))

    # --- 8. Buchfuehrung: keine Luecken ---
    out.append(_pruefe_buchfuehrung(s))

    # --- 9. Nachtrags-Disziplin (Plan §4.6) ---
    if not p.empty and "nachgetragen" in p:
        n_nach = int(p["nachgetragen"].fillna(0).sum())
        out.append(Befund(
            9, "Nachtrags-Disziplin", True,
            f"{n_nach} nachgetragene Vorhersage(n). Sie zaehlen in KEINER "
            "Vorwaertsstatistik mit (shadow_eval filtert sie heraus)."
        ))

    # --- 10. Handelt der Spiegel ueberhaupt wie der Live-Bot? ---
    out.append(_pruefe_handelsrhythmus(s))
    return out


LIVE_SPIEGEL_BOT = "B09_nachkauf"
"""Der Bot, der laut §G6 die Live-Konfiguration traegt.

Feldweise deckungsgleich (gesichert in `tests/test_konsistenz.py`) - was
NICHT heisst, dass er sich auch gleich VERHAELT. Genau diese Luecke
prueft `_pruefe_handelsrhythmus`."""


def _pruefe_handelsrhythmus(s: ShadowStore) -> Befund:
    """Deckt sich das Handelsverhalten des Spiegels mit dem echten Bot?

    **Der Unterschied zu Pruefung 3.** Jene vergleicht KURSE (yfinance
    gegen Alpaca). Diese vergleicht, WAS getan wird - und dort lag ein
    Fund, den keine Konfigurationspruefung finden konnte (§G16).

    `max_new_positions=3` bedeutet an den zwei Orten Verschiedenes:

        live.run_once   3 Kaeufe je ZYKLUS - der Daemon laeuft alle 15 Min,
                        also bis zu 26-mal am Handelstag
        shadow._spiegel 3 Kaeufe je HANDELSTAG - der Tagesbar-Rhythmus
                        kennt nur einen Durchgang

    Gemessen am 22.08.2026: Der Live-Bot eroeffnete am 28.07. **50
    Positionen an einem Tag**; das Spiegelbuch schafft konstruktions-
    bedingt drei. Folge: Live steht bei 15/15 Positionen und 91 %
    investiert, `B09_nachkauf` bei 11/15 und 64 %.

    Daraus folgt der eigentliche Schaden. `Engine._find_topups` bekommt
    das von `_find_entries` bereits verplante Kapital abgezogen. Solange
    Plaetze frei sind, ist dieser Betrag das gesamte freie Kapital -
    also gibt es **nie** Nachkaeufe. Erst im vollen Depot (`slots = 0`,
    `entries = []`, `verplant = 0`) entstehen sie. Deshalb:

        Live-Journal   110 topup von 304 Entscheidungen (36 %)
        Spiegelbuch      0 topup von  51 Kaeufen

    `B09_nachkauf` ist damit ueber seine gesamte Laufzeit **bitgleich mit
    `B08_voll_investiert`** - seine Achse (`allow_topup`) hat nie
    gebunden. Er belegt einen Flottenplatz, hebt die Schwelle fuer alle
    (§B2) und misst nichts. Und `B11_dyn_ausstieg_live` wird laut
    BETRIEBSPLAN §3.3 gegen genau diesen Bot geprueft.

    **Warum das hier nur gemeldet und nicht behoben wird:** Beides waere
    eine Aenderung der Handelslogik waehrend einer laufenden Messung -
    CLAUDE.md verbietet das ausdruecklich. Der Weg fuehrt ueber einen
    eigenen Flottenbot nach dem 10.10.2026.
    """
    try:
        from .journal import JOURNAL_DB

        with sqlite3.connect(JOURNAL_DB) as c:
            live = pd.read_sql(
                "SELECT d.action, COUNT(*) n FROM decisions d"
                " JOIN runs r ON d.run_id = r.run_id"
                " WHERE r.script = 'live_trade' AND d.blocked_by IS NULL"
                " GROUP BY d.action", c)
    except Exception as e:  # noqa: BLE001
        return Befund(10, "Handelsrhythmus Live gegen Spiegel", True,
                      f"nicht durchfuehrbar: {type(e).__name__}: {e}")

    if live.empty:
        return Befund(10, "Handelsrhythmus Live gegen Spiegel", True,
                      "Noch keine Live-Entscheidungen.")

    sp = s.table("predictions", "buch = 'spiegel' AND bot_id = ?",
                 (LIVE_SPIEGEL_BOT,))
    if sp.empty:
        return Befund(10, "Handelsrhythmus Live gegen Spiegel", True,
                      f"{LIVE_SPIEGEL_BOT} hat noch nicht gehandelt.")

    je_live = dict(zip(live["action"], live["n"]))
    n_live_top = int(je_live.get("topup", 0))
    n_live_ges = int(sum(je_live.values()))
    n_sp_top = int((sp["aktion"] == "topup").sum())

    anteil_live = n_live_top / max(1, n_live_ges)
    # Der Spiegel muss nicht denselben ANTEIL treffen - er sieht andere
    # Tage. Ein Befund ist erst, dass eine ganze Aktionsart FEHLT,
    # obwohl sie live ein Drittel ausmacht.
    ok = not (n_live_top > 0 and n_sp_top == 0 and anteil_live > 0.05)

    return Befund(
        10, "Handelsrhythmus Live gegen Spiegel", ok,
        f"Live: {n_live_top} von {n_live_ges} Entscheidungen sind Nachkaeufe "
        f"({anteil_live:.0%}). {LIVE_SPIEGEL_BOT}: {n_sp_top} von {len(sp)}."
        + ("" if ok else
           f"  ABWEICHUNG: Der Spiegel fuehrt eine Aktionsart gar nicht aus, "
           f"die live ein {anteil_live:.0%}-Anteil ist. Ursache: "
           f"`max_new_positions` wirkt live je ZYKLUS (bis 26/Tag), im "
           f"Spiegel je HANDELSTAG - das Spiegeldepot wird nie voll, und "
           f"Nachkaeufe entstehen nur im vollen Depot (§G16). "
           f"{LIVE_SPIEGEL_BOT} ist damit KEIN Live-Spiegel, obwohl seine "
           f"Konfiguration feldweise stimmt.")
    )


def _pruefe_gegen_depot(s: ShadowStore) -> Befund:
    """Was der Live-Bot gekauft hat, muss das Spiegelbuch auch gekauft haben.

    Zugleich ein laufender Test von yfinance gegen Alpaca: Weichen die
    Einstiegskurse stark ab, forscht man auf anderen Daten, als man handelt.
    """
    try:
        from .journal import Journal

        echte = Journal().table("orders", "dry_run = 0 AND side = 'buy'")
        if echte.empty:
            return Befund(3, "Abgleich mit dem Depot", True,
                          "Noch keine echten Kaeufe im Depot.")
        spiegel = s.table("predictions", "buch = 'spiegel' AND aktion = 'buy'")
        if spiegel.empty:
            return Befund(3, "Abgleich mit dem Depot", True,
                          "Spiegelbuch hat noch nicht gehandelt - "
                          "Abgleich ab dem ersten gemeinsamen Handelstag.")

        echte["tag"] = pd.to_datetime(echte["ts"], format="mixed", utc=True).dt.date
        spiegel["tag"] = pd.to_datetime(spiegel["entry_date"], format="mixed",
                                        utc=True).dt.date
        gemeinsame = set(echte["tag"]) & set(spiegel["tag"])
        if not gemeinsame:
            return Befund(3, "Abgleich mit dem Depot", True,
                          "Noch kein gemeinsamer Handelstag.")

        # Bewusst die VERTEILUNG pruefen, nicht einzelne Trades: Der Live-Bot
        # kauft ~20 Minuten nach Eroeffnung, der Schatten zur Eroeffnung.
        # Einzelne Werte bewegen sich in dieser Spanne leicht um mehr als
        # 0,5 % - das ist Marktrauschen, kein Fehler. Ein Problem waere erst
        # eine SYSTEMATISCHE Verschiebung (Median), etwa durch abweichende
        # Split-/Dividendenanpassung zwischen yfinance und Alpaca.
        abweichungen = []
        for _, e in echte[echte["tag"].isin(gemeinsame)].iterrows():
            m = spiegel[(spiegel["symbol"] == e["symbol"])
                        & (spiegel["tag"] == e["tag"])]
            if m.empty or not e.get("fill_price") or float(e["fill_price"]) <= 0:
                continue
            abweichungen.append(
                float(m["entry_price"].iat[0]) / float(e["fill_price"]) - 1
            )
        if not abweichungen:
            return Befund(3, "Abgleich mit dem Depot", True,
                          "Noch keine vergleichbaren Kaeufe mit Fuellpreis.")
        a = pd.Series(abweichungen)
        median_bps = float(a.median() * 10_000)
        ok = abs(median_bps) < 50          # 50 bps = Schwelle aus datasources
        return Befund(
            3, "Abgleich mit dem Depot", ok,
            f"{len(a)} gemeinsame Kaeufe. Median-Abweichung yfinance gegen "
            f"Alpaca: {median_bps:+.1f} bps (Streuung "
            f"{float(a.std(ddof=0) * 10_000):.0f} bps)."
            + ("" if ok else "  ZU GROSS - unterschiedliche Kursanpassung, "
                             "Forschung und Handel laufen auf anderen Daten.")
        )
    except Exception as e:  # noqa: BLE001
        return Befund(3, "Abgleich mit dem Depot", True,
                      f"nicht durchfuehrbar: {type(e).__name__}: {e}")


ANPASSUNG_GRENZE = 0.15
"""Ab welchem Anteil rueckwirkend geaenderter Kurse an den JUENGSTEN
Stichtagen etwas nicht stimmt.

Bewusst grosszuegiger als die frueheren 5 %, aber auf einer ganz anderen
Grundmenge - siehe `_pruefe_kursanpassung`."""

ANPASSUNG_JUENGSTE_TAGE = 5
"""Wie viele Stichtage als 'jung' gelten. Klein genug, dass ein Ausfall
binnen einer Woche auffaellt; gross genug fuer eine Quote."""

SLIPPAGE_GRENZE_BPS = 15.0
"""Ab welchem Slippage-MEDIAN die Schattenannahme nicht mehr trägt.

Aus `docs/BETRIEBSPLAN.md` §8 uebernommen ("Slippage-Median > 15 bps ueber
30 Trades -> alle Backtest- und Schattenergebnisse neu bewerten"). §3.1
nennt zusaetzlich 8 bps als Ziel fuer die Kostentragfaehigkeit; 15 ist die
Abbruchschwelle und damit die richtige fuer eine Pruefung, die FEHL
melden darf."""


def _pruefe_kursanpassung(s: ShadowStore) -> Befund:
    """Aendert yfinance Kurse rueckwirkend - und passiert das gerade JETZT?

    **Geprueft wird die junge Kante, nicht die Historie (§G16).** Bis zum
    22.08.2026 rechnete diese Pruefung den Anteil ueber ALLE Ergebnisse
    und meldete damit dauerhaft FEHL.

    Der Grund ist strukturell: `auto_adjust=True` passt historische Kurse
    nach JEDER Dividende und jedem Split rueckwirkend an. Je aelter ein
    Stichtag, desto mehr solcher Ereignisse liegen dahinter. Gemessen je
    Stichtag:

        28.07. - 07.08.    6 % bis 25 %   (alt, viele Ereignisse seither)
        13.08. - 20.08.    0 % bis  4 %   (jung)
        kumuliert          7,7 %          -> FEHL bei 5 % Schwelle

    Die kumulierte Quote MUSS mit der Zeit wachsen. Eine Schwelle darauf
    reisst zwangslaeufig, ohne dass etwas kaputt ist - exakt der
    Fehlversuch, den `data_integrity.check_stumme_felder` schon einmal
    gemacht hat und den §G13 festhaelt: eine Quote ueber die Historie
    statt der gefaehrlichen Richtung.

    Gefaehrlich ist der umgekehrte Fall: **frische** Stichtage mit hoher
    Anpassungsrate. Das hiesse, die Kursquelle aendert Daten, die gerade
    erst entstanden sind - dann stimmt etwas mit dem Feed nicht, und
    genau dann sind die juengsten Vorhersagen betroffen.

    Die gespeicherten Kurse werden in keinem Fall ueberschrieben; die
    Abweichung wird nur vermerkt (`verifizieren`).
    """
    o = s.table("shadow_outcomes")
    p = s.table("predictions")
    if o.empty or "data_check" not in o or p.empty:
        return Befund(4, "Kursanpassung", True, "Noch keine Ergebnisse.")

    df = o[["pred_id", "data_check"]].merge(
        p[["pred_id", "as_of"]], on="pred_id", how="inner")
    if df.empty:
        return Befund(4, "Kursanpassung", True, "Noch keine Ergebnisse.")

    df["tag"] = pd.to_datetime(df["as_of"], format="mixed", utc=True).dt.date
    tage = sorted(df["tag"].unique())
    jung = set(tage[-ANPASSUNG_JUENGSTE_TAGE:])
    frisch = df[df["tag"].isin(jung)]
    if len(frisch) < 20:
        return Befund(4, "Kursanpassung", True,
                      f"Erst {len(frisch)} Ergebnis(se) an den juengsten "
                      f"Stichtagen - zu wenig fuer eine Quote.")

    anteil_jung = float((frisch["data_check"] == "kurs_angepasst").mean())
    anteil_alt = float((df["data_check"] == "kurs_angepasst").mean())
    ok = anteil_jung < ANPASSUNG_GRENZE

    # Tausenderpunkte nur auf der ZAHL bilden, nie per `.replace()` ueber
    # den fertigen Satz - das frisst die Satzkommas gleich mit (beim
    # Umbau von `fokus.hebel()` am selben Tag genau einmal passiert).
    n_frisch = f"{len(frisch):,}".replace(",", ".")
    return Befund(
        4, "Kursanpassung erkannt", ok,
        f"{anteil_jung:.1%} der {n_frisch} Ergebnisse an den juengsten "
        f"{len(jung)} Stichtagen wurden rueckwirkend angepasst "
        f"(Grenze {ANPASSUNG_GRENZE:.0%}). Ueber die ganze Historie "
        f"{anteil_alt:.1%} - dort erwartbar, weil jede Dividende die "
        f"aelteren Kurse mit anpasst. Gespeicherte Kurse wurden NICHT "
        f"ueberschrieben."
        + ("" if ok else "  AUFFAELLIG: Auch frische Kurse aendern sich - "
                         "das deutet auf ein Problem der Kursquelle, nicht "
                         "auf normale Dividendenanpassung.")
    )


def _pruefe_kosten(s: ShadowStore) -> Befund:
    """Der Schatten darf nicht guenstiger sein als das echte Depot.

    **Gemessen wird der MEDIAN, nicht der Mittelwert (§G16).** Bis zum
    22.08.2026 rechnete diese Pruefung einen n-gewichteten Mittelwert und
    meldete damit dauerhaft FEHL. An denselben 162 pruefbaren Orders:

        Median   +0,0 bps   -> Kriterium aus BETRIEBSPLAN §3.1 erfuellt
        Mittel  -71,7 bps   -> Pruefung meldet FEHL

    Die Differenz stammt aus drei Datenfehlern, die dieses Projekt selbst
    dokumentiert (§G, 04.08.2026): KGS mit -1.648 bps und SIMO mit
    -1.584 bps sind kaputte IEX-Quotes, keine Ausfuehrungsqualitaet.
    Genau gegen solche Artefakte ist der Median robust - und genau
    deshalb nennt der Entscheidungsvertrag ihn, an beiden Stellen
    (§3.1 und §8).

    Eine Pruefung, die eine andere Kennzahl misst als der Vertrag, den
    sie ueberwacht, erzeugt einen dauerhaften Fehlalarm in der
    wichtigsten Zahl des Projekts - und eine Warnung, die immer
    leuchtet, wird weggeklickt (`docs/LERNTEMPO.md` §5).

    **Zum Vorzeichen:** `journal.order()` rechnet so, dass POSITIV
    "schlechter als erwartet" heisst (fuer Verkaeufe negiert). Ein
    negativer Wert ist also guenstige Ausfuehrung - dann ist die
    Schattenannahme zu vorsichtig, nicht zu optimistisch. Die alte
    Meldung behauptete unabhaengig vom Vorzeichen das Gegenteil.
    """
    try:
        from .journal import Journal

        angesetzt = 3.0
        MIN_FUELLUNGEN = 30   # wie BETRIEBSPLAN §3.1/§8: "ueber 30 Trades"

        # Median ueber die einzelnen ORDERS, nicht ueber Symbol-Mediane.
        # §3.1 sagt woertlich "ueber 30+ saubere Orders". Ein Median ueber
        # Symbole gewichtet ein Symbol mit einer Fuellung genauso wie eines
        # mit sechs - gemessen am 22.08.2026: 73 Symbole, 178 Fuellungen.
        werte = Journal().slippage_werte().dropna()
        n_gesamt = len(werte)

        if n_gesamt < MIN_FUELLUNGEN or not np.isfinite(werte).any():
            # Kein messbarer Wert ist KEIN Fehlschlag: Slippage steht erst
            # fest, wenn genug echte Orders mit Fuellpreis UND Referenzkurs
            # vorliegen. Ein "nan" als Verstoss zu melden waere ein Fehlalarm.
            return Befund(5, "Kostenkontrolle", True,
                          f"Im Depot erst {n_gesamt} Fuellung(en) mit "
                          f"gemessener Slippage - zu wenig fuer eine "
                          f"belastbare Aussage (noetig {MIN_FUELLUNGEN}, "
                          f"BETRIEBSPLAN §3.1). Schattenannahme "
                          f"{angesetzt:.1f} bps bleibt vorlaeufig.")

        echt = float(werte.median())
        ok = abs(echt) <= SLIPPAGE_GRENZE_BPS

        # Ausreisser bleiben sichtbar - sie sind Information, kein Rauschen.
        # Ein stiller Median waere die andere Haelfte desselben Fehlers.
        gross = werte[werte.abs() > 100]
        zusatz = ""
        if len(gross):
            zusatz = (f"  {len(gross)} von {n_gesamt} Order(s) ueber |100| bps "
                      f"(groesste {gross.abs().max():.0f}) - pruefen, ob "
                      f"Datenfehler (§G) oder echte Bewegung; der Median "
                      f"traegt sie nicht mit.")

        richtung = ("" if ok else
                    ("  Schatten ist zu optimistisch - Annahme anheben."
                     if echt > 0 else
                     "  Ausfuehrung ist besser als angenommen - die "
                     "Schattenannahme ist zu vorsichtig, nicht zu lasch."))

        return Befund(
            5, "Kostenkontrolle", ok,
            f"Depot misst {echt:+.1f} bps Slippage (Median ueber "
            f"{n_gesamt} Orders), Schatten setzt {angesetzt:.1f} bps an. "
            f"Grenze {SLIPPAGE_GRENZE_BPS:.0f} bps (§8), Ziel < 8 bps "
            f"(§3.1)." + richtung + zusatz
        )
    except Exception as e:  # noqa: BLE001
        return Befund(5, "Kostenkontrolle", True,
                      f"nicht durchfuehrbar: {type(e).__name__}: {e}")


def _pruefe_replay(s: ShadowStore) -> Befund:
    """Erzeugt der Schattencode dieselben Entscheidungen wie simulate.py?

    Beide rufen `Engine.decide()`. Weichen sie ab, ist einer von beiden
    falsch - und dann taugt der Vergleich zwischen Simulation und Schatten
    grundsaetzlich nicht.
    """
    try:
        from . import simulate as sim
        from . import universe as U

        syms = list(dict.fromkeys([*U.BENCHMARK_SETS["broad_liquid"][:40],
                                   MARKET_SYMBOL]))
        bars = lade_bars(syms, 2.0, verbose=False)
        markt = bars.xs(MARKET_SYMBOL, level="symbol")["close"].astype(float)
        res = sim.run(bars, engine_config=EngineConfig.for_reversal(),
                      sim_config=sim.SimConfig(initial_cash=100_000,
                                               log_to_journal=False),
                      market=markt, verbose=False)
        n = len(res.trades)
        return Befund(6, "Replay gegen simulate.py", True,
                      f"simulate.py laeuft auf denselben Daten durch "
                      f"({n} Trades). Beide nutzen Engine.decide().")
    except Exception as e:  # noqa: BLE001
        return Befund(6, "Replay gegen simulate.py", False,
                      f"FEHLGESCHLAGEN: {type(e).__name__}: {e}")


def _pruefe_buchfuehrung(s: ShadowStore) -> Befund:
    """Luecken werden gemeldet, nicht geschaetzt."""
    p = s.table("predictions")
    if p.empty:
        return Befund(8, "Buchfuehrung", True, "Noch keine Vorhersagen.")

    heute = pd.Timestamp.now(tz="UTC").normalize()
    a = pd.to_datetime(p["as_of"], format="mixed", utc=True)
    # Vorhersagen, deren Folgetag laengst vorbei ist, muessen eingebucht sein.
    faellig = p[(a < heute - pd.Timedelta(days=4)) & p["entry_price"].isna()]
    o = s.table("shadow_outcomes")
    eingebucht = p[p["entry_price"].notna()]
    ohne_ergebnis = (len(eingebucht) - len(o)) if not eingebucht.empty else 0

    probleme = []
    if len(faellig):
        probleme.append(f"{len(faellig)} ueberfaellige Vorhersage(n) ohne "
                        "Einstiegskurs")
    if ohne_ergebnis > 0:
        probleme.append(f"{ohne_ergebnis} eingebuchte ohne Ergebnis "
                        "(normal, solange der Horizont laeuft)")
    return Befund(
        8, "Buchfuehrung", len(faellig) == 0,
        "; ".join(probleme) if probleme else
        f"{len(p):,} Vorhersagen, {len(eingebucht):,} eingebucht, "
        f"{len(o):,} bewertet - keine Luecken.",
    )


def pruefbericht(store: ShadowStore | None = None, *,
                 mit_replay: bool = False) -> str:
    befunde = pruefungen(store, mit_replay=mit_replay)
    n_fehl = sum(1 for b in befunde if not b.ok)
    L = ["=" * 78, "  KORREKTHEITSPRUEFUNGEN DES SCHATTENBETRIEBS", "=" * 78, ""]
    L += [str(b) for b in befunde]
    L += ["", "=" * 78,
          f"  {len(befunde) - n_fehl} von {len(befunde)} Pruefungen bestanden."]
    if n_fehl:
        L.append("  ACHTUNG: Solange Pruefungen fehlschlagen, sind die Zahlen")
        L.append("  des Schattenbetriebs nicht zitierfaehig.")
    return "\n".join(L)
