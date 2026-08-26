# Taktikwechsel — der Plan, wenn keine Funde mehr zu erwarten sind

> **Anlass (26.08.2026).** 0 von 49 bzw. 63 Versuchen bestanden (§B6).
> Der Faktorraum aus Kurs und Volumen gilt laut §C als ausgeschöpft. Die
> Frage ist nicht mehr „welcher Faktor als nächster", sondern: **Was
> ändert man, wenn man keine Funde mehr erwartet?**
>
> Dieses Dokument ist der Plan dafür. Es ersetzt keinen Befund — es legt
> vorab fest, in welcher Reihenfolge und gegen welche Kriterien
> gearbeitet wird.

---

## 1. Die Arithmetik, aus der alles folgt

```
Ertrag/Jahr  =  ( Vorsprung je Trade − Kosten je Trade )  ×  Umschlag
```

Heute:

```
( 0,110 %  −  0,142 % )  ×  50  =  −1,6 % / Jahr
```

Drei Größen, drei Hebel. Bisher wurde **nur an der ersten gearbeitet** —
in 49 bis 63 Versuchen, ohne einen einzigen Treffer.

## 2. Der Denkfehler, der zuerst aus dem Weg muss

**„Weniger handeln" allein dreht das Vorzeichen nicht.**

Ist der Vorsprung je Trade kleiner als die Kosten je Trade, verliert
weniger Umschlag nur *langsamer*. Bei 10 statt 5 Tagen Haltedauer:

```
( 0,110 % − 0,142 % ) × 25  =  −0,8 % / Jahr
```

Halb so schlecht, immer noch negativ. Der Umschlag ist ein
**Verstärker**, kein Vorzeichen.

**Aber daraus folgt genau der richtige Hebel.** Die Kosten je Trade sind
**vom Horizont unabhängig** — ein Rundlauf kostet 0,142 %, egal ob die
Position fünf Tage oder fünfzig gehalten wird. Der Vorsprung je Trade
dagegen wächst mit dem Horizont, solange der Effekt überhaupt noch
nachläuft.

> **Es reicht also nicht, seltener zu handeln. Es muss ein Horizont
> gefunden werden, auf dem der Vorsprung je Trade über 0,142 % steigt.**
> Von 0,110 % auf 0,142 % sind das **+29 %** — nicht die Verdopplung, die
> man intuitiv erwartet.

## 3. Die eine Zahl, die zuerst gemessen wird

**Vorsprung je Trade als Funktion der Haltedauer**, über die 15-Jahre-
Historie, gegen Benchmark bereinigt:

| Haltedauer | Umschlag/Jahr | Vorsprung nötig | Status |
|---:|---:|---:|---|
| 3 Tage | 84 | > 0,142 % | `halten_kurz`, gemessen |
| 5 Tage | 50 | > 0,142 % | heutige Regel, **0,110 %** |
| 10 Tage | 25 | > 0,142 % | `halten_lang`, **t = +2,05** |
| 20 Tage | 12,6 | > 0,142 % | **fehlt** |
| 40 Tage | 6,3 | > 0,142 % | **fehlt** |

Die Kostenschwelle ist in jeder Zeile **dieselbe**. Das ist der Kern.

**Warum das nicht schon beantwortet ist:** §G11 hielt am 21.08.2026 fest
„Hätte längeres Halten geholfen? Nein" — gemessen mit der Simulation, die
derselbe Befund als fehlerhaft ausweist. Der 15-Jahre-Lauf sagt seither
`halten_lang` **t = +2,05**, die zweitbeste Achse von vierzehn. Die Frage
ist offen, nicht beantwortet.

**Zu tun:** `max_hold_days` 20 und 40 als Achsen in `32_lernlauf.py`,
ausgewertet **je Trade** statt nur als Endrendite.

## 4. Die vier Hebel, nach erwartetem Beitrag

### Hebel 1 — Kosten je Trade (die Zahl selbst)

Läuft. `37_spannen_messen.py`, Entscheidungsregel steht vorab in
`BETRIEBSPLAN` §3.4. §G39: die 5 bps sind nie gemessen worden. Ohne diese
Zahl ist jede Rechnung in diesem Dokument auf Sand gebaut.

### Hebel 2 — Haltedauer (Abschnitt 3)

Der einzige Hebel, der die Kostenseite **ohne** neuen Alpha-Fund
adressiert. Kostet einen Historienlauf, keinen Zählerplatz.

### Hebel 3 — Positionsgrößen

Gebaut am 26.08.2026: `EngineConfig.groessen_modus` mit
`inverse_vola` (Vorgabe, bitgleich zu vorher), `gleich`, `score`,
`score_vola`. Drei neue Lernlauf-Achsen.

**Warum das kein weiterer Faktorversuch ist:** Es ändert den Vorsprung je
**Dollar**, nicht je Trade — bei unverändertem Umschlag. Der Score
entscheidet heute nur, *ob* gekauft wird und in welcher Reihenfolge. Trägt
er Information, liegt Kapital an der falschen Stelle.

**Der Vorbehalt:** `score` ist die Achse mit dem größten
Konzentrationsrisiko. Weniger, größere Positionen heißt höhere Streuung
des Ergebnisses bei gleichem Erwartungswert — und `B07_mehr_positionen`
zeigt bereits t = −2,16, also dass **weniger** Breite geschadet hat.

### Hebel 4 — Ein-/Ausstiegslogik

Zuletzt, weil hier die meisten Freiheitsgrade und damit die größte
Gefahr des Überanpassens sitzen. Vorab festgelegt, was NICHT gemacht
wird:

* **Keine neuen Score-Bausteine.** §C: ausgeschöpft.
* **Keine Tauschregel.** §G28: vier Kriterien, alle negativ.
* **Keine Limitorder.** §G40: verworfen.

Was bleibt, sind zwei ungemessene Achsen, die §G19 bereits als
ungeprüft ausweist:

* `exit_score` — der Wert, der laut §E `target_atr` wirkungslos macht.
  Im Lernlauf als `exit_score_hoch`/`exit_score_null` vorhanden, aber nie
  gegen den Vorsprung **je Trade** ausgewertet.
* `reenter_cooldown_days` — §F beziffert die Kosten der Sperrfrist, ohne
  sie gegen den Nutzen zu stellen.

## 5. Reihenfolge und Termine

| # | Schritt | Kostet | Wann |
|---|---|---|---|
| 1 | Spannen-Messung auswerten (§3.4) | Stunden | **26.08.** |
| 2 | Haltedauer 20/40 im Lernlauf, Auswertung **je Trade** | Minuten | nach 1 |
| 3 | Positionsgrößen-Achsen im Lernlauf | Minuten | nach 1 |
| 4 | Was überlebt: Voranmeldung im Kandidatenregister | 1 Zählerplatz | frühestens **nach dem 10.10.** |
| 5 | Schattenbot, eine Achse | Wochen | nach 4 |

**Vor dem 10.10.2026 wird nichts an der Handelslogik geändert.** Die
Schritte 2 und 3 sind Historienläufe — sie dürfen verwerfen, nie
abnehmen (`UMBAUPLAN` §2.3), und kosten keinen Zählerplatz.

## 6. Die Regel gegen das naheliegendste Eigentor

Ein Taktikwechsel ist die perfekte Gelegenheit, die Bilanz von 0 aus 63
heimlich zurückzusetzen. Deshalb vorab:

1. **Der Versuchszähler wird nicht zurückgesetzt.** Auch nicht „weil wir
   jetzt etwas anderes machen".
2. **Neue Hypothese = ein Zählerplatz.** Unabhängige Replikation
   derselben Hypothese = keiner, kombiniert über
   `statistik.kombiniere_unabhaengig` (§G43) — das spart einen Platz,
   **nicht** die Hürde.
3. **Eine Achse je Bot**, auch beim Taktikwechsel.
4. **Vorab festgelegte Kriterien**, auch wenn sie diesmal schneller
   erreichbar aussehen.

## 7. Wann dieses Projekt eingestellt gehört

Vorab festgelegt, damit es später keine Verhandlung wird. **Einstellen,
wenn beides zutrifft:**

* Die gemessene Spanne (§3.4) liegt über 15 bps **und** ist durch eine
  zweite, nicht-IEX-Quelle bestätigt, **und**
* keine Haltedauer zwischen 5 und 40 Tagen erreicht im 15-Jahre-Lauf
  einen Vorsprung je Trade über der dann gültigen Kostenschwelle.

Dann ist belegt, dass eine Umkehr-Strategie auf mittelgroßen US-Werten
zu Retail-Kosten nicht handelbar ist — kein Scheitern, sondern das
Ergebnis. **Es wäre mehr wert als ein System, das leise Geld verliert.**

Was in diesem Fall bleibt, ist der Messapparat: 500 Tests, 76
Mutationen, ein Register, das sich selbst nicht belügt, und eine
dokumentierte Kette von 63 sauber verworfenen Ideen. Genau das messen
die meisten nie.
