#!/usr/bin/env python3
"""Kalibriert den IC-Kanal: welche Schwelle liefert wirklich 5 % Fehlalarm?

**Warum es dieses Skript gibt (23.08.2026, BEFUNDE §G26).** §G25 hat den
IC zum einzigen Kanal mit Trennschaerfe erklaert - und damit zum
entscheidenden Instrument fuer den 10.10. Geprueft war er nie.

Zwei Details entscheiden ueber Gueltigkeit oder Wertlosigkeit des Tests:

  * `fwd_5d` muss ECHT ueberlappend gebildet werden - Tag t und t+1
    teilen vier ihrer fuenf Renditetage (§G12).
  * Der Score muss PERSISTENT sein. Ein erster Entwurf wuerfelte ihn
    taeglich neu; dann ist der Tages-IC nicht autokorreliert, die Falle
    entsteht gar nicht, und der Test meldete brave 6 %. Ein
    Scheinergebnis.

`PERSISTENZ` ist an den echten Schattendaten GEMESSEN (Median der
Tag-zu-Tag-Rangkorrelation der Scores, 0,49). Aendert sich das Universum
oder die Signalformel, gehoert der Wert nachgemessen - er steuert das
Ergebnis unmittelbar (mit 0,80 statt 0,49 stieg die Fehlalarmquote von
11 % auf 13,2 %).

    python scripts/30_ic_kalibrierung.py 600

Ergebnis vom 23.08.2026, 53 Handelstage:

    Schwelle    roh     korrigiert    Soll
       2,00   18,7 %       11,0 %     5,0 %
       2,85    6,3 %        2,2 %     0,8 %

    fuer echte 5,0 % noetig: |t| > 2,57
    fuer echte 0,8 % noetig: |t| > 3,43
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import numpy as np, pandas as pd
from alpaca_bot import shadow_eval as se

RNG = np.random.default_rng(20260823)
PERSISTENZ = 0.49   # GEMESSEN an den echten Schattendaten (Median der Tag-zu-Tag-Rangkorrelation)

def lauf(T=53, N=130, H=5, signal=0.0, sigma=0.02):
    """Ein Schattenbuch unter der Null (signal=0) oder mit echtem Vorsprung.

    `fwd_5d` wird ECHT ueberlappend gebildet: Tag t und Tag t+1 teilen
    vier ihrer fuenf Renditetage. Genau das ist die Falle aus §G12.
    """
    r = RNG.normal(0.0, sigma, (T + H, N))          # Tagesrenditen

    # Der Score ist PERSISTENT, nicht taeglich neu gewuerfelt. Eine
    # ueberverkaufte Aktie ist morgen meist noch ueberverkauft - real
    # aendert sich die Rangliste langsam. Ein erster Entwurf zog jeden Tag
    # unabhaengig; dann ist der Tages-IC NICHT autokorreliert, die Falle
    # aus §G12 entsteht gar nicht erst, und der Test misst das Falsche.
    score = np.empty((T, N))
    score[0] = RNG.uniform(0, 1, N)
    for t in range(1, T):
        score[t] = PERSISTENZ * score[t-1] + (1-PERSISTENZ) * RNG.uniform(0, 1, N)
    if signal:
        # Der Score hebt die Folgerendite - der einzige Unterschied zur Null
        r[:T] += 0.0                                 # Vergangenheit unberuehrt
        for t in range(T):
            r[t+1:t+1+H] += signal * (score[t] - 0.5)[None, :] / H
    zeilen = []
    for t in range(T):
        fwd = np.prod(1 + r[t+1:t+1+H], axis=0) - 1  # ueberlappendes Fenster
        for i in range(N):
            zeilen.append((f"T{t:03d}", score[t, i], fwd[i]))
    return pd.DataFrame(zeilen, columns=["tag", "score", "fwd_5d"])

def serie(n_laeufe, signal, T=53):
    ts, ics, rohe = [], [], []
    for i in range(n_laeufe):
        k = se.ic(lauf(T=T, signal=signal), "fwd_5d")
        if np.isfinite(k.get("t", np.nan)):
            ts.append(k["t"]); ics.append(k["ic"]); rohe.append(k["t_roh"])
        if (i+1) % 100 == 0: print(f"    {i+1}/{n_laeufe}", flush=True)
    return np.array(ts), np.array(ics), np.array(rohe)

if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 400
    print("=== NULL: Score ohne jede Vorhersagekraft, 53 Tage ===")
    t, i, roh = serie(n, 0.0)
    print(f"\n  {len(t)} auswertbare Laeufe")
    print(f"  IC        : Mittel {i.mean():+.4f}  (Soll 0)")
    print(f"  t korr.   : Mittel {t.mean():+.3f}  Std {t.std(ddof=1):.3f}  (Soll 0 / ~1)")
    print(f"  t roh     : Mittel {roh.mean():+.3f}  Std {roh.std(ddof=1):.3f}")
    print(f"  Aufblaehung des rohen t: {roh.std(ddof=1)/t.std(ddof=1):.2f}x")
    print()
    print(f"  {'Schwelle':>10} {'korrigiert':>12} {'roh':>10} {'Soll':>8}")
    for schw, soll in ((2.0, "5,0 %"), (2.85, "0,8 %")):
        print(f"  {schw:>10.2f} {(np.abs(t)>schw).mean():>11.1%} "
              f"{(np.abs(roh)>schw).mean():>9.1%} {soll:>8}")
