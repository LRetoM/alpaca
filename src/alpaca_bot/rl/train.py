"""Training und - vor allem - ehrliche Auswertung.

Die Trainingskurve eines DQN sagt fast nichts aus. Ein Agent, der auf
seinen eigenen Trainingsdaten 400 % erwirtschaftet, hat in aller Regel
den Kursverlauf auswendig gelernt.

Deshalb ist hier die Auswertung der eigentliche Kern:

  1. **Walk-Forward.** Trainiert wird auf Fenster n, bewertet auf Fenster
     n+1. Die Bewertungsdaten hat der Agent nie gesehen.
  2. **Zufallspolitik als Messlatte.** Mit vielen Startwerten, um eine
     Verteilung zu erhalten. Liegt der Agent innerhalb dieser Verteilung,
     ist sein Ergebnis Zufall - unabhaengig davon, wie gut es aussieht.
  3. **Perzentil statt Mittelwert.** Nicht "Agent 12 %, Zufall 8 %",
     sondern "Agent schlaegt 73 % aller Zufallslaeufe". Nur die zweite
     Aussage ist gegen Glueck robust.
  4. **Standardisierung nur auf dem Trainingsfenster.** Sonst kennt der
     Agent Mittelwert und Streuung der Zukunft - ein leises, sehr
     wirksames Leck.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .dqn import DQNAgent, DQNConfig
from .env import ACTION_EXPOSURE, Action, EnvConfig, TradingEnv


@dataclass
class FoldResult:
    fold: int
    train_from: str
    train_to: str
    test_from: str
    test_to: str
    agent_return: float
    buy_hold_return: float
    random_median: float
    random_p90: float
    percentile_vs_random: float
    matched_constant_return: float
    """Konstante Position gleicher Hoehe - ohne jedes Timing."""
    avg_exposure: float
    timing_percentile: float
    """Perzentil gegen zeitlich verschobene Kopien der eigenen Politik.
    Unter 95 gibt es kein nachweisbares Timing-Koennen."""
    n_trades: int
    max_drawdown: float
    violations: int


@dataclass
class TrainingReport:
    folds: list[FoldResult] = field(default_factory=list)
    agent: DQNAgent | None = None

    def table(self) -> pd.DataFrame:
        if not self.folds:
            return pd.DataFrame()
        return pd.DataFrame([f.__dict__ for f in self.folds])

    def verdict(self) -> str:
        """Das Urteil. Bewusst unbestechlich formuliert."""
        if not self.folds:
            return "Keine Ergebnisse."
        df = self.table()
        pct_rand = df["percentile_vs_random"].mean()
        timing = df["timing_percentile"].mean()
        beat_bh = (df["agent_return"] > df["buy_hold_return"]).mean()
        beat_matched = (df["agent_return"] > df["matched_constant_return"]).mean()
        mean_ret = df["agent_return"].mean()

        lines = [
            "=" * 66,
            "  URTEIL",
            "=" * 66,
            f"  Mittlere Rendite (out-of-sample)   : {mean_ret:>8.2%}",
            f"  Mittlere Marktbeteiligung          : {df['avg_exposure'].mean():>8.0%}",
            "",
            "  Messlatten, schwaechste zuerst:",
            f"    schlaegt Zufallspolitik          : {pct_rand:>8.0f}. Perzentil"
            "   (schwach - straft nur haeufiges Handeln)",
            f"    schlaegt Buy & Hold              : {beat_bh:>8.0%} der Fenster",
            f"    schlaegt konstante Position      : {beat_matched:>8.0%} der Fenster"
            "   (fair: gleiche Beteiligung, kein Timing)",
            f"    TIMING-KOENNEN                   : {timing:>8.0f}. Perzentil"
            "   (>= 95 erforderlich)",
            "",
        ]

        # Das Urteil haengt am Timing-Test, nicht an der Rendite.
        if timing >= 95 and beat_matched >= 0.6:
            lines += [
                "  ERGEBNIS: Nachweisbares Timing-Koennen.",
                "",
                "  Der Agent war zu den richtigen ZEITPUNKTEN investiert, nicht",
                "  nur im Mittel guenstig positioniert. Das ist das Ergebnis, auf",
                "  das es ankommt - und es ist selten.",
                "",
                "  Trotzdem zuerst pruefen:",
                "    1. pit.audit_feature_function auf den Merkmalen sauber?",
                "    2. Standardisierung nur aus dem Trainingsfenster?",
                "    3. Auf einem unberuehrten Zeitraum wiederholbar?",
            ]
        elif timing >= 80:
            lines += [
                "  ERGEBNIS: Schwacher Hinweis auf Timing-Koennen, nicht belastbar.",
                "  Mit anderen Startwerten, Symbolen und Zeitraeumen wiederholen.",
                "  Haelt der Vorsprung ueber mehrere Laeufe, lohnt Weiterarbeit.",
            ]
        else:
            lines += [
                "  ERGEBNIS: KEIN nachweisbares Timing-Koennen.",
                "",
                "  Die Rendite oben - egal wie hoch - stammt aus der mittleren",
                "  Marktbeteiligung, nicht aus dem Zeitpunkt der Entscheidungen.",
                "  Zeitlich verschobene Kopien derselben Politik haetten aehnlich",
                "  abgeschnitten. Eine konstante Position waere billiger gewesen.",
                "",
                "  Das ist der haeufigste Ausgang und kein Fehler im Code.",
                "  Sinnvolle naechste Schritte:",
                "    - Erst pruefen, ob ueberhaupt ein Signal existiert:",
                "      scripts/06_event_study.py",
                "    - Mehr Symbole ins Training (Breite statt Tiefe)",
                "    - Bessere Merkmale statt groesserem Netz",
                "    - Laengerer Horizont (gamma hoeher)",
            ]
        return "\n".join(lines)


def run_episode(
    env: TradingEnv, policy, *, greedy: bool = True, learn_agent: DQNAgent | None = None
) -> dict:
    """Spielt eine Episode. Mit `learn_agent` wird dabei gelernt."""
    state = env.reset()
    total_reward, violations = 0.0, 0

    while not env.done:
        action = policy(state, env)
        next_state, reward, done, info = env.step(action)
        if learn_agent is not None:
            learn_agent.remember(state, action, reward, next_state, done)
            learn_agent.learn()
        total_reward += reward
        if env.history and env.history[-1].get("violation"):
            violations += 1
        state = next_state

    frame = env.frame()
    n_trades = (
        int((frame["exposure"].diff().abs() > 1e-9).sum()) if not frame.empty else 0
    )
    dd = (
        float((frame["equity"] / frame["equity"].cummax() - 1).min())
        if not frame.empty
        else 0.0
    )
    return {
        "return": env.total_return,
        "reward": total_reward,
        "n_trades": n_trades,
        "max_drawdown": dd,
        "violations": violations,
        "frame": frame,
    }


def random_baseline(
    features: pd.DataFrame,
    prices: pd.Series,
    env_cfg: EnvConfig,
    scaler: tuple[np.ndarray, np.ndarray],
    n_runs: int = 50,
) -> np.ndarray:
    """Verteilung der reinen Zufallspolitik.

    ACHTUNG - diese Messlatte ist schwaecher, als sie aussieht: Die
    Politik wuerfelt bei JEDEM Schritt neu und zahlt dadurch bei fast
    jeder Bar Gebuehren. Sie zu schlagen beweist nur, dass ein Agent
    gelernt hat, nicht staendig zu handeln - dafuer braucht es kein
    Marktsignal.

    Sie bleibt als Untergrenze nuetzlich, aber das eigentliche Urteil
    faellt `timing_skill_test`.
    """
    out = []
    for seed in range(n_runs):
        rng = np.random.default_rng(seed)
        env = TradingEnv(features, prices, env_cfg, feature_scaler=scaler)
        res = run_episode(env, lambda s, e: int(rng.integers(0, len(Action))))
        out.append(res["return"])
    return np.array(out)


def constant_baseline(
    features: pd.DataFrame,
    prices: pd.Series,
    env_cfg: EnvConfig,
    scaler: tuple[np.ndarray, np.ndarray],
    exposure: float,
) -> float:
    """Konstante Position in Hoehe von `exposure` - ohne jedes Timing.

    Die faire Messlatte fuer die durchschnittliche Marktbeteiligung des
    Agenten. Wer im Mittel zu 50 % investiert ist, muss sich mit einer
    dauerhaften 50-%-Position vergleichen, nicht mit Buy & Hold.
    """
    level = min(ACTION_EXPOSURE, key=lambda a: abs(ACTION_EXPOSURE[a] - exposure))
    env = TradingEnv(features, prices, env_cfg, feature_scaler=scaler)
    return run_episode(env, lambda s, e: int(level))["return"]


def timing_skill_test(
    exposure_path: pd.Series, prices: pd.Series, n_rotations: int = 200, seed: int = 0
) -> dict:
    """DER entscheidende Test: steckt im Agenten wirklich Timing-Koennen?

    Verfahren: Die vom Agenten tatsaechlich gewaehlte Positionsfolge wird
    zyklisch um einen zufaelligen Betrag verschoben und erneut auf die
    Kurse angewendet.

    Die Verschiebung erhaelt ALLES, was die Politik ausmacht - mittlere
    Position, Umschlaghaeufigkeit, Haltedauern, Verteilung der Groessen.
    Zerstoert wird ausschliesslich die zeitliche Ausrichtung zu den
    Kursen. Damit misst der Vergleich genau eine Sache: Hat der Agent zum
    RICHTIGEN Zeitpunkt investiert, oder hat er nur eine im Mittel
    guenstige Positionsgroesse gehabt?

    Liegt das echte Ergebnis nicht deutlich ueber der Verschiebungs-
    verteilung, gibt es kein Timing-Koennen - egal wie gut die absolute
    Rendite aussieht.
    """
    rng = np.random.default_rng(seed)
    ret = prices.pct_change().fillna(0.0).to_numpy()
    exp = exposure_path.reindex(prices.index).ffill().fillna(0.0).to_numpy()

    def total(e: np.ndarray) -> float:
        turnover = np.abs(np.diff(e, prepend=0.0))
        # Gleiche Kostenannahme wie in der Umgebung (1 bp Gebuehr + 3 bp Slippage).
        step = e * ret - turnover * 4 / 10_000
        return float(np.prod(1 + step) - 1)

    actual = total(exp)
    n = len(exp)
    shifted = np.array(
        [total(np.roll(exp, int(rng.integers(1, n)))) for _ in range(n_rotations)]
    )
    percentile = float((shifted < actual).mean() * 100)
    return {
        "actual_return": actual,
        "rotated_median": float(np.median(shifted)),
        "rotated_p95": float(np.percentile(shifted, 95)),
        "timing_percentile": percentile,
        "has_timing_skill": bool(percentile >= 95),
    }


def train_walk_forward(
    features: pd.DataFrame,
    prices: pd.Series,
    *,
    n_folds: int = 4,
    episodes_per_fold: int = 30,
    min_train: int = 400,
    env_config: EnvConfig | None = None,
    dqn_config: DQNConfig | None = None,
    n_random: int = 50,
    verbose: bool = True,
) -> TrainingReport:
    """Trainiert und bewertet walk-forward.

    Der Agent bleibt ueber die Fenster erhalten (er lernt weiter), aber
    bewertet wird immer nur auf Daten, die zum Zeitpunkt des Trainings
    noch in der Zukunft lagen.
    """
    idx = features.index.intersection(prices.index)
    features, prices = features.loc[idx], prices.loc[idx]
    env_cfg = env_config or EnvConfig()

    n = len(features)
    if n < min_train + n_folds * 60:
        raise ValueError(
            f"Zu wenig Daten: {n} Bars. Noetig sind mindestens "
            f"{min_train + n_folds * 60}. Mehr Historie laden oder n_folds senken."
        )

    fold_size = (n - min_train) // n_folds
    report = TrainingReport()
    agent: DQNAgent | None = None

    for k in range(n_folds):
        train_end = min_train + k * fold_size
        test_end = n if k == n_folds - 1 else train_end + fold_size

        f_train, p_train = features.iloc[:train_end], prices.iloc[:train_end]
        f_test, p_test = features.iloc[train_end:test_end], prices.iloc[train_end:test_end]
        if len(f_test) < 30:
            continue

        # Standardisierung NUR aus dem Trainingsfenster.
        arr = f_train.to_numpy(dtype=np.float64)
        scaler = (np.nanmean(arr, axis=0), np.nanstd(arr, axis=0))

        train_env = TradingEnv(f_train, p_train, env_cfg, feature_scaler=scaler)
        if agent is None:
            agent = DQNAgent(train_env.state_dim, train_env.n_actions, dqn_config)

        if verbose:
            print(f"\n[Fenster {k + 1}/{n_folds}] Training auf {len(f_train)} Bars "
                  f"({episodes_per_fold} Episoden) ...")

        for ep in range(episodes_per_fold):
            res = run_episode(
                train_env,
                lambda s, e: agent.act(s, greedy=False),
                learn_agent=agent,
            )
            if verbose and (ep + 1) % max(1, episodes_per_fold // 3) == 0:
                loss = np.mean(agent.losses[-200:]) if agent.losses else float("nan")
                print(f"    Episode {ep + 1:>3}: Rendite {res['return']:>7.1%} | "
                      f"eps {agent.epsilon:.2f} | Verlust {loss:.4f}")

        # --- Auswertung auf ungesehenen Daten ---
        test_env = TradingEnv(f_test, p_test, env_cfg, feature_scaler=scaler)
        agent_res = run_episode(test_env, lambda s, e: agent.act(s, greedy=True))

        bh_env = TradingEnv(f_test, p_test, env_cfg, feature_scaler=scaler)
        bh_res = run_episode(bh_env, lambda s, e: int(Action.FULL))

        rand = random_baseline(f_test, p_test, env_cfg, scaler, n_random)
        percentile = float((rand < agent_res["return"]).mean() * 100)

        # Die beiden fairen Messlatten.
        frame = agent_res["frame"]
        avg_exp = float(frame["exposure"].mean()) if not frame.empty else 0.0
        matched = constant_baseline(f_test, p_test, env_cfg, scaler, avg_exp)
        timing = (
            timing_skill_test(frame["exposure"], p_test.loc[frame.index])
            if not frame.empty
            else {"timing_percentile": float("nan")}
        )

        report.folds.append(
            FoldResult(
                fold=k + 1,
                train_from=str(f_train.index[0].date()),
                train_to=str(f_train.index[-1].date()),
                test_from=str(f_test.index[0].date()),
                test_to=str(f_test.index[-1].date()),
                agent_return=round(agent_res["return"], 4),
                buy_hold_return=round(bh_res["return"], 4),
                random_median=round(float(np.median(rand)), 4),
                random_p90=round(float(np.percentile(rand, 90)), 4),
                percentile_vs_random=round(percentile, 1),
                matched_constant_return=round(float(matched), 4),
                avg_exposure=round(avg_exp, 3),
                timing_percentile=round(float(timing["timing_percentile"]), 1),
                n_trades=agent_res["n_trades"],
                max_drawdown=round(agent_res["max_drawdown"], 4),
                violations=agent_res["violations"],
            )
        )
        if verbose:
            print(f"  -> Test {f_test.index[0].date()} bis {f_test.index[-1].date()}: "
                  f"Agent {agent_res['return']:>7.1%} | B&H {bh_res['return']:>7.1%}")
            print(f"     faire Messlatten: konstant {avg_exp:.0%} -> "
                  f"{matched:>7.1%} | Timing-Perzentil "
                  f"{timing['timing_percentile']:.0f} (>=95 noetig)")

    report.agent = agent
    return report


def evaluate(
    agent: DQNAgent,
    features: pd.DataFrame,
    prices: pd.Series,
    scaler: tuple[np.ndarray, np.ndarray] | None = None,
    env_config: EnvConfig | None = None,
    n_random: int = 50,
) -> dict:
    """Einzelbewertung gegen alle drei Vergleichspolitiken."""
    cfg = env_config or EnvConfig()
    if scaler is None:
        arr = features.to_numpy(dtype=np.float64)
        scaler = (np.nanmean(arr, axis=0), np.nanstd(arr, axis=0))

    res = run_episode(
        TradingEnv(features, prices, cfg, feature_scaler=scaler),
        lambda s, e: agent.act(s, greedy=True),
    )
    bh = run_episode(
        TradingEnv(features, prices, cfg, feature_scaler=scaler),
        lambda s, e: int(Action.FULL),
    )
    flat = run_episode(
        TradingEnv(features, prices, cfg, feature_scaler=scaler),
        lambda s, e: int(Action.FLAT),
    )
    rand = random_baseline(features, prices, cfg, scaler, n_random)

    return {
        "agent_return": res["return"],
        "buy_hold_return": bh["return"],
        "flat_return": flat["return"],
        "random_median": float(np.median(rand)),
        "percentile_vs_random": float((rand < res["return"]).mean() * 100),
        "n_trades": res["n_trades"],
        "max_drawdown": res["max_drawdown"],
        "violations": res["violations"],
        "frame": res["frame"],
    }
