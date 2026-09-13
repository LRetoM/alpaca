#!/usr/bin/env python3
"""Schritt 57: Quartals-Momentum vorwaerts messen - Koerbe vorab festschreiben.

    python scripts/57_querschnitt_vorwaerts.py --anmelden
    python scripts/57_querschnitt_vorwaerts.py --korb        # am Stichtag
    python scripts/57_querschnitt_vorwaerts.py --auswerten
    python scripts/57_querschnitt_vorwaerts.py              # Stand

**Warum vorwaerts.** §G79: Rueckwaerts ist in dieser Werkstatt nichts
mehr zu beweisen - die projektweite Zufallsschwelle liegt bei 4,90, und
dafuer braeuchte man bei sechs Jahren Daten einen Sharpe von 2,0. Ein
einzelner vorab angemeldeter Test vorwaerts hat eine Huerde von rund
2,0.

**Was das Protokoll leistet.** Der Korb wird geschrieben, bevor sein
Ergebnis existiert. Das ist konstruktiv lookahead-frei - nicht weil ein
Test es prueft, sondern weil die Zukunft zum Zeitpunkt des Schreibens
noch nicht stattgefunden hat.

**Was es NICHT leistet, in Zahlen.** Bei Sharpe 0,48 (§G78) braucht
t = 2,0 rund **17 Jahre**. Dieses Protokoll wird die Strategie also nicht
beweisen. Es tut zwei andere Dinge, die etwas wert sind:

1. Es haelt fest, was vorab behauptet wurde - gegen die nachtraegliche
   Erzaehlung, auch die eigene.
2. Es faellt **sofort** auf, wenn die Strategie vorwaerts deutlich
   schlechter laeuft als rueckwaerts. Das ist der haeufigste Fall, und
   ihn frueh zu sehen ist der eigentliche Nutzen.

Ehrlicher geht es mit den Mitteln dieses Projekts nicht.
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
from alpaca_bot import querschnitt as q  # noqa: E402
from alpaca_bot.querschnitt_vorwaerts import Vorwaerts  # noqa: E402

# --- Die Voranmeldung, wortwoertlich ---------------------------------
ANMELDUNG_ID = "Q01_quartals_momentum"

NAME = "Quartals-Momentum marktneutral"

HYPOTHESE = (
    "Querschnitt-Momentum ueber 120 Handelstage traegt auch nach Kosten, "
    "weil bei 63 Tagen Haltedauer nur rund 3 % Kostenlast im Jahr "
    "entstehen statt ueber 30 % bei kurzer Haltedauer. Marktneutral "
    "gerechnet, damit weder Marktanstieg noch Survivorship das Ergebnis "
    "erzeugen koennen - beide waren die Ursache der Scheinbefunde in "
    "§G53 und §G73."
)

CONFIG = dict(signal="momentum", rueckblick_tage=120, luecke_tage=5,
              halten_tage=63, anteil_pct=10.0, marktneutral=True,
              min_preis=5.0, min_dollar_volumen=1_000_000.0,
              spanne_bps=30.0, slippage_bps=3.0)

KRITERIEN = {
    "t_schwelle": 2.0,
    "begruendung_schwelle": "EIN vorab angemeldeter Test, nicht der "
                            "470.001-te Versuch (§G79).",
    "min_perioden": 20,
    "erwartung_rueckwaerts": {
        "netto_je_periode_pct": 2.174, "sharpe": 0.49, "t": 1.10,
        "treffer_pct": 60.0,
        "quelle": "§G78 (korrigiert, §G80), 2021-2026, 30 bps, 20 Perioden",
    },
    "abbruch_wenn": "Nach 8 Perioden liegt der Mittelwert unter null - "
                    "dann ist der Rueckwaerts-Befund vorwaerts nicht "
                    "wiederzufinden.",
}


def _kopf(text: str) -> None:
    print()
    print("=" * 78)
    print(f"  {text}")
    print("=" * 78)


def _laden(jahre_text: str, raster: str):
    jahre = []
    for teil in filter(None, jahre_text.split(",")):
        if "-" in teil:
            a, _, b = teil.strip().partition("-")
            jahre.extend(range(int(a), int(b) + 1))
        else:
            jahre.append(int(teil))
    jahre = sorted(set(jahre))
    print(f"Vorrat laden ({jahre}, {raster}) ...", flush=True)
    kd = ausbruch_daten.laden_kursdaten(
        jahre, raster=raster,
        fortschritt=lambda a, t: print(f"  {a*100:5.1f}% {t}", flush=True))
    return kd


def anmelden(db: Vorwaerts) -> int:
    if db.anmeldung(ANMELDUNG_ID):
        print("Schon angemeldet - eine Voranmeldung wird nicht ersetzt.")
        return 1
    db.anmelden(id=ANMELDUNG_ID, name=NAME, hypothese=HYPOTHESE,
                config=CONFIG, kriterien=KRITERIEN)
    _kopf("VORANMELDUNG GESCHRIEBEN")
    print(f"  Kennung : {ANMELDUNG_ID}")
    print(f"  Name    : {NAME}")
    print(f"  Datei   : {db.pfad}")
    print()
    print("  Hypothese:")
    for zeile in HYPOTHESE.split(". "):
        if zeile.strip():
            print(f"    {zeile.strip().rstrip('.')}.")
    print()
    print("  Vorab festgelegt:")
    print(f"    Schwelle          : t > {KRITERIEN['t_schwelle']}")
    print(f"    Perioden noetig   : {KRITERIEN['min_perioden']}")
    print(f"    Rueckwaerts-Erwartung: "
          f"{KRITERIEN['erwartung_rueckwaerts']['netto_je_periode_pct']:+.3f} % "
          f"je Periode, Sharpe "
          f"{KRITERIEN['erwartung_rueckwaerts']['sharpe']}")
    print(f"    Abbruch wenn      : {KRITERIEN['abbruch_wenn']}")
    print()
    print("  Korb erfassen: python scripts/57_querschnitt_vorwaerts.py --korb")
    print("=" * 78)
    return 0


def korb(db: Vorwaerts, jahre: str, raster: str) -> int:
    a = db.anmeldung(ANMELDUNG_ID)
    if not a:
        print("Erst anmelden (--anmelden).")
        return 1
    cfg = q.QuerschnittConfig(**a["config"])
    kd = _laden(jahre, raster)
    kurse, umsatz = q.tageskurse(kd)

    # Der letzte vorhandene Handelstag ist der Stichtag. Das Signal sieht
    # ausschliesslich Kurse bis dahin - mehr gibt es noch nicht.
    i = len(kurse) - 1
    stichtag = kurse.index[i]
    werte = q.signal_werte(kurse.iloc[:i + 1], cfg)
    preis, vol = kurse.iloc[i], umsatz.iloc[i]
    erlaubt = werte.index[
        (preis.reindex(werte.index) >= cfg.min_preis)
        & (vol.reindex(werte.index) >= cfg.min_dollar_volumen)]
    werte = werte.loc[erlaubt]
    if len(werte) < cfg.min_symbole:
        print(f"Nur {len(werte)} handelbare Werte - unter dem Minimum "
              f"{cfg.min_symbole}. Kein Korb.")
        return 1

    k = max(int(len(werte) * cfg.anteil_pct / 100.0), 1)
    sortiert = werte.sort_values(ascending=False)
    long_seite, short_seite = sortiert.iloc[:k], sortiert.iloc[-k:]

    try:
        n = db.korb_schreiben(ANMELDUNG_ID, stichtag, long_seite,
                              short_seite, preis)
    except ValueError as e:
        print(f"{e}")
        return 1

    _kopf(f"KORB ERFASST - Stichtag {stichtag.date()}")
    print(f"  {n} Zeilen, {len(long_seite)} long / {len(short_seite)} short, "
          f"aus {len(werte)} handelbaren Werten")
    print(f"  Halten bis rund {cfg.halten_tage} Handelstage spaeter.")
    print()
    print(f"  Long  (staerkste): "
          f"{', '.join(str(s) for s in long_seite.index[:10])}"
          f"{' ...' if len(long_seite) > 10 else ''}")
    print(f"  Short (schwaechste): "
          f"{', '.join(str(s) for s in short_seite.index[:10])}"
          f"{' ...' if len(short_seite) > 10 else ''}")
    print()
    print("  Dieser Korb steht jetzt fest und kann nicht mehr geaendert "
          "werden.")
    print("=" * 78)
    return 0


def auswerten(db: Vorwaerts, jahre: str, raster: str) -> int:
    a = db.anmeldung(ANMELDUNG_ID)
    if not a:
        print("Nichts angemeldet.")
        return 1
    offen = db.offene(ANMELDUNG_ID)
    if not offen:
        print("Keine offenen Koerbe.")
        return _stand(db)

    cfg = q.QuerschnittConfig(**a["config"])
    kd = _laden(jahre, raster)
    kurse, _ = q.tageskurse(kd)
    tage = kurse.index.normalize()

    neu = 0
    for tag in offen:
        stichtag = pd.Timestamp(tag)
        treffer = np.flatnonzero(tage == stichtag)
        if not len(treffer):
            print(f"  {tag}: Stichtag nicht in den Kursdaten - uebersprungen.")
            continue
        i = int(treffer[0])
        if i + cfg.halten_tage >= len(kurse):
            rest = i + cfg.halten_tage - len(kurse) + 1
            print(f"  {tag}: laeuft noch, {rest} Handelstage fehlen.")
            continue

        k = db.korb(ANMELDUNG_ID, tag)
        p1 = kurse.iloc[i + cfg.halten_tage]
        r = {}
        fehlend = 0
        for _, zeile in k.iterrows():
            sym = zeile["symbol"]
            ende = float(p1.get(sym, float("nan")))
            if not np.isfinite(ende):
                fehlend += 1
                continue
            r.setdefault(zeile["seite"], []).append(
                (ende / float(zeile["kurs"]) - 1.0) * 100.0)

        r_long = float(np.mean(r.get("long", [np.nan])))
        r_short = float(np.mean(r.get("short", [np.nan])))
        if not np.isfinite(r_long) or not np.isfinite(r_short):
            print(f"  {tag}: zu viele fehlende Kurse - uebersprungen.")
            continue
        kosten = cfg.kosten_je_rundlauf_pct() * 2.0
        brutto = r_long - r_short
        db.ergebnis_schreiben(
            ANMELDUNG_ID, tag, ende=str(kurse.index[i + cfg.halten_tage].date()),
            r_long=r_long, r_short=r_short, brutto_pct=brutto,
            netto_pct=brutto - kosten, n_long=len(r.get("long", [])),
            n_short=len(r.get("short", [])), fehlend=fehlend)
        neu += 1
        print(f"  {tag}: netto {brutto - kosten:+.3f} % "
              f"(long {r_long:+.2f} / short {r_short:+.2f})")

    print(f"\n  {neu} Periode(n) neu ausgewertet.")
    return _stand(db)


def _stand(db: Vorwaerts) -> int:
    a = db.anmeldung(ANMELDUNG_ID)
    _kopf("VORWAERTS-STAND")
    if not a:
        print("  Nichts angemeldet.")
        print("  python scripts/57_querschnitt_vorwaerts.py --anmelden")
        print("=" * 78)
        return 0
    print(f"  {a['name']}  (angemeldet {a['angemeldet_am'][:19]})")
    kr = a["kriterien"]
    e = db.ergebnisse(ANMELDUNG_ID)
    koerbe = db.stichtage(ANMELDUNG_ID)
    offen = db.offene(ANMELDUNG_ID)
    print(f"  Koerbe erfasst : {len(koerbe)}")
    print(f"  ausgewertet    : {len(e)}")
    print(f"  noch offen     : {len(offen)}")

    if len(e):
        netto = e["netto_pct"].dropna()
        print()
        print(f"  Mittelwert je Periode : {netto.mean():+.3f} %")
        print(f"  Rueckwaerts erwartet  : "
              f"{kr['erwartung_rueckwaerts']['netto_je_periode_pct']:+.3f} %")
        print(f"  Treffer               : {(netto > 0).mean()*100:.0f} %")
        if len(netto) >= 2 and netto.std() > 0:
            t = netto.mean() / (netto.std() / math.sqrt(len(netto)))
            print(f"  t-Wert                : {t:.2f}  "
                  f"(noetig {kr['t_schwelle']}, ab "
                  f"{kr['min_perioden']} Perioden)")
        if len(netto) >= 8 and netto.mean() < 0:
            print()
            print("  ABBRUCHKRITERIUM ERREICHT: Nach 8 Perioden ist der "
                  "Mittelwert negativ.")
            print(f"  Vorab festgelegt: {kr['abbruch_wenn']}")
    else:
        print()
        print("  Noch kein Ergebnis. Bei 63 Handelstagen Haltedauer dauert")
        print("  eine Periode rund drei Monate.")
    print("=" * 78)
    return 0


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--anmelden", action="store_true")
    p.add_argument("--korb", action="store_true")
    p.add_argument("--auswerten", action="store_true")
    p.add_argument("--jahre", default="2021-2026")
    p.add_argument("--raster", default="15Min")
    args = p.parse_args()

    db = Vorwaerts()
    if args.anmelden:
        return anmelden(db)
    if args.korb:
        return korb(db, args.jahre, args.raster)
    if args.auswerten:
        return auswerten(db, args.jahre, args.raster)
    return _stand(db)


if __name__ == "__main__":
    raise SystemExit(main())
