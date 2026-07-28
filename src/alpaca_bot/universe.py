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

import pandas as pd
from alpaca.trading.requests import GetAssetsRequest

from .clients import trading_client
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
