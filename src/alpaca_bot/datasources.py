"""Datenquellen-Router: Alpaca sparsam, freie Quellen ausreizen.

Alpacas Basic-Plan erlaubt 200 Requests/Minute. Dieses Kontingent wird
gebraucht fuer das, wofuer es keinen Ersatz gibt: Kontostand, Orders,
Positionen und die Kurse im Moment der Handelsentscheidung.

Fuer Forschung und Backtests ist es Verschwendung - dort werden Millionen
Bars ueber tausende Symbole gebraucht, immer wieder. Deshalb:

    Alpaca      -> Handel, Konto, Live-Quotes zur Entscheidung
    yfinance    -> Massendaten fuer Forschung und Backtests
    Stooq       -> Ausweichquelle, wenn yfinance blockt

Zwei Vorteile jenseits des Kontingents:
  * Alpacas Historie beginnt 2016. yfinance und Stooq reichen Jahrzehnte
    zurueck - mehr Marktregime, mehr unabhaengige Beobachtungen.
  * Wiederholte Forschungslaeufe kosten mit Plattencache nichts.

**Das Risiko dabei, offen benannt:** Verschiedene Quellen liefern leicht
verschiedene Kurse - andere Anpassung bei Splits und Dividenden, andere
Schlusskurs-Definition. Wer auf Quelle A forscht und mit Quelle B
handelt, validiert etwas anderes, als er tut. Deshalb gibt es
`compare_sources()`, und deshalb wird innerhalb einer Studie NIE
gemischt.
"""

from __future__ import annotations

import datetime as dt
import io
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from .config import CACHE_DIR
from .ratelimit import RateLimiter, with_retry

BAR_CACHE = CACHE_DIR / "bars"
BAR_CACHE.mkdir(parents=True, exist_ok=True)

OHLCV = ["open", "high", "low", "close", "volume"]


class DataSourceError(RuntimeError):
    pass


def _cache_path(source: str, key: str, years: float) -> Path:
    return BAR_CACHE / f"{source}_{key}_{years:g}y.parquet"


def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    """Bringt beliebige Quellen auf das Alpaca-Format:
    MultiIndex (symbol, timestamp), Spalten open/high/low/close/volume, UTC."""
    if df.empty:
        return df
    df = df[[c for c in OHLCV if c in df.columns]].copy()
    for c in df.columns:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.dropna(subset=["close"])


# ---------------------------------------------------------------------------
# yfinance
# ---------------------------------------------------------------------------
def _yf_batch(symbols: list[str], years: float) -> pd.DataFrame:
    import yfinance as yf

    limiter = RateLimiter("yfinance")
    limiter.acquire()

    start = (dt.datetime.now(dt.UTC) - dt.timedelta(days=int(years * 365))).date()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        raw = with_retry(
            lambda: yf.download(
                tickers=symbols,
                start=start,
                interval="1d",
                auto_adjust=True,   # Splits und Dividenden eingerechnet
                group_by="ticker",
                threads=True,
                progress=False,
                repair=True,
            ),
            retries=2,
        )
    if raw is None or raw.empty:
        return pd.DataFrame()

    frames = {}
    if isinstance(raw.columns, pd.MultiIndex):
        for sym in symbols:
            if sym not in raw.columns.get_level_values(0):
                continue
            sub = raw[sym].rename(columns=str.lower)
            sub = _normalize(sub)
            if not sub.empty:
                frames[sym] = sub
    else:
        sub = _normalize(raw.rename(columns=str.lower))
        if not sub.empty:
            frames[symbols[0]] = sub

    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, names=["symbol", "timestamp"])
    # Auf der EBENE arbeiten, nicht auf den expandierten Werten:
    # get_level_values() liefert einen Eintrag je Zeile (mit Duplikaten),
    # set_levels() erwartet aber die eindeutigen Ebenenwerte.
    level = out.index.levels[out.index.names.index("timestamp")]
    if level.tz is None:
        out.index = out.index.set_levels(
            pd.DatetimeIndex(level).tz_localize("UTC"), level="timestamp"
        )
    return out.sort_index()


# ---------------------------------------------------------------------------
# Stooq - Ausweichquelle, kein Schluessel, keine Registrierung
# ---------------------------------------------------------------------------
def _stooq_one(symbol: str) -> pd.DataFrame:
    url = f"https://stooq.com/q/d/l/?s={symbol.lower()}.us&i=d"
    resp = with_retry(lambda: requests.get(url, timeout=30), retries=2)
    if resp.status_code != 200 or "Date" not in resp.text[:200]:
        return pd.DataFrame()
    df = pd.read_csv(io.StringIO(resp.text))
    if df.empty or "Close" not in df.columns:
        return pd.DataFrame()
    df["timestamp"] = pd.to_datetime(df["Date"], utc=True)
    df = df.set_index("timestamp").rename(columns=str.lower)
    return _normalize(df)


def _stooq_batch(symbols: list[str], years: float) -> pd.DataFrame:
    cutoff = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=int(years * 365))
    frames = {}
    for sym in symbols:
        try:
            df = _stooq_one(sym)
        except Exception:  # noqa: BLE001
            continue
        if not df.empty:
            frames[sym] = df[df.index >= cutoff]
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, names=["symbol", "timestamp"]).sort_index()


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------
def get_history(
    symbols: str | list[str],
    years: float = 5.0,
    source: str = "yfinance",
    batch_size: int = 200,
    use_cache: bool = True,
    verbose: bool = True,
) -> pd.DataFrame:
    """Historische Tagesbars aus einer freien Quelle, im Alpaca-Format.

    Args:
        source: 'yfinance' | 'stooq' | 'alpaca'.
            'alpaca' NUR verwenden, wenn es wirklich Alpaca-Kurse sein
            muessen - es verbraucht das knappe Handelskontingent.

    Returns:
        MultiIndex (symbol, timestamp) mit open/high/low/close/volume.
    """
    syms = [symbols] if isinstance(symbols, str) else sorted(set(symbols))
    if not syms:
        return pd.DataFrame()

    # hashlib statt Pythons eingebautem hash(): Der ist pro Prozessstart
    # zufaellig gesalzen (Hash-Randomisierung seit Python 3.3) - ein zweiter
    # Skriptlauf mit demselben Symbolset haette einen ANDEREN Schluessel
    # bekommen, den Cache faelschlich als leer angesehen und alles neu
    # abgerufen. Genau das hat am 04.08.2026 das yfinance-Tageskontingent
    # (1800/Tag) durch einen zweiten Lauf von scripts/19_faktor_tests.py
    # vollstaendig aufgebraucht, obwohl alle Daten schon im Cache lagen.
    # `shadow.lade_bars` umgeht das Problem bereits mit hashlib - hier
    # nachgezogen, statt es fuer jeden weiteren Aufrufer offen zu lassen.
    import hashlib

    digest = hashlib.sha256("|".join(syms).encode()).hexdigest()[:10]
    key = f"{len(syms)}_{digest}"
    cache = _cache_path(source, key, years)
    if use_cache and cache.exists():
        if verbose:
            print(f"      aus Cache: {cache.name}")
        return pd.read_parquet(cache)

    if source == "alpaca":
        from .data import get_bars

        out = get_bars(syms, "1D", lookback_days=int(years * 365))
    else:
        fetch = _yf_batch if source == "yfinance" else _stooq_batch
        frames = []
        n_batches = (len(syms) + batch_size - 1) // batch_size
        for i in range(0, len(syms), batch_size):
            chunk = syms[i : i + batch_size]
            try:
                part = fetch(chunk, years)
                if not part.empty:
                    frames.append(part)
            except Exception as e:  # noqa: BLE001
                if verbose:
                    print(f"      Batch {i // batch_size + 1}: {type(e).__name__}: {e}")
            if verbose:
                got = sum(len(f) for f in frames)
                print(f"      {source}: Batch {i // batch_size + 1}/{n_batches} "
                      f"-> {got:,} Bars")
        out = pd.concat(frames).sort_index() if frames else pd.DataFrame()

    if use_cache and not out.empty:
        out.to_parquet(cache)
    return out


def compare_sources(
    symbols: list[str], years: float = 2.0, verbose: bool = True
) -> pd.DataFrame:
    """Prueft, wie stark Alpaca und die freie Quelle voneinander abweichen.

    Pflichtpruefung, bevor auf einer freien Quelle geforscht und bei
    Alpaca gehandelt wird. Grosse Abweichungen bedeuten unterschiedliche
    Split-/Dividendenanpassung - dann sind die Backtest-Renditen nicht
    die, die man handeln wuerde.

    Faustregel: mittlere absolute Abweichung der Tagesrenditen unter
    10 Basispunkten ist unbedenklich, ueber 50 bps ist ein Problem.
    """
    from .data import get_bars, ohlcv

    alp = get_bars(symbols, "1D", lookback_days=int(years * 365))
    free = get_history(symbols, years, source="yfinance", verbose=False)

    rows = []
    for sym in symbols:
        try:
            a = ohlcv(alp, sym)["close"]
            b = free.xs(sym, level="symbol")["close"]
        except KeyError:
            continue
        a.index = pd.DatetimeIndex(a.index).normalize()
        b.index = pd.DatetimeIndex(b.index).normalize()
        common = a.index.intersection(b.index)
        if len(common) < 50:
            continue
        ra = a.loc[common].pct_change().dropna()
        rb = b.loc[common].pct_change().dropna()
        i2 = ra.index.intersection(rb.index)
        diff_bps = float((ra.loc[i2] - rb.loc[i2]).abs().mean() * 10_000)
        rows.append({
            "symbol": sym,
            "gemeinsame_tage": len(common),
            "korrelation": round(float(ra.loc[i2].corr(rb.loc[i2])), 5),
            "abweichung_bps": round(diff_bps, 2),
            "kurs_alpaca": round(float(a.loc[common[-1]]), 2),
            "kurs_frei": round(float(b.loc[common[-1]]), 2),
        })

    df = pd.DataFrame(rows)
    if verbose and not df.empty:
        mean_diff = df["abweichung_bps"].mean()
        print(df.to_string(index=False))
        print(f"\n  Mittlere Abweichung der Tagesrenditen: {mean_diff:.2f} bps")
        if mean_diff < 10:
            print("  -> unbedenklich, Forschung auf der freien Quelle ist vertretbar")
        elif mean_diff < 50:
            print("  -> spuerbar. Ergebnisse vor dem Handeln auf Alpaca-Daten gegenpruefen")
        else:
            print("  -> ZU GROSS. Unterschiedliche Anpassung. Nicht mischen.")
    return df
