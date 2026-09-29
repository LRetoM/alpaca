# Auswertung nach 11 Tagen Dauerbetrieb — Befunde und Umsetzungsplan

> Stand: 2026-08-15, nach ununterbrochenem Betrieb vom 04.08. bis 15.08.
> Grundlage: 119 echte Orders, 36 abgeschlossene Trades, 1.284
> Entscheidungen im Depot; 12.516 Vorhersagen im Schattenbetrieb.

---

## 0. Kurzfassung

**Betrieb:** einwandfrei. Beide Dienste liefen 11 Tage ohne Unterbrechung
(gleiche Prozess-ID durchgehend), ein einziger Fehler (HTTP 500 von
Alpaca), automatisch abgefangen.

**Ergebnis:** +8,36 % gegen +5,07 % SPY. Sieht gut aus, ist aber über
36 Trades in einer einzigen, stark steigenden Marktphase **kein Beleg**.

**Der wichtigste Befund ist methodisch:** Die naive Auswertung der
Schattendaten ergibt einen Vorsprung von +0,74 % je 5 Tagen mit t = 2,63
— scheinbar belastbar. Rechnet man korrekt (je Tag mitteln, dann über die
Tage testen, weil Vorhersagen desselben Tages nicht unabhängig sind),
bleibt **t = 1,45 — nicht belastbar**. Dieselben Daten, zwei Aussagen.
Die zweite ist die richtige.

**Sechs echte Fehler gefunden**, davon zwei, die Lernen aktiv verhindern
(`bars_held` immer 0, `after_10d` nie gefüllt).

---

## 1. Betriebsbilanz

| Kennzahl | Wert |
|---|---|
| Laufzeit ohne Unterbrechung | 04.08. 19:19 → 15.08., **11 Tage** |
| Prozess-Neustarts | 0 |
| Fehler gesamt | 1 (HTTP 500, automatisch abgefangen) |
| Fehlgeschlagene Läufe | 0 von 276 |
| Handelstage lückenlos protokolliert | 30.07. – 13.08. |

Die vor der Abreise getroffenen Maßnahmen (Deckel offen, Netzteil,
Updates pausiert) haben gehalten. Kein Schlaf-Ereignis im Log.

---

## 2. Ergebnis — und warum es nichts beweist

| | Wert |
|---|---|
| Depot 100.000 $ → 108.361,63 $ | **+8,36 %** |
| SPY im selben Zeitraum | +5,07 % |
| Differenz | +3,3 Prozentpunkte |
| Abgeschlossene Trades | 36 |
| Trefferquote | 78 % |
| Mittlere Rendite je Trade | +4,00 % |

**Warum das kein Beleg ist:**

1. **36 Trades sind zu wenig.** Der gemessene Vorsprung der Strategie
   liegt bei +0,11 % je Trade; die Streuung einzelner Aktien liegt bei
   mehreren Prozent. Um einen so kleinen Effekt nachzuweisen, braucht es
   Hunderte bis Tausende Beobachtungen.
2. **Eine einzige Marktphase.** SPY +5,07 %, das Universum sogar +3,73 %
   je 5 Tage. In einer so starken Aufwärtsphase sieht fast jede
   Kaufstrategie gut aus.
3. **Die Trades überlappen stark.** 10 der 13 auswertbaren Zeitausstiege
   fanden am **selben Tag** statt (04.08.) — das sind faktisch 3
   unabhängige Beobachtungen, nicht 13.

---

## 3. Deine Frage: Was passiert nach 5 Tagen?

### 3.1 Was der Bot heute tut

Geregelt in `engine.py`:

```
max_hold_days = 5          -> nach 5 Handelstagen: Zeitausstieg, IMMER
reenter_cooldown_days = 3  -> danach 3 Handelstage Kaufsperre fuer das Symbol
```

Eine Aktie, die am fünften Tag noch steigt, **wird trotzdem verkauft**.
Sie kann frühestens nach 3 Handelstagen zurückgekauft werden — und nur,
wenn sie dann erneut unter die Top-Kandidaten fällt.

**Der Rückkauf-Sofort-Fehler existiert nicht mehr:** Geprüft über alle
119 echten Orders — 6 Verstöße gegen die Sperre, **alle vom 28./29.07.,
also vor Einführung der Sperre** (Commit b40f4f3 vom 29.07.). Seitdem:
null Verstöße.

Die Mehrfachkäufe bei MAR (5×), CTVA (5×), TGTX (3×) sind **Nachkäufe**
(`allow_topup`) in laufende Gewinnpositionen, keine Wiedereinstiege —
50 Nachkauf-Entscheidungen insgesamt.

### 3.2 Was die Daten zur Haltedauer sagen

Für die 13 auswertbaren Zeitausstiege, marktbereinigt:

| | Wert |
|---|---|
| Realisiert im Schnitt | +6,87 % |
| Kurs 5 Tage NACH dem Verkauf | +0,55 % |
| SPY im selben Fenster | +0,03 % |
| **Überschuss über den Markt** | **+0,52 %** |
| Fälle, in denen Halten besser gewesen wäre | 10 von 13 |

Sieht nach „länger halten lohnt sich" aus. **Aber:**

- 10 der 13 Ausstiege waren am selben Tag → ~3 unabhängige Beobachtungen.
- Die Streuung ist gewaltig: von **−16,05 %** (SIMO) bis **+7,12 %**
  (LBRT). Die drei Fälle, in denen Verkaufen richtig war, waren
  *dramatisch* richtig; die zehn Gegenfälle nur moderat.
- Bei dieser Streuung und drei effektiven Beobachtungen ist der
  Mittelwert bedeutungslos.

**Fazit: Die Frage ist mit den Depotdaten nicht beantwortbar.** Sie ist
aber im Schattenbetrieb bereits angemeldet — Bot `B04_halten_lang`
(`max_hold_days=10`) läuft genau dafür. Dort sammeln sich die nötigen
Beobachtungen, ohne echtes Geld zu riskieren.

### 3.3 Was zusätzlich gemessen werden muss (neu)

Drei Fragen, die heute **nicht** beantwortet werden können, weil die
Daten fehlen — behoben in §5:

1. **Wurde ein verkauftes Symbol später zurückgekauft, und mit welchem
   Ergebnis?** (Wiedereinstiegs-Analyse)
2. **Wie lief es nach 10 Tagen weiter?** (`after_10d` ist heute für
   *jeden* Trade leer — siehe Fehler 2)
3. **Wie lange wurde eine Position tatsächlich gehalten?**
   (`bars_held` ist heute für *jeden* Trade 0 — siehe Fehler 1)

---

## 4. Der methodische Hauptbefund

Die Schattendaten (12.516 Vorhersagen) laden zu einem Fehler ein, den ich
selbst zuerst gemacht habe.

**Naive Rechnung** (jede Vorhersage = eine Beobachtung):

```
Kandidat 5d     : +4,477 %   t = 14,86
Benchmark (SPY) : +2,628 %
Universum       : +3,733 %
UEBERSCHUSS     : +0,744 %   t = 2,63   <- sieht belastbar aus
```

**Ehrliche Rechnung** (je Handelstag mitteln, dann über die Tage testen):

| Tag | n | Überschuss |
|---|---|---|
| 2026-07-28 | 158 | +0,71 % |
| 2026-07-29 | 229 | +1,94 % |
| 2026-07-30 | 98 | +1,52 % |
| 2026-07-31 | 119 | +0,19 % |
| 2026-08-03 | 90 | +0,45 % |
| 2026-08-04 | 67 | −0,73 % |
| 2026-08-05 | 80 | −0,24 % |
| 2026-08-06 | 85 | −0,12 % |

```
Tage: 8   Mittel: +0,464 %   t = 1,45   <- NICHT belastbar
```

**Warum die zweite Rechnung die richtige ist:** Alle Kandidaten eines
Tages sehen denselben Markt. Steigt der Markt, steigen sie gemeinsam.
Sie sind damit keine unabhängigen Beobachtungen — 926 Vorhersagen an 8
Tagen tragen ungefähr so viel Information wie 8 Beobachtungen, nicht 926.
Die naive Rechnung überschätzt die Sicherheit um etwa den Faktor
`sqrt(926/8) ≈ 10,8`.

**Konsequenz:** Jede künftige Auswertung muss tagesgeclustert rechnen.
Das wird in §5 als feste Funktion umgesetzt, damit der Fehler nicht
wieder passieren kann.

---

## 5. Gefundene Fehler und Umsetzungsplan

### Fehler 1 — `bars_held` ist in JEDEM Lebenslauf 0

`daemon._record_lifecycle()` liest `meta.get("bars_held")` aus
`state.position_meta`. Dort wird der Wert beim Anlegen auf 0 gesetzt und
**nie erhöht** — die Engine berechnet ihn zur Laufzeit frisch aus
`entry_date` (`live.build_portfolio`), schreibt ihn aber nie zurück.

*Folge:* Die Spalte `bars_held` ist über alle 36 Trades hinweg 0. Jede
Auswertung nach Haltedauer ist damit unmöglich — genau die Frage aus §3.

*Behebung:* In `_record_lifecycle` aus `entry_date`/`exit_date` in
Handelstagen berechnen, wie es `build_portfolio` bereits tut.

### Fehler 2 — `after_10d` wird NIE gefüllt

```python
def pending_analysis(self):
    "... WHERE after_5d IS NULL"
```

Sobald `after_5d` gesetzt ist, verlässt der Trade die Warteschlange.
`after_10d` braucht aber fünf Tage länger und wird deshalb nie
nachgetragen.

*Folge:* Die 10-Tage-Nachbetrachtung fehlt vollständig — bestätigt: 36
von 36 Trades haben `after_10d = None`. Für die Haltedauer-Frage ist das
genau die fehlende Zahl.

*Behebung:* Bedingung auf `after_5d IS NULL OR after_10d IS NULL`
erweitern.

### Fehler 3 — Score-Bewertung ignoriert das Vorzeichen

`lifecycle.analyse()` meldet „Der Score sortiert in die richtige
Richtung", sobald `|korr| >= 0.1` — **auch bei negativer Korrelation**.
Gemessen wurde −0,133; der Bericht lobte den Score trotzdem.

*Behebung:* Vorzeichen prüfen und bei negativer Korrelation ausdrücklich
warnen.

### Fehler 4 — Quote-Schwelle zu großzügig

Die am 04.08. eingebaute Prüfung (`_MAX_QUOTE_ABWEICHUNG = 0.05`) hat in
11 Tagen **13 fehlerhafte Quotes korrekt abgefangen**. Aber **8 weitere
Ausreißer über 200 bps sind durchgerutscht**, alle mit einer Abweichung
von **2,1 – 4,9 %** — knapp unter der Schwelle:

| Symbol | Quote | letzter Trade | Abweichung |
|---|---|---|---|
| MUSA | 553,39 | 527,50 | 4,9 % |
| FICO | 1142,40 | 1089,46 | 4,9 % |
| CTVA | 83,74 | 80,01 | 4,7 % |
| MAR | 374,62 | 360,25 | 4,0 % |
| PFGC | 109,88 | 105,70 | 4,0 % |
| POST | 81,66 | 78,62 | 3,9 % |
| MAR | 340,00 | 350,26 | 2,9 % |
| APP | 313,44 | 320,08 | 2,1 % |

Die Schwelle war an den beiden schlimmsten Fällen (SIMO/KGS, 11–14 %)
geeicht und damit zu grob.

*Behebung:* Schwelle auf 2 % senken. Begründung: Zwischen Quote und
letztem Trade liegen Sekunden — eine echte Bewegung von über 2 % in
Sekunden ist bei liquiden Werten die Ausnahme, eine fehlerhafte Quote
die Regel. Der Verlust ist gering: Wird eine echte Bewegung
fälschlich verworfen, ist die Referenz der letzte Trade — ebenfalls ein
echter Marktpreis, nur Sekunden alt.

### Fehler 5 — Integritätsprüfung meldet bekannte Altlasten als neu

`data_integrity.check_extreme_slippage` filtert die Legacy-Zeilen nicht,
die `journal.slippage_report()` bereits ausschließt. Der Health-Check
meldet deshalb dauerhaft dieselben drei AMKR-Zeilen von Ende Juli.

*Folge:* Gewöhnungseffekt — eine Warnung, die immer steht, wird
übersehen. Genau dann, wenn sie einmal etwas Neues meldet.

*Behebung:* Denselben Filter anwenden.

### Fehler 6 — 15 Entscheidungen ohne bewertetes Ergebnis

`evaluate_outcomes` läuft nur einmal je Kalendertag und begrenzt auf 200
Symbole. Bei 1.284 Entscheidungen bleiben Reste liegen.

*Behebung:* Symbolgrenze anheben und Lücken beim Start nacharbeiten.

### Neu 7 — Wiedereinstiegs-Analyse

Beantwortet deine Frage dauerhaft und automatisch: Wurde ein verkauftes
Symbol später zurückgekauft? Was hat der Zwischenverkauf gekostet oder
gebracht? Ohne dieses Werkzeug bleibt die Frage bei jedem Mal Handarbeit.

### Neu 8 — Tagesgeclusterte Auswertung als feste Funktion

Damit der Fehler aus §4 strukturell nicht wieder passieren kann.

---

## 6. Reihenfolge der Umsetzung

| # | Aufgabe | Warum zuerst |
|---|---|---|
| 1 | Fehler 1 + 2 (`bars_held`, `after_10d`) | Ohne sie ist die Haltedauer-Frage dauerhaft unbeantwortbar |
| 2 | Neu 8 (tagesgeclusterter Test) | Verhindert falsche Schlüsse aus allem Weiteren |
| 3 | Fehler 4 (Quote-Schwelle) | Wirkt auf jede künftige Order |
| 4 | Fehler 3 + 5 (Berichtsfehler) | Verhindert falsche Beruhigung |
| 5 | Neu 7 (Wiedereinstiege) | Beantwortet die offene Frage |
| 6 | Fehler 6 (Ergebnislücken) | Datenvollständigkeit |
| 7 | Dienste neu starten | Damit alles greift |

---

## 7. Was NICHT geändert wird — und warum

- **`max_hold_days` bleibt bei 5.** Die Daten deuten auf „länger halten"
  hin, aber mit drei effektiven Beobachtungen wäre das eine Änderung auf
  Zuruf. `B04_halten_lang` misst es bereits im Schatten.
- **Keine Parameteranpassung aus den 36 Trades.** Die Projektregel
  verlangt 30+ Trades *je Gruppe*; erreicht wird das nur beim
  Gesamtbestand, nicht in den Untergruppen.
- **Kein zweiter Live-Bot.** Der Befund aus `docs/mehrbot-plan.md` gilt
  unverändert: Erst muss feststehen, dass ein Bot nach Kosten trägt.
