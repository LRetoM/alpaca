# Befundregister 2027 — jeder Lauf, jedes Urteil

> Automatisch erzeugt aus `results/labor/befunde.jsonl` am 2026-09-29 12:09 UTC. **180 Befunde, 68 unterschiedliche Varianten → Zufallsschwelle 3.4 Sigma.** Ein t-Wert darunter ist kein Fund.

Nichts hier wird gelöscht. Verworfene Zeilen sind die wertvollsten: Sie sagen,
was nicht noch einmal probiert werden muss.

## BESTANDEN (2)

| Skript | Panel | Variante | Zeitraum | Regime | H | Kosten | CAGR | SPY | Univ.EW | Sharpe | MaxDD | Lehre |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 22 | qlib | momentum | 2006-2020 | trend_ok | 21 | 10 | 8.3% | 9.4% | 8.7% | 0.50 | -35.5% | CAGR >= SPY, Drawdown <= 0,8 x SPY, Auswahl >= Universum (rueckgefuellt) |
| 22 | sp500_close | momentum | 2016-2026 | vix_ruhig | 21 | 10 | 14.8% | 14.8% | 16.1% | 0.84 | -25.4% | CAGR >= SPY, Drawdown <= 0,8 x SPY, Auswahl >= Universum (rueckgefuellt) |

## KANDIDAT (32)

| Skript | Panel | Variante | Zeitraum | Regime | H | Kosten | CAGR | SPY | Univ.EW | Sharpe | MaxDD | Lehre |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 22 | sp500_close | ranking_preis | 2016-2026 | kein | 42 | 10 | 18.7% | 14.9% | 16.7% | 0.96 | -36.4% | knapp: DD>0,8xSPY |
| 22 | sp500_close | ranking_preis | 2016-2026 | kein | 42 | 20 | 18.0% | 14.9% | 16.7% | 0.93 | -36.4% | knapp: DD>0,8xSPY |
| 22 | sp500_close | ranking_preis | 2016-2026 | kein | 42 | 40 | 16.6% | 14.9% | 16.7% | 0.87 | -36.5% | knapp: DD>0,8xSPY |
| 22 | sp500_close | ranking_v2_preis | 2016-2026 | kein | 42 | 10 | 23.9% | 14.9% | 16.7% | 1.03 | -40.3% | knapp: DD>0,8xSPY |
| 22 | sp500_close | ranking_v2_preis | 2016-2026 | kein | 42 | 20 | 23.2% | 14.9% | 16.7% | 1.00 | -40.3% | knapp: DD>0,8xSPY |
| 22 | sp500_close | ranking_v2_preis | 2016-2026 | kein | 42 | 40 | 21.7% | 14.9% | 16.7% | 0.95 | -40.4% | knapp: DD>0,8xSPY |
| 22 | sp500_close | ranking_v2_preis | 2016-2026 | trend_ok | 42 | 10 | 16.7% | 14.9% | 16.7% | 0.91 | -34.7% | knapp: DD>0,8xSPY |
| 22 | sp500_close | ranking_v2_preis | 2016-2026 | trend_ok | 42 | 20 | 16.2% | 14.9% | 16.7% | 0.88 | -34.7% | knapp: DD>0,8xSPY |
| 22 | sp500_close | ranking_v2_preis | 2016-2026 | trend_ok | 42 | 40 | 15.2% | 14.9% | 16.7% | 0.84 | -34.7% | knapp: DD>0,8xSPY |
| 22 | sp500_close | ranking_v2_preis | 2016-2026 | vix_ruhig | 42 | 10 | 16.3% | 14.9% | 16.7% | 0.88 | -31.0% | knapp: DD>0,8xSPY |
| 22 | sp500_close | ranking_v2_preis | 2016-2026 | vix_ruhig | 42 | 20 | 15.7% | 14.9% | 16.7% | 0.86 | -31.1% | knapp: DD>0,8xSPY |
| 22 | qlib | kombi | 2006-2020 | trend_ok | 21 | 10 | 2.0% | 9.4% |  | 0.20 | -40.7% | knapp: CAGR<SPY (rueckgefuellt) |
| 22 | qlib | kombi | 2006-2020 | trend_ok | 21 | 20 | 1.1% | 9.4% |  | 0.16 | -41.7% | knapp: CAGR<SPY (rueckgefuellt) |
| 22 | qlib | kombi | 2006-2020 | trend_ok | 21 | 40 | -0.7% | 9.4% |  | 0.06 | -43.8% | knapp: CAGR<SPY (rueckgefuellt) |
| 22 | qlib | kombi | 2006-2020 | trend_und_vix | 21 | 10 | 0.5% | 9.4% |  | 0.11 | -40.5% | knapp: CAGR<SPY (rueckgefuellt) |
| 22 | qlib | kombi | 2006-2020 | trend_und_vix | 21 | 20 | -0.4% | 9.4% |  | 0.07 | -41.4% | knapp: CAGR<SPY (rueckgefuellt) |
| 22 | qlib | kombi | 2006-2020 | trend_und_vix | 21 | 40 | -2.0% | 9.4% |  | -0.03 | -43.2% | knapp: CAGR<SPY (rueckgefuellt) |
| 22 | qlib | kombi_ohne_volumen | 2006-2020 | trend_ok | 21 | 10 | 3.9% | 9.4% |  | 0.28 | -41.3% | knapp: CAGR<SPY (rueckgefuellt) |
| 22 | qlib | kombi_ohne_volumen | 2006-2020 | trend_ok | 21 | 20 | 2.9% | 9.4% |  | 0.24 | -42.2% | knapp: CAGR<SPY (rueckgefuellt) |
| 22 | qlib | kombi_ohne_volumen | 2006-2020 | trend_und_vix | 21 | 10 | 1.3% | 9.4% |  | 0.17 | -40.2% | knapp: CAGR<SPY (rueckgefuellt) |
| 22 | qlib | kombi_ohne_volumen | 2006-2020 | trend_und_vix | 21 | 20 | 0.5% | 9.4% |  | 0.12 | -40.6% | knapp: CAGR<SPY (rueckgefuellt) |
| 22 | qlib | kurz | 2006-2020 | kein | 5 | 10 | 7.4% | 9.2% | 8.7% | 0.39 | -57.3% | knapp: DD>0,8xSPY (rueckgefuellt) |
| 22 | qlib | kurz10 | 2006-2020 | kein | 10 | 10 | 7.3% | 9.3% | 8.7% | 0.41 | -51.2% | knapp: DD>0,8xSPY (rueckgefuellt) |
| 22 | qlib | momentum | 2006-2020 | trend_ok | 21 | 20 | 7.4% | 9.4% | 8.7% | 0.45 | -36.5% | knapp: CAGR<SPY (rueckgefuellt) |
| 22 | qlib | reversal | 2006-2020 | kein | 5 | 10 | 10.0% | 9.2% | 8.4% | 0.44 | -72.7% | knapp: DD>0,8xSPY (rueckgefuellt) |
| 22 | sp500_close | kurz_preis | 2016-2026 | kein | 5 | 10 | 19.3% | 14.6% | 16.0% | 0.89 | -46.2% | knapp: DD>0,8xSPY (rueckgefuellt) |
| 22 | sp500_close | momentum | 2016-2026 | kein | 21 | 10 | 23.7% | 14.8% | 16.1% | 1.01 | -40.6% | knapp: DD>0,8xSPY (rueckgefuellt) |
| 22 | sp500_close | momentum | 2016-2026 | kein | 21 | 20 | 22.3% | 14.8% | 16.1% | 0.96 | -40.7% | knapp: DD>0,8xSPY (rueckgefuellt) |
| 22 | sp500_close | momentum | 2016-2026 | kein | 21 | 40 | 19.4% | 14.8% | 16.1% | 0.86 | -40.8% | knapp: DD>0,8xSPY (rueckgefuellt) |
| 22 | sp500_close | momentum | 2016-2026 | trend_ok | 21 | 10 | 15.5% | 14.8% | 16.1% | 0.88 | -29.2% | knapp: DD>0,8xSPY (rueckgefuellt) |
| 22 | sp500_close | momentum | 2016-2026 | trend_ok | 21 | 20 | 14.5% | 14.8% | 16.1% | 0.83 | -29.2% | knapp: DD>0,8xSPY (rueckgefuellt) |
| 22 | sp500_close | momentum | 2016-2026 | vix_ruhig | 21 | 20 | 13.7% | 14.8% | 16.1% | 0.79 | -25.6% | knapp: Auswahl<Universum (rueckgefuellt) |

## VERWORFEN (146)

| Skript | Panel | Variante | Zeitraum | Regime | H | Kosten | CAGR | SPY | Univ.EW | Sharpe | MaxDD | Lehre |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 22 | qlib | ranking | 2006-2020 | kein | 42 | 20 | 5.8% | 9.4% | 8.7% | 0.37 | -54.2% | CAGR<SPY, DD>0,8xSPY, Auswahl<Universum |
| 22 | qlib | ranking | 2006-2020 | trend_ok | 42 | 20 | 6.1% | 9.4% | 8.7% | 0.47 | -29.0% | CAGR<SPY, Auswahl<Universum |
| 22 | qlib | ranking | 2006-2020 | vix_ruhig | 42 | 20 | 2.4% | 9.4% | 8.7% | 0.23 | -39.6% | CAGR<SPY, Auswahl<Universum |
| 22 | qlib | ranking | 2006-2020 | trend_und_vix | 42 | 20 | 4.3% | 9.4% | 8.7% | 0.37 | -26.6% | CAGR<SPY, Auswahl<Universum |
| 22 | sp500_close | ranking_preis | 2016-2026 | trend_ok | 42 | 10 | 13.4% | 14.9% | 16.7% | 0.88 | -30.8% | DD>0,8xSPY, Auswahl<Universum |
| 22 | sp500_close | ranking_preis | 2016-2026 | trend_ok | 42 | 20 | 12.9% | 14.9% | 16.7% | 0.85 | -30.8% | CAGR<SPY, DD>0,8xSPY, Auswahl<Universum |
| 22 | sp500_close | ranking_preis | 2016-2026 | trend_ok | 42 | 40 | 11.9% | 14.9% | 16.7% | 0.79 | -30.9% | CAGR<SPY, DD>0,8xSPY, Auswahl<Universum |
| 22 | sp500_close | ranking_preis | 2016-2026 | vix_ruhig | 42 | 10 | 12.7% | 14.9% | 16.7% | 0.83 | -27.5% | CAGR<SPY, DD>0,8xSPY, Auswahl<Universum |
| 22 | sp500_close | ranking_preis | 2016-2026 | vix_ruhig | 42 | 20 | 12.1% | 14.9% | 16.7% | 0.80 | -27.5% | CAGR<SPY, DD>0,8xSPY, Auswahl<Universum |
| 22 | sp500_close | ranking_preis | 2016-2026 | vix_ruhig | 42 | 40 | 10.9% | 14.9% | 16.7% | 0.73 | -27.5% | CAGR<SPY, DD>0,8xSPY, Auswahl<Universum |
| 22 | sp500_close | ranking_preis | 2016-2026 | trend_und_vix | 42 | 10 | 11.1% | 14.9% | 16.7% | 0.81 | -27.5% | CAGR<SPY, DD>0,8xSPY, Auswahl<Universum |
| 22 | sp500_close | ranking_preis | 2016-2026 | trend_und_vix | 42 | 20 | 10.7% | 14.9% | 16.7% | 0.78 | -27.5% | CAGR<SPY, DD>0,8xSPY, Auswahl<Universum |
| 22 | sp500_close | ranking_preis | 2016-2026 | trend_und_vix | 42 | 40 | 9.7% | 14.9% | 16.7% | 0.72 | -27.5% | CAGR<SPY, DD>0,8xSPY, Auswahl<Universum |
| 22 | sp500_close | ranking_v2_preis | 2016-2026 | vix_ruhig | 42 | 40 | 14.5% | 14.9% | 16.7% | 0.80 | -31.1% | DD>0,8xSPY, Auswahl<Universum |
| 22 | sp500_close | ranking_v2_preis | 2016-2026 | trend_und_vix | 42 | 10 | 13.9% | 14.9% | 16.7% | 0.84 | -31.0% | DD>0,8xSPY, Auswahl<Universum |
| 22 | sp500_close | ranking_v2_preis | 2016-2026 | trend_und_vix | 42 | 20 | 13.4% | 14.9% | 16.7% | 0.81 | -31.1% | DD>0,8xSPY, Auswahl<Universum |
| 22 | sp500_close | ranking_v2_preis | 2016-2026 | trend_und_vix | 42 | 40 | 12.5% | 14.9% | 16.7% | 0.76 | -31.1% | CAGR<SPY, DD>0,8xSPY, Auswahl<Universum |
| 22 | qlib | ear | 2006-2020 | kein | 42 | 20 | 7.2% | 9.4% | 8.7% | 0.43 | -56.7% | CAGR<SPY, DD>0,8xSPY (rueckgefuellt) |
| 22 | qlib | ear | 2006-2020 | trend_ok | 42 | 20 | 4.2% | 9.4% | 8.7% | 0.39 | -31.4% | CAGR<SPY, Auswahl<Universum (rueckgefuellt) |
| 22 | qlib | ear | 2006-2020 | vix_ruhig | 42 | 20 | 1.5% | 9.4% | 8.7% | 0.18 | -37.2% | CAGR<SPY, Auswahl<Universum (rueckgefuellt) |
| 22 | qlib | ear | 2006-2020 | trend_und_vix | 42 | 20 | 2.4% | 9.4% | 8.7% | 0.25 | -31.1% | CAGR<SPY, Auswahl<Universum (rueckgefuellt) |
| 22 | qlib | kombi | 2006-2020 | kein | 21 | 10 | 1.5% | 9.4% |  | 0.19 | -52.5% | CAGR<SPY, DD>0,8xSPY (rueckgefuellt) |
| 22 | qlib | kombi | 2006-2020 | kein | 21 | 20 | 0.3% | 9.4% |  | 0.14 | -54.3% | CAGR<SPY, DD>0,8xSPY (rueckgefuellt) |
| 22 | qlib | kombi | 2006-2020 | kein | 21 | 40 | -2.0% | 9.4% |  | 0.04 | -62.6% | CAGR<SPY, DD>0,8xSPY (rueckgefuellt) |
| 22 | qlib | kombi | 2006-2020 | vix_ruhig | 21 | 10 | -0.9% | 9.4% |  | 0.05 | -45.5% | CAGR<SPY, DD>0,8xSPY (rueckgefuellt) |
| 22 | qlib | kombi | 2006-2020 | vix_ruhig | 21 | 20 | -1.9% | 9.4% |  | -0.00 | -46.9% | CAGR<SPY, DD>0,8xSPY (rueckgefuellt) |
| 22 | qlib | kombi | 2006-2020 | vix_ruhig | 21 | 40 | -3.8% | 9.4% |  | -0.10 | -55.6% | CAGR<SPY, DD>0,8xSPY (rueckgefuellt) |
| 22 | qlib | kombi2 | 2006-2020 | kein | 21 | 20 | 5.2% | 9.4% | 8.7% | 0.43 | -30.7% | CAGR<SPY, Auswahl<Universum (rueckgefuellt) |
| 22 | qlib | kombi2 | 2006-2020 | trend_ok | 21 | 20 | 5.2% | 9.4% | 8.7% | 0.49 | -18.3% | CAGR<SPY, Auswahl<Universum (rueckgefuellt) |
| 22 | qlib | kombi2 | 2006-2020 | vix_ruhig | 21 | 20 | 3.0% | 9.4% | 8.7% | 0.30 | -23.5% | CAGR<SPY, Auswahl<Universum (rueckgefuellt) |
| 22 | qlib | kombi2 | 2006-2020 | trend_und_vix | 21 | 20 | 3.6% | 9.4% | 8.7% | 0.37 | -18.0% | CAGR<SPY, Auswahl<Universum (rueckgefuellt) |
| 22 | qlib | kombi2_h42 | 2006-2020 | kein | 42 | 10 | 6.4% | 9.4% | 8.7% | 0.40 | -54.0% | CAGR<SPY, DD>0,8xSPY, Auswahl<Universum (rueckgefuellt) |
| 22 | qlib | kombi2_h42 | 2006-2020 | kein | 42 | 20 | 5.8% | 9.4% | 8.7% | 0.37 | -54.2% | CAGR<SPY, DD>0,8xSPY, Auswahl<Universum (rueckgefuellt) |
| 22 | qlib | kombi2_h42 | 2006-2020 | kein | 42 | 40 | 4.5% | 9.4% | 8.7% | 0.31 | -54.7% | CAGR<SPY, DD>0,8xSPY, Auswahl<Universum (rueckgefuellt) |
| 22 | qlib | kombi2_h42 | 2006-2020 | trend_ok | 42 | 10 | 6.6% | 9.4% | 8.7% | 0.50 | -28.5% | CAGR<SPY, Auswahl<Universum (rueckgefuellt) |
| 22 | qlib | kombi2_h42 | 2006-2020 | trend_ok | 42 | 20 | 6.1% | 9.4% | 8.7% | 0.47 | -29.0% | CAGR<SPY, Auswahl<Universum (rueckgefuellt) |
| 22 | qlib | kombi2_h42 | 2006-2020 | trend_ok | 42 | 40 | 5.1% | 9.4% | 8.7% | 0.41 | -30.0% | CAGR<SPY, Auswahl<Universum (rueckgefuellt) |
| 22 | qlib | kombi2_h42 | 2006-2020 | vix_ruhig | 42 | 10 | 2.9% | 9.4% | 8.7% | 0.26 | -39.4% | CAGR<SPY, Auswahl<Universum (rueckgefuellt) |
| 22 | qlib | kombi2_h42 | 2006-2020 | vix_ruhig | 42 | 20 | 2.4% | 9.4% | 8.7% | 0.23 | -39.6% | CAGR<SPY, Auswahl<Universum (rueckgefuellt) |
| 22 | qlib | kombi2_h42 | 2006-2020 | vix_ruhig | 42 | 40 | 1.4% | 9.4% | 8.7% | 0.17 | -40.1% | CAGR<SPY, Auswahl<Universum (rueckgefuellt) |
| 22 | qlib | kombi2_h42 | 2006-2020 | trend_und_vix | 42 | 10 | 4.7% | 9.4% | 8.7% | 0.40 | -26.1% | CAGR<SPY, Auswahl<Universum (rueckgefuellt) |
| 22 | qlib | kombi2_h42 | 2006-2020 | trend_und_vix | 42 | 20 | 4.3% | 9.4% | 8.7% | 0.37 | -26.6% | CAGR<SPY, Auswahl<Universum (rueckgefuellt) |
| 22 | qlib | kombi2_h42 | 2006-2020 | trend_und_vix | 42 | 40 | 3.4% | 9.4% | 8.7% | 0.31 | -27.6% | CAGR<SPY, Auswahl<Universum (rueckgefuellt) |
| 22 | qlib | kombi_ohne_volumen | 2006-2020 | kein | 21 | 10 | 1.3% | 9.4% |  | 0.19 | -67.5% | CAGR<SPY, DD>0,8xSPY (rueckgefuellt) |
| 22 | qlib | kombi_ohne_volumen | 2006-2020 | kein | 21 | 20 | 0.1% | 9.4% |  | 0.15 | -68.0% | CAGR<SPY, DD>0,8xSPY (rueckgefuellt) |
| 22 | qlib | kombi_ohne_volumen | 2006-2020 | kein | 21 | 40 | -2.3% | 9.4% |  | 0.06 | -71.2% | CAGR<SPY, DD>0,8xSPY (rueckgefuellt) |
| 22 | qlib | kombi_ohne_volumen | 2006-2020 | trend_ok | 21 | 40 | 1.1% | 9.4% |  | 0.16 | -48.8% | CAGR<SPY, DD>0,8xSPY (rueckgefuellt) |
| 22 | qlib | kombi_ohne_volumen | 2006-2020 | vix_ruhig | 21 | 10 | -0.9% | 9.4% |  | 0.07 | -49.5% | CAGR<SPY, DD>0,8xSPY (rueckgefuellt) |
| 22 | qlib | kombi_ohne_volumen | 2006-2020 | vix_ruhig | 21 | 20 | -1.8% | 9.4% |  | 0.02 | -50.0% | CAGR<SPY, DD>0,8xSPY (rueckgefuellt) |
| 22 | qlib | kombi_ohne_volumen | 2006-2020 | vix_ruhig | 21 | 40 | -3.7% | 9.4% |  | -0.07 | -54.6% | CAGR<SPY, DD>0,8xSPY (rueckgefuellt) |
| 22 | qlib | kombi_ohne_volumen | 2006-2020 | trend_und_vix | 21 | 40 | -1.1% | 9.4% |  | 0.04 | -47.6% | CAGR<SPY, DD>0,8xSPY (rueckgefuellt) |
| 22 | qlib | kurz | 2006-2020 | kein | 5 | 20 | 2.1% | 9.2% | 8.7% | 0.22 | -68.0% | CAGR<SPY, DD>0,8xSPY, Auswahl<Universum (rueckgefuellt) |
| 22 | qlib | kurz | 2006-2020 | kein | 5 | 40 | -7.6% | 9.2% | 8.7% | -0.14 | -86.4% | CAGR<SPY, DD>0,8xSPY, Auswahl<Universum (rueckgefuellt) |
| 22 | qlib | kurz | 2006-2020 | trend_ok | 5 | 10 | -0.6% | 9.2% | 8.7% | 0.04 | -37.4% | CAGR<SPY, Auswahl<Universum (rueckgefuellt) |
| 22 | qlib | kurz | 2006-2020 | trend_ok | 5 | 20 | -4.3% | 9.2% | 8.7% | -0.21 | -57.9% | CAGR<SPY, DD>0,8xSPY, Auswahl<Universum (rueckgefuellt) |
| 22 | qlib | kurz | 2006-2020 | trend_ok | 5 | 40 | -11.2% | 9.2% | 8.7% | -0.70 | -84.8% | CAGR<SPY, DD>0,8xSPY, Auswahl<Universum (rueckgefuellt) |
| 22 | qlib | kurz | 2006-2020 | vix_ruhig | 5 | 10 | -3.9% | 9.2% | 8.7% | -0.16 | -55.2% | CAGR<SPY, DD>0,8xSPY, Auswahl<Universum (rueckgefuellt) |
| 22 | qlib | kurz | 2006-2020 | vix_ruhig | 5 | 20 | -7.7% | 9.2% | 8.7% | -0.40 | -72.9% | CAGR<SPY, DD>0,8xSPY, Auswahl<Universum (rueckgefuellt) |
| 22 | qlib | kurz | 2006-2020 | vix_ruhig | 5 | 40 | -15.0% | 9.2% | 8.7% | -0.89 | -91.4% | CAGR<SPY, DD>0,8xSPY, Auswahl<Universum (rueckgefuellt) |
| 22 | qlib | kurz | 2006-2020 | trend_und_vix | 5 | 10 | -1.6% | 9.2% | 8.7% | -0.05 | -38.6% | CAGR<SPY, Auswahl<Universum (rueckgefuellt) |
| 22 | qlib | kurz | 2006-2020 | trend_und_vix | 5 | 20 | -4.9% | 9.2% | 8.7% | -0.30 | -60.2% | CAGR<SPY, DD>0,8xSPY, Auswahl<Universum (rueckgefuellt) |
| 22 | qlib | kurz | 2006-2020 | trend_und_vix | 5 | 40 | -11.3% | 9.2% | 8.7% | -0.80 | -84.1% | CAGR<SPY, DD>0,8xSPY, Auswahl<Universum (rueckgefuellt) |
| 22 | qlib | kurz10 | 2006-2020 | kein | 10 | 20 | 4.6% | 9.3% | 8.7% | 0.31 | -52.7% | CAGR<SPY, DD>0,8xSPY, Auswahl<Universum (rueckgefuellt) |
| 22 | qlib | kurz10 | 2006-2020 | kein | 10 | 40 | -0.5% | 9.3% | 8.7% | 0.11 | -57.5% | CAGR<SPY, DD>0,8xSPY, Auswahl<Universum (rueckgefuellt) |
| 22 | qlib | kurz10 | 2006-2020 | trend_ok | 10 | 10 | 4.0% | 9.3% | 8.7% | 0.35 | -30.0% | CAGR<SPY, Auswahl<Universum (rueckgefuellt) |
| 22 | qlib | kurz10 | 2006-2020 | trend_ok | 10 | 20 | 2.0% | 9.3% | 8.7% | 0.21 | -32.1% | CAGR<SPY, Auswahl<Universum (rueckgefuellt) |
| 22 | qlib | kurz10 | 2006-2020 | trend_ok | 10 | 40 | -1.7% | 9.3% | 8.7% | -0.05 | -43.7% | CAGR<SPY, Auswahl<Universum (rueckgefuellt) |
| 22 | qlib | kurz10 | 2006-2020 | vix_ruhig | 10 | 10 | 1.3% | 9.3% | 8.7% | 0.16 | -33.7% | CAGR<SPY, Auswahl<Universum (rueckgefuellt) |
| 22 | qlib | kurz10 | 2006-2020 | vix_ruhig | 10 | 20 | -0.8% | 9.3% | 8.7% | 0.02 | -35.8% | CAGR<SPY, Auswahl<Universum (rueckgefuellt) |
| 22 | qlib | kurz10 | 2006-2020 | vix_ruhig | 10 | 40 | -4.7% | 9.3% | 8.7% | -0.25 | -53.8% | CAGR<SPY, DD>0,8xSPY, Auswahl<Universum (rueckgefuellt) |
| 22 | qlib | kurz10 | 2006-2020 | trend_und_vix | 10 | 10 | 2.8% | 9.3% | 8.7% | 0.28 | -20.0% | CAGR<SPY, Auswahl<Universum (rueckgefuellt) |
| 22 | qlib | kurz10 | 2006-2020 | trend_und_vix | 10 | 20 | 1.0% | 9.3% | 8.7% | 0.14 | -21.3% | CAGR<SPY, Auswahl<Universum (rueckgefuellt) |
| 22 | qlib | kurz10 | 2006-2020 | trend_und_vix | 10 | 40 | -2.4% | 9.3% | 8.7% | -0.13 | -37.9% | CAGR<SPY, Auswahl<Universum (rueckgefuellt) |
| 22 | qlib | momentum | 2006-2020 | kein | 21 | 10 | 6.1% | 9.4% | 8.7% | 0.35 | -57.5% | CAGR<SPY, DD>0,8xSPY, Auswahl<Universum (rueckgefuellt) |
| 22 | qlib | momentum | 2006-2020 | kein | 21 | 20 | 4.8% | 9.4% | 8.7% | 0.31 | -58.0% | CAGR<SPY, DD>0,8xSPY, Auswahl<Universum (rueckgefuellt) |
| 22 | qlib | momentum | 2006-2020 | kein | 21 | 40 | 2.4% | 9.4% | 8.7% | 0.22 | -59.1% | CAGR<SPY, DD>0,8xSPY, Auswahl<Universum (rueckgefuellt) |
| 22 | qlib | momentum | 2006-2020 | trend_ok | 21 | 40 | 5.4% | 9.4% | 8.7% | 0.36 | -39.1% | CAGR<SPY, Auswahl<Universum (rueckgefuellt) |
| 22 | qlib | momentum | 2006-2020 | vix_ruhig | 21 | 10 | 2.8% | 9.4% | 8.7% | 0.24 | -43.2% | CAGR<SPY, Auswahl<Universum (rueckgefuellt) |
| 22 | qlib | momentum | 2006-2020 | vix_ruhig | 21 | 20 | 1.9% | 9.4% | 8.7% | 0.19 | -43.8% | CAGR<SPY, Auswahl<Universum (rueckgefuellt) |
| 22 | qlib | momentum | 2006-2020 | vix_ruhig | 21 | 40 | -0.1% | 9.4% | 8.7% | 0.10 | -44.8% | CAGR<SPY, DD>0,8xSPY, Auswahl<Universum (rueckgefuellt) |
| 22 | qlib | momentum | 2006-2020 | trend_und_vix | 21 | 10 | 5.4% | 9.4% | 8.7% | 0.38 | -34.1% | CAGR<SPY, Auswahl<Universum (rueckgefuellt) |
| 22 | qlib | momentum | 2006-2020 | trend_und_vix | 21 | 20 | 4.6% | 9.4% | 8.7% | 0.34 | -35.6% | CAGR<SPY, Auswahl<Universum (rueckgefuellt) |
| 22 | qlib | momentum | 2006-2020 | trend_und_vix | 21 | 40 | 2.8% | 9.4% | 8.7% | 0.25 | -38.4% | CAGR<SPY, Auswahl<Universum (rueckgefuellt) |
| 22 | qlib | reversal | 2006-2020 | kein | 5 | 20 | 4.7% | 9.2% | 8.4% | 0.30 | -76.0% | CAGR<SPY, DD>0,8xSPY, Auswahl<Universum (rueckgefuellt) |
| 22 | qlib | reversal | 2006-2020 | kein | 5 | 40 | -5.3% | 9.2% | 8.4% | 0.03 | -87.5% | CAGR<SPY, DD>0,8xSPY, Auswahl<Universum (rueckgefuellt) |
| 22 | qlib | reversal | 2006-2020 | trend_ok | 5 | 10 | -3.5% | 9.2% | 8.4% | -0.07 | -60.3% | CAGR<SPY, DD>0,8xSPY, Auswahl<Universum (rueckgefuellt) |
| 22 | qlib | reversal | 2006-2020 | trend_ok | 5 | 20 | -7.1% | 9.2% | 8.4% | -0.26 | -73.4% | CAGR<SPY, DD>0,8xSPY, Auswahl<Universum (rueckgefuellt) |
| 22 | qlib | reversal | 2006-2020 | trend_ok | 5 | 40 | -13.8% | 9.2% | 8.4% | -0.62 | -90.9% | CAGR<SPY, DD>0,8xSPY, Auswahl<Universum (rueckgefuellt) |
| 22 | qlib | reversal | 2006-2020 | vix_ruhig | 5 | 10 | -6.9% | 9.2% | 8.4% | -0.22 | -74.5% | CAGR<SPY, DD>0,8xSPY, Auswahl<Universum (rueckgefuellt) |
| 22 | qlib | reversal | 2006-2020 | vix_ruhig | 5 | 20 | -10.6% | 9.2% | 8.4% | -0.41 | -84.9% | CAGR<SPY, DD>0,8xSPY, Auswahl<Universum (rueckgefuellt) |
| 22 | qlib | reversal | 2006-2020 | vix_ruhig | 5 | 40 | -17.7% | 9.2% | 8.4% | -0.78 | -94.9% | CAGR<SPY, DD>0,8xSPY, Auswahl<Universum (rueckgefuellt) |
| 22 | qlib | reversal | 2006-2020 | trend_und_vix | 5 | 10 | -4.7% | 9.2% | 8.4% | -0.16 | -60.1% | CAGR<SPY, DD>0,8xSPY, Auswahl<Universum (rueckgefuellt) |
| 22 | qlib | reversal | 2006-2020 | trend_und_vix | 5 | 20 | -7.9% | 9.2% | 8.4% | -0.34 | -74.9% | CAGR<SPY, DD>0,8xSPY, Auswahl<Universum (rueckgefuellt) |
| 22 | qlib | reversal | 2006-2020 | trend_und_vix | 5 | 40 | -14.0% | 9.2% | 8.4% | -0.71 | -90.3% | CAGR<SPY, DD>0,8xSPY, Auswahl<Universum (rueckgefuellt) |
| 22 | qlib | reversal_rein | 2006-2020 | kein | 5 | 10 | 6.5% | 9.2% | 8.7% | 0.36 | -66.8% | CAGR<SPY, DD>0,8xSPY, Auswahl<Universum (rueckgefuellt) |
| 22 | qlib | reversal_rein | 2006-2020 | kein | 5 | 20 | 1.3% | 9.2% | 8.7% | 0.19 | -74.9% | CAGR<SPY, DD>0,8xSPY, Auswahl<Universum (rueckgefuellt) |
| 22 | qlib | reversal_rein | 2006-2020 | kein | 5 | 40 | -8.4% | 9.2% | 8.7% | -0.16 | -91.4% | CAGR<SPY, DD>0,8xSPY, Auswahl<Universum (rueckgefuellt) |
| 22 | qlib | reversal_rein | 2006-2020 | trend_ok | 5 | 10 | -2.3% | 9.2% | 8.7% | -0.07 | -54.5% | CAGR<SPY, DD>0,8xSPY, Auswahl<Universum (rueckgefuellt) |
| 22 | qlib | reversal_rein | 2006-2020 | trend_ok | 5 | 20 | -5.9% | 9.2% | 8.7% | -0.32 | -70.2% | CAGR<SPY, DD>0,8xSPY, Auswahl<Universum (rueckgefuellt) |
| 22 | qlib | reversal_rein | 2006-2020 | trend_ok | 5 | 40 | -12.7% | 9.2% | 8.7% | -0.81 | -89.3% | CAGR<SPY, DD>0,8xSPY, Auswahl<Universum (rueckgefuellt) |
| 22 | qlib | reversal_rein | 2006-2020 | vix_ruhig | 5 | 10 | -6.7% | 9.2% | 8.7% | -0.34 | -71.2% | CAGR<SPY, DD>0,8xSPY, Auswahl<Universum (rueckgefuellt) |
| 22 | qlib | reversal_rein | 2006-2020 | vix_ruhig | 5 | 20 | -10.4% | 9.2% | 8.7% | -0.59 | -83.0% | CAGR<SPY, DD>0,8xSPY, Auswahl<Universum (rueckgefuellt) |
| 22 | qlib | reversal_rein | 2006-2020 | vix_ruhig | 5 | 40 | -17.4% | 9.2% | 8.7% | -1.09 | -94.6% | CAGR<SPY, DD>0,8xSPY, Auswahl<Universum (rueckgefuellt) |
| 22 | qlib | reversal_rein | 2006-2020 | trend_und_vix | 5 | 10 | -4.1% | 9.2% | 8.7% | -0.24 | -55.3% | CAGR<SPY, DD>0,8xSPY, Auswahl<Universum (rueckgefuellt) |
| 22 | qlib | reversal_rein | 2006-2020 | trend_und_vix | 5 | 20 | -7.4% | 9.2% | 8.7% | -0.50 | -72.1% | CAGR<SPY, DD>0,8xSPY, Auswahl<Universum (rueckgefuellt) |
| 22 | qlib | reversal_rein | 2006-2020 | trend_und_vix | 5 | 40 | -13.6% | 9.2% | 8.7% | -1.01 | -89.4% | CAGR<SPY, DD>0,8xSPY, Auswahl<Universum (rueckgefuellt) |
| 22 | qlib | ruhig | 2006-2020 | kein | 42 | 10 | 5.1% | 9.4% | 8.7% | 0.33 | -56.4% | CAGR<SPY, DD>0,8xSPY, Auswahl<Universum (rueckgefuellt) |
| 22 | qlib | ruhig | 2006-2020 | kein | 42 | 20 | 4.5% | 9.4% | 8.7% | 0.31 | -56.6% | CAGR<SPY, DD>0,8xSPY, Auswahl<Universum (rueckgefuellt) |
| 22 | qlib | ruhig | 2006-2020 | kein | 42 | 40 | 3.4% | 9.4% | 8.7% | 0.26 | -57.2% | CAGR<SPY, DD>0,8xSPY, Auswahl<Universum (rueckgefuellt) |
| 22 | qlib | ruhig | 2006-2020 | trend_ok | 42 | 10 | 3.8% | 9.4% | 8.7% | 0.33 | -38.5% | CAGR<SPY, Auswahl<Universum (rueckgefuellt) |
| 22 | qlib | ruhig | 2006-2020 | trend_ok | 42 | 20 | 3.4% | 9.4% | 8.7% | 0.30 | -39.1% | CAGR<SPY, Auswahl<Universum (rueckgefuellt) |
| 22 | qlib | ruhig | 2006-2020 | trend_ok | 42 | 40 | 2.5% | 9.4% | 8.7% | 0.24 | -40.4% | CAGR<SPY, Auswahl<Universum (rueckgefuellt) |
| 22 | qlib | ruhig | 2006-2020 | vix_ruhig | 42 | 10 | -0.3% | 9.4% | 8.7% | 0.05 | -39.0% | CAGR<SPY, Auswahl<Universum (rueckgefuellt) |
| 22 | qlib | ruhig | 2006-2020 | vix_ruhig | 42 | 20 | -0.8% | 9.4% | 8.7% | 0.03 | -39.3% | CAGR<SPY, Auswahl<Universum (rueckgefuellt) |
| 22 | qlib | ruhig | 2006-2020 | vix_ruhig | 42 | 40 | -1.7% | 9.4% | 8.7% | -0.03 | -39.9% | CAGR<SPY, Auswahl<Universum (rueckgefuellt) |
| 22 | qlib | ruhig | 2006-2020 | trend_und_vix | 42 | 10 | 1.7% | 9.4% | 8.7% | 0.19 | -35.5% | CAGR<SPY, Auswahl<Universum (rueckgefuellt) |
| 22 | qlib | ruhig | 2006-2020 | trend_und_vix | 42 | 20 | 1.3% | 9.4% | 8.7% | 0.16 | -36.1% | CAGR<SPY, Auswahl<Universum (rueckgefuellt) |
| 22 | qlib | ruhig | 2006-2020 | trend_und_vix | 42 | 40 | 0.5% | 9.4% | 8.7% | 0.11 | -37.5% | CAGR<SPY, Auswahl<Universum (rueckgefuellt) |
| 22 | qlib | volumen | 2006-2020 | kein | 21 | 10 | 2.2% | 9.4% |  | 0.21 | -53.8% | CAGR<SPY, DD>0,8xSPY (rueckgefuellt) |
| 22 | qlib | volumen | 2006-2020 | kein | 21 | 20 | 1.0% | 9.4% |  | 0.16 | -54.4% | CAGR<SPY, DD>0,8xSPY (rueckgefuellt) |
| 22 | qlib | volumen | 2006-2020 | kein | 21 | 40 | -1.4% | 9.4% |  | 0.05 | -58.6% | CAGR<SPY, DD>0,8xSPY (rueckgefuellt) |
| 22 | qlib | volumen | 2006-2020 | trend_ok | 21 | 10 | -0.4% | 9.4% |  | 0.04 | -46.0% | CAGR<SPY, DD>0,8xSPY (rueckgefuellt) |
| 22 | qlib | volumen | 2006-2020 | trend_ok | 21 | 20 | -1.3% | 9.4% |  | -0.03 | -48.0% | CAGR<SPY, DD>0,8xSPY (rueckgefuellt) |
| 22 | qlib | volumen | 2006-2020 | trend_ok | 21 | 40 | -3.1% | 9.4% |  | -0.16 | -55.1% | CAGR<SPY, DD>0,8xSPY (rueckgefuellt) |
| 22 | qlib | volumen | 2006-2020 | vix_ruhig | 21 | 10 | -3.4% | 9.4% |  | -0.17 | -49.5% | CAGR<SPY, DD>0,8xSPY (rueckgefuellt) |
| 22 | qlib | volumen | 2006-2020 | vix_ruhig | 21 | 20 | -4.4% | 9.4% |  | -0.23 | -55.5% | CAGR<SPY, DD>0,8xSPY (rueckgefuellt) |
| 22 | qlib | volumen | 2006-2020 | vix_ruhig | 21 | 40 | -6.2% | 9.4% |  | -0.37 | -65.5% | CAGR<SPY, DD>0,8xSPY (rueckgefuellt) |
| 22 | qlib | volumen | 2006-2020 | trend_und_vix | 21 | 10 | -1.7% | 9.4% |  | -0.07 | -45.3% | CAGR<SPY, DD>0,8xSPY (rueckgefuellt) |
| 22 | qlib | volumen | 2006-2020 | trend_und_vix | 21 | 20 | -2.5% | 9.4% |  | -0.14 | -47.5% | CAGR<SPY, DD>0,8xSPY (rueckgefuellt) |
| 22 | qlib | volumen | 2006-2020 | trend_und_vix | 21 | 40 | -4.1% | 9.4% |  | -0.27 | -55.0% | CAGR<SPY, DD>0,8xSPY (rueckgefuellt) |
| 22 | sp500_close | kurz_preis | 2016-2026 | kein | 5 | 20 | 13.5% | 14.6% | 16.0% | 0.67 | -46.4% | DD>0,8xSPY, Auswahl<Universum (rueckgefuellt) |
| 22 | sp500_close | kurz_preis | 2016-2026 | kein | 5 | 40 | 2.7% | 14.6% | 16.0% | 0.23 | -52.3% | CAGR<SPY, DD>0,8xSPY, Auswahl<Universum (rueckgefuellt) |
| 22 | sp500_close | kurz_preis | 2016-2026 | trend_ok | 5 | 10 | 10.5% | 14.6% | 16.0% | 0.75 | -22.9% | CAGR<SPY, Auswahl<Universum (rueckgefuellt) |
| 22 | sp500_close | kurz_preis | 2016-2026 | trend_ok | 5 | 20 | 6.5% | 14.6% | 16.0% | 0.50 | -24.3% | CAGR<SPY, Auswahl<Universum (rueckgefuellt) |
| 22 | sp500_close | kurz_preis | 2016-2026 | trend_ok | 5 | 40 | -1.1% | 14.6% | 16.0% | -0.01 | -33.2% | CAGR<SPY, DD>0,8xSPY, Auswahl<Universum (rueckgefuellt) |
| 22 | sp500_close | kurz_preis | 2016-2026 | vix_ruhig | 5 | 10 | 10.0% | 14.6% | 16.0% | 0.72 | -22.5% | CAGR<SPY, Auswahl<Universum (rueckgefuellt) |
| 22 | sp500_close | kurz_preis | 2016-2026 | vix_ruhig | 5 | 20 | 5.4% | 14.6% | 16.0% | 0.43 | -25.4% | CAGR<SPY, Auswahl<Universum (rueckgefuellt) |
| 22 | sp500_close | kurz_preis | 2016-2026 | vix_ruhig | 5 | 40 | -3.2% | 14.6% | 16.0% | -0.15 | -44.8% | CAGR<SPY, DD>0,8xSPY, Auswahl<Universum (rueckgefuellt) |
| 22 | sp500_close | kurz_preis | 2016-2026 | trend_und_vix | 5 | 10 | 7.2% | 14.6% | 16.0% | 0.60 | -22.5% | CAGR<SPY, Auswahl<Universum (rueckgefuellt) |
| 22 | sp500_close | kurz_preis | 2016-2026 | trend_und_vix | 5 | 20 | 3.5% | 14.6% | 16.0% | 0.33 | -24.2% | CAGR<SPY, Auswahl<Universum (rueckgefuellt) |
| 22 | sp500_close | kurz_preis | 2016-2026 | trend_und_vix | 5 | 40 | -3.3% | 14.6% | 16.0% | -0.20 | -44.3% | CAGR<SPY, DD>0,8xSPY, Auswahl<Universum (rueckgefuellt) |
| 22 | sp500_close | momentum | 2016-2026 | trend_ok | 21 | 40 | 12.5% | 14.8% | 16.1% | 0.74 | -29.3% | CAGR<SPY, DD>0,8xSPY, Auswahl<Universum (rueckgefuellt) |
| 22 | sp500_close | momentum | 2016-2026 | vix_ruhig | 21 | 40 | 11.4% | 14.8% | 16.1% | 0.68 | -26.2% | CAGR<SPY, Auswahl<Universum (rueckgefuellt) |
| 22 | sp500_close | momentum | 2016-2026 | trend_und_vix | 21 | 10 | 12.5% | 14.8% | 16.1% | 0.80 | -22.6% | CAGR<SPY, Auswahl<Universum (rueckgefuellt) |
| 22 | sp500_close | momentum | 2016-2026 | trend_und_vix | 21 | 20 | 11.5% | 14.8% | 16.1% | 0.75 | -22.7% | CAGR<SPY, Auswahl<Universum (rueckgefuellt) |
| 22 | sp500_close | momentum | 2016-2026 | trend_und_vix | 21 | 40 | 9.7% | 14.8% | 16.1% | 0.65 | -22.9% | CAGR<SPY, Auswahl<Universum (rueckgefuellt) |
