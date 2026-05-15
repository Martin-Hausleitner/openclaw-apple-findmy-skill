#!/usr/bin/env bash
set -euo pipefail

LABEL="ai.openclaw.findmysync.app"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
STATE="/Users/mh/.openclaw/workspace/state/apple-find-my/findmysync"

mkdir -p "$HOME/Library/LaunchAgents" "$STATE"

cat > "$PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/open</string>
    <string>-gj</string>
    <string>/Applications/FindMySync.app</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>StandardOutPath</key>
  <string>$STATE/app-launch.stdout.log</string>
  <key>StandardErrorPath</key>
  <string>$STATE/app-launch.stderr.log</string>
</dict>
</plist>
PLIST

plutil -lint "$PLIST"
launchctl bootout "gui/$(id -u)" "$PLIST" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
launchctl enable "gui/$(id -u)/$LABEL"
launchctl print "gui/$(id -u)/$LABEL" | sed -n '1,80p'
