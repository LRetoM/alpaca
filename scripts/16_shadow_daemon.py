#!/usr/bin/env python3
"""Schritt 16: Schattenbetrieb - lernen, ohne zu handeln.

Zeichnet taeglich JEDEN Kandidaten auf, den die Engine oberhalb der
Score-Schwelle findet, und haelt spaeter nach, was tatsaechlich daraus
geworden ist. Es wird keine einzige Order gesendet - dieses Skript
importiert `trading.py` gar nicht erst.

WARUM DAS NOETIG IST: Der Live-Bot kauft hoechstens 3 Werte je Lauf und
verwirft dabei ~200 Kandidaten. Ob unsere Rangliste richtig sortiert,
laesst sich aus 3 Beobachtungen am Tag nicht beantworten - aus 200 schon.
Und weil diese Vorhersagen VORWAERTS entstehen, sind sie gegen den Fehler
immun, eine Strategie auf derselben Historie auszuwaehlen, auf der man sie
danach misst.

Der Betrieb hat drei Schritte mit unterschiedlichem Rhythmus:

    entscheiden    nach US-Schluss (~22:15 CEST): Kandidaten festhalten
    einbuchen      naechster Handelstag: Eroeffnungskurs nachtragen
    verifizieren   laufend: Horizontrenditen, Ausstieg, Referenzen

    python scripts/16_shadow_daemon.py --status      # Zustand ansehen
    python scripts/16_shadow_daemon.py --einmal      # alle Schritte einmal
    python scripts/16_shadow_daemon.py               # Dauerbetrieb
    python scripts/16_shadow_daemon.py --schritt entscheiden

Getrennt vom Handelsbot betrieben (eigener Prozess, eigene Datenbank), damit
ein Fehler in der Forschung den Handelspfad nicht mitreisst.
"""

from __future__ import annotations

import argparse
import datetime as dt
import signal
import sys
import time
import traceback

from alpaca_bot import nutzung
from alpaca_bot.engine import EngineConfig
from alpaca_bot.shadow import (ShadowConfig, ShadowStore, einbuchen, entscheiden,
                               lernen, verifizieren)

_stop = False


def _limit_anheben() -> None:
    """Hebt das Limit offener Dateien auf ein fuer den Dauerbetrieb
    ausreichendes Mass an.

    launchd setzt fuer selbst gestartete Dienste standardmaessig ein
    Soft-Limit von 256 offenen Dateien - unabhaengig von der Shell-Grenze.
    yfinance oeffnet fuer seinen Zeitzonen-Cache (`tkr-tz.db`) bei jedem
    Download eine eigene SQLite-Verbindung, ohne sie zuverlaessig zu
    schliessen. Ueber Stunden im Dauerbetrieb summiert sich das, bis das
    256er-Limit reisst - beobachtet am 2026-07-29: ab da schlugen ALLE
    Schritte (Entscheiden/Einbuchen/Verifizieren) mit
    "OSError: Too many open files" bzw. "unable to open database file" fehl,
    fuer den Rest der Nacht, ohne dass der Daemon selbst abstuerzte.

    Angehoben wird auf das Hard-Limit des Systems (hier praktisch
    unbegrenzt) - schlaegt das fehl, laeuft der Prozess mit dem
    Standardwert weiter, statt abzubrechen.
    """
    try:
        import resource

        weich, hart = resource.getrlimit(resource.RLIMIT_NOFILE)
        ziel = min(hart, 8192) if hart != resource.RLIM_INFINITY else 8192
        if weich < ziel:
            resource.setrlimit(resource.RLIMIT_NOFILE, (ziel, hart))
            print(f"  Datei-Limit angehoben: {weich} -> {ziel}")
    except Exception as e:  # noqa: BLE001 - darf den Start nie verhindern
        print(f"  Datei-Limit konnte nicht angehoben werden: {e}")


def _handle_signal(signum, frame):  # noqa: ARG001
    global _stop
    print(f"\n  Signal {signum} empfangen - beende nach dem laufenden Schritt.")
    _stop = True


def alle_schritte(cfg: ShadowConfig, store: ShadowStore, *, verbose: bool = True) -> dict:
    """Ein vollstaendiger Durchgang.

    Reihenfolge ist wichtig: Erst einbuchen (Vorhersagen von gestern bekommen
    ihren Einstiegskurs), dann verifizieren, dann neu entscheiden. Andersherum
    wuerde die frische Entscheidung sofort mit-eingebucht - zum Kurs desselben
    Tages, auf dem sie beruht. Das waere ein Datenleck.

    **`lernen` steht am Ende und nicht am Anfang.** Es wertet aus, was die
    drei Schritte davor erzeugt haben. Liefe es zuerst, saehe es immer den
    Stand von gestern - eine ganze Runde Verzoegerung, die niemandem
    auffiele.

    Alle vier Schritte sind **idempotent**: Ohne neuen Handelstag tun sie
    nichts und kosten Sekundenbruchteile. Das ist die Voraussetzung
    dafuer, den Durchgang haeufig laufen zu lassen, ohne Rechenzeit und
    API-Kontingent zu verbrennen (§G14).
    """
    ergebnis = {}
    for name, fn, baustein in (("eingebucht", einbuchen, "schatten.einbuchen"),
                               ("verifiziert", verifizieren, "schatten.verifizieren"),
                               ("entschieden", entscheiden, "schatten.entscheiden"),
                               ("gelernt", lernen, "schatten.lernen")):
        if _stop:
            break
        t0 = time.time()
        try:
            print(f"  [{dt.datetime.now():%H:%M:%S}] {name} ...")
            ergebnis[name] = fn(cfg, store, verbose=verbose)
            # Die Signatur kennzeichnet das ERGEBNIS, nicht den Lauf: Zahl
            # plus juengster Stichtag. Bleibt sie ueber viele Runden gleich,
            # wurde zwar gerechnet, aber nichts Neues gefunden - genau der
            # Zustand, den der Dauerbetrieb monatelang hatte (§G14).
            nutzung.melden(baustein, ergebnis[name],
                           signatur=f"{ergebnis[name]}@{_stichtag(store)}",
                           dauer_s=round(time.time() - t0, 2))
        except Exception as e:  # noqa: BLE001 - ein Schritt darf die anderen nicht stoppen
            print(f"      FEHLER in '{name}': {type(e).__name__}: {e}")
            traceback.print_exc()
            ergebnis[name] = -1
            nutzung.melden(baustein, -1, signatur="fehler",
                           dauer_s=round(time.time() - t0, 2),
                           hinweis=f"{type(e).__name__}: {e}")

    # Sicherung NACH den Schritten, nicht davor: Gesichert wird der
    # Stand, den dieser Durchgang erzeugt hat. Und nur, wenn etwas
    # entstanden ist - die vier Schritte sind idempotent (§G14), am
    # Wochenende liefern sie alle 0. Eine Kopie je Leerlauf waere reine
    # Plattenarbeit und wuerde die sieben aufbewahrten Staende binnen
    # Stunden mit identischen Kopien fuellen, sodass am Montag kein
    # einziger Stand von vor dem Wochenende mehr da waere.
    # (BEFUNDE §G19 Fund 7)
    if any(v > 0 for v in ergebnis.values() if isinstance(v, int)):
        t0 = time.time()
        ziel = store.sichern()
        if verbose and ziel:
            print(f"      Sicherung: {ziel.name} "
                  f"({ziel.stat().st_size / 1e6:.1f} MB, "
                  f"{time.time() - t0:.1f}s)")
    return ergebnis


def _stichtag(store: ShadowStore) -> str:
    """Juengster Stichtag im Buch - Teil der Nutzungssignatur."""
    try:
        with store._conn() as c:
            return (c.execute("SELECT MAX(as_of) FROM predictions").fetchone()[0]
                    or "")[:10]
    except Exception:  # noqa: BLE001
        return ""


def main() -> int:
    _limit_anheben()
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--universe", default="gemessen",
                   help="'gemessen' = Werte aus dem Faktor-Labor, sonst feste Liste")
    p.add_argument("--max-symbols", type=int, default=800,
                   help="Obergrenze. Jeder Kandidat wird erfasst, Laufzeit waechst mit.")
    p.add_argument("--years", type=float, default=2.0,
                   help="Historie je Lauf (Signale brauchen 260 Bars Vorlauf)")
    p.add_argument("--min-score", type=float, default=None,
                   help="Ueberschreibt die Score-Schwelle der Strategie")
    p.add_argument("--interval", type=int, default=3600,
                   help="Sekunden zwischen zwei Durchgaengen im Dauerbetrieb")
    p.add_argument("--einmal", action="store_true", help="Nur ein Durchgang")
    p.add_argument("--status", action="store_true", help="Nur Zustand anzeigen")
    p.add_argument("--schritt",
                   choices=["entscheiden", "einbuchen", "verifizieren", "lernen"],
                   help="Nur diesen einen Schritt ausfuehren")
    p.add_argument("--bot-id", default="B00_basis")
    args = p.parse_args()

    store = ShadowStore()

    if args.status:
        print(store.status_text())
        return 0

    engine = EngineConfig.for_reversal()
    if args.min_score is not None:
        engine.min_score = args.min_score

    cfg = ShadowConfig(
        universe=args.universe,
        max_symbols=args.max_symbols,
        years=args.years,
        engine=engine,
        bot_id=args.bot_id,
    )

    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, _handle_signal)

    print("=" * 72)
    print("  SCHATTENBETRIEB  |  ES WERDEN KEINE ORDERS GESENDET")
    print("=" * 72)
    print(f"  Universum : {args.universe} (max. {args.max_symbols} Symbole)")
    print(f"  Strategie : {engine.strategy}, Score-Schwelle {engine.min_score}")
    print(f"  Datenbank : {store.path}")
    print()

    if args.schritt:
        fn = {"entscheiden": entscheiden, "einbuchen": einbuchen,
              "verifizieren": verifizieren, "lernen": lernen}[args.schritt]
        n = fn(cfg, store)
        print(f"\n  {args.schritt}: {n}")
        print()
        print(store.status_text())
        return 0

    if args.einmal:
        res = alle_schritte(cfg, store)
        print(f"\n  Ergebnis: {res}")
        print()
        print(store.status_text())
        return 0

    # --- Dauerbetrieb ---
    while not _stop:
        res = alle_schritte(cfg, store)
        print(f"  Durchgang fertig: {res}")
        if _stop:
            break
        for _ in range(args.interval):
            if _stop:
                break
            time.sleep(1)

    print("\n  Schattenbetrieb sauber beendet.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
