#!/usr/bin/env python3
"""Schritt 24: Haltedauer gegen Kosten - wo liegt das Optimum je Signal?

Der Befund des Projekts bis August 2026 lautet: Der Umkehr-Vorsprung von
+0,11 % je Trade liegt unter dem Rundlauf-Breakeven von 0,14 % bei 5 bps
Spread. Die Frage, die dieses Skript beantwortet, ist deshalb nicht "welches
Signal", sondern "**wie lange halten**, damit der Vorsprung je Trade groesser
wird als die Kosten je Trade".

Fuer jede Signalvariante wird das Rangportfolio mit Haltedauern von 2 bis
126 Tagen gerechnet, jeweils bei 10 / 20 / 40 bps je Rundlauf. Ausgegeben
wird die Netto-CAGR-Kurve ueber die Haltedauer - und der Punkt, ab dem die
Kurve flach wird (dort ist der Umschlag nicht mehr das Problem).

    python scripts/24_labor_haltedauer.py --panel qlib --variante kombi --start 2006-01-01
    python scripts/24_labor_haltedauer.py --panel projekt --variante reversal

Ergebnis: results/labor/haltedauer_<panel>_<variante>.csv
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

sys.path.insert(0, str(Path(__file__).resolve().parent))
from importlib import import_module  # noqa: E402

VARIANTEN = import_module("22_labor_portfolio").VARIANTEN

LABOR_DIR = PROJECT_ROOT / "data" / "labor"
OUT_DIR = PROJECT_ROOT / "results" / "labor"


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--panel", required=True)
    p.add_argument("--variante", default="kombi", choices=list(VARIANTEN))
    p.add_argument("--start", default=None)
    p.add_argument("--ende", default=None)
    p.add_argument("--top-n", type=int, default=20)
    p.add_argument("--haltedauern", type=int, nargs="+", default=[2, 5, 10, 21, 42, 63, 126])
    p.add_argument("--kosten", type=float, nargs="+", default=[10.0, 20.0, 40.0])
    p.add_argument("--regime", default=None, help="z. B. trend_ok")
    p.add_argument("--vix", default=str(PROJECT_ROOT / "data" / "extern" / "vix-daily.csv"))
    p.add_argument("--min-preis", type=float, default=3.0)
    p.add_argument("--min-dollar-volume", type=float, default=1_000_000)
    args = p.parse_args()

    t0 = time.time()
    panel = labor.panel_aus_cache(LABOR_DIR / args.panel).schneiden(args.start, args.ende)
    print(f"  {panel.beschreibung()}")
    spy = panel.close["SPY"] if "SPY" in panel.close.columns else None
    etfs = {"SPY", "QQQ", "IWM", "DIA", "VTI", "EEM", "EFA", "TLT", "GLD", "HYG", "USO", "BNO"}
    p_akt = panel.filtern([s for s in panel.symbole if s not in etfs])
    maske = labor.liquides_universum(p_akt, min_preis=args.min_preis,
                                     min_dollar_volume=args.min_dollar_volume)
    faktoren = labor.faktorzoo(p_akt, spy=spy)
    gew = VARIANTEN[args.variante]["gewichte"]
    fehlend = [k for k in gew if k not in faktoren]
    if fehlend:
        print(f"  ABBRUCH: Faktoren fehlen: {fehlend}")
        return 1
    score = labor.kombinieren(faktoren, gew)
    vix = labor.vix_laden(args.vix) if Path(args.vix).exists() else None
    regime = labor.regime_serien(spy, vix) if spy is not None else None

    rows = []
    for H in args.haltedauern:
        for kosten in args.kosten:
            cfg = labor.PortfolioConfig(top_n=args.top_n, haltedauer=H,
                                        kosten_bps_rundlauf=kosten, regime=args.regime)
            erg = labor.rangportfolio(score, p_akt, cfg, maske=maske, regime=regime,
                                      benchmark=spy)
            k = erg.kennzahlen()
            # Brutto-Vorsprung je Trade: (CAGR_brutto - SPY) / Umschlag - grobe Naeherung
            rows.append({"variante": args.variante, "H": H, "kosten_bps": kosten, **k})
        print(f"      H={H} fertig")

    df = pd.DataFrame(rows)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"haltedauer_{args.panel}_{args.variante}.csv"
    df.to_csv(out, index=False)

    print()
    print("=" * 96)
    print(f"  HALTEDAUER-KURVE  {args.variante}  Top {args.top_n}  Panel {args.panel}"
          f"  Regime={args.regime or 'kein'}   (SPY CAGR {df['bench_cagr'].iloc[0]:.1%})")
    print("=" * 96)
    piv = df.pivot(index="H", columns="kosten_bps", values="cagr")
    sh = df.pivot(index="H", columns="kosten_bps", values="sharpe")
    um = df.groupby("H")["umschlag_pa"].first()
    print(f"  {'H':>5}{'Umschlag/J':>12}" + "".join(f"{f'CAGR@{c:g}':>11}" for c in piv.columns)
          + "".join(f"{f'Sharpe@{c:g}':>12}" for c in sh.columns))
    for H in piv.index:
        print(f"  {H:>5}{um[H]:>12.1f}" + "".join(f"{piv.loc[H, c]:>11.1%}" for c in piv.columns)
              + "".join(f"{sh.loc[H, c]:>12.2f}" for c in sh.columns))
    print("\n  Lesart: Steigt die Netto-CAGR mit H, frisst der Umschlag den Vorsprung -")
    print("  dann ist laenger halten der Hebel, nicht ein besseres Signal.")
    print(f"\n  gespeichert: {out}   ({time.time() - t0:.0f} s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
