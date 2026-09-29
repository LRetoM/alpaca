#!/usr/bin/env python3
"""Schritt 34: Insider-Cluster (SEC EDGAR Form 4) durch dieselbe Pruefkette.

**Warum dieser Kandidat anders ist als die bisherigen 32** (18 aus
`kandidaten.py` + 14 Achsen aus dem Lernlauf, alle 0 bestanden,
`docs/BEFUNDE.md` §C/§B6/§G33): Er kommt NICHT aus einer weiteren
Ableitung von Kurs/Volumen, sondern aus SEC-EDGAR-Form-4-Meldungen -
echtem Insiderverhalten, zeitpunktgenau (Einreichung binnen 2 Werktagen
Pflicht), ohne Survivorship-Luecke (auch untergegangene Firmen bleiben im
Archiv). `edgar.py` war fertig gebaut, aber nie durch die Pruefkette
gelaufen.

**Dieselbe Pruefkette wie beim PEAD-Test (Schritt 19) und den 18
Kandidaten (Schritt 24):**

    1. Querschnitts-IC je Tag, t-Wert ueber die MONATE (nicht Einzelwerte)
    2. Jahresstabilitaet - Vorzeichenwechsel disqualifiziert
    3. Eigenstaendigkeit gegen die bestehenden Umkehr-Faktoren
    4. Lookahead-Pruefung (Merkmale zaehlen strikt ab `filing_date`, siehe
       `edgar.insider_features`)

**Laufzeit ist die reale Grenze, nicht Rechenleistung.** SEC EDGAR
erlaubt 10 Requests/Sekunde, wir fahren 8/s (`ratelimit.QUOTAS`). Jede
Form-4-Einreichung kostet 2 Requests. Ein Symbol mit 150 Einreichungen
ueber den Zeitraum kostet daher ~300 Requests = ~40 Sekunden - bei
Hunderten Symbolen laeuft das schnell auf Stunden hinaus. Der
Plattencache (`CACHE_DIR/edgar`) macht Wiederholungslaeufe praktisch
kostenlos; der erste Lauf ueber ein neues Symbol kostet immer.

**Deshalb zweistufig:**

    python scripts/34_edgar_kandidat.py --symbole 40   # Zeitmessung, KEIN Befund
    python scripts/34_edgar_kandidat.py --symbole 300  # der eigentliche Test

Ein kleiner Lauf dient laut `docs/BEFUNDE.md` §B4 AUSSCHLIESSLICH dem
Testen der Mechanik und der Zeitschaetzung - PEAD sah auf 60 Symbolen
wie der beste Faktor des Projekts aus und brach auf 800 zusammen. Dieses
Skript druckt das bei kleinem `--symbole` auch explizit aus.
"""

from __future__ import annotations

import argparse
import pickle
import sys
import time
from importlib import import_module
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from alpaca_bot import datasources, edgar, universe  # noqa: E402
from alpaca_bot.config import DATA_DIR  # noqa: E402
from alpaca_bot.earnings import eigenstaendigkeit  # noqa: E402

CHECKPOINT = DATA_DIR / "edgar_kandidat_checkpoint.pkl"
"""Zwischenstand des laufenden Kandidatentests. Die teure Ressource ist
der EDGAR-Plattencache (CACHE_DIR/edgar) - der macht jeden Neustart nach
einem Absturz ohnehin billig, weil bereits abgerufene Symbole aus dem
Cache kommen (kein Netzwerk, keine Drosselung). Dieser Checkpoint ist
zusaetzlich dazu da, WAEHREND eines mehrtaegigen Laufs einen
Zwischenstand ansehen zu koennen, ohne das Ende abzuwarten."""

sys.path.insert(0, str(Path(__file__).resolve().parent))
_k24 = import_module("24_kandidaten_test")
bewerte = _k24.bewerte
vorwaertsrenditen = _k24.vorwaertsrenditen

MARKT = "SPY"
MECHANIK_GRENZE = 100
"""Unter dieser Symbolzahl ist ein Lauf ausschliesslich eine Zeitmessung,
kein Befund - siehe §B4."""


def baue_edgar_panels(bars: pd.DataFrame, symbole: list[str], since: str,
                      windows: tuple[int, ...] = (30, 90),
                      max_filings: int | None = None,
                      checkpoint_every: int = 50,
                      verbose: bool = True) -> dict[str, pd.DataFrame]:
    """Insider-Merkmale je Symbol, auf das Kursraster projiziert.

    Ein EDGAR-Ausfall (Netzfehler, Symbol ohne CIK, kein Formular-4)
    darf den ganzen Lauf nicht kippen - einzelne Symbole werden
    uebersprungen, gezaehlt, aber nicht als harter Fehler behandelt.

    `max_filings` begrenzt JE SYMBOL die Zahl der geladenen Form-4-
    Einreichungen (an `edgar.insider_trades` durchgereicht, dort schon
    vorgesehen). Ohne Grenze kann ein einzelner Grosskonzern mit
    hunderten meldepflichtigen Personen den ganzen Lauf dominieren -
    genau das ist am 25.08.2026 im ersten Testlauf passiert (ein Symbol
    zog ueber 750 Einreichungen, mehrere Minuten fuer EIN Symbol).

    **Fortschritt wird JE SYMBOL gedruckt, nicht gebuendelt** - bei
    kleinen Testlaeufen (< 10 Symbole) kam sonst bis zum Ende gar keine
    Zeile, weil die alte Fassung nur alle 10 Symbole druckte.
    """
    gesammelt: dict[str, dict[str, pd.Series]] = {}
    n_ok = n_fehler = n_leer = n_zu_viele = 0
    start = time.monotonic()
    kandidaten_symbole = [s for s in symbole if s != MARKT]
    gesamt = len(kandidaten_symbole)

    for i, sym in enumerate(kandidaten_symbole, 1):
        t0 = time.monotonic()
        if verbose:
            print(f"      [{i}/{gesamt}  {i/gesamt:.0%}] {sym} ...",
                  end="", flush=True)
        try:
            df = bars.xs(sym, level="symbol").sort_index()
        except KeyError:
            if verbose:
                print(" keine Kursdaten, uebersprungen")
            continue
        if len(df) < 300:
            if verbose:
                print(" zu wenig Kurshistorie, uebersprungen")
            continue
        idx = pd.DatetimeIndex(df.index).tz_localize(None).normalize()
        idx = idx[~idx.duplicated(keep="last")]

        try:
            trades = edgar.insider_trades(sym, since=since, max_filings=max_filings)
        except edgar.ZuVieleMeldungen:
            # AUSSCHLIESSEN, nicht abschneiden (§G41). Ein halbes Panel ist
            # schlimmer als kein Panel: Es sieht vollstaendig aus und ist
            # systematisch in den frueheren Jahren leer.
            n_zu_viele += 1
            if verbose:
                print(" zu viele Meldungen, AUSGESCHLOSSEN")
            continue
        except edgar.EdgarError:
            raise  # SEC_USER_AGENT fehlt o.ae. - das darf den Lauf stoppen
        except Exception as e:  # noqa: BLE001 - Netz-/Parsingfehler einzelner Symbole
            n_fehler += 1
            if verbose:
                print(f" FEHLER ({type(e).__name__}), uebersprungen")
            continue

        buys = edgar.open_market_buys(trades)
        if buys.empty:
            n_leer += 1
            # Trotzdem aufnehmen: ein Symbol OHNE Insiderkaeufe ist eine
            # gueltige Beobachtung (Score 0), kein fehlender Wert - sonst
            # waere die Stichprobe auf die "spannenden" Faelle verzerrt.

        feats = edgar.insider_features(trades, idx.tz_localize("UTC"), sym, windows=windows)
        score = edgar.cluster_score(feats, window=windows[-1])
        score.index = idx

        gesammelt.setdefault("insider_cluster_score", {})[sym] = score
        for w in windows:
            spalte = f"insider_buyers_{w}d"
            s = feats[spalte].copy()
            s.index = idx
            gesammelt.setdefault(spalte, {})[sym] = s
        n_ok += 1

        if verbose:
            dt_sym = time.monotonic() - t0
            takt = (time.monotonic() - start) / i
            rest = takt * (gesamt - i)
            n_filings = len(trades)
            n_kaeufe = len(buys)
            print(f" {dt_sym:.1f}s  ({n_filings} Meldungen, {n_kaeufe} echte Kaeufe)  "
                  f"|  Schnitt {takt:.1f}s/Symbol  Rest ~{rest/60:.1f} Min", flush=True)

        if checkpoint_every and i % checkpoint_every == 0:
            CHECKPOINT.parent.mkdir(parents=True, exist_ok=True)
            with open(CHECKPOINT, "wb") as f:
                pickle.dump({"i": i, "gesamt": gesamt, "n_ok": n_ok,
                            "n_fehler": n_fehler, "n_leer": n_leer,
                            "n_zu_viele": n_zu_viele,
                            "gesammelt": gesammelt}, f)
            if verbose:
                print(f"      [Zwischenstand gespeichert: {CHECKPOINT}]")

    dauer = time.monotonic() - start
    if verbose:
        print(f"\n  {n_ok} Symbole verarbeitet in {dauer/60:.1f} Minuten "
              f"({dauer/max(n_ok,1):.1f}s/Symbol im Schnitt)")
        anteil = n_zu_viele / max(gesamt, 1)
        print(f"  {n_zu_viele} Symbole ({anteil:.0%}) wegen zu vieler "
              f"Meldungen AUSGESCHLOSSEN, {n_leer} ohne Insiderkaeufe")
        if anteil > 0.25:
            print()
            print("  WARNUNG: ueber ein Viertel des Universums fehlt. Das ist")
            print("  keine Zufallsstichprobe - ausgeschlossen werden die")
            print("  Symbole mit den MEISTEN Insidern, also tendenziell die")
            print("  groesseren Firmen. Vor der Auswertung --max-filings")
            print("  anheben oder --since verkuerzen (§G41).")
    return {k: pd.DataFrame(v) for k, v in gesammelt.items()}


def _pruefe_fenster(jahre: float, since: str) -> None:
    """Kursfenster und Meldungsfenster muessen zusammenpassen (§G41).

    **Warum das eine harte Pruefung ist und keine Warnung.** Die
    Insider-Merkmale existieren erst ab `--since`. Reicht das Kursraster
    weiter zurueck, ist der Faktor dort konstant null - und genau das
    war der Fehler vom 26.08.2026: ein Panel, das vollstaendig aussieht
    und in den frueheren Jahren leer ist. Der Faktor faellt dann an der
    Jahresstabilitaet durch, ohne dass es an den Daten liegt.

    Die Korrektur an `--max-filings` allein reicht NICHT: Sie sorgt nur
    dafuer, dass innerhalb des Meldungsfensters nichts fehlt. Ein zu
    langes Kursfenster erzeugt dieselbe Verzerrung noch einmal.
    """
    beginn_kurse = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=jahre * 365.25)
    beginn_meldungen = pd.Timestamp(since, tz="UTC")
    luecke = (beginn_meldungen - beginn_kurse).days
    if luecke > 90:
        raise SystemExit(
            f"\n  ABBRUCH: Das Kursfenster beginnt {luecke} Tage vor dem "
            f"Meldungsfenster.\n"
            f"    Kurse ab     {beginn_kurse.date()}  (--jahre {jahre:g})\n"
            f"    Meldungen ab {beginn_meldungen.date()}  (--since {since})\n\n"
            f"  In dieser Luecke ist der Insider-Faktor konstant null. Das ist\n"
            f"  exakt die Zeitverzerrung aus §G41, nur an anderer Stelle.\n"
            f"  Entweder --jahre auf ~{jahre - luecke/365.25:.1f} senken "
            f"oder --since auf {beginn_kurse.date()} vorziehen.\n")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--symbole", type=int, default=40)
    p.add_argument("--jahre", type=float, default=4.0,
                   help="Kurshistorie. MUSS zu --since passen, siehe "
                        "_pruefe_fenster (§G41)")
    p.add_argument("--since", default="2022-09-01",
                   help="Ab wann Form-4-Meldungen gezaehlt werden")
    p.add_argument("--horizont", type=int, default=5)
    p.add_argument("--max-filings", type=int, default=400,
                   help="Obergrenze Form-4-Einreichungen JE SYMBOL "
                        "(0 = unbegrenzt). Schuetzt vor Grosskonzernen mit "
                        "sehr vielen meldepflichtigen Personen, die sonst "
                        "die Laufzeit dominieren.")
    p.add_argument("--alle", action="store_true",
                   help="Ganzes Universum (aktuell 2168 Symbole) statt "
                        "einer Stichprobe - mehrtaegiger Lauf, siehe Modulkopf.")
    p.add_argument("--checkpoint-every", type=int, default=50,
                   help="Alle N Symbole einen Zwischenstand wegschreiben "
                        f"(0 = aus). Datei: {CHECKPOINT}")
    args = p.parse_args()
    _pruefe_fenster(args.jahre, args.since)
    max_filings = args.max_filings or None

    # `load_universe(max_symbols=N)` sortiert nach Dollarumsatz und nimmt
    # die N GROESSTEN - fuer diesen Kandidaten die denkbar schlechteste
    # Auswahl: Grosskonzerne haben die meisten Insider-Meldungen (langsam
    # abzurufen) und sind laut `edgar.py`-Doku genau dort, wo der Effekt
    # am schwaechsten ist ("bei kleineren, wenig beachteten Werten sogar
    # STAERKER"). Deshalb: ganzes Universum laden, dann ZUFAELLIG (fester
    # Seed, reproduzierbar) daraus ziehen statt die Top-N zu nehmen - ausser
    # bei --alle, da ist die Reihenfolge ohnehin egal.
    pool = universe.load_universe()
    if args.alle:
        symbols = list(pool)
    else:
        rng = np.random.default_rng(seed=42)
        symbols = list(rng.choice(pool, size=min(args.symbole, len(pool)),
                                  replace=False))

    print("=" * 78)
    print(f"  EDGAR-INSIDER-KANDIDAT  |  {len(symbols)} Symbole  |  seit {args.since}")
    print("=" * 78)
    if len(symbols) < MECHANIK_GRENZE:
        print(f"\n  ACHTUNG: Unter {MECHANIK_GRENZE} Symbolen ist das eine")
        print("  ZEITMESSUNG, KEIN Befund (§B4 - PEAD sah auf 60 Symbolen")
        print("  hervorragend aus und brach auf 800 zusammen).\n")
    if MARKT not in symbols:
        symbols = [*symbols, MARKT]

    print(f"  Kursdaten ({args.jahre:g} Jahre, aus dem Cache)")
    bars = datasources.get_history(symbols, years=args.jahre,
                                   source="yfinance", use_cache=True,
                                   verbose=False)
    if bars.empty:
        print("  Keine Kursdaten.")
        return 1
    print(f"     {len(bars):,} Bars, "
          f"{bars.index.get_level_values('symbol').nunique()} Symbole")

    print(f"\n  EDGAR-Insider-Merkmale bauen (SEC-Limit 8 req/s, "
          f"Plattencache macht Wiederholungen billig, "
          f"max. {max_filings or 'unbegrenzt'} Meldungen/Symbol)")
    panels = baue_edgar_panels(bars, list(symbols), args.since,
                               max_filings=max_filings,
                               checkpoint_every=args.checkpoint_every)
    if not panels:
        print("  Keine verwertbaren Insider-Daten.")
        return 1

    fwd = vorwaertsrenditen(bars, args.horizont)

    print("\n" + "=" * 78)
    print("  ERGEBNIS")
    print("=" * 78)
    print("\n  Vergleich: bester bestaetigter Faktor `reversal_3d` hat IC 0.018.")
    print("  Massgeblich ist die Zahl der MONATE, nicht der Tage.\n")

    zeilen = []
    for name, panel in sorted(panels.items()):
        e = bewerte(panel, fwd)
        e["kandidat"] = name
        zeilen.append(e)
    df = pd.DataFrame(zeilen).set_index("kandidat")
    df = df.sort_values("ic", key=lambda s: s.abs(), ascending=False)
    print(df[["n_tage", "n_monate", "ic", "t", "jahre_positiv",
              "jahre_gesamt", "stabil", "belastbar"]].to_string())

    if len(symbols) < MECHANIK_GRENZE:
        print("\n" + "-" * 78)
        print(f"  {len(symbols)} Symbole sind eine ZEITMESSUNG, kein Befund.")
        print("  Fuer den echten Test: --symbole >= 100 (empfohlen: 300+) oder --alle.")
        return 0

    treffer = df[df["belastbar"].fillna(False) & df["stabil"].fillna(False)]
    print("\n" + "-" * 78)
    if treffer.empty:
        print("  KEIN Kandidat besteht beide Huerden (|t| > 2 ueber >= 20")
        print("  Monate UND Vorzeichen in jedem Jahr gleich).")
    else:
        print(f"  {len(treffer)} Kandidat(en) bestehen beide Huerden - "
              f"weiter zur Eigenstaendigkeitspruefung:\n")
        for name, r in treffer.iterrows():
            print(f"    {name:<24} IC {r['ic']:+.5f}  t={r['t']:.2f}  "
                  f"({r['jahre_positiv']}/{r['jahre_gesamt']} Jahre)")

        print("\n  EIGENSTAENDIGKEIT gegen die bestehenden Umkehr-Faktoren:")
        for name in treffer.index:
            try:
                eig = eigenstaendigkeit(panels[name], bars, fwd, verbose=False)
                print(f"\n  {name}:")
                print(eig.to_string())
            except Exception as e:  # noqa: BLE001
                print(f"  {name}: Eigenstaendigkeitspruefung fehlgeschlagen: "
                      f"{type(e).__name__}: {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
