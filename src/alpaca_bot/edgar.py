"""SEC EDGAR: Insidergeschaefte aus Form 4 - die beste freie Signalquelle.

Warum ausgerechnet diese Quelle:

  * **Zeitpunktgenau.** Form 4 muss binnen 2 Werktagen nach dem Geschaeft
    eingereicht werden, und EDGAR speichert den Einreichungszeitpunkt
    sekundengenau. Es gibt hier keine Revisionen und keine nachtraeglich
    geglaetteten Zahlen - anders als bei Fundamentaldaten.
  * **Keine Survivorship-Luecke.** Auch Firmen, die es heute nicht mehr
    gibt, haben ihre Meldungen im Archiv. Das ist bei fast keiner anderen
    freien Quelle so.
  * **Belegt wirksam.** Geclusterte Insiderkaeufe gehoeren zu den wenigen
    Effekten, die bei kleineren, wenig beachteten Werten sogar STAERKER
    sind als bei Standardwerten.
  * **Kostenlos, ohne Schluessel.** Nur ein User-Agent mit Kontaktangabe
    ist Pflicht - ohne kommt HTTP 403.

Wichtig bei der Auswertung: Nur **Transaktionscode P** (Kauf am offenen
Markt) traegt Information. Optionsausuebungen (M), Zuteilungen (A) und
Plan-Verkaeufe (S mit 10b5-1) sagen wenig bis nichts. Verkaeufe generell
sind kaum aussagekraeftig - Insider verkaufen fuer ein Haus, eine
Scheidung oder zur Diversifikation. Gekauft wird aus genau einem Grund.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pandas as pd
import requests

from .config import CACHE_DIR, PROJECT_ROOT
from .ratelimit import RateLimiter, with_retry

_limit = RateLimiter("sec_edgar")

EDGAR_CACHE = CACHE_DIR / "edgar"
EDGAR_CACHE.mkdir(parents=True, exist_ok=True)

_SESSION = requests.Session()
"""Eine wiederverwendete Verbindung statt einer neuen je Abruf (§G46).

**Der eigentliche Grund fuer den Absturz vom 26./27.08.2026 - nicht das
geschlossene Terminal.** Jeder Aufruf ging bis dahin ueber
`requests.get(...)`, also einen frischen TCP+TLS-Handshake JE REQUEST.
Ein Symbol mit 900 Meldungen kostet ~1.800 Requests (2 je Einreichung) -
also 1.800 neue Verbindungen statt einer wiederverwendeten.

Gemessen im Log: durchschnittlich 320-330s je Symbol bei staendigen
`ReadTimeout`-Wiederholungen, hochgerechnet ~7-8 Tage fuer 2.168 Symbole.
Mit `Session()` (Keep-Alive, Connection-Pooling) sinkt der
Verbindungsaufwand auf einen Bruchteil - derselbe Mechanismus, den jeder
Browser und jede professionelle EDGAR-Anbindung nutzt."""

_ADAPTER = requests.adapters.HTTPAdapter(pool_connections=4, pool_maxsize=16)
_SESSION.mount("https://", _ADAPTER)

PARALLEL_FILINGS = 8
"""Gleichzeitige Filing-Abrufe in `insider_trades()` (§G47).

Erhoeht NICHT die erlaubte Rate - `RateLimiter("sec_edgar")` laesst
weiterhin nur 9 Requests/Sekunde durch, egal aus wie vielen Threads.
Der Wert ist bewusst kleiner als `pool_maxsize`: Ein Filing braucht ZWEI
Requests nacheinander (Verzeichnis, dann XML), ein Thread haelt seine
Verbindung also laenger als einen einzelnen Request."""

# Kaufcodes, die tatsaechlich Information tragen.
MEANINGFUL_BUY_CODES = {"P"}
# Codes, die haeufig als "Kauf" fehlinterpretiert werden, es aber nicht sind.
NOISE_CODES = {"A", "M", "G", "F", "C", "J"}


class EdgarError(RuntimeError):
    """EDGAR-Zugriff fehlgeschlagen."""


class ZuVieleMeldungen(EdgarError):
    """Ein Symbol hat mehr Form-4-Meldungen als die gesetzte Grenze.

    **Warum das eine Ausnahme ist und kein stilles Abschneiden** (§G41).
    Bis zum 26.08.2026 schnitt `insider_trades` bei Ueberschreitung
    einfach ab - mit `f.tail(max_filings)`, also den NEUESTEN N. Das
    Ergebnis war ein Panel, das in den frueheren Jahren praktisch leer
    und in den spaeteren voll war: Bei `max_filings=150` und einem
    Median von 436 Meldungen je Symbol fehlten dem mittleren Symbol
    zwei Drittel seiner Historie, immer die aeltere Haelfte.

    Gemessen am laufenden Kandidatentest: von 344 Symbolen mit
    ueberhaupt einem Insiderkauf begannen 13 vor 2022 und 314 ab 2023.
    Die Jahresstabilitaetspruefung haette dann Jahre bewertet, in denen
    zwei Symbole Daten haben - und den Faktor aus einem Grund verworfen,
    der nichts mit Insiderhandel zu tun hat.

    Ein Symbol, dessen Historie nicht vollstaendig geladen werden kann,
    gehoert deshalb AUSGESCHLOSSEN, nicht halbiert. Der Aufrufer muss
    das entscheiden und zaehlen - darum eine Ausnahme statt einer
    stillen Kuerzung.
    """


def _user_agent() -> str:
    """Pflicht-Header der SEC: Name und Kontakt-E-Mail.

    Ohne diesen Header antwortet EDGAR mit 403. Die SEC verlangt eine
    echte Kontaktmoeglichkeit, damit sie sich bei auffaelligem
    Datenverkehr melden kann.
    """
    import os

    ua = os.getenv("SEC_USER_AGENT", "").strip()
    if not ua or "<" in ua or "@" not in ua:
        raise EdgarError(
            "SEC_USER_AGENT fehlt oder ist ein Platzhalter.\n"
            f"  -> In {PROJECT_ROOT / '.env'} eintragen, Format:\n"
            "     SEC_USER_AGENT=Dein Name dein@email.de\n"
            "  Die SEC verlangt eine echte Kontaktangabe, sonst kommt 403."
        )
    return ua


def _get(url: str, *, as_json: bool = True, cache_key: str | None = None):
    """Gedrosselter EDGAR-Abruf mit Plattencache.

    Historische Einreichungen aendern sich nie - einmal geladen, koennen
    sie dauerhaft aus dem Cache kommen. Das spart bei einem Lauf ueber
    viele Symbole zehntausende Requests.
    """
    cache_file = EDGAR_CACHE / f"{cache_key}.json" if cache_key else None
    if cache_file and cache_file.exists():
        try:
            return json.loads(cache_file.read_text())
        except json.JSONDecodeError:
            cache_file.unlink(missing_ok=True)

    _limit.acquire()
    resp = with_retry(
        lambda: _SESSION.get(
            url,
            headers={
                "User-Agent": _user_agent(),
                "Accept-Encoding": "gzip, deflate",
            },
            timeout=30,
        )
    )
    if resp.status_code == 403:
        raise EdgarError(
            "EDGAR antwortet 403. Fast immer ein fehlender oder unplausibler "
            f"User-Agent. Aktuell gesetzt: {_user_agent()!r}"
        )
    resp.raise_for_status()

    data = resp.json() if as_json else resp.text
    if cache_file:
        cache_file.write_text(json.dumps(data) if as_json else json.dumps({"_text": data}))
    return data


# ---------------------------------------------------------------------------
# Ticker -> CIK
# ---------------------------------------------------------------------------
def ticker_map(refresh: bool = False) -> dict[str, str]:
    """Zuordnung Boersenkuerzel -> CIK (die EDGAR-Firmennummer)."""
    path = EDGAR_CACHE / "company_tickers.json"
    if refresh or not path.exists():
        _limit.acquire()
        resp = with_retry(
            lambda: _SESSION.get(
                "https://www.sec.gov/files/company_tickers.json",
                headers={"User-Agent": _user_agent()},
                timeout=30,
            )
        )
        resp.raise_for_status()
        path.write_text(resp.text)

    raw = json.loads(path.read_text())
    return {
        row["ticker"].upper(): str(row["cik_str"]).zfill(10)
        for row in raw.values()
    }


def cik_for(ticker: str) -> str | None:
    return ticker_map().get(ticker.upper())


# ---------------------------------------------------------------------------
# Form-4-Einreichungen finden
# ---------------------------------------------------------------------------
def filings(ticker: str, form: str = "4", since: str | None = None) -> pd.DataFrame:
    """Alle Einreichungen eines Typs fuer ein Symbol.

    Returns: form, filing_date (= Verfuegbarkeitszeitpunkt!), accession, url
    """
    cik = cik_for(ticker)
    if cik is None:
        return pd.DataFrame(columns=["form", "filing_date", "accession", "url"])

    data = _get(
        f"https://data.sec.gov/submissions/CIK{cik}.json",
        cache_key=f"submissions_{cik}",
    )
    frames = [pd.DataFrame(data.get("filings", {}).get("recent", {}))]

    # Aeltere Einreichungen liegen in ausgelagerten Zusatzdateien.
    for extra in data.get("filings", {}).get("files", []):
        name = extra.get("name")
        if not name:
            continue
        try:
            older = _get(
                f"https://data.sec.gov/submissions/{name}",
                cache_key=f"submissions_{cik}_{name.replace('.json', '')}",
            )
            frames.append(pd.DataFrame(older))
        except Exception:  # noqa: BLE001 - eine fehlende Altdatei darf nicht alles kippen
            continue

    df = pd.concat(frames, ignore_index=True)
    if df.empty or "form" not in df.columns:
        return pd.DataFrame(columns=["form", "filing_date", "accession", "url"])

    df = df[df["form"] == form].copy()
    if df.empty:
        return pd.DataFrame(columns=["form", "filing_date", "accession", "url"])

    df["filing_date"] = pd.to_datetime(df["filingDate"], utc=True)
    if since:
        df = df[df["filing_date"] >= pd.Timestamp(since, tz="UTC")]

    cik_plain = str(int(cik))
    df["accession"] = df["accessionNumber"].str.replace("-", "", regex=False)
    df["url"] = (
        "https://www.sec.gov/Archives/edgar/data/"
        + cik_plain + "/" + df["accession"] + "/" + df["accessionNumber"] + "-index.htm"
    )
    df["cik"] = cik_plain
    df["ticker"] = ticker.upper()
    return df[["ticker", "cik", "form", "filing_date", "accession",
               "accessionNumber", "url"]].sort_values("filing_date")


# ---------------------------------------------------------------------------
# Form 4 im Detail
# ---------------------------------------------------------------------------
@dataclass
class InsiderTrade:
    ticker: str
    filing_date: pd.Timestamp
    """Wann die Meldung oeffentlich wurde - DAS ist der Zeitpunkt, ab dem
    du davon wissen konntest."""
    transaction_date: pd.Timestamp | None
    owner: str
    is_officer: bool
    is_director: bool
    code: str
    shares: float
    price: float
    value: float
    acquired: bool


def _text(node, path: str, default: str = "") -> str:
    el = node.find(path)
    if el is None:
        return default
    val = el.find("value")
    target = val if val is not None else el
    return (target.text or default).strip() if target.text else default


def parse_form4(cik: str, accession_nodash: str, accession: str,
                ticker: str, filing_date: pd.Timestamp) -> list[InsiderTrade]:
    """Liest die XML einer Form-4-Einreichung aus."""
    base = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession_nodash}"
    try:
        listing = _get(f"{base}/index.json", cache_key=f"idx_{accession_nodash}")
    except Exception:  # noqa: BLE001
        return []

    xml_name = next(
        (
            item["name"]
            for item in listing.get("directory", {}).get("item", [])
            if item["name"].endswith(".xml") and not item["name"].startswith("R")
        ),
        None,
    )
    if not xml_name:
        return []

    try:
        blob = _get(f"{base}/{xml_name}", as_json=False,
                    cache_key=f"f4_{accession_nodash}")
        raw = blob["_text"] if isinstance(blob, dict) else blob
        root = ET.fromstring(raw)
    except Exception:  # noqa: BLE001
        return []

    owner = _text(root, ".//reportingOwnerId/rptOwnerName", "unbekannt")
    rel = root.find(".//reportingOwnerRelationship")
    is_officer = is_director = False
    if rel is not None:
        is_officer = _text(rel, "isOfficer", "0") in {"1", "true"}
        is_director = _text(rel, "isDirector", "0") in {"1", "true"}

    trades: list[InsiderTrade] = []
    for tx in root.findall(".//nonDerivativeTransaction"):
        code = _text(tx, "transactionCoding/transactionCode")
        amounts = tx.find("transactionAmounts")
        if amounts is None:
            continue
        try:
            shares = float(_text(amounts, "transactionShares", "0") or 0)
            price = float(_text(amounts, "transactionPricePerShare", "0") or 0)
        except ValueError:
            continue
        acquired = _text(amounts, "transactionAcquiredDisposedCode", "") == "A"
        tx_date = _text(tx, "transactionDate")

        trades.append(
            InsiderTrade(
                ticker=ticker,
                filing_date=filing_date,
                transaction_date=pd.Timestamp(tx_date, tz="UTC") if tx_date else None,
                owner=owner,
                is_officer=is_officer,
                is_director=is_director,
                code=code,
                shares=shares,
                price=price,
                value=shares * price,
                acquired=acquired,
            )
        )
    return trades


def insider_trades(
    tickers: str | Iterable[str], since: str = "2016-01-01", max_filings: int | None = None
) -> pd.DataFrame:
    """Alle Form-4-Geschaefte als Tabelle.

    ACHTUNG Laufzeit: Jede Einreichung braucht 2 Requests (Verzeichnis +
    XML). Ein Symbol mit 400 Form-4-Meldungen kostet also 800 Requests -
    bei 8-9/s Drossel rund 90-100 Sekunden PLATTENGEBUNDEN. Der
    Plattencache macht Wiederholungslaeufe praktisch kostenlos, der
    erste Lauf dauert.

    **Warum die Einreichungen parallel geholt werden (§G47, 27.08.2026).**
    Bis dahin lief das hier als einfache `for`-Schleife: ein Filing nach
    dem anderen, und jedes wartet erst die volle Netzwerkantwort ab,
    bevor das naechste beginnt. Gemessen im laufenden EDGAR-Lauf: die
    Drossel erlaubt 9 Requests/Sekunde, tatsaechlich ankamen **1,66**.
    Der Engpass war nie das SEC-Limit, sondern die reine Wartezeit auf
    die Antwort - das Budget lag die meiste Zeit brach.

    Der `ThreadPoolExecutor` aendert daran NICHTS an der erlaubten Rate:
    `_limit` (`RateLimiter`) ist threadsicher und bleibt die EINZIGE
    Instanz, die das SEC-Limit durchsetzt (`_get()` ruft `_limit.acquire()`
    unabhaengig vom aufrufenden Thread). Parallelitaet sorgt nur dafuer,
    dass ein Thread, der auf eine Antwort wartet, das Budget nicht fuer
    alle anderen blockiert.

    `max_filings` ist eine LAUFZEITBREMSE, keine Kuerzung: Wird sie
    ueberschritten, fliegt `ZuVieleMeldungen`. Der Aufrufer entscheidet
    dann, ob er das Symbol ausschliesst oder die Grenze anhebt. Bis zum
    26.08.2026 wurde hier still auf die neuesten N gekuerzt - siehe
    `ZuVieleMeldungen` fuer den Schaden, den das angerichtet hat (§G41).
    """
    syms = [tickers] if isinstance(tickers, str) else list(tickers)
    rows: list[InsiderTrade] = []

    for sym in syms:
        f = filings(sym, "4", since=since)
        if max_filings and len(f) > max_filings:
            raise ZuVieleMeldungen(
                f"{sym}: {len(f)} Form-4-Meldungen seit {since}, Grenze ist "
                f"{max_filings}. Symbol ausschliessen oder Grenze anheben - "
                f"Abschneiden erzeugt ein Panel mit Zeitverzerrung (§G41).")
        with ThreadPoolExecutor(max_workers=PARALLEL_FILINGS) as pool:
            for teil in pool.map(
                lambda r: parse_form4(r["cik"], r["accession"], r["accessionNumber"],
                                      r["ticker"], r["filing_date"]),
                [row for _, row in f.iterrows()],
            ):
                rows.extend(teil)

    if not rows:
        return pd.DataFrame(
            columns=["ticker", "filing_date", "transaction_date", "owner",
                     "is_officer", "is_director", "code", "shares", "price",
                     "value", "acquired"]
        )
    df = pd.DataFrame([t.__dict__ for t in rows])
    return df.sort_values("filing_date").reset_index(drop=True)


def open_market_buys(trades: pd.DataFrame) -> pd.DataFrame:
    """Filtert auf das, was tatsaechlich Information traegt: echte Kaeufe.

    Code P = Kauf am offenen Markt. Alles andere (Zuteilungen, Options-
    ausuebungen, Schenkungen) wird verworfen - es sagt ueber die
    Einschaetzung des Insiders nichts aus.
    """
    if trades.empty:
        return trades
    return trades[
        trades["code"].isin(MEANINGFUL_BUY_CODES)
        & trades["acquired"]
        & (trades["value"] > 0)
    ].copy()


def insider_features(
    trades: pd.DataFrame,
    price_index: pd.DatetimeIndex,
    ticker: str,
    windows: tuple[int, ...] = (30, 90),
) -> pd.DataFrame:
    """Zeitpunktsichere Insider-Merkmale auf dem Kurs-Zeitraster.

    Gezaehlt wird ab dem **filing_date** - dem Tag, an dem die Meldung
    oeffentlich wurde. Das Geschaeft selbst liegt bis zu 2 Werktage
    davor, aber davon konntest du nichts wissen.

    Merkmale je Fenster:
        insider_buys_Nd      Anzahl Kaufmeldungen
        insider_buyers_Nd    Anzahl VERSCHIEDENER Kaeufer (das Cluster-Mass)
        insider_value_Nd     Kaufvolumen in USD
        insider_officer_Nd   Kaeufe von Vorstaenden/Direktoren
    """
    idx = pd.DatetimeIndex(price_index)
    if idx.tz is None:
        idx = idx.tz_localize("UTC")
    out = pd.DataFrame(index=price_index)

    buys = open_market_buys(trades)
    if not buys.empty:
        buys = buys[buys["ticker"] == ticker.upper()]

    if buys.empty:
        for w in windows:
            out[f"insider_buys_{w}d"] = 0.0
            out[f"insider_buyers_{w}d"] = 0.0
            out[f"insider_value_{w}d"] = 0.0
            out[f"insider_officer_{w}d"] = 0.0
        return out

    fdates = pd.DatetimeIndex(buys["filing_date"])
    for w in windows:
        counts, buyers, values, officers = [], [], [], []
        for t in idx:
            lo = t - pd.Timedelta(days=w)
            # Strikt: nur Meldungen, die BIS EINSCHLIESSLICH t oeffentlich waren.
            mask = (fdates > lo) & (fdates <= t)
            sel = buys[mask]
            counts.append(len(sel))
            buyers.append(sel["owner"].nunique())
            values.append(float(sel["value"].sum()))
            officers.append(int((sel["is_officer"] | sel["is_director"]).sum()))
        out[f"insider_buys_{w}d"] = counts
        out[f"insider_buyers_{w}d"] = buyers
        out[f"insider_value_{w}d"] = values
        out[f"insider_officer_{w}d"] = officers

    return out


def cluster_score(features: pd.DataFrame, window: int = 90) -> pd.Series:
    """Verdichtet die Insider-Merkmale zu einem Wert zwischen 0 und 1.

    Gewichtung nach Aussagekraft: Die Anzahl VERSCHIEDENER Kaeufer ist
    das eigentliche Signal. Ein Vorstand, der fuenfmal nachlegt, ist eine
    Meinung; fuenf unabhaengige Insider, die zeitgleich kaufen, sind ein
    Befund.
    """
    buyers = features.get(f"insider_buyers_{window}d", pd.Series(0, index=features.index))
    value = features.get(f"insider_value_{window}d", pd.Series(0, index=features.index))
    officers = features.get(f"insider_officer_{window}d", pd.Series(0, index=features.index))

    score = (
        0.55 * (buyers.clip(0, 4) / 4)
        + 0.25 * (value.clip(0, 1_000_000) / 1_000_000)
        + 0.20 * (officers.clip(0, 3) / 3)
    )
    return score.clip(0, 1).rename("insider_score")
