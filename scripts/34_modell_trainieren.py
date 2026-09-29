#!/usr/bin/env python3
"""Schritt 34: Prognosemodell fuer den Bot trainieren (Score-Quelle "ml").

Trainiert EIN LightGBM-Modell auf dem Faktorzoo eines Labor-Panels bis zu
einem Stichtag (mit Embargo) und legt es unter `models/` ab - klein genug
fuer das Repo, mit Metadaten (Merkmale, Horizont, Stichtag, Wichtigkeit).
Der Bot laedt es mit `12_daemon.py --strategy ranking --score-quelle ml`.

Bewertet wird hier NICHTS - das tun `23_` (Walk-forward, OOS-IC, Portfolio
gegen Handmix auf demselben Universum) und `31_ --ml-pred` (Engine-Pfad).
Dieses Skript ist nur der Produktionsschritt: dieselben Parameter, dieselbe
Vorverarbeitung, alle Daten bis zum Stichtag.

    python scripts/34_modell_trainieren.py --panel projekt --horizont 21 --bis 2026-12-01
    python scripts/34_modell_trainieren.py --panel qlib --start 2006-01-01 --bis 2020-11-01

Regel (masterplan §7.2): Training einmal im Januar, Stichtag Ende November
(Embargo), unter dem Jahr wird nicht nachtrainiert.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from alpaca_bot import befunde, labor, modell  # noqa: E402
from alpaca_bot.config import PROJECT_ROOT  # noqa: E402

LABOR_DIR = PROJECT_ROOT / "data" / "labor"
ETFS = {"SPY", "QQQ", "IWM", "DIA", "VTI", "EEM", "EFA", "TLT", "GLD", "HYG", "USO", "BNO"}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--panel", required=True)
    ap.add_argument("--start", default=None)
    ap.add_argument("--bis", default=None, help="Stichtag (Embargo wird abgezogen); Standard: letzter Tag")
    ap.add_argument("--horizont", type=int, default=21)
    ap.add_argument("--stichprobe", type=int, default=5, help="jede k-te Zeile (Tag)")
    ap.add_argument("--min-preis", type=float, default=5.0)
    ap.add_argument("--min-dollar-volume", type=float, default=25_000_000)
    ap.add_argument("--name", default=None, help="Standard: lgbm_h<H>_<bis>")
    ap.add_argument("--verzeichnis", default=None, help="Standard: models/")
    args = ap.parse_args()

    t0 = time.time()
    panel = labor.panel_aus_cache(LABOR_DIR / args.panel).schneiden(args.start, args.bis)
    print(f"  {panel.beschreibung()}")
    spy = panel.close["SPY"] if "SPY" in panel.close.columns else None
    p_akt = panel.filtern([s for s in panel.symbole if s not in ETFS])
    maske = labor.liquides_universum(p_akt, min_preis=args.min_preis, min_dollar_volume=args.min_dollar_volume)
    haeufig = maske.columns[maske.mean(axis=0) >= 0.10]
    p_akt = p_akt.filtern(list(haeufig))
    maske = maske[list(haeufig)]
    faktoren = labor.faktorzoo(p_akt, spy=spy)
    fwd = labor.vorwaertsrendite(p_akt, args.horizont)
    tage = list(fwd.index)[::args.stichprobe]
    lang = modell.merkmalstabelle(faktoren, maske, tage=tage, ziel=fwd)
    bis = pd.Timestamp(args.bis) if args.bis else pd.Timestamp(p_akt.close.index[-1])
    print(f"  {len(lang):,} Zeilen, {len(faktoren)} Merkmale, Stichtag {bis.date()}, "
          f"Embargo {modell.embargo_tage(args.horizont)} Tage")
    m = modell.trainieren(lang, list(faktoren), args.horizont, bis=bis,
                          quelle=f"{args.panel} {p_akt.close.index[0].date()}..{bis.date()}")
    name = args.name or f"lgbm_h{args.horizont}_{bis.date()}"
    pfad = modell.speichern(m, name, Path(args.verzeichnis) if args.verzeichnis else None)
    print(f"\n  Modell {name}: {m.n_zeilen:,} Zeilen bis {m.trainiert_bis}")
    print("  Wichtigkeit (Gain-Anteil):")
    for k, v in sorted(m.wichtigkeit.items(), key=lambda kv: -kv[1])[:10]:
        print(f"      {k:<20}{v:>7.1%}")
    befunde.eintragen(skript="34", panel=args.panel, variante=name,
                      zeitraum=f"{p_akt.close.index[0].year}-{bis.year}",
                      parameter={"horizont": args.horizont, "stichprobe": args.stichprobe,
                                 "min_dollar_volume": args.min_dollar_volume, "bis": str(bis.date())},
                      kennzahlen={"n_zeilen": m.n_zeilen, "n_merkmale": len(m.merkmale),
                                  **{f"gain_{k}": v for k, v in list(sorted(m.wichtigkeit.items(), key=lambda kv: -kv[1]))[:5]}},
                      urteil="kandidat", hypothese="HYP-2027-06",
                      lehre="Produktionsmodell trainiert; Bewertung nur ueber 23_ (Walk-forward) und 31_ --ml-pred",
                      quelle_lauf=str(pfad))
    print(f"\n  gespeichert: {pfad} (+ .json)   ({time.time() - t0:.0f} s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
