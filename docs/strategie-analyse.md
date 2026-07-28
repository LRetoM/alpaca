# Strategie-Analyse: Was rentiert sich mathematisch, und wie testen wir es?

Antwort auf die Frage: 5000 Aktien überwachen, Ausbrüche erkennen, bevor sie
passieren — und das vorher sauber testen.

**Kurzfassung vorweg:** Deine Grundidee ist mathematisch richtig, und zwar aus
einem Grund, den du vielleicht noch nicht kennst (Teil A). Zwei Dinge an deinem
Testplan sind aber falsch und würden dich in die Irre führen — die 50-%-Quote
als Kriterium (Teil G.1) und die Datenbasis für 5000 Aktien (Teil F). Beides
ist reparierbar.

---

## Teil A — Die Mathematik: warum Breite schlägt Genauigkeit

### A.1 Das Fundamentalgesetz — der wichtigste Satz für deine Frage

Grinolds Fundamentalgesetz des aktiven Managements:

```
IR  ≈  IC × √BR
```

- **IR** = Information Ratio (Überrendite geteilt durch ihr Risiko — die Kennzahl, die zählt)
- **IC** = Information Coefficient: Korrelation zwischen deiner Prognose und dem, was wirklich passiert
- **BR** = Breadth: Anzahl **unabhängiger** Wetten pro Jahr

Was das bedeutet, ist bemerkenswert: **Genauigkeit geht linear ein, Breite mit
der Wurzel — aber Breite lässt sich um Größenordnungen leichter steigern.**

| Ansatz | IC | unabh. Wetten/Jahr | IR |
|---|---|---|---|
| 5 Aktien, sehr gut analysiert | 0,10 | 20 | 0,45 |
| **5000 Aktien, schwaches Signal** | **0,03** | **800** | **0,85** |
| 5000 Aktien, schwaches Signal, wöchentlich | 0,03 | 2500 | 1,50 |

Ein Analyst, der eine Aktie doppelt so gut versteht wie du, wird trotzdem
geschlagen von einem System, das 500-mal so viele Entscheidungen mit einem
winzigen Vorsprung trifft. **Das ist die mathematische Rechtfertigung deines
Plans.** Du brauchst kein gutes Modell. Du brauchst ein minimal besseres als
den Zufall, angewendet auf sehr viele Fälle.

**Die Falle in derselben Formel:** BR zählt *unabhängige* Wetten. Wenn du an
einem Tag 200 Tech-Aktien kaufst, ist das nicht 200-mal Breite — Tech-Aktien
korrelieren zu 0,7 miteinander, das sind effektiv vielleicht 8 Wetten. Breite
entsteht durch **Zeit** (viele Zeitpunkte) und **echte Verschiedenheit**
(Sektoren, Länder, Anlageklassen), nicht durch viele ähnliche Positionen.

Konsequenz für dein Design: über Sektoren **neutralisieren** und über die Zeit
streuen ist wertvoller als die Wachliste von 5000 auf 8000 zu vergrößern.

### A.2 Warum ausgerechnet Ausbrüche — die Schiefe der Renditen

Bessembinder (2018) hat alle US-Aktien seit 1926 untersucht:

- **57,8 %** aller Aktien haben über ihre Lebensdauer schlechter abgeschnitten als kurzlaufende Staatsanleihen.
- **4 %** aller Firmen erzeugen den **gesamten** Nettovermögenszuwachs des US-Aktienmarkts über T-Bills.
- Der Median-Aktie über ihre gesamte Börsenlebenszeit: **−3,7 %**.

Aktienrenditen sind also nicht normalverteilt, sondern extrem rechtsschief:
viele kleine Verluste, wenige gigantische Gewinne. Das ist die Struktur eines
Venture-Capital-Portfolios, nicht die eines Casinos.

**Daraus folgt dreierlei für dich:**

1. Deine Intuition — die wenigen Explosionen finden — greift genau den Teil
   der Verteilung an, in dem die gesamte Rendite steckt. Das ist der richtige
   Hebel.
2. Ein Portfolio aus wenigen Aktien verfehlt die 4 % mit hoher
   Wahrscheinlichkeit. **Breite ist hier nicht Risikostreuung, sondern die
   Bedingung dafür, überhaupt einen Treffer zu haben.**
3. **Deine Trefferquote wird niedrig sein — und das ist in Ordnung.** Genau
   deshalb ist dein 50-%-Kriterium das falsche Maß (Teil G.1).

### A.3 Was rein mathematisch am zuverlässigsten rentiert

Wenn man Erwartungswert gegen Verlässlichkeit abwägt, ist die Rangfolge
ziemlich eindeutig — und die ersten beiden Plätze belegen keine Signale:

| Rang | Hebel | Wirkung | Verlässlichkeit |
|---|---|---|---|
| 1 | **Kosten und Steuern senken** | +1–3 %/Jahr | **garantiert** |
| 2 | **Positionsgröße nach Volatilität** | Sharpe +30–50 % | sehr hoch |
| 3 | **Breite Diversifikation** | Risiko −40 % bei gleicher Rendite | sehr hoch |
| 4 | Faktor-Tilts (Quality, Momentum, Value) | +1–3 %/Jahr | mittel–hoch |
| 5 | Querschnitts-Ranking mit ML | +1–4 %/Jahr | mittel |
| 6 | Event-Erkennung (dein Plan) | hoch, aber schief | mittel–niedrig |
| 7 | Kurzfristige Richtungsprognose | ~0 | niedrig |

Der einzige garantierte Alpha-Quell ist die Kostenseite. Ein Prozent gesparte
Gebühren ist mathematisch identisch mit einem Prozent Überrendite — nur ohne
Risiko und ohne Prognose. Deine Beobachtung, dass Daytrading an Gebühren
scheitert, trifft genau diesen Punkt: **Du hast den wichtigsten Hebel
intuitiv schon richtig identifiziert.**

---

## Teil B — Landkarte der Strategien weltweit

Bewertung: Evidenz = Qualität der akademischen Belege. Lebt noch? = funktioniert
nach Veröffentlichung und Kosten heute noch. Für dich? = mit Alpaca + freien
Daten + realistischem Kapital umsetzbar.

### B.1 Querschnitt-Faktoren (Aktien gegeneinander ranken)

| Strategie | Horizont | Evidenz | Lebt noch? | Für dich? |
|---|---|---|---|---|
| **Momentum (12-1 Monate)** | 3–12 M | sehr stark | ja, aber Crash-anfällig | **ja** |
| **Quality / Gross Profitability** | 6–24 M | stark | ja | **ja** |
| **Net Share Issuance** (Firma gibt Aktien aus vs. kauft zurück) | 12 M | stark | ja, unterschätzt | **ja** |
| **Low Volatility** | 12 M | stark | ja | ja |
| Value (Buchwert/Kurs) | 3–10 J | stark | strittig, 2010er katastrophal | ja, mit Geduld |
| Size (klein schlägt groß) | 12 M | schwach | nur kombiniert mit Quality | bedingt |
| Investment / Asset Growth | 12 M | stark | ja | ja |
| Accruals (Bilanz-Qualität) | 12 M | stark | abgeschwächt | ja |

### B.2 Ereignisgetrieben — hier liegt dein Ansatz

| Strategie | Horizont | Evidenz | Lebt noch? | Für dich? |
|---|---|---|---|---|
| **PEAD** (Drift nach Gewinnüberraschung) | 1–3 M | **sehr stark** | ja — eine der langlebigsten Anomalien überhaupt | **ja, klar** |
| **Insiderkäufe (SEC Form 4)** | 1–12 M | stark | ja, besonders bei Nebenwerten | **ja, Daten frei** |
| **Analysten-Revisionen** | 1–3 M | stark | ja | ja |
| **52-Wochen-Hoch-Ausbruch** | 3–12 M | stark (George & Hwang) | ja | **ja** |
| Spin-offs | 12–24 M | mittel | teilweise | ja |
| Index-Aufnahme | Tage | früher stark | weitgehend wegarbitriert | nein |
| Merger-Arbitrage | 1–6 M | stark | ja, aber institutionell | eher nein |
| Short Squeeze (hohe Short-Quote + Stärke) | Tage–Wochen | mittel | ja, extrem riskant | vorsichtig |
| Biotech-Katalysatoren (FDA-Termine) | Tage | mittel | ja | ja, mit Fachwissen |

### B.3 Zeitreihen / Makro

| Strategie | Horizont | Evidenz | Lebt noch? | Für dich? |
|---|---|---|---|---|
| **Trendfolge (Managed Futures)** | 1–12 M | sehr stark, 100+ Jahre belegt | ja | ja, über ETFs |
| **Carry** (FX, Rohstoffe, Anleihen) | 1–12 M | sehr stark | ja | bedingt |
| Volatilitäts-Risikoprämie (Optionen verkaufen) | 1 M | stark | ja — mit Katastrophen-Tails | **nein, noch nicht** |
| Saisonalität (Sell in May, Januar) | — | schwach | überwiegend Data-Mining | nein |
| Zinskurven-Regime | 6–24 M | stark | ja | ja, als Filter |

### B.4 Was für dich strukturell unerreichbar ist

Market Making, HFT-Latenzarbitrage, Order-Flow-Vorhersage aus Level-2-Daten,
Sekunden-Statistical-Arbitrage. Dort konkurrierst du gegen Firmen mit
Mikrowellenstrecken zwischen Chicago und New Jersey. **Auf diesem Feld ist für
dich nichts zu holen — aber das ist kein Verlust, denn es ist nicht das Feld,
auf dem du spielen wolltest.**

### B.5 Die ernüchternde Metastudie

McLean & Pontiff (2016) haben 97 publizierte Anomalien nachgerechnet:

- **−26 %** Rendite bereits im Zeitraum zwischen Datenende und Veröffentlichung
- **−58 %** nach der Veröffentlichung

Übersetzt: Mehr als die Hälfte jedes Effekts, über den du in einem Paper liest,
ist bereits weg. Was übrig bleibt, ist die Hälfte einer ohnehin kleinen Zahl.
Rechne bei allem in Teil B mit dem halben publizierten Effekt — dann bist du
ungefähr richtig.

---

## Teil C — Faktoren-Katalog: was beobachten, wie verlässlich?

**PIT** = point-in-time-sicher: Ist der Wert später revidiert worden? Wenn ja,
enthält deine Historie Wissen, das es damals nicht gab.

### C.1 Kurs & Volumen — kostenlos, sofort verfügbar

| Variable | Aussagekraft | PIT | Quelle |
|---|---|---|---|
| Momentum 12-1 Monate | mittel | ✅ | Alpaca |
| Abstand zum 52-Wochen-Hoch | mittel | ✅ | Alpaca |
| Volatilitätskompression (Bollinger-Squeeze) | mittel | ✅ | berechnet |
| Volumen-Z-Score | mittel–hoch | ✅ | Alpaca |
| Dollar-Volumen-Trend (Liquiditätszufluss) | mittel | ✅ | Alpaca |
| Relative Stärke zum Sektor | mittel | ✅ | berechnet |
| Illiquidität (Amihud-Maß) | mittel | ✅ | berechnet |
| Gap-Häufigkeit, Lücken-Verhalten | schwach | ✅ | Alpaca |
| RSI, MACD, Stochastik einzeln | **sehr schwach** | ✅ | berechnet |

> Der letzte Punkt ist wichtig: Klassische Indikatoren allein haben in
> sauberen Tests fast keinen Prognosewert. Ihr Nutzen liegt in der
> **Kombination und im Risikomanagement**, nicht im Einzelsignal.

### C.2 Fundamental — kostenlos über SEC EDGAR + yfinance

| Variable | Aussagekraft | PIT | Achtung |
|---|---|---|---|
| **Nettoemission von Aktien** | hoch | ✅ EDGAR | unterschätzt, stark |
| **Gross Profitability** | hoch | ⚠️ | Restatements! EDGAR-Datum nutzen |
| Gewinnüberraschung (SUE) | hoch | ⚠️ | Konsensschätzung ist selten PIT |
| Free Cashflow Yield | mittel–hoch | ⚠️ | |
| Verschuldung / Zinsdeckung | mittel | ⚠️ | |
| Umsatzwachstum-Beschleunigung | mittel | ⚠️ | |
| KGV isoliert | schwach | ⚠️ | ohne Quality wertlos |

**Die PIT-Falle bei Fundamentaldaten:** yfinance liefert die *heutige,
korrigierte* Bilanz. Ein Unternehmen, das 2019 seine Zahlen nach unten
korrigiert hat, sieht in deiner Historie für 2018 schon korrigiert aus — du
"wusstest" den Betrug vor der Aufdeckung. **Immer das EDGAR-Einreichungsdatum
als Verfügbarkeitszeitpunkt verwenden, nie das Quartalsende.** Regel: Ein
Q4-Bericht ist frühestens 45–90 Tage nach Quartalsende bekannt.

### C.3 Ereignisse & Insider — kostenlos, PIT-perfekt

| Variable | Aussagekraft | PIT | Quelle |
|---|---|---|---|
| **Insiderkäufe Form 4, geclustert** | hoch | ✅ perfekt | SEC EDGAR |
| **8-K Material Events** | hoch | ✅ perfekt | SEC EDGAR |
| Einreichungszeitpunkt selbst (Freitag 17 Uhr = schlechte Nachricht) | mittel | ✅ | EDGAR |
| 13F-Positionen großer Fonds | mittel | ⚠️ 45 Tage Verzug | EDGAR |
| Sprachliche Veränderung im 10-K vs. Vorjahr | mittel–hoch | ✅ | EDGAR + LLM |
| Aktienrückkaufprogramme | mittel | ✅ | 8-K |

> SEC EDGAR ist die beste Datenquelle in diesem ganzen Katalog: kostenlos,
> zeitgestempelt auf die Sekunde, seit 1994, keine Revisionen, keine
> Survivorship-Lücke. **Wenn du nur eine externe Quelle anbindest, dann diese.**

### C.4 Makro — kostenlos über FRED

| Variable | Aussagekraft | PIT | Achtung |
|---|---|---|---|
| **Zinskurve 10J−3M (`T10Y3M`)** | hoch für Regime | ✅ | Marktdaten, nicht revidiert |
| **Credit Spreads (`BAMLH0A0HYM2`)** | hoch für Regime | ✅ | Risikoappetit in Echtzeit |
| Financial Conditions Index | hoch | ✅ | |
| Arbeitsmarkt, BIP, Inflation | mittel | ❌ **stark revidiert** | FRED ALFRED für PIT-Vintages |
| Einkaufsmanagerindex | mittel | ✅ | |

> **FRED vs. ALFRED:** Normale FRED-Serien enthalten die *revidierten* Werte.
> Die BIP-Zahl für Q1 2020 sah bei Erstveröffentlichung völlig anders aus als
> heute. Für PIT-Backtests brauchst du ALFRED (Vintage-Datenbank, ebenfalls
> kostenlos). Marktbasierte Serien (Zinsen, Spreads) werden nicht revidiert
> und sind unproblematisch.

### C.5 News, Text, Aufmerksamkeit

| Quelle | Reichweite | Historie | PIT | Kosten |
|---|---|---|---|---|
| **Alpaca News API (Benzinga)** | alle US-Aktien | ~2015+ | ✅ zeitgestempelt | **frei** |
| **GDELT** | global, alle Sprachen | 1979 / 2015+ | ✅ | **frei** (BigQuery) |
| **SEC EDGAR Volltext** | alle US-Emittenten | 2001+ | ✅ perfekt | **frei** |
| Wikipedia-Seitenaufrufe | global | 2015+ | ✅ stündlich | **frei** |
| Common Crawl News | global | 2016+ | ✅ | frei, groß |
| StockTwits / Reddit | Retail-Sentiment | wechselhaft | ⚠️ Löschungen | frei/eingeschränkt |
| **Google Trends** | global | 2004+ | ❌ **nicht PIT** | frei |

> **Google Trends ist für Backtests unbrauchbar** — die Werte sind auf den
> Abfragezeitraum normalisiert und werden rückwirkend neu skaliert. Dieselbe
> Abfrage liefert morgen andere Zahlen für 2019. Viele veröffentlichte
> "Google-Trends sagt Aktien voraus"-Studien haben genau daran gekrankt.

---

## Teil D — Was geht Explosionen tatsächlich voraus?

Das ist deine Kernfrage. Was die Literatur und saubere Tests hergeben,
sortiert nach Belastbarkeit:

**Belastbar:**

1. **Volatilitätskompression vor Expansion.** Volatilität ist stark
   autokorreliert und cluster-bildend. Eine ungewöhnlich enge Handelsspanne
   über Wochen geht überdurchschnittlich oft einer großen Bewegung voraus —
   **aber die Richtung sagt sie nicht vorher.** Nutzbar für "wann", nicht "wohin".
2. **Volumen vor Preis.** Ungewöhnliches Volumen ohne Preisbewegung deutet auf
   Akkumulation. Der Effekt ist bei kleinen, wenig beachteten Werten deutlich
   messbar, bei Large Caps praktisch weg.
3. **Geclusterte Insiderkäufe.** Mehrere Insider kaufen unabhängig innerhalb
   weniger Wochen — einer der stärksten Einzelprädiktoren, die frei verfügbar
   sind. Verkäufe sagen dagegen fast nichts (Insider verkaufen aus tausend
   Gründen).
4. **PEAD.** Nach einer positiven Gewinnüberraschung läuft der Kurs noch
   1–3 Monate weiter. Seit 1968 dokumentiert, funktioniert immer noch.
5. **52-Wochen-Hoch-Ausbruch mit Volumen.** Der Abstand zum 52-Wochen-Hoch ist
   ein besserer Momentum-Prädiktor als die Rendite selbst.
6. **Nettoemission negativ** (Firma kauft eigene Aktien zurück, verwässert nicht).

**Wackelig, aber untersuchenswert:**

7. Kombination hohe Short-Quote + beginnende relative Stärke (Squeeze-Setup)
8. Kleiner Streubesitz + steigende Aufmerksamkeit (Wikipedia-Aufrufe, News-Frequenz)
9. Analysten-Erstabdeckung eines vorher unbeachteten Werts
10. Sprachliche Tonveränderung im Quartalsbericht gegenüber Vorquartal

**Unbelastbar, trotz Popularität:**

- Chartformationen (Kopf-Schulter, Tassen-Henkel, Dreiecke). In
  regelbasierten Tests ohne Vorhersagewert. Sie *wirken* überzeugend, weil das
  menschliche Auge Muster in Rauschen findet und die Fehlschläge vergisst.
- Fibonacci-Retracements, Elliott-Wellen, Gann-Winkel.
- Einzelne Indikator-Überkreuzungen ohne Kontext.

**Der entscheidende Punkt zu deinem Vorhaben:** Kein Einzelsignal aus dieser
Liste hat einen IC über ~0,05. Der Wert entsteht durch **Kombination vieler
schwacher, wenig korrelierter Signale** — genau das, was ein Mensch nicht kann
und ein Modell schon. Dort liegt dein "kaum ein Mensch könnte das erkennen",
und nur dort.

---

## Teil E — Der Nachrichten-Teil deines Plans

**Ja, es gibt News zu praktisch allen US-Aktien, kostenlos, historisch:** die
Alpaca News API (Benzinga-Feed) liefert zeitgestempelte Schlagzeilen ab ca.
2015 für alle gelisteten US-Werte. Das ist bereits in deinem Konto enthalten.

**Aber — und das ist die harte Grenze deines Bitcoin-Beispiels:**

Für 2011 gibt es keine brauchbare freie Nachrichten-Historie zu Bitcoin. Der
Benzinga-Feed beginnt ~2015, GDELT 2.0 ebenfalls. Die damalige Diskussion fand
auf `bitcointalk.org` und in IRC-Kanälen statt, nicht in indexierten Medien.
**Der Test „hätten wir Bitcoin 2011 aus Nachrichten erkennen können" ist mit
freien Daten nicht ehrlich durchführbar** — und ein Test, den man nicht ehrlich
durchführen kann, ist schlimmer als kein Test, weil er falsche Sicherheit gibt.

**Die ehrliche Variante:** Nimm den Zeitraum ab 2016 und teste dort — es gibt
genug Explosionen (NVDA 2016 und 2023, TSLA 2020, GME 2021, SMCI 2023, die
Krypto-Zyklen 2017/2020/2024). Das sind hunderte Ereignisse mit sauberer
Nachrichtenhistorie. Das reicht statistisch vollkommen aus, und es ist
überprüfbar.

**Was aus Nachrichten realistisch herauszuholen ist:**

| Signal aus News | Stärke |
|---|---|
| **Frequenz-Anomalie** (plötzlich 5× so viele Artikel wie üblich) | mittel–hoch |
| **Erstabdeckung** (Werte, über die vorher nie berichtet wurde) | mittel |
| Tonalität / Sentiment | schwach–mittel, stark überschätzt |
| Themen-Cluster über viele Firmen (früher Sektortrend) | mittel |
| Nachrichten *nach* dem Kurssprung | **null** — genau die Falle, die du vermeiden willst |

Der letzte Punkt beschreibt exakt das Problem, das du selbst benannt hast. Es
hat einen Namen: **Look-ahead durch Publikationsverzögerung.** Der Artikel
"NVDA springt 24 % nach Quartalszahlen" trägt ein Datum, das *nach* der
Bewegung liegt — aber wenn du Tagesdaten mit Tages-News zusammenführst, landet
er im selben Zeitfenster wie der Kurssprung, und dein Modell "erkennt" den
Sprung mit 100 % Genauigkeit. Deshalb baue ich in den Code einen harten
Zeitstempel-Wächter (`pit.py`) mit einstellbarer Verzögerung ein.

---

## Teil F — Das größte Risiko deines 5000-Aktien-Plans

**Survivorship Bias.** Alpaca liefert Kursdaten nur für heute noch gelistete
Symbole. Wenn du heute 5000 Ticker abfragst und 10 Jahre zurücktestest, ist
jede einzelne Firma in deinem Datensatz eine, die überlebt hat. Alle
Pleiten, Delistings und Übernahmen zu Ramschpreisen fehlen.

Größenordnung: Etwa **8–12 % der US-Listings verschwinden pro Jahr**. Über
10 Jahre fehlt dir damit ein erheblicher Teil der Grundgesamtheit — und zwar
systematisch der schlechteste. Studien beziffern die künstliche Überrendite
auf **2–4 Prozentpunkte pro Jahr**. Das ist mehr, als deine ganze Strategie
je verdienen wird. Bei Nebenwerten ist der Effekt noch größer, und Nebenwerte
sind genau dort, wo dein Ansatz am besten funktionieren sollte.

**Drei Auswege, in dieser Reihenfolge:**

1. **Messen statt ignorieren.** Denselben Test auf Large Caps (wenig
   betroffen) und Small Caps (stark betroffen) laufen lassen. Divergiert das
   Ergebnis stark, weißt du, dass der Bias arbeitet.
2. **Universum rekonstruieren.** Historische Index-Mitgliedschaften aus
   ETF-Holdings-Archiven oder Wikipedia-Versionsgeschichte nachbauen. Mühsam,
   aber kostenlos und für den S&P 500 / Russell 1000 machbar.
3. **Bezahlen.** Nasdaq Data Link `SHARADAR/SEP` kostet ca. 50 $/Monat und
   enthält delistete Werte mit korrekten Delisting-Renditen. Das ist die mit
   Abstand günstigste echte Lösung — und der einzige Punkt in diesem ganzen
   Projekt, an dem ich Geld ausgeben würde, bevor irgendetwas gehandelt wird.

Zwischenlösung für den Anfang: **Teste zuerst auf dem S&P 500 und Russell
1000.** Dort ist der Bias klein genug, um Methodik zu validieren. Erst wenn das
Verfahren dort trägt, auf 5000 Werte gehen.

---

## Teil G — Das Testprotokoll: dein wichtigster Teil

### G.1 Warum „über 50 % bei 1000 Versuchen" das falsche Kriterium ist

Zwei Gründe, beide entscheidend:

**Grund 1: Trefferquote misst bei schiefen Auszahlungen das Falsche.**

Deine Strategie sucht Explosionen. Das Auszahlungsprofil sieht so aus: viele
kleine Verluste (−5 %, Stop greift), wenige riesige Gewinne (+200 %). Rechne:

| Trefferquote | Ø Gewinn | Ø Verlust | Erwartungswert je Trade |
|---|---|---|---|
| 25 % | +80 % | −10 % | **+12,5 %** ✅ ausgezeichnet |
| 50 % | +8 % | −9 % | −0,5 % ❌ Verlust |
| 70 % | +3 % | −12 % | −1,5 % ❌ Verlust |

**Eine Trefferquote von 25 % kann exzellent und eine von 70 % ruinös sein.**
Ein System auf Trefferquote zu optimieren, treibt dich systematisch dazu,
Gewinne zu früh mitzunehmen und Verluste laufen zu lassen — der klassische
Weg, sich langsam zu ruinieren.

**Was du stattdessen messen musst:**

| Kennzahl | Bedeutung | Zielwert |
|---|---|---|
| **Erwartungswert je Trade** | nach Kosten! | > 0, deutlich |
| **Profit-Faktor** | Summe Gewinne / Summe Verluste | > 1,3 |
| **Information Coefficient** | Rangkorrelation Prognose ↔ Realität | > 0,02 |
| **Deflated Sharpe Ratio** | Sharpe, korrigiert um Anzahl der Versuche | > 0 |
| Max Drawdown | musst du real aushalten | < 25 % |

**Grund 2: 1000 Versuche sind nicht 1000 Versuche.**

Die Stichprobengröße, die du brauchst, um einen echten Vorsprung von der
Zufallsschwankung zu trennen:

```
n  ≈  (z_α + z_β)² · p(1−p) / (p − p₀)²
```

Für einen 5-Prozentpunkte-Vorsprung (55 % vs. 50 %), 95 % Konfidenz, 80 %
Power: **n ≈ 610**. Für 2 Prozentpunkte: **n ≈ 3.900**.

**Dein Bauchgefühl mit den 1000 Versuchen liegt also gut** — für einen
deutlichen Effekt. Aber: Das müssen **unabhängige** Versuche sein. 1000 Trades
in derselben Woche über 1000 korrelierte Aktien sind statistisch **ein**
Versuch mit 1000 Nachkommastellen. Wenn im März 2020 alles gleichzeitig fällt,
hast du keine 400 Beobachtungen, sondern eine.

**Faustregel:** Effektive Stichprobe ≈ Anzahl unabhängiger Zeitfenster ×
Anzahl unkorrelierter Sektoren. Für 610 echte Beobachtungen brauchst du
realistisch **8–10 Jahre Historie über mehrere Marktregime**.

### G.2 Das Drei-Umschlag-Protokoll

Der Grund, warum die meisten selbstgebauten Systeme scheitern, ist nicht
schlechtes ML — es ist, dass dieselben Daten hunderte Male angeschaut werden,
bis irgendetwas funktioniert. Dagegen hilft nur Disziplin *vor* dem ersten Test:

```
┌──── Umschlag 1: ENTWICKLUNG ────┬─ Umschlag 2: WALK-FORWARD ─┬─ Umschlag 3: TRESOR ─┐
│  2016 – 2021                     │  2022 – 2024               │  2025 – heute        │
│  hier darfst du alles probieren  │  ehrliche Validierung      │  EINMAL. Nie wieder. │
└──────────────────────────────────┴────────────────────────────┴──────────────────────┘
```

**Regeln, die nicht verhandelbar sind:**

1. Umschlag 3 wird **erst geöffnet, wenn du glaubst, fertig zu sein.** Genau
   einmal. Ist das Ergebnis schlecht, ist die Idee tot — nicht „nachjustieren
   und nochmal". Nach dem zweiten Blick ist der Tresor kein Tresor mehr.
2. **Jede** getestete Variante wird protokolliert, auch die verworfenen. Wer
   200 Varianten testet, findet 10 mit p < 0,05 durch reinen Zufall. Die
   Deflated Sharpe Ratio korrigiert dafür — aber nur, wenn du die Zahl kennst.
3. Hypothese **vor** dem Test aufschreiben. „Insiderkäufe in Clustern sagen
   Outperformance über 3 Monate voraus" — dann testen. Nicht: testen, Muster
   sehen, Erklärung erfinden.

### G.3 Die Ereignisstudie — genau der Test, den du beschrieben hast

Dein abgeschottetes System ist methodisch eine **Event Study**, und das ist
ein etabliertes Verfahren. Ablauf:

```
        Beobachtungsfenster            Sperrzone        Ereignis
   ├──────────────────────────────┤  ├─────────┤  ├─────────────────┤
   t−120                       t−5    t−5 … t₀        t₀ … t+60
   NUR diese Daten sieht          hier passiert    die Explosion,
   das Modell                     der Ausbruch     die es zu finden galt
```

Der Punkt ist die **Sperrzone**: Die letzten Tage vor dem Ausbruch werden
verworfen. Ohne sie lernt das Modell, den Ausbruch an seinem eigenen Anfang zu
erkennen — was trivial und wertlos ist, weil du dann schon zu spät bist.

**Und der Test, den fast alle vergessen: die Kontrollgruppe.** Für jedes
Explosions-Ereignis brauchst du 20–50 zufällige Nicht-Ereignisse aus
demselben Zeitraum und Sektor. Ohne sie misst du nur, wie Aktien allgemein
aussehen, nicht, wie explodierende Aktien aussehen. Das ist der häufigste
Fehler in selbstgebauten Event-Studien.

### G.4 Der Negativ-Test, der dich vor dir selbst schützt

Bevor du irgendeinem positiven Ergebnis glaubst, muss dein System diese vier
Prüfungen **bestehen, indem es nichts findet**:

| Test | Erwartetes Ergebnis |
|---|---|
| Labels zeitlich zufällig durchmischen | IC ≈ 0. Wenn nicht → Leck |
| Auf reinem Random-Walk laufen lassen | kein Signal. Wenn doch → Overfit |
| Alle Features um 30 Tage in die Zukunft schieben | Ergebnis muss **besser** werden. Wenn nicht → Features tot |
| Zufällig eine von 100 Aktien wählen | schlechter als das Modell. Wenn nicht → kein Alpha |

Ein System, das auf Zufallsdaten Muster findet, findet auch auf echten Daten
Muster — nur eben keine echten. Diese vier Tests laufen in `06_event_study.py`
automatisch mit.

---

## Teil H — Der Fahrplan

### Phase 0 — Infrastruktur (jetzt, ~1 Woche)
Point-in-Time-Wächter, Ereigniserkennung, News-Anbindung, Universum.
**Kein einziger Trade, kein einziges Modell.** Diese Phase entscheidet über
alles Weitere: Ein Backtest auf undichter Infrastruktur ist nicht ein bisschen
falsch, sondern vollständig wertlos.

### Phase 1 — Ereignisse verstehen (2–3 Wochen)
Alle Bewegungen über +50 % in 60 Tagen seit 2016 finden. Deskriptiv anschauen:
Wie sahen diese Werte 120 Tage vorher aus? Volumen, Volatilität, News-Frequenz,
Insiderkäufe — jeweils **gegen die Kontrollgruppe**. Ergebnis dieser Phase ist
kein Modell, sondern eine Liste plausibler Hypothesen.

### Phase 2 — Einzelsignale messen (2–3 Wochen)
Jede Hypothese **einzeln** auf ihren IC prüfen. Erwartung: Die meisten haben
IC ≈ 0. Zwei bis vier werden bei 0,02–0,04 liegen. Das sind deine Bausteine.
Ein einzelnes Signal mit IC 0,03 klingt nach nichts — mit Breite ist es genau
das, was Teil A.1 braucht.

### Phase 3 — Kombination (3–4 Wochen)
Gradient Boosting über die überlebenden Signale, Ziel ist **Ranking**, nicht
Klassifikation: „Welche 50 der 5000 Aktien haben die höchste Wahrscheinlichkeit
für eine große Bewegung?" Walk-Forward mit Embargo, sektorneutral.

### Phase 4 — Portfolio (2 Wochen)
Aus dem Ranking ein Portfolio bauen: Positionsgrößen nach Volatilität,
Sektorlimits, maximaler Anteil je Position, Rebalancing-Frequenz. **Hier
entsteht mehr Rendite als in Phase 3.**

### Phase 5 — Tresor öffnen (1 Tag)
Umschlag 3. Einmal. Ergebnis akzeptieren.

### Phase 6 — Paper Trading (mindestens 6 Monate)
Täglich laufen lassen, jede Abweichung zwischen erwarteter und tatsächlicher
Ausführung protokollieren. Diese Lücke ist real und beträgt bei Nebenwerten
oft mehrere Prozent.

### Phase 7 — Klein live
Erst wenn Phase 6 trägt. Mit einem Betrag, dessen Totalverlust dich nicht
berührt.

**Realistischer Zeithorizont bis zum ersten echten Trade: 6–9 Monate.** Wer
das abkürzt, kürzt genau die Phasen ab, die verhindern, dass er sein Geld
verliert.

---

## Zusammenfassung: was an deinem Plan stimmt und was nicht

**Richtig, und zwar aus gutem Grund:**
- Breite statt Tiefe (Fundamentalgesetz: IR = IC × √BR)
- Ausbrüche als Ziel (Bessembinder: 4 % der Aktien machen die gesamte Rendite)
- Langer Horizont statt Daytrading (Kosten sind der einzige garantierte Alpha-Hebel)
- Vorher testen statt handeln (das trennt dich von 95 % aller Hobby-Trader)
- Strikt nur Vor-Ereignis-Daten verwenden (der Kern jeder ehrlichen Validierung)

**Muss korrigiert werden:**
- 50 % Trefferquote als Kriterium → Erwartungswert und Profit-Faktor
- 1000 Versuche → 1000 **unabhängige** Versuche, das braucht 8–10 Jahre Historie
- 5000 Aktien aus Alpaca → Survivorship Bias, erst auf Large/Mid Caps validieren
- Bitcoin 2011 aus News → keine freie Nachrichtenhistorie vor 2015, ab 2016 testen

**Was du unterschätzt:**
Positionsgröße und Portfoliokonstruktion bringen mehr als das Prognosemodell.
Phase 4 wird deine Rendite stärker verändern als Phase 3.

**Was du überschätzt:**
Dass ein Modell Dinge sieht, „die kaum ein Mensch erkennen könnte". Es sieht
dieselben Dinge — nur gleichzeitig, bei 5000 Werten, ohne Müdigkeit und ohne
Angst. Das ist der ganze Vorteil. Er reicht völlig aus.
