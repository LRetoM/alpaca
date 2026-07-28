"""Fabrik-Funktionen fuer die Alpaca-Clients.

Alpaca trennt zwei Welten:
  * Trading API  -> Konto, Orders, Positionen      (paper- oder live-Endpoint)
  * Market Data  -> Kurse, Bars, Quotes, Streams   (ein Endpoint fuer beide)
"""

from __future__ import annotations

from functools import lru_cache

from alpaca.data.enums import DataFeed
from alpaca.data.historical import (
    CryptoHistoricalDataClient,
    StockHistoricalDataClient,
)
from alpaca.data.live import CryptoDataStream, StockDataStream
from alpaca.trading.client import TradingClient

from .config import Settings, get_settings


@lru_cache(maxsize=1)
def trading_client() -> TradingClient:
    """Konto & Orders. `paper=True` zeigt auf https://paper-api.alpaca.markets."""
    s = get_settings()
    return TradingClient(s.api_key, s.secret_key, paper=s.paper)


@lru_cache(maxsize=1)
def stock_data_client() -> StockHistoricalDataClient:
    s = get_settings()
    return StockHistoricalDataClient(s.api_key, s.secret_key)


@lru_cache(maxsize=1)
def crypto_data_client() -> CryptoHistoricalDataClient:
    """Krypto-Marktdaten sind bei Alpaca komplett kostenlos (kein Feed-Limit)."""
    s = get_settings()
    return CryptoHistoricalDataClient(s.api_key, s.secret_key)


def stock_stream() -> StockDataStream:
    """WebSocket fuer Live-Kurse. Nicht gecacht: Streams sind Einweg-Objekte."""
    s = get_settings()
    return StockDataStream(s.api_key, s.secret_key, feed=data_feed(s))


def crypto_stream() -> CryptoDataStream:
    s = get_settings()
    return CryptoDataStream(s.api_key, s.secret_key)


def data_feed(settings: Settings | None = None) -> DataFeed:
    """String aus der .env -> DataFeed-Enum."""
    s = settings or get_settings()
    return DataFeed(s.data_feed)
