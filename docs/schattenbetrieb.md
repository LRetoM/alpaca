# Schattenbetrieb und Bot-Flotte: Lernen ohne zu handeln

Stand: 2026-07-29 · Grundlage: Code-Stand `b40f4f3`

Vollständiger Umsetzungsplan. Das Dokument ist so geschrieben, dass sich
daraus zu einem späteren Zeitpunkt ohne weitere Vorarbeit implementieren
lässt.

---

## Inhalt

0. [Sofort machbar — vier Schritte vor dem Schattenbetrieb](#0-sofort-machbar--vier-schritte-vor-dem-schattenbetrieb)
1. [Zielsetzung — und was daran realistisch ist](#1-zielsetzung--und-was-daran-realistisch-ist)
2. [Was an der Idee richtig ist](#2-was-an-der-idee-richtig-ist)
3. [Fünf Korrekturen](#3-fünf-korrekturen)
4. [Architektur](#4-architektur)
5. [Die Bot-Flotte](#5-die-bot-flotte)
6. [Statistische Disziplin](#6-statistische-disziplin)
7. [Attribution: woran lag es?](#7-attribution-woran-lag-es)
8. [Datenmodell](#8-datenmodell)
9. [Tagesablauf](#9-tagesablauf)
10. [Externes Wissen: das Hypothesenregister](#10-externes-wissen-das-hypothesenregister)
11. [Der Musterspeicher](#11-der-musterspeicher)
12. [Kaltstart aus vorhandenen Daten](#12-kaltstart-aus-vorhandenen-daten)
13. [Regimebedingung — wo der echte Gewinn liegt](#13-regimebedingung--wo-der-echte-gewinn-liegt)
14. [Korrektheitssicherungen](#14-korrektheitssicherungen)
15. [Auswertung](#15-auswertung)
16. [Phasenplan](#16-phasenplan)
17. [Was das System nicht leistet](#17-was-das-system-nicht-leistet)

---

## 0. Sofort machbar — vier Schritte vor dem Schattenbetrieb

Nicht jede Verbesserung muss auf den Schattenbetrieb warten. Diese vier
Punkte nutzen **ausschließlich bereits vorhandene Daten**
(`data/cache/bars/yfinance_2168_*_8y.parquet`, 9 Jahre Faktor-Labor,
`journal.sqlite`) und sind unabhängig vom restlichen Plan diese oder
nächste Woche erledigbar. Sie sind bewusst von den Phasen in §16
getrennt, weil sie einer anderen Regel folgen: **Korrektur und
Bestandsaufnahme dürfen sofort passieren — eine neue Handelsregel
daraus ableiten darf es nicht**, ohne Vorwärtsbestätigung (§0.5).

### 0.1 Die simulate.py-Zeitlücke schließen

**Befund, siehe §4.4:** `simulate.py:236` bucht Käufe zum
**Eröffnungskurs**. Der Live-Bot handelt laut `daemon.py:56` aber
frühestens **20 Minuten nach Eröffnung** (`open_delay_minutes = 20`) —
bewusst, weil die Eröffnungsspanne die teuerste Phase des Tages ist.

Jeder bisherige Backtest hat also mit einem Kurs gerechnet, den der
echte Bot grundsätzlich nie bekommt. Wie groß die Differenz ist, weiß
niemand — sie wurde nie gemessen.

**Vorgehen:** Für eine Stichprobe beide Kurse gegenüberstellen:
Eröffnungskurs gegen Kurs 20 Minuten danach. Ergibt sich ein spürbarer
systematischer Unterschied, ist `simulate.py` zu korrigieren — und alle
bisherigen Kennzahlen neu zu ziehen.

#### ERLEDIGT 2026-07-29 — Ergebnis: keine Korrektur nötig

Gemessen mit 5-Minuten-Daten (yfinance), 119 der liquidesten Symbole,
60 Handelstage, 7.140 Beobachtungen. Kandidaten wurden mit dem echten
`build_reversal_frame()` **inklusive SPY-Regimefilter** bestimmt, also
genau so, wie der Bot entscheidet. Gemessen wurde die Drift vom
Eröffnungskurs (09:30) zum tatsächlichen Kaufzeitpunkt (09:50):

| Gruppe | n | Mittel | t | 95-%-Band |
|---|---|---|---|---|
| Alle Beobachtungen | 7.140 | +3,39 bps | +0,77 | [−5,4; +12,2] |
| Umkehr-Kandidaten (Score ≥ 0,35) | 1.212 | **−0,58 bps** | −0,18 | [−22,5; +18,8] |
| Starke Kandidaten (Score ≥ 0,55) | 459 | −4,78 bps | −0,32 | [−33,8; +24,5] |

**Befund:** Für genau die Werte, die der Bot kauft, ist die Drift
statistisch nicht von null unterscheidbar (t = −0,18) und
wirtschaftlich vernachlässigbar gegenüber den bereits angesetzten
**8,0 bps** Spread + Slippage je Seite (`SimConfig`). Das Vorzeichen ist
sogar leicht günstig — Kaufen um 09:50 war im Mittel minimal billiger
als zur Eröffnung, nicht teurer.

**Konsequenz:** `simulate.py` wird **nicht** geändert. Die
Eröffnungskurs-Annahme ist für diese Strategie unbedenklich, und eine
Änderung ohne belegten Effekt würde nur Komplexität einführen.

**Einschränkung, die stehen bleiben muss:** 60 Handelstage sind eine
kleine Stichprobe; das 95-%-Band schließt einen Effekt von ±20 bps
nicht aus. Die Aussage lautet also „kein Effekt nachweisbar", nicht
„Effekt bewiesen ausgeschlossen". Sobald der Schattenbetrieb läuft,
wird dieselbe Größe fortlaufend mitgemessen (§4.4,
`entry_price_open` vs `entry_price`) — dann mit wachsender Stichprobe
und ohne Zusatzaufwand.

### 0.2 Kosten gegen Score-Schwelle prüfen

`daemon.py`s eigener Docstring enthält bereits die Warnung: *"die
Simulation zeigt, dass die Kosten den Vorsprung bei diesem Umschlag
aufzehren."* Das ist eine im Projekt schon gemessene, aber noch nicht
in eine Regeländerung umgesetzte Erkenntnis.

**Vorgehen:** Mit `10_simulate.py` und dem vorhandenen Cache
`min_score` für die Reversal-Strategie in Stufen durchlaufen (aktuell
0,35 — testen z. B. 0,40 / 0,45 / 0,50 / 0,55) und **Netto**-Rendite
nach Kosten (`costs.py`, bereits eingebunden) sowie Umschlag je Stufe
vergleichen. Weniger, aber überzeugendere Trades können den
Kosten-Vorsprung verbessern, auch ohne dass sich die Trefferquote
ändert.

**Wichtig:** Das Ergebnis dieses Laufs ist ein **Kandidat**, keine
sofortige Config-Änderung — siehe §0.5. Es entscheidet, welche Stufe
im Schattenbetrieb als `B05_schwelle_hoch` (§5.3) vorrangig getestet
wird, nicht die Produktionswerte direkt.

#### ERLEDIGT 2026-07-29 — Ergebnis: die Schwelle ist nicht das Problem

400 liquideste Symbole, 5 Jahre (2021-08 bis 2026-07), Startkapital
100.000 $, Kosten wie in `SimConfig` (5 bps Spread + 3 bps Slippage +
Gebühren), Reversal-Strategie:

| min_score | Netto-Rendite 5 J | Sharpe | Trades | Trefferquote | Kosten / \|Brutto\| |
|---|---|---|---|---|---|
| 0,35 (aktuell) | **+7,36 %** | 0,18 | 3.049 | 52,0 % | 0,72 |
| 0,45 | −0,79 % | 0,04 | 2.943 | 51,6 % | **1,09** |
| 0,55 | +2,66 % | 0,10 | 2.673 | 51,4 % | 0,86 |
| 0,65 | −0,48 % | 0,05 | 2.317 | 50,5 % | **1,08** |
| 0,75 | +1,28 % | 0,08 | 1.867 | 49,2 % | 0,94 |

**Referenz Buy & Hold SPY im selben Zeitraum: +80,71 %.**

Vier Befunde, alle unbequem:

1. **Jede Schwelle verliert dramatisch gegen Buy & Hold** — um 73 bis
   81 Prozentpunkte. Die beste Variante macht ~1,4 % pro Jahr, weniger
   als risikoloser Zins.
2. **Kein monotoner Zusammenhang.** Die Werte springen
   (+7,4 / −0,8 / +2,7 / −0,5 / +1,3). Ein echter Effekt zeigte einen
   Trend; dieses Zickzack ist die Signatur von Rauschen. Eine höhere
   Schwelle löst das Kostenproblem also **nicht**.
3. **Die Kosten fressen den Vorsprung vollständig** — 72 bis 109 % des
   Bruttogewinns. Bei 0,45 und 0,65 übersteigen die Kosten den
   Bruttogewinn. Das bestätigt die Warnung in `daemon.py`s eigenem
   Docstring quantitativ.
4. **Der Score sortiert am oberen Ende falsch.** Die Trefferquote
   *sinkt* mit steigender Schwelle (52,0 % → 49,2 %). Wäre die
   Rangliste gut, müsste sie steigen. Genau das ist die Frage, die der
   Schattenbetrieb vorwärts beantworten soll — hier ist sie rückwärts
   schon negativ.

**Einordnung, fairerweise:** Das Fenster 2021–2026 enthält einen sehr
starken Bullenmarkt. Eine Long-only-Umkehrstrategie, die oft in Cash
steht, hinkt dort strukturell hinterher. Das entschuldigt aber nicht
die absolute Schwäche (1,4 %/Jahr) und schon gar nicht Befund 3 und 4 —
die sind benchmark-unabhängig.

**Konsequenz für den Plan:** Die Schwellen-Achse (`B05_schwelle_hoch`,
§5.3) verliert an Priorität — sie ist gemessen wirkungslos. Wichtiger
werden die **Kosten-/Umschlag-Achse** (weniger handeln, länger halten)
und die Frage, ob der Score überhaupt sortiert (§15, Kalibrierung).
Der Live-Bot bleibt aus genau diesem Grund im Papierdepot: Es geht um
Infrastruktur und Messung, nicht um Ertrag.

### 0.3 PEAD historisch vortesten

Die vielversprechendste News-Hypothese aus §10.2b — Post-Earnings-
Announcement-Drift setzt sich über Wochen fort und passt damit zu
einer Architektur, die ohnehin erst am nächsten Handelstag ausführt.

**Vorgehen:** Aus `edgar.py`/`news.py` (oder ersatzweise aus
Ergebnisterminen, falls verfügbar) Gewinnüberraschungen der
Vergangenheit ziehen, mit `research.py`s Querschnitts-IC-Maschinerie
den IC von "Überraschung am Tag X" gegen Rendite an X+5/X+10/X+20
messen. Ein bis zwei Tage Aufwand, kein Warten auf neue Daten.

Ergibt sich ein IC mit |t| > 2, wandert PEAD als `HYP`-Eintrag
(§10.4) direkt in den Vorwärtstest, sobald der Schattenbetrieb steht —
mit Priorität vor der breiteren Ereignistyp-Liste.

### 0.4 Regime-Muster explorieren — als Kandidat, nicht als Entscheidung

Auf den 9 Jahren Faktor-Labor-Daten lässt sich schon heute rechnen, ob
z. B. `reversal_3d` in ruhiger und hektischer Marktvolatilität
unterschiedlich stark trägt (die Regimemerkmale aus §13 lassen sich
rückwirkend berechnen).

**Ausdrückliche Einschränkung:** Das ist Hypothesenbildung, keine
Bestätigung. Ein auf denselben historischen Daten gefundener
Regime-Split, der direkt in die Produktionsregeln übernommen wird,
wiederholt exakt den Fehler, den `research.py`s eigener Docstring
dokumentiert — die Momentum-Strategie, die aus plausibel aussehenden,
aber erst danach gemessenen Faktoren gebaut wurde und 127
Prozentpunkte gegen Buy & Hold verlor.

**Vorgehen:** Befund im Musterspeicher (§11) als `status='kandidat'`
ablegen, mit `entdeckt_aus='historie'`. Er wird erst zu
`status='bestaetigt'`, wenn er auch auf Daten hält, die zum Zeitpunkt
der Entdeckung noch nicht existierten (§11, Verfallsprüfung-Logik
rückwärts angewendet: erst bestätigen, dann vertrauen).

### 0.5 Die Regel, die alle vier Punkte zusammenhält

Bewusst zweigeteilt:

| Erlaubt sofort | Erst nach Vorwärtsbestätigung |
|---|---|
| Korrektur nachweisbarer Fehler (0.1) | Neue Stop/Ziel/Schwellen-Werte in Produktion übernehmen |
| Bestandsaufnahme vorhandener Daten (0.2–0.4) | Bot-gegen-Bot-Entscheidung der Flotte (§6.4) |
| Kandidaten für den Musterspeicher anlegen | Regime-Split als Handelsregel |

Der Unterschied: 0.1 behebt einen **Fehler**, unabhängig davon, was er
zeigt. 0.2–0.4 erzeugen **Kandidaten**, die genauso gut in die falsche
Richtung zeigen könnten — und deren Wert erst durch die in diesem Plan
aufgebaute Vorwärtsprüfung feststeht, nicht durch die Historie allein.

---

## 1. Zielsetzung — und was daran realistisch ist

Das erklärte Ziel: ein Bot, der Kurse mit der Zeit immer zuverlässiger
vorhersagt, und ein System, das dafür laufend Daten sammelt, speichert
und auswertet, bis klare Muster entstehen.

Das ist erreichbar — aber über einen anderen Mechanismus, als die
Formulierung nahelegt. Der Unterschied ist wichtig genug, um ihn an den
Anfang zu stellen.

**Die Richtungstrefferquote hat eine harte Obergrenze.** `docs/leitfaden.md`
kalibriert sie auf 54–56 % out-of-sample; `ml.py` sagt im Kopfkommentar
dasselbe und ergänzt: alles über 60 % ist fast immer ein Datenleck. Kein
Datenvolumen der Welt verschiebt diese Grenze, weil sie nicht aus
Datenmangel entsteht, sondern daraus, dass an einem liquiden Markt viele
gut ausgestattete Teilnehmer dasselbe versuchen.

**Was dagegen tatsächlich und dauerhaft besser wird**, wenn Daten
auflaufen:

| Hebel | Warum er trägt | Erwarteter Gewinn |
|---|---|---|
| **Regimebedingung** — wissen, *wann* der Vorsprung wirkt | Der Umkehr-Effekt ist nicht immer gleich stark. Ihn nur in tragenden Regimen zu handeln, erhöht den Vorsprung je Trade, ohne die Prognose zu verbessern | **hoch** |
| **Größenbestimmung über Volatilitätsprognose** | Volatilität ist ungleich besser vorhersagbar als Richtung (R² ~0,6 gegen ~0,01). Richtig skalieren schlägt besser raten | **hoch** |
| **Kosten und Umschlag** | Mechanisch, sicher, sofort messbar. Der Faktor-Labor-Befund lautet bereits: der Vorsprung existiert, die Kosten fressen ihn | **hoch** |
| **Ausstiegsregeln** (Stop, Ziel, Haltedauer) | MAE/MFE beantworten das direkt und brauchen nur genug abgeschlossene Trades | **mittel-hoch** |
| **Ausschluss von Fehlerfällen** | Zu wissen, wo man verliert, ist wertvoller als zu raten, wo man gewinnt | **mittel** |
| Rohe Richtungstrefferquote | Deckelt bei ~56 % | **gering** |

Die „immer klareren Muster", die entstehen werden, sind deshalb
überwiegend **Bedingungen und Ausschlüsse** — „der Effekt trägt in
ruhigen Marktphasen bei mittlerer Liquidität, nicht nach
Ergebnisveröffentlichungen" — und nicht eine stetig steigende
Trefferquote.

Das ist kein kleineres Ziel. Es ist das, was tatsächlich Geld verdient.
Aber es verlangt ein System, das Bedingungen messen kann — und genau
darauf ist der folgende Entwurf ausgelegt.

---

## 2. Was an der Idee richtig ist

Der Engpass des Projekts ist **nicht Rechenzeit, sondern Beobachtungen.**

Der Live-Bot macht höchstens 3 Käufe je Lauf, praktisch etwa 15 Trades
pro Woche. `lifecycle.analyse()` markiert Befunde erst ab 30
abgeschlossenen Trades als belastbar — und 30 ist noch großzügig.
Währenddessen läuft der Prozess 16 Stunden am Tag und schreibt
`kein Handel: Boerse geschlossen`.

Gleichzeitig wirft der Bot täglich bezahlte Information weg: Von ~200
Kandidaten oberhalb der Score-Schwelle werden 3 gekauft. Was aus den
anderen 197 wurde, erfährt niemand — dabei ist das die Antwort auf die
wichtigste Frage überhaupt: **sortiert unsere Rangliste richtig?**

Der eigentliche Wert liegt aber noch tiefer:

> Jeder Backtest in diesem Projekt ist potenziell dadurch verdorben, dass
> die Strategie ausgewählt wurde, *nachdem* man diese Historie gesehen
> hat. Vorwärts erzeugte Schattenvorhersagen sind gegen diesen Fehler
> immun. Sie sind die einzigen wirklich unbekannten Daten, die das
> Projekt je bekommt.

Der Schattenbetrieb ist damit das Gegenstück zum Papierdepot:
Das Depot misst **Ausführung** (Slippage, Gebühren, Broker-Regeln),
der Schatten misst **Vorhersagequalität** (sortiert der Score, tragen
die Regeln, unter welchen Bedingungen).

---

## 3. Fünf Korrekturen

Ohne diese fünf Punkte erzeugt das System Zahlen, die gut aussehen und
nichts bedeuten.

### 3.1 „Wird die Trefferquote über Wochen besser?" ist die falsche Frage

Ändert sich am Code nichts, schwankt die Trefferquote trotzdem — mit dem
Markt. Steigt der Gesamtmarkt vier Wochen, steigt sie mit, ohne dass
irgendetwas gelernt wurde. Wer diese Kurve als Lernfortschritt liest,
verwechselt Marktregime mit Können.

**Richtig:** Jede Kennzahl wird gegen eine Referenz gemessen, die
dasselbe Regime erlebt hat.

| Kennzahl | Referenz |
|---|---|
| Trefferquote | Basisrate: Anteil *aller* Symbole, die an dem Tag stiegen |
| Rendite je Vorhersage | Median-Rendite des Universums am selben Tag |
| Depotrendite | Buy & Hold desselben Universums |
| Bot gegen Bot | Tagesdifferenz beider (siehe 6.2) |

Gemessen wird immer der **Überschuss**, nie der Rohwert. Ein
Schattenbuch mit +3 % in einer Woche, in der das Universum +4 % machte,
ist ein Verlust.

Jede Vorhersage führt zusätzlich die **Code-Version** (Git-Commit) mit,
die sie erzeugt hat. Sonst ist „ist es besser geworden?" grundsätzlich
nicht beantwortbar, weil Regimewechsel und Codeänderungen sich
vermischen.

### 3.2 1.000 Schattentrades sind nicht 1.000 Beobachtungen

Alle Vorhersagen eines Tages sind vom selben Marktfaktor getrieben.
Statistisch zählt ein Handelstag mit 200 Kandidaten näher an *einer*
Beobachtung als an 200.

Die belastbare Rechnung läuft über die **Zeitreihe der Tages-ICs** —
genau so, wie `research.py` es bereits für die Historie tut:

```
t = mittlerer_tages_IC / (std_tages_IC / sqrt(anzahl_tage))
```

Mit dem gemessenen IC ≈ 0,017 und üblicher Tages-IC-Streuung ~0,10 ergibt
sich für t = 2:

> **≈ 140 Handelstage, also 6–9 Monate**, bis sich vorwärts belastbar
> sagen lässt, dass der Vorsprung überhaupt existiert.

Das ist die ehrliche Zahl für die *absolute* Aussage. Für
**Bot-gegen-Bot-Vergleiche** ist sie deutlich kleiner (siehe 6.2) — das
ist der Grund, warum die Flotte der effizientere Weg ist. Nützliche
Diagnosen (Kalibrierung, Kostenrealismus, Ausstiegsregeln) fallen schon
nach **2–4 Wochen** ab.

Jede Auswertung meldet **beides**: Anzahl Vorhersagen *und* Anzahl
unabhängiger Tage. Die zweite Zahl zählt.

### 3.3 Fiktive Trades ohne Kosten sind Selbstbetrug

Ein Schattentrade ohne Spread, Slippage und Gebühren ist systematisch
besser als jeder echte — und zwar genau in die Richtung, die einem
gefällt. `costs.py` mit `estimate_costs()` wird bereits von `simulate.py`
verwendet; der Schatten benutzt dieselbe Funktion mit denselben
Annahmen.

Zusätzlich wird die im Depot gemessene Slippage
(`journal.slippage_report()`) monatlich gegen die angesetzten
Basispunkte gehalten. Weichen sie ab, werden die Schattenannahmen
nachgezogen — nicht umgekehrt.

**Für die Flotte besonders wichtig:** Varianten mit höherem Umschlag
zahlen mehr Kosten. Eine Variante, die brutto führt, kann netto
verlieren. Verglichen wird **ausschließlich netto**, und der Umschlag
wird je Bot als eigene Kennzahl geführt.

### 3.4 yfinance schreibt die Vergangenheit um

`datasources.py` lädt mit `auto_adjust=True`. Für Forschung richtig, hier
eine subtile Falle: Nach Dividende oder Split werden **historische**
Kurse rückwirkend angepasst. Ein heute als „Einstieg bei 50,00"
gespeicherter Kurs steht in vier Wochen im selben Abruf bei 49,60.

Wer die Rendite später aus neu geladenen Daten berechnet, misst dann
teilweise die Anpassung statt der Kursbewegung.

**Regel:** Entscheidungs- und Einstiegskurse werden zum Zeitpunkt der
Entscheidung **roh gespeichert und nie neu abgeleitet.** Bei jeder
Verifikation wird der gespeicherte gegen den neu geladenen Kurs für
dasselbe Datum geprüft; Abweichungen werden im Feld `data_check` als
`kurs_angepasst` vermerkt statt still überschrieben.

### 3.5 Viele Bots gleichzeitig erzeugen Scheingewinner

Das ist die zentrale Gefahr der Flotte und der Grund, warum Abschnitt 6
existiert.

Laufen 20 Bots und ist in Wahrheit **keiner** besser als die anderen,
zeigt der beste nach drei Monaten trotzdem eine deutliche
Überrendite — rein zufällig. Der Erwartungswert des Maximums von N
unabhängigen Standardnormalgrößen liegt bei etwa `sqrt(2·ln N)`:

| Anzahl Bots N | erwartetes Maximum (Sigma) allein durch Zufall |
|---|---|
| 3 | 1,48 |
| 10 | 2,15 |
| 20 | 2,45 |
| 50 | 2,80 |
| 100 | 3,03 |

Ein t-Wert von 2,4 beim besten von 20 Bots ist also **kein Befund,
sondern der Normalfall**. Wer ihn als Erfolg liest und die Regeln
entsprechend ändert, verschlechtert das System.

Deshalb gilt in diesem Entwurf: Die Anzahl aller je gestarteten Bots
wird mitgezählt — auch der verworfenen — und jede Aussage über einen
Gewinner muss die Schwelle aus dieser Tabelle überschreiten.

---

## 4. Architektur

**Getrennter Prozess, getrennte Datenbank, gemeinsame Engine.**

### 4.1 Begründung der Trennung

1. **Der Handelspfad darf nicht gefährdet werden.** `daemon.py` beendet
   sich nach `max_consecutive_errors`. Läuft Forschungscode im selben
   Prozess, reißt ein Fehler dort den echten Bot mit.
2. **Der Takt ist ein anderer.** Der Live-Bot läuft alle 15 Minuten
   während der Handelszeit. Tagesbars ändern sich einmal täglich.
3. **Andere Datenquelle, andere Drosselung.** `ratelimit.py` führt die
   Kontingente für yfinance und Alpaca bereits getrennt.
4. **Rechenlast.** Signale für 1.200 Symbole × N Bots dauern; im
   Handelsloop könnte das eine echte Entscheidung verzögern.
5. **Strukturelle statt disziplinierter Trennung.** Die Alternative wäre
   eine gemeinsame `journal.sqlite` mit Filter auf `runs.script`. Genau
   dieser Mechanismus hat schon einmal versagt —
   `14_journal_bereinigen.py` musste Entwicklungsdaten aus der
   Produktionsdatenbank entfernen. Bei ~1.000 Vorhersagen täglich je Bot
   gegen ~60 echte Entscheidungen wäre jede vergessene
   `WHERE script=`-Bedingung eine still falsche Kennzahl.

Mit eigener Datei ist das strukturell unmöglich: Eine Abfrage gegen
`journal.sqlite` **kann** keine Schattendaten liefern.

Geteilt wird dagegen `Engine.decide()`. Es gilt weiter der zentrale
Grundsatz des Projekts — eine Entscheidungslogik, verschiedene
Datenquellen:

```
                       ┌─────────────────────┐
                       │   Engine.decide()   │   eine Logik
                       └──────────┬──────────┘
        ┌─────────────────────────┼─────────────────────────┐
   simulate.py                live.py                  shadow.py
   Historie                   Alpaca-Depot             yfinance, N Bots
   journal.sqlite             journal.sqlite           shadow.sqlite
   (script=simulate)          (script=live_trade)       ← eigene Datei
```

### 4.2 Neue Dateien

```
src/alpaca_bot/shadow.py        Kern: Vorhersagen erzeugen, einbuchen, schließen
src/alpaca_bot/shadow_eval.py   Auswertung: IC, Kohorten, Attribution, Flotte
src/alpaca_bot/fleet.py         Bot-Register, Voranmeldung, Versuchszähler
src/alpaca_bot/hypotheses.py    Hypothesenregister (externes Wissen)
src/alpaca_bot/patterns.py      Musterspeicher mit Verfallsprüfung
scripts/16_shadow_daemon.py     Dauerbetrieb des Schattensystems
scripts/17_shadow_report.py     Berichte + Prüfungen (--pruefen)
scripts/18_fleet.py             Bots anmelden, auflisten, stilllegen
data/shadow.sqlite              eigene Datenbank
data/shadow_raw/                JSONL-Rohprotokoll je Lauf
```

Bestehender Code wird **nicht verändert** — `shadow.py` ist ein reiner
zusätzlicher Aufrufer. Einzige Ausnahme: `lifecycle.analyse()` und
`research.py` werden wiederverwendet, indem ihnen Schattendaten im
passenden Format übergeben werden. Beide sind dafür bereits allgemein
genug geschrieben.

### 4.3 Zusammenspiel von Depot und Schatten

Beide Systeme sind einzeln unvollständig und ergänzen sich exakt dort,
wo der jeweils andere blind ist:

| | Depot (live) | Schatten |
|---|---|---|
| Umfang | ~15 Trades/Woche | 500–1.500 Vorhersagen/Woche |
| Kosten | **echt gemessen** | angenommen |
| Ausführung | **echt** (Fills, Teilausführung, Ablehnung) | modelliert |
| Statistik | zu dünn für jede Aussage | trägt |

Drei feste Kopplungen:

**1. Das Depot eicht den Schatten.** Monatlich wird
`journal.slippage_report()` gegen die im Schatten angesetzten
Basispunkte gehalten. Weicht es ab, werden die Schattenannahmen
nachgezogen. Das Depot ist die einzige Quelle für echte
Ausführungskosten — der Schatten kann sie nie messen, nur übernehmen.

**2. Der Schatten erklärt das Depot.** Jeder echte Trade existiert
zusätzlich als Vorhersage von `B00_basis` im Spiegelbuch. Die Differenz
zwischen beiden ist per Konstruktion **reine Ausführung**, kein Signal —
denn die Entscheidung war dieselbe. Damit wird für jeden einzelnen
Live-Trade trennbar, ob ein schlechtes Ergebnis an der Auswahl lag oder
am Handel.

**3. Gemeinsam auswerten, getrennt gewichten.** `lifecycle.analyse()`
läuft über beide Bestände — aber die Ergebnisse werden **nie zu einer
Zahl zusammengeworfen.** Würde man 1.000 Schattentrades und 15 echte in
einen Topf werfen, ertränken die Schattendaten genau die Beobachtungen,
die als einzige die Ausführungswahrheit tragen. Stattdessen:

- Schatten = der statistische Körper (Signal, Regeln, Bedingungen)
- Depot = der Eichanker (Kosten, Ausführung, Broker-Realität)
- Ein Befund, zu dem **beide** Daten haben, muss in beiden dieselbe
  Richtung zeigen. Widersprechen sie sich, ist das ein Prüfauftrag,
  keine Entscheidung.

### 4.4 Ein Fund im bestehenden Code, der hierher gehört

`simulate.py:236` bucht Käufe zum **Eröffnungskurs** (`bar["open"]`).
Der Live-Bot handelt aber laut `daemon.py:56` frühestens **20 Minuten
nach Eröffnung** (`open_delay_minutes = 20`), weil die Eröffnungsspanne
die teuerste Phase des Tages ist.

Die Simulation rechnet also mit einem Kurs, den der echte Bot
grundsätzlich nie bekommt.

**Inzwischen gemessen (§0.1, 2026-07-29):** Die Drift beträgt für
Umkehr-Kandidaten −0,58 bps (t = −0,18, n = 1.212 über 60 Tage) und ist
damit weder statistisch noch wirtschaftlich relevant — gegenüber 8,0 bps
bereits angesetzter Handelskosten. `simulate.py` wird deshalb **nicht**
geändert.

**Folge für den Plan:** Das Spiegelbuch bucht dennoch zum Kurs 20 Minuten
nach Eröffnung, weil das der Realität entspricht und nichts kostet. Beide
Kurse werden gespeichert (`entry_price_open` zusätzlich zu `entry_price`),
sodass die Größe **fortlaufend** mitgemessen wird. Der Einmalbefund oben
beruht auf 60 Tagen; sollte sich bei größerer Stichprobe doch ein
systematischer Betrag zeigen, fällt er hier auf, ohne dass jemand danach
suchen muss.

### 4.5 Betrieb als Systemdienst

Ja — genau wie der Handelsbot. `install_service.sh` ist dafür fast
fertig, hat aber `LABEL` (Zeile 20) und `scripts/12_daemon.py`
(Zeile 62) fest verdrahtet. Nötig ist eine rein additive Erweiterung um
zwei Parameter:

```bash
./scripts/install_service.sh --dienst schatten   # Label de.local.alpacashadow
./scripts/install_service.sh --dienst handel     # bisheriges Verhalten (Standard)
```

Beide Dienste laufen unabhängig nebeneinander, jeder mit `KeepAlive`
(Neustart nach Absturz) und `RunAtLoad` (Start nach Anmeldung). Getrennte
Protokolle: `logs/shadow.log` und `logs/shadow.error.log`.

Der Schattendienst braucht **kein** `--live` — er kann konstruktionsbedingt
keine Orders senden, weil er `trading.py` nicht importiert. Das ist die
stärkste Form der Trennung: nicht „darf nicht", sondern „kann nicht".

Rhythmus wie beim Handelsbot: eine Dauerschleife, die bis zum nächsten
Termin schläft (nicht `StartCalendarInterval`). Damit werden verpasste
Termine nach einem Ausfall sauber behandelt — siehe 4.6.

### 4.6 Nachtragen nach Ausfall — mit einer wichtigen Einschränkung

War der Rechner drei Tage aus, kann der Schattenbetrieb die fehlenden
Tage nachholen: yfinance liefert die Historie, und eine Momentaufnahme
mit `as_of` von vorgestern ist genauso gültig wie damals. Das ist ein
echter Vorteil gegenüber dem Live-Bot, der verpasste Gelegenheiten nie
zurückbekommt.

**Aber:** Wurde in der Zwischenzeit der Code geändert, ist ein
nachgetragener Lauf **kein Vorwärtstest mehr**, sondern ein Backtest —
neue Regeln auf alte Tage angewendet, mit dem Wissen, wie diese Tage
ausgingen. Genau die Verunreinigung, gegen die das ganze System gebaut
ist.

**Regel:**

- Jede nachgetragene Vorhersage bekommt `nachgetragen = 1` und die
  Code-Version, mit der sie **erzeugt** wurde.
- Stimmt diese mit der Version überein, die am ursprünglichen Tag aktiv
  war, zählt sie normal.
- Weicht sie ab, wird sie aus allen Vorwärtsstatistiken **ausgeschlossen**
  und nur als Backtest geführt.

Dafür führt `shadow_runs` mit, welche Code-Version zu welchem Zeitpunkt
aktiv war — ableitbar aus dem Git-Verlauf, aber sicherer, es beim Lauf
festzuhalten.

---

## 5. Die Bot-Flotte

### 5.1 Ein Prozess, viele Bots

Alle Bots laufen in **einem** Prozess. Der teure Teil — Kursdaten für
1.200 Symbole laden — passiert einmal. `Engine` ist ausdrücklich
zustandslos, also kann dieselbe Momentaufnahme an N verschiedene
Konfigurationen gereicht werden.

```python
snapshot = build_shadow_snapshot(symbols)      # einmal, teuer
for bot in fleet.active():                     # N-mal, billig
    decisions = Engine(bot.config).decide(snapshot, bot.portfolio)
    record(bot, decisions)
```

N getrennte Prozesse wären N-facher yfinance-Verkehr und würden die
Drossel reißen. Zusätzlicher Vorteil des gemeinsamen Laufs: Alle Bots
sehen garantiert **dieselben Kurse an denselben Tagen** — die
Voraussetzung für den gepaarten Vergleich in 6.2.

### 5.2 Zwei Bücher je Bot

| Buch | Regeln | Beobachtungen/Tag | Beantwortet |
|---|---|---|---|
| **Spiegel** | exakt wie der echte Bot: 15 Positionen, max. 3 Käufe, Kapitalgrenzen, Sperrfrist, Kosten, PDT | ~3 | Was hätte dieser Bot verdient? Direkt mit dem Depot vergleichbar |
| **Rangliste** | jeder Kandidat über `min_score`, keine Kapitalgrenze | 100–300 | Sortiert der Score? Liefert IC, Kalibrierung, Score-Bänder |

Der Unterschied zwischen beiden ist selbst eine Erkenntnis: Ist die
Rangliste gut und der Spiegel schlecht, liegt das Problem nicht am
Signal, sondern an Positionsgrößen, Limits oder Kosten.

### 5.3 Faktorieller Aufbau — sonst ist keine Attribution möglich

**Der wichtigste Entwurfspunkt der ganzen Flotte.** Unterscheiden sich
zwei Bots in fünf Parametern und einer gewinnt, hat man nichts gelernt.

**Regel: Jeder Bot unterscheidet sich vom Basis-Bot in genau EINER
Achse.** Wer Kombinationen testen will, nimmt sie erst auf, wenn beide
Einzelachsen vermessen sind.

Startaufstellung — bewusst klein (siehe 3.5):

| Bot | Achse | Wert | Hypothese |
|---|---|---|---|
| `B00_basis` | — | aktuelle Einstellung | Referenz, gegen die alles gemessen wird |
| `B01_stop_eng` | `stop_atr` | 1,5 (statt 2,0) | Schnellerer Ausstieg spart Verluste |
| `B02_stop_weit` | `stop_atr` | 3,0 | MAE-Befund: Gewinner gehen zwischenzeitlich tief ins Minus |
| `B03_ziel_weit` | `target_atr` | 3,0 (statt 2,0) | MFE-Befund: Ziel wird zu früh genommen |
| `B04_halten_lang` | `max_hold_days` | 10 (statt 5) | Effekt könnte länger tragen als gemessen |
| `B05_schwelle_hoch` | `min_score` | 0,50 (statt 0,35) | Weniger, aber bessere Trades — weniger Kosten |
| `B06_ohne_regime` | `market_regime_filter` | aus | Prüft, ob der Filter überhaupt etwas beiträgt |

Sieben Bots. Nach der Tabelle in 3.5 liegt die Zufallsschwelle damit bei
~1,9 Sigma — beherrschbar (die Umsetzung rechnet mit Sicherheitsaufschlag
**2,47**). Jeder weitere Bot hebt sie an, deshalb wird die Flotte nur
erweitert, wenn eine Achse abgeschlossen ist.

#### BEFUND 2026-07-29 — zwei der sieben Bots sind wirkungslos

Beim ersten Testlauf über 39 Handelstage meldete
`shadow_eval.divergenz()` drei Bots als **cent-genau identisch**:

| Paar | Abweichung über 38 Tage |
|---|---|
| `B00_basis` ↔ `B03_ziel_weit` | **0,00 bps** |
| `B00_basis` ↔ `B06_ohne_regime` | **0,00 bps** |
| `B00_basis` ↔ `B01_stop_eng` | 65,5 bps (wirkt) |

Ursachen, jeweils nachgeprüft:

- **`B03_ziel_weit`** ist strukturell wirkungslos. Bei `max_hold_days = 5`
  überlebt kaum eine Position lange genug, um überhaupt ein Ziel zu
  erreichen — von 98 Trades endeten nur 3 am Ziel, der Rest über
  Score-Verfall (32) und Zeitausstieg (53). Ein weiteres Ziel ändert daran
  nichts: Beide Bots verkauften dieselben Titel am selben Tag zum selben
  Kurs, lediglich mit anderer *Begründung*.
- **`B06_ohne_regime`** ist im Testzeitraum wirkungslos, aber nicht
  strukturell: Der SPY lag durchgehend über seinem 200-Tage-Schnitt, der
  Regimefilter hat also nie gegriffen. In einer Abwärtsphase würde er
  sehr wohl unterscheiden. Hier ist die Variante nur *derzeit nicht
  prüfbar*.

**Warum das teuer ist:** Beide belegen einen Flottenplatz und heben die
Zufallsschwelle für **alle** Bots (7 statt 5 Versuche → t > 2,47 statt
2,29), ohne selbst Information zu liefern.

**Konsequenz:** `B03_ziel_weit` sollte stillgelegt werden — die
informativere Achse wäre `exit_score` (steuert den Score-Verfall-Ausstieg,
der 32 von 98 Ausstiegen auslöste). `B06_ohne_regime` bleibt, muss aber
bis zur ersten Abwärtsphase als „nicht entscheidbar" geführt werden.

```bash
python scripts/18_fleet.py --divergenz     # findet solche Doubletten
python scripts/18_fleet.py --stilllegen B03_ziel_weit --grund "wirkungslos bei hold=5"
```

Das ist genau die Vorabprüfung, die §12.2 verlangt — hier vorwärts auf den
echten Büchern statt auf der Historie.

#### ERWEITERUNG 2026-07-30 — zwei Bots zum Investitionsgrad

**Beobachtung:** Bei vollen 15 von 15 Positionen standen nur **53,9 %** des
Kapitals im Markt, obwohl `target_invested = 0,90`. Ursache ist die
Volatilitäts-Skalierung in `engine.py`:

```python
size *= min(1.5, 0.03 / atr_pct)   # wirkt ABSOLUT, kann nur verkleinern
```

Umkehr-Kandidaten sind per Definition Werte, die gerade stark gefallen
sind — also fast immer über dem 3-%-ATR-Referenzwert. Die Skalierung
schrumpft sie deshalb systematisch. Auf echten Daten gemessen: **35,3 %
statt 90 %** bei 15 Positionen.

Das ist **kein Fehler**, sondern implizites Volatilitäts-Targeting: In
unruhigen Phasen steht weniger Kapital im Markt. Es ist aber eine
Risikohaltung, die nie bewusst gewählt wurde — und es gibt zwei Auswege,
die sich gegenseitig ausschließen. Deshalb werden sie **getrennt**
gemessen statt vermischt:

| Bot | Achse | Weg |
|---|---|---|
| `B07_mehr_positionen` | `max_positions` = 25 | mehr Plätze, gleiche Größe |
| `B08_voll_investiert` | `deploy_to_target` = True | gleiche Plätze, größere Positionen |

`deploy_to_target` (neu in `EngineConfig`, Standard **False**) macht die
Volatilitäts-Gewichtung *relativ* statt absolut: Sie bestimmt weiterhin,
wer mehr und wer weniger bekommt (Risikoparität), wird aber so normiert,
dass `target_invested` erreicht wird. `max_position_pct` bleibt hart —
was der Deckel abschneidet, verteilt sich per Wasserfüllung auf die
übrigen Kandidaten.

Gemessen nach der Änderung: **35,3 % → 90,0 %** bei gleicher
Positionsanzahl, Deckel eingehalten.

**Wichtig — kein Auffüllen um jeden Preis:** Gibt es zu wenige Kandidaten,
bleibt das Kapital liegen. Bei nur 3 Kandidaten werden 33 % investiert,
nicht künstlich mehr. „Kein passender Wert" bleibt ein gültiges Ergebnis.

**Ehrliche Einordnung:** Ein höherer Investitionsgrad ist nicht per se
besser. Er verstärkt Gewinne **und** Verluste. Da §0.2 für diese Strategie
über 5 Jahre *keinen* Netto-Vorsprung gegen Buy & Hold nachweisen konnte,
ist die Erwartung neutral bis negativ — genau deshalb steht `False` als
Standard, und genau deshalb entscheidet der Vorwärtstest, nicht die
Vermutung.

**Nicht umgesetzt: Gewichtung nach Score.** Naheliegend wäre, den
bestbewerteten Kandidaten mehr Kapital zu geben. §0.2 hat aber gemessen,
dass die Trefferquote mit steigendem Score *sinkt* (52,0 % → 49,2 %) — der
Score sortiert am oberen Ende nicht zuverlässig. Kapital dorthin zu
konzentrieren wäre auf heutiger Datenlage eher schädlich. Sobald der
Schattenbetrieb genug Daten für eine belastbare Kalibrierung hat, ist das
erneut zu prüfen.

Die Flotte umfasst damit **9 Bots**, die Zufallsschwelle steigt auf
**t > 2,60**.

### 5.4 Voranmeldung — der Schutz gegen nachträgliche Erzählungen

Jeder Bot muss **vor seinem ersten Lauf** mit Hypothese und Quelle
registriert werden (`scripts/18_fleet.py --anmelden`). Das Feld
`hypothese` ist Pflicht und beantwortet: *Warum sollte das besser sein,
und woher stammt die Vermutung?*

Ohne diese Disziplin passiert unweigerlich Folgendes: Ein Bot gewinnt,
man findet im Nachhinein eine Begründung, und aus Rauschen wird eine
Geschichte. Die Voranmeldung macht den Unterschied zwischen einem
bestätigten und einem erfundenen Befund nachprüfbar.

Ebenso Pflicht: **Stillgelegte Bots werden nicht gelöscht.** Sie zählen
dauerhaft in den Versuchszähler (siehe 6.1). Einen Verlierer zu
entfernen und zu vergessen ist der häufigste Weg, sich selbst zu
täuschen.

### 5.5 Rechenzeit: Signale werden geteilt, nicht vervielfacht

Die Startaufstellung aus 5.3 variiert fast ausschließlich
**Ausstiegsparameter** (`stop_atr`, `target_atr`, `max_hold_days`,
`min_score`). Diese beeinflussen die Signalberechnung **nicht** — nur
die Auswertung der fertigen Signale.

Das heißt: `build_reversal_frame()` läuft nicht siebenmal, sondern
einmal. Nur Bots mit abweichenden `ReversalWeights` oder abweichendem
`market_regime_filter` (hier: `B06_ohne_regime`) brauchen einen eigenen
Durchlauf.

**Umsetzung:** Signalrahmen werden je Lauf in einem Zwischenspeicher
gehalten, dessen Schlüssel ein Hash der signalrelevanten
Konfigurationsteile ist:

```python
key = hash_of(cfg.strategy, cfg.reversal_weights, cfg.weights)
frames = signal_cache.setdefault(key, build_frames(snapshot, cfg))
```

Damit kostet die Flotte kaum mehr Rechenzeit als ein einzelner Bot —
sieben Bots brauchen zwei Signaldurchläufe statt sieben. Das ist die
Voraussetzung dafür, die Flotte überhaupt täglich über 1.200 Symbole
laufen zu lassen.

---

## 6. Statistische Disziplin

### 6.1 Versuchszähler

Eine Tabelle hält fest, wie viele Bots, Varianten und Hypothesen
**insgesamt jemals** getestet wurden. Diese Zahl — nicht die Zahl der
gerade laufenden — bestimmt die Signifikanzschwelle:

```
schwelle_sigma = sqrt(2 * ln(n_versuche_gesamt)) + 0.5
```

Der Zuschlag von 0,5 ist ein bewusster Sicherheitsaufschlag. Jede
Auswertung zeigt die Schwelle mit an; Befunde darunter werden als
`nicht_belastbar` ausgewiesen — analog zum bestehenden
`belastbar`-Flag in `lifecycle.py`.

### 6.2 Gepaarter Vergleich — der eigentliche Effizienzgewinn

Bot A gegen Bot B über die jeweilige Gesamtrendite zu vergleichen ist
verschwenderisch, weil beide zu ~95 % dieselbe Marktbewegung enthalten.
Verglichen wird stattdessen die **Tagesdifferenz**:

```
d_t = rendite_A(t) - rendite_B(t)
t_wert = mittelwert(d) / (std(d) / sqrt(anzahl_tage))
```

Da beide Bots dieselben Tage, Symbole und Kurse sehen, kürzt sich der
Marktfaktor heraus. Die Streuung von `d` ist typisch **3–5× kleiner**
als die der Einzelrenditen — und weil die nötige Tageszahl quadratisch
davon abhängt, sinkt sie um den Faktor 10–25.

> Praktische Folge: Eine belastbare Aussage „Bot A schlägt Bot B" ist
> nach **6–10 Wochen** möglich, nicht erst nach 9 Monaten. Das ist der
> Grund, warum die Flotte der schnellere Erkenntnisweg ist als der
> Einzelbot.

Der gepaarte Test ist auch der einzige zulässige Weg für den Vergleich
mit `B00_basis`.

### 6.3 Sperrzone

Die letzten 20 % des verfügbaren Zeitraums bleiben bei jeder
Auswertung unberührt, bis eine Entscheidung getroffen ist. Erst danach
wird auf der Sperrzone geprüft. Hält der Befund dort nicht, wird er
verworfen — ohne Diskussion.

Der Wert der Sperrzone hängt vollständig daran, dass niemand vorher
hineinschaut. `shadow_eval.py` erzwingt das technisch: Die
Standardauswertung schneidet sie ab, und der Zugriff braucht einen
eigenen Schalter (`--sperrzone-oeffnen`), der protokolliert wird.

### 6.4 Was eine Regeländerung rechtfertigt

Alle vier Bedingungen müssen erfüllt sein:

1. gepaarter t-Wert über der Schwelle aus 6.1
2. mindestens 60 unabhängige Handelstage
3. Effekt hält in mindestens zwei von drei Marktregimen (siehe 13)
4. Befund bestätigt sich auf der Sperrzone

---

## 7. Attribution: woran lag es?

Wenn Bot A besser abschneidet als Bot B, ist „A ist besser" die
unbrauchbarste aller Antworten. Weil alles protokolliert ist, lässt sich
die Differenz mechanisch zerlegen.

### 7.1 Vier Quellen einer Differenz

| Quelle | Frage | Wie gemessen |
|---|---|---|
| **Auswahl** | Kauft A andere Symbole? | Rendite auf der Schnittmenge gegen Rendite auf der Differenzmenge |
| **Zeitpunkt** | Gleiches Symbol, anderer Tag? | Nur Trades in beiden Büchern, Einstiegsdatum vergleichen |
| **Größe** | Gleiche Trades, andere Gewichtung? | Beide Bücher auf Gleichgewichtung umrechnen und neu vergleichen |
| **Ausstieg** | Gleiche Einstiege, andere Ausstiege? | Kontrafaktisch: A's Einstiege mit B's Ausstiegsregeln nachrechnen |

### 7.2 Kontrafaktische Bücher

Der stärkste Teil: Da jede Vorhersage ihren vollständigen Kursverlauf
mitführt (MAE, MFE, Horizontrenditen), lassen sich **kreuzweise Bücher**
ohne neuen Datenabruf berechnen:

```
A_auswahl × B_ausstieg   →  liegt der Vorteil in der Auswahl?
B_auswahl × A_ausstieg   →  liegt er in den Ausstiegsregeln?
```

Ist `A_auswahl × B_ausstieg` ähnlich gut wie A, kommt A's Vorsprung aus
der Auswahl. Ist es ähnlich schlecht wie B, kommt er aus dem Ausstieg.
Damit ist die Frage „woran lag es" nicht mehr Interpretation, sondern
Rechnung.

Voraussetzung: Für jede Vorhersage werden die reinen Horizontrenditen
(1/3/5/10/20 Tage) **unabhängig von Stop und Ziel** gespeichert. Sie
sind die Grundlage jeder kontrafaktischen Rechnung — deshalb stehen sie
im Schema (Abschnitt 8) auch dann, wenn der Trade früher geschlossen
wurde.

---

## 8. Datenmodell

`data/shadow.sqlite`. Ergänzend ein JSONL-Rohprotokoll je Lauf unter
`data/shadow_raw/` — SQLite ist die Auswertungsschicht, JSONL die
Rekonstruktionsgrundlage, genau wie im Journal.

```sql
-- ---------------------------------------------------------------- Flotte
CREATE TABLE bots (
    bot_id        TEXT PRIMARY KEY,     -- 'B01_stop_eng'
    name          TEXT NOT NULL,
    familie       TEXT NOT NULL,        -- die variierte Achse: 'stop_abstand'
    basis_bot     TEXT,                 -- Vergleichsanker, meist 'B00_basis'
    achse         TEXT,                 -- 'stop_atr'
    wert          TEXT,                 -- '1.5'
    config_json   TEXT NOT NULL,        -- vollstaendige EngineConfig
    hypothese     TEXT NOT NULL,        -- PFLICHT: warum sollte das besser sein
    quelle        TEXT,                 -- eigene Messung | hypothese:HYP-012 | ...
    angemeldet_am TEXT NOT NULL,        -- VOR dem ersten Lauf
    aktiv_ab      TEXT, aktiv_bis TEXT,
    status        TEXT NOT NULL         -- angemeldet|laeuft|stillgelegt|verworfen
);

-- Zaehlt ALLE je gestarteten Versuche, auch verworfene (siehe 6.1)
CREATE TABLE versuchszaehler (
    stand_am        TEXT PRIMARY KEY,
    n_bots_gesamt   INTEGER NOT NULL,
    n_hypothesen    INTEGER NOT NULL,
    n_vergleiche    INTEGER NOT NULL,
    schwelle_sigma  REAL NOT NULL
);

-- ---------------------------------------------------------------- Laeufe
CREATE TABLE shadow_runs (
    run_id        TEXT PRIMARY KEY,
    started_at    TEXT NOT NULL, ended_at TEXT, status TEXT,
    as_of         TEXT NOT NULL,   -- letzter VOLLSTAENDIGER Handelstag
    data_source   TEXT NOT NULL,   -- 'yfinance'
    n_symbols     INTEGER,
    code_version  TEXT NOT NULL,   -- Git-Commit  <- unverzichtbar
    fehler        TEXT
);

-- ------------------------------------------------------------ Vorhersagen
CREATE TABLE predictions (
    pred_id         TEXT PRIMARY KEY,
    run_id          TEXT NOT NULL,
    bot_id          TEXT NOT NULL,
    buch            TEXT NOT NULL,   -- 'spiegel' | 'rangliste'
    as_of           TEXT NOT NULL,   -- Datenstichtag (Entscheidungsgrundlage)
    decided_at      TEXT NOT NULL,   -- Wanduhrzeit
    symbol          TEXT NOT NULL,
    rang            INTEGER,
    score           REAL,
    -- Preise: ROH gespeichert, nie neu abgeleitet (siehe 3.4)
    decision_price  REAL NOT NULL,   -- Schlusskurs an as_of
    entry_date      TEXT,            -- naechster Handelstag
    entry_price_open REAL,           -- Eroeffnung (wie simulate.py rechnet)
    entry_price     REAL,            -- Kurs 20 Min nach Eroeffnung (wie live handelt)
    entry_price_eff REAL,            -- nach Kosten; Basis ist entry_price
    -- Herkunft: nachgetragene Laeufe zaehlen nur, wenn die Code-Version
    -- mit der am urspruenglichen Tag aktiven uebereinstimmt (siehe 4.6)
    code_version    TEXT NOT NULL,
    nachgetragen    INTEGER DEFAULT 0,
    -- Plan
    planned_stop    REAL, planned_target REAL, planned_hold_days INTEGER,
    notional        REAL,
    reasons         TEXT, features TEXT,
    -- Kontext fuer die Regimebedingung (siehe 13)
    regime_markt    TEXT,            -- 'aufwaerts_ruhig' | 'abwaerts_hektisch' | ...
    regime_vola     TEXT,            -- Perzentilband der Marktvolatilitaet
    regime_breite   REAL,            -- Anteil Symbole ueber SMA50
    atr_pct         REAL,
    liquiditaet     REAL,            -- Dollar-Volumen
    wuerde_gehandelt INTEGER,        -- haette der echte Bot das gekauft?
    UNIQUE (as_of, symbol, bot_id, buch)
);

-- --------------------------------------------------------------- Ergebnis
CREATE TABLE shadow_outcomes (
    pred_id       TEXT PRIMARY KEY,
    exit_date     TEXT, exit_price REAL, exit_price_eff REAL, exit_reason TEXT,
    return_pct    REAL,             -- NETTO nach Kosten
    return_brutto REAL,
    kosten        REAL,
    bars_held     INTEGER,
    mae_pct       REAL, mfe_pct REAL, mae_date TEXT, mfe_date TEXT,
    -- Reine Horizontrenditen, UNABHAENGIG von Stop/Ziel.
    -- Grundlage jeder kontrafaktischen Rechnung (siehe 7.2) - deshalb
    -- immer gefuellt, auch wenn der Trade frueher geschlossen wurde.
    fwd_1d REAL, fwd_3d REAL, fwd_5d REAL, fwd_10d REAL, fwd_20d REAL,
    -- Referenzen: ohne sie ist die Zahl bedeutungslos (siehe 3.1)
    bench_fwd_5d     REAL,          -- SPY ueber denselben Zeitraum
    universum_fwd_5d REAL,          -- Median aller Symbole desselben Tages
    ueberschuss_5d   REAL,
    ziel_erreicht INTEGER, stop_erreicht INTEGER,
    evaluated_at  TEXT,
    data_check    TEXT              -- 'ok' | 'kurs_angepasst' | 'luecke'
);

-- ------------------------------------------------------------ Lernkurve
CREATE TABLE scoreboard (
    kohorte       TEXT NOT NULL,    -- '2026-W31'
    bot_id        TEXT NOT NULL,
    buch          TEXT NOT NULL,
    code_version  TEXT NOT NULL,
    regime        TEXT NOT NULL,    -- 'alle' oder ein einzelnes Regime
    n_vorhersagen INTEGER, n_tage INTEGER,   -- n_tage ist die zaehlende Zahl
    ic_5d REAL, ic_t_stat REAL,
    trefferquote REAL, basisrate REAL, ueberschuss REAL,
    rendite_netto REAL, umschlag REAL, kosten_anteil REAL,
    kalibrierung REAL,
    PRIMARY KEY (kohorte, bot_id, buch, regime)
);

-- Gepaarte Vergleiche (siehe 6.2)
CREATE TABLE vergleiche (
    kohorte     TEXT, bot_a TEXT, bot_b TEXT,
    n_tage      INTEGER,
    diff_mittel REAL, diff_std REAL, t_wert REAL,
    schwelle    REAL,               -- aus dem Versuchszaehler
    belastbar   INTEGER,
    attribution TEXT,               -- JSON: Auswahl/Zeitpunkt/Groesse/Ausstieg
    PRIMARY KEY (kohorte, bot_a, bot_b)
);
```

Die Tabellen für Hypothesen und Muster stehen in den Abschnitten 10
und 11.

---

## 9. Tagesablauf

| Zeit (CEST) | Schritt | Was passiert |
|---|---|---|
| ~22:15 (nach US-Schluss) | **Entscheiden** | yfinance-Bars laden, `as_of` = heutiger Schluss, Snapshot einmal bauen, je Bot `Engine.decide()`, Vorhersagen schreiben |
| ~16:00 (nach US-Eröffnung) | **Einbuchen** | Eröffnungskurs als `entry_price` nachtragen, Kosten anwenden |
| ~22:30 | **Pflegen** | Offene Schattenpositionen gegen Stop/Ziel/Zeit prüfen, schließen, Ergebnis berechnen |
| täglich | **Verifizieren** | Fällige Horizonte nachtragen, MAE/MFE, Referenzwerte, `data_check` |
| sonntags | **Bilanzieren** | Wochenkohorte ins `scoreboard`, gepaarte Vergleiche, Musterprüfung |
| monatlich | **Verfallsprüfung** | Bestätigte Muster gegen die neuesten Daten testen (siehe 11) |

Entscheidend — und exakt wie in `simulate.py` gelöst: **Entschieden wird
auf dem Schlusskurs von Tag T, eingebucht zur Eröffnung von T+1.** Wer
die Rendite ab dem Schlusskurs von T rechnet, auf dem die Entscheidung
beruhte, hat ein Datenleck und misst einen Vorsprung, den es nicht gibt.

Zwischen den Terminen schläft der Prozess. Er läuft auch am Wochenende
(Verifikation) und nutzt damit genau die Zeit, die heute ungenutzt ist.

---

## 10. Externes Wissen: das Hypothesenregister

Der Wunsch, Erkenntnisse aus Fachpublikationen und Handelsplattformen
einzubeziehen, ist berechtigt — verlangt aber eine sehr klare Regel.

### 10.1 Die nüchterne Ausgangslage

Veröffentlichte Handelsstrategien replizieren überwiegend **nicht**:

- Hou, Xue & Zhang (2020) prüften 452 dokumentierte Anomalien mit
  sauberer Methodik nach — rund **65 % fielen durch**.
- McLean & Pontiff (2016) zeigten, dass die Wirkung publizierter
  Anomalien nach Veröffentlichung im Mittel um **~58 % nachlässt**.

Gründe: Publikationsverzerrung (nur Erfolge werden gedruckt),
Überanpassung in der Quelle, und Arbitrage nach Bekanntwerden.

**Daraus folgt die Regel:** Eine externe Behauptung ist niemals ein
Signal. Sie ist eine **Hypothese, die durch unser eigenes System
laufen muss** — und das Schattensystem ist genau der richtige Filter
dafür.

Der Wert liegt nicht darin, fertige Strategien zu übernehmen, sondern
darin, den **Ideenvorrat** zu füllen. Gute Quellen liefern Hypothesen,
auf die man selbst nicht käme; die Prüfung bleibt unsere Aufgabe.

### 10.2 Quellenklassen und Vorabgewichtung

| Klasse | Beispiele | Prior | Behandlung |
|---|---|---|---|
| **Akademisch, repliziert** | Journal of Finance, RFS; Fama-French-Datenbibliothek | mittel | direkt in den Historientest |
| **Akademisch, einzeln** | SSRN-Arbeitspapiere | niedrig-mittel | Historientest, hohe Schwelle |
| **Praktiker mit Methodik** | AQR Public Research, Alpha Architect, Quantpedia (Katalog mit Quellenangaben) | niedrig-mittel | Historientest |
| **Broker-/Plattformmaterial** | Analysen von Handelsplattformen | niedrig | nur wenn präzise operationalisierbar |
| **Blogs, Foren, Video** | — | sehr niedrig | nur als Ideenquelle, keine Ressourcenbindung |

### 10.2a Bereits gebaut, aber nicht angeschlossen — kein neuer Aufwand, nur Verkabelung

Das ist kein Punkt der allgemeinen Liste, sondern verdient eigene
Priorität: Der **aktuell laufende Bot entscheidet ausschließlich aus
Kurs- und Volumendaten.** `build_reversal_frame()` (die Strategie, die
`daemon.py` tatsächlich fährt) bekommt nichts als OHLCV plus SPY
übergeben — kein Text, keine Meldung, kein Ereignis. Das ist keine
Vermutung, sondern durch Lesen von `signals.py:203` bestätigt.

Gleichzeitig existiert im Projekt bereits Code für genau die Daten, die
dort fehlen — er ist nur nirgendwo verkabelt:

- **`news.py`** (Alpaca-/Benzinga-Feed, alle US-Aktien ab ~2015,
  kostenlos, mit `pit.asof_join`-Sperre gegen Zeitpunkt-Leckage) wird im
  gesamten Projekt genau einmal aufgerufen — in `06_event_study.py`,
  einem einmaligen Forschungsskript. Weder Live-Bot noch Simulation
  nutzen es.
- **`edgar.py`** (Insider-Käufe, 372 Form-4-Meldungen bereits im Cache)
  ist zwar in die *andere* Strategie eingebaut (`momentum`/
  `build_signal_frame`, nicht die laufende `reversal`-Strategie) — aber
  `live.py:build_snapshot()` lädt Insider-Daten für den Live-Betrieb gar
  nicht. Genutzt wird das nur in `10_simulate.py`, dem Backtest.

`docs/strategie-analyse.md` (Teil E) hat die Machbarkeit bereits
untersucht und eine Rangfolge festgehalten, was aus News realistisch
herauszuholen ist:

| Signal aus News | Stärke |
|---|---|
| Frequenz-Anomalie (plötzlich viel mehr Artikel als sonst) | mittel-hoch |
| Erstabdeckung (vorher nie erwähnter Wert) | mittel |
| Tonalität/Sentiment | schwach, überschätzt |

Naives Zusammenführen auf Tagesebene wäre die Falle: Eine Schlagzeile
wie „Aktie springt 30 % nach Zahlen" erscheint **nach** dem Sprung.
Genau dagegen ist die `asof_join`-Sperre in `news.py` bereits gebaut —
die Vorarbeit gegen das Leck ist vorhanden, nur der Anschluss fehlt.

**Deshalb höhere Priorität als generische externe Hypothesen:** Das ist
kein neues Ideenquellen-Problem, sondern fertige Infrastruktur, die nur
angeschlossen werden muss. Empfehlung: als eigener Kandidatenfaktor
(`f_news_frequenz`, `f_news_erstabdeckung`) zuerst durch den
Historientest in `research.py` (8 Jahre Daten liegen bereits vor),
danach als zusätzlicher Bot in der Flotte (§5) mit genau dieser einen
Achse — nicht in die bestehenden Umkehr-Faktoren hineinmischen, sonst
lässt sich der Beitrag nicht mehr trennen (vgl. §5.3, faktorieller
Aufbau).

### 10.2b Titelklassifikation ohne trainiertes Modell — Machbarkeit und Grenzen

Naheliegende Erweiterung: Nicht nur Häufigkeit zählen, sondern aus dem
Schlagzeilentext selbst ableiten, ob eine Meldung positiv, neutral oder
negativ ist. Das ist **nicht ohne Weiteres zuverlässig**, aus einem
dokumentierten Grund: Loughran & McDonald (2011, *Journal of Finance*)
haben gezeigt, dass allgemeine Sentiment-Wörterbücher (Harvard IV u. Ä.)
in Finanztexten **~75 % der als "negativ" markierten Wörter falsch**
einstufen — Wörter wie "tax", "cost", "liability" wirken negativ,
sind in Finanzsprache aber neutral bis erwartbar. Eine frei erfundene
Keyword-Liste hätte dasselbe Problem, nur ungeprüft.

Zusätzlich scheitert reines Wortzählen an Verneinung ("denies
bankruptcy rumors" enthält "bankruptcy", ist aber keine schlechte
Nachricht) und an gemischten Aussagen ("beats on revenue, misses on
EPS, raises guidance").

**Was stattdessen tragfähig ist, in absteigender Zuverlässigkeit:**

1. **Ereignistyp-Erkennung (regelbasiert), primäres Merkmal.**
   Benzinga-Schlagzeilen sind stark schablonenhaft ("X Reports Q3 EPS
   of $Y, Est. $Z", "X Upgraded to Buy at...", "X Announces Recall
   of..."). Das macht das Erkennen des **Ereignistyps** per Regex
   deutlich zuverlässiger als eine Stimmungseinstufung, weil das
   Vokabular eng und standardisiert ist:

   | Kategorie | Beispiel-Muster |
   |---|---|
   | Gewinn: Übertreffen/Verfehlen | "beats/misses (estimates\|consensus)" |
   | Prognose: angehoben/gesenkt | "raises/cuts/lowers guidance" |
   | Analysten-Einstufung | "upgraded/downgraded/initiated (to\|at)" |
   | Übernahme/Fusion | "to acquire", "merger", "buyout" |
   | Rechtlich/regulatorisch | "lawsuit", "investigation", "recall", "FDA" |
   | Führungswechsel | "resigns", "appoints (CEO\|CFO)" |
   | Dividende | "declares dividend", "raises/cuts dividend" |

   Jede Kategorie wird als eigene 0/1-Variable geführt, nicht zu einem
   Score zusammengefasst — sonst geht genau die Information verloren,
   die sie wertvoll macht.

2. **Tonalität über ein Fachwörterbuch, zweites, schwächeres Merkmal.**
   Das **Loughran-McDonald Master Dictionary** (frei verfügbar, für
   genau diesen Zweck gebaut) statt einer selbst erdachten Wortliste:
   Ton = (Positiv-Treffer − Negativ-Treffer) / Gesamtwörter je
   Schlagzeile. Bewusst als *zweites* Merkmal geführt, nicht als
   Hauptsignal — konsistent mit der bereits in 10.2a zitierten
   Einordnung "Tonalität: schwach, überschätzt".

3. **Die „heiße Nachricht"-Falle.** Eine Meldung wirkt oft erst dann
   "heiß" (viele Artikel, mehrere Quellen), wenn sich der Kurs schon
   bewegt hat. Ein Klassifikator, der auf "heiß" zielt, misst dann
   leicht "hat sich der Kurs schon bewegt" statt "wird er sich
   bewegen" — dieselbe Zeitpunkt-Falle, gegen die `news.py`s
   `asof_join`-Sperre bereits gebaut ist. Deshalb wird "heiß" hier
   nicht als eigene Kategorie geführt, sondern über die bereits
   bestehende Frequenz-Anomalie (10.2a) erfasst, die den Zeitbezug
   sauber trennt.

**Der Maßstab für "zuverlässig" ist nicht menschliches Urteil, sondern
Messbarkeit.** Ob die Klassifikation taugt, entscheidet sich nicht
daran, ob sie intuitiv richtig wirkt, sondern daran, ob jede Kategorie
einen messbaren Tages-IC gegen Vorwärtsrenditen hat — mit derselben
`research.py`-Maschinerie (Querschnitts-IC, t-Statistik über die
Tagesreihe), die für jeden Kursfaktor bereits läuft. Kategorien ohne
IC werden verworfen, unabhängig davon, wie plausibel sie klingen.

**Ausdrücklich kein Trainingsmodell in diesem Schritt** — weder
klassisches ML noch ein Sprachmodell. Regex plus Fachwörterbuch ist
vollständig regelbasiert, deterministisch und ohne Trainingsdaten
prüfbar. Ein logistisches Regressionsmodell über Wortvektoren (mit
`ml.py`, Label = tatsächliche Vorwärtsrendite statt Mensch-Einstufung)
wäre ein plausibler nächster Schritt, aber erst, wenn die regelbasierte
Fassung einen gemessenen IC zeigt — sonst wird ein Modell auf ein
Signal trainiert, von dem noch niemand weiß, ob es existiert.

**Realistische Erwartung, kalibriert vor der ersten Messung:** Eher
ein schwacher Zusatzbaustein und Risikofilter als eine neue
Haupt-Ertragsquelle. Zwei Gründe:

1. `signals.py` hält fest, dass **kein Einzelsignal in diesem Projekt
   je einen IC über ~0,05 erreicht hat** (bester bestätigter Faktor
   `reversal_3d`: 0,018). Es gibt keinen Grund, bei textbasierten
   Signalen eine andere Größenordnung zu erwarten — die akademische
   Literatur zu Tonalität (Tetlock 2007, Loughran-McDonald 2011) findet
   durchweg kleine Effekte in vergleichbarer Größenordnung.
2. **Architekturbedingt:** Entschieden wird auf dem Schlusskurs von
   Tag T, gehandelt zur Eröffnung von T+1 (§9). Eine Nachricht während
   der Handelszeit ist im Schlusskurs desselben Tages meist schon
   verarbeitet — die schnelle Reaktion ist vorbei, bevor gehandelt
   werden kann. Ein Ereignistyp-Flag wie „Gewinn verfehlt" ist dann oft
   nur eine Umschreibung dessen, was `reversal_2d/3d` bereits zeigt,
   nicht zusätzliche unabhängige Information.

**Die eine Ausnahme mit echtem Potenzial: PEAD** (Post-Earnings-
Announcement-Drift, Bernard & Thomas 1989, seit über 30 Jahren
repliziert) — die Kursbewegung nach einer Gewinnüberraschung setzt sich
über **Wochen** fort, nicht nur im ersten Moment. Das passt zur
Architektur, weil nicht die erste Sekunde erwischt werden muss, nur die
Fortsetzung Tage später. Von allen hier diskutierten News-Hypothesen
ist das die einzige, bei der ein IC deutlich über der generischen
Tonalitäts-Erwartung realistisch ist — und sie sollte im Historientest
(10.3) vorrangig geprüft werden, vor der breiteren Ereignistyp-Liste.

Wie überall in diesem Plan gilt: Das ist eine kalibrierte Erwartung,
keine Messung. Der Historientest liefert die echte Zahl.

### 10.2c Weitere Quellen mit vorhandener Infrastruktur

- **Ereignisstudien** — `events.py` und `06_event_study.py`.

Diese sind die naheliegendsten Erweiterungen des Kandidatenraums, weil
sie Information enthalten, die **nicht** im Kurs steckt — und damit
echte Diversifikation gegenüber den bestehenden Umkehr-Faktoren bieten,
die laut `signals.py` untereinander stark korreliert sind.

### 10.3 Der Prüfpfad

```
Behauptung erfassen  →  operationalisieren  →  Historientest (8 Jahre)
   → besteht?  →  als Bot/Faktor voranmelden  →  Vorwärtstest im Schatten
   → besteht?  →  in den Musterspeicher
```

Der Historientest ist der **billige Filter**: Was auf 8 Jahren
vorhandener Daten keinen Tages-IC mit |t| > 2 zeigt, bindet keine
Vorwärtszeit. Der Vorwärtstest ist die **teure Bestätigung** — und die
einzige, die zählt, weil nur sie nicht rückblickend ausgewählt ist.

Zusätzlicher Test bei publizierten Anomalien: IC **vor** und **nach**
dem Veröffentlichungsdatum getrennt messen. Fällt der Effekt danach
deutlich ab, ist das der Zerfall aus McLean & Pontiff — und ein starkes
Argument, die Idee nicht weiterzuverfolgen.

### 10.4 Tabelle

```sql
CREATE TABLE hypothesen (
    hyp_id            TEXT PRIMARY KEY,     -- 'HYP-012'
    behauptung        TEXT NOT NULL,        -- "RSI(2)<10 -> Ueberrendite ueber 3 Tage"
    quelle            TEXT NOT NULL,        -- Autor / Publikation / URL
    quelle_typ        TEXT NOT NULL,        -- akademisch|praktiker|broker|blog
    veroeffentlicht   TEXT,                 -- Datum der Quelle (fuer Zerfallstest)
    behaupteter_effekt TEXT,
    erfasst_am        TEXT NOT NULL,        -- VOR dem Test
    operationalisierung TEXT,               -- exakte Messvorschrift
    testbar           INTEGER,
    -- Historientest
    hist_ic REAL, hist_t REAL, hist_ic_vor_veroeff REAL, hist_ic_nach_veroeff REAL,
    -- Vorwaertstest
    fwd_ic REAL, fwd_t REAL, fwd_n_tage INTEGER,
    status            TEXT NOT NULL,        -- offen|im_test|bestaetigt|widerlegt|nicht_testbar
    entschieden_am    TEXT
);
```

`erfasst_am` vor `im_test` ist die Voranmeldung — dieselbe Disziplin wie
bei den Bots, aus demselben Grund.

---

## 11. Der Musterspeicher

Das ist die Antwort auf „mit der Zeit sollen immer klarere Muster
entstehen". Ein Muster ist eine **bedingte Aussage** mit Belegen und
Lebenszyklus.

```sql
CREATE TABLE muster (
    muster_id     TEXT PRIMARY KEY,
    beschreibung  TEXT NOT NULL,     -- "Umkehr traegt nur bei ruhiger Marktvola"
    bedingung     TEXT NOT NULL,     -- maschinenlesbar: "regime_vola in ('niedrig','mittel')"
    wirkung       TEXT NOT NULL,     -- 'ic_5d' | 'trefferquote' | 'rendite_netto'
    entdeckt_am   TEXT NOT NULL,
    entdeckt_aus  TEXT NOT NULL,     -- 'schatten' | 'historie' | 'hypothese:HYP-012'
    -- Belege
    n_tage        INTEGER, effekt REAL, t_wert REAL, schwelle REAL,
    sperrzone_effekt REAL,           -- Ergebnis auf den unberuehrten Daten
    -- Lebenszyklus: Muster verfallen
    status        TEXT NOT NULL,     -- kandidat|bestaetigt|zerfallen|widerlegt
    zuletzt_geprueft   TEXT,
    zuletzt_bestaetigt TEXT,
    zerfallen_seit     TEXT,
    angewendet_in TEXT               -- welche Bots nutzen es
);
```

### Verfallsprüfung

**Muster sind nicht dauerhaft.** Ein 2026 bestätigter Effekt kann 2027
verschwinden — durch Arbitrage, Regimewechsel oder Strukturbruch. Jedes
bestätigte Muster wird deshalb **monatlich auf den seither neu
hinzugekommenen Daten** erneut geprüft (nur diese, nicht die alten):

- hält es → `zuletzt_bestaetigt` fortschreiben
- hält es zwei Prüfungen in Folge nicht → `status = 'zerfallen'`,
  `zerfallen_seit` setzen, alle Bots melden, die es nutzen

Genau das ist das „immer klarer" aus der Vision: Nicht ein wachsender
Stapel von Behauptungen, sondern eine **kleine Menge wiederholt
bestätigter Bedingungen** — und die Gewissheit, es sofort zu merken,
wenn eine davon aufhört zu funktionieren.

---

## 12. Kaltstart aus vorhandenen Daten

Es muss nicht bei null begonnen werden. Bereits vorhanden:

| Bestand | Umfang |
|---|---|
| `data/cache/bars/yfinance_2168_*_8y.parquet` | 2.168 Symbole, 8 Jahre, 125 MB |
| `data/cache/edgar/` | 372 Form-4-Meldungen |
| `journal.sqlite` | 1.082 Simulationsentscheidungen mit Ergebnissen, 60 Live-Entscheidungen |
| Faktor-Labor | ICs für alle Kandidatenfaktoren über 9 Jahre |

Drei zulässige Verwendungen:

1. **Maschinenprüfung.** Der Flottencode wird über die Historie laufen
   gelassen und muss für `B00_basis` dieselben Trades erzeugen wie
   `simulate.py`. Weichen sie ab, ist einer von beiden falsch.

2. **Vorabschätzung der nötigen Laufzeit.** Aus der Historie lässt sich
   die Streuung der *Tagesdifferenz* zwischen zwei Bot-Varianten
   messen. Eingesetzt in die Formel aus 6.2 ergibt das die Zahl der
   Vorwärtstage bis zur Entscheidbarkeit — **bevor** das Experiment
   startet. Varianten, die selbst nach einem Jahr nicht unterscheidbar
   wären, werden gar nicht erst aufgenommen.

3. **Billiger Vorfilter für Hypothesen** (siehe 10.3).

**Nicht zulässig:** Die historische Rangfolge zur Auswahl des Gewinners
zu verwenden. Genau das wäre die Überanpassung, gegen die das ganze
System gebaut ist. Die Historie prüft die Maschine und filtert Ideen —
entschieden wird ausschließlich vorwärts.

---

## 13. Regimebedingung — wo der echte Gewinn liegt

Nach Abschnitt 1 der aussichtsreichste Hebel. Er ist billig, weil er nur
verlangt, den Kontext jeder Vorhersage mitzuspeichern (im Schema bereits
vorgesehen) und die Auswertung danach zu schneiden.

**Marktregime** (je Tag, aus SPY und dem Universum):

| Merkmal | Berechnung | Bänder |
|---|---|---|
| Trend | SPY über/unter SMA200 | auf / ab |
| Volatilität | realisierte 20-Tage-Vola von SPY, Perzentil über 2 Jahre | niedrig / mittel / hoch |
| Marktbreite | Anteil Symbole über eigenem SMA50 | eng / normal / breit |

**Symbolkontext** (je Vorhersage): ATR-Perzentil, Liquiditätsband,
Kursband.

Ausgewertet wird der IC **je Regime** statt nur global. Der
wahrscheinliche Befund — und er wäre ein echter Fortschritt: Der
Umkehr-Effekt konzentriert sich in bestimmten Regimen. Nur dort zu
handeln erhöht den Vorsprung je Trade und senkt gleichzeitig die
Kosten, weil weniger gehandelt wird.

**Warnung, die mitgeführt werden muss:** Regimeschnitte vervielfachen
die Zahl der Vergleiche. Drei Trenddimensionen × drei Volabänder ergeben
neun Zellen — und in mindestens einer davon sieht der Effekt großartig
aus, garantiert. Regimebefunde zählen deshalb voll in den
Versuchszähler aus 6.1, und es werden **nur die drei oben genannten
Achsen** geschnitten, nicht beliebig viele.

---

## 14. Korrektheitssicherungen

Die Forderung „wir müssen sicher gehen, dass bei den fiktiven Trades
alles richtig zugeht" entscheidet über Wert oder Wertlosigkeit des
ganzen Systems. Acht automatische Prüfungen, abrufbar über
`python scripts/17_shadow_report.py --pruefen`:

1. **Lookahead-Sperre.** `MarketSnapshot.validate()` existiert bereits
   und wirft bei Daten nach `as_of`. Wird unverändert übernommen.
2. **Kalenderprüfung.** Ist `as_of` ein abgeschlossener Handelstag?
   Liegt `entry_date` strikt danach? Sonst Abbruch des Laufs.
3. **Abgleich mit dem echten Bot.** Für jedes Symbol, das der Live-Bot
   tatsächlich gekauft hat, muss `B00_basis` im Spiegelbuch am selben
   Tag dieselbe Entscheidung treffen. Kursabweichung über 0,5 % wird
   gemeldet. Verglichen wird gegen `entry_price` (20 Min nach
   Eröffnung), **nicht** gegen `entry_price_open` — sonst meldet die
   Prüfung dauerhaft eine Abweichung, die nur der Buchungszeitpunkt ist
   (siehe 4.4). Gleichzeitig ein laufender Test yfinance gegen Alpaca —
   `datasources.compare_sources()` liefert die Messgröße bereits.
4. **Kursanpassungs-Erkennung.** Gespeicherten gegen neu geladenen Kurs
   prüfen (siehe 3.4), Abweichung als `data_check` festhalten statt
   überschreiben.
5. **Kostenkontrolle.** Angesetzte Basispunkte monatlich gegen die real
   gemessene Slippage. Ist der Schatten günstiger als das Depot, sind
   seine Zahlen zu optimistisch.
6. **Replay-Test.** `B00_basis` über die Historie muss dieselben Trades
   erzeugen wie `simulate.py`.
7. **Flottenkonsistenz.** Alle Bots eines Laufs müssen dieselbe `as_of`
   und dieselbe Symbolmenge gesehen haben — sonst ist der gepaarte
   Vergleich aus 6.2 ungültig.
8. **Buchführung.** Für jede Vorhersage mit `entry_date` in der
   Vergangenheit muss ein `entry_price` existieren; für jede
   geschlossene Position ein vollständiges Ergebnis. Lücken werden
   gemeldet, nicht geschätzt — analog zu `journal.integrity_check()`.
9. **Nachtrags-Disziplin.** Jede Vorhersage mit `nachgetragen = 1`
   muss eine `code_version` tragen, die mit der am ursprünglichen Tag
   aktiven übereinstimmt. Andernfalls darf sie in keiner
   Vorwärtsstatistik auftauchen (siehe 4.6). Die Prüfung meldet, wie
   viele Vorhersagen aus diesem Grund ausgeschlossen sind — eine
   stillschweigend wachsende Zahl wäre ein ernstes Warnzeichen.

---

## 15. Auswertung

Wochenkohorte, je Bot, Buch und Regime — immer mit Referenz.

**Signalgüte**
- IC (Spearman) zwischen Score und 5-Tage-Rendite, plus t-Statistik über
  die Tagesreihe. `research.py` rechnet das bereits genau so und wird
  wiederverwendet.
- Trefferquote **minus Basisrate** desselben Tages
- Kalibrierung: erreicht Score-Band 0,8–1,0 tatsächlich mehr als
  0,4–0,6? Eine nicht monotone Rangliste sortiert nicht.

**Regel- und Ausführungsgüte**
- Anteil erreichter Ziele / ausgelöster Stops
- MAE/MFE — beantwortet „Stop zu eng, Ziel zu niedrig?".
  `lifecycle.analyse()` ist direkt anwendbar
- Nachlauf nach dem Ausstieg: War der Ausstieg richtig?
- Umschlag und Kostenanteil je Bot

**Flotte**
- Gepaarte Vergleiche gegen `B00_basis` mit t-Wert und Schwelle
- Attributionszerlegung der Differenz (Abschnitt 7)
- Rangliste der Bots **mit** Angabe der Zufallsschwelle aus 3.5

**Fortschritt**
- Lernkurve je `code_version`: IC und Überschuss vor/nach einer Änderung,
  auf denselben Kalenderwochen verglichen
- Musterbestand: bestätigt / zerfallen / Kandidat, mit Prüfdatum

**Ehrlichkeitsregeln, technisch erzwungen:**
- Jede Kennzahl wird mit `n_tage` ausgewiesen, nicht nur mit `n`
- Unter 60 Handelstagen gilt jeder Vergleich als „zu dünn"
- Jede Bot-Rangliste zeigt die Zufallsschwelle mit an
- Die Sperrzone ist standardmäßig abgeschnitten (siehe 6.3)

---

## 16. Phasenplan

**Phase 1 — Fundament** ✅ **ERLEDIGT 2026-07-29**
`shadow.py`, Schema, Rangliste-Buch, Entscheiden + Einbuchen +
Verifizieren, `16_shadow_daemon.py`, nur `B00_basis`.

Umgesetzt und geprüft:
- `src/alpaca_bot/shadow.py` — eigene DB `data/shadow.sqlite`, importiert
  bewusst kein `trading.py` (kann konstruktionsbedingt keine Order senden)
- `scripts/16_shadow_daemon.py` — `--status`, `--einmal`, `--schritt`,
  Dauerbetrieb, sauberes Beenden per Signal
- `install_service.sh --dienst schatten` (§4.5) — zweiter launchd-Dienst
  neben dem Handelsbot, eigene Protokolle `logs/shadow.*`
- **Erster Produktionslauf: 157 Kandidaten an einem Tag** gegenüber
  3 Käufen des Live-Bots — der ~52-fache Beobachtungsgewinn
- Kette end-to-end auf rückdatierten Vorhersagen getestet
  (eigene Test-DB, keine Testdaten in der Produktionsdatenbank):
  Einstieg immer **nach** dem Stichtag, MAE nie positiv, MFE nie negativ,
  MFE ≥ MAE, Überschuss-Median definitionsgemäß 0
- **Eigener Tages-Cache** statt `datasources.get_history(use_cache=True)`:
  dessen Cache-Schlüssel enthält kein Datum, ein täglicher Dienst hätte
  stillschweigend ewig dieselben Daten bekommen

→ Ab Tag 1 laufen Vorwärtsdaten auf. Vorher passiert kein Lernen.

**Phase 2 — Ehrlichkeit** ✅ **ERLEDIGT 2026-07-29**
Spiegelbuch mit Kosten, Kapitalgrenzen, Sperrfrist und aufgeschobener
Ausführung (`_spiegel` in `shadow.py`); **neun** Prüfungen statt acht
(Nachtrags-Disziplin kam dazu), abrufbar über
`17_shadow_report.py --pruefen`.

- Eigene Sperrfrist-Quelle (`ShadowEngine`): `Engine._cooldown_symbols()`
  liest fest aus `state.sqlite`, also aus dem Zustand des **Live**-Bots.
  Ungeprüft übernommen hätte der Schatten Symbole gemieden, die nur das
  echte Depot verkauft hat — und umgekehrt. Überschrieben statt
  `engine.py` zu ändern.
- **Prüfung 1 fand einen echten Bug im Spiegelbuch:** Beim Nachholen
  fehlender Tage wurde als Stichtag der *letzte* Tag gespeichert statt des
  Entscheidungstags — der Einstieg lag dadurch formal vor der Entscheidung.
  Behoben über `spiegel_pending.as_of`.
- Idempotenz über `shadow_cash.letzter_tag`: Ein Tag wird nie zweimal
  ausgeführt, auch wenn der Daemon stündlich läuft.
→ 9 von 9 Prüfungen bestanden.

**Phase 3 — Auswertung** ✅ **ERLEDIGT 2026-07-29**
`shadow_eval.py` + `scripts/17_shadow_report.py`: Querschnitts-IC je Tag
mit t-Statistik, Kalibrierung nach Score-Bändern, Wochenkohorten,
Basisraten-Vergleich, Überschuss gegen Universums-Median.

Drei Ehrlichkeitsregeln technisch erzwungen: Sperrzone standardmäßig
abgeschnitten (`--sperrzone-oeffnen` warnt laut), `n_tage` immer
ausgewiesen, nachgetragene Läufe automatisch aus jeder Vorwärtsstatistik
gefiltert.
→ Maschinerie steht; belastbare Diagnosen weiterhin erst nach 2–4 Wochen.

**Phase 4 — Flotte** ✅ **ERLEDIGT 2026-07-29**
`fleet.py` + `scripts/18_fleet.py`: Voranmeldung mit Pflicht-Hypothese
(mind. 20 Zeichen) und Pflicht-Achse, Versuchszähler der stillgelegte
Bots weiterzählt, Zufallsschwelle `sqrt(2·ln N) + 0,5`, gepaarter
Vergleich über Tagesdifferenzen, Attribution, Divergenz-Diagnose.

- **Signalteilung**: 7 Bots brauchen nur **2** Signaldurchläufe, weil die
  meisten Varianten nur Ausstiegsparameter ändern.
- Erster Produktionslauf: **1.058 Vorhersagen an einem Tag** über 7 Bots.
- Die Divergenz-Diagnose fand sofort zwei wirkungslose Varianten (§5.3).
→ Erste Bot-Vergleiche nach 6–10 Wochen.

**Phase 5 — Regime und Muster** ✅ **ERLEDIGT 2026-07-29**
Regimemerkmale (Markttrend, Volatilitätsband, Marktbreite) werden bei
jeder Vorhersage mitgespeichert. `patterns.py`: Musterspeicher mit
Lebenszyklus kandidat → bestätigt → zerfallen, monatliche
Verfallsprüfung **nur auf neu hinzugekommenen Daten**, Zerfall nach zwei
Fehlschlägen in Folge. `kandidaten_suchen()` schneidet ausschließlich die
drei festgelegten Achsen und warnt ausdrücklich, dass Funde Hypothesen
sind, keine Befunde.
→ Hier entstehen die eigentlichen Erkenntnisse — ab ~60 Handelstagen.

**Phase 6 — Externes Wissen** ✅ **ERLEDIGT 2026-07-29** (Erfassung)
`hypotheses.py`: Register mit Voranmeldung, Quellenklassen-Prior,
Historientest, und Zerfallstest vor/nach Veröffentlichungsdatum
(McLean & Pontiff).

`news_features.py`: Ereignistyp-Erkennung über 11 Regex-Muster,
Tonalität über finanzspezifische Wortlisten — kein trainiertes Modell.
Anbindung an den Schattenbetrieb über `--mit-news` (bewusst optional,
kostet Alpaca-Kontingent). **Die Merkmale beeinflussen die Entscheidung
nicht** — sie werden nur mitgeschrieben, damit später messbar ist, ob sie
etwas beitragen.

Beim Testen zwei eigene Fehler gefunden und behoben: „Analyst Upgrades
Tesla To Buy" wurde als Übernahme erkannt (Muster `to buy` entfernt), und
„Company Denies Bankruptcy Rumors" ergab +1,00 statt neutral
(Verneinung dämpft jetzt, statt das Vorzeichen zu kippen).
→ Offen bleibt der **Historientest** der News-Faktoren — das ist eine
Datenauswertung und wartet bewusst.

**Phase 7 — Modell** *(erst ab ~6 Monaten Vorwärtsdaten)*
Schattenergebnisse als Trainingsmenge für `ml.py`
(`walk_forward_predict` mit Embargo). Ersetzt oder ergänzt den linearen
Score.
→ **Bewusst zuletzt.** Ein Modell auf zwei Wochen Schattendaten zu
trainieren erzeugt einen Zufallsgenerator mit Gedächtnis.

Die Reihenfolge ist nicht verhandelbar: Phase 2 vor jeder Interpretation
von Phase-1-Zahlen; Phase 4 erst, wenn die Prüfungen greifen; Phase 7
zuletzt.

---

## 17. Was das System nicht leistet

- **Es ersetzt das Papierdepot nicht.** Slippage, Teilausführungen,
  Broker-Ablehnungen und PDT-Effekte zeigen sich nur dort.
- **Es macht die Strategie nicht besser, es misst sie.** Die
  Verbesserung entsteht erst, wo aus einem belastbaren Befund eine
  Regeländerung wird — eine bewusste Entscheidung, kein Automatismus.
  Der Versuch, das zu automatisieren, hätte bei den hier erreichbaren
  Datenmengen mit hoher Wahrscheinlichkeit Rauschen als Regel
  festgeschrieben.
- **Es beschleunigt nicht um den Faktor 100.** Wegen der Korrelation
  innerhalb eines Tages (3.2) ist der Faktor für absolute Aussagen 3–5.
  Für gepaarte Bot-Vergleiche ist er deutlich größer (10–25), und
  darauf liegt deshalb der Schwerpunkt.
- **Es schützt nicht vor Überanpassung, es macht sie messbar.** Wer 50
  Varianten testet, findet garantiert eine gute. Der Versuchszähler
  sorgt dafür, dass man weiß, wie gut sie sein müsste, um etwas zu
  bedeuten.
- **Es hebt die Obergrenze der Richtungsprognose nicht an.** Siehe
  Abschnitt 1: Der Gewinn kommt aus Bedingung, Größe und Kosten — nicht
  aus einer steigenden Trefferquote.
