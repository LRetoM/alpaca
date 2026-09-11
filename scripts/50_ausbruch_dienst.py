#!/usr/bin/env python3
"""Schritt 50: Ausbruch-Suche als Dauerdienst - laeuft im Hintergrund,
setzt beim Neustart automatisch fort statt bei 0 anzufangen.

    python scripts/50_ausbruch_dienst.py --jahre 2023-2026

**Anders als `49_ausbruch_dauerlauf.py`:** Kein Live-Terminal, keine
Interaktion. Stattdessen schreibt der Dienst regelmaessig zwei Dateien:

    ausbruch_stand.json         - aktueller Fortschritt, fuer `51_...`
    ausbruch_checkpoint.json    - vollstaendiger Zustand, zum Fortsetzen

Stirbt der Prozess (Absturz, Neustart des Rechners), laedt der naechste
Start den Checkpoint und rechnet dort weiter, statt wieder bei Versuch 1
anzufangen. Gedacht als LaunchAgent (siehe `docs/AUSBRUCH.md` §5c) -
genau wie `12_daemon.py` fuer den Handelsbot.

Status ansehen, ohne den Dienst anzufassen:

    python scripts/51_ausbruch_status.py
"""

from __future__ import annotations

import argparse
import signal
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from alpaca_bot import ausbruch_daten, ausbruch_store  # noqa: E402
from alpaca_bot import ausbruch_versuche  # noqa: E402
from alpaca_bot import ausbruch_suche as su  # noqa: E402
from alpaca_bot.config import DATA_DIR  # noqa: E402

def _stand_datei(instanz: str) -> Path:
    return DATA_DIR / f"ausbruch_stand_{instanz}.json"


def _checkpoint_datei(instanz: str) -> Path:
    return DATA_DIR / f"ausbruch_checkpoint_{instanz}.json"

_STOPP = False
_GRUND = ""


def _stoppen(signum, *_a) -> None:
    """Merkt sich, WELCHES Signal kam.

    Bei einem Lauf ueber Wochen ist "der Dienst ist aus" keine
    brauchbare Auskunft. Die drei Faelle haben verschiedene Ursachen und
    verschiedene Konsequenzen: SIGTERM ist ein gewollter Stopp
    (launchctl bootout, Neustart des Rechners), SIGINT ist Strg+C von
    Hand, und ein Ende ohne Signal heisst, dass die Suche selbst
    zurueckkehrte - weil der Suchraum abgesucht ist.
    """
    global _STOPP, _GRUND
    _STOPP = True
    _GRUND = {2: "SIGINT (Strg+C)", 15: "SIGTERM (launchctl/Neustart)"}.get(
        signum, f"Signal {signum}")


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


def _stand_schreiben(suche: su.Suche, letzte: list, grenze, instanz: str) -> None:
    """Kompakter Schnappschuss fuer `51_ausbruch_status.py`.

    Getrennt vom Checkpoint: Der Stand wird HAEUFIG geschrieben (jede
    Sekunde) und ist klein; der Checkpoint SELTENER (alle paar Minuten)
    und traegt den vollstaendigen Zustand zum Fortsetzen.
    """
    import json
    s = suche.stand
    z = suche.zustand()
    z["lernfenster_bis"] = str(grenze)
    z["schwelle"] = s.schwelle
    z["abstand"] = s.abstand
    z["phase_jetzt"] = s.phase
    z["letzte"] = [
        {"nr": v.nr, "phase": v.phase, "score": (None if v.score == float("-inf") else v.score),
         "besser": v.besser, "n_trades": v.kennzahlen.get("n_trades", 0)}
        for v in letzte[-12:]
    ]
    z["pid"] = None
    z["instanz"] = instanz
    pfad = _stand_datei(instanz)
    pfad.parent.mkdir(parents=True, exist_ok=True)
    tmp = pfad.with_suffix(".tmp")
    tmp.write_text(json.dumps(z, default=str, indent=2), encoding="utf-8")
    tmp.replace(pfad)


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--jahre", default=None)
    p.add_argument("--raster", default="15Min")
    p.add_argument("--symbole", type=int, default=None)
    p.add_argument("--score", default="t", choices=list(su.SCORES))
    p.add_argument("--min-trades", type=int, default=60)
    p.add_argument("--lernanteil", type=float, default=0.7)
    p.add_argument("--erkundung", type=int, default=60)
    p.add_argument("--fest", default="")
    p.add_argument("--saat", type=int, default=None)
    p.add_argument("--checkpoint-alle", type=int, default=200,
                   help="Checkpoint nach so vielen Versuchen sichern")
    p.add_argument("--elite-anteil", type=float, default=0.4,
                   help="Anteil der Neustarts, die beim gemeinsamen "
                        "Bestwert aller Instanzen ansetzen (0 = nie)")
    p.add_argument("--pruef-stichprobe", type=float, default=0.01,
                   help="Anteil der Versuche, fuer die das Prueffenster "
                        "zusaetzlich protokolliert wird - nur fuer die "
                        "spaetere Auswertung, nie zur Auswahl")
    p.add_argument("--instanz", default="a",
                   help="Kennung fuer PARALLELE Instanzen (a, b, c, ...) - "
                        "eigene Checkpoint-/Stand-Datei je Instanz, damit "
                        "sie sich nicht gegenseitig ueberschreiben. Der "
                        "gemeinsame Versuchszaehler in ausbruch.sqlite "
                        "zaehlt trotzdem ALLE Instanzen zusammen.")
    args = p.parse_args()

    checkpoint_pfad = _checkpoint_datei(args.instanz)

    jahre = (_jahre(args.jahre) if args.jahre
             else ausbruch_daten.jahre_vorhanden(args.raster))
    if not jahre:
        print("Kein Kursvorrat vorhanden.", flush=True)
        return 1

    fest: dict = {}
    for teil in filter(None, args.fest.split(",")):
        k, _, w = teil.partition("=")
        fest[k.strip()] = float(w.strip())

    print(f"[{time.strftime('%H:%M:%S')}] Vorrat laden ({jahre}) ...", flush=True)
    kd = ausbruch_daten.laden_kursdaten(
        jahre, raster=args.raster, max_symbole=args.symbole,
        fortschritt=lambda a, t: print(f"  {a*100:5.1f}% {t}", flush=True))
    print(f"[{time.strftime('%H:%M:%S')}] {len(kd.arrays):,} Symbole, "
          f"{kd.n_bars:,} Bars geladen", flush=True)

    lern, pruef, grenze = su.teilen(kd, args.lernanteil)
    protokoll = ausbruch_versuche.Protokoll(args.instanz)
    print(f"[{time.strftime('%H:%M:%S')}] [{args.instanz}] Protokoll: "
          f"{protokoll.anzahl():,} Versuche bereits gespeichert", flush=True)
    suche = su.Suche(lern, pruef, score=args.score, min_trades=args.min_trades,
                     fest=fest, erkundung_n=args.erkundung, saat=args.saat,
                     grenze=grenze, instanz=args.instanz,
                     elite_anteil=args.elite_anteil,
                     pruef_stichprobe=args.pruef_stichprobe,
                     protokoll=protokoll)

    # --- Checkpoint laden, falls vorhanden: FORTSETZEN statt neu ------
    z = su.Suche.laden_zustand(checkpoint_pfad)
    if z:
        suche.zustand_anwenden(z)
        print(f"[{time.strftime('%H:%M:%S')}] [{args.instanz}] Checkpoint "
              f"geladen - setze fort bei Versuch {suche.stand.versuche}, "
              f"gespeichert am {z.get('gespeichert_am', '?')}", flush=True)
    else:
        print(f"[{time.strftime('%H:%M:%S')}] [{args.instanz}] Kein "
              f"Checkpoint - starte bei Versuch 0", flush=True)

    lauf_id = ausbruch_store.neuer_lauf(
        {"dienst": True, "score": args.score, "jahre": jahre, "fest": fest,
         "lernanteil": args.lernanteil, "symbole": len(kd.arrays),
         "instanz": args.instanz},
        jahr=jahre[-1], raster=args.raster, n_symbole=len(kd.arrays),
        notiz=f"Dienst {jahre[0]}-{jahre[-1]} ({args.score}) [{args.instanz}]")

    signal.signal(signal.SIGINT, _stoppen)
    signal.signal(signal.SIGTERM, _stoppen)

    letzte: list = []
    letzter_checkpoint = suche.stand.versuche
    letztes_schreiben = 0.0

    for v in suche.laufen(lambda: _STOPP):
        letzte.append(v)
        letzte[:] = letzte[-40:]

        if time.time() - letztes_schreiben > 1.0:
            _stand_schreiben(suche, letzte, grenze, args.instanz)
            letztes_schreiben = time.time()

        if v.besser:
            print(f"[{time.strftime('%H:%M:%S')}] [{args.instanz}] Versuch "
                  f"{v.nr}: neuer Bester, score={v.score:.3f}, "
                  f"{v.kennzahlen.get('n_trades', 0)} Trades", flush=True)

        if suche.stand.versuche - letzter_checkpoint >= args.checkpoint_alle:
            protokoll.leeren()
            suche.speichern(checkpoint_pfad)
            letzter_checkpoint = suche.stand.versuche
            print(f"[{time.strftime('%H:%M:%S')}] [{args.instanz}] "
                  f"Checkpoint gesichert bei Versuch "
                  f"{suche.stand.versuche}", flush=True)

    # --- Sauberes Ende: letzten Checkpoint UND Stand schreiben --------
    protokoll.leeren()
    suche.speichern(checkpoint_pfad)
    _stand_schreiben(suche, letzte, grenze, args.instanz)
    ausbruch_store.abschliessen(lauf_id, {
        "dienst": True, "n_teilversuche": suche.stand.versuche,
        "beste_config": suche.stand.beste_config,
        "lern": suche.stand.beste_kennzahlen,
        "pruef": suche.stand.pruef_kennzahlen,
        "schwelle": suche.stand.schwelle,
    })
    ausbruch_store.suchversuche_buchen(lauf_id, suche.stand.versuche)
    grund = _GRUND or (
        f"Suchraum abgesucht (Phase '{suche.stand.phase}') - das Raster "
        f"ist zu klein oder zu viele Achsen sind mit --fest gebunden"
        if suche.stand.phase == "abgesucht" else "Generator kehrte zurueck")
    print(f"[{time.strftime('%H:%M:%S')}] [{args.instanz}] Beendet bei "
          f"Versuch {suche.stand.versuche}. GRUND: {grund}. "
          f"Checkpoint gesichert - naechster Start setzt hier fort.",
          flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
