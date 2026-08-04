"""Gewinnmeldungen als Faktorquelle - PEAD sauber pruefbar machen.

Der Post-Earnings-Announcement-Drift (Bernard & Thomas 1989) ist die am
besten replizierte Anomalie der Finanzforschung: Nach einer
Gewinnueberraschung laeuft der Kurs ueber WOCHEN in dieselbe Richtung
weiter, statt die Information sofort einzupreisen.

**Warum das zu diesem Projekt passt:** Die laufende Umkehr-Strategie
entscheidet auf dem Schlusskurs und handelt zur naechsten Eroeffnung
(siehe live.build_snapshot). Signale, die nur in der ersten Minute nach
einer Meldung existieren, sind damit strukturell unerreichbar. PEAD
dagegen wirkt ueber Tage bis Wochen - genau das Zeitfenster, das dieser
Bot bedienen KANN.

**Zwei Faktoren, bewusst getrennt gemessen:**

    pead_ueberraschung   Surprise(%) aus der Analystenschaetzung
    pead_reaktion        Kursreaktion am Meldetag gegen den Markt

Die Trennung ist keine Spielerei. `pead_reaktion` wird ausschliesslich
aus Kursen berechnet und ist damit zeitpunktsicher. `pead_ueberraschung`
stammt aus yfinance und traegt ein bekanntes Risiko (siehe unten). Zeigen
beide dasselbe Bild, stuetzt das den Befund; zeigen sie Verschiedenes,
liegt es an der Datenquelle und nicht am Effekt.

**WARNUNG - yfinance schreibt die Vergangenheit um** (docs/schattenbetrieb.md
§3.4): `get_earnings_dates()` liefert die HEUTE gespeicherte Schaetzung,
nicht die, die am Meldetag galt. Analystenschaetzungen werden nachtraeglich
revidiert. `pead_ueberraschung` ist deshalb ein SCREENING-Faktor fuer den
billigen Historientest - kein Beleg. Der Vorwaertstest im Schattenbetrieb
ist die einzige Bestaetigung, die zaehlt (hypotheses.py).

**Zeitpunktsicherheit beim Zusammenfuehren:** Eine Meldung um 16:00 ET
erscheint NACH dem Schlusskurs desselben Tages. Wer sie auf die Bar
dieses Tages legt, hat ein Leck - der Kurs von 16:00 kennt die Zahl noch
nicht. `_reaktionstag()` loest das ueber die Uhrzeit in New Yorker Zeit:

    Meldung vor 16:00 ET  ->  der Markt reagiert am SELBEN Tag
    Meldung ab  16:00 ET  ->  der Markt reagiert am NAECHSTEN Handelstag

Gemessen wird die Vorwaertsrendite immer ab dem SCHLUSSKURS des
Reaktionstages. Die Sprungbewegung der Meldung selbst ist damit
ausgeschlossen - genau das ist die Frage bei PEAD: Was kommt NACH der
ersten Reaktion noch?
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd

from .config import CACHE_DIR
from .ratelimit import RateLimiter, with_retry

TERMIN_CACHE = CACHE_DIR / "earnings"
TERMIN_CACHE.mkdir(parents=True, exist_ok=True)

# Ab wann gilt eine Meldung als "nach Boersenschluss"? 16:00 New Yorker Zeit.
SCHLUSS_STUNDE_ET = 16

# Wie lange nach der Meldung gilt der Faktor als aktiv? Bernard & Thomas
# messen den Drift ueber ~60 Handelstage. Laenger waere kein PEAD mehr,
# kuerzer schneidet den Effekt ab, den man messen will.
DRIFT_FENSTER_TAGE = 60


def _termin_datei(n_symbole: int, schluessel: str) -> Path:
    """Tagesgenauer Cache. Meldetermine aendern sich nur durch neue Quartale -
    ein Abruf je Kalendertag reicht, und der Cache spart 800 yfinance-Aufrufe."""
    heute = dt.date.today().isoformat()
    return TERMIN_CACHE / f"{heute}_{n_symbole}_{schluessel}.parquet"


def _stabiler_schluessel(symbols: list[str]) -> str:
    """hashlib statt Pythons eingebautem hash(): Der ist pro Prozessstart
    zufaellig gesalzen (Hash-Randomisierung seit Python 3.3) - ein zweiter
    Skriptlauf am selben Tag haette einen ANDEREN Schluessel bekommen, den
    Cache faelschlich als leer angesehen und alle Termine neu abgerufen.
    Exakt dieses Muster steckte bereits in `datasources.get_history` und
    wurde dort in `shadow.lade_bars` bewusst umgangen (siehe Kommentar
    dort) - hier direkt richtig gemacht statt den Fehler zu wiederholen."""
    import hashlib

    return hashlib.sha256("|".join(symbols).encode()).hexdigest()[:10]


def hole_termine(
    symbols: list[str], *, limit_je_symbol: int = 60,
    use_cache: bool = True, verbose: bool = True,
) -> pd.DataFrame:
    """Meldetermine samt Schaetzung und Ueberraschung, je Symbol ein Abruf.

    Laeuft ueber die yfinance-Drossel (60/min, 2000/Tag) und damit
    vollstaendig getrennt vom Alpaca-Kontingent des Handelsbots. Der
    laufende Betrieb wird dadurch nicht beruehrt - das ist Absicht und
    der Grund, warum hier nicht `data.get_bars` verwendet wird.

    Returns:
        DataFrame mit symbol, meldung_ts (UTC), eps_schaetzung,
        eps_gemeldet, ueberraschung_pct
    """
    import yfinance as yf

    syms = sorted(set(symbols))
    cache = _termin_datei(len(syms), _stabiler_schluessel(syms))
    if use_cache and cache.exists():
        if verbose:
            print(f"      aus Cache: {cache.name}")
        return pd.read_parquet(cache)

    limiter = RateLimiter("yfinance")
    zeilen: list[dict] = []
    fehler = 0

    for i, sym in enumerate(syms, 1):
        limiter.acquire()
        try:
            ed = with_retry(
                lambda s=sym: yf.Ticker(s).get_earnings_dates(limit=limit_je_symbol),
                retries=1,
            )
        except Exception:  # noqa: BLE001 - einzelne Ausfaelle sind normal
            fehler += 1
            continue
        if ed is None or ed.empty:
            fehler += 1
            continue

        for ts, row in ed.iterrows():
            zeilen.append({
                "symbol": sym,
                "meldung_ts": pd.Timestamp(ts).tz_convert("UTC"),
                "meldung_et": pd.Timestamp(ts).tz_convert("America/New_York"),
                "eps_schaetzung": _zahl(row.get("EPS Estimate")),
                "eps_gemeldet": _zahl(row.get("Reported EPS")),
                "ueberraschung_pct": _zahl(row.get("Surprise(%)")),
            })

        if verbose and i % 100 == 0:
            print(f"      Termine: {i}/{len(syms)} Symbole, "
                  f"{len(zeilen):,} Meldungen, {fehler} ohne Daten")

    if not zeilen:
        return pd.DataFrame(columns=["symbol", "meldung_ts", "meldung_et",
                                     "eps_schaetzung", "eps_gemeldet",
                                     "ueberraschung_pct"])

    df = pd.DataFrame(zeilen).sort_values(["symbol", "meldung_ts"])
    df = df.reset_index(drop=True)
    if use_cache:
        df.to_parquet(cache)
    if verbose:
        print(f"      {len(df):,} Meldungen fuer "
              f"{df['symbol'].nunique()} Symbole ({fehler} ohne Daten)")
    return df


def _zahl(x) -> float:
    try:
        v = float(x)
        return v if np.isfinite(v) else np.nan
    except (TypeError, ValueError):
        return np.nan


def _reaktionstag(meldung_et: pd.Timestamp, handelstage: pd.DatetimeIndex) -> pd.Timestamp | None:
    """Der erste Handelstag, an dem der Markt auf die Meldung reagieren KANN.

    Die Uhrzeit entscheidet. Eine Meldung um 16:05 ET erreicht den Markt
    erst am Folgetag; eine um 07:00 ET noch am selben. Wer das ignoriert
    und stets denselben Tag nimmt, baut bei jeder zweiten Meldung ein Leck
    ein - und PEAD sieht dann grandios aus, weil der Sprung der Meldung
    selbst mitgemessen wird.
    """
    datum = meldung_et.normalize().tz_localize(None)
    if meldung_et.hour >= SCHLUSS_STUNDE_ET:
        kandidaten = handelstage[handelstage > datum]
    else:
        kandidaten = handelstage[handelstage >= datum]
    return kandidaten[0] if len(kandidaten) else None


def baue_panel(
    termine: pd.DataFrame,
    bars: pd.DataFrame,
    *,
    markt_symbol: str = "SPY",
    drift_fenster: int = DRIFT_FENSTER_TAGE,
    verbose: bool = True,
) -> dict[str, pd.DataFrame]:
    """Baut die Faktortafeln (Zeilen = Handelstage, Spalten = Symbole).

    Ein Faktorwert steht an jedem Tag im Driftfenster nach einer Meldung.
    Ausserhalb ist er NaN - dort gibt es keine These, und ein Nullwert
    waere eine Aussage, die niemand treffen wollte.

    Returns:
        {"pead_ueberraschung": DataFrame, "pead_reaktion": DataFrame}
    """
    if bars.empty or termine.empty:
        return {}

    close = bars["close"].unstack(level="symbol").sort_index()
    close.index = pd.DatetimeIndex(close.index).tz_localize(None).normalize()
    close = close[~close.index.duplicated(keep="last")]
    handelstage = close.index

    markt = close[markt_symbol] if markt_symbol in close.columns else None
    if markt is None and verbose:
        print(f"      WARNUNG: {markt_symbol} fehlt - `pead_reaktion` wird "
              "ohne Marktbereinigung gerechnet (schwaecher, aber nutzbar).")

    tagesrendite = close.pct_change()
    markt_rendite = markt.pct_change() if markt is not None else None

    ueberraschung = pd.DataFrame(np.nan, index=handelstage, columns=close.columns)
    reaktion = pd.DataFrame(np.nan, index=handelstage, columns=close.columns)
    # Alter in Handelstagen seit der Meldung. Ohne diese Tafel laesst sich
    # der Zerfall nicht messen - und der Zerfall IST die Signatur von PEAD.
    alter = pd.DataFrame(np.nan, index=handelstage, columns=close.columns)

    bekannt = set(close.columns)
    n_verwendet = 0

    for _, m in termine.iterrows():
        sym = m["symbol"]
        if sym not in bekannt:
            continue
        tag = _reaktionstag(pd.Timestamp(m["meldung_et"]), handelstage)
        if tag is None:
            continue

        pos = handelstage.get_loc(tag)
        if isinstance(pos, slice):
            continue
        ende = min(pos + drift_fenster, len(handelstage) - 1)
        if ende <= pos:
            continue
        fenster = handelstage[pos : ende + 1]

        # --- Faktor 1: die gemeldete Ueberraschung ---
        u = m["ueberraschung_pct"]
        if np.isfinite(u):
            ueberraschung.loc[fenster, sym] = u

        # --- Faktor 2: die Kursreaktion am Reaktionstag, marktbereinigt ---
        r = tagesrendite[sym].iloc[pos] if pos < len(tagesrendite) else np.nan
        if np.isfinite(r):
            if markt_rendite is not None:
                r = r - markt_rendite.iloc[pos]
            reaktion.loc[fenster, sym] = r

        alter.loc[fenster, sym] = np.arange(len(fenster), dtype=float)
        n_verwendet += 1

    if verbose:
        print(f"      {n_verwendet:,} Meldungen ins Panel uebernommen "
              f"(Driftfenster {drift_fenster} Handelstage)")

    return {"pead_ueberraschung": ueberraschung, "pead_reaktion": reaktion,
            "_alter": alter}


def vorwaertsrenditen(bars: pd.DataFrame, horizonte=(5, 10, 20, 40)) -> dict[int, pd.DataFrame]:
    """Rendite ab dem SCHLUSSKURS des Tages, ueber `h` Handelstage.

    Bewusst ab dem Schlusskurs und nicht ab der Eroeffnung: Das ist
    dieselbe Bezugsgroesse, mit der `research.measure_factors` arbeitet,
    und damit sind die Ergebnisse untereinander vergleichbar.
    """
    close = bars["close"].unstack(level="symbol").sort_index()
    close.index = pd.DatetimeIndex(close.index).tz_localize(None).normalize()
    close = close[~close.index.duplicated(keep="last")]
    return {h: close.shift(-h) / close - 1 for h in horizonte}


def kennzahlen(faktor: pd.DataFrame, fwd: pd.DataFrame,
               min_symbole: int = 10) -> dict:
    """Querschnitts-IC je Tag, plus t-Wert ueber die Tagesreihe.

    Nutzt dieselbe Rechnung wie `research._daily_cross_sectional_ic` -
    Spearman ueber den Querschnitt, dann Mittelwert und t-Wert ueber die
    Tage. Ein Faktor ohne |t| > 2 ueber mehrere Jahre bindet keine
    weitere Zeit.
    """
    from .research import _daily_cross_sectional_ic

    gemeinsam = faktor.index.intersection(fwd.index)
    spalten = faktor.columns.intersection(fwd.columns)
    f = faktor.loc[gemeinsam, spalten]
    r = fwd.loc[gemeinsam, spalten]

    ic, spread, n = _daily_cross_sectional_ic(f, r, min_symbole)
    ic = ic.dropna()
    if len(ic) < 20:
        return {"n_tage": int(len(ic)), "ic": np.nan, "t": np.nan,
                "quintil_spanne": np.nan, "n_beobachtungen": 0}

    t = ic.mean() / (ic.std(ddof=1) / np.sqrt(len(ic)))
    sp = spread.reindex(ic.index).dropna()
    return {
        "n_tage": int(len(ic)),
        "n_beobachtungen": int((f.notna() & r.notna()).sum().sum()),
        "ic": round(float(ic.mean()), 5),
        "t": round(float(t), 2),
        "quintil_spanne": round(float(sp.mean()), 5) if len(sp) else np.nan,
        "anteil_positive_tage": round(float((ic > 0).mean()), 3),
    }


def placebo_permutation(faktor: pd.DataFrame, fwd: pd.DataFrame,
                        *, seed: int = 42, min_symbole: int = 10) -> dict:
    """Die richtige Kontrolle: Faktorwerte je TAG unter den Symbolen tauschen.

    Warum nicht einfach den Faktor zeitlich verschieben? Weil das eine
    Scheinkontrolle waere: Wer heute den Wert von in 90 Tagen einsetzt,
    benutzt echte Zukunftsinformation. Eine Firma, die in drei Monaten
    stark uebertrifft, ist bis dahin meist ohnehin gestiegen - ein so
    gebauter "Placebo" sieht deshalb IMMER stark aus und widerlegt nichts.

    Diese Fassung laesst Zeitstruktur und Werteverteilung exakt gleich und
    zerstoert AUSSCHLIESSLICH die Zuordnung Wert -> Symbol. Bleibt der IC
    danach bestehen, misst der Faktor eine Tageseigenschaft (etwa "an
    Meldetagen bewegt sich alles staerker") und nicht die Ueberraschung
    eines bestimmten Unternehmens. Er faellt korrekterweise auf ~0, wenn
    der Effekt echt symbolspezifisch ist.
    """
    rng = np.random.default_rng(seed)
    werte = faktor.to_numpy(copy=True)
    for i in range(werte.shape[0]):
        zeile = werte[i]
        gueltig = np.flatnonzero(np.isfinite(zeile))
        if gueltig.size > 1:
            zeile[gueltig] = zeile[rng.permutation(gueltig)]
    getauscht = pd.DataFrame(werte, index=faktor.index, columns=faktor.columns)
    return kennzahlen(getauscht, fwd, min_symbole)


def ic_nach_alter(
    faktor: pd.DataFrame, alter: pd.DataFrame, fwd: pd.DataFrame,
    baender: tuple[tuple[int, int], ...] = ((0, 5), (5, 10), (10, 20),
                                            (20, 40), (40, 60)),
    min_symbole: int = 10,
) -> pd.DataFrame:
    """IC aufgeschluesselt nach Handelstagen seit der Meldung.

    **Das ist die eigentliche Prueffrage.** Echter PEAD ist unmittelbar
    nach der Meldung am staerksten und klingt ab - die Information wird
    nach und nach eingepreist. Ein Faktor, dessen IC ueber alle Baender
    KONSTANT bleibt, misst dagegen keine Meldung, sondern eine dauerhafte
    Eigenschaft des Unternehmens (Qualitaet, Sektor, Groesse). Beides
    ergibt denselben Gesamt-IC und ist doch etwas voellig anderes:
    Nur das erste ist handelbar, weil nur das erste einen Zeitpunkt hat,
    an dem man einsteigen muss.
    """
    zeilen = []
    for lo, hi in baender:
        maske = (alter >= lo) & (alter < hi)
        k = kennzahlen(faktor.where(maske), fwd, min_symbole)
        k["band"] = f"{lo}-{hi}"
        zeilen.append(k)
    df = pd.DataFrame(zeilen).set_index("band")
    return df[["n_tage", "n_beobachtungen", "ic", "t"]]


def eigenstaendigkeit(
    faktor: pd.DataFrame, bars: pd.DataFrame, fwd: pd.DataFrame,
    *, gegen: tuple[str, ...] = ("reversal_3d", "rsi2", "ausverkauf", "bb_unten"),
    min_symbole: int = 10, verbose: bool = True,
) -> pd.DataFrame:
    """Bringt der Faktor NEUE Information - oder misst er die Umkehr nochmal?

    **Das ist die Frage, die ueber den Nutzen entscheidet.** Ein neuer
    Faktor mit IC 0.03 ist wertlos, wenn er mit `reversal_3d` zu 0.9
    korreliert - dann ist er derselbe Faktor unter anderem Namen, und die
    Kombination bringt keinen einzigen Basispunkt zusaetzlich. Genau davor
    warnt `signals.ReversalWeights`: Die dortigen fuenf Bausteine messen
    im Kern dasselbe, weshalb ihre Summe eben NICHT fuenfmal so viel
    Signal ist.

    Gemessen wird zweierlei:
      * die Querschnittskorrelation zum jeweiligen Bestandsfaktor,
      * der IC des Faktors, NACHDEM der Bestandsfaktor herausgerechnet
        wurde (Residual-IC). Bleibt der bestehen, ist die Information
        wirklich neu.
    """
    from .research import _daily_cross_sectional_ic, candidate_factors

    close_idx = faktor.index
    # candidate_factors EINMAL je Symbol - nicht je Bestandsfaktor erneut.
    # Bei 800 Symbolen und vier Faktoren waere das sonst der Vierfache
    # Aufwand fuer exakt dasselbe Ergebnis.
    gesammelt: dict[str, dict[str, pd.Series]] = {n: {} for n in gegen}
    for sym in bars.index.get_level_values("symbol").unique():
        try:
            df = bars.xs(sym, level="symbol")
        except KeyError:
            continue
        if len(df) < 260:
            continue
        f = candidate_factors(df)
        idx = pd.DatetimeIndex(f.index).tz_localize(None).normalize()
        for name in gegen:
            if name not in f.columns:
                continue
            s = f[name]
            s.index = idx
            gesammelt[name][sym] = s[~s.index.duplicated(keep="last")]

    bestand = {n: pd.DataFrame(sp).reindex(close_idx)
               for n, sp in gesammelt.items() if sp}
    if verbose:
        print(f"      Bestandsfaktoren berechnet: {', '.join(bestand)}")

    zeilen = []
    for name, tafel in bestand.items():
        spalten = faktor.columns.intersection(tafel.columns)
        a = faktor[spalten]
        b = tafel[spalten]
        gueltig = a.notna() & b.notna()

        # Querschnittskorrelation je Tag, dann Mittel ueber die Tage.
        korr = a.where(gueltig).corrwith(b.where(gueltig), axis=1,
                                         method="spearman")
        korr = korr.dropna()

        # Residual: den Bestandsfaktor je Tag herausrechnen (Rangebene).
        ar = a.where(gueltig).rank(axis=1)
        br = b.where(gueltig).rank(axis=1)
        arz = ar.sub(ar.mean(axis=1), axis=0)
        brz = br.sub(br.mean(axis=1), axis=0)
        beta = ((arz * brz).sum(axis=1)
                / (brz**2).sum(axis=1).replace(0, np.nan))
        residual = arz.sub(brz.mul(beta, axis=0))

        ic_res, _, _ = _daily_cross_sectional_ic(
            residual, fwd.reindex(index=close_idx, columns=spalten), min_symbole
        )
        ic_res = ic_res.dropna()
        t_res = (ic_res.mean() / (ic_res.std(ddof=1) / np.sqrt(len(ic_res)))
                 if len(ic_res) > 2 else np.nan)

        zeilen.append({
            "bestandsfaktor": name,
            "korrelation": round(float(korr.mean()), 3) if len(korr) else np.nan,
            "residual_ic": round(float(ic_res.mean()), 5) if len(ic_res) else np.nan,
            "residual_t": round(float(t_res), 2) if np.isfinite(t_res) else np.nan,
        })

    return pd.DataFrame(zeilen).set_index("bestandsfaktor") if zeilen else pd.DataFrame()


def jahresstabilitaet(faktor: pd.DataFrame, fwd: pd.DataFrame,
                      min_symbole: int = 10) -> pd.DataFrame:
    """IC je Kalenderjahr - der eigentliche Haerttest.

    Ein Faktor, der ueber den Gesamtzeitraum gut aussieht, aber sein
    Vorzeichen jaehrlich wechselt, ist kein Faktor, sondern eine
    Zufallsfolge mit einem guten Jahr. Genau diese Pruefung hat bei den
    Umkehr-Faktoren entschieden, welche aufgenommen wurden
    (signals.ReversalWeights: "nur was in JEDEM Jahr dasselbe Vorzeichen
    hatte").
    """
    from .research import _daily_cross_sectional_ic

    gemeinsam = faktor.index.intersection(fwd.index)
    spalten = faktor.columns.intersection(fwd.columns)
    f = faktor.loc[gemeinsam, spalten]
    r = fwd.loc[gemeinsam, spalten]
    ic, _, _ = _daily_cross_sectional_ic(f, r, min_symbole)
    ic = ic.dropna()
    if ic.empty:
        return pd.DataFrame()

    je_jahr = ic.groupby(ic.index.year).agg(
        n_tage="size", ic="mean",
        t=lambda s: s.mean() / (s.std(ddof=1) / np.sqrt(len(s))) if len(s) > 2 else np.nan,
    )
    return je_jahr.round(4)
