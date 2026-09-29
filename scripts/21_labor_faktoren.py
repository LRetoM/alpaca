#!/usr/bin/env python3
"""Schritt 21: Faktorzoo messen - Querschnitts-IC je Tag, je Horizont, je Jahr.

Beantwortet fuer JEDEN Kandidaten aus labor.faktorzoo():
  * Sortiert er die Aktien eines Tages richtig (IC, t-Wert)?
  * Auf welchem Horizont (5 / 10 / 21 / 42 / 63 Tage)?
  * Haelt das Vorzeichen in JEDEM Jahr - auch 2018, 2020, 2022?
  * Wie gross ist die Quintil-Spanne (oberstes minus unterstes Fuenftel)?

Der t-Wert wird zusaetzlich mit sqrt(Horizont) deflationiert, weil sich
benachbarte Tage bei ueberlappenden Horizonten fast vollstaendig
ueberschneiden. |t_deflated| > 2 gilt als brauchbar, > 3 als solide.

    python scripts/21_labor_faktoren.py --panel qlib --start 2005-01-01
    python scripts/21_labor_faktoren.py --panel projekt
    python scripts/21_labor_faktoren.py --panel sp500_close --horizonte 5 21 63

Ergebnis: results/labor/faktoren_<panel>.csv + Konsolenbericht.
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


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--panel", required=True, help="Name unter data/labor/")
    p.add_argument("--start", default=None)
    p.add_argument("--ende", default=None)
    p.add_argument("--horizonte", type=int, nargs="+", default=[5, 10, 21, 42, 63])
    p.add_argument("--min-preis", type=float, default=3.0)
    p.add_argument("--min-dollar-volume", type=float, default=1_000_000)
    p.add_argument("--spy", default="SPY", help="Symbol fuer relative Staerke")
    p.add_argument("--nur", nargs="*", default=None, help="nur diese Faktoren")
    args = p.parse_args()

    t0 = time.time()
    panel = labor.panel_aus_cache(LABOR_DIR / args.panel)
    panel = panel.schneiden(args.start, args.ende)
    print(f"  {panel.beschreibung()}")

    spy = panel.close[args.spy] if args.spy in panel.close.columns else None
    if spy is None:
        print("  Hinweis: kein SPY im Panel - relative Staerke entfaellt.")
    # SPY/ETFs raus aus dem Aktien-Querschnitt
    etfs = [s for s in panel.symbole if s in ("SPY", "QQQ", "IWM", "DIA", "VTI", "EEM", "EFA", "TLT", "GLD", "HYG", "USO", "BNO")]
    aktien = [s for s in panel.symbole if s not in etfs]
    p_akt = panel.filtern(aktien)

    maske = labor.liquides_universum(p_akt, min_preis=args.min_preis,
                                     min_dollar_volume=args.min_dollar_volume)
    print(f"  zugelassen im Mittel je Tag: {maske.sum(axis=1).mean():,.0f} Symbole")

    faktoren = labor.faktorzoo(p_akt, spy=spy)
    if args.nur:
        faktoren = {k: v for k, v in faktoren.items() if k in args.nur}
    print(f"  {len(faktoren)} Faktoren: {', '.join(faktoren)}")

    df = labor.ic_messen(faktoren, p_akt, horizonte=tuple(args.horizonte), maske=maske)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"faktoren_{args.panel}.csv"
    df.to_csv(out, index=False)

    print()
    print("=" * 110)
    print(f"  FAKTOR-RANGLISTE  Panel {args.panel}  ({panel.close.index[0].date()} .. {panel.close.index[-1].date()})")
    print("=" * 110)
    print(f"  {'Faktor':<20}{'Hor':>4}{'IC':>8}{'t_defl':>8}{'Treff':>7}{'Q5-Q1 p.a.':>12}{'Jahre+':>8}{'schl.Jahr':>10}  Urteil")
    print("  " + "-" * 106)
    for _, r in df.iterrows():
        print(f"  {r['faktor']:<20}{int(r['horizont']):>4}{r['ic']:>+8.4f}{r['t_deflated']:>+8.1f}"
              f"{r['trefferquote']:>7.0%}{r['q5_q1_pa']:>+12.1%}{r['anteil_jahre_positiv']:>8.0%}"
              f"{r['schlechtestes_jahr']:>+10.3f}  {r['urteil']}")

    # Jahrestabelle fuer den 21-Tage-Horizont (der Multi-Wochen-Fall)
    h = 21 if 21 in args.horizonte else args.horizonte[len(args.horizonte) // 2]
    jt = labor.jahres_ic_tabelle(df, horizont=h)
    if not jt.empty:
        print()
        print(f"  IC JE JAHR, Horizont {h} Tage (Vorzeichenstabilitaet):")
        with pd.option_context("display.width", 200, "display.max_columns", 30):
            print(jt.round(3).to_string())
    print(f"\n  gespeichert: {out}   ({time.time() - t0:.0f} s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
