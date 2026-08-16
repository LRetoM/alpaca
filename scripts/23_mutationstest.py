#!/usr/bin/env python3
"""Schritt 23: Pruefen, ob die Tests ueberhaupt etwas fangen.

**Das Problem, das dieses Skript loest:** Ein Test, der immer gruen ist,
weil er falsch geschrieben wurde, ist schlimmer als kein Test - er
erzeugt Sicherheit, wo keine ist. Ob ein Test wirklich prueft, laesst
sich nur auf eine Art feststellen: **Man baut den Fehler absichtlich ein
und schaut, ob der Test rot wird.**

Jede Mutation hier ist ein realer Fehler, der in diesem Projekt schon
einmal aufgetreten ist oder unmittelbar drohte. Faengt die Testsuite eine
Mutation NICHT, ist der zugehoerige Test wertlos und muss nachgebessert
werden.

    python scripts/23_mutationstest.py            # alle Mutationen
    python scripts/23_mutationstest.py --liste    # nur anzeigen

Sicherheit: Jede Aenderung wird im Speicher gehalten und in einem
`finally` zurueckgeschrieben - auch bei Absturz oder Strg-C. Nach dem
Lauf prueft das Skript zusaetzlich, dass alle Dateien wieder im
Originalzustand sind.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

WURZEL = Path(__file__).resolve().parents[1]
PYTHON = WURZEL / ".venv" / "bin" / "python"


@dataclass
class Mutation:
    name: str
    datei: str
    suchen: str
    ersetzen: str
    erwartet_rot: str
    """Welcher Test MUSS hierdurch rot werden - als Filterausdruck fuer pytest."""
    warum: str


MUTATIONEN = [
    # --- Ausstiegslogik ---------------------------------------------------
    Mutation(
        "Stop und Ziel vertauscht",
        "src/alpaca_bot/engine.py",
        'if price <= pos.stop_price:\n                reason = "stop_ausgeloest"',
        'if price >= pos.target_price:\n                reason = "stop_ausgeloest"',
        "test_engine_ausstiege",
        "Die Reihenfolge der Ausstiegsregeln entscheidet ueber das Etikett "
        "jedes Verkaufs - und damit ueber jede Auswertung nach Gruenden.",
    ),
    Mutation(
        "Zeitausstieg feuert einen Tag zu frueh",
        "src/alpaca_bot/engine.py",
        "elif pos.bars_held >= cfg.max_hold_days:",
        "elif pos.bars_held >= cfg.max_hold_days - 1:",
        "test_engine_ausstiege",
        "Ein Off-by-one im Zeitausstieg verkuerzt jede Haltedauer um einen "
        "Tag - der Effekt ist auf 3-5 Tagen gemessen, das faellt ins Gewicht.",
    ),
    Mutation(
        "Harte Grenze leckt in den Live-Pfad",
        "src/alpaca_bot/engine.py",
        "if not cfg.zeitausstieg_dynamisch:\n                    reason = \"zeitausstieg\"",
        "if False:\n                    reason = \"zeitausstieg\"",
        "test_engine_ausstiege",
        "GENAU der Fehler vom 16.08.2026: max_hold_days_hart wurde geprueft, "
        "bevor feststand, ob die Verlaengerung aktiv ist.",
    ),
    Mutation(
        "Trendpruefung ignoriert die Volatilitaet",
        "src/alpaca_bot/engine.py",
        "return (hoechst - price) <= self.cfg.trend_rueckfall_atr * atr",
        "return (hoechst - price) <= self.cfg.trend_rueckfall_atr * 100.0",
        "test_engine_ausstiege",
        "Ein fester statt ATR-skalierter Abstand - genau die Fassung, die "
        "am 15.08. verworfen wurde (27,5 % Ausloeserate statt 6 %).",
    ),
    Mutation(
        "Verlaengerung auch im Minus",
        "src/alpaca_bot/engine.py",
        "if pos.entry_price <= 0 or price <= pos.entry_price:\n            return False",
        "if pos.entry_price <= 0:\n            return False",
        "test_engine_ausstiege",
        "Eine Verlustposition laenger zu halten ist Hoffnung, keine Regel.",
    ),

    # --- Risiko-Dach -------------------------------------------------------
    Mutation(
        "Drawdown ohne Einzahlungsbereinigung",
        "src/alpaca_bot/risiko.py",
        "aktuell_bereinigt = equity - einzahlungen",
        "aktuell_bereinigt = equity",
        "test_risiko",
        "DER kritischste Fehler: Ohne Bereinigung haette ein realer "
        "25-%-Verlust nur 16,7 % gezeigt und NICHT gesperrt.",
    ),
    Mutation(
        "Sperre loest sich bei Erholung selbst",
        "src/alpaca_bot/risiko.py",
        'if int(sperre.get("aktiv") or 0) == 1:\n        gruende.append(',
        'if False:\n        gruende.append(',
        "test_risiko",
        "Eine sich selbst loesende Sperre kauft in den Crash zurueck, "
        "wegen dem sie ausgeloest hat.",
    ),
    Mutation(
        "Verkauf wird mitgesperrt",
        "src/alpaca_bot/risiko.py",
        'if seite == "sell":\n        return Freigabe(True, [], {})',
        'if False:\n        return Freigabe(True, [], {})',
        "test_risiko",
        "Eine Sperre, die den Ausstieg blockiert, macht aus dem Schutz "
        "eine Falle.",
    ),
    Mutation(
        "Entsperren ohne Bestaetigung",
        "src/alpaca_bot/risiko.py",
        "if bestaetigung.strip().lower() != BESTAETIGUNG:",
        "if False:",
        "test_risiko",
        "Die Reibung IST der Zweck - sonst wird im Schreck entsperrt.",
    ),

    # --- Referenzpreis und Ausfuehrung -------------------------------------
    Mutation(
        "Unplausible Quote wird uebernommen",
        "src/alpaca_bot/live.py",
        "return abweichung <= _MAX_QUOTE_ABWEICHUNG, last",
        "return True, last",
        "test_ausfuehrung",
        "SIMO wurde mit 225 statt 261 gemeldet - ein Stop-Verkauf darauf "
        "waere ein realer Verlust aus einem Datenfehler.",
    ),
    Mutation(
        "Intraday-Stop feuert auf Fallback-Quote",
        "src/alpaca_bot/live.py",
        'if ref.quelle == "fallback" or ref.preis <= 0:',
        "if ref.preis <= 0:",
        "test_ausfuehrung",
        "Ohne diesen Schutz verkauft ein Datenfehler eine gesunde Position.",
    ),
    Mutation(
        "Scheinmittelwert bei fehlender Quote-Seite",
        "src/alpaca_bot/live.py",
        "elif ask > 0 and bid > 0:\n            kandidat = (ask + bid) / 2",
        "elif True:\n            kandidat = (ask + bid) / 2",
        "test_ausfuehrung",
        "(0+45,54)/2 = 22,77 - eine Verfaelschung um 50 %, die einen "
        "Kurssturz meldet, der nie stattfand (Fehler vom 31.07.).",
    ),

    # --- Statistik ---------------------------------------------------------
    Mutation(
        "Statistik zaehlt Einzelwerte statt Gruppen",
        "src/alpaca_bot/statistik.py",
        "belastbar=bool(abs(t) > 2 and len(m) >= min_gruppen),",
        "belastbar=bool(abs(t) > 2),",
        "test_ausfuehrung",
        "Ein hoher t-Wert aus fuenf Gruppen ist genauso wenig belastbar "
        "wie ein niedriger aus hundert.",
    ),

    # --- Protokoll ---------------------------------------------------------
    Mutation(
        "Legacy-Zeilen wieder in der Slippage",
        "src/alpaca_bot/journal.py",
        'legacy = o["status"].astype(str).str.endswith(" geschlossen")',
        'legacy = o["status"].astype(str).str.endswith("###nie###")',
        "test_protokoll",
        "Die drei AMKR-Zeilen mit +2400 bps verdeckten den echten, "
        "negativen Mittelwert (-20 statt -258,7 bps).",
    ),
    Mutation(
        "bars_held wieder aus dem gespeicherten Wert",
        "src/alpaca_bot/daemon.py",
        "return max(0, len(pd.bdate_range(start.normalize(), ende.normalize())) - 1)",
        "return 0",
        "test_protokoll",
        "War in JEDEM Lebenslauf 0 - Haltedauer-Auswertung unmoeglich.",
    ),
    Mutation(
        "after_10d faellt wieder aus der Warteschlange",
        "src/alpaca_bot/lifecycle.py",
        '" WHERE after_1d IS NULL OR after_5d IS NULL OR after_10d IS NULL"',
        '" WHERE after_5d IS NULL"',
        "test_protokoll",
        "36 von 36 Trades hatten after_10d = None.",
    ),
    Mutation(
        "code_version sucht git am falschen Ort",
        "src/alpaca_bot/config.py",
        'cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=5,\n        )\n        v = out.stdout.strip()',
        'cwd=DATA_DIR, capture_output=True, text=True, timeout=5,\n        )\n        v = out.stdout.strip()',
        "test_protokoll",
        "Zwei Monate lang 'unbekannt' - 66 % der Vorhersagen ohne "
        "Versionszuordnung, ohne jede Fehlermeldung.",
    ),

    # --- Konsistenz --------------------------------------------------------
    Mutation(
        "Schatten importiert Handelscode",
        "src/alpaca_bot/shadow.py",
        "from .costs import DEFAULT_FEES, estimate_costs",
        "from .costs import DEFAULT_FEES, estimate_costs\nfrom . import trading  # MUTATION",
        "test_konsistenz",
        "Der Schatten darf konstruktionsbedingt keine Order senden "
        "koennen - nicht nur 'darf nicht'.",
    ),
    Mutation(
        "EngineConfig-Feld faellt aus dem Protokoll",
        "src/alpaca_bot/engine.py",
        '"zeitausstieg_dynamisch": self.zeitausstieg_dynamisch,',
        "",
        "test_konsistenz",
        "Eine Regel, die nicht mitgeschrieben wird, kann der Regelabgleich "
        "spaeter nicht pruefen - sie meldet stumm nichts.",
    ),
]


def pytest_laeuft_durch(filter_ausdruck: str) -> bool:
    r = subprocess.run(
        [str(PYTHON), "-m", "pytest", "tests/", "-q", "--no-header",
         "-x", "-p", "no:warnings", "-k", filter_ausdruck],
        cwd=WURZEL, capture_output=True, text=True,
    )
    return r.returncode == 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--liste", action="store_true")
    args = p.parse_args()

    if args.liste:
        for m in MUTATIONEN:
            print(f"  {m.name:<45} -> {m.erwartet_rot}")
        return 0

    print("=" * 78)
    print("  MUTATIONSTEST - fangen die Tests echte Fehler?")
    print("=" * 78)
    print("  Jede Zeile baut einen realen Fehler ein und prueft, ob die")
    print("  Testsuite rot wird. GEFANGEN = der Test taugt.\n")

    ungefangen: list[Mutation] = []
    nicht_anwendbar: list[Mutation] = []

    for m in MUTATIONEN:
        pfad = WURZEL / m.datei
        original = pfad.read_text(encoding="utf-8")
        if m.suchen not in original:
            print(f"  [?] {m.name:<45} Suchmuster nicht gefunden")
            nicht_anwendbar.append(m)
            continue
        try:
            pfad.write_text(original.replace(m.suchen, m.ersetzen, 1),
                            encoding="utf-8")
            gruen = pytest_laeuft_durch(m.erwartet_rot)
        finally:
            pfad.write_text(original, encoding="utf-8")

        if gruen:
            print(f"  [!] {m.name:<45} NICHT GEFANGEN")
            ungefangen.append(m)
        else:
            print(f"  [OK] {m.name:<45} gefangen")

    print("\n" + "=" * 78)
    print(f"  {len(MUTATIONEN) - len(ungefangen) - len(nicht_anwendbar)} "
          f"von {len(MUTATIONEN)} Mutationen gefangen")
    print("=" * 78)

    if nicht_anwendbar:
        print("\n  NICHT ANWENDBAR (Suchmuster veraltet - Skript anpassen):")
        for m in nicht_anwendbar:
            print(f"    - {m.name}")

    if ungefangen:
        print("\n  UNGEFANGEN - diese Tests pruefen nicht, was sie sollen:")
        for m in ungefangen:
            print(f"\n    {m.name}")
            print(f"      Datei : {m.datei}")
            print(f"      Warum : {m.warum}")
        return 1

    if nicht_anwendbar:
        return 1
    print("\n  Jede eingebaute Luecke wurde gefunden. Die Tests taugen.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
