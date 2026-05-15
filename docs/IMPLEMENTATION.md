# Implementation Notes

## What Works

The working local stack has four layers:

1. `findmy-key-extractor` extracts local Find My keys once on Martin's Mac.
2. `openclaw_findmy_export.py` uses those keys to decrypt local Find My caches.
3. LaunchAgent `ai.openclaw.findmy.export` refreshes the redacted summary every 5 minutes.
4. Optional LaunchAgent `ai.openclaw.findmysync.receiver` receives local
   FindMySync-style POSTs for dashboards and integration tests.

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
- macOS Contacts: display/full-name enrichment for FollowMyFriends handles

## FindMySync.app Status

The upstream FindMySync.app started and accepted a local endpoint, but it sent
zero events. Its status screen reported that it could not get `BeaconStore` key
data. On this Mac, the local cache files are encrypted, so direct JSON parsing
of `Items.data` and `Devices.data` fails.

The working replacement is direct local decryption with the extracted
`FMIPDataManager.bplist` and `FMFDataManager.bplist` keys.

A local patched FindMySync build now works by reading:

```text
/Users/mh/.openclaw/workspace/state/apple-find-my/export/private-exact.json
```

and posting FindMySync-compatible events to:

```text
http://127.0.0.1:8765/findmysync
```

Test result on 2026-05-15:

- 72 local POST events captured after repeated manual updates
- 18 unique FindMySync IDs
- all captured events contained a GPS field
- exact payloads remained only in the private local state directory

The reproducible Swift patch is stored at:

```text
patches/FindMySync-openclaw-export.patch
```

## Contacts Enrichment

The exporter reads local Contacts databases from:

```text
~/Library/Application Support/AddressBook/AddressBook-v22.abcddb
~/Library/Application Support/AddressBook/Sources/*/AddressBook-v22.abcddb
```

It indexes email addresses and normalized phone numbers, then enriches
FollowMyFriends handles with:

- `display_name`
- `full_name`
- `given_name`
- `family_name`
- `match_type`

Handles without a matching local contact are preserved as the original
phone/email handle.

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

FindMySync receiver install:

```bash
scripts/install_findmysync_receiver_launchagent.sh
```

Inspect:

```bash
launchctl print gui/$(id -u)/ai.openclaw.findmysync.receiver
```

Receiver UI:

```text
http://127.0.0.1:8765/findmysync
```

## Security Reset

After key extraction, re-enable macOS protections from Recovery:

```bash
nvram -d boot-args
csrutil enable
```

Then reboot. The local keys remain available for future exports.
