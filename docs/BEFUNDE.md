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
