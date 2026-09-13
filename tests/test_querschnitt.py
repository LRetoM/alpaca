"""Tests fuer die Querschnitt-Familie (`querschnitt.py`).

Eine neue Strategiefamilie ist die Gelegenheit, die Fehler der alten
nicht zu wiederholen. Geprueft wird darum vor allem:

1. **Kein Lookahead.** Das Signal darf ausschliesslich Kurse bis zum
   Stichtag sehen. Geprueft mechanisch ueber `pit.audit_feature_function`
   und zusaetzlich durch einen konstruierten Fall: Ein Kurssprung NACH
   dem Stichtag darf das Signal nicht veraendern.
2. **Marktneutral heisst marktneutral.** Steigen alle Werte gleich, muss
   das Ergebnis null sein (minus Kosten) - sonst rechnet die Konstruktion
   den Marktanstieg mit, und genau das soll sie nicht.
3. **Kosten werden abgezogen**, und zwar je Seite.
4. **Die Perioden ueberlappen nicht** - sonst waere `horizont=1` im
   gruppierten Test falsch (§G12).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from alpaca_bot import ausbruch, pit, querschnitt as q
from tests.test_ausbruch import _handelszeit_index


def _kursdaten(kurse: dict[str, np.ndarray], n_bars: int):
    """Kursdaten aus je Symbol einer Bar-Reihe."""
    idx = _handelszeit_index(n_bars)
    bars = {}
    for sym, c in kurse.items():
        c = np.asarray(c, dtype="float64")
        o = np.concatenate([[c[0]], c[:-1]])
        bars[sym] = pd.DataFrame(
            {"open": o, "high": np.maximum(o, c) * 1.001,
             "low": np.minimum(o, c) * 0.999, "close": c,
             "volume": np.full(len(c), 500_000.0)}, index=idx)
    return ausbruch.Kursdaten.aus_bars(bars)


def _viele_symbole(n_symbole=120, n_bars=26 * 200, saat=5):
    """Ein Universum mit unterschiedlichen Trends je Symbol."""
    r = np.random.default_rng(saat)
    kurse = {}
    for i in range(n_symbole):
        drift = (i - n_symbole / 2) / n_symbole * 0.0008
        schritte = r.normal(drift, 0.01, n_bars)
        kurse[f"S{i:03d}"] = 50.0 * np.exp(np.cumsum(schritte))
    return _kursdaten(kurse, n_bars)


def _cfg(**kw):
    basis = dict(rueckblick_tage=20, luecke_tage=2, halten_tage=10,
                 anteil_pct=20.0, min_symbole=20,
                 min_dollar_volumen=0.0, min_preis=0.0)
    basis.update(kw)
    return q.QuerschnittConfig(**basis)


# --- 1. Kein Lookahead ------------------------------------------------

def test_signal_sieht_keine_zukunft_mechanisch():
    """Der Leck-Test aus pit.py auf die Signalfunktion selbst."""
    r = np.random.default_rng(3)
    tage = pd.bdate_range("2021-01-04", periods=300)
    df = pd.DataFrame(
        {f"S{i}": 50 * np.exp(np.cumsum(r.normal(0, 0.01, 300)))
         for i in range(12)}, index=tage)

    def bauen(k: pd.DataFrame) -> pd.DataFrame:
        """Signalwerte je Stichtag - als Tabelle, wie pit.py sie erwartet."""
        cfg = _cfg()
        zeilen = {}
        for i in range(40, len(k)):
            zeilen[k.index[i]] = q.signal_werte(k.iloc[:i + 1], cfg)
        return pd.DataFrame(zeilen).T.reindex(k.index)

    ergebnis = pit.audit_feature_function(bauen, df)
    ergebnis.raise_if_leaking()


def test_kurssprung_nach_dem_stichtag_aendert_das_signal_nicht():
    """Der konstruierte Fall: Was nach dem Stichtag passiert, darf die
    Rangfolge am Stichtag nicht beruehren."""
    tage = pd.bdate_range("2021-01-04", periods=100)
    basis = pd.DataFrame(
        {"A": np.linspace(10, 20, 100), "B": np.linspace(20, 10, 100)},
        index=tage)
    cfg = _cfg()

    vorher = q.signal_werte(basis.iloc[:61], cfg)
    manipuliert = basis.copy()
    manipuliert.iloc[61:, 0] *= 5.0        # A explodiert - NACH dem Stichtag
    nachher = q.signal_werte(manipuliert.iloc[:61], cfg)

    pd.testing.assert_series_equal(vorher, nachher)


# --- 2. Marktneutral ---------------------------------------------------

def test_gleichmaessiger_marktanstieg_ergibt_null():
    """Steigen alle Werte identisch, ist der Long-Short-Abstand null.

    Das ist die eingebaute Benchmark (§J.4): Ein Marktanstieg allein darf
    kein Ergebnis erzeugen.
    """
    n_bars = 26 * 200
    steigend = 50.0 * np.exp(np.linspace(0, 0.5, n_bars))
    kd = _kursdaten({f"S{i:03d}": steigend.copy() for i in range(60)}, n_bars)
    erg = q.lauf(kd, _cfg(min_symbole=20, spanne_bps=0.0, slippage_bps=0.0))
    assert not erg.perioden.empty
    assert erg.perioden["brutto_pct"].abs().max() < 1e-6


def test_nur_long_nimmt_den_marktanstieg_mit():
    """Gegenprobe: Ohne Short-Seite steckt der Anstieg voll im Ergebnis -
    genau deshalb ist die Variante nur ein Vergleich, kein Befund."""
    n_bars = 26 * 200
    steigend = 50.0 * np.exp(np.linspace(0, 0.5, n_bars))
    kd = _kursdaten({f"S{i:03d}": steigend.copy() for i in range(60)}, n_bars)
    erg = q.lauf(kd, _cfg(min_symbole=20, marktneutral=False,
                          spanne_bps=0.0, slippage_bps=0.0))
    assert erg.perioden["brutto_pct"].mean() > 0.5


# --- 3. Kosten --------------------------------------------------------

def test_kosten_werden_je_seite_abgezogen():
    kd = _viele_symbole(n_symbole=60, n_bars=26 * 150)
    ohne = q.lauf(kd, _cfg(spanne_bps=0.0, slippage_bps=0.0))
    mit = q.lauf(kd, _cfg(spanne_bps=12.2, slippage_bps=3.0))
    # Verglichen wird die DIFFERENZ zweier Laeufe, die sich nur in Spanne
    # und Slippage unterscheiden - die Regulierungsgebuehr steckt in
    # beiden und kuerzt sich heraus. So prueft der Test genau das, was
    # sein Name sagt, und nicht nebenbei das Gebuehrenmodell.
    # Je Periode skaliert mit dem tatsaechlichen Umschlag: Was im Korb
    # bleibt, wird nicht gehandelt und kostet keine Spanne.
    erwartet = (12.2 + 2 * 3.0) / 100.0 * 2.0 * mit.perioden["umschlag"]
    assert ohne.perioden["brutto_pct"].equals(mit.perioden["brutto_pct"])
    diff = ohne.perioden["netto_pct"] - mit.perioden["netto_pct"]
    assert np.allclose(diff, erwartet)


def test_kostenlast_macht_kurze_haltedauer_teuer():
    """Die Zahl, die diese ganze Familie rechtfertigt."""
    kurz = q.QuerschnittConfig(halten_tage=2).kostenlast_pct_jahr()
    lang = q.QuerschnittConfig(halten_tage=21).kostenlast_pct_jahr()
    assert kurz > 30.0
    assert lang < 5.0


# --- 4. Perioden und Struktur -----------------------------------------

def test_perioden_ueberlappen_nicht():
    """Sonst waere horizont=1 im gruppierten Test falsch (§G12)."""
    kd = _viele_symbole(n_symbole=60, n_bars=26 * 200)
    erg = q.lauf(kd, _cfg(halten_tage=10))
    p = erg.perioden
    assert len(p) > 3
    for i in range(len(p) - 1):
        assert p["ende"].iloc[i] <= p["stichtag"].iloc[i + 1]


def test_liquiditaetsgrenzen_greifen():
    """§G60: Ohne Untergrenzen waehlt die Auswertung Werte, fuer die die
    Kostenannahme nicht gemessen ist."""
    kd = _viele_symbole(n_symbole=60, n_bars=26 * 150)
    streng = q.lauf(kd, _cfg(min_dollar_volumen=1e15, min_symbole=1))
    assert streng.perioden.empty


def test_unbekanntes_signal_ist_ein_fehler():
    kd = _viele_symbole(n_symbole=40, n_bars=26 * 120)
    with pytest.raises(ValueError, match="Unbekanntes Signal"):
        q.lauf(kd, _cfg(signal="gibtesnicht"))


def test_alle_signale_laufen_durch():
    kd = _viele_symbole(n_symbole=80, n_bars=26 * 200)
    for name in q.SIGNALE:
        erg = q.lauf(kd, _cfg(signal=name))
        assert not erg.perioden.empty, name
        assert "t_wert" in erg.kennzahlen


def test_umkehr_ist_das_vorzeichen_von_momentum():
    tage = pd.bdate_range("2021-01-04", periods=100)
    k = pd.DataFrame({"A": np.linspace(10, 20, 100),
                      "B": np.linspace(20, 10, 100)}, index=tage)
    cfg = _cfg()
    mom = q.signal_werte(k, q.QuerschnittConfig(
        signal="momentum", rueckblick_tage=20, luecke_tage=2))
    umk = q.signal_werte(k, q.QuerschnittConfig(
        signal="umkehr", rueckblick_tage=20, luecke_tage=2))
    pd.testing.assert_series_equal(mom, -umk)


def test_hinweise_nennen_die_vorbehalte():
    """Eine Warnung, die fehlt, ist keine."""
    kd = _viele_symbole(n_symbole=60, n_bars=26 * 150)
    erg = q.lauf(kd, _cfg())
    text = " ".join(erg.hinweise)
    assert "KOSTEN" in text
    assert "MARKTNEUTRAL" in text
    assert "EINSTIEG AUF DEM SCHLUSS" in text
    # Seit die Leihe im Modell steckt, heissen die beiden Short-Hinweise
    # LEIHE (eine Zahl) und VERFUEGBARKEIT (weiter ein Vorbehalt).
    assert "LEIHE" in text
    assert "VERFUEGBARKEIT" in text


def test_tageskurse_haben_einen_wert_je_handelstag():
    kd = _viele_symbole(n_symbole=10, n_bars=26 * 50)
    kurse, umsatz = q.tageskurse(kd)
    assert len(kurse) == 50
    assert kurse.shape == umsatz.shape
    assert kurse.index.is_monotonic_increasing
    assert not kurse.index.has_duplicates


# --- 5. Der NaN-Fehler vom 12.09.2026 ---------------------------------

def test_fehlender_letzter_bar_macht_den_tag_nicht_unbrauchbar():
    """Handelt ein Wert im letzten Bar des Tages nicht, war frueher der
    ganze Tagesschlusskurs NaN - gemessen 15 % aller Tage, und nur 1 von
    2.004 Symbolen war gar nicht betroffen. Ein `dropna()` im Signal
    waehlte dann nicht die liquidesten Werte, sondern die zufaellig in
    der letzten Viertelstunde aktiven.
    """
    n_bars = 26 * 40
    c = np.linspace(50.0, 60.0, n_bars)
    kd = _kursdaten({"AAA": c.copy(), "BBB": c.copy()}, n_bars)

    # Im letzten Bar des dritten Tages handelt BBB nicht.
    letzte = np.flatnonzero(np.asarray(kd.letzter_des_tages))
    o, h, l, cc, v = kd.arrays["BBB"]
    cc = np.array(cc, dtype="float64")
    cc[letzte[2]] = np.nan
    kd.arrays["BBB"] = (o, h, l, cc, v)

    kurse, _ = q.tageskurse(kd)
    assert np.isfinite(kurse["BBB"].iloc[2]), \
        "Ein fehlender Schlussbar darf den Tageskurs nicht loeschen"
    assert kurse["BBB"].iloc[2] == pytest.approx(kurse["BBB"].iloc[1])


def test_dauerhaft_totes_symbol_faellt_heraus():
    """Vorwaerts fuellen ja - aber begrenzt. Ein Wert, der eine Woche
    nicht handelt, darf nicht mit altem Kurs als lebendig gelten."""
    n_bars = 26 * 40
    c = np.linspace(50.0, 60.0, n_bars)
    kd = _kursdaten({"AAA": c.copy(), "TOT": c.copy()}, n_bars)
    letzte = np.flatnonzero(np.asarray(kd.letzter_des_tages))
    o, h, l, cc, v = kd.arrays["TOT"]
    cc = np.array(cc, dtype="float64")
    cc[letzte[10]:] = np.nan          # ab Tag 10 gar kein Handel mehr
    kd.arrays["TOT"] = (o, h, l, cc, v)

    kurse, _ = q.tageskurse(kd, ffill_tage=5)
    assert np.isfinite(kurse["TOT"].iloc[12])     # noch im Fuellfenster
    assert not np.isfinite(kurse["TOT"].iloc[-1])  # laengst darueber


def test_umsatz_wird_nicht_gefuellt():
    """Kein Handel heisst kein Umsatz - genau das soll der
    Liquiditaetsfilter sehen."""
    kd = _viele_symbole(n_symbole=10, n_bars=26 * 40)
    _kurse, umsatz = q.tageskurse(kd)
    assert (umsatz >= 0).all().all()


# --- 6. Ueberlappende Tranchen (versatz_tage) --------------------------

def test_versatz_erhoeht_die_zahl_der_beobachtungen():
    """Der Zweck: aus 20 Perioden werden 60, ohne mehr zu handeln."""
    kd = _viele_symbole(n_symbole=60, n_bars=26 * 300)
    ohne = q.lauf(kd, _cfg(halten_tage=30, versatz_tage=0))
    mit = q.lauf(kd, _cfg(halten_tage=30, versatz_tage=10))
    assert len(mit.perioden) > 2.5 * len(ohne.perioden)


def test_versatz_aendert_die_kostenlast_nicht():
    """Drei Tranchen schichten jede nur alle `halten_tage` um - der
    Umschlag je Kapitaleinheit bleibt derselbe. Wer hier die Schrittweite
    einsetzt, verdreifacht die Kosten ohne Grund."""
    a = q.QuerschnittConfig(halten_tage=63, versatz_tage=0)
    b = q.QuerschnittConfig(halten_tage=63, versatz_tage=21)
    assert a.kostenlast_pct_jahr() == pytest.approx(b.kostenlast_pct_jahr())


def test_ueberlappung_wird_dem_t_test_gemeldet():
    """DER Test. Ohne `horizont` liegt die Fehlalarmquote bei 39,5 %
    statt 5 (§G12) - die dreifache Beobachtungszahl waere dann ein
    dreifach ueberschaetzter t-Wert."""
    assert q.QuerschnittConfig(halten_tage=63,
                               versatz_tage=63).horizont_perioden() == 1
    assert q.QuerschnittConfig(halten_tage=63,
                               versatz_tage=21).horizont_perioden() == 3
    assert q.QuerschnittConfig(halten_tage=60,
                               versatz_tage=10).horizont_perioden() == 6

    kd = _viele_symbole(n_symbole=60, n_bars=26 * 300)
    erg = q.lauf(kd, _cfg(halten_tage=30, versatz_tage=10))
    assert erg.kennzahlen["horizont_perioden"] == 3


def test_ohne_versatz_bleibt_alles_wie_vorher():
    """Rueckwaertskompatibilitaet: versatz_tage=0 heisst nicht
    ueberlappend."""
    kd = _viele_symbole(n_symbole=60, n_bars=26 * 200)
    a = q.lauf(kd, _cfg(halten_tage=20, versatz_tage=0))
    b = q.lauf(kd, _cfg(halten_tage=20, versatz_tage=20))
    assert len(a.perioden) == len(b.perioden)
    assert a.kennzahlen["mittel_pct"] == pytest.approx(b.kennzahlen["mittel_pct"])
    assert a.kennzahlen["horizont_perioden"] == 1


# --- 7. Leihkosten der Short-Seite -------------------------------------

def test_leihe_wird_abgezogen():
    """Eine Short-Position kostet Leihe, jeden Tag den sie offen ist."""
    kd = _viele_symbole(n_symbole=60, n_bars=26 * 200)
    ohne = q.lauf(kd, _cfg(leihe_bps_jahr=0.0))
    mit = q.lauf(kd, _cfg(leihe_bps_jahr=300.0))
    diff = ohne.perioden["netto_pct"] - mit.perioden["netto_pct"]
    erwartet = 300.0 / 100.0 * (10 / 252.0)     # halten_tage=10 im _cfg
    assert np.allclose(diff, erwartet)
    assert ohne.perioden["brutto_pct"].equals(mit.perioden["brutto_pct"])


def test_leihe_ist_zeitabhaengig_nicht_handelsabhaengig():
    """Wer laenger haelt, zahlt mehr Leihe - das ist die Gegenkraft zu
    'lange halten senkt die Spannenkosten'."""
    kurz = q.QuerschnittConfig(halten_tage=21, leihe_bps_jahr=300.0)
    lang = q.QuerschnittConfig(halten_tage=63, leihe_bps_jahr=300.0)
    assert lang.leihe_je_periode_pct() == pytest.approx(
        3.0 * kurz.leihe_je_periode_pct())
    # Auf Jahresbasis dagegen gleich - Leihe laeuft unabhaengig vom Umschlag.
    assert (lang.kostenlast_pct_jahr() - lang.leihe_bps_jahr / 100.0
            < kurz.kostenlast_pct_jahr() - kurz.leihe_bps_jahr / 100.0)


def test_nur_long_zahlt_keine_leihe():
    cfg = q.QuerschnittConfig(marktneutral=False, leihe_bps_jahr=300.0)
    assert cfg.leihe_je_periode_pct() == 0.0


def test_hinweise_nennen_die_leihe_konkret():
    """Der frueher blosse Vorbehalt ist jetzt eine Zahl im Modell - der
    Hinweistext muss das sagen, nicht mehr 'nicht modelliert'."""
    kd = _viele_symbole(n_symbole=60, n_bars=26 * 150)
    erg = q.lauf(kd, _cfg(leihe_bps_jahr=50.0))
    text = " ".join(erg.hinweise)
    assert "LEIHE" in text
    assert "NICHT modelliert" not in text.split("VERFUEGBARKEIT")[0]
    assert "VERFUEGBARKEIT" in text


# --- 8. Gewichtung innerhalb des Korbs ---------------------------------

def test_gleichgewichtung_ist_die_vorgabe():
    kd = _viele_symbole(n_symbole=40, n_bars=26 * 120)
    kurse, _ = q.tageskurse(kd)
    g = q.gewichte(kurse, ["S000", "S001", "S002", "S003"], _cfg())
    assert np.allclose(g.values, 0.25)
    assert g.sum() == pytest.approx(1.0)


def test_inv_vola_gewichtet_ruhige_werte_hoeher():
    """Der Kern: gleicher Risikobeitrag statt gleicher Einsatz."""
    tage = pd.bdate_range("2021-01-04", periods=120)
    r = np.random.default_rng(2)
    k = pd.DataFrame({
        "RUHIG": 100 * np.exp(np.cumsum(r.normal(0, 0.002, 120))),
        "WILD": 100 * np.exp(np.cumsum(r.normal(0, 0.030, 120))),
    }, index=tage)
    g = q.gewichte(k, ["RUHIG", "WILD"], _cfg(gewichtung="inv_vola"))
    assert g["RUHIG"] > g["WILD"]
    assert g.sum() == pytest.approx(1.0)


def test_inv_vola_faellt_bei_zu_wenig_historie_auf_gleich_zurueck():
    """Ein stiller Ausfall waere hier besonders heikel - er saehe aus wie
    Vola-Gewichtung und waere keine."""
    tage = pd.bdate_range("2021-01-04", periods=4)
    k = pd.DataFrame({"A": [10.0, 11, 12, 13], "B": [20.0, 19, 18, 17]},
                     index=tage)
    g = q.gewichte(k, ["A", "B"], _cfg(gewichtung="inv_vola"))
    assert np.allclose(g.values, 0.5)


def test_ein_extrem_ruhiger_wert_dominiert_das_depot_nicht():
    """Ohne Untergrenze waere 1/Vola bei Vola nahe null eine Wette auf
    einen einzigen Wert statt einer Verteilung."""
    tage = pd.bdate_range("2021-01-04", periods=120)
    r = np.random.default_rng(4)
    k = pd.DataFrame({
        "FLACH": np.full(120, 50.0),                     # Vola exakt 0
        "A": 100 * np.exp(np.cumsum(r.normal(0, 0.02, 120))),
        "B": 100 * np.exp(np.cumsum(r.normal(0, 0.02, 120))),
    }, index=tage)
    g = q.gewichte(k, ["FLACH", "A", "B"], _cfg(gewichtung="inv_vola"))
    assert g["FLACH"] < 0.8, "ein einzelner Wert darf das Depot nicht tragen"
    assert g.sum() == pytest.approx(1.0)


def test_gewichte_sehen_keine_zukunft():
    """Die Gewichte duerfen nur aus Kursen bis zum Stichtag stammen."""
    tage = pd.bdate_range("2021-01-04", periods=120)
    k = pd.DataFrame({"A": np.linspace(10, 20, 120),
                      "B": np.linspace(20, 10, 120)}, index=tage)
    vorher = q.gewichte(k.iloc[:80], ["A", "B"], _cfg(gewichtung="inv_vola"))
    k2 = k.copy()
    k2.iloc[80:, 0] *= 10.0        # A wird NACH dem Stichtag wild
    nachher = q.gewichte(k2.iloc[:80], ["A", "B"], _cfg(gewichtung="inv_vola"))
    pd.testing.assert_series_equal(vorher, nachher)


def test_gewichtung_aendert_das_ergebnis_ueberhaupt():
    kd = _viele_symbole(n_symbole=80, n_bars=26 * 250)
    a = q.lauf(kd, _cfg(gewichtung="gleich"))
    b = q.lauf(kd, _cfg(gewichtung="inv_vola"))
    assert not np.allclose(a.perioden["brutto_pct"], b.perioden["brutto_pct"])
    assert len(a.perioden) == len(b.perioden)


# --- 9. Regulierungsgebuehren (SEC/FINRA) ------------------------------

def test_gebuehren_sind_nicht_null_trotz_kommissionsfrei():
    """Alpaca nimmt keine Kommission - SEC und FINRA schon."""
    cfg = q.QuerschnittConfig()
    assert cfg.regulierung_bps(50.0) > 0


def test_gebuehren_kommen_aus_dem_geprueften_kostenmodul():
    """Eigene Zahlen waeren eine zweite Wahrheit, die beim naechsten
    SEC-Satzwechsel veraltet."""
    from alpaca_bot.costs import DEFAULT_FEES
    cfg = q.QuerschnittConfig()
    erwartet = (DEFAULT_FEES.sec_fee_per_million / 1e6 * 1e4
                + DEFAULT_FEES.finra_taf_per_share / 50.0 * 1e4)
    assert cfg.regulierung_bps(50.0) == pytest.approx(erwartet)


def test_finra_gebuehr_haengt_am_stueckpreis():
    """Bei einem 5-Dollar-Papier zehnmal so teuer wie bei 50 Dollar -
    die TAF ist je AKTIE, nicht je Dollar."""
    cfg = q.QuerschnittConfig()
    billig = cfg.regulierung_bps(5.0)
    teuer = cfg.regulierung_bps(50.0)
    assert billig > teuer * 2


def test_gebuehren_stecken_in_der_periodenrendite():
    kd = _viele_symbole(n_symbole=60, n_bars=26 * 150)
    erg = q.lauf(kd, _cfg(spanne_bps=0.0, slippage_bps=0.0,
                          leihe_bps_jahr=0.0))
    # Ohne Spanne, Slippage und Leihe bleibt nur die Regulierung uebrig -
    # und die ist echt groesser als null.
    diff = (erg.perioden["brutto_pct"] - erg.perioden["netto_pct"])
    assert (diff > 0).all()


def test_gebuehrensaetze_sind_nicht_veraltet():
    """Veraltete Saetze machen jede Kostenrechnung falsch - das Modul
    fuehrt selbst ein Pruefdatum."""
    from alpaca_bot.costs import DEFAULT_FEES
    assert not DEFAULT_FEES.is_stale(), (
        f"Gebuehrensaetze zuletzt geprueft am {DEFAULT_FEES.verified} - "
        f"nachschlagen (SEC passt jaehrlich an).")


def test_rundlauf_rechnet_kauf_ueber_und_verkauf_unter_dem_kurs():
    """Der angezeigte Kurs wird nie gehandelt.

    Gekauft wird zum Briefkurs plus Slippage, verkauft zum Geldkurs minus
    Slippage. Ein Rundlauf kostet deshalb die VOLLE Spanne (zweimal die
    halbe) plus ZWEIMAL Slippage - nicht einmal.
    """
    cfg = q.QuerschnittConfig(spanne_bps=30.0, slippage_bps=3.0)
    halbe_seite = cfg.spanne_bps / 2 + cfg.slippage_bps      # 18 bps
    rundlauf_ohne_gebuehr = 2 * halbe_seite                   # 36 bps
    assert cfg.kosten_je_rundlauf_pct(50.0) * 100.0 == pytest.approx(
        rundlauf_ohne_gebuehr + cfg.regulierung_bps(50.0))


def test_hinweis_erklaert_den_einkaufspreis():
    kd = _viele_symbole(n_symbole=60, n_bars=26 * 150)
    erg = q.lauf(kd, _cfg(spanne_bps=30.0))
    text = " ".join(erg.hinweise)
    assert "EINKAUF UEBER" in text
    assert "NIE gehandelt" in text
    assert "Marktwirkung" in text


# --- 10. Umschlag: nur das Gehandelte kostet ---------------------------

def test_unveraenderter_korb_kostet_nichts_ausser_leihe():
    """Wer nichts handelt, zahlt keine Spanne. Die erste Fassung
    unterstellte 100 % Umschlag je Periode - deutlich zu pessimistisch."""
    n_bars = 26 * 250
    # Feste Rangfolge: Symbol i steigt immer staerker als i-1, also bleibt
    # der Korb ueber alle Perioden derselbe.
    kurse = {f"S{i:03d}": 50.0 * np.exp(np.linspace(0, 0.002 * i, n_bars))
             for i in range(60)}
    kd = _kursdaten(kurse, n_bars)
    erg = q.lauf(kd, _cfg(halten_tage=10, leihe_bps_jahr=0.0))
    p = erg.perioden
    assert p["umschlag"].iloc[0] == 1.0, "der erste Korb wird aufgebaut"
    assert p["umschlag"].iloc[1:].max() < 0.2, \
        "ein stabiler Korb darf nicht jede Periode voll umgeschlagen werden"
    assert p["kosten_pct"].iloc[1:].max() < p["kosten_pct"].iloc[0]


def test_umschlag_wird_je_tranche_verglichen():
    """Bei ueberlappenden Tranchen liegt die naechste Umschichtung
    DERSELBEN Tranche mehrere Schritte spaeter. Wer nur einen Korb merkt,
    vergleicht Tranche A mit Tranche B und misst Umschlag, den es nicht
    gibt."""
    n_bars = 26 * 300
    kurse = {f"S{i:03d}": 50.0 * np.exp(np.linspace(0, 0.002 * i, n_bars))
             for i in range(60)}
    kd = _kursdaten(kurse, n_bars)
    erg = q.lauf(kd, _cfg(halten_tage=30, versatz_tage=10,
                          leihe_bps_jahr=0.0))
    p = erg.perioden
    # Drei Tranchen -> die ersten drei Koerbe sind Aufbau, danach stabil.
    assert (p["umschlag"].iloc[:3] == 1.0).all()
    assert p["umschlag"].iloc[3:].max() < 0.2


def test_wechselnder_korb_kostet_voll():
    """Gegenprobe: Aendert sich die Rangfolge staendig, bleibt der
    Umschlag hoch - die Ersparnis darf nicht pauschal sein."""
    kd = _viele_symbole(n_symbole=60, n_bars=26 * 200, saat=11)
    erg = q.lauf(kd, _cfg(halten_tage=10, rueckblick_tage=5, luecke_tage=0))
    assert erg.perioden["umschlag"].iloc[1:].mean() > 0.4


def test_umschlag_steht_in_den_kennzahlen():
    kd = _viele_symbole(n_symbole=60, n_bars=26 * 150)
    k = q.lauf(kd, _cfg()).kennzahlen
    assert 0.0 <= k["umschlag_mittel"] <= 1.0
    assert k["kosten_mittel_pct"] > 0


# --- 11. Realisierte Vola aus Intraday-Bars ----------------------------

def test_realisierte_vola_trennt_ruhig_von_wild():
    n_bars = 26 * 60
    r = np.random.default_rng(9)
    ruhig = 50.0 * np.exp(np.cumsum(r.normal(0, 0.0005, n_bars)))
    wild = 50.0 * np.exp(np.cumsum(r.normal(0, 0.008, n_bars)))
    kd = _kursdaten({"RUHIG": ruhig, "WILD": wild}, n_bars)
    v = q.tagesvola(kd)
    assert v["WILD"].mean() > 5 * v["RUHIG"].mean()


def test_realisierte_vola_hat_einen_wert_je_handelstag():
    kd = _viele_symbole(n_symbole=8, n_bars=26 * 40)
    v = q.tagesvola(kd)
    kurse, _ = q.tageskurse(kd)
    assert len(v) == len(kurse) == 40
    assert list(v.columns) == sorted(v.columns)


def test_uebernachtsprung_zaehlt_nicht_zur_intraday_vola():
    """Der erste Bar eines Tages traegt den Sprung vom Vortagesschluss -
    er gehoert nicht in die Intraday-Schaetzung."""
    n_bars = 26 * 30
    c = np.full(n_bars, 50.0)
    kd = _kursdaten({"A": c.copy()}, n_bars)
    # Innerhalb der Tage passiert nichts, nur ueber Nacht springt es.
    letzte = np.flatnonzero(np.asarray(kd.letzter_des_tages))
    o, h, l, cc, v = kd.arrays["A"]
    cc = np.array(cc, dtype="float64")
    for i in letzte[:-1]:
        cc[i + 1:] *= 1.05          # Sprung jeweils zum Tagesbeginn
    kd.arrays["A"] = (o, h, l, cc, v)
    vola = q.tagesvola(kd)
    assert vola["A"].iloc[1:].max() < 1e-6, \
        "Uebernachtsprung darf nicht als Intraday-Schwankung zaehlen"


def test_realisierte_vola_ist_praeziser_als_tagesvola():
    """Der eigentliche Grund fuer den Aufwand: derselbe Schaetzer fuer
    dieselbe Groesse, aber mit deutlich kleinerem Schaetzfehler.

    Gemessen ueber viele Symbole gleicher wahrer Vola: Die Streuung der
    Schaetzungen untereinander muss kleiner sein.
    """
    n_bars = 26 * 80
    r = np.random.default_rng(21)
    kurse = {f"S{i:02d}": 50.0 * np.exp(np.cumsum(r.normal(0, 0.004, n_bars)))
             for i in range(40)}
    kd = _kursdaten(kurse, n_bars)

    aus_intraday = q.tagesvola(kd).mean()
    kurse_tag, _ = q.tageskurse(kd)
    aus_tagesschluss = kurse_tag.pct_change().std() * 100.0

    streuung_intraday = aus_intraday.std() / aus_intraday.mean()
    streuung_tag = aus_tagesschluss.std() / aus_tagesschluss.mean()
    assert streuung_intraday < streuung_tag, (
        f"Intraday-Schaetzer streut {streuung_intraday:.3f}, "
        f"Tagesschaetzer {streuung_tag:.3f} - erwartet war das Gegenteil")


def test_gewichtung_nutzt_die_realisierte_vola():
    """Der Lauf muss den besseren Schaetzer auch wirklich benutzen."""
    kd = _viele_symbole(n_symbole=60, n_bars=26 * 200)
    kurse, _ = q.tageskurse(kd)
    vola = q.tagesvola(kd)
    syms = list(kurse.columns[:10])
    mit = q.gewichte(kurse, syms, _cfg(gewichtung="inv_vola"), vola_bis=vola)
    ohne = q.gewichte(kurse, syms, _cfg(gewichtung="inv_vola"))
    assert not np.allclose(mit.values, ohne.values)
    assert mit.sum() == pytest.approx(1.0)
