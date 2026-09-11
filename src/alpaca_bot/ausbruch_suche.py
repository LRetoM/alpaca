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
import json
import math
import random
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterator

import numpy as np
import pandas as pd

from . import ausbruch

__all__ = ["RAUM", "SCORES", "Versuch", "Suche", "teilen",
           "elite_lesen", "elite_schreiben", "ELITE_DATEI"]


def _elite_pfad() -> Path:
    from .config import DATA_DIR
    return DATA_DIR / "ausbruch_elite.json"


ELITE_DATEI = property(lambda self: _elite_pfad())


def elite_lesen() -> dict | None:
    """Der beste Fund ueber ALLE parallel laufenden Instanzen.

    Vier unabhaengige Suchen finden vier verschiedene Huegel - das ist
    gewollt. Aber wenn Instanz b nach zwei Stunden immer noch bei t=0,3
    herumsucht, waehrend a laengst t=3,1 gefunden hat, ist weiteres
    Herumirren verschenkte Rechenzeit.
    """
    p = _elite_pfad()
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def elite_schreiben(score: float, config: dict, instanz: str,
                    kennzahlen: dict | None = None) -> bool:
    """Traegt einen neuen gemeinsamen Bestwert ein - nur wenn er besser ist.

    Kein Dateisperren: Geschrieben wird ausschliesslich bei einem neuen
    globalen Bestwert, also wenige Dutzend Mal in 48 Stunden. Zwei
    Instanzen, die in derselben Millisekunde schreiben, sind so
    unwahrscheinlich, dass die Kosten einer Sperre (und die Gefahr, dass
    ein abgestuerzter Prozess sie haelt) groesser waeren als der Schaden.
    Schlimmstenfalls geht EIN Eintrag verloren - der naechste Bestwert
    holt ihn wieder ein.
    """
    p = _elite_pfad()
    vorhanden = elite_lesen()
    if vorhanden and float(vorhanden.get("score", float("-inf"))) >= score:
        return False
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps({
        "score": float(score), "config": config, "instanz": instanz,
        "kennzahlen": kennzahlen or {},
        "gesetzt_am": dt.datetime.now(dt.UTC).isoformat(),
    }, default=str, indent=2), encoding="utf-8")
    tmp.replace(p)
    return True


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
    pruef_bewertungen: int = 0
    """Wie oft das Prueffenster ueberhaupt gerechnet wurde."""
    elite_uebernahmen: int = 0
    """Wie oft diese Instanz bei einem Neustart den gemeinsamen
    Bestwert der anderen Instanzen uebernommen hat."""

    @property
    def schwelle(self) -> float:
        """Huerde fuer den LERNWERT - `sqrt(2 ln N)` ueber alle Versuche.

        Der Lernwert ist das Maximum aus N Versuchen und damit durch die
        Auswahl aufgeblaeht. Bei 940.000 Versuchen liegt das
        Zufallsmaximum bei 5,24 - so hoch muss ein Lernwert liegen, um
        ueberhaupt aufzufallen.
        """
        return max(2.0, math.sqrt(2.0 * math.log(max(self.versuche, 2))))

    @property
    def pruef_schwelle(self) -> float:
        """Huerde fuer den PRUEFWERT - und die ist eine andere.

        **Das ist kein Absenken der Latte, sondern die Korrektur eines
        Denkfehlers.** Die Auswahl ueber N Versuche findet
        ausschliesslich im Lernfenster statt. Das Prueffenster sieht nur
        die wenigen Konfigurationen, die dort gewonnen haben - und jede
        dieser Bewertungen ist ein sauberer, einzelner Test auf Daten,
        die an keiner Auswahl beteiligt waren.

        Die Vielfachtestung ist also auf der Lernseite bereits bezahlt.
        Maassgeblich fuer den Pruefwert ist, wie oft das Prueffenster
        **selbst** befragt wurde - typisch 30 bis 200 Mal je Lauf, also
        eine Schwelle um 2,8 bis 3,3.

        Wuerde man hier weiter die Lernschwelle ansetzen (5,24), waere
        das Verfahren per Konstruktion unfaehig, jemals etwas zu finden -
        und zwar auch dann, wenn ein echter Effekt vorhanden ist.

        **Die Bedingung, unter der das gilt:** Es darf nie auf den
        Pruefwert hin ausgewaehlt werden. `Suche.laufen()` tut das nicht
        (durch Tests abgesichert), und dieser Zaehler laeuft ueber alle
        Instanzen und Laeufe hinweg weiter - wer die Suche zehnmal
        wiederholt und sich den besten Pruefwert heraussucht, hebt damit
        seine eigene Huerde.
        """
        return max(2.0, math.sqrt(2.0 * math.log(
            max(self.pruef_bewertungen, 2))))

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
        instanz: str = "a",
        elite_anteil: float = 0.4,
        pruef_stichprobe: float = 0.01,
        protokoll=None,
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
        self.instanz = instanz
        self.elite_anteil = elite_anteil
        """Anteil der Neustarts, die beim gemeinsamen Bestwert der
        anderen Instanzen ansetzen statt an einem Zufallspunkt.

        Bewusst NICHT 1,0: Wuerden alle Instanzen immer beim selben
        Punkt ansetzen, waeren vier parallele Suchen nur noch eine -
        mit vierfachem Stromverbrauch. 0,4 haelt die Vielfalt und nutzt
        trotzdem, was die anderen schon gefunden haben."""
        self.pruef_stichprobe = pruef_stichprobe
        """Anteil der Versuche, fuer die das Prueffenster ZUSAETZLICH
        gerechnet wird, ohne dass es die Auswahl beruehrt.

        Warum das kein Widerspruch zum Prueffenster-Prinzip ist: Diese
        Werte werden nur PROTOKOLLIERT, nie verglichen und nie zur
        Auswahl benutzt. Sie liefern die unverzerrte Antwort auf die
        eigentliche Frage - wie haengen Lern- und Pruefwert ueberhaupt
        zusammen? Ohne sie kennt man diesen Zusammenhang nur fuer die
        Gewinner, also fuer eine bewusst schiefe Auswahl."""
        self.protokoll = protokoll
        self.aktuell: dict | None = None
        self.aktuell_score: float = float("-inf")
        """Der Punkt, von dem gerade geklettert wird - siehe `laufen()`.
        Als Attribut statt lokaler Variable, damit ein Checkpoint ihn
        mitnehmen kann."""

    # --- Speichern / Fortsetzen ---------------------------------------
    def zustand(self) -> dict:
        """JSON-faehiger Schnappschuss - fuer einen Dienst, der sich
        selbst neu startet, statt bei jedem Neustart bei 0 anzufangen.

        **Was NICHT gespeichert wird: `_gesehen`.** Bei 6,3*10^11
        moeglichen Kombinationen ist die Chance, nach einem Neustart
        zufaellig etwas bereits Geprueftes zu ziehen, verschwindend
        gering - ein paar verschenkte Millisekunden, kein Fehler.
        """
        s = self.stand
        return {
            "version": 1,
            "gespeichert_am": dt.datetime.now(dt.UTC).isoformat(),
            "versuche": s.versuche,
            "neustarts": s.neustarts,
            "seit_verbesserung": s.seit_verbesserung,
            "beste_score": None if s.beste_score == float("-inf") else s.beste_score,
            "beste_config": s.beste_config,
            "beste_kennzahlen": s.beste_kennzahlen,
            "pruef_kennzahlen": s.pruef_kennzahlen,
            "kumulierte_sekunden": time.time() - s.start,
            "pruef_bewertungen": s.pruef_bewertungen,
            "elite_uebernahmen": s.elite_uebernahmen,
            "aktuell": self.aktuell,
            "aktuell_score": (None if self.aktuell_score == float("-inf")
                              else self.aktuell_score),
            "score_name": self.score_name,
            "min_trades": self.min_trades,
        }

    def zustand_anwenden(self, z: dict) -> None:
        """Setzt einen gesicherten Stand wieder ein - macht aus einem
        Neustart eine Fortsetzung statt eines Nullpunkts."""
        s = self.stand
        s.versuche = int(z.get("versuche", 0))
        s.neustarts = int(z.get("neustarts", 0))
        s.seit_verbesserung = int(z.get("seit_verbesserung", 0))
        bs = z.get("beste_score")
        s.beste_score = float(bs) if bs is not None else float("-inf")
        s.beste_config = dict(z.get("beste_config") or {})
        s.beste_kennzahlen = dict(z.get("beste_kennzahlen") or {})
        s.pruef_kennzahlen = dict(z.get("pruef_kennzahlen") or {})
        # `start` rueckdatieren, statt die Laufzeit separat zu fuehren -
        # damit zeigt jede bestehende Anzeige (Minuten, Tempo) automatisch
        # die GESAMTE Laufzeit ueber alle Neustarts hinweg.
        s.start = time.time() - float(z.get("kumulierte_sekunden", 0.0))
        s.pruef_bewertungen = int(z.get("pruef_bewertungen", 0))
        s.elite_uebernahmen = int(z.get("elite_uebernahmen", 0))
        self.aktuell = z.get("aktuell")
        ak = z.get("aktuell_score")
        self.aktuell_score = float(ak) if ak is not None else float("-inf")

    def speichern(self, pfad: "str | Path") -> None:
        """Schreibt den Zustand atomar - kein halb geschriebener
        Checkpoint, wenn der Prozess mitten im Schreiben stirbt."""
        pfad = Path(pfad)
        pfad.parent.mkdir(parents=True, exist_ok=True)
        tmp = pfad.with_suffix(pfad.suffix + ".tmp")
        tmp.write_text(json.dumps(self.zustand(), default=str, indent=2),
                       encoding="utf-8")
        tmp.replace(pfad)

    @staticmethod
    def laden_zustand(pfad: "str | Path") -> dict | None:
        pfad = Path(pfad)
        if not pfad.exists():
            return None
        return json.loads(pfad.read_text(encoding="utf-8"))

    # --- Bausteine ---------------------------------------------------
    def _schluessel(self, cfg: dict) -> tuple:
        return tuple(sorted((k, str(v)) for k, v in cfg.items()))

    def _zufallspunkt(self) -> dict:
        return {k: self.zufall.choice(v) for k, v in self.raum.items()}

    def _neustartpunkt(self) -> dict:
        """Wo eine neue Kletterpartie beginnt.

        Mit Wahrscheinlichkeit `elite_anteil` in der Umgebung des
        gemeinsamen Bestwerts aller Instanzen, sonst an einem reinen
        Zufallspunkt. "In der Umgebung", nicht "genau dort": Der
        Bestwert selbst ist bereits geprueft; dort neu anzusetzen
        brauchte nur Zeit, um festzustellen, dass seine Nachbarschaft
        schon abgesucht ist. Zwei zufaellige Achsen werden deshalb
        verstellt - nah genug, um vom Fund zu profitieren, weit genug
        fuer eine andere Kletterpartie.
        """
        if self.elite_anteil <= 0 or self.zufall.random() >= self.elite_anteil:
            return self._zufallspunkt()
        e = elite_lesen()
        if not e or not e.get("config"):
            return self._zufallspunkt()
        cfg = {k: e["config"].get(k, self.zufall.choice(v))
               for k, v in self.raum.items()}
        for achse in self.zufall.sample(sorted(self.raum), min(2, len(self.raum))):
            cfg[achse] = self.zufall.choice(self.raum[achse])
        self.stand.elite_uebernahmen += 1
        return cfg

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
        # `aktuell`/`aktuell_score` liegen auf self (nicht mehr lokal),
        # damit ein Checkpoint sie mitnehmen kann - siehe `zustand()`.
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
                if self.aktuell is None:
                    # Erste Kletterpartie startet beim bisher Besten -
                    # oder, nach einem Checkpoint, genau dort weiter.
                    self.aktuell = dict(self.stand.beste_config or
                                        self._zufallspunkt())
                    self.aktuell_score = self.stand.beste_score
                nachbarn = [n for n in self._nachbarn(self.aktuell)
                            if self._schluessel(n) not in self._gesehen]
                if nachbarn:
                    warteschlange = nachbarn
                    phase, cfg = "Bergsteigen", warteschlange.pop()
                else:
                    # Umgebung abgesucht: neue Partie an neuer Stelle.
                    self.stand.neustarts += 1
                    self.aktuell = self._neustartpunkt()
                    self.aktuell_score = float("-inf")
                    phase, cfg = "Neustart", dict(self.aktuell)

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
            if score > self.aktuell_score:
                self.aktuell, self.aktuell_score = dict(cfg), score
                warteschlange = []      # Umgebung des neuen Punktes
                self.stand.seit_verbesserung = 0
            else:
                self.stand.seit_verbesserung += 1

            # --- Globaler Bester -----------------------------------
            pk: dict | None = None
            pruef_grund = ""
            if besser:
                self.stand.beste_score = score
                self.stand.beste_config = dict(cfg)
                self.stand.beste_kennzahlen = k

                # EINMAL im Prueffenster nachsehen - und NIE danach
                # auswaehlen. Sonst waere es nach dem zweiten Treffer
                # genauso verbraucht wie das Lernfenster.
                _, pk = self._bewerten(cfg, self.pruef)
                self.stand.pruef_kennzahlen = pk
                self.stand.pruef_bewertungen += 1
                v.pruef_kennzahlen = pk
                pruef_grund = "bester"

                # Den Fund den anderen Instanzen zur Verfuegung stellen.
                elite_schreiben(score, dict(cfg), self.instanz, k)

            elif (self.pruef_stichprobe > 0
                  and self.zufall.random() < self.pruef_stichprobe):
                # Unverzerrte Stichprobe: NUR protokolliert, nie
                # verglichen, nie zur Auswahl benutzt. Sie beantwortet
                # die Frage, die die Gewinner-Auswahl nicht beantworten
                # kann - wie haengen Lern- und Pruefwert im Mittel
                # zusammen, nicht nur an der Spitze?
                _, pk = self._bewerten(cfg, self.pruef)
                self.stand.pruef_bewertungen += 1
                pruef_grund = "stichprobe"

            if self.protokoll is not None:
                self.protokoll.merken(v, pk, pruef_grund)

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
                self.aktuell = self._neustartpunkt()
                self.aktuell_score = float("-inf")
                warteschlange = []

    # --- Abschluss ---------------------------------------------------
    def bericht(self) -> str:
        """Das Urteil - und es haengt am Prueffenster, nicht am besten Wert."""
        s = self.stand
        L = []
        L.append(f"{s.versuche} Versuche in "
                 f"{(time.time() - s.start) / 60:.1f} Minuten, "
                 f"{s.neustarts} Neustarts.")
        L.append(f"Lernschwelle  ({s.versuche} Versuche)        : "
                 f"t > {s.schwelle:.2f}")
        L.append(f"Pruefschwelle ({s.pruef_bewertungen} Pruefungen) : "
                 f"t > {s.pruef_schwelle:.2f}   <- massgeblich")
        if s.elite_uebernahmen:
            L.append(f"{s.elite_uebernahmen} Neustarts setzten beim "
                     f"gemeinsamen Bestwert an.")
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
        elif pt < s.pruef_schwelle:
            L.append(f"URTEIL: KEIN BEFUND. Das Prueffenster zeigt t={pt:.2f} "
                     f"gegen seine Schwelle {s.pruef_schwelle:.2f}. Der gute "
                     f"Wert im Lernfenster ist das erwartete Ergebnis von "
                     f"{s.versuche} Versuchen, kein Effekt.")
        else:
            L.append(f"URTEIL: Das Prueffenster traegt (t={pt:.2f} > "
                     f"{s.pruef_schwelle:.2f} bei {s.pruef_bewertungen} "
                     f"Pruefungen). Das ist ein Grund fuer einen Flottenbot "
                     f"im Vorwaertsschatten - NICHT fuer eine Live-Schaltung. "
                     f"Ein Historienlauf nimmt nichts ab (BETRIEBSPLAN §4).")
            L.append("Vor dem naechsten Schritt: Gate aus docs/AUSBRUCH.md §6 "
                     "durchgehen (30 bps Spanne, beide Jahreshaelften, nicht "
                     "von funf Symbolen getragen).")
        return "\n".join(L)
