"""Nutzungsnachweis: laeuft wirklich alles, was gebaut wurde? (§G15)

REGRESSION 22.08.2026. Drei Bausteine innerhalb weniger Tage waren
fertig gebaut und liefen nie - ohne dass irgendetwas abstuerzte:

    Bar-Cache        `use_cache=True` rief niemand auf   (§G11)
    Musterspeicher   Tabelle `muster`: null Zeilen       (§G14)
    Kontext@topup    haengt nur an `buy`                 (§G13)

Diese Tests sichern die vier Erkennungsarten. Jede fuer sich, denn
keine findet die andere.
"""

from __future__ import annotations

import datetime as dt

import pytest


@pytest.fixture
def db(tmp_path):
    return tmp_path / "n.sqlite"


def _erwartung(**kw):
    from alpaca_bot.nutzung import Erwartung

    basis = {"baustein": "test.baustein", "zweck": "etwas Wichtiges",
             "hoechstens_stunden": 26}
    return (Erwartung(**{**basis, **kw}),)


class TestVierArtenDesStillenAusfalls:

    def test_nie_gelaufen_wird_erkannt(self, db):
        """Der haeufigste Fall: nirgends verdrahtet."""
        from alpaca_bot import nutzung

        b = nutzung.pruefen(_erwartung(), db=db)[0]
        assert b.art == "nie_gelaufen"
        assert not b.ok
        assert "nirgends" in b.detail

    def test_zu_selten_wird_erkannt(self, db):
        """Ein Schritt, der stumm scheitert, meldet sich einfach nicht mehr."""
        from alpaca_bot import nutzung

        jetzt = dt.datetime(2026, 8, 22, 12, tzinfo=dt.UTC)
        with nutzung._conn(db) as c:
            c.execute("INSERT INTO laeufe (baustein, ts, ergebnis, signatur)"
                      " VALUES ('test.baustein',?,5,'a')",
                      ((jetzt - dt.timedelta(hours=40)).isoformat(),))
        b = nutzung.pruefen(_erwartung(), db=db, jetzt=jetzt)[0]
        assert b.art == "zu_selten"

    def test_immer_leer_wird_erkannt(self, db):
        """Der Bar-Cache: er lief, traf aber nie."""
        from alpaca_bot import nutzung

        jetzt = dt.datetime(2026, 8, 22, 12, tzinfo=dt.UTC)
        with nutzung._conn(db) as c:
            for i in range(6):
                c.execute("INSERT INTO laeufe (baustein, ts, ergebnis, signatur)"
                          " VALUES ('test.baustein',?,0,?)",
                          ((jetzt - dt.timedelta(hours=i)).isoformat(), f"s{i}"))
        b = nutzung.pruefen(_erwartung(), db=db, jetzt=jetzt)[0]
        assert b.art == "immer_leer"

    def test_immer_gleich_wird_erkannt(self, db):
        """Der Kernfall aus §G14: 19.788 Verifizierungen je Stunde, Runde
        um Runde identisch. Es lief, es kostete Rechenzeit, und es entstand
        keine neue Information. Ohne diesen Test saehe so ein Baustein
        gesund aus - er meldet sich ja regelmaessig mit Ergebnissen."""
        from alpaca_bot import nutzung

        jetzt = dt.datetime(2026, 8, 22, 12, tzinfo=dt.UTC)
        with nutzung._conn(db) as c:
            for i in range(8):
                c.execute("INSERT INTO laeufe (baustein, ts, ergebnis, signatur)"
                          " VALUES ('test.baustein',?,19788,'19788@2026-08-21')",
                          ((jetzt - dt.timedelta(hours=i)).isoformat(),))
        b = nutzung.pruefen(_erwartung(), db=db, jetzt=jetzt)[0]
        assert b.art == "immer_gleich"
        assert "keine neue Information" in b.detail

    def test_gesunder_baustein_meldet_ok(self, db):
        from alpaca_bot import nutzung

        jetzt = dt.datetime(2026, 8, 22, 12, tzinfo=dt.UTC)
        with nutzung._conn(db) as c:
            for i in range(6):
                c.execute("INSERT INTO laeufe (baustein, ts, ergebnis, signatur)"
                          " VALUES ('test.baustein',?,?,?)",
                          ((jetzt - dt.timedelta(hours=i)).isoformat(),
                           10 + i, f"sig{i}"))
        b = nutzung.pruefen(_erwartung(), db=db, jetzt=jetzt)[0]
        assert b.ok


class TestAusnahmenSindBegruendet:

    def test_darf_leer_sein_unterdrueckt_die_meldung(self, db):
        """Der Lernschritt hat ohne neuen Handelstag legitim nichts zu tun."""
        from alpaca_bot import nutzung

        jetzt = dt.datetime(2026, 8, 22, 12, tzinfo=dt.UTC)
        with nutzung._conn(db) as c:
            for i in range(6):
                c.execute("INSERT INTO laeufe (baustein, ts, ergebnis, signatur)"
                          " VALUES ('test.baustein',?,0,?)",
                          ((jetzt - dt.timedelta(hours=i)).isoformat(), f"s{i}"))
        b = nutzung.pruefen(_erwartung(darf_leer_sein=True), db=db, jetzt=jetzt)[0]
        assert b.ok

    def test_darf_gleich_bleiben_unterdrueckt_die_meldung(self, db):
        from alpaca_bot import nutzung

        jetzt = dt.datetime(2026, 8, 22, 12, tzinfo=dt.UTC)
        with nutzung._conn(db) as c:
            for i in range(8):
                c.execute("INSERT INTO laeufe (baustein, ts, ergebnis, signatur)"
                          " VALUES ('test.baustein',?,3,'immer')",
                          ((jetzt - dt.timedelta(hours=i)).isoformat(),))
        b = nutzung.pruefen(_erwartung(darf_gleich_bleiben=True), db=db,
                            jetzt=jetzt)[0]
        assert b.ok


class TestProtokollStoertDenBetriebNie:

    def test_melden_wirft_nie(self, tmp_path):
        """Ein Nutzungsprotokoll, das den Handel stoppen kann, waere
        schlimmer als keins."""
        from alpaca_bot import nutzung

        nutzung.melden("x", 1, db=tmp_path / "nicht" / "da" / "n.sqlite")
        nutzung.melden("x", 1, db=tmp_path)          # Verzeichnis statt Datei
        # kein Absturz - das ist die ganze Zusicherung

    def test_live_meldet_seinen_zyklus(self):
        """Ohne diese Meldung faellt ein stehender Handelsbot nicht auf."""
        import inspect

        from alpaca_bot import live

        quelle = inspect.getsource(live.run_once)
        assert 'nutzung.melden(' in quelle
        assert '"live.zyklus"' in quelle

    def test_live_signatur_traegt_den_stichtag(self):
        """Die Meldung allein reicht nicht - es kommt darauf an, WAS sie
        kennzeichnet.

        Der Mutationstest hat am 22.08.2026 eine schwaechere Fassung
        dieses Tests ueberlebt: Sie prueft nur, DASS gemeldet wird. Eine
        leere Signatur macht den Waechter aber blind fuer den
        gefaehrlichsten Fall - einen Bot, der zwar laeuft, aber taeglich
        dieselbe Lage sieht (§G14). Genau davor soll er warnen.
        """
        import inspect

        from alpaca_bot import live

        quelle = inspect.getsource(live.run_once)
        assert "snapshot.as_of" in quelle.split("nutzung.melden(")[1][:220], (
            "die Nutzungssignatur muss den Stichtag tragen")

    def test_alle_erwartungen_haben_einen_zweck(self):
        """Der Zweck steht im Befund - ohne ihn ist ein Ausfall nicht
        einzuordnen, ohne den Code zu lesen."""
        from alpaca_bot.nutzung import ERWARTUNGEN

        for e in ERWARTUNGEN:
            assert len(e.zweck) > 15, f"{e.baustein} ohne verstaendlichen Zweck"
