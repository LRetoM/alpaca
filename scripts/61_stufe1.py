#!/usr/bin/env python3
"""Schritt 61: Stufe 1 in einem Lauf - alle Bots auf dem Projektcache bis 2026.

Das ist der Test, den die Session vom 29.09.2026 im Container NICHT machen konnte: Dort gibt es
Daten mit Volumen nur bis 2020 (qlib) und ab 2016 bis 2026 nur Schlusskurse heutiger S&P-Werte
(Survivorship). Der Projektcache auf dem Mac (2.168 Symbole, 2018-2026, mit Volumen) schliesst
diese Luecke. Der Runner fuehrt der Reihe nach aus und ueberspringt, was schon vorhanden ist:

  1. Panel aus dem Projektcache bauen                       (20_labor_daten.py)
  2. ML-Walk-forward, Vorhersagen sichern                   (23_labor_ml_ranking.py)
  3. Engine-Replays mit gemessenen Kosten 12,2 + 5 bps      (31_simulate_ranking.py)
       Handmix (Stop 3), Hybrid (Stop 3), Hybrid (ohne Stop)
  4. Jahresliste: Trendbot + Aktien-Bots + SPY              (60_jahresliste.py --panel)
  5. Trade-Autopsie und Befundregister                      (33_, 32_)

    python scripts/61_stufe1.py --pfad "$HOME/Library/Application Support/alpaca-bot/data/cache/bars/yfinance_2168_*_8y.parquet"
    python scripts/61_stufe1.py --name projekt --neu          # alles neu rechnen

Die Ausgabe landet zusaetzlich in results/labor/stufe1_<name>.txt (zum Einfuegen in den Chat).
Dauer auf einem Mac mit 16 GB: etwa 1 bis 1,5 Stunden, davon das meiste ML und Replays.
"""

from __future__ import annotations

import argparse
import glob
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable
OUT = ROOT / "results" / "labor"
KOSTEN = ["--spread-bps", "12.2", "--slippage-bps", "5"]
REPLAY = ["--stop-atr", "3", "--min-hold", "21", "--max-hold", "63", "--exit-rank", "0.2", "--max-new", "3"]


def lauf(titel: str, cmd: list[str], log, *, erwartet: Path | None = None, neu: bool = False, voll: bool = False) -> bool:
    if erwartet is not None and erwartet.exists() and not neu:
        msg = f"\n=== {titel}: übersprungen (vorhanden: {erwartet.name})"
        print(msg); log.write(msg + "\n"); return True
    t0 = time.time()
    msg = f"\n=== {titel}\n    $ {' '.join(cmd)}"
    print(msg, flush=True); log.write(msg + "\n")
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    zeilen = (r.stdout + r.stderr).strip().splitlines()
    tail = "\n".join(zeilen if voll else zeilen[-12:])
    print(tail); log.write(tail + "\n")
    ok = r.returncode == 0
    msg = f"    -> {'ok' if ok else 'FEHLGESCHLAGEN (Code %d)' % r.returncode}  ({time.time() - t0:.0f} s)"
    print(msg, flush=True); log.write(msg + "\n"); log.flush()
    return ok


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pfad", default=None, help="Projektcache-Parquet (Glob erlaubt); nur noetig, wenn das Panel noch fehlt")
    ap.add_argument("--name", default="projekt")
    ap.add_argument("--symbole", type=int, default=800, help="liquideste N Symbole fuer die Replays")
    ap.add_argument("--neu", action="store_true", help="vorhandene Ergebnisse neu rechnen")
    a = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    panel = ROOT / "data" / "labor" / a.name
    with (OUT / f"stufe1_{a.name}.txt").open("w", encoding="utf-8") as log:
        if not (panel / "close.parquet").exists() or a.neu:
            if not a.pfad:
                print("  Panel fehlt und --pfad ist nicht gesetzt (Projektcache-Parquet angeben)."); return 2
            treffer = sorted(glob.glob(str(Path(a.pfad).expanduser())))
            if not treffer:
                print(f"  Keine Datei gefunden: {a.pfad}"); return 2
            if not lauf("1. Panel bauen", [PY, "scripts/20_labor_daten.py", "--quelle", "projekt", "--pfad", treffer[-1],
                                            "--name", a.name], log, neu=True):
                return 1
        pred = OUT / f"ml_pred_{a.name}_h21.parquet"
        lauf("2. ML-Walk-forward (Vorhersagen)", [PY, "scripts/23_labor_ml_ranking.py", "--panel", a.name, "--horizont", "21",
                                                 "--stichprobe", "5", "--min-dollar-volume", "25000000", "--top-n", "50"],
             log, erwartet=pred, neu=a.neu)
        basis = [PY, "scripts/31_simulate_ranking.py", "--panel", a.name, "--variante", "momentum", "--symbole", str(a.symbole)]
        tag = f"simulate_ranking_{a.name}_momentum_stop%s_h21-63_x0.2_c5_vola%s_n3_s12.2_kapital.csv"
        lauf("3a. Replay Handmix, Stop 3", basis + REPLAY + KOSTEN, log, erwartet=OUT / (tag % ("3", "")), neu=a.neu)
        if pred.exists():
            lauf("3b. Replay Hybrid, Stop 3", basis + REPLAY + KOSTEN + ["--ml-pred", str(pred), "--hybrid"], log,
                 erwartet=OUT / (tag % ("3", "_hybrid")), neu=a.neu)
            ohne = [x for x in REPLAY]; ohne[ohne.index("--stop-atr") + 1] = "99"
            lauf("3c. Replay Hybrid, ohne Stop", basis + ohne + KOSTEN + ["--ml-pred", str(pred), "--hybrid"], log,
                 erwartet=OUT / (tag % ("99", "_hybrid")), neu=a.neu)
        else:
            msg = "\n  Keine ML-Vorhersagen (Schritt 2 fehlgeschlagen) - Hybrid wird nicht gerechnet."
            print(msg); log.write(msg + "\n")
        lauf("4. Jahresliste", [PY, "scripts/60_jahresliste.py", "--panel", a.name], log, voll=True)
        eigene = sorted(str(f) for f in OUT.glob(f"simulate_ranking_{a.name}_*.csv") if not f.name.endswith("_kapital.csv"))
        if eigene:
            lauf("5a. Trade-Autopsie (nur dieses Panel)", [PY, "scripts/33_trade_autopsie.py", "--datei", *eigene], log)
        lauf("5b. Befundregister", [PY, "scripts/32_befunde.py", "--bericht", "--zaehler"], log)
    print(f"\n  Fertig. Alles steht in {OUT / f'stufe1_{a.name}.txt'} und results/labor/jahresliste_{a.name}.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
