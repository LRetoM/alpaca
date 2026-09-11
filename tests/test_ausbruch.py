"""Tests fuer die Ausbruch-Strategie (`alpaca_bot.ausbruch`).

Der Schwerpunkt liegt NICHT auf "rechnet die Rendite richtig", sondern
auf den drei Stellen, an denen ein Backtest dieser Art systematisch
luegt. Jede davon macht die Ergebnisse besser, als sie sind, und keine
faellt bei oberflaechlicher Betrachtung auf:

1. Lookahead beim Einstieg (Kauf zum Signalkurs statt zum Folgekurs)
2. Stop und Ziel in derselben Bar (welcher zuerst?)
3. Kosten, die nicht anfallen

Dazu die Filter, die eine Idee ueberhaupt erst handelbar machen.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from alpaca_bot import ausbruch
from alpaca_bot.ausbruch import AusbruchConfig, bars_aus_zeit, lauf


def _handelszeit_index(n: int, start_tag="2025-01-02") -> pd.DatetimeIndex:
    """`n` aufeinanderfolgende Bars INNERHALB der Handelszeit.

    Seit §G62 wirft `Kursdaten` alles ausserhalb 09:30-16:00 weg. Ein
    Testindex, der mit `date_range(freq="15min")` einfach durchlaeuft,
    verliert dadurch die Mehrheit seiner Bars - der Test prueft dann
    etwas anderes als gemeint. Deshalb wird hier wie in Wirklichkeit
    nach 26 Bars auf den naechsten Handelstag umgebrochen.
    """
    stempel, tag, im_tag = [], pd.Timestamp(start_tag), 0
    while len(stempel) < n:
        if tag.weekday() >= 5:              # Wochenende ueberspringen
            tag += pd.Timedelta(days=1)
            continue
        minute = 9 * 60 + 30 + 15 * im_tag
        stempel.append(pd.Timestamp(
            f"{tag:%Y-%m-%d} {minute // 60:02d}:{minute % 60:02d}",
            tz="America/New_York"))
        im_tag += 1
        if im_tag >= 26:
            im_tag = 0
            tag += pd.Timedelta(days=1)
    return pd.DatetimeIndex(stempel).tz_convert("UTC")


def _reihe(kurse, volumen=None, start="2025-01-02", freq=None):
    """Baut einen Bar-Datensatz aus einer Schlusskursliste.

    open == close des Vorgaengers, high/low knapp darum - so bleibt der
    Datensatz frei von Zufaelligkeiten, die einen Test verrauschen.
    """
    n = len(kurse)
    idx = _handelszeit_index(n, start)
    c = np.asarray(kurse, dtype=float)
    o = np.concatenate([[c[0]], c[:-1]])
    return pd.DataFrame(
        {"open": o, "high": np.maximum(o, c), "low": np.minimum(o, c),
         "close": c,
         "volume": np.full(n, 1e6) if volumen is None
                   else np.asarray(volumen, float)},
        index=idx,
    )


def _cfg(**over) -> AusbruchConfig:
    """Konfiguration ohne Filter und ohne Kosten - fuer Tests, die EINE
    Sache pruefen sollen und nicht das Zusammenspiel aller."""
    grund = dict(anstieg_pct=10.0, fenster_bars=2, min_dollar_volumen=0.0,
                 min_rel_volumen=0.0, min_preis=0.0, spanne_bps=0.0,
                 slippage_bps=0.0, verlust_pct=0.0, gewinn_pct=0.0,
                 trailing_pct=0.0, halten_bars=2, sperrfrist_bars=0,
                 eroeffnung_sperre_bars=0, schluss_sperre_bars=0,
                 max_positionen=5, positions_pct=50.0, startkapital=10_000.0,
                 vol_referenz_bars=26)
    grund.update(over)
    return AusbruchConfig(**grund)


# ---------------------------------------------------------------- Umrechnung
def test_zeit_in_bars():
    assert bars_aus_zeit(stunden=1) == 4
    assert bars_aus_zeit(stunden=2) == 8
    assert bars_aus_zeit(tage=1) == ausbruch.BARS_JE_TAG == 26
    # Ein Handelstag sind 6,5 Stunden, nicht 24 - sonst waere "1 Tag"
    # dasselbe wie "24 Stunden", und es ist fast das Vierfache.
    assert bars_aus_zeit(tage=1) != bars_aus_zeit(stunden=24)


# ---------------------------------------------------------------- Lookahead
def test_kauf_erfolgt_zum_folgebar_nicht_zum_signalkurs():
    """DER wichtigste Test des Moduls.

    Kurs springt auf Bar 3 von 100 auf 120. Das Signal entsteht auf
    dessen Schlusskurs. Gekauft werden darf erst zum EROEFFNUNGSKURS von
    Bar 4 - und der ist hier 120, nicht der Kurs vor dem Sprung.

    Wer zum Signalkurs kauft, kauft zu dem Kurs, der den Anstieg gerade
    erzeugt hat. Das ist der haeufigste Fehler in genau dieser
    Strategiefamilie.
    """
    kurse = [100, 100, 100, 120, 121, 122, 123, 124]
    erg = lauf({"AAA": _reihe(kurse)}, _cfg(fenster_bars=2, halten_bars=2))

    assert len(erg.trades) == 1
    t = erg.trades.iloc[0]
    assert t["einstieg_kurs"] == pytest.approx(120.0), (
        "Eingestiegen wurde nicht zum Eroeffnungskurs des Folgebars - "
        "das ist Lookahead."
    )
    assert t["einstieg_ts"] == _reihe(kurse).index[4]


def test_kein_signal_auf_dem_letzten_bar():
    """Auf dem letzten Bar kann nicht mehr gekauft werden - es gibt
    keinen Folgebar. Ein Signal dort waere ein stiller Lookahead."""
    kurse = [100, 100, 100, 100, 100, 130]     # Sprung ganz am Ende
    erg = lauf({"AAA": _reihe(kurse)}, _cfg())
    assert len(erg.trades) == 0


# ---------------------------------------------------------- Stop vor Ziel
def test_stop_gewinnt_wenn_eine_bar_beides_beruehrt():
    """Beruehrt eine Bar Stop UND Ziel, ist nicht zu erkennen, was
    zuerst kam. Die pessimistische Annahme ist die einzige ehrliche -
    die Gegenannahme laesst jede Konfiguration mit weitem Ziel und
    engem Stop kuenstlich gut aussehen.
    """
    idx = pd.date_range("2025-01-02 14:30", periods=6, freq="15min", tz="UTC")
    df = pd.DataFrame({
        "open":  [100, 100, 100, 120, 120, 120],
        "close": [100, 100, 120, 120, 120, 120],
        # Bar 4 laeuft von -20 % bis +20 % - beide Marken in einer Bar.
        "high":  [100, 100, 120, 120, 144, 120],
        "low":   [100, 100, 100, 120,  96, 120],
        "volume": [1e6] * 6,
    }, index=idx)

    # Sperrfrist hoch, damit der Kursverlauf nach dem Stop kein
    # zweites Signal ausloest - hier soll genau EINE Frage beantwortet
    # werden, nicht das Zusammenspiel mehrerer Regeln.
    erg = lauf({"AAA": df}, _cfg(fenster_bars=2, halten_bars=10,
                                 verlust_pct=10.0, gewinn_pct=10.0,
                                 sperrfrist_bars=999))
    assert len(erg.trades) == 1
    assert erg.trades.iloc[0]["grund"] == "stop", (
        "Bei Stop UND Ziel in derselben Bar muss der Stop gelten."
    )
    assert erg.trades.iloc[0]["rendite_pct"] < 0


# ------------------------------------------------------------------ Kosten
def test_kosten_senken_die_rendite_und_zwar_beidseitig():
    """Ohne Kosten und mit Kosten - die Differenz muss der halben
    Spanne plus Slippage auf BEIDEN Seiten entsprechen."""
    kurse = [100, 100, 100, 120, 120, 120, 120]
    ohne = lauf({"AAA": _reihe(kurse)}, _cfg())
    mit = lauf({"AAA": _reihe(kurse)},
               _cfg(spanne_bps=100.0, slippage_bps=50.0))

    r_ohne = ohne.trades.iloc[0]["rendite_pct"]
    r_mit = mit.trades.iloc[0]["rendite_pct"]
    assert r_mit < r_ohne
    # 100 bps Spanne -> 50 je Seite, plus 50 Slippage je Seite = 1 % je
    # Seite, rund 2 % je Rundlauf.
    assert (r_ohne - r_mit) == pytest.approx(2.0, abs=0.1)


def test_bruttorendite_bleibt_von_kosten_unberuehrt():
    """Die Bruttospalte muss zeigen, was der Kurs tat - sonst laesst
    sich nicht trennen, ob eine Idee am Signal oder an den Kosten
    scheitert."""
    kurse = [100, 100, 100, 120, 120, 120, 120]
    mit = lauf({"AAA": _reihe(kurse)},
               _cfg(spanne_bps=100.0, slippage_bps=50.0))
    t = mit.trades.iloc[0]
    assert t["rendite_brutto_pct"] > t["rendite_pct"]
    assert t["rendite_brutto_pct"] == pytest.approx(0.0, abs=1e-9)


# ------------------------------------------------------------------ Filter
def test_umsatzschub_filtert_bewegung_ohne_volumen():
    """Ein Ausbruch ohne Umsatz ist meist Rauschen im Orderbuch. Der
    Filter muss ihn verwerfen."""
    n = 60
    kurse = [100.0] * (n - 6) + [100, 100, 130, 130, 130, 130]
    leise = [1e6] * n                       # Sprung ohne Mehrumsatz
    laut = [1e6] * (n - 4) + [9e6] * 4      # Sprung MIT Umsatzschub

    cfg = _cfg(fenster_bars=2, min_rel_volumen=3.0, vol_referenz_bars=26)
    assert len(lauf({"AAA": _reihe(kurse, leise)}, cfg).trades) == 0
    assert len(lauf({"AAA": _reihe(kurse, laut)}, cfg).trades) >= 1


def test_mindestkurs_haelt_pennystocks_heraus():
    kurse = [1.0, 1.0, 1.0, 2.0, 2.0, 2.0]
    assert len(lauf({"AAA": _reihe(kurse)}, _cfg(min_preis=5.0)).trades) == 0
    assert len(lauf({"AAA": _reihe(kurse)}, _cfg(min_preis=0.5)).trades) >= 1


def test_hoechstanstieg_verwirft_kapitalmassnahmen():
    """Ein Sprung von +900 % ist fast immer ein Datenfehler oder ein
    Reverse Split - kein handelbarer Ausbruch."""
    kurse = [10, 10, 10, 100, 100, 100]
    assert len(lauf({"AAA": _reihe(kurse)},
                    _cfg(max_anstieg_pct=100.0)).trades) == 0


# ------------------------------------------------------------- Ausstiege
def test_zeitausstieg_greift_nach_halten_bars():
    kurse = [100, 100, 100, 120, 120, 120, 120, 120, 120]
    erg = lauf({"AAA": _reihe(kurse)}, _cfg(halten_bars=3))
    t = erg.trades.iloc[0]
    assert t["grund"] == "zeit"
    assert t["gehalten_bars"] == 3


def test_gewinnziel_verkauft_und_stop_verkauft():
    steigt = [100, 100, 100, 120, 126, 132, 140, 140]
    e1 = lauf({"AAA": _reihe(steigt)},
              _cfg(halten_bars=50, gewinn_pct=10.0))
    assert e1.trades.iloc[0]["grund"] == "gewinnziel"
    assert e1.trades.iloc[0]["rendite_pct"] > 0

    faellt = [100, 100, 100, 120, 114, 100, 90, 90]
    e2 = lauf({"AAA": _reihe(faellt)},
              _cfg(halten_bars=50, verlust_pct=10.0))
    assert e2.trades.iloc[0]["grund"] == "stop"
    assert e2.trades.iloc[0]["rendite_pct"] < 0


def test_sperrfrist_verhindert_sofortigen_wiedereinstieg():
    """Ohne Sperre kauft die Strategie denselben Ausbruch mehrfach."""
    kurse = [100, 100, 100, 120, 121, 122, 123, 124, 125, 126, 127, 128]
    ohne = lauf({"AAA": _reihe(kurse)}, _cfg(halten_bars=1, sperrfrist_bars=0))
    mit = lauf({"AAA": _reihe(kurse)}, _cfg(halten_bars=1, sperrfrist_bars=50))
    assert len(mit.trades) < len(ohne.trades)
    assert len(mit.trades) == 1


# ------------------------------------------------------------ Depotgrenzen
def test_hoechstzahl_positionen_wird_eingehalten():
    kurse = [100, 100, 100, 120, 120, 120, 120, 120]
    bars = {f"S{i}": _reihe(kurse) for i in range(10)}
    cfg = _cfg(max_positionen=3, max_neue_je_bar=10,
               positions_pct=20.0, halten_bars=50)
    erg = lauf(bars, cfg)
    assert len(erg.trades) <= 3


def test_neue_kaeufe_je_bar_sind_gedeckelt():
    """Bremse gegen den Fall, dass ein Marktbeben viele Signale zugleich
    ausloest und das ganze Depot in EINE Bewegung laeuft."""
    kurse = [100, 100, 100, 120, 120, 120, 120, 120]
    bars = {f"S{i}": _reihe(kurse) for i in range(10)}
    erg = lauf(bars, _cfg(max_positionen=10, max_neue_je_bar=2,
                          positions_pct=5.0, halten_bars=50))
    erste = pd.to_datetime(erg.trades["einstieg_ts"]).min()
    assert (pd.to_datetime(erg.trades["einstieg_ts"]) == erste).sum() <= 2


def test_depot_geht_nie_ins_minus():
    kurse = [100, 100, 100, 120, 60, 30, 10, 10]
    bars = {f"S{i}": _reihe(kurse) for i in range(8)}
    erg = lauf(bars, _cfg(max_positionen=8, positions_pct=50.0,
                          max_neue_je_bar=8, halten_bars=50))
    assert (erg.equity > 0).all(), "Die Depotkurve darf nie negativ werden."


# --------------------------------------------------------------- Kennzahlen
def test_kennzahlen_nennen_die_zahl_der_handelstage():
    """Massgeblich ist die Zahl der HANDELSTAGE, nicht der Trades (§B1).
    Fehlt diese Zahl, ist jede Aussage ueber den t-Wert wertlos."""
    kurse = [100, 100, 100, 120, 120, 120, 120]
    erg = lauf({"AAA": _reihe(kurse)}, _cfg())
    assert "n_handelstage" in erg.kennzahlen
    assert "t_wert" in erg.kennzahlen


def test_hinweise_nennen_survivorship_und_kosten():
    """Die beiden Vorbehalte muessen IMMER mitlaufen - auch bei einem
    glaenzenden Ergebnis. Gerade dann."""
    kurse = [100, 100, 100, 200, 200, 200, 200]
    erg = lauf({"AAA": _reihe(kurse)}, _cfg(max_anstieg_pct=500))
    text = " ".join(erg.hinweise).upper()
    assert "SURVIVORSHIP" in text
    assert "KOSTEN" in text


def test_kostenvorschau_der_config_ist_nachrechenbar():
    c = AusbruchConfig(spanne_bps=12.2, slippage_bps=3.0, halten_bars=26)
    assert c.kosten_je_rundlauf_pct() == pytest.approx(0.182, abs=1e-3)
    assert c.bars_pro_jahr_schaetzung() == pytest.approx(252.0)


def test_leere_eingabe_wirft_klar():
    with pytest.raises(ValueError):
        lauf({}, _cfg())


def test_schlusssperre_deckt_den_ganzen_bereich_ab():
    """Regression: Die Sperre prueft den BEREICH bis Handelsschluss.

    Vorher stand dort ein Vergleich auf genau den Bar
    `i + schluss_sperre_bars`. Bei einem Wert von 3 waren i+1 und i+2
    damit erlaubt und nur i+3 gesperrt - das Gegenteil der Absicht, und
    ohne Test faellt es nicht auf, weil der Vorgabewert 1 ist und dort
    beide Fassungen dasselbe tun.
    """
    # Ein voller Handelstag aus 8 Bars, danach ein zweiter Tag.
    idx = pd.DatetimeIndex(
        list(pd.date_range("2025-01-02 14:30", periods=8, freq="15min", tz="UTC"))
        + list(pd.date_range("2025-01-03 14:30", periods=8, freq="15min", tz="UTC"))
    )
    c = np.array([100, 100, 100, 100, 100, 130, 130, 130,
                  100, 100, 100, 100, 100, 100, 100, 100], float)
    o = np.concatenate([[c[0]], c[:-1]])
    df = pd.DataFrame({"open": o, "high": np.maximum(o, c),
                       "low": np.minimum(o, c), "close": c,
                       "volume": np.full(16, 1e6)}, index=idx)

    # Signal auf Bar 5 (Schlusskurs 130) -> Kauf waere Bar 6.
    # Bar 7 ist der letzte des Tages, also liegt Bar 6 genau eine
    # Position davor. Mit Sperre 3 muss der Kauf unterbleiben.
    offen = lauf({"AAA": df}, _cfg(fenster_bars=2, schluss_sperre_bars=0))
    zu = lauf({"AAA": df}, _cfg(fenster_bars=2, schluss_sperre_bars=3))

    assert len(offen.trades) >= 1, "Ohne Sperre muss der Kauf zustande kommen."
    assert len(zu.trades) == 0, (
        "Mit Sperre 3 darf kurz vor Handelsschluss nicht gekauft werden."
    )


# ------------------------------------------------- Die fuenf neuen Hebel
def test_gewinner_werden_laenger_gehalten():
    """`zeitausstieg_nur_bei_verlust`: Frist abgelaufen, Position im
    Gewinn -> weiterhalten. Das ist die Fassung von "Gewinner laufen
    lassen", die den Umschlag wirklich senkt."""
    # Steigt durchgehend: bei Ablauf der Frist im Plus.
    kurse = [100, 100, 100, 120, 122, 124, 126, 128, 130, 132, 134, 136]
    puenktlich = lauf({"AAA": _reihe(kurse)},
                      _cfg(halten_bars=2, sperrfrist_bars=999))
    laenger = lauf({"AAA": _reihe(kurse)},
                   _cfg(halten_bars=2, sperrfrist_bars=999,
                        zeitausstieg_nur_bei_verlust=True))

    assert puenktlich.trades.iloc[0]["gehalten_bars"] == 2
    assert laenger.trades.iloc[0]["gehalten_bars"] > 2, (
        "Eine Position im Gewinn muss ueber die Frist hinaus gehalten werden."
    )


def test_harte_grenze_beendet_auch_einen_gewinner():
    """Ohne absolute Obergrenze koennte eine Position bis Jahresende
    gehalten werden, solange sie einen Cent im Plus steht."""
    kurse = [100, 100, 100] + [120 + i for i in range(20)]
    erg = lauf({"AAA": _reihe(kurse)},
               _cfg(halten_bars=2, halten_bars_hart=5, sperrfrist_bars=999,
                    zeitausstieg_nur_bei_verlust=True))
    t = erg.trades.iloc[0]
    assert t["gehalten_bars"] == 5
    assert t["grund"] == "zeit_hart"


def test_verlierer_gehen_trotz_gewinner_regel_puenktlich():
    """Die Gegenprobe: Die Regel darf NUR Gewinner verlaengern."""
    kurse = [100, 100, 100, 120, 118, 116, 114, 112, 110]
    erg = lauf({"AAA": _reihe(kurse)},
               _cfg(halten_bars=2, sperrfrist_bars=999,
                    zeitausstieg_nur_bei_verlust=True))
    assert erg.trades.iloc[0]["gehalten_bars"] == 2
    assert erg.trades.iloc[0]["grund"] == "zeit"


def test_verzoegerter_einstieg_kauft_spaeter_und_teurer():
    """`einstieg_verzoegerung_bars` verschiebt den Kauf nach hinten.

    Wichtig: Eine Verzoegerung kann Lookahead nicht erzeugen, nur
    vermeiden - der Kauf liegt in jedem Fall NACH dem Signalbar.
    """
    kurse = [100, 100, 100, 120, 125, 130, 135, 140, 140]
    sofort = lauf({"AAA": _reihe(kurse)}, _cfg(halten_bars=1, sperrfrist_bars=999))
    spaeter = lauf({"AAA": _reihe(kurse)},
                   _cfg(halten_bars=1, sperrfrist_bars=999,
                        einstieg_verzoegerung_bars=2))

    e_sofort = sofort.trades.iloc[0]
    e_spaet = spaeter.trades.iloc[0]
    assert e_spaet["einstieg_ts"] > e_sofort["einstieg_ts"]
    assert e_spaet["einstieg_kurs"] > e_sofort["einstieg_kurs"]


def test_tageszeitfenster_begrenzt_die_einstiege():
    """Meldungen kommen ueberwiegend vor Handelsbeginn - ob ein
    Ausbruch am Vormittag anders laeuft als am Nachmittag, ist damit
    pruefbar."""
    kurse = [100, 100, 100, 120, 120, 120, 120, 120]
    offen = lauf({"AAA": _reihe(kurse)},
                 _cfg(tageszeit_von_bar=0, tageszeit_bis_bar=26))
    # Fenster liegt komplett hinter dem Signal -> kein Einstieg.
    zu = lauf({"AAA": _reihe(kurse)},
              _cfg(tageszeit_von_bar=20, tageszeit_bis_bar=26))
    assert len(offen.trades) >= 1
    assert len(zu.trades) == 0


# ------------------------------------------------- Handelszeit (§G62)
def _tagesreihe(zeiten, kurs=100.0):
    """Bars zu genau diesen New Yorker Uhrzeiten an einem Tag."""
    idx = pd.DatetimeIndex(
        [pd.Timestamp(f"2025-06-02 {z}", tz="America/New_York") for z in zeiten]
    ).tz_convert("UTC")
    n = len(idx)
    return pd.DataFrame(
        {"open": [kurs] * n, "high": [kurs] * n, "low": [kurs] * n,
         "close": [kurs] * n, "volume": [1e6] * n}, index=idx)


def test_vorboersliche_bars_werden_verworfen():
    """Regression zu BEFUNDE §G62 - der folgenschwerste Fund des Audits.

    Alpaca liefert 15-Minuten-Bars ab 08:00 und bis 16:45. Gemessen
    waren das 8,6 % aller Bars. Sie machen drei Dinge kaputt:
    die Eroeffnungssperre schuetzt die falsche Tageszeit, die
    Tageszeit-Suchachsen bedeuten jeden Tag etwas anderes, und die
    Strategie darf dort handeln, wo die Spanne ein Vielfaches der
    gemessenen 12,2 bps betraegt.
    """
    zeiten = ["08:00", "08:30", "09:00", "09:30", "12:00", "15:45",
              "16:00", "16:30"]
    kd = ausbruch.Kursdaten.aus_bars({"AAA": _tagesreihe(zeiten)})
    ny = kd.achse.tz_convert("America/New_York")
    minuten = ny.hour * 60 + ny.minute

    assert minuten.min() >= 9 * 60 + 30, "Vorboerslicher Bar durchgerutscht."
    assert minuten.max() < 16 * 60, "Nachboerslicher Bar durchgerutscht."
    assert kd.n_bars == 3, f"Erwartet 09:30/12:00/15:45, bekam {kd.n_bars}"


def test_erster_bar_des_tages_ist_die_eroeffnung():
    """`bar_im_tag = 0` MUSS 09:30 sein.

    Vor der Reparatur war es an den meisten Tagen 08:00 - die
    Eroeffnungssperre schuetzte damit die vorboersliche Phase und liess
    die eigentliche Eroeffnung ungeschuetzt. Gemessen: von 250 Tagen
    begannen 104 um 08:00 und nur 52 um 09:30.
    """
    zeiten = ["08:00", "08:45", "09:30", "09:45", "10:00", "15:45", "16:30"]
    kd = ausbruch.Kursdaten.aus_bars({"AAA": _tagesreihe(zeiten)})
    ny = kd.achse.tz_convert("America/New_York")
    erster = ny[kd.bar_im_tag == 0]
    assert len(erster) == 1
    assert erster[0].strftime("%H:%M") == "09:30"


def test_tageslaenge_entspricht_der_konstanten():
    """`BARS_JE_TAG = 26` steckt in der Horizontrechnung des
    gruppierten Tests. Waren vor-/nachboersliche Bars dabei, hatte ein
    Tag 27,6 bis 29,9 Bars - und der Horizont war entsprechend falsch."""
    zeiten = [f"{9 + (30 + 15 * i) // 60:02d}:{(30 + 15 * i) % 60:02d}"
              for i in range(26)]
    kd = ausbruch.Kursdaten.aus_bars({"AAA": _tagesreihe(zeiten)})
    assert kd.n_bars == ausbruch.BARS_JE_TAG == 26
    assert kd.letzter_des_tages.sum() == 1


def test_handelszeitfilter_laesst_sich_abschalten():
    """Nur fuer Tests - der Vorgabewert bleibt True."""
    zeiten = ["08:00", "09:30", "16:30"]
    kd = ausbruch.Kursdaten.aus_bars({"AAA": _tagesreihe(zeiten)},
                                     handelszeit_only=False)
    assert kd.n_bars == 3
