#!/usr/bin/env python3
"""Schritt 60: Die Jahresliste - was hätten unsere Bots in jedem Jahr gemacht?

Fuehrt die beiden Straenge zusammen: den Trendbot aus develop (Dual-Momentum auf
ETFs, `trend.py`, derselbe Code wie im Schatten) und die Aktien-Bots der
Labor-Session (Engine-Replays mit `31_simulate_ranking.py`), jeweils mit den
GEMESSENEN Kosten (Spanne 12,2 bps, develop §G51/G54). Ausgegeben wird eine
Tabelle mit der Jahresrendite in Prozent - ohne Mittelung, ohne Auswahl.

Regeln der Liste (nach den Lehren §2.17 und develop §B4/§G53):
  * Jahr = Schlusskurs Vorjahresende bis Schlusskurs Jahresende (kein
    Eroeffnungs-Bias); das letzte Jahr ist ein Teiljahr und steht mit `*`.
  * Jede Zeile nennt Datenquelle, Kosten und ob Survivorship-Bias vorliegt.
  * Der 50/50-Mix rechnet taeglich auf 50/50 zurueck (Naeherung).
  * Nicht enthalten: Zins auf ungenutztes Bargeld bei den Aktien-Bots
    (2009-2015 ohnehin ~0, danach klein) - siehe zusammenfuehrung-develop.md.

    python scripts/60_jahresliste.py
Ergebnis: results/labor/jahresliste.csv und docs/jahresliste-2027.md
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from alpaca_bot import befunde, labor, trend  # noqa: E402
from alpaca_bot.config import PROJECT_ROOT  # noqa: E402
from alpaca_bot.trend_schatten import PHASE2_KANDIDATEN  # noqa: E402

OUT = PROJECT_ROOT / "results" / "labor"
DOC = PROJECT_ROOT / "docs" / "jahresliste-2027.md"
ANFANG, ENDE = "2009-01-01", "2020-11-10"     # gemeinsames Fenster (ML-Vorhersagen ab 2009, Panel-Ende)

REPLAYS_QLIB = {
    "Aktien-Bot Momentum (Handmix, Stop 3, Tor)": "simulate_ranking_qlib_momentum_stop3_h21-63_x0.2_c5_vola_n3_s12.2_kapital.csv",
    "Aktien-Bot Hybrid (Stop 3)": "simulate_ranking_qlib_momentum_stop3_h21-63_x0.2_c5_vola_hybrid_n3_s12.2_kapital.csv",
    "Aktien-Bot Hybrid (Stop nur im Trend)": "simulate_ranking_qlib_momentum_stop3_h21-63_x0.2_c5_vola_hybrid_n3_m99_s12.2_kapital.csv",
    "Aktien-Bot Hybrid (ohne Stop)": "simulate_ranking_qlib_momentum_stop99_h21-63_x0.2_c5_vola_hybrid_n3_s12.2_kapital.csv",
}
REPLAY_SP500 = "simulate_ranking_sp500_close_momentum_stop3_h21-63_x0.2_c5_vola_n3_s12.2_kapital.csv"


def kurve(pfad: Path) -> pd.Series:
    df = pd.read_csv(pfad, index_col=0, parse_dates=True)
    s = df.iloc[:, 0].astype(float)
    s.index = pd.DatetimeIndex(s.index).tz_localize(None) if s.index.tz is None else s.index.tz_convert("UTC").tz_localize(None)
    return s[~s.index.duplicated()].sort_index()


def jahres_renditen(eq: pd.Series, von: str, bis: str) -> dict[int, float]:
    """Jahresende bis Jahresende; Startkurs = letzter Kurs VOR `von` (sonst erster)."""
    eq = eq.dropna()
    out = {}
    jahre = sorted({t.year for t in eq.loc[von:bis].index})
    for j in jahre:
        ende = eq[eq.index.year == j].iloc[-1]
        vor = eq[eq.index.year < j]
        start = vor.iloc[-1] if len(vor) and j > pd.Timestamp(von).year else eq[eq.index.year == j].iloc[0]
        out[j] = float(ende / start - 1)
    return out


def kennzahlen(eq: pd.Series, von: str, bis: str) -> dict:
    e = eq.loc[von:bis].dropna()
    r = e.pct_change().dropna()
    jahre = (e.index[-1] - e.index[0]).days / 365.25
    return {"cagr": float((e.iloc[-1] / e.iloc[0]) ** (1 / jahre) - 1),
            "maxdd": float((e / e.cummax() - 1).min()),
            "sharpe": float(r.mean() / r.std() * np.sqrt(252)) if r.std() > 0 else float("nan")}


def trendbot_kurven() -> dict[str, pd.Series]:
    p = labor.panel_aus_cache(PROJECT_ROOT / "data" / "labor" / "qlib")
    syms = list(dict.fromkeys(trend.UNIVERSEN["broad"] + ["BIL", "AGG"]))
    preise = p.close[[s for s in syms if s in p.close.columns]].copy()
    out = {}
    for name in ("dualmom_15", "dualmom"):
        cfg = PHASE2_KANDIDATEN[name]
        res = trend.run(preise.drop(columns=["AGG"]), cfg, start="2004-06-01", end=ENDE)
        out[name] = res.equity_curve.astype(float)
    # Referenzen: SPY Buy&Hold und 60/40 (SPY/AGG, taeglich auf 60/40 zurueck)
    spy = preise["SPY"].dropna()
    out["SPY"] = spy / spy.iloc[0]
    r = 0.6 * preise["SPY"].pct_change() + 0.4 * preise["AGG"].pct_change()
    out["60/40"] = (1 + r.fillna(0)).cumprod()
    return out


def main() -> int:
    kurven: dict[str, pd.Series] = {}
    t = trendbot_kurven()
    kurven["SPY (Buy & Hold)"] = t["SPY"]
    kurven["60/40 (SPY/AGG)"] = t["60/40"]
    kurven["Trendbot dualmom_15 (Vola-Ziel 15 %)"] = t["dualmom_15"]
    kurven["Trendbot dualmom (Vola-Ziel 10 %)"] = t["dualmom"]
    fehlend = []
    for name, datei in REPLAYS_QLIB.items():
        pfad = OUT / datei
        if pfad.exists():
            kurven[name] = kurve(pfad)
        else:
            fehlend.append(datei)
    if fehlend:
        print("  FEHLT (Replay noch nicht gelaufen):", *fehlend, sep="\n    ")

    # Mix: Trendbot 15 % + bester vorhandener Hybrid, taeglich 50/50
    hybrid_name = next((n for n in ("Aktien-Bot Hybrid (Stop nur im Trend)", "Aktien-Bot Hybrid (Stop 3)", "Aktien-Bot Hybrid (ohne Stop)") if n in kurven), None)
    if hybrid_name:
        a = kurven["Trendbot dualmom_15 (Vola-Ziel 15 %)"].pct_change()
        b = kurven[hybrid_name].pct_change().reindex(a.index)
        gem = (0.5 * a + 0.5 * b.fillna(0)).loc[ANFANG:ENDE]
        kurven[f"MIX 50/50: Trendbot 15 % + {hybrid_name.replace('Aktien-Bot ', '')}"] = (1 + gem.fillna(0)).cumprod()

    jahre = list(range(2009, 2021))
    tab = pd.DataFrame({n: pd.Series(jahres_renditen(k, ANFANG, ENDE)) for n, k in kurven.items()}).reindex(jahre)
    kz = pd.DataFrame({n: kennzahlen(k, ANFANG, ENDE) for n, k in kurven.items()}).T
    tab.loc["CAGR 2009-2020*"] = kz["cagr"]
    tab.loc["Max. Drawdown"] = kz["maxdd"]
    tab.loc["Sharpe"] = kz["sharpe"]
    tab.to_csv(OUT / "jahresliste.csv")

    pd.set_option("display.width", 250)
    def f(v, zeile):
        if pd.isna(v):
            return "–"
        return f"{v:.2f}" if zeile == "Sharpe" else f"{v * 100:+.1f} %"
    print("\n  JAHRESRENDITEN in %, nach Kosten (Spanne 12,2 bps + 5 bps Slippage je Seite), qlib 2009 - 10.11.2020")
    for zeile in tab.index:
        print(f"  {str(zeile):<18}" + "".join(f"{f(tab.loc[zeile, c], zeile):>11}" for c in tab.columns))
    print("  Spalten:", *[f"[{i}] {c}" for i, c in enumerate(tab.columns)], sep="\n    ")

    # S&P-Fenster fuer den Aktien-Bot (Obergrenze wegen Survivorship)
    sp = OUT / REPLAY_SP500
    if sp.exists():
        s = kurve(sp)
        r = jahres_renditen(s, "2016-01-01", "2026-12-31")
        print("\n  Aktien-Bot Momentum auf S&P-500-Panel 2016 - 09/2026 (Obergrenze, Survivorship):")
        print("   " + "  ".join(f"{j}: {v * 100:+.1f} %" for j, v in r.items()))
        k = kennzahlen(s, "2016-01-01", "2026-12-31")
        print(f"   CAGR {k['cagr'] * 100:.1f} %  MaxDD {k['maxdd'] * 100:.1f} %  Sharpe {k['sharpe']:.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
