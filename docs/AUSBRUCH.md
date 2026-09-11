# Ausbruch-Werkstatt — kaufen, was gerade stark gestiegen ist

> Angelegt 11.09.2026. **Voranmeldung: Dieses Dokument entsteht, bevor
> ein einziges Ergebnis existiert.** Nach dem ersten Lauf wäre jede
> Festlegung hier eine Erzählung über eine bereits bekannte Zahl.

---

## 1. Die Idee

Alle 15 Minuten das ganze Universum absuchen. Springt ein Wert innerhalb
weniger Stunden um X Prozent, einen großen Teil des Kapitals
hineinlegen — in der Erwartung, dass die Bewegung weiterläuft. Verkauft
wird nach fester Zeit, bei Gewinnziel oder am Stop.

Bewusst ein volatiles System: große Gewinne sollen möglich sein, große
Verluste werden dafür in Kauf genommen.

**Das ist das Gegenteil der bisherigen Strategie.** `engine.py` kauft,
was *gefallen* ist (Umkehr). Diese hier kauft, was *gestiegen* ist
(Ausbruch/Momentum). Beide können nicht gleichzeitig recht haben — und
genau deshalb ist es ein sauber getrennter, eigener Versuch und kein
Parameter am bestehenden Bot.

## 2. Warum das überhaupt einen Versuch wert ist

Der Umkehr-Bot ist an der Kostenhürde gescheitert (§G54): Vorsprung
+0,11 % je Trade gegen 0,287 % Rundlaufkosten, Faktor 2,6 zu wenig.
Eine Idee, die diese Hürde nehmen soll, muss **je Trade deutlich mehr
verdienen** — nicht ein bisschen mehr.

Genau das ist das Argument für Ausbrüche: Eine Bewegung von 10–20 % in
Stunden ist zwei Größenordnungen über der Kostenschwelle. Wenn davon
auch nur ein Bruchteil nachläuft, trägt es die Kosten mühelos.

**Das Gegenargument, das genauso ernst zu nehmen ist:** Genau diese
Werte haben die weitesten Spannen. Die gemessenen 12,2 bps sind der
Median des *liquiden* Universums im Normalzustand. Ein Wert mitten in
einem 20-%-Sprung liegt deutlich darüber. Deshalb ist `spanne_bps`
einstellbar und sollte hier eher zu hoch als zu niedrig angesetzt
werden.

## 3. Was gebaut wurde

| Datei | Zweck |
|---|---|
| `src/alpaca_bot/ausbruch.py` | Die Strategie. Reine Rechnung, keine I/O, 23 Stellschrauben. |
| `src/alpaca_bot/ausbruch_daten.py` | Lokaler Bar-Vorrat als Parquet. Einmal laden, dann liest jeder Test von der Platte. |
| `src/alpaca_bot/ausbruch_store.py` | `ausbruch.sqlite`: Läufe, Trades, Depotkurve, Symbol-Bestenliste, **Versuchszähler**. |
| `scripts/46_ausbruch.py` | Oberfläche. Lokaler Server, Browser-UI, Live-Strom. |
| `src/alpaca_bot/ausbruch_suche.py` | Automatische Suche: Erkundung, Bergsteigen, Neustart — mit Lern-/Prüffenster. |
| `scripts/47_ausbruch_suche.py` | Live-Terminal für die Suche. |
| `tests/test_ausbruch.py` | 25 Tests, Schwerpunkt auf den Lügen-Stellen (unten). |
| `tests/test_ausbruch_suche.py` | 16 Tests, Schwerpunkt auf der Fenster-Trennung. |

**Handelt nicht.** Kein Import von `trading.py`, kein Dienst ruft es
auf. Der Weg zu echtem Geld führt über die Flotte
(`UMBAUPLAN` Schritt 6), nie von hier.

**Warum Browser statt Fenster:** `tkinter` fehlt in dieser
Python-Installation (`_tkinter` nicht vorhanden). Der lokale Server
braucht nur die Standardbibliothek, keine neue Abhängigkeit und keinen
`ratelimit.QUOTAS`-Eintrag — er spricht mit niemandem außer 127.0.0.1.

## 4. Die drei Stellen, an denen so ein Backtest lügt

Alle drei sind zu unseren Ungunsten aufgelöst und durch Tests
festgenagelt. **Wer eine davon umdreht, bekommt deutlich schönere Zahlen
und ein System, das live verliert.**

### 4.1 Lookahead beim Einstieg

Das Signal entsteht auf dem **Schlusskurs** von Bar t. Gekauft wird zum
**Eröffnungskurs** von Bar t+1.

Wer stattdessen zum Schlusskurs von Bar t kauft, kauft zu dem Kurs, der
den Anstieg gerade erzeugt hat. Das ist der häufigste Fehler in genau
dieser Strategiefamilie und macht aus jedem Ergebnis eine Fiktion.
Test: `test_kauf_erfolgt_zum_folgebar_nicht_zum_signalkurs`.

### 4.2 Stop und Ziel in derselben Bar

Berührt eine Bar den Stop **und** das Ziel, ist aus den Daten nicht zu
erkennen, was zuerst kam. **Hier gilt immer der Stop.**

Die Gegenannahme lässt jede Konfiguration mit weitem Ziel und engem Stop
künstlich gut aussehen — und das ist genau die Ecke des Parameterraums,
in die ein Sweep von selbst läuft.
Test: `test_stop_gewinnt_wenn_eine_bar_beides_beruehrt`.

### 4.3 Survivorship — hier härter als anderswo

Das Universum kennt nur **heute gelistete** Symbole. Bei einer
Ausbruch-Strategie ist das der größte Einzelvorbehalt des ganzen
Vorhabens: Der Wert, der +40 % macht und ein halbes Jahr später
verschwindet, ist gar nicht erst in den Daten. Übrig bleiben die
Ausbrüche, die *überlebt* haben.

§G11 beziffert den Schein-Vorteil auf 2–4 Prozentpunkte pro Jahr — für
dieses Segment eher darüber. **Jede Zahl aus dieser Werkstatt ist eine
Obergrenze.** Der Hinweis steht deshalb dauerhaft im Kopf der
Oberfläche, nicht hinter einem Aufklapp-Pfeil.

## 5. Der Versuchszähler — der eigentliche Zweck der Datenbank

Eine Oberfläche zum Herumprobieren **ist** eine Maschine zur Herstellung
von Scheingewinnern. Bei N Versuchen liegt das Zufallsmaximum bei
`sqrt(2 ln N)` (§B2). Das lässt sich nicht abschalten — nur zählen.

Deshalb:

* Jeder Lauf wird **vor** der Rechnung angemeldet. Ein Lauf, der erst
  nach dem Ergebnis gezählt würde, ließe sich stillschweigend verwerfen,
  wenn er nicht gefällt.
* `lauf_loeschen()` entfernt Trades und Kurve, **nicht** den
  Zählereintrag — der Lauf bleibt als `verworfen` stehen.
* Die Schwelle steht bei jedem Ergebnis neben dem t-Wert.

**Getrennt von `fleet.schwelle_sigma()`.** Der Flottenzähler zählt
angemeldete Vorwärtsbots; Historienläufe kosten dort bewusst keinen
Platz (`BETRIEBSPLAN` §4). Hier läuft ein eigener Zähler für eine eigene
Frage.

### Die Grenze des Zählers — benannt, nicht beschönigt

**Gezählt wird nur, was über die Oberfläche läuft.** `ausbruch.lauf()`
ist eine reine Funktion und kennt die Datenbank nicht; ein direkter
Aufruf aus einem Skript oder aus `python -c` erscheint nirgends im
Zähler.

Das ist bewusst so — eine Rechenfunktion, die beim Aufruf in eine
Datenbank schreibt, wäre in Tests und in jedem anderen Zusammenhang
unbrauchbar. Aber es heißt: **Der Zähler ist eine ehrliche Buchführung,
keine Schranke.** Wer an ihm vorbei rechnet, hat die Historie genauso
befragt; die Zahl in der Oberfläche ist dann zu niedrig, und die
Schwelle damit zu leicht.

Konkret betroffen: Der Belastungstest vom 11.09.2026 (598 Symbole,
5,2 Sekunden) lief als Direktaufruf und steht deshalb nicht in
`laeufe`. Wer Läufe außerhalb der Oberfläche fährt, führt sie von Hand
nach — oder ruft `ausbruch_store.neuer_lauf()` selbst auf.

## 5a. Die automatische Suche (`scripts/47_ausbruch_suche.py`)

```
python scripts/47_ausbruch_suche.py                  # Strg+C beendet
python scripts/47_ausbruch_suche.py --symbole 200    # schneller, gröber
python scripts/47_ausbruch_suche.py --score calmar
python scripts/47_ausbruch_suche.py --fest halten_bars=26
```

Probiert Kombinationen durch, merkt sich die beste und sucht von dort
weiter — **Erkundung → Bergsteigen → Neustart** im Wechsel, bis du
abbrichst. Live-Terminal mit Versuchszahl, Tempo, Phase, aktuell bester
Konfiguration und den letzten zwölf Versuchen.

Tempo gemessen: **~1 Sekunde je Versuch bei 150 Symbolen**, ~5 s bei
598. Also 700–3.600 Versuche pro Stunde.

### Die eine Sache, die diese Suche überhaupt zulässig macht

Eine Suche über 6·10¹¹ Kombinationen ist die perfekte Maschine zur
Herstellung von Scheingewinnern. Bei N Versuchen liegt das
Zufallsmaximum bei `sqrt(2 ln N)` — nach 3.000 Durchläufen bei **4,00**.
Sie *wird* eine Konfiguration mit t > 4 finden, auch auf reinem Rauschen.

Deshalb wird das Jahr geschnitten:

```
|<------- LERNFENSTER (70 %) ------->|<-- PRÜFFENSTER (30 %) -->|
   Hier wird optimiert.                 Hier wird NUR nachgesehen.
   Tausende Versuche.                   Kein Versuch wählt danach aus.
```

Findet die Suche im Lernfenster etwas Besseres, wird dieselbe
Konfiguration **einmal** im Prüffenster nachgerechnet — protokolliert,
aber **nie zur Auswahl benutzt**. Sonst wäre das Prüffenster nach dem
zweiten Treffer genauso verbraucht wie das Lernfenster.

**Die Zahl, auf die es ankommt, steht deshalb rechts, nicht links.**
Und noch aussagekräftiger ist der **Abstand** zwischen beiden: Fällt eine
Konfiguration von t=2,2 im Lernfenster auf t=−0,6 im Prüffenster, ist
sie an den Lernzeitraum angepasst und nicht gut.

> **Erster Probelauf (11.09.2026, 60 Symbole, 107 Versuche in 42
> Sekunden):** Lernfenster t = 2,17 (+2,07 %), Prüffenster t = −0,55
> (−0,88 %), **Abstand +2,72**. Genau das erwartete Bild. Die Suche
> funktioniert — und ihr erstes Ergebnis ist die Bestätigung, dass der
> Schutzmechanismus greift.

### Jeder Teilversuch hebt die Schwelle — für alle

`ausbruch_store.n_versuche()` zählt Handläufe **und** Suchversuche
zusammen. Eine Suche mit 3.000 Durchläufen hebt die Hürde auf 4,00 —
auch für spätere Handläufe in der Werkstatt. Das ist unbequem und
richtig: Die Daten sind 3.000-mal befragt worden, und keine spätere
Auswertung kann so tun, als wäre sie die erste.

### Warum kein neuronales Netz

Bei ~17 Achsen und Sekunden je Durchlauf ist örtliche Suche mit
Neustarts schneller, nachvollziehbar und hat keine eigenen
Hyperparameter, die wieder angepasst werden müssten. Ein DQN würde hier
dasselbe tun, nur langsamer und undurchsichtiger — und seine
Zwischenergebnisse wären nicht als Konfigurationszeile lesbar.

---

## 6. Das Gate — vorab festgelegt, bevor eine Zahl existiert

Die Werkstatt darf eine Idee **verwerfen**, nie abnehmen
(`BETRIEBSPLAN` §4). Der Weg nach vorn ist ein Flottenbot im
Vorwärtsschatten — und dafür muss **alles** davon zutreffen:

0. **Wenn die Konfiguration aus einer automatischen Suche stammt:
   Maßgeblich ist allein das Prüffenster.** Der beste Wert im
   Lernfenster ist bei genug Versuchen garantiert gut und zählt nicht.
1. **t über der Zufallsschwelle** von `ausbruch_store.schwelle_sigma()`,
   überlappungskorrigiert, bei mindestens **60 Handelstagen** mit Trades.
2. **Mindestens 200 Trades.** Darunter trägt die Streuungsschätzung nicht.
3. **Trägt bei 30 bps Spanne**, nicht nur bei 12,2. Wenn eine
   Konfiguration nur mit der optimistischen Kostenannahme funktioniert,
   ist sie keine Strategie, sondern eine Kostenwette.
4. **Trägt in beiden Jahreshälften.** Ein Ergebnis, das allein aus
   Januar–Juni kommt, ist ein Zeitraum, kein Effekt.
5. **Hängt nicht an fünf Symbolen.** Die Top-5 der Bestenliste dürfen
   nicht mehr als 50 % des Gesamtgewinns tragen.
6. **Der maximale Rückgang ist ausgehalten worden** — also vorab
   benannt, nicht nachträglich als „damit muss man leben" erklärt.

**Fällt eines durch, gibt es keinen Flottenplatz.** Und diese sechs
Punkte werden nicht nachträglich gelockert (§B2) — auch nicht, wenn
fünf davon erfüllt sind.

## 7. Ehrliche Vorbehalte

* **Der Nachrichtenfaktor fehlt.** Ein 20-%-Sprung hat fast immer eine
  Meldung als Ursache (Studienergebnis, Übernahme, Zahlen). Ob die
  Bewegung nachläuft, hängt an der Art der Meldung — und die kennt diese
  Rechnung nicht. `news.py` und `gdelt.py` existieren im Projekt; sie
  anzubinden wäre der nächste ehrliche Schritt, nicht ein weiterer
  Parameter.
* **Ein Jahr ist wenig.** 2025 war ein steigender Markt. Momentum
  funktioniert in steigenden Märkten fast immer und bricht in Wenden
  zusammen. Ein Ergebnis aus 2025 allein sagt wenig; 2018 und 2022
  gehören dazu.
* **Die Datenlage ist besser als die Handelbarkeit.** 15-Minuten-Bars
  sagen nichts darüber, ob zum Eröffnungskurs des Folgebars wirklich
  Stück verfügbar waren. Bei einem Wert, der gerade 20 % gesprungen ist,
  ist das keine Kleinigkeit.
* **Diese Idee ist alt und gut untersucht.** Momentum auf kurzen
  Horizonten ist eines der meistgetesteten Muster überhaupt. Dass es hier
  zu finden wäre, ist nicht ausgeschlossen — aber die Vorannahme sollte
  sein, dass die einfache Fassung nicht trägt.

## 8. Bedienung

```
python scripts/46_ausbruch.py          # Browser öffnet sich
python scripts/46_ausbruch.py --port 9000 --kein-browser
```

**Schritt 1 — Kursdaten.** Einmalig. 600 Symbole × ein Jahr
15-Minuten-Bars sind rund 4 Millionen Zeilen und etwa 20 Minuten
Ladezeit. Danach liest jeder Testlauf von der Platte und braucht
Sekunden. Der Abruf ist fortsetzbar: Ein Abbruch kostet nichts.

**Schritt 2 — Einstellen.** Alle 23 Stellschrauben, gruppiert nach
Einstieg, Filter, Position, Ausstieg, Kosten, Betrieb. Die
Kostenvorschau rechnet **vor** dem Lauf aus, wie viel Kostenlast die
gewählte Haltedauer im Jahr erzeugt.

**Schritt 3 — Laufen lassen.** Fortschrittsbalken, Live-Kontostand,
Live-Gewinn, offene Positionen und ein Protokoll, das mitläuft.
Abbrechen jederzeit möglich.

Danach: Kennzahlen mit t-Wert gegen die Zufallsschwelle, die
Bestenliste der Symbole, alle Trades und die Liste aller bisherigen
Läufe.

**Speicherorte** (nicht unter `~/Documents`, macOS-TCC):

```
~/Library/Application Support/alpaca-bot/data/intraday/15Min_2025/
~/Library/Application Support/alpaca-bot/data/ausbruch.sqlite
```
