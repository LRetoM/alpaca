"""Ein- und Auszahlungen erfassen - damit Renditekennzahlen stimmen.

**Das Problem, das dieses Modul loest:** Der Bot rechnet durchgehend
relativ zum Kontowert. Zahlst du 10.000 $ auf 100.000 $ ein, handelt er
ab dem naechsten Zyklus korrekt mit mehr Geld - das funktioniert bereits
ohne dieses Modul.

Falsch wird dagegen **jede Auswertung**: Eine Einzahlung von 10 % sieht
in einer equity-basierten Rechnung wie +10 % Gewinn aus. Betroffen sind
der Drawdown-Zaehler (`risiko.py`), jeder Vergleich gegen Buy & Hold und
der Abgleich zwischen Depot und Schattendepot.

**Was NICHT herausgerechnet wird:** Dividenden (DIV) und Zinsen (INT).
Sie sind echter Ertrag des eingesetzten Kapitals - wer sie abzieht, macht
das System schlechter, als es ist. Nur CSD (Einzahlung) und CSW
(Auszahlung) veraendern die Bezugsgroesse.

**Zeitgewichtete Rendite (TWR):** Die einzige Kennzahl, die mit Buy &
Hold und dem Schattendepot vergleichbar ist - beide kennen keine
Einzahlungen. Sie schneidet den Verlauf an jedem Kapitalfluss und
verkettet die Teilrenditen.
"""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

from .state import Store

# Alpaca-Aktivitaetstypen, die die Bezugsgroesse der Rendite veraendern.
# Bewusst NUR diese beiden - siehe Modul-Docstring.
FLUSS_TYPEN = ("CSD", "CSW")


def fluesse_nachtragen(store: Store | None = None, *,
                       verbose: bool = False) -> int:
    """Holt Ein-/Auszahlungen von Alpaca und bucht neue davon.

    Gibt die Zahl der NEU gebuchten Fluesse zurueck. Mehrfach aufrufbar:
    Der Alpaca-Aktivitaets-`id` ist Primaerschluessel, ein bereits
    gebuchter Fluss wird still uebersprungen.
    """
    from .costs import actual_activities

    s = store or Store()
    neu = 0
    for art in FLUSS_TYPEN:
        try:
            df = actual_activities(art, limit=100)
        except Exception as e:  # noqa: BLE001 - darf den Handel nie stoppen
            if verbose:
                print(f"      Kapitalfluesse ({art}) nicht abrufbar: "
                      f"{type(e).__name__}")
            continue
        if df is None or df.empty:
            continue
        for _, r in df.iterrows():
            fluss_id = str(r.get("id") or "")
            if not fluss_id:
                continue
            betrag = _betrag(r, art)
            if betrag is None:
                continue
            ts = r.get("date") or r.get("transaction_time") or r.get("created_at")
            if s.fluss_buchen(fluss_id, ts or dt.datetime.now(dt.UTC), art, betrag):
                neu += 1
                if verbose:
                    print(f"      Kapitalfluss erkannt: {art} "
                          f"{betrag:+,.2f} USD am {str(ts)[:10]}")
    return neu


def _betrag(zeile, art: str) -> float | None:
    """Vorzeichen vereinheitlichen: Einzahlung positiv, Auszahlung negativ.

    Alpaca liefert `net_amount` je nach Typ mit unterschiedlichem
    Vorzeichen. Wer das nicht vereinheitlicht, addiert Auszahlungen zur
    Einzahlungssumme - und der einzahlungsbereinigte Hoechststand waere
    genau falsch herum korrigiert.
    """
    for feld in ("net_amount", "amount"):
        wert = zeile.get(feld)
        if wert is None:
            continue
        try:
            v = float(wert)
        except (TypeError, ValueError):
            continue
        return abs(v) if art == "CSD" else -abs(v)
    return None


def zeitgewichtete_rendite(store: Store | None = None) -> dict:
    """Rendite, die von Ein- und Auszahlungen unberuehrt bleibt.

    Der Verlauf wird an jedem Kapitalfluss geschnitten; die Teilrenditen
    werden verkettet:

        r_i      = (equity_ende - fluss_i) / equity_start - 1
        r_gesamt = prod(1 + r_i) - 1

    Gibt zusaetzlich die naive (equity-basierte) Rendite zurueck - nur
    wenn beide nebeneinander stehen, faellt auf, wenn eine Einzahlung als
    Gewinn gelesen wurde.
    """
    s = store or Store()
    v = s.kapital_verlauf(tage=3650)
    if v.empty or len(v) < 2:
        return {"n_punkte": len(v), "twr": np.nan, "naiv": np.nan,
                "hinweis": "zu wenig Messpunkte"}

    v = v.copy()
    v["ts"] = pd.to_datetime(v["ts"], format="mixed", utc=True, errors="coerce")
    v = v.dropna(subset=["ts"]).sort_values("ts")

    f = s.kapitalfluesse()
    if not f.empty:
        f = f.copy()
        f["ts"] = pd.to_datetime(f["ts"], format="mixed", utc=True,
                                 errors="coerce")
        f = f.dropna(subset=["ts"]).sort_values("ts")

    faktor = 1.0
    vorher = float(v.iloc[0]["equity"])
    for i in range(1, len(v)):
        jetzt = float(v.iloc[i]["equity"])
        # Fluesse, die zwischen den beiden Messpunkten lagen
        zufluss = 0.0
        if not f.empty:
            maske = (f["ts"] > v.iloc[i - 1]["ts"]) & (f["ts"] <= v.iloc[i]["ts"])
            zufluss = float(f.loc[maske, "betrag"].sum())
        if vorher > 0:
            faktor *= (jetzt - zufluss) / vorher
        vorher = jetzt

    naiv = (float(v.iloc[-1]["equity"]) / float(v.iloc[0]["equity"]) - 1
            if float(v.iloc[0]["equity"]) > 0 else np.nan)
    return {
        "n_punkte": len(v),
        "twr": round(faktor - 1, 6),
        "naiv": round(naiv, 6),
        "einzahlungen": round(s.einzahlungen_summe(), 2),
        "von": str(v.iloc[0]["ts"])[:19],
        "bis": str(v.iloc[-1]["ts"])[:19],
    }


def bericht(store: Store | None = None) -> str:
    s = store or Store()
    L = ["=" * 70, "  KAPITALFLUESSE UND ECHTE RENDITE", "=" * 70]
    f = s.kapitalfluesse()
    if f.empty:
        L.append("  Keine Ein-/Auszahlungen erfasst.")
        L.append("  (Bei einem unveraenderten Konto ist das korrekt.)")
    else:
        L.append(f"  {len(f)} Kapitalfluss/-fluesse:")
        for _, r in f.iterrows():
            L.append(f"    {str(r['ts'])[:10]}  {r['art']}  "
                     f"{r['betrag']:>+12,.2f} USD")
        L.append(f"  Saldo: {f['betrag'].sum():+,.2f} USD")

    r = zeitgewichtete_rendite(s)
    L.append("")
    if not np.isfinite(r.get("twr", np.nan)):
        L.append(f"  Rendite noch nicht berechenbar ({r.get('hinweis','')}).")
    else:
        L += [
            f"  Zeitraum          : {r['von']} bis {r['bis']}",
            f"  Messpunkte        : {r['n_punkte']}",
            f"  Zeitgewichtet     : {r['twr']:+.2%}   <- vergleichbar",
            f"  Naiv (equity)     : {r['naiv']:+.2%}",
        ]
        if abs(r["twr"] - r["naiv"]) > 0.001:
            L.append("  -> Die Differenz stammt aus Ein-/Auszahlungen. Nur der")
            L.append("     zeitgewichtete Wert ist mit Buy & Hold vergleichbar.")
    return "\n".join(L)
