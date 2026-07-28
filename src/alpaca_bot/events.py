"""Explosive Kursbewegungen historisch finden - und die Kontrollgruppe dazu.

Das Herzstueck der Ereignisstudie: Welche Aktien sind wann explodiert, wie
sahen sie VORHER aus, und - der Teil, den fast alle vergessen - wie sahen
die aus, die nicht explodiert sind?

Ohne Kontrollgruppe misst man nur, wie Aktien allgemein aussehen. Wenn 80 %
aller Explosionen ein steigendes Volumen zeigten, aber 78 % aller normalen
Aktien auch, dann ist Volumen wertlos. Genau diese zweite Zahl fehlt in den
meisten selbstgebauten Studien.

Zeitliche Struktur jedes Ereignisses:

    Beobachtungsfenster        Sperrzone          Ereignis
  |--------------------------|-----------|--------------------------|
  t0-lookback            t0-blackout     t0                      t0+window
  NUR das sieht das Modell   verworfen    Ausbruch beginnt

Die Sperrzone ist nicht optional. Ohne sie lernt das Modell, den Ausbruch
an seinen ersten Tagen zu erkennen - trivial, und zum Handeln zu spaet.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class EventConfig:
    """Was zaehlt als Explosion?"""

    threshold: float = 0.50
    """Mindest-Rendite, z. B. 0.50 = +50 %."""
    window: int = 60
    """...innerhalb dieser Anzahl Handelstage."""
    lookback: int = 120
    """So viele Tage vor dem Ereignis darf das Modell sehen."""
    blackout: int = 5
    """Sperrzone unmittelbar vor t0 - wird verworfen."""
    min_price: float = 1.0
    """Penny Stocks ausschliessen: dort ist +100 % ein Spread-Artefakt."""
    min_dollar_volume: float = 100_000
    """Mindest-Handelsumsatz. Was nicht handelbar ist, ist kein Signal."""
    cooldown: int | None = None
    """Mindestabstand zwischen zwei Ereignissen desselben Symbols.
    None = `window` verwenden."""

    def __post_init__(self):
        if self.cooldown is None:
            self.cooldown = self.window


def find_events(
    bars: pd.DataFrame, config: EventConfig | None = None
) -> pd.DataFrame:
    """Findet alle explosiven Bewegungen im Bar-DataFrame.

    Args:
        bars: MultiIndex (symbol, timestamp) mit OHLCV, wie aus `data.get_bars`.
              Ein flaches DataFrame eines Symbols geht auch.

    Returns:
        Ein Ereignis je Zeile: symbol, t0 (frueheste Einstiegsmoeglichkeit),
        Rendite, Spitzendatum, zwischenzeitlicher Rueckschlag.

    `t0` ist bewusst der ERSTE Tag, an dem die Bewegung noch vollstaendig
    vor einem lag - nicht der Tag des groessten Anstiegs. Nur so misst man,
    was rechtzeitig erkennbar gewesen waere.
    """
    cfg = config or EventConfig()
    rows: list[dict] = []

    for symbol, df in _iter_symbols(bars):
        df = df.sort_index()
        if len(df) < cfg.window + cfg.lookback + cfg.blackout:
            continue

        close = df["close"].astype(float)
        dollar_vol = (close * df["volume"].astype(float)).rolling(20).mean()

        # Hoechstkurs der naechsten `window` Tage - der beste Ausstieg.
        fwd_max = close.shift(-1).rolling(cfg.window, min_periods=5).max().shift(
            -cfg.window + 1
        )
        fwd_return = fwd_max / close - 1

        eligible = (
            (fwd_return >= cfg.threshold)
            & (close >= cfg.min_price)
            & (dollar_vol >= cfg.min_dollar_volume)
        )
        # Genug Vorgeschichte, damit ein Beobachtungsfenster existiert.
        eligible.iloc[: cfg.lookback + cfg.blackout] = False

        candidates = np.flatnonzero(eligible.to_numpy())
        last_taken = -10**9
        for i in candidates:
            if i - last_taken < cfg.cooldown:
                continue  # gehoert noch zur selben Bewegung
            last_taken = i

            t0 = close.index[i]
            entry = float(close.iloc[i])
            seg = close.iloc[i : i + cfg.window + 1]
            peak_pos = int(np.argmax(seg.to_numpy()))
            peak = float(seg.iloc[peak_pos])
            trough_before_peak = float(seg.iloc[: peak_pos + 1].min())

            rows.append(
                {
                    "symbol": symbol,
                    "t0": t0,
                    "entry_price": round(entry, 4),
                    "peak_price": round(peak, 4),
                    "return": round(peak / entry - 1, 4),
                    "peak_date": seg.index[peak_pos],
                    "days_to_peak": peak_pos,
                    # Wie weh tat es zwischendurch? Ein Stop-Loss haette hier
                    # ausgeloest - dieser Wert entscheidet, ob die Bewegung
                    # ueberhaupt handelbar gewesen waere.
                    "max_drawdown_before_peak": round(trough_before_peak / entry - 1, 4),
                    "index_pos": i,
                }
            )

    if not rows:
        return pd.DataFrame(
            columns=["symbol", "t0", "entry_price", "peak_price", "return",
                     "peak_date", "days_to_peak", "max_drawdown_before_peak",
                     "index_pos"]
        )
    return pd.DataFrame(rows).sort_values(["t0", "symbol"]).reset_index(drop=True)


def sample_controls(
    bars: pd.DataFrame,
    events: pd.DataFrame,
    config: EventConfig | None = None,
    n_per_event: int = 20,
    seed: int = 42,
    match_symbol: bool = True,
) -> pd.DataFrame:
    """Zieht Kontrollfaelle: (Symbol, Datum), an denen NICHTS passiert ist.

    Drei Bedingungen, damit der Vergleich etwas aussagt:

      1. **Gleiches Symbol** (`match_symbol=True`, Standard). Ohne das
         vergleicht man NVDA vor dem Ausbruch mit Procter & Gamble an einem
         beliebigen Tag - und "misst" dann nur, dass NVDA volatiler ist als
         P&G. Das ist eine Eigenschaft des Tickers, kein Vorzeichen eines
         Ausbruchs. Mit Symbol-Bindung lautet die Frage richtig: Sah DIESE
         Aktie vor IHREM Ausbruch anders aus als sonst?
      2. **Aehnlicher Zeitraum.** Sonst wird der Bullenmarkt 2021 gegen den
         Baerenmarkt 2022 gestellt und man misst das Datum.
      3. **Nicht im Vorfeld eines echten Ereignisses.** Sonst landen
         Positivfaelle in der Kontrollgruppe.

    `match_symbol=False` nur setzen, wenn bewusst symboluebergreifende
    Unterschiede gesucht werden - dann ist das Ergebnis aber kein
    Timing-Signal, sondern eine Aktienauswahl-Eigenschaft.
    """
    cfg = config or EventConfig()
    rng = np.random.default_rng(seed)

    empty = pd.DataFrame(
        columns=["symbol", "t0", "entry_price", "return", "index_pos"]
    )
    if n_per_event <= 0 or events.empty:
        return empty

    per_symbol = {sym: df.sort_index() for sym, df in _iter_symbols(bars)}
    if not per_symbol:
        return empty

    # Sperrzonen: Ereignisfenster plus Vorlauf und Nachlauf.
    banned: dict[str, list[tuple[pd.Timestamp, pd.Timestamp]]] = {}
    for _, ev in events.iterrows():
        df = per_symbol.get(ev["symbol"])
        if df is None:
            continue
        i = int(ev["index_pos"])
        lo = max(0, i - cfg.lookback)
        hi = min(len(df) - 1, i + cfg.window)
        banned.setdefault(ev["symbol"], []).append((df.index[lo], df.index[hi]))

    event_dates = pd.DatetimeIndex(events["t0"]) if len(events) else pd.DatetimeIndex([])
    symbols = list(per_symbol)
    rows: list[dict] = []

    # Wie viele Kontrollen aus welchem Symbol? Bei Symbol-Bindung so viele,
    # wie das Symbol Ereignisse hat - mal n_per_event.
    if match_symbol and len(events):
        quota = (events["symbol"].value_counts() * n_per_event).to_dict()
        quota = {s: n for s, n in quota.items() if s in per_symbol}
    else:
        total = max(1, len(events)) * n_per_event
        quota = {s: max(1, total // max(1, len(symbols))) for s in symbols}

    for sym, want in quota.items():
        df = per_symbol[sym]
        close = df["close"].astype(float)
        lo = cfg.lookback + cfg.blackout
        hi = len(df) - cfg.window - 1
        if hi <= lo:
            continue

        # Alle zulaessigen Positionen einmal bestimmen, statt blind zu
        # wuerfeln. Bei Symbolen mit vielen Ereignissen ist ein grosser Teil
        # der Historie gesperrt - zufaelliges Probieren laeuft dort leer.
        blocked = np.zeros(len(df), dtype=bool)
        for lo_, hi_ in banned.get(sym, []):
            a = int(df.index.searchsorted(lo_))
            b = int(df.index.searchsorted(hi_, side="right"))
            blocked[a:b] = True

        allowed = np.flatnonzero(~blocked[lo:hi] ) + lo
        allowed = allowed[close.to_numpy()[allowed] >= cfg.min_price]
        if allowed.size == 0:
            continue

        take = min(int(want), allowed.size)
        chosen = rng.choice(allowed, size=take, replace=False)
        for pos in chosen:
            pos = int(pos)
            entry = float(close.iloc[pos])
            seg = close.iloc[pos : pos + cfg.window + 1]
            rows.append(
                {
                    "symbol": sym,
                    "t0": df.index[pos],
                    "entry_price": round(entry, 4),
                    "return": round(float(seg.max()) / entry - 1, 4),
                    "index_pos": pos,
                }
            )

    if not rows:
        return pd.DataFrame(
            columns=["symbol", "t0", "entry_price", "return", "index_pos"]
        )
    return pd.DataFrame(rows).sort_values(["t0", "symbol"]).reset_index(drop=True)


def observation_window(
    bars: pd.DataFrame, symbol: str, t0: pd.Timestamp, config: EventConfig | None = None
) -> pd.DataFrame | None:
    """Gibt NUR die Daten zurueck, die vor dem Ereignis bekannt waren.

    Alles ab `t0 - blackout` wird abgeschnitten. Diese Funktion ist die
    einzige erlaubte Art, an die Vorlaufdaten eines Ereignisses zu kommen.
    """
    cfg = config or EventConfig()
    df = _symbol_frame(bars, symbol)
    if df is None or df.empty:
        return None
    df = df.sort_index()

    pos = int(df.index.searchsorted(t0))
    end = pos - cfg.blackout
    start = end - cfg.lookback
    if start < 0 or end <= start:
        return None
    return df.iloc[start:end].copy()


def build_dataset(
    bars: pd.DataFrame,
    events: pd.DataFrame,
    controls: pd.DataFrame,
    feature_fn,
    config: EventConfig | None = None,
) -> tuple[pd.DataFrame, pd.Series, pd.DataFrame]:
    """Baut die Lernmatrix aus Ereignissen und Kontrollen.

    Fuer jeden Fall wird `feature_fn` auf das Beobachtungsfenster angewendet
    und die LETZTE Zeile genommen - der Zustand am Ende der Sperrzone.

    Returns:
        X (Features), y (1 = Explosion, 0 = Kontrolle), meta (symbol, t0, return)
    """
    cfg = config or EventConfig()
    feats, labels, meta = [], [], []

    for label, table in ((1, events), (0, controls)):
        for _, row in table.iterrows():
            win = observation_window(bars, row["symbol"], row["t0"], cfg)
            if win is None or len(win) < 60:
                continue
            f = feature_fn(win)
            f = f.replace([np.inf, -np.inf], np.nan).dropna(how="all")
            if f.empty:
                continue
            feats.append(f.iloc[-1])
            labels.append(label)
            meta.append(
                {
                    "symbol": row["symbol"],
                    "t0": row["t0"],
                    "return": row.get("return", np.nan),
                    "label": label,
                }
            )

    if not feats:
        return pd.DataFrame(), pd.Series(dtype=float), pd.DataFrame()

    X = pd.DataFrame(feats).reset_index(drop=True)
    y = pd.Series(labels, name="explodiert")
    m = pd.DataFrame(meta)
    keep = X.notna().mean() > 0.7  # Spalten, die meistens fehlen, fliegen raus
    X = X.loc[:, keep]
    return X, y, m


def compare_groups(
    X: pd.DataFrame, y: pd.Series, top: int = 15
) -> pd.DataFrame:
    """Wodurch unterscheiden sich Explosionen von Kontrollen?

    Liefert je Feature den standardisierten Mittelwertunterschied (Cohens d).
    Einordnung: |d| < 0.2 ist praktisch bedeutungslos, 0.2-0.5 klein,
    > 0.5 deutlich. Bei Finanzdaten sind Werte ueber 0.3 schon bemerkenswert.
    """
    rows = []
    for col in X.columns:
        a = pd.to_numeric(X.loc[y == 1, col], errors="coerce").dropna()
        b = pd.to_numeric(X.loc[y == 0, col], errors="coerce").dropna()
        if len(a) < 5 or len(b) < 5:
            continue
        pooled = np.sqrt((a.var(ddof=1) + b.var(ddof=1)) / 2)
        if not np.isfinite(pooled) or pooled == 0:
            continue
        d = (a.mean() - b.mean()) / pooled
        rows.append(
            {
                "feature": col,
                "cohens_d": round(float(d), 3),
                "mittel_explosion": round(float(a.mean()), 4),
                "mittel_kontrolle": round(float(b.mean()), 4),
                "n_explosion": len(a),
                "n_kontrolle": len(b),
            }
        )
    if not rows:
        return pd.DataFrame()
    out = pd.DataFrame(rows)
    return out.reindex(out["cohens_d"].abs().sort_values(ascending=False).index).head(top)


# ---------------------------------------------------------------------------
def _iter_symbols(bars: pd.DataFrame):
    """Iteriert (symbol, df) - egal ob MultiIndex oder flaches DataFrame."""
    if isinstance(bars.index, pd.MultiIndex):
        for symbol in bars.index.get_level_values("symbol").unique():
            yield symbol, bars.xs(symbol, level="symbol")
    else:
        yield getattr(bars, "name", "SYMBOL"), bars


def _symbol_frame(bars: pd.DataFrame, symbol: str) -> pd.DataFrame | None:
    if isinstance(bars.index, pd.MultiIndex):
        try:
            return bars.xs(symbol, level="symbol")
        except KeyError:
            return None
    return bars
