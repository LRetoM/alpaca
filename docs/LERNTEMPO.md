# Lerntempo — wie wir schneller an belastbare Erkenntnisse kommen

> Stand: 22.08.2026. Ergänzt `BEFUNDE.md` (was wir wissen) und
> `BETRIEBSPLAN.md` (was gerade läuft) um die Frage: **Wie erhöhen wir
> die Zahl richtig ausgewerteter Erkenntnisse pro Monat?**
>
> Alle Zahlen hier sind gerechnet, nicht geschätzt. Die Quelle steht
> jeweils dabei.

---

## 1. Der Engpass ist nicht die Datenmenge

Das Projekt sammelt pro Tag ~1.200 Symbolbewertungen und ~10
Entscheidungen. Trotzdem dauert jede Aussage Wochen. Der Grund:

**Maßgeblich sind unabhängige Beobachtungen, nicht Datenpunkte.** Und
davon gibt es genau eine Sorte — den Handelstag. Alles andere ist
Vervielfachung derselben Information:

| Ebene | Was sie multipliziert | Was sie an Information bringt |
|---|---|---|
| 1.200 Symbole/Tag | Zeilen | wenig (alle sehen denselben Markt) |
| 10 Entscheidungen/Tag | Zeilen | nichts (§B1) |
| 5-Tage-Horizont | Zeilen | **negativ** (§G12: Fehlalarm 39,5 %) |

Zwei der drei Überlappungsebenen sind inzwischen sauber behandelt (§B1,
§G12). Damit steht fest, was wirklich zählt — und wo die Hebel liegen.

---

## 2. Die Versuchszählerfalle — der wichtigste Hebel

`fleet.schwelle_sigma()` rechnet:

```
schwelle = sqrt(2 · ln(n_versuche)) + 0,5
```

`n_versuche` zählt **alle je angemeldeten Bots und Hypothesen**, auch
stillgelegte. Jede Anmeldung erschwert damit dauerhaft **jeden anderen**
Versuch:

| Versuche | Schwelle | nötige Handelstage für B11 |
|---:|---:|---:|
| **16 (heute)** | **2,85** | **22** |
| 20 | 2,95 | 24 |
| 25 | 3,04 | 25 |
| 30 | 3,11 | 26 |
| 40 | 3,22 | 28 |

*(Handelstage aus `statistik.noetige_gruppen` mit dem heute an B11
gemessenen Effekt 0,0035 und Streuung 0,0057.)*

**Fünf unbedachte Anmeldungen kosten jeden laufenden Versuch rund drei
zusätzliche Handelstage.** Der Zähler ist unumkehrbar.

### Folge: Vorfiltern statt anmelden

Seit dem 21.08. fährt `scripts/10_simulate.py` nachweislich die
**Live-Strategie** (§G11) und der Bar-Cache funktioniert (§G11 Fund 4).
Damit lässt sich eine Idee über 6 Jahre in Minuten prüfen — **ohne den
Versuchszähler zu erhöhen**.

> **Regel:** Keine Anmeldung in die Flotte, bevor die Idee einen
> Historienlauf überstanden hat. Der Lauf darf **verwerfen, nie
> abnehmen** (BETRIEBSPLAN §4) — aber genau das ist sein Wert: Er
> kostet nichts und hält den Zähler niedrig.

---

## 3. Breite — der zweite große Hebel

Fundamentalgesetz der aktiven Verwaltung: `IR = IC · sqrt(BR)`. Der
Zeitbedarf bis zur Signifikanz skaliert mit `1/IR²`, also **linear mit
der Breite**.

Das Universum umfasst laut §H **2.189** Symbole über 1 Mio. $/Tag. Der
Bot handelt **1.200**.

| Symbole | IR | Zeitbedarf |
|---:|---:|---:|
| 1.200 (heute) | ×1,00 | ×1,00 |
| 1.600 | ×1,15 | ×0,75 |
| **2.189** | **×1,35** | **×0,55** |

**Die volle Breite halbiert die Wartezeit nahezu.** Kosten: ein Zyklus
über 1.201 Symbole dauert ~158 s (§H), über 2.189 entsprechend ~290 s —
bei einem 15-Minuten-Takt unkritisch.

**Aber:** Das ändert die Handelslogik und darf laut CLAUDE.md nicht
ungemessen live gehen. Reihenfolge: erst Historienlauf (§2), dann
eigener Flottenbot mit **genau dieser einen** Achse.

---

## 4. Was die Auswertung ehrlich macht — und was sie kostet

Die Korrektur aus §G12 **senkt** das Tempo: Sie entzieht dem t-Wert im
Mittel den Faktor 1,62. Das ist der Preis dafür, dass ein Befund auch
einer ist.

Gegenrechnung: Ohne sie wären 39,5 % aller Befunde Fehlalarme. Ein
Fehlalarm kostet nicht nur die Zeit bis zur Entdeckung, sondern eine
Anmeldung im Zähler (§2) — er verlangsamt also doppelt.

**Ehrliche Auswertung ist kein Gegensatz zum Tempo, sondern seine
Voraussetzung.**

---

## 5. Datenklarheit — die Regeln, die aus §G13 folgen

Das teuerste Muster dieses Projekts ist nicht der falsche Handel,
sondern die **stille falsche Zahl**. Chronik: `bars_held` = 0,
`after_10d` leer, `code_version` zwei Monate 'unbekannt' (66 % der
Daten), Bar-Cache nie getroffen, 98,4 % Simulationszeilen im
Live-Journal.

Daraus vier Regeln:

1. **Jede Auswertung nennt ihre Quelle.** `decision_quality` filtert
   jetzt per Vorgabe auf `live_trade`; die Gesamtsicht verlangt eine
   bewusste Angabe.
2. **Rekonstruktion wird markiert.** `bars_held_quelle` unterscheidet
   `gemessen` von `rekonstruiert`. Ohne den Vermerk ist ein Nachtrag
   später nicht mehr von einer Messung zu unterscheiden (§G11).
3. **Jeder Lauf trägt seine Konfiguration.** `lauf.json` neben jeder
   `trades.csv` (§G11) — eine Ergebnisdatei ohne sie ist wertlos.
4. **Neue Auswertungsfelder gehören in `_pflichtfelder_aus_gruenden()`.**
   Dann bewacht `data_integrity` automatisch, dass sie nicht verstummen.

### Was ein Wächter leisten muss — teuer gelernt

Beim Bau des Wächters entstanden zwei Fassungen, die *falsch* gewarnt
hätten (§G13). Beide Fehler haben dieselbe Form:

- **Nicht die Füllquote prüfen, sondern das Aufhören.** Sonst meldet
  jede Einführung eines Feldes wochenlang einen Ausfall.
- **Nicht Ungleiches in einen Topf.** `topup`-Zeilen täuschten einen
  Ausfall bei `buy` vor — und hätten einen echten verwässert.

**Eine Warnung, die immer leuchtet, wird weggeklickt.** Dann fällt auch
die echte nicht mehr auf. Ein Wächter mit Fehlalarmen ist schlechter als
keiner.

---

## 5a. Der 24/7-Betrieb — was er kann und was nicht

Seit dem 22.08.2026 hat der Schattenbetrieb vier statt drei Schritte:

```
einbuchen -> verifizieren -> entscheiden -> lernen
```

`lernen` prüft den Musterspeicher, sucht Kandidatenschnitte und meldet
Zerfall. Er stand vorher nur als Werkzeug bereit und lief nie (§G14).

**Alle vier Schritte sind idempotent.** Ohne neuen Handelstag tun sie
nichts und kosten Sekundenbruchteile — die Verifizierung fiel von 17 s
auf 1 s je Durchgang. Das ist die Voraussetzung dafür, häufig zu laufen,
ohne Rechenzeit und API-Kontingent zu verbrennen.

### Die harte Grenze, die 24/7 nicht verschiebt

Rund um die Uhr zu rechnen erzeugt **keine** zusätzlichen unabhängigen
Beobachtungen. Neue Information entsteht genau einmal je Handelstag,
wenn eine neue Tagesbar vorliegt. Alles andere ist Wiederholung.

Was das konkret heißt, mit den heutigen 19 Handelstagen:

| Auswertung | nötig | Stand | frühestens |
|---|---:|---:|---|
| gültiger 5-Tage-IC (t-Wert) | 15 Tage | 13 | ~jetzt |
| Muster als Kandidat anlegen | 20 Tage | 19 | Ende August |
| Muster **bestätigen** | 60 Tage | 19 | ~November |
| Flotten-Abnahme §3.3 | 20 auswertbare | 4 | 10.10. |

**Der Lernapparat läuft jetzt korrekt — er hat nur noch fast nichts zu
lernen.** Das ist kein Mangel, sondern die Disziplin bei der Arbeit.

### Warum das Anschalten ohne §G12 schädlich gewesen wäre

Der Kandidatenlauf lieferte am 22.08. `regime_vola == 'niedrig'` mit
einem IC von **+0,248 aus zwei Handelstagen** — dem Vierzehnfachen des
besten je gemessenen Faktors. Mit unkorrigiertem t-Wert wäre so etwas
als bestätigtes Muster in den Speicher gewandert, dauerhaft und
automatisch.

**Eine Lernschleife auf falscher Statistik lernt schneller — das Falsche.**
Bei 5-Tage-Fenstern läge die Fehlalarmquote bei 39,5 %.

### Reinforcement Learning

`src/alpaca_bot/rl/` ist gebaut und benennt selbst die vier Grenzen:
Datenhunger (DQN braucht Millionen Übergänge; 10 Jahre Tagesdaten sind
2.500 Schritte je Aktie), Nicht-Stationarität, Auswendiglernen des
Kurspfads, Zuordnungsproblem bei 95 % Rauschen. Es ist deshalb auf die
**Positionsgröße** angesetzt statt auf die Richtung, und jede Auswertung
läuft gegen eine Zufallspolitik.

Der Engpass ist auch dort nicht das Verfahren, sondern dieselbe Zahl wie
überall: unabhängige Handelstage. Mehr Rechenzeit ersetzt sie nicht —
**Breite (§3) und ein niedriger Versuchszähler (§2) tun es.**

---

## 6. Reihenfolge der nächsten Schritte

| # | Schritt | Wirkung | Bedingung |
|---|---|---|---|
| 1 | `bars_held` reparieren (`scripts/25`) | Health-Check wieder grün, Haltedauer-Auswertung korrekt | jetzt möglich |
| 2 | Kontext auch an `topup`/`sell` (§G13 Fund 3) | Sektor- und Regimeauswertung deckt die Mehrheit der Zuteilung ab | Protokollfeld, braucht Dienstneustart |
| 3 | Historienlauf als Pflichtfilter etablieren | hält den Versuchszähler niedrig | Prozessregel, sofort |
| 4 | Breite 1.200 → 2.189 historisch prüfen | halbiert bei Erfolg die Wartezeit | erst Historie, dann Flotte |
| 5 | B11 laufen lassen | — | Zwischenschau 12.09., Entscheidung 10.10. |

**Schritte 1–3 ändern keine Handelsentscheidung** und stören die laufende
B11-Messung deshalb nicht. Schritt 4 ändert sie und geht erst danach.

---

## 7. Was NICHT hilft

Damit diese Wege nicht ein zweites Mal geprüft werden:

| Idee | Warum nicht |
|---|---|
| Mehr Bots parallel anmelden | Hebt die Schwelle für alle (§2) — verlangsamt |
| Mehr Symbole je Bot **statt** Breite im Universum | Rangliste wird nur zerschnitten (§C, 04.08.) |
| Kürzerer Horizont für schnellere Ergebnisse | Der Effekt lebt auf 3–5 Tagen (§A) |
| Naiven t-Wert „zum Vergleich" zitieren | 39,5 % Fehlalarme (§G12) |
| Auf die Depotrendite schauen | Marktbewegung, keine Aussage (BETRIEBSPLAN §5.3) |
