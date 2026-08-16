#!/usr/bin/env python3
"""Schritt 24: Neue Faktorkandidaten auf 8 Jahren pruefen.

Nutzt den vorhandenen yfinance-Cache (801 Symbole, 8 Jahre) - kein neues
Datenkontingent noetig, und der laufende Handel wird nicht beruehrt.

    python scripts/24_kandidaten_test.py
    python scripts/24_kandidaten_test.py --horizont 5

Die Pruefkette ist bewusst dieselbe wie beim PEAD-Test (Schritt 19), der
zwei Hypothesen widerlegt hat:

    1. Querschnitts-IC je Tag, t-Wert ueber die TAGE (nicht Einzelwerte)
    2. Jahresstabilitaet - Vorzeichenwechsel disqualifiziert
    3. Eigenstaendigkeit gegen die bestehenden Umkehr-Faktoren
    4. Lookahead-Pruefung des Faktors selbst

Ein Kandidat, der 1-3 besteht, ist ein Kandidat fuer den Schattenbetrieb -
kein Befund. Live wird nur, was dort vorwaerts bestanden hat.
"""

from __future__ import annotations

import argparse
import sys

import numpy as np
import pandas as pd

from alpaca_bot import datasources, kandidaten, universe
from alpaca_bot.research import _daily_cross_sectional_ic
from alpaca_bot.statistik import gruppierter_test

MARKT = "SPY"


def baue_panels(bars: pd.DataFrame, verbose: bool = True) -> dict[str, pd.DataFrame]:
    """Faktortafeln (Zeilen = Tage, Spalten = Symbole) fuer alle Kandidaten."""
    symbole = bars.index.get_level_values("symbol").unique()
    markt = None
    if MARKT in symbole:
        markt = bars.xs(MARKT, level="symbol")["close"]
        markt.index = pd.DatetimeIndex(markt.index).tz_localize(None).normalize()

    gesammelt: dict[str, dict[str, pd.Series]] = {}
    n = 0
    for sym in symbole:
        if sym == MARKT:
            continue
        df = bars.xs(sym, level="symbol").sort_index()
        if len(df) < 300:
            continue
        df.index = pd.DatetimeIndex(df.index).tz_localize(None).normalize()
        df = df[~df.index.duplicated(keep="last")]
        try:
            f = kandidaten.neue_kandidaten(df, markt)
        except Exception:  # noqa: BLE001 - einzelne Ausfaelle sind normal
            continue
        for spalte in f.columns:
            gesammelt.setdefault(spalte, {})[sym] = f[spalte]
        n += 1
        if verbose and n % 200 == 0:
            print(f"      {n} Symbole verarbeitet")

    if verbose:
        print(f"      {n} Symbole, {len(gesammelt)} Kandidaten")
    return {k: pd.DataFrame(v) for k, v in gesammelt.items()}


def vorwaertsrenditen(bars: pd.DataFrame, horizont: int) -> pd.DataFrame:
    close = bars["close"].unstack(level="symbol").sort_index()
    close.index = pd.DatetimeIndex(close.index).tz_localize(None).normalize()
    close = close[~close.index.duplicated(keep="last")]
    return close.shift(-horizont) / close - 1


def bewerte(panel: pd.DataFrame, fwd: pd.DataFrame,
            min_symbole: int = 30) -> dict:
    """IC je Tag, dann gruppierter Test ueber die Tage."""
    tage = panel.index.intersection(fwd.index)
    spalten = panel.columns.intersection(fwd.columns)
    if len(tage) < 100 or len(spalten) < min_symbole:
        return {"n_tage": 0, "ic": np.nan, "t": np.nan}

    ic, _, _ = _daily_cross_sectional_ic(
        panel.loc[tage, spalten], fwd.loc[tage, spalten], min_symbole)
    ic = ic.dropna()
    if len(ic) < 100:
        return {"n_tage": len(ic), "ic": np.nan, "t": np.nan}

    # Jeder Tag ist EINE Beobachtung - deshalb hier der Monat als Gruppe,
    # sonst waeren aufeinanderfolgende Tage wieder ueberlappend.
    r = gruppierter_test(ic, pd.Series(ic.index.to_period("M").astype(str),
                                       index=ic.index), min_gruppen=20)
    je_jahr = ic.groupby(ic.index.year).mean()
    return {
        "n_tage": len(ic),
        "ic": round(float(ic.mean()), 5),
        "t": round(float(r.t), 2) if np.isfinite(r.t) else np.nan,
        "n_monate": r.n_gruppen,
        "belastbar": r.belastbar,
        "jahre_positiv": int((je_jahr > 0).sum()),
        "jahre_gesamt": len(je_jahr),
        "stabil": bool((je_jahr > 0).all() or (je_jahr < 0).all()),
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--horizont", type=int, default=5)
    p.add_argument("--max-symbols", type=int, default=800)
    p.add_argument("--jahre", type=float, default=8.0)
    args = p.parse_args()

    print("=" * 78)
    print(f"  NEUE FAKTORKANDIDATEN  |  Horizont {args.horizont} Tage")
    print("=" * 78)

    symbols = universe.load_universe(max_symbols=args.max_symbols)
    if MARKT not in symbols:
        symbols = [*symbols, MARKT]
    print(f"\n  Kursdaten ({args.jahre:g} Jahre, aus dem Cache)")
    bars = datasources.get_history(symbols, years=args.jahre,
                                   source="yfinance", use_cache=True,
                                   verbose=False)
    if bars.empty:
        print("  Keine Daten.")
        return 1
    print(f"     {len(bars):,} Bars, "
          f"{bars.index.get_level_values('symbol').nunique()} Symbole")

    print("\n  Faktortafeln bauen")
    panels = baue_panels(bars)
    fwd = vorwaertsrenditen(bars, args.horizont)

    print("\n" + "=" * 78)
    print("  ERGEBNIS")
    print("=" * 78)
    print("\n  Vergleich: bester bestaetigter Faktor `reversal_3d` hat IC 0.018.")
    print("  Massgeblich ist die Zahl der MONATE, nicht der Tage.\n")

    zeilen = []
    for name, panel in sorted(panels.items()):
        e = bewerte(panel, fwd)
        e["kandidat"] = name
        zeilen.append(e)

    df = pd.DataFrame(zeilen).set_index("kandidat")
    df = df.sort_values("ic", key=lambda s: s.abs(), ascending=False)
    print(df[["n_tage", "n_monate", "ic", "t", "jahre_positiv",
              "jahre_gesamt", "stabil", "belastbar"]].to_string())

    beschr = kandidaten.beschreibung()
    treffer = df[df["belastbar"].fillna(False) & df["stabil"].fillna(False)]
    print("\n" + "-" * 78)
    if treffer.empty:
        print("  KEIN Kandidat besteht beide Huerden (|t| > 2 ueber >= 20")
        print("  Monate UND Vorzeichen in jedem Jahr gleich).")
        print("\n  Das ist der Normalfall, kein Fehlschlag: ~65 % publizierter")
        print("  Anomalien fallen bei sauberer Nachpruefung durch, und dieses")
        print("  Projekt hat noch nie einen Faktor ueber IC 0.05 gesehen.")
    else:
        print(f"  {len(treffer)} Kandidat(en) bestehen beide Huerden:\n")
        for name, r in treffer.iterrows():
            print(f"    {name:<22} IC {r['ic']:+.5f}  t={r['t']:.2f}  "
                  f"({r['jahre_positiv']}/{r['jahre_gesamt']} Jahre)")
            print(f"      {beschr.get(name, '')}")
        print("\n  NAECHSTER SCHRITT: Eigenstaendigkeit gegen die bestehenden")
        print("  Umkehr-Faktoren pruefen (earnings.eigenstaendigkeit). Ein")
        print("  Faktor, der mit reversal_3d zu 0.9 korreliert, ist derselbe")
        print("  Faktor unter anderem Namen und bringt keinen Basispunkt.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
