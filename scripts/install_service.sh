#!/usr/bin/env bash
# Richtet den Bot als macOS-Dienst ein - startet automatisch neu.
#
# launchd ist der richtige Weg auf macOS: Es startet den Prozess neu, wenn
# er stirbt, und startet ihn beim Anmelden erneut. Damit laeuft der Bot
# auch nach einem Absturz oder Neustart des Rechners weiter.
#
# Es gibt ZWEI unabhaengige Dienste. Sie laufen bewusst getrennt, damit ein
# Fehler im Forschungspfad den Handelspfad nicht mitreisst:
#
#   handel   scripts/12_daemon.py         entscheidet und handelt im Papierdepot
#   schatten scripts/16_shadow_daemon.py  zeichnet Kandidaten auf, sendet NICHTS
#
#   ./scripts/install_service.sh                      # Handel, Vorschaumodus
#   ./scripts/install_service.sh --live               # Handel mit Orders
#   ./scripts/install_service.sh --dienst schatten    # Schattenbetrieb
#   ./scripts/install_service.sh --remove             # Handelsdienst entfernen
#   ./scripts/install_service.sh --dienst schatten --remove
#
# Danach:
#   launchctl list | grep alpaca                  # laeuft er?
#   tail -f logs/daemon.log                       # was tut der Handelsbot?
#   tail -f logs/shadow.log                       # was tut der Schattenbot?
#   python scripts/12_daemon.py --status          # Zustand Handel
#   python scripts/16_shadow_daemon.py --status   # Zustand Schatten

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="$PROJECT_DIR/.venv/bin/python"
LOGDIR="$PROJECT_DIR/logs"

# --- Argumente einlesen (Reihenfolge egal) ---
DIENST="handel"
WANT_LIVE=0
WANT_REMOVE=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        --dienst) DIENST="${2:-}"; shift 2 ;;
        --live)   WANT_LIVE=1; shift ;;
        --remove) WANT_REMOVE=1; shift ;;
        *) echo "Unbekanntes Argument: $1"; exit 1 ;;
    esac
done

case "$DIENST" in
    handel)
        LABEL="de.local.alpacabot"
        SCRIPT="scripts/12_daemon.py"
        LOGBASE="daemon"
        ;;
    schatten)
        LABEL="de.local.alpacashadow"
        SCRIPT="scripts/16_shadow_daemon.py"
        LOGBASE="shadow"
        # Der Schattenbetrieb kennt kein --live: Er importiert `trading.py`
        # nicht und KANN deshalb keine Order senden - nicht nur "darf nicht".
        WANT_LIVE=0
        ;;
    *) echo "FEHLER: --dienst muss 'handel' oder 'schatten' sein."; exit 1 ;;
esac

PLIST="$HOME/Library/LaunchAgents/${LABEL}.plist"

if [[ $WANT_REMOVE -eq 1 ]]; then
    launchctl bootout "gui/$(id -u)/${LABEL}" 2>/dev/null || true
    rm -f "$PLIST"
    echo "Dienst '${DIENST}' (${LABEL}) entfernt."
    exit 0
fi

MODE_ARG=""
MODE_TEXT="VORSCHAU (keine Orders)"
if [[ $WANT_LIVE -eq 1 ]]; then
    MODE_ARG="<string>--live</string>"
    MODE_TEXT="ORDERS AKTIV (Papierdepot)"
fi
if [[ "$DIENST" == "schatten" ]]; then
    MODE_TEXT="SCHATTENBETRIEB (kann keine Orders senden)"
fi

if [[ ! -x "$PYTHON" ]]; then
    echo "FEHLER: $PYTHON nicht gefunden. Zuerst die Umgebung einrichten."
    exit 1
fi
if [[ ! -f "$PROJECT_DIR/.env" ]]; then
    echo "FEHLER: .env fehlt. Ohne Zugangsdaten kann der Bot nicht starten."
    exit 1
fi

mkdir -p "$LOGDIR" "$HOME/Library/LaunchAgents"

cat > "$PLIST" <<PLIST_END
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${LABEL}</string>

    <key>ProgramArguments</key>
    <array>
        <string>${PYTHON}</string>
        <string>${PROJECT_DIR}/${SCRIPT}</string>
        ${MODE_ARG}
    </array>

    <key>WorkingDirectory</key>
    <string>${PROJECT_DIR}</string>

    <!-- Startet den Prozess neu, wenn er stirbt - der Kern der Anforderung -->
    <key>KeepAlive</key>
    <true/>

    <!-- Startet auch beim Anmelden, also nach einem Neustart des Rechners -->
    <key>RunAtLoad</key>
    <true/>

    <!-- Bei sofortigem Absturz nicht in einer Endlosschleife neu starten -->
    <key>ThrottleInterval</key>
    <integer>60</integer>

    <!-- launchd setzt fuer selbst gestartete Dienste sonst ein Soft-Limit
         von 256 offenen Dateien. yfinance oeffnet je Download eine eigene
         SQLite-Verbindung fuer seinen Zeitzonen-Cache, ohne sie zuverlaessig
         zu schliessen - im Dauerbetrieb riss dieses Limit nach einigen
         Stunden (beobachtet 2026-07-29, alle Schritte fielen fuer den Rest
         der Nacht aus). Das Skript hebt das Limit zusaetzlich selbst an
         (_limit_anheben) - diese Angabe ist die zweite Verteidigungslinie. -->
    <key>SoftResourceLimits</key>
    <dict>
        <key>NumberOfFiles</key>
        <integer>8192</integer>
    </dict>
    <key>HardResourceLimits</key>
    <dict>
        <key>NumberOfFiles</key>
        <integer>8192</integer>
    </dict>

    <key>StandardOutPath</key>
    <string>${LOGDIR}/${LOGBASE}.log</string>
    <key>StandardErrorPath</key>
    <string>${LOGDIR}/${LOGBASE}.error.log</string>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PYTHONUNBUFFERED</key>
        <string>1</string>
    </dict>
</dict>
</plist>
PLIST_END

launchctl bootout "gui/$(id -u)/${LABEL}" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"

echo "======================================================================"
echo "  DIENST EINGERICHTET: ${LABEL}"
echo "======================================================================"
echo "  Dienst      : ${DIENST}  (${SCRIPT})"
echo "  Modus       : ${MODE_TEXT}"
echo "  Neustart    : automatisch bei Absturz (KeepAlive)"
echo "  Nach Reboot : automatisch beim Anmelden (RunAtLoad)"
echo "  Protokoll   : ${LOGDIR}/${LOGBASE}.log"
echo
echo "  Status ansehen : python ${SCRIPT} --status"
echo "  Live verfolgen : tail -f ${LOGDIR}/${LOGBASE}.log"
echo "  Entfernen      : ./scripts/install_service.sh --dienst ${DIENST} --remove"
