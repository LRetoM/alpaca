#!/usr/bin/env python3
"""Schritt 53: Das Gate aus docs/AUSBRUCH.md §6 als ausfuehrbarer Test.

    python scripts/53_ausbruch_gate.py                       # Stand ansehen
    python scripts/53_ausbruch_gate.py --anmelden --quelle rand
    python scripts/53_ausbruch_gate.py --pruefen

**Warum es dieses Skript gibt.** Das Gate stand bisher nur als Prosa in
der Dokumentation. Eine Huerde, die niemand ausrechnet, ist keine
Huerde - sie ist eine Absichtserklaerung. Hier sind die sechs Punkte
Code, und zwar in der Reihenfolge, die sie unbestechlich macht:

1. `--anmelden` schreibt Konfiguration UND Grenzwerte fest, **bevor**
   irgendeine Zahl aus dem Prueffenster existiert.
2. `--pruefen` rechnet **einmal** und schreibt das Ergebnis
   unveraenderlich daneben. Eine zweite Pruefung derselben Anmeldung
   wird abgelehnt.

Das ist der ganze Unterschied zwischen einem Test und einer Erzaehlung
(BEFUNDE §J.2). Wer nach dem Ergebnis die Grenze verschiebt, hat nicht
gemessen, sondern erzaehlt.

**Was hier NICHT passiert: suchen.** Dieses Skript darf eine Idee nur
verwerfen oder zum Flottenbot durchlassen (`BETRIEBSPLAN` §4). Es
probiert keine Varianten. Genau deshalb braucht es keine erhoehte
Zufallsschwelle fuer sich selbst - es benutzt die des Projekts
(`ausbruch_store.schwelle_sigma()`), und zwar die STRENGERE aus
Anmeldung und Pruefung.

**Der Vorbehalt zur Quelle `rand`.** Gemessen am 12.09.2026 stammen
438.934 von 439.200 Versuchen aus Bergsteig-Ketten. Die Randmittelwerte
je Achse sind deshalb kein unabhaengiger Beleg, sondern zum grossen Teil
ein Echo desselben Huegels - die Ausgabe von `--anmelden` stellt sie
darum der Elite-Konfiguration gegenueber. Stimmen beide ueberein, ist
`rand` keine zweite Meinung.

**Speicher.** Laedt denselben Kursvorrat wie die vier Suchinstanzen
(rund 0,6 GB). Laeuft also als fuenfter Prozess daneben; bei knappem
RAM die Instanzen vorher stoppen.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import uuid
from dataclasses import dataclass, asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from alpaca_bot import ausbruch  # noqa: E402
from alpaca_bot import ausbruch_daten  # noqa: E402
from alpaca_bot import ausbruch_store  # noqa: E402
from alpaca_bot import ausbruch_suche as su  # noqa: E402
from alpaca_bot import ausbruch_versuche as av  # noqa: E402
from alpaca_bot.config import DATA_DIR  # noqa: E402

# --- Die Grenzwerte des Gates. Aus docs/AUSBRUCH.md §6, nicht neu ----
MIN_TRADES = 200          # §6.2 - darunter traegt die Streuungsschaetzung nicht
MIN_HANDELSTAGE = 60      # §6.1 - massgeblich sind TAGE, nicht Trades (§B1)
SPANNE_STRENG = 30.0      # §6.3 - nicht nur bei den optimistischen 12,2 bps
TOP_ANTEIL_MAX = 50.0     # §6.5 - Top-5-Symbole duerfen nicht die Haelfte tragen
DD_GRENZE_VORGABE = 15.0  # §6.6 - vorab zu benennen, hier die Vorgabe


def _gate_datei() -> Path:
    return DATA_DIR / "ausbruch_gate.json"


def _kopf(text: str) -> None:
    print()
    print("=" * 78)
    print(f"  {text}")
    print("=" * 78)


# =====================================================================
#  Kandidaten
# =====================================================================

def _raum_wert(achse: str, wert):
    """Den Rasterwert mit dem Typ zurueckgeben, den die Suche benutzt.

    Aus dem Protokoll kommen numpy-Typen, aus JSON kommt `52.0` statt
    `52`. `AusbruchConfig` bekaeme sonst einen float, wo ein Bar-Index
    erwartet wird - und `range(52.0)` ist ein TypeError mitten im Lauf.
    """
    kandidaten = su.RAUM.get(achse, [])
    if kandidaten and all(isinstance(k, bool) for k in kandidaten):
        return bool(wert)
    for k in kandidaten:
        try:
            if float(k) == float(wert):
                return k
        except (TypeError, ValueError):
            continue
    return wert


def randfavorit(df: pd.DataFrame | None = None,
                min_gruppe: int = 30) -> tuple[dict, list[dict]]:
    """Je Achse der Wert mit dem hoechsten mittleren Lern-t-Wert.

    Das ist die belastbarere Haelfte der Auswertung (Abschnitt 3 in
    Skript 52): Ueber hunderttausende Versuche gemittelt ist die
    Randverteilung je Achse eine Aussage - der einzelne Gewinner ist es
    nicht (§B2).

    Nur Versuche mit gueltigem Score zaehlen, also mit mindestens
    `min_trades` Trades im Lernfenster. Ohne diesen Filter kippen
    Versuche mit einer Handvoll Trades die Mittelwerte (§G63).

    Gibt (config, tabelle) zurueck.
    """
    if df is None:
        df = av.zusammenfuehren()
    g = df[df["score"].notna()]
    if g.empty:
        return {}, []
    mittel = float(g["t_lern"].mean())
    config: dict = {}
    tabelle: list[dict] = []
    for spalte in [c for c in df.columns if c.startswith("k_")]:
        s = g.groupby(spalte)["t_lern"].agg(["mean", "size"])
        s = s[s["size"] >= min_gruppe]
        if len(s) < 2:
            continue
        achse = spalte[2:]
        best = s["mean"].idxmax()
        config[achse] = _raum_wert(achse, best)
        tabelle.append({
            "achse": achse,
            "wert": config[achse],
            "delta": float(s["mean"].max() - mittel),
            "n": int(s.loc[best, "size"]),
        })
    return config, tabelle


def _normieren(config: dict) -> dict:
    """Dieselbe Ableitung, die auch die Suche vornimmt.

    `tageszeit_bis_bar < tageszeit_von_bar` waere ein leeres Zeitfenster.
    Die Suche zieht die Obergrenze hoch (`_bewerten`); ohne dieselbe
    Regel hier waere das Ergebnis nicht vergleichbar.
    """
    c = dict(config)
    if c.get("tageszeit_bis_bar", 26) < c.get("tageszeit_von_bar", 0):
        c["tageszeit_bis_bar"] = c["tageszeit_von_bar"]
    return c


# =====================================================================
#  Die sechs Kriterien - reine Funktionen, damit pruefbar
# =====================================================================

@dataclass
class Kriterium:
    nr: str
    name: str
    bestanden: bool
    ist: str
    soll: str


def _zahl(wert) -> float:
    """float(wert), aber None und Unsinn werden NaN statt Absturz."""
    try:
        f = float(wert)
    except (TypeError, ValueError):
        return float("nan")
    return f


def _ganz(wert) -> int:
    """int(wert), aber NaN und None werden 0 statt Absturz.

    `int(float("nan"))` wirft ValueError. Eine fehlende Kennzahl darf
    das Gate nicht zum Absturz bringen - sie muss es schliessen.
    """
    f = _zahl(wert)
    return int(f) if np.isfinite(f) else 0


def haelften(trades: pd.DataFrame, grenze) -> tuple[float, float, int, int]:
    """Mittlere Rendite je Trade in der ersten und zweiten Haelfte.

    Geteilt wird am Zeitpunkt, nicht an der Trade-Nummer: Sonst waere
    die "Haelfte" eine Eigenschaft der Trades und nicht des Zeitraums -
    eine Strategie, die im ersten Monat 200 Trades macht und danach
    zwei, haette sonst zwei "Haelften" im selben Monat.
    """
    if trades.empty:
        return float("nan"), float("nan"), 0, 0
    ts = pd.to_datetime(trades["einstieg_ts"])
    grenze = pd.Timestamp(grenze)
    if ts.dt.tz is not None and grenze.tz is None:
        grenze = grenze.tz_localize(ts.dt.tz)
    elif ts.dt.tz is None and grenze.tz is not None:
        grenze = grenze.tz_localize(None)
    a = trades.loc[(ts < grenze).values, "rendite_pct"]
    b = trades.loc[(ts >= grenze).values, "rendite_pct"]
    return (float(a.mean()) if len(a) else float("nan"),
            float(b.mean()) if len(b) else float("nan"),
            int(len(a)), int(len(b)))


def konzentration(trades: pd.DataFrame,
                  top: int = 5) -> tuple[float, pd.Series]:
    """Anteil der besten `top` Symbole am Gesamtgewinn, in Prozent.

    Ist der Gesamtgewinn nicht positiv, gibt es nichts zu verteilen -
    dann `inf`, damit das Kriterium faellt statt durch eine Division
    mit negativem Nenner zufaellig zu bestehen.
    """
    leer = pd.Series(dtype=float)
    if trades.empty or "gewinn_usd" not in trades.columns:
        return float("nan"), leer
    je_symbol = (trades.groupby("symbol")["gewinn_usd"].sum()
                 .sort_values(ascending=False))
    gesamt = float(je_symbol.sum())
    if not np.isfinite(gesamt) or gesamt <= 0:
        return float("inf"), je_symbol.head(top)
    return float(je_symbol.head(top).sum() / gesamt * 100.0), je_symbol.head(top)


def gate_bewerten(k12: dict, k30: dict, trades: pd.DataFrame, *,
                  schwelle: float, dd_grenze: float, haelfte_grenze,
                  min_trades: int = MIN_TRADES,
                  min_handelstage: int = MIN_HANDELSTAGE,
                  spanne_streng: float = SPANNE_STRENG,
                  top_anteil_max: float = TOP_ANTEIL_MAX) -> list[Kriterium]:
    """Die sechs Punkte aus docs/AUSBRUCH.md §6, ausgerechnet.

    **Jede Pruefung ist ausdruecklich NaN-fest.** Ein NaN-Vergleich ist
    in Python immer False - ein `nicht_bestanden = t < schwelle` wuerde
    bei NaN also "bestanden" ergeben. Genau dieser Mechanismus hat am
    12.09.2026 einen Zusammenhang vorgetaeuscht (§G63). Hier gilt
    darum: NaN faellt durch, immer.
    """
    aus: list[Kriterium] = []

    t = _zahl(k12.get("t_wert"))
    tage = _ganz(k12.get("n_handelstage"))
    ok1 = bool(np.isfinite(t) and t > schwelle and tage >= min_handelstage)
    aus.append(Kriterium(
        "1", "t ueber Zufallsschwelle, ueberlappungskorrigiert", ok1,
        f"t = {t:.2f} bei {tage} Handelstagen",
        f"t > {schwelle:.2f} und >= {min_handelstage} Handelstage"))

    n = _ganz(k12.get("n_trades"))
    aus.append(Kriterium(
        "2", "genug Trades fuer eine Streuungsschaetzung",
        bool(n >= min_trades), f"{n} Trades", f">= {min_trades} Trades"))

    t30 = _zahl(k30.get("t_wert"))
    r30 = _zahl(k30.get("rendite_pct"))
    ok3 = bool(np.isfinite(t30) and t30 > schwelle)
    aus.append(Kriterium(
        "3", f"traegt auch bei {spanne_streng:g} bps Spanne", ok3,
        f"t = {t30:.2f}, Rendite {r30:+.2f} %",
        f"t > {schwelle:.2f} (nicht nur bei 12,2 bps)"))

    m1, m2, n1, n2 = haelften(trades, haelfte_grenze)
    ok4 = bool(np.isfinite(m1) and np.isfinite(m2) and m1 > 0 and m2 > 0)
    aus.append(Kriterium(
        "4", "traegt in beiden Haelften des Prueffensters", ok4,
        f"1. Haelfte {m1:+.3f} % je Trade (n={n1}), "
        f"2. Haelfte {m2:+.3f} % je Trade (n={n2})",
        "beide Haelften positiv"))

    anteil, _top = konzentration(trades)
    ok5 = bool(np.isfinite(anteil) and anteil <= top_anteil_max)
    aus.append(Kriterium(
        "5", "haengt nicht an fuenf Symbolen", ok5,
        f"Top-5 tragen {anteil:.1f} % des Gewinns"
        if np.isfinite(anteil) else "kein verteilbarer Gewinn",
        f"<= {top_anteil_max:g} %"))

    dd = abs(_zahl(k12.get("max_drawdown_pct")))
    ok6 = bool(np.isfinite(dd) and dd <= dd_grenze)
    aus.append(Kriterium(
        "6", "maximaler Rueckgang innerhalb der vorab benannten Grenze",
        ok6, f"{dd:.1f} %", f"<= {dd_grenze:.1f} % (vorab benannt)"))

    return aus


# =====================================================================
#  Anmeldung und Pruefung - der Ein-Schuss-Mechanismus
# =====================================================================

def _laden() -> dict:
    p = _gate_datei()
    if not p.exists():
        return {"anmeldungen": []}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"anmeldungen": []}


def _schreiben(daten: dict) -> None:
    p = _gate_datei()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(daten, default=str, indent=2), encoding="utf-8")
    tmp.replace(p)


def _offene(daten: dict) -> dict | None:
    """Die juengste Anmeldung, die noch kein Ergebnis hat."""
    for a in reversed(daten.get("anmeldungen", [])):
        if a.get("ergebnis") is None and not a.get("verworfen_am"):
            return a
    return None


def anmelden(quelle: str, dd_grenze: float, datei: str | None) -> int:
    daten = _laden()
    offen = _offene(daten)
    if offen:
        print(f"Es liegt bereits eine offene Anmeldung vor "
              f"({offen['id'][:8]}, {offen['angemeldet_am'][:19]}).")
        print("Erst pruefen (--pruefen) oder ausdruecklich verwerfen "
              "(--verwerfen).")
        print("Eine zweite Anmeldung daneben waere ein zweiter Versuch "
              "am selben Prueffenster.")
        return 1

    tabelle: list[dict] = []
    if quelle == "elite":
        e = su.elite_lesen() or {}
        config = dict(e.get("config") or {})
        herkunft = (f"Elite-Konfiguration, score {e.get('score', 0):.3f}, "
                    f"Instanz [{e.get('instanz')}], {e.get('gesetzt_am', '?')[:19]}")
    elif quelle == "rand":
        config, tabelle = randfavorit()
        herkunft = ("Randfavorit: je Achse der Wert mit dem hoechsten "
                    "mittleren Lern-t-Wert (Skript 52, Abschnitt 3)")
    else:
        config = json.loads(Path(datei).read_text(encoding="utf-8"))
        config = dict(config.get("config") or config)
        herkunft = f"Datei {datei}"

    if not config:
        print("Keine Konfiguration ermittelbar - laeuft die Suche schon?")
        return 1
    config = _normieren({k: _raum_wert(k, v) for k, v in config.items()})

    jahre = ausbruch_daten.jahre_vorhanden("15Min")
    eintrag = {
        "id": uuid.uuid4().hex,
        "angemeldet_am": dt.datetime.now(dt.UTC).isoformat(),
        "quelle": quelle,
        "herkunft": herkunft,
        "config": config,
        "kriterien": {
            "schwelle_angemeldet": ausbruch_store.schwelle_sigma(),
            "n_versuche_bei_anmeldung": ausbruch_store.n_versuche(),
            "min_trades": MIN_TRADES,
            "min_handelstage": MIN_HANDELSTAGE,
            "spanne_streng_bps": SPANNE_STRENG,
            "top_anteil_max_pct": TOP_ANTEIL_MAX,
            "dd_grenze_pct": dd_grenze,
        },
        "datenbasis": {"jahre": jahre, "raster": "15Min", "lernanteil": 0.7},
        "ergebnis": None,
    }
    daten.setdefault("anmeldungen", []).append(eintrag)
    _schreiben(daten)

    _kopf("VORANMELDUNG GESCHRIEBEN - noch existiert keine Pruefzahl")
    print(f"  Kennung   : {eintrag['id'][:8]}")
    print(f"  Quelle    : {herkunft}")
    print(f"  Datei     : {_gate_datei()}")
    print()
    print("  Vorab festgelegte Grenzen (werden nicht mehr angefasst):")
    print(f"    t ueber                : {eintrag['kriterien']['schwelle_angemeldet']:.2f}")
    print(f"    Handelstage mindestens : {MIN_HANDELSTAGE}")
    print(f"    Trades mindestens      : {MIN_TRADES}")
    print(f"    Spanne streng          : {SPANNE_STRENG:g} bps")
    print(f"    Top-5-Anteil hoechstens: {TOP_ANTEIL_MAX:g} %")
    print(f"    Rueckgang hoechstens   : {dd_grenze:.1f} %")
    print()
    print("  Konfiguration:")
    for k, w in sorted(config.items()):
        print(f"    {k:<32} {w}")

    if tabelle:
        elite = dict((su.elite_lesen() or {}).get("config") or {})
        abweichend = [t for t in tabelle
                      if str(_raum_wert(t["achse"], elite.get(t["achse"])))
                      != str(t["wert"])]
        print()
        print(f"  Randfavorit gegen Elite: {len(tabelle) - len(abweichend)} "
              f"von {len(tabelle)} Achsen identisch.")
        if not abweichend:
            print("  ACHTUNG: vollstaendig identisch. Der Randfavorit ist "
                  "dann KEINE")
            print("  zweite Meinung, sondern dieselbe Konfiguration auf "
                  "zweitem Weg -")
            print("  die Randmittelwerte sind ein Echo derselben "
                  "Bergsteig-Ketten.")

    print()
    print("  Naechster Schritt: python scripts/53_ausbruch_gate.py --pruefen")
    print("=" * 78)
    return 0


def verwerfen() -> int:
    daten = _laden()
    offen = _offene(daten)
    if not offen:
        print("Keine offene Anmeldung.")
        return 1
    offen["verworfen_am"] = dt.datetime.now(dt.UTC).isoformat()
    _schreiben(daten)
    print(f"Anmeldung {offen['id'][:8]} verworfen - der Eintrag bleibt "
          f"stehen (kein Loeschen, sonst waere die Spur weg).")
    return 0


def pruefen(symbole: int | None) -> int:
    daten = _laden()
    offen = _offene(daten)
    if not offen:
        print("Keine offene Anmeldung. Erst anmelden:")
        print("  python scripts/53_ausbruch_gate.py --anmelden --quelle rand")
        return 1

    kr = offen["kriterien"]
    # Die STRENGERE der beiden Schwellen. Nachtraeglich zu lockern waere
    # der Fehler, den die Voranmeldung verhindert; nachtraeglich zu
    # verschaerfen ist nie zum eigenen Vorteil - die Suche hat seit der
    # Anmeldung weitergezaehlt.
    schwelle = max(float(kr["schwelle_angemeldet"]),
                   ausbruch_store.schwelle_sigma())

    jahre = offen["datenbasis"]["jahre"]
    raster = offen["datenbasis"]["raster"]
    print(f"Vorrat laden ({jahre}, {raster}) ...", flush=True)
    kd = ausbruch_daten.laden_kursdaten(
        jahre, raster=raster, max_symbole=symbole,
        fortschritt=lambda a, t: print(f"  {a*100:5.1f}% {t}", flush=True))
    lern, pruef, grenze = su.teilen(kd, offen["datenbasis"]["lernanteil"])
    print(f"{len(kd.arrays):,} Symbole, {kd.n_bars:,} Bars. "
          f"Prueffenster ab {grenze}.", flush=True)

    config = _normieren(
        {k: _raum_wert(k, v) for k, v in offen["config"].items()})

    print("Prueffenster rechnen (12,2 bps) ...", flush=True)
    erg12 = ausbruch.lauf(pruef, ausbruch.AusbruchConfig(**config))
    print(f"Prueffenster rechnen ({SPANNE_STRENG:g} bps) ...", flush=True)
    erg30 = ausbruch.lauf(
        pruef, ausbruch.AusbruchConfig(**{**config,
                                          "spanne_bps": SPANNE_STRENG}))

    achse = pruef.achse if hasattr(pruef, "achse") else None
    haelfte_grenze = (achse[len(achse) // 2] if achse is not None
                      else pd.Timestamp(grenze))

    kriterien = gate_bewerten(
        erg12.kennzahlen, erg30.kennzahlen, erg12.trades,
        schwelle=schwelle, dd_grenze=float(kr["dd_grenze_pct"]),
        haelfte_grenze=haelfte_grenze,
        min_trades=int(kr["min_trades"]),
        min_handelstage=int(kr["min_handelstage"]))

    # Die Pruefung selbst sind zwei Laeufe - die gehoeren in den
    # Versuchszaehler, sonst bliebe die Zufallsschwelle zu niedrig.
    lauf_id = ausbruch_store.neuer_lauf(
        {"gate": True, "anmeldung": offen["id"], "config": config},
        jahr=jahre[-1], raster=raster, n_symbole=len(kd.arrays),
        notiz=f"Gate-Pruefung {offen['id'][:8]}")
    ausbruch_store.suchversuche_buchen(lauf_id, 2)
    ausbruch_store.abschliessen(lauf_id, erg12.kennzahlen)

    bestanden = all(k.bestanden for k in kriterien)
    anteil, top = konzentration(erg12.trades)
    offen["ergebnis"] = {
        "geprueft_am": dt.datetime.now(dt.UTC).isoformat(),
        "lauf_id": lauf_id,
        "schwelle_wirksam": schwelle,
        "prueffenster_ab": str(grenze),
        "haelfte_grenze": str(haelfte_grenze),
        "kennzahlen_12bps": {k: v for k, v in erg12.kennzahlen.items()
                             if isinstance(v, (int, float, bool))},
        "kennzahlen_30bps": {k: v for k, v in erg30.kennzahlen.items()
                             if isinstance(v, (int, float, bool))},
        "top5_symbole": {str(s): float(w) for s, w in top.items()},
        "kriterien": [asdict(k) for k in kriterien],
        "bestanden": bestanden,
    }
    _schreiben(daten)

    _ergebnis_zeigen(offen, kriterien, erg12, erg30)
    return 0


def _ergebnis_zeigen(eintrag: dict, kriterien: list[Kriterium],
                     erg12, erg30) -> None:
    e = eintrag["ergebnis"]
    _kopf(f"GATE-PRUEFUNG {eintrag['id'][:8]} - docs/AUSBRUCH.md §6")
    print(f"  Angemeldet : {eintrag['angemeldet_am'][:19]}")
    print(f"  Geprueft   : {e['geprueft_am'][:19]}")
    print(f"  Quelle     : {eintrag['herkunft']}")
    print(f"  Prueffenster ab {e['prueffenster_ab'][:19]}, "
          f"Schwelle {e['schwelle_wirksam']:.2f}")
    print()
    for k in kriterien:
        zeichen = "BESTANDEN" if k.bestanden else "  FAELLT "
        print(f"  [{zeichen}] §6.{k.nr}  {k.name}")
        print(f"              ist:  {k.ist}")
        print(f"              soll: {k.soll}")
    print()
    k12 = erg12.kennzahlen
    print(f"  Prueffenster gesamt: Rendite {k12.get('rendite_pct', 0):+.2f} %, "
          f"{k12.get('n_trades', 0)} Trades, "
          f"Trefferquote {k12.get('trefferquote_pct', 0):.1f} %")
    print(f"  Bei {SPANNE_STRENG:g} bps: "
          f"Rendite {erg30.kennzahlen.get('rendite_pct', 0):+.2f} %")

    if not erg12.trades.empty:
        t = erg12.trades.copy()
        t["jahr"] = pd.to_datetime(t["einstieg_ts"]).dt.year
        print()
        print("  Je Jahr im Prueffenster (Zusatzinfo, kein Kriterium):")
        for jahr, teil in t.groupby("jahr"):
            print(f"    {int(jahr)}  {len(teil):>5} Trades  "
                  f"Mittel {teil['rendite_pct'].mean():+.3f} %  "
                  f"Summe {teil['gewinn_usd'].sum():+,.0f} $")

    gefallen = [k for k in kriterien if not k.bestanden]
    print()
    if e["bestanden"]:
        print("  URTEIL: Alle sechs Punkte bestanden. Naechster Schritt ist")
        print("  ein Flottenbot im Vorwaertsschatten (fleet.anmelden),")
        print("  NICHT das echte Konto (BEFUNDE §J.3).")
    else:
        print(f"  URTEIL: KEIN FLOTTENPLATZ. {len(gefallen)} von "
              f"{len(kriterien)} Punkten gefallen: "
              f"{', '.join('§6.' + k.nr for k in gefallen)}.")
        print("  Diese Punkte werden nicht nachtraeglich gelockert (§B2) -")
        print("  auch nicht, wenn die anderen erfuellt sind.")
    print("=" * 78)


def stand() -> int:
    daten = _laden()
    eintraege = daten.get("anmeldungen", [])
    _kopf("GATE - Stand")
    if not eintraege:
        print("  Keine Anmeldung bisher.")
        print()
        print("  Anmelden:  python scripts/53_ausbruch_gate.py --anmelden "
              "--quelle rand")
        print("=" * 78)
        return 0
    for a in eintraege:
        e = a.get("ergebnis")
        if a.get("verworfen_am"):
            zustand = f"verworfen {a['verworfen_am'][:19]}"
        elif e is None:
            zustand = "OFFEN - noch nicht geprueft"
        else:
            zustand = ("BESTANDEN" if e["bestanden"] else "durchgefallen") + \
                      f" am {e['geprueft_am'][:19]}"
        print(f"  {a['id'][:8]}  {a['angemeldet_am'][:19]}  "
              f"{a['quelle']:<8}  {zustand}")
        if e and not e["bestanden"]:
            gefallen = [k["nr"] for k in e["kriterien"] if not k["bestanden"]]
            print(f"            gefallen: "
                  f"{', '.join('§6.' + n for n in gefallen)}")
    print("=" * 78)
    return 0


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--anmelden", action="store_true")
    p.add_argument("--pruefen", action="store_true")
    p.add_argument("--verwerfen", action="store_true")
    p.add_argument("--quelle", default="rand",
                   choices=["rand", "elite", "datei"])
    p.add_argument("--datei", default=None,
                   help="JSON mit einer Konfiguration (bei --quelle datei)")
    p.add_argument("--dd-grenze", type=float, default=DD_GRENZE_VORGABE,
                   help="Vorab benannter maximaler Rueckgang in Prozent (§6.6)")
    p.add_argument("--symbole", type=int, default=None,
                   help="Nur zum Ausprobieren - aendert das Universum und "
                        "macht das Ergebnis unvergleichbar")
    args = p.parse_args()

    if args.anmelden:
        return anmelden(args.quelle, args.dd_grenze, args.datei)
    if args.pruefen:
        return pruefen(args.symbole)
    if args.verwerfen:
        return verwerfen()
    return stand()


if __name__ == "__main__":
    raise SystemExit(main())
