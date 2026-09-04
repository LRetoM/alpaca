# Trendbot — der Strategie-Familien-Wechsel

> **Anlass (04.09.2026).** Nach ~90 Konfig-Varianten, 5 Lern-/RL-Methoden,
> 13 Flottenbots und der EDGAR-Prüfung ist der bisherige Ansatz
> ausgeschöpft: kurzfristige, querschnittliche Aktiensignale auf
> mittelgroßen US-Werten. Zwei eingebaute Killer — Spannen von ~12 bps
> (§G51) und Survivorship (+2–4 pp/Jahr, §G11).
>
> Dieses Dokument legt **vorab** fest, was stattdessen getestet wird, mit
> welchen Kriterien, und wie der Weg zu einem live-fähigen Bot bis zum
> **01.01.2027** aussieht. Es ersetzt keinen Befund — es rahmt die
> Messung, bevor eine Zahl existiert.

---

## 1. Die Idee

**Nicht das Tuning ändern, die Strategie-Familie.** Getestet wird
**Time-Series-Trendfolge / Dual-Momentum auf liquiden ETFs** über
mehrere Anlageklassen.

Warum genau das die beiden Killer umgeht:

| Killer | Warum er hier nicht greift |
|---|---|
| Spanne 12 bps | ~12 Rebalances/Jahr → 2 bps Kosten = ~0,2 %/Jahr Drag. ETF-Spannen liegen bei 1–2 bps. |
| Survivorship | ETFs auf große Anlageklassen verschwinden nicht. Kein Phantom-Vorteil. |
| „selbst erdachter Faktor" (§B3) | Zeit-Serien-Momentum ist der am besten belegte systematische Effekt überhaupt (AQR, 100+ Jahre, Dutzende Märkte). Keine Neuentdeckung. |

**Was es NICHT ist:** kein Renditewunder. Ziel ist *positiver
Erwartungswert nach Kosten bei kontrolliertem Drawdown* — im Backtest
grob Sharpe 0,5–0,8 über 25+ Jahre und etwa halb so tiefer Max-Drawdown
wie Buy-&-Hold SPY.

---

## 2. Was gebaut wird

| Baustein | Zweck |
|---|---|
| `src/alpaca_bot/trend.py` | Strategie + Backtest. Monatliches Rebalancing, Kosten beidseitig je Rebalance, Vol-Targeting-Overlay. Drei Strategien: `tsmom`, `dualmom`, `ma_filter`. |
| `scripts/43_trend.py` | Lauf über Altdaten (yfinance, tiefe Historie). `--vergleich` fährt alle Strategien + Benchmarks in einer Tabelle, `--walk-forward` prüft, ob die Auswahl vorwärts trägt. |
| `src/alpaca_bot/trend_store.py` | `trend.sqlite` — Läufe vergleichbar halten. |
| `tests/test_trend.py` | kein Lookahead, Kosten beidseitig, Vol-Targeting-Deckel, Rebalance-Kalender, Benchmark-Rechnung. |

**Wiederverwendet, nicht neu gebaut:** `statistik`, `costs`, der
Walk-Forward-Gedanke, die Jahr-für-Jahr-Ehrlichkeit. `trend.py` lebt
neben `engine.py`, ohne sie anzufassen — wie `spekulativ.py`.

---

## 3. Universum

Liquide ETFs, Total-Return-bereinigt (Dividenden reinvestiert — bei
Anleihen-ETFs ist die Ausschüttung der Großteil der Rendite):

| Klasse | ETF | yfinance ab |
|---|---|---|
| US-Aktien | SPY | 1993 |
| Industrieländer ex-US | EFA | 2001 |
| Schwellenländer | EEM | 2003 |
| US-Staatsanleihen mittel | IEF | 2002 |
| US-Staatsanleihen lang | TLT | 2002 |
| Gold | GLD | 2004 |
| Rohstoffe breit | DBC | 2006 |
| Immobilien | VNQ | 2004 |
| Cash | BIL / SHY | 2007 / 2002 |

`--universe broad` = alle (gemeinsame Historie ab ~2007, enthält 2008,
2011, 2015, 2018, 2020, 2022). `--universe core` = {SPY, IEF, GLD}
(ab ~2004). `--universe equity` = {SPY, EFA, EEM} (ab ~2003).

---

## 4. Die Strategien (vorab festgelegt, kein Sweep)

1. **`tsmom`** — absolute Momentum je Asset: 12-1-Monats-Rendite > Cash
   → halten, sonst raus. Gleichgewicht über die „an"-Assets.
2. **`dualmom`** — Rangliste nach 12-1-Momentum, Top-N halten; ist die
   beste Rendite ≤ Cash, alles in Cash (Antonacci-GEM-Logik).
3. **`ma_filter`** — Preis > eigener 200-Tage-Schnitt → halten, sonst
   raus. Gleichgewicht.
4. **Vol-Targeting-Overlay** (Modifikator): jede Position auf ~10 %
   Jahresvola skaliert, Bruttohebel gedeckelt auf 1,0.

Getestete Achsen: `lookback_monate` ∈ {6, 9, 12}, `vol_ziel` ∈ {aus,
10 %}. Das sind **6 Varianten je Strategie**, vorab notiert — die
Zufallsschwelle für 18+ Varianten wird im Bericht mitgeführt.

**Benchmarks in jeder Tabelle:** SPY Buy-&-Hold, 60/40 (SPY/IEF,
monatlich), Gleichgewicht-alle Buy-&-Hold.

---

## 5. Das Gate — festgelegt bevor eine Zahl existiert

Phase 1 (Historie) ist **bestanden**, wenn *alle* zutreffen:

1. Die beste Variante schlägt **60/40 netto** im Gesamtzeitraum **und**
   in ≥ 60 % der Kalenderjahre.
2. Max-Drawdown ist **kleiner** als der von Buy-&-Hold SPY (Ziel: < 60 %
   davon).
3. Der **Walk-Forward** (Lookback-Auswahl je Jahr auf Vergangenheit,
   Messung im nächsten Jahr) liefert einen Vorsprung gegen 60/40, der
   über die Jahre nicht das Vorzeichen wechselt.
4. Der Vorsprung überlebt eine **doppelte Kostenannahme** (4 bps statt 2).

Fällt eines durch → keine Phase 2. Dann ist belegt, dass auch diese
Familie auf einem Retail-Konto nichts trägt — ein Ergebnis, kein
Misserfolg.

---

## 6. Fahrplan bis 01.01.2027

| Phase | Zeitraum | Inhalt |
|---|---|---|
| **1 — Historie** | jetzt – ~20.09. | `trend.py` + Backtest, `--vergleich`, `--walk-forward`. Gate aus §5. Ergebnis als neuer §G in `BEFUNDE.md`. |
| **2 — Papier** | ~Okt/Nov | Bei bestandenem Gate: eigener Paper-Bot (monatlicher Rebalance-Cron), 4–6 Wochen. Prüfen: echte ETF-Fills = Modell, Rebalance-Logik, Slippage. |
| **3 — Live-Entscheidung** | Dez | Go-Live-Kriterien wie `BETRIEBSPLAN` §3.3: X Wochen Paper deckt Modell, Drawdown im Rahmen, Slippage < Y bps. |
| **Live** | 01.01.2027 | Bei erfüllten Kriterien: klein starten (10–20 % des Kontos), über Monate hochskalieren. |

**Der Umkehr-Bot läuft unverändert weiter** bis zum 10.10.-Termin —
nicht anfassen. Der Trendbot ist ein zusätzlicher, diversifizierender
Kandidat, kein Ersatz.

---

## 7. Ehrliche Vorbehalte

- Trendfolge hatte 2010–2020 eine schwache Dekade. Auch Phase 1 kann
  durchfallen.
- yfinance-ETF-Daten sind gut, aber die inoffizielle Yahoo-Schnittstelle
  ist kein Produktionspfad — für den Live-Betrieb kommen die Kurse von
  Alpaca.
- „Erfolgversprechend" ≠ „macht reich". Wer 50 %/Jahr erwartet, wird von
  jedem ehrlichen systematischen Ansatz enttäuscht.
