"""Vektorisierter Backtester mit ehrlichen Kennzahlen.

Zwei Regeln, die hier fest eingebaut sind:

1. **Kein Blick in die Zukunft.** Das Signal von Bar *t* wird erst auf
   Bar *t+1* gehandelt (`position.shift(1)`). Wer das vergisst, baut
   Strategien mit 300 % Rendite, die live sofort verlieren.
2. **Kosten immer mitrechnen.** Gebuehren + Spread fressen genau die
   Strategien auf, die auf Papier am besten aussehen (viele Trades).

Ausserdem laeuft jeder Backtest automatisch gegen Buy-and-Hold. Eine
Strategie, die den Index nicht schlaegt, ist keine Strategie.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

TRADING_DAYS = 252


@dataclass
class BacktestResult:
    equity: pd.Series
    returns: pd.Series
    position: pd.Series
    benchmark_equity: pd.Series
    metrics: dict = field(default_factory=dict)
    benchmark_metrics: dict = field(default_factory=dict)

    def summary(self) -> str:
        rows = [
            ("Rendite gesamt", "total_return", "{:>9.1%}"),
            ("Rendite p.a. (CAGR)", "cagr", "{:>9.1%}"),
            ("Volatilitaet p.a.", "ann_vol", "{:>9.1%}"),
            ("Sharpe Ratio", "sharpe", "{:>9.2f}"),
            ("Sortino Ratio", "sortino", "{:>9.2f}"),
            ("Max. Drawdown", "max_drawdown", "{:>9.1%}"),
            ("Calmar Ratio", "calmar", "{:>9.2f}"),
            ("Trefferquote", "hit_rate", "{:>9.1%}"),
            ("Marktexposure", "exposure", "{:>9.1%}"),
            ("Anzahl Trades", "n_trades", "{:>9.0f}"),
        ]
        lines = [
            f"{'Kennzahl':<24}{'Strategie':>12}{'Buy & Hold':>14}",
            "-" * 50,
        ]
        for label, key, fmt in rows:
            a = self.metrics.get(key)
            b = self.benchmark_metrics.get(key)
            sa = fmt.format(a) if a is not None and np.isfinite(a) else "        -"
            sb = fmt.replace(">9", ">11").format(b) if b is not None and np.isfinite(b) else "          -"
            lines.append(f"{label:<24}{sa:>12}{sb:>14}")
        return "\n".join(lines)

    def __str__(self) -> str:
        return self.summary()


def compute_metrics(returns: pd.Series, periods: int = TRADING_DAYS) -> dict:
    """Standard-Kennzahlen aus einer Renditereihe."""
    r = returns.dropna()
    if r.empty:
        return {}

    equity = (1 + r).cumprod()
    total = float(equity.iloc[-1] - 1)
    years = len(r) / periods
    cagr = float(equity.iloc[-1] ** (1 / years) - 1) if years > 0 else np.nan

    ann_vol = float(r.std() * np.sqrt(periods))
    sharpe = float(r.mean() / r.std() * np.sqrt(periods)) if r.std() > 0 else np.nan

    downside = r[r < 0].std()
    sortino = float(r.mean() / downside * np.sqrt(periods)) if downside and downside > 0 else np.nan

    dd = equity / equity.cummax() - 1
    max_dd = float(dd.min())
    calmar = float(cagr / abs(max_dd)) if max_dd < 0 else np.nan

    active = r[r != 0]
    hit_rate = float((active > 0).mean()) if len(active) else np.nan

    return {
        "total_return": total,
        "cagr": cagr,
        "ann_vol": ann_vol,
        "sharpe": sharpe,
        "sortino": sortino,
        "max_drawdown": max_dd,
        "calmar": calmar,
        "hit_rate": hit_rate,
        "best_day": float(r.max()),
        "worst_day": float(r.min()),
        "n_periods": int(len(r)),
    }


def backtest(
    prices: pd.Series,
    target_position: pd.Series,
    *,
    fee_bps: float = 1.0,
    slippage_bps: float = 3.0,
    initial_cash: float = 100_000.0,
    periods: int = TRADING_DAYS,
) -> BacktestResult:
    """Testet eine Signalreihe gegen echte Kurse.

    Args:
        prices: Schlusskurse (DatetimeIndex).
        target_position: gewuenschte Position je Bar.
            1.0 = voll long, 0 = Cash, -1.0 = voll short, 0.5 = halb.
        fee_bps: Gebuehr pro Umsatz in Basispunkten (Alpaca US-Aktien: 0).
        slippage_bps: realistischer Ausfuehrungsnachteil. 3 bps ist fuer
            liquide Large-Caps optimistisch-realistisch, bei Nebenwerten
            eher 10-20.
    """
    prices = prices.dropna().astype(float)
    pos = target_position.reindex(prices.index).ffill().fillna(0.0).astype(float)

    # Signal von heute wird morgen gehandelt -> kein Lookahead.
    pos_traded = pos.shift(1).fillna(0.0)

    market_ret = prices.pct_change().fillna(0.0)
    turnover = pos_traded.diff().abs().fillna(pos_traded.abs())
    cost = turnover * (fee_bps + slippage_bps) / 10_000

    strat_ret = pos_traded * market_ret - cost

    equity = (1 + strat_ret).cumprod() * initial_cash
    bench_equity = (1 + market_ret).cumprod() * initial_cash

    metrics = compute_metrics(strat_ret, periods)
    metrics["n_trades"] = int((turnover > 1e-9).sum())
    metrics["exposure"] = float((pos_traded.abs() > 1e-9).mean())
    metrics["total_costs"] = float((cost * equity.shift(1).fillna(initial_cash)).sum())
    metrics["final_equity"] = float(equity.iloc[-1])

    bench_metrics = compute_metrics(market_ret, periods)
    bench_metrics["n_trades"] = 1
    bench_metrics["exposure"] = 1.0
    bench_metrics["final_equity"] = float(bench_equity.iloc[-1])

    return BacktestResult(
        equity=equity,
        returns=strat_ret,
        position=pos_traded,
        benchmark_equity=bench_equity,
        metrics=metrics,
        benchmark_metrics=bench_metrics,
    )


def volatility_target(
    signal: pd.Series,
    prices: pd.Series,
    target_vol: float = 0.15,
    window: int = 20,
    max_leverage: float = 1.0,
) -> pd.Series:
    """Skaliert ein 0/1-Signal auf eine konstante Ziel-Volatilitaet.

    In ruhigen Phasen groessere, in hektischen kleinere Position. Das ist
    der wirksamste einzelne Hebel fuer eine bessere Sharpe Ratio - meist
    mehr wert als ein besseres Einstiegssignal.
    """
    realized = prices.pct_change().rolling(window).std() * np.sqrt(TRADING_DAYS)
    scale = (target_vol / realized).clip(upper=max_leverage).fillna(0.0)
    return (signal * scale).clip(-max_leverage, max_leverage)


def split_train_test(
    df: pd.DataFrame, test_size: float = 0.3
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Zeitlicher Split - niemals zufaellig mischen bei Zeitreihen!"""
    cut = int(len(df) * (1 - test_size))
    return df.iloc[:cut].copy(), df.iloc[cut:].copy()


def plot(result: BacktestResult, title: str = "Backtest", save_path=None):
    """Equity-Kurve + Drawdown zeichnen."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, (ax1, ax2) = plt.subplots(
        2, 1, figsize=(12, 8), sharex=True, height_ratios=[3, 1]
    )
    ax1.plot(result.equity, label="Strategie", linewidth=1.6)
    ax1.plot(result.benchmark_equity, label="Buy & Hold", linewidth=1.2, alpha=0.7)
    ax1.set_title(title)
    ax1.set_ylabel("Kontowert ($)")
    ax1.legend()
    ax1.grid(alpha=0.3)

    dd = result.equity / result.equity.cummax() - 1
    ax2.fill_between(dd.index, dd * 100, 0, alpha=0.4, color="crimson")
    ax2.set_ylabel("Drawdown (%)")
    ax2.grid(alpha=0.3)

    fig.tight_layout()
    if save_path:
        fig.savefig(save_path, dpi=120)
        plt.close(fig)
        return save_path
    return fig
