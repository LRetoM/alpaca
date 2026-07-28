#!/usr/bin/env python3
"""Schritt 6: Haetten wir den Ausbruch VORHER erkennen koennen?

Der Test, um den es dir geht. Ablauf:

  1. Alle explosiven Bewegungen der Historie finden
  2. Fuer jede: NUR die Daten vor dem Ausbruch nehmen (mit Sperrzone)
  3. Kontrollgruppe ziehen - Faelle, in denen nichts passiert ist
  4. Unterscheiden sich beide Gruppen ueberhaupt?
  5. Kann ein Modell sie out-of-sample trennen?
  6. NEGATIVTESTS: findet das System auch dort etwas, wo nichts ist?

Punkt 6 ist der wichtigste. Ein System, das auf gemischten Labels ein
Signal findet, findet auch auf echten Daten keines - es erfindet nur eines.

    python scripts/06_event_study.py
    python scripts/06_event_study.py --universe mega_cap --years 8 --threshold 0.4
"""

from __future__ import annotations

import argparse
import sys

import numpy as np
import pandas as pd

from alpaca_bot import compliance, data, events, features, ml, pit, universe
from alpaca_bot.config import RESULTS_DIR
from alpaca_bot.journal import Journal


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--universe", default="mega_cap",
                   choices=list(universe.BENCHMARK_SETS) + ["custom"])
    p.add_argument("--symbols", nargs="*", default=None)
    p.add_argument("--years", type=float, default=9.0)
    p.add_argument("--threshold", type=float, default=0.50,
                   help="Was gilt als Explosion? 0.50 = +50 %%")
    p.add_argument("--window", type=int, default=60, help="...in wie vielen Tagen")
    p.add_argument("--lookback", type=int, default=120)
    p.add_argument("--blackout", type=int, default=5)
    p.add_argument("--controls", type=int, default=20, help="Kontrollen je Ereignis")
    p.add_argument("--skip-preflight", action="store_true")
    args = p.parse_args()

    symbols = args.symbols or universe.BENCHMARK_SETS[args.universe]
    cfg = events.EventConfig(
        threshold=args.threshold, window=args.window,
        lookback=args.lookback, blackout=args.blackout,
    )

    journal = Journal()
    with journal.run("06_event_study", config=vars(args)) as run:
        # --- 0. Budget pruefen, bevor irgendetwas geladen wird ---
        if not args.skip_preflight:
            print(compliance.preflight(len(symbols), args.years, "1D"))
            print()

        # --- 1. Daten ---
        print(f"[1/7] Lade {len(symbols)} Symbole, {args.years:g} Jahre ...")
        bars = data.get_bars(symbols, "1D", lookback_days=int(args.years * 365))
        if bars.empty:
            print("Keine Daten erhalten.")
            return 1
        n_sym = bars.index.get_level_values("symbol").nunique()
        print(f"      {len(bars):,} Bars fuer {n_sym} Symbole")
        run.log("daten_geladen", symbole=n_sym, bars=len(bars))
        print()
        print(universe.survivorship_warning(n_sym, args.years,
                                            "large_cap" if "mega" in args.universe else "small_cap"))

        # --- 2. Feature-Funktion pruefen, BEVOR sie benutzt wird ---
        print(f"\n[2/7] Pruefe die Feature-Funktion auf Zukunftslecks ...")
        probe = data.ohlcv(bars, symbols[0])
        audit = pit.audit_feature_function(features.build_features, probe)
        print(f"      {audit}")
        run.log("pit_audit", sauber=audit.clean, lecks=list(audit.leaking_columns))
        if not audit.clean:
            print("\n  ABBRUCH: Undichte Features. Alles Weitere waere wertlos.")
            return 1

        # --- 3. Ereignisse ---
        print(f"\n[3/7] Suche Bewegungen ueber +{args.threshold:.0%} "
              f"in {args.window} Tagen ...")
        ev = events.find_events(bars, cfg)
        if ev.empty:
            print("      Keine Ereignisse gefunden. Schwelle senken oder mehr Symbole.")
            return 1
        print(f"      {len(ev)} Ereignisse gefunden")
        print(f"      Mediane Rendite: {ev['return'].median():.1%} | "
              f"Median Tage bis Hoch: {ev['days_to_peak'].median():.0f}")
        print(f"      Median Zwischenrueckschlag: "
              f"{ev['max_drawdown_before_peak'].median():.1%}")
        print("\n      Groesste Bewegungen:")
        print(ev.nlargest(8, "return")[
            ["symbol", "t0", "return", "days_to_peak", "max_drawdown_before_peak"]
        ].to_string(index=False))
        run.snapshot("ereignisse", ev)

        # --- 4. Kontrollgruppe ---
        print(f"\n[4/7] Ziehe Kontrollgruppe ({args.controls} je Ereignis) ...")
        ctrl = events.sample_controls(bars, ev, cfg, n_per_event=args.controls)
        print(f"      {len(ctrl)} Kontrollfaelle")
        if ctrl.empty:
            print("      Zu wenige Kontrollen - Universum vergroessern.")
            return 1

        # --- 5. Unterscheiden sich die Gruppen? ---
        print(f"\n[5/7] Baue Merkmale aus den VORFENSTERN "
              f"(t0-{args.lookback} bis t0-{args.blackout}) ...")
        X, y, meta = events.build_dataset(bars, ev, ctrl, features.build_features, cfg)
        if X.empty:
            print("      Keine verwertbaren Vorfenster.")
            return 1
        print(f"      {len(X)} Faelle x {X.shape[1]} Merkmale "
              f"({int(y.sum())} Explosionen, {int((y == 0).sum())} Kontrollen)")

        diff = events.compare_groups(X, y)
        print("\n      Groesste Unterschiede Explosion vs. Kontrolle:")
        print(diff.to_string(index=False))
        print("\n      |Cohens d| < 0.2 = praktisch bedeutungslos, 0.2-0.5 = klein,")
        print("      > 0.5 = deutlich. Bei Finanzdaten ist alles ueber 0.3 bemerkenswert.")
        run.snapshot("gruppenvergleich", diff)

        # --- 6. Kann ein Modell trennen? ---
        print(f"\n[6/7] Walk-Forward-Modell auf den Vorfenstern ...")
        order = meta.sort_values("t0").index
        Xs, ys = X.loc[order].reset_index(drop=True), y.loc[order].reset_index(drop=True)
        base_rate = float(ys.mean())

        try:
            wf = ml.walk_forward_predict(
                Xs, ys, "gbm", n_splits=4, embargo=0,
                min_train=max(100, int(len(Xs) * 0.4)),
            )
            print(wf.fold_scores.to_string(index=False))
            print()
            print(wf.summary())
            ic = pit.information_coefficient(
                wf.predictions, ys.loc[wf.predictions.index].astype(float)
            )
            print(f"  Information Coefficient: {ic:.4f}")
            run.log("modell", accuracy=wf.accuracy, auc=wf.auc, ic=ic,
                    basisrate=base_rate)
        except ValueError as e:
            print(f"      Zu wenig Daten: {e}")
            return 1

        # --- 7. Negativtests ---
        print(f"\n[7/7] NEGATIVTESTS - hier MUSS das System scheitern:")

        def fit_predict(Xf, yf):
            r = ml.walk_forward_predict(Xf, yf, "gbm", n_splits=3, embargo=0,
                                        min_train=max(80, int(len(Xf) * 0.5)))
            return r.predictions

        shuffled = pit.shuffle_test(Xs, ys, fit_predict, n_rounds=5)
        ok_shuffle = shuffled["passed"]
        print(f"      Gemischte Labels -> mittlerer IC {shuffled['mean_ic']:+.4f} "
              f"(Rauschgrenze +/-{shuffled['threshold']:.4f})   "
              f"{'BESTANDEN' if ok_shuffle else 'DURCHGEFALLEN - Leck!'}")

        # Trefferquote der obersten Raenge - die einzige entscheidungsrelevante
        # Groesse. "Wenn wir die 20 aussichtsreichsten kaufen, wie viele
        # explodieren?" gegen die Basisrate.
        preds = wf.predictions.sort_values(ascending=False)
        topk = min(20, max(5, len(preds) // 20))
        hits = float(ys.loc[preds.head(topk).index].mean())
        lift = hits / base_rate if base_rate > 0 else float("nan")
        print(f"      Top-{topk}-Trefferquote: {hits:.1%} gegen Basisrate "
              f"{base_rate:.1%}  (Faktor {lift:.2f})")

        n_needed = pit.required_sample_size(
            max(0.01, hits - base_rate), base_rate=base_rate
        )
        genug = len(Xs) >= n_needed
        print(f"      Stichprobe: {len(Xs)} Faelle, noetig fuer diesen "
              f"Effekt: {n_needed:,}   {'ausreichend' if genug else 'ZU KLEIN'}")

        # --- Urteil ---
        print("\n" + "=" * 70)
        print("  URTEIL")
        print("=" * 70)
        print(f"  Basisrate (Anteil Explosionen) : {base_rate:>8.1%}")
        print(f"  AUC (0.5 = Zufall)             : {wf.auc:>8.3f}   <- massgeblich")
        print(f"  Top-{topk}-Trefferquote          : {hits:>8.1%}")
        print(f"  Lift gegenueber Zufall         : {lift:>8.2f}x")
        print()
        print(f"  Hinweis: Accuracy ({wf.accuracy:.1%}) ist hier BEDEUTUNGSLOS.")
        print(f"  Bei {base_rate:.1%} Basisrate erreicht 'immer nein' schon "
              f"{1 - base_rate:.1%}.")
        print()

        if not ok_shuffle:
            print("  UNGUELTIG: Das System findet auch auf gemischten Labels ein")
            print("  Signal. Irgendwo steckt ein Leck - Ergebnis wertlos, bis")
            print("  die Pipeline repariert ist.")
        elif wf.auc < 0.55 or lift < 1.5:
            print("  ERGEBNIS: Kein verwertbares Vorwissen in diesen Merkmalen.")
            print("  Die Vorfenster von Explosionen sehen aus wie alle anderen.")
            print()
            print("  Das ist der erwartete Ausgang bei reinen Kursmerkmalen und")
            print("  KEIN Fehler. Nutzbares Vorwissen steckt eher in Daten, die")
            print("  hier noch fehlen:")
            print("    - Insiderkaeufe (SEC Form 4, kostenlos, PIT-perfekt)")
            print("    - News-Frequenz-Anomalien (news.py, ab 2015 verfuegbar)")
            print("    - Gewinnueberraschungen und Analystenrevisionen")
            print("    - Nettoemission von Aktien")
        elif not genug:
            print("  ERGEBNIS: Vorsprung sichtbar, Stichprobe aber zu klein.")
            print(f"  Fuer Belastbarkeit fehlen Faelle: {n_needed - len(Xs):,}.")
            print("  Universum vergroessern oder Zeitraum verlaengern.")
        else:
            print("  ERGEBNIS: Statistisch belastbarer Vorsprung.")
            print("  Naechster Schritt: in eine handelbare Strategie uebersetzen")
            print("  und mit Kosten (costs.py) gegenrechnen - erst dann zeigt")
            print("  sich, ob der Vorsprung die Gebuehren ueberlebt.")

        out = RESULTS_DIR / "event_study"
        out.mkdir(exist_ok=True)
        ev.to_csv(out / "ereignisse.csv", index=False)
        diff.to_csv(out / "gruppenvergleich.csv", index=False)
        print(f"\n  Ergebnisse gespeichert: {out}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
