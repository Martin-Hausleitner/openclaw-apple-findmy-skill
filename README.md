# OpenClaw Apple Find My Skill

Local Apple Find My data pipeline for Martin's OpenClaw and Hermes agents.

This repository contains reusable code, launch installers, and a Codex/OpenClaw
skill. It intentionally does **not** contain keys, Apple account credentials,
decrypted databases, exact coordinates, private dashboard state, or location
history.

## What This Solves

Apple's Find My data is split across different local sources. The reliable
setup here keeps those sources separate, then normalizes them for agents and
local web dashboards.

| Source | Best For | Current Local Coverage |
|---|---|---:|
| FollowMyFriends | Find My People/Friends | 15 people, 14 with location |
| FindMySync-style sender | Find My Devices/Items | 9 devices + 11 items with location |
| OpenClaw normalizer | Unified agent/dashboard export | 34 tracks total |

Dashboard output is currently verified as:

| Dashboard | URL | Verified Count |
|---|---|---:|
| OwnTracks | `http://127.0.0.1:18084` | 34 tracks |
| Traccar | `http://127.0.0.1:18082` | 31 merged devices / positions |
| GeoPulse | `http://127.0.0.1:18085` | 34 GPS rows |

## Architecture

```text
Apple Find My local caches
        |
        | one-time local key extraction
        v
openclaw_findmy_export.py
        |
        +--> redacted summary for agents
        +--> private exact JSON, mode 0600
                 |
                 +--> owntracks_findmy_bridge.py -> OwnTracks
                 +--> traccar_findmy_bridge.py   -> Traccar
                 +--> geopulse_findmy_bridge.py  -> GeoPulse
                 +--> patched FindMySync sender  -> local receiver
```

The current design uses existing tools where they are strongest:

- **FollowMyFriends** remains the best existing path for people/friends.
- **FindMySync** remains useful as a Devices/Items sender shape.
- **OpenClaw code** is the normalizer and dashboard adapter, not a public cloud.
- The current Python exporter decrypts the fresh local FollowMyFriends database
  itself. Do not run the old FollowMyFriends app poller in parallel unless you
  intentionally want it to open Apple Find My.

## Repository Layout

```text
scripts/
  openclaw_findmy_export.py       # local decrypt + normalized export
  owntracks_findmy_bridge.py      # publish 34 tracks to OwnTracks
  traccar_findmy_bridge.py        # publish merged tracks to Traccar
  geopulse_findmy_bridge.py       # publish 34 points to GeoPulse
  *_bootstrap_local.py            # create local dashboard users/sources
  install_*.sh                    # LaunchAgent / local stack installers

skills/apple-find-my/SKILL.md     # reusable agent skill
docs/SETUP.md                     # install and operations guide
docs/IMPLEMENTATION.md            # implementation notes
docker/owntracks/docker-compose.yml
patches/FindMySync-openclaw-export.patch
```

## Private State

All private runtime files live outside the repo:

```text
/Users/mh/.openclaw/workspace/state/apple-find-my
```

Important files:

```text
export/latest-summary.json        # safe default for agent answers
export/private-exact.json         # exact private data, mode 0600
owntracks/                        # OwnTracks state and logs
traccar/                          # Traccar database, logs, local login
geopulse/                         # GeoPulse database, keys, local login
findmysync/events.jsonl           # raw local receiver payloads
backup/                           # local backup passphrase and backup logs
```

Never commit the private state directory. `.gitignore` is configured to block
keys, local databases, exact JSON, cache data, and logs.

## Install

Full details are in [docs/SETUP.md](docs/SETUP.md).

Short version:

```bash
cd /Users/mh/Documents/Playground/openclaw-apple-findmy-skill

# Core 10-minute export
scripts/install_launchagent.sh

# Optional existing-tool receiver/sender path
scripts/install_findmysync_receiver_launchagent.sh
scripts/make_findmysync_dockless.sh
scripts/install_findmysync_app_launchagent.sh

# Keep old visible app pollers out of the loop
scripts/disable_visible_findmy_pollers.sh

# Optional dashboards and 10-minute bridges
scripts/install_owntracks_stack.sh
scripts/install_traccar_stack.sh
scripts/install_geopulse_stack.sh

# Hourly OneDrive backup + local JSONL/log retention
scripts/install_onedrive_backup_launchagent.sh
```

All recurring jobs are installed as macOS LaunchAgents and currently run every 10 minutes
where polling is involved.

## Current Autostart Jobs

| LaunchAgent | Purpose | Interval |
|---|---|---:|
| `ai.openclaw.findmy.export` | refresh local normalized export | 10 min |
| `ai.openclaw.findmy.owntracks-bridge` | send export to OwnTracks | 10 min |
| `ai.openclaw.findmy.traccar-bridge` | send merged export to Traccar | 10 min |
| `ai.openclaw.findmy.geopulse-bridge` | send export to GeoPulse | 10 min |
| `ai.openclaw.findmy.onedrive-backup` | encrypted private backup to OneDrive | 60 min |
| `ai.openclaw.findmysync.receiver` | receive local FindMySync-style posts | always on |
| `ai.openclaw.findmysync.app` | start FindMySync app at login | login |

Inspect with:

```bash
launchctl print gui/$(id -u)/ai.openclaw.findmy.export
launchctl print gui/$(id -u)/ai.openclaw.findmy.owntracks-bridge
launchctl print gui/$(id -u)/ai.openclaw.findmy.traccar-bridge
launchctl print gui/$(id -u)/ai.openclaw.findmy.geopulse-bridge
launchctl print gui/$(id -u)/ai.openclaw.findmy.onedrive-backup
```

## Verify

Run the exporter:

```bash
/Users/mh/.openclaw/workspace/.venvs/findmy-key-extractor/bin/python \
  scripts/openclaw_findmy_export.py --print-summary
```

Check the dashboard bridges:

```bash
/Users/mh/.openclaw/workspace/.venvs/findmy-key-extractor/bin/python \
  scripts/owntracks_findmy_bridge.py --print-summary
/Users/mh/.openclaw/workspace/.venvs/findmy-key-extractor/bin/python \
  scripts/traccar_findmy_bridge.py --print-summary
/Users/mh/.openclaw/workspace/.venvs/findmy-key-extractor/bin/python \
  scripts/geopulse_findmy_bridge.py --print-summary
```

Check the full stack without printing coordinates or secrets:

```bash
scripts/findmy_healthcheck.py
```

Run a manual OneDrive backup:

```bash
scripts/backup_findmy_to_onedrive.py
```

Verify the newest encrypted archive without extracting private data:

```bash
scripts/verify_onedrive_backup.py
```

Expected current bridge count:

```text
OwnTracks/GeoPulse: 34 tracks = 14 people + 9 devices + 11 items
Traccar: 31 merged tracks after duplicate Find My IDs are collapsed
```

## Dashboard Notes

- **OwnTracks** is the lightest local map and keeps separate tracks.
- **Traccar** is the strongest multi-device dashboard and merges duplicate
  Find My IDs into one device/position track.
- **GeoPulse** is a nicer timeline/GPS-data UI, but it is less ideal for
  multi-device identity because it stores a user timeline.

Dashboard credentials are generated/stored only in private local state files:

```text
/Users/mh/.openclaw/workspace/state/apple-find-my/traccar/login.env
/Users/mh/.openclaw/workspace/state/apple-find-my/geopulse/login.env
```

OneDrive backups are written here:

```text
/Users/mh/Library/CloudStorage/OneDrive-Personal/Anlagen/Backup/OpenClaw-FindMy
```

`Latest/` contains redacted summaries for agents. `Archive/Encrypted/`
contains encrypted private snapshots. The backup passphrase stays local under
`/Users/mh/.openclaw/workspace/state/apple-find-my/backup` and is not committed.
`Status/healthcheck.json` and `Status/quality-report.md` give normal assistants
a redacted end-to-end status, freshness score, dashboard status, and backup
verification result.

## Safety Model

- No Apple ID password or 2FA code is stored in this repo.
- No exact location data is committed.
- Agents should read `latest-summary.json` by default.
- Agents can run `scripts/findmy_healthcheck.py` for a safe freshness report.
- Exact data is only for local dashboard bridges and explicit private checks.
- Location output in chat should be summarized unless Martin explicitly asks
  for exact private coordinates.

## Recommended Operating Mode

Keep the core exporter and dashboard bridges at 10-minute intervals. Keep FindMySync as a
fallback/control path if desired, but use the OpenClaw normalized export as the
main source for Hermes/OpenClaw and dashboards.
