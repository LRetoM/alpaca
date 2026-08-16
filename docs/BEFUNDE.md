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
