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
        "belastbar=bool(abs(massgeblich) > 2 and len(m) >= min_gruppen),",
        "belastbar=bool(abs(massgeblich) > 2),",
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

    # --- Ueberlappung zwischen den Handelstagen (§G12) ---------------------
    Mutation(
        "Ueberlappungskorrektur abgeschaltet",
        "src/alpaca_bot/statistik.py",
        "        t_ueber, aufbl = newey_west_t(m.to_numpy(), lag=horizont - 1)",
        "        t_ueber, aufbl = t, 1.0",
        "test_statistik_ueberlappung",
        "Genau der Zustand vor dem 22.08.2026: der t-Wert faellt um bis zu "
        "1,8x zu hoch aus, und 6 von 10 Faktoren waeren Fehlbefunde.",
    ),
    Mutation(
        "Urteil haengt am rohen statt am korrigierten t-Wert",
        "src/alpaca_bot/statistik.py",
        "    massgeblich = t_ueber if np.isfinite(t_ueber) else t",
        "    massgeblich = t",
        "test_statistik_ueberlappung",
        "Die gefaehrlichste Teilreparatur: die Korrektur wird gerechnet und "
        "sogar ausgegeben, aber das Urteil 'belastbar' ignoriert sie.",
    ),
    Mutation(
        "Gruppenmittel vor der Korrektur nicht sortiert",
        "src/alpaca_bot/statistik.py",
        "    m = m.sort_index()",
        "    m = m",
        "test_statistik_ueberlappung",
        "Newey-West liest die Autokorrelation aus der Reihenfolge. Unsortiert "
        "verschwindet sie stillschweigend - die Korrektur waere folgenlos.",
    ),
    Mutation(
        "Faktorauswahl prueft wieder den rohen t-Wert",
        "src/alpaca_bot/research.py",
        '    t = sub["t_korrigiert"].fillna(sub["t_stat"]) if "t_korrigiert" in sub else sub["t_stat"]',
        '    t = sub["t_stat"]',
        "test_statistik_ueberlappung",
        "Die Stelle, an der aus einer Messung eine Strategie wird - hier hat "
        "der unkorrigierte Wert die tragenden Faktoren durchgelassen.",
    ),
    Mutation(
        "Bartlett-Gewichte durch volle Gewichte ersetzt",
        "src/alpaca_bot/statistik.py",
        "        s += 2.0 * (1.0 - k / (lag + 1.0)) * gk",
        "        s += 2.0 * gk",
        "test_statistik_ueberlappung",
        "Ohne den auslaufenden Kern ist die geschaetzte Varianz nicht mehr "
        "garantiert positiv - der Schaetzer kippt bei negativer Autokorrelation.",
    ),

    # --- Datenklarheit: stumme Felder und vermischte Quellen (§G13) --------
    Mutation(
        "decision_quality mischt Simulation wieder mit ein",
        "src/alpaca_bot/journal.py",
        'script: str | None = "live_trade") -> pd.DataFrame:',
        "script: str | None = None) -> pd.DataFrame:",
        "test_datenklarheit",
        "Im Live-Journal stehen 304 echte gegen 18.118 Simulationszeilen. "
        "Ohne die Vorgabe beschreibt die Kennzahl den Backtest.",
    ),
    Mutation(
        "Feld-Waechter prueft wieder die ganze Historie",
        "src/alpaca_bot/data_integrity.py",
        "                        fenster: int = 400, juengste: int = 20) -> None:",
        "                        fenster: int = 400, juengste: int = 400) -> None:",
        "test_datenklarheit",
        "Ein grosses Fenster reicht ueber den Einfuehrungstag eines Feldes "
        "zurueck und meldet die Einfuehrung als Ausfall - Dauergelb.",
    ),
    Mutation(
        "Feld-Waechter zaehlt Simulationszeilen mit",
        "src/alpaca_bot/data_integrity.py",
        "            \" WHERE r.script = 'live_trade'\"\n            \" ORDER BY d.ts DESC LIMIT ?\",",
        "            \" ORDER BY d.ts DESC LIMIT ?\",",
        "test_datenklarheit",
        "Simulationslaeufe fuehren die Kontextfelder nicht und stellten "
        "98,4 % der Tabelle - sie melden einen Ausfall, den es nicht gibt.",
    ),
    Mutation(
        "bars_held wird nicht gegen die Daten geprueft",
        "src/alpaca_bot/data_integrity.py",
        "    falsch = f[abweichung > 1]",
        "    falsch = f[abweichung > 9999]",
        "test_datenklarheit",
        "36 von 56 Trades trugen eine falsche 0. Eine falsche Zahl ist "
        "schlimmer als eine fehlende - sie geht in jeden Mittelwert ein.",
    ),

    Mutation(
        "Nachkauf verliert den Auswertungskontext",
        "src/alpaca_bot/engine.py",
        '            self._mit_kontext(gruende, snapshot, sym)',
        "            pass",
        "test_datenklarheit",
        "topup ist die Mehrheit der Kapitalzuteilung (110 von 304). Ohne "
        "Kontext uebersieht die Sektorauswertung den groesseren Teil.",
    ),

    # --- Dauerbetrieb und Lernschleife (§G14) -----------------------------
    Mutation(
        "IC rechnet wieder ohne Ueberlappungskorrektur",
        "src/alpaca_bot/shadow_eval.py",
        "        t_korr, aufbl = statistik.newey_west_t(tages_ic.to_numpy(), lag=h - 1)",
        "        t_korr, aufbl = float(t_roh), 1.0",
        "test_dauerbetrieb",
        "Das ist die Kennzahl, nach der die Flotte beurteilt wird. "
        "Unkorrigiert faellt sie systematisch zu hoch aus (§G12).",
    ),
    Mutation(
        "Entarteter Schaetzer liefert wieder eine Zahl",
        "src/alpaca_bot/statistik.py",
        "    if n < 3 * (lag + 1):\n        return float(\"nan\"), float(\"nan\")",
        "    if n < 0:\n        return float(\"nan\"), float(\"nan\")",
        "test_dauerbetrieb",
        "Bei 8 Tagen und 10-Tage-Horizont machte der Schaetzer aus t=5,30 "
        "ein t=14,57 - kein zu hoher Wert, sondern Unsinn.",
    ),
    Mutation(
        "Musterspeicher rechnet wieder ohne Horizont",
        "src/alpaca_bot/patterns.py",
        "    r = gruppierter_test(teil[spalte], teil[\"tag\"], min_gruppen=MIN_TAGE_BESTAETIGUNG,\n                         horizont=h)",
        "    r = gruppierter_test(teil[spalte], teil[\"tag\"], min_gruppen=MIN_TAGE_BESTAETIGUNG)",
        "test_dauerbetrieb",
        "Eine Lernschleife auf unkorrigierten Werten bestaetigt rund 40 % "
        "Rauschen als Muster - dauerhaft und automatisch.",
    ),
    Mutation(
        "Lernschritt faellt aus dem Dauerbetrieb",
        "scripts/16_shadow_daemon.py",
        '                     ("gelernt", lernen)):',
        "                     ):",
        "test_dauerbetrieb",
        "Genau der Zustand vor dem 22.08.2026: der Musterspeicher war "
        "gebaut, wurde aber nie aufgerufen - Tabelle `muster` leer.",
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
