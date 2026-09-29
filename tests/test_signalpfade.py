"""Rechnen Historienlauf und Schatten denselben Score? (§G24)

**Der Fund vom 23.08.2026.** Anlass war der Einwand, die historischen
Testtrades bildeten die laufende Strategie nicht ab. Er trifft zu.

Beide Pfade rufen `signals.build_reversal_frame`, aber verschieden:

    simulate.py:191   build_reversal_frame(df, market, weights)
    shadow_daten.py   build_reversal_frame(df, market, weights,
                                           symbol=s, news=news)

`ReversalWeights.news = 0.10` ist ein ADDITIVER Score-Baustein. Fehlt
`news`, ist `f_news = 0` und der Faktor entfaellt ersatzlos. Gemessen an
acht echten Symbolen mit echten Nachrichtendaten: **sechs bekommen einen
anderen Score**, bis zu +0,1000 - und die Rangfolge dreht sich:

    simulate.py :  CW   WMT  BABA  TJX  TTMI  AGX  VICR  FN
    shadow/live :  WMT  CW   TJX   TTMI BABA  FN   AGX   VICR

Der Bot kauft die obersten Plaetze. Andere Reihenfolge heisst andere
Aktien im Depot.

**Warum es niemand fand:** `shadow.pruefungen()` Nr. 6 heisst "Replay
gegen simulate.py" und versprach im Docstring, genau das zu vergleichen.
Die Umsetzung startete `simulate.run()`, zaehlte Trades und meldete
`True`, sofern nichts abstuerzte - ein Durchlauftest, als Vergleich
beschriftet. Dieselbe Fehlerklasse wie §G17 und §G19.

**Nicht nachruestbar:** Der Nachrichtenfeed reicht nicht bis 2021
zurueck. Die Historienzahlen aus §G11 gelten fuer die
Vier-Faktor-Fassung, nicht fuer die laufende - das muss sichtbar
bleiben, nicht behoben werden.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from alpaca_bot.signals import ReversalWeights, build_reversal_frame

IDX = pd.date_range("2024-01-01", periods=300, freq="B", tz="UTC")


def _bars(seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    c = 100 * np.exp(np.cumsum(rng.normal(0.0, 0.015, len(IDX))))
    c[-3:] = c[-4] * np.array([0.96, 0.93, 0.90])       # Umkehr-Setup
    return pd.DataFrame({"open": c, "high": c * 1.01, "low": c * 0.99,
                         "close": c, "volume": np.full(len(IDX), 5e6)},
                        index=IDX)


def _artikel(n: int = 40) -> pd.DataFrame:
    """Artikel-Rohdaten im Schema von `news.get_news()`.

    `symbols` ist eine LISTE je Artikel - eine Meldung deckt oft mehrere
    Werte ab. Genau deshalb verlangt `build_reversal_frame` zusammen mit
    `news` auch `symbol=`: Ohne den Filter zaehlte jede Meldung fuer
    jedes Symbol.
    """
    tage = IDX[-n:]
    return pd.DataFrame({
        "timestamp": tage,
        "updated_at": tage,
        "symbols": [["X", "Y"]] * n,
        "headline": [f"Meldung {i}" for i in range(n)],
        "summary": [""] * n,
        "source": ["test"] * n,
        "author": ["test"] * n,
        "url": [""] * n,
        "id": list(range(n)),
    })


class TestNewsFaktorWirkt:
    """Das Gewicht ist 0,10 - und es ist additiv, nicht kosmetisch."""

    def test_gewicht_ist_nicht_null(self):
        assert ReversalWeights().news == pytest.approx(0.10), (
            "Wird der Faktor auf 0 gesetzt, verschwindet der Unterschied "
            "zwischen Historienlauf und Schatten - dann ist §G24 erledigt "
            "und dieser Test darf angepasst werden."
        )

    def test_ohne_news_kein_beitrag(self):
        """Der simulate.py-Aufruf: kein Gate, kein Abzug, kein Beitrag."""
        f = build_reversal_frame(_bars(), None, ReversalWeights())
        assert f["f_news"].iloc[-1] == 0.0
        assert pd.isna(f["news_z"].iloc[-1])

    def test_mit_news_anderer_score(self):
        """DER Fund: derselbe Kurs, zwei Aufrufe, zwei Scores."""
        df = _bars()
        w = ReversalWeights()
        ohne = float(build_reversal_frame(df, None, w)["score"].iloc[-1])
        mit = float(build_reversal_frame(df, None, w, symbol="X",
                                         news=_artikel())["score"].iloc[-1])
        assert mit > ohne, (
            "Der Nachrichtenfaktor ist additiv - mit Artikeln muss der "
            "Score hoeher liegen. Sonst greift er nicht, und §G24 waere "
            "gegenstandslos."
        )
        assert mit - ohne <= w.news + 1e-9, (
            "Der Beitrag darf das Gewicht nie ueberschreiten."
        )

    def test_beitrag_ist_gedeckelt(self):
        """`f_news` ist auf 0..1 geklemmt - kein unbegrenzter Hebel."""
        df = _bars()
        w = ReversalWeights()
        viel = build_reversal_frame(df, None, w, symbol="X",
                                    news=_artikel(200))
        assert 0.0 <= float(viel["f_news"].iloc[-1]) <= 1.0

    def test_rangfolge_kann_kippen(self):
        """Nur ein Symbol mit Nachrichten reicht, um die Reihenfolge zu drehen."""
        w = ReversalWeights()
        a, b = _bars(1), _bars(2)
        # Ohne Nachrichten: fester Abstand. Mit Nachrichten fuer den
        # Zweitplatzierten kann er ihn ueberholen.
        sa = float(build_reversal_frame(a, None, w)["score"].iloc[-1])
        sb = float(build_reversal_frame(b, None, w)["score"].iloc[-1])
        schwaecher, staerker = (b, a) if sa >= sb else (a, b)
        neu = float(build_reversal_frame(schwaecher, None, w, symbol="X",
                                         news=_artikel(200))["score"].iloc[-1])
        alt_stark = max(sa, sb)
        assert neu != min(sa, sb), "Der Faktor muss den Score veraendern"
        # Ob er ueberholt, haengt vom Abstand ab - der Test haelt fest, DASS
        # ein Ueberholen moeglich ist, sobald der Abstand unter 0,10 liegt.
        if alt_stark - min(sa, sb) < w.news:
            assert neu > alt_stark, (
                "Bei einem Abstand unter dem News-Gewicht MUSS der "
                "Zweitplatzierte ueberholen koennen - genau so drehte sich "
                "die Rangfolge in §G24."
            )


class TestSimulateUndSchattenRufenVerschieden:
    """Der Unterschied steht im Quelltext und muss sichtbar bleiben."""

    def test_simulate_uebergibt_kein_news(self):
        from pathlib import Path

        from alpaca_bot.config import PROJECT_ROOT

        quelle = (Path(PROJECT_ROOT) / "src" / "alpaca_bot"
                  / "simulate.py").read_text()
        assert "build_reversal_frame(df, market, ecfg.reversal_weights)" in quelle, (
            "Wenn `simulate.py` hier geaendert wurde, ist §G24 entweder "
            "behoben oder verschoben - beides gehoert nachgetragen, bevor "
            "die Historienzahlen wieder als Messung der laufenden Strategie "
            "zitiert werden."
        )

    def test_schatten_uebergibt_news(self):
        from pathlib import Path

        from alpaca_bot.config import PROJECT_ROOT

        quelle = (Path(PROJECT_ROOT) / "src" / "alpaca_bot"
                  / "shadow_daten.py").read_text()
        assert "symbol=s, news=news" in quelle


class TestReplayPruefungVergleichtWirklich:
    """Sie hiess 'Replay', prueft aber bis 23.08.2026 nur Lauffaehigkeit."""

    def test_pruefung_vergleicht_scores_nicht_nur_lauffaehigkeit(self):
        import inspect

        from alpaca_bot import shadow_pruefung as sp

        quelle = inspect.getsource(sp._pruefe_replay)
        assert "build_reversal_frame" in quelle, (
            "Die Pruefung muss die SCORES beider Pfade vergleichen. Bis zum "
            "23.08.2026 startete sie `simulate.run()`, zaehlte die Trades "
            "und meldete True, sofern nichts abstuerzte."
        )
        assert "abweichungen" in quelle

    def test_meldet_die_ursache_nicht_nur_die_abweichung(self):
        import inspect

        from alpaca_bot import shadow_pruefung as sp

        quelle = inspect.getsource(sp._pruefe_replay)
        assert "news" in quelle and "G24" in quelle, (
            "Ein Befund ohne Ursache wird als Rauschen abgetan - die "
            "Meldung muss den Nachrichtenfaktor benennen."
        )
