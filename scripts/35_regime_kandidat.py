#!/usr/bin/env python3
"""Schritt 35: Makro- und Nachrichtenregime gegen die Strategie pruefen.

**Die Frage, die dieses Skript beantwortet:** Haengt der Erfolg der
Strategie vom Marktregime ab - und zwar messbar an etwas Besserem als
`SPY > SMA200`?

**Warum das eine andere Pruefkette ist als Schritt 24/34.** Ein
Makrowert (VIX, Zinsstruktur, Credit Spread) ist an einem Tag fuer ALLE
Symbole gleich. Der Querschnitts-IC, mit dem dieses Projekt jeden
Kursfaktor prueft, misst aber, ob ein Faktor die Symbole eines Tages
richtig SORTIERT - eine Konstante sortiert nichts. Wer Makrodaten durch
`24_kandidaten_test.py` schickt, bekommt garantiert IC ~ 0 und haelt das
faelschlich fuer ein Ergebnis.

Der passende Test ist ein Regimetest auf der TAGESRENDITE der Strategie:

    Teile die Handelstage nach dem Makrowert in Baender.
    Unterscheidet sich die mittlere Tagesrendite zwischen den Baendern?

Weil jeder Handelstag genau eine Beobachtung liefert, gibt es die
Ueberlappung aus §B1 hier nicht - gruppiert wird trotzdem (nach Monat),
damit benachbarte Tage nicht als unabhaengig durchgehen.

**Die Luecke, auf die das zielt (§G7/§G8).** Der heutige Regimefilter
setzt den Score ALLER Symbole auf 0, sobald SPY unter seinem
200-Tage-Schnitt liegt - und weil derselbe Score auch die Ausstiegsregel
speist, wird dabei das gesamte Depot in einem Zyklus liquidiert. Das ist
ein Nebeneffekt der geteilten Score-Berechnung, kein Entwurf. Er
betrifft 18 % aller Handelstage. Ein Regimemass, das frueher oder feiner
dreht (Credit Spreads drehen typischerweise vor Aktien), waere damit
kein weiterer Kursfaktor, sondern eine Verbesserung an einer belegten
Schwachstelle.

    python scripts/35_regime_kandidat.py                  # Makro (kein Schluessel noetig)
    python scripts/35_regime_kandidat.py --mit-gdelt      # zusaetzlich Nachrichten
    python scripts/35_regime_kandidat.py --jahre 15 --symbole 800

**Was dieser Lauf darf und was nicht** - wie jeder Historienlauf
(`UMBAUPLAN.md`): Er darf eine Idee VERWERFEN. Abnehmen darf ihn nur der
Vorwaertsbetrieb. Survivorship und der fehlende Nachrichtenfaktor
(§G24) gelten hier genauso.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from alpaca_bot import gdelt, makro, simulate, universe  # noqa: E402
from alpaca_bot.config import code_version  # noqa: E402
from alpaca_bot.engine import EngineConfig  # noqa: E402
from alpaca_bot.statistik import gruppierter_test  # noqa: E402

MARKT = "SPY"

# Dieselbe Live-Basis wie im Lernlauf (`32_lernlauf.py`): Der Live-Bot
# faehrt seit dem 30.07.2026 mit deploy_to_target und allow_topup (§G6).
LIVE_BASIS = {"deploy_to_target": True, "allow_topup": True}


def strategie_tagesrendite(jahre: float, symbole: int, kapital: float,
                           verbose: bool = True) -> pd.Series:
    """Ein Historienlauf der LIVE-Konfiguration, Tagesrendite als Reihe."""
    from alpaca_bot.shadow_daten import MARKET_SYMBOL, lade_bars

    syms = universe.load_universe(max_symbols=symbole)
    if verbose:
        print(f"  Universum : {len(syms)} Symbole, {jahre:g} Jahre")
    bars = lade_bars([*syms, MARKET_SYMBOL], jahre, verbose=verbose)
    markt = bars.xs(MARKET_SYMBOL, level="symbol")["close"].astype(float)

    cfg = EngineConfig.for_reversal(**LIVE_BASIS)
    scfg = simulate.SimConfig(initial_cash=kapital, log_to_journal=False)
    if verbose:
        print("  Historienlauf der Live-Konfiguration ...", flush=True)
    res = simulate.run(bars, engine_config=cfg, sim_config=scfg,
                       market=markt, verbose=False)

    eq = pd.Series(dict(res.equity_curve)) if isinstance(res.equity_curve, list) \
        else pd.Series(res.equity_curve)
    eq.index = pd.DatetimeIndex(pd.to_datetime(eq.index)).tz_localize(None).normalize()
    r = eq.pct_change().dropna()
    if verbose:
        print(f"     {len(r)} Handelstage, Gesamtrendite "
              f"{eq.iloc[-1]/eq.iloc[0]-1:+.1%}, {len(res.trades)} Trades")
    return r


def spy_regime(kalender: pd.DatetimeIndex, jahre: float) -> pd.Series:
    """Der HEUTIGE Regimefilter als Vergleichsmassstab: SPY ueber SMA200.

    Ohne diesen Vergleich waere jedes Ergebnis unbewertbar - die Frage
    ist nicht 'sagt der Makrowert etwas', sondern 'sagt er MEHR als das,
    was der Bot schon benutzt'.
    """
    from alpaca_bot import indicators as ind
    from alpaca_bot.shadow_daten import lade_bars

    bars = lade_bars([MARKT], jahre, verbose=False)
    if bars.empty:
        return pd.Series(dtype=float)
    spy = bars.xs(MARKT, level="symbol")["close"].astype(float)
    spy.index = pd.DatetimeIndex(spy.index).tz_localize(None).normalize()
    spy = spy[~spy.index.duplicated(keep="last")]
    ueber = (spy > ind.sma(spy, 200)).astype(float)
    return ueber.reindex(ueber.index.union(kalender)).ffill().reindex(kalender)


def zeige(name: str, tab: pd.DataFrame, beschr: str = "") -> None:
    if tab.empty:
        print(f"\n  {name}: zu wenig Daten fuer eine Bandeinteilung")
        return
    print(f"\n  {name}")
    if beschr:
        print(f"     {beschr}")
    print(tab.to_string(index=False))
    spanne = tab["mittel"].max() - tab["mittel"].min()
    print(f"     Spanne zwischen bestem und schlechtestem Band: "
          f"{spanne*100:.4f} %/Tag")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--jahre", type=float, default=8.0)
    p.add_argument("--symbole", type=int, default=800)
    p.add_argument("--kapital", type=float, default=30_000.0)
    p.add_argument("--baender", type=int, default=4)
    p.add_argument("--mit-gdelt", action="store_true",
                   help="Zusaetzlich GDELT-Nachrichtenregime pruefen")
    args = p.parse_args()

    print("=" * 78)
    print(f"  REGIME-KANDIDAT  |  {args.jahre:g} Jahre  |  Code {code_version()}")
    print("=" * 78)

    rendite = strategie_tagesrendite(args.jahre, args.symbole, args.kapital)
    if rendite.empty:
        print("  Keine Tagesrenditen - Abbruch.")
        return 1
    kalender = pd.DatetimeIndex(rendite.index)

    print("\n" + "-" * 78)
    print("  MASSSTAB: der heutige Filter (SPY ueber SMA200)")
    print("-" * 78)
    spy = spy_regime(kalender, args.jahre)
    if not spy.empty:
        for wert, etikett in [(1.0, "SPY UEBER SMA200 (Bot kauft)"),
                             (0.0, "SPY UNTER SMA200 (Bot sperrt)")]:
            g = rendite[spy.reindex(kalender) == wert]
            if len(g) < 20:
                continue
            r = gruppierter_test(
                g, pd.Series(g.index.to_period("M").astype(str), index=g.index),
                min_gruppen=6)
            print(f"     {etikett:<32} {len(g):>5} Tage  "
                  f"Mittel {g.mean()*100:>+7.4f} %/Tag  t={r.t:>+6.2f}")

    print("\n" + "-" * 78)
    print("  MAKROREGIME (revisionsfreie Reihen - siehe makro.py Modulkopf)")
    print("-" * 78)
    seit = (kalender.min() - pd.Timedelta(days=800)).date().isoformat()
    reihen = makro.lade_reihen(seit=seit)
    if reihen.empty:
        print("  Keine Makroreihen verfuegbar.")
    else:
        merkmale = makro.regime_merkmale(reihen, kalender)
        beschr = makro.beschreibung()
        for spalte in merkmale.columns:
            tab = makro.regime_auswertung(rendite, merkmale[spalte],
                                          n_baender=args.baender)
            basis = spalte.split("_")[0]
            zeige(spalte, tab, beschr.get(basis, "")[:100])

    if args.mit_gdelt:
        print("\n" + "-" * 78)
        print("  NACHRICHTENREGIME (GDELT)")
        print("-" * 78)
        roh = gdelt.marktweit(start=max(seit, gdelt.FRUEHESTER_TAG))
        if roh.empty:
            print("  Keine GDELT-Daten verfuegbar.")
        else:
            gm = gdelt.merkmale(roh, kalender)
            for spalte in gm.columns:
                tab = makro.regime_auswertung(rendite, gm[spalte],
                                              n_baender=args.baender)
                zeige(spalte, tab)

    print("\n" + "=" * 78)
    print("  WIE DAS ZU LESEN IST")
    print("=" * 78)
    print("  Ein Band mit hohem |t| heisst: In diesem Regime verhaelt sich")
    print("  die Strategie anders. Das ist NOCH KEIN Handelssignal - es")
    print("  muesste erst als Regimefilter formuliert, im Historienlauf")
    print("  gegen den heutigen SPY-Filter gemessen und danach im")
    print("  Schattenbetrieb bestaetigt werden (UMBAUPLAN Schritt 6).")
    print()
    print("  Zahl der geprueften Baender x Merkmale zaehlt als Versuche")
    print("  (§B2). Ein einzelnes auffaelliges Band unter zwanzig")
    print("  geprueften ist der Normalfall, kein Befund.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
