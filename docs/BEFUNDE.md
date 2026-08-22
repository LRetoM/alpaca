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

**Die zwei offenen Punkte überschätzen beide den Schatten**, nie den
Live-Bot — die Messung ist also optimistisch, nicht pessimistisch. Das
ist die ungefährlichere Richtung, aber es heißt: Ein im Schatten knapp
bestandener Bot ist live noch nicht bestanden.

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
laufenden Dienste. Am Ende: **296 Tests** (vorher 222), 48
Selbstprüfungen, **51 von 51 Mutationen gefangen**, beide Dienste mit dem
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
