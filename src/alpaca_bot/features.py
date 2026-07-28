"""Feature-Engineering fuer Machine Learning auf Kursdaten.

Der wichtigste Punkt: ein Modell auf Rohkursen zu trainieren
funktioniert nicht. Kurse sind nicht stationaer - der Bereich 400-450
kam in den Trainingsdaten vor, 600 nie. Das Modell muss stattdessen
*relative, stationaere* Groessen sehen: Renditen, Abstaende zu
Durchschnitten in Prozent, Verhaeltnisse, Rangwerte.

Jedes Feature hier ist strikt kausal (nutzt nur Vergangenheit).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import indicators as ind


def build_features(df: pd.DataFrame, market: pd.Series | None = None) -> pd.DataFrame:
    """OHLCV -> Feature-Matrix.

    Args:
        df: OHLCV eines Symbols mit DatetimeIndex.
        market: optionale Referenz-Zeitreihe (z. B. SPY-Schlusskurse),
            um relative Staerke gegenueber dem Gesamtmarkt zu messen.
    """
    c, X = df["close"], pd.DataFrame(index=df.index)

    # --- Renditen ueber mehrere Horizonte: kurzfristige Umkehr vs. Momentum
    for n in (1, 2, 3, 5, 10, 21, 63):
        X[f"ret_{n}"] = c.pct_change(n)

    # --- Abstand zu gleitenden Durchschnitten (in %, damit skalenfrei)
    for w in (10, 20, 50, 200):
        X[f"dist_sma_{w}"] = c / ind.sma(c, w) - 1

    # --- Momentum / Oszillatoren
    X["rsi_2"] = ind.rsi(c, 2) / 100
    X["rsi_14"] = ind.rsi(c, 14) / 100
    m = ind.macd(c)
    X["macd_hist"] = m["hist"] / c
    X["macd_cross"] = np.sign(m["macd"] - m["signal"])

    # --- Volatilitaet und Bandlage
    bb = ind.bollinger(c, 20)
    X["bb_pct"] = bb["bb_pct"]
    X["bb_width"] = bb["bb_width"]
    X["vol_10"] = ind.realized_volatility(c, 10)
    X["vol_60"] = ind.realized_volatility(c, 60)
    X["vol_ratio"] = X["vol_10"] / X["vol_60"]  # steigende Nervositaet?

    if {"high", "low"}.issubset(df.columns):
        X["atr_pct"] = ind.atr(df, 14) / c
        X["range_pct"] = (df["high"] - df["low"]) / c
        # Wo im Tagesbereich schloss der Kurs? Naehe Hoch = Staerke.
        span = (df["high"] - df["low"]).replace(0, np.nan)
        X["close_loc"] = (c - df["low"]) / span

    # --- Volumen relativ zum eigenen Durchschnitt
    if "volume" in df.columns:
        v = df["volume"].astype(float)
        X["vol_z"] = ind.zscore(v, 20)
        X["dollar_vol_z"] = ind.zscore(v * c, 20)

    # --- Drawdown-Zustand: wie weit unter dem letzten Hoch?
    X["drawdown"] = c / c.cummax() - 1
    X["days_since_high"] = (
        pd.Series(np.arange(len(c)), index=c.index)
        - pd.Series(np.arange(len(c)), index=c.index).where(c == c.cummax()).ffill()
    )

    # --- Relative Staerke gegenueber dem Markt
    if market is not None:
        mkt = market.reindex(c.index).ffill()
        X["rel_strength_21"] = c.pct_change(21) - mkt.pct_change(21)
        X["mkt_ret_5"] = mkt.pct_change(5)
        X["mkt_above_sma200"] = (mkt > ind.sma(mkt, 200)).astype(float)

    # --- Kalender (Saisonalitaeten sind schwach, aber messbar)
    X["dow"] = c.index.dayofweek
    X["month"] = c.index.month

    return X.replace([np.inf, -np.inf], np.nan)


def make_label(
    df: pd.DataFrame,
    horizon: int = 5,
    kind: str = "binary",
    threshold: float = 0.0,
) -> pd.Series:
    """Zielvariable aus zukuenftigen Renditen.

    kind:
        'binary'    -> 1, wenn Rendite ueber `horizon` Bars > threshold
        'return'    -> die Rendite selbst (Regression)
        'triple'    -> -1/0/1 mit neutraler Zone (robuster gegen Rauschen)

    Achtung: Das Label schaut per Definition in die Zukunft. Deshalb
    MUSS beim Training ein Embargo von `horizon` Bars zwischen Trainings-
    und Testfenster liegen - siehe `ml.walk_forward_predict`.
    """
    fwd = df["close"].shift(-horizon) / df["close"] - 1

    if kind == "return":
        return fwd.rename("y")
    if kind == "binary":
        return (fwd > threshold).astype(int).where(fwd.notna()).rename("y")
    if kind == "triple":
        band = threshold if threshold > 0 else fwd.std() * 0.5
        y = pd.Series(0, index=fwd.index, dtype=float)
        y[fwd > band] = 1
        y[fwd < -band] = -1
        return y.where(fwd.notna()).rename("y")
    raise ValueError(f"kind muss binary|return|triple sein, nicht {kind!r}")


def prepare(
    df: pd.DataFrame,
    horizon: int = 5,
    kind: str = "binary",
    market: pd.Series | None = None,
    threshold: float = 0.0,
) -> tuple[pd.DataFrame, pd.Series]:
    """Fertige, ausgerichtete (X, y) ohne NaN-Zeilen."""
    X = build_features(df, market=market)
    y = make_label(df, horizon=horizon, kind=kind, threshold=threshold)
    data = X.join(y).dropna()
    return data.drop(columns="y"), data["y"]
