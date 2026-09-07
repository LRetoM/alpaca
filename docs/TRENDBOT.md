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

### 5a. Gate-Ergebnis (04.09.2026, `BEFUNDE.md` §G52) — 2 von 4

| Kriterium | Ergebnis |
|---|---|
| 1. schlägt 60/40 gesamt + ≥ 60 % Jahre | **NEIN** (+277 % vs +361 %, 37 % der Jahre) |
| 2. Max-Drawdown < SPY B&H | **JA** (−16 % vs −52 %) |
| 3. Walk-Forward-Vorsprung stabil | **NEIN** (t = −1,34) |
| 4. überlebt doppelte Kosten | **JA** |

**Phase 1 nicht bestanden.** Die Strategie ist *risikoärmer, nicht
besser*: Sharpe 0,88 über beiden Benchmarks, Drawdown ein Drittel von
SPY, aber kein Renditevorsprung gegen ein simples 60/40.

### 5b. Produktentscheidung (Nutzer, 04.09.2026)

Der Nutzer hat entschieden, die defensive Variante trotz nicht
bestandenem Gate als Phase 2 vorwärts zu verfolgen — **als bewusste
Produktentscheidung** (§G52 Option 2), nicht als Gate-Umgehung. Das
Ziel wird damit ausdrücklich umdefiniert: von „schlägt den Markt" zu
„defensive Allokation, kompoundiert ~7,5 %/Jahr, verliert im Crash ein
Drittel dessen was SPY verliert". Die Phase-3-Hürde (unten) muss diese
Umdefinition auffangen.

**Festgeschriebene Konfiguration** (`trend_schatten.PHASE2_CONFIG`):
`dualmom`, 9-Monats-Lookback (skip 1), Top-3, 10 % Vol-Ziel, monatliches
Rebalancing, 2 bps Kosten. Änderungen hier sind eine neue Voranmeldung.

---

## 6. Fahrplan bis 01.01.2027

| Phase | Zeitraum | Inhalt | Stand |
|---|---|---|---|
| **1 — Historie** | erledigt 04.09. | `trend.py` + Backtest, Gate §5. | §G52, 2/4 |
| **2 — Vorwärts-Schatten (Pferderennen)** | 04.09. – ~30.11. | `trend_schatten.py` + `scripts/45_trend_schatten.py`, LaunchAgent `de.local.alpacatrend` (werktags nach US-Schluss). **Sendet keine Orders** — verfolgt **6 defensive Allokationen parallel** (`PHASE2_KANDIDATEN`: dualmom, tsmom, ma_filter, gem, risk_parity, risk_parity_defensiv), je simulierte Equity + Zielgewichte ab gemeinsamem Startdatum. | läuft ab 04.09. |
| **3 — Live-Entscheidung** | Dez | Hürde unten. | offen |
| **Live** | frühestens 01.01.2027 | Bei erfüllter Hürde: klein starten (10–20 % des Kontos), über Monate hochskalieren. | offen |

### 6a. Phase-3-Hürde — vorab festgelegt (04.09.2026)

Live geht der Bot nur, wenn *alle* zutreffen:

1. **≥ 8 Wochen** Vorwärts-Schatten ohne Abweichung zwischen berechneten
   und plausiblen Alpaca-Zielgewichten (Rebalance-Logik greift korrekt).
1a. **Aus dem Pferderennen wird die Strategie gewählt**, die vorwärts am
   saubersten läuft — bester risikoadjustierter Verlauf (Sharpe seit
   Start) UND kein Drawdown-Ausreißer. `dualmom` ist der Vorgabe-
   Kandidat; wird eine andere gewählt, ist das ausdrücklich erlaubt
   (alle 6 standen vorab fest, kein nachträgliches Cherry-Picking).
2. Der Drawdown der gewählten Strategie seit Start bleibt **über −20 %**
   (die Strategie soll ja gerade defensiv sein — reißt sie das früh,
   war die Prämisse falsch).
3. Ein separater **Live-Klempner-Test**: eine einzelne 100-$-ETF-
   Testorder auf dem Paper-Konto wird zum erwarteten Kurs (± 5 bps)
   gefüllt.
4. Der Umkehr-Bot-Termin (10.10.) ist entschieden — kein paralleler
   offener Umbau.

Fällt eines durch → kein Live zum 01.01., der Schatten läuft weiter.
**Diese Hürde wird nicht nachträglich gelockert** (§B2).

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
