"""Ausbruch-Strategie: kaufen, was gerade stark gestiegen ist.

**Die Idee (Nutzer, 11.09.2026).** Alle 15 Minuten das ganze Universum
pruefen. Springt ein Wert innerhalb weniger Stunden um X Prozent, wird
ein grosser Teil des Kapitals hineingelegt - in der Erwartung, dass die
Bewegung weiterlaeuft. Entweder das stimmt, oder es kippt und ein
Schwellwert verkauft. Bewusst ein volatiles System.

Das ist das Gegenteil der Umkehr-Strategie in `engine.py`, die kauft,
was gefallen ist. Beide koennen nicht gleichzeitig recht haben - und
genau deshalb ist es ein eigener, sauber getrennter Versuch.

**Was dieses Modul NICHT tut.** Es handelt nicht. Es importiert
`trading.py` nicht und wird von keinem Dienst aufgerufen. Es rechnet
Historie durch. Der Weg zu echtem Geld fuehrt ueber die Flotte
(`docs/UMBAUPLAN.md` Schritt 6), nie direkt von hier.

---

## Die drei Stellen, an denen ein Backtest dieser Art luegt

Sie sind hier alle drei bewusst zu unseren Ungunsten aufgeloest. Wer
eine der drei umdreht, bekommt deutlich schoenere Zahlen und ein System,
das live verliert.

**1. Lookahead beim Einstieg.** Das Signal entsteht auf dem SCHLUSSKURS
von Bar t. Gekauft wird zum EROEFFNUNGSKURS von Bar t+1. Wer stattdessen
zum Schlusskurs von Bar t kauft, kauft zu dem Kurs, der den Anstieg
gerade erzeugt hat - das ist der haeufigste Fehler in genau dieser
Strategiefamilie und macht aus jedem Ergebnis eine Fiktion.

**2. Stop und Ziel in derselben Bar.** Faellt eine Bar unter den Stop
UND ueber das Ziel, ist aus Tagesdaten nicht zu erkennen, was zuerst
kam. Hier gilt immer der STOP. Das ist pessimistisch und richtig: Die
Gegenannahme laesst jede Konfiguration mit weitem Ziel und engem Stop
kuenstlich gut aussehen.

**3. Survivorship.** Das Universum kennt nur heute gelistete Symbole.
Bei einer Ausbruch-Strategie trifft das haerter als bei jeder anderen:
Der Wert, der +40 % macht und ein halbes Jahr spaeter verschwindet, ist
gar nicht erst in den Daten. `universe.survivorship_warning` beziffert
den Schein-Vorteil auf 2-4 Prozentpunkte pro Jahr (§G11) - fuer dieses
Segment eher mehr. **Jedes Ergebnis hier ist eine Obergrenze.**

---

## Die Kosten sind bei dieser Strategie der Hauptgegner

Ein Rundlauf kostet bei der gemessenen Spanne von 12,2 bps rund
**0,287 %** (§G54). Wer im Schnitt einen Tag haelt, macht bei 252
Handelstagen und einer Position 252 Rundlaeufe - das sind **72 %
Kostenlast pro Jahr und Positionsplatz**. Eine Strategie, die stuendlich
handelt, muss also nicht knapp, sondern haushoch gewinnen.

Und die 12,2 bps sind der Median des LIQUIDEN Universums. Ein Wert
mitten in einem 20-%-Sprung hat eine deutlich weitere Spanne - deshalb
ist `spanne_bps` einstellbar und sollte fuer dieses Segment eher hoch
angesetzt werden.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field, asdict
from typing import Callable, Iterable

import numpy as np
import pandas as pd

# 15-Minuten-Bars einer regulaeren US-Sitzung (09:30-16:00 ET).
BARS_JE_TAG = 26

__all__ = [
    "AusbruchConfig", "Trade", "Ergebnis", "lauf",
    "BARS_JE_TAG", "bars_aus_zeit",
]


def bars_aus_zeit(stunden: float = 0.0, tage: float = 0.0,
                  bar_minuten: int = 15) -> int:
    """Rechnet Stunden/Handelstage in Bars um.

    Ein Handelstag sind 6,5 Stunden, nicht 24 - der Unterschied ist der
    Grund, warum "ueber einen Tag" und "ueber 24 Stunden" hier zwei
    verschiedene Dinge sind.
    """
    je_stunde = 60.0 / bar_minuten
    return max(1, int(round(stunden * je_stunde + tage * BARS_JE_TAG)))


@dataclass
class AusbruchConfig:
    """Jeder Hebel dieser Strategie. Alles einstellbar, nichts versteckt.

    Die Vorgaben sind bewusst KEINE optimierten Werte - sie sind ein
    plausibler Startpunkt. Wer sie fuer "die richtigen" haelt, hat §B2
    nicht gelesen: Bei genug Durchlaeufen findet man immer eine
    Konfiguration, die in der Vergangenheit gut aussah.
    """

    # --- Einstieg: was gilt als Ausbruch? -----------------------------
    anstieg_pct: float = 10.0
    """Mindestanstieg im Pruef-Fenster, in Prozent."""

    fenster_bars: int = 8
    """Laenge des Fensters in Bars (8 x 15 Min = 2 Stunden)."""

    max_anstieg_pct: float = 100.0
    """Obergrenze. Ein Sprung von +300 % ist meist eine Kapitalmassnahme
    oder ein Datenfehler, kein handelbarer Ausbruch."""

    # --- Filter: worauf wir den Ausbruch ueberhaupt handeln -----------
    min_preis: float = 3.0
    max_preis: float = 2000.0
    """Unter 3 $ dominieren Spanne und Tick-Groesse jede Bewegung."""

    min_dollar_volumen: float = 2_000_000.0
    """Gehandelter Gegenwert im Fenster. Der wichtigste Liquiditaets-
    filter: Ein Ausbruch ohne Umsatz ist nicht handelbar, weil die
    eigene Order ihn selbst bewegt."""

    min_rel_volumen: float = 2.0
    """Umsatz im Fenster geteilt durch den ueblichen Umsatz gleicher
    Laenge. Bei Ausbruechen der aussagekraeftigste Filter ueberhaupt:
    Eine Bewegung ohne Volumen ist meist Rauschen im Orderbuch."""

    vol_referenz_bars: int = 26 * 20
    """Wogegen `min_rel_volumen` misst (20 Handelstage)."""

    # --- Position ------------------------------------------------------
    positions_pct: float = 15.0
    """Anteil des Depotwerts je Position, in Prozent."""

    max_positionen: int = 6
    max_neue_je_bar: int = 2
    """Bremse gegen den Fall, dass ein Marktbeben 50 Signale zugleich
    ausloest und das ganze Depot in eine einzige Marktbewegung laeuft."""

    max_investiert_pct: float = 100.0
    """Obergrenze fuer die Summe aller Positionen. Ueber 100 waere Hebel."""

    # --- Ausstieg ------------------------------------------------------
    halten_bars: int = 26
    """Spaetestens nach so vielen Bars wird verkauft (26 = 1 Handelstag)."""

    gewinn_pct: float = 10.0
    """Gewinnmitnahme. 0 = aus."""

    verlust_pct: float = 5.0
    """Stop. 0 = aus - dann haelt nur noch die Zeit die Position."""

    trailing_pct: float = 0.0
    """Nachziehender Stop unter dem Hoechstkurs seit Einstieg. 0 = aus."""

    # --- Kosten --------------------------------------------------------
    spanne_bps: float = 12.2
    """Geld-Brief-Spanne in bps. 12,2 ist der gemessene Median des
    liquiden Aktienuniversums (§G54, 5 Handelstage). Fuer Werte mitten
    in einem Ausbruch ist das die UNTERGRENZE."""

    slippage_bps: float = 3.0
    """Abweichung vom erwarteten Kurs, zusaetzlich zur halben Spanne."""

    # --- Betrieb -------------------------------------------------------
    startkapital: float = 100_000.0

    sperrfrist_bars: int = 26
    """Nach einem Verkauf so lange kein Wiedereinstieg in denselben Wert.
    Ohne das kauft die Strategie denselben Ausbruch mehrfach."""

    eroeffnung_sperre_bars: int = 2
    """Die ersten Bars des Tages meiden (30 Min). Dort sind Spannen
    weit und Kurse sprunghaft - `37_spannen_messen.py` schliesst
    denselben Zeitraum aus demselben Grund aus."""

    schluss_sperre_bars: int = 1
    """Keine NEUEN Positionen kurz vor Schluss. Ausstiege bleiben
    erlaubt - eine Sperre darf nie aus einer Position gefangen halten."""

    ueber_nacht: bool = True
    """False = alles vor Handelsschluss glattstellen. Schaltet das
    Overnight-Gap-Risiko aus und erhoeht den Umschlag."""

    def bars_pro_jahr_schaetzung(self) -> float:
        """Grobe Rundlaeufe je Positionsplatz und Jahr - fuer die
        Kostenvorschau, bevor ein Lauf ueberhaupt startet."""
        return 252.0 * BARS_JE_TAG / max(self.halten_bars, 1)

    def kosten_je_rundlauf_pct(self) -> float:
        """Was ein vollstaendiger Kauf-Verkauf-Zyklus kostet, in Prozent."""
        return (self.spanne_bps + 2.0 * self.slippage_bps) / 100.0

    def als_dict(self) -> dict:
        return asdict(self)


@dataclass
class Trade:
    symbol: str
    einstieg_ts: pd.Timestamp
    einstieg_kurs: float
    ausstieg_ts: pd.Timestamp | None = None
    ausstieg_kurs: float | None = None
    grund: str = ""
    stueck: float = 0.0
    rendite_pct: float = 0.0
    """Nach Kosten."""
    rendite_brutto_pct: float = 0.0
    gehalten_bars: int = 0
    ausloeser_anstieg_pct: float = 0.0
    rel_volumen: float = 0.0
    gewinn_usd: float = 0.0


@dataclass
class Ergebnis:
    config: AusbruchConfig
    trades: pd.DataFrame
    equity: pd.Series
    kennzahlen: dict = field(default_factory=dict)
    hinweise: list[str] = field(default_factory=list)
    n_signale: int = 0
    n_signale_verworfen: dict = field(default_factory=dict)


def _kauf_kurs(roh: float, cfg: AusbruchConfig) -> float:
    """Was ein Kauf wirklich kostet: halbe Spanne plus Slippage."""
    return roh * (1.0 + (cfg.spanne_bps / 2.0 + cfg.slippage_bps) / 10_000.0)


def _verkauf_kurs(roh: float, cfg: AusbruchConfig) -> float:
    return roh * (1.0 - (cfg.spanne_bps / 2.0 + cfg.slippage_bps) / 10_000.0)


def _signale_je_symbol(
    o: np.ndarray, h: np.ndarray, l: np.ndarray, c: np.ndarray,
    v: np.ndarray, cfg: AusbruchConfig,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict]:
    """Wo im Kursverlauf eines Symbols feuert ein Ausbruch?

    Vollstaendig vektorisiert - bei 1.200 Symbolen x 6.700 Bars ist eine
    Python-Schleife je Bar nicht vertretbar.

    Returns:
        (index_der_signale, anstieg_pct, rel_volumen, verworfen_zaehler)
        Der Index bezieht sich auf den Bar, dessen SCHLUSSKURS das
        Signal ausloest. Gekauft wird auf index+1.
    """
    n = len(c)
    f = cfg.fenster_bars
    verworfen: dict[str, int] = {}
    if n < f + 2:
        return np.array([], int), np.array([]), np.array([]), verworfen

    # Anstieg ueber das Fenster: Schluss jetzt gegen Schluss vor f Bars.
    frueher = np.full(n, np.nan)
    frueher[f:] = c[:-f]
    with np.errstate(invalid="ignore", divide="ignore"):
        anstieg = (c / frueher - 1.0) * 100.0

    treffer = np.isfinite(anstieg) & (anstieg >= cfg.anstieg_pct)
    verworfen["kein_anstieg"] = int(n - treffer.sum())

    def _weg(maske: np.ndarray, name: str) -> np.ndarray:
        nonlocal treffer
        vorher = int(treffer.sum())
        treffer = treffer & maske
        verworfen[name] = vorher - int(treffer.sum())
        return treffer

    _weg(np.isfinite(anstieg) & (anstieg <= cfg.max_anstieg_pct), "zu_gross")
    _weg((c >= cfg.min_preis) & (c <= cfg.max_preis), "preis")

    # Dollar-Volumen im Fenster: Summe aus Volumen x typischem Kurs.
    dollar = v * c
    kum = np.concatenate([[0.0], np.nancumsum(dollar)])
    fenster_dollar = np.full(n, np.nan)
    fenster_dollar[f:] = kum[f + 1:] - kum[1:n - f + 1]
    _weg(np.isfinite(fenster_dollar)
         & (fenster_dollar >= cfg.min_dollar_volumen), "volumen")

    # Relatives Volumen: Fenster gegen den ueblichen Umsatz gleicher
    # Laenge. Der Referenzzeitraum endet VOR dem Fenster - sonst misst
    # der Vergleich sich selbst mit.
    ref = cfg.vol_referenz_bars
    rel = np.full(n, np.nan)
    if n > ref + f:
        ref_kum = np.full(n, np.nan)
        ref_kum[ref + f:] = (kum[ref + 1:n - f + 1] - kum[1:n - ref - f + 1])
        ref_je_fenster = ref_kum / ref * f
        with np.errstate(invalid="ignore", divide="ignore"):
            rel = fenster_dollar / ref_je_fenster
    if cfg.min_rel_volumen > 0:
        _weg(np.isfinite(rel) & (rel >= cfg.min_rel_volumen), "rel_volumen")

    # Auf index+1 wird gekauft - der letzte Bar kann kein Signal tragen.
    moeglich = np.zeros(n, bool)
    moeglich[:-1] = True
    _weg(moeglich, "kein_folgebar")

    idx = np.flatnonzero(treffer)
    return idx, anstieg[idx], rel[idx], verworfen


def lauf(
    bars: dict[str, pd.DataFrame],
    cfg: AusbruchConfig,
    *,
    fortschritt: Callable[[float, str], None] | None = None,
    abbruch: Callable[[], bool] | None = None,
) -> Ergebnis:
    """Faehrt die Strategie ueber die Historie.

    Args:
        bars: Symbol -> DataFrame mit open/high/low/close/volume,
            Index ist der Zeitstempel (UTC), aufsteigend.
        cfg: alle Parameter.
        fortschritt: wird mit (anteil 0..1, Text, Zustand) gerufen.
            `Zustand` ist ein dict mit den LIVE-Werten des laufenden
            Depots (Kapital, Gewinn, offene Positionen, Trades) - die
            Oberflaeche zeigt damit waehrend des Laufs, ob die Taktik
            traegt, statt erst am Ende. Callbacks mit nur zwei
            Parametern werden weiterhin akzeptiert.
        abbruch: liefert True, wenn der Lauf abbrechen soll.

    Returns:
        `Ergebnis` mit Trades, Equity-Kurve und Kennzahlen.
    """
    if not bars:
        raise ValueError("Keine Kursdaten uebergeben.")

    stoppen = abbruch or (lambda: False)

    def melde(anteil: float, text: str, zustand: dict | None = None) -> None:
        """Ruft den Callback - egal ob er zwei oder drei Parameter nimmt."""
        if fortschritt is None:
            return
        try:
            fortschritt(anteil, text, zustand or {})
        except TypeError:
            fortschritt(anteil, text)

    # --- 1. Gemeinsame Zeitachse --------------------------------------
    melde(0.02, "Zeitachse aufbauen ...")
    achse = pd.DatetimeIndex(
        sorted(set().union(*(df.index for df in bars.values())))
    )
    n_bars = len(achse)
    if n_bars < cfg.fenster_bars + 3:
        raise ValueError(f"Zu wenige Bars ({n_bars}) fuer Fenster "
                         f"{cfg.fenster_bars}.")

    # --- 2. Signale je Symbol, vektorisiert ---------------------------
    # Ausgerichtet auf die gemeinsame Achse, damit der Portfolio-Lauf
    # spaeter mit einem einzigen Index auf jedes Symbol zugreifen kann.
    spalten = ("open", "high", "low", "close", "volume")
    daten: dict[str, tuple[np.ndarray, ...]] = {}
    signale: dict[int, list[tuple]] = {}
    n_signale = 0
    verworfen_gesamt: dict[str, int] = {}

    symbole = sorted(bars)
    for i, sym in enumerate(symbole):
        if stoppen():
            raise InterruptedError("Vom Nutzer abgebrochen.")
        if i % 25 == 0:
            melde(0.02 + 0.55 * i / len(symbole),
                  f"Signale: {i}/{len(symbole)} Symbole, "
                  f"{n_signale} Ausbrueche gefunden")
        df = bars[sym]
        fehlend = [s for s in spalten if s not in df.columns]
        if fehlend:
            continue
        df = df[~df.index.duplicated(keep="last")].reindex(achse)
        arr = tuple(df[s].to_numpy(dtype=float) for s in spalten)
        daten[sym] = arr
        o, h, l, c, v = arr
        idx, anst, rel, verw = _signale_je_symbol(o, h, l, c, v, cfg)
        for k, val in verw.items():
            verworfen_gesamt[k] = verworfen_gesamt.get(k, 0) + val
        for j, pos in enumerate(idx):
            signale.setdefault(int(pos), []).append(
                (sym, float(anst[j]), float(rel[j] if np.isfinite(rel[j]) else 0.0))
            )
        n_signale += len(idx)

    if not daten:
        raise ValueError("Kein Symbol hatte vollstaendige Spalten.")

    # --- 3. Portfolio-Lauf, Bar fuer Bar ------------------------------
    melde(0.6, f"{n_signale:,} Ausbrueche gefunden - Depot durchrechnen ...")

    kapital = float(cfg.startkapital)
    cash = kapital
    offen: dict[str, dict] = {}
    gesperrt: dict[str, int] = {}
    trades: list[Trade] = []
    equity_werte = np.full(n_bars, np.nan)

    tage = achse.tz_convert("America/New_York").date if achse.tz is not None \
        else achse.date
    # Wievielter Bar des jeweiligen Handelstages - fuer die Eroeffnungs-
    # und Schlusssperre. Ein fester Zaehler waere falsch, sobald ein Tag
    # unvollstaendig ist (halbe Handelstage um Feiertage).
    bar_im_tag = np.zeros(n_bars, int)
    letzter_des_tages = np.zeros(n_bars, bool)
    z = 0
    for i in range(n_bars):
        if i > 0 and tage[i] != tage[i - 1]:
            z = 0
            letzter_des_tages[i - 1] = True
        bar_im_tag[i] = z
        z += 1
    letzter_des_tages[n_bars - 1] = True

    def _schliessen(sym: str, i: int, roh: float, grund: str) -> None:
        nonlocal cash
        p = offen.pop(sym)
        kurs = _verkauf_kurs(roh, cfg)
        erloes = p["stueck"] * kurs
        cash += erloes
        brutto = (roh / p["roh_einstieg"] - 1.0) * 100.0
        netto = (kurs / p["kurs_einstieg"] - 1.0) * 100.0
        trades.append(Trade(
            symbol=sym,
            einstieg_ts=achse[p["bar"]], einstieg_kurs=p["kurs_einstieg"],
            ausstieg_ts=achse[i], ausstieg_kurs=kurs, grund=grund,
            stueck=p["stueck"], rendite_pct=netto, rendite_brutto_pct=brutto,
            gehalten_bars=i - p["bar"],
            ausloeser_anstieg_pct=p["anstieg"], rel_volumen=p["rel_vol"],
            gewinn_usd=erloes - p["einsatz"],
        ))
        gesperrt[sym] = i + cfg.sperrfrist_bars

    for i in range(n_bars):
        if stoppen():
            raise InterruptedError("Vom Nutzer abgebrochen.")
        if i % 200 == 0:
            gewinn = kapital - cfg.startkapital
            treffer = ([t.rendite_pct > 0 for t in trades] or [False])
            melde(
                0.6 + 0.38 * i / n_bars,
                f"{achse[i]:%d.%m. %H:%M}  |  {len(trades)} Trades  |  "
                f"Depot {kapital:,.0f} $  ({gewinn:+,.0f})",
                {
                    "kapital": float(kapital),
                    "gewinn_usd": float(gewinn),
                    "gewinn_pct": float(gewinn / cfg.startkapital * 100.0),
                    "cash": float(cash),
                    "offene_positionen": len(offen),
                    "n_trades": len(trades),
                    "trefferquote_pct": float(
                        sum(treffer) / len(treffer) * 100.0) if trades else 0.0,
                    "zeitpunkt": str(achse[i]),
                    "bar": i, "bars_gesamt": n_bars,
                },
            )

        # --- 3a. Ausstiege zuerst. Eine Position, die heute gestoppt
        # wird, darf nicht noch Kapital fuer einen Neukauf binden.
        for sym in list(offen):
            o, h, l, c, v = daten[sym]
            if not np.isfinite(c[i]):
                continue
            p = offen[sym]
            if i <= p["bar"]:
                continue
            p["hoch"] = max(p["hoch"], h[i] if np.isfinite(h[i]) else p["hoch"])

            stop = p["stop"]
            if cfg.trailing_pct > 0:
                stop = max(stop, p["hoch"] * (1.0 - cfg.trailing_pct / 100.0))

            # REIHENFOLGE IST ABSICHT: Stop vor Ziel. Beruehrt eine Bar
            # beides, ist aus ihr nicht zu lesen, was zuerst kam - die
            # pessimistische Annahme ist die einzige ehrliche.
            if cfg.verlust_pct > 0 or cfg.trailing_pct > 0:
                if np.isfinite(l[i]) and l[i] <= stop:
                    _schliessen(sym, i, min(stop, o[i] if np.isfinite(o[i])
                                            else stop), "stop")
                    continue
            if cfg.gewinn_pct > 0 and np.isfinite(h[i]) and h[i] >= p["ziel"]:
                _schliessen(sym, i, max(p["ziel"], o[i] if np.isfinite(o[i])
                                        else p["ziel"]), "gewinnziel")
                continue
            if i - p["bar"] >= cfg.halten_bars:
                _schliessen(sym, i, c[i], "zeit")
                continue
            if not cfg.ueber_nacht and letzter_des_tages[i]:
                _schliessen(sym, i, c[i], "tagesschluss")
                continue

        # --- 3b. Depotwert NACH den Ausstiegen ------------------------
        wert = cash
        for sym, p in offen.items():
            c_arr = daten[sym][3]
            kurs = c_arr[i] if np.isfinite(c_arr[i]) else p["kurs_einstieg"]
            wert += p["stueck"] * kurs
        kapital = wert
        equity_werte[i] = wert

        # --- 3c. Einstiege: Signal von Bar i-1, Kauf zum Open von i ---
        kandidaten = signale.get(i - 1, [])
        if not kandidaten:
            continue
        if bar_im_tag[i] < cfg.eroeffnung_sperre_bars:
            continue
        # Der GANZE Bereich bis zum Schluss ist gesperrt, nicht nur der
        # eine Bar `i + schluss_sperre_bars`. Bei einem Wert von 3 waere
        # sonst Bar i+1 und i+2 erlaubt und nur i+3 gesperrt - also
        # genau das Gegenteil der Absicht.
        bis = min(i + cfg.schluss_sperre_bars, n_bars - 1)
        if letzter_des_tages[i] or letzter_des_tages[i:bis + 1].any():
            continue

        # Bei mehreren Signalen zugleich: der staerkste Umsatzschub
        # zuerst. Eine willkuerliche Reihenfolge (etwa alphabetisch)
        # waere ein verstecktes Auswahlkriterium.
        kandidaten = sorted(kandidaten, key=lambda t: -t[2])
        neu = 0
        for sym, anstieg, rel_vol in kandidaten:
            if neu >= cfg.max_neue_je_bar:
                break
            if len(offen) >= cfg.max_positionen or sym in offen:
                continue
            if gesperrt.get(sym, -1) > i:
                continue
            o = daten[sym][0]
            if not np.isfinite(o[i]) or o[i] <= 0:
                continue

            einsatz = kapital * cfg.positions_pct / 100.0
            investiert = sum(
                p["stueck"] * (daten[s][3][i] if np.isfinite(daten[s][3][i])
                               else p["kurs_einstieg"])
                for s, p in offen.items()
            )
            if investiert + einsatz > kapital * cfg.max_investiert_pct / 100.0:
                continue
            einsatz = min(einsatz, cash)
            if einsatz <= 0:
                continue

            kurs = _kauf_kurs(o[i], cfg)
            stueck = einsatz / kurs
            cash -= stueck * kurs
            offen[sym] = {
                "bar": i, "stueck": stueck, "kurs_einstieg": kurs,
                "roh_einstieg": o[i], "einsatz": stueck * kurs,
                "hoch": o[i], "anstieg": anstieg, "rel_vol": rel_vol,
                "stop": o[i] * (1.0 - cfg.verlust_pct / 100.0)
                        if cfg.verlust_pct > 0 else 0.0,
                "ziel": o[i] * (1.0 + cfg.gewinn_pct / 100.0)
                        if cfg.gewinn_pct > 0 else np.inf,
            }
            neu += 1

    # Offene Positionen am Ende zum letzten Kurs glattstellen, sonst
    # haengt das Ergebnis an zufaellig offenen Wetten.
    for sym in list(offen):
        c = daten[sym][3]
        letzte = c[np.isfinite(c)]
        if len(letzte):
            _schliessen(sym, n_bars - 1, float(letzte[-1]), "lauf_ende")
    if offen:
        offen.clear()
    equity_werte[n_bars - 1] = cash + 0.0

    melde(0.99, "Kennzahlen rechnen ...")
    equity = pd.Series(equity_werte, index=achse).ffill().fillna(cfg.startkapital)
    t_df = pd.DataFrame([asdict(t) for t in trades])
    erg = Ergebnis(config=cfg, trades=t_df, equity=equity,
                   n_signale=n_signale, n_signale_verworfen=verworfen_gesamt)
    erg.kennzahlen = _kennzahlen(erg, cfg)
    erg.hinweise = _hinweise(erg, cfg, len(symbole))
    melde(1.0, "fertig")
    return erg


def _kennzahlen(erg: Ergebnis, cfg: AusbruchConfig) -> dict:
    """Die Zahlen, die im Kopf der Oberflaeche stehen."""
    from . import statistik

    eq = erg.equity
    t = erg.trades
    k: dict = {}
    k["startkapital"] = float(cfg.startkapital)
    k["endkapital"] = float(eq.iloc[-1]) if len(eq) else float(cfg.startkapital)
    k["rendite_pct"] = (k["endkapital"] / k["startkapital"] - 1.0) * 100.0
    k["n_trades"] = int(len(t))
    k["n_signale"] = erg.n_signale

    lauf_max = eq.cummax()
    k["max_drawdown_pct"] = float(((eq / lauf_max - 1.0).min()) * 100.0) if len(eq) else 0.0

    if len(t):
        k["trefferquote_pct"] = float((t["rendite_pct"] > 0).mean() * 100.0)
        k["mittel_pct"] = float(t["rendite_pct"].mean())
        k["median_pct"] = float(t["rendite_pct"].median())
        k["brutto_mittel_pct"] = float(t["rendite_brutto_pct"].mean())
        k["kosten_je_trade_pct"] = k["brutto_mittel_pct"] - k["mittel_pct"]
        k["bester_pct"] = float(t["rendite_pct"].max())
        k["schlechtester_pct"] = float(t["rendite_pct"].min())
        k["haltedauer_bars"] = float(t["gehalten_bars"].median())
        gewinne = t.loc[t["gewinn_usd"] > 0, "gewinn_usd"].sum()
        verluste = abs(t.loc[t["gewinn_usd"] <= 0, "gewinn_usd"].sum())
        k["profit_faktor"] = float(gewinne / verluste) if verluste else float("inf")
        k["kosten_gesamt_usd"] = float(
            (t["rendite_brutto_pct"] - t["rendite_pct"]).mul(
                t["stueck"] * t["einstieg_kurs"] / 100.0).sum()
        )

        # DER massgebliche Test. Trades desselben Handelstages sehen
        # denselben Markt und sind keine unabhaengigen Beobachtungen
        # (§B1). Der Horizont ist die mediane Haltedauer in TAGEN -
        # ohne ihn liegt die Fehlalarmquote bei 39,5 % statt 5 (§G12).
        tage = pd.to_datetime(t["einstieg_ts"]).dt.date
        horizont = max(1, int(round(t["gehalten_bars"].median() / BARS_JE_TAG)))
        try:
            res = statistik.gruppierter_test(
                t["rendite_pct"], pd.Series(tage.values),
                horizont=horizont, min_gruppen=20,
            )
            k["t_wert"] = float(getattr(res, "t_ueberlappung", None)
                                or getattr(res, "t", 0.0))
            k["t_naiv"] = float(getattr(res, "t_naiv", 0.0))
            k["n_handelstage"] = int(getattr(res, "n_gruppen", 0))
            k["belastbar"] = bool(getattr(res, "belastbar", False))
            k["horizont_tage"] = horizont
        except Exception as e:  # noqa: BLE001 - ein Test darf den Lauf nie kippen
            k["t_wert"] = float("nan")
            k["t_hinweis"] = f"{type(e).__name__}: {e}"
    else:
        k.update(trefferquote_pct=0.0, mittel_pct=0.0, median_pct=0.0,
                 t_wert=float("nan"), n_handelstage=0, belastbar=False)
    return k


def _hinweise(erg: Ergebnis, cfg: AusbruchConfig, n_symbole: int) -> list[str]:
    """Was zu diesem Ergebnis dazugehoert, damit es nicht falsch gelesen wird.

    Diese Liste steht in der Oberflaeche NEBEN dem Ergebnis, nicht unter
    einem Aufklapp-Pfeil. Eine Warnung, die man wegklicken kann, ist
    keine.
    """
    k = erg.kennzahlen
    H: list[str] = []

    H.append(
        f"SURVIVORSHIP: Das Universum kennt nur heute gelistete Symbole. "
        f"Werte, die nach einem Ausbruch verschwanden, fehlen vollstaendig - "
        f"bei DIESER Strategie ist das der groesste einzelne Vorbehalt. "
        f"Der Schein-Vorteil liegt laut §G11 bei 2-4 Prozentpunkten pro Jahr, "
        f"in diesem Segment eher darueber. Jede Zahl hier ist eine OBERGRENZE."
    )

    rundlaeufe = cfg.bars_pro_jahr_schaetzung()
    last = rundlaeufe * cfg.kosten_je_rundlauf_pct()
    H.append(
        f"KOSTEN: {cfg.kosten_je_rundlauf_pct():.3f} % je Rundlauf bei "
        f"{cfg.spanne_bps:g} bps Spanne. Bei {cfg.halten_bars} Bars Haltedauer "
        f"sind das ~{rundlaeufe:.0f} Rundlaeufe pro Jahr und Positionsplatz "
        f"= ~{last:.0f} % Kostenlast jaehrlich. Die Strategie muss das erst "
        f"verdienen, bevor der erste Dollar Gewinn entsteht."
    )

    n_tage = k.get("n_handelstage", 0)
    if n_tage < 20:
        H.append(
            f"KEIN BEFUND MOEGLICH: nur {n_tage} Handelstage mit Trades. "
            f"Massgeblich ist die Zahl der TAGE, nicht der Trades (§B1). "
            f"Unter 20 traegt keine Aussage."
        )
    elif not np.isnan(k.get("t_wert", float("nan"))):
        H.append(
            f"STATISTIK: t = {k['t_wert']:.2f} ueber {n_tage} Handelstage "
            f"(Horizont {k.get('horizont_tage', 1)} Tage, "
            f"ueberlappungskorrigiert). Der naive t-Wert waere "
            f"{k.get('t_naiv', float('nan')):.2f} - er ist bedeutungslos, "
            f"nicht bloss ungenau."
        )

    if k.get("n_trades", 0) and k.get("kosten_je_trade_pct", 0) > 0:
        anteil = k["kosten_je_trade_pct"] / max(abs(k["brutto_mittel_pct"]), 1e-9)
        if anteil > 0.5:
            H.append(
                f"Die Kosten fressen {anteil:.0%} des Bruttoergebnisses je Trade "
                f"({k['brutto_mittel_pct']:+.3f} % brutto -> "
                f"{k['mittel_pct']:+.3f} % netto)."
            )

    if k.get("n_trades", 0) < 30:
        H.append(f"Nur {k.get('n_trades', 0)} Trades - zu wenig fuer jede Aussage.")

    H.append(
        "Ein Historienlauf darf eine Idee VERWERFEN, nie abnehmen "
        "(BETRIEBSPLAN §4). Was hier ueberlebt, geht als Flottenbot in "
        "den Vorwaertsschatten - nicht live."
    )
    return H
