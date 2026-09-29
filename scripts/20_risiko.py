#!/usr/bin/env python3
"""Schritt 20: Risiko-Dach ansehen und im Ernstfall entsperren.

Das Risiko-Dach sperrt den Handel selbstaendig, wenn der Drawdown seine
Grenze reisst. Geloest wird eine Sperre NUR von Hand - eine Sperre, die
sich selbst aufhebt, kauft genau in den Crash zurueck, wegen dem sie
ausgeloest hat.

    python scripts/20_risiko.py                 # Zustand ansehen
    python scripts/20_risiko.py --kapital       # zusaetzlich Kapitalfluesse
    python scripts/20_risiko.py --pruefen       # Pruefung jetzt ausfuehren
    python scripts/20_risiko.py --entsperren    # Sperre loesen (fragt nach)
"""

from __future__ import annotations

import argparse
import sys

from alpaca_bot import kapital, risiko


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--kapital", action="store_true",
                   help="Kapitalfluesse und zeitgewichtete Rendite anzeigen")
    p.add_argument("--pruefen", action="store_true",
                   help="Risikopruefung jetzt gegen das echte Konto ausfuehren")
    p.add_argument("--entsperren", action="store_true",
                   help="Sperre loesen - verlangt eine woertliche Bestaetigung")
    args = p.parse_args()

    print(risiko.bericht())

    if args.kapital:
        print()
        print(kapital.bericht())

    if args.pruefen:
        print()
        print("Pruefe gegen das echte Konto ...")
        # schreiben=False: Eine Pruefung von Hand darf keinen Messpunkt in
        # den Kapitalverlauf schreiben. Sonst verfaelschte jeder Aufruf die
        # Zeitreihe, aus der die zeitgewichtete Rendite berechnet wird.
        f = risiko.pruefe_konto(schreiben=False)
        print(f)

    if args.entsperren:
        print()
        print("Eine Sperre zu loesen heisst: Du hast die URSACHE verstanden")
        print("und behoben. Nicht: Du willst, dass es weitergeht.")
        print()
        eingabe = input(f"Bitte woertlich eingeben - '{risiko.BESTAETIGUNG}': ")
        print(risiko.sperre_loesen(eingabe))

    return 0


if __name__ == "__main__":
    sys.exit(main())
