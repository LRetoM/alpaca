#!/usr/bin/env python3
"""Schritt 22: Rangportfolios netto nach Kosten - Jahr fuer Jahr gegen SPY.

Aus einem Score wird ein handelbares Long-only-Portfolio: Top-N, Haltedauer H,
ueberlappende Kohorten, Kosten je Rundlauf, wahlweise Regimefilter und
Volatilitaets-Ziel. Ausgegeben wird das, was zaehlt: CAGR, Sharpe, maximaler
Drawdown und die JAHRESTABELLE - insbesondere 2018, 2020 und 2022.

Vordefinierte Varianten (--variante):
    momentum      mom_12_1 + mom_konsistenz          (Multi-Wochen, H=21)
    momentum_vola mom_12_1_vola                       (vola-skaliertes Momentum)
    reversal      reversal_5d + rsi2_invers           (Kurzfrist, H=5)
    volumen       vol_schub_1w                        (High-Volume-Premium, H=21)
    kombi         Momentum + Volumen + Low-Vol (Z-Score-Mix, H=21)
    ear           ear_proxy (Sprung mit Volumen, PEAD-Ersatz, H=42)

Jede Variante laeuft in vier Regime-Fassungen: ohne Filter, SPY>SMA200,
VIX<25, beides. Und in drei Kostenstufen (10/20/40 bps Rundlauf).

    python scripts/22_labor_portfolio.py --panel qlib --variante kombi --start 2006-01-01
    python scripts/22_labor_portfolio.py --panel projekt --variante momentum --top-n 20 --haltedauer 21
    python scripts/22_labor_portfolio.py --panel sp500_close --variante momentum --vix data/extern/vix-daily.csv

Ergebnis: results/labor/portfolio_<panel>_<variante>.csv
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from alpaca_bot import labor  # noqa: E402
from alpaca_bot.config import PROJECT_ROOT  # noqa: E402

LABOR_DIR = PROJECT_ROOT / "data" / "labor"
OUT_DIR = PROJECT_ROOT / "results" / "labor"

VARIANTEN = {
    "momentum": dict(gewichte={"mom_12_1": 1.0, "mom_konsistenz": 1.0}, haltedauer=21),
    "momentum_vola": dict(gewichte={"mom_12_1_vola": 1.0}, haltedauer=21),
    "reversal": dict(gewichte={"reversal_5d": 1.0, "rsi2_invers": 1.0}, haltedauer=5),
    "volumen": dict(gewichte={"vol_schub_1w": 1.0}, haltedauer=21),
    "kombi": dict(gewichte={"mom_12_1": 1.0, "mom_konsistenz": 0.5, "vol_schub_1w": 1.0,
                            "vola_niedrig": 0.5}, haltedauer=21),
    "kombi_ohne_volumen": dict(gewichte={"mom_12_1": 1.0, "mom_konsistenz": 0.5,
                                         "vola_niedrig": 0.5}, haltedauer=21),
    "ear": dict(gewichte={"ear_proxy": 1.0}, haltedauer=42),
    "lowvol": dict(gewichte={"vola_niedrig": 1.0}, haltedauer=42),
    # --- nach dem Faktorzoo auf qlib 2005-2020 ergaenzt (siehe masterplan §6.5) ---
    # "ruhig": Aktien, deren Umsatz der letzten 6 Monate UNTER dem eigenen
    # Vorjahresmass liegt (vol_schub_6m_neg) - staerkster und stabilster Fund
    # im Zoo (t_defl 3,9 auf 21 Tagen, 87 % positive Jahre). In-sample
    # entdeckt, deshalb HYP-2027-17: Bestaetigung auf 2016-2026 ist Pflicht.
    "ruhig": dict(gewichte={"vol_schub_6m_neg": 1.0}, haltedauer=42),
    "kombi2": dict(gewichte={"mom_konsistenz": 1.0, "vol_schub_6m_neg": 1.0,
                             "mom_12_1_vola": 0.5}, haltedauer=21),
    "kombi2_h42": dict(gewichte={"mom_konsistenz": 1.0, "vol_schub_6m_neg": 1.0,
                                 "mom_12_1_vola": 0.5}, haltedauer=42),
    # --- KURZE Horizonte auf Einzelaktien (Nutzerwunsch: Tage statt Wochen) ---
    # Die auf 5 Tagen staerksten, untereinander wenig korrelierten Faktoren
    # aus dem Zoo (t_defl h=5: vol_schub_6m_neg 5,2 / mom_konsistenz 4,0 /
    # reversal_5d 3,8 / rsi2 3,0 / vol_z_1d 2,6). Umkehr liefert das Timing,
    # Momentum-Konsistenz und ruhiges Volumen die Auswahl - "gefallene
    # Qualitaet, die keiner beachtet".
    "kurz": dict(gewichte={"reversal_5d": 1.0, "rsi2_invers": 0.5, "mom_konsistenz": 1.0,
                           "vol_schub_6m_neg": 1.0, "vol_z_1d": 0.5}, haltedauer=5),
    "kurz10": dict(gewichte={"reversal_5d": 1.0, "rsi2_invers": 0.5, "mom_konsistenz": 1.0,
                             "vol_schub_6m_neg": 1.0, "vol_z_1d": 0.5}, haltedauer=10),
    # Nur Kursfaktoren (fuer Panels ohne Volumen wie sp500_close)
    "kurz_preis": dict(gewichte={"reversal_5d": 1.0, "rsi2_invers": 0.5, "mom_konsistenz": 1.0,
                                 "mom_12_1_vola": 0.5}, haltedauer=5),
    # Reine Umkehr wie der heutige Bot, zum direkten Vergleich mit 'kurz'
    "reversal_rein": dict(gewichte={"reversal_5d": 1.0, "rsi2_invers": 1.0}, haltedauer=5),
    # Exakt der Score der Engine-Strategie "ranking" (signals.RankingWeights),
    # fuer den Replay-Vergleich mit scripts/31 - mit und ohne Volumen
    "ranking": dict(gewichte={"mom_konsistenz": 1.0, "vol_schub_6m_neg": 1.0,
                              "mom_12_1_vola": 0.5}, haltedauer=42),
    "ranking_preis": dict(gewichte={"mom_konsistenz": 1.0, "mom_12_1_vola": 0.5}, haltedauer=42),
    # Kandidat v2: rohes 12-1-Momentum dazu (CAGR-staerker), ruhiges Volumen halb
    "ranking_v2": dict(gewichte={"mom_12_1": 1.0, "mom_konsistenz": 1.0, "vol_schub_6m_neg": 0.5},
                       haltedauer=42),
    "ranking_v2_preis": dict(gewichte={"mom_12_1": 1.0, "mom_konsistenz": 1.0}, haltedauer=42),
}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--panel", required=True)
    p.add_argument("--variante", default="kombi", choices=list(VARIANTEN))
    p.add_argument("--start", default=None)
    p.add_argument("--ende", default=None)
    p.add_argument("--top-n", type=int, default=20)
    p.add_argument("--haltedauer", type=int, default=None)
    p.add_argument("--kosten", type=float, nargs="+", default=[10.0, 20.0, 40.0],
                   help="bps je Rundlauf")
    p.add_argument("--vola-ziel", type=float, default=None)
    p.add_argument("--regimes", nargs="+", default=None,
                   help="Regime-Spalten statt der vier Standardfassungen, z. B. trend_ok trend_hyst")
    p.add_argument("--vix", default=str(PROJECT_ROOT / "data" / "extern" / "vix-daily.csv"))
    p.add_argument("--min-preis", type=float, default=3.0)
    p.add_argument("--min-dollar-volume", type=float, default=1_000_000)
    p.add_argument("--spy", default="SPY")
    args = p.parse_args()

    t0 = time.time()
    panel = labor.panel_aus_cache(LABOR_DIR / args.panel).schneiden(args.start, args.ende)
    print(f"  {panel.beschreibung()}")
    var = VARIANTEN[args.variante]
    H = args.haltedauer or var["haltedauer"]

    spy = panel.close[args.spy] if args.spy in panel.close.columns else None
    if spy is None:
        print("  WARNUNG: kein SPY im Panel - kein Benchmark, kein Trendfilter.")
    etfs = {"SPY", "QQQ", "IWM", "DIA", "VTI", "EEM", "EFA", "TLT", "GLD", "HYG", "USO", "BNO"}
    p_akt = panel.filtern([s for s in panel.symbole if s not in etfs])
    maske = labor.liquides_universum(p_akt, min_preis=args.min_preis,
                                     min_dollar_volume=args.min_dollar_volume)

    faktoren = labor.faktorzoo(p_akt, spy=spy)
    fehlend = [k for k in var["gewichte"] if k not in faktoren]
    if fehlend:
        print(f"  ABBRUCH: Faktoren fehlen in diesem Panel (kein Volumen?): {fehlend}")
        return 1
    score = labor.kombinieren(faktoren, var["gewichte"])

    vix = None
    if Path(args.vix).exists():
        vix = labor.vix_laden(args.vix)
    regime = labor.regime_serien(spy, vix) if spy is not None else None
    regime_varianten = [None]
    if regime is not None and args.regimes:
        fehlend = [r for r in args.regimes if r not in regime.columns]
        if fehlend:
            print(f"  ABBRUCH: unbekannte Regime-Spalten {fehlend}; bekannt: {list(regime.columns)}")
            return 1
        regime_varianten += list(args.regimes)
    elif regime is not None:
        regime_varianten += ["trend_ok"]
        if vix is not None:
            regime["vix_ruhig"] = ~regime["vix_hoch"]
            regime["trend_und_vix"] = regime["trend_ok"] & regime["vix_ruhig"]
            regime_varianten += ["vix_ruhig", "trend_und_vix"]

    rows = []
    tabellen = {}
    for reg in regime_varianten:
        for kosten in args.kosten:
            cfg = labor.PortfolioConfig(top_n=args.top_n, haltedauer=H,
                                        kosten_bps_rundlauf=kosten, regime=reg,
                                        vola_ziel=args.vola_ziel)
            erg = labor.rangportfolio(score, p_akt, cfg, maske=maske, regime=regime,
                                      benchmark=spy)
            k = erg.kennzahlen()
            rows.append({"variante": args.variante, "regime": reg or "kein",
                         "kosten_bps": kosten, "top_n": args.top_n, "H": H, **k})
            tabellen[(reg or "kein", kosten)] = erg.jahrestabelle()

    df = pd.DataFrame(rows)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"portfolio_{args.panel}_{args.variante}.csv"
    df.to_csv(out, index=False)

    print()
    print("=" * 108)
    print(f"  RANGPORTFOLIO  {args.variante}  Top {args.top_n}, H={H} Tage, Panel {args.panel}")
    print("=" * 108)
    print(f"  {'Regime':<14}{'Kosten':>7}{'CAGR':>8}{'SPY':>8}{'Univ.EW':>9}{'Sharpe':>8}{'MaxDD':>8}{'SPY DD':>8}"
          f"{'Vola':>7}{'Umschl./J':>10}{'Kosten/J':>9}{'Expo':>6}")
    print("  " + "-" * 113)
    for _, r in df.iterrows():
        print(f"  {r['regime']:<14}{r['kosten_bps']:>7.0f}{r['cagr']:>8.1%}{r['bench_cagr']:>8.1%}"
              f"{r.get('univ_cagr', float('nan')):>9.1%}"
              f"{r['sharpe']:>8.2f}{r['max_drawdown']:>8.1%}{r['bench_maxdd']:>8.1%}{r['vola']:>7.1%}"
              f"{r['umschlag_pa']:>10.1f}{r['kosten_pa']:>9.1%}{r['exposure']:>6.0%}")
    print("  Univ.EW = gleichgewichtetes Universum aller zugelassenen Werte, ohne Kosten -")
    print("  der Massstab fuer AUSWAHL-Alpha; SPY ist der Massstab fuer den Anleger.")

    # Jahrestabelle: Referenzfassung (kein Regime, mittlere Kosten) und beste Regimefassung
    mitte = args.kosten[len(args.kosten) // 2]
    for key in [("kein", mitte)] + [(r, mitte) for r in regime_varianten if r]:
        if key in tabellen:
            print(f"\n  JAHRESTABELLE  Regime={key[0]}, Kosten={key[1]:.0f} bps:")
            print(tabellen[key].round(3).to_string())
    # --- Befundregister: jede Zeile ein Befund, mechanisch beurteilt ---
    from alpaca_bot import befunde

    zeitraum = f"{panel.close.index[0].year}-{panel.close.index[-1].year}"
    for _, r in df.iterrows():
        k = {c: r[c] for c in ("cagr", "bench_cagr", "univ_cagr", "sharpe", "max_drawdown",
                               "bench_maxdd", "umschlag_pa", "kosten_pa", "exposure") if c in r}
        urteil, lehre = befunde.urteil_portfolio(k)
        befunde.eintragen(skript="22", panel=args.panel, variante=args.variante, zeitraum=zeitraum,
                          parameter={"regime": r["regime"], "haltedauer": int(r["H"]),
                                     "kosten_bps": float(r["kosten_bps"]), "top_n": int(r["top_n"]),
                                     "min_dollar_volume": args.min_dollar_volume,
                                     "vola_ziel": args.vola_ziel, "gewichte": str(var["gewichte"])},
                          kennzahlen=k, urteil=urteil, lehre=lehre, quelle_lauf=str(out))
    print(f"  {len(df)} Befunde ins Register geschrieben ({befunde.REGISTER.name})")
    print(f"\n  gespeichert: {out}   ({time.time() - t0:.0f} s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
