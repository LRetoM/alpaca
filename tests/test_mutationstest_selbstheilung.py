"""Der Mutationstest heilt eine haengengebliebene Mutation selbst (§G46).

**Der Vorfall (27.08.2026).** `finally: pfad.write_text(original, ...)`
schuetzt gegen normale Exceptions und Strg-C - nicht gegen SIGKILL. Ein
Mutationstest-Lauf endete mit Exit-Code 137 (SIGKILL), waehrend die
Mutation "Limitkauf zahlt wieder den Spread" auf der Platte lag.
`_kaufkosten` in `simulate.py` blieb Stunden mutiert und bezahlte fuer
Limitorders erneut den vollen Spread - genau die Rechnung, deren
Wegfall §G34 belegt. Aufgefallen ist es durch Zufall bei einer
Routineabfrage, nicht durch eine Pruefung.

Diese Datei testet die Reparatur, nicht die einzelnen Mutationen -
dafuer gibt es `23_mutationstest.py --liste` und den Lauf selbst.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))
mut = importlib.import_module("23_mutationstest")


@pytest.fixture
def eine_mutation():
    """Die erste Mutation aus der echten Liste - kein Fantasiebeispiel."""
    return mut.MUTATIONEN[0]


def test_haengende_mutation_wird_erkannt_und_repariert(eine_mutation, tmp_path, monkeypatch):
    """Der eigentliche Vorfall nachgestellt: eine Datei liegt mit der
    MUTIERTEN Version auf der Platte, ohne dass ein Prozess mehr laeuft."""
    ziel = tmp_path / "betroffen.py"
    ziel.write_text(f"vorher\n{eine_mutation.ersetzen}\nnachher\n", encoding="utf-8")

    monkeypatch.setattr(mut, "WURZEL", tmp_path)
    monkeypatch.setattr(mut, "MUTATIONEN", [
        mut.Mutation(eine_mutation.name, "betroffen.py",
                    eine_mutation.suchen, eine_mutation.ersetzen,
                    eine_mutation.erwartet_rot, eine_mutation.warum)
    ])

    repariert = mut._pruefe_unversehrt()

    assert repariert == [eine_mutation.name]
    assert eine_mutation.suchen in ziel.read_text(encoding="utf-8")
    assert eine_mutation.ersetzen not in ziel.read_text(encoding="utf-8")


def test_saubere_datei_bleibt_unangetastet(eine_mutation, tmp_path, monkeypatch):
    """Der Regelfall: nichts haengt, nichts wird gemeldet."""
    ziel = tmp_path / "sauber.py"
    inhalt = f"vorher\n{eine_mutation.suchen}\nnachher\n"
    ziel.write_text(inhalt, encoding="utf-8")

    monkeypatch.setattr(mut, "WURZEL", tmp_path)
    monkeypatch.setattr(mut, "MUTATIONEN", [
        mut.Mutation(eine_mutation.name, "sauber.py",
                    eine_mutation.suchen, eine_mutation.ersetzen,
                    eine_mutation.erwartet_rot, eine_mutation.warum)
    ])

    assert mut._pruefe_unversehrt() == []
    assert ziel.read_text(encoding="utf-8") == inhalt


def test_das_reale_simulate_py_ist_gerade_sauber():
    """Regressionsanker fuer den konkreten Vorfall: `_kaufkosten` in
    `simulate.py` MUSS die Nullen fuer Limitorders wieder haben. Waere
    die Datei heute Nacht nicht zufaellig aufgefallen, haette dieser
    Test den Zustand als einziger sichtbar gemacht."""
    assert mut._pruefe_unversehrt() == []
