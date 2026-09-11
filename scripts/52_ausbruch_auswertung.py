#!/usr/bin/env python3
"""Schritt 52: Was haben die Instanzen gelernt? Auswertung aller Versuche.

    python scripts/52_ausbruch_auswertung.py
    python scripts/52_ausbruch_auswertung.py --top 30
    python scripts/52_ausbruch_auswertung.py --csv ergebnisse.csv

Fuehrt die Protokolle ALLER Instanzen zusammen und beantwortet drei
Fragen - in aufsteigender Wichtigkeit:

1. **Welche Konfiguration gewann?** Interessant, aber am wenigsten
   belastbar: Der Beste aus einer Million Versuchen ist per
   Konstruktion ein Ausreisser (§B2).

2. **Traegt irgendetwas ins Prueffenster?** Die Entscheidungsfrage.
   Maassgeblich ist die PRUEFSCHWELLE (`sqrt(2 ln Pruefungen)`), nicht
   die Lernschwelle - die Auswahl fand nur im Lernfenster statt.

3. **Welche Achsenwerte schneiden systematisch besser ab?** Die
   eigentliche Erkenntnis. Ueber hunderttausende Versuche gemittelt ist
   "anstieg_pct = 10 liegt im Schnitt 0,4 t-Punkte ueber anstieg_pct =
   30" eine belastbare Aussage - der einzelne Gewinner ist es nicht.

Der Zusammenhang zwischen Lern- und Pruefwert wird aus der
**Zufallsstichprobe** gerechnet (siehe `--pruef-stichprobe` in Skript
50), nicht aus den Gewinnern: Die Gewinner sind eine bewusst schiefe
Auswahl und wuerden den Zusammenhang systematisch falsch darstellen.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from alpaca_bot import ausbruch_versuche as av  # noqa: E402
from alpaca_bot import ausbruch_suche as su  # noqa: E402


def _kopf(text: str) -> None:
    print()
    print("=" * 78)
    print(f"  {text}")
    print("=" * 78)


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--top", type=int, default=15)
    p.add_argument("--min-trades", type=int, default=60)
    p.add_argument("--csv", default=None, help="alles als CSV ausgeben")
    args = p.parse_args()

    df = av.zusammenfuehren()
    if df.empty:
        print("Kein Versuchsprotokoll gefunden.")
        print("Laeuft der Dienst? -> python scripts/51_ausbruch_status.py")
        return 1

    if args.csv:
        df.to_csv(args.csv, index=False)
        print(f"{len(df):,} Zeilen nach {args.csv} geschrieben.")

    achsen = [c for c in df.columns if c.startswith("k_")]
    n_pruef = int(df["t_pruef"].notna().sum())
    pruef_schwelle = max(2.0, math.sqrt(2.0 * math.log(max(n_pruef, 2))))
    lern_schwelle = max(2.0, math.sqrt(2.0 * math.log(max(len(df), 2))))

    # ---------------------------------------------------------------
    _kopf("GRUNDLAGE")
    print(f"  Versuche gesamt        : {len(df):,}")
    for inst, teil in df.groupby("instanz"):
        print(f"      Instanz [{inst}]        : {len(teil):,}")
    print(f"  davon mit Pruefwert    : {n_pruef:,}")
    print(f"      als neuer Bester   : {int((df['pruef_grund'] == 'bester').sum()):,}")
    print(f"      als Stichprobe     : {int((df['pruef_grund'] == 'stichprobe').sum()):,}")
    print()
    print(f"  Lernschwelle  (Auswahl ueber {len(df):,} Versuche) : "
          f"t > {lern_schwelle:.2f}")
    print(f"  Pruefschwelle ({n_pruef:,} Pruefungen)              : "
          f"t > {pruef_schwelle:.2f}   <- massgeblich")

    # ---------------------------------------------------------------
    _kopf("2. TRAEGT ETWAS INS PRUEFFENSTER? (die Entscheidungsfrage)")
    mit_pruef = df[df["t_pruef"].notna()].copy()
    if mit_pruef.empty:
        print("  Noch keine Pruefbewertung - zu frueh fuer ein Urteil.")
    else:
        mit_pruef["abstand"] = mit_pruef["t_lern"] - mit_pruef["t_pruef"]
        best = mit_pruef.sort_values("t_pruef", ascending=False).head(args.top)
        print(f"  {'t_pruef':>8}{'t_lern':>8}{'Abstand':>9}{'Rend_pr':>9}"
              f"{'Trades':>8}  {'Grund':<11}{'Inst':>5}")
        for _, r in best.iterrows():
            print(f"  {r['t_pruef']:>8.2f}{r['t_lern']:>8.2f}"
                  f"{r['abstand']:>+9.2f}{(r['rendite_pruef'] or 0):>8.1f}%"
                  f"{int(r['n_trades']):>8}  {str(r['pruef_grund']):<11}"
                  f"{r['instanz']:>5}")

        spitze = float(best["t_pruef"].iloc[0])
        print()
        if spitze >= pruef_schwelle:
            print(f"  URTEIL: Der beste Pruefwert {spitze:.2f} liegt UEBER "
                  f"der Schwelle {pruef_schwelle:.2f}.")
            print("  Naechster Schritt ist NICHT live, sondern das Gate aus")
            print("  docs/AUSBRUCH.md §6: 30 bps Spanne, beide Jahreshaelften,")
            print("  nicht von fuenf Symbolen getragen. Dann Flottenbot.")
        else:
            print(f"  URTEIL: KEIN BEFUND. Bester Pruefwert {spitze:.2f} "
                  f"gegen Schwelle {pruef_schwelle:.2f}.")

    # ---------------------------------------------------------------
    _kopf("3. WELCHE ACHSENWERTE TRAGEN? (die eigentliche Erkenntnis)")
    brauchbar = df[(df["score"].notna()) & (df["n_trades"] >= args.min_trades)]
    print(f"  Grundlage: {len(brauchbar):,} Versuche mit mindestens "
          f"{args.min_trades} Trades.")
    print(f"  Gelesen wird die Spalte 'Delta': mittlerer Lern-t-Wert dieses")
    print(f"  Achsenwerts minus Gesamtmittel. Positiv = traegt.")
    if brauchbar.empty:
        print("  Zu wenige verwertbare Versuche.")
    else:
        mittel = brauchbar["t_lern"].mean()
        for achse in achsen:
            g = brauchbar.groupby(achse)["t_lern"].agg(["mean", "size"])
            g = g[g["size"] >= 30]
            if len(g) < 2:
                continue
            g["delta"] = g["mean"] - mittel
            g = g.sort_values("delta", ascending=False)
            name = achse[2:]
            print(f"\n  {name}")
            for wert, r in g.iterrows():
                balken = "#" * min(int(abs(r["delta"]) * 12), 28)
                zeichen = "+" if r["delta"] >= 0 else "-"
                print(f"      {str(wert):>12}  {r['delta']:>+7.3f}  "
                      f"n={int(r['size']):>7}  {zeichen}{balken}")

    # ---------------------------------------------------------------
    _kopf("ZUSAMMENHANG LERN- GEGEN PRUEFWERT (aus der Stichprobe)")
    stich = df[(df["pruef_grund"] == "stichprobe") & df["t_pruef"].notna()]
    if len(stich) < 30:
        print(f"  Erst {len(stich)} Stichproben - fuer eine Aussage zu wenig.")
        print("  (Sammelt sich mit der Laufzeit von selbst an.)")
    else:
        r = float(np.corrcoef(stich["t_lern"], stich["t_pruef"])[0, 1])
        print(f"  {len(stich):,} unverzerrte Stichproben.")
        print(f"  Korrelation Lern gegen Pruef: {r:+.3f}")
        print()
        if r < 0.05:
            print("  Ein guter Lernwert sagt NICHTS ueber das Prueffenster.")
            print("  Das ist der Befund: In dieser Strategiefamilie ist das,")
            print("  was die Suche findet, reine Anpassung an den Zeitraum.")
        elif r < 0.3:
            print("  Schwacher Zusammenhang - ein guter Lernwert erhoeht die")
            print("  Chance auf einen guten Pruefwert, garantiert sie nicht.")
        else:
            print("  Deutlicher Zusammenhang - die Suche findet etwas, das")
            print("  ueber den Lernzeitraum hinaus traegt.")

    # ---------------------------------------------------------------
    _kopf("1. BESTE KONFIGURATION IM LERNFENSTER (am wenigsten belastbar)")
    e = su.elite_lesen()
    if e:
        print(f"  Gemeinsamer Bestwert: score {e.get('score', 0):.3f} "
              f"(Instanz [{e.get('instanz')}], {e.get('gesetzt_am', '?')[:19]})")
        for k, w in sorted((e.get("config") or {}).items()):
            print(f"      {k:<32} {w}")
    print()
    print("  In der Werkstatt nachstellen: python scripts/46_ausbruch.py")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
