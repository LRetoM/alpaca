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
# Cash-Verzinsung ueber BIL (0-3 Monate T-Bills) fuer ALLE Kandidaten -
# Korrektur einer falschen Annahme (§G96: pauschal 2 % gegen real 4-5 %
# in 2023-25), keine Strategieaenderung. Gilt einheitlich, bevorzugt also
# keinen Kandidaten. Fehlt BIL an einem Tag, faellt der Lauf SICHTBAR auf
# die Pauschale zurueck (siehe `_lauf_einer`).
_CASH = "BIL"
_BASIS = dict(kosten_bps=2.0, slippage_bps=1.0, startkapital=100_000.0,
              rebalance="monatlich", cash_symbol=_CASH)

# Primaerer Kandidat ab 13.09.2026: dualmom mit 15 % Vol-Ziel.
#
# Nutzerentscheidung vom 13.09.2026 - eine Risikopraeferenz, kein
# Suchergebnis: Bei 15 % statt 10 % Vol-Ziel liefert dieselbe Strategie
# auf eigenen Daten 14,4 % statt 11,1 % im Jahr bei -14,8 % statt -10 %
# Rueckgang und praktisch gleichem Sharpe (§G92, §G96). Der Sharpe faellt
# monoton mit dem Vol-Ziel - der Regler ist sauber, kein Gluecksgriff.
# `dualmom` (10 %) bleibt als eigener Kandidat im Rennen.
PHASE2_CONFIG = trend.TrendConfig(
    strategie="dualmom", lookback_monate=9, skip_monate=1, top_n=3,
    vol_ziel=0.15, vol_fenster_tage=60, max_brutto=1.0, **_BASIS,
)

# Das Pferderennen. Die ersten sechs standen am 07.09.2026 fest;
# `dualmom_15` und `gem_15` kamen am 13.09.2026 dazu - mit EIGENEM
# Startdatum, damit ihr Vorwaertsverlauf nicht rueckwirkend beginnt.
PHASE2_KANDIDATEN: dict[str, trend.TrendConfig] = {
    "dualmom_15": PHASE2_CONFIG,
    "dualmom": trend.TrendConfig(strategie="dualmom", lookback_monate=9,
                                 skip_monate=1, top_n=3, vol_ziel=0.10,
                                 vol_fenster_tage=60, max_brutto=1.0, **_BASIS),
    "gem_15": trend.TrendConfig(strategie="gem", lookback_monate=12,
                                vol_ziel=0.15, **_BASIS),
    "tsmom": trend.TrendConfig(strategie="tsmom", lookback_monate=12,
                               vol_ziel=0.10, **_BASIS),
    "ma_filter": trend.TrendConfig(strategie="ma_filter", ma_tage=200,
                                   vol_ziel=0.10, **_BASIS),
    "gem": trend.TrendConfig(strategie="gem", lookback_monate=12,
                             vol_ziel=0.10, **_BASIS),
    "risk_parity": trend.TrendConfig(strategie="risk_parity",
                                     vol_fenster_tage=60, **_BASIS),
    "risk_parity_defensiv": trend.TrendConfig(strategie="risk_parity",
                                              vol_fenster_tage=60,
                                              max_brutto=0.6, **_BASIS),
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
    """Eine Strategie durchrechnen und fortschreiben. Gibt (start_datum, snapshot).

    `sd` ist das Startdatum DIESER Strategie (None = heute erster Lauf).

    **Die Nulllinie kommt aus der Kurve, nicht aus der Datenbank
    (13.09.2026).** Frueher wurde der Stand am Startdatum aus `equity`
    gelesen. Aendert sich die Verbuchung (etwa Cash ueber BIL statt
    Pauschale), stand dort noch der alte Wert, oben aber der neue - ein
    Sprung in der Rendite, der kein Marktereignis war. Die Strategie ist
    zustandslos: Stand heute geteilt durch Stand am Startdatum, beide
    aus derselben Rechnung, ist die einzige in sich stimmige Rendite.
    Die Datenbank bleibt als Protokoll.
    """
    cash_quelle = cfg.cash_symbol or "pauschale"
    if cfg.cash_symbol and cfg.cash_symbol not in prices.columns:
        # SICHTBAR zurueckfallen, nicht still: Ein fehlender Tag von BIL
        # darf den Lauf nicht kippen - aber es muss im Snapshot stehen.
        from dataclasses import replace as _replace
        cfg = _replace(cfg, cash_symbol="")
        cash_quelle = f"pauschale ({cash_quelle} FEHLT in den Kursen)"
    res = trend.run(prices, cfg)
    eq = res.equity_curve
    if eq.empty:
        return sd or "", {"strategie": name, "fehler": "keine Equity"}

    if sd is None:
        sd = str(eq.index[-1].date())

    # Letzter Stand AM Kalendertag des Starts. `asof(Mitternacht)` griffe
    # den Vortag - die Bars liegen mit Uhrzeit im Index, und 0,17 % Rendite
    # am ersten Tag (13.09.2026) waren genau dieser Off-by-one.
    sd_tag = pd.Timestamp(sd).normalize()
    am_tag = eq[eq.index.normalize() == sd_tag.tz_localize(eq.index.tz)
                if sd_tag.tz is None else eq.index.normalize() == sd_tag]
    if len(am_tag):
        se = float(am_tag.iloc[-1])
    else:
        sd_ts = sd_tag.tz_localize(eq.index.tz) if sd_tag.tz is None else sd_tag
        se = float(eq.asof(sd_ts)) if sd_ts >= eq.index[0] else float(eq.iloc[0])

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
        "start_datum": sd,
        "cash_quelle": cash_quelle,
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
            # Startdatum JE STRATEGIE. Die ersten sechs haben keins - fuer
            # sie gilt das globale (04.09.2026), das hier einmalig als
            # ihr eigenes festgeschrieben wird. Ein spaeter hinzugefuegter
            # Kandidat bekommt den Tag seines ersten Laufs - nie
            # rueckwirkend den Rennstart, sonst waere sein "Vorwaerts"
            # zum Teil rueckwaerts.
            sd_name = _meta(c, f"start_datum:{name}")
            if sd_name is None:
                # Kein eigener Eintrag: Altkandidat (hat schon Equity aus
                # der Zeit vor den Einzel-Startdaten) -> globaler Start.
                # Sonst ein Nachzuegler -> None, also HEUTE.
                war_dabei = c.execute("SELECT 1 FROM equity WHERE strategie=? "
                                      "LIMIT 1", (name,)).fetchone()
                sd_name = sd if war_dabei else None
            sd_neu, snap = _lauf_einer(prices, returns, name, cfg, sd_name, c)
            if sd is None:
                sd = sd_neu
            if _meta(c, f"start_datum:{name}") is None and sd_neu:
                c.execute("INSERT OR REPLACE INTO meta VALUES (?,?)",
                          (f"start_datum:{name}", sd_neu))
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

    primaer = pro.get("dualmom_15", pro.get("dualmom", next(iter(pro.values()), {})))
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
    with _conn() as c:
        starts = {r["schluessel"].split(":", 1)[1]: r["wert"] for r in
                  c.execute("SELECT schluessel, wert FROM meta WHERE "
                            "schluessel LIKE 'start_datum:%'")}
    zeilen = []
    for name, g in eq.groupby("strategie"):
        e = g.set_index("datum")["wert"]
        e.index = pd.to_datetime(e.index)
        sd_name = starts.get(name, sd)
        vorw = e[e.index >= pd.Timestamp(sd_name)]
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
        if sd_name != sd:
            name = f"{name} (ab {sd_name})"
        zeilen.append((rendite, name, dd, m.get("sharpe", float("nan")), alloc))
    for rendite, name, dd, sharpe, alloc in sorted(zeilen, key=lambda x: -x[0]):
        sh = f"{sharpe:>9.2f}" if sharpe == sharpe else f"{'-':>9}"
        L.append(f"  {name:<20}{rendite:>10.2%}{dd:>9.1%}{sh}  {alloc}")
    L.append("")
    L.append("  Kein Live-Handel. Bis Dez laeuft das Rennen; Phase 3 nimmt die")
    L.append("  Strategie, die vorwaerts am saubersten laeuft (TRENDBOT.md §6a).")
    L.append("  §G52: das Gate ist NICHT bestanden - bewusste Produktentscheidung.")
    return "\n".join(L)
