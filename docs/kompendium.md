# Kompendium: Handelsstrategien, Chartanalyse und Marktfaktoren

Die Arbeitsgrundlage des Projekts. Jeder Eintrag ist nach Belastbarkeit
bewertet — nicht nach Popularität. Das ist der wesentliche Unterschied zu
den meisten Trading-Ressourcen im Netz: Was sich gut verkauft und was
nachweislich funktioniert, sind zwei fast disjunkte Mengen.

**Verwandte Dokumente:** [strategie-analyse.md](strategie-analyse.md) (Mathematik
und Testprotokoll) · [leitfaden.md](leitfaden.md) (Einstieg, Datenquellen)

---

## Wie dieses Dokument zu lesen ist

### Bewertungsskala

| Stufe | Bedeutung |
|---|---|
| ★★★★★ | Über Jahrzehnte, Märkte und Anlageklassen repliziert. Überlebt Kosten. |
| ★★★★☆ | Solide Belege, mehrfach unabhängig repliziert. Nach Veröffentlichung abgeschwächt. |
| ★★★☆☆ | Belege vorhanden, aber Replikation uneinheitlich oder stark kostenabhängig. |
| ★★☆☆☆ | Schwache oder widersprüchliche Belege. Vermutlich Data-Mining. |
| ★☆☆☆☆ | Keine belastbaren Belege. Populär, aber in sauberen Tests wertlos. |

### Die drei Zahlen, die jede Euphorie dämpfen sollten

1. **Hou, Xue & Zhang (2020, *Review of Financial Studies*)** haben 447
   publizierte Anomalien nachgerechnet. **65 % ließen sich nicht
   replizieren.** Zwei von drei Effekten, über die es ein Paper gibt,
   existieren bei sauberer Methodik nicht.
2. **McLean & Pontiff (2016, *Journal of Finance*)** zeigen: Was übrig
   bleibt, verliert nach Veröffentlichung **26–58 %** seiner Wirkung.
3. **Jensen et al. (2023, *Journal of Finance*)** halten dagegen — mit
   bayesianischer Methodik und globalen Daten replizieren deutlich mehr
   Faktoren. Die Wahrheit liegt dazwischen.

**Arbeitsregel für dieses Projekt: Rechne mit der Hälfte jedes
publizierten Effekts.** Dann liegst du ungefähr richtig.

---

# TEIL 1 — CHARTANALYSE

## 1.1 Die unangenehme Befundlage

Du hast gefragt, ob wir Charts gut genug lesen können, um kurzfristige
Anstiege früh genug zu erkennen. Die ehrliche Antwort in einem Satz:

> **Klassische Chartformationen: nein. Volatilitäts- und Volumenstruktur:
> teilweise ja — aber für das „wann", nicht für das „wohin".**

Die wichtigste Arbeit dazu ist **Lo, Mamaysky & Wang (2000), „Foundations
of Technical Analysis"** (*Journal of Finance*). Sie haben Chartmuster
erstmals algorithmisch statt visuell identifiziert — mit Kernel-Regression,
also ohne den menschlichen Bias, im Nachhinein Muster zu sehen. Ergebnis:
Einige Formationen tragen **statistisch signifikante Zusatzinformation**.
Aber die Autoren betonen selbst, dass statistische Signifikanz nicht
Handelbarkeit bedeutet — nach Spread und Gebühren bleibt kaum etwas.

**Savin, Weller & Zvingelis (2007)** untersuchten speziell Kopf-Schulter-
Formationen auf S&P 500 und Russell 2000 (1990–1999). Sie fanden
Prognosewert vor allem bei den kleineren Russell-2000-Werten — also genau
dort, wo Spread und Illiquidität den Vorteil wieder auffressen.

**Warum Chartformationen trotzdem so überzeugend wirken:** Das
menschliche Auge findet Muster in Rauschen (Apophänie), erinnert
Treffer und vergisst Fehlschläge (Bestätigungsfehler), und jede Formation
ist im Nachhinein eindeutig, vorher aber mehrdeutig. Auf einem Random-Walk-
Chart findest du genauso viele „perfekte" Tassen-Henkel-Formationen wie
auf einem echten. Das kannst du in diesem Projekt selbst nachprüfen —
`scripts/00_selftest.py` erzeugt genau solche Zufallscharts.

## 1.2 Chartmuster im Einzelnen

| Muster | Bewertung | Anmerkung |
|---|---|---|
| **Volatilitätskompression → Expansion** | ★★★★☆ | Der einzige robuste „Chart"-Effekt. Volatilität ist stark autokorreliert. Sagt **wann**, nicht **wohin**. |
| **52-Wochen-Hoch-Ausbruch** | ★★★★☆ | George & Hwang (2004). Der Abstand zum 52-Wochen-Hoch schlägt die Rendite als Momentum-Maß. |
| **Volumen-Ausbruch ohne Preisbewegung** | ★★★☆☆ | Akkumulationshinweis. Messbar bei Nebenwerten, bei Large Caps praktisch weg. |
| **Gap-Verhalten (Ausbruchslücken)** | ★★★☆☆ | Overnight-Gaps mit Nachrichtenbezug haben Drift. Ohne Nachricht: Rauschen. |
| Gleitende-Durchschnitt-Kreuzungen | ★★☆☆☆ | Funktioniert in Trendmärkten, verliert in Seitwärtsphasen. Als **Filter** brauchbar, als Signal schwach. |
| Unterstützung / Widerstand | ★★☆☆☆ | Runde Zahlen zeigen schwache Clustereffekte. Weit unterhalb der Handelskosten. |
| Kopf-Schulter | ★★☆☆☆ | Siehe oben — marginal, kostenabhängig, bei Nebenwerten nicht handelbar. |
| Dreiecke, Flaggen, Wimpel | ★★☆☆☆ | Im Kern verkleidete Volatilitätskompression. Der Effekt steckt in der Kompression, nicht in der Form. |
| Tasse mit Henkel | ★☆☆☆☆ | Keine kontrollierte Studie mit positivem Befund. |
| Doppel-Top / Doppel-Boden | ★☆☆☆☆ | Im Nachhinein eindeutig, vorher nicht abgrenzbar. |
| **Fibonacci-Retracements** | ★☆☆☆☆ | Keine theoretische Grundlage, keine empirische Bestätigung. |
| **Elliott-Wellen** | ★☆☆☆☆ | Nicht falsifizierbar — die Wellenzählung wird nachträglich angepasst. |
| **Gann-Winkel, Astro-Zyklen** | ★☆☆☆☆ | Keine Evidenz. |

## 1.3 Indikatoren

Alle in [indicators.py](../src/alpaca_bot/indicators.py) implementiert.

| Indikator | Als Einzelsignal | Tatsächlicher Nutzen |
|---|---|---|
| **ATR** | — | ★★★★★ **für Positionsgröße und Stop-Abstand.** Der nützlichste Indikator überhaupt — und keiner, der Richtung vorhersagt. |
| **Realisierte Volatilität** | — | ★★★★★ für Risikosteuerung (`backtest.volatility_target`). |
| SMA 200 | ★★☆☆☆ | ★★★★☆ als **Regime-Filter**: „nur long über dem 200-Tage-Schnitt" verbessert fast jede Strategie. |
| MACD | ★★☆☆☆ | ★★★☆☆ als Momentum-Bestätigung in Kombination. |
| RSI (14) | ★★☆☆☆ | Schwach. In Trends bleibt er lange extrem. |
| RSI (2) | ★★★☆☆ | Kurzfrist-Mean-Reversion auf **Indizes/ETFs** — nicht auf Einzelaktien. |
| Bollinger %B | ★★☆☆☆ | Nützlich als Feature, schwach als Signal. |
| Bollinger-Bandbreite | ★★★★☆ | Misst die Volatilitätskompression — siehe 1.2. |
| Stochastik, CCI, Williams %R | ★☆☆☆☆ | Redundant zum RSI. |
| Ichimoku | ★★☆☆☆ | Bündel bekannter Effekte, kein eigener Beitrag. |
| Volumen-Z-Score | ★★★☆☆ | Aufmerksamkeitsmaß, in Kombination wertvoll. |
| OBV, Chaikin | ★★☆☆☆ | Schwach, stark parameterabhängig. |

> **Das Muster ist eindeutig:** Indikatoren, die *Risiko* messen (ATR,
> Volatilität, Bandbreite), sind wertvoll. Indikatoren, die *Richtung*
> vorhersagen sollen, sind es kaum. Genau deshalb steckt der Hebel in
> Positionsgröße statt in Einstiegssignalen.

---

# TEIL 2 — STRATEGIEFAMILIEN

## 2.1 Querschnitt-Faktoren (Aktien gegeneinander ranken)

| Strategie | Bewertung | Horizont | Für dich? |
|---|---|---|---|
| **Momentum 12-1** | ★★★★★ | 3–12 M | ja — Jegadeesh & Titman (1993), weltweit repliziert |
| **Quality / Gross Profitability** | ★★★★☆ | 6–24 M | ja — Novy-Marx (2013) |
| **Nettoemission von Aktien** | ★★★★☆ | 12 M | ja, unterschätzt — Daten frei über EDGAR |
| **Investment / Asset Growth** | ★★★★☆ | 12 M | ja |
| **Low Volatility** | ★★★★☆ | 12 M | ja — Ang et al. (2006) |
| Value (B/P, FCF-Yield) | ★★★☆☆ | 3–10 J | ja, mit sehr viel Geduld — 2010er katastrophal |
| Accruals | ★★★☆☆ | 12 M | ja — Sloan (1996), abgeschwächt |
| Size (klein > groß) | ★★☆☆☆ | 12 M | nur kombiniert mit Quality |
| Betting-against-Beta | ★★★☆☆ | 12 M | schwer ohne Hebel umsetzbar |

**Momentum-Crashes:** Daniel & Moskowitz (2016) — Momentum verliert in
Erholungsphasen nach Crashs katastrophal (März–Mai 2009: −73 %). Ein
Volatilitätsfilter halbiert diesen Effekt. Wer Momentum handelt, muss das
einbauen.

## 2.2 Ereignisgetrieben — dein Ansatz

| Strategie | Bewertung | Horizont | Datenquelle |
|---|---|---|---|
| **PEAD (Drift nach Gewinnüberraschung)** | ★★★★★ | 1–3 M | frei — seit Bernard & Thomas (1989), eine der langlebigsten Anomalien |
| **Insiderkäufe, geclustert** | ★★★★☆ | 1–12 M | **frei, PIT-perfekt** — SEC Form 4 |
| **Analysten-Revisionen** | ★★★★☆ | 1–3 M | teilweise frei |
| **52-Wochen-Hoch-Ausbruch** | ★★★★☆ | 3–12 M | frei |
| Aktienrückkauf-Ankündigungen | ★★★☆☆ | 6–24 M | frei (8-K) |
| Spin-offs | ★★★☆☆ | 12–24 M | frei |
| Short Squeeze (hohe Quote + Stärke) | ★★☆☆☆ | Tage–Wochen | teuer, sehr riskant |
| Merger-Arbitrage | ★★★★☆ | 1–6 M | institutionell dominiert |
| Index-Aufnahme | ★☆☆☆☆ | Tage | wegarbitriert |

> **Insiderkäufe verdienen besondere Aufmerksamkeit:** kostenlos,
> sekundengenau zeitgestempelt, keine Survivorship-Lücke, und einer der
> wenigen Effekte, der bei Nebenwerten *stärker* ist. Verkäufe sagen
> dagegen fast nichts — Insider verkaufen aus tausend Gründen, kaufen aber
> nur aus einem.

## 2.3 Zeitreihen und Makro

| Strategie | Bewertung | Anmerkung |
|---|---|---|
| **Trendfolge (Managed Futures)** | ★★★★★ | Über 100+ Jahre und alle Anlageklassen belegt. Für dich über ETFs. |
| **Carry** | ★★★★☆ | FX, Rohstoffe, Anleihen. |
| Volatilitäts-Risikoprämie | ★★★★☆ | Reale Prämie — mit Katastrophentails. **Nicht als Einsteiger.** |
| Zinskurven-Regime | ★★★★☆ | `T10Y3M` als Filter, nicht als Signal. |
| Saisonalität (Sell in May) | ★★☆☆☆ | Überwiegend Data-Mining. |
| Turn-of-Month | ★★★☆☆ | Robuster als andere Kalendereffekte, aber winzig. |

## 2.4 Was strukturell unerreichbar ist

Market Making · HFT-Latenzarbitrage · Order-Flow-Vorhersage aus Level-2 ·
Sekunden-Statistical-Arbitrage. Dort konkurrierst du gegen Firmen mit
Mikrowellenstrecken. **Kein Verlust — es war nie dein Feld.**

---

# TEIL 3 — RISIKO UND PORTFOLIO

Dieser Teil bringt mehr Rendite als Teil 1 und 2 zusammen. Er wird fast
immer übersprungen.

## 3.1 Positionsgröße

| Verfahren | Bewertung | Anmerkung |
|---|---|---|
| **Volatilitäts-Targeting** | ★★★★★ | Position ∝ 1/Volatilität. Sharpe +30–50 %. `backtest.volatility_target()` |
| **ATR-basierte Größe** | ★★★★★ | Risiko je Trade fix in % des Depots, Stop = 2·ATR. |
| **Fractional Kelly (¼–½)** | ★★★★☆ | Volles Kelly ist mathematisch optimal und praktisch unaushaltbar. |
| Feste Stückzahl | ★☆☆☆☆ | Ignoriert Risiko vollständig. |
| Martingale / Verdopplung | ☆☆☆☆☆ | Führt mit Sicherheit zum Totalverlust. |

## 3.2 Ausstieg

| Verfahren | Bewertung |
|---|---|
| **ATR-Trailing-Stop** | ★★★★☆ — passt sich der Volatilität an |
| **Zeitbasierter Ausstieg** | ★★★★☆ — unterschätzt; „nach 20 Tagen raus" schlägt oft komplexe Regeln |
| Fester Prozent-Stop | ★★★☆☆ — ignoriert, dass 5 % bei TSLA und KO Verschiedenes bedeuten |
| Bracket (Ziel + Stop vorab) | ★★★★☆ — der Ausstieg steht fest, bevor die Emotion einsetzt |
| Kein Stop | ★★☆☆☆ — bei breit diversifizierten Indexpositionen vertretbar, bei Einzelaktien nicht |

## 3.3 Portfoliokonstruktion

- **Gleichgewichtung** ★★★★☆ — schlägt in Studien erstaunlich oft die optimierte Variante (DeMiguel et al. 2009)
- **Risk Parity** ★★★★☆ — nach Risikobeitrag statt nach Kapital
- **Sektorneutralität** ★★★★☆ — verhindert, dass ein Modell nur „Tech" lernt
- **Mean-Variance-Optimierung** ★★☆☆☆ — extrem empfindlich gegenüber Schätzfehlern
- **Maximale Positionsgröße** ★★★★★ — die einfachste wirksame Regel überhaupt

---

# TEIL 4 — DEINE FRAGE: KURZFRISTIGE ANSTIEGE FRÜH GENUG ERKENNEN?

Zusammenführung aller Befunde:

**Aus reinen Charts: nein.** Die Effektstärken liegen unter den
Handelskosten. Das kannst du selbst messen: `costs.breakeven_move_pct()`
zeigt, dass bei 5 bps Spanne bereits 0,14 % Bewegung nötig sind, nur um
bei null herauszukommen — bei Nebenwerten mit 50 bps über 1 %.

**Aus Kombination mehrerer schwacher Quellen: eingeschränkt ja.** Die
realistische Erwartung ist ein IC von 0,02–0,05. Klingt nach nichts —
ist über 5000 Werte und viele Zeitpunkte aber genau das, was das
Fundamentalgesetz braucht (`IR ≈ IC × √BR`, siehe
[strategie-analyse.md](strategie-analyse.md)).

**Die aussichtsreichste Kombination**, nach erwartetem Beitrag:

1. Insiderkäufe geclustert (SEC Form 4) — frei, PIT-perfekt
2. Gewinnüberraschung + PEAD-Fenster
3. News-Frequenz-Anomalie ([news.py](../src/alpaca_bot/news.py))
4. Volatilitätskompression + Volumenanstieg
5. Relative Stärke zum Sektor
6. Nettoemission negativ

**Und der Zeithorizont ist entscheidend:** „Kurzfristig" im Sinne von
Tagen ist strukturell verschlossen — PDT-Regel unter 25.000 $ und
Kostenschwelle. „Kurzfristig" im Sinne von 1–3 Monaten ist der Bereich,
in dem PEAD und Insider-Effekte leben. **Deine ursprüngliche Intuition,
Daytrading zu vermeiden, war richtig — und zwar aus mehr Gründen, als du
damals genannt hast.**

---

# TEIL 5 — QUELLEN

## Bücher (nach Nutzen für dieses Projekt)

1. **López de Prado, *Advances in Financial Machine Learning*** — das
   wichtigste Buch. Purged CV, Meta-Labeling, Deflated Sharpe Ratio.
2. **Grinold & Kahn, *Active Portfolio Management*** — Herkunft des
   Fundamentalgesetzes.
3. **Ernest Chan, *Quantitative Trading*** / *Algorithmic Trading* — praktisch, ehrlich.
4. **Andreas Clenow, *Trading Evolved*** — Python-basierte Umsetzung.
5. **Bailey & López de Prado, „The Deflated Sharpe Ratio"** — Korrektur für Mehrfachtesten.

## Kernpapiere

| Thema | Quelle |
|---|---|
| Replikationskrise | Hou, Xue & Zhang (2020), *RFS*; Jensen et al. (2023), *JF* |
| Anomalie-Zerfall | McLean & Pontiff (2016), *JF* |
| Renditeschiefe | Bessembinder (2018), *JFE* |
| Chartmuster | Lo, Mamaysky & Wang (2000), *JF* |
| Momentum | Jegadeesh & Titman (1993); Daniel & Moskowitz (2016) |
| 52-Wochen-Hoch | George & Hwang (2004), *JF* |
| Profitabilität | Novy-Marx (2013), *JFE* |
| PEAD | Bernard & Thomas (1989) |
| Naive Diversifikation | DeMiguel, Garlappi & Uppal (2009), *RFS* |

## Verlässliche Online-Quellen

| Quelle | Wofür |
|---|---|
| **quantpedia.com** | Strategie-Datenbank mit Paper-Verweisen |
| **alphaarchitect.com** | Faktorforschung, ungewöhnlich ehrlich über Grenzen |
| **SSRN / NBER** | Originalpapiere, kostenlos |
| **global-q.org** | Hou/Xue/Zhang Replikationsdaten |
| **cxoadvisory.com** | Systematische Prüfung populärer Behauptungen |
| **quantitativo.com**, **Robot Wealth** | Praxisnahe, methodisch saubere Blogs |

## Quellen, denen du nicht trauen solltest

Alles mit Renditeversprechen · Signaldienste · Kurse ohne
Out-of-Sample-Nachweis · Backtests ohne Kosten · YouTube-Chartanalyse
ohne Trefferstatistik · „Ich habe 10.000 $ in 30 Tagen verdoppelt" —
Überlebensauswahl in Reinform. Auf 1000 Zufallstrader kommen immer
einige mit spektakulären Ergebnissen; nur die schreiben darüber.

---

## Der eine Satz, der bleiben sollte

Die Strategien in diesem Dokument sind der leichte Teil — sie sind
öffentlich, jeder kann sie lesen. Der schwere Teil ist die Disziplin,
sie unverändert durchzuhalten, wenn sie sechs Monate lang nicht
funktionieren. Genau dafür sind [journal.py](../src/alpaca_bot/journal.py)
und [selfcheck.py](../src/alpaca_bot/selfcheck.py) gebaut.

---

*Dokumentation zu einem Softwareprojekt, keine Anlageberatung.*
