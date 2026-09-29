"""GDELT: weltweite Nachrichtenintensitaet und -tonalitaet.

**Warum diese Quelle (25.08.2026).** Dritte Quelle ausserhalb der
Kursdaten, neben `edgar.py` (Insider) und `makro.py` (Regime). In
`ratelimit.QUOTAS` seit dem 28.07.2026 registriert, nie benutzt.

GDELT wertet weltweit Nachrichten aus und liefert zwei Groessen, die der
vorhandene Alpaca/Benzinga-Feed so nicht hat:

    AUFMERKSAMKEIT  Wie viele Artikel erscheinen ueberhaupt? Ein
                    ploetzlicher Anstieg ist Information, unabhaengig
                    davon, ob die Nachricht gut oder schlecht ist.
    TONALITAET      Wie positiv/negativ berichtet wird (Tone-Wert).

**Abgrenzung zum bestehenden Nachrichtenfaktor.** `ReversalWeights.news`
(Gewicht 0,10) benutzt den Alpaca/Benzinga-Feed. Der ist der einzige
Baustein des Live-Bots OHNE eigene Messung (`docs/BEFUNDE.md` §G24/§G25 -
"auf ausdruecklichen Wunsch direkt eingebaut, OHNE vorherige
Schattenbetrieb-Messung"). GDELT ist damit auch eine Moeglichkeit, jenen
Faktor erstmals gegen eine unabhaengige zweite Quelle zu halten.

**Zwei Betriebsarten, weil zwei verschiedene Tests noetig sind:**

    marktweit()     Ein Wert je Tag fuer den Gesamtmarkt.
                    -> Regimetest wie in `makro.regime_auswertung`,
                       NICHT Querschnitts-IC (eine Konstante sortiert
                       nichts - siehe Modulkopf von `makro.py`).
    je_symbol()     Artikelzahl und Ton je Symbol und Tag.
                    -> Querschnitts-IC, also die uebliche Pruefkette
                       aus `scripts/24_kandidaten_test.py`.

**Was `je_symbol()` teuer und rauschig macht - vorab, nicht hinterher.**
GDELT kennt keine Ticker, nur Text. Die Abfrage laeuft ueber den
Firmennamen, und der ist mehrdeutig ("Apple" die Frucht, "Target" das
Wort, "Gap" die Luecke). `FIRMENNAMEN` haelt deshalb nur Namen, die
eindeutig genug sind; fuer den Rest liefert die Funktion bewusst nichts
statt Rauschen. Ausserdem kostet jedes Symbol eine eigene Abfrage - bei
2.000 Symbolen ist das ein mehrtaegiger Lauf wie bei EDGAR.

**Zeitpunktsicherheit.** GDELT indiziert nach VEROEFFENTLICHUNGSzeit der
Artikel, es gibt keine Revisionen. Ein Wert vom 3. Maerz war am 3. Maerz
bekannt. Das ist der angenehme Unterschied zu Wirtschaftsstatistik
(`makro.REIHEN_REVIDIERT`) - hier droht kein Lookahead durch Revision,
nur durch falsche Fensterbildung, und dagegen hilft dieselbe Regel wie
ueberall: rollende Fenster, `ffill`, nie `bfill`.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json

import numpy as np
import pandas as pd

from .config import CACHE_DIR
from .ratelimit import RateLimiter, with_retry

_limit = RateLimiter("gdelt")

GDELT_CACHE = CACHE_DIR / "gdelt"
DOC_API = "https://api.gdeltproject.org/api/v2/doc/doc"

# GDELT DOC 2.0 reicht zurueck bis 2017 - frueher gibt es nichts.
FRUEHESTER_TAG = "2017-01-01"

MARKT_ABFRAGEN: dict[str, str] = {
    "marktstress": '("stock market" OR "wall street") '
                   '(crash OR selloff OR plunge OR turmoil)',
    "marktoptimismus": '("stock market" OR "wall street") '
                       '(rally OR surge OR record OR optimism)',
    "rezession": '"recession" (economy OR economic)',
}
"""Marktweite Abfragen. Bewusst wenige und breit - jede zusaetzliche
Abfrage ist ein weiterer Versuch im Sinne von §B2, und drei reichen, um
die Frage 'traegt Nachrichtenstimmung ueberhaupt' zu stellen."""

FIRMENNAMEN: dict[str, str] = {
    # Nur eindeutige Namen. Mehrdeutige (Apple, Target, Gap, Visa, Ford)
    # fehlen bewusst - lieber keine Beobachtung als eine falsche.
    "NVDA": "Nvidia", "MSFT": "Microsoft", "TSLA": "Tesla",
    "AMZN": "Amazon", "GOOGL": "Alphabet", "META": "Meta Platforms",
    "NFLX": "Netflix", "AMD": "AMD", "INTC": "Intel",
    "BA": "Boeing", "PFE": "Pfizer", "MRNA": "Moderna",
    "XOM": "Exxon Mobil", "CVX": "Chevron", "JPM": "JPMorgan",
    "GS": "Goldman Sachs", "WFC": "Wells Fargo", "COIN": "Coinbase",
}


def _cache_pfad(schluessel: str) -> "object":
    GDELT_CACHE.mkdir(parents=True, exist_ok=True)
    h = hashlib.sha256(schluessel.encode()).hexdigest()[:16]
    return GDELT_CACHE / f"{h}.json"


def _abfrage(query: str, start: str, ende: str) -> pd.DataFrame:
    """Eine GDELT-Zeitreihenabfrage: Artikel je Tag plus Durchschnittston.

    Ergebnis wird dauerhaft zwischengespeichert - historische Tage
    aendern sich nicht mehr, ein zweiter Lauf kostet nichts.
    """
    import requests

    schluessel = f"{query}|{start}|{ende}"
    pfad = _cache_pfad(schluessel)
    if pfad.exists():
        try:
            roh = json.loads(pfad.read_text())
        except json.JSONDecodeError:
            pfad.unlink(missing_ok=True)
            roh = None
        if roh is not None:
            return _als_frame(roh)

    def _hole():
        """`raise_for_status` gehoert INNERHALB des Retry-Lambdas.

        Stand ausserhalb, wie zuerst geschrieben: `requests.get` liefert
        bei HTTP 429 ganz normal ein Response-Objekt zurueck, ohne zu
        werfen. `with_retry` sah also einen Erfolg, gab die Antwort
        heraus - und erst danach warf `raise_for_status`. Der Backoff,
        der genau fuer 429 gebaut ist, lief nie an. Gemessen am
        25.08.2026: drei GDELT-Abfragen in Folge, alle 429, kein
        einziger Wiederholungsversuch.
        """
        r = requests.get(
            DOC_API,
            params={
                "query": query, "mode": "timelinetone", "format": "json",
                "startdatetime": f"{start.replace('-', '')}000000",
                "enddatetime": f"{ende.replace('-', '')}235959",
            },
            headers={"User-Agent": "alpaca-bot research (contact via SEC_USER_AGENT)"},
            timeout=60,
        )
        r.raise_for_status()
        return r

    _limit.acquire()
    # `base_delay=8`: GDELTs eigene Fehlermeldung nennt "one every 5
    # seconds". Die Vorgabe 2s waere die erste Wiederholung schon zu
    # frueh und wuerde das Limit nur erneut reissen.
    resp = with_retry(_hole, base_delay=8.0)
    try:
        roh = resp.json()
    except ValueError:
        # GDELT antwortet bei Fehlern gelegentlich mit HTML statt JSON.
        return pd.DataFrame(columns=["tag", "ton", "artikel"])

    pfad.write_text(json.dumps(roh))
    return _als_frame(roh)


def _als_frame(roh: dict) -> pd.DataFrame:
    """GDELTs Zeitreihenformat in eine Tabelle mit Tag und Ton.

    **Nur Ton, keine Artikelzahl - und das ist Absicht.** Der Modus
    `timelinetone` liefert ausschliesslich Tonwerte; ein Feld `norm`
    (Artikelzahl) gibt es dort nicht. Die erste Fassung dieses Moduls
    legte trotzdem eine Spalte `artikel` an und fuellte sie mit `NaN` -
    also genau ein stummes Feld, wie es `docs/BEFUNDE.md` §G13 als
    eigene Fehlerklasse fuehrt: Es sieht nach einer Messgroesse aus,
    enthaelt aber nie eine. Gemessen am 25.08.2026: 923 von 923 Tagen
    leer.

    Wer die Artikelzahl braucht, muss `mode=timelinevol` abfragen - eine
    ZWEITE Abfrage je Reihe. Bei GDELTs Limit (1 Anfrage je 5 Sekunden)
    ist das eine bewusste Entscheidung, keine Kleinigkeit, und sie wird
    getroffen, wenn der Ton allein etwas zeigt.
    """
    reihen = roh.get("timeline", []) if isinstance(roh, dict) else []
    if not reihen:
        return pd.DataFrame(columns=["tag", "ton"])

    punkte = reihen[0].get("data", [])
    if not punkte:
        return pd.DataFrame(columns=["tag", "ton"])

    df = pd.DataFrame(punkte)
    if "date" not in df:
        return pd.DataFrame(columns=["tag", "ton"])

    df["tag"] = pd.to_datetime(df["date"], format="mixed",
                               errors="coerce").dt.tz_localize(None).dt.normalize()
    df["ton"] = pd.to_numeric(df.get("value"), errors="coerce")
    return df[["tag", "ton"]].dropna(subset=["tag"]).sort_values("tag")


def marktweit(start: str = FRUEHESTER_TAG, ende: str | None = None,
              abfragen: dict[str, str] | None = None,
              verbose: bool = True) -> pd.DataFrame:
    """Marktweite Nachrichtenintensitaet und -tonalitaet je Tag.

    Returns: Zeilen = Tage, Spalten = `<name>_ton` und `<name>_artikel`.
    """
    ende = ende or dt.date.today().isoformat()
    abfragen = abfragen or MARKT_ABFRAGEN
    spalten: dict[str, pd.Series] = {}

    for name, query in abfragen.items():
        try:
            df = _abfrage(query, start, ende)
        except Exception as e:  # noqa: BLE001 - eine Abfrage darf nicht alles kippen
            if verbose:
                print(f"    {name:<18} Fehler ({type(e).__name__})")
            continue
        if df.empty:
            if verbose:
                print(f"    {name:<18} keine Daten")
            continue
        df = df.set_index("tag")
        spalten[f"{name}_ton"] = df["ton"]
        if verbose:
            print(f"    {name:<18} {len(df):>5} Tage  "
                  f"{df.index.min().date()} - {df.index.max().date()}")

    return pd.DataFrame(spalten).sort_index() if spalten else pd.DataFrame()


def je_symbol(symbole: list[str], start: str = FRUEHESTER_TAG,
              ende: str | None = None, verbose: bool = True) -> dict[str, pd.DataFrame]:
    """Artikelzahl und Ton je Symbol - nur fuer eindeutige Firmennamen.

    Symbole ohne Eintrag in `FIRMENNAMEN` werden uebersprungen, nicht
    geraten. Ein mehrdeutiger Name ("Target", "Gap") wuerde Artikel
    zaehlen, die nichts mit der Firma zu tun haben - das waere kein
    schwaches Signal, sondern ein falsches.
    """
    ende = ende or dt.date.today().isoformat()
    out: dict[str, pd.DataFrame] = {}
    unbekannt = []

    for sym in symbole:
        name = FIRMENNAMEN.get(sym.upper())
        if not name:
            unbekannt.append(sym)
            continue
        try:
            df = _abfrage(f'"{name}"', start, ende)
        except Exception as e:  # noqa: BLE001
            if verbose:
                print(f"    {sym:<8} Fehler ({type(e).__name__})")
            continue
        if not df.empty:
            out[sym.upper()] = df.set_index("tag")
            if verbose:
                print(f"    {sym:<8} {len(df):>5} Tage")

    if verbose and unbekannt:
        print(f"    {len(unbekannt)} Symbole ohne eindeutigen Firmennamen "
              f"uebersprungen (siehe FIRMENNAMEN)")
    return out


def merkmale(roh: pd.DataFrame, kalender: pd.DatetimeIndex | None = None
             ) -> pd.DataFrame:
    """Zeitpunktsichere Merkmale aus den Rohreihen.

    Wie in `makro.regime_merkmale`: ausschliesslich rollende
    Rueckwaerts-Fenster und `ffill`. Der Pegel der Artikelzahl ist fuer
    sich wenig aussagekraeftig (GDELTs Abdeckung waechst ueber die
    Jahre), die ABWEICHUNG vom eigenen Mittel dagegen schon - deshalb
    wird alles als z-Wert bzw. Perzentil gegen die eigene Vergangenheit
    gerechnet, nie als Rohwert.
    """
    out = pd.DataFrame(index=roh.index)
    for spalte in roh.columns:
        s = pd.to_numeric(roh[spalte], errors="coerce")
        mittel = s.rolling(252, min_periods=30).mean()
        streuung = s.rolling(252, min_periods=30).std()
        out[f"{spalte}_z"] = (s - mittel) / streuung.replace(0, np.nan)
        out[f"{spalte}_perzentil"] = s.rolling(252, min_periods=30).rank(pct=True)

    if kalender is not None:
        out = out.reindex(out.index.union(kalender)).ffill().reindex(kalender)
    return out.replace([np.inf, -np.inf], np.nan)


def beschreibung() -> dict[str, str]:
    return {
        "marktstress": "Artikel ueber Crash/Selloff/Turmoil - Panikmass "
                       "aus Nachrichten statt aus Kursen",
        "marktoptimismus": "Artikel ueber Rally/Rekord - Gegenstueck",
        "rezession": "Rezessionsberichterstattung - dreht oft vor "
                     "den Wirtschaftsdaten selbst",
    }
