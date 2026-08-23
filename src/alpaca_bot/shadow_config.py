"""Einstellungen eines Schattenlaufs - was gemessen wird, nicht wie.

Bewusst ein eigenes Modul und nicht Teil der Schritte: `ShadowConfig`
ist das, was der Daemon vorgibt, bevor irgendetwas laeuft. Sie kennt
weder Speicher noch Datenquelle - deshalb kann jede andere Schicht sie
importieren, ohne einen Zyklus zu erzeugen. Genau daran haengt die
Schichtung: `_universum_symbole(cfg: ShadowConfig)` in `shadow_daten`
war die einzige Stelle, an der die Datenschicht sonst auf die
Schrittschicht zeigen wuerde.

**Herkunft: Aufteilung von `shadow.py` am 23.08.2026 (BEFUNDE §G20).**
Der Schattenbetrieb lag in EINER Datei mit 2.339 Zeilen und fuenf
Verantwortungen. Der Code in diesem Modul wurde dabei **unveraendert**
verschoben - kein Ausdruck, keine Zeile Logik wurde angefasst. Nachgewiesen
ueber den Bytecode jeder Funktion, nicht behauptet (`scripts/29_umzug_pruefen.py`).
"""


from __future__ import annotations

from dataclasses import dataclass, field

from .engine import EngineConfig


# `RAW_DIR = DATA_DIR / "shadow_raw"` stand hier bis zum 23.08.2026 und
# wurde bei jedem `ShadowStore()` angelegt - aber NIE beschrieben. Seit
# dem 31.07.2026 leer, und es sah aus wie das Gegenstueck zu
# `journal_raw`. Ersetzt durch `ShadowStore.sichern()`, das eine echte,
# transaktionskonsistente Kopie ablegt (BEFUNDE §G19 Fund 7).

MARKET_SYMBOL = "SPY"

# Horizonte, auf denen jede Vorhersage nachgehalten wird. Bewusst UNABHAENGIG
# von Stop und Ziel: Sie sind die Grundlage jeder kontrafaktischen Rechnung
# (Plan §7.2) - "waere Bot A's Auswahl mit Bot B's Ausstieg besser gewesen?"
HORIZONTE = (1, 3, 5, 10, 20)

@dataclass
class ShadowConfig:
    """Einstellungen des Schattenbetriebs."""

    universe: str = "gemessen"
    max_symbols: int = 800
    """Obergrenze. Kleiner als beim Live-Bot, weil hier JEDER Kandidat
    aufgezeichnet wird und die Laufzeit linear mitwaechst."""

    years: float = 2.0
    """Historie je Lauf. 2 Jahre reichen fuer die 260-Bar-Vorlaufzeit der
    Signale und halten den Download ertraeglich."""

    spread_bps: float = 5.0
    slippage_bps: float = 3.0
    """Identisch mit SimConfig - sonst waeren Schatten und Simulation nicht
    vergleichbar. Ein Schattentrade ohne Kosten sieht systematisch besser aus
    als jeder echte, und zwar genau in die Richtung, die einem gefaellt."""

    news_max_symbole: int = 200
    """Nur die bestbewerteten Kandidaten bekommen den zusaetzlichen
    Tonalitaets-/Ereignis-Kontext (news_ton/news_ereignis, _news_kontext) -
    dieser zweite Feed-Abruf ist zu langsam fuer 800 Symbole je Lauf.

    Betrifft NICHT den eigentlichen Score-Faktor (ReversalWeights.news):
    Der laeuft seit 03.08.2026 immer, ueber das GANZE Universum, als Teil
    des normalen Starts (siehe baue_snapshot) - kein Flag, keine Grenze."""

    max_new_positions: int = 3
    """Kaeufe je Lauf im Spiegelbuch - identisch mit dem Live-Bot. Im
    Ranglisten-Buch bestimmt der Wert nur, welche Kandidaten das Kennzeichen
    `wuerde_gehandelt` bekommen; erfasst werden dort alle."""

    engine: EngineConfig = field(default_factory=EngineConfig.for_reversal)
    bot_id: str = "B00_basis"
