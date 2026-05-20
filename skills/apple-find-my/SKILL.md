---
name: apple-find-my
description: Use when Martin asks OpenClaw or Hermes to read, verify, install, debug, or dashboard his consented local Apple Find My people, devices, items, AirTags, FollowMyFriends, FindMySync, OwnTracks, Traccar, or GeoPulse data.
---

# Apple Find My Local Pipeline

Use this skill for Martin's local Apple Find My stack. The stack keeps private
location data on the Mac and exposes only redacted summaries by default.

## Safety Rules

- Never print Apple Find My keys, raw decrypted plist rows, raw SQLite rows,
  dashboard login files, raw GPS payloads, or exact coordinates by default.
- Use the redacted summary for normal answers:

```bash
cat /Users/mh/.openclaw/workspace/state/apple-find-my/export/latest-summary.json
```

- Use exact private data only for local bridge/debug work and only summarize
  results in chat.
- Do not commit or publish files under:

```text
/Users/mh/.openclaw/workspace/state/apple-find-my
```

## Mental Model

| Component | Role |
|---|---|
| FollowMyFriends | people/friends source |
| FindMySync | devices/items sender shape and fallback |
| `openclaw_findmy_export.py` | normalized local export |
| OwnTracks | lightweight 34-track map |
| Traccar | multi-device dashboard |
| GeoPulse | timeline/GPS-data dashboard |

Current verified shape:

```text
34 tracks = 14 people + 9 devices + 11 items
```

Traccar currently stores 31 merged dashboard devices because duplicate Find My
IDs are collapsed before publishing to Traccar.

FindMySync does **not** provide people in the current local setup. FollowMyFriends
does **not** provide AirTags/items as its primary data source.

## Core Commands

Run a one-shot export:

```bash
/Users/mh/.openclaw/workspace/.venvs/findmy-key-extractor/bin/python \
  /Users/mh/Documents/Playground/openclaw-apple-findmy-skill/scripts/openclaw_findmy_export.py \
  --print-summary
```

Install or refresh the 10-minute core export:

```bash
/Users/mh/Documents/Playground/openclaw-apple-findmy-skill/scripts/install_launchagent.sh
```

Install existing-tool path:

```bash
/Users/mh/Documents/Playground/openclaw-apple-findmy-skill/scripts/install_findmysync_receiver_launchagent.sh
/Users/mh/Documents/Playground/openclaw-apple-findmy-skill/scripts/install_findmysync_app_launchagent.sh
```

Install dashboards:

```bash
/Users/mh/Documents/Playground/openclaw-apple-findmy-skill/scripts/install_owntracks_stack.sh
/Users/mh/Documents/Playground/openclaw-apple-findmy-skill/scripts/install_traccar_stack.sh
/Users/mh/Documents/Playground/openclaw-apple-findmy-skill/scripts/install_geopulse_stack.sh
```

## Dashboard URLs

```text
http://127.0.0.1:8765/findmysync  # local FindMySync receiver status
http://127.0.0.1:18084            # OwnTracks
http://127.0.0.1:18082            # Traccar
http://127.0.0.1:18085            # GeoPulse
```

Dashboard credentials are private local files:

```text
/Users/mh/.openclaw/workspace/state/apple-find-my/traccar/login.env
/Users/mh/.openclaw/workspace/state/apple-find-my/geopulse/login.env
```

Do not print those files unless Martin explicitly asks for local login details.

## Verify Bridges

Run local bridge checks:

```bash
cd /Users/mh/Documents/Playground/openclaw-apple-findmy-skill

/Users/mh/.openclaw/workspace/.venvs/findmy-key-extractor/bin/python \
  scripts/owntracks_findmy_bridge.py --print-summary
/Users/mh/.openclaw/workspace/.venvs/findmy-key-extractor/bin/python \
  scripts/traccar_findmy_bridge.py --print-summary
/Users/mh/.openclaw/workspace/.venvs/findmy-key-extractor/bin/python \
  scripts/geopulse_findmy_bridge.py --print-summary
```

Expected:

```text
points_seen/tracks = 34
errors = []
```

Run a redacted full-stack healthcheck:

```bash
/Users/mh/Documents/Playground/openclaw-apple-findmy-skill/scripts/findmy_healthcheck.py
```

Run or install the OneDrive backup:

```bash
/Users/mh/Documents/Playground/openclaw-apple-findmy-skill/scripts/backup_findmy_to_onedrive.py
/Users/mh/Documents/Playground/openclaw-apple-findmy-skill/scripts/install_onedrive_backup_launchagent.sh
```

Verify Traccar/GeoPulse counts through APIs without printing coordinates:

```bash
curl -sS 'http://127.0.0.1:18085/api/gps?limit=100' -b /tmp/geopulse.cookies \
  | jq '.data.pagination.total'

curl -sS http://127.0.0.1:18082/api/devices -b /tmp/traccar.cookies | jq 'length'
curl -sS http://127.0.0.1:18082/api/positions -b /tmp/traccar.cookies | jq 'length'
```

## Autostart

Current 10-minute LaunchAgents:

```text
ai.openclaw.findmy.export
ai.openclaw.findmy.owntracks-bridge
ai.openclaw.findmy.traccar-bridge
ai.openclaw.findmy.geopulse-bridge
ai.openclaw.findmy.onedrive-backup
```

Persistent/local-start jobs:

```text
ai.openclaw.findmysync.receiver
ai.openclaw.findmysync.app
ai.openclaw.findmy.owntracks-stack
ai.openclaw.findmy.traccar-stack
ai.openclaw.findmy.geopulse-stack
```

OneDrive target:

```text
/Users/mh/Library/CloudStorage/OneDrive-Personal/Anlagen/Backup/OpenClaw-FindMy
```

`Latest/` is redacted and agent-safe. `Archive/Encrypted/` is private and
encrypted; do not print archive contents or the local backup passphrase.

Inspect:

```bash
launchctl print gui/$(id -u)/ai.openclaw.findmy.export
```

## Required Private Files

Keys are expected at:

```text
/Users/mh/.openclaw/workspace/skills/apple-find-my/vendor/findmy-key-extractor/keys/LocalStorage.key
/Users/mh/.openclaw/workspace/skills/apple-find-my/vendor/findmy-key-extractor/keys/FMIPDataManager.bplist
/Users/mh/.openclaw/workspace/skills/apple-find-my/vendor/findmy-key-extractor/keys/FMFDataManager.bplist
```

If missing, pause and use Martin's private key extraction flow. Do not parse or
publish raw encrypted cache files.

## Documentation

Repo:

```text
/Users/mh/Documents/Playground/openclaw-apple-findmy-skill
```

Read:

```text
README.md
docs/SETUP.md
docs/IMPLEMENTATION.md
```
