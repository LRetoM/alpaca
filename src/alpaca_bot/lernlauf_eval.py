"""Auswertung des Lernlaufs: gepaarter Test, Trennschaerfe, Walk-Forward.

**Warum ein eigenes Modul statt `shadow_eval.py` mitzubenutzen.**
`shadow_eval.vergleich_gepaart` und `shadow_eval.trennschaerfe` rechnen
technisch dasselbe (Tagesdifferenz zweier Equity-Kurven, t-Test,
Streuungsrechnung) - aber sie sind fest an `ShadowStore` und
`fleet.schwelle_sigma()` gebunden, also an die LIVE-Flotte und ihren
Versuchszaehler. Der Lernlauf hat keinen Store und keinen eigenen
Versuchszaehler (Historienlaeufe kosten laut `docs/UMBAUPLAN.md` §2.2
erst dann einen Versuchszaehler-Platz, wenn ein Kandidat daraus ins
Kandidatenregister geht). Die Funktionen hier arbeiten deshalb direkt auf
`pd.Series` und nehmen die Schwelle als Parameter entgegen, statt sie aus
einer Datenbank zu lesen.

**Die zweite Aufgabe dieses Moduls ist wichtiger als die erste:**
`walk_forward_auswahl` traegt die Eigenschaft, um die es beim ganzen
Umbau geht - die Auswahl fuer Jahr k sieht AUSSCHLIESSLICH Jahre < k.
Sie stand bisher als Schleife in `scripts/32_lernlauf.py:main()` und war
damit nicht isoliert testbar. Herausgezogen, damit ein Regressionstest
(`tests/test_lernlauf.py`) direkt gegen sie laufen kann - siehe
`docs/UMBAUPLAN.md` §4, letzter Abnahmepunkt: eine Mutation, die das
Bewertungsjahr in die Auswahl aufnimmt, muss einen Test toeten.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

Z_GUETE_80 = 0.84
"""Normalquantil fuer 80 % Trefferwahrscheinlichkeit (einseitig) - siehe
`shadow_eval.Z_GUETE_80`, hier dupliziert, weil dieses Modul bewusst
nichts aus `shadow_eval` importiert (keine ShadowStore-Abhaengigkeit)."""


def schwelle_sigma(n_versuche: int) -> float:
    """Zufallsschwelle fuer N Auswertungen - dieselbe Formel wie `fleet.schwelle_sigma`.

    N ist hier NICHT der Versuchszaehler der Flotte, sondern die Zahl der
    Zellen im Lernlauf-Raster (Bots x Jahresscheiben, siehe Modulkopf von
    `scripts/32_lernlauf.py`): Bei 14 Bots x 12 Jahresscheiben (15-Jahre-
    Standard) sind das 168 Auswertungen.

        schwelle = sqrt(2 * ln(n)) + 0.5

    Der Zuschlag 0.5 ist derselbe bewusste Sicherheitsaufschlag wie bei
    `fleet.schwelle_sigma`.
    """
    n = max(int(n_versuche), 2)
    return round(math.sqrt(2 * math.log(n)) + 0.5, 2)


@dataclass
class PaarVergleich:
    n_tage: int
    diff_mittel: float
    diff_std: float
    t_wert: float | None
    schwelle: float
    belastbar: bool
    min_tage: int
    hinweis: str = ""


def paarweiser_test(equity_a: pd.Series, equity_b: pd.Series, schwelle: float,
                    *, min_tage: int = 20) -> PaarVergleich:
    """Bot A gegen Bot B ueber die TAGESDIFFERENZ - wie `shadow_eval.vergleich_gepaart`.

    Beide Kurven werden auf ihren gemeinsamen Kalender ausgerichtet, dann
    d_t = rendite_A(t) - rendite_B(t) gebildet. Der Marktfaktor kuerzt
    sich heraus, weil beide Bots denselben Tag, dieselben Symbole und
    denselben Kurs sehen (`docs/BEFUNDE.md` §G22: an echten Kurven
    nachgemessen keine Aufblaehung des t-Werts fuer diese Eintages-
    Differenz - anders als bei ueberlappenden Mehrtages-Fenstern, §G12).

    Keine Sperrzone: Anders als der Schattenbetrieb, der eine laufende
    Messung gegen nachtraegliches Erzaehlen schuetzen muss, ist der
    Lernlauf ein einmaliger Blick auf abgeschlossene Historie. Er darf
    laut `docs/UMBAUPLAN.md` ohnehin nur VERWERFEN, nie ABNEHMEN - die
    Schutzfunktion der Sperrzone hat hier keinen Gegenstand.
    """
    a = equity_a.astype(float).pct_change()
    b = equity_b.astype(float).pct_change()
    d = (a - b).dropna()
    d = d[np.isfinite(d)]

    if len(d) < 3:
        return PaarVergleich(len(d), float("nan"), float("nan"), None,
                             schwelle, False, min_tage,
                             hinweis=f"nur {len(d)} Tage - kein t-Wert")

    mittel, std = float(d.mean()), float(d.std(ddof=1))
    t = mittel / (std / math.sqrt(len(d))) if std > 0 else None
    belastbar = bool(t is not None and abs(t) > schwelle and len(d) >= min_tage)
    return PaarVergleich(len(d), mittel, std,
                         round(t, 4) if t is not None else None,
                         schwelle, belastbar, min_tage)


@dataclass
class Trennschaerfe:
    n_streuung: int
    streuung: float | None
    n_tage: int
    schwelle: float
    gerade_noch: float | None
    mit_80_prozent: float | None
    kumuliert_80: float | None
    hinweis: str = ""


def trennschaerfe(equity_a: pd.Series, equity_b: pd.Series, schwelle: float,
                  *, n_tage: int | None = None) -> Trennschaerfe:
    """Welchen taeglichen Effekt koennte dieser Vergleich ueberhaupt zeigen?

    Dieselbe Rechnung wie `shadow_eval.trennschaerfe` (siehe dort fuer die
    Herleitung und den Anlass, `docs/BEFUNDE.md` §G22/§G23): Ein
    "durchgefallen" ohne diese Zahl laesst "nicht besser" und "nicht
    zeigbar" gleich aussehen.

        gerade_noch    = schwelle * s / sqrt(n)
        mit_80_prozent = (schwelle + 0.84) * s / sqrt(n)
    """
    a = equity_a.astype(float).pct_change()
    b = equity_b.astype(float).pct_change()
    d = (a - b).dropna()
    d = d[np.isfinite(d)]

    if len(d) < 3:
        return Trennschaerfe(len(d), None, 0, schwelle, None, None, None,
                             hinweis=f"nur {len(d)} Tage - keine Streuungsschaetzung")

    streuung = float(d.std(ddof=1))
    n = int(n_tage) if n_tage is not None else len(d)
    if n < 2 or streuung <= 0:
        return Trennschaerfe(len(d), round(streuung, 6), n, schwelle,
                             None, None, None,
                             hinweis="Streuung 0 - die Bots sind bitgleich, ein "
                                     "Unterschied ist grundsaetzlich nicht messbar")

    gerade_noch = schwelle * streuung / math.sqrt(n)
    mit_80 = (schwelle + Z_GUETE_80) * streuung / math.sqrt(n)
    return Trennschaerfe(len(d), round(streuung, 6), n, schwelle,
                         round(gerade_noch, 6), round(mit_80, 6),
                         round(mit_80 * n, 6))


# ---------------------------------------------------------------------------
# Walk-Forward: die Eigenschaft, um die es geht
# ---------------------------------------------------------------------------
@dataclass
class WalkForwardZeile:
    jahr: int
    gewaehlt: str
    rendite_gewaehlt: float
    rendite_basis: float
    diff: float


def walk_forward_auswahl(jahres: pd.DataFrame, scheiben: list[tuple],
                         min_auswahl_jahre: int, *,
                         basis: str = "basis") -> list[WalkForwardZeile]:
    """Fuer jede Jahresscheibe: waehle den Bot NUR aus fruehen Jahren.

    **Das ist die Kerneigenschaft des ganzen Umbaus** (`docs/UMBAUPLAN.md`
    §2.1): Die Auswahl fuer Jahr `scheiben[idx]` darf ausschliesslich
    `jahres[[s[0] for s in scheiben[:idx]]]` lesen - niemals eine Spalte,
    die das Bewertungsjahr selbst oder ein spaeteres enthaelt.

    Args:
        jahres: Zeilen = Bots, Spalten = Jahre, Werte = Jahresrendite.
        scheiben: `(jahr, start, ende)`-Tupel in chronologischer Ordnung,
            wie von `jahresscheiben()` erzeugt.
        min_auswahl_jahre: so viele Jahre muessen vor der ersten Auswahl
            liegen (sonst ist die Auswahl selbst schon Rauschen).
        basis: Name der Vergleichszeile in `jahres` (unveraenderter Bot).

    Returns:
        Eine Zeile je bewertetem Jahr, IN CHRONOLOGISCHER REIHENFOLGE.
    """
    zeilen: list[WalkForwardZeile] = []
    for idx, (jahr, _, _) in enumerate(scheiben):
        if idx < min_auswahl_jahre:
            continue
        vorherige_jahre = [s[0] for s in scheiben[:idx]]
        mittel = jahres[vorherige_jahre].mean(axis=1)
        gewaehlt = str(mittel.idxmax())
        e_gew = float(jahres.loc[gewaehlt, jahr])
        e_bas = float(jahres.loc[basis, jahr])
        zeilen.append(WalkForwardZeile(jahr, gewaehlt, e_gew, e_bas, e_gew - e_bas))
    return zeilen


@dataclass
class WalkForwardTest:
    n_jahre: int
    mittel_diff: float
    t_wert: float | None
    jahre_mit_vorsprung: int
    wechsel: int
    hinweis: str = ""


def walk_forward_test(zeilen: list[WalkForwardZeile]) -> WalkForwardTest:
    """Traegt die walk-forward getroffene Auswahl ins naechste Jahr?

    Jede Zeile ist EIN unabhaengiges Kalenderjahr - anders als bei
    taeglichen Renditen gibt es hier kein Ueberlappungsproblem (§G1/§G12),
    ein Jahr endet, bevor das naechste beginnt. Ein gewoehnlicher t-Test
    ueber die Jahresdifferenzen ist deshalb ausreichend.
    """
    if len(zeilen) < 3:
        return WalkForwardTest(len(zeilen), float("nan"), None, 0, 0,
                               hinweis=f"nur {len(zeilen)} Jahre - kein t-Wert")

    d = np.array([z.diff for z in zeilen])
    mittel, std = float(d.mean()), float(d.std(ddof=1))
    t = mittel / (std / math.sqrt(len(d))) if std > 0 else None
    wechsel = sum(1 for a, b in zip(zeilen, zeilen[1:]) if a.gewaehlt != b.gewaehlt)
    return WalkForwardTest(
        len(zeilen), mittel, round(t, 4) if t is not None else None,
        int((d > 0).sum()), wechsel,
    )
