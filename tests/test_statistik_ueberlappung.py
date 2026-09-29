"""Die Ueberlappung ZWISCHEN den Handelstagen (BEFUNDE §G12).

REGRESSION 22.08.2026. Das Projekt hatte die Ueberlappung INNERHALB
eines Handelstages seit dem 15.08. sauber geloest (`gruppierter_test`,
§B1). Die zwischen den Tagen blieb: Bei einem Renditefenster von 5 Tagen
sagt Tag 1 die Tage 1-5 voraus und Tag 2 die Tage 2-6 - vier von fuenf
Tagen sind dieselben.

Gemessen mit dem projekteigenen Faktor-Scan ueber 1.182 Symbole und
7 Jahre: der t-Wert fiel im Mittel um den Faktor 1,62 zu hoch aus. Von
30 Faktoren ueberschritten naiv 10 die Zufallsschwelle, korrigiert 4.

Das Tueckische daran: Das Wissen war im Projekt bereits vorhanden -
`scripts/24_kandidaten_test.py` gruppiert ausdruecklich nach MONAT, mit
genau dieser Begruendung im Kommentar. Nur `research.py`, das die
tragenden Faktoren der Strategie ausgewaehlt hat, tat es nicht.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def _ueberlappende_reihe(rng, n: int = 400, fenster: int = 5) -> np.ndarray:
    """Reihe aus echt ueberlappenden Fenstern - reines Rauschen, KEIN Effekt.

    Gebaut wie die Wirklichkeit: taegliche unabhaengige Schocks, daraus
    gleitende `fenster`-Tage-Mittel. Jeder Wert teilt mit seinem Nachbarn
    `fenster - 1` Schocks. Ein korrekter Test darf hier fast nie einen
    Befund melden.
    """
    schock = rng.normal(0, 1, n)
    return np.array([schock[i:i + fenster].mean()
                     for i in range(n - fenster)])


class TestNeweyWestGrundverhalten:
    """Die Korrekturfunktion selbst."""

    def test_ohne_autokorrelation_aendert_sie_nichts(self):
        """Kontrollfall. Ohne Ueberlappung muss die Korrektur folgenlos sein.

        Ohne diesen Test koennte die Funktion pauschal jeden t-Wert
        senken und saehe in allen anderen Tests richtig aus.
        """
        from alpaca_bot.statistik import newey_west_t

        rng = np.random.default_rng(1)
        x = rng.normal(0.3, 1, 500)
        t_naiv = x.mean() / (x.std(ddof=1) / np.sqrt(len(x)))
        t_korr, aufbl = newey_west_t(x, lag=4)

        # Geprueft wird die Aufblaehung, nicht die t-Differenz: die
        # Aufblaehung ist massstabsfrei, die Differenz waechst mit dem
        # t-Wert selbst. Eine absolute Schranke auf die Differenz waere
        # bei t=6,5 eine ganz andere Anforderung als bei t=0,5 - und
        # haette hier faelschlich angeschlagen (gemessen 0,78 bei einer
        # Aufblaehung von 0,89, also einwandfrei).
        assert abs(aufbl - 1.0) < 0.15
        assert abs(t_korr / t_naiv - 1.0) < 0.2

    def test_bei_ueberlappung_senkt_sie_den_t_wert(self):
        from alpaca_bot.statistik import newey_west_t

        rng = np.random.default_rng(7)
        x = _ueberlappende_reihe(rng)
        t_naiv = x.mean() / (x.std(ddof=1) / np.sqrt(len(x)))
        t_korr, aufbl = newey_west_t(x, lag=4)

        assert aufbl > 1.3, "Ueberlappung muss als Aufblaehung sichtbar werden"
        assert abs(t_korr) < abs(t_naiv)

    def test_reihenfolge_ist_die_information(self):
        """Umsortiert verschwindet die Autokorrelation - und damit die Korrektur.

        Das ist der Grund, warum `gruppierter_test` seine Gruppenmittel
        vor der Korrektur chronologisch sortiert. Ein Aufrufer, der eine
        unsortierte Reihe uebergibt, bekaeme stillschweigend den
        unkorrigierten Wert zurueck.
        """
        from alpaca_bot.statistik import newey_west_t

        rng = np.random.default_rng(3)
        x = _ueberlappende_reihe(rng)
        _, aufbl_sortiert = newey_west_t(x, lag=4)
        gemischt = x.copy()
        np.random.default_rng(11).shuffle(gemischt)
        _, aufbl_gemischt = newey_west_t(gemischt, lag=4)

        assert aufbl_sortiert > 1.3
        assert abs(aufbl_gemischt - 1.0) < 0.2

    def test_negative_varianz_faellt_nicht_um(self):
        """Newey-West kann rechnerisch eine Varianz <= 0 schaetzen.

        Bei stark negativer Autokorrelation ist das kein Ergebnis,
        sondern eine Grenze des Schaetzers. Die Funktion muss dann einen
        endlichen Wert liefern statt NaN aus einer Wurzel aus Negativem.
        """
        from alpaca_bot.statistik import newey_west_t

        # Perfekter Zickzack: maximale negative Autokorrelation.
        x = np.array([1.0, -1.0] * 100) + 0.05
        t, aufbl = newey_west_t(x, lag=4)
        assert np.isfinite(t) and np.isfinite(aufbl)

    def test_kern_trifft_den_analytisch_erwarteten_wert(self):
        """Pinnt den Bartlett-Kern gegen einen herleitbaren Sollwert.

        Fuer ein gleitendes `q`-Tage-Mittel aus weissem Rauschen sind die
        Autokovarianzen exakt bekannt: gamma_k / gamma_0 = (q - k) / q.
        Mit den Bartlett-Gewichten (1 - k/(lag+1)) und lag = q - 1 folgt

            LRV / gamma_0 = 1 + 2 * sum_{k=1}^{q-1} ((q - k) / q)^2

        Fuer q = 5 sind das 1 + 2*(0,64+0,36+0,16+0,04) = 3,40, also eine
        Aufblaehung von sqrt(3,40) = 1,844.

        Warum dieser Test noetig wurde: Der Mutationstest ersetzte am
        22.08.2026 die Bartlett-Gewichte durch volle Gewichte und blieb
        UNGEFANGEN - alle damaligen Tests prueften nur "groesser als 1".
        Volle Gewichte ergeben hier sqrt(5) = 2,236 und fallen jetzt auf.
        """
        from alpaca_bot.statistik import newey_west_t

        q = 5
        erwartet = np.sqrt(1 + 2 * sum(((q - k) / q) ** 2 for k in range(1, q)))
        assert abs(erwartet - 1.844) < 0.001, "Herleitung selbst pruefen"

        # Ueber viele Ziehungen mitteln - eine einzelne Reihe streut.
        rng = np.random.default_rng(99)
        werte = [newey_west_t(_ueberlappende_reihe(rng, n=2000, fenster=q),
                              lag=q - 1)[1] for _ in range(40)]
        assert abs(float(np.mean(werte)) - erwartet) < 0.12

    def test_zu_kurze_reihe_liefert_nan_statt_zufall(self):
        from alpaca_bot.statistik import newey_west_t

        t, aufbl = newey_west_t(np.array([1.0, 2.0]), lag=4)
        assert np.isnan(t) and np.isnan(aufbl)


class TestGruppierterTestMitHorizont:
    """Die Verdrahtung in `gruppierter_test`."""

    def test_horizont_1_ist_unveraendert(self):
        """Rueckwaertskompatibilitaet: der Vorgabewert darf nichts aendern.

        Alle bestehenden Aufrufer ohne `horizont=` muessen exakt
        dieselbe Zahl bekommen wie vorher.
        """
        from alpaca_bot.statistik import gruppierter_test

        rng = np.random.default_rng(5)
        werte = pd.Series(rng.normal(0.01, 0.05, 300))
        tage = pd.Series(pd.date_range("2024-01-01", periods=300, freq="B"))
        r = gruppierter_test(werte, tage)

        assert r.horizont == 1
        assert r.t_ueberlappung == r.t
        assert r.aufblaehung == 1.0

    def test_horizont_5_senkt_den_t_wert(self):
        """Derselbe Datensatz, zwei t-Werte."""
        from alpaca_bot.statistik import gruppierter_test

        rng = np.random.default_rng(7)
        x = _ueberlappende_reihe(rng)
        tage = pd.Series(pd.date_range("2024-01-01", periods=len(x), freq="B"))
        roh = gruppierter_test(pd.Series(x), tage)
        korr = gruppierter_test(pd.Series(x), tage, horizont=5)

        assert roh.t == korr.t, "der Tages-t-Wert selbst bleibt gleich"
        assert abs(korr.t_ueberlappung) < abs(korr.t)
        assert korr.aufblaehung > 1.3

    def test_urteil_kippt_bei_reinem_rauschen(self):
        """Der Kernfall: aus einem Fehlbefund wird kein Befund.

        Seed 24 ist bewusst gesucht: t roh -3,37 (waere ein Befund),
        korrigiert -1,82 (keiner). Die Reihe enthaelt KEINEN Effekt,
        sie ist ein gleitendes Mittel ueber weisses Rauschen - der rohe
        Wert ist also nachweislich falsch, nicht bloss optimistisch.
        """
        from alpaca_bot.statistik import gruppierter_test

        x = _ueberlappende_reihe(np.random.default_rng(24))
        tage = pd.Series(pd.date_range("2024-01-01", periods=len(x), freq="B"))
        roh = gruppierter_test(pd.Series(x), tage)
        korr = gruppierter_test(pd.Series(x), tage, horizont=5)

        assert roh.belastbar, "ohne Korrektur waere das ein Befund"
        assert not korr.belastbar, "mit Korrektur darf es keiner sein"

    def test_belastbar_haengt_am_korrigierten_wert(self):
        """Sonst waere die Korrektur gerechnet, aber folgenlos."""
        from alpaca_bot.statistik import gruppierter_test

        x = _ueberlappende_reihe(np.random.default_rng(24))
        tage = pd.Series(pd.date_range("2024-01-01", periods=len(x), freq="B"))
        r = gruppierter_test(pd.Series(x), tage, horizont=5)

        assert abs(r.t) > 2, "Voraussetzung: roh waere es ein Befund"
        assert abs(r.t_ueberlappung) < 2
        assert not r.belastbar

    def test_gruppen_werden_chronologisch_sortiert(self):
        """Unsortiert uebergebene Tage duerfen das Ergebnis nicht aendern.

        `groupby` sortiert zwar selbst, aber die Korrektur haengt an der
        Reihenfolge - deshalb ist das eine Zusicherung, kein Zufall.
        """
        from alpaca_bot.statistik import gruppierter_test

        rng = np.random.default_rng(7)
        x = _ueberlappende_reihe(rng)
        tage = pd.date_range("2024-01-01", periods=len(x), freq="B")
        df = pd.DataFrame({"w": x, "t": tage})
        gemischt = df.sample(frac=1.0, random_state=2)

        a = gruppierter_test(df["w"], df["t"], horizont=5)
        b = gruppierter_test(gemischt["w"], gemischt["t"], horizont=5)
        assert abs(a.t_ueberlappung - b.t_ueberlappung) < 1e-9

    def test_bericht_nennt_beide_werte(self):
        """Der Text muss den rohen Wert als ueberschaetzt kennzeichnen."""
        from alpaca_bot.statistik import gruppierter_test

        rng = np.random.default_rng(7)
        x = _ueberlappende_reihe(rng)
        tage = pd.Series(pd.date_range("2024-01-01", periods=len(x), freq="B"))
        text = str(gruppierter_test(pd.Series(x), tage, horizont=5))

        assert "Ueberlapp" in text and "massgeblich" in text
        assert "ueberschaetzt" in text

    def test_horizont_1_zeigt_keine_doppelte_zeile(self):
        """Zwei identische t-Zeilen laden dazu ein, die falsche zu zitieren."""
        from alpaca_bot.statistik import gruppierter_test

        rng = np.random.default_rng(5)
        werte = pd.Series(rng.normal(0.01, 0.05, 300))
        tage = pd.Series(pd.date_range("2024-01-01", periods=300, freq="B"))
        text = str(gruppierter_test(werte, tage))

        assert "t (gruppiert)" in text
        assert "Ueberlapp" not in text


class TestFehlalarmquote:
    """Der eigentliche Beleg: wie oft meldet der Test Unsinn?

    Auf reinem Rauschen ohne jeden Effekt darf ein Test bei |t|>2 in
    etwa 5 % der Faelle anschlagen. Gemessen ueber 200 Laeufe mit
    5-Tage-Fenstern: unkorrigiert rund 40 %, korrigiert rund 11 %.

    Die 11 % sind ehrlich zu nennen: Newey-West unterkorrigiert in
    endlichen Stichproben bekanntermassen. Die Korrektur macht den Test
    nicht exakt, sie macht ihn brauchbar.
    """

    def test_unkorrigiert_meldet_massenhaft_fehlbefunde(self):
        from alpaca_bot.statistik import gruppierter_test

        rng = np.random.default_rng(42)
        tage = pd.Series(pd.date_range("2024-01-01", periods=395, freq="B"))
        roh = korr = 0
        laeufe = 200
        for _ in range(laeufe):
            x = _ueberlappende_reihe(rng)
            r = gruppierter_test(pd.Series(x), tage, horizont=5)
            roh += abs(r.t) > 2
            korr += abs(r.t_ueberlappung) > 2

        assert roh / laeufe > 0.25, "der Ausgangsfehler muss sichtbar sein"
        assert korr / laeufe < 0.20
        assert korr < roh / 2, "die Korrektur muss die Quote mindestens halbieren"


class TestFaktorAuswahlNutztDenKorrigiertenWert:
    """`research.py` - die Stelle, an der die Korrektur zaehlt.

    Die Kette, die den Fehler teuer gemacht hat:
    `scripts/11_factor_lab.py` -> `research.measure_factors` -> `t_stat`
    (unkorrigiert) -> `select_factors(min_t=3.0)`. Die tragenden Faktoren
    der Strategie (`signals.ReversalWeights`) sind ueber genau diesen Weg
    ausgewaehlt worden.
    """

    def _ergebnisse(self):
        return pd.DataFrame([
            # Haelt die Schwelle roh, aber nicht korrigiert.
            dict(factor="scheinbar_stark", horizon=5, ic_mean=0.016,
                 ic_std=0.1, t_stat=3.9, n_days=1500, n_obs=9, hit_rate=0.55,
                 q5_minus_q1=0.01, t_korrigiert=2.1, aufblaehung=1.86),
            # Haelt sie in beiden Rechnungen.
            dict(factor="echt_stark", horizon=5, ic_mean=0.012,
                 ic_std=0.1, t_stat=4.4, n_days=1500, n_obs=9, hit_rate=0.56,
                 q5_minus_q1=0.01, t_korrigiert=3.2, aufblaehung=1.38),
        ])

    def test_scheinbar_starker_faktor_wird_nicht_gewaehlt(self):
        from alpaca_bot import research

        gewaehlt = research.select_factors(self._ergebnisse(), horizon=5,
                                           min_t=3.0)
        assert "echt_stark" in gewaehlt
        assert "scheinbar_stark" not in gewaehlt, (
            "ein Faktor, der nur unkorrigiert ueber der Schwelle liegt, "
            "darf nicht in die Strategie")

    def test_urteil_folgt_dem_korrigierten_wert(self):
        from alpaca_bot.research import FactorResult

        r = FactorResult(factor="x", horizon=5, ic_mean=0.02, ic_std=0.1,
                         t_stat=3.9, n_days=1500, n_obs=9, hit_rate=0.55,
                         q5_minus_q1=0.01, t_korrigiert=1.5, aufblaehung=2.6)
        assert r.verdict == "Rauschen"

    def test_ohne_korrektur_gilt_der_rohe_wert(self):
        """Alte Ergebnistabellen duerfen nicht stillschweigend durchfallen."""
        from alpaca_bot.research import FactorResult

        r = FactorResult(factor="x", horizon=5, ic_mean=0.02, ic_std=0.1,
                         t_stat=3.9, n_days=1500, n_obs=9, hit_rate=0.55,
                         q5_minus_q1=0.01)
        assert r.verdict == "NUETZLICH"

    def test_rangliste_kennzeichnet_den_rohen_wert(self):
        from alpaca_bot import research

        d = self._ergebnisse()
        d["verdict"] = ["Rauschen", "NUETZLICH"]
        text = research.summarize(d)
        assert "t korr." in text and "t roh" in text
        assert "nie zitieren" in text

    def test_messung_liefert_beide_werte(self):
        """Ende zu Ende auf echten Kursen - liefert `measure_factors` sie?"""
        from alpaca_bot import research

        rng = np.random.default_rng(4)
        tage = pd.date_range("2020-01-01", periods=400, freq="B")
        teile = []
        for sym in [f"S{i:02d}" for i in range(40)]:
            kurs = 100 * np.exp(np.cumsum(rng.normal(0, 0.02, len(tage))))
            teile.append(pd.DataFrame({
                "symbol": sym, "timestamp": tage, "open": kurs, "high": kurs * 1.01,
                "low": kurs * 0.99, "close": kurs, "volume": 1e6}))
        bars = pd.concat(teile).set_index(["symbol", "timestamp"]).sort_index()

        erg = research.measure_factors(bars, horizons=(5,), verbose=False)
        assert not erg.empty
        assert erg["t_korrigiert"].notna().any()
        assert erg["aufblaehung"].notna().any()
        assert (erg["aufblaehung"] > 0).all()
