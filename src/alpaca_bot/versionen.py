"""Ergebnisse nach Codeversion aufschluesseln - Grundlage jeder Rueckrollung.

**Die Frage, die dieses Modul beantwortet:** Wenn ein Ergebnis schlechter
wird - lag es an einer Aenderung im Code oder am Markt? Ohne diese
Trennung besteht die Gefahr, einen Fehler dauerhaft zu etablieren: Man
nimmt an, jede Aenderung sei eine Verbesserung, und merkt nie, dass ab
einem bestimmten Commit alles schlechter lief.

**Warum das ohne Versionsangabe unmoeglich ist**, zeigt ein realer Fall
aus diesem Projekt: `shadow.code_version()` bestimmte den Git-Commit mit
`cwd=DATA_DIR.parent`. Solange die Datenbanken im Projektordner lagen,
stimmte das zufaellig. Nach dem Umzug nach ~/Library/Application Support
(30.07.2026, TCC-Dateischutz) zeigte der Pfad auf ein Verzeichnis ohne
Git - die Funktion lieferte ab da stumm 'unbekannt'. Gemessen am
15.08.2026: **8.278 von 12.516 Vorhersagen ohne Version**, zwei Drittel
der Daten also ohne Zuordnung. Der Fehler hat sich nie gemeldet.

**Die wichtigste Einschraenkung, gleich vorweg:** Ein Versionsvergleich
ist KEIN kontrollierter Versuch. Verschiedene Versionen liefen in
verschiedenen Marktphasen - der Unterschied kann vollstaendig daher
ruehren. Dieses Modul liefert deshalb bewusst keine Bewertung, sondern
nur die Aufschluesselung samt Marktvergleich im selben Zeitraum. Wer
daraus eine Rueckrollung ableitet, braucht zusaetzlich einen Grund im
Code, nicht nur eine Zahl.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .journal import Journal


def laeufe_je_version(journal: Journal | None = None,
                      script: str = "live_trade") -> pd.DataFrame:
    """Welche Version lief wann, und was hat sie getan?"""
    j = journal or Journal()
    runs = j.table("runs", "script = ?", (script,))
    if runs.empty:
        return pd.DataFrame()

    runs = runs.copy()
    runs["started_at"] = pd.to_datetime(runs["started_at"], format="mixed",
                                        utc=True, errors="coerce")
    runs["code_version"] = runs["code_version"].fillna("unbekannt")

    g = runs.groupby("code_version").agg(
        laeufe=("run_id", "size"),
        von=("started_at", "min"),
        bis=("started_at", "max"),
        fehlgeschlagen=("status", lambda s: int((s == "failed").sum())),
    )
    return g.sort_values("von")


def entscheidungen_je_version(journal: Journal | None = None,
                              horizont: int = 5,
                              script: str = "live_trade") -> pd.DataFrame:
    """Ergebnis der Entscheidungen, aufgeschluesselt nach Codeversion.

    `n_tage` steht bewusst mit in der Tabelle: Eine Version, die nur an
    zwei Handelstagen lief, ist mit einer ueber zwanzig Tagen nicht
    vergleichbar - egal wie viele Entscheidungen dabei herauskamen
    (siehe die Ueberlappungsfalle in docs/BEFUNDE.md §B1).
    """
    j = journal or Journal()
    sql = (
        "SELECT r.code_version, d.decision_id, d.ts, d.symbol, d.action,"
        "       d.conviction, o.fwd_return"
        " FROM decisions d"
        " JOIN runs r ON d.run_id = r.run_id"
        " LEFT JOIN outcomes o ON d.decision_id = o.decision_id"
        "        AND o.horizon = ?"
        " WHERE r.script = ?"
    )
    with j._conn() as c:
        df = pd.read_sql_query(sql, c, params=(horizont, script))
    if df.empty:
        return pd.DataFrame()

    df["code_version"] = df["code_version"].fillna("unbekannt")
    df["tag"] = pd.to_datetime(df["ts"], format="mixed", utc=True,
                               errors="coerce").dt.tz_localize(None).dt.normalize()

    g = df.groupby("code_version").agg(
        entscheidungen=("decision_id", "size"),
        n_tage=("tag", "nunique"),
        bewertet=("fwd_return", "count"),
        mittel=("fwd_return", "mean"),
        median=("fwd_return", "median"),
        trefferquote=("fwd_return", lambda s: (s > 0).mean() if s.notna().any() else np.nan),
        von=("tag", "min"),
        bis=("tag", "max"),
    )
    return g.sort_values("von").round(4)


def markt_je_version(journal: Journal | None = None,
                     script: str = "live_trade") -> pd.DataFrame:
    """Wie lief der MARKT waehrend jeder Version?

    Die entscheidende Gegenprobe. Sieht eine Version besser aus, waehrend
    der Markt in ihrem Zeitraum stieg, ist der Unterschied kein Befund
    ueber den Code. Ohne diese Spalte verwechselt man Marktphasen mit
    Verbesserungen - und rollt womoeglich eine gute Aenderung zurueck,
    nur weil danach ein schlechter Monat kam.
    """
    from . import data

    v = laeufe_je_version(journal, script)
    if v.empty:
        return pd.DataFrame()

    spanne = int((v["bis"].max() - v["von"].min()).days) + 10
    spy = data.get_bars(["SPY"], "1D", lookback_days=max(spanne, 30))
    if spy.empty:
        return v
    s = spy.xs("SPY", level="symbol")["close"]
    s.index = pd.DatetimeIndex(s.index).tz_localize(None).normalize()

    zeilen = []
    for version, r in v.iterrows():
        a = pd.Timestamp(r["von"]).tz_localize(None).normalize()
        b = pd.Timestamp(r["bis"]).tz_localize(None).normalize()
        fenster = s.loc[a:b]
        markt = (float(fenster.iloc[-1] / fenster.iloc[0] - 1)
                 if len(fenster) >= 2 else np.nan)
        zeilen.append({"code_version": version, "markt_spy": markt})
    return v.join(pd.DataFrame(zeilen).set_index("code_version")).round(4)


def bericht(journal: Journal | None = None, horizont: int = 5) -> str:
    """Lesbare Aufschluesselung - fuer den Tages-/Monatsbericht."""
    L = ["=" * 78, "  ERGEBNISSE NACH CODEVERSION", "=" * 78, ""]

    lauf = markt_je_version(journal)
    if lauf.empty:
        L.append("  Noch keine Laeufe mit Versionsangabe.")
        L.append("  (Vor dem 15.08.2026 wurde die Version nicht erfasst.)")
        return "\n".join(L)

    L.append("  Laufzeit und Marktumfeld je Version:")
    zeig = lauf.copy()
    for sp in ("von", "bis"):
        if sp in zeig:
            zeig[sp] = pd.to_datetime(zeig[sp]).dt.strftime("%d.%m")
    L.append("  " + zeig.to_string().replace("\n", "\n  "))

    erg = entscheidungen_je_version(journal, horizont)
    if not erg.empty:
        L += ["", f"  Entscheidungsergebnis (Horizont {horizont} Tage):"]
        z = erg.copy()
        for sp in ("von", "bis"):
            if sp in z:
                z[sp] = pd.to_datetime(z[sp]).dt.strftime("%d.%m")
        L.append("  " + z.to_string().replace("\n", "\n  "))

    L += [
        "",
        "-" * 78,
        "  LESEHINWEIS - das ist KEIN kontrollierter Versuch.",
        "",
        "  Verschiedene Versionen liefen in verschiedenen Marktphasen. Die",
        "  Spalte `markt_spy` zeigt, wie der Gesamtmarkt im jeweiligen",
        "  Zeitraum lief - ist der Unterschied zwischen zwei Versionen",
        "  kleiner als der Unterschied ihrer Marktphasen, sagt die Zahl",
        "  ueber den Code nichts aus.",
        "",
        "  Ebenso zaehlt `n_tage`, nicht die Zahl der Entscheidungen:",
        "  Entscheidungen desselben Tages sind nicht unabhaengig",
        "  (docs/BEFUNDE.md §B1).",
        "",
        "  Eine Rueckrollung braucht IMMER zusaetzlich einen Grund im Code -",
        "  eine Zahl allein reicht nie.",
    ]
    return "\n".join(L)
