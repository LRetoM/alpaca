"""Regelabgleich: Hat der Bot getan, was er tun sollte?

Der Tagesbericht zeigt, WAS passiert ist. Dieses Modul prueft, ob das
mit den Regeln uebereinstimmt, die wir festgelegt haben.

Der Unterschied ist wesentlich: Ein Bot kann fehlerfrei laufen, sauber
protokollieren und trotzdem systematisch etwas anderes tun als geplant -
weil ein Parameter nicht greift, eine Grenze falsch berechnet wird oder
eine Regel im Live-Pfad fehlt, die es in der Simulation gab. Genau solche
Abweichungen sind vorher schon mehrfach aufgetreten (Zeitausstieg feuerte
live nie, Marktfilter war live inaktiv, fester Dollar-Deckel unterlief
die Prozentregel).

Geprueft wird gegen die Regeln, die zum ZEITPUNKT der Entscheidung galten -
nicht gegen die heutige Konfiguration. Parameter aendern sich, und ein
Abgleich gegen den aktuellen Stand wuerde alte Entscheidungen faelschlich
als Regelbruch ausweisen.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

import pandas as pd

from .journal import Journal
from .state import Store

FEHLERQUOTE_VERSTOSS = 0.20
"""Ab welchem Anteil fehlgeschlagener Laeufe es ein Regelbruch ist.

Darunter `auffaellig`: Einzelne Ausfaelle einer Netz-API sind erwartbar
(§H: 11 Tage Dauerbetrieb, 1 HTTP 500, automatisch abgefangen) und der
Daemon ist mit `max_consecutive_errors=10` genau dafuer gebaut. Darueber
scheitert nicht eine Anfrage, sondern der Betrieb."""


@dataclass
class RuleViolation:
    severity: str
    """'verstoss' = Regel gebrochen | 'auffaellig' = erklaerungsbeduerftig"""
    rule: str
    detail: str
    when: str = ""
    symbol: str = ""

    def __str__(self) -> str:
        tag = "[VERSTOSS]  " if self.severity == "verstoss" else "[AUFFAELLIG]"
        where = f" {self.symbol}" if self.symbol else ""
        when = f" ({self.when[:16]})" if self.when else ""
        return f"{tag} {self.rule}{where}{when}\n             {self.detail}"


@dataclass
class AuditReport:
    findings: list[RuleViolation] = field(default_factory=list)
    checks: list[str] = field(default_factory=list)
    stats: dict = field(default_factory=dict)

    @property
    def violations(self) -> list[RuleViolation]:
        return [f for f in self.findings if f.severity == "verstoss"]

    @property
    def clean(self) -> bool:
        return not self.violations

    def add(self, severity: str, rule: str, detail: str,
            when: str = "", symbol: str = "") -> None:
        self.findings.append(RuleViolation(severity, rule, detail, when, symbol))

    def __str__(self) -> str:
        lines = ["=" * 74, "  REGELABGLEICH: Lief der Bot wie geplant?", "=" * 74, ""]

        if self.stats:
            lines.append("  Grundlage:")
            for k, v in self.stats.items():
                lines.append(f"    {k:<34} {v}")
            lines.append("")

        lines.append(f"  {len(self.checks)} Regeln geprueft:")
        for c in self.checks:
            lines.append(f"    - {c}")
        lines.append("")

        if not self.findings:
            lines.append("  ERGEBNIS: Keine Abweichungen. Der Bot hat sich exakt an")
            lines.append("  die Regeln gehalten, die zum Entscheidungszeitpunkt galten.")
        else:
            for f in self.findings:
                lines.append(str(f))
                lines.append("")
            n_v = len(self.violations)
            lines.append(f"  {n_v} Verstoss/Verstoesse, "
                         f"{len(self.findings) - n_v} auffaellig")
            lines.append("")
            lines.append(
                "  ERGEBNIS: Der Bot hat sich an die Regeln gehalten."
                if self.clean
                else "  ERGEBNIS: REGELVERSTOESSE - vor dem Weiterlaufen klaeren."
            )
        return "\n".join(lines)


def _run_configs(j: Journal) -> dict[str, dict]:
    """Regeln je Lauf, wie sie damals galten."""
    runs = j.table("runs", "script = 'live_trade'")
    out = {}
    for _, r in runs.iterrows():
        try:
            out[r["run_id"]] = json.loads(r["config"] or "{}")
        except json.JSONDecodeError:
            out[r["run_id"]] = {}
    return out


def _grund(roh, schluessel):
    """Ein einzelnes Feld aus der JSON-Begruendung einer Entscheidung.

    Defektes JSON gibt `None` zurueck statt zu werfen: Der Regelabgleich
    darf an einer kaputten Zeile nicht abbrechen, sonst bleiben alle
    folgenden Zeilen ungeprueft - der Ausfall waere groesser als der
    Defekt. Ein `None` fuehrt beim Aufrufer zu einem eigenen Befund,
    verschwindet also nicht still.
    """
    if not roh:
        return None
    try:
        return json.loads(roh).get(schluessel)
    except (json.JSONDecodeError, TypeError, AttributeError):
        return None


def check_decisions(j: Journal, report: AuditReport, days: int = 7) -> None:
    """Entsprach jede Kauf- UND Nachkaufentscheidung den damaligen Schwellen?

    **Warum `topup` mitgeprueft wird (23.08.2026, BEFUNDE §G19 Fund 6).**
    Diese Funktion filterte bis dahin auf `action == "buy"`. Nachkaeufe
    sind aber **110 von 304** Live-Entscheidungen (36 %) und damit die
    Mehrheit der Kapitalzuteilung (§G13 Fund 3, §G16 Fund 1).

    `Engine._find_topups` erzwingt fuer sie zwei Regeln:

        score >= min_score              die These traegt heute noch
        gewinn >= topup_min_gain_pct    kein Nachkauf in einen Verlust

    Die zweite ist die teurere. Der Docstring der Engine sagt, warum:
    *"In eine verlustreiche Position nachzukaufen ist Average-Down und
    macht aus einem begrenzten Verlust einen groesseren."* Geprueft wurde
    bis zum 23.08.2026 keine von beiden.

    Nachgemessen an allen 110 bisherigen Nachkaeufen: **null Verstoesse**.
    Die Engine haelt sich daran - es war eine Abdeckungsluecke, kein
    Regelbruch. Genau deshalb gehoert sie geschlossen: Dieses Modul
    existiert fuer den Fall, dass eine Regel aufhoert zu greifen, und
    eine Regel ohne Abgleich hoert unbemerkt auf.
    """
    report.checks.append("Kaufentscheidungen halten die Score-Schwelle ein")
    report.checks.append("Nachkaeufe halten Score-Schwelle und Gewinnvorgabe ein")
    report.checks.append("Positionsgroessen halten max_position_pct ein")

    configs = _run_configs(j)
    since = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=days)

    dec = j.table("decisions")
    if dec.empty:
        return
    # format="mixed": journal.py schreibt Zeitstempel ueber isoformat(), das
    # Mikrosekunden WEGLAESST, wenn sie exakt 0 sind. Ohne explizites Format
    # inferiert pandas das Muster vom ersten Wert und verwirft jeden Wert mit
    # abweichendem Muster als NaT - beobachtet am 03.08.2026: 91 von 1173
    # Zeitstempeln (7,8 %) gingen so verloren, darunter die META-Kaufentscheidung.
    dec["ts"] = pd.to_datetime(dec["ts"], format="mixed", utc=True, errors="coerce")
    dec = dec[(dec["ts"] >= since) & (dec["run_id"].isin(configs))]

    # `buy` UND `topup`: Beide teilen dieselbe Score-Schwelle, weil beide
    # Kapital zuteilen. Getrennt gezaehlt bleiben sie, damit im Bericht
    # sichtbar ist, ob eine Art gar nicht vorkommt - genau das war der
    # Fund bei B09 (§G16 Fund 1: 0 Nachkaeufe im Spiegel, 110 live).
    kapital = dec[dec["action"].isin(("buy", "topup"))
                  & (dec["blocked_by"].isna())]
    report.stats["Kaufentscheidungen geprueft"] = int(
        (kapital["action"] == "buy").sum())
    report.stats["Nachkaeufe geprueft"] = int(
        (kapital["action"] == "topup").sum())

    for _, d in kapital.iterrows():
        cfg = configs.get(d["run_id"], {})
        art = "Nachkauf" if d["action"] == "topup" else "Kauf"

        min_score = cfg.get("min_score")
        if min_score is not None and d["conviction"] is not None:
            if float(d["conviction"]) < float(min_score) - 1e-9:
                report.add(
                    "verstoss", "Score-Schwelle",
                    f"{art}: Score {d['conviction']:.3f} lag unter der "
                    f"damaligen Schwelle {min_score}.",
                    str(d["ts"]), d["symbol"],
                )

        if d["action"] != "topup":
            continue

        # Die Average-Down-Sperre. `gewinn_pct` schreibt
        # `Engine._find_topups` in die Begruendung - ohne dieses Feld
        # laesst sich die Regel nicht nachpruefen, deshalb ist sein
        # Fehlen selbst ein Befund und kein stilles Ueberspringen.
        gewinn = _grund(d["reasons"], "gewinn_pct")
        mindest = cfg.get("topup_min_gain_pct")
        if mindest is None:
            continue
        if gewinn is None:
            report.add(
                "auffaellig", "Nachkauf ohne Gewinnangabe",
                "Die Begruendung traegt kein `gewinn_pct` - ob in eine "
                "Verlustposition nachgekauft wurde, ist an dieser Zeile "
                "nicht pruefbar.",
                str(d["ts"]), d["symbol"],
            )
            continue
        if float(gewinn) < float(mindest) - 1e-9:
            report.add(
                "verstoss", "Nachkauf in eine Verlustposition",
                f"Position lag bei {float(gewinn):+.2%}, erlaubt ist ab "
                f"{float(mindest):+.2%}. Nachkaufen in eine fallende "
                f"Position ist Average-Down: aus einem begrenzten Verlust "
                f"wird ein groesserer.",
                str(d["ts"]), d["symbol"],
            )


def check_position_sizes(j: Journal, report: AuditReport, equity: float) -> None:
    """Ueberschreitet eine Position ihre Groessengrenze?"""
    report.checks.append("Keine Position ueber der Einzelgrenze")

    configs = _run_configs(j)
    if not configs:
        return
    latest = list(configs.values())[-1]
    max_pct = latest.get("max_position_pct")
    if max_pct is None or equity <= 0:
        return

    from . import account

    pos = account.positions()
    if pos.empty:
        return

    limit = equity * float(max_pct)
    for sym, row in pos.iterrows():
        value = float(row["market_value"] or 0)
        # Toleranz: Eine Position darf durch Kursgewinne ueber die Grenze
        # wachsen - verboten ist nur der EINSTIEG oberhalb der Grenze.
        if value > limit * 1.25:
            report.add(
                "auffaellig", "Einzelposition ueber der Grenze",
                f"${value:,.2f} = {value / equity:.1%} des Kapitals "
                f"(Grenze {float(max_pct):.0%}). Bei starkem Kursgewinn "
                "normal, sonst pruefen.",
                symbol=sym,
            )


def check_exposure(report: AuditReport, equity: float, invested: float) -> None:
    """Bleibt die Gesamtinvestition unter target_invested?"""
    report.checks.append("Gesamtinvestition unter der Obergrenze")
    if equity <= 0:
        return
    ratio = invested / equity
    report.stats["Investiert"] = f"${invested:,.2f} ({ratio:.1%} des Kapitals)"
    if ratio > 0.95:
        report.add(
            "verstoss", "Gesamtinvestition",
            f"{ratio:.1%} des Kapitals investiert - die Obergrenze liegt "
            "bei 90 %, der Cash-Puffer fehlt.",
        )


def check_exits(j: Journal, report: AuditReport) -> None:
    """Wurden Positionen nach den Ausstiegsregeln geschlossen?

    Prueft besonders den Zeitausstieg: Er hat live schon einmal gar nicht
    ausgeloest, weil die Haltedauer nicht mitgezaehlt wurde.
    """
    report.checks.append("Positionen ueberschreiten die Haltedauer nicht")

    # Aus dem juengsten Lauf lesen, der die Regeln tatsaechlich mitgeschrieben
    # hat. Faellt zurueck auf die aktuelle Konfiguration - sonst bliebe die
    # Pruefung stumm, solange noch alte Laeufe ohne Regelprotokoll vorliegen,
    # und genau dieser Fehler (Zeitausstieg feuert nie) waere unentdeckt.
    configs = _run_configs(j)
    max_hold = next(
        (c["max_hold_days"] for c in reversed(list(configs.values()))
         if c.get("max_hold_days") is not None),
        None,
    )
    if max_hold is None:
        from .engine import EngineConfig

        max_hold = EngineConfig.for_reversal().max_hold_days

    store = Store()
    stored = store.load_positions()
    today = pd.Timestamp.now(tz="UTC").normalize()

    for sym, meta in stored.items():
        entry = pd.Timestamp(meta["entry_date"])
        if entry.tz is None:
            entry = entry.tz_localize("UTC")
        held = len(pd.bdate_range(entry.normalize(), today)) - 1
        if held > int(max_hold):
            report.add(
                "verstoss", "Zeitausstieg",
                f"Seit {held} Handelstagen gehalten, erlaubt sind "
                f"{max_hold}. Der Zeitausstieg greift nicht.",
                symbol=sym,
            )


def check_state_consistency(report: AuditReport) -> None:
    """Stimmen Bot-Zustand und Broker-Depot ueberein?"""
    report.checks.append("Bot-Zustand deckt sich mit dem Broker-Depot")

    from . import account

    try:
        broker = set(account.positions().index)
    except Exception as e:  # noqa: BLE001
        report.add("auffaellig", "Depotabgleich",
                   f"Kontoabruf fehlgeschlagen: {type(e).__name__}")
        return

    stored = set(Store().load_positions())
    if broker - stored:
        report.add(
            "verstoss", "Position ohne Zustand",
            f"{', '.join(sorted(broker - stored))} - der Bot kennt Stop und "
            "Ziel dieser Positionen nicht und kann sie nicht regelkonform "
            "schliessen.",
        )
    if stored - broker:
        report.add(
            "auffaellig", "Verwaister Zustand",
            f"{', '.join(sorted(stored - broker))} - Zustand zu Positionen, "
            "die es beim Broker nicht gibt.",
        )


QUOTE_ABWEICHUNG_GRENZE = 0.05
"""Ab welcher Abweichung ein Positionspreis als unglaubwuerdig gilt.

Bewusst milder als `live._MAX_QUOTE_ABWEICHUNG` (2 %): Jene Schwelle
entscheidet, welcher von zwei Kursen als Referenz dient, und ein
Fehlalarm kostet dort nichts. Diese hier meldet einen Befund - sie soll
grobe Ausreisser fangen, nicht normale Intraday-Bewegung."""


def check_positionspreise(report: AuditReport) -> None:
    """Deckt sich der Positionspreis des Brokers mit dem letzten echten Trade?

    **Der Fund vom 24.08.2026 (BEFUNDE §G29).** Das Depot meldete an
    diesem Tag -2,07 %. Davon waren **1,24 Prozentpunkte ein
    Datenfehler**: Alpaca bepreiste DKS mit 150,50 $, waehrend der letzte
    tatsaechlich gehandelte Kurs bei 179,64 $ lag - eine Abweichung von
    -16,2 % auf einer Position von 9.000 $. Die zugehoerige Quote war
    sichtbar kaputt (Bid 171,49 / Ask 187,15, Spanne 9 % des Kurses).

    **Warum das mehr ist als ein Schoenheitsfehler.** `risiko._kennzahlen`
    rechnet auf `konto["equity"]` und `positionswert()` auf
    `market_value` - beides kommt vom Broker und traegt den falschen Kurs
    weiter. Der gemeldete Drawdown war dadurch um 1,2 Prozentpunkte zu
    gross. Bei der 20-%-Sperre entscheidet genau diese Zahl darueber, ob
    der Handel stillgelegt wird.

    **Warum trotzdem NICHT ueberschrieben wird.** Die Zahl des Brokers ist
    die verbindliche - unsere eigene Rechnung danebenzustellen hiesse,
    zwei Buchfuehrungen zu haben. Und fuer eine SPERRE ist der
    pessimistischere Wert die sichere Richtung: Er sperrt frueher, nicht
    spaeter. Gemeldet werden muss die Abweichung trotzdem, sonst bleibt
    ein 16-%-Fehler unsichtbar - und in der anderen Richtung wuerde er
    einen echten Verlust verdecken.

    Der Handelspfad ist von diesem Fehler nicht betroffen:
    `live._quote_plausibel` prueft jede Quote gegen den letzten Trade und
    verwarf sie hier korrekt, weshalb der Intraday-Stop NICHT ausgeloest
    hat (Stop 166,67, echter Kurs 179,64).
    """
    report.checks.append("Positionspreise decken sich mit echten Trades")

    from . import account, data

    try:
        pos = account.positions()
    except Exception as e:  # noqa: BLE001
        report.add("auffaellig", "Positionspreise",
                   f"Kontoabruf fehlgeschlagen: {type(e).__name__}")
        return
    if pos.empty:
        return
    try:
        snap = data.snapshots(list(pos.index))
    except Exception as e:  # noqa: BLE001
        report.add("auffaellig", "Positionspreise",
                   f"Kursabruf fehlgeschlagen: {type(e).__name__}")
        return

    fehlbetrag = 0.0
    for sym, r in pos.iterrows():
        try:
            broker = float(r["current_price"] or 0)
            letzter = float(snap.loc[sym, "last"] or 0)
            qty = float(r["qty"] or 0)
        except (KeyError, TypeError, ValueError):
            continue
        if broker <= 0 or letzter <= 0:
            continue
        abw = broker / letzter - 1
        fehlbetrag += qty * (letzter - broker)
        if abs(abw) > QUOTE_ABWEICHUNG_GRENZE:
            report.add(
                "auffaellig", "Positionspreis weicht vom letzten Trade ab",
                f"Broker {broker:.2f}, letzter echter Trade {letzter:.2f} "
                f"({abw:+.1%}, {qty * (letzter - broker):+,.0f} $ Unterschied "
                f"im Depotwert). Kontowert und Drawdown rechnen auf dem "
                f"Brokerkurs - eine Bewegung dieser Groesse ist damit "
                f"moeglicherweise gar keine (§G29).",
                symbol=str(sym),
            )
    report.stats["Preisdifferenz im Depotwert"] = f"${fehlbetrag:+,.2f}"


def check_gaps(j: Journal, report: AuditReport, expected_interval_min: int = 15,
               days: int = 1) -> None:
    """Lief der Bot ohne Unterbrechung durch?"""
    report.checks.append("Keine unerwarteten Laufzeitluecken")

    runs = j.table("runs", "script = 'live_trade'")
    if runs.empty:
        return
    runs["started_at"] = pd.to_datetime(runs["started_at"], format="mixed", utc=True)
    since = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=days)
    recent = runs[runs["started_at"] >= since].sort_values("started_at")
    report.stats["Handelslaeufe"] = len(recent)

    # Die QUOTE entscheidet ueber die Schwere, nicht die absolute Zahl.
    #
    # Bis zum 22.08.2026 war jeder einzelne fehlgeschlagene Lauf ein
    # `verstoss`. Real gemessen: 1 von 91 Laeufen endete mit einem HTTP 500
    # von Alpaca - `docs/BEFUNDE.md` §H fuehrt genau diesen Vorfall als
    # BESTANDENE Betriebspruefung ("automatisch abgefangen"). Ein
    # transienter Netzfehler ist kein Regelbruch; der Daemon ist mit
    # `max_consecutive_errors=10` ausdruecklich dafuer gebaut.
    #
    # Warum das zaehlt: Mit diesem Abgleich im Health-Check (BETRIEBSPLAN
    # §8) haette die Ampel ab sofort dauerhaft ROT gezeigt - und eine
    # Warnung, die immer leuchtet, wird weggeklickt (`docs/LERNTEMPO.md`
    # §5). Dann faellt auch der echte Regelbruch nicht mehr auf.
    #
    # Ueber der Quote ist es keine Panne mehr, sondern ein Zustand: Dann
    # scheitert nicht eine Anfrage, sondern der Betrieb.
    failed = recent[recent["status"] == "failed"]
    if len(failed):
        quote = len(failed) / max(1, len(recent))
        schwer = quote > FEHLERQUOTE_VERSTOSS
        report.stats["Fehlgeschlagene Laeufe"] = f"{len(failed)}/{len(recent)} ({quote:.0%})"
        report.add(
            "verstoss" if schwer else "auffaellig", "Fehlgeschlagene Laeufe",
            f"{len(failed)} von {len(recent)} Laeufen mit Fehler beendet "
            f"({quote:.0%})."
            + ("  Das ist kein Einzelfall mehr - Ursache klaeren."
               if schwer else
               "  Einzelne Ausfaelle einer Netz-API sind erwartbar und "
               "werden vom Daemon abgefangen (§H); sichtbar bleiben sie "
               "trotzdem."),
        )

    if len(recent) > 1:
        gaps = recent["started_at"].diff().dropna()
        worst = gaps.max().total_seconds() / 60
        report.stats["Groesste Luecke"] = f"{worst:.0f} Minuten"
        # Boersenschluss erzeugt naturgemaess grosse Luecken - erst ab
        # dem Vielfachen des Takts waehrend der Handelszeit auffaellig.
        if worst > expected_interval_min * 4 and worst < 900:
            report.add(
                "auffaellig", "Laufzeitluecke",
                f"{worst:.0f} Minuten zwischen zwei Laeufen (Takt: "
                f"{expected_interval_min} Min). Absturz oder Neustart?",
            )


def run_audit(days: int = 7) -> AuditReport:
    """Vollstaendiger Regelabgleich."""
    from . import account

    j = Journal()
    report = AuditReport()

    try:
        acct = account.account_summary()
        equity = float(acct["portfolio_value"])
        pos = account.positions()
        invested = float(pos["market_value"].sum()) if not pos.empty else 0.0
        report.stats["Kapital"] = f"${equity:,.2f}"
        report.stats["Offene Positionen"] = len(pos)
    except Exception as e:  # noqa: BLE001
        report.add("auffaellig", "Kontoabruf", f"{type(e).__name__}: {e}")
        equity = invested = 0.0

    check_gaps(j, report, days=days)
    check_decisions(j, report, days=days)
    check_position_sizes(j, report, equity)
    check_exposure(report, equity, invested)
    check_exits(j, report)
    check_state_consistency(report)
    check_positionspreise(report)
    return report
