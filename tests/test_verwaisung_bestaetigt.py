"""RMBS: eine Position ohne Stop, weil ein Broker-Read sie einmal ausliess (§G37).

**Der Vorfall (26.08.2026).** `account.orders()` zeigt fuer RMBS genau
EINE Order - Kauf am 20.08., nie verkauft. Trotzdem meldete
`sync_with_broker()` bei einem Neustart am 21.08. `RMBS` als verwaist und
loeschte Stop und Ziel sofort. Die Position blieb danach mehrere Tage
ungeschuetzt im Depot, weil der Broker-Read RMBS bei den folgenden
Aufrufen ebenfalls wiederholt ausliess - die "fehlt in der DB, ist aber
beim Broker da"-Ergaenzung in `daemon.recover()` griff deshalb nie.

**Die Regel, die das verhindern soll:** Ein Symbol darf erst als
verwaist gelten, wenn es bei ZWEI aufeinanderfolgenden Aufrufen fehlt -
nicht beim ersten. Und: Taucht es dazwischen wieder auf, muss der
Verdacht verworfen werden, nicht liegen bleiben und spaeter faelschlich
zuschlagen.
"""

from __future__ import annotations


def test_einmaliges_fehlen_loescht_noch_nicht(temp_store):
    """Der eigentliche Vorfall: ein einzelnes Fehlen darf die Marken
    NICHT sofort loeschen - genau das geschah bei RMBS."""
    temp_store.save_position(
        "RMBS", entry_price=91.53, entry_date="2026-08-20T14:17:30+00:00",
        stop_price=77.95, target_price=105.11, high_water=93.315,
    )

    orphans = temp_store.sync_with_broker(broker_symbols=set())  # RMBS fehlt

    assert orphans == []
    assert "RMBS" in temp_store.load_positions(), (
        "Erstes Fehlen im Broker-Read hat die Marken geloescht - "
        "genau der Fehler aus §G37"
    )


def test_zweimaliges_fehlen_loescht(temp_store):
    """Fehlt ein Symbol bei ZWEI aufeinanderfolgenden Aufrufen, ist die
    Loeschung berechtigt - Bracket-Order, manueller Verkauf o.ae."""
    temp_store.save_position(
        "XYZ", entry_price=50.0, entry_date="2026-08-01T00:00:00+00:00",
        stop_price=45.0, target_price=60.0, high_water=52.0,
    )

    temp_store.sync_with_broker(broker_symbols=set())          # 1. Mal fehlt
    orphans = temp_store.sync_with_broker(broker_symbols=set())  # 2. Mal fehlt

    assert orphans == ["XYZ"]
    assert "XYZ" not in temp_store.load_positions()


def test_wiederauftauchen_verwirft_den_verdacht(temp_store):
    """Taucht ein Symbol zwischen zwei Aufrufen wieder im Broker-Read auf,
    darf ein spaeteres erneutes Fehlen es NICHT sofort loeschen - der
    alte Verdacht ist verbraucht, es zaehlt wieder als 'erstes Fehlen'."""
    temp_store.save_position(
        "RMBS", entry_price=91.53, entry_date="2026-08-20T14:17:30+00:00",
        stop_price=77.95, target_price=105.11, high_water=93.315,
    )

    temp_store.sync_with_broker(broker_symbols=set())              # fehlt (Verdacht)
    temp_store.sync_with_broker(broker_symbols={"RMBS"})           # taucht wieder auf
    orphans = temp_store.sync_with_broker(broker_symbols=set())    # fehlt erneut

    assert orphans == [], "Wiederaufgetauchtes Symbol wurde beim naechsten Fehlen sofort geloescht"
    assert "RMBS" in temp_store.load_positions()


def test_zwei_symbole_unabhaengig_verdaechtigt(temp_store):
    """Ein bestaetigt verwaistes Symbol darf den Verdacht eines anderen,
    erst einmal fehlenden Symbols nicht mitreissen."""
    temp_store.save_position(
        "AAA", entry_price=10.0, entry_date="2026-08-01T00:00:00+00:00",
        stop_price=9.0, target_price=12.0, high_water=10.0,
    )
    temp_store.save_position(
        "BBB", entry_price=20.0, entry_date="2026-08-01T00:00:00+00:00",
        stop_price=18.0, target_price=24.0, high_water=20.0,
    )

    temp_store.sync_with_broker(broker_symbols={"BBB"})   # AAA fehlt (1. Mal)
    orphans = temp_store.sync_with_broker(broker_symbols={"AAA"})  # BBB fehlt (1. Mal), AAA da

    assert orphans == [], "AAA war beim ersten Aufruf nur verdaechtig, wurde aber schon geloescht"
    assert "AAA" in temp_store.load_positions()
    assert "BBB" in temp_store.load_positions()
