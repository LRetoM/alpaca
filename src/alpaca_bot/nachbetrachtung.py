"""Was WAERE gewesen - Ausstiege und Wiedereinstiege im Rueckblick pruefen.

Das Handelsprotokoll beantwortet "was ist passiert". Dieses Modul
beantwortet die teurere Frage: **war es richtig?**

Drei Fragen, die sich sonst niemand stellt, weil die Antwort unbequem
sein kann:

    1. Der Zeitausstieg nach `max_hold_days` verkauft eine Position, auch
       wenn sie noch steigt. Wie oft war das ein Fehler?
    2. Nach dem Verkauf gilt eine Sperrfrist. Wurde das Symbol spaeter
       zurueckgekauft - und war der Umweg teurer als Durchhalten?
    3. Zwischen hoechstem erreichtem Kurs (MFE) und tatsaechlichem
       Ausstieg liegt Luft. Wie viel, und laesst sie sich heben?

**Warum das eigene Modul und nicht `lifecycle.py`:** Dort steht, WAS mit
einem Trade geschah. Hier steht, was die ALTERNATIVE gebracht haette -
eine kontrafaktische Rechnung. Beides zu vermischen macht es zu leicht,
eine Vermutung ueber die Alternative fuer eine Messung zu halten.

**Die wichtigste Einschraenkung**, gleich vorweg: Ausstiege haeufen sich
auf wenigen Tagen (am 04.08.2026 zehn Positionen gleichzeitig). Ihre
Nachlauf-Fenster ueberlappen fast vollstaendig - zehn Faelle sind dann
etwa eine Beobachtung, nicht zehn. Jede Auswertung hier laeuft deshalb
ueber `statistik.gruppierter_test`, und der Bericht nennt die Zahl der
unabhaengigen Tage immer mit.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .lifecycle import Lifecycle
from .statistik import gruppierter_test


def _handelstage_zwischen(a, b) -> int | None:
    try:
        s, e = pd.Timestamp(a), pd.Timestamp(b)
        if s.tz is None:
            s = s.tz_localize("UTC")
        if e.tz is None:
            e = e.tz_localize("UTC")
        return max(0, len(pd.bdate_range(s.normalize(), e.normalize())) - 1)
    except Exception:  # noqa: BLE001
        return None


def war_der_ausstieg_richtig(
    trades: pd.DataFrame | None = None, *, markt: pd.Series | None = None,
) -> pd.DataFrame:
    """Je Ausstiegsgrund: Wie lief der Kurs NACH dem Verkauf weiter?

    Ein positiver Nachlauf heisst nicht automatisch "zu frueh verkauft" -
    in einem steigenden Markt steigt fast alles. Deshalb wird, wenn
    `markt` uebergeben ist, der Marktverlauf abgezogen. Nur der
    UEBERSCHUSS ist eine Aussage ueber die Ausstiegsregel; die Rohzahl
    ist eine Aussage ueber den Markt.

    Args:
        markt: Schlusskurse eines Index (SPY), tz-naiv normalisiert.
    """
    t = Lifecycle().table() if trades is None else trades
    t = t[t["exit_date"].notna()].copy()
    if t.empty:
        return pd.DataFrame()

    t["exit_tag"] = pd.to_datetime(t["exit_date"], format="mixed", utc=True,
                                   errors="coerce").dt.tz_localize(None).dt.normalize()

    for h in (1, 5, 10):
        spalte = f"after_{h}d"
        if spalte not in t.columns:
            continue
        if markt is not None:
            t[f"ueberschuss_{h}d"] = t[spalte] - t["exit_tag"].map(
                lambda d, hh=h: _markt_fwd(markt, d, hh)
            )
        else:
            t[f"ueberschuss_{h}d"] = t[spalte]

    zeilen = []
    for grund, g in t.groupby("exit_reason"):
        zeile = {"ausstiegsgrund": grund, "n": len(g),
                 "n_tage": g["exit_tag"].nunique(),
                 "realisiert": g["return_pct"].mean()}
        for h in (1, 5, 10):
            sp = f"ueberschuss_{h}d"
            zeile[f"danach_{h}d"] = g[sp].mean() if sp in g else np.nan
        zeilen.append(zeile)
    return pd.DataFrame(zeilen).set_index("ausstiegsgrund").round(4)


def _markt_fwd(markt: pd.Series, tag, horizont: int) -> float:
    if pd.isna(tag):
        return np.nan
    idx = markt.index[markt.index <= tag]
    if len(idx) == 0:
        return np.nan
    pos = markt.index.get_loc(idx[-1])
    if pos + horizont >= len(markt):
        return np.nan
    return float(markt.iloc[pos + horizont] / markt.iloc[pos] - 1)


def zeitausstieg_pruefen(
    trades: pd.DataFrame | None = None, *, markt: pd.Series | None = None,
    horizont: int = 5,
) -> tuple[pd.DataFrame, object]:
    """Der Kernfall: War der Zeitausstieg nach `max_hold_days` zu frueh?

    Gibt die Einzelfaelle zurueck UND den gruppierten Test darueber.
    Ohne den Test verleitet die Einzelfallliste zum Zaehlen ("10 von 13
    waeren besser gelaufen") - und genau dieses Zaehlen ist der Fehler,
    wenn zehn davon am selben Tag stattfanden.
    """
    t = Lifecycle().table() if trades is None else trades
    t = t[(t["exit_reason"] == "zeitausstieg") & t["exit_date"].notna()].copy()
    sp = f"after_{horizont}d"
    if t.empty or sp not in t.columns:
        return pd.DataFrame(), None

    t["exit_tag"] = pd.to_datetime(t["exit_date"], format="mixed", utc=True,
                                   errors="coerce").dt.tz_localize(None).dt.normalize()
    if markt is not None:
        t["markt"] = t["exit_tag"].map(lambda d: _markt_fwd(markt, d, horizont))
        t["ueberschuss"] = t[sp] - t["markt"]
    else:
        t["markt"] = np.nan
        t["ueberschuss"] = t[sp]

    fall = t[["symbol", "exit_tag", "return_pct", sp, "markt", "ueberschuss"]].copy()
    fall = fall.dropna(subset=["ueberschuss"]).sort_values("ueberschuss",
                                                           ascending=False)
    # `horizont` durchreichen: `ueberschuss` ist die Rendite ueber
    # `horizont` Tage NACH dem Ausstieg. Zwei an aufeinanderfolgenden
    # Tagen ausgestiegene Positionen teilen sich damit `horizont - 1`
    # Tage ihres Nachlauf-Fensters (§G12). Ohne das Argument faellt der
    # t-Wert hier systematisch zu hoch aus - und dies ist die Zahl, an
    # der die Frage "haetten wir laenger halten sollen?" haengt.
    test = gruppierter_test(fall["ueberschuss"], fall["exit_tag"],
                            horizont=horizont)
    # Nur die Zahlenspalten runden - `exit_tag` ist ein Datum, und
    # DataFrame.round() wuerde darauf nur eine Warnung erzeugen.
    zahlen = fall.select_dtypes(include="number").columns
    fall[zahlen] = fall[zahlen].round(4)
    return fall, test


def wiedereinstiege(
    journal_orders: pd.DataFrame | None = None, sperrfrist: int = 3,
) -> pd.DataFrame:
    """Wurde ein verkauftes Symbol spaeter zurueckgekauft - und lohnte es?

    Unterscheidet streng zwischen zwei Faellen, die im Orderbuch gleich
    aussehen:

      * **Wiedereinstieg**: verkauft, Position war leer, spaeter neu
        gekauft. Nur hier ist die Frage "haetten wir einfach halten
        sollen?" ueberhaupt sinnvoll.
      * **Nachkauf**: die Position bestand durchgehend und wurde
        aufgestockt (`allow_topup`). Sieht im Orderbuch wie ein zweiter
        Kauf aus, ist aber kein Wiedereinstieg - wer das vermengt, zaehlt
        50 Nachkaeufe als 50 Fehlentscheidungen.

    `zwischenkosten` ist die eigentliche Kennzahl: die Differenz zwischen
    Rueckkaufkurs und Verkaufskurs. Positiv heisst, der Umweg ueber den
    Verkauf war teuer - man hat teurer zurueckgekauft als verkauft.
    """
    from .journal import Journal

    o = Journal().table("orders", "dry_run = 0") if journal_orders is None \
        else journal_orders
    if o.empty:
        return pd.DataFrame()

    o = o.copy()
    o["ts"] = pd.to_datetime(o["ts"], format="mixed", utc=True, errors="coerce")
    o = o.dropna(subset=["ts"]).sort_values("ts")

    # Bestand je Symbol mitfuehren, um Nachkauf von Wiedereinstieg zu
    # trennen. Ohne diese Buchfuehrung ist die Unterscheidung unmoeglich:
    # Beide sind im Orderbuch schlicht eine weitere "buy"-Zeile.
    zeilen = []
    for sym, g in o.groupby("symbol"):
        offen = False
        letzter_verkauf = None
        for _, r in g.iterrows():
            if r["side"] == "buy":
                if offen:
                    continue  # Nachkauf - kein Wiedereinstieg
                if letzter_verkauf is not None:
                    v_kurs = letzter_verkauf["fill_price"]
                    k_kurs = r["fill_price"]
                    tage = _handelstage_zwischen(letzter_verkauf["ts"], r["ts"])
                    zeilen.append({
                        "symbol": sym,
                        "verkauft_am": letzter_verkauf["ts"],
                        "verkaufskurs": v_kurs,
                        "zurueck_am": r["ts"],
                        "rueckkaufkurs": k_kurs,
                        "handelstage_pause": tage,
                        "sperrfrist_verletzt": (tage is not None
                                                and tage < sperrfrist),
                        "zwischenkosten_pct": (
                            (k_kurs / v_kurs - 1) if v_kurs and k_kurs else np.nan
                        ),
                    })
                offen = True
            elif r["side"] == "sell":
                offen = False
                letzter_verkauf = r

    if not zeilen:
        return pd.DataFrame()
    df = pd.DataFrame(zeilen)
    return df.sort_values("zurueck_am").reset_index(drop=True)


def bericht(markt: pd.Series | None = None) -> str:
    """Lesbare Nachbetrachtung fuer den Tages-/Wochenbericht."""
    L = ["=" * 76, "  NACHBETRACHTUNG: waren die Ausstiege richtig?", "=" * 76, ""]

    je_grund = war_der_ausstieg_richtig(markt=markt)
    if je_grund.empty:
        L.append("  Noch keine abgeschlossenen Trades.")
        return "\n".join(L)

    # Der Bericht MUSS nennen, in welchem Modus er gerechnet hat. "falls
    # Markt uebergeben" stand hier frueher - und liess offen, welcher der
    # beiden Faelle die Tabelle darunter erzeugt hat. Ein Aufruf ohne
    # `markt` (z. B. aus der Shell) liefert Rohzahlen, die im Bullenmarkt
    # jeden Ausstieg zu frueh aussehen lassen; genau so wurden sie am
    # 21.08.2026 einmal fehlgedeutet.
    if markt is None:
        L.append("  ACHTUNG: OHNE Marktbereinigung gerechnet. Die Spalten")
        L.append("  'danach_*' enthalten Rohrenditen - in einem steigenden")
        L.append("  Markt steigt nach jedem Verkauf fast alles. Erst mit")
        L.append("  `markt=` sind sie eine Aussage ueber die Ausstiegsregel.")
    else:
        L.append("  Je Ausstiegsgrund, Nachlauf MARKTBEREINIGT "
                 "(Ueberschuss gegen die Marktreihe):")
    L.append("  " + je_grund.to_string().replace("\n", "\n  "))
    L.append("")

    fall, test = zeitausstieg_pruefen(markt=markt)
    L.append("-" * 76)
    L.append("  ZEITAUSSTIEG: haetten wir laenger halten sollen?")
    L.append("-" * 76)
    if test is None or fall.empty:
        L.append("  Noch keine auswertbaren Zeitausstiege.")
    else:
        besser = int((fall["ueberschuss"] > 0).sum())
        # Diese Zeile wird am haeufigsten zitiert ("18 von 24") - sie muss
        # ihren eigenen Bezug mitfuehren, sonst wandert sie ohne ihn weiter.
        bezug = ("Ueberschuss ueber den Markt" if markt is not None
                 else "ROHRENDITE, Markt NICHT abgezogen")
        L.append(f"  Faelle, in denen Halten besser gewesen waere: "
                 f"{besser} von {len(fall)}  ({bezug})")
        L.append("")
        L.append(str(test))
        L.append("")
        L.append("  ACHTUNG: Die Faelle verteilen sich auf "
                 f"{fall['exit_tag'].nunique()} Handelstage. Die Zahl der TAGE "
                 "ist massgeblich,")
        L.append("  nicht die Zahl der Faelle - Positionen desselben Tages "
                 "erleben denselben Markt.")

    L.append("")
    L.append("-" * 76)
    L.append("  WIEDEREINSTIEGE (Nachkaeufe sind ausgenommen)")
    L.append("-" * 76)
    w = wiedereinstiege()
    if w.empty:
        L.append("  Keine Wiedereinstiege - jedes verkaufte Symbol blieb verkauft.")
    else:
        L.append(f"  {len(w)} Wiedereinstieg(e), davon "
                 f"{int(w['sperrfrist_verletzt'].sum())} vor Ablauf der Sperrfrist.")
        L.append("  " + w.to_string(index=False).replace("\n", "\n  "))
        gueltig = w["zwischenkosten_pct"].dropna()
        if len(gueltig):
            L.append("")
            L.append(f"  Mittlere Zwischenkosten: {gueltig.mean():+.2%} "
                     "(positiv = teurer zurueckgekauft als verkauft)")
    return "\n".join(L)
