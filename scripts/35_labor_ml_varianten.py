#!/usr/bin/env python3
"""Schritt 35: Was tun mit den ML-Vorhersagen? Regime, Vola-Ziel, Hybrid - ohne Neutraining.

Befund (masterplan §6.10): Der ML-Ranker gewinnt auf qlib OHNE Regime-Tor
5 Punkte gegen den Handmix und verliert MIT Tor 2,4 Punkte - sein
Vorsprung sitzt in den Phasen, die das Tor sperrt (Erholungs-Ranker).
Dieses Skript nimmt die gespeicherten OOS-Vorhersagen (`ml_pred_*.parquet`
aus scripts/23) und rechnet daraus die Fassungen, die diesen Befund nutzen
koennten, alle auf demselben Universum und mit denselben Kosten:

    ml_kein          ML, kein Tor
    ml_trend         ML, Tor trend_ok
    ml_hyst          ML, Hysterese-Tor (HYP-24)
    ml_vola25        ML, kein Tor, Vola-Ziel 0,25 (HYP-22)
    ml_trend_vola25  ML, Tor + Vola-Ziel
    hybrid           Tor auf -> Momentum-Handmix, Tor zu -> ML-Auswahl (mit Vola-Ziel 0,25)
    momentum_trend   Referenz: Handmix momentum mit Tor
    momentum_kein    Referenz: Handmix momentum ohne Tor

Bestehensregel (vorab): CAGR >= momentum_trend + 2 Punkte UND MaxDD <= -30 %.

    python scripts/35_labor_ml_varianten.py --panel qlib --start 2006-01-01 --horizont 21 --min-dollar-volume 25000000
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from alpaca_bot import befunde, labor  # noqa: E402
from alpaca_bot.config import PROJECT_ROOT  # noqa: E402

LABOR_DIR = PROJECT_ROOT / "data" / "labor"
OUT_DIR = PROJECT_ROOT / "results" / "labor"
ETFS = {"SPY", "QQQ", "IWM", "DIA", "VTI", "EEM", "EFA", "TLT", "GLD", "HYG", "USO", "BNO"}


def main() -> int:
    from importlib import import_module
    varianten = import_module("22_labor_portfolio").VARIANTEN

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--panel", required=True)
    ap.add_argument("--start", default=None)
    ap.add_argument("--ende", default=None)
    ap.add_argument("--horizont", type=int, default=21)
    ap.add_argument("--pred", default=None, help="Standard: results/labor/ml_pred_<panel>_h<H>.parquet")
    ap.add_argument("--top-n", type=int, default=50)
    ap.add_argument("--kosten", type=float, default=20.0)
    ap.add_argument("--min-preis", type=float, default=3.0)
    ap.add_argument("--min-dollar-volume", type=float, default=1_000_000)
    ap.add_argument("--vola-ziel", type=float, default=0.25)
    ap.add_argument("--vix", default=str(PROJECT_ROOT / "data" / "extern" / "vix-daily.csv"))
    args = ap.parse_args()

    t0 = time.time()
    pred_pfad = Path(args.pred) if args.pred else OUT_DIR / f"ml_pred_{args.panel}_h{args.horizont}.parquet"
    pred = pd.read_parquet(pred_pfad)
    panel = labor.panel_aus_cache(LABOR_DIR / args.panel).schneiden(args.start, args.ende)
    print(f"  {panel.beschreibung()}")
    spy = panel.close["SPY"] if "SPY" in panel.close.columns else None
    p_akt = panel.filtern([s for s in panel.symbole if s not in ETFS])
    maske = labor.liquides_universum(p_akt, min_preis=args.min_preis, min_dollar_volume=args.min_dollar_volume)
    haeufig = maske.columns[maske.mean(axis=0) >= 0.10]
    p_akt = p_akt.filtern(list(haeufig))
    maske = maske[list(haeufig)]
    faktoren = labor.faktorzoo(p_akt, spy=spy)
    vix = labor.vix_laden(args.vix) if Path(args.vix).exists() else None
    regime = labor.regime_serien(spy, vix)

    ml = (pred.pivot(index="tag", columns="symbol", values="pred")
          .reindex(columns=p_akt.close.columns).reindex(p_akt.close.index).ffill(limit=5))
    erstes = int(pd.DatetimeIndex(pred["tag"]).year.min())
    mom = labor.kombinieren(faktoren, varianten["momentum"]["gewichte"])
    # Hybrid: Tor auf -> Momentum, Tor zu -> ML. Beide als Rangperzentil, damit die Skala egal ist.
    an = regime["trend_ok"].reindex(p_akt.close.index).fillna(False).astype(bool)
    hybrid = mom.rank(axis=1, pct=True).where(an, ml.rank(axis=1, pct=True))

    faelle = [
        ("ml_kein", ml, None, None), ("ml_trend", ml, "trend_ok", None), ("ml_hyst", ml, "trend_hyst", None),
        ("ml_vola25", ml, None, args.vola_ziel), ("ml_trend_vola25", ml, "trend_ok", args.vola_ziel),
        ("hybrid", hybrid, None, None), ("hybrid_vola25", hybrid, None, args.vola_ziel),
        ("momentum_trend", mom, "trend_ok", None), ("momentum_kein", mom, None, None),
        ("momentum_vola25", mom, None, args.vola_ziel),
    ]
    rows = []
    print(f"\n  ML-VARIANTEN  Panel {args.panel}  H={args.horizont}  Top {args.top_n}  {args.kosten:.0f} bps  ab {erstes}")
    print(f"  {'Fassung':<18}{'CAGR':>8}{'SPY':>8}{'Univ.EW':>9}{'Sharpe':>8}{'MaxDD':>8}{'Expo':>7}{'Umschl.':>9}")
    for name, sc, reg, vz in faelle:
        cfg = labor.PortfolioConfig(top_n=args.top_n, haltedauer=args.horizont, kosten_bps_rundlauf=args.kosten,
                                    regime=reg, vola_ziel=vz)
        erg = labor.rangportfolio(sc, p_akt, cfg, maske=maske, regime=regime, benchmark=spy)
        erg.renditen = erg.renditen.loc[str(erstes):]
        k = erg.kennzahlen()
        rows.append({"fassung": name, "regime": reg or "kein", "vola_ziel": vz, **k})
        print(f"  {name:<18}{k['cagr']:>8.1%}{k['bench_cagr']:>8.1%}{k.get('univ_cagr', float('nan')):>9.1%}"
              f"{k['sharpe']:>8.2f}{k['max_drawdown']:>8.1%}{k.get('exposure', float('nan')):>7.0%}{k['umschlag_pa']:>9.1f}")
    df = pd.DataFrame(rows)
    ref = float(df.loc[df.fassung == "momentum_trend", "cagr"].iloc[0])
    print(f"\n  Bestehensregel: CAGR >= momentum_trend ({ref:.1%}) + 2 Punkte UND MaxDD <= -30 %")
    for _, r in df.iterrows():
        besteht = r["cagr"] >= ref + 0.02 and r["max_drawdown"] >= -0.30
        urteil = "bestanden" if besteht else ("kandidat" if r["cagr"] >= ref + 0.02 else "verworfen")
        lehre = (f"ML-Variante aus gespeicherten Vorhersagen; gegen momentum_trend {r['cagr'] - ref:+.1%}; "
                 f"MaxDD {r['max_drawdown']:.1%}")
        befunde.eintragen(skript="35", panel=args.panel, variante=r["fassung"], zeitraum=f"{erstes}-{p_akt.close.index[-1].year}",
                          parameter={"regime": r["regime"], "haltedauer": args.horizont, "kosten_bps": args.kosten,
                                     "top_n": args.top_n, "vola_ziel": r["vola_ziel"], "min_dollar_volume": args.min_dollar_volume},
                          kennzahlen={c: r[c] for c in ("cagr", "bench_cagr", "univ_cagr", "sharpe", "max_drawdown",
                                                         "bench_maxdd", "umschlag_pa", "exposure") if c in r and pd.notna(r[c])},
                          urteil=urteil, hypothese="HYP-2027-06", lehre=lehre, quelle_lauf=str(pred_pfad))
        print(f"      {r['fassung']:<18}{urteil}")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"ml_varianten_{args.panel}_h{args.horizont}.csv"
    df.to_csv(out, index=False)
    print(f"\n  gespeichert: {out}   ({time.time() - t0:.0f} s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
