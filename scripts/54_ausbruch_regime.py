#!/usr/bin/env python3
"""Schritt 54: Bringt ein Marktregime-Filter etwas? Messung im LERNfenster.

    python scripts/54_ausbruch_regime.py
    python scripts/54_ausbruch_regime.py --sma 26,78,130 --referenz QQQ

**Warum im Lernfenster gemessen wird.** Genau dafuer ist es da. Das
Prueffenster ist die einzige Ressource dieses Projekts, die sich
verbraucht: Jede Frage, die man ihm stellt, macht die naechste Antwort
weniger wert. Eine Idee wird deshalb erst hier durchgerechnet - und nur
wenn sie hier deutlich traegt, lohnt die eine vorangemeldete
Gate-Pruefung (`scripts/53_ausbruch_gate.py`).

**Die Hypothese, vorab und in einem Satz.** docs/AUSBRUCH.md §7 haelt
fest: "Momentum funktioniert in steigenden Maerkten fast immer und
bricht in Wenden zusammen." Wenn das stimmt, muss ein Filter, der nur
bei steigendem Referenzwert einsteigen laesst, die Rendite je Trade
heben - und nicht bloss die Zahl der Trades senken.

**Woran die Idee scheitern darf.** Ein Filter, der die Trades halbiert
und die Rendite je Trade unveraendert laesst, hat nichts erklaert. Er
hat nur weniger gehandelt. Deshalb steht in der Ausgabe die Rendite JE
TRADE neben der Gesamtrendite, und der t-Wert neben beidem.

Die Versuche werden im Zaehler gebucht (`ausbruch_store`), damit die
Zufallsschwelle des Projekts sie kennt. Wer misst, ohne zu zaehlen,
senkt die eigene Huerde.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np  # noqa: E402

from alpaca_bot import ausbruch  # noqa: E402
from alpaca_bot import ausbruch_daten  # noqa: E402
from alpaca_bot import ausbruch_store  # noqa: E402
from alpaca_bot import ausbruch_suche as su  # noqa: E402


def _kopf(text: str) -> None:
    print()
    print("=" * 78)
    print(f"  {text}")
    print("=" * 78)


def _zeile(name: str, k: dict, basis: dict | None = None) -> str:
    t = float(k.get("t_wert", float("nan")))
    n = int(k.get("n_trades", 0) or 0)
    mittel = float(k.get("mittel_pct", 0.0))
    rendite = float(k.get("rendite_pct", 0.0))
    tage = int(k.get("n_handelstage", 0) or 0)
    zusatz = ""
    if basis is not None and basis.get("n_trades"):
        anteil = 100.0 * n / int(basis["n_trades"])
        delta = mittel - float(basis.get("mittel_pct", 0.0))
        zusatz = f"  {anteil:5.1f} % der Trades  je Trade {delta:+.3f} pp"
    return (f"  {name:<22}{t:>7.2f}{rendite:>9.2f} %{mittel:>9.3f} %"
            f"{n:>7}{tage:>6}{zusatz}")


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--referenz", default="QQQ",
                   help="Referenzwert fuer das Marktregime")
    p.add_argument("--sma", default="26,78,130",
                   help="Laengen des gleitenden Mittels in Bars "
                        "(26 = 1 Handelstag)")
    p.add_argument("--lernanteil", type=float, default=0.7)
    p.add_argument("--raster", default="15Min")
    p.add_argument("--jahre", default=None,
                   help="z.B. 2023-2026. Ohne Angabe ALLE vorhandenen - "
                        "was sich aendert, sobald Jahre nachgeladen "
                        "werden. Fuer einen Vergleich mit einer frueheren "
                        "Messung die Jahre ausdruecklich nennen.")
    args = p.parse_args()

    laengen = [int(x) for x in args.sma.split(",") if x.strip()]

    elite = su.elite_lesen() or {}
    config = dict(elite.get("config") or {})
    if not config:
        print("Keine Elite-Konfiguration gefunden - laeuft die Suche schon?")
        return 1

    if args.jahre:
        jahre = []
        for teil in filter(None, args.jahre.split(",")):
            if "-" in teil:
                a, _, b = teil.strip().partition("-")
                jahre.extend(range(int(a), int(b) + 1))
            else:
                jahre.append(int(teil))
        jahre = sorted(set(jahre))
    else:
        jahre = ausbruch_daten.jahre_vorhanden(args.raster)
    print(f"Vorrat laden ({jahre}, {args.raster}) ...", flush=True)
    kd = ausbruch_daten.laden_kursdaten(
        jahre, raster=args.raster,
        fortschritt=lambda a, t: print(f"  {a*100:5.1f}% {t}", flush=True))
    lern, _pruef, grenze = su.teilen(kd, args.lernanteil)
    print(f"{len(kd.arrays):,} Symbole. Lernfenster bis {grenze}.", flush=True)

    if args.referenz not in kd.arrays:
        print(f"Referenzwert {args.referenz} liegt nicht im Vorrat.")
        return 1

    _kopf(f"MARKTREGIME-FILTER im LERNfenster - Referenz {args.referenz}")
    print(f"  {'Variante':<22}{'t':>7}{'Rendite':>11}{'je Trade':>11}"
          f"{'Trades':>7}{'Tage':>6}")
    print("  " + "-" * 74)

    t0 = time.time()
    basis_erg = ausbruch.lauf(lern, ausbruch.AusbruchConfig(**config))
    basis = basis_erg.kennzahlen
    print(_zeile("ohne Filter", basis), flush=True)

    ergebnisse = {"ohne": basis}
    for laenge in laengen:
        cfg = ausbruch.AusbruchConfig(
            **{**config, "regime_symbol": args.referenz,
               "regime_sma_bars": laenge})
        k = ausbruch.lauf(lern, cfg).kennzahlen
        ergebnisse[f"sma{laenge}"] = k
        tage_txt = f"SMA {laenge} ({laenge/26:.0f} Tage)"
        print(_zeile(tage_txt, k, basis), flush=True)

    n_versuche = 1 + len(laengen)
    lauf_id = ausbruch_store.neuer_lauf(
        {"regime_ab": True, "referenz": args.referenz, "sma": laengen,
         "config": config},
        jahr=jahre[-1], raster=args.raster, n_symbole=len(kd.arrays),
        notiz=f"Regime-A/B {args.referenz} {laengen}")
    ausbruch_store.suchversuche_buchen(lauf_id, n_versuche)
    ausbruch_store.abschliessen(lauf_id, basis)

    print()
    print(f"  {n_versuche} Versuche gebucht, {time.time() - t0:.0f} s. "
          f"Zufallsschwelle jetzt {ausbruch_store.schwelle_sigma():.2f}.")

    # --- Das Urteil, an den vorab genannten Kriterien -----------------
    beste = max(
        (n for n in ergebnisse if n != "ohne"),
        key=lambda n: float(ergebnisse[n].get("mittel_pct", -99)),
        default=None)
    print()
    if beste is None:
        print("  Keine Variante gerechnet.")
        return 0
    bk = ergebnisse[beste]
    d_mittel = float(bk.get("mittel_pct", 0)) - float(basis.get("mittel_pct", 0))
    anteil = (100.0 * int(bk.get("n_trades", 0) or 0)
              / max(int(basis.get("n_trades", 0) or 1), 1))
    print(f"  Beste Variante: {beste}, je Trade {d_mittel:+.3f} pp "
          f"gegenueber ohne Filter, bei {anteil:.0f} % der Trades.")
    if d_mittel <= 0:
        print("  URTEIL: Der Filter erklaert nichts. Er handelt nur weniger.")
        print("  Kein Grund, dafuer das Prueffenster anzufassen.")
    elif anteil < 25.0:
        print("  VORSICHT: Weniger als ein Viertel der Trades bleibt uebrig.")
        print("  Ein Gewinn je Trade auf so kleiner Zahl ist Auswahl, "
              "kein Effekt.")
    else:
        print("  Der Filter hebt die Rendite je Trade. Naechster Schritt "
              "waere EINE")
        print("  vorangemeldete Gate-Pruefung - nicht mehr Varianten.")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
