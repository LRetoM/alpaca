# Projektanweisungen

## Vor jeder Änderung

**`docs/BEFUNDE.md` lesen.** Dort steht, was bereits gemessen, widerlegt
oder als Fehler behoben wurde. Mehrere Fehler in diesem Projekt sind
entstanden, weil eine bereits beantwortete Frage erneut beantwortet
wurde — oder weil ein Befund ohne Blick auf seine Stichprobengröße
übernommen wurde.

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

## Nach Codeänderungen an der Handelslogik

1. `python scripts/00_selftest.py` (47 Prüfungen)
2. `python scripts/18_health_check.py`
3. Dienste neu starten, sonst läuft weiter der alte Code:
   `launchctl kickstart -k gui/$(id -u)/de.local.alpacabot`
   `launchctl kickstart -k gui/$(id -u)/de.local.alpacaschatten`
