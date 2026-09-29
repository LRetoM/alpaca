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

from alpaca_bot import account, data, trend, universe  # noqa: E402
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
    quote_alter_s REAL,
    feed         TEXT NOT NULL DEFAULT 'iex',
    PRIMARY KEY (gemessen_am, symbol)
);
"""

# Wie alt eine Quote je Feed hoechstens sein darf, um als zeitgleiche
# Beobachtung zu gelten. `delayed_sip` ist konstruktionsbedingt ~15 Min
# alt - dort waere die 120-s-Grenze von `iex` gleichbedeutend mit "alles
# verwerfen".
QUOTE_ALTER_MAX = {"iex": 120.0, "delayed_sip": 20 * 60.0}

# Um wie viel die Eroeffnungssperre je Feed spaeter greift: der
# verzoegerte Feed zeigt um 09:50 NY die Lage von 09:35 - noch mitten in
# der Eroeffnungsturbulenz.
EROEFFNUNG_OFFSET_MIN = {"iex": 0, "delayed_sip": 15}

BATCH = 200
"""Symbole je Anfrage. Alpaca vertraegt mehr, aber ein kleinerer Batch
haelt den Speicher flach und macht einen Teilausfall billig."""

MAX_QUOTE_ALTER_S = 120.0
"""Aelter als zwei Minuten ist keine zeitgleiche Beobachtung.

**Der Grund, gemessen am 26.08.2026.** Der Median ueber das ganze
Universum lag bei 248 bps - 2,5 % Spanne, was kein Markt ist. Das
unterste Viertel lag bei 13 bps, das unterste Zehntel bei 5. Die
Verteilung ist zweigipflig: Fuer einen Teil der Werte hat IEX eine echte
beidseitige Quote, fuer den Rest steht eine alte da.

IEX sieht ~2 % des US-Volumens (§G29). Bei duenn gehandelten Werten
bedeutet das nicht 'weite Spanne', sondern 'seit Stunden kein Update'.
Wer beides zusammenwirft, misst die Abwesenheit des Feeds und nennt sie
Transaktionskosten."""

ETF_DEZIL = 0
"""Reservierte Dezil-Marke fuer die Trendbot-ETFs.

Die Liquiditaetsdezile 1-10 beschreiben das AKTIEN-Universum. Die ETFs
gehoeren nicht hinein - sie wuerden die Dezilgrenzen verschieben und
waeren in der Auswertung nicht mehr von Aktien zu trennen. Deshalb eine
eigene Marke ausserhalb des Wertebereichs, die in `bericht()` einen
eigenen Block bekommt und aus 'Dezile 1-6' herausfaellt."""

MAX_PLAUSIBEL_BPS = 2000.0
"""Ueber 20 % Spanne ist keine Spanne mehr, sondern eine kaputte Quote.

Bewusst sehr grosszuegig gesetzt: Der Zweck dieses Laufs ist, weite
Spannen zu FINDEN. Eine enge Plausibilitaetsgrenze wuerde genau das
wegfiltern, was die Messung zeigen soll. Ausgeschlossen wird nur, was
keine Quote sein kann."""


def _minuten_nach_eroeffnung(stempel: str, offset_min: int = 0) -> float:
    """Minuten zwischen Handelsbeginn und dem, was diese Aufnahme SIEHT.

    Bezug ist 09:30 **New Yorker Zeit** am selben Tag, nicht die erste
    Aufnahme des Laufs: Ein Lauf, der selbst schon in der Eroeffnungsphase
    beginnt, haette sonst seine eigene erste Aufnahme als Nullpunkt und
    wuerde die naechsten 20 Minuten faelschlich mitverwerfen. Und ueber
    `zoneinfo` statt einer festen UTC-Stunde, weil die USA und Europa die
    Zeitumstellung an verschiedenen Tagen machen.

    `offset_min` zieht die Verzoegerung des Feeds ab: `delayed_sip` zeigt
    um 09:50 die Lage von 09:35 - fuer die Eroeffnungssperre zaehlt die
    Datenzeit, nicht die Wanduhr.
    """
    from zoneinfo import ZoneInfo

    ny = ZoneInfo("America/New_York")
    ts = pd.Timestamp(stempel)
    if ts.tz is None:
        ts = ts.tz_localize("UTC")
    lokal = ts.tz_convert(ny) - pd.Timedelta(minutes=offset_min)
    eroeffnung = lokal.normalize() + pd.Timedelta(hours=9, minutes=30)
    return (lokal - eroeffnung).total_seconds() / 60


@contextmanager
def _conn():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    try:
        c.executescript(SCHEMA)
        # CREATE TABLE IF NOT EXISTS ergaenzt keine Spalten. Ohne diese
        # Nachruestung schlaegt jeder Schreibvorgang gegen eine aeltere
        # Tabelle fehl - und zwar erst NACH der Messung, also nachdem die
        # Quotes schon abgerufen waren.
        vorhanden = {r[1] for r in c.execute("PRAGMA table_info(spannen)")}
        for spalte, typ in (("quote_alter_s", "REAL"),
                            ("feed", "TEXT NOT NULL DEFAULT 'iex'")):
            if spalte not in vorhanden:
                c.execute(f"ALTER TABLE spannen ADD COLUMN {spalte} {typ}")
        yield c
        c.commit()
    finally:
        c.close()


def eine_aufnahme(symbole: list[str], dezile: dict[str, int],
                  *, feed: str = "iex", verbose: bool = True) -> pd.DataFrame:
    """Eine Momentaufnahme der Spannen ueber alle Symbole."""
    stempel = dt.datetime.now(dt.UTC).isoformat()
    zeilen = []
    for i in range(0, len(symbole), BATCH):
        teil = symbole[i:i + BATCH]
        try:
            q = data.latest_quotes(teil, feed=feed)
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
            alter = None
            try:
                qt = pd.Timestamp(r["timestamp"])
                if qt.tz is None:
                    qt = qt.tz_localize("UTC")
                alter = (pd.Timestamp.now(tz="UTC") - qt).total_seconds()
            except Exception:  # noqa: BLE001 - fehlender Zeitstempel ist kein Abbruch
                pass
            zeilen.append({"gemessen_am": stempel, "symbol": sym,
                           "bid": bid, "ask": ask, "mid": mid,
                           "spanne_bps": bps,
                           "liq_dezil": dezile.get(sym),
                           "quote_alter_s": alter,
                           "feed": feed})
        if verbose:
            print(f"      Batch {i//BATCH+1}/{(len(symbole)-1)//BATCH+1}: "
                  f"{len(zeilen)} verwertbare Quotes bisher", flush=True)

    df = pd.DataFrame(zeilen)
    if not df.empty:
        with _conn() as c:
            df.to_sql("spannen", c, if_exists="append", index=False)
    return df


EROEFFNUNG_MINUTEN = 20
"""So lange nach Handelsbeginn zaehlt eine Aufnahme nicht.

**Gemessen am 26.08.2026, nicht geschaetzt.** Die erste Aufnahme lief
sieben Minuten nach der Eroeffnung und lieferte einen Median von 528 bps
ueber 1.132 Symbole - das Hundertfache jeder plausiblen Spanne. In den
ersten Minuten stehen viele Quotes noch nicht oder nur einseitig, und
der IEX-Feed (~2 % des Volumens, §G29) braucht dafuer laenger als die
konsolidierte NBBO. Eine Aufnahme aus dieser Phase misst die Traegheit
des Feeds, nicht den Markt."""


def _feed_block(df: pd.DataFrame, feed: str, *, mit_eroeffnung: bool) -> tuple[str, float | None]:
    """Auswertung EINES Feeds. Gibt (Text, Median Dezile 1-6) zurueck."""
    offset = EROEFFNUNG_OFFSET_MIN.get(feed, 0)
    alter_max = QUOTE_ALTER_MAX.get(feed, MAX_QUOTE_ALTER_S)

    if not mit_eroeffnung:
        stempel = sorted(df["gemessen_am"].unique())
        behalten = [t for t in stempel
                    if _minuten_nach_eroeffnung(t, offset) >= EROEFFNUNG_MINUTEN]
        if not behalten:
            return (f"  [{feed}] alle {len(stempel)} Aufnahme(n) liegen in den "
                    f"ersten {EROEFFNUNG_MINUTEN} Minuten nach Handelsbeginn "
                    f"(Feed-Verzoegerung {offset} Min beruecksichtigt).", None)
        df = df[df["gemessen_am"].isin(behalten)]

    n_vor = len(df)
    alt = df["quote_alter_s"]
    if alt.notna().any():
        df = df[alt.notna() & (alt <= alter_max)]
    if df.empty:
        return (f"  [{feed}] keine Quote juenger als {alter_max:.0f} s - "
                f"nicht messbar.", None)

    L = [f"  FEED: {feed}"
         + ("   (IEX, ~2 % des US-Volumens, §G29 - OBERGRENZE)"
            if feed == "iex"
            else "   (konsolidierte NBBO, ~15 Min verzoegert - die eigentliche Zahl)")]
    L.append(f"  {len(df):,} Quotes aus {df['gemessen_am'].nunique()} Aufnahme(n), "
             f"{df['symbol'].nunique()} Symbole"
             + (f"  ({n_vor - len(df)} veraltet verworfen)" if n_vor != len(df) else ""))
    q = df["spanne_bps"].quantile([.10, .25, .50, .75, .90]).round(1)
    L.append(f"    10%={q[.10]:.1f}  25%={q[.25]:.1f}  Median={q[.50]:.1f}  "
             f"75%={q[.75]:.1f}  90%={q[.90]:.1f}  bps")

    median_16 = None
    if df["liq_dezil"].notna().any():
        L.append(f"    {'Dezil':<7}{'n':>7}{'Median':>10}{'75%':>9}{'90%':>9}")
        g = df.dropna(subset=["liq_dezil"]).groupby("liq_dezil")["spanne_bps"]
        for dez, teil in g:
            L.append(f"    {int(dez):<7}{len(teil):>7}{teil.median():>10.1f}"
                     f"{teil.quantile(.75):>9.1f}{teil.quantile(.90):>9.1f}")
        gehandelt = df[df["liq_dezil"].between(1, 6)]["spanne_bps"]
        if not gehandelt.empty:
            median_16 = float(gehandelt.median())
            L.append(f"    -> Dezile 1-6 (dort kauft der Bot): Median "
                     f"{median_16:.1f} bps")

    # Die Trendbot-ETFs, je Symbol einzeln. Bei acht Werten ist ein
    # Median wertlos - entscheidend ist, ob EINER von ihnen teuer ist,
    # denn die Allokation haelt sie alle.
    etf = df[df["liq_dezil"] == ETF_DEZIL]
    if not etf.empty:
        L.append("")
        L.append(f"    TREND-ETFs (trend.UNIVERSEN['broad']) - "
                 f"`trend_schatten.PHASE2_CONFIG` rechnet mit "
                 f"{trend.TrendConfig.kosten_bps:g} bps je Seite")
        L.append(f"    {'ETF':<7}{'n':>6}{'Median':>10}{'75%':>9}{'90%':>9}")
        for sym, teil in etf.groupby("symbol")["spanne_bps"]:
            L.append(f"    {sym:<7}{len(teil):>6}{teil.median():>10.2f}"
                     f"{teil.quantile(.75):>9.2f}{teil.quantile(.90):>9.2f}")
        L.append(f"    -> Median ueber alle ETFs: {etf['spanne_bps'].median():.2f} bps"
                 f"   |   schlechtester Einzelwert: "
                 f"{etf.groupby('symbol')['spanne_bps'].median().max():.2f} bps")
    return "\n".join(L), median_16


def bericht(*, mit_eroeffnung: bool = False) -> str:
    with _conn() as c:
        df = pd.read_sql("SELECT * FROM spannen", c)
    if df.empty:
        return "  Noch keine Messung. Bei offener Boerse laufen lassen."
    if "feed" not in df:
        df["feed"] = "iex"
    df["feed"] = df["feed"].fillna("iex")

    L = ["=" * 78, "  GELD-BRIEF-SPANNE IM LIVE-UNIVERSUM", "=" * 78]
    if not mit_eroeffnung:
        L.append(f"  (Aufnahmen aus den ersten {EROEFFNUNG_MINUTEN} Minuten nach "
                 f"Handelsbeginn ausgeschlossen; Feed-Verzoegerung beruecksichtigt)")
    L.append("")

    mediane: dict[str, float | None] = {}
    for feed in sorted(df["feed"].unique()):
        block, m16 = _feed_block(df[df["feed"] == feed].copy(), feed,
                                 mit_eroeffnung=mit_eroeffnung)
        mediane[feed] = m16
        L.append(block)
        L.append("")

    L.append("  " + "-" * 74)
    L.append("  EINORDNUNG")
    L.append("  " + "-" * 74)
    L.append("  Kostenmodell: 5,0 bps (costs.py:151). Breakeven-Grenze fuer die")
    L.append("  Strategie bei heutigem Umschlag: 3,4 bps (BETRIEBSPLAN §3.4).")
    sip = mediane.get("delayed_sip")
    iex = mediane.get("iex")
    if sip is not None:
        L.append("")
        L.append(f"  KONSOLIDIERTE NBBO (delayed_sip), Dezile 1-6: {sip:.1f} bps.")
        if sip <= 3.4:
            L.append("  -> UNTER der Breakeven-Grenze. Die Annahme von 5 bps war "
                     "zu pessimistisch;")
            L.append("     die halbe Spanne traegt den gemessenen Vorsprung "
                     "(+0,110 %/Trade).")
        elif sip <= 5.0:
            L.append("  -> zwischen Breakeven (3,4) und Annahme (5,0). Knapp, aber "
                     "die Annahme")
            L.append("     ist nicht zu guenstig - der zentrale Konflikt aus §A "
                     "bleibt bestehen.")
        elif sip <= 10.0:
            L.append("  -> UEBER der Annahme. Der Hebel ist der Umschlag "
                     "(max_hold_days), nicht der")
            L.append("     naechste Faktor (BETRIEBSPLAN §3.4, Zeile '5-10 bps').")
        else:
            L.append("  -> DEUTLICH ueber der Annahme. Kein Faktorfund dieser "
                     "Groessenordnung schliesst das;")
            L.append("     entweder radikal laengere Haltedauer oder in dieser "
                     "Form nicht handelbar (§3.4).")
        if iex is not None:
            L.append(f"  (IEX zeigt fuer dieselben Dezile {iex:.1f} bps - "
                     f"Faktor {iex / max(sip, 0.1):.0f} weiter, das ist die "
                     f"Feed-Luecke, nicht der Markt.)")
    else:
        L.append("")
        L.append("  Nur IEX gemessen - das ist eine OBERGRENZE (§G29). Fuer die")
        L.append("  eigentliche Zahl mit --feed delayed_sip nachmessen.")
    L.append("")
    L.append("  Diese Messung setzt costs.py NICHT auf einen neuen Wert - das")
    L.append("  waere eine vorangemeldete Entscheidung, keine Nebenwirkung (§3.4).")
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
    p.add_argument("--mit-eroeffnung", action="store_true",
                   help=f"auch die ersten {EROEFFNUNG_MINUTEN} Minuten nach "
                        f"Handelsbeginn mitzaehlen - NICHT verwertbar")
    p.add_argument("--ohne-etfs", action="store_true",
                   help="die Trendbot-ETFs NICHT mitmessen (Vorgabe: mitmessen)")
    p.add_argument("--trotz-geschlossener-boerse", action="store_true",
                   help="Messung erzwingen - das Ergebnis ist dann NICHT verwertbar")
    p.add_argument("--feed", choices=("iex", "delayed_sip"), default="iex",
                   help="iex = kostenloser Standard (~2 %% des Volumens, "
                        "OBERGRENZE, §G29); delayed_sip = konsolidierte NBBO, "
                        "~15 Min verzoegert - die eigentliche Zahl fuer §G44")
    args = p.parse_args()

    if args.bericht:
        print(bericht(mit_eroeffnung=args.mit_eroeffnung))
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
    print(f"  SPANNEN MESSEN  |  {args.wiederholungen} Aufnahme(n)  |  "
          f"Feed: {args.feed}")
    print("=" * 78)
    syms = universe.load_universe(max_symbols=args.symbole)
    etfs: list[str] = []
    if not args.ohne_etfs:
        # Die Trendbot-ETFs mitmessen. Sie kosten eine Handvoll Quotes,
        # beantworten aber eine Frage, die sonst offen bliebe:
        # `trend.TrendConfig` rechnet mit 2 bps je Seite, und genau so
        # eine ungemessene Annahme hat beim Aktien-Bot das Vorzeichen
        # gedreht (BEFUNDE §G39/§G54). Sie tragen ETF_DEZIL und fallen
        # damit aus 'Dezile 1-6' heraus.
        etfs = [x for x in trend.UNIVERSEN["broad"] if x not in set(syms)]
        print(f"  Trend-ETFs: {len(etfs)} zusaetzlich ({', '.join(etfs)})")
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
        print(f"\n  [{n}/{args.wiederholungen}] Aufnahme ({args.feed}) ...",
              flush=True)
        df = eine_aufnahme(syms + etfs,
                           {**dezile, **{e: ETF_DEZIL for e in etfs}},
                           feed=args.feed)
        if df.empty:
            print("      keine verwertbaren Quotes")
        else:
            aktien = df[df["liq_dezil"] != ETF_DEZIL]["spanne_bps"]
            print(f"      {len(df)} Quotes, Median Aktien "
                  f"{aktien.median():.1f} bps"
                  if not aktien.empty else f"      {len(df)} Quotes")
            e = df[df["liq_dezil"] == ETF_DEZIL]["spanne_bps"]
            if not e.empty:
                print(f"      {len(e)} ETF-Quotes, Median {e.median():.2f} bps")
        if n < args.wiederholungen:
            time.sleep(args.abstand)

    print()
    print(bericht(mit_eroeffnung=args.mit_eroeffnung))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
