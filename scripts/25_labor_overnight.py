#!/usr/bin/env python3
"""Schritt 25: Overnight- gegen Intraday-Rendite - und was davon Kosten ueberlebt.

Die Literatur (Lou/Polk/Skouras; Cooper et al.) zeigt: Fast die gesamte
Indexrendite entsteht ueber Nacht (Schluss -> naechste Eroeffnung), der
Handelstag selbst bringt ueber Jahrzehnte fast nichts. Klingt nach einer
Strategie: abends kaufen, morgens verkaufen. Der Haken sind 2 Rundlaeufe je
Tag - 500 Ausfuehrungen pro Jahr.

Dieses Skript misst auf Tagesbars (Lean 1998-2021, spaeter dein Alpaca-Cache):
  1. Zerlegung Overnight / Intraday je Jahr fuer SPY, QQQ, IWM
  2. Overnight-only NETTO bei 0,5 / 1 / 2 / 5 bps je Ausfuehrung
  3. Bedingte Varianten: nur ueber SMA200, nur bei VIX < 25, nur Mo-Do,
     nur nach negativem Intraday (Umkehr) - jeweils netto
  4. Die Breakeven-Kosten je Variante

    python scripts/25_labor_overnight.py --panel lean --symbole SPY QQQ IWM
    python scripts/25_labor_overnight.py --panel projekt --symbole SPY QQQ

Erwartung, vorab festgehalten: brutto deutlich positiv, netto bei
realistischen 1-2 bps je Seite nahe null oder negativ. Interessant ist nur,
ob eine bedingte Fassung mit weniger Trades die Kostenhuerde nimmt.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from alpaca_bot import labor  # noqa: E402
from alpaca_bot.config import PROJECT_ROOT  # noqa: E402

LABOR_DIR = PROJECT_ROOT / "data" / "labor"
OUT_DIR = PROJECT_ROOT / "results" / "labor"
TD = 252


def _kz(r: pd.Series) -> dict:
    r = r.dropna()
    if len(r) < 50:
        return {"cagr": np.nan, "sharpe": np.nan, "maxdd": np.nan}
    eq = (1 + r).cumprod()
    cagr = eq.iloc[-1] ** (TD / len(r)) - 1
    sh = r.mean() / r.std() * np.sqrt(TD) if r.std() > 0 else np.nan
    dd = (eq / eq.cummax() - 1).min()
    return {"cagr": float(cagr), "sharpe": float(sh), "maxdd": float(dd)}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--panel", default="lean")
    p.add_argument("--symbole", nargs="+", default=["SPY", "QQQ", "IWM"])
    p.add_argument("--start", default="2000-01-01")
    p.add_argument("--kosten", type=float, nargs="+", default=[0.0, 0.5, 1.0, 2.0, 5.0],
                   help="bps je AUSFUEHRUNG (Overnight = 2 je Tag)")
    p.add_argument("--vix", default=str(PROJECT_ROOT / "data" / "extern" / "vix-daily.csv"))
    args = p.parse_args()

    panel = labor.panel_aus_cache(LABOR_DIR / args.panel).schneiden(args.start, None)
    if panel.open is None:
        print("  ABBRUCH: Panel ohne Eroeffnungskurse - Overnight nicht messbar.")
        return 1
    vix = labor.vix_laden(args.vix) if Path(args.vix).exists() else None

    rows = []
    for sym in args.symbole:
        if sym not in panel.close.columns:
            print(f"  {sym}: nicht im Panel")
            continue
        o, c = panel.open[sym].astype(float), panel.close[sym].astype(float)
        on = (o / c.shift(1) - 1)          # Schluss t-1 -> Eroeffnung t
        intra = (c / o - 1)                # Eroeffnung t -> Schluss t
        cc = c.pct_change()
        print()
        print("=" * 96)
        print(f"  {sym}: Overnight gegen Intraday, {c.index[0].date()} .. {c.index[-1].date()}")
        print("=" * 96)
        jt = pd.DataFrame({
            "overnight": on.groupby(on.index.year).apply(lambda s: (1 + s).prod() - 1),
            "intraday": intra.groupby(intra.index.year).apply(lambda s: (1 + s).prod() - 1),
            "close_close": cc.groupby(cc.index.year).apply(lambda s: (1 + s).prod() - 1),
        })
        print(jt.round(3).to_string())
        brutto = _kz(on)
        print(f"\n  Overnight brutto: CAGR {brutto['cagr']:+.1%}  Sharpe {brutto['sharpe']:.2f}  MaxDD {brutto['maxdd']:.1%}")
        print(f"  Intraday  brutto: CAGR {_kz(intra)['cagr']:+.1%}  Sharpe {_kz(intra)['sharpe']:.2f}")
        print(f"  Buy&Hold        : CAGR {_kz(cc)['cagr']:+.1%}  Sharpe {_kz(cc)['sharpe']:.2f}  MaxDD {_kz(cc)['maxdd']:.1%}")

        # Bedingte Fassungen
        sma200 = c.shift(1) > c.shift(1).rolling(200).mean()
        bedingungen = {
            "immer": pd.Series(True, index=c.index),
            "ueber_sma200": sma200,
            "mo_do": pd.Series(c.index.dayofweek < 4, index=c.index),   # Einstieg Mo-Do Abend
            "nach_intraday_minus": intra.shift(1) < 0,
            "nach_intraday_plus": intra.shift(1) > 0,
        }
        if vix is not None:
            vx = vix.reindex(c.index).ffill().shift(1)
            bedingungen["vix_unter_25"] = vx < 25
            bedingungen["vix_ueber_25"] = vx >= 25
        print(f"\n  {'Bedingung':<22}{'Tage/J':>8}" + "".join(f"{f'netto@{k:g}bps':>14}" for k in args.kosten) + f"{'Breakeven':>11}")
        print("  " + "-" * 92)
        for name, bed in bedingungen.items():
            bed = bed.reindex(c.index).fillna(False)
            r = on.where(bed, 0.0)
            n_pa = float(bed.sum()) / (len(c) / TD)
            zeile = f"  {name:<22}{n_pa:>8.0f}"
            for k in args.kosten:
                r_net = r - bed.astype(float) * 2 * k / 10_000
                kz = _kz(r_net)
                zeile += f"{kz['cagr']:>+8.1%}/{kz['sharpe']:>4.2f} "
                rows.append({"symbol": sym, "bedingung": name, "kosten_bps_je_seite": k, **kz,
                             "tage_pa": n_pa})
            be = float(on[bed].mean() * 10_000 / 2) if bed.any() else np.nan
            zeile += f"{be:>9.1f}bps"
            print(zeile)
        print("  Breakeven = mittlere Overnight-Rendite je Tag in bps, geteilt durch 2 Ausfuehrungen.")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"overnight_{args.panel}.csv"
    pd.DataFrame(rows).to_csv(out, index=False)
    print(f"\n  gespeichert: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
