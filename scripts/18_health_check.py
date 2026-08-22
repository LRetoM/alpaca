#!/usr/bin/env python3
"""Schritt 18: Health-Check - eine Ampel, verstaendlich ohne Vorwissen.

Fuer unterwegs gedacht: Ein Blick, drei moegliche Antworten.

    GRUEN  - alles laeuft wie geplant, nichts zu tun
    GELB   - laeuft, aber etwas ist auffaellig - lesen, meist kein Handeln noetig
    ROT    - etwas ist wirklich kaputt - naechstes Mal am Rechner nachsehen

Prueft in einem Durchgang:
  1. Laufen beide Dienste ueberhaupt (launchd-Registrierung)?
  2. Wann war der letzte erfolgreiche Durchgang - zu lange her?
  3. Datenintegritaet (siehe data_integrity.py)
  4. Deckt sich das Depot mit dem gespeicherten Zustand?

    python scripts/18_health_check.py
"""

from __future__ import annotations

import subprocess
import sys

import pandas as pd


def main() -> int:
    print("=" * 60)
    print("  HEALTH-CHECK")
    print("=" * 60)

    ampel = "GRUEN"
    gruende: list[str] = []

    # --- 1. Dienste registriert? ---
    try:
        out = subprocess.run(["launchctl", "list"], capture_output=True, text=True,
                             timeout=10).stdout
    except Exception as e:  # noqa: BLE001
        out = ""
        gruende.append(f"launchctl nicht abrufbar: {e}")
        ampel = "ROT"

    handel_laeuft = "de.local.alpacabot" in out
    schatten_laeuft = "de.local.alpacaschatten" in out
    print(f"  Handelsbot registriert : {'ja' if handel_laeuft else 'NEIN'}")
    print(f"  Schattenbot registriert: {'ja' if schatten_laeuft else 'NEIN'}")
    if not handel_laeuft:
        ampel = "ROT"
        gruende.append("Handelsbot ist NICHT als Dienst registriert - er laeuft nicht.")
    if not schatten_laeuft:
        ampel = "ROT" if ampel != "ROT" else ampel
        gruende.append("Schattenbot ist NICHT als Dienst registriert.")

    # --- 2. Letzter erfolgreicher Durchgang ---
    try:
        from alpaca_bot.state import Store

        status = Store().status()
        if status:
            last_ok = pd.Timestamp(status.get("last_ok") or status.get("last_run"))
            if last_ok.tz is None:
                last_ok = last_ok.tz_localize("UTC")
            alter_min = (pd.Timestamp.now(tz="UTC") - last_ok).total_seconds() / 60
            print(f"  Letzter Handelsbot-Erfolg vor: {alter_min:.0f} Minuten")
            if alter_min > 120:  # ueber 2h ohne Erfolg - kann Boersenschluss sein
                if ampel == "GRUEN":
                    ampel = "GELB"
                gruende.append(
                    f"Handelsbot zuletzt vor {alter_min:.0f} Minuten erfolgreich - "
                    "pruefen ob das durch Boersenschluss erklaerbar ist."
                )
            fehler = status.get("errors_total", 0)
            print(f"  Fehler gesamt (Handelsbot): {fehler}")
        else:
            print("  Kein Handelsbot-Status gefunden.")
            ampel = "ROT"
            gruende.append("Noch nie ein erfolgreicher Handelsbot-Durchgang protokolliert.")
    except Exception as e:  # noqa: BLE001
        gruende.append(f"Status nicht abrufbar: {type(e).__name__}: {e}")
        ampel = "ROT"

    # --- 2b. Risiko-Dach ---
    # Steht bewusst VOR der Datenintegritaet: Eine aktive Sperre ist die
    # wichtigste Einzelinformation ueberhaupt - sie bedeutet, dass der Bot
    # gerade NICHT handelt. Wer sie uebersieht, wundert sich tagelang ueber
    # ausbleibende Trades.
    try:
        from alpaca_bot import risiko
        from alpaca_bot.state import Store as _S

        sperre = _S().sperre_lesen()
        if int(sperre.get("aktiv") or 0) == 1:
            ampel = "ROT"
            gruende.append(f"RISIKO-SPERRE AKTIV: {sperre.get('grund')}")
            print(f"  Risiko-Dach     : SPERRE AKTIV")
        else:
            v = _S().kapital_verlauf(tage=90)
            if v.empty:
                print("  Risiko-Dach     : frei (noch keine Messpunkte)")
            else:
                a = v.iloc[-1]
                g = risiko.Risikogrenzen()
                print(f"  Risiko-Dach     : frei | Drawdown "
                      f"{a['drawdown_pct']:.1%} (Grenze {g.max_drawdown_pct:.0%}) "
                      f"| Exposure {a['exposure']:.0%}")
                if a["drawdown_pct"] > g.max_drawdown_pct * 0.75:
                    ampel = "GELB" if ampel == "GRUEN" else ampel
                    gruende.append(
                        f"Drawdown {a['drawdown_pct']:.1%} naehert sich der "
                        f"Grenze {g.max_drawdown_pct:.0%}.")
    except Exception as e:  # noqa: BLE001
        gruende.append(f"Risiko-Dach nicht pruefbar: {type(e).__name__}: {e}")
        ampel = "ROT"

    # --- 3. Datenintegritaet ---
    try:
        from alpaca_bot import data_integrity

        r = data_integrity.run_all()
        print(f"  Datenintegritaet: {r.ampel()}")
        if not r.ok:
            ampel = "ROT"
            for f in r.errors:
                gruende.append(f"Datenfehler: {f.check} - {f.detail[:100]}")
    except Exception as e:  # noqa: BLE001
        gruende.append(f"Datenintegritaet nicht pruefbar: {type(e).__name__}: {e}")
        ampel = "ROT"

    # --- 3b. Nutzungsnachweis ---
    # Bewusst GELB und nicht ROT: Ein stillstehender Baustein ist kein
    # Datenverlust und kein Handelsfehler - er kostet nur Zeit, in der wir
    # nichts lernen. Das rechtfertigt eine Warnung, keinen Stopp. Er gehoert
    # aber hierher, weil genau das dreimal wochenlang unbemerkt blieb (§G15).
    try:
        from alpaca_bot import nutzung

        befunde = nutzung.pruefen()
        schlecht = [b for b in befunde if not b.ok]
        print(f"  Bausteine       : {len(befunde) - len(schlecht)}/{len(befunde)} "
              f"arbeiten wie geplant")
        if schlecht:
            ampel = "GELB" if ampel == "GRUEN" else ampel
            for b in schlecht:
                gruende.append(f"Baustein '{b.baustein}': "
                               f"{b.detail.splitlines()[0]}")
    except Exception as e:  # noqa: BLE001 - der Nachweis darf nie blockieren
        print(f"  Bausteine       : nicht pruefbar ({type(e).__name__})")

    # --- 4. Depot vs. Zustand ---
    try:
        from alpaca_bot import account
        from alpaca_bot.state import Store

        broker = set(account.positions().index)
        stored = set(Store().load_positions())
        print(f"  Positionen: {len(broker)} im Depot, {len(stored)} mit Zustand")
        if broker - stored:
            ampel = "ROT"
            gruende.append(
                f"Positionen ohne Zustand: {', '.join(sorted(broker - stored))}"
            )
        acct = account.account_summary()
        print(f"  Kapital: ${acct['portfolio_value']:,.2f}")
    except Exception as e:  # noqa: BLE001
        gruende.append(f"Depot nicht abrufbar: {type(e).__name__}: {e}")
        ampel = "ROT"

    # --- Ergebnis ---
    print()
    print("=" * 60)
    symbol = {"GRUEN": "🟢", "GELB": "🟡", "ROT": "🔴"}.get(ampel, "")
    print(f"  {symbol}  {ampel}")
    print("=" * 60)
    if gruende:
        print()
        for g in gruende:
            print(f"  - {g}")
    else:
        print("  Alles laeuft wie geplant. Nichts zu tun.")

    return 0 if ampel != "ROT" else 1


if __name__ == "__main__":
    sys.exit(main())
