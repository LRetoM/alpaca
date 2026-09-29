# Bot-Start 2027: Betriebsanleitung für die Strategie „ranking“

> Stand: 2026-09-29. Diese Anleitung beschreibt, wie der Bot mit der neuen
> Strategie gestartet wird — vom Trockenlauf über das Papierdepot bis zum
> Live-Schalter — und welche Bedingungen an jeder Stufe erfüllt sein müssen.
> Die Zahlen, auf denen die Strategie beruht, stehen in
> [masterplan-2027.md](masterplan-2027.md) §6. Die Regeln des Projekts in
> [../CLAUDE.md](../CLAUDE.md).

## 0. Was der Bot tut (in fünf Sätzen)

1. Jeden Handelstag (alle 15 Minuten, ab 20 Minuten nach Eröffnung) lädt
   er Tagesbars für die 1.200 liquidesten US-Aktien plus SPY.
2. Er berechnet je Aktie drei Bausteine — Momentum-Konsistenz, ruhiges
   Volumen, vola-skaliertes 12-1-Momentum — und bildet daraus im
   **Tagesquerschnitt** einen Z-Score-Mix und einen Rang.
3. Er kauft aus dem obersten Zehntel des Rangs bis zu 50 Positionen,
   gewichtet nach 1/Volatilität, nur wenn SPY über seinem 200-Tage-Schnitt
   liegt (Regime-Tor), Kurs ≥ 5 $, Umsatz ≥ 25 Mio. $/Tag.
4. Er verkauft bei Stop (3 ATR), nach 63 Tagen, oder — frühestens nach
   21 Tagen — wenn die Aktie unter das mittlere Perzentil fällt
   (Rangverlust). Kein Gewinnziel: Gewinner laufen.
5. Über allem sitzt das Risiko-Dach: Drawdown 20 % vom Höchststand →
   Vollsperre (nur Verkäufe, Lösen nur von Hand), Tagesverlust 5 % → keine
   neuen Käufe heute.

Erwarteter Umschlag: 12–18 Rundläufe je Position und Jahr, Kosten
~2–4 % p.a. bei 20 bps je Rundlauf. Das ist der Unterschied zum Umkehr-Bot
(100 Rundläufe, 10–20 % p.a. Kosten).

## 1. Voraussetzungen

```bash
cd ~/Documents/alpaca            # oder wo das Repo liegt
.venv/bin/python scripts/00_selftest.py      # 65 Prüfungen, ohne Keys
.venv/bin/python scripts/09_selfcheck.py     # Projektverfassung
.venv/bin/python scripts/01_check_setup.py   # Keys, Konto, Uhr
```

`.env` (nie ins Repo):

```
ALPACA_API_KEY=...
ALPACA_SECRET_KEY=...
ALPACA_PAPER=true               # Papierdepot. Live erst nach Stufe 3.
ALPACA_DATA_FEED=iex
MAX_POSITION_PCT=0.05           # bei 50 Positionen; 0.10 bei 30
MAX_ORDER_NOTIONAL=20000        # Sicherheitsnetz gegen Rechenfehler
ALLOW_LIVE_TRADING=false
PDT_RULE_ACTIVE=true            # nach Prüfung am Konto: false (FINRA 04.06.2026)
SEC_USER_AGENT=Name mail@example.com
```

Universum: `results/factor_lab/universum.csv` muss existieren
(`python scripts/11_factor_lab.py --max-symbols 2500` baut es).

## 2. Stufe 1 — Historie: die Strategie auf DEINEN Daten bestätigen

Bevor irgendetwas läuft: dieselben Messungen wie im Masterplan, auf dem
Projektcache (2.168 Symbole, 2018–2026). Dauer: 30–60 Minuten.

```bash
P=.venv/bin/python
$P scripts/20_labor_daten.py --quelle projekt --pfad "$HOME/Library/Application Support/alpaca-bot/data/cache/bars/yfinance_2168_*_8y.parquet" --name projekt
$P scripts/21_labor_faktoren.py --panel projekt --min-dollar-volume 25000000
$P scripts/22_labor_portfolio.py --panel projekt --variante kombi2 --top-n 50 --min-dollar-volume 25000000
$P scripts/24_labor_haltedauer.py --panel projekt --variante kombi2 --top-n 50 --min-dollar-volume 25000000
$P scripts/31_simulate_ranking.py --panel projekt --symbole 800          # ECHTER Engine-Pfad mit Kosten
$P scripts/23_labor_ml_ranking.py --panel projekt --horizont 21 --min-dollar-volume 25000000 --top-n 50   # ML gegen Handmix, gleiches Universum
$P scripts/23_labor_ml_ranking.py --panel projekt --horizont 21 --min-dollar-volume 25000000 --top-n 50 --regime trend_ok
$P scripts/31_simulate_ranking.py --panel projekt --symbole 800 --stop-atr 3 --exit-rank 0.2 --verlaengern 0.9 --ml-pred results/labor/ml_pred_projekt_h21.parquet
$P scripts/33_trade_autopsie.py                                    # Pflicht nach jedem Replay
$P scripts/29_labor_dynamisch.py --panel projekt --min-dollar-volume 25000000 --top-n 30
$P scripts/30_labor_muster.py --panel projekt
$P scripts/27_hypothesen_anmelden.py --anmelden
```

**Bestanden, wenn** (Spalte `trend_ok`, 20 bps):
- `22_` kombi2: CAGR ≥ SPY − 2 Punkte UND MaxDD ≤ 0,6 × SPY-MaxDD UND
  CAGR ≥ Univ.EW; 2020 und 2022 in der Jahrestabelle nicht schlechter als
  SPY − 5 Punkte.
- `31_` (Engine-Pfad) weicht von `22_` um höchstens 2 Punkte CAGR ab.
  Größere Abweichung = Fehler in einem der beiden Pfade, erst klären.
- `21_`: `vol_schub_6m_neg` und `mom_konsistenz` mit ≥ 75 % positiven
  Jahren (HYP-17 bestätigt oder verworfen).
- `23_`: **ML ≥ Handmix + 2 Punkte auf demselben Universum** (Zeile „ML minus
  bester Handmix“) → Score-Quelle `ml` für den Bot; sonst Handmix. Das ist die
  Entscheidung, die qlib (+5) und S&P (−0,2, ohne Volumen) offen lassen
  (masterplan §6.10).
- `31_` mit `--verlaengern 0.9 --exit-rank 0.2`: CAGR ≥ `22_`-Referenz − 2 Punkte
  (masterplan §6.9: ohne Verlängerung fehlten 5 Punkte).

Nicht bestanden → **kein Start.** Dann zurück zum Masterplan §9.2.

## 3. Stufe 2 — Trockenlauf und Papierdepot

```bash
# Trockenlauf: nichts wird gesendet, alles wird protokolliert
$P scripts/12_daemon.py --strategy ranking --once

# Papierdepot als Dienst (macOS launchd), Orders werden gesendet
./scripts/install_service.sh --dienst handel     # danach in der plist: --strategy ranking --live
# oder im Vordergrund:
$P scripts/12_daemon.py --strategy ranking --live
```

Parallel die Schattenflotte mit der neuen Strategie voranmelden (eine
Achse je Bot):

```bash
$P scripts/18_fleet.py --anmelden --bot-id M00_ranking_basis --achse strategy --wert ranking \
   --hypothese "Multi-Wochen-Ranking aus Konsistenz-Momentum und ruhigem Volumen schlaegt die Umkehr netto (masterplan §6.7)"
$P scripts/18_fleet.py --anmelden --bot-id M01_ohne_regime --achse market_regime_filter --wert aus \
   --hypothese "Prueft, ob das Regime-Tor den Drawdown halbiert, wie 2006-2020 gemessen"
$P scripts/18_fleet.py --anmelden --bot-id M02_top30 --achse max_positions --wert 30 \
   --hypothese "Konzentration erhoeht CAGR bei tragbarem Drawdown"
```

Täglich / wöchentlich:

```bash
$P scripts/13_tagesbericht.py
$P scripts/18_health_check.py
$P scripts/17_shadow_report.py --pruefen
$P scripts/15_lernbericht.py
$P scripts/07_journal_report.py        # Slippage: Median muss < 8 bps bleiben
```

**Stufe 2 ist bestanden, wenn** nach ≥ 60 Handelstagen:
- gemessene Slippage (Median über ≥ 30 Orders) < 8 bps,
- `audit.py` keinen Regelbruch meldet,
- der gepaarte Vergleich `M00_ranking_basis` gegen `B00_basis` (Umkehr)
  über der Zufallsschwelle liegt (`18_fleet.py --vergleich`),
- das Risiko-Dach mindestens einmal im Trockenlauf ausgelöst und gelöst
  wurde (`python -c "from alpaca_bot.risiko import RisikoDach; print(RisikoDach().sperre())"`).

## 4. Stufe 3 — Live, klein

Die Projektverfassung (Regel 1) verlangt sechs Monate Papierbetrieb der
**gestarteten Konfiguration**. Wer früher live geht, ändert die Verfassung
bewusst — mit einem Betrag, dessen Totalverlust nicht schmerzt.

```
ALPACA_PAPER=false
ALLOW_LIVE_TRADING=true
MAX_ORDER_NOTIONAL=<5 % des Kontos>
```

Dann `12_daemon.py --strategy ranking --live`. Das Skript verweigert heute
den Live-Modus mit einem Hinweis auf die Umkehr-Strategie; diese Sperre
wird erst entfernt, wenn Stufe 2 bestanden ist — das ist Absicht.

## 5. Notfälle

| Ereignis | Was passiert | Was du tust |
|---|---|---|
| Drawdown > 20 % | Vollsperre, nur Verkäufe | Ursache klären; `RisikoDach().sperre_loesen("ich habe die ursache verstanden")` |
| Tagesverlust > 5 % | keine neuen Käufe heute | nichts; morgen frei |
| Slippage-Median > 15 bps | Abbruchkriterium (mehrbot-plan §13) | Universum auf Top 600 verkleinern |
| Bot handelt gegen Regel (`audit.py`) | — | sofort aus, Logikfehler, kein Pech |
| Einzahlung/Auszahlung | Drawdown-Marke würde verfälscht | `RisikoDach().einzahlung_melden(betrag, "…", id="<alpaca activity id>")` |

## 6. Was diese Strategie NICHT ist

Kein Daytrading (das ist Buch B, `26_labor_orb_intraday.py`, eigener Test,
eigener Kapitaldeckel). Keine Garantie. Ein System, das in den Messungen
2006–2020 SPY in der CAGR **nicht** geschlagen hat und dessen Vorteil dort
der halbe Drawdown war — und das auf 2016–2026 (mit Bias) deutlich mehr
zeigte. Ob es 2027 mehr als ein Welt-ETF verdient, entscheidet Stufe 1 auf
deinen Daten und Stufe 2 vorwärts. Nicht dieses Dokument.

---
*Dokumentation zu einem Softwareprojekt, keine Anlageberatung.*
