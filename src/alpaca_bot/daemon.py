"""Autonomer Dauerbetrieb - ueberlebt Abstuerze, Neustarts und Stromausfall.

Der Bot trifft selbstaendig Entscheidungen, solange er laeuft. Stirbt der
Prozess, startet ihn der Betriebssystemdienst neu (siehe
`scripts/install_service.sh`). Nach dem Neustart stellt er den Zustand
wieder her und macht weiter, als waere nichts gewesen.

**Warum das funktioniert - der Entwurf ist bewusst zustandsarm:**

Der Bot haelt keinen wichtigen Zustand im Arbeitsspeicher. Die Wahrheit
liegt an zwei Orten, die einen Absturz ueberleben:

    Alpaca         -> welche Positionen existieren, Kapital, Daytrades
    state.sqlite   -> Stop, Ziel, Einstiegsdatum, Begruendung dazu

Beim Start liest er beides und baut daraus den Zustand neu auf. Ein
Neustart mitten im Handelstag ist damit unkritisch. Selbst wenn
state.sqlite verloren geht, laeuft der Bot weiter - er ergaenzt fehlende
Marken dann konservativ und meldet es.

**Was der Daemon NICHT tut:** Er handelt nicht ausserhalb der
Boersenzeiten und nicht in den ersten Minuten nach Eroeffnung. Die
Eroeffnungsspanne ist die volatilste und teuerste Phase des Tages -
Spreads sind dort ein Vielfaches des Normalwerts. Der Backtest rechnet
mit Eroeffnungskursen des Folgetags, aber mit normalen Spannen.
"""

from __future__ import annotations

import datetime as dt
import signal
import time
import traceback
from dataclasses import dataclass, field

import pandas as pd

from . import account, compliance, live, trading
from .engine import EngineConfig, Position
from .journal import Journal
from .state import Store


@dataclass
class DaemonConfig:
    symbols: list[str] = field(default_factory=list)
    dry_run: bool = True
    """Standard ist Vorschau. Echtes Senden muss explizit gewaehlt werden."""

    interval_seconds: int = 900
    """Abstand zwischen zwei Entscheidungslaeufen waehrend der Handelszeit."""

    idle_seconds: int = 1800
    """Abstand bei geschlossener Boerse. Laenger, weil nichts passieren kann."""

    open_delay_minutes: int = 20
    """So lange nach Eroeffnung nicht handeln - die Eroeffnungsspanne ist
    die teuerste Zeit des Tages."""

    close_buffer_minutes: int = 15
    """So lange vor Schluss nicht mehr eroeffnen."""

    max_new_positions: int = 3
    """Kaeufe je Lauf. Begrenzt den Schaden, falls die Logik fehlerhaft ist."""

    max_consecutive_errors: int = 10
    """Danach beendet sich der Prozess mit Fehlercode - der Dienst startet
    ihn neu. Ein sauberer Neustart ist verlaesslicher als ein Prozess, der
    in einem kaputten Zustand weiterlaeuft."""

    engine: EngineConfig = field(default_factory=EngineConfig.for_reversal)


class Daemon:
    """Die Dauerschleife."""

    def __init__(self, config: DaemonConfig):
        self.cfg = config
        self.store = Store()
        self.journal = Journal()
        self._stop = False
        self._errors = 0
        self._last_evaluation: dt.date | None = None

        # Auf Beendigungssignale sauber reagieren, damit der Zustand
        # konsistent bleibt und der Dienst nicht in einer Schleife haengt.
        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, self._handle_signal)

    def _handle_signal(self, signum, frame) -> None:  # noqa: ARG002
        print(f"\n  Signal {signum} empfangen - beende nach dem laufenden Schritt.")
        self._stop = True

    # --- Zustandswiederherstellung ----------------------------------------
    def recover(self) -> dict:
        """Baut den Zustand aus Broker + Datenbank neu auf.

        Laeuft bei JEDEM Start. Alpaca sagt, welche Positionen es gibt;
        die Datenbank liefert die Marken dazu. Beides wird abgeglichen.
        """
        acct = account.account_summary()
        broker_positions = account.positions()
        broker_symbols = set(broker_positions.index)

        orphans = self.store.sync_with_broker(broker_symbols)
        stored = self.store.load_positions()

        missing = broker_symbols - set(stored)
        for sym in missing:
            row = broker_positions.loc[sym]
            entry = float(row["avg_entry"])
            # Konservative Ergaenzung: enger Stop, damit eine Position
            # ohne bekannte Historie nicht unbegrenzt weiterlaeuft.
            self.store.save_position(
                sym, entry_price=entry,
                entry_date=pd.Timestamp.now(tz="UTC").normalize(),
                stop_price=entry * 0.93, target_price=entry * 1.10,
                high_water=max(entry, float(row.get("current_price") or entry)),
                reasons={"herkunft": "beim Start vorgefunden, Marken geschaetzt"},
            )

        # --- Einstandskurs mit dem Broker abgleichen ---
        # Entschieden wird auf dem Schlusskurs des Vortages, ausgefuehrt wird
        # am naechsten Handelstag zum dann gueltigen Kurs. Zwischen beidem
        # koennen Prozente liegen. Stop und Ziel muessen sich am ECHTEN
        # Einstand orientieren, sonst steht der Stop nach einer Kursluecke
        # sofort im Geld oder unerreichbar weit weg.
        adjusted = []
        for sym in broker_symbols & set(stored):
            meta = stored[sym]
            real_entry = float(broker_positions.loc[sym, "avg_entry"])
            saved_entry = float(meta["entry_price"])
            if saved_entry <= 0:
                continue
            drift = abs(real_entry / saved_entry - 1)
            if drift > 0.005:
                scale = real_entry / saved_entry
                self.store.save_position(
                    sym, entry_price=real_entry,
                    entry_date=meta["entry_date"],
                    stop_price=float(meta["stop_price"]) * scale,
                    target_price=float(meta["target_price"]) * scale,
                    high_water=max(real_entry, float(meta["high_water"]) * scale),
                    bars_held=int(meta["bars_held"]),
                    entry_score=meta["entry_score"],
                    reasons={"korrigiert": f"Einstand {saved_entry:.2f} -> "
                                           f"{real_entry:.2f} laut Broker"},
                )
                adjusted.append(f"{sym} ({drift:.1%})")

        return {
            "kapital": float(acct["portfolio_value"]),
            "positionen_broker": len(broker_symbols),
            "metadaten_geladen": len(stored),
            "verwaist_entfernt": orphans,
            "ohne_metadaten_ergaenzt": sorted(missing),
            "einstand_korrigiert": adjusted,
            "daytrades": int(acct.get("daytrade_count") or 0),
        }

    def _record_lifecycle(self, decision, meta: dict) -> None:
        """Legt den Lebenslauf eines geschlossenen Trades an.

        MAE, MFE und der Nachlauf werden hier noch nicht gefuellt - der
        Kursverlauf NACH dem Ausstieg existiert schlicht noch nicht.
        Das ergaenzt `_analyse_closed_trades()` in den Folgetagen.
        """
        try:
            import uuid

            from .lifecycle import Lifecycle

            entry = meta.get("entry_price")
            Lifecycle().record({
                "trade_id": uuid.uuid4().hex,
                "symbol": decision.symbol,
                "entry_date": str(meta.get("entry_date") or ""),
                "entry_price": entry,
                "entry_score": meta.get("entry_score"),
                "entry_reasons": meta.get("reasons"),
                "planned_stop": meta.get("stop_price"),
                "planned_target": meta.get("target_price"),
                "exit_date": pd.Timestamp.now(tz="UTC").isoformat(),
                "exit_price": decision.price,
                "exit_reason": str(decision.reasons.get("ausstiegsgrund", "")),
                "return_pct": decision.reasons.get("gewinn_pct"),
                "bars_held": meta.get("bars_held"),
            })
        except Exception as e:  # noqa: BLE001 - darf den Handel nie stoppen
            print(f"      Lebenslauf nicht erfasst: {type(e).__name__}: {e}")

    def _analyse_closed_trades(self) -> None:
        """Ergaenzt MAE, MFE und Nachlauf fuer bereits geschlossene Trades.

        Laeuft einmal taeglich mit der Ergebnisbewertung mit. Der Nachlauf
        braucht Zeit: Ob ein Ausstieg richtig war, zeigt sich erst Tage
        spaeter - deshalb wird jeder Trade mehrfach nachbearbeitet, bis
        alle Zeitfenster gefuellt sind.
        """
        try:
            from . import data
            from .lifecycle import Lifecycle, analyse_path

            lc = Lifecycle()
            offen = lc.pending_analysis()
            if not offen:
                return

            df = lc.table()
            todo = df[df["trade_id"].isin(offen) & df["exit_date"].notna()]
            if todo.empty:
                return

            symbols = sorted(todo["symbol"].unique())[:100]
            bars = data.get_bars(symbols, "1D", lookback_days=90)
            if bars.empty:
                return

            ergaenzt = 0
            for _, t in todo.iterrows():
                try:
                    sym_bars = bars.xs(t["symbol"], level="symbol")
                except KeyError:
                    continue
                extra = analyse_path(
                    sym_bars, t["entry_date"], t["exit_date"],
                    float(t["entry_price"] or 0),
                )
                if not extra:
                    continue
                row = t.to_dict()
                row.update(extra)
                row["analysed_at"] = pd.Timestamp.now(tz="UTC").isoformat()
                lc.record(row)
                ergaenzt += 1
            if ergaenzt:
                print(f"      {ergaenzt} Trade-Lebenslauf/-laeufe ergaenzt")
        except Exception as e:  # noqa: BLE001
            print(f"      Lebenslauf-Analyse fehlgeschlagen: {type(e).__name__}: {e}")

    def _maybe_evaluate_outcomes(self) -> None:
        """Ordnet einmal taeglich jeder Entscheidung ihr Ergebnis zu.

        Das ist der Schritt, der aus Protokoll Lernen macht: Ohne ihn
        bleibt `journal.decision_quality()` leer, und die Frage "welche
        Begruendung hat sich bewaehrt" ist nicht zu beantworten.

        Nur einmal je Kalendertag, weil dafuer Kursdaten geladen werden.
        """
        today = dt.date.today()
        if self._last_evaluation == today:
            return
        try:
            from . import data
            from .journal import make_price_lookup

            decisions = self.journal.table("decisions")
            if decisions.empty:
                self._last_evaluation = today
                return
            symbols = sorted(decisions["symbol"].dropna().unique())[:200]
            bars = data.get_bars(symbols, "1D", lookback_days=120)
            n = self.journal.evaluate_outcomes(
                make_price_lookup(bars), horizons=(1, 3, 5)
            )
            print(f"      {n} Ergebnis(se) zu Entscheidungen nachgetragen")
            self._analyse_closed_trades()
            self._last_evaluation = today
        except Exception as e:  # noqa: BLE001
            print(f"      Ergebnisbewertung fehlgeschlagen: {type(e).__name__}: {e}")

    # --- Handelsfenster ----------------------------------------------------
    def trading_window(self) -> tuple[bool, str]:
        """Darf jetzt gehandelt werden?"""
        clock = account.market_clock()
        if not clock["is_open"]:
            return False, "Boerse geschlossen"

        now = pd.Timestamp.now(tz="UTC")
        next_close = pd.Timestamp(clock["next_close"])
        if next_close.tz is None:
            next_close = next_close.tz_localize("UTC")

        minutes_to_close = (next_close - now).total_seconds() / 60
        if minutes_to_close < self.cfg.close_buffer_minutes:
            return False, f"kurz vor Schluss ({minutes_to_close:.0f} Min)"

        # Eroeffnungsspanne meiden: Handelstag dauert 6.5 Stunden.
        minutes_since_open = 390 - minutes_to_close
        if minutes_since_open < self.cfg.open_delay_minutes:
            return False, (f"Eroeffnungsspanne, noch "
                           f"{self.cfg.open_delay_minutes - minutes_since_open:.0f} Min warten")
        return True, "offen"

    # --- Ein Durchgang -----------------------------------------------------
    def step(self) -> bool:
        """Ein Entscheidungslauf. Gibt zurueck, ob er erfolgreich war."""
        can_trade, reason = self.trading_window()
        if not can_trade:
            print(f"  [{dt.datetime.now():%H:%M:%S}] kein Handel: {reason}")
            self.store.heartbeat(ok=True)
            return True

        # Ausfuehrungspreise der letzten Orders nachtragen. Muss VOR dem
        # Entscheiden passieren, damit die Slippage-Auswertung vollstaendig
        # bleibt, auch wenn der Prozess zwischendurch neu gestartet wurde.
        try:
            filled = live.reconcile_fills()
            if filled:
                print(f"      {filled} Ausfuehrungspreis(e) nachgetragen")
        except Exception as e:  # noqa: BLE001 - darf den Lauf nicht stoppen
            print(f"      Fuellpreis-Abgleich fehlgeschlagen: {type(e).__name__}")

        self._maybe_evaluate_outcomes()

        state = self.recover()
        print(f"  [{dt.datetime.now():%H:%M:%S}] Kapital "
              f"${state['kapital']:,.2f} | {state['positionen_broker']} Positionen")
        if state["verwaist_entfernt"]:
            print(f"      verwaiste Metadaten entfernt: "
                  f"{', '.join(state['verwaist_entfernt'])}")
        if state["ohne_metadaten_ergaenzt"]:
            print(f"      Positionen ohne Zustand ergaenzt: "
                  f"{', '.join(state['ohne_metadaten_ergaenzt'])}")

        result = live.run_once(
            self.cfg.symbols, self.cfg.engine,
            dry_run=self.cfg.dry_run,
            max_new_positions=self.cfg.max_new_positions,
            verbose=True,
        )

        # Zustand fortschreiben - AUSSCHLIESSLICH fuer abgeschickte Orders.
        # result.decisions enthaelt auch die Vorschlaege, die `max_new_positions`
        # abgeschnitten hat; wer die mitschreibt, erfindet Positionen.
        if not self.cfg.dry_run:
            for d in result.executed_decisions:
                if d.action == "buy" and d.target_notional > 0:
                    self.store.save_position(
                        d.symbol, entry_price=d.price,
                        entry_date=pd.Timestamp.now(tz="UTC").normalize(),
                        stop_price=d.stop_price, target_price=d.target_price,
                        high_water=d.price, entry_score=d.conviction,
                        reasons=d.reasons,
                    )
                elif d.action == "sell":
                    # Ausstieg festhalten, BEVOR die Metadaten geloescht werden -
                    # danach ist der Einstiegskurs nicht mehr verfuegbar.
                    meta = self.store.load_positions().get(d.symbol, {})
                    self.store.record_exit(
                        d.symbol,
                        exit_price=d.price,
                        exit_reason=str(d.reasons.get("ausstiegsgrund", "")),
                        entry_price=meta.get("entry_price"),
                        return_pct=d.reasons.get("gewinn_pct"),
                        bars_held=meta.get("bars_held"),
                    )
                    self._record_lifecycle(d, meta)
                    self.store.drop_position(d.symbol)
                # `topup` wird hier BEWUSST nicht behandelt: `live.py` hat den
                # Zustand ueber `_nachkauf_im_zustand()` bereits fortgeschrieben
                # (Mischkurs beim Einstand, Stop/Ziel/bars_held unveraendert).
                # Ein zweiter save_position() hier wuerde genau diese sorgsam
                # erhaltenen Marken mit den Werten der Nachkauf-Entscheidung
                # ueberschreiben und die Haltefrist zuruecksetzen.

        self.store.heartbeat(
            ok=True, equity=result.equity,
            positions=state["positionen_broker"],
        )
        return True

    # --- Dauerschleife -----------------------------------------------------
    def run_forever(self) -> int:
        """Laeuft, bis er beendet wird oder zu viele Fehler auftreten."""
        print("=" * 72)
        print(f"  DAEMON GESTARTET  |  "
              f"{'VORSCHAU' if self.cfg.dry_run else 'ORDERS AKTIV'}")
        print("=" * 72)
        print(f"  Universum : {len(self.cfg.symbols)} Symbole")
        print(f"  Takt      : {self.cfg.interval_seconds}s (Handel) / "
              f"{self.cfg.idle_seconds}s (geschlossen)")
        print(f"  Strategie : {self.cfg.engine.strategy}, "
              f"max. {self.cfg.engine.max_positions} Positionen")
        print()

        try:
            state = self.recover()
            print("  Zustand wiederhergestellt:")
            for k, v in state.items():
                print(f"    {k:<26} {v}")
            print()
        except Exception as e:  # noqa: BLE001
            print(f"  Wiederherstellung fehlgeschlagen: {type(e).__name__}: {e}")

        while not self._stop:
            try:
                self.step()
                self._errors = 0
            except KeyboardInterrupt:
                break
            except Exception as e:  # noqa: BLE001
                self._errors += 1
                msg = f"{type(e).__name__}: {e}"
                print(f"  [FEHLER {self._errors}/{self.cfg.max_consecutive_errors}] {msg}")
                traceback.print_exc()
                try:
                    self.store.heartbeat(ok=False, error=msg)
                except Exception as heartbeat_err:  # noqa: BLE001
                    # Die Fehlerprotokollierung darf selbst nie zum Absturz-
                    # grund werden. Genau das ist am 30./31.07.2026 passiert:
                    # ein voruebergehender SSL-Fehler war an sich harmlos und
                    # haette der Retry-Logik unten weichen sollen - stattdessen
                    # scheiterte der heartbeat()-Aufruf selbst (TCC blockierte
                    # state.sqlite unter ~/Documents fuer den headless
                    # gestarteten Dienst), diese zweite Exception war
                    # ungeschuetzt und riss den gesamten Prozess mit runter.
                    print(f"  [FEHLER] Fehlerprotokollierung fehlgeschlagen: "
                          f"{type(heartbeat_err).__name__}: {heartbeat_err}")

                if self._errors >= self.cfg.max_consecutive_errors:
                    print("\n  Zu viele Fehler in Folge - beende mit Fehlercode.")
                    print("  Der Systemdienst startet den Prozess neu.")
                    return 1
                # Wartezeit bei wiederholten Fehlern verlaengern.
                time.sleep(min(300, 30 * self._errors))
                continue

            can_trade, _ = self.trading_window()
            wait = self.cfg.interval_seconds if can_trade else self.cfg.idle_seconds
            for _ in range(wait):
                if self._stop:
                    break
                time.sleep(1)

        print("\n  Daemon sauber beendet.")
        return 0
