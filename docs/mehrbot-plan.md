# Mehrere Bots, ein Konto: Aufbau, Risikosteuerung und Datenerfassung

> Stand: 2026-08-04. Geschrieben nach vollständiger Durchsicht von
> `engine.py`, `live.py`, `daemon.py`, `state.py`, `journal.py`,
> `trading.py`, `compliance.py`, `shadow.py`, `fleet.py`, `universe.py`,
> `ratelimit.py`, `config.py`.
>
> Dieses Dokument ergänzt `docs/schattenbetrieb.md` und widerspricht ihm
> nicht. Der Schattenbetrieb regelt, wie **Varianten** gemessen werden.
> Hier geht es um die Frage, was davon je **echtes Geld** anfassen darf.

---

## Inhalt

- [0. Kurzfassung — der Befund in fünf Sätzen](#0-kurzfassung--der-befund-in-fünf-sätzen)
- [1. Was heute steht](#1-was-heute-steht)
- [2. Die drei harten Grenzen](#2-die-drei-harten-grenzen)
- [3. Warum Symbol-Aufteilung nicht das ist, wonach es aussieht](#3-warum-symbol-aufteilung-nicht-das-ist-wonach-es-aussieht)
- [4. Der empfohlene Aufbau: drei Ebenen](#4-der-empfohlene-aufbau-drei-ebenen)
- [5. Bauteil 1 — Risiko-Dach (`risiko.py`)](#5-bauteil-1--risiko-dach-risikopy)
- [6. Bauteil 2 — Kapital-Allokator (`allokation.py`)](#6-bauteil-2--kapital-allokator-allokationpy)
- [7. Bauteil 3 — Positionsbesitz (`state.py`-Migration)](#7-bauteil-3--positionsbesitz-statepy-migration)
- [8. Bauteil 4 — Kapitalflüsse und Einzahlungserkennung](#8-bauteil-4--kapitalflüsse-und-einzahlungserkennung)
- [9. Bauteil 5 — Datenerfassung: was heute fehlt](#9-bauteil-5--datenerfassung-was-heute-fehlt)
- [10. Kapazität: wie viele Symbole, wie viele Bots](#10-kapazität-wie-viele-symbole-wie-viele-bots)
- [11. Betrieb: Laptop, Raspberry Pi oder Server](#11-betrieb-laptop-raspberry-pi-oder-server)
- [12. Phasenplan](#12-phasenplan)
- [13. Abbruchkriterien](#13-abbruchkriterien)

---

## 0. Kurzfassung — der Befund in sechs Sätzen

1. **Der Engpass ist nicht die Symbolzahl, sondern der Spread.** Gemessen
   am 04.08.2026: Der Breakeven eines Rundlaufs liegt bei 5 bps Spread
   schon bei **0,142 %** — der gemessene Vorsprung der Strategie beträgt
   **+0,11 % je Trade**. Die Strategie liegt bei realistischen Kosten
   bereits *unter* Null, bevor irgendein zweiter Bot startet.

2. **Die Ausführungsqualität ist noch gar nicht belastbar gemessen.** Es
   gibt 30 echte Orders, davon 14 mit berechenbarer Slippage, und deren
   Mittelwert (+400 bps) wird von drei AMKR-Verkäufen mit einem
   offensichtlich falschen Referenzpreis dominiert (`expected_price`
   60,74 gegen Füllpreis 45,59). **Das ist die wichtigste offene Zahl des
   Projekts — und sie ist kaputt.**

3. **„Jeder Bot bekommt eigene 1.200 Symbole" geht nicht.** Von 8.464
   handelbaren Werten überleben 2.189 den Liquiditätsfilter (≥ 1 Mio. $
   Umsatz/Tag). Drei Bots à 1.200 bräuchten 3.600 — die gibt es nur, wenn
   man bis 250.000 $/Tag heruntergeht, und dort ist der Spread tödlich
   (siehe Satz 1).

4. **Mathematisch ist „N Bots mit disjunkten Symbolen" fast dasselbe wie
   „ein Bot mit N·15 Positionen"** — nur mit schlechterer Auswahl, weil
   die Rangliste künstlich in Töpfe zerschnitten wird. Genau diese
   Hypothese läuft bereits als `B07_mehr_positionen` in der Schattenflotte.

5. **Mehrere Bots auf einem Alpaca-Konto sind heute strukturell kaputt:**
   `state.position_meta` hat `symbol` als Primärschlüssel (kein `bot_id`),
   `build_portfolio()` gibt jedem Bot das *volle* Kontokapital, und
   `_check_exits()` würde die Positionen der anderen Bots verkaufen.
   Dazu fehlt jedes Risiko-Dach: kein Drawdown-Stopp, keine
   Tagesverlustgrenze, keine Klumpenkontrolle.

6. **Empfehlung:** Live bleibt **ein** Bot über das volle Universum. Die
   nächsten zwei Wochen gehören der Ausführungsmessung und dem
   Risiko-Dach — nicht der Bot-Vermehrung. Ein zweiter Bot verdreifacht
   nur die Kosten eines Vorsprungs, von dem noch nicht feststeht, ob es
   ihn nach Kosten überhaupt gibt.

---

## 1. Was heute steht

### 1.1 Die Live-Kette

```
scripts/12_daemon.py
   └── daemon.Daemon.run_forever()
         └── step()  alle 900 s während der Handelszeit
               ├── live.reconcile_fills()        Füllpreise nachtragen
               ├── _maybe_evaluate_outcomes()    1×/Tag: Ergebnisse zuordnen
               ├── recover()                     Zustand aus Broker + DB
               └── live.run_once()
                     ├── compliance.check_account()
                     ├── build_snapshot()        1.201 Symbole, ~500 Bars
                     ├── build_portfolio()       Alpaca + state.sqlite
                     ├── Engine.decide()         ← identisch zu simulate.py
                     └── trading.market_order()  je Entscheidung
```

Gemessen aus `~/Library/Logs/alpaca-bot/daemon.log`: ein vollständiger
Zyklus über 1.201 Symbole dauert **~158 Sekunden** (21:22:42 → 21:40:20
bei `interval_seconds=900`).

### 1.2 Was schon sehr gut ist

| Baustein | Datei | Warum es zählt |
|---|---|---|
| Ein Entscheidungspfad | `engine.py` | Backtest und Live rufen dieselbe `decide()`. Abweichung kann nur aus Ausführung stammen. |
| Lookahead-Sperre | `engine.MarketSnapshot.validate()` | Strukturell, nicht diszipliniert — die Engine *kann* nicht in die Zukunft sehen. |
| Entscheidung → Ergebnis | `journal.py` | `decisions` → `outcomes` über 1/3/5 Tage, mit Begründungs-Dictionary. |
| Trade-Lebenslauf | `lifecycle.py` | MAE, MFE, Nachlauf 1/5/10 Tage. Beantwortet „war der Stop zu eng?". |
| Ausführungsqualität | `journal.slippage_report()` | Trennt Slippage sauber von Kursdrift über Nacht. |
| Kostenmodell | `costs.py` | SEC/FINRA mit Prüfdatum, `breakeven_move_pct()`. |
| Flotten-Disziplin | `fleet.py` | Voranmeldung, Versuchszähler, `sqrt(2·ln N)`-Schwelle. |
| **Mehr-Bot-Buchführung** | `shadow.py` | `shadow_portfolio` hat bereits `PRIMARY KEY (bot_id, symbol)` und `shadow_cash` je Bot. |

**Der letzte Punkt ist wichtig:** Die Buchführung, die du live willst,
existiert im Schatten schon vollständig. Es fehlt nicht die Idee, sondern
die Übertragung auf den Kapitalpfad — und genau dort ist sie gefährlich.

---

## 2. Die harten Grenzen

### 2.1 Grenze 1 — Kapital wird doppelt vergeben

`live.build_portfolio()` liest:

```python
acct = account.account_summary()
return PortfolioState(
    cash=float(acct["cash"]),              # ← das GANZE Konto
    equity=float(acct["portfolio_value"]), # ← das GANZE Konto
    positions=positions,                   # ← ALLE Positionen, auch fremde
    ...
)
```

Zwei Bots auf einem Konto sehen also beide 100 % des Kapitals **und alle
Positionen des jeweils anderen**. Drei Folgen, alle schlimm:

1. **Größenberechnung.** `engine._find_entries()` rechnet
   `investable = portfolio.equity * cfg.target_invested`. Bei drei Bots
   ist das 3 × 90 % = 270 % Zielinvestition.

2. **Fremdverkauf.** `engine._check_exits()` iteriert über
   `portfolio.positions` — also auch über die Positionen der anderen
   Bots — und verkauft sie gegen die *eigenen* Stop-/Ziel-Marken.
   Bot B liquidiert Bot A.

3. **Wettlauf.** Weil `free = min(investable - already, portfolio.cash)`
   gilt, nimmt in der Praxis der Bot, der zuerst läuft, alles; die
   übrigen finden `free = 0` und handeln nie. Kein Fehler im Log, nur
   ein Bot, der stumm nichts tut.

### 2.2 Grenze 2 — Positionsbesitz existiert nicht

```sql
-- state.py, Zeile 36
CREATE TABLE IF NOT EXISTS position_meta (
    symbol        TEXT PRIMARY KEY,   -- ← kein bot_id
    ...
```

Und `daemon.recover()` ruft `store.sync_with_broker(broker_symbols)`, das
alle Metadaten löscht, die beim Broker nicht mehr auftauchen. Mit
getrennten Datenbanken je Bot würde jeder Bot die Positionen der anderen
als „beim Start vorgefunden" adoptieren und ihnen geschätzte Marken
verpassen (`entry * 0.93` / `entry * 1.10`).

### 2.3 Grenze 3 — kontoweite Ressourcen sind nicht teilbar

| Ressource | Wo geregelt | Warum sie bei N Bots bricht |
|---|---|---|
| **PDT-Daytrades** | `compliance.py` | 3 je 5 Werktage unter 25.000 $ — kontoweit, nicht je Bot. Drei Bots verbrauchen sie in einem Lauf. |
| **`MAX_POSITION_PCT`** | `trading._check_risk()` | Prüft gegen `portfolio_value` des *Kontos*. Bei Teilkapital je Bot bindet die Regel nie mehr. |
| **`MAX_ORDER_NOTIONAL`** | `trading._check_risk()` | Reines Sicherheitsnetz, kontoweit. |
| **Kaufkraft** | Alpaca | Wettlauf zwischen den Bots, wer zuerst zugreift. |
| **API-Minutenlimit** | `ratelimit.py` | **`RateLimiter._counters` ist ein Klassenattribut — prozesslokal.** Nur Tageslimits liegen auf Platte. Drei Daemon-*Prozesse* koordinieren ihr 200/min-Budget nicht und reißen es. |

Der letzte Punkt ist der stärkste technische Grund für **einen Prozess
mit N Engines** statt N Prozessen — genau wie es `docs/schattenbetrieb.md`
§5.1 für den Schatten bereits festlegt.

### 2.4 Grenze 0 — die Ausführungsmessung ist noch kaputt

Diese Grenze steht hinter allen anderen, deshalb bekommt sie die Null.

`journal.slippage_report()` liefert heute (Stand 04.08.2026):

```
Orders mit Fuellpreis : 30      davon 14 mit berechenbarer Slippage
Mittel (n-gewichtet)  : +297,3 bps
Median ueber Symbole  :  -12,1 bps
```

Ein Mittelwert von +297 bps bei einem Median von −12 bps bedeutet:
**Der Mittelwert misst Ausreißer, nicht Ausführung.** Die drei größten:

| Zeit | Symbol | Seite | `expected_price` | Füllpreis | „Slippage" |
|---|---|---|---|---|---|
| 28.07. 18:25 | AMKR | sell | 60,74 | 45,59 | +2.494 bps |
| 28.07. 19:01 | AMKR | sell | 60,74 | 45,97 | +2.432 bps |
| 28.07. 19:36 | AMKR | sell | 60,74 | 46,13 | +2.405 bps |

Dreimal derselbe Referenzpreis 60,74 zu drei verschiedenen Zeitpunkten,
bei Füllpreisen um 46 — das ist kein Ausführungsproblem, sondern ein
**stehengebliebener oder falsch zugeordneter Referenzkurs**. Es sind
zugleich genau die AMKR-Rundläufe, die den `reenter_cooldown_days`-Fehler
ausgelöst haben (`engine.py:258-265`).

Und selbst nach Entfernen aller Werte über 500 bps bleibt ein
merkwürdiges Bild: n = 11, Mittel **−157 bps**, Median **−31 bps**. Der
Bot würde also *systematisch besser* ausgeführt als sein eigener
Referenzpreis. Das ist unplausibel und deutet darauf hin, dass
`_reference_price()` über den **IEX-Feed** eine zu weite Spanne liefert
(`live.py:241` beschreibt das Problem für die fehlende Seite bereits).

**Konsequenz:** Die eine Zahl, die entscheidet, ob echtes Geld
vertretbar ist — die tatsächliche Ausführungsqualität —, ist derzeit
**nicht messbar**. Sie zu reparieren hat Vorrang vor jedem zweiten Bot,
denn ein zweiter Bot verdreifacht Kosten, die noch niemand beziffern
kann.

Zu prüfen sind drei Dinge:

1. **Wieso ist `expected_price` bei den AMKR-Verkäufen konstant?**
   Verdacht: `latest_quotes()` liefert vorbörslich/bei dünnem IEX-Buch
   einen alten Wert, und `_reference_price` übernimmt ihn ungeprüft.
2. **Referenz plausibilisieren.** Weicht die Quote um mehr als z. B. 3 %
   vom letzten Schlusskurs ab, ist sie zu verwerfen und der Schlusskurs
   zu nehmen — mit Kennzeichnung im Protokoll.
3. **16 von 30 Orders haben gar keinen berechenbaren Wert.** Ursache
   klären; ohne sie ist die Stichprobe nochmals halbiert.

---

## 3. Warum Symbol-Aufteilung nicht das ist, wonach es aussieht

Deine Annahme: „gleicher Bot, andere Symbole → gleiche Qualität, mehr
Daten." Der erste Teil stimmt für den *Code*, nicht für das *Verhalten*.

### 3.1 Die Identität

Heute wählt der Bot **die besten 15 aus 1.200**. Bei drei Bots à 400
Symbolen wählt jeder **die besten 15 aus 400** — zusammen 45 Positionen
aus demselben Topf von 1.200.

> **Drei Bots mit disjunkten Symbolen ≈ ein Bot mit `max_positions=45`.**

Nur eben schlechter: Die Aufteilung erzwingt, dass aus jedem Topf genau
15 kommen. Ist Topf A stark und Topf C schwach, kauft Bot C trotzdem
seine 15 schwächsten Kandidaten, während Bot A seine Nummer 16 bis 20
verwirft — obwohl die besser wären. **Die Aufteilung verschlechtert die
Rangliste, sie verbessert sie nicht.**

### 3.2 Was sich dadurch wirklich ändert

| Größe | Richtung | Anmerkung |
|---|---|---|
| Mittlere Signalstärke je Position | **schlechter** | Top 1,25 % → Top 3,75 % des Universums |
| Streuung / Klumpenrisiko | besser | mehr Namen, kleinere Einzelposition |
| Kosten in % des Kapitals | ~gleich | keine Fixkommission; Umschlag in Dollar bleibt gleich |
| Anzahl Beobachtungen je Woche | **3× besser** | das ist dein eigentliches Ziel |
| Attribution je Segment | besser | wenn Slices nach Segment geschnitten sind |

Der Tausch lautet also: **schwächere Signale gegen mehr Beobachtungen.**
Das kann sich lohnen — aber es ist eine Strategieänderung mit
Renditewirkung, keine reine Infrastrukturmaßnahme. Und weil laut
`docs/schattenbetrieb.md` §0.2 die Kosten bereits 72–109 % des
Bruttogewinns fressen, ist „schwächere Signale" hier kein Detail.

### 3.3 Die gute Nachricht

Genau diese Frage misst die Schattenflotte schon:

```python
# fleet.py, STARTAUFSTELLUNG
dict(bot_id="B07_mehr_positionen", achse="max_positions", wert="25", ...)
```

**Warte auf dieses Ergebnis, statt die Frage live mit echtem Geld neu zu
stellen.** Es kostet dich nichts außer Zeit, die ohnehin vergeht.

### 3.4 Wofür die Aufteilung trotzdem gut ist

Für **Attribution**: „Funktioniert die Umkehr bei Nebenwerten besser als
bei Standardwerten?" Das ist eine echte, offene Frage
(`universe.bias_probe()` existiert genau dafür). Aber du brauchst dafür
keine getrennten Bots — es reicht, jede Position mit ihrem
Liquiditätsdezil zu **beschriften** und danach auszuwerten. Ein Feld
statt einer Flotte.

---

## 4. Der empfohlene Aufbau: drei Ebenen

```
┌────────────────────────────────────────────────────────────────┐
│  EBENE 3  Risiko-Dach  (risiko.py)                    NEU      │
│  Kontoweit, über allem. Drawdown-Stopp, Tagesverlust,          │
│  Brutto-Exposure, Klumpen. Kann JEDEN Bot stilllegen.          │
└────────────────────────────────────────────────────────────────┘
             │ Freigabe / Drosselung
             ▼
┌────────────────────────────────────────────────────────────────┐
│  EBENE 2  Kapital-Allokator  (allokation.py)          NEU      │
│  Teilt das EINE Konto in Teilbücher. Jeder Bot bekommt ein     │
│  eigenes `PortfolioState` mit eigenem equity/cash und NUR      │
│  seinen Positionen.                                            │
└────────────────────────────────────────────────────────────────┘
             │ PortfolioState je Bot
             ▼
┌────────────────────────────────────────────────────────────────┐
│  EBENE 1  Bots  (engine.py, unverändert)                       │
│  N × Engine.decide(snapshot, teilportfolio)                    │
│  EIN Prozess, EIN Datenabruf, N Engines.                       │
└────────────────────────────────────────────────────────────────┘
```

**Wichtig:** Ebene 1 bleibt *unangetastet*. `Engine` ist zustandslos und
bekommt einen `PortfolioState` — dem ist egal, ob der das ganze Konto
oder ein Drittel beschreibt. Das ist der Grund, warum dieser Umbau
überhaupt sicher machbar ist.

### 4.1 Die Reihenfolge, in der gebaut wird

| # | Bauteil | Nutzen ohne Mehr-Bot-Betrieb | Priorität |
|---|---|---|---|
| 1 | **Risiko-Dach** | Hoch — schützt sofort den heutigen Einzelbot | **zuerst** |
| 2 | **Kapitalflüsse** | Hoch — ohne das ist jede Renditekennzahl falsch, sobald du einzahlst | **zuerst** |
| 3 | **Regime + Sektor protokollieren** | Hoch — heute fehlt der wichtigste Auswertungsschlüssel | **zuerst** |
| 4 | Positionsbesitz (`bot_id`) | Keiner — nur Vorbereitung | danach |
| 5 | Kapital-Allokator | Keiner — nur Vorbereitung | danach |

**Die ersten drei nützen dir sofort, auch wenn du nie einen zweiten Bot
startest.** Deshalb stehen sie vorn.

---

## 5. Bauteil 1 — Risiko-Dach (`risiko.py`)

Das ist die wichtigste fehlende Sicherung. Heute existiert *keine*
Verlustgrenze: `trading._check_risk()` prüft nur Einzelordergröße und
Kaufkraft. Ein Bot mit kaputter Logik verliert, bis nichts mehr da ist.

### 5.1 Schnittstelle

```python
# src/alpaca_bot/risiko.py
"""Kontoweites Risiko-Dach - die Grenze, die keine Strategie kennt.

Jede Regel hier ist eine Antwort auf die Frage: "Was, wenn die
Strategie NICHT funktioniert?" - nicht auf "wie optimiere ich sie?".
Deshalb steht dieses Modul UEBER der Engine und nicht in ihr: Eine
Engine, die ihre eigenen Notbremsen zieht, hat keine.

Grundsatz: Jede Sperre ist PERSISTENT und muss von HAND geloest
werden. Eine Sperre, die sich nach einer Stunde selbst aufhebt, kauft
genau in den Crash zurueck, wegen dem sie ausgeloest hat.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Risikogrenzen:
    """Die harten Grenzen. Bewusst wenige und runde Werte."""

    max_drawdown_pct: float = 0.20
    """Rueckgang vom Hoechststand des Kontos. Darueber: Vollsperre.

    20 % ist kein Optimum, sondern eine Setzung: Ab hier ist die
    Annahme "die Strategie funktioniert, nur gerade nicht" nicht mehr
    zu halten. Der Hoechststand wird um Einzahlungen bereinigt
    (siehe kapitalfluesse), sonst hebt jede Einzahlung die Marke und
    die Sperre loest nie aus."""

    tagesverlust_pct: float = 0.05
    """Verlust seit Tagesbeginn. Darueber: keine NEUEN Kaeufe mehr
    heute. Verkaeufe bleiben immer erlaubt - aus einer Position
    herauszukommen darf nie gesperrt sein."""

    max_brutto_exposure: float = 1.00
    """Summe aller Positionswerte / Kontowert. 1.00 = kein Hebel.
    Die Grenze existiert, weil `target_invested` je Bot gilt, diese
    Regel aber ueber ALLE Bots summiert."""

    max_sektor_pct: float = 0.35
    """Hoechster Anteil eines Sektors. 15 Halbleiterwerte sind
    EINE Wette, keine 15 - und genau so verhalten sie sich im Crash."""

    max_positionen_gesamt: int = 45
    """Kontoweite Obergrenze, unabhaengig von der Bot-Anzahl."""

    min_cash_reserve_pct: float = 0.05
    """Nie voll investiert. Puffer gegen Kursluecken und
    Zwangsverkaeufe."""

    verified: str = "2026-08-04"


@dataclass
class Freigabe:
    """Antwort des Risiko-Dachs auf eine geplante Order."""

    ok: bool
    gruende: list[str] = field(default_factory=list)
    """Warum blockiert - mit ZAHLEN, nicht nur mit Regelnamen.
    `blocked_by="RiskError"` allein ist im Nachhinein wertlos."""

    gekappt_auf: float | None = None
    """Wenn die Order nicht verboten, aber zu gross ist."""


def pruefe_order(bot_id: str, symbol: str, seite: str, betrag: float,
                 *, konto: dict, positionen, grenzen=Risikogrenzen()) -> Freigabe:
    """Vor JEDER Order. Verkaeufe passieren immer (allow_closing)."""


def pruefe_konto(grenzen=Risikogrenzen()) -> Freigabe:
    """Einmal je Zyklus, VOR dem Entscheiden. Loest die Vollsperre aus."""


def sperre_setzen(grund: str, kennzahlen: dict) -> None:
    """Schreibt die Sperre nach state.sqlite. Ueberlebt Neustarts."""


def sperre_loesen(bestaetigung: str) -> str:
    """Nur von Hand. `bestaetigung` muss woertlich
    'ich habe die Ursache verstanden' lauten - eine Reibung, die
    verhindert, dass man im Schock einfach weiterlaufen laesst."""
```

### 5.2 Tabelle

```sql
-- ergaenzt state.py SCHEMA
CREATE TABLE IF NOT EXISTS risiko_sperre (
    id           INTEGER PRIMARY KEY CHECK (id = 1),
    aktiv        INTEGER NOT NULL DEFAULT 0,
    grund        TEXT,
    kennzahlen   TEXT,          -- JSON: equity, hoechststand, drawdown
    gesetzt_am   TEXT,
    geloest_am   TEXT,
    geloest_von  TEXT
);

CREATE TABLE IF NOT EXISTS kapital_verlauf (
    ts           TEXT PRIMARY KEY,
    equity       REAL NOT NULL,
    cash         REAL NOT NULL,
    exposure     REAL NOT NULL,   -- Summe Positionswerte / equity
    n_positionen INTEGER NOT NULL,
    hoechststand REAL NOT NULL,   -- einzahlungsbereinigt
    drawdown_pct REAL NOT NULL
);
```

`kapital_verlauf` ist **neu und wichtig**: `heartbeat` hält heute nur den
*letzten* Wert. Es gibt damit keine Equity-Kurve in Zyklusauflösung —
also keine Möglichkeit, im Nachhinein zu sehen, wann ein Drawdown begann.

### 5.3 Einbau

In `daemon.step()`, direkt nach `compliance.check_account()`:

```python
frei = risiko.pruefe_konto()
if not frei.ok:
    print(f"  RISIKO-SPERRE: {'; '.join(frei.gruende)}")
    self.store.heartbeat(ok=True, error="risiko_sperre")
    return True          # kein Fehler - eine bewusste Entscheidung
```

Und in `live.run_once()` vor jedem Kauf, parallel zu
`compliance.assert_can_trade()`.

---

## 6. Bauteil 2 — Kapital-Allokator (`allokation.py`)

Erst nötig, wenn wirklich mehr als ein Bot live handelt.

### 6.1 Grundregel

> **Jeder Dollar hat genau einen Eigentümer, und jedes Symbol gehört zu
> genau einem Bot.**

Der zweite Teil ist der Trick, der alles vereinfacht: Weil du disjunkte
Symbol-Slices willst, ist der Eigentümer einer Position **aus dem Symbol
ableitbar**. Es braucht keine Aufteilung einer gemeinsamen AAPL-Position
zwischen zwei Bots — die kann es per Konstruktion nicht geben.

### 6.2 Schnittstelle

```python
# src/alpaca_bot/allokation.py
"""Ein Konto, mehrere Teilbuecher.

Alpaca kennt nur EIN Konto. Die Engine kennt nur EIN Portfolio. Dieses
Modul steht dazwischen und schneidet das Konto so zu, dass jeder Bot
einen PortfolioState bekommt, der (a) nur sein Kapital und (b) nur
seine Positionen enthaelt.

Warum das reicht: `Engine` ist zustandslos und rechnet ausschliesslich
relativ (`equity * target_invested`, `equity * max_position_pct`). Ein
Bot mit einem Drittel des Kapitals verhaelt sich exakt wie ein
eigenstaendiger Bot auf einem Drittel-Konto. Es ist KEINE Aenderung an
der geprueften Logik noetig - und genau das ist die Bedingung dafuer,
dass die Simulationsergebnisse weiter gelten.
"""

@dataclass(frozen=True)
class Buch:
    bot_id: str
    anteil: float
    """Soll-Anteil am Gesamtkapital. Summe ueber alle Buecher <= 1.0
    minus Risikoreserve - wird in `teile_auf` erzwungen, nicht
    gehofft."""
    symbole: tuple[str, ...]
    """Der Slice. MUSS disjunkt zu allen anderen Buechern sein."""


def pruefe_disjunkt(buecher: list[Buch]) -> None:
    """Wirft, wenn zwei Buecher dasselbe Symbol beanspruchen.

    Laeuft beim Start UND bei jedem Universums-Neuaufbau. Ohne diese
    Pruefung kann eine Position zwei Eigentuemer bekommen und beide
    Bots verkaufen sie - der zweite Verkauf geht ins Leere oder,
    schlimmer, in eine Short-Position."""


def teile_auf(konto: dict, positionen: pd.DataFrame,
              buecher: list[Buch], besitz: dict[str, str]) -> dict[str, PortfolioState]:
    """Schneidet Konto und Positionen in Teilbuecher.

    `besitz` (symbol -> bot_id) hat VORRANG vor der Slice-Zuordnung.
    Grund: Wird das Universum neu gebaut, koennen Symbole den Slice
    wechseln. Eine offene Position darf ihren Eigentuemer aber NICHT
    wechseln - sonst erbt ein Bot eine Position, deren Stop und Ziel
    ein anderer gesetzt hat, und die Haltefrist beginnt von vorn.

    Regel: Ein Symbol wechselt den Slice erst, wenn es GESCHLOSSEN ist.
    """
```

### 6.3 Kapitalzuteilung — wie der Anteil bestimmt wird

Drei Verfahren, aufsteigend nach Anspruch. **Starte mit dem ersten.**

```python
def anteile_gleich(bot_ids: list[str], reserve: float = 0.05) -> dict[str, float]:
    """Gleichverteilung. Der ehrliche Standard.

    Solange kein Bot einen NACHGEWIESENEN Vorsprung hat, ist jede
    andere Aufteilung eine Wette auf Rauschen. Bei drei Bots und 5 %
    Reserve also je 31,7 %."""


def anteile_nach_risiko(bot_ids, vola: dict[str, float], reserve=0.05):
    """Risikoparitaet: Anteil ~ 1/Volatilitaet des Teilbuchs.

    Erst sinnvoll ab ~60 abgeschlossenen Trades JE BOT - darunter ist
    die geschaetzte Volatilitaet selbst zu verrauscht."""


def anteile_nach_leistung(bot_ids, t_werte: dict[str, float], schwelle: float):
    """NUR wenn der t-Wert die Zufallsschwelle aus
    `fleet.schwelle_sigma()` ueberschreitet. Sonst faellt das Verfahren
    auf Gleichverteilung zurueck.

    Das ist keine Vorsicht, sondern Notwendigkeit: Bei N Bots liegt
    das erwartete Maximum allein durch Zufall bei sqrt(2*ln N) Sigma.
    Kapital nach unbestaetigter Leistung umzuschichten heisst,
    systematisch dem Rauschen hinterherzulaufen."""
```

### 6.4 Was `live.py` ändern muss

Genau **eine** Funktion, `build_portfolio()`, bekommt einen Parameter:

```python
def build_portfolio(snapshot, *, buch: Buch | None = None,
                    besitz: dict[str, str] | None = None) -> PortfolioState:
    """buch=None -> bisheriges Verhalten (ganzes Konto, ein Bot).

    Der Standardwert ist Absicht: Der heutige Einzelbot laeuft
    unveraendert weiter, ohne dass eine Zeile seiner Logik anders
    arbeitet. Der Mehr-Bot-Betrieb ist ein ZUSATZ, kein Umbau.
    """
```

---

## 7. Bauteil 3 — Positionsbesitz (`state.py`-Migration)

```sql
-- NEU: wer besitzt welche Position
CREATE TABLE IF NOT EXISTS position_besitz (
    symbol     TEXT PRIMARY KEY,   -- ein Symbol, ein Eigentuemer
    bot_id     TEXT NOT NULL,
    seit       TEXT NOT NULL
);

-- position_meta bekommt bot_id, behaelt aber symbol als Schluessel:
-- Es KANN nur eine offene Position je Symbol geben (Alpaca fuehrt sie
-- zusammen). Ein zusammengesetzter Schluessel (bot_id, symbol) wuerde
-- vortaeuschen, zwei Bots koennten dasselbe Symbol getrennt halten -
-- das ist beim Broker nicht darstellbar.
ALTER TABLE position_meta ADD COLUMN bot_id TEXT NOT NULL DEFAULT 'B00_basis';
```

Der Standardwert `'B00_basis'` macht die Migration rückwärtskompatibel:
Bestehende Positionen gehören dem heutigen Bot, alles läuft weiter.

`sync_with_broker()` und `load_positions()` bekommen einen optionalen
`bot_id`-Filter — ohne ihn verhalten sie sich wie bisher.

---

## 8. Bauteil 4 — Kapitalflüsse und Einzahlungserkennung

### 8.1 Die gute Nachricht zuerst

**Deine Einzahlungen werden schon heute korrekt verarbeitet.** Die Engine
rechnet ausschließlich relativ:

```python
investable = portfolio.equity * cfg.target_invested
cap        = portfolio.equity * cfg.max_position_pct * cfg.position_size_margin
mindest    = portfolio.equity * cfg.min_position_pct
```

`equity` wird in jedem Zyklus frisch von Alpaca geholt. Zahlst du ein,
wächst `equity`, und der Bot handelt ab dem nächsten Zyklus mit mehr
Geld — ohne Codeänderung. Genau dafür wurde der feste USD-Deckel
`max_order_notional` aus der Größenberechnung entfernt (siehe Kommentar
in `engine.py:213-225`).

### 8.2 Die schlechte Nachricht

**Jede Renditekennzahl wird falsch, sobald du einzahlst.** Eine Einzahlung
von 10.000 $ auf 100.000 $ sieht in einer Equity-basierten Auswertung wie
+10 % Gewinn aus. Betroffen: `kapital_verlauf`, der Drawdown-Zähler in
Bauteil 1, jeder Vergleich gegen Buy & Hold, und `shadow_eval`s Abgleich
zwischen Depot und Schatten.

**Das ist heute schon ein Datenqualitätsproblem, nicht erst bei mehreren
Bots.**

### 8.3 Lösung

`costs.actual_activities()` existiert bereits und kann genau das:

```python
# neu in account.py oder risiko.py
def kapitalfluesse_nachtragen(store: Store) -> int:
    """Holt Ein-/Auszahlungen von Alpaca und schreibt sie fort.

    Alpaca-Aktivitaetstypen:
        CSD  Cash Deposit        Einzahlung
        CSW  Cash Withdrawal     Auszahlung
        DIV  Dividende           Ertrag, KEINE Einzahlung
        INT  Zinsen              Ertrag, KEINE Einzahlung
        FEE  Gebuehren           Kosten

    Nur CSD/CSW veraendern die Bezugsgroesse der Rendite. DIV und INT
    sind echter Ertrag und muessen DRIN bleiben - wer sie herausrechnet,
    macht das System schlechter, als es ist.
    """
    from .costs import actual_activities
    n = 0
    for art in ("CSD", "CSW"):
        df = actual_activities(art, after=store.letzter_kapitalfluss(art))
        ...
    return n
```

```sql
CREATE TABLE IF NOT EXISTS kapitalfluesse (
    id          TEXT PRIMARY KEY,   -- Alpaca activity id, verhindert Doppelbuchung
    ts          TEXT NOT NULL,
    art         TEXT NOT NULL,      -- CSD | CSW
    betrag      REAL NOT NULL,      -- positiv = Einzahlung
    erkannt_am  TEXT NOT NULL
);
```

### 8.4 Die richtige Renditekennzahl

```python
def zeitgewichtete_rendite(verlauf: pd.DataFrame,
                           fluesse: pd.DataFrame) -> pd.Series:
    """Rendite, die von Ein- und Auszahlungen unberuehrt bleibt.

    Das Konto wird an jedem Kapitalfluss in Teilperioden geschnitten;
    die Teilrenditen werden verkettet. Nur so ist die Kennzahl
    vergleichbar mit Buy & Hold und mit dem Schattendepot - beide
    kennen keine Einzahlungen.

        r_gesamt = prod(1 + r_i) - 1
        r_i      = (equity_ende - fluss_i) / equity_start - 1
    """
```

**Und für den Drawdown:** Der Höchststand muss um Einzahlungen bereinigt
werden, sonst hebt jede Einzahlung die Marke und die Sperre löst nie aus.

---

## 9. Bauteil 5 — Datenerfassung: was heute fehlt

Du fragst, ob genug erfasst wird. Antwort: **erstaunlich viel, aber die
zwei wichtigsten Auswertungsschlüssel fehlen.**

### 9.1 Was heute je Trade gespeichert wird

| Feld | Tabelle | Datei |
|---|---|---|
| Begründung als Dictionary | `decisions.reasons` | `journal.py` |
| Score, Rang, Stop-/Zielabstand | `decisions.reasons` | `engine.py:809-811` |
| Kurs bei Entscheidung / bei Order / Füllpreis | `orders` | `journal.py` |
| Slippage vs. Kursdrift (getrennt!) | `orders` | `live.py:365-375` |
| Blockierungsgrund | `decisions.blocked_by` | `live.py` |
| Vorwärtsrendite 1/3/5 Tage | `outcomes` | `daemon.py:264` |
| MAE / MFE / Nachlauf 1/5/10 Tage | `lifecycle.trades` | `lifecycle.py` |
| Ausstiegsgrund | `lifecycle.exit_reason` | `daemon.py:185` |

Das ist mehr, als die meisten Privatprojekte je erfassen.

### 9.2 Die zwei kritischen Lücken

**Lücke 1 — Regime.** `shadow.py` speichert `regime_markt`, `regime_vola`,
`regime_breite` je Vorhersage. **Der Live-Pfad speichert nichts davon.**
Damit lässt sich die wichtigste Frage des Projekts am Depot nicht
beantworten: *In welcher Marktlage funktioniert die Strategie?*
`docs/schattenbetrieb.md` §13 nennt genau das „wo der echte Gewinn liegt".

**Lücke 2 — Sektor/Branche.** Nirgends erfasst. Ohne dieses Feld sind
weder Klumpenkontrolle (Bauteil 1) noch die Frage „ist der Vorsprung ein
Sektoreffekt?" beantwortbar.

### 9.3 Weitere Lücken, nach Nutzen sortiert

| # | Was fehlt | Warum es zählt | Aufwand |
|---|---|---|---|
| 1 | **Regime bei Entscheidung** | Wichtigster Auswertungsschlüssel | klein — Werte liegen in `shadow._regime()` bereit |
| 2 | **Sektor je Symbol** | Klumpenrisiko, Attribution | klein — einmalig laden, cachen |
| 3 | **Liquiditätsdezil je Symbol** | Ersetzt die Bot-Aufteilung für Attribution (§3.4) | klein — aus `universum.csv` |
| 4 | **Blockierungsgrund mit Zahlen** | `"RiskError"` allein ist wertlos | klein |
| 5 | **Wie viele Kandidaten standen zur Wahl** | „Rang 1 von 200" ≠ „Rang 1 von 3" | klein |
| 6 | **Equity je Zyklus** (`kapital_verlauf`) | Heute nur der letzte Wert | klein |
| 7 | **Kapitalflüsse** | Ohne das ist jede Rendite falsch | mittel |
| 8 | **Verworfene Kandidaten live** | Deckt der Schatten bereits ab | — |

### 9.4 Konkret: `reasons` erweitern

Der eleganteste Weg — `reasons` ist bereits ein freies Dictionary und
wird von `journal.decision_quality()` automatisch nach Schlüssel und
Wertband gruppiert. Neue Schlüssel werden also **ohne Schemaänderung**
auswertbar:

```python
# in engine._find_entries(), bei den bestehenden reasons["rang"] usw.
reasons["regime_markt"]   = snapshot.regime.markt      # "bullisch"|"baerisch"|"neutral"
reasons["regime_vola"]    = snapshot.regime.vola       # "ruhig"|"normal"|"unruhig"
reasons["regime_breite"]  = round(snapshot.regime.breite, 3)
reasons["sektor"]         = snapshot.sektor.get(sym, "unbekannt")
reasons["liq_dezil"]      = snapshot.liq_dezil.get(sym)
reasons["kandidaten_gesamt"] = len(candidates)
reasons["bot_id"]         = self.cfg.bot_id
```

Dafür bekommt `MarketSnapshot` drei neue, optionale Felder. Weil sie
optional sind, bleibt `simulate.py` lauffähig, ohne sie zu füllen.

---

## 10. Kapazität: wie viele Symbole, wie viele Bots

### 10.1 Der Symbolvorrat (vollständig gemessen 2026-08-04)

Gemessen mit `universe.build_universe(min_price=2.0,
min_dollar_volume=100_000, probe_days=90)` über **alle** 8.464
handelbaren NASDAQ/NYSE-Werte — nicht geschätzt:

| Stufe | Anzahl |
|---|---|
| Handelbar bei Alpaca, NASDAQ + NYSE | **8.464** |
| dito, inkl. ARCA (fast nur ETFs) | 11.157 |
| davon fractionable (Teilaktien möglich) | 4.972 |
| Mit auswertbaren Kursdaten (90 Tage) | 8.118 |
| Kurs ≥ $2, Umsatz ≥ 100.000 $/Tag | 3.484 |
| Umsatz ≥ 250.000 $/Tag | 3.031 |
| Umsatz ≥ 500.000 $/Tag | 2.594 |
| **Umsatz ≥ 1 Mio. $/Tag** | **2.189** |
| Umsatz ≥ 1 Mio. $/Tag **und** Kurs ≥ $3 | 2.183 |
| Umsatz ≥ 2 Mio. $/Tag | 1.736 |
| Umsatz ≥ 5 Mio. $/Tag | 1.105 |
| Umsatz ≥ 10 Mio. $/Tag | 678 |

Der Live-Bot nutzt heute die **obersten 1.200** nach Dollar-Volumen; das
Symbol auf Rang 1.200 setzt noch 4,3 Mio. $/Tag um.

### 10.2 Die Grenze ist der Spread, nicht der Umsatz

Bei 104.000 $ Konto und 45 Positionen wäre eine Position ~2.300 $ groß.
Gegen 500.000 $ Tagesumsatz sind das 0,46 % — vom **Marktimpact** her
unproblematisch. Man könnte also rein rechnerisch bis auf ~2.600 oder
sogar ~3.000 Symbole gehen.

**Man darf es trotzdem nicht.** Gerechnet mit `costs.breakeven_move_pct`
(Kurs 50 $, 100 Stück):

| Spread | Breakeven-Bewegung | Reicht der Vorsprung von +0,11 %/Trade? |
|---|---|---|
| 2 bps | 0,082 % | **ja** |
| 5 bps | 0,142 % | nein |
| 10 bps | 0,243 % | nein |
| 20 bps | 0,443 % | nein |
| 50 bps | 1,048 % | nein |

> **Das ist der eigentliche Befund dieses Dokuments.** Der gemessene
> Vorsprung der Umkehr-Strategie beträgt +0,11 % je Trade
> (`docs/schattenbetrieb.md`). Schon bei 5 Basispunkten Spread — dem
> Wert, mit dem `SimConfig` rechnet — liegt der Breakeven bei 0,142 %.
> Die Strategie ist bei realistischen Kosten **nicht kostentragfähig**,
> und das deckt sich exakt mit dem Befund in §0.2 des Schattenplans
> („Kosten fressen 72–109 % des Bruttogewinns").

Dünnere Werte haben systematisch weitere Spreads. Das Universum von
1.200 auf 2.600 auszudehnen heißt, genau die Werte aufzunehmen, bei
denen der Vorsprung mathematisch nicht mehr existiert.

### 10.3 Was rechnerisch ginge — und was davon sinnvoll ist

| Slices | Symbole je Slice | Unterste Liquidität | Bewertung |
|---|---|---|---|
| **1 × 1.200** | 1.200 | 4,3 Mio. $/Tag | heutiger Stand |
| 1 × 2.183 | 2.183 | 1,0 Mio. $/Tag | mehr Breite, deutlich weitere Spreads |
| 2 × 1.090 | 1.090 | 1,0 Mio. $/Tag | machbar |
| **3 × 727** | 727 | 1,0 Mio. $/Tag | machbar, Auswahl spürbar verdünnt |
| 3 × 865 | 865 | 500.000 $/Tag | Spread-Risiko im untersten Band |
| 5 × 437 | 437 | 1,0 Mio. $/Tag | Auswahl zu dünn — nicht empfohlen |
| 3 × 1.200 | — | 250.000 $/Tag | rechnerisch möglich, **wirtschaftlich sinnlos** |

**Belastbare Obergrenze: 3 Slices à ~727 Symbole.** Alles darüber kauft
Breite mit Spread — und Spread ist genau die Größe, an der die Strategie
heute schon scheitert.

### 10.3 Zeit- und API-Budget (kein Engpass)

Gemessen: **1.201 Symbole ≈ 158 s je Zyklus.**

Requests je Zyklus (`data.estimate_requests`, 500 Tage Historie,
Batchgröße 300): `ceil(300 · 500 / 10.000) = 15` je Batch.

| Symbole | Batches | Requests | geschätzte Dauer |
|---|---|---|---|
| 1.201 | 5 | 61 | ~158 s (gemessen) |
| 2.168 | 8 | 109 | ~285 s |
| 3.000 | 10 | 151 | ~395 s |

Limit: 200/min × 0,9 Sicherheit = **180/min**. Selbst 3.000 Symbole
passen in einen 15-Minuten-Takt.

**Aber nur in EINEM Prozess.** `RateLimiter._counters` ist ein
Klassenattribut und damit prozesslokal — drei Daemon-Prozesse fahren
3 × 180/min und reißen das Limit. Ein Prozess mit N Engines ist deshalb
nicht nur eleganter, sondern die einzige korrekte Variante.

### 10.4 Empfehlung zur Aufteilung

**Wenn** aufgeteilt wird, dann nicht zufällig, sondern nach einer Achse,
die eine Frage beantwortet:

```python
# allokation.py
def slices_nach_liquiditaet(universum: pd.DataFrame, n: int) -> list[tuple[str, ...]]:
    """Teilt nach Dollar-Volumen in n Baender.

    Beantwortet: "Funktioniert die Umkehr bei Nebenwerten besser?"
    Das ist eine offene Frage mit Literaturhintergrund - und die
    Antwort ist unmittelbar handlungsrelevant.

    ACHTUNG: Genau hier ist der Survivorship Bias am groessten
    (universe.DELISTING_RATE_PER_YEAR: micro_cap 18 %/Jahr gegen
    large_cap 2 %). Ein Vorsprung des untersten Bandes ist deshalb
    zuerst ein Verdacht, kein Befund - siehe universe.bias_probe().
    """


def slices_nach_sektor(universum, sektoren: dict) -> list[tuple[str, ...]]:
    """Teilt nach Sektor. Beantwortet: "Ist der Effekt sektorspezifisch?"

    Nachteil: Sektoren sind ungleich gross, die Slices dadurch auch."""


def slices_zufaellig(universum, n: int, seed: int = 42) -> list[tuple[str, ...]]:
    """Zufaellige Aufteilung. Beantwortet KEINE Frage - aber genau das
    macht sie zur richtigen Kontrolle: Drei zufaellige Slices sollten
    sich NICHT unterscheiden. Tun sie es doch, misst das System Rauschen,
    und jede Aussage der anderen Aufteilungen ist wertlos.

    Diese Variante zuerst laufen lassen. Sie ist der Nullversuch."""
```

**Der letzte Punkt ist der wichtigste des Kapitels:** Bevor du aus einer
Aufteilung irgendetwas schließt, muss die *zufällige* Aufteilung zeigen,
dass sie nichts zeigt.

---

## 11. Betrieb: Laptop, Raspberry Pi oder Server

### 11.1 Vergleich

| | Laptop (heute) | Raspberry Pi 5 (8 GB) | VPS (Hetzner CX22) |
|---|---|---|---|
| Kosten | 0 € | ~110 € einmalig + ~15 €/Jahr Strom | ~4 €/Monat |
| Läuft im Ruhezustand | **nein** | ja | ja |
| Stromausfall / WLAN | betroffen | betroffen | nicht betroffen |
| Zyklus 1.200 Symbole | ~158 s | ~400–600 s (geschätzt) | ~150–250 s |
| Dienstverwaltung | launchd | systemd | systemd |
| **TCC-Dateischutz-Probleme** | **ja** (siehe unten) | nein | nein |

### 11.2 Empfehlung: VPS

**Hetzner CX22** (2 vCPU, 4 GB RAM, 40 GB SSD, ~3,79 €/Monat, Standort
Nürnberg oder Falkenstein). Gründe:

1. **Die macOS-TCC-Probleme verschwinden.** Dein Code trägt heute zwei
   Umgehungen dafür: `config.py:17-31` legt die Datenbanken nach
   `~/Library/Application Support`, und `install_service.sh:36-52`
   verlegt die Logs nach `~/Library/Logs` — beides, weil launchd unter
   `~/Documents` nicht schreiben darf. Auf Linux gibt es das Problem
   nicht.

2. **Latenz ist irrelevant.** Du handelst Tagesbars in einem
   15-Minuten-Takt. Ob Frankfurt oder Virginia macht keinen Unterschied.

3. **4 GB reichen.** 1.200 Symbole × 500 Bars ergeben roh ~40 MB; mit
   pandas-Overhead, `per_symbol`-Dict und Signalrahmen liegt der Spitzen-
   bedarf bei ~1–2 GB.

Ein Raspberry Pi geht auch, ist aber langsamer, hängt an deiner
Stromversorgung und deinem Internet — und SD-Karten sterben unter
Dauerschreiblast (SSD per USB wäre Pflicht). Für ~4 €/Monat ist der VPS
die bessere Wahl.

### 11.3 Was für den Umzug zu ändern ist

```python
# config.py - der Pfad ist heute hart auf macOS verdrahtet:
DATA_DIR = Path.home() / "Library" / "Application Support" / "alpaca-bot" / "data"

# noetig:
import sys
if sys.platform == "darwin":
    _BASIS = Path.home() / "Library" / "Application Support" / "alpaca-bot"
else:                                    # Linux: XDG-Standard
    _BASIS = Path(os.getenv("XDG_DATA_HOME",
                            Path.home() / ".local" / "share")) / "alpaca-bot"
DATA_DIR = _BASIS / "data"
```

Weiter nötig:
- `scripts/install_service.sh` → systemd-Unit (`Restart=always`,
  `RestartSec=30`) statt launchd-plist.
- Zeitzone des Servers auf UTC setzen — der Code rechnet durchgängig in
  UTC, aber `dt.date.today()` in `daemon._maybe_evaluate_outcomes()`
  nutzt die lokale Zone.
- `.env` per `scp`, **nicht** ins Repo (steht bereits in `.gitignore`).

### 11.4 Ein Fund nebenbei

```python
# daemon.py:431 - die Wartezeit driftet
for _ in range(wait):
    if self._stop:
        break
    time.sleep(1)
```

Gemessen im Log: bei `idle_seconds=1800` liegen zwischen zwei Läufen
tatsächlich **1.994 s** (22:31:17 → 23:04:31) — rund 11 % Drift, weil
jeder `sleep(1)` etwas mehr als eine Sekunde kostet. Harmlos beim
Einzelbot, aber sobald mehrere Bots getaktet zusammenarbeiten sollen,
gehört das auf eine Frist statt auf eine Zählschleife:

```python
frist = time.monotonic() + wait
while not self._stop and time.monotonic() < frist:
    time.sleep(min(1.0, frist - time.monotonic()))
```

---

## 12. Phasenplan

### Phase A — jetzt bis ~18.08.2026 (2 Wochen, Einzelbot läuft weiter)

Ziel: **Sicherheit und Datenqualität**, ohne die Strategie anzufassen.

| # | Aufgabe | Datei | Prüfung |
|---|---|---|---|
| **A0** | **Referenzpreis reparieren** (§2.4) | `live.py` | Kein `expected_price` mehr > 3 % vom letzten Schluss; Anteil berechenbarer Slippage > 90 % |
| A1 | Risiko-Dach bauen | `risiko.py` (neu) | Sperre auslösen und lösen im Trockenlauf |
| A2 | `kapital_verlauf` je Zyklus schreiben | `state.py`, `daemon.py` | Equity-Kurve über 2 Wochen vorhanden |
| A3 | Kapitalflüsse erfassen | `account.py`, `state.py` | Testeinzahlung im Papierdepot wird erkannt |
| A4 | Regime in `reasons` schreiben | `engine.py`, `live.py` | `decision_quality()` gruppiert nach Regime |
| A5 | Sektor + Liquiditätsdezil laden und cachen | `universe.py` | Feld bei jeder neuen Entscheidung gesetzt |
| A6 | Sleep-Drift beheben | `daemon.py` | Abstand = `interval_seconds` ± 5 s |

**A0 ist die Bedingung für alles Weitere.** Ohne belastbare Slippage ist
weder entscheidbar, ob echtes Geld vertretbar ist, noch ob ein zweiter
Bot etwas kostet oder bringt.

**Nicht** in Phase A: irgendeine Änderung an `engine.py`s
Entscheidungslogik. Die zwei Wochen sollen eine saubere Vergleichsbasis
liefern.

### Phase B — ~18.08. bis ~25.08.2026 (1 Woche, Umbau)

| # | Aufgabe | Bedingung |
|---|---|---|
| B1 | `position_besitz` + `bot_id` in `position_meta` | Migration muss bestehende Positionen behalten |
| B2 | `allokation.py` mit `anteile_gleich` | `pruefe_disjunkt` als Test |
| B3 | `build_portfolio(buch=...)` | `buch=None` muss bitweise dasselbe liefern wie heute |
| B4 | Daemon: N Engines, EIN Datenabruf | Signal-Cache wie `fleet.Bot.signal_schluessel()` |
| B5 | **Erst im Trockenlauf**, mindestens 3 Handelstage | Keine Order, nur Protokoll |

### Phase C — ~25.08. bis ~22.09.2026 (4 Wochen, Messung)

> **Sperrbedingung.** Phase C startet nur, wenn nach A0 gilt: gemessene
> Slippage über mindestens 30 saubere Orders **< 8 bps im Median**, und
> der Rundlauf-Breakeven liegt damit unter dem gemessenen Vorsprung von
> 0,11 % je Trade. Ist das nicht erfüllt, ist die richtige Konsequenz
> **nicht** ein zweiter Bot, sondern eine Strategie mit geringerem
> Umschlag oder größerem Vorsprung je Trade. Mehr Bots multiplizieren
> einen negativen Erwartungswert.

Aufstellung — bewusst klein, weil jeder weitere Bot die
Zufallsschwelle hebt (`fleet.schwelle_sigma()`):

| Bot | Slice | Anteil | Hypothese |
|---|---|---|---|
| `L00_basis` | Rang 1–722 (liquideste) | 33 % | Referenz |
| `L01_mitte` | Rang 723–1.445 | 33 % | Mittleres Band |
| `L02_dünn` | Rang 1.446–2.168 | 29 % | Nebenwerte-Effekt — **Survivorship-Verdacht** |
| — | Reserve | 5 % | Risikopuffer |

Parallel im Schatten: dieselbe Aufteilung **zufällig** als Nullversuch
(§10.4). Unterscheiden sich die zufälligen Slices ebenso stark wie die
nach Liquidität, ist der Befund Rauschen.

### Phase D — ab ~22.09.2026 (Auswertung)

Entscheidung nach `fleet.schwelle_sigma()`, nicht nach Augenmaß. Bei
3 Live-Bots + 10 Schattenbots liegt der Versuchszähler bei 13 →
Schwelle `sqrt(2·ln 13) + 0,5 ≈ 2,76 Sigma`.

---

## 13. Abbruchkriterien

Schreibe diese Schwellen **jetzt** auf, nicht dann, wenn sie erreicht
sind:

| Ereignis | Konsequenz |
|---|---|
| Konto-Drawdown > 20 % (einzahlungsbereinigt) | Vollsperre, Handel aus, Ursachenanalyse |
| Tagesverlust > 5 % | Keine neuen Käufe bis zum nächsten Handelstag |
| Gemessene Slippage > 15 bps im Mittel über 30 Trades | **Alle** Backtest- und Schattenergebnisse neu bewerten (`costs.reconcile`) |
| `data_integrity.py` meldet 3 Läufe in Folge Befunde | Handel aus, bis geklärt |
| Bot handelt gegen eine Regel (`audit.py`) | Sofort aus — ein Regelbruch ist ein Logikfehler, kein Pech |
| Ein Slice gewinnt mit t < `schwelle_sigma()` | **Kein** Befund. Keine Kapitalumschichtung. |

---

## 14. Was dieser Plan bewusst nicht tut

- **Er verspricht keine höhere Rendite.** Mehr Bots erzeugen mehr
  Beobachtungen, nicht mehr Vorsprung. Der Vorsprung muss aus dem Signal
  kommen, und das Signal ist unverändert.
- **Er ändert die Strategie nicht.** `engine.py` bleibt bis auf drei
  zusätzliche Protokollfelder unberührt. Alles, was simuliert wurde, gilt
  weiter.
- **Er ersetzt den Schattenbetrieb nicht.** Der Schatten bleibt der Ort,
  an dem Varianten gemessen werden — kostenlos und ohne Kapitalrisiko.
  Live wird nur, was dort bestanden hat.
