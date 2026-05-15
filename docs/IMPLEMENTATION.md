# Implementation Notes

## What Works

The working local stack has three layers:

1. `findmy-key-extractor` extracts local Find My keys once on Martin's Mac.
2. `openclaw_findmy_export.py` uses those keys to decrypt local Find My caches.
3. LaunchAgent `ai.openclaw.findmy.export` refreshes the redacted summary every 5 minutes.

Normal agents should read:

```text
/Users/mh/.openclaw/workspace/state/apple-find-my/export/latest-summary.json
```

Exact private data is written to:

```text
/Users/mh/.openclaw/workspace/state/apple-find-my/export/private-exact.json
```

That file is intentionally private mode `0600`.

## Current Coverage

- `Items.data`: AirTags, item trackers, AirPods parts, scooter-style items
- `Devices.data`: iPhone, iPad, Mac, Watch, AirPods, family devices
- `FamilyMembers.data`: family members
- `FriendCacheData.data`: friend metadata/cache
- FollowMyFriends local SQLite: people/friend table counts

## Why FindMySync.app Was Not Enough

FindMySync.app started and accepted a local endpoint, but it sent zero events.
Its status screen reported that it could not get `BeaconStore` key data. On this
Mac, the local cache files are encrypted, so direct JSON parsing of
`Items.data` and `Devices.data` fails.

The working replacement is direct local decryption with the extracted
`FMIPDataManager.bplist` and `FMFDataManager.bplist` keys.

## Autostart

Install or refresh:

```bash
scripts/install_launchagent.sh
```

Inspect:

```bash
launchctl print gui/$(id -u)/ai.openclaw.findmy.export
```

Logs:

```text
/Users/mh/.openclaw/workspace/state/apple-find-my/export/launchagent.stdout.log
/Users/mh/.openclaw/workspace/state/apple-find-my/export/launchagent.stderr.log
```

## Security Reset

After key extraction, re-enable macOS protections from Recovery:

```bash
nvram -d boot-args
csrutil enable
```

Then reboot. The local keys remain available for future exports.
