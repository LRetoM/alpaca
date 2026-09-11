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
| Umkehr-Faktoren sind über 9 Jahre stabil | `reversal_3d` IC +0,018, `rsi2` +0,016, `ausverkauf` +0,010 — jeweils 100 % positive Jahre. **Die t-Werte dieses Laufs sind zu hoch** (§G12); die Vorzeichenstabilität je Jahr ist davon unberührt und trägt den Befund | `signals.ReversalWeights`, Messlauf über 2.162 Symbole |
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

**Und das reicht nicht allein.** Bei einem Renditefenster über mehrere
Tage überlappen sich zusätzlich die **benachbarten Gruppen** — dagegen
hilft Mitteln nicht. Dann gehört `horizont=` dazu (§G12). Ohne das
Argument liegt die Fehlalarmquote bei 5-Tage-Fenstern nicht bei 5 %,
sondern bei **39,5 %**.
Der naive t-Wert ist nicht „zu hoch", sondern bedeutungslos — er kann in
beide Richtungen abweichen (Schatten: 2,63 statt 1,45; Zeitausstieg: 0,17
statt 1,61).

### B2. Viele Versuche erzeugen Scheingewinner

Bei N Versuchen liegt das erwartete Maximum allein durch Zufall bei
`sqrt(2·ln N)`. Maßgeblich ist **`fleet.schwelle_sigma()`** — hier steht
bewusst keine Zahl. Ein t-Wert darunter ist der Normalfall, kein Befund.
Stillgelegte Bots zählen dauerhaft mit.

```
python scripts/21_fleet.py     # weist Versuchszahl und Schwelle aus
```

> **Warum hier keine Zahl mehr steht (23.08.2026, §G19 Fund 2).** Bis
> dahin stand an dieser Stelle „Aktuell 12 Versuche → Schwelle t > 2,73".
> Beides war überholt: 16 Versuche, Schwelle **2,85**. Die Zahl war an
> fünf Stellen dieses Dokuments abgeschrieben und **überall zu niedrig** —
> ein Register, das die Hürde senkt, gegen die es messen soll. Genau
> davor warnt `BETRIEBSPLAN` §3.2: *„Eine abgeschriebene Zahl im Dokument
> wäre nach der nächsten Anmeldung falsch und würde die Hürde
> nachträglich senken."* Sie war es bereits.

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

## B6. Die Bilanz aller Versuche — die wichtigste Zahl für jede Planung

**Stand 23.08.2026.** Diese Aufstellung existiert, weil die Einzelbefunde
über das ganze Register verstreut sind und in der Summe etwas sagen, was
keiner von ihnen allein sagt.

| Versuch | Anzahl | bestanden |
|---|---:|---:|
| Flottenbots (`B00`–`B12`) | 13 | **0** |
| Registrierte Hypothesen | 3 | 0 |
| Faktorkandidaten (§C, 16.08.) | 18 | 0 |
| PEAD über Analysten / Kursreaktion (§C) | 2 | 0 (beide widerlegt) |
| Symbol-Aufteilung auf mehrere Bots (§C) | 1 | 0 (widerlegt) |
| ML-Modell gegen den Score (§G15) | 1 | 0 (verworfen) |
| **Summe (Stand 23.08.)** | **38** | **0** |

**Fortschreibung nach dem 23.08.2026** — die Tabelle oben bleibt stehen,
damit die Zahl von damals nachvollziehbar bleibt:

| Versuch | Anzahl | bestanden | § |
|---|---:|---:|---|
| Lernlauf-Achsen, 15 Jahre (25.08.) | 14 | 0 | §G33 |
| FRED-Makro + GDELT, Bänder (25.08.) | 10 | 0 | §G35 |
| Limitorder statt Marktorder (26.08.) | 1 | 0 | §G40 |

**Die Gesamtzahl hängt davon ab, wie die Überschneidung gezählt wird —
und deshalb steht hier eine Spanne, keine glatte Zahl:**

| Zählweise | Summe | bestanden |
|---|---:|---:|
| ohne die Lernlauf-Achsen (sie prüfen teils dieselben Achsen wie `B04`, `B06`, `B11` auf anderen Daten) | **49** | **0** |
| mit allen 14 Lernlauf-Achsen als eigene Versuche | **63** | **0** |

> `docs/UEBERGABE.md` nannte am 26.08. „48". Das war die erste Zählweise
> vor dem Limitorder-Lauf. Welche der beiden man nimmt, ändert an der
> Aussage nichts: **Der Zähler für „bestanden" steht in jeder Zählweise
> auf null.** Wer aus der Uneindeutigkeit die kleinere Zahl wählt, senkt
> die eigene Hürde — deshalb ist im Zweifel die größere maßgeblich.

Die 13 Flottenbots im Detail:

* **4 wirkungslos, stillgelegt** — `B01`, `B02`, `B03`, `B05` (§E)
* **4 bitgleich mit ihrer Referenz** — `B03`, `B05` (stillgelegt),
  `B06`, `B09` (laufend). Sie messen strukturell **nichts**
* **3 unter der Schwelle** — `B04` (0,41×), `B07` (−0,89×), `B08`
  (0,22× der Nachweisgrenze, §G22)
* **2 zu neu** — `B11`, `B12`
* **1 ersetzt** — `B10`

### Was daraus folgt — und was nicht

**Das ist kein Scheitern, sondern die Basisrate.** §B3 nennt sie für
publizierte Anomalien: ~65 % replizieren nicht, der Rest verliert im
Mittel 58 % seiner Wirkung. Für selbst erdachte Parametervarianten ist
sie noch schlechter. Wer diese Bilanz für ungewöhnlich hält, wird die
nächsten zwanzig Versuche falsch einplanen.

**Jeder Versuch verteuert alle anderen — dauerhaft.** `schwelle_sigma`
wächst mit `sqrt(2·ln N)`, stillgelegte Bots zählen weiter mit (§B2):

```
16 Versuche -> 2,85      21 Versuche -> 2,97
19 Versuche -> 2,93      24 Versuche -> 3,02
```

Und die Erhöhung wirkt **rückwirkend auf jede laufende Messung**. Fünf
neue Achsen auf einmal anzumelden macht also nicht fünf Fragen
beantwortbar — es macht die eine, die gerade läuft, schwerer.

### Die Unterscheidung, an der alles hängt

|  | Messapparat | Handelslogik |
|---|---|---|
| Beispiele | Protokoll, Wächter, Auswertung, Werkzeuge | `EngineConfig`, Ausstiegsregeln, Universum |
| Kosten | keine | **ein Versuchszählerplatz, dauerhaft** |
| Wann | jederzeit | nur vorangemeldet, eine Achse |
| Basisrate | — | **0 von 38** |

Am Messapparat darf und soll laufend gearbeitet werden — die Runden
§G13–§G22 haben genau das getan, ohne eine einzige Handelsentscheidung
zu berühren. **Ein „Code 2.0", der beides vermischt, kostet die
Vergleichsbasis und hebt die Hürde für alles Laufende.**

### Der eigentliche Engpass ist nicht die Feinjustierung

§A: Vorsprung **+0,11 % je Trade** gegen Rundlauf-Breakeven **0,142 %**.
§C stellt fest, dass der Faktorraum aus Kurs- und Volumendaten
**vermutlich ausgeschöpft** ist — die 18 Kandidaten entdeckten
überwiegend den bereits gehandelten Umkehr-Effekt neu.

Keine der 13 Flottenachsen adressiert diesen Konflikt. Sie justieren
Stop, Ziel, Frist, Breite und Kapitaleinsatz — alles Randbedingungen
eines Vorsprungs, der zu klein ist. Neue Information müsste von
**außerhalb** der Kursdaten kommen (Nachrichten, Insider,
Fundamentaldaten), nicht aus einer weiteren Ableitung derselben Reihe.


---

## C. Widerlegt — nicht erneut versuchen

| Hypothese | Ergebnis | Datum |
|---|---|---|
| **PEAD über Analysten-Überraschung** (`H01`) | IC 0,011 — aber Zerfallsprofil **falsch herum** (nichts in den ersten 10 Tagen, Effekt erst ab Tag 20). Keine Meldungswirkung, sondern dauerhafte Symboleigenschaft. Vorzeichen 2021/2022 negativ. | 04.08.2026 |
| **PEAD über Kursreaktion** (`H02`) | IC **−0,010** (t=−6,5) — Richtung entgegengesetzt. Sieht nach Umkehr aus, also dem, was der Bot ohnehin handelt. | 04.08.2026 |
| **Symbol-Aufteilung auf mehrere Bots** | Mathematisch ≈ „ein Bot mit N·15 Positionen", nur mit **schlechterer Auswahl** (Rangliste künstlich in Töpfe zerschnitten). Zudem existieren keine 3×1.200 liquiden Symbole — nur 2.189 ab 1 Mio. $/Tag. | 04.08.2026 |

| **Tauschregel: schwaechste Position gegen besseren Kandidaten** | Ueber 7 Jahre t = +0,85, ueber 5 Jahre t = −0,50 — Vorzeichen nicht stabil. Und die Regel verkauft zu **80 % Gewinner**: Der Umkehr-Score misst „wie ueberverkauft", eine erholte Position rutscht damit automatisch ans Ende der Rangliste. Nicht widerlegt, sondern falsch operationalisiert (§G28). | 24.08.2026 |
| **18 neue Faktorkandidaten** (16.08.2026) | Struktur, Lücken, Volumen, Marktbezug — **keiner** besteht. Zwei erreichten \|t\|>2 (`bewegung_je_volumen` IC +0,013 t=2,06; `aufwaertstage_5` IC −0,012 t=−2,13), scheiterten aber an der Jahresstabilität (7/9 bzw. 3/9 Jahre). Gemessen über 8 Jahre, 789 Symbole, ~2.000 Handelstage. | 16.08.2026 |

**Aufschlussreich am Vorzeichen:** `aufwaertstage_5` (−0,012),
`rel_staerke_5` (−0,015) und `beschleunigung_5_10` (−0,012) sind alle
**negativ** — wenige Aufwärtstage, schwache relative Stärke und
nachlassende Beschleunigung sagen *höhere* Folgerenditen voraus. Das ist
schlicht der Umkehr-Effekt in anderer Verpackung, den der Bot bereits
handelt. Die Kandidaten entdecken das bestehende Signal neu, statt neue
Information zu liefern.

**Methodischer Wert des Negativergebnisses:** Er bestätigt die Kalibrierung
aus §A — kein Einzelfaktor dieses Projekts kam je über IC 0,05, und der
Faktorraum aus Kurs- und Volumendaten ist damit vermutlich ausgeschöpft.
Neue Information müsste von **außerhalb** kommen (Nachrichten, Insider,
Fundamentaldaten), nicht aus einer weiteren Kursableitung.

---

## D. Gemessen, aber (noch) nicht belastbar

**Die laufenden Stände stehen bewusst nicht mehr hier.** Sie ändern sich
täglich; eine abgeschriebene Zahl ist innerhalb einer Woche falsch
(gemessen: alle drei Flottenzeilen dieser Tabelle waren es am
23.08.2026, §G19 Fund 2). Abrufen:

```
python scripts/27_status.py    # alle Bots gegen ihre registrierte Referenz
python scripts/21_fleet.py     # Versuchszahl und Schwelle
```

| Frage | Wo abzulesen | Schwelle |
|---|---|---|
| Länger halten (10 statt 5 Tage)? | `B04_halten_lang` | `fleet.schwelle_sigma()` |
| Mehr Positionen (25 statt 15)? | `B07_mehr_positionen` — Tendenz **negativ** | `fleet.schwelle_sigma()` |
| Voll investieren? | `B08_voll_investiert` | `fleet.schwelle_sigma()` |
| Nachkauf? | `B09_nachkauf` — **misst nichts**, bitgleich mit `B08` (§G16 Fund 1) | — |
| Vorsprung der Rangliste gegen Universum | `17_shadow_report.py` | t > 2 |

**Keiner dieser Werte rechtfertigt derzeit eine Regeländerung.** Der
Momentaufnahme halber, ausdrücklich **datiert und nicht fortzuschreiben**
(23.08.2026, Schwelle 2,85): B04 t = +1,26 über 14 Tage, B07 t = −1,93
über 13, B08 t = +0,70 über 13, B11 t = +1,24 über 4.

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

**21.08.2026 — B01, B02, B03, B05 stillgelegt.** Der Befund war seit
15.08. unverändert (diff_mittel exakt 0,0 gegen B00 über inzwischen 13
Handelstage) — mehr Kalenderzeit ändert daran strukturell nichts, das
Ergebnis ist fertig. `fleet.stilllegen()` entfernt sie nicht, sie zählen
weiter im Versuchszähler (`fleet.n_versuche`). Weiterlaufen bleiben nur
Bots, die noch echte Information sammeln (B04, B07, B08, B09, B11) oder
auf einen Regimewechsel warten (B06 — wirkungslos im Bullenmarkt, aber
keine tote Achse, siehe §G7/§G8).

**Ersatz angemeldet: `B12_schwelle_kalibriert`.** Derselbe Grund, warum
B05 nie band: `min_score=0,50` lag weit unter dem, was echte Käufe je
erreichen. Gemessen an B00s tatsächlichen Käufen (Spiegelbuch, n=51):
Median-Score 0,97, Minimum 0,66, 25%-Quantil 0,87. `min_score=0,80`
filtert damit **21,6 %** der bisherigen Käufe — bindet also tatsächlich,
anders als der alte Wert. Startet bei 0 Tagen, braucht wie jeder neue Bot
~20 Handelstage. **Jeder neue Versuch hebt die Schwelle für alle** —
2,83 → 2,85 nach dieser Anmeldung.

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

## G3. Der Stop wirkte nur einmal am Tag — Reaktionszeit bis 24 Stunden

**Datum:** 15.08.2026. **Schwere:** hoch, betraf jede offene Position.

`build_snapshot` verwirft bewusst die unfertige Tagesbar, damit
Einstiegssignale auf denselben Kursen beruhen, auf denen sie gemessen
wurden. Verifiziert am 15.08.: Der Bot rechnete mit dem **Stichtag
14.08.** — also dem Vortagesschluss.

Für Einstiege ist das richtig. Für Stops war es gefährlich:

| Ereignis | Reaktion **vorher** |
|---|---|
| Aktie stürzt heute 30 % ab | **erst am nächsten Handelstag** |
| Gap-Down über Nacht | am selben Tag |

Erschwerend: Der Live-Bot sendet ausschließlich `market_order` — es lag
**keine Stop-Order beim Broker**, die intraday ausgelöst hätte. Es gab
also innerhalb eines Tages überhaupt keinen Schutz.

**Und die Messung log:** `shadow.py` rechnet seit jeher mit
Intraday-Stops (`if bar["low"] <= pos.stop_price`). Die Schattenergebnisse
haben den Verlustschutz damit **systematisch überschätzt** — genau in den
teuersten Fällen.

**Behoben** durch `live.pruefe_stops_intraday()`: prüft jeden Zyklus
(~15 Min) die Stop-Marken gegen den aktuellen Kurs. Damit stimmen Live
und Schatten erstmals überein.

Bewusste Abgrenzung — **nur der Stop**, nicht die übrigen Ausstiege:

| Regel | Bezugskurs | Warum |
|---|---|---|
| Stop | **aktuell** | Notbremse, kein Signal — keine Backtest-Rechtfertigung für Verzögerung |
| Gewinnziel | Tagesschluss | Chance, kein Risiko |
| Score-Ausstieg | Tagesschluss | ist ein Signal, auf Tagesschlusskursen gemessen |
| Zeitausstieg | Tagesschluss | datumsbasiert |

**Schutz gegen Fehlauslösung:** Verkauft wird nur auf eine als plausibel
geprüfte Quote hin. Eine veraltete IEX-Quote meldete am 04.08. SIMO mit
225 statt 261 — ein Stop-Verkauf darauf wäre ein realer Verlust aus einem
reinen Datenfehler gewesen.

**Restrisiko:** Läuft der Bot nicht (Rechner aus, Absturz), greift auch
dieser Stop nicht. Echte Stop-Orders beim Broker wären der nächste
Schritt — sie wirken auch bei totem Bot.

---

## G4. Live gegen Schatten — jeder bekannte Unterschied

**Datum:** 15.08.2026, systematisch abgeglichen. **Warum das zählt:** Der
Schatten ist die Messung, Live die Realität. Jeder Unterschied bedeutet,
dass die Messung etwas anderes misst als das, was passiert.

| Aspekt | Live | Schatten | Stand |
|---|---|---|---|
| **Intraday-Stop** | jetzt ja (~15 Min) | ja (`bar["low"]`) | **behoben 15.08.** |
| **Kursdaten** | Alpaca/IEX | yfinance | **bewusst** — gehandelt wird bei Alpaca, geforscht mit freien Daten |
| **Kosten** | echte Spreads | 5 bps + 3 bps angenommen | **bewusst** — die Annahme wird gegen `slippage_report()` geprüft |
| **Ausführung** | Market-Order im Tagesverlauf | Eröffnungskurs des Folgetags | **offen** — Schatten nimmt einen günstigeren Zeitpunkt an |
| **Risiko-Dach** | ja (seit 15.08.) | nein | **offen** — Schatten kennt keine Sperre, überschätzt damit im Crash |
| **PDT-Regeln** | ja (`compliance`) | nein | gering — greift erst unter 25.000 $ |
| **Codeversion** | jetzt erfasst | jetzt erfasst | **behoben 15.08.** |
| **Haltedauer-Zählung** | echte Handelstage (`handelskalender`) | echte Bars | **behoben 26.08.** — §G38, vor dem ersten Auftreten am 07.09. |

**Die zwei offenen Punkte überschätzen beide den Schatten**, nie den
Live-Bot — die Messung ist also optimistisch, nicht pessimistisch. Das
ist die ungefährlichere Richtung, aber es heißt: Ein im Schatten knapp
bestandener Bot ist live noch nicht bestanden.

**Nachtrag 26.08.2026:** Die letzte Zeile war die erste dieser Tabelle,
die die **Handelslogik** betraf und nicht die Messbedingungen — der
Live-Bot hätte in Feiertagswochen einen Handelstag früher verkauft als
jede Messung, gegen die er verglichen wird. Für sie galt der Trostsatz
oben also nicht. Noch am selben Tag behoben (§G38), bevor sie zum ersten
Mal greifen konnte.

---

## G5. Versionserfassung war zwei Monate lang kaputt

**Datum:** 15.08.2026. **Genau die Fehlerart, gegen die dieses Register
existiert.**

`shadow.code_version()` bestimmte den Git-Commit mit
`cwd=DATA_DIR.parent`. Solange die Datenbanken im Projektordner lagen,
stimmte das zufällig. Der Umzug nach `~/Library/Application Support`
(30.07., wegen TCC-Dateischutz) zeigte auf ein Verzeichnis **ohne Git** —
seitdem lieferte die Funktion stumm `'unbekannt'`.

**8.278 von 12.516 Vorhersagen (66 %) ohne Versionszuordnung.** Der
Fehler hat sich nie gemeldet; er war nur sichtbar, wenn man gezielt danach
sah.

**Folge für die Auswertung:** Für zwei Drittel der Schattendaten lässt
sich nicht mehr sagen, welcher Codestand sie erzeugt hat — ein
Versionsvergleich ist dort unmöglich.

**Behoben:** `config.code_version()` ist jetzt die einzige Quelle für
beide Pfade und bezieht sich fest auf `PROJECT_ROOT`. Zusätzlich erfasst
das Live-Journal die Version je Lauf (`runs.code_version`) — vorher gar
nicht. Auswertung über `versionen.bericht()`.

---

## G6. Die Flotten-Referenz war seit über zwei Wochen falsch

**Datum:** 16.08.2026, gefunden auf direkte Nachfrage "stimmt alles mit
Schatten und Live überein?". **Schwere: hoch** — betraf die Vergleichsbasis
fast der gesamten Flotte.

`B00_basis` trägt die Behauptung „Entspricht exakt der Einstellung des
Live-Bots". Das stimmte am 29.07., dem Tag der Anmeldung — **seit dem
30.07.2026 nicht mehr**: `scripts/12_daemon.py` änderte an diesem Tag
seine Standardwerte auf `deploy_to_target=True` und `allow_topup=True`
(Commits `3e3d30e`, `f253724`). `B00_basis` blieb bei `False`/`False`
stehen.

**Ausmaß:** 8 der 10 Flottenbots (`B01`–`B07`, `B10`) vergleichen sich
gegen `B00`. Über zwei Wochen lang bezog sich „Referenz = Live" auf eine
Konfiguration, die live gar nicht mehr lief.

**Einordnung — nicht so schlimm wie es klingt:** Die Vergleiche
`B01`–`B07` gegen `B00` bleiben **intern gültig**: Beide Seiten jedes
Vergleichs teilten dieselbe `False`/`False`-Basis, die eine getestete
Achse (`stop_atr`, `target_atr`, …) war jeweils sauber isoliert. Falsch
war nur die Behauptung, das Ergebnis sage etwas über den *tatsächlichen*
Live-Bot aus.

**Der Zufallsfund, der die Reparatur einfach machte:** `B09_nachkauf`
(`deploy_to_target=True, allow_topup=True`, sonst Standard) ist seit dem
30.07. **zufällig exakt deckungsgleich** mit der echten Live-Konfiguration
— registriert um 18:30 Uhr desselben Tages, kurz nachdem der Live-Standard
umgestellt wurde, aber als Investitionsgrad-Experiment gegen `B08`
geführt, nie als Live-Spiegel erkannt.

**Behoben:**
- `B00_basis` und `B09_nachkauf`: Hypothesentext in Code **und** laufender
  Datenbank korrigiert (Registrierungen sind unveränderlich für die
  Konfiguration, der Beschreibungstext war nachträglich korrigierbar).
- `B10_dyn_ausstieg` (16.08. registriert, 1 Tag alt, keine verwertbaren
  Daten) **stillgelegt** — verglich gegen die falsche Basis.
- `B11_dyn_ausstieg_live` neu angemeldet: identische Idee, aber gegen
  `B09_nachkauf` verglichen. Verifiziert bitweise: unterscheidet sich von
  der echten Live-Konfiguration in **exakt einem** Feld
  (`zeitausstieg_dynamisch`).

**Lehre:** „Entspricht dem Live-Bot" ist eine Behauptung, die verfällt,
sobald sich der Live-Standard ändert — sie muss bei jeder Änderung an
`scripts/12_daemon.py`s Voreinstellungen neu geprüft werden, nicht nur
einmal bei der Registrierung.

---

## G7. Regimefilter löst auch Verkäufe aus — nicht nur Käufe

**Datum:** 16.08.2026. **Bisher nirgends dokumentiert.**

`ReversalWeights.market_regime_filter` ist als Kaufsperre dokumentiert
("Nur kaufen, wenn der Gesamtmarkt über seinem 200-Tage-Schnitt liegt").
Verifiziert am Code (`signals.py`): Der Filter setzt den Score aber nicht
nur für NEUE Kandidaten auf 0, sondern für ALLE Symbole — und derselbe
Score wird auch für die Ausstiegsregel `exit_score` verwendet
(`engine._check_exits`).

**Getestet mit einer Engine-Instanz:** Eine Aktie mit einem klaren,
starken Umkehr-Setup (−30 % in 20 Tagen) wurde bei SPY unter seinem
200-Tage-Schnitt sofort verkauft, Grund `these_traegt_nicht_mehr`, Score
exakt 0,0 — obwohl das Einzelsignal stark war.

**Folge:** Kippt der Markt, würde das gesamte Depot in einem einzigen
Zyklus komplett liquidiert, unabhängig vom Zustand der Einzelpositionen.
Kein bewusst designtes Verhalten, sondern ein Nebeneffekt der geteilten
Score-Berechnung zwischen Kauf- und Verkaufslogik.

**Noch nicht geändert** — betrifft Handelslogik, erst im Schatten prüfen
(z. B. eigener Bot: Regimefilter nur beim Einstieg, nicht beim Ausstieg).

## G8. Wie lange kann der Bot komplett in Cash sitzen?

**Datum:** 16.08.2026, gerechnet an 9 Jahren echten SPY-Kursen.

Liegt SPY unter seinem 200-Tage-Schnitt, kauft der Bot nichts Neues
(Score aller Kandidaten = 0, siehe G7). Gemessen:

| Zeitraum | Dauer |
|---|---|
| 11.04.–15.08.2022 | ~4 Monate |
| 17.08.–29.11.2022 | ~3 Monate |
| 26.03.–09.05.2025 | ~2 Monate |

**Anteil aller Handelstage 2018–2026 unter dem 200-Tage-Schnitt: 18 %.**
Mehrmonatige Cash-Phasen sind damit erwartbares, kein fehlerhaftes
Verhalten — sollten aber nicht mit einem stehengebliebenen Bot verwechselt
werden, wenn man den Tagesbericht liest.

---

## G9. Zwei vermutete Defekte in der Nachbetrachtung — beide existierten nicht

**Datum:** 21.08.2026. **Wichtig als Warnung, nicht als Fehlermeldung.**

Beim Prüfen der Frage „verkauft der Zeitausstieg zu früh?" wurden zwei
Defekte vermutet und beide widerlegt. Nicht erneut untersuchen:

**1. „Die Marktbereinigung ist nicht verdrahtet."** Falsch. Sie läuft
seit jeher in `scripts/13_tagesbericht.py:222-224`, inklusive korrekter
`tz_localize(None).normalize()`-Aufbereitung. Der Irrtum entstand durch
einen nackten Shell-Aufruf `nachbetrachtung.bericht()` — dessen Default
`markt=None` rechnet Rohzahlen. Der Produktionspfad war nie betroffen.

**2. „Es fehlen Nachlauf-Werte (`after_10d` bei EIX, META, SAIA)."**
Falsch. Es war eine Momentaufnahme im Fenster zwischen „Trade wird
fällig" und „nächster Daemon-Zyklus". Der Nachtrag in `daemon.py:233-272`
schloss sie ohne Zutun. Kontrolle danach: **after_1d 51/51, after_5d
36/36, after_10d 18/18 — kein Loch.** Der Backfill arbeitet korrekt.

**Was tatsächlich geändert wurde:** `bericht()` weist jetzt aus, in
welchem Modus es gerechnet hat („OHNE Marktbereinigung … ROHRENDITE"
bzw. „MARKTBEREINIGT … Überschuss über den Markt"). Vorher stand dort
nur „falls Markt übergeben" — die Tabelle sah in beiden Fällen gleich
aus. Genau diese Zeile („18 von 26") wird am häufigsten zitiert und
führt ihren Bezug jetzt mit. Regressionstest:
`tests/test_ausfuehrung.py::TestBerichtNenntSeinenBezug`.

**Die Zahl, um die es ging** (Zeitausstieg, Nachlauf nach 5 Tagen):

| Rechnung | Mittelwert | t (gruppiert) | Tage |
|---|---|---|---|
| roh (ohne Markt) | +0,93 % | 1,08 | 6 |
| marktbereinigt | **+0,50 %** | **0,60** | 7 |

Die Marktbereinigung halbiert den scheinbaren Effekt. Beide Werte liegen
weit unter der Schwelle (2,85) und weit unter den nötigen 20 Gruppen —
**der Zeitausstieg ist derzeit weder als „zu früh" noch als „richtig"
belegt.** Die Messung dazu läuft als `B11_dyn_ausstieg_live` (§I).

---

## G10. Der Entscheidungstermin 10.10. war unerreichbar — MIN_TAGE gegen §3.3

**21.08.2026.** Eine Prüfung *vor* den Auswertungsterminen fand einen
Widerspruch, der die Entscheidung am 10.10.2026 unmöglich gemacht hätte.

### Der Widerspruch

| Quelle | Aussage |
|---|---|
| `shadow_eval.py` (Konstante `MIN_TAGE`) | **60** auswertbare Tage nötig, steuert die `belastbar`-Flagge in `vergleich_gepaart` |
| `docs/BETRIEBSPLAN.md` §4 (bis 21.08.) | „Die gepaarte Messung braucht laut `shadow_eval.MIN_TAGE` mindestens **20** Tage." |
| `shadow_eval.py`, Docstring derselben Funktion | „A schlägt B ist nach **6–10 Wochen** entscheidbar" (= 30–50 Tage) |

`git log -S 'MIN_TAGE'` belegt: die Konstante stand seit dem **ersten**
Schatten-Commit (`cd46b40`) auf 60. Sie war **nie** 20 — der Betriebsplan
hat sie nie korrekt wiedergegeben.

### Die Folge, in Zahlen

`B11_dyn_ausstieg_live` ist am 18.08.2026 angemeldet. `vergleich_gepaart`
verwirft die jüngsten 20 % der Tage (Sperrzone), gezählt wird danach:

| Termin | rohe Handelstage | auswertbar | `belastbar` bei MIN_TAGE=60 |
|---|---|---|---|
| 12.09.2026 (Zwischenschau) | 19 | 15 | nein |
| **10.10.2026 (Entscheidung)** | **39** | **31** | **nein** |
| ~30.11.2026 | 75 | 60 | ja |

Am vorab festgelegten Entscheidungstermin wäre `belastbar` also zwingend
`False` gewesen — **egal wie gut der t-Wert ist.** Ein Termin, der kein
Ergebnis liefern kann, ist kein Termin.

### Festlegung

Maßgeblich sind die **vier Kriterien aus BETRIEBSPLAN §3.3**. `MIN_TAGE`
(60) bleibt als strengere Hausmarke von `vergleich_gepaart` bestehen,
wird bei jeder Auswertung ausgewiesen — hat aber **kein Vetorecht**.

Das ist bewusst *keine* nachträgliche Absenkung der Hürde: §3.3 verlangt
weiterhin einen t-Wert über `fleet.schwelle_sigma()` und mindestens 20
auswertbare Tage. Geändert wurde nur, welches der beiden widersprüchlichen
Dokumente gilt — und das vor dem Termin, nicht an ihm.

### Zweiter Fund: `verlaengert` wird nirgends gespeichert

§3.3 Kriterium 3 fragt nach dem Anteil **verlängerter** Positionen.
`verlaengert` ist in `engine.py` nur eine lokale Variable. Die Engine
protokolliert das Merkmal zwar abgeleitet als `nach_verlaengerung` in den
Entscheidungsgründen — aber `shadow_exits` hat gar keine Spalte für
Gründe. Ableitung im Schatten: `bars_held > max_hold_days`, wortgleich
zur Engine (`engine.py:815`).

**Diese Ableitung ist in den Echtdaten bisher nirgends belegt.** Kein Bot
der Flotte hat je `bars_held > max_hold_days` erreicht:

| Bot | dyn. Ausstieg | Frist | Ausstiege | max. `bars_held` | verlängert |
|---|---|---|---|---|---|
| `B00_basis` | nein | 5 | 40 | 5 | 0 |
| `B04_halten_lang` | nein | 10 | 26 | 10 | 0 |
| `B10_dyn_ausstieg` | ja | 5 | **0** | — | — |
| `B11_dyn_ausstieg_live` | ja | 5 | 2 | 2 | 0 |

Das ist erwartungskonform (nicht-dynamische Bots verkaufen exakt bei der
Frist, B11 ist erst 3 Tage alt), aber es heißt: die Ableitung ist nur
durch Tests gesichert, nicht durch Beobachtung.

### Werkzeug statt Improvisation

Vorher gab es **keine** Funktion, die die vier Kriterien prüft — am 10.10.
hätte das improvisiert werden müssen. Neu:

```
python scripts/21_fleet.py --kriterien B11_dyn_ausstieg_live
```

Jedes Kriterium hat **drei** Zustände: erfüllt / durchgefallen / **offen**.
`offen` heißt „noch keine Datengrundlage" und zählt nie als Bestehen.

### Dabei gefundener Fehler: eine erfundene Null

Die erste Fassung meldete für `B04_halten_lang` (`zeitausstieg_dynamisch
= False`) „Kriterium 3 **DURCHGEFALLEN**, ist: 0.0". B04 verkauft aber
konstruktionsbedingt exakt bei `max_hold_days` und **kann** nie
verlängern — die Quote war keine Messung, sondern ein Artefakt der
Division. Falsch in der gefährlichen Richtung: eine Null, die wie ein
Befund aussieht. Behoben, steht jetzt als `entfaellt`.

Regression: `tests/test_ausfuehrung.py::TestKriterienPruefen`, 9 Tests.
Gegen fünf Mutationen geprüft (Nenner `>=`→`>`, Zähler `>`→`>=`, `None`
als Bestehen, dyn-Prüfung entfernt, Untergrenze entfernt) — alle fünf
Mutanten wurden von den Tests getötet.

---

## G11. Die Historien-Simulation simulierte einen anderen Bot (21.08.2026)

**Anlass.** Der Schattenbetrieb misst vorwärts und braucht dafür Wochen
(§G10). Die Frage war, ob sich dieselben Fragen rückwärts an Altdaten
beantworten lassen — dann müsste nicht auf jede Messung gewartet werden.
Antwort: ja, aber das dafür vorhandene Werkzeug war unbrauchbar, und zwar
aus sechs unabhängigen Gründen — der fünfte war der erste Reparaturversuch
selbst.

### Fund 1: Falsche Strategie — acht von zehn Feldern wichen ab

`scripts/10_simulate.py` versprach in Zeile 2 wörtlich „exakt der Ablauf
des spaeteren Live-Betriebs" und baute dann `EngineConfig()` — die
Momentum-Voreinstellung. Der Bot fährt `EngineConfig.for_reversal()`.

| Feld | Simulation | Live-Bot |
|---|---|---|
| `strategy` | momentum | **reversal** |
| `max_hold_days` | 60 | **5** |
| `min_score` | 0,55 | **0,35** |
| `exit_score` | 0,35 | **0,10** |
| `stop_atr` | 2,5 | **2,0** |
| `target_atr` | 6,0 | **2,0** |
| `trail_after_atr` | 3,0 | **99,0** (aus) |
| `max_positions` | 12 | **15** |
| `min_dollar_volume` | 2 Mio. | **1 Mio.** |

Sichtbar wurde es an einer einzigen Zahl: die abgelegte
`results/simulation/trades.csv` (821 Trades, 2021–2026) hatte eine
**mittlere Haltedauer von 17,3 Tagen**. Der Live-Bot hält 5.

### Fund 2: Der Marktfilter fiel lautlos aus

`simulate.run()` nimmt einen Parameter `market`. Das Skript übergab ihn
nie. In `signals.build_reversal_frame` steht dafür:

```python
if w.market_regime_filter and market is not None:
    out["markt_ok"] = (mkt > ind.sma(mkt, 200)).astype(float)
else:
    out["markt_ok"] = 1.0
```

Ohne SPY wird `markt_ok` also **1.0** — der Filter verschwindet, ohne zu
werfen und ohne eine Zeile zu protokollieren. Die Simulation kaufte damit
in genau die Einbrüche hinein, die der Live-Bot per Konstruktion
aussitzt. Fehlerrichtung: das Ergebnis wird **besser**, als es wäre. Das
fällt bei einer Auswertung nie von selbst auf.

### Fund 3: Falsches Universum

Simuliert wurde `BENCHMARK_SETS["broad_liquid"]` — 110 fest verdrahtete
Standardwerte. Der Live-Bot handelt `load_universe(max_symbols=1200)`,
also die 1.200 umsatzstärksten von 2.168.
`universe.load_universe` warnt im eigenen Docstring ausdrücklich davor:
die Umkehr-Faktoren waren auf 2.162 Symbolen stabil (100 % positive
Jahre), auf den 150 liquidesten dagegen **nicht** (`rsi2`: 29 % positive
Jahre). Getestet wurde die Strategie also ausgerechnet dort, wo sie
gemessen nicht funktioniert.

### Fund 4: Der Bar-Cache konnte nie treffen

Beim Versuch, den Lauf zu beschleunigen, fiel auf, dass `use_cache=True`
in `data.get_bars` **toter und zusätzlich kaputter Code** war —
projektweit von niemandem aufgerufen, Cache-Verzeichnis leer, während
`compliance.py:235` ausdrücklich zur Nutzung riet. Zwei Fehler in
derselben Zeile:

1. `abs(hash(key))` — Pythons String-`hash()` ist pro Prozess
   randomisiert (`PYTHONHASHSEED`). Nachgemessen: drei Programmstarts,
   drei verschiedene Dateinamen für denselben Abruf. Ein Treffer war
   ausgeschlossen.
2. Der Schlüssel enthielt `start` als vollen Zeitstempel. Bei Aufruf mit
   `lookback_days` ist das `datetime.now()` — **mit Mikrosekunden**. Der
   Schlüssel war damit selbst innerhalb eines Prozesses jedes Mal anders.

Behoben: `data._cache_key` mit sha256 und auf den Tag normalisierten
Zeitangaben. `universe.fetch_history` reicht `use_cache` jetzt durch —
das ist bei einem Lauf über 1.200 Symbole und 7 Jahre der Unterschied
zwischen Minuten und Stunden, und die API-Quote teilen sich Live-Bot,
Schattenbetrieb und jede Auswertung.

### Was das Werkzeug leisten kann — und was nicht

Es kann eine Idee **billig verwerfen**. Es kann sie **nicht bestätigen**.
Zwei Gründe, beide unbehebbar:

* **Survivorship** (`universe.py:1–19`): Alpaca kennt nur heute gelistete
  Symbole. 8–12 % der US-Listings verschwinden pro Jahr, systematisch die
  schlechtesten. Schein-Vorteil 2–4 Prozentpunkte pro Jahr — *mehr, als
  die Strategie je verdienen wird.*
* **Regeln auf alte Tage anzuwenden ist kein Vorwärtstest**
  (`docs/schattenbetrieb.md:565`). Wer die Historie oft genug befragt,
  findet dort alles.

Der Entscheidungsvertrag bleibt deshalb unberührt: **BETRIEBSPLAN §3.3
und der 10.10.2026**. Die Simulation ist ein Filter *vor* dem Schatten,
kein Ersatz für ihn.

### Fund 5: Der erste Reparaturversuch war selbst wieder falsch

`EngineConfig.for_reversal()` allein ist **nicht** der Live-Bot.
`12_daemon.py` startet zusätzlich mit `deploy_to_target=True` und
`allow_topup=True` (Schalter `--kein-voll-investiert` /
`--kein-nachkauf`, beide `default=True`).

Es sind **exakt die zwei Felder aus §G6** — dieselben, die am 30.07.2026
schon einmal die Flotten-Referenz still zerstört haben. Der erste große
Lauf war damit trotz grüner Tests nicht der Bot. Der Unterschied ist
nicht kosmetisch: ohne `deploy_to_target` bleibt Kapital unbeschäftigt
liegen — Gesamtrendite −0,83 % statt +7,57 %.

Ursache war ein zu grober Test: er prüfte, **dass** `for_reversal()`
benutzt wird, nicht, **ob das Ergebnis dem Bot entspricht**. Ersetzt
durch einen feldweisen Vergleich gegen die aus `12_daemon.py` gelesenen
Voreinstellungen (`live_engine_config()`, gepinnt in
`test_konfiguration_ist_feldweise_die_live_konfiguration`).

### Fund 6: Das Werkzeug lud selbst zum verbotenen Fehlschluss ein

Unter der Score-Tabelle stand: *„Wenn höhere Scores NICHT bessere
Ergebnisse liefern, misst der Score nichts Verwertbares."* Die Tabelle
zählt jeden Trade einzeln. Im großen Lauf sah sie nach einem
dramatischen Befund aus:

| Score-Bereich | n | Ø Rendite |
|---|---:|---:|
| 0,353–0,515 | 169 | **+0,64 %** |
| 0,515–0,677 | 415 | +0,70 % |
| 0,677–0,838 | 739 | −0,04 % |
| 0,838–1,00 | 2.302 | **−0,11 %** |

Der Score schien verkehrt herum zu sortieren — und 63 % aller Trades
liegen im schlechtesten Feld. Gruppiert nach Handelstag: **t = −0,09**.
Nichts davon hält. An einem Abverkaufstag fällt alles gemeinsam; die
Tabelle zählt das als hunderte getrennte Belege. Genau der Fehler, den
§B1 und CLAUDE.md verbieten — eingebaut in die Ausgabe des eigenen
Werkzeugs. Ersetzt durch `gruppierte_pruefung()`, die den t-Wert auf
Basis der Handelstage ausweist und den naiven danebenstellt.

### Das Ergebnis: kein nachweisbarer Vorsprung

Erster ehrlicher Lauf der Live-Strategie über ihr eigenes Universum
(1.201 Symbole, 7 Jahre Daten, Handel ab 09/2020, 3.625 Trades,
**969 Handelstage** als Stichprobe):

| | Strategie | Buy & Hold SPY |
|---|---:|---:|
| Gesamtrendite | **+7,57 %** | +157,20 % |
| p. a. | +1,19 % | ~17 % |
| Max. Drawdown | −27,50 % | |
| Sharpe | 0,15 | |
| Trefferquote | 50,0 % | |
| Profit-Faktor | 1,02 | |
| Kosten | 5.790 $ (19 % des Startkapitals) | |

Gruppierter Test, Schwelle `fleet.schwelle_sigma()` = 2,85:

| Frage | Mittel je Trade | t (Tage) | t (naiv) | Urteil |
|---|---:|---:|---:|---|
| Rendite gegen null | −0,016 % | **−0,11** | 0,30 | kein Befund |
| Score hoch minus tief | −0,020 % | **−0,09** | −0,09 | kein Befund |
| Rendite **vor** Kosten | +0,096 % | 0,62 | 1,39 | kein Befund |

**Wie das zu lesen ist.** Nicht als „die Strategie verliert" — das
95 %-Intervall je Trade reicht von −0,32 % bis +0,29 %, ein kleiner
echter Vorsprung wäre hier nicht nachweisbar (dafür bräuchte es
> 0,44 % je Trade). Sondern: **über 969 unabhängige Handelstage zeigt
sich kein Vorsprung, auch nicht vor Kosten.** Der Punktschätzer liegt
bei null.

Dazu zwei Dinge, die keinen t-Test brauchen:

* Das realisierte Ergebnis von 6 Jahren ist +7,57 % gegen +157,20 %, bei
  −27,5 % Drawdown.
* Diese Zahl ist eine **Obergrenze**. Survivorship: 52 % des Universums
  über 7 Jahre fehlen, Schein-Rendite +2 bis +4 pp pro Jahr. Zieht man
  auch nur 2 pp ab, wird aus +1,19 % p. a. etwa −0,8 % p. a.

### Das gesamte Plus hängt an einem einzigen Teiljahr

Der Lauf endet am 21.08.2026, 2026 ist also nur zu zwei Dritteln
enthalten. Trennt man es ab, kippt das Vorzeichen:

| Zeitraum | Kapital | Rendite | Ø je Trade | Tage | t (gruppiert) |
|---|---:|---:|---:|---:|---:|
| 2021–2025 | 30.000 $ → 23.267 $ | **−22,44 %** | −0,234 % | 822 | **−1,50** |
| 2026 (Teiljahr) | 23.267 $ → 32.270 $ | **+38,70 %** | +1,200 % | 147 | **+2,31** |
| gesamt | | +7,57 % | −0,016 % | 969 | −0,11 |

Beide Teilbefunde liegen unter der Schwelle 2,85 — auch das gute Jahr.
Und 147 Handelstage sind der beste Ausschnitt aus 969: wer sechs Jahre
in Stücke schneidet, findet immer eines, das trägt. Das ist keine
Bestätigung, sondern der Normalfall.

Jahr für Jahr (Strategie gegen SPY):

| | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---:|---:|---:|---:|---:|---:|
| Strategie | −6,9 % | −17,8 % | +17,1 % | −8,5 % | −7,7 % | +30,3 % |
| SPY | +30,5 % | −18,7 % | +26,7 % | +25,6 % | +18,0 % | +12,7 % |
| Differenz | −37,4 | **+0,9** | −9,6 | −34,1 | −25,7 | **+17,7** |

Nur 2022 (Bärenmarkt, dort arbeitet der Regimefilter) und 2026 liegen
vorne. Dazu die Konzentration: die **10 besten von 3.625 Trades** tragen
5.276 $ bei — die Netto-Summe des ganzen Laufs beträgt 2.306 $. Ohne
diese zehn ist der Lauf mit rund −3.000 $ im Minus.

**Geprüfte und widerlegte Erklärung.** Naheliegender Verdacht war ein
Auswahlartefakt: `load_universe` sortiert nach dem **heutigen**
Dollarumsatz, und stark gehandelt wird, was zuletzt gelaufen ist — das
würde 2026 künstlich begünstigen. Nachgemessen über alle 1.201 Symbole:

| Jahr | Universum (Median) | Universum (Mittel) | SPY |
|---|---:|---:|---:|
| 2021 | +25,6 % | +30,7 % | +30,5 % |
| 2023 | +19,0 % | +34,4 % | +26,7 % |
| 2024 | +15,0 % | +29,4 % | +25,6 % |
| 2025 | +12,0 % | +27,7 % | +18,0 % |
| 2026 | **+11,5 %** | +19,5 % | **+12,6 %** |

2026 ist im Universum das **schwächste** Jahr und liegt unter SPY. Der
Verdacht trägt nicht. Nebenbefund: das *Mittel* schlägt SPY in jedem
einzelnen Jahr, der *Median* nie — das ist die Signatur der
Survivorship, gleichmäßig über alle Jahre verteilt, nicht 2026-lastig.

Was 2026 erklärt, ist damit offen. Die ehrliche Antwort bei t = +2,31
auf 147 Tagen: es kann Zufall sein, und nichts spricht dagegen.

### Der Lauf selbst ist sauber

Damit das Null-Ergebnis nicht als kaputte Pipeline missverstanden wird:
`pit.audit_feature_function` lief vor der Simulation und meldete
**[SAUBER] 5 Abschneidepunkte geprüft, keine Zukunftsabhängigkeit**.
Blockiert wurden 67 Entscheidungen wegen `kursluecke_seit_entscheidung`
und 66 wegen `betrag_zu_klein` — beides erwartetes Verhalten. Das
Ergebnis ist das der Strategie, nicht das eines Defekts.

Woran die Trades endeten (Summen über den ganzen Lauf):

| Grund | n | Ø | Summe |
|---|---:|---:|---:|
| `zeitausstieg` | 2.149 | −0,59 % | **−15.268 $** |
| `stop_intraday` | 456 | −7,27 % | **−45.456 $** |
| `these_traegt_nicht_mehr` | 776 | +3,16 % | +31.655 $ |
| `gewinnziel_erreicht` | 244 | +9,23 % | +31.375 $ |

Der Zeitausstieg nach 5 Tagen ist die größte Einzelblutung nach dem
Stop. Anders als alles andere in diesem Lauf hält die Zahl auch dem
gruppierten Test stand — **in der ersten Periode**:

| Zeitraum | n | Ø je Handelstag | Tage | t | Urteil |
|---|---:|---:|---:|---:|---|
| 2021–2025 | 1.836 | −0,73 % | 711 | **−5,29** | **BEFUND** |
| 2026 | 313 | −0,07 % | 125 | −0,15 | kein Befund |

(Ø je Handelstag, nicht je Trade — je Trade sind es −0,65 % bzw.
−0,25 %. Maßgeblich ist die Tagesgruppe, §B1.)

Der Anteil ist in beiden Perioden identisch (59,3 % aller Trades), die
Rendite nicht. Das ist der einzige Wert des ganzen Laufs, der die
Schwelle 2,85 überschreitet.

**Er rechtfertigt trotzdem keine Parameteränderung.** Nach dem
Ausstiegsgrund zu filtern heißt, auf das Ergebnis zu bedingen: Trades
mit großem Gewinn sind vorher über `gewinnziel_erreicht` weg, die mit
großem Verlust über `stop_intraday`. Übrig bleibt konstruktionsbedingt
die Mitte. Vorab weiß niemand, welcher Trade dort landet.

### Hätte längeres Halten geholfen? Nein (21.08.2026)

Genau die Frage, für die der Historienlauf gebaut wurde. Für alle 2.149
Zeitausstiege gemessen, was der Kurs **nach** dem Verkauf tat —
marktbereinigt gegen SPY, gruppiert nach Ausstiegstag:

| + Handelstage | n | roh | marktbereinigt | t | Urteil |
|---|---:|---:|---:|---:|---|
| 1 | 2.149 | −0,05 % | −0,09 % | −1,01 | kein Befund |
| 2 | 2.149 | −0,09 % | −0,16 % | −2,14 | kein Befund |
| 3 | 2.146 | −0,00 % | −0,13 % | −1,79 | kein Befund |
| 5 | 2.140 | +0,15 % | −0,09 % | −1,76 | kein Befund |
| 10 | 2.129 | **+0,43 %** | **−0,05 %** | −1,01 | kein Befund |

Die rohe Spalte ist die Falle: +0,43 % nach 10 Tagen sieht aus wie „zu
früh verkauft". Es ist der Markt, der in diesen 10 Tagen ohnehin stieg.
Marktbereinigt bleibt an **jedem** Horizont ein Minus, der Punktschätzer
zeigt durchgehend in die falsche Richtung.

**Was das heißt und was nicht.** Es widerlegt die einfache Fassung
(„einfach länger halten") — die braucht keinen Flottenplatz mehr.
`B11_dyn_ausstieg_live` testet die schärfere Fassung: *signalgesteuert*
aussteigen statt nach fester Frist. Das ist nicht dasselbe und wird von
dieser Messung nicht entschieden. §3.3 misst vorwärts, Termin bleibt der
**10.10.2026**, Zwischenblick ohne Schlüsse am **12.09.2026**.

### Was daraus folgt — und was nicht

Kein Parameter der Handelslogik wird auf Basis dieses Laufs geändert
(CLAUDE.md: erst im Schatten messen). Der Lauf ist ein Filter, keine
Abnahme. Was er liefert, ist eine belastbare Erwartungshaltung: eine
Idee, die diesen Lauf nicht übersteht, braucht keinen Flottenplatz.

### Behoben

`live_engine_config()` (feldweise der Bot), `market=spy` durchgereicht,
Universum `live` mit 1.200 Symbolen wie der Bot, Cache an,
`gruppierte_pruefung()` in der Ausgabe, und jeder Lauf legt neben
`trades.csv` eine **`lauf.json`** mit seiner vollständigen Konfiguration
ab. Ohne diese Datei ist eine `trades.csv` wertlos: die alte verriet mit
keinem Feld, dass sie aus einer anderen Strategie stammte — erst dadurch
konnte die Abweichung so lange unbemerkt bleiben.

Regression: `tests/test_konsistenz.py::TestSimulationFaehrtDieLiveStrategie`
(9 Tests) und `tests/test_daten.py::TestBarCacheSchluessel` (6 Tests).
Gegen 15 Mutationen geprüft, alle getötet — darunter zwei, die schwächere
erste Fassungen der Tests überlebt hatten (die Zeichenkette `lauf.json`
statt des Schreibvorgangs gesucht; `for_reversal()` strukturell statt
feldweise geprüft).

---

## G12. Die zweite Überlappung: zwischen den Handelstagen (22.08.2026)

**Schwere: hoch.** Betrifft jede Faktormessung des Projekts — auch die,
auf denen die Strategie selbst steht.

### Was übersehen wurde

§B1 hat die Überlappung **innerhalb** eines Handelstages gelöst: Alle
Kandidaten eines Tages sehen denselben Markt, also wird je Tag gemittelt.
Richtig — aber es bleibt eine zweite Ebene:

```
Tag 1 sagt die Rendite der Tage 1–5 voraus
Tag 2 sagt die Rendite der Tage 2–6 voraus   <- 4 von 5 Tagen geteilt
```

Bei einem Horizont von 5 Tagen teilen zwei **benachbarte Tagesmittel**
vier Fünftel ihres Renditefensters. Sie sind damit ebenso wenig
unabhängig wie zwei Vorhersagen desselben Tages — nur eine Ebene höher.
Das Mitteln je Tag beseitigt diese zweite Ebene nicht; es tut dagegen
buchstäblich nichts.

### Wie groß der Fehler ist

**Der entscheidende Beleg** — 200 Läufe über reines Rauschen, gleitende
5-Tage-Fenster, **kein echter Effekt vorhanden**. Ein Test bei |t| > 2
darf in ~5 % der Fälle anschlagen:

| Rechnung | Fehlalarmquote | Soll |
|---|---:|---:|
| ohne Korrektur | **39,5 %** | 5 % |
| mit Korrektur | 11,0 % | 5 % |

**Knapp vier von zehn „Befunden" aus überlappenden Fenstern sind reines
Rauschen.** Die verbleibenden 11 % sind ehrlich zu nennen: Newey-West
unterkorrigiert in endlichen Stichproben. Die Korrektur macht den Test
nicht exakt, sie macht ihn brauchbar.

### Auf echten Daten

Projekteigener Faktor-Scan (`research.candidate_factors`), 1.182 Symbole,
7 Jahre, 1.561 Handelstage, Horizont 5:

| Faktor | IC | t roh | t korrigiert | Aufblähung | Urteil |
|---|---:|---:|---:|---:|---|
| `ausverkauf` | +0,0088 | 4,41 | **3,15** | 1,40× | bleibt Befund |
| `rsi2` | +0,0145 | 3,94 | **2,70** | 1,46× | **kippt** |
| `reversal_3d` | +0,0165 | 3,91 | **2,79** | 1,40× | **kippt** |
| `reversal_2d` | +0,0151 | 3,59 | **2,91** | 1,23× | bleibt Befund |
| `amihud` | +0,0137 | 3,56 | **1,95** | 1,82× | **kippt** |
| `mom_252_21` | +0,0193 | 3,52 | **2,02** | 1,74× | **kippt** |
| `reversal_5d` | +0,0144 | 3,42 | **2,16** | 1,58× | **kippt** |
| `dist_sma10` | −0,0141 | −3,36 | **−2,04** | 1,64× | **kippt** |

**Über alle 30 Faktoren: naiv 10 „Befunde", korrigiert 4.** Sechs von
zehn verschwinden. Mittlere Aufblähung 1,62×. (Schwelle 2,85 =
`fleet.schwelle_sigma()`.)

### Die Aufblähung ist nicht konstant — und das ist der Kern

Sie ist das **Produkt aus zwei Dingen**: der Überlappung der
Renditefenster **und der Trägheit des Faktors selbst**.

| Faktor | Aufblähung | warum |
|---|---:|---|
| `reversal_1d` | **0,96×** | erneuert sich täglich vollständig |
| `schluss_lage` | 1,02× | dito |
| `reversal_2d` | 1,23× | kurzes Gedächtnis |
| `amihud` | **1,82×** | träge, 20-Tage-Fenster |
| `mom_252_21` | 1,74× | träge, Jahresfenster |

`reversal_1d` ist zugleich der **Kontrollfall**, der den Befund
absichert: Bei Horizont 1 (keine Überlappung) liegt die Aufblähung bei
0,99× und die Autokorrelation bei −0,016. Der Effekt entsteht also
nachweislich durch die Überlappung und nicht durch irgendeine andere
Eigenschaft der Daten.

**Folge:** Eine pauschale Faustzahl (`t / 1,6`) wäre falsch. Die
Korrektur muss aus den Daten kommen.

### Warum das teuer ist

Die Kette, über die die Strategie entstanden ist:

```
scripts/11_factor_lab.py
  -> research.measure_factors()   t_stat = ic / (std / sqrt(n_tage))   [unkorrigiert]
  -> research.select_factors(min_t=3.0)
  -> signals.ReversalWeights
```

**Die tragenden Faktoren der Strategie wurden mit dem aufgeblähten
t-Wert ausgewählt.** Zwei der in `ReversalWeights` dokumentierten
Bausteine (`rsi2`, `reversal_3d`) halten die heutige Schwelle nach
Korrektur nicht mehr.

### Was das NICHT heißt

- **Die Strategie ist damit nicht widerlegt.** `ReversalWeights` nennt
  als Kriterium ausdrücklich die **Vorzeichenstabilität je Jahr**
  („100 % positive Jahre") — ein anderes und robusteres Kriterium als
  der t-Wert, das von dieser Korrektur unberührt bleibt.
- **Kein Parameter wird deshalb geändert** (CLAUDE.md). Der Befund
  senkt die *Beweislast-Erfüllung* der Vergangenheit, er ist kein
  Handelssignal.
- Die Zahlen in §A stammen aus einem anderen Lauf (2.162 Symbole,
  9 Jahre) und sind hier nicht direkt nachgerechnet. Die Richtung des
  Fehlers gilt trotzdem: sie sind zu optimistisch.

### Das Wissen war bereits im Projekt vorhanden

Der unangenehmste Teil. `scripts/24_kandidaten_test.py:91` gruppiert
ausdrücklich nach **Monat**, mit genau dieser Begründung im Kommentar:

> „Jeder Tag ist EINE Beobachtung – deshalb hier der Monat als Gruppe,
> sonst wären aufeinanderfolgende Tage wieder überlappend."

Dort war es also gelöst. Nur `research.py` — das Werkzeug, das die
tragenden Faktoren ausgewählt hat — tat es nicht. **Es war kein
Wissenslücke, sondern eine Inkonsistenz.** Damit gilt umgekehrt: die
18 Faktorkandidaten vom 16.08. (§C) wurden korrekt gemessen und bleiben
widerlegt.

### Behoben

- `statistik.newey_west_t()` — Bartlett-Kern, gegen den analytisch
  herleitbaren Sollwert geprüft (für ein gleitendes q-Tage-Mittel ist
  `LRV/gamma_0 = 1 + 2·Σ((q−k)/q)²`, bei q=5 also 3,40 → 1,844×).
- `statistik.gruppierter_test(..., horizont=)` — Vorgabe 1 (unverändert
  rückwärtskompatibel). `belastbar` hängt am **korrigierten** Wert.
- `research.FactorResult.t_korrigiert` / `.aufblaehung`; `verdict`,
  `select_factors` und die Sortierung der Rangliste nutzen den
  korrigierten Wert. Alte Ergebnistabellen ohne die Spalten zeigen einen
  Strich, nie den rohen Wert an der Stelle des korrigierten.
- `nachbetrachtung.zeitausstieg_pruefen` reicht seinen `horizont` durch.
- `scripts/10_simulate.py` korrigiert über die **gemessene** mediane
  Haltedauer, nicht über `max_hold_days` (Stops beenden viele Trades
  früher).

Regression: `tests/test_statistik_ueberlappung.py` (19 Tests). Fünf neue
Mutationen in `scripts/23_mutationstest.py`, **24 von 24 gefangen** —
zwei davon erst nach Nachbesserung: der Bartlett-Kern war nur gegen
„größer als 1" geprüft, und die Sortierzusicherung war ein wirkungsloses
Duplikat von `groupby(sort=True)`.

---

## G13. Datenklarheit: stumme Felder und vermischte Quellen (22.08.2026)

**Anlass:** die Frage „sind alle Auswertungen legitim?". Drei Funde, alle
aus derselben Familie — Zahlen, die plausibel aussehen und falsch sind.

### Fund 1: 98,4 % des Live-Journals sind gar nicht live

`decisions` im Live-Journal, nach Quelle aufgeschlüsselt:

| `runs.script` | `strategy` | Zeilen | Zeitraum |
|---|---|---:|---|
| `live_trade` | `engine` | **304** | 28.07.–21.08.2026 |
| `simulate` | `mehrfaktor` | **18.118** | **2021-07-08**–20.08.2026 |
| `stop_intraday` | `stop_intraday` | 3 | ab 15.08. |

Simulationsläufe schreiben in dasselbe Journal wie der Bot — mit
**rückdatierten Zeitstempeln bis 2021**. Vier Läufe erzeugten 18.118
Zeilen, die von echten Entscheidungen nur am Feld `strategy` zu
unterscheiden sind.

**Die Trennung existierte** (`decision_quality(script=)`), und ihr
Docstring benannte sogar genau diese Gefahr. **Von vier Aufrufern nutzte
sie genau einer:**

| Aufrufer | Filter | Folge |
|---|---|---|
| `scripts/13_tagesbericht.py` | `script="live_trade"` | richtig |
| `scripts/07_journal_report.py` | — | beschrieb den Backtest |
| `src/alpaca_bot/selfcheck.py` | — | beschrieb den Backtest |

Zwei Berichte nannten also die Entscheidungsqualität einer Simulation die
des Bots. Nebenwirkung: Die Integritätsprüfung mahnte dauerhaft „17.100
Entscheidungen ohne bewertetes Ergebnis" — fast alles Simulationszeilen,
die nie eines brauchen. Eine Warnung, die immer leuchtet, wird
weggeklickt.

**Behoben:** `decision_quality(script=)` hat jetzt die Vorgabe
`"live_trade"`. Die gefährliche Richtung (`script=None`) verlangt eine
bewusste Angabe. `integrity_check` zählt nur noch Live-Zeilen — aus
17.100 wurden **62**.

### Fund 2: `bars_held` ist in 64 % der Trades falsch

| | Trades | `bars_held` | echte Handelstage |
|---|---:|---|---|
| Ausstieg **vor** 17.08. | **36** | immer **0** | Median 5 (2–5) |
| Ausstieg **ab** 17.08. | 20 | 2–5 | **Abweichung 0** |

Der am 15.08. behobene Fehler (§G) wirkt korrekt für neue Trades — aber
die 36 alten Zeilen behielten ihre falsche Null. Der Median der
Haltedauer lag dadurch bei **0 statt 5**.

**Eine falsche Zahl ist hier schlimmer als eine fehlende.** Eine Null
sieht wie eine Messung aus und geht in jeden Mittelwert ein. Ein `NULL`
wäre aufgefallen.

Die Rekonstruktion ist belastbar, weil sie an echten Daten geprüft ist:
Für die 20 korrekten Trades reproduziert `np.busday_count(einstieg,
ausstieg)` den gemessenen Wert mit **Abweichung 0**.

**Werkzeug:** `scripts/25_bars_held_reparieren.py` — Trockenlauf als
Vorgabe, legt eine Sicherung an und markiert jede berichtigte Zeile in
`bars_held_quelle` als `rekonstruiert`. Ohne diesen Vermerk wäre später
nicht mehr unterscheidbar, was Messung und was Nachtrag ist (§G11).

### Fund 3: Der Auswertungskontext hängt nur an `buy`

`regime_markt`, `regime_vola`, `sektor` und `liq_dezil` werden seit dem
20.08. erfasst — aber nur für Kaufentscheidungen:

| Aktion | Anteil der letzten 60 | Kontext |
|---|---:|---|
| `topup` | 41 | **nein** |
| `buy` | 11 | ja |
| `sell` | 8 | **nein** |

**`topup` ist die Mehrheit der Kapitalzuteilung** (110 von 304 Live-
Entscheidungen, bis zu 9 Nachkäufe je Symbol laut §G2). Eine Auswertung
der Sektorkonzentration übersieht damit den größeren Teil. **Noch nicht
behoben** — reine Protokollerweiterung, aber sie erfordert einen
Dienstneustart.

### Der Wächter, der daraus eine Routine macht

Alle drei Funde gehören zu **einem** Muster: ein Feld ist leer, konstant
oder falsch, nichts stürzt ab, und es fällt nur auf, wenn jemand zufällig
gezielt nachsieht. So verliefen `bars_held`, `after_10d`, `code_version`
(66 % der Daten), der Bar-Cache — und jetzt diese drei.

`data_integrity` prüft deshalb ab sofort automatisch:

| Prüfung | fängt |
|---|---|
| `check_stumme_felder` | ein Feld **hört auf**, sich zu füllen |
| `check_bars_held_stimmig` | Werte widersprechen den Datumsangaben |
| `check_lifecycle_felder` | `after_*` bleiben leer, obwohl fällig |
| `check_codeversion_zuordnung` | Läufe ohne Versionszuordnung |

**Zwei Fehlversuche beim Bau — beide lehrreich:**

1. Der erste Entwurf prüfte die **Füllquote über die Historie** und
   schlug sofort bei vier Feldern an, die zwei Tage zuvor eingeführt
   worden waren. Er hätte ~30 Tage gelb geleuchtet, ohne dass etwas
   kaputt war. Geprüft wird jetzt die gefährliche Richtung: hört ein
   Feld **auf**? Ein kleines Fenster (20 Zeilen) stellt die richtige
   Frage; eine Einführung ist binnen eines Tages wieder sauber.
2. Der zweite Entwurf warf **alle Aktionsarten in einen Topf** und
   meldete einen Ausfall bei `buy`, den die vielen `topup`-Zeilen nur
   vortäuschten. Ein Topf aus ungleichen Dingen erzeugt Fehlalarme *und*
   verdeckt echte Ausfälle.

Beide Fehlversuche stehen als Testfall in der Suite — sie sind die
eigentliche Schwierigkeit an dieser Art Wächter.

Regression: `tests/test_datenklarheit.py` (11 Tests). Vier neue
Mutationen, **28 von 28 gefangen**.

---

## G14. Der Schattenbot lief 24/7 — aber er lernte nicht (22.08.2026)

**Anlass:** die Forderung, das System müsse außerhalb der Handelszeiten
weiterarbeiten und kontinuierlich dazulernen. Der Befund war das
Gegenteil von erwartet.

### Er lief bereits rund um die Uhr — nur ohne Erkenntnisgewinn

Der Dauerbetrieb kennt keine Börsenzeiten und rechnet stündlich. Jeder
Durchgang meldete:

```
Durchgang fertig: {'eingebucht': 0, 'verifiziert': 19788, 'entschieden': 0}
```

**Immer dieselben 19.788.** `offene_ergebnisse()` hält eine Vorhersage
offen, bis `fwd_20d` gefüllt ist — also 20 Handelstage lang. Ein
Ergebnis kann sich aber nur ändern, wenn eine **neue Tagesbar**
dazukommt; innerhalb eines Handelstages ist jede Wiederholung bitgleich.

| | vorher | nachher |
|---|---:|---:|
| Dauer je Durchgang | 17 s | **0,2 s** |
| Rechenzeit ohne neue Daten | ~7 Min/Tag | ~0 |

Ehrliche Einordnung: 7 Minuten täglich sind **keine** dramatische
Verschwendung. Der eigentliche Befund ist nicht die verlorene
Rechenzeit, sondern dass die übrigen 23 h 53 min gar nichts taten.

Der Filter vergleicht bewusst gegen den **jüngsten geladenen Bar**, nicht
gegen die Uhrzeit: Am Wochenende und an Feiertagen kommt keine Bar dazu,
eine kalendarische Regel würde dort weiterrechnen.

### Der eigentliche Fund: die Lernschleife war gebaut und lief nie

`patterns.py` ist vollständig und mit der richtigen Disziplin gebaut —
Musterverfall, Nachprüfung ausschließlich auf **neu hinzugekommenen**
Daten, Mindestzahl an Handelstagen, Meldung an alle betroffenen Bots.
Sein eigener Docstring beschreibt genau das gewünschte Verhalten.

**Die Tabelle `muster` enthielt null Zeilen.** Der Daemon kannte nur
`einbuchen`/`verifizieren`/`entscheiden` und rief den Musterspeicher an
keiner Stelle auf.

Das ist der Unterschied zwischen „das System könnte lernen" und „das
System lernt".

### Warum das Anschalten allein gefährlich gewesen wäre

`patterns._messen` und `shadow_eval.ic` rechneten den t-Wert **ohne die
Korrektur aus §G12** — auf `fwd_5d`, also genau dem überlappenden
Horizont. Eine 24/7-Lernschleife darauf hätte rund um die Uhr
Scheinmuster erzeugt, bei einer Fehlalarmquote von 39,5 %.

Was der Kandidatenlauf tatsächlich ausspuckte:

| Bedingung | Handelstage | IC |
|---|---:|---:|
| `regime_vola == 'niedrig'` | **2** | **+0,248** |
| `regime_vola == 'hoch'` | 4 | +0,097 |
| `regime_markt == 'aufwaerts'` | 13 | +0,070 |

Ein IC von 0,248 aus **zwei Handelstagen** — das Vierzehnfache des besten
je gemessenen Faktors (§A). Mit unkorrigiertem t wäre so etwas als
bestätigtes Muster in den Speicher gewandert.

### Ein Fehler in der Korrektur selbst

Beim Verdrahten fiel auf, dass `newey_west_t` **entartet**, wenn die
Reihe zu kurz für den Lag ist. An echten Schattendaten:

| Horizont | Handelstage | t roh | t „korrigiert" |
|---|---:|---:|---:|
| `fwd_10d` | 8 | 5,30 | **14,57** |

Kein zu hoher Wert, sondern Unsinn — und er sieht wie ein spektakulärer
Befund aus. Bei acht Beobachtungen und einem Zehn-Tage-Fenster steckt
darin weniger als ein unabhängiger Block.

**Behoben:** `newey_west_t` verlangt `n >= 3·(lag+1)` und liefert sonst
`nan`. Wichtig ist, was dann **nicht** passiert: Der rohe Wert springt
nicht ein. Er wäre die optimistischste aller Antworten. Der
Schattenbericht schreibt stattdessen aus, dass es keinen t-Wert gibt,
und nennt den rohen ausdrücklich als „NICHT zitieren".

**Folge für die laufende Auswertung:** Mit 13 Handelstagen ist der
5-Tage-IC des Schattenbuchs derzeit **ohne gültigen t-Wert**. Nötig sind
mindestens 15. Die bisher berichteten Werte (`t=1,22`) waren nie
belastbar — was zur ohnehin geltenden Hausmarke von 60 Tagen passt.

### Was jetzt läuft

Der Dauerbetrieb hat einen vierten Schritt:

```
einbuchen -> verifizieren -> entscheiden -> lernen
```

`lernen` steht **am Ende**, nicht am Anfang: Es wertet aus, was die drei
Schritte davor erzeugt haben. Zuerst gerufen sähe es immer den Stand von
gestern — eine ganze Runde Verzögerung, die niemandem auffiele.

Alle vier Schritte sind **idempotent**: ohne neuen Handelstag tun sie
nichts und kosten Sekundenbruchteile. Erst das macht häufiges Laufen
sinnvoll.

**Was `lernen` ausdrücklich nicht tut:** Es ändert keine Handelsregel.
Ein bestätigtes Muster ist eine Beobachtung mit Beleg und Verfallsdatum,
kein Signal. Der Weg in die Handelslogik führt weiterhin über eine
Voranmeldung in der Flotte.

### Zur Frage nach Reinforcement Learning

`src/alpaca_bot/rl/` existiert und benennt im eigenen Modul-Docstring die
vier Gründe, warum RL hier begrenzt ist: Datenhunger (DQN braucht
Millionen Übergänge, 10 Jahre Tagesdaten sind 2.500 Schritte je Aktie),
Nicht-Stationarität, Auswendiglernen des Kurspfads, Zuordnungsproblem
bei 95 % Rauschen. Es ist deshalb auf die **Positionsgröße** angesetzt,
nicht auf die Richtung, und jede Auswertung läuft gegen eine
Zufallspolitik.

Das ist die richtige Konstruktion. Der Engpass ist auch hier nicht das
Verfahren, sondern die Zahl unabhängiger Handelstage: derzeit **19**.

---

## G15. Ein ML-Modell schlaegt den Score nicht (22.08.2026)

**Anlass:** die Forderung nach einem selbstlernenden System, das aus
allen Daten lernt und dadurch besser wird. Die Frage dahinter ist
praezise und war bisher unbeantwortet:

> Sortiert ein gelerntes Modell die Kandidaten besser als der
> handgebaute Score?

**Antwort: nein.** Gemessen ueber 1.186 Symbole, 7 Jahre und **1.101
unabhaengige Handelstage** - die groesste Stichprobe, die das Projekt
fuer diese Frage je hatte.

| | IC | t (korr.) | t roh | Dezil-Spreizung | t |
|---|---:|---:|---:|---:|---:|
| GBM auf 32 Merkmalen | +0,0041 | 0,71 | 1,10 | **-0,405 %** | **-2,44** |
| Score (Bot heute) | +0,0089 | 1,40 | 2,21 | -0,140 % | -1,11 |

Beide unter der Schwelle (2,85). **Das Modell ist schlechter als der
Score**, den es ersetzen sollte.

### Der Nebenbefund ist der wichtigere: die Spreizung ist negativ

Der IC ist bei beiden positiv, die Dezil-Spreizung bei beiden **negativ**.
Das ist kein Widerspruch, sondern eine Aussage ueber die Struktur: Ueber
die Mitte des Feldes sortiert der Score schwach richtig, aber das
**oberste Dezil laeuft schlechter als das unterste** - und genau das
oberste Dezil kauft der Bot (Top 15 von 1.200).

Damit ist die Beobachtung aus §G11 Fund 6 bestaetigt, diesmal sauber
gerechnet: Dort zeigte die Score-Tabelle -0,11 % im hoechsten
Score-Band, wurde aber als "gruppiert t = -0,09, nichts haelt"
eingeordnet. Je Handelstag als Dezilspreizung gemessen und
ueberlappungskorrigiert liegt der Wert beim Modell bei **t = -2,44** -
naeher an der Schwelle als jeder positive Wert des Laufs, nur mit
falschem Vorzeichen.

**Ein IC allein haette hier in die Irre gefuehrt.** Deshalb weist
`dataset.guete` beide Zahlen nebeneinander aus.

### Weniger Symbole sahen besser aus - das Muster aus §B4

| Universum | Modell-IC | Score-IC | Urteil |
|---|---:|---:|---|
| 300 Symbole | **+0,0146** | +0,0087 | Modell fuehrt |
| 1.186 Symbole | +0,0041 | +0,0089 | Modell faellt zurueck |

Auf 300 Symbolen schlug das Modell den Score deutlich. Auf dem vollen
Universum kippt es. Exakt der PEAD-Verlauf aus §B4 (IC 0,032 auf 60
Symbolen, Zusammenbruch auf 800) - **Probelaeufe auf kleinen Universen
dienen dem Testen der Mechanik, nie der Bewertung.**

### Was das fuer die Vision "selbstlernendes System" heisst

Es widerlegt nicht das Lernen, sondern eine bestimmte Hoffnung: dass
*mehr Modell* auf *denselben Daten* einen Vorsprung hebt. Das deckt sich
mit §C: Der Faktorraum aus Kurs- und Volumendaten ist ausgeschoepft, neue
Information muesste von **ausserhalb** kommen. Ein GBM auf 32
OHLCV-Ableitungen ist eine weitere Ableitung desselben Raums.

Der Engpass bleibt der aus §G14 und `docs/LERNTEMPO.md`: unabhaengige
Handelstage. Gerechnet mit `statistik.noetige_gruppen` braucht ein Effekt
der Groesse, die dieses Projekt real misst (IC ~0,02), rund **926
Handelstage**. Der Schatten hatte am 22.08. **19**.

### Die Kette ist kalibriert - beide Richtungen geprueft

Damit das Null-Ergebnis nicht als stumpfes Werkzeug missverstanden wird,
wurde die Auswertung gegen drei synthetische Panels gefahren:

| eingebauter Effekt | IC | t | Urteil |
|---|---:|---:|---|
| keiner (Kontrolle) | -0,0105 | -0,98 | kein Befund |
| schwach (AR -0,15) | +0,0201 | 1,86 | kein Befund |
| stark (AR -0,35) | +0,1025 | **11,81** | **BEFUND** |

Sie schweigt bei Rauschen und spricht bei echtem Signal. Nebenbefund:
Die gemessene Aufblaehung des rohen t-Werts lag bei **1,59x** - eine
unabhaengige Bestaetigung der 1,62x aus §G12.

Bemerkenswert die mittlere Zeile: Ein Effekt **staerker als jeder je
real gemessene Faktor** (IC 0,0201 gegen 0,018 in §A) reicht bei 396
Handelstagen nicht ueber die Schwelle. Das ist der Preis der Ehrlichkeit,
in einer Zahl.

### Vier Fehler beim Bau - alle aus der Familie "es stuerzt nichts ab"

| # | Fehler | Wirkung |
|---|---|---|
| 1 | `market` mit Mitternachts-Stempeln gegen Bars mit 04:00 UTC | `reindex` trifft nie, 3 Merkmale komplett NaN, `dropna` verwirft das **gesamte** Panel. Ausgabe: "0 Zeilen" |
| 2 | leeres Merkmal wurde stumm verschluckt | man sieht nur "0 Zeilen" und sucht an der falschen Stelle |
| 3 | `fokus` verglich jeden Bot gegen eine **global** gewaehlte Referenz | B04 vs B09 sind **drei** geaenderte Achsen, nicht eine - exakt §G6 |
| 4 | `fokus` rechnete aus **13** Handelstagen ein "nie entscheidbar" hoch | glatte Zahl mit Datum, ohne Deckung (§G13) |

Fehler 3 ist der unangenehmste: Das Werkzeug, das die Disziplin des
Projekts durchsetzen soll, haette den teuersten Fehler des Projekts
reproduziert. `Bot.basis_bot` existierte die ganze Zeit und wurde
ignoriert.

Fehler 4 ist die Lehre aus §G13 in neuer Verkleidung: Eine Hochrechnung
erbt die Unsicherheit ihrer Eingangsgroesse, liefert aber eine glatte
Zahl. `fokus.MIN_TAGE_HOCHRECHNUNG = 20` verhindert das jetzt -
darunter steht `offen`, nie `nie`.

### Was gebaut wurde

| Modul | Zweck |
|---|---|
| `dataset.py` | Panel (alle Symbole x alle Tage) statt Trade-Datensatz; Label = Ueberschuss gegen den Tagesmedian; Walk-Forward auf der **Tagesachse** mit Embargo |
| `lernkern.py` | Modellregistry: jede Version mit Trainingszeitraum, Merkmalen, Codeversion und **eingefrorener** Schwelle; Abnahme nur bei nachgewiesener Verbesserung |
| `fokus.py` | Rangliste offener Fragen nach `noetige_gruppen` - was ist als naechstes ueberhaupt entscheidbar? |

**Warum `ml.walk_forward_predict` nicht benutzt wird:** Es schneidet nach
Zeilenposition (`.iloc`). Auf einem Panel legt das Zeilen **desselben
Handelstages** in Trainings- und Testfenster - ein Leck genau der Art,
gegen die `pit.py` existiert, nur eine Ebene hoeher. Fuer die Zeitreihe
eines einzelnen Symbols bleibt die Funktion richtig.

Regression: `tests/test_lernkern.py` (23 Tests), darunter je einer fuer
die vier Fehler oben, der Nachweis, dass kein Handelstag in beiden
Fenstern liegt, und beide Kalibrierungsrichtungen.

### Fortschreibung 04.09.2026 — Wiederholung mit frischem Fenster

`26_lernkern.py --symbole 1200 --jahre 7` erneut gelaufen (der Baustein
lag seit 22.08. still, Health-Check GELB — jetzt GRÜN). Panel: 1.351
Handelstage, 1.186 Symbole, 32 Merkmale, Zeitraum bis 27.08.2026.
Neue Modellversion `03f6c2b0`:

| | IC | t (korr.) | Dezil-Spreizung | t |
|---|---:|---:|---:|---:|
| Modell (gbm) | 0,0060 | 1,01 | **−0,349 %** | −2,13 |
| Score (Bot heute) | 0,0091 | 1,45 | −0,127 % | −1,01 |

**Unverändert: das Modell schlägt den Score nicht** (Spreizung −0,35 %
gegen −0,13 %), beide unter der Schwelle 2,88. Drittes Mal bestätigt
(§G15, §G50). `03f6c2b0` **abgelehnt**, kein Zählerplatz-Bezug — der
Lauf ist ein Filter, keine Abnahme.

---

## G15. Der Nutzungsnachweis — gegen die häufigste Fehlerklasse dieses Projekts

**Anlass:** die Feststellung, dass dreimal innerhalb weniger Tage ein
fertig gebauter Baustein niemals lief.

### Die Serie

| Datum | Baustein | Zustand | gefunden nach |
|---|---|---|---|
| 21.08. | Bar-Cache | `use_cache=True` rief niemand auf | ~3 Wochen |
| 22.08. | Musterspeicher | Tabelle `muster`: 0 Zeilen | seit Bau |
| 22.08. | Kontext bei `topup` | hing nur an `buy` | 2 Tage |
| 22.08. | `liquiditaet` | 0 von 12.250 gefüllt | seit Bau |

Dazu die ältere Chronik: `bars_held` immer 0, `after_10d` nie gefüllt,
`code_version` zwei Monate `'unbekannt'` (66 % der Daten), 98,4 %
Simulationszeilen im Live-Journal.

**Das Muster ist immer dasselbe:** Ein Baustein ist gebaut, sieht im Code
richtig aus und tut nichts. Kein Absturz, keine Meldung. Gefunden wurde
jeder Fall nur, weil zufällig jemand gezielt nachsah.

### Die vier Arten des stillen Ausfalls

Jede braucht einen eigenen Test, weil keine die andere findet:

| Art | Beispiel |
|---|---|
| **nie gelaufen** | Musterspeicher, Bar-Cache — nirgends verdrahtet |
| **immer leer** | Cache lief, traf aber nie |
| **immer gleich** | 19.788 Verifizierungen je Stunde, Runde um Runde identisch |
| **zu selten** | ein Schritt, der stumm scheitert |

Die dritte ist die tückischste: Ein solcher Baustein meldet sich
regelmäßig **mit Ergebnissen** und sieht in jeder Statistik gesund aus.
Nur entsteht keine neue Information.

`nutzung.py` prüft alle vier automatisch. Jeder Baustein meldet nach dem
Lauf, was herauskam — mit einer **Signatur**, die das Ergebnis
kennzeichnet, nicht den Lauf. Bleibt sie konstant, wurde gerechnet und
nichts gefunden.

### Was der Nachweis ausdrücklich nicht leistet

Er prüft **Nutzung**, nicht Richtigkeit. Ein Baustein kann täglich laufen,
wechselnde Ergebnisse liefern und trotzdem falsch rechnen — dagegen helfen
`tests/`, `data_integrity.py` und der Mutationstest. Hier geht es um die
davorliegende, banalere Frage: Passiert überhaupt etwas?

### Ein weiterer stiller Ausfall, gefunden beim Bau

`liquiditaet` ist in **0 von 12.250** Schattenvorhersagen gefüllt.
Ursache: `engine.py` liest `dollar_volume` aus der Kurszeile für die
Liquiditätsschwelle, schrieb es aber nie in `reasons` — und
`shadow.py:1064` erwartet es genau dort. Damit war die Frage „entsteht
der Vorsprung nur bei illiquiden Werten?" nie beantwortbar. **Behoben**
(reines Protokollfeld).

### Ein Fehler von mir, transparent festgehalten

Beim Bau dieses Nachweises habe ich `src/alpaca_bot/lernkern.py`
**überschrieben** — die Datei existierte bereits mit einer anderen
Aufgabe (Modellregistry und Abnahme statt Experimentwarteschlange).

Wiederhergestellt aus drei erhaltenen Quellen: `tests/test_lernkern.py`
(legt die Schnittstelle fest), `scripts/26_lernkern.py` (den Aufrufweg)
und dem **Datenbankschema samt zwei Originalzeilen**, das die
Feldstruktur exakt vorgab. Die beiden trainierten Modelle und ihre
`.joblib`-Dateien blieben unberührt.

**Lehre:** Vor jedem `cat >` auf eine existierende Datei gehört ein Blick
hinein. Der Verlust war hier reparabel, weil Tests, CLI und Datenbank die
Schnittstelle dreifach festhielten — genau die Redundanz, die dieses
Projekt ohnehin fordert.

### Was der wiederhergestellte Lernkern zeigt

Zwei Läufe lagen bereits in der Registry, beide **abgelehnt**:

| Symbole | Handelstage | IC | t korr. | t roh | Urteil |
|---:|---:|---:|---:|---:|---|
| 299 | 1.074 | 0,0146 | 1,91 | 3,10 | abgelehnt |
| 1.186 | 1.101 | 0,0041 | 0,71 | 1,10 | abgelehnt |

**Der Effekt schrumpft mit der Breite** — dieselbe Signatur wie beim
PEAD-Test (§B4: großartig auf 60 Symbolen, zusammengebrochen auf 800).
Ein dritter Lauf über 250 Symbole ergab Modell IC 0,0308 (t 2,70) gegen
Score IC 0,0184 (t 1,89): Das Modell sortiert besser als der handgebaute
Score, **aber beide bleiben unter der Schwelle von 2,85.**

Regression: `tests/test_nutzung.py` (10 Tests), vier neue Mutationen,
**37 von 37 gefangen** — eine davon entlarvte erneut einen zu schwachen
Test von mir (er prüfte, *dass* gemeldet wird, nicht *womit*).

---

## G16. Der Live-Spiegel spiegelt nicht — und vier stille Lücken (22.08.2026)

**Anlass:** eine vollständige Durchsicht des Projekts ohne konkreten
Verdacht. **Dreizehn Defekte** aus derselben Familie wie §G15 — nichts
stürzt ab, nichts meldet sich, jede Zahl sieht plausibel aus — und ein
vierzehnter Eintrag, der kein Defekt ist, sondern eine erstmals gemessene
Zahl (Fund 14).

Geprüft wurden alle 52 Module (28.384 Zeilen zum Prüfzeitpunkt), 375
öffentliche Funktionen, beide Testschichten, die vier Datenbanken und die
laufenden Dienste. Am Ende: **332 Tests** (vorher 222), 48
Selbstprüfungen, **54 von 54 Mutationen gefangen**, beide Dienste mit dem
neuen Stand neu gestartet.

### Fund 1: `B09_nachkauf` ist kein Live-Spiegel — Schwere: hoch

§G6 hat `B09_nachkauf` zur Referenz für „vergleiche gegen den echten
Live-Bot" erklärt, und `tests/test_konsistenz.py` sichert seither, dass
seine Konfiguration **feldweise** stimmt. Das war richtig — und reichte
nicht. Was beide tatsächlich *tun*:

| | Live-Journal | Spiegelbuch `B09` |
|---|---:|---:|
| Kaufentscheidungen | 131 | 51 |
| **Nachkäufe (`topup`)** | **110 (36 %)** | **0** |
| Positionen | 15 / 15 | 11 / 15 |
| investiert | 91 % | 64 % |

**Die Ursache ist kein Parameter, sondern der Aufrufrhythmus.**
`max_new_positions=3` bedeutet an den beiden Orten Verschiedenes:

```
live.run_once      3 Käufe je ZYKLUS      – Daemon-Takt 15 Min, bis 26/Tag
shadow._spiegel    3 Käufe je HANDELSTAG  – Tagesbar-Rhythmus, ein Durchgang
```

Gemessen: Am 28.07.2026 eröffnete der Live-Bot **50 Positionen an einem
Tag** über 18 Zyklen. Das Spiegelbuch schafft konstruktionsbedingt drei.

**Daran hängt der eigentliche Schaden.** `Engine._find_topups` bekommt
das von `_find_entries` bereits verplante Kapital abgezogen. Solange
Plätze frei sind, ist dieser Betrag das *gesamte* freie Kapital — es gibt
dann **nie** Nachkäufe. Erst im vollen Depot (`slots = 0`,
`entries = []`, `verplant = 0`) entstehen sie. An der Engine
nachgestellt:

| Depotstand | Käufe | Nachkäufe |
|---|---:|---:|
| 11 / 15 Plätze | 4 | **0** |
| 15 / 15 Plätze | 0 | **15** |

Live ist voll → 110 Nachkäufe. Der Spiegel wird nie voll → null.

**Zwei Folgen:**

1. `B09_nachkauf` ist über seine gesamte Laufzeit **bitgleich mit
   `B08_voll_investiert`** (`divergenz()`: 17 Tage, max. Abweichung
   0,00 bps, `identisch=True`). Seine Achse `allow_topup` hat nie
   gebunden — derselbe Befund wie B01/B02/B03/B05 in §E. Er belegt einen
   Flottenplatz und hebt die Schwelle für alle (§B2), ohne etwas zu
   messen.
2. `B11_dyn_ausstieg_live` wird laut BETRIEBSPLAN §3.3 gegen genau
   diesen Bot abgenommen.

**Einordnung — wie schon bei §G6 nicht so schlimm, wie es klingt:** Der
Vergleich B11 gegen B09 bleibt **intern gültig**. Beide Seiten teilen
denselben Rhythmus, die eine getestete Achse
(`zeitausstieg_dynamisch`) ist sauber isoliert. Falsch ist allein die
Behauptung, das Ergebnis sage etwas über den *tatsächlichen* Live-Bot.

**Nebenbefund:** Der Live-Bot lässt bei jedem Lauf Kapital liegen. Die
Engine bemisst die Positionsgrößen für *alle* Vorschläge, ausgeführt
werden nur `max_new_positions`. Im nachgestellten Fall blieben 6.414 $
von 27.574 $ ungenutzt — und der Nachkauf, der genau das auffangen soll,
war durch dieselbe Verplanung blockiert.

**Nicht geändert.** Beides ist Handelslogik während einer laufenden
Messung (CLAUDE.md). Der Weg führt über einen eigenen Flottenbot nach dem
10.10.2026. **Neu:** `shadow.pruefungen()` hat eine zehnte Prüfung
(„Handelsrhythmus Live gegen Spiegel"), die die Abweichung bei jedem
Aufruf ausweist. Regression:
`tests/test_handelsrhythmus.py` (7 Tests).

### Fund 2: Der Musterspeicher hätte sich ab Tag 20 selbst geflutet

`shadow.lernen` ruft seit §G14 täglich
`patterns.kandidaten_suchen(anlegen=True)`. `erfassen()` vergab eine
frische `uuid4` **ohne zu prüfen, ob dieselbe Bedingung schon
existiert**. Drei Defekte lagen scharf, sobald der Schatten seinen 20.
Handelstag erreicht (Stand am 22.08.: **19**):

1. **Duplikate.** Gemessen im Regressionstest: **10 Zeilen nach 5
   Läufen** statt 2. Täglich wären dieselben ~4 Regimeschnitte erneut
   angelegt worden.
2. **Wiederbelebung.** Ein als `zerfallen` markiertes Muster wäre am
   nächsten Tag als frischer `kandidat` zurückgekehrt — der
   Verfallsmechanismus, also der ausdrückliche Zweck des Moduls, wäre
   wirkungslos gewesen.
3. **Ungezählte Versuche.** Jeder Regimeschnitt ist ein Vergleich.
   `hypotheses.erfassen` hebt dafür seit jeher den Versuchszähler,
   `patterns.erfassen` nicht. Wer neun Regimezellen prüft, findet in
   einer garantiert etwas (§B2) — eine Schwelle, die davon nichts weiß,
   ist zu niedrig.

**Behoben:** `erfassen()` ist idempotent über (`bedingung`, `wirkung`),
fasst einen vorhandenen Eintrag nicht an und hebt den Versuchszähler
**nur beim erstmaligen** Anlegen. Regression:
`tests/test_musterspeicher.py` (17 Tests).

#### Betriebsentscheidung vom 22.08.2026: der Lernlauf legt weiter an

Nach der Reparatur stand die Wahl, das automatische Anlegen bis zum
10.10. auszusetzen. **Entschieden: es bleibt an** — der Lernapparat läuft
voll.

Die Folge muss hier stehen, damit sie am Entscheidungstermin niemanden
überrascht: Sobald der Schatten seinen 20. Handelstag erreicht, legt der
Lauf die Regimeschnitte als Kandidaten an, und jeder hebt
`fleet.schwelle_sigma()` **für alle laufenden Messungen, auch
rückwirkend**. Bei vier bis sechs Schnitten steigt sie von **2,85 auf
etwa 2,93**.

Das ist methodisch richtig — ein geprüfter Schnitt *ist* ein Versuch
(§B2), und ihn nicht zu zählen wäre genau die Selbsttäuschung, gegen die
`fleet` gebaut ist. Es ist zugleich eine reale Verschärfung für
`B11_dyn_ausstieg_live`, dessen Kriterium 1 an dieser Schwelle hängt
(BETRIEBSPLAN §3.3).

**Diese Verschärfung ist damit vorab festgelegt und nicht nachträglich
entstanden.** Sie darf am 10.10. nicht als Argument dienen, den Vertrag
anzupassen — weder nach oben noch nach unten. Die aktuelle Schwelle ist
bei jeder Auswertung abrufbar (`python scripts/21_fleet.py`); eine
abgeschriebene Zahl gilt nicht (§3.2).

### Fund 3: Der letzte unkorrigierte t-Wert setzte einen Status

§G12 hat die Überlappungskorrektur an vier Stellen eingebaut.
`hypotheses.historientest` blieb übrig — ausgerechnet die Stelle, an der
aus einer Zahl ein **Urteil** wird:

```python
status = "im_test" if abs(t) > 2 else "widerlegt"
```

Bei einem 5-Tage-Fenster liegt die Fehlalarmquote unkorrigiert bei
**39,5 %** (§G12). Vier von zehn Urteilen wären Rauschen gewesen — in
beide Richtungen: eine brauchbare Idee verworfen oder eine wertlose in
den teuren Vorwärtstest geschickt.

Verschärfend: Die Funktion nahm `horizont` als Parameter entgegen und
benutzte ihn im Rumpf **an keiner Stelle**. Eine Signatur, die eine
Korrektur verspricht, die es nicht gibt, ist schlimmer als gar keine —
sie beruhigt beim Lesen.

**Behoben:** Newey-West über die chronologisch sortierte IC-Reihe, `t_roh`
zum Vergleich daneben, und bei zu kurzer Reihe **kein Urteil** (Status
`offen`, `hist_t` als NULL) statt eines Ersatzwerts. Regression:
`tests/test_hypothesen.py` (9 Tests), inklusive Kalibrierung in beide
Richtungen.

### Fund 4: Ein Abbruchkriterium, das auf einen manuellen Aufruf wartete

BETRIEBSPLAN §8 führt auf: *„Regelabgleich meldet Abweichung → Sofort
aus — ein Regelbruch ist ein Logikfehler, kein Pech."*
`audit.run_audit()` wurde von genau einer Stelle gerufen:
`scripts/13_tagesbericht.py`, laut §5.2 „alle 1–2 Wochen" von Hand. Der
Health-Check kannte ihn nicht.

**Beim Einbauen der zweite Fund:** Der Abgleich meldete einen
`VERSTOSS`, weil **1 von 91** Läufen mit einem HTTP 500 von Alpaca
endete. §H führt genau diesen Vorfall als *bestandene* Betriebsprüfung.
Unverändert eingebaut hätte die Ampel ab sofort dauerhaft ROT gezeigt —
und eine Warnung, die immer leuchtet, wird weggeklickt
(`docs/LERNTEMPO.md` §5).

**Behoben:** Die **Quote** entscheidet über die Schwere
(`FEHLERQUOTE_VERSTOSS = 0,20`), nicht die absolute Zahl. Der
Health-Check ruft den Regelabgleich jetzt bei jedem Lauf; ein Verstoß
färbt ROT, eine Auffälligkeit wird nur genannt. Regression:
`tests/test_regelabgleich.py` (7 Tests).

### Fund 5: Ein abstürzender Baustein galt als gesund

Im Schatten-Log standen drei
`sqlite3.OperationalError: unable to open database file` — alle drei
Schritte eines Durchgangs scheiterten. `16_shadow_daemon.py` fängt das ab
und meldet `nutzung.melden(baustein, -1, signatur="fehler")`.

Der Wächter aus §G15 erkannte das **nicht**: `darf_leer_sein=True` (für
alle Schattenschritte gesetzt) überspringt die Leer-Prüfung, `-1` ist
nicht `0`, und „immer_gleich" braucht **fünf** Läufe. Ein Baustein, der
bei jedem Aufruf abstürzt, ist der eindeutigste Ausfall überhaupt — und
wurde bestenfalls als mildeste Kategorie gemeldet, mit dem irreführenden
Text „es entsteht keine neue Information". Sie entsteht sehr wohl: die
Information, dass es kaputt ist.

**Behoben:** fünfte Ausfallart `fehlerhaft`, die am **jüngsten** Lauf
hängt und sofort greift. Am jüngsten, damit ein überstandener Netzausfall
erledigt ist, sobald wieder etwas durchläuft.

### Fund 6: Das Kriterium, das die Strategie trägt, lief nirgends

§G12 hat den t-Wert der tragenden Faktoren entwertet — `rsi2` (2,70) und
`reversal_3d` (2,79) halten die Schwelle 2,85 nach Korrektur nicht mehr.
Was den Befund dennoch trägt, benennt §G12 ausdrücklich:

> `ReversalWeights` nennt als Kriterium ausdrücklich die
> **Vorzeichenstabilität je Jahr** („100 % positive Jahre") — ein anderes
> und robusteres Kriterium als der t-Wert, das von dieser Korrektur
> unberührt bleibt.

`research.measure_stability` und `research.stability_report` messen genau
das. **Beide wurden von keinem Skript aufgerufen.** `11_factor_lab.py`
fuhr nur `measure_factors` → `summarize` → `select_factors` — alles am
t-Wert hängend.

Damit war das Kriterium, auf dem die Strategie steht, aus dem laufenden
Werkzeug heraus **nicht reproduzierbar**. Die „100 % positive Jahre"
stammen aus einem Messlauf, den niemand wiederholen konnte, ohne die
Funktion von Hand zu rufen. Dieselbe Fehlerklasse wie §G15.

**Zweiter Defekt im selben Skript:** Die Zusammenfassung unter der
Rangliste filterte mit `results["t_stat"] >= 3.0` — dem **rohen** Wert —
während `select_factors` daneben korrekt `t_korrigiert` prüfte. Zwei
verschiedene Schwellen in derselben Ausgabe, und die laxere stand in der
Zeile, die man zitiert („stärkster positiver Faktor").

**Behoben:** `11_factor_lab.py` hat einen fünften Schritt
(„Hält das Vorzeichen über die Jahre?"), legt `stabilitaet.csv` ab, und
alle Anzeigen rechnen mit dem korrigierten Wert. Regression:
`tests/test_musterspeicher.py::TestVorzeichenstabilitaetIstVerdrahtet`.

### Fund 7: 17 durchgeführte Versuche, die niemand mehr sah

`lernkern.sqlite` enthielt die Tabellen `experimente` (17 Zeilen) und
`ergebnisse` (17) — Reste der Experimentwarteschlange, die beim Bau des
Nutzungsnachweises überschrieben wurde (§G15 hält den Vorfall selbst
fest: „Vor jedem `cat >` auf eine existierende Datei gehört ein Blick
hinein"). Wiederhergestellt wurde damals der **Code**; die **Daten**
blieben liegen, und kein Modul las sie mehr.

**Was drinstand, bevor gelöscht wurde.** Drei Familien (`merkmal` 7,
`haltedauer` 5, `bedingung` 5), alle am 22.08.2026 in einem einzigen
Lauf, alle Status `fertig`, **alle mit `befund = 0`** — kein einziger
Treffer. Die Schwelle wuchs innerhalb des Laufs von 0,50 auf 2,85; der
Zähler war also lauf-lokal und von `fleet.n_versuche` getrennt.

Methodisch sind sie überholt: Sie liefen auf **8 bis 14 Handelstagen**.
Für einen 5-Tage-Horizont ist das laut §G14 zu wenig für einen gültigen
t-Wert — entsprechend steht bei 13 der 17 Zeilen `t_wert = NULL`, während
der rohe danebensteht. Genau das Verhalten, das §G14 als richtig
festgelegt hat.

**Entscheidung (22.08.2026): verworfen.** Sicherung als
`lernkern.vor_experimente_entfernt_20260822_172234.sqlite`, danach beide
Tabellen entfernt; `modelle` (die Registry, 3 Zeilen) blieb unberührt.
Nicht in den Versuchszähler nachgetragen, weil kein Experiment eine
Aussage getragen hat und die Messmethodik seit §G14 eine andere ist — ein
Nachtrag hätte die Schwelle für die laufende B11-Messung gehoben, ohne
dass je etwas gemessen worden wäre.

**Eine Beobachtung daraus ist aufhebenswert — ausdrücklich KEIN Befund:**

| Frage | Tage | t roh | t korr. | Schwelle |
|---|---:|---:|---:|---:|
| Sortiert `news_z` die Kandidaten? | 9 | **−3,12** | — | 2,76 |
| Sortiert `news_5d` die Kandidaten? | 9 | −0,88 | — | 2,83 |

Der korrigierte Wert ist nicht berechenbar (9 Tage), der rohe ist laut
§G12 nicht zitierfähig. Es ist also **nichts gemessen**. Aufhebenswert
ist es trotzdem: `signals.ReversalWeights.news` ist der einzige Baustein,
der **ohne vorherige Messung** eingebaut wurde (03.08.2026, bewusste
Abweichung von der Projektregel), und er führt seine eigene
Abbruchbedingung mit — *„Fällt die Auswertung negativ aus, gehört dieser
Faktor wieder auf 0."* Das Vorzeichen zeigt in diese Richtung.

**Zu prüfen, sobald 20+ auswertbare Handelstage vorliegen** — über das
Feld `news_aktiv`, das genau für diese Trennung protokolliert wird.

### Fund 8: Die PDT-Gegenprobe ist gebaut und leer

`state.py` führt eine eigene Daytrade-Tabelle, und
`compliance.day_trades_from_orders` ist ausdrücklich als „Gegenprobe zum
`daytrade_count` des Brokers" dokumentiert — *„wenn beide auseinander
laufen, stimmt die eigene Buchführung nicht."*

Gemessen: `day_trades` enthält **0 Zeilen**. `record_day_trade` wird
nirgends aufgerufen, `day_trades_last` und `day_trades_from_orders`
ebenfalls nicht. Die Gegenprobe existiert als Code und hat nie
stattgefunden.

**Derzeit folgenlos:** Die PDT-Regel greift erst unter 25.000 $, das
Konto steht bei 109.701 $ (§G4 stuft das Risiko entsprechend als
„gering" ein). **Nicht behoben** — das Füllen der Tabelle gehört in den
Live-Pfad und damit hinter einen Dienstneustart; als Sicherung wird sie
erst relevant, wenn das Konto unter die Schwelle fällt. Festgehalten,
damit sie nicht für vorhanden gehalten wird.

### Fund 9: Die Kostenkontrolle maß eine andere Zahl als der Vertrag

**Der wichtigste Fund mit positivem Ausgang.** `shadow.pruefungen()`
Nr. 5 meldete dauerhaft FEHL:

> Depot misst −92,0 bps Slippage (n-gewichtet, 178 Füllungen), Schatten
> setzt 3,0 bps an. **Schatten ist zu optimistisch.**

Beide Teile der Meldung waren falsch.

**Falsche Kennzahl.** Der Entscheidungsvertrag nennt zweimal
ausdrücklich den **Median** — §3.1 („Slippage-Median < 8 bps über 30+
saubere Orders") und §8 („Slippage-Median > 15 bps → alle Ergebnisse neu
bewerten"). Die Prüfung rechnete einen n-gewichteten **Mittelwert**. An
denselben 162 prüfbaren Orders:

| Kennzahl | Wert | Urteil |
|---|---:|---|
| **Median** (Vertrag) | **+0,0 bps** | §3.1 **erfüllt** |
| Mittelwert (Prüfung) | −71,7 bps | meldet FEHL |

Die Differenz stammt aus Datenfehlern, die dieses Register selbst führt
(§G, 04.08.2026): **KGS −1.648 bps** und **SIMO −1.584 bps** sind
kaputte IEX-Quotes, keine Ausführungsqualität. Genau gegen solche
Artefakte ist der Median robust — und genau deshalb steht er im Vertrag.

**Falsche Ebene.** Der erste Reparaturversuch nahm den Median über die
**Symbol**-Mediane. Ein Regressionstest hat ihn sofort widerlegt: Bei 73
Symbolen mit 1 bis 6 Füllungen gewichtet das ein Symbol mit einer Order
genauso wie eines mit sechs. §3.1 sagt wörtlich „über 30+ saubere
**Orders**". Behoben über `journal.slippage_werte()`, das sich die
Bereinigung mit `slippage_report()` teilt — getrennte Filter hätten
Bericht und Prüfung auf verschiedenen Grundmengen rechnen lassen.

**Falsche Richtung.** Bei der Vorzeichenkonvention aus `journal.order()`
heißt negativ *günstiger als erwartet*. Der Satz „Schatten ist zu
optimistisch" beschreibt den umgekehrten Fall.

**Folge für §3.1 — die Kernfrage des Projekts.** Mit der richtigen
Kennzahl ist die Ausführungsbedingung **erfüllt**: 162 prüfbare Orders
gegen die geforderten 30, Median +0,0 bps gegen die geforderten < 8. Das
beantwortet allerdings nur die eine Hälfte: Spread und Gebühren fallen im
Papierdepot gar nicht erst an, der Rundlauf-Breakeven von 0,142 % bleibt
vollständig bestehen, und der gemessene Vorsprung von +0,11 % liegt
weiterhin darunter (§A). Der Engpass ist nicht mehr die Ausführung,
sondern weiterhin der Vorsprung.

Die 24 Orders über |100| bps bleiben in der Meldung sichtbar — sie sind
Information, kein Rauschen. Ein stiller Median wäre die andere Hälfte
desselben Fehlers.

### Fund 10: Die Kursanpassungsprüfung musste zwangsläufig anschlagen

Prüfung 4 meldete FEHL: „1.525 von 19.788 Ergebnissen mit rückwirkend
geändertem Kurs (7,7 %)" gegen eine Schwelle von 5 %.

Aufgeschlüsselt je Stichtag zeigt sich, dass die Schwelle gar nicht
halten *kann*:

| Stichtage | Anteil angepasst |
|---|---:|
| 28.07. – 07.08. (alt) | 6 % bis **25 %** |
| 13.08. – 20.08. (jung) | 0 % bis 4 % |
| kumuliert | 7,7 % → FEHL |

yfinance lädt mit `auto_adjust=True` und passt historische Kurse nach
**jeder** Dividende und jedem Split rückwirkend an. Je älter ein
Stichtag, desto mehr solcher Ereignisse liegen dahinter. Die kumulierte
Quote **muss** also mit der Betriebsdauer wachsen.

Das ist exakt der Fehlversuch, den `data_integrity.check_stumme_felder`
schon einmal gemacht hat und den §G13 festhält: eine Quote über die
Historie prüfen statt der gefährlichen Richtung.

Gefährlich ist der umgekehrte Fall — **frische** Stichtage mit hoher
Anpassungsrate. Das hieße, die Kursquelle ändert Daten, die gerade erst
entstanden sind, und dann sind die jüngsten Vorhersagen betroffen.

**Behoben:** `_pruefe_kursanpassung` prüft die jüngsten 5 Stichtage
gegen 15 %; der Historienwert wird zur Einordnung mitgenannt. Aktuell:
1,2 % an der jungen Kante. Regression: `tests/test_kostenkontrolle.py`
(10 Tests), drei neue Mutationen — **48 von 48 gefangen**.

### Fund 11: Der Tagesbericht meldete eine erfundene Zahl

Derselbe Mittelwert-Fehler wie Fund 9, an sichtbarerer Stelle.
`scripts/13_tagesbericht.py` ruft `costs.reconcile()` in Abschnitt
„[3] AUSFÜHRUNG" — und BETRIEBSPLAN §5.2 nennt genau diesen Abschnitt
als das, was alle 1–2 Wochen zu lesen ist, mit der ausdrücklichen
Erwartung *„Slippage-Median"*. Ausgegeben wurde:

```
angenommen :    3.0 bps
tatsaechlich:  -80.6 bps
-> Ausfuehrung ist 83.6 bps besser als angenommen.
```

`journal_df["mittel"].mean()` mittelt die Symbol-Mittelwerte
**ungewichtet** — drei kaputte IEX-Quotes tragen darin genauso viel wie
70 saubere Symbole. Die Aussage „83,6 bps besser" war frei erfunden.

**Behoben:** `reconcile` nimmt die Einzelwerte über den neuen Zugang
`journal.slippage_werte()` und rechnet den Median über **Orders** — die
Ebene, die §3.1 meint. Beide teilen sich dieselbe Bereinigung
(`_slippage_basis`), damit Bericht und Prüfung nie auf verschiedenen
Grundmengen rechnen. Der Bericht sagt jetzt: `0.0 bps (Median über 162
Orders)`, mit den 24 Ausreißern daneben.

### Fund 12: Die Faktorauswahl versprach einen Filter, den es nicht gab

`research.select_factors` nahm zwei Parameter entgegen, die im Rumpf
**an keiner Stelle** benutzt wurden:

```python
max_correlation: float = 0.7
factor_data: dict[str, pd.DataFrame] | None = None
```

Ausgewählt wurden schlicht die Top-N nach t-Wert. Dieselbe Fehlerklasse
wie Fund 3 (`historientest(horizont)`) — eine Signatur, die eine Prüfung
verspricht, die nicht stattfindet.

Das wiegt hier besonders, weil das Projekt die Redundanz seiner eigenen
Faktoren an **drei** Stellen aufschreibt: `research.py` („möglichst wenig
korrelierter Anzeichen"), `ReversalWeights` („messen im Kern dasselbe …
fünf Messungen desselben Effekts sind nicht fünfmal so viel Signal") und
§A. Der Mechanismus, der genau das verhindern soll, war nicht gebaut.

**Behoben:** Gieriger Filter entlang der t-Rangliste, |Korrelation|
gemessen (ein invertierter Klon ist genauso redundant wie ein Klon).
`measure_factors(mit_panels=True)` liefert die Faktorwerte, die der
Filter braucht — sie entstehen ohnehin und wurden bisher verworfen.
Fehlen sie, wird das **gemeldet** statt still durchzulassen.

### Fund 13: Ein ignoriertes CLI-Argument im Abnahme-Skript

`shadow_eval.vergleich_gepaart` nahm `buch="spiegel"` entgegen und
benutzte es nie — gerechnet wurde stets auf `equity_kurve`.
`scripts/21_fleet.py` bot es als `--buch {spiegel,rangliste}` an und
reichte es durch: **Wer `--buch rangliste` wählte, bekam still das
Spiegelbuch-Ergebnis.** Das ist das Skript, mit dem am 10.10. abgenommen
wird.

**Behoben durch Entfernen, nicht durch Implementieren.** Der Parameter
ist konzeptionell nicht erfüllbar: Verglichen werden Equity-Kurven, und
ein Depot hat nur das Spiegelbuch. Das Ranglisten-Buch zeichnet
Kandidaten ohne Kapitalgrenze auf — dort gibt es keine Kurve. Ein
Parameter, dessen zweiter Wert unmöglich ist, gehört nicht in die
Signatur.

### Fund 14: Die vier Score-Bausteine tragen 1,53 Signale, nicht 4

**Der aufschlussreichste Fund dieser Runde** — er entstand beim Bau des
Korrelationsfilters aus Fund 12 und ist kein Defekt, sondern eine
erstmals gemessene Zahl.

Gemessen an **198.038 echten Beobachtungen** über 396 Symbole, für die
vier Bausteine, die tatsächlich in den Score eingehen:

| | `f_rueckgang` | `f_rsi2` | `f_ausverkauf` | `f_band_unten` |
|---|---:|---:|---:|---:|
| `f_rueckgang` | 1,00 | **0,69** | 0,57 | 0,50 |
| `f_rsi2` | 0,69 | 1,00 | 0,42 | 0,49 |
| `f_ausverkauf` | 0,57 | 0,42 | 1,00 | 0,32 |
| `f_band_unten` | 0,50 | 0,49 | 0,32 | 1,00 |

**Kein einziges Paar liegt über 0,7** — der Paarfilter aus Fund 12 hätte
nichts verworfen. Die effektive Zahl unabhängiger Bausteine
(`1/(w'Rw)`, mit den echten Score-Gewichten) liegt aber bei **1,53 von
4**; ungewichtet bei 1,60.

Damit ist §A erstmals mit einer Zahl belegt. Der Satz *„die Summe ist
NICHT fünfmal so viel Signal"* stimmt — es ist rund **anderthalbmal** so
viel.

**Die methodische Lehre ist die wichtigere:** Paarweise Korrelation ist
das falsche Maß. Vier Faktoren können paarweise alle sauber sein und
gemeinsam fast dasselbe messen. `select_factors` weist die effektive
Breite deshalb bei jeder Auswahl mit aus.

**Was das NICHT heißt.** Es ist kein Urteil über die Strategie und kein
Grund für eine Gewichtsänderung (CLAUDE.md). Die Breite im Sinne von
`IR = IC·√BR` kommt aus den **Symbolen** (1.200 je Tag), nicht aus den
Faktoren. Eine niedrige effektive Faktorbreite heißt nur: Die Gewichtung
glättet, sie addiert keine unabhängige Information — genau das, was
`ReversalWeights` im eigenen Docstring bereits behauptet hatte, ohne es
je gemessen zu haben.

Bemerkenswert am Rande: `f_ausverkauf` ist mit 0,32–0,57 der
unabhängigste Baustein — er trägt die meiste eigenständige Information
und hat mit 0,25 nur das dritthöchste Gewicht. Eine Beobachtung, keine
Empfehlung; der Weg zu einer anderen Gewichtung führt über die Flotte.

Regression: `tests/test_faktorauswahl.py` (16 Tests), zwei neue
Mutationen.

### Nebenbefund: eine abgeschriebene Zahl war bereits gedriftet

`fokus.hebel()` trug den Satz „Der Bot handelt 1.200 von **2.189**
liquiden Symbolen" fest im Code. `universum.csv` enthält **2.168**;
§G11 Fund 3 nennt ebenfalls 2.168, §H führt 2.189. Dasselbe Prinzip, das
BETRIEBSPLAN §3.2 für die Signifikanzschwelle festlegt („hier steht
bewusst keine Zahl"), gilt für den Code. Beide Zahlen kommen jetzt aus
den Quellen: die gehandelte aus der Voreinstellung von `12_daemon.py`,
die verfügbare aus `universum.csv`, die Historientage aus `trades.csv`.

### Was die Prüfung NICHT gefunden hat

Damit der Bericht nicht nur aus Funden besteht — diese Vermutungen haben
sich an den Daten **nicht** bestätigt:

* **`vergleich_gepaart` braucht keine Überlappungskorrektur.** Der
  Verdacht lag nahe (§G12). Gemessen an allen Bot-Paaren: Die
  Autokorrelation der Tagesdifferenz `d_t` liegt zwischen −0,16 und
  +0,18, die Aufblähung zwischen **0,70× und 1,20×**. Die Differenz
  zweier Equity-Tagesrenditen ist ein Horizont-1-Wert — hier zu
  „korrigieren" würde den t-Wert teils *erhöhen*. Bleibt wie es ist.
* Kein totes Modul: alle 52 Module in `src/alpaca_bot/` sind verdrahtet.
* Der Mutationstest fing nach der Erweiterung **51 von 51** — darunter
  eine, die einen zu schwachen Test von mir entlarvte (er prüfte den
  `nan`-Wert, aber nicht den daraus folgenden Status).

---

## G17. Die zwei ungeprüften Werkzeuge — geprüft, behalten, abgesichert (22.08.2026)

**Anlass:** Nach §G16 blieben zwei Flächen ohne Testabdeckung übrig —
`src/alpaca_bot/rl/` (keine einzige Testdatei) und `events.py` (nur
`00_selftest.py` [6]). Die Frage war: einbinden oder entfernen?

### Die Entscheidung: behalten

Der entscheidende Test war nicht „wird es benutzt", sondern **„läuft es
noch, und ist es kalibriert?"** Ein Werkzeug, das man nicht starten kann,
ist toter Code — egal wie gut es aussieht.

| | läuft | methodisch | Abdeckung vorher |
|---|---|---|---|
| `events.py` | ja, `00_selftest` [6] grün | Kontrollgruppe **und** Sperrzone | 4 Selbsttest-Prüfungen |
| `rl/` | ja, Lauf in 5 s | Timing-Test nicht abschaltbar | **keine** |

Beide sind **Werkzeuge, keine Dauerläufer** — wie `03_backtest.py`. Dass
sie nicht im 15-Minuten-Takt laufen, ist ihre Bestimmung, kein Ausfall
im Sinne von §G15. Der Nutzungsnachweis überwacht sie deshalb bewusst
nicht.

Entscheidend für RL: Ein Lauf auf reinem Rauschen meldet korrekt **„KEIN
nachweisbares Timing-Können"** (Perzentil 17 von geforderten 95). Ein
Werkzeug, das bei Rauschen schweigt, ist die Voraussetzung dafür, seinem
Urteil bei echten Daten zu trauen.

Gegen ein Entfernen sprach zusätzlich, dass `README.md` den Timing-Test
als eine der **fünf Sicherungen** führt und `selfcheck.CHARTER` Regel 7
ihn verlangt. Der Preis ist sichtbar: `torch` belegt **535 MB von
1,2 GB** der Umgebung.

### Die eigentliche Lücke war die Absicherung

Der Modul-Docstring behauptet, der Timing-Test sei „fest verdrahtet und
lässt sich nicht abschalten". Das war eine **Behauptung** — genau die Art
Zusicherung, die dieses Projekt sonst durch Tests deckt. Nachgeprüft: Sie
stimmt, es gibt keinen Schalter. Jetzt ist sie auch getestet.

### Erstmals gemessen: die Fehlalarmquote des Timing-Tests

Auf reinem Random Walk, 400 Läufe je Variante:

| Politik | Fehlalarm | Soll |
|---|---:|---:|
| träge (15 % Umschichtwahrscheinlichkeit) | **8,5 %** | 5 % |
| häufig (50 %) | 6,8 % | 5 % |

**Kein Defekt, sondern eine Eigenschaft des Verfahrens.** Zyklisch
rotierte Kopien einer trägen Positionsfolge sind untereinander
korreliert — benachbarte Rotationen unterscheiden sich kaum. Die
Nullverteilung wird zu eng, der echte Wert liegt öfter am Rand.
Derselbe Mechanismus wie bei den überlappenden Renditefenstern in §G12,
und in derselben Größenordnung: §G12 nennt für die korrigierte Statistik
11 % und benennt das ausdrücklich als ehrliche Restunschärfe.

**Eine Ursachenhypothese wurde geprüft und verworfen.**
`np.diff(e, prepend=0.0)` unterstellt jeder Rotation einen Kaltstart aus
Position 0, den nur die echte Folge per Konstruktion hat (`env.reset`).
Der Effekt ist real — im Mittel 2,3 bps einmalig — ändert die
Fehlalarmquote aber **nicht** (7,8 % mit und ohne). Deshalb wurde dort
nichts geändert: eine Korrektur ohne gemessene Wirkung wäre Kosmetik.

**Folge für die Nutzung:** Ein einzelner Lauf über Perzentil 95 ist bei
~8 % Fehlalarmquote kein Nachweis. Genau das sagt `verdict()` bereits —
*„Schwacher Hinweis auf Timing-Können, nicht belastbar. Mit anderen
Startwerten, Symbolen und Zeiträumen wiederholen."*

### Zwei eigene Fehler, vom Werkzeug gefangen

1. Der Hellseher-Test war **um einen Tag verschoben**. `total()` rechnet
   `e * ret` — das Exposure wirkt auf dieselbe Tagesrendite. Falsch
   ausgerichtet ergab er Perzentil 2 statt 100. Auch das ist ein
   korrektes Signal, nur das umgekehrte; beide Richtungen sind jetzt
   Testfälle.
2. Der Mutationstest entlarvte einen zu schwachen Test von mir — zum
   zweiten Mal in dieser Sitzung. Meine Sperrzonen-Tests gaben
   `blackout` explizit an und blieben grün, als die Mutation den
   **Standardwert** auf 0 setzte. Ein Test, der nur seine eigenen
   Argumente prüft, prüft die Voreinstellung nicht.

Regression: `tests/test_werkzeuge.py` (16 Tests), drei neue Mutationen —
**54 von 54 gefangen**.


## G18. Drei stille Ausfälle in den Sicherungen selbst (22.08.2026)

**Anlass:** letzte Gegenprüfung, diesmal nach zwei Fehlerklassen
gesucht, die sich mechanisch finden lassen — vollständig stille
`except`-Blöcke und verbliebene unkorrigierte t-Werte. 26 stille Blöcke
gefunden, die meisten bewusst und dokumentiert. **Drei waren es nicht** —
und ein vierter Fund entstand beim Prüfen selbst.

### Fund 1: Das Risiko-Dach verlor Positionen — Schwere: hoch

`risiko._kennzahlen` und `risiko.sektor_anteile` rechneten:

```python
abs(float(r["qty"]) * float(r.get("current_price") or 0))
```

in einem `except (TypeError, ValueError): continue`. Zwei Wege, auf
denen eine Position **still** aus der Risikorechnung verschwand:

* `current_price` ist `None` — `account.positions()` setzt das Feld
  ausdrücklich so, wenn Alpaca keinen Kurs liefert (Handelsaussetzung).
  `or 0` machte daraus den Wert **null**, ganz ohne Exception.
* `qty` unlesbar — die Zeile fiel per `continue` heraus.

Gemessen an drei Positionen à 30.000 $ auf 100.000 $ Konto:

| | Positionswert | Exposure | Sektoranteil |
|---|---:|---:|---:|
| alle Werte lesbar | 90.000 $ | 90 % | 90 % |
| ein Kurs fehlt | 60.000 $ | **60 %** | **60 %** |
| eine Menge unlesbar | 60.000 $ | **60 %** | **60 %** |

**Das Dach unterschätzte damit und ließ Käufe zu, die es sonst blockiert
hätte** — der genaue Gegensatz zu seinem eigenen Grundsatz: *„Fällt die
Risikoprüfung selbst aus, wird nicht gehandelt. Ein Risiko-Dach, das im
Zweifel durchlässt, ist keines."*

Besonders unangenehm: `sektor_anteile` schreibt dasselbe Prinzip eine
Ebene höher schon auf — *„Symbole ohne Sektorangabe zählen unter
'unbekannt' — sie verschwinden nicht stillschweigend, sonst sähe ein
Depot ohne Sektordaten wie ein perfekt gestreutes aus."* Für die
**Zahlen** galt es nicht.

**Behoben:** `risiko.positionswert()` mit Fallback-Kette vom genauesten
zum konservativsten Wert — `market_value` → `qty·current_price` →
`qty·avg_entry`. Der Einstand ist eine Untergrenze, aber ein Wert. Erst
wenn auch die Menge fehlt, ist nichts bestimmbar; dann wird die Position
**gezählt und benannt** (`n_unbewertbar`, `unbewertbar`) statt
übersprungen, und `pruefe_order` blockiert Neukäufe — Verkäufe bleiben
erlaubt, eine Sperre darf nie zur Falle werden.

### Fund 2: Die JSONL-Sicherung konnte still verschwinden

`journal.py` beschreibt die Aufgabenteilung selbst: *„SQLite ist die
Auswertungsschicht, JSONL die Sicherung — wäre die Datenbank je
beschädigt, ließe sie sich daraus vollständig rekonstruieren."*

`_write_raw` fing `OSError`/`ValueError` mit `pass` ab. Ein voller
Datenträger oder eine entzogene Schreibberechtigung wäre erst
aufgefallen, **wenn man die Sicherung braucht** — §G15 in seiner
teuersten Form.

**Behoben:** Meldung statt Schweigen, aber nur **einmal je Lauf** (eine
Meldung je Zeile wäre Lärm, und Lärm wird überlesen — dieselbe Lehre wie
beim Feld-Wächter §G13). Geworfen wird weiterhin nicht: Der Ausfall der
Sicherung darf den Handel nicht stoppen.

### Fund 3: Die letzte unkorrigierte t-Wert-Stelle

§G12 hat die Überlappungskorrektur an fünf Stellen eingebaut —
`statistik`, `research`, `shadow_eval`, `nachbetrachtung`,
`10_simulate.py`. §G16 Fund 3 fand `hypotheses.py` als sechste.
**`earnings.py` war die siebte und letzte.**

Das fällt hier ins Gewicht, weil `19_faktor_tests.py` die Kennzahl über
Horizonte von **1 bis 60 Tagen** abruft. Bei einem 60-Tage-Fenster
teilen benachbarte Tage 59/60 ihres Renditefensters — der rohe t-Wert
ist dort weit jenseits von „etwas zu hoch".

Und der Horizont war die ganze Zeit bekannt: `19_faktor_tests.py`
schrieb ihn **nachträglich ins Ergebnis** (`k["horizont"] = h`), statt
ihn in die Rechnung zu geben.

**Behoben:** `kennzahlen(..., horizont=)` mit Newey-West, `t_roh`
daneben, und das Skript reicht `horizont=h` durch.

### Fund 4: Der Wächter hätte an jedem Wochenende gelb geleuchtet

**Gefunden durch die eigene Arbeit.** Nach dem Dienstneustart meldete der
Health-Check GELB — an einem Samstag:

```
Baustein 'schatten.einbuchen': 6 Laeufe, aber immer dasselbe
Ergebnis (0@2026-08-21) - es entsteht keine neue Information
```

Der letzte Handelstag war Freitag. Die vier Schattenschritte sind seit
§G14 **per Konstruktion idempotent** — ohne neuen Handelstag *müssen* sie
dasselbe liefern; genau dafür wurden sie umgebaut. Der Wächter hätte
damit an jedem Wochenende und Feiertag gelb geleuchtet, also an rund
**zwei von sieben Tagen**. Und eine Warnung, die immer leuchtet, wird
weggeklickt (`docs/LERNTEMPO.md` §5).

**Die Unterscheidung steckte längst in den Daten.** Die Signatur ist nach
Konvention `"<ergebnis>@<datenstand>"`:

| | Signaturen | Urteil |
|---|---|---|
| Wochenende | `0@2026-08-21`, `0@2026-08-21`, … | Ruhe, kein Befund |
| §G14-Zustand | `19788@08-21`, `19788@08-20`, … | **es entsteht nichts** |

Derselbe Datenstand heißt: Es gab nichts Neues. Ein *wandernder*
Datenstand bei stehendem Ergebnis ist der teure Fall.

**Nebenbefund — der bestehende Test bildete §G14 gar nicht ab.** Er legte
acht Läufe mit demselben Stichtag an. Genau das ist am Wochenende der
Normalfall; der Test hätte den echten Zustand nie von der Ruhe getrennt.
Jetzt wandern die Stichtage.

### Was diese Runde sonst geprüft und für gut befunden hat

* **26 stille `except`-Blöcke** insgesamt — die übrigen 23 sind bewusst
  und im Code begründet (Quote-Ausfall darf keine Order verhindern,
  Heartbeat im Fehlerbehandler, Symbol nicht in Bars).
* `costs.FeeSchedule.is_stale()` wird von `selfcheck.py:310` geprüft —
  die Gebührensätze veralten nicht unbemerkt.
* `ratelimit`: Keine Quelle führt zwei zeitbasierte Limits gleichzeitig,
  der geteilte Ereigniszähler ist damit unkritisch.

Regression: `tests/test_risiko_bewertbarkeit.py` (17 Tests) und vier
neue Fälle in `tests/test_nutzung.py`, fünf neue Mutationen —
**59 von 59 gefangen**.


## G19. Acht Funde in der Datenwahrheit — und ein Vertrag mit drei Referenzen (23.08.2026)

**Anlass:** fünfte vollständige Durchsicht, diesmal mit zwei Leitfragen —
*„liefert dieses Artefakt die Daten, die es zu liefern behauptet?"* und
*„sagen Code und Dokument dasselbe?"*. Ausgangslage: Testsuite grün,
Health-Check grün, Arbeitsbaum sauber.

**Vorweg, weil es beim Prüfen sofort auffällt und keiner ist:** Das
Live-Journal stand seit Freitag 21.08. 20:15 UTC still. Das ist korrekt —
22./23.08. sind Wochenende.

### Fund 1: Der Entscheidungsvertrag für den 10.10. hatte drei Referenzen — Schwere: hoch

Die Frage *„wogegen wird `B11_dyn_ausstieg_live` abgenommen?"* hatte vier
Antworten an vier Orten:

| Quelle | Referenz |
|---|---|
| `BETRIEBSPLAN` §3.3 (Vertragstext, 3 Stellen) | `B00_basis` |
| Flottenregistrierung in `shadow.sqlite` | `B09_nachkauf` |
| `21_fleet.py --basis` (Standardwert) | `B00_basis` |
| `fokus.offene_fragen` (per Test gepinnt) | `B09_nachkauf` |

**Keine Formalie.** Gemessen an den echten Schattendaten:

```
--kriterien B11_dyn_ausstieg_live                        t = 0,99
--kriterien B11_dyn_ausstieg_live --basis B09_nachkauf   t = 1,24
```

Beide Zahlen heißen „Kriterium 1 aus §3.3".

**`B00_basis` war die widerlegte Antwort.** §G6 hat sie am 16.08.2026
verworfen — der Live-Bot läuft seit dem 30.07. mit
`deploy_to_target=True` und `allow_topup=True`, `B00_basis` steht auf
`False`/`False`. `B11_dyn_ausstieg_live` wurde daraufhin **eigens** gegen
`B09_nachkauf` angemeldet; daher sein Namenszusatz „gegen echte
Live-Basis". Der Betriebsplan wurde nie nachgezogen, obwohl er zuletzt am
22.08. bearbeitet wurde — und §G16 Fund 1 zitiert ihn sogar mit *„laut
BETRIEBSPLAN §3.3 gegen genau diesen Bot"*. Er sagte das nicht.

**Verschärfend:** `shadow.pruefungen()` Nr. 10 meldet gleichzeitig FEHL —
*„B09_nachkauf ist KEIN Live-Spiegel"* (§G16 Fund 1). Der Vertrag nannte
also eine widerlegte Referenz, das ausführende Kommando nahm sie als
Vorgabe, und die registrierte Alternative ist ihrerseits als kein Spiegel
markiert.

**Behoben:** `shadow_eval.referenz_bot()` liest die Registrierung;
`kriterien_pruefen`/`kriterien_text`/`--basis` haben `None` statt eines
Botnamens als Vorgabe. Die Ausgabe weist die Herkunft der Referenz jetzt
im Kopf aus (`registrierte Basis` vs. `VON HAND GESETZT`). Der
Betriebsplan nennt `B09_nachkauf` — die **vier Kriterien selbst bleiben
Wort für Wort unverändert**, es ist keine nachträgliche Anpassung,
sondern die Rückkehr zur Festlegung vom 16.08.

**Lehre:** Eine Registrierung ist unveränderlich und datiert. Ein
Dokumentsatz ist beides nicht. Wo beide etwas über dieselbe Messung
sagen, gewinnt die Registrierung — dasselbe Prinzip, mit dem
`BETRIEBSPLAN` §3.2 verbietet, `schwelle_sigma()` abzuschreiben.

### Fund 2: Dieses Register senkte die eigene Signifikanzhürde

`fleet.schwelle_sigma()` steht bei **2,85** (16 Versuche). Dieses Dokument
schrieb an **fünf Stellen 2,73** — §B2 (dazu „Aktuell 12 Versuche"), §D
dreimal, §I einmal. Der übrige Text nutzt korrekt 2,85.

Das verstößt gegen die eigene Regel. `CLAUDE.md`: *„Aktuelle
Signifikanzschwelle: `fleet.schwelle_sigma()`"*. `BETRIEBSPLAN` §3.2:
*„Eine abgeschriebene Zahl im Dokument wäre nach der nächsten Anmeldung
falsch und würde die Hürde nachträglich senken."* Sie war es bereits.

Die „Stand"-Spalte in §D war ebenfalls gedriftet: B04 mit 0,94 notiert
(aktuell 1,26), B07 mit −2,42 (aktuell −1,93), B08/B09 mit 0,14
(aktuell 0,70).

**Behoben:** §B2, §D und §I verweisen auf `fleet.schwelle_sigma()` und
`scripts/27_status.py`, statt zu beziffern. Wo eine Momentaufnahme
nützlich ist, steht sie **datiert und ausdrücklich nicht
fortzuschreiben**.

### Fund 3: Die Slippage-Bereinigung filterte auf einen Wert, den es nie gab — Schwere: mittel-hoch

`journal._slippage_basis` schloss Zeilen ohne echte Marktquote so aus:

```python
fallback = o["referenz_quelle"] == "fallback"
```

Der Wert kommt in den Daten **kein einziges Mal** vor. Die Spalte
entstand erst am 04.08.2026 per `_migrate`; ältere Zeilen tragen `NULL`,
und `NULL != "fallback"`. Der Filter entfernte **null** Zeilen.

| | n | Median | Mittel |
|---|---:|---:|---:|
| wie gerechnet | 162 | +0,0 bps | **−71,7 bps** |
| nur verifizierte Referenz | 131 | +0,0 bps | **−27,4 bps** |

Die 31 Zeilen stammen alle aus 28.07.–04.08. und enthalten genau die
Ausreißer, die §G bereits als Datenfehler führt: KGS −1.648,
SIMO −1.584, TGTX −1.258 bps.

**Der Schluss in `BETRIEBSPLAN` §3.1 bleibt gültig** — der Median ist
beidseitig +0,0, und 131 liegt weit über den geforderten 30. Falsch war
die Grundmenge, nicht das Urteil. Dass es folgenlos blieb, liegt allein
am Median: §G16 Fund 9 hatte die Kostenkontrolle vom Mittelwert auf ihn
umgestellt und damit unwissentlich das Symptom behandelt.

**Behoben:** Positivliste statt Ausschlussliste — gezählt wird nur, was
`referenz_quelle` in {`quote`, `quote_verworfen`} führt. Eine
Ausschlussliste muss jeden schlechten Wert kennen; eine Positivliste nur
die guten, und Neues rutscht nicht automatisch durch. §3.1 nennt jetzt
131 Orders.

### Fund 4: 28,6 % der Sicherung waren Fremddaten — Schwere: hoch

`journal.py` beschreibt seine Aufgabenteilung so: *„SQLite ist die
Auswertungsschicht, JSONL die Sicherung — wäre die Datenbank je
beschädigt, ließe sie sich daraus vollständig rekonstruieren."*

`RAW_DIR` war ein **Modul-Global**. `Journal(pfad)` isolierte die SQLite
sauber — `tests/conftest.py` nutzt das ausdrücklich —, aber `RunLogger`
schrieb die JSONL immer ins Produktivverzeichnis:

| | Dateien | Zeilen |
|---|---:|---:|
| Lauf steht im Journal | 472 | 19.845 |
| **kein Lauf im Journal** | **2.146** | **7.935 (28,6 %)** |
| davon mit Symbol `TEST` | 84 | — |

Eine Rekonstruktion hätte Testtrades als echte eingespielt. **Kein
Werkzeug liest die JSONL je zurück** — die Zusicherung war nie geprüft.

Besonders unangenehm: `scripts/14_journal_bereinigen.py` existiert
**genau deshalb**, weil Symbol `TEST` schon einmal in die
Produktivdatenbank lief. Geräumt wurde damals die Datenbank. Das Leck
blieb offen — und mein eigener Testlauf beim Prüfen legte 17 weitere
Dateien an.

**Behoben:** `Journal.raw_dir` hängt an der Datenbank
(`self.path.parent / "journal_raw"`), kein `mkdir` mehr beim Import.
Neues Werkzeug `scripts/28_rohprotokoll_bereinigen.py` (Trockenlauf als
Vorgabe, **verschiebt statt löscht** — eine Datei ohne Lauf kann auch aus
einem bewusst bereinigten Lauf stammen; 19 der 2.159 waren es
nachweislich). Ausgeführt: 2.159 Dateien nach `journal_raw/fremd/`, die
Sicherung ist jetzt sortenrein (472 Dateien, 472 Läufe, 0 fremd).

### Fund 5: Zwei stumme Spalten in `orders`

Über 183 echte Orders:

| Spalte | Zustand |
|---|---|
| `raw` | 183/183 „gefüllt" — mit dem String `'null'` |
| `status` | 178/183 `pending_new` — der Status **bei Abgabe**, nie der endgültige |

Am Journal war damit nicht ablesbar, ob eine Order ausgeführt wurde. Die
übrigen 5 `status`-Werte tragen deutschen Fließtext aus dem alten
`close_position` (`"AMKR geschlossen"`) — zwei unvereinbare Typen in
einer Spalte.

`raw` ist §G13 Fund 2 in Reinform: *„Eine Null sieht wie eine Messung
aus. Ein `NULL` wäre aufgefallen."*

**Warum es niemand fand:** `check_stumme_felder` bewacht
`decisions.reasons`, `check_lifecycle_felder` den Lebenslauf. Für die
`orders`-Spalten gab es **keinen Wächter**.

**Behoben:** `live.reconcile_fills` schreibt Endstatus **und** die
Broker-Rohzeile nach — beides liegt dort längst vor und wurde nur nicht
gespeichert (`COALESCE`, damit eine Korrektur nie weniger Information
hinterlässt als sie vorfand). `run.order` speichert SQL-`NULL` statt
`'null'`. Neu: `data_integrity.check_stumme_orderspalten` — er fragt
nicht „ist gefüllt?", sondern **„trägt mehr als einen Wert?"**. Er meldet
beide Spalten heute noch; sie klären sich mit dem nächsten Handelstag.

### Fund 6: Der Regelabgleich sah 36 % der Entscheidungen nicht

`audit.check_decisions` filterte auf `action == "buy"`. Nachkäufe sind
**110 von 304** Live-Entscheidungen und die Mehrheit der
Kapitalzuteilung (§G13 Fund 3). `Engine._find_topups` erzwingt für sie
zwei Regeln — `score >= min_score` und `topup_min_gain_pct`, die
Average-Down-Sperre. Geprüft wurde keine.

**Nachgemessen an allen 110 Nachkäufen: null Verstöße.** Die Engine hält
sich daran — es war eine Abdeckungslücke, kein Regelbruch. Genau deshalb
gehört sie geschlossen: Das Modul existiert für den Fall, dass eine Regel
aufhört zu greifen, und eine Regel ohne Abgleich hört unbemerkt auf.

**Behoben:** `buy` und `topup` werden geprüft und **getrennt gezählt** —
damit sichtbar bleibt, wenn eine Aktionsart gar nicht vorkommt (genau der
Fund bei B09). Ein Nachkauf ohne `gewinn_pct` ist selbst ein Befund, kein
stilles Überspringen.

### Fund 7: Eine Sicherung, die es nie gab

`shadow.RAW_DIR` wurde bei **jedem** `ShadowStore()` angelegt und **nie
beschrieben** — seit dem 31.07.2026 leer. Es sah aus wie das Gegenstück
zu `journal_raw`.

Dahinter liegen 26 MB: 20.690 Vorhersagen, die gesamte Flottenmessung,
der Musterspeicher, der Versuchszähler — die Datengrundlage der
Entscheidung vom 10.10.2026, vollständig ungesichert. Nur ein leeres
Verzeichnis, das eine Sicherung vortäuschte.

**Behoben:** `ShadowStore.sichern()` legt eine
transaktionskonsistente Kopie über `sqlite3.Connection.backup()` an
(nicht `shutil.copy` — eine Dateikopie während eines Schreibvorgangs
kann eine halbe Transaktion erwischen, und eine Sicherung, die da ist und
nicht funktioniert, ist schlimmer als keine). Sieben Stände, aufgeräumt
nach Alter. Der Schattendaemon ruft sie **nach** einem Durchgang und
**nur bei tatsächlicher Änderung** — die vier Schritte sind idempotent
(§G14), am Wochenende liefern sie alle 0, und sieben identische Kopien
hätten am Montag jeden Stand von vor dem Wochenende verdrängt. Erste
Sicherung: 26,4 MB, `PRAGMA integrity_check` = ok.

### Fund 8: Der Protokollkopf mischte Simulation und Live

Rest von §G13 Fund 1. `Journal.summary()` meldete:

```
Entscheidungen  :  18425  (183 ausgefuehrt)
Zeitraum        : 2026-07-28 bis 2026-08-21
```

Das las sich wie 1 % Ausführungsquote. 18.118 Zeilen stammen aus vier
Simulationsläufen mit rückdatierten Zeitstempeln bis 2021. §G13 hat
`decision_quality` und `integrity_check` gefiltert — der **Kopf** dieses
Berichts blieb ungefiltert und stand direkt über einem Befund, der
korrekt 62 statt 17.100 meldete, ohne dass der Unterschied erklärbar war.
Der Zeitraum verschärfte es: Er kommt aus `runs.started_at`.

**Behoben:** 304 LIVE (181 ausgeführt), 18.121 aus Simulation getrennt
ausgewiesen, und der Entscheidungszeitraum steht daneben, sobald
Simulationszeilen vorhanden sind.

### Struktur: eine Zusicherung, die zur Laufzeit schwächer ist als ihr Wortlaut

*„Der Schattenbetrieb importiert `trading.py` bewusst nicht — er **kann**
keine Order senden, nicht nur ‚darf nicht'."* Das steht in `CLAUDE.md`,
`README.md` und `BETRIEBSPLAN` §6.

**Am Quelltext stimmt es** — kein Schattenmodul referenziert `trading`.
Geprüft war es an keiner Stelle: dieselbe Lage wie beim RL-Docstring in
§G17.

**Zur Laufzeit trägt der Wortlaut nicht.** `import alpaca_bot.shadow`
führt `__init__.py` aus, und das importiert `trading` mit — nachgemessen,
`alpaca_bot.trading` liegt danach in `sys.modules`. Aus „kann nicht" wird
streng genommen „tut nicht". Der Import allein sendet keine Order, und
`trading` hält zusätzlich `dry_run=True` als Vorgabe und `_check_risk()`
vor jedem Senden — die Trennung ist mehrfach abgesichert. Aber die
stärkere Formulierung trägt nur so weit, wie die Prüfung reicht: bis zum
Quelltext. Das steht jetzt im Docstring der Regel.

**Behoben:** `selfcheck.CHARTER` hat eine 13. Regel („Der Schattenbetrieb
ruft keine Order-Funktion auf"), geprüft über `check_schatten_handelt_nicht`
gegen `shadow.py`, `shadow_eval.py`, `fleet.py`, `patterns.py` — auch
lokale Importe innerhalb von Funktionen.

### Zwei zu schwache Tests, vom Mutationstest entlarvt

Zum dritten Mal in diesem Projekt (nach §G17 zweimal) hat der
Mutationstest eigene Tests widerlegt, die grün waren:

1. **`test_protokoll.test_legacy_zeilen_ausgeschlossen`** wurde durch
   Fund 3 **im Stillen entwertet.** Seine Legacy-Zeile trug kein
   `referenz_quelle`; nach der Verschärfung flog sie aus **zwei** Gründen
   heraus. Der Test blieb grün, auch als die Mutation den Legacy-Filter
   ganz entfernte. Jetzt trägt die Zeile `quote`, und der Legacy-Filter
   ist wieder der einzige Grund.
2. **Meine eigenen Tests der neuen Verfassungsregel** setzten
   `SCHATTEN_MODULE` durchweg per monkeypatch auf eine Attrappe — sie
   prüften den Mechanismus, nie die Voreinstellung. Eine Mutation auf
   `SCHATTEN_MODULE = ()` blieb ungefangen: Die Regel hätte grün
   gemeldet, ohne eine Datei anzusehen. Wieder §G17: *„Ein Test, der nur
   seine eigenen Argumente prüft, prüft die Voreinstellung nicht."*

### Was diese Runde sonst geprüft und für gut befunden hat

* **Keine Importzyklen zwischen den Schichten.** Im Schattenblock gibt es
  welche (`fleet ↔ shadow`, `patterns ↔ shadow`, `shadow ↔ shadow_eval`),
  aufgelöst über lokale Importe.
* **Alle 23 `EngineConfig`-Felder haben Leser** — kein toter Parameter.
* **Alle 32 Skripte starten.** Kein Artefakt ist unbenutzbar geworden.
* `_run_configs`, `decision_quality` und `integrity_check` filtern
  korrekt auf `live_trade` (§G13 hält).
* Die 17.100 unbewerteten Entscheidungen sind weiterhin korrekt auf 62
  gefiltert.
* `Store.record_day_trade` ist weiterhin ungenutzt — bekannt und bewusst
  offen (§G16 Fund 8), nicht erneut aufgeführt.

### Neu dokumentiert: der Messstand der Konfiguration

`EngineConfig.for_reversal()` trägt jetzt eine Tabelle, die je Achse
nennt, **welcher Flottenbot die Alternative geprüft hat und mit welchem
Ergebnis** — und wo kein Eintrag steht, heißt das „ungemessen", nicht
„gut". Sie beantwortet die Frage, die sich sonst in ein paar Generationen
wieder stellt: *Ist das der beste Wert oder nur der erste, den jemand
hingeschrieben hat?*

Dabei sichtbar geworden: **drei Achsen, die die Strategie mittragen,
wurden nie gegengeprüft** — `exit_score`, `trail_after_atr` und
`reenter_cooldown_days`. `exit_score` ist die auffälligste, weil §E ihn
ausdrücklich als den Wert ausweist, der `target_atr` wirkungslos macht.

Regression: `tests/test_abnahmereferenz.py` (11), 
`tests/test_journalherkunft.py` (17), `tests/test_sicherungen_runde5.py`
(19), sechs neue Mutationen — **65 von 65 gefangen**.


## G20. `shadow.py` aufgeteilt — mit Nachweis statt Zusicherung (23.08.2026)

**Anlass:** §G19 hielt fest, dass `shadow.py` fünf Verantwortungen in
2.339 Zeilen trägt, und stellte den Umbau zurück — sechs Wochen vor dem
Entscheidungstermin am 10.10.2026 schien er zu riskant. Auf Nachfrage
geprüft, ob das stimmt. **Es stimmte nicht.** Ein reiner Umzug ist keine
Änderung an der Handelslogik. Riskant ist nicht der Umzug, sondern der
fehlende *Beweis*, dass es einer ist.

### Der eigentliche Strukturfehler

Die Selbstprüfungen des Schattens (~500 Zeilen) lagen **in der Datei,
die sie prüfen**. Dieselbe Aufgabe existiert auf drei Ebenen, und nur
bei einer lag der Prüfer im Geprüften:

| Ebene | Prüfer | Wo |
|---|---|---|
| Live-Handelsregeln | `audit.py` | eigenes Modul |
| Journal | `data_integrity.py` | eigenes Modul |
| Schattenbetrieb | `pruefungen()` | **in `shadow.py`** |

### Die Aufteilung

```
shadow_config.py      70 Zeilen   Einstellungen eines Laufs
shadow_store.py      746 Zeilen   shadow.sqlite und ihr Schema
shadow_daten.py      263 Zeilen   Universum, Bars, Snapshot
shadow_schritte.py   846 Zeilen   die vier Schritte
shadow_pruefung.py   530 Zeilen   die zehn Korrektheitsprüfungen
shadow.py            139 Zeilen   Fassade + Landkarte
```

Abhängigkeiten laufen nur in eine Richtung: `config ← daten ← schritte`,
`store ← schritte, pruefung`.

**`ShadowConfig` bekam ein eigenes Modul, obwohl es nur eine Dataclass
ist.** Nicht aus Ordnungsliebe: `_universum_symbole(cfg: ShadowConfig)`
war die einzige Stelle, an der die Datenschicht auf die Schrittschicht
zeigt. Ohne diese Trennung bliebe genau ein Zyklus übrig — und ein
einziger Zyklus reicht, damit die Schichtung nur noch behauptet ist.

**Die Fassade bleibt.** Zwölf Stellen importieren aus `alpaca_bot.shadow`.
Ein Umzug, der gleichzeitig alle Aufrufer ändert, ist kein reiner Umzug
mehr und damit nicht mehr nachweisbar.

### Der Nachweis: Bytecode, nicht Tests

`scripts/29_umzug_pruefen.py` vergleicht für **jede** verschobene
Funktion das übersetzte Code-Objekt gegen den Stand davor: `co_code`,
`co_consts` (rekursiv, auch verschachtelte Funktionen), `co_names`,
`co_varnames`, Argumentzahlen, Flags.

```
61 von 61 Funktionen bytegleich.
Der Umzug hat nichts am Verhalten geaendert.
```

**Warum die Testsuite als Nachweis nicht reicht.** Sie zeigt, dass die
*geprüften Fälle* weiter stimmen — nicht, dass nichts anderes sich
geändert hat. Genau dieser Unterschied ist die Fehlerklasse, an der
dieses Projekt mehrfach gescheitert ist (§G15). Der Bytecode hängt nicht
von der Auswahl der Testfälle ab.

**`co_names` ist dabei der eigentliche Wachhund:** Ein Modulwechsel
ändert, *woher* ein globaler Name kommt. Ein vergessener Import oder ein
Name, der still auf etwas anderes fällt, steht dort — und sonst nirgends.

Gegenproben: `pruefbericht()` an echten Daten Zeile für Zeile identisch,
Testsuite grün, Selbstprüfung 0 Verstöße, Mutationstest 65/65.

### Der Umzug hat eine Sicherung blind gemacht — gefunden vom Mutationstest

**Der wichtigste Fund dieser Runde, und er kam nicht von einem Test.**

§G19 hatte am selben Tag die Verfassungsregel 9 eingeführt („Der
Schattenbetrieb ruft keine Order-Funktion auf"), mit einer aufgezählten
Modulliste:

```python
SCHATTEN_MODULE = ("shadow.py", "shadow_eval.py", "fleet.py", "patterns.py")
```

Nach dem Umzug lag der bewachte Code in `shadow_schritte.py`. **Die Regel
bewachte ab da die Fassade und meldete weiter grün.** Ebenso
`tests/test_konsistenz.TestSchattenKannNichtHandeln`, das `shadow.py`
fest verdrahtet las.

Gefunden hat das der Mutationslauf: Er baut `from . import trading` in
das echte Modul ein — und niemand schlug an. Die Testsuite war zu diesem
Zeitpunkt vollständig grün.

Das ist §G15 in seiner unangenehmsten Form: **eine Sicherung, die vom
Aufräumen selbst blind gemacht wird.** Und es ist ein Argument gegen
aufgezählte Listen in Prüfungen, nicht gegen das Aufräumen.

**Behoben:** `selfcheck.schatten_module()` sucht per Muster
(`shadow*.py` plus `SCHATTEN_ZUSATZ`) statt aufzuzählen — von vier
bewachten Modulen auf neun. Ein neues Schattenmodul ist automatisch
abgedeckt, ohne dass jemand daran denken muss. `test_konsistenz` nutzt
dieselbe Quelle. Die Mutation bricht jetzt das **Suchmuster**
(`shadow*.py` → `shadow.py`), also genau den Fehler von heute.

### Was der Umzug sonst noch mitnahm

`subprocess` und `Decision` wurden importiert und nirgends benutzt —
Reste aus der Zeit, als `code_version()` den Git-Aufruf selbst machte.
Beim Neuaufbau der Importe fielen sie weg.

### Was der Umzug NICHT geändert hat

Kein Ausdruck, keine Zeile Logik, kein Schema, keine Datenbank. Die
laufende Flottenmessung ist unberührt — sie liegt in `shadow.sqlite`,
und die vier Schritte sind idempotent (§G14), ein Dienstneustart kostet
sie nichts.

Regression: `scripts/29_umzug_pruefen.py` (bleibt als Werkzeug für den
nächsten Umzug), eine geänderte Mutation — **65 von 65 gefangen**.


## G21. Der Intraday-Stop protokollierte keinen Lebenslauf (23.08.2026)

**Anlass:** die Frage „reicht die Basis, um am 10.10.2026 einfach
auszuwerten?". Beim Durchrechnen der vier Kriterien geprüft, was die
Auswertung an diesem Tag sonst noch abfragen würde — und dabei die
Auffälligkeit „58 Ausstiege, 56 Lebenslauf-Einträge" aufgelöst, die seit
der Eingangsprüfung dieser Runde offen stand.

### Der Fund

`daemon._record_lifecycle` hängt am normalen `sell`-Pfad. Der am
15.08.2026 ergänzte **Intraday-Stop** (`live.pruefe_stops_intraday`)
schreibt seinen Ausstieg direkt über `state.record_exit` und ging daran
vorbei.

| Ausstiegsgrund | im Lebenslauf | mittlere Rendite |
|---|---:|---:|
| `zeitausstieg` | 39/39 | +2,5 % |
| `these_traegt_nicht_mehr` | 11/11 | +5,1 % |
| `gewinnziel_erreicht` | 4/4 | +11,1 % |
| `stop_ausgeloest` | 2/2 | −5,5 % |
| **`stop_intraday`** | **0/2** | **−8,3 %** |

**Die Richtung wiegt schwerer als die Größe.** Der Intraday-Stop feuert
per Konstruktion bei scharfen Einbrüchen — er trifft fast nur
Verlusttrades. Folgen im Lernbericht:

* Mittlere Rendite **+3,34 % statt +2,94 %** — systematisch zu gut.
* Als „schlechtester Ausstiegsgrund" wurde `stop_ausgeloest` (−5,5 %)
  genannt. Der tatsächlich schlechteste (`stop_intraday`, −8,3 %) tauchte
  gar nicht erst auf.

Dass es heute nur 0,4 Prozentpunkte sind, liegt allein an n=2. Der Fehler
wächst mit jedem Intraday-Stop und **immer in dieselbe Richtung**.

### Warum der Wächter ihn nicht fand

`check_lifecycle_coverage` verglich nur Gesamtzahlen:

```python
if len(exits) > len(trades) + 1:      # 58 > 56 + 1  ->  Befund
```

Der Befund kam also — und war wertlos. „Zwei fehlende von 58" liest sich
wie Zeitversatz, und die Toleranz `+1` hätte einen einzelnen fehlenden
Eintrag ganz verschluckt. Die Wahrheit stand in der Aufschlüsselung: Ein
Grund mit **0 %** neben vier mit 100 % ist kein Zeitversatz, sondern ein
ausgefallener Schreibpfad. Eine Gesamtzahl kann das nicht zeigen.

### Behoben

* **`lifecycle.eintrag_anlegen()`** — ein Ort für alle Ausstiege. Beide
  Pfade rufen ihn; `daemon._record_lifecycle` delegiert.
* **`lifecycle.handelstage()`** — die Haltedauer-Rechnung ist aus
  `daemon.py` dorthin gewandert, weil `live` sie ebenfalls braucht und
  nicht aus `daemon` importieren darf (`daemon` importiert `live`).
  Nebeneffekt: `record_exit` bekommt jetzt denselben Wert wie der
  Lebenslauf statt `meta["bars_held"]`, das seit jeher auf 0 steht.
* **Der Wächter fragt anders.** Nicht mehr „wie viele fehlen", sondern
  **„fehlt ein Eintrag, der NEUER ist als der jüngste vorhandene?"**

### Ein Fehler in der Korrektur selbst — vom Test gefangen

Beim Einbau habe ich `_handelstage` in `live.py` benutzt, ohne es dort zu
importieren. Die Folge wäre **schlimmer als der ursprüngliche Fehler**
gewesen: Die Zeile steht **vor** `store.record_exit`, der `except`-Block
hätte sie gefangen — und damit hätte der Intraday-Stop verkauft, aber
weder Ausstieg noch Lebenslauf noch `drop_position` protokolliert.

Gefunden hat es der neue Test, der den Pfad mit `dry_run=False`
durchspielt. **Der bestehende `test_ausfuehrung.TestIntradayStop` fuhr
immer mit `dry_run=True`** — der Schreibzweig liegt aber hinter
`if not dry_run`. Es gab also Tests des Intraday-Stops, nur keinen, der
bis zum Schreiben kam. Genau dort saß die Lücke.

### Warum das Kriterium des Wächters zweimal geändert wurde

Der erste Entwurf fragte „fehlt der **jüngste** Ausstieg dieses Grundes?".
Richtig — und nicht abstellbar: Die zwei Zeilen vom 19./20.08. lassen
sich **nicht nachtragen** (`position_meta` wird beim Verkauf gelöscht,
der Einstiegsscore ist damit weg), und der nächste Intraday-Stop kann
Wochen auf sich warten lassen. Der Health-Check stand daraufhin **ROT**,
und `BETRIEBSPLAN` §8 macht aus zweimal ROT „Handel aus".

Eine Warnung, die sich nicht abstellen lässt, wird weggeklickt (§G18
Fund 4). Das tragfähige Kriterium vergleicht deshalb mit dem jüngsten
**vorhandenen** Eintrag: Fehlt etwas Neueres, hat der Lebenslauf seither
geschrieben — nur für diesen Ausstieg nicht, also ein laufender Ausfall.
Liegt alles Fehlende davor, ist es Vergangenheit und wird benannt statt
gemeldet. Kein Datum im Code, keine Ausnahmeliste; die Grenze ergibt sich
aus den Daten und wandert mit.

**Die zwei Zeilen bleiben unrepariert.** Eine erfundene Zeile wäre
schlimmer als eine fehlende (§G13 Fund 2). Der Befund nennt sie beim
Namen, damit niemand sie für vorhanden hält.

### Was das für den 10.10. bedeutet

**Nichts für die Abnahme von B11** — die rechnet auf `shadow.sqlite`, und
der Lebenslauf ist eine Live-Tabelle. Wohl aber für jede Abfrage über
`15_lernbericht.py` oder die Nachbetrachtung: Sie war bis heute
systematisch zu optimistisch.

Regression: `tests/test_lebenslauf_abdeckung.py` (13 Tests), zwei neue
Mutationen — **67 von 67 gefangen**.


## G22. Kriterium 1 rechnet richtig — kann am 10.10. aber kaum etwas zeigen (23.08.2026)

**Anlass:** die Vorgabe, dass die Auswertung am 10.10.2026 „genau das
bewerten und rechnen muss, was wir uns vornehmen". Also den Rechenweg
selbst geprüft, der an diesem Tag das Urteil fällt.

### Teil 1: Der t-Wert ist NICHT aufgebläht — erstmals gemessen

Der Verdacht lag nahe: §G12 hat gezeigt, dass überlappende
Renditefenster den t-Wert um das 1,6-fache aufblähen. `vergleich_gepaart`
rechnet über Tagesdifferenzen `d_t = r_A(t) − r_B(t)`, und die Positionen
beider Depots laufen über mehrere Tage — überlappen sich also.

**Gemessen statt vermutet.** 600 Läufe auf reinem Rauschen, beide Depots
mit **identischer Rangliste** (ein erster Entwurf ließ sie unabhängig
würfeln — dann dominiert unabhängiges Rauschen und die Quote fällt zu
niedrig aus):

| Perzentil von \|t\| | gemessen | t-Verteilung (df=34) |
|---|---:|---:|
| 90 % | 1,71 | 1,69 |
| 95 % | 2,04 | 2,03 |
| 97,5 % | 2,42 | 2,35 |
| 99 % | 2,70 | 2,73 |

Kolmogorow-Smirnow gegen t(34): **p = 0,16**. Mittelwert +0,05
(Soll 0), Standardabweichung 1,04 (Soll 1). Fehlalarmquote bei t > 2:
**6,0 %** gegen nominal 5 %, bei der echten Schwelle 2,85: **0,5 %**.

**Der Unterschied zu §G12 ist strukturell:** Dort teilten benachbarte
Tage ein *Mehrtages-Renditefenster*. Hier ist `d_t` eine
**Eintages-Differenz** — es gibt kein Fenster zu teilen. Die gemessene
Autokorrelation von `d` ist nicht von 0 zu unterscheiden.

**Gegenprobe zur Richtung:** Bei einem künstlich eingebauten Vorsprung
von 15 bps/Tag liegt das mittlere t bei +1,88, das Vorzeichen ist in
94 % positiv. Der Test findet einen echten Effekt und zeigt ihn in die
richtige Richtung.

### Teil 2: Die Annahme, auf der der Zeitplan steht, hält nicht

`vergleich_gepaart` versprach im Docstring:

> *„Die Streuung von d ist typisch 3-5x kleiner als die der
> Einzelrenditen … Praktische Folge: ‚A schlägt B' ist nach 6-10 Wochen
> entscheidbar."*

An den echten Equity-Kurven nachgemessen:

| Paar | Reduktionsfaktor |
|---|---:|
| `B08` gegen `B00` | **3,6×** — wie behauptet |
| `B04` gegen `B00` | 2,4× |
| **`B11` gegen `B09`** | **1,1×** — praktisch keine Reduktion |
| `B07` gegen `B00` | 0,8× — die Differenz streut **stärker** |

**Die Reduktion entsteht durch Überlappung der Depots.** Bots, die sich
nur im Kapitaleinsatz unterscheiden (`B08`), halten fast dieselben
Positionen — dort greift sie. Bots, die **andere Positionen
unterschiedlich lange halten**, haben wenig Überlappung. Genau das ist
`B11`. Und weil der Zeitbedarf **quadratisch** mit der Streuung wächst,
macht 1,1× statt 3,6× aus „6–10 Wochen" schnell Monate.

### Was das für den 10.10. konkret heißt

Bei 31 auswertbaren Tagen ist nachweisbar:

| Streuungsschätzung | ab | kumuliert über 31 Tage |
|---|---:|---:|
| `B11` gegen `B09` (eigene, n=5) | 0,34 %/Tag | **10,5 %** |
| `B04` gegen `B00` (belastbarer, n=18) | 0,18 %/Tag | **5,4 %** |

Der **gesamte** gemessene Vorsprung der Strategie beträgt +0,11 % **je
Trade** (§A) — auf das Depot gerechnet grob 0,02–0,03 %/Tag. `B11`
müsste also **mehrfach so viel beitragen, wie die Strategie insgesamt
verdient**, um am 10.10. bestehen zu können.

**Der wahrscheinlichste Ausgang ist: Kriterium 1 fällt durch.** Das ist
kein Grund, den Vertrag zu ändern — die konservative Vorgabe ist richtig.
Es ist ein Grund, das Ergebnis richtig zu lesen.

### Behoben: die Trennschärfe ist jetzt Teil jeder Auswertung

`shadow_eval.trennschaerfe()` rechnet je Vergleich aus, welcher Effekt
überhaupt nachweisbar wäre:

```
gerade_noch    = schwelle * s / sqrt(n)
mit_80_prozent = (schwelle + 0,84) * s / sqrt(n)
```

Die zweite Zahl ist die ehrlichere: Ein Effekt exakt in Höhe der ersten
wird nur in der **Hälfte** der Fälle auch gefunden.

`kriterien_text` gibt sie **immer** mit aus, samt Warnung. Denn ein
durchgefallenes Kriterium 1 hat zwei völlig verschiedene Ursachen, die
in der bisherigen Ausgabe identisch aussahen:

* Der Bot ist **nicht besser**.
* Der Bot **ist** besser, aber die Datenlage kann es nicht zeigen.

Nur die erste rechtfertigt, eine Idee zu verwerfen. Sonderfall
abgefangen: Bei Streuung 0 (bitgleiche Bots wie `B09`/`B08`, §G16
Fund 1) meldet die Funktion das ausdrücklich — ohne den Hinweis sähe die
Ausgabe wie *perfekte* Trennschärfe aus.

**Vorab festgehalten**, nicht nachträglich: Die Erwartung steht seit dem
23.08.2026 in `BETRIEBSPLAN` §3.3 — sechs Wochen vor dem Termin. Nach dem
Termin wäre dieselbe Rechnung eine Erklärung für ein unerwünschtes
Ergebnis; vorher ist sie eine Vorhersage.

Regression: `tests/test_trennschaerfe.py` (12 Tests), zwei neue
Mutationen.


## G23. Kriterium 1 kann nur Effekte finden, die es nicht geben kann (23.08.2026)

**Anlass:** die Frage nach konkreten Szenarien in Kapital statt in
t-Werten. Beim Umrechnen kam eine Zahl heraus, die den ganzen
Flottenaufbau betrifft.

### Die Strategie in Geld, bei echten Kosten

Depot 109.701 $, 90 % investiert auf 15 Plätze = **6.582 $ je Position**.
Mittlere Haltedauer gemessen **4,45 Handelstage** über 56 Trades.

| | Betrag |
|---|---:|
| Rundläufe pro Jahr | 850 |
| Bruttoertrag (+0,11 % je Trade, §A) | +6.155 $ |
| Kosten (0,142 % Rundlauf, §A) | −7.946 $ |
| **Netto** | **−1.791 $/Jahr = −1,6 %** |

Im Papierdepot fällt nichts davon an — deshalb sieht es dort gut aus.
Um bei echtem Geld auf ±0 zu kommen, müsste der Vorsprung je Trade von
**0,110 % auf 0,142 %** steigen: **+0,032 Prozentpunkte**.

### Die Zahl, um die es geht

Diese Lücke, aufs Depot und auf den Tag umgerechnet:

```
wirtschaftlich entscheidend :  0,0065 %/Tag   (= 1.797 $/Jahr)
```

Und was Kriterium 1 am 10.10. bei 31 Tagen nachweisen könnte (§G22):

| Streuungsschätzung | nachweisbar ab | Faktor |
|---|---:|---:|
| günstige (B04) | 0,180 %/Tag | **28× zu groß** |
| B11s eigene | 0,346 %/Tag | **53× zu groß** |

**Umgekehrt gelesen ist es noch deutlicher.** Ein Bestehen von
Kriterium 1 am 10.10. würde bedeuten:

| Streuungsschätzung | impliziter Mehrertrag |
|---|---:|
| günstige | ~49.900 $/Jahr = **45 % p.a.** gegenüber B09 |
| B11s eigene | ~95.800 $/Jahr = **87 % p.a.** |

**Ein bestandenes Kriterium 1 wäre damit kein Erfolg, sondern ein
Warnsignal.** Eine Strategie mit +0,11 % Vorsprung je Trade kann keine
45 % p.a. Zusatzertrag aus einer geänderten Ausstiegsregel erzeugen. Wer
das misst, hat mit hoher Wahrscheinlichkeit einen Fehlalarm vor sich —
und die Schwelle von 2,95 schützt davor gerade **nicht**, weil sie
Mehrfachtestung abfängt, nicht Unplausibilität.

### Wie lange die Messung bräuchte, um das Relevante zu sehen

```
guenstige Streuung :  23.875 auswertbare Tage  = 118 Jahre
B11s Streuung      :  88.082 auswertbare Tage  = 437 Jahre
```

**Das ist keine Frage der Geduld.** Der gepaarte Vergleich über
Tages-Equity kann nur **große** Effekte finden. Kleine, wirtschaftlich
entscheidende sind für ihn unsichtbar — bei jeder realistischen Laufzeit.

### Was daraus folgt

**Der Fehler liegt nicht im Code.** `vergleich_gepaart` rechnet
nachweislich korrekt (§G22: Verteilung deckt sich mit t(34), p = 0,16).
Der Fehler liegt in der **Wahl der Messgröße**: 31 Tagesdifferenzen mit
0,265 % Rauschen können einen Effekt von 0,0065 % nicht auflösen. Das
Signal-Rausch-Verhältnis beträgt 1:40.

**Was der Vertrag trotzdem leistet.** Kriterien 2, 3 und 4 hängen nicht
am t-Wert:

* **Kriterium 3** ist ein Anteil über ~75 Ausstiege — Standardfehler
  5,3 %, die Bandbreite 10–60 % ist klar trennbar.
* **Kriterium 4** ist eine Vorzeichenfrage über ~22 verlängerte Trades.
* Die **mittlere Haltedauer** ist Arithmetik (B04 zeigt sie heute schon:
  6,11 statt 4,45 Tage).

Diese drei beantworten *„greift die Regel und wie oft"*. Sie beantworten
nicht *„lohnt sie sich"*. Die zweite Frage ist über die Flotte in
vertretbarer Zeit **nicht** beantwortbar.

**Das Instrument mit Trennschärfe existiert bereits:** der Historienlauf.
§G11 hat über **2.149 Zeitausstiege** gemessen, was der Kurs danach tat —
marktbereinigt, nach Ausstiegstag gruppiert, mit klarem Ergebnis (jeder
Punktschätzer negativ). Zweitausend Trades tragen, was einunddreißig
Tagesdifferenzen nicht tragen. Deshalb steht im `BETRIEBSPLAN` §4 „erst
Historienfilter" — dieser Befund beziffert, warum.


## G24. Der Historienlauf testet eine andere Strategie als der Live-Bot (23.08.2026)

**Anlass:** der Einwand, die historischen Testtrades funktionierten nicht
richtig und die echten Ergebnisse würden besser ausfallen. Geprüft statt
diskutiert — **der Einwand trifft zu.**

### Der Fund

Beide Pfade rufen `signals.build_reversal_frame`, aber mit
unterschiedlichen Argumenten:

```
simulate.py:191   build_reversal_frame(df, market, ecfg.reversal_weights)
shadow_daten.py   build_reversal_frame(df, market, cfg.reversal_weights,
                                       symbol=s, news=news)
```

`ReversalWeights.news = 0.10` ist ein **additiver Score-Baustein**
(`signals.py:320`). Fehlt `news`, ist `f_news = 0` — der Faktor entfällt
ersatzlos. Der Historienlauf rechnet also **ohne** ihn, Schatten und
Live-Bot rechnen **mit** ihm.

### Gemessen, nicht hergeleitet

Acht Symbole, dieselben Bars, dieselben Gewichte, echte Nachrichtendaten:

| Symbol | `simulate.py` | Schatten/Live | Differenz |
|---|---:|---:|---:|
| WMT | 0,8666 | 0,9666 | **+0,1000** |
| TJX | 0,7235 | 0,8235 | +0,1000 |
| TTMI | 0,6988 | 0,7988 | +0,1000 |
| FN | 0,5955 | 0,6955 | +0,1000 |
| BABA | 0,7354 | 0,7913 | +0,0559 |
| VICR | 0,6182 | 0,6332 | +0,0150 |
| CW | 0,9455 | 0,9455 | 0 |
| AGX | 0,6539 | 0,6539 | 0 |

**Sechs von acht bekommen einen anderen Score.** Und die Rangfolge kippt:

```
simulate.py :  CW   WMT  BABA  TJX  TTMI  AGX  VICR  FN
shadow/live :  WMT  CW   TJX   TTMI BABA  FN   AGX   VICR
```

Der Bot kauft die obersten Plätze. Eine andere Reihenfolge heißt **andere
Aktien im Depot**.

Über den gesamten Schattenbestand (2.117 Vorhersagen `B00`):

* **19,7 %** tragen einen Nachrichtenbeitrag > 0, im Mittel **+0,054**
* **65 Kandidaten (3,07 %)** überschreiten `min_score = 0,35`
  **ausschließlich** wegen der Nachrichten
* **46 %** der als `wuerde_gehandelt` markierten Kandidaten haben einen
  Nachrichtenbeitrag

### Was daraus folgt — und was ausdrücklich nicht

**Der Historienlauf ist kein sauberer Test der laufenden Strategie.** Die
Zahlen aus §G11 (−22,4 % über 2021–2025, +7,57 % über sechs Jahre,
Vorsprung je Trade −0,016 %) messen die **Vier-Faktor-Fassung ohne
Nachrichten**. Live läuft eine Fünf-Faktor-Fassung.

**Das heißt NICHT, dass die Ergebnisse besser werden.** Der
Nachrichtenfaktor ist der einzige Baustein ohne eigene Messung — seine
eigene Dokumentation sagt es deutlich:

> *„Für diesen Faktor gibt es KEINE eigene Messung … Er wurde auf
> ausdrücklichen Wunsch am 03.08.2026 direkt in beide Bots eingebaut,
> OHNE vorherige Schattenbetrieb-Messung … Fällt die Auswertung negativ
> aus, gehört dieser Faktor wieder auf 0."*

Er kann helfen oder schaden. Bekannt ist nur, dass er **wirkt** — und das
ist jetzt beziffert.

**Nachrüsten geht nicht.** Der Alpaca-Nachrichtenfeed reicht nicht bis
2021 zurück. Die Historie lässt sich also nicht mit Nachrichten
nachrechnen; die beiden Fassungen bleiben getrennt vergleichbar.

**Die vier Kernbausteine sind identisch** (Gewicht 1,00 von 1,10). Der
Unterschied betrifft ~9 % des Scores — genug, um die Rangfolge zu drehen,
zu wenig, um aus −22 % ein Plus zu machen.

### Warum es niemand gefunden hat

`shadow.pruefungen()` Nr. 6 heißt „Replay gegen simulate.py" und
verspricht im Docstring: *„Erzeugt der Schattencode dieselben
Entscheidungen wie simulate.py? Weichen sie ab, ist einer von beiden
falsch."*

Die Umsetzung prüfte das **nicht**. Sie startete `simulate.run()`, zählte
die Trades und meldete `True`, sofern nichts abstürzte — ein
Durchlauftest, als Vergleich beschriftet. Genau die Fehlerklasse aus §G17
und §G19: eine Zusicherung, die niemand nachgerechnet hat.

Erschwerend: Der Bericht meldete sie durchgehend als
*„übersprungen (--replay zum Ausführen)"* — sie lief also nicht einmal
in ihrer schwachen Fassung.

**Behoben:** Die Prüfung vergleicht jetzt die **Scores** beider Pfade auf
denselben Bars und meldet Abweichungen mit Symbol und Betrag.

### Einordnung für die Planung

Die Zahlen aus §G23 (Kostenlast, Szenarien) bleiben gültig — sie hängen
am Umschlag und am Spread, nicht am Score. Was sich ändert, ist die
Belastbarkeit der **Renditeschätzung**: Die historischen Jahreszahlen
gelten für die Vier-Faktor-Fassung. Für die live laufende Fassung gibt es
**keine Mehrjahresmessung** — nur 19 Handelstage Papierbetrieb.


## G25. Die Lernschleife ist offen — und nur ein Kanal hat Trennschärfe (23.08.2026)

**Anlass:** die Frage, ob Speichern und Auswerten so funktionieren wie
gedacht und ob sich der Bot auf lange Sicht verbessert. Erstmals nicht
nach Einzelfehlern gesucht, sondern nach dem **Kreislauf als Ganzem**.

### Die Speicherschicht ist in Ordnung

Derselbe Vorgang über vier Datenbanken verfolgt:

| | Anzahl |
|---|---:|
| Verkäufe im Journal (`executed=1`) | 61 |
| Ausstiege in `state.exits` | 58 |
| Einträge im Lebenslauf | 56 |
| Käufe/Nachkäufe `executed=1` gegen echte Kauf-Orders | **122 = 122** |

Abgleich nach Symbol und Tag: Journal → `state.exits` weicht in **einer**
Position ab (AMKR 28.07., der bekannte Legacy-Fall mit drei Wiederholungen
am selben Tag), `state.exits` → Lebenslauf in **zwei** (die
`stop_intraday`-Zeilen aus §G21, ab jetzt geschlossen). Keine
verschwundenen Vorgänge, keine erfundenen.

**Speichern funktioniert.** Die Sorge ist an dieser Stelle unbegründet.

### Der Kreislauf ist es nicht

Geprüft, ob der Handelspfad **irgendein** gelerntes Artefakt liest:

```
grep patterns|lernkern|hypotheses|muster
  in live.py, engine.py, daemon.py, signals.py   ->  0 Treffer
```

Und die Bilanz der vier Lernkanäle:

| Kanal | Bestand | in die Handelslogik gelangt |
|---|---|---|
| Musterspeicher | 0 Zeilen | 0 |
| Hypothesen | 3, **alle widerlegt** | 0 |
| Lernkern | 3 Modelle, **alle verworfen** | 0 |
| Flotte | 13 Bots, **0 bestanden** | 0 |

**In der gesamten Projektlaufzeit hat keine einzige Messung die
Handelslogik verändert.**

Das ist zunächst **Absicht** und richtig so — `lernen()` schreibt es
selbst hin: *„Was er ausdrücklich NICHT tut: Er ändert keine Handelsregel.
Ein bestätigtes Muster ist eine Beobachtung mit Beleg und Verfallsdatum,
kein Signal."* Ein System, das sich selbst umschreibt, wäre gefährlicher
als eines, das stillsteht.

**Die eine Änderung, die je durchkam, kam am Apparat vorbei.** Der
Nachrichtenfaktor (`ReversalWeights.news = 0.10`, Commit `3c5dcd3`) wurde
laut eigener Dokumentation *„auf ausdrücklichen Wunsch direkt in beide
Bots eingebaut, OHNE vorherige Schattenbetrieb-Messung"*. Der einzige
Baustein ohne Messung ist der einzige, der es in die laufende Logik
geschafft hat — und §G24 zeigt, dass er die Rangfolge dreht.

### Warum der Kreislauf nicht schließt

§G23 hat es beziffert: Der Flottenvergleich über Tages-Equity kann nur
Effekte ab 0,18–0,35 %/Tag finden. Wirtschaftlich entscheidend sind
0,0065 %/Tag. Der Kanal, über den eine Idee laut CLAUDE.md in die
Handelslogik gelangen soll, ist **28- bis 53-mal zu grob**.

Damit ist die Schleife nicht nur offen, sondern strukturell blockiert.

### Aber ein Kanal hat Trennschärfe — der IC

Der Unterschied ist die **Zähleinheit**. Der Flottenvergleich mittelt
31 Tagesdifferenzen. Der IC mittelt über **Tausende Vorhersagen je Tag**:

| Handelstage | IC nachweisbar ab (t > 2, überlappungskorrigiert) |
|---:|---:|
| 13 (heute) | +0,136 — kein t-Wert berechenbar |
| 31 | +0,081 |
| **53 (10.10.)** | **+0,063** |
| 100 | +0,048 |
| 250 | +0,031 |

**Gemessen: IC +0,0696 über 13 Tage.** Am 10.10. liegt die Nachweisgrenze
bei +0,063 — der gemessene Wert liegt knapp darüber.

> **Korrigiert am selben Tag durch §G26.** Diese Rechnung nutzt `t > 2`.
> Gemessen liefert diese Schwelle aber 11 % Fehlalarm statt 5 %; ehrlich
> kalibriert sind es **2,57**, und damit steigt die Nachweisgrenze auf
> **+0,081**. Der gemessene IC liegt dann **darunter**. Die Aussage
> „wird am 10.10. erstmals entscheidbar" war zu optimistisch.

Damit wird am 10.10. erstmals die Frage entscheidbar, für die der
Schattenbetrieb überhaupt gebaut wurde (`shadow.py`-Docstring): **„Sortiert
unsere Rangliste richtig?"**

**Zwei Warnungen dazu.** Erstens ist IC +0,070 gegenüber dem besten je
gemessenen Einzelfaktor (0,018 über 9 Jahre, §A) **verdächtig hoch** —
dieselbe Unplausibilitätsprüfung wie in §G23. Zweitens ist der Wert aus
13 Tagen; die Streuung des Tages-IC beträgt 0,173, also das
Zweieinhalbfache des Mittelwerts.

### Was daraus folgt

Der Messapparat ist nicht kaputt — er ist **an der falschen Stelle
angeschlossen**. Er hat Trennschärfe dort, wo er Vorhersagen zählt, und
keine dort, wo er Depots vergleicht.

| Frage | Kanal | Trennschärfe |
|---|---|---|
| Sortiert die Rangliste? | IC über Vorhersagen | **ja, ab ~53 Tagen** |
| Ist Ausstiegsregel A besser als B? | Equity-Vergleich | **nein, nie** |
| Trägt ein Faktor? | Historienlauf, 2.149 Ausstiege | ja (aber §G24) |

Wer den Bot verbessern will, muss Fragen stellen, die der IC beantworten
kann — also Fragen an die **Auswahl**, nicht an die **Ausstiegsmechanik**.


## G26. Der IC-Kanal geprüft — Richtung stimmt, Schwelle ist zu mild (23.08.2026)

**Anlass:** §G25 hat den IC zum einzigen Kanal mit Trennschärfe erklärt
und damit zum entscheidenden Instrument für den 10.10. Er war aber nie so
geprüft worden wie Kriterium 1 in §G22 — eine Lücke genau an der Stelle,
die zählt.

### Der Aufbau

600 Läufe unter der Null: 130 Symbole, 53 Handelstage, Score **ohne jede**
Vorhersagekraft. Entscheidend sind zwei Details, die den Unterschied
zwischen einem gültigen und einem wertlosen Test ausmachen:

* **`fwd_5d` echt überlappend gebildet** — Tag t und t+1 teilen vier
  ihrer fünf Renditetage. Das ist die Falle aus §G12.
* **Der Score ist persistent, nicht täglich neu gewürfelt.** Ein erster
  Entwurf zog jeden Tag unabhängig; dann ist der Tages-IC gar nicht
  autokorreliert, die Falle entsteht nicht, und der Test misst das
  Falsche. Er meldete brave 6 % — ein Scheinergebnis.

**Die Persistenz wurde gemessen, nicht geschätzt.** Tag-zu-Tag-Rang-
korrelation der echten Schatten-Scores: **Median 0,49** (Bereich
0,09–0,66, 18 Tagespaare). Symbolüberlappung von Tag zu Tag: 33 %. Ein
zweiter Entwurf mit angenommenen 0,80 überzeichnete die Fehlalarmquote
deutlich — die Zahlen unten stehen für den gemessenen Wert.

### Was herauskam

| Schwelle | roher t | korrigierter t | Soll |
|---:|---:|---:|---:|
| 2,00 | 18,7 % | **11,0 %** | 5,0 % |
| 2,85 | 6,3 % | **2,2 %** | 0,8 % |

**Die Überlappungskorrektur wirkt** — sie halbiert die Fehlalarmquote
(18,7 → 11,0 %). Das bestätigt §G12 aus einer unabhängigen Richtung.

**Sie reicht nicht.** 11 % gegen 5 % ist mehr als das Doppelte. §G12 hat
genau das schon benannt („für die korrigierte Statistik 11 % … ehrliche
Restunschärfe") — diese Messung bestätigt die Zahl auf den Punkt.

Kalibriert, also die Schwellen, die **wirklich** liefern, was sie
versprechen:

```
für  5,0 % Fehlalarm nötig:  |t| > 2,57   (nominal 2,00)
für  0,8 % Fehlalarm nötig:  |t| > 3,43   (nominal 2,85)
```

### Die Richtung stimmt einwandfrei

Mit echtem Signal im Score:

| Signalstärke | IC | mittleres t | Vorzeichen positiv | über 2,85 |
|---|---:|---:|---:|---:|
| 0,02 | +0,169 | +7,98 | 100 % | 100 % |
| 0,05 | +0,377 | +13,46 | 100 % | 100 % |

Der Test findet, was da ist, und zeigt es in die richtige Richtung. **Der
Rechenweg ist nicht defekt** — er ist nur milder, als seine Schwelle
behauptet.

### Was das für den 10.10. ändert

§G25 hat die Nachweisgrenze mit `t > 2` gerechnet: IC ab **+0,063** bei
53 Tagen, gegen einen gemessenen IC von **+0,0696** — knapp darüber, also
gerade noch entscheidbar.

Mit der kalibrierten Schwelle 2,57 statt 2,00 verschiebt sich das:

| | Nachweisgrenze | gemessener IC |
|---|---:|---:|
| §G25 (nominal `t > 2`) | +0,063 | +0,070 ✓ knapp darüber |
| **kalibriert (`t > 2,57`)** | **+0,081** | +0,070 ✗ **darunter** |

**Auch der IC-Kanal ist am 10.10. damit wahrscheinlich nicht
entscheidbar.** Die Aussage aus §G25 („wird erstmals entscheidbar") war
zu optimistisch und wird hiermit korrigiert.

Bei 100 Handelstagen läge die kalibrierte Grenze bei +0,062, bei 250 bei
+0,040 — der IC bleibt der Kanal mit der besten Trennschärfe, nur braucht
er mehr Zeit als §G25 angenommen hat.

### Was NICHT geändert wurde

`fleet.schwelle_sigma()` bleibt unverändert. Sie erfüllt einen anderen
Zweck — sie fängt die **Mehrfachtestung** ab (§B2), nicht die
Überlappungs-Restunschärfe. Beide Effekte multiplizieren sich; eine
Schwelle, die beides zugleich abdecken soll, verwischt die Begründung.
Wer den IC zitiert, findet die kalibrierte Grenze hier.


## G27. Das Spiegelbuch vergaß, warum es gekauft hat (24.08.2026)

**Anlass:** die Frage, ob der Bot eine schwache Position gegen einen
besseren Kandidaten tauschen sollte. Um sie zu beantworten, braucht man
den Score der gehaltenen Position. Er war nicht da.

### Der Fund

`shadow_portfolio`, 130 Zeilen:

| Spalte | gefüllt | eindeutige Werte |
|---|---:|---:|
| `entry_score` | **0 / 130** | 0 |
| `reasons` | 130 / 130 | **1** — immer `{}` |

**Die Ursache.** `shadow_schritte._spiegel` ruft `depot_speichern` an drei
Stellen. Nur der **Kauf** gibt `entry_score` und `reasons` mit. Der
**tägliche Übertrag** der gehaltenen Positionen liest sie aus einem
`meta`-Dictionary — und das wird **einmal vor der Tagesschleife** geladen:

```python
for sym, m in store.depot_positionen(bot.bot_id).items():
    meta[sym] = m          # <- einmal, vor der Schleife
...
    store.depot_speichern(bot.bot_id, pos,
                          entry_score=(meta.get(sym) or {}).get("entry_score"))
```

Ein im selben Lauf gekaufter Wert steht dort nicht. Also kam `None` an
und überschrieb per `INSERT OR REPLACE` den korrekten Wert vom Vortag.
`reasons` wurde am Übertrag gar nicht erst übergeben — und
`_json(reasons or {})` machte daraus zuverlässig `{}`.

Jede Position wird mindestens einmal übertragen. **Also verlor jede ihre
Begründung, lückenlos.**

### Warum es so lange unbemerkt blieb

Beide Spalten sahen gefüllt aus. `reasons` zu 100 %, mit einem Wert, der
wie Inhalt aussieht. Dieselbe Fehlerklasse wie `orders.raw` (§G19
Fund 5) — nur eine Datenbank weiter. Der Stummheitswächter aus §G19 deckt
`decisions.reasons` und `orders` ab, nicht `shadow_portfolio`.

### Was dadurch unbeantwortbar war

Genau die Frage, für die das Spiegelbuch existiert:

> **„War die gehaltene Position schwächer als der beste verworfene
> Kandidat?"**

Man sah, WAS gehalten wurde, aber nicht, mit welcher Begründung — und
konnte es deshalb mit nichts vergleichen. Das Ranglisten-Buch zeichnet
jeden verworfenen Kandidaten samt Score auf; die Gegenseite fehlte.

### Behoben

`depot_speichern` nutzt `ON CONFLICT ... DO UPDATE` statt
`INSERT OR REPLACE`, mit `COALESCE` auf beiden Feldern: Ein `None` lässt
den bestehenden Wert stehen, statt ihn zu löschen. `reasons` wird als
`None` statt `{}` übergeben, damit `COALESCE` greifen kann — ein leeres
Dictionary wäre ein **Wert** und würde weiter überschreiben.

Kurswerte (`qty`, `bars_held`, `high_water`, Stop, Ziel) werden weiterhin
**immer** fortgeschrieben. Geschützt sind nur die beiden Felder, die den
Einstieg beschreiben und sich nie ändern.

**Neu: Prüfung 11 „Einstiegsgründe im Spiegelbuch"** in
`shadow.pruefungen()`. Sie prüft die Füllquote, nicht die Variation —
anders als bei `orders.status` ist hier ein konstanter Wert nicht das
Problem, sondern ein leerer.

**Die Altdaten bleiben leer.** Nachtragen ginge nur aus den
`predictions`, und deren Zuordnung zur Position ist nach einem Nachkauf
mehrdeutig. Eine rekonstruierte Zahl wäre schlechter als eine fehlende
(§G13 Fund 2). Ab dem nächsten Kauf füllt sich die Spalte von selbst.

### Zur ursprünglichen Frage: lohnt sich Tauschen?

Die Messung ist damit **noch nicht möglich**, aber der Rahmen steht.
Was heute schon feststeht:

* **Die Gelegenheit ist real und groß.** `Engine._find_entries` bricht
  bei vollem Depot sofort ab (`if slots <= 0: return []`) — es werden gar
  keine Kandidaten mehr bewertet. Im Schatten liegen täglich **53 bis 232**
  Kandidaten über `min_score`, gekauft werden 3.
* **Die nötige Score-Differenz wäre klein.** Aus der Dezilrechnung: pro
  0,10 Score-Punkte rund +0,94 % auf 5 Tage. Ein zusätzlicher Rundlauf
  kostet 0,142 %. Rechnerisch trüge sich ein Tausch ab **0,015**
  Score-Differenz — der Anreiz wäre fast immer gegeben.
* **Und genau das ist die Falle.** Die Dezilspreizung stammt aus 1.269
  Vorhersagen über **13 Handelstage**. Nach §B1 gruppiert: mittlere
  Spreizung +1,51 Prozentpunkte, **t = 1,52 naiv**, überlappungskorrigiert
  nicht einmal berechenbar. Vier der 13 Tage sind negativ (−5,33 bis
  +9,62). Der mittlere Fünf-Tages-Ertrag aller Zeilen liegt bei +3,17 % —
  das Fenster war stark positiv, die Spreizung also zu einem großen Teil
  Marktbewegung.

**Solange der IC nicht belastbar ist (§G26: nachweisbar ab +0,081,
gemessen +0,070), ist Tauschen eine Wette auf eine unbestätigte
Rangliste — bezahlt mit sicheren Zusatzkosten.**

Der richtige Weg steht in `BETRIEBSPLAN` §4: erst Historienfilter
(`scripts/10_simulate.py`, kostet keinen Versuchszähler und darf
verwerfen), und dort hat die Frage echte Trennschärfe — 2.149 Ausstiege
statt 13 Tage.


## G28. Die Tauschregel gemessen — sie verkauft Gewinner (24.08.2026)

**Anlass:** die Idee, bei vollem Depot die schwächste laufende Position
vorzeitig gegen einen deutlich besser bewerteten Kandidaten zu tauschen.
Gemessen im Historienlauf (`scripts/31_tauschregel.py`), weil der keinen
Versuchszähler kostet und Trennschärfe hat (BETRIEBSPLAN §4).

### Das Ergebnis

7 Jahre, 1.200 Symbole, 1.757 Handelstage:

| Variante | Rendite | p. a. | max DD | Tausche |
|---|---:|---:|---:|---:|
| ohne Tausch | +19,8 % | +2,62 % | −29,2 % | 0 |
| Tausch ab 0,10 | +30,8 % | +3,92 % | −32,0 % | 1.200 |
| Tausch ab 0,30 | +33,1 % | +4,19 % | −31,6 % | 1.188 |
| Tausch ab 0,60 | +19,1 % | +2,54 % | −32,3 % | 920 |

Gepaart gegen den Grundlauf: **t = +0,72 / +0,85 / +0,02.**

**Kein Befund** — aus vier unabhängigen Gründen:

1. **Kein t-Wert kommt in die Nähe der Schwelle** (2,85).
2. **Das Vorzeichen ist nicht stabil.** Über 5 Jahre und 400 Symbole
   waren dieselben Regeln **negativ** (t = −0,50 bis −0,86). Ein Effekt,
   der bei einem anderen Ausschnitt das Vorzeichen wechselt, ist Rauschen.
3. **+1,3 pp p. a. liegen unter der Survivorship-Korrektur** (2–4 pp,
   §G11). Das Skript sagt es selbst: „Ein Plus unterhalb dieser Größe ist
   kein Befund."
4. **Drei Schwellen sind drei Versuche** (§B2). Der beste von drei
   Rauschzügen liegt erwartungsgemäß bei t ≈ 0,9.

Auch der Drawdown ist unstabil: über 7 Jahre schlechter (−32,0 gegen
−29,2 %), über 5 Jahre besser.

### Der interessante Teil: WARUM es nicht wirkt

| | |
|---|---:|
| Stand der getauschten Position | Median **+1,58 %**, Mittel +2,05 % |
| **davon im Gewinn** | **80 %** |
| Haltedauer bis zum Tausch | Median 3 Tage |
| mittlere Score-Differenz | 0,60–0,78 |

**Die Regel verkauft überwiegend Gewinner** — das Gegenteil ihrer
Absicht.

Der Grund ist strukturell und war vorher niemandem klar: Der
Umkehr-Score misst **„wie überverkauft"**. Eine Position, die sich seit
dem Einstieg erholt hat, ist per Definition nicht mehr überverkauft —
ihr Score fällt Richtung null. **Die „schwächste" Position im Depot ist
damit fast immer die, die am besten gelaufen ist.**

Deshalb bindet auch die Schwelle kaum: Die Differenz beträgt im Mittel
0,60–0,78, weil der gehaltene Wert bei ~0 steht. Zwischen 0,10 und 0,30
liegt praktisch kein Unterschied (1.200 gegen 1.188 Tausche).

### Vier Kriterien geprüft — alle negativ

Nach dem Befund oben wurde das Auswahlkriterium austauschbar gemacht und
mit drei Alternativen gemessen (5 Jahre, 400 Symbole, 1.253 Handelstage,
Kandidatenschwelle 0,60):

| Kriterium für „schwächste Position" | wählt Gewinner | Mittel %/Tag | t | Rendite p. a. |
|---|---:|---:|---:|---:|
| *Grundlauf ohne Tausch* | — | — | — | **+10,98 %** |
| `score` — niedrigster Umkehr-Score | **80 %** | −0,0045 | −0,50 | +9,51 % |
| `gewinn` — schlechtester Stand | 1 % | −0,0085 | −1,13 | — |
| `rueckstand` — weiteste ATR unter dem Höchststand | 2 % | −0,0044 | −0,56 | +9,61 % |
| `stagnation` — geringster Fortschritt je Tag | 1 % | −0,0117 | −1,53 | +7,71 % |

**Alle vier sind negativ.** Kein einzelnes Ergebnis ist signifikant, aber
das Vorzeichen ist über vier völlig verschiedene Operationalisierungen
hinweg stabil — einschließlich zweier, die exakt das Gegenteil auswählen
(80 % Gewinner gegen 1 %).

Das ist die aussagekräftigere Form: Bei Mehrfachtestung (§B2) ist die
Gefahr, den besten von vier Rauschzügen für einen Befund zu halten. Hier
ist **auch der beste negativ**.

**Und der Drawdown steigt durchweg:** −9,7 % im Grundlauf gegen −12,1 %
bis −14,7 % in allen Tauschvarianten. Mehr Umschlag, mehr Risiko.

**Die Erklärung ist arithmetisch, nicht strategisch.** Jeder Tausch
kostet einen zusätzlichen Rundlauf (0,142 %, §A). Der eintauschende
Kandidat müsste diesen Betrag verlässlich einspielen — und der IC ist
dafür zu klein und zu unsicher (§G26: nachweisbar ab +0,081, gemessen
+0,070). Solange die Rangliste nicht belastbar sortiert, ist jeder
zusätzliche Umschlag eine sichere Kosten- gegen eine unsichere
Ertragsposition.

### Was daraus folgt

**Die Idee ist nicht widerlegt, sondern falsch operationalisiert.** „Die
schwächste Position" über den Einstiegs-Score zu definieren, misst nicht
Schwäche, sondern Erfolg. Wer die Idee weiterverfolgen will, braucht ein
anderes Maß für „diese Position trägt nicht mehr" — etwa:

* Rückstand gegenüber dem eigenen Höchststand (das prüft `B11` bereits),
* Zeit ohne Fortschritt statt Score-Niveau,
* oder den Score-**Verlauf** statt des Score-Standes.

Der bestehende `exit_score`-Mechanismus tut bereits etwas Ähnliches — und
gehört zu den drei Achsen, die **nie gegengeprüft** wurden (§G19
Messstand).

### Zwei eigene Fehler beim Bau, beide gefunden

1. **Der erste Haken feuerte in 7 Jahren 40-mal.** Er sprang nur an, wenn
   die Engine gar nichts kaufte. Gemessen ist das Depot an **55 %** der
   Tage voll, die Engine kauft aber an **83 %** — `_find_entries` zieht
   `being_sold` ab, ein Ausstieg macht im selben Durchgang einen Platz
   frei. **„Voll" heißt nicht „kauft nicht".** Aufgefallen daran, dass
   alle drei Schwellen bitgleiche Ergebnisse lieferten.
2. **Ohne `gewinn_pct` im Protokoll** wäre der eigentliche Befund
   unsichtbar geblieben. Die Renditezahlen allein hätten „kein Effekt"
   gesagt, nicht „die Regel schneidet Gewinner ab".

### Was am Handelsbot geändert wurde

**Nichts.** `simulate.run` hat einen optionalen Haken
`nach_entscheidung` bekommen, der `Engine.decide()` unberührt lässt; ohne
ihn ist das Ergebnis bitgleich wie zuvor. Der Grund für einen Haken statt
eines Schleifen-Nachbaus steht in §G11 Fund 1 — dort fuhr ein Nachbau
unbemerkt eine andere Strategie als der Live-Bot.


## G29. Ein Drittel des Tagesverlusts war ein Datenfehler (24.08.2026)

**Anlass:** die Frage, woran der Rückgang der letzten Tage liegt.
Nachgerechnet — und ein Teil davon hat gar nicht stattgefunden.

### Der Fund

Das Depot meldete am 24.08.2026 **−2,07 %**. Aufgeschlüsselt:

| Position | Broker-Kurs | letzter echter Trade | Abweichung | Unterschied im Depotwert |
|---|---:|---:|---:|---:|
| **DKS** | 150,50 | 179,64 | **−16,2 %** | **+1.748 $** |
| KEYS | 316,99 | 310,66 | +2,0 % | −31 $ |
| JBLU | 5,05 | 4,96 | +1,8 % | −158 $ |
| übrige 11 | | | < 2 % | zusammen −216 $ |
| | | | **Summe** | **+1.343 $** |

Die zugehörige Quote war sichtbar kaputt: **Bid 171,49 / Ask 187,15**,
Spanne 15,66 $ = 9 % des Kurses. `snapshots` und die Tagesbar sagen beide
179,64.

| | |
|---|---:|
| Kontowert gemeldet | 106.072 $ |
| mit echten Kursen | **107.415 $** |
| Tagesveränderung gemeldet | **−2,07 %** |
| Tagesveränderung bereinigt | **−0,83 %** |
| SPY am selben Tag | −0,28 % |

**Rund 1,2 der 2,07 Prozentpunkte sind keine Kursbewegung, sondern ein
Preisfehler.** Der reale Rückstand gegenüber dem Markt beträgt an diesem
Tag etwa 0,55 Prozentpunkte.

### Wie der Fehler zustande kommt — nachgemessen

Die rohen Positionsdaten von Alpaca zeigen die Rechnung:

```
lastday_price     179,33     <- korrekt (Vortagesschluss)
change_today       -0,17013  <- FALSCH
current_price     148,82     = 179,33 x (1 - 0,17013)
```

Alpaca markiert die Position also mit `Vortagesschluss × (1 + Tagesänderung)`.
Der Vortageskurs stimmt; **die Tagesänderung von −17,01 % ist der Fehler.**
Die tatsächliche Bewegung beträgt +0,2 % (179,33 → 179,64).

Gegengeprüft an **219 Minutenbars** des Tages: DKS lief durchgehend
zwischen **175,87 und 185,21**. Ein Kurs um 150 kam **kein einziges Mal**
vor. Der Positionspreis wanderte während der Prüfung außerdem von 150,50
über 148,84 auf 148,82 — er folgt also gar keinem realen Kurs.

**Die Ursache ist bekannt und dokumentiert.** Das Konto läuft auf
`Feed=iex`, und dieser Feed sieht nur **~2 % des US-Handelsvolumens**
(`live._quote_plausibel`). Genau das war schon die Ursache der Ausreißer
vom 04.08.2026 (SIMO 225 statt 261, KGS 50,67 statt 59,02). Ein einzelner
fehlerhafter oder ungewöhnlicher Druck auf IEX genügt, damit
`change_today` danebenliegt — und über die Multiplikation schlägt das
voll auf den Positionswert durch.

**Neu ist nur, wo es auftaucht.** Bisher betraf es die *Quote* im
Handelspfad, und dagegen steht seit dem 04.08. `_quote_plausibel`. Hier
betrifft es das *Position Marking* des Brokers — ein Feld, das der Bot
nicht selbst berechnet und deshalb auch nicht plausibilisieren konnte.

### Warum das mehr ist als ein Schönheitsfehler

`risiko._kennzahlen` rechnet auf `konto["equity"]`, `positionswert()` auf
`market_value` — beide kommen vom Broker und tragen den falschen Kurs
weiter. Der ausgewiesene **Drawdown war um 1,2 Prozentpunkte zu groß**.
Genau diese Zahl entscheidet bei 20 % über die automatische Vollsperre
(BETRIEBSPLAN §6).

Bei einer Position von 9.000 $ auf 106.000 $ Konto sind 1,2 pp verkraftbar.
Bei einer größeren Position, oder wenn mehrere Kurse gleichzeitig
danebenliegen, entscheidet ein Datenfehler über die Stilllegung des
Handels.

### Der Handelspfad war NICHT betroffen

`live._quote_plausibel` prüft jede Quote gegen den letzten echten Trade
(§G: SIMO/KGS, 04.08.2026) und hat hier korrekt gegriffen: Die Abweichung
von 4,5 % lag über der 2-%-Schwelle, die Quote wurde verworfen, und der
Intraday-Stop rechnete mit 179,64 statt 150,50. **Stop 166,67 — es wurde
nicht verkauft.**

Ohne diesen Schutz hätte ein Datenfehler eine gesunde Position mit
−16 % ausgestoppt. Der Schutz existiert seit dem 04.08.2026 und hat heute
zum ersten Mal nachweisbar einen echten Verlust verhindert.

### Der falsche Kurs kam bis in den Zustand des Bots

`live.build_portfolio` bekommt die Momentaufnahme übergeben und
**benutzte sie nie** — es las `row["current_price"]`, also genau das
fehlerhafte Feld. Zwei Wege führten von dort weiter:

```python
current    = float(row.get("current_price") or entry)
high_water = max(current, float(meta["high_water"]))
```

**`high_water` ist ein `max()`.** Ein einmal zu HOCH gesetzter
Höchststand kommt **nie wieder herunter**. Er verschiebt dauerhaft den
nachziehenden Stop (`trail_after_atr`) und die Verlängerungsregel von
`B11` („weniger als 1 × ATR unter ihrem Höchststand"). Heute lag der
Fehler zu niedrig und blieb folgenlos — die andere Richtung wäre
irreparabel gewesen.

**Behoben:** `build_portfolio` prüft jeden Positionskurs gegen
`snapshots()['last']` und verwirft den Brokerwert bei über 5 %
Abweichung.

Warum gegen den letzten Trade und nicht gegen die Tagesbar: Die Bar
trägt den Schlusskurs von **gestern**. Eine echte Kurslücke (Zahlen,
Übernahme) wäre davon nicht zu unterscheiden. Der letzte Trade ist eine
zeitgleiche Beobachtung — dieselbe Überlegung wie in
`_quote_plausibel`.

Warum 5 % und nicht 2 % wie im Handelspfad: Dort wird zwischen zwei
zeitgleichen Kursen gewählt, ein Fehlalarm kostet nichts. Hier wird der
Wert des Brokers verworfen — eine echte Kurslücke soll dabei nicht
abgeschnitten werden.

Fällt der Kursabruf aus, läuft der Bot mit dem Brokerwert weiter. Eine
fehlende Prüfung darf keine Position verschwinden lassen.

### Was geändert wurde — und was ausdrücklich nicht

**Neu: `audit.check_positionspreise`.** Vergleicht jeden Positionspreis
des Brokers gegen den letzten echten Trade und meldet Abweichungen über
5 % samt Betrag im Depotwert. Die Schwelle ist bewusst milder als die
2 % im Handelspfad: Dort entscheidet sie, welcher von zwei Kursen die
Referenz ist (ein Fehlalarm kostet nichts), hier erzeugt sie einen
Befund.

**Nicht geändert: Der Kontowert wird nicht überschrieben.** Zwei Gründe:

* Die Zahl des Brokers ist die verbindliche. Eine eigene Rechnung
  danebenzustellen hieße, zwei Buchführungen zu haben — und bei
  Abweichung wüsste niemand, welche gilt.
* Für eine **Sperre** ist der pessimistischere Wert die sichere Richtung.
  Er sperrt früher, nicht später.

Gemeldet werden muss die Abweichung trotzdem: In der anderen Richtung
würde derselbe Fehler einen **echten** Verlust verdecken.

### Was der Tag sonst zeigt

Die echten Bewegungen des Tages, nach Beitrag:

```
AUR   -8,6 %   -743 $   -0,69 pp
TLN   -2,8 %   -305 $   -0,28 pp
VIK   -1,4 %   -158 $   -0,15 pp
...
WMT   +2,7 %   +148 $   +0,14 pp
JBLU  +1,4 %   +125 $   +0,12 pp
```

6 von 14 Positionen im Gewinn, Median −0,68 %. Kein einzelner Ausreißer
außer AUR — das ist normale Streuung, kein Regelbruch. Der Regelabgleich
meldet 0 Verstöße.


## G31. Die Historie ist 5- bis 9-mal feiner als der Vorwärtstest (24.08.2026)

**Anlass:** der Einwand, warum bis zum 10.10. gewartet wird, wenn dieselben
Bots auch auf Altdaten laufen könnten. Statt zu argumentieren gemessen —
`B11_dyn_ausstieg_live` über sieben Jahre Historie statt 31 Schattentage.

### Das Ergebnis

Live-Konfiguration (`deploy_to_target`, `allow_topup`) gegen dieselbe
Konfiguration plus `zeitausstieg_dynamisch`, 1.200 Symbole, 1.756
Handelstage:

| | Rendite | Trades |
|---|---:|---:|
| B09-Äquivalent (Live-Konfig) | +11,6 % | 4.403 |
| **B11 (+ dynamischer Zeitausstieg)** | **+56,6 %** | **3.932** |

Gepaart über die Tagesdifferenz:

```
Mittel      +0,0192 %/Tag
Streuung     0,4176 %/Tag
t           +1,92        über 1.756 Handelstage
```

### Die eigentliche Zahl: die Auflösung

| Verfahren | nachweisbar ab | Beobachtungen |
|---|---:|---:|
| Schattenbetrieb am 10.10.2026 | 0,18–0,35 %/Tag | 31 Tage |
| **Historienlauf** | **0,0378 %/Tag** | **1.756 Tage** |
| wirtschaftlich entscheidend (§G23) | 0,0065 %/Tag | — |

**Der Historienlauf ist 5- bis 9-mal feiner.** Der Grund ist Arithmetik:
`sqrt(1756/31) = 7,5` bei praktisch gleicher Streuung (0,418 gegen
0,509 %/Tag).

Der Einwand war also berechtigt. Für eine **Vorauswahl** ist die Historie
dem Vorwärtstest um Größenordnungen überlegen, und das Warten bringt für
diese Frage nichts hinzu, was der Historienlauf nicht schneller liefert.

### Was der Befund über B11 selbst sagt

**t = 1,92** liegt unter der milden Schwelle 2 und weit unter
`schwelle_sigma` (2,85). Kein Befund nach den Regeln des Projekts.

Aber der gemessene Effekt von **+0,0192 %/Tag ist rund das Dreifache der
wirtschaftlich entscheidenden Größe** (0,0065 %/Tag, §G23) — und er kommt
mit **471 Trades weniger**, also geringeren Kosten. Das ist der bisher
stärkste Hinweis, dass an B11 etwas dran sein könnte.

### Der Vorbehalt, der sich hier NICHT herauskürzt

Bei einem gepaarten Vergleich kürzt sich Survivorship normalerweise
weitgehend heraus — beide Seiten handeln dasselbe Universum. **Bei dieser
Frage aber nicht.**

`B11` hält Gewinner **länger**. In einem Universum, aus dem alle
untergegangenen Firmen fehlen, sieht „Gewinner länger halten"
systematisch besser aus, als es war: Genau die Fälle, in denen ein
laufender Gewinner später kollabiert, sind aus den Daten entfernt.
`B09` mit fester Frist trifft dieser Fehler weniger, weil er ohnehin nach
fünf Tagen verkauft.

**Die +45 Prozentpunkte sind deshalb eine Obergrenze mit einer Schlagseite
zugunsten von B11.** Wie groß sie ist, lässt sich ohne ein
Point-in-Time-Universum nicht beziffern.

### Was daraus folgt

1. **Die Historie wird zum Hauptwerkzeug der Vorauswahl.** Sie ist
   schneller *und* feiner. `scripts/32_lernlauf.py` setzt das um.
2. **Der Vorwärtsbetrieb bleibt — genau wegen dieses Vorbehalts.** Er ist
   die einzige Messung ohne Survivorship, und für eine Regel, die
   Gewinner länger hält, ist das kein Detail, sondern der Kern.
3. **Die Rollenverteilung ist damit gemessen begründet, nicht behauptet:**
   Historie verwirft schnell und fein, der Vorwärtstest nimmt ab, weil nur
   er den einen Fehler nicht hat, der genau diese Idee begünstigt.


## G32. DKS-Absturz am 25.08.2026 — echt, nicht der §G29-Kursfehler, und ein neuer Randfall gefunden

**Anlass:** Nutzer meldete −2.300 $ unrealisiert auf DKS, Sorge vor einem
zweiten Fall wie §G29 (Kursfehler) und ob von Hand verkauft werden muss.
Live nachgeprüft statt vermutet.

### Es war real — anders als §G29

| | §G29 (24.08.) | Dieser Fall (25.08.) |
|---|---|---|
| Ursache | IEX-Feed rechnete `change_today` falsch | Dick's Sporting Goods meldete Q2-2026-Zahlen |
| Beleg | 219 Minutenbars zeigten durchgehend 175,87–185,21 $ | Nachrichtenfeed: „Transcript: Dick's Sporting Goods Q2 2026 Earnings Conference Call" + „... Moving In Tuesday's Pre-Market Session"; Snapshot nach Handelsbeginn 143,10 $ (−20,3 % ggü. Vortagesschluss 179,64 $), danach weiter auf 135,05 $ |
| Reale Kursbewegung? | **nein** | **ja** |

### Der Stop hat richtig gegriffen

`live.pruefe_stops_intraday()` verkaufte DKS um 16:00:51 Uhr (MESZ) zu
135,90 $ (`referenz_quelle=quote`, Slippage −62,7 bps gegen den
Erwartungspreis 135,05 $) — Stop lag bei 166,67 $, Einstand 180,81 $ vom
21.08. Realisierter Verlust ≈ **2.694 $** auf 59,98 Stück. Das Depot ist
das **Papierkonto** (`ALPACA_PAPER=True`) — kein echtes Geld betroffen.

**Kein Eingriff von Hand nötig oder erfolgt** — genau wie
`BETRIEBSPLAN.md` §5.3 vorschreibt. Der Mechanismus hat getan, wofür er
gebaut ist.

### Der Randfall, den die Prüfung dabei aufdeckte

Zwei Minuten vor Handelsbeginn (9:28 ET) lieferte `data.snapshots('DKS')`
noch `last=179,64` (Vortagesschluss) — der IEX-Feed hatte seit gestern
keinen neuen Trade gesehen. Wäre in diesem Fenster ein Stop-Check
gelaufen, hätte `_quote_plausibel` die echte, bereits stark gefallene
Bid/Ask-Quote (~137 $) gegen diesen veralteten Referenzwert geprüft,
eine Abweichung von >20 % gegen `_MAX_QUOTE_ABWEICHUNG` (2 %) gefunden
und **den echten Kurs verworfen** — dieselbe Prüfung, die §G29s Fehler
fängt, hätte hier einen echten Kurssturz maskiert. Sobald nach
Handelsbeginn der erste echte Trade durch den Feed lief, aktualisierte
sich die Referenz und der Stop griff korrekt.

**Nicht behoben, absichtlich — kein Fix unter Zeitdruck.** Betroffen wäre
nur ein sehr schmales Fenster (ein echter Kurssprung zwischen
Vortagesschluss und dem ersten Trade nach Handelsbeginn, bei dünn über
IEX gehandelten Werten). Ein Fix braucht eine überlegte Regel (z. B.:
`data.snapshots()`-Referenz verwerfen, wenn ihr Zeitstempel vor dem
heutigen Handelsbeginn liegt) und einen Regressionstest, nicht eine
Änderung an der Handelslogik im laufenden Betrieb.

**Zweiter Nebenbefund:** Der Takt „1800 s bei geschlossener Börse"
bedeutet, dass der Daemon bis zu ~30 Minuten nach der tatsächlichen
Öffnung noch im Ruhemodus stecken kann, bevor der nächste Zyklus prüft.
Hier lag zwischen Handelsbeginn (15:30 MESZ) und der Verkaufsmeldung
(16:00:51 MESZ) rund eine halbe Stunde. Für einen Stop ist das
tolerierbar (kein Bracket-Order-Ersatz, siehe §G3), aber es ist eine
Verzögerung, die bei einem schnelleren Absturz teurer werden kann — auch
das ein Kandidat für eine spätere, gemessene Änderung, nicht für jetzt.

---

## G33. Erster vollständiger 15-Jahre-Lernlauf — 14 Achsen, keine bestanden, zwei auffällig (25.08.2026)

**Anlass:** erster Produktivlauf von `scripts/32_lernlauf.py` nach dem
Umbau (§G31/`UMBAUPLAN.md`), Standard-Zeitraum 15 Jahre, 800 Symbole
angefragt (792 mit ausreichender Historie, `BRK.B` bei yfinance nicht
abrufbar). Lauf-ID `8765e60b58c9`, persistiert in `lernlauf.sqlite`.
3.767 Handelstage, 15 vollständige Jahresscheiben (2012–2026).

### Gepaarter Vergleich gegen `basis` — keine Achse besteht

Zufallsschwelle bei 225 Zellen (15 Bots × 15 Jahresscheiben): **t > 3,79**.
Kein einziger der 14 Bots überschreitet sie:

| Bot | t | Bemerkung |
|---|---:|---|
| `ohne_regime` | **+2,22** | staerkster positiver Wert, aber unter der Schwelle |
| `halten_lang` | +2,05 | dito |
| `dyn_ausstieg` | +1,86 | entspricht `B11_dyn_ausstieg_live` |
| `trailing` | **−3,53** | staerkster Wert überhaupt, in der SCHÄDLICHEN Richtung |

**0 von 14 Achsen bestanden** — deckt sich mit der Basisrate aus §B6
(bislang 0 von 38 Versuchen im ganzen Projekt).

### Walk-Forward — knapp unter der Schwelle, aber deutlich stabiler als der Probelauf

```
Ueber 12 ungesehene Jahre:
  mittlere Differenz : +6,80 Prozentpunkte/Jahr
  Jahre mit Vorsprung: 11 von 12
  t = +3,49   (Schwelle 3,79)
```

**Urteil laut Vorgabe: KEIN BEFUND** (t unter der Schwelle) — das Skript
hält sich an die vorab festgelegte Regel, obwohl die Zahl auffällig
aussieht. Genau dafür ist die Schwelle vorher festgelegt worden, nicht
nachträglich verhandelbar.

Zum Vergleich der erste kleine Probelauf vom 24.08.2026 (8 Jahre, 120
Symbole, `UMBAUPLAN.md` §5): dort mittlere Differenz **−0,25 pp/Jahr**,
t = −0,11, Bot wechselte in 4 von 4 Übergängen. Hier: nur **2 von 11**
Übergängen wechselten den Bot — die Auswahlsequenz war 2015 `stop_weit`,
2016–2020 `halten_lang`, 2021–2026 `ohne_regime`. Deutlich stabiler,
aber die Verfahrensfrage aus §5 bleibt bis zur nächsten Schwelle offen:
**„knapp keine" ist kein Freibrief, es ist „noch kein Befund"**.

### Der Survivorship-Vorbehalt trifft ausgerechnet die beiden Auffälligen

`halten_lang` und `ohne_regime` sind beide Varianten, die Gewinner
LÄNGER laufen lassen bzw. in fallenden Märkten weiterhandeln, statt in
Cash zu gehen. Genau für diese Art Regel gilt der Vorbehalt aus
`UMBAUPLAN.md` §1 in voller Stärke: Das Universum kennt nur heute
gelistete Symbole — Fälle, in denen ein länger gehaltener „Gewinner"
später kollabiert oder eine Position in einer echten Bärenmarkt-Erholung
tatsächlich pleitegeht, fehlen systematisch. Beide Werte sind deshalb
eine **Obergrenze mit Schlagseite**, keine Schätzung der wahren Wirkung.

### `ohne_regime` — die erste echte Bärenmarkt-Messung dieser Achse

`ohne_regime` entspricht exakt der laufenden `B06_ohne_regime` in der
Live-Flotte (Regimefilter aus). Live wurde B06 bisher nur im
durchgehenden Bullenmarkt beobachtet und war deshalb „wirkungslos, aber
keine tote Achse" (§E). Dieser Lauf ist die erste Messung über echte
Bärenmärkte (2018, 2022) — und dort schneidet `ohne_regime` auffällig
gut ab (2022: −2,6 % gegen −19,7 % der Basis). **Folge: B06 bleibt
laufen — genau wie in `UMBAUPLAN.md` §2 empfohlen — es braucht keinen
neuen Flottenbot für diese Achse, sie ist bereits registriert.** Im
Kandidatenregister als `K01_ohne_regime_15j` mit Status `gefunden`
dokumentiert (hist_t 2,22, `n_varianten_getestet=14`).

### `trailing` — das klarste Negativsignal

`trail_after_atr=1,5` ist mit t=−3,53 der einzige Wert, der die Schwelle
beinahe erreicht — in der falschen Richtung, bei −41,8 % Gesamtrendite
über 15 Jahre (schwächstes Ergebnis aller 14 Achsen). `UMBAUPLAN.md`
nannte `trail_after_atr` als „offen, aber ohne Beleg" — jetzt gibt es
einen ersten, klar negativen Beleg. Im Kandidatenregister als
`K02_trailing_15j` angemeldet und direkt auf Status `verworfen` gesetzt
— kein Grund, dafür einen Flottenplatz zu belegen oder die Achse weiter
zu verfolgen.

### Was das nicht heißt

Keiner der beiden Fälle ist ein Befund im Sinne der Projektregeln — beide
liegen unter der Schwelle, und `ohne_regime`/`halten_lang` tragen den
Survivorship-Vorbehalt in voller Stärke. Der Lauf hat **verworfen**
(`trailing`) und **nichts Neues abgenommen** — genau die Rolle, die ihm
`UMBAUPLAN.md` zuweist.

---

## G34. Der Bot sendet nur Marktorders — und der Spread ist 54 % der Kosten (25.08.2026)

**Anlass:** die Frage, ob es in Foren/Fachquellen einfache Dinge gibt,
an die wir nicht denken. Die Recherche hat einen gefunden, und er ist
größer als alles, was die letzten 38 Faktorversuche zusammen erbracht
haben — weil er **nicht auf der Ertragsseite** ansetzt, sondern auf der
Kostenseite.

### Der Fund im Code

```
grep -rn "limit_order" src/ scripts/   ->  nur die Definition, KEIN Aufruf
```

`trading.limit_order()` ist **implementiert und wird nirgends benutzt**.
Der Live-Bot sendet ausschließlich `market_order` (bereits in §G3 als
Nebensatz vermerkt: *„Der Live-Bot sendet ausschließlich `market_order`"*
— dort ging es um fehlende Stop-Orders, die Kostenfolge wurde nie
gezogen).

### Warum das teuer ist — die Zerlegung

Rundlauf über 10.000 $ bei 5 bps Spread (`costs.round_trip`):

| Posten | Betrag | Anteil |
|---|---:|---:|
| **Spread (2× halbe Spanne)** | **5,00 $** | **54 %** |
| Slippage (2× 2 bps) | 4,00 $ | 43 % |
| SEC-Gebühr + FINRA TAF | 0,22 $ | 2 % |
| Kommission (Alpaca) | 0,00 $ | 0 % |
| **Summe** | **9,22 $** | |

Eine Marktorder zahlt den Spread **per Konstruktion**: Kauf zum Brief-,
Verkauf zum Geldkurs. Eine Limitorder kann ihn ganz oder teilweise
**vereinnahmen** statt zu zahlen.

### Was das für den zentralen Konflikt bedeutet

`breakeven_move_pct()` nach Spread-Annahme, gegen den gemessenen
Vorsprung von **+0,11 % je Trade** (§A):

| effektiver Spread | Breakeven | gegen +0,11 % |
|---:|---:|---|
| 5,0 bps (heute) | 0,1423 % | **fehlt 0,032 pp** |
| 4,0 bps | 0,1222 % | fehlt 0,012 pp |
| **3,0 bps** | **0,1022 %** | **TRÄGT** |
| 2,0 bps | 0,0822 % | trägt deutlich |

**Die Lücke von 0,032 Prozentpunkten, die dieses Projekt seit Wochen mit
neuen Faktoren zu schließen versucht, schließt sich vollständig bei einer
Spread-Reduktion von 5 auf 3 bps.** Das ist keine neue Alpha-Quelle,
sondern Arithmetik auf der Kostenseite.

### Die Belege von außen

* **Anand/Samadi/Sokobin, *Review of Finance* (FINRA-Daten):** Retail-
  Limitorders haben **niedrigere Handelskosten** als marktnahe Orders —
  robust gegen Kontrollen für Aktie, Zeitpunkt, Ordergröße und Broker.
  **~65 % werden vollständig ausgeführt**, deutlich mehr als bei
  institutionellen Orders. Der Grund ist ausgerechnet die Trägheit von
  Privatanlegern: Sie stornieren nicht im Sekundentakt.
* **Der Effekt ist am größten bei weiteren Spreads, höherer Volatilität
  und kleineren Werten** — also exakt in unserem Universum. `universe.py`
  handelt bewusst NICHT die 150 liquidesten Werte (§A), sondern 1.200
  mittelgroße. Genau dort ist der Hebel am größten.
* **Gegenbeleg, der mitgehört werden muss:** *„The Negative Drift of a
  Limit Order Fill"* (arXiv 2407.16527) — adverse Selektion. Man wird
  gerade dann ausgeführt, wenn der Kurs weiterläuft. Für eine
  Umkehr-Strategie kann das in beide Richtungen wirken: besserer
  Einstieg, oder ein fallendes Messer.

### Warum das NICHT im Papierdepot geprüft werden kann

**Der wichtigste Vorbehalt.** Alpacas Paper-Simulator füllt Limitorders
laut eigener Dokumentation *„großzügig, sobald der Kurs die Marke
berührt"* — es gibt keine Warteschlangenposition und keinen
Markteinfluss. Genau der Teil, der bei Limitorders entscheidet
(werde ich überhaupt ausgeführt?), ist im Papierdepot **unrealistisch
optimistisch**. Ein Limitorder-Test im Papierdepot würde also genau das
messen, was nicht stimmt.

**Der gangbare Weg ist der Historienlauf:** `simulate.py` hat OHLC-Daten,
also lässt sich prüfen, ob das Tagestief eine Limitmarke berührt hätte —
mit einer *konservativen* Füllannahme (nur füllen, wenn der Kurs die
Marke deutlich unterschreitet, nicht bei bloßer Berührung).

### Status: nicht umgesetzt, bewusst

Das ist eine **Änderung an der Handelslogik** und fällt damit unter die
Sperre bis zum 10.10.2026 (`CLAUDE.md`, `BETRIEBSPLAN` §2.4). Angemeldet
als Kandidat `K03_limit_statt_market`, Status `gefunden`. Der nächste
Schritt ist ein Füllmodell in `simulate.py`, nicht eine Änderung an
`live.py`.

---

## G35. Zwei neue Datenquellen gebaut — und drei eigene Fehler dabei gefunden (25.08.2026)

**Anlass:** §C hält fest, dass der Faktorraum aus Kurs- und Volumendaten
ausgeschöpft ist und neue Information von außen kommen muss. Nach EDGAR
(§G32 ff.) sind jetzt zwei weitere registrierte, aber nie benutzte
Quellen angebunden: **FRED** (`makro.py`) und **GDELT** (`gdelt.py`).

### Die Designentscheidung, ohne die der Test wertlos wäre

**Ein Makrowert ist an einem Tag für alle Symbole gleich.** Der
Querschnitts-IC, mit dem dieses Projekt jeden Faktor prüft
(`research._daily_cross_sectional_ic`), misst aber, ob ein Faktor die
Symbole eines Tages richtig **sortiert** — eine Konstante sortiert
nichts. Makrodaten durch `24_kandidaten_test.py` zu schicken würde
garantiert IC ≈ 0 liefern, und das sähe wie ein Ergebnis aus.

Deshalb ein eigener Test: `makro.regime_auswertung()` teilt die
Handelstage nach dem Makrowert in Bänder und vergleicht die
**Tagesrendite der Strategie** zwischen den Bändern (`scripts/35_regime_kandidat.py`).
Gruppiert wird nach Monat, damit benachbarte Tage nicht als unabhängig
zählen (§B1).

### Die Revisionsfalle — warum nur die halbe FRED-Bibliothek nutzbar ist

`pit.py` warnte bereits: Makro-Erstveröffentlichungen werden später
revidiert. Heutige FRED-Werte auf historische Tage zu legen wäre
Lookahead. `makro.py` trennt deshalb hart:

| Klasse | Beispiele | Nutzbar? |
|---|---|---|
| `REIHEN_OHNE_REVISION` | VIX, Zinsen, Credit Spreads (Marktpreise) | **ja** — werden nie revidiert |
| `REIHEN_REVIDIERT` | BIP, CPI, Arbeitslosenquote | **nein** — nur über ALFRED-Vintages |

Ein Regressionstest (`test_revidierte_reihen_werden_nicht_geladen`) hält
fest, dass die zweite Klasse nicht versehentlich in die erste rutscht.

**Kein API-Schlüssel nötig:** Die revisionsfreien Reihen sind genau die
marktbasierten, und die gibt es auch über yfinance (`^VIX`, `^TNX`,
`^IRX`). Gemessen: 3 von 4 Reihen ohne Schlüssel verfügbar, nur
`hy_spread` (Credit Spread) braucht FRED.

### Drei eigene Fehler, beim Bauen gefunden und behoben

**Fund 1: GDELTs Ratenlimit war im Projekt falsch eingetragen.**
`ratelimit.QUOTAS` führte GDELT seit dem 28.07.2026 mit `per_minute=30`
und der Notiz *„Kein offizielles Limit"* — eine unbelegte Annahme. GDELT
antwortet bei diesem Tempo mit HTTP 429 und nennt sein Limit im
Klartext: **„Please limit requests to one every 5 seconds"** — also
0,2/s statt 0,5/s. Korrigiert, mit dem gemessenen Datum als `verified`.

**Fund 2: `raise_for_status()` stand außerhalb des Retry-Lambdas.**

```python
resp = with_retry(lambda: requests.get(...))   # 429 wirft hier NICHT
resp.raise_for_status()                        # erst hier - zu spät
```

`requests.get` liefert bei HTTP 429 ganz normal ein Response-Objekt
zurück. `with_retry` sah also einen **Erfolg**, und der Backoff, der
genau für 429 gebaut ist, lief **nie an**. Gemessen: drei GDELT-Abfragen
in Folge, alle 429, null Wiederholungsversuche. Nach der Korrektur
(Statusprüfung *innerhalb* des Lambdas, `base_delay=8`) liefen alle drei
Abfragen durch. **Dieselbe Bauart steckt in `edgar.py`** — dort fällt es
nicht auf, weil das Ratenlimit korrekt eingetragen ist.

**Fund 3: eine stumme Spalte, sofort nach dem Bauen.** Die erste Fassung
von `gdelt._als_frame` legte eine Spalte `artikel` an und füllte sie aus
dem Feld `norm`. Das gibt es im Modus `timelinetone` nicht — gemessen:
**923 von 923 Tagen leer**. Genau die Fehlerklasse aus §G13 („stumme
Felder"), diesmal binnen Minuten nach dem Schreiben gefunden. Spalte
entfernt statt mit `NaN` mitgeschleppt, Regressionstest
`test_gdelt_legt_keine_stumme_artikelspalte_an`.

### Stand

13 neue Tests (`tests/test_makro_gdelt.py`), Schwerpunkt
Zeitpunktsicherheit: Ein Merkmal darf sich nicht ändern, wenn man die
Reihe hinter dem Stichtag abschneidet — der Test, der zentrierte Fenster
und `bfill` sofort auffliegen lässt.

### Fund 4: der eigene Test maß eine Tautologie — gefunden vor der Auswertung

**Der wichtigste Fund dieses Umbaus, und er betrifft nicht die Daten,
sondern die Frage.** Der erste Lauf über 8 Jahre und 800 Symbole (2.008
Handelstage) lieferte für `vix_aenderung_5d`:

| VIX-Änderung (5 Tage) | Ø Rendite/Tag | t | Monate |
|---|---:|---:|---:|
| stärkster Rückgang | **+0,2568 %** | **+4,79** | 96 |
| leichter Rückgang | +0,1214 % | +1,97 | 96 |
| leichter Anstieg | +0,0305 % | −0,33 | 95 |
| stärkster Anstieg | **−0,3018 %** | **−5,31** | 89 |

Monoton über alle vier Bänder, |t| bis 5,31, Spanne **0,5586 %/Tag** —
um Größenordnungen mehr als alles, was dieses Projekt je gemessen hat.

**Und vollständig wertlos.** Der Test verglich das Merkmal von Tag *t*
mit der Rendite von Tag *t*. Ein steigender VIX **ist** ein fallender
Markt, und ein Long-Depot verliert an fallenden Tagen. Gemessen wurde
also: *„Wenn der Markt fällt, verlieren wir."* Handelbar ist das nicht —
die VIX-Änderung eines Tages steht erst am Ende dieses Tages fest.

**Behoben** durch `lag=1` als Vorgabe in `regime_auswertung`: Das Merkmal
muss am **Vortagesschluss** feststehen, die Rendite wird am Folgetag
gemessen. Nur so lautet die Frage *„hätte man es vorher wissen können?"*
statt *„beschreibt es, was gleichzeitig passierte?"*.

Gesichert durch `test_gleichzeitiger_zusammenhang_wird_mit_lag_nicht_gefunden`:
Ein rein gleichzeitiger Zusammenhang muss mit `lag=0` ein |t| > 5 zeigen
und mit `lag=1` unter 3 fallen. Fällt der Test um, ist die Tautologie
zurück.

**Einordnung.** Dieselbe Fehlerklasse wie §G11 Fund 6 (das Werkzeug lud
zum verbotenen Fehlschluss ein) und §G24 (eine Zusicherung, die niemand
nachgerechnet hat) — diesmal jedoch **vor** der Notierung als Befund
gefunden, nicht Wochen danach. Der spektakuläre t-Wert war das Warnsignal:
§G23 hält fest, dass eine Strategie mit +0,11 % Vorsprung je Trade keine
Effekte dieser Größe erzeugen kann. Wer solche Zahlen sieht, hat fast
immer einen Messfehler vor sich, keinen Fund.

### Das Ergebnis des korrigierten Laufs: kein Befund

8 Jahre, 800 Symbole, 2.008 Handelstage, 10 Merkmale × 4 Bänder =
**40 Auswertungen**. Zufallsschwelle dafür: `sqrt(2·ln 40) + 0,5 ≈ 3,21`.

| Merkmal | Spanne bestes–schlechtestes Band | max \|t\| |
|---|---:|---:|
| `vix_niveau` | 0,1519 %/Tag | **2,45** |
| `vix_aenderung_5d` | 0,0630 %/Tag | 2,25 |
| `zinsstruktur` | 0,1172 %/Tag | 1,85 |
| `zins_aenderung_20d` | 0,0939 %/Tag | 1,24 |
| GDELT (6 Merkmale) | 0,042–0,127 %/Tag | 1,94 |

**Keines überschreitet die Schwelle.** Damit sind FRED und GDELT als
Regimequelle vorerst durchgefallen — die 39. bis 48. erfolglose Messung
dieses Projekts (§B6).

**Wie stark die Tautologie den ersten Lauf getragen hatte**, zeigt
`vix_aenderung_5d` am deutlichsten: Spanne **0,5586 %/Tag** gleichzeitig
gegen **0,0630 %/Tag** versetzt. **89 % des scheinbaren Effekts waren
reine Gleichzeitigkeit.**

**Der einzige Punkt, der eine Notiz wert ist** (kein Befund, unter der
Schwelle): `vix_niveau` verläuft monoton in der ökonomisch erwarteten
Richtung — bei hohem VIX-Perzentil +0,0987 %/Tag (t = +2,45), bei
niedrigem −0,0233 %/Tag (t = −2,28). Das deckt sich mit der im Modulkopf
von `makro.py` vorab notierten Vermutung: Eine Umkehr-Strategie braucht
Überreaktion, und Überreaktion gibt es in Panik häufiger als in Ruhe.
Vorab notiert, damit es später keine nachträgliche Erzählung wird —
aber t = 2,45 unter einer Schwelle von 3,21 ist der Normalfall, kein
Fund.

---

## G36. Der Intraday-Stop protokollierte keinen Auswertungskontext (25.08.2026)

**Anlass:** `18_health_check.py` sprang auf **ROT** — 8 Datenfehler,
19 von 20 der jüngsten `sell`-Entscheidungen ohne `regime_markt`,
`sektor` und `liq_dezil`.

### Zwei Ursachen, die sich überlagerten

| Ursache | Status |
|---|---|
| **Altbestand.** Bis Commit `dd16334` (22.08.2026) hing der Kontextblock nur an der Kaufschleife; `sell` und `topup` bekamen nichts (§G13 Fund 3). | seit 22.08. behoben — alte Zeilen bleiben natürlich leer |
| **`live.pruefe_stops_intraday` baut gar keinen `MarketSnapshot`** und rief `_mit_kontext` deshalb nie auf. | **war weiterhin offen** |

Der zweite Punkt ist derselbe Mechanismus wie §G21 (dort fehlte
*demselben* Pfad der Lebenslauf): Eine Verbesserung wird an der
Hauptstraße eingebaut und im Sonderpfad vergessen, weil der Code an
`build_snapshot` klebte.

**Warum das mehr als Kosmetik ist:** Der Intraday-Stop feuert per
Konstruktion im Einbruch. Ohne `regime_markt` fehlen der Auswertung
ausgerechnet die Verlusttrades der schlechten Marktphasen — also die
Zeilen, die *„in welcher Marktlage trägt die Strategie?"* überhaupt erst
beantworten könnten. Exakt dieselbe Fehlerrichtung wie §G21.

### Behoben

`_regime_aus_markt()`, `_symbolkontext()` und `_markt_reihe_fuer_regime()`
sind aus `build_snapshot` herausgezogen und werden jetzt auch vom
Intraday-Stop benutzt — einmal je Lauf, nicht je Symbol. Beide liefern
bei einem Ausfall ein leeres Dictionary statt zu werfen: **ein fehlendes
Protokollfeld darf niemals einen Stop-Verkauf verhindern.**

### Beim Reparieren gefunden: eine erfundene Volatilitätsangabe

Der neue Test `test_leere_reihe_erfindet_kein_volatilitaetsband` deckte
sofort einen zweiten Fehler auf. Bei zu wenigen Bars ist die
Volatilität `NaN`:

```python
"ruhig" if vola < 0.15 else "unruhig" if vola > 0.30 else "normal"
```

`NaN < 0.15` und `NaN > 0.30` sind **beide False** — der Wert fiel still
auf `"normal"` durch. Eine erfundene Angabe, die in jeder Auswertung wie
eine Messung aussieht: dieselbe Fehlerrichtung wie die *„erfundene Null"*
aus §G10, die für `B04_halten_lang` ein „DURCHGEFALLEN" meldete, wo gar
nichts messbar war. Behoben, steht jetzt als `unbekannt`.

### Absicherung

9 Regressionstests (`tests/test_stopkontext.py`), zwei neue Mutationen in
`23_mutationstest.py` — **73 von 73 gefangen**. Die Handelsentscheidungen
sind unberührt: Der Vergleich der extrahierten Funktionen gegen den alten
Inline-Block ist bitgleich, solange ≥ 260 Bars vorliegen, und genau das
verlangt `build_snapshot` ohnehin.

### Warum der Health-Check trotzdem noch ROT meldet

**Erwartetes Verhalten, kein unvollständiger Fix.** Der Prüfer sieht sich
die **jüngsten 20** Entscheidungen je Aktionsart an. Davon stammen 19 aus
der Zeit vor den beiden Reparaturen. Er wird grün, sobald 20 neue
Verkäufe aufgelaufen sind — bei der aktuellen Handelsfrequenz einige
Tage.

**Der Prüfer wird dafür ausdrücklich NICHT angepasst.** Eine Schwelle zu
lockern, damit die eigene Reparatur früher grün aussieht, ist genau das,
wovor §B2 warnt („ein Register, das die Hürde senkt, gegen die es messen
soll"). Die Zahl bleibt, bis die Daten sie einholen.

---

## G37. RMBS fünf Tage ohne Stop — ein Broker-Read hat eine echte Position ausgelassen (26.08.2026)

**Anlass:** Routine-Statuscheck auf Nutzerfrage („laufen alle Bots
richtig?"). `18_health_check.py` meldete 🔴: „Position ohne Zustand —
RMBS — Stop/Ziel unbekannt, kann nicht regelkonform geschlossen werden."

### Der Beleg — nicht vermutet, nachgeprüft

`account.orders()` zeigt für RMBS **genau eine** Order: Kauf am
20.08.2026, 14:17:30 UTC, 10,637824 Stück zu 91,53 $, Status `filled`.
Keine zweite Order, kein Verkauf. Die Position wurde **nie geschlossen**.

Trotzdem verzeichnet der Daemon-Log bei einem Neustart am 21.08.:

```
positionen_broker   14   metadaten_geladen   14   verwaist_entfernt   ['RMBS']
```

`state.sync_with_broker()` sah RMBS nicht in der Antwort von
`account.positions()` und löschte Stop (77,39) und Ziel (104,36) sofort —
nach der Logik „fehlt beim Broker → wurde verkauft". Diese Annahme war
falsch, belegt durch die Bestellhistorie.

### Warum es sich nicht von selbst korrigierte

`daemon.recover()` läuft bei jedem Zyklus, in dem der Markt offen ist,
und ergänzt fehlende Metadaten, wenn eine Position beim Broker auftaucht,
aber lokal unbekannt ist (`missing = broker_symbols - stored`). Das hätte
RMBS beim nächsten Handelstag automatisch wieder mit (geschätzten)
Marken versehen müssen. Ist es aber nicht: Der Log zeigt für **jeden**
Zyklus vom 21.08. bis zum Abend des 25.08. `positionen_broker` und
`metadaten_geladen` exakt gleich (15=15) — RMBS fehlte in der
Broker-Antwort **wiederholt**, nicht nur bei diesem einen Neustart. Erst
ein manueller Abruf am Morgen des 26.08. (Marktschluss, ruhige Zeit)
lieferte RMBS korrekt zurück (16 Positionen). Die genaue Ursache auf
Alpaca-Seite (Pagination, Eventual Consistency, ein Rand des
Fractional-Share-Handlings) ist von hier aus nicht feststellbar — nur die
Wiederholung ist belegt.

### Sofortmaßnahme

Marken wiederhergestellt, mit den ECHTEN statt geschätzten Werten:
Fülkurs 91,53 $ (Broker-`avg_entry`), Stop-/Zielabstand 14,84 % aus der
ursprünglichen Kaufentscheidung (`reasons.stop_abstand_pct`, Journal-
Eintrag der ausgeführten Order), High-Water 93,315 $ (höchstes Tageshoch
seit Einstand, aus echten Bars). Kein Blindflug mit `entry * 0.93/1.10`
nötig, weil die Herkunft — anders als bei einer wirklich unbekannten
Altposition — vollständig rekonstruierbar war.

### Root-Cause-Fix

`state.sync_with_broker()`: Ein Symbol gilt jetzt erst nach **zwei
aufeinanderfolgenden** Aufrufen als bestätigt verwaist, nicht nach dem
ersten Fehlen. Neue Tabelle `verdacht_verwaist` — bewusst persistent
(übersteht Neustarts), weil der Ursprungsfehler selbst bei einem
Neustart passierte. Taucht ein vorgemerktes Symbol dazwischen wieder auf,
verfällt der Verdacht automatisch.

**Kosten der Änderung:** Eine wirklich verkaufte Position behält ihre
(dann bedeutungslosen) Marken bis zu einem Zyklus länger — unschädlich,
da `Engine` sie ohnehin nicht mehr im Broker-Depot sieht und keine
Order darauf senden kann. Der Tausch (verzögerte, aber korrekte Löschung
gegen sofortige, manchmal falsche Löschung) ist eindeutig richtig herum.

### Absicherung

4 Regressionstests (`tests/test_verwaisung_bestaetigt.py`), 1 neue
Mutation in `23_mutationstest.py` („Verwaisung wieder beim ersten Fehlen
gelöscht") — **76 von 76 gefangen**. `scripts/22_tests.py`: 496 von 496,
beide Schichten grün. `18_health_check.py`: „Position ohne Zustand" weg,
16 von 16 Positionen mit Zustand.

### Einordnung

Nur das Papierkonto betroffen (`ALPACA_PAPER=True`), kein echtes Geld.
Aber in der Fehlerrichtung identisch mit §G29/§G32: eine Angabe, der der
Bot vertraut (hier: Existenz einer Position im Broker-Read), war für
einen Moment falsch, und der Bot hat das ungeprüft übernommen. Anders als
bei einem Kursfehler (der sich beim nächsten Tick meist korrigiert) blieb
der Schaden hier bestehen, bis eine gezielte Prüfung ihn fand — das ist
der eigentliche Grund für den „erst beim zweiten Mal"-Fix: Eine einzelne
fehlerhafte Momentaufnahme darf niemals dauerhafte Folgen haben.

---

## G38. Die Haltedauer wird live anders gezählt als im Schatten (26.08.2026)

**Anlass:** Durchsicht des Projekts auf Nutzerfrage („was wurde vergessen
oder ist falsch"). Aufgefallen beim Nachrechnen, warum `bars_held` in
`position_meta` bei 15 von 16 Positionen 0 steht.

### Der Fund

`bars_held` ist die Zahl, an der `max_hold_days = 5` hängt — der
Zeitausstieg, der die Strategie definiert. Sie wird an **zwei
verschiedenen Stellen unterschiedlich** gezählt:

```
live.build_portfolio()     len(pd.bdate_range(einstieg, heute)) - 1
lifecycle.handelstage()    dieselbe Rechnung
audit.py, state.py         dieselbe Rechnung

simulate.py:344            engine.update_position() — einmal je BAR
shadow_schritte.py:333     engine.update_position() — einmal je BAR
```

`engine.update_position()` (`engine.py:1106`, `pos.bars_held += 1`) wird
vom **Live-Pfad nie aufgerufen**. Live leitet die Haltedauer aus dem
Einstiegsdatum ab, Simulation und Schatten zählen echte Bars.

**`pd.bdate_range` zählt Montag bis Freitag und kennt keine
Börsenfeiertage.** Der Bar-Kalender kennt sie sehr wohl — ein Feiertag
existiert dort schlicht nicht.

### Gemessen, nicht hergeleitet

Einstieg Do 03.09.2026, Stichtag Do 10.09.2026, dazwischen Labor Day
(Mo 07.09., NYSE und Nasdaq geschlossen):

| Zählweise | Wert |
|---|---:|
| `lifecycle.handelstage("2026-09-03", "2026-09-10")` | **5** |
| echte Handelstage (04., 08., 09., 10.09.) | **4** |

Dieselbe Kalenderspanne ohne Feiertag (17.–24.09.) liefert in beiden
Zählweisen 5. **Der Unterschied hängt am Feiertag, nicht an einem
generellen Off-by-one.**

### Die Folge

`engine.py:825` prüft `pos.bars_held >= cfg.max_hold_days`. In einer
Feiertagswoche ist die Bedingung live nach dem **4.** echten Handelstag
erfüllt, in Simulation und Schatten erst nach dem **5.**

* **`max_hold_days = 5` ist live faktisch eine 4-Tage-Regel** — aber nur
  in Feiertagswochen, also unregelmäßig.
* Es ist eine **live/Schatten-Divergenz**, die in §G4 fehlte. Anders als
  die beiden dort notierten offenen Punkte überschätzt sie nicht den
  Schatten, sondern verändert die **Handelslogik selbst**.
* Betroffen sind rund **10 Börsenfeiertage im Jahr**. Bei einem
  5-Tage-Fenster und ~250 Handelstagen liegt grob jeder fünfte Trade in
  einer Feiertagswoche.

### Noch ist kein Schaden entstanden — und das Datum steht fest

Der Live-Bot handelt seit Ende Juli 2026. Zwischen dem 30.07. und heute
lag **kein einziger US-Börsenfeiertag**. Der Fehler hat also bisher
nachweislich nichts verändert.

**Das erste Mal greift er am Montag, 07.09.2026 (Labor Day)** — und
damit innerhalb des Messfensters, das am 10.10.2026 entschieden wird.

### Behoben am selben Tag — vor dem ersten Auftreten

Neues Modul `handelskalender.py`: Es holt den echten Börsenkalender von
**Alpaca selbst** (3.290 Handelstage), also von derselben Stelle, die
auch den Handel ausführt, und legt ihn auf Platte. Eine fest verdrahtete
Feiertagsliste wäre die schlechtere Wahl — sie veraltet still, genau die
Fehlerklasse, gegen die dieses Projekt seine Wächter gebaut hat.

**Fünf Stellen rechneten dieselbe Größe:** `lifecycle.handelstage`,
`live.build_portfolio`, `state.py`, `audit.py`, `nachbetrachtung.py`.
Alle fünf nutzen jetzt `handelskalender.zwischen()`. Ein Test über den
**Syntaxbaum** (nicht über den Text — sonst schlägt diese Erklärung hier
selbst an) stellt sicher, dass keine sechste Zählweise zurückkommt.

**Der bewusste Rückfall:** Ist der Kalender nicht abrufbar und nichts
zwischengespeichert, wird wieder mit Werktagen gerechnet. Schlechter,
aber nie schlechter als vorher — und ein Abbruch wäre hier die
gefährlichere Wahl: Eine Haltedauer, die nicht berechnet werden kann,
hielte Positionen unbegrenzt offen.

**Warum das trotz der Sperre bis zum 10.10. richtig war.** Es ist keine
Parameteränderung, sondern eine Korrektur, die `max_hold_days = 5`
erstmals bedeuten lässt, was überall dokumentiert ist. Sie bringt Live
**in** Übereinstimmung mit Schatten und Simulation, statt sie
auseinanderzuführen. `B11` ist davon unberührt — es vergleicht zwei
Schattenbots miteinander.

**Absicherung:** `tests/test_haltedauer_feiertage.py`, 9 Tests. Die
vorherige Fassung hielt bewusst den falschen Ist-Zustand fest und hat
beim Umbau angeschlagen — genau dafür war sie gebaut.

---

## G39. Die 5 bps, auf denen die ganze Kostenrechnung steht, sind nie gemessen worden (26.08.2026)

**Anlass:** Nachrechnen von §G34 vor dem Limitorder-Lauf. Die Kernaussage
dort lautet: Bei 5 bps Spread liegt der Rundlauf-Breakeven bei 0,1423 %,
bei 3 bps bei 0,1022 % — und damit unter dem gemessenen Vorsprung von
+0,110 %. Die Frage war nur: **woher kommt die 5?**

### Der Fund steht als Kommentar im eigenen Quelltext

`costs.py:151`, seit dem ersten Tag unverändert:

```python
# Ohne Quote: Spanne schaetzen. 5 bps ist fuer Large Caps typisch,
# bei Nebenwerten sind 30-100 bps normal.
half = last * (spread_bps if spread_bps is not None else 5.0) / 20_000
```

**Der Kommentar sagt selbst, dass 5 bps für ein anderes Marktsegment
gilt als das, was der Bot handelt.**

`universe.py:87` sagt, warum das Segment absichtlich ein anderes ist:

> „…bei den 150 liquidesten Werten allein war derselbe Effekt NICHT
> nachweisbar"

Die Strategie handelt bewusst **nicht** dort, wo 5 bps typisch sind.
Genau dieselbe Begründung führt §G34 als Argument **für** Limitorders an
(„Der Effekt ist am größten bei weiteren Spreads … und kleineren Werten
— also exakt unser Universum"). Beide Sätze stehen im selben Register.
Zusammengelesen heben sie sich auf: Wenn unser Universum weite Spreads
hat, dann ist 5 bps die falsche Zahl für den Breakeven.

### Wo die Zahl überall drinsteckt

| Ort | Wert |
|---|---|
| `costs.effective_price` (Vorgabe ohne Quote) | 5,0 bps |
| `costs.round_trip`, `breakeven_move_pct` | 5,0 bps |
| `simulate.SimConfig.spread_bps` | 5,0 bps |
| `simulate.SimConfig.slippage_bps` | 3,0 bps |
| §G4 „Kosten: 5 bps + 3 bps angenommen" | — |
| §G34 Rundlaufrechnung, §A zentraler Konflikt | — |

Damit hängt **jedes** Backtest- und Historienergebnis des Projekts an
dieser einen ungemessenen Zahl — einschließlich des Lernlaufs (§G33),
des Limitorder-Vergleichs (§G34) und der Aussage „Vorsprung +0,110 %
gegen Breakeven 0,1423 %", die den zentralen Konflikt definiert.

### Was tatsächlich gehandelt wird

Liquiditätsdezile der protokollierten Live-Käufe (Dezil 1 = liquideste
10 % des Universums; das Universum selbst ist bereits auf ≥ 1 Mio. $
Tagesumsatz gefiltert):

| Dezil | Käufe | Anteil |
|---:|---:|---:|
| 1 | 4 | 16 % |
| 2 | 3 | 12 % |
| 3 | 6 | 24 % |
| 4 | 8 | 32 % |
| 5 | 2 | 8 % |
| 6 | 2 | 8 % |

**n = 25** — klein, siehe §B4, das ist eine Beschreibung und keine
Schätzung. Der Schwerpunkt liegt in den Dezilen 3–4. Das ist weder
Large Cap noch Nebenwert, sondern dazwischen: der Bereich, für den der
Quelltextkommentar **keine** Zahl nennt.

### Was das NICHT heißt

**Nicht** „der Spread ist 30 bps". Diese Zahl ist genauso ungemessen wie
die 5. Der Befund ist ausdrücklich, dass **beide Enden** unbelegt sind
und die tatsächliche Zahl dazwischen liegt.

**Nicht** „der Limitorder-Lauf ist wertlos". Er vergleicht zwei Arme mit
demselben Kostenmodell; die Differenz zwischen ihnen bleibt gültig. Was
sich verschiebt, ist die **Höhe** des Breakevens, gegen den das Ergebnis
gelesen wird — und damit die Frage, ob die gesparte Spanne reicht.

**Nicht** „die Slippage-Messung beantwortet das". `journal.slippage_werte()`
misst die Abweichung vom **Referenzkurs zum Orderzeitpunkt** (Ask beim
Kauf, Bid beim Verkauf). Wer schon am Ask kauft, hat die halbe Spanne
bereits bezahlt, bevor die Messung beginnt. Slippage und Spread sind
zwei verschiedene Kosten; `BETRIEBSPLAN` §3.1 sagt das auch, zieht aber
nur den Schluss „Spread fällt im Papierdepot nicht an" — nicht den
zweiten, dass die im Backtest angesetzte Spread-Höhe damit weiterhin
unbelegt ist.

### Ein Nebenbefund zur Slippage-Messung

Aufgeschlüsselt nach Referenzquelle zerfällt der Median von +0,0 bps in
zwei gegenläufige Teilmengen (n = 137, Stand 26.08.2026):

| Referenzquelle | n | Median | Mittel |
|---|---:|---:|---:|
| `quote` (Bid/Ask, IEX) | 97 | −1,0 bps | −46,4 bps |
| `quote_verworfen` (letzter echter Trade) | 40 | **+11,8 bps** | +18,9 bps |

Vorzeichen: **positiv = ungünstig** (schlechter ausgeführt als die
Referenz).

Die Teilmenge mit der **belastbareren** Referenz — dem letzten echten
Trade statt einer IEX-Quote — zeigt konsistent ungünstige Ausführung um
rund 12 bps und läge damit über der Bedingung „Median < 8 bps" aus
`BETRIEBSPLAN` §3.1. Und rund 12 bps gegen einen Referenzkurs in
Trade-Nähe ist ungefähr das, was eine halbe Spanne von 24 bps kostet.

**Beide Teilmengen sind verzerrt, in entgegengesetzte Richtungen**, und
keine ist eine Schätzung der echten Ausführungskosten:

* `quote_verworfen` entsteht per Konstruktion nur dort, wo die Quote um
  über 2 % vom letzten Trade abwich (`_MAX_QUOTE_ABWEICHUNG`) — also in
  unruhigen, dünnen Momenten mit ohnehin weiten Spannen. Die Teilmenge
  **überschätzt** den Normalfall.
* `quote` mit einem Mittel von −46 bps behauptet, der Bot führe im
  Schnitt 46 bps **besser** aus als die Quote. Das passiert an einem
  echten Markt nicht. Es ist ein Papierkonto (`ALPACA_PAPER=True`);
  gemessen wird Alpacas Füllmodell, nicht der Markt — dieselbe
  Einschränkung, die §G34 für Limitorders ausdrücklich zieht und die für
  Marktorders genauso gilt.

Der Nebenbefund ist deshalb **kein** neuer Kostenwert, sondern eine
Warnung vor dem gepoolten Median: Er ist der Mittelweg zweier
Teilmengen, die sich widersprechen, und die mit der besseren Referenz
fällt durch.

### Was zu tun wäre — und warum es noch nicht getan ist

Die Spanne ist direkt messbar: `data.latest_quotes()` liefert Bid und
Ask. Eine Messung über das Live-Universum **während der Handelszeit**
(15:30–22:00 MEZ) ergäbe eine Verteilung statt einer Annahme.

**Der Vorbehalt, der sie nicht ersetzt:** Der freie Feed ist IEX, und
IEX sieht ~2 % des US-Volumens (§G29). Eine daraus gerechnete Spanne ist
eine **Obergrenze**, keine Punktschätzung. Für die Frage, die hier
ansteht, ist eine Obergrenze aber genau das Richtige: Trägt der
Vorsprung selbst im ungünstigen Fall, ist die Sache entschieden.

Nicht sofort ausgeführt, weil zum Zeitpunkt des Fundes (10:40 MEZ) die
US-Börse geschlossen war — außerhalb der Handelszeit sind Spannen
systematisch weiter und die Messung wertlos.

---

## G40. Limitorder statt Marktorder — gemessen, kein Befund (26.08.2026)

**Der Lauf, der seit dem 25.08. gebaut war und nie gestartet wurde.**
`scripts/36_limit_vergleich.py`, 8 Jahre, 800 Symbole, 1.492.071 Bars,
identische Tage und Kurse in beiden Armen. Einziger Unterschied: der
Ordertyp beim Einstieg. Verkäufe bleiben in beiden Armen Marktorders.

### Das Ergebnis

Marktorder (der heutige Live-Bot): **+54,7 %**, 5.243 Trades,
**+0,2576 %** je Trade.

| Marke unter dem Entscheidungskurs | Rendite | Trades | je Trade | Füllquote | verpasst | **t** |
|---:|---:|---:|---:|---:|---:|---:|
| 5 bps | +57,0 % | 4.886 | +0,3363 % | 81 % | 1.170 | **−0,008** |
| 10 bps | +64,0 % | 4.859 | +0,3543 % | 79 % | 1.256 | +0,218 |
| 25 bps | +70,6 % | 4.793 | +0,3281 % | 76 % | 1.537 | +0,423 |
| 50 bps | +95,7 % | 4.664 | +0,3494 % | 70 % | 2.018 | +1,035 |

**Zufallsschwelle bei 4 geprüften Marken: |t| > 2,17. Höchster Wert
1,035. Urteil: KEIN BEFUND.**

Damit steht die Bilanz bei **0 von 49**.

### Warum die Renditespalte in die Irre führt

+95,7 % gegen +54,7 % sieht nach der Lösung des zentralen Konflikts aus.
Sie ist es nicht, aus zwei Gründen.

**Erstens: der gepaarte t-Wert ist die maßgebliche Zahl, nicht die
Endrendite.** Beide Arme sehen dieselben Tage; die Tagesdifferenz kürzt
den Marktfaktor heraus. Über ~2.000 Handelstage liegt sie bei t = 1,03 —
also innerhalb dessen, was Zufall erzeugt. Eine Endrendite über acht
Jahre hängt an wenigen Pfaden; genau dagegen wurde der gepaarte Test
vorab festgelegt.

**Zweitens, und das ist der eigentliche Punkt: bei 50 bps wird gar
nicht mehr die Kostenfrage gemessen.** Eine Marke 0,5 % unter dem
Entscheidungskurs heißt „kaufe nur, wenn der Wert morgen noch einmal ein
halbes Prozent tiefer fällt". Das ist **eine andere Einstiegsregel**,
keine gesparte Spanne — und für eine Umkehr-Strategie eine plausibel
bessere. Die Kosten- und die Signalfrage sind bei großen Marken
untrennbar vermischt.

**Sauber getrennt sind sie nur bei 5 bps** — dort entspricht die Marke
ungefähr der Spanne selbst, die Einstiegsregel bleibt praktisch
unverändert. Und genau dort steht:

```
t = -0,008
```

**Bei der reinen Kostenfrage ist der Effekt exakt null.**

### Was der Lauf trotzdem belegt — die Mechanik stimmt

| Größe | erwartet | gemessen |
|---|---|---|
| Füllquote | ~65 % (Anand/Samadi/Sokobin, FINRA) | **70–81 %** |
| Ersparnis je gefülltem Trade | 5 bps Spanne + 3 bps Slippage | +0,079 pp je Trade bei 5 bps |

Die Füllquote des Modells liegt **über** dem Literaturwert — das Modell
ist also eher großzügig als streng, trotz des bewusst konservativen
Puffers (das Tagestief muss die Marke unterschreiten, Berühren zählt
nicht). Die Ersparnis kommt in der erwarteten Größenordnung an.

**Die Ersparnis ist real und wird von den verpassten Einstiegen genau
aufgefressen.** 1.170 von 6.056 Kaufversuchen (**19 %**) kommen nie
zustande. Was an der Spanne gespart wird, kostet die Auswahl.

### Der Vorbehalt, unter dem dieses Urteil steht

Beide Arme rechnen mit `spread_bps = 5,0` — der Zahl, die §G39 am selben
Tag als **ungemessen** ausgewiesen hat („für Large Caps typisch",
angewandt auf ein Universum, das absichtlich keine Large Caps handelt).

Wäre die echte Spanne deutlich weiter, wäre auch die Ersparnis der
Limitorder deutlich größer, und die Rechnung „Ersparnis gegen verpasste
Einstiege" könnte kippen. **Die verpassten Einstiege sind von der
Spread-Annahme unabhängig, die Ersparnis nicht.**

**Das ändert am Urteil von heute nichts.** Die Entscheidungsregel stand
vorab fest (`docs/UEBERGABE.md` §7: „Negativ → K03 auf `verworfen`"),
das Ergebnis ist negativ, `K03_limit_statt_market` steht auf
**`verworfen`**. Sie nachträglich aufzuweichen, weil ein Vorbehalt
gefunden wurde, wäre genau das Verhalten, gegen das §B2 dieses Register
überhaupt geschrieben hat.

**Der richtige Weg, falls §G39 eine wesentlich weitere Spanne zeigt,**
ist eine **neue** Voranmeldung mit dem gemessenen Wert und einem eigenen
Zählerplatz — nicht das Zurückholen dieser hier.

### Nebenbefund: das Skript warnte nicht vor kleinen Läufen

`34_edgar_kandidat.py` druckt unter 100 Symbolen ausdrücklich „ZEITMESSUNG,
KEIN Befund (§B4)". `36_limit_vergleich.py` tat das nicht — ein Probelauf
mit `--symbole 40` lieferte eine fertig formatierte Ergebnistabelle mit
t-Werten, von einem echten Lauf nicht zu unterscheiden. Nachgezogen,
gleiche Grenze und gleicher Wortlaut wie in Skript 34.

---

## G41. Der EDGAR-Test schnitt zwei Drittel der Historie weg (26.08.2026)

**Anlass:** Nutzerfrage, ob dem laufenden EDGAR-Test schon etwas zu
entnehmen ist. Geprüft wurde bewusst **nur die Abdeckung**, kein IC und
kein t-Wert (§B4). Die Abdeckung reichte.

### Was auffiel

Aus dem Zwischenstand bei 650 von 2.168 Symbolen:

| | |
|---|---|
| Symbole mit Score ≠ 0 je Handelstag | Median **8** von 642 |
| Tage mit ≤ 5 informativen Symbolen | **47 %** |
| Median erste 250 Tage → letzte 250 Tage | **2 → 87** |

Ein Faktor 40 in der Abdeckung über den Zeitraum.

### Die Ursache — eine Zeile

```python
edgar.py:311   if max_filings:
                   f = f.tail(max_filings)      # die NEUESTEN N
```

`--max-filings` stand auf **150**. Aus dem Plattencache nachgemessen
(400 CIKs): **Median 436 Form-4-Meldungen je Symbol** seit 2018,
**85 % der Symbole über 150.** Dem mittleren Symbol fehlten also rund
**zwei Drittel** seiner Historie — und zwar immer die ältere Hälfte,
weil `.tail()` von hinten nimmt.

Sichtbar in den Daten: Von 344 Symbolen mit überhaupt einem
Insiderkauf begannen **13 vor 2022 und 314 ab 2023**.

### Warum das den Test zerstört hätte

Die Prüfkette verlangt **Jahresstabilität** — ein Vorzeichenwechsel
zwischen Jahren disqualifiziert. Bei zwei informativen Symbolen pro Tag
ist der Jahres-IC eines frühen Jahres reines Rauschen; sein Vorzeichen
kippt mit einer Münze. **Der Faktor wäre durchgefallen aus einem Grund,
der nichts mit Insiderhandel zu tun hat.**

Kein Lookahead — aber dieselbe Familie wie §G11 (Survivorship) und
§G35 Fund 4 (Tautologie): eine Eigenschaft der Datenbeschaffung, die
sich als Eigenschaft der Welt ausgibt.

### Behoben

`max_filings` ist keine Kürzung mehr, sondern eine **Laufzeitbremse mit
Ausnahme**: `edgar.ZuVieleMeldungen`. Ein Symbol, dessen Historie nicht
vollständig geladen werden kann, wird **ausgeschlossen**, nicht halbiert
— ein halbes Panel ist schlimmer als kein Panel, weil es vollständig
aussieht.

* `34_edgar_kandidat.py` fängt die Ausnahme, zählt sie, und **warnt
  laut, wenn über 25 % des Universums fehlen** (die Ausgeschlossenen
  sind keine Zufallsstichprobe — es sind die Firmen mit den meisten
  Insidern, also die größeren).
* Neue Vorgaben: `--since 2022-09-01`, `--max-filings 400`. Nach
  derselben Messung laufen damit ~90 % der Symbole vollständig durch.
* **Zweiter Fundort:** `10_simulate.py:266` hatte dieselbe Zeile mit
  `max_filings=120`. Nachgezogen.

### Zweite Stelle, an der dieselbe Verzerrung entsteht

Beim Nachprüfen der neuen Vorgaben aufgefallen: `--jahre` (Kurshistorie)
und `--since` (Meldungsfenster) waren **unabhängig voneinander**. Mit
`--jahre 8 --since 2022-09-01` hätte das Kursraster vier Jahre weiter
zurückgereicht als die Meldungen — der Faktor wäre dort konstant null
gewesen, und die Zeitverzerrung wäre in exakt derselben Form
zurückgekommen, nur an anderer Stelle.

**Die Korrektur an `max_filings` allein reicht also nicht.** Sie sorgt
nur dafür, dass innerhalb des Meldungsfensters nichts fehlt.

`_pruefe_fenster()` bricht jetzt **hart ab**, wenn das Kursfenster mehr
als 90 Tage vor dem Meldungsfenster beginnt, und nennt den korrigierten
Wert. Vorgaben aufeinander abgestimmt: `--jahre 4.0`, `--since 2022-09-01`.

**Absicherung:** `tests/test_edgar_abschneiden.py`, 5 Tests (darunter
einer, der die Vorgaben des Skripts gegen die gemessene
Meldungsverteilung prüft), 1 Mutation.

**Der Lauf vom 25.08. ist damit ungültig** und wird verworfen. Der
Plattencache (1,2 GB) bleibt und macht den Neustart billiger.

---

## G42. Positionsgrößen — die Achse, die 63 Versuche lang nie variiert wurde (26.08.2026)

**Der Fund ist eine Abwesenheit.** Alle 13 Flottenbots und alle 14
Lernlauf-Achsen variieren Ein- und Ausstiegsregeln. **Wie viel Kapital
ein Kandidat bekommt, war fest verdrahtet:**

```python
engine.py   _vola_gewicht(atr_pct) = min(1.5, 0.03 / atr_pct)
```

Der Score entscheidet heute, **ob** gekauft wird und in welcher
Reihenfolge — **nicht wieviel**. Ein Kandidat mit Score 0,95 bekommt
dasselbe wie einer mit 0,40, korrigiert nur um die Volatilität.

### Warum das kein weiterer Faktorversuch ist

Diese Achse ändert den Vorsprung je **Dollar** bei **unverändertem
Umschlag**. Jede der 63 bisherigen Achsen justierte Randbedingungen
eines Vorsprungs, der zu klein ist (§A). Diese verschiebt Kapital
innerhalb desselben Vorsprungs.

### Gebaut

`EngineConfig.groessen_modus` mit vier Werten:

| Wert | Gewicht |
|---|---|
| `inverse_vola` | `min(1.5, 0.03/atr_pct)` — **Vorgabe, bitgleich zu vorher** |
| `gleich` | 1,0 — die Nullhypothese |
| `score` | Score, Untergrenze 0,05 |
| `score_vola` | Produkt aus beidem |

An **beiden** Verteilungsstellen eingebaut (Neukauf und Nachkauf), im
Konfigurations-Abzug protokolliert, drei neue Lernlauf-Achsen.

**Die Beweislast bei einer Änderung an der Handelslogik:** 43 Tests,
darunter ein parametrisierter über 35 Kombinationen aus ATR und Score,
der zeigt, dass `inverse_vola` **rechnerisch identisch** zum alten
`_vola_gewicht` ist. Dieselbe Beweisform wie beim §G20-Split. Plus zwei
Mutationen.

**Der Vorbehalt, vorab notiert:** `score` konzentriert das Kapital.
`B07_mehr_positionen` zeigt bereits t = −2,16 — weniger Breite hat
geschadet. Eine Verbesserung des Erwartungswerts bei höherer Streuung
ist kein Fortschritt, wenn die Streuung die Nachweisbarkeit frisst.
Zu messen im Historienlauf (3.767 Handelstage), nicht im Schatten (15).

---

## G43. Replikation erhöhte bisher die Hürde, statt sie zu stützen (26.08.2026)

**Anlass:** Die Frage, ob die Zufallsschwelle zu streng gesetzt ist.

### Die Schwelle selbst ist richtig — nachgerechnet

`schwelle_sigma(n) = sqrt(2·ln n) + 0,5`:

| n | Projekt | Bonferroni (5 %) | echte Familien-Fehlerrate |
|---:|---:|---:|---:|
| 16 | 2,85 | 2,96 | 6,8 % |
| 40 | 3,22 | 3,23 | 5,0 % |
| 225 | 3,79 | 3,69 | 3,3 % |

Praktisch Bonferroni, bei kleinem n sogar **milder**. Harvey/Liu/Zhu
fordern für neue Faktoren t > 3,0.

**Die Gegenprobe entscheidet:** Bei Schwelle 2,0 und 63 Versuchen sind
**2,9 Zufallstreffer** zu erwarten (Wahrscheinlichkeit für mindestens
einen: 95 %). Die tatsächlichen Beinahe-Treffer — `ohne_regime` +2,22,
`vix_niveau` +2,45, `halten_lang` +2,05, `dyn_ausstieg` +1,86 — sind
**genau so viele, wie reines Rauschen liefert.**

### Der echte Fehler liegt woanders

**Jeder Test zählte als eigener Versuch — auch zweimal dieselbe Frage
auf verschiedenen Daten.** `halten_lang`:

```
Schatten,      16 Handelstage    t = +1,16
Historienlauf, 15 Jahre          t = +2,05
```

Nach alter Rechnung: zwei Versuche, beide unter der Schwelle, beide
erhöhen die Hürde **für alle anderen laufenden Messungen**. Das ist
verkehrt herum. Zwei übereinstimmende Läufe auf getrennten Daten sind
ein **stärkerer** Beleg, nicht ein doppelt bestrafter.

### Behoben

`statistik.kombiniere_unabhaengig()` — Stouffer:
`Z = Σ(wᵢ·zᵢ) / √(Σwᵢ²)`. Für die beiden oben: **t = +2,27**
(gewichtet nach √Gruppenzahl: +2,12). Beides weiterhin unter 2,85 —
`halten_lang` besteht auch kombiniert nicht, und das ist die richtige
Antwort.

**Zwei Dinge, die die Funktion ausdrücklich nicht tut:**

1. **Sie senkt keine Schwelle.** Die Schwelle wird übergeben, nicht
   gerechnet. Replikation spart einen Zählerplatz, keine Hürde.
2. **Sie mittelt keinen Widerspruch weg.** Zeigen die Läufe
   verschiedene Vorzeichen, ist das Ergebnis nie `belastbar` — dann ist
   die Kombination keine Replikation, sondern eine Mittelung über einen
   Widerspruch.

**Die Bedingung, an der alles hängt:** Die Läufe müssen unabhängig
sein. Zwei Auswertungen desselben Schattenbestands sind es nicht.
Abhängige Läufe hier hineinzugeben baut einen t-Wert, der nur wie eine
Replikation aussieht — dieselbe Fehlerklasse wie die Überlappung aus
§B1/§G12, eine Ebene höher.

**Was die Schwelle NICHT löst — und das ist der eigentliche Engpass:**
§G23 und §G31. Das Messgerät löst 0,0378 %/Tag auf, entscheidend wären
0,0065 %/Tag. Eine niedrigere Schwelle tauscht „findet nichts" gegen
„findet Rauschen". Trennschärfe kauft man mit Breite (IR = IC·√BR),
nicht mit einer niedrigeren Hürde.

**Absicherung:** `tests/test_replikation.py`, 7 Tests, 1 Mutation.

---

## G44. Die Spanne ist mit dem freien Feed nicht messbar (26.08.2026)

**Vorab festgelegt** in `BETRIEBSPLAN` §3.4, geschrieben um 15:05 Uhr —
25 Minuten vor Handelsbeginn, also bevor eine Zahl existierte.

### Das Ergebnis

Sechs Aufnahmen über das Live-Universum, 15:35–16:25 Uhr. Nur Quotes
jünger als 120 s, Eröffnungsphase ausgeschlossen:

| | bps |
|---|---:|
| 10 % | **4,9** |
| 25 % | **11,9** |
| **Median** | **268,0** |
| 75 % | 722,0 |
| 90 % | 1.132,1 |

Nach Liquiditätsdezil liegt der Median zwischen 54 und 434 bps, **ohne
erkennbare Ordnung** — Dezil 6 (dünn) hat mit 54 bps den *engsten*
Median, Dezil 3 mit 434 den weitesten. Eine echte Spannenverteilung
sähe monoton aus.

### Das Urteil: nicht verwertbar

268 bps sind 2,7 %. Das ist keine Geld-Brief-Spanne, das ist ein Feed,
der die meisten unserer Werte nicht ernsthaft quotet. IEX sieht ~2 % des
US-Volumens (§G29); bei allem außerhalb der größten Namen steht dort
eine breite, wenn auch aktuelle Quote.

**Es liegt nicht an veralteten Daten.** Genau dafür wurde das
Quote-Alter mitgemessen: 4.655 von 5.777 Quotes waren älter als zwei
Minuten und wurden verworfen. Der Median der **frischen** Quotes bleibt
bei 268 bps. Die fehlende Monotonie über die Dezile ist der zweite
Beleg.

Nach der vorab festgelegten Regel (§3.4, Zeile „> 20 bps") gilt damit:
**zweite Quelle nötig, vor jedem Schluss.** Diese Messung entscheidet
nichts.

### Was sie trotzdem beantwortet — und es ist der wertvollere Teil

**Die Slippage-Messung des Projekts steht auf denselben Quotes.**
`live._reference_price` nimmt beim Kauf den IEX-**Ask** als
Bezugsgröße. Liegt der im Median 134 bps über der Mitte, sieht jede
Ausführung dagegen günstig aus. Genau das zeigt §G39:

| Referenzquelle | n | Median | Mittel |
|---|---:|---:|---:|
| `quote` (IEX Bid/Ask) | 97 | −1,0 bps | **−46,4 bps** |
| `quote_verworfen` (letzter echter Trade) | 40 | **+11,8 bps** | +18,9 bps |

Die −46 bps „günstiger als erwartet" im oberen Teil waren nie eine
Ausführungsqualität. **Sie sind die Weite der IEX-Quote.** Damit ist die
Teilmenge mit dem letzten echten Trade als Referenz die einzige
belastbare — und sie sagt rund **+12 bps ungünstig**, gegen eine im
Kostenmodell angesetzte halbe Spanne von 2,5 bps.

### Die Einordnung, die daraus folgt

Die Strategie braucht laut §3.4 eine Spanne von **≤ 3,4 bps**, um bei
heutigem Umschlag auf null zu kommen. Die beiden verwertbaren Signale
des Tages:

* unterstes Zehntel der IEX-Quotes: **4,9 bps** — also schon dort, wo
  der Feed am besten ist, über der Anforderung;
* Ausführung gegen den letzten echten Trade: **~12 bps**.

**Beide liegen über 3,4 bps.** Das ist kein Beweis — die erste Zahl ist
eine Auswahl der besten Fälle, die zweite eine verzerrte Teilmenge
(sie entsteht nur, wo die Quote um über 2 % danebenlag). Aber es gibt
**keine** Messung, die in Richtung 3,4 bps zeigt.

### Was als Nächstes zu tun wäre

Eine Quelle, die die konsolidierte NBBO sieht. Kostenlos praktisch nur
Tiingo (`ratelimit.QUOTAS`, 500 Abrufe/Tag, max. 1.000 Symbole/Monat) —
das reicht für eine Stichprobe von ~200 Symbolen an mehreren Tagen, nicht
für das ganze Universum. Für die Frage „liegt die Spanne über oder unter
3,4 bps" genügt eine Stichprobe.

**Nicht getan wurde:** `costs.py` anzufassen. Ein geänderter
Kostenparameter bewertet jede vergangene und laufende Messung neu; das
ist eine eigene, vorangemeldete Entscheidung (§3.4).

---

## G45. Lernlauf mit 20 Achsen — 0 von 19, aber ein sauberes Muster (26.08.2026)

15 Jahre, 800 Symbole, 3.768 Handelstage, 20 Achsen über 15
Jahresscheiben. Lauf `d44ad22a8731`. **Zufallsschwelle bei 300 Zellen:
|t| > 3,88.**

### Ergebnis: keine Achse besteht

| Achse | t | Richtung |
|---|---:|---|
| `ohne_regime` | **+2,02** | stärkste positive |
| `halten_lang` (10 T) | +1,81 | |
| `halten_40` | +1,80 | |
| `score_gewicht` | **+1,75** | erste Größenmessung überhaupt |
| `halten_20` | +1,50 | |
| `gleichgewicht` | +1,42 | |
| `dyn_ausstieg` | +1,37 | = laufendes `B11` |
| `halten_kurz` (3 T) | +1,15 | |
| … | | |
| `score_mal_vola` | +0,36 | |
| `trailing` | **−3,42** | einzige über der Schwelle — **schädlich** |

Damit steht die Bilanz bei **0 von rund 68**.

### Was die Zahlen trotzdem sagen

**Erstens: Die Haltedauer zeigt keine Kante nach oben.** Alle vier
Halte-Achsen (3, 10, 20, 40 Tage) liegen positiv zwischen +1,15 und
+1,81 — aber ohne Anstieg zum längeren Horizont hin. Die vorab in
`docs/TAKTIKWECHSEL.md` §3 gestellte Frage („ab welchem Horizont
übersteigt der Vorsprung je Trade die Kostenschwelle?") bekommt damit
**keine positive Antwort**. 40 Tage sind nicht besser als 10.

**Zweitens: Positionsgrößen wirken, aber schwach.** Erste Messung
dieser Achse überhaupt (§G42). Score-Gewichtung (+1,75) schlägt
Gleichgewichtung (+1,42) und das Produkt (+0,36). Die Rangfolge ist
ökonomisch plausibel — mehr Kapital in bessere Kandidaten —, aber
keiner der drei Werte trägt.

**Drittens: `trailing` ist der reproduzierbarste Befund des Projekts —
und er ist negativ.** −3,42 heute, −3,53 am 25.08. Zweimal über der
Schwelle, beide Male schädlich. Das ist das einzige Ergebnis, das
dieses Projekt je zuverlässig reproduziert hat.

### Der Walk-Forward — zum zweiten Mal knapp darunter

| | 25.08. (14 Achsen) | 26.08. (20 Achsen) |
|---|---:|---:|
| mittlere Differenz | +6,80 pp/Jahr | +5,37 pp/Jahr |
| Jahre mit Vorsprung | 11 von 12 | **10 von 12** |
| t | +3,49 | **+2,60** |
| Schwelle | 3,79 | **3,88** |
| Botwechsel | 2 von 11 | 2 von 11 |

**Urteil laut Vorgabe: KEIN BEFUND.** Die Auswahl war stabil
(`halten_40` sechs Jahre in Folge, dann `ohne_regime` viermal) — das
Skript meldet hier also **nicht** die Instabilität, vor der es warnt.

**Die Versuchung, die hier ausdrücklich ausgeschlagen wird:** Zwei
Läufe, beide knapp unter der Schwelle, beide positiv — das sieht nach
einem Fall für `statistik.kombiniere_unabhaengig` (§G43) aus. **Ist es
nicht.** Beide Läufe rechnen auf denselben 15 Jahren, denselben
Symbolen, denselben Kursen. Sie sind nicht unabhängig, sondern zwei
Blicke auf dieselben Daten. Sie zu kombinieren wäre exakt die
Fehlanwendung, vor der der Docstring der Funktion warnt — dieselbe
Familie wie die Überlappung aus §B1.

### Die Kosten der eigenen Erweiterung, beziffert

Die fünf neu hinzugefügten Achsen haben das Raster von 225 auf 300
Zellen vergrößert und **die Schwelle von 3,79 auf 3,88 gehoben**.
Derselbe Walk-Forward-Wert wäre gestern gegen 3,79 gemessen worden.

Das ist kein Argument gegen die Erweiterung — es ist die Rechnung, die
§B2 beschreibt, hier zum ersten Mal in Zahlen sichtbar: **Jede
zusätzlich geprüfte Idee macht es für alle anderen schwerer.**

### Registriert

`K04_halten_40` und `K05_score_gewicht`, beide **`verworfen`**, mit
ihren t-Werten und dem Hinweis auf die vorab notierte Erwartung.

---

> **Nachtrag zur Nummerierung.** Die Commits vom 27.08.2026 tragen im
> Betreff „(G46)" und „(G48)" für die EDGAR-Infrastruktur (Verbindungs-
> Pooling, eskalierende SEC-Drosselung) — die zugehörigen §-Einträge
> hier fehlen noch, ebenso das **EDGAR-Sachergebnis** (Lauf fertig
> 28.08.2026: `insider_cluster_score` IC 0,0041 t=1,47, `insider_buyers_90d`
> t=1,44, `insider_buyers_30d` t=1,47 — alle 5/5 Jahre gleiches
> Vorzeichen, aber \|t\| < 2, weit unter der Schwelle → **kein Kandidat
> besteht**). Nachzutragen als §G46–§G48. Der folgende Eintrag ist
> deshalb §G49.

## G49. Der spekulative Historienlauf — maximale Aggression, gemessen (03.09.2026)

**Anlass:** Nutzerwunsch nach einem bewusst kompromisslosen Backtest —
die volatilsten Werte, schneller Umschlag, Hebel, Konzentration,
Daytrade — um die *Verteilung* des Endkapitals über viele Jahre zu
sehen, nicht den Mittelwert. Ausdrücklich **nur Offline auf Altdaten**,
kein Handelsbot, keine Flottenanmeldung.

### Das Werkzeug

`src/alpaca_bot/spekulativ.py` + `scripts/40_spekulativ.py` +
`spekulativ_store.py` (`spekulativ.sqlite` in `DATA_DIR`). Eigenständiger
Tag-für-Tag-Simulator (nutzt **nicht** die `Engine` — andere
Strategiefamilie), Ausführung erst zum Folgetags-Open, Stop/Ziel/Trailing
intraday gegen Tages-High/Low mit **Stop-vor-Ziel-Pessimismus** (§G3/§G4),
Kosten beidseitig über `costs.estimate_costs`, Margin-Zins auf negatives
Cash, PDT-Regel modelliert. Vier Presets (`max_aggression`,
`bounce_hunter`, `breakout_runner`, `daytrade_scalp`), jede Achse per
Flag; `--sweep`, `--walk-forward`, `--kosten-check`. Auswertung führt
`statistik.gruppierter_test` mit `horizont=haltedauer+1`, Jahrestabelle,
Block-Bootstrap und Kostensensitivität mit. Absicherung:
`tests/test_spekulativ.py`, 15 Tests (kein Lookahead via
`pit.audit_feature_function`, Kosten beidseitig, Stop vor Ziel,
Hebeldeckel, Ruin hält an, gruppierter Test genutzt, Survivorship im
Bericht, Compounding, `voll_rotation`).

**Kein Versuchszählerplatz**, solange kein Kandidat in der Flotte
angemeldet wird (BETRIEBSPLAN §4, wie der Lernlauf). Der Lauf darf eine
Idee **verwerfen, nicht abnehmen**.

### Erster echter Lauf — Preset `max_aggression`

1 Position, Hebel 3×, `voll_rotation`, Momentum \|1T\| ≥ 12 % auf 4×
Volumen, Daytrade (0 Tage halten), Stop 3×ATR. Universum: oberstes
ATR%-Terzil des Live-Universums = **202 Symbole**, **10 Jahre**, 1.538
Handelstage, Alpaca-IEX-Tagesbalken. Lauf `e7024b3f34e5`.

| | Wert |
|---|---|
| Start → Ende | 30.000 $ → **473.107 $** (+1.477 %) |
| CAGR | **+57,2 %** |
| Max. Drawdown | **−94,5 %** |
| Ertrag je Trade netto | **+0,993 %** (brutto +1,156 %) |
| Trefferquote / Profit-Faktor | 56,4 % / 1,18 |
| Kosten gesamt | 127.255 $ (bei 30.000 $ Start) |
| **Gruppierter t (236 Handelstage)** | **2,42 — unter der Schwelle 2,88 → kein Befund** |

**Warum die Zahl trotz +57 % CAGR nichts belegt:**

1. **2 von 8 Jahren positiv.** 2021/22/23: −16 % / −32 % / −54 %. Dann
   2024 **+1.204 %**, 2025 **+431 %**, 2026 −12 %. Der ganze Lauf hängt an
   zwei Jahren — dasselbe Muster wie §G11.
2. **Kosten kippen das Vorzeichen** (echte Neuläufe, `--kosten-check`):
   0 bps → CAGR +90 %; 10+6 bps → +32 %; **25+10 bps → −8 %, Endkapital
   18.000 $** (unter Start). §G44 hat für genau dieses Segment 25–270 bps
   gemessen, nicht 5. Im realistischen Kostenbereich verliert die
   Strategie.
3. **Ruin ist der wahrscheinliche Pfad.** Block-Bootstrap (5-Tage-Blöcke,
   5.000 Ziehungen): p05 = 0,11× / p50 = 16,7× / p95 = 2.283×.
   P(Endkapital < Start) = 17 %, **P(zwischenzeitlich −80 %) = 29 %**. Der
   16×-Median ist der Überlebenspfad, nicht der Erwartungswert.
4. **Survivorship:** 65 % der Symbole über 10 Jahre fehlen im Datensatz —
   und eine Aggressiv-Long-Regel wird von genau den fehlenden Pleiten
   getroffen. Die absolute Zahl ist eine **Obergrenze**.

**Was es sagt:** Der Ertrag je Trade (+0,99 %) ist rund 9× so groß wie
der der Umkehrstrategie (+0,11 %, §A) — die Bewegung auf den volatilsten
Werten ist real größer. Aber: statistisch kein Befund (t 2,42 < 2,88
über 10 Jahre), bei realistischen Kosten negativ, mit −94,5 % Drawdown.
Deckt sich mit `TAKTIKWECHSEL` §7 und der Basisrate §B6 (0 von rund 68).

### Sweep über Hebel × Haltedauer × Positionszahl (Lauf `9fb9bb0d4a5d`)

18 Konfigurationen, dieselben 203 Symbole / 10 Jahre. Zufallsmaximum bei
18 Versuchen: t ≈ 2,90.

| Hebel | Halten | CAGR | Max-DD | t (grp) | p05 | p50 |
|---:|---:|---:|---:|---:|---:|---:|
| 2 | **0 T** | **+58,3 %** | −79 % | 2,41 | 0,74× | 15,8× |
| 3 | 0 T | +57,2 % | −95 % | 2,32 | **0,12×** | 15,1× |
| 1 | 0 T | +29,6 % | −50 % | 2,23 | **1,14×** | 4,8× |
| 1 | 3 T | +8,1 % | −80 % | 1,50 | 0,22× | 1,55× |
| 2 | 3 T | −18,8 % | −99 % | 1,39 | 0,00× | 0,31× |
| 3 | 3 T | **−100 % (Ruin)** | −99 % | −1,5 | — | — |

**Drei klare Muster, keiner davon ein Befund:**

1. **Der Effekt ist ein Ein-Tages-Ereignis.** Jede `haltedauer=3`-Variante
   verliert oder geht in den Ruin — der Sprung dreht in den Folgetagen.
   Momentum auf den volatilsten Werten über mehrere Tage halten ist
   strukturell verlustbringend. Das ist die deutlichste Aussage des
   Laufs.
2. **Hebel über 2× kauft nur Streuung.** Hebel 2 schlägt Hebel 3 im CAGR
   (+58,3 vs +57,2 %) bei p05 0,74× statt 0,12× — mehr Hebel senkt das
   zeitgewichtete Ergebnis, weil der tiefere Drawdown den Zinseszins
   frisst. Hebel 1 ist die einzige Stufe, deren 5 %-Bootstrap-Pfad
   (p05 1,14×) über dem Startkapital endet.
3. **`max_positionen` war wirkungslos** — CAGR identisch für 1/5/15.
   Ursache: das Preset pinnt `groessen_modus=voll_rotation` (genau eine
   Position). Eine echte Breiten-Achse braucht `--groessen-modus gleich`.

**Walk-Forward: t = −0,13.** Die historisch beste Konfiguration je Jahr
zu wählen trägt nicht ins nächste Jahr (3/5 Jahre Vorsprung, mittlere
Diff −12,9 %). 2024 hätte die Auswahl Hebel 1 genommen und +334 pp
liegen gelassen, 2025 Hebel 3 und Glück gehabt.

### Konsistenzpflicht: „jedes Kalenderjahr muss Gewinn machen" (03.09.2026)

**Anlass:** Nutzervorgabe — nicht die Gesamtrendite zählt, sondern es
darf **kein einziges Minusjahr** geben (egal ob 1, 5 oder 10 Jahre
betrachtet). Gebaut als `--min-jahr-rendite X` (Filter + zweite
Rangliste + Walk-Forward nur über die Bestandenen). Test:
`tests/test_spekulativ.py::TestKonsistenzpflicht`.

**Reversal/Bounce (24 Konfigs, Lauf `46abd5970527`):** alles flach oder
negativ, Walk-Forward t = +0,09. Keine erfüllt die Pflicht. Erledigt.

**Momentum-Daytrade + Breite (27 Konfigs, Lauf `00ae86691195`):** 11 von
27 erfüllen die Pflicht **in-sample** (8/8 Jahre positiv). Sie clustern
um ein Rezept: Auslöser **+10 %** (nicht 6 %, nicht 15 %), 10 Positionen
gleichgewichtet, Haltedauer 0, Hebel skaliert nur die Rendite (1,0 →
CAGR +7,6 % / 1,5 → +11,4 % / 2,0 → +15,2 %; Max-DD −9/−14/−18 %).
Walk-Forward über die 11: **5/5 Jahre Vorsprung, t = +2,62** — der beste
Walk-Forward-Wert des Projekts, aber weiter unter 2,88.

**Der Detaillauf entzaubert es** (`76a98dc5fc10`, 10 Pos / Hebel 1 /
+10 %):

| Prüfung | Ergebnis |
|---|---|
| Gruppierter t je Trade (541 Handelstage) | **1,60** (naiv 3,02) — keine Kante |
| Kosten-Check echte Neuläufe | 5+3 bps: +7,6 % · 10+6: +5,0 % · **25+10: −1,0 %** |
| **Ohne `--hochvola`-Vorauswahl** (595 Symbole, `1225dcc05cf1`) | CAGR **+4,3 %**, **5/10 Jahre positiv** (2021: −5,6 %), **Konsistenzpflicht VERFEHLT**, t je Trade **0,65**, bei 25 bps −3,4 % |

**Warum die Konsistenz nicht trägt:**

1. **Sie hing an der Universumsauswahl.** `--hochvola` nimmt das oberste
   ATR%-Terzil nach *jüngster* Vola — ein mildes §G11-Auswahlartefakt.
   Ohne diesen Schritt ist 2021 ein −5,6 %-Jahr und die Pflicht
   durchgefallen.
2. **Es gibt keine Kante je Trade.** Der gruppierte t fällt von 1,60 auf
   **0,65**, sobald das Universum ehrlich gewählt wird. „Jedes Jahr
   knapp positiv" ist die **Niedrigvarianz-Signatur** von 966 winzigen
   Tageswetten auf 10 Positionen, nicht ein Beleg für Ertrag.
3. **Kosten und Survivorship erklären den Rest.** Bei 25 bps (§G44s
   Untergrenze für dieses Segment) ist beide Fassungen negativ.
   Survivorship trägt zusätzlich +2–4 pp/Jahr Schein-Rendite bei.

### Gesamturteil §G49

Über 10 Jahre, ~90 Varianten und drei Strategiefamilien (Momentum,
Reversal, Konsistenz-gefiltert) übersteigt **keine** die
Zufallsschwelle. Der Ertrag je Trade ist bei roher Kostenannahme größer
als bei der Umkehrstrategie, aber: statistisch nicht von Rauschen zu
trennen (bester ehrlicher t = 0,65–1,60), an wenigen Jahren hängend, bei
realistischen Kosten negativ, mit Ruin als wahrscheinlichem Pfad ab
Hebel 2 und jeder Haltedauer über 0. Die „jedes-Jahr-positiv"-Konfig war
ein Artefakt aus Universumsauswahl + optimistischen Kosten +
Survivorship.

Der einzige verwertbare *strukturelle* Nebenbefund: **der Momentum-Sprung
auf volatilen Werten ist ein Ein-Tages-Ereignis** — jede Haltedauer über
0 verliert oder ruiniert. Spiegelbild zu §A („Umkehr-Effekt lebt auf
3–5 Tagen"). Braucht keinen Flottenplatz.

**Das Werkzeug bleibt** für weitere Verfeinerung (`--quelle yf` für
20 Jahre inkl. 2008/2015/2018, `--gap-pct`, `--ausloeser-ntage`,
kausaler Vola-Filter). **Kein Kandidat geht in die Flotte** — der Zähler
bleibt bei 0 von rund 68.

---

## G50. Der DQN-Agent zeigt kein Timing-Koennen (03.09.2026)

**Anlass:** erneute Nutzerforderung nach einem selbstlernenden System
(„RL, mit so vielen Faktoren wie möglich, alles ausprobieren, gegen alle
Daten bis gestern trainieren"). §G15 hatte das am 22.08.2026 bereits
verneint — dort aber mit einem **GBM auf der Ranking-Aufgabe**. Hier
zum ersten Mal der **tatsächliche DQN-Agent** aus `src/alpaca_bot/rl/`
(Double-DQN, Zielnetz, Replay, Huber; Umgebung mit Gebühren/Slippage je
Positionsänderung, PDT, Folge-Bar-Ausführung), Walk-Forward über 10
Jahre, 4 Fenster, gegen die fest verdrahtete Zufalls-/Konstant-Messlatte
(`scripts/08_train_rl.py`).

| Symbol | Timing-Perzentil (>= 95 nötig) | Urteil |
|---|---:|---|
| SPY | 42 | kein Timing-Können |
| QBTS | 19 | kein Timing-Können |
| CYTK | 70 | kein Timing-Können |
| SYRE | 85 | „schwacher Hinweis, nicht belastbar" |

**0 von 4 zeigen Timing-Können.** SYREs 85 stammt aus einem einzigen
Fenster mit +3.216 % Rendite bei Timing-Perzentil 50 — der auswendig
gelernte Kurssprung, vor dem der Modul-Docstring ausdrücklich warnt; die
beiden anderen SYRE-Fenster (Perzentil 89 und 100) trugen fast keine
Rendite. Das Muster ist Rauschen, kein Signal.

**Damit ist §G15 ein zweites Mal bestätigt, jetzt mit dem echten
RL-Agenten.**

### Der Querschnitt-DQN (Breite statt Tiefe) — auch negativ (03.09.2026)

Die im ersten Entwurf noch offen gelassene Variante — ein Agent lernt
aus vielen Symbolen gleichzeitig (IR = IC·√BR, §G31/§G43) — gebaut als
`src/alpaca_bot/rl/pooled.py` (Walk-Forward über gemeinsamen Kalender,
gepoolter Scaler nur aus Train, Urteil verlangt Median-Timing ≥ 95 über
Symbole UND ≥ 50 % Symbole mit Können, damit kein Glückstreffer trägt).
Test: `tests/test_rl_pooled.py`, 7 Tests, darunter der SYRE-Fall.

Lauf `lauf_0_40sym`: 40 volatilste Werte, 10 Jahre, 3 Fenster, ein
gemeinsamer Agent, 507.000 Lernschritte.

| | Wert |
|---|---:|
| Symbol×Fenster bewertet | 113 |
| Median Agent-Rendite (OOS) | +15,2 % |
| schlägt konstante Position | **49 %** (Münzwurf) |
| **Median Timing-Perzentil** | **14** (≥ 95 nötig) |
| **Anteil Symbole mit Timing-Können** | **3 %** (3/113; ≥ 50 % nötig) |

Die 3 „Treffer" sind das bekannte Muster: COHR/LITE bei Perzentil 98/97
mit ~0 % Beteiligung und ~0 % Rendite (der Agent stand flach), TSLA
2025/26 bei 96 mit +55 % (auswendig gelernter Momentum-Lauf). MSTR
+303 % trägt Perzentil 83 — riesige Rendite, kein Timing.

### Fünf Wege, ein Ergebnis

| Methode | § | Stichprobe | Ergebnis |
|---|---|---|---|
| GBM-Ranking | G15 | 1.101 Handelstage | schlechter als der Score |
| 20-Achsen-Lernlauf | G45 | 15 J, 3.768 Tage | 0 von 19 |
| Spekulativ-Sweep | G49 | ~90 Konfigs, 10 J | keiner über der Schwelle |
| Einzel-DQN | G50 | 4 Symbole, WF | 0 von 4 Timing |
| **Querschnitt-DQN** | G50 | **40 Symbole, WF** | **3 % Timing, Münzwurf gegen konstant** |

**Der Engpass ist das Signal-Rausch-Verhältnis, nicht das Modell.** Das
Messgerät löst 0,0378 %/Tag auf, entscheidend wären 0,0065 %/Tag
(§G31/§G43). Größeres Netz, mehr Daten, mehr Breite — nichts davon
schließt diese Lücke; Survivorship (§G11) gibt dem Renditemaximierer
sogar einen Phantom-Vorteil zum Auswendiglernen. **Die Lernfrage ist
damit beantwortet.** Neue Information müsste von außerhalb der Kursdaten
kommen (§C) — und Insider/EDGAR (§G, insider_cluster t=1,47) hat das
bereits verneint. Der nächste konkrete Schritt bleibt der aus
`BETRIEBSPLAN` §3.4: eine **zweite, nicht-IEX-Datenquelle** für die
Spannen-Messung — siehe §G51.

---

## G51. Die Spanne ist doch messbar — konsolidierte NBBO: ~12 bps (03.09.2026)

**§G44 hielt fest, mit dem freien IEX-Feed sei die Spanne nicht messbar
(Median 268 bps = 2,7 %, keine Monotonie über die Dezile).** Beim
Nachsehen des Alpaca-Kontos: **`delayed_sip` ist freigeschaltet** — die
konsolidierte NBBO über alle Börsen, ~15 Minuten verzögert, kostenlos.
Genau die „zweite Quelle", die §G44 und `BETRIEBSPLAN` §3.4 fordern.

`scripts/37_spannen_messen.py --feed delayed_sip` (neu: `--feed`-Schalter,
feed-abhängige Frische- und Eröffnungsfilter, `latest_quotes(feed=…)`).
Drei Aufnahmen, 3.582 Quotes, 1.194 Symbole, Eröffnungs-20-Min
ausgeschlossen (Verzögerung eingerechnet), veraltete Quotes verworfen:

| | delayed_sip (NBBO) | IEX (§G44) |
|---|---:|---:|
| 10 % | 3,2 bps | 4,9 |
| 25 % | 5,9 | 11,9 |
| **Median (Dezile 1–6)** | **12,2 bps** | 268,0 |
| 75 % | 23,7 | 722 |
| Dezile 1→6 | 6,9 / 12,1 / 11,9 / 14,4 / 16,9 / 17,7 — **monoton** | 205 / 428 / 435 / 374 / 232 / 54 |

Stabil über die drei Aufnahmen (12,4 / 12,0 / 12,2). Die Monotonie
(liquider = enger) ist der Beleg, dass es eine echte Spannenverteilung
ist — genau das, was IEX vermissen ließ. Der Faktor 22 zwischen den
Feeds ist die Feed-Lücke (IEX sieht ~2 % des Volumens, §G29), nicht der
Markt.

### Was das bedeutet — §3.4s vorab festgelegte Tabelle

| Spanne | Breakeven | annualisiert |
|---:|---:|---:|
| 3,4 bps | 0,110 % (= Vorsprung) | ±0 |
| 5,0 (Annahme) | 0,142 % | −1,6 %/Jahr |
| **12,2 (gemessen)** | **~0,27 %** | **≈ −8 %/Jahr** |

12 bps liegt in §3.4s Band **„10–20 bps: Annahme deutlich zu günstig.
Kein Faktorfund dieser Größenordnung schließt das. Entweder radikal
längere Haltedauer oder die Strategie ist in dieser Form nicht
handelbar."** Die Asymmetrie-Klausel (§3.4: „über 20 bps kann IEX sein")
greift **nicht** — die Zahl ist die konsolidierte NBBO, unter 20, monoton
und über drei Aufnahmen stabil.

**Folgen:**

1. **Der zentrale Konflikt aus §A verschärft sich, statt sich zu lösen.**
   Vorsprung +0,110 %/Trade gegen jetzt ~0,27 % Rundlauf-Breakeven. Die
   Umkehrstrategie bei 5 Tagen Haltedauer / ~50 Umschlägen ist **nicht
   kostentragfähig** — nicht knapp, sondern klar.
2. **Der Hebel ist der Umschlag, nicht der nächste Faktor** (§3.4,
   `TAKTIKWECHSEL` §2). Eine Haltedauer, die den Vorsprung *je Trade*
   über ~0,27 % hebt, ist die einzige offene Richtung — und §G45 fand
   dafür keine Kante (40 Tage nicht besser als 10).
3. **`spekulativ.py` (§G49) ist damit erledigt.** Die Daytrade-Rezepte
   mit 100+ Trades/Jahr kippten schon im `--kosten-check` bei 25 bps ins
   Minus; bei realen 12 bps sind sie tief negativ.
4. **`costs.py` wird NICHT angefasst.** Ein geänderter Kostenparameter
   bewertet jede laufende und vergangene Messung neu — eigene,
   vorangemeldete Entscheidung, keine Nebenwirkung dieser Messung. Die
   Voranmeldung steht jetzt in `BETRIEBSPLAN` §3.5: Wechsel erst nach
   ≥ 4 Handelstagen stabiler Messung **und** nach dem 10.10.2026
   (B11-Basis zuerst), dann voller Neulauf.

**Weitermessen:** LaunchAgent `de.local.alpacaspannen` (nicht im Repo,
`~/Library/LaunchAgents/`) sammelt ab 04.09.2026 werktags 16:15 Ortszeit
6 Aufnahmen je Tag in `spannen.sqlite`. Auswertung:
`scripts/37_spannen_messen.py --bericht`. Entfernen, wenn genug Tage da
sind: `launchctl bootout gui/$(id -u)/de.local.alpacaspannen`.

**Absicherung:** `scripts/37_spannen_messen.py` migriert die `feed`-Spalte
idempotent, Bericht vergleicht beide Feeds. 596 Tests grün.

---

## G52. Trendfolge/Dual-Momentum auf ETFs — defensiv, aber kein Renditevorsprung (04.09.2026)

**Anlass:** der Strategie-Familien-Wechsel (`docs/TRENDBOT.md`). Der
bisherige Ansatz (kurzfristige Aktiensignale) ist ausgeschöpft; Zeit-
Serien-Momentum auf liquiden ETFs umgeht die beiden Killer Spanne (§G51)
und Survivorship (§G11).

**Gebaut:** `src/alpaca_bot/trend.py` + `scripts/43_trend.py` +
`tests/test_trend.py` (10 Tests). Drei Strategien (`tsmom`, `dualmom`,
`ma_filter`), monatliches Rebalancing, Kosten beidseitig auf den
Turnover, Vol-Targeting-Overlay. yfinance-Total-Return, 7 ETFs (EFA fiel
bei einem Netz-Timeout aus), gemeinsame Historie **2008–2026**.

### Ergebnis — beste Variante (`dualmom`, 9-Monats-Lookback, 10 % Vol-Ziel)

| | Strategie | 60/40 | SPY B&H |
|---|---:|---:|---:|
| CAGR | 7,5 % | 8,7 % | 11,9 % |
| Sharpe | **0,88** | 0,79 | 0,67 |
| Max Drawdown | **−15,8 %** | −30,8 % | −51,5 % |
| Calmar | 0,48 | 0,28 | 0,23 |

Kostendrag nur 0,15 %/Jahr (Turnover 5×). Die 10 %-Vol-Ziel-Varianten
clustern alle bei Sharpe 0,83–0,88 / −15 % DD — konsistent, kein
Parameter-Glückstreffer. 2008: **+8,4 %** (60/40 −17 %). 2022: **−1,7 %**
(60/40 −16 %). Die defensive Eigenschaft ist real.

### Das Gate (`TRENDBOT` §5) — vorab festgelegt, 2 von 4

| Kriterium | Ergebnis |
|---|---|
| 1. schlägt 60/40 gesamt **und** ≥ 60 % Jahre | **NEIN** — +277 % vs +361 %, nur 37 % der Jahre |
| 2. Max-Drawdown < SPY B&H | **JA** — −16 % vs −51 % |
| 3. Walk-Forward-Vorsprung stabil | **NEIN** — t = −1,34, 5/16 Jahre, im Mittel −3,0 %/Jahr gegen 60/40 |
| 4. überlebt doppelte Kosten (4 bps) | **JA** — CAGR +7,3 % bei 4 bps, +7,1 % bei 8 |

**Phase 1 nicht bestanden** (Kriterium 1 und 3). Kein Renditevorsprung
gegen ein simples 60/40, und die Lookback-Auswahl trägt **nicht** ins
nächste Jahr. Kosten sind hier nicht das Problem — der Effekt selbst ist
zu schwach.

### Einordnung

Das ist das **bislang kohärenteste** Ergebnis des Projekts: eine
Strategie mit klarem Risiko-Nutzen (Sharpe über beiden Benchmarks,
Drawdown ein Drittel von SPY, positiv in 2008 und 2022). Aber sie ist
**risikoärmer, nicht besser** — sie gibt Rendite gegen Ruhe ab. Auf
einem Fenster (2008–2026), das von einem historischen Anleihen-
Bullenmarkt dominiert ist, ist genau das erwartbar: 60/40 ist dort
außergewöhnlich schwer zu schlagen.

**Nicht post-hoc umgewidmet:** Das Gate stand vor der Messung und wird
nicht auf „Sharpe statt Rendite" geändert — das wäre §B2/§G45. Zwei
ehrliche Anschlüsse:

1. **Fairerer Test der Familie:** ETFs reichen nur bis 2004–2008. Die
   stärkste Trendfolge-Evidenz liegt in den 1970er–2000er Jahren.
   Ein Lauf auf Index-Total-Return-Reihen über 50+ Jahre wäre der
   eigentliche Test — steht noch aus.
2. **Andere Zielsetzung:** Wer eine *defensive* Allokation für das
   Live-Konto will (kompoundiert ~7,5 %/Jahr, verliert im Crash ein
   Drittel dessen, was SPY verliert), hat sie hier. Das ist eine eigene,
   vorab zu treffende Produktentscheidung — kein bestandenes Gate.

---

## G53. Jahres-Aktienauswahl — 22,8 % CAGR, die fast ganz Survivorship ist (04.09.2026)

**Anlass:** Nutzeridee — Anfang jedes Jahres die aussichtsreichsten
Aktien wählen, ganzes Jahr halten, bei extremem Verlauf raus. Sehr wenige
Trades → die gemessene Spanne (§G51) zählt kaum.

**Gebaut:** `src/alpaca_bot/jahresbot.py` + `scripts/44_jahresbot.py` +
`tests/test_jahresbot.py` (7). Signale `momentum` (12-1-Monat),
`tief_vola`, `momentum_vola`; Top-N, jährliches Rebalancing,
Verlust-Stop, „Gewinner laufen lassen". Kosten mit der echten
NBBO-Spanne (12+3 bps) beidseitig, nur bei tatsächlichem Kauf/Verkauf.
Beim Bau ein RateLimiter-Bug behoben (`acquire(n)` mit n über dem
Minutenlimit → IndexError; `tests/test_ratelimit_burst.py`).

### Der Lauf — beste Variante (`momentum_vola`, Top-20, kein Stop)

Universum `universe.load_universe(500)` (heute liquideste US-Werte),
yfinance-Total-Return, **2005–2026, 21 Rebalances, 492 Symbole**.

| | Wert |
|---|---:|
| CAGR | **22,8 %** (SPY B&H ~11,3 %) |
| Sharpe / Sortino | 0,83 / 1,05 |
| Max Drawdown | **−60,9 %** |
| schlägt SPY | 14 von 22 Jahren (64 %) |
| Walk-Forward (Regel fix, Jahr für Jahr gegen SPY) | mittlere Diff **+15,8 %/Jahr, t = +2,14** |

Auf den ersten Blick das beste Ergebnis des Projekts. **Es hält trotzdem
nicht.**

### Warum die Zahl nicht trägt

1. **Survivorship auf Maximum.** Der Bericht sagt es selbst: **89 % des
   Universums fehlen** über 21 Jahre (~4.472 damals → 492 heute). Top-20
   Momentum aus den *heute* 500 liquidesten Werten zu picken heißt: das
   Universum enthält garantiert Nvidia, Apple & Co. und **keine** der
   Tausenden, die auf null gingen. Das ist §G11 und §B4 kombiniert, in
   voller Stärke. Der akademische Cross-Sectional-Momentum-Aufschlag
   liegt bei ~4–8 %/Jahr *mit* Point-in-Time-Universum — hier sind es
   +15,8 %/Jahr über SPY. Der Löwenanteil der Differenz ist die
   Verzerrung, nicht das Signal.
2. **An wenigen Jahren aufgehängt.** 2019 +52 %, 2020 +91 %, 2024
   **+158 %**, 2026 +67 %. 2024 allein trägt +133 pp gegen SPY. Genau das
   Muster aus §G11/§G49 („der ganze Vorsprung hängt an einem Teiljahr").
3. **Kein Krisenschutz.** 2008: −48 % gegen SPY −36 % — *schlechter*.
   Der −25 %-Stop drückt den Max-Drawdown von −61 auf −43 % und die CAGR
   auf ~18 %, hilft aber im Vorzeichen nicht.
4. **t = 2,14 < 2,90** (Zufallsmaximum bei 18 Varianten). Nach der
   eigenen Hürde des Projekts **kein Befund** — und das ohne
   Berücksichtigung des Survivorship-Rückenwinds, der t weiter drücken
   würde.

### Die saubere Version derselben Idee: §G52

Jährliches Momentum auf **Anlageklassen-ETFs** (§G52, `dualmom`) hat
keine Survivorship-Verzerrung. Ergebnis dort: Sharpe 0,88, −16 %
Drawdown — aber **kein Renditevorsprung** gegen 60/40, Walk-Forward
negativ. Der Mehrertrag der Einzelaktien-Version über die ETF-Version
**ist** der Survivorship- plus Konzentrationsaufschlag, sichtbar gemacht.

### Was daraus folgt

Einzelaktien-Jahresauswahl lässt sich mit freien Daten **nicht
validieren** — es bräuchte ein Point-in-Time-Universum (kostenpflichtig).
§B4 ist eindeutig: ein guter Probelauf beweist nichts (PEAD: t=6,7 auf
60 Symbolen, tot auf 800). Diese 22,8 % CAGR sind die eindrücklichste
Illustration von §G11 im ganzen Register — **kein live-fähiger
Kandidat.** Kein `costs.py`-Bezug, kein Zählerplatz.

---

## G54. Die gemessene Spanne dreht das Vorzeichen der Strategie (11.09.2026)

**Anlass:** Zwischenbilanz, von der geplanten 12.09. auf den 11.09.
vorgezogen (der 12.09. ist ein Samstag, kein Handelstag).

### Zuerst: die Datengrundlage aus §3.5 ist erfüllt

`BETRIEBSPLAN` §3.5 hat am 04.09.2026 vorab festgelegt, wann der
`costs.py`-Wert gewechselt werden darf: **mindestens 4 Handelstage** und
**Spannweite der Tagesmediane < 4 bps**. Beides liegt jetzt vor.

| Handelstag | Aufnahmen | Median Dezile 1–6 |
|---|---:|---:|
| 03.09.2026 | 3 | 12,20 bps |
| 04.09.2026 | 6 | 12,23 bps |
| 08.09.2026 | 6 | 11,73 bps |
| 09.09.2026 | 6 | 11,51 bps |
| 10.09.2026 | 6 | 12,85 bps |

**5 Handelstage, Spannweite 1,34 bps, Median der Tagesmediane 12,2 bps.**
Feed `delayed_sip` (konsolidierte NBBO), Quotes < 20 min alt, erste
20 Minuten nach Eröffnung ausgeschlossen. Die Momentaufnahme aus §G51
war also keine: der Wert ist stabil.

### Der Test, den §3.4 für diesen Fall vorgesehen hat

`scripts/10_simulate.py` nimmt `--spread` entgegen. **Zweimal derselbe
Lauf**, Live-Konfiguration, 1.201 Symbole, 8 Jahre, nur die Spanne
verändert — `costs.py` wurde dabei **nicht** angefasst:

| | 5,0 bps (Annahme) | **12,2 bps (gemessen)** |
|---|---:|---:|
| CAGR über 8 Jahre | +1,95 % | **−2,84 %** |
| Erwartungswert je Trade | +0,07 % | **−0,10 %** |
| Rendite je Trade, gruppiert und marktbereinigt | +0,0245 % (t = 0,14) | −0,1229 % (t = −0,68) |
| Kosten gesamt | 6.114 $ | 8.649 $ |
| Trades | 3.682 | 3.681 |
| Trefferquote | 50,1 % | 48,6 % |

**Das Vorzeichen kippt.** Und es kippt auf einem Universum, dessen
Survivorship-Bonus derselbe Lauf mit **+2 bis +4 Prozentpunkten pro
Jahr** beziffert — die ehrliche Zahl liegt also eher bei −5 bis −7 %/Jahr.

### Der Rundlauf-Breakeven, neu gerechnet

`costs.breakeven_move_pct`, Slippage 2 bps wie in §3.4:

| Spanne | Breakeven je Rundlauf | gegen +0,110 % | bei ~50 Rundläufen p. a. |
|---:|---:|---:|---:|
| 5,0 bps (Annahme) | 0,142 % | +0,032 pp | −1,6 %/Jahr |
| **12,2 bps (gemessen)** | **0,287 %** | **+0,177 pp** | **−8,8 %/Jahr** |

Der Vorsprung müsste **0,287 % je Trade** betragen. Gemessen sind
0,110 % — **Faktor 2,61 zu wenig**. §A sprach von +29 %, die fehlen.
Es sind 161 %.

### Keine Haltedauer schließt die Lücke

`TAKTIKWECHSEL` §3 verlangt genau diese Rechnung („Vorsprung je Trade
als Funktion der Haltedauer, ausgewertet je Trade statt als
Endrendite") und sie war nie gemacht. Aus dem 15-Jahre-Lernlauf
`d44ad22a8731` (20 Achsen, 790 Symbole) rekonstruiert — Bruttoertrag je
Rundlauf = Jahresrendite / Rundläufe je Positionsplatz, zuzüglich der in
der Simulation bereits abgezogenen Kosten (5 bps Spanne + 3 bps
Slippage = 0,162 % je Rundlauf):

| Achse | Rundläufe je Platz p. a. | Brutto je Rundlauf | netto bei 12,2 bps (Schwelle 0,307 %) |
|---|---:|---:|---:|
| `halten_40` | 31,2 | 0,296 % | **−0,011 pp** |
| `halten_lang` (10 T) | 34,1 | 0,282 % | −0,025 pp |
| `halten_20` | 31,1 | 0,274 % | −0,033 pp |
| `ohne_regime` | 56,9 | 0,288 % | −0,018 pp |
| `basis` (5 T) | 49,1 | 0,182 % | −0,125 pp |
| `halten_kurz` (3 T) | 71,4 | 0,207 % | −0,100 pp |

**Keine der 20 Achsen trägt.** Die beste (`halten_40`) verfehlt die
Schwelle um 0,011 Prozentpunkte — und das vor Abzug des Survivorship-
Bonus. `halten_20` und `halten_40` erzeugen fast identisch viele Trades
(467,2 gegen 467,3 p. a.): ab etwa 20 Tagen bindet der Zeitausstieg
kaum noch, die Kurve läuft flach aus. Ein noch längerer Horizont ist
deshalb keine offene Frage mehr.

> **Vorbehalt zur Rekonstruktion.** Die Bruttospalte ist gerechnet, nicht
> direkt gemessen: Der Lernlauf speichert nur Jahresrendite und
> Trade-Zahl, nicht `erwartungswert_pro_trade`. Die Näherung setzt
> 15 durchgehend besetzte Positionsplätze an und verkettet arithmetisch
> statt geometrisch. Die **direkt gemessenen** Zahlen sind die der
> Tabelle darüber (`basis`, 8 Jahre, zwei Läufe) — und sie zeigen
> dasselbe Vorzeichen.

### Das Einstellungskriterium greift NICHT — genau gelesen

`TAKTIKWECHSEL` §7 verlangt **beides**:

| Bedingung | Stand |
|---|---|
| Spanne **über 15 bps**, durch Nicht-IEX-Quelle bestätigt | **NEIN** — 12,2 bps, bestätigt, aber unter 15 |
| Keine Haltedauer 5–40 Tage über der Kostenschwelle | **JA** — siehe Tabelle |

**Eines von zwei.** Das Kriterium ist damit nicht erfüllt, und es wird
nicht nachträglich auf „eines reicht" gelockert (§B2). Festgehalten ist
aber, dass der Puffer nur noch aus 2,8 bps Spanne besteht.

### Was daraus NICHT folgt

* **Kein neuer Wert in `costs.py`.** §3.5 hat die Reihenfolge vorab
  festgelegt: erst die B11-Entscheidung am 10.10. mit der alten Basis,
  dann der Wechsel. Diese beiden Läufe haben `costs.py` nicht berührt —
  sie sind Übergabeparameter an `simulate.run`, keine Änderung.
* **Keine Änderung an der Handelslogik.** Gilt unverändert bis 10.10.
* **Keine Stilllegung des Umkehr-Bots.** §7 ist nicht erfüllt.

### Was daraus folgt

Der Engpass ist ab jetzt benannt und beziffert: **die Strategie muss
ihren Vorsprung je Trade um Faktor 2,6 heben, und keine der 34 bisher
gemessenen Achsen tut das.** Das ist die belastbarste negative Aussage,
die das Projekt bisher hat — und sie stützt die Produktentscheidung vom
04.09. (`TRENDBOT` §5b), den Schwerpunkt auf die ETF-Allokation zu legen,
ohne dass dafür ein Gate umgangen werden musste.

---

## G55. `evaluate_outcomes` wertet nur 300 von 1.031 Symbolen aus (11.09.2026)

**Der Fund.** Der Tagesbericht meldete „60 Entscheidung(en) ohne
bewertetes Ergebnis". Nachgesehen: seit dem 02.09.2026 hat **keine
einzige** Entscheidung mehr ein 5-Tage-Ergebnis bekommen.

```
02.09.  35 Entscheidungen,  35 ohne Ergebnis
03.09.  54                  54
04.09.  61                  61
08.09.  13                  13
09.09.  51                  51
10.09.  12                  12
```

**Die Bewertung läuft.** `daemon._maybe_evaluate_outcomes` lief zuletzt
am 10.09.2026 um 14:02 UTC und schrieb 93 Zeilen. Der Fehler steckt in
der Auswahl der Symbole, für die Kurse geladen werden:

```python
symbols = (vorrang + rest)[:300]     # daemon.py:335
```

`rest` ist **alphabetisch sortiert**. Bei 1.031 Symbolen in `decisions`
wird ab `DPZ` nichts mehr geladen — **731 Symbole, 71 %, sind
systematisch unerreichbar.**

**`vorrang` fängt das nicht auf.** Die Vorrangliste sammelt
Entscheidungen, zu denen *gar kein* Ergebnis existiert:

```python
fehlend = decisions[~decisions["decision_id"].isin(offen["decision_id"])]
```

Der Vergleich läuft über `decision_id`, **nicht über (decision_id,
horizon)**. Eine Entscheidung, deren 1- und 3-Tage-Ergebnis bereits
steht und der nur der 5-Tage-Wert fehlt, gilt damit als erledigt. Genau
das ist der Normalfall: Am Tag der Bewertung sind 1 und 3 Tage
verfügbar, 5 noch nicht — und am nächsten Tag fällt das Symbol durch
das alphabetische Raster. `vorrang` hat deshalb nur **18** Einträge
statt der nötigen Hunderte.

**Der Umfang, gemessen:**

| | Zahl |
|---|---:|
| Live-Entscheidungen gesamt | 685 |
| davon ohne 5-Tage-Ergebnis | **277 (40 %)** |
| davon Symbol außerhalb des 300er-Fensters | **128 — dauerhaft unerreichbar** |

**Das ist derselbe Fehler zum zweiten Mal.** Der Kommentar über der
Zeile beschreibt ihn bereits: „Früher stand hier `sorted(...)[:200]` —
eine rein alphabetische Auswahl. Solange weniger als 200 Symbole
zusammenkommen, fällt das nicht auf (aktuell 157); darüber hinaus würde
alles ab etwa ‚T‘ systematisch NIE ausgewertet." Die Reparatur hob die
Grenze auf 300 und fügte `vorrang` hinzu — aber `vorrang` prüft die
falsche Schlüsselgröße, und aus 157 Symbolen sind 1.031 geworden.

**Folge.** `journal.decision_quality()` — laut eigenem Docstring „die
wichtigste Auswertung im ganzen System" — rechnet auf 60 % der
Live-Entscheidungen. Die Auswahl ist alphabetisch und damit
voraussichtlich unkorreliert mit der Rendite: es ist ein Verlust an
Trennschärfe, keine Verzerrung in eine Richtung. Bei einer ohnehin
knappen Live-Stichprobe ist das trotzdem teuer.

### Behoben am selben Tag (11.09.2026)

1. `daemon._symbole_mit_offenen_horizonten()` vergleicht jetzt das **Paar**
   `(decision_id, horizon)`. Die Horizonte stehen als `HORIZONTE_LIVE`
   am Modul, damit die Symbolauswahl weiß, was sie offenhalten muss —
   vorher stand die Zahlenreihe nur am Aufruf.
2. Die Obergrenze liegt bei `MAX_SYMBOLE_JE_LAUF = 1.500` und ist ein
   Sicherheitsnetz, kein Filter: Greift sie doch, trifft sie zuerst die
   **fertigen** Symbole. Ein Symbol mit offenem Horizont kann sie nicht
   kosten — genau das prüft ein eigener Test.
3. **Zweite Fundstelle, beim Reparieren entdeckt.**
   `scripts/13_tagesbericht.py:121` trug noch die *Urfassung* des
   Fehlers: `sorted(...)[:200]`, rein alphabetisch, ohne Vorrangliste.
   Im Daemon war sie längst ersetzt, im Bericht nicht. Bei 1.046
   Symbolen fiel dort alles ab etwa „C" heraus. Ebenfalls auf die neue
   Methode gezogen.
4. Regressionstest `tests/test_ergebnisfenster.py`, 6 Fälle. Er enthält
   die **alte Logik als Vergleichsfunktion** und prüft ausdrücklich, dass
   sie durchfällt — ein Test, den auch der kaputte Code besteht, sichert
   nichts.

**Wirkung, gemessen nach dem Nachtrag:**

| | vorher | nachher |
|---|---:|---:|
| Symbole im Ladefenster | 300 | **1.046 (alle)** |
| Live-Entscheidungen ohne 5-Tage-Wert | 277 | **222** |
| Ergebniszeilen gesamt | 55.885 | **99.825** |

Die verbleibenden 222 sind **kein Rest des Fehlers**: Sie stammen alle
vom 02.09. oder später. `make_price_lookup` setzt am Bar *nach* der
Entscheidung an, ein 5-Tage-Wert für den 02.09. braucht deshalb Kurse bis
zum 11.09. — den heute noch nicht geschlossenen Tag. Sie füllen sich von
selbst.

Dienste nach `CLAUDE.md` vollständig neu gestartet, Tests und
Health-Check davor und danach grün.

---

## G56. B11 — Zwischenschau vom 11.09.2026, keine Entscheidung

**`BETRIEBSPLAN` §4 sieht für ca. 12.09. eine reine Zwischenschau vor,
ausdrücklich ohne Entscheidung.** Der 12.09.2026 ist ein Samstag; die
Schau wurde deshalb auf den 11.09. vorgezogen. Der Entscheidungstermin
bleibt der **10.10.2026** mit allen vier Kriterien aus §3.3.

```
python scripts/21_fleet.py --kriterien B11_dyn_ausstieg_live
```

| Kriterium | Stand | Soll |
|---|---|---|
| 1. t über Zufallsschwelle | 1,41 | > 2,88 |
| 2. auswertbare Handelstage | 14 | ≥ 20 |
| 3. Verlängerungsquote | **33,3 % — erfüllt** | 10–60 % |
| 4. Median der verlängerten Trades | **−0,0133** | > 0 |

### Was neu ist: Kriterium 4 steht negativ, aber auf 7 Trades

§7.1 hatte Kriterium 4 als eine der Fragen geführt, die „sicher kommen":
„~22 verlängerte Trades, reine Vorzeichenfrage". Nachgezählt:

| | Zahl |
|---|---:|
| B11-Ausstiege gesamt | 36 |
| davon Frist erreicht (`bars_held >= 5`) | 21 |
| davon verlängert | **7** |
| davon im Plus | 2 (28,6 %) |

**Sieben Trades nach 14 Tagen.** Linear auf die 31 auswertbaren Tage des
10.10. hochgerechnet: **etwa 15**, nicht 22. Bei 15 Beobachtungen ist
eine Vorzeichenfrage mit 28 % Trefferquote noch gut mit Zufall
vereinbar — zwei von sieben Positiven liegen bei einem fairen Vorzeichen
bei p ≈ 0,45 einseitig.

**Diese Hochrechnung steht hier vor dem Termin, nicht danach** — aus
demselben Grund wie §G22: Am 10.10. wäre sie eine Erklärung für ein
unerwünschtes Ergebnis, heute ist sie eine Vorhersage. **Der Vertrag aus
§3.3 wird nicht geändert.** Fällt Kriterium 4 durch, gilt das; es ist
nur festgehalten, dass die Datenbasis dünner ausfällt als §7.1 erwartet
hat.

### Der Nebenbefund, der die Richtung dreht

Innerhalb von B11 schneiden die **verlängerten** Positionen besser ab als
die, die zum Stichtag verkauft wurden:

| | n | Median |
|---|---:|---:|
| verlängert (`bars_held > 5`) | 7 | **−1,33 %** |
| nicht verlängert (`bars_held == 5`) | 14 | −3,94 % |

Kriterium 4 prüft das **absolute** Vorzeichen, nicht diesen Vergleich —
und das bleibt so. Aber es erklärt, warum ein negativer Median hier
nicht dasselbe heißt wie „die Regel schadet": Der Zeitraum war für
beide Gruppen schlecht (Depot −1,85 % seit dem 18.08., SPY −1,24 %).

### Der Betrieb in der Zwischenschau

| | Stand 11.09.2026 |
|---|---|
| Health-Check | **GRÜN** — die befristete Ausnahme aus §8.1 (Stichtag 10.09.) ist eingehalten, der §G36-Zustand aus dem Fenster gewandert |
| Regelabgleich | keine Abweichungen, 9 Regeln, 0 Verstöße |
| Risiko-Dach | frei, Drawdown 4,8 % (Grenze 20 %), Exposure 90 % |
| Tests | 48 Prüfungen, 0 Fehler, beide Schichten grün |
| Kapital | 104.644 $ |
| Depot seit 15.08. | −3,60 % gegen SPY −1,91 % |
| Slippage-Median | +0,0 bps über 284 Orders |
| `shadow.pruefungen()` | 9 von 11 grün; Nr. 10 und 11 weiter FEHL (§G16, bekannt) |

Die Depot-Unterrendite von 1,7 Prozentpunkten über 18 Handelstage ist
**kein Befund** (§5.3) und wird hier nur zur Vollständigkeit geführt.

---

## G57. Ausbruch-Werkstatt gebaut — Voranmeldung, noch kein Ergebnis (11.09.2026)

**Anlass:** Nutzerentscheidung. Nach §G54 (Umkehr-Strategie trägt die
Kosten nicht) wird eine Idee der Gegenrichtung geprüft: kaufen, was
gerade stark gestiegen ist, in der Erwartung, dass die Bewegung
nachläuft.

**Das Argument dafür, in einer Zahl.** Der Umkehr-Bot scheitert an
0,287 % Rundlaufkosten gegen +0,11 % Vorsprung je Trade. Eine Bewegung
von 10–20 % in Stunden liegt zwei Größenordnungen darüber — läuft davon
auch nur ein Bruchteil nach, ist die Kostenhürde kein Thema mehr.

**Das Gegenargument, gleich stark.** Genau diese Werte haben die
weitesten Spannen. Die 12,2 bps aus §G54 sind der Median des *liquiden*
Universums im Normalzustand, nicht der eines Wertes mitten im Sprung.

**Gebaut:** `ausbruch.py` (Strategie, 23 Stellschrauben),
`ausbruch_daten.py` (Parquet-Vorrat für 15-Minuten-Bars),
`ausbruch_store.py` (Läufe/Trades/Bestenliste + eigener Versuchszähler),
`scripts/46_ausbruch.py` (lokale Weboberfläche mit Live-Anzeige),
`tests/test_ausbruch.py` (20 Tests). Vollständige Voranmeldung mit
Sechs-Punkte-Gate in `docs/AUSBRUCH.md` — **geschrieben, bevor der erste
Lauf existierte.**

### Die drei Lügen-Stellen, vorab zu unseren Ungunsten aufgelöst

| Stelle | Entscheidung | Test |
|---|---|---|
| Lookahead | Signal auf Schluss von Bar t, **Kauf zum Open von t+1** | `test_kauf_erfolgt_zum_folgebar_nicht_zum_signalkurs` |
| Stop und Ziel in einer Bar | **immer der Stop** | `test_stop_gewinnt_wenn_eine_bar_beides_beruehrt` |
| Survivorship | dauerhaft im Kopf der Oberfläche, nicht wegklickbar | `test_hinweise_nennen_survivorship_und_kosten` |

Jede dieser drei Entscheidungen macht die Zahlen schlechter. Das ist der
Punkt: Die Gegenannahme lässt genau die Ecke des Parameterraums gut
aussehen, in die ein Sweep von selbst läuft.

### Zwei Fehler beim Bauen gefunden

1. **Schluss-Sperre prüfte einen Punkt statt eines Bereichs.** Bei
   `schluss_sperre_bars=3` waren die Bars t+1 und t+2 erlaubt und nur
   t+3 gesperrt — das Gegenteil der Absicht. Beim Vorgabewert 1 tun
   beide Fassungen dasselbe, deshalb wäre es ohne Test nie aufgefallen.
   Behoben, Regressionstest `test_schlusssperre_deckt_den_ganzen_bereich_ab`.
2. **Ein Testdatensatz löste zwei Signale statt einem aus** und prüfte
   damit das Zusammenspiel mehrerer Regeln statt der einen gemeinten
   Frage. Die Engine lag richtig, der Test war unscharf.

### Der Versuchszähler ist der eigentliche Zweck der Datenbank

Eine Oberfläche zum Herumprobieren **ist** eine Maschine zur Herstellung
von Scheingewinnern (§B2). Das lässt sich nicht abschalten, nur zählen:
Jeder Lauf wird **vor** der Rechnung angemeldet, `lauf_loeschen()`
entfernt die Daten aber **nicht** den Zählereintrag, und die Schwelle
`sqrt(2 ln N)` steht bei jedem Ergebnis neben dem t-Wert. Getrennt vom
Flottenzähler, weil Historienläufe dort bewusst keinen Platz kosten
(`BETRIEBSPLAN` §4).

**Die Grenze des Zählers, benannt statt beschönigt:** Gezählt wird nur,
was über die Oberfläche läuft. `ausbruch.lauf()` ist eine reine Funktion
und kennt die Datenbank nicht — ein Direktaufruf erscheint nirgends. Das
ist bewusst so (eine Rechenfunktion, die beim Aufruf in eine Datenbank
schreibt, wäre in Tests unbrauchbar), heißt aber: **Der Zähler ist
ehrliche Buchführung, keine Schranke.**

### Stand — erste Zahlen, ausdrücklich kein Befund

| | Rauchtest | Belastungstest |
|---|---:|---:|
| Symbole | 10 | **598** |
| Bars | 70.000 | **3,72 Mio** |
| Laufzeit | 0,1 s | **5,2 s** |
| Signale → Trades | 286 → 79 | 1.686 → 210 |
| Rendite 2025 | +4,7 % | **+2,71 %** |
| max. Rückgang | — | −11,7 % |
| Trefferquote | 53,2 % | 41,9 % |
| je Trade brutto → netto | — | **+0,312 % → +0,130 %** |
| t (Handelstage) | 1,06 (56) | **0,19 (121)** |

Konfiguration des Belastungstests: 10 % Anstieg über 2 Stunden,
Umsatzschub ≥ 2×, 1 Tag Haltedauer, +10 % Ziel, −5 % Stop, 12,2 bps.

**t = 0,19 über 121 Handelstage — kein Befund.** Der Vorrat umfasst 598
Symbole, 86 MB; ein voller Durchlauf dauert 5 Sekunden, Herumprobieren
ist damit praktikabel.

**Eine Beobachtung, die den Unterschied zu §G54 zeigt:** Der
Bruttoertrag je Trade liegt mit **+0,312 %** über der Kostenschwelle von
0,182 % — anders als beim Umkehr-Bot, wo er sie nie erreicht. Die Kosten
fressen hier 58 % des Bruttoergebnisses, nicht 160 %. Das ist genau das
strukturelle Argument für diese Strategiefamilie.

**Es ist trotzdem kein Befund.** Ein Punktschätzer mit t = 0,19 ist von
null nicht zu unterscheiden, 2025 war ein steigender Markt, und der
Survivorship-Vorbehalt aus §4.3 gilt in voller Stärke. Dieser Eintrag
hält fest, was gebaut und was vorab festgelegt wurde — nicht, was
gefunden wurde.

### Nachtrag: die automatische Suche und ihr erstes Ergebnis

Auf Nutzerwunsch ergänzt (`ausbruch_suche.py`, `scripts/47_...`): ein
Verfahren, das Kombinationen durchprobiert, sich die beste merkt und von
dort weitersucht — Erkundung, Bergsteigen, Neustart im Wechsel, mit
Live-Terminal. Suchraum: 17 Achsen, **6,3·10¹¹ Kombinationen**. Tempo
~1 s je Versuch bei 150 Symbolen.

**Das Gegenmittel ist eingebaut, nicht angeflanscht.** Das Jahr wird
zeitlich in Lernfenster (70 %) und Prüffenster (30 %) geschnitten.
Optimiert wird ausschließlich auf dem Lernfenster; das Prüffenster wird
bei jedem neuen Besten *einmal* nachgerechnet und **nie zur Auswahl
benutzt**. Maßgeblich ist der Abstand zwischen beiden.

**Erster Probelauf (60 Symbole, 107 Versuche in 42 Sekunden):**

| | Lernfenster | Prüffenster |
|---|---:|---:|
| t-Wert | **+2,17** | **−0,55** |
| Rendite | +2,07 % | −0,88 % |
| Trades | 57 | 19 |

**Abstand +2,72 nach nur 107 Versuchen.** Das ist keine Enttäuschung,
sondern der Nachweis, dass der Schutzmechanismus greift: Genau so sieht
eine Konfiguration aus, die den Lernzeitraum beschreibt und sonst
nichts. Ohne die Fenstertrennung stünde hier „t = 2,17 gefunden" — und
das wäre die Illusion mit Nachkommastellen, vor der §B2 warnt.

**Der Zähler zählt beides zusammen.** `n_versuche()` summiert Handläufe
und alle Teilversuche automatischer Suchen. Eine Suche mit 3.000
Durchläufen hebt die Schwelle auf `sqrt(2 ln 3000)` = **4,00** — auch
für spätere Handläufe in der Werkstatt. Stand nach dem Probelauf: 108
Versuche, Schwelle 3,06.

**Eigener Fehler dabei:** Im ersten Entwurf stand `sqrt(2 ln 3000)` =
3,58 im Docstring. Richtig sind 4,00 (3,58 wäre ln 600). Der Code
rechnete korrekt, nur der erklärende Text war falsch — und genau solche
abgeschriebenen Zahlen sind laut §G19 Fund 2 der Weg, auf dem eine Hürde
unbemerkt sinkt.

---

## G58. Die Ausbruch-Suche verglich den Prüfwert mit der falschen Schwelle (11.09.2026)

**Der Fund.** Der Bericht der automatischen Suche stellte den
**Prüfwert** gegen die **Lernschwelle** `sqrt(2 ln N_Versuche)`. Bei
einem Dauerlauf mit 940.000 Versuchen liegt die bei **5,24**.

Ein Prüfwert von 3,5 wäre damit als „kein Befund" abgetan worden —
**auch bei einem echten Effekt.** Das Verfahren war per Konstruktion
unfähig, jemals etwas zu finden.

### Warum das falsch war

Die Auswahl über N Versuche findet **ausschließlich im Lernfenster**
statt. Das Prüffenster sieht nur die wenigen Konfigurationen, die dort
gewonnen haben. Jede dieser Bewertungen ist ein **sauberer Einzeltest**
auf Daten, die an keiner Auswahl beteiligt waren — die Vielfachtestung
ist auf der Lernseite bereits bezahlt.

| Schwelle | gilt für | Grundlage | Wert |
|---|---|---|---:|
| Lernschwelle | Lernwert | 940.000 Versuche | **5,24** |
| **Prüfschwelle** | **Prüfwert** | **~50 Prüfungen** | **2,80** |

### Warum das kein Absenken der Latte ist

Der Zähler `pruef_bewertungen` läuft über **alle Instanzen und alle
Läufe** hinweg weiter. Wer die Suche zehnmal wiederholt und sich den
besten Prüfwert heraussucht, hebt damit seine eigene Hürde — genau wie
§B2 es verlangt. Und die Bedingung bleibt unverändert: Es darf nie auf
den Prüfwert hin ausgewählt werden. `Suche.laufen()` tut das nicht,
abgesichert durch `test_pruefungen_werden_gezaehlt` und
`test_pruefschwelle_haengt_an_den_pruefungen_nicht_an_den_versuchen`.

**Einordnung.** Das ist die Umkehrung des üblichen Fehlers in diesem
Projekt: Sonst waren die Hürden zu niedrig (§G19 Fund 2, §G43). Hier war
eine so hoch, dass sie das Werkzeug unbrauchbar machte. Beide Richtungen
sind Fehler — eine Schwelle muss die Frage treffen, die sie stellt.

---

## G59. Dauerbetrieb der Ausbruch-Suche — 4 Instanzen, Protokoll, Elite (11.09.2026)

**Anlass.** Die Suche sollte über Tage bis Wochen laufen und am Ende
auswertbare Daten liefern. Drei Dinge fehlten dafür.

### 1. Ein einzelner Prozess nutzte einen von zehn Kernen

Gemessen: 100 % CPU auf einem Kern, neun leer. Umgestellt auf **vier
parallele Instanzen** (`--instanz a|b|c|d`, je eigener LaunchAgent):

| | vorher | nachher |
|---|---:|---:|
| Versuche je Sekunde | 1,35 | **5,4** |
| je Stunde | ~4.900 | **~19.500** |
| in 48 Stunden | ~235.000 | **~940.000** |
| Speicher | 1,2 GB | 4,8 GB von 26 GB |

**Handelsbot und Schattenbot laufen weiter** — sie stehen bei 0,0 % CPU
(33 Minuten Schlaf, 20 Sekunden Arbeit). Sie zu stoppen brächte nichts
und zerstörte die B11-Messung (10.10.) und das Trendbot-Pferderennen
(bis 30.11.).

### 2. Kein Fortsetzen nach Neustart

Ein Absturz oder Neustart begann wieder bei Versuch 0. Jetzt:
Checkpoint alle 200 Versuche, `KeepAlive` startet neu, der Checkpoint
setzt fort. Getestet: nach Abbruch bei 447 setzte der Neustart bei 447
fort, nicht bei 0.

**Bewusst nicht gespeichert: die Menge der bereits geprüften
Konfigurationen.** Bei 6,3·10¹¹ Kombinationen ist die Chance, nach einem
Neustart zufällig etwas Wiederholtes zu ziehen, verschwindend gering —
ein paar verschenkte Millisekunden gegen eine Datei, die über Wochen ins
Unermessliche wächst.

### 3. Nur der beste Fund wurde gespeichert

Das ist genau das Falsche. Der beste Fund aus einer Million Versuchen
**ist** ein Ausreißer (§B2). Die belastbare Erkenntnis lautet nicht
„welche Konfiguration gewann", sondern „welche Achsenwerte schneiden
über hunderttausende Versuche hinweg systematisch besser ab".

Jetzt wird **jeder** Versuch protokolliert (`ausbruch_versuche.py`, eine
SQLite je Instanz — vier Prozesse in derselben Datei blockieren sich bei
5 Schreibvorgängen je Sekunde). `scripts/52_ausbruch_auswertung.py`
rechnet daraus die Randverteilung je Achse. Erste 800 Versuche:

```
  anstieg_pct
                15   +0.876  n=108        fenster_bars
                30   -1.690  n=112                    16   +1.239  n=146
                                                      52   -1.826  n= 60
```

Zu lesen als: mittlerer Lern-t-Wert dieses Achsenwerts minus
Gesamtmittel. **Diese Aussagen stützen sich auf hunderte Versuche, nicht
auf einen.**

### Dazu: die unverzerrte Stichprobe

Für **1 % der Versuche** wird das Prüffenster zusätzlich gerechnet — nur
protokolliert, nie verglichen, nie zur Auswahl. Erst das beantwortet die
eigentliche Frage: *Sagt ein guter Lernwert überhaupt etwas über den
Prüfwert?* Aus den Gewinnern allein ist das nicht zu beantworten, sie
sind eine bewusst schiefe Auswahl.

Liegt die Korrelation nahe null, findet die Suche reine
Zeitraum-Anpassung und die Strategiefamilie trägt in dieser Form nichts.
**Das wäre ein Befund, kein Misserfolg.**

### Elite-Austausch zwischen den Instanzen

Vier unabhängige Suchen finden vier verschiedene Hügel — das ist
gewollt. Aber wenn Instanz b nach zwei Stunden bei t=0,3 herumsucht,
während a längst t=3,1 gefunden hat, ist weiteres Herumirren verschenkte
Rechenzeit. **40 % der Neustarts** setzen deshalb in der *Umgebung* des
gemeinsamen Bestwerts an (zwei zufällig verstellte Achsen).

Bewusst nicht 100 %: Vier Instanzen, die alle beim selben Punkt
ansetzen, sind nur noch eine Suche mit vierfachem Stromverbrauch.

### Stand

22 Tests für Engine, Suche und Protokoll; `22_tests.py` grün. Vier
Instanzen laufen seit 11.09.2026, 18:44 Uhr auf 1.844 Symbolen über
2023–2026. **Es liegt noch kein Ergebnis vor** — dieser Eintrag hält
fest, was gebaut wurde, nicht was gefunden wurde.

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
| Länger halten? | `B04_halten_lang` | `fleet.schwelle_sigma()` |
| Dynamischer Ausstieg statt fixer 5 Tage? | `B11_dyn_ausstieg_live` gegen seine registrierte Basis | alle vier Kriterien aus `BETRIEBSPLAN` §3.3, Termin 10.10.2026 |
| Mehr Breite? | `B07_mehr_positionen` | `fleet.schwelle_sigma()`; Tendenz negativ |

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
