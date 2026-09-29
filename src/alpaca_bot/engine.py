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
    RankingWeights,
    ReversalWeights,
    SignalWeights,
    build_ranking_frame,
    build_reversal_frame,
    build_signal_frame,
    explain,
    explain_ranking,
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
    news: pd.DataFrame | None = None
    """Roh-Artikel ueber ALLE betrachteten Symbole (Format wie news.get_news()),
    ebenfalls nur bis as_of - `signals.build_reversal_frame` filtert intern
    per Symbol und wendet die Verfuegbarkeitsverzoegerung an (pit.asof_join).
    Fehlt dieses Feld, entfaellt der Nachrichtenfaktor ersatzlos."""
    kontext: dict[str, dict] = field(default_factory=dict)
    """Zusatzangaben je Symbol fuer das PROTOKOLL - nie fuer die Entscheidung.

    Erlaubte Schluessel: `sektor`, `liq_dezil`. Sie beantworten spaeter
    Fragen, die am Depot sonst unbeantwortbar bleiben: "Funktioniert die
    Strategie bei Nebenwerten besser?" und "Klumpt das Depot in einem
    Sektor?" (BEFUNDE, Luecken im Betriebsplan).

    **Bewusst NICHT in die Score-Berechnung eingebunden.** Wuerde der
    Sektor die Entscheidung beeinflussen, waere das eine ungetestete
    Strategieaenderung. Hier geht es ausschliesslich darum, spaeter
    auswerten zu koennen, was ohnehin passiert ist."""

    regime: dict = field(default_factory=dict)
    """Marktlage zum Entscheidungszeitpunkt - ebenfalls nur fuers Protokoll.

    Der Schattenbetrieb erfasst das seit jeher (`shadow._regime`), der
    Live-Pfad bisher gar nicht. Damit war die wichtigste Frage des
    Projekts am Depot nicht beantwortbar: In WELCHER Marktlage traegt die
    Strategie? (docs/schattenbetrieb.md §13 nennt genau das "wo der echte
    Gewinn liegt".)"""

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

        if self.news is not None and not self.news.empty:
            from . import pit

            pit.assert_no_future_events(self.news, self.as_of, time_col="timestamp")


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

    position_size_margin: float = 0.995
    """Sicherheitsabstand zur Positionsgrenze (0.5 %).

    Die Engine sizet Kandidaten mit hohem Score bewusst bis exakt an
    max_position_pct heran. Das Kapital, gegen das sie rechnet, ist aber
    eine Momentaufnahme von `portfolio.equity` - und `trading._check_risk()`
    holt sich beim TATSAECHLICHEN Senden der Order Sekunden spaeter einen
    FRISCHEN Kapitalwert. Bei live schwankenden Kursen reicht die kleinste
    Bewegung dazwischen, um aus 10,000 % 10,001 % zu machen - beobachtet am
    31.07.2026 bei META und SAIA, die deshalb ueber mehrere Runden hinweg
    identisch vorgeschlagen und blockiert wurden, ohne dass sich am Score
    etwas geaendert haette. Derselbe Puffer-Gedanke wie bei
    `target_invested` (0.90 statt 1.0), nur enger, weil es hier nur um
    Sekunden Drift geht, nicht um einen ganzen Handelstag."""

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

    groessen_modus: str = "inverse_vola"
    """Wie das freie Kapital auf die Kandidaten verteilt wird.

    **Die einzige Strukturachse, die bis zum 26.08.2026 nie gemessen
    wurde.** Alle 13 Flottenbots und alle 14 Lernlauf-Achsen variieren
    Ein- und Ausstiegsregeln; wie VIEL ein Kandidat bekommt, war fest
    verdrahtet.

        inverse_vola   Gewicht = min(1.5, 0.03/atr_pct). Risikoparitaet:
                       volatile Werte bekommen weniger. **Vorgabe, und
                       bitgleich zum Verhalten vor dem 26.08.2026.**
        gleich         Gewicht = 1.0 fuer jeden. Die Nullhypothese - hat
                       die Volatilitaetsgewichtung ueberhaupt je etwas
                       gebracht? Niemand hat es geprueft.
        score          Gewicht = Score. Der Score entscheidet heute nur,
                       OB gekauft wird und in welcher Reihenfolge, nicht
                       wieviel. Traegt er Information (IC > 0, sonst gaebe
                       es die Strategie nicht), liegt hier Kapital an der
                       falschen Stelle.
        score_vola     Beides multipliziert.

    **Warum das die interessanteste verbliebene Achse ist:** Sie aendert
    die Kosten je Einheit Vorsprung, OHNE den Umschlag zu aendern. Jede
    andere Achse justiert Randbedingungen eines Vorsprungs, der zu klein
    ist (BEFUNDE §A, §B6).

    Zu messen im Historienlauf (`32_lernlauf.py`, 3.767 Handelstage), nicht
    im Schatten (15 Tage) - und erst danach als Voranmeldung."""

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

    zeitausstieg_dynamisch: bool = False
    """Darf der Zeitausstieg aufgeschoben werden, solange die Position traegt?

    Standard `False` = unveraendertes Verhalten: Nach `max_hold_days` wird
    verkauft, egal wie der Wert gerade laeuft.

    `True` = die Frist wird verlaengert, SOLANGE zwei Bedingungen zugleich
    gelten (siehe `_traegt_noch`): Die Position steht im Gewinn UND ihr
    Kurs liegt nahe an ihrem eigenen Hoechststand seit Einstieg. Faellt
    sie vom Hoechststand zurueck oder ins Minus, greift der Zeitausstieg
    sofort - auch rueckwirkend, wenn die Frist laengst ueberschritten ist.

    **Warum ueberhaupt:** Gemessen am 15.08.2026 sind 15 von 24
    Ausstiegen im Schattenbetrieb Zeitausstiege (62 %) - die Frist ist der
    mit Abstand wirksamste Ausstiegsgrund. Zugleich zeigte sich, dass
    `target_atr` praktisch WIRKUNGSLOS ist (Bot B03: identische Renditen,
    nur anderes Etikett, weil `exit_score` gleichzeitig ausloest). Wer
    Gewinne laufen lassen will, muss deshalb genau hier ansetzen und
    nicht am Gewinnziel.

    **Warum nicht einfach `max_hold_days` hochsetzen:** Das wuerde auch
    jede stagnierende Position laenger halten und damit Kapital binden,
    das anderswo arbeiten koennte. B04_halten_lang misst genau das
    (10 statt 5 Tage) und liegt bei t = 0.94 - kein nachweisbarer Vorteil.
    Die dynamische Variante haelt NUR die Werte laenger, die tatsaechlich
    noch laufen.

    **Ungetestet.** Gehoert in die Flotte, nicht in den Live-Bot."""

    trend_rueckfall_atr: float = 1.0
    """Wie weit darf der Kurs vom Hoechststand zurueckfallen, ohne dass der
    Trend als gebrochen gilt - gemessen in ATR, nicht in Prozent.

    **Warum ATR und kein fester Prozentsatz:** Umkehr-Kandidaten sind per
    Definition Werte, die gerade stark gefallen sind - also volatile.
    Gemessen an den tatsaechlich gehaltenen Positionen (15.08.2026, 200
    Positionstage) betraegt ihr ATR im Median **5,16 %**, im oberen Viertel
    ueber 8 %. Ein fester Schwellwert kann das nicht abbilden:

        feste 2 %      -> loeste an 27,5 % aller Positionstage aus
        1.0 x ATR      -> loest an  6,0 % aus  (~5,2 % beim Median)
        1.5 x ATR      -> loest an  1,0 % aus

    Bei 2 % wuerde also mehr als jeder vierte Tag als "Trend gebrochen"
    gelten, obwohl eine Bewegung dieser Groesse fuer diese Werte voellig
    normales Rauschen ist. Die Verlaengerung waere damit praktisch nie
    wirksam geworden - der Parameter haette anders geheissen als er wirkt.

    1.0 als Standard: Ein Rueckfall um eine volle Tagesschwankung ist mehr
    als Rauschen, aber noch keine Trendwende. Derselbe Massstab, den
    `stop_atr` und `target_atr` bereits verwenden - ein fester Prozentwert
    waere hier der einzige Fremdkoerper im System gewesen."""

    max_hold_days_hart: int = 20
    """Absolute Obergrenze, auch wenn die Position noch traegt. Ohne sie
    koennte eine Position unbegrenzt laufen - und der Umkehr-Effekt ist
    auf 3-5 Tagen gemessen, nicht auf Monaten. Was so lange laeuft, ist
    kein Umkehr-Trade mehr, sondern ein Momentum-Trade unter falschem
    Namen (genau der Fehler, der den ersten Anlauf ruiniert hat)."""

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

    sizing: str = "vola"
    """Gewichtung bei `deploy_to_target`: "vola" = 1/ATR-Gewichte (Risikoparitaet),
    "gleich" = Gleichgewicht wie die vektorisierte Labor-Referenz (22_)."""

    score_quelle: str = "mix"
    """Woher der Querschnitts-Score der Strategie 'ranking' kommt:
    "mix"    = Z-Score-Mix der RankingWeights (Handmix)
    "ml"     = Spalte `ml_score` der Signale (Vorhersage eines gespeicherten Modells, modell.py)
    "hybrid" = ueber der SMA200 (markt_ok) der Handmix, darunter das Modell (HYP-2027-25:
               Momentum traegt im Trend, das Modell in der Erholung). Das Regime-Tor wird
               fuer Einstiege dann NICHT angewendet - den Schutz uebernimmt das Vola-Ziel.
    Fehlt `ml_score` in einer Modell-Phase, gibt es keine Kandidaten und damit keine
    Kaeufe (sicherer Ausfall)."""

    ml_modell: str | None = None
    """Name des gespeicherten Modells (models/<name>.txt/.json) fuer score_quelle 'ml'/'hybrid';
    None = das juengste `lgbm_h21_*`."""

    max_new_per_day: int | None = None
    """Hoechstens so viele NEUE Positionen je Handelstag - gestaffelte Kohorten statt
    einer Klumpen-Kohorte. Grund (masterplan §6.9): Dieselbe Strategie als einzelne
    42-Tage-Kohorte streut je nach Startversatz zwischen 7,9 % und 18,0 % CAGR; die
    Momentum-Literatur (Jegadeesh/Titman) mittelt das mit ueberlappenden Kohorten weg.
    Mit Deckel 3-5 baut sich die Engine diese Staffelung selbst. None = kein Deckel.
    Gilt in Simulation UND Live (dort zusaetzlich der Deckel des Laufs)."""

    stop_atr_modellphase: float | None = None
    """Stop-Abstand (in ATR) fuer Kaeufe in der Modell-Phase des Hybrids (SPY unter SMA200).
    None = wie `stop_atr`. HYP-2027-26: Dort reisst der enge Stop die Erholungskaeufe am
    Tief raus (qlib: 10,5 % mit gegen 15,5 % ohne Stop); 99 = praktisch kein Stop."""
    renew_rank_pct: float | None = None
    """Verlaengerung (Strategie 'ranking'): Nach `max_hold_days` wird NUR verkauft, wenn
    das Rangperzentil der Position UNTER diesem Wert liegt. None = klassischer
    Zeitausstieg. Gemessen (masterplan §6.9): greift selten und hilft nicht - bleibt als
    Schalter fuer Replays, ist nicht Standard."""

    allow_topup: bool = False
    """Duerfen bereits gehaltene Positionen zusaetzliches Kapital bekommen,
    BEVOR ein Platz frei wird?

    Standard False - unveraendertes Verhalten. `_find_entries` schliesst
    gehaltene Symbole grundsaetzlich aus; ohne diesen Schalter bleibt freies
    Kapital bei vollen Positionsplaetzen ungenutzt liegen, bis eine Position
    ausgestoppt wird, ihr Ziel erreicht oder die Haltefrist ablaeuft.

    Bewusst SEPARAT von `deploy_to_target`: Jenes bestimmt, wie stark NEUE
    Positionen gefuellt werden. Dieses hier erlaubt zusaetzlich, GEHALTENE
    Positionen nachzukaufen. Beides zusammen sonst zu vermengen macht es
    unmoeglich zu sagen, woran ein Effekt lag.

    Nur fuer Gewinner (siehe `topup_min_gain_pct`) und nur, wenn die These
    heute noch genauso stark ist wie bei einem Neukauf (`min_score`) - eine
    angeschlagene Position bekommt kein zusaetzliches Kapital
    ("nachkaufen in eine wackelnde These" ist Average-Down, nicht
    Ueberzeugung). Stop und Ziel bleiben bei den urspruenglichen Werten -
    sie chasen der Position nicht hinterher. `bars_held` und `high_water`
    werden NICHT zurueckgesetzt, sonst wuerde wiederholtes Nachkaufen die
    Haltefrist-Regel faktisch aushebeln.

    ERST im Schattenbetrieb messen (Bot B09_nachkauf), bevor der Live-Bot
    das je tut - siehe docs/schattenbetrieb.md."""

    topup_min_gain_pct: float = 0.0
    """Nur Positionen mindestens auf diesem Gewinnniveau werden aufgestockt.
    0.0 = ab Break-even. Verhindert, in eine bereits verlustreiche Position
    nachzukaufen."""

    # --- nur Strategie "ranking" (masterplan-2027 §7) ---
    min_hold_days: int = 0
    """Mindesthaltedauer in Handelstagen, bevor der Rangverlust-Ausstieg
    greifen darf. Stop, Ziel und Zeitausstieg gelten immer. Bei 'ranking'
    21: Der Score wurde auf 21-Tage-Renditen gemessen, ein Ausstieg nach
    drei Tagen wegen eines Rangwechsels waere Umschlag ohne Gegenwert."""

    min_rank_pct: float = 0.90
    """Kauf nur aus dem obersten Perzentil des Tages-Querschnitts (0,90 =
    beste 10 %). Bei 800 Kandidaten sind das 80, aus denen die freien
    Plaetze nach Score gefuellt werden."""

    exit_rank_pct: float = 0.50
    """Rangverlust-Ausstieg: faellt eine Position unter dieses Perzentil
    (nach `min_hold_days`), traegt die These nicht mehr. Bewusst weit unter
    der Kaufschwelle (Hysterese), sonst wird staendig getauscht."""

    weights: SignalWeights = field(default_factory=SignalWeights)
    reversal_weights: ReversalWeights = field(default_factory=ReversalWeights)
    ranking_weights: RankingWeights = field(default_factory=RankingWeights)

    def __post_init__(self) -> None:
        if self.score_quelle == "hybrid":
            self.ranking_weights.market_regime_filter = False
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
            "allow_topup": self.allow_topup,
            "topup_min_gain_pct": self.topup_min_gain_pct,
            "max_position_pct": self.max_position_pct,
            "min_position_pct": self.min_position_pct,
            "min_score": self.min_score,
            "groessen_modus": self.groessen_modus,
            "exit_score": self.exit_score,
            "stop_atr": self.stop_atr,
            "target_atr": self.target_atr,
            "trail_after_atr": self.trail_after_atr,
            "max_hold_days": self.max_hold_days,
            "zeitausstieg_dynamisch": self.zeitausstieg_dynamisch,
            "trend_rueckfall_atr": self.trend_rueckfall_atr,
            "max_hold_days_hart": self.max_hold_days_hart,
            "min_dollar_volume": self.min_dollar_volume,
            "min_price": self.min_price,
            "reenter_cooldown_days": self.reenter_cooldown_days,
            "sizing": self.sizing,
            "score_quelle": self.score_quelle,
            "renew_rank_pct": self.renew_rank_pct,
            # Gewichte der Ranking-Strategie: sonst prueft der Regelabgleich nie, ob ein
            # Bot mit anderen Gewichten laeuft, als er angemeldet wurde.
            "ranking_weights": {
                **{k: float(getattr(self.ranking_weights, k)) for k in self.ranking_weights.FAKTOREN},
                "market_regime_filter": bool(self.ranking_weights.market_regime_filter),
                "min_price": float(self.ranking_weights.min_price),
                "max_volatility": float(self.ranking_weights.max_volatility),
            },
            "stop_atr_modellphase": self.stop_atr_modellphase,
            "ml_modell": self.ml_modell,
            "max_new_per_day": self.max_new_per_day,
            "min_hold_days": self.min_hold_days,
            "min_rank_pct": self.min_rank_pct,
            "exit_rank_pct": self.exit_rank_pct,
        }

    @classmethod
    def for_ranking(cls, **overrides) -> EngineConfig:
        """Voreinstellungen fuer die Multi-Wochen-Auswahl (masterplan-2027 §7).

        Die Zahlen sind die GEMESSENEN Rahmenbedingungen, nicht optimierte
        Werte: Universum >= 25 Mio. $/Tag und Kurs >= 5 $ (Top 20 aus 3.000
        Werten verliert, §6.6), Top 50 (Breite), Haltedauer 21-63 Tage (der
        Score wurde auf 21-42 Tagen gemessen), Stop 3 ATR, kein Gewinnziel
        (Momentum wird nicht gedeckelt), Regime-Tor ueber SPY-SMA200, Kapital
        bis zum Zielanteil eingesetzt mit 1/Vola-Gewichtung.

        Erwarteter Umschlag ~12-18 Rundlaeufe je Jahr und Position, also
        ~2-4 % Kosten p.a. bei 20 bps - der ganze Unterschied zum Umkehr-Bot
        (100 Rundlaeufe, 10-20 % Kosten).

        Stand 2026-09-29 (masterplan §6.9, lehren §1): Rangverlust erst unter dem
        20. Perzentil, hoechstens 3 neue Positionen je Tag (Staffelung), Stop 3 ATR,
        keine Verlaengerung, 1/Vola-Sizing. Score-Quelle 'mix' als Rueckfall; 'ml'
        und 'hybrid' (HYP-25) nach Stufe 1 auf dem Projektcache.
        """
        defaults = dict(
            strategy="ranking",
            max_positions=50,
            min_hold_days=21,
            max_hold_days=63,
            min_rank_pct=0.90,
            exit_rank_pct=0.20,     # 2026-09-29: 0,50 -> 0,20 (S&P +1 Punkt, qlib +1,7; MaxDD -31 -> -20 %)
            stop_atr=3.0,           # bleibt: halbiert den Drawdown, kostet keine CAGR (HYP-20 widerlegt)
            target_atr=99.0,        # kein Gewinnziel
            trail_after_atr=99.0,   # kein Trailing - der Rang entscheidet
            min_score=float("-inf"),
            exit_score=float("-inf"),
            min_dollar_volume=25_000_000,
            min_price=5.0,
            deploy_to_target=True,
            allow_topup=False,
            reenter_cooldown_days=5,
            max_new_per_day=3,      # gestaffelte Kohorten gegen die Kohorten-Lotterie (masterplan §6.9)
        )
        defaults.update(overrides)
        return cls(**defaults)

    @classmethod
    def for_reversal(cls, **overrides) -> EngineConfig:
        """Voreinstellungen fuer die Kurzfrist-Umkehr - der GELTENDE Stand.

        Die Haltedauer MUSS zum Horizont passen, auf dem der Effekt
        gemessen wurde (3-5 Tage). Genau dieser Fehler hat den ersten
        Anlauf ruiniert: Momentum-Faktoren mit 3-12-Monats-Wirkung wurden
        mit 17 Tagen Haltedauer gehandelt.

        Enge Ziele und Stops, kurze Haltedauer, hoher Umschlag - dafuer
        muss der Vorsprung je Trade die Kosten deutlich uebersteigen.
        Ob er das tut, entscheidet die Simulation, nicht die Hoffnung.

        ------------------------------------------------------------------
        MESSSTAND: was ist an diesen Werten geprueft? (Stand 23.08.2026)
        ------------------------------------------------------------------
        Diese Tabelle beantwortet die Frage, die sich in ein paar
        Generationen zwangslaeufig wieder stellt: *"Ist das der beste Wert
        oder nur der erste, den jemand hingeschrieben hat?"* Sie nennt je
        Achse den Flottenbot, der die Alternative geprueft hat, und das
        Ergebnis. Kein Eintrag = nie gegengemessen.

          Wert                       geprueft durch     Ergebnis
          -------------------------  -----------------  --------------------
          min_score=0.35             B05 (-> 0.50)      wirkungslos: band nie,
                                                        alle Kaeufe >= 0.678
                                     B12 (-> 0.80)      LAEUFT seit 21.08.,
                                                        filtert 21,6 % (kalibriert
                                                        am Median 0,97 der
                                                        echten Kaeufe)
          stop_atr=2.0               B01 (-> 1.5)       wirkungslos, stillgelegt
                                     B02 (-> 3.0)       wirkungslos, stillgelegt
                                                        (in 14 Tagen kein
                                                        einziger Stop ausgeloest)
          target_atr=2.0             B03 (-> 3.0)       wirkungslos, stillgelegt -
                                                        `exit_score` feuert am
                                                        selben Tag zum selben Kurs
          max_hold_days=5            B04 (-> 10)        laeuft, unter der Schwelle
                                     Historienlauf      marktbereinigt NEGATIV auf
                                                        allen Horizonten (§G11)
          zeitausstieg_dynamisch=F   B11                LAEUFT, Termin 10.10.2026
                                                        (BETRIEBSPLAN §3.3)
          max_positions=15           B07 (-> 25)        laeuft, Tendenz NEGATIV
          deploy_to_target=F*        B08                laeuft, unter der Schwelle
          allow_topup=F*             B09                misst NICHTS - bitgleich
                                                        mit B08 (§G16 Fund 1)
          Regimefilter an            B06                im Bullenmarkt wirkungslos,
                                                        wartet auf Regimewechsel
          reenter_cooldown_days=3    --                 NIE gegengemessen; Kosten
                                                        beziffert in §F
          exit_score=0.10            --                 NIE gegengemessen, obwohl
                                                        §E ihn als den Wert
                                                        ausweist, der `target_atr`
                                                        aushebelt
          trail_after_atr=99.0       --                 NIE gegengemessen
          min_dollar_volume=1e6      --                 Liquiditaetsgrenze, keine
                                                        Ertragsachse
          min_price=3.0              --                 dito

        (*) Der LIVE-Bot laeuft seit dem 30.07.2026 mit
        `deploy_to_target=True` und `allow_topup=True` - er setzt sie ueber
        `scripts/12_daemon.py`. Die Vorgabe hier ist bewusst `False`
        geblieben, weil `B00_basis` sie traegt. Genau diese Luecke war
        BEFUNDE §G6: "B00_basis entspricht dem Live-Bot" stimmte danach
        nie wieder. Wer die Live-Konfiguration braucht, nimmt
        `B09_nachkauf`, nicht diese Vorgaben.

        **Wie diese Tabelle aktuell bleibt.** Sie wird bei jeder
        Stilllegung und jeder Anmeldung mitgezogen. Die laufenden t-Werte
        stehen bewusst NICHT hier - sie aendern sich taeglich, und eine
        abgeschriebene Zahl ist binnen einer Woche falsch (BEFUNDE §G19
        Fund 2). Abrufen mit `python scripts/27_status.py`.

        **Was "kein Eintrag" bedeutet.** Nicht "gut", sondern
        "ungemessen". Drei Achsen tragen die Strategie mit und wurden nie
        gegengeprueft - `exit_score` ist die auffaelligste, weil §E ihn
        als den Wert ausweist, der `target_atr` wirkungslos macht.
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


def kandidatengewicht(atr_pct: float, score: float, modus: str) -> float:
    """Relatives Gewicht eines Kandidaten nach `EngineConfig.groessen_modus`.

    Rein relativ: `verteile_kapital` normiert anschliessend. Ein Gewicht
    von 0 ist deshalb verboten - es wuerde die Position stumm auf null
    setzen, statt sie klein zu machen. Der Score kann bei `min_score=0`
    beliebig nahe an 0 liegen, darum die Untergrenze.
    """
    vola = _vola_gewicht(atr_pct)
    if modus == "gleich":
        return 1.0
    if modus == "score":
        return max(float(score), 0.05)
    if modus == "score_vola":
        return max(float(score), 0.05) * vola
    return vola  # "inverse_vola" - die Vorgabe, unveraendert


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
    gewichte: dict[str, float],
    frei: float,
    deckel: float | dict[str, float],
    mindest: float,
) -> dict[str, float]:
    """Verteilt `frei` auf die Kandidaten - Wasserfuellung mit Deckel.

    Drei Bedingungen gleichzeitig zu erfuellen ist nicht trivial:
      * die Summe soll `frei` moeglichst ausschoepfen,
      * keine Einzelposition darf ihren Deckel ueberschreiten,
      * Positionen unter `mindest` lohnen sich nicht (Spread frisst sie auf).

    Wer einfach proportional verteilt und danach deckelt, laesst das
    abgeschnittene Kapital liegen. Deshalb wird in Runden gefuellt: Wer den
    Deckel reisst, bekommt genau den Deckel und scheidet aus; sein Rest
    wird unter den Uebrigen neu aufgeteilt. Das wiederholt sich, bis
    niemand mehr anschlaegt.

    Zu kleine Positionen fliegen anschliessend raus, und ihr Anteil geht
    zurueck in den Topf - ebenfalls in Runden, weil dadurch andere
    Positionen wachsen und ihrerseits den Deckel reissen koennen.

    `deckel` darf eine Zahl sein (gleiche Obergrenze fuer alle, der Fall
    beim Neukauf) oder ein Dictionary je Symbol. Letzteres braucht der
    Nachkauf: Dort ist die Obergrenze die RESTLUFT bis `max_position_pct`,
    und die ist fuer jede gehaltene Position eine andere.
    """
    if not gewichte or frei <= 0:
        return {}

    deckel_je = (deckel if isinstance(deckel, dict)
                 else {s: float(deckel) for s in gewichte})
    gewichte = {s: g for s, g in gewichte.items() if deckel_je.get(s, 0) > 0}
    if not gewichte:
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
        """Wasserfuellung: wer seinen Deckel reisst, bekommt genau den Deckel
        und scheidet aus; sein Rest wird unter den Uebrigen neu aufgeteilt."""
        groessen: dict[str, float] = {}
        rest, pool = frei, dict(kandidaten)
        while pool and rest > 1e-9:
            summe = sum(pool.values())
            if summe <= 0:
                break
            reisst = [s for s, g in pool.items()
                      if rest * g / summe > deckel_je[s]]
            if not reisst:
                for s, g in pool.items():
                    groessen[s] = rest * g / summe
                break
            for s in reisst:
                groessen[s] = deckel_je[s]
                rest -= deckel_je[s]
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
                snapshot.bars[symbol], snapshot.market, self.cfg.reversal_weights,
                symbol=symbol, news=snapshot.news,
            )
        if self.cfg.strategy == "ranking":
            return build_ranking_frame(
                snapshot.bars[symbol], snapshot.market, self.cfg.ranking_weights
            )
        return build_signal_frame(
            snapshot.bars[symbol], snapshot.insider.get(symbol), self.cfg.weights
        )

    # -- Querschnitts-Score (nur Strategie "ranking") -------------------------
    def _querschnitt_scores(
        self, snapshot: MarketSnapshot, portfolio: PortfolioState
    ) -> dict[str, dict]:
        """Z-Score-Mix ueber ALLE zulaessigen Kandidaten eines Tages.

        Genau so wurde die Strategie gemessen (labor.kombinieren): jeder
        Baustein wird ueber den Tages-Querschnitt standardisiert (Mittel 0,
        Streuung 1, gekappt bei +-3), gewichtet addiert, und der Rang als
        Perzentil ausgewiesen. Gehaltene Positionen bekommen ihren Rang
        immer - auch wenn sie heute nicht mehr zulaessig waeren (dann
        Perzentil 0, damit der Rangverlust-Ausstieg greift).
        """
        cfg = self.cfg
        gew = cfg.ranking_weights.gewichte()
        zeilen: dict[str, pd.Series] = {}
        for sym, df in snapshot.bars.items():
            if len(df) < 260:
                continue
            frame = self._signals(sym, snapshot)
            if frame.empty:
                continue
            zeilen[sym] = frame.iloc[-1]
        if not zeilen:
            return {}
        tab = pd.DataFrame(zeilen).T
        for k in gew:
            tab[k] = pd.to_numeric(tab.get(k), errors="coerce")
        dvol = pd.to_numeric(tab.get("dollar_volume"), errors="coerce").fillna(0.0)
        zul = (pd.to_numeric(tab.get("zulaessig"), errors="coerce").fillna(0.0) > 0) \
            & (dvol >= cfg.min_dollar_volume) & tab[list(gew)].notna().all(axis=1)
        markt_ok = bool(pd.to_numeric(tab.get("markt_ok"), errors="coerce").fillna(1.0).mean() >= 0.5)
        modell_phase = cfg.score_quelle == "ml" or (cfg.score_quelle == "hybrid" and not markt_ok)
        self.__dict__["_modell_phase"] = modell_phase
        if modell_phase:
            # Fehlt die Spalte ganz (kein Modell geladen), gibt es keine Kandidaten.
            roh = tab["ml_score"] if "ml_score" in tab.columns else pd.Series(np.nan, index=tab.index)
            ml = pd.to_numeric(roh, errors="coerce")
            tab["ml_score"] = ml
            zul = zul & ml.notna()
        kand = tab[zul]
        out: dict[str, dict] = {}
        if len(kand) >= 30:
            if modell_phase:
                # Die Vorhersage IST der Querschnitts-Score - kein Mix, keine Kappung.
                score = kand["ml_score"].astype(float)
            else:
                score = pd.Series(0.0, index=kand.index)
                for k, w in gew.items():
                    s = kand[k].astype(float)
                    sd = s.std()
                    z = ((s - s.mean()) / sd).clip(-3, 3) if sd and np.isfinite(sd) and sd > 0 else s * 0.0
                    score = score + w * z
            pct = score.rank(pct=True)
            for sym in kand.index:
                out[sym] = {"score": float(score[sym]), "pct": float(pct[sym]),
                            "row": kand.loc[sym]}
        # Gehaltene Positionen ohne Zulassung: Rang 0, Score -inf
        for sym in portfolio.positions:
            if sym not in out and sym in tab.index:
                out[sym] = {"score": float("-inf"), "pct": 0.0, "row": tab.loc[sym]}
        return out

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

        # Ranking: der Score entsteht im Querschnitt ALLER Kandidaten des
        # Tages - einmal rechnen, dann fuer Ausstiege und Einstiege nutzen.
        self._qs: dict[str, dict] = (
            self._querschnitt_scores(snapshot, portfolio)
            if self.cfg.strategy == "ranking" else {}
        )

        exits = self._check_exits(snapshot, portfolio)
        decisions.extend(exits)

        # Verkaufte Symbole geben ihren PLATZ frei, sind aber selbst gesperrt.
        # Beides zu vermischen war ein teurer Fehler: Die Position wurde am
        # Ziel verkauft und im selben Durchgang zurueckgekauft, weil ihr Score
        # unveraendert hoch war - dreimal hintereinander bei AMKR, jedes Mal
        # mit identischem Stop und Ziel. Nur die Kosten waren neu.
        freed = {d.symbol for d in exits if d.action == "sell"}
        blocked = freed | self._cooldown_symbols(snapshot.as_of)
        entries = self._find_entries(snapshot, portfolio, freed, blocked)
        decisions.extend(entries)

        # Nachkauf ZULETZT: Neue Positionen haben Vorrang vor dem Aufstocken
        # bestehender. Breite schlaegt Tiefe - erst wenn keine neuen
        # Kandidaten mehr aufgenommen werden koennen (Plaetze voll oder
        # nichts ueber der Schwelle), wandert freies Kapital in vorhandene
        # Positionen. Was die Einstiege bereits verplant haben, ist fuer den
        # Nachkauf nicht mehr verfuegbar.
        if self.cfg.allow_topup:
            verplant = sum(d.target_notional for d in entries)
            decisions.extend(
                self._find_topups(snapshot, portfolio, freed, verplant)
            )
        return decisions

    # -- Nachkauf ------------------------------------------------------------
    def _find_topups(
        self,
        snapshot: MarketSnapshot,
        portfolio: PortfolioState,
        being_sold: set[str],
        verplant: float = 0.0,
    ) -> list[Decision]:
        """Stockt bestehende Positionen auf, wenn Kapital ungenutzt liegt.

        Ohne diesen Schritt bleibt bei vollen Positionsplaetzen Kapital
        liegen, bis eine Position ausgestoppt wird, ihr Ziel erreicht oder
        die Haltefrist ablaeuft - gemessen am 2026-07-30 waren das 46 % des
        Depots bei 15 von 15 belegten Plaetzen.

        Aufgestockt wird nur, was BEIDE Bedingungen erfuellt:

          * Die These traegt heute noch wie bei einem Neukauf
            (`score >= min_score`) - nicht nur "faellt nicht mehr".
          * Die Position liegt im Gewinn (`topup_min_gain_pct`).

        Der zweite Punkt ist der wichtige: In eine verlustreiche Position
        nachzukaufen ist Average-Down und macht aus einem begrenzten Verlust
        einen groesseren. Wer die These fuer intakt haelt, darf aufstocken;
        wer den Einstandskurs verbilligen will, betreibt Selbsttaeuschung.

        Stop und Ziel bleiben unveraendert - sie laufen der Position nicht
        hinterher. `bars_held` bleibt ebenfalls stehen, sonst wuerde
        wiederholtes Nachkaufen die Haltefrist aushebeln.
        """
        cfg = self.cfg
        investable = portfolio.equity * cfg.target_invested
        already = sum(
            p.qty * (snapshot.last_price(s) or p.entry_price)
            for s, p in portfolio.positions.items()
            if s not in being_sold
        )
        frei = max(0.0, min(investable - already - verplant,
                            portfolio.cash - verplant))
        mindest = portfolio.equity * cfg.min_position_pct
        if frei < mindest:
            return []

        cap = portfolio.equity * cfg.max_position_pct * cfg.position_size_margin
        gewichte: dict[str, float] = {}
        restluft: dict[str, float] = {}
        info: dict[str, tuple] = {}

        for sym, pos in portfolio.positions.items():
            if sym in being_sold:
                continue
            price = snapshot.last_price(sym)
            if price is None or price <= 0:
                continue
            if pos.unrealized_pct(price) < cfg.topup_min_gain_pct:
                continue

            frame = self._signals(sym, snapshot)
            row = frame.iloc[-1]
            score = float(row.get("score", 0.0))
            if not np.isfinite(score) or score < cfg.min_score:
                continue

            luft = cap - pos.qty * price
            if luft < mindest:
                continue

            gewichte[sym] = kandidatengewicht(
                float(row.get("atr_pct", 0) or 0), score, cfg.groessen_modus)
            restluft[sym] = luft
            info[sym] = (score, row, price, pos)

        if not gewichte:
            return []

        # Nach Score sortieren: Bei knappem Kapital bekommt die staerkste
        # These zuerst etwas ab (verteile_kapital schneidet von hinten ab).
        reihenfolge = sorted(gewichte, key=lambda s: -info[s][0])
        gewichte = {s: gewichte[s] for s in reihenfolge}

        groessen = verteile_kapital(gewichte, frei, restluft, mindest)

        out: list[Decision] = []
        for sym, betrag in groessen.items():
            score, row, price, pos = info[sym]
            gruende = (explain_reversal(row) if cfg.strategy == "reversal"
                       else explain(row, cfg.weights))
            gruende["nachkauf"] = True
            gruende["bestand_vorher"] = round(pos.qty * price, 2)
            gruende["gewinn_pct"] = round(pos.unrealized_pct(price), 4)
            self._mit_kontext(gruende, snapshot, sym)
            out.append(
                Decision(
                    symbol=sym,
                    action="topup",
                    conviction=score,
                    price=price,
                    target_notional=round(betrag, 2),
                    # Stop und Ziel bleiben, wie sie beim Einstieg gesetzt
                    # wurden - der Nachkauf aendert die These nicht.
                    stop_price=pos.stop_price,
                    target_price=pos.target_price,
                    reasons=gruende,
                )
            )
        return out

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
            rang_pct = None
            if cfg.strategy == "ranking":
                info = self._qs.get(sym)
                score = float(info["score"]) if info else float("-inf")
                rang_pct = float(info["pct"]) if info else 0.0
                if not np.isfinite(score):
                    score = -9.0

            verlaengert = False
            reason: str | None = None
            if price <= pos.stop_price:
                reason = "stop_ausgeloest"
            elif price >= pos.target_price:
                reason = "gewinnziel_erreicht"
            elif pos.bars_held >= cfg.max_hold_days:
                # Zwei unabhaengige Verlaengerungsregeln, beide standardmaessig aus:
                #  (1) ranking: `renew_rank_pct` - bleibt, wer noch im Kaufbereich steht
                #      (2026-09-29, gemessen: hilft nicht, Schalter fuer Replays)
                #  (2) `zeitausstieg_dynamisch` - Trendpruefung mit harter Grenze (develop)
                # Die gesamte Sonderbehandlung haengt an den Schaltern. Stehen sie aus,
                # gilt exakt die alte Regel - ohne dass `max_hold_days_hart` gelesen wird
                # (sonst bekaeme eine Position ab Tag 20 das Etikett "zeitausstieg_hart"
                # statt "zeitausstieg" und die Auswertung nach Ausstiegsgruenden waere
                # still verfaelscht).
                if (cfg.strategy == "ranking" and cfg.renew_rank_pct is not None
                        and rang_pct is not None and rang_pct >= cfg.renew_rank_pct):
                    self.__dict__.setdefault("verlaengert_rang", []).append((sym, pos.bars_held))
                elif not cfg.zeitausstieg_dynamisch:
                    reason = "zeitausstieg"
                elif pos.bars_held >= cfg.max_hold_days_hart:
                    # Harte Grenze VOR der Trendpruefung, sonst koennte eine
                    # dauerhaft steigende Position unbegrenzt weiterlaufen.
                    reason = "zeitausstieg_hart"
                elif self._traegt_noch(pos, price, float(row.get("atr", 0) or 0)):
                    verlaengert = True
                else:
                    reason = "zeitausstieg"
            elif cfg.strategy == "ranking":
                # Rangverlust erst nach der Mindesthaltedauer - Hysterese
                # gegen staendiges Tauschen (exit_rank_pct << min_rank_pct).
                if pos.bars_held >= cfg.min_hold_days and rang_pct < cfg.exit_rank_pct:
                    reason = "rangverlust"
            elif score < cfg.exit_score:
                reason = "these_traegt_nicht_mehr"

            # Die Score-Regel gilt AUCH fuer verlaengerte Positionen. Sonst
            # entstuende eine Position, die zwar noch steigt, deren These
            # aber laengst nicht mehr traegt - und die durch die
            # Verlaengerung gegen genau die Regel immun waere, die sie
            # sonst geschlossen haette.
            if verlaengert and score < cfg.exit_score:
                reason = "these_traegt_nicht_mehr"
                verlaengert = False

            if reason:
                out.append(
                    Decision(
                        symbol=sym,
                        action="sell",
                        conviction=score,
                        price=price,
                        target_notional=pos.qty * price,
                        reasons=self._mit_kontext({
                            "ausstiegsgrund": reason,
                            "gewinn_pct": round(pnl, 4),
                            "tage_gehalten": pos.bars_held,
                            "score_jetzt": round(score, 3),
                            "rang_pct": (round(rang_pct, 3) if rang_pct is not None else None),
                            "einstieg": round(pos.entry_price, 4),
                            "stop": round(pos.stop_price, 4),
                            "ziel": round(pos.target_price, 4),
                            # Nur gesetzt, wenn die Frist ueberschritten war -
                            # macht im Protokoll unterscheidbar, ob ein Trade
                            # regulaer oder nach Verlaengerung endete.
                            **({"nach_verlaengerung": True}
                               if pos.bars_held > cfg.max_hold_days else {}),
                        }, snapshot, sym),
                    )
                )
        return out

    @staticmethod
    def _mit_kontext(gruende: dict, snapshot: MarketSnapshot, sym: str) -> dict:
        """Haengt Regime, Sektor und Liquiditaetsdezil an eine Begruendung.

        Beeinflusst die Entscheidung NICHT. Sie wird dadurch im Nachhinein
        zuordenbar: "in welcher Marktlage und bei welcher Werteklasse
        traegt die Strategie?" - die wichtigste offene Frage des Projekts.

        **Warum als eigene Funktion.** Bis zum 22.08.2026 stand dieser
        Block nur in der Kaufschleife. `topup` und `sell` bekamen nichts -
        und `topup` ist mit 110 von 304 Live-Entscheidungen die Mehrheit
        der Kapitalzuteilung (bis zu 9 Nachkaeufe je Symbol, §G2). Eine
        Auswertung der Sektorkonzentration uebersah damit den groesseren
        Teil (§G13 Fund 3). Drei Aufrufstellen mit demselben kopierten
        Block waeren die naechste Gelegenheit, eine davon zu vergessen.

        `reasons` ist ein freies Dictionary, und
        `journal.decision_quality()` gruppiert neue Schluessel automatisch
        nach Wertbaendern - es braucht dafuer keine Schemaaenderung.
        """
        for schluessel, wert in (snapshot.kontext.get(sym) or {}).items():
            gruende[schluessel] = wert
        for schluessel, wert in (snapshot.regime or {}).items():
            gruende[schluessel] = wert
        return gruende

    def _traegt_noch(self, pos: Position, price: float, atr: float) -> bool:
        """Laeuft die Position noch, oder stagniert sie nur?

        Zwei Bedingungen, beide notwendig:

          1. **Im Gewinn.** Eine Position im Minus laenger zu halten, weil
             sie „noch laufen koennte", ist Hoffnung, keine Regel - und
             genau das Muster, das aus einem begrenzten Verlust einen
             grossen macht.
          2. **Nahe am eigenen Hoechststand.** `high_water` wird taeglich
             in `update_position` fortgeschrieben. Faellt der Kurs mehr als
             `trend_rueckfall_atr` x ATR darunter zurueck, ist der Trend
             gebrochen - dann wird die aufgeschobene Frist sofort wirksam.

        Der Abstand skaliert mit der Volatilitaet des Wertes: Ein ruhiger
        Wert darf weniger zurueckfallen als ein unruhiger, bevor das als
        Trendbruch gilt. Ein fester Prozentsatz waere hier falsch - siehe
        die Messung im Docstring von `trend_rueckfall_atr`.

        Fehlt der ATR (0 oder nicht berechenbar), gilt die Position als
        NICHT mehr tragend: Ohne Volatilitaetsmass laesst sich Rauschen
        nicht von einer Trendwende unterscheiden, und im Zweifel gilt die
        urspruengliche Regel - verkaufen. Eine Verlaengerung ist eine
        Ausnahme und muss positiv begruendet sein, nicht durch fehlende
        Daten entstehen.

        Bewusst KEINE Bedingung auf den Score: Der misst „ist der Wert
        ueberverkauft", also die Einstiegs-These. Nach einem erfolgreichen
        Anstieg ist ein Umkehr-Kandidat definitionsgemaess nicht mehr
        ueberverkauft - der Score MUSS also fallen. Ihn hier zu verlangen
        hiesse, die Verlaengerung genau dann zu verweigern, wenn sie
        funktioniert hat. Die Score-Untergrenze (`exit_score`) greift
        weiterhin separat.
        """
        if pos.entry_price <= 0 or price <= pos.entry_price:
            return False
        if atr <= 0:
            return False
        hoechst = max(pos.high_water or pos.entry_price, price)
        return (hoechst - price) <= self.cfg.trend_rueckfall_atr * atr

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
        if cfg.max_new_per_day is not None:
            slots = min(slots, int(cfg.max_new_per_day))
        if slots <= 0:
            return []

        # Alle Kandidaten bewerten und in eine Rangliste bringen.
        candidates: list[tuple[str, float, pd.Series, float]] = []
        if cfg.strategy == "ranking":
            # Kandidaten kommen aus dem Querschnitt: nur oberstes Perzentil,
            # Zulassung (Regime, Kurs, Umsatz) ist dort bereits geprueft.
            for sym, info in self._qs.items():
                if sym in held or sym in blocked or sym in portfolio.positions:
                    continue
                if info["pct"] < cfg.min_rank_pct or not np.isfinite(info["score"]):
                    continue
                price = snapshot.last_price(sym)
                if price is None or price < cfg.min_price:
                    continue
                row = info["row"].copy()
                row["score"] = info["score"]
                row["rang_pct"] = info["pct"]
                candidates.append((sym, float(info["score"]), row, price))
        else:
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
        cap = portfolio.equity * cfg.max_position_pct * cfg.position_size_margin
        mindest = portfolio.equity * cfg.min_position_pct

        # Bei `deploy_to_target` wird das freie Kapital vorab auf alle
        # Kandidaten verteilt (Wasserfuellung), damit `target_invested`
        # tatsaechlich erreicht wird. Sonst gilt der bisherige Weg, bei dem
        # die Volatilitaets-Skalierung absolut wirkt und nur verkleinern kann.
        verteilt: dict[str, float] = {}
        if cfg.deploy_to_target:
            verteilt = verteile_kapital(
                {sym: kandidatengewicht(float(row.get("atr_pct", 0) or 0), _score,
                                        "gleich" if cfg.sizing == "gleich" else cfg.groessen_modus)
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

            stop_abstand = cfg.stop_atr
            if cfg.stop_atr_modellphase is not None and self.__dict__.get("_modell_phase"):
                stop_abstand = cfg.stop_atr_modellphase
            stop = price - stop_abstand * atr if atr > 0 else price * 0.90
            target = price + cfg.target_atr * atr if atr > 0 else price * 1.25

            if cfg.strategy == "reversal":
                reasons = explain_reversal(row)
            elif cfg.strategy == "ranking":
                reasons = explain_ranking(row, score, float(row.get("rang_pct", 0.0)))
            else:
                reasons = explain(row, cfg.weights)
            reasons["rang"] = len(out) + 1
            reasons["stop_abstand_pct"] = round(1 - stop / price, 4)
            reasons["ziel_abstand_pct"] = round(target / price - 1, 4)

            # Auswertungsschluessel - beeinflussen die Entscheidung NICHT,
            # machen sie aber im Nachhinein zuordenbar. `reasons` ist ein
            # freies Dictionary, und `journal.decision_quality()` gruppiert
            # neue Schluessel automatisch nach Wertbaendern - es braucht
            # dafuer keine Schemaaenderung.
            reasons["kandidaten_gesamt"] = len(candidates)
            # `dollar_volume` steht in der Kurszeile und wird oben bereits
            # fuer die Liquiditaetsschwelle gelesen - nur nie protokolliert.
            # `shadow.py:1064` erwartet es unter genau diesem Namen und
            # schrieb deshalb seit jeher NULL: 0 von 12.250 Vorhersagen
            # hatten eine Liquiditaetsangabe (§G15). Damit war die Frage
            # "entsteht der Vorsprung nur bei illiquiden Werten?" nicht
            # beantwortbar - eine der wenigen echten Auswertungsachsen.
            reasons["dollar_volume"] = round(float(row.get("dollar_volume", 0) or 0), 2)
            self._mit_kontext(reasons, snapshot, sym)

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
