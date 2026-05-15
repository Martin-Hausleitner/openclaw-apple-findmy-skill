# Implementation Notes

## What Works

The working local stack has four layers:

1. `findmy-key-extractor` extracts local Find My keys once on Martin's Mac.
2. `openclaw_findmy_export.py` uses those keys to decrypt local Find My caches.
3. LaunchAgent `ai.openclaw.findmy.export` refreshes the redacted summary every 60 minutes.
4. Optional LaunchAgents `ai.openclaw.findmysync.receiver` and
   `ai.openclaw.findmysync.app` receive local FindMySync-style POSTs and start
   the sender app at login.
5. Optional LaunchAgents `ai.openclaw.findmy.owntracks-stack` and
   `ai.openclaw.findmy.owntracks-bridge` start the local OwnTracks web map and
   publish people/devices/items from the private exact export every 60 minutes.
6. Optional comparison stacks run Traccar and GeoPulse as local-only web UIs.

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
- macOS Contacts: display/full-name, email, phone, and photo-presence enrichment
  for FollowMyFriends handles

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

## OwnTracks Web Viewer

The local OwnTracks viewer is available at:

```text
http://127.0.0.1:18084
```

The recorder API is bound to localhost:

```text
http://127.0.0.1:18083
```

Docker containers:

- `openclaw-owntracks-mqtt`
- `openclaw-owntracks-recorder`
- `openclaw-owntracks-frontend`

The bridge writes OwnTracks-compatible local traces for:

- `people`
- `devices`
- `items`

The trace store lives under:

```text
/Users/mh/.openclaw/workspace/state/apple-find-my/owntracks
```

Do not publish this store. It contains exact private location history.

## Comparison Web UIs

Local-only comparison UIs:

- OwnTracks: `http://127.0.0.1:18084`
- Traccar: `http://127.0.0.1:18082`
- GeoPulse: `http://127.0.0.1:18085`

Autostart LaunchAgents:

- `ai.openclaw.findmy.traccar-stack`
- `ai.openclaw.findmy.geopulse-stack`

OwnTracks is currently the only one fed by `owntracks_findmy_bridge.py`.
Traccar and GeoPulse are installed for UI comparison and can be connected later
if selected as the final dashboard.

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
scripts/install_findmysync_app_launchagent.sh
```

Inspect:

```bash
launchctl print gui/$(id -u)/ai.openclaw.findmysync.receiver
launchctl print gui/$(id -u)/ai.openclaw.findmysync.app
```

Receiver UI:

```text
http://127.0.0.1:8765/findmysync
```

OwnTracks viewer install:

```bash
scripts/install_owntracks_stack.sh
```

Inspect:

```bash
launchctl print gui/$(id -u)/ai.openclaw.findmy.owntracks-stack
launchctl print gui/$(id -u)/ai.openclaw.findmy.owntracks-bridge
```

## Security Reset

After key extraction, re-enable macOS protections from Recovery:

```bash
nvram -d boot-args
csrutil enable
```

Then reboot. The local keys remain available for future exports.
