#!/usr/bin/env python3
"""Redacted healthcheck for Martin's local Apple Find My stack."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any


STATE = Path("/Users/mh/.openclaw/workspace/state/apple-find-my")
EXPORT = STATE / "export/latest-summary.json"
PRIVATE_EXPORT = STATE / "export/private-exact.json"
FINDMYSYNC_EVENTS = STATE / "findmysync/events.jsonl"
ONEDRIVE_BACKUP = (
    Path.home() / "Library/CloudStorage/OneDrive-Personal/Anlagen/Backup/OpenClaw-FindMy"
)
FMF_DB = (
    Path.home()
    / "Library/Group Containers/group.com.apple.findmy.findmylocateagent/Library/Application Support/LocalStorage.db"
)


def now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def parse_time(value: Any) -> dt.datetime | None:
    if isinstance(value, (int, float)):
        seconds = value / 1000 if value > 100_000_000_000 else value
        return dt.datetime.fromtimestamp(seconds, dt.timezone.utc)
    if isinstance(value, str) and value:
        try:
            return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(
                dt.timezone.utc
            )
        except ValueError:
            return None
    return None


def file_info(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"exists": False}
    stat = path.stat()
    mtime = dt.datetime.fromtimestamp(stat.st_mtime, dt.timezone.utc)
    return {
        "exists": True,
        "mtime": mtime.isoformat(),
        "age_minutes": round((now() - mtime).total_seconds() / 60, 1),
        "bytes": stat.st_size,
    }


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def latest_findmysync_events() -> dict[str, Any]:
    if not FINDMYSYNC_EVENTS.exists():
        return {"exists": False}
    newest: dt.datetime | None = None
    unique_ids: set[str] = set()
    events = 0
    events_by_day: dict[str, int] = {}
    cutoff = now() - dt.timedelta(days=3)
    with FINDMYSYNC_EVENTS.open(errors="replace") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts = parse_time(row.get("received_at"))
            if not ts:
                continue
            if newest is None or ts > newest:
                newest = ts
            if ts >= cutoff:
                events += 1
                events_by_day[ts.date().isoformat()] = events_by_day.get(ts.date().isoformat(), 0) + 1
                dev_id = (row.get("payload") or {}).get("dev_id")
                if dev_id:
                    unique_ids.add(str(dev_id))
    return {
        "exists": True,
        "newest_event": newest.isoformat() if newest else None,
        "newest_age_minutes": round((now() - newest).total_seconds() / 60, 1)
        if newest
        else None,
        "events_last_3_days": events,
        "unique_ids_last_3_days": len(unique_ids),
        "events_by_day_last_3_days": events_by_day,
    }


def people_freshness(private_data: dict[str, Any]) -> dict[str, Any]:
    people = private_data.get("followmyfriends_people_enriched") or []
    timestamps: list[dt.datetime] = []
    for person in people:
        loc = person.get("location") if isinstance(person, dict) else None
        if not isinstance(loc, dict):
            continue
        ts = parse_time(loc.get("timeStamp") or loc.get("timestamp") or loc.get("location_timestamp"))
        if ts:
            timestamps.append(ts)
    newest = max(timestamps) if timestamps else None
    return {
        "people_total": len(people),
        "people_with_location_timestamp": len(timestamps),
        "newest_location": newest.isoformat() if newest else None,
        "newest_age_hours": round((now() - newest).total_seconds() / 3600, 1)
        if newest
        else None,
    }


def backup_info() -> dict[str, Any]:
    archives = sorted((ONEDRIVE_BACKUP / "Archive/Encrypted").glob("*.enc"))
    manifests = sorted((ONEDRIVE_BACKUP / "Manifests").glob("*.json"))
    latest_archive = archives[-1] if archives else None
    return {
        "folder": str(ONEDRIVE_BACKUP),
        "exists": ONEDRIVE_BACKUP.exists(),
        "encrypted_archives": len(archives),
        "manifests": len(manifests),
        "latest_archive": file_info(latest_archive) if latest_archive else {"exists": False},
        "latest_summary": file_info(ONEDRIVE_BACKUP / "Latest/latest-summary.json"),
    }


def main() -> int:
    summary = load_json(EXPORT)
    private_data = load_json(PRIVATE_EXPORT)
    payload = {
        "checked_at": now().isoformat(),
        "privacy": "Redacted healthcheck. No coordinates, keys, raw rows, or dashboard credentials.",
        "export": {
            "latest_summary": file_info(EXPORT),
            "private_exact": file_info(PRIVATE_EXPORT),
            "generated_at": summary.get("generated_at"),
            "counts": summary.get("counts"),
            "legacy_cache_status": summary.get("legacy_cache_status"),
        },
        "people_source": {
            "localstorage_db": file_info(FMF_DB),
            **people_freshness(private_data),
        },
        "findmysync_source": latest_findmysync_events(),
        "onedrive_backup": backup_info(),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
