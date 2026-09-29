#!/usr/bin/env python3
"""Schritt 33: Trade-Autopsie - was die Engine aus ihren eigenen Trades lernt.

Ein Replay (scripts/31) liefert eine Zahl (CAGR) und eine Trade-Liste. Die
Zahl sagt, OB es geklappt hat; die Trade-Liste sagt, WARUM nicht. Dieses
Skript zerlegt jede Trade-Liste nach Ausstiegsgrund, Haltedauer,
Einstiegs-Score, Einstiegsmonat und Jahr, rekonstruiert den
Investitionsgrad und formuliert daraus maschinell Lehren - Saetze, die als
Befund ins Register (`befunde.py`) gehen und so fuer die naechste Generation
von Tests verfuegbar bleiben.

Beispiel des ersten Einsatzes (2026-09-29, S&P-Replay ohne Stop): 57 % aller
Ausstiege waren "rangverlust" mit Oe -2,3 %, Zeitausstiege dagegen Oe +8,7 %.
Daraus wurde HYP-2027-21 (der Rangverlust ist ein verspaeteter Stop, der
gegen die Umkehr wettet) - registriert VOR dem Gegen-Test.

    python scripts/33_trade_autopsie.py                              # alle simulate_ranking_*.csv
    python scripts/33_trade_autopsie.py --datei results/labor/simulate_ranking_qlib_stop99.csv
    python scripts/33_trade_autopsie.py --kein-register              # nur anzeigen

Ergebnis: results/labor/autopsie_<name>.md je Datei, plus je eine Zeile im
Befundregister (Skript 33, Variante "autopsie").
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from alpaca_bot import befunde  # noqa: E402
from alpaca_bot.config import PROJECT_ROOT  # noqa: E402

OUT_DIR = PROJECT_ROOT / "results" / "labor"
HALTE_KLASSEN = ([0, 10, 21, 42, 63, 10_000], ["<=10", "11-21", "22-42", "43-63", ">63"])


def laden(pfad: Path) -> pd.DataFrame:
    t = pd.read_csv(pfad, parse_dates=["entry_date", "exit_date"])
    for c in ("entry_date", "exit_date"):
        if getattr(t[c].dt, "tz", None) is not None:
            t[c] = t[c].dt.tz_localize(None)
    t["notional"] = t["qty"] * t["entry_price"]
    t["jahr"] = t["entry_date"].dt.year
    t["monat"] = t["entry_date"].dt.month
    return t


def investitionsgrad(t: pd.DataFrame, kapital: float = 100_000) -> pd.Series:
    """Offenes Volumen zu Einstandskursen / (Startkapital + realisierter Gewinn)."""
    tage = pd.bdate_range(t["entry_date"].min(), t["exit_date"].max())
    realisiert = t.groupby("exit_date")["net_pnl"].sum().reindex(tage).fillna(0.0).cumsum()
    offen = pd.Series(0.0, index=tage)
    for r in t.itertuples():
        offen.loc[r.entry_date:r.exit_date] += r.notional
    return offen / (kapital + realisiert)


def _agg(t: pd.DataFrame):
    n_ges = len(t)
    return dict(n=("return_pct", "size"),
                anteil=("return_pct", lambda s: len(s) / n_ges),
                treffer=("return_pct", lambda s: float((s > 0).mean())),
                mittel=("return_pct", "mean"), median=("return_pct", "median"),
                tage=("bars_held", "mean"), pnl=("net_pnl", "sum"))


def tabellen(t: pd.DataFrame) -> dict[str, pd.DataFrame]:
    out: dict[str, pd.DataFrame] = {}
    agg = _agg(t)
    out["ausstieg"] = t.groupby("exit_reason").agg(**agg).sort_values("n", ascending=False)
    t = t.copy()
    t["halte"] = pd.cut(t["bars_held"], HALTE_KLASSEN[0], labels=HALTE_KLASSEN[1])
    out["haltedauer"] = t.groupby("halte", observed=True).agg(**agg)
    if t["entry_score"].nunique() > 8:
        t["score_q"] = pd.qcut(t["entry_score"], 4, labels=["q1", "q2", "q3", "q4_top"])
        out["score_quartil"] = t.groupby("score_q", observed=True).agg(**agg)
    out["einstiegsmonat"] = t.groupby("monat").agg(**agg)
    out["jahr"] = t.groupby("jahr").agg(**agg)
    return out


def lehren(t: pd.DataFrame, tab: dict[str, pd.DataFrame], expo: pd.Series) -> list[str]:
    """Regeln, die aus den Tabellen Saetze machen. Jede Regel ist bewusst simpel und
    nachpruefbar - das Skript soll Hinweise geben, keine Urteile faellen."""
    L: list[str] = []
    a = tab["ausstieg"]
    grosse = a[a["anteil"] >= 0.20]
    pos = a[a["mittel"] > 0]
    for grund, r in grosse[grosse["mittel"] < 0].iterrows():
        satz = (f"Ausstieg '{grund}' traegt {r['anteil']:.0%} der Trades bei Oe {r['mittel']:+.1%} "
                f"(Treffer {r['treffer']:.0%}, Oe {r['tage']:.0f} Tage)")
        if not pos.empty:
            best = pos["mittel"].idxmax()
            satz += (f"; '{best}' dagegen Oe {pos['mittel'].max():+.1%}. Pruefen: verkauft diese Regel "
                     f"NACH dem Verlust statt vor ihm (verspaeteter Stop)?")
        L.append(satz + ".")
    h = tab["haltedauer"]
    if len(h) >= 3 and h["mittel"].iloc[-1] > 0 > h["mittel"].iloc[0]:
        L.append(f"Rendite steigt mit der Haltedauer ({h.index[0]}: {h['mittel'].iloc[0]:+.1%} -> "
                 f"{h.index[-1]}: {h['mittel'].iloc[-1]:+.1%}): die fruehen Ausstiege sind die Verlierer - "
                 f"die Kostenkurve aus 24_ zeigt sich auch im Engine-Pfad.")
    if "score_quartil" in tab:
        q = tab["score_quartil"]
        spanne = float(q["mittel"].iloc[-1] - q["mittel"].iloc[0])
        if abs(spanne) < 0.01:
            L.append(f"Score-Quartil innerhalb der Kaufmenge ohne Wirkung (oben minus unten {spanne:+.2%}): "
                     f"keine Konzentration auf die Top 10, die Rangschwelle reicht.")
        else:
            L.append(f"Score-Quartil wirkt ({spanne:+.2%} oben minus unten): engere Rangschwelle testen.")
    j = tab["jahr"]
    schlecht = j[j["mittel"] < 0]
    if not schlecht.empty:
        L.append("Verlustjahre nach Einstiegsjahr: "
                 + ", ".join(f"{int(y)} ({r['mittel']:+.1%}, n={int(r['n'])})" for y, r in schlecht.iterrows())
                 + " - gegen SPY-Jahr und Regime-Tor pruefen.")
    e = expo[expo > 0]
    if not e.empty:
        L.append(f"Investitionsgrad (zu Einstandskursen) Mittel {e.mean():.0%}, Median {e.median():.0%}, "
                 f"Tage unter 50 %: {float((expo < 0.5).mean()):.0%} - Cash-Bremse "
                 + ("ist ein Hebel." if e.mean() < 0.75 else "ist kein Haupthebel."))
    m = tab["einstiegsmonat"]
    L.append(f"Einstiegsmonat: bester {int(m['mittel'].idxmax())} ({m['mittel'].max():+.1%}), schlechtester "
             f"{int(m['mittel'].idxmin())} ({m['mittel'].min():+.1%}) - nur Notiz: {t['jahr'].nunique()} Jahre "
             f"sind fuer Saisonregeln zu duenn (Versuchszaehler!).")
    return L


def bericht(name: str, t: pd.DataFrame, tab: dict[str, pd.DataFrame], expo: pd.Series,
            saetze: list[str]) -> str:
    def f(df: pd.DataFrame) -> str:
        d = df.copy()
        for c in ("anteil", "treffer", "mittel", "median"):
            d[c] = d[c].map(lambda v: f"{v:+.1%}" if c in ("mittel", "median") else f"{v:.0%}")
        d["tage"] = d["tage"].map(lambda v: f"{v:.0f}")
        d["pnl"] = d["pnl"].map(lambda v: f"{v:,.0f}")
        d.insert(0, str(d.index.name or ""), [str(i) for i in d.index])
        kopf = "| " + " | ".join(str(c) for c in d.columns) + " |"
        trenn = "|" + "---|" * len(d.columns)
        zeilen = ["| " + " | ".join(str(v) for v in row) + " |" for row in d.itertuples(index=False)]
        return "\n".join([kopf, trenn, *zeilen])
    L = [f"# Trade-Autopsie: {name}", "",
         f"{len(t)} Trades, {t['entry_date'].min():%Y-%m-%d} bis {t['exit_date'].max():%Y-%m-%d}, "
         f"Netto-PnL {t['net_pnl'].sum():,.0f} $, Trefferquote {(t['return_pct'] > 0).mean():.1%}, "
         f"Oe je Trade {t['return_pct'].mean():+.2%}.", "", "## Lehren (maschinell formuliert)", ""]
    L += [f"- {s}" for s in saetze]
    for titel, key in (("Ausstiegsgrund", "ausstieg"), ("Haltedauer", "haltedauer"),
                       ("Einstiegs-Score-Quartil", "score_quartil"), ("Einstiegsmonat", "einstiegsmonat"),
                       ("Einstiegsjahr", "jahr")):
        if key in tab:
            L += ["", f"## Nach {titel}", "", f(tab[key])]
    L += ["", "## Investitionsgrad je Jahr", "",
          ", ".join(f"{y}: {v:.0%}" for y, v in expo.groupby(expo.index.year).mean().items()), ""]
    return "\n".join(L)


def autopsie(pfad: Path, kapital: float, register: bool) -> list[str]:
    t = laden(pfad)
    if t.empty:
        print(f"  {pfad.name}: keine Trades")
        return []
    tab = tabellen(t)
    expo = investitionsgrad(t, kapital)
    saetze = lehren(t, tab, expo)
    name = pfad.stem
    text = bericht(name, t, tab, expo, saetze)
    out = OUT_DIR / f"autopsie_{name}.md"
    out.write_text(text, encoding="utf-8")
    print(f"\n=== {name}: {len(t)} Trades -> {out.name}")
    for s in saetze:
        print(f"  - {s}")
    if register:
        a = tab["ausstieg"]
        k = {f"mittel_{g}": float(r["mittel"]) for g, r in a.iterrows()}
        k.update({f"anteil_{g}": float(r["anteil"]) for g, r in a.iterrows()})
        k.update(expo_mittel=float(expo[expo > 0].mean()) if (expo > 0).any() else None,
                 n_trades=int(len(t)), treffer=float((t["return_pct"] > 0).mean()),
                 mittel_je_trade=float(t["return_pct"].mean()))
        panel = name.replace("simulate_ranking_", "").split("_stop")[0]
        urteil = "kandidat" if any("verspaeteter Stop" in s for s in saetze) else "zu_duenn"
        befunde.eintragen(skript="33", panel=panel, variante="autopsie",
                          zeitraum=f"{t['jahr'].min()}-{t['exit_date'].max().year}",
                          parameter={"datei": pfad.name}, kennzahlen=k, urteil=urteil,
                          lehre=" | ".join(saetze), quelle_lauf=str(out))
    return saetze


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--datei", nargs="*", default=None, help="Trade-CSV(s); Standard: alle simulate_ranking_*.csv")
    ap.add_argument("--kapital", type=float, default=100_000)
    ap.add_argument("--kein-register", action="store_true")
    args = ap.parse_args()
    dateien = ([Path(d) for d in args.datei] if args.datei
               else sorted(p for p in OUT_DIR.glob("simulate_ranking_*.csv") if not p.name.endswith("_kapital.csv")))
    if not dateien:
        print("  keine Trade-Dateien gefunden (erst scripts/31_simulate_ranking.py laufen lassen)")
        return 1
    for d in dateien:
        autopsie(d, args.kapital, register=not args.kein_register)
    return 0


if __name__ == "__main__":
    sys.exit(main())
