#!/usr/bin/env python3
"""Schritt 55: Traegt eine Konfiguration in JEDEM Jahr - oder nur in einem?

    python scripts/55_ausbruch_perioden.py
    python scripts/55_ausbruch_perioden.py --quelle elite --jahre 2021-2026

**Die Frage, die ein einzelner Lern/Pruef-Schnitt nicht beantwortet.**
Ein Schnitt liefert eine Zahl. Sechs Jahre liefern sechs Zahlen - und
erst die zeigen, ob ein Ergebnis ein Effekt ist oder eine Marktphase.

**Warum das gerade fuer 2021 und 2022 gebaut wurde.** 2021 war ein
extremer Aufschwung (Meme-Aktien, SPAC-Welle, Nullzins), 2022 ein
harter Baerenmarkt. Eine Ausbruch-Strategie sieht in 2021 glaenzend aus,
aus Gruenden, die so nicht wiederkommen. Deshalb gilt hier eine strenge
Trennung:

    Dieses Skript WAEHLT NICHTS AUS. Es bewertet eine fertige
    Konfiguration je Periode. Optimiert wird nie auf diesen Jahren -
    sonst waere das Ergebnis wieder nur die Erinnerung an 2021.

**Das Marktumfeld wird gemessen, nicht behauptet.** Die Jahresrendite
des Referenzwerts steht neben jedem Jahr - so ist nachlesbar, ob ein
gutes Jahr ein gutes Marktjahr war.

**Gelesen wird die Spalte 'je Trade', nicht 'Rendite'.** Die
Gesamtrendite eines Jahres haengt an der Zahl der Trades; die Rendite je
Trade ist der Teil, der die Strategie beschreibt. Und `Top5` daneben
sagt, ob das Jahr breit getragen war oder an fuenf Symbolen hing (§G66).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from alpaca_bot import ausbruch  # noqa: E402
from alpaca_bot import ausbruch_daten  # noqa: E402
from alpaca_bot import ausbruch_store  # noqa: E402
from alpaca_bot import ausbruch_suche as su  # noqa: E402


def _kopf(text: str) -> None:
    print()
    print("=" * 78)
    print(f"  {text}")
    print("=" * 78)


def _jahre(text: str) -> list[int]:
    aus: set[int] = set()
    for teil in filter(None, text.split(",")):
        teil = teil.strip()
        if "-" in teil:
            a, _, b = teil.partition("-")
            aus.update(range(int(a), int(b) + 1))
        else:
            aus.add(int(teil))
    return sorted(aus)


def markt_rendite(kd, symbol: str, jahr: int) -> float:
    """Jahresrendite des Referenzwerts - das gemessene Marktumfeld."""
    eintrag = kd.arrays.get(symbol)
    if eintrag is None:
        return float("nan")
    c = pd.Series(eintrag[3].astype("float64")).ffill().dropna()
    if len(c) < 2:
        return float("nan")
    return float((c.iloc[-1] / c.iloc[0] - 1.0) * 100.0)


def periode_bewerten(kd_jahr, config: dict, referenz: str,
                     jahr: int) -> dict:
    """Einen einzelnen Zeitabschnitt durchrechnen."""
    erg = ausbruch.lauf(kd_jahr, ausbruch.AusbruchConfig(**config))
    k = erg.kennzahlen
    return {
        "jahr": jahr,
        "markt_pct": markt_rendite(kd_jahr, referenz, jahr),
        "t": float(k.get("t_wert", float("nan"))),
        "t_ohne_top5": float(k.get("t_ohne_top5", float("nan"))),
        "top5_pct": float(k.get("top5_anteil_pct", float("nan"))),
        "rendite_pct": float(k.get("rendite_pct", 0.0)),
        "mittel_pct": float(k.get("mittel_pct", 0.0)),
        "n_trades": int(k.get("n_trades", 0) or 0),
        "n_tage": int(k.get("n_handelstage", 0) or 0),
        "dd_pct": float(k.get("max_drawdown_pct", 0.0)),
    }


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--quelle", default="elite",
                   choices=["elite", "gate", "datei"])
    p.add_argument("--datei", default=None)
    p.add_argument("--jahre", default=None, help="z.B. 2021-2026")
    p.add_argument("--raster", default="15Min")
    p.add_argument("--referenz", default="QQQ",
                   help="Referenzwert fuer das gemessene Marktumfeld")
    args = p.parse_args()

    # --- Konfiguration holen -----------------------------------------
    if args.quelle == "elite":
        e = su.elite_lesen() or {}
        config = dict(e.get("config") or {})
        herkunft = f"Elite, score {e.get('score', 0):.3f}"
    elif args.quelle == "gate":
        from alpaca_bot.config import DATA_DIR
        daten = json.loads((DATA_DIR / "ausbruch_gate.json").read_text())
        eintrag = daten["anmeldungen"][-1]
        config = dict(eintrag["config"])
        herkunft = f"Gate-Anmeldung {eintrag['id'][:8]}"
    else:
        roh = json.loads(Path(args.datei).read_text(encoding="utf-8"))
        config = dict(roh.get("config") or roh)
        herkunft = f"Datei {args.datei}"

    if not config:
        print("Keine Konfiguration gefunden.")
        return 1

    jahre = _jahre(args.jahre) if args.jahre else \
        ausbruch_daten.jahre_vorhanden(args.raster)
    if not jahre:
        print("Kein Kursvorrat vorhanden.")
        return 1

    print(f"Vorrat laden ({jahre}, {args.raster}) ...", flush=True)
    kd = ausbruch_daten.laden_kursdaten(
        jahre, raster=args.raster,
        fortschritt=lambda a, t: print(f"  {a*100:5.1f}% {t}", flush=True))
    print(f"{len(kd.arrays):,} Symbole, {kd.n_bars:,} Bars.", flush=True)

    _kopf("JE PERIODE - dieselbe Konfiguration, getrennte Jahre")
    print(f"  Konfiguration: {herkunft}")
    print(f"  Marktumfeld gemessen an {args.referenz}")
    print()
    print(f"  {'Jahr':<6}{'Markt':>9}{'t':>7}{'t-o-Top5':>10}{'Top5':>8}"
          f"{'Rendite':>10}{'je Trade':>10}{'Trades':>8}{'Tage':>6}")
    print("  " + "-" * 74)

    zeilen = []
    for jahr in jahre:
        try:
            teil = kd.zeitraum(f"{jahr}-01-01", f"{jahr + 1}-01-01")
        except ValueError:
            continue
        try:
            z = periode_bewerten(teil, config, args.referenz, jahr)
        except Exception as e:  # noqa: BLE001
            print(f"  {jahr:<6}  Fehler: {type(e).__name__}: {e}")
            continue
        zeilen.append(z)
        top5 = (f"{z['top5_pct']:>7.0f}%" if np.isfinite(z["top5_pct"])
                else "      -")
        tot = (f"{z['t_ohne_top5']:>10.2f}"
               if np.isfinite(z["t_ohne_top5"]) else "         -")
        print(f"  {jahr:<6}{z['markt_pct']:>8.1f}%{z['t']:>7.2f}{tot}{top5}"
              f"{z['rendite_pct']:>9.2f}%{z['mittel_pct']:>9.3f}%"
              f"{z['n_trades']:>8}{z['n_tage']:>6}", flush=True)

    if not zeilen:
        print("  Keine Periode auswertbar.")
        return 1

    # --- Die Buchung: das waren echte Laeufe --------------------------
    lauf_id = ausbruch_store.neuer_lauf(
        {"perioden": True, "quelle": args.quelle, "jahre": jahre,
         "config": config},
        jahr=jahre[-1], raster=args.raster, n_symbole=len(kd.arrays),
        notiz=f"Perioden-Auswertung {herkunft}")
    ausbruch_store.suchversuche_buchen(lauf_id, len(zeilen))

    # --- Urteil -------------------------------------------------------
    positiv = [z for z in zeilen if z["mittel_pct"] > 0]
    breit = [z for z in zeilen
             if np.isfinite(z["top5_pct"]) and z["top5_pct"] <= 50.0]
    schwach = [z for z in zeilen if z["n_trades"] < 30]

    print()
    print(f"  Positiv je Trade : {len(positiv)} von {len(zeilen)} Jahren")
    print(f"  Breit getragen   : {len(breit)} von {len(zeilen)} Jahren "
          f"(Top-5 unter 50 %)")
    if schwach:
        print(f"  Zu duenn         : {len(schwach)} Jahre mit unter 30 Trades "
              f"- dort sagt die Zahl wenig")

    baer = [z for z in zeilen if np.isfinite(z["markt_pct"])
            and z["markt_pct"] < 0]
    if baer:
        gut_im_baer = [z for z in baer if z["mittel_pct"] > 0]
        print(f"  Im fallenden Markt: {len(gut_im_baer)} von {len(baer)} "
              f"Jahren positiv "
              f"({', '.join(str(z['jahr']) for z in baer)})")
    else:
        print("  Im fallenden Markt: kein Jahr mit negativem Markt im "
              "Zeitraum -")
        print("                      die Probe aufs Exempel fehlt noch.")

    print()
    if len(positiv) == len(zeilen) and len(breit) == len(zeilen):
        print("  Traegt in jedem Jahr und jedes Jahr breit. Das ist der "
              "seltene Fall,")
        print("  in dem eine Gate-Pruefung sich lohnt.")
    elif len(positiv) <= 1:
        print("  Ein einzelnes gutes Jahr ist eine Marktphase, kein Effekt.")
    else:
        print("  Uneinheitlich. Welche Jahre tragen und welche nicht, steht "
              "oben -")
        print("  das ist die eigentliche Information, nicht der Durchschnitt.")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
