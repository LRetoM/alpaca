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
        # Ueber MEHRERE Stichtage hinweg dieselbe Zahl - das ist der
        # Zustand, der Rechenzeit kostet, ohne Information zu erzeugen.
        # (Acht Laeufe an EINEM Stichtag waeren davon nicht zu
        # unterscheiden: an einem Wochenende ist genau das der
        # Normalfall, siehe TestWochenendeIstKeinStillstand.)
        tage = ["2026-08-21", "2026-08-20", "2026-08-19", "2026-08-18"]
        with nutzung._conn(db) as c:
            for i in range(8):
                c.execute("INSERT INTO laeufe (baustein, ts, ergebnis, signatur)"
                          " VALUES ('test.baustein',?,19788,?)",
                          ((jetzt - dt.timedelta(hours=i)).isoformat(),
                           f"19788@{tage[i % len(tage)]}"))
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
        assert "_melde_zyklus(" in quelle
        assert '"live.zyklus"' in inspect.getsource(live._melde_zyklus)

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
        assert "snapshot.as_of" in quelle.split("_melde_zyklus(")[-1][:220], (
            "die Nutzungssignatur muss den Stichtag tragen")

    def test_auch_ein_blockierter_zyklus_meldet_sich(self):
        """Sonst leuchtet der Waechter jedes Wochenende gelb.

        `run_once` kehrt bei geschlossener Boerse frueh zurueck. Ein
        blockierter Zyklus IST ein Lauf - der Bot hat geprueft und
        entschieden, nicht zu handeln.
        """
        import inspect

        from alpaca_bot import live

        quelle = inspect.getsource(live.run_once)
        assert quelle.count("_melde_zyklus(") >= 2, (
            "jeder Rueckgabepunkt muss melden, sonst gilt ein geschlossener "
            "Markt als ausgefallener Bot")

    def test_daemon_meldet_auch_ohne_handel(self):
        """Der Daemon kehrt bei geschlossener Boerse zurueck, BEVOR
        `run_once` gerufen wird.

        Gefunden am 22.08.2026 beim Nachpruefen: Die Meldung sass nur in
        `run_once` - und der Waechter meldete den Live-Bot trotz laufendem
        Dienst als "nie gelaufen". Ein Waechter, der einen gesunden Bot
        anschwaerzt, verliert genau das Vertrauen, das er herstellen soll.
        """
        import inspect

        from alpaca_bot import daemon

        quelle = inspect.getsource(daemon)
        assert "_melde_zyklus" in quelle, (
            "der Daemon muss auch den Nicht-Handel melden")

    def test_alle_erwartungen_haben_einen_zweck(self):
        """Der Zweck steht im Befund - ohne ihn ist ein Ausfall nicht
        einzuordnen, ohne den Code zu lesen."""
        from alpaca_bot.nutzung import ERWARTUNGEN

        for e in ERWARTUNGEN:
            assert len(e.zweck) > 15, f"{e.baustein} ohne verstaendlichen Zweck"


class TestFehlerSchlaegtSofortDurch:
    """Die fuenfte Art: der Baustein laeuft und stuerzt jedes Mal ab.

    **Anlass (22.08.2026).** Im Schatten-Log standen drei
    `sqlite3.OperationalError: unable to open database file` - alle drei
    Schritte eines Durchgangs scheiterten. `16_shadow_daemon.py` faengt
    das ab und meldet `nutzung.melden(baustein, -1, signatur="fehler")`.

    Der Waechter erkannte das aber NICHT als Ausfall:

      * `darf_leer_sein=True` (fuer alle Schattenschritte gesetzt)
        ueberspringt die Leer-Pruefung,
      * `ergebnis = -1` ist nicht 0, also greift sie ohnehin nicht,
      * und "immer_gleich" braucht **fuenf** Laeufe.

    Ein Baustein, der bei jedem Aufruf abstuerzt, ist der eindeutigste
    Ausfall ueberhaupt - und wurde als mildeste Kategorie gemeldet, mit
    dem irrefuehrenden Text "es entsteht keine neue Information". Er
    entsteht sehr wohl: die Information, dass es kaputt ist.
    """

    def _mit_laeufen(self, db, ergebnisse, jetzt):
        from alpaca_bot import nutzung

        with nutzung._conn(db) as c:
            for i, e in enumerate(ergebnisse):
                c.execute(
                    "INSERT INTO laeufe (baustein, ts, ergebnis, signatur)"
                    " VALUES ('test.baustein',?,?,?)",
                    ((jetzt - dt.timedelta(hours=i + 1)).isoformat(), e,
                     "fehler" if e < 0 else f"s{i}"))
        return nutzung.pruefen(_erwartung(darf_leer_sein=True), db=db, jetzt=jetzt)[0]

    def test_ein_einziger_fehllauf_wird_gemeldet(self, db):
        """Nicht erst nach fuenf. Ein Absturz ist sofort eine Aussage."""
        jetzt = dt.datetime(2026, 8, 22, 12, tzinfo=dt.UTC)
        b = self._mit_laeufen(db, [-1], jetzt)
        assert b.art == "fehlerhaft", f"erwartet 'fehlerhaft', war '{b.art}'"
        assert not b.ok

    def test_meldung_nennt_den_fehler_nicht_fehlende_information(self, db):
        jetzt = dt.datetime(2026, 8, 22, 12, tzinfo=dt.UTC)
        b = self._mit_laeufen(db, [-1, -1, -1], jetzt)
        assert "fehlgeschlagen" in b.detail.lower() or "fehler" in b.detail.lower()
        assert "keine neue Information" not in b.detail

    def test_erfolgreicher_lauf_danach_loescht_den_befund(self, db):
        """Ein alter Fehler, auf den Erfolge folgten, ist erledigt.

        Sonst bliebe der Waechter nach einem einmaligen Netzausfall
        dauerhaft rot - und eine Warnung, die immer leuchtet, wird
        weggeklickt (`docs/LERNTEMPO.md` §5).
        """
        jetzt = dt.datetime(2026, 8, 22, 12, tzinfo=dt.UTC)
        # Index 0 ist der juengste Lauf (ts = jetzt - 1h).
        b = self._mit_laeufen(db, [7, 5, -1], jetzt)
        assert b.ok, f"nach erfolgreichen Laeufen erledigt, war '{b.art}'"

    def test_gesunder_baustein_bleibt_ok(self, db):
        jetzt = dt.datetime(2026, 8, 22, 12, tzinfo=dt.UTC)
        b = self._mit_laeufen(db, [3, 4, 5], jetzt)
        assert b.ok and b.art == "ok"


class TestWochenendeIstKeinStillstand:
    """"Immer gleich" nur bei NEUEN Daten (§G18).

    **Anlass (22.08.2026, ein Samstag).** Nach dem Dienstneustart meldete
    der Health-Check GELB:

        Baustein 'schatten.einbuchen': 6 Laeufe, aber immer dasselbe
        Ergebnis (0@2026-08-21) - es entsteht keine neue Information

    Der letzte Handelstag war Freitag. Die vier Schattenschritte sind
    seit §G14 **per Konstruktion idempotent** - ohne neuen Handelstag
    MUESSEN sie dasselbe liefern; genau dafuer wurden sie umgebaut. Der
    Waechter haette damit an jedem Wochenende und Feiertag gelb
    geleuchtet, also an rund zwei von sieben Tagen.

    Eine Warnung, die immer leuchtet, wird weggeklickt
    (`docs/LERNTEMPO.md` §5) - dann faellt auch der echte Stillstand
    nicht mehr auf.

    Unterschieden wird ueber den Datenstand in der Signatur
    (`"<ergebnis>@<stichtag>"`): Bleibt der Stichtag stehen, ist Ruhe
    normal. Wandert er, waehrend das Ergebnis steht, ist es der teure
    §G14-Zustand.
    """

    def _laeufe(self, db, signaturen, jetzt):
        from alpaca_bot import nutzung

        with nutzung._conn(db) as c:
            for i, sig in enumerate(signaturen):
                c.execute(
                    "INSERT INTO laeufe (baustein, ts, ergebnis, signatur)"
                    " VALUES ('test.baustein',?,0,?)",
                    ((jetzt - dt.timedelta(hours=i + 1)).isoformat(), sig))
        return nutzung.pruefen(_erwartung(darf_leer_sein=True), db=db,
                               jetzt=jetzt)[0]

    def test_gleicher_stichtag_ist_kein_befund(self):
        """Wochenende: sechs Laeufe, ein Handelstag."""
        import tempfile, pathlib

        jetzt = dt.datetime(2026, 8, 22, 12, tzinfo=dt.UTC)
        with tempfile.TemporaryDirectory() as d:
            db = pathlib.Path(d) / "n.sqlite"
            b = self._laeufe(db, ["0@2026-08-21"] * 6, jetzt)
        assert b.ok, (
            f"ohne neuen Handelstag ist Ruhe der Normalfall, war '{b.art}'")

    def test_wandernder_stichtag_bei_gleichem_ergebnis_faellt_auf(self):
        """Der §G14-Zustand: es wird gerechnet, aber nichts entsteht."""
        import tempfile, pathlib

        jetzt = dt.datetime(2026, 8, 22, 12, tzinfo=dt.UTC)
        with tempfile.TemporaryDirectory() as d:
            db = pathlib.Path(d) / "n.sqlite"
            # Gleiche Signatur, aber ueber mehrere Stichtage hinweg waere
            # sie verschieden - hier steht sie, obwohl die Tage wandern.
            b = self._laeufe(db, [f"19788@2026-08-{t}" for t in
                                  (21, 20, 19, 18, 17, 14)], jetzt)
        assert not b.ok and b.art == "immer_gleich", b.art

    def test_signatur_ohne_datenstand_verhaelt_sich_wie_bisher(self):
        """Rueckwaertskompatibel: kein '@' -> alte Regel."""
        import tempfile, pathlib

        jetzt = dt.datetime(2026, 8, 22, 12, tzinfo=dt.UTC)
        with tempfile.TemporaryDirectory() as d:
            db = pathlib.Path(d) / "n.sqlite"
            b = self._laeufe(db, ["immer_dasselbe"] * 6, jetzt)
        assert b.art == "immer_gleich"
