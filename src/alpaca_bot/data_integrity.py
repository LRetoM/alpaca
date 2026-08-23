"""Automatisierte Pruefung: sind die gesammelten Daten wirklich richtig?

`audit.py` prueft, ob der Bot sich an seine HANDELSREGELN gehalten hat.
`selfcheck.py` prueft den CODE gegen die Projektregeln. Dieses Modul
prueft eine dritte, eigene Sache: ob die DATEN SELBST - die Zahlen in
den SQLite-Datenbanken, auf denen jede spaetere Auswertung aufbaut -
strukturell in Ordnung sind.

Der Grund, warum das ein eigenes Modul braucht: Am 03.08.2026 wurden bei
einer manuellen Pruefung vier Datenfehler gefunden, die JEDER fuer sich
lautlos waren - kein Absturz, keine Fehlermeldung, einfach falsche oder
fehlende Zahlen in Auswertungen, die auf den ersten Blick plausibel
aussahen (z.B. "0 Kaufentscheidungen" trotz echter Kaeufe). Eine
manuelle Ad-hoc-Pruefung findet solche Fehler nur, wenn zufaellig jemand
gezielt danach sucht. Dieses Modul automatisiert genau die Pruefungen,
die diese vier Fehler damals aufgedeckt haben, damit sie reproduzierbar
und wiederholbar sind - nicht nur einmalig von Hand gemacht.

Jeder Check hier ist die direkte Lehre aus einem echten Vorfall:

    Zeitstempel-Format    -> "Kaufentscheidungen geprueft: 0" trotz Kaeufen
    Platzhalter-Order-IDs -> Verkaeufe nie mit Fuellpreis abgleichbar
    Primaerschluessel-Kollision -> Dry-Run-Orders ueberschrieben sich selbst
    Fuellpreis-Vollstaendigkeit -> Orders aelter als das Abgleichfenster verloren
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from .journal import JOURNAL_DB, Journal
from .lifecycle import LIFECYCLE_DB
from .state import STATE_DB


@dataclass
class Finding:
    severity: str
    """'fehler' = Daten sind nachweislich falsch/verloren |
    'auffaellig' = erklaerungsbeduerftig, nicht zwingend falsch"""
    check: str
    detail: str

    def __str__(self) -> str:
        tag = "[FEHLER]    " if self.severity == "fehler" else "[AUFFAELLIG]"
        return f"{tag} {self.check}\n             {self.detail}"


@dataclass
class IntegrityReport:
    findings: list[Finding] = field(default_factory=list)
    checks: list[str] = field(default_factory=list)
    stats: dict = field(default_factory=dict)

    @property
    def errors(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "fehler"]

    @property
    def ok(self) -> bool:
        return not self.errors

    def add(self, severity: str, check: str, detail: str) -> None:
        self.findings.append(Finding(severity, check, detail))

    def ampel(self) -> str:
        """Eine Zeile, verstaendlich ohne Vorwissen - fuer den Health-Check."""
        if not self.ok:
            return f"ROT - {len(self.errors)} Datenfehler gefunden"
        if self.findings:
            return f"GELB - {len(self.findings)} Auffaelligkeit(en), kein Datenverlust"
        return "GRUEN - alle Datenintegritaets-Pruefungen bestanden"

    def __str__(self) -> str:
        lines = ["=" * 74, "  DATENINTEGRITAET", "=" * 74, "", f"  Status: {self.ampel()}", ""]
        if self.stats:
            lines.append("  Grundlage:")
            for k, v in self.stats.items():
                lines.append(f"    {k:<34} {v}")
            lines.append("")
        lines.append(f"  {len(self.checks)} Pruefungen:")
        for c in self.checks:
            lines.append(f"    - {c}")
        lines.append("")
        if self.findings:
            for f in self.findings:
                lines.append(str(f))
                lines.append("")
        else:
            lines.append("  Keine Befunde.")
        return "\n".join(lines)


def _table_exists(db: Path, name: str) -> bool:
    if not db.exists():
        return False
    with sqlite3.connect(db) as c:
        row = c.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
        ).fetchone()
    return row is not None


def check_timestamps(j: Journal, report: IntegrityReport) -> None:
    """Sind ALLE Zeitstempel im Journal auswertbar - nicht nur die meisten?

    Lehre aus dem 03.08.2026-Vorfall: pandas' automatische Formaterkennung
    verwirft Zeilen mit abweichendem Zeitstempel-Muster lautlos als NaT,
    wenn nicht explizit format='mixed' angegeben wird. Ohne diesen Check
    faellt das nur auf, wenn jemand zufaellig die Zaehlung hinterfragt.
    """
    report.checks.append("Alle Zeitstempel in decisions/orders/runs sind parsebar")
    for table, col in (("decisions", "ts"), ("orders", "ts"), ("runs", "started_at")):
        df = j.table(table)
        if df.empty or col not in df.columns:
            continue
        parsed = pd.to_datetime(df[col], format="mixed", utc=True, errors="coerce")
        bad = int(parsed.isna().sum())
        report.stats[f"{table}.{col} geprueft"] = len(df)
        if bad:
            report.add(
                "fehler", f"Zeitstempel {table}.{col}",
                f"{bad} von {len(df)} Zeilen nicht parsebar (NaT). Jede "
                "zeitbasierte Auswertung uebersieht diese Zeilen lautlos.",
            )


def check_order_ids(j: Journal, report: IntegrityReport) -> None:
    """Haben echte Orders eine ECHTE Broker-ID, keinen Platzhalter?

    Lehre: `close_position()` gab frueher nur einen Text zurueck, jeder
    Verkauf bekam eine selbst erfundene "local_..."-ID, die nie zu einer
    Alpaca-Order passt - `reconcile_fills()` konnte solche Verkaeufe
    NIE abgleichen.
    """
    report.checks.append("Echte Orders (dry_run=0) haben keine local_-Platzhalter-ID")
    o = j.table("orders", "dry_run = 0")
    if o.empty:
        return
    fake = o[o["order_id"].astype(str).str.startswith("local_")]
    report.stats["Echte Orders gesamt"] = len(o)
    if not fake.empty:
        report.add(
            "fehler", "Platzhalter-Order-ID bei echter Order",
            f"{len(fake)} von {len(o)} echten Orders haben eine lokal "
            f"erfundene ID statt der Broker-ID: "
            f"{', '.join(fake['symbol'].tolist()[:10])}. Diese koennen nie "
            "mit einem Fuellpreis abgeglichen werden.",
        )


def check_id_collisions(j: Journal, report: IntegrityReport) -> None:
    """Wurde eine order_id mehrfach vergeben (stiller Ueberschreib-Verlust)?

    Lehre: OrderResult.id war im Trockenlauf immer der feste String
    "dry-run". Da order_id PRIMARY KEY ist und mit INSERT OR REPLACE
    geschrieben wird, ueberschrieb jede weitere Dry-Run-Order lautlos die
    vorherige - ohne Fehlermeldung, ohne Absturz.
    """
    report.checks.append("Keine feste Platzhalter-ID, die sich selbst ueberschreiben wuerde")
    o = j.table("orders")
    if o.empty:
        return
    verdaechtig = {"dry-run", "not_sent", ""}
    treffer = o[o["order_id"].isin(verdaechtig)]
    if len(treffer) > 1:
        report.add(
            "fehler", "Feste Platzhalter-ID mehrfach verwendet",
            f"order_id-Wert(e) {sorted(set(treffer['order_id']))} kommen "
            f"{len(treffer)}x vor, obwohl PRIMARY KEY - JEDE weitere "
            "Verwendung ueberschreibt die vorherige. Nur der letzte "
            "Eintrag ist noch vorhanden.",
        )


def check_fill_completeness(j: Journal, report: IntegrityReport,
                            max_age_hours: float = 6.0) -> None:
    """Bleiben echte Orders zu lange ohne Fuellpreis?

    Lehre: Ein starres 48h-Abgleichfenster in reconcile_fills() verlor
    Orders, die laenger offen blieben, unwiderruflich - der Broker kannte
    sie noch, aber das Fenster erfasste sie nicht mehr. Hier wird deutlich
    enger geprueft (6h), um fruehzeitig zu warnen statt erst nach Tagen.
    """
    report.checks.append(f"Echte Orders bekommen binnen {max_age_hours:g}h einen Fuellpreis")
    o = j.table("orders", "dry_run = 0 AND fill_price IS NULL")
    if o.empty:
        return
    ts = pd.to_datetime(o["ts"], format="mixed", utc=True, errors="coerce")
    alter_h = (pd.Timestamp.now(tz="UTC") - ts).dt.total_seconds() / 3600
    alt = o[alter_h > max_age_hours]
    if not alt.empty:
        report.add(
            "fehler", "Order ohne Fuellpreis ueber dem Zeitlimit",
            f"{len(alt)} Order(s) aelter als {max_age_hours:g}h ohne "
            f"fill_price: {', '.join(alt['symbol'].tolist()[:10])}. "
            "reconcile_fills() ausfuehren oder Ursache pruefen.",
        )


def check_run_configs(j: Journal, report: IntegrityReport, letzte_n: int = 20) -> None:
    """Schreiben aktuelle Laeufe die vollstaendigen Handelsregeln mit?

    Ohne das kann `audit.py` spaetere Entscheidungen nicht gegen die
    damals geltenden Schwellen pruefen.
    """
    report.checks.append("Aktuelle Laeufe protokollieren min_score in ihrer Konfiguration")
    import json

    runs = j.table("runs", "script = 'live_trade'")
    if runs.empty:
        return
    runs["started_at"] = pd.to_datetime(runs["started_at"], format="mixed", utc=True)
    recent = runs.sort_values("started_at").tail(letzte_n)
    fehlend = 0
    for _, r in recent.iterrows():
        try:
            cfg = json.loads(r["config"] or "{}")
        except json.JSONDecodeError:
            cfg = {}
        if "min_score" not in cfg:
            fehlend += 1
    report.stats[f"Letzte {letzte_n} Laeufe geprueft"] = len(recent)
    if fehlend:
        report.add(
            "auffaellig", "Config-Protokollierung",
            f"{fehlend} von {len(recent)} juengsten Laeufen ohne vollstaendige "
            "Regel-Konfiguration - vermutlich vor dem entsprechenden Fix "
            "entstanden, kein aktuelles Problem.",
        )


def check_state_vs_broker(report: IntegrityReport) -> None:
    """Deckt sich der gespeicherte Zustand mit dem echten Depot?"""
    report.checks.append("Bot-Zustand deckt sich mit dem Broker-Depot")
    from . import account
    from .state import Store

    try:
        broker = set(account.positions().index)
    except Exception as e:  # noqa: BLE001
        report.add("auffaellig", "Depotabgleich", f"Kontoabruf fehlgeschlagen: {e}")
        return
    stored = set(Store().load_positions())
    if broker - stored:
        report.add(
            "fehler", "Position ohne Zustand",
            f"{', '.join(sorted(broker - stored))} - Stop/Ziel unbekannt, "
            "kann nicht regelkonform geschlossen werden.",
        )
    if stored - broker:
        report.add(
            "auffaellig", "Verwaister Zustand",
            f"{', '.join(sorted(stored - broker))} - Zustand ohne Position.",
        )


def check_extreme_slippage(j: Journal, report: IntegrityReport,
                           schwelle_bps: float = 500.0) -> None:
    """Listet ungewoehnlich grosse Slippage-Werte - nicht automatisch falsch.

    Lehre aus SAIA (-317 bps): manche Ausreisser sind echte Marktbewegung
    waehrend der Ausfuehrung, kein Rechenfehler. Deshalb 'auffaellig',
    nicht 'fehler' - aber sichtbar machen, damit es nicht uebersehen wird.
    """
    report.checks.append(f"Auffaellige Slippage (>|{schwelle_bps:g}| bps) wird gelistet")
    o = j.table("orders", "dry_run = 0 AND slippage_bps IS NOT NULL")
    if o.empty:
        return

    # Nur Zeilen pruefen, deren Referenzpreis ueberhaupt beurteilbar ist.
    # Drei Gruppen sind es NICHT:
    #
    #   * Status-Text "X geschlossen" -> vor dem close_position()-Fix
    #     (9c26b6a), Referenzpreis nachweislich unbrauchbar.
    #   * referenz_quelle IS NULL     -> vor Einfuehrung der Quote-Pruefung
    #     (04.08.2026); ob die Quote taugte, ist nachtraeglich nicht mehr
    #     feststellbar. Genau hier liegen die bekannten Faelle SIMO/KGS.
    #   * referenz_quelle = 'fallback' -> gar keine Quote vorhanden, der
    #     Wert misst Kursdrift statt Slippage.
    #
    # Ohne diese Trennung meldet der Health-Check bei JEDEM Lauf dieselben
    # historischen Zeilen. Eine Warnung, die dauerhaft steht, wird
    # ueberlesen - und zwar genau dann, wenn sie einmal etwas Neues meldet.
    # Sie verschwinden deshalb aus der MELDUNG, werden aber gezaehlt: Was
    # nicht beurteilbar ist, darf trotzdem nicht unsichtbar werden.
    quelle = o.get("referenz_quelle", pd.Series(index=o.index, dtype=object))
    legacy = o["status"].astype(str).str.endswith(" geschlossen")
    unpruefbar = legacy | quelle.isna() | (quelle == "fallback")
    aktuell = o[~unpruefbar]

    extreme = aktuell[aktuell["slippage_bps"].abs() > schwelle_bps]
    if not extreme.empty:
        beispiele = ", ".join(
            f"{r['symbol']}({r['slippage_bps']:+.0f}bps)"
            for _, r in extreme.head(5).iterrows()
        )
        report.add(
            "auffaellig", "Grosse Slippage-Werte",
            f"{len(extreme)} von {len(aktuell)} pruefbaren Order(s) ueber "
            f"{schwelle_bps:g} bps: {beispiele}. Pruefen ob reale "
            "Marktbewegung (siehe costs.reconcile) oder Referenzpreis-Fehler.",
        )
    if unpruefbar.any():
        report.checks.append(
            f"{int(unpruefbar.sum())} Order(s) ohne pruefbaren Referenzpreis "
            "von der Slippage-Pruefung ausgenommen (vor close_position()-Fix, "
            "vor der Quote-Pruefung, oder ohne echte Quote)"
        )


def check_lifecycle_coverage(report: IntegrityReport) -> None:
    """Hat jeder Verkauf einen Lebenslauf-Eintrag (fuer den Lernbericht)?"""
    report.checks.append("Jeder Ausstieg hat einen Lebenslauf-Eintrag")
    from .lifecycle import Lifecycle
    from .state import Store

    exits = Store().recent_exits(days=90)
    trades = Lifecycle().table()
    report.stats["Ausstiege gesamt"] = len(exits)
    report.stats["Lebenslauf-Eintraege"] = len(trades)
    if len(exits) > len(trades) + 1:  # etwas Toleranz fuer Timing
        report.add(
            "auffaellig", "Lebenslauf unvollstaendig",
            f"{len(exits)} Ausstiege protokolliert, aber nur {len(trades)} "
            "Lebenslauf-Eintraege - manche Verkaeufe liefern keine Daten "
            "fuer den Lernbericht.",
        )


# --------------------------------------------------------------------------
# Stumme Felder
# --------------------------------------------------------------------------
# Ein Feld, das angelegt wird und dann immer leer oder immer gleich bleibt,
# meldet sich nie von selbst. Es sieht in jeder Tabelle plausibel aus - und
# verfaelscht jede Auswertung, die nach ihm gruppiert.
#
# Die Chronik dieses Projekts besteht ueberwiegend aus genau diesem Fehler:
#
#     bars_held        in JEDEM Trade 0            (15.08.)
#     after_10d        nie gefuellt                (15.08.)
#     code_version     zwei Monate 'unbekannt'     (15.08., 66 % der Daten)
#     regime_breite    live nie gefuellt           (22.08., dieser Check)
#     Bar-Cache        nie getroffen               (21.08.)
#
# Keiner davon hat einen Fehler ausgeloest. Alle wurden nur gefunden, weil
# jemand zufaellig gezielt nachsah. Dieser Check macht daraus eine Routine.

SCHWEIGE_TOLERANZ = 0.80
"""Ab welchem Anteil eines einzigen Wertes ein Feld als 'stumm' gilt."""


def _pflichtfelder_aus_gruenden() -> dict[str, str]:
    """Felder in `decisions.reasons`, die eine Auswertungsachse tragen.

    Der Wert ist die Begruendung - sie steht im Befundtext, damit beim
    Lesen sofort klar ist, WAS ohne dieses Feld nicht mehr beantwortbar
    ist. Ein Befund ohne diese Angabe wuerde als Formalie abgetan.
    """
    return {
        "regime_markt": "in welcher Marktlage die Strategie traegt",
        "regime_vola": "ob sie von der Marktunruhe abhaengt",
        "sektor": "ob 15 Positionen in Wahrheit eine Wette sind",
        "liq_dezil": "ob der Vorsprung nur bei illiquiden Werten entsteht",
    }


def check_stumme_felder(j: Journal, report: IntegrityReport,
                        fenster: int = 400, juengste: int = 20) -> None:
    """Felder, die gefuellt sein sollten - und die aufgehoert haben, es zu sein.

    **Warum nicht schlicht die Fuellquote?** Ein erster Entwurf am
    22.08.2026 meldete genau das - und schlug sofort bei vier Feldern an,
    die zwei Tage zuvor eingefuehrt worden waren. Ueber die Historie
    gerechnet waren sie zwangslaeufig zu 93 % leer. Der Check haette
    ~30 Tage lang gelb geleuchtet, ohne dass irgendetwas kaputt war.
    Eine Warnung, die immer leuchtet, wird weggeklickt - und dann faellt
    auch die echte nicht mehr auf.

    Geprueft wird deshalb die gefaehrliche Richtung: ein Feld, das
    frueher Werte hatte und in den JUENGSTEN Entscheidungen keine mehr.
    Das ist die Signatur jedes stummen Ausfalls dieses Projekts - der
    Code lief weiter, nur das Feld blieb leer.

    **`juengste` ist bewusst klein (20).** Ein grosses Fenster reicht ueber
    den Einfuehrungstag eines Feldes zurueck und meldet die davorliegenden
    Leerzeilen als Ausfall - der zweite Fehlalarm desselben Vormittags.
    Ein kleines Fenster stellt die richtige Frage: "sind die ALLERNEUESTEN
    Entscheidungen vollstaendig?" Faellt ein Feld aus, ist es das binnen
    eines Tages; wird eines eingefuehrt, ist das Fenster binnen eines Tages
    wieder sauber.
    """
    import json as _json

    report.checks.append("Auswertungsfelder hoeren nicht auf, sich zu fuellen")

    # NUR Live-Entscheidungen. Simulationslaeufe schreiben in dieselbe
    # Tabelle und fuehren die Kontextfelder nicht - ohne diesen Filter
    # meldete der Check am 22.08.2026 einen Ausfall, wo in Wahrheit
    # Backtest-Zeilen die Stichprobe fuellten (98,4 % der Tabelle).
    with sqlite3.connect(JOURNAL_DB) as c:
        d = pd.read_sql(
            "SELECT d.action, d.reasons FROM decisions d"
            " JOIN runs r ON d.run_id = r.run_id"
            " WHERE r.script = 'live_trade'"
            " ORDER BY d.ts DESC LIMIT ?",
            c, params=(fenster,))
    if len(d) < juengste:
        return

    # Je AKTIONSART getrennt. Am 22.08.2026 verglich ein erster Entwurf
    # alle Entscheidungen in einem Topf und meldete "Feld hoert auf" -
    # in Wahrheit haengt der Kontext nur an `buy`, und `topup` war schlicht
    # die Mehrheit der Zeilen. Ein Topf aus ungleichen Dingen erzeugt
    # Fehlalarme UND verdeckt echte Ausfaelle: waere `buy` tatsaechlich
    # ausgefallen, haetten die vielen `topup`-Zeilen es verwaessert.
    d = d[d["action"].notna()]

    def hol(roh, schluessel):
        try:
            return _json.loads(roh).get(schluessel)
        except Exception:  # noqa: BLE001 - defektes JSON ist hier kein Absturz
            return None

    for feld, wofuer in _pflichtfelder_aus_gruenden().items():
        d = d.assign(_w=d["reasons"].map(lambda r, f=feld: hol(r, f)))
        traeger = [a for a, g in d.groupby("action") if g["_w"].notna().any()]
        if not traeger:
            report.stats[f"Feld {feld}"] = "nie erhoben"
            continue

        # Nur Aktionsarten pruefen, die das Feld ueberhaupt je getragen
        # haben. Dass `topup` keinen Sektor mitschreibt, ist eine eigene
        # Luecke (unten als `check_kontext_abdeckung`) - aber kein Ausfall
        # eines Feldes, das dort nie erhoben wurde.
        for aktion in traeger:
            g = d[d["action"] == aktion]
            n = min(juengste, len(g))
            if n < juengste:
                continue  # zu wenig Verlauf fuer eine Aussage
            frisch = g["_w"].head(n).dropna()
            quote = len(frisch) / n
            report.stats[f"Feld {feld} ({aktion})"] = f"{quote:.0%} der juengsten {n}"

            if quote < 0.9:
                report.add(
                    "fehler", f"Feld '{feld}' wird bei '{aktion}' nicht mehr gefuellt",
                    f"Nur {len(frisch)} von {n} der ALLERJUENGSTEN "
                    f"'{aktion}'-Entscheidungen tragen einen Wert, obwohl das "
                    f"Feld dort frueher gefuellt wurde. Ein Feld, das aufhoert "
                    f"- genau so verliefen `bars_held`, `after_10d` und "
                    f"`code_version`. Ohne dieses Feld ist nicht mehr "
                    f"beantwortbar, {wofuer}.",
                )
                continue
            if frisch.nunique() > 1 or aktion != traeger[0]:
                continue
            # Kein Fehler: ein Bullenmarkt liefert nur 'bullisch'. Aber es
            # heisst, dass diese Achse derzeit NICHTS trennt - und das muss
            # dastehen, bevor jemand danach gruppiert und sich wundert.
            report.add(
                "auffaellig", f"Feld '{feld}' ist derzeit konstant",
                f"Alle {len(frisch)} juengsten Werte sind "
                f"'{frisch.iloc[0]}'. Das kann richtig sein (eine "
                f"Marktphase liefert nur einen Wert), taugt aber nicht als "
                f"Auswertungsachse - ein Vergleich darueber haette nur "
                f"eine Gruppe.",
            )


# Spalten der `orders`-Tabelle, die eine Auswertungsachse tragen, und was
# ohne sie nicht mehr beantwortbar ist. Dieselbe Form wie
# `_pflichtfelder_aus_gruenden` - der Befundtext muss sagen, WAS fehlt,
# sonst wird er als Formalie abgetan.
_ORDERSPALTEN = {
    "status": "ob eine Order ueberhaupt ausgefuehrt wurde",
    "referenz_quelle": "ob eine Zeile echte Ausfuehrungsqualitaet misst "
                       "oder nur Kursdrift seit der Entscheidung",
    "fill_price": "zu welchem Kurs tatsaechlich gehandelt wurde",
    "expected_price": "wogegen die Ausfuehrung gemessen wird",
}


def check_stumme_orderspalten(j: Journal, report: IntegrityReport,
                              juengste: int = 30) -> None:
    """Traegt jede Orderspalte noch Information - oder nur noch einen Wert?

    **Warum es diesen Check zusaetzlich gibt (23.08.2026, §G19 Fund 5).**
    `check_stumme_felder` bewacht `decisions.reasons`,
    `check_lifecycle_felder` den Lebenslauf. Fuer die `orders`-Tabelle
    gab es nichts - und genau dort standen zwei stumme Spalten:

        raw      183 von 183 echten Zeilen: der String 'null'
        status   178 von 183: 'pending_new'

    Beide sahen zu 100 % gefuellt aus. `raw` enthielt die JSON-Schreibweise
    von "nichts", `status` den Wert bei ABGABE - nie den endgueltigen.
    Am Journal war damit nicht ablesbar, ob eine Order ausgefuehrt wurde,
    obwohl die Spalte genau dafuer da ist.

    **Der Unterschied zu `check_stumme_felder`.** Dort ist die gefaehrliche
    Richtung "war gefuellt, ist es nicht mehr". Hier ist sie "sieht gefuellt
    aus, traegt aber nur einen einzigen Wert" - eine Spalte, die nie
    variiert, ist keine Messung, sondern eine Konstante mit Spaltenkopf.

    Geprueft wird auf den JUENGSTEN Orders, aus demselben Grund wie dort:
    Eine Spalte, die spaeter eingefuehrt wurde, ist ueber die ganze
    Historie zwangslaeufig ueberwiegend leer, und ein Check, der deshalb
    dauerhaft leuchtet, wird weggeklickt.
    """
    report.checks.append("Orderspalten tragen mehr als einen Wert")

    o = j.table("orders", "dry_run = 0")
    if o.empty:
        return
    o = o.sort_values("ts").tail(juengste)
    if len(o) < juengste:
        return
    report.stats["Orders geprueft"] = len(o)

    for spalte, wofuer in _ORDERSPALTEN.items():
        if spalte not in o.columns:
            continue
        werte = o[spalte].dropna()
        quote = len(werte) / len(o)

        if quote < 0.5:
            report.add(
                "fehler", f"Orderspalte '{spalte}' ist ueberwiegend leer",
                f"Nur {len(werte)} von {len(o)} der juengsten Orders tragen "
                f"einen Wert. Ohne die Spalte ist nicht mehr beantwortbar, "
                f"{wofuer}.",
            )
            continue

        if werte.nunique() <= 1 and len(werte) >= juengste * 0.5:
            einziger = werte.iloc[0] if len(werte) else "leer"
            report.add(
                "auffaellig", f"Orderspalte '{spalte}' traegt nur einen Wert",
                f"Alle {len(werte)} juengsten Orders zeigen '{einziger}'. "
                f"Eine Spalte, die nie variiert, sieht gefuellt aus und ist "
                f"keine Messung. Genau so verlief `orders.status` bis zum "
                f"23.08.2026 ('pending_new' in 178 von 183 Zeilen - der "
                f"Status bei Abgabe, nie der endgueltige). Ohne echte "
                f"Variation ist nicht beantwortbar, {wofuer}.",
            )

    # `raw` getrennt, weil hier der Text 'null' und SQL-NULL dasselbe
    # bedeuten - eine reine Fuellquote wuerde 100 % melden. Seit dem
    # 23.08.2026 schreibt `journal.RunLogger.order` SQL-NULL statt
    # 'null'; Altzeilen tragen weiter den Text.
    if "raw" in o.columns:
        echt = o["raw"].dropna()
        echt = echt[echt.astype(str).str.strip() != "null"]
        report.stats["Orders mit Broker-Rohzeile"] = f"{len(echt)}/{len(o)}"
        if echt.empty:
            report.add(
                "auffaellig", "Orderspalte 'raw' enthaelt keine Broker-Zeile",
                f"Keine der juengsten {len(o)} Orders traegt die Aufzeichnung "
                f"der Gegenseite. Sie entsteht im Broker-Abgleich "
                f"(`live.reconcile_fills`) - bleibt sie leer, hat der "
                f"Abgleich seit der letzten Order nicht gegriffen.",
            )


def check_lifecycle_felder(report: IntegrityReport) -> None:
    """`bars_held`, `mae/mfe` und die Nachlauf-Fenster - stumm oder gefuellt?

    Drei der vier hier geprueften Felder waren im August 2026 nachweislich
    kaputt. Sie sind die Grundlage des Lernberichts und der Frage, ob der
    Zeitausstieg zu frueh greift.
    """
    from .lifecycle import Lifecycle

    report.checks.append("Lebenslauf-Felder sind gefuellt und variieren")
    t = Lifecycle().table()
    if t.empty:
        return

    # Nur abgeschlossene Trades - ein offener hat noch keinen Nachlauf.
    fertig = t[t["exit_date"].notna()]
    if fertig.empty:
        return

    if "bars_held" in fertig.columns:
        bh = pd.to_numeric(fertig["bars_held"], errors="coerce").dropna()
        report.stats["bars_held Median"] = (float(bh.median())
                                            if len(bh) else "leer")
        if len(bh) and (bh == 0).all():
            report.add(
                "fehler", "bars_held ist in jedem Trade 0",
                f"Alle {len(bh)} abgeschlossenen Trades melden Haltedauer 0. "
                "Genau dieser Fehler bestand bis zum 15.08.2026 (§G) - er "
                "macht jede Aussage ueber Haltedauer und Zeitausstieg wertlos.",
            )

    # after_1d/5d/10d: das Fenster braucht Zeit. Nur Trades bewerten, die
    # alt genug sind - sonst meldet der Check die normale Wartezeit als Fehler.
    exit_dt = pd.to_datetime(fertig["exit_date"], format="mixed", utc=True,
                             errors="coerce")
    jetzt = pd.Timestamp.now(tz="UTC")
    for spalte, tage in (("after_1d", 3), ("after_5d", 9), ("after_10d", 16)):
        if spalte not in fertig.columns:
            continue
        reif = fertig[exit_dt < jetzt - pd.Timedelta(days=tage)]
        if len(reif) < 5:
            continue
        gefuellt = pd.to_numeric(reif[spalte], errors="coerce").notna().sum()
        anteil = gefuellt / len(reif)
        report.stats[f"{spalte} gefuellt"] = f"{anteil:.0%} ({len(reif)} reif)"
        if anteil < 0.5:
            report.add(
                "auffaellig", f"'{spalte}' bleibt leer",
                f"Nur {gefuellt} von {len(reif)} faelligen Trades haben einen "
                f"Wert. `after_10d` war aus genau diesem Grund bis zum "
                f"15.08.2026 nie gefuellt - `pending_analysis` fragte nur "
                f"nach `after_5d IS NULL`.",
            )


def check_bars_held_stimmig(report: IntegrityReport) -> None:
    """Widerspricht `bars_held` den Ein-/Ausstiegsdaten?

    Der schaerfere Nachfolger der reinen "alles null"-Pruefung. Ein Feld
    muss nicht komplett kaputt sein, um zu luegen - es reicht, wenn ein
    Teil der Zeilen aus der Zeit vor einer Reparatur stammt.

    Gemessen am 22.08.2026: 36 von 56 abgeschlossenen Trades trugen
    `bars_held = 0`, obwohl ihre Datumsangaben 2 bis 5 Handelstage
    hergeben - allesamt Ausstiege VOR dem 17.08., also Rueckstand des am
    15.08. behobenen Fehlers (§G). Die 20 Trades danach stimmen exakt
    mit dem Datum ueberein (groesste Abweichung: 0 Tage).

    Die Null ist dabei gefaehrlicher als ein fehlender Wert: Sie sieht
    wie eine Messung aus und geht in jeden Mittelwert ein. Der Median
    der Haltedauer lag dadurch bei 0 statt bei 5.
    """
    import numpy as np

    from .lifecycle import Lifecycle

    report.checks.append("bars_held deckt sich mit den Ein-/Ausstiegsdaten")
    t = Lifecycle().table()
    if t.empty or "bars_held" not in t.columns:
        return
    f = t[t["exit_date"].notna()].copy()
    if f.empty:
        return

    f["_bh"] = pd.to_numeric(f["bars_held"], errors="coerce")
    ein = pd.to_datetime(f["entry_date"], format="mixed", utc=True, errors="coerce")
    aus = pd.to_datetime(f["exit_date"], format="mixed", utc=True, errors="coerce")
    gueltig = ein.notna() & aus.notna() & f["_bh"].notna()
    if not gueltig.any():
        return

    f = f[gueltig]
    erwartet = pd.Series(
        [np.busday_count(a.date(), b.date())
         for a, b in zip(ein[gueltig], aus[gueltig])], index=f.index)
    # Ein Tag Toleranz: Handelsfeiertage kennt `busday_count` nicht.
    abweichung = (f["_bh"] - erwartet).abs()
    falsch = f[abweichung > 1]

    report.stats["bars_held stimmig"] = f"{len(f) - len(falsch)}/{len(f)}"
    if len(falsch):
        anteil = len(falsch) / len(f)
        report.add(
            "fehler", "bars_held widerspricht den Datumsangaben",
            f"{len(falsch)} von {len(f)} abgeschlossenen Trades "
            f"({anteil:.0%}). Beispiel: {falsch.iloc[0]['symbol']} meldet "
            f"{falsch.iloc[0]['_bh']:.0f} Tage, die Daten ergeben "
            f"{erwartet.loc[falsch.index[0]]:.0f}. Eine falsche Zahl ist "
            "hier schlimmer als eine fehlende - sie geht in jeden "
            "Mittelwert ein, ohne aufzufallen (§G, 15.08.2026).",
        )


def check_codeversion_zuordnung(j: Journal, report: IntegrityReport,
                                letzte_n: int = 200) -> None:
    """Laesst sich noch sagen, welcher Codestand die Daten erzeugt hat?

    `shadow.code_version()` lieferte nach dem Umzug der Datenbanken zwei
    Monate lang stumm 'unbekannt' - fuer 66 % aller Vorhersagen (§G5).
    Ein Versionsvergleich ist auf solchen Daten unmoeglich.
    """
    report.checks.append("Laeufe tragen eine erkennbare Codeversion")
    with sqlite3.connect(JOURNAL_DB) as c:
        try:
            r = pd.read_sql(
                "SELECT code_version FROM runs ORDER BY started_at DESC LIMIT ?",
                c, params=(letzte_n,))
        except Exception:  # noqa: BLE001 - alte Journale ohne die Spalte
            return
    if r.empty:
        return

    unbekannt = r["code_version"].isna() | r["code_version"].isin(
        ["", "unbekannt", "unknown"])
    anteil = float(unbekannt.mean())
    report.stats["Laeufe ohne Codeversion"] = f"{anteil:.0%}"
    if anteil > 0.2:
        report.add(
            "auffaellig", "Codeversion fehlt haeufig",
            f"{anteil:.0%} der letzten {len(r)} Laeufe ohne Versionszuordnung. "
            "Fuer diese Daten laesst sich nicht mehr sagen, welcher Codestand "
            "sie erzeugt hat (§G5).",
        )


def run_all() -> IntegrityReport:
    """Fuehrt alle Datenintegritaets-Pruefungen aus."""
    report = IntegrityReport()
    j = Journal()

    check_timestamps(j, report)
    check_order_ids(j, report)
    check_id_collisions(j, report)
    check_fill_completeness(j, report)
    check_run_configs(j, report)
    check_state_vs_broker(report)
    check_extreme_slippage(j, report)
    check_lifecycle_coverage(report)
    check_stumme_felder(j, report)
    check_stumme_orderspalten(j, report)
    check_lifecycle_felder(report)
    check_bars_held_stimmig(report)
    check_codeversion_zuordnung(j, report)

    # journal.py's eigene Vollstaendigkeitspruefung mit einbeziehen
    report.checks.append("Journal-interne Konsistenz (journal.integrity_check)")
    for p in j.integrity_check():
        report.add("auffaellig", "Journal-Konsistenz", p)

    return report
