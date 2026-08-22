"""Lernkern: Modellversionen, ihre Bewertung und die Abnahme.

**Die eine Frage:** Sortiert ein gelerntes Modell die Kandidaten besser
als der handgebaute Score - gemessen ueber Handelstage, nach Korrektur
der Ueberlappung (§G12), gegen die Zufallsschwelle der Flotte?

## Warum die Historie und nicht der Schatten

Gemessen am 22.08.2026: Der Schatten hat 20.690 Vorhersagen, aber **19**
unabhaengige Handelstage. Die Historie hat rund 969. Ein Effekt der
Groesse, die dieses Projekt real misst (IC ~0,02), braucht ueber 900
Handelstage bis zur Schwelle. Der Schatten kann diese Frage heute nicht
tragen, egal wie oft man rechnet (§G14, `docs/LERNTEMPO.md` §5a).

Das ist zugleich die Antwort auf "der Bot soll rund um die Uhr lernen":
Er kann es - aber auf der **Historie**, nicht auf neuen Handelstagen.

## Was ein Lauf hier NICHT darf

Er nimmt nichts ab. Survivorship allein schenkt 2-4 Prozentpunkte im
Jahr - mehr, als die Strategie je verdienen wird (§G11). Jedes Ergebnis
ist eine **Obergrenze** und ein **Filter**: Was hier durchfaellt, braucht
keinen Flottenplatz. Was besteht, ist eine Hypothese fuer den Schatten,
kein Signal.

## Die Registry

Jede trainierte Version bekommt eine `model_version` und einen Eintrag
mit Codestand, Datenquelle, Zahl der bewerteten Handelstage, IC, t-Wert
und der zum Messzeitpunkt geltenden Schwelle. Ohne diese Zeile liesse
sich spaeter nicht sagen, ob eine neue Version wirklich besser ist oder
nur auf einen anderen Zeitraum passt - derselbe Gedanke wie `lauf.json`
neben jeder `trades.csv` (§G11).
"""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from .config import DATA_DIR, code_version

DB_PFAD = DATA_DIR / "lernkern.sqlite"
MODELL_DIR = DATA_DIR / "modelle"
"""Wohin die trainierten Modelle als joblib gelegt werden.

Neben der Registry-Zeile, nicht statt ihr: Die Datei allein sagt
nicht, woran das Modell gemessen wurde - genau der Fehler, an dem
eine `trades.csv` ohne `lauf.json` gescheitert ist (§G11)."""

MIN_TAGE_BEWERTUNG = 250
"""Unter so vielen out-of-sample bewerteten Handelstagen wird nichts
abgenommen - egal wie gut der t-Wert aussieht.

250 Handelstage sind rund ein Jahr. Die Zahl ist keine Konvention,
sondern folgt aus §A: Bei einem IC um 0,02 und der beobachteten Streuung
liegt die noetige Zahl in dieser Groessenordnung. Ein t-Wert aus 19 Tagen
(dem heutigen Schattenstand) traegt sie nicht - deshalb lehnt `abnehmen`
solche Versionen ab, auch bei t = 9,9."""

MIN_VERBESSERUNG_IC = 0.002
"""Um wie viel IC eine neue Version die alte schlagen muss.

Ohne Mindestabstand wuerde jede Version, die zufaellig 0,0001 besser
liegt, als Fortschritt gelten - und die Registry fuellte sich mit
Scheinverbesserungen."""

SCHEMA = """
CREATE TABLE IF NOT EXISTS modelle (
    model_version   TEXT PRIMARY KEY,
    erstellt_at     TEXT NOT NULL,
    code_version    TEXT,
    status          TEXT NOT NULL DEFAULT 'kandidat',
    quelle          TEXT,            -- 'historie' | 'schatten'
    panel_von       TEXT,
    panel_bis       TEXT,
    n_tage          INTEGER,         -- Handelstage im Panel
    n_zeilen        INTEGER,
    n_symbole       INTEGER,
    horizont        INTEGER,
    label_art       TEXT,
    model_kind      TEXT,
    merkmale        TEXT,            -- JSON-Liste
    ic              REAL,
    t               REAL,            -- korrigiert (§G12)
    t_roh           REAL,            -- unkorrigiert, nur zum Vergleich
    aufblaehung     REAL,
    spreizung       REAL,
    spreizung_t     REAL,
    n_tage_bewertet INTEGER,         -- out-of-sample, NICHT n_tage
    schwelle        REAL,
    befund          INTEGER,
    urteil          TEXT,
    pfad            TEXT             -- joblib-Datei des Modells
);
CREATE INDEX IF NOT EXISTS idx_modelle_status ON modelle (status, erstellt_at);
"""


def _conn(pfad: Path | None = None) -> sqlite3.Connection:
    """Verbindung zur Registry. `DB_PFAD` ist bewusst modulweit, damit
    Tests ihn ersetzen koennen, ohne jede Funktion durchzureichen."""
    p = Path(pfad or DB_PFAD)
    p.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(p)
    c.row_factory = sqlite3.Row
    c.executescript(SCHEMA)
    return c


@dataclass
class Version:
    """Eine trainierte Modellversion samt ihrer Herkunft."""

    model_version: str
    quelle: str
    horizont: int
    model_kind: str
    n_tage_bewertet: int
    schwelle: float
    merkmale: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        return (f"{self.model_version} ({self.quelle}, {self.model_kind}, "
                f"Horizont {self.horizont}, {self.n_tage_bewertet} Tage)")




def trainieren(bars: pd.DataFrame, *, quelle: str = "historie",
               horizont: int = 5, market: pd.Series | None = None,
               model_kind: str = "gbm", n_falten: int = 5,
               verbose: bool = True, pfad: Path | None = None):
    """Baut das Panel, faehrt den Walk-Forward und traegt die Version ein.

    Gibt `(Version, Guete)` zurueck. Die Guete stammt aus
    `dataset.guete` - **derselben** Funktion, durch die auch der
    bestehende Score laeuft. Ein Vergleich, bei dem die neue Methode
    anders gemessen wird als die alte, ist kein Vergleich (§G11 Fund 6).

    Der Walk-Forward ist nicht verhandelbar: Eine zufaellige Aufteilung
    in Trainings- und Testdaten liesse Information aus der Zukunft ins
    Training - das Modell saehe grossartig aus und waere wertlos.
    """
    from . import dataset, fleet

    panel = dataset.baue_panel(bars, horizont=horizont, market=market,
                               verbose=verbose)
    if verbose:
        print(panel.bericht())

    erg = dataset.walk_forward_panel(panel, model_kind=model_kind,
                                     n_falten=n_falten, verbose=verbose)
    schwelle = fleet.schwelle_sigma()
    g = dataset.guete(erg.vorhersagen, erg.tatsaechlich, erg.tage,
                      name=f"Modell ({model_kind})", horizont=horizont,
                      schwelle=schwelle)

    # UUID statt sprechender Kennung: Der Name darf keine Eigenschaft des
    # Laufs behaupten, die sich spaeter aendert. Alles Beschreibende steht
    # in den Spalten daneben - dort ist es abfragbar und kann nicht mit
    # dem Dateinamen auseinanderlaufen.
    mv = str(uuid.uuid4())
    modell_pfad = MODELL_DIR / f"{mv}.joblib"
    try:
        MODELL_DIR.mkdir(parents=True, exist_ok=True)
        import joblib

        joblib.dump({"modell": erg.modell, "merkmale": list(erg.merkmale),
                     "horizont": horizont, "model_kind": model_kind}, modell_pfad)
    except Exception as e:  # noqa: BLE001 - ohne Datei bleibt der Eintrag gueltig
        if verbose:
            print(f"      Modell nicht gespeichert ({type(e).__name__}: {e})")
        modell_pfad = None

    v = Version(
        model_version=mv, quelle=quelle, horizont=horizont,
        model_kind=model_kind, n_tage_bewertet=g.n_tage, schwelle=schwelle,
        merkmale=list(erg.merkmale),
    )

    with _conn(pfad) as c:
        c.execute(
            "INSERT OR REPLACE INTO modelle (model_version, erstellt_at,"
            " code_version, status, quelle, panel_von, panel_bis, n_tage,"
            " n_zeilen, n_symbole, horizont, label_art, model_kind, merkmale,"
            " ic, t, t_roh, aufblaehung, spreizung, spreizung_t,"
            " n_tage_bewertet, schwelle, befund, pfad)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (mv, dt.datetime.now(dt.UTC).isoformat(), code_version(),
             "kandidat", quelle, str(panel.tage.min())[:10],
             str(panel.tage.max())[:10], panel.n_tage, len(panel.X),
             panel.n_symbole, horizont, panel.label_art, model_kind,
             json.dumps(list(erg.merkmale), ensure_ascii=False),
             _zahl(g.ic), _zahl(g.t), _zahl(g.t_roh), _zahl(g.aufblaehung),
             _zahl(g.spreizung), _zahl(g.spreizung_t), g.n_tage, schwelle,
             int(g.befund), str(modell_pfad) if modell_pfad else None),
        )
    return v, g


def _zahl(x) -> float | None:
    """NaN gehoert als NULL in die Datenbank, nicht als Zahl.

    Ein gespeichertes NaN liest sich spaeter je nach Werkzeug als 0,0 -
    und aus "nicht messbar" wuerde stillschweigend "kein Effekt"."""
    try:
        f = float(x)
    except (TypeError, ValueError):
        return None
    return f if np.isfinite(f) else None


def abnehmen(model_version: str, *, verbose: bool = True,
             pfad: Path | None = None) -> str:
    """Darf diese Version in die naechste Stufe? Gibt den Grund zurueck.

    **Drei Huerden, alle vorab festgelegt** (die Konstanten oben stehen
    modulweit, nicht je Aufruf - sonst waere jede Version an einer
    anderen Huerde gemessen worden):

        1. genug bewertete Handelstage  (`MIN_TAGE_BEWERTUNG`)
        2. t ueber der Zufallsschwelle des Messzeitpunkts
        3. IC besser als die beste bisher abgenommene Version
           (`MIN_VERBESSERUNG_IC`)

    Die Reihenfolge ist Absicht: Zuerst die Datenbasis, dann die
    Signifikanz, dann der Fortschritt. Ein grossartiger t-Wert aus 19
    Tagen faellt an Huerde 1 - und muss dort fallen, sonst wandert eine
    Momentaufnahme weiter (§G14).

    Die Funktion nimmt NICHTS live. `status='abgenommen'` heisst: darf
    als Hypothese in den Schatten. Der Weg in die Handelslogik fuehrt
    weiter ueber eine Voranmeldung in der Flotte (CLAUDE.md).
    """
    with _conn(pfad) as c:
        m = c.execute("SELECT * FROM modelle WHERE model_version=?",
                      (model_version,)).fetchone()
        if m is None:
            return f"  {model_version}: nicht in der Registry."

        n_tage = int(m["n_tage_bewertet"] or 0)
        t = m["t"]
        ic = m["ic"]

        if n_tage < MIN_TAGE_BEWERTUNG:
            urteil = (f"abgelehnt: nur {n_tage} bewertete Handelstage, "
                      f"noetig {MIN_TAGE_BEWERTUNG}")
            lang = ("  Auch ein hoher t-Wert traegt das nicht - die Datenbasis "
                    "ist zu klein.")
        elif t is None or not np.isfinite(float(t)):
            urteil = "abgelehnt: kein gueltiger t-Wert"
            lang = ("  Bei diesem Horizont laesst sich die Ueberlappung nicht "
                    "schaetzen (§G12).")
        elif abs(float(t)) <= float(m["schwelle"] or 0):
            urteil = (f"abgelehnt: t = {float(t):.2f} unter Schwelle "
                      f"{float(m['schwelle']):.2f}")
            lang = ("  Das ist bei dieser Zahl von Versuchen der Normalfall, "
                    "kein Befund.")
        else:
            best = c.execute(
                "SELECT model_version, ic FROM modelle WHERE status='abgenommen'"
                " AND ic IS NOT NULL ORDER BY ic DESC LIMIT 1").fetchone()
            if best and float(ic or 0) < float(best["ic"]) + MIN_VERBESSERUNG_IC:
                urteil = (f"abgelehnt: IC {float(ic or 0):.4f} verbessert "
                          f"{str(best['model_version'])[:8]} "
                          f"({float(best['ic']):.4f}) nicht um "
                          f"{MIN_VERBESSERUNG_IC}")
                lang = "  Ohne Mindestabstand waere jede Zufallsschwankung ein Fortschritt."
            else:
                urteil = (f"abgenommen: IC {float(ic or 0):.4f}, t = {float(t):.2f} "
                          f"ueber {n_tage} Handelstagen")
                lang = ("  Das heisst: darf als Hypothese in den Schatten. "
                        "NICHT live (CLAUDE.md).")

        # `verworfen` und nicht `kandidat`: Eine abgelehnte Version bleibt
        # in der Registry stehen - sie zaehlt im Versuchszaehler mit und
        # ist Teil der Historie. Sie darf nur nie wieder als Kandidat
        # auftauchen und dadurch ein zweites Mal geprueft werden.
        neuer_status = "abgenommen" if urteil.startswith("abgenommen") else "verworfen"
        c.execute("UPDATE modelle SET status=?, urteil=? WHERE model_version=?",
                  (neuer_status, urteil, model_version))
        grund = f"  {str(model_version)[:8]}: {urteil}\n{lang}"

    if verbose:
        print(grund)
    return grund


def aktive_version(*, pfad: Path | None = None) -> Version | None:
    """Die zuletzt abgenommene Version - oder None, wenn es keine gibt.

    "Aktiv" heisst hier **nicht** "handelt live". Es heisst: Diese
    Version hat die drei Abnahmehuerden genommen und darf als Hypothese
    in den Schatten. Der Unterschied ist der ganze Punkt des Projekts -
    ein Modell, das die Historie schlaegt, ist damit noch nicht
    kostentragfaehig (§A) und noch nicht im Schatten bestaetigt.
    """
    with _conn(pfad) as c:
        r = c.execute(
            "SELECT * FROM modelle WHERE status='abgenommen'"
            " ORDER BY erstellt_at DESC LIMIT 1").fetchone()
    if r is None:
        return None
    return Version(
        model_version=r["model_version"], quelle=r["quelle"] or "",
        horizont=int(r["horizont"] or 0), model_kind=r["model_kind"] or "",
        n_tage_bewertet=int(r["n_tage_bewertet"] or 0),
        schwelle=float(r["schwelle"] or 0),
        merkmale=json.loads(r["merkmale"]) if r["merkmale"] else [],
    )


def verlauf(*, limit: int = 20, pfad: Path | None = None) -> pd.DataFrame:
    """Die Registry als Tabelle, juengste zuerst - fuer Auswertungen.

    `fokus.py` rechnet daraus zurueck, wie viele Handelstage der
    Modellfrage noch fehlen. Deshalb muessen `ic`, `t` und
    `n_tage_bewertet` hier so stehen, wie sie gemessen wurden - nicht
    gerundet und nicht ersatzweise gefuellt.
    """
    with _conn(pfad) as c:
        return pd.read_sql_query(
            "SELECT * FROM modelle ORDER BY erstellt_at DESC LIMIT ?",
            c, params=(limit,))


def bericht(*, pfad: Path | None = None, limit: int = 15) -> str:
    """Die Registry: welche Version wurde wann woran gemessen?"""
    with _conn(pfad) as c:
        df = pd.read_sql_query(
            "SELECT model_version, erstellt_at, quelle, status, n_tage_bewertet,"
            " ic, t, t_roh, aufblaehung, schwelle, horizont, model_kind,"
            " n_symbole, urteil FROM modelle"
            " ORDER BY erstellt_at DESC", c)

    L = ["=" * 78, "  LERNKERN - Modellregistry", "=" * 78, ""]
    if df.empty:
        L += ["  Noch keine Modellversion trainiert.", "",
              "  Erster Lauf:  python scripts/26_lernkern.py"]
        return "\n".join(L)

    L.append(f"  {'Version':<10}{'Quelle':<10}{'Sym':>6}{'Tage':>6}{'IC':>9}"
             f"{'t':>7}{'roh':>7}  Status")
    L.append("  " + "-" * 74)
    for _, r in df.head(limit).iterrows():
        t = f"{r['t']:.2f}" if pd.notna(r["t"]) else "-"
        tr = f"{r['t_roh']:.2f}" if pd.notna(r["t_roh"]) else "-"
        ic = f"{r['ic']:.4f}" if pd.notna(r["ic"]) else "-"
        nt = int(r["n_tage_bewertet"]) if pd.notna(r["n_tage_bewertet"]) else 0
        ns = int(r["n_symbole"]) if pd.notna(r["n_symbole"]) else 0
        # Nur der Kopf der UUID - die volle Kennung steht in der Datenbank
        # und im Dateinamen; hier wuerde sie die Tabelle unlesbar machen.
        L.append(f"  {str(r['model_version'])[:8]:<10}{r['quelle']:<10}{ns:>6}"
                 f"{nt:>6}{ic:>9}{t:>7}{tr:>7}  {r['status']}")
    n_ab = int((df["status"] == "abgenommen").sum())
    L += ["",
          f"  {len(df)} Version(en), davon {n_ab} abgenommen.",
          f"  Abnahmehuerden: >= {MIN_TAGE_BEWERTUNG} bewertete Handelstage, "
          f"t ueber der Zufallsschwelle,",
          f"  IC mindestens {MIN_VERBESSERUNG_IC} besser als die beste bisherige.",
          "",
          "  'abgenommen' heisst: darf als Hypothese in den Schatten.",
          "  NICHT live - der Weg dorthin fuehrt ueber die Flotte."]
    return "\n".join(L)
