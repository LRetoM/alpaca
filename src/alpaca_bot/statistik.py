"""Statistische Tests, die der Ueberlappung standhalten.

**Der Fehler, gegen den dieses Modul gebaut ist**, ist am 15.08.2026 bei
der Auswertung der ersten elf Betriebstage passiert - und zwar mir selbst
beim ersten Anlauf:

    Naiv  (926 Vorhersagen als 926 Beobachtungen):  +0.744 %   t = 2.63
    Ehrlich (je Tag mitteln, dann ueber 8 Tage):    +0.464 %   t = 1.45

Dieselben Daten. Die erste Zahl sieht nach einem belastbaren Befund aus,
die zweite nach Rauschen. Richtig ist die zweite.

**Warum:** Alle Kandidaten eines Handelstages sehen denselben Markt.
Steigt der Markt, steigen sie gemeinsam - ihre Ergebnisse sind keine
unabhaengigen Ziehungen. 926 Vorhersagen an 8 Tagen tragen ungefaehr so
viel Information wie 8 Beobachtungen, nicht 926.

Dieselbe Falle steckt in Trade-Auswertungen: Am 04.08.2026 wurden zehn
Positionen am selben Tag durch den Zeitausstieg geschlossen. Ihre
Nachlauf-Fenster ueberlappen sich fast vollstaendig - "10 von 13 Faellen"
sind in Wahrheit ungefaehr drei.

**Der naive t-Wert ist nicht einfach "zu hoch", sondern bedeutungslos.**
Meist faellt er zu optimistisch aus (Schattendaten: 2.63 statt 1.45),
weil er Unabhaengigkeit unterstellt, die es nicht gibt. Er kann aber auch
zu niedrig liegen - bei den Zeitausstiegen ergab er 0.28 gegen 1.64
gruppiert, weil einzelne Ausreisser innerhalb eines Tages die Streuung
aufblaehen, die beim Mitteln je Tag verschwindet. Entscheidend ist
deshalb nicht die Richtung der Abweichung, sondern die Bezugsgroesse:
Massgeblich ist die Zahl der GRUPPEN, nie die Zahl der Einzelwerte.

Deshalb gibt dieses Modul den naiven Wert bewusst MIT aus: Nur wenn beide
nebeneinander stehen, sieht man den Unterschied - und merkt, wenn eine
Aussage nur durch die falsche Zaehlweise zustande kommt.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class Testergebnis:
    """Ergebnis eines gruppierten Mittelwerttests."""

    n_beobachtungen: int
    """Rohzahl der Einzelwerte - NICHT die Grundlage des t-Werts."""
    n_gruppen: int
    """Anzahl unabhaengiger Gruppen (meist Handelstage). DAS ist die
    Stichprobengroesse, die zaehlt."""
    mittel: float
    """Mittelwert der Gruppenmittelwerte."""
    t: float
    """t-Wert auf Basis der GRUPPEN."""
    t_naiv: float
    """t-Wert, wenn man faelschlich jede Einzelbeobachtung zaehlt -
    nur zum Vergleich, nie als Befund verwenden."""
    anteil_positive_gruppen: float
    belastbar: bool
    """|t| > 2 UND mindestens 20 Gruppen. Beides noetig: Ein hoher t-Wert
    aus fuenf Gruppen ist genauso wenig belastbar wie ein niedriger aus
    hundert."""

    def __str__(self) -> str:
        urteil = "BELASTBAR" if self.belastbar else "nicht belastbar"
        zeilen = [
            f"  Beobachtungen : {self.n_beobachtungen:>8,}",
            f"  Gruppen (Tage): {self.n_gruppen:>8}   <- massgeblich",
            f"  Mittelwert    : {self.mittel:>+8.4%}",
            f"  t (gruppiert) : {self.t:>8.2f}   [{urteil}]",
            f"  t (naiv)      : {self.t_naiv:>8.2f}   <- ueberschaetzt, nur Vergleich",
            f"  positive Tage : {self.anteil_positive_gruppen:>8.1%}",
        ]
        if not self.belastbar:
            if self.n_gruppen < 20:
                zeilen.append(f"  -> Nur {self.n_gruppen} Gruppen. Unter 20 ist kein "
                              "Befund moeglich, egal wie gut der t-Wert aussieht.")
            else:
                zeilen.append("  -> |t| <= 2: nicht von Zufall zu unterscheiden.")
        return "\n".join(zeilen)


def gruppierter_test(
    werte: pd.Series,
    gruppen: pd.Series,
    *,
    min_gruppen: int = 20,
    min_je_gruppe: int = 1,
) -> Testergebnis:
    """Mittelwerttest, der Ueberlappung innerhalb einer Gruppe verkraftet.

    Args:
        werte: die Einzelwerte (z. B. Ueberschussrenditen).
        gruppen: gleich lang, die Gruppenzugehoerigkeit (meist der
            Handelstag). Werte derselben Gruppe gelten als NICHT
            unabhaengig voneinander.
        min_gruppen: ab wie vielen Gruppen ein Befund ueberhaupt moeglich
            ist. 20 ist bewusst hoch - bei weniger ist die Schaetzung der
            Streuung selbst zu unsicher, um einen t-Wert zu tragen.

    Das Verfahren ist bewusst das einfachste, das korrekt ist: je Gruppe
    mitteln, dann ein gewoehnlicher t-Test ueber die Gruppenmittel. Eine
    aufwendigere Fehlerrechnung (Clustered Standard Errors, Newey-West)
    wuerde bei zweistelligen Gruppenzahlen keine ehrlichere Antwort
    liefern, nur eine praezisere Verpackung derselben Unsicherheit.
    """
    df = pd.DataFrame({"wert": werte, "gruppe": gruppen}).dropna()
    if df.empty:
        return Testergebnis(0, 0, np.nan, np.nan, np.nan, np.nan, False)

    roh = df["wert"]
    n_roh = len(roh)
    t_naiv = (roh.mean() / (roh.std(ddof=1) / np.sqrt(n_roh))
              if n_roh > 2 and roh.std(ddof=1) > 0 else np.nan)

    je_gruppe = df.groupby("gruppe")["wert"].agg(["size", "mean"])
    je_gruppe = je_gruppe[je_gruppe["size"] >= min_je_gruppe]
    m = je_gruppe["mean"]

    if len(m) < 2 or m.std(ddof=1) == 0:
        return Testergebnis(n_roh, len(m), float(m.mean()) if len(m) else np.nan,
                            np.nan, float(t_naiv), np.nan, False)

    t = m.mean() / (m.std(ddof=1) / np.sqrt(len(m)))
    return Testergebnis(
        n_beobachtungen=n_roh,
        n_gruppen=len(m),
        mittel=float(m.mean()),
        t=float(t),
        t_naiv=float(t_naiv),
        anteil_positive_gruppen=float((m > 0).mean()),
        belastbar=bool(abs(t) > 2 and len(m) >= min_gruppen),
    )


def noetige_gruppen(effekt: float, streuung: float, t_ziel: float = 2.0) -> int:
    """Wie viele Handelstage braucht es, um `effekt` nachzuweisen?

    Beantwortet die Frage, die vor jeder Messung stehen sollte: Ist der
    geplante Zeitraum ueberhaupt lang genug? Wer das erst hinterher
    fragt, hat die Wahl zwischen "kein Befund" und Selbstbetrug.

        n = (t_ziel * streuung / effekt) ** 2
    """
    if effekt == 0 or not np.isfinite(effekt):
        return 10**9
    return int(np.ceil((t_ziel * streuung / abs(effekt)) ** 2))
