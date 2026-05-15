#!/usr/bin/env bash
set -euo pipefail

LABEL="ai.openclaw.findmy.traccar-stack"
STATE="/Users/mh/.openclaw/workspace/state/apple-find-my/traccar"
LAUNCH="$HOME/Library/LaunchAgents"
COMPOSE="$STATE/docker-compose.yml"

mkdir -p "$STATE/data" "$STATE/logs" "$LAUNCH"

cat > "$COMPOSE" <<'YAML'
services:
  traccar:
    image: traccar/traccar:latest
    container_name: openclaw-traccar
    restart: unless-stopped
    ports:
      - "127.0.0.1:18082:8082"
    volumes:
      - /Users/mh/.openclaw/workspace/state/apple-find-my/traccar/data:/opt/traccar/data
      - /Users/mh/.openclaw/workspace/state/apple-find-my/traccar/logs:/opt/traccar/logs
YAML

docker compose -f "$COMPOSE" up -d

cat > "$LAUNCH/$LABEL.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$LABEL</string>
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
  <string>$STATE</string>
</dict>
</plist>
PLIST

plutil -lint "$LAUNCH/$LABEL.plist"
launchctl bootout "gui/$(id -u)" "$LAUNCH/$LABEL.plist" >/dev/null 2>&1 || true
launchctl bootstrap "gui/$(id -u)" "$LAUNCH/$LABEL.plist"
launchctl kickstart -k "gui/$(id -u)/$LABEL"
echo "Traccar UI: http://127.0.0.1:18082"
