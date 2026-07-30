"""Die Entscheidungslogik - EIN Pfad fuer Historie und Live-Betrieb.

Das ist der wichtigste architektonische Punkt des ganzen Projekts.

Der uebliche Fehler beim Bot-Bau: Man schreibt einen Backtest, der mit
fertigen Kursreihen vektorisiert rechnet, und danach einen Live-Bot, der
Tag fuer Tag Entscheidungen trifft. Beide enthalten die "gleiche"
Strategie - aber eben zweimal geschrieben. Sie weichen voneinander ab,
und man validiert etwas anderes, als man spaeter handelt.

Hier gibt es nur `Engine.decide()`. Die Funktion bekommt eine
Momentaufnahme dessen, was zu einem Zeitpunkt bekannt war, und gibt
Entscheidungen zurueck. Wer diese Momentaufnahme baut, ist ihr egal:

    Historie:  simulate.py schneidet die Vergangenheit bei T ab
    Live:      der Paper-Trader holt den aktuellen Stand von Alpaca

Damit gilt: Was in der Simulation getestet wurde, ist buchstaeblich
derselbe Code, der spaeter handelt. Ein Unterschied zwischen Test und
Realitaet kann nur noch aus Ausfuehrung und Kosten stammen - und genau
die misst `journal.slippage_report()`.

**Strukturelle Absicherung gegen Lookahead:** `MarketSnapshot` enthaelt
ausschliesslich Daten bis `as_of`. Die Engine hat keinen Zugriff auf
irgendetwas anderes - kein Dateisystem, keine API, keine globalen
Zustaende. Sie KANN nicht in die Zukunft sehen, selbst wenn man es
versuchen wollte.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .signals import (
    ReversalWeights,
    SignalWeights,
    build_reversal_frame,
    build_signal_frame,
    explain,
    explain_reversal,
)


@dataclass
class Position:
    symbol: str
    qty: float
    entry_price: float
    entry_date: pd.Timestamp
    stop_price: float
    target_price: float
    bars_held: int = 0
    high_water: float = 0.0
    """Hoechster Kurs seit Einstieg - fuer den nachziehenden Stop."""

    def unrealized_pct(self, price: float) -> float:
        return price / self.entry_price - 1


@dataclass
class MarketSnapshot:
    """Alles, was zum Zeitpunkt `as_of` bekannt war - und nichts darueber hinaus.

    Der Vertrag: Jede Zeitreihe hier endet bei `as_of`. Wer diese Klasse
    baut, ist dafuer verantwortlich - `simulate.py` schneidet ab,
    der Live-Betrieb bekommt ohnehin nur Vergangenheit.
    """

    as_of: pd.Timestamp
    bars: dict[str, pd.DataFrame]
    """Symbol -> OHLCV bis einschliesslich as_of."""
    insider: dict[str, pd.DataFrame] = field(default_factory=dict)
    market: pd.Series | None = None
    """Schlusskurse eines Marktindex (SPY) bis as_of - fuer den Regime-Filter."""
    signals: dict[str, pd.DataFrame] = field(default_factory=dict)
    """Optional vorberechnete Signale, ebenfalls bis as_of geschnitten.

    Erlaubt, weil `signals.build_signal_frame` nachweislich kausal ist
    (geprueft mit `pit.audit_feature_function`): Fuer eine kausale
    Funktion gilt build(voll).loc[:T] == build(bis_T). Einmal rechnen und
    schneiden ist also identisch zur schrittweisen Berechnung - nur O(n)
    statt O(n^2). `validate()` prueft trotzdem jeden Schnitt nach."""

    def last_price(self, symbol: str) -> float | None:
        df = self.bars.get(symbol)
        if df is None or df.empty:
            return None
        return float(df["close"].iloc[-1])

    def validate(self) -> None:
        """Prueft den Vertrag: nichts in dieser Momentaufnahme liegt nach `as_of`."""
        for name, store in (("bars", self.bars), ("signals", self.signals),
                            ("insider", self.insider)):
            for sym, df in store.items():
                if df is None or df.empty:
                    continue
                last = pd.Timestamp(df.index[-1])
                if last.tz is None:
                    last = last.tz_localize("UTC")
                if last > self.as_of:
                    raise ValueError(
                        f"LOOKAHEAD in {name}[{sym}]: Daten bis {last}, "
                        f"Stichtag ist {self.as_of}."
                    )


@dataclass
class PortfolioState:
    cash: float
    equity: float
    positions: dict[str, Position] = field(default_factory=dict)
    day_trades_used: int = 0
    opened_today: set[str] = field(default_factory=set)


@dataclass
class Decision:
    symbol: str
    action: str
    """'buy' | 'sell' | 'hold'"""
    reasons: dict
    conviction: float = 0.0
    target_notional: float = 0.0
    price: float = 0.0
    stop_price: float = 0.0
    target_price: float = 0.0
    blocked_by: str | None = None

    def __str__(self) -> str:
        tag = f" [blockiert: {self.blocked_by}]" if self.blocked_by else ""
        return (f"{self.action.upper():<5} {self.symbol:<6} "
                f"${self.target_notional:>9,.2f}  Score {self.conviction:.3f}{tag}")


@dataclass
class EngineConfig:
    """Die Stellschrauben der Strategie.

    Bewusst wenige und runde Werte. Jede zusaetzliche Stellschraube ist
    eine weitere Gelegenheit, die Historie zu ueberoptimieren.
    """

    max_positions: int = 12
    """Wie viele Werte gleichzeitig. Breite schlaegt Tiefe (IR = IC x sqrt(BR)),
    aber jede Position braucht genug Kapital, um Gebuehren zu ueberleben."""

    target_invested: float = 0.90
    """Anteil des Kapitals, der maximal im Markt steht. Nicht 1.0 - etwas
    Puffer verhindert Zwangsverkaeufe bei Kursluecken."""

    deploy_to_target: bool = False
    """Soll `target_invested` tatsaechlich ERREICHT werden?

    Standard `False` = bisheriges Verhalten: Die Volatilitaets-Skalierung
    wirkt als absoluter Multiplikator, der eine Position nur verkleinern
    kann. Weil Umkehr-Kandidaten definitionsgemaess gerade stark gefallen
    sind und damit fast immer ueber dem 3-%-ATR-Referenzwert liegen, wird
    dadurch systematisch WENIGER als `target_invested` eingesetzt -
    gemessen am 2026-07-30: 53,9 % statt 90 %, bei vollen 15 von 15
    Positionen. Das ist implizites Volatilitaets-Targeting: In unruhigen
    Phasen steht weniger Kapital im Markt.

    `True` = die Volatilitaets-Gewichtung bestimmt nur noch die RELATIVE
    Verteilung (Risikoparitaet: volatile Werte bekommen weniger Gewicht),
    wird aber so normiert, dass das freie Kapital bis `target_invested`
    eingesetzt wird. `max_position_pct` bleibt dabei hart - was durch den
    Deckel abgeschnitten wird, verteilt sich auf die uebrigen Kandidaten
    (Wasserfuellung).

    Bewusst KEIN neuer Standardwert: Beides sind unterschiedliche
    Risikohaltungen, keine richtig/falsch-Frage. Welche traegt, entscheidet
    der Vorwaertstest der Flotte (Bot B08_voll_investiert), nicht die
    Vermutung."""

    max_position_pct: float | None = None
    """Obergrenze je Einzelposition. None = Wert aus der .env (MAX_POSITION_PCT).

    Bewusst KEIN eigener Zahlenwert als Standard: Die Engine berechnet die
    Groesse damit, und `trading._check_risk()` prueft jede Order gegen
    denselben Wert aus der .env. Standen hier zwei verschiedene Zahlen
    (Engine 12 %, .env 10 %), schlug die Engine dauerhaft Groessen vor,
    die die Risikopruefung zwangslaeufig ablehnte - derselbe Kandidat
    wurde stundenlang in jeder Runde neu vorgeschlagen und blockiert."""

    min_position_pct: float = 0.001
    """Mindestgroesse als Anteil des Kapitals (0.1 %). Darunter frisst der
    Spread den Vorsprung. Bewusst relativ, nicht in USD - ein fixer
    Dollarbetrag waere bei einem 1.000-$-Konto eine faktische Handelssperre
    und bei einem 1.000.000-$-Konto bedeutungslos klein.

    Ein harter USD-Deckel je Order existiert bewusst NICHT mehr in der
    Engine (frueher `max_order_notional`) - er hat bei wachsendem Kapital
    still die MAX_POSITION_PCT-Regel unterlaufen und 25.000 $ von
    100.000 $ ungenutzt gelassen. Der einzige verbleibende Deckel ist
    `trading._check_risk()` mit MAX_ORDER_NOTIONAL aus der .env - ein
    reines Sicherheitsnetz gegen Rechenfehler, das bewusst so hoch steht,
    dass es unter normalem Betrieb nie bindet."""

    min_score: float = 0.55
    """Ab wann gilt ein Wert als Kandidat."""

    exit_score: float = 0.35
    """Faellt der Score darunter, wird verkauft - die These traegt nicht mehr."""

    stop_atr: float = 2.5
    """Stop-Abstand in ATR. Passt sich automatisch der Volatilitaet an."""

    target_atr: float = 6.0
    """Gewinnziel in ATR. Verhaeltnis 6:2.5 heisst: Treffer muessen nicht
    haeufig sein, nur gross genug (siehe strategie-analyse.md, Teil G.1)."""

    trail_after_atr: float = 3.0
    """Ab diesem Gewinn wird der Stop nachgezogen - Gewinne laufen lassen,
    aber nicht wieder hergeben."""

    max_hold_days: int = 60
    """Zeitausstieg. Eine These, die 60 Tage nicht aufgeht, war falsch."""

    min_dollar_volume: float = 2_000_000
    """Liquiditaetsuntergrenze. Was nicht handelbar ist, ist kein Signal."""

    min_price: float = 3.0
    """Untergrenze. Darunter fressen Spreads den Vorsprung
    (siehe costs.breakeven_move_pct)."""

    strategy: str = "reversal"
    """'reversal' = Kurzfrist-Umkehr (gemessen stabil, siehe signals.ReversalWeights)
    'momentum'  = der urspruengliche Mehrfaktor-Score (im Test unterlegen)"""

    reenter_cooldown_days: int = 3
    """Sperrfrist, bevor ein gerade verkauftes Symbol neu gekauft werden darf.

    Ohne diese Sperre verkauft die Engine eine Position am Ziel und kauft
    sie im SELBEN Durchgang sofort zurueck, weil ihr Score unveraendert
    hoch ist - beobachtet bei AMKR: drei Runden hintereinander verkauft und
    neu gekauft, mit identischem Stop und Ziel. Es entsteht keine neue
    These, nur doppelte Spread- und Gebuehrenkosten."""

    weights: SignalWeights = field(default_factory=SignalWeights)
    reversal_weights: ReversalWeights = field(default_factory=ReversalWeights)

    def __post_init__(self) -> None:
        if self.max_position_pct is None:
            try:
                from .config import get_settings

                self.max_position_pct = get_settings().max_position_pct
            except Exception:  # noqa: BLE001 - ohne .env laeuft die Simulation weiter
                self.max_position_pct = 0.10

    def as_dict(self) -> dict:
        """Die geltenden Regeln als flaches Dictionary - fuer das Protokoll.

        `audit.py` prueft spaetere Entscheidungen gegen genau diese Werte.
        Ohne sie kann der Regelabgleich nicht arbeiten und meldet stumm
        nichts, auch wenn eine Regel gar nicht greift.
        """
        return {
            "strategy": self.strategy,
            "max_positions": self.max_positions,
            "target_invested": self.target_invested,
            "deploy_to_target": self.deploy_to_target,
            "max_position_pct": self.max_position_pct,
            "min_position_pct": self.min_position_pct,
            "min_score": self.min_score,
            "exit_score": self.exit_score,
            "stop_atr": self.stop_atr,
            "target_atr": self.target_atr,
            "trail_after_atr": self.trail_after_atr,
            "max_hold_days": self.max_hold_days,
            "min_dollar_volume": self.min_dollar_volume,
            "min_price": self.min_price,
            "reenter_cooldown_days": self.reenter_cooldown_days,
        }

    @classmethod
    def for_reversal(cls, **overrides) -> EngineConfig:
        """Voreinstellungen fuer die Kurzfrist-Umkehr.

        Die Haltedauer MUSS zum Horizont passen, auf dem der Effekt
        gemessen wurde (3-5 Tage). Genau dieser Fehler hat den ersten
        Anlauf ruiniert: Momentum-Faktoren mit 3-12-Monats-Wirkung wurden
        mit 17 Tagen Haltedauer gehandelt.

        Enge Ziele und Stops, kurze Haltedauer, hoher Umschlag - dafuer
        muss der Vorsprung je Trade die Kosten deutlich uebersteigen.
        Ob er das tut, entscheidet die Simulation, nicht die Hoffnung.
        """
        defaults = dict(
            strategy="reversal",
            min_score=0.35,
            exit_score=0.10,
            stop_atr=2.0,
            target_atr=2.0,
            trail_after_atr=99.0,   # kein Trailing bei so kurzer Haltedauer
            max_hold_days=5,        # der Effekt lebt auf 3-5 Tagen
            max_positions=15,
            min_dollar_volume=1_000_000,
        )
        defaults.update(overrides)
        return cls(**defaults)


def _vola_gewicht(atr_pct: float) -> float:
    """Relatives Gewicht eines Kandidaten aus seiner Volatilitaet.

    Identisch zum bisherigen Skalierungsfaktor (3 % ATR als Referenz,
    hoechstens 1.5-fach) - nur wird er hier als GEWICHT verwendet und
    anschliessend normiert, statt als absoluter Multiplikator zu wirken.
    Dadurch bleibt die Risikoparitaet erhalten (volatile Werte bekommen
    weniger), ohne dass Kapital ungenutzt liegen bleibt.
    """
    if atr_pct <= 0:
        return 1.0
    return min(1.5, 0.03 / max(atr_pct, 0.005))


def verteile_kapital(
    gewichte: dict[str, float], frei: float, deckel: float, mindest: float
) -> dict[str, float]:
    """Verteilt `frei` auf die Kandidaten - Wasserfuellung mit Deckel.

    Drei Bedingungen gleichzeitig zu erfuellen ist nicht trivial:
      * die Summe soll `frei` moeglichst ausschoepfen,
      * keine Einzelposition darf `deckel` ueberschreiten,
      * Positionen unter `mindest` lohnen sich nicht (Spread frisst sie auf).

    Wer einfach proportional verteilt und danach deckelt, laesst das
    abgeschnittene Kapital liegen. Deshalb wird in Runden gefuellt: Wer den
    Deckel reisst, bekommt genau den Deckel und scheidet aus; sein Rest
    wird unter den Uebrigen neu aufgeteilt. Das wiederholt sich, bis
    niemand mehr anschlaegt.

    Zu kleine Positionen fliegen anschliessend raus, und ihr Anteil geht
    zurueck in den Topf - ebenfalls in Runden, weil dadurch andere
    Positionen wachsen und ihrerseits den Deckel reissen koennen.
    """
    if not gewichte or frei <= 0 or deckel <= 0:
        return {}

    # Mehr Kandidaten, als sich mit `mindest` ueberhaupt finanzieren lassen?
    # Dann die hinteren weglassen. `gewichte` kommt nach Score sortiert
    # herein, es fliegen also die schwaechsten Kandidaten zuerst. Wuerde man
    # stattdessen erst verteilen und danach alle zu kleinen streichen, bliebe
    # am Ende NICHTS uebrig - bei 50 Kandidaten und 3.000 $ Mindestgroesse
    # bekaeme jeder 1.800 $, alle faenden sich unter der Grenze wieder.
    max_n = int(frei // mindest) if mindest > 0 else len(gewichte)
    if max_n <= 0:
        return {}
    offen = {s: max(g, 1e-9) for s, g in list(gewichte.items())[:max_n]}

    def _fuellen(kandidaten: dict[str, float]) -> dict[str, float]:
        """Wasserfuellung: wer den Deckel reisst, bekommt genau den Deckel
        und scheidet aus; sein Rest wird unter den Uebrigen neu aufgeteilt."""
        groessen: dict[str, float] = {}
        rest, pool = frei, dict(kandidaten)
        while pool and rest > 1e-9:
            summe = sum(pool.values())
            if summe <= 0:
                break
            reisst = [s for s, g in pool.items() if rest * g / summe > deckel]
            if not reisst:
                for s, g in pool.items():
                    groessen[s] = rest * g / summe
                break
            for s in reisst:
                groessen[s] = deckel
                rest -= deckel
                del pool[s]
        return groessen

    groessen: dict[str, float] = {}
    for _ in range(len(offen) + 2):           # terminiert garantiert
        groessen = _fuellen(offen)
        zu_klein = [s for s, v in groessen.items() if v < mindest]
        if not zu_klein:
            return {s: v for s, v in groessen.items() if v > 0}
        # Nur den KLEINSTEN entfernen: Sein Anteil verteilt sich auf die
        # uebrigen, wodurch diese ueber die Mindestgroesse wachsen koennen.
        offen.pop(min(zu_klein, key=lambda s: groessen[s]), None)
        if not offen:
            return {}

    return {s: v for s, v in groessen.items() if v >= mindest}


class Engine:
    """Trifft Entscheidungen aus einer Momentaufnahme. Zustandslos."""

    def __init__(self, config: EngineConfig | None = None):
        self.cfg = config or EngineConfig()

    # -- Signalberechnung ---------------------------------------------------
    def _signals(self, symbol: str, snapshot: MarketSnapshot) -> pd.DataFrame:
        """Signale je Symbol.

        Bevorzugt die vorberechneten Signale aus der Momentaufnahme (schnell,
        und durch das PIT-Audit als gleichwertig nachgewiesen). Fehlen sie -
        etwa im Live-Betrieb -, werden sie hier berechnet.
        """
        pre = snapshot.signals.get(symbol)
        if pre is not None and not pre.empty:
            return pre
        if self.cfg.strategy == "reversal":
            return build_reversal_frame(
                snapshot.bars[symbol], snapshot.market, self.cfg.reversal_weights
            )
        return build_signal_frame(
            snapshot.bars[symbol], snapshot.insider.get(symbol), self.cfg.weights
        )

    # -- Hauptmethode -------------------------------------------------------
    def decide(
        self, snapshot: MarketSnapshot, portfolio: PortfolioState
    ) -> list[Decision]:
        """Was ist heute zu tun?

        Reihenfolge ist wichtig: Erst Ausstiege pruefen (macht Kapital und
        Plaetze frei), dann Einstiege. Andersherum wuerde das System
        Chancen verpassen, weil das Depot noch voll ist.
        """
        snapshot.validate()
        decisions: list[Decision] = []

        exits = self._check_exits(snapshot, portfolio)
        decisions.extend(exits)

        # Verkaufte Symbole geben ihren PLATZ frei, sind aber selbst gesperrt.
        # Beides zu vermischen war ein teurer Fehler: Die Position wurde am
        # Ziel verkauft und im selben Durchgang zurueckgekauft, weil ihr Score
        # unveraendert hoch war - dreimal hintereinander bei AMKR, jedes Mal
        # mit identischem Stop und Ziel. Nur die Kosten waren neu.
        freed = {d.symbol for d in exits if d.action == "sell"}
        blocked = freed | self._cooldown_symbols(snapshot.as_of)
        decisions.extend(self._find_entries(snapshot, portfolio, freed, blocked))
        return decisions

    def _cooldown_symbols(self, as_of: pd.Timestamp) -> set[str]:
        """Symbole, die noch in der Sperrfrist nach einem Verkauf stehen.

        Der Zustand liegt in der Datenbank, damit die Sperre auch einen
        Neustart des Prozesses ueberlebt - sonst waere sie nach jedem
        Absturz wirkungslos, und genau dann wird sie gebraucht.
        """
        days = self.cfg.reenter_cooldown_days
        if days <= 0:
            return set()
        try:
            from .state import Store

            return Store().symbols_in_cooldown(days, as_of=as_of)
        except Exception:  # noqa: BLE001 - in der Simulation ohne Store
            return set()

    # -- Ausstiege ----------------------------------------------------------
    def _check_exits(
        self, snapshot: MarketSnapshot, portfolio: PortfolioState
    ) -> list[Decision]:
        out: list[Decision] = []
        cfg = self.cfg

        for sym, pos in list(portfolio.positions.items()):
            df = snapshot.bars.get(sym)
            price = snapshot.last_price(sym)
            if df is None or price is None:
                continue

            frame = self._signals(sym, snapshot)
            row = frame.iloc[-1]
            score = float(row.get("score", 0.0))
            pnl = pos.unrealized_pct(price)

            reason: str | None = None
            if price <= pos.stop_price:
                reason = "stop_ausgeloest"
            elif price >= pos.target_price:
                reason = "gewinnziel_erreicht"
            elif pos.bars_held >= cfg.max_hold_days:
                reason = "zeitausstieg"
            elif score < cfg.exit_score:
                reason = "these_traegt_nicht_mehr"

            if reason:
                out.append(
                    Decision(
                        symbol=sym,
                        action="sell",
                        conviction=score,
                        price=price,
                        target_notional=pos.qty * price,
                        reasons={
                            "ausstiegsgrund": reason,
                            "gewinn_pct": round(pnl, 4),
                            "tage_gehalten": pos.bars_held,
                            "score_jetzt": round(score, 3),
                            "einstieg": round(pos.entry_price, 4),
                            "stop": round(pos.stop_price, 4),
                            "ziel": round(pos.target_price, 4),
                        },
                    )
                )
        return out

    # -- Einstiege ----------------------------------------------------------
    def _find_entries(
        self,
        snapshot: MarketSnapshot,
        portfolio: PortfolioState,
        being_sold: set[str],
        blocked: set[str] | None = None,
    ) -> list[Decision]:
        """
        Args:
            being_sold: gibt Depotplaetze frei (die Position verschwindet gleich).
            blocked: darf NICHT gekauft werden - gerade verkauft oder in der
                Sperrfrist. Bewusst getrennt von `being_sold`: das eine ist
                eine Kapazitaets-, das andere eine Zulassungsfrage.
        """
        cfg = self.cfg
        blocked = blocked or set()
        held = set(portfolio.positions) - being_sold
        slots = cfg.max_positions - len(held)
        if slots <= 0:
            return []

        # Alle Kandidaten bewerten und in eine Rangliste bringen.
        candidates: list[tuple[str, float, pd.Series, float]] = []
        for sym, df in snapshot.bars.items():
            if sym in held or sym in blocked or len(df) < 260:
                continue
            price = snapshot.last_price(sym)
            if price is None or price < cfg.min_price:
                continue

            frame = self._signals(sym, snapshot)
            row = frame.iloc[-1]
            score = float(row.get("score", 0.0))
            if not np.isfinite(score) or score < cfg.min_score:
                continue
            dvol = float(row.get("dollar_volume", 0) or 0)
            if dvol < cfg.min_dollar_volume:
                continue
            candidates.append((sym, score, row, price))

        candidates.sort(key=lambda x: -x[1])
        chosen = candidates[:slots]
        if not chosen:
            return []

        # --- Positionsgroesse ---
        # AUSSCHLIESSLICH prozentual vom aktuellen Kapital - kein fester
        # Dollarwert fliesst hier ein. Das ist bewusst so: Ein fixer
        # Dollar-Deckel wird bei wachsendem Kapital zur stillen Bremse
        # (genau das hat zuvor 25.000 $ von 100.000 $ brachliegen lassen,
        # weil MAX_ORDER_NOTIONAL=5000 unter dem 10-%-Anteil lag). Die
        # einzige Grenze ist der Portfolioanteil - die skaliert automatisch
        # mit, egal ob das Konto 1.000 $ oder 1.000.000 $ haelt.
        #
        # `MAX_ORDER_NOTIONAL` aus der .env bleibt als reines Sicherheitsnetz
        # gegen Rechenfehler in trading._check_risk erhalten (dort wird JEDE
        # Order nochmal geprueft) - hier in der Groessenberechnung wirkt es
        # bewusst NICHT mit, damit es die Skalierung nie unterlaeuft.
        investable = portfolio.equity * cfg.target_invested
        already = sum(
            p.qty * (snapshot.last_price(s) or p.entry_price)
            for s, p in portfolio.positions.items()
            if s not in being_sold
        )
        free = max(0.0, min(investable - already, portfolio.cash))
        per_slot = free / max(1, len(chosen))
        cap = portfolio.equity * cfg.max_position_pct
        mindest = portfolio.equity * cfg.min_position_pct

        # Bei `deploy_to_target` wird das freie Kapital vorab auf alle
        # Kandidaten verteilt (Wasserfuellung), damit `target_invested`
        # tatsaechlich erreicht wird. Sonst gilt der bisherige Weg, bei dem
        # die Volatilitaets-Skalierung absolut wirkt und nur verkleinern kann.
        verteilt: dict[str, float] = {}
        if cfg.deploy_to_target:
            verteilt = verteile_kapital(
                {sym: _vola_gewicht(float(row.get("atr_pct", 0) or 0))
                 for sym, _score, row, _price in chosen},
                frei=free, deckel=cap, mindest=mindest,
            )

        out: list[Decision] = []
        for sym, score, row, price in chosen:
            atr = float(row.get("atr", 0) or 0)
            atr_pct = float(row.get("atr_pct", 0) or 0)

            if cfg.deploy_to_target:
                size = verteilt.get(sym, 0.0)
                if size <= 0:
                    continue
            else:
                size = min(per_slot, cap)
                # Volatilitaets-Skalierung: 3 % ATR ist der Referenzwert.
                if atr_pct > 0:
                    size *= min(1.5, 0.03 / max(atr_pct, 0.005))
                size = min(size, cap)

                # Auch die Mindestgroesse ist relativ zum Kapital, nicht ein
                # fixer Dollarbetrag - sonst driftet sie bei wachsendem Konto
                # in die Bedeutungslosigkeit oder wird bei kleinem Konto zur
                # faktischen Handelssperre.
                if size < mindest:
                    continue

            stop = price - cfg.stop_atr * atr if atr > 0 else price * 0.90
            target = price + cfg.target_atr * atr if atr > 0 else price * 1.25

            reasons = (explain_reversal(row) if cfg.strategy == "reversal"
                       else explain(row, cfg.weights))
            reasons["rang"] = len(out) + 1
            reasons["stop_abstand_pct"] = round(1 - stop / price, 4)
            reasons["ziel_abstand_pct"] = round(target / price - 1, 4)

            out.append(
                Decision(
                    symbol=sym,
                    action="buy",
                    conviction=score,
                    price=price,
                    target_notional=round(size, 2),
                    stop_price=round(stop, 4),
                    target_price=round(target, 4),
                    reasons=reasons,
                )
            )
        return out

    # -- Stop nachziehen ----------------------------------------------------
    def update_position(self, pos: Position, price: float, atr: float) -> Position:
        """Taegliche Pflege einer offenen Position: Haltedauer und Trailing-Stop.

        Der Stop wird nur nach OBEN gezogen, nie nach unten. Ein Stop, den
        man nachgibt, wenn es unangenehm wird, ist kein Stop.
        """
        pos.bars_held += 1
        pos.high_water = max(pos.high_water or pos.entry_price, price)

        if atr > 0 and price >= pos.entry_price + self.cfg.trail_after_atr * atr:
            trailed = pos.high_water - self.cfg.stop_atr * atr
            pos.stop_price = max(pos.stop_price, trailed)
        return pos
