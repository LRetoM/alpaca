#!/usr/bin/env python3
"""Lohnt es sich, eine schwache Position gegen einen besseren Kandidaten zu tauschen?

**Die Idee (24.08.2026).** Bei 15 von 15 Positionen hoert die Engine auf,
ueberhaupt Kandidaten zu bewerten:

    slots = cfg.max_positions - len(held)
    if slots <= 0:
        return []

Im Schattenbetrieb liegen taeglich **53 bis 232** Kandidaten ueber
`min_score`; gekauft werden drei. Der Rest wird nicht verworfen, sondern
gar nicht erst angesehen. Die Frage ist also berechtigt: Waere es besser,
die schwaechste laufende Position vorzeitig zu verkaufen und den deutlich
besser bewerteten Kandidaten zu nehmen?

**Warum das hier gemessen wird und nicht im Schatten.** BETRIEBSPLAN §4:
Der Historienlauf ist der billige Filter. Er kostet **keinen
Versuchszaehler**, darf eine Idee **verwerfen** und hat Trennschaerfe -
2.149 Ausstiege ueber sieben Jahre statt 13 Handelstage im Schatten. Ein
Flottenplatz waere teuer (er hebt `schwelle_sigma` fuer ALLE laufenden
Messungen) und laut §G23 ohnehin zu grob, um den Effekt zu sehen.

**Was dieser Lauf NICHT darf.** Er darf die Idee nicht abnehmen. Zwei
Gruende stehen in BETRIEBSPLAN §4: Survivorship (Alpaca kennt nur heute
gelistete Symbole, Schein-Vorteil 2-4 pp pro Jahr) und "rueckwaerts ist
kein Vorwaertstest". Jedes Ergebnis ist eine **Obergrenze**.

**Die Regel, die geprueft wird.** An jedem Tag mit vollem Depot:

    bester_freier_score - schwaechster_gehaltener_score >= schwelle
        -> schwaechste Position verkaufen, Kandidaten kaufen

Beide Seiten benutzen den **aktuellen** Score, nicht den vom Einstieg -
sonst vergliche man eine frische Bewertung mit einer alten.

**Was der Tausch kostet.** Einen zusaetzlichen Rundlauf. `simulate.run`
rechnet Spread, Slippage und Gebuehren bei jeder Ausfuehrung mit; die
Zahlen unten sind also netto. Rechnerisch truege sich ein Tausch schon ab
0,015 Score-Differenz (§G27) - genau deshalb ist die Messung noetig und
nicht die Rechnung.

    python scripts/31_tauschregel.py --years 7
    python scripts/31_tauschregel.py --years 7 --schwellen 0.1,0.2,0.3
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from alpaca_bot import simulate, statistik, universe  # noqa: E402
from alpaca_bot.engine import Decision, EngineConfig  # noqa: E402


def tauscher(schwelle: float, protokoll: list):
    """Baut den Haken fuer `simulate.run(nach_entscheidung=...)`.

    `protokoll` sammelt jeden Tausch, damit sich hinterher trennen laesst,
    ob ein Effekt aus vielen kleinen oder wenigen grossen Eingriffen kam
    (§G11: "das gesamte Plus haengt an einem einzigen Teiljahr").
    """

    def haken(snapshot, portfolio, decisions, signals):
        # Nur eingreifen, wenn die Engine NICHTS kaufen konnte. Sonst
        # wuerde die Regel mit den normalen Kaeufen konkurrieren statt
        # die Luecke zu fuellen, die sie schliessen soll.
        if any(d.action in ("buy", "topup") for d in decisions):
            return decisions
        verkauft = {d.symbol for d in decisions if d.action == "sell"}
        gehalten = set(portfolio.positions) - verkauft
        if len(gehalten) < 1:
            return decisions

        cfg = EngineConfig.for_reversal()

        def score(sym):
            f = signals.get(sym)
            if f is None or f.empty or "score" not in f:
                return None
            v = float(f["score"].iloc[-1])
            return v if np.isfinite(v) else None

        # Schwaechste gehaltene Position nach AKTUELLEM Score
        gehalten_scores = {s: score(s) for s in gehalten}
        gehalten_scores = {s: v for s, v in gehalten_scores.items() if v is not None}
        if not gehalten_scores:
            return decisions
        schwach = min(gehalten_scores, key=gehalten_scores.get)
        schwach_score = gehalten_scores[schwach]

        # Bester freier Kandidat - dieselben Filter wie `_find_entries`
        bester, bester_score = None, -np.inf
        for sym in snapshot.bars:
            if sym in portfolio.positions:
                continue
            preis = snapshot.last_price(sym)
            if preis is None or preis < cfg.min_price:
                continue
            v = score(sym)
            if v is None or v < cfg.min_score or v <= bester_score:
                continue
            f = signals[sym]
            dvol = float(f["dollar_volume"].iloc[-1]
                         if "dollar_volume" in f else 0)
            if dvol < cfg.min_dollar_volume:
                continue
            bester, bester_score = sym, v

        if bester is None or (bester_score - schwach_score) < schwelle:
            return decisions

        pos = portfolio.positions[schwach]
        preis_neu = snapshot.last_price(bester) or 0.0
        if preis_neu <= 0:
            return decisions
        f = signals[bester]
        atr = float(f["atr"].iloc[-1]) if "atr" in f else preis_neu * 0.02

        protokoll.append({
            "datum": snapshot.as_of, "raus": schwach, "raus_score": schwach_score,
            "rein": bester, "rein_score": bester_score,
            "differenz": bester_score - schwach_score,
            "gehalten_tage": pos.bars_held,
        })
        return list(decisions) + [
            Decision(symbol=schwach, action="sell",
                     reasons={"ausstiegsgrund": "getauscht",
                              "gegen": bester,
                              "score_differenz": round(bester_score - schwach_score, 4)},
                     conviction=schwach_score,
                     price=snapshot.last_price(schwach) or pos.entry_price),
            Decision(symbol=bester, action="buy",
                     reasons={"tausch": True, "ersetzt": schwach},
                     conviction=bester_score, price=preis_neu,
                     target_notional=pos.qty * (snapshot.last_price(schwach)
                                                or pos.entry_price),
                     stop_price=preis_neu - cfg.stop_atr * atr,
                     target_price=preis_neu + cfg.target_atr * atr),
        ]

    return haken


def kennzahlen(res, name: str) -> dict:
    eq = pd.Series(dict(res.equity_curve)) if isinstance(res.equity_curve, list) \
        else pd.Series(res.equity_curve)
    start, ende = float(eq.iloc[0]), float(eq.iloc[-1])
    r = eq.pct_change().dropna()
    jahre = len(eq) / 252
    return {
        "name": name,
        "rendite": ende / start - 1,
        "p_a": (ende / start) ** (1 / jahre) - 1 if jahre > 0 else 0.0,
        "max_dd": float((eq / eq.cummax() - 1).min()),
        "trades": len(res.trades),
        "tage": len(eq),
        "tagesrenditen": r,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--years", type=float, default=7.0)
    ap.add_argument("--max-symbols", type=int, default=1200)
    ap.add_argument("--schwellen", default="0.10,0.20,0.30",
                    help="Score-Differenzen, ab denen getauscht wird")
    ap.add_argument("--kapital", type=float, default=30_000.0)
    args = ap.parse_args()

    from alpaca_bot.shadow_daten import lade_bars, MARKET_SYMBOL

    syms = universe.load_universe(max_symbols=args.max_symbols)
    print(f"  Universum: {len(syms)} Symbole, {args.years} Jahre")
    bars = lade_bars([*syms, MARKET_SYMBOL], args.years, verbose=True)
    markt = bars.xs(MARKET_SYMBOL, level="symbol")["close"].astype(float)

    ecfg = EngineConfig.for_reversal()
    scfg = simulate.SimConfig(initial_cash=args.kapital, log_to_journal=False)

    print("\n  Grundlauf (ohne Tausch) ...")
    basis = simulate.run(bars, engine_config=ecfg, sim_config=scfg,
                         market=markt, verbose=False)
    ergebnisse = [kennzahlen(basis, "ohne Tausch")]
    protokolle = {}

    for sch in [float(x) for x in args.schwellen.split(",")]:
        print(f"  Tausch ab Score-Differenz {sch:.2f} ...")
        prot: list = []
        res = simulate.run(bars, engine_config=ecfg, sim_config=scfg,
                           market=markt, verbose=False,
                           nach_entscheidung=tauscher(sch, prot))
        ergebnisse.append(kennzahlen(res, f"Tausch ab {sch:.2f}"))
        protokolle[sch] = prot

    print("\n" + "=" * 78)
    print("  TAUSCHREGEL AM HISTORIENLAUF")
    print("=" * 78)
    print(f"  {'Variante':<20} {'Rendite':>9} {'p.a.':>8} {'max DD':>8} "
          f"{'Trades':>7} {'Tausche':>8}")
    for e in ergebnisse:
        sch = e["name"].replace("Tausch ab ", "")
        n_t = len(protokolle.get(float(sch), [])) if sch != "ohne Tausch" else 0
        print(f"  {e['name']:<20} {e['rendite']:>+8.1%} {e['p_a']:>+7.2%} "
              f"{e['max_dd']:>+7.1%} {e['trades']:>7} {n_t:>8}")

    # Gepaarter Test gegen den Grundlauf - dieselbe Logik wie in der Flotte
    print(f"\n  Gepaarter Test der Tagesdifferenz gegen den Grundlauf")
    print(f"  (§B1: maszgeblich sind Handelstage, nicht Trades)")
    b = ergebnisse[0]["tagesrenditen"]
    for e in ergebnisse[1:]:
        d = (e["tagesrenditen"] - b).dropna()
        if len(d) < 30:
            continue
        t = d.mean() / (d.std(ddof=1) / np.sqrt(len(d)))
        print(f"    {e['name']:<20} Mittel {d.mean()*100:+.4f} %/Tag  "
              f"t = {t:+.2f}  ueber {len(d)} Tage")

    for sch, prot in protokolle.items():
        if not prot:
            continue
        p = pd.DataFrame(prot)
        print(f"\n  Tausche bei Schwelle {sch:.2f}: {len(p)}")
        print(f"    mittlere Score-Differenz : {p.differenz.mean():.3f}")
        print(f"    Haltedauer der Verkauften: Median {p.gehalten_tage.median():.0f} Tage")
        print(f"    je Jahr                  : {len(p)/args.years:.0f}")

    print("\n  ACHTUNG: Dieser Lauf darf die Idee VERWERFEN, nicht abnehmen.")
    print("  Survivorship-Bias hebt jedes Ergebnis um 2-4 pp pro Jahr")
    print("  (BETRIEBSPLAN §4). Ein Plus unterhalb dieser Groesse ist kein Befund.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
