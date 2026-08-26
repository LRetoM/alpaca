# Übergabe — Stand 26.08.2026

> **Für eine neue Sitzung.** Dieses Dokument fasst zusammen, was zwischen
> dem 22. und 26.08.2026 passiert ist, was gerade läuft, und woran
> weitergearbeitet werden muss. Es ersetzt nicht `BEFUNDE.md` — es zeigt,
> wo dort nachzuschlagen ist.

**Zuerst lesen, in dieser Reihenfolge:**

1. `CLAUDE.md` — die Regeln, nicht verhandelbar
2. Dieses Dokument — Überblick und Einstieg
3. `docs/BEFUNDE.md` §B2, §B6, §J — die Fallen und die Bilanz
4. `docs/BETRIEBSPLAN.md` §3.3 — was am 10.10.2026 entschieden wird
5. `docs/UMBAUPLAN.md` — der Umbau, Schritte 1–5 sind erledigt

---

## 1. Betriebszustand — was gerade läuft

| Dienst | Status | Details |
|---|---|---|
| **Live-Bot** (`12_daemon.py --live`) | 🟢 läuft | Neustart 26.08. 09:47. Kapital $106.097, **16 Positionen, alle mit Zustand**. Papierkonto (`ALPACA_PAPER=True`) |
| **Schatten-Bot** (`16_shadow_daemon.py`) | 🟢 läuft | 8 Flottenbots, ~789 Symbole/Tag, verarbeitet Stichtag 25.08. |
| **EDGAR-Lauf** (`34_edgar_kandidat.py`) | 🟡 läuft seit 25.08. 18:05 | **24 % (517/2168 Symbole)**, ~50 Std. Restlaufzeit. Checkpoint alle 50 Symbole |

**Prüfstand:**

```
python scripts/22_tests.py        ->  496 von 496, beide Schichten grün
python scripts/23_mutationstest.py ->  76 von 76 gefangen
python scripts/18_health_check.py  ->  ROT (siehe unten, erwartet)
```

**Warum der Health-Check ROT meldet und das in Ordnung ist:** Er sieht
sich die *jüngsten 20* Entscheidungen je Aktionsart an. Die
Kontextfelder (`regime_markt`, `sektor`, `liq_dezil`) bei `sell`/`topup`
wurden am 25.08. repariert (§G36), aber 19 der 20 jüngsten Zeilen
stammen von davor. Er wird von selbst grün, sobald 20 neue Verkäufe
aufgelaufen sind — einige Handelstage. **Der Prüfer wird dafür nicht
angepasst.** Eine Schwelle zu lockern, damit die eigene Reparatur früher
grün aussieht, ist genau das, wovor §B2 warnt.

**Flottenstand:** 16 Versuche gesamt, Zufallsschwelle **t > 2,85**.
Laufend: `B00`, `B04`, `B06`, `B07`, `B08`, `B09`, `B11`, `B12`.
`B06` und `B09` sind **bitgleich** mit ihrer Referenz und messen
strukturell nichts — sie bleiben trotzdem laufen (`B09` ist B11s
registrierte Referenz, `B06` wartet auf einen Regimewechsel).

---

## 2. Die wichtigste Zahl für jede Planung

```
0 von 48 Versuchen bestanden.
```

38 bis zum 23.08. (§B6), dazu die 10 Makro-/GDELT-Bänder aus §G35.
**Das ist kein Scheitern, das ist die Basisrate.** §B3 nennt für
publizierte Anomalien: ~65 % replizieren nicht, der Rest verliert im
Mittel 58 % seiner Wirkung. Wer diese Bilanz für ungewöhnlich hält,
plant die nächsten zwanzig Versuche falsch.

**Der eigentliche Engpass, an dem alles hängt:**

```
Vorsprung je Trade   +0,110 %
Rundlauf-Breakeven    0,142 %
                     --------
Lücke                 0,032 Prozentpunkte
```

Keine der 14 geprüften Parameterachsen adressiert diesen Konflikt — sie
justieren alle nur Randbedingungen eines Vorsprungs, der zu klein ist.
**Die einzige gemessene Sache, die diese Lücke vollständig schließt, ist
die Kostenseite** (§G34, siehe Abschnitt 5).

---

## 3. Was in dieser Sitzungsreihe gemacht wurde

Chronologisch, mit dem jeweiligen Befund-Paragraphen.

### 22.–23.08. — Der große Durchgang durch den Messapparat

| Was | § | Ergebnis |
|---|---|---|
| Vollständige Durchsicht | §G13–G18 | 10 stille Fehler, 8 behoben |
| Acht Funde in der Datenwahrheit | §G19 | u. a. `exit_score` und `trail_after_atr` nie gegengeprüft |
| `shadow.py` aufgeteilt (2339 Zeilen → 5 Module) | §G20 | **Bytecode-Nachweis: 61/61 Funktionen bitgleich** — die Handelslogik ist beweisbar unberührt |
| Intraday-Stop schrieb keinen Lebenslauf | §G21 | Ausgerechnet die Verlusttrades fehlten der Auswertung |
| Trennschärfe-Rahmen gebaut | §G22 | `shadow_eval.trennschaerfe()` |
| Was Kriterium 1 am 10.10. leisten kann | §G23 | **Es kann nur Effekte finden, die es nicht geben kann** (28–53× über dem wirtschaftlich Relevanten) |
| Historienlauf gegen Live verglichen | §G24 | **Der Historienlauf testet eine andere Strategie** — `simulate.py` übergibt kein `news`, rechnet also 4 statt 5 Faktoren |
| Lernschleife geprüft | §G25 | Sie ist **offen** — 0 von 38 Versuchen haben je die Handelslogik erreicht |
| IC-Kanal kalibriert | §G26 | Fehlalarmquote real **11 %** statt 5 % bei t>2; echte Schwelle **t>2,57**. Score-Persistenz gemessen: 0,49 (nicht 0,80 wie angenommen) |

### 24.08. — Tauschregel und Kursfehler

| Was | § | Ergebnis |
|---|---|---|
| Spiegelbuch vergaß Einstiegsgründe | §G27 | `INSERT OR REPLACE` überschrieb `entry_score`/`reasons` beim täglichen Übertrag → COALESCE |
| **Tauschregel gemessen** (volle 15 Positionen, besserer Kandidat kommt) | §G28 | **Alle 4 Kriterien negativ.** Die Score-Variante verkauft zu **80 % Gewinner** — der Umkehr-Score misst „wie überverkauft", eine erholte Position rutscht automatisch ans Ende |
| **Falscher Brokerkurs** (DKS $150,50 statt $179,64) | §G29 | Mechanismus: `current_price = lastday_price × (1 + change_today)`, und `change_today` war schlicht falsch. IEX sieht nur ~2 % des Volumens |
| Historie gegen Vorwärtstest vermessen | §G31 | **Die Historie ist 5- bis 9-mal feiner** — 0,0378 %/Tag gegen 0,18–0,35 %/Tag |

### 25.08. — Der Umbau und drei neue Datenquellen

| Was | § | Ergebnis |
|---|---|---|
| DKS-Absturz geprüft | §G32 | **Echt**, nicht wie §G29 — Q2-Zahlen. Der Stop hat korrekt gegriffen. Randfall gefunden: vor Handelsbeginn kann `_quote_plausibel` einen echten Sturz maskieren (bewusst nicht unter Zeitdruck gefixt) |
| **Erster 15-Jahre-Lernlauf** | §G33 | 792 Symbole, 3.767 Handelstage, 15 Jahresscheiben. **0 von 14 Achsen bestanden** |
| **Limitorder-Recherche** | §G34 | **Der Spread ist 54 % der Rundlaufkosten.** `trading.limit_order()` war implementiert und wurde **nie aufgerufen** |
| FRED + GDELT angebunden | §G35 | 3 eigene Fehler dabei gefunden. **Ergebnis: kein Befund** |
| Intraday-Stop ohne Auswertungskontext | §G36 | Derselbe Sonderpfad wie §G21. Dabei eine **erfundene Volatilitätsangabe** gefunden (`NaN` fiel still auf `"normal"` durch) |
| Umbauplan Schritte 3–5 | — | `lernlauf.sqlite`, `lernlauf_eval`, `kandidatenregister` |

### 26.08. — RMBS

| Was | § | Ergebnis |
|---|---|---|
| **RMBS fünf Tage ohne Stop** | §G37 | Siehe unten — der schwerwiegendste Fund des Tages |

---

## 4. Die Fehler — nach Schwere

### Schwer: Der Bot handelte mit falschen Daten

**§G29 — Falscher Brokerkurs kam in den Zustand des Bots.**
Alpaca meldete für DKS $150,50, echt waren $179,64. Der Wert floss
direkt in `high_water = max(current, meta["high_water"])`. Weil das ein
`max()` ist, korrigiert es sich **nie von selbst** — der Trailing-Stop
und B11s Halte-Regel wären dauerhaft verzerrt gewesen.
*Behoben:* `live.build_portfolio()` prüft jeden Positionskurs gegen
`data.snapshots()['last']` gegen und verwirft Abweichungen > 5 %.
5 Regressionstests + Mutation.

**§G37 — RMBS fünf Tage ohne Stop.**
`account.orders()` zeigt für RMBS **genau eine** Order: Kauf am 20.08.,
nie verkauft. Trotzdem meldete `sync_with_broker()` bei einem Neustart am
21.08. „verwaist" und löschte Stop (77,39) und Ziel (104,36) sofort. Und
es korrigierte sich nicht: Der Broker-Read ließ RMBS **wiederholt** aus,
alle Zyklen vom 21. bis 25.08. zeigten `15 = 15`.
*Behoben:* Ein Symbol gilt erst nach **zwei aufeinanderfolgenden**
Aufrufen als verwaist (neue Tabelle `verdacht_verwaist`, überlebt
Neustarts — der Ursprungsfehler passierte bei einem Neustart). Marken mit
den *echten* Werten wiederhergestellt (Füllkurs 91,53, Abstand 14,84 %
aus der ursprünglichen Kaufentscheidung, High-Water aus echten Bars).
4 Regressionstests + Mutation.

### Schwer: Messungen, die etwas anderes maßen als gedacht

**§G24 — Der Historienlauf testet eine andere Strategie.**
`simulate.py:191` ruft `build_reversal_frame(df, market, ecfg.reversal_weights)`
ohne `news=`. `shadow_daten.py` übergibt `symbol=s, news=news`. Der
Historienlauf rechnet die Vier-Faktor-Fassung, live läuft die
Fünf-Faktor-Fassung — **und die Rangfolge dreht sich dadurch.**
*Status:* dokumentiert, **nicht behoben**. Deshalb gilt die Regel:
Historie darf verwerfen, nie abnehmen.

**§G35 Fund 4 — Der eigene Test maß eine Tautologie.**
Der erste Makro-Lauf zeigte für `vix_aenderung_5d` eine Spanne von
0,5586 %/Tag mit |t| bis 5,31 — um Größenordnungen mehr als alles je
Gemessene. Und vollständig wertlos: verglichen wurde das Merkmal von Tag
*t* mit der Rendite von Tag *t*. Ein steigender VIX **ist** ein fallender
Markt. Gemessen wurde: *„Wenn der Markt fällt, verlieren wir."*
*Behoben:* `lag=1` als Vorgabe. **89 % des scheinbaren Effekts waren
reine Gleichzeitigkeit.** Gefunden **vor** der Notierung als Befund — der
spektakuläre t-Wert war das Warnsignal.

**§G26 — Der IC-Kanal war zu mild kalibriert.**
Nominal t>2 bedeutet real eine Fehlalarmquote von **11 %**, nicht 5 %.
*Behoben:* echte Schwelle t>2,57.

### Mittel: Protokoll- und Auswertungslücken

| Fehler | § | Kern |
|---|---|---|
| Intraday-Stop ohne Lebenslauf | §G21 | Genau die Verlusttrades fehlten |
| Intraday-Stop ohne Auswertungskontext | §G36 | Derselbe Sonderpfad, ein Jahr später |
| Erfundene Volatilitätsangabe | §G36 | `NaN < 0.15` und `NaN > 0.30` sind **beide False** → fiel still auf `"normal"` |
| Spiegelbuch vergaß Einstiegsgründe | §G27 | `INSERT OR REPLACE` beim täglichen Übertrag |
| Buchführungsprüfer meldete Falsch-Positiv | §G30 | Delistetes Symbol (WBS) als „laufender Ausfall" |
| GDELT-Ratenlimit falsch eingetragen | §G35 | 30/min eingetragen, echt ist **eine Anfrage alle 5 Sekunden** |
| `raise_for_status()` außerhalb des Retry-Lambdas | §G35 | HTTP 429 wurde nicht wiederholt |

### Meine eigenen Fehler beim Reparieren — beide von den eigenen Tests gefangen

1. **Beim §G21-Fix** `_handelstage` benutzt, ohne es zu importieren. Das
   wäre **schlimmer als der Originalfehler** gewesen: Der `except`-Block
   hätte es still geschluckt, der Stop hätte verkauft und *weder* Ausstieg
   *noch* Lebenslauf *noch* `drop_position` protokolliert. Gefangen vom
   neuen Test, weil der `dry_run=False` ausübt — der vorhandene
   `TestIntradayStop` lief immer nur mit `dry_run=True`.
2. **Beim §G20-Split** wurde `check_schatten_handelt_nicht` zum No-Op —
   die Prüfung listete hart `shadow.py`, die Logik war nach
   `shadow_schritte.py` gewandert. **Gefangen vom Mutationstest**, nicht
   von einem Test. Behoben durch `schatten_module()` per Glob.

**Das ist der Grund, warum der Mutationstest nicht verhandelbar ist.**

---

## 5. Strategien aus dem Netz — der große Überblick

Der Faktorraum aus Kurs- und Volumendaten ist laut §C **vermutlich
ausgeschöpft** — die 18 Faktorkandidaten entdeckten überwiegend den
bereits gehandelten Umkehr-Effekt neu. Neue Information muss von
**außerhalb** kommen. Das ist die Begründung für alles in diesem
Abschnitt.

### 5.1 🔴 Gemessen und durchgefallen

| Idee | Quelle | Ergebnis | § |
|---|---|---|---|
| **PEAD über Analysten-Überraschung** | Standard-Literatur | IC 0,011, aber **Zerfallsprofil falsch herum** (nichts in 10 Tagen, Effekt ab Tag 20) → keine Meldungswirkung, sondern Symboleigenschaft | §C |
| **PEAD über Kursreaktion** | dito | IC **−0,010** (t=−6,5), Richtung entgegengesetzt — sieht nach Umkehr aus, also dem, was der Bot ohnehin handelt | §C |
| **18 Faktorkandidaten** | eigene Ableitung | keiner besteht; die zwei mit \|t\|>2 scheiterten an der Jahresstabilität | §C |
| **FRED Makro** (VIX-Niveau, VIX-Änderung, Zinsstruktur, Zinsänderung) | FRED / yfinance | max \|t\| = 2,45 gegen Schwelle 3,21 — **kein Befund** | §G35 |
| **GDELT Nachrichtenregime** (6 Merkmale) | GDELT 2.0 | max \|t\| = 1,94 — **kein Befund** | §G35 |
| **Tauschregel** (schwache Position gegen besseren Kandidaten) | eigene Idee (Nutzer) | 4 Kriterien, alle negativ; verkauft zu 80 % Gewinner | §G28 |
| **ML-Modell gegen den Score** | — | schlägt den Score nicht | §G15 |
| **Symbol-Aufteilung auf mehrere Bots** | — | mathematisch ≈ ein Bot mit N·15 Positionen, nur mit **schlechterer** Auswahl | §C |
| **`trail_after_atr = 1,5`** | Lernlauf-Achse | t = **−3,53**, stärkster Wert aller 14 Achsen — **in der schädlichen Richtung**. −41,8 % über 15 Jahre | §G33 |

**Ein Hinweis zu `vix_niveau`** (kein Befund, aber notiert): Es verläuft
monoton in der ökonomisch erwarteten Richtung — hohes VIX-Perzentil
+0,0987 %/Tag (t=+2,45), niedriges −0,0233 %/Tag (t=−2,28). Passt zur
vorab notierten Vermutung: Eine Umkehr-Strategie braucht Überreaktion,
und die gibt es in Panik häufiger. **Vorab notiert, damit es später keine
nachträgliche Erzählung wird.** t=2,45 unter Schwelle 3,21 bleibt der
Normalfall.

### 5.2 🟡 Läuft gerade

| Idee | Quelle | Stand |
|---|---|---|
| **SEC EDGAR Form 4 — Insider-Cluster** | SEC EDGAR (Pflichtmeldung binnen 2 Werktagen) | **24 % (517/2168)**, ~50 Std. Rest. Erstes Ergebnis frühestens 28.08. |

**Warum dieser Kandidat anders ist als die bisherigen 32:** Er kommt
nicht aus einer weiteren Ableitung von Kurs und Volumen, sondern aus
echtem Insiderverhalten. **Zeitpunktgenau** (Einreichungsfrist 2
Werktage) und **ohne Survivorship-Lücke** — auch untergegangene Firmen
bleiben im Archiv. Das ist die einzige laufende Messung, die den
strukturellen Vorbehalt gegen alle Historienläufe nicht trägt.

**Achtung bei der Auswertung:** §B4 — PEAD sah auf 60 Symbolen aus wie
der beste Faktor des Projekts (t = 6,7) und brach auf 800 vollständig
zusammen. Ein Teilergebnis aus dem Checkpoint ist **keine** Aussage.

### 5.3 🟠 Gebaut, aber noch nicht gelaufen — **die wichtigste offene Sache**

| Idee | Quelle | Stand |
|---|---|---|
| **Limitorder statt Marktorder** | Anand/Samadi/Sokobin, *Review of Finance* (FINRA-Daten) | Füllmodell in `simulate.py` **fertig**, `scripts/36_limit_vergleich.py` **fertig**, **NIE GELAUFEN** |

**Warum das ganz oben auf die Liste gehört:**

```
Rundlauf über 10.000 $ bei 5 bps Spread:

  Spread (2× halbe Spanne)   5,00 $   54 %   <- per Konstruktion gezahlt
  Slippage (2× 2 bps)        4,00 $   43 %
  SEC + FINRA TAF            0,22 $    2 %
  Kommission (Alpaca)        0,00 $    0 %
```

| effektiver Spread | Breakeven | gegen +0,11 % |
|---:|---:|---|
| 5,0 bps (heute) | 0,1423 % | fehlt 0,032 pp |
| **3,0 bps** | **0,1022 %** | **TRÄGT** |

**Die Lücke, die dieses Projekt seit Wochen mit neuen Faktoren zu
schließen versucht, schließt sich vollständig bei einer
Spread-Reduktion von 5 auf 3 bps.** Das ist keine neue Alpha-Quelle,
sondern Arithmetik auf der Kostenseite — und deshalb die einzige
gemessene Sache, die den zentralen Konflikt aus §A überhaupt adressiert.

**Die Belege:**
* Retail-Limitorders haben **niedrigere** Handelskosten als marktnahe
  Orders, robust gegen Kontrollen für Aktie, Zeitpunkt, Ordergröße und
  Broker. **~65 % werden vollständig ausgeführt.** Der Grund ist
  ausgerechnet die Trägheit von Privatanlegern — sie stornieren nicht im
  Sekundentakt.
* Der Effekt ist **am größten bei weiteren Spreads, höherer Volatilität
  und kleineren Werten** — also exakt unser Universum. `universe.py`
  handelt bewusst nicht die 150 liquidesten Werte, sondern 1.200
  mittelgroße.
* **Gegenbeleg, der mitgehört werden muss:** *„The Negative Drift of a
  Limit Order Fill"* (arXiv 2407.16527) — adverse Selektion. Man wird
  gerade dann ausgeführt, wenn der Kurs weiterläuft.

**Der Vorbehalt, der alles bestimmt:** Alpacas Papierdepot füllt
Limitorders *„großzügig, sobald der Kurs die Marke berührt"* — es gibt
keine Warteschlangenposition. Genau der Teil, der bei Limitorders
entscheidet (*werde ich überhaupt ausgeführt?*), ist im Papierdepot
**unrealistisch optimistisch**. Ein Limitorder-Test im Papierdepot misst
also genau das, was nicht stimmt.

**Deshalb ist der Historienlauf der Weg**, und das Füllmodell ist bewusst
konservativ gebaut: Das Tagestief muss die Marke **unterschreiten**,
bloßes Berühren zählt nicht.

```bash
python scripts/36_limit_vergleich.py                     # 8 Jahre, 800 Symbole
python scripts/36_limit_vergleich.py --offsets 5,10,25,50
```

Angemeldet als `K03_limit_statt_market`, Status `gefunden`.

### 5.4 ⚪ Registriert, aber nie angefasst

Diese Quellen stehen in `ratelimit.QUOTAS` (seit 28.07.2026, Limits
verifiziert), es existiert aber **keine Zeile Code**, die sie benutzt:

| Quelle | Limit | Was damit ginge |
|---|---|---|
| **Finnhub** | 60/min | Analystenschätzungen, Earnings-Kalender, Insider-Sentiment |
| **FMP** | 250/Tag | Fundamentaldaten, Bilanzkennzahlen |
| **Tiingo** | 50/Std, 500/Tag, max. 1000 Symbole/Monat | Alternative Kursquelle, News |
| **Wikimedia Pageviews** | 50/s (200 erlaubt) | Aufmerksamkeitsmaß — Abrufzahlen einer Firmenseite als Retail-Interesse |
| **Alpha Vantage** | **25/Tag** | Praktisch unbrauchbar für Schleifen |

**Einordnung, ehrlich:** Fundamentaldaten (FMP) tragen die
Revisionsfalle aus §G35 in voller Stärke — heutige Bilanzzahlen auf
historische Tage zu legen ist Lookahead, und Point-in-Time-Vintages gibt
es dort nicht kostenlos. **Wikimedia Pageviews** ist der interessanteste
der vier: revisionsfrei, zeitpunktgenau, und misst etwas, das in keiner
Kursreihe steckt.

### 5.5 🟢 Bereits gemessen, aber unter der Schwelle — nicht wegwerfen

| Achse | t | Bemerkung |
|---|---:|---|
| `ohne_regime` (`market_regime_filter=False`) | **+2,22** | stärkster positiver Wert von 14. **Erste Messung über echte Bärenmärkte** (2018, 2022) — dort 2022: −2,6 % gegen −19,7 % der Basis |
| `halten_lang` (`max_hold_days=10`) | +2,05 | entspricht laufendem `B04` |
| `dyn_ausstieg` | +1,86 | entspricht laufendem `B11` — die Messung, die am 10.10. entschieden wird |

**Der Survivorship-Vorbehalt trifft ausgerechnet die beiden
Auffälligsten.** `ohne_regime` und `halten_lang` lassen beide Gewinner
länger laufen bzw. handeln in fallenden Märkten weiter. Genau für diese
Art Regel gilt: Das Universum kennt nur heute gelistete Symbole — die
Fälle, in denen ein länger gehaltener „Gewinner" später kollabiert,
**fehlen systematisch**. Beide Werte sind eine **Obergrenze mit
Schlagseite**, keine Schätzung der wahren Wirkung.

`ohne_regime` ist als `K01_ohne_regime_15j` registriert (Status
`gefunden`, `n_varianten_getestet=14`). **B06 bleibt deshalb laufen** —
es braucht keinen neuen Flottenbot, die Achse ist bereits registriert.

---

## 6. Der Umbau — was jetzt anders funktioniert

**Die Zahl, die ihn begründet** (§G31):

| Verfahren | nachweisbar ab | Beobachtungen |
|---|---:|---:|
| Schattenbetrieb am 10.10.2026 | 0,18–0,35 %/Tag | 31 Handelstage |
| **Historienlauf** | **0,0378 %/Tag** | **1.756 Handelstage** |
| wirtschaftlich entscheidend (§G23) | 0,0065 %/Tag | — |

**Der Historienlauf ist 5- bis 9-mal feiner** und liefert in Minuten
statt Monaten. Was gebaut wurde:

* **`scripts/32_lernlauf.py`** — 15 Achsen über 15 Jahresscheiben,
  Walk-Forward. Gruppiert Bots nach `signal_schluessel()`, sodass die
  teure Signalberechnung einmal je Gewichtssatz läuft statt einmal je Bot.
* **`simulate.run(signal_frames=...)`** — macht genau das möglich.
* **`lernlauf.sqlite`** — 5 Tabellen, jeder Lauf mit `code_version`.
* **`lernlauf_eval`** — gepaarter t-Wert + Trennschärfe je Bot.
* **`kandidatenregister`** — erzwungener Statusweg
  (`gefunden` → `im_schatten`|`verworfen` → `abgenommen`|`verworfen`),
  Pflicht-Hypothese, `n_varianten_getestet`.
* **`scripts/33_kandidaten.py`** — CLI dazu.

**Der verbindliche Weg einer Idee:**

```
1. Historienlauf   (Minuten)   darf VERWERFEN
2. Kandidatenregister          Voranmeldung mit Datum und Variantenzahl
3. Schattenbot     (Wochen)    einzige survivorship-freie Messung
4. Abnahme                     nach BETRIEBSPLAN §3.3
5. Live                        mit Dienstneustart und Regelabgleich
```

Stufe 3 darf **nur** überspringen, wer zeigen kann, dass Survivorship
die Frage nicht berührt. Für Ein-/Ausstiegsregeln ist das praktisch nie
der Fall.

### Das Warnsignal, das noch offen ist

Der Walk-Forward-Test beantwortet die Frage: *Trägt eine aus der
Historie getroffene Auswahl ins nächste, ungesehene Jahr?*

| Lauf | mittlere Differenz | t | Botwechsel |
|---|---:|---:|---|
| Probelauf 24.08. (8 J., 120 Sym.) | **−0,25 pp/Jahr** | −0,11 | **4 von 4** |
| Produktivlauf 25.08. (15 J., 792 Sym.) | **+6,80 pp/Jahr** | **+3,49** | 2 von 11 |

Schwelle bei 225 Zellen: **t > 3,79**. Der große Lauf liegt **knapp
darunter** — Urteil laut Vorgabe: **KEIN BEFUND**. Das Skript hält sich
an die vorab festgelegte Regel, obwohl die Zahl auffällig aussieht.
Genau dafür wurde sie vorher festgelegt.

**„Knapp keine" ist kein Freibrief, es ist „noch kein Befund".** Die
Verfahrensfrage bleibt offen, bis ein unabhängiger Lauf sie beantwortet.

---

## 7. Was als Nächstes zu tun ist

### Priorität 1 — Der Limitorder-Lauf

```bash
python scripts/36_limit_vergleich.py
```

**Begründung:** Die einzige gemessene Sache, die den zentralen Konflikt
(+0,11 % gegen 0,142 %) vollständig schließt. Alles ist gebaut, es
wurde nur nie gestartet. Kostet Minuten.

**Was danach zu tun ist, hängt vom Ergebnis ab:**
* *Negativ* → `K03` auf `verworfen`, Thema erledigt, ein Tag gespart.
* *Positiv* → **nicht live schalten.** Es braucht dann eine gemessene
  Füllquote (Papierdepot geht für diese Frage nicht) und liegt ohnehin
  unter der Sperre bis 10.10.

### Priorität 2 — EDGAR abwarten und richtig auswerten

Fertig ca. 28.08. **Nicht auf Teilergebnisse schauen** (§B4). Wenn er
bestanden hat: ins Kandidatenregister, dann Schattenbot — nicht direkt
live.

### Priorität 3 — Die zwei Randfälle, die bewusst offen blieben

1. **§G32:** Vor Handelsbeginn kann `_quote_plausibel` einen echten
   Kurssturz maskieren, weil die Referenz noch der Vortagesschluss ist.
   Vorschlag: `snapshots()`-Referenz verwerfen, wenn ihr Zeitstempel vor
   dem heutigen Handelsbeginn liegt. **Braucht einen Regressionstest,
   keine Schnellreparatur.**
2. **§G32 Nebenbefund:** Der Takt „1800 s bei geschlossener Börse"
   bedeutet bis zu ~30 Min Verzögerung nach Handelsbeginn. Bei DKS lag
   eine halbe Stunde zwischen Öffnung und Verkauf.

### Priorität 4 — Wikimedia Pageviews

Die einzige der vier ungenutzten Quellen, die revisionsfrei,
zeitpunktgenau ist und etwas misst, das in keiner Kursreihe steckt.

### Was NICHT zu tun ist

* **Keine Änderung an der Handelslogik vor dem 10.10.2026.** Das zerstört
  die Vergleichsbasis von `B11`.
* **Keine neuen Flottenbots vor dem 10.10.** Jeder hebt `schwelle_sigma`
  **rückwirkend für alle laufenden Messungen**.
* **Kein Prüfer lockern, damit eine Reparatur früher grün aussieht.**

---

## 8. Die Regeln, die nicht gebrochen werden dürfen

1. **Statistik:** immer `statistik.gruppierter_test`, maßgeblich sind
   **Handelstage**, nie Einzelwerte. Bei Mehrtages-Horizont `horizont=`
   übergeben — ohne das liegt die Fehlalarmquote bei **39,5 %** statt 5 %
   (§G12), und maßgeblich ist dann `t_ueberlappung`.
2. **Ein Parameter je Bot.** Sonst ist kein Unterschied zuzuordnen.
3. **Voranmeldung vor jedem Test.** Ohne sie ist ein späterer Treffer
   nicht von einer nachträglichen Erzählung zu unterscheiden.
4. **Der Versuchszähler bleibt.** Stillgelegte Bots zählen dauerhaft mit.
   Sie herauszunehmen wäre keine Aufräumaktion, sondern das nachträgliche
   Absenken der Hürde.
5. **Historie darf verwerfen, nie abnehmen** — Survivorship (§G11) und
   fehlender Nachrichtenfaktor (§G24).
6. **Nach jeder Codeänderung:** `22_tests.py` **und** `18_health_check.py`.
   Schlägt etwas fehl: **nicht neu starten**, erst beheben.
7. **Jeder gefundene Fehler bekommt einen Regressionstest UND eine
   Mutation.** Ein Test ohne Mutation ist eine Behauptung — §G20 hat
   gezeigt, dass eine Prüfung still zum No-Op werden kann.
8. **Fehler im Protokoll sind so ernst wie Fehler im Handel.** Eine
   falsche Messung führt zu falschen Entscheidungen mit echtem Geld.

**Die Unterscheidung, an der alles hängt:**

|  | Messapparat | Handelslogik |
|---|---|---|
| Beispiele | Protokoll, Wächter, Auswertung, Werkzeuge | `EngineConfig`, Ausstiegsregeln, Universum |
| Kosten | keine | **ein Versuchszählerplatz, dauerhaft** |
| Wann | jederzeit | nur vorangemeldet, eine Achse |
| Basisrate | — | **0 von 48** |

Am Messapparat darf und soll laufend gearbeitet werden. **Ein „Code 2.0",
der beides vermischt, kostet die Vergleichsbasis.**

---

## 9. Zahlen zum Nachschlagen

```
Vorsprung je Trade            +0,110 %
Rundlauf-Breakeven             0,142 %   (bei 5 bps Spread)
Breakeven bei 3 bps            0,102 %   <- hier trägt es

Versuche gesamt                     48   bestanden: 0
Flotten-Versuchszähler              16   Schwelle t > 2,85
Schwelle Lernlauf (225 Zellen)           t > 3,79
Schwelle Makro (40 Auswertungen)         t > 3,21
IC-Kanal, kalibriert                     t > 2,57

Tests                          496/496
Mutationen                       76/76
Symbolvorrat ab 1 Mio $/Tag      2.189
Universum live                   1.200
Universum Schatten                 789

Historie: 15 Jahre               3.767 Handelstage, 792 Symbole
Survivorship-Aufschlag             2–4 Prozentpunkte/Jahr
Score-Persistenz (gemessen)         0,49
Regimefilter sperrt                 18 % aller Handelstage

Entscheidungstermin B11        10.10.2026
```

**Wichtige Pfade:**

```
Daten    ~/Library/Application Support/alpaca-bot/data/
Logs     ~/Library/Logs/alpaca-bot/{daemon,shadow}.log
Dienste  ~/Library/LaunchAgents/de.local.alpaca{bot,schatten}.plist
```

**Dienste neu starten** (nach jeder Änderung an der Handelslogik):

```bash
launchctl bootout gui/$(id -u)/de.local.alpacabot
launchctl bootout gui/$(id -u)/de.local.alpacaschatten
# auf Prozessende warten, dann:
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/de.local.alpacabot.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/de.local.alpacaschatten.plist
```

---

## 10. Was dieses Projekt ehrlicherweise noch nicht kann

Damit die nächste Sitzung es nicht neu entdeckt:

* **Der zentrale Konflikt ist ungelöst.** +0,11 % gegen 0,142 %. Nur die
  Kostenseite (§G34) adressiert ihn — und die ist noch nicht gemessen.
* **Die Lernschleife ist offen** (§G25). Der Handelspfad liest kein
  gelerntes Artefakt. Das ist Absicht — ein sich selbst umschreibendes
  System wäre gefährlicher. Aber es heißt: **Nichts verbessert sich von
  allein.** Jede Verbesserung ist ein bewusster, gemessener,
  vorangemeldeter Schritt.
* **0 von 48.** Der Umbau macht das **Verwerfen** schneller, nicht das
  **Finden** wahrscheinlicher. Das ist trotzdem viel wert — 48
  Fehlversuche in Minuten statt in Jahren.
* **Die Verfahrensfrage aus §6 ist offen.** Ob eine aus der Historie
  getroffene Auswahl überhaupt ins nächste Jahr trägt, ist mit t=+3,49
  gegen Schwelle 3,79 **noch nicht beantwortet**.
* **Alles ist Papierkonto.** `ALPACA_PAPER=True`. Kein Ergebnis dieses
  Projekts ist je mit echtem Geld entstanden.
