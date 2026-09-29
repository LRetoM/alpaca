"""Der Musterspeicher als Lernschleife - was er beim taeglichen Lauf anrichtet.

**Anlass (22.08.2026).** `shadow.lernen` ruft seit §G14 taeglich
`patterns.kandidaten_suchen(anlegen=True)`. Die Tabelle `muster` war zu
diesem Zeitpunkt noch leer, weil das Anlegen erst ab 20 Handelstagen
greift und der Schatten bei 19 stand. Der Zustand war also unauffaellig -
und genau deshalb pruefbar, BEVOR er scharf wird.

Drei Defekte lagen bereit:

1. **Duplikate.** `erfassen()` vergibt eine frische `uuid4` und prueft
   nicht, ob dieselbe Bedingung schon existiert. Ab dem 20. Handelstag
   haette jeder Tag dieselben ~4 Regimeschnitte erneut angelegt.
2. **Wiederbelebung.** Ein als `zerfallen` markiertes Muster waere am
   naechsten Tag als frischer `kandidat` zurueckgekehrt. Der gesamte
   Verfallsmechanismus - der Kern des Moduls - waere wirkungslos
   gewesen.
3. **Ungezaehlte Versuche.** Jeder Regimeschnitt ist ein Vergleich.
   `hypotheses.erfassen` hebt dafuer den Versuchszaehler, `patterns`
   nicht. Damit waeren Vergleiche entstanden, die die Schwelle fuer
   niemanden anheben - §B2 auf den Kopf gestellt.

Alle drei sind dieselbe Fehlerklasse wie §G15: kein Absturz, keine
Meldung, nur eine still wachsende Tabelle und eine zu niedrige Huerde.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from alpaca_bot import patterns
from alpaca_bot.shadow import ShadowStore


@pytest.fixture
def store(tmp_path) -> ShadowStore:
    return ShadowStore(tmp_path / "shadow.sqlite")


class TestKeineDuplikate:
    """Dieselbe Bedingung darf nur EINMAL im Speicher stehen."""

    def test_zweimal_erfassen_legt_nur_ein_muster_an(self, store):
        a = patterns.erfassen("Umkehr bei ruhiger Vola",
                              "regime_vola == 'niedrig'", store=store)
        b = patterns.erfassen("Umkehr bei ruhiger Vola",
                              "regime_vola == 'niedrig'", store=store)
        assert a == b, "dieselbe Bedingung muss dieselbe muster_id liefern"
        assert len(store.table("muster")) == 1

    def test_taeglicher_lauf_laesst_die_tabelle_nicht_wachsen(self, store):
        """Der eigentliche Schadensfall: `lernen` laeuft jeden Handelstag."""
        for _ in range(10):
            patterns.erfassen("Umkehr bei ruhiger Vola",
                              "regime_vola == 'niedrig'", store=store)
        assert len(store.table("muster")) == 1, (
            "zehn Laeufe haetten zehn identische Muster angelegt")

    def test_verschiedene_bedingungen_bleiben_getrennt(self, store):
        patterns.erfassen("A", "regime_vola == 'niedrig'", store=store)
        patterns.erfassen("B", "regime_vola == 'hoch'", store=store)
        assert len(store.table("muster")) == 2

    def test_gleiche_bedingung_andere_wirkung_ist_ein_eigenes_muster(self, store):
        """Wirkung gehoert zum Schluessel - `ic_5d` und `rendite` sind
        zwei verschiedene Aussagen ueber dieselbe Bedingung."""
        patterns.erfassen("A", "regime_vola == 'niedrig'",
                          wirkung="ic_5d", store=store)
        patterns.erfassen("A", "regime_vola == 'niedrig'",
                          wirkung="rendite", store=store)
        assert len(store.table("muster")) == 2


class TestZerfallenBleibtZerfallen:
    """Der Verfallsmechanismus ist der Kern des Moduls - er darf nicht
    durch den naechsten Kandidatenlauf ausgehebelt werden."""

    def test_zerfallenes_muster_wird_nicht_wiederbelebt(self, store):
        mid = patterns.erfassen("Umkehr bei ruhiger Vola",
                                "regime_vola == 'niedrig'", store=store)
        with store._conn() as c:
            c.execute("UPDATE muster SET status='zerfallen' WHERE muster_id=?",
                      (mid,))

        wieder = patterns.erfassen("Umkehr bei ruhiger Vola",
                                   "regime_vola == 'niedrig'", store=store)
        assert wieder == mid
        status = store.table("muster").set_index("muster_id").loc[mid, "status"]
        assert status == "zerfallen", (
            "ein zerfallenes Muster als frischen Kandidaten zurueckzuholen "
            "macht die Verfallspruefung wirkungslos")

    def test_widerlegtes_muster_bleibt_widerlegt(self, store):
        mid = patterns.erfassen("A", "regime_markt == 'abwaerts'", store=store)
        with store._conn() as c:
            c.execute("UPDATE muster SET status='widerlegt' WHERE muster_id=?",
                      (mid,))
        patterns.erfassen("A", "regime_markt == 'abwaerts'", store=store)
        status = store.table("muster").set_index("muster_id").loc[mid, "status"]
        assert status == "widerlegt"


class TestJederSchnittIstEinVersuch:
    """§B2: Wer viele Schnitte prueft, findet in einem davon garantiert
    etwas. Die Schwelle muss das wissen."""

    def test_neues_muster_hebt_den_versuchszaehler(self, store):
        from alpaca_bot import fleet

        # Erst den Boden verlassen: `n_versuche` gibt bei leerer Datenbank
        # `max(1, ...)` zurueck, dort waere ein Zuwachs von 0 auf 1 nicht
        # sichtbar. Gemessen wird der Zuwachs, nicht der Absolutwert.
        patterns.erfassen("Vorlauf", "score > 0.9", store=store)
        vorher = fleet.n_versuche(store)
        patterns.erfassen("A", "regime_vola == 'niedrig'", store=store)
        assert fleet.n_versuche(store) == vorher + 1

    def test_duplikat_hebt_den_zaehler_NICHT(self, store):
        """Sonst wuerde ein taeglicher Lauf die Schwelle unbegrenzt
        hochtreiben und jede laufende Messung erdrosseln."""
        from alpaca_bot import fleet

        patterns.erfassen("A", "regime_vola == 'niedrig'", store=store)
        nach_erstem = fleet.n_versuche(store)
        for _ in range(5):
            patterns.erfassen("A", "regime_vola == 'niedrig'", store=store)
        assert fleet.n_versuche(store) == nach_erstem

    def test_zaehler_wirkt_auf_die_schwelle(self, store):
        from alpaca_bot import fleet

        vorher = fleet.schwelle_sigma(store)
        for i in range(8):
            patterns.erfassen(f"M{i}", f"regime_vola == 'v{i}'", store=store)
        assert fleet.schwelle_sigma(store) > vorher


class TestKandidatenSuchenIstGesteuert:
    """`anlegen=True` ist eine Betriebsentscheidung, keine Nebenwirkung."""

    def _datensatz(self, n_tage: int) -> pd.DataFrame:
        rng = np.random.default_rng(7)
        zeilen = []
        for tag in pd.date_range("2026-01-01", periods=n_tage, freq="B"):
            for _ in range(20):
                s = rng.random()
                zeilen.append({"tag": tag.date(), "score": s,
                               "fwd_5d": s * 0.01 + rng.normal(0, 0.03),
                               "regime_markt": "aufwaerts",
                               "regime_vola": "niedrig"})
        return pd.DataFrame(zeilen)

    def test_anlegen_false_legt_nichts_an(self, store, monkeypatch):
        monkeypatch.setattr("alpaca_bot.shadow_eval.datensatz",
                            lambda *a, **k: self._datensatz(30))
        patterns.kandidaten_suchen(store, anlegen=False, verbose=False)
        assert len(store.table("muster")) == 0

    def test_wiederholtes_anlegen_bleibt_stabil(self, store, monkeypatch):
        """Der Daemon ruft das taeglich. Nach dem zweiten Lauf darf keine
        einzige Zeile hinzukommen."""
        monkeypatch.setattr("alpaca_bot.shadow_eval.datensatz",
                            lambda *a, **k: self._datensatz(30))
        patterns.kandidaten_suchen(store, anlegen=True, verbose=False)
        nach_erstem = len(store.table("muster"))
        for _ in range(4):
            patterns.kandidaten_suchen(store, anlegen=True, verbose=False)
        assert len(store.table("muster")) == nach_erstem
        assert nach_erstem > 0, "der Testdatensatz sollte Kandidaten liefern"


class TestFokusZahlenKommenAusDenQuellen:
    """Keine abgeschriebenen Zahlen im Anzeigetext (§3.2-Prinzip).

    `fokus.hebel()` trug bis zum 22.08.2026 den Satz "Der Bot handelt
    1.200 von 2.189 liquiden Symbolen" fest im Rumpf. Die zweite Zahl war
    zu diesem Zeitpunkt bereits falsch: `universum.csv` enthaelt **2.168**
    Symbole. §G11 Fund 3 nennt ebenfalls 2.168, waehrend §H 2.189 fuehrt -
    die Zahl war beim Abschreiben gedriftet.

    `docs/BETRIEBSPLAN.md` §3.2 begruendet dasselbe Prinzip fuer die
    Signifikanzschwelle: "Hier steht bewusst keine Zahl. Eine
    abgeschriebene Zahl im Dokument waere nach der naechsten Anmeldung
    falsch." Fuer den Code gilt es genauso.
    """

    def test_breite_liest_die_skript_voreinstellung(self):
        from alpaca_bot import fokus

        gehandelt, _ = fokus._breite()
        assert gehandelt is not None
        quelle = __import__("pathlib").Path("scripts/12_daemon.py").read_text()
        assert f"default={gehandelt}" in quelle, (
            "die gehandelte Symbolzahl muss die Voreinstellung sein, die "
            "der Dienst tatsaechlich startet")

    def test_breite_zaehlt_das_echte_universum(self):
        import pandas as pd
        from alpaca_bot import fokus
        from alpaca_bot.universe import UNIVERSE_FILE

        _, verfuegbar = fokus._breite()
        if not UNIVERSE_FILE.exists():
            pytest.skip("universum.csv nicht vorhanden")
        echt = len(pd.read_csv(UNIVERSE_FILE)["symbol"].dropna().unique())
        assert verfuegbar == echt

    def test_keine_festen_symbolzahlen_im_hebeltext(self):
        import inspect
        from alpaca_bot import fokus

        quelle = inspect.getsource(fokus.hebel)
        for zahl in ("2.189", "2189", "1.200 von", "969"):
            assert zahl not in quelle, (
                f"{zahl!r} steht wieder fest im Text - sie driftet still, "
                "sobald sich die Quelle aendert")

    def test_hebeltext_bleibt_lesbar(self):
        """Tausenderpunkte duerfen keine Satzkommas fressen."""
        from alpaca_bot import fokus

        text = " ".join(fokus.hebel())
        assert "da. der" not in text and "Frage. die" not in text


class TestVorzeichenstabilitaetIstVerdrahtet:
    """Das Kriterium, auf dem `ReversalWeights` steht (§G16).

    §G12 hat den t-Wert der tragenden Faktoren entwertet (`rsi2` und
    `reversal_3d` halten die Schwelle nach Korrektur nicht mehr). Was den
    Befund dennoch traegt, benennt §G12 ausdruecklich: die
    **Vorzeichenstabilitaet je Jahr** - "100 % positive Jahre", ein
    robusteres Kriterium, das von der Korrektur unberuehrt bleibt.

    `research.measure_stability` misst genau das und wurde von KEINEM
    Skript aufgerufen. Das Kriterium, auf dem die Strategie steht, war
    damit aus dem laufenden Werkzeug nicht reproduzierbar.
    """

    def test_factor_lab_ruft_die_stabilitaetsmessung(self):
        quelle = __import__("pathlib").Path("scripts/11_factor_lab.py").read_text()
        assert "measure_stability" in quelle, (
            "das Kriterium aus §G12 muss im Werkzeug laufen, nicht nur in "
            "einem einmaligen Messlauf von Hand")
        assert "stability_report" in quelle

    def test_zusammenfassung_nutzt_den_korrigierten_t_wert(self):
        """Zwei Schwellen in derselben Ausgabe - die laxere stand in der
        Zeile, die zitiert wird."""
        quelle = __import__("pathlib").Path("scripts/11_factor_lab.py").read_text()
        block = quelle[quelle.index("SCHRITT 4"):]
        assert 'results["t_stat"] >= 3.0' not in block, (
            "`select_factors` prueft t_korrigiert - die Anzeige daneben "
            "muss dieselbe Schwelle verwenden")
        assert "t_korrigiert" in block
