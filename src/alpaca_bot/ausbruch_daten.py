"""Lokaler Bar-Vorrat fuer die Ausbruch-Versuche.

**Warum ein eigener Cache.** Ein Jahr 15-Minuten-Bars sind rund 6.700
Bars je Symbol. Fuer 1.200 Symbole sind das ~8 Millionen Zeilen und bei
direktem Abruf knapp eine Stunde Wartezeit - je Testlauf. Das macht
Ausprobieren unmoeglich.

Deshalb: **einmal laden, als Parquet ablegen, danach aus der Platte
lesen.** Ein Testlauf braucht dann Sekunden statt einer Stunde, und
genau darum geht es bei einer Oberflaeche zum Herumprobieren.

**Wo die Daten liegen.** Unter `DATA_DIR` (Application Support), nicht
unter `~/Documents` - macOS-TCC blockiert Hintergrunddienste dort
(`CLAUDE.md`, §H). Ein Symbol je Datei, damit ein abgebrochener Lauf
fortsetzbar ist und ein kaputtes Symbol nicht den ganzen Vorrat kippt.

**Warum Parquet und nicht SQLite.** Spaltenweise Kompression bringt bei
Kursreihen Faktor 5-8, und `pandas.read_parquet` liefert direkt das
Format, das die Engine braucht. `pyarrow` ist bereits im Projekt.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Callable, Sequence

import pandas as pd
from alpaca.data.enums import Adjustment

from . import data as _data
from .config import DATA_DIR

VORRAT = DATA_DIR / "intraday"
"""Ein Unterordner je Zeitraster, darin eine Parquet-Datei je Symbol."""

SPALTEN = ["open", "high", "low", "close", "volume"]

__all__ = ["VORRAT", "laden", "laden_kursdaten", "vorrat_aufbauen",
           "bestand", "bestand_loeschen", "jahre_vorhanden"]


def _ordner(raster: str, jahr: int) -> Path:
    return VORRAT / f"{raster}_{jahr}"


def _datei(raster: str, jahr: int, symbol: str) -> Path:
    # Punkte in Symbolen (BRK.B) waeren im Dateinamen mehrdeutig.
    return _ordner(raster, jahr) / f"{symbol.replace('.', '-')}.parquet"


def bestand(raster: str = "15Min", jahr: int = 2025) -> dict:
    """Was liegt schon auf der Platte?"""
    ordner = _ordner(raster, jahr)
    if not ordner.exists():
        return {"symbole": 0, "mb": 0.0, "ordner": str(ordner)}
    dateien = list(ordner.glob("*.parquet"))
    return {
        "symbole": len(dateien),
        "mb": sum(f.stat().st_size for f in dateien) / 1e6,
        "ordner": str(ordner),
    }


def bestand_loeschen(raster: str = "15Min", jahr: int = 2025) -> int:
    """Vorrat verwerfen. Gibt die Zahl geloeschter Dateien zurueck."""
    ordner = _ordner(raster, jahr)
    if not ordner.exists():
        return 0
    n = 0
    for f in ordner.glob("*.parquet"):
        f.unlink()
        n += 1
    return n


def vorrat_aufbauen(
    symbole: Sequence[str],
    *,
    jahr: int = 2025,
    raster: str = "15Min",
    batch: int = 20,
    neu_laden: bool = False,
    fortschritt: Callable[[float, str], None] | None = None,
    abbruch: Callable[[], bool] | None = None,
) -> dict:
    """Laedt die Bars und legt sie ab. Fortsetzbar.

    Bereits vorhandene Symbole werden uebersprungen (ausser
    `neu_laden=True`) - ein abgebrochener Lauf kostet also nichts.

    `adjustment=ALL` ist Pflicht: Ohne Split-Bereinigung sieht ein
    1:2-Split wie ein 50-%-Absturz aus, und genau danach sucht diese
    Strategie in umgekehrter Richtung.
    """
    melde = fortschritt or (lambda *_: None)
    stoppen = abbruch or (lambda: False)

    ordner = _ordner(raster, jahr)
    ordner.mkdir(parents=True, exist_ok=True)

    offen = [s for s in symbole
             if neu_laden or not _datei(raster, jahr, s).exists()]
    bericht = {"geladen": 0, "uebersprungen": len(symbole) - len(offen),
               "leer": 0, "fehler": 0, "zeilen": 0}
    if not offen:
        melde(1.0, f"Vorrat vollstaendig ({len(symbole)} Symbole)")
        return bericht

    start = f"{jahr}-01-01"
    ende = f"{jahr}-12-31"
    melde(0.0, f"{len(offen)} Symbole fehlen - lade {raster} fuer {jahr}")

    for i in range(0, len(offen), batch):
        if stoppen():
            raise InterruptedError("Vom Nutzer abgebrochen.")
        teil = list(offen[i:i + batch])
        anteil = i / max(len(offen), 1)
        melde(anteil,
              f"Lade {i + 1}-{min(i + batch, len(offen))} von {len(offen)}  "
              f"({bericht['zeilen']:,} Bars)")
        try:
            df = _data.get_bars(teil, raster, start=start, end=ende,
                                adjustment=Adjustment.ALL)
        except Exception as e:  # noqa: BLE001 - ein Batch darf den Lauf nicht kippen
            melde(anteil, f"   Batch uebersprungen: {type(e).__name__}: {e}")
            bericht["fehler"] += len(teil)
            continue
        if df.empty:
            bericht["leer"] += len(teil)
            continue
        for sym in teil:
            try:
                eins = df.xs(sym, level="symbol")
            except KeyError:
                bericht["leer"] += 1
                continue
            eins = eins[[c for c in SPALTEN if c in eins.columns]].dropna()
            if len(eins) < 100:
                # Weniger als ~4 Handelstage: als Vorrat wertlos, und
                # eine Datei anzulegen wuerde den Fortsetz-Mechanismus
                # glauben machen, das Symbol sei erledigt.
                bericht["leer"] += 1
                continue
            eins.to_parquet(_datei(raster, jahr, sym), compression="zstd")
            bericht["geladen"] += 1
            bericht["zeilen"] += len(eins)

    b = bestand(raster, jahr)
    (ordner / "_stand.json").write_text(json.dumps({
        "aktualisiert": dt.datetime.now(dt.UTC).isoformat(),
        "raster": raster, "jahr": jahr, **bericht, **b,
    }, indent=2), encoding="utf-8")
    melde(1.0, f"Vorrat: {b['symbole']} Symbole, {b['mb']:.0f} MB")
    return bericht


def laden(
    symbole: Sequence[str] | None = None,
    *,
    jahr: int = 2025,
    raster: str = "15Min",
    max_symbole: int | None = None,
    fortschritt: Callable[[float, str], None] | None = None,
) -> dict[str, pd.DataFrame]:
    """Holt den Vorrat von der Platte in den Speicher.

    Gibt Symbol -> DataFrame zurueck, genau das Format, das
    `ausbruch.lauf` erwartet.
    """
    melde = fortschritt or (lambda *_: None)
    ordner = _ordner(raster, jahr)
    if not ordner.exists():
        raise FileNotFoundError(
            f"Kein Vorrat unter {ordner}. Erst `vorrat_aufbauen()` laufen "
            f"lassen - in der Oberflaeche der Knopf 'Kursdaten laden'."
        )

    dateien = sorted(ordner.glob("*.parquet"))
    if symbole is not None:
        erlaubt = {s.replace(".", "-") for s in symbole}
        dateien = [f for f in dateien if f.stem in erlaubt]
    if max_symbole:
        dateien = dateien[:max_symbole]
    if not dateien:
        raise FileNotFoundError(f"Keine passenden Dateien in {ordner}.")

    out: dict[str, pd.DataFrame] = {}
    for i, f in enumerate(dateien):
        if i % 100 == 0:
            melde(i / len(dateien), f"Lade Vorrat: {i}/{len(dateien)} Symbole")
        try:
            out[f.stem.replace("-", ".")] = pd.read_parquet(f)
        except Exception:  # noqa: BLE001 - eine kaputte Datei ist kein Abbruch
            continue
    melde(1.0, f"{len(out)} Symbole im Speicher")
    return out

def jahre_vorhanden(raster: str = "15Min") -> list[int]:
    """Welche Jahre liegen fuer dieses Raster auf der Platte?"""
    if not VORRAT.exists():
        return []
    aus = []
    for d in VORRAT.iterdir():
        if d.is_dir() and d.name.startswith(f"{raster}_"):
            try:
                aus.append(int(d.name.rsplit("_", 1)[1]))
            except ValueError:
                continue
    return sorted(aus)


def laden_kursdaten(
    jahre: Sequence[int] | int = 2025,
    *,
    raster: str = "15Min",
    max_symbole: int | None = None,
    min_bars: int = 500,
    fortschritt: Callable[[float, str], None] | None = None,
):
    """Laedt den Vorrat direkt in ein `ausbruch.Kursdaten`-Objekt.

    **Der Unterschied zu `laden()` ist der Speicher.** `laden()` gibt
    ein dict voller DataFrames zurueck; bei 5.000 Symbolen ueber fuenf
    Jahre sind das ueber 6 GB allein an pandas-Objekten, bevor die
    Ausrichtung ueberhaupt beginnt. Hier wird **je Symbol geladen,
    sofort auf float32 ausgerichtet und der DataFrame verworfen** -
    der Spitzenbedarf entspricht damit dem Endergebnis statt dem
    Doppelten.

    Mehrere Jahre werden aneinandergehaengt. Die Zeitachse entsteht
    aus einem ersten Durchgang, der nur die INDIZES liest (Parquet
    erlaubt das ohne die Datenspalten) - das ist der Grund, warum zwei
    Durchgaenge hier billiger sind als einer.
    """
    from . import ausbruch as _a

    melde = fortschritt or (lambda *_: None)
    jahre = [jahre] if isinstance(jahre, int) else sorted(jahre)
    fehlend = [j for j in jahre if not _ordner(raster, j).exists()]
    if fehlend:
        raise FileNotFoundError(
            f"Kein Vorrat fuer {fehlend} ({raster}). Vorhanden: "
            f"{jahre_vorhanden(raster)}. Erst laden: "
            f"scripts/48_ausbruch_daten.py"
        )

    # Welche Symbole in ALLEN gewuenschten Jahren vorliegen. Ein Symbol,
    # das nur die Haelfte des Zeitraums abdeckt, brauchte eine
    # Sonderbehandlung bei jeder Kennzahl - und waere zugleich ein
    # stiller Survivorship-Filter in die andere Richtung.
    je_jahr = [{f.stem for f in _ordner(raster, j).glob("*.parquet")}
               for j in jahre]
    gemeinsam = sorted(set.intersection(*je_jahr)) if je_jahr else []
    if max_symbole:
        gemeinsam = gemeinsam[:max_symbole]
    if not gemeinsam:
        raise FileNotFoundError("Kein Symbol deckt alle gewuenschten Jahre ab.")

    # --- Durchgang 1: nur die Zeitstempel -----------------------------
    melde(0.0, f"Zeitachse aus {len(gemeinsam)} Symbolen x {len(jahre)} Jahr(en)")
    indizes = []
    for i, stem in enumerate(gemeinsam):
        if i % 250 == 0:
            melde(0.3 * i / len(gemeinsam), f"Zeitachse: {i}/{len(gemeinsam)}")
        for j in jahre:
            try:
                indizes.append(pd.read_parquet(
                    _ordner(raster, j) / f"{stem}.parquet", columns=[]).index)
            except Exception:  # noqa: BLE001
                continue
    if not indizes:
        raise FileNotFoundError("Keine lesbaren Dateien im Vorrat.")
    achse = _a._achse_bauen(indizes)
    del indizes

    # --- Durchgang 2: ausrichten, DataFrame sofort verwerfen ----------
    arrays: dict[str, tuple] = {}
    for i, stem in enumerate(gemeinsam):
        if i % 100 == 0:
            mb = sum(a.nbytes for t in arrays.values() for a in t) / 1e6
            melde(0.3 + 0.7 * i / len(gemeinsam),
                  f"Ausrichten: {i}/{len(gemeinsam)} Symbole, {mb:,.0f} MB")
        teile = []
        for j in jahre:
            try:
                teile.append(pd.read_parquet(
                    _ordner(raster, j) / f"{stem}.parquet"))
            except Exception:  # noqa: BLE001
                continue
        if not teile:
            continue
        df = pd.concat(teile) if len(teile) > 1 else teile[0]
        if len(df) < min_bars:
            continue
        a = _a._ausrichten(df, achse)
        del df, teile
        if a is not None:
            arrays[stem.replace("-", ".")] = a

    if not arrays:
        raise FileNotFoundError("Kein Symbol hatte genug verwertbare Bars.")
    bit, ldt = _a._tagesraster(achse)
    kd = _a.Kursdaten(achse, arrays, bit, ldt)
    melde(1.0, f"{len(arrays)} Symbole, {kd.n_bars:,} Bars, "
               f"{kd.speicher_mb():,.0f} MB")
    return kd
