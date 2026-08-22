"""Fokus: woran zu arbeiten sich als naechstes lohnt - gerechnet, nicht gefuehlt.

**Die Frage, die dieses Modul beantwortet.** Das Projekt hat jederzeit ein
Dutzend offener Fragen: Traegt der dynamische Ausstieg? Schlaegt das
Modell den Score? Hilft mehr Breite? Jede davon braucht eine bestimmte
Zahl unabhaengiger Handelstage, bis sie entscheidbar ist - und diese Zahl
ist **vorab ausrechenbar**, aus dem bisher gemessenen Effekt und seiner
Streuung:

    n = (schwelle * streuung / effekt) ** 2        (statistik.noetige_gruppen)

Damit laesst sich jede offene Frage nach demselben Massstab sortieren:
**Wie viele Handelstage fehlen noch bis zur Antwort?** Das ist die
Fokus-Rangliste. Sie ersetzt das Gefuehl, woran man arbeiten sollte,
durch eine Zahl.

**Der unangenehmste Teil ist der nuetzlichste.** Bei einem gemessenen
Effekt nahe null wird `n` astronomisch. Das ist kein Rechenfehler,
sondern die Antwort: Diese Frage wird **nie** entscheidbar, egal wie
lange man wartet. Genau das ist am 21.08.2026 mit B01/B02/B03/B05
passiert - vier Bots mit exakt 0,0 Differenz zu B00, stillgelegt, weil
mehr Kalenderzeit daran strukturell nichts aendert (BEFUNDE §E). Dieses
Modul haette das drei Wochen frueher gesagt.

**Die zwei Hebel, die es ausweist**, stehen in `docs/LERNTEMPO.md` und
sind beide gemessen:

  * **Der Versuchszaehler.** `fleet.schwelle_sigma()` waechst mit jeder
    je angemeldeten Hypothese - dauerhaft und fuer alle. Weil `n`
    quadratisch von der Schwelle abhaengt, verteuert jede unbedachte
    Anmeldung *jede laufende Messung*.
  * **Die Breite.** `IR = IC * sqrt(BR)`: Mehr Symbole je Tag heben den
    Informationsgehalt eines Tages. Das Universum haette 2.189 Symbole
    ueber 1 Mio. $/Tag, der Bot handelt 1.200 (BEFUNDE §H).

**Was dieses Modul nicht kann.** Es sagt, wann eine Frage entscheidbar
ist - nicht, ob die Antwort gefaellt. Und es rechnet mit dem *bisher
gemessenen* Effekt: Ist der selbst noch Rauschen, ist auch die
Hochrechnung Rauschen. Deshalb fuehrt jede Zeile die Zahl der Tage mit,
auf denen sie beruht.
"""

from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import statistik

NIE = 10**9
"""Rueckgabe von `statistik.noetige_gruppen` bei Effekt null."""

UNENTSCHEIDBAR_AB = 5_000
"""Handelstage (~20 Jahre), ab denen eine Frage als tot gilt.

Keine willkuerliche Grenze: Das Projekt hat 9 Jahre freie Kursdaten. Eine
Frage, die 20 Jahre braeuchte, ist mit den verfuegbaren Mitteln nicht
beantwortbar - unabhaengig davon, wie geduldig man ist.
"""

HANDELSTAGE_JE_JAHR = 252

MIN_TAGE_HOCHRECHNUNG = 20
"""Handelstage, unter denen keine Hochrechnung ausgewiesen wird.

**Der wichtigste Schutz dieses Moduls.** `noetige_gruppen` rechnet mit
dem bisher gemessenen Effekt. Bei 13 Handelstagen ist dieser Effekt
selbst fast nur Rauschen - eine Hochrechnung darauf erbt die
Unsicherheit und liefert trotzdem eine glatte Zahl mit Datum. Genau die
Art Ausgabe, die BEFUNDE §G13 als teuerstes Muster des Projekts benennt:
plausibel aussehend und falsch.

Ein Effekt nahe null nach 13 Tagen heisst NICHT "nie entscheidbar",
sondern "noch nichts gemessen". Die 20 sind dieselbe Untergrenze, die
`statistik.gruppierter_test` als `min_gruppen` fuehrt.
"""


@dataclass
class Frage:
    """Eine offene Frage samt ihrer Entscheidbarkeit."""

    name: str
    quelle: str
    effekt: float
    streuung: float
    tage_vorhanden: int
    schwelle: float
    achse: str = ""
    hinweis: str = ""

    @property
    def tage_noetig(self) -> int:
        return statistik.noetige_gruppen(self.effekt, self.streuung,
                                         t_ziel=self.schwelle)

    @property
    def tage_fehlend(self) -> int:
        return max(0, self.tage_noetig - self.tage_vorhanden)

    @property
    def zu_frueh(self) -> bool:
        """Zu wenig Daten fuer eine Hochrechnung - kein Urteil moeglich."""
        return self.tage_vorhanden < MIN_TAGE_HOCHRECHNUNG

    @property
    def tot(self) -> bool:
        """Wird diese Frage je entscheidbar sein?

        Nur beantwortbar, wenn ueberhaupt genug gemessen wurde. Sonst ist
        die ehrliche Antwort `zu_frueh`, nicht `tot`.
        """
        return (not self.zu_frueh) and self.tage_noetig >= UNENTSCHEIDBAR_AB

    @property
    def datum(self) -> str:
        """Wann waere sie beantwortet - bei einem Handelstag je Werktag?"""
        if self.tot:
            return "nie"
        if self.tage_fehlend == 0:
            return "jetzt"
        d = np.busday_offset(np.datetime64(dt.date.today()),
                             self.tage_fehlend, roll="forward")
        return str(d)

    def zeile(self) -> str:
        if self.zu_frueh:
            noetig, wann = "     ?", "offen"
        elif self.tot:
            noetig, wann = "     -", "nie"
        else:
            noetig, wann = f"{self.tage_noetig:>6,}".replace(",", "."), self.datum
        return (f"  {self.name:<34} {self.tage_vorhanden:>5}  {noetig}  "
                f"{wann:<12} {self.hinweis}")


def _frage_aus_bot(bot_id: str, basis: str, store=None) -> Frage | None:
    """Eine Flottenfrage: Schlaegt dieser Bot seine Referenz?"""
    from . import shadow_eval

    try:
        v = shadow_eval.vergleich_gepaart(bot_id, basis, store, schreiben=False)
    except Exception:  # noqa: BLE001
        return None
    if v.get("n_tage", 0) < 3 or "diff_std" not in v:
        return Frage(f"{bot_id} vs {basis}", "flotte", 0.0, 1.0,
                     int(v.get("n_tage", 0)), v.get("schwelle", 2.85),
                     hinweis="noch keine Messung")
    return Frage(
        name=f"{bot_id} vs {basis}",
        quelle="flotte",
        effekt=float(v["diff_mittel"]),
        streuung=float(v["diff_std"]),
        tage_vorhanden=int(v["n_tage"]),
        schwelle=float(v["schwelle"]),
        hinweis=(f"t={v['t_wert']:+.2f}" if v.get("t_wert") is not None else ""),
    )


def offene_fragen(store=None) -> list[Frage]:
    """Sammelt alle Fragen, die derzeit auf Daten warten.

    **Jeder Bot wird gegen seine EIGENE registrierte Referenz gemessen**
    (`Bot.basis_bot`), nicht gegen eine global gewaehlte. Das ist keine
    Feinheit: B04 unterscheidet sich von B00 in einer Achse
    (`max_hold_days`), von B09 dagegen in dreien. Ein Vergleich ueber
    mehrere Achsen misst nichts - "eine Achse je Bot" ist die
    Anmeldebedingung von `fleet.anmelden` und muss in der Auswertung
    gelten, sonst war die Disziplin bei der Anmeldung umsonst.

    Diese Zeile ist die Lehre aus BEFUNDE §G6: Dort war die Referenz
    `B00_basis` zwei Wochen lang falsch, und alle Vergleiche der halben
    Flotte bezogen sich auf eine Konfiguration, die live nicht mehr lief.
    """
    from . import fleet, lernkern

    fragen: list[Frage] = []
    schwelle = fleet.schwelle_sigma(store)

    for b in fleet.aktive_bots(store):
        if not b.basis_bot:
            continue          # B00 ist die Referenz, nicht die Frage
        f = _frage_aus_bot(b.bot_id, b.basis_bot, store)
        if f:
            f.achse = b.achse or ""
            fragen.append(f)

    # --- Der Lernkern -----------------------------------------------------
    akt = lernkern.aktive_version()
    df = lernkern.verlauf(limit=1)
    if not df.empty:
        r = df.iloc[0]
        tage = int(r["n_tage_bewertet"] or 0)
        ic = float(r["ic"]) if pd.notna(r["ic"]) else 0.0
        # Streuung aus dem gemessenen t zurueckrechnen: t = ic/(s/sqrt(n))
        t = float(r["t"]) if pd.notna(r["t"]) else np.nan
        streu = (abs(ic) / abs(t) * math.sqrt(tage)) if (np.isfinite(t) and t) else 1.0
        fragen.append(Frage(
            name="Modell schlaegt Score (Panel)", quelle="lernkern",
            effekt=ic, streuung=streu, tage_vorhanden=tage, schwelle=schwelle,
            achse="ml", hinweis=f"{r['quelle']}, {'aktiv' if akt else 'Kandidat'}"))
    else:
        fragen.append(Frage("Modell schlaegt Score (Panel)", "lernkern",
                            0.0, 1.0, 0, schwelle, achse="ml",
                            hinweis="noch nicht trainiert"))

    return fragen


def hebel(store=None) -> list[str]:
    """Was die Wartezeit verkuerzt - mit Zahlen, nicht mit Ratschlaegen."""
    from . import fleet

    n = fleet.n_versuche(store)
    s_jetzt = fleet.schwelle_sigma(store)
    z = []

    # --- Hebel 1: der Versuchszaehler ------------------------------------
    # n haengt quadratisch von der Schwelle ab. Der Aufschlag durch fuenf
    # weitere Anmeldungen laesst sich deshalb als Prozentsatz angeben, der
    # fuer JEDE laufende Messung gilt.
    s_plus5 = math.sqrt(2 * math.log(n + 5)) + 0.5
    auf = (s_plus5 / s_jetzt) ** 2 - 1
    z.append(
        f"Versuchszaehler: {n} Versuche -> Schwelle {s_jetzt:.2f}. "
        f"Fuenf weitere Anmeldungen heben sie auf {s_plus5:.2f} und "
        f"verlaengern JEDE laufende Messung um {auf:.0%}.")
    z.append(
        "  -> Ideen zuerst im Historienlauf pruefen (scripts/10_simulate.py). "
        "Er kostet keinen Zaehler und darf verwerfen (BETRIEBSPLAN §4).")

    # --- Hebel 2: die Breite ---------------------------------------------
    # IR = IC * sqrt(BR); Zeitbedarf ~ 1/IR^2, also ~ 1/BR.
    z.append(
        f"Breite: Der Bot handelt 1.200 von 2.189 liquiden Symbolen. "
        f"IR = IC*sqrt(BR) heisst: volle Breite kuerzt den Zeitbedarf auf "
        f"{1200/2189:.0%} - die Wartezeit faellt fast auf die Haelfte.")
    z.append(
        "  -> Aendert die Handelslogik. Reihenfolge: erst Historienlauf, "
        "dann eigener Flottenbot, fruehestens nach dem 10.10.")

    # --- Hebel 3: die Historie -------------------------------------------
    z.append(
        "Historie: 969 Handelstage sind sofort da, der Schatten waechst um "
        "einen je Tag. Fuer jede Frage, die sich rueckwaerts stellen laesst, "
        "ist das der Unterschied zwischen Tagen und Jahren.")
    return z


def bericht(store=None) -> str:
    """Die Fokus-Rangliste: was als naechstes beantwortbar ist."""
    fragen = offene_fragen(store)
    lebend = sorted([f for f in fragen if not f.tot and not f.zu_frueh],
                    key=lambda f: f.tage_fehlend)
    frueh = [f for f in fragen if f.zu_frueh]
    tot = [f for f in fragen if f.tot]

    z = ["=" * 90,
         "  FOKUS - welche Frage ist als naechstes entscheidbar?",
         "=" * 90,
         f"  Stand: {dt.date.today()}   Referenz je Bot: seine registrierte basis_bot",
         "",
         f"  {'Frage':<34} {'Tage':>5}  {'noetig':>6}  {'entscheidbar':<12} Stand",
         "  " + "-" * 86]
    z += [f.zeile() for f in lebend] or ["  (keine offenen Fragen)"]

    if frueh:
        z += ["",
              f"  NOCH KEIN URTEIL - unter {MIN_TAGE_HOCHRECHNUNG} Handelstagen:",
              "  " + "-" * 86]
        z += [f.zeile() for f in frueh]
        z += ["",
              "  Diese Zeilen tragen bewusst KEINE Hochrechnung. Der bisher",
              "  gemessene Effekt ist selbst noch Rauschen; ein Datum daraus",
              "  waere eine glatte Zahl ohne Deckung (BEFUNDE §G13)."]

    if tot:
        z += ["",
              "  NICHT ENTSCHEIDBAR - gemessener Effekt zu nah an null:",
              "  " + "-" * 86]
        z += [f.zeile() for f in tot]
        z += ["",
              "  Diese Fragen werden durch Warten NICHT beantwortet. Mehr",
              "  Kalenderzeit aendert daran strukturell nichts - so geschehen",
              "  bei B01/B02/B03/B05 (BEFUNDE §E, stillgelegt am 21.08.).",
              "  Entweder die Achse groesser fassen oder den Bot stilllegen.",
              "",
              "  AUSNAHME, die hier nicht automatisch erkennbar ist: Ein Bot",
              "  kann bewusst auf einen Zustand warten, den es noch nicht gab.",
              "  `B06_ohne_regime` ist im Bullenmarkt per Konstruktion",
              "  wirkungslos und misst erst beim Regimewechsel etwas (§E/§G8:",
              "  18 % aller Handelstage liegen unter dem 200-Tage-Schnitt).",
              "  Ein Effekt von null ist dort das erwartete Zwischenergebnis,",
              "  kein Grund zur Stilllegung."]

    z += ["",
          "  WICHTIG - was diese Spalte NICHT ist: Sie sagt, ab wann die",
          "  Datenlage eine Frage tragen KOENNTE. Sie ersetzt keinen vorab",
          "  festgelegten Entscheidungstermin. Fuer B11 gilt weiterhin der",
          "  Vertrag aus BETRIEBSPLAN §3.3 mit dem 10.10.2026 und allen vier",
          "  Kriterien - ein frueheres Datum hier ist KEINE Erlaubnis, frueher",
          "  zu entscheiden. Genau diese Aufweichung beschreibt §G10 als die",
          "  Gefahr, gegen die der Vertrag existiert.",
          "", "=" * 90, "  HEBEL - was die Wartezeit verkuerzt", "=" * 90]
    for h in hebel(store):
        z.append(f"  {h}" if not h.startswith("  ") else f"  {h}")
    z += ["",
          "  Die Spalte 'Tage' ist die Zahl unabhaengiger HANDELSTAGE, nicht",
          "  die der Zeilen oder Trades (BEFUNDE §B1). 20.690 Schatten-",
          "  vorhersagen sind 19 Beobachtungen.",
          "=" * 90]
    return "\n".join(z)
