"""Der 24/7-Schattenbetrieb: keine Leerarbeit, kein Scheinlernen (§G14).

Zwei Befunde vom 22.08.2026, die zusammengehoeren:

1. Der Dauerbetrieb rechnete stuendlich alle 19.788 offenen Vorhersagen
   neu, obwohl sich ohne neue Tagesbar nichts aendern kann.
2. Der Musterspeicher - die eigentliche Lernschleife - wurde NIE
   aufgerufen. Die Tabelle `muster` hatte null Zeilen.

Der zweite Punkt ist der wichtigere: Das System konnte lernen, tat es
aber nicht. Und haette man es unbesehen angeschaltet, haette es auf
unkorrigierten t-Werten (§G12) rund um die Uhr Scheinmuster erzeugt.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


class TestICKorrigiertDieUeberlappung:
    """`shadow_eval.ic` - die Kennzahl, nach der die Flotte beurteilt wird."""

    def _datensatz(self, n_tage: int, seed: int = 3) -> pd.DataFrame:
        rng = np.random.default_rng(seed)
        zeilen = []
        for tag in pd.date_range("2024-01-01", periods=n_tage, freq="B"):
            for _ in range(20):
                score = rng.random()
                zeilen.append({"tag": tag.date(), "score": score,
                               "fwd_5d": score * 0.01 + rng.normal(0, 0.03),
                               "fwd_1d": score * 0.01 + rng.normal(0, 0.03)})
        return pd.DataFrame(zeilen)

    def test_horizont_1_bleibt_unkorrigiert(self):
        """Kontrollfall: ohne Ueberlappung darf sich nichts aendern."""
        from alpaca_bot.shadow_eval import ic

        k = ic(self._datensatz(60), "fwd_1d")
        assert k["aufblaehung"] == 1.0
        assert k["t"] == k["t_roh"]

    def test_horizont_5_wird_korrigiert_und_zeigt_beides(self):
        from alpaca_bot.shadow_eval import ic

        k = ic(self._datensatz(60), "fwd_5d")
        assert "t_roh" in k and "aufblaehung" in k
        assert np.isfinite(k["t"])

    def test_zu_wenige_tage_liefern_KEINEN_t_wert(self):
        """Der gefaehrlichste Fall - und der Grund fuer diesen Test.

        Am 22.08.2026 lieferte `ic` fuer `fwd_10d` ueber nur 8
        Handelstage ein korrigiertes t von **14,57** gegen ein rohes von
        5,30. Der Newey-West-Schaetzer entartet, wenn die Reihe kuerzer
        ist als ein paar unabhaengige Bloecke - und das Ergebnis sieht
        dann nicht falsch aus, sondern spektakulaer.

        Richtig ist: kein t-Wert. Und ausdruecklich NICHT ersatzweise der
        rohe - der waere die optimistischste aller Antworten.
        """
        from alpaca_bot.shadow_eval import ic

        k = ic(self._datensatz(8), "fwd_5d")
        assert not np.isfinite(k["t"]), "kein gueltiger t-Wert bei 8 Tagen"
        assert k["t"] != k.get("t_roh"), "der rohe darf nicht einspringen"
        assert "hinweis" in k and "zu wenig" in k["hinweis"]

    def test_bericht_nennt_den_rohen_wert_als_nicht_zitierbar(self):
        from alpaca_bot import shadow_eval
        import inspect

        quelle = inspect.getsource(shadow_eval.bericht)
        assert "NICHT zitieren" in quelle


class TestMusterspeicherRechnetKorrigiert:
    """`patterns._messen` - hieran haengt, ob ein Muster als bestaetigt gilt."""

    def test_messen_nutzt_den_gruppierten_test_mit_horizont(self):
        from alpaca_bot import patterns
        import inspect

        quelle = inspect.getsource(patterns._messen)
        assert "horizont=h" in quelle, (
            "ohne Horizont waeren rund 40 % der bestaetigten Muster Rauschen")

    def test_zu_wenige_tage_bestaetigen_kein_muster(self):
        from alpaca_bot.patterns import _messen

        rng = np.random.default_rng(5)
        df = pd.DataFrame({
            "tag": np.repeat(pd.date_range("2024-01-01", periods=6, freq="B"), 10),
            "fwd_5d": rng.normal(0.01, 0.02, 60),
            "regime_vola": "niedrig",
        })
        r = _messen(df, "regime_vola == 'niedrig'", "rendite")
        assert not np.isfinite(r["t"])


class TestLernschrittImDauerbetrieb:
    """`shadow.lernen` - der Schritt, den es vorher nicht gab."""

    def test_daemon_ruft_den_lernschritt(self):
        """Die eigentliche Luecke: gebaut, aber nie aufgerufen."""
        quelle = __import__("pathlib").Path("scripts/16_shadow_daemon.py").read_text()
        assert '"gelernt", lernen' in quelle

    def test_lernen_steht_hinter_den_erzeugenden_schritten(self):
        """Zuerst gerufen saehe es immer den Stand von gestern."""
        quelle = __import__("pathlib").Path("scripts/16_shadow_daemon.py").read_text()
        assert quelle.index('"entschieden", entscheiden') < quelle.index('"gelernt", lernen')

    def test_ohne_neuen_handelstag_passiert_nichts(self, tmp_path, monkeypatch):
        """Idempotenz: zweimal am selben Tag darf nichts kosten."""
        from alpaca_bot.shadow import ShadowConfig, ShadowStore, lernen

        store = ShadowStore(tmp_path / "s.sqlite")
        with store._conn() as c:
            c.execute(
                "INSERT INTO predictions (pred_id, run_id, bot_id, buch, as_of,"
                " decided_at, symbol, aktion, decision_price, code_version, score)"
                " VALUES ('p1','r1','B00','rangliste','2026-08-21',"
                "'2026-08-21T20:00:00+00:00','AAPL','buy',100.0,'abc',0.9)")
        store.setze_lerntag("2026-08-21")

        gerufen = []
        import alpaca_bot.patterns as pat
        monkeypatch.setattr(pat, "pruefen", lambda *a, **k: gerufen.append("p"))
        monkeypatch.setattr(pat, "kandidaten_suchen", lambda *a, **k: gerufen.append("k"))

        n = lernen(ShadowConfig(), store, verbose=False)
        assert n == 0 and gerufen == []

    def test_merker_ueberlebt_neustart(self, tmp_path):
        """Der Lerntag muss auf Platte liegen, nicht im Prozess."""
        from alpaca_bot.shadow import ShadowStore

        pfad = tmp_path / "s.sqlite"
        ShadowStore(pfad).setze_lerntag("2026-08-21")
        assert ShadowStore(pfad).letzter_lerntag() == "2026-08-21"

    def test_nie_gelernt_liefert_leeren_string(self, tmp_path):
        from alpaca_bot.shadow import ShadowStore

        assert ShadowStore(tmp_path / "s.sqlite").letzter_lerntag() == ""


class TestVerifizierenRechnetNichtDoppelt:
    """Der Aktualitaetsfilter - 19.788 Vorhersagen, 24-mal am Tag."""

    def test_filter_vergleicht_gegen_den_neuesten_bar(self):
        """Nicht gegen die Uhrzeit: am Wochenende kommt keine Bar dazu."""
        from alpaca_bot import shadow
        import inspect

        quelle = inspect.getsource(shadow.verifizieren)
        assert "neuester_bar" in quelle
        assert "bewertet > neuester_bar" in quelle

    def test_offene_ergebnisse_liefert_evaluated_at(self):
        from alpaca_bot import shadow
        import inspect

        quelle = inspect.getsource(shadow.ShadowStore.offene_ergebnisse)
        assert "evaluated_at" in quelle
