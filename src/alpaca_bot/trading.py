"""Orders platzieren - mit eingebauten Leitplanken.

Jede Order laeuft durch `_check_risk()`. Das verhindert die zwei Fehler,
die im Paper-Trading harmlos sind und im Live-Trading teuer:
Tippfehler bei der Menge und zu grosse Einzelpositionen.
"""

from __future__ import annotations

from dataclasses import dataclass

from alpaca.trading.enums import OrderClass, OrderSide, TimeInForce
from alpaca.trading.requests import (
    LimitOrderRequest,
    MarketOrderRequest,
    StopLossRequest,
    TakeProfitRequest,
    TrailingStopOrderRequest,
)

from .account import account_summary
from .clients import trading_client
from .config import get_settings
from .ratelimit import RateLimiter

_limit = RateLimiter("alpaca_trading")


class RiskError(RuntimeError):
    """Order verletzt eine Risiko-Leitplanke und wurde nicht gesendet."""


@dataclass
class OrderResult:
    id: str
    symbol: str
    side: str
    qty: float | None
    notional: float | None
    status: str
    dry_run: bool = False

    def __str__(self) -> str:
        tag = "[DRY-RUN] " if self.dry_run else ""
        size = f"{self.qty} Stk" if self.qty else f"${self.notional}"
        return f"{tag}{self.side.upper()} {size} {self.symbol} -> {self.status}"


def _check_risk(symbol: str, notional_estimate: float) -> None:
    s = get_settings()

    if notional_estimate > s.max_order_notional:
        raise RiskError(
            f"Order-Volumen ${notional_estimate:,.2f} > Limit "
            f"${s.max_order_notional:,.2f} (MAX_ORDER_NOTIONAL in .env)."
        )

    acct = account_summary()
    if acct["trading_blocked"]:
        raise RiskError("Das Konto ist fuer den Handel gesperrt.")

    portfolio = acct["portfolio_value"]
    if portfolio > 0:
        pct = notional_estimate / portfolio
        if pct > s.max_position_pct:
            raise RiskError(
                f"Position waere {pct:.1%} des Portfolios, erlaubt sind "
                f"{s.max_position_pct:.1%} (MAX_POSITION_PCT in .env)."
            )
    if notional_estimate > acct["buying_power"]:
        raise RiskError(
            f"Kaufkraft reicht nicht: ${acct['buying_power']:,.2f} verfuegbar, "
            f"${notional_estimate:,.2f} noetig."
        )


def _estimate_price(symbol: str) -> float:
    from .data import latest_quotes

    q = latest_quotes(symbol)
    ask = float(q.loc[symbol, "ask"])
    bid = float(q.loc[symbol, "bid"])
    return ask or bid or 0.0


def market_order(
    symbol: str,
    qty: float | None = None,
    *,
    notional: float | None = None,
    side: str = "buy",
    time_in_force: str = "day",
    dry_run: bool = True,
) -> OrderResult:
    """Market-Order. Entweder `qty` (Stueck) ODER `notional` (USD-Betrag).

    `notional` erlaubt Bruchteile von Aktien - ideal fuer kleine Konten.
    `dry_run=True` ist Absicht: nichts wird gesendet, bis du es willst.
    """
    if (qty is None) == (notional is None):
        raise ValueError("Genau eines von qty oder notional angeben.")

    est = float(notional) if notional else float(qty) * _estimate_price(symbol)
    _check_risk(symbol, est)

    if dry_run:
        return OrderResult("dry-run", symbol, side, qty, notional, "not_sent", True)

    req = MarketOrderRequest(
        symbol=symbol,
        qty=qty,
        notional=notional,
        side=OrderSide(side),
        time_in_force=TimeInForce(time_in_force),
    )
    _limit.acquire()
    o = trading_client().submit_order(req)
    return OrderResult(
        str(o.id), o.symbol, side, qty, notional, str(o.status).split(".")[-1].lower()
    )


def limit_order(
    symbol: str,
    qty: float,
    limit_price: float,
    *,
    side: str = "buy",
    time_in_force: str = "day",
    dry_run: bool = True,
) -> OrderResult:
    """Limit-Order: wird nur zu diesem Preis oder besser ausgefuehrt."""
    _check_risk(symbol, qty * limit_price)
    if dry_run:
        return OrderResult("dry-run", symbol, side, qty, None, "not_sent", True)

    req = LimitOrderRequest(
        symbol=symbol,
        qty=qty,
        limit_price=round(limit_price, 2),
        side=OrderSide(side),
        time_in_force=TimeInForce(time_in_force),
    )
    _limit.acquire()
    o = trading_client().submit_order(req)
    return OrderResult(
        str(o.id), o.symbol, side, qty, None, str(o.status).split(".")[-1].lower()
    )


def bracket_order(
    symbol: str,
    qty: float,
    *,
    take_profit_pct: float = 0.10,
    stop_loss_pct: float = 0.05,
    side: str = "buy",
    dry_run: bool = True,
) -> OrderResult:
    """Kauf mit automatischem Gewinnziel UND Stop-Loss.

    Die wichtigste Order-Art fuer systematisches Handeln: der Ausstieg
    steht fest, bevor die Position existiert. Kein Nachverhandeln mit
    sich selbst, wenn es rot wird.
    """
    price = _estimate_price(symbol)
    if price <= 0:
        raise RiskError(f"Kein Kurs fuer {symbol} verfuegbar.")
    _check_risk(symbol, qty * price)

    if side == "buy":
        tp = round(price * (1 + take_profit_pct), 2)
        sl = round(price * (1 - stop_loss_pct), 2)
    else:
        tp = round(price * (1 - take_profit_pct), 2)
        sl = round(price * (1 + stop_loss_pct), 2)

    if dry_run:
        res = OrderResult("dry-run", symbol, side, qty, None, "not_sent", True)
        print(f"  Einstieg ~{price:.2f} | Ziel {tp:.2f} | Stop {sl:.2f}")
        return res

    req = MarketOrderRequest(
        symbol=symbol,
        qty=qty,
        side=OrderSide(side),
        time_in_force=TimeInForce.DAY,
        order_class=OrderClass.BRACKET,
        take_profit=TakeProfitRequest(limit_price=tp),
        stop_loss=StopLossRequest(stop_price=sl),
    )
    _limit.acquire()
    o = trading_client().submit_order(req)
    return OrderResult(
        str(o.id), o.symbol, side, qty, None, str(o.status).split(".")[-1].lower()
    )


def trailing_stop(
    symbol: str, qty: float, trail_percent: float = 3.0, *, dry_run: bool = True
) -> OrderResult:
    """Nachziehender Stop: laesst Gewinne laufen, begrenzt den Rueckfall."""
    if dry_run:
        return OrderResult("dry-run", symbol, "sell", qty, None, "not_sent", True)
    req = TrailingStopOrderRequest(
        symbol=symbol,
        qty=qty,
        side=OrderSide.SELL,
        time_in_force=TimeInForce.GTC,
        trail_percent=trail_percent,
    )
    _limit.acquire()
    o = trading_client().submit_order(req)
    return OrderResult(
        str(o.id), o.symbol, "sell", qty, None, str(o.status).split(".")[-1].lower()
    )


def close_position(symbol: str, *, dry_run: bool = True) -> OrderResult:
    """Position komplett schliessen.

    Gibt wie `market_order()` ein OrderResult mit der ECHTEN Alpaca-
    Order-ID zurueck. Vorher wurde die Rueckgabe von
    `trading_client().close_position()` verworfen und durch einen reinen
    Text ersetzt ("AMKR geschlossen") - dadurch bekam jeder Verkauf im
    Protokoll eine selbst erfundene Platzhalter-ID (order_id="local_..."),
    die niemals zu einer echten Order beim Broker passt.
    `live.reconcile_fills()` konnte solche Verkaeufe deshalb NIE mit
    einem Fuellpreis abgleichen - kein Zeitfenster-Problem, sondern ein
    strukturell fehlender Schluessel. Betraf jeden Verkauf, nicht nur
    Einzelfaelle. Entdeckt am 03.08.2026 bei der Pruefung der
    Ausfuehrungsqualitaet.
    """
    if dry_run:
        return OrderResult("dry-run", symbol, "sell", None, None, "not_sent", True)
    _limit.acquire()
    o = trading_client().close_position(symbol)
    return OrderResult(
        str(o.id), o.symbol, "sell",
        float(o.qty) if o.qty else None, None,
        str(o.status).split(".")[-1].lower(),
    )


def close_all(*, dry_run: bool = True) -> str:
    """Notausstieg: alles verkaufen, offene Orders stornieren."""
    if dry_run:
        return "[DRY-RUN] wuerde ALLE Positionen schliessen"
    _limit.acquire()
    trading_client().close_all_positions(cancel_orders=True)
    return "Alle Positionen geschlossen"


def cancel_all_orders(*, dry_run: bool = True) -> str:
    if dry_run:
        return "[DRY-RUN] wuerde alle offenen Orders stornieren"
    _limit.acquire()
    trading_client().cancel_orders()
    return "Alle offenen Orders storniert"
