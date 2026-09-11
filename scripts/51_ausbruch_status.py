#!/usr/bin/env python3
"""Schritt 51: Ein Befehl - aktueller Stand aller Ausbruch-Dienst-Instanzen.

    python scripts/51_ausbruch_status.py

Liest NUR die vom Dienst geschriebenen Statusdateien - fasst den
laufenden Prozess nicht an, beliebig oft aufrufbar. Zeigt jede
parallele Instanz einzeln (siehe `--instanz` in Skript 50) und die
gemeinsame Versuchszahl/Schwelle ueber alle Instanzen zusammen.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from alpaca_bot import ausbruch_store  # noqa: E402
from alpaca_bot import ausbruch_suche as su  # noqa: E402
from alpaca_bot import ausbruch_versuche as av  # noqa: E402
from alpaca_bot.config import DATA_DIR  # noqa: E402


def _p(d: dict, feld: str, n: int = 2, suffix: str = "") -> str:
    v = d.get(feld)
    return "-" if v is None else f"{v:.{n}f}{suffix}"


def _prozesse() -> dict[str, str]:
    """Instanz-Kennung -> PID, fuer alle laufenden Dienst-Prozesse.

    `ps -o pid,command` statt `pgrep -af`: Auf dieser macOS-Version gibt
    `pgrep -af` nur die PID ohne Kommandozeile zurueck - das Aufteilen
    an der ersten Leerstelle liefert dann Muell statt der Instanz.
    """
    try:
        out = subprocess.run(
            ["ps", "-ax", "-o", "pid,command"],
            capture_output=True, text=True, timeout=3).stdout
    except Exception:  # noqa: BLE001
        return {}
    aus: dict[str, str] = {}
    for zeile in out.splitlines():
        if "50_ausbruch_dienst.py" not in zeile:
            continue
        teile = zeile.split()
        pid = teile[0]
        instanz = "a"
        if "--instanz" in teile:
            instanz = teile[teile.index("--instanz") + 1]
        aus[instanz] = pid
    return aus


def _instanz_anzeigen(z: dict, pid: str | None) -> None:
    print("=" * 70)
    print(f"  INSTANZ [{z.get('instanz', '?')}]  "
          f"{'[LAEUFT PID ' + pid + ']' if pid else '[GESTOPPT]'}")
    print("=" * 70)
    print(f"  Zuletzt aktualisiert : {z.get('gespeichert_am', '?')}")
    print(f"  Versuche (Instanz)   : {z.get('versuche', 0):,}")
    print(f"  Neustarts            : {z.get('neustarts', 0)}"
          f"   davon vom Bestwert: {z.get('elite_uebernahmen', 0)}")
    print(f"  Pruefbewertungen     : {z.get('pruef_bewertungen', 0)}")
    print(f"  Lernfenster bis      : {z.get('lernfenster_bis', '?')}")
    print()

    print("  LERNFENSTER            PRUEFFENSTER")
    bk, pk = z.get("beste_kennzahlen", {}), z.get("pruef_kennzahlen", {})
    for feld, label, dez, suf in (
        ("t_wert", "t-Wert", 2, ""), ("rendite_pct", "Rendite", 2, " %"),
        ("mittel_pct", "je Trade", 3, " %"), ("n_trades", "Trades", 0, ""),
        ("n_handelstage", "Handelstage", 0, ""),
        ("max_drawdown_pct", "max. Rueckgang", 1, " %"),
    ):
        print(f"    {label:<14}{_p(bk, feld, dez, suf):>14}"
              f"{_p(pk, feld, dez, suf):>22}")

    abstand = z.get("abstand")
    if abstand is not None:
        print(f"    {'Abstand':<14}{abstand:>+14.2f}"
              f"   {'gross = an Lernzeitraum angepasst' if abs(abstand) > 1.5 else ''}")
    print()

    cfg = z.get("beste_config", {})
    if cfg:
        print("  BESTE KONFIGURATION DIESER INSTANZ")
        for k, w in sorted(cfg.items()):
            print(f"    {k:<32} {w}")
        print()

    print("  LETZTE VERSUCHE")
    for v in z.get("letzte", [])[-6:]:
        marke = "*" if v.get("besser") else " "
        sc = "  -inf" if v.get("score") is None else f"{v['score']:6.2f}"
        print(f"   {marke} {v['nr']:>6}  {v['phase'][:4]:<5} {sc}  "
              f"{v.get('n_trades', 0):>4}T")
    print()


def main() -> int:
    dateien = sorted(DATA_DIR.glob("ausbruch_stand_*.json"))
    if not dateien:
        print("Kein Dienst gefunden (noch nie gelaufen).")
        print("Starten mit: python scripts/50_ausbruch_dienst.py")
        return 1

    laufend = _prozesse()
    gesamt_versuche = 0
    beste_gesamt: tuple[float, dict] | None = None

    for pfad in dateien:
        z = json.loads(pfad.read_text(encoding="utf-8"))
        instanz = z.get("instanz", pfad.stem.rsplit("_", 1)[-1])
        _instanz_anzeigen(z, laufend.get(instanz))
        gesamt_versuche += z.get("versuche", 0)
        pt = (z.get("pruef_kennzahlen") or {}).get("t_wert")
        if pt is not None and (beste_gesamt is None or pt > beste_gesamt[0]):
            beste_gesamt = (pt, z)

    import math
    gesamt_pruef = sum(
        json.loads(f.read_text(encoding="utf-8")).get("pruef_bewertungen", 0)
        for f in dateien)
    lern_schwelle = max(2.0, math.sqrt(2.0 * math.log(max(gesamt_versuche, 2))))
    pruef_schwelle = max(2.0, math.sqrt(2.0 * math.log(max(gesamt_pruef, 2))))

    print("=" * 70)
    print(f"  GESAMT ueber {len(dateien)} Instanz(en)")
    print(f"    Versuche           : {gesamt_versuche:,}")
    print(f"    Pruefbewertungen   : {gesamt_pruef:,}")
    print(f"    Lernschwelle       : t > {lern_schwelle:.2f}")
    print(f"    Pruefschwelle      : t > {pruef_schwelle:.2f}   <- massgeblich")

    e = su.elite_lesen()
    if e:
        print(f"    Gemeinsamer Bestwert: score {e.get('score', 0):.3f} "
              f"von Instanz [{e.get('instanz')}]")
    if beste_gesamt:
        bp = beste_gesamt[0]
        urteil = ("UEBER der Schwelle" if bp >= pruef_schwelle
                  else "unter der Schwelle - kein Befund")
        print(f"    Bestes Pruef-t     : {bp:.2f}  ({urteil})")

    try:
        n_prot = sum(av.Protokoll(i).anzahl() for i in av.instanzen())
        print(f"    Protokollierte Versuche: {n_prot:,}"
              f"   -> Auswertung: scripts/52_ausbruch_auswertung.py")
    except Exception:  # noqa: BLE001 - Anzeige darf nie den Status kippen
        pass
    if not laufend:
        print("\n  Kein Dienst laeuft gerade. Starten mit:")
        print("    python scripts/50_ausbruch_dienst.py --instanz a")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
