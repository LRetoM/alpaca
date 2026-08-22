"""Die Kostenkontrolle muss dieselbe Kennzahl prüfen wie der Vertrag (§G16).

**Anlass (22.08.2026).** `shadow.pruefungen()` Nr. 5 meldete FEHL:

    Depot misst -92.0 bps Slippage (n-gewichtet, 178 Fuellungen),
    Schatten setzt 3.0 bps an. Schatten ist zu optimistisch.

Beide Teile der Meldung waren falsch.

**1. Falsche Kennzahl.** Der Entscheidungsvertrag nennt zweimal
ausdrücklich den MEDIAN:

    BETRIEBSPLAN §3.1  "Erforderlich: Slippage-Median < 8 bps über 30+
                        saubere Orders"
    BETRIEBSPLAN §8    "Slippage-Median > 15 bps über 30 Trades ->
                        alle Backtest- und Schattenergebnisse neu bewerten"

Die Prüfung rechnete einen n-gewichteten MITTELWERT. Gemessen an
denselben 162 prüfbaren Orders:

    Median   +0,0 bps   -> Kriterium aus §3.1 ERFÜLLT
    Mittel  -71,7 bps   -> Prüfung meldet FEHL

Die Differenz stammt aus drei bekannten Datenfehlern, die das Projekt
selbst dokumentiert (§G, 04.08.2026): KGS -1648 bps und SIMO -1584 bps
sind kaputte IEX-Quotes, keine Ausführungsqualität. Genau gegen solche
Artefakte ist der Median robust - und genau deshalb steht er im Vertrag.

**2. Falsche Richtung.** Ein NEGATIVER Wert heißt bei der Vorzeichen-
konvention aus `journal.order()`: besser ausgeführt als erwartet. Der
Satz "Schatten ist zu optimistisch - Annahme anheben" beschreibt den
umgekehrten Fall.

Ein Fehlalarm in der wichtigsten Kennzahl des Projekts ist teuer: Er
steht dauerhaft im Prüfbericht, und eine Warnung, die immer leuchtet,
wird weggeklickt (`docs/LERNTEMPO.md` §5).
"""

from __future__ import annotations

import inspect

import pandas as pd
import pytest

from alpaca_bot import shadow


class TestKennzahlIstDerMedian:
    """Was der Vertrag verlangt, muss die Prüfung messen."""

    def test_pruefung_nutzt_den_median(self):
        quelle = inspect.getsource(shadow._pruefe_kosten)
        assert "median" in quelle.lower(), (
            "BETRIEBSPLAN §3.1 und §8 nennen beide den Median - eine "
            "Prüfung auf den Mittelwert misst etwas anderes als der Vertrag")

    def test_ausreisser_kippen_das_urteil_nicht(self, monkeypatch):
        """Der konkrete Fall: 160 saubere Orders, 2 kaputte Quotes."""
        werte = pd.Series([0.5] * 160 + [-1647.9, -1583.5])
        monkeypatch.setattr("alpaca_bot.journal.Journal.slippage_werte",
                            lambda self, **kw: werte)

        b = shadow._pruefe_kosten(shadow.ShadowStore.__new__(shadow.ShadowStore))
        assert b.ok, (
            "zwei kaputte IEX-Quotes duerfen 160 saubere Orders nicht "
            "ueberstimmen - dagegen ist der Median da")
        assert "2 von 162" in b.text, "die Ausreisser muessen sichtbar bleiben"

    def test_echte_verschlechterung_faellt_auf(self, monkeypatch):
        """Die Prüfung darf nicht einfach immer bestehen."""
        werte = pd.Series([45.0] * 80 + [52.0] * 80)
        monkeypatch.setattr("alpaca_bot.journal.Journal.slippage_werte",
                            lambda self, **kw: werte)

        b = shadow._pruefe_kosten(shadow.ShadowStore.__new__(shadow.ShadowStore))
        assert not b.ok, (
            "ein Median von ~48 bps gegen 3 bps Annahme ist eine echte "
            "Abweichung und muss auffallen")

    def test_zu_wenige_fuellungen_sind_kein_fehlschlag(self, monkeypatch):
        werte = pd.Series([40.0, 41.0, 39.0])
        monkeypatch.setattr("alpaca_bot.journal.Journal.slippage_werte",
                            lambda self, **kw: werte)

        b = shadow._pruefe_kosten(shadow.ShadowStore.__new__(shadow.ShadowStore))
        assert b.ok and "zu wenig" in b.text.lower()


class TestRichtungStimmt:
    """Negativ heißt besser als erwartet - nicht schlechter."""

    def test_guenstigere_ausfuehrung_heisst_nicht_zu_optimistisch(self, monkeypatch):
        werte = pd.Series([-40.0] * 100)
        monkeypatch.setattr("alpaca_bot.journal.Journal.slippage_werte",
                            lambda self, **kw: werte)

        b = shadow._pruefe_kosten(shadow.ShadowStore.__new__(shadow.ShadowStore))
        assert "zu optimistisch" not in b.text, (
            "bei guenstigerer Ausfuehrung als erwartet ist die "
            "Schattenannahme zu vorsichtig, nicht zu optimistisch")

    def test_meldung_nennt_die_vertragsschwelle(self, monkeypatch):
        """Ohne Bezug zu §3.1 ist die Zahl nicht einzuordnen."""
        werte = pd.Series([1.0] * 100)
        monkeypatch.setattr("alpaca_bot.journal.Journal.slippage_werte",
                            lambda self, **kw: werte)

        b = shadow._pruefe_kosten(shadow.ShadowStore.__new__(shadow.ShadowStore))
        assert "8" in b.text or "§3.1" in b.text


class TestKursanpassungPrueftDieKante:
    """Prüfung 4 durfte nicht die ganze Historie mitteln (§G16).

    yfinance lädt mit `auto_adjust=True`: Nach jeder Dividende und jedem
    Split ändern sich die HISTORISCHEN Kurse rückwirkend. Je älter ein
    Stichtag, desto mehr solcher Ereignisse liegen dahinter. Gemessen am
    22.08.2026 je Stichtag:

        28.07. – 07.08.   6 % bis 25 %   (alt, viele Ereignisse seither)
        13.08. – 20.08.   0 % bis  4 %   (jung)
        kumuliert         7,7 %          -> Prüfung meldet FEHL bei 5 %

    Die kumulierte Quote **muss** mit der Zeit wachsen und wird die
    Schwelle dauerhaft reißen, ohne dass etwas kaputt ist. Das ist exakt
    der Fehlversuch, den `data_integrity.check_stumme_felder` bereits
    einmal gemacht und §G13 festgehalten hat: eine Quote über die
    Historie zu prüfen statt der gefährlichen Richtung.

    Gefährlich wäre: **frische** Stichtage mit plötzlich hoher
    Anpassungsrate. Das hieße, die Kursquelle ändert Daten, die gerade
    erst entstanden sind — dann stimmt etwas mit dem Feed nicht.
    """

    def test_alte_stichtage_kippen_das_urteil_nicht(self):
        import inspect

        quelle = inspect.getsource(shadow._pruefe_kursanpassung)
        assert "juengste" in quelle.lower() or "kante" in quelle.lower(), (
            "geprueft gehoert die junge Kante, nicht die kumulierte "
            "Historie - sonst reisst die Schwelle zwangslaeufig (§G13)")

    def test_frische_anpassungen_fallen_auf(self, tmp_path):
        """Der gefaehrliche Fall muss weiterhin anschlagen."""
        s = shadow.ShadowStore(tmp_path / "s.sqlite")
        _fuelle(s, alt_quote=0.02, jung_quote=0.60)
        b = shadow._pruefe_kursanpassung(s)
        assert not b.ok

    def test_alte_anpassungen_sind_normal(self, tmp_path):
        s = shadow.ShadowStore(tmp_path / "s.sqlite")
        _fuelle(s, alt_quote=0.60, jung_quote=0.02)
        b = shadow._pruefe_kursanpassung(s)
        assert b.ok, ("alte Stichtage mit vielen Anpassungen sind der "
                      "Normalfall von auto_adjust")

    def test_ohne_daten_kein_fehlschlag(self, tmp_path):
        s = shadow.ShadowStore(tmp_path / "s.sqlite")
        assert shadow._pruefe_kursanpassung(s).ok


def _fuelle(s, *, alt_quote: float, jung_quote: float,
            n_je_tag: int = 30) -> None:
    """Alte und junge Stichtage mit einstellbarer Anpassungsquote.

    Genug Tage je Gruppe, dass `ANPASSUNG_JUENGSTE_TAGE` sie trennen
    kann - sonst landen beide Gruppen im Fenster und der Test misst den
    Durchschnitt statt der Kante.
    """
    import datetime as dt

    n_jung = shadow.ANPASSUNG_JUENGSTE_TAGE
    n_alt = n_jung + 3
    start = dt.date(2026, 6, 1)
    tage = [(start + dt.timedelta(days=i), alt_quote) for i in range(n_alt)]
    tage += [(start + dt.timedelta(days=n_alt + i), jung_quote)
             for i in range(n_jung)]

    with s._conn() as c:
        for tag, quote in tage:
            for i in range(n_je_tag):
                pid = f"p{tag.isoformat()}_{i}"
                c.execute(
                    "INSERT INTO predictions (pred_id, run_id, bot_id, buch,"
                    " as_of, decided_at, symbol, aktion, decision_price,"
                    " code_version) VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (pid, "r1", "B00", "rangliste", tag.isoformat(),
                     f"{tag.isoformat()}T20:00:00+00:00", f"S{i}", "buy",
                     100.0, "abc"))
                c.execute(
                    "INSERT INTO shadow_outcomes (pred_id, data_check)"
                    " VALUES (?,?)",
                    (pid, "kurs_angepasst" if i < int(n_je_tag * quote) else "ok"))


class TestReconcileImTagesbericht:
    """`costs.reconcile` - die Zeile, die im Wochenbericht gelesen wird (§G16).

    **Anlass (22.08.2026).** Derselbe Mittelwert-Fehler wie in
    `shadow._pruefe_kosten`, nur an sichtbarerer Stelle:
    `scripts/13_tagesbericht.py` ruft `costs.reconcile()` in Abschnitt
    "[3] AUSFUEHRUNG", und `docs/BETRIEBSPLAN.md` §5.2 nennt genau diesen
    Abschnitt als das, was alle 1-2 Wochen zu lesen ist -- mit der
    ausdruecklichen Erwartung "Slippage-**Median**".

    Ausgegeben wurde stattdessen:

        angenommen :    3.0 bps
        tatsaechlich:  -80.6 bps
        -> Ausfuehrung ist 83.6 bps besser als angenommen.

    `journal_df["mittel"].mean()` mittelt die Symbol-Mittelwerte
    ungewichtet. Drei kaputte IEX-Quotes (KGS, SIMO, GNRC) tragen dabei
    genauso viel wie 70 saubere Symbole. Die Aussage "83,6 bps besser"
    ist frei erfunden; der Median ueber dieselben 162 Orders ist +0,0.

    Eine falsche Zahl ist hier schlimmer als eine fehlende: Sie steht im
    Bericht, sieht nach Messung aus und wird zitiert.
    """

    def test_reconcile_nutzt_den_median_der_orders(self):
        from alpaca_bot import costs

        werte = pd.Series([0.5] * 160 + [-1647.9, -1583.5])
        bericht = pd.DataFrame({"n": [162], "mittel": [-19.3],
                                "median": [0.5], "max": [12.0]},
                               index=pd.Index(["X"], name="symbol"))
        text = costs.reconcile(3.0, bericht, werte=werte)
        assert "+0.5" in text or "0.5" in text, (
            f"erwartet der Median (0,5), ausgegeben wurde:\n{text}")
        assert "-19" not in text and "-1647" not in text

    def test_ohne_rohwerte_kein_erfundener_mittelwert(self):
        """Fehlen die Einzelwerte, darf NICHT auf den Mittelwert
        ausgewichen werden - dann lieber der Symbol-Median.

        Geprueft wird der RUMPF, nicht die ganze Quelle: Der Docstring
        zitiert die alte Zeile absichtlich, damit der Fehler dokumentiert
        bleibt. Ein Test ueber `inspect.getsource()` wuerde daran haengen
        bleiben - genau das ist beim Schreiben passiert.
        """
        from alpaca_bot import costs
        import inspect

        quelle = inspect.getsource(costs.reconcile)
        rumpf = quelle.split('"""')[-1]
        assert 'journal_df["mittel"].mean()' not in rumpf
        assert ".median()" in rumpf

    def test_meldung_nennt_die_zahl_der_orders(self):
        from alpaca_bot import costs

        werte = pd.Series([1.0] * 50)
        bericht = pd.DataFrame({"n": [50], "mittel": [1.0],
                                "median": [1.0], "max": [3.0]},
                               index=pd.Index(["X"], name="symbol"))
        text = costs.reconcile(3.0, bericht, werte=werte)
        assert "50" in text, "ohne Stichprobengroesse ist die Zahl nicht einzuordnen"

    def test_tagesbericht_reicht_die_rohwerte_durch(self):
        quelle = __import__("pathlib").Path("scripts/13_tagesbericht.py").read_text()
        block = quelle[quelle.index("[3] AUSFUEHRUNG"):]
        assert "slippage_werte" in block[:1200], (
            "der Bericht muss die Einzelwerte durchreichen, sonst rechnet "
            "reconcile weiter auf Symbolebene")
