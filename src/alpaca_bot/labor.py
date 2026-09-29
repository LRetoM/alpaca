"""Forschungslabor 2027: vektorisierte Hypothesentests auf breiten Panels.

Warum ein zweites Labor neben `research.py`?

`research.py` misst Faktor-ICs je Tag (Spearman) und ist dafuer gut. Fuer den
Plan 2027 fehlen drei Dinge, die hier ergaenzt werden:

  1. **Panels statt Schleifen.** Alle Kurse liegen als breite Matrizen
     (Zeilen = Tage, Spalten = Symbole) vor. Jeder Faktor ist eine
     Matrixoperation. Damit laufen 40 Faktoren x 5 Horizonte x 4.000
     Symbole in Minuten, nicht Stunden.
  2. **Portfolio-Simulation ohne Engine-Overhead.** Ein Rangportfolio
     (Top-N, Haltedauer H, Kosten in bps, Regimefilter) wird vektorisiert
     bewertet - inklusive Jahrestabelle und Vergleich gegen SPY. Das ist
     KEIN Ersatz fuer `simulate.py` (die Engine ist der Live-Pfad), sondern
     der billige Vorfilter davor: Was hier nicht traegt, kommt nie in die
     Engine.
  3. **Mehrere Datenquellen.** Der Rechner, auf dem dieses Modul geschrieben
     wurde, konnte weder Yahoo noch Alpaca erreichen. Deshalb lesen die
     Lader auch das Qlib-Binaerformat (US-Aktien ab 1999 bis 11/2020, mit
     Volumen), Data_Stock (S&P-500-Schlusskurse 2016-2026), Lean-Beispiele
     (SPY/QQQ/IWM OHLCV 1998-2021) und - auf deinem Mac - den Projektcache
     `data/cache/bars/*.parquet` mit 2.168 Symbolen ueber 8+ Jahre.

**Ehrlichkeitsregeln, die hier fest eingebaut sind:**

  * Jede Vorwaertsrendite beginnt am NAECHSTEN Handelstag (`shift(-1)` auf
    der Eroeffnung, wenn vorhanden, sonst am naechsten Schluss). Wer die
    Rendite ab dem Entscheidungsschluss rechnet, misst einen Vorsprung,
    den es live nicht gibt.
  * Kosten sind Pflichtparameter. Es gibt keine kostenlose Simulation.
  * Jede Kennzahl kommt mit Jahrestabelle. Ein Mittelwert ueber 2016-2026
    versteckt 2020 und 2022; genau die zwei Jahre entscheiden aber, ob man
    die Strategie ueberlebt.
  * Survivorship: Alle hier lesbaren freien Quellen enthalten nur
    ueberlebende Symbole. Jedes Ergebnis ist eine OBERGRENZE.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

TRADING_DAYS = 252


# ===========================================================================
# 1. Panels: breite Matrizen je Feld
# ===========================================================================
@dataclass
class Panel:
    """Kurse als breite Matrizen. Index = Handelstage (UTC-naiv), Spalten = Symbole.

    `close` ist immer vorhanden; `open/high/low/volume` koennen fehlen
    (Data_Stock liefert z. B. nur Schlusskurse). Funktionen, die ein Feld
    brauchen, pruefen `hat()` und fallen sonst auf eine dokumentierte
    Naeherung zurueck oder melden sich ab.
    """

    close: pd.DataFrame
    open: pd.DataFrame | None = None
    high: pd.DataFrame | None = None
    low: pd.DataFrame | None = None
    volume: pd.DataFrame | None = None
    raw_close: pd.DataFrame | None = None
    """Unbereinigter Kurs (fuer Kursfilter >= 3 $). Fehlt er, gilt close."""
    quelle: str = "unbekannt"

    def hat(self, feld: str) -> bool:
        return getattr(self, feld, None) is not None

    @property
    def symbole(self) -> list[str]:
        return list(self.close.columns)

    @property
    def dollar_volume(self) -> pd.DataFrame | None:
        if self.volume is None:
            return None
        px = self.raw_close if self.raw_close is not None else self.close
        return self.volume * px

    def schneiden(self, start: str | None = None, ende: str | None = None) -> "Panel":
        def _s(df):
            if df is None:
                return None
            return df.loc[start:ende]
        return Panel(
            close=_s(self.close), open=_s(self.open), high=_s(self.high),
            low=_s(self.low), volume=_s(self.volume), raw_close=_s(self.raw_close),
            quelle=self.quelle,
        )

    def filtern(self, symbole: list[str]) -> "Panel":
        keep = [s for s in symbole if s in self.close.columns]
        def _f(df):
            return None if df is None else df[keep]
        return Panel(
            close=_f(self.close), open=_f(self.open), high=_f(self.high),
            low=_f(self.low), volume=_f(self.volume), raw_close=_f(self.raw_close),
            quelle=self.quelle,
        )

    def beschreibung(self) -> str:
        felder = [f for f in ("open", "high", "low", "close", "volume") if self.hat(f)]
        return (f"Panel[{self.quelle}] {len(self.close.columns):,} Symbole, "
                f"{len(self.close):,} Tage ({self.close.index[0].date()} .. "
                f"{self.close.index[-1].date()}), Felder: {', '.join(felder)}")


def _naiv(idx) -> pd.DatetimeIndex:
    idx = pd.DatetimeIndex(idx)
    if idx.tz is not None:
        idx = idx.tz_convert("UTC").tz_localize(None)
    return idx.normalize()


def panel_aus_multiindex(bars: pd.DataFrame, quelle: str = "projekt") -> Panel:
    """Projektformat (MultiIndex symbol/timestamp, OHLCV) -> Panel.

    Das ist das Format von `datasources.get_history()` und `data.get_bars()`,
    also der Weg fuer die 2.168-Symbole-Historie auf deinem Rechner.
    """
    df = bars.copy()
    if not isinstance(df.index, pd.MultiIndex):
        raise ValueError("MultiIndex (symbol, timestamp) erwartet.")
    df = df.reset_index()
    df["timestamp"] = _naiv(df["timestamp"])
    df = df.drop_duplicates(["symbol", "timestamp"])
    felder = {}
    for f in ("open", "high", "low", "close", "volume"):
        if f in df.columns:
            felder[f] = (df.pivot(index="timestamp", columns="symbol", values=f)
                         .sort_index().astype("float32"))
    return Panel(close=felder["close"], open=felder.get("open"),
                 high=felder.get("high"), low=felder.get("low"),
                 volume=felder.get("volume"), quelle=quelle)


def panel_aus_qlib(pfad: str | Path, *, start: str = "2005-01-01",
                   min_tage: int = 250, verbose: bool = True) -> Panel:
    """Qlib-Binaerformat (Yahoo-Sammlung, US-Aktien bis 11/2020) -> Panel.

    Format je Datei: float32-Array, erstes Element = Startposition im
    Kalender, danach die Werte. Kurse sind bereinigt und auf den ersten
    Handelstag normiert (Schluss am ersten Tag = 1); `close / factor` ist
    der Rohkurs in USD. Das Volumen ist DURCH den Faktor geteilt gespeichert
    (AAPL 09.11.2020: gespeichert 121,4 Mio., real 154,5 Mio. = gespeichert
    x Faktor 1,273). Hier wird es auf echte Stueckzahlen zurueckgerechnet,
    damit `volume * raw_close` den echten Dollar-Umsatz ergibt - empirisch
    an AAPL und SPY geprueft.
    """
    pfad = Path(pfad)
    cal = pd.to_datetime(Path(pfad, "calendars", "day.txt").read_text().split())
    inst = pd.read_csv(Path(pfad, "instruments", "all.txt"), sep="\t", header=None,
                       names=["symbol", "von", "bis"])
    start_ts = pd.Timestamp(start)
    inst = inst[pd.to_datetime(inst["bis"]) >= start_ts]
    felder = {f: {} for f in ("open", "high", "low", "close", "volume", "factor")}
    n_ok = 0
    for i, sym in enumerate(inst["symbol"]):
        # Feature-Ordner sind kleingeschrieben, die Instrumentenliste nicht.
        d = Path(pfad, "features", str(sym).lower())
        if not d.exists():
            continue
        try:
            arr = {f: np.fromfile(d / f"{f}.day.bin", dtype="<f4") for f in felder}
        except FileNotFoundError:
            continue
        if any(len(a) < 2 for a in arr.values()):
            continue
        s = int(arr["close"][0])
        n = len(arr["close"]) - 1
        idx = cal[s:s + n]
        if len(idx) < min_tage or idx[-1] < start_ts:
            continue
        for f, a in arr.items():
            if int(a[0]) != s or len(a) - 1 != n:
                break
            felder[f][sym.upper()] = pd.Series(a[1:], index=idx)
        else:
            n_ok += 1
        if verbose and i % 2000 == 0 and i:
            print(f"      {i:,}/{len(inst):,} Instrumente gelesen ...")
    frames = {f: pd.DataFrame(v).sort_index().loc[start:].astype("float32")
              for f, v in felder.items()}
    close = frames["close"]
    raw = (frames["close"] / frames["factor"]).astype("float32")
    volume_roh = (frames["volume"] * frames["factor"]).astype("float32")
    if verbose:
        print(f"      Qlib: {n_ok:,} Symbole mit >= {min_tage} Tagen ab {start}")
    return Panel(close=close, open=frames["open"], high=frames["high"],
                 low=frames["low"], volume=volume_roh, raw_close=raw,
                 quelle="qlib_us")


def panel_bereinigen(p: Panel, *, min_abdeckung: float = 0.5,
                     max_sprung: float = 1.0, max_sturz: float = -0.6,
                     max_fehler_je_symbol: int = 5, verbose: bool = True) -> Panel:
    """Zwei Datenfehler, die jede Messung ruinieren - hier mechanisch entfernt.

    1. **Geistertage.** Tage, an denen nur eine Handvoll Symbole Kurse hat
       (Feiertage, an denen ein paar Auslandswerte notieren). Sie reissen
       Loecher in jede rollierende Reihe und verfaelschen Querschnitte.
       Regel: Tag bleibt nur, wenn mindestens `min_abdeckung` der
       Median-Abdeckung erreicht ist.
    2. **Flip-Flop-Fehler.** Kurse, die an einem Tag um +1.700 % springen
       und am naechsten zurueck (FCC in Data_Stock, CBE in Qlib). Das sind
       falsche Datenpunkte, keine Bewegungen. Regel: Ein Tagessprung ueber
       `max_sprung` oder ein Sturz unter `max_sturz`, dem eine Gegenbewegung
       folgt, wird auf NaN gesetzt. Symbole mit mehr als
       `max_fehler_je_symbol` solcher Ausreisser fliegen ganz raus - dort
       ist die Reihe nicht zu retten.

    Echte Explosionen (+100 % nach Uebernahme) bleiben erhalten, weil ihnen
    keine Gegenbewegung folgt.
    """
    c = p.close
    cov = c.notna().sum(axis=1)
    tage_ok = cov >= min_abdeckung * cov.median()
    n_geister = int((~tage_ok).sum())

    def _cut(df):
        return None if df is None else df.loc[tage_ok]

    c = c.loc[tage_ok]
    r = c.pct_change()
    ausreisser = (r > max_sprung) | (r < max_sturz)
    r_next = r.shift(-1)
    gegen = ((r > max_sprung) & (r_next < -0.4)) | ((r < max_sturz) & (r_next > 0.6))
    n_flip = int(gegen.sum().sum())
    schlecht = ausreisser.sum()
    raus = schlecht[schlecht > max_fehler_je_symbol].index.tolist()
    behalten = [s for s in c.columns if s not in raus]

    def _clean(df):
        if df is None:
            return None
        df = df.loc[tage_ok, behalten].copy()
        df[gegen[behalten]] = np.nan
        return df

    out = Panel(close=_clean(p.close), open=_clean(p.open), high=_clean(p.high),
                low=_clean(p.low), volume=_clean(p.volume),
                raw_close=_clean(p.raw_close), quelle=p.quelle)
    if verbose:
        print(f"      bereinigt: {n_geister} Geistertage entfernt, {n_flip} Flip-Flop-Werte "
              f"auf NaN, {len(raus)} Symbole verworfen ({', '.join(raus[:8])}"
              f"{' ...' if len(raus) > 8 else ''})")
    return out


def panel_speichern(p: Panel, verzeichnis: str | Path) -> None:
    """Panel als ein Parquet je Feld ablegen - schneller Wiedereinstieg."""
    d = Path(verzeichnis)
    d.mkdir(parents=True, exist_ok=True)
    for f in ("open", "high", "low", "close", "volume", "raw_close"):
        df = getattr(p, f)
        if df is not None:
            out = df.copy()
            out.columns = [str(c) for c in out.columns]
            out.to_parquet(d / f"{f}.parquet")
    (d / "quelle.txt").write_text(p.quelle)


def panel_aus_cache(verzeichnis: str | Path) -> Panel:
    d = Path(verzeichnis)
    felder = {}
    for f in ("open", "high", "low", "close", "volume", "raw_close"):
        pth = d / f"{f}.parquet"
        felder[f] = pd.read_parquet(pth) if pth.exists() else None
    quelle = (d / "quelle.txt").read_text() if (d / "quelle.txt").exists() else d.name
    return Panel(close=felder["close"], open=felder["open"], high=felder["high"],
                 low=felder["low"], volume=felder["volume"],
                 raw_close=felder["raw_close"], quelle=quelle)


def vix_laden(pfad: str | Path) -> pd.Series:
    """VIX-Tagesschluss aus datasets/finance-vix (DATE,OPEN,HIGH,LOW,CLOSE)."""
    df = pd.read_csv(pfad)
    df.columns = [c.strip().upper() for c in df.columns]
    df["DATE"] = pd.to_datetime(df["DATE"])
    return df.set_index("DATE")["CLOSE"].astype(float).sort_index()


def panel_aus_data_stock(pfad: str | Path) -> Panel:
    """Data_Stock (Long-Format Date/Ticker/Value, bereinigte Schlusskurse)."""
    df = pd.read_parquet(pfad)
    df["Date"] = pd.to_datetime(df["Date"])
    wide = (df.pivot(index="Date", columns="Ticker", values="Value")
            .sort_index().astype("float32"))
    wide.columns = [c.replace("BRKB.VI", "BRK.B") for c in wide.columns]
    return Panel(close=wide, quelle="data_stock")


def panel_aus_csv_verzeichnis(verzeichnis: str | Path, *, adj: bool = True,
                              muster: str = "*.csv") -> Panel:
    """Ein CSV je Symbol (Kaggle/yfinance-Stil: Date,Open,High,Low,Close,Adj Close,Volume
    oder timestamp,open,high,low,close,volume)."""
    verzeichnis = Path(verzeichnis)
    felder = {f: {} for f in ("open", "high", "low", "close", "volume")}
    raw = {}
    for p in sorted(verzeichnis.glob(muster)):
        sym = p.stem.upper()
        df = pd.read_csv(p)
        df.columns = [c.strip().lower() for c in df.columns]
        dcol = "date" if "date" in df.columns else "timestamp"
        df[dcol] = pd.to_datetime(df[dcol], utc=True).dt.tz_localize(None).dt.normalize()
        df = df.set_index(dcol).sort_index()
        df = df[~df.index.duplicated()]
        if adj and "adj close" in df.columns and "close" in df.columns:
            k = (df["adj close"] / df["close"]).replace([np.inf, -np.inf], np.nan)
            raw[sym] = df["close"]
            for f in ("open", "high", "low", "close"):
                if f in df.columns:
                    felder[f][sym] = df[f] * k
            if "volume" in df.columns:
                felder["volume"][sym] = df["volume"] / k
        else:
            for f in felder:
                if f in df.columns:
                    felder[f][sym] = df[f]
    frames = {f: (pd.DataFrame(v).sort_index().astype("float32") if v else None)
              for f, v in felder.items()}
    return Panel(close=frames["close"], open=frames["open"], high=frames["high"],
                 low=frames["low"], volume=frames["volume"],
                 raw_close=pd.DataFrame(raw).sort_index().astype("float32") if raw else None,
                 quelle=f"csv:{verzeichnis.name}")


def panel_laden(quelle: str, pfad: str | Path | None = None, **kw) -> Panel:
    """Einheitlicher Einstieg. quelle in {qlib, data_stock, csv, projekt, parquet}.

    `projekt`: der Projektcache (`datasources.get_history(..., use_cache=True)`),
    `parquet`: eine beliebige Parquet-Datei im Projektformat (MultiIndex).
    """
    if quelle == "qlib":
        return panel_aus_qlib(pfad, **kw)
    if quelle == "data_stock":
        return panel_aus_data_stock(pfad)
    if quelle == "csv":
        return panel_aus_csv_verzeichnis(pfad, **kw)
    if quelle in ("parquet", "projekt"):
        return panel_aus_multiindex(pd.read_parquet(pfad), quelle=quelle)
    raise ValueError(f"Unbekannte Quelle: {quelle}")


def liquides_universum(p: Panel, *, min_preis: float = 3.0,
                       min_dollar_volume: float = 1_000_000,
                       fenster: int = 60) -> pd.DataFrame:
    """Zulassungs-Maske je Tag und Symbol - ROLLIEREND, nicht global.

    Ein Symbol ist an Tag t zugelassen, wenn Median-Kurs und Median-Umsatz
    der letzten `fenster` Tage die Grenzen einhalten. Ein globaler Filter
    ("heute liquide") waere ein Lookahead: Er wuesste, welche Werte spaeter
    gross werden.
    """
    px = p.raw_close if p.raw_close is not None else p.close
    ok = px.rolling(fenster, min_periods=fenster // 2).median() >= min_preis
    dv = p.dollar_volume
    if dv is not None:
        ok &= dv.rolling(fenster, min_periods=fenster // 2).median() >= min_dollar_volume
    return ok


# ===========================================================================
# 2. Vorwaertsrenditen - immer ab dem NAECHSTEN Handelstag
# ===========================================================================
def vorwaertsrendite(p: Panel, horizont: int, *, ab_eroeffnung: bool = True) -> pd.DataFrame:
    """Rendite von Entscheidung am Schluss von t bis Schluss von t+1+h-1.

    `ab_eroeffnung=True`: Einstieg zur Eroeffnung von t+1 (wie simulate.py),
    Ausstieg zum Schluss von t+h. Fehlt die Eroeffnung, ab Schluss t+1.
    Beides ist frei von dem Leck, ab Schluss t zu rechnen.
    """
    c = p.close
    ende = c.shift(-horizont)
    if ab_eroeffnung and p.open is not None:
        einstieg = p.open.shift(-1)
    else:
        einstieg = c.shift(-1)
        ende = c.shift(-(horizont + 1))
    return (ende / einstieg - 1).astype("float32")


# ===========================================================================
# 3. Faktorzoo - alles strikt kausal (nur rolling/shift nach hinten)
# ===========================================================================
def _rank_pct(df: pd.DataFrame) -> pd.DataFrame:
    return df.rank(axis=1, pct=True)


def faktorzoo(p: Panel, *, spy: pd.Series | None = None) -> dict[str, pd.DataFrame]:
    """Alle Kandidaten als Panels. Vorzeichen: hoch = erwartete Ueberrendite.

    Gruppen (und was die Literatur erwartet):
      Umkehr        reversal_5d, reversal_21d, rsi2 - kurzfristig positiv
      Momentum      mom_6m, mom_12_1, mom_12_1_vola - mittelfristig positiv
      52-Wochen     naehe_52w_hoch - positiv (George & Hwang)
      Volatilitaet  vola_niedrig - positiv (Low-Vol-Anomalie)
      Volumen       vol_schub_1w (High-Volume-Return-Premium, GKM 2001) +,
                    vol_schub_6m negativ, turnover_trend
      Sprung        ear_proxy (Ereignisrendite mit Volumen, PEAD-Ersatz)
      Liquiditaet   amihud (Illiquiditaetspraemie)
      Rel. Staerke  rel_staerke_63 gegen SPY
    """
    c = p.close
    r1 = c.pct_change()
    logc = np.log(c)
    out: dict[str, pd.DataFrame] = {}

    # --- Umkehr ---
    out["reversal_5d"] = -(c / c.shift(5) - 1)
    out["reversal_21d"] = -(c / c.shift(21) - 1)
    gain = r1.clip(lower=0)
    loss = (-r1).clip(lower=0)
    ag = gain.ewm(alpha=0.5, adjust=False, min_periods=2).mean()
    al = loss.ewm(alpha=0.5, adjust=False, min_periods=2).mean()
    out["rsi2_invers"] = -(100 - 100 / (1 + ag / al.replace(0, np.nan)))

    # --- Momentum ---
    out["mom_6m"] = c / c.shift(126) - 1
    out["mom_12_1"] = c.shift(21) / c.shift(252) - 1
    vola = r1.rolling(63, min_periods=50).std()
    out["mom_12_1_vola"] = out["mom_12_1"] / (vola * np.sqrt(252)).replace(0, np.nan)
    # Momentum-Konsistenz: Anteil positiver Monate (Frazzini-"smooth momentum")
    m_ret = c.pct_change(21)
    out["mom_konsistenz"] = sum((m_ret.shift(21 * k) > 0).astype("float32")
                                for k in range(1, 12)) / 11.0

    # --- 52-Wochen-Hoch ---
    hi52 = (p.high if p.high is not None else c).rolling(252, min_periods=120).max()
    out["naehe_52w_hoch"] = c / hi52

    # --- Volatilitaet ---
    out["vola_niedrig"] = -vola
    if p.high is not None and p.low is not None:
        tr = pd.concat([(p.high - p.low), (p.high - c.shift(1)).abs(),
                        (p.low - c.shift(1)).abs()]).groupby(level=0).max()
        out["atr_niedrig"] = -(tr.rolling(14, min_periods=10).mean() / c)

    # --- Volumen (nur mit Volumen) ---
    if p.volume is not None:
        v = p.volume.replace(0, np.nan)
        logv = np.log(v)
        # High-Volume-Return-Premium: Volumen der letzten Woche gegen 10 Wochen davor
        out["vol_schub_1w"] = logv.rolling(5, min_periods=3).mean() - logv.shift(5).rolling(50, min_periods=40).mean()
        # Tages-Volumenschock (Z-Score gegen 60 Tage)
        out["vol_z_1d"] = (logv - logv.rolling(60, min_periods=45).mean()) / logv.rolling(60, min_periods=45).std()
        # Sechs Monate abnormales Volumen: negativ (langfristig ueberhandelt)
        out["vol_schub_6m_neg"] = -(logv.rolling(126, min_periods=100).mean() - logv.shift(126).rolling(252, min_periods=200).mean())
        # Turnover-Trend: steigt der Umsatz seit Wochen?
        out["turnover_trend"] = logv.rolling(20, min_periods=15).mean() - logv.rolling(120, min_periods=100).mean()
        # Amihud-Illiquiditaet (hoch = illiquide = Praemie, aber teuer)
        dv = p.dollar_volume
        out["amihud"] = (r1.abs() / dv.replace(0, np.nan)).rolling(20, min_periods=15).mean()
        # Volumen ohne Preisbewegung (Akkumulation): hoher Umsatz, kleine Range
        if p.high is not None and p.low is not None:
            rng = ((p.high - p.low) / c).rolling(5, min_periods=3).mean()
            out["akkumulation"] = out["vol_schub_1w"] - _rank_pct(rng)
        # EAR-Proxy: groesster |Tagesreturn| der letzten 5 Tage MIT Volumenschock,
        # Vorzeichen des Sprungs. Ersetzt Ergebnisdaten, wo keine vorliegen.
        z = out["vol_z_1d"]
        sprung = r1.where(z > 2.0)
        out["ear_proxy"] = sprung.rolling(5, min_periods=1).sum()
        # Gap-up mit Volumen (nur mit Eroeffnung)
        if p.open is not None:
            gap = p.open / c.shift(1) - 1
            out["gap_volumen"] = gap.where(z > 1.5).rolling(3, min_periods=1).sum()

    # --- Relative Staerke gegen SPY ---
    if spy is not None:
        s = spy.reindex(c.index).ffill()
        out["rel_staerke_63"] = (c / c.shift(63) - 1).sub(s / s.shift(63) - 1, axis=0)

    # --- Drawdown-Zustand (52w) ---
    lo52 = (p.low if p.low is not None else c).rolling(252, min_periods=120).min()
    out["abstand_52w_tief"] = c / lo52 - 1

    return {k: v.replace([np.inf, -np.inf], np.nan).astype("float32") for k, v in out.items()}


# ===========================================================================
# 4. Querschnitts-IC je Tag, vektorisiert
# ===========================================================================
def ic_je_tag(faktor: pd.DataFrame, fwd: pd.DataFrame, maske: pd.DataFrame | None = None,
              min_symbole: int = 50) -> pd.Series:
    """Spearman-IC je Tag ueber den Querschnitt (Pearson auf Raengen)."""
    f, r = faktor.align(fwd, join="inner")
    valid = f.notna() & r.notna()
    if maske is not None:
        valid &= maske.reindex_like(f).fillna(False).astype(bool)
    n = valid.sum(axis=1)
    fr = f.where(valid).rank(axis=1)
    rr = r.where(valid).rank(axis=1)
    frc = fr.sub(fr.mean(axis=1), axis=0).where(valid, 0.0)
    rrc = rr.sub(rr.mean(axis=1), axis=0).where(valid, 0.0)
    num = (frc * rrc).sum(axis=1)
    den = np.sqrt((frc ** 2).sum(axis=1) * (rrc ** 2).sum(axis=1))
    return (num / den.replace(0, np.nan)).where(n >= min_symbole).dropna()


def quintil_spanne(faktor: pd.DataFrame, fwd: pd.DataFrame,
                   maske: pd.DataFrame | None = None, q: float = 0.2) -> pd.Series:
    """Rendite oberstes minus unterstes Quintil je Tag (gleichgewichtet)."""
    f, r = faktor.align(fwd, join="inner")
    valid = f.notna() & r.notna()
    if maske is not None:
        valid &= maske.reindex_like(f).fillna(False).astype(bool)
    pr = f.where(valid).rank(axis=1, pct=True)
    top = r.where(pr > 1 - q).mean(axis=1)
    bot = r.where(pr <= q).mean(axis=1)
    return (top - bot).dropna()


@dataclass
class ICBefund:
    faktor: str
    horizont: int
    ic: float
    t: float
    n_tage: int
    trefferquote: float
    q5_q1_pa: float
    """Quintil-Spanne annualisiert (ohne Kosten, ohne Ueberlappung korrigiert)."""
    jahre: dict[int, float] = field(default_factory=dict)
    anteil_jahre_positiv: float = float("nan")
    schlechtestes_jahr: float = float("nan")

    @property
    def urteil(self) -> str:
        if abs(self.t) < 2:
            return "Rauschen"
        if self.ic > 0 and self.anteil_jahre_positiv >= 0.75:
            return "NUETZLICH+stabil" if self.ic > 0.01 else "schwach+stabil"
        if self.ic > 0:
            return "positiv, instabil"
        return "INVERTIERT" if self.ic < -0.01 else "schwach negativ"


def ic_messen(faktoren: dict[str, pd.DataFrame], p: Panel, horizonte=(5, 10, 21, 42, 63),
              maske: pd.DataFrame | None = None, verbose: bool = True) -> pd.DataFrame:
    """Faktorzoo x Horizonte -> Tabelle mit t-Wert und Jahresstabilitaet.

    Die t-Statistik wird ueber die Tagesreihe der ICs gerechnet. Bei
    ueberlappenden Horizonten sind benachbarte Tage korreliert; deshalb
    wird t zusaetzlich mit sqrt(horizont) deflationiert (`t_deflated`) - eine
    konservative Naeherung an Newey-West.
    """
    rows = []
    for h in horizonte:
        fwd = vorwaertsrendite(p, h)
        for name, f in faktoren.items():
            ic = ic_je_tag(f, fwd, maske)
            if len(ic) < 60:
                continue
            sp = quintil_spanne(f, fwd, maske).reindex(ic.index).dropna()
            arr = ic.to_numpy()
            std = arr.std(ddof=1)
            t = arr.mean() / (std / np.sqrt(len(arr))) if std > 0 else 0.0
            jahre = ic.groupby(ic.index.year).mean()
            jahre = jahre[ic.groupby(ic.index.year).size() >= 40]
            b = ICBefund(
                faktor=name, horizont=h, ic=float(arr.mean()), t=float(t),
                n_tage=len(arr), trefferquote=float((arr > 0).mean()),
                q5_q1_pa=float(sp.mean() * TRADING_DAYS / h) if len(sp) else float("nan"),
                jahre={int(k): round(float(v), 4) for k, v in jahre.items()},
                anteil_jahre_positiv=float((jahre > 0).mean()) if len(jahre) else float("nan"),
                schlechtestes_jahr=float(jahre.min()) if len(jahre) else float("nan"),
            )
            rows.append({**{k: v for k, v in b.__dict__.items() if k != "jahre"},
                         "t_deflated": b.t / np.sqrt(h), "urteil": b.urteil,
                         **{f"ic_{y}": v for y, v in b.jahre.items()}})
        if verbose:
            print(f"      Horizont {h:>3} Tage fertig")
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    return df.reindex(df["t_deflated"].abs().sort_values(ascending=False).index).reset_index(drop=True)


# ===========================================================================
# 5. Regime
# ===========================================================================
def regime_serien(spy_close: pd.Series, vix_close: pd.Series | None = None,
                  breite: pd.Series | None = None) -> pd.DataFrame:
    """Marktregime je Tag - alle Werte nur aus Vergangenheit.

    trend_ok      SPY ueber SMA200
    trend_ok_50   SPY ueber SMA50
    vola_hoch     realisierte 20-Tage-Vola von SPY im obersten Quintil der
                  letzten 2 Jahre (rollierend, kein globales Quantil!)
    vix_hoch      VIX > 25 (fester Schwellwert, PIT-sicher)
    drawdown_spy  Rueckgang vom 252-Tage-Hoch
    """
    s = spy_close.astype(float)
    df = pd.DataFrame(index=s.index)
    df["trend_ok"] = s > s.rolling(200).mean()
    df["trend_ok_50"] = s > s.rolling(50).mean()
    # trend_hyst (HYP-2027-24): AUS, sobald SPY unter die SMA200 faellt; wieder AN,
    # sobald SPY ueber der SMA50 liegt UND die SMA50 gegenueber vor 10 Tagen steigt -
    # schnellerer Wiedereinstieg nach V-Erholungen, gleicher Ausstieg. Nur Vergangenheit.
    sma50 = s.rolling(50).mean()
    an_signal = (s > sma50) & (sma50 > sma50.shift(10))
    aus_signal = ~df["trend_ok"]
    zustand = np.zeros(len(s), dtype=bool)
    z = False
    for i, (a, b, t) in enumerate(zip(an_signal.to_numpy(), aus_signal.to_numpy(), df["trend_ok"].to_numpy())):
        if z and b:
            z = False
        elif not z and (a or t):
            z = True
        zustand[i] = z
    df["trend_hyst"] = zustand
    rv = np.log(s).diff().rolling(20).std() * np.sqrt(252)
    df["vola_20"] = rv
    df["vola_hoch"] = rv > rv.rolling(504, min_periods=250).quantile(0.8)
    df["drawdown_spy"] = s / s.rolling(252, min_periods=60).max() - 1
    if vix_close is not None:
        vx = vix_close.reindex(s.index).ffill()
        df["vix"] = vx
        df["vix_hoch"] = vx > 25
        df["vix_extrem"] = vx > 35
    if breite is not None:
        df["breite"] = breite.reindex(s.index)
    return df


def marktbreite(p: Panel, fenster: int = 50) -> pd.Series:
    """Anteil der Symbole ueber ihrem eigenen SMA(fenster)."""
    c = p.close
    ueber = (c > c.rolling(fenster).mean())
    return ueber.sum(axis=1) / c.notna().sum(axis=1).replace(0, np.nan)


# ===========================================================================
# 6. Vektorisierte Rangportfolios
# ===========================================================================
@dataclass
class PortfolioConfig:
    top_n: int = 20
    haltedauer: int = 21
    """Handelstage bis zum Rebalancing. Ueberlappende Kohorten werden
    gleichgewichtet gemischt (Jegadeesh-Titman-Konstruktion), damit das
    Ergebnis nicht vom Starttag abhaengt."""
    kosten_bps_rundlauf: float = 20.0
    """Spread + Slippage + Gebuehren fuer Kauf UND Verkauf zusammen."""
    regime: str | None = None
    """Spalte aus regime_serien(): nur investiert, wenn True. None = immer."""
    vola_ziel: float | None = None
    """Ziel-Volatilitaet p.a. fuer das Gesamtportfolio (z. B. 0.15). None = aus."""
    max_hebel: float = 1.0
    min_score_rang: float | None = None
    """Nur Kandidaten ueber diesem Perzentil (0..1) des Scores - fuer 'lieber Cash'."""


@dataclass
class PortfolioErgebnis:
    equity: pd.Series
    renditen: pd.Series
    benchmark: pd.Series
    cfg: PortfolioConfig
    umschlag_pa: float
    kosten_pa: float
    exposure: float
    universum: pd.Series | None = None
    """Gleichgewichtete Tagesrendite ALLER zugelassenen Symbole (ohne Kosten).

    Der zweite, wichtigere Massstab: Schlaegt die Auswahl das Universum, aus
    dem sie waehlt? SPY ist kapitalgewichtet und besteht aus Grosswerten;
    ein Top-20 aus 3.000 Nebenwerten kann SPY verlieren und trotzdem
    Auswahl-Alpha haben - oder umgekehrt. Nur dieser Vergleich trennt
    Faktorwirkung von Universumseffekt."""

    def kennzahlen(self) -> dict:
        r = self.renditen.dropna()
        b = self.benchmark.reindex(r.index).fillna(0.0)
        out = {**_kennzahlen(r), "bench_cagr": _kennzahlen(b)["cagr"],
               "bench_maxdd": _kennzahlen(b)["max_drawdown"],
               "umschlag_pa": self.umschlag_pa, "kosten_pa": self.kosten_pa,
               "exposure": self.exposure}
        if self.universum is not None:
            u = self.universum.reindex(r.index).fillna(0.0)
            out["univ_cagr"] = _kennzahlen(u)["cagr"]
            out["univ_maxdd"] = _kennzahlen(u)["max_drawdown"]
        return out

    def jahrestabelle(self) -> pd.DataFrame:
        r = self.renditen.dropna()
        b = self.benchmark.reindex(r.index).fillna(0.0)
        u = (self.universum.reindex(r.index).fillna(0.0)
             if self.universum is not None else None)
        rows = []
        for y, g in r.groupby(r.index.year):
            bb = b.loc[g.index]
            row = {"jahr": int(y), "strategie": float((1 + g).prod() - 1),
                   "spy": float((1 + bb).prod() - 1),
                   "differenz": float((1 + g).prod() - (1 + bb).prod()),
                   "maxdd": float(_maxdd(g)), "maxdd_spy": float(_maxdd(bb)),
                   "tage": len(g)}
            if u is not None:
                row["univ_ew"] = float((1 + u.loc[g.index]).prod() - 1)
            rows.append(row)
        return pd.DataFrame(rows).set_index("jahr")


def _maxdd(r: pd.Series) -> float:
    eq = (1 + r).cumprod()
    return float((eq / eq.cummax() - 1).min())


def _kennzahlen(r: pd.Series) -> dict:
    r = r.dropna()
    if r.empty:
        return {}
    eq = (1 + r).cumprod()
    jahre = len(r) / TRADING_DAYS
    cagr = float(eq.iloc[-1] ** (1 / jahre) - 1) if jahre > 0 else np.nan
    vol = float(r.std() * np.sqrt(TRADING_DAYS))
    return {"total": float(eq.iloc[-1] - 1), "cagr": cagr, "vola": vol,
            "sharpe": float(r.mean() / r.std() * np.sqrt(TRADING_DAYS)) if r.std() > 0 else np.nan,
            "max_drawdown": _maxdd(r), "n_tage": int(len(r))}


def rangportfolio(score: pd.DataFrame, p: Panel, cfg: PortfolioConfig,
                  maske: pd.DataFrame | None = None,
                  regime: pd.DataFrame | None = None,
                  benchmark: pd.Series | None = None) -> PortfolioErgebnis:
    """Long-only Top-N-Portfolio auf einem Score-Panel, vektorisiert.

    Mechanik:
      * An jedem Tag t wird aus `score` (nur Vergangenheit) eine Kohorte
        der Top-N gewaehlt. Sie wird ab Eroeffnung t+1 (falls vorhanden,
        sonst Schluss t+1) fuer `haltedauer` Tage gehalten.
      * Es laufen `haltedauer` ueberlappende Kohorten gleichzeitig, jede
        mit 1/haltedauer des Kapitals. Das ist die Standardkonstruktion
        der Momentum-Literatur und macht das Ergebnis unabhaengig vom
        Startdatum.
      * Kosten: je Kohorte beim Ein- und Ausstieg `kosten_bps_rundlauf`.
        Ein Symbol, das in der Folgekohorte wieder gewaehlt wird, gilt
        trotzdem als neu gekauft - konservativ.
      * Regime: Ist das Regime am Entscheidungstag aus, wird die Kohorte
        nicht eroeffnet (Cash, 0 %).
    """
    c = p.close
    r_close = c.pct_change()
    sc = score.reindex_like(c)
    universum_ew = None
    if maske is not None:
        m = maske.reindex_like(c).fillna(False).astype(bool)
        sc = sc.where(m)
        # Gleichgewichtetes Universum: Zulassung von gestern, Rendite von heute
        universum_ew = r_close.where(m.shift(1)).mean(axis=1).fillna(0.0)
    if cfg.min_score_rang is not None:
        pr = sc.rank(axis=1, pct=True)
        sc = sc.where(pr >= cfg.min_score_rang)

    # Rang je Tag: Top-N Auswahl als 0/1 Matrix
    rk = sc.rank(axis=1, ascending=False, method="first")
    gewaehlt = (rk <= cfg.top_n).astype("float32")
    n_gewaehlt = gewaehlt.sum(axis=1)

    if regime is not None and cfg.regime:
        an = regime[cfg.regime].reindex(c.index).fillna(False).astype(bool)
        gewaehlt = gewaehlt.mul(an.astype("float32"), axis=0)
        n_gewaehlt = gewaehlt.sum(axis=1)

    H = cfg.haltedauer
    # Nur Symbole, die je gewaehlt wurden, tragen etwas bei - alle anderen
    # Spalten sind exakt null und kosten bei 8.000 Symbolen nur Rechenzeit.
    je_gewaehlt = gewaehlt.columns[gewaehlt.sum(axis=0) > 0]
    gewaehlt = gewaehlt[je_gewaehlt]
    c = c[je_gewaehlt]
    r_close = r_close[je_gewaehlt]
    # Rendite Tag t+1 relativ zu Eroeffnung t+1 (Einstieg) bzw. Schluss
    if p.open is not None:
        r_erster_tag = (c / p.open[je_gewaehlt] - 1)   # Eroeffnung -> Schluss am Einstiegstag
    else:
        r_erster_tag = r_close                          # Naeherung: Schluss -> Schluss
    gew = gewaehlt.div(n_gewaehlt.replace(0, np.nan), axis=0).fillna(0.0)  # Gewichte je Kohorte

    # Tagesrendite des Gesamtportfolios = Mittel ueber H Kohorten
    port = pd.Series(0.0, index=c.index)
    kosten = pd.Series(0.0, index=c.index)
    r1 = r_close.fillna(0.0)
    rft = r_erster_tag.fillna(0.0)
    for k in range(1, H + 1):
        w = gew.shift(k)                          # Kohorte, die vor k Tagen entschieden wurde
        if k == 1:
            port += (w * rft).sum(axis=1) / H
        else:
            port += (w * r1).sum(axis=1) / H
    # Kosten: jede Kohorte zahlt beim Eroeffnen (Tag t+1) den Rundlauf anteilig
    aktiv = gew.shift(1).sum(axis=1)             # Anteil investiert je neuer Kohorte
    kosten = aktiv * cfg.kosten_bps_rundlauf / 10_000 / H
    port = port - kosten

    exposure = float((gew.shift(1).sum(axis=1)).mean())
    if cfg.vola_ziel:
        rv = port.rolling(20).std() * np.sqrt(TRADING_DAYS)
        skala = (cfg.vola_ziel / rv).clip(upper=cfg.max_hebel).shift(1).fillna(0.0)
        port = port * skala
        kosten = kosten * skala

    port = port.iloc[H + 1:]
    kosten = kosten.iloc[H + 1:]
    bench = (benchmark.pct_change() if benchmark is not None else pd.Series(0.0, index=port.index))
    bench = bench.reindex(port.index).fillna(0.0)
    equity = (1 + port).cumprod()
    umschlag = float(aktiv.mean() * TRADING_DAYS / H * 2)
    return PortfolioErgebnis(equity=equity, renditen=port, benchmark=bench, cfg=cfg,
                             umschlag_pa=umschlag,
                             kosten_pa=float(kosten.mean() * TRADING_DAYS),
                             exposure=exposure,
                             universum=(universum_ew.reindex(port.index)
                                        if universum_ew is not None else None))


def zscore_querschnitt(f: pd.DataFrame, clip: float = 3.0) -> pd.DataFrame:
    """Je Tag standardisieren - Grundlage fuer Kombinationen."""
    m = f.mean(axis=1)
    s = f.std(axis=1).replace(0, np.nan)
    return f.sub(m, axis=0).div(s, axis=0).clip(-clip, clip)


def kombinieren(faktoren: dict[str, pd.DataFrame], gewichte: dict[str, float]) -> pd.DataFrame:
    """Gleichgewichtete Z-Score-Kombination. Bewusst runde Gewichte."""
    acc = None
    for name, w in gewichte.items():
        z = zscore_querschnitt(faktoren[name]) * w
        acc = z if acc is None else acc.add(z, fill_value=0.0)
    return acc


# ===========================================================================
# 7. Statistik-Helfer
# ===========================================================================
def deflated_sharpe(sharpe: float, n_versuche: int, n_tage: int,
                    skew: float = 0.0, kurt: float = 3.0) -> float:
    """Wahrscheinlichkeit, dass ein beobachteter Sharpe echt ist, wenn
    `n_versuche` Varianten probiert wurden (Bailey & Lopez de Prado 2014).

    Vereinfacht: erwartetes Maximum von n Zufalls-Sharpes ~ sqrt(2 ln n) /
    sqrt(T) (annualisiert), dann Normalapproximation.
    """
    from scipy.stats import norm

    if n_tage < 30 or not np.isfinite(sharpe):
        return float("nan")
    sr_tag = sharpe / np.sqrt(TRADING_DAYS)
    sr0 = np.sqrt(2 * np.log(max(n_versuche, 2))) / np.sqrt(n_tage)
    var = (1 - skew * sr_tag + (kurt - 1) / 4 * sr_tag ** 2) / (n_tage - 1)
    if var <= 0:
        return float("nan")
    return float(norm.cdf((sr_tag - sr0) / np.sqrt(var)))


def jahres_ic_tabelle(df: pd.DataFrame, faktoren: list[str] | None = None,
                      horizont: int = 21) -> pd.DataFrame:
    sub = df[df["horizont"] == horizont]
    if faktoren:
        sub = sub[sub["faktor"].isin(faktoren)]
    cols = [c for c in sub.columns if c.startswith("ic_")]
    return sub.set_index("faktor")[["ic", "t_deflated", "anteil_jahre_positiv"] + cols]
