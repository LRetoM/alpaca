"""Das Risiko-Dach darf keine Position stillschweigend verlieren (§G18).

**Anlass (22.08.2026).** `risiko._kennzahlen` und `risiko.sektor_anteile`
rechneten den Positionswert als:

    abs(float(r["qty"]) * float(r.get("current_price") or 0))

umschlossen von `except (TypeError, ValueError): continue`.

Zwei Wege, auf denen eine Position **still** aus der Risikorechnung
verschwindet:

  * `current_price` ist `None` -> `or 0` macht daraus Wert **0**,
    ganz ohne Exception. `account.positions()` setzt das Feld
    ausdrücklich auf `None`, wenn Alpaca keinen Kurs liefert (etwa bei
    einer Handelsaussetzung).
  * `qty` unlesbar -> `except ... continue`, die Zeile fällt raus.

Gemessen an drei Positionen à 30.000 $ auf 100.000 $ Konto:

    alle Werte lesbar      Positionswert 90.000    Exposure 90 %
    ein Kurs fehlt         Positionswert 60.000    Exposure 60 %
    eine Menge unlesbar    Positionswert 60.000    Exposure 60 %

Die Klumpenkontrolle verschiebt sich mit: Sektoranteil 90 % -> 60 %.

**Das Dach unterschätzt damit und lässt Käufe zu, die es sonst
blockiert hätte** - der genaue Gegensatz zu seinem eigenen Grundsatz:

    "Fällt die Risikoprüfung selbst aus, wird nicht gehandelt.
     Ein Risiko-Dach, das im Zweifel durchlässt, ist keines."

Und `sektor_anteile` schreibt dasselbe Prinzip eine Ebene höher schon
auf: *"Symbole ohne Sektorangabe zählen unter 'unbekannt' - sie
verschwinden nicht stillschweigend, sonst sähe ein Depot ohne
Sektordaten wie ein perfekt gestreutes aus."* Für die **Zahlen** galt
das bisher nicht.
"""

from __future__ import annotations

import pandas as pd
import pytest

from alpaca_bot import risiko


def _depot(**abweichung) -> pd.DataFrame:
    """Drei Positionen à 30.000 $, optional eine mit kaputtem Feld."""
    df = pd.DataFrame(
        {"qty": [100.0, 100.0, 100.0],
         "current_price": [300.0, 300.0, 300.0],
         "avg_entry": [280.0, 280.0, 280.0],
         "market_value": [30000.0, 30000.0, 30000.0]},
        index=pd.Index(["A", "B", "C"], name="symbol"),
    ).astype(object)
    for spalte, wert in abweichung.items():
        df.loc["C", spalte] = wert
    return df


class FakeStore:
    def einzahlungen_summe(self): return 0.0
    def kapital_verlauf(self, tage=90): return pd.DataFrame()


KONTO = {"equity": 100_000.0, "portfolio_value": 100_000.0,
         "cash": 10_000.0, "last_equity": 100_000.0}


class TestPositionenVerschwindenNicht:
    def test_fehlender_kurs_faellt_auf_market_value_zurueck(self):
        k = risiko._kennzahlen(KONTO, _depot(current_price=None), FakeStore())
        assert k["positionswert"] == pytest.approx(90_000, abs=1), (
            "market_value liegt vor - die Position darf nicht mit 0 zaehlen")
        assert k["exposure"] == pytest.approx(0.90, abs=0.01)

    def test_ohne_kurs_und_marktwert_gilt_der_einstand(self):
        """Der Einstand ist eine konservative Untergrenze - besser als 0."""
        k = risiko._kennzahlen(
            KONTO, _depot(current_price=None, market_value=None), FakeStore())
        assert k["positionswert"] == pytest.approx(88_000, abs=1), (
            "60.000 + 100 x 280 Einstand")

    def test_unlesbare_menge_nutzt_trotzdem_den_marktwert(self):
        """Solange EINE Quelle traegt, ist die Position bewertbar."""
        k = risiko._kennzahlen(KONTO, _depot(qty="n/a"), FakeStore())
        assert k["n_unbewertbar"] == 0
        assert k["positionswert"] == pytest.approx(90_000, abs=1)

    def test_erst_ohne_jede_quelle_ist_sie_unbewertbar(self):
        """Der Ernstfall: weder Marktwert noch Kurs noch Einstand."""
        k = risiko._kennzahlen(
            KONTO, _depot(qty="n/a", market_value=None,
                          current_price=None, avg_entry=None), FakeStore())
        assert k["n_unbewertbar"] == 1
        assert "C" in k["unbewertbar"]
        assert k["positionswert"] == pytest.approx(60_000, abs=1), (
            "die uebrigen zwei zaehlen normal weiter")

    def test_gesundes_depot_meldet_nichts(self):
        k = risiko._kennzahlen(KONTO, _depot(), FakeStore())
        assert k["n_unbewertbar"] == 0
        assert k["positionswert"] == pytest.approx(90_000, abs=1)


class TestKlumpenkontrolleVerliertNichts:
    def test_sektoranteil_bleibt_vollstaendig(self):
        sek = {"A": "Tech", "B": "Tech", "C": "Tech"}
        a = risiko.sektor_anteile(_depot(current_price=None), sek, 100_000.0)
        assert a["Tech"] == pytest.approx(0.90, abs=0.01), (
            "eine Position ohne Kurs darf den Sektoranteil nicht druecken - "
            "sonst sieht ein Klumpen wie Streuung aus")

    def test_unbewertbare_position_zaehlt_unter_unbewertbar(self):
        sek = {"A": "Tech", "B": "Tech", "C": "Tech"}
        a = risiko.sektor_anteile(
            _depot(qty="n/a", market_value=None, current_price=None,
                   avg_entry=None), sek, 100_000.0)
        assert "unbewertbar" in a, (
            "wie bei fehlenden Sektordaten: sichtbar bleiben, nicht "
            "stillschweigend verschwinden")


class TestImZweifelWirdNichtGekauft:
    """Der Grundsatz aus dem Modul-Docstring, jetzt auch fuer die Zahlen."""

    def _freigabe(self, depot, seite="buy"):
        class S(FakeStore):
            def sperre_lesen(self): return {"aktiv": 0}
        return risiko.pruefe_order("X", seite, 1_000.0, konto=KONTO,
                                   positionen=depot, store=S())

    def test_unbewertbare_position_blockiert_neukauf(self):
        f = self._freigabe(_depot(qty="n/a", market_value=None,
                                  current_price=None, avg_entry=None))
        assert not f.ok
        # Der Grund muss die Position NENNEN und sagen, warum blockiert
        # wird - `blocked_by="RiskError"` allein ist im Nachhinein wertlos
        # (siehe Freigabe.gruende).
        text = " ".join(f.gruende)
        assert "bestimmbaren Wert" in text, f.gruende
        assert "C" in text, "die betroffene Position gehoert in die Meldung"
        assert "Verkaeufe bleiben erlaubt" in text

    def test_verkauf_bleibt_immer_erlaubt(self):
        """Eine Sperre darf nie zur Falle werden - auch diese nicht."""
        assert self._freigabe(
            _depot(qty="n/a", market_value=None, current_price=None,
                   avg_entry=None), seite="sell").ok

    def test_gesundes_depot_wird_nicht_blockiert(self):
        assert self._freigabe(_depot()).ok


class TestRohprotokollMeldetSeinenAusfall:
    """Die JSONL-Sicherung darf nicht still verschwinden (§G18).

    `journal.py` beschreibt die Aufgabenteilung selbst: *"SQLite ist die
    Auswertungsschicht, JSONL die Sicherung - wäre die Datenbank je
    beschädigt, ließe sie sich daraus vollständig rekonstruieren."*

    `_write_raw` fing OSError/ValueError mit `pass` ab. Ein voller
    Datenträger oder eine entzogene Schreibberechtigung wäre erst
    aufgefallen, wenn man die Sicherung BRAUCHT — die Fehlerklasse aus
    §G15 in ihrer teuersten Form.
    """

    def _logger(self, tmp_path):
        from alpaca_bot.journal import Journal

        j = Journal(tmp_path / "j.sqlite")
        with j.run("test") as run:
            return run

    def test_ausfall_wird_gemeldet(self, tmp_path, capsys):
        run = self._logger(tmp_path)

        class KaputterStrom:
            def write(self, *a): raise OSError("No space left on device")
            def flush(self): pass

        run._raw = KaputterStrom()
        run.log("irgendwas", wert=1)

        ausgabe = capsys.readouterr().out
        assert "ROHPROTOKOLL" in ausgabe, (
            "eine ausgefallene Sicherung muss sich melden")
        assert "No space left" in ausgabe, "die Ursache gehoert dazu"

    def test_meldung_nur_einmal_je_lauf(self, tmp_path, capsys):
        """Laerm wird ueberlesen - dieselbe Lehre wie beim Feld-Waechter."""
        run = self._logger(tmp_path)

        class KaputterStrom:
            def write(self, *a): raise OSError("kaputt")
            def flush(self): pass

        run._raw = KaputterStrom()
        for _ in range(5):
            run.log("wiederholt")
        assert capsys.readouterr().out.count("ROHPROTOKOLL") == 1

    def test_handel_laeuft_weiter(self, tmp_path):
        """Der Ausfall darf nie zum Abbruch fuehren."""
        run = self._logger(tmp_path)

        class KaputterStrom:
            def write(self, *a): raise OSError("kaputt")
            def flush(self): pass

        run._raw = KaputterStrom()
        did = run.decision("AAPL", "buy", reasons={"score": 0.9})
        assert did, "die Entscheidung muss trotzdem in SQLite landen"


class TestEarningsRechnetKorrigiert:
    """Die letzte Stelle ohne Ueberlappungskorrektur (§G12/§G18)."""

    def _panel(self, n_tage: int = 300, n_sym: int = 40, seed: int = 5):
        import numpy as np

        rng = np.random.default_rng(seed)
        idx = pd.date_range("2022-01-01", periods=n_tage, freq="B")
        spalten = [f"S{i:02d}" for i in range(n_sym)]
        f = pd.DataFrame(rng.normal(size=(n_tage, n_sym)), index=idx,
                         columns=spalten)
        roh = pd.DataFrame(rng.normal(0, 0.02, size=(n_tage + 20, n_sym)),
                           index=pd.date_range("2022-01-01",
                                               periods=n_tage + 20, freq="B"),
                           columns=spalten)
        # gleitendes 20-Tage-Fenster = starke Ueberlappung
        r = roh.rolling(20).sum().iloc[20:].set_axis(idx) + 0.12 * f
        return f, r

    def test_horizont_wird_verwendet(self):
        import inspect
        from alpaca_bot import earnings

        rumpf = inspect.getsource(earnings.kennzahlen).split('"""')[-1]
        assert "horizont" in rumpf and "newey_west_t" in rumpf

    def test_korrigierter_wert_liegt_unter_dem_rohen(self):
        import numpy as np
        from alpaca_bot import earnings

        f, r = self._panel()
        k = earnings.kennzahlen(f, r, horizont=20)
        assert np.isfinite(k["t"])
        assert abs(k["t"]) < abs(k["t_roh"]), (
            "bei einem 20-Tage-Fenster MUSS korrigiert werden")

    def test_horizont_1_bleibt_unveraendert(self):
        from alpaca_bot import earnings

        f, r = self._panel()
        k = earnings.kennzahlen(f, r, horizont=1)
        assert k["t"] == pytest.approx(k["t_roh"], abs=1e-9)

    def test_faktortest_reicht_den_horizont_durch(self):
        quelle = __import__("pathlib").Path("scripts/19_faktor_tests.py").read_text()
        assert "horizont=h" in quelle, (
            "der Horizont war immer bekannt - er wurde nur nachtraeglich "
            "ins Ergebnis geschrieben statt in die Rechnung")
