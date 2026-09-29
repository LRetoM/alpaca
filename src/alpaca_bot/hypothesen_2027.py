"""Hypothesenkatalog 2027 - jede These VOR dem Test festgehalten.

Das ist die Voranmeldung, die `hypotheses.py` verlangt: Behauptung, Quelle,
exakte Messvorschrift, erwarteter Effekt. Wer erst testet und dann die
Hypothese formuliert, findet immer eine.

Prioritaet (P1 zuerst) folgt drei Kriterien:
  * Evidenzlage (repliziert? lebt nach Veroeffentlichung noch?)
  * Kosten-Tragfaehigkeit bei Alpaca (Spread, Umschlag, Auktionsorders)
  * Datenverfuegbarkeit im kostenlosen Rahmen

Die Skripte 21-26 liefern fuer jeden Eintrag den Historientest. Vorwaerts
bestaetigt wird ausschliesslich im Schattenbetrieb (docs/schattenbetrieb.md).
"""

from __future__ import annotations

KATALOG: list[dict] = [
    # ---------------------------------------------------------------- P1
    dict(
        hyp_id="HYP-2027-01",
        prio=1,
        behauptung="Querschnitts-Momentum (12-1 Monate) plus Konsistenz-Filter, Top 20-30, "
                   "3-6 Wochen Haltedauer, schlaegt SPY netto nach Kosten bei geringerem "
                   "Drawdown, wenn nur ueber SPY-SMA200 investiert wird.",
        quelle="Jegadeesh & Titman 1993; Daniel & Moskowitz 2016 (Crashs); "
               "eigene Messung scripts/22 (S&P 500 2016-2026: obere Schranke, Index-Bias)",
        quelle_typ="akademisch_repliziert", veroeffentlicht="1993-03-01",
        operationalisierung="labor.faktorzoo mom_12_1 + 0.5*mom_konsistenz, Z-Score-Mix, "
                            "Universum >= 25 Mio. $/Tag (Top ~800), Top 50, H=21, Kosten 20 bps Rundlauf, "
                            "Regime trend_ok; Messgroesse: Netto-CAGR minus SPY UND minus gleichgewichtetes "
                            "Universum, MaxDD, Jahre 2018/2020/2022 einzeln. (Top 20 aus 3.000 Werten ist "
                            "gemessen ein Verlustgeschaeft - masterplan §6.6.)",
        erwartung="Ueberschuss +2 bis +6 %-Punkte p.a. auf breitem Universum; auf heutigen "
                  "S&P-500-Konstituenten deutlich mehr (Bias). MaxDD ohne Filter ~ SPY, mit Filter kleiner.",
        skript="scripts/22_labor_portfolio.py --variante momentum",
    ),
    dict(
        hyp_id="HYP-2027-02",
        prio=1,
        behauptung="Ungewoehnlich hohes Volumen der letzten Woche (gegen 10 Wochen davor) sagt "
                   "positive Ueberrendite ueber die naechsten 4 Wochen voraus (High-Volume-Return-"
                   "Premium) - und verbessert Momentum als Zusatzfaktor.",
        quelle="Gervais, Kaniel & Mingelgrin 2001 JF; Wang 2021; ScienceDirect 2020 (Fundamentals)",
        quelle_typ="akademisch_repliziert", veroeffentlicht="2001-06-01",
        operationalisierung="labor.faktorzoo vol_schub_1w: mean(log V, 5 Tage) - mean(log V, 50 Tage davor). "
                            "IC auf 21/42 Tagen, Jahrestabelle; Portfolio 'volumen' und 'kombi' gegen 'kombi_ohne_volumen'.",
        erwartung="IC +0,01 bis +0,02 auf 21 Tagen, in >= 75 % der Jahre positiv; Kombi schlaegt Kombi-ohne-Volumen.",
        skript="scripts/21_labor_faktoren.py; scripts/22_labor_portfolio.py --variante kombi",
    ),
    dict(
        hyp_id="HYP-2027-03",
        prio=1,
        behauptung="Post-Earnings-Announcement-Drift laesst sich OHNE Analystendaten handeln: "
                   "die Kursreaktion am Ergebnistag (EAR) ersetzt die Gewinnueberraschung; "
                   "Werte im obersten EAR-Dezil driften 1-3 Monate weiter.",
        quelle="Brandt, Kishore, Santa-Clara & Venkatachalam 2008 (EAR: +7,55 % p.a. abnormal); "
               "Bernard & Thomas 1989",
        quelle_typ="akademisch_repliziert", veroeffentlicht="2008-01-01",
        operationalisierung="Ergebnistermine aus EDGAR 8-K Item 2.02 (Einreichungszeitstempel, PIT-perfekt). "
                            "EAR = Rendite Schluss T-1 bis Schluss T+1 minus SPY. Kauf am Schluss T+1 "
                            "(Einstieg T+2 Eroeffnung), Haltedauer 42 Tage, Top-Dezil je Woche. "
                            "Vorstufe ohne EDGAR: labor.faktorzoo ear_proxy (Sprung > 2 Sigma mit Volumen-Z > 2).",
        erwartung="Ueberschuss +3 bis +6 % p.a. long-only, Trefferquote ~55 %, wenig Umschlag.",
        skript="scripts/22_labor_portfolio.py --variante ear; danach edgar.py um 8-K erweitern",
    ),
    dict(
        hyp_id="HYP-2027-04",
        prio=1,
        behauptung="Opening-Range-Breakout NUR auf den 20 Aktien mit dem hoechsten relativen "
                   "Volumen der ersten 5 Minuten ist auch mit IEX-Daten und realen Kosten "
                   "profitabel (Sharpe > 1); ohne die Volumenauswahl ist ORB wertlos.",
        quelle="Zarattini, Barbon & Aziz 2024 SSRN 4729284 (7.000 Aktien 2016-2023, Sharpe 2,4-2,8); "
               "Zarattini & Aziz 2023 SSRN 4416622 (QQQ/TQQQ)",
        quelle_typ="akademisch_einzeln", veroeffentlicht="2024-02-16",
        operationalisierung="scripts/26_labor_orb_intraday.py mit Alpaca-5-Minuten-Bars, Regeln exakt wie im Paper, "
                            "Kosten 3+2 bps je Seite, 1 % Risiko je Trade, Hebel <= 4. Messung je Jahr 2019-2026, "
                            "getrennt nach RV-Band; Kontrolle: dieselbe Mechanik auf Zufallsauswahl statt Top-RV.",
        erwartung="Deutlich schwaecher als im Paper (IEX-Volumen ist nur ~2 % des Marktes). "
                  "Bestehen = Sharpe > 1 netto UND Top-RV schlaegt Zufallsauswahl mit t > 3.",
        skript="scripts/26_labor_orb_intraday.py",
    ),
    dict(
        hyp_id="HYP-2027-05",
        prio=1,
        behauptung="Der Regimefilter (SPY > SMA200 und/oder VIX < 25) senkt den maximalen "
                   "Drawdown jeder Long-only-Variante um mindestens ein Drittel, ohne die "
                   "CAGR um mehr als 2 %-Punkte zu senken.",
        quelle="Faber 2007; Barroso & Santa-Clara 2015 (vola-managed momentum); eigene Messung",
        quelle_typ="akademisch_repliziert", veroeffentlicht="2007-02-01",
        operationalisierung="scripts/22: jede Variante in 4 Regimefassungen; Vergleich MaxDD und CAGR; "
                            "Jahre 2008, 2018, 2020, 2022 einzeln.",
        erwartung="MaxDD -30 bis -50 % relativ; CAGR -1 bis +1 %-Punkte; 2020 kostet der Filter (spaeter Wiedereinstieg).",
        skript="scripts/22_labor_portfolio.py",
    ),
    # ---------------------------------------------------------------- P2
    dict(
        hyp_id="HYP-2027-06",
        prio=2,
        behauptung="Ein Gradient-Boosting-Ranker auf dem Faktorzoo erreicht out-of-sample einen "
                   "IC von >= 0,03 auf 21 Tagen (das Doppelte des besten Einzelfaktors) und ein "
                   "Top-20-Portfolio mit Sharpe > 1 netto.",
        quelle="Gu, Kelly & Xiu 2020 RFS; Springer OR Spectrum 2022 (10-1 Spread 0,6 %/Monat GBM)",
        quelle_typ="akademisch_repliziert", veroeffentlicht="2020-02-01",
        operationalisierung="scripts/23: LightGBM, expanding window, jaehrlich, Embargo H+5, Ziel = Rang der 21-Tage-Rendite. "
                            "IC je Jahr mit t; Portfolio Top 20, H=21, 20 bps.",
        erwartung="IC 0,02-0,04; Sharpe 0,8-1,3 brutto; 2020/2022 negativ moeglich.",
        skript="scripts/23_labor_ml_ranking.py",
    ),
    dict(
        hyp_id="HYP-2027-07",
        prio=2,
        behauptung="Die Overnight-Praemie (Schluss -> Eroeffnung) bei QQQ/IWM ist mit "
                   "Auktionsorders (MOC/MOO bei Alpaca, kein Spread) netto positiv, "
                   "insbesondere nur ueber SMA200.",
        quelle="Lou, Polk & Skouras 2019; Cooper, Cliff & Gulen 2008; Alpha Architect (Kosten fressen es "
               "bei Spread-Ausfuehrung); eigene Messung scripts/25: Breakeven 2,6-2,7 bps je Ausfuehrung",
        quelle_typ="akademisch_repliziert", veroeffentlicht="2008-01-01",
        operationalisierung="scripts/25 auf Alpaca-Tagesbars 2016-2026; dann 4 Wochen Papierhandel mit "
                            "time_in_force='cls' (Kauf) und 'opg' (Verkauf), gemessene Fill-Abweichung zum Auktionspreis.",
        erwartung="Brutto 8-13 % p.a., Sharpe 0,8-1,0; netto nur tragfaehig, wenn Auktions-Fills < 1 bps kosten.",
        skript="scripts/25_labor_overnight.py",
    ),
    dict(
        hyp_id="HYP-2027-08",
        prio=2,
        behauptung="Geclusterte Insiderkaeufe (>= 2 verschiedene Kaeufer in 30 Tagen, Code P) "
                   "sagen +4 bis +8 % abnormale Rendite ueber 6-12 Monate voraus, staerker bei "
                   "Small Caps und weit unter dem 52-Wochen-Hoch.",
        quelle="Cohen, Malloy & Pomorski 2012; arXiv 2602.06198 (2018-2024 Microcaps); 2iQ Cluster-Studien",
        quelle_typ="akademisch_repliziert", veroeffentlicht="2012-06-01",
        operationalisierung="edgar.insider_features auf dem Universum, cluster_score >= 0,5 als Ereignis; "
                            "Ereignisstudie mit Kontrollgruppe (events.py), Horizonte 21/63/126/252 Tage.",
        erwartung="Ueberschuss +2 bis +5 % ueber 6 Monate; selten (wenige Signale/Monat) -> Zusatzbaustein, kein Kern.",
        skript="scripts/06_event_study.py mit Insider-Ereignissen (Erweiterung noetig)",
    ),
    dict(
        hyp_id="HYP-2027-09",
        prio=2,
        behauptung="Kurzfrist-Umkehr (5 Tage) traegt netto NUR auf Large Caps mit engem Spread "
                   "und Haltedauer >= 10 Tagen; auf dem heutigen 1.200er-Universum mit 5 Tagen "
                   "Haltedauer ist sie strukturell unprofitabel.",
        quelle="de Groot, Huij & Zhou 2012 (30-50 bps/Woche netto nur bei Large Caps); eigene Messung "
               "docs/schattenbetrieb.md 0.2 (+1,4 %/J gegen +12 %/J SPY)",
        quelle_typ="akademisch_repliziert", veroeffentlicht="2012-01-01",
        operationalisierung="scripts/24 --variante reversal: Haltedauer 2..63 x Kosten 10/20/40 bps; "
                            "Universum-Schnitt nach Dollar-Volumen (Top 300 vs. Rest).",
        erwartung="Netto-CAGR steigt mit H bis ~10-21 Tage; Large-Cap-Schnitt besser; insgesamt < Momentum.",
        skript="scripts/24_labor_haltedauer.py --variante reversal",
    ),
    dict(
        hyp_id="HYP-2027-10",
        prio=2,
        behauptung="Hohes Short Interest (FINRA, halbmonatlich, kostenlos) sagt negative "
                   "Rendite voraus; niedriges Short Interest plus Momentum ist ein besserer "
                   "Long-Filter als Momentum allein. Taegliches Short-Volumen (Reg SHO) hat KEINEN "
                   "Prognosewert.",
        quelle="Boehmer, Huszar & Jordan 2010 ('The good news in short interest'); Rapach et al. 2016; "
               "Equibles 2025 (Reg-SHO-Tagesvolumen = Nowcast, kein Signal)",
        quelle_typ="akademisch_repliziert", veroeffentlicht="2010-01-01",
        operationalisierung="FINRA Equity Short Interest Files (Archiv ab 2014) laden, SI/Float und Days-to-Cover "
                            "als Faktor mit 1 Tag Verzug nach Veroeffentlichung; IC 21/42 Tage; Momentum x SI-Quintil.",
        erwartung="IC des SI-Faktors -0,01 bis -0,02 (invers nutzbar als Ausschluss); Reg-SHO-Tagesvolumen IC ~ 0.",
        skript="neu: scripts/28_labor_short_interest.py (Datenlader fehlt noch)",
    ),
    # ---------------------------------------------------------------- P3
    dict(
        hyp_id="HYP-2027-11",
        prio=3,
        behauptung="Naehe zum 52-Wochen-Hoch ist im heutigen Markt (2016-2026) KEIN positiver "
                   "Faktor mehr auf 1-2 Monaten (eigene Messung negativ), aber auf 6-12 Monaten.",
        quelle="George & Hwang 2004; eigene Messung scripts/21 (IC -0,015 auf 21 Tagen, 18 % Jahre positiv)",
        quelle_typ="eigene_messung", veroeffentlicht="2004-10-01",
        operationalisierung="scripts/21 mit Horizonten 126/252; Zerfallstest vor/nach 2004.",
        erwartung="Kurzfristig negativ (Anker-Effekt), langfristig schwach positiv; nicht als Kernfaktor.",
        skript="scripts/21_labor_faktoren.py --horizonte 63 126 252",
    ),
    dict(
        hyp_id="HYP-2027-12",
        prio=3,
        behauptung="Low-Volatility ist in Bullenjahren negativ (Beta-Effekt) und nur als "
                   "Positionsgroessen-Regel (1/Vola) nuetzlich, nicht als Auswahlfaktor.",
        quelle="Ang et al. 2006; eigene Messung scripts/21 (IC -0,03 auf 21 Tagen, 2016-2026)",
        quelle_typ="eigene_messung", veroeffentlicht="2006-02-01",
        operationalisierung="scripts/22 --variante lowvol vs. --vola-ziel 0.15 auf Momentum.",
        erwartung="Als Faktor negativ; als Sizing +20-40 % Sharpe.",
        skript="scripts/22_labor_portfolio.py --variante momentum --vola-ziel 0.15",
    ),
    dict(
        hyp_id="HYP-2027-13",
        prio=3,
        behauptung="Krypto (BTC/ETH bei Alpaca, 24/7, keine PDT-Historie) hat Zeitreihen-Momentum "
                   "auf 1-4 Wochen, das die 25-bps-Taker-Gebuehr bei woechentlichem Rebalancing ueberlebt.",
        quelle="Liu & Tsyvinski 2021; Springer FMPM 2025 (Krypto-Momentum instabil)",
        quelle_typ="akademisch_einzeln", veroeffentlicht="2021-01-01",
        operationalisierung="Alpaca-Krypto-Tagesbars ab 2021: Position = sign(Rendite 20 Tage) ueber SMA100, "
                            "woechentlich, Kosten 25 bps je Seite (Limit-Orders 15 bps).",
        erwartung="Sharpe 0,5-0,9 mit MaxDD > 40 %; kein Kern, Diversifikation.",
        skript="neu: scripts/29_labor_krypto.py",
    ),
    dict(
        hyp_id="HYP-2027-14",
        prio=3,
        behauptung="Nachrichten-Frequenz-Anomalie (news_z > 2) hat einen messbaren IC auf "
                   "5-21 Tagen; Tonalitaet allein hat keinen.",
        quelle="Tetlock 2007; Loughran & McDonald 2011; docs/schattenbetrieb.md 10.2",
        quelle_typ="akademisch_repliziert", veroeffentlicht="2007-06-01",
        operationalisierung="news_features.merkmale_je_symbol auf 2 Jahre Universum (Alpaca-News-Kontingent!), "
                            "IC je Kategorie; das Zusatzgewicht news=0.10 in ReversalWeights bleibt bis dahin ungeprueft.",
        erwartung="news_z IC +0,005 bis +0,015; ev_gewinn_uebertroffen als PEAD-Marker staerker als Ton.",
        skript="neu: scripts/30_labor_news_ic.py",
    ),
    dict(
        hyp_id="HYP-2027-15",
        prio=3,
        behauptung="Sektorneutrale Auswahl (Top-N je Sektor statt global) senkt den Drawdown von "
                   "Momentum in Rotationsphasen (2021-2022) messbar, kostet aber Rendite in "
                   "Themenmaerkten (2023-2024).",
        quelle="Moskowitz & Grinblatt 1999 (Industry Momentum); Praxis",
        quelle_typ="akademisch_repliziert", veroeffentlicht="1999-08-01",
        operationalisierung="Sektor je Symbol aus datasets/s-and-p-500-companies (GICS) bzw. EDGAR SIC; "
                            "labor.rangportfolio mit Sektorquote (Erweiterung noetig).",
        erwartung="MaxDD -5 bis -10 %-Punkte, CAGR -1 bis -3 %-Punkte.",
        skript="labor.py Erweiterung: max_sektor_anteil",
    ),
    dict(
        hyp_id="HYP-2027-16",
        prio=3,
        behauptung="Intraday-Momentum (erste halbe Stunde sagt letzte halbe Stunde voraus) auf SPY "
                   "ist nach 2020 und nach Kosten tot.",
        quelle="Gao, Han, Li & Zhou 2018 JFE; Diva 2024 (schwach 2023-24)",
        quelle_typ="akademisch_repliziert", veroeffentlicht="2018-03-01",
        operationalisierung="Alpaca-30-Minuten-Bars SPY 2016-2026; Regel: Vorzeichen(erste 30 min) -> Position 15:30-16:00; "
                            "Kosten 1 bps je Seite.",
        erwartung="Brutto +1 bis +3 % p.a., netto ~0. Widerlegung erwartet.",
        skript="neu: scripts/31_labor_intraday_momentum.py",
    ),
    # ---------------------------------------------------------------- aus dem Zoo
    dict(
        hyp_id="HYP-2027-17",
        prio=1,
        behauptung="'Ruhige' Aktien - Umsatz der letzten 6 Monate unter dem eigenen "
                   "Vorjahresmass (vol_schub_6m_neg) - schlagen 'laute' ueber die naechsten "
                   "1-2 Monate; der Effekt ist staerker und stabiler als das 1-Wochen-"
                   "Volumenpremium und ergaenzt Momentum (geringe Korrelation).",
        quelle="Eigene Messung scripts/21 auf qlib 2005-2020 (IC +0,018 auf 21 Tagen, t_defl 3,9, "
               "87 % positive Jahre; auf 42 Tagen IC +0,023); Literatur: langfristig hohes "
               "abnormales Volumen sagt NEGATIVE Rendite voraus (Banerjee & Kremer 2010; "
               "Wang 2021 - die 'Persistence or Reversal'-Linie)",
        quelle_typ="eigene_messung", veroeffentlicht=None,
        operationalisierung="labor.faktorzoo vol_schub_6m_neg = -(mean(log V, 126 Tage) - mean(log V, 252 Tage "
                            "davor)). IN-SAMPLE auf 2005-2020 gefunden -> Bestaetigung NUR auf 2016-2026 "
                            "(Projektcache) zaehlt: IC > 0,01, t_defl > 2, >= 75 % Jahre positiv. "
                            "Portfolio 'ruhig' (H=42) und 'kombi2' gegen 'momentum' und 'kombi'.",
        erwartung="Out-of-sample halber Effekt (IC ~0,01), aber weiter positiv; kombi2 Sharpe > momentum.",
        skript="scripts/21_labor_faktoren.py --panel projekt; scripts/22_labor_portfolio.py --variante kombi2",
    ),
    dict(
        hyp_id="HYP-2027-18",
        prio=1,
        behauptung="Ein Mehrfaktor-Ranking auf Einzelaktien mit 5-10 Tagen Haltedauer "
                   "(Umkehr fuer das Timing, Momentum-Konsistenz und ruhiges Volumen fuer die "
                   "Auswahl, Volumenschock als Verstaerker) hat einen groesseren Vorsprung je "
                   "Trade als die reine Umkehr und ueberlebt 10-20 bps je Rundlauf - die reine "
                   "Umkehr des heutigen Bots nicht.",
        quelle="Eigene Messung scripts/21 auf qlib 2005-2020 (t_defl h=5: reversal_5d 3,8, "
               "mom_konsistenz 4,0, vol_schub_6m_neg 5,2, vol_z_1d 2,6; paarweise wenig korreliert); "
               "de Groot/Huij/Zhou 2012 (Umkehr nur auf Large Caps netto)",
        quelle_typ="eigene_messung", veroeffentlicht=None,
        operationalisierung="scripts/22 --variante kurz (H=5) und kurz10 gegen reversal_rein; scripts/24 "
                            "--variante kurz mit H in {2,5,10,21}; Kosten 10/20/40 bps; Top 20 und Top 10; "
                            "Universum Top 800 nach Umsatz. Bestehen: Netto-CAGR > SPY bei 20 bps UND "
                            "kurz > reversal_rein in >= 75 % der Jahre.",
        erwartung="Brutto-Vorsprung 2-3x der reinen Umkehr; netto bei 10 bps positiv, bei 40 bps tot. "
                  "H=10 wahrscheinlich der Kompromiss zwischen Signalstaerke und Kosten.",
        skript="scripts/22_labor_portfolio.py --variante kurz; scripts/24_labor_haltedauer.py --variante kurz",
    ),
]


def nach_prio(prio: int | None = None) -> list[dict]:
    if prio is None:
        return list(KATALOG)
    return [h for h in KATALOG if h["prio"] == prio]


def tabelle() -> str:
    L = ["=" * 100, "  HYPOTHESENKATALOG 2027", "=" * 100]
    for h in KATALOG:
        L.append(f"\n  {h['hyp_id']}  [P{h['prio']}]  {h['skript']}")
        L.append(f"    {h['behauptung']}")
        L.append(f"    Erwartung: {h['erwartung']}")
    return "\n".join(L)
