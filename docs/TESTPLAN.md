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
>
> **Stand 22.08.2026:** **332 Tests** in 21 Dateien, 48 Selbstprüfungen,
> 59 von 59 Mutationen gefangen.
>
> Die Spalte „Tests" in §2 zählt Testfunktionen und summiert sich auf
> **327**. pytest meldet 332, weil zwei Tests parametrisiert sind
> (`test_engine_ausstiege.py` über fünf Haltedauern,
> `test_lernkern.py` über zwei Zeitzonen) und jede Parametrisierung
> einzeln zählt. Beide Zahlen sind richtig — sie zählen Verschiedenes.

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
5. **Der Mutationstest prüft die Tests.** Ein Test, der immer grün ist,
   weil er falsch geschrieben wurde, ist schlimmer als kein Test. Er hat
   bereits mehrfach zu schwache Tests entlarvt — zuletzt am 22.08.2026
   einen, der einen `nan`-Wert prüfte, aber nicht das Urteil, das daraus
   folgte (§G16).

---

## 2. Die Testdateien — was wo liegt

Eine Zeile je Datei, damit erkennbar bleibt, wo ein neuer Test hingehört.
**Diese Tabelle wird bei jeder neuen Datei mitgeführt.** Bis zum
22.08.2026 nannte dieser Abschnitt fünf Dateien, die es nicht (mehr) gab,
und fünfzehn existierende fehlten — ein Dokument, das etwas zu
beschreiben behauptet und es nicht mehr tut, ist genau die Fehlerklasse
aus `BEFUNDE.md` §G15/§G16.

### 2.1 Handelslogik

| Datei | Tests | Kernfragen |
|---|---:|---|
| `test_engine_ausstiege.py` | 18 | Reihenfolge Stop → Ziel → Zeit → Score. Dynamischer Zeitausstieg. **Schalter-Isolation**: bei `zeitausstieg_dynamisch=False` verhält sich die Engine bitweise wie vorher. Lookahead-Sperre. |
| `test_engine_einstiege.py` | 18 | Kapitalverteilung (Wasserfüllung), Positionsgrößen, Sperrfrist, Regimefilter (sperrt Käufe **und** verkauft Bestand, §G7), Nachkauf. |
| `test_handelsrhythmus.py` | 7 | **Live gegen Spiegel (§G16):** Nachkäufe entstehen nur im vollen Depot. `max_new_positions` wirkt live je Zyklus, im Schatten je Handelstag. |

### 2.2 Risiko und Kapital

| Datei | Tests | Kernfragen |
|---|---:|---|
| `test_risiko_bewertbarkeit.py` | 17 | **§G18:** Keine Position verschwindet still aus der Risikorechnung — Fallback `market_value` → `qty·current_price` → `qty·avg_entry`. Ist nichts bestimmbar, wird **blockiert** statt übersprungen (Verkäufe bleiben erlaubt). Dazu: das JSONL-Rohprotokoll meldet seinen Ausfall, `earnings` rechnet überlappungskorrigiert. |
| `test_risiko.py` | 18 | Drawdown-Sperre bei 20 %. **Einzahlungsbereinigung** (ohne sie hätte ein realer 25-%-Verlust nur 16,7 % gezeigt). Sperre ist persistent, Lösen nur wörtlich, **Verkaufen immer erlaubt**, Exposure/Cash/Sektor/Anzahl je einzeln, Prüfung fällt aus → kein Handel. |

### 2.3 Protokoll und Datenqualität

| Datei | Tests | Kernfragen |
|---|---:|---|
| `test_protokoll.py` | 18 | `code_version` je Lauf *(war 2 Monate kaputt)*, `referenz_quelle`, Slippage schließt Legacy und Fallback aus, Dry-Run-Orders überschreiben sich nicht, Lebenslauf, Kapitalflüsse (DIV/INT sind **kein** Kapitalfluss). |
| `test_datenklarheit.py` | 14 | Wächter für **stumme Felder** (hört ein Feld auf, sich zu füllen?), `bars_held` gegen die Datumsangaben, Journal trennt Live von Simulation, Kontext an **allen** Entscheidungsarten (nicht nur `buy`). |
| `test_monitoring.py` | 8 | Kontext im Protokoll, Kontext ändert **keine** Entscheidung, Liquiditätsdezile. |
| `test_daten.py` | 6 | Bar-Cache-Schlüssel: `sha256` statt `hash()` *(pro Prozess randomisiert)*, Datum auf den Tag normalisiert. |

### 2.4 Ausführung

| Datei | Tests | Kernfragen |
|---|---:|---|
| `test_ausfuehrung.py` | 30 | Referenzpreis (Quote > 2 % vom letzten Trade → verworfen; **kein** Mittelwert aus echt und 0; `fallback` fliegt aus der Slippage). Intraday-Stop feuert **nicht** auf `fallback`. Wiedereinstiege getrennt von Nachkäufen. Bericht nennt seinen Bezug. **Die vier Abnahmekriterien aus BETRIEBSPLAN §3.3.** |
| `test_regelabgleich.py` | 7 | **§G16:** Fehler**quote** statt Fehlerzahl entscheidet die Schwere. Der Regelabgleich läuft im Health-Check, nicht nur im Wochenbericht. |
| `test_kostenkontrolle.py` | 14 | **§G16:** Die Kostenkontrolle misst den **Median über Orders** — dieselbe Kennzahl, die BETRIEBSPLAN §3.1/§8 nennen. Ausreißer kippen das Urteil nicht, bleiben aber sichtbar. Richtung stimmt (negativ = günstiger). Die Kursanpassungsprüfung prüft die **junge Kante**, nicht die Historie. |

### 2.5 Statistik — die schärfste Schicht

| Datei | Tests | Kernfragen |
|---|---:|---|
| `test_statistik_ueberlappung.py` | 19 | Newey-West-Grundverhalten, `gruppierter_test` mit `horizont`, **gemessene Fehlalarmquote** (39,5 % ohne Korrektur), Faktorauswahl nutzt den korrigierten Wert. |
| `test_faktorauswahl.py` | 16 | **§G16:** Der Korrelationsfilter, den die Signatur seit jeher versprach, existiert. **Effektive Breite** statt nur paarweiser Korrelation — vier Faktoren können paarweise sauber sein und gemeinsam 1,53 Signale tragen. |
| `test_hypothesen.py` | 9 | **§G16:** `horizont` ist kein toter Parameter. Der Status hängt am korrigierten t-Wert. Ohne gültigen t-Wert **kein Urteil** (`offen`). Kalibrierung in beide Richtungen. |

### 2.6 Lernapparat

| Datei | Tests | Kernfragen |
|---|---:|---|
| `test_lernkern.py` | 22 | Panel-Zusicherungen, Zeitzonen, Wächter gegen leere Merkmale, **Walk-Forward ohne Leck** (kein Handelstag in beiden Fenstern), ehrliche Bewertung, Fokus rechnet nicht hoch, wo nichts gemessen ist, Abnahmehürden. |
| `test_dauerbetrieb.py` | 13 | IC korrigiert die Überlappung, Musterspeicher rechnet mit Horizont, Lernschritt ist im Daemon verdrahtet und steht **hinter** den erzeugenden Schritten, Verifizieren rechnet nicht doppelt. |
| `test_musterspeicher.py` | 17 | **§G16:** keine Duplikate, Zerfallenes bleibt zerfallen, jeder Schnitt zählt als Versuch. Fokus-Zahlen kommen aus den Quellen. **Vorzeichenstabilität ist verdrahtet.** |
| `test_nutzung.py` | 20 | Die **fünf** Arten des stillen Ausfalls: nie gelaufen, immer leer, immer gleich, zu selten, **fehlerhaft** (§G16). „Immer gleich“ nur bei **neuen Daten** — sonst leuchtet der Health-Check an jedem Wochenende (§G18). Ausnahmen sind begründet, das Protokoll stört den Betrieb nie. |

### 2.7 Werkzeuge — Ereignisstudie und RL

| Datei | Tests | Kernfragen |
|---|---:|---|
| `test_werkzeuge.py` | 16 | **§G17:** Sperrzone ist nicht optional (auch im **Standardwert**). Der Timing-Test ist **nicht abschaltbar** — README führt ihn als eine der fünf Sicherungen. Er erkennt echtes Timing (Perzentil 100) und falsches (2). **Fehlalarmquote gemessen: 8,5 %** auf reinem Rauschen. Die RL-Kette läuft durch, ohne Trainingsdaten im Testfenster. |

> Beide Module sind **Werkzeuge, keine Dauerläufer** — wie
> `03_backtest.py`. Der Nutzungsnachweis überwacht sie bewusst nicht;
> dass sie nicht im 15-Minuten-Takt laufen, ist ihre Bestimmung, kein
> Ausfall im Sinne von §G15.

### 2.8 Live/Schatten-Konsistenz — der wichtigste Block

| Datei | Tests | Kernfragen |
|---|---:|---|
| `test_konsistenz.py` | 20 | **`B09_nachkauf` ist deckungsgleich mit dem, was `12_daemon.py` startet** *(Invariante — bricht, sobald jemand die Skript-Defaults ändert)*. `shadow.py` importiert **kein** `trading.py`. Beide Pfade melden dieselbe `code_version`. Alle `EngineConfig`-Felder erscheinen in `as_dict()`. Die Simulation fährt feldweise die Live-Strategie. |

> **Wichtige Ergänzung seit §G16:** `test_konsistenz.py` sichert die
> **Konfiguration**. Dass zwei Bots mit gleicher Konfiguration sich auch
> gleich **verhalten**, ist damit *nicht* gesichert — genau dort lag der
> schwerste Fund. `test_handelsrhythmus.py` schließt diese Lücke.

---

## 3. Ausführen

```
python scripts/22_tests.py          # beide Schichten, das übliche Kommando
python scripts/23_mutationstest.py  # prüft, ob die Tests etwas fangen
python scripts/18_health_check.py   # Betrieb, Daten, Regeln, Bausteine
```

Einzeln:

```
python scripts/00_selftest.py       # Forschungsschicht (48 Prüfungen)
.venv/bin/pytest tests/ -q          # Betriebsschicht (332 Tests)
```

**Alles gehört nach jeder Codeänderung ausgeführt, bevor die Dienste neu
gestartet werden.** Schlägt etwas fehl: nicht neu starten, erst beheben.

---

## 4. Wenn ein neuer Fehler gefunden wird

Die Reihenfolge ist nicht verhandelbar und hat sich mehrfach bewährt:

1. **Test zuerst.** Er muss den Fehler reproduzieren und **rot** sein,
   bevor der Fix geschrieben wird. Ein Test, der nach dem Fix geschrieben
   wird, prüft, was der Fix tut — nicht, was der Fehler war.
2. **Fix.** Mit einem Kommentar, der den Vorfall benennt, nicht nur die
   Regel.
3. **Mutation ergänzen** in `scripts/23_mutationstest.py`: den Fehler
   absichtlich wieder einbauen und prüfen, dass der neue Test rot wird.
   Fängt er sie nicht, taugt der Test nicht — das ist am 22.08.2026
   genau einmal passiert und wurde nachgebessert.
4. **Eintrag in `docs/BEFUNDE.md`** mit Zahl, Datum und Quelle.
5. **Diese Tabelle in §2 mitführen**, wenn eine Datei dazukommt.
