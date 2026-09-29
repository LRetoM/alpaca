#!/usr/bin/env python3
"""Schritt 28: Short Seller als Signal - Short Interest (FINRA) im Faktorzoo.

Prueft HYP-2027-10: Hohe Leerverkaufsquote sagt negative Rendite voraus (als
Ausschlussfilter fuer Long-Portfolios nuetzlich), das taegliche
Reg-SHO-Shortvolumen dagegen nicht.

Drei Wege an die Daten:
  --si-datei    eine oder mehrere FINRA-Dateien (CSV/pipe), z. B. aus dem
                Archiv unter otce.finra.org/otce/EquityShortInterest/archives
  --si-api      Query-API fuer einen Zeitraum (kostenlos, ohne Schluessel;
                Format beim ersten Lauf pruefen, siehe finra.py)
  --selftest    synthetische Datei, prueft nur die Mechanik (PIT-Verzug,
                Forward-Fill, IC-Berechnung)

    python scripts/28_labor_short_interest.py --selftest
    python scripts/28_labor_short_interest.py --panel projekt --si-api 2018-01-01 2026-09-01
    python scripts/28_labor_short_interest.py --panel projekt --si-datei data/extern/finra/*.txt

Ausgabe: IC je Horizont und Jahr fuer si_days_to_cover_neg, si_aenderung_neg,
si_quote_vol_neg; Kombination Momentum x Short-Interest-Quintil.
"""

from __future__ import annotations

import argparse
import glob
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from alpaca_bot import finra, labor  # noqa: E402
from alpaca_bot.config import PROJECT_ROOT  # noqa: E402

LABOR_DIR = PROJECT_ROOT / "data" / "labor"
OUT_DIR = PROJECT_ROOT / "results" / "labor"


def _selftest_ic() -> int:
    """Synthetisches Panel, in dem hohe Short-Quote WIRKLICH negativ wirkt -
    das Skript muss den Effekt finden, und ohne eingebauten Effekt nicht.

    Der Null-Test baut die Renditen OHNE Effekt neu. Eine zufaellige
    Umsortierung der Symbole reicht nicht: Bei einem persistenten Faktor
    bleibt die (zufaellige) Zuordnung jeden Tag dieselbe, die Tages-ICs sind
    dann autokorreliert und der t-Wert wertlos - dieselbe Falle wie bei
    echten Short-Interest-Daten, weshalb dort t zusaetzlich um sqrt(Horizont)
    deflationiert wird.
    """
    rng = np.random.default_rng(11)
    kal = pd.bdate_range("2022-01-03", "2023-12-29")
    syms = [f"S{i:03d}" for i in range(120)]
    # Short Interest ist PERSISTENT (aendert sich halbmonatlich, nicht taeglich):
    # je Symbol ein Niveau plus langsame Drift, sonst korreliert shift(1) nicht.
    niveau = rng.uniform(0.5, 15, len(syms))
    drift = np.cumsum(rng.normal(0, 0.05, (len(kal), len(syms))), axis=0)
    dtc = pd.DataFrame(np.clip(niveau + drift, 0.2, 30), index=kal, columns=syms)
    rausch = rng.normal(0.0003, 0.02, (len(kal), len(syms)))

    def _ic_t(effekt: float) -> tuple[float, float]:
        r = rausch - effekt * (dtc.to_numpy() - 7.5) / 7.5
        close = pd.DataFrame(100 * np.cumprod(1 + r, axis=0), index=kal, columns=syms)
        p = labor.Panel(close=close.astype("float32"), quelle="synthetisch")
        fwd = labor.vorwaertsrendite(p, 21)
        ic = labor.ic_je_tag(-dtc.shift(1), fwd, min_symbole=30)
        return float(ic.mean()), float(ic.mean() / (ic.std(ddof=1) / np.sqrt(len(ic))))

    ic1, t1 = _ic_t(0.0010)
    ok = t1 > 3
    print(f"  [{'ok' if ok else 'FEHLER'}] Eingebauter Effekt wird gefunden: IC {ic1:+.3f}, t {t1:+.1f}")
    ic0, t0 = _ic_t(0.0)
    ok0 = abs(t0) < 3
    print(f"  [{'ok' if ok0 else 'FEHLER'}] Ohne Effekt: IC {ic0:+.3f}, t {t0:+.1f} (Rauschen erwartet)")
    return int(not (ok and ok0))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--panel", default=None)
    ap.add_argument("--si-datei", nargs="*", default=None)
    ap.add_argument("--si-api", nargs=2, metavar=("START", "ENDE"), default=None)
    ap.add_argument("--horizonte", type=int, nargs="+", default=[10, 21, 42])
    ap.add_argument("--min-dollar-volume", type=float, default=10_000_000)
    args = ap.parse_args()

    if args.selftest:
        rc = finra.selftest()
        return rc or _selftest_ic()
    if not args.panel or not (args.si_datei or args.si_api):
        print("  --panel und (--si-datei ... | --si-api START ENDE) angeben, oder --selftest.")
        return 1

    panel = labor.panel_aus_cache(LABOR_DIR / args.panel)
    if args.si_api:
        si = finra.lade_short_interest_api(*args.si_api)
    else:
        dateien = [f for muster in args.si_datei for f in glob.glob(muster)]
        si = pd.concat([finra.lade_short_interest_datei(f) for f in dateien], ignore_index=True)
    print(f"  Short Interest: {len(si):,} Zeilen, {si['symbol'].nunique():,} Symbole, "
          f"{si['settlement'].min().date()} .. {si['settlement'].max().date()}")

    etfs = {"SPY", "QQQ", "IWM", "DIA", "VTI", "EEM", "EFA", "TLT", "GLD", "HYG"}
    p_akt = panel.filtern([s for s in panel.symbole if s not in etfs])
    maske = labor.liquides_universum(p_akt, min_dollar_volume=args.min_dollar_volume)
    faktoren = finra.short_interest_panels(si, p_akt.close.index, p_akt.symbole,
                                          volumen_panel=p_akt.volume)
    zoo = labor.faktorzoo(p_akt, spy=panel.close.get("SPY"))
    faktoren["mom_konsistenz"] = zoo["mom_konsistenz"]
    df = labor.ic_messen(faktoren, p_akt, horizonte=tuple(args.horizonte), maske=maske)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"short_interest_{args.panel}.csv"
    df.to_csv(out, index=False)
    cols = ["faktor", "horizont", "ic", "t_deflated", "anteil_jahre_positiv", "schlechtestes_jahr", "urteil"]
    print(df[cols].round(4).to_string(index=False))

    # Momentum x Short-Interest: hilft der Ausschluss stark geshorteter Werte?
    if "si_days_to_cover_neg" in faktoren:
        dtc = -faktoren["si_days_to_cover_neg"]
        hoch = dtc.rank(axis=1, pct=True) > 0.8
        fwd = labor.vorwaertsrendite(p_akt, 21)
        ic_alle = labor.ic_je_tag(zoo["mom_konsistenz"], fwd, maske)
        ic_ohne = labor.ic_je_tag(zoo["mom_konsistenz"].where(~hoch), fwd, maske)
        print(f"\n  Momentum-IC (21 Tage) alle Werte: {ic_alle.mean():+.4f}  "
              f"ohne oberstes Short-Quintil: {ic_ohne.mean():+.4f}")
    print(f"\n  gespeichert: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
