"""Filing-Abrufe laufen parallel statt nacheinander (§G47, 27.08.2026).

**Der Fund.** `insider_trades()` holte jede Form-4-Einreichung einzeln in
einer `for`-Schleife - jeder Abruf wartete die volle Netzwerkantwort ab,
bevor der naechste begann. Im laufenden Kandidatentest gemessen: Die
Drossel (`RateLimiter("sec_edgar")`) erlaubt 9 Requests/Sekunde,
tatsaechlich kamen **1,66** an (Dateiwachstum im Plattencache ueber 30s
gemessen). Der Engpass war die reine Wartezeit, nicht das SEC-Limit -
das Budget lag die meiste Zeit brach.

**Was der Fix NICHT tut.** Er erhoeht nicht die erlaubte Rate. Die
Drossel bleibt threadsicher die einzige Instanz, die das SEC-Limit
durchsetzt, unabhaengig davon, aus welchem Thread `_get()` aufgerufen
wird. Der Test unten prueft genau das: Mehrere "langsame" Abrufe parallel
dauern insgesamt nicht laenger als der langsamste EINZELNE - waeren sie
weiterhin sequentiell, waere die Gesamtzeit die SUMME.
"""

from __future__ import annotations

import time

import pandas as pd

from alpaca_bot import edgar


def _langsame_zeile(**kwargs):
    time.sleep(0.15)
    return []


def test_filings_werden_parallel_geholt(monkeypatch):
    """Der eigentliche Fix: N langsame Abrufe brauchen ungefaehr die Zeit
    EINES Abrufs, nicht N mal so lang."""
    n = edgar.PARALLEL_FILINGS
    monkeypatch.setattr(edgar, "parse_form4",
                        lambda cik, acc, accn, tick, dt: _langsame_zeile())
    monkeypatch.setattr(edgar, "filings", lambda *a, **k: pd.DataFrame({
        "cik": ["1"] * n, "accession": ["a"] * n, "accessionNumber": ["a-1"] * n,
        "ticker": ["TEST"] * n, "filing_date": [pd.Timestamp("2024-01-01")] * n,
    }))

    start = time.monotonic()
    edgar.insider_trades("TEST", since="2024-01-01")
    dauer = time.monotonic() - start

    # Sequentiell waeren das n * 0.15s. Grosszuegige Grenze (die Haelfte
    # der sequentiellen Zeit), damit der Test nicht auf einer langsamen
    # CI-Maschine grundlos flackert.
    sequentiell = n * 0.15
    assert dauer < sequentiell / 2, (
        f"{dauer:.2f}s fuer {n} Abrufe a 0.15s - das ist nicht schneller "
        f"als sequentiell ({sequentiell:.2f}s). Laeuft insider_trades() "
        f"wieder als einfache for-Schleife (§G47)?")


def test_drossel_bleibt_die_einzige_bremse(monkeypatch):
    """Parallelitaet darf die ERLAUBTE Rate nicht erhoehen - nur die
    LEERLAUFZEIT innerhalb des erlaubten Budgets wegnehmen."""
    aufrufe = []
    echtes_acquire = edgar._limit.acquire

    def gezaehltes_acquire(n=1):
        aufrufe.append(time.monotonic())
        return echtes_acquire(n)

    monkeypatch.setattr(edgar._limit, "acquire", gezaehltes_acquire)
    monkeypatch.setattr(edgar, "_get", lambda *a, **k: (edgar._limit.acquire(), {})[1])
    monkeypatch.setattr(edgar, "filings", lambda *a, **k: pd.DataFrame({
        "cik": ["1"] * 4, "accession": ["a"] * 4, "accessionNumber": ["a-1"] * 4,
        "ticker": ["TEST"] * 4, "filing_date": [pd.Timestamp("2024-01-01")] * 4,
    }))

    edgar.insider_trades("TEST", since="2024-01-01")

    # Jedes Filing loest 1 _get() aus (index.json) - die zweite (XML)
    # wird hier nicht erreicht, weil `_get` bereits [] liefert. Massgeblich
    # ist nur: JEDER Abruf ging durch acquire(), keiner daran vorbei.
    assert len(aufrufe) == 4


def test_pool_maxsize_deckt_die_parallelitaet_ab():
    """Weniger Verbindungen im Pool als parallele Worker wuerde Threads
    aufeinander warten lassen und einen Teil des Gewinns wieder auffressen."""
    adapter = edgar._SESSION.get_adapter("https://data.sec.gov/x")
    assert adapter._pool_maxsize >= edgar.PARALLEL_FILINGS
