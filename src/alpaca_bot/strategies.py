"""Regelbasierte Strategien als Ausgangspunkt und Vergleichsmassstab.

Jede Strategie liefert eine Zielposition je Bar (1 = long, 0 = Cash,
-1 = short). Diese Reihe geht direkt in `backtest.backtest()`.

Diese einfachen Regeln sind absichtlich der erste Schritt: Sie sind die
Messlatte, die ein ML-Modell spaeter schlagen muss. Ein Modell, das
einen 200-Tage-Durchschnitt nicht schlaegt, ist die Komplexitaet nicht wert.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np
import pandas as pd

from . import indicators as ind


class Strategy(ABC):
    name: str = "strategy"

    @abstractmethod
    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        """OHLCV-DataFrame -> Zielposition je Bar."""

    def __repr__(self) -> str:
        params = ", ".join(f"{k}={v}" for k, v in vars(self).items())
        return f"{type(self).__name__}({params})"


class BuyAndHold(Strategy):
    """Die Messlatte. Erstaunlich schwer zu schlagen."""

    name = "buy_and_hold"

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        return pd.Series(1.0, index=df.index)


class SmaCross(Strategy):
    """Trendfolge: long, wenn der schnelle ueber dem langsamen Schnitt liegt.

    Verdient in klaren Trends, verliert in Seitwaertsphasen durch
    Fehlsignale. Klassiker, gut zum Lernen der Mechanik.
    """

    name = "sma_cross"

    def __init__(self, fast: int = 50, slow: int = 200, allow_short: bool = False):
        self.fast, self.slow, self.allow_short = fast, slow, allow_short

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        c = df["close"]
        fast, slow = ind.sma(c, self.fast), ind.sma(c, self.slow)
        sig = np.where(fast > slow, 1.0, -1.0 if self.allow_short else 0.0)
        return pd.Series(sig, index=df.index).where(slow.notna(), 0.0)


class RsiReversion(Strategy):
    """Mean-Reversion: kaufen, wenn ueberverkauft, verkaufen bei Erholung.

    Funktioniert bei Indizes/ETFs besser als bei Einzelaktien - ein Index
    faellt selten wegen einer schlechten Nachricht dauerhaft aus.
    """

    name = "rsi_reversion"

    def __init__(self, window: int = 2, entry: float = 10.0, exit: float = 60.0):
        self.window, self.entry, self.exit = window, entry, exit

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        r = ind.rsi(df["close"], self.window)
        pos, holding = [], 0.0
        for value in r:
            if holding == 0.0 and value < self.entry:
                holding = 1.0
            elif holding == 1.0 and value > self.exit:
                holding = 0.0
            pos.append(holding)
        return pd.Series(pos, index=df.index)


class TrendWithFilter(Strategy):
    """Trendfolge mit Volatilitaets- und Regime-Filter.

    Drei Bedingungen muessen gleichzeitig stimmen:
      1. Kurs ueber dem 200-Tage-Schnitt (langfristiges Regime ist positiv)
      2. MACD-Histogramm positiv (kurzfristiges Momentum stimmt)
      3. Volatilitaet nicht im Panikbereich (kein Griff ins fallende Messer)

    Weniger Trades, aber deutlich weniger Fehlsignale als reines SmaCross.
    """

    name = "trend_filtered"

    def __init__(self, regime: int = 200, vol_max: float = 0.45):
        self.regime, self.vol_max = regime, vol_max

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        c = df["close"]
        above_regime = c > ind.sma(c, self.regime)
        momentum_ok = ind.macd(c)["hist"] > 0
        calm = ind.realized_volatility(c, 20) < self.vol_max
        return (above_regime & momentum_ok & calm).astype(float)


class BollingerBreakout(Strategy):
    """Ausbruch: long, wenn der Kurs das obere Band durchbricht."""

    name = "bollinger_breakout"

    def __init__(self, window: int = 20, n_std: float = 2.0):
        self.window, self.n_std = window, n_std

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        bb = ind.bollinger(df["close"], self.window, self.n_std)
        entry = df["close"] > bb["bb_upper"]
        exit_ = df["close"] < bb["bb_mid"]
        pos, holding = [], 0.0
        for e, x in zip(entry, exit_):
            if e:
                holding = 1.0
            elif x:
                holding = 0.0
            pos.append(holding)
        return pd.Series(pos, index=df.index)


REGISTRY: dict[str, type[Strategy]] = {
    "buy_and_hold": BuyAndHold,
    "sma_cross": SmaCross,
    "rsi_reversion": RsiReversion,
    "trend_filtered": TrendWithFilter,
    "bollinger_breakout": BollingerBreakout,
}


def get(name: str, **kwargs) -> Strategy:
    if name not in REGISTRY:
        raise ValueError(f"Unbekannt: {name}. Verfuegbar: {', '.join(REGISTRY)}")
    return REGISTRY[name](**kwargs)
