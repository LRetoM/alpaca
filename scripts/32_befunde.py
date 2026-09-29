#!/usr/bin/env python3
"""Schritt 32: Befundregister - Rueckfuellung, Bericht, Versuchszaehler.

Das Register (`befunde.py`) wird von den Labor-Skripten automatisch
gefuellt. Dieses Skript rendert daraus `docs/befunde-2027.md` (das ins
Repo committete Gedaechtnis) und kann bereits vorhandene Ergebnis-CSVs
rueckwirkend eintragen.

    python scripts/32_befunde.py --bericht              # docs/befunde-2027.md neu erzeugen
    python scripts/32_befunde.py --rueckfuellen         # results/labor/portfolio_*.csv einlesen
    python scripts/32_befunde.py --zaehler              # wie viele Versuche, welche Schwelle
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from alpaca_bot import befunde  # noqa: E402
from alpaca_bot.config import PROJECT_ROOT  # noqa: E402

OUT_DIR = PROJECT_ROOT / "results" / "labor"

# Zeitraeume der bekannten Panels (fuer die Rueckfuellung aus CSVs ohne Datum)
PANEL_ZEITRAUM = {"qlib": "2006-2020", "sp500_close": "2016-2026", "lean": "2000-2021"}


def rueckfuellen() -> int:
    n = 0
    vorhanden = befunde.laden()
    schon = set()
    if not vorhanden.empty:
        schon = set(zip(vorhanden["panel"], vorhanden["variante"], vorhanden.get("p_regime", ""),
                        vorhanden.get("p_kosten_bps", ""), vorhanden.get("p_haltedauer", ""),
                        vorhanden.get("p_top_n", "")))
    for csv in sorted(OUT_DIR.glob("portfolio_*.csv")):
        df = pd.read_csv(csv)
        if df.empty or "variante" not in df.columns:
            continue
        panel = csv.stem.split("_")[1] if csv.stem.count("_") >= 2 else "?"
        if "sp500" in csv.stem:
            panel = "sp500_close"
        for _, r in df.iterrows():
            key = (panel, r["variante"], r["regime"], float(r["kosten_bps"]), int(r["H"]), int(r["top_n"]))
            if key in schon:
                continue
            k = {c: float(r[c]) for c in ("cagr", "bench_cagr", "univ_cagr", "sharpe", "max_drawdown",
                                          "bench_maxdd", "umschlag_pa", "kosten_pa", "exposure") if c in r and pd.notna(r[c])}
            urteil, lehre = befunde.urteil_portfolio(k)
            befunde.eintragen(skript="22", panel=panel, variante=r["variante"],
                              zeitraum=PANEL_ZEITRAUM.get(panel, "?"),
                              parameter={"regime": r["regime"], "haltedauer": int(r["H"]),
                                         "kosten_bps": float(r["kosten_bps"]), "top_n": int(r["top_n"])},
                              kennzahlen=k, urteil=urteil, lehre=lehre + " (rueckgefuellt)",
                              quelle_lauf=str(csv))
            schon.add(key)
            n += 1
    return n


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bericht", action="store_true")
    ap.add_argument("--rueckfuellen", action="store_true")
    ap.add_argument("--zaehler", action="store_true")
    args = ap.parse_args()
    if args.rueckfuellen:
        print(f"  {rueckfuellen()} Befunde rueckgefuellt")
    if args.zaehler or not (args.bericht or args.rueckfuellen):
        print(f"  Versuchszaehler: {befunde.versuchszaehler()}")
    if args.bericht:
        text = befunde.bericht(schreiben=True)
        print(f"  {befunde.BERICHT} geschrieben ({len(text.splitlines())} Zeilen)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
