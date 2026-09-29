"""Querschnitt-DQN: einen Agenten ueber VIELE Symbole zugleich lernen lassen.

**Warum das ueberhaupt gebaut wird.** `train_walk_forward` (ein Symbol)
zeigte 0 von 4 Symbolen mit Timing-Koennen (`docs/BEFUNDE.md` §G50), und
`08_train_rl.py` schlaegt in seinem eigenen Negativ-Urteil als naechsten
Schritt vor: *"Mehr Symbole ins Training - Breite statt Tiefe"*. Das
deckt sich mit IR = IC * sqrt(BR) aus §G31/§G43: Trennschaerfe kauft man
mit Breite, nicht mit einem groesseren Netz.

Dieses Modul ist die billige, ehrliche Pruefung dieser einen noch nicht
ausgeschoepften Variante. Es aendert nichts an der Handelslogik und
kostet keinen Versuchszaehlerplatz (BETRIEBSPLAN §4).

**Der Aufbau bleibt so streng wie in `train.py`:**

  * Walk-Forward ueber einen GEMEINSAMEN Kalender - bewertet wird immer
    nur, was zur Trainingszeit in der Zukunft lag.
  * Standardisierung aus dem GEPOOLTEN Trainingsfenster, nie aus der
    Zukunft.
  * Das Urteil haengt am `timing_skill_test` je Symbol, nicht an der
    Rendite - und ein einzelnes auswendig gelerntes Fenster (die
    SYRE-Lehre aus §G50) darf das Gesamturteil NICHT tragen: verlangt
    wird ein Median ueber Symbole UND ein Mindestanteil von Symbolen mit
    Koennen.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .dqn import DQNAgent, DQNConfig
from .env import Action, EnvConfig, TradingEnv
from .train import constant_baseline, random_baseline, run_episode, timing_skill_test


@dataclass
class PooledSymbolResult:
    fold: int
    symbol: str
    test_from: str
    test_to: str
    agent_return: float
    matched_constant_return: float
    percentile_vs_random: float
    avg_exposure: float
    timing_percentile: float
    n_trades: int


@dataclass
class PooledFoldSummary:
    fold: int
    n_symbols: int
    median_timing: float
    frac_timing_skill: float
    """Anteil Symbole mit timing_percentile >= 95."""
    median_agent_return: float
    median_matched_return: float
    frac_beat_matched: float


@dataclass
class PooledReport:
    symbol_rows: list[PooledSymbolResult] = field(default_factory=list)
    fold_summaries: list[PooledFoldSummary] = field(default_factory=list)
    agent: DQNAgent | None = None
    n_symbols_total: int = 0
    n_folds: int = 0

    def table(self) -> pd.DataFrame:
        return pd.DataFrame([r.__dict__ for r in self.symbol_rows])

    def fold_table(self) -> pd.DataFrame:
        return pd.DataFrame([s.__dict__ for s in self.fold_summaries])

    # --- die Kennzahlen, an denen das Urteil haengt ---
    def overall_median_timing(self) -> float:
        t = self.table()
        return float(t["timing_percentile"].median()) if not t.empty else float("nan")

    def overall_frac_skill(self) -> float:
        t = self.table()
        return float((t["timing_percentile"] >= 95).mean()) if not t.empty else 0.0

    def frac_beat_matched(self) -> float:
        t = self.table()
        if t.empty:
            return 0.0
        return float((t["agent_return"] > t["matched_constant_return"]).mean())

    def verdict(self) -> str:
        t = self.table()
        if t.empty:
            return "Keine Ergebnisse."
        med = self.overall_median_timing()
        frac = self.overall_frac_skill()
        n_skill = int((t["timing_percentile"] >= 95).sum())
        beat_m = self.frac_beat_matched()
        med_ret = float(t["agent_return"].median())

        lines = [
            "=" * 70,
            "  URTEIL - QUERSCHNITT-DQN (Breite statt Tiefe)",
            "=" * 70,
            f"  Symbole x Fenster bewertet        : {len(t)}",
            f"  Median Agent-Rendite (OOS)        : {med_ret:>8.2%}",
            f"  Anteil schlaegt konstante Position: {beat_m:>8.0%}",
            "",
            f"  Median Timing-Perzentil (Symbole) : {med:>8.0f}   (>= 95 noetig)",
            f"  Anteil Symbole mit Timing-Koennen : {frac:>8.0%}   "
            f"({n_skill} von {len(t)}; >= 50 % noetig)",
            "",
        ]
        if med >= 95 and frac >= 0.5 and beat_m >= 0.6:
            lines += [
                "  ERGEBNIS: NACHWEISBARES Timing-Koennen, quer ueber Symbole.",
                "",
                "  Das ist der Fall, den §G50 als 'einzige nicht ausgeschoepfte",
                "  Variante' offen gelassen hat. Bevor irgendetwas daraus folgt:",
                "    1. Mit anderem Seed und anderem Symbolsatz wiederholen.",
                "    2. pit.audit_feature_function auf den Merkmalen pruefen.",
                "    3. Auf einem unberuehrten Zeitraum (spaeter) gegenpruefen.",
                "    4. Survivorship-Abschlag (+2..+4 pp/Jahr, §G11) abziehen.",
            ]
        elif med >= 80 or frac >= 0.33:
            lines += [
                "  ERGEBNIS: schwacher Hinweis, NICHT belastbar.",
                "  Mit anderen Seeds und Symbolsaetzen wiederholen. Traegt der",
                "  Vorsprung ueber mehrere Laeufe, lohnt Weiterarbeit - sonst",
                "  ist es das uebliche Rauschen (SYRE-Lehre, §G50).",
            ]
        else:
            lines += [
                "  ERGEBNIS: KEIN nachweisbares Timing-Koennen - auch Breite",
                "  rettet es nicht.",
                "",
                "  Damit ist die Lernfrage auf funf Wegen negativ: GBM-Ranking",
                "  (§G15), 20-Achsen-Lernlauf (§G45), Spekulativ-Sweep (§G49),",
                "  Einzel-DQN (§G50) und jetzt Querschnitt-DQN. Der Engpass ist",
                "  das Signal-Rausch-Verhaeltnis (§G31/§G43), nicht das Modell.",
            ]
        return "\n".join(lines)


def _kalender(reihen: dict[str, tuple[pd.DataFrame, pd.Series]]) -> pd.DatetimeIndex:
    alle = set()
    for feats, _prices in reihen.values():
        alle |= set(feats.index)
    return pd.DatetimeIndex(sorted(alle))


def train_pooled_walk_forward(
    reihen: dict[str, tuple[pd.DataFrame, pd.Series]],
    *,
    n_folds: int = 3,
    episodes_per_symbol_per_fold: int = 5,
    min_train_frac: float = 0.45,
    min_train_bars: int = 300,
    min_test_bars: int = 30,
    env_config: EnvConfig | None = None,
    dqn_config: DQNConfig | None = None,
    n_random: int = 25,
    seed: int = 0,
    verbose: bool = True,
) -> PooledReport:
    """Trainiert EINEN Agenten ueber alle `reihen` walk-forward.

    Args:
        reihen: Symbol -> (Merkmale, Schlusskurse), volle Historie. Alle
            Merkmalsrahmen muessen dieselben Spalten in derselben
            Reihenfolge haben (gleicher `features.build_features`-Aufruf).
        min_train_frac: Anteil des gemeinsamen Kalenders, der vor dem
            ersten Bewertungsfenster liegt.

    Der Agent bleibt ueber die Fenster erhalten und lernt weiter; bewertet
    wird je Fenster nur auf Kalendertagen, die beim Training des Fensters
    noch in der Zukunft lagen.
    """
    env_cfg = env_config or EnvConfig()
    rng = np.random.default_rng(seed)

    kalender = _kalender(reihen)
    if len(kalender) < min_train_bars + n_folds * min_test_bars:
        raise ValueError(
            f"Gemeinsamer Kalender zu kurz: {len(kalender)} Tage.")

    grenzen_pos = np.linspace(
        int(len(kalender) * min_train_frac), len(kalender), n_folds + 1
    ).astype(int)
    grenzen = [kalender[min(p, len(kalender) - 1)] for p in grenzen_pos]

    report = PooledReport(n_symbols_total=len(reihen), n_folds=n_folds)
    agent: DQNAgent | None = None

    for k in range(n_folds):
        train_ende = grenzen[k]
        test_ende = grenzen[k + 1]

        # --- je Symbol die Fenster schneiden ---
        train_paare: dict[str, tuple[pd.DataFrame, pd.Series]] = {}
        test_paare: dict[str, tuple[pd.DataFrame, pd.Series]] = {}
        for sym, (feats, prices) in reihen.items():
            idx = feats.index.intersection(prices.index)
            f, p = feats.loc[idx], prices.loc[idx]
            f_tr, p_tr = f[f.index < train_ende], p[p.index < train_ende]
            maske_te = (f.index >= train_ende) & (f.index < test_ende)
            f_te, p_te = f[maske_te], p[maske_te]
            if len(f_tr) >= min_train_bars and len(f_te) >= min_test_bars:
                train_paare[sym] = (f_tr, p_tr)
                test_paare[sym] = (f_te, p_te)

        if not train_paare:
            continue

        # --- Standardisierung aus dem GEPOOLTEN Trainingsfenster ---
        pool = np.vstack([f.to_numpy(dtype=np.float64) for f, _ in train_paare.values()])
        scaler = (np.nanmean(pool, axis=0), np.nanstd(pool, axis=0))

        if agent is None:
            bsp_env = TradingEnv(*next(iter(train_paare.values())), env_cfg,
                                 feature_scaler=scaler)
            agent = DQNAgent(bsp_env.state_dim, bsp_env.n_actions, dqn_config)

        if verbose:
            print(f"\n[Fenster {k + 1}/{n_folds}] Training: {len(train_paare)} Symbole, "
                  f"{episodes_per_symbol_per_fold} Episoden je Symbol "
                  f"(Test {train_ende.date()} .. {test_ende.date()})")

        syms = list(train_paare)
        for ep in range(episodes_per_symbol_per_fold):
            rng.shuffle(syms)
            for sym in syms:
                env = TradingEnv(*train_paare[sym], env_cfg, feature_scaler=scaler)
                run_episode(env, lambda s, e: agent.act(s, greedy=False),
                            learn_agent=agent)
            if verbose:
                loss = np.mean(agent.losses[-500:]) if agent.losses else float("nan")
                print(f"    Runde {ep + 1}/{episodes_per_symbol_per_fold}: "
                      f"eps {agent.epsilon:.2f}  Verlust {loss:.4f}  "
                      f"Schritte {agent.steps:,}")

        # --- Auswertung je Symbol auf ungesehenen Daten ---
        n_skill_hier = 0
        rendite_agent, rendite_matched, schlaegt = [], [], 0
        timings = []
        for sym in test_paare:
            f_te, p_te = test_paare[sym]
            env = TradingEnv(f_te, p_te, env_cfg, feature_scaler=scaler)
            res = run_episode(env, lambda s, e: agent.act(s, greedy=True))
            frame = res["frame"]
            if frame.empty:
                continue
            avg_exp = float(frame["exposure"].mean())
            matched = constant_baseline(f_te, p_te, env_cfg, scaler, avg_exp)
            rand = random_baseline(f_te, p_te, env_cfg, scaler, n_random)
            pct_rand = float((rand < res["return"]).mean() * 100)
            tm = timing_skill_test(frame["exposure"], p_te.loc[frame.index])

            report.symbol_rows.append(PooledSymbolResult(
                fold=k + 1, symbol=sym,
                test_from=str(f_te.index[0].date()),
                test_to=str(f_te.index[-1].date()),
                agent_return=round(res["return"], 4),
                matched_constant_return=round(float(matched), 4),
                percentile_vs_random=round(pct_rand, 1),
                avg_exposure=round(avg_exp, 3),
                timing_percentile=round(float(tm["timing_percentile"]), 1),
                n_trades=res["n_trades"],
            ))
            timings.append(tm["timing_percentile"])
            rendite_agent.append(res["return"])
            rendite_matched.append(float(matched))
            if res["return"] > matched:
                schlaegt += 1
            if tm["timing_percentile"] >= 95:
                n_skill_hier += 1

        if timings:
            report.fold_summaries.append(PooledFoldSummary(
                fold=k + 1, n_symbols=len(timings),
                median_timing=round(float(np.median(timings)), 1),
                frac_timing_skill=round(n_skill_hier / len(timings), 3),
                median_agent_return=round(float(np.median(rendite_agent)), 4),
                median_matched_return=round(float(np.median(rendite_matched)), 4),
                frac_beat_matched=round(schlaegt / len(timings), 3),
            ))
            if verbose:
                s = report.fold_summaries[-1]
                print(f"  -> Fenster {k + 1}: Median Timing {s.median_timing:.0f}, "
                      f"{n_skill_hier}/{s.n_symbols} Symbole mit Koennen, "
                      f"schlaegt konstant {s.frac_beat_matched:.0%}")

    report.agent = agent
    return report
