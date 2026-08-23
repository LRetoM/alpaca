"""Schattenbetrieb: lernen, ohne zu handeln (Phase 1 aus docs/schattenbetrieb.md).

Der Engpass des Projekts ist nicht Rechenzeit, sondern BEOBACHTUNGEN. Der
Live-Bot kauft hoechstens 3 Werte je Lauf und verwirft dabei ~200 Kandidaten,
ueber die niemand je erfaehrt, was aus ihnen geworden waere. Genau das ist
aber die wichtigste Frage: **sortiert unsere Rangliste richtig?**

Dieses Modul beantwortet sie, indem es taeglich JEDEN Kandidaten aufzeichnet
und spaeter nachhaelt, was tatsaechlich passiert ist - ohne eine einzige
Order zu senden.

**Der entscheidende Wert liegt nicht in "mehr Trades":**

    Jeder Backtest in diesem Projekt ist potenziell dadurch verdorben, dass
    die Strategie ausgewaehlt wurde, NACHDEM man diese Historie gesehen hat.
    Vorwaerts erzeugte Schattenvorhersagen sind gegen diesen Fehler immun.
    Sie sind die einzigen wirklich unbekannten Daten, die das Projekt bekommt.

**Trennung vom Handelspfad - strukturell, nicht diszipliniert:**

    journal.sqlite   Depot und Simulation   (unberuehrt von diesem Modul)
    shadow.sqlite    Schattenbetrieb        (eigene Datei)

Eine Abfrage gegen `journal.sqlite` KANN keine Schattendaten liefern. Das ist
Absicht: Bei ~1.000 Schattenvorhersagen taeglich gegen ~60 echte Entscheidungen
waere jede vergessene `WHERE script=`-Bedingung eine still falsche Kennzahl -
und genau dieser Mechanismus hat schon einmal versagt (14_journal_bereinigen.py).

Dieses Modul importiert bewusst **kein** `trading.py`. Es kann konstruktions-
bedingt keine Order senden, nicht nur "darf nicht".

**Geteilt wird dagegen `Engine.decide()`** - derselbe Grundsatz wie im ganzen
Projekt: eine Entscheidungslogik, verschiedene Datenquellen.

    simulate.py  ->  Historie, bei Tag T abgeschnitten
    live.py      ->  Alpaca-Depot
    shadow.py    ->  yfinance, virtuelles Buch          <- hier

Drei Arbeitsschritte mit unterschiedlichem Rhythmus:

    entscheiden()   nach US-Schluss: Kandidaten des Tages festhalten
    einbuchen()     naechster Handelstag: Eroeffnungskurs nachtragen
    verifizieren()  laufend: was ist tatsaechlich daraus geworden

---------------------------------------------------------------------------
Aufteilung vom 23.08.2026 - diese Datei ist die Fassade (BEFUNDE §G20)
---------------------------------------------------------------------------

Bis dahin lag alles davon in DIESER Datei: 2.339 Zeilen, fuenf
Verantwortungen. Aufgeteilt nach Schichten, mit unveraendertem Code:

    shadow_config.py     Einstellungen eines Laufs        ~70 Zeilen
    shadow_store.py      shadow.sqlite und ihr Schema    ~750 Zeilen
    shadow_daten.py      Universum, Bars, Snapshot       ~260 Zeilen
    shadow_schritte.py   die vier Schritte               ~850 Zeilen
    shadow_pruefung.py   die zehn Korrektheitspruefungen ~530 Zeilen

Die Abhaengigkeiten laufen nur in eine Richtung:

    config  <-  daten  <-  schritte
    store   <-  schritte, pruefung
    config, daten, store  <-  pruefung

**Warum ueberhaupt.** Der Auslass war `shadow_pruefung`: Der Schatten
pruefte sich aus derselben Datei heraus, die er prueft - waehrend
`audit.py` (Live-Handelsregeln) und `data_integrity.py` (Journal)
laengst eigene Module waren. Dieselbe Aufgabe, drei Ebenen, und nur bei
einer lag der Pruefer im Geprueften.

**Warum diese Fassade bleibt.** Zwoelf Stellen in Skripten und Tests
importieren aus `alpaca_bot.shadow`. Ein Umzug, der gleichzeitig alle
Aufrufer aendert, laesst sich nicht mehr als reiner Umzug nachweisen -
und genau dieser Nachweis war die Bedingung dafuer, waehrend einer
laufenden Messung ueberhaupt aufzuraeumen (CLAUDE.md). Wer neuen Code
schreibt, importiert direkt aus dem passenden Modul; wer bestehenden
liest, findet hier die Landkarte.

**Der Umzug ist geprueft, nicht behauptet.** `scripts/29_umzug_pruefen.py`
vergleicht den BYTECODE jeder verschobenen Funktion gegen den Stand vor
dem Umzug. Gleicher Bytecode heisst gleiches Verhalten - das ist der
Nachweis, den eine laufende Messung verlangt.
"""

from __future__ import annotations

# Die Fassade re-exportiert bewusst ALLES, auch die mit `_` beginnenden
# Namen: `_pruefe_handelsrhythmus`, `_pruefe_kosten`, `_pruefe_kursanpassung`,
# `_regime` und `_spiegel` werden von Tests und Skripten benutzt. Ein
# Unterstrich heisst "nicht Teil der oeffentlichen Schnittstelle", nicht
# "existiert nicht" - und ein Umzug ist der falsche Anlass, das zu klaeren.
from .shadow_config import HORIZONTE, MARKET_SYMBOL, ShadowConfig
from .shadow_daten import (
    SHADOW_CACHE,
    _news_kontext,
    _regime,
    _signalrahmen,
    _universum_symbole,
    baue_snapshot,
    lade_bars,
)
from .shadow_pruefung import (
    ANPASSUNG_GRENZE,
    ANPASSUNG_JUENGSTE_TAGE,
    LIVE_SPIEGEL_BOT,
    SLIPPAGE_GRENZE_BPS,
    Befund,
    _pruefe_buchfuehrung,
    _pruefe_gegen_depot,
    _pruefe_handelsrhythmus,
    _pruefe_kosten,
    _pruefe_kursanpassung,
    _pruefe_replay,
    pruefbericht,
    pruefungen,
)
from .shadow_schritte import (
    ShadowEngine,
    _rangliste,
    _spiegel,
    _trage_ueberschuss_nach,
    einbuchen,
    entscheiden,
    lernen,
    verifizieren,
)
from .shadow_store import SCHEMA, SHADOW_DB, ShadowStore, _json, code_version

__all__ = [
    # Einstellungen
    "ShadowConfig", "HORIZONTE", "MARKET_SYMBOL",
    # Speicher
    "ShadowStore", "SHADOW_DB", "SCHEMA", "code_version",
    # Daten
    "lade_bars", "baue_snapshot", "SHADOW_CACHE",
    # Schritte
    "entscheiden", "einbuchen", "verifizieren", "lernen", "ShadowEngine",
    # Pruefung
    "pruefungen", "pruefbericht", "Befund",
]
