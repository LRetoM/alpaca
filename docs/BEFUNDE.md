# Befunde-Register — was wir gemessen haben und was daraus folgt

> **Zweck:** Das eine Dokument, das VOR jeder Codeänderung gelesen wird.
> Es hält fest, was gemessen wurde, was widerlegt ist und welche Fehler
> schon einmal gemacht wurden — damit sie nicht ein zweites Mal passieren.
>
> **Regel:** Jeder Eintrag nennt die Zahl, das Datum und die Quelle. Ein
> Befund ohne Messung gehört nicht hierher, sondern ins Hypothesenregister
> (`hypotheses.py`).
>
> **Ergänzend:** Detailbegründungen stehen im Code (Kommentare sind dort
> bewusst ausführlich) und in den Commit-Nachrichten. Dieses Register ist
> der Index, nicht der Ersatz.

---

## A. Die Strategie — was gemessen ist

| Befund | Zahl | Quelle |
|---|---|---|
| Umkehr-Faktoren sind über 9 Jahre stabil | `reversal_3d` IC +0,018, `rsi2` +0,016, `ausverkauf` +0,010 — jeweils 100 % positive Jahre | `signals.ReversalWeights`, Messlauf über 2.162 Symbole |
| Kein Einzelfaktor im Projekt kam je über IC 0,05 | Bester: 0,018 | `signals.py` |
| Die fünf Umkehr-Bausteine messen im Kern **dasselbe** | stark korreliert — die Summe ist NICHT fünfmal so viel Signal | `signals.ReversalWeights` |
| Vorsprung je Trade | **+0,11 %** | `docs/schattenbetrieb.md` |
| Der Effekt lebt auf **3–5 Tagen** | deshalb `max_hold_days=5` | `EngineConfig.for_reversal` |
| Momentum-Strategie war unterlegen | im Test schlechter als Umkehr | `EngineConfig.strategy` |
| Umkehr wirkt NICHT bei den 150 liquidesten Werten | `rsi2` dort nur 29 % positive Jahre | `universe.load_universe` |

### Der zentrale Konflikt

**Vorsprung +0,11 % je Trade gegen Rundlauf-Breakeven 0,142 % bei 5 bps
Spread** (gemessen 04.08.2026, `costs.breakeven_move_pct`). Die Strategie
ist bei realistischen Kosten **nicht nachweislich kostentragfähig**. Das
deckt sich mit dem Befund „Kosten fressen 72–109 % des Bruttogewinns"
(`docs/schattenbetrieb.md` §0.2).

**Folge:** Jede Änderung, die den Umschlag erhöht, muss zuerst zeigen,
dass sie den Vorsprung stärker hebt als die Kosten.

---

## B. Methodische Fallen — teuer gelernt

### B1. Überlappung: die wichtigste Falle

**Datum:** 15.08.2026. **Betrifft:** jede Auswertung.

Vorhersagen desselben Handelstages sehen denselben Markt und sind **keine
unabhängigen Beobachtungen**. Dieselben Daten, zwei Ergebnisse:

```
Naiv    (926 Vorhersagen als 926 Beobachtungen):  +0,744 %   t = 2,63
Ehrlich (je Tag mitteln, dann über 8 Tage):       +0,464 %   t = 1,45
```

Ebenso bei Trades: Am 04.08.2026 wurden **zehn Positionen am selben Tag**
geschlossen. „10 von 13 Fällen" sind faktisch **drei** Beobachtungen.

**Regel:** Immer `statistik.gruppierter_test` verwenden. Maßgeblich ist
die Zahl der **Gruppen** (Handelstage), nie die Zahl der Einzelwerte.
Der naive t-Wert ist nicht „zu hoch", sondern bedeutungslos — er kann in
beide Richtungen abweichen (Schatten: 2,63 statt 1,45; Zeitausstieg: 0,17
statt 1,61).

### B2. Viele Versuche erzeugen Scheingewinner

Bei N Versuchen liegt das erwartete Maximum allein durch Zufall bei
`sqrt(2·ln N)`. Aktuell 12 Versuche → **Schwelle t > 2,73**
(`fleet.schwelle_sigma`). Ein t-Wert darunter ist der Normalfall, kein
Befund. Stillgelegte Bots zählen dauerhaft mit.

### B3. Publizierte Anomalien replizieren meist nicht

~65 % fallen bei sauberer Nachprüfung durch (Hou/Xue/Zhang 2020),
publizierte Effekte verlieren im Mittel ~58 % (McLean/Pontiff 2016).
**Regel:** Externe Behauptung = Hypothese, nie Signal.

### B4. Ein guter Probelauf beweist nichts

**Datum:** 04.08.2026, PEAD-Test. Auf 60 Symbolen: IC 0,032, t=6,7, mit
lehrbuchmäßigem Zerfallsprofil — besser als der beste bestehende Faktor.
Auf 800 Symbolen brach es vollständig zusammen. **Regel:** Probeläufe auf
kleinen Universen dienen dem Testen der Mechanik, nie der Bewertung.

### B5. yfinance schreibt die Vergangenheit um

`get_earnings_dates()` liefert die **heutige** Analystenschätzung, nicht
die vom Meldetag. Für Screening brauchbar, als Beleg nicht.

---

## C. Widerlegt — nicht erneut versuchen

| Hypothese | Ergebnis | Datum |
|---|---|---|
| **PEAD über Analysten-Überraschung** (`H01`) | IC 0,011 — aber Zerfallsprofil **falsch herum** (nichts in den ersten 10 Tagen, Effekt erst ab Tag 20). Keine Meldungswirkung, sondern dauerhafte Symboleigenschaft. Vorzeichen 2021/2022 negativ. | 04.08.2026 |
| **PEAD über Kursreaktion** (`H02`) | IC **−0,010** (t=−6,5) — Richtung entgegengesetzt. Sieht nach Umkehr aus, also dem, was der Bot ohnehin handelt. | 04.08.2026 |
| **Symbol-Aufteilung auf mehrere Bots** | Mathematisch ≈ „ein Bot mit N·15 Positionen", nur mit **schlechterer Auswahl** (Rangliste künstlich in Töpfe zerschnitten). Zudem existieren keine 3×1.200 liquiden Symbole — nur 2.189 ab 1 Mio. $/Tag. | 04.08.2026 |

---

## D. Gemessen, aber (noch) nicht belastbar

| Frage | Stand | Schwelle |
|---|---|---|
| Länger halten (10 statt 5 Tage)? | `B04_halten_lang`: **t = 0,94** über 10 Tage | t > 2,73 |
| Mehr Positionen (25 statt 15)? | `B07`: **t = −2,42** — Tendenz **negativ** | t > 2,73 |
| Voll investieren / Nachkauf? | `B08`/`B09`: t = 0,14 | t > 2,73 |
| Vorsprung der Rangliste gegen Universum | +0,46 %/5 Tage, **t = 1,45** über 8 Tage | t > 2 |

**Keiner dieser Werte rechtfertigt derzeit eine Regeländerung.**

---

## E. Wirkungslose Parameter — überraschende Befunde

**Datum:** 15.08.2026, Flottenvergleich über `shadow_exits`.

| Bot | Änderung | Wirkung | Warum |
|---|---|---|---|
| `B01_stop_eng` | `stop_atr` 2,0 → 1,5 | **keine** | In 14 Tagen wurde **kein einziger Stop ausgelöst** |
| `B02_stop_weit` | `stop_atr` 2,0 → 3,0 | **keine** | dito |
| `B03_ziel_weit` | `target_atr` 2,0 → 3,0 | **keine Renditewirkung** | Ausstieg erfolgt am **selben Tag zum selben Kurs**, nur mit anderem Etikett: Die Score-Regel (`exit_score`) feuert gleichzeitig |
| `B05_schwelle_hoch` | `min_score` 0,35 → 0,50 | **keine** | Alle 39 Käufe hatten Score ≥ 0,678 — die Schwelle bindet nie |
| `B06_ohne_regime` | Regimefilter aus | **keine** | Markt war durchgehend bullisch, der Filter greift nur im Bärenmarkt |

**Die wichtigste Folge:** `target_atr` zu erhöhen bringt **nichts**,
solange `exit_score` gleichzeitig auslöst. Wer Gewinne laufen lassen
will, muss an der **Ausstiegs-Reihenfolge** ansetzen, nicht am Zielwert.

Aufteilung der Ausstiege (B00, Spiegelbuch, 24 Trades):
**15× Zeitausstieg (62 %)**, 5× Score-Regel, 4× Gewinnziel.
→ Der **Zeitausstieg dominiert**. Er ist der einzige Hebel, der wirkt.

---

## F. Die 3-Tage-Sperre — was sie wirklich kostet

**Datum:** 15.08.2026. **Anlass:** Verdacht, sie blockiere starke Werte.

Gemessen über alle 24 Verkäufe im Schatten: In den 3 Tagen nach einem
Verkauf tauchten nur **3 Symbole** erneut als Kandidat auf — auf **Rang
25, 37 und 54**. Gekauft werden nur die **Top 15**.

**Die Sperre hat in 14 Tagen real nichts gekostet.** Sie verhindert
dagegen nachweislich einen teuren Fehler: Ohne sie verkaufte der Bot
AMKR am 28.07. dreimal in 90 Minuten und kaufte jedes Mal sofort zurück
— identischer Stop, identisches Ziel, nur doppelte Kosten.

---

## G. Behobene Fehler — Chronik

Damit derselbe Fehler nicht in anderer Form wiederkehrt.

| Datum | Fehler | Kernursache |
|---|---|---|
| 29.07. | AMKR-Rückkaufschleife | Score nach Verkauf unverändert hoch → Sperrfrist eingeführt |
| 30.07. | Dienst startete nicht (`EX_CONFIG`) | macOS-TCC: launchd darf nicht nach `~/Documents` schreiben → Logs nach `~/Library/Logs` |
| 31.07. | Referenzpreis bei fehlender Quote-Seite | Mittelwert aus echter und fehlender Seite: `(0+45,54)/2 = 22,77` |
| 31.07. | Kapital-Drift zwischen Sizing und Order | Engine rechnete mit Momentaufnahme, Risikoprüfung holte frischen Wert → `position_size_margin` |
| 03.08. | Verkäufe nie mit Füllpreis abgleichbar | `close_position()` verwarf die Broker-Antwort und erfand eine ID |
| 03.08. | Dry-Run-Orders überschrieben sich | Feste ID `"dry-run"` als PRIMARY KEY |
| 04.08. | Slippage-Messung unbrauchbar | Kaputte IEX-Quotes (SIMO 225 statt 261) → Plausibilitätsprüfung gegen letzten Trade |
| 04.08. | yfinance-Tageskontingent verbraucht | `hash()` ist pro Prozess zufällig gesalzen → Cache traf nie. **Fix:** `hashlib` |
| 15.08. | `bars_held` in **jedem** Trade 0 | Wert wird angelegt, nie erhöht; Engine rechnet ihn separat |
| 15.08. | `after_10d` **nie** gefüllt | `pending_analysis` fragte nur `after_5d IS NULL` |
| 15.08. | Score-Bericht lobte negative Korrelation | Nur Betrag geprüft, nicht Vorzeichen |
| 15.08. | Quote-Schwelle zu grob | 5 % ließ 8 Ausreißer (2,1–4,9 %) durch → auf 2 % verschärft |
| 15.08. | Trendbruch-Schwelle als fester Prozentsatz | 2 % hätten an **27,5 %** aller Positionstage ausgelöst — Umkehr-Kandidaten haben Median-ATR 5,16 %. Umgestellt auf 1,0 × ATR (6,0 % Auslöserate) |
| 15.08. | `max_hold_days_hart` wirkte außerhalb seines Schalters | Ohne `zeitausstieg_dynamisch` bekam eine Position ab Tag 20 das Etikett `zeitausstieg_hart`; bei der Momentum-Konfiguration (`max_hold_days=60`) sogar immer. Gleiche Entscheidung, falscher Grund im Protokoll → verfälschte Auswertung nach Ausstiegsgründen |

**Muster, das sich wiederholt:** Die meisten Fehler waren **Protokoll-
und Auswertungsfehler**, nicht Handelsfehler. Der Bot handelte korrekt,
aber die Messung log. Das ist gefährlicher als ein offensichtlicher
Absturz — deshalb prüft `data_integrity.py` inzwischen automatisch.

---

## G2. Das Risiko-Dach — warum die Einzahlungsbereinigung entscheidend ist

**Datum:** 15.08.2026, beim Bau von `risiko.py` gemessen.

Ohne Bereinigung um Ein-/Auszahlungen ist die Drawdown-Sperre genau dann
wirkungslos, wenn am meisten Kapital im Spiel ist. Verifiziert:

| Schritt | Konto | Drawdown **mit** Bereinigung | **ohne** |
|---|---|---|---|
| Start | 100.000 | 0 % | 0 % |
| +50.000 eingezahlt | 150.000 | **0 %** (kein Scheingewinn) | 0 % |
| Verlust auf | 125.000 | **25 % → Sperre** | 16,7 % → **keine Sperre** |

Derselbe reale Verlust hätte ohne Bereinigung die Grenze nicht gerissen.
Ebenso bei der Rendite: naiv **+25 %**, zeitgewichtet **−16,67 %**.

**Folge:** `risiko.py` hängt zwingend an `state.kapitalfluesse`. Fällt die
Kapitalfluss-Erfassung aus, ist die Sperre nicht mehr verlässlich.

Weiter gilt: **Dividenden (DIV) und Zinsen (INT) werden NICHT
herausgerechnet** — sie sind echter Ertrag des eingesetzten Kapitals. Nur
CSD/CSW verändern die Bezugsgröße.

---

## H. Betrieb — was sich bewährt hat

| Erkenntnis | Detail |
|---|---|
| Dauerbetrieb funktioniert | 11 Tage ununterbrochen (04.–15.08.), 1 Fehler (HTTP 500), automatisch abgefangen |
| Datenbanken NICHT unter `~/Documents` | macOS-TCC blockiert Hintergrunddienste dort |
| `RateLimiter` ist **prozesslokal** | Nur Tageslimits liegen auf Platte. N Prozesse ⇒ N× Minutenrate |
| Ein Zyklus über 1.201 Symbole | ~158 s; ~61 Requests |
| Symbolvorrat (gemessen 04.08.) | 8.464 handelbar → **2.189** ab 1 Mio. $/Tag Umsatz |
| Laptop ist kein Server | MacBook schläft bei geschlossenem Deckel — dann läuft **nichts**, auch kein Neustart |

---

## I. Offene Fragen mit laufender Messung

| Frage | Wo gemessen | Nötig |
|---|---|---|
| Trägt die Strategie nach echten Kosten? | `journal.slippage_report()` | 30+ saubere Orders, Median < 8 bps |
| Länger halten? | `B04_halten_lang` | t > 2,73 |
| Dynamischer Ausstieg statt fixer 5 Tage? | **noch nicht angemeldet** | siehe `docs/auswertung-august.md` |
| Mehr Breite? | `B07_mehr_positionen` | derzeit t = −2,42 (negativ) |

---

## J. Feste Regeln — aus Schaden gelernt

1. **Keine Regeländerung unter 30 Beobachtungen je Gruppe** — und
   „Gruppe" heißt Handelstage, nicht Trades (siehe B1).
2. **Voranmeldung vor jedem Test.** Ohne sie ist ein späterer Treffer
   nicht von einer nachträglichen Erzählung zu unterscheiden.
3. **Live wird nur, was im Schatten bestanden hat.**
4. **Jede Kennzahl gegen eine Benchmark.** Ein positiver Nachlauf im
   steigenden Markt beweist nichts — nur der Überschuss zählt.
5. **Ein Parameter je Bot.** Sonst ist keine Zuordnung möglich.
6. **Fehler im Protokoll sind so ernst wie Fehler im Handel.** Eine
   falsche Messung führt zu falschen Entscheidungen mit echtem Geld.
