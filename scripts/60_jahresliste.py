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

    python scripts/60_jahresliste.py                 # qlib 2009-2020 (Vergleich aller Bots)
    python scripts/60_jahresliste.py --bis2026       # sp500_close 2016-2026 (einziges Panel bis 2026 im Container)
    python scripts/60_jahresliste.py --panel projekt # beliebiges Panel, z. B. Projektcache 2018-2026 auf dem Mac
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


ETFS_BIS_2026 = ["SPY", "QQQ", "TLT", "HYG", "LQD"]     # alles, was das Panel bis 2026 an ETFs hat


def bis_2026() -> int:
    """Fenster 2016 - 09/2026 auf dem einzigen Panel, das bis 2026 reicht (sp500_close).

    Grenzen, die im Ergebnis stehen muessen: nur Schlusskurse, nur heutige S&P-Mitglieder
    (Survivorship), fuer den Trendbot nur fuenf ETFs statt zehn und Bargeld pauschal
    verzinst (kein BIL). Die Verkleinerung des Trendbots wird an 2016-2020 gegen den
    vollen Lauf auf dem qlib-Panel gemessen."""
    q = labor.panel_aus_cache(PROJECT_ROOT / "data" / "labor" / "qlib").close
    sp = labor.panel_aus_cache(PROJECT_ROOT / "data" / "labor" / "sp500_close").close
    cfg = PHASE2_KANDIDATEN["dualmom_15"]
    from dataclasses import replace
    cfg_pauschal = replace(cfg, cash_symbol="", cash_rendite_pa=0.02)

    voll = trendbot_kurven()["dualmom_15"]
    klein_q = trend.run(q[ETFS_BIS_2026], cfg_pauschal, start="2004-06-01", end="2020-11-10").equity_curve.astype(float)
    klein_sp = trend.run(sp[ETFS_BIS_2026], cfg_pauschal, start="2015-01-01", end="2026-09-28").equity_curve.astype(float)
    r_voll = jahres_renditen(voll, "2016-01-01", "2020-12-31")
    r_klein = jahres_renditen(klein_q, "2016-01-01", "2020-12-31")
    print("\n  PRUEFUNG DER VERKLEINERUNG (Trendbot 15 %, qlib-Daten): voller Lauf (10 ETFs + BIL) gegen 5 ETFs + Pauschale")
    for j in r_voll:
        print(f"   {j}: voll {r_voll[j] * 100:+6.1f} %   klein {r_klein[j] * 100:+6.1f} %   Abstand {(r_klein[j] - r_voll[j]) * 100:+5.1f}")
    cv, ck = kennzahlen(voll, "2016-01-01", "2020-11-10"), kennzahlen(klein_q, "2016-01-01", "2020-11-10")
    print(f"   CAGR voll {cv['cagr'] * 100:.1f} %  klein {ck['cagr'] * 100:.1f} %   MaxDD voll {cv['maxdd'] * 100:.1f} %  klein {ck['maxdd'] * 100:.1f} %")

    aktien = kurve(OUT / REPLAY_SP500)
    spy = sp["SPY"].dropna(); spy = spy / spy.iloc[0]
    a = klein_sp.pct_change(); b = aktien.pct_change().reindex(a.index)
    mix = (1 + (0.5 * a + 0.5 * b.fillna(0)).loc["2016-01-04":]).cumprod()
    reihen = {"SPY": spy, "Aktien-Bot Momentum (S&P-Panel)": aktien, "Trendbot 15 % (5 ETFs)": klein_sp, "Mix 50/50": mix}
    von, bis = "2016-01-01", "2026-12-31"
    tab = pd.DataFrame({n: pd.Series(jahres_renditen(k, von, bis)) for n, k in reihen.items()})
    print("\n  JAHRESRENDITEN 2016 - 28.09.2026 (sp500_close, Kosten 12,2 + 5 bps; Aktien-Bot Survivorship-Obergrenze)")
    print(f"  {'Jahr':<6}" + "".join(f"{n[:24]:>26}" for n in tab.columns))
    for j in tab.index:
        print(f"  {j:<6}" + "".join(f"{tab.loc[j, c] * 100:>+25.1f} %" for c in tab.columns))
    kz = {n: kennzahlen(k, "2017-01-01", "2026-12-31") for n, k in reihen.items()}
    print(f"  {'CAGR':<6}" + "".join(f"{kz[c]['cagr'] * 100:>+25.1f} %" for c in tab.columns) + "   (2017 - 09/2026)")
    print(f"  {'MaxDD':<6}" + "".join(f"{kz[c]['maxdd'] * 100:>+25.1f} %" for c in tab.columns))
    print(f"  {'Sharpe':<6}" + "".join(f"{kz[c]['sharpe']:>26.2f}" for c in tab.columns))
    tab.to_csv(OUT / "jahresliste_bis2026.csv")
    # Abstand S&P-Panel gegen qlib fuer denselben Bot in den gemeinsamen Jahren 2017-2020
    qk = kurve(OUT / REPLAYS_QLIB["Aktien-Bot Momentum (Handmix, Stop 3, Tor)"])
    rq, rs = jahres_renditen(qk, "2017-01-01", "2020-11-10"), jahres_renditen(aktien, "2017-01-01", "2020-11-10")
    gq = np.prod([1 + v for v in rq.values()]) ** (1 / 3.86) - 1
    gs = np.prod([1 + v for v in rs.values()]) ** (1 / 3.86) - 1
    print(f"\n  SURVIVORSHIP-ABSTAND desselben Aktien-Bots 2017 - 10.11.2020: S&P-Panel {gs * 100:.1f} %/Jahr, qlib {gq * 100:.1f} %/Jahr "
          f"-> Abstand {(gs - gq) * 100:.1f} Punkte/Jahr (ein Fenster, vier Jahre)")
    return 0


def panel_liste(name: str) -> int:
    """Jahresliste fuer ein beliebiges Panel (z. B. `projekt` = Projektcache auf dem Mac, 2018-2026).

    Liest die Replay-Kurven `simulate_ranking_<name>_*_s12.2_kapital.csv`, rechnet den Trendbot mit
    den ETFs, die das Panel hat (BIL als Cash, falls vorhanden), und schreibt die Tabelle. Fehlende
    Bausteine werden benannt, nicht ersetzt."""
    p = labor.panel_aus_cache(PROJECT_ROOT / "data" / "labor" / name)
    c = p.close
    von = str(c.index[0].year + 1) + "-01-01"
    bis = str(c.index[-1].date())
    reihen: dict[str, pd.Series] = {}
    if "SPY" in c.columns:
        spy = c["SPY"].dropna(); reihen["SPY"] = spy / spy.iloc[0]
    etfs = [x for x in dict.fromkeys(trend.UNIVERSEN["broad"] + ["BIL"]) if x in c.columns]
    if len([x for x in etfs if x != "BIL"]) >= 5:
        from dataclasses import replace
        cfg = PHASE2_KANDIDATEN["dualmom_15"]
        cfg = cfg if "BIL" in etfs else replace(cfg, cash_symbol="")
        reihen[f"Trendbot dualmom_15 ({len(etfs) - ('BIL' in etfs)} ETFs)"] = trend.run(c[etfs], cfg).equity_curve.astype(float)
    else:
        print(f"  Trendbot NICHT gerechnet: nur {etfs} im Panel (>= 5 ETFs noetig)")
    muster = {"Aktien-Bot Momentum (Handmix)": f"simulate_ranking_{name}_momentum_stop3_h21-63_x0.2_c5_vola_n3_s12.2_kapital.csv",
              "Aktien-Bot Hybrid (Stop 3)": f"simulate_ranking_{name}_momentum_stop3_h21-63_x0.2_c5_vola_hybrid_n3_s12.2_kapital.csv",
              "Aktien-Bot Hybrid (ohne Stop)": f"simulate_ranking_{name}_momentum_stop99_h21-63_x0.2_c5_vola_hybrid_n3_s12.2_kapital.csv"}
    for lab, datei in muster.items():
        if (OUT / datei).exists():
            reihen[lab] = kurve(OUT / datei)
        else:
            print(f"  FEHLT: {lab}  ({datei})")
    tab = pd.DataFrame({n: pd.Series(jahres_renditen(k, von, bis)) for n, k in reihen.items()})
    kz = {n: kennzahlen(k, von, bis) for n, k in reihen.items()}
    print(f"\n  JAHRESRENDITEN in %, Panel {name}, {von[:4]} - {bis}, Kosten 12,2 + 5 bps (letztes Jahr = Teiljahr)")
    print(f"  {'Jahr':<8}" + "".join(f"{n[:27]:>29}" for n in tab.columns))
    for j in tab.index:
        print(f"  {j:<8}" + "".join(f"{tab.loc[j, c_] * 100:>+27.1f} %" if not pd.isna(tab.loc[j, c_]) else f"{'–':>29}" for c_ in tab.columns))
    print(f"  {'CAGR':<8}" + "".join(f"{kz[c_]['cagr'] * 100:>+27.1f} %" for c_ in tab.columns))
    print(f"  {'MaxDD':<8}" + "".join(f"{kz[c_]['maxdd'] * 100:>+27.1f} %" for c_ in tab.columns))
    print(f"  {'Sharpe':<8}" + "".join(f"{kz[c_]['sharpe']:>29.2f}" for c_ in tab.columns))
    tab.to_csv(OUT / f"jahresliste_{name}.csv")
    return 0


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
    sys.exit(bis_2026() if "--bis2026" in sys.argv else panel_liste(sys.argv[sys.argv.index("--panel") + 1]) if "--panel" in sys.argv else main())
