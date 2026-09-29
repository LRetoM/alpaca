"""Kontoweites Risiko-Dach - die Grenze, die keine Strategie kennt.

Jede Regel hier ist eine Antwort auf die Frage "Was, wenn die Strategie
NICHT funktioniert?" - nicht auf "wie optimiere ich sie?". Deshalb steht
dieses Modul UEBER der Engine und nicht in ihr: Eine Engine, die ihre
eigenen Notbremsen zieht, hat keine. (Entwurf: docs/mehrbot-plan.md §5.)

Drei Regeln, bewusst wenige und rund:

  * **Drawdown-Sperre.** Faellt das Konto um mehr als `max_drawdown_pct`
    unter seinen Hoechststand, werden keine neuen Kaeufe mehr gesendet -
    Verkaeufe bleiben immer erlaubt. Die Sperre ist PERSISTENT und wird nur
    von Hand geloest. Eine Sperre, die sich nach einer Stunde selbst
    aufhebt, kauft genau in den Crash zurueck, wegen dem sie ausgeloest hat.
  * **Tagesverlust-Bremse.** Verlust seit Tagesbeginn ueber
    `tagesverlust_pct`: keine neuen Kaeufe mehr HEUTE. Loest sich am
    naechsten Handelstag von selbst.
  * **Equity-Verlauf.** Jeder Zyklus schreibt Kontowert, Cash und
    Positionszahl fort. Ohne diese Kurve laesst sich im Nachhinein nicht
    sehen, wann ein Drawdown begann - und der Hoechststand muss
    einzahlungsbereinigt sein, sonst hebt jede Einzahlung die Marke.

Einzahlungen: `kapital_verlauf` fuehrt `hoechststand` als Hoechststand des
Kontowerts MINUS der seit Beginn gemeldeten Nettoeinzahlungen
(`einzahlung_melden`). Wer einzahlt und es nicht meldet, verschiebt die
Drawdown-Marke nach oben - das ist ungefaehrlich (Sperre kommt frueher),
das Gegenteil (Auszahlung nicht melden) verzoegert sie. Deshalb werden
Auszahlungen ebenfalls gemeldet.
"""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

from .config import DATA_DIR

RISIKO_DB = DATA_DIR / "state.sqlite"

SCHEMA = """
CREATE TABLE IF NOT EXISTS risiko_sperre (
    id           INTEGER PRIMARY KEY CHECK (id = 1),
    aktiv        INTEGER NOT NULL DEFAULT 0,
    grund        TEXT,
    kennzahlen   TEXT,
    gesetzt_am   TEXT,
    geloest_am   TEXT,
    geloest_von  TEXT
);
CREATE TABLE IF NOT EXISTS kapital_verlauf (
    ts           TEXT PRIMARY KEY,
    tag          TEXT NOT NULL,
    equity       REAL NOT NULL,
    cash         REAL,
    n_positionen INTEGER,
    netto_einzahlungen REAL NOT NULL,
    hoechststand REAL NOT NULL,
    drawdown_pct REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS kapitalfluesse (
    id          TEXT PRIMARY KEY,
    ts          TEXT NOT NULL,
    betrag      REAL NOT NULL,
    notiz       TEXT
);
CREATE INDEX IF NOT EXISTS idx_kapital_tag ON kapital_verlauf(tag);
"""

BESTAETIGUNG = "ich habe die ursache verstanden"


@dataclass(frozen=True)
class Risikogrenzen:
    max_drawdown_pct: float = 0.20
    tagesverlust_pct: float = 0.05
    max_brutto_exposure: float = 1.00
    min_cash_reserve_pct: float = 0.05
    verified: str = "2026-09-29"


@dataclass
class Freigabe:
    ok: bool
    """Duerfen NEUE Kaeufe gesendet werden? Verkaeufe sind immer erlaubt."""
    gruende: list[str] = field(default_factory=list)
    drawdown_pct: float = 0.0
    tagesverlust_pct: float = 0.0
    hoechststand: float = 0.0
    sperre_aktiv: bool = False

    def __str__(self) -> str:
        zustand = "FREI" if self.ok else "GESPERRT (nur Verkaeufe)"
        L = [f"Risiko-Dach: {zustand}  Drawdown {self.drawdown_pct:.1%}  "
             f"heute {self.tagesverlust_pct:+.1%}  Hoechststand {self.hoechststand:,.0f}"]
        L += [f"  - {g}" for g in self.gruende]
        return "\n".join(L)


class RisikoDach:
    def __init__(self, path: Path = RISIKO_DB, grenzen: Risikogrenzen | None = None):
        self.path = path
        self.grenzen = grenzen or Risikogrenzen()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.executescript(SCHEMA)

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        con = sqlite3.connect(self.path, timeout=30)
        con.row_factory = sqlite3.Row
        try:
            yield con
            con.commit()
        finally:
            con.close()

    # --- Kapitalfluesse -----------------------------------------------------
    def einzahlung_melden(self, betrag: float, notiz: str = "", *, id: str | None = None) -> None:
        """Positiv = Einzahlung, negativ = Auszahlung. `id` verhindert Doppelbuchung."""
        with self._conn() as c:
            c.execute(
                "INSERT OR IGNORE INTO kapitalfluesse (id, ts, betrag, notiz) VALUES (?,?,?,?)",
                (id or dt.datetime.now(dt.UTC).isoformat(), dt.datetime.now(dt.UTC).isoformat(),
                 float(betrag), notiz),
            )

    def netto_einzahlungen(self) -> float:
        with self._conn() as c:
            r = c.execute("SELECT COALESCE(SUM(betrag), 0) AS s FROM kapitalfluesse").fetchone()
        return float(r["s"] or 0.0)

    # --- Verlauf --------------------------------------------------------------
    def verlauf_schreiben(self, equity: float, cash: float | None = None,
                          n_positionen: int | None = None, *, ts: dt.datetime | None = None) -> dict:
        ts = ts or dt.datetime.now(dt.UTC)
        netto = self.netto_einzahlungen()
        bereinigt = float(equity) - netto
        with self._conn() as c:
            r = c.execute("SELECT MAX(hoechststand) AS h FROM kapital_verlauf").fetchone()
            hoechst = max(float(r["h"] or 0.0), bereinigt)
            dd = bereinigt / hoechst - 1 if hoechst > 0 else 0.0
            c.execute(
                "INSERT OR REPLACE INTO kapital_verlauf (ts, tag, equity, cash, n_positionen,"
                " netto_einzahlungen, hoechststand, drawdown_pct) VALUES (?,?,?,?,?,?,?,?)",
                (ts.isoformat(), ts.date().isoformat(), float(equity),
                 None if cash is None else float(cash), n_positionen, netto, hoechst, dd),
            )
        return {"hoechststand": hoechst, "drawdown_pct": dd, "bereinigt": bereinigt}

    def tagesstart_equity(self, tag: dt.date) -> float | None:
        with self._conn() as c:
            r = c.execute(
                "SELECT equity FROM kapital_verlauf WHERE tag = ? ORDER BY ts ASC LIMIT 1",
                (tag.isoformat(),),
            ).fetchone()
        return float(r["equity"]) if r else None

    # --- Sperre -----------------------------------------------------------------
    def sperre(self) -> dict | None:
        with self._conn() as c:
            r = c.execute("SELECT * FROM risiko_sperre WHERE id = 1").fetchone()
        return dict(r) if r and r["aktiv"] else None

    def sperre_setzen(self, grund: str, kennzahlen: dict) -> None:
        with self._conn() as c:
            c.execute(
                "INSERT INTO risiko_sperre (id, aktiv, grund, kennzahlen, gesetzt_am)"
                " VALUES (1, 1, ?, ?, ?)"
                " ON CONFLICT(id) DO UPDATE SET aktiv=1, grund=excluded.grund,"
                " kennzahlen=excluded.kennzahlen, gesetzt_am=excluded.gesetzt_am,"
                " geloest_am=NULL, geloest_von=NULL",
                (grund, json.dumps(kennzahlen, default=str), dt.datetime.now(dt.UTC).isoformat()),
            )

    def sperre_loesen(self, bestaetigung: str, von: str = "hand") -> str:
        """Nur von Hand. `bestaetigung` muss woertlich lauten:
        'ich habe die ursache verstanden' - eine Reibung, die verhindert,
        dass man im Schock einfach weiterlaufen laesst. Der Hoechststand
        wird auf den aktuellen Kontowert gesetzt, sonst loest die Sperre
        beim naechsten Zyklus sofort wieder aus."""
        if bestaetigung.strip().lower() != BESTAETIGUNG:
            return f"Nicht geloest. Bestaetigung muss lauten: '{BESTAETIGUNG}'"
        with self._conn() as c:
            c.execute(
                "UPDATE risiko_sperre SET aktiv=0, geloest_am=?, geloest_von=? WHERE id=1",
                (dt.datetime.now(dt.UTC).isoformat(), von),
            )
            r = c.execute("SELECT equity, netto_einzahlungen FROM kapital_verlauf"
                          " ORDER BY ts DESC LIMIT 1").fetchone()
            if r:
                # Neuer Bezugspunkt: alle alten Hoechststaende auf den aktuellen Wert kappen
                c.execute("UPDATE kapital_verlauf SET hoechststand = MIN(hoechststand, ?)",
                          (float(r["equity"]) - float(r["netto_einzahlungen"]),))
        return "Sperre geloest. Hoechststand auf aktuellen Kontowert gesetzt."

    # --- Pruefung -----------------------------------------------------------------
    def pruefe_konto(self, equity: float, cash: float | None = None,
                     n_positionen: int | None = None, *, ts: dt.datetime | None = None) -> Freigabe:
        """Einmal je Zyklus, VOR dem Entscheiden. Schreibt den Verlauf fort und
        entscheidet, ob neue Kaeufe erlaubt sind."""
        ts = ts or dt.datetime.now(dt.UTC)
        start = self.tagesstart_equity(ts.date())
        v = self.verlauf_schreiben(equity, cash, n_positionen, ts=ts)
        tagesverlust = (equity / start - 1) if start else 0.0
        gruende: list[str] = []
        aktiv = self.sperre()
        if aktiv:
            gruende.append(f"Vollsperre seit {str(aktiv['gesetzt_am'])[:16]}: {aktiv['grund']} - "
                           f"loesen mit risiko.sperre_loesen('{BESTAETIGUNG}')")
        elif v["drawdown_pct"] <= -self.grenzen.max_drawdown_pct:
            grund = (f"Drawdown {v['drawdown_pct']:.1%} unter Hoechststand "
                     f"{v['hoechststand']:,.0f} (Grenze {self.grenzen.max_drawdown_pct:.0%})")
            self.sperre_setzen(grund, {"equity": equity, **v})
            gruende.append("VOLLSPERRE gesetzt: " + grund)
        if tagesverlust <= -self.grenzen.tagesverlust_pct:
            gruende.append(f"Tagesverlust {tagesverlust:.1%} (Grenze {self.grenzen.tagesverlust_pct:.0%}) - "
                           "heute keine neuen Kaeufe")
        return Freigabe(ok=not gruende, gruende=gruende, drawdown_pct=v["drawdown_pct"],
                        tagesverlust_pct=tagesverlust, hoechststand=v["hoechststand"],
                        sperre_aktiv=bool(self.sperre()))


def selftest(pfad: Path | None = None) -> int:
    import tempfile

    fehler = 0
    with tempfile.TemporaryDirectory() as tmp:
        d = RisikoDach(Path(tmp) / "state.sqlite")
        t0 = dt.datetime(2026, 10, 1, 15, 0, tzinfo=dt.UTC)
        f = d.pruefe_konto(100_000, ts=t0)
        ok = f.ok and f.drawdown_pct == 0
        print(f"  [{'ok' if ok else 'FEHLER'}] Start: frei, Drawdown 0"); fehler += not ok
        f = d.pruefe_konto(94_000, ts=t0 + dt.timedelta(hours=1))
        ok = not f.ok and any("Tagesverlust" in g for g in f.gruende) and not f.sperre_aktiv
        print(f"  [{'ok' if ok else 'FEHLER'}] -6 % am Tag: Tagesbremse, keine Vollsperre"); fehler += not ok
        f = d.pruefe_konto(94_000, ts=t0 + dt.timedelta(days=1))
        ok = f.ok
        print(f"  [{'ok' if ok else 'FEHLER'}] Naechster Tag: Bremse geloest"); fehler += not ok
        f = d.pruefe_konto(79_000, ts=t0 + dt.timedelta(days=2))
        ok = not f.ok and f.sperre_aktiv
        print(f"  [{'ok' if ok else 'FEHLER'}] -21 % vom Hoechststand: Vollsperre"); fehler += not ok
        f = d.pruefe_konto(95_000, ts=t0 + dt.timedelta(days=3))
        ok = not f.ok and f.sperre_aktiv
        print(f"  [{'ok' if ok else 'FEHLER'}] Erholung loest die Sperre NICHT von selbst"); fehler += not ok
        msg = d.sperre_loesen("falsch")
        ok = d.sperre_aktiv if False else d.sperre() is not None
        print(f"  [{'ok' if ok else 'FEHLER'}] Falsche Bestaetigung loest nicht: {msg[:40]}"); fehler += not ok
        d.sperre_loesen(BESTAETIGUNG)
        f = d.pruefe_konto(95_500, ts=t0 + dt.timedelta(days=4))
        ok = f.ok and abs(f.drawdown_pct) < 0.02
        print(f"  [{'ok' if ok else 'FEHLER'}] Nach dem Loesen: frei, Hoechststand neu gesetzt ({f.drawdown_pct:+.1%})"); fehler += not ok
        d.einzahlung_melden(20_000, "Test", id="e1")
        f = d.pruefe_konto(115_500, ts=t0 + dt.timedelta(days=5))
        ok = f.ok and f.hoechststand < 100_000
        print(f"  [{'ok' if ok else 'FEHLER'}] Einzahlung hebt den Hoechststand nicht ({f.hoechststand:,.0f})"); fehler += not ok
    print(f"\n  risiko-Selbsttest: {'bestanden' if fehler == 0 else f'{fehler} Fehler'}")
    return 1 if fehler else 0
