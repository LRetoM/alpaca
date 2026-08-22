"""Panel, Lernkern und Fokus - die Lernschicht (22.08.2026).

Vier Fehler sind beim Bau dieser Schicht gefunden worden, jeder hat hier
seinen Test. Alle vier gehoeren zu derselben Familie wie BEFUNDE §G13:
**es stuerzt nichts ab, es kommt nur eine falsche oder leere Zahl heraus.**

1. `market` mit abweichenden Zeitstempeln (Mitternacht statt 04:00 UTC)
   liess `reindex` still ins Leere laufen -> drei Merkmale komplett NaN
   -> `dropna` verwarf das GESAMTE Panel. Ausgabe: "0 Zeilen".
2. Ein leeres Merkmal wurde stumm verschluckt, statt gemeldet zu werden.
3. `fokus` verglich jeden Bot gegen eine global gewaehlte Referenz statt
   gegen seine registrierte `basis_bot` - bei B04 waeren das drei
   geaenderte Achsen gewesen statt einer. Exakt der Fehler aus §G6.
4. `fokus` rechnete aus 13 Handelstagen ein "nie entscheidbar" hoch. Ein
   Effekt nahe null nach 13 Tagen heisst "noch nichts gemessen", nicht
   "nie". Eine glatte Zahl ohne Deckung (§G13).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from alpaca_bot import dataset


def _bars(n_sym=40, n_tage=600, autokorr=0.0, seed=3, tz="UTC"):
    """Panel-Rohdaten. `autokorr < 0` baut einen echten Umkehr-Effekt ein."""
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2021-01-01", periods=n_tage, tz=tz)
    teile = []
    for s in range(n_sym):
        e = rng.normal(0, 0.02, n_tage)
        r = np.zeros(n_tage)
        for t in range(1, n_tage):
            r[t] = autokorr * r[t - 1] + e[t]
        px = 100 * np.exp(np.cumsum(r))
        teile.append(pd.DataFrame(
            {"symbol": f"S{s:02d}", "timestamp": idx, "open": px,
             "high": px * 1.01, "low": px * 0.99, "close": px,
             "volume": rng.integers(1e6, 5e6, n_tage).astype(float)}))
    return pd.concat(teile).set_index(["symbol", "timestamp"]).sort_index()


class TestPanelGrundzusicherungen:
    """Was ein Panel garantieren muss, damit eine Auswertung gilt."""

    def test_handelstag_ist_die_beobachtung_nicht_die_zeile(self):
        """§B1. `n_tage` muss weit unter `len(X)` liegen - sonst zaehlt
        jemand Zeilen und nennt sie Beobachtungen."""
        p = dataset.baue_panel(_bars(), horizont=5, verbose=False)
        assert p.n_tage < len(p.X) / 10
        assert p.n_tage == p.tage.nunique()

    def test_keine_dienstspalten_in_den_merkmalen(self):
        """Ein durchgerutschtes `__tag` waere ein Datenleck: Das Modell
        lernt das Datum und sieht im Backtest hervorragend aus."""
        p = dataset.baue_panel(_bars(), horizont=5, verbose=False)
        assert not [c for c in p.X.columns if c.startswith("__")]
        for verboten in ("tag", "symbol", "date", "timestamp"):
            assert verboten not in p.X.columns

    def test_label_ist_ueberschuss_nicht_rohrendite(self):
        """§J Regel 4. Gegen den Tagesmedian gemessen muss die Basisrate
        bei 0,5 liegen - unabhaengig davon, ob der Markt stieg oder fiel.

        Ein Label auf Rohrenditen laege in einem Bullenmarkt deutlich
        darueber, und das Modell lernte "der Markt steigt" statt
        "dieses Symbol schlaegt die anderen"."""
        p = dataset.baue_panel(_bars(), horizont=5, verbose=False)
        assert abs(float(p.y.mean()) - 0.5) < 0.02

    def test_x_y_tage_bleiben_ausgerichtet(self):
        p = dataset.baue_panel(_bars(), horizont=5, verbose=False)
        assert len(p.X) == len(p.y) == len(p.tage) == len(p.symbole)
        assert p.X.index.equals(p.y.index)
        assert p.X.index.equals(p.tage.index)


class TestZeitzonenAngleichung:
    """FEHLER 1 (22.08.2026): market lief still ins Leere."""

    @pytest.mark.parametrize("markt_tz", [None, "UTC"])
    def test_markt_trifft_auch_bei_abweichender_zeitzone(self, markt_tz):
        """Alpaca-Bars tragen 04:00 UTC. Eine SPY-Reihe auf Mitternacht -
        egal ob mit oder ohne Zeitzone - muss trotzdem greifen."""
        bars = _bars(tz="UTC")
        tage = pd.DatetimeIndex(
            bars.index.get_level_values("timestamp").unique()).sort_values()
        # Bewusst NICHT die Bar-Stempel: auf Mitternacht normalisiert,
        # genau wie eine von Hand aufbereitete Reihe.
        m_idx = tage.tz_localize(None).normalize()
        if markt_tz:
            m_idx = m_idx.tz_localize(markt_tz)
        markt = pd.Series(np.linspace(400, 500, len(m_idx)), index=m_idx)

        p = dataset.baue_panel(bars, horizont=5, market=markt, verbose=False)

        assert len(p.X) > 0, "Panel leer - Marktreihe hat nicht gegriffen"
        for spalte in ("rel_strength_21", "mkt_ret_5"):
            assert spalte in p.X.columns
            assert p.X[spalte].notna().all()

    def test_ohne_markt_bleibt_das_panel_nutzbar(self):
        """Der Marktbezug ist optional - sein Fehlen darf nicht alles kippen."""
        p = dataset.baue_panel(_bars(), horizont=5, market=None, verbose=False)
        assert len(p.X) > 0
        assert "rel_strength_21" not in p.X.columns


class TestWaechterLeereMerkmale:
    """FEHLER 2: ein leeres Merkmal wurde stumm verschluckt."""

    def test_leeres_panel_nennt_die_schuldigen_merkmale(self):
        """Die Fehlermeldung muss sagen WELCHES Merkmal leer war.

        Ohne das sieht man nur '0 Zeilen' und sucht an der falschen
        Stelle - so geschehen beim ersten Lauf dieses Moduls."""
        bars = _bars(tz="UTC")
        # Marktreihe mit voellig fremdem Zeitraum -> trifft nie
        fremd = pd.Series(
            np.linspace(400, 500, 300),
            index=pd.bdate_range("1990-01-01", periods=300, tz="UTC"))

        with pytest.raises(ValueError) as e:
            dataset.baue_panel(bars, horizont=5, market=fremd, verbose=False)

        text = str(e.value)
        assert "leer" in text.lower()
        assert "rel_strength_21" in text or "mkt_ret_5" in text


class TestWalkForwardKeinLeck:
    """Die Schnittachse - der Unterschied zwischen Messung und Leck."""

    def test_kein_handelstag_liegt_in_train_und_test(self):
        """Der zentrale Test dieses Moduls.

        `ml.walk_forward_predict` schneidet nach Zeilenposition. Auf einem
        Panel legt das Zeilen DESSELBEN Handelstages in beide Fenster -
        das Modell hat den Testtag im Training gesehen. Hier wird nach
        Tagen geschnitten, und genau das wird hier nachgewiesen."""
        p = dataset.baue_panel(_bars(n_tage=700), horizont=5, verbose=False)
        erg = dataset.walk_forward_panel(p, n_falten=3, min_train_tage=300,
                                         verbose=False)
        assert not erg.falten.empty
        for _, f in erg.falten.iterrows():
            assert f["train_bis"] < f["test_von"], (
                f"Falte {f['falte']}: Training endet {f['train_bis']}, "
                f"Test beginnt {f['test_von']} - Ueberschneidung")

    def test_embargo_liegt_zwischen_den_fenstern(self):
        """Ein Label von Tag T benutzt die Kurse bis T+h. Ohne Embargo
        steckt genau diese Bewegung schon im Training."""
        h = 5
        p = dataset.baue_panel(_bars(n_tage=700), horizont=h, verbose=False)
        erg = dataset.walk_forward_panel(p, n_falten=3, min_train_tage=300,
                                         verbose=False)
        # Ueber Datumszeichenketten vergleichen: `falten` legt sie als
        # `str(...)[:10]` ab, die Tagesachse ist zeitzonenbehaftet. Ein
        # `np.datetime64`-Vergleich findet dort nie etwas.
        tage = [str(t)[:10] for t in np.sort(p.tage.unique())]
        for _, f in erg.falten.iterrows():
            i_train = tage.index(f["train_bis"])
            i_test = tage.index(f["test_von"])
            assert i_test - i_train >= h, (
                f"Falte {f['falte']}: Abstand {i_test - i_train} < Embargo {h}")

    def test_zu_wenige_tage_wirft_statt_zu_raten(self):
        """Lieber ein Abbruch als eine Falte aus drei Tagen."""
        p = dataset.baue_panel(_bars(n_tage=300), horizont=5, verbose=False)
        with pytest.raises(ValueError, match="Handelstage"):
            dataset.walk_forward_panel(p, n_falten=5, min_train_tage=1000,
                                       verbose=False)


class TestBewertungIstEhrlich:
    """Schweigt sie bei Rauschen, spricht sie bei Signal?"""

    def test_auf_rauschen_kein_befund(self):
        """Der Kontrollfall. Ohne ihn koennte die Kette pauschal Befunde
        melden und in allen anderen Tests richtig aussehen."""
        p = dataset.baue_panel(_bars(n_tage=700, autokorr=0.0, seed=11),
                               horizont=5, verbose=False)
        erg = dataset.walk_forward_panel(p, n_falten=3, min_train_tage=300,
                                         verbose=False)
        g = dataset.guete(erg.vorhersagen, erg.tatsaechlich, erg.tage,
                          name="rauschen", horizont=5, schwelle=2.85)
        assert not g.befund, f"Befund auf reinem Rauschen: t={g.t:.2f}"

    def test_starkes_signal_wird_gefunden(self):
        """Die Gegenprobe. Eine Kette, die nie anschlaegt, ist nicht
        streng, sondern kaputt."""
        p = dataset.baue_panel(_bars(n_tage=700, autokorr=-0.35, seed=11),
                               horizont=5, verbose=False)
        erg = dataset.walk_forward_panel(p, n_falten=3, min_train_tage=300,
                                         verbose=False)
        g = dataset.guete(erg.vorhersagen, erg.tatsaechlich, erg.tage,
                          name="signal", horizont=5, schwelle=2.85)
        assert g.ic > 0
        assert g.befund, f"starkes Signal nicht gefunden: t={g.t:.2f}"

    def test_korrektur_senkt_den_t_wert_bei_horizont_ueber_eins(self):
        """§G12. Bei 5-Tage-Fenstern muss `t` unter `t_roh` liegen -
        gemessene Aufblaehung im Projekt: 1,62x."""
        p = dataset.baue_panel(_bars(n_tage=700, autokorr=-0.35, seed=11),
                               horizont=5, verbose=False)
        erg = dataset.walk_forward_panel(p, n_falten=3, min_train_tage=300,
                                         verbose=False)
        g = dataset.guete(erg.vorhersagen, erg.tatsaechlich, erg.tage,
                          name="x", horizont=5, schwelle=2.85)
        assert abs(g.t) < abs(g.t_roh)
        assert g.aufblaehung > 1.0

    def test_bericht_nennt_den_rohen_wert_als_nicht_zitierfaehig(self):
        """Der rohe t-Wert steht in der Tabelle. Wer ihn dort sieht, muss
        im selben Blick lesen, dass er nicht zitiert wird (§G14)."""
        g = dataset.Guete("x", 100, 0.01, 1.0, 1.6, 1.6, 0.1, 1.0, 5, 2.85)
        text = dataset.vergleichsbericht([g])
        assert "NICHT zitiert" in text
        assert "39,5" in text


class TestFokusRechnetEhrlich:
    """FEHLER 3 und 4."""

    def test_unter_zwanzig_tagen_kein_urteil(self):
        """FEHLER 4. Aus 13 Handelstagen darf kein 'nie' werden.

        `noetige_gruppen` rechnet mit dem gemessenen Effekt. Ist der
        selbst noch Rauschen, ist die Hochrechnung es auch - sie liefert
        aber eine glatte Zahl mit Datum (§G13)."""
        from alpaca_bot import fokus

        f = fokus.Frage("test", "flotte", effekt=0.000001, streuung=0.01,
                        tage_vorhanden=13, schwelle=2.85)
        assert f.zu_frueh
        assert not f.tot, "13 Tage duerfen kein 'nie entscheidbar' tragen"
        assert "?" in f.zeile() and "nie" not in f.zeile()

    def test_ab_zwanzig_tagen_wird_geurteilt(self):
        from alpaca_bot import fokus

        f = fokus.Frage("test", "flotte", effekt=0.000001, streuung=0.01,
                        tage_vorhanden=40, schwelle=2.85)
        assert not f.zu_frueh
        assert f.tot

    def test_erreichbare_frage_nennt_ein_datum(self):
        from alpaca_bot import fokus

        f = fokus.Frage("test", "flotte", effekt=0.01, streuung=0.02,
                        tage_vorhanden=40, schwelle=2.85)
        assert not f.tot and not f.zu_frueh
        assert f.tage_noetig == int(np.ceil((2.85 * 0.02 / 0.01) ** 2))
        assert f.datum not in ("nie", "offen")

    def test_jeder_bot_wird_gegen_seine_registrierte_basis_gemessen(self):
        """FEHLER 3 = §G6. `offene_fragen` darf keine globale Referenz
        benutzen. B04 unterscheidet sich von B00 in einer Achse, von B09
        in dreien - ein Vergleich ueber drei Achsen misst nichts."""
        import inspect

        from alpaca_bot import fokus

        quelle = inspect.getsource(fokus.offene_fragen)
        assert "b.basis_bot" in quelle, (
            "offene_fragen muss die registrierte basis_bot je Bot nutzen")
        # Kein globaler Basis-Parameter mehr, der das aushebeln koennte
        assert "basis" not in inspect.signature(fokus.offene_fragen).parameters

    def test_bericht_weicht_den_entscheidungsvertrag_nicht_auf(self):
        """Ein frueheres Datum in der Fokus-Spalte ist keine Erlaubnis,
        frueher zu entscheiden. §3.3 und der 10.10. bleiben (§G10)."""
        from alpaca_bot import fokus

        text = fokus.bericht()
        assert "10.10.2026" in text
        assert "§3.3" in text


class TestLernkernAbnahme:
    """Eine neue Version wird nicht automatisch gut."""

    def test_kriterien_stehen_als_konstanten_fest(self):
        """Vorab und nicht je Aufruf - sonst waere jede Version an einer
        anderen Huerde gemessen worden."""
        from alpaca_bot import lernkern

        assert lernkern.MIN_TAGE_BEWERTUNG >= 250
        assert lernkern.MIN_VERBESSERUNG_IC > 0

    def test_abnahme_lehnt_unter_der_schwelle_ab(self, tmp_path, monkeypatch):
        from alpaca_bot import lernkern

        monkeypatch.setattr(lernkern, "DB_PFAD", tmp_path / "l.sqlite")
        with lernkern._conn() as c:
            c.execute(
                "INSERT INTO modelle (model_version, erstellt_at, code_version,"
                " status, quelle, n_tage_bewertet, ic, t, schwelle, befund)"
                " VALUES ('v1','2026-01-01','abc','kandidat','historie',"
                " 900, 0.01, 1.5, 2.85, 0)")
        grund = lernkern.abnehmen("v1", verbose=False)
        assert "abgelehnt" in grund and "1.5" in grund

    def test_abnahme_lehnt_bei_zu_wenig_tagen_ab(self, tmp_path, monkeypatch):
        """Auch ein grossartiger t-Wert reicht nicht, wenn die Datenbasis
        ihn nicht tragen kann."""
        from alpaca_bot import lernkern

        monkeypatch.setattr(lernkern, "DB_PFAD", tmp_path / "l.sqlite")
        with lernkern._conn() as c:
            c.execute(
                "INSERT INTO modelle (model_version, erstellt_at, code_version,"
                " status, quelle, n_tage_bewertet, ic, t, schwelle, befund)"
                " VALUES ('v2','2026-01-01','abc','kandidat','schatten',"
                " 19, 0.20, 9.9, 2.85, 1)")
        grund = lernkern.abnehmen("v2", verbose=False)
        assert "abgelehnt" in grund and "19" in grund
