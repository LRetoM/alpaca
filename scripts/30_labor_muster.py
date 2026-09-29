#!/usr/bin/env python3
"""Schritt 30: Chartmuster und Explosions-Vorlaeufer - ehrlich gemessen.

Zwei Fragen, zwei Teile:

TEIL A - Regelbasierte Chartmuster als Faktoren. Kein Auge, keine Formation
"die man sieht", sondern eindeutige Rechenvorschriften auf OHLCV. Jedes
Muster wird wie jeder andere Faktor gemessen: Querschnitts-IC je Tag ueber
5/21/63 Tage, Vorzeichenstabilitaet je Jahr, und fuer 0/1-Muster die mittlere
Vorwaertsrendite MIT gegen OHNE Muster (in Prozentpunkten, gleicher Tag).

    kompression      Bollinger-Bandbreite gegen ihren 120-Tage-Median (eng = hoch)
    nr7              engste Tagesspanne der letzten 7 Tage (Inside/NR7-Setup)
    donchian_20      Schluss ueber dem 20-Tage-Hoch (Ausbruch)
    ausbruch_52w_vol Schluss >= 98 % des 52-Wochen-Hochs UND Volumen-Z > 1
    drei_rot         >= 3 Verlusttage in Folge (Umkehr-Setup)
    hammer           nach >= 3 Verlusttagen Schluss im oberen Drittel der Spanne, Volumen-Z > 1
    golden_cross_5d  SMA50 hat SMA200 in den letzten 5 Tagen von unten gekreuzt
    death_cross_5d   dito von oben (erwartet negativ)
    gap_up_vol       Eroeffnungsluecke > 3 % mit Volumen-Z > 1 (gemessen: kehrt um)

TEIL B - Ereignisstudie "was ging Explosionen voraus?" mit dem vorhandenen
Werkzeug (events.py, features.py, ml.py): Alle Bewegungen >= +50 % in 60
Tagen, Beobachtungsfenster 120 Tage mit 5 Tagen Sperrzone, Kontrollgruppe
gleiches Symbol / anderer Zeitpunkt, Cohens d je Merkmal, und ein
walk-forward Klassifikator (AUC out-of-sample; 0,5 = Zufall).

    python scripts/30_labor_muster.py --panel qlib --start 2006-01-01
    python scripts/30_labor_muster.py --panel projekt --max-events 1500

Erwartung, vorab: Volatilitaetskompression und Volumen tragen etwas (wann,
nicht wohin), klassische Formationen nicht. Gap-ups negativ. Die
Ereignisstudie findet Unterschiede (Vola, Volumen, Drawdown-Zustand), aber
mit AUC < 0,65 - Explosionen sind selten und im Vorfeld nur schwach
erkennbar. Wer hier AUC > 0,75 findet, hat ein Leck.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from alpaca_bot import events, features, labor, ml  # noqa: E402
from alpaca_bot.config import PROJECT_ROOT  # noqa: E402

LABOR_DIR = PROJECT_ROOT / "data" / "labor"
OUT_DIR = PROJECT_ROOT / "results" / "labor"


# ---------------------------------------------------------------------------
# Teil A
# ---------------------------------------------------------------------------
def muster_faktoren(p: labor.Panel) -> tuple[dict[str, pd.DataFrame], set[str]]:
    c, h, l, o, v = p.close, p.high, p.low, p.open, p.volume
    r1 = c.pct_change()
    out: dict[str, pd.DataFrame] = {}
    binaer: set[str] = set()

    sd = c.rolling(20, min_periods=15).std()
    bw = (4 * sd) / c.rolling(20, min_periods=15).mean()
    out["kompression"] = -(bw / bw.rolling(120, min_periods=80).median())

    if h is not None and l is not None:
        spanne = (h - l)
        out["nr7"] = (spanne <= spanne.rolling(7, min_periods=7).min()).astype("float32")
        binaer.add("nr7")
        out["donchian_20"] = (c > h.shift(1).rolling(20, min_periods=15).max()).astype("float32")
        binaer.add("donchian_20")
    if v is not None:
        logv = np.log(v.replace(0, np.nan))
        vz = (logv - logv.rolling(60, min_periods=45).mean()) / logv.rolling(60, min_periods=45).std()
        hi52 = (h if h is not None else c).rolling(252, min_periods=120).max()
        out["ausbruch_52w_vol"] = ((c >= 0.98 * hi52) & (vz > 1.0)).astype("float32")
        binaer.add("ausbruch_52w_vol")
        if o is not None:
            gap = o / c.shift(1) - 1
            out["gap_up_vol"] = ((gap > 0.03) & (vz > 1.0)).astype("float32")
            binaer.add("gap_up_vol")
    runter = (r1 < 0).astype("float32")
    drei = (runter.rolling(3, min_periods=3).sum() >= 3)
    out["drei_rot"] = drei.astype("float32")
    binaer.add("drei_rot")
    if h is not None and l is not None and v is not None:
        lage = (c - l) / (h - l).replace(0, np.nan)
        out["hammer"] = (drei.shift(1) & (lage > 0.66) & (vz > 1.0)).astype("float32")
        binaer.add("hammer")
    sma50, sma200 = c.rolling(50, min_periods=45).mean(), c.rolling(200, min_periods=180).mean()
    ueber = (sma50 > sma200).astype("float32")
    kreuz_auf = ((ueber - ueber.shift(1)) > 0).rolling(5, min_periods=1).max()
    kreuz_ab = ((ueber - ueber.shift(1)) < 0).rolling(5, min_periods=1).max()
    out["golden_cross_5d"] = kreuz_auf.astype("float32")
    out["death_cross_5d"] = kreuz_ab.astype("float32")
    binaer |= {"golden_cross_5d", "death_cross_5d"}
    return {k: vv.replace([np.inf, -np.inf], np.nan) for k, vv in out.items()}, binaer


def binaer_spanne(f: pd.DataFrame, fwd: pd.DataFrame, maske: pd.DataFrame) -> tuple[float, float, int]:
    """Mittlere Vorwaertsrendite mit Muster minus ohne, je Tag gemittelt; t-Wert; Anzahl Signale."""
    fm, r = f.align(fwd, join="inner")
    m = maske.reindex_like(fm).fillna(False)
    mit = r.where((fm == 1) & m).mean(axis=1)
    ohne = r.where((fm == 0) & m).mean(axis=1)
    d = (mit - ohne).dropna()
    n = int(((fm == 1) & m).sum().sum())
    if len(d) < 30:
        return np.nan, np.nan, n
    return float(d.mean()), float(d.mean() / (d.std(ddof=1) / np.sqrt(len(d)))), n


def teil_a(p: labor.Panel, maske: pd.DataFrame, horizonte: tuple[int, ...]) -> pd.DataFrame:
    fakt, binaer = muster_faktoren(p)
    df = labor.ic_messen(fakt, p, horizonte=horizonte, maske=maske, verbose=False)
    rows = []
    for h in horizonte:
        fwd = labor.vorwaertsrendite(p, h)
        for name in binaer:
            if name not in fakt:
                continue
            spanne, t, n = binaer_spanne(fakt[name], fwd, maske)
            rows.append({"faktor": name, "horizont": h, "mit_minus_ohne_pct": spanne * 100 if np.isfinite(spanne) else np.nan,
                         "t_spanne": t / np.sqrt(h) if np.isfinite(t) else np.nan, "n_signale": n})
    sp = pd.DataFrame(rows)
    if not df.empty and not sp.empty:
        df = df.merge(sp, on=["faktor", "horizont"], how="left")
    return df


# ---------------------------------------------------------------------------
# Teil B
# ---------------------------------------------------------------------------
def panel_zu_bars(p: labor.Panel, symbole: list[str]) -> pd.DataFrame:
    frames = []
    for s in symbole:
        df = pd.DataFrame({"open": p.open[s], "high": p.high[s], "low": p.low[s],
                           "close": p.close[s], "volume": p.volume[s]}).dropna(subset=["close"])
        df.index = pd.DatetimeIndex(df.index).tz_localize("UTC")
        df["symbol"] = s
        frames.append(df)
    out = pd.concat(frames)
    out.index.name = "timestamp"
    return out.set_index("symbol", append=True).swaplevel().sort_index()


def teil_b(p: labor.Panel, maske: pd.DataFrame, *, max_symbole: int, max_events: int,
           controls: int, seed: int = 42) -> str:
    rng = np.random.default_rng(seed)
    liquide = maske.mean(axis=0)
    syms = list(liquide[liquide > 0.5].sort_values(ascending=False).index[:max_symbole])
    bars = panel_zu_bars(p, syms)
    cfg = events.EventConfig(threshold=0.5, window=60, lookback=120, blackout=5,
                             min_price=3.0, min_dollar_volume=1_000_000)
    ev = events.find_events(bars, cfg)
    n_alle = len(ev)
    if len(ev) > max_events:
        ev = ev.sample(max_events, random_state=seed).sort_values("t0").reset_index(drop=True)
    ctrl = events.sample_controls(bars, ev, cfg, n_per_event=controls, seed=seed)
    spy = p.close["SPY"] if "SPY" in p.close.columns else None
    X, y, meta = events.build_dataset(bars, ev, ctrl, lambda w: features.build_features(w), cfg)
    if X.empty:
        return "  Keine Ereignisse gefunden."
    X = X.drop(columns=[c for c in ("dow", "month") if c in X.columns])
    vergleich = events.compare_groups(X, y, top=12)
    L = ["=" * 92, f"  EXPLOSIONEN (>= +50 % in 60 Tagen): {n_alle:,} gefunden, {len(ev):,} untersucht, "
         f"{len(ctrl):,} Kontrollen, {len(syms):,} Symbole", "=" * 92,
         f"  Median Rendite bis Spitze {ev['return'].median():+.0%}, Tage bis Spitze Median {ev['days_to_peak'].median():.0f}, "
         f"Rueckschlag vor Spitze Median {ev['max_drawdown_before_peak'].median():+.0%}",
         "", "  Wodurch unterscheiden sich Explosionen VORHER von Kontrollen (Cohens d):",
         vergleich.to_string(index=False), ""]
    # Walk-forward-Klassifikator in Zeitreihenfolge
    order = np.argsort(pd.DatetimeIndex(meta["t0"]).values)
    Xo, yo = X.iloc[order].reset_index(drop=True), y.iloc[order].reset_index(drop=True)
    Xo = Xo.fillna(Xo.median())
    try:
        res = ml.walk_forward_predict(Xo, yo, "gbm", n_splits=5, embargo=60, min_train=max(250, len(Xo) // 4))
        L += [f"  Walk-forward GBM: AUC {res.auc:.3f} (0,5 = Zufall), Accuracy {res.accuracy:.3f}, "
              f"Basisrate {yo.mean():.3f}", res.fold_scores.round(3).to_string(index=False)]
        # Negativtest: Labels zeitlich mischen
        y_mix = pd.Series(rng.permutation(yo.to_numpy()), index=yo.index)
        res0 = ml.walk_forward_predict(Xo, y_mix, "gbm", n_splits=5, embargo=60, min_train=max(250, len(Xo) // 4))
        L += [f"  Negativtest (Labels gemischt): AUC {res0.auc:.3f} - muss ~0,5 sein"]
    except Exception as e:  # noqa: BLE001
        L += [f"  Klassifikator nicht moeglich: {type(e).__name__}: {e}"]
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--panel", required=True)
    ap.add_argument("--start", default=None)
    ap.add_argument("--ende", default=None)
    ap.add_argument("--horizonte", type=int, nargs="+", default=[5, 21, 63])
    ap.add_argument("--min-dollar-volume", type=float, default=5_000_000)
    ap.add_argument("--max-symbole", type=int, default=1500)
    ap.add_argument("--max-events", type=int, default=1500)
    ap.add_argument("--controls", type=int, default=5)
    ap.add_argument("--nur", choices=["a", "b"], default=None)
    args = ap.parse_args()

    t0 = time.time()
    panel = labor.panel_aus_cache(LABOR_DIR / args.panel).schneiden(args.start, args.ende)
    print(f"  {panel.beschreibung()}")
    if panel.open is None or panel.volume is None:
        print("  Panel ohne OHLCV - Muster nicht messbar.")
        return 1
    etfs = {"SPY", "QQQ", "IWM", "DIA", "VTI", "EEM", "EFA", "TLT", "GLD", "HYG", "USO", "BNO"}
    p_akt = panel.filtern([s for s in panel.symbole if s not in etfs])
    maske = labor.liquides_universum(p_akt, min_dollar_volume=args.min_dollar_volume)
    # Speicher: nur Symbole behalten, die an >= 10 % der Tage zugelassen sind -
    # alle anderen tragen weder zum Querschnitt noch zum Portfolio bei.
    haeufig = maske.columns[maske.mean(axis=0) >= 0.10]
    p_akt = p_akt.filtern(list(haeufig))
    maske = maske[list(haeufig)]
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    if args.nur != "b":
        df = teil_a(p_akt, maske, tuple(args.horizonte))
        df.to_csv(OUT_DIR / f"muster_{args.panel}.csv", index=False)
        print()
        print("=" * 110)
        print("  TEIL A - CHARTMUSTER ALS FAKTOREN")
        print("=" * 110)
        cols = ["faktor", "horizont", "ic", "t_deflated", "anteil_jahre_positiv", "schlechtestes_jahr",
                "mit_minus_ohne_pct", "t_spanne", "n_signale", "urteil"]
        print(df[[c for c in cols if c in df.columns]].round(4).to_string(index=False))
        print("  mit_minus_ohne_pct = mittlere Vorwaertsrendite (in %-Punkten) an Tagen MIT Muster minus OHNE, gleicher Tag")

    if args.nur != "a":
        print()
        print(teil_b(p_akt, maske, max_symbole=args.max_symbole, max_events=args.max_events,
                     controls=args.controls))
    print(f"\n  ({time.time() - t0:.0f} s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
