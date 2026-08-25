"""Kandidatenregister: die Zwischenstufe zwischen Historienlauf und Schatten.

**Wozu (`docs/UMBAUPLAN.md` Schritt 5).** Was den Lernlauf uebersteht,
darf laut Umbauplan NICHT direkt in die Flotte. Grund: Der Lernlauf kann
eine Idee nur VERWERFEN, nie ABNEHMEN (Survivorship, fehlender
Nachrichtenfaktor - siehe Kopf von `scripts/32_lernlauf.py`). Ohne eine
Voranmeldung mit Datum und Variantenzahl waere ein spaeterer Treffer im
Schatten nicht von einer nachtraeglichen Erzaehlung zu unterscheiden
(`docs/BEFUNDE.md` §J Regel 2 - dasselbe Prinzip, das `fleet.anmelden`
fuer die Flotte selbst durchsetzt).

`n_varianten_getestet` ist Pflicht, nicht optional: Ein Kandidat, der aus
14 gleichzeitig geprueften Varianten ausgewaehlt wurde, hat 14 Versuche
hinter sich, nicht einen - das Zufallsmaximum steigt mit `sqrt(2 ln N)`
(`docs/BEFUNDE.md` §B2).

**Der Weg, verbindlich (Umbauplan Schritt 6):**

    1. Historienlauf   (Minuten)   darf VERWERFEN
    2. Kandidatenregister          Voranmeldung mit Datum und Variantenzahl  <- hier
    3. Schattenbot     (Wochen)    einzige survivorship-freie Messung
    4. Abnahme                     nach BETRIEBSPLAN §3.3
    5. Live                        mit Dienstneustart und Regelabgleich

Dieses Modul deckt Schritt 2 ab. Es registriert und verfolgt Kandidaten -
es meldet KEINEN Flottenbot an (das bleibt `fleet.anmelden`, eine
bewusst getrennte, spaetere Entscheidung) und importiert `trading.py`
nicht.
"""

from __future__ import annotations

import datetime as dt

import pandas as pd

from .lernlauf_store import LernlaufStore

STATUS = {"gefunden", "im_schatten", "abgenommen", "verworfen"}
"""Die vier Zustaende aus `docs/UMBAUPLAN.md` Schritt 5 - wortgleich."""

# Erlaubte Uebergaenge. Ein Kandidat kann nicht von "verworfen" wieder
# "abgenommen" werden, ohne neu angemeldet zu werden - das waere genau
# die nachtraegliche Erzaehlung, gegen die die Voranmeldung schuetzt.
_UEBERGAENGE: dict[str, set[str]] = {
    "gefunden": {"im_schatten", "verworfen"},
    "im_schatten": {"abgenommen", "verworfen"},
    "abgenommen": set(),
    "verworfen": set(),
}


def _store(store: LernlaufStore | None) -> LernlaufStore:
    return store or LernlaufStore()


def anmelden(kandidat_id: str, *, achse: str, wert: str, hypothese: str,
            n_varianten_getestet: int, code_version: str | None = None,
            store: LernlaufStore | None = None) -> str:
    """Meldet einen neuen Kandidaten an. Status startet bei 'gefunden'.

    Mehrfachaufruf mit derselben `kandidat_id` ist ein Fehler (anders als
    `fleet.anmelden`, das idempotent still ueberschreibt) - eine
    Voranmeldung, die sich selbst ueberschreiben liesse, waere keine.
    """
    if not hypothese or not hypothese.strip():
        raise ValueError("Eine Voranmeldung ohne Hypothese ist keine (§J Regel 2).")
    if n_varianten_getestet < 1:
        raise ValueError("n_varianten_getestet muss mindestens 1 sein.")

    s = _store(store)
    with s._conn() as c:
        vorhanden = c.execute(
            "SELECT 1 FROM kandidaten WHERE kandidat_id=?", (kandidat_id,)
        ).fetchone()
        if vorhanden:
            raise ValueError(
                f"{kandidat_id!r} ist bereits angemeldet. Eine Voranmeldung ist "
                "nicht ueberschreibbar - `ergebnis_eintragen`/`status_setzen` nutzen."
            )
        jetzt = dt.datetime.now(dt.UTC).isoformat()
        c.execute(
            "INSERT INTO kandidaten (kandidat_id, achse, wert, hypothese,"
            " entdeckt_am, code_version, n_varianten_getestet, status,"
            " aktualisiert_am) VALUES (?,?,?,?,?,?,?,?,?)",
            (kandidat_id, achse, wert, hypothese, jetzt, code_version,
             int(n_varianten_getestet), "gefunden", jetzt),
        )
    return f"{kandidat_id} angemeldet (achse={achse}, wert={wert}, status=gefunden)."


def ergebnis_eintragen(kandidat_id: str, *, hist_effekt_pro_tag: float | None = None,
                       hist_t: float | None = None, hist_fenster: int | None = None,
                       walkforward_t: float | None = None,
                       store: LernlaufStore | None = None) -> None:
    """Traegt Historienlauf-Kennzahlen zu einem bereits angemeldeten Kandidaten nach."""
    s = _store(store)
    with s._conn() as c:
        row = c.execute(
            "SELECT 1 FROM kandidaten WHERE kandidat_id=?", (kandidat_id,)
        ).fetchone()
        if not row:
            raise ValueError(f"{kandidat_id!r} ist nicht angemeldet.")
        felder, werte = [], []
        for name, wert in [("hist_effekt_pro_tag", hist_effekt_pro_tag),
                           ("hist_t", hist_t), ("hist_fenster", hist_fenster),
                           ("walkforward_t", walkforward_t)]:
            if wert is not None:
                felder.append(f"{name}=?")
                werte.append(wert)
        if not felder:
            return
        felder.append("aktualisiert_am=?")
        werte.append(dt.datetime.now(dt.UTC).isoformat())
        werte.append(kandidat_id)
        c.execute(f"UPDATE kandidaten SET {', '.join(felder)} WHERE kandidat_id=?",
                 tuple(werte))


def status_setzen(kandidat_id: str, status: str, *,
                  store: LernlaufStore | None = None) -> str:
    """Bewegt einen Kandidaten entlang des Vertrags aus Schritt 6.

    Nur die in `_UEBERGAENGE` erlaubten Schritte gehen durch - eine
    Statusaenderung, die den Weg ueberspringt (z. B. direkt 'gefunden' ->
    'abgenommen'), wuerde Stufe 3 (Schattenbot) und Stufe 4 (Abnahme nach
    BETRIEBSPLAN §3.3) umgehen, genau das, was `docs/UMBAUPLAN.md`
    Schritt 6 ausdruecklich verbietet.
    """
    if status not in STATUS:
        raise ValueError(f"Unbekannter Status {status!r}. Erlaubt: {sorted(STATUS)}")

    s = _store(store)
    with s._conn() as c:
        row = c.execute(
            "SELECT status FROM kandidaten WHERE kandidat_id=?", (kandidat_id,)
        ).fetchone()
        if not row:
            raise ValueError(f"{kandidat_id!r} ist nicht angemeldet.")
        aktuell = row["status"]
        if status not in _UEBERGAENGE.get(aktuell, set()) and status != aktuell:
            raise ValueError(
                f"Uebergang {aktuell!r} -> {status!r} nicht erlaubt. Erlaubt ab "
                f"{aktuell!r}: {sorted(_UEBERGAENGE.get(aktuell, set())) or '(nichts, Endzustand)'}"
            )
        c.execute(
            "UPDATE kandidaten SET status=?, aktualisiert_am=? WHERE kandidat_id=?",
            (status, dt.datetime.now(dt.UTC).isoformat(), kandidat_id),
        )
    return f"{kandidat_id}: {aktuell} -> {status}"


def liste(store: LernlaufStore | None = None) -> pd.DataFrame:
    return _store(store).table("kandidaten").sort_values("entdeckt_am")


def bericht(store: LernlaufStore | None = None) -> str:
    df = liste(store)
    L = ["=" * 78, "  KANDIDATENREGISTER", "=" * 78]
    if df.empty:
        L.append("  Noch kein Kandidat angemeldet.")
        return "\n".join(L)
    for _, r in df.iterrows():
        L.append(f"  {r['kandidat_id']:<28} [{r['status']:<12}] "
                 f"achse={r['achse']}={r['wert']}  "
                 f"Varianten getestet: {r['n_varianten_getestet']}")
        L.append(f"      {r['hypothese']}")
        # Jedes Feld einzeln pruefen statt nur `hist_t`: Ein Kandidat kann
        # z.B. nur einen t-Wert tragen, ohne dass `hist_effekt_pro_tag`
        # gesetzt ist (`ergebnis_eintragen` schreibt Felder unabhaengig
        # voneinander). Ein Format-String auf einem ungeprueften Feld
        # stuerzte hier am 25.08.2026 mit TypeError ab, sobald `hist_t`
        # gesetzt war, aber `hist_effekt_pro_tag` fehlte (K02_trailing_15j).
        teile = []
        if pd.notna(r.get("hist_effekt_pro_tag")):
            teile.append(f"{r['hist_effekt_pro_tag']:+.4%}/Tag")
        if pd.notna(r.get("hist_t")):
            teile.append(f"t={r['hist_t']}")
        if pd.notna(r.get("hist_fenster")):
            teile.append(f"Fenster={r['hist_fenster']} Jahre")
        if teile:
            L.append("      hist: " + "  ".join(teile))
    return "\n".join(L)
