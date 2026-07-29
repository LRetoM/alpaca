"""Nachrichten als Kandidaten-Merkmale - regelbasiert, ohne trainiertes Modell.

Der Live-Bot entscheidet bisher ausschliesslich aus Kurs- und Volumendaten:
`build_reversal_frame()` bekommt nichts als OHLCV plus SPY. Gleichzeitig
liegt mit `news.py` ein vollstaendig gebauter Nachrichten-Zugang brach - er
wurde bis 2026-07-29 von keiner Stelle im Projekt aufgerufen.

Dieses Modul schliesst die Luecke. Es liefert Merkmale, die NICHT im Kurs
stecken, und ist damit echte Diversifikation gegenueber den bestehenden
Umkehr-Faktoren, die laut `signals.py` untereinander stark korreliert sind.

**Warum kein Sentiment-Modell und keine frei erfundene Stichwortliste:**

Loughran & McDonald (2011, Journal of Finance) haben gezeigt, dass
allgemeine Sentiment-Woerterbuecher in Finanztexten ~75 % der als "negativ"
markierten Woerter falsch einstufen - "tax", "cost", "liability" klingen
negativ, sind in Finanzsprache aber neutral. Dazu kommen Verneinungen
("denies bankruptcy rumors") und gemischte Aussagen ("beats on revenue,
misses on EPS").

Tragfaehig ist stattdessen, in dieser Reihenfolge:

  1. **Ereignistyp** (primaer). Benzinga-Schlagzeilen sind stark
     schablonenhaft ("X Reports Q3 EPS of $Y, Est. $Z"). Regeln erkennen den
     TYP zuverlaessig, weil das Vokabular eng und standardisiert ist.
  2. **Frequenz-Anomalie** ueber `news.news_features()` - laut
     docs/strategie-analyse.md das staerkste Signal aus News ueberhaupt.
  3. **Tonalitaet** (schwach, bewusst nachrangig).

**Zeitpunktsicherheit:** Ein Artikel traegt den Zeitpunkt seiner
VEROEFFENTLICHUNG, nicht den des Ereignisses. "Aktie springt 30 % nach
Zahlen" erscheint NACH dem Sprung. `news.news_features()` erzwingt deshalb
einen Verzug ueber `pit.asof_join`; dieses Modul reicht ihn unveraendert
durch und fuegt nichts hinzu, was daran vorbeiginge.

**Erwartung, vor der ersten Messung festgehalten:** eher schwacher
Zusatzbaustein als neue Ertragsquelle. Kein Einzelsignal im Projekt hat je
einen IC ueber ~0.05 erreicht, und die Architektur (Entscheidung auf
Schlusskurs T, Ausfuehrung T+1) verpasst die schnelle Nachrichtenreaktion
ohnehin. Die aussichtsreichste Ausnahme ist PEAD - die Drift nach
Gewinnueberraschungen wirkt ueber Wochen und passt damit zum Horizont.
"""

from __future__ import annotations

import re

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Ereignistypen - eng gefasste Muster auf schablonenhaften Schlagzeilen.
# Jede Kategorie bleibt eine EIGENE Groesse; sie zu einem Score zu verrechnen
# wuerde genau die Information zerstoeren, die sie wertvoll macht.
# ---------------------------------------------------------------------------
EREIGNISSE: dict[str, re.Pattern] = {
    "gewinn_uebertroffen": re.compile(
        r"\b(beats?|tops?|exceeds?)\b.{0,30}\b(estimate|consensus|expectation|eps|view)",
        re.I),
    "gewinn_verfehlt": re.compile(
        r"\b(miss(es|ed)?|falls? short|below)\b.{0,30}\b(estimate|consensus|expectation|eps|view)",
        re.I),
    "prognose_angehoben": re.compile(
        r"\b(raises?|lifts?|boosts?|hikes?)\b.{0,25}\b(guidance|outlook|forecast|target)",
        re.I),
    "prognose_gesenkt": re.compile(
        r"\b(cuts?|lowers?|slashes|trims?|reduces?)\b.{0,25}\b(guidance|outlook|forecast|target)",
        re.I),
    "hochgestuft": re.compile(r"\bupgrade[sd]?\b", re.I),
    "herabgestuft": re.compile(r"\bdowngrade[sd]?\b", re.I),
    # "to buy" bewusst NICHT als Muster: Es trifft Analysten-Einstufungen
    # ("Upgrades Tesla To Buy") und erzeugte damit falsche Uebernahmen.
    "uebernahme": re.compile(
        r"\b(to acquire|acquisition|merger|merges with|buyout|takeover)\b", re.I),
    "rechtlich": re.compile(
        r"\b(lawsuit|litigation|investigation|subpoena|probe|recall|fda (reject|warning))\b",
        re.I),
    "fuehrungswechsel": re.compile(
        r"\b(resigns?|steps down|appoints?|names?)\b.{0,20}\b(ceo|cfo|president|chair)",
        re.I),
    "dividende": re.compile(r"\b(declares?|raises?|cuts?)\b.{0,15}\bdividend\b", re.I),
    "aktienrueckkauf": re.compile(r"\b(buyback|repurchase program)\b", re.I),
}

# Fachwortlisten in Anlehnung an Loughran-McDonald. Bewusst kurz und
# finanzspezifisch statt allgemeinsprachlich - eine lange, frei erfundene
# Liste waere genau der Fehler, den die Studie nachgewiesen hat.
POSITIV = {
    "beats", "beat", "tops", "exceeds", "raises", "upgrade", "upgraded",
    "surges", "soars", "record", "strong", "growth", "profit", "gains",
    "outperform", "buyback", "approval", "approved", "wins", "awarded",
}
NEGATIV = {
    "misses", "missed", "cuts", "cut", "downgrade", "downgraded", "plunges",
    "slumps", "weak", "loss", "losses", "lawsuit", "investigation", "recall",
    "bankruptcy", "default", "halts", "halted", "warning", "resigns", "probe",
}
# Verneinungen kehren die Bedeutung um. Ohne diese Pruefung waere
# "denies bankruptcy rumors" eine schlechte Nachricht.
VERNEINUNG = re.compile(r"\b(denies|denied|refutes|dismisses|no |not )\b", re.I)


def ereignistypen(headline: str) -> list[str]:
    """Welche Ereignistypen stecken in dieser Schlagzeile?

    Mehrfachtreffer sind erlaubt und gewollt - "beats on revenue, cuts
    guidance" ist beides und darf nicht zu einem Wert verrechnet werden.
    """
    if not headline:
        return []
    return [name for name, muster in EREIGNISSE.items() if muster.search(headline)]


def tonalitaet(headline: str) -> float:
    """Ton einer Schlagzeile in [-1, 1]. Bewusst SCHWACHES Zweitmerkmal.

    Reine Wortzaehlung auf einer finanzspezifischen Liste. Kein Modell,
    kein Training, deterministisch nachvollziehbar.

    Zwei bewusste Daempfungen, beide aus Fehlern im ersten Test:

    * **Belegstaerke.** Ein einziges Stichwort erzeugte zuvor sofort den
      Vollausschlag ±1.00, womit das Merkmal faktisch dreiwertig war.
      Ein Treffer zaehlt jetzt halb, ab zwei gilt der volle Wert.
    * **Verneinung daempft, statt zu kippen.** "Company Denies Bankruptcy
      Rumors" ergab durch reines Vorzeichenwechseln +1.00 - also eine
      starke GUTE Nachricht. Ein Dementi ist aber neutral bis leicht
      negativ, nicht positiv. Verneinte Schlagzeilen werden deshalb stark
      gegen null gezogen.
    """
    if not headline:
        return 0.0
    woerter = re.findall(r"[a-z']+", headline.lower())
    if not woerter:
        return 0.0
    p = sum(w in POSITIV for w in woerter)
    n = sum(w in NEGATIV for w in woerter)
    if p == n == 0:
        return 0.0

    ton = (p - n) / (p + n)
    ton *= min(1.0, (p + n) / 2.0)          # Belegstaerke
    if VERNEINUNG.search(headline):
        ton *= -0.25                         # Daempfung statt Kippen
    return round(ton, 3)


def merkmale_je_symbol(artikel: pd.DataFrame, symbol: str,
                       preis_index: pd.DatetimeIndex,
                       *, verzug: pd.Timedelta = pd.Timedelta(days=1)
                       ) -> pd.DataFrame:
    """Alle Nachrichten-Merkmale eines Symbols auf dem Kurs-Zeitraster.

    Baut auf `news.news_features()` auf - dort sitzt die
    Zeitpunkt-Sperre - und ergaenzt Ereignistyp und Ton.
    """
    from . import news

    basis = news.news_features(artikel, preis_index, symbol, delay=verzug)

    if artikel.empty or "headline" not in artikel:
        for c in ("news_ton", *[f"ev_{k}" for k in EREIGNISSE]):
            basis[c] = 0.0
        return basis

    lang = news.explode_symbols(artikel)
    lang = lang[lang["symbol"] == symbol].copy()
    if lang.empty:
        for c in ("news_ton", *[f"ev_{k}" for k in EREIGNISSE]):
            basis[c] = 0.0
        return basis

    # Derselbe Verzug wie in news_features - sonst liefe der Ton der
    # Frequenz voraus und brächte genau das Leck zurueck, das dort
    # verhindert wird.
    lang["verfuegbar"] = pd.DatetimeIndex(lang["timestamp"]) + verzug
    lang["ton"] = lang["headline"].map(tonalitaet)
    for name in EREIGNISSE:
        lang[f"ev_{name}"] = lang["headline"].map(
            lambda h, n=name: float(n in ereignistypen(h)))

    spalten = ["ton"] + [f"ev_{k}" for k in EREIGNISSE]
    je_tag = (lang.set_index("verfuegbar")[spalten]
              .resample("1D").mean())

    ziel = pd.DatetimeIndex(preis_index)
    if ziel.tz is None:
        ziel = ziel.tz_localize("UTC")
    ausgerichtet = je_tag.reindex(ziel, method="ffill").fillna(0.0)
    ausgerichtet.index = preis_index

    basis["news_ton"] = ausgerichtet["ton"]
    for k in EREIGNISSE:
        basis[f"ev_{k}"] = ausgerichtet[f"ev_{k}"]
    return basis


def kontext_fuer_stichtag(symbole: list[str], stichtag: pd.Timestamp,
                          *, tage_zurueck: int = 90,
                          verbose: bool = False) -> pd.DataFrame:
    """Nachrichten-Kontext je Symbol ZUM Stichtag - eine Zeile je Symbol.

    Fuer den Schattenbetrieb: Was war ueber dieses Symbol am
    Entscheidungstag bekannt? Bewusst nur der letzte Stand, nicht die ganze
    Reihe - gespeichert wird ein Kontext je Vorhersage.
    """
    from . import news

    start = (stichtag - pd.Timedelta(days=tage_zurueck)).strftime("%Y-%m-%d")
    ende = stichtag.strftime("%Y-%m-%d")
    try:
        artikel = news.get_news(symbole, start=start, end=ende,
                                max_articles=5_000)
    except Exception as e:  # noqa: BLE001 - News duerfen den Lauf nie stoppen
        if verbose:
            print(f"      News nicht abrufbar: {type(e).__name__}: {e}")
        return pd.DataFrame()

    if artikel.empty:
        return pd.DataFrame()

    lang = news.explode_symbols(artikel)
    lang = lang[lang["symbol"].isin(symbole)].copy()
    if lang.empty:
        return pd.DataFrame()

    lang["verfuegbar"] = pd.DatetimeIndex(lang["timestamp"]) + pd.Timedelta(days=1)
    lang = lang[lang["verfuegbar"] <= stichtag]
    if lang.empty:
        return pd.DataFrame()

    lang["ton"] = lang["headline"].map(tonalitaet)
    lang["typen"] = lang["headline"].map(ereignistypen)

    fenster5 = stichtag - pd.Timedelta(days=5)
    zeilen = []
    for sym, g in lang.groupby("symbol"):
        letzte5 = g[g["verfuegbar"] > fenster5]
        tage = g["verfuegbar"].dt.normalize().nunique()
        alle_tage = max(1, tage_zurueck)
        erwartet = len(g) / alle_tage * 5
        std = np.sqrt(max(erwartet, 1.0))
        typen = [t for liste in letzte5["typen"] for t in liste]
        zeilen.append({
            "symbol": sym,
            "news_5d": float(len(letzte5)),
            "news_z": round(float((len(letzte5) - erwartet) / std), 3),
            "news_tage_her": float((stichtag - g["verfuegbar"].max()).days),
            "news_erstabdeckung": float(tage <= 1),
            "news_ton": round(float(letzte5["ton"].mean()), 3) if len(letzte5) else 0.0,
            "news_ereignis": ",".join(sorted(set(typen))) if typen else "",
        })
    return pd.DataFrame(zeilen).set_index("symbol")
