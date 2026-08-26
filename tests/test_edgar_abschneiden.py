"""Form-4-Meldungen werden ausgeschlossen, nicht abgeschnitten (§G41).

**Der Vorfall (26.08.2026).** `insider_trades` kuerzte bei Ueberschreitung
von `max_filings` still auf die NEUESTEN N (`f.tail(max_filings)`). Bei
der Vorgabe 150 und einem gemessenen Median von 436 Meldungen je Symbol
fehlten dem mittleren Symbol zwei Drittel der Historie - und zwar immer
die aeltere Haelfte.

Im laufenden Kandidatentest sichtbar geworden: Von 344 Symbolen mit
ueberhaupt einem Insiderkauf begannen 13 vor 2022 und 314 ab 2023. Die
Zahl informativer Symbole je Handelstag stieg von 2 (erste 250 Tage) auf
87 (letzte 250) - ein Faktor 40, der nichts mit Insiderhandel zu tun hat.

**Die Regel:** Ein Symbol, dessen Historie nicht vollstaendig geladen
werden kann, wird AUSGESCHLOSSEN. Ein halbes Panel ist schlimmer als
kein Panel - es sieht vollstaendig aus.
"""

from __future__ import annotations

import pandas as pd
import pytest

from alpaca_bot import edgar


def _filings(n: int) -> pd.DataFrame:
    """n Form-4-Meldungen, gleichmaessig ueber acht Jahre verteilt."""
    tage = pd.date_range("2018-01-01", "2026-01-01", periods=n, tz="UTC")
    return pd.DataFrame({
        "ticker": "TEST", "cik": "1", "form": "4", "filing_date": tage,
        "accession": [f"a{i}" for i in range(n)],
        "accessionNumber": [f"a-{i}" for i in range(n)],
        "url": "", })


def test_ueberschreitung_wirft_statt_zu_kuerzen(monkeypatch):
    """Der Kern: 436 Meldungen bei Grenze 150 sind ein Ausschluss."""
    monkeypatch.setattr(edgar, "filings", lambda *a, **k: _filings(436))

    with pytest.raises(edgar.ZuVieleMeldungen):
        edgar.insider_trades("TEST", since="2018-01-01", max_filings=150)


def test_unter_der_grenze_laeuft_normal(monkeypatch):
    """Wer unter der Grenze bleibt, wird vollstaendig geladen."""
    monkeypatch.setattr(edgar, "filings", lambda *a, **k: _filings(10))
    monkeypatch.setattr(edgar, "parse_form4", lambda *a, **k: [])

    df = edgar.insider_trades("TEST", since="2018-01-01", max_filings=150)
    assert df.empty  # parse_form4 liefert nichts - aber es hat nicht geworfen


def test_ohne_grenze_wird_nichts_ausgeschlossen(monkeypatch):
    """`max_filings=None` heisst: alles laden, keine Ausnahme."""
    monkeypatch.setattr(edgar, "filings", lambda *a, **k: _filings(900))
    monkeypatch.setattr(edgar, "parse_form4", lambda *a, **k: [])

    edgar.insider_trades("TEST", since="2018-01-01", max_filings=None)


def test_zuvielemeldungen_ist_ein_edgarerror():
    """Aufrufer, die nur `EdgarError` fangen, verlieren den Fall nicht -
    aber sie duerfen ihn nicht mit einem Netzfehler verwechseln."""
    assert issubclass(edgar.ZuVieleMeldungen, edgar.EdgarError)


def test_die_vorgaben_erzeugen_die_verzerrung_nicht_mehr():
    """`34_edgar_kandidat.py` lief mit `--since 2018-01-01 --max-filings 150`.

    Gemessen: 85 % der Symbole liegen ueber 150 Meldungen seit 2018.
    Die neuen Vorgaben (Fenster ab 09/2022, Grenze 400) lassen laut
    derselben Messung rund 90 % der Symbole vollstaendig durch.
    """
    import re
    from pathlib import Path

    quelle = Path(__file__).resolve().parents[1] / "scripts" / "34_edgar_kandidat.py"
    text = quelle.read_text()
    since = re.search(r'"--since", default="([\d-]+)"', text).group(1)
    grenze = int(re.search(r'"--max-filings", type=int, default=(\d+)', text).group(1))

    assert since >= "2022-01-01", (
        f"Fenster {since} ist zu lang fuer die Meldungsgrenze - "
        f"das erzeugt wieder die Zeitverzerrung aus §G41")
    assert grenze >= 400, (
        f"Grenze {grenze} schliesst zu viele Symbole aus (§G41)")
