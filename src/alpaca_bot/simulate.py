"""Historien-Replay: Tag fuer Tag durch die Vergangenheit, wie im Live-Betrieb.

Kein vektorisierter Backtest. Die Simulation geht die Historie Handelstag
fuer Handelstag durch, baut fuer jeden Tag eine Momentaufnahme aus
ausschliesslich vergangenen Daten und ruft **dieselbe** `Engine.decide()`
auf, die spaeter im Paper- und Live-Betrieb laeuft.

Was dabei mitsimuliert wird - und was ein vektorisierter Backtest
typischerweise unterschlaegt:

  * **Ausfuehrung erst am Folgetag zur Eroeffnung.** Wer am Abend ein
    Signal sieht, kann fruehestens am naechsten Morgen handeln.
  * **Spread, Slippage und Regulierungsgebuehren** ueber `costs.py` -
    Kauf zum Briefkurs, Verkauf zum Geldkurs.
  * **PDT-Regel.** Unter 25.000 USD nur 3 Daytrades je 5 Werktage.
  * **Kapitalgrenzen.** Es kann nur gekauft werden, was bezahlbar ist.
  * **Kursluecken.** Ein Stop bei 48 wird nicht bei 48 ausgefuehrt, wenn
    die Aktie bei 44 eroeffnet - sondern bei 44.
  * **Lueckenloses Protokoll.** Jede Entscheidung landet mit ihrer
    Begruendung im Journal, exakt wie im Live-Betrieb.

Der Preis dafuer ist Rechenzeit: statt einer Matrixoperation laeuft eine
echte Schleife. Das ist es wert - was hier getestet wird, ist genau das,
was spaeter handelt.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .costs import DEFAULT_FEES, FeeSchedule, estimate_costs
from .engine import (
    Decision,
    Engine,
    EngineConfig,
    MarketSnapshot,
    PortfolioState,
    Position,
)
from .journal import Journal


@dataclass
class SimConfig:
    initial_cash: float = 30_000.0
    spread_bps: float = 5.0
    slippage_bps: float = 3.0
    warmup_bars: int = 260
    """So viele Bars Vorlauf, bevor die erste Entscheidung faellt -
    der 200-Tage-Schnitt und die Jahres-Rangwerte brauchen Historie."""
    pdt_threshold: float = 25_000.0
    pdt_max_day_trades: int = 3
    fees: FeeSchedule = field(default_factory=lambda: DEFAULT_FEES)
    log_to_journal: bool = True


@dataclass
class Trade:
    symbol: str
    entry_date: pd.Timestamp
    exit_date: pd.Timestamp | None
    entry_price: float
    exit_price: float | None
    qty: float
    entry_score: float
    exit_reason: str
    gross_pnl: float
    costs: float
    net_pnl: float
    return_pct: float
    bars_held: int


@dataclass
class SimResult:
    equity_curve: pd.Series
    trades: pd.DataFrame
    decisions: pd.DataFrame
    config: SimConfig
    blocked: dict[str, int] = field(default_factory=dict)

    @property
    def total_return(self) -> float:
        if self.equity_curve.empty:
            return 0.0
        return float(self.equity_curve.iloc[-1] / self.equity_curve.iloc[0] - 1)

    def metrics(self) -> dict:
        from .backtest import compute_metrics

        eq = self.equity_curve
        if eq.empty or len(eq) < 2:
            return {}
        m = compute_metrics(eq.pct_change().dropna())
        t = self.trades
        if not t.empty:
            wins = t[t["net_pnl"] > 0]
            losses = t[t["net_pnl"] <= 0]
            m["n_trades"] = len(t)
            m["trefferquote"] = float(len(wins) / len(t))
            m["mittlerer_gewinn"] = float(wins["return_pct"].mean()) if len(wins) else 0.0
            m["mittlerer_verlust"] = float(losses["return_pct"].mean()) if len(losses) else 0.0
            m["profit_faktor"] = (
                float(wins["net_pnl"].sum() / abs(losses["net_pnl"].sum()))
                if len(losses) and losses["net_pnl"].sum() != 0
                else float("inf")
            )
            m["erwartungswert_pro_trade"] = float(t["return_pct"].mean())
            m["kosten_gesamt"] = float(t["costs"].sum())
            m["mittlere_haltedauer"] = float(t["bars_held"].mean())
        return m

    def summary(self) -> str:
        m = self.metrics()
        if not m:
            return "Keine Ergebnisse."
        lines = [
            "=" * 66,
            "  SIMULATIONSERGEBNIS",
            "=" * 66,
            f"  Startkapital          : ${self.config.initial_cash:>12,.2f}",
            f"  Endkapital            : ${self.equity_curve.iloc[-1]:>12,.2f}",
            f"  Gesamtrendite         : {self.total_return:>13.2%}",
            f"  Rendite p.a. (CAGR)   : {m.get('cagr', float('nan')):>13.2%}",
            f"  Sharpe Ratio          : {m.get('sharpe', float('nan')):>13.2f}",
            f"  Max. Drawdown         : {m.get('max_drawdown', float('nan')):>13.2%}",
            "",
            f"  Trades                : {m.get('n_trades', 0):>13,}",
            f"  Trefferquote          : {m.get('trefferquote', 0):>13.1%}",
            f"  Mittlerer Gewinn      : {m.get('mittlerer_gewinn', 0):>13.2%}",
            f"  Mittlerer Verlust     : {m.get('mittlerer_verlust', 0):>13.2%}",
            f"  Profit-Faktor         : {m.get('profit_faktor', 0):>13.2f}",
            f"  Erwartungswert/Trade  : {m.get('erwartungswert_pro_trade', 0):>13.2%}",
            f"  Mittlere Haltedauer   : {m.get('mittlere_haltedauer', 0):>13.0f} Tage",
            f"  Kosten gesamt         : ${m.get('kosten_gesamt', 0):>12,.2f}",
        ]
        if self.blocked:
            lines.append("")
            lines.append("  Blockierte Entscheidungen:")
            for k, v in sorted(self.blocked.items(), key=lambda kv: -kv[1]):
                lines.append(f"    {k:<28} {v:>6}")
        return "\n".join(lines)


def run(
    bars: pd.DataFrame,
    engine_config: EngineConfig | None = None,
    sim_config: SimConfig | None = None,
    insider: dict[str, pd.DataFrame] | None = None,
    start: str | None = None,
    end: str | None = None,
    verbose: bool = True,
) -> SimResult:
    """Spielt die Historie Tag fuer Tag durch.

    Args:
        bars: MultiIndex (symbol, timestamp) mit OHLCV.
        insider: optionale Insider-Merkmale je Symbol.
    """
    cfg = sim_config or SimConfig()
    engine = Engine(engine_config or EngineConfig())
    insider = insider or {}

    # --- Daten je Symbol vorbereiten ---
    per_symbol: dict[str, pd.DataFrame] = {}
    for sym in bars.index.get_level_values("symbol").unique():
        df = bars.xs(sym, level="symbol").sort_index()
        if len(df) > cfg.warmup_bars:
            per_symbol[sym] = df

    if not per_symbol:
        raise ValueError("Keine Symbole mit ausreichender Historie.")

    # --- Signale EINMAL vorberechnen ---
    # Zulaessig, weil signals.build_signal_frame durch pit.audit_feature_function
    # als kausal nachgewiesen ist: build(voll).loc[:T] == build(bis_T). Die
    # Momentaufnahme bekommt jeden Tag nur den Schnitt bis heute, und
    # snapshot.validate() prueft das bei jedem einzelnen Aufruf nach.
    from .signals import build_signal_frame

    ecfg = engine.cfg
    if verbose:
        print(f"    Berechne Signale fuer {len(per_symbol)} Symbole ...")
    signal_frames = {
        sym: build_signal_frame(df, insider.get(sym), ecfg.weights)
        for sym, df in per_symbol.items()
    }

    # Gemeinsamer Handelskalender.
    calendar = sorted(set().union(*[set(df.index) for df in per_symbol.values()]))
    calendar = pd.DatetimeIndex(calendar)
    if start:
        calendar = calendar[calendar >= pd.Timestamp(start, tz="UTC")]
    if end:
        calendar = calendar[calendar <= pd.Timestamp(end, tz="UTC")]
    if len(calendar) < 2:
        raise ValueError("Zu wenig Handelstage im gewaehlten Zeitraum.")

    # --- Zustand ---
    portfolio = PortfolioState(cash=cfg.initial_cash, equity=cfg.initial_cash)
    equity_history: list[tuple[pd.Timestamp, float]] = []
    trades: list[Trade] = []
    decision_log: list[dict] = []
    blocked: dict[str, int] = {}
    day_trade_dates: list[pd.Timestamp] = []
    pending: list[Decision] = []
    open_meta: dict[str, dict] = {}

    journal = Journal() if cfg.log_to_journal else None
    ctx = journal.run("simulate", config={
        "symbole": len(per_symbol), "start": str(calendar[0].date()),
        "ende": str(calendar[-1].date()), "kapital": cfg.initial_cash,
    }) if journal else None
    run_log = ctx.__enter__() if ctx else None

    try:
        for i, today in enumerate(calendar):
            # ---------- 1. Aufgeschobene Orders von gestern ausfuehren ----------
            # Entscheidung faellt am Abend von T, Ausfuehrung am Morgen von T+1.
            for d in pending:
                df = per_symbol.get(d.symbol)
                if df is None or today not in df.index:
                    continue
                bar = df.loc[today]
                fill = float(bar["open"])

                if d.action == "buy":
                    _execute_buy(d, fill, today, portfolio, open_meta, cfg, blocked)
                elif d.action == "sell":
                    _execute_sell(
                        d, bar, today, portfolio, open_meta, cfg, trades,
                        day_trade_dates, blocked,
                    )
            pending = []

            # ---------- 2. Offene Positionen pflegen ----------
            for sym, pos in list(portfolio.positions.items()):
                df = per_symbol.get(sym)
                if df is None or today not in df.index:
                    continue
                bar = df.loc[today]
                atr = _atr_at(df, today)
                engine.update_position(pos, float(bar["close"]), atr)

                # Intraday-Stop: wurde der Stop im Tagesverlauf gerissen?
                if float(bar["low"]) <= pos.stop_price:
                    # Kursluecke beruecksichtigen: nicht besser als die Eroeffnung.
                    fill = min(pos.stop_price, float(bar["open"]))
                    _close_position(
                        sym, fill, today, "stop_intraday", portfolio, open_meta,
                        cfg, trades, day_trade_dates,
                    )

            # ---------- 3. Kontowert bestimmen ----------
            value = portfolio.cash
            for sym, pos in portfolio.positions.items():
                df = per_symbol.get(sym)
                price = (
                    float(df.loc[today, "close"])
                    if df is not None and today in df.index
                    else pos.entry_price
                )
                value += pos.qty * price
            portfolio.equity = value
            equity_history.append((today, value))

            # ---------- 4. Entscheidungen fuer morgen ----------
            if i < cfg.warmup_bars or i >= len(calendar) - 1:
                continue

            active = {
                sym: df.loc[:today]
                for sym, df in per_symbol.items()
                if today in df.index and len(df.loc[:today]) >= cfg.warmup_bars
            }
            snapshot = MarketSnapshot(
                as_of=today,
                bars=active,
                signals={
                    sym: signal_frames[sym].loc[:today] for sym in active
                },
                insider={
                    sym: f.loc[:today] for sym, f in insider.items() if not f.empty
                },
            )
            portfolio.day_trades_used = len(
                [d for d in day_trade_dates if (today - d).days <= 7]
            )

            decisions = engine.decide(snapshot, portfolio)

            for d in decisions:
                decision_log.append({
                    "datum": today, "symbol": d.symbol, "aktion": d.action,
                    "score": d.conviction, "betrag": d.target_notional,
                    **{f"grund_{k}": v for k, v in d.reasons.items()},
                })
                if run_log:
                    run_log.decision(
                        d.symbol, d.action, ts=today, reasons=d.reasons,
                        conviction=d.conviction, price=d.price,
                        strategy="mehrfaktor", blocked_by=d.blocked_by,
                    )
            pending = decisions

            if verbose and i % 250 == 0:
                print(f"    {today.date()}  Kapital ${value:>11,.0f}  "
                      f"Positionen {len(portfolio.positions):>2}  "
                      f"Trades {len(trades):>4}")
    finally:
        if ctx:
            ctx.__exit__(None, None, None)

    eq = pd.Series(dict(equity_history)).sort_index()
    return SimResult(
        equity_curve=eq,
        trades=pd.DataFrame([t.__dict__ for t in trades]),
        decisions=pd.DataFrame(decision_log),
        config=cfg,
        blocked=blocked,
    )


# ---------------------------------------------------------------------------
def _atr_at(df: pd.DataFrame, when: pd.Timestamp) -> float:
    from . import indicators as ind

    sub = df.loc[:when]
    if len(sub) < 20:
        return 0.0
    val = ind.atr(sub, 14).iloc[-1]
    return float(val) if np.isfinite(val) else 0.0


def _execute_buy(d, fill, today, portfolio, open_meta, cfg, blocked):
    qty = int(d.target_notional / fill) if fill > 0 else 0
    if qty <= 0:
        blocked["betrag_zu_klein"] = blocked.get("betrag_zu_klein", 0) + 1
        return

    cost = estimate_costs("buy", qty, last=fill, spread_bps=cfg.spread_bps,
                          slippage_bps=cfg.slippage_bps, fees=cfg.fees)
    if cost.net_proceeds > portfolio.cash:
        qty = int(portfolio.cash * 0.98 / (fill * 1.01))
        if qty <= 0:
            blocked["kapital_erschoepft"] = blocked.get("kapital_erschoepft", 0) + 1
            return
        cost = estimate_costs("buy", qty, last=fill, spread_bps=cfg.spread_bps,
                              slippage_bps=cfg.slippage_bps, fees=cfg.fees)

    portfolio.cash -= cost.net_proceeds
    portfolio.positions[d.symbol] = Position(
        symbol=d.symbol, qty=qty, entry_price=cost.effective_price,
        entry_date=today, stop_price=d.stop_price, target_price=d.target_price,
        high_water=cost.effective_price,
    )
    portfolio.opened_today.add(d.symbol)
    open_meta[d.symbol] = {
        "entry_date": today, "entry_cost": cost.total_cost,
        "score": d.conviction, "entry_price": cost.effective_price,
    }


def _execute_sell(d, bar, today, portfolio, open_meta, cfg, trades,
                  day_trade_dates, blocked):
    pos = portfolio.positions.get(d.symbol)
    if pos is None:
        return
    # PDT: Wuerde der Verkauf am selben Tag wie der Kauf stattfinden?
    if (
        portfolio.equity < cfg.pdt_threshold
        and pos.entry_date == today
        and len([x for x in day_trade_dates if (today - x).days <= 7])
        >= cfg.pdt_max_day_trades
    ):
        blocked["pdt_regel"] = blocked.get("pdt_regel", 0) + 1
        return
    _close_position(d.symbol, float(bar["open"]), today,
                    d.reasons.get("ausstiegsgrund", "signal"),
                    portfolio, open_meta, cfg, trades, day_trade_dates)


def _close_position(sym, fill, today, reason, portfolio, open_meta, cfg,
                    trades, day_trade_dates):
    pos = portfolio.positions.pop(sym, None)
    if pos is None:
        return
    meta = open_meta.pop(sym, {})

    cost = estimate_costs("sell", pos.qty, last=fill, spread_bps=cfg.spread_bps,
                          slippage_bps=cfg.slippage_bps, fees=cfg.fees)
    portfolio.cash += cost.net_proceeds

    if pos.entry_date == today:
        day_trade_dates.append(today)

    invested = pos.qty * pos.entry_price
    gross = pos.qty * (cost.effective_price - pos.entry_price)
    total_costs = cost.total_cost + meta.get("entry_cost", 0.0)
    net = cost.net_proceeds - (invested + meta.get("entry_cost", 0.0))

    trades.append(Trade(
        symbol=sym, entry_date=pos.entry_date, exit_date=today,
        entry_price=pos.entry_price, exit_price=cost.effective_price,
        qty=pos.qty, entry_score=meta.get("score", 0.0), exit_reason=reason,
        gross_pnl=round(gross, 2), costs=round(total_costs, 2),
        net_pnl=round(net, 2),
        return_pct=round(net / invested, 4) if invested else 0.0,
        bars_held=pos.bars_held,
    ))
