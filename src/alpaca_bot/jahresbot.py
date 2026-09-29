"""Jahresauswahl: einmal im Jahr die aussichtsreichsten Aktien kaufen, halten.

**Die Idee (Nutzer, 04.09.2026).** Anfang jedes Jahres die Werte
auswaehlen, die im kommenden Jahr am ehesten steigen, sie das ganze Jahr
halten, am Jahresende (oder bei extremem Verlauf) verkaufen und in die
neuen Kandidaten rotieren. **Sehr wenige Trades pro Jahr** - genau das,
was der zentrale Kostenkonflikt (§G51: Spanne ~12 bps) verlangt: Bei
~1 Umschlag je Position und Jahr ist die halbe Spanne ~0,06 %/Jahr,
vernachlaessigbar.

**Was auf Altdaten kausal testbar ist.** „News" oder „welche Aktie steigt
2015" gibt es rueckwirkend nicht sauber (yfinance schreibt die
Vergangenheit um, §B5). Testbar ist die **querschnittliche Auswahl nach
Kurssignalen**: 12-1-Monats-Momentum (Jegadeesh-Titman), niedrige
Volatilitaet, oder eine Kombination. Top-N, jaehrliches Rebalancing,
Stop bei extremem Verlust, Gewinner laufen lassen.

**Zwei Vorbehalte, die im Ergebnis mitgedruckt werden.**

* **Survivorship (§G11).** Jaehrliches Stock-Picking auf den *heute*
  gelisteten Namen ist maximal davon betroffen - man waehlt aus den
  Ueberlebenden. Abschlag +2..+4 pp/Jahr. Jedes absolute Ergebnis ist
  eine Obergrenze.
* **§C.** Der Faktorraum aus Kurs- und Volumendaten gilt als
  ausgeschoepft; Momentum war im Projekt der Umkehr unterlegen (§A). Was
  hier anders ist: der *Horizont* (Jahr statt Tage) und damit die
  Kostenlast.

Kein Handelsbot, kein Versuchszaehlerplatz (BETRIEBSPLAN §4).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import costs

TAGE_PRO_MONAT = 21
TRADING_DAYS = 252


@dataclass
class JahresConfig:
    signal: str = "momentum"          # momentum | tief_vola | momentum_vola
    top_n: int = 20
    lookback_monate: int = 12
    skip_monate: int = 1             # 12-1
    rebalance_monat: int = 1        # Januar
    stop_pct: float = 0.25          # -25 % vom Einstand -> raus bis Jahresende (0 = aus)
    gewinner_laufen_lassen: bool = True
    laufband_faktor: float = 1.5    # Name bleibt, wenn noch in den Top (top_n * faktor)
    min_kurs: float = 5.0
    min_dollar_volumen: float = 5_000_000.0
    kosten_bps: float = 12.0        # gemessene NBBO-Spanne (§G51), voll
    slippage_bps: float = 3.0
    startkapital: float = 100_000.0

    def pruefe(self) -> None:
        if self.signal not in ("momentum", "tief_vola", "momentum_vola"):
            raise ValueError(f"signal: {self.signal!r}")
        if self.top_n < 1:
            raise ValueError("top_n >= 1")
        if not 1 <= self.rebalance_monat <= 12:
            raise ValueError("rebalance_monat 1..12")
        if self.skip_monate >= self.lookback_monate:
            raise ValueError("skip < lookback")


# ---------------------------------------------------------------------------
def _merkmale(df: pd.DataFrame, cfg: JahresConfig) -> pd.DataFrame:
    close = df["close"].astype(float)
    vol = df["volume"].astype(float)
    out = pd.DataFrame(index=df.index)
    out["close"] = close
    out["low"] = df["low"].astype(float)
    out["open"] = df["open"].astype(float)
    lb, sk = cfg.lookback_monate * TAGE_PRO_MONAT, cfg.skip_monate * TAGE_PRO_MONAT
    out["mom"] = close.shift(sk) / close.shift(lb) - 1.0
    out["vola"] = close.pct_change().rolling(126).std() * np.sqrt(TRADING_DAYS)
    out["dollar_vol"] = (close * vol).rolling(20).median()
    return out


def _rang_wert(zeile: pd.Series, cfg: JahresConfig) -> float:
    """Hoeher = besser."""
    if cfg.signal == "tief_vola":
        return -zeile["vola"] if np.isfinite(zeile["vola"]) else -9e9
    if cfg.signal == "momentum_vola":
        if not (np.isfinite(zeile["mom"]) and np.isfinite(zeile["vola"]) and zeile["vola"] > 0):
            return -9e9
        return zeile["mom"] / zeile["vola"]
    return zeile["mom"] if np.isfinite(zeile["mom"]) else -9e9


@dataclass
class JahresTrade:
    symbol: str
    entry_date: pd.Timestamp
    exit_date: pd.Timestamp
    entry_raw: float
    exit_raw: float
    qty: int
    exit_reason: str
    brutto_ret: float
    net_pnl: float
    return_pct: float
    tage_gehalten: int


@dataclass
class JahresResult:
    equity_curve: pd.Series
    trades: pd.DataFrame
    config: JahresConfig
    n_symbols: int
    kalender_tage: int
    rebalances: int

    @property
    def total_return(self) -> float:
        if self.equity_curve.empty:
            return 0.0
        return float(self.equity_curve.iloc[-1] / self.equity_curve.iloc[0] - 1)

    def metrics(self) -> dict:
        from .backtest import compute_metrics

        eq = self.equity_curve
        if eq.empty or len(eq) < 30:
            return {}
        m = compute_metrics(eq.pct_change().dropna())
        t = self.trades
        jahre = len(eq) / TRADING_DAYS
        if not t.empty:
            gew = t[t["net_pnl"] > 0]
            m["n_trades"] = int(len(t))
            m["trades_pro_jahr"] = float(len(t) / jahre) if jahre else 0.0
            m["trefferquote"] = float(len(gew) / len(t))
            m["ertrag_je_trade"] = float(t["return_pct"].mean())
            m["mittlere_haltedauer_tage"] = float(t["tage_gehalten"].mean())
        return m

    def jahres_renditen(self) -> dict[int, float]:
        eq = self.equity_curve
        out = {}
        for j in sorted({ts.year for ts in eq.index}):
            ej = eq[eq.index.year == j]
            if len(ej) >= 2:
                out[j] = float(ej.iloc[-1] / ej.iloc[0] - 1)
        return out


def run(bars: pd.DataFrame, cfg: JahresConfig | None = None, *,
        start: str | None = None, end: str | None = None,
        verbose: bool = False) -> JahresResult:
    """Backtest: jaehrliches Rebalancing, taegliche Bewertung und Stop-Pruefung.

    bars: MultiIndex (symbol, timestamp), OHLCV. `SPY` darf enthalten sein
    und wird als Handelskandidat ausgeschlossen (nur Benchmark).
    """
    cfg = cfg or JahresConfig()
    cfg.pruefe()

    per_symbol: dict[str, pd.DataFrame] = {}
    for sym in bars.index.get_level_values("symbol").unique():
        if str(sym) == "SPY":
            continue
        d = bars.xs(sym, level="symbol").sort_index()
        d = d[~d.index.duplicated(keep="last")]
        if len(d) > cfg.lookback_monate * TAGE_PRO_MONAT + 30:
            per_symbol[str(sym)] = d
    if not per_symbol:
        raise ValueError("Keine Symbole mit ausreichender Historie.")
    merk = {s: _merkmale(d, cfg) for s, d in per_symbol.items()}

    kal = pd.DatetimeIndex(sorted(set().union(*[set(d.index) for d in per_symbol.values()])))
    if start:
        kal = kal[kal >= pd.Timestamp(start, tz=kal.tz)]
    if end:
        kal = kal[kal <= pd.Timestamp(end, tz=kal.tz)]
    warmup = cfg.lookback_monate * TAGE_PRO_MONAT + 25
    if len(kal) < warmup + 60:
        raise ValueError("Zu wenig Historie im Zeitraum.")

    # erster Handelstag je Jahr im Rebalance-Monat, nach dem Warmup
    rebal = []
    for jahr in sorted({d.year for d in kal[warmup:]}):
        kandidat = kal[(kal.year == jahr) & (kal.month == cfg.rebalance_monat)]
        if len(kandidat):
            rebal.append(kandidat[0])
    rebal_set = set(rebal)
    if len(rebal) < 3:
        raise ValueError("Weniger als 3 Rebalance-Termine im Zeitraum.")

    cash = float(cfg.startkapital)
    pos: dict[str, dict] = {}          # sym -> qty, entry_raw, entry_date, stop
    pend_buy: dict[str, float] = {}    # sym -> notional
    pend_sell: dict[str, str] = {}     # sym -> reason
    eq_hist: list[tuple[pd.Timestamp, float]] = []
    trades: list[JahresTrade] = []

    def schliessen(sym, fill_raw, tag, grund):
        nonlocal cash
        p = pos.pop(sym, None)
        if p is None:
            return
        verk = costs.estimate_costs("sell", p["qty"], last=fill_raw,
                                    spread_bps=cfg.kosten_bps,
                                    slippage_bps=cfg.slippage_bps)
        cash += verk.net_proceeds
        invest = p["qty"] * p["entry_raw"]
        netto = verk.net_proceeds - (invest + p["entry_kosten"])
        trades.append(JahresTrade(
            symbol=sym, entry_date=p["entry_date"], exit_date=tag,
            entry_raw=p["entry_raw"], exit_raw=float(fill_raw), qty=int(p["qty"]),
            exit_reason=grund,
            brutto_ret=float(fill_raw / p["entry_raw"] - 1.0),
            net_pnl=round(netto, 2),
            return_pct=round(netto / invest, 5) if invest else 0.0,
            tage_gehalten=int((tag - p["entry_date"]).days),
        ))

    for i, tag in enumerate(kal):
        # 1. offene Orders von gestern
        for sym, grund in list(pend_sell.items()):
            d = per_symbol.get(sym)
            if d is not None and tag in d.index:
                schliessen(sym, float(d.loc[tag, "open"]), tag, grund)
        pend_sell.clear()
        for sym, notional in list(pend_buy.items()):
            d = per_symbol.get(sym)
            if d is None or tag not in d.index:
                continue
            fill = float(d.loc[tag, "open"])
            qty = int(notional / fill) if fill > 0 else 0
            if qty <= 0:
                continue
            kauf = costs.estimate_costs("buy", qty, last=fill,
                                        spread_bps=cfg.kosten_bps,
                                        slippage_bps=cfg.slippage_bps)
            cash -= kauf.net_proceeds
            pos[sym] = dict(qty=qty, entry_raw=fill, entry_date=tag,
                            entry_kosten=kauf.total_cost,
                            stop=fill * (1 - cfg.stop_pct) if cfg.stop_pct > 0 else 0.0)
        pend_buy.clear()

        # 2. Stops (taeglich, gegen das Tagestief)
        for sym, p in list(pos.items()):
            d = per_symbol.get(sym)
            if d is None or tag not in d.index:
                continue
            if p["stop"] > 0 and float(d.loc[tag, "low"]) <= p["stop"] and sym not in pend_sell:
                pend_sell[sym] = "stop"

        # 3. Kontowert
        wert = cash
        for sym, p in pos.items():
            d = per_symbol.get(sym)
            px = float(d.loc[tag, "close"]) if d is not None and tag in d.index else p["entry_raw"]
            wert += p["qty"] * px
        eq_hist.append((tag, wert))

        # 4. Rebalance
        if tag in rebal_set:
            kand = []
            for sym, mk in merk.items():
                if tag not in mk.index:
                    continue
                z = mk.loc[tag]
                if z["close"] < cfg.min_kurs or not np.isfinite(z["dollar_vol"]) \
                        or z["dollar_vol"] < cfg.min_dollar_volumen:
                    continue
                rw = _rang_wert(z, cfg)
                if rw > -9e8:
                    kand.append((sym, rw))
            if not kand:
                continue
            kand.sort(key=lambda x: -x[1])
            ziel = [s for s, _ in kand[:cfg.top_n]]
            laufband = {s for s, _ in kand[:int(cfg.top_n * cfg.laufband_faktor)]}

            behalten = set()
            if cfg.gewinner_laufen_lassen:
                behalten = {s for s in pos if s in laufband}
            behalten |= (set(pos) & set(ziel))

            for sym in list(pos):
                if sym not in behalten and sym not in pend_sell:
                    pend_sell[sym] = "rebalance"

            slots_frei = cfg.top_n - len(behalten)
            neu = [s for s in ziel if s not in behalten][:max(0, slots_frei)]
            if neu:
                slot = wert / cfg.top_n
                for sym in neu:
                    pend_buy[sym] = slot
            if verbose:
                print(f"  {tag.date()}  halte {len(behalten)}, kaufe {len(neu)}, "
                      f"verkaufe {len(pend_sell)}  Equity ${wert:,.0f}")

    # am Ende glattstellen
    letzter = kal[-1]
    for sym in list(pos):
        d = per_symbol.get(sym)
        g = d.index[d.index <= letzter]
        if len(g):
            schliessen(sym, float(d.loc[g[-1], "close"]), letzter, "lauf_ende")
    eq_hist.append((letzter, cash))

    eq = pd.Series(dict(eq_hist)).sort_index()
    return JahresResult(
        equity_curve=eq,
        trades=pd.DataFrame([t.__dict__ for t in trades]),
        config=cfg, n_symbols=len(per_symbol), kalender_tage=len(kal),
        rebalances=len(rebal),
    )


# ---------------------------------------------------------------------------
def auswerten(result: JahresResult, bars: pd.DataFrame, *,
              n_varianten: int = 1, segment: str = "small_cap") -> str:
    from . import universe

    cfg = result.config
    eq = result.equity_curve
    m = result.metrics()
    jahre = len(eq) / TRADING_DAYS if len(eq) else 0

    spy = None
    if "SPY" in bars.index.get_level_values("symbol"):
        s = bars.xs("SPY", level="symbol")["close"].sort_index()
        s = s[(s.index >= eq.index[0]) & (s.index <= eq.index[-1])]
        if len(s) > 2:
            spy = float(s.iloc[-1] / s.iloc[0] - 1)

    L = ["=" * 74, "  JAHRESBOT - HISTORIENLAUF", "=" * 74]
    L.append(f"  Signal {cfg.signal} | Top {cfg.top_n} | Lookback "
             f"{cfg.lookback_monate}-{cfg.skip_monate}M | Stop "
             f"{'aus' if cfg.stop_pct == 0 else f'-{cfg.stop_pct:.0%}'} | "
             f"Gewinner laufen lassen: {cfg.gewinner_laufen_lassen}")
    L.append(f"  {result.n_symbols} Symbole | {eq.index[0].date()} .. "
             f"{eq.index[-1].date()} | {result.rebalances} Rebalances | "
             f"Kosten {cfg.kosten_bps:g}+{cfg.slippage_bps:g} bps")
    L.append("")
    L.append(f"  Gesamtrendite         {result.total_return:>12.1%}")
    L.append(f"  CAGR                  {m.get('cagr', float('nan')):>12.1%}"
             + (f"     (SPY B&H {spy:+.1%})" if spy is not None else ""))
    L.append(f"  Max Drawdown          {m.get('max_drawdown', float('nan')):>12.1%}")
    L.append(f"  Sharpe / Sortino      {m.get('sharpe', float('nan')):>6.2f} /"
             f"{m.get('sortino', float('nan')):>5.2f}")
    L.append(f"  Trades / Jahr         {m.get('trades_pro_jahr', 0):>12.1f}")
    L.append(f"  Trefferquote          {m.get('trefferquote', 0):>12.1%}")
    L.append(f"  Ertrag je Trade       {m.get('ertrag_je_trade', 0):>12.2%}")
    L.append(f"  Mittlere Haltedauer   {m.get('mittlere_haltedauer_tage', 0):>10.0f} Tage")
    if not result.trades.empty:
        gr = result.trades.groupby("exit_reason").size().to_dict()
        L.append(f"  Ausstiege: " + ", ".join(f"{k}={v}" for k, v in sorted(gr.items())))
    L.append("")

    jr = result.jahres_renditen()
    L.append(f"  {'Jahr':>6} {'Bot':>10} {'SPY':>10}  Diff")
    schlaege, nj = 0, 0
    for j in sorted(jr):
        rs = float("nan")
        if spy is not None:
            sj = bars.xs("SPY", level="symbol")["close"]
            sj = sj[sj.index.year == j]
            if len(sj) >= 2:
                rs = float(sj.iloc[-1] / sj.iloc[0] - 1)
        diff = jr[j] - rs if np.isfinite(rs) else float("nan")
        if np.isfinite(diff):
            nj += 1
            schlaege += int(diff > 0)
        L.append(f"  {j:>6} {jr[j]:>10.1%} {rs:>10.1%}  {diff:>+8.1%}")
    L.append(f"  -> schlaegt SPY in {schlaege}/{nj} Jahren "
             f"({schlaege / nj:.0%})" if nj else "  -> keine vollen Jahre")
    L.append("")
    L.append("  " + "-" * 70)
    L.append("  EINORDNUNG")
    L.append("  " + "-" * 70)
    for zeile in universe.survivorship_warning(result.n_symbols, jahre or 1,
                                               segment).splitlines():
        L.append("  " + zeile)
    L.append("")
    L.append("  Jaehrliches Stock-Picking auf HEUTIGEN Namen ist maximal")
    L.append("  survivorship-verzerrt (§G11). Von der CAGR grob 2-4 pp/Jahr")
    L.append("  abziehen. §C: der Kurs-/Volumen-Faktorraum gilt als ausgeschoepft.")
    if n_varianten > 1:
        mt = float(np.sqrt(2 * np.log(n_varianten)) + 0.5)
        L.append(f"  {n_varianten} Varianten -> Zufallsmaximum t ~ {mt:.2f} (§B2/§B4).")
    L.append("=" * 74)
    return "\n".join(L)


def walk_forward(bars: pd.DataFrame, cfg: JahresConfig | None = None, *,
                 start=None, end=None) -> dict:
    """Je Jahr: Auswahl aus Vergangenheit, gemessen im naechsten Jahr.

    Hier trivialer als bei der Flotte, weil die Auswahlregel (Top-N nach
    Momentum) fix ist - der Walk-Forward misst, ob DIESE Regel Jahr fuer
    Jahr gegen SPY traegt, ohne Rueckschau.
    """
    res = run(bars, cfg, start=start, end=end)
    jr = res.jahres_renditen()
    spy_close = (bars.xs("SPY", level="symbol")["close"]
                 if "SPY" in bars.index.get_level_values("symbol") else None)
    diffs = []
    zeilen = []
    for j in sorted(jr):
        if spy_close is None:
            continue
        sj = spy_close[spy_close.index.year == j]
        if len(sj) < 2:
            continue
        rs = float(sj.iloc[-1] / sj.iloc[0] - 1)
        diffs.append(jr[j] - rs)
        zeilen.append({"jahr": j, "bot": jr[j], "spy": rs, "diff": jr[j] - rs})
    d = pd.Series(diffs)
    return {
        "zeilen": zeilen, "n_jahre": len(d),
        "mittel_diff": float(d.mean()) if len(d) else float("nan"),
        "jahre_mit_vorsprung": int((d > 0).sum()),
        "t": float(d.mean() / (d.std(ddof=1) / np.sqrt(len(d))))
        if len(d) > 2 and d.std(ddof=1) > 0 else float("nan"),
    }
