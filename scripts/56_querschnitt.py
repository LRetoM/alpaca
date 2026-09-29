#!/usr/bin/env python3
"""Schritt 56: Querschnitt-Strategien messen - marktneutral, lange Haltedauer.

    python scripts/56_querschnitt.py                  # Voranmeldung zeigen
    python scripts/56_querschnitt.py --messen
    python scripts/56_querschnitt.py --messen --spanne 30

**Die Voranmeldung steht im Code, nicht im Kopf.** `VARIANTEN` unten ist
die vollstaendige Liste dessen, was gemessen wird - vor der ersten Zahl
festgelegt (§J.2). Wer nachher eine Variante ergaenzt, hebt damit die
Zufallsschwelle fuer alle, und das Skript rechnet es vor.

**Warum es hier keine Suche gibt.** Die Ausbruch-Werkstatt hat 470.000
Konfigurationen durchprobiert. Das Ergebnis war eine Verteilung ohne
rechten Rand (§G77) und eine Achsen-Statistik, die in Teilen das
Vorzeichen verdrehte (§G76). Diese Familie wird darum bewusst mit einer
Handvoll Hypothesen gemessen statt abgesucht. Bei 8 Versuchen liegt das
Zufallsmaximum bei sqrt(2 ln 8) = 2,04 - bei 470.000 bei 5,11. Das ist
der ganze Unterschied zwischen einer pruefbaren Frage und einer
Lotterie.

**Gelesen wird die Spalte `netto` und daneben `t`.** Die Bruttorendite
ist ohne Belang, wenn die Kosten sie auffressen; der t-Wert ohne die
Kostenzeile ist ohne Belang, weil er nicht sagt, ob etwas uebrig bleibt.

**Was hier NICHT bewiesen werden kann.** Die Short-Seite ist ohne
Leihkosten gerechnet, und das Universum enthaelt nur heute gelistete
Werte. Marktneutral kuerzt den Survivorship-Rueckenwind stark, aber
nicht restlos (§G53, §4.3). Jede Zahl ist eine Obergrenze.
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from alpaca_bot import ausbruch_daten  # noqa: E402
from alpaca_bot import ausbruch_store  # noqa: E402
from alpaca_bot import querschnitt as q  # noqa: E402


# =====================================================================
#  DIE VORANMELDUNG - vollstaendig, vor der ersten Zahl
# =====================================================================
#
#  Je Eintrag genau eine Idee. Die Haltedauer variiert bewusst nur an
#  zwei Stellen (21 und 63 Tage), damit nicht die Haltedauer selbst zur
#  durchsuchten Achse wird.

VARIANTEN: list[dict] = [
    # --- Die vier Signale, alle mit Monatsumschlag ---------------------
    {"name": "momentum 60/21",
     "hypothese": "Wer ueber 60 Tage gestiegen ist, steigt weiter.",
     "cfg": dict(signal="momentum", rueckblick_tage=60, halten_tage=21)},

    {"name": "umkehr 60/21",
     "hypothese": "Das Gegenteil - Gefallene holen auf.",
     "cfg": dict(signal="umkehr", rueckblick_tage=60, halten_tage=21)},

    {"name": "tief_vola 60/21",
     "hypothese": "Ruhige Werte schlagen unruhige (Low-Vol-Anomalie).",
     "cfg": dict(signal="tief_vola", rueckblick_tage=60, halten_tage=21)},

    {"name": "momentum_je_vola 60/21",
     "hypothese": "Momentum, normiert auf die eigene Schwankung.",
     "cfg": dict(signal="momentum_je_vola", rueckblick_tage=60,
                 halten_tage=21)},

    # --- Laengerer Rueckblick UND laengere Haltedauer ------------------
    # Mit Versatz: drei Tranchen im Monatsabstand, jede haelt 63 Tage.
    # Dreifache Beobachtungszahl bei gleichem Umschlag - und der
    # gruppierte Test bekommt `horizont=3` gemeldet (§G12).
    {"name": "momentum 120/63",
     "hypothese": "Dieselbe Idee auf Quartalsebene - noch weniger Kosten.",
     "cfg": dict(signal="momentum", rueckblick_tage=120, halten_tage=63,
                 versatz_tage=21)},

    {"name": "momentum_je_vola 120/63",
     "hypothese": "Quartals-Momentum, normiert auf die eigene Schwankung.",
     "cfg": dict(signal="momentum_je_vola", rueckblick_tage=120,
                 halten_tage=63, versatz_tage=21)},

    {"name": "tief_vola 120/63",
     "hypothese": "Low-Vol auf Quartalsebene - die Anomalie gilt dort als "
                  "am stabilsten.",
     "cfg": dict(signal="tief_vola", rueckblick_tage=120, halten_tage=63,
                 versatz_tage=21)},

    {"name": "momentum 250/63",
     "hypothese": "Klassisches Zwoelfmonats-Momentum, quartalsweise "
                  "umgeschichtet.",
     "cfg": dict(signal="momentum", rueckblick_tage=250, luecke_tage=21,
                 halten_tage=63, versatz_tage=21)},

    # --- Risikoverteilung statt Signalsuche ---------------------------
    # Dasselbe Signal, nur anders umgesetzt: gleicher Risikobeitrag je
    # Wert statt gleichem Einsatz. Hebt den Sharpe, ohne neue Information
    # zu benutzen - und `t = Sharpe x Wurzel(Jahre)` macht das doppelt so
    # wirksam wie das Verdoppeln der Historie (§G79).
    {"name": "momentum 250/63 invvola",
     "hypothese": "Zwoelfmonats-Momentum, aber jeder Wert mit gleichem "
                  "Risikobeitrag statt gleichem Einsatz.",
     "cfg": dict(signal="momentum", rueckblick_tage=250, luecke_tage=21,
                 halten_tage=63, versatz_tage=21, gewichtung="inv_vola")},

    {"name": "momentum 250/63 breit",
     "hypothese": "Dasselbe mit 20 % je Seite statt 10 % - breiter "
                  "gestreut, weniger Einzelwertrisiko.",
     "cfg": dict(signal="momentum", rueckblick_tage=250, luecke_tage=21,
                 halten_tage=63, versatz_tage=21, anteil_pct=20.0)},

    {"name": "momentum 250/63 breit+invvola",
     "hypothese": "Beide Risikomassnahmen zusammen.",
     "cfg": dict(signal="momentum", rueckblick_tage=250, luecke_tage=21,
                 halten_tage=63, versatz_tage=21, anteil_pct=20.0,
                 gewichtung="inv_vola")},

    {"name": "umkehr 10/21",
     "hypothese": "Kurzfrist-Umkehr: Verlierer der letzten zwei Wochen.",
     "cfg": dict(signal="umkehr", rueckblick_tage=10, luecke_tage=0,
                 halten_tage=21)},

    # --- Engere Auswahl -----------------------------------------------
    {"name": "momentum 60/21 eng",
     "hypothese": "Nur die besten 5 % statt 10 % - starkes Signal, "
                  "weniger Werte.",
     "cfg": dict(signal="momentum", rueckblick_tage=60, halten_tage=21,
                 anteil_pct=5.0)},

    # --- Die Vergleichsgroesse, ausdruecklich KEIN Befundkandidat -----
    {"name": "momentum 60/21 NUR LONG",
     "hypothese": "Vergleich: wie viel davon ist einfach der Markt?",
     "cfg": dict(signal="momentum", rueckblick_tage=60, halten_tage=21,
                 marktneutral=False)},
]


def _kopf(text: str) -> None:
    print()
    print("=" * 82)
    print(f"  {text}")
    print("=" * 82)


def _voranmeldung_zeigen() -> int:
    _kopf("VORANMELDUNG - was gemessen wird, bevor eine Zahl existiert")
    schwelle = max(2.0, math.sqrt(2.0 * math.log(max(len(VARIANTEN), 2))))
    print(f"  {len(VARIANTEN)} Varianten. Zufallsmaximum daraus: "
          f"t = {schwelle:.2f}")
    print(f"  Projektweite Schwelle (alle Versuche): "
          f"t = {ausbruch_store.schwelle_sigma():.2f}  <- massgeblich")
    print()
    for i, v in enumerate(VARIANTEN, 1):
        print(f"  {i}. {v['name']}")
        print(f"     {v['hypothese']}")
    print()
    print("  Messen mit: python scripts/56_querschnitt.py --messen")
    print("=" * 82)
    return 0


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--messen", action="store_true")
    p.add_argument("--jahre", default="2021-2026")
    p.add_argument("--raster", default="15Min")
    p.add_argument("--spanne", type=float, default=12.2,
                   help="Spanne in bps. Fuers Gate mit 30 rechnen (§6.3)")
    p.add_argument("--leihe", type=float, default=50.0,
                   help="Leihkosten der Short-Seite in bps pro Jahr. 50 = "
                        "gut leihbar, 300 = schwer leihbar (Gegenrechnung)")
    p.add_argument("--alle-symbole", action="store_true",
                   help="Vereinigung statt Schnittmenge der Jahre - nimmt "
                        "den Filter 'muss seit dem ersten Jahr existieren' "
                        "heraus. Behebt Survivorship NICHT (§4.3)")
    p.add_argument("--jahresweise", action="store_true",
                   help="Zusaetzlich je Kalenderjahr aufschluesseln - die "
                        "Probe, ob ein Ergebnis ein Effekt ist oder eine "
                        "Marktphase (§G73)")
    args = p.parse_args()

    if not args.messen:
        return _voranmeldung_zeigen()

    jahre = []
    for teil in filter(None, args.jahre.split(",")):
        if "-" in teil:
            a, _, b = teil.strip().partition("-")
            jahre.extend(range(int(a), int(b) + 1))
        else:
            jahre.append(int(teil))
    jahre = sorted(set(jahre))

    print(f"Vorrat laden ({jahre}, {args.raster}) ...", flush=True)
    kd = ausbruch_daten.laden_kursdaten(
        jahre, raster=args.raster, alle_symbole=args.alle_symbole,
        fortschritt=lambda a, t: print(f"  {a*100:5.1f}% {t}", flush=True))
    print(f"{len(kd.arrays):,} Symbole, {kd.n_bars:,} Bars "
          f"({'Vereinigung' if args.alle_symbole else 'Schnittmenge'} "
          f"der Jahre).", flush=True)

    schwelle = ausbruch_store.schwelle_sigma()
    _kopf(f"QUERSCHNITT, marktneutral - {jahre[0]}-{jahre[-1]}, "
          f"Spanne {args.spanne:g} bps, Leihe {args.leihe:g} bps/Jahr")
    print(f"  {'Variante':<24}{'t':>7}{'netto':>9}{'brutto':>9}{'Kosten':>8}"
          f"{'Treffer':>9}{'Sharpe':>8}{'Perioden':>10}{'Horiz':>7}")
    print("  " + "-" * 85)

    zeilen = []
    je_jahr: dict[str, pd.DataFrame] = {}
    z_cfg: dict[str, dict] = {}
    for v in VARIANTEN:
        cfg = q.QuerschnittConfig(**{**v["cfg"], "spanne_bps": args.spanne,
                                     "leihe_bps_jahr": args.leihe})
        try:
            erg = q.lauf(kd, cfg)
        except Exception as e:  # noqa: BLE001
            print(f"  {v['name']:<24}  Fehler: {type(e).__name__}: {e}")
            continue
        k = erg.kennzahlen
        je_jahr[v["name"]] = erg.perioden
        z_cfg[v["name"]] = {**v["cfg"], "spanne_bps": args.spanne,
                            "leihe_bps_jahr": args.leihe}
        zeilen.append({"name": v["name"], **k,
                       "marktneutral": cfg.marktneutral})
        t = k.get("t_wert", float("nan"))
        print(f"  {v['name']:<24}{t:>7.2f}{k['mittel_pct']:>8.3f}%"
              f"{k['brutto_mittel_pct']:>8.3f}%"
              f"{k['kostenlast_pct_jahr']:>7.1f}%"
              f"{k['trefferquote_pct']:>8.1f}%{k.get('sharpe', float('nan')):>8.2f}"
              f"{k['n_perioden']:>10}{k.get('horizont_perioden', 1):>7}",
              flush=True)

    if not zeilen:
        print("  Keine Variante auswertbar.")
        return 1

    ausbruch_store.suchversuche_buchen(
        ausbruch_store.neuer_lauf(
            {"querschnitt": True, "jahre": jahre, "spanne_bps": args.spanne,
             "varianten": [v["name"] for v in VARIANTEN]},
            jahr=jahre[-1], raster=args.raster, n_symbole=len(kd.arrays),
            notiz=f"Querschnitt {len(zeilen)} Varianten"),
        len(zeilen))

    # --- Urteil ------------------------------------------------------
    echte = [z for z in zeilen if z["marktneutral"]]
    print()
    print("  Spalte 'netto' ist die Rendite JE PERIODE nach Kosten.")
    print(f"  Massgeblich: t > {schwelle:.2f} "
          f"(projektweite Zufallsschwelle, alle Versuche)")
    print()
    treffer = [z for z in echte
               if np.isfinite(z.get("t_wert", float("nan")))
               and z["t_wert"] > schwelle and z["n_perioden"] >= 20]
    if treffer:
        for z in treffer:
            print(f"  UEBER DER SCHWELLE: {z['name']} mit t = "
                  f"{z['t_wert']:.2f} bei {z['n_perioden']} Perioden.")
        print("  Naechster Schritt ist NICHT live, sondern: dieselbe Messung")
        print("  mit --spanne 30, dann je Jahr getrennt (Skript 55), dann das")
        print("  Gate. Ein Treffer unter acht Varianten ist noch kein Befund.")
    else:
        beste = max(echte, key=lambda z: (z.get("t_wert") if
                                          np.isfinite(z.get("t_wert", np.nan))
                                          else -99), default=None)
        if beste:
            print(f"  KEIN BEFUND. Beste marktneutrale Variante: "
                  f"{beste['name']}, t = {beste['t_wert']:.2f} "
                  f"gegen Schwelle {schwelle:.2f}.")
    # --- Je Jahr: Effekt oder Marktphase? ----------------------------
    if args.jahresweise:
        kandidaten = sorted(
            (z for z in echte if np.isfinite(z.get("t_wert", np.nan))),
            key=lambda z: -z["t_wert"])[:4]
        for z in kandidaten:
            p_ = je_jahr.get(z["name"])
            if p_ is None or p_.empty:
                continue
            print()
            print(f"  JE JAHR - {z['name']}")
            p_ = p_.copy()
            p_["jahr"] = pd.to_datetime(p_["stichtag"]).dt.year
            # NICHT summieren: Bei ueberlappenden Tranchen ueberdecken
            # sich die Halteperioden. Die Summe von 12 Quartalsrenditen
            # eines Jahres waere das Dreifache dessen, was das Depot
            # wirklich verdient hat - drei Tranchen halten je ein Drittel.
            # Ehrlich ist Mittel x (252 / Haltedauer).
            h_ = q.QuerschnittConfig(**z_cfg[z["name"]]).halten_tage
            print(f"    {'Jahr':<6}{'netto Mittel':>14}{'~Jahr':>10}"
                  f"{'Treffer':>9}{'Perioden':>10}")
            for jahr, teil in p_.groupby("jahr"):
                n = teil["netto_pct"]
                print(f"    {int(jahr):<6}{n.mean():>13.3f}%"
                      f"{n.mean() * 252.0 / h_:>9.1f}%"
                      f"{(n > 0).mean()*100:>8.0f}%{len(n):>10}")
            pos = p_.groupby("jahr")["netto_pct"].mean() > 0
            print(f"    -> positiv in {int(pos.sum())} von {len(pos)} Jahren")

    # Der Vergleich Nur-Long gegen marktneutral ist nur gueltig, wenn
    # BEIDE dieselbe Periodenlaenge haben - sonst stehen 63-Tage-Renditen
    # gegen 21-Tage-Renditen. Gepaart wird darum ueber den Namen.
    for z in zeilen:
        if z["marktneutral"]:
            continue
        partner_name = z["name"].replace(" NUR LONG", "")
        partner = next((y for y in echte if y["name"] == partner_name), None)
        if partner is None:
            continue
        # Die Differenz enthaelt DREI Dinge, nicht zwei. Sie nur als
        # "Markt plus Survivorship" zu beschriften waere falsch, seit die
        # Leihe im Modell steckt: Die marktneutrale Seite zahlt zusaetzlich
        # die Spanne des zweiten Beins UND die Leihe.
        c = q.QuerschnittConfig(**z_cfg[partner_name])
        zusatzkosten = c.kosten_je_rundlauf_pct() + c.leihe_je_periode_pct()
        d = z["mittel_pct"] - partner["mittel_pct"]
        print()
        print(f"  Gleiche Konfiguration, einmal ohne Short-Seite "
              f"({partner_name}):")
        print(f"    marktneutral {partner['mittel_pct']:+.3f} % je Periode, "
              f"nur Long {z['mittel_pct']:+.3f} %")
        print(f"    Differenz {d:+.3f} pp. Davon sind "
              f"{zusatzkosten:.3f} pp die Zusatzkosten der Short-Seite "
              f"(zweites Bein plus Leihe);")
        print(f"    die restlichen {d - zusatzkosten:+.3f} pp sind Marktdrift "
              f"und Survivorship, nicht Koennen (§G53).")
    print("=" * 82)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
