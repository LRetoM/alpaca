"""Handelsumgebung fuer RL - mit echten Reibungen und echten Broker-Regeln.

Die Umgebung ist der wichtigere Teil eines RL-Systems. Ein Agent lernt
exakt das, was die Umgebung belohnt - ist sie zu freundlich, lernt er
eine Politik, die es in der Realitaet nicht gibt.

Deshalb sind hier eingebaut:
  * Gebuehren und Slippage bei JEDER Positionsaenderung
  * die PDT-Regel (max. 3 Daytrades je 5 Werktage unter 25.000 USD)
  * Ausfuehrung immer erst auf der Folge-Bar (kein Handeln zum Kurs,
    den man gerade erst gesehen hat)
  * Strafterme fuer genau die Fehler, die vermieden werden sollen

Die Belohnung ist bewusst zerlegt und wird einzeln protokolliert. So
laesst sich nach dem Training beantworten, WELCHER Anreiz das Verhalten
getrieben hat - statt nur zu sehen, dass er irgendetwas getan hat.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum

import numpy as np
import pandas as pd


class Action(IntEnum):
    """Ziel-Positionsgroesse, nicht Kauf/Verkauf.

    RL ist bei der Frage "wie viel" nachweislich staerker als bei
    "in welche Richtung".
    """

    FLAT = 0
    QUARTER = 1
    HALF = 2
    FULL = 3


ACTION_EXPOSURE: dict[int, float] = {
    Action.FLAT: 0.0,
    Action.QUARTER: 0.25,
    Action.HALF: 0.50,
    Action.FULL: 1.00,
}


@dataclass
class RewardConfig:
    """Belohnung und Strafen - die "Punkte", die das System vergibt und abzieht.

    Grundbelohnung ist die logarithmische Aenderung des Kontowerts. Log,
    weil sich Renditen multiplikativ zusammensetzen: +50 % und -50 %
    ergeben nicht null, sondern -25 %. Die Log-Form bestraft grosse
    Verluste automatisch staerker - genau richtig fuer ein System, dessen
    Ziel ein dauerhaft wachsendes Konto ist.
    """

    equity_scale: float = 100.0
    """Skalierung der Hauptbelohnung. Rohrenditen (~0.001) sind fuer
    Gradienten zu klein."""

    turnover_penalty: float = 0.5
    """Strafe je Einheit Positionsaenderung. Bestraft Hin- und Herhandeln
    ueber die Kosten hinaus - Handeln muss sich lohnen, nicht nur nicht schaden."""

    drawdown_penalty: float = 2.0
    """Strafe fuer JEDES neue Zwischentief. Ohne diesen Term lernt der
    Agent, mit voller Position zu zocken: der Erwartungswert ist positiv,
    der Weg dorthin unaushaltbar."""

    violation_penalty: float = 5.0
    """Strafe fuer den Versuch, eine Broker-Regel zu verletzen (PDT).
    Die Aktion wird zusaetzlich verhindert - der Agent soll lernen, dass
    sie nicht existiert."""

    hold_bonus: float = 0.0
    """Optionaler Bonus fuers Halten. Standard 0 - nur einschalten, wenn
    der Agent trotz Turnover-Strafe zu nervoes handelt."""


@dataclass
class EnvConfig:
    initial_cash: float = 100_000.0
    fee_bps: float = 1.0
    slippage_bps: float = 3.0
    max_steps: int | None = None
    enforce_pdt: bool = True
    pdt_equity_threshold: float = 25_000.0
    pdt_max_day_trades: int = 3
    pdt_window: int = 5
    reward: RewardConfig = field(default_factory=RewardConfig)


class TradingEnv:
    """Gym-aehnliche Umgebung fuer eine einzelne Aktie.

        env = TradingEnv(features, prices)
        state = env.reset()
        state, reward, done, info = env.step(Action.HALF)

    Bewusst ohne gymnasium-Abhaengigkeit: die Schnittstelle ist klein und
    eine weitere Bibliothek waere hier nur Ballast.
    """

    def __init__(
        self,
        features: pd.DataFrame,
        prices: pd.Series,
        config: EnvConfig | None = None,
        feature_scaler: tuple[np.ndarray, np.ndarray] | None = None,
    ):
        """
        Args:
            features: Merkmalsmatrix, strikt kausal (mit pit.audit_feature_function
                geprueft!). Index muss zu `prices` passen.
            feature_scaler: (mittel, std) aus dem TRAININGSFENSTER. Wird die
                Standardisierung auf allen Daten berechnet, sickert Wissen
                ueber die Zukunft ein - ein subtiles, sehr haeufiges Leck.
        """
        idx = features.index.intersection(prices.index)
        self.features = features.loc[idx].replace([np.inf, -np.inf], np.nan).ffill().fillna(0.0)
        self.prices = prices.loc[idx].astype(float)
        self.cfg = config or EnvConfig()

        if feature_scaler is None:
            mu = self.features.to_numpy(dtype=np.float64).mean(axis=0)
            sd = self.features.to_numpy(dtype=np.float64).std(axis=0)
        else:
            mu, sd = feature_scaler
        self._mu = mu
        self._sd = np.where(np.asarray(sd) < 1e-9, 1.0, sd)

        self.n_market_features = self.features.shape[1]
        # 5 Portfolio-Zustaende ergaenzen die Marktmerkmale.
        self.state_dim = self.n_market_features + 5
        self.n_actions = len(Action)
        self.reset()

    # --- Kern -------------------------------------------------------------
    def reset(self, start: int = 0) -> np.ndarray:
        self.t = max(1, start)
        self.cash = self.cfg.initial_cash
        self.exposure = 0.0
        self.equity = self.cfg.initial_cash
        self.peak_equity = self.cfg.initial_cash
        self.drawdown = 0.0
        self.bars_held = 0
        self.entry_price: float | None = None
        self._day_trades: list[int] = []
        self._opened_today_at: int | None = None
        self.history: list[dict] = []
        self.done = False
        return self._state()

    def step(self, action: int) -> tuple[np.ndarray, float, bool, dict]:
        """Fuehrt eine Aktion aus und rueckt einen Zeitschritt vor."""
        if self.done:
            raise RuntimeError("Episode beendet - reset() aufrufen.")

        target = ACTION_EXPOSURE[int(action)]
        prev_exposure = self.exposure
        violation = False

        # --- Broker-Regel: wuerde das ein Daytrade sein? ---
        if self.cfg.enforce_pdt and self._blocks_day_trade(target):
            target = prev_exposure  # Aktion wird verhindert
            violation = True

        delta = abs(target - prev_exposure)

        # Kosten fallen auf den gehandelten Anteil an, nicht aufs Ganze.
        cost_rate = (self.cfg.fee_bps + self.cfg.slippage_bps) / 10_000
        cost = self.equity * delta * cost_rate

        # --- Zeitschritt: Rendite der FOLGENDEN Bar ---
        if self.t + 1 >= len(self.prices):
            self.done = True
            return self._state(), 0.0, True, {"grund": "daten_ende"}

        p_now = float(self.prices.iloc[self.t])
        p_next = float(self.prices.iloc[self.t + 1])
        market_return = p_next / p_now - 1

        equity_before = self.equity
        # Die neue Position wirkt ab jetzt - deshalb `target`, nicht `prev`.
        self.equity = self.equity * (1 + target * market_return) - cost

        if delta > 1e-9:
            self._record_trade(prev_exposure, target)

        self.exposure = target
        self.bars_held = self.bars_held + 1 if target > 0 else 0
        self.peak_equity = max(self.peak_equity, self.equity)
        prev_dd = self.drawdown
        self.drawdown = self.equity / self.peak_equity - 1

        reward, parts = self._reward(
            equity_before, self.equity, delta, prev_dd, self.drawdown, violation, target
        )

        self.history.append(
            {
                "t": self.prices.index[self.t],
                "action": int(action),
                "exposure": target,
                "price": p_now,
                "equity": self.equity,
                "reward": reward,
                "violation": violation,
                **parts,
            }
        )

        self.t += 1
        limit = self.cfg.max_steps
        if self.t + 1 >= len(self.prices) or (limit and len(self.history) >= limit):
            self.done = True
        if self.equity <= self.cfg.initial_cash * 0.1:
            self.done = True  # praktisch ruiniert - Episode abbrechen

        return self._state(), reward, self.done, {"equity": self.equity, "parts": parts}

    # --- Belohnung ---------------------------------------------------------
    def _reward(
        self,
        eq_before: float,
        eq_after: float,
        turnover: float,
        dd_before: float,
        dd_after: float,
        violation: bool,
        exposure: float,
    ) -> tuple[float, dict]:
        r = self.cfg.reward
        log_growth = np.log(max(eq_after, 1e-6) / max(eq_before, 1e-6))

        gain = r.equity_scale * log_growth
        pen_turnover = -r.turnover_penalty * turnover
        # Nur NEUE Tiefs bestrafen, nicht das blosse Verharren im Minus.
        pen_drawdown = -r.drawdown_penalty * max(0.0, dd_before - dd_after)
        pen_violation = -r.violation_penalty if violation else 0.0
        bonus_hold = r.hold_bonus if (turnover < 1e-9 and exposure > 0) else 0.0

        total = gain + pen_turnover + pen_drawdown + pen_violation + bonus_hold
        return float(total), {
            "r_gewinn": round(float(gain), 5),
            "r_turnover": round(float(pen_turnover), 5),
            "r_drawdown": round(float(pen_drawdown), 5),
            "r_verstoss": round(float(pen_violation), 5),
            "r_halten": round(float(bonus_hold), 5),
        }

    # --- PDT ---------------------------------------------------------------
    def _blocks_day_trade(self, target: float) -> bool:
        """Wuerde diese Aenderung die PDT-Regel verletzen?"""
        if self.equity >= self.cfg.pdt_equity_threshold:
            return False
        # Daytrade = am selben Tag eroeffnet und wieder geschlossen.
        closing_today = (
            self._opened_today_at == self.t
            and self.exposure > 0
            and target < self.exposure
        )
        if not closing_today:
            return False
        recent = [t for t in self._day_trades if self.t - t <= self.cfg.pdt_window]
        return len(recent) >= self.cfg.pdt_max_day_trades

    def _record_trade(self, prev: float, target: float) -> None:
        if prev == 0 and target > 0:
            self._opened_today_at = self.t
            self.entry_price = float(self.prices.iloc[self.t])
        elif prev > 0 and target < prev and self._opened_today_at == self.t:
            self._day_trades.append(self.t)

    # --- Zustand -----------------------------------------------------------
    def _state(self) -> np.ndarray:
        row = self.features.iloc[min(self.t, len(self.features) - 1)].to_numpy(
            dtype=np.float64
        )
        market = np.clip((row - self._mu) / self._sd, -5, 5)

        unrealized = 0.0
        if self.entry_price and self.exposure > 0:
            unrealized = float(self.prices.iloc[self.t]) / self.entry_price - 1

        recent_dt = len([t for t in self._day_trades if self.t - t <= self.cfg.pdt_window])
        portfolio = np.array(
            [
                self.exposure,
                np.clip(unrealized, -1, 1),
                np.clip(self.bars_held / 60.0, 0, 2),
                np.clip(self.drawdown, -1, 0),
                recent_dt / max(1, self.cfg.pdt_max_day_trades),
            ],
            dtype=np.float64,
        )
        return np.nan_to_num(np.concatenate([market, portfolio])).astype(np.float32)

    # --- Auswertung --------------------------------------------------------
    def frame(self) -> pd.DataFrame:
        """Verlauf der Episode inklusive aller Belohnungsanteile."""
        if not self.history:
            return pd.DataFrame()
        return pd.DataFrame(self.history).set_index("t")

    @property
    def total_return(self) -> float:
        return self.equity / self.cfg.initial_cash - 1


# ---------------------------------------------------------------------------
# Vergleichspolitiken - ohne sie ist keine Trainingszahl interpretierbar.
# ---------------------------------------------------------------------------
def policy_buy_and_hold(state: np.ndarray, env: TradingEnv) -> int:
    return int(Action.FULL)


def policy_random(state: np.ndarray, env: TradingEnv, rng=None) -> int:
    rng = rng or np.random.default_rng()
    return int(rng.integers(0, len(Action)))


def policy_flat(state: np.ndarray, env: TradingEnv) -> int:
    return int(Action.FLAT)
