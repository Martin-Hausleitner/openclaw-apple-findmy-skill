# Setup Guide

This guide recreates the local Apple Find My pipeline on Martin's Mac. It keeps
private data outside the Git repository.

## Prerequisites

- macOS with Find My already signed in and showing the expected devices/items.
- Local key extraction already completed:

```text
/Users/mh/.openclaw/workspace/skills/apple-find-my/vendor/findmy-key-extractor/keys/LocalStorage.key
/Users/mh/.openclaw/workspace/skills/apple-find-my/vendor/findmy-key-extractor/keys/FMIPDataManager.bplist
/Users/mh/.openclaw/workspace/skills/apple-find-my/vendor/findmy-key-extractor/keys/FMFDataManager.bplist
```

- Python venv:

```text
/Users/mh/.openclaw/workspace/.venvs/findmy-key-extractor/bin/python
```

- Docker Desktop or compatible Docker CLI for OwnTracks, Traccar, and GeoPulse.

## 1. Install Core Exporter

```bash
cd /Users/mh/Documents/Playground/openclaw-apple-findmy-skill
scripts/install_launchagent.sh
```

This installs:

```text
ai.openclaw.findmy.export
```

It runs every 10 minutes and writes:

```text
/Users/mh/.openclaw/workspace/state/apple-find-my/export/latest-summary.json
/Users/mh/.openclaw/workspace/state/apple-find-my/export/private-exact.json
```

## 2. Install Existing-Tool Path

FindMySync is kept as a local Devices/Items sender shape and fallback/control
path:

```bash
scripts/install_findmysync_receiver_launchagent.sh
scripts/make_findmysync_dockless.sh
scripts/install_findmysync_app_launchagent.sh
scripts/disable_visible_findmy_pollers.sh
```

Receiver UI:

```text
http://127.0.0.1:8765/findmysync
```

FindMySync events are private:

```text
/Users/mh/.openclaw/workspace/state/apple-find-my/findmysync/events.jsonl
```

## 3. Install OwnTracks

```bash
scripts/install_owntracks_stack.sh
```

UI:

```text
http://127.0.0.1:18084
```

Installed jobs:

```text
ai.openclaw.findmy.owntracks-stack
ai.openclaw.findmy.owntracks-bridge
```

## 4. Install Traccar

```bash
scripts/install_traccar_stack.sh
```

UI:

```text
http://127.0.0.1:18082
```

Traccar's local OsmAnd ingest endpoint is bound to:

```text
127.0.0.1:15055
```

Installed jobs:

```text
ai.openclaw.findmy.traccar-stack
ai.openclaw.findmy.traccar-bridge
```

The installer creates or reuses a private local login file:

```text
/Users/mh/.openclaw/workspace/state/apple-find-my/traccar/login.env
```

## 5. Install GeoPulse

```bash
scripts/install_geopulse_stack.sh
```

UI:

```text
http://127.0.0.1:18085
```

Installed jobs:

```text
ai.openclaw.findmy.geopulse-stack
ai.openclaw.findmy.geopulse-bridge
```

The installer creates or reuses private local files:

```text
/Users/mh/.openclaw/workspace/state/apple-find-my/geopulse/login.env
/Users/mh/.openclaw/workspace/state/apple-find-my/geopulse/bridge.env
```

## Verify Counts

Core export:

```bash
/Users/mh/.openclaw/workspace/.venvs/findmy-key-extractor/bin/python \
  scripts/openclaw_findmy_export.py --print-summary
```

Bridges:

```bash
/Users/mh/.openclaw/workspace/.venvs/findmy-key-extractor/bin/python \
  scripts/owntracks_findmy_bridge.py --print-summary
/Users/mh/.openclaw/workspace/.venvs/findmy-key-extractor/bin/python \
  scripts/traccar_findmy_bridge.py --print-summary
/Users/mh/.openclaw/workspace/.venvs/findmy-key-extractor/bin/python \
  scripts/geopulse_findmy_bridge.py --print-summary
```

Expected current count:

```text
OwnTracks/GeoPulse: 34 tracks: 14 people, 9 devices, 11 items
Traccar: 31 merged tracks after duplicate Find My IDs are collapsed
```

## Verify Autostart

```bash
for label in \
  ai.openclaw.findmy.export \
  ai.openclaw.findmy.owntracks-bridge \
  ai.openclaw.findmy.traccar-bridge \
  ai.openclaw.findmy.geopulse-bridge \
  ai.openclaw.findmy.onedrive-backup \
  ai.openclaw.findmysync.receiver \
  ai.openclaw.findmysync.app
do
  echo "--- $label"
  launchctl print "gui/$(id -u)/$label" | grep -E 'state =|last exit code|run interval' || true
done
```

## OneDrive Backup

The backup job stores redacted summaries and encrypted private snapshots in:

```text
/Users/mh/Library/CloudStorage/OneDrive-Personal/Anlagen/Backup/OpenClaw-FindMy
```

Install or refresh it:

```bash
scripts/install_onedrive_backup_launchagent.sh
```

Run it manually:

```bash
scripts/backup_findmy_to_onedrive.py
```

Verify the latest encrypted backup without extracting private rows:

```bash
scripts/verify_onedrive_backup.py
```

The private archive includes the normalized private export, decrypted
FollowMyFriends cache snapshot, FindMySync receiver events, and bridge logs.
It is encrypted before it enters OneDrive. The local passphrase remains under:

```text
/Users/mh/.openclaw/workspace/state/apple-find-my/backup/onedrive-backup-passphrase.txt
```

For a redacted end-to-end status report:

```bash
scripts/findmy_healthcheck.py
```

Normal assistants can read:

```text
/Users/mh/Library/CloudStorage/OneDrive-Personal/Anlagen/Backup/OpenClaw-FindMy/Status/healthcheck.json
/Users/mh/Library/CloudStorage/OneDrive-Personal/Anlagen/Backup/OpenClaw-FindMy/Status/quality-report.md
/Users/mh/Library/CloudStorage/OneDrive-Personal/Anlagen/Backup/OpenClaw-FindMy/Status/assistant-brief.md
/Users/mh/Library/CloudStorage/OneDrive-Personal/Anlagen/Backup/OpenClaw-FindMy/Status/sync-sentinel.json
```

## Source Comparison

| Source | Role |
|---|---|
| FollowMyFriends | People/Friends source |
| FindMySync | Devices/Items sender shape |
| OpenClaw exporter | Normalized local data source for agents/dashboards |
| OwnTracks | lightweight map |
| Traccar | multi-device dashboard |
| GeoPulse | timeline/GPS-data dashboard |

## Troubleshooting

- If counts are zero, run the core exporter manually first.
- If dashboards are empty, run the relevant bridge manually with
  `--print-summary`.
- If Traccar login fails, inspect `traccar/login.env`.
- If GeoPulse login/source fails, inspect `geopulse/login.env` and
  `geopulse/bridge.env`.
- If key files are missing, do not continue with raw cache files; repeat the
  local key extraction flow privately.

## Security Reset Reminder

If SIP or boot args were disabled during key extraction, re-enable protections
from Recovery:

```bash
nvram -d boot-args
csrutil enable
```

Then reboot.
