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

**Die ZWEITE Ueberlappung - gefunden am 22.08.2026 (`docs/BEFUNDE.md`
§G12).** Das Mitteln je Handelstag beseitigt die Ueberlappung INNERHALB
eines Tages. Es beseitigt nicht die zwischen den Tagen:

    Tag 1 sagt die Rendite der Tage 1-5 voraus
    Tag 2 sagt die Rendite der Tage 2-6 voraus   <- 4 von 5 Tagen geteilt

Bei einem Horizont von 5 Tagen teilen sich zwei benachbarte Tagesmittel
vier Fuenftel ihres Renditefensters. Sie sind damit ebenso wenig
unabhaengig wie zwei Vorhersagen desselben Tages - nur eine Ebene hoeher.

Gemessen ueber 1.182 Symbole und 7 Jahre mit dem projekteigenen
Faktor-Scan: der t-Wert faellt im Mittel um den Faktor **1,62** zu hoch
aus. Von 30 Faktoren ueberschritten naiv 10 die Zufallsschwelle, nach
Korrektur nur noch 4.

**Die Aufblaehung ist nicht fuer alle Faktoren gleich.** Sie ist das
Produkt aus zwei Dingen: der Ueberlappung der Renditefenster UND der
Traegheit des Faktors selbst. Ein Faktor, der sich taeglich vollstaendig
erneuert (`reversal_1d`: 0,96x), erzeugt trotz ueberlappender Fenster
kaum Autokorrelation. Ein traeger Faktor (`amihud`: 1,82x,
`mom_252_21`: 1,74x) dagegen sehr wohl. Deshalb laesst sich die
Korrektur nicht durch eine pauschale Faustzahl ersetzen - sie muss aus
den Daten kommen.

Behandelt wird sie ueber `horizont=` in `gruppierter_test` (Newey-West
mit Bartlett-Kern ueber die Reihe der Tagesmittel).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


def newey_west_t(reihe: np.ndarray | pd.Series, lag: int) -> tuple[float, float]:
    """t-Wert einer Zeitreihe, korrigiert um ihre eigene Autokorrelation.

    Der gewoehnliche t-Test unterstellt, dass aufeinanderfolgende Werte
    unabhaengig sind. Bei ueberlappenden Renditefenstern sind sie das
    nicht (siehe Modul-Docstring). Newey-West schaetzt die Streuung
    stattdessen aus der Reihe selbst, indem es die Autokovarianzen bis
    `lag` mitzaehlt - gewichtet mit dem Bartlett-Kern, der linear auf
    null auslaeuft.

    Args:
        reihe: die Beobachtungen in ZEITLICHER Reihenfolge. Eine
            umsortierte Reihe ergibt eine andere Antwort - die
            Autokorrelation ist die Information, um die es hier geht.
        lag: wie viele Nachbarn mitzaehlen. Bei einem Renditefenster von
            `h` Tagen ist `h - 1` richtig: so viele Nachbarn teilen sich
            mit einer Beobachtung mindestens einen Tag.

    Returns:
        (t_korrigiert, aufblaehung). `aufblaehung` ist das Verhaeltnis
        der korrigierten zur naiven Standardabweichung: 1,0 heisst keine
        Autokorrelation, 1,6 heisst, der naive t-Wert war 1,6-mal zu
        hoch. Der Wert kann UNTER 1 liegen (negative Autokorrelation);
        dann war der naive t-Wert zu niedrig.

    Bei negativer Autokorrelation kann die geschaetzte Varianz rechnerisch
    <= 0 werden. Das ist kein Ergebnis, sondern eine Grenze des
    Schaetzers; in dem Fall faellt die Funktion auf die naive Varianz
    zurueck (Aufblaehung 1,0) statt eine Wurzel aus einer negativen Zahl
    zu ziehen.
    """
    x = np.asarray(reihe, dtype=float)
    x = x[np.isfinite(x)]
    n = len(x)
    if n < 3:
        return float("nan"), float("nan")

    e = x - x.mean()
    g0 = float(e @ e) / n
    if g0 <= 0:
        return float("nan"), float("nan")

    s = g0
    for k in range(1, min(lag, n - 1) + 1):
        gk = float(e[k:] @ e[:-k]) / n
        s += 2.0 * (1.0 - k / (lag + 1.0)) * gk

    if s <= 0:
        return float(x.mean() / np.sqrt(g0 / n)), 1.0
    return float(x.mean() / np.sqrt(s / n)), float(np.sqrt(s / g0))


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
    hundert.

    Massgeblich ist `t_ueberlappung`, nicht `t` - sonst wuerde die
    Ueberlappung zwischen den Tagen (§G12) wieder durchrutschen."""
    horizont: int = 1
    """Laenge des Renditefensters in Handelstagen. 1 = keine Ueberlappung
    zwischen den Tagen, dann ist `t_ueberlappung == t`."""
    t_ueberlappung: float = float("nan")
    """t-Wert, zusaetzlich um die Ueberlappung ZWISCHEN den Tagen
    korrigiert (Newey-West). DAS ist der Wert, gegen den eine Schwelle
    geprueft wird."""
    aufblaehung: float = float("nan")
    """Um welchen Faktor `t` zu hoch war. 1,0 = keine Autokorrelation."""

    def __str__(self) -> str:
        urteil = "BELASTBAR" if self.belastbar else "nicht belastbar"
        zeilen = [
            f"  Beobachtungen : {self.n_beobachtungen:>8,}",
            f"  Gruppen (Tage): {self.n_gruppen:>8}   <- massgeblich",
            f"  Mittelwert    : {self.mittel:>+8.4%}",
        ]
        # Bei Horizont 1 waeren "t" und "t (Ueberlappung)" dieselbe Zahl.
        # Zwei identische Zeilen laden dazu ein, die falsche zu zitieren.
        if self.horizont > 1:
            zeilen += [
                f"  t (Ueberlapp.): {self.t_ueberlappung:>8.2f}   "
                f"[{urteil}]  <- massgeblich",
                f"  t (nur Tage)  : {self.t:>8.2f}   <- ueberschaetzt "
                f"({self.aufblaehung:.2f}x, Horizont {self.horizont} T)",
            ]
        else:
            zeilen.append(f"  t (gruppiert) : {self.t:>8.2f}   [{urteil}]")
        zeilen += [
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
    horizont: int = 1,
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
        horizont: Laenge des Renditefensters in Handelstagen. Das
            Mitteln je Gruppe beseitigt nur die Ueberlappung INNERHALB
            eines Tages; bei `horizont > 1` ueberlappen sich zusaetzlich
            die Fenster BENACHBARTER Tage (§G12). Dann wird der t-Wert
            zusaetzlich nach Newey-West korrigiert.

            Der Vorgabewert 1 ist bewusst der unkorrigierte Fall: Wer
            einen Horizont hat, muss ihn nennen. Eine geratene Vorgabe
            waere fuer manche Aufrufer zu streng und fuer andere zu
            lasch, und beides faellt nicht auf.

    Das Verfahren ist bewusst das einfachste, das korrekt ist: je Gruppe
    mitteln, dann ein t-Test ueber die Gruppenmittel. Auf die Gruppenmittel
    wird bei `horizont > 1` Newey-West angewandt.

    **Warum Newey-West hier doch, entgegen der frueheren Notiz an dieser
    Stelle.** Bis zum 22.08.2026 stand hier, eine aufwendigere
    Fehlerrechnung liefere "keine ehrlichere Antwort, nur eine praezisere
    Verpackung derselben Unsicherheit". Fuer die Ueberlappung INNERHALB
    eines Tages stimmt das - Mitteln erledigt sie vollstaendig. Fuer die
    zwischen den Tagen stimmt es nicht: dort erledigt das Mitteln gar
    nichts, und gemessen wurde ein Faktor 1,62 (§G12). Das ist kein
    Verpackungsunterschied, das ist der Unterschied zwischen Befund und
    kein Befund - bei 6 von 10 gepruefen Faktoren.
    """
    df = pd.DataFrame({"wert": werte, "gruppe": gruppen}).dropna()
    if df.empty:
        return Testergebnis(0, 0, np.nan, np.nan, np.nan, np.nan, False)

    roh = df["wert"]
    n_roh = len(roh)
    t_naiv = (roh.mean() / (roh.std(ddof=1) / np.sqrt(n_roh))
              if n_roh > 2 and roh.std(ddof=1) > 0 else np.nan)

    # `sort=False`: die chronologische Ordnung wird bewusst EINMAL
    # hergestellt, unten ueber `sort_index()`. Lieferte `groupby` sie
    # zusaetzlich, waere jene Zeile ein wirkungsloses Duplikat - und die
    # Zusicherung damit an keiner Stelle pruefbar (Mutationstest
    # 22.08.2026: die Mutation blieb ungefangen).
    je_gruppe = df.groupby("gruppe", sort=False)["wert"].agg(["size", "mean"])
    je_gruppe = je_gruppe[je_gruppe["size"] >= min_je_gruppe]
    m = je_gruppe["mean"]

    if len(m) < 2 or m.std(ddof=1) == 0:
        return Testergebnis(n_roh, len(m), float(m.mean()) if len(m) else np.nan,
                            np.nan, float(t_naiv), np.nan, False,
                            horizont=horizont)

    t = float(m.mean() / (m.std(ddof=1) / np.sqrt(len(m))))

    # Newey-West liest die Autokorrelation aus der REIHENFOLGE. Diese
    # Zeile ist die einzige Stelle, die sie herstellt (siehe `sort=False`
    # oben). Bei Datumsangaben (`date`, `Timestamp`, ISO-Zeichenketten)
    # ist aufsteigend gleich chronologisch. Bei einem Schluessel, der
    # anders sortiert (etwa "1.8.", "10.8.", "2.8."), waere das Ergebnis
    # nicht bloss ungenau, sondern Unsinn - solche Schluessel gehoeren
    # hier nicht hinein.
    m = m.sort_index()

    if horizont > 1:
        t_ueber, aufbl = newey_west_t(m.to_numpy(), lag=horizont - 1)
    else:
        t_ueber, aufbl = t, 1.0

    massgeblich = t_ueber if np.isfinite(t_ueber) else t
    return Testergebnis(
        n_beobachtungen=n_roh,
        n_gruppen=len(m),
        mittel=float(m.mean()),
        t=t,
        t_naiv=float(t_naiv),
        anteil_positive_gruppen=float((m > 0).mean()),
        belastbar=bool(abs(massgeblich) > 2 and len(m) >= min_gruppen),
        horizont=horizont,
        t_ueberlappung=float(t_ueber),
        aufblaehung=float(aufbl),
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
