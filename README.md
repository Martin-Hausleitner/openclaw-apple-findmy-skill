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
- 7 of 15 FollowMyFriends handles enriched from local Contacts in the first run
- 15 friend-cache entries
- 2 item groups
- 6 safe-location records

## How It Works

1. Apple Find My writes encrypted local caches.
2. Martin extracts local keys once on his own Mac.
3. `scripts/openclaw_findmy_export.py` decrypts the local caches on-device.
4. Local macOS Contacts are indexed for email/phone matching.
5. Exact data is written only to a private local state file with mode `0600`.
6. Agents read the redacted summary for normal answers.

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

## One-Shot Export

```bash
/Users/mh/.openclaw/workspace/.venvs/findmy-key-extractor/bin/python scripts/openclaw_findmy_export.py --print-summary
```

## Security Reset After Key Extraction

After extracting keys, re-enable macOS protections from Recovery:

```bash
nvram -d boot-args
csrutil enable
```

Then reboot. The extracted local keys remain usable for the exporter.
