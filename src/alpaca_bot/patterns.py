"""Musterspeicher: was sich wiederholt bewaehrt hat - und was aufgehoert hat.

Das ist die Antwort auf "mit der Zeit sollen immer klarere Muster entstehen".
Ein Muster ist hier keine vage Beobachtung, sondern eine **bedingte Aussage
mit Beleg und Lebenszyklus**:

    "Der Umkehr-Effekt traegt nur bei ruhiger Marktvolatilitaet"
    bedingung: regime_vola in ('niedrig','mittel')
    Beleg    : IC +0.031, t=2.8, ueber 74 Handelstage

**Der wichtigste Teil ist der Verfall.** Muster sind nicht dauerhaft. Ein
2026 bestaetigter Effekt kann 2027 verschwinden - durch Arbitrage,
Regimewechsel oder Strukturbruch. Wer einen einmal gefundenen Zusammenhang
dauerhaft glaubt, handelt irgendwann eine Regel, die seit Monaten nicht mehr
gilt.

Deshalb wird jedes bestaetigte Muster monatlich **auf den seither NEU
hinzugekommenen Daten** erneut geprueft - nur auf diesen, nicht auf den
alten, die es ja bereits bestaetigt haben. Faellt es zweimal in Folge durch,
wird es als 'zerfallen' markiert und alle Bots gemeldet, die es nutzen.

Genau das ist das "immer klarer": nicht ein wachsender Stapel von
Behauptungen, sondern eine kleine Menge wiederholt bestaetigter Bedingungen -
und die Gewissheit, es zu merken, wenn eine aufhoert zu funktionieren.
"""

from __future__ import annotations

import datetime as dt
import uuid

import numpy as np
import pandas as pd

from .shadow import ShadowStore
from .shadow_eval import _horizont_tage
from .statistik import gruppierter_test

MIN_TAGE_BESTAETIGUNG = 60
"""Unter dieser Zahl unabhaengiger Handelstage wird kein Muster bestaetigt."""

FEHLSCHLAEGE_BIS_ZERFALL = 2
"""Ein einzelner schlechter Monat ist Rauschen. Zwei in Folge sind ein Signal."""


def erfassen(beschreibung: str, bedingung: str, *, wirkung: str = "ic_5d",
             entdeckt_aus: str = "schatten", store: ShadowStore | None = None
             ) -> str:
    """Legt ein Muster als KANDIDAT an - noch nicht als bestaetigt.

    `bedingung` ist ein pandas-`query`-Ausdruck auf dem Auswertungsdatensatz,
    z. B. ``"regime_vola == 'niedrig'"`` oder ``"score > 0.6"``. Er muss
    maschinenlesbar sein, damit die Verfallspruefung ihn spaeter ohne
    menschliches Zutun wiederholen kann.

    **Idempotent seit dem 22.08.2026.** Existiert (bedingung, wirkung)
    bereits, wird die vorhandene `muster_id` zurueckgegeben und NICHTS
    veraendert. Ohne diese Zusicherung waren drei Defekte scharf, sobald
    der Schatten seinen 20. Handelstag erreicht (`docs/BEFUNDE.md` §G16):

    1. `shadow.lernen` ruft `kandidaten_suchen(anlegen=True)` an JEDEM
       Handelstag. Bei frischer `uuid4` je Aufruf waere die Tabelle
       taeglich um dieselben ~4 Regimeschnitte gewachsen - gemessen im
       Regressionstest: 10 Zeilen nach 5 Laeufen statt 2.
    2. Ein als `zerfallen` markiertes Muster waere am naechsten Tag als
       frischer `kandidat` zurueckgekehrt. Der Verfallsmechanismus -
       der eigentliche Zweck dieses Moduls (siehe Modul-Docstring) -
       waere damit wirkungslos gewesen.
    3. Der Status eines bestaetigten Musters waere ueberschrieben worden.

    Deshalb wird ein vorhandener Eintrag hier bewusst NICHT angefasst -
    weder Status noch Zaehler noch Beschreibung. Wer ein Muster neu
    bewerten will, nimmt `pruefen()`; das ist der Weg, der die
    Verfallslogik durchlaeuft.
    """
    s = store or ShadowStore()
    with s._conn() as c:
        # Der Schluessel ist (bedingung, wirkung), nicht die Beschreibung:
        # Der Text ist Prosa und kann sich aendern, die Messvorschrift ist
        # die Identitaet des Musters. Dieselbe Bedingung auf `ic_5d` und
        # auf `rendite` sind dagegen zwei verschiedene Aussagen.
        vorhanden = c.execute(
            "SELECT muster_id FROM muster WHERE bedingung=? AND wirkung=?",
            (bedingung, wirkung),
        ).fetchone()
        if vorhanden:
            return str(vorhanden["muster_id"])

        mid = f"M-{uuid.uuid4().hex[:8]}"
        c.execute(
            "INSERT INTO muster (muster_id, beschreibung, bedingung, wirkung,"
            " entdeckt_am, entdeckt_aus, status, fehlschlaege)"
            " VALUES (?,?,?,?,?,?,'kandidat',0)",
            (mid, beschreibung, bedingung, wirkung,
             dt.datetime.now(dt.UTC).isoformat(), entdeckt_aus),
        )
        # Jeder Musterschnitt ist ein Versuch und hebt die Schwelle fuer
        # ALLE - genau wie eine Bot-Anmeldung (fleet.anmelden) und eine
        # Hypothese (hypotheses.erfassen). Wer neun Regimezellen prueft,
        # findet in mindestens einer garantiert etwas (§B2); eine Schwelle,
        # die davon nichts weiss, ist zu niedrig.
        #
        # Der Zaehler steigt NUR beim erstmaligen Anlegen. Stuende er
        # ausserhalb dieser Bedingung, wuerde ihn der taegliche Lauf
        # unbegrenzt hochtreiben und jede laufende Messung erdrosseln.
        c.execute(
            "INSERT INTO versuchszaehler (id, n_bots_gesamt, n_hypothesen,"
            " aktualisiert) VALUES (1, 0, 1, ?)"
            " ON CONFLICT(id) DO UPDATE SET"
            "   n_hypothesen = versuchszaehler.n_hypothesen + 1,"
            "   aktualisiert = excluded.aktualisiert",
            (dt.datetime.now(dt.UTC).isoformat(),),
        )
    return mid


def _messen(df: pd.DataFrame, bedingung: str, wirkung: str = "ic_5d") -> dict:
    """Misst die Wirkung eines Musters auf einem Datensatz.

    Gerechnet wird ueber die Zeitreihe der Tageswerte, nicht ueber den Topf
    aller Zeilen - alle Vorhersagen eines Tages sind vom selben Marktfaktor
    getrieben und zaehlen statistisch naeher an einer Beobachtung als an 200.
    """
    from .shadow_eval import ic

    if df.empty:
        return {"n_tage": 0, "effekt": np.nan, "t": np.nan}
    try:
        teil = df.query(bedingung)
    except Exception as e:  # noqa: BLE001
        return {"n_tage": 0, "effekt": np.nan, "t": np.nan,
                "fehler": f"{type(e).__name__}: {e}"}
    if teil.empty:
        return {"n_tage": 0, "effekt": np.nan, "t": np.nan}

    if wirkung == "ic_5d":
        k = ic(teil)
        return {"n_tage": k["n_tage"], "effekt": k["ic"], "t": k["t"]}

    # Sonst: Tagesmittel der Zielgroesse gegen null testen.
    #
    # UEBER `gruppierter_test` mit `horizont`, nicht von Hand: Die
    # Zielgroessen sind 5-Tage-Fenster (`fwd_5d`, `ueberschuss_5d`), und
    # benachbarte Handelstage teilen vier Fuenftel davon (§G12). Ein hier
    # von Hand gerechneter t-Wert waere im Mittel um 1,6 zu hoch - und
    # dieser Wert entscheidet, ob ein Muster als bestaetigt gilt.
    #
    # Ein Musterspeicher, der auf unkorrigierten Werten laeuft, wuerde bei
    # 5-Tage-Fenstern in rund 40 % der Faelle ein Muster "bestaetigen",
    # das reines Rauschen ist - und zwar dauerhaft und automatisch.
    spalte = {"ueberschuss": "ueberschuss_5d", "rendite": "fwd_5d"}.get(wirkung, wirkung)
    if spalte not in teil:
        return {"n_tage": 0, "effekt": np.nan, "t": np.nan}
    h = _horizont_tage(spalte)
    r = gruppierter_test(teil[spalte], teil["tag"], min_gruppen=MIN_TAGE_BESTAETIGUNG,
                         horizont=h)
    if r.n_gruppen < 3:
        return {"n_tage": r.n_gruppen, "effekt": np.nan, "t": np.nan}
    t = r.t_ueberlappung
    if not np.isfinite(t):
        return {"n_tage": r.n_gruppen, "effekt": round(float(r.mittel), 5),
                "t": np.nan,
                "hinweis": f"{r.n_gruppen} Tage sind fuer einen {h}-Tage-"
                           f"Horizont zu wenig - kein t-Wert"}
    return {"n_tage": int(r.n_gruppen), "effekt": round(float(r.mittel), 5),
            "t": round(float(t), 2), "t_roh": round(float(r.t), 2),
            "aufblaehung": round(float(r.aufblaehung), 2)}


def pruefen(store: ShadowStore | None = None, *, nur_neue_daten: bool = True,
            verbose: bool = True) -> pd.DataFrame:
    """Prueft alle Muster - bestaetigte auf NEUEN Daten, Kandidaten auf allen.

    `nur_neue_daten=True` ist der Kern der Verfallspruefung: Ein bestaetigtes
    Muster wird ausschliesslich an dem gemessen, was seit seiner letzten
    Bestaetigung hinzugekommen ist. Wuerde man die alten Daten mitrechnen,
    truege der urspruengliche Fund das Ergebnis noch jahrelang mit und der
    Zerfall fiele nie auf.
    """
    from . import fleet
    from .shadow_eval import datensatz

    s = store or ShadowStore()
    df = datensatz(s, buch="rangliste", sperrzone_oeffnen=False)
    alle = s.table("muster")
    if alle.empty:
        return pd.DataFrame()

    schwelle = fleet.schwelle_sigma(s)
    jetzt = dt.datetime.now(dt.UTC).isoformat()
    zeilen = []

    for _, m in alle.iterrows():
        basis = df
        if nur_neue_daten and m["status"] == "bestaetigt" and m["zuletzt_bestaetigt"]:
            grenze = pd.Timestamp(m["zuletzt_bestaetigt"]).date()
            basis = df[df["tag"] > grenze] if not df.empty else df

        r = _messen(basis, m["bedingung"], m["wirkung"])
        haelt = (np.isfinite(r.get("t", np.nan))
                 and abs(r["t"]) > schwelle
                 and r["n_tage"] >= MIN_TAGE_BESTAETIGUNG)

        neuer_status, fehl = m["status"], int(m["fehlschlaege"] or 0)
        zerfallen_seit = m["zerfallen_seit"]

        if r["n_tage"] == 0:
            hinweis = "keine neuen Daten"
        elif haelt:
            neuer_status, fehl = "bestaetigt", 0
            hinweis = "haelt"
        else:
            if m["status"] == "bestaetigt":
                fehl += 1
                if fehl >= FEHLSCHLAEGE_BIS_ZERFALL:
                    neuer_status = "zerfallen"
                    zerfallen_seit = zerfallen_seit or jetzt
                    hinweis = f"ZERFALLEN nach {fehl} Fehlschlaegen"
                else:
                    hinweis = f"Fehlschlag {fehl}/{FEHLSCHLAEGE_BIS_ZERFALL}"
            else:
                hinweis = (f"noch zu duenn ({r['n_tage']} von "
                           f"{MIN_TAGE_BESTAETIGUNG} Tagen)")

        with s._conn() as c:
            c.execute(
                "UPDATE muster SET n_tage=?, effekt=?, t_wert=?, schwelle=?,"
                " status=?, fehlschlaege=?, zuletzt_geprueft=?,"
                " zuletzt_bestaetigt=?, zerfallen_seit=? WHERE muster_id=?",
                (r["n_tage"], r.get("effekt"), r.get("t"), schwelle,
                 neuer_status, fehl, jetzt,
                 jetzt if haelt else m["zuletzt_bestaetigt"],
                 zerfallen_seit, m["muster_id"]),
            )
        zeilen.append({"muster_id": m["muster_id"],
                       "beschreibung": m["beschreibung"][:44],
                       "n_tage": r["n_tage"], "effekt": r.get("effekt"),
                       "t": r.get("t"), "schwelle": schwelle,
                       "status": neuer_status, "hinweis": hinweis})
        if verbose:
            print(f"  {m['muster_id']}  {m['beschreibung'][:40]:<42} "
                  f"t={r.get('t')}  -> {neuer_status} ({hinweis})")
    return pd.DataFrame(zeilen)


def kandidaten_suchen(store: ShadowStore | None = None, *,
                      anlegen: bool = False, verbose: bool = True) -> pd.DataFrame:
    """Durchsucht die Regime-Dimensionen nach auffaelligen Bedingungen.

    **Warnung, die mitgefuehrt werden muss:** Regimeschnitte vervielfachen
    die Zahl der Vergleiche. Drei Trenddimensionen mal drei Volabaender
    ergeben neun Zellen - und in mindestens einer davon sieht der Effekt
    grossartig aus, garantiert. Gefundene Kandidaten sind deshalb
    ausdruecklich KEINE Befunde, sondern Hypothesen, die sich erst ueber
    `pruefen()` auf spaeteren Daten bewaehren muessen.

    Geschnitten werden nur die drei im Plan festgelegten Achsen, nicht
    beliebig viele.
    """
    from .shadow_eval import datensatz

    s = store or ShadowStore()
    df = datensatz(s, buch="rangliste", sperrzone_oeffnen=False)
    if df.empty:
        return pd.DataFrame()

    achsen = {
        "regime_markt": sorted(df["regime_markt"].dropna().unique()),
        "regime_vola": sorted(df["regime_vola"].dropna().unique()),
    }
    zeilen = []
    for achse, werte in achsen.items():
        for w in werte:
            bed = f"{achse} == '{w}'"
            r = _messen(df, bed, "ic_5d")
            zeilen.append({"bedingung": bed, "n_tage": r["n_tage"],
                           "ic": r.get("effekt"), "t": r.get("t")})
            if anlegen and r["n_tage"] >= 20:
                erfassen(f"Umkehr-Effekt bei {achse}={w}", bed,
                         entdeckt_aus="schatten", store=s)
    out = pd.DataFrame(zeilen).sort_values("t", ascending=False, na_position="last")
    if verbose and not out.empty:
        print(out.to_string(index=False))
        print("\n  Das sind KANDIDATEN, keine Befunde. Sie muessen sich auf")
        print("  spaeteren, hier noch nicht gesehenen Daten bewaehren.")
    return out


def bericht(store: ShadowStore | None = None) -> str:
    s = store or ShadowStore()
    df = s.table("muster")
    L = ["=" * 78, "  MUSTERSPEICHER", "=" * 78]
    if df.empty:
        L += ["  Noch keine Muster erfasst.", "",
              "  Kandidaten suchen:",
              "    python scripts/17_shadow_report.py --muster-suchen"]
        return "\n".join(L)

    for status in ("bestaetigt", "kandidat", "zerfallen", "widerlegt"):
        teil = df[df["status"] == status]
        if teil.empty:
            continue
        L.append(f"\n  {status.upper()} ({len(teil)})")
        for _, m in teil.iterrows():
            L.append(f"    {m['muster_id']}  {m['beschreibung']}")
            L.append(f"        Bedingung: {m['bedingung']}")
            L.append(f"        Effekt {m['effekt']}  t={m['t_wert']}  "
                     f"ueber {m['n_tage']} Tage  (Schwelle {m['schwelle']})")
            if status == "zerfallen":
                L.append(f"        ZERFALLEN seit {str(m['zerfallen_seit'])[:10]} - "
                         "nicht mehr verwenden.")
    return "\n".join(L)
