#!/usr/bin/env bash
set -euo pipefail

LABEL="ai.openclaw.findmy.status-publisher"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
SCRIPT="/Users/mh/Documents/Playground/openclaw-apple-findmy-skill/scripts/publish_findmy_agent_status.py"
STATE="/Users/mh/.openclaw/workspace/state/apple-find-my/status-publisher"
PYTHON="/usr/bin/python3"

mkdir -p "$STATE" "$(dirname "$PLIST")"
chmod +x "$SCRIPT"

cat > "$PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>$PYTHON</string>
    <string>$SCRIPT</string>
  </array>
  <key>StartInterval</key>
  <integer>600</integer>
  <key>RunAtLoad</key>
  <true/>
  <key>StandardOutPath</key>
  <string>$STATE/launchagent.stdout.log</string>
  <key>StandardErrorPath</key>
  <string>$STATE/launchagent.stderr.log</string>
</dict>
</plist>
PLIST

launchctl bootout "gui/$(id -u)" "$PLIST" >/dev/null 2>&1 || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
launchctl enable "gui/$(id -u)/$LABEL"
launchctl kickstart -k "gui/$(id -u)/$LABEL" >/dev/null 2>&1 || true
echo "$PLIST: OK"
