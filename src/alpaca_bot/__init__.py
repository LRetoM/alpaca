"""alpaca_bot - Werkzeugkasten fuer Paper-Trading und Marktanalyse mit Alpaca.

Schnellstart:

    from alpaca_bot import data, account, backtest, strategies

    df   = data.ohlcv(data.get_bars("AAPL", "1D", lookback_days=1000), "AAPL")
    sig  = strategies.get("trend_filtered").generate_signals(df)
    res  = backtest.backtest(df["close"], sig)
    print(res.summary())
"""

from . import account, backtest, clients, data, features, indicators, ml, strategies, trading
from .config import get_settings

__version__ = "0.1.0"

__all__ = [
    "account",
    "backtest",
    "clients",
    "data",
    "features",
    "indicators",
    "ml",
    "strategies",
    "trading",
    "get_settings",
]
