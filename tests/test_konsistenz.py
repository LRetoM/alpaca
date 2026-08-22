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
        """Erfasst ALLE Importformen, auch `from . import trading`.

        Die erste Fassung pruefte `if isinstance(k, ast.ImportFrom) and
        k.module` - bei einem relativen Import ohne Modulnamen
        (`from . import trading`) ist `k.module` aber None, und genau
        dieser Fall wurde stillschweigend uebersprungen. Der Mutationstest
        (Schritt 23) baute exakt diese Zeile ein und der Test blieb gruen.
        """
        quelle = (PROJECT_ROOT / "src" / "alpaca_bot" / "shadow.py").read_text(
            encoding="utf-8")
        baum = ast.parse(quelle)
        importiert: set[str] = set()
        for k in ast.walk(baum):
            if isinstance(k, ast.ImportFrom):
                # k.module ist None bei `from . import x` - die Namen
                # muessen deshalb IMMER mit erfasst werden.
                if k.module:
                    importiert.add(k.module)
                for n in k.names:
                    importiert.add(n.name)
                    if k.module:
                        importiert.add(f"{k.module}.{n.name}")
            elif isinstance(k, ast.Import):
                for n in k.names:
                    importiert.add(n.name)
        verboten = {m for m in importiert if "trading" in m}
        assert not verboten, f"shadow.py importiert Handelscode: {verboten}"

    def test_pruefung_erkennt_relativen_import(self):
        """Gegenprobe auf die PRUEFLOGIK selbst - ohne sie waere nicht
        feststellbar, ob der Test oben ueberhaupt etwas finden kann."""
        baum = ast.parse("from . import trading")
        gefunden: set[str] = set()
        for k in ast.walk(baum):
            if isinstance(k, ast.ImportFrom):
                if k.module:
                    gefunden.add(k.module)
                for n in k.names:
                    gefunden.add(n.name)
        assert "trading" in gefunden

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


class TestSimulationFaehrtDieLiveStrategie:
    """REGRESSION (21.08.2026): Die Historien-Simulation simulierte eine
    andere Strategie als den Bot.

    `scripts/10_simulate.py` versprach in Zeile 2 "exakt der Ablauf des
    spaeteren Live-Betriebs" und baute dann `EngineConfig()` - die
    Momentum-Voreinstellung. Der Bot faehrt `for_reversal()`. Acht von
    zehn entscheidenden Feldern wichen ab, darunter `max_hold_days`
    60 gegen 5 und `target_atr` 6.0 gegen 2.0. Im abgelegten Ergebnis
    (`results/simulation/trades.csv`, 821 Trades) betrug die mittlere
    Haltedauer 17,3 Tage, live sind es 5.

    Dazu wurde `market` nie durchgereicht. Ohne SPY faellt
    `ReversalWeights.market_regime_filter` still aus - die Simulation
    kaufte in Crashs hinein, die der Live-Bot aussitzt.

    Derselbe Fehlertyp wie bei `TestFlottenReferenz`: eine schriftliche
    Zusicherung, unter der die Wirklichkeit weglief. Deshalb hier als
    Invariante und nicht als Momentaufnahme.
    """

    @staticmethod
    def _quelle() -> str:
        return (PROJECT_ROOT / "scripts" / "10_simulate.py").read_text(
            encoding="utf-8")

    def _run_aufruf(self) -> ast.Call:
        """Der `simulate.run(...)`-Aufruf des Skripts."""
        for knoten in ast.walk(ast.parse(self._quelle())):
            if (isinstance(knoten, ast.Call)
                    and isinstance(knoten.func, ast.Attribute)
                    and knoten.func.attr == "run"
                    and isinstance(knoten.func.value, ast.Name)
                    and knoten.func.value.id == "simulate"):
                return knoten
        pytest.fail("Kein simulate.run(...) in scripts/10_simulate.py gefunden.")

    @staticmethod
    def _sim_modul():
        """`scripts/10_simulate.py` als Modul - der Name faengt mit einer
        Ziffer an und ist deshalb nicht importierbar."""
        import importlib.util

        pfad = PROJECT_ROOT / "scripts" / "10_simulate.py"
        spec = importlib.util.spec_from_file_location("_sim10", pfad)
        modul = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modul)
        return modul

    def test_konfiguration_ist_feldweise_die_live_konfiguration(self):
        """Der schaerfste Test der Klasse - und der einzige, der den
        zweiten Teil des Fehlers gefunden haette.

        Eine erste Fassung pruefte nur, DASS `for_reversal()` benutzt
        wird. Das war zu grob: `for_reversal()` allein hat
        `deploy_to_target=False` und `allow_topup=False`, der Live-Bot
        faehrt beide auf True. Der erste grosse Lauf (1.186 Symbole,
        7 Jahre) war damit trotz bestandenem Test nicht der Bot.

        Es sind exakt die zwei Felder aus §G6. Zweimal derselbe Fehler an
        derselben Stelle - deshalb hier feldweise statt strukturell.
        """
        sim = self._sim_modul().live_engine_config().as_dict()
        live = live_konfiguration().as_dict()
        unterschiede = {k: (sim.get(k), live[k]) for k in live
                        if sim.get(k) != live[k]}
        assert not unterschiede, (
            f"Die Simulation faehrt nicht den Live-Bot: {unterschiede} "
            "(Format: Feld -> (Simulation, Live)). Entweder wurden die "
            "Voreinstellungen in 12_daemon.py geaendert oder "
            "live_engine_config() - beides muss zusammen wandern."
        )

    def test_baut_die_konfiguration_ueber_for_reversal(self):
        """Der Kernfehler. `EngineConfig(...)` blank ist die falsche
        Strategie, egal welche Argumente daneben stehen."""
        aufrufe = [
            k for k in ast.walk(ast.parse(self._quelle()))
            if isinstance(k, ast.Call) and (
                (isinstance(k.func, ast.Name) and k.func.id == "EngineConfig")
                or (isinstance(k.func, ast.Attribute)
                    and isinstance(k.func.value, ast.Name)
                    and k.func.value.id == "EngineConfig"))
        ]
        assert aufrufe, "Die Simulation baut gar keine EngineConfig mehr."
        for k in aufrufe:
            assert isinstance(k.func, ast.Attribute) and k.func.attr == "for_reversal", (
                "scripts/10_simulate.py instanziiert EngineConfig direkt. "
                "Das ist die Momentum-Voreinstellung, nicht die Strategie "
                "des Live-Bots - das Ergebnis saegt am eigenen Ast."
            )

    def test_reicht_den_marktfilter_durch(self):
        """`market=` ist kein Komfortargument, sondern der Regimefilter."""
        aufruf = self._run_aufruf()
        assert any(kw.arg == "market" for kw in aufruf.keywords), (
            "simulate.run() bekommt kein `market`. Ohne SPY setzt "
            "build_reversal_frame markt_ok auf 1.0 und der Filter "
            "verschwindet lautlos - siehe test_ohne_markt_faellt_der_filter_still_aus."
        )

    def test_ohne_markt_faellt_der_filter_still_aus(self):
        """Gegenprobe, warum der Test darueber noetig ist.

        Der Ausfall des Filters wirft nichts und protokolliert nichts. Er
        macht nur jedes Ergebnis besser, als es waere. Genau diese
        Fehlerrichtung faellt bei einer Auswertung nie auf.
        """
        import numpy as np
        import pandas as pd

        from alpaca_bot.signals import build_reversal_frame

        idx = pd.date_range("2020-01-01", periods=300, freq="B", tz="UTC")
        kurs = pd.Series(np.linspace(100, 60, 300), index=idx)
        df = pd.DataFrame({"open": kurs, "high": kurs * 1.01,
                           "low": kurs * 0.99, "close": kurs,
                           "volume": 1_000_000.0}, index=idx)
        # Baerenmarkt: der Index liegt am Ende klar unter seinem
        # 200-Tage-Schnitt, der Live-Bot kauft hier nichts.
        markt = pd.Series(np.linspace(400, 250, 300), index=idx)

        mit = build_reversal_frame(df, markt)
        ohne = build_reversal_frame(df, None)
        assert mit["markt_ok"].iloc[-1] == 0.0
        assert ohne["markt_ok"].iloc[-1] == 1.0
        assert mit["score"].iloc[-1] == 0.0
        assert ohne["score"].iloc[-1] > 0.0

    def test_simuliert_das_live_universum(self):
        """Dieselbe Symbolzahl wie der Bot - sonst handelt die Simulation
        eine andere Auswahl.

        `load_universe` sortiert nach Umsatz. Wer hier 2.168 statt 1.200
        einsetzt, nimmt 968 Werte dazu, die der Bot nie sieht, und zwar
        durchweg die duennsten - genau das Segment mit dem groessten
        Survivorship Bias (18 % Delisting/Jahr gegen 2 % bei Large Caps).
        """
        def default_von(pfad: str, flag: str):
            baum = ast.parse((PROJECT_ROOT / pfad).read_text(encoding="utf-8"))
            for k in ast.walk(baum):
                if not (isinstance(k, ast.Call)
                        and isinstance(k.func, ast.Attribute)
                        and k.func.attr == "add_argument"):
                    continue
                if not any(isinstance(a, ast.Constant) and a.value == flag
                           for a in k.args):
                    continue
                for kw in k.keywords:
                    if kw.arg == "default" and isinstance(kw.value, ast.Constant):
                        return kw.value.value
            return None

        live = default_von("scripts/12_daemon.py", "--max-symbols")
        sim = default_von("scripts/10_simulate.py", "--max-symbols")
        assert live is not None and sim is not None
        assert sim == live, (
            f"Die Simulation laeuft ueber {sim} Symbole, der Live-Bot ueber "
            f"{live}. Ein Ergebnis aus einem anderen Universum sagt ueber "
            "den laufenden Bot nichts aus."
        )

    def test_score_urteil_kommt_aus_dem_gruppierten_test(self):
        """REGRESSION (21.08.2026): Das Skript druckte eine Score-Tabelle
        mit jedem Trade einzeln und darunter den Satz „Wenn hoehere Scores
        NICHT bessere Ergebnisse liefern, misst der Score nichts
        Verwertbares."

        Im Lauf ueber 1.201 Symbole sah diese Tabelle nach einem
        dramatischen Befund aus: 2.302 Trades mit den hoechsten Scores
        hatten eine negative Durchschnittsrendite, 169 mit den
        niedrigsten eine positive. Gruppiert nach Handelstag: **t =
        -0,09**. Nichts davon hielt. Das Werkzeug lud zu genau dem
        Fehlschluss ein, den CLAUDE.md und §B1 verbieten.
        """
        quelle = self._quelle()
        assert "misst der Score nichts Verwertbares" not in quelle, (
            "Der naive Schlusssatz unter der Score-Tabelle ist zurueck."
        )
        assert "gruppierte_pruefung" in quelle

    def test_gruppierter_test_schlaegt_den_naiven(self):
        """Gegenprobe an konstruierten Daten: gleiche Zahlen, zwei
        Urteile. Ohne diesen Unterschied waere die Gruppierung Zierrat.

        Gebaut wird reines Marktrauschen - an jedem Tag bewegt sich
        alles gemeinsam, der Score sortiert nichts. Der naive t-Wert
        sieht darin trotzdem einen Effekt, weil er 40 Trades pro Tag als
        40 unabhaengige Belege zaehlt.
        """
        import numpy as np
        import pandas as pd

        from alpaca_bot import statistik

        rng = np.random.default_rng(7)
        zeilen = []
        for i in range(60):
            tagesbewegung = rng.normal(0.004, 0.001)   # der ganze Tag zieht mit
            for _ in range(40):
                zeilen.append({"tag": i, "wert": tagesbewegung + rng.normal(0, 0.0005)})
        df = pd.DataFrame(zeilen)
        r = statistik.gruppierter_test(df["wert"], df["tag"])

        assert abs(r.t_naiv) > 3 * abs(r.t), (
            f"Der naive t-Wert ({r.t_naiv:.1f}) muesste den gruppierten "
            f"({r.t:.1f}) hier deutlich uebertreiben - sonst pruefen die "
            "beiden Verfahren dasselbe und die Gruppierung waere wirkungslos."
        )
        assert r.n_gruppen == 60 and r.n_beobachtungen == 2400

    def test_live_bot_faehrt_wirklich_reversal(self):
        """Bindeglied: `for_reversal` ist nur dann die richtige Wahl fuer
        die Simulation, solange der Live-Bot diese Strategie faehrt.
        Wechselt er, muss dieser Test brechen - nicht das Ergebnis."""
        assert live_konfiguration().strategy == "reversal"

    def test_ergebnisse_tragen_ihre_konfiguration(self):
        """Die alte `trades.csv` verriet mit keinem Feld, aus welcher
        Konfiguration sie stammte. Erst dadurch konnte die Abweichung
        monatelang unbemerkt bleiben.

        Geprueft wird der SCHREIBVORGANG, nicht das Vorkommen der
        Zeichenkette. Eine erste Fassung dieses Tests suchte nur nach
        "lauf.json" irgendwo im Quelltext - und ueberlebte den Mutanten,
        der das Ziel der Datei aenderte und die Erwaehnung im
        Ausgabetext stehen liess.
        """
        baum = ast.parse(self._quelle())
        ziele = [
            k for k in ast.walk(baum)
            if isinstance(k, ast.Call)
            and isinstance(k.func, ast.Attribute)
            and k.func.attr == "write_text"
            and any(isinstance(t, ast.Constant) and t.value == "lauf.json"
                    for t in ast.walk(k.func.value))
        ]
        assert ziele, (
            "scripts/10_simulate.py schreibt keine lauf.json mehr. Ein "
            "Ergebnis ohne seine Konfiguration ist keine Messung."
        )
        inhalt = ast.dump(baum)
        for feld in ("engine_config", "marktfilter_aktiv", "n_symbole_mit_daten"):
            assert f"'{feld}'" in inhalt, f"Feld {feld} fehlt in der lauf.json."
