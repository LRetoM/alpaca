"""Regressionstest zu BEFUNDE §G55 (11.09.2026).

**Der Vorfall.** `daemon._maybe_evaluate_outcomes` laedt Kursdaten nur
fuer eine begrenzte Zahl von Symbolen. Die Vorrangliste, die Symbole mit
offenen Ergebnissen nach vorn ziehen sollte, verglich ueber
`decision_id` allein - nicht ueber das Paar aus Entscheidung und
Horizont. Eine Entscheidung mit gefuelltem 1- und 3-Tage-Wert galt damit
als erledigt, auch wenn ihr 5-Tage-Wert fehlte. Genau das ist der
Normalfall, denn am Tag der Bewertung sind die kurzen Horizonte
verfuegbar und der lange nicht.

Der Rest der Liste war alphabetisch sortiert. Gemessen am 11.09.2026:
1.031 Symbole in `decisions`, Schnitt bei `DPZ`, 731 Symbole (71 %)
unerreichbar. 277 von 685 Live-Entscheidungen ohne 5-Tage-Ergebnis,
davon 128 dauerhaft.

**Es war der zweite Anlauf.** Der erste Fehler (`sorted(...)[:200]`,
alles ab "T" fiel weg) stand bereits als Kommentar im Quelltext. Die
Reparatur hob die Grenze auf 300 und fuegte die Vorrangliste hinzu, die
die falsche Schluesselgroesse verglich. Deshalb dieser Test: Ein Fehler,
der zweimal auftrat, darf nicht ein drittes Mal zurueckkommen.
"""

from __future__ import annotations

import pandas as pd

from alpaca_bot.daemon import HORIZONTE_LIVE, MAX_SYMBOLE_JE_LAUF, Daemon


def _entscheidungen(symbole: list[str]) -> pd.DataFrame:
    return pd.DataFrame(
        [{"decision_id": f"d{i}", "symbol": s} for i, s in enumerate(symbole)]
    )


def _ergebnisse(paare: list[tuple[str, int]]) -> pd.DataFrame:
    if not paare:
        return pd.DataFrame(columns=["decision_id", "horizon", "fwd_return"])
    return pd.DataFrame(
        [{"decision_id": d, "horizon": h, "fwd_return": 0.0} for d, h in paare]
    )


def _auswahl_vor_der_reparatur(decisions, outcomes, grenze=300):
    """Die Logik, wie sie bis zum 11.09.2026 in `daemon.py` stand.

    Steht hier, damit die Tests nachweislich TRENNEN: Ein Test, den auch
    der kaputte Code besteht, sichert nichts. Wird nicht produktiv
    benutzt.
    """
    fehlend = decisions[~decisions["decision_id"].isin(outcomes["decision_id"])]
    vorrang = list(dict.fromkeys(fehlend["symbol"].dropna()))
    rest = [x for x in sorted(decisions["symbol"].dropna().unique())
            if x not in set(vorrang)]
    return (vorrang + rest)[:grenze]


def test_teilweise_bewertete_entscheidung_bleibt_offen():
    """Der Kern von §G55: 1 und 3 gefuellt, 5 fehlt -> weiter vorrangig.

    Aufbau wie im echten Vorfall: viele Symbole, und das eine mit dem
    offenen 5-Tage-Horizont steht alphabetisch hinten. Vor der Reparatur
    galt es als erledigt, weil seine `decision_id` in `outcomes` stand -
    und fiel deshalb hinter die Grenze.
    """
    symbole = [f"A{i:04d}" for i in range(400)] + ["ZZZZ"]
    dec = _entscheidungen(symbole)
    # Nur ZZZZ (letzter Index) hat ueberhaupt Ergebnisse - aber nur die
    # kurzen Horizonte. Alle anderen sind voll bewertet.
    paare = [(f"d{i}", h) for i in range(400) for h in HORIZONTE_LIVE]
    paare += [("d400", 1), ("d400", 3)]          # 5 fehlt
    out = _ergebnisse(paare)

    syms = Daemon._symbole_mit_offenen_horizonten(dec, out, HORIZONTE_LIVE)

    assert syms[0] == "ZZZZ", (
        "Ein Symbol mit offenem 5-Tage-Horizont muss vorne stehen - "
        "genau das hat §G55 uebersehen."
    )

    # Nachweis, dass dieser Test trennt: der alte Code faellt durch.
    assert "ZZZZ" not in _auswahl_vor_der_reparatur(dec, out), (
        "Dieser Test wuerde auch die kaputte Fassung bestehen - dann "
        "sichert er nichts."
    )


def test_vollstaendig_bewertete_entscheidung_verliert_den_vorrang():
    """Die Gegenprobe: alle Horizonte da -> nicht mehr vorrangig."""
    dec = _entscheidungen(["AAAA", "ZZZZ"])
    out = _ergebnisse([("d1", h) for h in HORIZONTE_LIVE])  # ZZZZ fertig

    syms = Daemon._symbole_mit_offenen_horizonten(dec, out, HORIZONTE_LIVE)

    assert syms[0] == "AAAA", "Das offene Symbol gehoert vor das fertige."
    assert "ZZZZ" in syms, "Fertige Symbole duerfen trotzdem mitlaufen."


def test_kein_alphabetischer_schnitt_bei_vielen_symbolen():
    """Der urspruengliche Fehler: 1.031 Symbole, Schnitt bei `DPZ`.

    400 Symbole mit OFFENEM Horizont muessen vollstaendig durchkommen.
    Mit der alten 300er-Grenze und alphabetischem `rest` waere hier
    rund ein Viertel verschwunden - und zwar immer dasselbe Viertel.
    """
    symbole = [f"S{i:04d}" for i in range(400)]
    dec = _entscheidungen(symbole)
    out = _ergebnisse([])       # nichts bewertet, alle offen

    syms = Daemon._symbole_mit_offenen_horizonten(dec, out, HORIZONTE_LIVE)

    fehlend = set(symbole) - set(syms)
    assert not fehlend, (
        f"{len(fehlend)} Symbole mit offenem Horizont wurden nie geladen, "
        f"darunter {sorted(fehlend)[:5]} - das ist §G55."
    )


def test_obergrenze_schneidet_die_fertigen_zuerst():
    """Greift die Obergrenze doch, darf sie nur Fertiges treffen.

    Eine Grenze ist noetig, damit ein Datenabruf nicht unbegrenzt
    waechst. Sie darf aber nie ein Symbol kosten, dessen Ergebnis noch
    aussteht - sonst ist der Fehler nur verschoben.
    """
    n_offen = 50
    n_fertig = MAX_SYMBOLE_JE_LAUF + 200
    offen = [f"OFFEN{i:05d}" for i in range(n_offen)]
    fertig = [f"FERTIG{i:05d}" for i in range(n_fertig)]

    dec = _entscheidungen(offen + fertig)
    out = _ergebnisse(
        [(f"d{i}", h)
         for i in range(n_offen, n_offen + n_fertig)
         for h in HORIZONTE_LIVE]
    )

    syms = Daemon._symbole_mit_offenen_horizonten(dec, out, HORIZONTE_LIVE)

    assert len(syms) <= MAX_SYMBOLE_JE_LAUF, "Die Obergrenze muss greifen."
    assert set(offen).issubset(set(syms)), (
        "Die Obergrenze hat ein Symbol mit offenem Horizont gekostet."
    )


def test_leere_ergebnistabelle_haelt_alles_offen():
    """Erster Lauf auf einem frischen Journal: nichts ist bewertet."""
    dec = _entscheidungen(["AAAA", "BBBB", "CCCC"])

    syms = Daemon._symbole_mit_offenen_horizonten(
        dec, pd.DataFrame(columns=["decision_id", "horizon"]), HORIZONTE_LIVE
    )

    assert set(syms) == {"AAAA", "BBBB", "CCCC"}


def test_leere_entscheidungen_ergeben_leere_liste():
    """Darf nicht werfen - der Daemon laeuft auch am ersten Tag."""
    leer = pd.DataFrame(columns=["decision_id", "symbol"])
    assert Daemon._symbole_mit_offenen_horizonten(
        leer, pd.DataFrame(columns=["decision_id", "horizon"]), HORIZONTE_LIVE
    ) == []
