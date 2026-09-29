# CLAUDE.md — Projekt-Brief für jede Arbeitssitzung

Dieses Dokument ist der Prompt, mit dem jede Session an diesem Repo startet.
Es ersetzt das Nachlesen von fünf Dokumenten. Wer hier arbeitet — Mensch
oder Modell — hält sich an die Regeln in Teil 2, ohne Ausnahme.

## 1. Was das Projekt ist und will

**Ziel:** Ein Handelsbot bei Alpaca (US-Aktien, später ggf. Krypto), der ab
Anfang 2027 unbeaufsichtigt läuft und **nach Kosten** zuverlässig mehr
verdient als ein Welt-ETF, bei kleinerem Drawdown. Kostenloser Rahmen: Alpaca
Basic (IEX-Feed, 200 Requests/min), yfinance, SEC EDGAR, FRED, FINRA-Dateien.

**Stand (September 2026):** Die Infrastruktur ist fertig und gut (eine
Entscheidungs-Engine für Backtest, Papierdepot und Schattenflotte, Journal
mit Begründungen, Trade-Lebenslauf, PIT-Wächter, Kostenmodell). Die aktuell
laufende **Kurzfrist-Umkehr-Strategie ist gemessen nicht kostentragfähig**
(+1,4 %/J gegen +12 %/J SPY; Kosten fressen 72–109 % des Bruttogewinns; der
Score sortiert am oberen Ende falsch). Der Vorsprung je Trade (+0,11 %) liegt
unter dem Rundlauf-Breakeven (0,14 % bei 5 bps Spread). **Das ist der Befund,
von dem aus 2027 geplant wird — nicht wegdiskutieren.**

**Der Plan:** [docs/masterplan-2027.md](docs/masterplan-2027.md). Kurz: weg
vom 5-Tage-Umschlag, hin zu **Multi-Wochen-Ranking** (Momentum + Volumen +
Ereignisse, 3–6 Wochen Haltedauer, Regimefilter, Vola-Sizing), plus **ein**
kontrollierter Daytrading-Test (ORB auf „Stocks in Play“), plus Auktions-
Overnight als Nebenkandidat. Alles zuerst auf 10+ Jahren Historie, dann
vorwärts in der Schattenflotte, dann Papierdepot, dann klein live.

## 2. Regeln, die nie verhandelt werden

1. **Erst messen, dann bauen.** Kein Faktor kommt in `engine.py`, bevor er
   in `scripts/21_labor_faktoren.py` einen |t_deflated| > 2 und ≥ 75 %
   positive Jahre hat UND in `scripts/22_labor_portfolio.py` netto nach
   Kosten trägt — Jahrestabelle mit 2018, 2020, 2022 einzeln.
2. **Hypothese vor dem Test.** Jede neue Idee wird in
   `src/alpaca_bot/hypothesen_2027.py` eingetragen (Behauptung, Quelle,
   Messvorschrift, Erwartung) und mit `scripts/27_hypothesen_anmelden.py`
   registriert, BEVOR gerechnet wird. Der Versuchszähler steigt; die
   Signifikanzschwelle `sqrt(2·ln N) + 0,5` gilt für alle.
3. **Kosten sind Pflicht.** Keine Kennzahl ohne Spread, Slippage, SEC/FINRA.
   Standard in Simulationen: 20 bps je Rundlauf (10/40 als Sensitivität).
   Was bei 40 bps stirbt, ist keine Strategie für Nebenwerte.
4. **Point-in-Time.** Entscheidung auf Schluss T, Ausführung frühestens
   Eröffnung T+1. Nachrichten +1 Tag, Fundamentaldaten am Einreichungsdatum,
   Insider am Filing-Datum. `pit.audit_feature_function()` für jedes neue
   Merkmal. Rollierende Ränge, nie globale.
5. **Survivorship benennen.** Alle freien Kursquellen enthalten nur
   Überlebende; heutige S&P-500-Listen enthalten Index-Aufnahme-Bias
   (Momentum sieht dort doppelt so gut aus). Jedes Ergebnis auf solchen Daten
   ist eine **Obergrenze** und wird so beschriftet.
6. **Referenz statt Rohwert.** Jede Rendite gegen SPY desselben Zeitraums,
   jede Trefferquote gegen die Basisrate desselben Tages, jeder Bot gegen
   `B00_basis` im gepaarten Test.
7. **Tresor.** Die letzten 20 % jeder Zeitreihe (Schatten: `--sperrzone-oeffnen`)
   werden erst angeschaut, wenn eine Entscheidung steht. Einmal.
8. **Live-Pfad nicht anfassen ohne Vorwärtsbestätigung.** `engine.py`,
   `live.py`, `daemon.py`, `trading.py`, `compliance.py` ändern sich nur
   nach einem bestandenen Schattenlauf (≥ 60 Handelstage, t über Schwelle,
   2 von 3 Regimen, Sperrzone bestätigt) — oder zur Behebung eines
   nachgewiesenen Fehlers.
9. **Keine Keys, keine Kontodaten, keine `.env` im Repo oder im Chat.**
10. **Ehrlich berichten.** Ein negativer Befund ist ein Ergebnis. „Nichts
    gefunden“ wird protokolliert wie ein Treffer.

## 3. Wo was liegt

| Frage | Ort |
|---|---|
| Der Plan bis 2027, Hypothesen, erwartete Zahlen | `docs/masterplan-2027.md` |
| Mathematik, Testprotokoll, Survivorship | `docs/strategie-analyse.md` |
| Welche Strategien belegt sind | `docs/kompendium.md` |
| Schattenflotte, Regime, Musterspeicher | `docs/schattenbetrieb.md` |
| Risiko-Dach, Mehr-Bot-Betrieb, Kapazität | `docs/mehrbot-plan.md` |
| Entscheidungslogik (EIN Pfad) | `src/alpaca_bot/engine.py`, `signals.py` |
| Historien-Replay mit Kosten | `src/alpaca_bot/simulate.py`, `scripts/10_simulate.py` |
| Faktor-IC (Schleifen-Version) | `src/alpaca_bot/research.py`, `scripts/11_factor_lab.py` |
| **Labor 2027 (Panels, Faktorzoo, Rangportfolio, Regime)** | `src/alpaca_bot/labor.py`, `scripts/20_…26_` |
| Hypothesenkatalog + Registrierung | `src/alpaca_bot/hypothesen_2027.py`, `scripts/27_` |
| Kosten, Breakeven | `src/alpaca_bot/costs.py` |
| Schatten, Flotte, Auswertung | `shadow.py`, `fleet.py`, `shadow_eval.py`, `scripts/16_–18_` |
| Daten: Projektcache | `~/Library/Application Support/alpaca-bot/data/cache/bars/*.parquet` (macOS) |
| Daten: Labor-Panels | `data/labor/<name>/{close,open,high,low,volume}.parquet` (gitignored) |
| Ergebnisse | `results/labor/*.csv` (gitignored; Zahlen wandern in die Docs) |

## 4. Wie eine Session arbeitet

```bash
.venv/bin/python scripts/00_selftest.py        # 47 Prüfungen, keine Keys
.venv/bin/python scripts/09_selfcheck.py       # Projektverfassung
# Panels einmal bauen (Mac: aus dem Projektcache)
.venv/bin/python scripts/20_labor_daten.py --quelle projekt --pfad <cache.parquet> --name projekt
# Dann messen:
.venv/bin/python scripts/21_labor_faktoren.py --panel projekt
.venv/bin/python scripts/22_labor_portfolio.py --panel projekt --variante kombi
.venv/bin/python scripts/24_labor_haltedauer.py --panel projekt --variante reversal
.venv/bin/python scripts/23_labor_ml_ranking.py --panel projekt --horizont 21
.venv/bin/python scripts/25_labor_overnight.py --panel projekt --symbole SPY QQQ IWM
.venv/bin/python scripts/26_labor_orb_intraday.py --selftest   # dann mit --start/--ende
```

Arbeitsweise für jede Aufgabe:
1. Hypothese im Katalog nachschlagen oder neu eintragen (Regel 2).
2. Auf den Labor-Panels messen (Regel 1), Jahrestabelle lesen, nicht nur
   Mittelwerte.
3. Befund in `docs/masterplan-2027.md` §Ergebnisse eintragen — auch negative.
4. Erst dann, falls positiv: Bot in der Flotte voranmelden
   (`scripts/18_fleet.py --anmelden`), eine Achse je Bot.
5. Commit mit klarer Nachricht auf Deutsch, was gemessen wurde und was
   herauskam.

## 5. Was regulatorisch neu ist (prüfen, bevor es handelt)

- **PDT-Regel abgeschafft:** SEC-Zustimmung 14.04.2026, FINRA-Wirksamkeit
  04.06.2026, Broker haben bis 20.10.2027 Zeit zur Umsetzung. Alpaca hat ein
  neues Intraday-Margin-Modell angekündigt. `compliance.py` prüft noch die
  alte 3-Daytrades-Regel — **vor dem ersten Daytrading-Test im Papierdepot
  am eigenen Konto verifizieren** (`account.daytrade_count`,
  `pattern_day_trader`) und dann anpassen. Bis dahin bleibt die Sperre
  drin: Sie schadet nicht, sie bremst nur.
- **Alpaca 24/5-Handel** (Overnight-Sessions über Blue Ocean ATS, nur
  Limit-Orders) existiert seit 2026. Für die Overnight-Hypothese sind aber
  die Auktionsorders (`cls`/`opg`) der relevante Weg, nicht die Nachtsession.
- **SEC-Gebühr** 20,60 $/Mio. seit 04.04.2026 (`costs.FeeSchedule.verified`
  jährlich prüfen).

## 6. Was dieses Projekt bewusst NICHT tut

Kein Sekunden-/HFT-Handel, kein Optionsverkauf, kein Hebel über 1,0 im
Aktienbuch außerhalb des ORB-Tests (dort ≤ 4× intraday, 0 über Nacht), keine
Chartformationen, kein Sentiment-Modell ohne gemessenen IC, keine
Parameteroptimierung auf der Gesamthistorie, keine Regeländerung aus einem
einzelnen guten Monat.

---
*Dokumentation zu einem Softwareprojekt, keine Anlageberatung.*
