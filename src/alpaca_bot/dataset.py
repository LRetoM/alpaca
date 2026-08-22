"""ML-Trainingsdaten aus der Kurshistorie - das Panel, nicht die Trades.

**Warum das Panel und nicht die 3.625 Trades aus `results/simulation`.**
Ein Datensatz aus gehandelten Trades ist auf die Auswahl des bestehenden
Scores bedingt: Er enthaelt nur Situationen, die `min_score` bereits
passiert haben. Ein Modell darauf lernt "welcher der ausgewaehlten Trades
lief gut" - nicht "welche Situation ist gut". Die Frage, wegen der dieses
Modul existiert, ist aber die zweite:

    Sortiert ein gelerntes Modell die Kandidaten besser als der
    handgebaute Score?

Dafuer werden ALLE Symbole an ALLEN Tagen gebraucht, auch die nie
gekauften - genau das, was `shadow.py` vorwaerts tut (dort: 19 Handels-
tage) und was hier rueckwaerts ueber ~1.500 Handelstage gebaut wird.

**Die drei Regeln, die hier technisch erzwungen sind.** Alle drei stammen
aus Fehlern, die dieses Projekt bereits bezahlt hat:

1. **Der Handelstag ist die Beobachtung, nicht die Zeile.** Ein Panel aus
   1.200 Symbolen x 1.500 Tagen hat 1,8 Mio. Zeilen und ~1.500
   unabhaengige Beobachtungen (BEFUNDE §B1). Jede Rueckgabe dieses Moduls
   fuehrt `tage` mit; keine Kennzahl wird ohne sie berechnet.

2. **Das Label ist ein Ueberschuss, keine Rohrendite.** BEFUNDE §J Regel 4
   und der konkrete Fall aus §G11: Der Nachlauf nach dem Zeitausstieg sah
   roh mit +0,43 % nach einer verpassten Chance aus, marktbereinigt blieb
   -0,05 %. Wer roh misst, misst den Markt. Bezugsgroesse ist deshalb der
   **Median des Universums am selben Tag** - dieselbe Referenz, die
   `shadow_eval` verwendet.

3. **Der Walk-Forward schneidet nach Datum, nicht nach Zeilenposition.**
   `ml.walk_forward_predict` ist fuer die Zeitreihe EINES Symbols gebaut
   und schneidet mit `.iloc`. Auf ein Panel angewandt landen Zeilen
   desselben Handelstages in Trainings- UND Testfenster - ein Leck genau
   der Art, gegen die `pit.py` existiert, nur eine Ebene hoeher. Deshalb
   `walk_forward_panel()` mit Schnitten auf der Tagesachse und einem
   Embargo in Handelstagen.

**Was dieses Modul ausdruecklich NICHT tut:** Es aendert keine
Handelsregel und meldet keinen Bot an. Ein Ergebnis hier ist ein Filter
(BETRIEBSPLAN §4) - es darf eine Idee verwerfen, nie abnehmen. Der Weg in
die Handelslogik fuehrt weiter ueber eine Voranmeldung in der Flotte.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import features as feat
from . import statistik

MIN_HISTORIE = 250
"""Bars, die ein Symbol braucht, bevor es ins Panel darf.

`features.build_features` enthaelt `dist_sma_200`. Ein Symbol mit 120
Bars liefert dort ausschliesslich NaN und faellt spaeter beim `dropna`
ohnehin heraus - aber erst, nachdem es Rechenzeit gekostet hat.
"""

MIN_SYMBOLE_JE_TAG = 20
"""Unter dieser Zahl ist der Tagesmedian als Referenz nicht belastbar.

Der Median ueber 5 Symbole ist selbst fast nur Rauschen; ein Ueberschuss
gegen ihn misst dann die Zufaelligkeit der Referenz mit. Betrifft in der
Praxis nur die Raender der Historie, wo wenige Symbole Daten haben.
"""


def _markt_angleichen(market: pd.Series, bars_index: pd.MultiIndex) -> pd.Series:
    """Marktreihe auf die exakten Zeitstempel der Bars abbilden - ueber das Datum.

    Gejoint wird auf dem Kalendertag, zurueckgegeben wird auf den
    Original-Zeitstempeln der Bars. Damit trifft jedes spaetere
    `market.reindex(df.index)` in `features.py` und `signals.py`, egal wie
    die uebergebene Reihe zeitlich aufbereitet war.
    """
    ziel = pd.DatetimeIndex(
        bars_index.get_level_values("timestamp").unique()).sort_values()

    def _tage(idx: pd.DatetimeIndex) -> pd.DatetimeIndex:
        return (idx.tz_localize(None) if idx.tz is not None else idx).normalize()

    quelle = pd.Series(np.asarray(market, dtype=float),
                       index=_tage(pd.DatetimeIndex(market.index)))
    quelle = quelle[~quelle.index.duplicated(keep="last")].sort_index()

    # `ffill` deckt Feiertage ab, an denen ein Symbol handelt und der
    # Index nicht - nie `bfill`, das waere ein Blick nach vorn (pit.py).
    werte = quelle.reindex(_tage(ziel)).ffill()
    return pd.Series(werte.to_numpy(), index=ziel, name="market")


# ---------------------------------------------------------------------------
# Das Panel
# ---------------------------------------------------------------------------

@dataclass
class Panel:
    """Fertige Trainingsdaten samt der Spalten, die sie interpretierbar machen.

    `X`, `y`, `tage` und `symbole` sind gleich lang und teilen denselben
    Index. Sie werden bewusst NICHT zu einem DataFrame verschmolzen: Ein
    einziger `df[features]`-Zugriff, der versehentlich `tag` mitnimmt,
    waere ein Datenleck (das Modell lernt das Datum) und faellt in der
    Auswertung nicht auf.
    """

    X: pd.DataFrame
    y: pd.Series
    tage: pd.Series
    symbole: pd.Series
    roh_rendite: pd.Series
    """Die unbereinigte Vorwaertsrendite - nur zur Kontrolle, nie als Ziel."""
    horizont: int
    label_art: str
    referenz: str
    n_symbole: int = 0
    warnungen: list[str] = field(default_factory=list)

    @property
    def n_tage(self) -> int:
        """Die Zahl, die zaehlt (§B1) - nicht `len(self.X)`."""
        return int(self.tage.nunique())

    def bericht(self) -> str:
        z = [
            "-" * 74,
            "  PANEL",
            "-" * 74,
            f"  Zeilen           : {len(self.X):,}".replace(",", "."),
            f"  Handelstage      : {self.n_tage:,}".replace(",", ".")
            + "   <- die Zahl, die zaehlt (§B1)",
            f"  Symbole          : {self.n_symbole:,}".replace(",", "."),
            f"  Merkmale         : {self.X.shape[1]}",
            f"  Label            : {self.label_art}, Horizont {self.horizont} Tage",
            f"  Referenz         : {self.referenz}",
            f"  Zeitraum         : {self.tage.min()} bis {self.tage.max()}",
        ]
        if self.label_art == "binaer":
            z.append(f"  Basisrate        : {self.y.mean():.3f}"
                     "   (0,5 = ausgewogen, per Konstruktion)")
        for w in self.warnungen:
            z.append(f"  ! {w}")
        z.append("-" * 74)
        return "\n".join(z)


def baue_panel(
    bars: pd.DataFrame,
    *,
    horizont: int = 5,
    market: pd.Series | None = None,
    label_art: str = "binaer",
    min_historie: int = MIN_HISTORIE,
    verbose: bool = True,
) -> Panel:
    """OHLCV vieler Symbole -> (X, y, tage) fuer das Lernen.

    Args:
        bars: MultiIndex (symbol, timestamp) wie von `data.get_bars` /
            `universe.fetch_history`.
        horizont: Renditefenster in Handelstagen. 5 ist der Wert, auf dem
            der Effekt dieses Projekts lebt (BEFUNDE §A) - und zugleich
            der, der die Ueberlappungskorrektur noetig macht (§G12).
        market: SPY-Schlusskurse. Fliesst als relative Staerke in die
            Merkmale ein (`features.build_features`). Fehlt er, entfaellt
            der Marktbezug der Merkmale - nicht die Label-Referenz, die
            haengt am Universumsmedian.
        label_art: 'binaer' (Ueberschuss > 0) oder 'ueberschuss' (die
            Zahl selbst, fuer Regression).

    Der Ablauf ist bewusst zweistufig: erst je Symbol die Merkmale und die
    rohe Vorwaertsrendite, dann EIN querschnittlicher Durchgang fuer die
    Referenz. Die Referenz kann nicht je Symbol entstehen - sie ist per
    Definition eine Aussage ueber den Tag.
    """
    if label_art not in ("binaer", "ueberschuss"):
        raise ValueError(
            f"label_art muss 'binaer' oder 'ueberschuss' sein, nicht {label_art!r}"
        )
    if horizont < 1:
        raise ValueError(f"horizont muss >= 1 sein, nicht {horizont}")

    symbole = list(bars.index.get_level_values("symbol").unique())
    if verbose:
        print(f"    Baue Panel aus {len(symbole):,} Symbolen ...".replace(",", "."))

    # --- Marktreihe auf die exakten Bar-Zeitstempel bringen --------------
    # Nicht bloss die Zeitzone: Alpaca-Tagesbars tragen 04:00 oder 05:00
    # UTC, eine von Hand geholte SPY-Reihe oft Mitternacht. `reindex` in
    # `features.build_features` trifft dann KEINEN einzigen Zeitpunkt und
    # liefert still ueberall NaN - die Marktmerkmale sind leer, das
    # abschliessende `dropna` verwirft das gesamte Panel, und nichts
    # stuerzt ab. Beobachtet am 22.08.2026 beim ersten Lauf dieses Moduls.
    #
    # `scripts/10_simulate.py` umgeht das, indem es SPY aus demselben
    # bars-Frame zieht (Zeile 241) - dann stimmen die Stempel per
    # Konstruktion. Hier wird der allgemeine Fall geloest, damit auch eine
    # extern geholte Reihe funktioniert.
    if market is not None:
        market = _markt_angleichen(market, bars.index)

    teile: list[pd.DataFrame] = []
    zu_kurz = 0

    for i, sym in enumerate(symbole):
        df = bars.xs(sym, level="symbol").sort_index()
        if len(df) < min_historie:
            zu_kurz += 1
            continue

        # `build_features` ist durch `pit.audit_feature_function` als kausal
        # nachgewiesen (selfcheck.py:291). Deshalb darf sie EINMAL auf der
        # vollen Historie laufen: build(voll).loc[:T] == build(bis_T).
        X = feat.build_features(df, market=market)

        # Die rohe Vorwaertsrendite. Sie ist noch nicht das Label - erst der
        # querschnittliche Durchgang unten macht daraus einen Ueberschuss.
        c = df["close"].astype(float)
        fwd = c.shift(-horizont) / c - 1

        teil = X.copy()
        teil["__fwd"] = fwd
        teil["__symbol"] = sym
        teil["__tag"] = df.index
        teile.append(teil)

        if verbose and (i + 1) % 200 == 0:
            print(f"      {i + 1:,}/{len(symbole):,} Symbole".replace(",", "."))

    if not teile:
        raise ValueError(
            f"Kein Symbol hat {min_historie} Bars. Mehr Historie laden "
            f"oder min_historie senken."
        )

    panel = pd.concat(teile, ignore_index=True)
    del teile

    # --- Der querschnittliche Durchgang: Referenz je Handelstag -----------
    # Der Median, nicht das Mittel. Das Mittel eines Tages wird von wenigen
    # Ausreissern getragen - genau der Effekt, der in BEFUNDE §G11 die
    # Survivorship sichtbar machte (das Mittel schlug SPY in jedem Jahr,
    # der Median nie). Als Referenz ist der Median die konservative Wahl.
    panel = panel.dropna(subset=["__fwd"])
    je_tag = panel.groupby("__tag")["__fwd"]
    panel["__ref"] = je_tag.transform("median")
    panel["__n_tag"] = je_tag.transform("size")

    warnungen = []
    duenn = int((panel["__n_tag"] < MIN_SYMBOLE_JE_TAG).sum())
    if duenn:
        anteil = duenn / len(panel)
        warnungen.append(
            f"{duenn:,} Zeilen ({anteil:.1%}) an Tagen mit < "
            f"{MIN_SYMBOLE_JE_TAG} Symbolen verworfen - "
            f"Tagesmedian dort nicht belastbar".replace(",", ".")
        )
        panel = panel[panel["__n_tag"] >= MIN_SYMBOLE_JE_TAG]

    panel["__ueberschuss"] = panel["__fwd"] - panel["__ref"]

    # --- Label ------------------------------------------------------------
    if label_art == "binaer":
        y = (panel["__ueberschuss"] > 0).astype(int)
    else:
        y = panel["__ueberschuss"].astype(float)

    dienst = ["__fwd", "__symbol", "__tag", "__ref", "__n_tag", "__ueberschuss"]
    X = panel.drop(columns=dienst)

    # --- Waechter: welches Merkmal ist praktisch leer? -------------------
    # Ein einzelnes durchgehend leeres Merkmal loescht ueber `notna().all()`
    # das ganze Panel. Ohne diese Meldung sieht man nur "0 Zeilen" und
    # sucht an der falschen Stelle. Dieselbe Fehlerfamilie wie §G13:
    # ein Feld hoert auf, sich zu fuellen, und nichts stuerzt ab.
    leer = X.columns[X.notna().mean() < 0.5].tolist()
    if leer:
        warnungen.append(
            f"Merkmale ueberwiegend leer: {', '.join(leer[:6])}"
            + (f" (+{len(leer) - 6} weitere)" if len(leer) > 6 else "")
            + " - haeufigste Ursache: `market` passt zeitlich nicht zu `bars`")

    # Erst JETZT die NaN-Zeilen entfernen. Frueher waere falsch: `dropna`
    # vor dem zeitlichen Bezug ist eines der Lecks, die pit.py auflistet.
    gut = X.notna().all(axis=1)
    if gut.sum() == 0 and len(X):
        raise ValueError(
            "Panel ist nach dem Entfernen der NaN-Zeilen leer. "
            + (f"Ueberwiegend leere Merkmale: {', '.join(leer[:6])}. "
               if leer else "")
            + "Bei uebergebenem `market` ist die haeufigste Ursache eine "
              "nicht passende Zeitzone oder ein nicht ueberlappender Zeitraum."
        )
    X, y = X[gut], y[gut]
    tage = panel.loc[gut, "__tag"]
    syms = panel.loc[gut, "__symbol"]
    roh = panel.loc[gut, "__fwd"]

    # float32 halbiert den Speicher. Bei 1,8 Mio. Zeilen x 35 Merkmalen ist
    # das der Unterschied zwischen 500 MB und 250 MB - und die Merkmale
    # sind Renditen und Verhaeltnisse, keine Groessen, bei denen die
    # siebte Nachkommastelle etwas entscheidet.
    X = X.astype(np.float32)

    p = Panel(
        X=X.reset_index(drop=True),
        y=y.reset_index(drop=True),
        tage=tage.reset_index(drop=True),
        symbole=syms.reset_index(drop=True),
        roh_rendite=roh.reset_index(drop=True),
        horizont=horizont,
        label_art=label_art,
        referenz=f"Median aller Symbole desselben Handelstages (>= {MIN_SYMBOLE_JE_TAG})",
        n_symbole=int(syms.nunique()),
        warnungen=warnungen,
    )
    if zu_kurz:
        p.warnungen.append(f"{zu_kurz} Symbole mit < {min_historie} Bars uebersprungen")
    if verbose:
        print(p.bericht())
    return p


# ---------------------------------------------------------------------------
# Walk-Forward auf der Tagesachse
# ---------------------------------------------------------------------------

@dataclass
class PanelErgebnis:
    """Out-of-Sample-Vorhersagen eines Panel-Walk-Forward."""

    vorhersagen: pd.Series
    tatsaechlich: pd.Series
    """Der Ueberschuss - immer die Zahl, nie das binaere Label."""
    tage: pd.Series
    symbole: pd.Series
    falten: pd.DataFrame
    modell: object
    merkmale: list[str]
    horizont: int

    @property
    def n_tage(self) -> int:
        return int(self.tage.nunique())


def walk_forward_panel(
    panel: Panel,
    model_kind: str = "gbm",
    *,
    n_falten: int = 5,
    min_train_tage: int = 250,
    verbose: bool = True,
    **model_kwargs,
) -> PanelErgebnis:
    """Ehrliche Out-of-Sample-Vorhersagen ueber die ganze Historie.

    Der Unterschied zu `ml.walk_forward_predict` ist die Schnittachse:
    dort Zeilenposition, hier **Handelstag**. Auf einem Panel ist das kein
    Detail, sondern der Unterschied zwischen einer Messung und einem Leck -
    ein Positionsschnitt trennt mitten in einen Handelstag hinein und legt
    Zeilen desselben Tages in beide Fenster.

    Das Embargo betraegt `panel.horizont` Handelstage. Grund: Ein Label
    vom Tag T benutzt die Kurse bis T+h. Ohne Embargo enthaelt das
    Trainingsfenster genau die Kursbewegung, die im Testfenster
    vorhergesagt werden soll.
    """
    tage_sortiert = np.sort(panel.tage.unique())
    n_tage = len(tage_sortiert)
    embargo = panel.horizont

    noetig = min_train_tage + embargo + n_falten
    if n_tage < noetig:
        raise ValueError(
            f"Zu wenige Handelstage: {n_tage}, noetig sind {noetig} "
            f"(min_train_tage={min_train_tage} + Embargo={embargo} + "
            f"{n_falten} Falten). Mehr Historie laden oder n_falten senken."
        )

    test_gesamt = n_tage - min_train_tage
    breite = test_gesamt // n_falten

    vorhersagen = pd.Series(np.nan, index=panel.X.index, dtype=float)
    zeilen = []

    for i in range(n_falten):
        start = min_train_tage + i * breite
        ende = n_tage if i == n_falten - 1 else start + breite

        # Das Embargo wird vom TRAININGSENDE abgezogen, nicht vom
        # Teststart. Andernfalls blieben die embargierten Tage ganz
        # unbenutzt statt nur ungelernt.
        train_ende = start - embargo
        if train_ende < 50:
            continue

        train_tage = set(tage_sortiert[:train_ende])
        test_tage = set(tage_sortiert[start:ende])

        ist_train = panel.tage.isin(train_tage).to_numpy()
        ist_test = panel.tage.isin(test_tage).to_numpy()
        if not ist_test.any() or not ist_train.any():
            continue

        y_tr = panel.y[ist_train]
        if y_tr.nunique() < 2:
            continue

        from .ml import make_model

        m = make_model(model_kind, **model_kwargs)
        m.fit(panel.X[ist_train], y_tr)

        if hasattr(m, "predict_proba"):
            p = m.predict_proba(panel.X[ist_test])[:, 1]
        else:
            p = m.predict(panel.X[ist_test])
        vorhersagen[ist_test] = p

        zeilen.append({
            "falte": i + 1,
            "train_bis": str(tage_sortiert[train_ende - 1])[:10],
            "test_von": str(tage_sortiert[start])[:10],
            "test_bis": str(tage_sortiert[ende - 1])[:10],
            "n_train_tage": train_ende,
            "n_test_tage": len(test_tage),
            "n_train_zeilen": int(ist_train.sum()),
            "n_test_zeilen": int(ist_test.sum()),
        })
        if verbose:
            print(f"      Falte {i + 1}/{n_falten}: trainiert bis "
                  f"{zeilen[-1]['train_bis']}, testet "
                  f"{zeilen[-1]['test_von']}..{zeilen[-1]['test_bis']} "
                  f"({len(test_tage)} Tage)")

    if not zeilen:
        raise ValueError("Keine einzige Falte konnte gerechnet werden.")

    gueltig = vorhersagen.notna()

    # Das finale Modell auf allen Daten - fuer den spaeteren Einsatz, NICHT
    # fuer eine Kennzahl. Jede Zahl in `PanelErgebnis` stammt aus den
    # Falten oben.
    from .ml import make_model

    final = make_model(model_kind, **model_kwargs)
    final.fit(panel.X, panel.y)

    return PanelErgebnis(
        vorhersagen=vorhersagen[gueltig],
        tatsaechlich=(panel.y[gueltig].astype(float) if panel.label_art == "ueberschuss"
                      else (panel.roh_rendite[gueltig] - panel.roh_rendite[gueltig].groupby(
                          panel.tage[gueltig]).transform("median"))),
        tage=panel.tage[gueltig],
        symbole=panel.symbole[gueltig],
        falten=pd.DataFrame(zeilen),
        modell=final,
        merkmale=list(panel.X.columns),
        horizont=panel.horizont,
    )


# ---------------------------------------------------------------------------
# Bewertung - die einzige Stelle, an der eine Zahl entsteht
# ---------------------------------------------------------------------------
#
# Hier steht bewusst NICHT `accuracy` oder `auc`. Beide zaehlen Zeilen, und
# ein Panel hat 1,8 Mio. Zeilen bei ~1.500 unabhaengigen Beobachtungen. Eine
# AUC von 0,55 aus solchen Daten sieht wie ein Befund aus und ist keiner -
# das ist derselbe Fehler, der in BEFUNDE §G14 einen IC von +0,248 aus ZWEI
# Handelstagen erzeugt hat.
#
# Gemessen wird deshalb wie ueberall im Projekt: querschnittlich je Tag,
# dann ueber die Tage - mit der Ueberlappungskorrektur aus §G12.

@dataclass
class Guete:
    """Wie gut sortiert eine Rangfolge? Immer je Tag, immer korrigiert."""

    name: str
    n_tage: int
    ic: float
    """Mittlerer Spearman-Rangkorrelation je Handelstag."""
    t: float
    """Der korrigierte t-Wert. Bei Horizont > 1 nach Newey-West (§G12)."""
    t_roh: float
    """Unkorrigiert - steht zum Vergleich da, NICHT zum Zitieren."""
    aufblaehung: float
    spreizung: float
    """Oberstes minus unterstes Dezil, je Tag, in Prozentpunkten."""
    spreizung_t: float
    horizont: int
    schwelle: float
    """`fleet.schwelle_sigma()` zum Zeitpunkt der Messung."""

    @property
    def befund(self) -> bool:
        """Ein Befund ist es nur ueber der Schwelle - und nur mit gueltigem t."""
        return bool(np.isfinite(self.t) and abs(self.t) > self.schwelle)

    def zeile(self) -> str:
        t_txt = f"{self.t:>6.2f}" if np.isfinite(self.t) else "   -  "
        s_txt = f"{self.spreizung_t:>6.2f}" if np.isfinite(self.spreizung_t) else "   -  "
        urteil = "BEFUND" if self.befund else "kein Befund"
        return (f"  {self.name:<22} {self.ic:>8.4f} {t_txt} {self.t_roh:>7.2f} "
                f"{self.spreizung:>8.3f}% {s_txt}   {urteil}")


def _tages_ic(vorhersage: pd.Series, tatsaechlich: pd.Series,
              tage: pd.Series, min_je_tag: int = 5) -> pd.Series:
    """Spearman je Handelstag - die Reihe, auf der alles Weitere beruht.

    Spearman und nicht Pearson: Es geht um die Rangfolge, nicht um die
    Hoehe. Ein Modell, das die Reihenfolge trifft, aber die Renditen um
    den Faktor zehn danebenschaetzt, ist fuer eine Rangliste brauchbar.
    """
    df = pd.DataFrame({"p": vorhersage, "y": tatsaechlich, "tag": tage}).dropna()
    paare = []
    for tag, g in df.groupby("tag", sort=False):
        if len(g) < min_je_tag or g["p"].nunique() < 2:
            continue
        r = g["p"].corr(g["y"], method="spearman")
        if np.isfinite(r):
            paare.append((tag, r))
    # Chronologisch - Newey-West liest die Autokorrelation aus der
    # Reihenfolge (dieselbe Zusicherung wie in shadow_eval.ic).
    paare.sort(key=lambda x: x[0])
    return pd.Series([r for _, r in paare], index=[t for t, _ in paare], dtype=float)


def _tages_spreizung(vorhersage: pd.Series, tatsaechlich: pd.Series,
                     tage: pd.Series, n_koerbe: int = 10,
                     min_je_tag: int = 20) -> pd.Series:
    """Oberstes minus unterstes Dezil, je Handelstag.

    Der IC sagt, ob sortiert wird. Diese Zahl sagt, ob sich das lohnt: Sie
    ist naeher an dem, was ein Bot tatsaechlich verdient, weil er nur die
    Spitze der Rangliste kauft.
    """
    df = pd.DataFrame({"p": vorhersage, "y": tatsaechlich, "tag": tage}).dropna()
    werte = []
    for tag, g in df.groupby("tag", sort=False):
        if len(g) < min_je_tag or g["p"].nunique() < n_koerbe:
            continue
        try:
            koerbe = pd.qcut(g["p"], n_koerbe, labels=False, duplicates="drop")
        except ValueError:
            continue
        oben, unten = koerbe.max(), koerbe.min()
        if oben == unten:
            continue
        werte.append((tag, g.loc[koerbe == oben, "y"].mean()
                      - g.loc[koerbe == unten, "y"].mean()))
    werte.sort(key=lambda x: x[0])
    return pd.Series([v for _, v in werte], index=[t for t, _ in werte], dtype=float)


def guete(vorhersage: pd.Series, tatsaechlich: pd.Series, tage: pd.Series,
          *, name: str, horizont: int, schwelle: float | None = None) -> Guete:
    """Die eine Auswertungsfunktion - fuer das Modell wie fuer den Score.

    Dass beide durch dieselbe Funktion laufen, ist der Punkt: Ein
    Vergleich, bei dem die neue Methode anders gemessen wird als die alte,
    ist kein Vergleich. Genau daran ist in BEFUNDE §G11 Fund 6 schon
    einmal eine ganze Score-Tabelle gescheitert.
    """
    if schwelle is None:
        from . import fleet
        schwelle = fleet.schwelle_sigma()

    ic_reihe = _tages_ic(vorhersage, tatsaechlich, tage)
    if len(ic_reihe) < 2:
        return Guete(name, len(ic_reihe), np.nan, np.nan, np.nan, np.nan,
                     np.nan, np.nan, horizont, schwelle)

    tage_idx = pd.Series(ic_reihe.index, index=ic_reihe.index)
    erg = statistik.gruppierter_test(ic_reihe, tage_idx, horizont=horizont,
                                     min_gruppen=20)

    spr = _tages_spreizung(vorhersage, tatsaechlich, tage)
    if len(spr) >= 2:
        spr_erg = statistik.gruppierter_test(
            spr, pd.Series(spr.index, index=spr.index),
            horizont=horizont, min_gruppen=20)
        spr_mittel, spr_t = spr_erg.mittel * 100, spr_erg.t_ueberlappung
    else:
        spr_mittel, spr_t = np.nan, np.nan

    return Guete(
        name=name,
        n_tage=len(ic_reihe),
        ic=float(ic_reihe.mean()),
        # `t_ueberlappung` und nicht `t` - bei Horizont > 1 ist der
        # unkorrigierte Wert laut §G12 im Mittel um 1,62 zu hoch.
        t=float(erg.t_ueberlappung),
        t_roh=float(erg.t),
        aufblaehung=float(erg.aufblaehung),
        spreizung=float(spr_mittel),
        spreizung_t=float(spr_t),
        horizont=horizont,
        schwelle=schwelle,
    )


def vergleichsbericht(ergebnisse: list[Guete], *, frage: str = "") -> str:
    """Modell gegen Score, nebeneinander, mit der Schwelle im Kopf."""
    if not ergebnisse:
        return "  (keine Ergebnisse)"
    s = ergebnisse[0].schwelle
    h = ergebnisse[0].horizont
    z = [
        "=" * 78,
        "  SORTIERGUETE - querschnittlich je Handelstag, Ueberlappung korrigiert",
        "=" * 78,
    ]
    if frage:
        z += [f"  Frage: {frage}", ""]
    z += [
        f"  {'':<22} {'IC':>8} {'t':>6} {'t_roh':>7} {'Spreizung':>9} {'t':>6}   Urteil",
        "  " + "-" * 74,
    ]
    z += [g.zeile() for g in ergebnisse]
    z += [
        "  " + "-" * 74,
        f"  Handelstage: {ergebnisse[0].n_tage:,}".replace(",", ".")
        + f"   Horizont: {h} Tage   Schwelle: t > {s:.2f}",
        "",
        "  `t` ist der um die Ueberlappung korrigierte Wert (BEFUNDE §G12).",
        "  `t_roh` steht zum Vergleich da und wird NICHT zitiert - bei",
        f"  {h}-Tage-Fenstern liegt seine Fehlalarmquote bei 39,5 % statt 5 %.",
        "",
        "  Die Schwelle stammt aus `fleet.schwelle_sigma()` und steigt mit",
        "  jedem je angemeldeten Versuch. Ein t-Wert darunter ist der",
        "  NORMALFALL, kein Befund (BEFUNDE §B2).",
        "=" * 78,
    ]
    if any(np.isnan(g.t) for g in ergebnisse):
        z += [
            "",
            "  ! Mindestens ein t-Wert ist nicht berechenbar. Das ist kein",
            "    Fehler, sondern die ehrliche Antwort: Bei einem "
            f"{h}-Tage-Fenster",
            f"    braucht Newey-West mindestens {3 * h} Handelstage (§G14).",
            "    Der rohe Wert springt bewusst NICHT ein - er waere die",
            "    optimistischste aller Antworten.",
        ]
    return "\n".join(z)


def baue_score(bars: pd.DataFrame, panel: Panel,
               market: pd.Series | None = None,
               weights=None, verbose: bool = True) -> pd.Series:
    """Der bestehende Handel-Score fuer dieselben Zeilen wie das Panel.

    Der Gegenspieler im Vergleich. Er muss aus **derselben** Funktion
    kommen, die der Bot benutzt (`signals.build_reversal_frame`), und auf
    **denselben** Zeilen ausgewertet werden wie das Modell - sonst
    vergleicht man zwei verschiedene Stichproben und nennt es Fortschritt.

    Rueckgabe ist auf `panel.X.index` ausgerichtet; Zeilen ohne Score
    bleiben NaN und fallen in `guete()` heraus.
    """
    from .signals import build_reversal_frame

    stuecke = {}
    symbole = panel.symbole.unique()
    for i, sym in enumerate(symbole):
        try:
            df = bars.xs(sym, level="symbol").sort_index()
        except KeyError:
            continue
        f = build_reversal_frame(df, market=market, weights=weights)
        stuecke[sym] = f["score"]
        if verbose and (i + 1) % 200 == 0:
            print(f"      Score {i + 1:,}/{len(symbole):,}".replace(",", "."))

    if not stuecke:
        return pd.Series(np.nan, index=panel.X.index, dtype=float)

    lang = pd.concat(stuecke, names=["symbol", "tag"]).rename("score")
    schl = pd.MultiIndex.from_arrays([panel.symbole, panel.tage])
    return pd.Series(lang.reindex(schl).to_numpy(), index=panel.X.index,
                     dtype=float, name="score")
