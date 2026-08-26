#!/usr/bin/env python3
"""Schritt 37: Wie weit ist die Geld-Brief-Spanne in UNSEREM Universum wirklich?

**Die Frage (BEFUNDE §G39).** Das gesamte Kostenmodell des Projekts
rechnet mit 5 bps Spread. Woher die Zahl kommt, steht als Kommentar im
eigenen Quelltext:

    costs.py:151   # 5 bps ist fuer Large Caps typisch,
                   # bei Nebenwerten sind 30-100 bps normal.

Der Bot handelt aber ausdruecklich NICHT die Large Caps -
`universe.py:87` haelt fest, dass der Effekt bei den 150 liquidesten
Werten nicht nachweisbar war. Damit haengt der zentrale Konflikt des
Projekts (Vorsprung +0,110 % gegen Breakeven 0,1423 %) an einer Zahl aus
einem anderen Marktsegment.

Dieses Skript ersetzt die Annahme durch eine Verteilung.

**Was gemessen wird.** Die relative Spanne je Symbol:

    spanne_bps = (ask - bid) / mid * 10_000

Und - das ist der eigentliche Punkt - **aufgeschluesselt nach
Liquiditaetsdezil**, denn nur die Dezile, in denen der Bot tatsaechlich
kauft, gehen ihn etwas an. Laut Journal sind das ueberwiegend 3 und 4.

**Der Vorbehalt, der im Ergebnis mitgedruckt wird.** Der kostenlose
Alpaca-Feed ist IEX, und IEX sieht ~2 % des US-Volumens (§G29). Die so
gemessene Spanne ist deshalb eine **OBERGRENZE**, keine Punktschaetzung -
an der konsolidierten NBBO ist die echte Spanne enger. Fuer die Frage,
die ansteht, ist eine Obergrenze aber die richtige Groesse: Traegt der
Vorsprung selbst im unguenstigen Fall, ist die Sache entschieden.

**Nur bei offener Boerse.** Ausserhalb der Handelszeit stellt kaum
jemand Quotes; die Spannen sind dann um ein Vielfaches weiter und die
Messung ist wertlos. Das Skript verweigert deshalb den Dienst bei
geschlossener Boerse, statt eine unbrauchbare Zahl zu drucken.

**Eine Momentaufnahme ist duenn.** Spannen sind zur Eroeffnung am
weitesten und ziehen sich ueber den Tag zusammen. `--wiederholungen`
nimmt mehrere Aufnahmen im Abstand von `--abstand` Sekunden und rechnet
ueber alle; jede Aufnahme wird einzeln weggeschrieben, sodass Laeufe an
verschiedenen Tagen zusammenwachsen.

    python scripts/37_spannen_messen.py                       # eine Aufnahme
    python scripts/37_spannen_messen.py --wiederholungen 6 --abstand 600
    python scripts/37_spannen_messen.py --bericht             # nur auswerten

**Was dieses Skript NICHT tut.** Es aendert nichts. Es setzt
insbesondere `costs.py` nicht auf einen neuen Wert - das waere eine
Aenderung an der Bewertungsgrundlage aller laufenden Messungen und
gehoert vorangemeldet, nicht als Nebenwirkung einer Messung.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sqlite3
import sys
import time
from contextlib import contextmanager
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from alpaca_bot import account, data, universe  # noqa: E402
from alpaca_bot.config import DATA_DIR  # noqa: E402

DB = DATA_DIR / "spannen.sqlite"

SCHEMA = """
CREATE TABLE IF NOT EXISTS spannen (
    gemessen_am  TEXT NOT NULL,
    symbol       TEXT NOT NULL,
    bid          REAL,
    ask          REAL,
    mid          REAL,
    spanne_bps   REAL,
    liq_dezil    INTEGER,
    PRIMARY KEY (gemessen_am, symbol)
);
"""

BATCH = 200
"""Symbole je Anfrage. Alpaca vertraegt mehr, aber ein kleinerer Batch
haelt den Speicher flach und macht einen Teilausfall billig."""

MAX_PLAUSIBEL_BPS = 2000.0
"""Ueber 20 % Spanne ist keine Spanne mehr, sondern eine kaputte Quote.

Bewusst sehr grosszuegig gesetzt: Der Zweck dieses Laufs ist, weite
Spannen zu FINDEN. Eine enge Plausibilitaetsgrenze wuerde genau das
wegfiltern, was die Messung zeigen soll. Ausgeschlossen wird nur, was
keine Quote sein kann."""


@contextmanager
def _conn():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    try:
        c.executescript(SCHEMA)
        yield c
        c.commit()
    finally:
        c.close()


def eine_aufnahme(symbole: list[str], dezile: dict[str, int],
                  *, verbose: bool = True) -> pd.DataFrame:
    """Eine Momentaufnahme der Spannen ueber alle Symbole."""
    stempel = dt.datetime.now(dt.UTC).isoformat()
    zeilen = []
    for i in range(0, len(symbole), BATCH):
        teil = symbole[i:i + BATCH]
        try:
            q = data.latest_quotes(teil)
        except Exception as e:  # noqa: BLE001 - ein Batch darf den Lauf nicht kippen
            if verbose:
                print(f"      Batch {i//BATCH+1}: {type(e).__name__}, uebersprungen")
            continue
        for sym, r in q.iterrows():
            bid, ask = float(r["bid"] or 0), float(r["ask"] or 0)
            if not (ask > bid > 0):
                continue
            mid = (ask + bid) / 2
            bps = (ask - bid) / mid * 10_000
            if bps > MAX_PLAUSIBEL_BPS:
                continue
            zeilen.append({"gemessen_am": stempel, "symbol": sym,
                           "bid": bid, "ask": ask, "mid": mid,
                           "spanne_bps": bps,
                           "liq_dezil": dezile.get(sym)})
        if verbose:
            print(f"      Batch {i//BATCH+1}/{(len(symbole)-1)//BATCH+1}: "
                  f"{len(zeilen)} verwertbare Quotes bisher", flush=True)

    df = pd.DataFrame(zeilen)
    if not df.empty:
        with _conn() as c:
            df.to_sql("spannen", c, if_exists="append", index=False)
    return df


def bericht() -> str:
    with _conn() as c:
        df = pd.read_sql("SELECT * FROM spannen", c)
    if df.empty:
        return "  Noch keine Messung. Bei offener Boerse laufen lassen."

    L = ["=" * 78, "  GELD-BRIEF-SPANNE IM LIVE-UNIVERSUM", "=" * 78]
    aufnahmen = df["gemessen_am"].nunique()
    L.append(f"  {len(df):,} Quotes aus {aufnahmen} Aufnahme(n), "
             f"{df['symbol'].nunique()} Symbole")
    L.append("")

    q = df["spanne_bps"].quantile([.10, .25, .50, .75, .90]).round(1)
    L.append("  Verteilung ueber alle Symbole (bps):")
    L.append(f"    10 %  {q[.10]:>7.1f}      Median {q[.50]:>7.1f}      "
             f"90 %  {q[.90]:>7.1f}")
    L.append(f"    25 %  {q[.25]:>7.1f}                          "
             f"75 %  {q[.75]:>7.1f}")
    L.append("")

    if df["liq_dezil"].notna().any():
        L.append("  Nach Liquiditaetsdezil (1 = liquideste 10 % des Universums):")
        L.append(f"    {'Dezil':<7}{'n':>7}{'Median':>10}{'75 %':>10}{'90 %':>10}")
        g = df.dropna(subset=["liq_dezil"]).groupby("liq_dezil")["spanne_bps"]
        for dez, teil in g:
            L.append(f"    {int(dez):<7}{len(teil):>7}"
                     f"{teil.median():>10.1f}{teil.quantile(.75):>10.1f}"
                     f"{teil.quantile(.90):>10.1f}")
        L.append("")
        gehandelt = df[df["liq_dezil"].between(1, 6)]["spanne_bps"]
        if not gehandelt.empty:
            L.append(f"  Dezile 1-6 (dort kauft der Bot laut Journal): "
                     f"Median {gehandelt.median():.1f} bps")
    L.append("")
    L.append("  " + "-" * 74)
    L.append("  EINORDNUNG")
    L.append("  " + "-" * 74)
    L.append(f"  Das Kostenmodell rechnet mit 5,0 bps (costs.py:151, "
             f"'fuer Large Caps typisch').")
    median = float(df["spanne_bps"].median())
    L.append(f"  Gemessener Median: {median:.1f} bps  "
             f"= Faktor {median/5:.1f} auf die Annahme.")
    L.append("")
    L.append("  OBERGRENZE, keine Punktschaetzung: Der freie Feed ist IEX und")
    L.append("  sieht ~2 % des US-Volumens (§G29). An der konsolidierten NBBO")
    L.append("  ist die echte Spanne enger. Diese Messung taugt fuer die Frage")
    L.append("  'traegt der Vorsprung auch im unguenstigen Fall' - nicht als")
    L.append("  neuer Parameter fuer costs.py.")
    return "\n".join(L)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--symbole", type=int, default=1200,
                   help="Groesse des Universums (Vorgabe: wie live)")
    p.add_argument("--wiederholungen", type=int, default=1)
    p.add_argument("--abstand", type=int, default=600,
                   help="Sekunden zwischen den Aufnahmen")
    p.add_argument("--bericht", action="store_true",
                   help="nur auswerten, nicht messen")
    p.add_argument("--trotz-geschlossener-boerse", action="store_true",
                   help="Messung erzwingen - das Ergebnis ist dann NICHT verwertbar")
    args = p.parse_args()

    if args.bericht:
        print(bericht())
        return 0

    try:
        offen = bool(account.market_clock().get("is_open"))
    except Exception as e:  # noqa: BLE001
        print(f"  Boersenzeit nicht abrufbar: {type(e).__name__}: {e}")
        return 1

    if not offen and not args.trotz_geschlossener_boerse:
        print("=" * 78)
        print("  BOERSE GESCHLOSSEN - keine Messung.")
        print("=" * 78)
        print("  Ausserhalb der Handelszeit stellt kaum jemand Quotes. Die")
        print("  Spannen sind dann um ein Vielfaches weiter, und die Zahl")
        print("  waere schlechter als gar keine - sie saehe nach einer")
        print("\n  Vorhandene Messungen ansehen: --bericht")
        return 1

    print("=" * 78)
    print(f"  SPANNEN MESSEN  |  {args.wiederholungen} Aufnahme(n)")
    print("=" * 78)
    syms = universe.load_universe(max_symbols=args.symbole)
    print(f"  Universum : {len(syms)} Symbole")
    if len(syms) < 200:
        print("      HINWEIS: Die Dezile werden INNERHALB der uebergebenen")
        print("      Menge gebildet. Bei so wenigen Symbolen ist die Spalte")
        print("      'Dezil' bedeutungslos - fuer die Aufschluesselung das")
        print("      volle Universum messen (Vorgabe 1200).")
    print("  Dezile    : werden berechnet ...", flush=True)
    try:
        dezile = universe.liquiditaets_dezile(syms)
    except Exception as e:  # noqa: BLE001
        print(f"      nicht verfuegbar ({type(e).__name__}) - Messung ohne Dezile")
        dezile = {}

    for n in range(1, args.wiederholungen + 1):
        print(f"\n  [{n}/{args.wiederholungen}] Aufnahme ...", flush=True)
        df = eine_aufnahme(syms, dezile)
        if df.empty:
            print("      keine verwertbaren Quotes")
        else:
            print(f"      {len(df)} Quotes, Median "
                  f"{df['spanne_bps'].median():.1f} bps")
        if n < args.wiederholungen:
            time.sleep(args.abstand)

    print()
    print(bericht())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
