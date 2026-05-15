---
name: apple-find-my
description: Use when Martin asks OpenClaw or Hermes to read his consented Apple Find My items, devices, family devices, or FollowMyFriends people from the local macOS cache.
---

# Apple Find My Local Export

This skill reads Martin's own Apple Find My data from local macOS caches after
keys have been extracted once on the same Mac.

## Safety

- Never print Apple Find My keys, raw decrypted plist rows, raw SQLite rows, or exact coordinates by default.
- Use `/Users/mh/.openclaw/workspace/state/apple-find-my/export/redacted-summary.json` for normal agent answers.
- Use `/Users/mh/.openclaw/workspace/state/apple-find-my/export/private-exact.json` only when Martin explicitly asks for exact private data.
- Do not commit or publish state files, keys, cache files, or decrypted databases.
- For FindMySync tests, summarize counts from `/Users/mh/.openclaw/workspace/state/apple-find-my/findmysync/events.jsonl`; do not print raw GPS payloads.
- For OwnTracks web viewer checks, summarize counts from the local store under `/Users/mh/.openclaw/workspace/state/apple-find-my/owntracks`; do not print exact coordinates.

## Commands

Run a one-shot export:

```bash
/Users/mh/.openclaw/workspace/.venvs/findmy-key-extractor/bin/python /Users/mh/Documents/Playground/openclaw-apple-findmy-skill/scripts/openclaw_findmy_export.py --print-summary
```

Install/update the hourly LaunchAgent:

```bash
/Users/mh/Documents/Playground/openclaw-apple-findmy-skill/scripts/install_launchagent.sh
```

It currently runs hourly to reduce overhead.

Install/update the optional FindMySync local receiver:

```bash
/Users/mh/Documents/Playground/openclaw-apple-findmy-skill/scripts/install_findmysync_receiver_launchagent.sh
/Users/mh/Documents/Playground/openclaw-apple-findmy-skill/scripts/install_findmysync_app_launchagent.sh
```

Install/update the optional OwnTracks local web viewer:

```bash
/Users/mh/Documents/Playground/openclaw-apple-findmy-skill/scripts/install_owntracks_stack.sh
```

Read the latest redacted status:

```bash
cat /Users/mh/.openclaw/workspace/state/apple-find-my/export/latest-summary.json
```

Open the local FindMySync receiver UI:

```text
http://127.0.0.1:8765/findmysync
```

Open the local OwnTracks web viewer:

```text
http://127.0.0.1:18084
```

Open the local comparison UIs:

```text
http://127.0.0.1:18082  # Traccar
http://127.0.0.1:18085  # GeoPulse
```

## What It Covers

- Items and AirTags from `Items.data`
- Devices from `Devices.data`
- Family members from `FamilyMembers.data`
- Friend cache metadata from `FriendCacheData.data`
- FollowMyFriends local database table counts
- macOS Contacts name, email, phone, and photo-presence enrichment for FollowMyFriends handles
- Optional patched FindMySync.app posts to the local receiver for integration tests
- Optional OwnTracks Recorder + Frontend displays local traces for people, devices, and items

## Required Local Files

Keys are expected at:

- `/Users/mh/.openclaw/workspace/skills/apple-find-my/vendor/findmy-key-extractor/keys/LocalStorage.key`
- `/Users/mh/.openclaw/workspace/skills/apple-find-my/vendor/findmy-key-extractor/keys/FMIPDataManager.bplist`
- `/Users/mh/.openclaw/workspace/skills/apple-find-my/vendor/findmy-key-extractor/keys/FMFDataManager.bplist`

If the keys are missing, run the local key extraction flow from Martin's private
OpenClaw skill. This public repo intentionally does not contain those files.
