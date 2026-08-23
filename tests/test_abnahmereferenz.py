"""Die Abnahme misst gegen die REGISTRIERTE Referenz (§G19 Fund 1).

**Der Fund vom 23.08.2026.** Dieselbe Frage - "wogegen wird
`B11_dyn_ausstieg_live` am 10.10.2026 abgenommen?" - hatte vier
Antworten an vier Orten:

    BETRIEBSPLAN §3.3 (Vertragstext)   ->  B00_basis
    Flottenregistrierung in shadow.db  ->  B09_nachkauf
    `21_fleet.py --basis` (Standard)   ->  B00_basis
    `fokus.offene_fragen`              ->  B09_nachkauf

Und es war keine Formalie. Gemessen am 23.08.2026 an den echten
Schattendaten:

    --kriterien B11_dyn_ausstieg_live                       t = 0.99
    --kriterien B11_dyn_ausstieg_live --basis B09_nachkauf  t = 1.24

Beide Zahlen heissen "Kriterium 1 aus §3.3" und entscheiden ueber
denselben Vertrag.

**Warum B00_basis die falsche Antwort ist.** BEFUNDE §G6 hat sie am
16.08.2026 widerlegt: Der Live-Bot laeuft seit dem 30.07.2026 mit
`deploy_to_target=True` und `allow_topup=True`, `B00_basis` steht
unveraendert auf `False`/`False`. `B11_dyn_ausstieg_live` wurde
daraufhin eigens gegen `B09_nachkauf` angemeldet - daher sein Namenszusatz
"gegen echte Live-Basis". Das Abnahmekommando nahm trotzdem weiter B00,
weil der Standardwert hartkodiert war.

**Die Lehre, die diese Tests festhalten:** Eine Registrierung ist
unveraenderlich und traegt das Datum ihrer Festlegung. Ein Satz in einem
Dokument ist beides nicht. Wo beide etwas ueber dieselbe Messung sagen,
gewinnt die Registrierung - dasselbe Prinzip, mit dem BETRIEBSPLAN §3.2
verbietet, `schwelle_sigma()` als Zahl abzuschreiben.
"""

from __future__ import annotations

import pytest

from alpaca_bot import fleet, shadow_eval
from alpaca_bot.shadow import ShadowStore


@pytest.fixture
def flotte(tmp_path):
    """Basis-Bot, ein Live-Spiegel und ein Kandidat, der gegen ihn laeuft."""
    s = ShadowStore(tmp_path / "shadow.sqlite")
    fleet.anmelden(
        "B00_basis", name="Basis", familie="basis",
        hypothese="Der unveraenderte Ausgangsstand, gegen den gemessen wird.",
        basis_bot=None, store=s,
    )
    fleet.anmelden(
        "B09_nachkauf", name="Nachkauf", familie="kapital", achse="allow_topup",
        wert="True", aenderung={"allow_topup": True, "deploy_to_target": True},
        hypothese="Freies Kapital in laufende Gewinner statt es liegen zu lassen.",
        basis_bot="B00_basis", store=s,
    )
    fleet.anmelden(
        "B11_dyn_ausstieg_live", name="Dynamischer Ausstieg (gegen Live-Basis)",
        familie="ausstieg", achse="zeitausstieg_dynamisch", wert="True",
        aenderung={"zeitausstieg_dynamisch": True, "allow_topup": True,
                   "deploy_to_target": True},
        hypothese="Gewinner laufen lassen, statt sie nach fester Frist zu verkaufen.",
        basis_bot="B09_nachkauf", store=s,
    )
    return s


class TestReferenzBot:
    """`referenz_bot` liest die Anmeldung, nicht eine Vorgabe."""

    def test_nimmt_die_registrierte_basis(self, flotte):
        assert shadow_eval.referenz_bot("B11_dyn_ausstieg_live", flotte) == "B09_nachkauf"

    def test_nicht_pauschal_b00(self, flotte):
        """Der eigentliche Fund: der alte Standard haette B00 geliefert."""
        assert shadow_eval.referenz_bot("B11_dyn_ausstieg_live", flotte) != "B00_basis"

    def test_basis_bot_ohne_eigene_referenz(self, flotte):
        """`B00_basis` ist selbst der Nullpunkt - Rueckfall, kein Fehler."""
        assert shadow_eval.referenz_bot("B00_basis", flotte) == "B00_basis"

    def test_unbekannter_bot_faellt_zurueck(self, flotte):
        assert shadow_eval.referenz_bot("B99_gibt_es_nicht", flotte) == "B00_basis"


class TestAbnahmeNimmtDieRegistrierung:
    """Der Entscheidungsvertrag §3.3 rechnet gegen die Anmeldung."""

    def test_kriterien_ohne_angabe_nutzen_die_registrierung(self, flotte):
        k = shadow_eval.kriterien_pruefen("B11_dyn_ausstieg_live", store=flotte)
        assert k["basis"] == "B09_nachkauf", (
            "Ohne ausdrueckliche Angabe muss die registrierte Basis gelten. "
            "Ein hartkodiertes B00_basis stellt den Vertrag auf eine von "
            "BEFUNDE §G6 widerlegte Referenz."
        )

    def test_ausdrueckliche_angabe_gewinnt(self, flotte):
        """Die Gegenprobe von Hand muss moeglich bleiben."""
        k = shadow_eval.kriterien_pruefen(
            "B11_dyn_ausstieg_live", "B00_basis", store=flotte)
        assert k["basis"] == "B00_basis"

    def test_text_weist_die_herkunft_der_referenz_aus(self, flotte):
        """Wer die Zahl zitiert, muss sehen, woher die Referenz kommt."""
        t = shadow_eval.kriterien_text("B11_dyn_ausstieg_live", store=flotte)
        assert "B09_nachkauf" in t
        assert "registrierte Basis" in t

    def test_text_warnt_bei_abweichender_handeingabe(self, flotte):
        """Eine von Hand gesetzte Referenz darf nicht wie die echte aussehen."""
        t = shadow_eval.kriterien_text(
            "B11_dyn_ausstieg_live", "B00_basis", store=flotte)
        assert "VON HAND GESETZT" in t
        assert "B09_nachkauf" in t, (
            "Die Warnung muss die registrierte Basis nennen, sonst weiss "
            "der Leser nicht, wovon abgewichen wurde."
        )


class TestKeinHartkodierterStandard:
    """Der Standard darf nicht wieder in den Code zurueckwandern."""

    def test_kriterien_pruefen_hat_keinen_bot_als_vorgabe(self):
        import inspect

        sig = inspect.signature(shadow_eval.kriterien_pruefen)
        assert sig.parameters["basis_bot"].default is None, (
            "basis_bot muss None sein. Ein Bot-Name als Standard ist genau "
            "der Fehler aus §G19 Fund 1: Er ueberstimmt die Registrierung "
            "still und ohne Hinweis in der Ausgabe."
        )

    def test_kriterien_text_hat_keinen_bot_als_vorgabe(self):
        import inspect

        sig = inspect.signature(shadow_eval.kriterien_text)
        assert sig.parameters["basis_bot"].default is None

    def test_abnahmekommando_hat_keinen_bot_als_vorgabe(self):
        """`21_fleet.py --basis` war die Stelle, an der es live schieflief."""
        from pathlib import Path

        from alpaca_bot.config import PROJECT_ROOT

        quelle = (Path(PROJECT_ROOT) / "scripts" / "21_fleet.py").read_text()
        assert '"--basis", default=None' in quelle, (
            "Das Abnahmekommando muss die registrierte Basis nehmen. Bis "
            "zum 23.08.2026 stand hier default='B00_basis' - und damit "
            "entschied ein Argumentstandard, was der Entscheidungsvertrag "
            "regeln sollte."
        )
