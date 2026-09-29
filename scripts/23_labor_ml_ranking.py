#!/usr/bin/env python3
"""Schritt 23: Querschnitts-Ranking mit Gradient Boosting - walk-forward, jaehrlich.

Der Stand der Literatur (Gu/Kelly/Xiu 2020 und Nachfolger): Baum-Ensembles
auf Querschnitts-Raengen vieler schwacher Merkmale liefern out-of-sample
einen IC von 0,03-0,06 - das Doppelte bis Dreifache eines Einzelfaktors.
Genau das braucht das Fundamentalgesetz (IR = IC x sqrt(BR)).

Aufbau, bewusst konservativ:
  * Merkmale = alle Faktoren aus labor.faktorzoo(), je Tag in Perzentil-
    Raenge [0,1] transformiert (querschnittlich, damit Marktphasen keine
    Skaleneffekte einschleppen).
  * Ziel = Perzentil-Rang der Vorwaertsrendite ueber `--horizont` Tage
    (Ranking, nicht Regression auf Rohrenditen - robuster gegen Ausreisser).
  * Training expanding window bis Jahr Y-1, Embargo = Horizont + 5 Tage,
    Vorhersage fuer Jahr Y. Jedes Jahr wird EINMAL vorhergesagt, nie
    nachjustiert.
  * Es wird nur jede k-te Zeile trainiert (`--stichprobe`), sonst sind es
    Millionen Zeilen; das kostet fast nichts an Guete.
  * Ausgabe: OOS-IC je Jahr (mit t), Vergleich gegen den besten
    Einzelfaktor, und ein Top-N-Rangportfolio netto nach Kosten.

    python scripts/23_labor_ml_ranking.py --panel qlib --start 2006-01-01 --horizont 21
    python scripts/23_labor_ml_ranking.py --panel projekt --horizont 10 --top-n 20

Ergebnis: results/labor/ml_ranking_<panel>.csv
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from alpaca_bot import labor  # noqa: E402
from alpaca_bot.config import PROJECT_ROOT  # noqa: E402

LABOR_DIR = PROJECT_ROOT / "data" / "labor"
OUT_DIR = PROJECT_ROOT / "results" / "labor"


def _lang(faktoren: dict[str, pd.DataFrame], ziel: pd.DataFrame,
          maske: pd.DataFrame, stichprobe: int) -> pd.DataFrame:
    """Breite Panels -> lange Tabelle (tag, symbol, merkmale..., y)."""
    teile = {}
    for name, f in faktoren.items():
        teile[name] = f.where(maske).rank(axis=1, pct=True).astype("float32")
    y = ziel.where(maske).rank(axis=1, pct=True).astype("float32")
    frames = []
    tage = list(y.index)[::stichprobe]
    for t in tage:
        zeile = pd.DataFrame({k: v.loc[t] for k, v in teile.items()})
        zeile["y"] = y.loc[t]
        zeile["tag"] = t
        zeile = zeile.dropna(subset=["y"])
        if len(zeile) >= 50:
            frames.append(zeile)
    df = pd.concat(frames)
    df.index.name = "symbol"
    return df.reset_index()


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--panel", required=True)
    p.add_argument("--start", default=None)
    p.add_argument("--ende", default=None)
    p.add_argument("--horizont", type=int, default=21)
    p.add_argument("--erstes-testjahr", type=int, default=None)
    p.add_argument("--stichprobe", type=int, default=5, help="jede k-te Zeile (Tag)")
    p.add_argument("--top-n", type=int, default=20)
    p.add_argument("--kosten", type=float, default=20.0)
    p.add_argument("--min-preis", type=float, default=3.0)
    p.add_argument("--min-dollar-volume", type=float, default=1_000_000)
    args = p.parse_args()

    try:
        import lightgbm as lgb
    except ImportError:
        print("  lightgbm fehlt: pip install lightgbm")
        return 1

    t0 = time.time()
    panel = labor.panel_aus_cache(LABOR_DIR / args.panel).schneiden(args.start, args.ende)
    print(f"  {panel.beschreibung()}")
    spy = panel.close["SPY"] if "SPY" in panel.close.columns else None
    etfs = {"SPY", "QQQ", "IWM", "DIA", "VTI", "EEM", "EFA", "TLT", "GLD", "HYG", "USO", "BNO"}
    p_akt = panel.filtern([s for s in panel.symbole if s not in etfs])
    maske = labor.liquides_universum(p_akt, min_preis=args.min_preis,
                                     min_dollar_volume=args.min_dollar_volume)
    faktoren = labor.faktorzoo(p_akt, spy=spy)
    fwd = labor.vorwaertsrendite(p_akt, args.horizont)
    print(f"  {len(faktoren)} Merkmale, baue lange Tabelle (jede {args.stichprobe}. Zeile) ...")
    lang = _lang(faktoren, fwd, maske, args.stichprobe)
    lang["jahr"] = pd.DatetimeIndex(lang["tag"]).year
    merkmale = list(faktoren)
    print(f"  {len(lang):,} Zeilen, {lang['tag'].nunique():,} Tage, Jahre {lang['jahr'].min()}-{lang['jahr'].max()}")

    jahre = sorted(lang["jahr"].unique())
    erstes = args.erstes_testjahr or jahre[min(3, len(jahre) - 1)]
    embargo = pd.Timedelta(days=int((args.horizont + 5) * 1.5))
    vorhersagen = []
    wichtig = []
    for y in [j for j in jahre if j >= erstes]:
        grenze = pd.Timestamp(f"{y}-01-01") - embargo
        tr = lang[lang["tag"] < grenze]
        te = lang[lang["jahr"] == y]
        if len(tr) < 5_000 or te.empty:
            continue
        m = lgb.LGBMRegressor(
            objective="regression", n_estimators=300, learning_rate=0.03,
            num_leaves=31, min_child_samples=200, subsample=0.7, subsample_freq=1,
            colsample_bytree=0.7, reg_lambda=5.0, verbose=-1, n_jobs=4,
        )
        m.fit(tr[merkmale], tr["y"])
        te = te.copy()
        te["pred"] = m.predict(te[merkmale])
        vorhersagen.append(te[["tag", "symbol", "y", "pred"]])
        wichtig.append(pd.Series(m.feature_importances_, index=merkmale, name=y))
        print(f"      {y}: trainiert auf {len(tr):,} Zeilen bis {tr['tag'].max().date()}, "
              f"vorhergesagt {len(te):,}")

    if not vorhersagen:
        print("  Zu wenig Daten fuer einen Walk-Forward.")
        return 1
    pred = pd.concat(vorhersagen)

    # --- OOS-IC je Tag und Jahr ---
    ic_tag = pred.groupby("tag").apply(
        lambda g: g["pred"].corr(g["y"], method="spearman") if len(g) >= 50 else np.nan
    ).dropna()
    ic_jahr = ic_tag.groupby(ic_tag.index.year).agg(["mean", "std", "count"])
    ic_jahr["t"] = ic_jahr["mean"] / (ic_jahr["std"] / np.sqrt(ic_jahr["count"]))

    # bester Einzelfaktor OOS zum Vergleich (gleicher Horizont, gleiche Tage)
    einzel = {}
    for name in merkmale:
        s = lang[lang["tag"].isin(ic_tag.index)].groupby("tag").apply(
            lambda g, n=name: g[n].corr(g["y"], method="spearman") if g[n].notna().sum() >= 50 else np.nan
        ).dropna()
        einzel[name] = float(s.mean())
    bester = max(einzel, key=lambda k: abs(einzel[k]))

    print()
    print("=" * 84)
    print(f"  ML-RANKING walk-forward, Horizont {args.horizont} Tage, Panel {args.panel}")
    print("=" * 84)
    print(f"  {'Jahr':>6}{'IC':>9}{'t':>8}{'Tage':>7}")
    for y, r in ic_jahr.iterrows():
        print(f"  {y:>6}{r['mean']:>+9.4f}{r['t']:>+8.1f}{int(r['count']):>7}")
    ges_t = ic_tag.mean() / (ic_tag.std() / np.sqrt(len(ic_tag)))
    print(f"  {'alle':>6}{ic_tag.mean():>+9.4f}{ges_t:>+8.1f}{len(ic_tag):>7}"
          f"   (t deflationiert um sqrt(H): {ges_t / np.sqrt(args.horizont):+.1f})")
    print(f"\n  bester Einzelfaktor auf denselben Tagen: {bester} IC {einzel[bester]:+.4f}")
    imp = pd.concat(wichtig, axis=1).mean(axis=1).sort_values(ascending=False)
    print("  Merkmalswichtigkeit (Mittel ueber Jahre):")
    for k, v in imp.head(10).items():
        print(f"      {k:<20}{v:>8.0f}")

    # --- Rangportfolio auf den OOS-Vorhersagen ---
    score = pred.pivot(index="tag", columns="symbol", values="pred").reindex(columns=p_akt.close.columns)
    score = score.reindex(p_akt.close.index).ffill(limit=args.stichprobe)
    cfg = labor.PortfolioConfig(top_n=args.top_n, haltedauer=args.horizont,
                                kosten_bps_rundlauf=args.kosten)
    erg = labor.rangportfolio(score, p_akt, cfg, maske=maske, benchmark=spy)
    erg.renditen = erg.renditen.loc[str(erstes):]
    k = erg.kennzahlen()
    print(f"\n  Top-{args.top_n}-Portfolio auf OOS-Vorhersagen, H={args.horizont}, {args.kosten:.0f} bps:")
    print(f"      CAGR {k['cagr']:+.1%}  (SPY {k['bench_cagr']:+.1%})  Sharpe {k['sharpe']:.2f}  "
          f"MaxDD {k['max_drawdown']:.1%} (SPY {k['bench_maxdd']:.1%})  Umschlag {k['umschlag_pa']:.1f}/J")
    print(erg.jahrestabelle().round(3).to_string())

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"ml_ranking_{args.panel}_h{args.horizont}.csv"
    ic_jahr.to_csv(out)
    print(f"\n  gespeichert: {out}   ({time.time() - t0:.0f} s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
