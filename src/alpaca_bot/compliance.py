"""Broker-Regeln und API-Budget - die harten Grenzen, die keine Strategie kennt.

Ein Modell rechnet in Renditen. Der Broker rechnet in Regeln. Wer die
zweite Schicht nicht implementiert, baut Strategien, die rechtlich oder
technisch gar nicht ausfuehrbar sind - und merkt es erst live.

Die wichtigste Regel fuer dich:

**PDT - Pattern Day Trader.** Liegt das Kontokapital unter 25.000 USD,
sind in 5 rollierenden Werktagen nur **3 Daytrades** erlaubt. Ein Daytrade
ist Kauf UND Verkauf desselben Wertpapiers am selben Handelstag. Beim
vierten wird das Konto fuer 90 Tage auf "nur schliessende Orders"
gesetzt - oder es muss auf 25.000 USD aufgefuellt werden.

Das ist keine Alpaca-Eigenheit, sondern FINRA-Regel 4210 und gilt bei
jedem US-Broker. Im Paper-Konto wird sie ebenfalls simuliert.

**Und das ist eine gute Nachricht fuer deinen Plan:** Die Regel macht
Daytrading unter 25.000 USD strukturell unmoeglich und zwingt dich zu
genau dem Mehrtages-Horizont, den du ohnehin wolltest. Was wie eine
Einschraenkung aussieht, deckt sich hier mit der besseren Strategie.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

import pandas as pd

from .ratelimit import QUOTAS, RateLimiter

PDT_EQUITY_THRESHOLD = 25_000.0
PDT_MAX_DAY_TRADES = 3
PDT_WINDOW_DAYS = 5


class ComplianceError(RuntimeError):
    """Eine Broker-Regel wuerde verletzt. Die Order wird nicht gesendet."""


@dataclass
class ComplianceStatus:
    ok: bool
    equity: float
    day_trades_used: int
    day_trades_left: int | None
    is_pdt_restricted: bool
    warnings: list[str] = field(default_factory=list)
    blocks: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        lines = [
            f"Kontowert          : ${self.equity:,.2f}",
            f"Daytrades (5 Tage) : {self.day_trades_used}"
            + (f" / {PDT_MAX_DAY_TRADES}" if self.day_trades_left is not None else " (unbegrenzt)"),
        ]
        if self.day_trades_left is not None:
            lines.append(f"Noch moeglich      : {self.day_trades_left}")
        for w in self.warnings:
            lines.append(f"  [Hinweis] {w}")
        for b in self.blocks:
            lines.append(f"  [BLOCKIERT] {b}")
        return "\n".join(lines)


def check_account(account: dict | None = None) -> ComplianceStatus:
    """Prueft den aktuellen Kontostatus gegen die Broker-Regeln."""
    if account is None:
        from .account import account_summary

        account = account_summary()

    equity = float(account.get("equity") or account.get("portfolio_value") or 0.0)
    used = int(account.get("daytrade_count") or 0)
    below = equity < PDT_EQUITY_THRESHOLD
    left = max(0, PDT_MAX_DAY_TRADES - used) if below else None

    warnings_, blocks = [], []

    if account.get("trading_blocked"):
        blocks.append("Konto ist fuer den Handel gesperrt.")
    if account.get("pattern_day_trader") and below:
        blocks.append(
            "Konto ist als Pattern Day Trader markiert UND unter 25.000 USD. "
            "Es sind nur noch schliessende Orders erlaubt."
        )
    if below:
        if used >= PDT_MAX_DAY_TRADES:
            blocks.append(
                f"{used} Daytrades in 5 Werktagen verbraucht. Ein weiterer "
                "loest die PDT-Sperre aus (90 Tage)."
            )
        elif used == PDT_MAX_DAY_TRADES - 1:
            warnings_.append(
                "Nur noch 1 Daytrade frei. Positionen ueber Nacht halten, "
                "dann zaehlt es nicht als Daytrade."
            )
        warnings_.append(
            f"Konto unter ${PDT_EQUITY_THRESHOLD:,.0f}: max. {PDT_MAX_DAY_TRADES} "
            "Daytrades je 5 Werktage. Mehrtages-Positionen sind unbegrenzt."
        )

    return ComplianceStatus(
        ok=not blocks,
        equity=equity,
        day_trades_used=used,
        day_trades_left=left,
        is_pdt_restricted=bool(below),
        warnings=warnings_,
        blocks=blocks,
    )


def would_be_day_trade(
    symbol: str, side: str, positions_opened_today: dict[str, str]
) -> bool:
    """Wuerde diese Order einen Daytrade ausloesen?

    Args:
        positions_opened_today: {symbol: 'buy'|'sell'} - heute eroeffnete Positionen.
    """
    opened = positions_opened_today.get(symbol)
    if opened is None:
        return False
    return (opened == "buy" and side == "sell") or (opened == "sell" and side == "buy")


def assert_can_trade(
    symbol: str,
    side: str,
    *,
    account: dict | None = None,
    positions_opened_today: dict[str, str] | None = None,
    allow_closing: bool = True,
) -> ComplianceStatus:
    """Harte Pruefung vor jeder echten Order. Wirft bei Regelverstoss.

    `allow_closing=True` laesst schliessende Orders auch bei PDT-Sperre zu -
    aus einer Position herauszukommen ist immer erlaubt.
    """
    status = check_account(account)

    if status.blocks and not (allow_closing and side == "sell"):
        raise ComplianceError(
            "Order blockiert:\n  " + "\n  ".join(status.blocks)
        )

    if status.is_pdt_restricted and positions_opened_today:
        if would_be_day_trade(symbol, side, positions_opened_today):
            if status.day_trades_left is not None and status.day_trades_left <= 0:
                raise ComplianceError(
                    f"{symbol}: Diese Order waere ein Daytrade, aber das "
                    f"Kontingent ({PDT_MAX_DAY_TRADES} je 5 Werktage) ist "
                    "aufgebraucht. Position ueber Nacht halten."
                )
            status.warnings.append(
                f"{symbol}: Diese Order IST ein Daytrade. Danach noch "
                f"{(status.day_trades_left or 1) - 1} frei."
            )
    return status


def day_trades_from_orders(orders: pd.DataFrame, days: int = PDT_WINDOW_DAYS) -> int:
    """Zaehlt Daytrades der letzten n Werktage aus der eigenen Order-Historie.

    Gegenprobe zum `daytrade_count` des Brokers - wenn beide auseinander
    laufen, stimmt die eigene Buchfuehrung nicht.
    """
    if orders.empty:
        return 0
    df = orders[orders["status"].isin(["filled", "partially_filled"])].copy()
    if df.empty:
        return 0
    df["day"] = pd.DatetimeIndex(df["submitted_at"]).tz_convert("UTC").normalize()
    cutoff = pd.Timestamp.now(tz="UTC").normalize() - pd.tseries.offsets.BDay(days)
    df = df[df["day"] >= cutoff]

    count = 0
    for (_, _), grp in df.groupby(["day", "symbol"]):
        sides = set(grp["side"])
        if {"buy", "sell"}.issubset(sides):
            count += min(
                (grp["side"] == "buy").sum(), (grp["side"] == "sell").sum()
            )
    return int(count)


# ---------------------------------------------------------------------------
# API-Budget: passt der geplante Lauf ueberhaupt in die Kontingente?
# ---------------------------------------------------------------------------
@dataclass
class BudgetPlan:
    """Was ein geplanter Lauf an API-Anfragen kosten wird."""

    items: dict[str, int] = field(default_factory=dict)

    def add(self, source: str, n_requests: int) -> BudgetPlan:
        if source not in QUOTAS:
            raise KeyError(f"Unbekannte Quelle {source!r}")
        self.items[source] = self.items.get(source, 0) + n_requests
        return self

    def check(self) -> tuple[bool, str]:
        """Passt der Plan in die verbleibenden Kontingente von heute?"""
        lines, ok = [], True
        total_seconds = 0.0

        for source, n in sorted(self.items.items()):
            lim = RateLimiter(source)
            q = lim.quota
            rate = (
                q.per_minute * lim.safety / 60
                if q.per_minute
                else (q.per_second * lim.safety if q.per_second else 10.0)
            )
            seconds = n / rate
            total_seconds += seconds
            line = f"  {q.name[:38]:<40}{n:>8,} Req{seconds / 60:>8.1f} Min"

            rem = lim.remaining_today()
            if rem is not None:
                line += f"   (heute frei: {rem:,})"
                if n > rem:
                    ok = False
                    line += "  >>> PASST NICHT"
            lines.append(line)

        head = "API-Budget fuer diesen Lauf:" if ok else "API-Budget REICHT NICHT:"
        lines.append(f"  {'GESAMT':<40}{sum(self.items.values()):>8,} Req"
                     f"{total_seconds / 60:>8.1f} Min")
        if total_seconds > 3600:
            lines.append(
                f"  Hinweis: {total_seconds / 3600:.1f} Stunden Laufzeit. "
                "Zwischenergebnisse cachen (use_cache=True), sonst faengt "
                "jeder Abbruch von vorne an."
            )
        return ok, head + "\n" + "\n".join(lines)


def preflight(
    n_symbols: int,
    years: float,
    timeframe: str = "1D",
    *,
    with_news: bool = False,
    check_broker: bool = False,
) -> str:
    """Vollstaendige Vorabpruefung, bevor ein grosser Lauf startet.

        print(compliance.preflight(n_symbols=500, years=10, with_news=True))

    Beantwortet: Wie lange dauert das, passt es in die Limits, und darf
    das Konto ueberhaupt handeln?
    """
    from .data import estimate_requests

    days = int(years * 365)
    plan = BudgetPlan().add("alpaca_data", estimate_requests(n_symbols, timeframe, days))
    if with_news:
        # Grobe Annahme: ~40 Artikel je Symbol und Jahr, 50 je Antwortseite.
        plan.add("alpaca_news", max(1, int(n_symbols * years * 40 / 50)))

    ok, budget_text = plan.check()
    parts = [
        "=" * 68,
        f"  VORABPRUEFUNG  |  {n_symbols:,} Symbole x {years:g} Jahre ({timeframe})",
        "=" * 68,
        budget_text,
    ]

    if check_broker:
        try:
            status = check_account()
            parts += ["", "Broker-Regeln:", str(status)]
            ok = ok and status.ok
        except Exception as e:  # noqa: BLE001
            parts += ["", f"Kontostatus nicht abrufbar: {type(e).__name__}: {e}"]

    parts += ["", "  ERGEBNIS: " + ("Lauf kann starten." if ok else "Lauf wuerde anstossen - Umfang reduzieren.")]
    return "\n".join(parts)
