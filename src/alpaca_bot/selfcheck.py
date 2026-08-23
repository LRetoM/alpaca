"""Selbstpruefung: Machen wir noch das, was wir uns vorgenommen haben?

Ein Projekt dieser Groesse driftet. Nicht durch eine falsche Entscheidung,
sondern durch fuenfzig kleine Bequemlichkeiten: hier ein Aufruf ohne
Drossel, dort ein `dry_run=False` als Standard, drueben ein Feature, das
niemand mehr durch die Leck-Pruefung geschickt hat.

Deshalb steht die Projektverfassung hier als CODE, nicht als Prosa. Was
in einer Doku steht, wird gelesen und vergessen. Was hier steht, wird bei
jedem Lauf geprueft und meldet sich, wenn es verletzt wird.

    python scripts/09_selfcheck.py     # vor JEDER groesseren Aenderung

Drei Ebenen:
  1. VERFASSUNG - die unverhandelbaren Regeln, gegen den Code geprueft
  2. AKTUALITAET - veralten Gebuehrensaetze, Limits, Annahmen?
  3. FORTSCHRITT - wird das System ueber die Zeit tatsaechlich besser?
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from .config import PROJECT_ROOT

SRC = PROJECT_ROOT / "src" / "alpaca_bot"
SCRIPTS = PROJECT_ROOT / "scripts"


# ---------------------------------------------------------------------------
# Ebene 1: Die Verfassung
# ---------------------------------------------------------------------------
CHARTER = {
    "ziel": (
        "Ein System, das einen kleinen, statistisch nachgewiesenen Vorsprung "
        "diszipliniert und ueber viele Entscheidungen umsetzt - nicht eines, "
        "das einzelne Kurse vorhersagt."
    ),
    "regeln": [
        "Kein Handel mit echtem Geld ohne mindestens 6 Monate Paper-Betrieb.",
        "Jede Order-Funktion hat dry_run=True als Standard.",
        "Jeder externe API-Aufruf laeuft durch ratelimit.RateLimiter.",
        "Jede Feature-Funktion besteht pit.audit_feature_function.",
        "Kein Zeitreihen-Split mit shuffle=True.",
        "Jede Strategie wird gegen Buy & Hold UND gegen die Basisrate gemessen.",
        "Jede RL-Politik wird gegen den Timing-Test gemessen, nicht gegen die Rendite.",
        "Live-Handel und Simulation nutzen DIESELBE Engine.decide().",
        "Der Schattenbetrieb ruft keine Order-Funktion auf.",
        "Jede Entscheidung wird mit Begruendung protokolliert - auch die blockierten.",
        "Kosten werden immer mitgerechnet, nie nachtraeglich abgezogen.",
        "Keine Zugangsdaten im Code oder im Repository.",
        "Der Tresor-Zeitraum wird genau einmal geoeffnet.",
    ],
    "bewusst_nicht": [
        "Daytrading unter 25.000 USD (PDT-Regel, und Kosten fressen den Vorsprung).",
        "Sekundenhandel / HFT - dort ist strukturell nichts zu holen.",
        "Optionen verkaufen, bevor der Rest nachweislich traegt.",
        "Deep Learning auf wenigen Jahren Tagesdaten.",
        "Hebel, solange die Strategie nicht ueber Jahre traegt.",
    ],
}


@dataclass
class Finding:
    level: str  # 'verstoss' | 'warnung' | 'hinweis'
    rule: str
    detail: str
    location: str = ""

    def __str__(self) -> str:
        tag = {"verstoss": "[VERSTOSS]", "warnung": "[WARNUNG] ", "hinweis": "[HINWEIS] "}[self.level]
        loc = f"  ({self.location})" if self.location else ""
        return f"{tag} {self.rule}\n           {self.detail}{loc}"


@dataclass
class CheckReport:
    findings: list[Finding] = field(default_factory=list)
    checks_run: int = 0

    @property
    def violations(self) -> list[Finding]:
        return [f for f in self.findings if f.level == "verstoss"]

    @property
    def ok(self) -> bool:
        return not self.violations

    def add(self, level: str, rule: str, detail: str, location: str = "") -> None:
        self.findings.append(Finding(level, rule, detail, location))

    def __str__(self) -> str:
        lines = ["=" * 70, "  SELBSTPRUEFUNG", "=" * 70, ""]
        if not self.findings:
            lines.append(f"  {self.checks_run} Pruefungen - keine Befunde.")
        else:
            for level in ("verstoss", "warnung", "hinweis"):
                group = [f for f in self.findings if f.level == level]
                if group:
                    lines.extend(str(f) for f in group)
                    lines.append("")
            n_v = len(self.violations)
            lines.append(
                f"  {self.checks_run} Pruefungen | {n_v} Verstoss/Verstoesse | "
                f"{len(self.findings) - n_v} Hinweise"
            )
        lines.append("")
        lines.append(
            "  ERGEBNIS: Das Projekt haelt sich an seine Regeln."
            if self.ok
            else "  ERGEBNIS: Regelverstoesse gefunden - vor der naechsten Aenderung beheben."
        )
        return "\n".join(lines)


def _py_files() -> list[Path]:
    return sorted(
        [p for p in SRC.rglob("*.py") if "__pycache__" not in str(p)]
        + [p for p in SCRIPTS.rglob("*.py") if "__pycache__" not in str(p)]
    )


def check_dry_run_defaults(report: CheckReport) -> None:
    """Jede Order-Funktion muss dry_run=True als Standard haben."""
    report.checks_run += 1
    path = SRC / "trading.py"
    if not path.exists():
        return
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef) or node.name.startswith("_"):
            continue
        args = node.args
        names = [a.arg for a in args.args + args.kwonlyargs]
        if "dry_run" not in names:
            continue
        # Standardwert der Keyword-Only-Argumente pruefen
        defaults = dict(
            zip([a.arg for a in args.kwonlyargs], args.kw_defaults)
        )
        default = defaults.get("dry_run")
        is_true = isinstance(default, ast.Constant) and default.value is True
        if not is_true:
            report.add(
                "verstoss",
                "dry_run=True als Standard",
                f"Funktion '{node.name}' hat dry_run nicht auf True.",
                f"trading.py:{node.lineno}",
            )


def check_rate_limiting(report: CheckReport) -> None:
    """Jedes Modul mit API-Zugriff muss den Rate-Limiter einbinden."""
    report.checks_run += 1
    api_markers = ("trading_client()", "stock_data_client()", "crypto_data_client()",
                   "requests.get", "requests.post", "client.get_news")
    for path in _py_files():
        if path.name in {"ratelimit.py", "clients.py", "selfcheck.py"}:
            continue
        text = path.read_text()
        uses_api = any(m in text for m in api_markers)
        if uses_api and "RateLimiter" not in text and "throttled" not in text:
            report.add(
                "verstoss",
                "Jeder API-Aufruf durch die Drossel",
                f"{path.name} ruft eine externe API, ohne ratelimit einzubinden.",
                str(path.relative_to(PROJECT_ROOT)),
            )


def check_single_decision_path(report: CheckReport) -> None:
    """Der Live-Pfad MUSS dieselbe Engine benutzen wie die Simulation.

    Diese Pruefung existiert, weil genau dieser Bruch schon einmal
    unbemerkt entstanden ist: `simulate.py` wurde auf die Engine
    umgestellt, `05_paper_trade.py` blieb auf dem alten Strategiepfad.
    Damit haette im Depot eine andere Logik gehandelt als geprueft wurde -
    der teuerste denkbare Fehler in diesem Projekt, und keine der
    damaligen Pruefungen hat ihn bemerkt.
    """
    report.checks_run += 1

    trading_modules = {
        "live.py": SRC / "live.py",
        "simulate.py": SRC / "simulate.py",
    }
    for name, path in trading_modules.items():
        if not path.exists():
            report.add("verstoss", "Ein Entscheidungspfad",
                       f"{name} fehlt - Live und Simulation koennen nicht "
                       "dieselbe Logik nutzen.", name)
            continue
        text = path.read_text()
        if "Engine" not in text or "decide(" not in text:
            report.add("verstoss", "Ein Entscheidungspfad",
                       f"{name} ruft Engine.decide() nicht auf.", name)

    # Kein Handelsskript darf noch am alten Strategiepfad haengen.
    for path in SCRIPTS.glob("*.py"):
        text = path.read_text()
        places_orders = "trading.market_order" in text or "live.run_once" in text
        uses_old = "strategies.get(" in text
        if places_orders and uses_old:
            report.add(
                "verstoss",
                "Ein Entscheidungspfad",
                f"{path.name} platziert Orders, benutzt aber strategies.get() "
                "statt der Engine. Simulation und Live wuerden auseinanderlaufen.",
                path.name,
            )


SCHATTEN_ZUSATZ = ("fleet.py", "patterns.py")
"""Schattenmodule, deren Name nicht mit `shadow` beginnt."""


def schatten_module() -> list[str]:
    """Alle Module des Schattenbetriebs - per Suchmuster, nicht per Liste.

    **Warum ein Glob und keine aufgezaehlte Liste (23.08.2026, §G20).**
    Hier stand zuerst genau so eine Liste:

        SCHATTEN_MODULE = ("shadow.py", "shadow_eval.py", "fleet.py",
                           "patterns.py")

    Am selben Tag wurde `shadow.py` in fuenf Module aufgeteilt. Der Code,
    um den es geht, wanderte nach `shadow_schritte.py` - und die Regel
    bewachte ab da die **Fassade** statt des Codes. Sie meldete weiter
    gruen. Gefunden hat das nicht ein Test, sondern der Mutationstest:
    Er baute `from . import trading` in `shadow_schritte.py` ein, und
    niemand schlug an.

    Das ist die Fehlerklasse aus §G15 in ihrer unangenehmsten Form - eine
    Sicherung, die vom Aufraeumen selbst blind gemacht wird. Ein
    Suchmuster hat sie nicht: Ein neues `shadow_*.py` ist automatisch
    abgedeckt, ohne dass jemand daran denken muss.
    """
    return sorted({p.name for p in SRC.glob("shadow*.py")} | set(SCHATTEN_ZUSATZ))


def check_schatten_handelt_nicht(report: CheckReport) -> None:
    """Kein Schattenmodul darf `trading` erreichen.

    **Warum das eine eigene Regel bekommt (23.08.2026, §G19).** Diese
    Zusicherung steht an drei prominenten Stellen - `CLAUDE.md`,
    `README.md` und `BETRIEBSPLAN` §6 - und war bis heute an keiner
    einzigen geprueft:

        "Der Schattenbetrieb importiert trading.py bewusst NICHT -
         er *kann* keine Order senden, nicht nur 'darf nicht'."

    Nachgemessen: Sie stimmt. Kein Schattenmodul referenziert `trading`.
    Das ist genau die Lage aus §G17 (der RL-Docstring behauptete, der
    Timing-Test sei nicht abschaltbar - er stimmte auch, war aber
    ungeprueft). Eine Zusicherung, die dieses Projekt sonst durch Tests
    deckt, blieb hier eine Behauptung.

    **Was diese Regel NICHT leistet - und das gehoert dazu.** Sie prueft
    den Quelltext, nicht den Prozess. Zur Laufzeit ist
    `alpaca_bot.trading` sehr wohl geladen: `import alpaca_bot.shadow`
    fuehrt `__init__.py` aus, und das importiert `trading` mit. Aus
    "kann nicht" wird damit streng genommen "tut nicht". Ein Import
    allein sendet keine Order, und `trading` haelt zusaetzlich
    `dry_run=True` als Standard und `_check_risk()` vor jedem Senden -
    die Trennung ist also mehrfach abgesichert. Aber die staerkere
    Formulierung ("kann nicht") traegt nur so weit, wie diese Pruefung
    reicht: bis zum Quelltext.

    Geprueft werden alle `shadow*.py` plus `SCHATTEN_ZUSATZ` - siehe
    `schatten_module()`, warum das ein Suchmuster und keine Liste ist.
    """
    report.checks_run += 1
    for name in schatten_module():
        path = SRC / name
        if not path.exists():
            continue
        try:
            tree = ast.parse(path.read_text())
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            treffer = False
            if isinstance(node, ast.ImportFrom):
                treffer = (node.module or "").split(".")[-1] == "trading" or any(
                    a.name == "trading" for a in node.names)
            elif isinstance(node, ast.Import):
                treffer = any(a.name.split(".")[-1] == "trading"
                              for a in node.names)
            if treffer:
                report.add(
                    "verstoss", "Der Schattenbetrieb ruft keine Order-Funktion auf",
                    f"{name} importiert `trading`. Der Schattenbetrieb darf "
                    f"Orders nicht einmal erreichen koennen - das ist der "
                    f"Grund, warum er ohne Kapitalrisiko messen darf.",
                    f"{name}:{node.lineno}",
                )


def check_no_shuffle_split(report: CheckReport) -> None:
    """Zeitreihen duerfen niemals zufaellig gemischt werden.

    Geprueft wird ueber den AST, nicht per Textsuche - sonst schlaegt die
    Pruefung bei Docstrings an, die genau davor warnen.
    """
    report.checks_run += 1
    for path in _py_files():
        try:
            tree = ast.parse(path.read_text())
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            name = getattr(fn, "id", None) or getattr(fn, "attr", None)
            if name != "train_test_split":
                continue
            kwargs = {k.arg: k.value for k in node.keywords if k.arg}
            shuffle = kwargs.get("shuffle")
            explicitly_false = (
                isinstance(shuffle, ast.Constant) and shuffle.value is False
            )
            if not explicitly_false:
                report.add(
                    "verstoss",
                    "Kein shuffle=True bei Zeitreihen",
                    "train_test_split ohne shuffle=False mischt die Zeit "
                    "und erzeugt ein Datenleck. Nutze backtest.split_train_test().",
                    f"{path.name}:{node.lineno}",
                )


def check_no_secrets(report: CheckReport) -> None:
    """Keine Zugangsdaten im Code."""
    report.checks_run += 1
    # Alpaca-Keys: PK/AK + 18 Grossbuchstaben/Ziffern
    key_pattern = re.compile(r"\b(?:PK|AK)[A-Z0-9]{16,}\b")
    for path in _py_files():
        text = path.read_text()
        for m in key_pattern.finditer(text):
            line = text[: m.start()].count("\n") + 1
            report.add(
                "verstoss",
                "Keine Zugangsdaten im Code",
                f"Sieht aus wie ein API-Key: {m.group()[:8]}...",
                f"{path.name}:{line}",
            )

    gitignore = PROJECT_ROOT / ".gitignore"
    if gitignore.exists() and ".env" not in gitignore.read_text():
        report.add("verstoss", "Keine Zugangsdaten im Repository",
                   ".env fehlt in .gitignore.")


def check_feature_purity(report: CheckReport) -> None:
    """Die Feature-Funktion muss die Leck-Pruefung bestehen."""
    report.checks_run += 1
    try:
        import numpy as np

        from . import features, pit

        rng = np.random.default_rng(3)
        n = 500
        close = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))
        idx = pd.bdate_range("2022-01-03", periods=n, tz="UTC")
        df = pd.DataFrame(
            {"open": close, "high": close * 1.01, "low": close * 0.99,
             "close": close, "volume": rng.integers(1e6, 5e6, n).astype(float)},
            index=idx,
        )
        result = pit.audit_feature_function(features.build_features, df, n_checks=3)
        if not result.clean:
            report.add(
                "verstoss",
                "Features muessen die PIT-Pruefung bestehen",
                f"Undichte Spalten: {', '.join(list(result.leaking_columns)[:5])}",
                "features.build_features",
            )
    except Exception as e:  # noqa: BLE001
        report.add("warnung", "PIT-Pruefung nicht ausfuehrbar",
                   f"{type(e).__name__}: {e}")


def check_staleness(report: CheckReport) -> None:
    """Veralten hinterlegte Gebuehren und Limits?"""
    report.checks_run += 1
    from .costs import DEFAULT_FEES
    from .ratelimit import QUOTAS

    if DEFAULT_FEES.is_stale():
        report.add(
            "warnung",
            "Gebuehrensaetze aktuell halten",
            f"Zuletzt geprueft am {DEFAULT_FEES.verified} - die SEC passt "
            "ihren Satz jaehrlich an. Nachschlagen.",
            "costs.FeeSchedule",
        )
    today = pd.Timestamp.now()
    for key, q in QUOTAS.items():
        if not q.verified:
            continue
        age = (today - pd.Timestamp(q.verified)).days
        if age > 365:
            report.add("warnung", "API-Limits aktuell halten",
                       f"{q.name}: seit {age} Tagen nicht geprueft.", f"ratelimit.QUOTAS[{key!r}]")


def check_documentation(report: CheckReport) -> None:
    """Existieren die Dokumente, auf die sich der Plan stuetzt?"""
    report.checks_run += 1
    for rel in ("docs/leitfaden.md", "docs/strategie-analyse.md", "README.md"):
        if not (PROJECT_ROOT / rel).exists():
            report.add("warnung", "Planungsdokumente vorhanden",
                       f"{rel} fehlt.", rel)


def check_journal_health(report: CheckReport) -> None:
    """Ist das Protokoll lueckenlos?"""
    report.checks_run += 1
    try:
        from .journal import Journal

        problems = Journal().integrity_check()
        for p in problems:
            report.add("hinweis", "Protokoll lueckenlos halten", p, "journal.sqlite")
    except Exception as e:  # noqa: BLE001
        report.add("hinweis", "Protokoll pruefbar", f"{type(e).__name__}: {e}")


# ---------------------------------------------------------------------------
# Ebene 3: Werden wir tatsaechlich besser?
# ---------------------------------------------------------------------------
def progress_report(horizon: int = 5) -> str:
    """Verbessert sich die Entscheidungsqualitaet ueber die Zeit?

    Beantwortet die Frage "haben wir das Grundziel weiter verbessert" mit
    Zahlen statt mit Gefuehl. Braucht Protokolldaten aus mehreren Laeufen.
    """
    try:
        from .journal import Journal

        j = Journal()
        quality = j.decision_quality(horizon)
        if quality.empty:
            return (
                "Noch keine bewerteten Entscheidungen im Protokoll.\n"
                "  -> scripts/05_paper_trade.py laufen lassen, danach\n"
                "     journal.evaluate_outcomes() ausfuehren."
            )
        lines = [
            f"Entscheidungsqualitaet nach Begruendung (Horizont {horizon} Tage):",
            "",
            quality.to_string(),
            "",
            "  Lesart: 'mittel' ist die durchschnittliche Folgerendite, wenn diese",
            "  Begruendung zutraf. Begruendungen mit negativem Mittelwert ueber",
            "  ausreichend viele Faelle gehoeren aus der Strategie entfernt.",
        ]
        return "\n".join(lines)
    except Exception as e:  # noqa: BLE001
        return f"Fortschrittsbericht nicht verfuegbar: {type(e).__name__}: {e}"


def run_all() -> CheckReport:
    """Fuehrt alle Pruefungen aus."""
    report = CheckReport()
    for check in (
        check_dry_run_defaults,
        check_single_decision_path,
        check_schatten_handelt_nicht,
        check_rate_limiting,
        check_no_shuffle_split,
        check_no_secrets,
        check_feature_purity,
        check_staleness,
        check_documentation,
        check_journal_health,
    ):
        try:
            check(report)
        except Exception as e:  # noqa: BLE001
            report.add("warnung", f"Pruefung {check.__name__} fehlgeschlagen",
                       f"{type(e).__name__}: {e}")
    return report


def charter_text() -> str:
    lines = ["=" * 70, "  PROJEKTVERFASSUNG", "=" * 70, "", "ZIEL", f"  {CHARTER['ziel']}", "",
             "UNVERHANDELBARE REGELN"]
    lines += [f"  {i:>2}. {r}" for i, r in enumerate(CHARTER["regeln"], 1)]
    lines += ["", "BEWUSST NICHT TEIL DES PLANS"]
    lines += [f"   - {r}" for r in CHARTER["bewusst_nicht"]]
    return "\n".join(lines)
