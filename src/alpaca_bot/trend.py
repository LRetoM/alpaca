"""Trendfolge / Dual-Momentum auf liquiden ETFs - der Strategie-Familien-Wechsel.

**Warum (04.09.2026, `docs/TRENDBOT.md`).** Der bisherige Ansatz -
kurzfristige querschnittliche Aktiensignale auf mittelgrossen US-Werten -
ist ausgeschoepft (0 von ~90 Konfigs, 5 Lernmethoden, §C). Zwei
eingebaute Killer: Spannen ~12 bps (§G51) und Survivorship (§G11).

Time-Series-Momentum auf liquiden ETFs umgeht beide: ~12 Rebalances/Jahr
(2 bps Kosten sind ~0,2 %/Jahr), ETF-Spannen 1-2 bps, ETFs auf grosse
Anlageklassen verschwinden nicht. Es ist der am besten belegte
systematische Effekt ueberhaupt (AQR, 100+ Jahre) - keine Neuentdeckung,
also greift §B3 ("65 % replizieren nicht") nicht dieselbe Wucht.

**Kein Handelsbot.** Reiner Offline-Backtest auf Altdaten, wie
`simulate.py` / `spekulativ.py`. Monatliches Rebalancing, Kosten
beidseitig auf den Turnover, Vol-Targeting-Overlay. Drei Strategien:
`tsmom` (absolute Momentum je Asset), `dualmom` (Rangliste + Cash-Filter,
Antonacci-GEM), `ma_filter` (Preis ueber eigenem 200-Tage-Schnitt).

Das Urteil faellt am Gate aus `docs/TRENDBOT.md` §5, nicht an einer
schoenen Kurve.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np
import pandas as pd

TAGE_PRO_MONAT = 21
TRADING_DAYS = 252


UNIVERSEN: dict[str, list[str]] = {
    "broad": ["SPY", "EFA", "EEM", "IEF", "TLT", "GLD", "DBC", "VNQ"],
    "core": ["SPY", "IEF", "GLD"],
    "equity": ["SPY", "EFA", "EEM"],
    "klassisch": ["SPY", "EFA", "EEM", "IEF", "GLD", "VNQ"],
}


@dataclass
class TrendConfig:
    strategie: str = "tsmom"           # tsmom | dualmom | ma_filter
    lookback_monate: int = 12
    skip_monate: int = 1              # 12-1: der letzte Monat wird uebersprungen
    ma_tage: int = 200               # nur ma_filter
    top_n: int = 3                    # nur dualmom
    vol_ziel: float = 0.10           # annualisiert; 0 = kein Vol-Targeting
    vol_fenster_tage: int = 60
    max_brutto: float = 1.0         # Deckel auf die Summe der Gewichte
    cash_rendite_pa: float = 0.02
    kosten_bps: float = 2.0         # je Seite, auf den Turnover
    slippage_bps: float = 1.0
    startkapital: float = 100_000.0
    rebalance: str = "monatlich"     # monatlich | woechentlich

    vol_ebene: str = "asset"
    """Worauf sich `vol_ziel` bezieht: "asset" oder "depot".

    * `"asset"` (bisher): jede Position einzeln auf das Ziel skaliert.
      Drei Assets, die nicht perfekt korrelieren, ergeben dann ein Depot
      UNTER dem Ziel - gemessen 8,1 % realisiert bei 10 % Ziel (§G97).
      Das Risikobudget wird zu vier Fuenfteln genutzt.
    * `"depot"`: die relativen Gewichte bleiben (inverse Vola), aber die
      Summe wird so skaliert, dass das DEPOT das Ziel trifft - ueber die
      Kovarianz der gehaltenen Assets im Vol-Fenster. Das ist die
      uebliche Fassung (Moskowitz/Ooi/Pedersen skalieren die Strategie,
      nicht die Position).

    Keine neue Information, kein neuer Parameter: Das Ziel bleibt 10 %.
    Es wird nur dort angewandt, wo es hingehoert. Der Deckel
    `max_brutto` bleibt - ohne Margin wird nie ueber 100 % investiert."""

    cash_symbol: str = ""
    """Kursreihe, die den Cash-Anteil verzinst, z. B. "BIL". "" = Pauschale.

    **Warum das keine Kosmetik ist.** Der Bot haelt im Schnitt 40 % Cash.
    `cash_rendite_pa` unterstellt dafuer pauschal 2 % - 2023 bis 2025
    lagen US-Geldmarktzinsen bei 4 bis 5 %. Ein Geldmarkt-ETF (BIL: 0-3
    Monate T-Bills) liefert den ECHTEN Ertrag aus derselben Datenquelle
    wie alles andere, Tag fuer Tag, einschliesslich der Nullzinsphase
    2020/21. Das ist eine Korrektur der Annahme, keine Strategieaenderung.

    Der Cash-ETF wird selbst NIE gehandelt und taucht in keiner Rangliste
    auf - er ist der Massstab fuer "nicht investiert", kein Kandidat.
    Die Momentum-Huerde (`huerde`) bleibt vorerst bei der Pauschale."""

    lookbacks: tuple[int, ...] = ()
    """Ensemble ueber mehrere Lookbacks. Leer = nur `lookback_monate`.

    **Weniger Freiheitsgrade, nicht mehr.** Das Gate scheitert an
    Kriterium 3: Die AUSWAHL des Lookbacks traegt nicht ins naechste Jahr
    (t = -1,34 auf yfinance, 0,07 auf eigenen Daten). Wer die Zielgewichte
    ueber 6, 9 und 12 Monate mittelt, waehlt nichts mehr aus - und hat
    damit nichts, was nicht uebertragen koennte.

    Das ist keine Neuerfindung: Mehrere Horizonte zu mitteln ist die
    uebliche Fassung robuster Trendfolge (Antonacci, AQR). Der Preis ist
    ein etwas traegeres Signal; der Gewinn ist, dass kein einzelner
    Monat das Ergebnis dreht."""

    rebalance_versatz_tage: int = 0
    """Rebalance-Termine um so viele Handelstage nach hinten schieben.

    Fuer Tranchen: drei Laeufe mit Versatz 0, 7 und 14 Tagen, deren
    Renditen gemittelt werden, sind ein Depot aus drei Teildepots. Das
    nimmt dem Ergebnis die Abhaengigkeit vom Monatsende (§G87: das
    Raster allein aenderte 2023 von -1,9 % auf +1,0 %)."""

    def pruefe(self) -> None:
        if self.strategie not in ("tsmom", "dualmom", "ma_filter",
                                  "gem", "risk_parity"):
            raise ValueError(f"strategie: {self.strategie!r}")
        if self.rebalance not in ("monatlich", "woechentlich"):
            raise ValueError(f"rebalance: {self.rebalance!r}")
        if self.lookback_monate < 1 or self.skip_monate < 0:
            raise ValueError("lookback >= 1, skip >= 0")
        if self.skip_monate >= self.lookback_monate:
            raise ValueError("skip_monate muss kleiner als lookback_monate sein")
        for lb in self.lookbacks:
            if lb < 1 or self.skip_monate >= lb:
                raise ValueError(f"lookbacks: {lb} unbrauchbar bei skip "
                                 f"{self.skip_monate}")
        if self.rebalance_versatz_tage < 0:
            raise ValueError("rebalance_versatz_tage >= 0")

    def max_lookback(self) -> int:
        """Der laengste Horizont - bestimmt den Vorlauf."""
        return max((*self.lookbacks, self.lookback_monate))


# ---------------------------------------------------------------------------
def _rebalance_termine(index: pd.DatetimeIndex, modus: str,
                       versatz_tage: int = 0) -> pd.DatetimeIndex:
    """Letzter Handelstag je Monat (bzw. je Woche), optional versetzt.

    `versatz_tage` schiebt jeden Termin um so viele HANDELSTAGE nach
    hinten - auf den naechsten vorhandenen Index-Eintrag, nie auf einen
    Kalendertag ohne Handel.
    """
    s = pd.Series(index, index=index)
    if modus == "woechentlich":
        grp = s.groupby([index.isocalendar().year, index.isocalendar().week])
    else:
        grp = s.groupby([index.year, index.month])
    termine = pd.DatetimeIndex(sorted(grp.last().to_numpy()))
    if versatz_tage <= 0:
        return termine
    pos = index.searchsorted(termine) + versatz_tage
    pos = pos[pos < len(index)]
    return pd.DatetimeIndex(sorted(set(index[pos])))


def _momentum(prices: pd.DataFrame, bis: pd.Timestamp,
              lookback_m: int, skip_m: int) -> pd.Series:
    """Rendite je Asset ueber das Fenster [t - lookback, t - skip] Monate.

    Rein kausal: es wird nur `prices.loc[:bis]` benutzt, positional von
    hinten geschnitten.
    """
    p = prices.loc[:bis]
    end_i = -1 - skip_m * TAGE_PRO_MONAT
    start_i = -1 - lookback_m * TAGE_PRO_MONAT
    if len(p) < abs(start_i) + 1:
        return pd.Series(np.nan, index=prices.columns)
    ende = p.iloc[end_i]
    anfang = p.iloc[start_i]
    return (ende / anfang - 1.0).where(anfang.notna() & ende.notna())


def _realized_vol(returns: pd.DataFrame, bis: pd.Timestamp,
                  fenster: int) -> pd.Series:
    r = returns.loc[:bis].tail(fenster)
    return r.std(ddof=1) * np.sqrt(TRADING_DAYS)


def ziel_gewichte(prices: pd.DataFrame, returns: pd.DataFrame,
                  bis: pd.Timestamp, cfg: TrendConfig,
                  cash_kurse: pd.Series | None = None) -> pd.Series:
    """Zielgewichte zum Rebalance-Termin `bis`. Summe <= max_brutto, Rest
    ist implizit Cash. Nur Daten bis `bis`.

    Mit `cfg.lookbacks` werden die Gewichte je Horizont gerechnet und
    gemittelt - ein Asset, das nur bei einem von drei Horizonten
    qualifiziert, bekommt ein Drittel seines Gewichts. Ohne `lookbacks`
    exakt das bisherige Verhalten.
    """
    if not cfg.lookbacks:
        return _ziel_gewichte_einzel(prices, returns, bis, cfg, cash_kurse)
    teile = []
    for lb in cfg.lookbacks:
        einzel = replace(cfg, lookback_monate=lb, lookbacks=())
        teile.append(_ziel_gewichte_einzel(prices, returns, bis, einzel,
                                           cash_kurse))
    teile = [t for t in teile if not t.empty]
    if not teile:
        return pd.Series(dtype=float)
    alle = sorted(set().union(*(t.index for t in teile)))
    summe = sum(t.reindex(alle).fillna(0.0) for t in teile)
    return summe / len(cfg.lookbacks)


def _ziel_gewichte_einzel(prices: pd.DataFrame, returns: pd.DataFrame,
                          bis: pd.Timestamp, cfg: TrendConfig,
                          cash_kurse: pd.Series | None = None) -> pd.Series:
    """Zielgewichte fuer GENAU EINEN Lookback - der bisherige Kern.

    `cash_kurse`: Ist die Reihe da, wird die Momentum-Huerde aus IHREM
    Ertrag ueber dasselbe Fenster gerechnet statt aus der Pauschale.
    Das ist die Antonacci-Fassung ("absolute Momentum gegen T-Bills")
    und konsistent zu `cash_symbol` (§G96): Wer Cash mit BIL verzinst,
    muss auch "besser als Cash" an BIL messen.
    """
    p = prices.loc[:bis]
    mindest = cfg.lookback_monate * TAGE_PRO_MONAT + 5
    verfuegbar = [a for a in p.columns if p[a].notna().sum() > mindest
                  and (cfg.strategie != "ma_filter"
                       or p[a].notna().sum() > cfg.ma_tage + 5)]
    if not verfuegbar:
        return pd.Series(dtype=float)

    # "absolute Momentum > Cash": der Cash-Ertrag ueber dasselbe Fenster.
    fenster_jahre = (cfg.lookback_monate - cfg.skip_monate) / 12.0
    huerde = cfg.cash_rendite_pa * fenster_jahre
    if cash_kurse is not None:
        cm = _momentum(cash_kurse.to_frame("cash"), bis, cfg.lookback_monate,
                       cfg.skip_monate)
        if cm.notna().all() and np.isfinite(float(cm.iloc[0])):
            huerde = float(cm.iloc[0])

    # --- immer investierte Strategien (kein Momentum-Filter) ---
    if cfg.strategie == "risk_parity":
        vol = _realized_vol(returns[verfuegbar], bis, cfg.vol_fenster_tage)
        inv = (1.0 / vol.replace(0.0, np.nan)).dropna()
        if inv.empty:
            return pd.Series(dtype=float)
        return inv / inv.sum() * cfg.max_brutto

    if cfg.strategie == "gem":
        # Global-Equities-Momentum (Antonacci, verallgemeinert): das eine
        # Asset mit dem staerksten Momentum halten - liegt es unter der
        # Cash-Huerde, ganz in das Asset mit der niedrigsten Vola (Anleihe).
        mom = _momentum(prices[verfuegbar], bis, cfg.lookback_monate,
                        cfg.skip_monate).dropna().sort_values(ascending=False)
        if mom.empty:
            return pd.Series(dtype=float)
        if mom.iloc[0] > huerde:
            an = [mom.index[0]]
        else:
            vol = _realized_vol(returns[verfuegbar], bis, cfg.vol_fenster_tage)
            an = [vol.dropna().idxmin()] if vol.notna().any() else []
        if not an:
            return pd.Series(dtype=float)
        w = pd.Series(1.0, index=an)
        if cfg.vol_ziel > 0:
            v = _realized_vol(returns[an], bis, cfg.vol_fenster_tage)
            w = w * (cfg.vol_ziel / v.replace(0.0, np.nan)).clip(upper=1.5).fillna(1.0)
        return w * cfg.max_brutto / w.sum() if w.sum() > cfg.max_brutto else w

    if cfg.strategie == "ma_filter":
        an = []
        for a in verfuegbar:
            reihe = p[a].dropna()
            if reihe.iloc[-1] > reihe.rolling(cfg.ma_tage).mean().iloc[-1]:
                an.append(a)
    else:
        mom = _momentum(prices[verfuegbar], bis, cfg.lookback_monate,
                        cfg.skip_monate).dropna()
        if mom.empty:
            return pd.Series(dtype=float)
        if cfg.strategie == "dualmom":
            mom = mom.sort_values(ascending=False)
            if mom.iloc[0] <= huerde:
                an = []
            else:
                an = [a for a in mom.index[:cfg.top_n] if mom[a] > huerde]
        else:  # tsmom
            an = [a for a in verfuegbar if a in mom.index and mom[a] > huerde]

    if not an:
        return pd.Series(dtype=float)

    w = pd.Series(1.0 / len(an), index=an)

    if cfg.vol_ziel > 0:
        vol = _realized_vol(returns[an], bis, cfg.vol_fenster_tage)
        skal = (cfg.vol_ziel / vol.replace(0.0, np.nan)).clip(upper=3.0).fillna(1.0)
        w = w * skal
        if cfg.vol_ebene == "depot" and len(an) > 1:
            # Depotvola aus der Kovarianz - nur Daten bis `bis`.
            cov = returns[an].loc[:bis].tail(cfg.vol_fenster_tage).cov() * TRADING_DAYS
            pv = float(np.sqrt(max(w.values @ cov.values @ w.values, 0.0)))
            if pv > 0:
                w = w * min(cfg.vol_ziel / pv, 3.0)

    if w.sum() > cfg.max_brutto:
        w = w * cfg.max_brutto / w.sum()
    return w


# ---------------------------------------------------------------------------
@dataclass
class TrendResult:
    equity_curve: pd.Series
    weights: pd.DataFrame
    turnover: pd.Series
    config: TrendConfig
    kosten_anteil_kum: float
    n_assets: int

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
        jahre = len(eq) / TRADING_DAYS
        m["n_rebalances"] = int(len(self.turnover))
        m["turnover_pa"] = float(self.turnover.sum() / jahre) if jahre else 0.0
        m["kosten_pa"] = float(self.kosten_anteil_kum / jahre) if jahre else 0.0
        if not self.weights.empty:
            invest = self.weights.sum(axis=1).clip(upper=1.0)
            m["cash_anteil"] = float(1.0 - invest.mean())
            m["monate_voll_cash"] = float((invest < 0.01).mean())
        return m

    def jahres_renditen(self) -> dict[int, float]:
        eq = self.equity_curve
        out = {}
        for j in sorted({t.year for t in eq.index}):
            ej = eq[eq.index.year == j]
            if len(ej) >= 2:
                out[j] = float(ej.iloc[-1] / ej.iloc[0] - 1)
        return out


def run(prices: pd.DataFrame, cfg: TrendConfig | None = None, *,
        start: str | pd.Timestamp | None = None,
        end: str | pd.Timestamp | None = None) -> TrendResult:
    """Backtest: monatliches Rebalancing, taegliche Bewertung.

    Args:
        prices: DataFrame Datum x Asset, **total-return-bereinigt**
            (Dividenden reinvestiert - bei Anleihen-ETFs ist die
            Ausschuettung der Grossteil der Rendite).
    """
    cfg = cfg or TrendConfig()
    cfg.pruefe()

    prices = prices.sort_index()
    prices = prices[~prices.index.duplicated(keep="last")]
    returns = prices.pct_change()

    def _ts(x, vorgabe):
        if x is None:
            return vorgabe
        t = pd.Timestamp(x)
        if t.tz is None and prices.index.tz is not None:
            t = t.tz_localize(prices.index.tz)
        elif t.tz is not None and prices.index.tz is None:
            t = t.tz_localize(None)
        return t

    start = _ts(start, prices.index[0])
    end = _ts(end, prices.index[-1])

    # Cash-Reihe abtrennen: Sie verzinst den nicht investierten Anteil
    # und darf weder in die Rangliste noch in die Benchmark.
    cash_r: pd.Series | None = None
    if cfg.cash_symbol:
        if cfg.cash_symbol not in prices.columns:
            raise ValueError(f"cash_symbol {cfg.cash_symbol!r} nicht in den "
                             f"Kursen - ohne Reihe keine Verzinsung.")
        cash_r = prices[cfg.cash_symbol].pct_change().fillna(0.0)
        cash_kurse = prices[cfg.cash_symbol]
        prices = prices.drop(columns=[cfg.cash_symbol])
        returns = returns.drop(columns=[cfg.cash_symbol])
    else:
        cash_kurse = None

    termine = _rebalance_termine(prices.index, cfg.rebalance,
                                 cfg.rebalance_versatz_tage)
    # Vorlauf: so viel Historie, wie die Strategie WIRKLICH braucht.
    #
    # Bis zum 13.09.2026 stand hier `lookback + ma_tage + 10` - fuer jede
    # Strategie, obwohl `ma_tage` (200 Tage) nur der ma_filter benutzt.
    # dualmom wartete damit rund zehn Monate auf einen gleitenden
    # Durchschnitt, den es nie berechnet, und der Backtest auf dem
    # eigenen Vorrat begann im Februar 2022 statt im Fruehjahr 2021.
    # Zehn Monate Daten lagen ungenutzt (BEFUNDE §G93).
    #
    # Das Vol-Fenster gehoert dagegen fuer alle hinein, die Vol-Targeting
    # benutzen: Ohne gefuelltes Fenster ist die erste Skalierung Zufall.
    warmup = cfg.max_lookback() * TAGE_PRO_MONAT + 10
    if cfg.strategie == "ma_filter":
        warmup += cfg.ma_tage
    if cfg.vol_ziel and cfg.vol_ziel > 0:
        warmup = max(warmup, cfg.vol_fenster_tage + 10)
    termine = pd.DatetimeIndex([
        t for t in termine
        if t >= start and t <= end
        and len(prices.loc[:t].dropna(how="all")) > warmup
    ])
    if len(termine) < 6:
        raise ValueError("Zu wenige Rebalance-Termine im Zeitraum.")

    erster = termine[0]
    equity = float(cfg.startkapital)
    w_akt = pd.Series(dtype=float)        # gedriftete Gewichte (Anteil an Equity)
    eq_hist: list[tuple[pd.Timestamp, float]] = []
    w_hist: list[dict] = []
    turnover_hist: list[tuple[pd.Timestamp, float]] = []
    kosten_kum = 0.0
    termine_set = set(termine)
    cash_tag = cfg.cash_rendite_pa / TRADING_DAYS

    lauf = prices.index[(prices.index >= erster) & (prices.index <= end)]
    for k, tag in enumerate(lauf):
        if k > 0:
            r = returns.loc[tag]
            neu = (w_akt * (1.0 + r.reindex(w_akt.index).fillna(0.0))) if not w_akt.empty \
                else pd.Series(dtype=float)
            c_tag = float(cash_r.loc[tag]) if cash_r is not None else cash_tag
            cash_w = max(0.0, 1.0 - float(w_akt.sum())) * (1.0 + c_tag)
            gesamt = float(neu.sum()) + cash_w
            equity *= gesamt
            w_akt = (neu / gesamt) if gesamt > 0 and not neu.empty else pd.Series(dtype=float)
        eq_hist.append((tag, equity))

        if tag in termine_set:
            w_ziel = ziel_gewichte(prices, returns, tag, cfg,
                                   cash_kurse=cash_kurse)
            union = w_akt.index.union(w_ziel.index)
            wa = w_akt.reindex(union).fillna(0.0)
            wz = w_ziel.reindex(union).fillna(0.0)
            turnover = float((wz - wa).abs().sum())
            kosten = turnover * (cfg.kosten_bps + cfg.slippage_bps) / 10_000.0
            equity *= (1.0 - kosten)
            kosten_kum += kosten
            w_akt = w_ziel[w_ziel.abs() > 1e-9]
            w_hist.append({"datum": tag, **w_ziel.to_dict()})
            turnover_hist.append((tag, turnover))

    eq = pd.Series(dict(eq_hist)).sort_index()
    wdf = pd.DataFrame(w_hist).set_index("datum") if w_hist else pd.DataFrame()
    return TrendResult(
        equity_curve=eq,
        weights=wdf.fillna(0.0),
        turnover=pd.Series(dict(turnover_hist)).sort_index() if turnover_hist
        else pd.Series(dtype=float),
        config=cfg,
        kosten_anteil_kum=kosten_kum,
        n_assets=prices.shape[1],
    )


# ---------------------------------------------------------------------------
# Benchmarks
# ---------------------------------------------------------------------------
def _bh(prices: pd.Series, kapital: float) -> pd.Series:
    p = prices.dropna()
    return kapital * (p / p.iloc[0])


def benchmark_kurven(prices: pd.DataFrame, kapital: float,
                     ab: pd.Timestamp) -> dict[str, pd.Series]:
    """SPY B&H, 60/40 (SPY/IEF, monatlich), Gleichgewicht-alle B&H."""
    out: dict[str, pd.Series] = {}
    px = prices[prices.index >= ab]
    if "SPY" in px:
        out["SPY B&H"] = _bh(px["SPY"], kapital)
    if "SPY" in px and "IEF" in px:
        r = px[["SPY", "IEF"]].pct_change().dropna()
        w = pd.Series({"SPY": 0.6, "IEF": 0.4})
        # monatlich zuruecksetzen -> naeherungsweise: gewichtete Tagesrendite
        # bei taeglichem Rebalancing (Unterschied zu monatlich ist < 0,1 %/Jahr)
        port = (r * w).sum(axis=1)
        out["60/40"] = kapital * (1 + port).cumprod()
    ew_cols = [c for c in px.columns if px[c].notna().sum() > 60]
    if len(ew_cols) >= 2:
        r = px[ew_cols].pct_change().dropna()
        out["EW alle B&H"] = kapital * (1 + r.mean(axis=1)).cumprod()
    return out


def _kennz(eq: pd.Series) -> dict:
    from .backtest import compute_metrics

    if eq is None or len(eq.dropna()) < 30:
        return {}
    return compute_metrics(eq.pct_change().dropna())


# ---------------------------------------------------------------------------
def auswerten(result: TrendResult, prices: pd.DataFrame, *,
              n_varianten: int = 1) -> str:
    cfg = result.config
    eq = result.equity_curve
    m = result.metrics()
    ab = eq.index[0]
    bench = benchmark_kurven(prices, float(cfg.startkapital), ab)

    L = ["=" * 76, "  TRENDBOT - HISTORIENLAUF", "=" * 76]
    L.append(f"  Strategie {cfg.strategie} | Lookback {cfg.lookback_monate}-"
             f"{cfg.skip_monate} M | Vol-Ziel "
             f"{'aus' if cfg.vol_ziel == 0 else f'{cfg.vol_ziel:.0%}'} | "
             f"{cfg.rebalance} | Kosten {cfg.kosten_bps:g}+{cfg.slippage_bps:g} bps")
    L.append(f"  {result.n_assets} Assets | {eq.index[0].date()} .. "
             f"{eq.index[-1].date()} | {len(result.turnover)} Rebalances")
    L.append("")

    L.append("  KENNZAHLEN                 Strategie" + "".join(
        f"{n:>14}" for n in bench))
    def zeile(label, key, fmt):
        vals = [m.get(key, float("nan"))] + [_kennz(bench[n]).get(key, float("nan"))
                                             for n in bench]
        L.append(f"  {label:<22}" + "".join(
            (fmt.format(v) if np.isfinite(v) else f"{'-':>14}") for v in vals))
    zeile("CAGR", "cagr", "{:>14.2%}")
    zeile("Vol p.a.", "ann_vol", "{:>14.1%}")
    zeile("Sharpe", "sharpe", "{:>14.2f}")
    zeile("Sortino", "sortino", "{:>14.2f}")
    zeile("Max Drawdown", "max_drawdown", "{:>14.1%}")
    zeile("Calmar", "calmar", "{:>14.2f}")
    L.append("")
    L.append(f"  Turnover p.a.   {m.get('turnover_pa', 0):>6.2f}   "
             f"Kostendrag p.a. {m.get('kosten_pa', 0):>6.2%}   "
             f"Cash-Anteil {m.get('cash_anteil', 0):>5.0%}   "
             f"Monate voll Cash {m.get('monate_voll_cash', 0):>4.0%}")
    L.append("")

    # --- Jahr fuer Jahr gegen 60/40 ---
    jr = result.jahres_renditen()
    b6040 = bench.get("60/40")
    bspy = bench.get("SPY B&H")
    L.append(f"  {'Jahr':>6} {'Strat':>9} {'60/40':>9} {'SPY':>9}  Diff z. 60/40")
    schlaege_6040 = 0
    n_jahre = 0
    for j in sorted(jr):
        s = jr[j]
        def jr_bench(b):
            if b is None:
                return float("nan")
            bj = b[b.index.year == j]
            return float(bj.iloc[-1] / bj.iloc[0] - 1) if len(bj) >= 2 else float("nan")
        r6040, rspy = jr_bench(b6040), jr_bench(bspy)
        diff = s - r6040 if np.isfinite(r6040) else float("nan")
        if np.isfinite(diff):
            n_jahre += 1
            schlaege_6040 += int(diff > 0)
        L.append(f"  {j:>6} {s:>9.1%} {r6040:>9.1%} {rspy:>9.1%}  {diff:>+9.1%}")
    anteil = schlaege_6040 / n_jahre if n_jahre else 0.0
    L.append(f"  -> schlaegt 60/40 in {schlaege_6040}/{n_jahre} Jahren "
             f"({anteil:.0%})")
    L.append("")

    # --- Gate aus docs/TRENDBOT.md §5 ---
    L.append("  " + "-" * 72)
    L.append("  GATE (docs/TRENDBOT.md §5)")
    L.append("  " + "-" * 72)
    tr_strat = result.total_return
    tr_6040 = float(b6040.iloc[-1] / b6040.iloc[0] - 1) if b6040 is not None else float("nan")
    dd_strat = m.get("max_drawdown", float("nan"))
    dd_spy = _kennz(bspy).get("max_drawdown", float("nan")) if bspy is not None else float("nan")

    g1 = (tr_strat > tr_6040) and (anteil >= 0.60)
    g2 = np.isfinite(dd_strat) and np.isfinite(dd_spy) and dd_strat > dd_spy  # weniger negativ
    L.append(f"  1) schlaegt 60/40 gesamt UND >=60% Jahre : "
             f"{'JA' if g1 else 'NEIN'}  "
             f"(gesamt {tr_strat:+.0%} vs {tr_6040:+.0%}, Jahre {anteil:.0%})")
    L.append(f"  2) Max-Drawdown kleiner als SPY B&H      : "
             f"{'JA' if g2 else 'NEIN'}  "
             f"({dd_strat:.0%} vs {dd_spy:.0%})")
    L.append(f"  3) Walk-Forward-Vorsprich stabil          : mit --walk-forward pruefen")
    L.append(f"  4) ueberlebt doppelte Kosten (4 bps)     : mit --kosten-check pruefen")
    L.append("")
    if n_varianten > 1:
        mt = float(np.sqrt(2 * np.log(n_varianten)) + 0.5)
        L.append(f"  {n_varianten} Varianten geprueft -> Zufallsmaximum t ~ {mt:.2f}. "
                 f"Die beste ist per Konstruktion die beste (§B2/§B4).")
    L.append("  yfinance-ETF-Daten, Total-Return. Fuer den Live-Betrieb kommen")
    L.append("  die Kurse von Alpaca (§TRENDBOT §7).")
    L.append("=" * 76)
    return "\n".join(L)


def vergleich(prices: pd.DataFrame, *,
              strategien=("tsmom", "dualmom", "ma_filter"),
              lookbacks=(6, 9, 12), vol_ziele=(0.0, 0.10),
              basis: TrendConfig | None = None,
              start=None, end=None) -> pd.DataFrame:
    """Alle Strategie x Lookback x Vol-Ziel-Kombinationen + Benchmarks."""
    basis = basis or TrendConfig()
    zeilen = []
    for strat in strategien:
        for lb in lookbacks:
            for vz in vol_ziele:
                cfg = replace(basis, strategie=strat, lookback_monate=lb, vol_ziel=vz)
                try:
                    res = run(prices, cfg, start=start, end=end)
                except Exception as e:  # noqa: BLE001
                    zeilen.append({"strategie": strat, "lookback": lb, "vol_ziel": vz,
                                   "fehler": type(e).__name__})
                    continue
                m = res.metrics()
                zeilen.append({
                    "strategie": strat, "lookback": lb,
                    "vol_ziel": ("aus" if vz == 0 else f"{vz:.0%}"),
                    "CAGR": m.get("cagr", float("nan")),
                    "MaxDD": m.get("max_drawdown", float("nan")),
                    "Sharpe": m.get("sharpe", float("nan")),
                    "Calmar": m.get("calmar", float("nan")),
                    "TO_pa": m.get("turnover_pa", float("nan")),
                    "Cash": m.get("cash_anteil", float("nan")),
                })
    df = pd.DataFrame(zeilen)
    return df.sort_values("Sharpe", ascending=False) if "Sharpe" in df else df


def walk_forward(prices: pd.DataFrame, *, basis: TrendConfig | None = None,
                 lookbacks=(6, 9, 12), start=None, end=None) -> dict:
    """Je Kalenderjahr den bis dahin besten Lookback (nach Sharpe) waehlen,
    im naechsten Jahr messen. Traegt die Auswahl vorwaerts?
    """
    basis = basis or TrendConfig()
    per_lb: dict[int, TrendResult] = {}
    for lb in lookbacks:
        per_lb[lb] = run(prices, replace(basis, lookback_monate=lb),
                         start=start, end=end)

    jahre = sorted(set().union(*[set(r.jahres_renditen()) for r in per_lb.values()]))
    b = benchmark_kurven(prices, float(basis.startkapital),
                         per_lb[lookbacks[0]].equity_curve.index[0])
    b6040 = b.get("60/40")

    zeilen, diffs = [], []
    for pos in range(2, len(jahre) - 1):
        train = jahre[:pos + 1]
        testj = jahre[pos + 1]
        sharpe_bis = {}
        for lb, r in per_lb.items():
            eq = r.equity_curve
            eqt = eq[eq.index.year.isin(train)]
            if len(eqt) > 60:
                dr = eqt.pct_change().dropna()
                sharpe_bis[lb] = float(dr.mean() / dr.std() * np.sqrt(TRADING_DAYS)) \
                    if dr.std() > 0 else float("nan")
        if not sharpe_bis:
            continue
        best = max(sharpe_bis, key=lambda k: (sharpe_bis[k]
                                              if np.isfinite(sharpe_bis[k]) else -9))
        rj = per_lb[best].jahres_renditen().get(testj, float("nan"))
        r6040 = float("nan")
        if b6040 is not None:
            bj = b6040[b6040.index.year == testj]
            if len(bj) >= 2:
                r6040 = float(bj.iloc[-1] / bj.iloc[0] - 1)
        if np.isfinite(rj) and np.isfinite(r6040):
            diffs.append(rj - r6040)
            zeilen.append({"jahr": testj, "lookback": best, "strat_rendite": rj,
                           "b6040": r6040, "diff": rj - r6040})
    d = pd.Series(diffs)
    return {
        "zeilen": zeilen,
        "n_jahre": len(d),
        "mittel_diff": float(d.mean()) if len(d) else float("nan"),
        "jahre_mit_vorsprung": int((d > 0).sum()),
        "t": float(d.mean() / (d.std(ddof=1) / np.sqrt(len(d))))
        if len(d) > 2 and d.std(ddof=1) > 0 else float("nan"),
    }
