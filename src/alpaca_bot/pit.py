"""Point-in-Time-Waechter: findet Lookahead-Lecks, statt vor ihnen zu warnen.

Das ist das wichtigste Modul im Projekt. Ein Backtest auf undichten Daten
ist nicht ein bisschen zu optimistisch - er ist vollstaendig wertlos, und
zwar auf eine Art, die sich gut anfuehlt. Genau deshalb faellt sie nicht auf.

Drei Werkzeuge:

1. `audit_feature_function()` - der mechanische Leck-Test.
   Baut die Features einmal auf der vollen Historie und einmal auf einer
   bei T abgeschnittenen Kopie. Beide muessen bis T Zeichen fuer Zeichen
   identisch sein. Sind sie es nicht, benutzt die Funktion Zukunftsdaten.
   Dieser Test findet Lecks, die beim Lesen des Codes unsichtbar sind.

2. `asof_join()` - Zusammenfuehren von Ereignissen mit Kursen unter
   Zwangsverzoegerung. Verhindert die haeufigste Falle bei News-Daten.

3. `Envelope` - das Drei-Umschlag-Protokoll aus der Strategie-Analyse,
   als Code. Der Tresor-Zeitraum protokolliert jeden Zugriff.

Typische Lecks, die Test 1 findet und ein Code-Review nicht:
  * StandardScaler auf dem gesamten Datensatz gefittet
  * `.rank(pct=True)` oder `.mean()` ueber die volle Historie
  * `bfill()` statt `ffill()`
  * `df.dropna()` VOR dem zeitlichen Split
  * Fundamentaldaten am Quartalsende statt am Einreichungsdatum
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Callable, Sequence

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Verfuegbarkeitsregeln: wann wusste man etwas WIRKLICH?
# ---------------------------------------------------------------------------
AVAILABILITY_DELAY: dict[str, pd.Timedelta] = {
    # News tragen den Veroeffentlichungszeitpunkt. Eine Meldung um 15:47 darf
    # fruehestens auf den naechsten handelbaren Kurs wirken - nicht auf den
    # Tagesschluss, denn dazwischen liegt keine Handelsmoeglichkeit fuer dich.
    "news": pd.Timedelta("1D"),
    # Quartalszahlen: Einreichung bei der SEC, nicht Quartalsende. 10-Q kommt
    # 40 Tage, 10-K bis 90 Tage nach Periodenende.
    "fundamentals": pd.Timedelta("90D"),
    # Insider-Meldungen: Form 4 muss binnen 2 Werktagen eingereicht werden.
    "insider": pd.Timedelta("2D"),
    # 13F-Fondspositionen: 45 Tage nach Quartalsende.
    "institutional": pd.Timedelta("45D"),
    # Makro-Erstveroeffentlichung, danach oft revidiert (siehe ALFRED).
    "macro": pd.Timedelta("30D"),
    # Kursdaten sind sofort verfuegbar - aber der Basic-Plan haelt die
    # letzten 15 Minuten zurueck.
    "prices": pd.Timedelta("0s"),
}


class LookaheadError(AssertionError):
    """Ein Feature hat Zugriff auf Daten aus der Zukunft."""


# ---------------------------------------------------------------------------
# 1. Der mechanische Leck-Test
# ---------------------------------------------------------------------------
@dataclass
class AuditResult:
    clean: bool
    n_checks: int
    leaking_columns: dict[str, float] = field(default_factory=dict)
    """Spalte -> groesste beobachtete Abweichung."""
    cut_points: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        if self.clean:
            return (f"[SAUBER] {self.n_checks} Abschneidepunkte geprueft, "
                    f"keine Zukunftsabhaengigkeit gefunden.")
        lines = [f"[LECK] {len(self.leaking_columns)} Spalte(n) benutzen Zukunftsdaten:"]
        for col, diff in sorted(
            self.leaking_columns.items(), key=lambda kv: -kv[1]
        )[:15]:
            lines.append(f"    {col:<28} max. Abweichung {diff:.3e}")
        lines.append("  Diese Features sind unbrauchbar, bis das behoben ist.")
        return "\n".join(lines)

    def raise_if_leaking(self) -> None:
        if not self.clean:
            raise LookaheadError(str(self))


def audit_feature_function(
    build_fn: Callable[[pd.DataFrame], pd.DataFrame],
    df: pd.DataFrame,
    *,
    n_checks: int = 5,
    tol: float = 1e-8,
    min_fraction: float = 0.4,
) -> AuditResult:
    """Prueft, ob `build_fn` ausschliesslich Vergangenheitsdaten benutzt.

    Verfahren: Features einmal auf allen Daten berechnen, einmal auf der
    bei T abgeschnittenen Kopie. Bis T muessen beide identisch sein.

        result = audit_feature_function(features.build_features, df)
        result.raise_if_leaking()

    Args:
        build_fn: Funktion DataFrame -> DataFrame mit gleichem Index.
        n_checks: Anzahl der Abschneidepunkte.
        tol: erlaubte numerische Abweichung (Gleitkomma-Rauschen).
        min_fraction: frühester Abschneidepunkt als Anteil der Historie.
    """
    full = build_fn(df)
    numeric = full.select_dtypes(include=[np.number]).columns
    leaks: dict[str, float] = {}
    cuts: list[str] = []

    positions = np.linspace(min_fraction, 0.95, n_checks)
    for frac in positions:
        cut = int(len(df) * frac)
        if cut < 30:
            continue
        t = df.index[cut - 1]
        cuts.append(str(t))

        truncated = build_fn(df.iloc[:cut])
        common_idx = full.index[:cut].intersection(truncated.index)
        if len(common_idx) == 0:
            continue

        for col in numeric:
            if col not in truncated.columns:
                continue
            a = pd.to_numeric(full.loc[common_idx, col], errors="coerce")
            b = pd.to_numeric(truncated.loc[common_idx, col], errors="coerce")
            # NaN an derselben Stelle ist kein Unterschied.
            both_nan = a.isna() & b.isna()
            diff = (a - b).abs().where(~both_nan, 0.0)
            # NaN nur auf einer Seite = echter Unterschied.
            diff = diff.where(a.isna() == b.isna(), np.inf)
            worst = float(np.nanmax(diff.to_numpy())) if len(diff) else 0.0
            if worst > tol:
                leaks[col] = max(leaks.get(col, 0.0), worst)

    return AuditResult(
        clean=not leaks, n_checks=len(cuts), leaking_columns=leaks, cut_points=cuts
    )


def audit_labels(y: pd.Series, horizon: int) -> str:
    """Erinnert daran, dass Labels per Definition in die Zukunft schauen.

    Das ist erlaubt und noetig - aber es erzwingt ein Embargo von
    `horizon` Bars zwischen Trainings- und Testfenster.
    """
    n_future = int(y.notna().sum())
    return (
        f"Label mit Horizont {horizon}: die letzten {horizon} Bars koennen kein "
        f"Label haben ({n_future} verwendbar). Embargo >= {horizon} Bars ist "
        f"Pflicht - sonst ueberlappen Trainings- und Testlabels."
    )


# ---------------------------------------------------------------------------
# 2. Zeitpunktsicheres Zusammenfuehren
# ---------------------------------------------------------------------------
def available_at(
    timestamps: pd.Series | pd.DatetimeIndex, kind: str = "news"
) -> pd.DatetimeIndex:
    """Wann ist eine Information handelbar verfuegbar? Zeitstempel + Verzoegerung."""
    if kind not in AVAILABILITY_DELAY:
        raise KeyError(
            f"Unbekannte Datenart {kind!r}. Bekannt: {', '.join(AVAILABILITY_DELAY)}"
        )
    idx = pd.DatetimeIndex(timestamps)
    if idx.tz is None:
        idx = idx.tz_localize("UTC")
    return idx + AVAILABILITY_DELAY[kind]


def asof_join(
    prices: pd.DataFrame,
    events: pd.DataFrame,
    *,
    kind: str = "news",
    event_time_col: str = "timestamp",
    extra_delay: pd.Timedelta | None = None,
    tolerance: pd.Timedelta | None = pd.Timedelta("30D"),
) -> pd.DataFrame:
    """Fuehrt Ereignisdaten an Kursdaten - nur mit dem, was damals bekannt war.

    Jedem Ereignis wird die Verfuegbarkeitsverzoegerung seiner Datenart
    aufgeschlagen, danach wird rueckwaerts gejoint. Ein Ereignis von heute
    14:00 landet damit nie auf einer Kursbar von heute 09:30.
    """
    if events.empty:
        return prices.copy()

    ev = events.copy()
    ev["_available"] = available_at(ev[event_time_col], kind)
    if extra_delay is not None:
        ev["_available"] = ev["_available"] + extra_delay
    ev = ev.sort_values("_available")

    px = prices.copy()
    px_idx = pd.DatetimeIndex(px.index)
    if px_idx.tz is None:
        px_idx = px_idx.tz_localize("UTC")
    px["_time"] = px_idx
    px = px.sort_values("_time")

    merged = pd.merge_asof(
        px,
        ev.drop(columns=[event_time_col]),
        left_on="_time",
        right_on="_available",
        direction="backward",
        tolerance=tolerance,
    )
    merged.index = prices.index
    return merged.drop(columns=["_time", "_available"], errors="ignore")


def assert_no_future_events(
    events: pd.DataFrame, as_of: dt.datetime | pd.Timestamp, time_col: str = "timestamp"
) -> None:
    """Harte Zusicherung: kein Ereignis liegt nach dem Stichtag."""
    ts = pd.DatetimeIndex(events[time_col])
    if ts.tz is None:
        ts = ts.tz_localize("UTC")
    cutoff = pd.Timestamp(as_of)
    if cutoff.tz is None:
        cutoff = cutoff.tz_localize("UTC")
    future = ts > cutoff
    if future.any():
        raise LookaheadError(
            f"{int(future.sum())} von {len(ts)} Ereignissen liegen nach dem "
            f"Stichtag {cutoff}. Spaetestes: {ts.max()}"
        )


# ---------------------------------------------------------------------------
# 3. Das Drei-Umschlag-Protokoll
# ---------------------------------------------------------------------------
@dataclass
class Envelope:
    """Teilt die Historie in Entwicklung / Validierung / Tresor.

        env = Envelope()
        train = env.development(df)     # beliebig oft
        val   = env.validation(df)      # zum ehrlichen Pruefen
        test  = env.vault(df)           # EINMAL, ganz am Ende
    """

    dev_end: str = "2021-12-31"
    val_end: str = "2024-12-31"
    _vault_opened: int = 0

    def development(self, df: pd.DataFrame) -> pd.DataFrame:
        return df.loc[: self.dev_end]

    def validation(self, df: pd.DataFrame) -> pd.DataFrame:
        return df.loc[self.dev_end : self.val_end]

    def vault(self, df: pd.DataFrame, confirm: bool = False) -> pd.DataFrame:
        """Der Tresor. Jeder Zugriff wird gezaehlt und gemeldet."""
        self._vault_opened += 1
        if not confirm:
            raise PermissionError(
                "Der Tresor-Zeitraum wird nur EINMAL geoeffnet, ganz am Ende.\n"
                "Wenn du wirklich fertig bist: vault(df, confirm=True).\n"
                "Ist das Ergebnis schlecht, ist die Idee tot - nicht nachjustieren."
            )
        if self._vault_opened > 1:
            print(
                f"  [WARNUNG] Tresor zum {self._vault_opened}. Mal geoeffnet. "
                "Ab jetzt ist dieser Zeitraum kein unabhaengiger Test mehr - "
                "jedes Ergebnis daraus ist optimistisch verzerrt."
            )
        return df.loc[self.val_end :]

    def describe(self, df: pd.DataFrame) -> str:
        """Uebersicht, ohne den Tresor dabei zu oeffnen."""
        n_vault = len(df.loc[self.val_end :])
        return (
            f"Entwicklung : {len(self.development(df)):>6} Bars bis {self.dev_end}\n"
            f"Validierung : {len(self.validation(df)):>6} Bars bis {self.val_end}\n"
            f"Tresor      : {n_vault:>6} Bars ab {self.val_end}  "
            f"(bisher {self._vault_opened}x geoeffnet)"
        )


# ---------------------------------------------------------------------------
# 4. Negativ-Tests: das System muss beweisen, dass es NICHTS findet
# ---------------------------------------------------------------------------
def shuffle_test(
    X: pd.DataFrame,
    y: pd.Series,
    fit_predict: Callable[[pd.DataFrame, pd.Series], pd.Series],
    n_rounds: int = 5,
    seed: int = 0,
) -> dict:
    """Mischt die Labels und prueft, dass das Modell danach nichts findet.

    Findet es trotzdem etwas, stimmt die Pipeline nicht - dann korreliert
    irgendwo eine Hilfsspalte mit der Zeit oder mit dem Ziel.
    """
    rng = np.random.default_rng(seed)
    scores = []
    for _ in range(n_rounds):
        y_shuffled = pd.Series(
            rng.permutation(y.to_numpy()), index=y.index, name=y.name
        )
        preds = fit_predict(X, y_shuffled)
        common = preds.dropna().index.intersection(y_shuffled.index)
        if len(common) < 10:
            continue
        ic = float(
            pd.Series(preds.loc[common]).corr(
                pd.Series(y_shuffled.loc[common]), method="spearman"
            )
        )
        scores.append(ic)
    arr = np.array(scores, dtype=float)
    if not len(arr):
        return {"mean_ic": float("nan"), "passed": False, "rounds": 0,
                "max_abs_ic": float("nan"), "threshold": float("nan"), "n": 0}

    # Geprueft wird der MITTELWERT, nicht das Maximum.
    #
    # Bei sauberer Pipeline streuen die IC-Werte gemischter Labels um null
    # mit Standardfehler ~1/sqrt(n). Das Maximum aus k Runden ist aber kein
    # mittelwertfreier Wert - sein Erwartungswert liegt bei k=5 schon bei
    # rund 1,8 Standardfehlern. Wer das Maximum gegen eine Sigma-Schwelle
    # prueft, meldet deshalb staendig Lecks, die keine sind.
    n = max(10, len(y))
    k = len(arr)
    se = 1.0 / np.sqrt(n) / np.sqrt(k)
    threshold = 3.0 * se
    mean_ic = float(np.nanmean(arr))

    return {
        "mean_ic": mean_ic,
        "max_abs_ic": float(np.nanmax(np.abs(arr))),
        "threshold": float(threshold),
        "std_error": float(se),
        "n": int(n),
        "rounds": k,
        "passed": bool(abs(mean_ic) < threshold),
    }


def information_coefficient(
    predictions: pd.Series, forward_returns: pd.Series, method: str = "spearman"
) -> float:
    """IC = Rangkorrelation zwischen Prognose und tatsaechlicher Rendite.

    Einordnung: 0,02-0,05 ist ein echtes, nutzbares Signal. Ueber 0,15
    auf Tagesdaten ist praktisch immer ein Leck.
    """
    common = predictions.dropna().index.intersection(forward_returns.dropna().index)
    if len(common) < 10:
        return float("nan")
    return float(
        predictions.loc[common].corr(forward_returns.loc[common], method=method)
    )


def required_sample_size(
    edge: float = 0.05, base_rate: float = 0.5, alpha: float = 0.05, power: float = 0.8
) -> int:
    """Wie viele UNABHAENGIGE Beobachtungen braucht der Nachweis eines Vorsprungs?

        required_sample_size(0.05)  ->  ~610   (55 % gegen 50 %)
        required_sample_size(0.02)  -> ~3900   (52 % gegen 50 %)

    Achtung: unabhaengig. 1000 Trades derselben Woche ueber korrelierte
    Aktien sind statistisch EINE Beobachtung, nicht 1000.
    """
    z_alpha = _norm_ppf(1 - alpha)
    z_beta = _norm_ppf(power)
    p = base_rate + edge
    return int(np.ceil((z_alpha + z_beta) ** 2 * p * (1 - p) / edge**2))


def _norm_ppf(q: float) -> float:
    """Quantil der Standardnormalverteilung (Acklam-Approximation).

    Eigene Implementierung, damit scipy keine Pflichtabhaengigkeit wird.
    """
    a = [-3.969683028665376e01, 2.209460984245205e02, -2.759285104469687e02,
         1.383577518672690e02, -3.066479806614716e01, 2.506628277459239e00]
    b = [-5.447609879822406e01, 1.615858368580409e02, -1.556989798598866e02,
         6.680131188771972e01, -1.328068155288572e01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e00,
         -2.549732539343734e00, 4.374664141464968e00, 2.938163982698783e00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e00,
         3.754408661907416e00]
    p_low, p_high = 0.02425, 1 - 0.02425
    if q < p_low:
        s = np.sqrt(-2 * np.log(q))
        return (((((c[0] * s + c[1]) * s + c[2]) * s + c[3]) * s + c[4]) * s + c[5]) / (
            (((d[0] * s + d[1]) * s + d[2]) * s + d[3]) * s + 1
        )
    if q > p_high:
        s = np.sqrt(-2 * np.log(1 - q))
        return -(((((c[0] * s + c[1]) * s + c[2]) * s + c[3]) * s + c[4]) * s + c[5]) / (
            (((d[0] * s + d[1]) * s + d[2]) * s + d[3]) * s + 1
        )
    s = q - 0.5
    r = s * s
    return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * s / (
        ((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1
    )
