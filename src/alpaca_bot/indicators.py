"""Technische Indikatoren - bewusst selbst implementiert.

Kein Fremdpaket noetig, jede Formel ist nachlesbar, und alle Funktionen
arbeiten strikt kausal: kein Wert benutzt Daten aus der Zukunft.
Das ist die Hauptfehlerquelle bei selbstgebauten Backtests.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def sma(s: pd.Series, window: int = 20) -> pd.Series:
    """Einfacher gleitender Durchschnitt."""
    return s.rolling(window, min_periods=window).mean()


def ema(s: pd.Series, span: int = 20) -> pd.Series:
    """Exponentieller Durchschnitt - reagiert schneller als SMA."""
    return s.ewm(span=span, adjust=False, min_periods=span).mean()


def rsi(s: pd.Series, window: int = 14) -> pd.Series:
    """Relative Strength Index (0-100).

    Klassisch: >70 = ueberkauft, <30 = ueberverkauft. In starken Trends
    bleibt der RSI aber lange extrem - allein taugt er nicht als Signal.
    """
    delta = s.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / window, adjust=False, min_periods=window).mean()
    avg_loss = loss.ewm(alpha=1 / window, adjust=False, min_periods=window).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(50)


def macd(
    s: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9
) -> pd.DataFrame:
    """MACD-Linie, Signallinie und Histogramm (Momentum-Wechsel)."""
    macd_line = ema(s, fast) - ema(s, slow)
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    return pd.DataFrame(
        {
            "macd": macd_line,
            "signal": signal_line,
            "hist": macd_line - signal_line,
        }
    )


def bollinger(s: pd.Series, window: int = 20, n_std: float = 2.0) -> pd.DataFrame:
    """Bollinger-Baender + %B (Position im Band, 0 = unten, 1 = oben)."""
    mid = sma(s, window)
    sd = s.rolling(window, min_periods=window).std()
    upper, lower = mid + n_std * sd, mid - n_std * sd
    return pd.DataFrame(
        {
            "bb_mid": mid,
            "bb_upper": upper,
            "bb_lower": lower,
            "bb_width": (upper - lower) / mid,
            "bb_pct": (s - lower) / (upper - lower),
        }
    )


def atr(df: pd.DataFrame, window: int = 14) -> pd.Series:
    """Average True Range: durchschnittliche Tagesschwankung in Kurs-Einheiten.

    Die praktischste Groesse fuer Positionsgroesse und Stop-Abstand:
    Stop = Einstieg - 2 * ATR passt sich automatisch der Volatilitaet an.
    """
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)
    return tr.ewm(alpha=1 / window, adjust=False, min_periods=window).mean()


def realized_volatility(s: pd.Series, window: int = 20, periods: int = 252) -> pd.Series:
    """Annualisierte Volatilitaet aus log-Renditen."""
    return np.log(s / s.shift(1)).rolling(window).std() * np.sqrt(periods)


def zscore(s: pd.Series, window: int = 20) -> pd.Series:
    """Wie viele Standardabweichungen liegt der Wert vom Mittel entfernt?"""
    m = s.rolling(window, min_periods=window).mean()
    sd = s.rolling(window, min_periods=window).std()
    return (s - m) / sd


def rolling_drawdown(equity: pd.Series) -> pd.Series:
    """Aktueller Rueckgang vom bisherigen Hoechststand (negativ, in %)."""
    return equity / equity.cummax() - 1


def add_all(df: pd.DataFrame, close_col: str = "close") -> pd.DataFrame:
    """Haengt einen Standard-Satz Indikatoren an ein OHLCV-DataFrame."""
    out = df.copy()
    c = out[close_col]

    out["sma_20"] = sma(c, 20)
    out["sma_50"] = sma(c, 50)
    out["sma_200"] = sma(c, 200)
    out["ema_12"] = ema(c, 12)
    out["rsi_14"] = rsi(c, 14)
    out = out.join(macd(c))
    out = out.join(bollinger(c))
    if {"high", "low"}.issubset(out.columns):
        out["atr_14"] = atr(out, 14)
        out["atr_pct"] = out["atr_14"] / c
    out["vol_20"] = realized_volatility(c, 20)
    out["ret_1"] = c.pct_change()
    out["dist_sma200"] = c / out["sma_200"] - 1
    return out
