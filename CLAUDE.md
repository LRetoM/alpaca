# Projektanweisungen

## Vor jeder Änderung

**Zwei Dokumente lesen:**

- **`docs/BEFUNDE.md`** — was bereits gemessen, widerlegt oder als Fehler
  behoben wurde. Mehrere Fehler in diesem Projekt sind entstanden, weil
  eine bereits beantwortete Frage erneut beantwortet wurde — oder weil
  ein Befund ohne Blick auf seine Stichprobengröße übernommen wurde.
- **`docs/BETRIEBSPLAN.md`** — was gerade läuft, wie lange, und welche
  Kriterien vorab festgelegt wurden. **Eine laufende Messung darf nicht
  durch eine Änderung an der Handelslogik unterbrochen werden**, sonst
  ist die Vergleichsbasis zerstört.

Nach einer Messung oder einem behobenen Fehler: **Eintrag in
`docs/BEFUNDE.md` ergänzen.** Mit Zahl, Datum und Quelle.

## Sprache

Antworten auf Deutsch. Code-Kommentare und Docstrings auf Deutsch, in
Quelltextdateien ohne Umlaute (`ae`, `oe`, `ue`, `ss`) — Markdown-Dateien
dagegen mit korrekten Umlauten.

## Statistik — die wichtigste Regel

Vorhersagen und Trades desselben Handelstages sind **nicht unabhängig**.
Immer `statistik.gruppierter_test` verwenden; maßgeblich ist die Zahl der
**Handelstage**, nie die Zahl der Einzelwerte. Der naive t-Wert ist
bedeutungslos, nicht bloß ungenau.

**Zwei Ebenen, nicht eine.** Mitteln je Handelstag löst nur die
Überlappung *innerhalb* eines Tages. Reicht das Renditefenster über
mehrere Tage, überlappen auch die *benachbarten* Tage — dagegen hilft
Mitteln nicht. Deshalb bei jedem Mehrtages-Horizont `horizont=` mit
übergeben:

```python
statistik.gruppierter_test(werte, tage, horizont=5)   # 5-Tage-Fenster
```

Ohne dieses Argument liegt die Fehlalarmquote nicht bei 5 %, sondern bei
**39,5 %** (gemessen, `docs/BEFUNDE.md` §G12). Maßgeblich ist dann
`t_ueberlappung`, nicht `t`.

Aktuelle Signifikanzschwelle: `fleet.schwelle_sigma()` (steigt mit jedem
weiteren Versuch). Ein t-Wert darunter ist der Normalfall, kein Befund.

## Was NICHT ohne Messung geändert wird

- Parameter der Handelslogik (`EngineConfig`) — erst im Schatten messen
- `max_hold_days`, `stop_atr`, `target_atr`, `min_score`
- Die Sperrfrist nach einem Verkauf (`reenter_cooldown_days`)

Neue Ideen laufen als eigener Bot in der Flotte (`fleet.anmelden`) mit
**genau einer** geänderten Achse, nicht direkt live.

## Sicherheitsgrundsätze

- `dry_run=True` ist der Standard; echtes Senden muss explizit sein.
- Der Schattenbetrieb importiert `trading.py` bewusst **nicht** — er
  *kann* keine Order senden, nicht nur „darf nicht".
- Datenbanken und Logs gehören **nicht** unter `~/Documents` (macOS-TCC
  blockiert Hintergrunddienste dort).
- Jede neue externe API zuerst in `ratelimit.QUOTAS` eintragen.

## Tests — nicht verhandelbar

**Nach JEDER Codeänderung, vor jedem Neustart:**

```
python scripts/22_tests.py        # beide Schichten
python scripts/18_health_check.py
```

Schlägt etwas fehl: **nicht neu starten**, erst beheben.

**Jeder gefundene Fehler bekommt einen Regressionstest** in `tests/`,
benannt nach dem konkreten Vorfall. Ein Fehler, der einmal auftrat, darf
nie unbemerkt zurückkommen. Details: `docs/TESTPLAN.md`.

Warum das streng ist: Bis zum 16.08.2026 prüfte nur
`scripts/00_selftest.py` — und der deckt die **Forschungsschicht** ab
(Indikatoren, Backtest, ML). Handelslogik, Risiko-Dach, Protokollierung
und Live/Schatten-Konsistenz waren ungetestet. Genau dort lagen dann auch
alle gefundenen Fehler: `bars_held` immer 0, `after_10d` nie gefüllt,
`code_version` zwei Monate kaputt, Flotten-Referenz zwei Wochen falsch.

## Nach Codeänderungen an der Handelslogik

1. `python scripts/22_tests.py` (Tests, beide Schichten)
2. `python scripts/18_health_check.py`
3. Dienste **vollständig** neu starten, sonst läuft weiter der alte Code:
   ```
   launchctl bootout gui/$(id -u)/de.local.alpacabot
   launchctl bootout gui/$(id -u)/de.local.alpacaschatten
   # auf Prozessende warten, dann:
   launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/de.local.alpacabot.plist
   launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/de.local.alpacaschatten.plist
   ```
