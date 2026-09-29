# Zusammenführung develop + Labor-Session — Abgleich der Erkenntnisse

> Stand: 2026-09-29. Zwei Arbeitsstränge liefen getrennt und sind heute in
> `main` zusammengeführt worden. Dieses Dokument hält fest, **was passiert
> ist, was sich widerspricht, was sich bestätigt** — und welche Zahlen
> deshalb neu gerechnet werden müssen. Die Rohdaten stehen in
> [BEFUNDE.md](BEFUNDE.md) (develop, von Hand) und
> [befunde-2027.md](befunde-2027.md) (Labor, automatisch).

## 1. Was passiert ist

| | develop | Labor-Session (29.09.) |
|---|---|---|
| Zeitraum | 04.08. – 13.09.2026 | 29.09.2026 |
| Basis | `main` vom 04.08. (fbb4368) | dieselbe Basis |
| Umfang | 91 Commits, 184 Dateien, 64 Testdateien | 17 Commits, 38 Dateien |
| Fokus | Schattenflotte, Umkehr-Bot live im Papier, Trendbot, Querschnitt, Ausbruch-Suche, Lernkern, Kostenmessung | Einzelaktien-Ranking über Wochen, Faktorzoo, ML-Score, Hybrid, Befundregister |
| Gedächtnis | `BEFUNDE.md` (G-Nummern, 8.700 Zeilen), `BETRIEBSPLAN.md` | `befunde.jsonl` + `befunde-2027.md`, `lehren-2027.md` |

**Die Labor-Session hat develop nicht gekannt.** Der Arbeitsbranch wurde
von `main` (Stand 04.08.) abgezweigt, nicht von `develop`. Im gesamten
Baum kam weder „Trendbot“ noch „dualmom“ noch eine G-Nummer vor. Folge:
Alles, was heute gemessen wurde, wurde ohne die 91 Commits an Vorwissen
gemessen — und ein Teil davon doppelt gebaut (Risiko-Dach).

### Konflikte und ihre Auflösung

Nur vier Dateien kollidierten (180 wurden automatisch zusammengeführt).
Regel des Auftrags: **bei Überschneidung gilt die heutige Fassung** — außer
dort, wo das die andere Seite kaputt gemacht hätte.

| Datei | Auflösung |
|---|---|
| `engine.py` | beide Seiten vereinigt: develops dynamischer Zeitausstieg (`zeitausstieg_dynamisch`) und Größenmodell (`groessen_modus`) UND heutige Verlängerung (`renew_rank_pct`), ML-/Hybrid-Score, Phasen-Stop, Tagesdeckel. Beide Verlängerungsregeln standardmäßig aus. Heutiger Schalter `sizing="gleich"` bildet auf develops `groessen_modus="gleich"` ab. |
| `simulate.py` | Parameter vereinigt (`ml_scores`, `nach_entscheidung`, `signal_frames`); Signalaufbau: übernommene Frames zuerst, sonst berechnen (Ranking-Strategie bleibt); ML-Spalte wird danach angehängt |
| `CLAUDE.md` | heutige Fassung als Hauptteil, develops Projektanweisungen **wörtlich** als Teil 9 (Statistik-, Test- und Sicherheitsregeln gelten weiter) |
| `risiko.py` | **develops Fassung bleibt kanonisch** (Abweichung von der Regel, s. u.); die heutige Klasse `RisikoDach` liegt als Archiv in `risiko_dach.py` mit eigener Datenbank |

**Abweichung Risiko-Dach — Begründung:** develop hat dasselbe Modul schon am
15.08. gebaut, mit denselben Grenzen (20 % Drawdown, 5 % Tagesverlust),
demselben Freigabesatz und denselben Tabellennamen, dazu Order-Prüfung,
Sektor- und Positionsgrenzen, Bericht, `20_risiko.py`, Regressionstests und
Mutationstests. Sechs weitere Stellen (Daemon, Health-Check, Tagesbericht,
Audit, Mutationstest, Skript) hängen daran. Die heutige Fassung zu behalten
hätte diese Stellen gebrochen und nichts Neues gebracht. Die Doppelprüfung im
Daemon (meine zweite, schwächere) ist entfernt; nichts Heutiges geht
verloren, weil die Klasse archiviert und getestet ist.

## 2. Abgleich der Befunde

Legende: **bestätigt** = beide Seiten kommen unabhängig zum selben Schluss;
**relativiert** = derselbe Befund, aber eine Zahl ändert sich; **offen** =
die Seiten messen Verschiedenes und widersprechen sich nicht, lassen sich
aber nicht direkt vergleichen.

| Thema | develop | Labor heute | Verhältnis | Konsequenz |
|---|---|---|---|---|
| Survivorship | G53: Jahres-Aktienauswahl 22,8 % CAGR, „fast ganz Survivorship“ (89 % des Universums fehlen); Literatur 4–8 %/J mit PIT-Universum | S&P-Panel (heutige Mitglieder) 22–31 %, qlib (mit Delistings) 7 % | **bestätigt** | S&P-Zahlen bleiben Obergrenzen; Erwartung aus qlib |
| Kurzfrist-Umkehr | Vorsprung +0,11 %/Trade < Breakeven; „Faktorraum aus Kurs und Volumen vermutlich ausgeschöpft“ (§C) | 5-Tage-Umkehr echt (t 3,8), aber kostenfressend; Top-20 verliert | **bestätigt** | keine Umkehr-Strategie |
| Momentum quartalsweise | G89: marktneutral t 0,86, „schwach positiv“ | Long-only Handmix + Tor: SPY − 3 bis SPY + 1 | **bestätigt** (ähnliche Größenordnung) | Momentum trägt den Drawdown-Schutz, nicht die Rendite |
| Kosten | G51/G54: gemessene Spanne **12,2 bps** (NBBO), kippt die Umkehr-Strategie von +1,95 % auf −2,84 % | Labor-Portfolios 20 bps Rundlauf, Engine-Replays 5 + 5 bps je Seite | **relativiert** | Rundlauf real ≈ 22 bps. Labor-Standard 20 bps stimmt. **Engine-Replays waren ≈ 7 bps/Rundlauf zu billig ≈ −0,7 Punkte/Jahr** — mit `--spread-bps 12.2` neu rechnen (§4) |
| ML gegen Handmix | G15: GBM schlägt den Score nicht (1.186 Symbole, t 0,71); „auf kleinen Universen sieht es besser aus — Mechaniktest, nie Bewertung“ | qlib (8.000 Symbole): ML +3,4 / +5 / +3,6 Punkte ohne Tor; S&P (600 Symbole): ±0; mit Tor −2,4 | **offen, nicht widersprüchlich** | Heutiges ML-Ergebnis gilt nach develops Standard als **nicht bestanden** (t deflationiert 1,2–2,0 < 3,55). Bleibt „kandidat“ — Projektcache entscheidet |
| Tauschregel / Rangverlust | G28: Tauschregel verkauft zu 80 % Gewinner | HYP-21: Rangverlust-Ausstieg nicht die Engine-Lücke; Schwelle 0,20 besser als 0,50 | **verwandt, bestätigt** | Ausstiegsregeln, die auf gefallene Kurse reagieren, verdächtig halten |
| Regime-Tor | G67: QQQ-Filter „kostet nichts, bringt nichts“ (Umkehr-Bot) | Tor halbiert Drawdown des Momentum-Rankings | **strategieabhängig** | Tor nur für Trendstrategien einsetzen |
| Statistik | B1/G12: naiver t „bedeutungslos“, ohne `horizont=` 39,5 % Fehlalarm | t deflationiert um √Horizont (grobe, konservative Näherung) | **relativiert** | Kandidaten des Labors mit `statistik.gruppierter_test(horizont=…)` nachprüfen (§4) |
| Versuchszähler | 0 von 48+ bestanden, Schwelle t > 2,85 (projektweit 4,90 in G89) | 105 Varianten, Schwelle 3,55 | **bestätigt** | beide Zähler addieren, nicht getrennt führen |
| Trend/Dual-Momentum | G52/G90: Trendbot Sharpe 0,88–1,35, MaxDD −16 %, positiv 2008 und 2022; „Träger fürs Jahresziel“ | Hybrid qlib: Sharpe 0,71–0,80, MaxDD −30 %, 2008/2022 ungemessen | **offen — der wichtigste offene Punkt** | gleiche Daten, gleiche Kosten, direkter Vergleich (§4) |

### Was das für die heutigen Kernaussagen heißt

1. **Der Hybrid (HYP-25) bleibt ein Kandidat**, nicht mehr. develops
   Erfahrung (G84–G89: „bestes Ergebnis des Projekts“ → jede Korrektur ging
   nach unten, am Ende t 0,86) ist die Warnung, dass ein in-sample
   entworfener Kandidat mit jeder ehrlichen Korrektur schrumpft. Erwartung
   deshalb weiter **SPY-nah bei kleinerem Drawdown**, nicht „weit darüber“.
2. **Der Trendbot ist der ernsthafte Konkurrent** für den Kern: weniger
   Drawdown, 2008 und 2022 gemessen, und er läuft schon im Schatten.
   Der Nutzerwunsch „Einzelaktien statt ETFs“ steht dem entgegen; die
   sinnvolle Synthese ist ein Test „Trend-Kern + Aktienauswahl-Schicht“
   (§4), kein Entweder-oder.
3. **Die Qualität des Vorgehens** unterscheidet sich: develop hat
   Regressionstests, Mutationstests, einen Nutzungsnachweis und ein
   vorab festgelegtes Entscheidungsdatum (10.10.2026, `BETRIEBSPLAN` §3.3).
   Die heutigen Änderungen dürfen diese Messung nicht stören — sie betreffen
   nur die **neue** Strategie `ranking`; `for_reversal` und die
   Flottenbots blieben unverändert (Tests in §3).

## 3. Prüfstand nach dem Merge

Gemessen am 2026-09-29 nach dem Merge, im selben Container, gegen die reine
`develop`-Basis (eigener Worktree, `PYTHONPATH` auf dessen `src`):

| Prüfung | reines develop | zusammengeführt |
|---|---|---|
| Betriebsschicht `pytest tests/` | 841 bestanden, 3 fehlgeschlagen, 2 übersprungen | **841 bestanden, 3 fehlgeschlagen, 2 übersprungen** |
| Forschungsschicht `00_selftest.py` | — (anderer Umfang) | **72 von 72** |
| Projektverfassung `09_selfcheck.py` | — | 10 Prüfungen, keine Befunde |

Die drei Fehlschläge sind in beiden Fassungen identisch und **umgebungsbedingt**
(keine API-Schlüssel in diesem Container, kein Feiertagskalender ohne Netz):
`test_daten::…cache_schreibt_und_liest…`, `test_haltedauer_feiertage::…ueberspringt_den_feiertag`,
`…max_hold_days_greift_jetzt_zur_richtigen_zeit`. Auf dem Rechner mit `.env` und
Netz sind sie zu wiederholen.

**Beim ersten Merge-Lauf brachen zwei Tests durch die heutigen Änderungen —
beide behoben, ohne die Tests aufzuweichen:**

1. `test_alle_felder_im_protokoll`: das neue Feld `ranking_weights` fehlte in
   `EngineConfig.as_dict()`. Behoben durch Aufnahme ins Protokoll — das war
   ohnehin nötig, sonst hätte der Regelabgleich Bots mit abweichenden
   Ranking-Gewichten nie bemerkt.
2. `test_keine_zweite_zaehlweise_im_quelltext`: `modell.py` und `finra.py`
   nutzen `bdate_range` in ihren Selbsttests für synthetische Kalender. Beide
   stehen jetzt mit derselben Begründung wie `selfcheck.py` auf der Ausnahmeliste.
   Keine Haltedauer wird damit gemessen.

## 4. Offene Arbeitsliste (in dieser Reihenfolge)

1. **Engine-Replays mit gemessenen Kosten** neu rechnen: `31_ … --spread-bps 12.2 --slippage-bps 5`
   für die Standardkonfiguration (qlib + S&P). Erwartung: −0,5 bis −1 Punkt.
2. **Gruppierter Test** (`statistik.gruppierter_test(werte, tage, horizont=H)`)
   auf die Kandidaten ML h21/h42 und Hybrid anwenden; Ergebnis in
   `BEFUNDE.md` (G99 ff.) und Register.
3. **Trendbot gegen Hybrid** auf denselben Daten und Kosten (`43_trend.py`
   / `45_trend_schatten.py` gegen `35_`), inklusive 2008 und 2022, soweit
   die Panels reichen.
4. **Trend-Kern + Aktienschicht** als Hypothese anmelden (vor dem Lauf).
5. Die offenen Läufe aus Masterplan §9.3 (HYP-22/24/26).
6. Entscheidung am **10.10.2026** (`BETRIEBSPLAN` §3.3) nicht durch
   Änderungen an der Live-Handelslogik stören.

## 5. Lehre aus dem Vorfall (nach `lehren-2027.md` §2.17)

**Zwei Stränge ohne Abgleich kosten doppelt:** ein Risiko-Dach zweimal
gebaut, Kostenmessung (12,2 bps) und Statistikregel (39,5 % Fehlalarm)
nicht gekannt, ein Tag Messungen auf zu billigen Kosten. **Regel:** Jede
Sitzung beginnt mit `git branch -a`, `git log --oneline origin/develop`
und dem Lesen von `BEFUNDE.md` §A–§C, bevor gemessen wird — und der
Arbeitsbranch wird vom aktuellsten Strang abgezweigt.
