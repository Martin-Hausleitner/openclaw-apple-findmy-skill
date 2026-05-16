#!/usr/bin/env bash
set -euo pipefail

APP="/Applications/FindMySync.app"
PLIST="$APP/Contents/Info.plist"
STATE="/Users/mh/.openclaw/workspace/state/apple-find-my/findmysync"

if [[ ! -d "$APP" ]]; then
  echo "FindMySync.app not found at $APP" >&2
  exit 1
fi

backup_dir="$STATE/backups/$(date +%Y%m%d-%H%M%S)-info-plist"
mkdir -p "$backup_dir"
cp "$PLIST" "$backup_dir/Info.plist"

/usr/libexec/PlistBuddy -c 'Delete :LSUIElement' "$PLIST" >/dev/null 2>&1 || true
/usr/libexec/PlistBuddy -c 'Add :LSUIElement bool true' "$PLIST"

# The local build is ad-hoc signed, so re-seal it after editing Info.plist.
/usr/bin/codesign --force --deep --sign - "$APP" >/dev/null
/usr/bin/codesign --verify --deep --strict "$APP" >/dev/null

/usr/bin/defaults write application.mph.am.FindMySync.FindMySync extra_hide_findmy_app -bool true
/usr/bin/defaults write mph.am.FindMySync extra_hide_findmy_app -bool true

echo "FindMySync is dockless (LSUIElement=true). Backup: $backup_dir"
