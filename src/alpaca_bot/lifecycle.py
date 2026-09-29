"""Trade-Lebenslauf: was zwischen Ein- und Ausstieg wirklich passiert ist.

Bisher wusste das System von einem abgeschlossenen Trade nur Anfang und
Ende. Damit lassen sich zwei entscheidende Fragen nicht beantworten:

  * **War der Stop zu eng?** Eine Position, die knapp ausgestoppt wurde
    und danach ins Ziel gelaufen waere, sieht in der Statistik aus wie
    ein normaler Verlust - dabei war nicht die Auswahl falsch, sondern
    der Stop-Abstand.
  * **War das Ziel zu niedrig?** Ein Trade, der +8 % erreichte und bei
    +4 % verkauft wurde, zaehlt als Gewinn. Dass die Haelfte liegen
    blieb, sieht niemand.

Beide Fehlerarten sind teuer und in einer reinen Ein-/Ausstiegsstatistik
unsichtbar. Deshalb werden hier drei Dinge festgehalten:

    MAE   groesster Zwischenverlust waehrend der Haltezeit
    MFE   groesster Zwischengewinn waehrend der Haltezeit
    danach  Kursverlauf NACH dem Ausstieg (war der Ausstieg richtig?)

Aus dem Vergleich dieser Werte mit den tatsaechlichen Ein- und
Ausstiegskursen ergeben sich konkrete, pruefbare Verbesserungsvorschlaege.

**Wichtig zur Ehrlichkeit:** Dieses Modul schlaegt Anpassungen vor, es
nimmt sie nicht selbst vor. Bei zwanzig Trades ist jedes Muster Rauschen.
Wer ein System auf so duenner Grundlage automatisch nachjustiert, hat
kein lernendes System gebaut, sondern einen Zufallsgenerator mit
Gedaechtnis. `mindestanzahl` steht deshalb bewusst hoch.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import numpy as np
import pandas as pd

from .config import DATA_DIR

LIFECYCLE_DB = DATA_DIR / "lifecycle.sqlite"

SCHEMA = """
CREATE TABLE IF NOT EXISTS trades (
    trade_id        TEXT PRIMARY KEY,
    symbol          TEXT NOT NULL,
    entry_date      TEXT NOT NULL,
    entry_price     REAL NOT NULL,
    qty             REAL,
    notional        REAL,
    entry_score     REAL,
    entry_reasons   TEXT,
    planned_stop    REAL,
    planned_target  REAL,
    exit_date       TEXT,
    exit_price      REAL,
    exit_reason     TEXT,
    return_pct      REAL,
    bars_held       INTEGER,
    mae_pct         REAL,
    mfe_pct         REAL,
    mae_date        TEXT,
    mfe_date        TEXT,
    after_1d        REAL,
    after_5d        REAL,
    after_10d       REAL,
    analysed_at     TEXT
);
CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol);
CREATE INDEX IF NOT EXISTS idx_trades_exit ON trades(exit_date);
"""


class Lifecycle:
    """Speicher und Auswertung abgeschlossener Trades."""

    def __init__(self, path: Path = LIFECYCLE_DB):
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

    # --- Erfassen ----------------------------------------------------------
    def record(self, trade: dict) -> None:
        cols = [
            "trade_id", "symbol", "entry_date", "entry_price", "qty", "notional",
            "entry_score", "entry_reasons", "planned_stop", "planned_target",
            "exit_date", "exit_price", "exit_reason", "return_pct", "bars_held",
            "mae_pct", "mfe_pct", "mae_date", "mfe_date",
            "after_1d", "after_5d", "after_10d", "analysed_at",
        ]
        values = [trade.get(k) for k in cols]
        with self._conn() as c:
            c.execute(
                f"INSERT OR REPLACE INTO trades ({','.join(cols)})"
                f" VALUES ({','.join('?' * len(cols))})",
                values,
            )

    def table(self) -> pd.DataFrame:
        with self._conn() as c:
            return pd.read_sql_query("SELECT * FROM trades", c)

    def pending_analysis(self) -> list[str]:
        """Trades, deren Nachlauf noch nicht vollstaendig ausgewertet ist.

        Die Bedingung MUSS alle Nachlauf-Fenster abdecken, nicht nur das
        kuerzeste. Frueher stand hier allein `after_5d IS NULL`: Sobald
        der 5-Tage-Wert gefuellt war, verliess der Trade die Warteschlange -
        und `after_10d`, das fuenf Tage laenger braucht, wurde NIE
        nachgetragen. Bestaetigt am 15.08.2026: 36 von 36 Trades hatten
        `after_10d = None`, obwohl fuer die aelteren laengst Kurse
        vorlagen. Genau dieser Wert beantwortet aber die Frage, ob der
        Zeitausstieg nach 5 Tagen zu frueh kommt.
        """
        with self._conn() as c:
            rows = c.execute(
                "SELECT trade_id FROM trades"
                " WHERE after_1d IS NULL OR after_5d IS NULL OR after_10d IS NULL"
            ).fetchall()
        return [r["trade_id"] for r in rows]


def handelstage(entry_date, exit_ts) -> int | None:
    """Haltedauer in HANDELSTAGEN - dieselbe Rechnung wie build_portfolio.

    Kalendertage waeren hier falsch: Eine Position von Freitag bis Montag
    hat drei Kalendertage, aber nur einen Handelstag gelebt - und der
    Zeitausstieg (`max_hold_days`) rechnet in Handelstagen. Zwei
    verschiedene Zaehlweisen im selben System machen jede Auswertung nach
    Haltedauer unvergleichbar.

    **Seit dem 26.08.2026 ueber den echten Boersenkalender** (§G38). Bis
    dahin stand hier `pd.bdate_range`, das Montag bis Freitag zaehlt und
    Feiertage NICHT kennt. Simulation und Schattenbetrieb zaehlen dagegen
    Bars, und am Feiertag gibt es keine - in jeder Feiertagswoche verkaufte
    der Live-Bot damit einen Handelstag frueher als jede Messung, gegen
    die er verglichen wird.
    """
    from .handelskalender import zwischen
    if not entry_date:
        return None
    try:
        start = pd.Timestamp(entry_date)
        if start.tz is None:
            start = start.tz_localize("UTC")
        ende = pd.Timestamp(exit_ts)
        if ende.tz is None:
            ende = ende.tz_localize("UTC")
        return zwischen(start, ende)
    except Exception:  # noqa: BLE001 - Protokoll darf den Handel nie stoppen
        return None


def eintrag_anlegen(
    *, symbol: str, meta: dict, exit_price: float | None,
    exit_reason: str, return_pct: float | None, exit_ts=None,
    bars_held: int | None = None, store: Lifecycle | None = None,
) -> None:
    """Legt den Lebenslauf eines geschlossenen Trades an - EIN Ort fuer ALLE Ausstiege.

    **Warum das eine gemeinsame Funktion ist (23.08.2026, BEFUNDE §G21).**
    Bis dahin stand dieser Code ausschliesslich in
    `daemon._record_lifecycle`, also im normalen `sell`-Pfad. Der am
    15.08.2026 ergaenzte Intraday-Stop (`live.pruefe_stops_intraday`)
    schreibt seinen Ausstieg direkt ueber `state.record_exit` und ging an
    dieser Stelle vorbei.

    Gemessen am 23.08.2026, Abdeckung des Lebenslaufs je Ausstiegsgrund:

        zeitausstieg              39/39   100 %
        these_traegt_nicht_mehr   11/11   100 %
        gewinnziel_erreicht        4/4    100 %
        stop_ausgeloest            2/2    100 %
        stop_intraday              0/2      0 %   <- fehlte vollstaendig

    **Die Richtung des Fehlers wiegt schwerer als seine Groesse.** Der
    Intraday-Stop feuert per Konstruktion bei scharfen Einbruechen - er
    trifft also fast nur Verlusttrades. Die beiden fehlenden lagen bei
    -8,9 % und -7,8 %, waehrend die 56 erfassten im Mittel +3,34 %
    zeigten. Der Lernbericht war dadurch systematisch zu gut (+3,34 %
    statt +2,94 %) und nannte `stop_ausgeloest` (-5,5 %) den
    schlechtesten Ausstiegsgrund, obwohl `stop_intraday` (-8,3 %)
    schlechter war und schlicht unsichtbar blieb.

    Dass es heute nur 0,4 Prozentpunkte sind, liegt allein an n=2. Der
    Fehler waechst mit jedem Intraday-Stop und immer in dieselbe
    Richtung - genau die Sorte, die man nicht aussitzt.

    MAE, MFE und der Nachlauf bleiben hier leer: Der Kursverlauf NACH dem
    Ausstieg existiert noch nicht. Das ergaenzt
    `daemon._analyse_closed_trades()` in den Folgetagen.

    `bars_held` wird vom Aufrufer aus den DATEN gerechnet und nicht aus
    `meta` uebernommen: `position_meta.bars_held` wird beim Anlegen auf 0
    gesetzt und NIE erhoeht - die Engine berechnet den Wert zur Laufzeit
    frisch aus `entry_date` (`live.build_portfolio`), schreibt ihn aber
    nicht zurueck. Wer `meta` vertraut, schreibt fuer JEDEN Trade eine 0
    ins Protokoll (bestaetigt: 36 von 36 Trades hatten `bars_held = 0`).
    """
    import uuid

    # `state.load_positions()` liefert die Rohzeile, `reasons` ist dort
    # bereits eine TEXT-Spalte. Ein Aufrufer, der stattdessen das Dict
    # durchreicht, bekaeme sonst `sqlite3.ProgrammingError` - und weil
    # beide Aufrufer den Fehler fangen muessen (ein Ausfall hier darf den
    # Verkauf nicht rueckgaengig machen), waere das Ergebnis genau die
    # stille Luecke, die diese Funktion schliesst.
    gruende = meta.get("reasons")
    if isinstance(gruende, (dict, list)):
        gruende = json.dumps(gruende, ensure_ascii=False, default=str)

    ts = pd.Timestamp(exit_ts or pd.Timestamp.now(tz="UTC"))
    (store or Lifecycle()).record({
        "trade_id": uuid.uuid4().hex,
        "symbol": symbol,
        "entry_date": str(meta.get("entry_date") or ""),
        "entry_price": meta.get("entry_price"),
        "entry_score": meta.get("entry_score"),
        "entry_reasons": gruende,
        "planned_stop": meta.get("stop_price"),
        "planned_target": meta.get("target_price"),
        "exit_date": ts.isoformat(),
        "exit_price": exit_price,
        "exit_reason": exit_reason,
        "return_pct": return_pct,
        "bars_held": bars_held,
    })


def analyse_path(
    bars: pd.DataFrame, entry_date, exit_date, entry_price: float
) -> dict:
    """Rechnet MAE, MFE und den Nachlauf aus dem Kursverlauf aus.

    Args:
        bars: OHLCV des Symbols, muss den Zeitraum abdecken.
    """
    idx = pd.DatetimeIndex(bars.index)
    if idx.tz is None:
        idx = idx.tz_localize("UTC")
    df = bars.copy()
    df.index = idx

    start = pd.Timestamp(entry_date)
    end = pd.Timestamp(exit_date)
    for t in (start, end):
        if t.tz is None:
            t = t.tz_localize("UTC")
    start = start.tz_localize("UTC") if start.tz is None else start
    end = end.tz_localize("UTC") if end.tz is None else end

    during = df.loc[start:end]
    out: dict = {}

    if not during.empty and entry_price > 0:
        # Tiefstkurs waehrend der Haltezeit = groesster Zwischenverlust.
        low = during["low"].astype(float)
        high = during["high"].astype(float)
        out["mae_pct"] = round(float(low.min() / entry_price - 1), 4)
        out["mfe_pct"] = round(float(high.max() / entry_price - 1), 4)
        out["mae_date"] = str(low.idxmin().date())
        out["mfe_date"] = str(high.idxmax().date())

    # Nachlauf: Wie lief es weiter, nachdem wir ausgestiegen sind?
    after = df.loc[df.index > end]
    close = after["close"].astype(float)
    exit_row = df.loc[df.index <= end]
    if not exit_row.empty:
        ref = float(exit_row["close"].iloc[-1])
        for n, key in ((1, "after_1d"), (5, "after_5d"), (10, "after_10d")):
            if len(close) >= n and ref > 0:
                out[key] = round(float(close.iloc[n - 1] / ref - 1), 4)
    return out


# ---------------------------------------------------------------------------
# Auswertung: was laesst sich daraus lernen?
# ---------------------------------------------------------------------------
@dataclass
class Insight:
    thema: str
    befund: str
    grundlage: str
    vorschlag: str = ""
    belastbar: bool = False

    def __str__(self) -> str:
        tag = "[BELASTBAR]" if self.belastbar else "[zu duenn] "
        lines = [f"{tag} {self.thema}", f"            {self.befund}",
                 f"            Grundlage: {self.grundlage}"]
        if self.vorschlag:
            lines.append(f"            -> {self.vorschlag}")
        return "\n".join(lines)


def analyse(trades: pd.DataFrame, mindestanzahl: int = 30) -> list[Insight]:
    """Sucht auswertbare Muster in abgeschlossenen Trades.

    `mindestanzahl` steht bewusst hoch. Unterhalb davon werden Befunde
    zwar berechnet und angezeigt, aber als 'zu duenn' markiert - sie
    duerfen keine Parameteraenderung ausloesen. Bei 10 Trades laesst sich
    ein echter Effekt nicht von Zufall unterscheiden, und eine Anpassung
    auf dieser Grundlage macht das System schlechter, nicht besser.
    """
    out: list[Insight] = []
    if trades.empty:
        return [Insight("Datenlage", "Noch keine abgeschlossenen Trades.",
                        "0 Trades")]

    done = trades[trades["exit_date"].notna()]
    n = len(done)
    genug = n >= mindestanzahl

    # --- 1. War der Stop zu eng? ---
    stopped = done[done["exit_reason"].astype(str).str.contains("stop", na=False)]
    if len(stopped) >= 3 and "after_5d" in stopped:
        erholt = stopped[stopped["after_5d"] > 0.02]
        quote = len(erholt) / len(stopped)
        out.append(Insight(
            "Stop-Abstand",
            f"{len(erholt)} von {len(stopped)} ausgestoppten Trades stiegen "
            f"binnen 5 Tagen nach dem Ausstieg um ueber 2 % ({quote:.0%}).",
            f"{len(stopped)} ausgestoppte Trades",
            "Stop weiter setzen (stop_atr erhoehen) - der Ausstieg kam zu frueh."
            if quote > 0.5 else "Stop-Abstand wirkt angemessen.",
            belastbar=len(stopped) >= mindestanzahl,
        ))

    # --- 2. War das Ziel zu niedrig? ---
    if "mfe_pct" in done and done["mfe_pct"].notna().any():
        gewinner = done[done["return_pct"] > 0]
        if len(gewinner) >= 3:
            liegen_geblieben = (gewinner["mfe_pct"] - gewinner["return_pct"]).mean()
            out.append(Insight(
                "Gewinnziel",
                f"Im Mittel lagen {liegen_geblieben:.1%} zwischen dem hoechsten "
                f"erreichten Kurs und dem tatsaechlichen Ausstieg.",
                f"{len(gewinner)} Gewinn-Trades",
                "Ziel hoeher setzen oder Trailing-Stop nutzen."
                if liegen_geblieben > 0.03 else "Ziel wird gut ausgeschoepft.",
                belastbar=len(gewinner) >= mindestanzahl,
            ))

    # --- 3. Wie tief ging es vor dem Gewinn? ---
    if "mae_pct" in done and done["mae_pct"].notna().any():
        gewinner = done[(done["return_pct"] > 0) & done["mae_pct"].notna()]
        if len(gewinner) >= 3:
            schmerz = gewinner["mae_pct"].mean()
            out.append(Insight(
                "Zwischenverlust bei Gewinnern",
                f"Erfolgreiche Trades lagen zwischenzeitlich im Mittel "
                f"{schmerz:.1%} im Minus.",
                f"{len(gewinner)} Gewinn-Trades",
                "Ein Stop enger als dieser Wert wuerde genau die Trades "
                "abschneiden, die am Ende funktioniert haetten.",
                belastbar=len(gewinner) >= mindestanzahl,
            ))

    # --- 4. Welcher Ausstiegsgrund traegt? ---
    if len(done) >= 3:
        je_grund = done.groupby("exit_reason")["return_pct"].agg(
            n="size", mittel="mean")
        beste = je_grund["mittel"].idxmax() if len(je_grund) else None
        schlechteste = je_grund["mittel"].idxmin() if len(je_grund) else None
        if beste is not None and beste != schlechteste:
            out.append(Insight(
                "Ausstiegsgruende",
                f"Bester Grund: '{beste}' ({je_grund.loc[beste, 'mittel']:+.2%}), "
                f"schlechtester: '{schlechteste}' "
                f"({je_grund.loc[schlechteste, 'mittel']:+.2%}).",
                f"{n} abgeschlossene Trades ueber {len(je_grund)} Gruende",
                belastbar=genug,
            ))

    # --- 5. Sagt der Einstiegs-Score das Ergebnis vorher? ---
    if done["entry_score"].notna().sum() >= 10:
        korr = done["entry_score"].corr(done["return_pct"], method="spearman")
        # Das VORZEICHEN entscheidet, nicht nur die Staerke. Frueher stand
        # hier nur `abs(korr) < 0.1`, wodurch eine deutlich NEGATIVE
        # Korrelation als "sortiert in die richtige Richtung" gemeldet
        # wurde - also genau der schlimmste Fall (die Rangliste sortiert
        # verkehrt herum) als Erfolg. Beobachtet am 15.08.2026: korr =
        # -0.133 wurde gelobt.
        if abs(korr) < 0.1:
            vorschlag = ("Ein Score, der nicht mit dem Ergebnis korreliert, "
                         "sortiert die Kandidaten nicht - dann ist die "
                         "Rangliste wertlos.")
        elif korr < 0:
            vorschlag = ("ACHTUNG: Die Korrelation ist NEGATIV - hohe Scores "
                         "fuehrten zu SCHLECHTEREN Ergebnissen. Entweder ist "
                         "die Rangliste verkehrt herum, oder die Stichprobe "
                         "ist noch zu klein. Keine Regelaenderung ohne "
                         "Bestaetigung im Schattenbetrieb.")
        else:
            vorschlag = "Der Score sortiert in die richtige Richtung."
        out.append(Insight(
            "Aussagekraft des Scores",
            f"Rangkorrelation zwischen Einstiegs-Score und Ergebnis: {korr:+.3f}.",
            f"{int(done['entry_score'].notna().sum())} Trades mit Score",
            vorschlag,
            belastbar=genug,
        ))

    return out


def report(trades: pd.DataFrame, mindestanzahl: int = 30) -> str:
    """Lesbarer Lernbericht."""
    done = trades[trades["exit_date"].notna()] if not trades.empty else trades
    lines = ["=" * 74, "  WAS WIR AUS DEN ABGESCHLOSSENEN TRADES LERNEN", "=" * 74, ""]

    n = len(done)
    lines.append(f"  Abgeschlossene Trades: {n}")
    if n:
        lines.append(f"  Mittlere Rendite     : {done['return_pct'].mean():+.2%}")
        lines.append(f"  Trefferquote         : {(done['return_pct'] > 0).mean():.0%}")
        if done["mae_pct"].notna().any():
            lines.append(f"  Mittlerer Zwischentiefstand: {done['mae_pct'].mean():.2%}")
        if done["mfe_pct"].notna().any():
            lines.append(f"  Mittlerer Zwischenhoechststand: {done['mfe_pct'].mean():+.2%}")
    lines.append("")

    for ins in analyse(trades, mindestanzahl):
        lines.append(str(ins))
        lines.append("")

    if n < mindestanzahl:
        lines.append(f"  HINWEIS: Unter {mindestanzahl} Trades sind alle Befunde")
        lines.append("  Momentaufnahmen. Sie werden angezeigt, damit du die")
        lines.append("  Entwicklung verfolgen kannst - aber keiner davon")
        lines.append("  rechtfertigt bisher eine Aenderung an den Regeln.")
    return "\n".join(lines)
