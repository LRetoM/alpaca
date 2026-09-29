# Jahresliste 2027 — was unsere Bots in jedem Jahr gemacht hätten

> Erzeugt mit `scripts/60_jahresliste.py` am 2026-09-29. Alle Zahlen sind **nach Kosten** (gemessene
> Spanne 12,2 bps + 5 bps Slippage je Seite; Trendbot 2 + 1 bps je Seite, ETFs). Jahr = Schlusskurs
> Vorjahresende bis Jahresende. **Backtests, keine Versprechen.**

## 1. qlib-Panel 2009 – 10,11,2020 (breites Universum, ehrlichster Test)

| Jahr | SPY | Trendbot 15 % | Aktien-Momentum (Handmix) | Hybrid (Stop nur im Trend) | Hybrid (ohne Stop) | Mix 50/50 |
|---|---:|---:|---:|---:|---:|---:|
| 2009 | +22,7 % | +1,9 % | +16,1 % | +16,7 % | +19,0 % | +9,3 % |
| 2010 | +15,1 % | +9,3 % | +1,8 % | +16,5 % | +20,8 % | +13,1 % |
| 2011 | +1,9 % | +1,2 % | +2,5 % | +7,6 % | +9,8 % | +5,0 % |
| 2012 | +16,0 % | +7,5 % | +3,8 % | +7,5 % | +8,1 % | +7,6 % |
| 2013 | +32,3 % | +8,9 % | +21,8 % | +21,1 % | +29,8 % | +14,9 % |
| 2014 | +13,5 % | +11,4 % | +5,5 % | +6,0 % | +17,4 % | +8,9 % |
| 2015 | +1,2 % | −7,5 % | −3,7 % | +5,5 % | +7,8 % | −1,0 % |
| 2016 | +12,0 % | −2,0 % | +4,4 % | +7,8 % | +10,9 % | +3,0 % |
| 2017 | +21,7 % | +20,9 % | +24,2 % | +28,6 % | +22,8 % | +24,8 % |
| 2018 | −4,6 % | −4,4 % | −3,1 % | −3,9 % | −6,3 % | −4,0 % |
| 2019 | +31,2 % | +21,3 % | +2,9 % | +23,4 % | +22,7 % | +22,5 % |
| 2020* | +11,6 % | −6,4 % | +15,5 % | +14,7 % | +21,7 % | +4,3 % |
| **CAGR 2009-2020*** | +14,2 % | +4,8 % | +7,4 % | +12,4 % | +15,2 % | +8,8 % |
| **Max. Drawdown** | −33,7 % | −22,1 % | −24,9 % | −35,5 % | −34,6 % | −28,5 % |
| **Sharpe** | 0,82 | 0,46 | 0,57 | 0,73 | 0,85 | 0,69 |

`*` 2020 endet am 10.11. (Panel-Ende).

Weitere Spalten in `results/labor/jahresliste.csv`: 60/40, Trendbot 10 %, Hybrid mit Stop 3.

## 2. Was die Zahlen aussagen (und was nicht)

- **Kein Bot schlägt SPY nach Rendite sicher.** Am nächsten kommt der Hybrid ohne Stop (15,2 % gegen 14,2 %, Sharpe 0,85
  gegen 0,82) — ein Abstand innerhalb des Rauschens eines einzelnen Engine-Replays (±3 Punkte, Lehre §2.15), in-sample entworfen,
  mit ML-Modell, das noch nicht trainiert im Repo liegt.
- **Der heute startbare Bot** (Aktien-Momentum, Handmix, Tor, Stop 3) macht 7,4 % gegen SPY 14,2 % bei −24,9 % statt −33,7 % Drawdown:
  er kauft Ruhe, keine Rendite.
- **Der Trendbot** (`dualmom_15`) gibt in diesem Bullenfenster 9 Punkte CAGR ab (4,8 %); 2008 war er +14 % gegen SPY −36 %
  (nicht in der Tabelle, weil die Hybrid-Vorhersagen erst 2009 beginnen).
- **Der 50/50-Mix hilft hier nicht:** 8,8 % bei −28,5 %. Der Drawdown sinkt um 5 Punkte, die Rendite um 6.
- **Mit Stop nur im Trend** (HYP-26) gewinnt nicht gegen Stop 3 (12,4 % beide): die Hypothese ist in dieser Ziehung nicht bestätigt.
- **Kosten:** Der Wechsel von 5 + 5 auf 12,2 + 5 bps kostet je Bot 0,3 bis 0,6 CAGR-Punkte (Hybrid ohne Stop 15,5 → 15,2 %;
  Handmix 8,0 → 7,4 %), nicht die 0,7, die vorab geschätzt waren.
- **Nicht enthalten:** Zins auf ungenutztes Bargeld bei den Aktien-Bots (2009–2015 ~0; laut develop §G96 später +1,4 Punkte/Jahr auf
  den Cash-Anteil).

## 3. Bis 2026 — was im Container möglich ist und was nicht

**Der Nutzer hat recht:** Der Bot soll bis 2026 laufen, und ein Test, der 2020 endet, reicht nicht. Im Container gibt es aber nur
ein Panel bis 2026 — `sp500_close`: **nur Schlusskurse, nur heutige S&P-500-Mitglieder (Survivorship), kein Volumen.** Alles mit
Volumen (qlib, Lean) endet 2020/2021; der Projektcache (2.168 Symbole, 2018–2026) und der Alpaca-Vorrat (07/2020–2026) liegen
auf dem Mac (`scripts/61_stufe1.py`, §5). Was sich hier bis 2026 rechnen lässt:

**Aktien-Bot Momentum (Handmix, Stop 3, Tor), Engine-Replay, Kosten 12,2 + 5 bps — Obergrenze:**

| | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026* |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Aktien-Bot (S&P-Panel) | +25,5 | −6,8 | +17,8 | +30,7 | +8,3 | −10,1 | +4,6 | +44,5 | +16,2 | +20,0 |
| SPY | +21,7 | −4,6 | +31,2 | +18,3 | +28,7 | −18,2 | +26,2 | +24,9 | +17,7 | +7,9 |

CAGR 2017–09/2026: Aktien-Bot **+14,4 %**, SPY +15,2 %; MaxDD −23,5 % gegen −33,7 %; Sharpe 0,88 gegen 0,87.

**Gemessener Survivorship-Abstand:** Derselbe Bot macht in den gemeinsamen Jahren 2017 – 10.11.2020 auf dem S&P-Panel 16,5 % pro Jahr,
auf dem qlib-Panel (mit ausgeschiedenen Aktien) 9,6 % — **6,9 Punkte pro Jahr Unterschied** (ein Fenster, vier Jahre, grobe Schätzung).
Der ehrliche Wert für 2017–2026 liegt damit bei etwa **+7,5 % pro Jahr** und deckt sich mit den 7,4 % des qlib-Laufs 2009–2020.

**Trendbot bis 2026 — nur mit Vorbehalt.** Im Container fehlen fünf der zehn ETFs (kein GLD, EFA, EEM, IWM, DIA, BIL). Eine Nachbildung mit
SPY/QQQ/TLT/HYG/LQD wurde gegen den vollen Lauf geprüft und ist **nicht verlässlich**: auf 2016–2020 weicht sie um −1,8 bis +7,8 Punkte je
Jahr ab (2018: +3,4 % statt −4,4 %; CAGR 9,1 % statt 5,6 %); auf 2022–2026 liegt sie mit rund 8 % weit unter den **14,4 % pro Jahr bei −14,8 %
Rückgang, die develop auf echten Alpaca-Daten gemessen hat** (§G96/§G98, 02/2022 – 09/2026, mit BIL-Cash). Für den Trendbot gilt deshalb die
Messung von develop; eine Mix-Zeile bis 2026 aus der Nachbildung wäre nicht belastbar und steht nicht in dieser Liste.

**Umkehr-Bot (läuft heute im Papierdepot), Historien-Simulation aus develop §G11, 5 bps Spanne, Survivorship +2 bis +4 Punkte/Jahr:**

| | 2021 | 2022 | 2023 | 2024 | 2025 | 2026* |
|---|---:|---:|---:|---:|---:|---:|
| Umkehr-Bot | −6,9 | −17,8 | +17,1 | −8,5 | −7,7 | +30,3 |
| SPY | +30,5 | −18,7 | +26,7 | +25,6 | +18,0 | +12,7 |

Über 8 Jahre +1,95 % CAGR bei 5 bps, **−2,84 % bei der gemessenen Spanne**; ehrlich eher −5 bis −7 % (develop §G54).

**Nicht bis 2026 messbar im Container:** Hybrid/ML (braucht Volumen: `vol_schub_6m_neg` ist das wichtigste Merkmal), der volle Trendbot und
jeder Bot auf einem Universum mit ausgeschiedenen Aktien. Das ist der Zweck von §5.

## 4. Grenzen dieser Liste

- Backtests. Ein Engine-Replay hat ±3 Punkte CAGR Ziehungsrauschen (Lehre §2.15).
- qlib enthält auch ausgeschiedene Aktien; `sp500_close` nicht.
- Bargeld bei den Aktien-Bots ohne Zins (2009–2015 ~0, später laut develop §G96 bis +1,4 Punkte/Jahr auf den Cash-Anteil).
- Hybrid und Stop-Varianten sind auf denselben Daten entworfen, auf denen sie gemessen wurden.

## 5. Stufe 1 auf dem Mac — der Test bis 2026 mit Volumen

Ein Befehl (Dauer etwa 1 bis 1,5 Stunden), er baut das Panel aus dem Projektcache, rechnet die ML-Vorhersagen, die Engine-Replays mit gemessenen
Kosten und gibt dieselbe Jahresliste aus — dann für 2019/2021 bis 2026 mit Volumen:

```bash
cd ~/Documents/alpaca
.venv/bin/python scripts/61_stufe1.py --pfad "$HOME/Library/Application Support/alpaca-bot/data/cache/bars/yfinance_2168_*_8y.parquet"
```

Die Ausgabe steht danach in `results/labor/stufe1_projekt.txt`. Fehlende ETFs im Projektcache meldet der Runner; dann läuft der Trendbot nicht,
und die Zahlen von develop (§G90/§G96) gelten weiter.
