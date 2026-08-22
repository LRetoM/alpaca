#!/usr/bin/env python3
"""Schritt 10: Historien-Simulation - exakt der Ablauf des spaeteren Live-Betriebs.

Spielt die Vergangenheit Tag fuer Tag durch und ruft dabei dieselbe
`Engine.decide()` auf, die spaeter im Paper- und Live-Handel entscheidet.
Kein vektorisierter Backtest, kein zweiter Strategie-Code.

Enthalten: Ausfuehrung erst am Folgetag, Spread und Gebuehren, PDT-Regel,
Kursluecken bei Stops, lueckenloses Protokoll.

WOFUER: Der Schattenbetrieb misst vorwaerts und braucht dafuer Wochen
(BETRIEBSPLAN §3.3). Dieses Skript beantwortet dieselbe Frage rueckwaerts
in Minuten. Es kann eine Idee damit billig VERWERFEN. Es kann sie nicht
bestaetigen - dafuer bleibt der Schattenbetrieb zustaendig, siehe
`docs/BEFUNDE.md` §G11 und `docs/schattenbetrieb.md`.

Damit das ueberhaupt dieselbe Frage ist, muss die Simulation dieselbe
Strategie fahren wie der Live-Bot. Bis zum 21.08.2026 tat sie das nicht
(§G11): sie lief mit `EngineConfig()` statt `EngineConfig.for_reversal()`,
ohne Marktfilter und auf 110 fest verdrahteten Symbolen statt den 1.200,
die der Bot handelt.

    python scripts/10_simulate.py                      # Live-Strategie, Live-Universum
    python scripts/10_simulate.py --max-symbols 200    # schneller Probelauf
    python scripts/10_simulate.py --universe broad_liquid   # feste Vergleichsliste
    python scripts/10_simulate.py --insider            # mit SEC-Form-4-Daten (langsam)
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from dataclasses import asdict

import numpy as np
import pandas as pd

from alpaca_bot import compliance, data, pit, signals, simulate, universe
from alpaca_bot.config import RESULTS_DIR, code_version
from alpaca_bot.engine import EngineConfig


def live_engine_config(**ueberschreibungen) -> EngineConfig:
    """Die Konfiguration, die der Live-Bot TATSAECHLICH faehrt.

    `EngineConfig.for_reversal()` allein genuegt nicht. `12_daemon.py`
    startet zusaetzlich mit `deploy_to_target=True` und
    `allow_topup=True` (Schalter `--kein-voll-investiert` /
    `--kein-nachkauf`, beide `default=True`).

    Genau diese zwei Felder haben am 30.07.2026 schon einmal eine
    Referenz still zerstoert: `B00_basis` blieb bei False/False, waehrend
    der Live-Bot auf True/True umgestellt wurde, und acht Flottenbots
    verglichen sich zwei Wochen lang gegen eine falsche Basis
    (`docs/BEFUNDE.md` §G6). Ein Lauf ohne sie ist nicht der Bot: ohne
    `deploy_to_target` bleibt Kapital unbeschaeftigt liegen.

    Gepinnt in
    tests/test_konsistenz.py::test_konfiguration_ist_feldweise_die_live_konfiguration -
    dieser Test liest die Voreinstellungen aus `12_daemon.py` und
    vergleicht Feld fuer Feld. Aendert sich der Live-Bot, faellt er.
    """
    return EngineConfig.for_reversal(
        deploy_to_target=True, allow_topup=True, **ueberschreibungen
    )


def gruppierte_pruefung(trades: pd.DataFrame) -> str:
    """Die beiden Kernfragen, gruppiert nach Handelstag gerechnet.

    **Warum das hier stehen muss.** Direkt darueber druckt das Skript die
    Score-Tabelle - jeder Trade einzeln gezaehlt. Am 21.08.2026 sah die
    aus wie ein dramatischer Befund: die 2.302 Trades mit den HOECHSTEN
    Scores hatten eine negative Durchschnittsrendite, die 169 mit den
    niedrigsten eine positive. Der Score schien verkehrt herum zu
    sortieren.

    Gruppiert nach Handelstag: **t = -0,09**. Nichts davon haelt. Trades
    desselben Tages sind nicht unabhaengig (CLAUDE.md, `docs/BEFUNDE.md`
    §B1) - an einem Abverkaufstag faellt alles gemeinsam, und die Tabelle
    zaehlt das als hunderte getrennte Belege.

    Der alte Schlusssatz unter der Tabelle lautete: "Wenn hoehere Scores
    NICHT bessere Ergebnisse liefern, misst der Score nichts
    Verwertbares." Das Werkzeug lud damit zu genau dem Fehlschluss ein,
    den die wichtigste Regel des Projekts verbietet.
    """
    from alpaca_bot import fleet, statistik

    t = trades.copy()
    t["tag"] = pd.to_datetime(t["entry_date"]).dt.normalize()
    schwelle = fleet.schwelle_sigma()
    L = ["", "  GRUPPIERTER TEST (massgeblich, Stichprobe = Handelstage)",
         f"  Schwelle fleet.schwelle_sigma() = {schwelle}"]

    def zeile(name: str, r) -> str:
        urteil = "BEFUND" if abs(r.t) > schwelle else "kein Befund"
        return (f"    {name:<28} Mittel {r.mittel:+.4%}  t {r.t:>6.2f}  "
                f"(naiv {r.t_naiv:>6.2f})  Tage {r.n_gruppen:>4}  [{urteil}]")

    L.append(zeile("Rendite je Trade", statistik.gruppierter_test(t["return_pct"], t["tag"])))

    # Je Tag: obere gegen untere Score-Haelfte. Der Vergleich passiert
    # INNERHALB eines Tages - damit faellt die gemeinsame Marktbewegung
    # heraus, die die naive Tabelle als Signal missdeutet.
    paare = []
    for tag, g in t.groupby("tag"):
        if len(g) < 4:
            continue
        med = g["entry_score"].median()
        hoch, tief = g[g["entry_score"] > med], g[g["entry_score"] <= med]
        if len(hoch) and len(tief):
            paare.append({"tag": tag,
                          "d": hoch["return_pct"].mean() - tief["return_pct"].mean()})
    if paare:
        p = pd.DataFrame(paare)
        L.append(zeile("Score hoch minus tief", statistik.gruppierter_test(p["d"], p["tag"])))
    else:
        L.append("    Score hoch minus tief        zu wenige Tage mit >= 4 Trades")

    L += ["", "  'kein Befund' heisst NICHT 'kein Effekt' - nur, dass diese",
          "  Stichprobe ihn nicht zeigt. Und ein Befund aus der Historie",
          "  darf verwerfen, nicht abnehmen (BETRIEBSPLAN §4)."]
    return "\n".join(L)


def yearly_breakdown(result, benchmark: pd.Series | None) -> pd.DataFrame:
    """Jahr fuer Jahr - haelt die Strategie ueber die Zeit, oder kam alles
    aus einem einzigen guten Jahr?"""
    eq = result.equity_curve
    rows = []
    for year, grp in eq.groupby(eq.index.year):
        if len(grp) < 2:
            continue
        r = float(grp.iloc[-1] / grp.iloc[0] - 1)
        row = {"Jahr": year, "Strategie": r}
        if benchmark is not None:
            b = benchmark.reindex(grp.index).ffill().dropna()
            if len(b) > 1:
                row["Buy&Hold SPY"] = float(b.iloc[-1] / b.iloc[0] - 1)
        rows.append(row)
    df = pd.DataFrame(rows)
    if "Buy&Hold SPY" in df.columns:
        df["Differenz"] = df["Strategie"] - df["Buy&Hold SPY"]
    return df


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--universe", default="live",
                   help="'live' = das gemessene Universum aus universum.csv "
                        "(so handelt der Bot), sonst ein Name aus BENCHMARK_SETS")
    # 1200 ist KEINE freie Wahl: exakt so viele Symbole handelt der
    # Live-Bot (`scripts/12_daemon.py --max-symbols`). Eine Simulation
    # ueber alle 2.168 wuerde eine andere Auswahl handeln als der Bot -
    # und `load_universe` sortiert nach Umsatz, die zusaetzlichen 968
    # waeren durchweg die duennsten Werte. Gepinnt in
    # tests/test_konsistenz.py::test_simuliert_das_live_universum.
    p.add_argument("--max-symbols", type=int, default=1200,
                   help="Nur die N umsatzstaerksten (Standard: wie der Live-Bot)")
    p.add_argument("--years", type=float, default=9.0)
    p.add_argument("--cash", type=float, default=30_000)
    p.add_argument("--positions", type=int, default=None,
                   help="Standard: der Live-Wert aus EngineConfig.for_reversal()")
    p.add_argument("--min-score", type=float, default=None,
                   help="Standard: der Live-Wert aus EngineConfig.for_reversal()")
    p.add_argument("--spread", type=float, default=5.0)
    p.add_argument("--slippage", type=float, default=3.0)
    p.add_argument("--no-cache", action="store_true",
                   help="Bars frisch laden statt aus dem Datei-Cache")
    p.add_argument("--insider", action="store_true",
                   help="SEC-Form-4-Daten einbeziehen (dauert beim ersten Lauf)")
    p.add_argument("--split", default="2023-01-01",
                   help="Ab hier gilt der Zeitraum als unberuehrte Validierung")
    args = p.parse_args()

    if args.universe == "live":
        try:
            syms = universe.load_universe(max_symbols=args.max_symbols)
        except FileNotFoundError as e:
            print(e)
            return 1
    else:
        syms = universe.BENCHMARK_SETS.get(args.universe)
        if syms is None:
            print(f"Unbekanntes Universum. Verfuegbar: live, "
                  f"{', '.join(universe.BENCHMARK_SETS)}")
            return 1
        if args.max_symbols:
            syms = syms[:args.max_symbols]

    print(compliance.preflight(len(syms) + 1, args.years, "1D"))
    print()

    # --- 1. Daten ---
    # Batchweise: ein einzelner Request ueber Hunderte Symbole und Jahre
    # laeuft in Zeitueberschreitungen. Der Cache macht den zweiten Lauf
    # ueber dasselbe Universum zur Sache von Sekunden.
    use_cache = not args.no_cache
    print(f"[1/5] Lade {len(syms)} Symbole + SPY, {args.years:g} Jahre "
          f"({'Cache an' if use_cache else 'Cache aus'}) ...")
    bars = universe.fetch_history(
        sorted(set(syms) | {"SPY"}), years=args.years,
        verbose=len(syms) > 300, use_cache=use_cache,
    )
    if bars.empty:
        print("Keine Daten erhalten.")
        return 1
    n_sym = bars.index.get_level_values("symbol").nunique()
    print(f"      {len(bars):,} Bars, {n_sym} Symbole")
    print()
    # Segment ehrlich waehlen. Das Live-Universum reicht bis weit in die
    # Nebenwerte; mit "large_cap" (2 % Delisting/Jahr) gerechnet saehe der
    # Bias dort um ein Vielfaches kleiner aus, als er ist.
    segment = "large_cap" if args.universe != "live" else "small_cap"
    print(universe.survivorship_warning(n_sym, args.years, segment))

    spy = data.ohlcv(bars, "SPY")["close"] if "SPY" in bars.index.get_level_values("symbol") else None
    tradable = bars.drop("SPY", level="symbol", errors="ignore")

    # --- 2. Kausalitaet pruefen, BEVOR simuliert wird ---
    print(f"\n[2/5] Pruefe die Signalfunktion auf Zukunftslecks ...")
    # Nicht syms[0]: bei grossen Universen liefert nicht jedes angefragte
    # Symbol Daten, und ein KeyError hier haette den Lauf nach dem teuren
    # Ladeschritt abgebrochen.
    probe = data.ohlcv(bars, tradable.index.get_level_values("symbol")[0])
    audit = pit.audit_feature_function(signals.build_signal_frame, probe, n_checks=5)
    print(f"      {audit}")
    if not audit.clean:
        print("      ABBRUCH: Undichte Signale - jedes Ergebnis waere wertlos.")
        return 1

    # --- 3. Optional: Insiderdaten ---
    insider = {}
    if args.insider:
        from alpaca_bot import edgar

        print(f"\n[3/5] Lade SEC-Form-4-Daten fuer {len(syms)} Symbole ...")
        print("      (erster Lauf dauert, danach aus dem Cache)")
        for i, sym in enumerate(syms, 1):
            try:
                df_sym = data.ohlcv(bars, sym)
                trades = edgar.insider_trades(sym, since="2016-01-01", max_filings=120)
                if not trades.empty:
                    insider[sym] = edgar.insider_features(trades, df_sym.index, sym)
                if i % 10 == 0:
                    print(f"      {i}/{len(syms)} ...")
            except Exception as e:  # noqa: BLE001
                print(f"      {sym}: {type(e).__name__}")
        with_buys = sum(
            1 for f in insider.values()
            if f.get("insider_buyers_90d", pd.Series([0])).max() > 0
        )
        print(f"      {len(insider)} Symbole mit Daten, davon {with_buys} "
              f"mit echten Marktkaeufen")
    else:
        print(f"\n[3/5] Insiderdaten uebersprungen (--insider zum Aktivieren)")

    # --- 4. Simulation ---
    # Mit dem blanken `EngineConfig()` lief hier bis zum 21.08.2026 eine
    # voellig andere Strategie: 60 statt 5 Tage Haltedauer, Ziel 6.0
    # statt 2.0 ATR, Nachziehen ab 3.0 ATR statt gar nicht. Acht von zehn
    # Feldern wichen ab, die mittlere Haltedauer im Ergebnis 17,3 gegen 5
    # Tage live. Was dabei herauskam, sagte ueber den laufenden Bot
    # nichts aus. `live_engine_config()` ist der Bot, feldweise gepinnt.
    ueberschreibungen = {}
    if args.positions is not None:
        ueberschreibungen["max_positions"] = args.positions
    if args.min_score is not None:
        ueberschreibungen["min_score"] = args.min_score
    ecfg = live_engine_config(**ueberschreibungen)
    scfg = simulate.SimConfig(
        initial_cash=args.cash,
        spread_bps=args.spread,
        slippage_bps=args.slippage,
    )
    print(f"\n[4/5] Simuliere Tag fuer Tag ({ecfg.strategy}, max. "
          f"{ecfg.max_positions} Positionen, Score-Schwelle {ecfg.min_score}, "
          f"Haltedauer {ecfg.max_hold_days} Tage) ...")
    if spy is None:
        print("      WARNUNG: kein SPY - der Marktfilter der Live-Strategie")
        print("      (nur kaufen ueber dem 200-Tage-Schnitt) entfaellt still.")
    # `market` ist nicht optional-fuer-Komfort: ohne SPY faellt
    # `ReversalWeights.market_regime_filter` ersatzlos aus, und die
    # Simulation kauft in Crashs hinein, die der Live-Bot aussitzt.
    result = simulate.run(tradable, ecfg, scfg, insider=insider,
                          market=spy, verbose=True)

    # --- 5. Auswertung ---
    print()
    print(result.summary())

    if spy is not None:
        eq = result.equity_curve
        b = spy.reindex(eq.index).ffill().dropna()
        if len(b) > 1:
            bh = float(b.iloc[-1] / b.iloc[0] - 1)
            print()
            print(f"  Buy & Hold SPY        : {bh:>13.2%}")
            print(f"  Differenz             : {result.total_return - bh:>13.2%}")

    print("\n" + "=" * 66)
    print("  JAHR FUER JAHR")
    print("=" * 66)
    yb = yearly_breakdown(result, spy)
    if not yb.empty:
        fmt = yb.copy()
        for c in fmt.columns:
            if c != "Jahr":
                fmt[c] = fmt[c].map(lambda v: f"{v:>8.2%}")
        print(fmt.to_string(index=False))

    # --- Unberuehrter Zeitraum ---
    split = pd.Timestamp(args.split, tz="UTC")
    eq = result.equity_curve
    dev, val = eq[eq.index < split], eq[eq.index >= split]
    print("\n" + "=" * 66)
    print("  ENTWICKLUNG GEGEN VALIDIERUNG")
    print("=" * 66)
    if len(dev) > 1 and len(val) > 1:
        r_dev = float(dev.iloc[-1] / dev.iloc[0] - 1)
        r_val = float(val.iloc[-1] / val.iloc[0] - 1)
        print(f"  bis {args.split}  : {r_dev:>8.2%}  ({len(dev)} Tage)")
        print(f"  ab  {args.split}  : {r_val:>8.2%}  ({len(val)} Tage)")
        print()
        if r_dev > 0 and r_val < 0:
            print("  WARNUNG: Funktioniert nur im Entwicklungszeitraum. Das ist")
            print("  das klassische Muster einer ueberangepassten Strategie.")
        elif r_val > 0 and r_dev > 0:
            print("  Beide Zeitraeume positiv - erstes gutes Zeichen.")
        else:
            print("  Kein tragfaehiges Ergebnis in beiden Zeitraeumen.")

    # --- Ausstiegsgruende und Signalqualitaet ---
    if not result.trades.empty:
        t = result.trades
        print("\n" + "=" * 66)
        print("  WORAN DIE TRADES ENDETEN")
        print("=" * 66)
        by_reason = t.groupby("exit_reason").agg(
            n=("return_pct", "size"),
            mittel=("return_pct", "mean"),
            summe_pnl=("net_pnl", "sum"),
        ).sort_values("n", ascending=False)
        print(by_reason.round(4).to_string())

        print("\n  Score beim Einstieg vs. Ergebnis:")
        t2 = t.copy()
        t2["score_gruppe"] = pd.cut(t2["entry_score"], bins=4)
        print(t2.groupby("score_gruppe", observed=True).agg(
            n=("return_pct", "size"), mittel=("return_pct", "mean")
        ).round(4).to_string())
        print("  Diese Tabelle ist NICHT der Befund - sie zaehlt jeden Trade")
        print("  einzeln. Massgeblich ist der gruppierte Test darunter.")
        print(gruppierte_pruefung(t))

    out = RESULTS_DIR / "simulation"
    out.mkdir(exist_ok=True)
    result.equity_curve.to_csv(out / "kapitalkurve.csv")
    result.trades.to_csv(out / "trades.csv", index=False)

    # Ohne diese Datei ist eine trades.csv wertlos: die alte enthielt 821
    # Trades und verriet mit keinem Feld, dass sie aus einer anderen
    # Strategie stammte als der laufende Bot. Ein Ergebnis ohne seine
    # Konfiguration ist keine Messung, sondern eine Zahl.
    lauf = {
        "zeitpunkt": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "code_version": code_version(),
        "universum": args.universe,
        "n_symbole_angefragt": len(syms),
        "n_symbole_mit_daten": n_sym,
        "jahre": args.years,
        "marktfilter_aktiv": spy is not None,
        "nachrichtenfaktor_aktiv": False,
        "insider_aktiv": bool(insider),
        "engine_config": asdict(ecfg),
        "sim_config": {"initial_cash": scfg.initial_cash,
                       "spread_bps": scfg.spread_bps,
                       "slippage_bps": scfg.slippage_bps,
                       "warmup_bars": scfg.warmup_bars},
        "ergebnis": {"gesamtrendite": result.total_return,
                     "n_trades": int(len(result.trades)),
                     "mittlere_haltedauer": (float(result.trades["bars_held"].mean())
                                             if not result.trades.empty else None)},
    }
    (out / "lauf.json").write_text(
        json.dumps(lauf, indent=2, default=str), encoding="utf-8")
    print(f"\n  Ergebnisse gespeichert: {out}")
    print(f"  Konfiguration des Laufs: {out / 'lauf.json'}")
    print("\n  Der Nachrichtenfaktor (ReversalWeights.news, Gewicht 0,10)")
    print("  fehlt hier bauartbedingt - `simulate.run` reicht keine")
    print("  Artikel durch. Live ist er aktiv. Bekannte Abweichung.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
