"""Machine Learning auf Zeitreihen - mit Walk-Forward statt naiver CV.

Der haeufigste Anfaengerfehler: `train_test_split(shuffle=True)`. Damit
trainiert das Modell auf Daten von Freitag und wird auf Mittwoch
getestet - es "kennt" die Zukunft. Ergebnis: 85 % Trefferquote im Test,
Verlust im echten Handel.

Hier wird deshalb konsequent walk-forward validiert:

    |== Train ==|--Embargo--|== Test ==|
    |======= Train =========|--Embargo--|== Test ==|
    |============ Train ============|--Embargo--|== Test ==|

Das Embargo ist noetig, weil ein Label mit Horizont h die naechsten h
Bars mitbenutzt. Ohne Embargo sickert genau dieses Wissen ins Training.

Realistische Erwartung: 52-55 % Trefferquote out-of-sample ist bei
Tagesdaten schon gut. Alles ueber 60 % bedeutet fast immer, dass sich
irgendwo ein Leck eingeschlichen hat - dann zuerst den Code pruefen,
nicht das Modell feiern.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import accuracy_score, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


def _label(value) -> str:
    """Index-Eintrag lesbar machen - egal ob Datum oder laufende Nummer.

    Die Ereignisstudie uebergibt einen nummerierten Index (ein Fall je
    Ereignis), Zeitreihen einen DatetimeIndex. Beides muss funktionieren.
    """
    date_fn = getattr(value, "date", None)
    return str(date_fn()) if callable(date_fn) else str(value)


def make_model(kind: str = "gbm", **kwargs):
    """Modell-Fabrik.

    'gbm'    - Gradient Boosting: erste Wahl fuer tabellarische Daten.
    'rf'     - Random Forest: robust, schwerer zu ueberanpassen.
    'logreg' - lineare Basislinie. Wenn GBM sie nicht schlaegt, gibt es
               vermutlich kein nichtlineares Signal zu finden.
    'ridge'  - lineare Regression fuer Rendite-Vorhersage.
    """
    if kind == "gbm":
        return HistGradientBoostingClassifier(
            max_depth=kwargs.pop("max_depth", 3),
            learning_rate=kwargs.pop("learning_rate", 0.05),
            max_iter=kwargs.pop("max_iter", 200),
            l2_regularization=kwargs.pop("l2_regularization", 1.0),
            random_state=42,
            **kwargs,
        )
    if kind == "rf":
        return RandomForestClassifier(
            n_estimators=kwargs.pop("n_estimators", 300),
            max_depth=kwargs.pop("max_depth", 5),
            min_samples_leaf=kwargs.pop("min_samples_leaf", 50),
            n_jobs=-1,
            random_state=42,
            **kwargs,
        )
    if kind == "logreg":
        return make_pipeline(
            StandardScaler(),
            LogisticRegression(max_iter=1000, C=kwargs.pop("C", 0.1), **kwargs),
        )
    if kind == "ridge":
        return make_pipeline(StandardScaler(), Ridge(alpha=kwargs.pop("alpha", 1.0)))
    raise ValueError(f"Unbekannter Modelltyp: {kind}")


@dataclass
class WalkForwardResult:
    predictions: pd.Series
    """Out-of-sample Wahrscheinlichkeit fuer 'steigt' (bzw. Vorhersagewert)."""
    actual: pd.Series
    fold_scores: pd.DataFrame
    model: object
    """Auf ALLEN Daten neu trainiertes Modell - fuer den Live-Einsatz."""
    feature_names: list[str]

    @property
    def accuracy(self) -> float:
        p = (self.predictions > 0.5).astype(int)
        return float(accuracy_score(self.actual.loc[p.index], p))

    @property
    def auc(self) -> float:
        try:
            return float(roc_auc_score(self.actual.loc[self.predictions.index],
                                       self.predictions))
        except ValueError:
            return float("nan")

    def summary(self) -> str:
        return (
            f"Walk-Forward ueber {len(self.fold_scores)} Folds\n"
            f"  Out-of-Sample Accuracy : {self.accuracy:.3f}\n"
            f"  Out-of-Sample AUC      : {self.auc:.3f}   (0.5 = Zufall)\n"
            f"  Vorhersagen            : {len(self.predictions)}\n"
            f"  Basisrate (Anteil 'steigt'): "
            f"{self.actual.loc[self.predictions.index].mean():.3f}"
        )


def walk_forward_predict(
    X: pd.DataFrame,
    y: pd.Series,
    model_kind: str = "gbm",
    *,
    n_splits: int = 5,
    embargo: int = 5,
    min_train: int = 250,
    **model_kwargs,
) -> WalkForwardResult:
    """Erzeugt ehrliche Out-of-Sample-Vorhersagen ueber die ganze Historie.

    Args:
        embargo: Anzahl Bars, die zwischen Trainings- und Testfenster
            verworfen werden. Muss >= dem Label-Horizont sein.
    """
    X, y = X.align(y, join="inner", axis=0)
    n = len(X)
    if n < min_train + n_splits * 20:
        raise ValueError(
            f"Zu wenig Daten: {n} Zeilen. Mehr Historie laden oder "
            f"n_splits/min_train reduzieren."
        )

    test_total = n - min_train
    fold = test_total // n_splits
    preds = pd.Series(np.nan, index=X.index, dtype=float)
    rows = []

    for i in range(n_splits):
        test_start = min_train + i * fold
        test_end = n if i == n_splits - 1 else test_start + fold
        train_end = max(0, test_start - embargo)
        if train_end < 50:
            continue

        X_tr, y_tr = X.iloc[:train_end], y.iloc[:train_end]
        X_te, y_te = X.iloc[test_start:test_end], y.iloc[test_start:test_end]
        if y_tr.nunique() < 2 or len(X_te) == 0:
            continue

        m = make_model(model_kind, **model_kwargs)
        m.fit(X_tr, y_tr)

        if hasattr(m, "predict_proba"):
            p = m.predict_proba(X_te)[:, 1]
        else:
            p = m.predict(X_te)
        preds.iloc[test_start:test_end] = p

        acc = accuracy_score(y_te, (p > 0.5).astype(int)) if y_te.nunique() > 0 else np.nan
        try:
            auc = roc_auc_score(y_te, p)
        except ValueError:
            auc = np.nan
        rows.append(
            {
                "fold": i + 1,
                "train_bis": _label(X.index[train_end - 1]),
                "test_von": _label(X.index[test_start]),
                "test_bis": _label(X.index[test_end - 1]),
                "n_train": train_end,
                "n_test": len(X_te),
                "accuracy": acc,
                "auc": auc,
            }
        )

    final = make_model(model_kind, **model_kwargs)
    final.fit(X, y)

    return WalkForwardResult(
        predictions=preds.dropna(),
        actual=y,
        fold_scores=pd.DataFrame(rows),
        model=final,
        feature_names=list(X.columns),
    )


def feature_importance(
    result: WalkForwardResult, X: pd.DataFrame, y: pd.Series, n_repeats: int = 5
) -> pd.DataFrame:
    """Permutations-Wichtigkeit: wie stark faellt die Guete, wenn ein
    Feature zufaellig gemischt wird? Aussagekraeftiger als die eingebaute
    `feature_importances_`, die korrelierte Features ueberbewertet."""
    X, y = X.align(y, join="inner", axis=0)
    r = permutation_importance(
        result.model, X, y, n_repeats=n_repeats, random_state=42, n_jobs=-1
    )
    return (
        pd.DataFrame(
            {"feature": X.columns, "wichtigkeit": r.importances_mean,
             "std": r.importances_std}
        )
        .sort_values("wichtigkeit", ascending=False)
        .reset_index(drop=True)
    )


def signal_from_predictions(
    preds: pd.Series,
    long_threshold: float = 0.55,
    short_threshold: float | None = None,
    scale_by_confidence: bool = False,
) -> pd.Series:
    """Wahrscheinlichkeiten -> Zielposition fuer den Backtest.

    Die Schwelle ist bewusst > 0.5: nur handeln, wenn das Modell
    deutlich ueberzeugt ist. Das reduziert Trades und damit Kosten.
    """
    if scale_by_confidence:
        # 0.5 -> 0 Position, 1.0 -> volle Position
        sig = ((preds - 0.5) * 2).clip(lower=0.0)
        return sig.where(preds > long_threshold, 0.0)

    sig = (preds > long_threshold).astype(float)
    if short_threshold is not None:
        sig = sig - (preds < short_threshold).astype(float)
    return sig
