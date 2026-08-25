#!/usr/bin/env python3
"""Schritt 36: Marktorder gegen Limitorder auf identischer Historie.

**Die Frage (BEFUNDE §G34).** Der Spread ist 54 % der Rundlaufkosten.
Der Live-Bot sendet ausschliesslich Marktorders und zahlt ihn damit per
Konstruktion. Faellt der effektive Spread von 5 auf 3 bps, sinkt der
Breakeven von 0,1423 % auf 0,1022 % - und die Luecke zum gemessenen
Vorsprung von +0,11 % je Trade schliesst sich vollstaendig.

**Was dieser Lauf misst - und warum er nicht geschoent ist.** Beide
Seiten sehen dieselben Tage, Symbole und Kurse; der einzige Unterschied
ist der Ordertyp. Die Limitorder spart die Spanne, zahlt dafuer aber
zwei Preise, die der Lauf automatisch mitnimmt:

    VERPASSTE EINSTIEGE   Kommt der Kurs nie an die Marke, entfaellt der
                          Trade ersatzlos (`limit_nicht_gefuellt`).
    ADVERSE SELEKTION     Ausgefuehrt wird bevorzugt, wenn der Kurs
                          weiterfaellt - also gerade dann, wenn die
                          These schlechter aussieht. Das faellt ohne
                          Zutun in die Trade-Ergebnisse.

Die Fuellregel ist bewusst konservativ: Das Tagestief muss die Marke um
`--puffer` UNTERSCHREITEN, blosses Beruehren zaehlt nicht. Sonst machte
das Modell exakt den Fehler, den Alpacas Papierdepot macht - und der
laesst Limitorders kuenstlich gut aussehen.

    python scripts/36_limit_vergleich.py                    # 8 Jahre, 800 Symbole
    python scripts/36_limit_vergleich.py --offsets 5,10,25,50

**Was dieser Lauf darf.** Verwerfen. Abnehmen darf ihn nur der
Vorwaertsbetrieb - und der kann es fuer diese Frage NICHT im
Papierdepot, weil Alpaca dort Limitorders unrealistisch fuellt (§G34).
Ein Livegang braucht deshalb echtes Geld in kleiner Groesse oder eine
Messung der tatsaechlichen Fuellquote. Das ist eine Entscheidung fuer
spaeter, nicht fuer diesen Lauf.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from alpaca_bot import simulate, universe  # noqa: E402
from alpaca_bot.config import code_version  # noqa: E402
from alpaca_bot.engine import EngineConfig  # noqa: E402
from alpaca_bot.lernlauf_eval import (  # noqa: E402
    paarweiser_test, schwelle_sigma, trennschaerfe,
)

LIVE_BASIS = {"deploy_to_target": True, "allow_topup": True}


def lauf(bars, markt, ecfg, scfg) -> tuple[pd.Series, pd.DataFrame, dict]:
    res = simulate.run(bars, engine_config=ecfg, sim_config=scfg,
                       market=markt, verbose=False)
    eq = pd.Series(dict(res.equity_curve)) if isinstance(res.equity_curve, list) \
        else pd.Series(res.equity_curve)
    eq.index = pd.DatetimeIndex(pd.to_datetime(eq.index)).tz_localize(None).normalize()
    return eq, res.trades, getattr(res, "blocked", {}) or {}


def kennzahlen(eq: pd.Series, trades: pd.DataFrame) -> dict:
    if trades.empty:
        return {"rendite": eq.iloc[-1] / eq.iloc[0] - 1, "trades": 0,
                "je_trade": float("nan"), "treffer": float("nan")}
    return {
        "rendite": eq.iloc[-1] / eq.iloc[0] - 1,
        "trades": len(trades),
        "je_trade": float(trades["return_pct"].mean()),
        "treffer": float((trades["return_pct"] > 0).mean()),
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--jahre", type=float, default=8.0)
    p.add_argument("--symbole", type=int, default=800)
    p.add_argument("--kapital", type=float, default=30_000.0)
    p.add_argument("--offsets", default="5,10,25,50",
                   help="Limitmarken in bps unter dem Entscheidungskurs")
    p.add_argument("--puffer", type=float, default=2.0,
                   help="Um so viel bps muss das Tief die Marke unterschreiten")
    args = p.parse_args()
    offsets = [float(x) for x in args.offsets.split(",") if x.strip()]

    print("=" * 78)
    print(f"  MARKT- GEGEN LIMITORDER  |  {args.jahre:g} Jahre  |  Code {code_version()}")
    print("=" * 78)

    from alpaca_bot.shadow_daten import MARKET_SYMBOL, lade_bars

    syms = universe.load_universe(max_symbols=args.symbole)
    print(f"  Universum : {len(syms)} Symbole")
    bars = lade_bars([*syms, MARKET_SYMBOL], args.jahre, verbose=True)
    markt = bars.xs(MARKET_SYMBOL, level="symbol")["close"].astype(float)
    ecfg = EngineConfig.for_reversal(**LIVE_BASIS)

    print("\n  [1] Marktorder (der heutige Live-Bot) ...", flush=True)
    eq_markt, tr_markt, _ = lauf(
        bars, markt, ecfg,
        simulate.SimConfig(initial_cash=args.kapital, log_to_journal=False))
    k_markt = kennzahlen(eq_markt, tr_markt)
    print(f"      {k_markt['rendite']:+.1%}  {k_markt['trades']} Trades  "
          f"{k_markt['je_trade']:+.4%} je Trade")

    zeilen = []
    for off in offsets:
        print(f"\n  [2] Limitorder, {off:g} bps unter dem Entscheidungskurs ...",
              flush=True)
        scfg = simulate.SimConfig(
            initial_cash=args.kapital, log_to_journal=False,
            limit_einstieg=True, limit_offset_bps=off, limit_puffer_bps=args.puffer)
        eq_lim, tr_lim, blocked = lauf(bars, markt, ecfg, scfg)
        k = kennzahlen(eq_lim, tr_lim)
        nicht_gefuellt = blocked.get("limit_nicht_gefuellt", 0)
        versuche = k["trades"] + nicht_gefuellt
        quote = k["trades"] / versuche if versuche else float("nan")

        paar = paarweiser_test(eq_lim, eq_markt, schwelle_sigma(len(offsets)))
        ts = trennschaerfe(eq_lim, eq_markt, schwelle_sigma(len(offsets)))
        zeilen.append({
            "offset_bps": off, "rendite": k["rendite"], "trades": k["trades"],
            "je_trade": k["je_trade"], "fuellquote": quote,
            "nicht_gefuellt": nicht_gefuellt, "t": paar.t_wert,
            "nachweisbar_80": ts.mit_80_prozent,
        })
        print(f"      {k['rendite']:+.1%}  {k['trades']} Trades  "
              f"{k['je_trade']:+.4%} je Trade  |  Fuellquote {quote:.0%}  "
              f"({nicht_gefuellt} verpasst)")

    print("\n" + "=" * 78)
    print("  ERGEBNIS - Limitorder gegen Marktorder")
    print("=" * 78)
    print(f"  Marktorder (Basis): {k_markt['rendite']:+.1%}, "
          f"{k_markt['trades']} Trades, {k_markt['je_trade']:+.4%} je Trade\n")
    df = pd.DataFrame(zeilen)
    for spalte, fmt in (("rendite", "{:+.1%}"), ("je_trade", "{:+.4%}"),
                        ("fuellquote", "{:.0%}")):
        df[spalte] = df[spalte].map(lambda v, f=fmt: f.format(v) if pd.notna(v) else "-")
    print(df.to_string(index=False))

    print(f"\n  Zufallsschwelle bei {len(offsets)} geprueften Marken: "
          f"|t| > {schwelle_sigma(len(offsets))}")
    print()
    print("  Massgeblich ist NICHT die Gesamtrendite, sondern der gepaarte")
    print("  t-Wert: Beide Seiten sehen dieselben Tage, der Marktfaktor")
    print("  kuerzt sich heraus. Und der Vergleich JE TRADE zeigt, ob die")
    print("  gesparte Spanne die verpassten Einstiege ueberwiegt - eine")
    print("  hoehere Gesamtrendite bei drastisch weniger Trades kann auch")
    print("  bedeuten, dass schlicht weniger gehandelt wurde.")
    print()
    print("  Dieser Lauf darf VERWERFEN, nicht abnehmen. Und Vorsicht: Die")
    print("  uebliche Abnahme im Papierdepot geht hier NICHT - Alpaca")
    print("  fuellt Limitorders dort unrealistisch grosszuegig (§G34).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
