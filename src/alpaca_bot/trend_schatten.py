"""Vorwaerts-Schatten fuer die defensive ETF-Allokation (Trendbot Phase 2).

**Warum das existiert.** §G52 hat die Trendfolge-/Dual-Momentum-Familie
auf ETFs gemessen: Sharpe 0,88, Max-Drawdown −16 %, aber **kein**
Renditevorsprung gegen 60/40 - das Gate aus `docs/TRENDBOT.md` §5 ist
nicht bestanden. Der Nutzer hat am 04.09.2026 die bewusste
**Produktentscheidung** getroffen, die defensive Variante trotzdem als
Phase 2 vorwaerts zu verfolgen (§G52 Option 2: „eine eigene, vorab zu
treffende Produktentscheidung - kein bestandenes Gate").

**Was dieser Schatten tut - und was nicht.** Er sendet **keine Orders**.
Er zieht taeglich die aktuellen ETF-Kurse von Alpaca, rechnet die
festgeschriebene Konfiguration (`PHASE2_CONFIG`) durch und schreibt fort:

  * die simulierte Equity-Kurve ab dem Startdatum des Schattens
  * die Zielgewichte an jedem Monats-Rebalance
  * die heutigen Zielgewichte (was der Bot jetzt halten wuerde)

Nach ~4-6 Wochen liegt eine echte Vorwaerts-Aufzeichnung vor: Deckt sich
das Live-Signal mit dem Backtest, waere der Verlauf wie erwartet? Erst
danach faellt die Live-Entscheidung (`docs/TRENDBOT.md` Phase 3).

Reiner Lese-/Rechenbetrieb, kein Import von `trading.py`.
"""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict, replace

import pandas as pd

from . import trend
from .config import DATA_DIR

DB = DATA_DIR / "trend_schatten.sqlite"

# Die festgeschriebene Phase-2-Konfiguration. Beste Variante aus §G52
# (dualmom, 9-Monats-Lookback, 10 % Vol-Ziel). Aenderungen hier sind eine
# neue Voranmeldung, keine Nebenwirkung.
PHASE2_CONFIG = trend.TrendConfig(
    strategie="dualmom", lookback_monate=9, skip_monate=1, top_n=3,
    vol_ziel=0.10, vol_fenster_tage=60, max_brutto=1.0,
    kosten_bps=2.0, slippage_bps=1.0, startkapital=100_000.0,
    rebalance="monatlich",
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS equity (
    datum       TEXT PRIMARY KEY,
    wert        REAL NOT NULL,
    invest_anteil REAL
);
CREATE TABLE IF NOT EXISTS gewichte (
    datum   TEXT NOT NULL,
    symbol  TEXT NOT NULL,
    gewicht REAL NOT NULL,
    PRIMARY KEY (datum, symbol)
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


def _meta_lesen(c, schluessel, vorgabe=None):
    r = c.execute("SELECT wert FROM meta WHERE schluessel=?", (schluessel,)).fetchone()
    return r["wert"] if r else vorgabe


def start_datum(prices: pd.DataFrame) -> pd.Timestamp:
    """Zweitletztes Monatsende mit Daten - so ist ab dem ersten Lauf ein
    vollstaendiger Rebalance-Zyklus verfolgt und eine Position bekannt."""
    termine = trend._rebalance_termine(prices.index, "monatlich")
    return termine[-2] if len(termine) >= 2 else termine[0]


def aktualisieren(prices: pd.DataFrame,
                  cfg: trend.TrendConfig | None = None) -> dict:
    """Rechnet die Phase-2-Konfiguration ueber die vorliegende Historie
    durch und schreibt Equity + Rebalance-Gewichte fort. Idempotent: die
    kausale Equity-Kurve ab `start_datum` aendert sich nicht, wenn hinten
    ein Tag dazukommt.
    """
    cfg = cfg or PHASE2_CONFIG
    prices = prices.sort_index()

    # Voller Lauf ueber die verfuegbare Historie (kausal, bei +1 Tag am
    # Ende stabil). Der Schatten misst die Rendite ab seinem Startdatum -
    # der Backtest davor ist nur Kontext.
    res = trend.run(prices, cfg)
    eq = res.equity_curve
    if eq.empty:
        return {"fehler": "keine Equity-Kurve"}

    with _conn() as c:
        sd = _meta_lesen(c, "start_datum")
        if sd is None:
            # Der Schatten startet JETZT: heutiger Stand = Nulllinie. Alles
            # davor ist Backtest-Kontext, gemessen wird die Vorwaerts-Slice.
            sd = str(eq.index[-1].date())
            se = float(eq.iloc[-1])
            c.execute("INSERT OR REPLACE INTO meta VALUES (?,?)", ("start_datum", sd))
            c.execute("INSERT OR REPLACE INTO meta VALUES (?,?)",
                      ("start_equity", str(se)))
            c.execute("INSERT OR REPLACE INTO meta VALUES (?,?)",
                      ("config", json.dumps(asdict(cfg), default=str)))
            c.execute("INSERT OR REPLACE INTO meta VALUES (?,?)",
                      ("angelegt_am", dt.datetime.now(dt.UTC).isoformat()))
        se = float(_meta_lesen(c, "start_equity", str(cfg.startkapital)))

    with _conn() as c:
        for d, w in eq.items():
            invest = None
            if not res.weights.empty and d in res.weights.index:
                invest = float(res.weights.loc[d].clip(lower=0).sum())
            c.execute("INSERT OR REPLACE INTO equity VALUES (?,?,?)",
                      (str(pd.Timestamp(d).date()), float(w), invest))
        for d, row in res.weights.iterrows():
            for sym, g in row.items():
                if abs(float(g)) > 1e-6:
                    c.execute("INSERT OR REPLACE INTO gewichte VALUES (?,?,?)",
                              (str(pd.Timestamp(d).date()), str(sym), float(g)))
        c.execute("INSERT OR REPLACE INTO meta VALUES (?,?)",
                  ("zuletzt_aktualisiert", dt.datetime.now(dt.UTC).isoformat()))

    returns = prices.pct_change()
    heute = prices.index[-1]
    ziel = trend.ziel_gewichte(prices, returns, heute, cfg)
    naechstes_reb = _naechster_rebalance(prices, heute)

    slice_ab = eq[eq.index >= pd.Timestamp(sd, tz=eq.index.tz)]
    dd_seit_start = float((slice_ab / slice_ab.cummax() - 1).min()) if len(slice_ab) else 0.0
    return {
        "start_datum": sd,
        "stand": str(heute.date()),
        "equity": float(eq.iloc[-1]),
        "rendite_seit_start": float(eq.iloc[-1] / se - 1) if se else 0.0,
        "max_drawdown_seit_start": dd_seit_start,
        "ziel_gewichte": {k: round(float(v), 4) for k, v in ziel.items()},
        "cash_anteil": round(max(0.0, 1.0 - float(ziel.sum())), 4),
        "naechster_rebalance": str(naechstes_reb.date()) if naechstes_reb is not None else None,
        "n_equity_punkte": len(eq),
        "tage_vorwaerts": (pd.Timestamp.now(tz="UTC") - pd.Timestamp(sd, tz="UTC")).days,
    }


def _naechster_rebalance(prices: pd.DataFrame, ab: pd.Timestamp):
    """Das erste Monatsende NACH `ab` (grob geschaetzt aus dem Kalender)."""
    naechster_monat = (ab + pd.offsets.MonthBegin(1))
    kal = prices.index[prices.index >= ab]
    kandidat = kal[kal.month == naechster_monat.month]
    if len(kandidat):
        # letzter Handelstag dieses Monats liegt in der Zukunft - hier nur
        # der Monatswechsel als Naeherung
        return kandidat[0]
    return None


def bericht() -> str:
    with _conn() as c:
        eq = pd.read_sql("SELECT * FROM equity ORDER BY datum", c)
        gw = pd.read_sql("SELECT * FROM gewichte ORDER BY datum, symbol", c)
        sd = _meta_lesen(c, "start_datum")
        akt = _meta_lesen(c, "zuletzt_aktualisiert")
    if eq.empty:
        return "  Noch kein Schattenlauf. `scripts/45_trend_schatten.py` ausfuehren."

    from .backtest import compute_metrics

    with _conn() as c:
        se = float(_meta_lesen(c, "start_equity", "100000") or "100000")
    e = eq.set_index("datum")["wert"]
    e.index = pd.to_datetime(e.index)
    vorwaerts = e[e.index >= pd.Timestamp(sd)]
    m = compute_metrics(vorwaerts.pct_change().dropna()) if len(vorwaerts) > 3 else {}
    rendite = float(e.iloc[-1] / se - 1) if se else 0.0
    dd = float((vorwaerts / vorwaerts.cummax() - 1).min()) if len(vorwaerts) else 0.0
    tage_vorwaerts = (pd.Timestamp(eq["datum"].iloc[-1]) - pd.Timestamp(sd)).days

    L = ["=" * 70, "  TRENDBOT-SCHATTEN (defensive ETF-Allokation, Phase 2)", "=" * 70]
    L.append(f"  Start {sd}  |  Stand {eq['datum'].iloc[-1]}  |  "
             f"{tage_vorwaerts} Kalendertage vorwaerts ({len(vorwaerts)} Handelstage)")
    L.append(f"  zuletzt aktualisiert: {akt}")
    L.append("")
    L.append(f"  Simulierte Equity      ${e.iloc[-1]:>12,.0f}")
    L.append(f"  Rendite seit Start     {rendite:>12.2%}")
    L.append(f"  Max Drawdown seit Start{dd:>12.1%}")
    if m:
        L.append(f"  Sharpe (vorwaerts)     {m.get('sharpe', float('nan')):>12.2f}")
    L.append("")
    if not gw.empty:
        letztes = gw[gw["datum"] == gw["datum"].max()]
        L.append(f"  Letztes Rebalance ({gw['datum'].max()}):")
        for _, r in letztes.iterrows():
            L.append(f"    {r['symbol']:<6} {r['gewicht']:>7.1%}")
        cash = 1.0 - letztes["gewicht"].clip(lower=0).sum()
        L.append(f"    {'Cash':<6} {cash:>7.1%}")
    L.append("")
    L.append("  Kein Live-Handel. Vorwaerts-Aufzeichnung fuer die Entscheidung")
    L.append("  in `docs/TRENDBOT.md` Phase 3 (Dez). §G52: das Gate ist NICHT")
    L.append("  bestanden - dies laeuft als bewusste Produktentscheidung.")
    return "\n".join(L)
