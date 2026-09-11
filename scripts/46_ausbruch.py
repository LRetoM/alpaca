#!/usr/bin/env python3
"""Schritt 46: Ausbruch-Werkstatt - Oberflaeche zum Durchspielen der Idee.

    python scripts/46_ausbruch.py           # oeffnet den Browser
    python scripts/46_ausbruch.py --port 9000
    python scripts/46_ausbruch.py --kein-browser

**Die Idee, die hier geprueft wird (Nutzer, 11.09.2026).** Alle 15
Minuten das Universum absuchen. Springt ein Wert in wenigen Stunden um
X Prozent, einen grossen Teil des Kapitals hineinlegen und darauf
setzen, dass die Bewegung weiterlaeuft. Verkauft wird nach fester Zeit,
bei Gewinnziel oder am Stop. Bewusst ein volatiles System.

**Was diese Oberflaeche ist.** Ein Werkzeug, um die Idee an der Historie
2025 durchzuspielen - mit jeder Stellschraube einzeln verstellbar, mit
Live-Fortschritt, Live-Kontostand und einer Bestenliste der Symbole.

**Was sie NICHT ist.** Ein Weg zu echtem Geld. Sie handelt nicht,
importiert `trading.py` nicht und wird von keinem Dienst gerufen. Ein
Historienlauf darf eine Idee VERWERFEN, nie abnehmen (`BETRIEBSPLAN`
§4). Was hier ueberlebt, geht als Flottenbot in den Vorwaertsschatten.

**Warum Browser statt Fenster-Oberflaeche.** `tkinter` fehlt in dieser
Python-Installation (kein `_tkinter`). Der Umweg ueber einen lokalen
Server braucht nur die Standardbibliothek, keine neue Abhaengigkeit und
keinen Eintrag in `ratelimit.QUOTAS` - er spricht mit niemandem ausser
127.0.0.1.

**Die Warnung, die mitlaeuft.** Jeder Lauf zaehlt in
`ausbruch_store.n_versuche()`. Bei N Versuchen liegt das Zufallsmaximum
bei `sqrt(2 ln N)` (§B2) - die Oberflaeche weist diese Schwelle bei
jedem Ergebnis aus. Eine Werkstatt zum Herumprobieren IST eine Maschine
zur Herstellung von Scheingewinnern; sie laesst sich nicht abschalten,
nur mitzaehlen.
"""

from __future__ import annotations

import argparse
import json
import queue
import sys
import threading
import traceback
import webbrowser
from dataclasses import fields as dc_fields
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd  # noqa: E402

from alpaca_bot import ausbruch, ausbruch_daten, ausbruch_store, universe  # noqa: E402

HIER = Path(__file__).resolve().parent / "weboberflaeche"


# ---------------------------------------------------------------------
#  Laufender Zustand - genau ein Lauf gleichzeitig
# ---------------------------------------------------------------------
class Werkstatt:
    """Haelt den aktuellen Lauf und verteilt Meldungen an die Oberflaeche.

    Bewusst nur EIN Lauf gleichzeitig: Zwei parallele Laeufe wuerden sich
    die Rate-Limits teilen und die Fortschrittsanzeige unlesbar machen.
    """

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.aktiv = False
        self.abbruch_gewuenscht = False
        self.hoerer: list[queue.Queue] = []
        self.letzter_lauf: str | None = None
        self.zustand: dict = {}

    # --- Meldungen ---------------------------------------------------
    def sende(self, art: str, **daten) -> None:
        nachricht = {"art": art, **daten}
        if art == "zustand":
            self.zustand = daten
        tot = []
        for q in self.hoerer:
            try:
                q.put_nowait(nachricht)
            except queue.Full:
                tot.append(q)
        for q in tot:
            self.hoerer.remove(q)

    def anmelden(self) -> queue.Queue:
        q: queue.Queue = queue.Queue(maxsize=500)
        self.hoerer.append(q)
        return q

    def abmelden(self, q: queue.Queue) -> None:
        if q in self.hoerer:
            self.hoerer.remove(q)

    def log(self, text: str, stufe: str = "info") -> None:
        self.sende("log", text=text, stufe=stufe)

    def fortschritt(self, anteil: float, text: str, zustand=None) -> None:
        self.sende("fortschritt", anteil=float(anteil), text=text)
        if zustand:
            self.sende("zustand", **zustand)

    def abbrechen(self) -> bool:
        return self.abbruch_gewuenscht

    # --- Aufgaben ----------------------------------------------------
    def starten(self, ziel, *args) -> bool:
        with self.lock:
            if self.aktiv:
                return False
            self.aktiv = True
            self.abbruch_gewuenscht = False
        t = threading.Thread(target=self._huelle, args=(ziel, *args),
                             daemon=True)
        t.start()
        return True

    def _huelle(self, ziel, *args) -> None:
        try:
            ziel(*args)
        except InterruptedError as e:
            self.log(f"Abgebrochen: {e}", "warn")
            self.sende("ende", ok=False, grund="abgebrochen")
        except Exception as e:  # noqa: BLE001
            self.log(f"{type(e).__name__}: {e}", "fehler")
            self.log(traceback.format_exc()[-1500:], "fehler")
            self.sende("ende", ok=False, grund=str(e))
        finally:
            with self.lock:
                self.aktiv = False


W = Werkstatt()


# ---------------------------------------------------------------------
#  Aufgabe 1: Kursdaten in den lokalen Vorrat holen
# ---------------------------------------------------------------------
def aufgabe_daten(n_symbole: int, jahr: int, raster: str) -> None:
    W.log(f"Universum bestimmen (die {n_symbole} umsatzstaerksten) ...")
    syms = universe.load_universe(max_symbols=n_symbole)
    W.log(f"{len(syms)} Symbole. Lade {raster}-Bars fuer {jahr}.")
    W.log("Einmalig - danach liest jeder Testlauf von der Platte.", "gut")

    bericht = ausbruch_daten.vorrat_aufbauen(
        syms, jahr=jahr, raster=raster,
        fortschritt=lambda a, t: (W.fortschritt(a, t), W.log(t))[0],
        abbruch=W.abbrechen,
    )
    b = ausbruch_daten.bestand(raster, jahr)
    W.log(f"Fertig: {b['symbole']} Symbole, {b['mb']:.0f} MB auf der Platte. "
          f"Neu {bericht['geladen']}, uebersprungen {bericht['uebersprungen']}, "
          f"ohne Daten {bericht['leer']}, Fehler {bericht['fehler']}.", "gut")
    W.sende("ende", ok=True, grund="daten")


# ---------------------------------------------------------------------
#  Aufgabe 2: Der Testlauf
# ---------------------------------------------------------------------
def aufgabe_lauf(cfg_dict: dict, jahr: int, raster: str,
                 max_symbole: int | None, notiz: str) -> None:
    cfg = ausbruch.AusbruchConfig(**cfg_dict)

    W.log("Vorrat von der Platte laden ...")
    bars = ausbruch_daten.laden(
        jahr=jahr, raster=raster, max_symbole=max_symbole,
        fortschritt=lambda a, t: W.fortschritt(a * 0.1, t),
    )
    W.log(f"{len(bars)} Symbole im Speicher.")

    lauf_id = ausbruch_store.neuer_lauf(
        cfg.als_dict(), jahr=jahr, raster=raster,
        n_symbole=len(bars), notiz=notiz)
    W.letzter_lauf = lauf_id
    n = ausbruch_store.n_versuche()
    schwelle = ausbruch_store.schwelle_sigma()
    W.log(f"Lauf {lauf_id} angemeldet. Versuch Nr. {n} - "
          f"Zufallsschwelle jetzt t > {schwelle:.2f}.", "warn")
    W.sende("lauf_start", lauf_id=lauf_id, n_versuche=n, schwelle=schwelle)

    erg = ausbruch.lauf(bars, cfg,
                        fortschritt=lambda a, t, z=None:
                            W.fortschritt(0.1 + 0.9 * a, t, z),
                        abbruch=W.abbrechen)

    ausbruch_store.speichern(lauf_id, erg.trades, erg.equity)
    ausbruch_store.abschliessen(lauf_id, erg.kennzahlen)

    k = erg.kennzahlen
    W.log(f"FERTIG. {k['n_trades']} Trades aus {k['n_signale']:,} Signalen. "
          f"Rendite {k['rendite_pct']:+.2f} %, "
          f"Trefferquote {k.get('trefferquote_pct', 0):.1f} %, "
          f"max. Rueckgang {k.get('max_drawdown_pct', 0):.1f} %.",
          "gut" if k["rendite_pct"] > 0 else "warn")

    t_wert = k.get("t_wert")
    if t_wert is not None and t_wert == t_wert:   # nicht NaN
        urteil = "UEBER der Schwelle" if abs(t_wert) > schwelle else "kein Befund"
        W.log(f"t = {t_wert:.2f} gegen Schwelle {schwelle:.2f} -> {urteil}. "
              f"({k.get('n_handelstage', 0)} Handelstage)",
              "gut" if abs(t_wert) > schwelle else "info")

    for h in erg.hinweise:
        W.log(h, "warn")

    W.sende("ergebnis", lauf_id=lauf_id, kennzahlen=_rein(k),
            hinweise=erg.hinweise, schwelle=schwelle, n_versuche=n,
            verworfen=erg.n_signale_verworfen)
    W.sende("ende", ok=True, grund="lauf")


def _rein(d: dict) -> dict:
    """NaN und Inf sind kein gueltiges JSON - sie wuerden die Seite kippen."""
    out = {}
    for k, v in d.items():
        if isinstance(v, float):
            out[k] = None if (v != v or v in (float("inf"), float("-inf"))) else v
        else:
            out[k] = v
    return out


def _tabelle(df: pd.DataFrame) -> list[dict]:
    if df is None or df.empty:
        return []
    return json.loads(df.to_json(orient="records", date_format="iso"))


# ---------------------------------------------------------------------
#  Der Server
# ---------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):      # Konsole gehoert dem Nutzer-Log
        pass

    # --- Hilfen ------------------------------------------------------
    def _senden(self, koerper: bytes, typ: str = "application/json",
                code: int = 200) -> None:
        self.send_response(code)
        self.send_header("Content-Type", typ)
        self.send_header("Content-Length", str(len(koerper)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(koerper)

    def _json(self, obj, code: int = 200) -> None:
        self._senden(json.dumps(obj, default=str).encode(), code=code)

    def _datei(self, name: str, typ: str) -> None:
        pfad = HIER / name
        if not pfad.exists():
            self._senden(b"nicht gefunden", "text/plain", 404)
            return
        self._senden(pfad.read_bytes(), typ)

    def _koerper(self) -> dict:
        laenge = int(self.headers.get("Content-Length") or 0)
        if not laenge:
            return {}
        try:
            return json.loads(self.rfile.read(laenge) or b"{}")
        except json.JSONDecodeError:
            return {}

    # --- GET ---------------------------------------------------------
    def do_GET(self) -> None:  # noqa: N802
        weg = urlparse(self.path)
        frage = parse_qs(weg.query)

        if weg.path in ("/", "/index.html"):
            return self._datei("ausbruch.html", "text/html; charset=utf-8")
        if weg.path == "/ausbruch.css":
            return self._datei("ausbruch.css", "text/css; charset=utf-8")
        if weg.path == "/ausbruch.js":
            return self._datei("ausbruch.js",
                               "application/javascript; charset=utf-8")

        if weg.path == "/api/stand":
            jahr = int(frage.get("jahr", ["2025"])[0])
            raster = frage.get("raster", ["15Min"])[0]
            return self._json({
                "vorrat": ausbruch_daten.bestand(raster, jahr),
                "n_versuche": ausbruch_store.n_versuche(),
                "schwelle": round(ausbruch_store.schwelle_sigma(), 3),
                "aktiv": W.aktiv,
                "felder": _feldliste(),
                "vorgaben": ausbruch.AusbruchConfig().als_dict(),
                "zustand": W.zustand,
            })

        if weg.path == "/api/laeufe":
            df = ausbruch_store.laeufe(limit=100)
            if not df.empty:
                df = df.drop(columns=["config_json", "kennzahlen_json"],
                             errors="ignore")
            return self._json(_tabelle(df))

        if weg.path == "/api/besten":
            lauf = frage.get("lauf", [None])[0] or W.letzter_lauf
            mt = int(frage.get("min_trades", ["3"])[0])
            return self._json(_tabelle(
                ausbruch_store.bestenliste(lauf, min_trades=mt, limit=60)))

        if weg.path == "/api/trades":
            lauf = frage.get("lauf", [None])[0] or W.letzter_lauf
            if not lauf:
                return self._json([])
            df = ausbruch_store.trades_von(lauf)
            if not df.empty:
                df = df.sort_values("einstieg_ts").tail(400)
            return self._json(_tabelle(df))

        if weg.path == "/api/strom":
            return self._strom()

        self._senden(b"nicht gefunden", "text/plain", 404)

    # --- POST --------------------------------------------------------
    def do_POST(self) -> None:  # noqa: N802
        weg = urlparse(self.path)
        koerper = self._koerper()

        if weg.path == "/api/daten":
            ok = W.starten(aufgabe_daten,
                           int(koerper.get("n_symbole", 500)),
                           int(koerper.get("jahr", 2025)),
                           str(koerper.get("raster", "15Min")))
            return self._json({"gestartet": ok})

        if weg.path == "/api/lauf":
            cfg = koerper.get("config", {})
            sauber = _config_pruefen(cfg)
            if isinstance(sauber, str):
                return self._json({"gestartet": False, "fehler": sauber}, 400)
            maxs = koerper.get("max_symbole")
            ok = W.starten(aufgabe_lauf, sauber,
                           int(koerper.get("jahr", 2025)),
                           str(koerper.get("raster", "15Min")),
                           int(maxs) if maxs else None,
                           str(koerper.get("notiz", "")))
            return self._json({"gestartet": ok})

        if weg.path == "/api/stop":
            W.abbruch_gewuenscht = True
            W.log("Abbruch angefordert - der Lauf haelt beim naechsten Schritt.",
                  "warn")
            return self._json({"ok": True})

        self._senden(b"nicht gefunden", "text/plain", 404)

    # --- Live-Strom (Server-Sent Events) -----------------------------
    def _strom(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        q = W.anmelden()
        try:
            while True:
                try:
                    n = q.get(timeout=15)
                except queue.Empty:
                    self.wfile.write(b": halten\n\n")     # Keep-Alive
                    self.wfile.flush()
                    continue
                nutz = json.dumps(n, default=str).encode()
                self.wfile.write(b"data: " + nutz + b"\n\n")
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            W.abmelden(q)


# ---------------------------------------------------------------------
#  Feldbeschreibung fuer die Oberflaeche
# ---------------------------------------------------------------------
GRUPPEN = {
    "Einstieg - was gilt als Ausbruch": [
        ("anstieg_pct", "Mindestanstieg", "%", 0.5, 200),
        ("max_anstieg_pct", "Hoechstanstieg (darueber: Datenfehler)", "%", 1, 1000),
        ("fenster_bars", "Pruef-Fenster", "Bars", 1, 500),
    ],
    "Filter - worauf wir handeln": [
        ("min_preis", "Mindestkurs", "$", 0, 10_000),
        ("max_preis", "Hoechstkurs", "$", 1, 100_000),
        ("min_dollar_volumen", "Mindestumsatz im Fenster", "$", 0, 1e10),
        ("min_rel_volumen", "Umsatzschub (0 = aus)", "x normal", 0, 100),
        ("vol_referenz_bars", "Referenzzeitraum fuer Umsatz", "Bars", 26, 20_000),
    ],
    "Position": [
        ("positions_pct", "Einsatz je Position", "% Depot", 0.1, 100),
        ("max_positionen", "Positionen gleichzeitig", "Stueck", 1, 50),
        ("max_neue_je_bar", "Neue Kaeufe je Bar", "Stueck", 1, 50),
        ("max_investiert_pct", "Hoechstens investiert", "% Depot", 1, 100),
    ],
    "Ausstieg": [
        ("halten_bars", "Spaetestens verkaufen nach", "Bars", 1, 20_000),
        ("gewinn_pct", "Gewinnmitnahme (0 = aus)", "%", 0, 500),
        ("verlust_pct", "Stop (0 = aus)", "%", 0, 100),
        ("trailing_pct", "Nachziehender Stop (0 = aus)", "%", 0, 100),
    ],
    "Kosten - der Hauptgegner": [
        ("spanne_bps", "Geld-Brief-Spanne", "bps", 0, 500),
        ("slippage_bps", "Slippage je Seite", "bps", 0, 500),
    ],
    "Betrieb": [
        ("startkapital", "Startkapital", "$", 1000, 1e9),
        ("sperrfrist_bars", "Sperre nach Verkauf", "Bars", 0, 20_000),
        ("eroeffnung_sperre_bars", "Eroeffnung meiden", "Bars", 0, 26),
        ("schluss_sperre_bars", "Vor Schluss nicht kaufen", "Bars", 0, 26),
    ],
}

HILFE = {
    "anstieg_pct": "Um so viel muss der Kurs im Fenster gestiegen sein, damit gekauft wird. Deine Idee: 10-20 %.",
    "max_anstieg_pct": "Ein Sprung von +300 % ist fast immer eine Kapitalmassnahme oder ein Datenfehler - nicht handelbar.",
    "fenster_bars": "Ueber welchen Zeitraum der Anstieg zaehlt. Bei 15-Min-Bars: 4 = 1 Stunde, 8 = 2 Stunden, 26 = 1 Handelstag.",
    "min_dollar_volumen": "Gehandelter Gegenwert im Fenster. Ein Ausbruch ohne Umsatz ist nicht handelbar - die eigene Order bewegt ihn selbst.",
    "min_rel_volumen": "Umsatz im Fenster gegen den ueblichen Umsatz. Bei Ausbruechen der aussagekraeftigste Filter ueberhaupt.",
    "positions_pct": "Deine Idee: 15 %. Achtung - 15 % je Position und 6 Positionen sind 90 % des Depots in sechs sehr volatilen Werten.",
    "max_neue_je_bar": "Bremse: Ein Marktbeben loest sonst 50 Signale zugleich aus und das ganze Depot laeuft in EINE Bewegung.",
    "halten_bars": "26 Bars = 1 Handelstag. Kurze Haltedauer heisst viel Umschlag heisst hohe Kosten.",
    "gewinn_pct": "Bei welchem Gewinn verkauft wird. Zu eng schneidet genau die Ausreisser ab, von denen die Strategie lebt.",
    "verlust_pct": "Bei welchem Verlust verkauft wird. Das ist die Notbremse dieser Strategie.",
    "trailing_pct": "Stop, der dem Hoechstkurs folgt. Laesst Gewinner laufen - im 15-Jahre-Lernlauf war das die schaedlichste Achse (t = -3,53).",
    "spanne_bps": "12,2 bps ist der gemessene Median des liquiden Universums (BEFUNDE §G54). Fuer einen Wert mitten im Ausbruch ist das die UNTERGRENZE - 25-50 ist realistischer.",
    "slippage_bps": "Abweichung vom erwarteten Kurs. Bei schnellen Bewegungen deutlich hoeher als im Normalbetrieb.",
    "sperrfrist_bars": "Ohne Sperre kauft die Strategie denselben Ausbruch mehrfach hintereinander.",
    "eroeffnung_sperre_bars": "Die ersten Minuten haben weite Spannen und sprunghafte Kurse. 37_spannen_messen.py schliesst denselben Zeitraum aus.",
}


def _feldliste() -> list[dict]:
    typen = {f.name: f.type for f in dc_fields(ausbruch.AusbruchConfig)}
    out = []
    for gruppe, felder in GRUPPEN.items():
        for name, label, einheit, lo, hi in felder:
            out.append({"gruppe": gruppe, "name": name, "label": label,
                        "einheit": einheit, "min": lo, "max": hi,
                        "hilfe": HILFE.get(name, ""),
                        "ganzzahl": "int" in str(typen.get(name, ""))})
    out.append({"gruppe": "Betrieb", "name": "ueber_nacht",
                "label": "Ueber Nacht halten", "einheit": "", "schalter": True,
                "hilfe": "Aus = alles vor Handelsschluss glattstellen. "
                         "Schaltet Gap-Risiko ab, erhoeht aber den Umschlag."})
    return out


def _config_pruefen(roh: dict):
    """Nimmt nur bekannte Felder und haelt sie in ihren Grenzen.

    Eine Oberflaeche, die ungeprueft in eine Dataclass schreibt, macht
    aus einem Tippfehler einen stillen Fehllauf. Rueckgabe: sauberes
    dict oder ein Fehlertext.
    """
    erlaubt = {f.name: f for f in dc_fields(ausbruch.AusbruchConfig)}
    grenzen = {n: (lo, hi) for felder in GRUPPEN.values()
               for n, _, _, lo, hi in felder}
    sauber: dict = {}
    for name, wert in (roh or {}).items():
        if name not in erlaubt:
            continue
        typ = str(erlaubt[name].type)
        try:
            if "bool" in typ:
                sauber[name] = bool(wert)
                continue
            zahl = float(wert)
            if zahl != zahl:
                return f"{name}: keine Zahl"
            lo, hi = grenzen.get(name, (float("-inf"), float("inf")))
            if not (lo <= zahl <= hi):
                return f"{name} = {zahl:g} liegt ausserhalb von {lo:g}..{hi:g}"
            sauber[name] = int(round(zahl)) if "int" in typ else zahl
        except (TypeError, ValueError):
            return f"{name}: {wert!r} ist keine gueltige Zahl"
    if sauber.get("verlust_pct", 1) == 0 and sauber.get("gewinn_pct", 1) == 0 \
            and sauber.get("trailing_pct", 1) == 0:
        # Kein Fehler, aber es muss gesagt werden.
        pass
    return sauber


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--kein-browser", action="store_true")
    args = p.parse_args()

    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    adresse = f"http://127.0.0.1:{args.port}/"

    print("=" * 74)
    print("  AUSBRUCH-WERKSTATT")
    print("=" * 74)
    print(f"  Oberflaeche : {adresse}")
    print(f"  Vorrat      : {ausbruch_daten.VORRAT}")
    print(f"  Datenbank   : {ausbruch_store.DB}")
    print(f"  Versuche    : {ausbruch_store.n_versuche()}  "
          f"(Schwelle t > {ausbruch_store.schwelle_sigma():.2f})")
    print()
    print("  Nur auf 127.0.0.1 - von aussen nicht erreichbar.")
    print("  Beenden mit Strg+C.")
    print("=" * 74)

    if not args.kein_browser:
        threading.Timer(0.7, lambda: webbrowser.open(adresse)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Beendet.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
