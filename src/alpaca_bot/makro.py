"""Makro-Regimedaten: FRED (St. Louis Fed) und marktbasierte Ersatzreihen.

**Warum eine eigene Datenquelle (25.08.2026).** `docs/BEFUNDE.md` §C haelt
fest, dass der Faktorraum aus Kurs- und Volumendaten vermutlich
ausgeschoepft ist - 18 Kandidaten, alle durchgefallen, die auffaelligen
entpuppten sich als der bereits gehandelte Umkehr-Effekt. Neue Information
muss von AUSSERHALB kommen. Makrodaten sind neben EDGAR (`edgar.py`) die
zweite solche Quelle, die im Projekt registriert (`ratelimit.QUOTAS`),
aber nie benutzt wurde.

**Der entscheidende Unterschied zu allen bisherigen Faktoren - bitte
zuerst lesen, sonst wird der Test falsch gebaut.** Ein Makrowert ist an
einem Tag fuer ALLE Symbole gleich. Der Querschnitts-IC (`research.
_daily_cross_sectional_ic`), mit dem dieses Projekt jeden Faktor prueft,
ist damit strukturell **nicht anwendbar**: Er misst, ob ein Faktor die
Symbole eines Tages richtig sortiert - eine Konstante sortiert nichts.

Makrodaten koennen deshalb nur auf drei Arten wirken:

    1. REGIME    Wann funktioniert die Strategie, wann nicht?
                 -> `regime_auswertung()`, geprueft auf der Tagesrendite
    2. INTERAKTION  Makro x Symboleigenschaft (z. B. Beta x Zinsaenderung)
                 -> ergibt Querschnittsvariation, dann IC-testbar
    3. TIMING    Marktweiter Ein-/Ausstieg
                 -> ersetzt/ergaenzt den groben SPY>SMA200-Filter (§G7)

Weg 1 ist der interessanteste, weil er eine bereits belegte Luecke
trifft: §G7 zeigt, dass der heutige Regimefilter das GESAMTE Depot in
einem Zyklus liquidiert, wenn SPY unter seinen 200-Tage-Schnitt faellt -
ein Nebeneffekt, kein Entwurf. §G8 beziffert, dass das 18 % aller
Handelstage betrifft.

**Die Revisionsfalle - der Grund, warum die Reihenauswahl hier nicht
beliebig ist.** `pit.py` warnt bereits: Makro-Erstveroeffentlichungen
werden spaeter revidiert. Wer heutige FRED-Werte auf historische Tage
legt, benutzt Zahlen, die es damals so nicht gab - ein Lookahead-Fehler,
der ein Ergebnis traumhaft aussehen laesst und wertlos ist.

Deshalb sind die Reihen hier in zwei Klassen geteilt:

    REIHEN_OHNE_REVISION   Marktpreise (VIX, Zinsen, Spreads). Sie werden
                           NIE revidiert - der Schlusskurs von gestern
                           bleibt der Schlusskurs von gestern.
    REIHEN_REVIDIERT       Wirtschaftsstatistik (BIP, Arbeitsmarkt, CPI).
                           NUR ueber ALFRED-Vintages zeitpunktsicher.
                           Hier bewusst NICHT eingebaut - lieber keine
                           Reihe als eine, die still in die Zukunft sieht.

**Kein API-Schluessel noetig.** FRED verlangt einen (kostenlosen)
Schluessel. Die marktbasierten Reihen gibt es aber auch ueber yfinance,
und genau die sind die revisionsfreien. `lade_reihen()` nimmt FRED, wenn
`FRED_API_KEY` gesetzt ist, und faellt sonst auf yfinance zurueck - ohne
dass sich am Ergebnis etwas aendert.
"""

from __future__ import annotations

import datetime as dt
import os

import numpy as np
import pandas as pd

from .config import CACHE_DIR
from .ratelimit import RateLimiter, with_retry

_limit = RateLimiter("fred")

MAKRO_CACHE = CACHE_DIR / "makro"

# ---------------------------------------------------------------------------
# Reihenauswahl
# ---------------------------------------------------------------------------
REIHEN_OHNE_REVISION: dict[str, dict] = {
    # Schluessel = unser Name. `fred` = FRED-Kuerzel, `yf` = yfinance-Ersatz.
    "vix": {
        "fred": "VIXCLS", "yf": "^VIX",
        "was": "Erwartete 30-Tage-Schwankung des S&P 500 (Angstbarometer)",
        "warum": "Umkehr-Strategien kaufen Gefallenes. Ob das traegt, "
                 "haengt plausibel davon ab, ob der Markt panisch ist "
                 "(Ueberreaktion, gute Umkehrchance) oder ruhig faellt "
                 "(echte Neubewertung, schlechte).",
    },
    "zins_10j": {
        "fred": "DGS10", "yf": "^TNX",
        "was": "Rendite 10-jaehriger US-Staatsanleihen",
        "warum": "Zinsniveau und -aenderung treiben Bewertungsniveaus; "
                 "steigende Zinsen treffen zinssensitive Werte staerker.",
    },
    "zins_3m": {
        "fred": "DGS3MO", "yf": "^IRX",
        "was": "Rendite 3-monatiger US-Staatsanleihen",
        "warum": "Kurzes Ende - zusammen mit dem langen ergibt es die "
                 "Zinsstruktur.",
    },
    "hy_spread": {
        "fred": "BAMLH0A0HYM2", "yf": None,
        "was": "Risikoaufschlag von Hochzinsanleihen (Credit Spread)",
        "warum": "Der klassische Stressindikator. Er dreht oft FRUEHER "
                 "als Aktien und ist damit ein Kandidat fuer einen "
                 "besseren Regimefilter als SPY>SMA200 (§G7).",
    },
}
"""Reihen, die NICHT revidiert werden - Marktpreise. Nur diese sind ohne
ALFRED-Vintages zeitpunktsicher."""

REIHEN_REVIDIERT: dict[str, str] = {
    "arbeitslosenquote": "UNRATE",
    "cpi": "CPIAUCSL",
    "bip": "GDPC1",
    "industrieproduktion": "INDPRO",
}
"""Bewusst NICHT geladen. Diese Reihen werden nach Erstveroeffentlichung
revidiert; die heutigen Werte auf historische Tage zu legen waere
Lookahead. Zeitpunktsicher nur ueber ALFRED-Vintages (`realtime_start`/
`realtime_end` der FRED-API) - das ist ein eigener Ausbau, kein Nebenbei.
Steht hier, damit die naechste Sitzung nicht denkt, sie seien vergessen
worden."""


# ---------------------------------------------------------------------------
# Beschaffung
# ---------------------------------------------------------------------------
def _fred_key() -> str | None:
    k = os.getenv("FRED_API_KEY", "").strip()
    return k if k and "<" not in k else None


def _von_fred(kuerzel: str, seit: str) -> pd.Series:
    """Eine Reihe von der FRED-API. Braucht `FRED_API_KEY`."""
    import requests

    key = _fred_key()
    if not key:
        raise RuntimeError("FRED_API_KEY fehlt")

    def _hole():
        # `raise_for_status` INNERHALB des Lambdas - sonst sieht
        # `with_retry` bei HTTP 429/503 einen Erfolg und der Backoff
        # laeuft nie an (derselbe Fehler wie in `gdelt.py`, dort am
        # 25.08.2026 an echten 429ern aufgefallen).
        r = requests.get(
            "https://api.stlouisfed.org/fred/series/observations",
            params={"series_id": kuerzel, "api_key": key, "file_type": "json",
                    "observation_start": seit},
            timeout=30,
        )
        r.raise_for_status()
        return r

    _limit.acquire()
    resp = with_retry(_hole)
    beob = resp.json().get("observations", [])
    if not beob:
        return pd.Series(dtype=float)

    df = pd.DataFrame(beob)
    werte = pd.to_numeric(df["value"], errors="coerce")   # "." = fehlend
    s = pd.Series(werte.values, index=pd.to_datetime(df["date"]), name=kuerzel)
    return s.dropna()


def _von_yfinance(kuerzel: str, seit: str) -> pd.Series:
    """Marktbasierter Ersatz ueber yfinance - kein Schluessel noetig.

    Nur fuer die revisionsfreien Reihen sinnvoll (Marktpreise). Fuer
    Wirtschaftsstatistik gibt es hier keinen Ersatz, und das ist auch
    richtig so - siehe `REIHEN_REVIDIERT`.
    """
    from .datasources import get_history

    bars = get_history([kuerzel], years=_jahre_seit(seit), source="yfinance",
                       use_cache=True, verbose=False)
    if bars.empty:
        return pd.Series(dtype=float)
    s = bars.xs(kuerzel, level="symbol")["close"].astype(float)
    s.index = pd.DatetimeIndex(s.index).tz_localize(None).normalize()
    return s[~s.index.duplicated(keep="last")].rename(kuerzel)


def _jahre_seit(seit: str) -> float:
    tage = (dt.date.today() - dt.date.fromisoformat(seit)).days
    return max(tage / 365.25, 1.0)


def lade_reihen(namen: list[str] | None = None, seit: str = "2010-01-01",
                verbose: bool = True) -> pd.DataFrame:
    """Alle revisionsfreien Makroreihen als Tabelle (Zeilen = Tage).

    Nimmt FRED, wenn `FRED_API_KEY` gesetzt ist, sonst den yfinance-
    Ersatz. Reihen ohne Ersatz (etwa `hy_spread`) fehlen dann - das wird
    gemeldet, nicht verschwiegen.
    """
    MAKRO_CACHE.mkdir(parents=True, exist_ok=True)
    namen = namen or list(REIHEN_OHNE_REVISION)
    hat_key = _fred_key() is not None
    if verbose:
        quelle = "FRED" if hat_key else "yfinance-Ersatz (kein FRED_API_KEY)"
        print(f"  Makroreihen ueber {quelle}")

    spalten: dict[str, pd.Series] = {}
    for name in namen:
        cfg = REIHEN_OHNE_REVISION.get(name)
        if cfg is None:
            continue
        cache = MAKRO_CACHE / f"{name}_{seit}_{dt.date.today().isoformat()}.parquet"
        if cache.exists():
            spalten[name] = pd.read_parquet(cache)[name]
            if verbose:
                print(f"    {name:<16} aus Tages-Cache")
            continue

        s = pd.Series(dtype=float)
        if hat_key and cfg["fred"]:
            try:
                s = _von_fred(cfg["fred"], seit)
            except Exception as e:  # noqa: BLE001 - Ausfall einer Reihe kippt nicht alles
                if verbose:
                    print(f"    {name:<16} FRED-Fehler ({type(e).__name__}), "
                          f"versuche Ersatz")
        if s.empty and cfg["yf"]:
            try:
                s = _von_yfinance(cfg["yf"], seit)
            except Exception as e:  # noqa: BLE001
                if verbose:
                    print(f"    {name:<16} auch Ersatz fehlgeschlagen "
                          f"({type(e).__name__})")
        if s.empty:
            if verbose:
                print(f"    {name:<16} NICHT VERFUEGBAR"
                      + ("" if cfg["yf"] else " (nur ueber FRED, Schluessel fehlt)"))
            continue

        s.index = pd.DatetimeIndex(s.index).tz_localize(None).normalize()
        spalten[name] = s
        pd.DataFrame({name: s}).to_parquet(cache)
        if verbose:
            print(f"    {name:<16} {len(s):>6} Werte  "
                  f"{s.index.min().date()} - {s.index.max().date()}")

    if not spalten:
        return pd.DataFrame()
    return pd.DataFrame(spalten).sort_index()


# ---------------------------------------------------------------------------
# Merkmale
# ---------------------------------------------------------------------------
def regime_merkmale(reihen: pd.DataFrame, kalender: pd.DatetimeIndex | None = None
                    ) -> pd.DataFrame:
    """Aus den Rohreihen zeitpunktsichere Regimemerkmale bauen.

    **Jedes Merkmal benutzt ausschliesslich Werte BIS zum jeweiligen Tag.**
    Rollende Fenster, keine zentrierten; `ffill`, nie `bfill`. Ein
    `bfill` waere genau das Leck, das `pit.audit_feature_function` sucht.

    Merkmale:
        vix_niveau        VIX-Perzentil im 2-Jahres-Rueckblick (0-1)
        vix_aenderung_5d  Veraenderung ueber 5 Handelstage
        zinsstruktur      10J minus 3M (invers = Rezessionssignal)
        zins_aenderung_20d  Veraenderung der 10-Jahres-Rendite
        hy_niveau         Credit-Spread-Perzentil, 2-Jahres-Rueckblick
        hy_aenderung_20d  Ausweitung/Verengung ueber 20 Tage
    """
    out = pd.DataFrame(index=reihen.index)

    if "vix" in reihen:
        v = reihen["vix"]
        # 504 Handelstage ~ 2 Jahre. `rolling` schaut nur zurueck.
        out["vix_niveau"] = v.rolling(504, min_periods=60).rank(pct=True)
        out["vix_aenderung_5d"] = v.pct_change(5)

    if {"zins_10j", "zins_3m"}.issubset(reihen.columns):
        out["zinsstruktur"] = reihen["zins_10j"] - reihen["zins_3m"]
    if "zins_10j" in reihen:
        out["zins_aenderung_20d"] = reihen["zins_10j"].diff(20)

    if "hy_spread" in reihen:
        h = reihen["hy_spread"]
        out["hy_niveau"] = h.rolling(504, min_periods=60).rank(pct=True)
        out["hy_aenderung_20d"] = h.diff(20)

    if kalender is not None:
        # ffill: der letzte VERFUEGBARE Wert gilt weiter. Niemals bfill -
        # das wuerde einen Wert von morgen auf heute legen.
        out = out.reindex(out.index.union(kalender)).ffill().reindex(kalender)
    return out


def regime_auswertung(tagesrendite: pd.Series, merkmal: pd.Series,
                      n_baender: int = 4, horizont: int = 1,
                      lag: int = 1) -> pd.DataFrame:
    """Haengt die Tagesrendite der Strategie am Makroregime des VORTAGS?

    **Das ist der Test, der fuer Makrodaten passt** - nicht der
    Querschnitts-IC (siehe Modulkopf: ein Makrowert ist an einem Tag fuer
    alle Symbole gleich und sortiert deshalb nichts).

    **`lag=1` ist der wichtigste Parameter dieser Funktion, und die
    Vorgabe ist bewusst nicht 0** (gefunden am 25.08.2026 beim ersten
    Lauf, bevor die Zahlen als Befund notiert wurden):

    Ohne Versatz vergleicht man das Merkmal von Tag t mit der Rendite von
    Tag t. Fuer ein Marktmass ist das eine **Tautologie, kein Befund**:
    Ein steigender VIX IST ein fallender Markt, und ein Long-Depot
    verliert an fallenden Tagen. Der erste Lauf lieferte so
    `vix_aenderung_5d` mit t = +4,79 im besten und t = -5,31 im
    schlechtesten Band ueber 2.008 Handelstage - eine spektakulaer
    aussehende Zahl, die nur sagt: "wenn der Markt faellt, verlieren
    wir". Handelbar ist das nicht, weil die VIX-Aenderung des Tages erst
    am Ende des Tages feststeht.

    Mit `lag=1` steht das Merkmal am VORTAGESSCHLUSS fest und die
    Rendite wird am Folgetag gemessen. Nur so beantwortet der Test die
    Frage, auf die es ankommt: *Haette man es vorher wissen koennen?*

    Args:
        tagesrendite: Rendite der Strategie je Handelstag.
        merkmal: das Regimemerkmal, auf denselben Kalender gebracht.
        n_baender: in wie viele Regimeklassen geteilt wird.
        lag: um wie viele Handelstage das Merkmal zurueckversetzt wird.
            1 = das Merkmal war am Vortag bekannt (Vorgabe, handelbar).
            0 = gleichzeitig; nur zum Vorfuehren der Tautologie oben,
            nie als Befund.

    Returns: je Band Anzahl Tage, mittlere Rendite, t-Wert gegen null.
    """
    from . import statistik

    if lag:
        merkmal = merkmal.shift(lag)
    df = pd.DataFrame({"r": tagesrendite, "m": merkmal}).dropna()
    if len(df) < n_baender * 20:
        return pd.DataFrame()

    try:
        df["band"] = pd.qcut(df["m"], n_baender, duplicates="drop")
    except ValueError:
        return pd.DataFrame()

    zeilen = []
    for band, g in df.groupby("band", observed=True):
        # Jeder Tag ist EINE Beobachtung; als Gruppe dient der Monat,
        # damit benachbarte Tage nicht als unabhaengig gezaehlt werden.
        r = statistik.gruppierter_test(
            g["r"], pd.Series(g.index.to_period("M").astype(str), index=g.index),
            min_gruppen=6, horizont=horizont)
        zeilen.append({
            "band": str(band), "n_tage": len(g),
            "mittel": round(float(g["r"].mean()), 6),
            "t": round(float(r.t), 2) if np.isfinite(r.t) else np.nan,
            "n_monate": r.n_gruppen,
            "anteil_positiv": round(float((g["r"] > 0).mean()), 3),
        })
    return pd.DataFrame(zeilen)


def beschreibung() -> dict[str, str]:
    """Was jede Reihe misst und warum sie hier steht - fuer den Bericht."""
    return {name: f"{cfg['was']} | {cfg['warum']}"
            for name, cfg in REIHEN_OHNE_REVISION.items()}
