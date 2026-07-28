"""Konto-Informationen: Guthaben, Positionen, Orders, Markt-Status."""

from __future__ import annotations

import datetime as dt

import pandas as pd
from alpaca.trading.enums import QueryOrderStatus
from alpaca.trading.requests import GetOrdersRequest

from .clients import trading_client
from .ratelimit import RateLimiter

# Trading API: eigenes Kontingent, 200/min - getrennt von den Marktdaten.
_limit = RateLimiter("alpaca_trading")


def account_summary() -> dict:
    """Die wichtigsten Kontokennzahlen als Dictionary."""
    _limit.acquire()
    a = trading_client().get_account()
    return {
        "account_number": a.account_number,
        "status": str(a.status),
        "currency": a.currency,
        "equity": float(a.equity),
        "last_equity": float(a.last_equity),
        "cash": float(a.cash),
        "buying_power": float(a.buying_power),
        "portfolio_value": float(a.portfolio_value),
        "daytrade_count": a.daytrade_count,
        "pattern_day_trader": a.pattern_day_trader,
        "trading_blocked": a.trading_blocked,
        "shorting_enabled": a.shorting_enabled,
        "multiplier": a.multiplier,
    }


def positions() -> pd.DataFrame:
    """Offene Positionen mit unrealisiertem Gewinn/Verlust."""
    _limit.acquire()
    open_positions = trading_client().get_all_positions()
    rows = [
        {
            "symbol": p.symbol,
            "qty": float(p.qty),
            "side": str(p.side).split(".")[-1].lower(),
            "avg_entry": float(p.avg_entry_price),
            "current_price": float(p.current_price) if p.current_price else None,
            "market_value": float(p.market_value) if p.market_value else None,
            "unrealized_pl": float(p.unrealized_pl) if p.unrealized_pl else None,
            "unrealized_plpc": (
                round(float(p.unrealized_plpc) * 100, 2) if p.unrealized_plpc else None
            ),
            "asset_class": str(p.asset_class).split(".")[-1],
        }
        for p in open_positions
    ]
    if not rows:
        return pd.DataFrame(
            columns=["symbol", "qty", "side", "avg_entry", "current_price",
                     "market_value", "unrealized_pl", "unrealized_plpc", "asset_class"]
        ).set_index("symbol")
    return pd.DataFrame(rows).set_index("symbol").sort_values("market_value", ascending=False)


def orders(
    status: str = "all", limit: int = 100, after: dt.datetime | None = None
) -> pd.DataFrame:
    """Order-Historie. status: 'open' | 'closed' | 'all'."""
    req = GetOrdersRequest(
        status=QueryOrderStatus(status), limit=limit, after=after, nested=True
    )
    _limit.acquire()
    order_list = trading_client().get_orders(req)
    rows = [
        {
            "submitted_at": o.submitted_at,
            "symbol": o.symbol,
            "side": str(o.side).split(".")[-1].lower(),
            "type": str(o.order_type).split(".")[-1].lower(),
            "qty": float(o.qty) if o.qty else None,
            "notional": float(o.notional) if o.notional else None,
            "filled_qty": float(o.filled_qty) if o.filled_qty else 0.0,
            "filled_avg_price": (
                float(o.filled_avg_price) if o.filled_avg_price else None
            ),
            "status": str(o.status).split(".")[-1].lower(),
            "id": str(o.id),
        }
        for o in order_list
    ]
    if not rows:
        return pd.DataFrame(
            columns=["submitted_at", "symbol", "side", "type", "qty", "notional",
                     "filled_qty", "filled_avg_price", "status", "id"]
        )
    return pd.DataFrame(rows).sort_values("submitted_at", ascending=False)


def market_clock() -> dict:
    """Ist die US-Boerse gerade offen? Wann oeffnet/schliesst sie?"""
    _limit.acquire()
    c = trading_client().get_clock()
    return {
        "timestamp": c.timestamp,
        "is_open": c.is_open,
        "next_open": c.next_open,
        "next_close": c.next_close,
    }


def portfolio_history(period: str = "1M", timeframe: str = "1D") -> pd.DataFrame:
    """Equity-Kurve des Kontos. period: '1D','1W','1M','3M','1A','all'."""
    from alpaca.trading.requests import GetPortfolioHistoryRequest

    h = trading_client().get_portfolio_history(
        GetPortfolioHistoryRequest(period=period, timeframe=timeframe)
    )
    df = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(h.timestamp, unit="s", utc=True),
            "equity": h.equity,
            "profit_loss": h.profit_loss,
            "profit_loss_pct": h.profit_loss_pct,
        }
    )
    return df.set_index("timestamp")
