"""Der spekulative Historienlauf: maximales Risiko, maximaler Umschlag.

WOZU. Alle bisherigen Versuche (BEFUNDE §B6, 0 von rund 68) haben an den
Randbedingungen eines Vorsprungs von +0,11 % je Trade gedreht. Dieser
Lauf stellt eine andere Frage: Wenn man bewusst auf die volatilsten
Werte geht, schnell ein- und aussteigt, konzentriert und gehebelt
setzt - wie sieht dann die VERTEILUNG des Endkapitals ueber viele Jahre
aus? Nicht der Mittelwert ist die Antwort, sondern der Rand.

WAS DIESER LAUF NICHT DARF (wie simulate.py, BETRIEBSPLAN §4):

  * Eine Live-Schaltung begruenden. Er darf eine Idee VERWERFEN, nicht
    abnehmen.
  * Als Befund gelten. Survivorship (das Universum kennt nur heute
    gelistete Symbole; Schein-Rendite +2..+4 pp/Jahr, §G11) macht jedes
    absolute Ergebnis zu einer OBERGRENZE. Die groessten Verlierer -
    Pleiten, Delistings - fehlen im Datensatz vollstaendig, und genau
    die traefe eine "kauf die Abstuerze"-Regel am haertesten.
  * Einen Versuchszaehlerplatz kosten - solange er nur hier laeuft und
    nichts in der Flotte anmeldet.

Kein Import von trading.py, kein Senden, reiner Offline-Backtest auf
OHLC-Tagesdaten. Die Statistik folgt CLAUDE.md: massgeblich ist die Zahl
der HANDELSTAGE, nie die der Trades; `statistik.gruppierter_test` mit
`horizont=` wird immer mitgefuehrt.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

import numpy as np
import pandas as pd

from . import costs
from . import indicators as ind

WARMUP_BARS = 260
"""So viele Bars Vorlauf, bevor die erste Entscheidung faellt - der
20-Tage-Volumenschnitt, ATR und das 252-Tage-Perzentil brauchen Historie."""

TRADING_DAYS = 252


# ---------------------------------------------------------------------------
# Konfiguration - jede Achse ist eine Stellschraube fuer den Sweep
# ---------------------------------------------------------------------------
@dataclass
class SpekulativConfig:
    """Alle Achsen des spekulativen Laufs an einem Ort.

    Die Vorgaben sind der `max_aggression`-Fall: konzentriert, gehebelt,
    schneller Umschlag, weiter Stop plus Trailing (die fette Rechtsflanke
    mitnehmen - Lehre aus BEFUNDE §E: die Ausstiegs-Reihenfolge zaehlt,
    nicht der Zielwert).
    """

    # --- Kapital und Positionierung ---
    startkapital: float = 30_000.0
    max_positionen: int = 5
    """Gleichzeitig offene Positionen. Weniger = hoehere Streuung,
    hoeherer Maximalertrag, hoeheres Ruin-Risiko. Sweep-Achse."""
    hebel: float = 2.0
    """Ziel-Bruttoexposure = Equity x hebel. 1.0 = ungehebelt, bis 4.0
    (Alpaca-Intraday-Grenze). Cash darf negativ werden (Margin)."""
    groessen_modus: str = "gleich"
    """gleich | konviktion | voll_rotation | fixed_fraction.
    `voll_rotation` erzwingt genau EINE Position mit dem gesamten
    Spielraum - das theoretische Ertragsmaximum und das Ruin-Maximum."""
    fixed_fraction: float = 0.20
    """Nur bei groessen_modus='fixed_fraction': Anteil von Equity x hebel
    je Neueinstieg."""
    compounding: bool = True
    """Positionsgroesse folgt der aktuellen Equity. Aus = immer relativ
    zum Startkapital (zeigt den Effekt ohne Zinseszins)."""
    margin_zins_pa: float = 0.08
    """Jahreszins auf negatives Cash (Wertpapierkredit). 0 = aus."""

    # --- Einstiegssignal ---
    richtung: str = "momentum"
    """momentum = Staerke kaufen (Fortsetzung) | reversal = Schwaeche
    kaufen (Bounce). Short ist bewusst NICHT in v1 - Leihkosten und
    -verfuegbarkeit muessten sonst mitmodelliert werden."""
    ausloeser_1t_pct: float = 0.10
    """Betrag der 1-Tages-Rendite, ab dem ein Wert Kandidat wird."""
    ausloeser_ntage: int = 0
    """0 = aus. Sonst: zusaetzlicher Kandidat, wenn die N-Tage-Rendite
    ueber ihrem eigenen `ausloeser_perzentil`-Quantil (252 Tage) liegt."""
    ausloeser_perzentil: float = 0.98
    gap_pct: float = 0.0
    """0 = aus. Sonst zusaetzliche Bedingung: Eroeffnungsluecke
    Open/Vortagesschluss ueber (momentum) bzw. unter (reversal) dieser
    Marke."""
    vol_faktor: float = 3.0
    """Heutiges Volumen muss > vol_faktor x 20-Tage-Schnitt sein.
    0 = keine Volumenbestaetigung."""
    min_kurs: float = 3.0
    min_dollar_volumen: float = 1_000_000.0
    rangliste: str = "bewegung"
    """Wonach die Top-N aus den Kandidaten gewaehlt werden:
    bewegung = |1-Tages-Rendite| | volumen = Volumenverhaeltnis."""

    # --- Ausstieg ---
    haltedauer: int = 2
    """Maximale Handelstage im Markt. 0 = reiner Daytrade (Einstieg zum
    Open, Ausstieg zum Close desselben Tages)."""
    stop_pct: float = 0.0
    """Fester Stop als Bruchteil unter dem Einstand. 0 = aus."""
    stop_atr: float = 2.5
    """Stop als Vielfaches des ATR unter dem Einstand. 0 = aus."""
    ziel_pct: float = 0.0
    ziel_atr: float = 0.0
    """Gewinnziel. Vorgabe 0 = kein festes Ziel (Trailing uebernimmt)."""
    trail_atr: float = 4.0
    """Trailing-Stop als ATR-Abstand unter dem hoechsten erreichten
    Schluss. 0 = aus."""
    trail_pct: float = 0.0

    # --- Kosten (Rundlauf traegt beide Seiten) ---
    spread_bps: float = 5.0
    slippage_bps: float = 3.0

    # --- Ausfuehrung / Ehrlichkeit ---
    stop_vor_ziel: bool = True
    """Kollidieren Stop und Ziel am selben Tag, gilt pessimistisch der
    Stop (BEFUNDE §G3/§G4). Sonst waere das Ergebnis Fiktion."""
    pdt_beachten: bool = True
    """Pattern-Day-Trader-Regel: unter 25.000 $ Equity nur 3 Daytrades je
    5 Handelstage. Fuer haltedauer=0 eine echte Bremse."""
    pdt_schwelle: float = 25_000.0
    pdt_max: int = 3

    def pruefe(self) -> None:
        """Verwirft unsinnige Kombinationen frueh - nicht erst nach Stunden."""
        if self.richtung not in ("momentum", "reversal"):
            raise ValueError(f"richtung: {self.richtung!r}")
        if self.groessen_modus not in (
            "gleich", "konviktion", "voll_rotation", "fixed_fraction"
        ):
            raise ValueError(f"groessen_modus: {self.groessen_modus!r}")
        if self.rangliste not in ("bewegung", "volumen"):
            raise ValueError(f"rangliste: {self.rangliste!r}")
        if not 0.5 <= self.hebel <= 4.0:
            raise ValueError(f"hebel {self.hebel} ausserhalb 0.5..4.0")
        if self.max_positionen < 1:
            raise ValueError("max_positionen >= 1")
        if self.haltedauer < 0:
            raise ValueError("haltedauer >= 0")


PRESETS: dict[str, SpekulativConfig] = {
    # Konzentriert, gehebelt, Daytrade, weiter Stop - das Ertrags- und
    # Ruin-Maximum.
    "max_aggression": SpekulativConfig(
        max_positionen=1, hebel=3.0, groessen_modus="voll_rotation",
        richtung="momentum", ausloeser_1t_pct=0.12, vol_faktor=4.0,
        haltedauer=0, stop_atr=3.0, ziel_atr=0.0, trail_atr=0.0,
    ),
    # Abstuerze einsammeln und auf die Gegenbewegung setzen.
    "bounce_hunter": SpekulativConfig(
        max_positionen=3, hebel=2.0, groessen_modus="gleich",
        richtung="reversal", ausloeser_1t_pct=0.10, vol_faktor=3.0,
        haltedauer=2, stop_atr=2.0, ziel_atr=3.0, trail_atr=0.0,
    ),
    # Ausbruch auf Volumen, Gewinner laufen lassen.
    "breakout_runner": SpekulativConfig(
        max_positionen=5, hebel=2.0, groessen_modus="konviktion",
        richtung="momentum", ausloeser_1t_pct=0.08, vol_faktor=3.0,
        gap_pct=0.0, haltedauer=5, stop_atr=2.5, ziel_atr=0.0, trail_atr=4.0,
    ),
    # Viele kleine Daytrades, enge Marken.
    "daytrade_scalp": SpekulativConfig(
        max_positionen=10, hebel=2.0, groessen_modus="gleich",
        richtung="momentum", ausloeser_1t_pct=0.06, vol_faktor=2.5,
        haltedauer=0, stop_atr=1.5, ziel_atr=1.5, trail_atr=0.0,
    ),
}


# ---------------------------------------------------------------------------
# Merkmale - EINMAL vorberechnen, vollstaendig kausal (nur Vergangenheit)
# ---------------------------------------------------------------------------
def _merkmale(df: pd.DataFrame, cfg: SpekulativConfig) -> pd.DataFrame:
    """Pro Symbol: Signalbausteine plus fertige kandidat/rang-Spalten.

    Jede abgeleitete Groesse benutzt ausschliesslich Werte bis
    einschliesslich des jeweiligen Tages. Der 20-Tage-Volumenschnitt und
    das 252-Tage-Perzentil sind mit `.shift(1)` bewusst um einen Tag
    verzoegert, damit der heutige Wert nicht in seine eigene
    Vergleichsbasis eingeht.
    """
    close = df["close"].astype(float)
    openp = df["open"].astype(float)
    vol = df["volume"].astype(float)

    out = pd.DataFrame(index=df.index)
    out["open"] = openp
    out["high"] = df["high"].astype(float)
    out["low"] = df["low"].astype(float)
    out["close"] = close
    out["ret_1t"] = close.pct_change()
    out["gap"] = openp / close.shift(1) - 1.0

    vsma = vol.rolling(20).mean().shift(1)
    out["vol_ratio"] = np.where(vsma > 0, vol / vsma, np.nan)

    atr = ind.atr(df, 14).astype(float)
    out["atr"] = atr
    out["dollar_vol"] = (close * vol).rolling(20).median()

    if cfg.ausloeser_ntage > 0:
        nret = close / close.shift(cfg.ausloeser_ntage) - 1.0
        out["nret"] = nret
        out["nret_q"] = nret.rolling(252).quantile(cfg.ausloeser_perzentil).shift(1)

    # --- kandidat / rang vollstaendig vektorisiert ---
    r = out["ret_1t"]
    if cfg.richtung == "momentum":
        treffer = r >= cfg.ausloeser_1t_pct
        if cfg.gap_pct > 0:
            treffer &= out["gap"] >= cfg.gap_pct
    else:  # reversal
        treffer = r <= -cfg.ausloeser_1t_pct
        if cfg.gap_pct > 0:
            treffer &= out["gap"] <= -cfg.gap_pct

    if cfg.vol_faktor > 0:
        treffer &= out["vol_ratio"] >= cfg.vol_faktor

    if cfg.ausloeser_ntage > 0:
        perz = (out["nret"] >= out["nret_q"])
        if cfg.vol_faktor > 0:
            perz &= out["vol_ratio"] >= cfg.vol_faktor
        treffer |= perz

    treffer &= close >= cfg.min_kurs
    treffer &= out["dollar_vol"] >= cfg.min_dollar_volumen
    treffer &= atr > 0
    treffer &= r.notna()

    out["kandidat"] = treffer.fillna(False).to_numpy(dtype=bool)
    if cfg.rangliste == "volumen":
        out["rang"] = out["vol_ratio"].fillna(0.0)
    else:
        out["rang"] = r.abs().fillna(0.0)
    return out


def _stop_marke(entry: float, atr: float, cfg: SpekulativConfig) -> float:
    marken = []
    if cfg.stop_atr > 0 and atr > 0:
        marken.append(entry - cfg.stop_atr * atr)
    if cfg.stop_pct > 0:
        marken.append(entry * (1 - cfg.stop_pct))
    return max(marken) if marken else 0.0


def _ziel_marke(entry: float, atr: float, cfg: SpekulativConfig) -> float:
    marken = []
    if cfg.ziel_atr > 0 and atr > 0:
        marken.append(entry + cfg.ziel_atr * atr)
    if cfg.ziel_pct > 0:
        marken.append(entry * (1 + cfg.ziel_pct))
    return min(marken) if marken else 0.0


def _trail_marke(high_water: float, atr: float, cfg: SpekulativConfig) -> float:
    marken = []
    if cfg.trail_atr > 0 and atr > 0:
        marken.append(high_water - cfg.trail_atr * atr)
    if cfg.trail_pct > 0:
        marken.append(high_water * (1 - cfg.trail_pct))
    return max(marken) if marken else 0.0


# ---------------------------------------------------------------------------
# Ergebnis
# ---------------------------------------------------------------------------
@dataclass
class Trade:
    symbol: str
    entry_date: pd.Timestamp
    exit_date: pd.Timestamp
    entry_raw: float
    """Fuellkurs OHNE Kostenanpassung - Basis der Kostensensitivitaet."""
    exit_raw: float
    entry_price: float
    """Effektiver Einstand nach halber Spanne und Slippage."""
    exit_price: float
    qty: int
    richtung: str
    exit_reason: str
    brutto_ret: float
    """Rendite auf Rohkurse, ohne jede Kosten."""
    gross_pnl: float
    kosten: float
    net_pnl: float
    return_pct: float
    bars_held: int


@dataclass
class SpekResult:
    equity_curve: pd.Series
    trades: pd.DataFrame
    config: SpekulativConfig
    ruin: bool
    ruin_datum: pd.Timestamp | None
    margin_zins: float
    n_symbols: int
    kalender_tage: int
    blockiert: dict[str, int] = field(default_factory=dict)

    # --- Kennzahlen ---
    @property
    def total_return(self) -> float:
        if self.equity_curve.empty:
            return -1.0 if self.ruin else 0.0
        return float(self.equity_curve.iloc[-1] / self.equity_curve.iloc[0] - 1)

    def metrics(self) -> dict:
        from .backtest import compute_metrics

        eq = self.equity_curve
        if eq.empty or len(eq) < 3:
            return {"ruin": self.ruin}
        # Nach einem Ruin wird die Kurve negativ - `pct_change` und die
        # CAGR-Wurzel daraus sind dann bedeutungslos. Kennzahlen auf dem
        # letzten noch positiven Stueck rechnen, der Ruin steht separat.
        eq_pos = eq[eq > 0]
        m = compute_metrics(eq_pos.pct_change().dropna()) if len(eq_pos) >= 3 else {}
        m["ruin"] = self.ruin
        if self.ruin:
            m["total_return"] = -1.0
            m["cagr"] = -1.0
        m["margin_zins"] = self.margin_zins
        t = self.trades
        if not t.empty:
            gew = t[t["net_pnl"] > 0]
            vrl = t[t["net_pnl"] <= 0]
            m["n_trades"] = int(len(t))
            m["trades_pro_tag"] = float(len(t) / max(1, self.kalender_tage))
            m["trefferquote"] = float(len(gew) / len(t))
            m["mittlerer_gewinn"] = float(gew["return_pct"].mean()) if len(gew) else 0.0
            m["mittlerer_verlust"] = float(vrl["return_pct"].mean()) if len(vrl) else 0.0
            m["profit_faktor"] = (
                float(gew["net_pnl"].sum() / abs(vrl["net_pnl"].sum()))
                if len(vrl) and vrl["net_pnl"].sum() != 0 else float("inf")
            )
            m["ertrag_je_trade"] = float(t["return_pct"].mean())
            m["ertrag_je_trade_brutto"] = float(t["brutto_ret"].mean())
            m["kosten_gesamt"] = float(t["kosten"].sum())
            m["mittlere_haltedauer"] = float(t["bars_held"].mean())
            m["laengste_verluststrecke"] = _laengste_verluststrecke(t)
        return m

    def gruppentest(self):
        """Gruppierter t-Test der Trade-Renditen nach EINSTIEGSTAG.

        Horizont = haltedauer + 1: bei einer mehrtaegigen Haltedauer
        ueberlappen sich die Renditefenster benachbarter Einstiegstage
        (CLAUDE.md / BEFUNDE §G12). `gruppierter_test` korrigiert das
        ueber Newey-West; massgeblich ist dann `t_ueberlappung`.
        """
        from .statistik import gruppierter_test

        t = self.trades
        if t.empty:
            return gruppierter_test(pd.Series(dtype=float), pd.Series(dtype=float))
        horizont = max(1, int(self.config.haltedauer) + 1)
        return gruppierter_test(
            t["return_pct"], t["entry_date"], horizont=horizont
        )

    def jahres_renditen(self) -> dict[int, float]:
        """Kalenderjahr -> Rendite der Equity-Kurve in diesem Jahr.

        Grundlage der Konsistenzpruefung: Eine Strategie, die in einem
        Jahr die Haelfte verliert und es in einem anderen wieder
        einspielt, hat KEINE jaehrliche Gewinnpflicht erfuellt - auch
        wenn die Gesamtrendite stimmt.
        """
        eq = self.equity_curve
        if eq.empty:
            return {}
        out: dict[int, float] = {}
        for j in sorted({ts.year for ts in eq.index}):
            eq_j = eq[eq.index.year == j]
            if len(eq_j) >= 2:
                out[j] = float(eq_j.iloc[-1] / eq_j.iloc[0] - 1)
        return out

    def schlechtestes_jahr(self) -> tuple[int, float] | None:
        jr = self.jahres_renditen()
        if not jr:
            return None
        j = min(jr, key=jr.get)
        return j, jr[j]

    def jahre_ueber(self, schwelle: float = 0.0) -> tuple[int, int]:
        """(Anzahl Jahre >= schwelle, Anzahl Jahre gesamt)."""
        jr = list(self.jahres_renditen().values())
        return sum(1 for r in jr if r >= schwelle), len(jr)

    def jahrestabelle(self) -> pd.DataFrame:
        """Rendite, Trades und gruppierter t-Wert je Kalenderjahr.

        BEFUNDE §G11: der gesamte Vorsprung eines Laufs kann an einem
        einzigen Teiljahr haengen. Ohne diese Aufschluesselung sieht man
        das nicht.
        """
        from .statistik import gruppierter_test

        eq = self.equity_curve
        t = self.trades
        zeilen = []
        if eq.empty:
            return pd.DataFrame()
        jahres_r = self.jahres_renditen()
        for j in sorted(jahres_r):
            rendite = jahres_r[j]
            tj = t[t["entry_date"].dt.year == j] if not t.empty else t
            if len(tj) >= 2:
                horizont = max(1, int(self.config.haltedauer) + 1)
                res = gruppierter_test(tj["return_pct"], tj["entry_date"],
                                       horizont=horizont, min_gruppen=5)
                tval = res.t_ueberlappung if np.isfinite(res.t_ueberlappung) else res.t
            else:
                tval = float("nan")
            zeilen.append({"jahr": j, "rendite": rendite,
                           "n_trades": int(len(tj)), "t": float(tval)})
        return pd.DataFrame(zeilen).set_index("jahr")

    def bootstrap(self, n: int = 5000, blocklaenge: int = 5,
                  seed: int = 0) -> dict:
        """Moving-Block-Bootstrap der Tagesrenditen -> Verteilung des
        Endkapitals.

        Bei "maximaler Ertrag" ist der Mittelwert nicht die Geschichte,
        sondern der Rand: Wie wahrscheinlich ist Ruin, wie fett die
        Rechtsflanke? Der Block erhaelt die kurzfristige Autokorrelation
        (Vola-Cluster), die ein naiver i.i.d.-Bootstrap zerstoeren wuerde.
        """
        eq = self.equity_curve
        if eq.empty or len(eq) < 30:
            return {}
        r = eq.pct_change().dropna().to_numpy()
        m = len(r)
        rng = np.random.default_rng(seed)
        n_bloecke = int(np.ceil(m / blocklaenge))
        endwerte = np.empty(n)
        min_multiple = np.empty(n)
        for k in range(n):
            starts = rng.integers(0, m - blocklaenge + 1, size=n_bloecke)
            idx = (starts[:, None] + np.arange(blocklaenge)[None, :]).ravel()[:m]
            pfad = np.cumprod(1.0 + r[idx])
            endwerte[k] = pfad[-1]
            min_multiple[k] = pfad.min()
        return {
            "n": n,
            "p05": float(np.percentile(endwerte, 5)),
            "p25": float(np.percentile(endwerte, 25)),
            "p50": float(np.percentile(endwerte, 50)),
            "p75": float(np.percentile(endwerte, 75)),
            "p95": float(np.percentile(endwerte, 95)),
            "prob_verlust": float((endwerte < 1.0).mean()),
            "prob_ruin_80pct": float((min_multiple < 0.20).mean()),
            "prob_2x": float((endwerte > 2.0).mean()),
            "prob_5x": float((endwerte > 5.0).mean()),
            "prob_10x": float((endwerte > 10.0).mean()),
        }

    def kosten_sensitivitaet(
        self, bps_stufen: tuple[tuple[float, float], ...] = (
            (0.0, 0.0), (5.0, 3.0), (10.0, 6.0), (25.0, 10.0), (50.0, 20.0),
        )
    ) -> pd.DataFrame:
        """Ertrag je Trade bei anderen Spannen - NAEHERUNG ohne Neurechnung
        des Hebels.

        Pro Trade: `brutto_ret` minus den Rundlaufkosten-Prozentsatz bei
        der jeweiligen Spanne (`costs.round_trip` auf dem Rohkurs). Das
        ist exakt fuer die Ebene "je Trade"; die auf das gehebelte Depot
        kumulierte Wirkung braucht einen echten Neulauf (40_spekulativ.py
        --kosten-check)."""
        t = self.trades
        if t.empty:
            return pd.DataFrame()
        zeilen = []
        for spread, slip in bps_stufen:
            rundlauf = t["entry_raw"].apply(
                lambda p: costs.round_trip(
                    100, float(p), float(p), spread_bps=spread, slippage_bps=slip
                )["breakeven_kurs"] / float(p) - 1.0
            )
            netto = t["brutto_ret"] - rundlauf
            zeilen.append({
                "spread_bps": spread,
                "slippage_bps": slip,
                "ertrag_je_trade": float(netto.mean()),
                "trefferquote": float((netto > 0).mean()),
                "summe_pnl_norm": float(netto.sum()),
            })
        return pd.DataFrame(zeilen).set_index(["spread_bps", "slippage_bps"])


def _laengste_verluststrecke(trades: pd.DataFrame) -> int:
    lauf = best = 0
    for pnl in trades.sort_values("exit_date")["net_pnl"]:
        if pnl <= 0:
            lauf += 1
            best = max(best, lauf)
        else:
            lauf = 0
    return int(best)


# ---------------------------------------------------------------------------
# Der Lauf - Handelstag fuer Handelstag
# ---------------------------------------------------------------------------
def run(
    bars: pd.DataFrame,
    cfg: SpekulativConfig | None = None,
    *,
    start: str | None = None,
    end: str | None = None,
    verbose: bool = True,
) -> SpekResult:
    """Spielt die Historie Tag fuer Tag durch.

    Args:
        bars: MultiIndex (symbol, timestamp) mit OHLCV.
        cfg: die Stellschrauben. Ohne Angabe der `max_aggression`-Fall.

    Ablauf je Tag T:
      1. offene Kauforders von gestern zur heutigen Eroeffnung fuellen
      2. offene Positionen pflegen: Stop/Ziel/Trailing intraday gegen
         Tages-High/Low (pessimistische Reihenfolge), dann Zeitausstieg
      3. Kontowert bestimmen, Margin-Zins abziehen, auf Ruin pruefen
      4. Signale auf dem heutigen (abgeschlossenen) Bar -> Rangliste ->
         Top-N als Order fuer morgen
    """
    cfg = cfg or PRESETS["max_aggression"]
    cfg.pruefe()

    per_symbol: dict[str, pd.DataFrame] = {}
    for sym in bars.index.get_level_values("symbol").unique():
        df = bars.xs(sym, level="symbol").sort_index()
        df = df[~df.index.duplicated(keep="last")]
        if len(df) > WARMUP_BARS:
            per_symbol[str(sym)] = df
    if not per_symbol:
        raise ValueError("Keine Symbole mit ausreichender Historie.")

    if verbose:
        print(f"    Merkmale fuer {len(per_symbol)} Symbole ...")
    merk = {sym: _merkmale(df, cfg) for sym, df in per_symbol.items()}

    kalender = pd.DatetimeIndex(
        sorted(set().union(*[set(df.index) for df in per_symbol.values()]))
    )
    if start:
        kalender = kalender[kalender >= pd.Timestamp(start, tz=kalender.tz)]
    if end:
        kalender = kalender[kalender <= pd.Timestamp(end, tz=kalender.tz)]
    if len(kalender) < WARMUP_BARS + 5:
        raise ValueError("Zu wenig Handelstage im gewaehlten Zeitraum.")

    startkapital = float(cfg.startkapital)
    cash = startkapital
    positionen: dict[str, dict] = {}
    pending: list[dict] = []
    equity_hist: list[tuple[pd.Timestamp, float]] = []
    trades: list[Trade] = []
    blockiert: dict[str, int] = {}
    daytrade_tage: list[pd.Timestamp] = []
    margin_zins_kum = 0.0
    ruin = False
    ruin_datum: pd.Timestamp | None = None

    def basis_equity(aktuelle_equity: float) -> float:
        return aktuelle_equity if cfg.compounding else startkapital

    def schliessen(sym: str, fill_raw: float, tag: pd.Timestamp,
                   grund: str) -> None:
        nonlocal cash
        pos = positionen.pop(sym, None)
        if pos is None:
            return
        verk = costs.estimate_costs(
            "sell", pos["qty"], last=fill_raw,
            spread_bps=cfg.spread_bps, slippage_bps=cfg.slippage_bps,
        )
        cash += verk.net_proceeds
        if pos["entry_date"] == tag:
            daytrade_tage.append(tag)
        invested = pos["qty"] * pos["entry"]
        gross = pos["qty"] * (verk.effective_price - pos["entry"])
        kosten_ges = verk.total_cost + pos["entry_kosten"]
        netto = verk.net_proceeds - (invested + pos["entry_kosten"])
        trades.append(Trade(
            symbol=sym, entry_date=pos["entry_date"], exit_date=tag,
            entry_raw=pos["entry_raw"], exit_raw=float(fill_raw),
            entry_price=pos["entry"], exit_price=verk.effective_price,
            qty=int(pos["qty"]), richtung=pos["richtung"], exit_reason=grund,
            brutto_ret=float(fill_raw / pos["entry_raw"] - 1.0),
            gross_pnl=round(gross, 2), kosten=round(kosten_ges, 2),
            net_pnl=round(netto, 2),
            return_pct=round(netto / invested, 5) if invested else 0.0,
            bars_held=int(pos["bars_held"]),
        ))

    for i, heute in enumerate(kalender):
        # ---------- 1. Kauforders von gestern ausfuehren ----------
        for order in pending:
            sym = order["symbol"]
            df = per_symbol.get(sym)
            if df is None or heute not in df.index:
                blockiert["kein_bar_am_folgetag"] = blockiert.get(
                    "kein_bar_am_folgetag", 0) + 1
                continue
            bar = df.loc[heute]
            fill = float(bar["open"])
            if fill <= 0:
                continue
            qty = int(order["notional"] / fill)
            if qty <= 0:
                blockiert["betrag_zu_klein"] = blockiert.get("betrag_zu_klein", 0) + 1
                continue
            kauf = costs.estimate_costs(
                "buy", qty, last=fill,
                spread_bps=cfg.spread_bps, slippage_bps=cfg.slippage_bps,
            )
            cash -= kauf.net_proceeds
            mk = merk[sym]
            atr = float(mk.loc[heute, "atr"]) if heute in mk.index else 0.0
            if not np.isfinite(atr):
                atr = 0.0
            entry = kauf.effective_price
            positionen[sym] = dict(
                qty=qty, entry=entry, entry_raw=fill, entry_date=heute,
                stop=_stop_marke(entry, atr, cfg),
                ziel=_ziel_marke(entry, atr, cfg),
                high_water=entry, richtung=cfg.richtung,
                entry_kosten=kauf.total_cost, bars_held=0,
            )
        pending = []

        # ---------- 2. offene Positionen pflegen ----------
        heutige_daytrades = len([d for d in daytrade_tage if (heute - d).days <= 7])
        for sym, pos in list(positionen.items()):
            df = per_symbol.get(sym)
            if df is None or heute not in df.index:
                continue
            bar = df.loc[heute]
            hi, lo, cl, op = (float(bar["high"]), float(bar["low"]),
                              float(bar["close"]), float(bar["open"]))
            pos["bars_held"] += 1
            if cl > pos["high_water"]:
                pos["high_water"] = cl
            mk = merk[sym]
            atr = float(mk.loc[heute, "atr"]) if heute in mk.index else 0.0
            if not np.isfinite(atr):
                atr = 0.0
            trail = _trail_marke(pos["high_water"], atr, cfg)
            eff_stop = max(pos["stop"], trail) if trail > 0 else pos["stop"]

            stop_hit = eff_stop > 0 and lo <= eff_stop
            ziel_hit = pos["ziel"] > 0 and hi >= pos["ziel"]
            grund = fill = None
            if stop_hit and ziel_hit:
                if cfg.stop_vor_ziel:
                    grund, fill = "stop", min(eff_stop, op)
                else:
                    grund, fill = "ziel", max(pos["ziel"], op)
            elif stop_hit:
                grund, fill = "stop", min(eff_stop, op)
            elif ziel_hit:
                grund, fill = "ziel", max(pos["ziel"], op)
            elif pos["bars_held"] >= cfg.haltedauer:
                grund, fill = "zeit", cl

            if grund is None:
                continue

            # PDT-Bremse: nur fuer den Zeit-/Ziel-Ausstieg am Kauftag.
            # Ein Stop ist eine Notbremse und wird nie blockiert.
            if (cfg.pdt_beachten and grund != "stop"
                    and pos["entry_date"] == heute
                    and cash + sum(  # grobe Equity-Schaetzung fuer die Schwelle
                        p["qty"] * float(per_symbol[s].loc[heute, "close"])
                        for s, p in positionen.items()
                        if heute in per_symbol[s].index
                    ) < cfg.pdt_schwelle
                    and heutige_daytrades >= cfg.pdt_max):
                blockiert["pdt_regel"] = blockiert.get("pdt_regel", 0) + 1
                pos["bars_held"] -= 1  # zaehlt morgen erneut
                continue

            schliessen(sym, fill, heute, grund)
            if pos["entry_date"] == heute:
                heutige_daytrades += 1

        # ---------- 3. Kontowert, Margin-Zins, Ruin ----------
        wert = cash
        for sym, pos in positionen.items():
            df = per_symbol.get(sym)
            px = (float(df.loc[heute, "close"])
                  if df is not None and heute in df.index else pos["entry"])
            wert += pos["qty"] * px
        if cash < 0 and cfg.margin_zins_pa > 0:
            z = -cash * cfg.margin_zins_pa / TRADING_DAYS
            cash -= z
            wert -= z
            margin_zins_kum += z
        equity_hist.append((heute, wert))
        if wert <= 0:
            ruin = True
            ruin_datum = heute
            if verbose:
                print(f"    RUIN am {heute.date()} - Lauf abgebrochen")
            break

        # ---------- 4. Signale fuer morgen ----------
        if i < WARMUP_BARS or i >= len(kalender) - 1:
            continue
        frei = cfg.max_positionen - len(positionen)
        if cfg.groessen_modus == "voll_rotation":
            frei = min(frei, 1)
        if frei <= 0:
            continue

        kandidaten: list[tuple[str, float]] = []
        for sym, mk in merk.items():
            if sym in positionen or heute not in mk.index:
                continue
            zeile = mk.loc[heute]
            if bool(zeile["kandidat"]):
                kandidaten.append((sym, float(zeile["rang"])))
        if not kandidaten:
            continue
        kandidaten.sort(key=lambda x: -x[1])
        gewaehlt = kandidaten[:frei]

        eq_basis = basis_equity(wert)
        brutto_ziel = eq_basis * cfg.hebel
        investiert = sum(
            pos["qty"] * float(per_symbol[s].loc[heute, "close"])
            for s, pos in positionen.items() if heute in per_symbol[s].index
        )
        spielraum = max(0.0, brutto_ziel - investiert)
        if spielraum < 1:
            continue

        rang_summe = sum(rg for _, rg in gewaehlt) or 1.0
        for sym, rang in gewaehlt:
            if cfg.groessen_modus == "voll_rotation":
                notional = spielraum
            elif cfg.groessen_modus == "fixed_fraction":
                notional = eq_basis * cfg.hebel * cfg.fixed_fraction
            elif cfg.groessen_modus == "konviktion":
                anteil = rang / rang_summe
                # auf den Slot-Durchschnitt normiert, dann 0,3x..3x gekappt
                faktor = float(np.clip(anteil * len(gewaehlt), 0.3, 3.0))
                notional = (eq_basis * cfg.hebel / cfg.max_positionen) * faktor
            else:  # gleich
                notional = eq_basis * cfg.hebel / cfg.max_positionen
            notional = min(notional, spielraum)
            if notional < 1:
                continue
            spielraum -= notional
            pending.append(dict(symbol=sym, notional=notional, rang=rang))

        if verbose and i % 500 == 0:
            print(f"    {heute.date()}  Equity ${wert:>12,.0f}  "
                  f"Positionen {len(positionen):>2}  Trades {len(trades):>5}")

    # --- offene Positionen zum letzten Kurs glattstellen ---
    if not ruin and positionen:
        letzter = kalender[min(len(kalender) - 1, i)]
        for sym in list(positionen):
            df = per_symbol.get(sym)
            if df is None:
                continue
            gueltig = df.index[df.index <= letzter]
            if len(gueltig) == 0:
                continue
            schliessen(sym, float(df.loc[gueltig[-1], "close"]), letzter, "lauf_ende")
        wert = cash
        equity_hist.append((letzter, wert))

    eq = pd.Series(dict(equity_hist)).sort_index()
    return SpekResult(
        equity_curve=eq,
        trades=pd.DataFrame([t.__dict__ for t in trades]),
        config=cfg,
        ruin=ruin,
        ruin_datum=ruin_datum,
        margin_zins=round(margin_zins_kum, 2),
        n_symbols=len(per_symbol),
        kalender_tage=len(kalender),
        blockiert=blockiert,
    )


# ---------------------------------------------------------------------------
# Auswertung - eine Zahl, mit allen Vorbehalten daneben
# ---------------------------------------------------------------------------
def auswerten(
    result: SpekResult,
    *,
    benchmark_return: float | None = None,
    benchmark_name: str = "SPY B&H",
    n_konfigurationen: int = 1,
    schwelle: float | None = None,
    jahre: float | None = None,
    segment: str = "small_cap",
    min_jahr_schwelle: float | None = None,
) -> str:
    """Vollstaendiger Textbericht: Kennzahlen, gruppierter Test,
    Jahrestabelle, Bootstrap-Verteilung, Kostensensitivitaet, und die
    Leitplanken, ohne die die Zahl in die Irre fuehrt.
    """
    from . import universe

    cfg = result.config
    m = result.metrics()
    L: list[str] = []
    L.append("=" * 74)
    L.append("  SPEKULATIVER HISTORIENLAUF - ERGEBNIS")
    L.append("=" * 74)

    # --- Konfiguration in einer Zeile ---
    L.append(f"  Richtung {cfg.richtung} | Ausloeser |1T| >= {cfg.ausloeser_1t_pct:.0%}"
             f" | Vol > {cfg.vol_faktor:g}x | Halten {cfg.haltedauer} T")
    L.append(f"  Positionen {cfg.max_positionen} | Hebel {cfg.hebel:g}x | "
             f"Groesse {cfg.groessen_modus} | Stop {cfg.stop_atr:g}xATR | "
             f"Ziel {cfg.ziel_atr:g}xATR | Trail {cfg.trail_atr:g}xATR")
    L.append(f"  Kosten {cfg.spread_bps:g}+{cfg.slippage_bps:g} bps | "
             f"{result.n_symbols} Symbole | {result.kalender_tage} Handelstage")
    L.append("")

    if result.ruin:
        L.append(f"  *** RUIN am {result.ruin_datum.date()} - Konto vollstaendig "
                 f"verloren. ***")
        L.append(f"  Bis dahin: {len(result.trades)} Trades, "
                 f"{result.kalender_tage} Handelstage.")
        L.append("")

    # --- Kernkennzahlen ---
    endkapital = float(result.equity_curve.iloc[-1]) if not result.equity_curve.empty else 0.0
    L.append("  KENNZAHLEN")
    L.append(f"    Startkapital          ${cfg.startkapital:>14,.0f}")
    L.append(f"    Endkapital            ${endkapital:>14,.0f}")
    L.append(f"    Gesamtrendite         {result.total_return:>14.1%}")
    L.append(f"    Rendite p.a. (CAGR)   {m.get('cagr', float('nan')):>14.1%}")
    L.append(f"    Max. Drawdown         {m.get('max_drawdown', float('nan')):>14.1%}")
    L.append(f"    Sharpe / Sortino      {m.get('sharpe', float('nan')):>7.2f} /"
             f"{m.get('sortino', float('nan')):>6.2f}")
    L.append(f"    Margin-Zins gezahlt   ${result.margin_zins:>14,.0f}")
    if benchmark_return is not None:
        L.append(f"    {benchmark_name:<20} {benchmark_return:>14.1%}   "
                 f"(Differenz {result.total_return - benchmark_return:>+.1%})")
    L.append("")
    L.append(f"    Trades                {m.get('n_trades', 0):>14,}")
    L.append(f"    Trades je Handelstag  {m.get('trades_pro_tag', 0):>14.2f}")
    L.append(f"    Trefferquote          {m.get('trefferquote', 0):>14.1%}")
    L.append(f"    Ertrag je Trade netto {m.get('ertrag_je_trade', 0):>14.3%}")
    L.append(f"    Ertrag je Trade brutto{m.get('ertrag_je_trade_brutto', 0):>14.3%}")
    L.append(f"    Mittlerer Gewinn      {m.get('mittlerer_gewinn', 0):>14.2%}")
    L.append(f"    Mittlerer Verlust     {m.get('mittlerer_verlust', 0):>14.2%}")
    L.append(f"    Profit-Faktor         {m.get('profit_faktor', 0):>14.2f}")
    L.append(f"    Laengste Verluststrecke {m.get('laengste_verluststrecke', 0):>12} Trades")
    L.append(f"    Kosten gesamt         ${m.get('kosten_gesamt', 0):>14,.0f}")
    if result.blockiert:
        L.append("    Blockiert: " + ", ".join(
            f"{k}={v}" for k, v in sorted(result.blockiert.items(), key=lambda x: -x[1])))
    L.append("")

    # --- Gruppierter Test (die eine belastbare Zahl) ---
    res = result.gruppentest()
    L.append("  GRUPPIERTER TEST - Trade-Renditen nach Einstiegstag")
    L.append("  (massgeblich ist die Zahl der HANDELSTAGE, nicht der Trades)")
    for zeile in str(res).splitlines():
        L.append("  " + zeile)
    if schwelle is not None:
        massgeblich = res.t_ueberlappung if np.isfinite(res.t_ueberlappung) else res.t
        verdikt = ("UEBER der Schwelle" if abs(massgeblich) > schwelle
                   else "unter der Schwelle - kein Befund")
        L.append(f"    Zufallsschwelle (fleet.schwelle_sigma): {schwelle:.2f}  "
                 f"-> {verdikt}")
    L.append("")

    # --- Jahrestabelle ---
    jt = result.jahrestabelle()
    if not jt.empty:
        L.append("  JAHR FUER JAHR  (BEFUNDE §G11: der ganze Vorsprung kann an "
                 "einem Teiljahr haengen)")
        L.append(f"    {'Jahr':>6} {'Rendite':>12} {'Trades':>8} {'t (grp)':>9}")
        for jahr, row in jt.iterrows():
            L.append(f"    {jahr:>6} {row['rendite']:>12.1%} "
                     f"{int(row['n_trades']):>8} {row['t']:>9.2f}")
        pos_jahre = int((jt["rendite"] > 0).sum())
        L.append(f"    -> {pos_jahre} von {len(jt)} Jahren positiv")
        sj = result.schlechtestes_jahr()
        if sj is not None:
            L.append(f"    -> schlechtestes Jahr: {sj[0]} mit {sj[1]:+.1%}")
        if min_jahr_schwelle is not None and sj is not None:
            n_ok, n_ges = result.jahre_ueber(min_jahr_schwelle)
            erfuellt = n_ok == n_ges and n_ges > 0
            L.append(f"    -> KONSISTENZPFLICHT (jedes Jahr >= "
                     f"{min_jahr_schwelle:+.0%}): "
                     f"{'ERFUELLT' if erfuellt else 'VERFEHLT'} "
                     f"({n_ok}/{n_ges} Jahre). "
                     + ("" if erfuellt else
                        "Ein einziges Minusjahr genuegt zum Durchfallen."))
            if erfuellt:
                L.append("       ACHTUNG: 'jedes Jahr positiv' IN-SAMPLE ist bei "
                         "genug geprueften Konfigs Zufall (BEFUNDE §B4/§G45). "
                         "Entscheidend ist die Walk-Forward-Zeile, nicht diese.")
        L.append("")

    # --- Bootstrap-Verteilung ---
    bs = result.bootstrap()
    if bs:
        L.append("  BOOTSTRAP - Verteilung des Endkapital-Vielfachen "
                 f"({bs['n']:,} Ziehungen, Bloecke a 5 Tage)")
        L.append(f"    p05 / p25 / p50 / p75 / p95:  "
                 f"{bs['p05']:.2f}x / {bs['p25']:.2f}x / {bs['p50']:.2f}x / "
                 f"{bs['p75']:.2f}x / {bs['p95']:.2f}x")
        L.append(f"    Wahrsch. Endkapital < Start : {bs['prob_verlust']:.1%}")
        L.append(f"    Wahrsch. zwischenzeitl. -80%: {bs['prob_ruin_80pct']:.1%}")
        L.append(f"    Wahrsch. > 2x / 5x / 10x    : "
                 f"{bs['prob_2x']:.1%} / {bs['prob_5x']:.1%} / {bs['prob_10x']:.1%}")
        L.append("")

    # --- Kostensensitivitaet ---
    ks = result.kosten_sensitivitaet()
    if not ks.empty:
        L.append("  KOSTENSENSITIVITAET - Ertrag je Trade (Naeherung, ohne "
                 "Hebel-Neurechnung)")
        L.append(f"    {'Spread+Slip bps':>18} {'Ertrag/Trade':>14} {'Treffer':>9}")
        for (spread, slip), row in ks.iterrows():
            L.append(f"    {spread:>6.0f} + {slip:<3.0f}       "
                     f"{row['ertrag_je_trade']:>14.3%} {row['trefferquote']:>9.1%}")
        L.append("    (BEFUNDE §G44: der freie IEX-Feed misst fuer diese Werte "
                 "eher 25-270 bps, nicht 5.)")
        L.append("")

    # --- Leitplanken ---
    if jahre:
        L.append("  SURVIVORSHIP")
        for zeile in universe.survivorship_warning(
                result.n_symbols, jahre, segment).splitlines():
            L.append("  " + zeile)
        L.append("")

    if n_konfigurationen > 1:
        mt_schwelle = float(np.sqrt(2 * np.log(n_konfigurationen)) + 0.5)
        L.append(f"  MULTIPLES TESTEN: {n_konfigurationen} Konfigurationen geprueft "
                 f"-> Zufallsmaximum t ~ {mt_schwelle:.2f}.")
        L.append("  Die beste Konfiguration eines Sweeps ist per Konstruktion "
                 "die beste - das ist kein Befund (BEFUNDE §B2/§B4).")
        L.append("")

    L.append("  EINORDNUNG")
    L.append("  - Absolute Renditen sind eine OBERGRENZE: die Pleiten fehlen "
             "im Universum, und eine")
    L.append("    Aggressiv-Long-Regel wuerde genau von ihnen getroffen.")
    L.append("  - Dieser Lauf darf eine Idee VERWERFEN, nicht abnehmen "
             "(BETRIEBSPLAN §4).")
    L.append("  - Kein Versuchszaehlerplatz, solange nichts in der Flotte "
             "angemeldet wird.")
    L.append("=" * 74)
    return "\n".join(L)


# ---------------------------------------------------------------------------
# Sweep - eine Achse (oder mehrere) rastern
# ---------------------------------------------------------------------------
def sweep_konfigs(basis: SpekulativConfig,
                  achsen: dict[str, list]) -> list[tuple[dict, SpekulativConfig]]:
    """Kartesisches Produkt ueber `achsen` auf `basis` angewandt.

    Returns: Liste aus (belegung, config). `belegung` haelt nur die
    gesetzten Achsen fest - fuer die Ergebniszeile.
    """
    import itertools

    namen = list(achsen)
    kombis = list(itertools.product(*[achsen[n] for n in namen]))
    out = []
    for werte in kombis:
        belegung = dict(zip(namen, werte))
        out.append((belegung, replace(basis, **belegung)))
    return out
