#!/usr/bin/env python3
"""Schritt 18: Bot-Flotte verwalten.

Mehrere Bot-Varianten laufen gleichzeitig im Schattenbetrieb. Weil alle
dieselben Tage, Symbole und Kurse sehen, kuerzt sich beim Vergleich der
Marktfaktor heraus - "A schlaegt B" ist dadurch nach 6-10 Wochen
entscheidbar statt erst nach 9 Monaten.

DIE GEFAHR DABEI: Laufen 20 Bots und ist in Wahrheit keiner besser, zeigt
der beste trotzdem eine deutliche Ueberrendite - rein zufaellig. Deshalb
zaehlt dieses Skript JEDEN je angemeldeten Bot mit (auch stillgelegte) und
weist die daraus folgende Zufallsschwelle bei jeder Auswertung aus.

    python scripts/21_fleet.py                        # Uebersicht
    python scripts/21_fleet.py --startaufstellung     # die 7 Bots aus §5.3
    python scripts/21_fleet.py --divergenz            # wirkungslose Varianten finden
    python scripts/21_fleet.py --vergleich B00_basis B01_stop_eng
    python scripts/21_fleet.py --kriterien B11_dyn_ausstieg_live  # Abnahme §3.3
    python scripts/21_fleet.py --stilllegen B03_ziel_weit --grund "wirkungslos"
    python scripts/21_fleet.py --anmelden MEIN_BOT --achse stop_atr --wert 2.5 \\
        --hypothese "Begruendung mit mindestens 20 Zeichen"
"""

from __future__ import annotations

import argparse
import sys

from alpaca_bot import fleet, shadow_eval
from alpaca_bot.shadow import ShadowStore


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--startaufstellung", action="store_true",
                   help="Meldet die sieben Bots aus docs/schattenbetrieb.md §5.3 an")
    p.add_argument("--divergenz", action="store_true",
                   help="Findet Varianten, die sich nicht unterscheiden")
    p.add_argument("--vergleich", nargs=2, metavar=("BOT_A", "BOT_B"),
                   help="Gepaarter Vergleich zweier Bots")
    p.add_argument("--attribution", nargs=2, metavar=("BOT_A", "BOT_B"),
                   help="Woran lag der Unterschied?")
    p.add_argument("--kriterien", metavar="BOT_ID",
                   help="Die vier Abnahmekriterien aus BETRIEBSPLAN §3.3")
    p.add_argument("--basis", default="B00_basis",
                   help="Vergleichsbot fuer --kriterien (Standard: B00_basis)")
    p.add_argument("--stilllegen", metavar="BOT_ID")
    p.add_argument("--grund", default="")
    p.add_argument("--anmelden", metavar="BOT_ID")
    p.add_argument("--name", default="")
    p.add_argument("--familie", default="eigen")
    p.add_argument("--achse")
    p.add_argument("--wert")
    p.add_argument("--hypothese", default="")
    p.add_argument("--buch", default="spiegel", choices=["spiegel", "rangliste"])
    args = p.parse_args()

    store = ShadowStore()

    if args.startaufstellung:
        n = fleet.startaufstellung_anmelden(store)
        print(f"\n  {n} Bot(s) neu angemeldet.\n")
        print(fleet.uebersicht(store))
        return 0

    if args.anmelden:
        wert = args.wert
        aenderung = {}
        if args.achse and wert is not None:
            try:
                aenderung = {args.achse: float(wert)}
            except ValueError:
                aenderung = {args.achse: wert}
        try:
            print(fleet.anmelden(
                args.anmelden, name=args.name or args.anmelden,
                familie=args.familie, hypothese=args.hypothese,
                achse=args.achse, wert=wert, aenderung=aenderung, store=store))
        except ValueError as e:
            print(f"  FEHLER: {e}")
            return 1
        return 0

    if args.stilllegen:
        print(fleet.stilllegen(args.stilllegen, args.grund, store))
        return 0

    if args.divergenz:
        d = shadow_eval.divergenz(store)
        print("=" * 78)
        print("  UNTERSCHEIDEN SICH DIE BOTS UEBERHAUPT?")
        print("=" * 78)
        if d.empty:
            print("  Noch keine Equity-Kurven - der Schattenbetrieb muss erst laufen.")
            return 0
        print(d.to_string(index=False))
        identisch = d[d["identisch"]]
        if len(identisch):
            print()
            print("  ACHTUNG: Diese Paare sind identisch. Solche Varianten liefern")
            print("  keine Information, belegen aber einen Flottenplatz und heben")
            print("  die Zufallsschwelle fuer ALLE anderen Bots:")
            for _, r in identisch.iterrows():
                print(f"    {r['bot_a']} == {r['bot_b']}")
        return 0

    if args.vergleich:
        a, b = args.vergleich
        r = shadow_eval.vergleich_gepaart(a, b, store, buch=args.buch)
        print("=" * 78)
        print(f"  GEPAARTER VERGLEICH: {a} gegen {b}")
        print("=" * 78)
        for k, v in r.items():
            print(f"  {k:<14} {v}")
        if r.get("t_wert") is not None and not r.get("belastbar"):
            print()
            print("  NICHT BELASTBAR. Entweder liegt |t| unter der Zufallsschwelle,")
            print(f"  oder es sind weniger als {shadow_eval.MIN_TAGE} Handelstage.")
            print("  `MIN_TAGE` ist die strengere Hausmarke dieser Funktion. Fuer")
            print("  die Abnahme einer Aenderung gilt BETRIEBSPLAN §3.3:")
            print(f"      python scripts/21_fleet.py --kriterien {a}")
        return 0

    if args.kriterien:
        print(shadow_eval.kriterien_text(args.kriterien, args.basis, store))
        return 0

    if args.attribution:
        a, b = args.attribution
        r = shadow_eval.attribution(a, b, store)
        print("=" * 78)
        print(f"  ATTRIBUTION: woran lag der Unterschied {a} gegen {b}?")
        print("=" * 78)
        for k, v in r.items():
            print(f"  {k:<26} {v}")
        return 0

    print(fleet.uebersicht(store))
    return 0


if __name__ == "__main__":
    sys.exit(main())
