#!/usr/bin/env python3
"""Spekulativer Historienlauf: maximales Risiko, maximaler Umschlag.

Ein reiner Offline-Backtest auf OHLC-Tagesdaten - kein Handelsbot, keine
Flottenanmeldung, kein Versuchszaehlerplatz (BETRIEBSPLAN §4). Er beantwortet
NICHT "sollen wir das live schalten", sondern: Wie sieht die Verteilung des
Endkapitals aus, wenn man kompromisslos auf Volatilitaet, Konzentration,
Hebel und schnellen Umschlag geht - ueber viele Jahre?

Beispiele:

    # Einzellauf mit einem Preset
    python scripts/40_spekulativ.py --preset bounce_hunter --jahre 12

    # Einzelne Achsen anpassen (verfeinern / optimieren)
    python scripts/40_spekulativ.py --preset breakout_runner \\
        --hebel 3 --haltedauer 3 --stop-atr 2.0 --trail-atr 5

    # Raster ueber mehrere Achsen, Ergebnis nach spekulativ.sqlite
    python scripts/40_spekulativ.py --sweep "hebel=1,2,3 haltedauer=0,2,5 max_positionen=3,5,10"

    # Walk-Forward: traegt die historisch beste Konfig ins naechste Jahr?
    python scripts/40_spekulativ.py --sweep "hebel=1,2,3 haltedauer=0,2,5" --walk-forward

    # Exakte Kostenwirkung (echte Neulaeufe statt Naeherung)
    python scripts/40_spekulativ.py --preset max_aggression --kosten-check
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, replace

import numpy as np
import pandas as pd

from alpaca_bot import pit, spekulativ, universe
from alpaca_bot.config import RESULTS_DIR, code_version
from alpaca_bot.spekulativ_store import SpekulativStore

def _bool_arg(x: str) -> bool:
    return str(x).lower() in ("1", "true", "ja", "yes", "an", "on")


# Achsen, die im --sweep-String vorkommen duerfen, mit ihrem Typ.
SWEEP_TYPEN: dict[str, type] = {
    "max_positionen": int, "hebel": float, "haltedauer": int,
    "ausloeser_1t_pct": float, "ausloeser_ntage": int, "gap_pct": float,
    "vol_faktor": float, "stop_atr": float, "stop_pct": float,
    "ziel_atr": float, "ziel_pct": float, "trail_atr": float, "trail_pct": float,
    "fixed_fraction": float, "margin_zins_pa": float,
    "spread_bps": float, "slippage_bps": float,
    "richtung": str, "groessen_modus": str, "rangliste": str,
    "compounding": _bool_arg, "pdt_beachten": _bool_arg,
}


def parse_sweep(text: str) -> dict[str, list]:
    """"hebel=1,2,3 haltedauer=0,5" -> {"hebel": [1.0, 2.0, 3.0], ...}"""
    achsen: dict[str, list] = {}
    for stueck in text.split():
        if "=" not in stueck:
            raise SystemExit(f"--sweep: '{stueck}' ist kein achse=werte")
        name, roh = stueck.split("=", 1)
        name = name.strip()
        if name not in SWEEP_TYPEN:
            raise SystemExit(
                f"--sweep: Achse '{name}' unbekannt. Erlaubt: "
                f"{', '.join(sorted(SWEEP_TYPEN))}")
        typ = SWEEP_TYPEN[name]
        achsen[name] = [typ(w.strip()) for w in roh.split(",") if w.strip()]
    if not achsen:
        raise SystemExit("--sweep: leer")
    return achsen


def lade_bars_yfinance(symbols: list[str], jahre: float,
                       verbose: bool = True) -> pd.DataFrame:
    """OHLCV ueber yfinance, MultiIndex (symbol, timestamp), split-bereinigt.

    yfinance ist die inoffizielle Yahoo-Schnittstelle (ratelimit.QUOTAS
    'yfinance', bewusst konservativ). Fuer Tages-Bars ueber viele Jahre
    ist sie brauchbar; die Survivorship-Falle bleibt trotzdem - Yahoo
    kennt heute delistete Ticker ueberwiegend auch nicht mehr.
    """
    import yfinance as yf

    from alpaca_bot.ratelimit import RateLimiter

    limiter = RateLimiter("yfinance")
    start = (pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=int(jahre * 365))).date()
    frames = []
    schritt = 100
    for i in range(0, len(symbols), schritt):
        chunk = symbols[i:i + schritt]
        limiter.acquire(len(chunk))
        roh = yf.download(chunk, start=str(start), auto_adjust=True,
                          group_by="ticker", progress=False, threads=True)
        if roh is None or roh.empty:
            continue
        for sym in chunk:
            try:
                sub = roh[sym] if len(chunk) > 1 else roh
            except KeyError:
                continue
            sub = sub.rename(columns=str.lower)[["open", "high", "low", "close", "volume"]]
            sub = sub.dropna()
            if sub.empty:
                continue
            sub.index = pd.to_datetime(sub.index, utc=True)
            sub["symbol"] = sym
            frames.append(sub.set_index("symbol", append=True).reorder_levels([1, 0]))
        if verbose:
            print(f"      yfinance {min(i + schritt, len(symbols))}/{len(symbols)}")
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames).sort_index()
    out.index = out.index.set_names(["symbol", "timestamp"])
    return out


def symbolliste(name: str, max_symbols: int) -> list[str]:
    if name == "live":
        return universe.load_universe(max_symbols=max_symbols)
    fest = universe.BENCHMARK_SETS.get(name)
    if fest is None:
        raise SystemExit(
            f"Universum '{name}' unbekannt. 'live' oder: "
            f"{', '.join(universe.BENCHMARK_SETS)}")
    return fest[:max_symbols] if max_symbols else fest


def config_aus_args(args) -> spekulativ.SpekulativConfig:
    cfg = spekulativ.PRESETS[args.preset] if args.preset else spekulativ.SpekulativConfig()
    ueber: dict = {}
    for feld in (
        "startkapital", "max_positionen", "hebel", "groessen_modus",
        "fixed_fraction", "margin_zins_pa", "richtung", "ausloeser_1t_pct",
        "ausloeser_ntage", "gap_pct", "vol_faktor", "min_kurs",
        "min_dollar_volumen", "rangliste", "haltedauer", "stop_pct", "stop_atr",
        "ziel_pct", "ziel_atr", "trail_atr", "trail_pct", "spread_bps",
        "slippage_bps",
    ):
        wert = getattr(args, feld, None)
        if wert is not None:
            ueber[feld] = wert
    if args.kein_compounding:
        ueber["compounding"] = False
    if args.kein_pdt:
        ueber["pdt_beachten"] = False
    cfg = replace(cfg, **ueber)
    cfg.pruefe()
    return cfg


def benchmark_return(bars: pd.DataFrame, start, ende) -> float | None:
    if "SPY" not in bars.index.get_level_values("symbol"):
        return None
    spy = bars.xs("SPY", level="symbol")["close"].sort_index()
    spy = spy[(spy.index >= start) & (spy.index <= ende)]
    if len(spy) < 2:
        return None
    return float(spy.iloc[-1] / spy.iloc[0] - 1)


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--preset", choices=sorted(spekulativ.PRESETS),
                   help="Startkonfiguration; einzelne Achsen darunter ueberschreibbar")
    p.add_argument("--universe", default="live")
    p.add_argument("--max-symbols", type=int, default=800)
    p.add_argument("--jahre", type=float, default=12.0)
    p.add_argument("--quelle", choices=("alpaca", "yf"), default="alpaca",
                   help="alpaca = das Projekt-uebliche IEX-Tagesraster (gecacht); "
                        "yf = yfinance (tiefere Historie, inoffiziell)")
    p.add_argument("--no-cache", action="store_true")
    p.add_argument("--hochvola", action="store_true",
                   help="Universum auf das oberste ATR%%-Terzil eindampfen")
    p.add_argument("--split", default=None,
                   help="Nur Zeitraum ab hier auswerten (Rest ist Vorlauf)")
    p.add_argument("--notiz", default="")

    # --- Sweep / Walk-Forward ---
    p.add_argument("--sweep", default=None,
                   help='z.B. "hebel=1,2,3 haltedauer=0,2,5"')
    p.add_argument("--walk-forward", action="store_true",
                   help="Mit --sweep: waehlt je Jahr die bis dahin beste Konfig "
                        "und misst sie im naechsten, ungesehenen Jahr")
    p.add_argument("--kosten-check", action="store_true",
                   help="Einzellauf zusaetzlich bei 0 / 2x / hoher Spanne echt neu rechnen")
    p.add_argument("--min-jahr-rendite", dest="min_jahr_rendite", type=float,
                   default=None,
                   help="Konsistenzpflicht: JEDES Kalenderjahr muss mindestens "
                        "diese Rendite liefern (z.B. 0.0 = nie ein Minusjahr, "
                        "0.05 = jedes Jahr >= +5%%). Im Sweep zeigt eine zweite "
                        "Rangliste nur die Konfigs, die das schaffen; der "
                        "Walk-Forward laeuft dann nur ueber sie.")

    # --- Einzelachsen (alle optional; None = Preset-/Vorgabewert) ---
    p.add_argument("--startkapital", type=float)
    p.add_argument("--max-positionen", dest="max_positionen", type=int)
    p.add_argument("--hebel", type=float)
    p.add_argument("--groessen-modus", dest="groessen_modus",
                   choices=("gleich", "konviktion", "voll_rotation", "fixed_fraction"))
    p.add_argument("--fixed-fraction", dest="fixed_fraction", type=float)
    p.add_argument("--margin-zins-pa", dest="margin_zins_pa", type=float)
    p.add_argument("--kein-compounding", action="store_true")
    p.add_argument("--kein-pdt", action="store_true")
    p.add_argument("--richtung", choices=("momentum", "reversal"))
    p.add_argument("--ausloeser-1t-pct", dest="ausloeser_1t_pct", type=float)
    p.add_argument("--ausloeser-ntage", dest="ausloeser_ntage", type=int)
    p.add_argument("--gap-pct", dest="gap_pct", type=float)
    p.add_argument("--vol-faktor", dest="vol_faktor", type=float)
    p.add_argument("--min-kurs", dest="min_kurs", type=float)
    p.add_argument("--min-dollar-volumen", dest="min_dollar_volumen", type=float)
    p.add_argument("--rangliste", choices=("bewegung", "volumen"))
    p.add_argument("--haltedauer", type=int)
    p.add_argument("--stop-pct", dest="stop_pct", type=float)
    p.add_argument("--stop-atr", dest="stop_atr", type=float)
    p.add_argument("--ziel-pct", dest="ziel_pct", type=float)
    p.add_argument("--ziel-atr", dest="ziel_atr", type=float)
    p.add_argument("--trail-atr", dest="trail_atr", type=float)
    p.add_argument("--trail-pct", dest="trail_pct", type=float)
    p.add_argument("--spread", dest="spread_bps", type=float)
    p.add_argument("--slippage", dest="slippage_bps", type=float)
    args = p.parse_args()

    # --- Zufallsschwelle aus der Flotte (rueckwaerts kein Zaehlerbezug,
    # aber die Einordnung soll dieselbe Latte anlegen) ---
    try:
        from alpaca_bot import fleet
        schwelle = fleet.schwelle_sigma()
    except Exception:  # noqa: BLE001
        schwelle = float(np.sqrt(2 * np.log(64)) + 0.5)

    syms = symbolliste(args.universe, args.max_symbols)
    print(f"[1/4] Lade {len(syms)} Symbole + SPY, {args.jahre:g} Jahre "
          f"ueber {args.quelle} ({'Cache aus' if args.no_cache else 'Cache an'}) ...")
    ziel_syms = sorted(set(syms) | {"SPY"})
    if args.quelle == "yf":
        bars = lade_bars_yfinance(ziel_syms, args.jahre, verbose=len(syms) > 200)
    else:
        bars = universe.fetch_history(ziel_syms, years=args.jahre,
                                      verbose=len(syms) > 200,
                                      use_cache=not args.no_cache)
    if bars.empty:
        print("Keine Daten erhalten.")
        return 1
    n_sym = bars.index.get_level_values("symbol").nunique()
    print(f"      {len(bars):,} Bars, {n_sym} Symbole")

    if args.hochvola:
        tradable = bars.drop("SPY", level="symbol", errors="ignore")
        atrp = {}
        for s in tradable.index.get_level_values("symbol").unique():
            d = tradable.xs(s, level="symbol")
            if len(d) < 260:
                continue
            r = (d["high"] - d["low"]) / d["close"]
            atrp[s] = float(r.tail(500).mean())
        if atrp:
            grenze = np.percentile(list(atrp.values()), 66)
            behalten = {s for s, v in atrp.items() if v >= grenze} | {"SPY"}
            bars = bars[bars.index.get_level_values("symbol").isin(behalten)]
            n_sym = bars.index.get_level_values("symbol").nunique()
            print(f"      Hochvola-Filter: {n_sym} Symbole (oberstes ATR%%-Terzil)")

    # --- Kausalitaet der Merkmale pruefen, BEVOR gerechnet wird ---
    print("[2/4] Pruefe die Merkmalsfunktion auf Zukunftslecks ...")
    probe_cfg = spekulativ.PRESETS.get(args.preset or "breakout_runner")
    probe_sym = bars.drop("SPY", level="symbol", errors="ignore") \
        .index.get_level_values("symbol")[0]
    probe = bars.xs(probe_sym, level="symbol").sort_index()
    audit = pit.audit_feature_function(
        lambda df: spekulativ._merkmale(df, probe_cfg), probe, n_checks=5)
    print(f"      {audit}")
    if not audit.clean:
        print("      ABBRUCH: undichte Merkmale - jedes Ergebnis waere wertlos.")
        return 1

    store = SpekulativStore()
    RESULTS_DIR.joinpath("spekulativ").mkdir(parents=True, exist_ok=True)

    # ================================================================
    # A) SWEEP (optional mit Walk-Forward)
    # ================================================================
    if args.sweep:
        achsen = parse_sweep(args.sweep)
        basis = config_aus_args(args)
        konfigs = spekulativ.sweep_konfigs(basis, achsen)
        n = len(konfigs)
        mt = float(np.sqrt(2 * np.log(max(2, n))) + 0.5)
        print(f"[3/4] Sweep ueber {n} Konfigurationen "
              f"(Zufallsmaximum t ~ {mt:.2f}) ...")
        lauf_id = store.lauf_anlegen(
            code_version=code_version(), art="sweep", jahre=args.jahre,
            symbole=n_sym, universum=args.universe, quelle=args.quelle,
            n_konfigs=n, schwelle=schwelle, notiz=args.notiz)

        zeilen = []
        ergebnisse = []
        for k, (belegung, cfg) in enumerate(konfigs):
            try:
                res = spekulativ.run(bars.drop("SPY", level="symbol", errors="ignore"),
                                     cfg, start=args.split, verbose=False)
            except Exception as e:  # noqa: BLE001
                print(f"      [{k + 1}/{n}] {belegung} -> {type(e).__name__}: {e}")
                continue
            m = res.metrics()
            gt = res.gruppentest()
            bs = res.bootstrap(n=2000)
            sj = res.schlechtestes_jahr()
            n_ok, n_ges = res.jahre_ueber(args.min_jahr_rendite
                                          if args.min_jahr_rendite is not None
                                          else 0.0)
            min_jahr = sj[1] if sj else float("nan")
            konsistent = (args.min_jahr_rendite is not None
                          and n_ges > 0 and n_ok == n_ges)
            store.ergebnis_schreiben(
                lauf_id, k, belegung=belegung, config=asdict(cfg), metriken=m,
                gruppentest=gt, bootstrap=bs, n_handelstage=res.kalender_tage,
                min_jahr_rendite=(float(min_jahr) if np.isfinite(min_jahr) else None),
                jahre_positiv=n_ok, jahre_gesamt=n_ges)
            ergebnisse.append((belegung, cfg, res, m, gt, bs))
            zeilen.append({
                **belegung,
                "CAGR": m.get("cagr", float("nan")),
                "MaxDD": m.get("max_drawdown", float("nan")),
                "minJahr": min_jahr,
                "Jp": f"{n_ok}/{n_ges}",
                "Trades": m.get("n_trades", 0),
                "t_grp": (gt.t_ueberlappung if np.isfinite(gt.t_ueberlappung) else gt.t),
                "p05": bs.get("p05", float("nan")),
                "p50": bs.get("p50", float("nan")),
                "Ruin": "JA" if m.get("ruin") else "",
                "_konsistent": konsistent,
            })
            print(f"      [{k + 1}/{n}] {belegung}  CAGR {m.get('cagr', 0):+.1%}  "
                  f"MaxDD {m.get('max_drawdown', 0):.0%}  "
                  f"minJahr {min_jahr:+.0%}  t {zeilen[-1]['t_grp']:+.2f}  "
                  f"{zeilen[-1]['Ruin']}")

        tab = pd.DataFrame(zeilen).sort_values("CAGR", ascending=False)
        zeig = [c for c in tab.columns if not c.startswith("_")]
        print("\n  RANGLISTE (nach CAGR; minJahr = schlechtestes Kalenderjahr; "
              "Jp = Jahre >= Schwelle / gesamt)")
        print(tab[zeig].to_string(index=False, float_format=lambda x: f"{x:.3f}"))
        print(f"\n  {n} Konfigurationen -> die beste ist per Konstruktion die beste. "
              f"Das ist KEIN Befund (BEFUNDE §B2/§B4).")

        konsistente_idx = [i for i, z in enumerate(zeilen) if z["_konsistent"]]
        if args.min_jahr_rendite is not None:
            print(f"\n  KONSISTENZPFLICHT: jedes Kalenderjahr >= "
                  f"{args.min_jahr_rendite:+.0%}")
            if not konsistente_idx:
                print("  -> KEINE einzige Konfiguration schafft das. "
                      "Ueber alle Jahre hinweg gewinnt keine dieser Varianten "
                      "zuverlaessig.")
            else:
                ktab = tab[tab["_konsistent"]][zeig].sort_values(
                    "CAGR", ascending=False)
                print(f"  -> {len(konsistente_idx)} von {n} Konfigurationen "
                      f"erfuellen sie IN-SAMPLE:")
                print(ktab.to_string(index=False,
                                     float_format=lambda x: f"{x:.3f}"))
                print("  ACHTUNG: 'jedes Jahr positiv' rueckblickend ist bei "
                      f"{n} geprueften Konfigs auch reiner Zufallstreffer "
                      "(BEFUNDE §B4/§G45). Erst die Walk-Forward-Zeile zeigt, "
                      "ob es vorwaerts traegt.")

        if args.walk_forward:
            nur = konsistente_idx if (args.min_jahr_rendite is not None
                                      and konsistente_idx) else None
            _walk_forward(ergebnisse, bars, args, store, lauf_id, schwelle,
                          nur_idx=nur)

        store.lauf_beenden(lauf_id)
        _json_ablegen(f"sweep_{lauf_id}", {"lauf_id": lauf_id, "tabelle": zeilen})
        print(f"\n  Geschrieben: spekulativ.sqlite (lauf_id {lauf_id})")
        return 0

    # ================================================================
    # B) EINZELLAUF
    # ================================================================
    cfg = config_aus_args(args)
    print(f"[3/4] Einzellauf: {args.preset or 'vorgabe'} "
          f"{json.dumps({k: v for k, v in asdict(cfg).items() if k in SWEEP_TYPEN})}")
    tradable = bars.drop("SPY", level="symbol", errors="ignore")
    res = spekulativ.run(tradable, cfg, start=args.split, verbose=True)

    bench = benchmark_return(bars, res.equity_curve.index[0], res.equity_curve.index[-1])
    print()
    print(spekulativ.auswerten(
        res, benchmark_return=bench, n_konfigurationen=1, schwelle=schwelle,
        jahre=args.jahre, min_jahr_schwelle=args.min_jahr_rendite,
        segment="large_cap" if args.universe != "live" else "small_cap"))

    if args.kosten_check:
        print("\n  KOSTEN-CHECK - echte Neulaeufe:")
        for spread, slip in ((0.0, 0.0), (10.0, 6.0), (25.0, 10.0)):
            r2 = spekulativ.run(tradable, replace(cfg, spread_bps=spread,
                                                  slippage_bps=slip),
                                start=args.split, verbose=False)
            m2 = r2.metrics()
            print(f"    {spread:>4.0f}+{slip:<3.0f} bps  ->  CAGR {m2.get('cagr', 0):+.2%}  "
                  f"Endkapital ${r2.equity_curve.iloc[-1]:,.0f}  "
                  f"{'RUIN' if m2.get('ruin') else ''}")

    lauf_id = store.lauf_anlegen(
        code_version=code_version(), art="einzeln", jahre=args.jahre,
        symbole=n_sym, universum=args.universe, quelle=args.quelle,
        n_konfigs=1, schwelle=schwelle, notiz=args.notiz)
    _sj = res.schlechtestes_jahr()
    _nok, _nges = res.jahre_ueber(args.min_jahr_rendite
                                  if args.min_jahr_rendite is not None else 0.0)
    store.ergebnis_schreiben(
        lauf_id, 0, belegung={"preset": args.preset or "vorgabe"},
        config=asdict(cfg), metriken=res.metrics(), gruppentest=res.gruppentest(),
        bootstrap=res.bootstrap(), n_handelstage=res.kalender_tage,
        min_jahr_rendite=(float(_sj[1]) if _sj else None),
        jahre_positiv=_nok, jahre_gesamt=_nges)
    store.lauf_beenden(lauf_id)
    _json_ablegen(f"einzeln_{lauf_id}", {
        "lauf_id": lauf_id, "config": asdict(cfg), "metriken": res.metrics(),
        "trades": len(res.trades),
    })
    print(f"\n  Geschrieben: spekulativ.sqlite (lauf_id {lauf_id})")
    print("[4/4] fertig.")
    return 0


def _walk_forward(ergebnisse, bars, args, store, lauf_id, schwelle,
                  *, nur_idx=None) -> None:
    """Je Kalenderjahr die bis dahin beste Konfig waehlen, im naechsten
    (ungesehenen) Jahr messen. Traegt die Auswahl vorwaerts?

    `nur_idx`: wenn gesetzt, kommen nur diese Konfig-Indizes in den Topf -
    so laeuft der Walk-Forward ausschliesslich ueber die Varianten, die
    die Konsistenzpflicht in-sample erfuellt haben. Genau das ist der
    ehrliche Test fuer "das goldene Einstellungsding": nicht ob es
    rueckblickend jedes Jahr lief, sondern ob eine so ausgewaehlte
    Konfig auch im naechsten, ungesehenen Jahr traegt.
    """
    from alpaca_bot.statistik import gruppierter_test

    if nur_idx is not None:
        ergebnisse = [e for i, e in enumerate(ergebnisse) if i in set(nur_idx)]
        print(f"\n  (Walk-Forward-Topf auf {len(ergebnisse)} konsistente "
              f"Konfigs eingeschraenkt)")

    # Jahresrenditen je Konfig aus der Equity-Kurve.
    per_konfig: dict[int, pd.Series] = {}
    labels: dict[int, dict] = {}
    for idx, (belegung, cfg, res, *_rest) in enumerate(ergebnisse):
        eq = res.equity_curve
        if eq.empty:
            continue
        jr = {}
        for j in sorted({ts.year for ts in eq.index}):
            e = eq[eq.index.year == j]
            if len(e) >= 2:
                jr[j] = float(e.iloc[-1] / e.iloc[0] - 1)
        per_konfig[idx] = pd.Series(jr)
        labels[idx] = belegung

    if not per_konfig:
        return
    alle_jahre = sorted(set().union(*[set(s.index) for s in per_konfig.values()]))
    if len(alle_jahre) < 4:
        print("\n  Walk-Forward: zu wenige volle Jahre.")
        return

    print("\n  WALK-FORWARD  (Auswahl auf Jahr 1..k, Messung in k+1)")
    diffs = []
    for pos in range(2, len(alle_jahre) - 1):
        train = alle_jahre[:pos + 1]
        test_jahr = alle_jahre[pos + 1]
        # beste Konfig: hoechste mittlere Jahresrendite ueber die Trainingsjahre
        bewert = {
            idx: np.mean([s.get(j, np.nan) for j in train])
            for idx, s in per_konfig.items()
            if np.isfinite(np.nanmean([s.get(j, np.nan) for j in train]))
        }
        if not bewert:
            continue
        best = max(bewert, key=bewert.get)
        r_best = per_konfig[best].get(test_jahr, np.nan)
        r_basis = float(np.nanmean([per_konfig[idx].get(test_jahr, np.nan)
                                    for idx in per_konfig]))
        if not np.isfinite(r_best):
            continue
        diffs.append(r_best - r_basis)
        store.walkforward_zeile_schreiben(
            lauf_id, test_jahr, gewaehlt=labels[best],
            rendite_gewaehlt=r_best, rendite_basis=r_basis)
        print(f"    {test_jahr}: gewaehlt {labels[best]}  "
              f"-> {r_best:+.1%}  (Schnitt aller {r_basis:+.1%}, "
              f"Diff {r_best - r_basis:+.1%})")

    if len(diffs) >= 3:
        d = pd.Series(diffs)
        t = float(d.mean() / (d.std(ddof=1) / np.sqrt(len(d)))) if d.std(ddof=1) else float("nan")
        pos = int((d > 0).sum())
        print(f"    -> {pos}/{len(d)} Jahre mit Vorsprung, mittlere Diff "
              f"{d.mean():+.1%}, t = {t:+.2f} (Schwelle {schwelle:.2f})")
        print("    Rueckwaerts ist kein Vorwaertstest (BETRIEBSPLAN §4). "
              "Das darf verwerfen, nicht abnehmen.")


def _json_ablegen(name: str, obj: dict) -> None:
    pfad = RESULTS_DIR / "spekulativ" / f"{name}.json"
    pfad.write_text(json.dumps(obj, indent=2, default=str), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
