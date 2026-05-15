# OpenClaw Apple Find My Skill

Local Apple Find My exporter for Martin's OpenClaw and Hermes agents.

The repo contains code and a reusable skill only. It does **not** contain keys,
cache files, decrypted databases, exact coordinates, or private location dumps.

## Current Local Result

On Martin's Mac, the private setup currently exports:

- 14 Find My items / item parts
- 20 devices
- 3 family members
- 15 FollowMyFriends people tracked in the app
- 9+ FollowMyFriends handles enriched from local Contacts / same-person matching
- Contact enrichment now includes matched emails, phone numbers, and photo presence
- 15 friend-cache entries
- 2 item groups
- 6 safe-location records
- FindMySync local receiver tested with 20 unique FindMySync IDs
- OwnTracks local web viewer receives Find My people/devices/items traces;
  current seed sent 34 local points into 31 unique visible tracks

## How It Works

1. Apple Find My writes encrypted local caches.
2. Martin extracts local keys once on his own Mac.
3. `scripts/openclaw_findmy_export.py` decrypts the local caches on-device.
4. Local macOS Contacts are indexed for email/phone matching.
5. Exact data is written only to a private local state file with mode `0600`.
6. Agents read the redacted summary for normal answers.
7. Optional: a patched local `FindMySync.app` sends FindMySync-compatible
   events to a local-only receiver at `http://127.0.0.1:8765/findmysync`.
8. Optional: OwnTracks Recorder + Frontend visualize the local exact export as
   private map traces at `http://127.0.0.1:18084`.

## Local Paths

Private state:

```text
/Users/mh/.openclaw/workspace/state/apple-find-my/export
```

Redacted summary:

```text
/Users/mh/.openclaw/workspace/state/apple-find-my/export/latest-summary.json
```

## Install Autostart

```bash
scripts/install_launchagent.sh
```

This installs `ai.openclaw.findmy.export`, running every 5 minutes.

For the optional FindMySync local receiver:

```bash
scripts/install_findmysync_receiver_launchagent.sh
scripts/install_findmysync_app_launchagent.sh
```

This installs `ai.openclaw.findmysync.receiver` and
`ai.openclaw.findmysync.app`.

For the optional local OwnTracks web viewer:

```bash
scripts/install_owntracks_stack.sh
```

This starts:

- `openclaw-owntracks-mqtt`
- `openclaw-owntracks-recorder`
- `openclaw-owntracks-frontend`
- LaunchAgent `ai.openclaw.findmy.owntracks-stack`
- LaunchAgent `ai.openclaw.findmy.owntracks-bridge`

The bridge runs every 5 minutes and posts only to the local recorder.

## One-Shot Export

```bash
/Users/mh/.openclaw/workspace/.venvs/findmy-key-extractor/bin/python scripts/openclaw_findmy_export.py --print-summary
```

## FindMySync Local Test

The receiver UI is local only:

```text
http://127.0.0.1:8765/findmysync
```

The working FindMySync variant reads the private exact export and posts
FindMySync-compatible events to that endpoint. The receiver captures exact
payloads only in Martin's private state directory and prints redacted summaries.

## OwnTracks Local Web Viewer

The OwnTracks UI is local only:

```text
http://127.0.0.1:18084
```

The recorder API is bound to localhost:

```text
http://127.0.0.1:18083
```

The bridge converts the private exact export into OwnTracks-compatible points
for `people`, `devices`, and `items`. Current and future points are stored
locally under:

```text
/Users/mh/.openclaw/workspace/state/apple-find-my/owntracks
```

Do not publish this store. It contains exact private location history.

## Security Reset After Key Extraction

After extracting keys, re-enable macOS protections from Recovery:

```bash
nvram -d boot-args
csrutil enable
```

Then reboot. The extracted local keys remain usable for the exporter.
