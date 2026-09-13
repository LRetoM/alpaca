"""Querschnitt-Strategien: nicht "steigt dieser Wert", sondern "welcher am meisten".

**Warum diese Familie, nachdem die Ausbruch-Familie nichts hergab.** Die
Werkstatt hat bisher fast nur eine Frage gestellt: *Steigt dieser eine
Wert in den naechsten Stunden?* Das ist das schwerste Spiel am Markt -
kurze Haltedauer, jeder Rundlauf kostet die volle Spanne, und die
Gegenseite sind Maschinen. §G77 hat es ausgemessen: kein rechter Rand,
Mittelwert unter null.

Hier wird eine andere Frage gestellt:

    Von 1.700 Werten - welche sind JETZT die staerksten, welche die
    schwaechsten? Kauf die einen, verkauf die anderen, halte Wochen.

Drei Dinge aendern sich damit grundlegend, und alle drei betreffen
genau die Stellen, an denen dieses Projekt bisher gescheitert ist:

**1. Die Kosten hoeren auf zu dominieren.** Bei 2 Tagen Haltedauer muss
eine Konfiguration 0,3 % je Rundlauf verdienen, nur um die Spanne zu
bezahlen (30 bps, §G54/Gate §6.3) - bei rund 130 Rundlaeufen im Jahr ist
das eine Kostenlast von ueber 30 % jaehrlich. Bei monatlichem Umschlag
sind es 12 Rundlaeufe und unter 4 %.

**2. Der steigende Markt kann das Ergebnis nicht mehr erzeugen.** Long
und Short in gleicher Groesse heisst: Der Marktanstieg hebt beide Seiten
und faellt heraus. §G73 hat gezeigt, wie noetig das ist - dort waren
fuenf von sechs Jahren steigende Jahre, und §J.4 verlangt ohnehin jede
Kennzahl gegen eine Benchmark. Marktneutral IST die Benchmark, eingebaut.

**3. Der Survivorship-Rueckenwind kuerzt sich weitgehend heraus.** Das
war der Genickbruch von §G53 (22,8 % CAGR, davon fast alles
Verzerrung): Ein Universum aus heute liquiden Werten enthaelt die
Gewinner per Konstruktion. Aber es enthaelt sie in BEIDEN Beinen. Der
Aufwaertsdrift fehlender Pleiten hebt die Long-Seite und die
Short-Seite; im Abstand bleibt nur zweiter Ordnung uebrig.

**Was das NICHT heilt.** Die Verzerrung verschwindet nicht ganz: Wer
heute gelistet ist, hat ueberlebt, und die Rangfolge innerhalb der
Ueberlebenden ist nicht verzerrungsfrei. Jede Zahl hier bleibt eine
Obergrenze (§4.3). Marktneutral macht sie nur erheblich kleiner.

---

## Wie hier gemessen wird - und warum NICHT gesucht

Die Ausbruch-Werkstatt hat 470.000 Konfigurationen durchprobiert und
daraus gelernt, dass eine Suche dieser Groesse zuverlaessig Illusionen
erzeugt (§B2, §G64, §G76). Dieses Modul macht das ausdruecklich anders:

    Eine kleine Zahl VORAB benannter Varianten, jede EINMAL gerechnet.

Kein Bergsteigen, keine Elite, kein Zufallsmaximum von
`sqrt(2 ln 470000)`. Wer hier eine Achse verstellt, zaehlt einen Versuch.

## Die Einheit der Beobachtung

Nicht der einzelne Trade, sondern die **Rebalance-Periode**. Bei
monatlichem Umschlag ueber sechs Jahre sind das rund 72 Beobachtungen -
und die sind, anders als 183 ueberlappende Trades (§G73),
naeherungsweise unabhaengig, weil sich die Halteperioden nicht
ueberschneiden. Genau deshalb ist `horizont=1` im gruppierten Test hier
korrekt und nicht geschummelt.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

__all__ = ["QuerschnittConfig", "SIGNALE", "Ergebnis", "tageskurse",
           "signal_werte", "lauf"]


# =====================================================================
#  Konfiguration
# =====================================================================

@dataclass
class QuerschnittConfig:
    """Alle Hebel. Vorgaben sind plausible Startwerte, keine optimierten."""

    signal: str = "momentum"
    """Welche Kennzahl die Rangfolge bildet - siehe `SIGNALE`."""

    rueckblick_tage: int = 60
    """Ueber wie viele Handelstage das Signal rechnet."""

    luecke_tage: int = 5
    """Wie viele der JUENGSTEN Tage das Signal auslaesst.

    Bei Momentum der klassische "skip month": Die letzten Tage tragen
    kurzfristige Umkehr und verwaessern das Signal. Zugleich ein
    Sicherheitsabstand gegen jede Art von Randeffekt."""

    halten_tage: int = 21
    """Haltedauer je Periode in Handelstagen (21 = rund ein Monat).

    Der wichtigste Hebel ueberhaupt: Er entscheidet, ob die Spanne das
    Ergebnis frisst. Siehe `kostenlast_pct_jahr()`."""

    versatz_tage: int = 0
    """Abstand zwischen zwei Rebalance-Stichtagen. 0 = `halten_tage`.

    **Warum das die Zahl der Beobachtungen verdreifacht, ohne zu
    schummeln.** Bei `halten_tage=63` und `versatz_tage=63` gibt es in
    sechs Jahren nur 20 Perioden - zu wenig fuer eine Streuungsschaetzung
    (§J.1), und der t-Wert bleibt zwangslaeufig klein. Mit
    `versatz_tage=21` starten drei TRANCHEN im Monatsabstand, jede haelt
    63 Tage. Man haelt dann drei Teildepots zu je einem Drittel.

    Der Umschlag je Kapitaleinheit bleibt derselbe: Jede Tranche wird
    weiterhin nur alle 63 Tage umgeschichtet. Die Kosten aendern sich
    also nicht - nur die Zahl der Beobachtungen steigt.

    **Was dafuer korrigiert werden MUSS.** Die Halteperioden benachbarter
    Tranchen ueberlappen. Ohne Korrektur liegt die Fehlalarmquote nicht
    bei 5 %, sondern bei 39,5 % (§G12). `_kennzahlen` uebergibt deshalb
    `horizont = halten_tage / versatz_tage` an den gruppierten Test, und
    massgeblich ist dann `t_ueberlappung`. Das ist keine Feinheit: Ohne
    diese Zeile waere die dreifache Beobachtungszahl ein dreifach
    ueberschaetzter t-Wert."""

    def schrittweite(self) -> int:
        """Abstand zweier Stichtage - `versatz_tage`, sonst `halten_tage`."""
        return max(int(self.versatz_tage or self.halten_tage), 1)

    def horizont_perioden(self) -> int:
        """Wie viele Stichtage ein Halteperioden-Fenster ueberdeckt.

        1 = keine Ueberlappung. Genau dieser Wert gehoert als `horizont`
        in den gruppierten Test (§G12).
        """
        return max(1, int(round(self.halten_tage / self.schrittweite())))

    anteil_pct: float = 10.0
    """Wie viel Prozent des Universums je Seite gehalten werden."""

    min_symbole: int = 100
    """Weniger Werte in der Rangfolge - dann keine Periode."""

    gewichtung: str = "gleich"
    """Wie das Kapital innerhalb eines Korbs verteilt wird.

    * `"gleich"` - jeder Wert denselben Betrag.
    * `"inv_vola"` - umgekehrt proportional zur eigenen Schwankung.

    **Warum das den Sharpe hebt, ohne die Idee zu aendern.** Bei
    Gleichgewichtung bestimmen die paar schwankungsstaerksten Werte den
    groessten Teil der Depotschwankung - ein Wert mit 80 % Jahresvola
    traegt achtmal so viel Risiko bei wie einer mit 10 %, bei gleichem
    Einsatz. Die erwartete Rendite je Wert ist davon unberuehrt.
    Umgekehrte Vola-Gewichtung gleicht die Risikobeitraege an.

    Das ist Risikoverteilung, keine Signalsuche: Es wird keine Achse
    optimiert und keine zusaetzliche Information benutzt - nur dasselbe
    Signal anders umgesetzt. `t = Sharpe x Wurzel(Jahre)` (§G79) macht
    diesen Hebel doppelt so wirksam wie das Verdoppeln der Historie."""

    vola_quelle: str = "intraday"
    """Woraus die Vola fuer `gewichtung="inv_vola"` geschaetzt wird.

    * `"intraday"` - realisierte Vola aus den 15-Minuten-Bars.
    * `"tagesschluss"` - Standardabweichung der Tagesrenditen.

    **Als Schalter gebaut, weil eine Verbesserung, die man nicht
    abschalten kann, auch nicht gemessen werden kann.** Der erste Versuch
    hatte den Intraday-Schaetzer fest verdrahtet - der Vergleich beider
    Verfahren lieferte dann zweimal dieselbe Zeile, und die vermeintliche
    Verbesserung blieb unbelegt."""

    marktneutral: bool = True
    """True = Long und Short in gleicher Groesse. False = nur Long.

    Nur-Long ist als Vergleich da, nicht als Vorschlag: Dort steckt der
    Marktanstieg und der Survivorship-Rueckenwind vollstaendig drin."""

    min_preis: float = 5.0
    min_dollar_volumen: float = 1_000_000.0
    """Liquiditaetsuntergrenzen. Nicht verhandelbar nach §G60: Ohne sie
    waehlt jede Auswertung Werte, fuer die die Kostenannahme nicht
    gemessen ist."""

    spanne_bps: float = 12.2
    """Geld-Brief-Spanne (§G54). Fuers Gate mit 30 zu rechnen."""

    slippage_bps: float = 3.0

    leihe_bps_jahr: float = 50.0
    """Leihkosten der Short-Seite, in bps pro JAHR.

    **Warum das hier stehen muss.** Eine Short-Position kostet Leihe,
    jeden Tag, den sie offen ist - anders als die Long-Seite. Die erste
    Fassung dieses Moduls hat sie weggelassen und im Hinweistext darauf
    verwiesen. Ein Vorbehalt im Fliesstext ersetzt keine Zeile im
    Kostenmodell: Er wird beim Lesen der Tabelle nicht mitgerechnet.

    50 bps im Jahr ist der Ansatz fuer gut leihbare, liquide Werte. Fuer
    schwer leihbare sind 300 bps und mehr normal - und genau die stehen
    typischerweise auf der Short-Seite einer Momentum-Strategie, weil
    sie gefallen sind. Deshalb gehoert eine Gegenrechnung mit 300 dazu,
    so wie 30 bps Spanne neben 12,2 gehoert (Gate §6.3).

    Die Liquiditaetsuntergrenzen halten die Auswahl im Bereich, fuer den
    50 bps plausibel sind - belegt ist die Zahl fuer dieses Universum
    nicht. Sie ist eine Annahme, kein Messwert."""

    def regulierung_bps(self, kurs: float = 50.0) -> float:
        """SEC- und FINRA-Gebuehren je Rundlauf und Seite, in bps.

        **Warum das trotz "kommissionsfrei" nicht null ist.** Alpaca nimmt
        keine Kommission auf US-Aktien - aber SEC Section 31 und die FINRA
        Trading Activity Fee fallen trotzdem an, beide **nur auf
        Verkaeufe**. Und beide Beine zahlen sie einmal je Rundlauf: die
        Long-Seite beim Ausstieg, die Short-Seite beim Eroeffnen.

        Die Saetze kommen aus `costs.FeeSchedule` - demselben geprueften
        Ort, den auch der Live-Bot benutzt. Eigene Zahlen hier waeren eine
        zweite Wahrheit, die beim naechsten SEC-Satzwechsel veraltet.

        Die FINRA-TAF haengt am STUECKPREIS, nicht am Gegenwert: Bei einem
        5-Dollar-Papier ist sie zehnmal so teuer wie bei einem
        50-Dollar-Papier. Deshalb der Kurs als Argument.
        """
        from .costs import DEFAULT_FEES as f
        sec = f.sec_fee_per_million / 1e6 * 1e4
        taf = f.finra_taf_per_share / max(float(kurs), 0.01) * 1e4
        return sec + taf

    def kosten_je_rundlauf_pct(self, kurs: float = 50.0) -> float:
        return (self.spanne_bps + 2.0 * self.slippage_bps
                + self.regulierung_bps(kurs)) / 100.0

    def leihe_je_periode_pct(self) -> float:
        """Leihkosten fuer eine Halteperiode, in Prozent.

        Zeitabhaengig, nicht handelsabhaengig: Wer laenger haelt, zahlt
        mehr. Das ist die Gegenkraft zu der Ueberlegung, die diese ganze
        Familie traegt - lange Haltedauer senkt die Spannenkosten, hebt
        aber die Leihkosten.
        """
        if not self.marktneutral:
            return 0.0
        return self.leihe_bps_jahr / 100.0 * (self.halten_tage / 252.0)

    def kostenlast_pct_jahr(self) -> float:
        """Was die Strategie jaehrlich allein an Kosten verdienen muss.

        Die Zahl, die die ganze Familie rechtfertigt: Bei 2 Tagen
        Haltedauer steht hier ueber 30 %, bei 21 Tagen unter 4 %.

        **Gerechnet wird gegen `halten_tage`, nicht gegen die
        Schrittweite.** Ueberlappende Tranchen schichten jede fuer sich
        nur alle `halten_tage` um, und jede haelt nur einen Bruchteil des
        Kapitals - der Umschlag je Kapitaleinheit bleibt derselbe. Wer
        hier die Schrittweite einsetzte, wuerde die Kosten bei drei
        Tranchen verdreifachen, obwohl sich nichts am Handel aendert.
        """
        perioden = 252.0 / max(self.halten_tage, 1)
        seiten = 2.0 if self.marktneutral else 1.0
        handel = perioden * self.kosten_je_rundlauf_pct() * seiten
        # Leihe ist zeitabhaengig: ueber ein Jahr immer der volle Satz,
        # unabhaengig von der Haltedauer.
        leihe = self.leihe_bps_jahr / 100.0 if self.marktneutral else 0.0
        return handel + leihe


# =====================================================================
#  Signale - jedes eine reine Funktion auf Tageskursen
# =====================================================================
#
#  Vertrag fuer JEDE Signalfunktion:
#    Eingabe: DataFrame (Index = Handelstage, Spalten = Symbole) mit
#             Kursen BIS EINSCHLIESSLICH des Stichtags - nie darueber.
#    Ausgabe: Series je Symbol. Hoeher = attraktiver fuer die Long-Seite.
#
#  Die Funktionen sehen deshalb konstruktiv keine Zukunft: Der Aufrufer
#  schneidet vorher ab. `pit.audit_feature_function` prueft das
#  mechanisch nach - siehe tests/test_querschnitt.py.

def _rendite(kurse: pd.DataFrame, von: int, bis: int) -> pd.Series:
    """Rendite zwischen zwei Rueckblick-Abstaenden, in Prozent.

    `von` und `bis` zaehlen von hinten: `_rendite(k, 60, 5)` ist die
    Rendite von "vor 60 Tagen" bis "vor 5 Tagen".
    """
    if len(kurse) <= von:
        return pd.Series(dtype="float64")
    start = kurse.iloc[-von - 1]
    ende = kurse.iloc[-bis - 1] if bis > 0 else kurse.iloc[-1]
    return (ende / start - 1.0) * 100.0


def _momentum(kurse: pd.DataFrame, cfg: QuerschnittConfig) -> pd.Series:
    """Wer ist gestiegen, steigt weiter - die klassische Querschnittsidee."""
    return _rendite(kurse, cfg.rueckblick_tage, cfg.luecke_tage)


def _umkehr(kurse: pd.DataFrame, cfg: QuerschnittConfig) -> pd.Series:
    """Das Gegenteil: Wer gefallen ist, holt auf.

    Bewusst als eigene Variante und nicht als Vorzeichen-Schalter: So
    steht sie im Versuchsprotokoll als eigener Versuch.
    """
    return -_rendite(kurse, cfg.rueckblick_tage, cfg.luecke_tage)


def _tief_vola(kurse: pd.DataFrame, cfg: QuerschnittConfig) -> pd.Series:
    """Ruhige Werte zuerst. Die am besten belegte Anomalie ueberhaupt."""
    r = kurse.pct_change().iloc[-cfg.rueckblick_tage:]
    if len(r) < 5:
        return pd.Series(dtype="float64")
    return -r.std() * 100.0


def _momentum_je_vola(kurse: pd.DataFrame,
                      cfg: QuerschnittConfig) -> pd.Series:
    """Momentum, geteilt durch die eigene Schwankung.

    Ein Anstieg von 30 % bei 20 % Schwankung ist ein anderer Befund als
    derselbe Anstieg bei 80 %.
    """
    mom = _rendite(kurse, cfg.rueckblick_tage, cfg.luecke_tage)
    r = kurse.pct_change().iloc[-cfg.rueckblick_tage:]
    if len(r) < 5 or mom.empty:
        return pd.Series(dtype="float64")
    vola = r.std() * 100.0
    return mom / vola.where(vola > 0.05)


SIGNALE: dict = {
    "momentum": _momentum,
    "umkehr": _umkehr,
    "tief_vola": _tief_vola,
    "momentum_je_vola": _momentum_je_vola,
}


# =====================================================================
#  Ergebnis
# =====================================================================

@dataclass
class Ergebnis:
    config: QuerschnittConfig
    perioden: pd.DataFrame
    """Eine Zeile je Rebalance: Renditen der Long-, Short- und
    Gesamtseite, nach Kosten."""
    kennzahlen: dict = field(default_factory=dict)
    hinweise: list[str] = field(default_factory=list)


# =====================================================================
#  Tageskurse aus Intraday-Bars
# =====================================================================

def tageskurse(kd, *, ffill_tage: int = 5) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Schlusskurse und Dollar-Umsaetze je Handelstag.

    Aus 15-Minuten-Bars wird der SCHLUSS des letzten Bars eines Tages.
    `Kursdaten` fuehrt dafuer schon `letzter_des_tages` mit - dieselbe
    Definition, die auch der Ausbruch-Lauf benutzt, damit beide Familien
    denselben Tagesbegriff haben.

    **Warum vorwaerts gefuellt wird (Fehler vom 12.09.2026).** Handelt
    ein Wert im LETZTEN Bar eines Tages nicht, ist dieser eine Bar NaN -
    und damit waere der ganze Tagesschlusskurs NaN, obwohl der Wert den
    Tag ueber gehandelt hat. Gemessen: **15 % aller Tagesschlusskurse**
    betroffen, und nur **1 von 2.004** Symbolen hatte gar kein NaN. Ein
    Signal, das `dropna()` benutzt, waehlt dann nicht die liquidesten
    Werte, sondern die, die zufaellig in der letzten Viertelstunde
    dreier bestimmter Tage gehandelt haben. Das ist keine Auswahl,
    sondern Rauschen im Universum.

    `ffill_tage` begrenzt das Fuellen bewusst: Ein Wert, der eine Woche
    lang gar nicht handelt, soll herausfallen und nicht mit einem alten
    Kurs als lebendig gelten.

    Gibt (kurse, dollar_volumen) zurueck, beide Index = Handelstage,
    Spalten = Symbole. Das Volumen wird NICHT gefuellt: kein Handel
    heisst kein Umsatz, und genau das soll der Liquiditaetsfilter sehen.
    """
    letzte = np.flatnonzero(np.asarray(kd.letzter_des_tages))
    if len(letzte) < 2:
        raise ValueError("Zu wenige Handelstage in den Kursdaten.")
    tage = pd.DatetimeIndex([kd.achse[i] for i in letzte]).normalize()

    schluss: dict[str, np.ndarray] = {}
    umsatz: dict[str, np.ndarray] = {}
    # Tagesumsatz = Summe der Bar-Umsaetze. Dafuer werden die Grenzen der
    # Tage gebraucht, nicht nur ihr letzter Bar.
    grenzen = np.concatenate([[0], letzte + 1])
    for sym, (o, h, l, c, v) in kd.arrays.items():
        c = np.asarray(c, dtype="float64")
        v = np.asarray(v, dtype="float64")
        schluss[sym] = c[letzte]
        tv = np.add.reduceat(np.nan_to_num(v * c), grenzen[:-1])
        umsatz[sym] = tv
    k = pd.DataFrame(schluss, index=tage).ffill(limit=ffill_tage)
    return k, pd.DataFrame(umsatz, index=tage)


def tagesvola(kd) -> pd.DataFrame:
    """Realisierte Volatilitaet je Handelstag, aus den Intraday-Bars.

    **Warum das besser ist als Vola aus Tagesschlusskursen - und warum
    ausgerechnet dieses Projekt es kann.** Die Schwankung eines Wertes
    aus Tagesschlusskursen zu schaetzen benutzt EINE Beobachtung je Tag.
    Aus 26 Viertelstundenbars werden es 25 Renditen je Tag. Die
    "realisierte Volatilitaet" - die Wurzel aus der Summe der
    quadrierten Intraday-Renditen - ist derselbe Schaetzer fuer dieselbe
    Groesse, nur mit einem Bruchteil des Schaetzfehlers.

    Das ist der einzige Punkt, an dem der 15-Minuten-Vorrat dieser
    Werkstatt einer Tagesdaten-Auswertung ueberlegen ist: nicht beim
    Signal (63 Tage Haltedauer braucht keine Viertelstunden), sondern
    bei der Risikoschaetzung.

    **Die Overnight-Luecke fehlt bewusst.** Gerechnet wird nur innerhalb
    des Handelstages; der Sprung vom Schluss zum naechsten Eroeffnungs-
    kurs bleibt aussen vor. Er waere ein eigener, andersartiger Beitrag
    (Nachrichten ueber Nacht) und wuerde die Schaetzung je nach Symbol
    unterschiedlich verzerren. Fuer eine RELATIVE Gewichtung - wer ist
    unruhiger als wer - ist der Intraday-Teil der stabilere Massstab.

    Gibt einen DataFrame (Index = Handelstage, Spalten = Symbole) mit
    der taeglichen realisierten Vola in Prozent zurueck.
    """
    letzte = np.flatnonzero(np.asarray(kd.letzter_des_tages))
    if len(letzte) < 2:
        raise ValueError("Zu wenige Handelstage in den Kursdaten.")
    tage = pd.DatetimeIndex([kd.achse[i] for i in letzte]).normalize()
    grenzen = np.concatenate([[0], letzte + 1])
    bar_im_tag = np.asarray(kd.bar_im_tag)

    aus: dict[str, np.ndarray] = {}
    for sym, (_o, _h, _l, c, _v) in kd.arrays.items():
        c = np.asarray(c, dtype="float64")
        with np.errstate(divide="ignore", invalid="ignore"):
            r = np.diff(np.log(c), prepend=np.nan)
        # Der erste Bar eines Tages enthaelt den Uebernachtsprung - raus.
        r[bar_im_tag == 0] = np.nan
        rr = np.nan_to_num(r * r)
        tagesvarianz = np.add.reduceat(rr, grenzen[:-1])
        aus[sym] = np.sqrt(tagesvarianz) * 100.0
    return pd.DataFrame(aus, index=tage)


def gewichte(kurse_bis: pd.DataFrame, symbole, cfg: QuerschnittConfig,
             *, vola_fenster: int = 60,
             vola_bis: pd.DataFrame | None = None) -> pd.Series:
    """Gewichte innerhalb eines Korbs, Summe 1.

    Wie das Signal sieht auch die Vola-Schaetzung ausschliesslich Kurse
    BIS zum Stichtag - `kurse_bis` ist bereits beschnitten.

    Faellt die Schaetzung aus (zu wenig Historie, Vola null), wird auf
    Gleichgewichtung zurueckgefallen. Ein stiller Ausfall waere hier
    besonders heikel: Er saehe aus wie Vola-Gewichtung und waere keine.
    """
    symbole = list(symbole)
    if not symbole:
        return pd.Series(dtype="float64")
    gleich = pd.Series(1.0 / len(symbole), index=symbole)
    if cfg.gewichtung != "inv_vola":
        return gleich

    if vola_bis is not None:
        # Realisierte Vola aus den Intraday-Bars - derselbe Schaetzer fuer
        # dieselbe Groesse, nur mit einem Bruchteil des Schaetzfehlers.
        teil = vola_bis.reindex(columns=symbole).iloc[-vola_fenster:]
        if len(teil) < 10:
            return gleich
        vola = teil.mean()
    else:
        r = kurse_bis[symbole].pct_change().iloc[-vola_fenster:]
        if len(r) < 10:
            return gleich
        vola = r.std()
    # Sehr kleine Vola wuerde ein einzelnes Papier das Depot dominieren
    # lassen - nach unten begrenzen, sonst ist es keine Verteilung mehr,
    # sondern eine Wette auf den ruhigsten Wert.
    untergrenze = float(vola.median()) * 0.25 if np.isfinite(
        vola.median()) else 0.0
    vola = vola.where(vola > untergrenze, untergrenze)
    g = (1.0 / vola).replace([np.inf, -np.inf], np.nan)
    if not np.isfinite(g.sum()) or g.sum() <= 0:
        return gleich
    g = g.fillna(0.0)
    return g / g.sum()


def signal_werte(kurse_bis: pd.DataFrame,
                 cfg: QuerschnittConfig) -> pd.Series:
    """Signalwerte aus Kursen, die BEREITS am Stichtag enden.

    Eigene Funktion, damit `pit.audit_feature_function` sie einzeln
    pruefen kann.
    """
    fn = SIGNALE.get(cfg.signal)
    if fn is None:
        raise ValueError(f"Unbekanntes Signal {cfg.signal!r}. "
                         f"Bekannt: {sorted(SIGNALE)}")
    return fn(kurse_bis, cfg).replace([np.inf, -np.inf], np.nan).dropna()


# =====================================================================
#  Der Lauf
# =====================================================================

def lauf(kd, cfg: QuerschnittConfig) -> Ergebnis:
    """Faehrt die Querschnitt-Strategie ueber die Historie.

    **Der Ablauf je Rebalance-Stichtag t:**

    1. Signal aus Kursen **bis einschliesslich t** - nie darueber.
    2. Rangfolge, Long die besten `anteil_pct`, Short die schlechtesten.
    3. Gehalten wird von t bis t + `halten_tage`. Die Rendite dieser
       Periode wird aus den Schlusskursen von t und t + h gerechnet.
    4. Kosten: ein voller Rundlauf je Seite und Periode.

    **Warum der Einstieg auf dem Schluss von t liegt und nicht auf dem
    Open von t+1.** Der Schlusskurs von t ist der letzte Kurs, den das
    Signal selbst benutzt - ihn auch als Einstieg zu nehmen, waere die
    optimistische Variante. Sie ist hier bewusst gewaehlt und kostet
    Ehrlichkeit, deshalb steht sie in `hinweise` als Vorbehalt: Real
    wuerde zum naechsten Kurs gehandelt. Bei 21 Tagen Haltedauer aendert
    ein Bar Versatz wenig, bei 2 Tagen waere es entscheidend - wer
    `halten_tage` klein setzt, muss das wissen.
    """
    kurse, umsatz = tageskurse(kd)
    # Einmal fuer den ganzen Lauf - die realisierte Vola haengt nicht vom
    # Stichtag ab, nur ihr AUSSCHNITT tut das.
    vola = (tagesvola(kd)
            if cfg.gewichtung == "inv_vola" and cfg.vola_quelle == "intraday"
            else None)
    n_tage = len(kurse)
    h = max(int(cfg.halten_tage), 1)
    start = int(cfg.rueckblick_tage) + int(cfg.luecke_tage) + 1
    if n_tage < start + h + 1:
        raise ValueError(f"Zu wenige Handelstage ({n_tage}) fuer "
                         f"Rueckblick {cfg.rueckblick_tage} und "
                         f"Haltedauer {h}.")

    # Der zuletzt gehaltene Korb JE TRANCHE. Bei `versatz < halten`
    # laufen mehrere Tranchen versetzt nebeneinander; die naechste
    # Umschichtung derselben Tranche liegt `horizont_perioden()` Schritte
    # spaeter, nicht einen. Wer hier nur einen Korb merkt, vergleicht
    # Tranche A mit Tranche B und misst einen Umschlag, den es nicht gibt.
    letzter_korb: dict[int, tuple[set, set]] = {}
    n_tranchen = cfg.horizont_perioden()

    zeilen = []
    for schritt, i in enumerate(
            range(start, n_tage - h, cfg.schrittweite())):
        bis = kurse.index[i]
        # --- 1. Signal, streng auf Vergangenheit beschnitten ----------
        werte = signal_werte(kurse.iloc[:i + 1], cfg)
        if werte.empty:
            continue

        # --- 2. Handelbarkeit am Stichtag -----------------------------
        preis = kurse.iloc[i]
        vol = umsatz.iloc[i]
        erlaubt = werte.index[
            (preis.reindex(werte.index) >= cfg.min_preis)
            & (vol.reindex(werte.index) >= cfg.min_dollar_volumen)
        ]
        werte = werte.loc[erlaubt]
        if len(werte) < cfg.min_symbole:
            continue

        # --- 3. Rangfolge ---------------------------------------------
        k = max(int(len(werte) * cfg.anteil_pct / 100.0), 1)
        sortiert = werte.sort_values(ascending=False)
        long_seite = sortiert.index[:k]
        short_seite = sortiert.index[-k:] if cfg.marktneutral else []

        # --- 4. Rendite der Halteperiode ------------------------------
        p0 = kurse.iloc[i]
        p1 = kurse.iloc[i + h]
        r = ((p1 / p0 - 1.0) * 100.0).replace([np.inf, -np.inf], np.nan)

        # Gewichte aus denselben beschnittenen Kursen wie das Signal -
        # nie aus `r`, denn das ist die Zukunft der Halteperiode.
        bis_jetzt = kurse.iloc[:i + 1]
        vola_bis = vola.iloc[:i + 1] if vola is not None else None
        g_long = gewichte(bis_jetzt, long_seite, cfg, vola_bis=vola_bis)
        r_long = float((r.reindex(long_seite).fillna(0.0) * g_long).sum())
        if len(short_seite):
            g_short = gewichte(bis_jetzt, short_seite, cfg,
                               vola_bis=vola_bis)
            r_short = float(
                (r.reindex(short_seite).fillna(0.0) * g_short).sum())
        else:
            r_short = 0.0
        if not np.isfinite(r_long):
            continue
        if cfg.marktneutral and not np.isfinite(r_short):
            continue

        # Kosten: Long- und Short-Seite je ein voller Rundlauf, plus die
        # zeitabhaengige Leihe auf der Short-Seite. Die FINRA-Gebuehr
        # haengt am Stueckpreis - darum der Medianpreis DIESES Korbs,
        # nicht ein pauschaler Wert.
        korb_kurs = float(p0.reindex(
            list(long_seite) + list(short_seite)).median())
        if not np.isfinite(korb_kurs) or korb_kurs <= 0:
            korb_kurs = 50.0

        # --- Umschlag: nur das WIRKLICH Gehandelte kostet --------------
        # Ein Wert, der im Korb bleibt, wird nicht verkauft und nicht neu
        # gekauft. Die erste Fassung unterstellte 100 % Umschlag je
        # Periode - bei breiten Koerben und stabilen Signalen ist das
        # deutlich zu pessimistisch. Gezaehlt wird der Anteil NEUER
        # Positionen; jede neue Position zieht im Lauf ihres Lebens genau
        # einen Rundlauf nach sich.
        tranche = schritt % max(n_tranchen, 1)
        vorher = letzter_korb.get(tranche)
        neu_long, neu_short = set(long_seite), set(short_seite)
        if vorher is None:
            umschlag = 1.0          # erster Korb: alles wird aufgebaut
        else:
            alt_long, alt_short = vorher
            teile = []
            if neu_long:
                teile.append(len(neu_long - alt_long) / len(neu_long))
            if neu_short:
                teile.append(len(neu_short - alt_short) / len(neu_short))
            umschlag = float(np.mean(teile)) if teile else 1.0
        letzter_korb[tranche] = (neu_long, neu_short)

        kosten = (cfg.kosten_je_rundlauf_pct(korb_kurs)
                  * (2.0 if cfg.marktneutral else 1.0)
                  * umschlag
                  + cfg.leihe_je_periode_pct())
        brutto = r_long - r_short if cfg.marktneutral else r_long
        zeilen.append({
            "stichtag": bis,
            "ende": kurse.index[i + h],
            "r_long": r_long,
            "r_short": r_short,
            "brutto_pct": brutto,
            "netto_pct": brutto - kosten,
            "n_je_seite": int(k),
            "n_rangfolge": int(len(werte)),
            "umschlag": umschlag,
            "kosten_pct": kosten,
        })

    perioden = pd.DataFrame(zeilen)
    erg = Ergebnis(config=cfg, perioden=perioden)
    erg.kennzahlen = _kennzahlen(perioden, cfg)
    erg.hinweise = _hinweise(cfg, perioden)
    return erg


def _kennzahlen(p: pd.DataFrame, cfg: QuerschnittConfig) -> dict:
    """Die Zahlen, die ueber die Strategie entscheiden."""
    from . import statistik

    k: dict = {"n_perioden": int(len(p))}
    if p.empty:
        k.update(mittel_pct=0.0, t_wert=float("nan"), rendite_pct=0.0,
                 trefferquote_pct=0.0, max_drawdown_pct=0.0,
                 brutto_mittel_pct=0.0)
        return k

    netto = p["netto_pct"]
    if "umschlag" in p.columns:
        # Ohne diese Zahl ist die Kostenzeile nicht nachpruefbar: Sie sagt,
        # auf welchen Anteil des Korbs die Rundlaufkosten ueberhaupt
        # angefallen sind.
        k["umschlag_mittel"] = float(p["umschlag"].mean())
        k["kosten_mittel_pct"] = float(p["kosten_pct"].mean())
    k["mittel_pct"] = float(netto.mean())
    k["brutto_mittel_pct"] = float(p["brutto_pct"].mean())
    k["median_pct"] = float(netto.median())
    k["trefferquote_pct"] = float((netto > 0).mean() * 100.0)
    k["streuung_pct"] = float(netto.std())
    k["rendite_pct"] = float(((1.0 + netto / 100.0).prod() - 1.0) * 100.0)
    k["kostenlast_pct_jahr"] = cfg.kostenlast_pct_jahr()

    kurve = (1.0 + netto / 100.0).cumprod()
    k["max_drawdown_pct"] = float((kurve / kurve.cummax() - 1.0).min() * 100.0)

    # Sharpe gegen die Haltedauer annualisieren, NICHT gegen die
    # Schrittweite: Drei ueberlappende Tranchen sind nicht dreimal so
    # viel Risiko, sondern dasselbe Depot dreimal versetzt betrachtet.
    perioden_je_jahr = 252.0 / max(cfg.halten_tage, 1)
    if k["streuung_pct"] > 0:
        k["sharpe"] = float(k["mittel_pct"] / k["streuung_pct"]
                            * np.sqrt(perioden_je_jahr))
    else:
        k["sharpe"] = float("nan")

    # Ueberlappen die Halteperioden (versatz < halten), ragt jedes Fenster
    # in die folgenden hinein. Ohne Korrektur liegt die Fehlalarmquote bei
    # 39,5 % statt 5 (§G12) - massgeblich ist dann `t_ueberlappung`.
    horizont = cfg.horizont_perioden()
    k["horizont_perioden"] = horizont
    try:
        res = statistik.gruppierter_test(
            netto, pd.Series(range(len(netto))), horizont=horizont,
            min_gruppen=20)
        tu = getattr(res, "t_ueberlappung", float("nan"))
        roh = float(tu) if tu == tu else float(getattr(res, "t", 0.0))
        k["t_wert"] = roh if abs(roh) < 50.0 else float("nan")
        k["n_handelstage"] = int(getattr(res, "n_gruppen", 0))
        k["belastbar"] = bool(getattr(res, "belastbar", False))
    except Exception as e:  # noqa: BLE001 - ein Test darf den Lauf nie kippen
        k["t_wert"] = float("nan")
        k["t_hinweis"] = f"{type(e).__name__}: {e}"
    return k


def _hinweise(cfg: QuerschnittConfig, p: pd.DataFrame) -> list[str]:
    """Was neben dem Ergebnis stehen muss, damit es nicht falsch gelesen wird."""
    halb = cfg.spanne_bps / 2.0 + cfg.slippage_bps
    H = [
        f"EINKAUF UEBER, VERKAUF UNTER DEM KURS: Gekauft wird zum "
        f"Briefkurs plus Slippage ({halb:.1f} bps ueber der Mitte), "
        f"verkauft zum Geldkurs minus Slippage ({halb:.1f} bps darunter). "
        f"Ein Rundlauf kostet damit die volle Spanne plus zweimal "
        f"Slippage = {cfg.spanne_bps + 2 * cfg.slippage_bps:.1f} bps, "
        f"dazu {cfg.regulierung_bps():.2f} bps SEC/FINRA beim Verkauf. "
        f"Der angezeigte Kurs wird NIE gehandelt.",
        f"KOSTEN: {cfg.kosten_je_rundlauf_pct():.3f} % je Rundlauf und Seite "
        f"bei {cfg.spanne_bps:g} bps Spanne, also "
        f"{cfg.kostenlast_pct_jahr():.1f} % Kostenlast im Jahr. Zum "
        f"Vergleich: bei 2 Tagen Haltedauer waeren es "
        f"{252.0 / 2 * cfg.kosten_je_rundlauf_pct() * (2 if cfg.marktneutral else 1):.0f} %.",
        "NICHT MODELLIERT: Marktwirkung der eigenen Order. Bei rund 30 bis "
        "60 Positionen je Seite und den Liquiditaetsuntergrenzen ist sie "
        "klein, aber sie ist nicht null - und sie waechst mit der "
        "Depotgroesse.",
        "EINSTIEG AUF DEM SCHLUSS des Stichtags - derselbe Kurs, den das "
        "Signal zuletzt sieht. Real wuerde einen Kurs spaeter gehandelt; "
        "bei langer Haltedauer ist der Unterschied klein, bei kurzer nicht.",
    ]
    if cfg.marktneutral:
        H.append(
            "MARKTNEUTRAL: Long und Short in gleicher Groesse. Der "
            "Marktanstieg kann dieses Ergebnis nicht erzeugen (§J.4), und "
            "der Survivorship-Rueckenwind kuerzt sich weitgehend heraus - "
            "aber nicht vollstaendig (§4.3, §G53)."
        )
    else:
        H.append(
            "NUR LONG: Marktanstieg UND Survivorship stecken vollstaendig "
            "im Ergebnis. Nur als Vergleichsgroesse lesbar, nie als Befund "
            "(§G53: 22,8 % CAGR, fast alles Verzerrung)."
        )
    if cfg.marktneutral:
        H.append(
            f"LEIHE: {cfg.leihe_bps_jahr:g} bps im Jahr auf die Short-Seite, "
            f"also {cfg.leihe_je_periode_pct():.3f} % je Halteperiode. Das ist "
            f"eine ANNAHME fuer gut leihbare Werte, kein Messwert fuer dieses "
            f"Universum. Bei schwer leihbaren Werten sind 300 bps normal - und "
            f"genau die stehen oft auf der Short-Seite einer "
            f"Momentum-Strategie, weil sie gefallen sind. Gegenrechnung mit "
            f"300 gehoert dazu."
        )
        H.append(
            "VERFUEGBARKEIT: Ob ein Wert zum Stichtag ueberhaupt leihbar war, "
            "ist NICHT modelliert - dafuer liegen keine historischen Daten "
            "vor. Die Liquiditaetsuntergrenzen halten die Auswahl im "
            "plausiblen Bereich, mehr nicht."
        )
    if not p.empty and len(p) < 20:
        H.append(
            f"KEIN BEFUND MOEGLICH: nur {len(p)} Perioden. Unter 20 traegt "
            f"die Streuungsschaetzung nicht (§J.1)."
        )
    return H
