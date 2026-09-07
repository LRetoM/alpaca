"""Fuellpreis-Abgleich laeuft auch bei geschlossener Boerse (07.09.2026).

**Der Vorfall.** Zwei Kaeufe (TCOM, NIO) fuellten Freitag 15:45 ET bei
Alpaca. Der Daemon traegt Fuellpreise erst im naechsten Zyklus nach -
aber die `kein Handel: Boerse geschlossen`-Abzweigung kehrte VOR dem
`reconcile_fills()`-Aufruf zurueck. Ueber das ganze Wochenende blieben
die Orders im Journal ohne `fill_price`; Montag frueh meldete
`data_integrity` (Schwelle 6 h) den Health-Check ROT.

**Der Fix.** `step()` ruft `live.reconcile_fills()` jetzt AUCH im
geschlossenen Zweig auf (billig: ohne offene Order sofortiger Ruecklauf),
mit einem 120-h-Fenster, das ein 3-Tage-Wochenende plus Feiertag
abdeckt.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

import alpaca_bot.daemon as dmod


@pytest.fixture
def daemon(monkeypatch):
    monkeypatch.setattr(dmod, "Store", MagicMock())
    monkeypatch.setattr(dmod, "Journal", MagicMock())
    fake_live = MagicMock()
    fake_live.reconcile_fills.return_value = 0
    monkeypatch.setattr(dmod, "live", fake_live)
    d = dmod.Daemon(dmod.DaemonConfig(symbols=["AAA"]))
    monkeypatch.setattr(d, "_maybe_stops_intraday", lambda: None)
    return d, fake_live


def test_geschlossene_boerse_traegt_fuellpreise_nach(daemon, monkeypatch):
    d, fake_live = daemon
    monkeypatch.setattr(d, "trading_window", lambda: (False, "boerse_geschlossen"))

    ergebnis = d.step()

    assert ergebnis is True
    fake_live.reconcile_fills.assert_called()
    # das Fenster muss ein Wochenende abdecken (> 72 h)
    kwargs = fake_live.reconcile_fills.call_args.kwargs
    args = fake_live.reconcile_fills.call_args.args
    fenster = kwargs.get("lookback_hours", args[0] if args else 48)
    assert fenster >= 96, f"Fenster {fenster} h deckt kein 3-Tage-Wochenende ab"


def test_abgleich_fehler_stoppt_den_zyklus_nicht(daemon, monkeypatch):
    d, fake_live = daemon
    monkeypatch.setattr(d, "trading_window", lambda: (False, "boerse_geschlossen"))
    fake_live.reconcile_fills.side_effect = RuntimeError("Broker weg")

    assert d.step() is True  # Fehler wird geschluckt, Zyklus gilt als erfolgreich
