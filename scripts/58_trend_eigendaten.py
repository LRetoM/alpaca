#!/usr/bin/env python3
"""Schritt 58: Der Trendbot auf UNSEREN Daten statt auf yfinance.

    python scripts/58_trend_eigendaten.py --vergleich
    python scripts/58_trend_eigendaten.py --walk-forward

**Warum das gebaut wird.** §G52 hat die Trendfolge-Familie auf
yfinance-Daten gemessen (Sharpe 0,88, -16 % Drawdown, positiv 2008 und
2022) - das kohaerenteste Ergebnis des Projekts. Hier laeuft derselbe
Code auf einem **unabhaengigen Datensatz**: dem eigenen Alpaca-Vorrat,
aus 15-Minuten-Bars auf Tagesschluesse verdichtet.

Keine neue Idee, sondern die Gegenprobe. Zwei Datenquellen, die dasselbe
sagen, sind mehr wert als eine Quelle, die es zweimal sagt.

**Die Dividendenfrage - geprueft, nicht angenommen.** Bei Anleihen-ETFs
wie IEF und TLT ist die Ausschuettung der Grossteil der Rendite. Direkt
an der API nachgemessen (12.09.2026, TLT, 04.01.2021):

    Adjustment.RAW       157,2750
    Adjustment.ALL       130,4800   <- der Vorrat benutzt diesen
    Adjustment.DIVIDEND  130,4800

Der Vorrat ist also total-return-bereinigt, genau wie `auto_adjust=True`
bei yfinance. Ohne diese Pruefung waere jede Allokation zwischen Aktien
und Anleihen verzerrt gewesen, ohne dass es auffaellt.

**Was der Vergleich NICHT leisten kann.** Der Vorrat beginnt am
27.07.2020 (§G86): sechs Jahre statt achtzehn, ohne 2008 und ohne den
Maerz-2020-Crash - also ohne die Ereignisse, in denen sich die defensive
Eigenschaft dieser Familie ueberhaupt zeigt. **Eine Bestaetigung hier ist
schwach, ein Widerspruch waere ein Alarmzeichen.**
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd  # noqa: E402

from alpaca_bot import ausbruch_daten  # noqa: E402
from alpaca_bot import querschnitt as q  # noqa: E402
from alpaca_bot import trend  # noqa: E402


def _kopf(text: str) -> None:
    print()
    print("=" * 78)
    print(f"  {text}")
    print("=" * 78)


def tageskurse_aus_vorrat(symbole: list[str], jahre: list[int],
                          raster: str = "15Min") -> pd.DataFrame:
    """Tagesschlusskurse der genannten Symbole aus dem eigenen Vorrat."""
    kd = ausbruch_daten.laden_kursdaten(
        jahre, raster=raster, alle_symbole=True,
        fortschritt=lambda a, t: None)
    fehlt = [s for s in symbole if s not in kd.arrays]
    if fehlt:
        raise SystemExit(
            f"Nicht im Vorrat: {fehlt}. Erst laden, siehe "
            f"scripts/48_ausbruch_daten.py")
    kurse, _umsatz = q.tageskurse(kd)
    px = kurse[symbole].dropna(how="all")
    px.index = pd.to_datetime(px.index, utc=True)
    return px.sort_index()


def _grundlage(px: pd.DataFrame) -> None:
    jahre = (px.index[-1] - px.index[0]).days / 365.25
    print(f"  {px.index[0].date()} bis {px.index[-1].date()} "
          f"({jahre:.1f} Jahre, {len(px)} Handelstage)")
    print()
    print(f"  {'ETF':<6}{'gesamt':>10}{'pro Jahr':>11}   "
          f"(total return, dividendenbereinigt)")
    for sym in px.columns:
        s = px[sym].dropna()
        if len(s) < 100:
            print(f"  {sym:<6}  zu wenige Tage - faellt heraus")
            continue
        ges = (s.iloc[-1] / s.iloc[0] - 1.0) * 100.0
        pa = ((s.iloc[-1] / s.iloc[0]) ** (1 / jahre) - 1.0) * 100.0
        print(f"  {sym:<6}{ges:>9.1f}%{pa:>10.1f}%")


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--universe", default="broad",
                   choices=sorted(trend.UNIVERSEN))
    p.add_argument("--vergleich", action="store_true")
    p.add_argument("--walk-forward", dest="walk_forward", action="store_true")
    p.add_argument("--strategie", default="dualmom",
                   choices=["tsmom", "dualmom", "ma_filter"])
    p.add_argument("--lookback", type=int, default=9)
    p.add_argument("--vol-ziel", dest="vol_ziel", type=float, default=0.10)
    p.add_argument("--raster", default="15Min")
    args = p.parse_args()

    symbole = trend.UNIVERSEN[args.universe]
    jahre = ausbruch_daten.jahre_vorhanden(args.raster)
    print(f"Eigener Vorrat {jahre}, Universum {args.universe}: {symbole}",
          flush=True)
    px = tageskurse_aus_vorrat(symbole, jahre, args.raster)

    _kopf("GRUNDLAGE - eigener Alpaca-Vorrat statt yfinance")
    _grundlage(px)

    if args.vergleich:
        _kopf("VERGLEICH aller Strategien auf eigenen Daten")
        tab = trend.vergleich(px)
        print(tab.to_string() if isinstance(tab, pd.DataFrame) else tab)
    elif args.walk_forward:
        _kopf("WALK-FORWARD auf eigenen Daten")
        wf = trend.walk_forward(px)
        print(wf.to_string() if isinstance(wf, pd.DataFrame) else wf)
    else:
        cfg = trend.TrendConfig(strategie=args.strategie,
                                lookback_monate=args.lookback,
                                vol_ziel=args.vol_ziel)
        res = trend.run(px, cfg)
        _kopf(f"{args.strategie}, Lookback {args.lookback} Monate, "
              f"Vol-Ziel {args.vol_ziel:.0%}")
        ber = trend.auswerten(res, px)
        print(ber.to_string() if isinstance(ber, pd.DataFrame) else ber)

    print()
    print("  VORBEHALT: Vorrat ab 27.07.2020 (§G86) - sechs Jahre, ohne 2008")
    print("  und ohne Maerz 2020. Genau die Krisen fehlen, in denen sich die")
    print("  defensive Eigenschaft zeigt. Bestaetigung hier ist schwach,")
    print("  ein Widerspruch waere ein Alarmzeichen.")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
