"""Handelsuniversum aufbauen - und den Survivorship Bias sichtbar machen.

Das groesste Risiko am Plan "5000 Aktien ueberwachen" ist kein Modellfehler,
sondern ein Datenfehler: **Alpaca kennt nur heute noch gelistete Symbole.**

Wer heute 5000 Ticker abfragt und 10 Jahre zurueckrechnet, testet
ausschliesslich auf Firmen, die ueberlebt haben. Jede Pleite, jedes
Delisting, jede Notuebernahme fehlt. Etwa 8-12 % der US-Listings
verschwinden pro Jahr - und zwar systematisch die schlechtesten.

Der so entstehende Schein-Vorteil betraegt in Studien 2-4 Prozentpunkte
pro Jahr. Das ist mehr, als die Strategie je verdienen wird. Bei
Nebenwerten ist der Effekt groesser - also genau dort, wo der Ansatz am
besten funktionieren sollte.

Dieses Modul kann den Bias nicht beseitigen (dazu braucht es Daten, die
Alpaca nicht hat). Es macht ihn **messbar**, und es baut Universen, in
denen er klein genug fuer eine erste Validierung ist.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from alpaca.trading.requests import GetAssetsRequest

from .clients import trading_client
from .config import PROJECT_ROOT
from .ratelimit import RateLimiter

_limit = RateLimiter("alpaca_trading")

# Grob geschaetzte jaehrliche Delisting-Rate nach Marktsegment. Dient dazu,
# die Groessenordnung des Bias abzuschaetzen - keine exakte Statistik.
DELISTING_RATE_PER_YEAR = {
    "large_cap": 0.02,
    "mid_cap": 0.05,
    "small_cap": 0.10,
    "micro_cap": 0.18,
}


def all_tradable_assets(
    asset_class: str = "us_equity", exchanges: tuple[str, ...] = ("NASDAQ", "NYSE", "ARCA")
) -> pd.DataFrame:
    """Alle heute handelbaren Symbole.

    ACHTUNG: "heute handelbar" - das ist genau die Survivorship-Falle.
    Fuer Live-Screening ist diese Liste richtig, fuer Backtests nicht.
    """
    from alpaca.trading.enums import AssetClass, AssetStatus

    _limit.acquire()
    assets = trading_client().get_all_assets(
        GetAssetsRequest(status=AssetStatus.ACTIVE, asset_class=AssetClass(asset_class))
    )
    rows = [
        {
            "symbol": a.symbol,
            "name": a.name,
            "exchange": str(a.exchange).split(".")[-1],
            "tradable": a.tradable,
            "shortable": a.shortable,
            "fractionable": a.fractionable,
            "marginable": a.marginable,
        }
        for a in assets
        if a.tradable
    ]
    df = pd.DataFrame(rows)
    if exchanges:
        df = df[df["exchange"].isin(exchanges)]
    return df.sort_values("symbol").reset_index(drop=True)


UNIVERSE_FILE = PROJECT_ROOT / "results" / "factor_lab" / "universum.csv"


def load_universe(
    path: Path | str | None = None, max_symbols: int | None = None
) -> list[str]:
    """Laedt das gemessene Universum aus der Datei von `build_universe`.

    WICHTIG fuer die Strategiewahl: Die Umkehr-Faktoren wurden auf 2.162
    Symbolen als stabil nachgewiesen (100 % positive Jahre). Auf den 150
    liquidesten Werten allein war derselbe Effekt NICHT nachweisbar
    (rsi2: 29 % positive Jahre). Wer die Strategie auf einer kleinen
    Liste von Standardwerten laufen laesst, handelt sie genau dort, wo
    sie gemessen nicht funktioniert.

    Die fest verdrahteten Listen in BENCHMARK_SETS sind fuer Tests und
    Vergleiche gedacht - nicht fuer den Produktivbetrieb.
    """
    p = Path(path) if path else UNIVERSE_FILE
    if not p.exists():
        raise FileNotFoundError(
            f"{p} fehlt. Universum zuerst aufbauen:\n"
            "  python scripts/11_factor_lab.py --max-symbols 2500"
        )
    df = pd.read_csv(p)
    if "dollar_volume" in df.columns:
        df = df.sort_values("dollar_volume", ascending=False)
    syms = df["symbol"].dropna().astype(str).tolist()
    return syms[:max_symbols] if max_symbols else syms


def build_universe(
    min_price: float = 3.0,
    min_dollar_volume: float = 1_000_000,
    exchanges: tuple[str, ...] = ("NASDAQ", "NYSE"),
    probe_days: int = 90,
    batch_size: int = 400,
    verbose: bool = True,
) -> pd.DataFrame:
    """Baut das handelbare Universum in zwei Stufen.

    Das Henne-Ei-Problem: Um nach Liquiditaet zu filtern, braucht man
    Kursdaten - aber neun Jahre Historie fuer 8.000 Symbole zu laden, um
    danach 70 % wegzuwerfen, waere Verschwendung.

    Loesung:
      Stufe 1: alle handelbaren Symbole (1 Request)
      Stufe 2: nur ein kurzes Fenster fuer ALLE laden (~80 Requests),
               daraus Kurs und Umsatz bestimmen und filtern
      Stufe 3: die volle Historie dann nur noch fuer die Ueberlebenden

    ARCA wird standardmaessig ausgeschlossen - dort liegen fast nur ETFs,
    und ein ETF ist keine Einzelaktie mit firmenspezifischem Signal.
    """
    from .data import get_bars

    assets = all_tradable_assets(exchanges=exchanges)
    symbols = assets["symbol"].tolist()
    if verbose:
        print(f"      Stufe 1: {len(symbols):,} handelbare Symbole "
              f"({', '.join(exchanges)})")

    rows: list[dict] = []
    n_batches = (len(symbols) + batch_size - 1) // batch_size
    for i in range(0, len(symbols), batch_size):
        chunk = symbols[i : i + batch_size]
        try:
            bars = get_bars(chunk, "1D", lookback_days=probe_days)
        except Exception as e:  # noqa: BLE001
            if verbose:
                print(f"      Batch {i // batch_size + 1}: {type(e).__name__}")
            continue
        if bars.empty:
            continue
        for sym in bars.index.get_level_values("symbol").unique():
            df = bars.xs(sym, level="symbol")
            if len(df) < probe_days * 0.5:
                continue  # zu viele fehlende Tage = illiquide oder neu
            price = float(df["close"].median())
            dvol = float((df["close"] * df["volume"]).median())
            rows.append({"symbol": sym, "price": price, "dollar_volume": dvol,
                         "bars": len(df)})
        if verbose:
            print(f"      Stufe 2: Batch {i // batch_size + 1}/{n_batches} "
                  f"-> {len(rows):,} mit Daten")

    if not rows:
        return pd.DataFrame(columns=["symbol", "price", "dollar_volume", "bars"])

    df = pd.DataFrame(rows)
    keep = df[(df["price"] >= min_price) & (df["dollar_volume"] >= min_dollar_volume)]
    keep = keep.merge(assets[["symbol", "exchange", "shortable"]], on="symbol", how="left")

    if verbose:
        print(f"      Stufe 2 fertig: {len(df):,} mit Daten, "
              f"{len(keep):,} nach Filter "
              f"(Kurs >= ${min_price:g}, Umsatz >= ${min_dollar_volume:,.0f}/Tag)")
    return keep.sort_values("dollar_volume", ascending=False).reset_index(drop=True)


def fetch_history(
    symbols: list[str], years: float = 5.0, batch_size: int = 300,
    verbose: bool = True
) -> pd.DataFrame:
    """Laedt die volle Historie fuer viele Symbole in Batches.

    Ein einzelner Request ueber tausende Symbole laeuft in Zeitueberschreitungen.
    Batches sind langsamer zu schreiben, aber die einzige Variante, die bei
    dieser Groessenordnung durchlaeuft.
    """
    from .data import get_bars

    frames = []
    n_batches = (len(symbols) + batch_size - 1) // batch_size
    for i in range(0, len(symbols), batch_size):
        chunk = symbols[i : i + batch_size]
        try:
            b = get_bars(chunk, "1D", lookback_days=int(years * 365))
            if not b.empty:
                frames.append(b)
        except Exception as e:  # noqa: BLE001
            if verbose:
                print(f"      Batch {i // batch_size + 1}: {type(e).__name__}: {e}")
            continue
        if verbose:
            total = sum(len(f) for f in frames)
            print(f"      Batch {i // batch_size + 1}/{n_batches} -> {total:,} Bars")

    if not frames:
        return pd.DataFrame()
    return pd.concat(frames).sort_index()


def liquid_universe(
    bars: pd.DataFrame,
    min_price: float = 5.0,
    min_dollar_volume: float = 1_000_000,
    min_history_days: int = 250,
) -> list[str]:
    """Filtert auf handelbare Werte: Kurs, Umsatz und genug Historie.

    Der Umsatzfilter ist kein Komfort, sondern Notwendigkeit. Eine Aktie
    mit 50.000 $ Tagesumsatz zeigt im Backtest schoene Renditen, die beim
    echten Kauf durch den eigenen Marktimpact verschwinden.
    """
    if not isinstance(bars.index, pd.MultiIndex):
        raise ValueError("MultiIndex (symbol, timestamp) erwartet.")

    keep: list[str] = []
    for symbol in bars.index.get_level_values("symbol").unique():
        df = bars.xs(symbol, level="symbol")
        if len(df) < min_history_days:
            continue
        recent = df.tail(60)
        price = float(recent["close"].median())
        dvol = float((recent["close"] * recent["volume"]).median())
        if price >= min_price and dvol >= min_dollar_volume:
            keep.append(symbol)
    return sorted(keep)


def survivorship_warning(n_symbols: int, years: float, segment: str = "small_cap") -> str:
    """Schaetzt, wie viele Werte im Testzeitraum fehlen - und was das kostet."""
    rate = DELISTING_RATE_PER_YEAR.get(segment, 0.10)
    survival = (1 - rate) ** years
    missing = n_symbols / survival - n_symbols
    return (
        f"Survivorship-Schaetzung fuer {segment} ueber {years:.0f} Jahre:\n"
        f"  Heute sichtbar        : {n_symbols:,} Symbole\n"
        f"  Damals vermutlich     : {n_symbols / survival:,.0f} Symbole\n"
        f"  Im Datensatz FEHLEND  : ~{missing:,.0f} ({(1 - survival):.0%}) - "
        f"ueberwiegend die schlechtesten\n"
        f"  Erwartete Schein-Rendite: +2 bis +4 Prozentpunkte pro Jahr\n"
        f"  -> Ergebnisse aus diesem Universum sind eine OBERGRENZE, kein Erwartungswert."
    )


def bias_probe(results_by_segment: dict[str, float]) -> str:
    """Diagnose: Wenn eine Strategie bei Nebenwerten viel besser aussieht als
    bei Standardwerten, arbeitet mit hoher Wahrscheinlichkeit der Bias mit.

        bias_probe({"large_cap": 0.06, "small_cap": 0.19})
    """
    if len(results_by_segment) < 2:
        return "Mindestens zwei Segmente noetig."
    large = results_by_segment.get("large_cap")
    small = results_by_segment.get("small_cap") or results_by_segment.get("micro_cap")
    if large is None or small is None:
        return "Segmente 'large_cap' und 'small_cap' noetig."

    gap = small - large
    lines = [
        f"Large Caps : {large:>7.2%}",
        f"Small Caps : {small:>7.2%}",
        f"Differenz  : {gap:>7.2%}",
        "",
    ]
    if gap > 0.08:
        lines.append(
            "VERDACHT: Der Vorsprung bei Nebenwerten ist gross. Ein Teil davon "
            "ist echt (Nebenwerte sind weniger effizient), ein Teil ist "
            "Survivorship Bias. Ohne Delisting-Daten laesst sich beides nicht "
            "trennen - behandle das Ergebnis als unbestaetigt."
        )
    elif gap > 0.03:
        lines.append(
            "Plausibel: Nebenwerte sind tatsaechlich weniger effizient. "
            "Der Bias ist vermutlich enthalten, aber nicht dominant."
        )
    else:
        lines.append(
            "Unauffaellig: kein ungewoehnlicher Nebenwerte-Vorsprung. "
            "Das spricht dafuer, dass der Effekt nicht vom Bias getrieben ist."
        )
    return "\n".join(lines)


# Startuniversen fuer die Validierung. Bewusst Standardwerte: dort ist der
# Survivorship Bias klein genug, um die METHODE zu pruefen. Erst wenn das
# Verfahren hier traegt, macht der Sprung auf 5000 Werte Sinn.
BENCHMARK_SETS: dict[str, list[str]] = {
    "mega_cap": [
        "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "BRK.B",
        "AVGO", "JPM", "LLY", "V", "UNH", "XOM", "MA", "JNJ", "PG", "HD",
        "COST", "ABBV",
    ],
    "sector_etfs": [
        "XLK", "XLF", "XLV", "XLE", "XLI", "XLY", "XLP", "XLU", "XLB", "XLRE",
        "XLC",
    ],
    "broad": ["SPY", "QQQ", "IWM", "DIA", "VTI", "EFA", "EEM", "TLT", "GLD", "HYG"],
    # Werte mit dokumentierten Explosionen - gut zum Kalibrieren der
    # Ereigniserkennung, aber KEIN Testuniversum: die Auswahl kennt bereits
    # den Ausgang. Nur zur Anschauung verwenden.
    "known_movers_demo": [
        "NVDA", "SMCI", "TSLA", "AMD", "PLTR", "COIN", "MSTR", "ENPH", "CELH",
    ],
    # Breites, liquides Universum ueber alle Sektoren. Genug Breite, damit
    # der sqrt(BR)-Effekt aus dem Fundamentalgesetz ueberhaupt greifen kann,
    # und liquide genug, dass Spread und Slippage kalkulierbar bleiben.
    #
    # ACHTUNG - Survivorship: Diese Liste besteht aus HEUTE gelisteten
    # Werten. Firmen, die im Testzeitraum verschwanden, fehlen. Das macht
    # jedes Ergebnis zu einer Obergrenze (siehe survivorship_warning).
    "broad_liquid": [
        # Technologie
        "AAPL", "MSFT", "NVDA", "AVGO", "ORCL", "CRM", "ADBE", "AMD", "INTC",
        "QCOM", "TXN", "MU", "AMAT", "LRCX", "NOW", "PANW", "SNPS", "CDNS",
        # Kommunikation / Internet
        "GOOGL", "META", "NFLX", "DIS", "CMCSA", "T", "VZ", "TMUS",
        # Konsum zyklisch
        "AMZN", "TSLA", "HD", "MCD", "NKE", "SBUX", "LOW", "TJX", "BKNG",
        # Konsum defensiv
        "PG", "KO", "PEP", "COST", "WMT", "MDLZ", "CL", "MO",
        # Gesundheit
        "UNH", "JNJ", "LLY", "ABBV", "MRK", "PFE", "TMO", "ABT", "DHR", "BMY",
        "AMGN", "GILD", "CVS", "ISRG", "VRTX", "REGN",
        # Finanzen
        "BRK.B", "JPM", "V", "MA", "BAC", "WFC", "GS", "MS", "AXP", "BLK",
        "SCHW", "C", "SPGI", "CB", "PGR",
        # Industrie
        "CAT", "HON", "UNP", "BA", "GE", "RTX", "LMT", "DE", "UPS", "MMM",
        "ETN", "EMR", "ITW", "CSX",
        # Energie / Rohstoffe
        "XOM", "CVX", "COP", "SLB", "EOG", "PSX", "MPC", "OXY", "LIN", "SHW",
        "FCX", "NEM",
        # Versorger / Immobilien
        "NEE", "DUK", "SO", "D", "AEP", "AMT", "PLD", "EQIX", "CCI", "SPG",
    ],
}


# ---------------------------------------------------------------------------
# Sektoren - Grundlage der Klumpenkontrolle im Risiko-Dach
# ---------------------------------------------------------------------------
SEKTOR_CACHE = PROJECT_ROOT / "results" / "factor_lab" / "sektoren.csv"


def sektoren(symbols: list[str], *, use_cache: bool = True,
             verbose: bool = False) -> dict[str, str]:
    """Symbol -> Sektor, dauerhaft gecacht.

    **Wofuer:** `risiko.pruefe_order` kann ohne diese Zuordnung das
    Klumpenrisiko nicht pruefen. Fuenfzehn Halbleiterwerte sind EINE Wette,
    keine fuenfzehn - im Crash verhalten sie sich auch so. Ohne Sektordaten
    saehe ein solches Depot wie ein perfekt gestreutes aus.

    Der Cache ist bewusst OHNE Datum im Namen: Der Sektor eines
    Unternehmens aendert sich praktisch nie. Ein taegliches Neuladen waere
    bei 1.200 Symbolen ein Vielfaches des yfinance-Tageskontingents - und
    genau dieses Kontingent wird fuer die Forschung gebraucht.

    Nur FEHLENDE Symbole werden nachgeladen. Faellt der Abruf aus, bleibt
    das Symbol unbekannt; `risiko.sektor_anteile` zaehlt es dann unter
    'unbekannt', statt es stillschweigend zu ignorieren.
    """
    import csv

    bekannt: dict[str, str] = {}
    if use_cache and SEKTOR_CACHE.exists():
        with SEKTOR_CACHE.open(encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("symbol"):
                    bekannt[row["symbol"]] = row.get("sektor") or "unbekannt"

    fehlend = [s for s in symbols if s not in bekannt]
    if not fehlend:
        return {s: bekannt.get(s, "unbekannt") for s in symbols}

    import yfinance as yf

    limiter = RateLimiter("yfinance")
    for i, sym in enumerate(fehlend, 1):
        try:
            limiter.acquire()
            info = yf.Ticker(sym).info
            bekannt[sym] = (info or {}).get("sector") or "unbekannt"
        except Exception:  # noqa: BLE001 - einzelne Ausfaelle sind normal
            bekannt[sym] = "unbekannt"
        if verbose and i % 25 == 0:
            print(f"      Sektoren: {i}/{len(fehlend)}")

    SEKTOR_CACHE.parent.mkdir(parents=True, exist_ok=True)
    with SEKTOR_CACHE.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["symbol", "sektor"])
        for s, sek in sorted(bekannt.items()):
            w.writerow([s, sek])
    return {s: bekannt.get(s, "unbekannt") for s in symbols}


def liquiditaets_dezile(symbols: list[str]) -> dict[str, int]:
    """Symbol -> Liquiditaetsdezil (1 = liquideste 10 %, 10 = duennste).

    **Wofuer:** Beantwortet die offene Frage aus `load_universe`: Die
    Umkehr-Faktoren waren auf 2.162 Symbolen stabil, auf den 150
    liquidesten dagegen NICHT (`rsi2` dort nur 29 % positive Jahre). Ob
    das live genauso ist, laesst sich nur beantworten, wenn jede
    Entscheidung ihr Dezil mitfuehrt.

    **Survivorship-Warnung:** Bei duennen Werten ist der Bias am
    groessten (micro_cap 18 %/Jahr Delisting gegen large_cap 2 %). Ein
    Vorsprung im untersten Dezil ist deshalb zuerst ein Verdacht, kein
    Befund - siehe `bias_probe`.
    """
    try:
        df = pd.read_csv(UNIVERSE_FILE)
    except (FileNotFoundError, OSError):
        return {}
    if "dollar_volume" not in df.columns:
        return {}
    df = df.dropna(subset=["symbol", "dollar_volume"]).copy()
    if df.empty:
        return {}
    # qcut mit duplicates="drop": Bei vielen gleichen Umsaetzen koennen
    # Dezilgrenzen zusammenfallen - ohne das Flag wirft pandas.
    df["dezil"] = pd.qcut(df["dollar_volume"].rank(ascending=False, method="first"),
                          10, labels=False, duplicates="drop") + 1
    zuordnung = dict(zip(df["symbol"].astype(str), df["dezil"].astype(int)))
    return {s: zuordnung[s] for s in symbols if s in zuordnung}
