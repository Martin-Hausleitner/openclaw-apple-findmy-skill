#!/usr/bin/env bash
set -euo pipefail

APP="/Applications/FindMySync.app"
STATE="/Users/mh/.openclaw/workspace/state/apple-find-my/findmysync"

mkdir -p "$STATE"

if [[ ! -d "$APP" ]]; then
  echo "FindMySync.app not found at $APP" >&2
  exit 1
fi

# -g keeps the current foreground app active, -j asks LaunchServices to hide
# the app after launch. The AppleScript pass catches apps that ignore -j.
/usr/bin/open -gj "$APP"

/bin/sleep 2
/usr/bin/osascript <<'APPLESCRIPT' >/dev/null 2>&1 || true
tell application "System Events"
  repeat with processName in {"FindMySync", "Find My Sync"}
    if exists process processName then
      set visible of process processName to false
    end if
  end repeat
end tell
APPLESCRIPT

echo "FindMySync launched hidden"
