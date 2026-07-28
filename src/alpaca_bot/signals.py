"""Mehrfaktor-Bewertung: wann deuten MEHRERE Anzeichen auf einen Ausbruch?

Kein Einzelsignal in diesem Projekt hat einen IC ueber ~0.05. Der Wert
entsteht erst durch Kombination schwacher, moeglichst wenig korrelierter
Anzeichen - genau das, was ein Mensch nicht gleichzeitig ueberblicken
kann und ein System schon.

Die sechs Bausteine, nach erwartetem Beitrag:

  1. Regime-Filter     - laeuft der Wert ueberhaupt aufwaerts? (Tor, kein Punkt)
  2. Momentum          - 3- und 12-Monats-Staerke                    ★★★★★
  3. Naehe zum 52-W-Hoch - George & Hwang (2004)                     ★★★★☆
  4. Vola-Kompression  - enge Spanne geht Bewegungen voraus          ★★★★☆
  5. Volumenanstieg    - Aufmerksamkeit/Akkumulation                 ★★★☆☆
  6. Insider-Cluster   - stark, aber SELTEN (Verstaerker, kein Tor)  ★★★★☆

Zu Punkt 6: Eine Messung ueber gemischte Symbole ergab, dass nur etwa
jeder dritte Wert ueberhaupt einen echten Marktkauf aufweist und
Cluster aus mehreren Kaeufern die Ausnahme sind. Deshalb ist der
Insider-Score ein additiver Bonus - waere er Pflichtbedingung, gaebe es
fast nie ein Signal.

Alle Bausteine sind strikt kausal und werden von
`pit.audit_feature_function` geprueft.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import indicators as ind


@dataclass
class SignalWeights:
    """Gewichte der Bausteine. Summe der Kernfaktoren = 1.0.

    Bewusst runde, gleichmaessige Werte statt optimierter Nachkommastellen:
    Auf der Historie feinjustierte Gewichte sind der schnellste Weg zur
    Ueberanpassung. Wer hier optimiert, optimiert den Zufall.
    """

    momentum: float = 0.30
    near_high: float = 0.25
    compression: float = 0.20
    volume: float = 0.25
    insider_bonus: float = 0.35
    """Additiver Bonus obendrauf - kann den Score ueber 1.0 heben."""

    require_regime: bool = True
    """Nur Werte ueber dem 200-Tage-Schnitt zulassen."""
    max_volatility: float = 1.20
    """Werte mit hoeherer Jahresvolatilitaet ausschliessen (Zockerpapiere)."""


def _pct_rank(s: pd.Series, window: int = 252) -> pd.Series:
    """Rang des aktuellen Werts in seiner eigenen Historie (0 bis 1).

    Rollierend berechnet, damit kein Wissen aus der Zukunft einfliesst -
    ein globales `rank(pct=True)` waere genau so ein Leck.
    """
    return s.rolling(window, min_periods=max(20, window // 5)).apply(
        lambda w: (w[-1] > w[:-1]).mean() if len(w) > 1 else 0.5, raw=True
    )


def build_signal_frame(
    df: pd.DataFrame,
    insider: pd.DataFrame | None = None,
    weights: SignalWeights | None = None,
) -> pd.DataFrame:
    """Berechnet alle Bausteine und den Gesamtscore je Bar.

    Args:
        df: OHLCV eines Symbols.
        insider: optionale Insider-Merkmale aus `edgar.insider_features`,
            auf demselben Index.

    Returns:
        DataFrame mit den Einzelbausteinen und Spalte `score`.
    """
    w = weights or SignalWeights()
    c = df["close"].astype(float)
    out = pd.DataFrame(index=df.index)

    # --- 1. Regime: langfristige Richtung ---
    sma200 = ind.sma(c, 200)
    out["regime_ok"] = (c > sma200).astype(float)

    # --- 2. Momentum ueber zwei Horizonte ---
    mom_3m = c.pct_change(63)
    mom_12m = c.pct_change(252).shift(21)  # 12-1: letzter Monat ausgespart
    out["mom_3m"] = mom_3m
    out["mom_12m"] = mom_12m
    out["f_momentum"] = (
        0.5 * _pct_rank(mom_3m) + 0.5 * _pct_rank(mom_12m)
    ).fillna(0.0)

    # --- 3. Naehe zum 52-Wochen-Hoch ---
    high_52w = c.rolling(252, min_periods=60).max()
    dist = c / high_52w
    out["dist_52w_high"] = dist
    # 1.0 = am Hoch, 0.0 = 30 % oder mehr darunter
    out["f_near_high"] = ((dist - 0.70) / 0.30).clip(0, 1).fillna(0.0)

    # --- 4. Volatilitaets-Kompression ---
    bb = ind.bollinger(c, 20)
    width = bb["bb_width"]
    out["bb_width"] = width
    # Enge Spanne = hoher Score, deshalb invertierter Rang
    out["f_compression"] = (1 - _pct_rank(width)).fillna(0.0)

    # --- 5. Volumen-Anstieg ---
    if "volume" in df.columns:
        v = df["volume"].astype(float)
        dollar_vol = v * c
        vz = ind.zscore(dollar_vol, 20)
        out["vol_z"] = vz
        out["f_volume"] = (vz / 3).clip(0, 1).fillna(0.0)
        out["dollar_volume"] = dollar_vol.rolling(20).mean()
    else:
        out["f_volume"] = 0.0
        out["dollar_volume"] = np.nan

    # --- 6. Insider-Cluster als Bonus ---
    if insider is not None and not insider.empty:
        from .edgar import cluster_score

        aligned = insider.reindex(df.index).ffill().fillna(0.0)
        out["f_insider"] = cluster_score(aligned).fillna(0.0)
    else:
        out["f_insider"] = 0.0

    # --- Risikofilter ---
    vol_annual = ind.realized_volatility(c, 20)
    out["volatility"] = vol_annual
    out["risk_ok"] = (vol_annual < w.max_volatility).astype(float)
    out["atr"] = ind.atr(df, 14) if {"high", "low"}.issubset(df.columns) else np.nan
    out["atr_pct"] = out["atr"] / c

    # --- Gesamtscore ---
    core = (
        w.momentum * out["f_momentum"]
        + w.near_high * out["f_near_high"]
        + w.compression * out["f_compression"]
        + w.volume * out["f_volume"]
    )
    score = core + w.insider_bonus * out["f_insider"]

    gate = out["risk_ok"]
    if w.require_regime:
        gate = gate * out["regime_ok"]
    out["score"] = (score * gate).fillna(0.0)

    return out


def explain(row: pd.Series, weights: SignalWeights | None = None) -> dict:
    """Zerlegt einen Score in seine Bestandteile - fuer das Protokoll.

    Genau diese Aufschluesselung wandert in `journal.decision(reasons=...)`.
    Ohne sie laesst sich spaeter nicht auswerten, WELCHER Grund funktioniert
    hat - und dann ist das Protokoll Buchhaltung statt Lernmaterial.
    """
    w = weights or SignalWeights()
    return {
        "score": round(float(row.get("score", 0)), 4),
        "momentum": round(float(row.get("f_momentum", 0)), 3),
        "naehe_52w_hoch": round(float(row.get("f_near_high", 0)), 3),
        "vola_kompression": round(float(row.get("f_compression", 0)), 3),
        "volumen_anstieg": round(float(row.get("f_volume", 0)), 3),
        "insider_cluster": round(float(row.get("f_insider", 0)), 3),
        "regime_ok": bool(row.get("regime_ok", 0)),
        "volatilitaet": round(float(row.get("volatility", 0)), 3),
        "atr_pct": round(float(row.get("atr_pct", 0) or 0), 4),
    }


def rank_candidates(
    scores: dict[str, pd.Series], as_of: pd.Timestamp, top_n: int = 10,
    min_score: float = 0.55
) -> list[tuple[str, float]]:
    """Rangliste aller Symbole zum Zeitpunkt `as_of`.

    Querschnittsvergleich statt Einzelurteil: nicht "ist AAPL gut?",
    sondern "welche 10 der 500 sind heute am aussichtsreichsten?" - das
    ist nachweislich die leichtere Frage (siehe strategie-analyse.md).
    """
    ranked = []
    for sym, s in scores.items():
        if as_of not in s.index:
            continue
        val = float(s.loc[as_of])
        if np.isfinite(val) and val >= min_score:
            ranked.append((sym, val))
    ranked.sort(key=lambda kv: -kv[1])
    return ranked[:top_n]
