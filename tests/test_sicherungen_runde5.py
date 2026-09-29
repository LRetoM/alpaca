"""Drei Sicherungen, die nicht sicherten, was sie versprachen (§G19).

**Fund 6 - der Regelabgleich sah die Mehrheit der Entscheidungen nicht.**
`audit.check_decisions` filterte auf `action == "buy"`. Nachkaeufe sind
110 von 304 Live-Entscheidungen (36 %) und die Mehrheit der
Kapitalzuteilung. `Engine._find_topups` erzwingt fuer sie zwei Regeln
(`min_score` und `topup_min_gain_pct`, die Average-Down-Sperre) -
geprueft wurde keine. Nachgemessen an allen 110: null Verstoesse. Es war
eine Abdeckungsluecke, kein Regelbruch. Genau deshalb gehoert sie
geschlossen: Dieses Modul existiert fuer den Fall, dass eine Regel
aufhoert zu greifen.

**Fund 7 - eine Sicherung, die es nie gab.** `shadow.RAW_DIR` wurde bei
jedem `ShadowStore()` angelegt und nie beschrieben; seit dem 31.07.2026
leer. Es sah aus wie das Gegenstueck zu `journal_raw`. Dahinter liegen
26 MB mit 20.690 Vorhersagen und der gesamten Flottenmessung - der
Datengrundlage der Entscheidung vom 10.10.2026, voellig ungesichert.

**Struktur - eine Zusicherung ohne Pruefung.** "Der Schattenbetrieb
importiert trading.py bewusst NICHT - er *kann* keine Order senden"
steht in `CLAUDE.md`, `README.md` und `BETRIEBSPLAN` §6. Sie stimmte,
war aber an keiner Stelle geprueft - dieselbe Lage wie beim
RL-Docstring in §G17.
"""

from __future__ import annotations

import sqlite3

import pytest

from alpaca_bot import audit, selfcheck
from alpaca_bot.journal import Journal
from alpaca_bot.shadow import ShadowStore


# ---------------------------------------------------------------------------
# Fund 6: Nachkaeufe im Regelabgleich
# ---------------------------------------------------------------------------
REGELN = {"min_score": 0.35, "topup_min_gain_pct": 0.0,
          "max_position_pct": 0.10}


@pytest.fixture
def buch(tmp_path):
    return Journal(tmp_path / "journal.sqlite")


def _lauf_mit_nachkauf(buch, *, score, gewinn):
    with buch.run("live_trade", config=REGELN) as run:
        run.decision(symbol="X", action="topup", conviction=score,
                     reasons={"nachkauf": True, "gewinn_pct": gewinn})


class TestNachkaeufeWerdenGeprueft:

    def test_nachkauf_unter_score_ist_ein_verstoss(self, buch):
        _lauf_mit_nachkauf(buch, score=0.20, gewinn=0.05)
        r = audit.AuditReport()
        audit.check_decisions(buch, r)
        assert any(f.rule == "Score-Schwelle" for f in r.violations)

    def test_nachkauf_in_den_verlust_ist_ein_verstoss(self, buch):
        """Average-Down: aus begrenztem Verlust wird ein groesserer."""
        _lauf_mit_nachkauf(buch, score=0.90, gewinn=-0.04)
        r = audit.AuditReport()
        audit.check_decisions(buch, r)
        treffer = [f for f in r.violations
                   if f.rule == "Nachkauf in eine Verlustposition"]
        assert treffer, (
            "Die Average-Down-Sperre war bis zum 23.08.2026 ungeprueft, "
            "obwohl 110 von 304 Live-Entscheidungen Nachkaeufe waren."
        )

    def test_regelkonformer_nachkauf_bleibt_still(self, buch):
        _lauf_mit_nachkauf(buch, score=0.90, gewinn=0.02)
        r = audit.AuditReport()
        audit.check_decisions(buch, r)
        assert not r.violations

    def test_nachkauf_ohne_gewinnangabe_faellt_auf(self, buch):
        """Ein fehlendes Feld darf nicht zum stillen Ueberspringen fuehren."""
        with buch.run("live_trade", config=REGELN) as run:
            run.decision(symbol="X", action="topup", conviction=0.9,
                         reasons={"nachkauf": True})
        r = audit.AuditReport()
        audit.check_decisions(buch, r)
        assert any(f.rule == "Nachkauf ohne Gewinnangabe" for f in r.findings)

    def test_nachkaeufe_werden_getrennt_gezaehlt(self, buch):
        """Sichtbar machen, wenn eine Aktionsart gar nicht vorkommt (§G16)."""
        with buch.run("live_trade", config=REGELN) as run:
            run.decision(symbol="A", action="buy", conviction=0.9,
                         reasons={"x": True})
            run.decision(symbol="B", action="topup", conviction=0.9,
                         reasons={"gewinn_pct": 0.01})
        r = audit.AuditReport()
        audit.check_decisions(buch, r)
        assert r.stats["Kaufentscheidungen geprueft"] == 1
        assert r.stats["Nachkaeufe geprueft"] == 1

    def test_kaeufe_werden_weiterhin_geprueft(self, buch):
        """Die Erweiterung darf die bestehende Pruefung nicht verdraengen."""
        with buch.run("live_trade", config=REGELN) as run:
            run.decision(symbol="A", action="buy", conviction=0.10,
                         reasons={"x": True})
        r = audit.AuditReport()
        audit.check_decisions(buch, r)
        assert any(f.rule == "Score-Schwelle" for f in r.violations)

    def test_verkaeufe_bleiben_aussen_vor(self, buch):
        """`sell` teilt keine Score-Schwelle - ein Ausstieg ist keine Zuteilung."""
        with buch.run("live_trade", config=REGELN) as run:
            run.decision(symbol="A", action="sell", conviction=0.01,
                         reasons={"x": True})
        r = audit.AuditReport()
        audit.check_decisions(buch, r)
        assert not r.violations


# ---------------------------------------------------------------------------
# Fund 7: Die Schattensicherung
# ---------------------------------------------------------------------------
class TestSchattenSicherung:

    def test_sicherung_ist_lesbar_und_vollstaendig(self, tmp_path):
        s = ShadowStore(tmp_path / "shadow.sqlite")
        s.depot_init("B00_basis", 100_000.0)
        ziel = s.sichern()
        assert ziel is not None and ziel.exists()
        with sqlite3.connect(f"file:{ziel}?mode=ro", uri=True) as c:
            assert c.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            assert c.execute("SELECT COUNT(*) FROM shadow_cash").fetchone()[0] == 1

    def test_liegt_neben_der_eigenen_datenbank(self, tmp_path):
        """Kein Modul-Global - derselbe Fehler wie bei journal_raw (Fund 1)."""
        s = ShadowStore(tmp_path / "shadow.sqlite")
        assert s.sicherung_dir == tmp_path / "shadow_sicherung"
        s.sichern()
        assert list(s.sicherung_dir.glob("shadow_*.sqlite"))

    def test_alte_staende_werden_begrenzt(self, tmp_path):
        s = ShadowStore(tmp_path / "shadow.sqlite")
        for i in range(5):
            ziel = s.sichern(behalten=3)
            assert ziel is not None
            # Zeitstempel hat Sekundenaufloesung - eindeutige Namen erzwingen
            ziel.rename(ziel.with_name(f"shadow_2026082{i}_120000.sqlite"))
        s.sichern(behalten=3)
        assert len(list(s.sicherung_dir.glob("shadow_*.sqlite"))) == 3

    def test_ausfall_stoppt_den_schattenbetrieb_nicht(self, tmp_path, monkeypatch):
        """Wie bei `journal._write_raw`: melden, nicht werfen (§G18 Fund 2)."""
        s = ShadowStore(tmp_path / "shadow.sqlite")
        monkeypatch.setattr(
            type(s.sicherung_dir), "mkdir",
            lambda *a, **k: (_ for _ in ()).throw(OSError("Datentraeger voll")))
        assert s.sichern() is None

    def test_kein_leeres_rohverzeichnis_mehr(self):
        """`shadow_raw` wurde angelegt und nie beschrieben - das ist weg."""
        import alpaca_bot.shadow as sh

        assert not hasattr(sh, "RAW_DIR"), (
            "Ein Verzeichnis, das wie eine Sicherung aussieht und nie "
            "beschrieben wird, ist schlimmer als keines - man verlaesst "
            "sich darauf."
        )


# ---------------------------------------------------------------------------
# Struktur: Der Schatten kann nicht handeln
# ---------------------------------------------------------------------------
class TestSchattenHandeltNicht:

    def test_kein_schattenmodul_importiert_trading(self):
        r = selfcheck.CheckReport()
        selfcheck.check_schatten_handelt_nicht(r)
        assert not r.violations, [str(f) for f in r.violations]

    def test_die_echte_modulliste_deckt_alle_schattenmodule_ab(self):
        """Der Mutationstest hat genau diese Luecke gefunden (23.08.2026).

        Alle Verstoss-Tests unten setzen `SCHATTEN_MODULE` per monkeypatch
        auf eine Attrappe - sie pruefen damit den Mechanismus, aber NIE
        die Voreinstellung. Eine Mutation, die die echte Liste auf `()`
        setzt, blieb deshalb ungefangen: Die Regel haette gruen gemeldet,
        ohne eine einzige Datei anzusehen.

        Dieselbe Lehre wie in §G17: *"Ein Test, der nur seine eigenen
        Argumente prueft, prueft die Voreinstellung nicht."* Zum zweiten
        Mal in diesem Projekt vom Mutationstest entlarvt.
        """
        bewacht = set(selfcheck.schatten_module())
        assert bewacht, (
            "Eine leere Modulliste laesst die Regel gruen melden, ohne "
            "etwas zu pruefen - die Fehlerklasse aus §G15."
        )
        # JEDES shadow*.py muss dabei sein. Genau hier lief es am
        # 23.08.2026 schief: Die Aufteilung schob den Code nach
        # `shadow_schritte.py`, die aufgezaehlte Liste kannte nur
        # `shadow.py`, und die Regel bewachte ab da die Fassade.
        vorhanden = {p.name for p in selfcheck.SRC.glob("shadow*.py")}
        assert vorhanden <= bewacht, (
            f"Nicht bewacht: {sorted(vorhanden - bewacht)}. Ein neues "
            f"Schattenmodul darf der Regel nicht entkommen."
        )
        for name in bewacht:
            assert (selfcheck.SRC / name).exists(), (
                f"{name} steht in der Liste, existiert aber nicht - die "
                f"Regel prueft dann eine Datei weniger, ohne es zu melden."
            )

    def test_regel_steht_in_der_verfassung(self):
        assert any("Schattenbetrieb" in regel
                   for regel in selfcheck.CHARTER["regeln"])

    def test_regel_wird_bei_verstoss_wirklich_laut(self, tmp_path, monkeypatch):
        """Ein Test, der nur seinen eigenen Gutfall prueft, prueft nichts (§G17)."""
        gefaelscht = tmp_path / "shadow.py"
        gefaelscht.write_text("from . import trading\n")
        monkeypatch.setattr(selfcheck, "SRC", tmp_path)
        r = selfcheck.CheckReport()
        selfcheck.check_schatten_handelt_nicht(r)
        assert r.violations

    def test_erkennt_auch_import_alpaca_bot_trading(self, tmp_path, monkeypatch):
        gefaelscht = tmp_path / "shadow.py"
        gefaelscht.write_text("import alpaca_bot.trading\n")
        monkeypatch.setattr(selfcheck, "SRC", tmp_path)
        r = selfcheck.CheckReport()
        selfcheck.check_schatten_handelt_nicht(r)
        assert r.violations

    def test_erkennt_auch_from_trading_import(self, tmp_path, monkeypatch):
        gefaelscht = tmp_path / "shadow.py"
        gefaelscht.write_text("from .trading import market_order\n")
        monkeypatch.setattr(selfcheck, "SRC", tmp_path)
        r = selfcheck.CheckReport()
        selfcheck.check_schatten_handelt_nicht(r)
        assert r.violations

    def test_lokaler_import_in_einer_funktion_wird_gefunden(self, tmp_path,
                                                            monkeypatch):
        """Der wahrscheinlichste Weg, wie es passieren wuerde."""
        gefaelscht = tmp_path / "shadow.py"
        gefaelscht.write_text(
            "def schritt():\n"
            "    from . import trading\n"
            "    return trading\n")
        monkeypatch.setattr(selfcheck, "SRC", tmp_path)
        r = selfcheck.CheckReport()
        selfcheck.check_schatten_handelt_nicht(r)
        assert r.violations
