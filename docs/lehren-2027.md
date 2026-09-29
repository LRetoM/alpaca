# Lehren 2027 — jeder Fehlschlag als Regel

> Stand: 2026-09-29. Dieses Dokument ist der zweite Teil des Gedächtnisses
> (der erste ist das automatisch erzeugte [befunde-2027.md](befunde-2027.md)).
> Hier steht, **warum** etwas nicht funktioniert hat, welche **Regel**
> daraus wurde und **wo** sie im Code oder in der Arbeitsweise verankert ist.
> Nichts wird gelöscht; ein überholter Eintrag bekommt einen Zusatz, keinen
> Strich. Wer neu einsteigt, liest zuerst §0 und §1, dann den Masterplan.

## 0. Wie das Lernen hier organisiert ist (der Kreislauf)

```
Idee  →  27_hypothesen_anmelden.py   (Behauptung, Test, Bestehensregel,
         ↓                             Erwartung — VOR dem Ergebnis, mit Datum)
Lauf  →  2x_/3x_-Skript              (jede Zeile geht automatisch ins Register:
         ↓                             befunde.eintragen → results/labor/befunde.jsonl)
Zahl  →  32_befunde.py --bericht      (docs/befunde-2027.md: bestanden/kandidat/
         ↓                             verworfen, Versuchszähler, Zufallsschwelle)
Warum →  33_trade_autopsie.py         (zerlegt die Trades: Ausstiegsgrund, Haltedauer,
         ↓                             Score, Monat, Jahr, Investitionsgrad → Sätze)
Regel →  dieses Dokument + Code       (EngineConfig.for_ranking, CLAUDE.md-Regeln,
                                       Risiko-Dach, Skript-Standards)
```

Drei Zahlen halten den Kreislauf ehrlich:

| Zahl | Wert (2026-09-29) | Bedeutung |
|---|---|---|
| Befunde im Register | 180 + Autopsien | jede gerechnete Variante × Regime × Kosten |
| Unterschiedliche Varianten | 68 | so oft wurde „etwas probiert“ |
| Zufallsschwelle | 3,4 σ | ein t-Wert darunter ist bei 68 Versuchen kein Fund |

Ein „Fund“, der die Schwelle nicht schafft, wird als *kandidat* geführt und
muss auf einem zweiten, nicht benutzten Panel bestehen (qlib 2006–2020 ↔
S&P 2016–2026 ↔ Projektcache 2018–2026), bevor er in die Engine darf.

## 1. Die zwölf wichtigsten Lehren (Kurzfassung, Stand 2026-09-29 abends)

1. **Kosten vor Signal.** Der Umkehr-Vorsprung (+0,11 % je Trade) lag unter
   dem Rundlauf-Breakeven (0,14 %). Regel: Erst die Haltedauer-Kurve (24_),
   dann das Signal. → `for_ranking(min_hold_days=21)`.
2. **Extremrand ist Gift.** Top 20 aus 3.000 Namen verliert; Top 50 aus
   dem liquiden Universum (≥ 25 Mio $/Tag) nicht. → `min_dollar_volume=25e6`,
   `max_positions=50`.
3. **IC ist notwendig, nicht hinreichend.** Positive ICs, verlierende
   Portfolios (Masterplan §6.6). Regel: Kein Faktor ohne 22_-Portfolio mit
   Kosten und **beiden** Benchmarks (SPY und Univ.EW).
4. **Ein Engine-Replay ist eine Ziehung, keine Messung.** Dieselbe
   Strategie als Klumpen-Kohorte streut je Startversatz 7,9–18,0 % CAGR
   (§2.15). Regel: gestaffelte Einstiege (`max_new_per_day`), und Engine-
   Zahlen nur mit ±3 Punkten Rauschen lesen.
5. **Drei plausible Täter waren keine.** Stop (HYP-20), Rangverlust
   (HYP-21), Sieger-Rauswurf (Verlängerung): alle einzeln entlastet. Regel:
   Jeder Verdacht aus einer Autopsie braucht den isolierenden Lauf — und
   das billigste Experiment (Referenz auf die Engine zubewegen) zuerst.
6. **Der Stop ist ein Drawdown-Halbierer, kein CAGR-Killer** (S&P −18 %
   statt −31 % bei −0,8 Punkten; qlib −30 % statt −45 % bei +0,5).
   Rangverlust erst unter dem 20. Perzentil: +1 Punkt, −10 Punkte MaxDD.
7. **Chartmuster sind keine Faktoren**, Ausbrüche kehren um; **Explosionen
   sind vorhersagbar, aber nicht verdienbar** (Vola + Drawdown = Lotterie).
8. **Die ML-Prognose ist ein Erholungs-Ranker, kein besserer Momentum-
   Ranker.** Ohne Regime-Tor +5 Punkte gegen den Handmix, mit Tor −2,4;
   der Vorsprung sitzt in 2009 und 2020. Auf dem S&P-Panel (ohne Volumen)
   kein Vorsprung. Regel: ML für die Phase, in der Momentum nichts hat
   (Hybrid/Vola-Ziel statt Tor, `35_`), Entscheidung auf dem Projektcache.
9. **Dynamische Haltedauer trägt nur, wo die Horizonte verschiedene Aktien
   bevorzugen** (qlib +4–6 Punkte, S&P −2). Zweite Stufe, nicht erste.
10. **Vola-Ziel halbiert den Drawdown — auf dem richtigen Niveau** (0,25
    für einen 50-Aktien-Momentumkorb; 0,15 bremst dauerhaft).
11. **Regime-Tor: halber Drawdown, verpasste V-Erholungen** — und ein
    schnellerer Wiedereinstieg (Hysterese) ändert daran nichts (+0,1 auf
    S&P). Was nach dem Tief oben steht, ist das Problem, nicht der Zeitpunkt.
12. **Survivorship macht aus 13 % 23 %.** Jede S&P-Zahl wird nur neben der
    qlib-Zahl gelesen; die Erwartung für 2027 kommt aus qlib.

## 2. Fehlschläge im Einzelnen — Ursache, Regel, Verankerung

Format: **Was scheiterte** · Messung · Warum · Regel · Verankert in · Status.

### 2.1 Umkehr-Bot (5-Tage-Reversal) — Vorsprung kleiner als Kosten
- Messung: +0,11 % je Trade brutto, Breakeven 0,14 % bei 5 bps Spread;
  qlib liq25 `reversal_rein` H5: netto negativ bei 20 bps.
- Warum: 100 Rundläufe je Position und Jahr; jeder Rundlauf kostet Spread +
  Slippage, das Signal trägt 5 Tage.
- Regel: Netto-Vorsprung je Trade ≥ 2 × Kosten je Rundlauf, sonst
  Haltedauer verlängern; Umschlag ≤ 20 Rundläufe/Jahr.
- Verankert: `EngineConfig.for_ranking` (min_hold 21, max_hold 63),
  Masterplan §6.7 Haltedauer-Kurve, CLAUDE.md Regel „Kosten zuerst“.
- Status: erledigt; `kurz`/`kurz10` auf qlib als Varianten geführt und
  verworfen (Register).

### 2.2 Top-20-Portfolios aus 3.000 Namen verlieren gegen ihr eigenes Universum
- Messung: 22_ qlib alle Symbole, Top 20: CAGR unter Univ.EW; ab Umsatz
  ≥ 25 Mio $ und Top 50 dreht sich das Bild (Masterplan §6.7).
- Warum: Der oberste Rang eines Querschnitts wird von Datenfehlern,
  Microcaps und Extremwerten besetzt (Flip-Flop-Kurse, illiquide Namen).
- Regel: Liquides Universum (60-Tage-Median Umsatz ≥ 25 Mio $, Kurs ≥ 5 $),
  Z-Scores auf ±3 gekappt, Top 50 statt Top 20.
- Verankert: `labor.liquides_universum`, `Engine._querschnitt_scores`
  (clip ±3), `for_ranking(max_positions=50, min_price=5)`.
- Status: erledigt.

### 2.3 Positive ICs, verlierende Portfolios
- Messung: Masterplan §6.6 — Faktoren mit t_defl > 3 (reversal_5d,
  vol_z_1d), deren Top-Portfolio netto verliert.
- Warum: Der IC misst den Rang über ALLE Aktien, das Portfolio kauft nur
  den Extremrand; dazu Kosten und Kollision zwischen Faktoren (Umkehr kauft
  Verlierer, Momentum Gewinner).
- Regel: Kein Faktor kommt ohne 22_-Portfolio (Kosten 10/20/40 bps, SPY und
  Univ.EW) in die Engine; das mechanische Urteil `befunde.urteil_portfolio`
  entscheidet, nicht der IC.
- Verankert: `befunde.urteil_portfolio`, Hooks in 22_/24_/31_.
- Status: erledigt.

### 2.4 Engine-Replay 5–6 Punkte unter der vektorisierten Referenz
- Messung (S&P 2016–2026, exakt gleicher Score `ranking_preis`, trend_ok,
  20 bps): Referenz 12,9 % CAGR / −30,8 % MaxDD; Engine ohne Stop 7,5 % /
  −31,0 %; Engine mit 3-ATR-Stop 6,7 % / −18,5 %. qlib 2009–2020: Referenz
  6,1 %, Engine 4,7 % (ohne Stop) bzw. 5,2 % (mit Stop).
- Warum (Trade-Autopsie, `33_`): 57 % der Ausstiege sind „rangverlust“
  mit Ø −2,3 % und Trefferquote 39 %; Zeitausstiege nach 63 Tagen Ø +8,7 %,
  Trefferquote 73 %. Der Rangverlust verkauft eine Aktie genau dann, wenn
  sie gerade gefallen ist — und kurz gefallene Aktien haben positive
  Umkehrrendite. Die Lücke konzentriert sich in V-Erholungen (2020: −3,5 %
  gegen +8,4 %; 2023: +0,6 % gegen +13,4 %; 2026: +1,6 % gegen +16,3 %).
  Investitionsgrad ist NICHT die Ursache (Engine 86 %, Referenz 74 %).
- Regel (vorläufig, bis HYP-21 entschieden): Ausstiegsregeln, die auf
  gefallene Kurse reagieren (Rangverlust, enge Stops), sind im
  Momentum-Rangportfolio verdächtig; der Zeitausstieg ist der Maßstab.
- Verankert: HYP-2027-21 (registriert vor dem Test), `33_trade_autopsie.py`.
- Status: **Gegen-Test gelaufen (S&P):** reiner Zeitausstieg 42 Tage 6,5 %
  (schlechter als die Basis 7,5 %), Rangverlust erst < 20. Perzentil
  **8,5 % bei MaxDD −20 %** (Basis −31 %). HYP-21 in der Hauptaussage
  widerlegt — der Rangverlust ist nicht die Lücke —, die weichere Schwelle
  ist eine echte Teilverbesserung (qlib-Gegenlauf läuft). Was die Lücke
  auch nicht ist: Signal (Rangkorrelation Engine/Labor 0,998), Investitions-
  grad, Kosten, Tagesdeckel. Isolierende Läufe (S&P, 42 Tage fest):
  Sperre 0 → **exakt gleich** (6,5 %), Gleichgewicht statt 1/Vola → +0,8
  (7,3 %). **Der Täter**: Der Abgleich der Engine-Bestände mit der
  Top-50-Liste der Referenz am selben Kauftag ergibt nur 33–46 von 50
  gemeinsamen Namen — beim Zeitausstieg wird die verkaufte Aktie am
  selben Tag nicht zurückgekauft, ihr Platz geht an Rang 51–100. Die
  Dauer-Sieger (die nach 42/63 Tagen noch im Top-Dezil stehen) fliegen
  systematisch raus, und aus ihnen kommen 40–90 % des Gewinns (§2.13).
  Regel: **Verlängerung statt Zeitausstieg** — nach der Höchstfrist wird
  nur verkauft, wer nicht mehr im Kaufbereich steht (`renew_rank_pct`,
  Engine + 31_ `--verlaengern`, Selbsttest). Replays laufen. Lehre über
  die Lehre: **Eine Autopsie zeigt Verdächtige, keine Täter** — jeder
  Verdacht braucht den isolierenden Lauf, und der Täter war am Ende die
  eine Regel, die niemand verdächtigt hatte, weil sie „nur die Uhr“ war.

### 2.5 Fester 3-ATR-Stop (HYP-2027-20) — Hauptaussage widerlegt
- Messung: siehe 2.4. Ohne Stop: S&P +0,8 Punkte CAGR, qlib −0,5 Punkte;
  MaxDD S&P −18 % → −31 %, qlib −30 % → −45 %.
- Warum: Der Stop kappt nicht die Gewinner (die laufen bis Zeit- oder
  Rangausstieg), sondern die Verlierer früh; im Engine-Pfad mit Rangverlust
  ist er sogar der bessere der beiden „Verlierer-Ausstiege“ (Stop Ø −5,4 %
  nach 14 Tagen gegen Rangverlust Ø −2,3 % nach 32 Tagen — der Stop
  bindet Kapital kürzer).
- Regel: Der Stop bleibt bei 3 ATR, solange kein Vola-Ziel (HYP-22) und
  kein besserer Ausstieg (HYP-21) bestätigt sind. Lehre über die Lehre:
  Eine Hypothese, die aus der Zahl „42–60 % der Ausstiege sind Stops“
  gebaut wurde, hat den Anteil mit der Wirkung verwechselt — die Autopsie
  nach Ausstiegsgrund hätte das vorher gezeigt. Deshalb ist `33_` jetzt
  Pflicht nach jedem Replay.
- Verankert: HYP-20 Urteil im Register (widerlegt), `for_ranking(stop_atr=3.0)`.
- Status: erledigt.

### 2.6 Chartmuster als Faktoren (30_ Teil A)
- Messung qlib 2006–2020, 9 Muster × 3 Horizonte: bestes t_defl +1,99
  (kompression, 5 Tage, 67 % positive Jahre), alle anderen ≤ 1,3 oder
  negativ; gap_up_vol −3,9, donchian_20 −2,8 (Ausbrüche kehren um).
  Schwelle bei 68 Varianten: 3,4 σ.
- Warum: Muster sind Beschreibungen des Vergangenen; das einzige stabile
  Signal in ihnen (Volumenkompression) ist ein Vola-Proxy, den
  `vola_niedrig`/`atr_niedrig` schon tragen.
- Regel: Keine Ausbruchs-/Gap-Käufe; Muster nur noch als
  **Ausschluss**-Kandidaten (gap_up_vol, donchian_20 negativ).
- Verankert: Register (27 Zeilen verworfen), Masterplan §6.11.
- Status: erledigt.

### 2.7 Explosionsvorhersage (30_ Teil B) — vorhersagbar, nicht verdienbar
- Messung: 1.162 Explosionen ≥ +50 %/60 Tage; Walk-forward-GBM AUC 0,81,
  Negativtest 0,50. Merkmale: vol_10 (d 1,08), atr_pct (1,07), drawdown
  (−0,92), rsi_14 (−0,72).
- Warum: Die Merkmale sind Volatilität und Absturz — Lotterieaktien. Der
  Faktorzoo sagt: hohe Vola = negativer IC (vola_niedrig +0,02 auf 63 Tagen).
  Wer Explosionen kauft, kauft auch die Crashs.
- Regel: Explosionsscore nur als Ausschlussfilter testen (HYP-23).
- Status: HYP-23 registriert, Test offen (30_ Teil C).

### 2.8 Dynamische Haltedauer (29_) schlägt feste Horizonte nicht
- Messung S&P: dyn_ic 27,3 % gegen fest_h21 29,2 %. **qlib (breites
  Universum): dyn_ic 22,3 % gegen bestes fest 17,3 % (2009–2020), alle
  Fassungen über SPY 14,3 %.** Ein Panel dagegen, eins deutlich dafür.
- Warum der Unterschied: Auf S&P wählt das Modell fast immer 63 Tage (75 %),
  auf qlib einen echten Mix (21 T 36 %, 5 T 20 %, 42/63 je 19 %) — die Wahl
  trägt nur, wo die Horizonte verschiedene Aktien bevorzugen.
- Regel (korrigiert): Die Dynamik ist zweite Stufe. **Erste Stufe ist die
  Prognose selbst**: Jede Fassung mit LightGBM-Score lag in beiden Panels
  über dem Handmix (§3, Masterplan §6.10/§7.2).
- Verankert: Masterplan §6.8 Nachtrag, §7.2 Architektur v2; HYP-19 kandidat.
- Status: Bestätigung auf drittem Panel (Projektcache) offen.

### 2.9 Saisonalität nach Einstiegsmonat — zu dünn
- Messung: In allen vier Replays Einstiege Mai/Juni Ø +4 bis +7 %,
  März Ø −1 bis −3 %. Kalendermonatsvergleich der Referenz gegen SPY: kein
  konsistentes Muster (Jan/Feb sogar besser als SPY).
- Warum: 10 Jahre, ein Panel überlappend — Versuchszähler.
- Regel: Keine Saisonregel. Notiz bleibt im Register (`33_`).
- Status: erledigt (bewusst NICHT verfolgt).

### 2.10 Score-Feinheit innerhalb der Kaufmenge ohne Wirkung
- Messung: Einstiegs-Score-Quartile innerhalb des Top-Dezils: Ø +2,5 % /
  +2,5 % / +2,0 % / +2,8 % (S&P), qlib ähnlich flach.
- Regel: Keine Konzentration auf Top 10/20; Rangschwelle 0,90 und 50
  Positionen bleiben. Deckt sich mit 2.2.
- Status: erledigt.

### 2.11 Regime-Tor verpasst V-Erholungen
- Messung: 2020 und 2023 kostet das Tor 10–13 Punkte gegen SPY (Referenz),
  halbiert aber den Drawdown 2008/2022.
- Regel: Tor bleibt; schnelleres Wiedereinstiegssignal als HYP-24 testen
  (Hysterese: aus bei SPY < SMA200, an bei SPY > SMA50 steigend).
- Status: **S&P gemessen: +0,1 Punkt (13,0 % gegen 12,9 %), MaxDD gleich,
  Exposure 77 % statt 74 %** — Bestehensregel (+1) verfehlt. Die
  V-Erholungs-Lücke liegt also nicht am Wiedereinstiegszeitpunkt des Tors
  (SMA50 kam 2020 nur sechs Wochen früher), sondern daran, WAS nach dem
  Tief oben im Rang steht (Verlierer-Rallye: die Momentum-Liste ist nach
  einem Crash voll mit defensiven Namen). qlib-Lauf in Kette 2; bei
  gleichem Bild: verworfen.

### 2.12 Infrastruktur: OOM-Kills, sich selbst tötende Shells
- Was scheiterte: fünf Läufe durch die 15-GB-Grenze verloren (ML h10, ML
  h21, ruhig, ranking, muster); `pkill -f`/`pgrep -f` traf die eigene Shell,
  wenn das Muster im selben Befehl stand.
- Regel: Schwere Läufe (ML, 29_, 22_ auf qlib) strikt nacheinander;
  Spaltenfilter vor dem Modell; Prozesse per PID beenden, nie per
  `pkill -f` im selben Befehl wie den Start; Ergebnisdateien mit
  eindeutigen Namen (31_: `_stop{}_h{}-{}_x{}`), sonst überschreiben
  sich Varianten.
- Verankert: CLAUDE.md §Arbeitsweise, 31_ Dateinamen.
- Status: erledigt.

### 2.15 Die Kohorten-Lotterie — der wirkliche Täter hinter der Engine-Lücke
- Messung: Dieselbe Strategie (`ranking_preis`, Top 50, 42 Tage, trend_ok,
  20 bps) als **einzelne** Kohorte statt 42 gestaffelter: CAGR je nach
  Startversatz **7,9–18,0 %** (Mittel 12,9 %, Streuung 2,9), MaxDD −19 bis
  −40 %. Die Engine-Replays (6,5 / 7,3 / 7,5 / 8,5 %) sind eine Ziehung aus
  dieser Verteilung. Verlängerung (2.13) gemessen: greift kaum (6–14 %
  weniger Zeitausstiege) und hilft nicht (6,6–8,0 %).
- Warum: Der Zeitausstieg macht alle Plätze am selben Tag frei; die
  Engine wird zur Klumpen-Kohorte, deren Ergebnis vom Zufall des Starttags
  abhängt. Die Momentum-Literatur staffelt genau deshalb (Jegadeesh/Titman
  1993: überlappende Portfolios).
- Regel: **Ein einzelner Engine-Replay hat ±3 Punkte CAGR und ±10 Punkte
  MaxDD Ziehungsrauschen** — nie eine Engine-Zahl gegen eine Referenzzahl
  lesen, ohne die Staffelung mitzubauen oder über Startversätze zu mitteln.
  Und: `max_new_per_day` (3–5) als Engine-Regel, damit sich die Kohorten
  von selbst staffeln — in Simulation und Live gleich.
- Verankert: `EngineConfig.max_new_per_day`, 31_ `--max-new`, Selbsttest;
  Masterplan §6.9 (Tabelle der Startversätze).
- Status: Replays mit Deckel 3/5 laufen; Bestehen: CAGR ≥ Referenz − 2.
- Lehre über die Lehre: Drei plausible Täter (Stop, Rangverlust, Sieger-
  Rauswurf) wurden nacheinander mit isolierenden Läufen entlastet, bevor
  das Experiment gefunden war, das den wahren Mechanismus zeigt (die
  Referenz so umbauen, dass sie sich wie die Engine verhält — nicht
  umgekehrt). Der billigste Test war der letzte. Nächstes Mal zuerst
  fragen: *Welches Experiment kann die Referenz auf die Engine zubewegen?*

### 2.16 Der ML-Vorsprung lebt in den Phasen, die das Regime-Tor sperrt
- Messung qlib 2009–2020, gleiche Vorhersagen, gleiches Universum: ohne
  Tor ML 15,7 % gegen Handmix 9–10 % (+5); **mit Tor ML 7,8 % gegen
  momentum 10,2 % (−2,4)**. 2009 ohne Tor +24 %, 2020 +35 %.
- Warum: Die wichtigsten Merkmale (ruhiges Volumen, niedrige Vola,
  Abstand zum 52-Wochen-Tief) beschreiben gefallene Qualität — das trägt
  in Erholungen, wenn Momentum leer ausgeht. In Trendphasen ist Momentum
  der bessere Ranker. Nicht gemessen: 2008 (vor dem ersten Testjahr).
- Regel: ML nicht als Ersatz des Handmix, sondern als **Fassung für die
  Phase, in der der Handmix nichts hat** — Hybrid und Vola-Ziel statt Tor
  werden aus den gespeicherten Vorhersagen geprüft (`35_`), Bestehensregel
  vorab: CAGR ≥ momentum+Tor + 2 UND MaxDD ≤ −30 %.
- Verankert: Masterplan §6.10, `35_labor_ml_varianten.py`, HYP-06, HYP-25.
- Status: **gemessen.** Hybrid 18,4 % (SPY 14,5 %, momentum_trend 10,2 %),
  mit Vola-Ziel 0,25: 14,0 % bei MaxDD −30,0 % — erste Fassung, die eine
  vorab registrierte Regel besteht. In-sample entworfen → HYP-25 mit
  Bestehensregel für den Projektcache (2020 und 2022 als Aus-Phasen).

### 2.13 Die Gewinne sitzen in wenigen Namen — und die Regeln zwingen sie raus
- Messung (Autopsie `33_`, Konzentration): S&P-Replay ohne Stop — die
  besten 5 % der Trades liefern 44 % des Bruttogewinns, die 10 besten
  Symbole 43 % des Netto-PnL; qlib: 10 Symbole = **87 %** des Netto-PnL.
  Ohne die 10 besten Trades schrumpft der Netto-PnL um 37–58 %.
- Warum: Momentum ist eine Rechtsschiefe-Strategie — der Erwartungswert
  kommt aus dem Rand. Zeitausstieg nach 63 Tagen, 5-Tage-Sperre und jede
  Gewinnmitnahme kappen genau diesen Rand; der Stop kappt den linken.
- Regel: Kein Gewinnziel (schon so), Zeitausstieg nur, wenn die Aktie das
  Top-Dezil verlassen hat (Verlängerung statt Verkauf — zu bauen, HYP-21
  Folgeversuch), Sperre 0 Tage für Namen, die noch im Top-Dezil stehen.
- Verankert: Autopsie-Kennzahl `konz_*` im Register; `EngineConfig.renew_rank_pct`
  (Verlängerung), 31_ `--verlaengern`; Sperre 0 gemessen: ohne Wirkung
  (die Sperre greift nie, weil der Platz am Verkaufstag selbst neu besetzt wird).
- Status: Verlängerungs-Replays laufen (0,9 / 0,8 / mit Stop 3).

### 2.14 Das Vola-Ziel braucht das richtige Niveau
- Messung S&P `ranking_preis` trend_ok: ohne 12,9 % / −30,8 %; Ziel 0,15:
  11,1 % / −15,7 %; 0,20: 12,3 % / −18,7 %; **0,25: 12,9 % / −20,8 %**.
- Warum: 0,15 liegt unter der Normalvola eines 50-Aktien-Momentumkorbs
  (~18–22 %) und bremst dauerhaft; 0,25 greift nur in Stressphasen.
- Regel: Zielvola = leicht über der Medianvola des Korbs, nie darunter;
  auf jedem Panel neu prüfen (qlib 0,25 in Kette 2).
- Verankert: HYP-22 Register-Zeilen (0,15/0,20/0,25), Masterplan §6.12.
- Status: S&P bestanden mit 0,25, qlib offen.

## 3. Was funktioniert hat — und warum (die Gegenseite)

| Fund | Messung | Warum es trägt | Status |
|---|---|---|---|
| Ruhiges Volumen (`vol_schub_6m_neg`) | t_defl 3,9–5,2 auf allen Horizonten, 87–93 % positive Jahre | „Gefallene Aufmerksamkeit“: keiner handelt sie, deshalb keine Überreaktion | in-sample; HYP-17 auf 2. Panel offen |
| Momentum-Konsistenz | t_defl 4,0 (5 T) … 1,7 (63 T), 75–81 % positive Jahre | Weg statt Ziel: stetige Gewinner statt Sprünge | robust |
| Längere Haltedauer | Netto-CAGR steigt monoton H 2 → 42 | Kosten je Tag sinken, Signal hält | erledigt |
| Regime-Tor SPY > SMA200 | MaxDD halbiert (−55 % → −24 %) | Momentum-Crashs passieren unter der 200er | erledigt |
| Vola-Ziel | MaxDD −52,9 % → −30,7 % bei gleicher CAGR | Exposure sinkt, wenn Vola steigt — vor dem Crash, nicht danach | HYP-22 |
| **ML-Prognose (LightGBM auf dem Faktorzoo)** | 23_: Top-50 h21 **15,7 %** gegen SPY 14,3 % / Univ.EW 13,2 % / Handmix 9–10 % (qlib 2009–2020). 29_: jede Fassung mit ML-Score über SPY, dyn_ic 22,3 %. S&P: fest_h21 29,2 % gegen Handmix 23,2 % | Nichtlineare Kombination; Stärke im oberen Rand, nicht im IC (0,030 = bester Einzelfaktor); Wichtigkeit vol_schub_6m_neg > vola_niedrig > mom_12_1_vola | **kandidat — die Stellschraube**; Bestätigung S&P/Regime/H läuft (Kette ML); Architektur v2 in Masterplan §7.2 |

## 4. Offene Hypothesen mit registrierter Bestehensregel

| ID | Behauptung (kurz) | Test | Bestehen |
|---|---|---|---|
| HYP-21 | Rangverlust-Ausstieg schadet | 31_ exit-rank 0.0/0.2 | CAGR ≥ Referenz − 2 — widerlegt; exit 0,2 Teilverbesserung (qlib läuft) |
| HYP-22 | Vola-Ziel halbiert Drawdown | 22_ --vola-ziel 0.25 | MaxDD ≤ 0,7×, CAGR ≥ −1 — S&P bestanden, qlib läuft |
| HYP-23 | Explosionen = Lotterie | 30_ Teil C | Top-Dezil ≤ Universum + 1 |
| HYP-24 | Schnellerer Wiedereinstieg | 22_ --regimes trend_hyst | CAGR ≥ +1, MaxDD ≤ +5 — S&P verfehlt (+0,1), qlib läuft |
| HYP-17 | Ruhiges Volumen hält auf 2016–2026 | 21_ projekt | ≥ 75 % positive Jahre |
| HYP-06 | ML-Ranker schlägt Handmix OOS | 23_ auf projekt | CAGR ≥ Handmix + 2 |

---
*Dokumentation zu einem Softwareprojekt, keine Anlageberatung.*
