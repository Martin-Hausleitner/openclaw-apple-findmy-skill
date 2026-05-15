#!/usr/bin/env bash
set -euo pipefail

LABEL_STACK="ai.openclaw.findmy.owntracks-stack"
LABEL_BRIDGE="ai.openclaw.findmy.owntracks-bridge"
ROOT="/Users/mh/Documents/Playground/openclaw-apple-findmy-skill"
STATE="/Users/mh/.openclaw/workspace/state/apple-find-my/owntracks"
PYTHON="/Users/mh/.openclaw/workspace/.venvs/findmy-key-extractor/bin/python"
BRIDGE="$ROOT/scripts/owntracks_findmy_bridge.py"
COMPOSE="$ROOT/docker/owntracks/docker-compose.yml"
LAUNCH="$HOME/Library/LaunchAgents"

mkdir -p "$LAUNCH" "$STATE/config" "$STATE/store"
chmod +x "$BRIDGE"

cat > "$STATE/config/config.js" <<'CONFIG'
window.owntracks = window.owntracks || {};
window.owntracks.config = {
  locale: "de-DE",
  layers: {
    last: true,
    line: true,
    points: true,
    heatmap: false,
  },
  onLocationChange: {
    fitView: true,
    reloadHistory: true,
  },
  showDistanceTravelled: true,
};
CONFIG

docker compose -f "$COMPOSE" up -d

cat > "$LAUNCH/$LABEL_STACK.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$LABEL_STACK</string>
  <key>ProgramArguments</key>
  <array>
    <string>/opt/homebrew/bin/docker</string>
    <string>compose</string>
    <string>-f</string>
    <string>$COMPOSE</string>
    <string>up</string>
    <string>-d</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>StandardOutPath</key>
  <string>$STATE/stack-launch.stdout.log</string>
  <key>StandardErrorPath</key>
  <string>$STATE/stack-launch.stderr.log</string>
  <key>WorkingDirectory</key>
  <string>$ROOT</string>
</dict>
</plist>
PLIST

cat > "$LAUNCH/$LABEL_BRIDGE.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$LABEL_BRIDGE</string>
  <key>ProgramArguments</key>
  <array>
    <string>$PYTHON</string>
    <string>$BRIDGE</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>StartInterval</key>
  <integer>600</integer>
  <key>StandardOutPath</key>
  <string>$STATE/bridge-launch.stdout.log</string>
  <key>StandardErrorPath</key>
  <string>$STATE/bridge-launch.stderr.log</string>
  <key>WorkingDirectory</key>
  <string>$ROOT</string>
</dict>
</plist>
PLIST

plutil -lint "$LAUNCH/$LABEL_STACK.plist" "$LAUNCH/$LABEL_BRIDGE.plist"
launchctl bootout "gui/$(id -u)" "$LAUNCH/$LABEL_STACK.plist" >/dev/null 2>&1 || true
launchctl bootout "gui/$(id -u)" "$LAUNCH/$LABEL_BRIDGE.plist" >/dev/null 2>&1 || true
launchctl bootstrap "gui/$(id -u)" "$LAUNCH/$LABEL_STACK.plist"
launchctl bootstrap "gui/$(id -u)" "$LAUNCH/$LABEL_BRIDGE.plist"
launchctl kickstart -k "gui/$(id -u)/$LABEL_STACK"
sleep 3
launchctl kickstart -k "gui/$(id -u)/$LABEL_BRIDGE"
"$PYTHON" "$BRIDGE" --print-summary
echo "OwnTracks UI: http://127.0.0.1:18084"
