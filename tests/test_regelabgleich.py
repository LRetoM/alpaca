"""Der Regelabgleich - ein Abbruchkriterium, das nur manuell lief.

**Anlass (22.08.2026).** `docs/BETRIEBSPLAN.md` §8 fuehrt auf:

    | Regelabgleich meldet Abweichung | Sofort aus - ein Regelbruch ist
    | ein Logikfehler, kein Pech |

`audit.run_audit()` wurde aber von genau einer Stelle gerufen:
`scripts/13_tagesbericht.py`, das laut §5.2 "alle 1-2 Wochen" von Hand
gestartet wird. Ein Abbruchkriterium, das nur greift, wenn jemand
zufaellig ein Skript aufruft, ist praktisch keines - dieselbe
Fehlerklasse wie §G15 ("gebaut, laeuft nie"), nur eine Stufe subtiler:
Es LIEF, aber nicht dort, wo es wirken muss.

**Der zweite Fund kam beim Einbauen.** Der Abgleich meldete einen
`VERSTOSS`, weil 1 von 91 Laeufen mit einem HTTP-500 von Alpaca endete.
Das ist kein Regelbruch, sondern der Normalfall eines Netzdienstes -
`docs/BEFUNDE.md` §H fuehrt genau diesen Vorfall als bestandene
Betriebspruefung. Haette man das unveraendert in den Health-Check
gehaengt, stuende die Ampel ab sofort dauerhaft auf ROT. Und eine
Warnung, die immer leuchtet, wird weggeklickt (`docs/LERNTEMPO.md` §5) -
dann faellt auch der echte Regelbruch nicht mehr auf.
"""

from __future__ import annotations

import pandas as pd
import pytest

from alpaca_bot import audit


class TestFehlerquoteStattFehlerzahl:
    """Ein einzelner Netzfehler ist kein Regelbruch."""

    def _report_mit(self, n_gesamt: int, n_fehler: int) -> audit.AuditReport:
        """Baut einen Report ueber ein kuenstliches Lauf-Journal."""
        jetzt = pd.Timestamp.now(tz="UTC")
        runs = pd.DataFrame({
            "run_id": [f"r{i}" for i in range(n_gesamt)],
            "script": "live_trade",
            "started_at": [(jetzt - pd.Timedelta(minutes=15 * i)).isoformat()
                           for i in range(n_gesamt)],
            "status": ["failed"] * n_fehler + ["ok"] * (n_gesamt - n_fehler),
        })

        class FakeJournal:
            def table(self, name, where="", params=()):
                return runs if name == "runs" else pd.DataFrame()

        report = audit.AuditReport()
        audit.check_gaps(FakeJournal(), report, days=7)
        return report

    def test_einzelner_fehler_ist_auffaellig_kein_verstoss(self):
        """Der konkrete Fall: 1 von 91 Laeufen, HTTP 500 (§H)."""
        r = self._report_mit(91, 1)
        assert r.clean, "ein transienter Netzfehler ist kein Regelbruch"
        assert any("Fehlgeschlagene" in f.rule for f in r.findings), (
            "sichtbar bleiben muss er trotzdem")

    def test_haeufung_ist_ein_verstoss(self):
        """Ab einer Quote ist es keine Panne mehr, sondern ein Zustand."""
        r = self._report_mit(20, 12)
        assert not r.clean
        assert any(f.severity == "verstoss" for f in r.findings)

    def test_keine_fehler_keine_meldung(self):
        r = self._report_mit(50, 0)
        assert r.clean
        assert not any("Fehlgeschlagene" in f.rule for f in r.findings)

    def test_meldung_nennt_die_quote(self):
        """Ohne Bezugsgroesse ist '3 Fehler' nicht einzuordnen."""
        r = self._report_mit(100, 3)
        text = " ".join(f.detail for f in r.findings)
        assert "100" in text and "3" in text


class TestHealthCheckPrueftDieRegeln:
    """Das Abbruchkriterium muss dort haengen, wo hingesehen wird."""

    def test_health_check_ruft_den_regelabgleich(self):
        quelle = __import__("pathlib").Path("scripts/18_health_check.py").read_text()
        assert "audit" in quelle and "run_audit" in quelle, (
            "BETRIEBSPLAN §8 macht den Regelabgleich zum Abbruchkriterium - "
            "er muss im Health-Check laufen, nicht nur im Wochenbericht")

    def test_verstoss_faerbt_die_ampel_rot(self):
        """§8: 'Sofort aus - ein Regelbruch ist ein Logikfehler, kein Pech.'"""
        quelle = __import__("pathlib").Path("scripts/18_health_check.py").read_text()
        block = quelle[quelle.index("run_audit"):]
        assert 'ampel = "ROT"' in block[:1200]

    def test_ausfall_des_abgleichs_blockiert_die_ampel_nicht(self):
        """Ein Kontoabruf-Fehler darf den Health-Check nicht zerreissen."""
        quelle = __import__("pathlib").Path("scripts/18_health_check.py").read_text()
        block = quelle[quelle.index("run_audit"):]
        assert "except" in block[:1600]
