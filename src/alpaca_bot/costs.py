"""Was ein Trade WIRKLICH kostet - und was am Ende tatsaechlich ankommt.

Der teuerste Irrtum im Privathandel ist nicht eine falsche Prognose,
sondern eine falsche Verrechnung. Man sieht einen Kurs von 100,00, kauft,
sieht spaeter 101,00 und glaubt, ein Prozent verdient zu haben. In
Wirklichkeit:

    angezeigter Kurs (letzter Trade)      100,00
    gekauft wird zum BRIEFKURS (Ask)      100,04      <- +4 Cent
    verkauft wird zum GELDKURS (Bid)      100,96      <- -4 Cent
    minus SEC-Gebuehr und FINRA-TAF       ~100,95
    ------------------------------------------------
    tatsaechlicher Gewinn                  0,91 %  statt 1,00 %

Bei einem Trade sind das neun Prozent des Gewinns. Bei 100 Trades im Jahr
ist es der Unterschied zwischen Gewinn und Verlust.

**Im Paper-Konto passiert das nicht** - Alpaca simuliert dort keine
Regulierungsgebuehren und oft auch keinen realistischen Spread. Ein
Paper-Ergebnis ist deshalb systematisch zu gut. Genau dafuer ist dieses
Modul da: Es rechnet die Luecke aus, bevor echtes Geld im Spiel ist.

Der wichtigste Wert hier ist `breakeven_move_pct()`: Um wie viel muss
sich der Kurs bewegen, damit ein Trade ueberhaupt bei null herauskommt?
Liegt der erwartete Gewinn einer Strategie unter dieser Schwelle, ist sie
mathematisch chancenlos - unabhaengig davon, wie gut das Modell ist.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd
import requests

from .config import get_settings
from .ratelimit import RateLimiter, with_retry

_limit = RateLimiter("alpaca_trading")


@dataclass(frozen=True)
class FeeSchedule:
    """Gebuehrensaetze mit Pruefdatum.

    ACHTUNG: Die SEC passt ihren Satz jaehrlich an (teils drastisch - er
    lag zeitweise bei 0,00 $/Mio.). `verified` zeigt, wann zuletzt
    geprueft wurde. Ist das Datum aelter als ein Jahr, nachschlagen -
    veraltete Saetze machen jede Kostenrechnung falsch.
    """

    # --- US-Aktien ---
    commission_per_share: float = 0.0
    """Alpaca: 0 $ Kommission auf US-Aktien und ETFs."""

    sec_fee_per_million: float = 20.60
    """SEC Section 31, NUR auf Verkaeufe. Ab 04.04.2026: 20,60 $ je Mio. USD."""

    finra_taf_per_share: float = 0.000166
    """FINRA Trading Activity Fee, NUR auf Verkaeufe, je Aktie."""

    finra_taf_max_per_trade: float = 8.30
    """Deckel je Verkaufsorder."""

    # --- Krypto ---
    crypto_taker_bps: float = 25.0
    crypto_maker_bps: float = 15.0

    verified: str = "2026-07-28"
    sources: tuple[str, ...] = (
        "https://www.federalregister.gov/documents/2026/03/04/2026-04233/"
        "order-making-fiscal-year-2026-annual-adjustments-to-transaction-fee-rates",
        "https://www.finra.org/rules-guidance/guidance/faqs/trading-activity-fee",
    )

    def is_stale(self, today: str | None = None) -> bool:
        t = pd.Timestamp(today or pd.Timestamp.now())
        return (t - pd.Timestamp(self.verified)).days > 365


DEFAULT_FEES = FeeSchedule()


@dataclass
class CostBreakdown:
    """Jede einzelne Kostenkomponente eines Trades."""

    side: str
    qty: float
    quoted_price: float
    """Der angezeigte Kurs (letzter Trade) - NICHT der, zu dem gehandelt wird."""
    effective_price: float
    """Der Kurs, zu dem tatsaechlich ausgefuehrt wird (Ask beim Kauf, Bid beim Verkauf)."""
    gross_value: float
    spread_cost: float
    commission: float
    sec_fee: float
    finra_taf: float
    slippage: float
    total_cost: float
    net_proceeds: float
    """Beim Verkauf: was wirklich auf dem Konto landet.
    Beim Kauf: was wirklich abgebucht wird."""

    @property
    def cost_bps(self) -> float:
        return self.total_cost / self.gross_value * 10_000 if self.gross_value else 0.0

    def __str__(self) -> str:
        return "\n".join(
            [
                f"  {self.side.upper()} {self.qty:g} Stueck",
                f"    angezeigter Kurs        {self.quoted_price:>12,.4f}",
                f"    tatsaechl. Ausfuehrung  {self.effective_price:>12,.4f}"
                f"   ({'Brief/Ask' if self.side == 'buy' else 'Geld/Bid'})",
                f"    Bruttowert              {self.gross_value:>12,.2f}",
                "    " + "-" * 40,
                f"    Spread (halb)           {self.spread_cost:>12,.2f}",
                f"    Kommission              {self.commission:>12,.2f}",
                f"    SEC-Gebuehr             {self.sec_fee:>12,.4f}",
                f"    FINRA TAF               {self.finra_taf:>12,.4f}",
                f"    Slippage (geschaetzt)   {self.slippage:>12,.2f}",
                "    " + "-" * 40,
                f"    KOSTEN GESAMT           {self.total_cost:>12,.2f}"
                f"   ({self.cost_bps:.1f} bps)",
                f"    {'Abbuchung' if self.side == 'buy' else 'Gutschrift':<24}"
                f"{self.net_proceeds:>12,.2f}",
            ]
        )


def effective_price(
    side: str, *, bid: float | None = None, ask: float | None = None,
    last: float | None = None, spread_bps: float | None = None
) -> tuple[float, float]:
    """Zu welchem Kurs wird wirklich gehandelt, und was kostet der Spread?

    Kauf laeuft ueber den Briefkurs (Ask), Verkauf ueber den Geldkurs (Bid).
    Der angezeigte "Kurs" ist meist der letzte Trade und liegt dazwischen -
    die halbe Spanne ist ein realer, sofort anfallender Verlust.

    Returns: (Ausfuehrungskurs, Spread-Kosten je Aktie)
    """
    if bid and ask and ask > bid > 0:
        mid = (bid + ask) / 2
        px = ask if side == "buy" else bid
        return px, abs(px - mid)

    if last is None:
        raise ValueError("Entweder bid/ask oder last angeben.")
    # Ohne Quote: Spanne schaetzen. 5 bps ist fuer Large Caps typisch,
    # bei Nebenwerten sind 30-100 bps normal.
    half = last * (spread_bps if spread_bps is not None else 5.0) / 20_000
    return (last + half if side == "buy" else last - half), half


def estimate_costs(
    side: str,
    qty: float,
    *,
    last: float | None = None,
    bid: float | None = None,
    ask: float | None = None,
    spread_bps: float | None = None,
    slippage_bps: float = 2.0,
    fees: FeeSchedule = DEFAULT_FEES,
    asset: str = "equity",
) -> CostBreakdown:
    """Vollstaendige Kostenaufstellung fuer einen geplanten Trade."""
    side = side.lower()
    quoted = last if last is not None else ((bid + ask) / 2 if bid and ask else 0.0)
    px, half_spread = effective_price(
        side, bid=bid, ask=ask, last=last, spread_bps=spread_bps
    )
    gross = qty * px

    spread_cost = half_spread * qty
    slippage = gross * slippage_bps / 10_000

    if asset == "crypto":
        commission = gross * fees.crypto_taker_bps / 10_000
        sec_fee = taf = 0.0
    else:
        commission = qty * fees.commission_per_share
        # SEC und FINRA fallen NUR beim Verkauf an.
        if side == "sell":
            sec_fee = gross * fees.sec_fee_per_million / 1_000_000
            taf = min(qty * fees.finra_taf_per_share, fees.finra_taf_max_per_trade)
        else:
            sec_fee = taf = 0.0

    total = spread_cost + commission + sec_fee + taf + slippage
    net = gross + total if side == "buy" else gross - total

    return CostBreakdown(
        side=side,
        qty=qty,
        quoted_price=round(quoted, 4),
        effective_price=round(px, 4),
        gross_value=round(gross, 2),
        spread_cost=round(spread_cost, 4),
        commission=round(commission, 4),
        sec_fee=round(sec_fee, 6),
        finra_taf=round(taf, 6),
        slippage=round(slippage, 4),
        total_cost=round(total, 4),
        net_proceeds=round(net, 2),
    )


def round_trip(
    qty: float,
    entry_price: float,
    exit_price: float,
    *,
    spread_bps: float = 5.0,
    slippage_bps: float = 2.0,
    fees: FeeSchedule = DEFAULT_FEES,
    asset: str = "equity",
) -> dict:
    """Kompletter Trade: kaufen, halten, verkaufen. Was bleibt uebrig?

    Die Antwort auf deine Frage - nicht "was denken wir zu verdienen",
    sondern "was steht am Ende auf dem Konto".
    """
    buy = estimate_costs(
        "buy", qty, last=entry_price, spread_bps=spread_bps,
        slippage_bps=slippage_bps, fees=fees, asset=asset
    )
    sell = estimate_costs(
        "sell", qty, last=exit_price, spread_bps=spread_bps,
        slippage_bps=slippage_bps, fees=fees, asset=asset
    )

    naive_profit = qty * (exit_price - entry_price)
    real_profit = sell.net_proceeds - buy.net_proceeds
    total_costs = buy.total_cost + sell.total_cost
    invested = buy.net_proceeds

    return {
        "naiver_gewinn": round(naive_profit, 2),
        "naive_rendite": round(exit_price / entry_price - 1, 5),
        "echter_gewinn": round(real_profit, 2),
        "echte_rendite": round(real_profit / invested, 5) if invested else 0.0,
        "kosten_gesamt": round(total_costs, 2),
        "kosten_bps": round(total_costs / (qty * entry_price) * 10_000, 1),
        "differenz": round(naive_profit - real_profit, 2),
        "anteil_weg": (
            round((naive_profit - real_profit) / naive_profit, 3)
            if naive_profit > 0 else None
        ),
        "breakeven_kurs": round(_breakeven_price(qty, entry_price, buy, spread_bps,
                                                 slippage_bps, fees, asset), 4),
        "kauf": buy,
        "verkauf": sell,
    }


def _breakeven_price(qty, entry, buy, spread_bps, slippage_bps, fees, asset) -> float:
    """Bei welchem Kurs ist der Trade genau bei null?"""
    lo, hi = entry, entry * 2
    for _ in range(60):
        mid = (lo + hi) / 2
        sell = estimate_costs("sell", qty, last=mid, spread_bps=spread_bps,
                              slippage_bps=slippage_bps, fees=fees, asset=asset)
        if sell.net_proceeds < buy.net_proceeds:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def breakeven_move_pct(
    price: float = 100.0,
    *,
    spread_bps: float = 5.0,
    slippage_bps: float = 2.0,
    qty: float = 100,
    fees: FeeSchedule = DEFAULT_FEES,
) -> float:
    """Um wie viel Prozent muss sich der Kurs mindestens bewegen?

    Die wichtigste Zahl fuer die Strategieauswahl. Liegt der erwartete
    Gewinn je Trade darunter, verliert die Strategie zwangslaeufig -
    egal wie treffsicher das Modell ist.
    """
    rt = round_trip(qty, price, price, spread_bps=spread_bps,
                    slippage_bps=slippage_bps, fees=fees)
    return rt["breakeven_kurs"] / price - 1


def cost_table(
    prices: tuple[float, ...] = (10, 50, 200),
    spreads_bps: tuple[float, ...] = (2, 5, 20, 50),
    qty: float = 100,
) -> pd.DataFrame:
    """Notwendige Mindestbewegung je Kursniveau und Spanne.

    Zeigt sofort, warum Nebenwerte-Daytrading nicht funktionieren kann:
    Bei 50 bps Spanne muss sich der Kurs um ueber ein Prozent bewegen,
    nur um die Kosten wieder hereinzuholen.
    """
    rows = []
    for p in prices:
        row = {"Kurs $": p}
        for s in spreads_bps:
            row[f"Spread {s:g}bps"] = f"{breakeven_move_pct(p, spread_bps=s, qty=qty):.3%}"
        rows.append(row)
    return pd.DataFrame(rows).set_index("Kurs $")


# ---------------------------------------------------------------------------
# Die Wahrheit: tatsaechlich abgerechnete Gebuehren vom Broker
# ---------------------------------------------------------------------------
def actual_activities(
    activity_type: str = "FEE", after: str | None = None, limit: int = 100
) -> pd.DataFrame:
    """Holt echte Kontobewegungen direkt von Alpaca (REST).

    Schaetzungen sind Schaetzungen. Das hier ist die Abrechnung. Sobald
    live gehandelt wird, ist DAS die Quelle der Wahrheit - und die
    Schaetzformeln oben gehoeren dagegen geprueft (`reconcile`).

    activity_type: 'FILL' (Ausfuehrungen), 'FEE' (Gebuehren), 'DIV', 'INT', ...
    """
    s = get_settings()
    base = (
        "https://paper-api.alpaca.markets" if s.paper
        else "https://api.alpaca.markets"
    )
    url = f"{base}/v2/account/activities/{activity_type}"
    params = {"page_size": limit}
    if after:
        params["after"] = after

    _limit.acquire()
    resp = with_retry(
        lambda: requests.get(
            url,
            headers={
                "APCA-API-KEY-ID": s.api_key,
                "APCA-API-SECRET-KEY": s.secret_key,
            },
            params=params,
            timeout=30,
        )
    )
    resp.raise_for_status()
    data = resp.json()
    if not data:
        return pd.DataFrame()
    return pd.DataFrame(data)


def reconcile(expected_bps: float, journal_df: pd.DataFrame,
              *, werte: pd.Series | None = None) -> str:
    """Vergleicht angenommene mit tatsaechlich aufgetretenen Kosten.

    Speist sich aus dem Handelsprotokoll (`journal.slippage_report`).
    Weicht die Realitaet dauerhaft nach oben ab, sind ALLE Backtests um
    genau diese Differenz zu optimistisch - und muessen neu bewertet
    werden, nicht die Strategie.

    **Gemessen wird der MEDIAN, nicht der Mittelwert (§G16).** Bis zum
    22.08.2026 stand hier `journal_df["mittel"].mean()` - der
    ungewichtete Mittelwert der Symbol-Mittelwerte. Ausgegeben wurde
    damit im Tagesbericht:

        angenommen :    3.0 bps
        tatsaechlich:  -80.6 bps
        -> Ausfuehrung ist 83.6 bps besser als angenommen.

    Die Aussage war frei erfunden. Drei kaputte IEX-Quotes (KGS, SIMO,
    GNRC - §G, 04.08.2026) trugen darin genauso viel wie 70 saubere
    Symbole; der Median ueber dieselben 162 Orders liegt bei +0,0 bps.

    Das wiegt schwer, weil `docs/BETRIEBSPLAN.md` §5.2 genau diesen
    Abschnitt als das benennt, was alle 1-2 Wochen zu lesen ist - und
    dort ausdruecklich den **Median** erwartet.

    Args:
        werte: die EINZELNEN Slippage-Werte je Order
            (`journal.slippage_werte()`). Das ist die Ebene, die §3.1
            meint ("ueber 30+ saubere Orders"). Fehlen sie, wird auf den
            Median der Symbol-Mediane zurueckgefallen - gekennzeichnet,
            damit die groebere Ebene sichtbar bleibt.
    """
    if journal_df is None or journal_df.empty:
        return ("Noch keine echten Ausfuehrungen protokolliert. "
                "Der Abgleich wird erst nach den ersten Live-Trades aussagekraeftig.")

    if werte is not None and len(werte.dropna()):
        w = werte.dropna()
        actual, n, ebene = float(w.median()), len(w), "Orders"
    else:
        spalte = "median" if "median" in journal_df else "mittel"
        actual = float(journal_df[spalte].median())
        n = int(journal_df["n"].sum()) if "n" in journal_df else len(journal_df)
        ebene = "Symbol-Mediane"

    diff = actual - expected_bps
    verdict = (
        "Backtest-Annahme ist realistisch."
        if abs(diff) < 2
        else (
            f"Backtests sind um ~{diff:.1f} bps je Trade ZU OPTIMISTISCH. "
            "Slippage-Annahme erhoehen und alle Ergebnisse neu bewerten."
            if diff > 0
            else f"Ausfuehrung ist {abs(diff):.1f} bps besser als angenommen."
        )
    )

    # Ausreisser gehoeren daneben, nicht weggemittelt: Der Median traegt
    # sie bewusst nicht mit, aber sie sind Information (§G16).
    zusatz = ""
    if werte is not None and len(werte.dropna()):
        gross = werte.dropna()
        gross = gross[gross.abs() > 100]
        if len(gross):
            zusatz = (f"\n   {len(gross)} von {n} Order(s) ueber |100| bps "
                      f"(groesste {gross.abs().max():.0f}) - der Median "
                      f"traegt sie nicht mit; pruefen ob Datenfehler (§G).")

    return (
        f"angenommen : {expected_bps:>6.1f} bps\n"
        f"tatsaechlich: {actual:>6.1f} bps   (Median ueber {n} {ebene})\n"
        f"Differenz   : {diff:>+6.1f} bps\n-> {verdict}{zusatz}"
    )
