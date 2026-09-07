"""Vorwaerts-Schatten: das Pferderennen der defensiven ETF-Allokationen (Trendbot Phase 2).

**Warum das existiert.** §G52 hat die Trendfolge-/Dual-Momentum-Familie
auf ETFs gemessen: Sharpe 0,88, Max-Drawdown −16 %, aber **kein**
Renditevorsprung gegen 60/40 - das Gate aus `docs/TRENDBOT.md` §5 ist
nicht bestanden. Der Nutzer hat am 04.09.2026 die bewusste
**Produktentscheidung** getroffen, die defensive Familie trotzdem als
Phase 2 vorwaerts zu verfolgen.

**Was dieser Schatten tut - und was nicht.** Er sendet **keine Orders**.
Er zieht taeglich die aktuellen ETF-Kurse von Alpaca und verfolgt
**mehrere** Allokationsstrategien parallel (`PHASE2_KANDIDATEN`), jede mit
ihrer simulierten Equity und ihren Zielgewichten ab dem gemeinsamen
Startdatum. So entsteht bis zur Phase-3-Entscheidung (Dez) ein echtes
Vorwaerts-Rennen - und man muss sich jetzt nicht auf `dualmom` festlegen,
sondern nimmt dann die Strategie, die vorwaerts am saubersten laeuft.

`PHASE2_CONFIG` bleibt der primaere Kandidat (dualmom, §G52).

Reiner Lese-/Rechenbetrieb, kein Import von `trading.py`.
"""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict

import pandas as pd

from . import trend
from .config import DATA_DIR

DB = DATA_DIR / "trend_schatten.sqlite"

# Primaerer Kandidat: beste Variante aus §G52.
PHASE2_CONFIG = trend.TrendConfig(
    strategie="dualmom", lookback_monate=9, skip_monate=1, top_n=3,
    vol_ziel=0.10, vol_fenster_tage=60, max_brutto=1.0,
    kosten_bps=2.0, slippage_bps=1.0, startkapital=100_000.0, rebalance="monatlich",
)

# Das Pferderennen - vorab festgelegt am 07.09.2026. Alle low-turnover,
# kostenrobust, ohne Survivorship (ETFs auf grosse Anlageklassen).
PHASE2_KANDIDATEN: dict[str, trend.TrendConfig] = {
    "dualmom": PHASE2_CONFIG,
    "tsmom": trend.TrendConfig(strategie="tsmom", lookback_monate=12, vol_ziel=0.10,
                               kosten_bps=2.0, slippage_bps=1.0),
    "ma_filter": trend.TrendConfig(strategie="ma_filter", ma_tage=200, vol_ziel=0.10,
                                   kosten_bps=2.0, slippage_bps=1.0),
    "gem": trend.TrendConfig(strategie="gem", lookback_monate=12, vol_ziel=0.10,
                             kosten_bps=2.0, slippage_bps=1.0),
    "risk_parity": trend.TrendConfig(strategie="risk_parity", vol_fenster_tage=60,
                                     kosten_bps=2.0, slippage_bps=1.0),
    "risk_parity_defensiv": trend.TrendConfig(strategie="risk_parity",
                                              vol_fenster_tage=60, max_brutto=0.6,
                                              kosten_bps=2.0, slippage_bps=1.0),
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS equity (
    strategie TEXT NOT NULL,
    datum     TEXT NOT NULL,
    wert      REAL NOT NULL,
    PRIMARY KEY (strategie, datum)
);
CREATE TABLE IF NOT EXISTS gewichte (
    strategie TEXT NOT NULL,
    datum     TEXT NOT NULL,
    symbol    TEXT NOT NULL,
    gewicht   REAL NOT NULL,
    PRIMARY KEY (strategie, datum, symbol)
);
CREATE TABLE IF NOT EXISTS meta (
    schluessel TEXT PRIMARY KEY,
    wert       TEXT
);
"""


@contextmanager
def _conn():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    try:
        c.executescript(SCHEMA)
        yield c
        c.commit()
    finally:
        c.close()


def _meta(c, schluessel, vorgabe=None):
    r = c.execute("SELECT wert FROM meta WHERE schluessel=?", (schluessel,)).fetchone()
    return r["wert"] if r else vorgabe


def _lauf_einer(prices: pd.DataFrame, returns: pd.DataFrame, name: str,
                cfg: trend.TrendConfig, sd: str | None, c) -> tuple[str, dict]:
    """Eine Strategie durchrechnen und fortschreiben. Gibt (start_datum, snapshot)."""
    res = trend.run(prices, cfg)
    eq = res.equity_curve
    if eq.empty:
        return sd or "", {"strategie": name, "fehler": "keine Equity"}

    if sd is None:
        sd = str(eq.index[-1].date())

    se_row = c.execute("SELECT wert FROM equity WHERE strategie=? AND datum=?",
                       (name, sd)).fetchone()
    # Erster Lauf dieser Strategie: heutiger Stand = Nulllinie.
    se = float(se_row["wert"]) if se_row else float(eq.iloc[-1])

    for d, w in eq.items():
        c.execute("INSERT OR REPLACE INTO equity VALUES (?,?,?)",
                  (name, str(pd.Timestamp(d).date()), float(w)))
    for d, row in res.weights.iterrows():
        for sym, g in row.items():
            if abs(float(g)) > 1e-6:
                c.execute("INSERT OR REPLACE INTO gewichte VALUES (?,?,?,?)",
                          (name, str(pd.Timestamp(d).date()), str(sym), float(g)))

    heute = prices.index[-1]
    ziel = trend.ziel_gewichte(prices, returns, heute, cfg)
    slice_ab = eq[eq.index >= pd.Timestamp(sd, tz=eq.index.tz)]
    dd = float((slice_ab / slice_ab.cummax() - 1).min()) if len(slice_ab) else 0.0
    m = res.metrics()
    return sd, {
        "strategie": name,
        "equity": float(eq.iloc[-1]),
        "rendite_seit_start": float(eq.iloc[-1] / se - 1) if se else 0.0,
        "max_drawdown_seit_start": dd,
        "sharpe_gesamt": m.get("sharpe", float("nan")),
        "ziel_gewichte": {k: round(float(v), 4) for k, v in ziel.items()},
        "cash_anteil": round(max(0.0, 1.0 - float(ziel.sum())), 4),
    }


def aktualisieren(prices: pd.DataFrame,
                  kandidaten: dict[str, trend.TrendConfig] | None = None) -> dict:
    """Alle Kandidaten durchrechnen und fortschreiben. Idempotent."""
    kandidaten = kandidaten or PHASE2_KANDIDATEN
    prices = prices.sort_index()
    returns = prices.pct_change()

    with _conn() as c:
        sd = _meta(c, "start_datum")
        neu = sd is None
        pro: dict[str, dict] = {}
        for name, cfg in kandidaten.items():
            sd_neu, snap = _lauf_einer(prices, returns, name, cfg, sd, c)
            if sd is None:
                sd = sd_neu
            pro[name] = snap
        if neu:
            c.execute("INSERT OR REPLACE INTO meta VALUES (?,?)", ("start_datum", sd))
            c.execute("INSERT OR REPLACE INTO meta VALUES (?,?)",
                      ("kandidaten", json.dumps({k: asdict(v) for k, v in
                                                 kandidaten.items()}, default=str)))
            c.execute("INSERT OR REPLACE INTO meta VALUES (?,?)",
                      ("angelegt_am", dt.datetime.now(dt.UTC).isoformat()))
        c.execute("INSERT OR REPLACE INTO meta VALUES (?,?)",
                  ("zuletzt_aktualisiert", dt.datetime.now(dt.UTC).isoformat()))

    primaer = pro.get("dualmom", next(iter(pro.values()), {}))
    return {
        "start_datum": sd,
        "stand": str(prices.index[-1].date()),
        "tage_vorwaerts": (pd.Timestamp.now(tz="UTC") - pd.Timestamp(sd, tz="UTC")).days,
        "kandidaten": pro,
        # Rueckwaertskompatibel: Felder des primaeren Kandidaten oben
        **{k: primaer[k] for k in ("equity", "rendite_seit_start",
                                   "max_drawdown_seit_start", "ziel_gewichte",
                                   "cash_anteil") if k in primaer},
    }


def bericht() -> str:
    with _conn() as c:
        eq = pd.read_sql("SELECT * FROM equity ORDER BY strategie, datum", c)
        gw = pd.read_sql("SELECT * FROM gewichte", c)
        sd = _meta(c, "start_datum")
        akt = _meta(c, "zuletzt_aktualisiert")
    if eq.empty:
        return "  Noch kein Schattenlauf. `scripts/45_trend_schatten.py` ausfuehren."

    from .backtest import compute_metrics

    L = ["=" * 74, "  TRENDBOT-SCHATTEN - Pferderennen der ETF-Allokationen (Phase 2)",
         "=" * 74]
    stand = eq["datum"].max()
    tage = (pd.Timestamp(stand) - pd.Timestamp(sd)).days
    L.append(f"  Start {sd}  |  Stand {stand}  |  {tage} Kalendertage vorwaerts")
    L.append(f"  zuletzt aktualisiert: {akt}")
    L.append("")
    L.append(f"  {'Strategie':<20}{'Rendite':>10}{'Max-DD':>9}{'Sharpe':>9}"
             f"  aktuelle Allokation")
    L.append("  " + "-" * 70)
    zeilen = []
    for name, g in eq.groupby("strategie"):
        e = g.set_index("datum")["wert"]
        e.index = pd.to_datetime(e.index)
        vorw = e[e.index >= pd.Timestamp(sd)]
        if len(vorw) < 1:
            continue
        se = float(vorw.iloc[0])
        rendite = float(e.iloc[-1] / se - 1) if se else 0.0
        dd = float((vorw / vorw.cummax() - 1).min()) if len(vorw) else 0.0
        m = compute_metrics(vorw.pct_change().dropna()) if len(vorw) > 5 else {}
        letzte = gw[(gw["strategie"] == name) & (gw["datum"] == gw[gw["strategie"] == name]["datum"].max())]
        alloc = " ".join(f"{r['symbol']}{r['gewicht']*100:.0f}"
                         for _, r in letzte.sort_values("gewicht", ascending=False).iterrows())
        cash = 1.0 - letzte["gewicht"].clip(lower=0).sum()
        if cash > 0.01:
            alloc += f" Cash{cash*100:.0f}"
        zeilen.append((rendite, name, dd, m.get("sharpe", float("nan")), alloc))
    for rendite, name, dd, sharpe, alloc in sorted(zeilen, key=lambda x: -x[0]):
        sh = f"{sharpe:>9.2f}" if sharpe == sharpe else f"{'-':>9}"
        L.append(f"  {name:<20}{rendite:>10.2%}{dd:>9.1%}{sh}  {alloc}")
    L.append("")
    L.append("  Kein Live-Handel. Bis Dez laeuft das Rennen; Phase 3 nimmt die")
    L.append("  Strategie, die vorwaerts am saubersten laeuft (TRENDBOT.md §6a).")
    L.append("  §G52: das Gate ist NICHT bestanden - bewusste Produktentscheidung.")
    return "\n".join(L)
