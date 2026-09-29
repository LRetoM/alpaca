"""Zentrale Konfiguration.

Alle Zugangsdaten kommen aus der .env-Datei im Projekt-Root.
Niemals Keys direkt in den Code schreiben!
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# ACHTUNG: Datenbanken und Cache liegen bewusst AUSSERHALB von PROJECT_ROOT,
# obwohl das Projekt selbst unter ~/Documents liegt. macOS' TCC-Dateischutz
# fuer den "Dokumente"-Ordner gilt fuer interaktive Terminals, aber nicht
# zuverlaessig fuer einen von launchd headless gestarteten Hintergrunddienst -
# derselbe Python-Prozess, dieselbe Binary, aber ohne die Zustimmung, die
# ein Terminal implizit mitbringt. Genau das hat schon einmal die Log-Dateien
# blockiert (siehe install_service.sh) und am 30./31.07.2026 den Handelsbot
# abstuerzen lassen: state.sqlite lag unter ~/Documents/alpaca/data, ein
# Schreibversuch daraus schlug mit "unable to open database file" fehl -
# ausgerechnet im Fehlerbehandler, der genau diesen Vorfall protokollieren
# wollte, wodurch ein harmloser Netzwerk-Haenger zum Totalabsturz wurde.
#
# ~/Library/Application Support ist der dafuer vorgesehene Ort und liegt
# ausserhalb des TCC-geschuetzten Bereichs.
DATA_DIR = Path.home() / "Library" / "Application Support" / "alpaca-bot" / "data"
CACHE_DIR = DATA_DIR / "cache"
RESULTS_DIR = PROJECT_ROOT / "results"

for _d in (DATA_DIR, CACHE_DIR, RESULTS_DIR):
    _d.mkdir(parents=True, exist_ok=True)

load_dotenv(PROJECT_ROOT / ".env")


class ConfigError(RuntimeError):
    """Fehlende oder unplausible Konfiguration."""


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    return default if raw is None or raw == "" else float(raw)


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    return default if raw is None or raw == "" else int(raw)


@dataclass(frozen=True)
class Settings:
    api_key: str
    secret_key: str
    paper: bool
    data_feed: str
    """'iex' = kostenlos (real-time, aber nur IEX-Volumen).
    'sip' = alle Boersen, braucht das kostenpflichtige Algo-Trader-Plus-Abo."""

    # --- Risiko-Leitplanken (werden in trading.py erzwungen) ---
    max_position_pct: float
    """Maximaler Anteil des Portfoliowerts in EINER Position (0.1 = 10 %)."""
    max_order_notional: float
    """Harte Obergrenze in USD pro einzelner Order."""
    allow_live_trading: bool
    """Muss explizit auf true stehen, sonst blockt der Code echtes Geld."""

    @property
    def is_paper(self) -> bool:
        return self.paper


def get_settings() -> Settings:
    """Laedt die Settings und prueft, dass die Keys gesetzt sind."""
    api_key = os.getenv("ALPACA_API_KEY", "").strip()
    secret_key = os.getenv("ALPACA_SECRET_KEY", "").strip()

    if not api_key or not secret_key:
        raise ConfigError(
            "ALPACA_API_KEY / ALPACA_SECRET_KEY fehlen.\n"
            f"  -> Kopiere .env.example nach .env ({PROJECT_ROOT / '.env'})\n"
            "  -> und trage deine Paper-Trading-Keys ein."
        )
    if api_key.startswith("<") or secret_key.startswith("<"):
        raise ConfigError("In der .env stehen noch die Platzhalter statt echter Keys.")

    paper = _env_bool("ALPACA_PAPER", True)
    feed = os.getenv("ALPACA_DATA_FEED", "iex").strip().lower()
    if feed not in {"iex", "sip", "otc", "delayed_sip", "boats", "overnight"}:
        raise ConfigError(f"Unbekannter ALPACA_DATA_FEED: {feed!r}")

    settings = Settings(
        api_key=api_key,
        secret_key=secret_key,
        paper=paper,
        data_feed=feed,
        max_position_pct=_env_float("MAX_POSITION_PCT", 0.10),
        max_order_notional=_env_float("MAX_ORDER_NOTIONAL", 5_000.0),
        allow_live_trading=_env_bool("ALLOW_LIVE_TRADING", False),
    )

    if not settings.paper and not settings.allow_live_trading:
        raise ConfigError(
            "ALPACA_PAPER=false, aber ALLOW_LIVE_TRADING ist nicht gesetzt.\n"
            "Das ist die Sicherung gegen versehentliches Handeln mit echtem Geld."
        )
    return settings


def code_version() -> str:
    """Git-Commit, der diesen Lauf erzeugt hat - fuer BEIDE Pfade.

    **Unverzichtbar fuer die Frage "ist es besser geworden?".** Ohne diese
    Angabe lassen sich Codeaenderungen nicht von Marktphasen trennen: Wird
    ein Ergebnis schlechter, ist nicht mehr feststellbar, ob eine
    Aenderung schuld war oder nur der Markt gedreht hat. Und ohne diese
    Unterscheidung laesst sich auch nicht gezielt auf einen besseren Stand
    zurueckrollen.

    `+dirty` heisst: Zum Zeitpunkt des Laufs lagen nicht eingecheckte
    Aenderungen vor. Solche Daten sind fuer einen Versionsvergleich nur
    eingeschraenkt brauchbar - der Commit allein beschreibt den Code dann
    nicht vollstaendig.

    **Warum hier und nicht in shadow.py:** Dort stand die Funktion mit
    `cwd=DATA_DIR.parent`. Solange die Datenbanken im Projektordner lagen,
    war das zufaellig richtig. Der Umzug nach ~/Library/Application Support
    (30.07.2026, TCC-Dateischutz) zeigte dorthin auf ein Verzeichnis OHNE
    Git - seitdem lieferte sie stumm 'unbekannt'. Gemessen am 15.08.2026:
    8.278 von 12.516 Schattenvorhersagen ohne Version, also zwei Drittel
    der Daten ohne Zuordnung. Der Bezug muss deshalb fest auf
    PROJECT_ROOT stehen, nicht auf einen Datenpfad.
    """
    import subprocess

    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=5,
        )
        v = out.stdout.strip()
        if not v:
            return "unbekannt"
        dirty = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=no"],
            cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=5,
        ).stdout.strip()
        return f"{v}+dirty" if dirty else v
    except Exception:  # noqa: BLE001 - fehlendes git darf den Lauf nie stoppen
        return "unbekannt"
