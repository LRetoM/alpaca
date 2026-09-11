"""Automatische Suche nach guten Ausbruch-Konfigurationen.

**Was das ist.** Ein Suchverfahren, das die Strategie aus `ausbruch.py`
immer wieder mit anderen Einstellungen durchrechnet, sich das Beste
merkt und von dort weitersucht - bis es abgebrochen wird.

**Was das zuallererst ist: die gefaehrlichste Maschine im ganzen
Projekt.** §B2 in einem Satz: Bei N Versuchen liegt das erwartete
Maximum allein durch Zufall bei `sqrt(2 ln N)`. Eine Suche mit 5.000
Durchlaeufen findet **garantiert** eine Konfiguration mit t ueber 4 -
auch auf reinem Rauschen. Wer sie ohne Gegenmittel laufen laesst,
erzeugt keinen Befund, sondern eine Illusion mit Nachkommastellen.

---

## Das Gegenmittel: ein Fenster, das die Suche nie sieht

Das Jahr wird in zwei Teile geschnitten:

```
|<------- LERNFENSTER (70 %) ------->|<-- PRUEFFENSTER (30 %) -->|
   Hier wird optimiert.                 Hier wird NUR nachgesehen.
   Tausende Versuche.                   Kein Versuch waehlt danach aus.
```

Die Suche optimiert **ausschliesslich** auf dem Lernfenster. Findet sie
dort etwas Besseres, wird dieselbe Konfiguration **einmal** auf dem
Prueffenster nachgerechnet - und das Ergebnis wird protokolliert, aber
**nie zur Auswahl benutzt**. Sonst waere das Prueffenster nach dem
zweiten Versuch genauso verbraucht wie das Lernfenster.

**Die Zahl, auf die es ankommt, ist deshalb nicht der beste Wert im
Lernfenster - sondern der Abstand zwischen beiden.** Faellt eine
Konfiguration von t=4,2 im Lernfenster auf t=0,1 im Prueffenster, ist
sie angepasst und nicht gut. Das ist der eigentliche Ertrag dieser
Suche: nicht "welche Einstellung gewinnt", sondern "traegt ueberhaupt
irgendetwas ueber die Grenze".

## Warum jeder Versuch mitzaehlt

`ausbruch_store.n_versuche()` zaehlt Handlaeufe UND Suchversuche
zusammen. Eine Suche mit 3.000 Durchlaeufen hebt die Schwelle fuer
alle spaeteren Auswertungen auf `sqrt(2 ln 3000)` = **4,00**. Das ist
unbequem und richtig: Die Daten sind 3.000-mal befragt worden, und
keine spaetere Auswertung kann so tun, als waere sie die erste.

## Wie gesucht wird

Drei Phasen im Wechsel, wie bei jeder vernuenftigen Suche mit
oertlichen Maxima:

| Phase | Was passiert |
|---|---|
| **Erkundung** | Zufaellige Punkte im ganzen Raum. Kartiert grob, wo ueberhaupt etwas ist. |
| **Bergsteigen** | Vom besten Punkt aus EINE Achse variieren, Verbesserung behalten. Findet das oertliche Maximum. |
| **Neustart** | Steckt das Bergsteigen fest, springt die Suche an einen neuen Zufallspunkt. Der globale Beste bleibt erhalten. |

Das ist bewusst kein neuronales Netz: Bei ~30 Achsen und Sekunden je
Durchlauf ist ortliche Suche mit Neustarts schneller, nachvollziehbar
und hat keine eigenen Hyperparameter, die wieder angepasst werden
muessten.
"""

from __future__ import annotations

import datetime as dt
import itertools
import math
import random
import time
from dataclasses import dataclass, field
from typing import Callable, Iterator

import numpy as np
import pandas as pd

from . import ausbruch

__all__ = ["RAUM", "SCORES", "Versuch", "Suche", "teilen"]


# ---------------------------------------------------------------------
#  Der Suchraum
# ---------------------------------------------------------------------
RAUM: dict[str, list] = {
    # Einstieg
    "anstieg_pct":            [3, 5, 7, 10, 15, 20, 30],
    "fenster_bars":           [2, 4, 8, 16, 26, 52, 78],
    "einstieg_verzoegerung_bars": [0, 1, 2, 4, 8],
    # Filter
    "min_rel_volumen":        [0, 1.5, 2, 3, 5, 10],
    "min_dollar_volumen":     [0, 5e5, 2e6, 1e7, 5e7],
    "min_preis":              [1, 3, 5, 10, 20],
    "tageszeit_von_bar":      [0, 2, 4, 8],
    "tageszeit_bis_bar":      [10, 16, 22, 26],
    # Position
    "positions_pct":          [5, 10, 15, 20, 33],
    "max_positionen":         [3, 5, 6, 10, 15],
    "max_neue_je_bar":        [1, 2, 3, 5],
    # Ausstieg
    "halten_bars":            [2, 4, 8, 13, 26, 52, 78, 130],
    "gewinn_pct":             [0, 3, 5, 8, 10, 15, 25],
    "verlust_pct":            [0, 2, 3, 5, 8, 12],
    "trailing_pct":           [0, 3, 5, 10],
    "zeitausstieg_nur_bei_verlust": [False, True],
    # Betrieb
    "sperrfrist_bars":        [0, 4, 26, 78],
}
"""Diskretes Raster statt stufenloser Bereiche.

Drei Gruende: Der Raum bleibt endlich und abzaehlbar (hier rund
10^13 Kombinationen - gross genug, dass Absuchen ausscheidet, klein
genug fuer definierte Nachbarschaften). Bergsteigen braucht den Begriff
"Nachbar", den nur ein Raster liefert. Und stufenlose Werte verfuehren
zu Scheinpraezision: `anstieg_pct = 11,37` ist keine Erkenntnis."""


def _score_t(k: dict) -> float:
    """Gruppierter t-Wert - beruecksichtigt die Stichprobengroesse selbst.

    Die Vorgabe, weil eine Konfiguration mit 8 glaenzenden Trades sonst
    jede mit 300 soliden schlaegt."""
    t = k.get("t_wert")
    return float(t) if t is not None and t == t else float("-inf")


def _score_rendite(k: dict) -> float:
    return float(k.get("rendite_pct", float("-inf")))


def _score_calmar(k: dict) -> float:
    """Rendite je Einheit Rueckgang. Bestraft, was nur durch Glueck lief."""
    dd = abs(k.get("max_drawdown_pct", 0.0))
    return float(k.get("rendite_pct", 0.0)) / dd if dd > 0.5 else float("-inf")


def _score_profit(k: dict) -> float:
    p = k.get("profit_faktor")
    if p is None or p != p or p == float("inf"):
        return float("-inf")
    return float(p)


SCORES: dict[str, Callable[[dict], float]] = {
    "t": _score_t,
    "rendite": _score_rendite,
    "calmar": _score_calmar,
    "profit_faktor": _score_profit,
}


def teilen(bars, anteil: float = 0.7):
    """Schneidet den Datensatz nach ZEIT in Lern- und Prueffenster.

    Nach Zeit, nicht nach Symbolen: Ein Schnitt nach Symbolen liesse die
    Suche denselben Zeitraum sehen und waere kein Test auf Uebertragung.

    Der Schnitt ist fuer alle Symbole derselbe Zeitpunkt - sonst haetten
    verschiedene Symbole verschiedene Marktphasen im Prueffenster.

    Nimmt ein `ausbruch.Kursdaten` (dann Sichten statt Kopien) oder ein
    dict von DataFrames (fuer Tests).
    """
    from .ausbruch import Kursdaten
    if isinstance(bars, Kursdaten):
        lern, pruef = bars.teilen(anteil)
        return lern, pruef, pruef.achse[0]
    alle = sorted(set().union(*(d.index for d in bars.values())))
    if len(alle) < 100:
        raise ValueError("Zu wenige Bars zum Teilen.")
    grenze = alle[int(len(alle) * anteil)]
    lern = {s: d[d.index < grenze] for s, d in bars.items()}
    pruef = {s: d[d.index >= grenze] for s, d in bars.items()}
    lern = {s: d for s, d in lern.items() if len(d) > 100}
    pruef = {s: d for s, d in pruef.items() if len(d) > 100}
    return lern, pruef, grenze


@dataclass
class Versuch:
    nr: int
    phase: str
    config: dict
    score: float
    kennzahlen: dict
    besser: bool = False
    dauer_s: float = 0.0
    pruef_kennzahlen: dict | None = None
    """Nur gefuellt, wenn dieser Versuch ein neuer Bester war."""


@dataclass
class Stand:
    """Was die Oberflaeche anzeigt."""
    versuche: int = 0
    beste_score: float = float("-inf")
    beste_config: dict = field(default_factory=dict)
    beste_kennzahlen: dict = field(default_factory=dict)
    pruef_kennzahlen: dict = field(default_factory=dict)
    phase: str = "Erkundung"
    seit_verbesserung: int = 0
    neustarts: int = 0
    verlauf: list = field(default_factory=list)
    start: float = field(default_factory=time.time)

    @property
    def schwelle(self) -> float:
        """`sqrt(2 ln N)` - die Huerde, die mit jedem Versuch steigt."""
        return max(2.0, math.sqrt(2.0 * math.log(max(self.versuche, 2))))

    @property
    def abstand(self) -> float | None:
        """Lernfenster minus Prueffenster - das Mass fuer Anpassung.

        Ein grosser Abstand heisst: Die Konfiguration beschreibt den
        Lernzeitraum, nicht den Markt.
        """
        a = self.beste_kennzahlen.get("t_wert")
        b = self.pruef_kennzahlen.get("t_wert")
        if a is None or b is None or a != a or b != b:
            return None
        return float(a) - float(b)


class Suche:
    """Die Suche selbst. Laeuft, bis `stoppen()` True liefert."""

    def __init__(
        self,
        lern: dict[str, pd.DataFrame],
        pruef: dict[str, pd.DataFrame],
        *,
        score: str = "t",
        min_trades: int = 40,
        raum: dict[str, list] | None = None,
        fest: dict | None = None,
        erkundung_n: int = 25,
        geduld: int = 2,
        saat: int | None = None,
        grenze: pd.Timestamp | None = None,
    ) -> None:
        self.lern, self.pruef = lern, pruef
        self.grenze = grenze
        """Wo der Schnitt liegt - nur fuer Anzeige und Bericht."""
        self.score_name = score
        self.score = SCORES[score]
        self.min_trades = min_trades
        self.raum = {k: v for k, v in (raum or RAUM).items()
                     if k not in (fest or {})}
        self.fest = dict(fest or {})
        self.erkundung_n = erkundung_n
        self.geduld = geduld
        self.zufall = random.Random(saat)
        self.stand = Stand()
        self._gesehen: set[tuple] = set()

    # --- Bausteine ---------------------------------------------------
    def _schluessel(self, cfg: dict) -> tuple:
        return tuple(sorted((k, str(v)) for k, v in cfg.items()))

    def _zufallspunkt(self) -> dict:
        return {k: self.zufall.choice(v) for k, v in self.raum.items()}

    def _nachbarn(self, cfg: dict) -> list[dict]:
        """Alle Punkte, die sich in GENAU EINER Achse unterscheiden.

        Eine Achse je Schritt - dieselbe Regel wie fuer Flottenbots
        (`CLAUDE.md`). Zwei gleichzeitig geaenderte Achsen machen die
        Verbesserung nicht zuordenbar.
        """
        aus = []
        for achse, werte in self.raum.items():
            for w in werte:
                if w == cfg.get(achse):
                    continue
                neu = dict(cfg)
                neu[achse] = w
                aus.append(neu)
        self.zufall.shuffle(aus)
        return aus

    def _bewerten(self, cfg: dict, bars: dict) -> tuple[float, dict]:
        voll = {**cfg, **self.fest}
        # Ableitungen, die sonst unsinnige Kombinationen erzeugen.
        if voll.get("tageszeit_bis_bar", 26) < voll.get("tageszeit_von_bar", 0):
            voll["tageszeit_bis_bar"] = voll["tageszeit_von_bar"]
        try:
            erg = ausbruch.lauf(bars, ausbruch.AusbruchConfig(**voll))
        except Exception:  # noqa: BLE001 - eine unsinnige Kombination ist kein Absturz
            return float("-inf"), {}
        k = erg.kennzahlen
        if k.get("n_trades", 0) < self.min_trades:
            # Zu wenige Trades: kein Ergebnis, kein Score. Sonst gewinnt
            # die Konfiguration, die zweimal zufaellig richtig lag.
            return float("-inf"), k
        return self.score(k), k

    # --- Hauptschleife -----------------------------------------------
    def laufen(self, stoppen: Callable[[], bool]) -> Iterator[Versuch]:
        """Liefert jeden Versuch, sobald er fertig ist.

        Als Generator, damit die Oberflaeche live mitlesen kann, ohne
        dass die Suche etwas ueber sie wissen muss.

        **Zwei Punkte, nicht einer (korrigiert 11.09.2026).** Die erste
        Fassung kletterte immer nur von der GLOBAL besten Konfiguration
        aus. War deren Nachbarschaft abgesucht, fiel die Suche fuer
        immer auf reines Wuerfeln zurueck - gemessen 1.198 "Neustarts"
        bei 1.448 Versuchen, also praktisch kein Bergsteigen mehr.

        Richtig ist die uebliche Trennung:

        * `aktuell` - der Punkt, von dem gerade geklettert wird. Ein
          Nachbar uebernimmt, sobald er **ihn** schlaegt, auch wenn er
          unter dem globalen Besten liegt.
        * `stand.beste_*` - der globale Beste. Wird nur festgehalten,
          nie zum Klettern benutzt.

        Ist die Umgebung von `aktuell` erschoepft, beginnt an einem
        neuen Zufallspunkt eine neue Kletterpartie. Der globale Beste
        bleibt davon unberuehrt.
        """
        aktuell: dict | None = None
        aktuell_score = float("-inf")
        warteschlange: list[dict] = []
        leerlauf = 0
        # Wie oft hintereinander nur schon Gesehenes gezogen werden darf,
        # bevor der Raum als abgesucht gilt. Grosszuegig, damit ein
        # kurzer Pechstraehne-Zufall nicht schon als Ende zaehlt - aber
        # endlich, denn ohne diese Grenze dreht die Schleife ewig, sobald
        # alle Kombinationen durch sind (passiert bei kleinem Raum oder
        # vielen `--fest`-Achsen).
        leerlauf_grenze = max(500, 20 * len(self.raum))

        while not stoppen():
            # --- Punkt waehlen -------------------------------------
            if self.stand.versuche < self.erkundung_n:
                phase, cfg = "Erkundung", self._zufallspunkt()
            elif warteschlange:
                phase, cfg = "Bergsteigen", warteschlange.pop()
            else:
                if aktuell is None:
                    # Erste Kletterpartie startet beim bisher Besten.
                    aktuell = dict(self.stand.beste_config or
                                   self._zufallspunkt())
                    aktuell_score = self.stand.beste_score
                nachbarn = [n for n in self._nachbarn(aktuell)
                            if self._schluessel(n) not in self._gesehen]
                if nachbarn:
                    warteschlange = nachbarn
                    phase, cfg = "Bergsteigen", warteschlange.pop()
                else:
                    # Umgebung abgesucht: neue Partie an neuer Stelle.
                    self.stand.neustarts += 1
                    aktuell, aktuell_score = self._zufallspunkt(), float("-inf")
                    phase, cfg = "Neustart", dict(aktuell)

            schl = self._schluessel(cfg)
            if schl in self._gesehen:
                leerlauf += 1
                if leerlauf > leerlauf_grenze:
                    self.stand.phase = "abgesucht"
                    return          # Der Raum ist vollstaendig durch.
                continue
            leerlauf = 0
            self._gesehen.add(schl)

            # --- Rechnen -------------------------------------------
            t0 = time.time()
            score, k = self._bewerten(cfg, self.lern)
            dauer = time.time() - t0

            self.stand.versuche += 1
            self.stand.phase = phase
            besser = score > self.stand.beste_score

            v = Versuch(nr=self.stand.versuche, phase=phase, config=dict(cfg),
                        score=score, kennzahlen=k, besser=besser,
                        dauer_s=dauer)

            # --- Oertlicher Fortschritt ----------------------------
            if score > aktuell_score:
                aktuell, aktuell_score = dict(cfg), score
                warteschlange = []      # Umgebung des neuen Punktes
                self.stand.seit_verbesserung = 0
            else:
                self.stand.seit_verbesserung += 1

            # --- Globaler Bester -----------------------------------
            if besser:
                self.stand.beste_score = score
                self.stand.beste_config = dict(cfg)
                self.stand.beste_kennzahlen = k

                # EINMAL im Prueffenster nachsehen - und NIE danach
                # auswaehlen. Sonst waere es nach dem zweiten Treffer
                # genauso verbraucht wie das Lernfenster.
                _, pk = self._bewerten(cfg, self.pruef)
                self.stand.pruef_kennzahlen = pk
                v.pruef_kennzahlen = pk

            self.stand.verlauf.append(
                (self.stand.versuche, score, self.stand.beste_score))
            yield v

            # Lange ohne oertlichen Fortschritt: Partie abbrechen, auch
            # wenn die Warteschlange noch Nachbarn haette. Sonst
            # arbeitet die Suche 70 aussichtslose Nachbarn ab, bevor
            # sie weiterzieht.
            if self.stand.seit_verbesserung > self.geduld * len(self.raum):
                self.stand.neustarts += 1
                self.stand.seit_verbesserung = 0
                aktuell, aktuell_score = self._zufallspunkt(), float("-inf")
                warteschlange = []

    # --- Abschluss ---------------------------------------------------
    def bericht(self) -> str:
        """Das Urteil - und es haengt am Prueffenster, nicht am besten Wert."""
        s = self.stand
        L = []
        L.append(f"{s.versuche} Versuche in "
                 f"{(time.time() - s.start) / 60:.1f} Minuten, "
                 f"{s.neustarts} Neustarts.")
        L.append(f"Zufallsschwelle bei {s.versuche} Versuchen: "
                 f"t > {s.schwelle:.2f}")
        if not s.beste_config:
            L.append("Keine Konfiguration erreichte die Mindestzahl Trades.")
            return "\n".join(L)

        lt = s.beste_kennzahlen.get("t_wert")
        pt = s.pruef_kennzahlen.get("t_wert")
        L.append(f"Bester Wert im Lernfenster : {s.beste_score:.3f} "
                 f"({self.score_name})")
        L.append(f"  Lernfenster  t={lt if lt is None else round(lt, 2)}  "
                 f"Rendite {s.beste_kennzahlen.get('rendite_pct', 0):+.2f} %  "
                 f"Trades {s.beste_kennzahlen.get('n_trades', 0)}")
        L.append(f"  Prueffenster t={pt if pt is None else round(pt, 2)}  "
                 f"Rendite {s.pruef_kennzahlen.get('rendite_pct', 0):+.2f} %  "
                 f"Trades {s.pruef_kennzahlen.get('n_trades', 0)}")

        ab = s.abstand
        if ab is not None:
            L.append(f"  Abstand Lern minus Pruef: {ab:+.2f}")
        if pt is None or pt != pt:
            L.append("URTEIL: Im Prueffenster nicht auswertbar - kein Befund.")
        elif abs(pt) < s.schwelle:
            L.append(f"URTEIL: KEIN BEFUND. Das Prueffenster zeigt t={pt:.2f} "
                     f"gegen die Schwelle {s.schwelle:.2f}. Der gute Wert im "
                     f"Lernfenster ist das erwartete Ergebnis von "
                     f"{s.versuche} Versuchen, kein Effekt.")
        else:
            L.append(f"URTEIL: Das Prueffenster traegt (t={pt:.2f} > "
                     f"{s.schwelle:.2f}). Das ist ein Grund fuer einen "
                     f"Flottenbot im Vorwaertsschatten - NICHT fuer eine "
                     f"Live-Schaltung. Ein Historienlauf nimmt nichts ab "
                     f"(BETRIEBSPLAN §4).")
        return "\n".join(L)
