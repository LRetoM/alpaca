# Masterplan 2027: Vom Umkehr-Bot zum kostentragfähigen System

> Stand: 2026-09-29. Geschrieben nach vollständiger Durchsicht aller Docs,
> aller Module, der Commit-Historie seit Juli 2026, einer Web-Recherche zu
> Strategien und Datenquellen, und nach eigenen Messungen auf drei frei
> verfügbaren Datensätzen (siehe §6). Alle Zahlen in §6 sind reproduzierbar
> mit `scripts/20_…26_`.
>
> Ehrlichkeitsvermerk vorweg: Der Rechner, auf dem dieser Plan entstand,
> hatte keinen Zugang zu Yahoo, Alpaca, FRED oder SEC. Die Messungen laufen
> deshalb auf Ersatzdaten (Qlib-US-Sammlung bis 11/2020, S&P-500-Schlusskurse
> 2016–2026, Lean-Beispieldaten für SPY/QQQ/IWM). **Der erste Schritt auf
> deinem Mac ist, dieselben Skripte auf dem Projektcache mit 2.168 Symbolen
> laufen zu lassen** (§8, Schritt 0). Erst diese Zahlen zählen.

---

## Inhalt

0. [Kurzfassung in zehn Sätzen](#0-kurzfassung-in-zehn-sätzen)
1. [Was in den letzten Monaten gebaut und gemessen wurde](#1-was-in-den-letzten-monaten-gebaut-und-gemessen-wurde)
2. [Warum das heutige System nicht besser als ein ETF ist](#2-warum-das-heutige-system-nicht-besser-als-ein-etf-ist)
3. [Was sich seit dem Sommer geändert hat (Regulierung, Broker)](#3-was-sich-seit-dem-sommer-geändert-hat-regulierung-broker)
4. [Der Ideenraum: was die Evidenz hergibt](#4-der-ideenraum-was-die-evidenz-hergibt)
5. [Der Hypothesenkatalog 2027](#5-der-hypothesenkatalog-2027)
6. [Eigene Messungen — Ergebnisse](#6-eigene-messungen--ergebnisse)
7. [Die Zielarchitektur 2027](#7-die-zielarchitektur-2027)
8. [Bauplan mit Zeitachse bis Januar 2027](#8-bauplan-mit-zeitachse-bis-januar-2027)
9. [Welche Zahlen wir uns erhoffen — und ab wann wir abbrechen](#9-welche-zahlen-wir-uns-erhoffen--und-ab-wann-wir-abbrechen)
10. [Was bewusst nicht gemacht wird](#10-was-bewusst-nicht-gemacht-wird)

---

## 0. Kurzfassung in zehn Sätzen

1. Die Infrastruktur ist fertig und besser als bei 95 % aller Privatprojekte:
   eine Engine für Backtest, Papierdepot und Schattenflotte, PIT-Wächter,
   Kostenmodell, Journal, Lebenslauf, neun laufende Schattenbots.
2. Die **Strategie** darauf ist die Schwachstelle: Kurzfrist-Umkehr mit fünf
   Tagen Haltedauer verdient +0,11 % je Trade und zahlt 0,14 % Kosten je
   Rundlauf. Das ist mathematisch verloren, egal wie gut das Signal wird.
3. Der Hebel heißt deshalb nicht „besseres Signal“, sondern **mehr Vorsprung
   je Trade als Kosten je Trade**. Auf Einzelaktien geht das auf zwei Wegen,
   die beide gebaut werden: **kurz** (5–10 Tage, Mehrfaktor statt reiner
   Umkehr, nur die liquidesten 800 Werte, Kosten ≤ 20 bps) und **mittel**
   (3–6 Wochen, Konsistenz-Momentum plus ruhiges Volumen). Welcher Weg mehr
   verdient, entscheidet die Haltedauer-Kurve (§6.6), nicht die Vorliebe.
4. Die stärksten Bausteine auf Einzelaktien (gemessen auf 8.061 US-Aktien,
   2005–2020, §6.5): **ruhiges Volumen** (sechs Monate unter dem eigenen
   Vorjahresumsatz — stabilster Faktor im Zoo), **Momentum-Konsistenz**
   (Anteil positiver Monate), **5-Tage-Umkehr** (stärkster Kurzfrist-Faktor,
   t = 3,8) und der **1-Tages-Volumenschock**. Das Wochen-Volumenpremium aus
   der Literatur ist in liquiden Werten tot; Gap-ups mit Volumen kehren um.
   PEAD braucht echte Ergebnistermine (EDGAR 8-K) — der Proxy taugt nicht.
5. Für den Daytrading-Wunsch gibt es genau **einen** wissenschaftlich sauber
   dokumentierten Ansatz: Opening-Range-Breakout auf den 20 Aktien mit dem
   höchsten relativen Volumen der ersten fünf Minuten (Sharpe 2,4–2,8 im
   Paper). Er wird als kontrollierter Test gebaut — mit der Erwartung, dass
   IEX-Daten und Kosten den Großteil davon auffressen.
6. **ETFs sind nicht das Ziel.** SPY und VIX dienen nur als Regime-Anzeiger
   (wann Einzelaktien gekauft werden dürfen). Die Overnight-Prämie bei
   QQQ/IWM (brutto 12–13 % p.a., Breakeven 2,6 bps je Ausführung) bleibt
   ein Nebentest mit Auktionsorders und kleinem Kapitaldeckel — mehr nicht.
7. **Regimefilter** (SPY über SMA200, VIX unter 25) und **Volatilitäts-Sizing**
   sind die zwei Hebel, die den Drawdown steuern; sie kosten in
   Erholungsjahren (2020) und zahlen in Bärenjahren (2022).
8. Die **PDT-Regel ist seit 04.06.2026 abgeschafft**; `compliance.py` weiß
   das noch nicht. Für den Daytrading-Test ist der Weg frei, für den Rest
   ändert es nichts.
9. Zeitplan: Oktober 2026 messen auf deinen Daten, November bauen und in
   der Schattenflotte voranmelden, Dezember Papierdepot mit der neuen
   Engine-Konfiguration, **Januar 2027 Start** — klein, mit Risiko-Dach.
10. Realistische Erwartung nach Kosten: **SPY + 3 bis 8 Prozentpunkte p.a.**
    bei Sharpe 0,8–1,3 und maximalem Drawdown von 20–30 % für das
    Einzelaktien-Ranking (kurz oder mittel, je nach §6.6); für den ORB-
    Daytrading-Test Sharpe > 1 als Bestehensgrenze. Gewinnmaximierung heißt
    hier: konzentrierter (Top 10 statt 20), kürzer (wenn die Kurve es
    erlaubt), und voll investiert im richtigen Regime — nicht: mehr
    handeln. „Zuverlässig hohe Margen mit Daytrading“ verspricht dieser Plan
    nicht, weil kein ehrlicher Datensatz sie hergibt; er baut den Test, der
    es zeigen oder widerlegen kann.

---

## 1. Was in den letzten Monaten gebaut und gemessen wurde

### 1.1 Gebaut (26 Commits seit dem Initial-Commit)

| Baustein | Datei | Zustand |
|---|---|---|
| Entscheidungs-Engine, EIN Pfad für alles | `engine.py` | fertig, zustandslos, Lookahead strukturell unmöglich |
| Historien-Replay Tag für Tag mit Kosten, PDT, Kurslücken | `simulate.py` | fertig |
| Live-Pfad, Daemon als Dienst, Wiederanlauf | `live.py`, `daemon.py`, `install_service.sh` | fertig, läuft im Papierdepot |
| Journal: Entscheidung → Begründung → Ergebnis | `journal.py` | fertig |
| Trade-Lebenslauf (MAE/MFE/Nachlauf) | `lifecycle.py` | fertig |
| Schattenbetrieb + Flotte + gepaarter Vergleich | `shadow.py`, `fleet.py`, `shadow_eval.py` | fertig, 9 Bots seit 29.07.2026 |
| Hypothesenregister, Musterspeicher | `hypotheses.py`, `patterns.py` | fertig, bisher leer |
| Faktor-Labor (Schleifen-IC) | `research.py`, `11_factor_lab.py` | fertig, einmal gelaufen |
| EDGAR Form 4, News-Merkmale | `edgar.py`, `news.py`, `news_features.py` | gebaut, **nicht historisch getestet** |
| Kosten mit Prüfdatum, Breakeven | `costs.py` | fertig |
| PIT-Wächter, Drei-Umschlag-Protokoll | `pit.py` | fertig |
| Datenintegrität, Health-Check | `data_integrity.py`, `18_health_check.py` | fertig |
| DQN mit Timing-Test | `rl/` | gebaut, Ergebnis nicht dokumentiert |
| **Neu (dieser Plan):** Labor 2027 | `labor.py`, `scripts/20_–27_` | fertig, siehe §6 |

### 1.2 Gemessen — die Zahlen, die bleiben

| Befund | Zahl | Quelle |
|---|---|---|
| Erster Anlauf (Momentum-Mehrfaktor, 17 Tage Haltedauer) | IC −0,05, **−127 Prozentpunkte** gegen Buy & Hold | `research.py` Docstring |
| Umkehr-Faktoren auf 2.162 Symbolen, 9 Jahre | reversal_3d IC +0,018, rsi2 +0,016, 100 % positive Jahre | `signals.ReversalWeights` |
| Dieselben Faktoren auf 150 liquidesten Werten | **nicht nachweisbar** (rsi2: 29 % positive Jahre) | `universe.load_universe` |
| Umkehr-Strategie 5 Jahre, 400 Symbole, netto | **+7,4 %** gesamt gegen **+80,7 %** SPY; Kosten 72–109 % des Brutto | `docs/schattenbetrieb.md` §0.2 |
| Score-Schwelle 0,35 → 0,75 | Trefferquote **sinkt** 52,0 % → 49,2 % | dito |
| Vorsprung je Trade vs. Breakeven | +0,11 % vs. 0,142 % (5 bps Spread) | `docs/mehrbot-plan.md` §0 |
| Eröffnung vs. 09:50-Kurs | −0,58 bps, t = −0,18 (kein Effekt) | `docs/schattenbetrieb.md` §0.1 |
| Investitionsgrad bei 15/15 Positionen | 53,9 % statt 90 % (Vola-Skalierung) | dito §5.3 |
| Schattenflotte: wirkungslose Varianten | B03 (Ziel) identisch mit Basis; B06 (Regime) im Testfenster nie aktiv | dito |
| Handelbares Universum bei ≥ 1 Mio. $/Tag | 2.189 von 8.464 Symbolen | `docs/mehrbot-plan.md` §10 |
| Live-Ausführungsmessung | 30 Orders, davon 14 auswertbar, Referenzpreis-Fehler behoben (Commits 107f982, 9c26b6a) | Commit-Log |

### 1.3 Was gebaut, aber nie ausgewertet wurde

- **PEAD-Historientest** (§0.3 im Schattenplan): offen.
- **News-Faktor-IC** (`f_news` mit Gewicht 0,10 im Live-Bot seit 03.08.2026): **ungetestet im Einsatz** — ein bewusster Regelbruch, der protokolliert ist (`news_aktiv`-Flag).
- **Insider-Cluster** (`edgar.py`, 372 Form-4-Meldungen im Cache): nur in der verworfenen Momentum-Strategie verkabelt, nie als Ereignisstudie gemessen.
- **Ereignisstudie** (`06_event_study.py`): Skript existiert, Ergebnis nirgends dokumentiert.
- **DQN** (`08_train_rl.py`): Ergebnis nirgends dokumentiert.
- **Regime-Schnitte** im Schatten: erst ab ~60 Handelstagen belastbar, also ab ~Ende Oktober 2026.

---

## 2. Warum das heutige System nicht besser als ein ETF ist

Es ist schlechter. Drei Ursachen, alle gemessen, alle strukturell:

**Ursache 1 — Der Zeithorizont ist falsch.** Ein IC von 0,018 auf 3–5 Tagen
ist echt, aber er ist eine *Quintil-Spanne* von ein paar Zehntelprozent je
Trade. Bei 5 Tagen Haltedauer und 15 Positionen entstehen ~600 Rundläufe im
Jahr. Jeder kostet 0,14 %. Das sind 80–90 % Kapital pro Jahr an Kosten,
gegen einen Bruttovorsprung von vielleicht 60–70 %. Das Verhältnis kann
kein Signal der Welt drehen.

**Ursache 2 — Long-only Umkehr steht im Bullenmarkt oft in Cash.** Umkehr-
Kandidaten sind gefallene Werte; in einem Markt, der 15 % p.a. steigt,
verpasst man den Markt selbst. Der Regimefilter verhindert Käufe im Crash,
kauft aber auch nicht die Erholung.

**Ursache 3 — Der Score sortiert oben nicht.** Trefferquote fällt mit dem
Score. Eine Rangliste, die oben schlechter wird, ist ein Zufallsgenerator
mit Vorfilter.

Was daraus folgt, ist der ganze Plan: **weniger handeln, länger halten,
anders auswählen** — und die Auswahl auf Merkmale stützen, deren Wirkung auf
3–8 Wochen dokumentiert ist, nicht auf 3 Tage.

---

## 3. Was sich seit dem Sommer geändert hat (Regulierung, Broker)

| Änderung | Datum | Bedeutung für uns | Quelle |
|---|---|---|---|
| **PDT-Regel abgeschafft** (FINRA Rule 4210, SEC-Zustimmung) | Zustimmung 14.04.2026, wirksam 04.06.2026, Broker bis 20.10.2027 | Daytrading unter 25.000 $ ist erlaubt. `compliance.py` prüft noch die alte Regel → am eigenen Konto verifizieren, dann anpassen. Die Projektverfassung in `selfcheck.py` nennt PDT noch als Ausschlussgrund. | Schwab, QuantInsti, Alpaca-Blog |
| Alpaca 24/5-Handel (Overnight-Session, Blue Ocean ATS) | 2026 | Nur Limit-Orders, dünn. Für uns nur relevant als Datenquelle, nicht als Handelsweg. | Alpaca Docs |
| Alpaca Krypto-Gebühren | Maker 0,15 % / Taker 0,25 % | Krypto-Momentum braucht ≥ 1 Woche Haltedauer, sonst tot. | Alpaca Docs |
| SEC Section 31 | 20,60 $/Mio. seit 04.04.2026 | in `costs.py` hinterlegt, jährlich prüfen | FeeSchedule |
| FINRA Short Interest | halbmonatlich, Archiv ab 2014, kostenlos | neue freie Signalquelle (HYP-10) | FINRA |
| FINRA Reg-SHO-Tagesvolumen | täglich seit 2009, kostenlos | Literatur: nur Nowcast, kein Signal — als Negativtest | FINRA, Equibles 2025 |
| EDGAR 8-K Item 2.02 | seit 2004, sekundengenau | die freie Quelle für Ergebnistermine (HYP-03) | SEC |

---

## 4. Der Ideenraum: was die Evidenz hergibt

Bewertung nach drei Kriterien: Evidenz (repliziert, lebt noch), Kosten-
Tragfähigkeit bei Alpaca, Datenverfügbarkeit im kostenlosen Rahmen.

| Idee | Evidenz | Kosten-tragfähig? | Daten frei? | Urteil |
|---|---|---|---|---|
| Querschnitts-Momentum 12-1, 3–6 Wochen | ★★★★★ | ja (Umschlag ~12–24×/J) | ja | **Kern** |
| High-Volume-Return-Premium (1 Woche) | ★★★★☆ (GKM 2001, Wang 2021) | ja bei H ≥ 21 | ja | **Kern-Zusatz** |
| PEAD über EAR (ohne Analysten) | ★★★★★ | ja (H = 42–63) | ja (8-K) | **Kern-Zusatz** |
| Regimefilter SMA200 / VIX | ★★★★☆ | kostet nichts | ja | **Pflicht** |
| Vola-Targeting / 1/Vola-Sizing | ★★★★★ | kostet nichts | ja | **Pflicht** |
| ORB auf Stocks in Play (Daytrading) | ★★★☆☆ (2 Paper, 1 Team) | **fraglich** (IEX, Slippage) | ja (Alpaca Minuten) | **ein Test** |
| Overnight-Prämie QQQ/IWM mit Auktionsorders | ★★★★☆ brutto, netto strittig | nur mit MOO/MOC | ja | Nebentest |
| Insider-Cluster (Form 4) | ★★★★☆ | ja (selten, lange Haltedauer) | ja | Zusatzbaustein |
| Short Interest als Ausschluss | ★★★★☆ | ja | ja (FINRA) | Zusatzbaustein |
| ML-Ranker (LightGBM) über Faktorzoo | ★★★★☆ | wie das Ranking | ja | ab Nov 2026 |
| Kurzfrist-Umkehr (heutiger Bot) | ★★★☆☆ | **nein** (gemessen) | ja | nur auf Large Caps mit H ≥ 10 |
| 52-Wochen-Hoch kurzfristig | ★★☆☆☆ (eigene Messung negativ 2016–2026) | — | ja | verworfen |
| Low-Vol als Auswahlfaktor | ★★☆☆☆ (2016–2026 negativ) | — | ja | nur als Sizing |
| Intraday-Momentum SPY (letzte 30 min) | ★★☆☆☆ (post-2020 schwach) | nein | ja | Negativtest |
| Reg-SHO-Tagesshortvolumen | ★☆☆☆☆ | — | ja | Negativtest |
| Krypto-Momentum (BTC/ETH) | ★★★☆☆ | nur wöchentlich | ja | Diversifikation, später |
| News-Ton | ★☆☆☆☆ | — | Kontingent | verworfen |
| Chartformationen, Fibonacci, Elliott | ☆ | — | — | verworfen |
| HFT, Market Making, Level 2 | unerreichbar | — | nein | verworfen |

---

## 5. Der Hypothesenkatalog 2027

Vollständig, mit Messvorschrift und Erwartung, in
`src/alpaca_bot/hypothesen_2027.py`; Registrierung mit
`scripts/27_hypothesen_anmelden.py --anmelden`. Hier die Kurzform:

| ID | Prio | These | Skript | Bestehensgrenze |
|---|---|---|---|---|
| HYP-01 | 1 | Momentum 12-1 + Konsistenz, Top 20, H=21, über SMA200 schlägt SPY netto bei kleinerem DD | 22 momentum | +2 %-Pkt CAGR, DD < SPY, 2022 besser als SPY |
| HYP-02 | 1 | Volumen-Schub 1 Woche sagt 4-Wochen-Rendite voraus; Kombi > Kombi ohne Volumen | 21, 22 kombi | IC > 0,01, ≥ 75 % Jahre, Kombi-Vorteil t > 2 |
| HYP-03 | 1 | PEAD über Ergebnistagsrendite (EAR), Termine aus 8-K | 22 ear + EDGAR | +3 %-Pkt netto, H=42 |
| HYP-04 | 1 | ORB nur auf Top-20-Relativvolumen ist netto profitabel | 26 | Sharpe > 1 netto UND Top-RV > Zufallsauswahl (t > 3) |
| HYP-05 | 1 | Regimefilter senkt MaxDD ≥ ⅓ bei ≤ 2 %-Pkt CAGR-Verlust | 22 (4 Regime) | wie formuliert |
| HYP-06 | 2 | LightGBM-Ranker: OOS-IC ≥ 0,03, Sharpe > 1 | 23 | wie formuliert |
| HYP-07 | 2 | Overnight QQQ/IWM mit Auktionsorders netto positiv | 25 + Papierhandel | Fill-Kosten < 1 bps gemessen |
| HYP-08 | 2 | Insider-Cluster +2–5 % über 6 Monate | 06 (Erweiterung) | t > 2 gegen Kontrollgruppe |
| HYP-09 | 2 | Umkehr trägt nur Large Cap + H ≥ 10 | 24 reversal | Netto-CAGR steigt mit H |
| HYP-10 | 2 | Short Interest als Ausschlussfilter; Reg-SHO-Tagesvolumen wertlos | 28 (neu) | SI-IC < −0,01; SHO-IC ≈ 0 |
| HYP-11 | 3 | 52-W-Hoch kurzfristig negativ, langfristig positiv | 21 h=126/252 | — |
| HYP-12 | 3 | Low-Vol nur als Sizing nützlich | 22 --vola-ziel | Sharpe +20 % |
| HYP-13 | 3 | Krypto-Momentum wöchentlich überlebt 25 bps | 29 (neu) | Sharpe > 0,5 |
| HYP-14 | 3 | News-Frequenz hat IC, Ton nicht | 30 (neu) | news_z t > 2 |
| HYP-15 | 3 | Sektorneutralität senkt DD in Rotationsphasen | labor-Erweiterung | DD −5 %-Pkt |
| HYP-16 | 3 | Intraday-Momentum SPY tot | 31 (neu) | Widerlegung erwartet |

Mit 16 Hypothesen plus 9 Flottenbots plus den bisherigen Versuchen liegt der
Versuchszähler bei ~30 → Zufallsschwelle **sqrt(2·ln 30) + 0,5 ≈ 3,1 Sigma**.
Ein t-Wert von 2,5 ist ab jetzt kein Befund mehr.

---

## 6. Eigene Messungen — Ergebnisse

### 6.1 Datenbasis (Ersatz, weil Yahoo/Alpaca gesperrt waren)

| Panel | Inhalt | Zeitraum | Bias |
|---|---|---|---|
| `qlib` | 8.061 US-Aktien, OHLCV (Qlib/Yahoo-Sammlung, GitHub-Release) | 2004-01 – 2020-11 | Survivorship (Liste von 11/2020), **kein 2022** |
| `sp500_close` | 629 heutige S&P-500-Werte, nur bereinigte Schlusskurse | 2016-01 – 2026-09 | **Index-Aufnahme-Bias** (heutige Mitglieder) |
| `lean` | SPY, QQQ (Lücke 2005–2010), IWM, OHLCV, splitbereinigt | 1998 – 2021-03 | keiner |
| VIX | CBOE Tagesschluss | 1990 – 2026-09 | keiner |

Zulassung je Tag: Kurs ≥ 3 $ und Median-Umsatz ≥ 1 Mio. $/Tag über 60 Tage,
**rollierend** (kein Blick auf spätere Liquidität). Kosten 10/20/40 bps je
Rundlauf. Einstieg immer zur Eröffnung des Folgetags.

### 6.2 Faktorzoo — S&P 500 2016–2026 (nur Kursfaktoren, 21 Tage)

| Faktor | IC | t_defl | Jahre positiv | schlechtestes Jahr | Lesart |
|---|---|---|---|---|---|
| mom_12_1 | +0,017 | +0,9 | 80 % | −0,042 (2021) | positiv, in 2021 (Rotation) negativ |
| mom_konsistenz | +0,012 | +0,9 | 82 % | −0,046 (2016) | stabiler als mom_12_1, kleiner |
| mom_12_1_vola | +0,016 | +0,9 | 90 % | −0,034 | **stabilste Momentum-Fassung** |
| reversal_5d (h=5) | +0,013 | +1,6 | 100 % | +0,002 | echt, aber winzig — bestätigt §1.2 |
| reversal_21d | +0,015 | +1,0 | 73 % | −0,044 | instabil |
| abstand_52w_tief | +0,025 | +1,6 | 64 % | −0,021 | Erholungs-Effekt, 2020/2024 stark |
| naehe_52w_hoch | **−0,015** | −0,8 | 18 % | −0,080 | **kurzfristig invertiert** (HYP-11) |
| vola_niedrig | **−0,032** | −1,7 | 27 % | −0,107 | Bullenmarkt-Beta, nicht als Faktor (HYP-12) |
| rel_staerke_63 | −0,009 | −0,6 | 36 % | −0,069 | Rauschen bis negativ |

Alle t-Werte sind klein, weil 500 Namen wenig Breite sind und die
Deflation um sqrt(21) hart ist. Die Richtung ist informativ, die Größe nicht.

### 6.3 Rangportfolio Momentum, S&P 500 2016–2026 (Obergrenze!)

Top 20, H=21, Kosten 20 bps, Einstieg Eröffnung T+1:

| Regime | CAGR | SPY | Sharpe | MaxDD | SPY DD | Umschlag/J |
|---|---|---|---|---|---|---|
| kein | **31,6 %** | 14,8 % | 1,07 | −45 % | −34 % | 23,6 |
| SPY > SMA200 | 21,3 % | 14,8 % | 0,94 | −34 % | −34 % | 17,6 |
| VIX < 25 | 20,3 % | 14,8 % | 0,89 | −30 % | −34 % | 20,2 |
| beides | 17,1 % | 14,8 % | 0,85 | −26 % | −34 % | 16,3 |

Jahre (kein Regime): 2018 +0,2 % (SPY −4,6 %), 2020 +46,6 % (+18,3 %),
2021 +24,0 % (+28,7 %), **2022 −3,8 % (−18,2 %)**, 2024 +82 % (+25 %).

**Warum das zu gut ist:** Die Liste enthält Werte wie PLTR, VST, SMCI, die
*wegen* ihres Anstiegs in den Index kamen. Momentum wählt sie vor der
Aufnahme aus — ein Lookahead über die Universumsdefinition. Die Zahlen sind
eine Obergrenze; die ehrliche Größenordnung liefert `qlib` (§6.5) und danach
dein Projektcache. Was trotzdem bleibt: Der Regimefilter senkt den Drawdown
in jeder Fassung (HYP-05 vorläufig bestätigt), und 2022 ist mit Momentum
deutlich besser als der Markt.

### 6.4 Overnight-Prämie (Lean, splitbereinigt, 2000–2021)

| Symbol | Overnight brutto CAGR / Sharpe | Intraday CAGR | Buy & Hold | Breakeven je Ausführung |
|---|---|---|---|---|
| SPY | +4,0 % / 0,39 | +0,7 % | +4,8 % | **0,9 bps** |
| QQQ | +12,7 % / 0,84 | −6,0 % | +5,9 % | 2,6 bps |
| IWM | +13,4 % / 1,01 | −4,9 % | +7,9 % | 2,7 bps |

Netto bei 1 bps je Seite: SPY −1,1 %, QQQ +7,2 %, IWM +7,8 % (Sharpe 0,5–0,6).
Bei 2 bps: QQQ +1,9 %, IWM +2,5 %. Bedingt „nur über SMA200“: IWM Sharpe
1,28 brutto, 0,86 bei 1 bps. **Urteil:** Bei Spread-Ausführung tot (deckt
sich mit Alpha Architect). Mit Auktionsorders (Alpaca `cls`/`opg`, kein
Spread, nur SEC/TAF ≈ 0,3 bps) rechnerisch positiv — deshalb HYP-07 als
Papierhandels-Test mit gemessenen Fill-Abweichungen, nicht als Backtest.
Vorbehalt: Daten enden 03/2021; ob die Prämie 2022–2026 noch besteht, muss
der Projektcache zeigen.

### 6.5 Breites Universum (qlib, 2005–2020): Faktorzoo

8.061 Symbole, davon je Tag ~2.500–3.500 zugelassen (Kurs ≥ 3 $, Umsatz
≥ 1 Mio. $). 20 Faktoren × 5 Horizonte, 1.720 s Rechenzeit. Sortiert nach
deflationiertem t-Wert, Horizont 21 Tage (der Multi-Wochen-Fall):

| Faktor | IC h=5 | IC h=21 | IC h=42 | t_defl h=21 | Jahre positiv | schlechtestes Jahr | Q5−Q1 p.a. (h=21) | Urteil |
|---|---|---|---|---|---|---|---|---|
| **vol_schub_6m_neg** („ruhige“ Aktien) | +0,012 | **+0,018** | **+0,023** | **+3,9** | **87 %** | −0,008 | +3,2 % | **stärkster Fund** |
| **mom_konsistenz** | +0,017 | +0,019 | +0,023 | +2,2 | 81 % | −0,054 (2016) | +2,4 % | robusteste Momentum-Form |
| mom_12_1_vola | +0,017 | +0,019 | +0,020 | +1,6 | 67 % | −0,080 (2009) | +3,7 % | Momentum-Crash 2009 |
| mom_12_1 | +0,017 | +0,017 | +0,016 | +1,3 | 67 % | −0,108 (2009) | +1,4 % | dito, schwächer |
| reversal_5d | **+0,020** | +0,011 | +0,006 | +1,1 (h=5: **+3,8**) | 94 % (h=5) | −0,001 | +13,7 % (h=5, brutto) | echt, nur kurz, hoher Umschlag |
| rsi2_invers | +0,012 | +0,006 | +0,002 | +0,8 (h=5: +3,0) | 88 % (h=5) | −0,002 | +9,9 % (h=5, brutto) | wie reversal_5d |
| vol_z_1d (Volumenschock 1 Tag) | +0,005 | +0,003 | +0,003 | +0,8 (h=5: +2,6) | 81 % (h=5) | −0,015 | +2,8 % (h=5) | klein, positiv |
| naehe_52w_hoch | +0,012 | +0,014 | +0,023 | +1,0 | 69 % | **−0,111 (2009)** | −1,8 % | Crash-anfällig |
| vola_niedrig / atr_niedrig | +0,015 | +0,011 | +0,016 | +0,7 | 69 % | −0,067 | −3,5 % (Quintil!) | IC positiv, Quintilspanne negativ → nur Sizing |
| **vol_schub_1w** (High-Volume-Premium GKM) | +0,003 | +0,002 | +0,002 | +0,5 | 56 % | −0,016 | +0,9 % | **praktisch tot** in liquiden Werten |
| turnover_trend (20d vs 120d) | −0,004 | −0,005 | −0,008 | −1,1 | 50 % | −0,039 | −0,5 % | eher negativ |
| **ear_proxy** (Sprung mit Volumen, 5 Tage) | **−0,010** | −0,010 | −0,008 | −1,2 (h=5: **−2,3**) | 31 % | −0,044 | −2,5 % | **Sprünge kehren um** — kein PEAD ohne echte Termine |
| **gap_volumen** (Gap-up mit Volumen) | **−0,013** | −0,010 | −0,009 | −1,3 (h=5: **−3,4**) | **6 %** | −0,036 | −2,8 % | **Gaps nicht jagen** |
| **amihud** (Illiquidität) | −0,014 | −0,016 | −0,022 | −2,3 (h=5: **−4,0**) | 38 % | −0,055 | ≈ 0 | illiquide Werte meiden |

Sieben Lehren daraus, alle direkt handlungsrelevant:

1. **Volumen zählt — aber andersherum als erwartet.** Nicht die „lauten“
   Aktien der letzten Woche laufen (GKM-Premium: IC +0,002, tot), sondern die
   **ruhigen** über sechs Monate (IC +0,018–0,023, 87 % positive Jahre,
   schlechtestes Jahr −0,008). Das ist der stabilste Faktor im ganzen Zoo,
   er ist billig zu handeln (H = 42 sinnvoll) und wenig mit Momentum
   korreliert. → **HYP-17**, Bestätigung out-of-sample auf 2016–2026 Pflicht.
2. **Momentum ja, aber als Konsistenz.** Der Anteil positiver Monate im
   letzten Jahr (mom_konsistenz) hat 81 % positive Jahre und ein
   schlechtestes Jahr von −0,054; rohes 12-1-Momentum hat 2009 −0,108. Die
   Konsistenz-Form dämpft den Momentum-Crash.
3. **Kurzfrist-Umkehr ist echt und trotzdem tot.** Auf 5 Tagen die
   höchsten t-Werte (3,8), Quintilspanne +13,7 % p.a. brutto — long-only die
   Hälfte, also ~0,14 % je 5-Tage-Trade: **exakt die +0,11 % je Trade, die
   das Projekt im Sommer gemessen hat, gegen 0,14 % Kosten.** Auf 21 Tagen
   ist der IC schon halbiert. Der Effekt lässt sich nicht „länger halten“.
4. **Sprünge kehren um.** Der naive PEAD-Ersatz (großer Tagesreturn mit
   Volumen) hat negativen IC. PEAD lebt nur *am Ergebnistermin*; ohne
   8-K-Daten ist HYP-03 nicht prüfbar und wird nicht behauptet.
5. **Gap-ups mit Volumen sind ein Verkaufs-, kein Kaufsignal** (6 %
   positive Jahre). Für einen Bot heißt das: nie am Tag nach einer
   Nachrichtenexplosion einsteigen — genau die „News nach dem Sprung“-Falle.
6. **Illiquidität kostet doppelt**: negativer IC und weiter Spread.
   Universum eher 800 als 2.000 Werte.
7. **Low-Vol als Auswahl ist ein Trugschluss**: positiver IC, aber negative
   Quintilspanne (das oberste Quintil ist zu langweilig, um SPY zu
   schlagen). Nur als Positionsgröße (1/Vola) nutzen.

### 6.6 Breites Universum (qlib, 2006–2020): Rangportfolios — der wichtigste Befund

Top 20 aus ~2.500–3.500 zugelassenen Aktien, H=21, Einstieg Eröffnung T+1:

| Variante | Regime | CAGR @20 bps | SPY | Sharpe | MaxDD | Jahre < SPY |
|---|---|---|---|---|---|---|
| kombi (mom+konsistenz+vol_1w+lowvol) | kein | **+0,3 %** | 9,4 % | 0,14 | −54 % | 12 von 15 |
| kombi | SPY > SMA200 | +1,1 % | 9,4 % | 0,16 | −42 % | |
| momentum (12-1 + Konsistenz) | kein | **−1,5 %** | 9,4 % | 0,11 | **−69 %** | 10 von 15 |
| momentum | SPY > SMA200 | +2,1 % | 9,4 % | 0,21 | −39 % | |
| kombi ohne Volumen | SPY > SMA200 | +2,9 % | 9,4 % | 0,24 | −42 % | |
| volumen (1-Wochen-Premium) | kein | +1,0 % | 9,4 % | 0,16 | −54 % | 11 von 15 |

**Positive ICs, verlorene Portfolios.** Das ist kein Widerspruch, sondern
die Lehre, die das ganze Projekt seit dem Frühjahr wiederholt: Ein IC von
0,02 über 3.000 Namen sagt, dass das *oberste Fünftel* (600 Aktien) das
unterste schlägt. Er sagt nichts über die **obersten 20** — das ist die
extreme Spitze der Rangliste, und dort sitzen bei einem Universum ab 1 Mio. $
Tagesumsatz systematisch: die kleinsten, volatilsten (25–32 % Vola gegen
19 % SPY), am weitesten gefallenen oder gestiegenen Namen. Gleichgewichtet
Top 20 aus Nebenwerten hat 2014–2020 gegen kapitalgewichtete Großwerte
strukturell verloren — unabhängig vom Signal. **Genau das ist der
Umkehr-Bot: Top 15 aus 1.200 Werten, Score-Spitze = Ausreißer.**

Drei Konsequenzen, die ab hier gelten:

1. **Universum: Top 500–800 nach Dollar-Umsatz**, nicht 1.200–3.000. Der
   Spread ist dort tragbar und die Rangspitze ist keine Lotterie.
2. **Breite statt Spitze: Top 50 statt Top 20.** Das Fundamentalgesetz
   (IR = IC × √BR) verlangt Breite; ein 20er-Portfolio wirft sie weg.
3. **Zwei Maßstäbe, immer beide:** SPY (was der Anleger sonst hätte) UND das
   gleichgewichtete Universum (ob die Auswahl überhaupt sortiert). Ab jetzt
   in jeder `22_`-Ausgabe als Spalte `Univ.EW`.

Die Läufe mit diesen Korrekturen (Universum ≥ 25 Mio. $/Tag, Top 50, Varianten
`kombi2`, `kurz`, `kurz10`, `momentum`) folgen in §6.7.

Bereits sichtbar in den Jahrestabellen: Der Trendfilter halbiert den
Drawdown (−69 % → −39 % bei Momentum) und kostet in Erholungsjahren
(2009: 0 % gegen +26 % SPY). Das ist der Preis des Filters, und er ist es
wert — 2008 hätte er den Momentum-Drawdown von −61 % auf −38 % begrenzt.

### 6.7 Korrigierte Läufe: liquides Universum (≥ 25 Mio. $/Tag), Top 50, kurze Horizonte

Universum je Tag: ~700–1.100 Aktien (2006–2020). Drei Maßstäbe: SPY (kapital-
gewichtet), **Univ.EW** (gleichgewichtetes Universum ohne Kosten) und die
Jahrestabelle.

**Spur „kurz“, H = 5 Tage** (Umkehr + RSI2 + Momentum-Konsistenz + ruhiges
Volumen + Volumenschock), Top 50:

| Regime | Kosten | CAGR | SPY | Univ.EW | Sharpe | MaxDD | Umschlag/J | Kosten/J |
|---|---|---|---|---|---|---|---|---|
| kein | 10 bps | **7,7 %** | 9,2 % | 8,7 % | 0,42 | −52 % | **100×** | 5,0 % |
| kein | 20 bps | 2,4 % | 9,2 % | 8,7 % | 0,22 | −63 % | 100× | 10,0 % |
| kein | 40 bps | −7,3 % | 9,2 % | 8,7 % | −0,17 | −85 % | 100× | 20,0 % |
| SPY > SMA200 | 10 bps | 1,0 % | 9,2 % | 8,7 % | 0,14 | −34 % | 75× | 3,7 % |
| SPY > SMA200 | 20 bps | −2,7 % | 9,2 % | 8,7 % | −0,13 | −49 % | 75× | 7,5 % |

Lesart: **Brutto** (7,7 % + 5,0 % Kosten ≈ 12,7 %) liegt die kurze Spur rund
**4 Prozentpunkte über dem Universum** — der Mehrfaktor-Score sortiert auf
5 Tagen also wirklich. Aber 100 Rundläufe im Jahr kosten selbst bei
optimistischen 10 bps mehr als den ganzen Vorsprung. **Das ist die Antwort auf
„kürzere Zeiträume“: Der Vorsprung existiert, die Kosten fressen ihn — bei
5 Tagen Haltedauer genauso wie beim heutigen Umkehr-Bot.** Auffällig: Der
Trendfilter schadet hier (Umkehr verdient in unruhigen Märkten), im
Gegensatz zu Momentum.

**Spur „kurz10“, H = 10 Tage**, gleicher Score, Top 50:

| Regime | Kosten | CAGR | SPY | Univ.EW | Sharpe | MaxDD | Umschlag/J | Kosten/J |
|---|---|---|---|---|---|---|---|---|
| kein | 10 bps | 7,3 % | 9,3 % | 8,7 % | 0,41 | −51 % | 50× | 2,5 % |
| kein | 20 bps | **4,6 %** | 9,3 % | 8,7 % | 0,31 | −53 % | 50× | 5,0 % |
| kein | 40 bps | −0,5 % | 9,3 % | 8,7 % | 0,11 | −58 % | 50× | 10,0 % |
| SPY > SMA200 | 10 bps | 4,0 % | 9,3 % | 8,7 % | 0,35 | **−30 %** | 37× | 1,9 % |
| SPY > SMA200 | 20 bps | 2,0 % | 9,3 % | 8,7 % | 0,21 | −32 % | 37× | 3,8 % |

Brutto (7,3 % + 2,5 %) ≈ 9,8 %: mit 10 Tagen ist der Bruttovorsprung über
dem Universum auf ~1 Prozentpunkt geschrumpft, dafür halbieren sich die
Kosten. **Weder 5 noch 10 Tage schlagen SPY netto** in diesem Universum und
Zeitraum. Die Faktoren sortieren (IC positiv, brutto über dem Universum),
aber die Rangspitze eines Umkehr-lastigen Scores ist teuer zu handeln.

**Spur „mittel“ = kombi2** (Momentum-Konsistenz + ruhiges Volumen + vola-
skaliertes Momentum), H = 21, Top 50, liquides Universum:

| Regime | Kosten | CAGR | SPY | Univ.EW | Sharpe | MaxDD | 2008 | Umschlag/J |
|---|---|---|---|---|---|---|---|---|
| kein | 20 bps | 5,1 % | 9,4 % | 8,7 % | 0,35 | −53 % | | 24× |
| **SPY > SMA200** | 20 bps | **5,9 %** | 9,4 % | 8,7 % | **0,48** | **−24 %** | **−4,5 % (SPY −36,8 %)** | 18× |
| beides | 20 bps | 3,8 % | 9,4 % | 8,7 % | 0,36 | −21 % | | 16× |

**Das ehrliche Fazit aus 2006–2020 auf ~1.000 liquiden Aktien:** Keine
Faktor-Auswahl schlägt SPY in der CAGR — weder kurz noch mittel. Die
Auswahl liegt sogar unter dem gleichgewichteten Universum. Was robust
gewinnt, ist der **Trendfilter**: Drawdown von −53 % auf −24 %, 2008 fast
ohne Verlust, bei ähnlicher CAGR. Auf dem S&P-Panel 2016–2026 sehen
dieselben Faktoren glänzend aus (§6.3) — der Unterschied ist zu einem
großen Teil der Index-Aufnahme-Bias und die Themen-Rally 2023–2024.

Die Wahrheit für *unsere* Zeit (2018–2026) liegt dazwischen und steht in
deinem Projektcache. Deshalb ist §8 Schritt 0 nicht verhandelbar: Erst wenn
`22_` auf dem Cache mit Univ.EW-Spalte gelaufen ist, wissen wir, ob die
Auswahl Alpha hat oder nur Beta.

**Alle Varianten im liquiden Universum, Top 50, 20 bps, 2006–2020** (SPY 9,3 %
CAGR / −55 % MaxDD; Univ.EW 8,7 %):

| Variante | H | Regime | CAGR | Sharpe | MaxDD | Umschlag/J |
|---|---|---|---|---|---|---|
| reversal_rein (wie der heutige Bot) | 5 | kein | 1,3 % | 0,19 | **−75 %** | 100× |
| reversal_rein | 5 | SMA200 | −5,9 % | −0,32 | −70 % | 75× |
| kurz (Mehrfaktor) | 5 | kein | 2,4 % | 0,22 | −63 % | 100× |
| kurz10 | 10 | kein | 4,6 % | 0,31 | −53 % | 50× |
| kurz (Haltedauer-Kurve) | 21 | kein | 6,7 % | 0,39 | | 24× |
| kurz (Haltedauer-Kurve) | 42 | kein | 7,0 % | 0,40 | | 12× |
| momentum (12-1 + Konsistenz) | 21 | kein | 4,8 % | 0,31 | −58 % | 24× |
| **momentum** | 21 | **SMA200** | **7,4 %** | **0,45** | **−37 %** | 18× |
| kombi2 | 21 | kein | 5,1 % | 0,35 | −53 % | 24× |
| **kombi2** | 21 | **SMA200** | 5,9 % | **0,48** | **−24 %** | 18× |
| kombi2, Top 20 | 21 | SMA200 | 5,5 % | 0,44 | −25 % | 18× |
| **kombi2, H=42** | 42 | **SMA200** | **6,1 %** | **0,47** | **−29 %** | **9×** |
| kombi2 + Vola-Ziel 15 % | 21 | SMA200 | 5,2 % | 0,49 | **−18 %** | 18× |
| ruhig (nur Volumenfaktor) | 42 | SMA200 | 3,4 % | 0,30 | −39 % | 9× |
| ear (Sprung-Proxy) | 42 | kein | 7,2 % | 0,43 | −57 % | 12× |
| ear | 42 | SMA200 | 4,2 % | 0,39 | −31 % | 9× |

Drei Ergänzungen daraus: **42 Tage Haltedauer** halbiert den Umschlag
gegenüber 21 Tagen bei gleicher oder besserer CAGR (6,1 % gegen 5,9 %);
das **Vola-Ziel** drückt den Drawdown auf −18 % (SPY −55 %) bei gleicher
CAGR — die zwei Hebel, die die Kompendium-Rangliste als „garantiert“
führt (Kosten senken, Größe nach Volatilität), wirken auch hier zuerst;
und der Volumenfaktor allein reicht nicht (3,4 %), erst die Kombination
mit Momentum-Konsistenz trägt.

Die Haltedauer-Kurve der kurzen Spur ist eindeutig: **Netto-CAGR steigt
monoton mit der Haltedauer** (2 Tage −13,6 %, 5 Tage 2,4 %, 10 Tage 4,6 %,
21 Tage 6,7 %, 42 Tage 7,0 %). Der Umschlag frisst den Vorsprung — dasselbe
Bild wie beim Umkehr-Bot, nur mit Zahlen für jede Stufe.

**Dieselben Varianten auf dem S&P-Panel 2016–2026** (Obergrenze, SPY 14,8 %,
Univ.EW 16,1 %): momentum Top 50 ohne Regime **22,3 %** (Sharpe 0,96, MaxDD
−41 %), mit SMA200 14,5 % (Sharpe 0,83, MaxDD −29 %); kurz_preis Top 50
H=5 13,5 %, H=10 16,9 %, **H=21 20,7 %, H=42 21,1 %** (Sharpe 1,06). Auch
hier: **länger halten gewinnt**, auf beiden Datensätzen, in jedem Jahr-
zehnt, bei jeder Kostenstufe.

**Was daraus die Strategie „ranking“ macht (§7, implementiert in
`signals.build_ranking_frame` und `EngineConfig.for_ranking`):**
Haltedauer 21–63 Tage (Mindesthaltedauer 21, Rangverlust-Ausstieg,
Zeitausstieg 63), Top 50 aus dem liquiden Universum, Regime-Tor SMA200,
Score aus Momentum-Konsistenz + ruhigem Volumen + vola-skaliertem
Momentum. Ehrliche Erwartung aus den beiden Datensätzen: **zwischen „SPY
minus 2 Punkte bei halbem Drawdown“ (2006–2020, breit) und „SPY plus 5–7
Punkte“ (2016–2026, S&P, mit Bias)** — die Wahrheit für 2018–2026 auf
deinem Cache steht noch aus (bot-start-2027.md, Stufe 1).

### 6.8 Dynamische Haltedauer (Skript 29) — Mechanik geprüft, Zahlen folgen

`scripts/29_labor_dynamisch.py` sagt je Aktie Renditen über 5/10/21/42/63
Tage voraus (ein LightGBM je Horizont, walk-forward jährlich, Embargo) und
lässt das System selbst wählen: Kauf nach höchster **erwarteter Netto-
Rendite je Tag** `(E[r_h] − Kosten)/h`, Halten, solange die beste
verbleibende Erwartung über den Ausstiegskosten liegt, Wechsel, wenn ein
Kandidat je Tag mehr verspricht als die schwächste Position plus
Wechselkosten. Verglichen wird gegen dieselben Vorhersagen mit festem
Horizont.

Selbsttest (synthetische Aktien mit eingebauten schnellen und langsamen
Bewegungen, nahezu perfekte Prognose): Die Dynamik wählt zu 88 % den
5-Tage-Horizont für schnelle Bewegungen und schlägt die feste 21-Tage-Fassung
— geprüft wird nur die Mechanik.

**Echter Lauf, S&P-Panel 2019–2026 (Training ab 2016), Top 30, 20 bps,
Einzelaktien:**

| Horizont | OOS-IC | t (roh) | t (deflationiert) |
|---|---|---|---|
| 5 | +0,010 | 3,6 | 1,6 |
| 10 | +0,013 | 4,7 | 1,5 |
| 21 | +0,016 | 5,5 | 1,2 |
| 42 | +0,017 | 6,1 | 0,9 |
| 63 | **+0,031** | 10,0 | 1,3 |

| Fassung | CAGR | SPY | Sharpe | MaxDD | Trades | Haltedauer Median | Treffer |
|---|---|---|---|---|---|---|---|
| **dynamisch** | 26,9 % | 15,2 % | 0,99 | −44 % | 1.990 | 15 Tage | 56 % |
| fest 5 | 9,4 % | 15,2 % | 0,76 | −21 % | 4.654 | 6 | 51 % |
| fest 10 | 21,9 % | 15,2 % | 0,98 | −35 % | 5.577 | 11 | 53 % |
| **fest 21** | **29,2 %** | 15,2 % | **1,12** | −45 % | 2.820 | 22 | 56 % |
| fest 42 | 25,7 % | 15,2 % | 0,97 | −48 % | 1.481 | 43 | 57 % |
| fest 63 | 26,7 % | 15,2 % | 0,99 | −47 % | 988 | 64 | 59 % |

Horizontwahl der Dynamik: 56 % h=5, 19 % h=10, 12 % h=21, 13 % länger.
Jahre: 2020 +72 %, 2021 +55 %, **2022 −22 % (SPY −18 %)**, 2023 +48 %,
2024 +35 %, 2025 +41 %.

**Zweite Fassung, IC-gewichtet** (`rate_h = IC_h · E[r_h] / h`): CAGR 27,3 %,
Sharpe 1,00, Horizontwahl kippt auf 75 % h=63. Sie liegt gleichauf mit der
rohen Dynamik und weiter unter der festen 21-Tage-Fassung (29,2 %, 1,12).
**Befund:** Auf diesen Daten bringt die dynamische Horizontwahl nichts
gegenüber „21 Tage halten, Rang prüfen“ — und das ist genau das, was die
Engine-Strategie tut (Mindesthaltedauer 21, Rangverlust-Ausstieg, Zeit 63).
Der Ausstieg ist damit bereits „dynamisch nach Prognose“: nicht die Uhr,
sondern der tägliche Rang entscheidet, ob eine Position bleibt. Was fehlt
und offen bleibt, ist der *Einstieg* nach horizontabhängiger Erwartung;
HYP-19 bleibt Kandidat, nicht Kern.

Drei Lehren:

1. **Das Mehr-Horizont-Modell sortiert out-of-sample auf jedem Horizont**
   (alle ICs positiv, roh hoch signifikant), am stärksten auf 63 Tagen. Das
   ist die Grundlage für „die Prognose entscheidet“ — sie existiert.
2. **Die erste Dynamik-Regel wählt zu oft kurz.** `rate = E[r_h]/h` bevorzugt
   den 5-Tage-Horizont, obwohl dessen Prognose die *unsicherste* ist
   (IC 0,010 gegen 0,031). Ergebnis: mehr Umschlag, Sharpe 0,99 statt 1,12
   der festen 21-Tage-Fassung. Die Korrektur ist klar und steht als
   nächster Schritt in HYP-19: **jede Horizont-Prognose mit ihrer eigenen
   Verlässlichkeit gewichten** (`rate_h = IC_h · E[r_h] / h`, IC aus dem
   Trainingsfenster) und kurze Horizonte nur wählen, wenn sie *deutlich*
   mehr je Tag versprechen als der Kostenaufschlag.
3. **Alle Zahlen hier sind Obergrenzen** (heutige S&P-Mitglieder, Bullenjahre
   2019–2026 mit SPY 15 % p.a.). Die 2022-Zeile zeigt, was ein Bärenjahr
   ohne Regime-Tor kostet.

**Auf deinem Mac ist das Schritt 0.5** (§8): `29_` auf dem Projektcache mit
liquidem Universum, Bestehensgrenze wie in HYP-19 (dynamisch ≥ beste feste
Fassung auf denselben Vorhersagen, OOS-IC je Horizont > 0,01).

**Nachtrag qlib (2026-09-29, liquides Universum, Top 30, 20 bps, ohne
Regime; Walk-forward ab 2009, die CAGR-Spalte enthält deshalb drei
Nulljahre 2006–2008 — umgerechnet auf 2009–2020 in Klammern):**

| Fassung | CAGR 2006–2020 (2009–2020) | Sharpe | MaxDD | Trades | Ø Halt |
|---|---|---|---|---|---|
| **dyn_ic** (IC-gewichtete Horizontwahl) | **17,5 % (22,3 %)** | 0,66 | −50 % | 3.531 | 25 T |
| dyn_roh | 16,6 % (21,2 %) | 0,62 | −54 % | 3.753 | 24 T |
| fest_h5 | 13,5 % (17,2 %) | 0,64 | −38 % | 6.256 | 5 T |
| fest_h10 | 13,6 % (17,3 %) | 0,58 | −45 % | 8.735 | 9 T |
| fest_h21 | 11,8 % (15,0 %) | 0,53 | −53 % | 5.897 | 15 T |
| fest_h42 | 8,3 % (10,5 %) | 0,43 | −50 % | 3.728 | 23 T |
| fest_h63 | 11,4 % (14,4 %) | 0,55 | −48 % | 3.271 | 26 T |
| SPY | 9,3 % (14,3 %) | | −55 % (−34 %) | | |

Zwei Dinge sind hier neu. Erstens: **Jede Fassung mit LightGBM-Prognose
liegt über SPY** — auch die festen Horizonte, auch mit drei Nulljahren.
Das ist, zusammen mit §6.10 (Skript 23, eigenes Training, Top 50: 15,7 %
gegen 14,3 %), der zweite unabhängige Lauf, in dem die ML-Prognose den
Handmix um 5 und mehr Punkte schlägt. Zweitens: Auf dem breiten Universum
**schlägt die dynamische Horizontwahl jeden festen Horizont um 4–6
Punkte** (auf dem S&P-Panel dagegen −2 gegen fest_h21). Die Wahl ist
dort ein echter Mix (21 Tage 36 %, 5 Tage 20 %, 42 und 63 je 19 %), auf
S&P eine Einheitswahl (63 Tage 75 %). HYP-19 ist damit **kandidat**: ein
Panel dafür, eins dagegen, Drawdown ohne Regime-Tor untragbar (−50 %).

Die eigentliche Nachricht ist nicht die Dynamik. Sie ist: **die Prognose
ist die Stellschraube.** Alles, was in diesem Labor bisher über SPY und
Universum lag, hatte eine LightGBM-Vorhersage im Score. Konsequenz in §7.2.

### 6.9 Der Replay-Test: die Strategie durch die ECHTE Engine

Die Strategie „ranking“ ist in `signals.build_ranking_frame` und
`EngineConfig.for_ranking` gebaut (§7) und wurde mit `scripts/31_` durch
`simulate.run` geschickt — Tag für Tag, mit Positionsgrößen, Stops,
Mindesthaltedauer, Kurslücken und allen Kosten aus `costs.py`
(5 bps Spread + 5 bps Slippage je Seite + SEC/FINRA). 600 liquideste
Symbole, 50 Plätze, Regime-Tor an.

| Panel | Zeitraum | Engine CAGR | Sharpe | MaxDD | SPY | Trades | Ø Halt | Ausstiege |
|---|---|---|---|---|---|---|---|---|
| qlib (mit Volumen) | 2010–2020 | **5,2 %** | 0,46 | −30 % | 14,2 % / −34 % | 1.551 | 31 Tage | **42 % Stop**, 37 % Rangverlust, 21 % Zeit |
| S&P (ohne Volumen) | 2016–2026 | **6,7 %** | 0,57 | **−18 %** | 14,7 % / −34 % | 3.742 | 28 Tage | **60 % Stop**, 21 % Zeit, 19 % Rangverlust |

Zum Vergleich derselbe Score vektorisiert (`22_ --variante ranking_preis`,
S&P 2015–2026, Top 50, 20 bps): **12,9 %** mit Regime, 18,0 % ohne. Die
Engine liegt also **6 Punkte unter der vektorisierten Messung** — und der
Replay-Test hat damit genau das getan, wofür er da ist: eine Lücke
gefunden. Sie liegt nicht im Signal (Trefferquote 35–45 % bei Ø Gewinn
+10–13 % gegen Ø Verlust −5 bis −6,5 %, Erwartungswert **+1,1–1,3 % je
Trade netto** — das ist ein gesundes, rechtsschiefes Profil), sondern in
der **Ausstiegsregel**: Der 3-ATR-Stop löst 42–60 % aller Ausstiege aus.
Bei einem Momentum-Wert mit 2,5 % ATR sind 3 ATR ein Rückschlag von 7,5 % —
den macht fast jeder Gewinner irgendwann in 63 Tagen, und der Stop
verkauft ihn genau dann. Das Kompendium (§3.2) sagt es seit dem Sommer:
Zeit- und Regelausstiege schlagen bei Momentum den festen Stop.

**Ergebnis der Simulationen ohne Stop (2026-09-29):** HYP-20 ist in der
Hauptaussage **widerlegt**. Der Stop kostet keine CAGR — er halbiert den
Drawdown:

| Panel | Stop 3 ATR | ohne Stop (99 ATR) | Referenz 22_ (gleicher Score) |
|---|---|---|---|
| S&P 2016–2026 | 6,7 % / MaxDD −18 % | 7,5 % / **−31 %** | 12,9 % / −31 % |
| qlib 2009–2020 | 5,2 % / −30 % | 4,7 % / **−45 %** | 6,1 % (2009–2020: 6,7 %) / −29 % |

Die Lücke zur vektorisierten Referenz bleibt also **mit und ohne Stop**
bestehen. Die Trade-Autopsie (`scripts/33_`) zeigte als nächsten
Verdächtigen den Rangverlust-Ausstieg (57 % der Ausstiege, Ø −2,3 %,
Trefferquote 39 %; Zeitausstiege Ø +8,7 %, 73 %). Daraus wurde
**HYP-2027-21**, registriert vor dem Test — und auch sie ist in der
Hauptaussage widerlegt:

| Engine-Fassung (S&P, ohne Stop) | CAGR | Sharpe | MaxDD |
|---|---|---|---|
| Basis: 21–63 Tage, Rangverlust < 50. Perzentil | 7,5 % | 0,56 | −31,0 % |
| reiner Zeitausstieg 42 Tage (wie die Referenz) | 6,5 % | 0,53 | −22,6 % |
| 21–63 Tage, Rangverlust erst < 20. Perzentil | **8,5 %** | **0,68** | **−20,5 %** |
| Referenz 22_ `ranking_preis`, trend_ok, 20 bps | 12,9 % | 0,85 | −30,8 % |

Der Rangverlust ist nicht die Lücke (der reine Zeitausstieg ist sogar
schlechter), aber die weichere Schwelle 0,20 ist eine echte
Teilverbesserung: +1 Punkt CAGR bei einem Drittel weniger Drawdown
(Kandidat für `for_ranking(exit_rank_pct=0.2)`, qlib-Gegenlauf läuft).

Was die Lücke NICHT ist (jeweils gemessen): das Signal (Engine- und
Labor-Score haben Rangkorrelation 0,998), der Investitionsgrad (Engine
77–86 % zu Einstandskursen, Referenz 74 %), die Kosten (Engine 0,6 % p.a.,
Referenz 1,8 %), der Tagesdeckel (der Simulator hat keinen). Was bleibt —
und jetzt einzeln gemessen wird: **1/Vola-Sizing** (die Referenz ist
gleichgewichtet; Momentum in ruhigen Aktien trägt weniger), die
**5-Tage-Wiedereinstiegssperre** (beim Zeitausstieg laufen die Sieger aus
und dürfen fünf Tage nicht zurück — ihre Plätze bekommen die Ränge 51–100)
und die **Klumpung der Kohorten** (die Referenz hat 42 gestaffelte
Kohorten, die Engine wenige große; die Jahreswerte der drei Engine-Fassungen
streuen deshalb um bis zu 20 Punkte — 2024: 18 % gegen 38 %). Die vier
isolierenden Läufe (`--cooldown 0`, `--sizing gleich`, beides, qlib
exit 0,2) sind gestartet; Ergebnis in der Tabelle unten, sobald da.

| Isolierender Lauf (S&P, 42 Tage fest, ohne Stop) | CAGR | MaxDD | Deutung |
|---|---|---|---|
| Basis (Sperre 5, 1/Vola) | 6,5 % | −22,6 % | |
| Sperre 0 Tage | 6,5 % | −22,6 % | **exakt gleich** — die Sperre wirkt nie, siehe unten |
| Gleichgewicht statt 1/Vola | 7,3 % | −22,7 % | +0,8 Punkte: Sizing ist ein kleiner Hebel |
| beides | 7,3 % | −22,7 % | wie Gleichgewicht allein |
| qlib 21–63, Rangverlust < 0,20 (2009–2020) | 6,4 % | −39,9 % | +1,7 gegen Basis 4,7 %, Drawdown leicht besser als −45 % |

**Der Täter ist gefunden — und es war keiner der Verdächtigen.** Der
Abgleich der Engine-Bestände mit der Top-50-Liste der Referenz am
jeweiligen Kauftag ergibt nur **33–46 von 50 gemeinsamen Namen**. Grund:
Beim Zeitausstieg verkauft die Engine alle Positionen einer Kohorte und
füllt die Plätze *am selben Tag* — eine gerade verkaufte Aktie ist an
diesem Tag ausgeschlossen (deshalb ändert die Sperre 0 nichts), ihr Platz
geht an Rang 51–100. Genau die Aktien, die nach 42 oder 63 Tagen **noch
immer** im Top-Dezil stehen, sind die Dauer-Sieger — und aus ihnen kommen
40–90 % des Gewinns (§6.9 Autopsie, Konzentration). Die vektorisierte
Referenz hält solche Namen über ihre 42 gestaffelten Kohorten
durchgehend; die Engine wirft sie systematisch raus. Weder Sizing noch
Sperre noch Rangverlust: **der Zeitausstieg selbst** ist die Lücke.

Konsequenz: **Verlängerung statt Zeitausstieg** — nach `max_hold_days`
wird nur verkauft, wenn die Aktie *nicht mehr* im Kaufbereich steht
(`renew_rank_pct`, Standardvorschlag 0,90 = das Top-Dezil). Das ist das
„dynamisch je Aktie“, das der Nutzer wollte, ohne Prognosehorizonte: Der
Rang entscheidet, wie lange gehalten wird. Sim und Live rechnen es gleich
(keine Zählerpflege nötig — nach der Höchstfrist gilt „halten, solange im
Kaufbereich“). Replays mit Verlängerung laufen; Ergebnis hier.

| Verlängerung (S&P, 21–63 Tage, Rangverlust < 0,20) | CAGR | MaxDD | Zeitausstiege |
|---|---|---|---|
| Basis ohne Verlängerung (ohne Stop) | 8,5 % | −20,5 % | 1.269 |
| ohne Stop, verlängern ab Perzentil 0,90 | 6,6 % | −27,9 % | 1.196 |
| ohne Stop, verlängern ab 0,80 | 7,9 % | −31,4 % | 1.097 |
| Stop 3 ATR, verlängern ab 0,90 | 8,0 % | −19,1 % | 897 |

**Auch das war es nicht.** Die Verlängerung greift selten (nur 6–14 %
weniger Zeitausstiege — nach 63 Tagen steht kaum eine Aktie noch im
Top-Dezil) und verschlechtert, wo sie greift. Die Sieger-Theorie aus dem
Bestandsabgleich war eine plausible Geschichte, kein Täter. Was der
Abgleich wirklich zeigte, kam erst mit dem letzten Experiment heraus:

**Der Täter ist die Kohorten-Lotterie.** Die vektorisierte Referenz
rechnet 42 überlappende Kohorten (jeden Tag ein Zweiundvierzigstel des
Kapitals neu) — die Standardkonstruktion der Momentum-Literatur seit
Jegadeesh/Titman 1993, gerade *weil* sie den Startzeitpunkt wegmittelt.
Die Engine mit Zeitausstieg bildet dagegen eine oder wenige Klumpen-
Kohorten (alle 50 Plätze werden am selben Tag frei und neu besetzt).
Dieselbe Strategie als **einzelne 42-Tage-Kohorte**, vektorisiert
gerechnet, je nach Startversatz:

| Startversatz (Tage) | 0 | 3 | 6 | 9 | 12 | 15 | 18 | 21 | 24 | 27 | 30 | 33 | 36 | 39 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| CAGR | 13,2 | 12,2 | 8,5 | 9,6 | 7,9 | 11,4 | 9,8 | 15,3 | 14,8 | 18,0 | 15,6 | 14,1 | 15,2 | 14,7 |
| MaxDD | −19 | −24 | −32 | −33 | −38 | −39 | −39 | −35 | −35 | −36 | −38 | −40 | −19 | −22 |

Mittel 12,9 % (= gestaffelte Referenz 12,7 %), **Spanne 7,9–18,0 %,
Streuung 2,9 Punkte**; MaxDD −19 % bis −40 %. Die Engine-Läufe (6,5 / 7,3 /
7,5 / 8,5 %) sind eine schlechte Ziehung aus dieser Verteilung, keine
schlechtere Strategie — und die Jahreswerte, die zwischen den
Engine-Fassungen um 20 Punkte streuten (2024: 18 % gegen 38 %), sind
dasselbe Phänomen. Lehre: **Ein einzelner Engine-Replay hat ±3 Punkte
CAGR und ±10 Punkte MaxDD Ziehungsrauschen.** Wer die Engine gegen die
Referenz misst, muss die Staffelung mitbauen oder über Startversätze
mitteln.

Heilung, als Engine-Regel gebaut (`max_new_per_day`, Simulation und Live
identisch): höchstens 3–5 neue Positionen je Tag — dann staffelt sich die
Engine ihre Kohorten selbst (50 Plätze / 3 je Tag ≈ 17 Kohorten). Preis:
Nach einer Regime-Sperre dauert die Wiederbefüllung 10–17 Handelstage
(die Referenz braucht 42). Replays mit Deckel 3 und 5 laufen:

| Tagesdeckel (S&P, 21–63 Tage, Rangverlust < 0,20) | CAGR | MaxDD | Deutung |
|---|---|---|---|
| Stop 3 ATR, Deckel 3 | _läuft_ | | Kandidat Live-Standard |
| Stop 3 ATR, Deckel 5 | _läuft_ | | |
| ohne Stop, Deckel 3 | _läuft_ | | Vergleich zur Referenz 12,9 % |

Für die Engine-Voreinstellung heißt das heute: **Stop bleibt bei 3 ATR**
(Drawdown-Halbierer, CAGR-neutral), Rangverlust-Schwelle 0,20 nach dem
qlib-Gegenlauf, Sizing und Sperre nach den isolierenden Läufen.

Zweiter Befund aus demselben Vergleich: Der Score-Kandidat **v2** (rohes
12-1-Momentum + Konsistenz + halbes ruhiges Volumen) bringt auf dem S&P-
Panel 16,2 % mit Regime (23,2 % ohne) gegen 12,9 % für die Fassung mit
vola-skaliertem Momentum — bei etwas höherem Drawdown (−35 % gegen −31 %).
Der Qlib-Gegenlauf (in der ML-Kette) entscheidet, welche Gewichte die
Engine bekommt; die Auswahl zählt im Versuchszähler (Schwelle 3,4 Sigma),
und die Bestätigung auf deinem Cache ist Pflicht.

### 6.10 ML-Ranker (LightGBM, walk-forward) — der erste Fund über SPY und Universum

`scripts/23_` auf qlib, liquides Universum, 19 Merkmale des Faktorzoos,
jährlicher Walk-forward mit Embargo (Training nur bis 39 Kalendertage vor
dem Testjahr), Ziel 21-Tage-Vorwärtsrendite, Top 50, 20 bps, **ohne**
Regime-Tor, 2009–2020:

| | CAGR | Sharpe | MaxDD | Jahre > SPY |
|---|---|---|---|---|
| **ML-Ranker h21** | **15,7 %** | 0,70 | −40,6 % | 7/12 |
| SPY | 14,3 % | | −33,7 % | |
| Univ.EW (liquides Universum) | 13,2 % | | | |
| Handmix `ranking` (kein Regime), gleicher Zeitraum | 10,4 % | 0,37 | −54 % | 4/12 |
| Handmix `momentum` (kein Regime) | 9,2 % | | | 5/12 |

OOS-IC +0,030 (t deflationiert 1,4) — **genau so hoch wie der beste
Einzelfaktor** (mom_12_1_vola +0,030) auf denselben Tagen. Das Portfolio
ist trotzdem 5–6 Punkte besser als jeder Handmix: Die Stärke des Modells
sitzt im oberen Rand der Verteilung, nicht im mittleren Rang (dieselbe
Lehre wie §6.6, nur umgekehrt). Merkmalswichtigkeit: vol_schub_6m_neg >
vola_niedrig > mom_12_1_vola > mom_6m > abstand_52w_tief — das Modell hat
die Handmix-Bausteine selbst gefunden und ergänzt sie um Vola und
52-Wochen-Abstand.

Einordnung, ehrlich: erstes Panel, in-sample gewählte Merkmale, kein
Regime-Tor, MaxDD über SPY. Urteil im Register: **kandidat** (2 von 3
Kriterien). Die Bestätigungskette läuft: S&P-Panel (nur Kursmerkmale),
qlib mit Regime-Tor, Horizonte 10 und 42. Das Skript speichert jetzt die
OOS-Vorhersagen (`ml_pred_*.parquet`), damit Regime, Vola-Ziel und
Haltedauer ohne Neutraining geprüft werden können, und rechnet die
Handmixe auf **exakt demselben Universum** mit — sonst vergleicht man
Universumsfilter statt Modelle.

**Zweites Panel, S&P 2019–2026 (nur 11 Kursmerkmale, ohne Volumen):**
ML 24,6 % gegen Handmix `momentum` 24,8 % auf demselben Universum (SPY
16,6 %, Univ.EW 17,1 %), OOS-IC +0,021, MaxDD −43,5 % gegen −40,7 %.
**Kein Vorsprung.** Die Deutung, die beide Panels zusammen erlauben: Der
ML-Vorsprung auf qlib kommt aus dem, was dem S&P-Panel fehlt — den
Volumenmerkmalen (`vol_schub_6m_neg` ist die wichtigste Variable) und der
Breite (8.000 statt 600 Namen, 2009 statt 2019 als erstes Testjahr). Das
ist kein Beweis, aber es ist die einzige Erklärung, die beide Zahlen
verträgt. Damit ist der **Projektcache (2018–2026, 2.168 Symbole MIT
Volumen) das entscheidende dritte Panel** — Stufe 1 in
`docs/bot-start-2027.md` bekommt `23_ --panel projekt` als Pflichtlauf mit
Bestehensregel „ML ≥ Handmix + 2 Punkte auf demselben Universum“.

**qlib MIT Regime-Tor (trend_ok), gleiche Vorhersagen, gleiches
Universum:** ML 7,8 % gegen momentum 10,2 %, ranking_v2 8,5 %, ranking
6,1 % (SPY 14,5 %, Univ.EW 13,9 %). **Mit Tor verliert der ML-Ranker
2,4 Punkte gegen den besten Handmix — ohne Tor gewinnt er 5.** Der ganze
Vorsprung sitzt also in den Phasen, die das Tor sperrt: 2009 (+24 %
Jahresrendite ohne Tor), 2020 (+35 %). Der ML-Ranker ist, so gelesen,
kein besserer Momentum-Ranker, sondern ein **Erholungs-Ranker**: Seine
wichtigsten Merkmale (ruhiges Volumen, niedrige Vola, Abstand zum
52-Wochen-Tief) beschreiben „gefallene Qualität, die keiner beachtet“ —
das trägt nach Abstürzen, wenn Momentum leer ausgeht. Achtung, ungetestet:
2008 liegt VOR dem ersten Testjahr (Walk-forward braucht drei Jahre
Training); ob der Ranker ohne Tor einen echten Bärenmarkt übersteht, ist
**nicht gemessen** (MaxDD ohne Tor −40,6 %; 2018 −10 %, 2011 −7 %).

Was daraus zu prüfen ist (aus den gespeicherten Vorhersagen, ohne neues
Training, `35_`): (a) ML ohne Tor, aber mit Vola-Ziel 0,25 — Drawdown-
Schutz ohne Sperre; (b) Hybrid: Tor zu → ML-Auswahl mit Vola-Ziel, Tor
auf → Momentum-Handmix; (c) Hysterese-Tor. Bestehensregel für jede
Fassung: CAGR ≥ momentum+trend_ok + 2 Punkte UND MaxDD ≤ −30 %.

Wenn der ML-Ranker auf dem dritten Panel hält, wird er der Score der
Engine (Architektur §7: `build_ranking_frame` liefert die Merkmale, ein
gespeichertes LightGBM-Modell den Rang; Training jährlich, Modell im Repo
mit Datum). Wenn nicht, bleibt der Handmix.

### 6.11 Chartmuster und Explosionen (Skript 30)

Teil A, neun Muster × drei Horizonte auf qlib 2006–2020 (27 Zeilen im
Register): **kein Muster über der Zufallsschwelle.** Bestes t_defl +1,99
(Volumenkompression, 5 Tage) — ein Vola-Proxy, den `vola_niedrig` schon
trägt. Gap-ups mit Volumen (−3,9) und Donchian-Ausbrüche (−2,8) sind
**negativ**: Ausbrüche kehren um. Regel: keine Ausbruchskäufe.

Teil B, 1.162 Explosionen (≥ +50 % in 60 Tagen) gegen 5.000 Kontrollen:
Walk-forward-GBM **AUC 0,81** (Negativtest 0,50). Die Merkmale davor:
vol_10 (Cohens d 1,08), atr_pct (1,07), bb_width (0,94), Drawdown (−0,92),
RSI (−0,72). Explosionen kommen aus abgestürzten, volatilen Aktien — und
genau die haben laut Faktorzoo **negative** erwartete Rendite (hohe Vola =
Lotterie). Vorhersagbar ist nicht verdienbar: HYP-2027-23 registriert, mit
dem Test, ob das Top-Dezil der Explosionswahrscheinlichkeit netto mehr
verdient als das Universum (Erwartung: nein, Crash-Anteil 2–3× höher;
Nutzen allenfalls als Ausschlussfilter).

### 6.12 Vola-Ziel (HYP-2027-22) — Drawdown-Halbierer, wenn das Ziel stimmt

`22_ --vola-ziel` skaliert den Investitionsgrad mit Zielvola /
realisierter 20-Tage-Vola des Portfolios:

| Panel, Variante | ohne | 0,15 | 0,20 | 0,25 |
|---|---|---|---|---|
| qlib kombi2, kein Regime | 5,1 % / −52,9 % | 5,2 % / −30,7 % | | |
| qlib kombi2, trend_ok | 5,9 % / −23,8 % | 5,2 % / −18,3 % | | |
| S&P ranking_preis, kein Regime | 18,0 % / −36,4 % | 13,4 % / −17,4 % | 15,7 % / −20,2 % | 16,8 % / −22,9 % |
| S&P ranking_preis, trend_ok | 12,9 % / −30,8 % | 11,1 % / −15,7 % | 12,3 % / −18,7 % | **12,9 % / −20,8 %** |

Mit Ziel 0,25 besteht die Regel (MaxDD ≤ 0,7×, CAGR ≥ ohne − 1) auf dem
S&P-Panel; 0,15 ist zu eng für ein Bullenjahrzehnt. qlib mit 0,25 läuft.
Wenn beides hält, kommt das Vola-Ziel ins Risiko-Dach als dynamischer
`target_invested` — es ersetzt nicht das Regime-Tor, es ergänzt es (das Tor
reagiert auf Trend, das Ziel auf Vola, und Vola steigt vor dem Trendbruch).

### 6.13 Was das Register nach 190 Befunden sagt

`docs/befunde-2027.md` (automatisch): 72 unterschiedliche Varianten,
Zufallsschwelle 3,4 Sigma. **Bestanden** (CAGR ≥ SPY − 2, MaxDD ≤ 0,8 ×
SPY, ≥ Univ.EW): zwei Zeilen, beide `momentum` qlib trend_ok bei 10 bps.
**Kandidat**: ML-Ranker h21, Engine exit 0,2, mehrere Vola-Ziel-Zeilen.
Alles andere verworfen oder zu dünn — und das ist der Zustand, den ein
ehrliches Labor nach 72 Versuchen zeigen muss. Die Lehren daraus, als
Regeln: `docs/lehren-2027.md`.

### 6.14 Selbsttests

- `scripts/00_selftest.py`: 61/61 bestanden (Ranking-Strategie, Risiko-Dach, Befundregister).
- `scripts/09_selfcheck.py`: 9 Prüfungen, 0 Verstöße.
- `scripts/26_labor_orb_intraday.py --selftest`: 6/6 bestanden (Auslöser,
  Stop-Begrenzung, Short-Sperre, relatives Volumen, Top-N, Zufallsmarkt ≈ 0).
- `scripts/27_hypothesen_anmelden.py --anmelden --db <test>`: 16 Einträge.

---

## 7. Die Zielarchitektur 2027

```
                     ┌──────────────────────────────────────────┐
                     │  RISIKO-DACH (risiko.py, mehrbot-plan §5) │  Drawdown 20 % → Sperre
                     │  Tagesverlust 5 %, Brutto ≤ 1,0, Sektor ≤ 35 % │
                     └───────────────┬──────────────────────────┘
                                     │
        ┌────────────────────────────┼─────────────────────────────┐
        ▼                            ▼                             ▼
┌──────────────────────┐   ┌────────────────────────┐   ┌────────────────────┐
│ BUCH A  Einzelaktien │   │ BUCH B  ORB-Daytrading │   │ BUCH C  Overnight  │
│ Ranking, 2 Spuren:   │   │ auf Einzelaktien       │   │ Auktion (HYP-07)   │
│  kurz  H=5–10 Tage   │   │ (nur wenn HYP-04 hält) │   │ ≤ 10 %, QQQ/IWM    │
│  mittel H=21–42 Tage │   │ ≤ 20 % Kapital, 0 über │   │ MOC → MOO          │
│ Universum Top 500–800│   │ Nacht, Hebel ≤ 4 intra │   │ nur über SMA200    │
│ Top 50 (kurz: 30)    │   │ Top 20 Rel.-Volumen    │   │ Nebentest, kein    │
│ Regime, 1/Vola       │   └────────────────────────┘   │ Kernbaustein       │
└──────────────────────┘                                └────────────────────┘
        ▲ dieselbe Engine.decide(), neue Strategie "ranking" in signals.py
```

**Buch A ist der Kern — Einzelaktien, keine ETFs.** SPY und VIX kommen nur
als Regime-Tor vor. Die Strategie `ranking` ersetzt die Umkehr in
`EngineConfig`, in zwei Spuren, die als getrennte Schattenbots laufen und
von denen die bessere (netto, gepaart, ≥ 60 Tage) das Kapital bekommt:

- **Spur „kurz“ (5–10 Tage)** — der Wunsch nach kurzen Zeiträumen, ehrlich
  gebaut: Score = 5-Tage-Umkehr (Timing) + Momentum-Konsistenz und ruhiges
  Volumen (Auswahl) + Volumenschock (Verstärker), Gewichte 1 / 0,5 / 1 / 1 /
  0,5. **Nur Top 500 nach Umsatz, Kurs ≥ 5 $**, Top 30, Haltedauer 5 oder
  10 Tage (entscheidet §6.7), Stop 2 ATR. Kosten sind hier alles:
  Limit-Orders im Spread, kein Kauf in den ersten 20 Minuten, Zielkosten
  ≤ 10 bps je Seite. Stirbt die Spur bei 20 bps im Backtest, wird sie
  nicht live gebaut.
- **Spur „mittel“ (21–42 Tage)** — Score = Momentum-Konsistenz + ruhiges
  Volumen + vola-skaliertes Momentum (1 / 1 / 0,5), Top 800, Top 50,
  Rebalancing wöchentlich mit Mindesthaltedauer 21 Tage, Ausstieg bei
  Rangverlust unter Perzentil 60 oder nach 63 Tagen, Stop 3 ATR.
- **Regime** für beide: neue Käufe nur bei SPY > SMA200 UND VIX < 25;
  offene Positionen laufen mit Stop weiter (kein Panikverkauf am
  Filtertag). Gemessen (§6.6): halbiert den Drawdown, kostet in
  Erholungsjahren.
- **Sizing**: 1/Vola relativ (`deploy_to_target=True`), Deckel 5 % je
  Position bei Top 50 (10 % bei Top 30), Zielinvestition 90 %.
- **Gewinnmaximierung, wo sie erlaubt ist:** Konzentration auf Top 20–30
  nur in der kurzen Spur und nur im liquiden Universum (§6.6 zeigt, warum
  Top 20 aus 3.000 verliert); voll investiert bei Regime an; kein Hebel im
  Aktienbuch. Mehr Rendite kommt aus mehr Vorsprung je Trade, nicht aus
  mehr Trades.

### 7.1 Das „smarte“ System: Prognose statt Uhr

Die Spuren „kurz“ und „mittel“ sind die **Messfassungen** (fester Horizont,
damit die Zahlen vergleichbar sind). Die **Betriebsfassung** hält nichts nach
Kalender, sondern nach Prognose — genau die Forderung „dynamisch je Aktie“:

```
           ┌────────────────────────────────────────────────────────┐
           │  Merkmale je Aktie (Faktorzoo: Umkehr, Konsistenz-       │
           │  Momentum, ruhiges Volumen, Volumenschock, Vola, ...)    │
           └───────────────┬────────────────────────────────────────┘
                           ▼
   ┌────────────┬────────────┬────────────┬────────────┬────────────┐
   │ Modell h=5 │ Modell h=10│ Modell h=21│ Modell h=42│ Modell h=63│   LightGBM je Horizont,
   │ E[r_5]     │ E[r_10]    │ E[r_21]    │ E[r_42]    │ E[r_63]    │   walk-forward, Embargo
   └─────┬──────┴─────┬──────┴─────┬──────┴─────┬──────┴─────┬──────┘
         └────────────┴────────────┼────────────┴────────────┘
                                   ▼
        rate_h = (E[r_h] − Rundlaufkosten) / h     → erwartete Nettorendite JE TAG
        h* = argmax_h rate_h                        → der Horizont, den DIESE Aktie heute verspricht
                                   ▼
   KAUFEN   Top-N nach rate_h*, nur wenn E[r_h*] > Mindestvorsprung und Regime-Tor offen
   HALTEN   jeden Tag neu: solange max_h E[r_h] > Ausstiegskosten
   WECHSELN wenn Kandidat: rate > rate(schwächste Position) + Kosten/h
   SICHERN  Stop 2–3 ATR, Sicherheitsgrenze 126 Tage, Risiko-Dach
```

Warum das besser ist als „max 10 Tage“ oder „max 21 Tage“: Eine Aktie, die
in 10 Tagen 3 % verspricht (0,30 %/Tag), wird der Aktie vorgezogen, die in
63 Tagen 8 % verspricht (0,13 %/Tag) — es sei denn, die Kosten des
schnelleren Umschlags drehen die Rechnung; das steht in `rate_h` schon
drin. Und eine Position wird nicht verkauft, weil ein Zähler abgelaufen
ist, sondern weil die Prognose für *diese* Aktie nichts mehr hergibt.

Was es **nicht** ist: ein Reinforcement-Learning-Agent. Das DQN im Projekt
existiert und hat einen ehrlichen Timing-Test — aber die Evidenz für RL auf
Tagesdaten ist dünn (2.500 Schritte je Aktie, nichtstationär, Belohnung
= Kursverlauf auswendig gelernt; `rl/__init__.py` beschreibt es selbst).
Baum-Modelle je Horizont mit Walk-Forward sind das, was in der Literatur
(Gu/Kelly/Xiu 2020 und Nachfolger) out-of-sample trägt. RL bleibt für die
Positionsgröße als Experiment im Schatten, nicht als Kern.

Was es kostet: fünf Modelle statt eines = fünfmal so viele Wege, Rauschen
zu lernen. Deshalb gilt die Bestehensgrenze aus §6.8 (dynamisch ≥ beste
feste Fassung auf denselben Vorhersagen, OOS-IC je Horizont > 0,01), und
deshalb läuft die dynamische Fassung als eigener Schattenbot gegen die
festen Spuren, bevor sie Kapital bekommt.

In der Engine ist der Mechanismus fast da: `exit_score` verkauft heute
schon, wenn „die These nicht mehr trägt“. Neu sind (a) `E[r_h]` je Horizont
als Score statt des linearen Umkehr-Scores, (b) `rate_h` als Rangkriterium,
(c) der Wechsel mit Opportunitätskosten. Alles drei in `signals.py`/
`engine.py` als Strategie `dynamisch`, Konfiguration
`EngineConfig.for_dynamisch()`.

**Buch B (ORB auf Einzelaktien) ist die Daytrading-Spur** — mit
Kapitaldeckel, eigener Buchführung (`bot_id`) und der Bestehensgrenze aus
HYP-04. **Buch C ist ein Nebentest** mit kleinem Deckel; es ist der einzige
Ort, an dem ETFs gehandelt würden, und er entfällt, wenn Buch A und B das
Kapital brauchen.

**Datenpipeline (alles kostenlos):**

| Daten | Quelle | Takt | Modul |
|---|---|---|---|
| Tagesbars 1.200 Symbole | Alpaca (Handel) / yfinance (Forschung) | täglich | `data.py`, `datasources.py` |
| 5-Minuten-Bars für ORB | Alpaca IEX (oder `delayed_sip` historisch) | täglich, gecacht | `26_` |
| Ergebnistermine | EDGAR 8-K Item 2.02 (Filing-Index, Volltext-Suche) | täglich | `edgar.py` **Erweiterung** |
| Insider | EDGAR Form 4 | täglich | `edgar.py` (fertig) |
| Short Interest | FINRA Equity Short Interest Files | halbmonatlich | **neu** `finra.py` |
| VIX, Zinskurve, HY-Spread | CBOE CSV, FRED (`T10Y3M`, `BAMLH0A0HYM2`) | täglich | **neu** `makro.py` |
| News-Frequenz | Alpaca News | täglich (Kontingent!) | `news.py` (fertig) |

---

### 7.2 Architektur v2: die Prognose als Score (Entwurf, 2026-09-29)

Beschlossen als Plan, gebaut erst nach der Bestätigungskette (§6.10:
S&P-Panel, qlib mit Regime-Tor, Horizonte 10/42). Wenn der ML-Ranker dort
den Handmix nicht um ≥ 2 Punkte schlägt, bleibt §7.1 mit Handmix. Wenn ja:

1. **Merkmale**: Der Faktorzoo (`labor.faktorzoo`, 19 Merkmale) wird die
   einzige Merkmalsquelle — im Labor UND im Bot. Der Daemon lädt ohnehin
   1.200 Symbole × 2 Jahre Tagesbars; daraus baut `labor.panel_aus_data_stock`
   ein Panel und `faktorzoo` die Merkmale des Tages. Kein zweiter
   Rechenweg (`build_ranking_frame` bleibt für die Handmix-Strategie).
2. **Modell**: `src/alpaca_bot/modell.py` — `trainieren(panel, horizont,
   bis)` (LightGBM, dieselben Parameter wie 23_, Embargo), `laden(pfad)`,
   `vorhersagen(merkmale_heute)`. Modelle liegen in `models/lgbm_h21_<datum>.txt`
   im Repo (klein), Training jährlich im Januar auf allen Daten bis
   Ende November (Embargo), Protokoll im Register.
3. **Engine**: Strategie `"ml"` — `_querschnitt_scores` nimmt die
   Modellvorhersage als Score statt des Z-Score-Mixes; alles andere
   (Regime-Tor, Top-Dezil, 50 Plätze, 21–63 Tage, Rangverlust 0,20, Stop
   3 ATR, Risiko-Dach, Vola-Ziel) bleibt. So ist der Wechsel eine Zeile
   in der Konfiguration, und der Replay 31_ vergleicht beide Scores auf
   demselben Pfad.
4. **Horizontwahl** (§6.8 dyn_ic) erst als zweite Stufe: ein Modell je
   Horizont, Rate = IC-gewichtete Erwartung je Tag. Nur wenn Stufe 3 auf
   beiden Panels steht.
5. **Kontrollen, die nicht verhandelbar sind**: Walk-forward-Bericht je
   Jahr im Register; das Modell des Bots ist immer das des letzten
   Januars (kein Nachtrainieren unter dem Jahr); Merkmalswichtigkeit wird
   protokolliert und muss die Handmix-Bausteine enthalten (sonst hat das
   Modell etwas gelernt, das wir nicht verstehen — Abbruch, §9.2).

Was das für den Zeitplan (§8) heißt: Schritt 2 (November) bekommt den
Punkt „Modell-Modul + Strategie ml + Replay-Vergleich“; Schritt 3
(Dezember) startet das Papierdepot mit dem Score, der im Replay auf
deinem Cache vorn liegt. Der Handmix ist der Rückfall, nicht der Plan.

## 8. Bauplan mit Zeitachse bis Januar 2027

### Schritt 0 — Oktober, Woche 1–2: Messen auf deinen Daten (kein Code im Live-Pfad)

| # | Aufgabe | Befehl | Bestanden, wenn |
|---|---|---|---|
| 0.1 | Panel aus Projektcache bauen | `20_labor_daten.py --quelle projekt --pfad <yfinance_2168_*_8y.parquet> --name projekt` | 2.000+ Symbole, 8 Jahre, OHLCV |
| 0.2 | Faktorzoo | `21_labor_faktoren.py --panel projekt` | Jahrestabelle inkl. 2020, 2022 gelesen |
| 0.3 | Portfolios, liquides Universum, Top 50 | `22_labor_portfolio.py --panel projekt --variante {kurz,kurz10,kombi2,momentum,reversal_rein} --top-n 50 --min-dollar-volume 25000000` | Tabelle in §6.8 dieses Docs, Spalten SPY **und** Univ.EW |
| 0.4 | Haltedauer-Kurve der kurzen Spur | `24_labor_haltedauer.py --panel projekt --variante kurz --haltedauern 2 5 10 21 42 --min-dollar-volume 25000000` | zeigt, ob H=5 oder H=10 die Kosten überlebt |
| 0.5 | ML-Ranker | `23_labor_ml_ranking.py --panel projekt --horizont 10 --min-dollar-volume 25000000 --top-n 50` | OOS-IC je Jahr, Vergleich zum besten Einzelfaktor |
| 0.6 | Overnight | `25_labor_overnight.py --panel projekt --symbole SPY QQQ IWM` | Breakeven 2016–2026 |
| 0.7 | ORB | `26_labor_orb_intraday.py --start 2024-01-02 --ende 2024-12-31` (1 Jahr, ~2.000 Requests) | Sharpe, Trades je Tag, RV-Band-Tabelle |
| 0.8 | Hypothesen registrieren | `27_hypothesen_anmelden.py --anmelden` | Register zeigt 16 Einträge |
| 0.9 | PDT-Status am Konto prüfen | `01_check_setup.py` + Alpaca-Dashboard | Feld `pattern_day_trader` / Margin-Modell dokumentiert |

Entscheidung am Ende von Schritt 0: **Welche zwei bis drei Faktoren tragen
auf deinen Daten netto?** Nur die kommen in Schritt 1.

### Schritt 1 — Oktober, Woche 3–4: Neue Datenlader

| # | Aufgabe | Datei | Prüfung |
|---|---|---|---|
| 1.1 | EDGAR 8-K Item 2.02 → Ergebnistermine je Symbol mit Einreichungszeit | `edgar.py: earnings_dates()` | Für 50 Symbole gegen yfinance-Kalender abgleichen (≥ 90 % Treffer ± 1 Tag) |
| 1.2 | FINRA Short Interest (Archiv ab 2014) | `finra.py` | 20 Stichtage, SI/Float je Symbol, `pit.asof_join` mit +1 Tag |
| 1.3 | Makro (VIX, T10Y3M, HY-Spread) mit Cache | `makro.py` | `regime_serien` läuft live |
| 1.4 | Sektor je Symbol (GICS aus `datasets/s-and-p-500-companies`, sonst SIC aus EDGAR) | `universe.py` | Feld in `reasons` (mehrbot-plan §9.4) |
| 1.5 | EAR-Faktor und SI-Faktor in `labor.faktorzoo` | `labor.py` | PIT-Audit bestanden |
| 1.6 | Messen wie 0.2–0.3 mit den neuen Faktoren | `21_`, `22_` | HYP-03, HYP-10 entschieden |

### Schritt 2 — November: Strategie „ranking“ in der Engine, Schatten voranmelden

| # | Aufgabe | Datei | Prüfung |
|---|---|---|---|
| 2.1 | `build_ranking_frame()` mit den Siegern aus Schritt 0/1 — zwei Gewichtssätze („kurz“, „mittel“) | `signals.py` | `pit.audit_feature_function` |
| 2.2 | `EngineConfig.for_ranking_kurz()` (H_min 5/10, max_hold 15, stop 2 ATR, Top 30, Universum 500) und `for_ranking_mittel()` (H_min 21, max_hold 63, stop 3 ATR, Top 50, Universum 800) | `engine.py` | `simulate.py` 2016–2026 reproduziert `22_`-Ergebnis ± 2 %-Pkt CAGR |
| 2.3 | Regime als Kauf-Tor, Vola-Sizing relativ, Rangverlust-Ausstieg | `engine.py` | Investitionsgrad 85–90 % bei Regime an |
| 2.4 | Risiko-Dach | `risiko.py` (mehrbot-plan §5) | Sperre auslösen/lösen im Trockenlauf |
| 2.5 | Schattenbots anmelden: `K00_kurz_basis`, `K01_kurz_H10`, `K02_kurz_top20`, `M00_mittel_basis`, `M01_mittel_ohne_volumen`, `M02_mittel_ohne_regime` — **eine Achse je Bot**, Vergleich kurz gegen mittel gepaart | `18_fleet.py --anmelden` | Divergenz-Diagnose: kein Bot identisch mit Basis |
| 2.6 | ORB als Schattenbuch (kein Handel), täglich nach Schluss ausgewertet | `26_` + `shadow.py` Erweiterung | Trades je Tag, RV-Band, netto |
| 2.7 | Overnight-Papierhandel QQQ/IWM mit `cls`/`opg`, 4 Wochen | `05_paper_trade.py` Erweiterung | gemessene Fill-Abweichung zum Auktionspreis |

### Schritt 3 — Dezember: Papierdepot mit „ranking“, Umkehr-Bot stilllegen

| # | Aufgabe | Prüfung |
|---|---|---|
| 3.1 | Daemon auf `for_ranking()` umstellen, Umkehr nur noch im Schatten | 10 Handelstage ohne Regelverstoß (`audit.py`) |
| 3.2 | Slippage über ≥ 30 Orders messen | Median < 8 bps (mehrbot-plan Sperrbedingung) |
| 3.3 | Schattenvergleich R00 gegen B00 (alt) gepaart | t über Schwelle nach ≥ 40 Tagen — sonst weiter messen |
| 3.4 | Tresor öffnen: `22_` auf 2025–2026 (letzte 20 %) **einmal** | Ergebnis akzeptieren |

### Schritt 4 — Januar 2027: Start

- Kapital klein (Totalverlust verkraftbar), Risiko-Dach aktiv, Regime an.
- Buch B (ORB) nur, wenn HYP-04 in Schritt 0.7 UND im Schatten (2.6) hält.
- Buch C (Overnight) nur, wenn 2.7 Fill-Kosten < 1 bps zeigt.
- Wochenbericht aus `13_tagesbericht.py` + `17_shadow_report.py`.

**Was den Zeitplan sprengen darf:** Nichts davon ist verhandelbar außer der
Reihenfolge innerhalb eines Schritts. Wer Schritt 0 auslässt, wiederholt
den Fehler vom Frühjahr (Strategie gebaut, dann gemessen).

---

## 9. Welche Zahlen wir uns erhoffen — und ab wann wir abbrechen

### 9.1 Erwartung (kalibriert VOR den Messungen auf deinem Cache)

| Buch | Brutto p.a. | Kosten p.a. | **Netto p.a.** | Sharpe | MaxDD | Bezug |
|---|---|---|---|---|---|---|
| A „mittel“ (21–42 Tage), kein Regime | SPY + 6–9 %-Pkt | 2–4 % | **SPY + 3–6 %-Pkt** | 0,8–1,1 | ≈ SPY | Literatur ÷ 2 (McLean-Pontiff), §6.3 ÷ 3 (Bias) |
| A „mittel“ mit Regime + Vola-Sizing | SPY + 3–6 %-Pkt | 2–3 % | SPY + 1–4 %-Pkt | 0,9–1,3 | **−20 bis −28 %** | §6.3 Regimefassungen |
| A „kurz“ (5–10 Tage, Top 30, Universum 500) | SPY + 10–15 %-Pkt | **8–15 %** (!) | **SPY + 0–6 %-Pkt** | 0,7–1,2 | ≈ SPY | §6.5 h=5-Quintilspannen ÷ 2, Kosten 10–20 bps × 25–50 Rundläufe |
| B ORB Stocks in Play (≤ 20 % Kapital) | 15–40 % auf das Teilkapital | 5–15 % | **0–20 %** auf Teilkapital | 0,5–1,5 | −15 % | Paper 2,4–2,8 Sharpe × IEX-Abschlag |
| C Overnight QQQ/IWM Auktion (≤ 20 %) | 8–12 % | 1–3 % | 4–8 % | 0,6–0,9 | −25 % | §6.4 |
| **Gesamt** | | | **SPY + 3–7 %-Pkt** | **1,0–1,3** | **−20 bis −30 %** | |

In Zahlen bei 12 % SPY-Jahr: 15–19 % netto. In einem Jahr wie 2022 (SPY −18 %):
−5 bis −12 % (Regime dämpft), nicht +20 %. **Das ist realistisch. Mehr
verspricht kein Datensatz, den wir ehrlich prüfen können.**

Und die Gegenrechnung aus §6.7 gehört daneben: Auf 2006–2020 im liquiden
Universum hat **keine** der Auswahlregeln SPY in der CAGR geschlagen; der
verlässliche Gewinn dort war die Halbierung des Drawdowns durch das
Regime-Tor. Sollte der Projektcache (2018–2026) dasselbe zeigen, ist die
richtige Antwort nicht „mehr handeln“, sondern: Regime-gesteuerter
Einzelaktien-Kern mit dem Mehr-Horizont-Modell als Auswahl (§7.1), niedriger
Umschlag, und die Daytrading-Spur nur, wenn HYP-04 besteht. Ein System, das
SPY um 2 Punkte schlägt und 2008/2020/2022 mit −20 % statt −35/−55 %
übersteht, ist über zehn Jahre der bessere Bot als eines, das im
Backtest 30 % zeigt und im ersten Bärenjahr abgeschaltet wird.

### 9.2 Abbruchkriterien (jetzt aufschreiben, nicht wenn es soweit ist)

| Ereignis | Konsequenz |
|---|---|
| Schritt 0: kein Faktor mit ≥ 75 % positiven Jahren und Netto-Vorteil auf deinem Cache | Kein Bot 2027 mit dieser Auswahl; zurück zu HYP-06 (ML) und HYP-03 (EAR) |
| Schritt 0.7: ORB Sharpe < 0,5 netto oder Top-RV nicht besser als Zufallsauswahl | Buch B gestrichen, keine zweite Runde |
| Schritt 2.7: Auktions-Fills > 1 bps Abweichung | Buch C gestrichen |
| Schritt 3.2: Slippage Median > 8 bps | Universum auf Top 600 verkleinern, erst dann Start |
| Schritt 3.4: Tresor-Ergebnis unter SPY | Start verschoben; Strategie tot, nicht „nachjustieren“ |
| Live: Konto-Drawdown > 20 % | Vollsperre (Risiko-Dach), Ursachenanalyse |
| Live: 3 Monate hinter SPY um > 10 %-Pkt bei Regime an | Halbieren, Schatten entscheidet |

---

## 10. Was bewusst nicht gemacht wird

- **Kein „alles einbeziehen“ auf einmal.** Jede Quelle (Short Interest,
  Insider, News, Makro) kommt als ein Faktor mit eigener Messung. Zehn
  ungeprüfte Merkmale in ein Modell zu werfen erzeugt einen Backtest, der
  gut aussieht und nichts bedeutet.
- **Keine Parameteroptimierung.** Gewichte bleiben rund, Haltedauern sind
  21/42/63, Stops 2/3 ATR. Was mit runden Zahlen nicht trägt, trägt nicht.
- **Kein Hebel im Multi-Wochen-Buch.** Der ORB-Test darf intraday hebeln,
  hält aber nichts über Nacht.
- **Keine Sekunden-Strategien**, keine Level-2-Daten, kein Market Making.
- **Keine Regeländerung aus dem Papierdepot allein.** Der Schatten mit
  gepaartem Test entscheidet, das Depot misst nur Ausführung.
- **Kein Livegang vor dem 6-Monats-Papierbetrieb der neuen Konfiguration** —
  Verfassung Regel 1. Das Papierdepot läuft seit Juli mit der *alten*
  Strategie; die Uhr für „ranking“ beginnt in Schritt 3, also Dezember.
  **Ein Livestart im Januar 2027 ist damit ein Start mit Testkapital im
  Papier-plus-Kleinstbetrag-Modus, kein voller Livegang.** Wer das anders
  will, ändert bewusst die Verfassung — nicht still.

---

*Dokumentation zu einem Softwareprojekt, keine Anlageberatung.*
