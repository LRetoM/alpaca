# Leitfaden: Marktdaten, kostenlose APIs und was KI im Trading wirklich kann

Dieser Text beantwortet drei Fragen:
1. Woher bekomme ich kostenlos gute Daten?
2. Wie werte ich sie aus?
3. Wie weit trägt der KI-Ansatz — und wo hört er auf?

---

## Teil 1 — Was der kostenlose Alpaca-Plan hergibt

| Bereich | Kostenlos | Grenze |
|---|---|---|
| Paper Trading | unbegrenzt, 100.000 $ Spielgeld | — |
| Live Trading US-Aktien/ETFs | 0 $ Kommission | — |
| Aktien-Marktdaten | IEX-Feed, real-time | nur ~2 % des Handelsvolumens |
| Aktien-Historie | seit 2016, Tages- und Minutenbars | SIP nur 15 Min verzögert |
| Krypto | vollständig, real-time, 24/7 | keine |
| Optionen | Daten + Handel (Level 1–2) | Freischaltung nötig |
| News-API | Benzinga-Schlagzeilen im Stream | — |
| WebSocket-Streams | Trades, Quotes, Bars | 1 Verbindung gleichzeitig |
| Requests | 200 pro Minute | — |

**Was der IEX-Feed praktisch bedeutet:** Der Schlusskurs weicht minimal vom
offiziellen Konsolidierungskurs ab, und bei sehr illiquiden Werten fehlen
einzelne Bars. Für Tagesstrategien, Backtests und Lernen ist das irrelevant.
Relevant wird es erst, wenn du auf Sekundenbasis handelst — dann brauchst du
den SIP-Feed (kostenpflichtig, ~99 $/Monat).

---

## Teil 2 — Kostenlose Datenquellen jenseits von Alpaca

Kursdaten allein sind die dünnste Informationsschicht überhaupt. Diese Quellen
sind alle kostenlos und ohne Kreditkarte nutzbar:

### Kurse & Fundamentaldaten
| Quelle | Was | Zugang |
|---|---|---|
| **yfinance** (bereits installiert) | Kurse seit 1970er, Bilanzen, GuV, Cashflow, Dividenden, Splits, Analystenschätzungen, Insider | `pip`-Paket, kein Key |
| **SEC EDGAR full-text + XBRL API** | Original-Geschäftsberichte (10-K, 10-Q), Insider-Käufe (Form 4), 13F-Positionen großer Fonds | `data.sec.gov`, kein Key, nur User-Agent-Header |
| **Financial Modeling Prep** | Kennzahlen, Ratios, Screener | 250 Requests/Tag gratis |
| **Tiingo** | saubere EOD-Historie, News | 500/Tag, 1000 Symbole |
| **Alpha Vantage** | Kurse, Forex, Indikatoren, Fundamentals | 25 Requests/Tag |
| **Finnhub** | Earnings-Kalender, Sentiment, Insider | 60/Minute |

### Makro & Zinsen — die meist unterschätzte Ebene
| Quelle | Was |
|---|---|
| **FRED (St. Louis Fed)** | 800.000+ Zeitreihen: Zinsen, Inflation, Arbeitsmarkt, Geldmenge, Zinskurve. Kostenloser API-Key, kein Limit in der Praxis. **Die beste Datenquelle im Netz, Punkt.** |
| **ECB Data Portal** | Euro-Zinsen, EZB-Politik |
| **US Treasury** | Renditekurve täglich |

Warum das zählt: Die Differenz zwischen 10-jährigen und 3-monatigen
US-Staatsanleihen (FRED-Serie `T10Y3M`) hat vor jeder US-Rezession seit 1970
das Vorzeichen gewechselt. Kein Chartmuster hat auch nur annähernd diese
Trefferquote. Makrodaten sind langsam — aber sie sind das Vorzeichen, unter
dem alle schnellen Signale stehen.

### News & Sentiment
| Quelle | Was |
|---|---|
| **Alpaca News API** | Benzinga-Schlagzeilen, direkt im Stream |
| **SEC Form 4** | Insider-Käufe. Vorstände kaufen aus genau einem Grund. |
| **Reddit / StockTwits API** | Retail-Sentiment, brauchbar als Kontraindikator bei Extremen |
| **Google Trends (pytrends)** | Suchvolumen als Aufmerksamkeitsmaß |

---

## Teil 3 — Wie man Marktdaten auswertet: fünf Ebenen

Die meisten Anfänger arbeiten ausschließlich auf Ebene 1 — dort ist der
Wettbewerb am härtesten und die Information am dünnsten.

**Ebene 1 — Preis und Technik.** Trend, Momentum, Volatilität, Volumen.
Billig zu berechnen, jeder hat sie, deshalb ist der Vorsprung klein. Nützlich
vor allem für *Risikosteuerung* (wie groß ist die Position?), weniger für
Richtungsprognosen. → `indicators.py`

**Ebene 2 — Marktstruktur.** Korrelationen, Sektorrotation, Marktbreite (wie
viele Aktien steigen wirklich?), Zinskurve, Credit Spreads. Ein Index auf
Allzeithoch, getragen von fünf Aktien, ist ein anderer Markt als einer, der
von 400 getragen wird. Das sieht man nur hier. → `data.close_matrix()`

**Ebene 3 — Fundamental.** Umsatzwachstum, Margen, Verschuldung, Bewertung,
Cashflow. Wirkt über Monate bis Jahre, nicht über Tage. Die einzige Ebene mit
belastbarer akademischer Evidenz für langfristige Überrendite (Value, Quality,
Size). → yfinance, SEC EDGAR

**Ebene 4 — Makro.** Zinsen, Inflation, Liquidität, Konjunkturzyklus.
Bestimmt, welche Strategien überhaupt funktionieren. Trendfolge funktioniert
in Liquiditätsexpansion, Mean-Reversion in Seitwärtsmärkten. → FRED

**Ebene 5 — Verhalten und Positionierung.** Sentiment, Insider, Fondsflüsse,
Optionsmarkt. Am nützlichsten in Extremen: wenn alle bullisch sind, ist das
Geld schon investiert.

**Der eigentliche Vorsprung entsteht durch Kombination.** Ein Kaufsignal aus
Ebene 1, das gegen Ebene 4 läuft, ist meist ein Verlustgeschäft.

---

## Teil 4 — Was KI hier wirklich kann

Die Vorstellung, ein lernendes System könne Kursbewegungen zuverlässig
vorhersagen, ist verständlich, aber sie muss präzisiert werden. Es geht nicht
darum, ob KI hilft — sie hilft. Es geht darum, **wo** sie hilft.

### Warum reine Richtungsprognose so schwer ist

Aktienkurse sind zu etwa 95 % Rauschen und zu 5 % Signal. Und dieses Signal
ist **adaptiv**: Sobald ein Muster bekannt ist, handeln es genug Marktteilnehmer,
bis es verschwindet. Das unterscheidet Finanzmärkte fundamental von
Bilderkennung — eine Katze bleibt eine Katze, auch wenn ein Modell sie erkennt.
Ein Kursmuster hört auf zu existieren, sobald es erkannt wird.

Konkrete Zahlen zur Einordnung:
- Tägliche Richtung von SPY erraten: 53,5 % ist die Basisrate (Aufwärtsdrift).
- Ein gutes ML-Modell out-of-sample: **54–56 %**.
- Über 60 % out-of-sample auf Tagesdaten: **fast immer ein Datenleck im Code.**

Das klingt ernüchternd. Ist es aber nicht: 55 % Trefferquote, konsequent über
tausende Trades mit sauberem Risikomanagement angewendet, ist ein exzellentes
Geschäft. Genau davon lebt jedes Casino — mit 51,4 %.

### Wo maschinelles Lernen nachweislich funktioniert

Diese fünf Anwendungen sind deutlich lohnender als Richtungsprognose:

**1. Volatilitätsprognose.** Volatilität ist im Gegensatz zur Richtung stark
autokorreliert: Auf einen unruhigen Tag folgt mit hoher Wahrscheinlichkeit ein
unruhiger Tag. Modelle erreichen hier R² von 0,4–0,6 — eine ganz andere Welt
als bei Renditen. Nutzen: Positionsgröße steuern.
→ `backtest.volatility_target()`. **Der stärkste einzelne Hebel im ganzen
Projekt.** Die gleiche Strategie mit Volatilitätssteuerung hat typisch eine
30–50 % bessere Sharpe Ratio als ohne.

**2. Regime-Erkennung** — genau das „Trends erkennen, positive wie negative".
Statt „steigt die Aktie morgen?" die Frage: „In welchem Marktzustand sind wir?"
Ruhiger Aufwärtstrend, volatiler Abwärtstrend, Seitwärtsphase? Regime sind
persistent und dadurch prognostizierbar. Werkzeuge: Hidden-Markov-Modelle,
Clustering auf Vola/Korrelation/Breite. Nutzen: pro Regime die passende
Strategie aktivieren.

**3. Querschnitts-Ranking statt Zeitreihen-Prognose.** Nicht „steigt AAPL?",
sondern „welche 10 von 500 Aktien laufen im nächsten Monat am besten?"
Das ist ein deutlich leichteres Problem — relative Fehler heben sich auf, und
der Markttrend fällt heraus. Das ist der Ansatz, mit dem Quant-Fonds
tatsächlich arbeiten.

**4. Meta-Labeling.** Ein zweites Modell bewertet nicht *ob* gekauft wird,
sondern *wie sicher* das erste Signal ist, und skaliert die Position. Steigert
die Präzision, ohne neue Signale erfinden zu müssen. (Aus López de Prado,
*Advances in Financial Machine Learning* — das beste Buch zum Thema.)

**5. Textverarbeitung mit LLMs.** Hier ist der Vorsprung derzeit real und
groß, weil die Daten unstrukturiert sind: Geschäftsberichte, Earnings Calls,
Nachrichten. Ein LLM kann 200 Quartalsberichte auf Tonfall-Veränderungen
gegenüber dem Vorquartal durchsehen — das war vor drei Jahren nicht möglich.
Sprachliche Vorsicht im Management-Kommentar ist ein messbares Frühsignal.

### Wo es nicht funktioniert

- **Punktprognose des Kurses** („SPY steht in 30 Tagen bei 612,40").
  Ein LSTM sagt dabei im Wesentlichen den letzten Kurs vorher, leicht verzögert.
  Die Charts sehen beeindruckend aus und sagen nichts aus.
- **Deep Learning auf wenigen Jahren Tagesdaten.** 2.500 Datenpunkte bei
  95 % Rauschen — ein neuronales Netz lernt dort auswendig, nicht generalisierend.
  Gradient Boosting mit 20 durchdachten Features schlägt es fast immer.
- **Optimierung auf der gesamten Historie.** Wer 200 Parameterkombinationen
  durchprobiert und die beste nimmt, hat den Zufall optimiert, nicht die Strategie.

### Die vier Fallen, die die meisten Projekte killen

1. **Lookahead / Datenleck.** Zukunftsdaten sickern ins Training. Häufigste
   Ursache: `train_test_split(shuffle=True)` bei Zeitreihen. Der Backtest
   zeigt dann 300 % Rendite, live verliert es sofort.
   → Hier abgesichert durch `ml.walk_forward_predict()` mit Embargo.
2. **Survivorship Bias.** Eine Strategie auf den heutigen S&P-500-Mitgliedern
   zu testen ist Betrug an sich selbst — Enron, Lehman und WeWork fehlen im
   Datensatz. Alpacas Kursdaten enthalten delistete Werte nicht.
3. **Overfitting durch Mehrfachtesten.** Wer 100 Strategien testet, findet
   3 mit p < 0,05 rein zufällig. Gegenmittel: Ideen *vorher* aufschreiben,
   Testanzahl protokollieren, echte Out-of-Sample-Periode unberührt lassen.
4. **Kosten ignorieren.** Spread + Slippage sind bei Tagesstrategien 2–5
   Basispunkte pro Trade. Eine Strategie mit 200 Trades/Jahr braucht allein
   dafür 4–10 % Vorsprung. → `backtest()` rechnet sie deshalb immer mit.

---

## Teil 5 — Fahrplan

**Woche 1–2: Verstehen.**
`02_market_overview.py` täglich laufen lassen. Ziel ist nicht Handeln, sondern
ein Gefühl dafür, wie sich die Kennzahlen bewegen. Notiere jeden Tag *eine*
Beobachtung.

**Woche 3–4: Backtesten.**
`03_backtest.py` auf verschiedenen Symbolen und Zeiträumen. Die Lektion, die
hier fast alle machen: Fast nichts schlägt Buy & Hold nach Kosten. Das ist
kein Scheitern, das ist der Befund.

**Woche 5–6: Modellieren.**
`04_train_model.py`. Zuerst Richtungsprognose (wahrscheinlich Zufall), dann
Volatilität, dann Regime. Feature-Importance lesen, statt Genauigkeit zu jagen.

**Woche 7–8: Paper handeln.**
`05_paper_trade.py` täglich, mindestens 3 Monate. Erst hier zeigt sich, was
im Backtest unsichtbar war: Ausführungspreise, verpasste Signale, die eigene
Nervosität.

**Danach: klein live.** Mit einem Betrag, dessen Totalverlust dich nicht
berührt. Die Lücke zwischen Paper und echtem Geld ist psychologisch, nicht
technisch — und sie ist größer als erwartet.

---

## Ehrliche Schlussbemerkung

Ein sorgfältig gebautes System kann einen kleinen, statistisch echten Vorsprung
finden und ihn diszipliniert umsetzen. Das ist ein reales Ziel.

Was es nicht kann: den Markt „verstehen" oder zuverlässig vorhersagen. Die
Konkurrenz besteht aus Firmen mit Millisekunden-Anbindung, Doktoranden in der
Physik und Datensätzen, die sechsstellig pro Jahr kosten. Auf deren Feld — Sekunden
und Minuten — ist nichts zu holen.

Dein möglicher Vorsprung liegt woanders, und er ist echt: Du musst niemandem
quartalsweise Rechenschaft ablegen, du kannst monatelang nichts tun, du kannst
in Positionen investieren, die zu klein für institutionelles Geld sind, und du
kannst Zeithorizonte nutzen, die kein Fonds durchhält. Systematisches Vorgehen
ist dabei der eigentliche Gewinn: Der größte messbare Vorteil eines Regelsystems
gegenüber diskretionärem Handeln ist nicht die bessere Prognose — es ist, dass
es in Panik nicht verkauft.

**Weiterführend:** López de Prado, *Advances in Financial Machine Learning* ·
Ernest Chan, *Quantitative Trading* · Andreas Clenow, *Trading Evolved* ·
`quantpedia.com` (Strategie-Datenbank mit Papers)

---

*Dieses Dokument ist Dokumentation zu einem Softwareprojekt, keine
Anlageberatung.*
