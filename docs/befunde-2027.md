# Befundregister 2027 — jeder Lauf, jedes Urteil

> Automatisch erzeugt aus `results/labor/befunde.jsonl` am 2026-09-29 14:49 UTC. **265 Befunde, 105 unterschiedliche Varianten → Zufallsschwelle 3.55 Sigma.** Ein t-Wert darunter ist kein Fund.

Nichts hier wird gelöscht. Verworfene Zeilen sind die wertvollsten: Sie sagen,
was nicht noch einmal probiert werden muss.

## BESTANDEN (10)

| Skript | Panel | Variante | Zeitraum | Regime | H | Kosten | CAGR | SPY | Univ.EW | Sharpe | MaxDD | Lehre |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 22 | qlib | momentum | 2006-2020 | trend_ok | 21 | 10 | 8.3% | 9.4% | 8.7% | 0.50 | -35.5% | CAGR >= SPY, Drawdown <= 0,8 x SPY, Auswahl >= Universum (rueckgefuellt) |
| 22 | sp500_close | momentum | 2016-2026 | vix_ruhig | 21 | 10 | 14.8% | 14.8% | 16.1% | 0.84 | -25.4% | CAGR >= SPY, Drawdown <= 0,8 x SPY, Auswahl >= Universum (rueckgefuellt) |
| 22 | sp500_close | ranking_preis | 2016-2026 | kein | 42 | 20 | 15.7% | 14.9% | 16.7% | 0.99 | -20.2% | CAGR >= SPY, Drawdown <= 0,8 x SPY, Auswahl >= Universum |
| 22 | sp500_close | ranking_preis | 2016-2026 | kein | 42 | 20 | 16.8% | 14.9% | 16.7% | 0.99 | -22.9% | CAGR >= SPY, Drawdown <= 0,8 x SPY, Auswahl >= Universum |
| 29 | qlib | fest_h5 | 2009-2020 | kein | 5 | 20 | 13.5% | 9.3% |  | 0.64 | -38.3% | CAGR >= SPY, Drawdown <= 0,8 x SPY, Auswahl >= Universum; LightGBM je Horizont, Top 30, ohne Regime. CAGR 13.5% ueber 2006-2020 inkl. 3 Nulljahren = 17.2% ueber 2009-2020.  |
| 35 | qlib | hybrid_vola25 | 2009-2020 | kein | 21 | 20 | 14.0% | 14.5% | 13.9% | 0.71 | -30.0% | ML-Variante aus gespeicherten Vorhersagen; gegen momentum_trend +3.8%; MaxDD -30.0% |
| 31 | qlib | ranking_engine | 2006-2020 | trend_ok | 21-63 | 20 | 8.7% | 9.3% |  | 0.61 | -34.1% | CAGR >= SPY, Drawdown <= 0,8 x SPY, Auswahl >= Universum; Ausstiege {'stop_intraday': 820, 'zeitausstieg': 546, 'rangverlust': 511} |
| 31 | qlib | ranking_engine | 2006-2020 | trend_ok | 21-63 | 20 | 13.0% | 9.3% |  | 0.80 | -35.3% | CAGR >= SPY, Drawdown <= 0,8 x SPY, Auswahl >= Universum; Ausstiege {'zeitausstieg': 750, 'rangverlust': 713} |
| 22 | qlib | ranking_v2 | 2006-2020 | trend_ok | 42 | 10 | 7.7% | 9.4% | 8.7% | 0.47 | -39.7% | CAGR >= SPY, Drawdown <= 0,8 x SPY, Auswahl >= Universum |
| 31 | sp500_close | ranking_engine | 2016-2026 | trend_ok | 21-63 | 20 | 13.3% | 14.7% |  | 0.85 | -23.8% | CAGR >= SPY, Drawdown <= 0,8 x SPY, Auswahl >= Universum; Ausstiege {'stop_intraday': 1742, 'zeitausstieg': 813, 'rangverlust': 241, 'gewinnziel_erreicht': 2} |

## KANDIDAT (72)

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
| 33 | qlib | autopsie | 2010-2020 | nan | nan |  |  |  |  |  |  | Ausstieg 'stop_intraday' traegt 42% der Trades bei Oe -7.6% (Treffer 0%, Oe 16 Tage); 'zeitausstieg' dagegen Oe +13.2%. Pruefen: verkauft diese Regel NACH dem Verlust statt vor ihm (verspaeteter Stop)?. / Rendite steigt mit der Haltedauer (<=10: -7.8% -> 43-63: +10.4%): die fruehen Ausstiege sind die Verlierer - die Kostenkurve aus 24_ zeigt sich auch im Engine-Pfad. / Score-Quartil innerhalb der Kaufmenge ohne Wirkung (oben minus unten -0.96%): keine Konzentration auf die Top 10, die Rangschwelle reicht. / Verlustjahre nach Einstiegsjahr: 2015 (-1.6%, n=148), 2018 (-1.2%, n=188) - gegen SPY-Jahr und Regime-Tor pruefen. / Investitionsgrad (zu Einstandskursen) Mittel 79%, Median 87%, Tage unter 50 %: 13% - Cash-Bremse ist kein Haupthebel. / Einstiegsmonat: bester 5 (+4.2%), schlechtester 3 (-1.3%) - nur Notiz: 11 Jahre sind fuer Saisonregeln zu duenn (Versuchszaehler!). |
| 33 | qlib | autopsie | 2010-2020 | nan | nan |  |  |  |  |  |  | Ausstieg 'rangverlust' traegt 68% der Trades bei Oe -2.1% (Treffer 42%, Oe 30 Tage); 'zeitausstieg' dagegen Oe +9.0%. Pruefen: verkauft diese Regel NACH dem Verlust statt vor ihm (verspaeteter Stop)?. / Rendite steigt mit der Haltedauer (11-21: -4.9% -> 43-63: +6.4%): die fruehen Ausstiege sind die Verlierer - die Kostenkurve aus 24_ zeigt sich auch im Engine-Pfad. / Score-Quartil wirkt (-1.68% oben minus unten): engere Rangschwelle testen. / Verlustjahre nach Einstiegsjahr: 2015 (-2.1%, n=120), 2018 (-2.2%, n=147), 2020 (-0.4%, n=86) - gegen SPY-Jahr und Regime-Tor pruefen. / Investitionsgrad (zu Einstandskursen) Mittel 81%, Median 89%, Tage unter 50 %: 13% - Cash-Bremse ist kein Haupthebel. / Einstiegsmonat: bester 5 (+6.5%), schlechtester 3 (-3.2%) - nur Notiz: 11 Jahre sind fuer Saisonregeln zu duenn (Versuchszaehler!). |
| 33 | sp500_close | autopsie | 2017-2026 | nan | nan |  |  |  |  |  |  | Ausstieg 'stop_intraday' traegt 60% der Trades bei Oe -5.4% (Treffer 0%, Oe 14 Tage); 'gewinnziel_erreicht' dagegen Oe +192.8%. Pruefen: verkauft diese Regel NACH dem Verlust statt vor ihm (verspaeteter Stop)?. / Rendite steigt mit der Haltedauer (<=10: -4.8% -> 43-63: +11.6%): die fruehen Ausstiege sind die Verlierer - die Kostenkurve aus 24_ zeigt sich auch im Engine-Pfad. / Score-Quartil wirkt (+1.09% oben minus unten): engere Rangschwelle testen. / Verlustjahre nach Einstiegsjahr: 2018 (-1.1%, n=397), 2022 (-1.1%, n=307), 2026 (-0.7%, n=239) - gegen SPY-Jahr und Regime-Tor pruefen. / Investitionsgrad (zu Einstandskursen) Mittel 84%, Median 89%, Tage unter 50 %: 15% - Cash-Bremse ist kein Haupthebel. / Einstiegsmonat: bester 4 (+4.5%), schlechtester 1 (-0.3%) - nur Notiz: 10 Jahre sind fuer Saisonregeln zu duenn (Versuchszaehler!). |
| 33 | sp500_close | autopsie | 2017-2026 | nan | nan |  |  |  |  |  |  | Ausstieg 'rangverlust' traegt 57% der Trades bei Oe -2.3% (Treffer 39%, Oe 32 Tage); 'gewinnziel_erreicht' dagegen Oe +189.6%. Pruefen: verkauft diese Regel NACH dem Verlust statt vor ihm (verspaeteter Stop)?. / Rendite steigt mit der Haltedauer (<=10: -30.3% -> 43-63: +6.8%): die fruehen Ausstiege sind die Verlierer - die Kostenkurve aus 24_ zeigt sich auch im Engine-Pfad. / Score-Quartil innerhalb der Kaufmenge ohne Wirkung (oben minus unten +0.31%): keine Konzentration auf die Top 10, die Rangschwelle reicht. / Verlustjahre nach Einstiegsjahr: 2018 (-1.1%, n=261), 2022 (-1.7%, n=209) - gegen SPY-Jahr und Regime-Tor pruefen. / Investitionsgrad (zu Einstandskursen) Mittel 86%, Median 90%, Tage unter 50 %: 13% - Cash-Bremse ist kein Haupthebel. / Einstiegsmonat: bester 4 (+7.5%), schlechtester 3 (-0.8%) - nur Notiz: 10 Jahre sind fuer Saisonregeln zu duenn (Versuchszaehler!). |
| 23 | qlib | ml_lgbm_h21 | 2009-2020 | kein | 21 | 20 | 15.7% | 14.5% | 13.2% | 0.70 | -40.6% | knapp: DD>0,8xSPY; OOS-IC +0,030 = bester Einzelfaktor (mom_12_1_vola), Portfolio aber +5 Punkte ueber Handmix (ranking kein 10,4 %, momentum 9,2 %): Staerke sitzt im oberen Rand, nicht im IC. Wichtigkeit vol_schub_6m_neg > vola_niedrig > mom_12_1_vola. Ohne Regime-Tor, MaxDD -40,6 %. Zweites Panel offen. |
| 31 | sp500_close | ranking_engine | 2016-2026 | trend_ok | 21-63 | 20 | 8.5% | 14.7% |  | 0.68 | -20.5% | knapp: CAGR<SPY; Ausstiege {'zeitausstieg': 1269, 'rangverlust': 809, 'gewinnziel_erreicht': 1} |
| 31 | sp500_close | ranking_engine | 2016-2026 | trend_ok | 42-42 | 20 | 6.5% | 14.7% |  | 0.53 | -22.6% | knapp: CAGR<SPY; Ausstiege {'zeitausstieg': 2680, 'stop_intraday': 1, 'gewinnziel_erreicht': 1} |
| 33 | sp500_close | autopsie | 2017-2026 | nan | nan |  |  |  |  |  |  | Ausstieg 'rangverlust' traegt 39% der Trades bei Oe -3.8% (Treffer 29%, Oe 30 Tage); 'gewinnziel_erreicht' dagegen Oe +189.6%. Pruefen: verkauft diese Regel NACH dem Verlust statt vor ihm (verspaeteter Stop)?. / Rendite steigt mit der Haltedauer (11-21: -3.7% -> 43-63: +6.6%): die fruehen Ausstiege sind die Verlierer - die Kostenkurve aus 24_ zeigt sich auch im Engine-Pfad. / Score-Quartil innerhalb der Kaufmenge ohne Wirkung (oben minus unten +0.34%): keine Konzentration auf die Top 10, die Rangschwelle reicht. / Verlustjahre nach Einstiegsjahr: 2018 (-1.5%, n=250), 2022 (-1.6%, n=203) - gegen SPY-Jahr und Regime-Tor pruefen. / Investitionsgrad (zu Einstandskursen) Mittel 79%, Median 89%, Tage unter 50 %: 20% - Cash-Bremse ist kein Haupthebel. / Einstiegsmonat: bester 4 (+8.1%), schlechtester 9 (-4.7%) - nur Notiz: 10 Jahre sind fuer Saisonregeln zu duenn (Versuchszaehler!). |
| 31 | sp500_close | ranking_engine_exit02 | 2016-2026 | trend_ok | 21-63 | 10 | 8.5% | 14.7% |  | 0.68 | -20.4% | Rangverlust erst unter dem 20. Perzentil: +1 Punkt CAGR (8,5 %) und MaxDD -20 % statt -31 % gegen Basis. Bestehensregel (>= 10,9 %) verfehlt; als Teilverbesserung Kandidat fuer for_ranking(exit_rank_pct=0.2), qlib-Gegenlauf laeuft. |
| 22 | sp500_close | ranking_preis | 2016-2026 | kein | 42 | 20 | 13.4% | 14.9% | 16.7% | 0.96 | -17.4% | knapp: Auswahl<Universum |
| 22 | sp500_close | ranking_preis | 2016-2026 | kein | 42 | 20 | 18.0% | 14.9% | 16.7% | 0.93 | -36.4% | knapp: DD>0,8xSPY |
| 22 | sp500_close | ranking_v2_preis | 2016-2026 | kein | 42 | 20 | 23.2% | 14.9% | 16.7% | 1.00 | -40.3% | knapp: DD>0,8xSPY |
| 22 | sp500_close | ranking_v2_preis | 2016-2026 | trend_ok | 42 | 20 | 16.2% | 14.9% | 16.7% | 0.88 | -34.7% | knapp: DD>0,8xSPY |
| 22 | sp500_close | ranking_v2_preis | 2016-2026 | trend_hyst | 42 | 20 | 16.3% | 14.9% | 16.7% | 0.89 | -34.7% | knapp: DD>0,8xSPY |
| 29 | qlib | dyn_ic | 2009-2020 | kein | dynamisch | 20 | 17.5% | 9.3% |  | 0.66 | -50.4% | knapp: DD>0,8xSPY; LightGBM je Horizont, Top 30, ohne Regime. CAGR 17.5% ueber 2006-2020 inkl. 3 Nulljahren = 22.3% ueber 2009-2020. IC-gewichtete Horizontwahl schlaegt jeden festen Horizont um 4-6 Punkte (auf S&P dagegen -2) - Wahlmix 21:36 % 5:20 % 42/63: je 19 %. |
| 29 | qlib | dyn_roh | 2009-2020 | kein | dynamisch | 20 | 16.6% | 9.3% |  | 0.62 | -53.9% | knapp: DD>0,8xSPY; LightGBM je Horizont, Top 30, ohne Regime. CAGR 16.6% ueber 2006-2020 inkl. 3 Nulljahren = 21.2% ueber 2009-2020.  |
| 29 | qlib | fest_h10 | 2009-2020 | kein | 10 | 20 | 13.6% | 9.3% |  | 0.58 | -44.8% | knapp: DD>0,8xSPY; LightGBM je Horizont, Top 30, ohne Regime. CAGR 13.6% ueber 2006-2020 inkl. 3 Nulljahren = 17.3% ueber 2009-2020.  |
| 29 | qlib | fest_h21 | 2009-2020 | kein | 21 | 20 | 11.8% | 9.3% |  | 0.53 | -52.9% | knapp: DD>0,8xSPY; LightGBM je Horizont, Top 30, ohne Regime. CAGR 11.8% ueber 2006-2020 inkl. 3 Nulljahren = 15.0% ueber 2009-2020.  |
| 29 | qlib | fest_h63 | 2009-2020 | kein | 63 | 20 | 11.4% | 9.3% |  | 0.55 | -47.5% | knapp: DD>0,8xSPY; LightGBM je Horizont, Top 30, ohne Regime. CAGR 11.4% ueber 2006-2020 inkl. 3 Nulljahren = 14.4% ueber 2009-2020.  |
| 31 | sp500_close | ranking_engine | 2016-2026 | trend_ok | 42-42 | 20 | 7.3% | 14.7% |  | 0.57 | -22.7% | knapp: CAGR<SPY; Ausstiege {'zeitausstieg': 2680, 'stop_intraday': 1, 'gewinnziel_erreicht': 1} |
| 31 | sp500_close | ranking_engine | 2016-2026 | trend_ok | 42-42 | 20 | 7.3% | 14.7% |  | 0.57 | -22.7% | knapp: CAGR<SPY; Ausstiege {'zeitausstieg': 2680, 'stop_intraday': 1, 'gewinnziel_erreicht': 1} |
| 31 | sp500_close | ranking_engine | 2016-2026 | trend_ok | 42-42 | 20 | 6.5% | 14.7% |  | 0.53 | -22.6% | knapp: CAGR<SPY; Ausstiege {'zeitausstieg': 2680, 'stop_intraday': 1, 'gewinnziel_erreicht': 1} |
| 31 | qlib | ranking_engine | 2006-2020 | trend_ok | 21-63 | 20 | 6.0% | 9.3% |  | 0.48 | -39.9% | knapp: CAGR<SPY; Ausstiege {'rangverlust': 703, 'zeitausstieg': 554} |
| 23 | sp500_close | ml_lgbm_h21 | 2019-2026 | kein | 21 | 20 | 24.6% | 16.6% | 17.1% | 0.93 | -43.5% | knapp: DD>0,8xSPY; ML minus bester Handmix -0.2%; OOS-IC +0.0210, bester Einzelfaktor vola_niedrig -0.0315 |
| 33 | qlib | autopsie | 2007-2020 | nan | nan |  |  |  |  |  |  | Ausstieg 'rangverlust' traegt 56% der Trades bei Oe -2.2% (Treffer 42%, Oe 30 Tage); 'zeitausstieg' dagegen Oe +7.0%. Pruefen: verkauft diese Regel NACH dem Verlust statt vor ihm (verspaeteter Stop)?. / Rendite steigt mit der Haltedauer (11-21: -3.9% -> 43-63: +5.3%): die fruehen Ausstiege sind die Verlierer - die Kostenkurve aus 24_ zeigt sich auch im Engine-Pfad. / Score-Quartil wirkt (-2.53% oben minus unten): engere Rangschwelle testen. / Verlustjahre nach Einstiegsjahr: 2015 (-2.0%, n=107), 2018 (-2.9%, n=132), 2019 (-0.1%, n=141) - gegen SPY-Jahr und Regime-Tor pruefen. / Investitionsgrad (zu Einstandskursen) Mittel 78%, Median 86%, Tage unter 50 %: 22% - Cash-Bremse ist kein Haupthebel. / Konzentration: die besten 5 % der Trades liefern 34% des Bruttogewinns, die 10 besten Symbole 58% des Netto-PnL; ohne die 10 besten Trades waere der Netto-PnL 85,729 $ statt 138,478 $ - breit verteilt. / Einstiegsmonat: bester 5 (+6.0%), schlechtester 3 (-1.0%) - nur Notiz: 14 Jahre sind fuer Saisonregeln zu duenn (Versuchszaehler!). |
| 31 | sp500_close | ranking_engine | 2016-2026 | trend_ok | 21-63 | 20 | 8.0% | 14.7% |  | 0.68 | -19.1% | knapp: CAGR<SPY; Ausstiege {'stop_intraday': 1949, 'zeitausstieg': 897, 'rangverlust': 364, 'gewinnziel_erreicht': 2} |
| 31 | qlib | ranking_engine | 2006-2020 | trend_ok | 21-63 | 20 | 6.2% | 9.3% |  | 0.56 | -22.1% | knapp: CAGR<SPY; Ausstiege {'stop_intraday': 719, 'rangverlust': 685, 'zeitausstieg': 366} |
| 35 | qlib | ml_kein | 2009-2020 | kein | 21 | 20 | 15.7% | 14.5% | 13.9% | 0.70 | -40.6% | ML-Variante aus gespeicherten Vorhersagen; gegen momentum_trend +5.6%; MaxDD -40.6% |
| 35 | qlib | hybrid | 2009-2020 | kein | 21 | 20 | 18.4% | 14.5% | 13.9% | 0.75 | -40.1% | ML-Variante aus gespeicherten Vorhersagen; gegen momentum_trend +8.2%; MaxDD -40.1% |
| 31 | qlib | ranking_engine | 2006-2020 | trend_ok | 21-63 | 20 | 5.6% | 9.3% |  | 0.49 | -31.8% | knapp: CAGR<SPY; Ausstiege {'stop_intraday': 649, 'rangverlust': 474, 'zeitausstieg': 398} |
| 31 | sp500_close | ranking_engine | 2016-2026 | trend_ok | 21-63 | 20 | 9.3% | 14.7% |  | 0.71 | -21.4% | knapp: CAGR<SPY; Ausstiege {'zeitausstieg': 965, 'rangverlust': 467, 'stop_intraday': 1} |
| 31 | sp500_close | ranking_engine | 2016-2026 | trend_ok | 21-63 | 20 | 7.5% | 14.7% |  | 0.61 | -21.2% | knapp: CAGR<SPY; Ausstiege {'stop_intraday': 1733, 'zeitausstieg': 825, 'rangverlust': 249, 'gewinnziel_erreicht': 2} |
| 31 | sp500_close | ranking_engine | 2016-2026 | trend_ok | 21-63 | 20 | 6.7% | 14.7% |  | 0.56 | -23.4% | knapp: CAGR<SPY; Ausstiege {'stop_intraday': 1902, 'zeitausstieg': 899, 'rangverlust': 284, 'gewinnziel_erreicht': 1} |
| 23 | qlib | ml_lgbm_h42 | 2009-2020 | kein | 42 | 20 | 16.6% | 14.5% | 13.9% | 0.72 | -40.9% | knapp: DD>0,8xSPY; ML minus bester Handmix +3.6%; OOS-IC +0.0343, bester Einzelfaktor abstand_52w_tief +0.0372 |
| 31 | qlib | ranking_engine | 2006-2020 | trend_ok | 21-63 | 20 | 5.1% | 9.3% |  | 0.47 | -27.1% | knapp: CAGR<SPY; Ausstiege {'stop_intraday': 685, 'rangverlust': 460, 'zeitausstieg': 419} |
| 33 | qlib | autopsie | 2007-2020 | nan | nan |  |  |  |  |  |  | Ausstieg 'stop_intraday' traegt 44% der Trades bei Oe -8.1% (Treffer 0%, Oe 17 Tage); 'zeitausstieg' dagegen Oe +13.5%. Pruefen: verkauft diese Regel NACH dem Verlust statt vor ihm (verspaeteter Stop)?. / Rendite steigt mit der Haltedauer (<=10: -8.4% -> 43-63: +10.9%): die fruehen Ausstiege sind die Verlierer - die Kostenkurve aus 24_ zeigt sich auch im Engine-Pfad. / Score-Quartil wirkt (-4.04% oben minus unten): engere Rangschwelle testen. / Verlustjahre nach Einstiegsjahr: 2008 (-0.1%, n=13), 2015 (-1.0%, n=165), 2018 (-0.3%, n=209) - gegen SPY-Jahr und Regime-Tor pruefen. / Investitionsgrad (zu Einstandskursen) Mittel 80%, Median 85%, Tage unter 50 %: 11% - Cash-Bremse ist kein Haupthebel. / Konzentration: die besten 5 % der Trades liefern 37% des Bruttogewinns, die 10 besten Symbole 51% des Netto-PnL; ohne die 10 besten Trades waere der Netto-PnL 179,432 $ statt 236,730 $ - breit verteilt. / Einstiegsmonat: bester 5 (+4.7%), schlechtester 10 (+0.3%) - nur Notiz: 14 Jahre sind fuer Saisonregeln zu duenn (Versuchszaehler!). |
| 22 | qlib | ranking_v2 | 2006-2020 | trend_ok | 42 | 20 | 7.2% | 9.4% | 8.7% | 0.44 | -40.2% | knapp: CAGR<SPY |
| 31 | qlib | ranking_engine | 2006-2020 | trend_ok | 21-63 | 20 | 6.7% | 9.3% |  | 0.55 | -23.8% | knapp: CAGR<SPY; Ausstiege {'stop_intraday': 623, 'rangverlust': 441, 'zeitausstieg': 418} |
| 33 | qlib_momentum | autopsie | 2007-2020 | nan | nan |  |  |  |  |  |  | Ausstieg 'stop_intraday' traegt 42% der Trades bei Oe -8.5% (Treffer 0%, Oe 18 Tage); 'zeitausstieg' dagegen Oe +14.1%. Pruefen: verkauft diese Regel NACH dem Verlust statt vor ihm (verspaeteter Stop)?. / Rendite steigt mit der Haltedauer (<=10: -8.5% -> 43-63: +10.6%): die fruehen Ausstiege sind die Verlierer - die Kostenkurve aus 24_ zeigt sich auch im Engine-Pfad. / Score-Quartil wirkt (+1.36% oben minus unten): engere Rangschwelle testen. / Verlustjahre nach Einstiegsjahr: 2015 (-0.9%, n=129), 2018 (-1.4%, n=164) - gegen SPY-Jahr und Regime-Tor pruefen. / Investitionsgrad (zu Einstandskursen) Mittel 74%, Median 84%, Tage unter 50 %: 27% - Cash-Bremse ist ein Hebel. / Konzentration: die besten 5 % der Trades liefern 40% des Bruttogewinns, die 10 besten Symbole 73% des Netto-PnL; ohne die 10 besten Trades waere der Netto-PnL 87,879 $ statt 161,651 $ - breit verteilt. / Einstiegsmonat: bester 6 (+5.2%), schlechtester 3 (-0.7%) - nur Notiz: 14 Jahre sind fuer Saisonregeln zu duenn (Versuchszaehler!). |
| 33 | sp500_close_momentum | autopsie | 2017-2026 | nan | nan |  |  |  |  |  |  | Ausstieg 'stop_intraday' traegt 62% der Trades bei Oe -6.6% (Treffer 0%, Oe 15 Tage); 'gewinnziel_erreicht' dagegen Oe +151.3%. Pruefen: verkauft diese Regel NACH dem Verlust statt vor ihm (verspaeteter Stop)?. / Rendite steigt mit der Haltedauer (<=10: -6.1% -> 43-63: +15.3%): die fruehen Ausstiege sind die Verlierer - die Kostenkurve aus 24_ zeigt sich auch im Engine-Pfad. / Score-Quartil wirkt (+1.73% oben minus unten): engere Rangschwelle testen. / Verlustjahre nach Einstiegsjahr: 2018 (-0.2%, n=292), 2022 (-1.7%, n=105) - gegen SPY-Jahr und Regime-Tor pruefen. / Investitionsgrad (zu Einstandskursen) Mittel 81%, Median 88%, Tage unter 50 %: 18% - Cash-Bremse ist kein Haupthebel. / Konzentration: die besten 5 % der Trades liefern 63% des Bruttogewinns, die 10 besten Symbole 60% des Netto-PnL; ohne die 10 besten Trades waere der Netto-PnL 144,371 $ statt 254,334 $ - rechtsschief: jede Regel, die Sieger zwingt (Zeitausstieg, Sperre, Gewinnziel), kostet den rechten Rand. / Einstiegsmonat: bester 4 (+8.4%), schlechtester 2 (-2.4%) - nur Notiz: 10 Jahre sind fuer Saisonregeln zu duenn (Versuchszaehler!). |

## ZU_DUENN (1)

| Skript | Panel | Variante | Zeitraum | Regime | H | Kosten | CAGR | SPY | Univ.EW | Sharpe | MaxDD | Lehre |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 33 | sp500_close | autopsie | 2017-2026 | nan | nan |  |  |  |  |  |  | Score-Quartil innerhalb der Kaufmenge ohne Wirkung (oben minus unten +0.93%): keine Konzentration auf die Top 10, die Rangschwelle reicht. / Verlustjahre nach Einstiegsjahr: 2022 (-2.2%, n=200), 2025 (-0.2%, n=250) - gegen SPY-Jahr und Regime-Tor pruefen. / Investitionsgrad (zu Einstandskursen) Mittel 77%, Median 86%, Tage unter 50 %: 11% - Cash-Bremse ist kein Haupthebel. / Einstiegsmonat: bester 10 (+4.7%), schlechtester 2 (-3.3%) - nur Notiz: 10 Jahre sind fuer Saisonregeln zu duenn (Versuchszaehler!). |

## VERWORFEN (181)

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
| 31 | sp500_close | ranking_engine | 2016-2026 | trend_ok | 21-63 | 10 | 6.7% | 14.7% |  | 0.57 | -18.4% | Engine-Replay mit 3-ATR-Stop: 60 % der Ausstiege sind Stops (Ø -5 %), Zeitausstiege Ø +15 %; CAGR 6-9 Punkte unter SPY (nachgetragen) |
| 31 | qlib | ranking_engine | 2009-2020 | trend_ok | 21-63 | 10 | 5.2% | 14.2% |  | 0.46 | -30.2% | Engine-Replay mit 3-ATR-Stop: 60 % der Ausstiege sind Stops (Ø -5 %), Zeitausstiege Ø +15 %; CAGR 6-9 Punkte unter SPY (nachgetragen) |
| 22 | sp500_close | ranking_preis | 2016-2026 | trend_ok | 42 | 20 | 11.1% | 14.9% | 16.7% | 0.91 | -15.7% | CAGR<SPY, Auswahl<Universum |
| 22 | sp500_close | ranking_preis | 2016-2026 | vix_ruhig | 42 | 20 | 10.7% | 14.9% | 16.7% | 0.85 | -18.3% | CAGR<SPY, Auswahl<Universum |
| 22 | sp500_close | ranking_preis | 2016-2026 | trend_und_vix | 42 | 20 | 9.6% | 14.9% | 16.7% | 0.83 | -15.1% | CAGR<SPY, Auswahl<Universum |
| 22 | sp500_close | ranking_preis | 2016-2026 | trend_ok | 42 | 20 | 12.3% | 14.9% | 16.7% | 0.91 | -18.7% | CAGR<SPY, Auswahl<Universum |
| 22 | sp500_close | ranking_preis | 2016-2026 | vix_ruhig | 42 | 20 | 11.9% | 14.9% | 16.7% | 0.85 | -19.9% | CAGR<SPY, Auswahl<Universum |
| 22 | sp500_close | ranking_preis | 2016-2026 | trend_und_vix | 42 | 20 | 10.6% | 14.9% | 16.7% | 0.84 | -17.9% | CAGR<SPY, Auswahl<Universum |
| 22 | sp500_close | ranking_preis | 2016-2026 | trend_ok | 42 | 20 | 12.9% | 14.9% | 16.7% | 0.91 | -20.8% | CAGR<SPY, Auswahl<Universum |
| 22 | sp500_close | ranking_preis | 2016-2026 | vix_ruhig | 42 | 20 | 12.1% | 14.9% | 16.7% | 0.84 | -22.6% | CAGR<SPY, Auswahl<Universum |
| 22 | sp500_close | ranking_preis | 2016-2026 | trend_und_vix | 42 | 20 | 10.9% | 14.9% | 16.7% | 0.83 | -19.9% | CAGR<SPY, Auswahl<Universum |
| 22 | sp500_close | ranking_preis | 2016-2026 | trend_ok | 42 | 20 | 12.9% | 14.9% | 16.7% | 0.85 | -30.8% | CAGR<SPY, DD>0,8xSPY, Auswahl<Universum |
| 22 | sp500_close | ranking_preis | 2016-2026 | trend_hyst | 42 | 20 | 13.0% | 14.9% | 16.7% | 0.85 | -30.8% | DD>0,8xSPY, Auswahl<Universum |
| 29 | qlib | fest_h42 | 2009-2020 | kein | 42 | 20 | 8.3% | 9.3% |  | 0.43 | -49.7% | CAGR<SPY, DD>0,8xSPY; LightGBM je Horizont, Top 30, ohne Regime. CAGR 8.3% ueber 2006-2020 inkl. 3 Nulljahren = 10.5% ueber 2009-2020.  |
| 23 | qlib | ml_lgbm_h21 | 2009-2020 | trend_ok | 21 | 20 | 7.8% | 14.5% | 13.9% | 0.49 | -30.7% | CAGR<SPY, DD>0,8xSPY, Auswahl<Universum; ML minus bester Handmix -2.4%; OOS-IC +0.0301, bester Einzelfaktor mom_12_1_vola +0.0298 |
| 31 | sp500_close | ranking_engine | 2016-2026 | trend_ok | 21-63 | 20 | 7.9% | 14.7% |  | 0.59 | -31.4% | CAGR<SPY, DD>0,8xSPY; Ausstiege {'zeitausstieg': 1097, 'rangverlust': 728, 'gewinnziel_erreicht': 5, 'stop_intraday': 1} |
| 31 | sp500_close | ranking_engine | 2016-2026 | trend_ok | 21-63 | 20 | 6.6% | 14.7% |  | 0.53 | -27.9% | CAGR<SPY, DD>0,8xSPY; Ausstiege {'zeitausstieg': 1196, 'rangverlust': 772, 'gewinnziel_erreicht': 3, 'stop_intraday': 1} |
| 35 | qlib | ml_trend | 2009-2020 | trend_ok | 21 | 20 | 7.8% | 14.5% | 13.9% | 0.49 | -30.7% | ML-Variante aus gespeicherten Vorhersagen; gegen momentum_trend -2.4%; MaxDD -30.7% |
| 35 | qlib | ml_hyst | 2009-2020 | trend_hyst | 21 | 20 | 7.8% | 14.5% | 13.9% | 0.49 | -30.4% | ML-Variante aus gespeicherten Vorhersagen; gegen momentum_trend -2.3%; MaxDD -30.4% |
| 35 | qlib | ml_vola25 | 2009-2020 | kein | 21 | 20 | 12.1% | 14.5% | 13.9% | 0.67 | -33.7% | ML-Variante aus gespeicherten Vorhersagen; gegen momentum_trend +2.0%; MaxDD -33.7% |
| 35 | qlib | ml_trend_vola25 | 2009-2020 | trend_ok | 21 | 20 | 7.9% | 14.5% | 13.9% | 0.52 | -25.3% | ML-Variante aus gespeicherten Vorhersagen; gegen momentum_trend -2.3%; MaxDD -25.3% |
| 35 | qlib | momentum_trend | 2009-2020 | trend_ok | 21 | 20 | 10.2% | 14.5% | 13.9% | 0.56 | -32.5% | ML-Variante aus gespeicherten Vorhersagen; gegen momentum_trend +0.0%; MaxDD -32.5% |
| 35 | qlib | momentum_kein | 2009-2020 | kein | 21 | 20 | 11.8% | 14.5% | 13.9% | 0.56 | -38.4% | ML-Variante aus gespeicherten Vorhersagen; gegen momentum_trend +1.6%; MaxDD -38.4% |
| 35 | qlib | momentum_vola25 | 2009-2020 | kein | 21 | 20 | 11.0% | 14.5% | 13.9% | 0.60 | -34.0% | ML-Variante aus gespeicherten Vorhersagen; gegen momentum_trend +0.8%; MaxDD -34.0% |
| 23 | qlib | ml_lgbm_h10 | 2009-2020 | kein | 10 | 20 | 11.6% | 14.5% | 13.9% | 0.54 | -44.2% | CAGR<SPY, DD>0,8xSPY, Auswahl<Universum; ML minus bester Handmix +3.4%; OOS-IC +0.0303, bester Einzelfaktor mom_12_1_vola +0.0262 |
| 22 | qlib | ranking_v2 | 2006-2020 | kein | 42 | 10 | 6.9% | 9.4% | 8.7% | 0.38 | -59.9% | CAGR<SPY, DD>0,8xSPY |
| 22 | qlib | ranking_v2 | 2006-2020 | kein | 42 | 20 | 6.3% | 9.4% | 8.7% | 0.36 | -60.0% | CAGR<SPY, DD>0,8xSPY, Auswahl<Universum |
| 22 | qlib | ranking_v2 | 2006-2020 | kein | 42 | 40 | 5.0% | 9.4% | 8.7% | 0.32 | -60.3% | CAGR<SPY, DD>0,8xSPY, Auswahl<Universum |
| 22 | qlib | ranking_v2 | 2006-2020 | trend_ok | 42 | 40 | 6.3% | 9.4% | 8.7% | 0.40 | -41.0% | CAGR<SPY, Auswahl<Universum |
| 22 | qlib | ranking_v2 | 2006-2020 | vix_ruhig | 42 | 10 | 3.3% | 9.4% | 8.7% | 0.26 | -44.8% | CAGR<SPY, DD>0,8xSPY, Auswahl<Universum |
| 22 | qlib | ranking_v2 | 2006-2020 | vix_ruhig | 42 | 20 | 2.8% | 9.4% | 8.7% | 0.24 | -45.0% | CAGR<SPY, DD>0,8xSPY, Auswahl<Universum |
| 22 | qlib | ranking_v2 | 2006-2020 | vix_ruhig | 42 | 40 | 1.8% | 9.4% | 8.7% | 0.19 | -45.4% | CAGR<SPY, DD>0,8xSPY, Auswahl<Universum |
| 22 | qlib | ranking_v2 | 2006-2020 | trend_und_vix | 42 | 10 | 5.5% | 9.4% | 8.7% | 0.38 | -36.3% | CAGR<SPY, Auswahl<Universum |
| 22 | qlib | ranking_v2 | 2006-2020 | trend_und_vix | 42 | 20 | 5.1% | 9.4% | 8.7% | 0.36 | -36.7% | CAGR<SPY, Auswahl<Universum |
| 22 | qlib | ranking_v2 | 2006-2020 | trend_und_vix | 42 | 40 | 4.2% | 9.4% | 8.7% | 0.31 | -37.6% | CAGR<SPY, Auswahl<Universum |

## WIDERLEGT (1)

| Skript | Panel | Variante | Zeitraum | Regime | H | Kosten | CAGR | SPY | Univ.EW | Sharpe | MaxDD | Lehre |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 31 | sp500_close | ranking_engine_h42fest | 2016-2026 | trend_ok | 42-42 | 10 | 6.5% | 14.7% |  | 0.53 | -22.6% | Reiner Zeitausstieg 42 Tage ohne Rangverlust: 6,5 % (Basis 7,5 %, Referenz 12,9 %). Der Rangverlust ist NICHT die Luecke zur vektorisierten Messung. Verdacht jetzt: 5-Tage-Wiedereinstiegssperre (alle 50 laufen gleichzeitig aus und duerfen nicht zurueck) + 1/Vola-Sizing. |
