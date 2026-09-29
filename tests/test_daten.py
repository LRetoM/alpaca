"""Die Datenschicht - Cache und Zeitraeume.

Ein kaputter Cache faellt nie auf. Er liefert keine falschen Zahlen, er
kostet nur jedes Mal wieder Zeit und API-Quote - und die Quote teilen
sich Live-Bot, Schattenbetrieb und jede Auswertung. Ein Backtest ueber
2.000 Symbole ist mit funktionierendem Cache eine Sache von Minuten und
ohne ihn eine von Stunden.
"""

from __future__ import annotations

import datetime as dt

import pandas as pd


class TestBarCacheSchluessel:
    """REGRESSION 21.08.2026: Der Bar-Cache konnte nie treffen.

    Zwei unabhaengige Fehler in derselben Zeile, beide unsichtbar:

    1. `abs(hash(key))` - Pythons String-`hash()` ist pro Prozess
       randomisiert (PYTHONHASHSEED). Jeder Programmstart erzeugte fuer
       denselben Abruf einen anderen Dateinamen.
    2. Der Schluessel enthielt `start` als vollen Zeitstempel. Beim
       Aufruf mit `lookback_days` ist das `datetime.now()` - mit
       Mikrosekunden. Der Schluessel war damit selbst innerhalb eines
       Prozesses bei jedem Aufruf verschieden.

    Befund: `use_cache=True` wurde im ganzen Projekt von niemandem
    aufgerufen, und das Cache-Verzeichnis war leer. Toter Code, der
    zusaetzlich kaputt war - waehrend `compliance.py` ausdruecklich
    riet, ihn zu benutzen.
    """

    def test_schluessel_ist_ueber_prozesse_stabil(self):
        """Der Kernfehler: derselbe Abruf muss denselben Schluessel geben.

        Hier steht ein FESTER Erwartungswert, und das ist Absicht. Ein
        Vergleich zweier Aufrufe im selben Test wuerde den
        Ursprungsfehler NICHT fangen: `hash()` ist innerhalb eines
        Prozesses sehr wohl stabil, und pytest laeuft in einem Prozess.
        Nur ein ueber Laeufe hinweg festgeschriebener Wert prueft das,
        worum es geht.

        Aendert jemand das Schluesselformat, faellt dieser Test - zu
        Recht: der vorhandene Cache wird dadurch ungueltig, und das
        soll eine bewusste Entscheidung sein, kein Nebeneffekt.
        """
        from alpaca_bot.data import _cache_key

        a = _cache_key(["AAPL", "MSFT"], "1D", "2020-01-01", "2021-01-01")
        assert a == "6a8694effd68d10f8811b47201c9ed54"
        assert len(a) == 32 and all(c in "0123456789abcdef" for c in a)

    def test_mikrosekunden_aendern_den_schluessel_nicht(self):
        """`lookback_days` erzeugt `datetime.now()` - zweimal nie gleich."""
        from alpaca_bot.data import _cache_key

        t1 = dt.datetime(2020, 1, 1, 9, 30, 0, 123456, tzinfo=dt.UTC)
        t2 = dt.datetime(2020, 1, 1, 16, 59, 59, 999999, tzinfo=dt.UTC)
        assert _cache_key(["AAPL"], "1D", t1, None) == \
            _cache_key(["AAPL"], "1D", t2, None)

    def test_symbolreihenfolge_aendert_den_schluessel_nicht(self):
        from alpaca_bot.data import _cache_key

        assert _cache_key(["MSFT", "AAPL"], "1D", None, None) == \
            _cache_key(["AAPL", "MSFT"], "1D", None, None)

    def test_verschiedene_abrufe_kollidieren_nicht(self):
        """Ein Cache, der alles fuer gleich haelt, ist schlimmer als keiner.

        Er liefert dann fremde Daten - und DAS waere ein stiller
        Datenfehler statt nur verschenkter Zeit.
        """
        from alpaca_bot.data import _cache_key

        basis = _cache_key(["AAPL"], "1D", "2020-01-01", "2021-01-01")
        anders = [
            _cache_key(["MSFT"], "1D", "2020-01-01", "2021-01-01"),
            _cache_key(["AAPL"], "1Min", "2020-01-01", "2021-01-01"),
            _cache_key(["AAPL"], "1D", "2020-01-02", "2021-01-01"),
            _cache_key(["AAPL"], "1D", "2020-01-01", "2021-01-02"),
            _cache_key(["AAPL"], "1D", "2020-01-01", None),
            _cache_key(["AAPL", "MSFT"], "1D", "2020-01-01", "2021-01-01"),
        ]
        assert len(set(anders)) == len(anders)
        assert basis not in anders

    def test_verschiedene_tage_trennen(self):
        """Tagesgenau, nicht groeber: gestern ist nicht heute."""
        from alpaca_bot.data import _cache_key

        t1 = dt.datetime(2020, 1, 1, 23, 59, tzinfo=dt.UTC)
        t2 = dt.datetime(2020, 1, 2, 0, 1, tzinfo=dt.UTC)
        assert _cache_key(["AAPL"], "1D", t1, None) != \
            _cache_key(["AAPL"], "1D", t2, None)

    def test_cache_schreibt_und_liest_dieselben_daten(self, tmp_path):
        """Der Rundlauf: schreiben, lesen, identisch.

        Prueft zugleich, dass der Index (symbol, timestamp) den Weg
        ueber CSV unbeschadet uebersteht - ohne das waere der Cache
        zwar schnell, aber die Daten haetten eine andere Form als beim
        Direktabruf.

        `CACHE_DIR` wird auf ein Wegwerfverzeichnis umgebogen. Sonst
        laege nach dem ersten Testlauf eine echte Cache-Datei da, der
        erste Abruf traefe sie - und der Test pruefte ab dem zweiten
        Lauf nicht mehr das Schreiben, ohne dass es auffiele.
        """
        from unittest.mock import patch

        from alpaca_bot import data

        idx = pd.MultiIndex.from_product(
            [["AAPL"], pd.to_datetime(["2020-01-02", "2020-01-03"], utc=True)],
            names=["symbol", "timestamp"])
        original = pd.DataFrame(
            {"open": [1.0, 2.0], "high": [1.5, 2.5], "low": [0.5, 1.5],
             "close": [1.2, 2.2], "volume": [100, 200]}, index=idx)

        class _Antwort:
            df = original

        with patch.object(data, "stock_data_client") as client, \
             patch.object(data, "CACHE_DIR", tmp_path), \
             patch.object(data._limit, "acquire"):
            client.return_value.get_stock_bars.return_value = _Antwort()
            erst = data.get_bars(["AAPL"], "1D", start="2020-01-01",
                                 end="2020-01-04", use_cache=True)
            # Zweiter Aufruf: der Client darf gar nicht mehr gefragt werden.
            client.return_value.get_stock_bars.reset_mock()
            zweit = data.get_bars(["AAPL"], "1D", start="2020-01-01",
                                  end="2020-01-04", use_cache=True)
            client.return_value.get_stock_bars.assert_not_called()

        pd.testing.assert_frame_equal(erst, zweit, check_freq=False)
        assert list(zweit.index.names) == ["symbol", "timestamp"]
        assert zweit["close"].tolist() == [1.2, 2.2]
