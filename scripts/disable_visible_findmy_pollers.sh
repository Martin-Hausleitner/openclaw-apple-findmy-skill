#!/usr/bin/env bash
set -euo pipefail

DISABLED_DIR="$HOME/Library/LaunchAgents.disabled"
FOLLOWMY_LABEL="ai.openclaw.followmyfriends.autofinish"
FOLLOWMY_PLIST="$HOME/Library/LaunchAgents/$FOLLOWMY_LABEL.plist"

mkdir -p "$DISABLED_DIR"

launchctl bootout "gui/$(id -u)" "$FOLLOWMY_PLIST" >/dev/null 2>&1 || true
launchctl disable "gui/$(id -u)/$FOLLOWMY_LABEL" >/dev/null 2>&1 || true

if [[ -f "$FOLLOWMY_PLIST" ]]; then
  mv "$FOLLOWMY_PLIST" \
    "$DISABLED_DIR/$FOLLOWMY_LABEL.plist.disabled-$(date +%Y%m%d-%H%M%S)"
fi

# The current Python exporter reads the local Find My database directly. The old
# FollowMyFriends app can open Apple Find My on a schedule; keep it out of the
# loop to avoid visible Dock/window churn.
/usr/bin/osascript -e 'tell application id "com.followmyfriends.app" to quit' >/dev/null 2>&1 || true
/usr/bin/osascript -e 'tell application id "com.apple.findmy" to quit' >/dev/null 2>&1 || true

# FindMySync has its own setting for hiding Apple's Find My app when it falls
# back to built-in readers. Keep both possible domains set because builds differ.
/usr/bin/defaults write application.mph.am.FindMySync.FindMySync extra_hide_findmy_app -bool true
/usr/bin/defaults write mph.am.FindMySync extra_hide_findmy_app -bool true

echo "Disabled visible Find My pollers. Core Python export remains active."
