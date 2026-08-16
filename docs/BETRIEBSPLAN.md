# Betriebsplan — was läuft, was beobachtet wird, wann entschieden wird

> Stand: 15.08.2026. **Dieses Dokument beantwortet: Was passiert jetzt,
> wie lange, und woran erkennen wir, ob es funktioniert hat?**
>
> Ergänzt `docs/BEFUNDE.md` (was wir bereits wissen) um den Fahrplan
> nach vorn. Beide werden bei jeder Änderung mitgeführt.

---

## 1. Neustart des Rechners — was passiert

**Ja, beide Bots starten automatisch wieder** — mit einer Bedingung.

| Schritt | Verhalten |
|---|---|
| Mac fährt hoch | FileVault verlangt das Passwort — **noch läuft nichts** |
| Du meldest dich an | launchd lädt beide Dienste (`RunAtLoad=true`) |
| Bot startet | Liest Positionen von Alpaca + Marken aus `state.sqlite`, macht weiter |
| Prozess stirbt später | launchd startet ihn neu (`KeepAlive=true`, 60 s Sperre) |

**Wichtig:** Die Dienste sind an deinen Benutzer gebunden. Am
Anmeldebildschirm laufen sie **nicht**. Da du beim Update ohnehin
anwesend bist und dich anmeldest, ist das unkritisch — aber es ist der
Grund, warum ein unbeaufsichtigter Neustart (Stromausfall) den Bot
pausieren würde, bis sich jemand anmeldet.

**Nach dem Neustart prüfen:**
```
python scripts/18_health_check.py      # muss GRÜN zeigen
```

Ein Datenverlust ist nicht möglich: Alpaca kennt die Positionen, die
Datenbanken liegen außerhalb des Projektordners und überleben alles.

---

## 2. Was wurde geändert — Live-Bot gegen Schattenbot

Das ist die wichtigste Unterscheidung des ganzen Umbaus.

### 2.1 Am LIVE-Bot: nur Messung, keine Handelslogik

| Änderung | Wirkung auf Handelsentscheidungen |
|---|---|
| Quote-Plausibilitätsprüfung (2 %) | **keine** — betrifft nur `expected_price` im Protokoll |
| `bars_held` korrekt berechnet | **keine** — Protokollfeld |
| `after_10d` wird gefüllt | **keine** — Auswertung |
| Score-Vorzeichen im Bericht | **keine** — Berichtstext |
| Slippage-Bereinigung | **keine** — Auswertung |
| Symbolauswahl bei `evaluate_outcomes` | **keine** — Auswertung |
| `zeitausstieg_dynamisch` | **AUS** — Standard `False` |
| **Intraday-Stop** (neu 15.08.) | **JA — echte Verhaltensänderung.** Stop-Marken werden jetzt jeden Zyklus (~15 Min) gegen den aktuellen Kurs geprüft statt einmal täglich gegen den Vortagesschluss. Bringt Live mit dem Schatten in Übereinstimmung, der das schon immer so gerechnet hat. |

> **Der Live-Bot wählt Kandidaten exakt wie vor dem Urlaub.** Einzige
> Verhaltensänderung ist der Intraday-Stop (Zeile oben) — er verkauft
> früher, kauft aber nichts anderes. Verifiziert: Bei
> `zeitausstieg_dynamisch=False` wird `max_hold_days_hart` nicht einmal
> gelesen; Tag 5, 19, 20 und 25 ergeben alle unverändert `zeitausstieg`.

Das ist Absicht: Wir haben elf Tage saubere Vergleichsdaten. Änderte
sich jetzt gleichzeitig die Handelslogik, wäre nicht mehr trennbar, was
woran lag.

### 2.2 Im SCHATTEN: die neue Idee, ohne Kapitalrisiko

`B11_dyn_ausstieg_live` — die dynamische Haltedauer:

```
Position hat 5 Tage erreicht
  ├─ im Gewinn UND weniger als 1 x ATR unter ihrem Höchststand
  │    └─ weiter halten
  ├─ Score unter exit_score
  │    └─ verkaufen ("these_traegt_nicht_mehr")
  ├─ Tag 20 erreicht
  │    └─ verkaufen ("zeitausstieg_hart")
  └─ sonst
       └─ verkaufen ("zeitausstieg")
```

---

## 3. Was wir erwarten — und woran wir es messen

**Vorab festgelegt, damit später keine Erzählung entsteht.**

### 3.1 Die eine Frage, die zuerst beantwortet werden muss

> **Trägt die Strategie nach echten Kosten?**

| | Wert |
|---|---|
| Gemessener Vorsprung | +0,11 % je Trade |
| Rundlauf-Breakeven bei 5 bps Spread | 0,142 % |
| **Erforderlich** | Slippage-Median **< 8 bps** über 30+ saubere Orders |
| Stand heute | 65 prüfbare Orders, **0 Ausreißer** seit dem Quote-Fix |

**Wenn das nicht erfüllt wird, ist jede andere Verbesserung irrelevant** —
dann handelt der Bot ein Signal, dessen Vorsprung die Kosten nicht deckt.

### 3.2 Die Flotte — Erwartung je Bot

Schwelle: **t > 2,76** (`fleet.schwelle_sigma`, steigt mit jedem Versuch).

| Bot | Erwartung | Stand |
|---|---|---|
| `B11_dyn_ausstieg_live` | **offen** — hält Gewinner länger, ohne Stagnierende zu binden | neu, 0 Tage |
| `B04_halten_lang` | wird vermutlich **nichts** zeigen | t = 0,94 |
| `B07_mehr_positionen` | Verdacht auf **negativ** | t = −2,42 |
| `B08`/`B09` | offen | t = 0,14 |
| `B01`/`B02`/`B03`/`B05`/`B06` | **wirkungslos** — Parameter greifen nicht | siehe BEFUNDE §E |

### 3.3 Was „Erfolg" für B10 konkret heißt

B10 gilt als **bestanden**, wenn *alle vier* zutreffen:

1. `vergleich_gepaart("B11_dyn_ausstieg_live", "B00_basis")` liefert **t > 2,76**
2. über mindestens **20 Handelstage**
3. Anteil verlängerter Positionen liegt zwischen **10 % und 60 %**
   (darunter: Regel greift praktisch nie; darüber: sie ist keine
   Ausnahme mehr, sondern hebelt den Zeitausstieg aus)
4. Die verlängerten Trades sind **nicht** allein durch wenige Ausreißer
   getragen — Median ebenfalls positiv

**Fällt einer der vier durch, bleibt es beim Zeitausstieg nach 5 Tagen.**

---

## 4. Zeitplan — wie lange laufen lassen

| Zeitraum | Was passiert | Was NICHT passiert |
|---|---|---|
| **jetzt – ca. 12.09.** (≈20 Handelstage) | Beide Bots laufen unverändert. B10 sammelt Daten. | Keine Parameteränderung, keine neue Hypothese |
| **ca. 12.09.** | Erste Zwischenauswertung | Noch keine Entscheidung |
| **ca. 10.10.** (≈40 Handelstage) | Entscheidung über B10 | — |

### Warum ~20 Handelstage das Minimum sind

Die gepaarte Messung braucht laut `shadow_eval.MIN_TAGE` mindestens 20
Tage. Der Grund steht in §B1 von `docs/BEFUNDE.md`: Maßgeblich ist die
Zahl der **Handelstage**, nicht der Trades. Elf Tage Betrieb haben nur
8 auswertbare Tage ergeben — zu wenig für jede Aussage.

**Realistisch:** 40 Tage sind besser als 20. Der Vorteil des gepaarten
Vergleichs (beide Bots sehen dieselben Tage) senkt die nötige Zeit von
~9 Monaten auf 6–10 Wochen, aber nicht auf zwei Wochen.

---

## 5. Was du beobachten solltest — und was nicht

### 5.1 Wöchentlich (2 Minuten)

```
python scripts/18_health_check.py
```
**Grün** = nichts zu tun. **Gelb/Rot** = melden. Zeigt jetzt auch den
Drawdown und warnt bereits, wenn er 75 % der Sperrgrenze erreicht (15 %) —
also **bevor** gesperrt wird.

Bei aktiver Sperre:
```
python scripts/20_risiko.py               # Grund und Kennzahlen ansehen
python scripts/20_risiko.py --entsperren  # erst NACH Ursachenklärung
```

### 5.2 Alle 1–2 Wochen (10 Minuten)

```
python scripts/13_tagesbericht.py --tage 14
```
Interessant sind dort:
- Abschnitt **[3] Ausführung**: Slippage-Median — die Kernfrage aus §3.1
- Abschnitt **[6] Nachbetrachtung**: Zeitausstieg und Wiedereinstiege
- **Regelabgleich** am Ende: muss „Keine Abweichungen" zeigen

### 5.3 Was du bewusst NICHT tun solltest

- **Nicht auf die Depotrendite schauen und daraus schließen.** +8,36 % in
  elf Tagen ist überwiegend Marktbewegung (SPY +5,07 %) und eine
  Stichprobe von 36 Trades. Eine gute Woche ist kein Befund, eine
  schlechte auch nicht.
- **Nicht bei einem Verlusttag eingreifen.** Der Bot hat Stop-Marken; ein
  Eingriff von Hand macht die Messung wertlos.
- **Keine Parameter „mal eben" ändern.** Jede Änderung setzt die
  Vergleichsbasis zurück und hebt die Signifikanzschwelle.

---

## 6. Ist das Projekt sinnvoll aufgebaut? — ehrliche Einschätzung

### Was gut ist

| Punkt | Warum es zählt |
|---|---|
| **Ein Entscheidungspfad** | `Engine.decide()` läuft in Backtest, Schatten und Live. Abweichungen können nur aus Ausführung stammen. |
| **Strukturelle Lookahead-Sperre** | `MarketSnapshot.validate()` — die Engine *kann* nicht in die Zukunft sehen. |
| **Schatten kann nicht handeln** | `shadow.py` importiert `trading.py` bewusst nicht. |
| **Voranmeldung + Versuchszähler** | Schutz gegen nachträgliche Erzählungen. |
| **Automatische Integritätsprüfung** | Findet Protokollfehler, bevor sie Entscheidungen verfälschen. |
| **Betrieb bewährt** | 11 Tage ununterbrochen, 1 abgefangener Fehler. |

### Was seit 15.08.2026 gebaut ist — Live-Tauglichkeit

| Baustein | Was er verhindert | Datei |
|---|---|---|
| **Drawdown-Sperre** (20 %) | Dass ein Bot mit kaputter Logik das Konto leerhandelt | `risiko.py` |
| **Tagesverlustgrenze** (5 %) | Weiterkaufen in einen laufenden Absturz | `risiko.py` |
| **Exposure-Grenze** (100 %) | Ungewollten Hebel (Alpaca erlaubt bis 4×) | `risiko.py` |
| **Cash-Reserve** (2 %) | Zwangsverkäufe bei Kurslücken | `risiko.py` |
| **Klumpenkontrolle** (40 %/Sektor) | Dass 15 Positionen in Wahrheit *eine* Wette sind | `risiko.py` + `universe.sektoren` |
| **Positionsobergrenze** (30) | Konfigurationsfehler bei `max_positions` | `risiko.py` |
| **Kapitalflüsse** | Dass Einzahlungen als Gewinn gelesen werden | `kapital.py` |
| **Zeitgewichtete Rendite** | Unvergleichbare Kennzahlen nach Einzahlung | `kapital.py` |
| **Equity je Zyklus** | Dass ein Drawdown-Beginn nicht rekonstruierbar ist | `state.kapital_verlauf` |

**Wichtige Eigenschaften, bewusst so gebaut:**

- **Die Sperre ist persistent und löst sich nie selbst.** Eine Sperre, die
  sich nach einer Stunde aufhebt, kauft genau in den Crash zurück, wegen
  dem sie ausgelöst hat. Lösen nur über `scripts/20_risiko.py --entsperren`
  mit wörtlicher Bestätigung.
- **Verkaufen ist immer erlaubt.** Eine Sperre darf nie verhindern, aus
  einer Position herauszukommen.
- **Fällt die Risikoprüfung selbst aus, wird nicht gehandelt.** Ein
  Risiko-Dach, das im Zweifel durchlässt, ist keines.
- **Auch Nachkäufe werden geprüft.** Sonst ließen sich die Grenzen über
  wiederholtes Aufstocken umgehen (gemessen: bis zu 9 Nachkäufe je Symbol).

### Was weiterhin fehlt

| Lücke | Folge | Priorität |
|---|---|---|
| **Regime nicht protokolliert** | „In welcher Marktlage funktioniert es?" ist am Depot nicht beantwortbar. | mittel |
| **Laptop statt Server** | Deckel zu = alles aus. Kein Auto-Login wegen FileVault. | mittel |
| **Slippage noch nicht belastbar** | Die Kernfrage (§3.1) braucht 30+ saubere Orders | läuft |

**Einschätzung:** Der Mess- und Lernapparat ist für ein Privatprojekt
ungewöhnlich sauber. Die Lücken liegen fast alle im **Risikoschutz** —
also genau dort, wo es teuer wird, sobald echtes Geld im Spiel ist. Für
den Papierbetrieb ist das vertretbar; **vor dem Wechsel auf echtes Geld
ist das Risiko-Dach Pflicht.**

---

## 7. Reihenfolge der nächsten Schritte

| # | Schritt | Wann | Bedingung |
|---|---|---|---|
| 1 | Bots laufen lassen, nichts ändern | jetzt – ~12.09. | — |
| 2 | ~~Risiko-Dach bauen~~ | **erledigt 15.08.** | — |
| 3 | ~~Kapitalflüsse erfassen~~ | **erledigt 15.08.** | — |
| 4 | Zwischenauswertung | ~12.09. | ≥20 Handelstage |
| 5 | Entscheidung über B10 | ~10.10. | ≥40 Handelstage, alle 4 Kriterien aus §3.3 |
| 6 | Echtgeld erwägen | frühestens danach | Slippage-Median < 8 bps **und** Risiko-Dach steht |

**Schritte 2 und 3 sind die einzigen, die jetzt sinnvoll parallel laufen
können** — sie ändern nichts an den Handelsentscheidungen und stören die
laufende Messung deshalb nicht.

---

## 8. Abbruchkriterien

| Ereignis | Konsequenz |
|---|---|
| Health-Check zweimal in Folge ROT | Handel aus, Ursache klären |
| Regelabgleich meldet Abweichung | Sofort aus — ein Regelbruch ist ein Logikfehler, kein Pech |
| Slippage-Median > 15 bps über 30 Trades | Alle Backtest- und Schattenergebnisse neu bewerten |
| Konto-Drawdown > 20 % | **automatische Vollsperre** durch `risiko.py`, Lösen nur von Hand |
| B10 verlängert > 60 % der Positionen | Regel greift zu oft, Schwelle war falsch kalibriert |
