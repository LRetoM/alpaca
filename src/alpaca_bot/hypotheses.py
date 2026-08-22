"""Hypothesenregister: externes Wissen pruefen statt uebernehmen.

Fachpublikationen und Handelsplattformen sind eine legitime Ideenquelle -
aber niemals ein Signal. Die nuechterne Ausgangslage:

  * Hou, Xue & Zhang (2020) prueften 452 dokumentierte Anomalien mit
    sauberer Methodik nach - rund **65 % fielen durch**.
  * McLean & Pontiff (2016) zeigten, dass die Wirkung publizierter
    Anomalien nach Veroeffentlichung im Mittel um **~58 % nachlaesst**.

Gruende: Publikationsverzerrung (nur Erfolge werden gedruckt),
Ueberanpassung in der Quelle, und Arbitrage nach Bekanntwerden.

**Daraus folgt die Regel dieses Moduls:** Eine externe Behauptung wird
erfasst, operationalisiert und dann durch unsere eigenen Daten geschickt.
Der Historientest ist der billige Filter, der Vorwaertstest im
Schattenbetrieb die teure - und einzig zaehlende - Bestaetigung.

    erfassen  ->  operationalisieren  ->  Historientest (8 Jahre)
       -> besteht?  ->  Vorwaertstest im Schatten
       -> besteht?  ->  in den Musterspeicher

`erfasst_am` liegt zwingend VOR dem Test. Dieselbe Voranmeldung wie bei den
Bots, aus demselben Grund: Ohne sie laesst sich ein spaeterer Treffer nicht
von einer nachtraeglichen Erzaehlung unterscheiden.

Zusaetzlich wird bei publizierten Anomalien der IC **vor** und **nach** dem
Veroeffentlichungsdatum getrennt gemessen. Faellt der Effekt danach deutlich
ab, ist das der Zerfall aus McLean & Pontiff - und ein starkes Argument,
die Idee nicht weiterzuverfolgen.
"""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

from .shadow import ShadowStore

# Vorabgewichtung nach Quellenklasse (Plan §10.2). Sie ersetzt keine Messung,
# sondern entscheidet, wie viel Aufwand eine Behauptung ueberhaupt wert ist.
QUELLEN_TYPEN = {
    "akademisch_repliziert": "mittel",
    "akademisch_einzeln": "niedrig-mittel",
    "praktiker": "niedrig-mittel",
    "broker": "niedrig",
    "blog": "sehr niedrig",
    "eigene_messung": "mittel",
}


def erfassen(hyp_id: str, behauptung: str, *, quelle: str, quelle_typ: str,
             operationalisierung: str = "", veroeffentlicht: str | None = None,
             behaupteter_effekt: str = "", store: ShadowStore | None = None) -> str:
    """Traegt eine Behauptung ein - VOR jedem Test.

    Args:
        operationalisierung: die exakte Messvorschrift. Ohne sie ist die
            Hypothese nicht pruefbar, und "hat funktioniert" waere
            Auslegungssache.
        veroeffentlicht: Datum der Quelle. Noetig fuer den Zerfallstest.
    """
    s = store or ShadowStore()
    if quelle_typ not in QUELLEN_TYPEN:
        raise ValueError(
            f"quelle_typ muss einer von {sorted(QUELLEN_TYPEN)} sein - "
            "die Klasse bestimmt, wie viel Aufwand die Pruefung wert ist."
        )
    with s._conn() as c:
        if c.execute("SELECT 1 FROM hypothesen WHERE hyp_id=?", (hyp_id,)).fetchone():
            return f"{hyp_id} ist bereits erfasst."
        c.execute(
            "INSERT INTO hypothesen (hyp_id, behauptung, quelle, quelle_typ,"
            " veroeffentlicht, behaupteter_effekt, erfasst_am,"
            " operationalisierung, testbar, status)"
            " VALUES (?,?,?,?,?,?,?,?,?,'offen')",
            (hyp_id, behauptung, quelle, quelle_typ, veroeffentlicht,
             behaupteter_effekt, dt.datetime.now(dt.UTC).isoformat(),
             operationalisierung, int(bool(operationalisierung))),
        )
        # Jede Hypothese ist ein Versuch und hebt die Signifikanzschwelle.
        c.execute(
            "INSERT INTO versuchszaehler (id, n_bots_gesamt, n_hypothesen,"
            " aktualisiert) VALUES (1, 0, 1, ?)"
            " ON CONFLICT(id) DO UPDATE SET"
            "   n_hypothesen = versuchszaehler.n_hypothesen + 1,"
            "   aktualisiert = excluded.aktualisiert",
            (dt.datetime.now(dt.UTC).isoformat(),),
        )
    return f"{hyp_id} erfasst (Status: offen)."


def historientest(hyp_id: str, faktor: pd.DataFrame, renditen: pd.DataFrame,
                  *, store: ShadowStore | None = None,
                  horizont: int = 5) -> dict:
    """Billiger Filter auf vorhandenen Daten.

    Was auf mehreren Jahren keinen Tages-IC mit |t| > 2 zeigt, bindet keine
    Vorwaertszeit. Der Test ist bewusst grosszuegig - er soll aussortieren,
    nicht bestaetigen.

    **Der t-Wert ist um die Ueberlappung korrigiert (§G12).** Bis zum
    22.08.2026 war er es nicht - und diese Funktion war die letzte Stelle
    im Projekt, an der ein unkorrigierter Wert einen STATUS setzte:

        status = "im_test" if abs(t) > 2 else "widerlegt"

    Bei einem 5-Tage-Fenster teilen benachbarte Tage vier Fuenftel ihres
    Renditefensters; die Fehlalarmquote liegt dann bei **39,5 %** statt
    5 %. Vier von zehn Urteilen waren damit Rauschen - in beide
    Richtungen: eine brauchbare Idee verworfen oder eine wertlose in den
    teuren Vorwaertstest geschickt.

    Verschaerfend kam hinzu, dass `horizont` zwar in der Signatur stand,
    im Rumpf aber **an keiner Stelle** benutzt wurde. Eine Signatur, die
    eine Korrektur verspricht, die es nicht gibt, ist schlimmer als gar
    keine - sie beruhigt beim Lesen.

    Args:
        faktor: DataFrame (Zeilen = Tage, Spalten = Symbole) mit dem Faktorwert.
        renditen: gleiche Form, mit der Vorwaertsrendite ueber `horizont`.
        horizont: Laenge des Renditefensters in Handelstagen. Steuert die
            Ueberlappungskorrektur. 1 = keine Ueberlappung.

    Returns:
        `t` ist der KORRIGIERTE Wert und die Grundlage des Status.
        `t_roh` steht zum Vergleich daneben - nie zitieren (§G12).
        Ist die Reihe zu kurz fuer den Schaetzer, ist `t` NaN und der
        Status bleibt `offen`; der rohe Wert springt bewusst nicht ein.
    """
    from . import statistik

    s = store or ShadowStore()
    gemeinsam = faktor.index.intersection(renditen.index)
    paare = []
    for tag in gemeinsam:
        f = faktor.loc[tag].dropna()
        r = renditen.loc[tag].dropna()
        idx = f.index.intersection(r.index)
        if len(idx) < 10 or f.loc[idx].nunique() < 2:
            continue
        paare.append((tag, f.loc[idx].corr(r.loc[idx], method="spearman")))

    # Chronologisch sortieren: `newey_west_t` liest die Autokorrelation aus
    # der REIHENFOLGE. Eine umsortierte Reihe ergaebe keinen ungenauen,
    # sondern einen bedeutungslosen Wert.
    paare.sort(key=lambda x: x[0])
    ics = pd.Series([x for _, x in paare if np.isfinite(x)])
    if len(ics) < 3:
        return {"n_tage": len(ics), "ic": np.nan, "t": np.nan,
                "t_roh": np.nan, "horizont": horizont}

    t_roh = float(ics.mean() / (ics.std(ddof=1) / np.sqrt(len(ics))))
    if horizont > 1:
        t_korr, aufbl = statistik.newey_west_t(ics.to_numpy(), lag=horizont - 1)
    else:
        t_korr, aufbl = t_roh, 1.0

    erg = {"n_tage": int(len(ics)), "ic": round(float(ics.mean()), 5),
           "t_roh": round(t_roh, 2), "horizont": horizont}
    if np.isfinite(t_korr):
        erg |= {"t": round(float(t_korr), 2), "aufblaehung": round(float(aufbl), 2)}
    else:
        # Kein t-Wert ist eine Aussage, kein Formatierungsproblem. Der rohe
        # waere hier die optimistischste aller Antworten und saehe wie ein
        # Ergebnis aus (§G14: 14,57 gegen 5,30 roh bei 8 Tagen).
        erg |= {"t": np.nan, "aufblaehung": np.nan,
                "hinweis": f"{len(ics)} Tage sind fuer einen "
                           f"{horizont}-Tage-Horizont zu wenig - kein t-Wert"}

    # Ohne gueltigen t-Wert wird NICHT geurteilt. `offen` heisst "noch
    # nicht entschieden" und ist ausdruecklich kein Bestehen - dieselbe
    # Drei-Zustaende-Regel wie in shadow_eval.kriterien_pruefen.
    if not np.isfinite(erg["t"]):
        status = "offen"
    else:
        status = "im_test" if abs(erg["t"]) > 2 else "widerlegt"

    with s._conn() as c:
        c.execute(
            "UPDATE hypothesen SET hist_ic=?, hist_t=?, status=?"
            " WHERE hyp_id=?",
            (erg["ic"], erg["t"] if np.isfinite(erg["t"]) else None,
             status, hyp_id),
        )
    return erg


def zerfallstest(hyp_id: str, faktor: pd.DataFrame, renditen: pd.DataFrame,
                 *, store: ShadowStore | None = None) -> dict:
    """Misst den IC getrennt VOR und NACH dem Veroeffentlichungsdatum.

    Faellt der Effekt nach der Veroeffentlichung deutlich ab, ist das der
    Zerfall aus McLean & Pontiff (~58 % im Mittel) - die Anomalie wurde
    wegarbitriert, und ein Vorwaertstest waere verlorene Zeit.
    """
    s = store or ShadowStore()
    with s._conn() as c:
        row = c.execute("SELECT veroeffentlicht FROM hypothesen WHERE hyp_id=?",
                        (hyp_id,)).fetchone()
    if not row or not row["veroeffentlicht"]:
        return {"hinweis": "kein Veroeffentlichungsdatum hinterlegt"}

    grenze = pd.Timestamp(row["veroeffentlicht"], tz="UTC")
    idx = pd.DatetimeIndex(faktor.index)
    if idx.tz is None:
        idx = idx.tz_localize("UTC")

    def _ic(maske):
        f, r = faktor[maske], renditen[maske]
        if f.empty:
            return np.nan
        vals = []
        for tag in f.index.intersection(r.index):
            a, b = f.loc[tag].dropna(), r.loc[tag].dropna()
            i = a.index.intersection(b.index)
            if len(i) >= 10 and a.loc[i].nunique() > 1:
                vals.append(a.loc[i].corr(b.loc[i], method="spearman"))
        vals = [v for v in vals if np.isfinite(v)]
        return round(float(np.mean(vals)), 5) if vals else np.nan

    vor, nach = _ic(idx < grenze), _ic(idx >= grenze)
    with s._conn() as c:
        c.execute(
            "UPDATE hypothesen SET hist_ic_vor_veroeff=?, hist_ic_nach_veroeff=?"
            " WHERE hyp_id=?", (vor, nach, hyp_id))

    zerfall = None
    if np.isfinite(vor) and np.isfinite(nach) and vor != 0:
        zerfall = round(1 - nach / vor, 3)
    return {"ic_vor": vor, "ic_nach": nach, "zerfall_anteil": zerfall}


def bericht(store: ShadowStore | None = None) -> str:
    s = store or ShadowStore()
    df = s.table("hypothesen")
    L = ["=" * 78, "  HYPOTHESENREGISTER", "=" * 78]
    if df.empty:
        L += ["  Noch keine Hypothesen erfasst.", "",
              "  Erfassen:",
              "    python scripts/17_shadow_report.py --hypothese-neu ..."]
        return "\n".join(L)

    for _, h in df.iterrows():
        L.append(f"\n  {h['hyp_id']}  [{h['status']}]")
        L.append(f"    {h['behauptung']}")
        L.append(f"    Quelle: {h['quelle']} ({h['quelle_typ']}, "
                 f"Prior: {QUELLEN_TYPEN.get(h['quelle_typ'], '?')})")
        if h["veroeffentlicht"]:
            L.append(f"    Veroeffentlicht: {h['veroeffentlicht']}")
        if pd.notna(h["hist_ic"]):
            L.append(f"    Historie : IC {h['hist_ic']}  t={h['hist_t']}")
        if pd.notna(h["hist_ic_vor_veroeff"]):
            L.append(f"    Zerfall  : IC vor {h['hist_ic_vor_veroeff']} -> "
                     f"nach {h['hist_ic_nach_veroeff']}")
        if pd.notna(h["fwd_ic"]):
            L.append(f"    Vorwaerts: IC {h['fwd_ic']}  t={h['fwd_t']}  "
                     f"({h['fwd_n_tage']} Tage)")
    L += ["", "-" * 78,
          "  Erinnerung: ~65 % publizierter Anomalien halten der Nachpruefung",
          "  nicht stand, und publizierte Effekte verlieren im Mittel ~58 %",
          "  ihrer Wirkung. Der Vorwaertstest ist die einzige Bestaetigung,",
          "  die zaehlt."]
    return "\n".join(L)
