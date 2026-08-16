# Testplan — was geprüft wird und warum

> **Anlass (16.08.2026):** Jede gezielte Nachfrage hat bisher einen Fehler
> zutage gefördert — `bars_held` immer 0, `after_10d` nie gefüllt,
> Score-Vorzeichen ignoriert, Quote-Schwelle zu grob, `code_version` zwei
> Monate kaputt, Flotten-Referenz seit zwei Wochen falsch. **Keiner davon
> wurde vom bestehenden Selbsttest gefunden.**
>
> Grund: `scripts/00_selftest.py` prüft die **Forschungsschicht**
> (Indikatoren, Backtest, ML, Lookahead). Handelslogik, Risiko-Dach,
> Protokollierung und Live/Schatten-Konsistenz waren **ungetestet**.

---

## 1. Grundsätze

1. **Jeder gefundene Fehler bekommt einen Regressionstest.** Ein Fehler,
   der einmal auftrat, darf nie unbemerkt zurückkommen. Die Testnamen
   nennen deshalb den konkreten Vorfall, nicht nur die Funktion.
2. **Tests brauchen kein Netz.** Alles läuft gegen synthetische Daten
   oder temporäre Datenbanken. Ein Test, der eine API braucht, ist kein
   Test, sondern ein Betriebszustand.
3. **Invarianten statt Momentaufnahmen.** Nicht „B09 hat Wert X", sondern
   „B09 ist deckungsgleich mit dem, was `12_daemon.py` startet" — das
   bleibt auch dann richtig, wenn sich die Werte ändern.
4. **Nach JEDER Änderung laufen lassen**, nicht nur vor dem Commit.

---

## 2. Was geprüft wird

### 2.1 Handelslogik (`test_engine_*.py`)

| Bereich | Kernfragen |
|---|---|
| Ausstiegsregeln | Reihenfolge Stop → Ziel → Zeit → Score. Löst jede Regel genau dann aus, wenn sie soll? |
| Dynamischer Zeitausstieg | Hält bei intaktem Trend, verkauft bei Rücksetzer > 1×ATR, harte Grenze bei 20 Tagen |
| **Schalter-Isolation** | Bei `zeitausstieg_dynamisch=False` verhält sich die Engine **bitweise** wie vorher — `max_hold_days_hart` wird nicht einmal gelesen |
| Positionsgrößen | `max_position_pct`, `min_position_pct`, Wasserfüllung, kein Kapital bleibt unnötig liegen |
| Sperrfrist | Kein Rückkauf innerhalb `reenter_cooldown_days` |
| Nachkauf | Nur in Gewinner, nur über `min_score`, Deckel wird eingehalten, `bars_held` wird **nicht** zurückgesetzt |
| Regimefilter | Sperrt Käufe — **und verkauft Bestand** (dokumentiertes Verhalten, siehe BEFUNDE §G7) |
| Lookahead | `MarketSnapshot.validate()` erkennt Daten nach `as_of` |

### 2.2 Risiko-Dach (`test_risiko.py`)

| Kernfrage | Warum kritisch |
|---|---|
| Drawdown-Sperre löst bei 20 % aus | ohne sie handelt ein defekter Bot bis auf null |
| **Einzahlungsbereinigung** | ohne sie hätte ein realer 25-%-Verlust nur 16,7 % gezeigt → keine Sperre |
| Sperre ist persistent | eine sich selbst lösende Sperre kauft in den Crash zurück |
| Lösen nur mit wörtlicher Bestätigung | Reibung ist der Zweck |
| **Verkaufen immer erlaubt** | eine Sperre darf nie zur Falle werden |
| Exposure / Cash / Sektor / Anzahl | jede Grenze einzeln |
| Prüfung fällt aus → kein Handel | ein Dach, das im Zweifel durchlässt, ist keines |

### 2.3 Kapitalflüsse (`test_kapital.py`)

- Derselbe Alpaca-Aktivitäts-`id` wird **nie zweimal** gebucht
- CSD positiv, CSW negativ (Vorzeichen vereinheitlicht)
- **DIV/INT werden NICHT** als Kapitalfluss gezählt (echter Ertrag)
- Zeitgewichtete Rendite ≠ naive Rendite bei Einzahlung

### 2.4 Protokoll (`test_journal.py`)

- `code_version` wird je Lauf geschrieben *(war 2 Monate kaputt)*
- `referenz_quelle` wird geschrieben
- `slippage_report` schließt Legacy- und Fallback-Zeilen aus
- Dry-Run-Orders überschreiben sich **nicht** gegenseitig
- Entscheidung → Order → Ergebnis bleibt verknüpft

### 2.5 Trade-Lebenslauf (`test_lifecycle.py`)

- `bars_held` wird **aus den Daten gerechnet**, nicht als 0 übernommen
- `pending_analysis` erfasst `after_10d`, nicht nur `after_5d`
- Score-Bewertung prüft das **Vorzeichen**, nicht nur den Betrag

### 2.6 Referenzpreis (`test_referenzpreis.py`)

- Quote > 2 % vom letzten Trade → verworfen, letzter Trade gilt
- Fehlende Quote-Seite → **kein** Mittelwert aus echt und 0
- Keine Quote → `fallback`, wird von der Slippage-Messung ausgeschlossen
- **Intraday-Stop feuert nicht auf `fallback`-Quotes**

### 2.7 Statistik (`test_statistik.py`)

- Gruppierter Test rechnet über **Gruppen**, nicht Einzelwerte
- Naiver Wert wird zum Vergleich mitgeliefert
- < 20 Gruppen ⇒ nie „belastbar", egal wie hoch t ist

### 2.8 Live/Schatten-Konsistenz (`test_konsistenz.py`)

**Der wichtigste Block** — hier lagen die teuersten Fehler.

- **`B09_nachkauf` ist deckungsgleich mit dem, was `12_daemon.py` startet**
  *(Invariante, keine Momentaufnahme — bricht, sobald jemand die
  Skript-Defaults ändert)*
- `shadow.py` importiert **kein** `trading.py`
- Beide Pfade melden dieselbe `code_version`
- Alle `EngineConfig`-Felder erscheinen in `as_dict()` *(sonst prüft der
  Regelabgleich sie nicht)*

### 2.9 Nachbetrachtung (`test_nachbetrachtung.py`)

- Wiedereinstieg wird von Nachkauf getrennt *(im Orderbuch sehen beide
  gleich aus)*
- Marktbereinigung wirkt

---

## 3. Ausführen

```
python scripts/00_selftest.py     # Forschungsschicht (47 Prüfungen)
.venv/bin/pytest tests/ -q        # Betriebsschicht
```

Beides gehört nach **jeder** Codeänderung ausgeführt, bevor die Dienste
neu gestartet werden.
