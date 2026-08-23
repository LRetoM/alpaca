"""Die vier Schritte des Schattenbetriebs - hier entstehen die Daten.

    entscheiden()   nach US-Schluss: Kandidaten des Tages festhalten
    einbuchen()     naechster Handelstag: Eroeffnungskurs nachtragen
    verifizieren()  laufend: was ist tatsaechlich daraus geworden
    lernen()        Muster pruefen, Kandidaten suchen, Zerfall melden

Alle vier sind **idempotent**: Ohne neuen Handelstag tun sie nichts
(§G14). Das ist die Voraussetzung dafuer, den Durchgang haeufig laufen
zu lassen.

Dieses Modul importiert bewusst **kein** `trading.py` - geprueft von
`selfcheck.check_schatten_handelt_nicht` (Verfassungsregel 9, §G19).
Geteilt wird dagegen `Engine.decide()`: eine Entscheidungslogik,
verschiedene Datenquellen.

**Herkunft: Aufteilung von `shadow.py` am 23.08.2026 (BEFUNDE §G20).**
Der Schattenbetrieb lag in EINER Datei mit 2.339 Zeilen und fuenf
Verantwortungen. Der Code in diesem Modul wurde dabei **unveraendert**
verschoben - kein Ausdruck, keine Zeile Logik wurde angefasst. Nachgewiesen
ueber den Bytecode jeder Funktion, nicht behauptet (`scripts/29_umzug_pruefen.py`).
"""


from __future__ import annotations

import datetime as dt
import json
import uuid

import numpy as np
import pandas as pd

from .costs import DEFAULT_FEES, estimate_costs
from .engine import (Engine, EngineConfig, MarketSnapshot,
                     PortfolioState, Position)
from .shadow_config import HORIZONTE, MARKET_SYMBOL, ShadowConfig
from .shadow_daten import (_news_kontext, _regime, _signalrahmen,
                           _universum_symbole, baue_snapshot, lade_bars)
from .shadow_store import ShadowStore, _json, code_version


class ShadowEngine(Engine):
    """Engine fuer den Schattenbetrieb - mit EIGENER Sperrfrist-Quelle.

    `Engine._cooldown_symbols()` liest die Sperrfrist fest aus `state.sqlite`,
    also aus dem Zustand des LIVE-Bots. Fuer das Spiegelbuch waere das ein
    stiller Fehler in beide Richtungen: Der Schatten wuerde Symbole meiden,
    die nur der echte Bot verkauft hat, und umgekehrt seine eigenen Verkaeufe
    nicht beruecksichtigen. Beide Buecher wuerden dadurch etwas anderes
    messen, als sie zu messen vorgeben.

    Deshalb wird die Quelle hier ueberschrieben statt `engine.py` zu aendern -
    der Handelspfad bleibt unberuehrt.
    """

    def __init__(self, config: EngineConfig, store: "ShadowStore", bot_id: str):
        super().__init__(config)
        self._store = store
        self._bot_id = bot_id

    def _cooldown_symbols(self, as_of: pd.Timestamp) -> set[str]:
        days = self.cfg.reenter_cooldown_days
        if days <= 0:
            return set()
        return self._store.symbole_in_sperrfrist(self._bot_id, days, as_of)

def _rangliste(bot, snap: MarketSnapshot, store: ShadowStore, run_id: str,
               regime: dict, cv: str, max_new: int = 3,
               news: dict[str, dict] | None = None) -> int:
    """Buch 'rangliste': jeder Kandidat, ohne Kapitalgrenze.

    `Engine.decide()` bleibt die einzige Quelle fuer Bewertung und Filterung
    (Liquiditaet, Mindestkurs, min_score). Nur die KAPITALlogik wird
    neutralisiert - das ist genau die Definition dieses Buchs. Ohne
    `min_position_pct=0` fiele `per_slot` bei vielen Kandidaten unter die
    Mindestgroesse und die Engine liefe leer.
    """
    ecfg = EngineConfig(**{**bot.config.as_dict(),
                           "max_positions": 10_000, "min_position_pct": 0.0})
    ecfg.reversal_weights = bot.config.reversal_weights
    ecfg.weights = bot.config.weights

    decisions = Engine(ecfg).decide(snap, PortfolioState(cash=1e9, equity=1e9))
    buys = [d for d in decisions if d.action == "buy"]

    jetzt = dt.datetime.now(dt.UTC).isoformat()
    news = news or {}
    for i, d in enumerate(buys, start=1):
        n = news.get(d.symbol, {})
        store.save_prediction({
            "pred_id": uuid.uuid4().hex, "run_id": run_id, "bot_id": bot.bot_id,
            "buch": "rangliste", "as_of": snap.as_of.isoformat(),
            "decided_at": jetzt, "symbol": d.symbol, "aktion": "buy",
            "rang": i, "score": d.conviction, "decision_price": d.price,
            "planned_stop": d.stop_price, "planned_target": d.target_price,
            "planned_hold_days": bot.config.max_hold_days,
            "notional": d.target_notional, "reasons": _json(d.reasons),
            "atr_pct": d.reasons.get("atr_pct"),
            "liquiditaet": d.reasons.get("dollar_volume"),
            "wuerde_gehandelt": int(i <= max_new),
            "code_version": cv, "nachgetragen": 0,
            # news_z/news_5d/news_tage_her/news_erstabdeckung sind genau die
            # Werte, die auch in den Score eingeflossen sind (aus d.reasons,
            # von signals.build_reversal_frame) - nicht separat neu berechnet,
            # sonst koennten Anzeige und Entscheidung auseinanderlaufen.
            # news_ton/news_ereignis kommen weiterhin aus dem eigenstaendigen
            # Tonalitaets-/Ereignis-Kontext (news_features.py, wirkungslos
            # auf den Score - siehe _news_kontext).
            "news_z": d.reasons.get("news_z"),
            "news_5d": d.reasons.get("news_5d"),
            "news_erstabdeckung": d.reasons.get("news_erstabdeckung"),
            "news_tage_her": d.reasons.get("news_tage_her"),
            "news_aktiv": int(bool(d.reasons.get("news_aktiv"))),
            "news_ereignis": n.get("news_ereignis"),
            "news_ton": n.get("news_ton"),
            **regime,
        })
    return len(buys)

def _spiegel(bot, snap: MarketSnapshot, per_symbol: dict[str, pd.DataFrame],
             signale: dict[str, pd.DataFrame], store: ShadowStore, run_id: str,
             regime: dict, cv: str, cfg: ShadowConfig,
             verbose: bool = False) -> dict:
    """Buch 'spiegel': bildet den echten Bot exakt nach.

    Aufgeschobene Ausfuehrung wie in `simulate.py`: Entschieden wird auf dem
    Schlusskurs von Tag T, ausgefuehrt zur Eroeffnung von T+1. Kapitalgrenzen,
    Positionslimit, Sperrfrist und Kosten wirken vollstaendig.

    Der Lauf holt fehlende Handelstage nach (Wochenende, Ausfall). Er ist
    idempotent: `letzter_tag` in `shadow_cash` verhindert, dass ein Tag
    zweimal ausgefuehrt wird - sonst wuerde jede Wiederholung des Daemons
    dieselben Kaeufe erneut buchen.
    """
    store.depot_init(bot.bot_id, bot.startkapital)
    stand = store.depot_stand(bot.bot_id)
    cash = float(stand["cash"])

    kalender = [t for t in sorted({t for df in per_symbol.values() for t in df.index})]
    kalender = [pd.Timestamp(t) for t in kalender]
    kalender = [t.tz_localize("UTC") if t.tz is None else t for t in kalender]

    letzter = stand.get("letzter_tag")
    if letzter:
        lt = pd.Timestamp(letzter)
        lt = lt.tz_localize("UTC") if lt.tz is None else lt
        offen = [t for t in kalender if t > lt and t <= snap.as_of]
    else:
        # Erster Lauf: nur den aktuellen Tag entscheiden, nichts ausfuehren.
        # Rueckwirkend zu handeln waere kein Vorwaertstest (Plan §4.6).
        offen = [snap.as_of]

    # Positionen laden
    positionen: dict[str, Position] = {}
    meta: dict[str, dict] = {}
    for sym, m in store.depot_positionen(bot.bot_id).items():
        ed = pd.Timestamp(m["entry_date"])
        positionen[sym] = Position(
            symbol=sym, qty=float(m["qty"]), entry_price=float(m["entry_price"]),
            entry_date=ed.tz_localize("UTC") if ed.tz is None else ed,
            stop_price=float(m["stop_price"]), target_price=float(m["target_price"]),
            bars_held=int(m["bars_held"] or 0), high_water=float(m["high_water"]),
        )
        meta[sym] = m

    engine = ShadowEngine(bot.config, store, bot.bot_id)
    stat = {"kaeufe": 0, "verkaeufe": 0, "tage": 0}
    jetzt = dt.datetime.now(dt.UTC).isoformat()

    for tag in offen:
        stat["tage"] += 1

        # ---------- 1. Aufgeschobene Orders von gestern ausfuehren ----------
        for p in store.pending_holen(bot.bot_id):
            df = per_symbol.get(p["symbol"])
            if df is None or tag not in df.index:
                continue
            bar = df.loc[tag]
            fill = float(bar["open"])
            if not np.isfinite(fill) or fill <= 0:
                continue

            if p["aktion"] == "buy":
                if p["symbol"] in positionen:
                    continue
                qty = int((p["notional"] or 0) / fill)
                if qty <= 0:
                    continue
                k = estimate_costs("buy", qty, last=fill,
                                   spread_bps=cfg.spread_bps,
                                   slippage_bps=cfg.slippage_bps, fees=DEFAULT_FEES)
                if k.net_proceeds > cash:
                    qty = int(cash * 0.98 / (fill * 1.01))
                    if qty <= 0:
                        continue
                    k = estimate_costs("buy", qty, last=fill,
                                       spread_bps=cfg.spread_bps,
                                       slippage_bps=cfg.slippage_bps,
                                       fees=DEFAULT_FEES)
                cash -= k.net_proceeds
                pos = Position(
                    symbol=p["symbol"], qty=qty,
                    entry_price=float(k.effective_price), entry_date=tag,
                    stop_price=float(p["stop_price"] or 0),
                    target_price=float(p["target_price"] or 0),
                    bars_held=0, high_water=float(k.effective_price),
                )
                positionen[p["symbol"]] = pos
                store.depot_speichern(bot.bot_id, pos,
                                      entry_score=p["score"],
                                      reasons=json.loads(p["reasons"] or "{}"))
                store.save_prediction({
                    "pred_id": uuid.uuid4().hex, "run_id": run_id,
                    "bot_id": bot.bot_id, "buch": "spiegel",
                    # Der Stichtag ist der Tag der ENTSCHEIDUNG, nicht der
                    # letzte Tag des Laufs - sonst laege beim Nachholen der
                    # Einstieg formal vor dem Stichtag (Pruefung 1).
                    "as_of": p["as_of"], "decided_at": jetzt,
                    "symbol": p["symbol"], "aktion": "buy", "score": p["score"],
                    "decision_price": fill, "entry_date": tag.isoformat(),
                    "entry_price_open": fill, "entry_price": fill,
                    "entry_price_eff": float(k.effective_price),
                    "entry_timing": "open",
                    "planned_stop": p["stop_price"], "planned_target": p["target_price"],
                    "planned_hold_days": bot.config.max_hold_days,
                    "notional": qty * fill, "reasons": p["reasons"],
                    "wuerde_gehandelt": 1, "code_version": cv,
                    "nachgetragen": 0, **regime,
                })
                stat["kaeufe"] += 1

            elif p["aktion"] == "topup" and p["symbol"] in positionen:
                # Nachkauf: Stueckzahl waechst, Einstand wird zum Mischkurs.
                # Stop, Ziel und bars_held bleiben unveraendert - der Nachkauf
                # verstaerkt eine These, er stellt keine neue auf.
                pos = positionen[p["symbol"]]

                # Sicherheitscheck ZUM AUSFUEHRUNGSZEITPUNKT (heutige
                # Eroeffnung), nicht nur bei der Entscheidung (gestriger
                # Schluss). Dazwischen kann eine Kursluecke einen gestrigen
                # Gewinner in einen heutigen Verlierer verwandeln - siehe
                # live.py fuer den Fund (CHRW: +2,1% -> -5,4%).
                if pos.entry_price > 0 and (fill / pos.entry_price - 1) < bot.config.topup_min_gain_pct:
                    continue

                # Groesse ZUM AUSFUEHRUNGSKURS gegen den Deckel pruefen,
                # nicht die am Vortag beschlossene Notional blind uebernehmen
                # - siehe live.py fuer die ausfuehrliche Begruendung (CHRW-
                # Fund: derselbe Fehler kann eine Position je nach
                # Kursrichtung faelschlich blockieren oder ueber den Deckel
                # hinaus vergroessern).
                eq_schaetzung = float(stand.get("equity", cash) or cash)
                deckel = eq_schaetzung * bot.config.max_position_pct
                ist_wert = pos.qty * fill
                erlaubt = max(0.0, deckel - ist_wert)
                notional = min(float(p["notional"] or 0), erlaubt)

                qty = int(notional / fill)
                if qty <= 0:
                    continue
                k = estimate_costs("buy", qty, last=fill,
                                   spread_bps=cfg.spread_bps,
                                   slippage_bps=cfg.slippage_bps, fees=DEFAULT_FEES)
                if k.net_proceeds > cash:
                    qty = int(cash * 0.98 / (fill * 1.01))
                    if qty <= 0:
                        continue
                    k = estimate_costs("buy", qty, last=fill,
                                       spread_bps=cfg.spread_bps,
                                       slippage_bps=cfg.slippage_bps,
                                       fees=DEFAULT_FEES)
                cash -= k.net_proceeds
                neu_qty = pos.qty + qty
                pos.entry_price = (
                    (pos.qty * pos.entry_price + qty * float(k.effective_price))
                    / neu_qty
                )
                pos.qty = neu_qty
                pos.high_water = max(pos.high_water, float(k.effective_price))
                store.depot_speichern(bot.bot_id, pos,
                                      entry_score=p["score"],
                                      reasons=json.loads(p["reasons"] or "{}"))
                store.save_prediction({
                    "pred_id": uuid.uuid4().hex, "run_id": run_id,
                    "bot_id": bot.bot_id, "buch": "spiegel",
                    "as_of": p["as_of"], "decided_at": jetzt,
                    "symbol": p["symbol"], "aktion": "topup", "score": p["score"],
                    "decision_price": fill, "entry_date": tag.isoformat(),
                    "entry_price_open": fill, "entry_price": fill,
                    "entry_price_eff": float(k.effective_price),
                    "entry_timing": "open",
                    "planned_stop": p["stop_price"], "planned_target": p["target_price"],
                    "planned_hold_days": bot.config.max_hold_days,
                    "notional": qty * fill, "reasons": p["reasons"],
                    "wuerde_gehandelt": 1, "code_version": cv,
                    "nachgetragen": 0, **regime,
                })
                stat["nachkaeufe"] = stat.get("nachkaeufe", 0) + 1

            elif p["aktion"] == "sell" and p["symbol"] in positionen:
                pos = positionen.pop(p["symbol"])
                k = estimate_costs("sell", pos.qty, last=fill,
                                   spread_bps=cfg.spread_bps,
                                   slippage_bps=cfg.slippage_bps, fees=DEFAULT_FEES)
                cash += k.net_proceeds
                rendite = float(k.effective_price) / pos.entry_price - 1
                store.ausstieg_merken(
                    bot.bot_id, pos.symbol, exit_date=tag.isoformat(),
                    exit_price=float(k.effective_price),
                    exit_reason=str(json.loads(p["reasons"] or "{}")
                                    .get("ausstiegsgrund", "signal")),
                    entry_price=pos.entry_price, return_pct=round(rendite, 5),
                    bars_held=pos.bars_held,
                )
                store.depot_loeschen(bot.bot_id, pos.symbol)
                meta.pop(pos.symbol, None)
                stat["verkaeufe"] += 1
        store.pending_leeren(bot.bot_id)

        # ---------- 2. Offene Positionen pflegen ----------
        for sym, pos in list(positionen.items()):
            df = per_symbol.get(sym)
            if df is None or tag not in df.index:
                continue
            bar = df.loc[tag]
            frame = signale.get(sym)
            atr = 0.0
            if frame is not None:
                bis = frame.loc[:tag]
                if len(bis):
                    atr = float(bis.iloc[-1].get("atr", 0) or 0)
            engine.update_position(pos, float(bar["close"]), atr)

            # Intraday-Stop: im Tagesverlauf gerissen?
            if float(bar["low"]) <= pos.stop_price:
                fill = min(pos.stop_price, float(bar["open"]))
                k = estimate_costs("sell", pos.qty, last=fill,
                                   spread_bps=cfg.spread_bps,
                                   slippage_bps=cfg.slippage_bps, fees=DEFAULT_FEES)
                cash += k.net_proceeds
                store.ausstieg_merken(
                    bot.bot_id, sym, exit_date=tag.isoformat(),
                    exit_price=float(k.effective_price), exit_reason="stop_intraday",
                    entry_price=pos.entry_price,
                    return_pct=round(float(k.effective_price) / pos.entry_price - 1, 5),
                    bars_held=pos.bars_held,
                )
                store.depot_loeschen(bot.bot_id, sym)
                positionen.pop(sym, None)
                stat["verkaeufe"] += 1
            else:
                store.depot_speichern(bot.bot_id, pos,
                                      entry_score=(meta.get(sym) or {}).get("entry_score"))

        # ---------- 3. Kontowert ----------
        equity = cash
        for sym, pos in positionen.items():
            df = per_symbol.get(sym)
            kurs = (float(df.loc[tag, "close"])
                    if df is not None and tag in df.index else pos.entry_price)
            equity += pos.qty * kurs
        store.equity_punkt(bot.bot_id, tag.date(), equity, cash, len(positionen))

        # ---------- 4. Entscheiden fuer morgen ----------
        aktive = {s: df.loc[:tag] for s, df in per_symbol.items()
                  if tag in df.index and len(df.loc[:tag]) >= 260}
        if not aktive:
            continue
        tages_snap = MarketSnapshot(
            as_of=tag, bars=aktive,
            market=snap.market.loc[:tag] if snap.market is not None else None,
            signals={s: signale[s].loc[:tag] for s in aktive if s in signale},
        )
        pf = PortfolioState(cash=cash, equity=equity, positions=dict(positionen))
        neue = engine.decide(tages_snap, pf)
        verkaeufe = [d for d in neue if d.action == "sell"]
        kaeufe = [d for d in neue if d.action == "buy"][:cfg.max_new_positions]
        # Nachkaeufe zaehlen NICHT gegen max_new_positions - sie eroeffnen
        # keine neue These, sondern verstaerken eine bestehende. Jede bleibt
        # einzeln durch max_position_pct gedeckelt.
        nachkaeufe = [d for d in neue if d.action == "topup"]
        store.pending_setzen(bot.bot_id, [*verkaeufe, *kaeufe, *nachkaeufe],
                             as_of=tag)

        store.depot_cash(bot.bot_id, cash, equity, letzter_tag=tag.isoformat())

    if verbose:
        extra = (f", {stat['nachkaeufe']} Nachkauf/-kaeufe"
                 if stat.get("nachkaeufe") else "")
        print(f"      {bot.bot_id:<18} Spiegel: {stat['tage']} Tag(e), "
              f"{stat['kaeufe']} Kauf/Kaeufe, {stat['verkaeufe']} Verkauf/Verkaeufe"
              f"{extra}, {len(positionen)} Positionen")
    return stat

def entscheiden(cfg: ShadowConfig, store: ShadowStore | None = None,
                *, verbose: bool = True) -> int:
    """Ein Entscheidungslauf fuer die ganze Flotte, beide Buecher.

    Die teure Arbeit - Kursdaten laden und Signale rechnen - passiert EINMAL
    und wird von allen Bots geteilt. Zusaetzlicher Nutzen: Alle Bots sehen
    garantiert dieselben Kurse an denselben Tagen, die Voraussetzung fuer den
    gepaarten Vergleich (Plan §6.2).
    """
    from . import fleet

    store = store or ShadowStore()
    symbols = _universum_symbole(cfg)

    bots = fleet.aktive_bots(store)
    if not bots:
        raise RuntimeError(
            "Keine Bots angemeldet. Zuerst die Startaufstellung anlegen:\n"
            "  python scripts/21_fleet.py --startaufstellung"
        )

    run_id = store.start_run("entscheiden", n_symbols=len(symbols),
                             universum=cfg.universe, engine=cfg.engine.as_dict())
    try:
        bars = lade_bars(symbols, cfg.years, verbose=verbose)
        if bars.empty:
            raise RuntimeError("Keine Kursdaten erhalten.")
        snap, extra = baue_snapshot(bars, verbose=verbose)

        # --- Kalenderpruefung (Plan §14.2) ---
        heute = pd.Timestamp.now(tz="UTC").normalize()
        if snap.as_of > heute:
            raise RuntimeError(f"Stichtag {snap.as_of.date()} liegt in der Zukunft.")

        regime = _regime(extra["markt"], snap.bars, snap.as_of)
        cv = code_version()
        if verbose:
            print(f"      Regime: {regime['regime_markt']}, "
                  f"Vola {regime['regime_vola']}, Breite {regime['regime_breite']}")

        # --- Signale je EINDEUTIGER Signalkonfiguration, nicht je Bot ---
        # snap.news geht an JEDEN Durchlauf - der Score-Faktor
        # (ReversalWeights.news) ist seit 03.08.2026 immer aktiv, fuer alle
        # Bots gleich, kein Flag mehr.
        cache: dict[str, dict] = {}
        for b in bots:
            k = b.signal_schluessel()
            if k not in cache:
                cache[k] = _signalrahmen(snap.bars, extra["markt"], b.config,
                                         news=snap.news)
        if verbose:
            print(f"      {len(cache)} Signaldurchlauf/-laeufe fuer {len(bots)} Bots")

        # Zusaetzlicher Tonalitaets-/Ereignis-Kontext (reine Metadaten, siehe
        # _news_kontext) fuer die besten Kandidaten des Basis-Bots - dessen
        # Rangliste beruecksichtigt den Score-Faktor jetzt bereits mit.
        basis_signale = cache[bots[0].signal_schluessel()]
        kand = sorted(
            ((float(f.iloc[-1].get("score", 0) or 0), s)
             for s, f in basis_signale.items() if len(f)),
            reverse=True,
        )[: cfg.news_max_symbole]
        news_ctx = _news_kontext([s for _, s in kand], snap.as_of,
                                 verbose=verbose)

        gesamt = 0
        for b in bots:
            signale = cache[b.signal_schluessel()]
            bot_snap = MarketSnapshot(
                as_of=snap.as_of, bars=snap.bars, market=snap.market,
                signals={s: f.loc[:snap.as_of] for s, f in signale.items()},
            )

            schon_da = store.table(
                "predictions",
                "as_of = ? AND bot_id = ? AND buch = 'rangliste'",
                (snap.as_of.isoformat(), b.bot_id),
            )
            if schon_da.empty:
                n = _rangliste(b, bot_snap, store, run_id, regime, cv,
                               max_new=cfg.max_new_positions, news=news_ctx)
                gesamt += n
                if verbose:
                    print(f"      {b.bot_id:<18} Rangliste: {n} Kandidaten")
            elif verbose:
                print(f"      {b.bot_id:<18} Rangliste: bereits erfasst")

            _spiegel(b, bot_snap, snap.bars, signale, store, run_id, regime, cv,
                     cfg, verbose=verbose)

        store.finish_run(run_id, "ok")
        return gesamt
    except Exception as e:  # noqa: BLE001
        store.finish_run(run_id, "fehler", f"{type(e).__name__}: {e}")
        raise

# ---------------------------------------------------------------------------
# Schritt 2: Einbuchen
# ---------------------------------------------------------------------------
def einbuchen(cfg: ShadowConfig, store: ShadowStore | None = None,
              *, verbose: bool = True) -> int:
    """Traegt den tatsaechlichen Einstiegskurs nach.

    Entschieden wird auf dem Schlusskurs von Tag T, eingebucht zur Eroeffnung
    von T+1. Wer die Rendite ab dem Schlusskurs von T rechnet, auf dem die
    Entscheidung beruhte, hat ein Datenleck und misst einen Vorsprung, den es
    nicht gibt.
    """
    store = store or ShadowStore()
    offen = store.offene_einbuchungen()
    if offen.empty:
        if verbose:
            print("      nichts einzubuchen")
        return 0

    # STABILES Universum laden statt der schrumpfenden Teilmenge der offenen
    # Vorhersagen - sonst trifft der Tages-Cache nie und es wird bei jedem
    # stuendlichen Durchlauf neu von yfinance geladen (siehe
    # `_universum_symbole`). Alle benoetigten Symbole sind darin enthalten,
    # weil jeder Kandidat aus genau diesem Universum stammt.
    symbols = _universum_symbole(cfg)
    run_id = store.start_run("einbuchen", n_symbols=len(symbols))
    try:
        bars = lade_bars(symbols, cfg.years, verbose=verbose)
        n = 0
        for _, p in offen.iterrows():
            try:
                df = bars.xs(p["symbol"], level="symbol").sort_index()
            except KeyError:
                continue
            as_of = pd.Timestamp(p["as_of"])
            if as_of.tz is None:
                as_of = as_of.tz_localize("UTC")

            idx = pd.DatetimeIndex(df.index)
            if idx.tz is None:
                idx = idx.tz_localize("UTC")
            spaeter = idx[idx > as_of]
            if len(spaeter) == 0:
                continue                      # naechster Handelstag noch nicht da
            entry_date = spaeter[0]
            bar = df.loc[df.index[idx.get_loc(entry_date)]]

            p_open = float(bar["open"])
            if not np.isfinite(p_open) or p_open <= 0:
                continue

            # Kosten wie in der Simulation - ohne sie waere der Schatten
            # systematisch besser als jeder echte Trade.
            qty = max(1, int((p["notional"] or p_open) / p_open))
            k = estimate_costs("buy", qty, last=p_open,
                               spread_bps=cfg.spread_bps,
                               slippage_bps=cfg.slippage_bps, fees=DEFAULT_FEES)

            store.save_fill(
                p["pred_id"],
                entry_date=entry_date.isoformat(),
                entry_price_open=p_open,
                entry_price=p_open,
                entry_price_eff=float(k.effective_price),
                # Phase 1 bucht zur Eroeffnung. Der Live-Bot handelt ~20 Min
                # spaeter; §0.1 hat diese Differenz mit -0,58 bps (t=-0,18)
                # als unerheblich gemessen. Phase 2 (Spiegelbuch) verfeinert.
                entry_timing="open",
            )
            n += 1
        store.finish_run(run_id, "ok")
        if verbose:
            print(f"      {n} Vorhersage(n) eingebucht")
        return n
    except Exception as e:  # noqa: BLE001
        store.finish_run(run_id, "fehler", f"{type(e).__name__}: {e}")
        raise

# ---------------------------------------------------------------------------
# Schritt 3: Verifizieren
# ---------------------------------------------------------------------------
def lernen(cfg: ShadowConfig, store: ShadowStore | None = None,
           *, verbose: bool = True) -> int:
    """Der Lernschritt: Muster pruefen, Kandidaten suchen, Zerfall melden.

    **Warum das ein eigener Schritt im Dauerbetrieb ist.** Der
    Musterspeicher (`patterns.py`) war vollstaendig gebaut - mit
    Verfallspruefung auf ausschliesslich NEUEN Daten, Mindestzahl an
    Handelstagen und Zerfallsmeldung. Er wurde nur nie aufgerufen: Am
    22.08.2026 enthielt die Tabelle `muster` **null Zeilen**. Der Daemon
    kannte nur einbuchen/verifizieren/entscheiden.

    Das ist der Unterschied zwischen "das System koennte lernen" und "das
    System lernt".

    **Warum er nur bei neuen Daten laeuft.** Zweimal am selben Tag
    gerechnet liefert er bitgleich dasselbe - er wuerde nur Rechenzeit und
    Protokollzeilen erzeugen. Gesteuert ueber denselben Gedanken wie der
    Aktualitaetsfilter in `verifizieren`: Ohne neuen Handelstag gibt es
    nichts Neues zu lernen.

    **Was er ausdruecklich NICHT tut:** Er aendert keine Handelsregel. Ein
    bestaetigtes Muster ist eine Beobachtung mit Beleg und Verfallsdatum,
    kein Signal. Der Weg von dort in die Handelslogik fuehrt weiterhin
    ueber eine Voranmeldung in der Flotte (CLAUDE.md).
    """
    from . import patterns

    store = store or ShadowStore()
    letzter = store.letzter_lerntag()
    with store._conn() as c:
        row = c.execute("SELECT MAX(as_of) FROM predictions").fetchone()
    neuester = (row[0] or "")[:10]
    if not neuester:
        return 0
    if letzter == neuester:
        if verbose:
            print(f"      kein neuer Handelstag seit {letzter} - nichts zu lernen")
        return 0

    run_id = store.start_run("lernen")
    try:
        gepruefte = patterns.pruefen(store, verbose=verbose)
        kandidaten = patterns.kandidaten_suchen(store, anlegen=True, verbose=verbose)
        store.setze_lerntag(neuester)
        n = len(gepruefte) + len(kandidaten)
        if verbose:
            zerfallen = (gepruefte["status"] == "zerfallen").sum() if not gepruefte.empty else 0
            print(f"      {len(gepruefte)} Muster geprueft, {zerfallen} zerfallen, "
                  f"{len(kandidaten)} Kandidatenschnitte")
        store.finish_run(run_id, "ok")
        return int(n)
    except Exception as e:  # noqa: BLE001
        store.finish_run(run_id, "fehler", f"{type(e).__name__}: {e}")
        raise

def verifizieren(cfg: ShadowConfig, store: ShadowStore | None = None,
                 *, verbose: bool = True) -> int:
    """Was ist tatsaechlich daraus geworden?

    Berechnet drei Dinge getrennt:

      1. Horizontrenditen (1/3/5/10/20 Tage) - UNABHAENGIG von Stop und Ziel.
         Grundlage jeder kontrafaktischen Rechnung (Plan §7.2).
      2. Den Ausstieg nach den geplanten Regeln (Stop/Ziel/Zeit) inkl. Kosten.
      3. Die Referenzen: SPY und Universums-Median ueber denselben Zeitraum.
         Ohne sie ist die Rendite bedeutungslos - ein Schattenbuch mit +3 % in
         einer Woche, in der das Universum +4 % machte, ist ein Verlust.
    """
    store = store or ShadowStore()
    offen = store.offene_ergebnisse()
    if offen.empty:
        if verbose:
            print("      nichts zu verifizieren")
        return 0

    # STABILES Universum statt der schrumpfenden Teilmenge - siehe Begruendung
    # in `einbuchen()` und `_universum_symbole()`.
    symbols = _universum_symbole(cfg)
    run_id = store.start_run("verifizieren", n_symbols=len(symbols))
    try:
        bars = lade_bars(symbols, cfg.years, verbose=verbose)
        try:
            spy = bars.xs(MARKET_SYMBOL, level="symbol").sort_index()["close"].astype(float)
        except KeyError:
            spy = None

        # --- Nur rechnen, was sich seit der letzten Auswertung aendern KONNTE ---
        #
        # Eine Vorhersage bleibt offen, bis `fwd_20d` gefuellt ist - also
        # 20 Handelstage lang. Der Dauerbetrieb lief bis zum 22.08.2026
        # stuendlich ueber ALLE offenen Vorhersagen: gemessen 19.788 Stueck,
        # rund 24-mal am Tag, also ~475.000 Auswertungen taeglich fuer
        # NULL neue Information. Ein Ergebnis kann sich nur aendern, wenn
        # eine neue Tagesbar dazugekommen ist; innerhalb eines Handelstages
        # ist jede Wiederholung bitgleich.
        #
        # Verglichen wird gegen den juengsten geladenen Bar, nicht gegen die
        # Uhrzeit: Am Wochenende und an Feiertagen kommt keine Bar dazu, und
        # eine kalendarische Regel wuerde dort weiter sinnlos rechnen.
        offen_gesamt = len(offen)
        try:
            neuester_bar = pd.DatetimeIndex(
                bars.index.get_level_values("timestamp")).max()
            if neuester_bar.tzinfo is None:
                neuester_bar = neuester_bar.tz_localize("UTC")
            bewertet = pd.to_datetime(offen.get("evaluated_at"), format="mixed",
                                      utc=True, errors="coerce")
            # `>=` waere falsch: eine Auswertung GENAU zum Bar-Zeitstempel
            # hat diesen Bar noch nicht gesehen.
            aktuell = bewertet.notna() & (bewertet > neuester_bar)
            offen = offen[~aktuell]
        except Exception as e:  # noqa: BLE001 - im Zweifel lieber alles rechnen
            if verbose:
                print(f"      Aktualitaetsfilter uebersprungen ({type(e).__name__})")

        if verbose and offen_gesamt:
            print(f"      {len(offen):,} von {offen_gesamt:,} offenen Vorhersagen "
                  f"koennen sich geaendert haben")
        if offen.empty:
            store.finish_run(run_id, "ok")
            return 0

        # Universums-Median je Stichtag: die Referenz, gegen die der
        # Ueberschuss gerechnet wird (Plan §3.1).
        uni_median: dict[str, float] = {}
        jetzt = dt.datetime.now(dt.UTC).isoformat()
        n = 0

        for _, p in offen.iterrows():
            try:
                df = bars.xs(p["symbol"], level="symbol").sort_index()
            except KeyError:
                continue
            idx = pd.DatetimeIndex(df.index)
            if idx.tz is None:
                idx = idx.tz_localize("UTC")
            df = df.copy()
            df.index = idx

            entry_date = pd.Timestamp(p["entry_date"])
            if entry_date.tz is None:
                entry_date = entry_date.tz_localize("UTC")
            if entry_date not in df.index:
                continue
            pos = int(df.index.get_loc(entry_date))
            close = df["close"].astype(float)
            entry = float(p["entry_price"])
            if entry <= 0:
                continue

            # --- Datenpruefung: wurde der Kurs rueckwirkend angepasst? ---
            # yfinance laedt mit auto_adjust=True; nach Dividende oder Split
            # aendern sich HISTORISCHE Kurse. Der gespeicherte Wert wird
            # deshalb NIE ueberschrieben, die Abweichung nur vermerkt.
            check = "ok"
            neu_open = float(df["open"].iloc[pos])
            if p["entry_price_open"] and abs(neu_open / float(p["entry_price_open"]) - 1) > 0.005:
                check = "kurs_angepasst"

            # --- 1. Horizontrenditen, unabhaengig von Stop/Ziel ---
            fwd = {}
            for h in HORIZONTE:
                fwd[f"fwd_{h}d"] = (
                    round(float(close.iloc[pos + h] / entry - 1), 5)
                    if pos + h < len(close) else None
                )

            # --- 2. Ausstieg nach den geplanten Regeln ---
            stop = float(p["planned_stop"] or 0)
            ziel = float(p["planned_target"] or 0)
            halte = int(p["planned_hold_days"] or 5)
            exit_date = exit_price = None
            grund = None
            ziel_erreicht = stop_erreicht = 0
            mae = mfe = None

            fenster = df.iloc[pos: pos + halte + 1]
            if len(fenster) > 1:
                lows = fenster["low"].astype(float)
                highs = fenster["high"].astype(float)
                mae = round(float(lows.min() / entry - 1), 5)
                mfe = round(float(highs.max() / entry - 1), 5)

                for j in range(1, len(fenster)):
                    tag = fenster.iloc[j]
                    lo, hi = float(tag["low"]), float(tag["high"])
                    if stop > 0 and lo <= stop:
                        # Kursluecke: nicht besser als die Eroeffnung
                        exit_price = min(stop, float(tag["open"]))
                        grund, stop_erreicht = "stop_ausgeloest", 1
                    elif ziel > 0 and hi >= ziel:
                        exit_price = max(ziel, float(tag["open"]))
                        grund, ziel_erreicht = "gewinnziel_erreicht", 1
                    if grund:
                        exit_date = fenster.index[j]
                        break
                if grund is None and len(fenster) > halte:
                    exit_date = fenster.index[-1]
                    exit_price = float(fenster["close"].iloc[-1])
                    grund = "zeitausstieg"

            row = {"pred_id": p["pred_id"], "evaluated_at": jetzt,
                   "data_check": check, "mae_pct": mae, "mfe_pct": mfe,
                   "ziel_erreicht": ziel_erreicht, "stop_erreicht": stop_erreicht,
                   **fwd}

            if exit_price and exit_date is not None:
                qty = max(1, int((p["notional"] or entry) / entry))
                k = estimate_costs("sell", qty, last=exit_price,
                                   spread_bps=cfg.spread_bps,
                                   slippage_bps=cfg.slippage_bps, fees=DEFAULT_FEES)
                eff_in = float(p["entry_price_eff"] or entry)
                eff_out = float(k.effective_price)
                row.update({
                    "exit_date": exit_date.isoformat(),
                    "exit_price": exit_price,
                    "exit_price_eff": eff_out,
                    "exit_reason": grund,
                    "return_brutto": round(exit_price / entry - 1, 5),
                    "return_pct": round(eff_out / eff_in - 1, 5),
                    "kosten": round(abs(eff_out - exit_price) + abs(eff_in - entry), 4),
                    "bars_held": int(df.index.get_loc(exit_date) - pos),
                })

            # --- 3. Referenzen ---
            if spy is not None and fwd.get("fwd_5d") is not None:
                s_idx = pd.DatetimeIndex(spy.index)
                if s_idx.tz is None:
                    s_idx = s_idx.tz_localize("UTC")
                sp = spy.copy()
                sp.index = s_idx
                if entry_date in sp.index:
                    sp_pos = int(sp.index.get_loc(entry_date))
                    if sp_pos + 5 < len(sp):
                        row["bench_fwd_5d"] = round(
                            float(sp.iloc[sp_pos + 5] / sp.iloc[sp_pos] - 1), 5)

            store.save_outcome(row)
            n += 1

        # --- Universums-Median und Ueberschuss nachtragen ---
        _trage_ueberschuss_nach(store)

        store.finish_run(run_id, "ok")
        if verbose:
            print(f"      {n} Ergebnis(se) bewertet")
        return n
    except Exception as e:  # noqa: BLE001
        store.finish_run(run_id, "fehler", f"{type(e).__name__}: {e}")
        raise

def _trage_ueberschuss_nach(store: ShadowStore) -> None:
    """Ueberschuss = eigene Rendite minus Median des Universums am selben Tag.

    Muss NACH allen Einzelergebnissen laufen, weil der Median erst feststeht,
    wenn alle Vorhersagen eines Stichtags bewertet sind.
    """
    with store._conn() as c:
        df = pd.read_sql_query(
            "SELECT o.pred_id, o.fwd_5d, p.as_of FROM shadow_outcomes o"
            " JOIN predictions p ON o.pred_id = p.pred_id"
            " WHERE o.fwd_5d IS NOT NULL",
            c,
        )
        if df.empty:
            return
        med = df.groupby("as_of")["fwd_5d"].median()
        for _, r in df.iterrows():
            m = float(med.loc[r["as_of"]])
            c.execute(
                "UPDATE shadow_outcomes SET universum_fwd_5d=?, ueberschuss_5d=?"
                " WHERE pred_id=?",
                (round(m, 5), round(float(r["fwd_5d"]) - m, 5), r["pred_id"]),
            )
