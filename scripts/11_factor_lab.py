#!/usr/bin/env python3
"""Schritt 11: Faktor-Labor - messen, BEVOR gebaut wird.

Der vorige Anlauf hat eine Strategie aus plausibel klingenden Faktoren
gebaut und erst danach gemessen. Ergebnis: IC von -0.05, die Faktoren
rangierten in die falsche Richtung, 127 Prozentpunkte hinter Buy & Hold.

Dieses Skript dreht die Reihenfolge um:

  1. Handelbares Universum bei Alpaca bestimmen (was koennen wir kaufen?)
  2. Tiefe Historie ueber FREIE Quellen laden (schont das Alpaca-Kontingent)
  3. ~30 Kandidaten-Faktoren ueber 4 Horizonte messen
  4. Rangliste nach Stabilitaet (t-Wert), nicht nach Erwartung

Erst was hier besteht, darf in die Strategie.

    python scripts/11_factor_lab.py
    python scripts/11_factor_lab.py --max-symbols 3000 --years 8
"""

from __future__ import annotations

import argparse
import sys

import pandas as pd

from alpaca_bot import datasources, research, universe
from alpaca_bot.config import RESULTS_DIR


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--years", type=float, default=8.0)
    p.add_argument("--min-price", type=float, default=3.0)
    p.add_argument("--min-volume", type=float, default=1_000_000)
    p.add_argument("--max-symbols", type=int, default=2500,
                   help="Obergrenze nach Liquiditaet (Speicher und Laufzeit)")
    p.add_argument("--source", default="yfinance", choices=["yfinance", "stooq", "alpaca"])
    p.add_argument("--horizons", nargs="+", type=int, default=[3, 5, 10, 20])
    p.add_argument("--rebuild", action="store_true", help="Cache ignorieren")
    args = p.parse_args()

    out_dir = RESULTS_DIR / "factor_lab"
    out_dir.mkdir(parents=True, exist_ok=True)
    universe_file = out_dir / "universum.csv"

    # --- 1. Universum ---
    print("=" * 78)
    print("  SCHRITT 1: HANDELBARES UNIVERSUM")
    print("=" * 78)
    print("  Alpaca wird hier nur fuer zwei Dinge genutzt: die Liste der")
    print("  handelbaren Symbole und ein kurzes Liquiditaetsfenster.")
    print("  Das kostet unter 100 Requests. Die tiefe Historie kommt danach")
    print(f"  aus einer freien Quelle ({args.source}).\n")

    if universe_file.exists() and not args.rebuild:
        uni = pd.read_csv(universe_file)
        print(f"      aus Cache: {len(uni):,} Symbole")
    else:
        uni = universe.build_universe(
            min_price=args.min_price,
            min_dollar_volume=args.min_volume,
            probe_days=90,
        )
        uni.to_csv(universe_file, index=False)

    if uni.empty:
        print("  Kein Universum aufgebaut.")
        return 1

    uni = uni.head(args.max_symbols)
    symbols = uni["symbol"].tolist()
    print(f"\n      Verwendet: {len(symbols):,} Symbole")
    print(f"      Kurs      : ${uni['price'].min():.2f} bis ${uni['price'].max():,.2f} "
          f"(Median ${uni['price'].median():.2f})")
    print(f"      Tagesumsatz Median: ${uni['dollar_volume'].median():,.0f}")

    print()
    print(universe.survivorship_warning(len(symbols), args.years, "small_cap"))

    # --- 2. Historie ---
    print("\n" + "=" * 78)
    print(f"  SCHRITT 2: HISTORIE ({args.years:g} Jahre, Quelle: {args.source})")
    print("=" * 78)
    bars = datasources.get_history(
        symbols, years=args.years, source=args.source, use_cache=not args.rebuild
    )
    if bars.empty:
        print("  Keine Daten erhalten.")
        return 1
    n_sym = bars.index.get_level_values("symbol").nunique()
    days = bars.index.get_level_values("timestamp")
    print(f"\n      {len(bars):,} Bars | {n_sym:,} Symbole | "
          f"{days.min().date()} bis {days.max().date()}")

    # --- 3. Faktoren messen ---
    print("\n" + "=" * 78)
    print("  SCHRITT 3: FAKTOREN MESSEN")
    print("=" * 78)
    # `mit_panels`: `select_factors` braucht die Faktorwerte fuer den
    # Korrelationsfilter. Ohne sie waehlt es die Top-N nach t-Wert und
    # meldet, dass nicht gefiltert wurde (§G16) - fuenf korrelierte
    # Faktoren sind aber nicht fuenfmal so viel Signal (BEFUNDE §A).
    results, panels = research.measure_factors(
        bars, horizons=tuple(args.horizons), mit_panels=True)
    if results.empty:
        print("  Keine auswertbaren Ergebnisse.")
        return 1

    print()
    print(research.summarize(results, top=30))

    # --- 4. Auswahl ---
    print("\n" + "=" * 78)
    print("  SCHRITT 4: WAS DARF IN DIE STRATEGIE?")
    print("=" * 78)
    # `t_korr` und NICHT `t_stat`: `select_factors` prueft seit §G12 den
    # korrigierten Wert, die Anzeige daneben tat es bis zum 22.08.2026
    # nicht. Zwei verschiedene Schwellen in derselben Ausgabe - und die
    # laxere stand in der Zeile, die man zitiert.
    t_korr = (results["t_korrigiert"].fillna(results["t_stat"])
              if "t_korrigiert" in results else results["t_stat"])
    results = results.assign(_t=t_korr)

    for h in args.horizons:
        chosen = research.select_factors(results, horizon=h, min_t=3.0,
                                         factor_data=panels)
        sub = results[(results["horizon"] == h) & (results["_t"] >= 3.0)]
        inverted = sub[sub["ic_mean"] < 0]["factor"].tolist()
        print(f"\n  Horizont {h} Tage:")
        print(f"    tragfaehig  : {', '.join(chosen) if chosen else '(keiner)'}")
        if inverted:
            print(f"    invertiert  : {', '.join(inverted[:6])}")
            print(f"                  (stabil, aber falsches Vorzeichen - NICHT")
            print(f"                   einfach umdrehen, das waere Data-Mining)")

    results.drop(columns=["_t"]).to_csv(out_dir / "faktoren.csv", index=False)
    print(f"\n  Gespeichert: {out_dir / 'faktoren.csv'}")

    # --- 5. Vorzeichenstabilitaet je Jahr ---
    #
    # **Das eigentlich tragende Kriterium.** §G12 hat gezeigt, dass der
    # t-Wert bei ueberlappenden Fenstern im Mittel um 1,62 zu hoch
    # ausfaellt - zwei der in `signals.ReversalWeights` dokumentierten
    # Bausteine (`rsi2`, `reversal_3d`) halten die heutige Schwelle danach
    # nicht mehr. Was den Befund dennoch traegt, benennt §G12 ausdruecklich:
    #
    #     "`ReversalWeights` nennt als Kriterium ausdruecklich die
    #      Vorzeichenstabilitaet je Jahr ('100 % positive Jahre') - ein
    #      anderes und robusteres Kriterium als der t-Wert, das von dieser
    #      Korrektur unberuehrt bleibt."
    #
    # `research.measure_stability` misst genau das - und wurde bis zum
    # 22.08.2026 von KEINEM Skript aufgerufen (§G16). Das Kriterium, auf
    # dem die Strategie steht, war damit aus dem laufenden Werkzeug heraus
    # nicht reproduzierbar: Die "100 % positive Jahre" stammten aus einem
    # Messlauf, den niemand wiederholen konnte, ohne die Funktion von Hand
    # zu rufen. Genau die Fehlerklasse aus §G15 - gebaut, laeuft nie.
    kern = sorted({f for h in args.horizons
                   for f in research.select_factors(results, horizon=h,
                                                    min_t=3.0,
                                                    factor_data=panels)})
    if kern:
        print("\n" + "=" * 78)
        print("  SCHRITT 5: HAELT DAS VORZEICHEN UEBER DIE JAHRE?")
        print("=" * 78)
        stab = research.measure_stability(bars, kern,
                                          horizon=max(args.horizons))
        if stab.empty:
            print("  Zu wenig Historie fuer eine Jahresaufteilung.")
        else:
            print()
            print(research.stability_report(stab))
            stab.to_csv(out_dir / "stabilitaet.csv", index=False)
            print(f"\n  Gespeichert: {out_dir / 'stabilitaet.csv'}")
    else:
        print("\n  Keine tragfaehigen Faktoren - Stabilitaetspruefung entfaellt.")

    best = results[results["ic_mean"] > 0].nlargest(1, "_t")
    if not best.empty:
        b = best.iloc[0]
        print(f"\n  Staerkster positiver Faktor: {b['factor']} auf {int(b['horizon'])} Tage")
        print(f"    IC {b['ic_mean']:+.4f} | t korr. {b['_t']:+.1f} "
              f"(roh {b['t_stat']:+.1f}) | Q5-Q1 {b['q5_minus_q1']:+.3%}")
    else:
        print("\n  KEIN Faktor mit positivem IC und ausreichender Stabilitaet.")
        print("  Dann traegt keine Strategie aus diesen Bausteinen.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
