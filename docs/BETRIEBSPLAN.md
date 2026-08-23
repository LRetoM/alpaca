# Betriebsplan — was läuft, was beobachtet wird, wann entschieden wird

> Stand: 15.08.2026. **Dieses Dokument beantwortet: Was passiert jetzt,
> wie lange, und woran erkennen wir, ob es funktioniert hat?**
>
> Ergänzt `docs/BEFUNDE.md` (was wir bereits wissen) um den Fahrplan
> nach vorn. Beide werden bei jeder Änderung mitgeführt.

---

## 1. Neustart des Rechners — was passiert

**Ja, beide Bots starten automatisch wieder** — mit einer Bedingung.

| Schritt | Verhalten |
|---|---|
| Mac fährt hoch | FileVault verlangt das Passwort — **noch läuft nichts** |
| Du meldest dich an | launchd lädt beide Dienste (`RunAtLoad=true`) |
| Bot startet | Liest Positionen von Alpaca + Marken aus `state.sqlite`, macht weiter |
| Prozess stirbt später | launchd startet ihn neu (`KeepAlive=true`, 60 s Sperre) |

**Wichtig:** Die Dienste sind an deinen Benutzer gebunden. Am
Anmeldebildschirm laufen sie **nicht**. Da du beim Update ohnehin
anwesend bist und dich anmeldest, ist das unkritisch — aber es ist der
Grund, warum ein unbeaufsichtigter Neustart (Stromausfall) den Bot
pausieren würde, bis sich jemand anmeldet.

**Nach dem Neustart prüfen:**
```
python scripts/18_health_check.py      # muss GRÜN zeigen
```

Ein Datenverlust ist nicht möglich: Alpaca kennt die Positionen, die
Datenbanken liegen außerhalb des Projektordners und überleben alles.

---

## 2. Was wurde geändert — Live-Bot gegen Schattenbot

Das ist die wichtigste Unterscheidung des ganzen Umbaus.

### 2.1 Am LIVE-Bot: nur Messung, keine Handelslogik

| Änderung | Wirkung auf Handelsentscheidungen |
|---|---|
| Quote-Plausibilitätsprüfung (2 %) | **keine** — betrifft nur `expected_price` im Protokoll |
| `bars_held` korrekt berechnet | **keine** — Protokollfeld |
| `after_10d` wird gefüllt | **keine** — Auswertung |
| Score-Vorzeichen im Bericht | **keine** — Berichtstext |
| Slippage-Bereinigung | **keine** — Auswertung |
| Symbolauswahl bei `evaluate_outcomes` | **keine** — Auswertung |
| `zeitausstieg_dynamisch` | **AUS** — Standard `False` |
| **Intraday-Stop** (neu 15.08.) | **JA — echte Verhaltensänderung.** Stop-Marken werden jetzt jeden Zyklus (~15 Min) gegen den aktuellen Kurs geprüft statt einmal täglich gegen den Vortagesschluss. Bringt Live mit dem Schatten in Übereinstimmung, der das schon immer so gerechnet hat. |

> **Der Live-Bot wählt Kandidaten exakt wie vor dem Urlaub.** Einzige
> Verhaltensänderung ist der Intraday-Stop (Zeile oben) — er verkauft
> früher, kauft aber nichts anderes. Verifiziert: Bei
> `zeitausstieg_dynamisch=False` wird `max_hold_days_hart` nicht einmal
> gelesen; Tag 5, 19, 20 und 25 ergeben alle unverändert `zeitausstieg`.

Das ist Absicht: Wir haben elf Tage saubere Vergleichsdaten. Änderte
sich jetzt gleichzeitig die Handelslogik, wäre nicht mehr trennbar, was
woran lag.

### 2.2 Im SCHATTEN: die neue Idee, ohne Kapitalrisiko

`B11_dyn_ausstieg_live` — die dynamische Haltedauer:

```
Position hat 5 Tage erreicht
  ├─ im Gewinn UND weniger als 1 x ATR unter ihrem Höchststand
  │    └─ weiter halten
  ├─ Score unter exit_score
  │    └─ verkaufen ("these_traegt_nicht_mehr")
  ├─ Tag 20 erreicht
  │    └─ verkaufen ("zeitausstieg_hart")
  └─ sonst
       └─ verkaufen ("zeitausstieg")
```

---

## 3. Was wir erwarten — und woran wir es messen

**Vorab festgelegt, damit später keine Erzählung entsteht.**

### 3.1 Die eine Frage, die zuerst beantwortet werden muss

> **Trägt die Strategie nach echten Kosten?**

| | Wert |
|---|---|
| Gemessener Vorsprung | +0,11 % je Trade |
| Rundlauf-Breakeven bei 5 bps Spread | 0,142 % |
| **Erforderlich** | Slippage-Median **< 8 bps** über 30+ saubere Orders |
| **Stand 23.08.2026** | **+0,0 bps Median über 131 prüfbare Orders** |

**Die Ausführungsbedingung ist damit erfüllt.** 131 prüfbare Orders
gegen die geforderten 30, Median +0,0 bps gegen die geforderten < 8.
Die Ausführung im Papierdepot kostet also praktisch nichts gegenüber dem
Referenzkurs.

> **Korrektur der Grundmenge vom 23.08.2026 (`BEFUNDE.md` §G19 Fund 3).**
> Hier stand vorher „162 prüfbare Orders". Die Bereinigung, die Zeilen
> ohne echte Marktquote entfernen sollte, filterte auf
> `referenz_quelle == 'fallback'` — einen Wert, den es in den Daten nie
> gab. Die Spalte kam erst am 04.08.2026 dazu; ältere Zeilen tragen
> `NULL`, und `NULL != 'fallback'`. So blieben 31 Orders aus
> 28.07.–04.08. in der Messung, darunter genau die Ausreißer, die §G
> bereits als Datenfehler führt (KGS −1.648, SIMO −1.584, TGTX −1.258 bps).
>
> | | n | Median | Mittel |
> |---|---:|---:|---:|
> | vorher | 162 | +0,0 bps | −71,7 bps |
> | **jetzt** | **131** | **+0,0 bps** | **−27,4 bps** |
>
> **Der Schluss oben ändert sich nicht** — der Median ist beidseitig +0,0,
> und 131 liegt weiterhin weit über den geforderten 30. Falsch war die
> Grundmenge, nicht das Urteil. Dass es folgenlos blieb, liegt allein am
> Median: §G16 Fund 9 hatte die Kostenkontrolle vom Mittelwert auf ihn
> umgestellt. Der Mittelwert war um **44,3 bps** verzerrt.

**Was das NICHT heißt.** Die Frage aus der Überschrift ist damit *nicht*
beantwortet, nur ihre eine Hälfte:

* **Slippage** (Abweichung vom Referenzkurs zum Orderzeitpunkt) ist
  gemessen und unauffällig.
* **Spread und Gebühren** fallen im Papierdepot gar nicht erst an
  (`README`: „Im Paper-Konto fällt nichts davon an — Paper-Ergebnisse
  sind deshalb systematisch zu gut"). Der Rundlauf-Breakeven von 0,142 %
  bleibt vollständig bestehen, und der gemessene Vorsprung von +0,11 %
  liegt weiterhin darunter (§A: „der zentrale Konflikt").

Der Engpass ist also nicht mehr die Ausführungsqualität, sondern
weiterhin der Vorsprung selbst.

> **Warum diese Zahl vorher falsch aussah:** Die automatische
> Kostenkontrolle (`shadow.pruefungen()` Nr. 5) rechnete bis zum
> 22.08.2026 einen **Mittelwert** statt des Medians und meldete
> −92,0 bps — getrieben von drei kaputten IEX-Quotes (KGS −1.648,
> SIMO −1.584), die §G bereits als Datenfehler führt. Behoben, siehe
> `BEFUNDE.md` §G16 Fund 9.

### 3.2 Die Flotte — Erwartung je Bot

Schwelle: **`fleet.schwelle_sigma()`** — hier steht bewusst keine Zahl.
Sie steigt mit jedem je angemeldeten Bot (die Anmeldung von B12 hob sie
von 2,83 auf 2,85). Eine abgeschriebene Zahl im Dokument wäre nach der
nächsten Anmeldung falsch und würde die Hürde nachträglich senken.
Abrufen: `python scripts/21_fleet.py` (weist sie bei jeder Auswertung aus).

**Stand 21.08.2026:** `B01`, `B02`, `B03`, `B05` **stillgelegt** — Befund
seit 15.08. unverändert (0,0 Differenz zu B00 über 13 Handelstage),
mehr Zeit ändert daran nichts. Zählen weiter im Versuchszähler.

| Bot | Erwartung | Stand |
|---|---|---|
| `B11_dyn_ausstieg_live` | **offen** — hält Gewinner länger, ohne Stagnierende zu binden | 5 Tage |
| `B04_halten_lang` | wird vermutlich **nichts** zeigen | t = 0,86, 13 Tage |
| `B07_mehr_positionen` | Verdacht auf **negativ** | t = −2,63, 12 Tage |
| `B08`/`B09` | offen | t = 0,65, 12 Tage |
| `B06_ohne_regime` | **wirkungslos im Bullenmarkt** — läuft weiter, wartet auf Regimewechsel | siehe BEFUNDE §E |
| `B01`/`B02`/`B03`/`B05` | **stillgelegt** — bestätigt wirkungslos | siehe BEFUNDE §E |

### 3.3 Was „Erfolg" für B11_dyn_ausstieg_live konkret heißt

Geprüft wird `B11_dyn_ausstieg_live` gegen **`B09_nachkauf`** — die bei
seiner Anmeldung hinterlegte Referenz. Der Vorgänger `B10_dyn_ausstieg`
ist seit 16.08. stillgelegt (er hat **null** Ausstiege produziert) und
zählt nur noch im Versuchszähler mit.

> **Korrektur vom 23.08.2026 (`BEFUNDE.md` §G19 Fund 1).** Hier stand bis
> dahin `B00_basis`. Das war ein Übersehen beim Nachziehen von §G6: Jener
> Befund hat `B00_basis` am 16.08.2026 als Live-Referenz **widerlegt**
> (der Live-Bot läuft seit dem 30.07. mit `deploy_to_target=True` und
> `allow_topup=True`, `B00_basis` steht auf `False`/`False`) und
> `B11_dyn_ausstieg_live` eigens gegen `B09_nachkauf` angemeldet — daher
> sein Namenszusatz „gegen echte Live-Basis". Dieses Dokument wurde nicht
> nachgezogen, und `21_fleet.py --basis` trug `B00_basis` als
> hartkodierten Standard.
>
> **Es war keine Formalie:** t = 0,99 gegen `B00_basis`, t = 1,24 gegen
> `B09_nachkauf` (gemessen 23.08.2026). Beide Zahlen heißen „Kriterium 1".
>
> Das ist **keine nachträgliche Anpassung des Vertrags** im Sinne der
> Warnung unten. Der Vertrag wird auf die Referenz zurückgesetzt, die bei
> der Anmeldung am 16.08.2026 festgelegt wurde — die Kriterien selbst
> bleiben Wort für Wort unverändert. Maßgeblich ist ab jetzt die
> **Registrierung**, nicht dieser Absatz: `shadow_eval.referenz_bot()`
> liest sie, und `--basis` ohne Angabe folgt ihr.
>
> **Einordnung:** Der Vergleich bleibt so oder so **intern gültig** —
> beide Seiten teilen denselben Rhythmus, die getestete Achse
> (`zeitausstieg_dynamisch`) ist sauber isoliert. Was `B09_nachkauf`
> **nicht** ist: ein Spiegel des echten Live-Bots (§G16 Fund 1,
> `shadow.pruefungen()` Nr. 10 weist die Abweichung bei jedem Aufruf aus).
> Ein bestandenes B11 heißt also „besser als B09 unter Spiegelbedingungen",
> nicht „besser als der Live-Bot".

**Diese vier Kriterien sind der Entscheidungsvertrag.** Sie stehen vorab
fest und werden nicht nachträglich angepasst — weder nach oben noch nach
unten. Ein Kommando prüft alle vier:

```
python scripts/21_fleet.py --kriterien B11_dyn_ausstieg_live
```

B11 gilt als **bestanden**, wenn *alle vier* zutreffen:

1. `vergleich_gepaart("B11_dyn_ausstieg_live", "B09_nachkauf")` liefert einen
   t-Wert über **`fleet.schwelle_sigma()`** (keine feste Zahl, siehe §3.2).
   Den Bot-Namen hier gar nicht erst abschreiben: `--kriterien` nimmt ohne
   `--basis` die registrierte Referenz und weist sie im Kopf mit aus.
2. über mindestens **20 auswertbare Handelstage** — das sind Tage *nach*
   Abzug der Sperrzone (`SPERRZONE_ANTEIL = 0,20`). 20 auswertbare Tage
   entsprechen **25 rohen** Handelstagen.
3. Anteil verlängerter Positionen liegt zwischen **10 % und 60 %**
   (darunter: Regel greift praktisch nie; darüber: sie ist keine
   Ausnahme mehr, sondern hebelt den Zeitausstieg aus).
   Nenner sind **nur die Ausstiege, die die Frist erreicht haben**
   (`bars_held >= max_hold_days`) — eine nach zwei Tagen ausgestoppte
   Position hatte nie die Gelegenheit, verlängert zu werden.
4. Die verlängerten Trades sind **nicht** allein durch wenige Ausreißer
   getragen — Median ebenfalls positiv

> **Festlegung vom 23.08.2026: Die Sperrzone gilt für Kriterium 1, nicht
> für 3 und 4.** Beim Durchrechnen der Kriterien fiel auf, dass der
> Vertrag dazu schwieg und die Umsetzung asymmetrisch ist:
> `vergleich_gepaart` (Kriterium 1) verwirft die jüngsten 20 % der
> Handelstage, die Kriterien 3 und 4 rechnen über **alle** Ausstiege.
>
> Das wird **nicht angeglichen**, aber es steht jetzt hier — und zwar
> *bevor* Daten dazu existieren, denn genau darum geht es:
>
> * **Kriterium 3 (Verlängerungsquote) misst einen Mechanismus,** nicht
>   ein Ergebnis: „greift die Regel überhaupt". Dafür ist mehr Datenbasis
>   besser, und eine Quote lässt sich nicht zugunsten eines Ergebnisses
>   erzählen.
> * **Kriterium 4 (Median positiv) ist ein Ergebniswert** und damit
>   grundsätzlich das, wogegen die Sperrzone schützt. Es bleibt trotzdem
>   ungefiltert, weil es kein Schwellenwert-Kriterium ist, sondern eine
>   Vorzeichenprüfung gegen die Ausreißer-Falle („trägt der Median oder
>   nur ein Glückstreffer"). Bei einer reinen Vorzeichenfrage kostet die
>   Sperrzone 20 % der ohnehin knappen Fälle, ohne die Erzählgefahr
>   nennenswert zu senken.
>
> **Der Punkt ist nicht, welche Antwort richtig ist, sondern wann sie
> fällt.** Am 10.10. wäre dieselbe Frage mit Kenntnis des Ergebnisses zu
> beantworten — genau der Fehler, gegen den §G10 den Vertrag überhaupt
> erst geschrieben hat. Deshalb steht sie hier, sechs Wochen vorher.

> **Vorab festgehaltene Erwartung vom 23.08.2026 — was der 10.10.
> beantworten kann und was nicht (`BEFUNDE.md` §G22).**
>
> Vor dem Termin gemessen, wie groß ein Unterschied sein müsste, damit
> Kriterium 1 ihn überhaupt findet. Bei 31 auswertbaren Tagen und der
> gemessenen Streuung der Tagesdifferenz:
>
> | Streuungsschätzung | nachweisbar ab | kumuliert über 31 Tage |
> |---|---:|---:|
> | B11 gegen B09 (eigene, n=5) | 0,34 %/Tag | **10,5 %** |
> | B04 gegen B00 (belastbarer, n=18) | 0,18 %/Tag | **5,4 %** |
>
> Zum Vergleich: Der **gesamte** gemessene Vorsprung der Strategie
> beträgt +0,11 % **je Trade** (§A), auf das Depot gerechnet grob
> 0,02–0,03 %/Tag.
>
> **B11 müsste also mehrfach so viel beitragen, wie die Strategie
> insgesamt verdient, um am 10.10. bestehen zu können.** Der
> wahrscheinlichste Ausgang ist deshalb: Kriterium 1 fällt durch, es
> bleibt beim Zeitausstieg.
>
> **Das ist kein Grund, den Vertrag zu ändern** — die konservative
> Vorgabe „im Zweifel keine Änderung" ist genau richtig. Es ist ein
> Grund, das Ergebnis richtig zu lesen: „durchgefallen" heißt hier
> **nicht nachweisbar**, nicht **widerlegt**. Die Auswertung weist die
> Trennschärfe seit dem 23.08.2026 bei jedem Aufruf mit aus, damit diese
> Verwechslung nicht passiert.
>
> **Warum das hier steht und nicht am 10.10.:** Nach dem Termin wäre
> dieselbe Rechnung eine nachträgliche Erklärung für ein unerwünschtes
> Ergebnis. Vorher ist sie eine Vorhersage.
>
> **Die Ursache ist bekannt und benannt.** `shadow_eval.vergleich_gepaart`
> versprach „Streuung 3–5× kleiner, entscheidbar nach 6–10 Wochen".
> Nachgemessen gilt das für Bots, die sich nur im Kapitaleinsatz
> unterscheiden (B08: 3,6×) — nicht für B11 gegen B09 (**1,1×**), die
> andere Positionen unterschiedlich lange halten. Der Docstring ist
> korrigiert.

**Fällt einer der vier durch, bleibt es beim Zeitausstieg nach 5 Tagen.**

**Drei Zustände, nicht zwei.** Jedes Kriterium kann *erfüllt*,
*durchgefallen* oder **offen** sein. `offen` heißt „noch keine
Datengrundlage" und ist **kein** Bestehen. Zwei erfüllte und zwei offene
Kriterien sind kein 2:0.

---

## 4. Zeitplan — wie lange laufen lassen

B11 ist seit **18.08.2026** angemeldet. Alle Tagesangaben zählen ab dort.

| Zeitraum | Was passiert | Was NICHT passiert |
|---|---|---|
| **jetzt – ca. 12.09.** (≈19 roh / **15 auswertbar**) | B11 und B00 laufen unverändert und sammeln Daten. | Keine Parameteränderung, keine neue Hypothese, **keine neue Bot-Anmeldung** |
| **ca. 12.09.** | Erste Zwischenauswertung — **reine Zwischenschau**. Kriterium 2 ist an diesem Tag noch nicht erfüllbar (15 < 20 auswertbare Tage). | **Keine Entscheidung.** Auch kein Abbruch, wenn es schlecht aussieht. |
| **ca. 10.10.** (≈39 roh / **31 auswertbar**) | Entscheidung über `B11_dyn_ausstieg_live` nach §3.3 | — |

### Rohe gegen auswertbare Handelstage

Das sind zwei verschiedene Zahlen und sie werden leicht verwechselt.
`vergleich_gepaart` verwirft die **jüngsten 20 %** der Handelstage
(`SPERRZONE_ANTEIL = 0,20`), damit ein Ergebnis nicht nachträglich auf
die letzten Tage hin erzählt werden kann. Gezählt wird danach.

| roh | auswertbar |
|---|---|
| 25 | 20 ← Kriterium 2 aus §3.3 |
| 39 (Stand 10.10.) | 31 |
| 75 | 60 ← `shadow_eval.MIN_TAGE` |

### `MIN_TAGE` ist ein Hinweis, kein Veto — Festlegung vom 21.08.2026

`shadow_eval.MIN_TAGE` steht auf **60** und steuert die
`belastbar`-Flagge in `vergleich_gepaart`. Dieses Dokument behauptete
bis zum 21.08.2026 an dieser Stelle, die Konstante sei 20. **Das war
falsch** — sie stand seit dem ersten Schatten-Commit auf 60 (Beleg:
`docs/BEFUNDE.md` §G10).

Die Folge wäre gewesen: 60 auswertbare Tage erreicht B11 erst am
**~30.11.2026**. Am 10.10. wäre `belastbar` zwingend `False` gewesen,
**egal wie gut der t-Wert ist** — der vorab festgelegte Termin hätte
kein Ergebnis liefern können.

**Festlegung:** Maßgeblich für die Abnahme sind die vier Kriterien aus
**§3.3**. `MIN_TAGE` bleibt als strengere Hausmarke von
`vergleich_gepaart` bestehen und wird ausgewiesen, hat aber **kein
Vetorecht**. Das deckt sich mit dem eigenen Anspruch des Moduls
(`shadow_eval.py`: „A schlägt B ist nach 6–10 Wochen entscheidbar") —
60 auswertbare Tage sind 15 Wochen.

Der Grund für ein Tage-Minimum überhaupt steht in §B1 von
`docs/BEFUNDE.md`: Maßgeblich ist die Zahl der **Handelstage**, nicht
der Trades. Elf Tage Betrieb haben nur 8 auswertbare Tage ergeben — zu
wenig für jede Aussage.

### Die Schwelle steigt vor dem 10.10. — bewusst und vorab festgelegt

**Ergänzung vom 22.08.2026.** Der Musterspeicher legt ab dem 20.
Schattenhandelstag automatisch Regimeschnitte als Kandidaten an, und
seit `BEFUNDE.md` §G16 zählt jeder davon korrekt im Versuchszähler.
Bei vier bis sechs Schnitten hebt das `fleet.schwelle_sigma()` von
**2,85 auf etwa 2,93** — für alle laufenden Messungen, auch für B11.

Das ist eine bewusste Entscheidung und steht deshalb *vor* dem Termin
hier. Sie ist **kein Grund**, den Entscheidungsvertrag aus §3.3
anzupassen. Maßgeblich bleibt der bei der Auswertung abgerufene Wert
(`python scripts/21_fleet.py`), nie eine abgeschriebene Zahl.

### Vor dem 10.10. keine neuen Bots anmelden

Jede Anmeldung hebt `fleet.schwelle_sigma()` für **alle** Bots, auch
rückwirkend für die laufende Messung (B12 hob sie von 2,83 auf 2,85).
Ein während der Messung angemeldeter Bot erschwert B11 also die eigene
Prüfung, ohne selbst etwas beizutragen. Neue Ideen werden bis zum
10.10. in §7 gesammelt, nicht angemeldet.

### Ideen trotzdem prüfen — der Historienfilter

„Nicht anmelden" heißt nicht „nicht prüfen". Seit 21.08.2026 fährt
`scripts/10_simulate.py` dieselbe Konfiguration wie der Live-Bot
(`for_reversal()`, Marktfilter an, 1.200 Symbole — vorher war es eine
andere Strategie, siehe `docs/BEFUNDE.md` §G11). Damit lässt sich eine
Idee an Altdaten in Minuten durchspielen, statt Wochen auf eine
Vorwärtsmessung zu warten:

```
python scripts/10_simulate.py --min-score 0.45     # eine Achse ändern
```

**Was das entscheidet — und was nicht.** Der Lauf darf eine Idee
**verwerfen**. Er darf sie **nicht** abnehmen. Zwei Gründe:

* **Survivorship:** Alpaca kennt nur heute gelistete Symbole. Der
  Schein-Vorteil liegt bei 2–4 Prozentpunkten pro Jahr — mehr, als die
  Strategie je verdienen wird. Jedes Ergebnis ist eine **Obergrenze**.
* **Rückwärts ist kein Vorwärtstest.** Wer die Historie oft genug
  befragt, findet dort alles.

Reihenfolge also: erst Historienfilter (billig, verwirft viel), was das
überlebt, kommt nach dem 10.10. als Flottenbot in den Schatten, und erst
§3.3 nimmt ab. Ein Flottenplatz ist teuer — er hebt `schwelle_sigma` für
alle. Der Filter sorgt dafür, dass dieser Platz nicht an eine Idee geht,
die schon an der Vergangenheit scheitert.

**Erste Anwendung (21.08.2026): „einfach länger halten" ist erledigt.**
Über alle 2.149 Zeitausstiege des Historienlaufs gemessen, was der Kurs
danach tat — marktbereinigt gegen SPY, gruppiert nach Ausstiegstag:
nach 1/2/3/5/10 Tagen jeweils −0,09 / −0,16 / −0,13 / −0,09 / −0,05 %,
kein Horizont über der Schwelle, jeder Punktschätzer negativ
(`docs/BEFUNDE.md` §G11). Roh sieht es umgekehrt aus (+0,43 % nach 10
Tagen) — das ist der Markt, nicht die Strategie.

Für die Auswertung am **10.10.** heißt das: eine Verlängerung der
Haltedauer als solche braucht keinen Flottenplatz mehr.
`B11_dyn_ausstieg_live` prüft die schärfere Fassung — *signalgesteuert*
aussteigen statt nach fester Frist — und wird davon **nicht**
vorentschieden. Die vier Kriterien aus §3.3 bleiben unverändert
maßgeblich; diese Messung ist Kontext, kein Kriterium.

---

## 5. Was du beobachten solltest — und was nicht

### 5.1 Wöchentlich (2 Minuten)

```
python scripts/18_health_check.py
```
**Grün** = nichts zu tun. **Gelb/Rot** = melden. Zeigt jetzt auch den
Drawdown und warnt bereits, wenn er 75 % der Sperrgrenze erreicht (15 %) —
also **bevor** gesperrt wird.

Bei aktiver Sperre:
```
python scripts/20_risiko.py               # Grund und Kennzahlen ansehen
python scripts/20_risiko.py --entsperren  # erst NACH Ursachenklärung
```

### 5.2 Alle 1–2 Wochen (10 Minuten)

```
python scripts/13_tagesbericht.py --tage 14
```
Interessant sind dort:
- Abschnitt **[3] Ausführung**: Slippage-Median — die Kernfrage aus §3.1
- Abschnitt **[6] Nachbetrachtung**: Zeitausstieg und Wiedereinstiege
- **Regelabgleich** am Ende: muss „Keine Abweichungen" zeigen

### 5.3 Was du bewusst NICHT tun solltest

- **Nicht auf die Depotrendite schauen und daraus schließen.** +8,36 % in
  elf Tagen ist überwiegend Marktbewegung (SPY +5,07 %) und eine
  Stichprobe von 36 Trades. Eine gute Woche ist kein Befund, eine
  schlechte auch nicht.
- **Nicht bei einem Verlusttag eingreifen.** Der Bot hat Stop-Marken; ein
  Eingriff von Hand macht die Messung wertlos.
- **Keine Parameter „mal eben" ändern.** Jede Änderung setzt die
  Vergleichsbasis zurück und hebt die Signifikanzschwelle.

---

## 6. Ist das Projekt sinnvoll aufgebaut? — ehrliche Einschätzung

### Was gut ist

| Punkt | Warum es zählt |
|---|---|
| **Ein Entscheidungspfad** | `Engine.decide()` läuft in Backtest, Schatten und Live. Abweichungen können nur aus Ausführung stammen. |
| **Strukturelle Lookahead-Sperre** | `MarketSnapshot.validate()` — die Engine *kann* nicht in die Zukunft sehen. |
| **Schatten handelt nicht** | Kein Schattenmodul importiert `trading.py`. Seit 23.08.2026 **geprüft** (`selfcheck`-Regel 9, §G19) statt behauptet. Geltungsbereich ist der Quelltext — zur Laufzeit lädt das Paket-`__init__.py` `trading` mit, dort tragen `dry_run=True` und `_check_risk()`. |
| **Voranmeldung + Versuchszähler** | Schutz gegen nachträgliche Erzählungen. |
| **Automatische Integritätsprüfung** | Findet Protokollfehler, bevor sie Entscheidungen verfälschen. |
| **Betrieb bewährt** | 11 Tage ununterbrochen, 1 abgefangener Fehler. |

### Was seit 15.08.2026 gebaut ist — Live-Tauglichkeit

| Baustein | Was er verhindert | Datei |
|---|---|---|
| **Drawdown-Sperre** (20 %) | Dass ein Bot mit kaputter Logik das Konto leerhandelt | `risiko.py` |
| **Tagesverlustgrenze** (5 %) | Weiterkaufen in einen laufenden Absturz | `risiko.py` |
| **Exposure-Grenze** (100 %) | Ungewollten Hebel (Alpaca erlaubt bis 4×) | `risiko.py` |
| **Cash-Reserve** (2 %) | Zwangsverkäufe bei Kurslücken | `risiko.py` |
| **Klumpenkontrolle** (40 %/Sektor) | Dass 15 Positionen in Wahrheit *eine* Wette sind | `risiko.py` + `universe.sektoren` |
| **Positionsobergrenze** (30) | Konfigurationsfehler bei `max_positions` | `risiko.py` |
| **Kapitalflüsse** | Dass Einzahlungen als Gewinn gelesen werden | `kapital.py` |
| **Zeitgewichtete Rendite** | Unvergleichbare Kennzahlen nach Einzahlung | `kapital.py` |
| **Equity je Zyklus** | Dass ein Drawdown-Beginn nicht rekonstruierbar ist | `state.kapital_verlauf` |

**Wichtige Eigenschaften, bewusst so gebaut:**

- **Die Sperre ist persistent und löst sich nie selbst.** Eine Sperre, die
  sich nach einer Stunde aufhebt, kauft genau in den Crash zurück, wegen
  dem sie ausgelöst hat. Lösen nur über `scripts/20_risiko.py --entsperren`
  mit wörtlicher Bestätigung.
- **Verkaufen ist immer erlaubt.** Eine Sperre darf nie verhindern, aus
  einer Position herauszukommen.
- **Fällt die Risikoprüfung selbst aus, wird nicht gehandelt.** Ein
  Risiko-Dach, das im Zweifel durchlässt, ist keines.
- **Auch Nachkäufe werden geprüft.** Sonst ließen sich die Grenzen über
  wiederholtes Aufstocken umgehen (gemessen: bis zu 9 Nachkäufe je Symbol).

### Was weiterhin fehlt

| Lücke | Folge | Priorität |
|---|---|---|
| **Regime nicht protokolliert** | „In welcher Marktlage funktioniert es?" ist am Depot nicht beantwortbar. | mittel |
| **Laptop statt Server** | Deckel zu = alles aus. Kein Auto-Login wegen FileVault. | mittel |
| **Slippage noch nicht belastbar** | Die Kernfrage (§3.1) braucht 30+ saubere Orders | läuft |

**Einschätzung:** Der Mess- und Lernapparat ist für ein Privatprojekt
ungewöhnlich sauber. Die Lücken liegen fast alle im **Risikoschutz** —
also genau dort, wo es teuer wird, sobald echtes Geld im Spiel ist. Für
den Papierbetrieb ist das vertretbar; **vor dem Wechsel auf echtes Geld
ist das Risiko-Dach Pflicht.**

---

## 7. Reihenfolge der nächsten Schritte

| # | Schritt | Wann | Bedingung |
|---|---|---|---|
| 1 | Bots laufen lassen, nichts ändern | jetzt – ~12.09. | — |
| 2 | ~~Risiko-Dach bauen~~ | **erledigt 15.08.** | — |
| 3 | ~~Kapitalflüsse erfassen~~ | **erledigt 15.08.** | — |
| 4 | Zwischenauswertung (**keine** Entscheidung) | ~12.09. | — |
| 5 | Entscheidung über `B11_dyn_ausstieg_live` | ~10.10. | alle 4 Kriterien aus §3.3, geprüft mit `--kriterien` |
| 6 | Echtgeld erwägen | frühestens danach | Slippage-Median < 8 bps **und** Risiko-Dach steht |

**Schritte 2 und 3 sind die einzigen, die jetzt sinnvoll parallel laufen
können** — sie ändern nichts an den Handelsentscheidungen und stören die
laufende Messung deshalb nicht.

---

## 8. Abbruchkriterien

| Ereignis | Konsequenz |
|---|---|
| Health-Check zweimal in Folge ROT | Handel aus, Ursache klären |
| Regelabgleich meldet Abweichung | Sofort aus — ein Regelbruch ist ein Logikfehler, kein Pech |
| Slippage-Median > 15 bps über 30 Trades | Alle Backtest- und Schattenergebnisse neu bewerten |
| Konto-Drawdown > 20 % | **automatische Vollsperre** durch `risiko.py`, Lösen nur von Hand |
| `B11_dyn_ausstieg_live` verlängert > 60 % der Positionen | Regel greift zu oft, Schwelle war falsch kalibriert (= §3.3 Kriterium 3) |
