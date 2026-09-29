#!/usr/bin/env python3
"""Schritt 49: Dauerlauf - sucht weiter, bis du sie beendest.

    python scripts/49_ausbruch_dauerlauf.py                   # alles, was da ist
    python scripts/49_ausbruch_dauerlauf.py --jahre 2021-2025
    python scripts/49_ausbruch_dauerlauf.py --symbole 2000 --score calmar
    python scripts/49_ausbruch_dauerlauf.py --stunden 12      # endet von selbst

**Das ist das Startkommando.** Es laedt den Vorrat einmal, richtet ihn
einmal aus und sucht dann ohne Unterbrechung weiter - Erkundung,
Bergsteigen, Neustart im Wechsel. Strg+C beendet und gibt das beste
Ergebnis aus.

**Tempo.** Nach dem Umbau vom 11.09.2026 kostet ein Versuch rund
**0,08 Sekunden** bei 598 Symbolen (vorher 5,7 - die gemeinsame
Zeitachse wurde bei jedem Versuch neu gebaut). Der Engpass ist damit
das einmalige Laden, nicht mehr die Suche:

    600 Symbole x 1 Jahr   ->  ~10 s laden,  ~45.000 Versuche/Stunde
    2.200 Symbole x 5 Jahre -> ~4 Min laden,  ~2.000 Versuche/Stunde

**Was das Ergebnis wert ist, haengt an einer Zahl - und die steht
rechts.** Optimiert wird auf dem Lernfenster; das Prueffenster wird nur
nachgerechnet und nie zur Auswahl benutzt. Bei 45.000 Versuchen liegt
das Zufallsmaximum im Lernfenster bei `sqrt(2 ln 45000)` = **4,63** -
eine Konfiguration mit t = 4 ist dort also der NORMALFALL und kein
Fund. Traegt sie im Prueffenster nicht, ist nichts da.

Vorher Daten laden: `python scripts/48_ausbruch_daten.py --nasdaq
--shortable --jahre 2021-2025`
"""

from __future__ import annotations

import argparse
import shutil
import signal
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from alpaca_bot import ausbruch, ausbruch_daten, ausbruch_store  # noqa: E402
from alpaca_bot import ausbruch_suche as su  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from importlib import import_module  # noqa: E402

_anzeige = import_module("47_ausbruch_suche")

_STOPP = False


def _stoppen(*_a) -> None:
    global _STOPP
    if _STOPP:
        print("\n  Sofortabbruch.")
        raise SystemExit(130)
    _STOPP = True
    print(f"\n\033[33m  Halte an - laufender Versuch wird zu Ende "
          f"gerechnet ...\033[0m", flush=True)


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--jahre", default=None,
                   help="z.B. 2021-2025 (Vorgabe: alles, was vorliegt)")
    p.add_argument("--raster", default="15Min")
    p.add_argument("--symbole", type=int, default=None,
                   help="nur die ersten N - spart Ladezeit und Speicher")
    p.add_argument("--score", default="t", choices=list(su.SCORES))
    p.add_argument("--min-trades", type=int, default=60)
    p.add_argument("--lernanteil", type=float, default=0.7)
    p.add_argument("--erkundung", type=int, default=60)
    p.add_argument("--fest", default="")
    p.add_argument("--saat", type=int, default=None)
    p.add_argument("--stunden", type=float, default=None,
                   help="nach so vielen Stunden von selbst beenden")
    args = p.parse_args()

    jahre = (_anzeige_jahre(args.jahre)
             if args.jahre else ausbruch_daten.jahre_vorhanden(args.raster))
    if not jahre:
        print("Kein Kursvorrat vorhanden. Zuerst:")
        print("  python scripts/48_ausbruch_daten.py --nasdaq --shortable "
              "--jahre 2021-2025")
        return 1

    fest: dict = {}
    vorgaben = ausbruch.AusbruchConfig().als_dict()
    for teil in filter(None, args.fest.split(",")):
        k, _, w = teil.partition("=")
        k, w = k.strip(), w.strip()
        if k not in vorgaben:
            print(f"Unbekannte Achse: {k}")
            return 1
        fest[k] = (w.lower() in ("true", "ja", "1")
                   if isinstance(vorgaben[k], bool) else float(w))

    print("=" * 74)
    print("  AUSBRUCH-DAUERLAUF")
    print("=" * 74)
    print(f"  Jahre  : {jahre}")
    print(f"  Raster : {args.raster}")
    print("  Vorrat laden und einmalig ausrichten ...")
    t0 = time.time()
    kd = ausbruch_daten.laden_kursdaten(
        jahre, raster=args.raster, max_symbole=args.symbole,
        fortschritt=lambda a, t: print(f"    {a * 100:5.1f}%  {t}", flush=True))
    print(f"  {len(kd.arrays):,} Symbole, {kd.n_bars:,} Bars, "
          f"{kd.speicher_mb():,.0f} MB, geladen in "
          f"{(time.time() - t0) / 60:.1f} Min")

    lern, pruef, grenze = su.teilen(kd, args.lernanteil)
    print(f"  Lernfenster bis {grenze:%d.%m.%Y}, Prueffenster danach.")
    print("  Suche startet - Strg+C beendet und gibt das Beste aus.")
    time.sleep(1.5)

    suche = su.Suche(lern, pruef, score=args.score, min_trades=args.min_trades,
                     fest=fest, erkundung_n=args.erkundung, saat=args.saat,
                     grenze=grenze)

    lauf_id = ausbruch_store.neuer_lauf(
        {"dauerlauf": True, "score": args.score, "jahre": jahre, "fest": fest,
         "lernanteil": args.lernanteil, "symbole": len(kd.arrays)},
        jahr=jahre[-1], raster=args.raster, n_symbole=len(kd.arrays),
        notiz=f"Dauerlauf {jahre[0]}-{jahre[-1]} ({args.score})")

    signal.signal(signal.SIGINT, _stoppen)
    frist = time.time() + args.stunden * 3600 if args.stunden else None
    breite = shutil.get_terminal_size((110, 40)).columns
    letzte: list = []
    sys.stdout.write("\033[2J\033[H")

    def ende() -> bool:
        return _STOPP or (frist is not None and time.time() > frist)

    letzte_zeichnung = 0.0
    for v in suche.laufen(ende):
        letzte.append(v)
        letzte[:] = letzte[-40:]
        # Bei 12 Versuchen je Sekunde waere Neuzeichnen bei jedem Versuch
        # reine Rechenzeit fuers Auge - dreimal je Sekunde reicht.
        if time.time() - letzte_zeichnung > 0.33 or v.besser:
            _anzeige.anzeigen(suche, letzte, breite)
            letzte_zeichnung = time.time()

    sys.stdout.write("\033[0m\n\n")
    print("=" * 74)
    print("  ERGEBNIS DES DAUERLAUFS")
    print("=" * 74)
    print(suche.bericht())
    if suche.stand.beste_config:
        print("\n  Beste Konfiguration:")
        for k, w in sorted(suche.stand.beste_config.items()):
            print(f"    {k:<32} {w}")
        print("\n  Nachstellen: python scripts/46_ausbruch.py")

    ausbruch_store.abschliessen(lauf_id, {
        "dauerlauf": True, "n_teilversuche": suche.stand.versuche,
        "beste_config": suche.stand.beste_config,
        "lern": suche.stand.beste_kennzahlen,
        "pruef": suche.stand.pruef_kennzahlen,
        "schwelle": suche.stand.schwelle,
    })
    ausbruch_store.suchversuche_buchen(lauf_id, suche.stand.versuche)
    print(f"\n  Lauf {lauf_id}: {suche.stand.versuche:,} Teilversuche gebucht.")
    print(f"  Versuche gesamt: {ausbruch_store.n_versuche():,}  "
          f"(Schwelle t > {ausbruch_store.schwelle_sigma():.2f})")
    return 0


def _anzeige_jahre(text: str) -> list[int]:
    aus: set[int] = set()
    for teil in filter(None, text.split(",")):
        teil = teil.strip()
        if "-" in teil:
            a, _, b = teil.partition("-")
            aus.update(range(int(a), int(b) + 1))
        else:
            aus.add(int(teil))
    return sorted(aus)


if __name__ == "__main__":
    raise SystemExit(main())
