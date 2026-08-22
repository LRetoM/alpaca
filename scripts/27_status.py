#!/usr/bin/env python3
"""Schritt 27: Ein Blick auf alles - laeuft es, und was haben wir gelernt?

Die eine Frage, die dieses Skript beantwortet: **Arbeitet das System
gerade fuer uns, und was ist seit dem letzten Blick dazugekommen?**

Es fasst zusammen, was sonst auf sechs Kommandos verteilt liegt:

    18_health_check   laeuft der Betrieb?
    nutzung           laufen alle Bausteine, oder faellt einer still aus?
    21_fleet          wo stehen die Schattenbots?
    26_lernkern       was hat das Modell zuletzt gezeigt?
    fokus             welche Frage ist wann entscheidbar?

**Warum als eigenes Skript und nicht als weiterer Abschnitt im
Tagesbericht:** Der Tagesbericht beantwortet "was hat der Bot getan".
Dieses hier beantwortet "kommen wir voran". Das sind verschiedene
Fragen, und die zweite ging bisher im Umfang der ersten unter - so
konnte der Musterspeicher monatelang unbemerkt stillstehen (§G14).

    python scripts/27_status.py            # alles
    python scripts/27_status.py --kurz     # nur die Ampeln
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--kurz", action="store_true", help="nur die Kernzahlen")
    args = ap.parse_args()

    from alpaca_bot import data_integrity, fleet, lernkern, nutzung

    print("=" * 78)
    print("  GESAMTSTATUS")
    print("=" * 78)

    # --- 1. Laufen die Bausteine? ---------------------------------------
    befunde = nutzung.pruefen()
    schlecht = [b for b in befunde if not b.ok]
    ampel = "GRUEN" if not schlecht else "GELB"
    print(f"\n  Bausteine       : {len(befunde) - len(schlecht)}/{len(befunde)} "
          f"arbeiten wie geplant  [{ampel}]")
    for b in schlecht:
        print(f"      ! {b.baustein}: {b.detail.splitlines()[0]}")

    # --- 2. Datenintegritaet --------------------------------------------
    r = data_integrity.run_all()
    print(f"  Daten           : {r.ampel()}")
    for f in r.errors:
        print(f"      ! {f.check}")

    # --- 3. Wo steht die Flotte? ----------------------------------------
    print(f"  Flotte          : {fleet.n_versuche()} Versuche, "
          f"Schwelle t > {fleet.schwelle_sigma()}")

    # --- 4. Was sagt der Lernkern? --------------------------------------
    v = lernkern.verlauf(limit=1)
    if v.empty:
        print("  Modell          : noch keine Version trainiert")
    else:
        z = v.iloc[0]
        t = f"{z['t']:.2f}" if z["t"] == z["t"] else "-"
        print(f"  Modell          : IC {z['ic']:.4f}, t {t} ueber "
              f"{int(z['n_tage_bewertet'] or 0)} Tagen -> {z['status']}")

    if args.kurz:
        return 0

    print()
    print(nutzung.bericht())
    print()
    print(lernkern.bericht())

    # `fokus` zuletzt: Es beantwortet die Frage, mit der man weggeht -
    # was als Naechstes entscheidbar wird.
    try:
        from alpaca_bot import fokus

        print()
        print(fokus.bericht())
    except Exception as e:  # noqa: BLE001
        print(f"\n  Fokus nicht verfuegbar ({type(e).__name__}: {e})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
