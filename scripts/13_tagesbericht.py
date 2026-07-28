#!/usr/bin/env python3
"""Schritt 13: Tagesbericht - was hat der Bot getan und hat es funktioniert?

Beantwortet in einem Durchgang die Fragen, die nach einem Handelstag
zaehlen:

  1. Lief der Bot ueberhaupt durch? (Laeufe, Fehler, Luecken)
  2. Was hat er gekauft und verkauft, und warum?
  3. Wie gut war die Ausfuehrung - stimmen die Backtest-Annahmen?
  4. Welche Begruendung hat sich bewaehrt?
  5. Stimmen Bot-Zustand und Broker-Depot ueberein?

    python scripts/13_tagesbericht.py
    python scripts/13_tagesbericht.py --tage 5
"""

from __future__ import annotations

import argparse
import sys

import pandas as pd

from alpaca_bot import account, costs, data, live
from alpaca_bot.journal import Journal, make_price_lookup
from alpaca_bot.state import Store


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--tage", type=int, default=1)
    p.add_argument("--erwartete-slippage", type=float, default=8.0,
                   help="Im Backtest angenommene Slippage in Basispunkten")
    args = p.parse_args()

    j = Journal()
    store = Store()
    since = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=args.tage)

    print("=" * 74)
    print(f"  TAGESBERICHT  |  letzte {args.tage} Tag(e)")
    print("=" * 74)

    # --- 1. Lief der Bot? ---
    print("\n[1] BETRIEB")
    status = store.status()
    if not status:
        print("    Kein Lauf protokolliert - der Bot lief noch nicht.")
        return 0
    print(f"    Letzter Lauf   : {status.get('last_run', '-')}")
    print(f"    Letzter Erfolg : {status.get('last_ok', '-')}")
    print(f"    Laeufe gesamt  : {status.get('runs_total', 0)}")
    print(f"    Fehler gesamt  : {status.get('errors_total', 0)}")
    if status.get("last_error"):
        print(f"    Letzter Fehler : {str(status['last_error'])[:150]}")

    runs = j.table("runs", "script = 'live_trade'")
    if not runs.empty:
        runs["started_at"] = pd.to_datetime(runs["started_at"], utc=True)
        recent = runs[runs["started_at"] >= since]
        failed = int((recent["status"] == "failed").sum())
        print(f"    Handelslaeufe im Zeitraum: {len(recent)}"
              + (f"  ({failed} fehlgeschlagen)" if failed else ""))
        if len(recent) > 1:
            gaps = recent["started_at"].sort_values().diff().dropna()
            if not gaps.empty:
                print(f"    Groesste Luecke zwischen Laeufen: "
                      f"{gaps.max().total_seconds() / 60:.0f} Minuten")

    # --- 2. Was wurde gehandelt? ---
    print("\n[2] ENTSCHEIDUNGEN UND ORDERS")
    orders = j.table("orders", "dry_run = 0")
    if not orders.empty:
        orders["ts"] = pd.to_datetime(orders["ts"], utc=True)
        orders = orders[orders["ts"] >= since]

    if orders.empty:
        print("    Keine echten Orders im Zeitraum.")
    else:
        cols = ["ts", "symbol", "side", "notional", "expected_price",
                "fill_price", "slippage_bps", "status"]
        show = orders[[c for c in cols if c in orders.columns]].copy()
        show["ts"] = show["ts"].dt.strftime("%d.%m %H:%M")
        print(show.to_string(index=False))

        offen = int(orders["fill_price"].isna().sum())
        if offen:
            print(f"\n    {offen} Order(s) ohne Ausfuehrungspreis - noch nicht "
                  "abgeglichen oder nicht ausgefuehrt.")

    # --- 3. Ausfuehrungsqualitaet ---
    print("\n[3] AUSFUEHRUNG: ANNAHME GEGEN REALITAET")
    try:
        n = live.reconcile_fills()
        if n:
            print(f"    {n} Ausfuehrungspreis(e) frisch nachgetragen.")
    except Exception as e:  # noqa: BLE001
        print(f"    Abgleich nicht moeglich: {type(e).__name__}")

    slip = j.slippage_report()
    if slip.empty:
        print("    Noch keine ausgefuehrten Orders mit Preisvergleich.")
        print("    Diese Auswertung entscheidet spaeter, ob die Backtests")
        print("    ueberhaupt realistisch waren - sie ist die wichtigste hier.")
    else:
        print(slip.to_string())
        print()
        print(costs.reconcile(args.erwartete_slippage, slip))

    # --- 4. Entscheidungsqualitaet ---
    print("\n[4] WELCHE BEGRUENDUNG HAT SICH BEWAEHRT?")
    dec = j.table("decisions")
    if not dec.empty:
        symbols = sorted(dec["symbol"].dropna().unique())[:200]
        try:
            bars = data.get_bars(symbols, "1D", lookback_days=120)
            added = j.evaluate_outcomes(make_price_lookup(bars), horizons=(1, 3, 5))
            if added:
                print(f"    {added} Ergebnis(se) nachgetragen.")
        except Exception as e:  # noqa: BLE001
            print(f"    Kursabruf fehlgeschlagen: {type(e).__name__}")

    # Nur der Live-Betrieb - Simulationsdaten wuerden das Bild verfaelschen.
    q = j.decision_quality(3, script="live_trade")
    if q.empty:
        print("    Noch keine bewerteten Ergebnisse. Aussagekraeftig wird das")
        print("    erst nach einigen Tagen - ein 3-Tage-Horizont braucht")
        print("    3 Tage, bevor er ueberhaupt messbar ist.")
    else:
        print(q.to_string())
        print("\n    'mittel' = durchschnittliche Rendite 3 Tage nach der Entscheidung.")

    # --- 5. Stimmt der Zustand? ---
    print("\n[5] ABGLEICH BOT-ZUSTAND GEGEN BROKER")
    try:
        broker = account.positions()
        stored = store.load_positions()
        broker_syms, stored_syms = set(broker.index), set(stored)

        print(f"    Broker : {len(broker_syms)} Positionen")
        print(f"    Bot    : {len(stored_syms)} gespeicherte Zustaende")

        if broker_syms - stored_syms:
            print(f"    OHNE ZUSTAND: {', '.join(sorted(broker_syms - stored_syms))}")
            print("      -> Der Bot kennt Stop und Ziel dieser Positionen nicht.")
        if stored_syms - broker_syms:
            print(f"    VERWAIST    : {', '.join(sorted(stored_syms - broker_syms))}")
            print("      -> Zustand zu Positionen, die es nicht mehr gibt.")
        if broker_syms == stored_syms:
            print("    Deckungsgleich.")

        if not broker.empty:
            print()
            rows = []
            for sym, row in broker.iterrows():
                m = stored.get(sym, {})
                cur = float(row.get("current_price") or 0)
                rows.append({
                    "Symbol": sym,
                    "Stueck": round(float(row["qty"]), 3),
                    "Einstieg": round(float(row["avg_entry"]), 2),
                    "Aktuell": round(cur, 2),
                    "G/V %": row.get("unrealized_plpc"),
                    "Stop": round(float(m["stop_price"]), 2) if m else None,
                    "Ziel": round(float(m["target_price"]), 2) if m else None,
                    "Tage": m.get("bars_held") if m else None,
                })
            print(pd.DataFrame(rows).to_string(index=False))

        acct = account.account_summary()
        print(f"\n    Kapital ${acct['portfolio_value']:,.2f} | "
              f"Cash ${acct['cash']:,.2f} | "
              f"Tagesveraenderung "
              f"{(acct['equity'] / acct['last_equity'] - 1) * 100:+.2f}%")
    except Exception as e:  # noqa: BLE001
        print(f"    Kontoabruf fehlgeschlagen: {type(e).__name__}: {e}")

    # --- 6. Lief er nach Plan? ---
    print()
    from alpaca_bot import audit

    print(audit.run_audit(days=args.tage))

    # --- Fazit ---
    print("\n" + "=" * 74)
    problems = j.integrity_check()
    if problems:
        print("  BEFUNDE:")
        for p_ in problems:
            print(f"    - {p_}")
    else:
        print("  Protokoll vollstaendig, keine Luecken.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
