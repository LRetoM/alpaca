"""Marktdaten holen: historische Bars, aktuelle Quotes, Snapshots.

Wichtig beim kostenlosen Alpaca-Plan:
  * Aktien-Feed = IEX (real-time, aber nur ~2 % des US-Handelsvolumens).
    Fuer Tages-Bars/Backtests reicht das gut; fuer Sekunden-Scalping nicht.
  * SIP (alle Boersen) gibt es historisch nur mit 15 Minuten Verzoegerung
    (Feed "delayed_sip") bzw. real-time nur im kostenpflichtigen Plan.
  * Krypto ist komplett kostenlos und vollstaendig.
  * Rate-Limit: 200 Requests/Minute.
"""

from __future__ import annotations

import datetime as dt
import hashlib
from typing import Iterable, Sequence

import pandas as pd
from alpaca.data.enums import Adjustment, DataFeed
from alpaca.data.requests import (
    CryptoBarsRequest,
    StockBarsRequest,
    StockLatestQuoteRequest,
    StockSnapshotRequest,
)
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

from .clients import crypto_data_client, data_feed, stock_data_client
from .config import CACHE_DIR
from .ratelimit import RateLimiter, with_retry

# Jeder Marktdaten-Aufruf laeuft durch diese Drossel (200/min, Basic-Plan).
_limit = RateLimiter("alpaca_data")

# Bars pro Antwortseite laut API. alpaca-py blaettert INTERN weiter - ein
# get_stock_bars() kann also viele HTTP-Requests sein. Wird das ignoriert,
# reisst ein einziger grosser Abruf das Minutenlimit.
_BARS_PER_PAGE = 10_000

_BARS_PER_DAY = {
    "1Min": 390, "5Min": 78, "15Min": 26, "1H": 7, "4H": 2, "1D": 1, "1W": 0.2,
}


def estimate_requests(n_symbols: int, timeframe: str, days: int) -> int:
    """Wie viele HTTP-Requests kostet ein Abruf wirklich? (Paginierung!)"""
    per_day = _BARS_PER_DAY.get(str(timeframe), 1)
    total_bars = n_symbols * days * per_day
    return max(1, int(-(-total_bars // _BARS_PER_PAGE)))


def _utc(x) -> pd.Timestamp:
    """Beliebige Zeitangabe -> UTC-Timestamp, egal ob naiv oder mit Zeitzone."""
    t = pd.Timestamp(x)
    return t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")


def _span_days(start, end) -> int:
    """Laenge des angefragten Zeitraums in Tagen - fuer die Request-Schaetzung."""
    now = pd.Timestamp.now(tz="UTC")
    s = _utc(start) if start is not None else now
    e = _utc(end) if end is not None else now
    return max(1, int((e - s).days))

# Kuerzel -> TimeFrame, damit Skripte "1D" statt Enum-Gebastel nutzen koennen.
TIMEFRAMES: dict[str, TimeFrame] = {
    "1Min": TimeFrame.Minute,
    "5Min": TimeFrame(5, TimeFrameUnit.Minute),
    "15Min": TimeFrame(15, TimeFrameUnit.Minute),
    "1H": TimeFrame.Hour,
    "4H": TimeFrame(4, TimeFrameUnit.Hour),
    "1D": TimeFrame.Day,
    "1W": TimeFrame.Week,
}


def parse_timeframe(tf: str | TimeFrame) -> TimeFrame:
    if isinstance(tf, TimeFrame):
        return tf
    try:
        return TIMEFRAMES[tf]
    except KeyError:
        raise ValueError(
            f"Unbekannter Timeframe {tf!r}. Erlaubt: {', '.join(TIMEFRAMES)}"
        ) from None


def _as_list(symbols: str | Iterable[str]) -> list[str]:
    return [symbols] if isinstance(symbols, str) else list(symbols)


def _cache_key(syms: list[str], tf, start, end) -> str:
    """Schluessel fuer den Bar-Cache - stabil ueber Prozessgrenzen hinweg.

    Zwei Fehler steckten in der Vorgaengerfassung, und beide machten den
    Cache zu totem Code (Befund 21.08.2026, `docs/BEFUNDE.md` §G11):

    1. `hash()` auf einen String ist in Python **pro Prozess
       randomisiert** (PYTHONHASHSEED). Derselbe Abruf bekam bei jedem
       Programmstart einen anderen Dateinamen - ein Treffer war
       ausgeschlossen. Deshalb sha256 statt hash().
    2. `start` ist bei Aufruf mit `lookback_days` ein
       `datetime.now()`-Wert **mit Mikrosekunden**. Der Schluessel war
       damit bei jedem Aufruf verschieden, sogar innerhalb eines
       Prozesses. Deshalb auf den Tag normalisiert.

    Die Tagesgenauigkeit ist fuer Tages-Bars richtig: zwei Abrufe
    desselben Zeitraums am selben Tag liefern dieselben Daten. Bei
    Intraday-Zeitraeumen greift `tf` als Unterscheidung mit ein.
    """
    def _tag(x) -> str:
        if x is None:
            return "None"
        if isinstance(x, dt.datetime):
            return x.date().isoformat()
        return str(x)[:10]

    roh = f"{','.join(sorted(syms))}|{tf}|{_tag(start)}|{_tag(end)}"
    return hashlib.sha256(roh.encode()).hexdigest()[:32]


def get_bars(
    symbols: str | Sequence[str],
    timeframe: str | TimeFrame = "1D",
    start: str | dt.datetime | None = None,
    end: str | dt.datetime | None = None,
    *,
    lookback_days: int | None = None,
    adjustment: Adjustment = Adjustment.ALL,
    feed: DataFeed | None = None,
    use_cache: bool = False,
) -> pd.DataFrame:
    """Historische Aktien-Bars als DataFrame.

    Rueckgabe: MultiIndex (symbol, timestamp) mit
    open/high/low/close/volume/trade_count/vwap.

    `adjustment=ALL` rechnet Splits und Dividenden ein - Pflicht fuer
    Backtests, sonst sieht ein Aktiensplit wie ein 50-%-Crash aus.
    """
    syms = _as_list(symbols)
    tf = parse_timeframe(timeframe)

    if start is None:
        days = lookback_days if lookback_days is not None else 365 * 2
        start = dt.datetime.now(dt.UTC) - dt.timedelta(days=days)

    cache_file = None
    if use_cache:
        cache_file = CACHE_DIR / f"{_cache_key(syms, tf, start, end)}.csv"
        if cache_file.exists():
            df = pd.read_csv(cache_file, parse_dates=["timestamp"])
            return df.set_index(["symbol", "timestamp"]).sort_index()

    req = StockBarsRequest(
        symbol_or_symbols=syms,
        timeframe=tf,
        start=start,
        end=end,
        adjustment=adjustment,
        feed=feed or data_feed(),
    )
    _limit.acquire(estimate_requests(len(syms), str(timeframe), _span_days(start, end)))
    df = with_retry(lambda: stock_data_client().get_stock_bars(req).df)

    if df.empty:
        return df
    df = df.sort_index()
    if cache_file is not None:
        df.reset_index().to_csv(cache_file, index=False)
    return df


def get_crypto_bars(
    symbols: str | Sequence[str] = "BTC/USD",
    timeframe: str | TimeFrame = "1D",
    start: str | dt.datetime | None = None,
    end: str | dt.datetime | None = None,
    *,
    lookback_days: int = 365,
) -> pd.DataFrame:
    """Krypto-Bars (Symbol-Format: 'BTC/USD', 'ETH/USD'). Kostenlos & 24/7."""
    if start is None:
        start = dt.datetime.now(dt.UTC) - dt.timedelta(days=lookback_days)
    syms = _as_list(symbols)
    req = CryptoBarsRequest(
        symbol_or_symbols=syms,
        timeframe=parse_timeframe(timeframe),
        start=start,
        end=end,
    )
    _limit.acquire(estimate_requests(len(syms), str(timeframe), _span_days(start, end)))
    return with_retry(lambda: crypto_data_client().get_crypto_bars(req).df).sort_index()


def ohlcv(df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """Ein Symbol aus dem MultiIndex-DataFrame als flache Zeitreihe."""
    if isinstance(df.index, pd.MultiIndex):
        out = df.xs(symbol, level="symbol").copy()
    else:
        out = df.copy()
    out.index = pd.DatetimeIndex(out.index)
    return out


def close_matrix(df: pd.DataFrame) -> pd.DataFrame:
    """MultiIndex-Bars -> Matrix mit Zeit als Index und Symbolen als Spalten.

    Praktisch fuer Korrelationen, Portfolio-Backtests und ML-Features.
    """
    return df["close"].unstack(level="symbol").sort_index()


def latest_quotes(
    symbols: str | Sequence[str], *, feed: DataFeed | str | None = None
) -> pd.DataFrame:
    """Aktuelle Geld-/Briefkurse (Bid/Ask).

    `feed` ueberschreibt den Feed aus der .env. Sinnvoll fuer den
    Spannen-Vergleich: der kostenlose Standard ist `iex` (~2 % des
    US-Volumens, §G29); `delayed_sip` liefert die konsolidierte NBBO mit
    ~15 Minuten Verzoegerung - fuer eine Spannen-Charakterisierung
    (nicht fuers Handeln) ist die Verzoegerung ohne Belang.
    """
    verwendet = DataFeed(feed) if isinstance(feed, str) else (feed or data_feed())
    req = StockLatestQuoteRequest(
        symbol_or_symbols=_as_list(symbols), feed=verwendet
    )
    _limit.acquire()
    quotes = with_retry(lambda: stock_data_client().get_stock_latest_quote(req))
    rows = [
        {
            "symbol": sym,
            "bid": q.bid_price,
            "bid_size": q.bid_size,
            "ask": q.ask_price,
            "ask_size": q.ask_size,
            "spread": round(q.ask_price - q.bid_price, 4),
            "timestamp": q.timestamp,
        }
        for sym, q in quotes.items()
    ]
    return pd.DataFrame(rows).set_index("symbol")


def snapshots(symbols: str | Sequence[str]) -> pd.DataFrame:
    """Momentaufnahme: letzter Trade, Quote, Tages-Bar und Vortages-Bar.

    Ein Request statt vier - der schnellste Weg zu einem Markt-Ueberblick.
    """
    req = StockSnapshotRequest(
        symbol_or_symbols=_as_list(symbols), feed=data_feed()
    )
    _limit.acquire()
    snaps = with_retry(lambda: stock_data_client().get_stock_snapshot(req))
    rows = []
    for sym, s in snaps.items():
        day, prev = s.daily_bar, s.previous_daily_bar
        last = s.latest_trade.price if s.latest_trade else None
        change = None
        if last is not None and prev is not None and prev.close:
            change = round((last / prev.close - 1) * 100, 2)
        rows.append(
            {
                "symbol": sym,
                "last": last,
                "change_pct": change,
                "open": day.open if day else None,
                "high": day.high if day else None,
                "low": day.low if day else None,
                "volume": day.volume if day else None,
                "prev_close": prev.close if prev else None,
            }
        )
    return pd.DataFrame(rows).set_index("symbol")
