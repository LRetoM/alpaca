"""Live gegen Schatten - die Invarianten, die keiner vergessen darf.

**Warum dieser Block der wichtigste ist:** Hier lagen die teuersten
Fehler des Projekts, und beide waren derselbe Typ - eine Zusicherung, die
bei ihrer Formulierung stimmte und spaeter still verfiel:

  * `B00_basis` trug "Entspricht exakt der Einstellung des Live-Bots".
    Richtig am 29.07., falsch ab dem 30.07. Zwei Wochen unbemerkt.
  * `shadow.code_version()` fand git in `DATA_DIR.parent`. Richtig bis
    zum Umzug der Datenbanken, danach zwei Monate lang 'unbekannt'.

Beide Male war die AUSSAGE korrekt dokumentiert - nur die Wirklichkeit
lief darunter weg. Tests, die solche Aussagen als INVARIANTE pruefen
(nicht als Momentaufnahme), sind die einzige Verteidigung.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from alpaca_bot.config import PROJECT_ROOT
from alpaca_bot.engine import EngineConfig


def live_konfiguration() -> EngineConfig:
    """Die Konfiguration, die `scripts/12_daemon.py` TATSAECHLICH startet.

    Bewusst aus den Skript-Voreinstellungen abgeleitet und nicht
    hartkodiert: Aendert jemand die Defaults im Skript, muss dieser Test
    mitwandern - genau das ist der Zweck.
    """
    quelle = (PROJECT_ROOT / "scripts" / "12_daemon.py").read_text(encoding="utf-8")
    baum = ast.parse(quelle)

    # `--kein-voll-investiert` / `--kein-nachkauf` sind Abschalter mit
    # `default=True`. Der Live-Bot laeuft also mit beiden AN, solange die
    # Flags nicht gesetzt sind.
    defaults: dict[str, bool] = {}
    for knoten in ast.walk(baum):
        if not (isinstance(knoten, ast.Call)
                and isinstance(knoten.func, ast.Attribute)
                and knoten.func.attr == "add_argument"):
            continue
        dest = default = None
        for kw in knoten.keywords:
            if kw.arg == "dest" and isinstance(kw.value, ast.Constant):
                dest = kw.value.value
            if kw.arg == "default" and isinstance(kw.value, ast.Constant):
                default = kw.value.value
        if dest in ("voll_investiert", "nachkauf"):
            defaults[dest] = default

    assert set(defaults) == {"voll_investiert", "nachkauf"}, (
        "Die Schalter --kein-voll-investiert / --kein-nachkauf wurden "
        "umbenannt oder entfernt. Dieser Test muss angepasst werden."
    )
    return EngineConfig.for_reversal(
        max_positions=15,
        deploy_to_target=defaults["voll_investiert"],
        allow_topup=defaults["nachkauf"],
    )


class TestFlottenReferenz:
    """REGRESSION (16.08.2026): B00_basis behauptete zwei Wochen lang,
    dem Live-Bot zu entsprechen. Am 30.07. wurden `deploy_to_target` und
    `allow_topup` zum Live-Standard (Commits 3e3d30e, f253724), B00 blieb
    bei False/False. 8 von 10 Flottenbots verglichen sich gegen diese
    falsche Basis."""

    def test_b09_ist_die_echte_live_referenz(self):
        """B09_nachkauf ist die einzige Flottenkonfiguration, die
        deckungsgleich mit dem laufenden Live-Bot ist. Bricht dieser Test,
        hat sich entweder der Live-Standard geaendert oder B09 - in beiden
        Faellen muss die Referenz neu bestimmt werden, BEVOR weiter
        gemessen wird."""
        from alpaca_bot import fleet

        b09 = next((b for b in fleet.STARTAUFSTELLUNG
                    if b["bot_id"] == "B09_nachkauf"), None)
        assert b09 is not None

        cfg = EngineConfig.for_reversal(**b09["aenderung"])
        live = live_konfiguration()
        unterschiede = {k: (live.as_dict()[k], cfg.as_dict().get(k))
                        for k in live.as_dict()
                        if live.as_dict()[k] != cfg.as_dict().get(k)}
        assert not unterschiede, (
            f"B09_nachkauf weicht vom echten Live-Bot ab: {unterschiede}. "
            "Entweder wurden die Defaults in 12_daemon.py geaendert oder "
            "B09 - die Live-Referenz der Flotte muss neu bestimmt werden."
        )

    def test_b00_behauptet_nicht_mehr_live_zu_sein(self):
        """Die falsche Zusicherung darf nicht zurueckkehren."""
        from alpaca_bot import fleet

        b00 = next(b for b in fleet.STARTAUFSTELLUNG
                   if b["bot_id"] == "B00_basis")
        assert "Entspricht exakt der Einstellung des Live-Bots." not in b00["hypothese"]

    def test_b00_weicht_tatsaechlich_ab(self):
        """Gegenprobe: Waere B00 wieder deckungsgleich, muesste der
        Warnhinweis entfernt werden - dieser Test macht das sichtbar."""
        live = live_konfiguration().as_dict()
        b00 = EngineConfig.for_reversal().as_dict()
        assert live != b00, (
            "B00_basis entspricht wieder dem Live-Bot. Der Warnhinweis in "
            "fleet.STARTAUFSTELLUNG ist damit veraltet."
        )


class TestSchattenKannNichtHandeln:
    """Der Schattenbetrieb importiert `trading.py` bewusst NICHT - er
    *kann* keine Order senden, nicht nur 'darf nicht'. Eine Disziplin, die
    nur im Kopf existiert, haelt nicht."""

    def test_shadow_importiert_kein_trading(self):
        quelle = (PROJECT_ROOT / "src" / "alpaca_bot" / "shadow.py").read_text(
            encoding="utf-8")
        baum = ast.parse(quelle)
        importiert = set()
        for k in ast.walk(baum):
            if isinstance(k, ast.ImportFrom) and k.module:
                importiert.add(k.module)
                for n in k.names:
                    importiert.add(f"{k.module}.{n.name}")
            elif isinstance(k, ast.Import):
                for n in k.names:
                    importiert.add(n.name)
        verboten = {m for m in importiert if "trading" in m}
        assert not verboten, f"shadow.py importiert Handelscode: {verboten}"

    def test_shadow_daemon_importiert_kein_trading(self):
        quelle = (PROJECT_ROOT / "scripts" / "16_shadow_daemon.py").read_text(
            encoding="utf-8")
        assert "import trading" not in quelle
        assert "from alpaca_bot import trading" not in quelle


class TestEngineConfigVollstaendig:
    """Jedes Feld muss in `as_dict()` erscheinen - sonst protokolliert der
    Lauf es nicht, und `audit.py` kann die Regel spaeter nicht pruefen.
    Eine Regel, die nicht mitgeschrieben wird, meldet stumm nichts."""

    def test_alle_felder_im_protokoll(self):
        from dataclasses import fields

        cfg = EngineConfig.for_reversal()
        protokolliert = set(cfg.as_dict())
        # Gewichte sind eigene Objekte und werden separat erfasst.
        ausnahmen = {"weights", "reversal_weights", "position_size_margin"}
        fehlend = {f.name for f in fields(cfg)} - protokolliert - ausnahmen
        assert not fehlend, (
            f"Diese EngineConfig-Felder fehlen in as_dict(): {fehlend}. "
            "Sie werden dadurch nicht protokolliert und vom Regelabgleich "
            "nicht geprueft."
        )


class TestKostenannahmen:
    """Schatten und Simulation muessen dieselben Kosten ansetzen - sonst
    sind ihre Ergebnisse nicht vergleichbar."""

    def test_schatten_und_simulation_gleich(self):
        from alpaca_bot.shadow import ShadowConfig
        from alpaca_bot.simulate import SimConfig

        s, sim = ShadowConfig(), SimConfig()
        assert s.spread_bps == sim.spread_bps
        assert s.slippage_bps == sim.slippage_bps


class TestIntradayStopKonsistenz:
    """REGRESSION: Der Schatten rechnete seit jeher mit Intraday-Stops
    (`bar["low"] <= stop`), der Live-Bot pruefte nur den Vortagesschluss.
    Die Messung ueberschaetzte den Verlustschutz damit systematisch - in
    genau den Faellen, die am teuersten sind."""

    def test_live_hat_intraday_stop(self):
        from alpaca_bot import live

        assert hasattr(live, "pruefe_stops_intraday")

    def test_daemon_ruft_ihn_auf(self):
        from alpaca_bot.daemon import Daemon

        quelle = inspect.getsource(Daemon.step)
        assert "_maybe_stops_intraday" in quelle

    def test_stop_laeuft_vor_der_fensterpruefung(self):
        """Die Fensterregeln schuetzen vor teuren EINSTIEGEN. Fuer eine
        Notbremse gilt das Gegenteil - sie muss auch in der
        Eroeffnungsspanne greifen."""
        from alpaca_bot.daemon import Daemon

        quelle = inspect.getsource(Daemon.step)
        assert quelle.index("_maybe_stops_intraday") < quelle.index("trading_window")
