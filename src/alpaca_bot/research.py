"""Faktor-Labor: erst messen, dann bauen.

Der teuerste Fehler des letzten Durchlaufs war die Reihenfolge. Es wurde
eine Strategie aus Faktoren gebaut, die plausibel klangen (Momentum,
Naehe zum Jahreshoch, Volatilitaetskompression) - und erst danach
gemessen. Ergebnis: IC von -0.05, die Faktoren rangierten in die
FALSCHE Richtung, die Strategie verlor 127 Prozentpunkte gegen Buy & Hold.

Die Ursache war kein Programmierfehler, sondern eine Verwechslung von
Zeithorizonten: Momentum wirkt ueber 3-12 Monate, gehandelt wurde mit 17
Tagen Haltedauer. Auf kurzer Sicht dominiert die Gegenbewegung.

Dieses Modul dreht die Reihenfolge um. Es misst viele Kandidaten ueber
mehrere Horizonte auf dem gesamten Universum und liefert eine Rangliste.
In die Strategie darf danach nur, was hier nachweislich positiv rangiert.

**Was hier gemessen wird - und was nicht:**

  * Gemessen wird der Information Coefficient (Rangkorrelation zwischen
    Faktorwert und tatsaechlicher Folgerendite).
  * Der IC wird QUERSCHNITTLICH je Tag berechnet, nicht ueber den
    gesamten Datenberg. Der Unterschied ist entscheidend: Ein globaler
    IC misst zu grossen Teilen, ob 2020 besser war als 2022 - also den
    Markt, nicht den Faktor. Der taegliche Querschnitts-IC misst genau
    das, was eine Rangliste braucht: Trennt der Faktor an EINEM Tag die
    guten von den schlechten Aktien?
  * Der t-Wert des mittleren IC sagt, ob der Effekt ueber die Zeit stabil
    ist. |t| > 2 gilt als brauchbar, |t| > 3 als solide.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import indicators as ind
from . import statistik


# ---------------------------------------------------------------------------
# Kandidaten-Faktoren
# ---------------------------------------------------------------------------
def candidate_factors(df: pd.DataFrame) -> pd.DataFrame:
    """Berechnet alle Kandidaten fuer EIN Symbol. Strikt kausal.

    Bewusst breit angelegt und mit gegenlaeufigen Hypothesen: Sowohl
    Momentum- als auch Umkehr-Varianten sind enthalten. Welche Richtung
    auf welchem Horizont traegt, entscheidet die Messung - nicht die
    Erwartung.
    """
    c = df["close"].astype(float)
    out = pd.DataFrame(index=df.index)

    # --- Kurzfristige Umkehr (Hypothese: gefallen -> Gegenbewegung) ---
    for n in (1, 2, 3, 5, 10):
        out[f"reversal_{n}d"] = -c.pct_change(n)

    out["rsi2"] = -ind.rsi(c, 2) / 100
    out["rsi14"] = -ind.rsi(c, 14) / 100

    bb = ind.bollinger(c, 20)
    out["bb_unten"] = -bb["bb_pct"]
    out["bb_breite"] = bb["bb_width"]

    # --- Mittelfristiges Momentum (Hypothese: laeuft weiter) ---
    out["mom_21d"] = c.pct_change(21)
    out["mom_63d"] = c.pct_change(63)
    out["mom_126d"] = c.pct_change(126)
    out["mom_252_21"] = c.pct_change(252).shift(21)

    # --- Abstand zu Durchschnitten ---
    for w in (10, 20, 50, 200):
        out[f"dist_sma{w}"] = c / ind.sma(c, w) - 1

    high_252 = c.rolling(252, min_periods=60).max()
    out["naehe_52w_hoch"] = c / high_252
    low_252 = c.rolling(252, min_periods=60).min()
    out["abstand_52w_tief"] = c / low_252 - 1

    # --- Volatilitaet ---
    out["vola_20"] = ind.realized_volatility(c, 20)
    out["vola_niedrig"] = -out["vola_20"]
    v10 = ind.realized_volatility(c, 10)
    v60 = ind.realized_volatility(c, 60)
    out["vola_verhaeltnis"] = v10 / v60

    if {"high", "low"}.issubset(df.columns):
        atr = ind.atr(df, 14)
        out["atr_pct"] = atr / c
        spanne = (df["high"] - df["low"]).replace(0, np.nan)
        # Wo im Tagesbereich schloss der Kurs? Naehe Tief = Schwaeche.
        out["schluss_lage"] = (c - df["low"]) / spanne

    # --- Volumen ---
    if "volume" in df.columns:
        v = df["volume"].astype(float)
        dv = v * c
        out["volumen_z"] = ind.zscore(dv, 20)
        out["volumen_schub"] = dv.rolling(5).mean() / dv.rolling(60).mean()
        # Illiquiditaet nach Amihud: Kursbewegung je Umsatzeinheit
        out["amihud"] = (c.pct_change().abs() / dv.replace(0, np.nan)).rolling(20).mean()
        # Ausverkauf: starker Rueckgang MIT hohem Volumen
        out["ausverkauf"] = (-c.pct_change(3)).clip(lower=0) * out["volumen_z"].clip(lower=0)

    # --- Drawdown-Zustand ---
    out["drawdown"] = c / c.cummax() - 1
    out["drawdown_tiefe"] = -out["drawdown"]

    return out.replace([np.inf, -np.inf], np.nan)


# ---------------------------------------------------------------------------
# Messung
# ---------------------------------------------------------------------------
@dataclass
class FactorResult:
    factor: str
    horizon: int
    ic_mean: float
    """Mittlerer taeglicher Querschnitts-IC."""
    ic_std: float
    t_stat: float
    """ic_mean / (ic_std / sqrt(n_tage)) - OHNE Ueberlappungskorrektur.

    Steht nur noch zum Vergleich hier. Massgeblich ist `t_korrigiert`;
    bis zum 22.08.2026 war dieser Wert das Auswahlkriterium, und er faellt
    systematisch zu hoch aus (`docs/BEFUNDE.md` §G12).
    """
    n_days: int
    n_obs: int
    hit_rate: float
    """Anteil der Tage mit positivem IC. 0.5 = Zufall."""
    q5_minus_q1: float
    """Renditedifferenz oberstes minus unterstes Quintil."""
    t_korrigiert: float = float("nan")
    """t_stat, korrigiert um die Ueberlappung der Renditefenster.

    Bei Horizont `h` teilen sich benachbarte Tages-ICs `h-1` von `h`
    Tagen ihres Fensters. DAS ist der Wert, gegen den eine Schwelle
    geprueft wird.
    """
    aufblaehung: float = float("nan")
    """Um welchen Faktor `t_stat` zu hoch war. 1,0 = keine Ueberlappung."""

    @property
    def verdict(self) -> str:
        # Bewusst `t_korrigiert`: das Urteil ist der Ort, an dem der
        # aufgeblaehte Wert am teuersten waere. Faellt die Korrektur aus
        # (NaN), gilt der unkorrigierte Wert - aber dann steht in der
        # Ausgabe auch keine Aufblaehung, das faellt auf.
        t = self.t_korrigiert if np.isfinite(self.t_korrigiert) else self.t_stat
        if abs(t) < 2:
            return "Rauschen"
        if self.ic_mean > 0:
            return "NUETZLICH" if self.ic_mean > 0.01 else "schwach positiv"
        return "INVERTIERT" if self.ic_mean < -0.01 else "schwach negativ"


def measure_factors(
    bars: pd.DataFrame,
    horizons: tuple[int, ...] = (3, 5, 10, 20),
    min_symbols_per_day: int = 30,
    verbose: bool = True,
) -> pd.DataFrame:
    """Misst alle Kandidaten-Faktoren ueber das gesamte Universum.

    Args:
        bars: MultiIndex (symbol, timestamp) mit OHLCV.
        horizons: Prognosehorizonte in Handelstagen.
        min_symbols_per_day: Tage mit weniger Symbolen werden verworfen -
            eine Rangkorrelation ueber 5 Werte ist reines Rauschen.

    Returns:
        Eine Zeile je (Faktor, Horizont), sortiert nach Aussagekraft.
    """
    symbols = bars.index.get_level_values("symbol").unique()
    if verbose:
        print(f"      Berechne Faktoren fuer {len(symbols):,} Symbole ...")

    factor_frames: dict[str, pd.DataFrame] = {}
    fwd_frames: dict[int, dict[str, pd.Series]] = {h: {} for h in horizons}

    for i, sym in enumerate(symbols, 1):
        df = bars.xs(sym, level="symbol").sort_index()
        if len(df) < 280:
            continue
        try:
            f = candidate_factors(df)
        except Exception:  # noqa: BLE001
            continue
        factor_frames[sym] = f
        c = df["close"].astype(float)
        for h in horizons:
            fwd_frames[h][sym] = c.shift(-h) / c - 1
        if verbose and i % 500 == 0:
            print(f"      {i:,}/{len(symbols):,} Symbole ...")

    if not factor_frames:
        return pd.DataFrame()

    factor_names = list(next(iter(factor_frames.values())).columns)
    if verbose:
        print(f"      {len(factor_frames):,} Symbole verwertbar, "
              f"{len(factor_names)} Faktoren, {len(horizons)} Horizonte")

    results: list[FactorResult] = []
    for h in horizons:
        fwd_panel = pd.DataFrame(fwd_frames[h])
        for name in factor_names:
            panel = pd.DataFrame(
                {sym: f[name] for sym, f in factor_frames.items() if name in f}
            )
            common = panel.index.intersection(fwd_panel.index)
            if len(common) < 30:
                continue
            panel, fwd = panel.loc[common], fwd_panel.loc[common]

            ic, spread, n_valid = _daily_cross_sectional_ic(
                panel, fwd, min_symbols_per_day
            )
            ic = ic.dropna()
            if len(ic) < 30:
                continue

            # Chronologisch - `newey_west_t` liest die Autokorrelation aus
            # der Reihenfolge, eine unsortierte Reihe ergaebe Unsinn.
            ic = ic.sort_index()
            arr = ic.to_numpy()
            mean, std = float(arr.mean()), float(arr.std(ddof=1))
            t = mean / (std / np.sqrt(len(arr))) if std > 0 else 0.0
            t_korr, aufbl = (statistik.newey_west_t(arr, lag=h - 1)
                             if h > 1 else (float(t), 1.0))
            sp = spread.reindex(ic.index).dropna()

            results.append(FactorResult(
                factor=name, horizon=h, ic_mean=mean, ic_std=std, t_stat=float(t),
                n_days=len(arr), n_obs=int(n_valid.reindex(ic.index).sum()),
                hit_rate=float((arr > 0).mean()),
                q5_minus_q1=float(sp.mean()) if len(sp) else float("nan"),
                t_korrigiert=float(t_korr), aufblaehung=float(aufbl),
            ))
        if verbose:
            print(f"      Horizont {h} Tage fertig")

    if not results:
        return pd.DataFrame()

    df = pd.DataFrame([{**r.__dict__, "verdict": r.verdict} for r in results])
    # Nach dem KORRIGIERTEN Wert sortieren. Die Rangliste ist das, was
    # gelesen wird; stuende oben, was nur unkorrigiert gross aussieht,
    # waere die Korrektur folgenlos.
    schluessel = df["t_korrigiert"].fillna(df["t_stat"]).abs()
    return df.reindex(schluessel.sort_values(ascending=False).index).reset_index(drop=True)


def _daily_cross_sectional_ic(
    panel: pd.DataFrame, fwd: pd.DataFrame, min_symbols: int
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Spearman-IC je Tag ueber den Querschnitt - vollstaendig vektorisiert.

    Eine Schleife ueber 1.300 Tage x 30 Faktoren x 4 Horizonte waere
    156.000 Einzelkorrelationen und damit unbrauchbar langsam. Da Spearman
    nichts anderes ist als Pearson auf Raengen, laesst sich alles als
    Matrixoperation schreiben.

    Returns: (IC je Tag, Quintil-Spanne je Tag, Anzahl gueltiger Symbole je Tag)
    """
    valid = panel.notna() & fwd.notna()
    n = valid.sum(axis=1)

    p = panel.where(valid)
    f = fwd.where(valid)

    pr = p.rank(axis=1)
    fr = f.rank(axis=1)

    # Zentrieren, ungueltige Felder auf 0 (tragen dann nichts bei)
    prc = pr.sub(pr.mean(axis=1), axis=0).where(valid, 0.0)
    frc = fr.sub(fr.mean(axis=1), axis=0).where(valid, 0.0)

    num = (prc * frc).sum(axis=1)
    den = np.sqrt((prc**2).sum(axis=1) * (frc**2).sum(axis=1))
    ic = (num / den.replace(0, np.nan)).where(n >= min_symbols)

    # Quintil-Spanne: oberstes minus unterstes Fuenftel derselben Zeile
    q = pr.div(n, axis=0)
    top = f.where(q > 0.8).mean(axis=1)
    bot = f.where(q <= 0.2).mean(axis=1)
    spread = (top - bot).where(n >= min_symbols)

    return ic, spread, n


def measure_stability(
    bars: pd.DataFrame,
    factors: list[str],
    horizon: int = 20,
    min_symbols_per_day: int = 30,
    verbose: bool = True,
) -> pd.DataFrame:
    """Haelt ein Faktor auch in verschiedenen Marktphasen?

    Der wichtigste Folgetest nach `measure_factors`. Ein Faktor kann ueber
    den Gesamtzeitraum glaenzend aussehen und trotzdem wertlos sein - naemlich
    dann, wenn er nur Marktbeta abbildet.

    Beispiel: In einer Hausse laufen schwankungsstarke Aktien besser. Ein
    Volatilitaetsfaktor zeigt dann einen schoenen positiven IC. Er misst
    aber nicht Prognosekraft, sondern Hebelwirkung - und dreht im
    Baerenmarkt ins Gegenteil.

    Ein Faktor ist nur brauchbar, wenn sein Vorzeichen ueber die Jahre
    STABIL bleibt. Wechselt es, ist er ein Beta-Stellvertreter.
    """
    symbols = bars.index.get_level_values("symbol").unique()
    factor_frames, fwd_frames = {}, {}

    for sym in symbols:
        df = bars.xs(sym, level="symbol").sort_index()
        if len(df) < 280:
            continue
        try:
            f = candidate_factors(df)
        except Exception:  # noqa: BLE001
            continue
        keep = [c for c in factors if c in f.columns]
        if not keep:
            continue
        factor_frames[sym] = f[keep]
        c = df["close"].astype(float)
        fwd_frames[sym] = c.shift(-horizon) / c - 1

    if not factor_frames:
        return pd.DataFrame()

    fwd_panel = pd.DataFrame(fwd_frames)
    rows = []
    for name in factors:
        panel = pd.DataFrame(
            {s: f[name] for s, f in factor_frames.items() if name in f}
        )
        common = panel.index.intersection(fwd_panel.index)
        if len(common) < 60:
            continue
        ic, _, _ = _daily_cross_sectional_ic(
            panel.loc[common], fwd_panel.loc[common], min_symbols_per_day
        )
        ic = ic.dropna()
        if ic.empty:
            continue
        for year, grp in ic.groupby(ic.index.year):
            if len(grp) < 30:
                continue
            arr = grp.to_numpy()
            std = arr.std(ddof=1)
            rows.append({
                "factor": name, "jahr": int(year),
                "ic": float(arr.mean()),
                "t": float(arr.mean() / (std / np.sqrt(len(arr)))) if std > 0 else 0.0,
                "tage": len(arr),
            })

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    # Vorzeichenstabilitaet je Faktor verdichten
    summary = df.groupby("factor").agg(
        jahre=("jahr", "size"),
        ic_mittel=("ic", "mean"),
        jahre_positiv=("ic", lambda s: int((s > 0).sum())),
        schlechtestes_jahr=("ic", "min"),
        bestes_jahr=("ic", "max"),
    )
    summary["anteil_positiv"] = summary["jahre_positiv"] / summary["jahre"]
    summary["stabil"] = summary["anteil_positiv"] >= 0.75
    return df.merge(summary.reset_index(), on="factor", how="left")


def stability_report(stab: pd.DataFrame) -> str:
    """Jahr-fuer-Jahr-Tabelle mit Urteil zur Vorzeichenstabilitaet."""
    if stab.empty:
        return "Keine Stabilitaetsdaten."
    pivot = stab.pivot_table(index="factor", columns="jahr", values="ic")
    summ = stab.groupby("factor").first()[
        ["ic_mittel", "anteil_positiv", "schlechtestes_jahr", "stabil"]
    ]

    lines = ["=" * 92, "  VORZEICHENSTABILITAET JE JAHR", "=" * 92, ""]
    header = f"  {'Faktor':<20}" + "".join(f"{c:>9}" for c in pivot.columns)
    lines += [header + f"{'Ø':>9}{'pos.':>7}  Urteil", "  " + "-" * 88]
    for f in pivot.index:
        row = f"  {f:<20}" + "".join(
            f"{pivot.loc[f, c]:>+9.3f}" if pd.notna(pivot.loc[f, c]) else f"{'-':>9}"
            for c in pivot.columns
        )
        s = summ.loc[f]
        verdict = "STABIL" if s["stabil"] else "instabil -> Beta-Verdacht"
        lines.append(row + f"{s['ic_mittel']:>+9.3f}{s['anteil_positiv']:>7.0%}  {verdict}")

    lines += [
        "",
        "  Ein Faktor, dessen Vorzeichen jaehrlich wechselt, misst die Marktphase,",
        "  nicht die Aktie. Solche Faktoren gehoeren NICHT in die Strategie -",
        "  sie funktionieren genau so lange, wie die Hausse dauert.",
    ]
    return "\n".join(lines)


def summarize(results: pd.DataFrame, top: int = 25) -> str:
    """Lesbare Rangliste der Faktoren."""
    if results.empty:
        return "Keine Ergebnisse."
    lines = [
        "=" * 92,
        "  FAKTOR-RANGLISTE  (taeglicher Querschnitts-IC, sortiert nach |t korr.|)",
        "=" * 92,
        f"  {'Faktor':<20}{'Hor.':>5}{'IC':>9}{'t korr.':>9}{'t roh':>8}"
        f"{'Aufbl.':>8}{'Trefferq.':>10}{'Tage':>7}  Bewertung",
        "  " + "-" * 88,
    ]
    for _, r in results.head(top).iterrows():
        tk = r.get("t_korrigiert", float("nan"))
        ab = r.get("aufblaehung", float("nan"))
        # Alte Ergebnistabellen (vor §G12) haben diese beiden Spalten nicht.
        # Dann steht hier ein Strich - und NICHT der rohe Wert an der Stelle
        # des korrigierten, wo er als korrigiert gelesen wuerde.
        sp_korr = f"{tk:>+9.1f}" if pd.notna(tk) else f"{'-':>9}"
        sp_aufbl = f"{ab:>7.2f}x" if pd.notna(ab) else f"{'-':>8}"
        lines.append(
            f"  {r['factor']:<20}{int(r['horizon']):>5}{r['ic_mean']:>+9.4f}"
            f"{sp_korr}{r['t_stat']:>+8.1f}{sp_aufbl}"
            f"{r['hit_rate']:>10.1%}{int(r['n_days']):>7}  {r['verdict']}"
        )
    lines += [
        "",
        "  Lesart:",
        "    IC       mittlere taegliche Rangkorrelation Faktor <-> Folgerendite",
        "    t korr.  MASSGEBLICH. Um die Ueberlappung der Renditefenster",
        "             bereinigt (Newey-West). |t|>2 brauchbar, |t|>3 solide",
        "    t roh    ohne diese Bereinigung - nur zum Vergleich, nie zitieren",
        "    Aufbl.   um welchen Faktor 't roh' zu hoch war. Haengt an der",
        "             Traegheit des Faktors: 1,0x bei taeglich wechselnden,",
        "             bis 1,8x bei traegen (§G12)",
        "",
        "  Ein hoher |t| bei winzigem IC ist normal und gut: Der Effekt ist klein,",
        "  aber verlaesslich. Genau darauf baut das Fundamentalgesetz (IR = IC x sqrt(BR)).",
    ]
    return "\n".join(lines)


def select_factors(
    results: pd.DataFrame, horizon: int, min_t: float = 3.0, max_factors: int = 6,
    max_correlation: float = 0.7, factor_data: dict[str, pd.DataFrame] | None = None
) -> list[str]:
    """Waehlt die tragfaehigen Faktoren fuer einen Horizont aus.

    Kriterien: ausreichend stabil (|t| >= min_t) und positiv rangierend.
    Negative Faktoren werden NICHT einfach invertiert - ein Vorzeichen,
    das nur auf dieser Stichprobe stimmt, ist Data-Mining. Wer invertiert,
    muss die Hypothese vorher aufschreiben.

    Geprueft wird `t_korrigiert`, nicht `t_stat`. Dies ist die Stelle, an
    der aus einer Messung eine Strategie wird - genau hier hat der
    unkorrigierte Wert am 16.08.2026 Faktoren durchgelassen, die die
    Schwelle nach Korrektur nicht halten (`docs/BEFUNDE.md` §G12).
    """
    sub = results[results["horizon"] == horizon].copy()
    t = sub["t_korrigiert"].fillna(sub["t_stat"]) if "t_korrigiert" in sub else sub["t_stat"]
    sub = sub[(t >= min_t) & (sub["ic_mean"] > 0)]
    sub = sub.reindex(t[t.index.isin(sub.index)].sort_values(ascending=False).index)
    return sub["factor"].head(max_factors).tolist()
