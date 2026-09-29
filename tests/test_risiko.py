"""Risiko-Dach - die Grenze, die keine Strategie kennt.

Diese Tests sind die wichtigsten im Projekt: Sie pruefen die Mechanik,
die verhindert, dass ein Bot mit fehlerhafter Logik das Konto leerhandelt.
Faellt hier ein Test, ist echtes Geld nicht mehr vertretbar.
"""

from __future__ import annotations

import pandas as pd
import pytest

from alpaca_bot import risiko


def konto(equity=100_000.0, cash=50_000.0, last=None, blockiert=False) -> dict:
    return {"equity": equity, "cash": cash, "last_equity": last or equity,
            "portfolio_value": equity, "trading_blocked": blockiert}


def positionen(n=3, wert=10_000.0) -> pd.DataFrame:
    return pd.DataFrame(
        {"qty": [1.0] * n, "current_price": [wert] * n},
        index=[f"S{i}" for i in range(n)],
    )


G = risiko.Risikogrenzen()


class TestDrawdownSperre:
    def test_unter_der_grenze_frei(self, temp_store):
        risiko.pruefe_konto(konto=konto(100_000.), positionen=positionen(),
                            grenzen=G, store=temp_store)
        f = risiko.pruefe_konto(konto=konto(85_000.), positionen=positionen(),
                                grenzen=G, store=temp_store)
        assert f.ok
        assert f.kennzahlen["drawdown_pct"] == pytest.approx(0.15, abs=0.01)

    def test_ueber_der_grenze_sperrt(self, temp_store):
        risiko.pruefe_konto(konto=konto(100_000.), positionen=positionen(),
                            grenzen=G, store=temp_store)
        f = risiko.pruefe_konto(konto=konto(75_000.), positionen=positionen(),
                                grenzen=G, store=temp_store)
        assert not f.ok
        assert "Drawdown" in f.gruende[0]

    def test_sperre_ueberlebt_erholung(self, temp_store):
        """Eine Sperre, die sich bei Erholung selbst aufhebt, kauft genau
        in den Crash zurueck, wegen dem sie ausgeloest hat."""
        risiko.pruefe_konto(konto=konto(100_000.), positionen=positionen(),
                            grenzen=G, store=temp_store)
        risiko.pruefe_konto(konto=konto(75_000.), positionen=positionen(),
                            grenzen=G, store=temp_store)
        f = risiko.pruefe_konto(konto=konto(120_000.), positionen=positionen(),
                                grenzen=G, store=temp_store)
        assert not f.ok, "Sperre muss auch bei Erholung bestehen bleiben"

    def test_grund_bleibt_der_erste(self, temp_store):
        """Der erste Ausloeser ist der interessante. Wuerde jeder Zyklus den
        Grund neu schreiben, waere 'womit fing es an' nicht beantwortbar."""
        risiko.pruefe_konto(konto=konto(100_000.), positionen=positionen(),
                            grenzen=G, store=temp_store)
        risiko.pruefe_konto(konto=konto(75_000.), positionen=positionen(),
                            grenzen=G, store=temp_store)
        erst = temp_store.sperre_lesen()["gesetzt_am"]
        risiko.pruefe_konto(konto=konto(50_000.), positionen=positionen(),
                            grenzen=G, store=temp_store)
        assert temp_store.sperre_lesen()["gesetzt_am"] == erst


class TestEinzahlungsbereinigung:
    """DER kritischste Test des Moduls.

    Ohne Bereinigung ist die Sperre genau dann wirkungslos, wenn am
    meisten Kapital im Spiel ist: Eine Einzahlung hebt den Hoechststand,
    und ein danach eintretender realer Verlust wird nie als Drawdown
    erkannt. Verifiziert am 15.08.2026.
    """

    def test_einzahlung_ist_kein_gewinn(self, temp_store):
        risiko.pruefe_konto(konto=konto(100_000.), positionen=positionen(),
                            grenzen=G, store=temp_store)
        temp_store.fluss_buchen("d1", pd.Timestamp.now(tz="UTC"), "CSD", 50_000.)
        f = risiko.pruefe_konto(konto=konto(150_000.), positionen=positionen(),
                                grenzen=G, store=temp_store)
        assert f.kennzahlen["drawdown_pct"] == pytest.approx(0.0, abs=1e-6)
        assert f.kennzahlen["einzahlungen"] == pytest.approx(50_000.)

    def test_realer_verlust_nach_einzahlung_sperrt(self, temp_store):
        """100k Start, +50k eingezahlt, dann Verlust auf 125k.
        Bereinigt: 25 % Drawdown -> Sperre.
        Ohne Bereinigung waeren es nur 16,7 % gewesen -> KEINE Sperre."""
        risiko.pruefe_konto(konto=konto(100_000.), positionen=positionen(),
                            grenzen=G, store=temp_store)
        temp_store.fluss_buchen("d1", pd.Timestamp.now(tz="UTC"), "CSD", 50_000.)
        risiko.pruefe_konto(konto=konto(150_000.), positionen=positionen(),
                            grenzen=G, store=temp_store)
        f = risiko.pruefe_konto(konto=konto(125_000.), positionen=positionen(),
                                grenzen=G, store=temp_store)
        assert f.kennzahlen["drawdown_pct"] == pytest.approx(0.25, abs=0.01)
        assert not f.ok, "Ohne Bereinigung waere das nur 16,7 % und wuerde durchgehen"


class TestEntsperren:
    def test_falsche_bestaetigung_wirkungslos(self, temp_store):
        risiko.pruefe_konto(konto=konto(100_000.), positionen=positionen(),
                            grenzen=G, store=temp_store)
        risiko.pruefe_konto(konto=konto(70_000.), positionen=positionen(),
                            grenzen=G, store=temp_store)
        risiko.sperre_loesen("ja ok", store=temp_store)
        assert int(temp_store.sperre_lesen()["aktiv"]) == 1

    def test_woertliche_bestaetigung_loest(self, temp_store):
        risiko.pruefe_konto(konto=konto(100_000.), positionen=positionen(),
                            grenzen=G, store=temp_store)
        risiko.pruefe_konto(konto=konto(70_000.), positionen=positionen(),
                            grenzen=G, store=temp_store)
        risiko.sperre_loesen(risiko.BESTAETIGUNG, store=temp_store)
        assert int(temp_store.sperre_lesen()["aktiv"]) == 0
        f = risiko.pruefe_konto(konto=konto(100_000.), positionen=positionen(),
                                grenzen=G, store=temp_store)
        assert f.ok


class TestOrderPruefung:
    def test_verkauf_immer_erlaubt(self, temp_store):
        """Eine Sperre darf nie verhindern, aus einer Position
        herauszukommen - das machte aus dem Schutz eine Falle."""
        risiko.pruefe_konto(konto=konto(100_000.), positionen=positionen(),
                            grenzen=G, store=temp_store)
        risiko.pruefe_konto(konto=konto(50_000.), positionen=positionen(),
                            grenzen=G, store=temp_store)
        f = risiko.pruefe_order("X", "sell", 999_999., konto=konto(50_000.),
                                positionen=positionen(), grenzen=G,
                                store=temp_store)
        assert f.ok

    def test_kauf_bei_sperre_blockiert(self, temp_store):
        risiko.pruefe_konto(konto=konto(100_000.), positionen=positionen(),
                            grenzen=G, store=temp_store)
        risiko.pruefe_konto(konto=konto(50_000.), positionen=positionen(),
                            grenzen=G, store=temp_store)
        f = risiko.pruefe_order("X", "buy", 1000., konto=konto(50_000.),
                                positionen=positionen(), grenzen=G,
                                store=temp_store)
        assert not f.ok

    def test_exposure_grenze(self, temp_store):
        f = risiko.pruefe_order("X", "buy", 30_000.,
                                konto=konto(100_000., cash=40_000.),
                                positionen=positionen(9, 10_000.),
                                grenzen=G, store=temp_store)
        assert not f.ok
        assert any("Exposure" in g for g in f.gruende)

    def test_cash_reserve(self, temp_store):
        f = risiko.pruefe_order("X", "buy", 9_900.,
                                konto=konto(100_000., cash=10_000.),
                                positionen=positionen(1, 1000.),
                                grenzen=G, store=temp_store)
        assert not f.ok
        assert any("Cash-Reserve" in g for g in f.gruende)

    def test_positionsobergrenze(self, temp_store):
        f = risiko.pruefe_order("X", "buy", 100.,
                                konto=konto(1_000_000., cash=500_000.),
                                positionen=positionen(G.max_positionen_gesamt, 100.),
                                grenzen=G, store=temp_store)
        assert not f.ok
        assert any("Positionen" in g for g in f.gruende)

    def test_klumpenkontrolle(self, temp_store):
        pos = positionen(4, 10_000.)  # 40 % bei 100k Konto
        sektoren = {s: "Technology" for s in pos.index}
        sektoren["NEU"] = "Technology"
        f = risiko.pruefe_order("NEU", "buy", 5_000.,
                                konto=konto(100_000., cash=50_000.),
                                positionen=pos, grenzen=G, store=temp_store,
                                sektoren=sektoren)
        assert not f.ok
        assert any("Sektor" in g for g in f.gruende)

    def test_unbekannter_sektor_verschwindet_nicht(self, temp_store):
        """Symbole ohne Sektorangabe zaehlen unter 'unbekannt' - sonst
        saehe ein Depot ohne Sektordaten wie perfekt gestreut aus."""
        pos = positionen(3, 10_000.)
        anteile = risiko.sektor_anteile(pos, {}, 100_000.)
        assert anteile == {"unbekannt": pytest.approx(0.30)}


class TestBrokerSperre:
    def test_trading_blocked_blockt(self, temp_store):
        f = risiko.pruefe_konto(konto=konto(blockiert=True),
                                positionen=positionen(), grenzen=G,
                                store=temp_store)
        assert not f.ok
        assert any("gesperrt" in g for g in f.gruende)


class TestKapitalVerlauf:
    def test_messpunkt_wird_geschrieben(self, temp_store):
        risiko.pruefe_konto(konto=konto(100_000.), positionen=positionen(),
                            grenzen=G, store=temp_store)
        v = temp_store.kapital_verlauf(tage=1)
        assert len(v) == 1
        assert v.iloc[0]["equity"] == pytest.approx(100_000.)

    def test_schreiben_abschaltbar(self, temp_store):
        """Eine Pruefung von Hand darf die Zeitreihe nicht verfaelschen,
        aus der die zeitgewichtete Rendite berechnet wird."""
        risiko.pruefe_konto(konto=konto(100_000.), positionen=positionen(),
                            grenzen=G, store=temp_store, schreiben=False)
        assert temp_store.kapital_verlauf(tage=1).empty
