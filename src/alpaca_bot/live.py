"""Live-Betrieb: baut die Momentaufnahme aus dem echten Konto.

Das Gegenstueck zu `simulate.py`. Beide bauen einen `MarketSnapshot` und
einen `PortfolioState` und rufen damit **dieselbe** `Engine.decide()`.
Der Unterschied liegt ausschliesslich in der Herkunft der Daten:

    simulate.py  ->  Historie, bei Tag T abgeschnitten
    live.py      ->  aktueller Stand von Alpaca

Damit ist sichergestellt, dass im Depot genau die Logik handelt, die
vorher auf der Historie geprueft wurde. Weicht das Ergebnis ab, kann es
nur an Ausfuehrung und Kosten liegen - und die misst
`journal.slippage_report()`.

Hier laufen die Kursdaten bewusst ueber Alpaca und nicht ueber eine freie
Quelle: Gehandelt wird bei Alpaca, also muss auch zu Alpaca-Kursen
entschieden werden. Fuer Forschung gilt das Gegenteil (siehe
`datasources.py`).
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from . import account, compliance, data, risiko, trading
from .engine import Decision, Engine, EngineConfig, MarketSnapshot, PortfolioState, Position
from .journal import Journal


@dataclass
class LiveResult:
    decisions: list[Decision]
    """ALLE Entscheidungen der Engine - auch die, die nicht ausgefuehrt wurden."""
    executed_decisions: list[Decision]
    """Nur die tatsaechlich abgeschickten. Ausschliesslich diese duerfen den
    gespeicherten Zustand veraendern.

    Der Unterschied ist nicht kosmetisch: Die Engine schlaegt oft mehr
    Kaeufe vor, als `max_new_positions` zulaesst. Wer die volle Liste zum
    Fortschreiben des Zustands nimmt, legt Metadaten fuer Positionen an,
    die nie eroeffnet wurden - und der Bot haelt sich nach einem Neustart
    fuer investiert, ohne es zu sein."""
    executed: int
    blocked: int
    dry_run: bool
    equity: float


MARKET_SYMBOL = "SPY"


def build_snapshot(
    symbols: list[str], lookback_days: int = 500, verbose: bool = False
) -> MarketSnapshot:
    """Holt die aktuelle Marktlage als Momentaufnahme.

    `as_of` ist der letzte VOLLSTAENDIGE Handelstag. Der laufende Tag wird
    bewusst ausgeschlossen: Eine unfertige Tagesbar taeuscht Signale vor,
    die sich bis Handelsschluss noch aendern - im Backtest gab es diesen
    Zwischenzustand nie.

    SPY wird immer mitgeladen. Die Umkehr-Strategie braucht es fuer den
    Markt-Regime-Filter, und die Simulation reicht es ebenfalls durch -
    fehlte es hier, liefe live ohne Filter, was ein anderes Verhalten
    waere als das geprueft wurde.
    """
    requested = list(dict.fromkeys([*symbols, MARKET_SYMBOL]))

    # In Bloecken laden: ein einzelner Request ueber tausende Symbole
    # sprengt die URL-Laenge. Die Drossel in data.get_bars zaehlt jeden
    # Block einzeln, das Kontingent bleibt also gewahrt.
    batch = 300
    if len(requested) <= batch:
        bars = data.get_bars(requested, "1D", lookback_days=lookback_days)
    else:
        frames = []
        for i in range(0, len(requested), batch):
            part = data.get_bars(
                requested[i : i + batch], "1D", lookback_days=lookback_days
            )
            if not part.empty:
                frames.append(part)
            if verbose:
                print(f"      Daten: {i + batch if i + batch < len(requested) else len(requested)}"
                      f"/{len(requested)} Symbole")
        bars = pd.concat(frames).sort_index() if frames else pd.DataFrame()
    if bars.empty:
        raise RuntimeError("Keine Marktdaten erhalten.")

    clock = account.market_clock()
    per_symbol: dict[str, pd.DataFrame] = {}
    for sym in bars.index.get_level_values("symbol").unique():
        df = bars.xs(sym, level="symbol").sort_index()
        # Bei offener Boerse die heutige, noch unfertige Bar verwerfen.
        if clock["is_open"] and len(df) > 0:
            today = pd.Timestamp.now(tz="UTC").normalize()
            if pd.Timestamp(df.index[-1]).normalize() >= today:
                df = df.iloc[:-1]
        if len(df) >= 260:
            per_symbol[sym] = df

    if not per_symbol:
        raise RuntimeError(
            "Kein Symbol mit ausreichender Historie (mindestens 260 Bars)."
        )

    as_of = max(pd.Timestamp(df.index[-1]) for df in per_symbol.values())
    if as_of.tz is None:
        as_of = as_of.tz_localize("UTC")

    # SPY dient nur als Regime-Referenz und ist selbst kein Handelskandidat.
    market_df = per_symbol.pop(MARKET_SYMBOL, None) if MARKET_SYMBOL not in symbols else per_symbol.get(MARKET_SYMBOL)
    market = market_df["close"] if market_df is not None else None
    if market is None:
        raise RuntimeError(
            f"{MARKET_SYMBOL} nicht ladbar - ohne Marktreferenz waere der "
            "Regime-Filter inaktiv und das Live-Verhalten wiche von der "
            "Simulation ab."
        )

    # --- Nachrichten fuer die Signalberechnung (Faktor ReversalWeights.news) ---
    # EIN Abruf fuer alle Symbole (news.get_news nimmt eine Liste und
    # paginiert selbst), nicht 1200 Einzelabrufe. Defensiv: ein Ausfall der
    # News-API darf niemals den Handelslauf verhindern - der Bot faehrt
    # dann einfach ohne den Nachrichtenfaktor fort (siehe ReversalWeights.news).
    news_df = None
    try:
        from . import news as news_mod

        start = (as_of - pd.Timedelta(days=90)).strftime("%Y-%m-%d")
        news_df = news_mod.get_news(
            list(per_symbol), start=start, end=as_of.strftime("%Y-%m-%d"),
            max_articles=5_000,
        )
        if verbose:
            print(f"      Nachrichten: {len(news_df)} Artikel geladen")
    except Exception as e:  # noqa: BLE001
        if verbose:
            print(f"      Nachrichten nicht ladbar ({type(e).__name__}) - "
                  "Bot faehrt ohne Nachrichtenfaktor fort.")
        news_df = None

    if verbose:
        print(f"      Stichtag: {as_of.date()} | {len(per_symbol)} Symbole "
              f"| Marktfilter: {MARKET_SYMBOL}")
    return MarketSnapshot(as_of=as_of, bars=per_symbol, market=market, news=news_df)


def build_portfolio(snapshot: MarketSnapshot) -> PortfolioState:
    """Liest Kontostand und Positionen - Broker plus gespeicherter Zustand.

    Aufgabenteilung:
        Alpaca        welche Positionen es gibt, Stueckzahl, Einstand
        state.sqlite  Stop, Ziel, Einstiegsdatum, Hoechststand

    Beides ist noetig. Alpaca kennt Stop und Ziel nicht, und ohne sie
    kaeme die Engine bei jedem Lauf zu anderen Ausstiegsentscheidungen
    als in der Simulation.

    `bars_held` wird aus dem Einstiegsdatum in Handelstagen berechnet.
    Ohne diesen Wert wuerde der Zeitausstieg nach `max_hold_days` nie
    ausloesen und Positionen liefen unbegrenzt weiter - der Backtest
    haette dann eine Haltedauer simuliert, die es live nicht gibt.
    """
    from .state import Store

    acct = account.account_summary()
    pos_df = account.positions()
    stored = Store().load_positions()
    today = pd.Timestamp.now(tz="UTC").normalize()

    positions: dict[str, Position] = {}
    for sym, row in pos_df.iterrows():
        if float(row["qty"]) <= 0:
            continue
        entry = float(row["avg_entry"])
        current = float(row.get("current_price") or entry)
        meta = stored.get(sym)

        if meta:
            entry_date = pd.Timestamp(meta["entry_date"])
            if entry_date.tz is None:
                entry_date = entry_date.tz_localize("UTC")
            stop = float(meta["stop_price"])
            target = float(meta["target_price"])
            high_water = max(current, float(meta["high_water"]))
        else:
            # Position ohne gespeicherten Zustand (manuell gekauft oder
            # Datenbank verloren): konservativ ergaenzen statt ignorieren.
            entry_date = today
            stop, target = entry * 0.93, entry * 1.10
            high_water = max(entry, current)

        held = int(len(pd.bdate_range(entry_date.normalize(), today)) - 1)

        positions[sym] = Position(
            symbol=sym,
            qty=float(row["qty"]),
            entry_price=entry,
            entry_date=entry_date,
            stop_price=stop,
            target_price=target,
            bars_held=max(0, held),
            high_water=high_water,
        )

    return PortfolioState(
        cash=float(acct["cash"]),
        equity=float(acct["portfolio_value"]),
        positions=positions,
        day_trades_used=int(acct.get("daytrade_count") or 0),
    )


@dataclass
class Referenzpreis:
    """Preis samt Herkunft - die Herkunft entscheidet, ob eine Zeile spaeter
    als echte Ausfuehrungsmessung zaehlen darf oder nur eine Notloesung ist.
    """

    preis: float
    quelle: str
    """'quote'           = echte Bid/Ask-Quote von Alpaca verwendet, gegen
                           den letzten Trade geprueft und plausibel.
    'quote_verworfen'   = die Bid/Ask-Quote wich zu stark vom letzten echten
                           Trade ab (siehe `_MAX_QUOTE_ABWEICHUNG`) - `preis`
                           ist dann der letzte Trade, nicht die Quote. Live
                           beobachtet bei SIMO und KGS am 04.08.2026: die
                           Quote lag 11-14 % neben Entscheidungskurs UND
                           Fuellpreis, waehrend Minutenbars zur selben Zeit
                           den tatsaechlichen Kurs exakt beim Fuellpreis
                           zeigten - die Quote selbst war fehlerhaft, keine
                           reale Bewegung.
    'fallback'          = keine gueltige Quote verfuegbar (IEX-Ausfall, Symbol
                           nicht abrufbar) - `preis` ist der Entscheidungskurs,
                           keine Marktbeobachtung. Eine Zeile mit dieser
                           Herkunft misst Kursdrift seit der Entscheidung,
                           nicht Slippage - genau die Vermischung, vor der
                           dieses Modul warnt (siehe unten).

    `journal.slippage_report()` schliesst nur 'fallback' aus dem Mittelwert
    aus - 'quote_verworfen' beruht auf einem echten Trade und zaehlt daher
    mit, zeigt seine Zahl aber gesondert an."""


_MAX_QUOTE_ABWEICHUNG = 0.02
"""Ab welcher Abweichung vom letzten echten Trade gilt eine Bid/Ask-Quote
als unglaubwuerdig - NICHT die Schwelle gegen den Entscheidungskurs (siehe
Docstring von `_reference_price`).

Am 04.08.2026 mit 5 % eingefuehrt und an den beiden schlimmsten Faellen
(SIMO/KGS, 11-14 % Abweichung) geeicht. Die Nachmessung nach 11 Tagen
Betrieb zeigte, dass das zu grob war: 13 Quotes wurden korrekt
abgefangen, aber ACHT weitere Ausreisser ueber 200 bps rutschten durch -
alle mit einer Abweichung zwischen 2,1 % und 4,9 %, also knapp unter der
Schwelle (MUSA 4,9 %, FICO 4,9 %, CTVA 4,7 %, MAR 4,0 %, PFGC 4,0 %,
POST 3,9 %, MAR 2,9 %, APP 2,1 %).

2 % ist bewusst streng: Zwischen Quote und letztem Trade liegen Sekunden.
Eine ECHTE Kursbewegung von ueber 2 % in Sekunden ist bei den hier
gehandelten liquiden Werten die Ausnahme, eine veraltete IEX-Quote die
Regel. Der Preis eines Fehlalarms ist zudem gering: Verworfen wird die
Quote zugunsten des letzten Trades - ebenfalls ein echter Marktpreis,
nur Sekunden alt. Es geht also nie um "Messung oder keine Messung",
sondern nur darum, welcher von zwei echten Kursen die Referenz ist."""


def _quote_plausibel(symbol: str, kandidat: float) -> tuple[bool, float | None]:
    """Prueft eine Quote gegen den letzten TATSAECHLICH gehandelten Kurs.

    Der Entscheidungskurs taugt als Massstab nicht: Ein Kandidat dieser
    Strategie ist per Definition ein Wert, der gerade stark gefallen ist -
    eine Abweichung von 15-20 % zum Vortagesschluss ist hier normaler
    Alltag, kein Datenfehler (siehe SAIA: 342-362 $ Intraday-Spanne an
    einem einzigen Tag, real, kein Bug). Eine Schwelle dagegen wuerde genau
    die grossen, echten Ausfuehrungsrisiken verstecken, die diese Messung
    aufdecken soll.

    Der letzte Trade dagegen ist eine ECHTE, zeitgleiche Marktbeobachtung -
    keine Erwartung, sondern ein Faktum. Weicht die Quote davon um mehr als
    `_MAX_QUOTE_ABWEICHUNG` ab, ist mit hoher Wahrscheinlichkeit die Quote
    fehlerhaft, nicht der Markt in Bewegung.

    Live beobachtet am 04.08.2026: SIMO-Verkauf mit Quote 225.32 $, obwohl
    Minutenbars zur selben Zeit Trades um 261-262 $ zeigen (Fuellpreis
    261.00 $, exakt im Bereich der echten Trades). KGS-Verkauf mit Quote
    50.67 $ gegen echte Trades um 59.0-59.4 $ (Fuellpreis 59.02 $). In
    beiden Faellen lag NUR die Bid/Ask-Quote daneben - nicht der
    Entscheidungskurs, nicht der Fuellpreis. Der IEX-Feed sieht nur ~2 %
    des US-Handelsvolumens; bei duenn gehandelten Werten wird die Quote
    dadurch gelegentlich unzuverlaessig, obwohl echte Trades korrekt
    durchkommen.
    """
    try:
        snap = data.snapshots(symbol)
        last = float(snap.loc[symbol, "last"] or 0)
    except Exception:  # noqa: BLE001 - Cross-Check darf keine Order verhindern
        return True, None
    if last <= 0 or kandidat <= 0:
        return True, None
    abweichung = abs(kandidat - last) / last
    return abweichung <= _MAX_QUOTE_ABWEICHUNG, last


def _reference_price(symbol: str, side: str, fallback: float) -> Referenzpreis:
    """Der Kurs, den man im Moment der Order realistisch bekommen konnte.

    DAS ist die richtige Bezugsgroesse fuer Slippage - nicht der Kurs, auf
    dem die Entscheidung beruhte. Entschieden wird auf dem Schlusskurs des
    Vortages; bis zur Ausfuehrung koennen Stunden und mehrere Prozent
    liegen. Wer den Entscheidungskurs als Referenz nimmt, misst die
    Marktbewegung ueber Nacht und nennt sie Slippage.

    Genau dieser Fehler hat zuvor Werte wie -2452 Basispunkte erzeugt und
    die gesamte Ausfuehrungsauswertung unbrauchbar gemacht.

    Kauf laeuft ueber den Briefkurs, Verkauf ueber den Geldkurs - was
    darueber hinaus verloren geht, ist echte Slippage.

    Jede so gewonnene Quote wird zusaetzlich gegen den letzten echten
    Trade geprueft (`_quote_plausibel`) - eine Bid/Ask-Quote kann auf dem
    IEX-Feed veraltet oder fehlerhaft sein, auch wenn beide Seiten formal
    gueltige (>0) Werte liefern.
    """
    try:
        q = data.latest_quotes(symbol)
        ask = float(q.loc[symbol, "ask"] or 0)
        bid = float(q.loc[symbol, "bid"] or 0)

        kandidat: float | None = None
        if side == "buy" and ask > 0:
            kandidat = ask
        elif side == "sell" and bid > 0:
            kandidat = bid
        # Die gewuenschte Seite fehlt (haeufig vorboerslich bei duenn
        # gehandelten Werten ueber den IEX-Feed - Ask oft 0.0). Ein
        # Mittelwert aus einer echten und einer fehlenden Seite waere KEIN
        # Mittelwert, sondern eine Verfaelschung um bis zu 50 %: (0+45.54)/2
        # ergibt 22.77 und meldet einen Kurssturz, der nie stattfand. Bei
        # einer fehlenden Seite gilt die vorhandene als bester verfuegbarer
        # Schaetzwert, echte Mittelwertbildung nur wenn BEIDE gueltig sind.
        elif ask > 0 and bid > 0:
            kandidat = (ask + bid) / 2
        elif ask > 0:
            kandidat = ask
        elif bid > 0:
            kandidat = bid

        if kandidat is not None:
            plausibel, letzter_trade = _quote_plausibel(symbol, kandidat)
            if plausibel or letzter_trade is None:
                return Referenzpreis(kandidat, "quote")
            return Referenzpreis(letzter_trade, "quote_verworfen")
    except Exception:  # noqa: BLE001 - Quote-Ausfall darf keine Order verhindern
        pass
    return Referenzpreis(float(fallback), "fallback")


def _nachkauf_im_zustand(d: Decision, fill_schaetzung: float) -> None:
    """Schreibt den gespeicherten Zustand nach einem Nachkauf fort.

    Zwei Dinge muessen hier zusammenpassen, sonst verfaelscht der Nachkauf
    die Ausstiegsregeln:

    1. **Der gespeicherte Einstand wird auf den neuen Mischkurs gesetzt.**
       Nicht aus Buchhaltungsliebe, sondern weil `daemon.recover()` bei einer
       Abweichung von ueber 0,5 % zwischen gespeichertem und Broker-Einstand
       Stop UND Ziel proportional neu skaliert. Nach einem Nachkauf aendert
       sich der Broker-Einstand zwangslaeufig - ohne diese Zeile wuerde
       `recover()` die Marken beim naechsten Start verschieben, obwohl sich
       an der These nichts geaendert hat.

    2. **Stop, Ziel, Einstiegsdatum und `bars_held` bleiben unveraendert.**
       Der Nachkauf verstaerkt eine bestehende These, er stellt keine neue
       auf. Wuerde `bars_held` zuruecksetzen, liesse sich die Haltefrist
       durch wiederholtes Nachkaufen beliebig verlaengern.
    """
    from .state import Store

    store = Store()
    meta = store.load_positions().get(d.symbol)
    if not meta:
        return

    alt_wert = float(d.reasons.get("bestand_vorher", 0) or 0)
    neu_wert = float(d.target_notional)
    alt_einstand = float(meta["entry_price"])
    if alt_wert <= 0 or alt_einstand <= 0 or fill_schaetzung <= 0:
        return

    # Mischkurs ueber die STUECKZAHLEN, nicht ueber die Betraege.
    alt_stueck = alt_wert / float(d.price) if d.price else 0.0
    neu_stueck = neu_wert / fill_schaetzung
    if alt_stueck + neu_stueck <= 0:
        return
    misch = ((alt_stueck * alt_einstand + neu_stueck * fill_schaetzung)
             / (alt_stueck + neu_stueck))

    store.save_position(
        d.symbol,
        entry_price=misch,
        entry_date=meta["entry_date"],          # unveraendert
        stop_price=float(meta["stop_price"]),   # unveraendert
        target_price=float(meta["target_price"]),
        high_water=max(float(meta["high_water"]), float(d.price)),
        bars_held=int(meta["bars_held"] or 0),  # NICHT zuruecksetzen
        entry_score=meta["entry_score"],
        reasons={"nachkauf": f"+${neu_wert:,.0f}, Einstand "
                             f"{alt_einstand:.2f} -> {misch:.2f}"},
    )


def reconcile_fills(lookback_hours: int = 48) -> int:
    """Traegt die tatsaechlichen Ausfuehrungspreise ins Protokoll nach.

    Eine Market-Order ist beim Absenden noch nicht ausgefuehrt - der
    Fuellpreis steht erst Sekunden bis Minuten spaeter fest. Deshalb wird
    er nicht beim Senden, sondern beim naechsten Durchgang nachgetragen.

    Ohne diesen Schritt bleibt `journal.slippage_report()` leer, und die
    wichtigste Frage des Papierbetriebs waere nicht zu beantworten: Wie
    weit weicht die echte Ausfuehrung von der im Backtest angenommenen ab?
    """
    import datetime as dt

    from .journal import Journal

    j = Journal()
    open_orders = j.table("orders", "dry_run = 0 AND fill_price IS NULL")
    if open_orders.empty:
        return 0

    # `since` deckt mindestens `lookback_hours` ab, wird aber nie enger als
    # noetig, um die AELTESTE noch offene Order zu erfassen. Ein starres
    # 48h-Fenster liess Orders, die aus irgendeinem Grund (Absturz,
    # ausbleibender Zyklus) laenger offen blieben, UNWIDERRUFLICH ohne
    # Fuellpreis zurueck - der Broker haelt die Order laengst nicht mehr im
    # 48h-Fenster vor, obwohl er sie kennt. Beobachtet am 03.08.2026: 5
    # Orders zwischen 64 und 132 Stunden alt, nie abgeglichen.
    import pandas as pd

    since = dt.datetime.now(dt.UTC) - dt.timedelta(hours=lookback_hours)
    ts = pd.to_datetime(open_orders["ts"], format="mixed", utc=True, errors="coerce")
    if ts.notna().any():
        oldest = ts.min().to_pydatetime() - dt.timedelta(hours=1)
        since = min(since, oldest)

    broker = account.orders(status="closed", limit=500, after=since)
    if broker.empty:
        return 0

    fills = {
        str(r["id"]): float(r["filled_avg_price"])
        for _, r in broker.iterrows()
        if r.get("filled_avg_price")
    }

    updated = 0
    with j._conn() as c:
        for _, o in open_orders.iterrows():
            price = fills.get(str(o["order_id"]))
            if price is None:
                continue
            sign = -1.0 if o["side"] == "sell" else 1.0

            slip = None
            if o.get("expected_price"):
                expected = float(o["expected_price"])
                if expected > 0:
                    slip = sign * (price - expected) / expected * 10_000

            drift = None
            if o.get("decision_price"):
                dp = float(o["decision_price"])
                if dp > 0:
                    drift = sign * (price - dp) / dp * 10_000

            c.execute(
                "UPDATE orders SET fill_price = ?, slippage_bps = ?,"
                " decision_drift_bps = ? WHERE order_id = ?",
                (price, slip, drift, o["order_id"]),
            )
            updated += 1
    return updated


def run_once(
    symbols: list[str],
    engine_config: EngineConfig | None = None,
    *,
    dry_run: bool = True,
    max_new_positions: int = 3,
    verbose: bool = True,
) -> LiveResult:
    """Ein vollstaendiger Durchlauf: Lage erfassen, entscheiden, handeln.

    `dry_run=True` ist Standard - es wird nichts gesendet, nur angezeigt.
    `max_new_positions` begrenzt, wie viele Kaeufe ein einzelner Lauf
    ausloesen darf. Schutz gegen den Fall, dass ein Fehler in der Logik das
    Depot in einem Durchgang umbaut.
    """
    cfg = engine_config or EngineConfig()
    engine = Engine(cfg)
    journal = Journal()

    # Die vollstaendigen Regeln des Laufs mitschreiben, nicht nur ein paar
    # Eckwerte. Ohne sie laesst sich spaeter nicht pruefen, ob eine
    # Entscheidung den DAMALS geltenden Regeln entsprach - Parameter
    # aendern sich, und ein Abgleich gegen die heutige Konfiguration
    # wuerde alte Entscheidungen faelschlich als Regelbruch ausweisen.
    with journal.run("live_trade", config={
        "symbole": len(symbols), "dry_run": dry_run,
        "max_neue_positionen": max_new_positions,
        # Ueber as_dict(), damit neu hinzukommende Regeln automatisch
        # mitprotokolliert werden. Eine handgepflegte Liste haette sonst
        # still Luecken - und genau die Regel, die nicht mitgeschrieben
        # wird, kann der Regelabgleich spaeter nicht pruefen.
        **cfg.as_dict(),
    }) as run:
        # --- 1. Broker-Regeln zuerst ---
        status = compliance.check_account()
        run.log("compliance", ok=status.ok, equity=status.equity,
                daytrades=status.day_trades_used)
        if verbose:
            print(str(status))
        if not status.ok:
            run.warn("Handel blockiert", gruende=status.blocks)
            return LiveResult([], [], 0, 0, dry_run, status.equity)

        # --- 2. Lage erfassen ---
        # Sektoren fuer die Klumpenkontrolle des Risiko-Dachs. Einmal je
        # Lauf, aus dem dauerhaften Cache - ohne sie kann `risiko` nicht
        # pruefen, ob das Depot in einem Sektor klumpt. Ein Ausfall darf
        # den Handel nicht stoppen; dann entfaellt nur diese eine Regel.
        try:
            from . import universe as _uni

            sektoren = _uni.sektoren(sorted({*symbols, *[
                s for s in account.positions().index
            ]}), verbose=False)
        except Exception as e:  # noqa: BLE001
            if verbose:
                print(f"      Sektoren nicht ladbar ({type(e).__name__}) - "
                      "Klumpenkontrolle entfaellt fuer diesen Lauf.")
            sektoren = None

        snapshot = build_snapshot(symbols, verbose=verbose)
        portfolio = build_portfolio(snapshot)
        run.log("lage", stichtag=str(snapshot.as_of.date()),
                symbole=len(snapshot.bars), kapital=portfolio.equity,
                positionen=len(portfolio.positions))

        if verbose:
            print(f"\n      Kapital ${portfolio.equity:,.2f} | "
                  f"Cash ${portfolio.cash:,.2f} | "
                  f"Positionen {len(portfolio.positions)}")

        # --- 3. Entscheiden (IDENTISCHER Aufruf wie in der Simulation) ---
        decisions = engine.decide(snapshot, portfolio)
        sells = [d for d in decisions if d.action == "sell"]
        buys = [d for d in decisions if d.action == "buy"][:max_new_positions]
        # Nachkaeufe zaehlen NICHT gegen `max_new_positions`: Diese Grenze
        # begrenzt, wie viele neue Thesen ein Lauf aufmacht. Ein Nachkauf
        # eroeffnet keine neue These, er verstaerkt eine bestehende - und
        # jede einzelne bleibt durch `max_position_pct` gedeckelt.
        topups = [d for d in decisions if d.action == "topup"]

        if verbose:
            print(f"\n      {len(sells)} Verkaeufe, {len(buys)} Kaeufe "
                  f"(von {len([d for d in decisions if d.action == 'buy'])} moeglichen)"
                  + (f", {len(topups)} Nachkaeufe" if topups else ""))

        executed = blocked = 0
        done: list[Decision] = []

        # --- 4. Erst verkaufen (macht Kapital frei), dann kaufen ---
        for d in sells:
            did = run.decision(d.symbol, "sell", reasons=d.reasons,
                               conviction=d.conviction, price=d.price,
                               strategy="engine")
            if verbose:
                print(f"      VERKAUF {d.symbol:<6} "
                      f"({d.reasons.get('ausstiegsgrund', '?')}, "
                      f"{d.reasons.get('gewinn_pct', 0):+.1%})")
            try:
                ref = _reference_price(d.symbol, "sell", fallback=d.price)
                res = trading.close_position(d.symbol, dry_run=dry_run)
                run.order(did, symbol=d.symbol, side="sell",
                          status=res.status,
                          # NIEMALS "dry-run" als order_id durchreichen:
                          # OrderResult.id ist im Trockenlauf immer dieser
                          # feste String. Da orders.order_id PRIMARY KEY ist
                          # und journal.order() mit INSERT OR REPLACE
                          # schreibt, wuerde jede weitere Dry-Run-Order die
                          # vorherige mit identischer ID stillschweigend
                          # ueberschreiben - nur die letzte haette ueberlebt.
                          # None laesst journal.order() eine eindeutige
                          # lokale ID erzeugen, wie es schon immer fuer
                          # NICHT gesetzte IDs vorgesehen war.
                          order_id=(res.id if not dry_run else None),
                          dry_run=dry_run, expected_price=ref.preis,
                          referenz_quelle=ref.quelle, decision_price=d.price)
                done.append(d)
                executed += 0 if dry_run else 1
            except Exception as e:  # noqa: BLE001
                run.error(f"Verkauf {d.symbol} fehlgeschlagen: {e}")
                blocked += 1

        for d in buys:
            did = run.decision(d.symbol, "buy", reasons=d.reasons,
                               conviction=d.conviction, price=d.price,
                               strategy="engine")
            if verbose:
                print(f"      KAUF    {d.symbol:<6} ${d.target_notional:>9,.2f}  "
                      f"Score {d.conviction:.3f}  "
                      f"Stop {d.stop_price:.2f} Ziel {d.target_price:.2f}")
            try:
                compliance.assert_can_trade(d.symbol, "buy")
                # Risiko-Dach je Order: Die Kontopruefung zu Beginn des
                # Laufs kennt die geplanten Kaeufe noch nicht. Erst hier
                # steht fest, wie hoch Exposure und Cash-Quote NACH dieser
                # Order waeren - und genau das ist die Frage.
                frei = risiko.pruefe_order(d.symbol, "buy", d.target_notional,
                                           sektoren=sektoren)
                if not frei.ok:
                    if verbose:
                        print(f"              -> Risiko-Dach: "
                              f"{'; '.join(frei.gruende)}")
                    run.decision(d.symbol, "buy", reasons=d.reasons,
                                 conviction=d.conviction, price=d.price,
                                 strategy="engine",
                                 blocked_by=f"Risikodach: {'; '.join(frei.gruende)[:200]}")
                    blocked += 1
                    continue
                ref = _reference_price(d.symbol, "buy", fallback=d.price)
                res = trading.market_order(
                    d.symbol, notional=round(d.target_notional, 2),
                    side="buy", dry_run=dry_run,
                )
                run.order(did, symbol=d.symbol, side="buy",
                          status=res.status,
                          # NIEMALS "dry-run" als order_id durchreichen:
                          # OrderResult.id ist im Trockenlauf immer dieser
                          # feste String. Da orders.order_id PRIMARY KEY ist
                          # und journal.order() mit INSERT OR REPLACE
                          # schreibt, wuerde jede weitere Dry-Run-Order die
                          # vorherige mit identischer ID stillschweigend
                          # ueberschreiben - nur die letzte haette ueberlebt.
                          # None laesst journal.order() eine eindeutige
                          # lokale ID erzeugen, wie es schon immer fuer
                          # NICHT gesetzte IDs vorgesehen war.
                          order_id=(res.id if not dry_run else None),
                          notional=d.target_notional, dry_run=dry_run,
                          expected_price=ref.preis, referenz_quelle=ref.quelle,
                          decision_price=d.price)
                done.append(d)
                executed += 0 if dry_run else 1
            except (trading.RiskError, compliance.ComplianceError) as e:
                if verbose:
                    print(f"              -> blockiert: {e}")
                run.decision(d.symbol, "buy", reasons=d.reasons,
                             conviction=d.conviction, price=d.price,
                             strategy="engine", blocked_by=type(e).__name__)
                blocked += 1
            except Exception as e:  # noqa: BLE001
                run.error(f"Kauf {d.symbol} fehlgeschlagen: {e}")
                blocked += 1

        # --- 5. Nachkaeufe in bestehende Positionen ---
        for d in topups:
            did = run.decision(d.symbol, "topup", reasons=d.reasons,
                               conviction=d.conviction, price=d.price,
                               strategy="engine")
            if verbose:
                print(f"      NACHKAUF {d.symbol:<5} ${d.target_notional:>9,.2f}  "
                      f"Score {d.conviction:.3f}  "
                      f"(Bestand ${d.reasons.get('bestand_vorher', 0):,.0f}, "
                      f"Gewinn gestern {d.reasons.get('gewinn_pct', 0):+.1%})")
            try:
                # Sicherheitscheck ZUM AUSFUEHRUNGSZEITPUNKT, nicht nur bei
                # der Entscheidung: Entschieden wird auf dem Schlusskurs von
                # gestern, ausgefuehrt zur heutigen Eroeffnung. Dazwischen
                # kann eine Kursluecke einen gestrigen Gewinner in einen
                # heutigen Verlierer verwandeln - beobachtet bei CHRW: +2,1 %
                # beim Schlusskurs, aber -5,4 % nach einer Eroeffnungsluecke
                # von -6,8 %. Reversal-Kandidaten sind per Definition volatil,
                # dieses Risiko ist hier groesser als bei ruhigen Werten. Die
                # Kernzusage "nie in einen Verlierer nachkaufen" muss deshalb
                # auch HIER gelten, nicht nur gestern Abend.
                ref = _reference_price(d.symbol, "buy", fallback=d.price)
                pos = portfolio.positions.get(d.symbol)
                if pos is not None and pos.entry_price > 0:
                    gewinn_jetzt = ref.preis / pos.entry_price - 1
                    if gewinn_jetzt < cfg.topup_min_gain_pct:
                        if verbose:
                            print(f"              -> abgebrochen: "
                                  f"Gewinn jetzt {gewinn_jetzt:+.1%} "
                                  f"(Luecke seit der Entscheidung)")
                        run.decision(d.symbol, "topup", reasons=d.reasons,
                                     conviction=d.conviction, price=d.price,
                                     strategy="engine",
                                     blocked_by="KurssluckeSeitEntscheidung")
                        blocked += 1
                        continue

                # Groesse ZUM AUSFUEHRUNGSZEITPUNKT gegen den Deckel pruefen,
                # nicht nur zum Entscheidungszeitpunkt: `d.target_notional`
                # wurde mit dem gestrigen Schlusskurs bemessen. Fuer einen
                # Wert, der seitdem gefallen ist, UNTERSCHAETZT dieser Kurs
                # den heutigen Positionswert und wuerde eine Position ueber
                # den Deckel hinaus vergroessern; fuer einen gestiegenen Wert
                # UEBERSCHAETZT er ihn und blockiert einen eigentlich noch
                # zulaessigen Nachkauf faelschlich (beobachtet bei CHRW:
                # Deckel nach gestrigem Kurs bereits gerissen, nach dem
                # heutigen noch 458 $ Luft). Deshalb hier mit dem echten
                # Kurs neu ausrechnen und kappen statt blind zu uebernehmen.
                if pos is not None:
                    cap = portfolio.equity * cfg.max_position_pct
                    ist_wert = pos.qty * ref.preis
                    erlaubt = max(0.0, cap - ist_wert)
                    if erlaubt < portfolio.equity * cfg.min_position_pct:
                        if verbose:
                            print(f"              -> abgebrochen: Position "
                                  f"waere bereits bei ${ist_wert:,.0f} "
                                  f"(Deckel ${cap:,.0f} zum aktuellen Kurs)")
                        run.decision(d.symbol, "topup", reasons=d.reasons,
                                     conviction=d.conviction, price=d.price,
                                     strategy="engine",
                                     blocked_by="DeckelZumAktuellenKurs")
                        blocked += 1
                        continue
                    if d.target_notional > erlaubt:
                        if verbose:
                            print(f"              Groesse gekappt: "
                                  f"${d.target_notional:,.0f} -> ${erlaubt:,.0f} "
                                  f"(Deckel zum aktuellen Kurs)")
                        d.target_notional = round(erlaubt, 2)

                compliance.assert_can_trade(d.symbol, "buy")
                # Auch der Nachkauf ist ein Kauf und erhoeht Exposure und
                # Klumpenrisiko. Ihn auszunehmen hiesse, die Grenzen ueber
                # wiederholtes Aufstocken zu umgehen - bei bis zu neun
                # Nachkaeufen je Symbol (gemessen: MUSA) ist das kein
                # theoretischer Fall.
                frei = risiko.pruefe_order(d.symbol, "buy", d.target_notional,
                                           sektoren=sektoren)
                if not frei.ok:
                    if verbose:
                        print(f"              -> Risiko-Dach: "
                              f"{'; '.join(frei.gruende)}")
                    run.decision(d.symbol, "topup", reasons=d.reasons,
                                 conviction=d.conviction, price=d.price,
                                 strategy="engine",
                                 blocked_by=f"Risikodach: {'; '.join(frei.gruende)[:200]}")
                    blocked += 1
                    continue
                res = trading.market_order(
                    d.symbol, notional=round(d.target_notional, 2),
                    side="buy", dry_run=dry_run,
                )
                run.order(did, symbol=d.symbol, side="buy",
                          status=res.status,
                          # NIEMALS "dry-run" als order_id durchreichen:
                          # OrderResult.id ist im Trockenlauf immer dieser
                          # feste String. Da orders.order_id PRIMARY KEY ist
                          # und journal.order() mit INSERT OR REPLACE
                          # schreibt, wuerde jede weitere Dry-Run-Order die
                          # vorherige mit identischer ID stillschweigend
                          # ueberschreiben - nur die letzte haette ueberlebt.
                          # None laesst journal.order() eine eindeutige
                          # lokale ID erzeugen, wie es schon immer fuer
                          # NICHT gesetzte IDs vorgesehen war.
                          order_id=(res.id if not dry_run else None),
                          notional=d.target_notional, dry_run=dry_run,
                          expected_price=ref.preis, referenz_quelle=ref.quelle,
                          decision_price=d.price)
                if not dry_run:
                    _nachkauf_im_zustand(d, ref.preis)
                done.append(d)
                executed += 0 if dry_run else 1
            except (trading.RiskError, compliance.ComplianceError) as e:
                if verbose:
                    print(f"              -> blockiert: {e}")
                run.decision(d.symbol, "topup", reasons=d.reasons,
                             conviction=d.conviction, price=d.price,
                             strategy="engine", blocked_by=type(e).__name__)
                blocked += 1
            except Exception as e:  # noqa: BLE001
                run.error(f"Nachkauf {d.symbol} fehlgeschlagen: {e}")
                blocked += 1

        run.log("abschluss", ausgefuehrt=executed, blockiert=blocked,
                entscheidungen=len(decisions), abgeschickt=len(done))
        return LiveResult(decisions, done, executed, blocked, dry_run,
                          portfolio.equity)
