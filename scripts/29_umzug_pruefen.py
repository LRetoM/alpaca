#!/usr/bin/env python3
"""Beweist, dass die Aufteilung von `shadow.py` das Verhalten nicht aendert.

**Warum es dieses Skript gibt (23.08.2026, BEFUNDE §G20).** `shadow.py`
wurde in fuenf Module aufgeteilt, waehrend die Flottenmessung fuer den
Entscheidungstermin am 10.10.2026 laeuft. `CLAUDE.md` verbietet, eine
laufende Messung durch eine Aenderung an der Handelslogik zu
unterbrechen - ein reiner Umzug ist keine solche Aenderung, aber das ist
eine BEHAUPTUNG, und dieses Projekt hat mit Behauptungen schlechte
Erfahrungen gemacht (§G17: "der Modul-Docstring behauptet ... Das war
eine Behauptung").

Die Testsuite reicht als Nachweis nicht aus. Sie zeigt, dass die
geprueften Faelle weiter stimmen - nicht, dass NICHTS anderes sich
geaendert hat. Der Unterschied ist genau der, an dem dieses Projekt
schon mehrfach gescheitert ist.

**Was hier stattdessen verglichen wird: der Bytecode.** Fuer jede
verschobene Funktion werden die Anweisungen des uebersetzten Code-Objekts
gegen den Stand vor dem Umzug gestellt:

    co_code       die Anweisungsfolge selbst
    co_consts     alle Konstanten (rekursiv, auch verschachtelte Funktionen)
    co_names      die benutzten globalen Namen
    co_varnames   lokale Variablen in ihrer Reihenfolge

Gleicher Bytecode bei gleichen Namen heisst: Die Funktion tut dasselbe.
Das ist ein staerkerer Nachweis als jeder Test, weil er nicht von der
Auswahl der Testfaelle abhaengt.

**`co_names` ist der eigentliche Wachhund.** Ein Modulwechsel aendert,
WOHER ein globaler Name kommt. Waere beim Umzug ein Import vergessen
oder ein Name still auf etwas anderes gefallen, stuende das dort - und
nur dort, im Bytecode faellt es sonst nirgends auf.

    python scripts/29_umzug_pruefen.py <vorher.py>

`vorher.py` ist der Stand von `shadow.py` vor dem Umzug. Aus dem Git-Baum:

    git show <commit>:src/alpaca_bot/shadow.py > /tmp/vorher.py
"""

from __future__ import annotations

import argparse
import importlib
import importlib.util
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

MODULE_NACHHER = [
    "alpaca_bot.shadow_config",
    "alpaca_bot.shadow_store",
    "alpaca_bot.shadow_daten",
    "alpaca_bot.shadow_schritte",
    "alpaca_bot.shadow_pruefung",
]


def _lade_alt(pfad: Path) -> types.ModuleType:
    """Laedt den alten Stand als eigenes Modul, ohne den neuen zu stoeren.

    Der Name ist bewusst `alpaca_bot.shadow_vorher`: Die relativen Importe
    darin (`from .engine import ...`) brauchen ein Paket als Elternteil,
    sonst scheitert der Import mit `ImportError: attempted relative import`.
    """
    importlib.import_module("alpaca_bot")
    spec = importlib.util.spec_from_file_location("alpaca_bot.shadow_vorher", pfad)
    modul = importlib.util.module_from_spec(spec)
    sys.modules["alpaca_bot.shadow_vorher"] = modul
    spec.loader.exec_module(modul)
    return modul


def _codeobjekte(modul: types.ModuleType, praefix: str = "") -> dict:
    """Alle Funktionen und Methoden eines Moduls als {Name: Code-Objekt}."""
    out = {}
    for name, obj in vars(modul).items():
        if name.startswith("__"):
            continue
        if isinstance(obj, types.FunctionType) and obj.__module__ == modul.__name__:
            out[praefix + name] = obj.__code__
        elif isinstance(obj, type) and obj.__module__ == modul.__name__:
            for mname, m in vars(obj).items():
                fn = m.__func__ if isinstance(m, (classmethod, staticmethod)) else m
                if isinstance(fn, types.FunctionType):
                    out[f"{praefix}{name}.{mname}"] = fn.__code__
    return out


def _konstanten(code) -> tuple:
    """Konstanten rekursiv - verschachtelte Funktionen zaehlen mit.

    Ohne die Rekursion bliebe der Rumpf jeder inneren Funktion (etwa
    `default()` in `_json` oder die Hilfsfunktionen in `_spiegel`)
    ungeprueft: Aussen steht dann nur ein Code-Objekt, dessen
    Vergleich immer 'ungleich' ergibt und deshalb geglaettet werden
    muesste. Ausgerechnet die inneren Funktionen tragen aber Logik.
    """
    out = []
    for k in code.co_consts:
        if hasattr(k, "co_code"):
            out.append(("<code>", k.co_name, k.co_code, _konstanten(k)))
        else:
            out.append(k)
    return tuple(out)


def _steckbrief(code) -> tuple:
    return (code.co_code, _konstanten(code), code.co_names, code.co_varnames,
            code.co_argcount, code.co_kwonlyargcount, code.co_flags)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("vorher", type=Path, help="shadow.py vor dem Umzug")
    args = p.parse_args()

    if not args.vorher.exists():
        print(f"  {args.vorher} gibt es nicht.")
        return 1

    alt = _codeobjekte(_lade_alt(args.vorher))
    neu: dict = {}
    herkunft: dict = {}
    for name in MODULE_NACHHER:
        m = importlib.import_module(name)
        for k, v in _codeobjekte(m).items():
            neu[k] = v
            herkunft[k] = name.split(".")[-1]

    print("=" * 78)
    print("  UMZUGSPRUEFUNG: gleicher Bytecode = gleiches Verhalten")
    print("=" * 78)
    print(f"  vorher : {args.vorher}  ({len(alt)} Funktionen)")
    print(f"  nachher: {len(MODULE_NACHHER)} Module        ({len(neu)} Funktionen)")
    print()

    fehlend = sorted(set(alt) - set(neu))
    neu_dazu = sorted(set(neu) - set(alt))
    gleich, abweichend = [], []
    for name in sorted(set(alt) & set(neu)):
        (gleich if _steckbrief(alt[name]) == _steckbrief(neu[name])
         else abweichend).append(name)

    print(f"  bytegleich  : {len(gleich)}")
    print(f"  abweichend  : {len(abweichend)}")
    print(f"  verschwunden: {len(fehlend)}")
    print(f"  neu         : {len(neu_dazu)}")

    if fehlend:
        print("\n  VERSCHWUNDEN - beim Umzug verloren gegangen:")
        for n in fehlend:
            print(f"    {n}")
    if neu_dazu:
        print("\n  NEU - beim Umzug entstanden (bei einem reinen Umzug: keine):")
        for n in neu_dazu:
            print(f"    {n}")
    if abweichend:
        print("\n  ABWEICHEND - hier wurde beim Umzug doch etwas geaendert:")
        for n in abweichend:
            a, b = alt[n], neu[n]
            print(f"\n    {n}  ({herkunft.get(n, '?')})")
            if a.co_code != b.co_code:
                print("      Anweisungsfolge unterscheidet sich")
            if _konstanten(a) != _konstanten(b):
                print("      Konstanten unterscheiden sich")
            if a.co_names != b.co_names:
                fehlt = set(a.co_names) - set(b.co_names)
                extra = set(b.co_names) - set(a.co_names)
                print(f"      globale Namen: -{sorted(fehlt)} +{sorted(extra)}")
            if a.co_varnames != b.co_varnames:
                print("      lokale Variablen unterscheiden sich")

    print("\n" + "=" * 78)
    if abweichend or fehlend or neu_dazu:
        print("  KEIN REINER UMZUG - die Abweichungen oben klaeren, bevor")
        print("  die Dienste neu starten. Eine laufende Messung vertraegt")
        print("  keine unbeabsichtigte Verhaltensaenderung (CLAUDE.md).")
        return 1
    print(f"  {len(gleich)} von {len(gleich)} Funktionen bytegleich.")
    print("  Der Umzug hat nichts am Verhalten geaendert.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
