"""Prognosemodell: LightGBM auf dem Faktorzoo - EIN Rechenweg fuer Labor und Bot.

Der Befund hinter diesem Modul (masterplan-2027 §6.8/§6.10, 2026-09-29):
Alles, was im Labor ueber SPY und Universum lag, hatte eine LightGBM-
Vorhersage im Score - der Handmix nicht. Damit die Engine denselben Score
bekommt, den das Labor gemessen hat, darf es nur EINE Merkmalsquelle
(`labor.faktorzoo`) und EINE Vorverarbeitung geben (Rang-Perzentile je
Tag ueber das zugelassene Universum, wie in scripts/23 `_lang`).

Was das Modul kann:
  * `merkmalstabelle(faktoren, maske, tage)` - Panels -> lange Tabelle
    (tag, symbol, merkmal_1..n), jedes Merkmal als Rangperzentil des Tages
  * `trainieren(...)`  - Modell auf allen Zeilen bis `bis - Embargo`
  * `speichern/laden`  - Booster + Metadaten (Merkmale, Horizont, Datum,
    Wichtigkeit) als zwei kleine Dateien im Repo (`models/`)
  * `score_panel(modell, faktoren, maske)` - Vorhersage je Tag und Symbol
    als breites Panel (fuer simulate.py und den Daemon)
  * `selftest()` - synthetisches Panel mit gepflanztem Signal: das Modell
    muss es OOS finden; ohne Signal darf es nichts finden

Was das Modul bewusst NICHT kann: unter dem Jahr nachtrainieren, Merkmale
ausserhalb des Zoos, Zielgroessen ausser der Rang-Vorwaertsrendite.
"""

from __future__ import annotations

import datetime as dt
import json
import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from .config import PROJECT_ROOT

MODELL_DIR = PROJECT_ROOT / "models"

LGBM_PARAMETER = dict(
    objective="regression", n_estimators=300, learning_rate=0.03, num_leaves=31,
    min_child_samples=200, subsample=0.7, subsample_freq=1, colsample_bytree=0.7,
    reg_lambda=5.0, verbose=-1, n_jobs=4,
)


def embargo_tage(horizont: int) -> int:
    """Kalendertage zwischen letzter Trainingszeile und erstem Testtag - die
    Zielgroesse der letzten Trainingszeilen muss realisiert sein."""
    return int((horizont + 5) * 1.5)


@dataclass
class Modell:
    booster: object                      # lightgbm.Booster
    merkmale: list[str]
    horizont: int
    trainiert_bis: str
    trainiert_am: str
    n_zeilen: int
    wichtigkeit: dict[str, float] = field(default_factory=dict)
    quelle: str = ""

    def vorhersagen(self, X: pd.DataFrame) -> np.ndarray:
        return self.booster.predict(X[self.merkmale].astype("float32"))

    def meta(self) -> dict:
        return {"merkmale": self.merkmale, "horizont": self.horizont,
                "trainiert_bis": self.trainiert_bis, "trainiert_am": self.trainiert_am,
                "n_zeilen": self.n_zeilen, "wichtigkeit": self.wichtigkeit, "quelle": self.quelle}


# ---------------------------------------------------------------------------
# Merkmale
# ---------------------------------------------------------------------------
def rangperzentile(faktoren: dict[str, pd.DataFrame], maske: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Jedes Merkmal als Rangperzentil je Tag ueber das zugelassene Universum."""
    return {n: f.where(maske).rank(axis=1, pct=True).astype("float32") for n, f in faktoren.items()}


def merkmalstabelle(faktoren: dict[str, pd.DataFrame], maske: pd.DataFrame,
                    tage: list | None = None, ziel: pd.DataFrame | None = None,
                    mindest_je_tag: int = 50) -> pd.DataFrame:
    """Breite Panels -> lange Tabelle (symbol, tag, merkmale..., [y])."""
    teile = rangperzentile(faktoren, maske)
    y = ziel.where(maske).rank(axis=1, pct=True).astype("float32") if ziel is not None else None
    if tage is None:
        tage = list(next(iter(teile.values())).index)
    frames = []
    for t in tage:
        zeile = pd.DataFrame({k: v.loc[t] for k, v in teile.items()})
        if y is not None:
            zeile["y"] = y.loc[t]
            zeile = zeile.dropna(subset=["y"])
        else:
            zeile = zeile[maske.loc[t].reindex(zeile.index).fillna(False).astype(bool)]
        zeile["tag"] = t
        if len(zeile) >= mindest_je_tag:
            frames.append(zeile)
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames)
    df.index.name = "symbol"
    return df.reset_index()


# ---------------------------------------------------------------------------
# Training / Speichern / Laden
# ---------------------------------------------------------------------------
def trainieren(lang: pd.DataFrame, merkmale: list[str], horizont: int, *,
               bis: str | pd.Timestamp | None = None, parameter: dict | None = None,
               quelle: str = "") -> Modell:
    """Trainiert auf allen Zeilen mit tag < bis - Embargo (bis=None: alle Zeilen)."""
    import lightgbm as lgb

    df = lang
    if bis is not None:
        grenze = pd.Timestamp(bis) - pd.Timedelta(days=embargo_tage(horizont))
        df = df[df["tag"] < grenze]
    if len(df) < 1_000:
        raise ValueError(f"zu wenig Trainingszeilen: {len(df)}")
    m = lgb.LGBMRegressor(**(parameter or LGBM_PARAMETER))
    m.fit(df[merkmale].astype("float32"), df["y"].astype("float32"))
    # Wichtigkeit nach GEWINN (Gain), nicht nach Anzahl der Splits: Rauschen bekommt
    # viele kleine Splits, Signal wenige grosse.
    gain = m.booster_.feature_importance(importance_type="gain")
    wicht = {k: float(v) / max(1.0, float(sum(gain))) for k, v in zip(merkmale, gain)}
    return Modell(booster=m.booster_, merkmale=list(merkmale), horizont=horizont,
                  trainiert_bis=str(pd.Timestamp(df["tag"].max()).date()),
                  trainiert_am=dt.date.today().isoformat(), n_zeilen=int(len(df)),
                  wichtigkeit=wicht, quelle=quelle)


def speichern(modell: Modell, name: str, verzeichnis: Path | None = None) -> Path:
    d = Path(verzeichnis or MODELL_DIR)
    d.mkdir(parents=True, exist_ok=True)
    pfad = d / f"{name}.txt"
    modell.booster.save_model(str(pfad))
    (d / f"{name}.json").write_text(json.dumps(modell.meta(), ensure_ascii=False, indent=1), encoding="utf-8")
    return pfad


def laden(name: str, verzeichnis: Path | None = None) -> Modell:
    import lightgbm as lgb

    d = Path(verzeichnis or MODELL_DIR)
    meta = json.loads((d / f"{name}.json").read_text(encoding="utf-8"))
    booster = lgb.Booster(model_file=str(d / f"{name}.txt"))
    return Modell(booster=booster, merkmale=meta["merkmale"], horizont=int(meta["horizont"]),
                  trainiert_bis=meta["trainiert_bis"], trainiert_am=meta["trainiert_am"],
                  n_zeilen=int(meta["n_zeilen"]), wichtigkeit=meta.get("wichtigkeit", {}),
                  quelle=meta.get("quelle", ""))


def neuestes(praefix: str = "lgbm_h21", verzeichnis: Path | None = None) -> str | None:
    """Name des juengsten gespeicherten Modells mit diesem Praefix (nach Dateiname)."""
    d = Path(verzeichnis or MODELL_DIR)
    kandidaten = sorted(p.stem for p in d.glob(f"{praefix}_*.json")) if d.exists() else []
    return kandidaten[-1] if kandidaten else None


# ---------------------------------------------------------------------------
# Anwendung
# ---------------------------------------------------------------------------
def score_panel(modell: Modell, faktoren: dict[str, pd.DataFrame], maske: pd.DataFrame,
                tage: list | None = None) -> pd.DataFrame:
    """Vorhersage je Tag (Zeilen) und Symbol (Spalten) - NaN, wo nicht zugelassen."""
    fehlend = [m for m in modell.merkmale if m not in faktoren]
    if fehlend:
        raise ValueError(f"Merkmale fehlen im Faktorzoo: {fehlend}")
    lang = merkmalstabelle({m: faktoren[m] for m in modell.merkmale}, maske, tage=tage)
    if lang.empty:
        return pd.DataFrame(index=maske.index if tage is None else tage, columns=maske.columns, dtype="float32")
    lang["pred"] = modell.vorhersagen(lang)   # NaN bleibt NaN - LightGBM kennt fehlende Werte, wie im Training
    return lang.pivot(index="tag", columns="symbol", values="pred").reindex(columns=maske.columns)


def _naiv_normiert(idx) -> pd.DatetimeIndex:
    idx = pd.DatetimeIndex(idx)
    if idx.tz is not None:
        idx = idx.tz_convert("UTC").tz_localize(None)
    return idx.normalize()


def signale_fuer_snapshot(bars: dict[str, pd.DataFrame], market: pd.Series | None, modell: Modell,
                          weights=None, *, min_preis: float = 5.0, min_dollar_volume: float = 25_000_000,
                          ) -> dict[str, pd.DataFrame]:
    """Live-Weg der Score-Quelle 'ml' - EIN Rechenweg mit dem Labor.

    Dieselben Merkmale (`labor.faktorzoo`), dieselbe Vorverarbeitung
    (Rangperzentile ueber das zugelassene Universum des Tages), Vorhersage
    nur fuer den letzten vollstaendigen Tag, angehaengt als Spalte
    `ml_score` an die gewohnten Ranking-Signale. Alle anderen Tage bleiben
    NaN - die Engine liest ohnehin nur die letzte Zeile.
    """
    from . import labor
    from .signals import RankingWeights, build_ranking_frame

    weights = weights or RankingWeights()
    frames = {sym: build_ranking_frame(df, market, weights) for sym, df in bars.items()}
    felder = ("open", "high", "low", "close", "volume")
    lang = pd.concat({sym: df[[c for c in felder if c in df.columns]] for sym, df in bars.items()},
                     names=["symbol", "timestamp"])
    panel = labor.panel_aus_multiindex(lang, quelle="live")
    for f in felder:
        m = getattr(panel, f, None)
        if m is not None:
            m.index = _naiv_normiert(m.index)
    spy = None
    if market is not None:
        spy = pd.Series(np.asarray(market, dtype=float), index=_naiv_normiert(market.index))
        spy = spy[~spy.index.duplicated()].reindex(panel.close.index).ffill()
    faktoren = labor.faktorzoo(panel, spy=spy)
    maske = labor.liquides_universum(panel, min_preis=min_preis, min_dollar_volume=min_dollar_volume)
    letzter = panel.close.index[-1]
    scores = score_panel(modell, faktoren, maske, tage=[letzter])
    for sym, fr in frames.items():
        fr["ml_score"] = np.nan
        if fr.empty or sym not in scores.columns:
            continue
        if _naiv_normiert(fr.index[-1:])[0] == letzter:
            fr.iloc[-1, fr.columns.get_loc("ml_score")] = float(scores.loc[letzter, sym])
    return frames


# ---------------------------------------------------------------------------
# Selbsttest
# ---------------------------------------------------------------------------
def _synthetisches_panel(n_sym: int = 120, n_tage: int = 900, signal: float = 0.0, seed: int = 7):
    """Zufallskurse; mit `signal` > 0 tragen zwei Merkmale Information ueber die
    Vorwaertsrendite (zusaetzlicher Drift proportional zum Merkmal)."""
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2015-01-01", periods=n_tage)
    syms = [f"S{i:03d}" for i in range(n_sym)]
    m1 = pd.DataFrame(rng.standard_normal((n_tage, n_sym)), index=idx, columns=syms).rolling(5).mean()
    m2 = pd.DataFrame(rng.standard_normal((n_tage, n_sym)), index=idx, columns=syms).rolling(5).mean()
    rausch = pd.DataFrame(rng.standard_normal((n_tage, n_sym)), index=idx, columns=syms).rolling(5).mean()
    eps = rng.standard_normal((n_tage, n_sym)) * 0.02
    # Rendite von t nach t+1 haengt vom Merkmal am Tag t ab
    r = pd.DataFrame(eps, index=idx, columns=syms) + signal * (m1.shift(1).fillna(0) - m2.shift(1).fillna(0) * 0.5)
    close = 100 * (1 + r).cumprod()
    fwd = close.shift(-6) / close.shift(-1) - 1     # Einstieg t+1, 5 Tage halten
    maske = pd.DataFrame(True, index=idx, columns=syms)
    return {"m1": m1, "m2": m2, "rausch": rausch}, fwd, maske


def selftest(leise: bool = False) -> bool:
    import tempfile

    ok = True

    def check(label, cond):
        nonlocal ok
        if not leise or not cond:
            print(f"  {'OK ' if cond else 'FEHLER'} {label}")
        ok &= bool(cond)

    fak, fwd, maske = _synthetisches_panel(signal=0.02)
    lang = merkmalstabelle(fak, maske, ziel=fwd)
    check("Merkmalstabelle: Rangperzentile in (0,1], jede Zeile ein Symbol-Tag",
          lang[["m1", "m2", "rausch"]].max().max() <= 1.0 and lang["y"].min() > 0
          and lang.groupby("tag").size().min() >= 50)
    bis = pd.Timestamp("2017-07-01")
    schnell = {**LGBM_PARAMETER, "n_estimators": 80}     # Selbsttest: schnell, nicht schoen
    modell = trainieren(lang, ["m1", "m2", "rausch"], horizont=5, bis=bis, quelle="selftest", parameter=schnell)
    check("Embargo: letzte Trainingszeile liegt >= Embargo vor 'bis'",
          pd.Timestamp(modell.trainiert_bis) <= bis - pd.Timedelta(days=embargo_tage(5)))
    test = lang[lang["tag"] >= bis].copy()
    test["pred"] = modell.vorhersagen(test)
    ic = test.groupby("tag").apply(lambda g: g["pred"].corr(g["y"], method="spearman")).mean()
    check(f"Gepflanztes Signal wird OOS gefunden (IC {ic:+.3f} > 0,05)", ic > 0.05)
    check("Wichtigkeit: Signalmerkmale > Rauschen",
          modell.wichtigkeit["m1"] > modell.wichtigkeit["rausch"])
    fak0, fwd0, maske0 = _synthetisches_panel(signal=0.0, seed=11)
    lang0 = merkmalstabelle(fak0, maske0, ziel=fwd0)
    m0 = trainieren(lang0, ["m1", "m2", "rausch"], horizont=5, bis=bis, parameter=schnell)
    t0 = lang0[lang0["tag"] >= bis].copy()
    t0["pred"] = m0.vorhersagen(t0)
    ic0 = t0.groupby("tag").apply(lambda g: g["pred"].corr(g["y"], method="spearman")).mean()
    check(f"Ohne Signal kein Fund (IC {ic0:+.3f} in [-0,03, 0,03])", abs(ic0) < 0.03)
    with tempfile.TemporaryDirectory() as tmp:
        speichern(modell, "lgbm_h5_2017-07-01", Path(tmp))
        wieder = laden("lgbm_h5_2017-07-01", Path(tmp))
        p1 = modell.vorhersagen(test.head(200)); p2 = wieder.vorhersagen(test.head(200))
        check("Speichern/Laden liefert identische Vorhersagen", np.allclose(p1, p2))
        check("neuestes() findet das Modell", neuestes("lgbm_h5", Path(tmp)) == "lgbm_h5_2017-07-01")
    sp = score_panel(modell, fak, maske, tage=list(maske.index[-3:]))
    check("score_panel: Panel Tag x Symbol, alle zugelassenen Symbole bewertet",
          sp.shape == (3, maske.shape[1]) and sp.notna().all().all())
    if not leise:
        print(f"  Selbsttest {'bestanden' if ok else 'FEHLGESCHLAGEN'}")
    return ok


if __name__ == "__main__":
    import sys
    sys.exit(0 if selftest() else 1)
