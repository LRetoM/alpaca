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

from . import account, compliance, data, trading
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

    if verbose:
        print(f"      Stichtag: {as_of.date()} | {len(per_symbol)} Symbole "
              f"| Marktfilter: {MARKET_SYMBOL}")
    return MarketSnapshot(as_of=as_of, bars=per_symbol, market=market)


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

    since = dt.datetime.now(dt.UTC) - dt.timedelta(hours=lookback_hours)
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
            if price is None or not o.get("expected_price"):
                continue
            expected = float(o["expected_price"])
            slip = (price - expected) / expected * 10_000
            if o["side"] == "sell":
                slip = -slip
            c.execute(
                "UPDATE orders SET fill_price = ?, slippage_bps = ? WHERE order_id = ?",
                (price, slip, o["order_id"]),
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
    engine = Engine(engine_config or EngineConfig())
    journal = Journal()

    with journal.run("live_trade", config={
        "symbole": len(symbols), "dry_run": dry_run,
        "max_neue_positionen": max_new_positions,
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

        if verbose:
            print(f"\n      {len(sells)} Verkaeufe, {len(buys)} Kaeufe "
                  f"(von {len([d for d in decisions if d.action == 'buy'])} moeglichen)")

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
                msg = trading.close_position(d.symbol, dry_run=dry_run)
                run.order(did, symbol=d.symbol, side="sell", status=str(msg),
                          dry_run=dry_run, expected_price=d.price)
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
                res = trading.market_order(
                    d.symbol, notional=round(d.target_notional, 2),
                    side="buy", dry_run=dry_run,
                )
                run.order(did, symbol=d.symbol, side="buy",
                          status=res.status, order_id=res.id,
                          notional=d.target_notional, dry_run=dry_run,
                          expected_price=d.price)
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

        run.log("abschluss", ausgefuehrt=executed, blockiert=blocked,
                entscheidungen=len(decisions), abgeschickt=len(done))
        return LiveResult(decisions, done, executed, blocked, dry_run,
                          portfolio.equity)
