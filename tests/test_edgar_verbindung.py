"""EDGAR-Abrufe teilen sich eine Verbindung, statt je Request neu zu verbinden (§G46).

**Der Vorfall (26.-27.08.2026).** Der Lauf ueber alle 2.168 Symbole
schaffte in acht Stunden nur 94 Symbole (4 %) und brach danach ab.
Durchschnitt: 320-330s je Symbol, mit staendigen `ReadTimeout`-
Wiederholungen im Log. Hochgerechnet waeren das 7-8 Tage statt der
geplanten 1,5-2.

**Die Ursache lag nicht am geschlossenen Terminal.** `_get()` und
`ticker_map()` riefen `requests.get(...)` auf - eine neue Funktion des
`requests`-Moduls, die bei jedem Aufruf einen frischen TCP+TLS-Handshake
aufbaut. Ein Symbol mit 900 Meldungen kostet ~1.800 Requests (zwei je
Einreichung, siehe `insider_trades`) - also 1.800 neue Verbindungen zu
`data.sec.gov`/`www.sec.gov` statt einer wiederverwendeten. Das erklaert
die haeufigen Timeouts unabhaengig vom eigentlichen Absturz.

**Behoben:** Ein modulweites `requests.Session()`-Objekt mit
Connection-Pooling. Beide Abrufstellen nutzen jetzt `_SESSION.get`,
keine mehr `requests.get`.
"""

from __future__ import annotations

import alpaca_bot.edgar as edgar


def test_get_nutzt_die_geteilte_session(monkeypatch, tmp_path):
    """Der eigentliche Fix: `_get()` geht ueber `_SESSION`, nicht ueber
    eine frische Verbindung je Aufruf."""
    monkeypatch.setattr(edgar, "EDGAR_CACHE", tmp_path)
    monkeypatch.setenv("SEC_USER_AGENT", "Test test@example.com")

    aufrufe = []

    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"ok": True}

    def fake_get(url, **kwargs):
        aufrufe.append(url)
        return FakeResponse()

    monkeypatch.setattr(edgar._SESSION, "get", fake_get)
    monkeypatch.setattr(edgar.requests, "get", lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("requests.get() direkt aufgerufen statt _SESSION.get() - "
                       "genau der Fehler aus §G46, neuer TCP+TLS-Handshake je Request")))

    ergebnis = edgar._get("https://data.sec.gov/beispiel.json")

    assert ergebnis == {"ok": True}
    assert aufrufe == ["https://data.sec.gov/beispiel.json"]


def test_ticker_map_nutzt_die_geteilte_session(monkeypatch, tmp_path):
    """Zweite Abrufstelle, gleicher Fehler waere hier genauso teuer -
    company_tickers.json wird nur einmal geholt, aber bei jedem
    frischen Cache-Ordner neu."""
    monkeypatch.setattr(edgar, "EDGAR_CACHE", tmp_path)
    monkeypatch.setenv("SEC_USER_AGENT", "Test test@example.com")

    class FakeResponse:
        text = '{"0": {"ticker": "TEST", "cik_str": 1}}'

        def raise_for_status(self):
            pass

    monkeypatch.setattr(edgar._SESSION, "get", lambda *a, **k: FakeResponse())
    monkeypatch.setattr(edgar.requests, "get", lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("requests.get() direkt aufgerufen statt _SESSION.get() (§G46)")))

    m = edgar.ticker_map()
    assert m == {"TEST": "0000000001"}


def test_session_hat_verbindungs_pooling_eingerichtet():
    """`_SESSION` muss tatsaechlich ein `requests.Session` mit einem
    HTTPS-Adapter sein - sonst waere die Variable nur Dekoration."""
    import requests

    assert isinstance(edgar._SESSION, requests.Session)
    adapter = edgar._SESSION.get_adapter("https://data.sec.gov/x")
    assert adapter.poolmanager is not None
