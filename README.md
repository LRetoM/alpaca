# Alpaca Trading & Analyse-Werkstatt

Arbeitsplatz für Paper-Trading, Marktdaten-Analyse, Ereignisstudien,
ML-Prognosen und ein DQN-System — mit den Sicherungen, die verhindern,
dass ein System sich selbst betrügt.

## Dokumentation

| Dokument | Inhalt |
|---|---|
| [docs/leitfaden.md](docs/leitfaden.md) | Einstieg: kostenlose Datenquellen, was KI im Trading kann |
| [docs/strategie-analyse.md](docs/strategie-analyse.md) | Die Mathematik (`IR ≈ IC × √BR`), Testprotokoll, Survivorship-Bias |
| [docs/kompendium.md](docs/kompendium.md) | Alle Strategien, Chartmuster und Indikatoren — nach Evidenz bewertet |

---

## Einrichtung

Die Umgebung steht (`.venv` mit allen Paketen). Nur die Keys fehlen:

```bash
cp .env.example .env      # dann Keys eintragen
.venv/bin/python scripts/00_selftest.py      # 47 Prüfungen, ohne Keys
.venv/bin/python scripts/01_check_setup.py   # mit Keys
```

> Die `.env` steht in `.gitignore`. Secret Keys gehören nie in Code, Repository oder Chat.

---

## Die Skripte

| Skript | Zweck |
|---|---|
| `00_selftest.py` | 47 Prüfungen des gesamten Codes. Keine Keys nötig. |
| `01_check_setup.py` | Keys, Konto, Marktdaten, Börsenstatus |
| `02_market_overview.py` | Täglicher Überblick: Trend, RSI, Vola, Korrelationen |
| `03_backtest.py` | Strategien testen, immer gegen Buy & Hold |
| `04_train_model.py` | ML mit Walk-Forward-Validierung |
| `05_paper_trade.py` | Handeln — ohne `--live` nur Vorschau |
| `06_event_study.py` | **Hätten wir den Ausbruch vorher erkannt?** Inkl. Negativtests |
| `07_journal_report.py` | Welche Begründung hat sich bewährt? Slippage-Abgleich |
| `08_train_rl.py` | DQN trainieren — Urteil per Timing-Test |
| `09_selfcheck.py` | **Vor jeder Änderung ausführen.** Code gegen die Projektverfassung |

---

## Module

| Modul | Zweck |
|---|---|
| [config.py](src/alpaca_bot/config.py) | Keys aus `.env`, Risiko-Leitplanken |
| [clients.py](src/alpaca_bot/clients.py) · [data.py](src/alpaca_bot/data.py) | Alpaca-Anbindung, Bars, Quotes, Snapshots |
| [account.py](src/alpaca_bot/account.py) · [trading.py](src/alpaca_bot/trading.py) | Konto, Positionen, Orders mit Risikoprüfung |
| [indicators.py](src/alpaca_bot/indicators.py) · [strategies.py](src/alpaca_bot/strategies.py) | Indikatoren und 5 Vergleichsstrategien |
| [backtest.py](src/alpaca_bot/backtest.py) | Vektorisiert, mit Kosten und Benchmark |
| [features.py](src/alpaca_bot/features.py) · [ml.py](src/alpaca_bot/ml.py) | 29 stationäre Merkmale, Walk-Forward mit Embargo |
| **[pit.py](src/alpaca_bot/pit.py)** | **Point-in-Time-Wächter — findet Lookahead-Lecks mechanisch** |
| [events.py](src/alpaca_bot/events.py) | Explosionen finden, Vorfenster, Kontrollgruppe |
| [news.py](src/alpaca_bot/news.py) | Nachrichten-Historie, zeitpunktsicher zusammengeführt |
| [universe.py](src/alpaca_bot/universe.py) | Universum + Survivorship-Bias messbar machen |
| **[journal.py](src/alpaca_bot/journal.py)** | **Audit: Entscheidung → Begründung → Ergebnis, verknüpft** |
| **[costs.py](src/alpaca_bot/costs.py)** | **Was ein Trade wirklich kostet und was ankommt** |
| [compliance.py](src/alpaca_bot/compliance.py) | PDT-Regel, Daytrade-Zähler, API-Budget-Preflight |
| [ratelimit.py](src/alpaca_bot/ratelimit.py) | Alle API-Limits an einer Stelle, mit Tageszählern |
| [selfcheck.py](src/alpaca_bot/selfcheck.py) | Projektverfassung, maschinell geprüft |
| [rl/](src/alpaca_bot/rl/) | DQN: Umgebung, Double-DQN-Agent, Walk-Forward-Training |

---

## Die fünf Sicherungen

Jede verhindert eine bestimmte Art, sich selbst zu betrügen:

1. **`dry_run=True` überall Standard.** Nichts wird gesendet, bis du es willst.
2. **Risiko-Leitplanken** (`MAX_POSITION_PCT`, `MAX_ORDER_NOTIONAL`) bei jeder Order.
3. **PDT-Regel im Code.** Unter 25.000 $ nur 3 Daytrades je 5 Werktage — sonst 90 Tage Sperre.
4. **Point-in-Time-Audit.** `pit.audit_feature_function()` baut Merkmale doppelt (voll und abgeschnitten) und vergleicht. Ein Feature, das Zukunftsdaten nutzt, fällt mechanisch auf.
5. **Der Timing-Test.** Eine RL-Politik wird nicht an ihrer Rendite gemessen, sondern gegen zeitlich verschobene Kopien ihrer selbst. Ohne Timing-Perzentil ≥ 95 lautet das Urteil „nichts gelernt" — egal wie hoch der Gewinn aussieht.

---

## Rate-Limits (Stand 28.07.2026)

Alle in [ratelimit.py](src/alpaca_bot/ratelimit.py) hinterlegt und automatisch durchgesetzt.

| Quelle | Limit | Anmerkung |
|---|---|---|
| Alpaca Trading | 200/min | pro Konto |
| Alpaca Market Data (Basic) | 200/min | Historie ab 2016, letzte 15 Min fehlen, IEX-Feed, 30 Symbole im Stream |
| Alpaca News (Benzinga) | 200/min | teilt sich das Datenkontingent, Historie ab ~2015 |
| SEC EDGAR | 10/s | User-Agent Pflicht, sonst 403 |
| FRED | ~120/min | Key gratis |
| yfinance | inoffiziell | konservativ gedrosselt, nie produktionskritisch nutzen |
| Alpha Vantage | **25/Tag** | Tageszähler überlebt Neustarts |
| FMP / Tiingo / Finnhub | 250/Tag · 500/Tag · 60/min | |

```python
from alpaca_bot import compliance
print(compliance.preflight(n_symbols=500, years=10, with_news=True))
```

---

## Gebühren — was wirklich ankommt

```python
from alpaca_bot import costs
rt = costs.round_trip(100, 100.00, 101.00, spread_bps=5)
# gedachter Gewinn: 100,00 $  →  echter Gewinn: 85,71 $  (14 % weg)
```

Kommission bei Alpaca ist 0 $, aber es bleiben: halber Spread beim Kauf,
halber beim Verkauf, SEC Section 31 (20,60 $/Mio., ab 04.04.2026, nur
Verkäufe) und FINRA TAF (0,000166 $/Aktie, nur Verkäufe).

**Im Paper-Konto fällt nichts davon an** — Paper-Ergebnisse sind deshalb
systematisch zu gut. `costs.py` rechnet die Lücke aus, bevor echtes Geld
im Spiel ist.
