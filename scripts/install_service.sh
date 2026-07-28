#!/usr/bin/env bash
# Richtet den Bot als macOS-Dienst ein - startet automatisch neu.
#
# launchd ist der richtige Weg auf macOS: Es startet den Prozess neu, wenn
# er stirbt, und startet ihn beim Anmelden erneut. Damit laeuft der Bot
# auch nach einem Absturz oder Neustart des Rechners weiter.
#
#   ./scripts/install_service.sh            # einrichten (Vorschaumodus)
#   ./scripts/install_service.sh --live     # mit Orders im Papierdepot
#   ./scripts/install_service.sh --remove   # wieder entfernen
#
# Danach:
#   launchctl list | grep alpacabot         # laeuft er?
#   tail -f logs/daemon.log                 # was tut er?
#   python scripts/12_daemon.py --status    # Zustand

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LABEL="de.local.alpacabot"
PLIST="$HOME/Library/LaunchAgents/${LABEL}.plist"
PYTHON="$PROJECT_DIR/.venv/bin/python"
LOGDIR="$PROJECT_DIR/logs"

if [[ "${1:-}" == "--remove" ]]; then
    launchctl bootout "gui/$(id -u)/${LABEL}" 2>/dev/null || true
    rm -f "$PLIST"
    echo "Dienst entfernt."
    exit 0
fi

MODE_ARG=""
MODE_TEXT="VORSCHAU (keine Orders)"
if [[ "${1:-}" == "--live" ]]; then
    MODE_ARG="<string>--live</string>"
    MODE_TEXT="ORDERS AKTIV (Papierdepot)"
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
        <string>${PROJECT_DIR}/scripts/12_daemon.py</string>
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

    <key>StandardOutPath</key>
    <string>${LOGDIR}/daemon.log</string>
    <key>StandardErrorPath</key>
    <string>${LOGDIR}/daemon.error.log</string>

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
echo "  Modus       : ${MODE_TEXT}"
echo "  Neustart    : automatisch bei Absturz (KeepAlive)"
echo "  Nach Reboot : automatisch beim Anmelden (RunAtLoad)"
echo "  Protokoll   : ${LOGDIR}/daemon.log"
echo
echo "  Status ansehen : python scripts/12_daemon.py --status"
echo "  Live verfolgen : tail -f ${LOGDIR}/daemon.log"
echo "  Entfernen      : ./scripts/install_service.sh --remove"
