#!/usr/bin/env python3
"""Schritt 47: Automatische Suche nach guten Ausbruch-Konfigurationen.

    python scripts/47_ausbruch_suche.py                  # los, Strg+C beendet
    python scripts/47_ausbruch_suche.py --symbole 200    # schneller, grober
    python scripts/47_ausbruch_suche.py --score calmar
    python scripts/47_ausbruch_suche.py --fest halten_bars=26,gewinn_pct=10

Probiert Kombinationen durch, merkt sich die beste, sucht von dort
weiter - Erkundung, Bergsteigen, Neustart im Wechsel. Laeuft, bis du
Strg+C drueckst, und gibt dann das beste Ergebnis aus.

**Die Zahl, auf die es ankommt, steht rechts, nicht links.** Links das
Lernfenster, auf dem optimiert wird - dort findet eine lange Suche
immer etwas Gutes, auch auf reinem Rauschen. Rechts das Prueffenster,
das die Suche nie zur Auswahl benutzt. Nur wenn es dort traegt, ist
ueberhaupt etwas da.

Alles Weitere: `docs/AUSBRUCH.md` §5 und `alpaca_bot.ausbruch_suche`.
"""

from __future__ import annotations

import argparse
import os
import shutil
import signal
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from alpaca_bot import ausbruch, ausbruch_daten, ausbruch_store  # noqa: E402
from alpaca_bot import ausbruch_suche as su  # noqa: E402

# ANSI - keine Abhaengigkeit fuer etwas, das acht Zeichen braucht.
CSI = "\033["
AUS, FETT, MATT = f"{CSI}0m", f"{CSI}1m", f"{CSI}2m"
ROT, GRUEN, GELB, BLAU, GRAU = (f"{CSI}31m", f"{CSI}32m", f"{CSI}33m",
                                f"{CSI}36m", f"{CSI}90m")
LEEREN, HOCH = f"{CSI}2J{CSI}H", f"{CSI}H"

_STOPP = False


def _stoppen(*_a) -> None:
    global _STOPP
    if _STOPP:                      # zweites Strg+C: sofort raus
        print("\n  Abbruch.")
        raise SystemExit(130)
    _STOPP = True
    print(f"\n{GELB}  Halte an - der laufende Versuch wird noch "
          f"zu Ende gerechnet ...{AUS}", flush=True)


def _farbe(wert: float, schwelle: float = 0.0) -> str:
    if wert != wert or wert == float("-inf"):
        return GRAU
    return GRUEN if wert > schwelle else (GELB if wert > 0 else ROT)


def _kurz(cfg: dict, nur: list[str] | None = None) -> str:
    """Konfiguration in einer Zeile. Nur die Achsen, die Platz haben."""
    teile = []
    for k, v in cfg.items():
        if nur and k not in nur:
            continue
        name = k.replace("_pct", "").replace("_bars", "").replace("_", "")[:9]
        if isinstance(v, bool):
            wert = "ja" if v else "nein"
        elif isinstance(v, float) and v >= 1e5:
            wert = f"{v:.0e}"
        else:
            wert = f"{v:g}" if isinstance(v, (int, float)) else str(v)
        teile.append(f"{name}={wert}")
    return " ".join(teile)


def anzeigen(suche: su.Suche, letzte: list, breite: int) -> None:
    """Zeichnet das Bild neu. Bewusst vollstaendig statt scrollend -
    ein weglaufendes Protokoll ist bei 700 Versuchen die Stunde
    unlesbar."""
    s = suche.stand
    laufzeit = time.time() - s.start
    tempo = s.versuche / laufzeit * 60 if laufzeit > 1 else 0.0
    lt = s.beste_kennzahlen.get("t_wert")
    pt = s.pruef_kennzahlen.get("t_wert")

    Z = [HOCH]
    Z.append(f"{FETT}{BLAU}  AUSBRUCH-SUCHE{AUS}"
             f"{GRAU}   Strg+C beendet und gibt das Beste aus{AUS}"
             f"{CSI}K")
    Z.append(f"{GRAU}  {'─' * (breite - 4)}{AUS}{CSI}K")

    Z.append(f"  {s.versuche:>5} Versuche   {tempo:>5.1f}/Min   "
             f"{laufzeit / 60:>5.1f} Min   "
             f"Phase {FETT}{s.phase:<12}{AUS}"
             f"Neustarts {s.neustarts}{CSI}K")
    Z.append(f"  Zufallsschwelle bei {s.versuche} Versuchen: "
             f"{FETT}t > {s.schwelle:.2f}{AUS}   "
             f"{GRAU}steigt mit jedem weiteren Versuch{AUS}{CSI}K")
    Z.append(f"{CSI}K")

    # --- Die beiden Fenster nebeneinander ---
    Z.append(f"{FETT}  LERNFENSTER{AUS} {GRAU}(hier wird optimiert){AUS}"
             f"          {FETT}PRUEFFENSTER{AUS} "
             f"{GRAU}(nie zur Auswahl benutzt){AUS}{CSI}K")
    if s.beste_config:
        bk, pk = s.beste_kennzahlen, s.pruef_kennzahlen
        def _p(d, f, n=2, s_=""):
            v = d.get(f)
            return "–" if v is None or v != v else f"{v:.{n}f}{s_}"
        zeilen = [
            ("t-Wert", f"{_farbe(lt or 0, s.schwelle)}{_p(bk,'t_wert')}{AUS}",
                       f"{_farbe(pt or 0, s.schwelle)}{_p(pk,'t_wert')}{AUS}"),
            ("Rendite", _p(bk, "rendite_pct", 2, " %"), _p(pk, "rendite_pct", 2, " %")),
            ("je Trade", _p(bk, "mittel_pct", 3, " %"), _p(pk, "mittel_pct", 3, " %")),
            ("Trades", _p(bk, "n_trades", 0), _p(pk, "n_trades", 0)),
            ("Handelstage", _p(bk, "n_handelstage", 0), _p(pk, "n_handelstage", 0)),
            ("max. Rueckgang", _p(bk, "max_drawdown_pct", 1, " %"),
                               _p(pk, "max_drawdown_pct", 1, " %")),
        ]
        for name, a, b in zeilen:
            Z.append(f"    {name:<16}{a:>22}        {b:>22}{CSI}K")
        ab = s.abstand
        if ab is not None:
            warn = ROT if ab > 1.5 else (GELB if ab > 0.7 else GRUEN)
            Z.append(f"    {'Abstand':<16}{warn}{ab:>+22.2f}{AUS}"
                     f"        {GRAU}gross = an den Lernzeitraum angepasst{AUS}"
                     f"{CSI}K")
    else:
        Z.append(f"    {GRAU}Noch keine Konfiguration mit genug Trades.{AUS}{CSI}K")
    Z.append(f"{CSI}K")

    # --- Aktuell bester Punkt ---
    Z.append(f"{FETT}  BESTE KONFIGURATION{AUS}{CSI}K")
    if s.beste_config:
        posten = list(s.beste_config.items())
        for i in range(0, len(posten), 3):
            Z.append("    " + _kurz(dict(posten[i:i + 3])) + f"{CSI}K")
    Z.append(f"{CSI}K")

    # --- Die letzten Versuche ---
    Z.append(f"{FETT}  LETZTE VERSUCHE{AUS}"
             f"{GRAU}   ★ = neuer Bester{AUS}{CSI}K")
    for v in letzte[-12:]:
        marke = f"{GRUEN}★{AUS}" if v.besser else " "
        sc = (f"{GRAU}   –  {AUS}" if v.score == float("-inf")
              else f"{_farbe(v.score, s.schwelle)}{v.score:>6.2f}{AUS}")
        n = v.kennzahlen.get("n_trades", 0)
        rest = breite - 44
        Z.append(f"  {marke} {GRAU}{v.nr:>5}{AUS} {v.phase[:4]:<5}{sc}"
                 f" {GRAU}{n:>4}T{AUS}  "
                 f"{MATT}{_kurz(v.config)[:max(rest, 10)]}{AUS}{CSI}K")
    Z.append(f"{CSI}K")
    Z.append(f"{GRAU}  Lernfenster bis {suche.grenze:%d.%m.%Y}  |  "
             f"{len(suche.lern)} Symbole  |  Score: {suche.score_name}  |  "
             f"min. {suche.min_trades} Trades{AUS}{CSI}K")
    Z.append(f"{CSI}J")
    sys.stdout.write("\n".join(Z))
    sys.stdout.flush()


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--jahr", type=int, default=2025)
    p.add_argument("--raster", default="15Min")
    p.add_argument("--symbole", type=int, default=None,
                   help="nur die ersten N - macht jeden Versuch schneller")
    p.add_argument("--score", default="t", choices=list(su.SCORES),
                   help="worauf optimiert wird (Vorgabe: gruppierter t-Wert)")
    p.add_argument("--min-trades", type=int, default=40)
    p.add_argument("--lernanteil", type=float, default=0.7,
                   help="Anteil des Jahres zum Optimieren (Rest ist Pruefung)")
    p.add_argument("--erkundung", type=int, default=25,
                   help="Zufallspunkte, bevor das Bergsteigen beginnt")
    p.add_argument("--fest", default="",
                   help="Achsen festhalten, z.B. halten_bars=26,gewinn_pct=10")
    p.add_argument("--saat", type=int, default=None,
                   help="Zufallssaat - macht einen Lauf wiederholbar")
    args = p.parse_args()

    fest: dict = {}
    for teil in filter(None, args.fest.split(",")):
        k, _, w = teil.partition("=")
        k, w = k.strip(), w.strip()
        if k not in ausbruch.AusbruchConfig().als_dict():
            print(f"Unbekannte Achse: {k}")
            return 1
        fest[k] = (w.lower() in ("true", "ja", "1")
                   if w.lower() in ("true", "false", "ja", "nein", "0", "1")
                   and k.startswith(("zeitausstieg", "ueber"))
                   else float(w))

    print("Vorrat laden ...", flush=True)
    bars = ausbruch_daten.laden(jahr=args.jahr, raster=args.raster,
                                max_symbole=args.symbole)
    lern, pruef, grenze = su.teilen(bars, args.lernanteil)
    print(f"  {len(bars)} Symbole. Lernfenster bis {grenze:%d.%m.%Y}, "
          f"Prueffenster danach.", flush=True)

    suche = su.Suche(lern, pruef, score=args.score, min_trades=args.min_trades,
                     fest=fest, erkundung_n=args.erkundung, saat=args.saat,
                     grenze=grenze)

    lauf_id = ausbruch_store.neuer_lauf(
        {"suche": True, "score": args.score, "fest": fest,
         "lernanteil": args.lernanteil, "symbole": len(bars)},
        jahr=args.jahr, raster=args.raster, n_symbole=len(bars),
        notiz=f"Suche ({args.score})")

    signal.signal(signal.SIGINT, _stoppen)
    breite = shutil.get_terminal_size((110, 40)).columns
    letzte: list = []
    sys.stdout.write(LEEREN)

    for v in suche.laufen(lambda: _STOPP):
        letzte.append(v)
        letzte[:] = letzte[-40:]
        anzeigen(suche, letzte, breite)

    # --- Abschluss ---------------------------------------------------
    sys.stdout.write(f"{CSI}0m\n\n")
    print("=" * 74)
    print("  ERGEBNIS DER SUCHE")
    print("=" * 74)
    print(suche.bericht())

    if suche.stand.beste_config:
        print("\n  Beste Konfiguration:")
        for k, w in sorted(suche.stand.beste_config.items()):
            print(f"    {k:<32} {w}")
        print("\n  In der Werkstatt nachstellen: "
              "python scripts/46_ausbruch.py")

    ausbruch_store.abschliessen(lauf_id, {
        "suche": True,
        "n_teilversuche": suche.stand.versuche,
        "beste_config": suche.stand.beste_config,
        "lern": suche.stand.beste_kennzahlen,
        "pruef": suche.stand.pruef_kennzahlen,
        "schwelle": suche.stand.schwelle,
    })
    ausbruch_store.suchversuche_buchen(lauf_id, suche.stand.versuche)
    print(f"\n  Gespeichert als Lauf {lauf_id}. "
          f"{suche.stand.versuche} Teilversuche im Zaehler.")
    print(f"  Versuche gesamt jetzt: {ausbruch_store.n_versuche()}  "
          f"(Schwelle t > {ausbruch_store.schwelle_sigma():.2f})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
