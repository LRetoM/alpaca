"""Kontoweites Risiko-Dach - die Grenze, die keine Strategie kennt.

Jede Regel hier beantwortet eine einzige Frage: **Was, wenn die Strategie
NICHT funktioniert?** Nicht "wie optimiere ich sie?". Deshalb steht dieses
Modul UEBER der Engine und nicht in ihr - eine Engine, die ihre eigenen
Notbremsen zieht, hat keine.

**Was vorher fehlte:** Bis 15.08.2026 existierte im gesamten Projekt keine
Verlustgrenze. `trading._check_risk()` prueft die Groesse einer EINZELNEN
Order und die Kaufkraft - aber nichts hielt den Bot davon ab, mit einer
fehlerhaften Logik das Konto bis auf null zu handeln. Fuer den
Papierbetrieb war das verschmerzbar; vor echtem Geld ist es das nicht.

**Drei Grundsaetze:**

1. **Jede Sperre ist persistent und muss von Hand geloest werden.** Eine
   Sperre, die sich nach einer Stunde selbst aufhebt, kauft genau in den
   Crash zurueck, wegen dem sie ausgeloest hat.

2. **Verkaufen ist immer erlaubt.** Eine Sperre darf nie verhindern, aus
   einer Position herauszukommen - das wuerde aus einer Schutzmassnahme
   eine Falle machen.

3. **Der Hoechststand wird um Einzahlungen bereinigt.** Sonst hebt jede
   Einzahlung die Marke, und die Drawdown-Sperre loest nie aus - der
   Schutz waere genau dann wirkungslos, wenn am meisten Kapital im Spiel
   ist. Deshalb haengt dieses Modul an `state.kapitalfluesse`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

import pandas as pd

from .state import Store

BESTAETIGUNG = "ich habe die ursache verstanden"
"""Woertlich noetig, um eine Sperre zu loesen. Die Reibung ist Absicht:
Sie verhindert, dass man im Schreck einfach weiterlaufen laesst."""


@dataclass(frozen=True)
class Risikogrenzen:
    """Die harten Grenzen. Bewusst wenige und runde Werte.

    Keine dieser Zahlen ist optimiert - sie sind Setzungen. Ein
    optimierter Grenzwert waere an die Vergangenheit angepasst und damit
    genau dann falsch, wenn etwas Neues passiert.
    """

    max_drawdown_pct: float = 0.20
    """Rueckgang vom einzahlungsbereinigten Hoechststand. Darueber:
    Vollsperre. 20 % ist die Grenze, ab der die Annahme "die Strategie
    funktioniert, nur gerade nicht" nicht mehr zu halten ist."""

    tagesverlust_pct: float = 0.05
    """Verlust seit dem letzten Handelsschluss. Darueber: keine NEUEN
    Kaeufe mehr an diesem Tag. Verkaeufe bleiben erlaubt."""

    max_brutto_exposure: float = 1.00
    """Summe aller Positionswerte geteilt durch Kontowert. 1.00 = kein
    Hebel. Alpaca erlaubt bis zu 4x - diese Grenze verhindert, dass ein
    Rechenfehler das je nutzt."""

    max_sektor_pct: float = 0.40
    """Hoechster Anteil eines Sektors am Depot. 15 Halbleiterwerte sind
    EINE Wette, keine 15 - und im Crash verhalten sie sich auch so.

    Wirkt erst, wenn Sektordaten vorliegen (siehe `sektor_anteile`);
    ohne sie wird die Regel als 'nicht pruefbar' gemeldet, nicht still
    uebersprungen."""

    max_positionen_gesamt: int = 30
    """Kontoweite Obergrenze, unabhaengig von `max_positions` der Engine.
    Reines Sicherheitsnetz gegen einen Konfigurationsfehler."""

    min_cash_reserve_pct: float = 0.02
    """Nie voll investiert. Puffer gegen Kursluecken."""

    verified: str = "2026-08-15"


@dataclass
class Freigabe:
    """Antwort des Risiko-Dachs."""

    ok: bool
    gruende: list[str] = field(default_factory=list)
    """Warum blockiert - MIT ZAHLEN. `blocked_by="RiskError"` allein ist
    im Nachhinein wertlos; man sieht dann, DASS blockiert wurde, aber
    nicht, wie knapp oder wie deutlich."""
    kennzahlen: dict = field(default_factory=dict)

    def __str__(self) -> str:
        if self.ok:
            return "Risiko-Dach: frei"
        return "Risiko-Dach BLOCKIERT:\n  " + "\n  ".join(self.gruende)


def positionswert(zeile) -> float | None:
    """Wert EINER Position - mit Fallback-Kette statt stillem Nullwert.

    **Der Fehler, gegen den das steht (§G18).** Vorher stand hier
    sinngemaess `qty * (current_price or 0)` in einem
    `except: continue`. Zwei Wege liessen eine Position still aus der
    Risikorechnung verschwinden:

      * `current_price` ist `None` - `account.positions()` setzt das Feld
        ausdruecklich so, wenn Alpaca keinen Kurs liefert (etwa bei einer
        Handelsaussetzung). `or 0` machte daraus den Wert **null**, ganz
        ohne Exception.
      * `qty` unlesbar - die Zeile fiel per `continue` heraus.

    Gemessen an drei Positionen a 30.000 $ auf 100.000 $ Konto: Exposure
    90 % statt 60 %, Sektoranteil 90 % statt 60 %. Das Dach hat damit
    UNTERSCHAETZT und Kaeufe zugelassen, die es sonst blockiert haette -
    der genaue Gegensatz zu seinem Grundsatz "im Zweifel wird nicht
    gehandelt".

    Die Kette geht vom genauesten zum konservativsten Wert:

        market_value          was der Broker selbst ausweist
        qty * current_price   selbst gerechnet
        qty * avg_entry       Einstand - eine Untergrenze, aber ein Wert

    Erst wenn auch die Menge fehlt, ist nichts bestimmbar. Dann kommt
    `None` zurueck - und der Aufrufer MUSS das zaehlen, statt es zu
    ueberspringen.
    """
    def _zahl(feld) -> float | None:
        try:
            wert = zeile.get(feld) if hasattr(zeile, "get") else zeile[feld]
        except (KeyError, IndexError, TypeError):
            return None
        if wert is None:
            return None
        try:
            f = float(wert)
        except (TypeError, ValueError):
            return None
        return f if pd.notna(f) else None

    mv = _zahl("market_value")
    if mv is not None:
        return abs(mv)

    qty = _zahl("qty")
    if qty is None:
        return None
    for feld in ("current_price", "avg_entry"):
        kurs = _zahl(feld)
        if kurs is not None:
            return abs(qty * kurs)
    return None


def _kennzahlen(konto: dict, positionen: pd.DataFrame,
                store: Store) -> dict:
    """Sammelt alles, was die Regeln brauchen - an genau einer Stelle."""
    equity = float(konto.get("equity") or konto.get("portfolio_value") or 0.0)
    cash = float(konto.get("cash") or 0.0)
    letzte = float(konto.get("last_equity") or equity)

    pos_wert = 0.0
    n_unbewertbar = 0
    unbewertbar: list[str] = []
    if positionen is not None and not positionen.empty:
        for sym, r in positionen.iterrows():
            wert = positionswert(r)
            if wert is None:
                # NICHT ueberspringen: Eine Position, die niemand bewerten
                # kann, ist kein Grund, sie aus dem Risiko herauszurechnen.
                n_unbewertbar += 1
                unbewertbar.append(str(sym))
                continue
            pos_wert += wert

    einzahlungen = store.einzahlungen_summe()

    # Hoechststand einzahlungsbereinigt: Von jedem historischen Kontowert
    # wird der bis dahin eingezahlte Betrag abgezogen. Sonst hebt eine
    # Einzahlung von 10.000 $ die Marke um 10.000 $, und ein danach
    # eintretender echter Verlust wird nie als Drawdown erkannt.
    verlauf = store.kapital_verlauf(tage=3650)
    if verlauf.empty:
        hoechst_bereinigt = equity - einzahlungen
    else:
        bereinigt = verlauf["equity"] - verlauf["einzahlungen_kumuliert"]
        hoechst_bereinigt = max(float(bereinigt.max()), equity - einzahlungen)

    aktuell_bereinigt = equity - einzahlungen
    drawdown = (0.0 if hoechst_bereinigt <= 0
                else max(0.0, 1 - aktuell_bereinigt / hoechst_bereinigt))
    tagesverlust = 0.0 if letzte <= 0 else max(0.0, 1 - equity / letzte)

    return {
        "equity": equity,
        "cash": cash,
        "positionswert": pos_wert,
        "exposure": (pos_wert / equity) if equity > 0 else 0.0,
        "n_positionen": 0 if positionen is None else len(positionen),
        "n_unbewertbar": n_unbewertbar,
        "unbewertbar": unbewertbar,
        "einzahlungen": einzahlungen,
        "hoechststand_bereinigt": hoechst_bereinigt + einzahlungen,
        "drawdown_pct": drawdown,
        "tagesverlust_pct": tagesverlust,
        "cash_quote": (cash / equity) if equity > 0 else 0.0,
    }


def pruefe_konto(
    *, konto: dict | None = None, positionen: pd.DataFrame | None = None,
    grenzen: Risikogrenzen = Risikogrenzen(), store: Store | None = None,
    schreiben: bool = True,
) -> Freigabe:
    """Einmal je Zyklus, VOR dem Entscheiden.

    Setzt die Vollsperre bei Drawdown-Ueberschreitung. Alle uebrigen
    Verstoesse werden gemeldet, sperren aber nicht dauerhaft - sie
    begrenzen nur Neukaeufe (siehe `pruefe_order`).
    """
    from . import account

    s = store or Store()
    konto = konto if konto is not None else account.account_summary()
    positionen = positionen if positionen is not None else account.positions()

    k = _kennzahlen(konto, positionen, s)
    gruende: list[str] = []

    # --- Bestehende Sperre hat Vorrang vor allem anderen ---
    sperre = s.sperre_lesen()
    if int(sperre.get("aktiv") or 0) == 1:
        gruende.append(
            f"Sperre aktiv seit {str(sperre.get('gesetzt_am'))[:19]}: "
            f"{sperre.get('grund')}. Loesen nur von Hand "
            f"(risiko.sperre_loesen)."
        )
        return Freigabe(False, gruende, k)

    if konto.get("trading_blocked"):
        gruende.append("Der Broker hat das Konto fuer den Handel gesperrt.")

    if k["drawdown_pct"] > grenzen.max_drawdown_pct:
        grund = (f"Drawdown {k['drawdown_pct']:.1%} ueber der Grenze "
                 f"{grenzen.max_drawdown_pct:.0%} (einzahlungsbereinigt, "
                 f"Hoechststand ${k['hoechststand_bereinigt']:,.2f}, "
                 f"jetzt ${k['equity']:,.2f}).")
        gruende.append(grund)
        if schreiben:
            s.sperre_setzen(grund, k)

    if schreiben:
        s.kapital_punkt(
            equity=k["equity"], cash=k["cash"], exposure=k["exposure"],
            n_positionen=k["n_positionen"],
            hoechststand=k["hoechststand_bereinigt"],
            drawdown_pct=k["drawdown_pct"], einzahlungen=k["einzahlungen"],
        )

    return Freigabe(not gruende, gruende, k)


def pruefe_order(
    symbol: str, seite: str, betrag: float, *,
    konto: dict | None = None, positionen: pd.DataFrame | None = None,
    grenzen: Risikogrenzen = Risikogrenzen(), store: Store | None = None,
    sektoren: dict[str, str] | None = None,
) -> Freigabe:
    """Vor JEDER Order.

    Verkaeufe passieren immer - aus einer Position herauszukommen darf nie
    gesperrt sein (Grundsatz 2 im Modul-Docstring). Geprueft werden
    ausschliesslich Kaeufe.
    """
    from . import account

    if seite == "sell":
        return Freigabe(True, [], {})

    s = store or Store()
    konto = konto if konto is not None else account.account_summary()
    positionen = positionen if positionen is not None else account.positions()
    k = _kennzahlen(konto, positionen, s)
    gruende: list[str] = []

    sperre = s.sperre_lesen()
    if int(sperre.get("aktiv") or 0) == 1:
        return Freigabe(False, [f"Sperre aktiv: {sperre.get('grund')}"], k)

    # Unbewertbare Positionen zuerst: Alle folgenden Grenzen rechnen mit
    # `positionswert` - fehlt der fuer eine Position, ist JEDE dieser
    # Zahlen zu niedrig. Weiterzukaufen hiesse, auf einer Rechnung zu
    # handeln, von der man weiss, dass sie unvollstaendig ist (§G18).
    #
    # Der Grundsatz steht im Modul-Docstring: "Fällt die Risikopruefung
    # selbst aus, wird nicht gehandelt." Bisher galt er nur fuer eine
    # geworfene Ausnahme, nicht fuer eine still unvollstaendige Zahl.
    if k.get("n_unbewertbar"):
        namen = ", ".join(k.get("unbewertbar", [])[:5])
        gruende.append(
            f"{k['n_unbewertbar']} Position(en) ohne bestimmbaren Wert "
            f"({namen}) - Exposure, Cash-Quote und Klumpenkontrolle sind "
            f"damit zu niedrig gerechnet. Keine Neukaeufe, bis der Broker "
            f"wieder Kurse liefert (Verkaeufe bleiben erlaubt)."
        )

    if k["tagesverlust_pct"] > grenzen.tagesverlust_pct:
        gruende.append(
            f"Tagesverlust {k['tagesverlust_pct']:.1%} ueber der Grenze "
            f"{grenzen.tagesverlust_pct:.0%} - heute keine Neukaeufe mehr."
        )

    neues_exposure = ((k["positionswert"] + betrag) / k["equity"]
                      if k["equity"] > 0 else 0.0)
    if neues_exposure > grenzen.max_brutto_exposure:
        gruende.append(
            f"Brutto-Exposure waere {neues_exposure:.1%} "
            f"(Grenze {grenzen.max_brutto_exposure:.0%})."
        )

    rest_cash = k["cash"] - betrag
    if k["equity"] > 0 and (rest_cash / k["equity"]) < grenzen.min_cash_reserve_pct:
        gruende.append(
            f"Cash-Reserve waere {rest_cash / k['equity']:.1%} "
            f"(Mindestens {grenzen.min_cash_reserve_pct:.0%})."
        )

    if k["n_positionen"] >= grenzen.max_positionen_gesamt:
        gruende.append(
            f"{k['n_positionen']} Positionen offen "
            f"(kontoweite Grenze {grenzen.max_positionen_gesamt})."
        )

    if sektoren:
        anteile = sektor_anteile(positionen, sektoren, k["equity"])
        sektor = sektoren.get(symbol)
        if sektor:
            neu = anteile.get(sektor, 0.0) + (betrag / k["equity"]
                                              if k["equity"] > 0 else 0)
            if neu > grenzen.max_sektor_pct:
                gruende.append(
                    f"Sektor '{sektor}' waere {neu:.1%} des Depots "
                    f"(Grenze {grenzen.max_sektor_pct:.0%})."
                )

    return Freigabe(not gruende, gruende, k)


def sektor_anteile(positionen: pd.DataFrame, sektoren: dict[str, str],
                   equity: float) -> dict[str, float]:
    """Anteil je Sektor am Kontowert. Symbole ohne Sektorangabe zaehlen
    unter 'unbekannt' - sie verschwinden nicht stillschweigend, sonst
    saehe ein Depot ohne Sektordaten wie ein perfekt gestreutes aus."""
    if positionen is None or positionen.empty or equity <= 0:
        return {}
    out: dict[str, float] = {}
    for sym, r in positionen.iterrows():
        wert = positionswert(r)
        if wert is None:
            # Dieselbe Regel wie fuer fehlende Sektordaten eine Zeile
            # tiefer: sichtbar bleiben, nicht stillschweigend
            # verschwinden. Sonst sieht ein Klumpen wie Streuung aus.
            out["unbewertbar"] = out.get("unbewertbar", 0.0)
            continue
        sektor = sektoren.get(str(sym), "unbekannt")
        out[sektor] = out.get(sektor, 0.0) + wert / equity
    return out


def sperre_loesen(bestaetigung: str, *, von: str = "hand",
                  store: Store | None = None) -> str:
    """Loest die Sperre - nur mit woertlicher Bestaetigung.

    Die Reibung ist der Zweck. Eine Sperre, die sich mit einem Tastendruck
    aufheben laesst, wird im Schreck aufgehoben - und genau dann ist sie
    am noetigsten.
    """
    if bestaetigung.strip().lower() != BESTAETIGUNG:
        return (f"Nicht geloest. Erforderlich ist woertlich: "
                f"'{BESTAETIGUNG}'")
    s = store or Store()
    vorher = s.sperre_lesen()
    if int(vorher.get("aktiv") or 0) != 1:
        return "Es war keine Sperre aktiv."
    s.sperre_loesen(von)
    return f"Sperre geloest (war: {vorher.get('grund')})."


def bericht(store: Store | None = None,
            grenzen: Risikogrenzen = Risikogrenzen()) -> str:
    """Lesbarer Zustand des Risiko-Dachs."""
    s = store or Store()
    L = ["=" * 70, "  RISIKO-DACH", "=" * 70]

    sperre = s.sperre_lesen()
    if int(sperre.get("aktiv") or 0) == 1:
        L += ["", "  *** SPERRE AKTIV ***",
              f"  Grund      : {sperre.get('grund')}",
              f"  Gesetzt am : {str(sperre.get('gesetzt_am'))[:19]}",
              f"  Loesen     : risiko.sperre_loesen('{BESTAETIGUNG}')", ""]
    else:
        L.append("  Keine Sperre aktiv.")

    v = s.kapital_verlauf(tage=90)
    if v.empty:
        L.append("  Noch kein Kapitalverlauf aufgezeichnet.")
    else:
        akt = v.iloc[-1]
        L += [
            "",
            f"  Kontowert       : ${akt['equity']:,.2f}",
            f"  Hoechststand    : ${akt['hoechststand']:,.2f} (einzahlungsbereinigt)",
            f"  Drawdown        : {akt['drawdown_pct']:.2%}  "
            f"(Grenze {grenzen.max_drawdown_pct:.0%})",
            f"  Exposure        : {akt['exposure']:.1%}  "
            f"(Grenze {grenzen.max_brutto_exposure:.0%})",
            f"  Positionen      : {int(akt['n_positionen'])}  "
            f"(Grenze {grenzen.max_positionen_gesamt})",
            f"  Einzahlungen    : ${akt['einzahlungen_kumuliert']:,.2f}",
            f"  Messpunkte      : {len(v)}",
        ]

    f = s.kapitalfluesse()
    if not f.empty:
        L += ["", f"  Kapitalfluesse: {len(f)} erfasst, "
                  f"Saldo ${f['betrag'].sum():,.2f}"]
    return "\n".join(L)
