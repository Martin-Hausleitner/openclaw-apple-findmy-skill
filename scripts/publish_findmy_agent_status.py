#!/usr/bin/env python3
"""Publish a fast redacted Find My status for normal assistants."""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any


REPO = Path("/Users/mh/Documents/Playground/openclaw-apple-findmy-skill")
HEALTHCHECK = REPO / "scripts/findmy_healthcheck.py"
ONEDRIVE = (
    Path.home() / "Library/CloudStorage/OneDrive-Personal/Anlagen/Backup/OpenClaw-FindMy"
)
STATUS_DIR = ONEDRIVE / "Status"


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


def ensure_onedrive_hint() -> dict[str, Any]:
    before = process_running("onedrive")
    attempted = False
    if not before and Path("/Applications/OneDrive.app").exists():
        attempted = True
        subprocess.run(["/usr/bin/open", "-gj", "-a", "OneDrive"], check=False)
        time.sleep(3)
    return {
        "running_before": before,
        "launch_attempted": attempted,
        "running_after": process_running("onedrive"),
    }


def run_healthcheck() -> dict[str, Any]:
    result = subprocess.run(
        [str(HEALTHCHECK)],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    if result.returncode != 0:
        return {
            "quality": {"status": "critical", "score": 0},
            "error": "healthcheck_failed",
        }
    return json.loads(result.stdout)


def write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def write_json_atomic(path: Path, data: Any) -> None:
    write_text_atomic(path, json.dumps(data, ensure_ascii=False, indent=2))


def render_current_markdown(health: dict[str, Any], onedrive_hint: dict[str, Any]) -> str:
    quality = health.get("quality") or {}
    export = health.get("export") or {}
    backup = health.get("onedrive_backup") or {}
    sync = health.get("onedrive_sync") or {}
    storage = health.get("storage") or {}
    lines = [
        "# Current Find My Status",
        "",
        "Redacted for normal assistants. No coordinates, keys, raw rows, or credentials.",
        "",
        f"- Status: {quality.get('status')} ({quality.get('score')}%)",
        f"- Checked: {health.get('checked_at')}",
        f"- Export generated: {export.get('generated_at')}",
        f"- Export age minutes: {(export.get('latest_summary') or {}).get('age_minutes')}",
        f"- Counts: {json.dumps(export.get('counts'), ensure_ascii=False)}",
        f"- OneDrive writable: {sync.get('writable')}",
        f"- OneDrive running after hint: {onedrive_hint.get('running_after')}",
        f"- Latest backup age minutes: {(backup.get('latest_archive') or {}).get('age_minutes')}",
        f"- Local state MB: {round((storage.get('local_state_bytes') or 0) / 1024 / 1024, 1)}",
        f"- OneDrive backup MB: {round((storage.get('onedrive_backup_bytes') or 0) / 1024 / 1024, 1)}",
        "",
        "Use the JSON files in this folder for automation. Use dashboards for visual map/history.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    STATUS_DIR.mkdir(parents=True, exist_ok=True)
    onedrive_hint = ensure_onedrive_hint()
    health = run_healthcheck()
    payload = {
        "published_at": health.get("checked_at"),
        "privacy": "Redacted normal-assistant status.",
        "onedrive_launch_hint": onedrive_hint,
        "health": health,
    }
    write_json_atomic(STATUS_DIR / "current-status.json", payload)
    write_text_atomic(STATUS_DIR / "current-status.md", render_current_markdown(health, onedrive_hint))
    write_text_atomic(
        STATUS_DIR / "current-status.txt",
        f"Find My status: {(health.get('quality') or {}).get('status')} "
        f"({(health.get('quality') or {}).get('score')}%). "
        f"OneDrive writable: {(health.get('onedrive_sync') or {}).get('writable')}. "
        f"Backup age min: {((health.get('onedrive_backup') or {}).get('latest_archive') or {}).get('age_minutes')}.\n",
    )
    print(
        json.dumps(
            {
                "status": (health.get("quality") or {}).get("status"),
                "score": (health.get("quality") or {}).get("score"),
                "onedrive_running": onedrive_hint.get("running_after"),
                "wrote": str(STATUS_DIR / "current-status.json"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
