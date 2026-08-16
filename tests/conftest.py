"""Gemeinsame Bausteine fuer alle Tests.

Grundsatz: **Kein Test braucht Netz.** Alles laeuft gegen synthetische
Kursreihen und temporaere Datenbanken. Ein Test, der eine API braucht,
prueft nicht die Logik, sondern den Betriebszustand - und schlaegt fehl,
sobald man ihn am Wochenende laufen laesst.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from alpaca_bot.engine import MarketSnapshot, PortfolioState, Position


@pytest.fixture
def idx() -> pd.DatetimeIndex:
    """300 Tage - genug fuer die 260-Bar-Vorlaufzeit der Signale."""
    return pd.date_range("2024-01-01", periods=300, freq="D", tz="UTC")


def mach_bars(idx, kurs=100.0, volumen=5e6) -> pd.DataFrame:
    """OHLCV mit konstantem oder vorgegebenem Kursverlauf."""
    k = np.full(len(idx), kurs, dtype=float) if np.isscalar(kurs) else np.asarray(kurs, dtype=float)
    return pd.DataFrame(
        {"open": k, "high": k * 1.01, "low": k * 0.99, "close": k,
         "volume": np.full(len(idx), volumen)},
        index=idx,
    )


def mach_signale(idx, score=0.5, atr=5.0, kurs=100.0) -> pd.DataFrame:
    """Vorberechnete Signale - umgeht die Signalberechnung.

    Erlaubt, die Entscheidungslogik isoliert zu pruefen: Wer Score und ATR
    direkt vorgibt, testet `decide()` und nicht `build_reversal_frame()`.
    """
    return pd.DataFrame(
        {"score": score, "atr": atr, "atr_pct": atr / kurs,
         "dollar_volume": 1e8},
        index=idx,
    )


@pytest.fixture
def snapshot_fabrik(idx):
    """Baut eine Momentaufnahme mit beliebig vielen Symbolen."""

    def bauen(symbole: dict, markt_kurs=None) -> MarketSnapshot:
        bars, signals = {}, {}
        for sym, cfg in symbole.items():
            kurs = cfg.get("kurs", 100.0)
            bars[sym] = mach_bars(idx, kurs, cfg.get("volumen", 5e6))
            signals[sym] = mach_signale(
                idx, cfg.get("score", 0.5), cfg.get("atr", 5.0),
                kurs if np.isscalar(kurs) else kurs[-1],
            )
        markt = (pd.Series(markt_kurs, index=idx) if markt_kurs is not None
                 else pd.Series(np.full(len(idx), 500.0), index=idx))
        return MarketSnapshot(as_of=idx[-1], bars=bars, signals=signals,
                              market=markt)

    return bauen


@pytest.fixture
def position_fabrik(idx):
    def bauen(symbol="X", qty=10.0, einstand=100.0, stop=80.0, ziel=200.0,
              gehalten=0, hoechst=None) -> Position:
        return Position(
            symbol=symbol, qty=qty, entry_price=einstand,
            entry_date=idx[-1] - pd.Timedelta(days=max(gehalten, 1)),
            stop_price=stop, target_price=ziel, bars_held=gehalten,
            high_water=hoechst if hoechst is not None else einstand,
        )

    return bauen


@pytest.fixture
def portfolio_fabrik():
    def bauen(positionen=None, kapital=100_000.0, cash=None) -> PortfolioState:
        pos = {p.symbol: p for p in (positionen or [])}
        return PortfolioState(
            cash=cash if cash is not None else kapital,
            equity=kapital, positions=pos,
        )

    return bauen


@pytest.fixture
def temp_store(tmp_path):
    """Frischer `state.Store` in einem Wegwerf-Verzeichnis.

    Wichtig: NIEMALS gegen die echte state.sqlite testen - ein Test, der
    Produktionsdaten anfasst, kann den laufenden Bot beschaedigen.
    """
    from alpaca_bot.state import Store

    return Store(tmp_path / "state.sqlite")


@pytest.fixture
def temp_journal(tmp_path):
    from alpaca_bot.journal import Journal

    return Journal(tmp_path / "journal.sqlite")


@pytest.fixture
def temp_lifecycle(tmp_path):
    from alpaca_bot.lifecycle import Lifecycle

    return Lifecycle(tmp_path / "lifecycle.sqlite")
