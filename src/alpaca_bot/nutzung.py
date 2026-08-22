"""Nutzungsnachweis: laeuft wirklich alles, was wir gebaut haben?

**Der Anlass ist eine Fehlerserie, kein Verdacht.** Dreimal innerhalb
weniger Tage stellte sich heraus, dass ein fertig gebauter Baustein
niemals lief - und niemand konnte es merken, weil nichts abstuerzte:

    21.08.  Der Bar-Cache traf nie. `use_cache=True` rief niemand auf,
            das Verzeichnis war leer. (§G11 Fund 4)
    22.08.  Der Musterspeicher lief nie. Tabelle `muster`: null Zeilen.
            Der Daemon kannte den Schritt gar nicht. (§G14)
    22.08.  Der Auswertungskontext hing nur an `buy`. `topup` - die
            Mehrheit der Kapitalzuteilung - bekam nichts. (§G13 Fund 3)

Dazu die aeltere Chronik: `bars_held` immer 0, `after_10d` nie gefuellt,
`code_version` zwei Monate 'unbekannt', 98,4 % Simulationszeilen im
Live-Journal.

**Das Muster ist immer dasselbe.** Ein Baustein ist gebaut, sieht im Code
richtig aus, und tut nichts. Kein Fehler, keine Meldung. Gefunden wurde
jeder Fall nur, weil zufaellig jemand gezielt nachsah - im Schnitt Wochen
zu spaet. Dieses Modul macht daraus eine Routine.

## Die vier Arten des stillen Ausfalls

Jede hat einen eigenen Test, weil keine die andere findet:

    NIE GELAUFEN      Der Baustein wird nirgends aufgerufen.
                      (Musterspeicher, Bar-Cache)
    IMMER LEER        Er laeuft, liefert aber nie ein Ergebnis.
                      (Cache traf nie, 0 Muster angelegt)
    IMMER GLEICH      Er laeuft und liefert immer dasselbe - also
                      keine neue Information. (19.788 Verifizierungen
                      je Stunde, Runde um Runde identisch)
    ZU SELTEN         Er laeuft, aber seltener als geplant.
                      (ein Schritt, der stumm scheitert)

## Was dieses Modul ausdruecklich NICHT tut

Es prueft **Nutzung**, nicht Richtigkeit. Ein Baustein kann taeglich
laufen, wechselnde Ergebnisse liefern und trotzdem falsch rechnen -
dagegen helfen `tests/`, `data_integrity.py` und der Mutationstest.
Hier geht es um die davorliegende, banalere Frage: Passiert ueberhaupt
etwas?
"""

from __future__ import annotations

import datetime as dt
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from .config import DATA_DIR

NUTZUNG_DB = DATA_DIR / "nutzung.sqlite"

SCHEMA = """
CREATE TABLE IF NOT EXISTS laeufe (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    baustein     TEXT NOT NULL,
    ts           TEXT NOT NULL,
    ergebnis     INTEGER,          -- Zahl der erzeugten/verarbeiteten Einheiten
    signatur     TEXT,             -- kennzeichnet, WAS herauskam
    dauer_s      REAL,
    hinweis      TEXT
);
CREATE INDEX IF NOT EXISTS idx_laeufe_baustein ON laeufe (baustein, ts);
"""


@dataclass(frozen=True)
class Erwartung:
    """Was ein Baustein leisten muss, damit er als genutzt gilt.

    Die Erwartung steht bewusst NEBEN dem Code des Bausteins, nicht in
    ihm: Ein Baustein, der gar nicht erst aufgerufen wird, kann seine
    eigene Erwartung nicht anmelden - und genau das war der haeufigste
    Fall.
    """

    baustein: str
    zweck: str
    """Wofuer er da ist - erscheint im Befund, damit der Ausfall
    einordbar ist, ohne den Code zu lesen."""
    hoechstens_stunden: float
    """Laeuft er seltener, gilt er als ausgefallen."""
    darf_leer_sein: bool = False
    """True fuer Bausteine, die legitim oft nichts zu tun haben
    (z. B. der Lernschritt ohne neuen Handelstag)."""
    darf_gleich_bleiben: bool = False
    """True, wenn wiederholt gleiche Ergebnisse normal sind."""
    seit_tagen: int = 3
    """Fenster, ueber das geurteilt wird."""


ERWARTUNGEN: tuple[Erwartung, ...] = (
    Erwartung("schatten.einbuchen", "Vorhersagen bekommen ihren Einstiegskurs",
              hoechstens_stunden=26, darf_leer_sein=True),
    Erwartung("schatten.verifizieren", "Ergebnisse gegen den echten Kursverlauf",
              hoechstens_stunden=26, darf_leer_sein=True),
    Erwartung("schatten.entscheiden", "die zehn Bots treffen ihre Entscheidungen",
              hoechstens_stunden=26, darf_leer_sein=True),
    Erwartung("schatten.lernen", "Musterspeicher pruefen und Kandidaten suchen",
              hoechstens_stunden=26, darf_leer_sein=True),
    Erwartung("lernkern.trainieren", "Modell gegen Score auf der Historie",
              hoechstens_stunden=24 * 8, darf_leer_sein=True, seit_tagen=10),
    Erwartung("live.zyklus", "der Handelsbot entscheidet",
              hoechstens_stunden=26, darf_leer_sein=True, darf_gleich_bleiben=True),
)
"""Die ueberwachten Bausteine.

Bewusst kurz. Jeder Eintrag ist ein Baustein, dessen stiller Ausfall
schon einmal Wochen gekostet hat oder kosten wuerde. Eine Liste, die
jeden Aufruf im Projekt ueberwacht, wuerde so viele Zeilen erzeugen,
dass niemand mehr hinsieht - und dann faellt auch der echte Ausfall
nicht mehr auf. Dieselbe Lehre wie beim Feld-Waechter (§G13).

`lernkern.trainieren` hat ein weites Fenster (8 Tage): Ein Panel-Lauf
ueber 1.200 Symbole und 7 Jahre dauert Minuten und gehoert nicht in
jeden Zyklus. Er darf aber nicht monatelang ausbleiben, ohne dass es
auffaellt - genau das war der Zustand des Musterspeichers.
"""


def _conn(db: Path | None = None) -> sqlite3.Connection:
    pfad = Path(db or NUTZUNG_DB)
    pfad.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(pfad)
    c.row_factory = sqlite3.Row
    c.executescript(SCHEMA)
    return c


def melden(baustein: str, ergebnis: int = 0, *, signatur: str = "",
           dauer_s: float | None = None, hinweis: str = "",
           db: Path | None = None) -> None:
    """Ein Baustein meldet, dass er gelaufen ist - und was herauskam.

    `signatur` ist der Schluessel zur Erkennung von "immer gleich": Sie
    kennzeichnet das ERGEBNIS, nicht den Lauf. Bleibt sie ueber viele
    Laeufe konstant, wurde zwar gerechnet, aber nichts Neues gefunden.
    Genau so lief der Schattenbot rund um die Uhr: 19.788 verifizierte
    Vorhersagen, Runde um Runde dieselben.

    Die Meldung darf NIE den Aufrufer stoppen. Ein Nutzungsprotokoll,
    das den Betrieb gefaehrdet, waere schlimmer als keins.
    """
    try:
        with _conn(db) as c:
            c.execute(
                "INSERT INTO laeufe (baustein, ts, ergebnis, signatur, dauer_s,"
                " hinweis) VALUES (?,?,?,?,?,?)",
                (baustein, dt.datetime.now(dt.UTC).isoformat(), int(ergebnis),
                 str(signatur), dauer_s, hinweis),
            )
    except Exception:  # noqa: BLE001 - Protokoll darf den Betrieb nie stoppen
        pass


@dataclass
class Befund:
    baustein: str
    art: str
    """'nie_gelaufen' | 'zu_selten' | 'immer_leer' | 'immer_gleich' | 'ok'"""
    detail: str
    zweck: str = ""

    @property
    def ok(self) -> bool:
        return self.art == "ok"

    def __str__(self) -> str:
        if self.ok:
            return f"  [OK]      {self.baustein:<26} {self.detail}"
        marke = {"nie_gelaufen": "NIE", "zu_selten": "SELTEN",
                 "immer_leer": "LEER", "immer_gleich": "GLEICH"}[self.art]
        return (f"  [{marke:<7}] {self.baustein:<26} {self.detail}\n"
                f"              Zweck: {self.zweck}")


def pruefen(erwartungen=ERWARTUNGEN, *, db: Path | None = None,
            jetzt: dt.datetime | None = None) -> list[Befund]:
    """Vergleicht jede Erwartung mit dem, was tatsaechlich passiert ist."""
    jetzt = jetzt or dt.datetime.now(dt.UTC)
    befunde: list[Befund] = []

    with _conn(db) as c:
        for e in erwartungen:
            grenze = (jetzt - dt.timedelta(days=e.seit_tagen)).isoformat()
            zeilen = c.execute(
                "SELECT ts, ergebnis, signatur FROM laeufe"
                " WHERE baustein=? AND ts>=? ORDER BY ts DESC",
                (e.baustein, grenze),
            ).fetchall()

            if not zeilen:
                # Unterscheidung, die zaehlt: nie gelaufen ODER laenger
                # her als das Fenster. Beides ist ein Ausfall, aber der
                # erste Fall heisst "nirgends verdrahtet".
                jemals = c.execute(
                    "SELECT COUNT(*) n, MAX(ts) letzte FROM laeufe WHERE baustein=?",
                    (e.baustein,)).fetchone()
                if not jemals["n"]:
                    befunde.append(Befund(
                        e.baustein, "nie_gelaufen",
                        "hat sich noch nie gemeldet - vermutlich nirgends "
                        "aufgerufen", e.zweck))
                else:
                    befunde.append(Befund(
                        e.baustein, "zu_selten",
                        f"zuletzt {jemals['letzte'][:16]}, aelter als das "
                        f"{e.seit_tagen}-Tage-Fenster", e.zweck))
                continue

            letzte = dt.datetime.fromisoformat(zeilen[0]["ts"])
            stunden = (jetzt - letzte).total_seconds() / 3600
            if stunden > e.hoechstens_stunden:
                befunde.append(Befund(
                    e.baustein, "zu_selten",
                    f"zuletzt vor {stunden:.1f} h, erlaubt sind "
                    f"{e.hoechstens_stunden:.0f} h", e.zweck))
                continue

            ergebnisse = [z["ergebnis"] or 0 for z in zeilen]
            if not e.darf_leer_sein and max(ergebnisse) == 0:
                befunde.append(Befund(
                    e.baustein, "immer_leer",
                    f"{len(zeilen)} Laeufe, jedes Mal 0 Ergebnisse", e.zweck))
                continue

            signaturen = {z["signatur"] for z in zeilen if z["signatur"]}
            if (not e.darf_gleich_bleiben and len(zeilen) >= 5
                    and len(signaturen) == 1):
                befunde.append(Befund(
                    e.baustein, "immer_gleich",
                    f"{len(zeilen)} Laeufe, aber immer dasselbe Ergebnis "
                    f"({next(iter(signaturen))[:40]}) - es entsteht keine "
                    f"neue Information", e.zweck))
                continue

            befunde.append(Befund(
                e.baustein, "ok",
                f"{len(zeilen)} Laeufe in {e.seit_tagen} T, zuletzt vor "
                f"{stunden:.1f} h, {len(signaturen)} verschiedene Ergebnisse"))
    return befunde


def bericht(*, db: Path | None = None, jetzt: dt.datetime | None = None) -> str:
    """Ein Blick: laeuft alles, was laufen soll?"""
    befunde = pruefen(db=db, jetzt=jetzt)
    schlecht = [b for b in befunde if not b.ok]
    L = ["=" * 74, "  NUTZUNGSNACHWEIS - laeuft, was wir gebaut haben?", "=" * 74, ""]
    for b in befunde:
        L.append(str(b))
    L.append("")
    if schlecht:
        L.append(f"  {len(schlecht)} von {len(befunde)} Bausteinen arbeiten nicht "
                 f"wie geplant.")
        L.append("  Ein Baustein, der nicht laeuft, kostet keine Fehlermeldung -")
        L.append("  nur Wochen, in denen wir nichts daraus lernen.")
    else:
        L.append(f"  Alle {len(befunde)} Bausteine arbeiten wie geplant.")
    return "\n".join(L)


def verlauf(baustein: str, *, tage: int = 7, db: Path | None = None) -> pd.DataFrame:
    """Was hat ein Baustein zuletzt geliefert? Fuer die Ursachensuche."""
    grenze = (dt.datetime.now(dt.UTC) - dt.timedelta(days=tage)).isoformat()
    with _conn(db) as c:
        return pd.read_sql_query(
            "SELECT ts, ergebnis, signatur, dauer_s, hinweis FROM laeufe"
            " WHERE baustein=? AND ts>=? ORDER BY ts DESC",
            c, params=(baustein, grenze))
