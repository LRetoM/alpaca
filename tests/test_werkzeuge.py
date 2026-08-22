"""Die zwei Werkzeuge ohne Testabdeckung: RL und Ereignisstudie (§G17).

**Anlass (22.08.2026).** Beide Module waren die letzten ungeprüften
Flächen des Projekts. Die naheliegende Frage war, ob sie überhaupt noch
laufen — sie taten es, beide, und methodisch einwandfrei. Der Befund lag
woanders:

    src/alpaca_bot/rl/    keine einzige Testdatei
    events.py             nur `00_selftest.py` [6], kein Regressionstest

Das wiegt bei RL besonders, weil `README.md` den Timing-Test als eine
der **fünf Sicherungen** des Projekts führt und `selfcheck.CHARTER`
Regel 7 ihn verlangt:

    "Jede RL-Politik wird gegen den Timing-Test gemessen, nicht gegen
     die Rendite."

Der Modul-Docstring behauptet zusätzlich, der Test sei "fest verdrahtet
und lässt sich nicht abschalten". Das war bis hierher eine *Behauptung* —
genau die Art Zusicherung, die dieses Projekt sonst durch Tests deckt.

**Warum die Module bleiben und nicht entfernt wurden.** Beide sind
Werkzeuge, keine Dauerläufer — wie `03_backtest.py` oder
`06_event_study.py`. Dass sie nicht im 15-Minuten-Takt laufen, ist ihre
Bestimmung, kein Ausfall. Entscheidend war, dass sie **funktionieren**
und **kalibriert** sind: Der RL-Lauf meldet auf reinem Rauschen korrekt
"KEIN nachweisbares Timing-Können" (Perzentil 17 von geforderten 95).
Ein Werkzeug, das bei Rauschen schweigt, ist die Voraussetzung dafür,
seinem Urteil bei echten Daten zu trauen.
"""

from __future__ import annotations

import inspect

import numpy as np
import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# Ereignisstudie
# ---------------------------------------------------------------------------
def _kursreihe(n: int = 400, sprung_bei: int | None = None,
               seed: int = 3) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    c = 100 * np.exp(np.cumsum(rng.normal(0.0002, 0.010, n)))
    if sprung_bei is not None:
        c[sprung_bei:] *= 1.8          # +80 % ab hier
    idx = pd.date_range("2023-01-01", periods=n, freq="B")
    return pd.DataFrame({"open": c, "high": c * 1.01, "low": c * 0.99,
                         "close": c, "volume": rng.lognormal(14, .3, n)},
                        index=idx)


class TestSperrzoneIstNichtOptional:
    """Ohne sie lernt das Modell, den Ausbruch an seinen ersten Tagen zu
    erkennen — trivial, und zum Handeln zu spät."""

    def test_standardwert_hat_eine_sperrzone(self):
        """Wer `EventConfig()` ohne Argumente nutzt, muss eine bekommen.

        Diesen Test hat der Mutationstest erzwungen: Die anderen Tests
        hier geben `blackout` explizit an und blieben deshalb grün, als
        die Mutation den Standardwert auf 0 setzte. Ein Test, der nur
        seine eigenen Argumente prüft, prüft die Voreinstellung nicht.
        """
        from alpaca_bot import events

        assert events.EventConfig().blackout >= 1, (
            "die Sperrzone ist laut Modul-Docstring 'nicht optional' - "
            "der Standardwert muss das abbilden")

    def test_beobachtungsfenster_endet_vor_der_sperrzone(self):
        from alpaca_bot import events

        df = _kursreihe(sprung_bei=250)
        cfg = events.EventConfig(threshold=0.30, window=40, lookback=60,
                                 blackout=5, min_dollar_volume=0)
        ev = events.find_events(df, cfg)
        assert len(ev), "der eingebaute Sprung muss gefunden werden"

        t0 = pd.Timestamp(ev.iloc[0]["t0"])
        fenster = events.observation_window(df, "TEST", t0, cfg)
        assert not fenster.empty
        letzter = pd.Timestamp(fenster.index[-1])
        abstand = len(df.loc[letzter:t0]) - 1
        assert abstand >= cfg.blackout, (
            f"das Fenster endet nur {abstand} Tage vor t0, die Sperrzone "
            f"verlangt {cfg.blackout}")

    def test_groessere_sperrzone_verschiebt_das_fenster_weiter_zurueck(self):
        from alpaca_bot import events

        df = _kursreihe(sprung_bei=250)
        basis = dict(threshold=0.30, window=40, lookback=60, min_dollar_volume=0)
        eng = events.EventConfig(blackout=2, **basis)
        weit = events.EventConfig(blackout=20, **basis)
        ev = events.find_events(df, eng)
        t0 = pd.Timestamp(ev.iloc[0]["t0"])

        ende_eng = pd.Timestamp(events.observation_window(df, "T", t0, eng).index[-1])
        ende_weit = pd.Timestamp(events.observation_window(df, "T", t0, weit).index[-1])
        assert ende_weit < ende_eng


class TestEreignisseUeberlappenNicht:
    def test_mindestabstand_wird_eingehalten(self):
        from alpaca_bot import events

        df = _kursreihe(n=600, sprung_bei=200)
        df.iloc[400:] *= 1.6            # zweiter Sprung
        cfg = events.EventConfig(threshold=0.30, window=40, lookback=60,
                                 blackout=5, min_dollar_volume=0)
        ev = events.find_events(df, cfg)
        if len(ev) < 2:
            pytest.skip("nur ein Ereignis gefunden")
        t0 = pd.DatetimeIndex(ev["t0"]).sort_values()
        abstaende = [len(df.loc[a:b]) - 1 for a, b in zip(t0[:-1], t0[1:])]
        assert min(abstaende) >= cfg.cooldown


class TestKontrollgruppe:
    """Ohne sie misst man nur, wie Aktien allgemein aussehen."""

    def test_leere_ereignisliste_stuerzt_nicht_ab(self):
        from alpaca_bot import events

        df = _kursreihe()
        cfg = events.EventConfig(min_dollar_volume=0)
        leer = events.find_events(df, cfg).head(0)
        assert len(events.sample_controls(df, leer, cfg, n_per_event=0)) == 0


# ---------------------------------------------------------------------------
# Reinforcement Learning
# ---------------------------------------------------------------------------
class TestTimingTestIstNichtAbschaltbar:
    """README nennt ihn als eine der fünf Sicherungen, CHARTER Regel 7
    verlangt ihn. Bis hierher war das eine Behauptung im Docstring."""

    def test_kein_schalter_um_den_aufruf(self):
        from alpaca_bot.rl import train

        quelle = inspect.getsource(train)
        i = quelle.index("timing_skill_test(frame[")
        umfeld = quelle[i - 300:i]
        # Erlaubt ist nur die Leerprüfung auf den Frame - kein Flag, kein
        # Konfigurationsschalter, kein `if cfg...`.
        assert "if cfg" not in umfeld and "if not disable" not in umfeld
        assert "skip_timing" not in quelle and "use_timing" not in quelle

    def test_ergebnis_traegt_das_timing_perzentil(self):
        from alpaca_bot.rl.train import FoldResult
        import dataclasses

        felder = {f.name for f in dataclasses.fields(FoldResult)}
        assert "timing_percentile" in felder, (
            "ohne dieses Feld kann das Urteil nicht daran haengen")

    def test_urteil_haengt_am_timing_nicht_an_der_rendite(self):
        from alpaca_bot.rl.train import TrainingReport

        quelle = inspect.getsource(TrainingReport.verdict)
        assert "timing" in quelle
        assert "95" in quelle, "die Schwelle gehoert ins Urteil"


class TestTimingTestMisstWasErBehauptet:
    """Die zyklische Verschiebung erhält alles außer der zeitlichen
    Ausrichtung - genau das macht sie zur fairen Messlatte."""

    def test_echtes_timing_wird_erkannt(self):
        """Eine Politik, die genau in den steigenden Tagen investiert ist,
        MUSS ein hohes Perzentil bekommen - sonst misst der Test nichts.

        Die Ausrichtung ist entscheidend: `total()` rechnet `e * ret`,
        das Exposure wirkt also auf DIESELBE Tagesrendite. Ein Hellseher
        setzt `exposure[i] = ret[i] > 0`. Beim Schreiben dieses Tests
        einmal um einen Tag verschoben - Ergebnis war Perzentil 2 statt
        100, also systematisch falsch investiert. Auch das ist ein
        korrektes Signal, nur eben das umgekehrte.
        """
        from alpaca_bot.rl.train import timing_skill_test

        rng = np.random.default_rng(1)
        n = 500
        ret = rng.normal(0, 0.01, n)
        idx = pd.date_range("2023-01-01", periods=n, freq="B")
        preise = pd.Series(100 * np.exp(np.cumsum(ret)), index=idx)
        exposure = pd.Series((ret > 0).astype(float), index=idx)

        r = timing_skill_test(exposure, preise, n_rotations=200)
        assert r["timing_percentile"] >= 95, (
            f"perfektes Timing muss erkannt werden, war "
            f"{r['timing_percentile']}")

    def test_systematisch_falsches_timing_faellt_auf(self):
        """Die Gegenprobe: um einen Tag verschoben investiert = sehr
        niedriges Perzentil. Ein Test, der nur nach oben ausschlaegt,
        koennte auch eine kaputte Konstante sein."""
        from alpaca_bot.rl.train import timing_skill_test

        rng = np.random.default_rng(1)
        n = 500
        ret = rng.normal(0, 0.01, n)
        idx = pd.date_range("2023-01-01", periods=n, freq="B")
        preise = pd.Series(100 * np.exp(np.cumsum(ret)), index=idx)
        exposure = pd.Series((np.roll(ret, -1) > 0).astype(float), index=idx)

        r = timing_skill_test(exposure, preise, n_rotations=200)
        assert r["timing_percentile"] < 20

    def test_zufaellige_politik_bekommt_kein_koennen_bescheinigt(self):
        """Der wichtigere Fall: Der Test darf nicht bei allem anschlagen."""
        from alpaca_bot.rl.train import timing_skill_test

        rng = np.random.default_rng(2)
        n = 500
        idx = pd.date_range("2023-01-01", periods=n, freq="B")
        preise = pd.Series(100 * np.exp(np.cumsum(rng.normal(0, 0.01, n))),
                           index=idx)
        exposure = pd.Series(rng.integers(0, 2, n).astype(float), index=idx)

        r = timing_skill_test(exposure, preise, n_rotations=200)
        assert r["timing_percentile"] < 95

    def test_konstante_position_hat_kein_timing(self):
        """Eine Dauerposition ist gegen Verschiebung invariant - ihr
        Perzentil darf kein Können vortaeuschen."""
        from alpaca_bot.rl.train import timing_skill_test

        rng = np.random.default_rng(3)
        n = 400
        idx = pd.date_range("2023-01-01", periods=n, freq="B")
        preise = pd.Series(100 * np.exp(np.cumsum(rng.normal(0.0005, 0.01, n))),
                           index=idx)
        exposure = pd.Series(np.ones(n), index=idx)

        r = timing_skill_test(exposure, preise, n_rotations=100)
        assert r["timing_percentile"] < 95


class TestFehlalarmquoteIstGemessen:
    """Wie oft schlaegt der Timing-Test auf reinem Rauschen an? (§G17)

    **Gemessen am 22.08.2026** ueber 400 Laeufe je Variante, reiner
    Random Walk ohne jedes Signal, realistische Agenten-Politiken:

        traege Politik (15 % Umschichtwahrscheinlichkeit)   8,5 %
        haeufige Politik (50 %)                             6,8 %
        Soll (Schwelle 95. Perzentil)                       5,0 %

    **Das ist kein Defekt, sondern eine Eigenschaft des Verfahrens.**
    Zyklisch rotierte Kopien einer traegen Positionsfolge sind
    untereinander korreliert - benachbarte Rotationen unterscheiden sich
    kaum. Die Nullverteilung wird dadurch zu eng, und der echte Wert
    liegt oefter am Rand, als der Zufall es hergeben duerfte. Derselbe
    Mechanismus wie bei den ueberlappenden Renditefenstern in §G12.

    Die Groessenordnung ist die des Projekts: §G12 nennt fuer die
    korrigierte Statistik 11 % gegen 5 % Soll und benennt das
    ausdruecklich als ehrliche Restunschaerfe. 7,8 % liegt darunter.

    **Geprueft wurde auch die naheliegende Ursache und verworfen:**
    `np.diff(e, prepend=0.0)` unterstellt jeder Rotation einen Kaltstart
    aus Position 0, den die echte Folge (env.reset) per Konstruktion hat.
    Der Effekt ist real (im Mittel 2,3 bps einmalig), aendert die
    Fehlalarmquote aber **nicht** (7,8 % mit und ohne). Deshalb wurde
    dort nichts geaendert - eine Korrektur ohne gemessene Wirkung waere
    Kosmetik.

    **Folge fuer die Nutzung:** Ein einzelner Lauf mit Perzentil ueber 95
    ist bei ~8 % Fehlalarmquote kein Nachweis. Genau das sagt
    `verdict()` auch: "Schwacher Hinweis auf Timing-Koennen, nicht
    belastbar. Mit anderen Startwerten, Symbolen und Zeitraeumen
    wiederholen."
    """

    def _politik(self, rng, n: int, p: float = 0.15) -> np.ndarray:
        e = np.zeros(n)
        akt = 0.0
        for i in range(n):
            if rng.random() < p:
                akt = rng.choice([0.0, 0.25, 0.5, 1.0])
            e[i] = akt
        return e

    def test_fehlalarmquote_bleibt_im_gemessenen_rahmen(self):
        """Bricht, wenn eine Aenderung den Test deutlich lockerer macht."""
        from alpaca_bot.rl.train import timing_skill_test

        treffer, N = 0, 120
        for s in range(N):
            rng = np.random.default_rng(s)
            n = 250
            ret = rng.normal(0, 0.012, n)
            idx = pd.date_range("2023-01-01", periods=n, freq="B")
            preise = pd.Series(100 * np.exp(np.cumsum(ret)), index=idx)
            exp = pd.Series(self._politik(rng, n), index=idx)
            r = timing_skill_test(exp, preise, n_rotations=100, seed=s)
            treffer += r["timing_percentile"] >= 95

        quote = treffer / N
        assert quote < 0.20, (
            f"Fehlalarmquote {quote:.1%} - gemessen wurden 8,5 % ueber 400 "
            f"Laeufe. Deutlich darueber heisst, der Test hat seine "
            f"Trennschaerfe verloren.")

    def test_urteil_nennt_einen_einzellauf_nicht_belastbar(self):
        """Bei ~8 % Fehlalarm darf ein einzelner Treffer nicht als
        Nachweis durchgehen."""
        from alpaca_bot.rl.train import TrainingReport

        quelle = inspect.getsource(TrainingReport.verdict)
        assert "nicht belastbar" in quelle
        assert "wiederholen" in quelle


class TestRLKetteLaeuftDurch:
    """Ein Werkzeug, das man nicht starten kann, ist toter Code."""

    def test_walk_forward_liefert_ein_urteil(self):
        from alpaca_bot import features
        from alpaca_bot.rl import DQNConfig, train_walk_forward
        from alpaca_bot.rl.env import EnvConfig, RewardConfig

        rng = np.random.default_rng(7)
        n = 900
        idx = pd.date_range("2020-01-01", periods=n, freq="B")
        c = 100 * np.exp(np.cumsum(rng.normal(0.0004, 0.014, n)))
        df = pd.DataFrame({"open": c, "high": c * 1.012, "low": c * 0.988,
                           "close": c, "volume": rng.lognormal(15, .3, n)},
                          index=idx)
        X = features.build_features(df).ffill().fillna(0.0)

        rep = train_walk_forward(
            X, df["close"], n_folds=2, episodes_per_fold=1, min_train=300,
            env_config=EnvConfig(reward=RewardConfig()),
            dqn_config=DQNConfig(), n_random=5, verbose=False)

        assert len(rep.folds) == 2
        t = rep.table()
        # Der Walk-Forward darf keine Trainingsdaten in den Test lassen.
        for _, f in t.iterrows():
            assert f["test_from"] > f["train_to"], (
                "Testfenster muss NACH dem Trainingsfenster liegen")
        assert t["timing_percentile"].notna().all(), (
            "jedes Fenster braucht sein Timing-Perzentil")

        urteil = rep.verdict()
        assert "TIMING-KOENNEN" in urteil
        assert "Marktbeteiligung" in urteil, (
            "die mittlere Beteiligung gehoert ins Urteil - eine Rendite "
            "aus hoher Beteiligung ist kein Timing")

    def test_merkmale_sind_zukunftsdicht(self):
        """Das Training steht und faellt damit - `08_train_rl.py` bricht
        bei undichten Merkmalen ab, hier wird es gesichert."""
        from alpaca_bot import features, pit

        rng = np.random.default_rng(4)
        n = 500
        c = 100 * np.exp(np.cumsum(rng.normal(0.0003, 0.012, n)))
        df = pd.DataFrame({"open": c, "high": c * 1.01, "low": c * 0.99,
                           "close": c, "volume": rng.lognormal(14, .3, n)},
                          index=pd.date_range("2023-01-01", periods=n, freq="B"))
        assert pit.audit_feature_function(features.build_features, df).clean
