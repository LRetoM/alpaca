#!/usr/bin/env python3
"""Schritt 19: Neue Faktoren auf der Historie pruefen - ohne den Bot zu stoeren.

Der billige Filter aus `hypotheses.py`: Was auf mehreren Jahren keinen
Querschnitts-IC mit |t| > 2 zeigt, bindet keine Vorwaertszeit im
Schattenbetrieb.

**Beruehrt den laufenden Handel nicht.** Kursdaten und Meldetermine kommen
ausschliesslich von yfinance (eigene Drossel: 60/min, 2000/Tag), nicht von
Alpaca. Das Handelskontingent des Bots (200/min) bleibt unangetastet -
deshalb kann dieses Skript waehrend der Boersenzeit laufen.

    python scripts/19_faktor_tests.py                 # voller Lauf
    python scripts/19_faktor_tests.py --max-symbols 200   # schneller Probelauf
    python scripts/19_faktor_tests.py --nur-bericht   # nur Register anzeigen

Was geprueft wird:

    pead_ueberraschung   Surprise(%) der Gewinnmeldung
    pead_reaktion        marktbereinigte Kursreaktion am Meldetag

Beide gegen Vorwaertsrenditen ueber 5/10/20/40 Handelstage, gemessen ab
dem Schlusskurs des Reaktionstages - die Sprungbewegung der Meldung selbst
ist ausgeschlossen.
"""

from __future__ import annotations

import argparse
import sys

import numpy as np
import pandas as pd

from alpaca_bot import datasources, earnings, hypotheses, universe

HORIZONTE = (5, 10, 20, 40)

HYPOTHESEN = [
    dict(
        hyp_id="H01_pead_ueberraschung",
        behauptung=(
            "Nach einer positiven Gewinnueberraschung laeuft der Kurs ueber "
            "Wochen weiter nach oben, nach einer negativen weiter nach unten - "
            "der Markt preist die Information nicht sofort vollstaendig ein."
        ),
        quelle="Bernard & Thomas (1989), Journal of Accounting Research",
        quelle_typ="akademisch_repliziert",
        veroeffentlicht="1989-01-01",
        behaupteter_effekt="Drift ueber 60 Handelstage in Richtung der Ueberraschung",
        operationalisierung=(
            "Faktor = Surprise(%) der letzten Meldung, aktiv fuer 60 Handelstage "
            "ab dem Reaktionstag. Reaktionstag = Meldetag, wenn vor 16:00 ET "
            "gemeldet, sonst der Folgehandelstag. Ziel = Vorwaertsrendite ab "
            "SCHLUSSKURS des Reaktionstages ueber 5/10/20/40 Handelstage. "
            "Mass = Spearman-Querschnitts-IC je Tag, t-Wert ueber die Tagesreihe."
        ),
    ),
    dict(
        hyp_id="H02_pead_reaktion",
        behauptung=(
            "Die marktbereinigte Kursreaktion am Meldetag sagt die Rendite der "
            "folgenden Wochen voraus - unabhaengig davon, was Analysten "
            "geschaetzt hatten."
        ),
        quelle="Bernard & Thomas (1989); Chan/Jegadeesh/Lakonishok (1996)",
        quelle_typ="akademisch_repliziert",
        veroeffentlicht="1989-01-01",
        behaupteter_effekt="gleiche Driftrichtung wie die Erstreaktion",
        operationalisierung=(
            "Faktor = Rendite des Symbols am Reaktionstag MINUS Rendite von SPY "
            "am selben Tag, aktiv fuer 60 Handelstage. Rein kursbasiert und "
            "damit zeitpunktsicher - keine revidierbaren Analystendaten. "
            "Ziel und Mass wie H01."
        ),
    ),
]


def _tabelle(name: str, faktor: pd.DataFrame,
             fwd: dict[int, pd.DataFrame]) -> pd.DataFrame:
    zeilen = []
    for h in HORIZONTE:
        k = earnings.kennzahlen(faktor, fwd[h])
        k["horizont"] = h
        zeilen.append(k)
    df = pd.DataFrame(zeilen).set_index("horizont")
    return df[["n_tage", "n_beobachtungen", "ic", "t",
               "quintil_spanne", "anteil_positive_tage"]]


def _urteil(tab: pd.DataFrame, zerfall: pd.DataFrame, placebo: dict,
            stab: pd.DataFrame) -> list[str]:
    """Fasst die vier Pruefungen zu einem Urteil zusammen.

    Bewusst als Liste von Einwaenden, nicht als Note: Ein Faktor ist nicht
    "gut", er hat nur (noch) keinen Einwand ueberlebt.
    """
    einwaende: list[str] = []

    if tab["t"].abs().max() < 2:
        einwaende.append("Kein Horizont erreicht |t| > 2 - unter der Schwelle.")

    if not zerfall.empty and zerfall["ic"].notna().sum() >= 2:
        fruehe = zerfall["ic"].iloc[0]
        spaete = zerfall["ic"].iloc[-1]
        if np.isfinite(fruehe) and np.isfinite(spaete):
            if abs(spaete) >= abs(fruehe) * 0.8:
                einwaende.append(
                    "Der IC klingt nicht ab (spaetes Band ist so stark wie das "
                    "fruehe). Das spricht fuer eine dauerhafte Symboleigenschaft, "
                    "nicht fuer eine Meldungswirkung."
                )

    if np.isfinite(placebo.get("t", np.nan)) and abs(placebo["t"]) > 2:
        einwaende.append(
            f"Placebo (Werte je Tag getauscht) hat selbst t={placebo['t']} - "
            "ein Teil des Effekts steckt im Tag, nicht im Symbol."
        )

    if not stab.empty:
        vz = np.sign(stab["ic"].dropna())
        if len(set(vz)) > 1:
            jahre = ", ".join(f"{int(j)}" for j in
                              stab.index[np.sign(stab["ic"]) < 0])
            einwaende.append(
                f"Vorzeichen wechselt zwischen den Jahren (negativ: {jahre}). "
                "Massstab dieses Projekts ist Stabilitaet in JEDEM Jahr "
                "(signals.ReversalWeights)."
            )
    return einwaende


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--max-symbols", type=int, default=800,
                   help="Obergrenze. Je Symbol EIN yfinance-Abruf fuer die "
                        "Meldetermine - 800 dauern etwa 15 Minuten.")
    p.add_argument("--jahre", type=float, default=5.0,
                   help="Kurshistorie in Jahren")
    p.add_argument("--drift-fenster", type=int, default=60,
                   help="Handelstage nach der Meldung, in denen der Faktor gilt")
    p.add_argument("--nur-bericht", action="store_true",
                   help="Nur das Hypothesenregister anzeigen, nichts messen")
    p.add_argument("--kein-cache", action="store_true")
    args = p.parse_args()

    if args.nur_bericht:
        print(hypotheses.bericht())
        return 0

    print("=" * 78)
    print("  FAKTOR-TESTS: PEAD (Post-Earnings-Announcement-Drift)")
    print("=" * 78)

    # --- 1. Hypothesen VOR dem Test eintragen -------------------------------
    # Die Voranmeldung ist der Unterschied zwischen einem bestaetigten und
    # einem erfundenen Befund. Sie hebt zugleich den Versuchszaehler und
    # damit die Signifikanzschwelle (fleet.schwelle_sigma).
    print("\n  1. Hypothesen anmelden")
    for h in HYPOTHESEN:
        print(f"     {hypotheses.erfassen(**h)}")

    # --- 2. Universum -------------------------------------------------------
    symbols = universe.load_universe(max_symbols=args.max_symbols)
    if "SPY" not in symbols:
        symbols = [*symbols, "SPY"]
    print(f"\n  2. Universum: {len(symbols)} Symbole "
          f"(liquideste nach Dollar-Volumen)")

    # --- 3. Kurse (yfinance, gecacht) ---------------------------------------
    print(f"\n  3. Kurshistorie ({args.jahre:g} Jahre, yfinance)")
    bars = datasources.get_history(symbols, years=args.jahre, source="yfinance",
                                   use_cache=not args.kein_cache, verbose=True)
    if bars.empty:
        print("     Keine Kursdaten erhalten - Abbruch.")
        return 1
    print(f"     {len(bars):,} Bars, "
          f"{bars.index.get_level_values('symbol').nunique()} Symbole")

    # --- 4. Meldetermine ----------------------------------------------------
    print(f"\n  4. Meldetermine (yfinance, ein Abruf je Symbol)")
    termine = earnings.hole_termine(symbols, use_cache=not args.kein_cache,
                                    verbose=True)
    if termine.empty:
        print("     Keine Meldetermine erhalten - Abbruch.")
        return 1

    zeitraum_start = pd.Timestamp(bars.index.get_level_values("timestamp").min())
    t_utc = pd.to_datetime(termine["meldung_ts"], utc=True)
    im_zeitraum = termine[t_utc >= zeitraum_start]
    print(f"     {len(termine):,} Meldungen insgesamt, "
          f"{len(im_zeitraum):,} im Kurszeitraum")

    # --- 5. Faktortafeln bauen ----------------------------------------------
    print(f"\n  5. Faktortafeln (Driftfenster {args.drift_fenster} Handelstage)")
    panel = earnings.baue_panel(im_zeitraum, bars,
                                drift_fenster=args.drift_fenster, verbose=True)
    if not panel:
        print("     Panel leer - Abbruch.")
        return 1

    fwd = earnings.vorwaertsrenditen(bars, HORIZONTE)

    # --- 6. Messen ----------------------------------------------------------
    print("\n" + "=" * 78)
    print("  ERGEBNISSE")
    print("=" * 78)
    print("\n  IC = Rangkorrelation Faktor gegen Vorwaertsrendite, je Tag ueber")
    print("  den Querschnitt. |t| > 2 gilt als Mindestschwelle fuer 'weiter")
    print("  pruefen'. Zum Vergleich: bester bestaetigter Faktor im Projekt")
    print("  (reversal_3d) hat IC 0.018.\n")

    alter = panel["_alter"]
    ergebnisse = {}
    urteile: dict[str, list[str]] = {}

    for name, faktor in panel.items():
        if name.startswith("_"):
            continue
        print(f"\n  --- {name} ---")
        tab = _tabelle(name, faktor, fwd)
        print(tab.to_string())
        ergebnisse[name] = tab

        besser = tab["t"].abs().idxmax() if tab["t"].notna().any() else None
        if besser is None:
            print("     (keine auswertbaren Tage)")
            continue

        # --- Zerfallsprofil: die eigentliche PEAD-Signatur ---
        print(f"\n     Zerfall nach Handelstagen seit der Meldung "
              f"(Horizont {besser}):")
        zerfall = earnings.ic_nach_alter(faktor, alter, fwd[besser])
        print("       " + zerfall.to_string().replace("\n", "\n       "))

        # --- Jahresstabilitaet ---
        print(f"\n     Jahresstabilitaet (Horizont {besser} Tage):")
        stab = earnings.jahresstabilitaet(faktor, fwd[besser])
        if stab.empty:
            print("       (zu wenig Daten)")
        else:
            print("       " + stab.to_string().replace("\n", "\n       "))

        # --- Placebo: Werte je Tag unter den Symbolen tauschen ---
        pl = earnings.placebo_permutation(faktor, fwd[besser])
        print(f"\n     Placebo (Werte je Tag unter den Symbolen getauscht):")
        print(f"       IC {pl['ic']}  t={pl['t']}  ({pl['n_tage']} Tage)")

        # --- Eigenstaendigkeit gegen die bestehenden Umkehr-Faktoren ---
        print(f"\n     Eigenstaendigkeit (bringt der Faktor NEUE Information?):")
        eig = earnings.eigenstaendigkeit(faktor, bars, fwd[besser], verbose=False)
        if eig.empty:
            print("       (nicht berechenbar)")
        else:
            print("       " + eig.to_string().replace("\n", "\n       "))

        einwaende = _urteil(tab, zerfall, pl, stab)
        if not eig.empty and eig["residual_t"].abs().max() < 2:
            einwaende.append(
                "Nach Herausrechnen der bestehenden Umkehr-Faktoren bleibt "
                "kein IC uebrig - der Faktor misst dasselbe wie die laufende "
                "Strategie und wuerde nichts hinzufuegen."
            )
        urteile[name] = einwaende
        print(f"\n     URTEIL:")
        if einwaende:
            for e in einwaende:
                print(f"       - {e}")
        else:
            print("       Kein Einwand ueberlebt - Kandidat fuer den "
                  "Vorwaertstest im Schatten.")

    # --- 7. Ins Register zurueckschreiben -----------------------------------
    print("\n" + "=" * 78)
    print("  REGISTER AKTUALISIEREN")
    print("=" * 78)
    zuordnung = {"pead_ueberraschung": "H01_pead_ueberraschung",
                 "pead_reaktion": "H02_pead_reaktion"}
    for name, tab in ergebnisse.items():
        hyp_id = zuordnung.get(name)
        if not hyp_id or tab["t"].isna().all():
            continue
        besser = tab["t"].abs().idxmax()
        erg = hypotheses.historientest(
            hyp_id, panel[name], fwd[besser], horizont=int(besser)
        )
        # `historientest` setzt den Status allein nach |t| > 2. Das reicht
        # als Filter nicht: Ein Faktor mit hohem t, der aber den Placebo-
        # oder Zerfallstest nicht besteht, ist genau der Fall, den die
        # ganze Pruefung verhindern soll.
        offene = urteile.get(name, [])
        status = "im_test" if (abs(erg.get("t") or 0) > 2 and not offene) else "widerlegt"
        print(f"  {hyp_id}: IC {erg.get('ic')}  t={erg.get('t')}  "
              f"-> {status}" + (f"  ({len(offene)} Einwand/Einwaende)" if offene else ""))
        if offene:
            from alpaca_bot.shadow import ShadowStore
            with ShadowStore()._conn() as c:
                c.execute("UPDATE hypothesen SET status='widerlegt' WHERE hyp_id=?",
                          (hyp_id,))

    print()
    print(hypotheses.bericht())
    return 0


if __name__ == "__main__":
    sys.exit(main())
