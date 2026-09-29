#!/usr/bin/env python3
"""Schritt 26: Opening Range Breakout auf "Stocks in Play" - der Daytrading-Test.

Die einzige Daytrading-Strategie mit sauberer, aktueller akademischer
Dokumentation: Zarattini, Barbon & Aziz (2024, SSRN 4729284) ueber 7.000
US-Aktien 2016-2023. Kernbefund dort: Der 5-Minuten-ORB auf ALLEN liquiden
Aktien bringt fast nichts (+29 % in 7 Jahren). Beschraenkt auf die 20 Aktien
mit dem hoechsten RELATIVEN VOLUMEN in den ersten 5 Minuten wird daraus
Sharpe ~2,4-2,8 bei Beta ~0. **Die Auswahl macht die Arbeit, nicht der
Ausbruch.** Genau das ist die Volumen-These, die du pruefen willst.

Regeln (wie im Paper, hier exakt operationalisiert):
  Universum   Kurs > 5 $, 14-Tage-Durchschnittsumsatz > 1 Mio. $, ATR(14) > 0,50 $
  Rel. Volumen  Volumen der ersten 5 Minuten / Mittel derselben 5 Minuten
              der letzten 14 Tage; nur Werte > 1,0 (100 %), Top 20 je Tag
  Richtung    erste 5-Minuten-Kerze gruen -> long ueber ihrem Hoch,
              rot -> short unter ihrem Tief (Short nur, wenn --mit-short)
  Einstieg    Stop-Order auf Hoch/Tief der Eroeffnungskerze, ab 09:35
  Stop        max(10 % ATR(14), Kerzenspanne) unter/ueber Einstieg
  Ziel        keins; Ausstieg zum Schluss (15:55) oder am Stop
  Groesse     1 % Risiko je Trade (Kapital x 1 % / Stopabstand), Hebel <= 4x
              gesamt, je Position <= Kapital / 5
  Kosten      Spread je Seite (--spread-bps) + Slippage; Stop-Fills mit
              Luecke werden am Eroeffnungskurs der Folgekerze gefuellt

Daten: Alpaca-Minutenbars (IEX-Feed, kostenlos, ab 2016). Vorsicht: IEX
deckt nur ~2 % des Volumens ab - das relative Volumen ist damit ein IEX-
relatives Volumen. Das ist ein echter Unterschied zum Paper (SIP) und wird
mitprotokolliert. `--feed sip` liefert bei 15 Minuten Verzoegerung
historisch die Vollansicht kostenlos (Alpaca Basic: `end` >= 15 min alt).

Budget: 1 Tag x 1.000 Symbole x 78 Fuenfminutenbars = 78.000 Bars = 8
Requests. 250 Tage -> 2.000 Requests -> ~11 Minuten bei 180/min. Das Skript
laedt tagesweise und cached unter data/cache/orb/, Abbruch und Neustart
sind unproblematisch.

    python scripts/26_labor_orb_intraday.py --selftest              # ohne Keys: Mechanik pruefen
    python scripts/26_labor_orb_intraday.py --start 2024-01-02 --ende 2024-12-31 --symbole-aus-universum 800
    python scripts/26_labor_orb_intraday.py --start 2022-01-03 --ende 2022-12-30 --mit-short --feed sip

Hinweis PDT: Seit 04.06.2026 gibt es die PDT-Regel nicht mehr (FINRA-Aenderung
von Rule 4210, SEC-Zustimmung 14.04.2026). compliance.py prueft sie noch -
fuer diesen Test irrelevant, weil hier nichts gehandelt wird.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from alpaca_bot.config import CACHE_DIR, PROJECT_ROOT  # noqa: E402

OUT_DIR = PROJECT_ROOT / "results" / "labor"
ORB_CACHE = CACHE_DIR / "orb"


@dataclass
class ORBConfig:
    kapital: float = 100_000.0
    risiko_je_trade: float = 0.01
    max_hebel: float = 4.0
    max_anteil_je_position: float = 0.20
    top_n: int = 20
    min_rel_volumen: float = 1.0
    min_preis: float = 5.0
    min_dollar_volume_14d: float = 1_000_000
    min_atr: float = 0.50
    stop_atr_anteil: float = 0.10
    spread_bps: float = 3.0
    slippage_bps: float = 2.0
    mit_short: bool = False
    eroeffnung: str = "09:30"
    range_minuten: int = 5
    schluss: str = "15:55"


@dataclass
class Trade:
    tag: pd.Timestamp
    symbol: str
    seite: str
    einstieg: float
    ausstieg: float
    stop: float
    qty: int
    grund: str
    rel_volumen: float
    pnl: float
    rendite_auf_risiko: float


# ---------------------------------------------------------------------------
# Kernlogik - reine Funktion auf einem Tag x Symbol
# ---------------------------------------------------------------------------
def orb_tag(bars: pd.DataFrame, cfg: ORBConfig, atr: float, rel_vol: float,
            kapital: float, seite_erlaubt: tuple[str, ...]) -> Trade | None:
    """Ein Handelstag, ein Symbol. `bars` = 5-Minuten-OHLCV des Tages (NY-Zeit)."""
    if bars.empty or len(bars) < 10:
        return None
    ersteres = bars.iloc[0]
    if ersteres["close"] == ersteres["open"]:
        return None
    seite = "long" if ersteres["close"] > ersteres["open"] else "short"
    if seite not in seite_erlaubt:
        return None
    spanne = float(ersteres["high"] - ersteres["low"])
    stop_abstand = max(cfg.stop_atr_anteil * atr, spanne)
    if stop_abstand <= 0:
        return None
    ausloeser = float(ersteres["high"]) if seite == "long" else float(ersteres["low"])
    risiko = kapital * cfg.risiko_je_trade
    qty = int(risiko / stop_abstand)
    qty = min(qty, int(kapital * cfg.max_anteil_je_position / max(ausloeser, 0.01)))
    if qty <= 0:
        return None
    kosten_seite = (cfg.spread_bps + cfg.slippage_bps) / 10_000

    rest = bars.iloc[1:]
    einstieg = None
    for ts, b in rest.iterrows():
        if seite == "long" and float(b["high"]) >= ausloeser:
            # Luecke ueber den Ausloeser: Fill an der Eroeffnung der Kerze
            einstieg = max(ausloeser, float(b["open"])) * (1 + kosten_seite)
            start_pos = rest.index.get_loc(ts)
            break
        if seite == "short" and float(b["low"]) <= ausloeser:
            einstieg = min(ausloeser, float(b["open"])) * (1 - kosten_seite)
            start_pos = rest.index.get_loc(ts)
            break
    if einstieg is None:
        return None

    stop = einstieg - stop_abstand if seite == "long" else einstieg + stop_abstand
    ausstieg, grund = None, "schluss"
    for ts, b in rest.iloc[start_pos:].iterrows():
        if seite == "long" and float(b["low"]) <= stop:
            ausstieg = min(stop, float(b["open"])) * (1 - kosten_seite)
            grund = "stop"
            break
        if seite == "short" and float(b["high"]) >= stop:
            ausstieg = max(stop, float(b["open"])) * (1 + kosten_seite)
            grund = "stop"
            break
    if ausstieg is None:
        letzte = float(rest["close"].iloc[-1])
        ausstieg = letzte * (1 - kosten_seite) if seite == "long" else letzte * (1 + kosten_seite)

    pnl = (ausstieg - einstieg) * qty if seite == "long" else (einstieg - ausstieg) * qty
    return Trade(tag=bars.index[0].normalize(), symbol="?", seite=seite, einstieg=einstieg,
                 ausstieg=ausstieg, stop=stop, qty=qty, grund=grund, rel_volumen=rel_vol,
                 pnl=float(pnl), rendite_auf_risiko=float(pnl / risiko))


def relatives_volumen(heute_erste: float, historie_erste: list[float]) -> float:
    """Volumen der ersten Kerze heute gegen den Mittelwert derselben Kerze der Vortage."""
    h = [x for x in historie_erste if np.isfinite(x) and x > 0]
    if len(h) < 5:
        return np.nan
    return float(heute_erste / np.mean(h))


# ---------------------------------------------------------------------------
# Tageslauf: Auswahl der Stocks in Play, dann Trades
# ---------------------------------------------------------------------------
def tag_simulieren(tag: pd.Timestamp, minuten: dict[str, pd.DataFrame],
                   erste_kerze_hist: dict[str, list[float]], tagesinfo: pd.DataFrame,
                   cfg: ORBConfig, kapital: float) -> list[Trade]:
    """`minuten`: symbol -> 5-Min-Bars des Tages. `tagesinfo`: symbol -> atr14, dv14, close_vortag."""
    kandidaten = []
    for sym, bars in minuten.items():
        if sym not in tagesinfo.index or bars.empty:
            continue
        info = tagesinfo.loc[sym]
        if info["close_vortag"] < cfg.min_preis or info["dv14"] < cfg.min_dollar_volume_14d \
                or info["atr14"] < cfg.min_atr:
            continue
        rv = relatives_volumen(float(bars["volume"].iloc[0]), erste_kerze_hist.get(sym, []))
        if not np.isfinite(rv) or rv < cfg.min_rel_volumen:
            continue
        kandidaten.append((sym, rv))
    kandidaten.sort(key=lambda x: -x[1])
    seiten = ("long", "short") if cfg.mit_short else ("long",)
    trades = []
    brutto_exposure = 0.0
    for sym, rv in kandidaten[: cfg.top_n]:
        t = orb_tag(minuten[sym], cfg, float(tagesinfo.loc[sym, "atr14"]), rv, kapital, seiten)
        if t is None:
            continue
        exposure = t.qty * t.einstieg
        if brutto_exposure + exposure > cfg.max_hebel * kapital:
            continue
        brutto_exposure += exposure
        t.symbol = sym
        trades.append(t)
    return trades


def auswerten(trades: list[Trade], cfg: ORBConfig) -> str:
    if not trades:
        return "  keine Trades"
    df = pd.DataFrame([t.__dict__ for t in trades])
    tag = df.groupby("tag")["pnl"].sum()
    eq = cfg.kapital + tag.cumsum()
    r = tag / cfg.kapital
    jahre = max(len(tag) / 252, 1e-9)
    cagr = (eq.iloc[-1] / cfg.kapital) ** (1 / jahre) - 1
    sharpe = r.mean() / r.std() * np.sqrt(252) if r.std() > 0 else np.nan
    dd = (eq / eq.cummax() - 1).min()
    L = ["=" * 78, "  ORB STOCKS-IN-PLAY - ERGEBNIS", "=" * 78,
         f"  Handelstage {len(tag):>6}   Trades {len(df):>7}   je Tag {len(df) / len(tag):>5.1f}",
         f"  Trefferquote {float((df['pnl'] > 0).mean()):>6.1%}   Ø R je Trade {df['rendite_auf_risiko'].mean():>+6.2f}"
         f"   Profit-Faktor {df.loc[df.pnl > 0, 'pnl'].sum() / max(1e-9, -df.loc[df.pnl <= 0, 'pnl'].sum()):>5.2f}",
         f"  Rendite {eq.iloc[-1] / cfg.kapital - 1:>+8.1%}   CAGR {cagr:>+7.1%}   Sharpe {sharpe:>5.2f}   MaxDD {dd:>6.1%}",
         f"  Ausstiege: {df['grund'].value_counts().to_dict()}",
         "",
         "  Nach Jahr:"]
    for y, g in df.groupby(df["tag"].dt.year):
        L.append(f"    {y}: {len(g):>5} Trades, PnL {g['pnl'].sum():>+10,.0f} $, "
                 f"Treffer {float((g['pnl'] > 0).mean()):.0%}, Ø R {g['rendite_auf_risiko'].mean():+.2f}")
    L += ["", "  Nach Rel.-Volumen-Band:"]
    df["rv_band"] = pd.cut(df["rel_volumen"], [0, 1.5, 2, 3, 5, 1e9])
    for b, g in df.groupby("rv_band", observed=True):
        L.append(f"    {str(b):<14} {len(g):>5} Trades, Ø R {g['rendite_auf_risiko'].mean():+.2f}, "
                 f"Treffer {float((g['pnl'] > 0).mean()):.0%}")
    L += ["", "  Vergleich Paper (2016-2023, SIP-Daten, Top 20): Sharpe ~2,4-2,8, Beta ~0.",
          "  Liegt dieser Lauf weit darunter, ist der Unterschied zuerst im Datenfeed",
          "  (IEX gegen SIP) und in den Kosten zu suchen, nicht in der Idee."]
    return "\n".join(L)


# ---------------------------------------------------------------------------
# Selbsttest mit synthetischen Bars - prueft die Mechanik, nicht die These
# ---------------------------------------------------------------------------
def _synthetische_bars(rng, tag: pd.Timestamp, preis: float, drift: float, n: int = 78) -> pd.DataFrame:
    idx = pd.date_range(tag + pd.Timedelta(hours=9, minutes=30), periods=n, freq="5min")
    ret = rng.normal(drift, 0.002, n)
    close = preis * np.cumprod(1 + ret)
    open_ = np.r_[preis, close[:-1]]
    high = np.maximum(open_, close) * (1 + rng.uniform(0, 0.002, n))
    low = np.minimum(open_, close) * (1 - rng.uniform(0, 0.002, n))
    vol = rng.integers(1_000, 50_000, n).astype(float)
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": vol}, index=idx)


def selftest() -> int:
    rng = np.random.default_rng(7)
    cfg = ORBConfig()
    fehler = 0
    # 1. Eine steigende Kerze, danach Anstieg: Long muss ausloesen und am Schluss enden
    tag = pd.Timestamp("2025-03-03")
    b = _synthetische_bars(rng, tag, 50.0, 0.001)
    b.iloc[0, b.columns.get_loc("close")] = b.iloc[0]["open"] * 1.005
    b.iloc[0, b.columns.get_loc("high")] = b.iloc[0]["close"]
    t = orb_tag(b, cfg, atr=1.0, rel_vol=3.0, kapital=100_000, seite_erlaubt=("long",))
    ok = t is not None and t.seite == "long" and t.einstieg >= b.iloc[0]["high"]
    print(f"  [{'ok' if ok else 'FEHLER'}] Long loest ueber dem Eroeffnungshoch aus"); fehler += not ok
    # 2. Fallender Markt: Stop muss greifen, Verlust <= 1 % Kapital (+ Kosten/Luecke)
    b2 = _synthetische_bars(rng, tag, 50.0, -0.004)
    b2.iloc[0, b2.columns.get_loc("close")] = b2.iloc[0]["open"] * 1.003
    b2.iloc[1, b2.columns.get_loc("high")] = b2.iloc[0]["close"] * 1.01   # Ausloeser reissen
    t2 = orb_tag(b2, cfg, atr=1.0, rel_vol=3.0, kapital=100_000, seite_erlaubt=("long",))
    ok = t2 is not None and t2.grund == "stop" and t2.pnl >= -100_000 * 0.01 * 1.6
    print(f"  [{'ok' if ok else 'FEHLER'}] Stop begrenzt den Verlust auf ~1 % (+Luecke/Kosten): "
          f"{t2.pnl if t2 else None}"); fehler += not ok
    # 3. Rote Eroeffnungskerze ohne --mit-short: kein Trade
    b3 = _synthetische_bars(rng, tag, 50.0, 0.0)
    b3.iloc[0, b3.columns.get_loc("close")] = b3.iloc[0]["open"] * 0.99
    t3 = orb_tag(b3, cfg, atr=1.0, rel_vol=3.0, kapital=100_000, seite_erlaubt=("long",))
    print(f"  [{'ok' if t3 is None else 'FEHLER'}] Rote Kerze ohne Short -> kein Trade"); fehler += t3 is not None
    # 4. Relatives Volumen und Top-N-Auswahl
    rv = relatives_volumen(3000, [1000] * 14)
    print(f"  [{'ok' if abs(rv - 3.0) < 1e-9 else 'FEHLER'}] relatives Volumen = {rv}"); fehler += abs(rv - 3.0) > 1e-9
    minuten = {f"S{i}": _synthetische_bars(rng, tag, 20 + i, 0.0005) for i in range(30)}
    hist = {f"S{i}": [1000.0] * 14 for i in range(30)}
    for i, (s, bars) in enumerate(minuten.items()):
        bars.iloc[0, bars.columns.get_loc("volume")] = 1000 * (0.5 + i / 5)   # steigende RV
    info = pd.DataFrame({"atr14": 1.0, "dv14": 5e6, "close_vortag": 25.0},
                        index=list(minuten))
    trades = tag_simulieren(tag, minuten, hist, info, cfg, 100_000)
    gewaehlt = {t.symbol for t in trades}
    ok = len(trades) <= cfg.top_n and all(t.rel_volumen >= 1.0 for t in trades)
    print(f"  [{'ok' if ok else 'FEHLER'}] Top-{cfg.top_n}-Auswahl nach relativem Volumen: "
          f"{len(trades)} Trades, min RV {min((t.rel_volumen for t in trades), default=None)}")
    fehler += not ok
    # 5. Zufallsmarkt ohne Drift: Erwartungswert ~0 nach Kosten leicht negativ
    alle = []
    for d in range(60):
        tag_d = pd.Timestamp("2025-01-02") + pd.Timedelta(days=d)
        mins = {f"Z{i}": _synthetische_bars(rng, tag_d, 30.0, 0.0) for i in range(40)}
        hist = {f"Z{i}": [1000.0] * 14 for i in range(40)}
        info = pd.DataFrame({"atr14": 0.8, "dv14": 5e6, "close_vortag": 30.0}, index=list(mins))
        alle += tag_simulieren(tag_d, mins, hist, info, cfg, 100_000)
    print(auswerten(alle, cfg))
    r_mean = np.mean([t.rendite_auf_risiko for t in alle]) if alle else 0
    ok = -0.6 < r_mean < 0.3
    print(f"  [{'ok' if ok else 'FEHLER'}] Zufallsmarkt: Ø R je Trade {r_mean:+.2f} (erwartet ~0 bis leicht negativ)")
    fehler += not ok
    print(f"\n  Selbsttest: {'bestanden' if fehler == 0 else f'{fehler} Fehler'}")
    return 1 if fehler else 0


# ---------------------------------------------------------------------------
# Echte Daten ueber Alpaca (laeuft nur mit Keys auf deinem Rechner)
# ---------------------------------------------------------------------------
def _lade_tag(symbole: list[str], tag: pd.Timestamp, feed: str) -> dict[str, pd.DataFrame]:
    """5-Minuten-Bars eines Tages fuer viele Symbole, mit Plattencache."""
    from alpaca_bot import data

    ORB_CACHE.mkdir(parents=True, exist_ok=True)
    pfad = ORB_CACHE / f"{tag.date()}_{feed}_{len(symbole)}.parquet"
    if pfad.exists():
        raw = pd.read_parquet(pfad)
    else:
        start = tag.tz_localize("America/New_York").replace(hour=9, minute=30)
        ende = tag.tz_localize("America/New_York").replace(hour=16, minute=0)
        frames = []
        for i in range(0, len(symbole), 200):
            teil = symbole[i:i + 200]
            try:
                b = data.get_bars(teil, "5Min", start=start, end=ende)
            except Exception as e:  # noqa: BLE001
                print(f"      {tag.date()} Batch {i // 200 + 1}: {type(e).__name__}: {e}")
                continue
            if not b.empty:
                frames.append(b)
        raw = pd.concat(frames) if frames else pd.DataFrame()
        if not raw.empty:
            raw.to_parquet(pfad)
    if raw.empty:
        return {}
    out = {}
    for sym in raw.index.get_level_values("symbol").unique():
        df = raw.xs(sym, level="symbol").sort_index()
        df.index = pd.DatetimeIndex(df.index).tz_convert("America/New_York")
        df = df.between_time("09:30", "15:55")
        out[sym] = df[["open", "high", "low", "close", "volume"]].astype(float)
    return out


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--selftest", action="store_true")
    p.add_argument("--start", default=None)
    p.add_argument("--ende", default=None)
    p.add_argument("--symbole", nargs="*", default=None)
    p.add_argument("--symbole-aus-universum", type=int, default=800,
                   help="die N liquidesten aus results/factor_lab/universum.csv")
    p.add_argument("--feed", default="iex", choices=["iex", "sip"])
    p.add_argument("--top-n", type=int, default=20)
    p.add_argument("--mit-short", action="store_true")
    p.add_argument("--spread-bps", type=float, default=3.0)
    p.add_argument("--slippage-bps", type=float, default=2.0)
    p.add_argument("--kapital", type=float, default=100_000)
    args = p.parse_args()

    if args.selftest:
        return selftest()
    if not args.start or not args.ende:
        print("  --start und --ende angeben (oder --selftest).")
        return 1

    from alpaca_bot import compliance, data, universe
    from alpaca_bot import indicators as ind

    cfg = ORBConfig(top_n=args.top_n, mit_short=args.mit_short, spread_bps=args.spread_bps,
                    slippage_bps=args.slippage_bps, kapital=args.kapital)
    symbole = args.symbole or universe.load_universe(max_symbols=args.symbole_aus_universum)
    tage = pd.bdate_range(args.start, args.ende)
    print(compliance.preflight(len(symbole), len(tage) / 252, "5Min"))

    # Tagesdaten fuer ATR/Umsatz (ein Abruf)
    daily = data.get_bars(symbole, "1D", start=(tage[0] - pd.Timedelta(days=40)).tz_localize("UTC"),
                          end=(tage[-1] + pd.Timedelta(days=1)).tz_localize("UTC"))
    tagesinfo_alle = {}
    for sym in daily.index.get_level_values("symbol").unique():
        df = daily.xs(sym, level="symbol").sort_index()
        df.index = pd.DatetimeIndex(df.index).tz_convert("America/New_York").normalize().tz_localize(None)
        tagesinfo_alle[sym] = pd.DataFrame({
            "atr14": ind.atr(df, 14), "dv14": (df["close"] * df["volume"]).rolling(14).mean(),
            "close_vortag": df["close"],
        }).shift(1)   # NUR Vortagswissen

    erste_kerze_hist: dict[str, list[float]] = {s: [] for s in symbole}
    trades: list[Trade] = []
    kapital = cfg.kapital
    for tag in tage:
        minuten = _lade_tag(symbole, tag, args.feed)
        if not minuten:
            continue
        info = pd.DataFrame({s: ti.loc[tag] for s, ti in tagesinfo_alle.items() if tag in ti.index}).T
        heute = tag_simulieren(tag, minuten, erste_kerze_hist, info, cfg, kapital)
        trades += heute
        kapital += sum(t.pnl for t in heute)
        for sym, bars in minuten.items():
            erste_kerze_hist.setdefault(sym, []).append(float(bars["volume"].iloc[0]))
            erste_kerze_hist[sym] = erste_kerze_hist[sym][-14:]
        print(f"      {tag.date()}  Kandidaten {len(minuten):>5}  Trades {len(heute):>3}  "
              f"Kapital {kapital:>12,.0f}")

    print(auswerten(trades, cfg))
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"orb_{args.start}_{args.ende}_{args.feed}.csv"
    pd.DataFrame([t.__dict__ for t in trades]).to_csv(out, index=False)
    print(f"\n  gespeichert: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
