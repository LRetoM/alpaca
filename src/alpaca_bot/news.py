"""Nachrichten-Historie von Alpaca (Benzinga-Feed) - zeitpunktsicher.

Kostenlos im Konto enthalten, deckt praktisch alle US-Aktien ab, Historie
ab etwa 2015. Damit ist die Frage "gibt es zu allen Aktien abfragbare News"
mit Ja beantwortet - mit einer wichtigen Einschraenkung, die den Kern
deines Testplans betrifft:

**Ein Artikel traegt den Zeitpunkt seiner Veroeffentlichung, nicht den des
Ereignisses.** Die Meldung "XY springt 30 % nach Zahlen" erscheint NACH dem
Sprung. Fuehrt man News und Kurse naiv auf Tagesebene zusammen, landet
dieser Artikel im selben Zeitfenster wie die Bewegung - und das Modell
"erkennt" Ausbrueche mit traumhafter Trefferquote, die live nicht existiert.

Deshalb laeuft hier jede Zusammenfuehrung ueber `pit.asof_join` mit einer
erzwungenen Verzoegerung. Es gibt in diesem Modul keinen Weg daran vorbei.

Was aus News realistisch herauszuholen ist (siehe docs/strategie-analyse.md):
  * Frequenz-Anomalie - ploetzlich viel mehr Artikel als sonst  (mittel-hoch)
  * Erstabdeckung - vorher nie erwaehnte Werte                  (mittel)
  * Tonalitaet/Sentiment                                        (schwach, ueberschaetzt)
"""

from __future__ import annotations

import datetime as dt
from typing import Sequence

import numpy as np
import pandas as pd
from alpaca.data.historical.news import NewsClient
from alpaca.data.requests import NewsRequest

from .config import get_settings
from .ratelimit import RateLimiter, with_retry

_limit = RateLimiter("alpaca_news")

# Alpaca liefert maximal 50 Artikel je Antwort.
_PAGE_SIZE = 50

# Fenstergroesse fuer die zeitliche Aufteilung in get_news(), siehe dort.
# 1 Tag statt mehrerer: Bei einem realistischen Live-Universum (~1200 Symbole)
# ist selbst ein 3-Tage-Fenster praktisch IMMER am 50-Artikel-Deckel
# gesaettigt (gemessen 03.08.2026: alle 30 Fenster bei 3 Tagen randvoll,
# macht die Tages-Zaehlung, auf der news_1d/5d/z aufbauen, ungenauer als
# noetig). Mit 1 Tag kostet derselbe 90-Tage-Abruf ca. 30s statt 9s - fuer
# einen Entscheidungslauf, der ohnehin einmal je Zyklus laeuft, unerheblich.
_CHUNK_DAYS = 1

# Historien-Beginn des Benzinga-Feeds. Alles davor ist leer - ein Test auf
# fruehere Zeitraeume liefert kein Signal, sondern nur eine leere Tabelle.
HISTORY_STARTS = "2015-01-01"


def news_client() -> NewsClient:
    s = get_settings()
    return NewsClient(s.api_key, s.secret_key)


def get_news(
    symbols: str | Sequence[str] | None = None,
    start: str | dt.datetime | None = None,
    end: str | dt.datetime | None = None,
    *,
    max_articles: int = 5_000,
    include_content: bool = False,
) -> pd.DataFrame:
    """Holt Nachrichten als DataFrame (paginiert, gedrosselt).

    Args:
        max_articles: harte Obergrenze. 5000 Artikel = 100 Requests = ca.
            30 Sekunden bei 200/min. Ohne Grenze laeuft eine Abfrage ueber
            5000 Symbole und 10 Jahre stundenlang.

    Returns:
        timestamp (UTC), symbols, headline, summary, source, author, url, id

    Zeitliche Aufteilung statt reiner next_page_token-Pagination: Bei
    breiten Abfragen (mehrere Symbole ueber Monate) liefert Alpacas
    News-Endpunkt `next_page_token=None` bereits nach der ERSTEN Seite,
    obwohl nachweislich mehr Artikel im angefragten Zeitraum existieren
    (bestaetigt 03.08.2026: eine 90-Tage/8-Symbol-Anfrage kam nach 50
    Artikeln zum Stillstand, obwohl allein AAPL im selben Fenster
    nachweislich hunderte hat - eine direkte Anfrage fuer einen frueheren
    Monat lieferte sofort aeltere Artikel). Ohne die Aufteilung waere der
    Nachrichtenfaktor fuer stark abgedeckte Werte auf ein paar Stunden am
    aktuellen Rand des Fensters verengt statt auf die angefragte Historie -
    und `news_z` damit faktisch bedeutungslos (60-Tage-Basismass braucht
    tatsaechlich verteilte Tage, nicht einen einzigen).
    """
    syms = [symbols] if isinstance(symbols, str) else (list(symbols) if symbols else None)

    end_ts = pd.Timestamp(end, tz="UTC") if end is not None else pd.Timestamp.now(tz="UTC")
    start_ts = (pd.Timestamp(start, tz="UTC") if start is not None
               else pd.Timestamp(HISTORY_STARTS, tz="UTC"))

    client = news_client()
    rows: list[dict] = []

    cursor_end = end_ts
    while cursor_end > start_ts and len(rows) < max_articles:
        cursor_start = max(start_ts, cursor_end - pd.Timedelta(days=_CHUNK_DAYS))
        page_token = None
        while len(rows) < max_articles:
            req = NewsRequest(
                symbols=",".join(syms) if syms else None,
                start=cursor_start,
                end=cursor_end,
                limit=min(_PAGE_SIZE, max_articles - len(rows)),
                include_content=include_content,
                exclude_contentless=True,
                page_token=page_token,
            )
            _limit.acquire()
            result = with_retry(lambda: client.get_news(req))

            items = _extract_items(result)
            if not items:
                break

            for a in items:
                rows.append(
                    {
                        "timestamp": getattr(a, "created_at", None),
                        "updated_at": getattr(a, "updated_at", None),
                        "symbols": list(getattr(a, "symbols", []) or []),
                        "headline": getattr(a, "headline", "") or "",
                        "summary": getattr(a, "summary", "") or "",
                        "source": getattr(a, "source", "") or "",
                        "author": getattr(a, "author", "") or "",
                        "url": getattr(a, "url", "") or "",
                        "id": getattr(a, "id", None),
                    }
                )

            page_token = getattr(result, "next_page_token", None)
            if not page_token:
                break
        # Ein Sekunde Abstand statt direkt an cursor_start anzuschliessen -
        # sonst koennte ein Artikel exakt auf der Grenze doppelt gezaehlt
        # werden (Fenster sind unten ueber "id" ohnehin dedupliziert, das
        # ist die zweite, nicht die einzige Verteidigung).
        cursor_end = cursor_start - pd.Timedelta(seconds=1)

    if not rows:
        return pd.DataFrame(
            columns=["timestamp", "updated_at", "symbols", "headline", "summary",
                     "source", "author", "url", "id"]
        )

    df = pd.DataFrame(rows)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.drop_duplicates(subset="id")
    return df.sort_values("timestamp").reset_index(drop=True)


def _extract_items(result) -> list:
    """alpaca-py liefert je nach Version NewsSet oder dict - beides abfangen."""
    if hasattr(result, "data") and isinstance(result.data, dict):
        return result.data.get("news", []) or []
    if isinstance(result, dict):
        return result.get("news", []) or []
    return list(result) if hasattr(result, "__iter__") else []


def explode_symbols(news: pd.DataFrame) -> pd.DataFrame:
    """Ein Artikel mit 5 Symbolen wird zu 5 Zeilen - fuer Aggregation je Aktie."""
    if news.empty:
        return news.assign(symbol=pd.Series(dtype=str))
    out = news.explode("symbols").rename(columns={"symbols": "symbol"})
    return out[out["symbol"].notna()].reset_index(drop=True)


def daily_counts(news: pd.DataFrame) -> pd.DataFrame:
    """Artikel je Symbol und Tag. Basis fuer die Frequenz-Anomalie."""
    if news.empty:
        return pd.DataFrame()
    long = explode_symbols(news)
    long["date"] = pd.DatetimeIndex(long["timestamp"]).tz_convert("UTC").normalize()
    counts = long.groupby(["date", "symbol"]).size().unstack(fill_value=0)
    return counts.sort_index()


def news_features(
    news: pd.DataFrame,
    price_index: pd.DatetimeIndex,
    symbol: str,
    *,
    delay: pd.Timedelta = pd.Timedelta("1D"),
) -> pd.DataFrame:
    """Zeitpunktsichere Nachrichten-Features auf dem Kurs-Zeitraster.

    Jeder Artikel wird um `delay` nach hinten verschoben, bevor er gezaehlt
    wird. Ein Artikel von Montag 15:47 wirkt damit fruehestens auf Dienstag -
    den ersten Zeitpunkt, an dem du tatsaechlich haettest handeln koennen.

    Features:
        news_1d/5d/20d   Artikelzahl in den letzten n Tagen
        news_z           Frequenz-Anomalie: 5-Tage-Zahl gegen 60-Tage-Normalmass
        days_since_news  Tage seit dem letzten Artikel
        first_coverage   1, wenn ueberhaupt zum ersten Mal berichtet wurde
    """
    idx = pd.DatetimeIndex(price_index)
    if idx.tz is None:
        idx = idx.tz_localize("UTC")
    else:
        # tz_convert statt Belassen: Kurs-Bars kommen ueber alpaca-py als
        # pydantic-Modelle zurueck, deren Zeitstempel ein eigenes
        # pydantic_core.TzInfo statt eines Standard-UTC-Objekts tragen.
        # pd.date_range() weiter unten vergleicht per tz_compare() gegen
        # das explizite tz="UTC" - inhaltsgleich, aber ein anderer Typ, und
        # das schlug mit "Inferred time zone not equal to passed time zone"
        # fehl (gefunden beim Testlauf gegen echte Alpaca-Bars, 03.08.2026).
        idx = idx.tz_convert("UTC")
    out = pd.DataFrame(index=price_index)

    if news.empty:
        for c in ("news_1d", "news_5d", "news_20d", "news_z", "first_coverage"):
            out[c] = 0.0
        out["days_since_news"] = np.nan
        return out

    long = explode_symbols(news)
    long = long[long["symbol"] == symbol]
    if long.empty:
        for c in ("news_1d", "news_5d", "news_20d", "news_z", "first_coverage"):
            out[c] = 0.0
        out["days_since_news"] = np.nan
        return out

    # HIER liegt die Zeitpunktsicherheit: Verfuegbarkeit = Veroeffentlichung + Verzug.
    available = pd.DatetimeIndex(long["timestamp"]) + delay
    per_day = pd.Series(1, index=available).resample("1D").sum()
    # .normalize() ist Pflicht: `resample("1D")` bindet per_day an Mitternacht
    # UTC, aber echte Kurs-Bars liegen praktisch nie dort (z. B. 04:00 UTC =
    # US-Boersenschluss). Ohne .normalize() haette date_range() unten JEDEN
    # Tag um idx.min()s Uhrzeit erzeugt statt um Mitternacht - der
    # nachfolgende reindex(..., fill_value=0) haette dann NIE eine
    # Uebereinstimmung gefunden und JEDEN echten Zaehlwert stillschweigend
    # auf 0 gesetzt (gefunden beim Testlauf gegen echte Alpaca-Bars,
    # 03.08.2026 - mit synthetischen, exakt mitternaechtlichen Testdaten war
    # der Fehler unsichtbar). Das spaetere `roll.reindex(idx, method="ffill")`
    # ordnet die mitternaechtlichen Tageswerte dann korrekt der jeweiligen
    # Bar-Uhrzeit zu.
    per_day = per_day.reindex(
        pd.date_range(min(per_day.index.min(), idx.min()).normalize(),
                     idx.max().normalize(), freq="1D", tz="UTC"),
        fill_value=0,
    )

    roll = pd.DataFrame(
        {
            "news_1d": per_day.rolling(1).sum(),
            "news_5d": per_day.rolling(5).sum(),
            "news_20d": per_day.rolling(20).sum(),
        }
    )
    base_mean = per_day.rolling(60, min_periods=20).mean() * 5
    base_std = per_day.rolling(60, min_periods=20).std() * np.sqrt(5)
    roll["news_z"] = (roll["news_5d"] - base_mean) / base_std.replace(0, np.nan)

    had_news = per_day.gt(0)
    last_news = pd.Series(
        np.where(had_news, np.arange(len(had_news)), np.nan), index=had_news.index
    ).ffill()
    roll["days_since_news"] = np.arange(len(had_news)) - last_news
    # Erst die beiden Wahrheitswerte verknuepfen, DANN in float wandeln.
    # Andersherum (float & bool) wirft TypeError - der Fehler blieb liegen,
    # weil dieses Modul bis 2026-07-29 von keiner Stelle aufgerufen wurde.
    roll["first_coverage"] = ((had_news.cumsum() == 1) & had_news).astype(float)

    aligned = roll.reindex(idx, method="ffill")
    aligned.index = price_index
    return aligned.fillna({"news_1d": 0, "news_5d": 0, "news_20d": 0,
                           "first_coverage": 0})
