#!/usr/bin/env bash
set -euo pipefail

LABEL="ai.openclaw.findmy.export"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
PYTHON="/Users/mh/.openclaw/workspace/.venvs/findmy-key-extractor/bin/python"
SCRIPT="/Users/mh/Documents/Playground/openclaw-apple-findmy-skill/scripts/openclaw_findmy_export.py"
STATE="/Users/mh/.openclaw/workspace/state/apple-find-my/export"

mkdir -p "$HOME/Library/LaunchAgents" "$STATE"

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
  <key>RunAtLoad</key>
  <true/>
  <key>StartInterval</key>
  <integer>600</integer>
  <key>StandardOutPath</key>
  <string>$STATE/launchagent.stdout.log</string>
  <key>StandardErrorPath</key>
  <string>$STATE/launchagent.stderr.log</string>
  <key>WorkingDirectory</key>
  <string>/Users/mh/Documents/Playground/openclaw-apple-findmy-skill</string>
</dict>
</plist>
PLIST

chmod 0644 "$PLIST"
launchctl bootout "gui/$(id -u)" "$PLIST" >/dev/null 2>&1 || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
launchctl kickstart -k "gui/$(id -u)/$LABEL"
echo "Installed $LABEL -> $PLIST"
