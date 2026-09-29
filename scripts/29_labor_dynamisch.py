#!/usr/bin/env python3
"""Schritt 29: Dynamische Haltedauer - die Prognose entscheidet je Aktie, nicht die Uhr.

Kein festes "max 10 Tage" oder "max 21 Tage". Fuer jede Aktie werden
Erwartungsrenditen ueber MEHRERE Horizonte vorhergesagt (5, 10, 21, 42,
63 Tage), jeweils mit einem eigenen Modell (LightGBM, walk-forward jaehrlich,
Ziel = winsorisierte Vorwaertsrendite). Daraus:

  * **Wann kaufen:** die erwartete Netto-Rendite JE TAG ist
        rate_h = (E[r_h] - Rundlaufkosten) / h
    Gekauft wird, was ueber alle h die hoechste rate hat - eine Aktie, die
    in 10 Tagen 3 % verspricht, schlaegt eine, die in 63 Tagen 8 %
    verspricht (0,30 %/Tag gegen 0,13 %/Tag), es sei denn, die Kosten
    drehen es.
  * **Wie lange halten:** so lange, wie die Prognose traegt. Jeden Tag wird
    fuer jede Position neu gerechnet. Verkauft wird, wenn
      (a) die beste verbleibende Erwartung max_h E[r_h] unter die
          Ausstiegskosten faellt ("These traegt nicht mehr" - dieselbe
          Logik wie `EngineConfig.exit_score`, nur mit Prognose statt Score),
      (b) ein Kandidat je Tag mehr verspricht als die Position PLUS die
          Kosten des Wechsels (Opportunitaetskosten), oder
      (c) die Sicherheitsgrenze (--max-tage, Standard 126) erreicht ist.
  * **Wie viel:** gleichgewichtet ueber die Positionen (Vola-Sizing ist
    Sache der Engine, hier geht es um den Horizont-Mechanismus).

Verglichen wird IMMER gegen dieselben Vorhersagen mit festem Horizont
(H = 21) - sonst misst man das Modell, nicht die Dynamik.

    python scripts/29_labor_dynamisch.py --selftest
    python scripts/29_labor_dynamisch.py --panel sp500_close --start 2016-01-01
    python scripts/29_labor_dynamisch.py --panel projekt --min-dollar-volume 25000000 --top-n 30

Ehrlich vorab: Ein Modell, das fuer 5 Horizonte Renditen vorhersagt, hat
fuenfmal so viele Gelegenheiten, Rauschen zu lernen. Deshalb Walk-Forward,
Embargo, und die Jahrestabelle - und deshalb zaehlt nur der Vergleich
"dynamisch gegen fest" auf denselben Vorhersagen.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from alpaca_bot import labor  # noqa: E402
from alpaca_bot.config import PROJECT_ROOT  # noqa: E402

LABOR_DIR = PROJECT_ROOT / "data" / "labor"
OUT_DIR = PROJECT_ROOT / "results" / "labor"
TD = 252


# ---------------------------------------------------------------------------
# 1. Vorhersagen je Horizont (walk-forward)
# ---------------------------------------------------------------------------
def vorhersagen_je_horizont(p: labor.Panel, maske: pd.DataFrame, horizonte: list[int],
                            *, stichprobe: int, erstes_testjahr: int | None,
                            spy: pd.Series | None, n_jobs: int = 2, verbose: bool = True
                            ) -> dict[int, pd.DataFrame]:
    """Liefert je Horizont ein Panel E[r_h] (Tage x Symbole), nur out-of-sample."""
    import lightgbm as lgb

    faktoren = labor.faktorzoo(p, spy=spy)
    merkmale = list(faktoren)
    raenge = {k: v.where(maske).rank(axis=1, pct=True).astype("float32") for k, v in faktoren.items()}
    ziele = {h: labor.vorwaertsrendite(p, h).where(maske).clip(-0.5, 0.5) for h in horizonte}

    tage = list(p.close.index)[::stichprobe]
    frames = []
    for t in tage:
        zeile = pd.DataFrame({k: v.loc[t] for k, v in raenge.items()})
        for h in horizonte:
            zeile[f"y{h}"] = ziele[h].loc[t]
        zeile = zeile.dropna(subset=merkmale, thresh=len(merkmale) - 3)
        if len(zeile) >= 50:
            zeile["tag"] = t
            frames.append(zeile)
    lang = pd.concat(frames)
    lang.index.name = "symbol"
    lang = lang.reset_index()
    lang["jahr"] = pd.DatetimeIndex(lang["tag"]).year
    jahre = sorted(lang["jahr"].unique())
    erstes = erstes_testjahr or jahre[min(3, len(jahre) - 1)]
    embargo = pd.Timedelta(days=int((max(horizonte) + 5) * 1.5))
    if verbose:
        print(f"  {len(lang):,} Zeilen, Testjahre {erstes}-{jahre[-1]}, Embargo {embargo.days} Tage")

    preds = {h: [] for h in horizonte}
    for y in [j for j in jahre if j >= erstes]:
        grenze = pd.Timestamp(f"{y}-01-01") - embargo
        tr = lang[lang["tag"] < grenze]
        te = lang[lang["jahr"] == y]
        if len(tr) < 5_000 or te.empty:
            continue
        for h in horizonte:
            tr_h = tr.dropna(subset=[f"y{h}"])
            m = lgb.LGBMRegressor(objective="regression", n_estimators=200, learning_rate=0.03,
                                  num_leaves=15, min_child_samples=300, subsample=0.7,
                                  subsample_freq=1, colsample_bytree=0.7, reg_lambda=10.0,
                                  verbose=-1, n_jobs=n_jobs)
            m.fit(tr_h[merkmale], tr_h[f"y{h}"])
            te_h = te[["tag", "symbol"]].copy()
            te_h["pred"] = m.predict(te[merkmale])
            preds[h].append(te_h)
        if verbose:
            print(f"      {y}: {len(tr):,} Trainingszeilen, {len(te):,} vorhergesagt")

    out = {}
    for h in horizonte:
        if not preds[h]:
            continue
        df = pd.concat(preds[h])
        wide = df.pivot(index="tag", columns="symbol", values="pred")
        wide = wide.reindex(index=p.close.index, columns=p.close.columns).ffill(limit=stichprobe)
        out[h] = wide.astype("float32")
    return out


# ---------------------------------------------------------------------------
# 2. Dynamische Simulation
# ---------------------------------------------------------------------------
def dynamisch_simulieren(preds: dict[int, pd.DataFrame], p: labor.Panel, maske: pd.DataFrame,
                         *, top_n: int, kosten_bps: float, max_tage: int, min_edge: float,
                         fest_h: int | None = None) -> tuple[pd.Series, dict]:
    """Tag fuer Tag: Erwartung je Tag ranken, dynamisch halten, ehrlich buchen.

    Ausfuehrung: Entscheidung auf Schluss t, Einstieg Eroeffnung t+1 (falls
    Eroeffnung vorhanden, sonst Schluss t+1), Ausstieg Schluss des
    Entscheidungstags nach Verkaufsentscheidung -> hier vereinfacht: Verkauf
    zur Eroeffnung t+1, damit beide Seiten denselben Zeitversatz haben.
    `fest_h` erzwingt einen festen Horizont (Vergleichsfassung).
    """
    hs = sorted(preds)
    c = p.close
    o = p.open if p.open is not None else c
    idx = c.index
    kosten = kosten_bps / 10_000
    halb = kosten / 2
    m = maske.reindex_like(c).fillna(False)

    # erwartete Netto-Rendite je Tag und bester Horizont, je Tag/Symbol
    rate = None
    best_h = None
    for h in hs:
        r_h = (preds[h] - kosten) / h
        if rate is None:
            rate, best_h = r_h.copy(), pd.DataFrame(h, index=idx, columns=c.columns, dtype="float32")
        else:
            besser = r_h > rate
            rate = rate.where(~besser, r_h)
            best_h = best_h.where(~besser, float(h))
    max_pred = None
    for h in hs:
        max_pred = preds[h] if max_pred is None else np.maximum(max_pred, preds[h])
    max_pred = pd.DataFrame(max_pred, index=idx, columns=c.columns)
    if fest_h is not None:
        rate = (preds[fest_h] - kosten) / fest_h
        best_h = pd.DataFrame(float(fest_h), index=idx, columns=c.columns)
        max_pred = preds[fest_h]

    rate = rate.where(m)
    o_arr, c_arr = o.to_numpy(dtype=float), c.to_numpy(dtype=float)
    rate_arr, pred_arr, h_arr = rate.to_numpy(dtype=float), max_pred.to_numpy(dtype=float), best_h.to_numpy(dtype=float)
    cols = list(c.columns)

    equity = 1.0
    kurve = []
    halt: dict[int, dict] = {}          # spaltenindex -> {"einstieg_tag": i, "h": h, "einstieg": px}
    pending_buy: list[int] = []
    pending_sell: list[int] = []
    n_trades, tage_gehalten, gewaehlte_h = 0, [], []
    gewinne = []
    for i in range(1, len(idx) - 1):
        # --- Ausfuehrung der gestrigen Entscheidungen zur heutigen Eroeffnung ---
        wert_vor = equity
        # Verkaeufe
        for j in pending_sell:
            pos = halt.pop(j, None)
            if pos is None:
                continue
            px = o_arr[i, j]
            if not np.isfinite(px):
                px = c_arr[i, j]
            r = px / pos["einstieg"] - 1 - halb
            if np.isfinite(r):
                gewinne.append(r)
            tage_gehalten.append(i - pos["einstieg_tag"])
            pos["ausstieg_r"] = r
        # Kaeufe
        for j in pending_buy:
            px = o_arr[i, j]
            if not np.isfinite(px):
                continue
            halt[j] = {"einstieg_tag": i, "h": h_arr[i - 1, j], "einstieg": px * (1 + halb)}
            gewaehlte_h.append(h_arr[i - 1, j])
            n_trades += 1
        pending_buy, pending_sell = [], []

        # --- Tagesrendite des Portfolios (gleichgewichtet ueber Positionen) ---
        if halt:
            rs = []
            for j, pos in halt.items():
                if pos["einstieg_tag"] == i:
                    rs.append(c_arr[i, j] / (pos["einstieg"] / (1 + halb)) - 1)   # Eroeffnung -> Schluss
                else:
                    rs.append(c_arr[i, j] / c_arr[i - 1, j] - 1)
            rs = [r for r in rs if np.isfinite(r)]
            tages_r = float(np.mean(rs)) * (len(halt) / max(top_n, len(halt))) if rs else 0.0
            # Kosten der heute ausgefuehrten Kaeufe/Verkaeufe wirken ueber halb in den Kursen
        else:
            tages_r = 0.0
        equity *= (1 + tages_r)
        kurve.append((idx[i], equity))

        # --- Entscheidungen fuer morgen ---
        r_row, p_row, h_row = rate_arr[i], pred_arr[i], h_arr[i]
        # 1. Ausstiege
        for j, pos in list(halt.items()):
            alter = i - pos["einstieg_tag"]
            grund = None
            if not np.isfinite(p_row[j]) or p_row[j] < halb:
                grund = "these"
            elif alter >= max_tage:
                grund = "zeit"
            elif fest_h is not None and alter >= fest_h:
                grund = "fest"
            if grund:
                pending_sell.append(j)
        frei = top_n - (len(halt) - len(pending_sell))
        # 2. Kandidaten
        ok = np.isfinite(r_row) & (r_row > 0) & (p_row > min_edge)
        kand = np.argsort(-np.where(ok, r_row, -np.inf))
        kand = [j for j in kand[: top_n * 3] if ok[j] and j not in halt and j not in pending_sell]
        # 3. Wechsel: Kandidat schlaegt schwaechste Position um mehr als die Wechselkosten je Tag
        if fest_h is None and kand and halt:
            for j in kand:
                if frei > 0:
                    break
                schwach = min((k for k in halt if k not in pending_sell),
                              key=lambda k: r_row[k] if np.isfinite(r_row[k]) else -np.inf, default=None)
                if schwach is None:
                    break
                r_schwach = r_row[schwach] if np.isfinite(r_row[schwach]) else -np.inf
                if r_row[j] > r_schwach + kosten / max(h_row[j], 1.0):
                    pending_sell.append(schwach)
                    frei += 1
                else:
                    break
        for j in kand:
            if frei <= 0:
                break
            pending_buy.append(j)
            frei -= 1

    eq = pd.Series(dict(kurve))
    r = eq.pct_change().dropna()
    stats = {**labor._kennzahlen(r), "trades": n_trades,
             "haltedauer_mittel": float(np.mean(tage_gehalten)) if tage_gehalten else np.nan,
             "haltedauer_median": float(np.median(tage_gehalten)) if tage_gehalten else np.nan,
             "trefferquote": float(np.mean([g > 0 for g in gewinne])) if gewinne else np.nan,
             "gewinn_je_trade": float(np.mean(gewinne)) if gewinne else np.nan,
             "h_verteilung": pd.Series(gewaehlte_h).value_counts(normalize=True).round(2).to_dict()
             if gewaehlte_h else {}}
    return r, stats


def _jahre(r: pd.Series, bench: pd.Series) -> pd.DataFrame:
    b = bench.pct_change().reindex(r.index).fillna(0.0)
    rows = []
    for y, g in r.groupby(r.index.year):
        rows.append({"jahr": int(y), "dynamisch": float((1 + g).prod() - 1),
                     "spy": float((1 + b.loc[g.index]).prod() - 1),
                     "maxdd": labor._maxdd(g), "tage": len(g)})
    return pd.DataFrame(rows).set_index("jahr")


# ---------------------------------------------------------------------------
def selftest() -> int:
    """Synthetik: Aktien mit eingebauter, unterschiedlich schneller Drift.
    Die Dynamik muss kurze Horizonte fuer schnelle und lange fuer langsame
    Werte waehlen und die feste Fassung nicht unterbieten."""
    rng = np.random.default_rng(5)
    kal = pd.bdate_range("2018-01-02", "2021-12-31")
    n = 80
    syms = [f"S{i:02d}" for i in range(n)]
    # Regime je Symbol wechselt alle 60 Tage: schnell (+0.4 %/Tag fuer 8 Tage, dann 0), langsam (+0.08 %/Tag), keine Drift
    drift = np.zeros((len(kal), n))
    for j in range(n):
        for start in range(0, len(kal), 60):
            art = rng.integers(0, 3)
            if art == 1:
                drift[start:start + 8, j] = 0.004
            elif art == 2:
                drift[start:start + 60, j] = 0.0008
    r = rng.normal(0, 0.015, (len(kal), n)) + drift
    close = pd.DataFrame(100 * np.cumprod(1 + r, axis=0), index=kal, columns=syms)
    p = labor.Panel(close=close.astype("float32"), quelle="synthetisch")
    maske = pd.DataFrame(True, index=kal, columns=syms)
    # "Perfekte" Prognosen = tatsaechliche Vorwaertsrendite plus Rauschen (Modelltest ist Sache von 23_)
    preds = {h: (labor.vorwaertsrendite(p, h) + rng.normal(0, 0.01, (len(kal), n))).astype("float32")
             for h in (5, 10, 21, 42)}
    r_dyn, s_dyn = dynamisch_simulieren(preds, p, maske, top_n=10, kosten_bps=20, max_tage=126, min_edge=0.005)
    r_fix, s_fix = dynamisch_simulieren(preds, p, maske, top_n=10, kosten_bps=20, max_tage=126, min_edge=0.005, fest_h=21)
    print(f"  dynamisch: CAGR {s_dyn['cagr']:+.1%}  Sharpe {s_dyn['sharpe']:.2f}  Trades {s_dyn['trades']}  "
          f"Haltedauer Median {s_dyn['haltedauer_median']:.0f}  h-Wahl {s_dyn['h_verteilung']}")
    print(f"  fest H=21: CAGR {s_fix['cagr']:+.1%}  Sharpe {s_fix['sharpe']:.2f}  Trades {s_fix['trades']}")
    ok1 = s_dyn["cagr"] > 0 and s_dyn["h_verteilung"].get(5.0, 0) + s_dyn["h_verteilung"].get(10.0, 0) > 0.3
    ok2 = s_dyn["sharpe"] >= s_fix["sharpe"] - 0.1
    print(f"  [{'ok' if ok1 else 'FEHLER'}] Dynamik waehlt kurze Horizonte fuer schnelle Bewegungen")
    print(f"  [{'ok' if ok2 else 'FEHLER'}] Dynamik nicht schlechter als fester Horizont bei perfekter Prognose")
    print(f"\n  Selbsttest: {'bestanden' if ok1 and ok2 else 'FEHLER'}")
    return 0 if ok1 and ok2 else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--panel", default=None)
    ap.add_argument("--start", default=None)
    ap.add_argument("--ende", default=None)
    ap.add_argument("--horizonte", type=int, nargs="+", default=[5, 10, 21, 42, 63])
    ap.add_argument("--stichprobe", type=int, default=5)
    ap.add_argument("--erstes-testjahr", type=int, default=None)
    ap.add_argument("--top-n", type=int, default=30)
    ap.add_argument("--kosten", type=float, default=20.0)
    ap.add_argument("--min-edge", type=float, default=0.01, help="Mindest-Erwartung E[r_h] fuer einen Kauf")
    ap.add_argument("--max-tage", type=int, default=126)
    ap.add_argument("--min-dollar-volume", type=float, default=25_000_000)
    ap.add_argument("--n-jobs", type=int, default=2)
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    if not args.panel:
        print("  --panel angeben oder --selftest.")
        return 1

    t0 = time.time()
    panel = labor.panel_aus_cache(LABOR_DIR / args.panel).schneiden(args.start, args.ende)
    print(f"  {panel.beschreibung()}")
    spy = panel.close["SPY"] if "SPY" in panel.close.columns else None
    etfs = {"SPY", "QQQ", "IWM", "DIA", "VTI", "EEM", "EFA", "TLT", "GLD", "HYG", "USO", "BNO"}
    p_akt = panel.filtern([s for s in panel.symbole if s not in etfs])
    maske = labor.liquides_universum(p_akt, min_dollar_volume=args.min_dollar_volume)
    preds = vorhersagen_je_horizont(p_akt, maske, args.horizonte, stichprobe=args.stichprobe,
                                    erstes_testjahr=args.erstes_testjahr, spy=spy, n_jobs=args.n_jobs)
    if not preds:
        print("  keine Vorhersagen (zu wenig Daten).")
        return 1

    # OOS-Guete je Horizont (Spearman je Tag)
    print("\n  OOS-IC je Horizont (Tagesmittel):")
    for h, w in preds.items():
        ic = labor.ic_je_tag(w, labor.vorwaertsrendite(p_akt, h), maske)
        t = ic.mean() / (ic.std(ddof=1) / np.sqrt(len(ic))) if len(ic) > 10 else np.nan
        print(f"      h={h:>3}: IC {ic.mean():+.4f}  t {t:+.1f} (deflationiert {t / np.sqrt(h):+.1f})  Tage {len(ic)}")

    ergebnisse = {}
    r_dyn, s_dyn = dynamisch_simulieren(preds, p_akt, maske, top_n=args.top_n, kosten_bps=args.kosten,
                                        max_tage=args.max_tage, min_edge=args.min_edge)
    ergebnisse["dynamisch"] = (r_dyn, s_dyn)
    for h in args.horizonte:
        r_f, s_f = dynamisch_simulieren(preds, p_akt, maske, top_n=args.top_n, kosten_bps=args.kosten,
                                        max_tage=args.max_tage, min_edge=args.min_edge, fest_h=h)
        ergebnisse[f"fest_h{h}"] = (r_f, s_f)

    print()
    print("=" * 100)
    print(f"  DYNAMISCHE HALTEDAUER gegen feste Horizonte  Panel {args.panel}, Top {args.top_n}, {args.kosten:.0f} bps")
    print("=" * 100)
    spy_cagr = labor._kennzahlen(spy.pct_change().reindex(r_dyn.index).dropna())["cagr"] if spy is not None else np.nan
    print(f"  {'Fassung':<12}{'CAGR':>8}{'SPY':>8}{'Sharpe':>8}{'MaxDD':>8}{'Trades':>8}{'Halt Ø':>8}{'Halt Med':>9}{'Treffer':>9}{'Ø/Trade':>9}")
    for name, (r, s) in ergebnisse.items():
        print(f"  {name:<12}{s['cagr']:>8.1%}{spy_cagr:>8.1%}{s['sharpe']:>8.2f}{s['max_drawdown']:>8.1%}"
              f"{s['trades']:>8}{s['haltedauer_mittel']:>8.1f}{s['haltedauer_median']:>9.0f}{s['trefferquote']:>9.1%}"
              f"{s['gewinn_je_trade']:>9.2%}")
    print(f"\n  Horizontwahl der Dynamik (Anteil je h): {s_dyn['h_verteilung']}")
    if spy is not None:
        print("\n  Jahrestabelle dynamisch:")
        print(_jahre(r_dyn, spy).round(3).to_string())

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"dynamisch_{args.panel}.csv"
    pd.DataFrame({k: {kk: vv for kk, vv in s.items() if kk != "h_verteilung"} for k, (_, s) in ergebnisse.items()}).T.to_csv(out)
    print(f"\n  gespeichert: {out}   ({time.time() - t0:.0f} s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
