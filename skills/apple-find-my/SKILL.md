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

## Commands

Run a one-shot export:

```bash
/Users/mh/.openclaw/workspace/.venvs/findmy-key-extractor/bin/python /Users/mh/Documents/Playground/openclaw-apple-findmy-skill/scripts/openclaw_findmy_export.py --print-summary
```

Install/update the every-5-minutes LaunchAgent:

```bash
/Users/mh/Documents/Playground/openclaw-apple-findmy-skill/scripts/install_launchagent.sh
```

Read the latest redacted status:

```bash
cat /Users/mh/.openclaw/workspace/state/apple-find-my/export/latest-summary.json
```

## What It Covers

- Items and AirTags from `Items.data`
- Devices from `Devices.data`
- Family members from `FamilyMembers.data`
- Friend cache metadata from `FriendCacheData.data`
- FollowMyFriends local database table counts

## Required Local Files

Keys are expected at:

- `/Users/mh/.openclaw/workspace/skills/apple-find-my/vendor/findmy-key-extractor/keys/LocalStorage.key`
- `/Users/mh/.openclaw/workspace/skills/apple-find-my/vendor/findmy-key-extractor/keys/FMIPDataManager.bplist`
- `/Users/mh/.openclaw/workspace/skills/apple-find-my/vendor/findmy-key-extractor/keys/FMFDataManager.bplist`

If the keys are missing, run the local key extraction flow from Martin's private
OpenClaw skill. This public repo intentionally does not contain those files.
