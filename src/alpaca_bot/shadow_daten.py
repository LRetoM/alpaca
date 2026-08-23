"""Datenbeschaffung fuer den Schattenbetrieb: Universum, Bars, Snapshot.

Zwischen Speicher und Schritten. Sie beschafft, was gerechnet wird -
sie rechnet nicht selbst und schreibt nichts in die Datenbank.

Die Trennung ist nicht nur Ordnung: `baue_snapshot` traegt die
Lookahead-Sperre (`MarketSnapshot.validate`). Wer sie sucht, soll sie
in der Schicht finden, die Daten liefert, und nicht zwischen 2.300
Zeilen Schrittlogik.

**Herkunft: Aufteilung von `shadow.py` am 23.08.2026 (BEFUNDE §G20).**
Der Schattenbetrieb lag in EINER Datei mit 2.339 Zeilen und fuenf
Verantwortungen. Der Code in diesem Modul wurde dabei **unveraendert**
verschoben - kein Ausdruck, keine Zeile Logik wurde angefasst. Nachgewiesen
ueber den Bytecode jeder Funktion, nicht behauptet (`scripts/29_umzug_pruefen.py`).
"""


from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

from .config import CACHE_DIR
from .engine import EngineConfig, MarketSnapshot
from .shadow_config import MARKET_SYMBOL, ShadowConfig


SHADOW_CACHE = CACHE_DIR / "shadow_bars"

# ---------------------------------------------------------------------------
# Daten
# ---------------------------------------------------------------------------
def _universum_symbole(cfg: ShadowConfig) -> list[str]:
    """Das STABILE Tagesuniversum - identisch fuer alle drei Schritte.

    Wichtig fuer den Tages-Cache in `lade_bars()`: Der Cache-Schluessel haengt
    vom exakten Symbolset ab. `einbuchen()`/`verifizieren()` bauten frueher
    ihre Liste aus den noch offenen Vorhersagen - einer Menge, die mit jeder
    abgearbeiteten Vorhersage SCHRUMPFT. Der Schluessel aenderte sich dadurch
    bei praktisch jedem Durchlauf, der Cache griff nie, und es wurde JEDE
    STUNDE neu von yfinance geladen (gemessen: ~8 offene Dateien je
    Download-Aufruf, die yfinance nicht zuverlaessig schliesst - genau das
    hat am 2026-07-29 nach einigen Stunden das Datei-Limit gerissen).

    Alle Symbole, die einbuchen/verifizieren je brauchen, sind eine
    Teilmenge dieses Universums. Mit einem STABILEN Symbolset trifft der
    Cache zuverlaessig, und es gibt nur noch EINEN echten Download-Zyklus
    je Kalendertag statt bis zu 24.
    """
    from . import universe

    if cfg.universe == "gemessen":
        symbols = universe.load_universe(max_symbols=cfg.max_symbols)
    else:
        symbols = universe.BENCHMARK_SETS[cfg.universe]
    return list(dict.fromkeys([*symbols, MARKET_SYMBOL]))

def lade_bars(symbols: list[str], years: float, *, verbose: bool = True) -> pd.DataFrame:
    """Tagesbars von yfinance, mit TAGESGENAUEM Cache.

    Bewusst NICHT `datasources.get_history(use_cache=True)`: Dessen
    Cache-Schluessel enthaelt kein Datum (`_cache_path` -> source_key_years),
    ein taeglich laufender Dienst bekaeme also stillschweigend ewig dieselben
    Daten. Hier steht das Datum im Dateinamen, ein neuer Tag laedt neu.
    """
    from .datasources import get_history

    SHADOW_CACHE.mkdir(parents=True, exist_ok=True)
    heute = dt.date.today().isoformat()
    # hashlib statt Pythons eingebautem hash(): Der ist pro Prozessstart
    # zufaellig gesalzen (Hash-Randomisierung seit Python 3.3) - nach jedem
    # Neustart des Daemons haette derselbe Symbol-Tag einen anderen
    # Schluessel ergeben und den Tages-Cache fuer den ganzen Tag entwertet.
    import hashlib

    digest = hashlib.sha256("|".join(sorted(symbols)).encode()).hexdigest()[:10]
    key = f"{len(symbols)}_{digest}"
    pfad = SHADOW_CACHE / f"{heute}_{key}_{years:g}y.parquet"

    if pfad.exists():
        if verbose:
            print(f"      aus Tages-Cache: {pfad.name}")
        return pd.read_parquet(pfad)

    bars = get_history(symbols, years=years, source="yfinance",
                       use_cache=False, verbose=verbose)
    if not bars.empty:
        bars.to_parquet(pfad)
        # Aeltere Tages-Caches aufraeumen, sonst waechst der Ordner unbegrenzt.
        for alt in sorted(SHADOW_CACHE.glob("*.parquet"))[:-3]:
            alt.unlink(missing_ok=True)
    return bars

def _regime(market: pd.Series, per_symbol: dict[str, pd.DataFrame],
            as_of: pd.Timestamp) -> dict:
    """Marktkontext zum Entscheidungszeitpunkt.

    Ohne diesen Kontext laesst sich spaeter nicht auswerten, UNTER WELCHEN
    BEDINGUNGEN der Vorsprung traegt - und genau dort liegt laut Plan §13 der
    aussichtsreichste Hebel.
    """
    out = {"regime_markt": "unbekannt", "regime_vola": "unbekannt",
           "regime_breite": None}
    if market is None or len(market) < 200:
        return out

    m = market.astype(float)
    sma200 = m.rolling(200).mean().iloc[-1]
    trend = "auf" if m.iloc[-1] > sma200 else "ab"

    ret = m.pct_change().dropna()
    vola20 = ret.tail(20).std() * np.sqrt(252)
    hist = ret.rolling(20).std().dropna() * np.sqrt(252)
    if len(hist) > 60:
        pct = float((hist.tail(504) < vola20).mean())
        band = "niedrig" if pct < 0.33 else ("mittel" if pct < 0.67 else "hoch")
    else:
        band = "unbekannt"

    ueber_sma50 = []
    for df in per_symbol.values():
        if len(df) < 50:
            continue
        c = df["close"].astype(float)
        ueber_sma50.append(float(c.iloc[-1] > c.rolling(50).mean().iloc[-1]))

    out["regime_markt"] = f"{trend}waerts"
    out["regime_vola"] = band
    out["regime_breite"] = round(float(np.mean(ueber_sma50)), 3) if ueber_sma50 else None
    return out

def baue_snapshot(bars: pd.DataFrame, *, min_bars: int = 260,
                  verbose: bool = True) -> tuple[MarketSnapshot, dict]:
    """Baut die Momentaufnahme aus yfinance-Bars.

    `as_of` ist der letzte Tag mit Daten. Anders als im Live-Betrieb muss hier
    keine unfertige Tagesbar verworfen werden: Der Lauf findet nach US-Schluss
    statt, und yfinance liefert Tagesbars erst, wenn der Tag abgeschlossen ist.
    Die Kalenderpruefung in `entscheiden()` stellt das sicher.
    """
    per_symbol: dict[str, pd.DataFrame] = {}
    for sym in bars.index.get_level_values("symbol").unique():
        df = bars.xs(sym, level="symbol").sort_index()
        if len(df) >= min_bars:
            per_symbol[sym] = df

    if not per_symbol:
        raise RuntimeError(
            f"Kein Symbol mit mindestens {min_bars} Bars - zu wenig Historie."
        )

    markt_df = per_symbol.pop(MARKET_SYMBOL, None)
    if markt_df is None:
        raise RuntimeError(
            f"{MARKET_SYMBOL} fehlt. Ohne Marktreferenz waere der Regime-Filter "
            "inaktiv und der Schatten wiche vom Live-Verhalten ab."
        )
    market = markt_df["close"].astype(float)

    as_of = max(pd.Timestamp(df.index[-1]) for df in per_symbol.values())
    if as_of.tz is None:
        as_of = as_of.tz_localize("UTC")

    # Nur Symbole, die bis zum Stichtag reichen - sonst entscheidet die Engine
    # auf veralteten Kursen (delistet, Handelsaussetzung).
    def _letzter(df: pd.DataFrame) -> pd.Timestamp:
        t = pd.Timestamp(df.index[-1])
        return t.tz_localize("UTC") if t.tz is None else t

    aktuell = {
        s: df for s, df in per_symbol.items()
        if _letzter(df) >= as_of - pd.Timedelta(days=5)
    }

    # --- Nachrichten fuer die Signalberechnung (Faktor ReversalWeights.news) ---
    # EIN Abruf fuer das ganze Universum, wie im Handelsbot (live.py) - sonst
    # wuerde die Rangfolge, die ueber die Kandidatenauswahl fuer den
    # News-Kontext unten entscheidet, selbst schon ohne News gebildet, und
    # der Faktor koennte nie mitentscheiden, wer ueberhaupt in Frage kommt.
    # Defensiv: ein Ausfall der News-API darf den Schattenbetrieb niemals
    # stoppen (siehe _news_kontext).
    news_df = None
    try:
        from . import news as news_mod

        start = (as_of - pd.Timedelta(days=90)).strftime("%Y-%m-%d")
        news_df = news_mod.get_news(
            list(aktuell), start=start, end=as_of.strftime("%Y-%m-%d"),
            max_articles=5_000,
        )
        if verbose:
            print(f"      Nachrichten: {len(news_df)} Artikel geladen")
    except Exception as e:  # noqa: BLE001
        if verbose:
            print(f"      Nachrichten nicht ladbar ({type(e).__name__}) - "
                  "Schattenbetrieb faehrt ohne Nachrichtenfaktor fort.")
        news_df = None

    if verbose:
        print(f"      Stichtag: {as_of.date()} | {len(aktuell)} Symbole "
              f"| Marktfilter: {MARKET_SYMBOL}")

    snap = MarketSnapshot(as_of=as_of, bars=aktuell, market=market.loc[:as_of],
                          news=news_df)
    snap.validate()
    return snap, {"markt": market}

# ---------------------------------------------------------------------------
# Schritt 1: Entscheiden - beide Buecher, alle Bots der Flotte
# ---------------------------------------------------------------------------
def _signalrahmen(per_symbol: dict[str, pd.DataFrame], market: pd.Series,
                  cfg: EngineConfig, news: pd.DataFrame | None = None,
                  ) -> dict[str, pd.DataFrame]:
    """Berechnet die Signale je Symbol EINMAL fuer eine Signalkonfiguration.

    Die meisten Flottenvarianten aendern nur Ausstiegsparameter (stop_atr,
    target_atr, max_hold_days, min_score) - die beruehren die
    Signalberechnung nicht. Sieben Bots brauchen dadurch zwei Durchlaeufe
    statt sieben; das ist die Voraussetzung dafuer, die Flotte ueberhaupt
    taeglich ueber ~800 Symbole laufen zu lassen.

    `news` wird unveraendert an `build_reversal_frame` durchgereicht - die
    Zeitpunktsicherheit (Verfuegbarkeit = Veroeffentlichung + Verzug) passiert
    dort je Symbol, nicht hier (siehe signals.build_reversal_frame).
    """
    from .signals import build_reversal_frame, build_signal_frame

    if cfg.strategy == "reversal":
        return {s: build_reversal_frame(df, market, cfg.reversal_weights,
                                        symbol=s, news=news)
                for s, df in per_symbol.items()}
    return {s: build_signal_frame(df, None, cfg.weights)
            for s, df in per_symbol.items()}

def _news_kontext(symbole: list[str], stichtag: pd.Timestamp,
                  verbose: bool = False) -> dict[str, dict]:
    """Zusaetzlicher Tonalitaets-/Ereignis-Kontext je Symbol - nur Metadaten.

    Anders als `news_z`/`news_5d`/`news_tage_her`/`news_erstabdeckung` (die
    kommen jetzt aus `signals.build_reversal_frame` und beeinflussen den
    Score aktiv, siehe ReversalWeights.news) liefert diese Funktion NUR
    `news_ton` und `news_ereignis` - eine zweite, unabhaengige Einordnung
    (Tonalitaet/Ereignistyp) ueber `news_features.py`, fuer die es in
    `news.py`s Score-Pfad keine Entsprechung gibt. Bewusst kein Gate, keine
    Wirkung auf die Entscheidung - reine Zusatzbeobachtung fuer die
    spaetere Auswertung. Darf den Lauf niemals stoppen.
    """
    try:
        from .news_features import kontext_fuer_stichtag

        df = kontext_fuer_stichtag(symbole, stichtag, verbose=verbose)
        if df.empty:
            return {}
        if verbose:
            print(f"      News-Kontext fuer {len(df)} von {len(symbole)} Symbolen")
        return df.to_dict(orient="index")
    except Exception as e:  # noqa: BLE001
        if verbose:
            print(f"      News-Kontext uebersprungen: {type(e).__name__}: {e}")
        return {}
