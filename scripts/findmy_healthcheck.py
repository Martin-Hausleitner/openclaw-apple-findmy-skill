#!/usr/bin/env python3
"""Redacted healthcheck for Martin's local Apple Find My stack."""

from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import urllib.error
import urllib.request
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
REPO = Path("/Users/mh/Documents/Playground/openclaw-apple-findmy-skill")
OPENCLAW_SKILL = Path("/Users/mh/.openclaw/workspace/skills/apple-find-my")
HERMES_SKILL = Path("/Users/mh/.hermes/skills/apple/findmy")
DASHBOARDS = {
    "findmysync_receiver": "http://127.0.0.1:8765/findmysync",
    "owntracks": "http://127.0.0.1:18084",
    "traccar": "http://127.0.0.1:18082",
    "geopulse": "http://127.0.0.1:18085",
}
BRIDGE_LOGS = {
    "traccar": STATE / "traccar/bridge-log.jsonl",
    "owntracks": STATE / "owntracks/bridge-log.jsonl",
    "geopulse": STATE / "geopulse/bridge-log.jsonl",
}
SYNC_SENTINEL = ONEDRIVE_BACKUP / "Status/sync-sentinel.json"


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


def directory_bytes(path: Path) -> int:
    if not path.exists():
        return 0
    total = 0
    for child in path.rglob("*"):
        if child.is_file():
            try:
                total += child.stat().st_size
            except OSError:
                pass
    return total


def top_level_storage(path: Path) -> dict[str, int]:
    if not path.exists():
        return {}
    out: dict[str, int] = {}
    for child in path.iterdir():
        if child.is_file():
            out[child.name] = child.stat().st_size
        elif child.is_dir():
            out[child.name] = directory_bytes(child)
    return dict(sorted(out.items(), key=lambda item: item[1], reverse=True))


def process_running(pattern: str) -> bool:
    try:
        result = subprocess.run(
            ["ps", "ax", "-o", "command="],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
        return pattern.lower() in result.stdout.lower()
    except Exception:
        return False


def onedrive_sync_info() -> dict[str, Any]:
    folder = ONEDRIVE_BACKUP
    sentinel = file_info(SYNC_SENTINEL)
    writable = False
    error = None
    probe = folder / "Status/.write-probe.tmp"
    try:
        probe.parent.mkdir(parents=True, exist_ok=True)
        probe.write_text("ok\n", encoding="utf-8")
        writable = probe.read_text(encoding="utf-8") == "ok\n"
        probe.unlink(missing_ok=True)
    except Exception as exc:  # noqa: BLE001 - healthcheck should report, not fail
        error = type(exc).__name__
    return {
        "folder": str(folder),
        "in_cloudstorage": "/Library/CloudStorage/OneDrive-Personal/" in str(folder),
        "file_provider_running": process_running("OneDrive File Provider"),
        "writable": writable,
        "write_probe_error": error,
        "sync_sentinel": sentinel,
    }


def http_check(url: str) -> dict[str, Any]:
    for method in ("HEAD", "GET"):
        request = urllib.request.Request(url, method=method)
        try:
            with urllib.request.urlopen(request, timeout=4) as response:
                return {"ok": 200 <= response.status < 400, "status": response.status, "method": method}
        except urllib.error.HTTPError as exc:
            if method == "HEAD" and exc.code in {405, 501}:
                continue
            return {"ok": exc.code < 500, "status": exc.code, "method": method}
        except Exception as exc:  # noqa: BLE001 - healthcheck should report, not fail
            return {"ok": False, "error": type(exc).__name__, "method": method}
    return {"ok": False, "error": "unreachable"}


def latest_jsonl_row(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"exists": False}
    latest: dict[str, Any] | None = None
    with path.open(errors="replace") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                latest = json.loads(line)
            except json.JSONDecodeError:
                continue
    if not latest:
        return {"exists": True, "has_rows": False}
    ts = parse_time(latest.get("ts") or latest.get("time") or latest.get("received_at"))
    errors = latest.get("errors") or []
    return {
        "exists": True,
        "has_rows": True,
        "latest_ts": ts.isoformat() if ts else None,
        "latest_age_minutes": round((now() - ts).total_seconds() / 60, 1) if ts else None,
        "latest_errors": len(errors) if isinstance(errors, list) else None,
        "points_seen": latest.get("points_seen"),
        "points_sent": latest.get("points_sent") or latest.get("positions_sent"),
    }


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
        "local_folder_bytes": directory_bytes(ONEDRIVE_BACKUP),
        "encrypted_archives": len(archives),
        "manifests": len(manifests),
        "latest_archive": file_info(latest_archive) if latest_archive else {"exists": False},
        "latest_summary": file_info(ONEDRIVE_BACKUP / "Latest/latest-summary.json"),
        "status_healthcheck": file_info(ONEDRIVE_BACKUP / "Status/healthcheck.json"),
        "assistant_brief": file_info(ONEDRIVE_BACKUP / "Status/assistant-brief.md"),
    }


def skill_install_info() -> dict[str, Any]:
    def one(path: Path) -> dict[str, Any]:
        return {
            "path": str(path),
            "skill_md": file_info(path / "SKILL.md"),
            "healthcheck": file_info(path / "scripts/findmy_healthcheck.py"),
            "backup": file_info(path / "scripts/backup_findmy_to_onedrive.py"),
        }

    return {"openclaw": one(OPENCLAW_SKILL), "hermes": one(HERMES_SKILL)}


def repo_info() -> dict[str, Any]:
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=REPO,
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        ).stdout.strip()
    except Exception:
        commit = None
    return {"path": str(REPO), "commit": commit}


def quality(payload: dict[str, Any]) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def add(name: str, ok: bool, detail: str, severity: str = "warn") -> None:
        checks.append({"name": name, "ok": ok, "severity": severity, "detail": detail})

    export_age = payload["export"]["latest_summary"].get("age_minutes")
    add(
        "export_fresh",
        isinstance(export_age, (int, float)) and export_age <= 20,
        f"export age {export_age} min",
        "critical",
    )
    people_age = payload["people_source"].get("newest_age_hours")
    add(
        "people_recent",
        isinstance(people_age, (int, float)) and people_age <= 6,
        f"newest people point age {people_age} h",
    )
    findmysync_age = payload["findmysync_source"].get("newest_age_minutes")
    add(
        "findmysync_recent",
        isinstance(findmysync_age, (int, float)) and findmysync_age <= 70,
        f"newest FindMySync event age {findmysync_age} min",
    )
    backup_age = payload["onedrive_backup"]["latest_archive"].get("age_minutes")
    add(
        "onedrive_backup_recent",
        isinstance(backup_age, (int, float)) and backup_age <= 75,
        f"latest encrypted backup age {backup_age} min",
        "critical",
    )
    add(
        "one_drive_status_file",
        payload["onedrive_backup"]["status_healthcheck"].get("exists") is True,
        "agent-readable Status/healthcheck.json exists",
    )
    sync = payload["onedrive_sync"]
    add(
        "one_drive_file_provider",
        sync.get("file_provider_running") is True,
        f"OneDrive file provider running: {sync.get('file_provider_running')}",
        "critical",
    )
    add(
        "one_drive_writable",
        sync.get("writable") is True,
        f"OneDrive write probe: {sync.get('writable')}",
        "critical",
    )
    sentinel_age = sync.get("sync_sentinel", {}).get("age_minutes")
    add(
        "one_drive_sentinel_recent",
        isinstance(sentinel_age, (int, float)) and sentinel_age <= 75,
        f"sync sentinel age {sentinel_age} min",
    )
    for name, status in payload["dashboards"].items():
        add(f"dashboard_{name}", status.get("ok") is True, f"{name}: {status}")
    for name, status in payload["bridges"].items():
        add(
            f"bridge_{name}",
            status.get("latest_errors") == 0 and status.get("latest_age_minutes", 9999) <= 30,
            f"{name}: age {status.get('latest_age_minutes')} min, errors {status.get('latest_errors')}",
            "critical",
        )

    failed = [check for check in checks if not check["ok"]]
    critical_failed = [check for check in failed if check["severity"] == "critical"]
    if critical_failed:
        status = "critical"
    elif failed:
        status = "degraded"
    else:
        status = "ok"
    return {
        "status": status,
        "score": round(100 * (len(checks) - len(failed)) / len(checks), 1) if checks else 0,
        "checks": checks,
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
        "onedrive_sync": onedrive_sync_info(),
        "dashboards": {name: http_check(url) for name, url in DASHBOARDS.items()},
        "bridges": {name: latest_jsonl_row(path) for name, path in BRIDGE_LOGS.items()},
        "storage": {
            "local_state_bytes": directory_bytes(STATE),
            "onedrive_backup_bytes": directory_bytes(ONEDRIVE_BACKUP),
            "local_state_breakdown": top_level_storage(STATE),
            "onedrive_breakdown": top_level_storage(ONEDRIVE_BACKUP),
        },
        "agent_install": skill_install_info(),
        "repo": repo_info(),
    }
    payload["quality"] = quality(payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
