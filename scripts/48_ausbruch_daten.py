#!/usr/bin/env python3
"""Schritt 48: Kursvorrat fuer die Ausbruch-Werkstatt aufbauen.

    python scripts/48_ausbruch_daten.py --nasdaq --jahre 2021-2025
    python scripts/48_ausbruch_daten.py --nasdaq --shortable --jahre 2023-2025
    python scripts/48_ausbruch_daten.py --symbole 1500 --jahre 2024,2025
    python scripts/48_ausbruch_daten.py --stand

Laedt 15-Minuten-Bars und legt sie als Parquet ab. **Fortsetzbar:**
Bereits vorhandene Symbole werden uebersprungen, ein Abbruch kostet
nichts. Ein zweiter Aufruf macht dort weiter, wo der erste aufhoerte.

**Rechne mit Stunden, nicht Minuten.** Gemessen am 11.09.2026:
rund 590 Symbole x 1 Jahr in 25 Minuten. Daraus folgt grob

    Stunden  =  Symbole / 590  x  Jahre  x  0,42

| Auswahl | Symbole | Jahre | Download | Platte | Speicher im Lauf |
|---|---:|---:|---:|---:|---:|
| Top 600 (schon da)  |   598 | 1 | fertig | 86 MB | 0,1 GB |
| NASDAQ shortable    | 2.171 | 3 |  ~4,6 h | 0,9 GB | 1,0 GB |
| NASDAQ shortable    | 2.171 | 5 |  ~7,7 h | 1,6 GB | 1,7 GB |
| NASDAQ vollstaendig | 5.568 | 2 |  ~7,9 h | 1,6 GB | 1,7 GB |
| NASDAQ vollstaendig | 5.568 | 5 | ~19,8 h | 4,1 GB | 4,2 GB |

**Empfehlung: `--nasdaq --shortable --jahre 2021-2025`.** Fuenf Jahre
decken einen Baerenmarkt (2022) mit ab - und genau das fehlt einem Lauf
ueber 2025 allein, denn Ausbruch-Strategien funktionieren in steigenden
Maerkten fast immer und brechen in Wenden zusammen. Die
Shortable-Liste ist zugleich ein grober Liquiditaetsfilter: Werte, die
Alpaca nicht leerverkaufen laesst, sind meist auch nicht sinnvoll
kaufbar.

**Warum die volle Liste NICHT besser ist.** Von 5.568 NASDAQ-Werten hat
die Mehrheit kaum Umsatz. Dort ist die Kostenannahme von 12,2 bps
(§G54, gemessen am liquiden Universum) nicht optimistisch, sondern
falsch - 200 bps und mehr sind normal. Mehr Symbole machen den Backtest
also **besser aussehend, nicht ehrlicher**. Wer sie trotzdem will,
bekommt sie mit `--nasdaq` ohne `--shortable` - und sollte dann
`min_dollar_volumen` hoch setzen.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from alpaca_bot import ausbruch_daten, universe  # noqa: E402


def _jahre(text: str) -> list[int]:
    """'2021-2025' oder '2024,2025' oder '2025'."""
    aus: set[int] = set()
    for teil in filter(None, text.split(",")):
        teil = teil.strip()
        if "-" in teil:
            a, _, b = teil.partition("-")
            aus.update(range(int(a), int(b) + 1))
        else:
            aus.add(int(teil))
    return sorted(aus)


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--jahre", default="2025", help="z.B. 2021-2025")
    p.add_argument("--raster", default="15Min")
    p.add_argument("--nasdaq", action="store_true",
                   help="alle an der NASDAQ handelbaren Symbole")
    p.add_argument("--shortable", action="store_true",
                   help="nur leerverkaufbare - grober Liquiditaetsfilter")
    p.add_argument("--symbole", type=int, default=None,
                   help="ohne --nasdaq: die N umsatzstaerksten aus dem "
                        "gemessenen Universum")
    p.add_argument("--stand", action="store_true", help="nur nachsehen")
    args = p.parse_args()

    if args.stand:
        print("=" * 70)
        print("  KURSVORRAT")
        print("=" * 70)
        jahre = ausbruch_daten.jahre_vorhanden(args.raster)
        if not jahre:
            print(f"  Nichts vorhanden fuer {args.raster}.")
            return 0
        gesamt = 0.0
        for j in jahre:
            b = ausbruch_daten.bestand(args.raster, j)
            gesamt += b["mb"]
            print(f"  {j}: {b['symbole']:>5} Symbole, {b['mb']:>8,.0f} MB")
        print(f"  {'':>4}  {'':>5}        {gesamt:>8,.0f} MB gesamt")
        print(f"\n  Ordner: {ausbruch_daten.VORRAT}")
        return 0

    jahre = _jahre(args.jahre)
    if args.nasdaq:
        syms = universe.nasdaq_universum(nur_shortable=args.shortable)
        quelle = f"NASDAQ{' shortable' if args.shortable else ' vollstaendig'}"
    else:
        syms = universe.load_universe(max_symbols=args.symbole)
        quelle = f"gemessenes Universum, Top {len(syms)}"

    geschaetzt = len(syms) / 590 * len(jahre) * 0.42
    print("=" * 70)
    print("  KURSVORRAT AUFBAUEN")
    print("=" * 70)
    print(f"  Quelle    : {quelle}")
    print(f"  Symbole   : {len(syms):,}")
    print(f"  Jahre     : {jahre}")
    print(f"  Raster    : {args.raster}")
    print(f"  Geschaetzt: ~{geschaetzt:.1f} Stunden, "
          f"~{len(syms) * len(jahre) * 0.145:,.0f} MB")
    print()
    print("  Fortsetzbar - Strg+C kostet nichts, ein zweiter Aufruf")
    print("  macht dort weiter, wo dieser aufhoert.")
    print("=" * 70)

    t0 = time.time()
    for n, jahr in enumerate(jahre, 1):
        print(f"\n[{n}/{len(jahre)}] Jahr {jahr}")
        try:
            ausbruch_daten.vorrat_aufbauen(
                syms, jahr=jahr, raster=args.raster,
                fortschritt=lambda a, t, j=jahr: print(
                    f"    {a * 100:5.1f}%  {t}", flush=True),
            )
        except KeyboardInterrupt:
            print(f"\n  Abgebrochen. Bisher Geladenes bleibt erhalten -")
            print(f"  derselbe Aufruf macht dort weiter.")
            return 130

    print(f"\n  Fertig in {(time.time() - t0) / 3600:.1f} Stunden.")
    for j in jahre:
        b = ausbruch_daten.bestand(args.raster, j)
        print(f"    {j}: {b['symbole']:>5} Symbole, {b['mb']:>8,.0f} MB")
    print(f"\n  Weiter mit:  python scripts/49_ausbruch_dauerlauf.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
