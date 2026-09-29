# Umbauplan — vom Warten zum Messen

> **Stand: 24.08.2026.** Dieses Dokument ist eine **Arbeitsanweisung für
> eine neue Sitzung**. Es beschreibt, wie der Erkenntnisgewinn vom
> Vorwärtsbetrieb auf die Historie verlagert wird.
>
> **Vor der Ausführung lesen:** `BEFUNDE.md` §G31 (die Messung, die diesen
> Umbau begründet), §B2 und §B4 (die Fallen, die er nicht auslösen darf).

---

## 0. Warum — die Zahl, die alles begründet

Am 24.08.2026 wurde erstmals gemessen, wie fein beide Verfahren auflösen
(`BEFUNDE.md` §G31):

| Verfahren | nachweisbar ab | Beobachtungen |
|---|---:|---:|
| Schattenbetrieb am 10.10.2026 | 0,18–0,35 %/Tag | 31 Handelstage |
| **Historienlauf** | **0,0378 %/Tag** | **1.756 Handelstage** |
| wirtschaftlich entscheidend (§G23) | 0,0065 %/Tag | — |

**Der Historienlauf ist 5- bis 9-mal feiner** — und er liefert das
Ergebnis in Minuten statt in Monaten. Für die **Vorauswahl** ist das
Warten dem Historienlauf um Größenordnungen unterlegen.

Konkret an `B11_dyn_ausstieg_live`: sieben Jahre Historie ergaben
+56,6 % gegen +11,6 % bei 471 Trades weniger, t = +1,92 über 1.756 Tage.
Der Schattenbetrieb wird bis zum 10.10. nur 31 Tage haben und kann
Effekte dieser Größe **grundsätzlich nicht** auflösen.

---

## 1. Was live bleibt — und warum genau das

| Was | Bleibt? | Begründung |
|---|---|---|
| `12_daemon.py` (Handelsbot) | **ja, unverändert** | Er sammelt die einzige Stichprobe ohne Survivorship und wendet an, was abgenommen wurde |
| `16_shadow_daemon.py` | **ja, reduziert** | Siehe unten — er ist die einzige survivorship-freie Messung |
| Flottenbots ohne Messwirkung | **stoppen** | Kosten Rechenzeit, liefern nichts |

### Warum der Schattenbetrieb NICHT ganz abgeschaltet wird

Das ist der einzige Punkt, an dem dieser Plan vom ursprünglichen Wunsch
abweicht — und er hat einen gemessenen Grund.

Der Historienlauf hat **einen** Fehler, der sich bei manchen Fragen
**nicht** herauskürzt: Survivorship. Das Universum kennt nur heute
gelistete Symbole. Bei einer Regel wie `B11` — *Gewinner länger halten* —
wirkt das systematisch **zugunsten der Regel**: Genau die Fälle, in denen
ein laufender Gewinner später kollabiert, fehlen in den Daten.

`B09` mit fester Frist trifft das weniger. Der gemessene Vorsprung von
+45 Prozentpunkten ist deshalb eine **Obergrenze mit Schlagseite**, und
wie groß die ist, lässt sich ohne Point-in-Time-Universum nicht sagen.

**Der Vorwärtsbetrieb hat diesen Fehler nicht.** Er kostet nichts (er
läuft auf demselben Rechner mit) und liefert die einzige Kontrolle gegen
genau den Fehler, der die aussichtsreichste Idee begünstigt.

**Regel: Historie verwirft, Vorwärtsbetrieb nimmt ab.** Das ist keine
Vorsicht aus Prinzip, sondern die Konsequenz aus §G31.

---

## 2. Die Leitplanken, die NICHT fallen dürfen

Diese vier Punkte sind der Unterschied zwischen einem schnelleren System
und einer Maschine, die Scheingewinner produziert. Wer sie aufweicht,
bekommt Ergebnisse — nur keine, auf die man Geld setzen kann.

### 2.1 Walk-Forward, nie Rückblick

Die Auswahl darf **immer nur** sehen, was **vor** dem Bewertungsfenster
liegt:

```
Auswahl auf Jahr 1..k-1   ->   Bewertung in Jahr k    (nie gesehen)
Auswahl auf Jahr 1..k     ->   Bewertung in Jahr k+1
```

Grund: `BEFUNDE.md` §B2. Bei N Auswertungen liegt das erwartete Maximum
allein durch Zufall bei `sqrt(2·ln N)`. Bei 14 Bots × 22 Jahresscheiben
sind das **308 Auswertungen** und ein Zufallsmaximum von **t = 3,38** —
bevor ein einziger echter Effekt im Spiel ist.

`scripts/32_lernlauf.py` setzt das bereits um. **Nicht umbauen, ohne
diese Eigenschaft zu erhalten.**

### 2.2 Der Versuchszähler bleibt

Stillgelegte Bots zählen dauerhaft in `fleet.n_versuche` mit. Sie
herauszunehmen wäre keine Aufräumaktion, sondern das nachträgliche
Absenken der Hürde, gegen die gemessen wird.

**Auch Historienläufe zählen.** Ein Kandidat, der aus 14 Varianten
ausgewählt wurde, hat 14 Versuche hinter sich — nicht einen.

### 2.3 Die Historie nimmt nichts ab

Zwei Gründe, beide gemessen:

* **Survivorship**: 2–4 Prozentpunkte pro Jahr (§G11) — mehr, als die
  Strategie je verdient hat.
* **Der Nachrichtenfaktor fehlt** (§G24): `simulate.py` übergibt kein
  `news`, rechnet also die Vier-Faktor-Fassung. Live läuft die
  Fünf-Faktor-Fassung, und die Rangfolge dreht sich dadurch.

### 2.4 Die laufende Messung wird nicht unterbrochen

Bis zum **10.10.2026** keine Änderung an der Handelslogik des Live-Bots
(`CLAUDE.md`). Der Umbau betrifft ausschließlich die **Auswertungsschicht**.

---

## 3. Der Umbau, Schritt für Schritt

### Schritt 1 — Bestandsaufnahme (15 Min)

```bash
python scripts/22_tests.py
python scripts/18_health_check.py
python scripts/21_fleet.py              # Trennschärfe je Bot ansehen
```

Notieren, welche Bots laut Trennschärfetabelle **BITGLEICH** sind. Stand
24.08.2026: `B06_ohne_regime` und `B09_nachkauf` (dazu `B03`, `B05` —
bereits stillgelegt).

### Schritt 2 — Flottenschnitt (30 Min)

**Stoppen:** nur, was weder misst noch als Referenz gebraucht wird.

* `B06_ohne_regime` — bitgleich, wartet auf einen Regimewechsel.
  **Entscheidung nötig:** stoppen spart Rechenzeit, verliert aber genau
  die Messung, für die er existiert. Empfehlung: **laufen lassen**, er
  kostet fast nichts.
* `B09_nachkauf` — **darf nicht gestoppt werden**, er ist die
  registrierte Referenz von `B11` (§G19).

**Ergebnis dieses Schritts ist voraussichtlich: kein Schnitt.** Das ist
kein Fehlschlag — die Flotte ist bereits klein. Der Gewinn kommt nicht
aus dem Streichen, sondern daraus, dass sie **nicht mehr das
Hauptwerkzeug** ist.

### Schritt 3 — Datenbasis erweitern (1 Std)

Gemessen am 24.08.2026:

| Quelle | reicht zurück | Bars (AAPL) |
|---|---|---:|
| Alpaca | 2020-07 | 1.527 |
| **yfinance** (`shadow_daten.lade_bars`) | **2001-08** | **6.280** |

Über 120 Symbole: 7 Jahre = 197.044 Beobachtungen, **25 Jahre = 594.015**.

**Zu tun:**

1. ~~`scripts/32_lernlauf.py --jahre 25` als Standard etablieren.~~
   **Erledigt anders, siehe Punkt 3** — der Standard ist 15 geblieben
   (er stand schon vorher auf 15, das war der Skriptdefault).
2. Prüfen, wie viele Symbole des Universums 25 Jahre tragen (gemessen:
   63 % von 120; bei 15 Jahren 78 %).
3. **[x] Entschieden (25.08.2026): 15 Jahre bleiben der Standard.**
   Ausschlag gaben mehr Symbolabdeckung (78 % gegen 63 %) und näher an
   der heutigen Marktstruktur liegende Regime. Das Argument für 25 Jahre
   (mehr Bewertungsfenster für den Walk-Forward-Test) bleibt gültig,
   aber 12 Jahresscheiben reichen für einen t-Wert (siehe Schritt 4).
   `--jahre 25` bleibt als expliziter Zusatzlauf möglich, ist nur nicht
   der Default.
4. **[x] Bar-Cache geprüft (25.08.2026).** `shadow_daten.lade_bars` hat
   einen EIGENEN, bereits korrekten Tages-Cache (sha256-Schlüssel über
   das sortierte Symbolset, Datum im Dateinamen, hält die letzten 3
   Stände) — das ist NICHT derselbe Cache, der in §G11 Fund 4 kaputt
   war (der lag in `data.get_bars`/`universe.fetch_history`, wird vom
   Lernlauf nicht benutzt). Kein Fix nötig.

### Schritt 4 — Lernlauf ausbauen (2–3 Std) — [x] erledigt 25.08.2026

`scripts/32_lernlauf.py` existiert und läuft. Umgesetzt:

1. **[x] Ergebnisse persistieren.** Neu: `alpaca_bot.lernlauf_store`
   (`lernlauf.sqlite`, fünf Tabellen: `laeufe`, `jahresergebnisse`,
   `bot_vergleiche`, `walkforward_zeilen`, `kandidaten`). Jeder Lauf
   trägt `code_version` (§G5).
2. **[x] Gepaarten t-Wert je Bot** gegen die Basis. Neu:
   `alpaca_bot.lernlauf_eval.paarweiser_test` — dieselbe Rechnung wie
   `shadow_eval.vergleich_gepaart` (Tagesdifferenz zweier Equity-Kurven),
   aber ohne ShadowStore-Bindung, weil der Lernlauf keinen eigenen
   Versuchszähler hat.
3. **[x] Trennschärfe je Bot ausweisen** — `alpaca_bot.lernlauf_eval.trennschaerfe`,
   sinngemäß `shadow_eval.trennschaerfe` (§G22).
4. **[x] Batch über mehrere Signalgruppen.** Neuer Bot `ohne_regime`
   ändert `market_regime_filter` über die Gewichte (Sonderschlüssel
   `_weights` in `BOTS`, Muster wie `fleet._bot_aus_zeile` für
   `B06_ohne_regime`) — damit laufen erstmals ZWEI Signalgruppen statt
   einer, und `signal_schluessel` ist mit echten mehreren Gruppen
   geprüft, nicht nur mit einer.

### Schritt 5 — Kandidatenregister (1–2 Std) — [x] erledigt 25.08.2026

Was die Historie überlebt, darf **nicht direkt live**. Es braucht eine
Zwischenstufe mit Voranmeldung (§J Regel 2):

```
Tabelle `kandidaten`:
    kandidat_id, achse, wert, entdeckt_am, code_version,
    hist_effekt_pro_tag, hist_t, hist_fenster, walkforward_t,
    n_varianten_getestet,      <- fuer §B2
    status: {gefunden, im_schatten, abgenommen, verworfen}
```

`n_varianten_getestet` ist Pflicht: Ein Kandidat aus 14 Varianten ist
nicht dasselbe wie einer aus einer gezielten Hypothese, und die Schwelle
muss das abbilden.

**Umgesetzt** als `alpaca_bot.kandidatenregister` (Tabelle `kandidaten`
in `lernlauf.sqlite`, s. o.) mit erzwungenem Statusweg (`gefunden` ->
`im_schatten`|`verworfen` -> `abgenommen`|`verworfen`, kein Überspringen)
und Pflicht-Hypothese. CLI: `scripts/33_kandidaten.py`.

### Schritt 6 — Rückkopplung zum Live-Bot (Regel, kein Code)

**Der Weg einer Idee, verbindlich:**

```
1. Historienlauf   (Minuten)   darf VERWERFEN
2. Kandidatenregister          Voranmeldung mit Datum und Variantenzahl
3. Schattenbot     (Wochen)    einzige survivorship-freie Messung
4. Abnahme                     nach BETRIEBSPLAN §3.3
5. Live                        mit Dienstneustart und Regelabgleich
```

Stufe 3 darf **nur** überspringen, wer zeigen kann, dass Survivorship die
Frage nicht berührt. Für Ein-/Ausstiegsregeln ist das praktisch nie der
Fall.

---

## 4. Abnahmekriterien für den Umbau selbst

Der Umbau ist fertig, wenn:

- [x] `python scripts/22_tests.py` grün — 25.08.2026, 456 von 456 (beide
      Schichten, inkl. 23 neuer Tests aus `tests/test_lernlauf.py` und
      `tests/test_kandidatenregister.py`)
- [x] `python scripts/23_mutationstest.py` — alle Mutationen gefangen —
      25.08.2026, **71 von 71**, inkl. der neuen Mutation
      „Walk-Forward sieht das Bewertungsjahr mit"
- [x] `python scripts/18_health_check.py` grün — 25.08.2026, 🟢 GRÜN
      (die gelbe Datenintegritäts- und Regelabgleich-Notiz dort ist
      unverändert vorbestehend und betrifft den Live-Bot, nicht diesen
      Umbau)
- [x] `scripts/32_lernlauf.py` (15-Jahre-Standard) läuft durch und
      schreibt nach `lernlauf.sqlite` — siehe §G32 in `BEFUNDE.md` für
      Lauf-ID und Ergebnis
- [x] Der Walk-Forward-Block weist aus, ob die Auswahl ins nächste Jahr
      trägt — **mit t-Wert und Nachweisgrenze** — siehe §G32
- [x] Der Live-Bot ist **unverändert** (`git diff` auf `engine.py`,
      `live.py`, `daemon.py`, `trading.py` zeigt keine Zeile Änderung —
      geprüft 25.08.2026, dieser Umbau betraf ausschließlich
      `scripts/32_lernlauf.py`, `scripts/33_kandidaten.py` (neu) und die
      neuen Module `lernlauf_eval.py`, `lernlauf_store.py`,
      `kandidatenregister.py`)
- [x] Ein Regressionstest sichert die Walk-Forward-Eigenschaft: Eine
      Mutation, die das Bewertungsjahr in die Auswahl aufnimmt, muss
      rot werden — `tests/test_lernlauf.py::TestWalkForwardSiehtBewertungsjahrNicht`,
      gefangen von der Mutation oben

Der letzte Punkt ist der wichtigste. Ohne ihn ist die Trennung eine
Behauptung — und dieses Projekt hat mit Behauptungen schlechte
Erfahrungen gemacht (§G17, §G19, §G24). Er ist jetzt keine mehr.

---

## 5. Was dieser Umbau NICHT löst

Ehrlich vorweg, damit die nächste Sitzung es nicht neu entdeckt:

* **Der zentrale Konflikt bleibt.** +0,11 % Vorsprung je Trade gegen
  0,142 % Rundlauf-Breakeven (§A). Keine der 14 Achsen adressiert ihn.
* **Die Lernschleife bleibt offen** (§G25). Der Handelspfad liest kein
  gelerntes Artefakt. Das ist Absicht — ein sich selbst umschreibendes
  System wäre gefährlicher.
* **0 von 38 Versuchen bestanden** (§B6). Der Umbau macht das Verwerfen
  schneller, nicht das Finden wahrscheinlicher.
* **Erste Messung zum Verfahren selbst** (Probelauf 24.08., 8 Jahre,
  120 Symbole): Die aus der Historie getroffene Auswahl trug **nicht** ins
  nächste Jahr — mittlere Differenz −0,25 pp/Jahr, t = −0,11, und der
  gewählte Bot wechselte in **4 von 4** Übergängen. Der große Lauf über
  22 Fenster steht aus; fällt er ebenso aus, ist das ein Befund über die
  Methode und gehört nach `BEFUNDE.md`.

**Der Gewinn dieses Umbaus ist Geschwindigkeit beim Verwerfen.** Das ist
viel wert — 38 Fehlversuche in Minuten statt in Jahren. Es ist nur nicht
dasselbe wie ein besserer Bot.
