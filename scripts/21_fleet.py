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
    # Standard ist bewusst None, nicht "B00_basis". Bis zum 23.08.2026
    # stand hier fest "B00_basis" - und damit nahm das Abnahmekommando
    # eine Referenz, die BEFUNDE §G6 am 16.08.2026 bereits widerlegt
    # hatte, waehrend die Registrierung von B11 auf B09_nachkauf zeigte.
    # Gemessener Unterschied: t = 0,99 gegen B00, t = 1,24 gegen B09
    # (BEFUNDE §G19 Fund 1). None heisst "nimm die registrierte Basis".
    p.add_argument("--basis", default=None,
                   help="Vergleichsbot fuer --kriterien "
                        "(Standard: die bei der Anmeldung registrierte Basis)")
    p.add_argument("--stilllegen", metavar="BOT_ID")
    p.add_argument("--grund", default="")
    p.add_argument("--anmelden", metavar="BOT_ID")
    p.add_argument("--name", default="")
    p.add_argument("--familie", default="eigen")
    p.add_argument("--achse")
    p.add_argument("--wert")
    p.add_argument("--hypothese", default="")
    # `--buch` entfernt (22.08.2026, BEFUNDE §G16): Der gepaarte Vergleich
    # rechnet auf Equity-Kurven, und die gibt es nur im Spiegelbuch. Das
    # Argument wurde durchgereicht und von `vergleich_gepaart` ignoriert -
    # wer "rangliste" waehlte, bekam still das Spiegelbuch.
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
        r = shadow_eval.vergleich_gepaart(a, b, store)
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
    print(_trennschaerfe_tabelle(store))
    return 0


def _trennschaerfe_tabelle(store) -> str:
    """Welcher Bot kann ueberhaupt etwas zeigen - und welcher nie?

    **Warum das in den Ueberblick gehoert (23.08.2026, BEFUNDE §G22).**
    Die Uebersicht nannte bisher Achse, Wert und Status. Was fehlte, war
    die Frage davor: *Ist dieser Bot ueberhaupt in der Lage, einen
    Unterschied zu zeigen?*

    Gemessen am 23.08.2026 sind **vier von zwoelf Bots bitgleich** mit
    ihrer Referenz - B03, B05 (beide stillgelegt), B06 und B09 (beide
    laufend). Sie messen strukturell nichts, zaehlen aber dauerhaft im
    Versuchszaehler und heben damit `schwelle_sigma` fuer alle anderen.
    Das ist teils gewollt (B06 wartet auf einen Regimewechsel, §E) und
    teils ein Befund (B09, §G16 Fund 1) - aber es muss sichtbar sein,
    bevor jemand auf ein Ergebnis von ihnen wartet.
    """
    zeilen = ["", "=" * 78,
              "  TRENNSCHAERFE - was koennte jeder Bot zeigen?",
              "=" * 78,
              f"  {'Bot':<26} {'Streuung':>10} {'nachweisbar ab':>16}  Bemerkung"]
    for bot in fleet.aktive_bots(store) or []:
        # Der Basis-Bot ist die Referenz, kein Kandidat. `referenz_bot`
        # gibt fuer ihn sich selbst zurueck - die Trennschaerfe waere
        # dann zwangslaeufig "bitgleich" und stuende irrefuehrend in
        # derselben Spalte wie die echten Nullmesser B06 und B09.
        if not bot.basis_bot or bot.basis_bot == bot.bot_id:
            continue
        t = shadow_eval.trennschaerfe(bot.bot_id, store=store)
        if t.get("hinweis"):
            kurz = ("BITGLEICH - misst nichts" if "bitgleich" in t["hinweis"]
                    else t["hinweis"][:44])
            zeilen.append(f"  {bot.bot_id:<26} {'-':>10} {'-':>16}  {kurz}")
            continue
        zeilen.append(
            f"  {bot.bot_id:<26} {t['streuung'] * 100:>9.3f}% "
            f"{t['mit_80_prozent'] * 100:>15.3f}%  "
            f"= {t['kumuliert_80'] * 100:.1f} % ueber {t['n_tage']} Tage")
    zeilen += [
        "",
        "  'nachweisbar ab' = mittlere Tagesdifferenz fuer 80 %",
        "  Trefferwahrscheinlichkeit bei der aktuellen Tageszahl.",
        "  Der GESAMTE Vorsprung der Strategie liegt bei +0,11 % je Trade",
        "  (BEFUNDE §A) - grob 0,02-0,03 %/Tag auf das ganze Depot.",
        "  Ein Bot, dessen Huerde weit darueber liegt, wird auch bei",
        "  echtem Vorsprung nicht bestehen. Das ist keine Aussage ueber",
        "  den Bot, sondern ueber die Datenlage.",
    ]
    return "\n".join(zeilen)


if __name__ == "__main__":
    sys.exit(main())
