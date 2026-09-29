"""FINRA-Daten: Short Interest (halbmonatlich) und Reg-SHO-Shortvolumen (taeglich).

Beides kostenlos, beides ohne Schluessel, beides mit klarer Zeitstempel-
Regel - und beides mit sehr unterschiedlicher Evidenzlage:

  * **Short Interest** (offene Leerverkaufspositionen je Aktie, zweimal im
    Monat): Hohe Short-Quote sagt NEGATIVE Rendite voraus (Boehmer, Huszar &
    Jordan 2010; Rapach et al. 2016 - aggregiert sogar einer der staerksten
    Marktpraediktoren). Als Ausschlussfilter fuer Long-Portfolios plausibel.
  * **Reg-SHO-Tagesshortvolumen** (Anteil Leerverkaeufe am Tagesumsatz):
    Laut aktueller Auswertung (Equibles 2025) nur ein Nowcast des naechsten
    Short-Interest-Berichts, KEIN Renditesignal. Hier als Negativtest.

**Point-in-Time, die Regel, die alles entscheidet:** FINRA veroeffentlicht den
Short-Interest-Bericht ~8 Werktage nach dem Stichtag (settlement date). Wer den
Wert am Stichtag selbst verwendet, weiss 8 Tage zu frueh Bescheid. Deshalb
tragen alle Werte hier `verfuegbar_ab = settlement + VEROEFFENTLICHUNGS_VERZUG`
und werden ueber `pit.asof_join`-Logik erst danach wirksam.

**Formatvorbehalt:** Die Feldnamen der FINRA-Dateien wurden aus der
oeffentlichen API-Beschreibung uebernommen; der Rechner, auf dem dieses Modul
entstand, konnte finra.org nicht erreichen. `lade_short_interest_datei()`
normalisiert bekannte Schreibweisen und meldet unbekannte Spalten laut. Beim
ersten echten Lauf: eine Datei von Hand pruefen, dann `--selftest` gegen
`_synthetische_datei()` vergleichen.
"""

from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from .config import CACHE_DIR
from .ratelimit import RateLimiter, with_retry

FINRA_CACHE = CACHE_DIR / "finra"
FINRA_CACHE.mkdir(parents=True, exist_ok=True)

VEROEFFENTLICHUNGS_VERZUG = pd.Timedelta(days=12)
"""Kalendertage zwischen Stichtag und Veroeffentlichung (8 Werktage + Puffer).
Konservativ, damit kein Wert vor seiner tatsaechlichen Verfuegbarkeit wirkt."""

# Query-API (kostenlos, JSON/CSV). Dokumentiert unter developer.finra.org.
SI_API_URL = "https://api.finra.org/data/group/otcMarket/name/consolidatedShortInterest"
# Reg-SHO-Tagesdateien, pipe-getrennt: Date|Symbol|ShortVolume|ShortExemptVolume|TotalVolume|Market
REGSHO_URL = "https://cdn.finra.org/equity/regsho/daily/CNMSshvol{datum}.txt"

_limit = RateLimiter("finra")

# Bekannte Schreibweisen -> Standardnamen
_SPALTEN = {
    "settlementdate": "settlement", "settlement_date": "settlement",
    "symbolcode": "symbol", "symbol": "symbol", "issuesymbolidentifier": "symbol",
    "currentshortpositionquantity": "short_qty", "shortinterest": "short_qty",
    "previousshortpositionquantity": "short_qty_vorher",
    "changepercent": "aenderung_pct", "changepreviousnumber": "aenderung_abs",
    "averagedailyvolumequantity": "avg_volumen", "avgdailyvolume": "avg_volumen",
    "daystocoverquantity": "days_to_cover", "daystocover": "days_to_cover",
    "marketclasscode": "markt", "issuename": "name",
}


def _normalisieren(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    umbenannt = {}
    unbekannt = []
    for c in df.columns:
        k = c.lower().replace(" ", "").replace("-", "")
        if k in _SPALTEN:
            umbenannt[c] = _SPALTEN[k]
        else:
            unbekannt.append(c)
    df = df.rename(columns=umbenannt)
    if unbekannt:
        print(f"      FINRA: unbekannte Spalten ignoriert: {unbekannt[:8]}")
    fehlt = {"settlement", "symbol", "short_qty"} - set(df.columns)
    if fehlt:
        raise ValueError(f"FINRA-Datei ohne Pflichtspalten {sorted(fehlt)}; "
                         f"vorhanden: {list(df.columns)[:12]}")
    df["settlement"] = pd.to_datetime(df["settlement"].astype(str).str.slice(0, 10),
                                      errors="coerce")
    df["symbol"] = df["symbol"].astype(str).str.upper().str.strip()
    for c in ("short_qty", "short_qty_vorher", "avg_volumen", "days_to_cover",
              "aenderung_pct", "aenderung_abs"):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["settlement", "symbol", "short_qty"])
    df["verfuegbar_ab"] = df["settlement"] + VEROEFFENTLICHUNGS_VERZUG
    return df


def lade_short_interest_datei(pfad: str | Path) -> pd.DataFrame:
    """Liest eine FINRA-Short-Interest-Datei (CSV oder pipe-getrennt)."""
    text = Path(pfad).read_text(errors="replace")
    sep = "|" if text.splitlines()[0].count("|") > text.splitlines()[0].count(",") else ","
    return _normalisieren(pd.read_csv(io.StringIO(text), sep=sep, dtype=str))


def lade_short_interest_api(start: str, ende: str, *, limit: int = 5000,
                            verbose: bool = True) -> pd.DataFrame:
    """Holt Short Interest ueber die FINRA-Query-API, seitenweise, mit Cache.

    Die API liefert je Aufruf hoechstens `limit` Zeilen; ein Stichtag hat
    ~15.000 Zeilen (alle Aktien). Deshalb je Stichtag mehrere Seiten.
    """
    cache = FINRA_CACHE / f"si_{start}_{ende}.parquet"
    if cache.exists():
        return pd.read_parquet(cache)
    frames = []
    offset = 0
    while True:
        body = {
            "limit": limit, "offset": offset,
            "dateRangeFilters": [{"fieldName": "settlementDate",
                                  "startDate": start, "endDate": ende}],
        }
        _limit.acquire()
        resp = with_retry(lambda: requests.post(
            SI_API_URL, json=body, timeout=60,
            headers={"Accept": "text/csv", "Content-Type": "application/json"}))
        if resp.status_code != 200:
            raise RuntimeError(f"FINRA API {resp.status_code}: {resp.text[:200]}")
        teil = pd.read_csv(io.StringIO(resp.text), dtype=str)
        if teil.empty:
            break
        frames.append(teil)
        if verbose:
            print(f"      FINRA SI: {offset + len(teil):,} Zeilen ...")
        if len(teil) < limit:
            break
        offset += limit
    df = _normalisieren(pd.concat(frames, ignore_index=True)) if frames else pd.DataFrame()
    if not df.empty:
        df.to_parquet(cache)
    return df


def lade_regsho_tag(datum: str | pd.Timestamp) -> pd.DataFrame:
    """Reg-SHO-Tagesdatei (Leerverkaufsvolumen je Symbol) fuer EINEN Tag."""
    d = pd.Timestamp(datum).strftime("%Y%m%d")
    cache = FINRA_CACHE / f"regsho_{d}.parquet"
    if cache.exists():
        return pd.read_parquet(cache)
    _limit.acquire()
    resp = with_retry(lambda: requests.get(REGSHO_URL.format(datum=d), timeout=60))
    if resp.status_code != 200 or "|" not in resp.text[:200]:
        return pd.DataFrame()
    df = pd.read_csv(io.StringIO(resp.text), sep="|", dtype=str)
    df.columns = [c.strip().lower() for c in df.columns]
    df = df[df.get("symbol", pd.Series(dtype=str)).notna()]
    df = df.rename(columns={"date": "datum", "shortvolume": "short_volumen",
                            "totalvolume": "gesamt_volumen"})
    df["datum"] = pd.to_datetime(df["datum"].astype(str).str.slice(0, 8), format="%Y%m%d",
                                 errors="coerce")
    for c in ("short_volumen", "gesamt_volumen"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["datum", "symbol"])
    df["symbol"] = df["symbol"].str.upper()
    # Gleicher Tag, verfuegbar nach Boersenschluss -> wirkt ab dem Folgetag
    df["verfuegbar_ab"] = df["datum"] + pd.Timedelta(days=1)
    df.to_parquet(cache)
    return df


# ---------------------------------------------------------------------------
# Faktor-Panels fuer das Labor
# ---------------------------------------------------------------------------
def short_interest_panels(si: pd.DataFrame, kalender: pd.DatetimeIndex,
                          symbole: list[str], *, volumen_panel: pd.DataFrame | None = None
                          ) -> dict[str, pd.DataFrame]:
    """Short-Interest-Merkmale als breite Panels (Tage x Symbole), PIT-sicher.

    Jeder Wert gilt ab `verfuegbar_ab` bis zum naechsten veroeffentlichten
    Wert (forward fill), nie frueher.

        si_days_to_cover   Leerverkaufsposition / durchschnittl. Tagesvolumen
                           (hoch = stark geshortet -> erwartete Rendite NEGATIV)
        si_aenderung       Veraenderung zum Vorbericht in %
        si_quote_vol       Short-Position / 20-Tage-Volumen aus dem Kurspanel
                           (unabhaengig von FINRAs eigener Volumenzahl)
    """
    kal = pd.DatetimeIndex(kalender)
    out = {}
    piv = {}
    for feld in ("days_to_cover", "aenderung_pct", "short_qty"):
        if feld not in si.columns:
            continue
        t = (si.pivot_table(index="verfuegbar_ab", columns="symbol", values=feld,
                            aggfunc="last")
             .reindex(columns=[s for s in symbole if s in si["symbol"].unique()]))
        t = t.reindex(t.index.union(kal)).sort_index().ffill(limit=40).reindex(kal)
        piv[feld] = t.reindex(columns=symbole).astype("float32")
    if "days_to_cover" in piv:
        out["si_days_to_cover_neg"] = -piv["days_to_cover"]
    if "aenderung_pct" in piv:
        out["si_aenderung_neg"] = -piv["aenderung_pct"]
    if "short_qty" in piv and volumen_panel is not None:
        v20 = volumen_panel.reindex(index=kal, columns=symbole).rolling(20, min_periods=10).mean()
        out["si_quote_vol_neg"] = -(piv["short_qty"] / v20.replace(0, np.nan))
    return {k: v.replace([np.inf, -np.inf], np.nan) for k, v in out.items()}


def regsho_panel(tage: list[pd.DataFrame], kalender: pd.DatetimeIndex,
                 symbole: list[str], fenster: int = 5) -> pd.DataFrame:
    """Anteil Leerverkaufsvolumen am Gesamtvolumen, rollierend, ab Folgetag."""
    df = pd.concat(tage, ignore_index=True)
    q = df.assign(quote=df["short_volumen"] / df["gesamt_volumen"].replace(0, np.nan))
    piv = q.pivot_table(index="verfuegbar_ab", columns="symbol", values="quote", aggfunc="mean")
    piv = piv.reindex(pd.DatetimeIndex(kalender)).reindex(columns=symbole)
    return piv.rolling(fenster, min_periods=max(2, fenster // 2)).mean().astype("float32")


# ---------------------------------------------------------------------------
# Selbsttest mit synthetischer Datei
# ---------------------------------------------------------------------------
def _synthetische_datei(pfad: Path, symbole: list[str], stichtage: list[str]) -> None:
    rng = np.random.default_rng(3)
    zeilen = ["settlementDate|symbolCode|issueName|marketClassCode|currentShortPositionQuantity|"
              "previousShortPositionQuantity|changePercent|averageDailyVolumeQuantity|daysToCoverQuantity"]
    for d in stichtage:
        for s in symbole:
            cur = int(rng.integers(1_000, 5_000_000))
            prev = int(cur * rng.uniform(0.7, 1.3))
            adv = int(rng.integers(50_000, 20_000_000))
            zeilen.append(f"{d}|{s}|{s} Inc|NNM|{cur}|{prev}|{(cur / prev - 1) * 100:.2f}|{adv}|{cur / adv:.2f}")
    pfad.write_text("\n".join(zeilen))


def selftest() -> int:
    import tempfile

    fehler = 0
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "shrt.txt"
        syms = ["AAA", "BBB", "CCC"]
        _synthetische_datei(p, syms, ["2024-01-12", "2024-01-31"])
        si = lade_short_interest_datei(p)
        ok = len(si) == 6 and set(si.columns) >= {"settlement", "symbol", "short_qty", "days_to_cover", "verfuegbar_ab"}
        print(f"  [{'ok' if ok else 'FEHLER'}] Datei gelesen: {len(si)} Zeilen, Spalten normalisiert"); fehler += not ok
        ok = (si["verfuegbar_ab"] - si["settlement"]).min() >= pd.Timedelta(days=8)
        print(f"  [{'ok' if ok else 'FEHLER'}] Verfuegbarkeit >= 8 Tage nach Stichtag"); fehler += not ok
        kal = pd.bdate_range("2024-01-02", "2024-03-01")
        panels = short_interest_panels(si, kal, syms)
        dtc = panels["si_days_to_cover_neg"]
        # Vor dem ersten Veroeffentlichungstag muss alles NaN sein (kein Lookahead)
        erster = si["verfuegbar_ab"].min()
        ok = dtc.loc[:erster - pd.Timedelta(days=1)].isna().all().all() and dtc.loc[erster:].notna().any().any()
        print(f"  [{'ok' if ok else 'FEHLER'}] Kein Wert vor Veroeffentlichung, Werte danach"); fehler += not ok
        # Zweiter Bericht ueberschreibt den ersten erst ab seinem eigenen Termin
        zweiter = si["verfuegbar_ab"].max()
        # Veroeffentlichung kann auf ein Wochenende fallen: letzter Handelstag
        # davor und erster Handelstag ab dem Termin
        wert_vor = dtc.loc[:zweiter - pd.Timedelta(days=1), "AAA"].iloc[-1]
        wert_nach = dtc.loc[zweiter:, "AAA"].iloc[0]
        erwartet_nach = -float(si[(si.symbol == "AAA") & (si.verfuegbar_ab == zweiter)]["days_to_cover"].iloc[0])
        ok = abs(wert_nach - erwartet_nach) < 1e-4 and wert_vor != wert_nach
        print(f"  [{'ok' if ok else 'FEHLER'}] Forward-Fill bis zum naechsten Bericht: {wert_vor:.2f} -> {wert_nach:.2f}"); fehler += not ok
    print(f"\n  finra-Selbsttest: {'bestanden' if fehler == 0 else f'{fehler} Fehler'}")
    return 1 if fehler else 0
