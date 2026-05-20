#!/usr/bin/env python3
"""Back up local Find My state to OneDrive with private archives encrypted."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import secrets
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request
from pathlib import Path
from typing import Any


STATE = Path("/Users/mh/.openclaw/workspace/state/apple-find-my")
EXPORT = STATE / "export"
FINDMYSYNC = STATE / "findmysync"
FOLLOWMYFRIENDS = STATE / "followmyfriends"
TRACCAR = STATE / "traccar"
OWNTRACKS = STATE / "owntracks"
GEOPULSE = STATE / "geopulse"
BACKUP_STATE = STATE / "backup"
PASSPHRASE_FILE = BACKUP_STATE / "onedrive-backup-passphrase.txt"
ONEDRIVE = (
    Path.home() / "Library/CloudStorage/OneDrive-Personal/Anlagen/Backup/OpenClaw-FindMy"
)
ARCHIVE_DIR = ONEDRIVE / "Archive/Encrypted"
MANIFEST_DIR = ONEDRIVE / "Manifests"
LATEST_DIR = ONEDRIVE / "Latest"
DOCS_DIR = ONEDRIVE / "Docs"
STATUS_DIR = ONEDRIVE / "Status"
HEALTHCHECK = Path("/Users/mh/Documents/Playground/openclaw-apple-findmy-skill/scripts/findmy_healthcheck.py")


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def ensure_passphrase() -> Path:
    BACKUP_STATE.mkdir(parents=True, exist_ok=True)
    BACKUP_STATE.chmod(0o700)
    if not PASSPHRASE_FILE.exists():
        PASSPHRASE_FILE.write_text(secrets.token_urlsafe(48), encoding="utf-8")
        PASSPHRASE_FILE.chmod(0o600)
    return PASSPHRASE_FILE


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def copy_if_exists(src: Path, dst: Path) -> dict[str, Any] | None:
    if not src.exists():
        return None
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_name(f".{dst.name}.{os.getpid()}.tmp")
    try:
        shutil.copy2(src, tmp)
        tmp.replace(dst)
    except OSError:
        tmp.unlink(missing_ok=True)
        if dst.exists():
            dst.unlink()
        shutil.copy2(src, dst)
    return {"source": str(src), "backup": str(dst), "bytes": dst.stat().st_size}


def add_if_exists(tar: tarfile.TarFile, src: Path, arcname: str, manifest: list[dict[str, Any]]) -> None:
    if not src.exists():
        return
    tar.add(src, arcname=arcname)
    manifest.append({"path": str(src), "archive_name": arcname, "bytes": src.stat().st_size})


def encrypt_file(src: Path, dst: Path, passphrase_file: Path) -> None:
    subprocess.run(
        [
            "/usr/bin/openssl",
            "enc",
            "-aes-256-cbc",
            "-pbkdf2",
            "-salt",
            "-in",
            str(src),
            "-out",
            str(dst),
            "-pass",
            f"file:{passphrase_file}",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    dst.chmod(0o600)


def verify_encrypted_archive(src: Path, passphrase_file: Path) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="findmy-verify-") as tmp_dir:
        tar_path = Path(tmp_dir) / "restore-check.tar.gz"
        result = subprocess.run(
            [
                "/usr/bin/openssl",
                "enc",
                "-d",
                "-aes-256-cbc",
                "-pbkdf2",
                "-in",
                str(src),
                "-out",
                str(tar_path),
                "-pass",
                f"file:{passphrase_file}",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            return {"ok": False, "error": "decrypt_failed"}
        try:
            with tarfile.open(tar_path, "r:gz") as tar:
                names = tar.getnames()
        except tarfile.TarError:
            return {"ok": False, "error": "tar_list_failed"}
    required = {
        "export/private-exact.json",
        "export/latest-summary.json",
        "findmysync/events.jsonl",
    }
    return {
        "ok": required.issubset(set(names)),
        "file_count": len(names),
        "contains_required": sorted(required.intersection(names)),
    }


def write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def write_json_atomic(path: Path, data: Any) -> None:
    write_text_atomic(path, json.dumps(data, ensure_ascii=False, indent=2))


def run_healthcheck() -> dict[str, Any]:
    if not HEALTHCHECK.exists():
        return {"error": "healthcheck_missing"}
    result = subprocess.run(
        [str(HEALTHCHECK)],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    if result.returncode != 0:
        return {"error": "healthcheck_failed"}
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"error": "healthcheck_invalid_json"}


def render_quality_report(health: dict[str, Any], manifest: dict[str, Any]) -> str:
    quality = health.get("quality") or {}
    backup = health.get("onedrive_backup") or {}
    storage = health.get("storage") or {}
    checks = quality.get("checks") or []
    lines = [
        "# OpenClaw Find My Backup Status",
        "",
        f"- Checked: {health.get('checked_at')}",
        f"- Quality: {quality.get('status')} ({quality.get('score')}%)",
        f"- Latest encrypted archive: {manifest.get('archive', {}).get('path')}",
        f"- Archive verify: {manifest.get('archive_verify', {}).get('ok')}",
        f"- OneDrive folder bytes: {backup.get('local_folder_bytes')}",
        f"- Local state bytes: {storage.get('local_state_bytes')}",
        "",
        "## Checks",
        "",
    ]
    for check in checks:
        mark = "OK" if check.get("ok") else "WARN"
        lines.append(f"- {mark}: {check.get('name')} - {check.get('detail')}")
    lines.extend(
        [
            "",
            "This report is redacted. It intentionally contains no coordinates, keys, raw rows, or dashboard credentials.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_time(row: dict[str, Any]) -> dt.datetime | None:
    value = row.get("received_at") or row.get("ts") or row.get("time")
    if not isinstance(value, str):
        return None
    try:
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(dt.timezone.utc)
    except ValueError:
        return None


def trim_jsonl(path: Path, days: int, max_lines: int) -> dict[str, Any]:
    if not path.exists():
        return {"path": str(path), "exists": False}
    cutoff = utc_now() - dt.timedelta(days=days)
    kept: list[str] = []
    total = 0
    with path.open(errors="replace") as handle:
        for line in handle:
            if not line.strip():
                continue
            total += 1
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                kept.append(line)
                continue
            ts = parse_time(row)
            if ts is None or ts >= cutoff:
                kept.append(line)
    if len(kept) > max_lines:
        kept = kept[-max_lines:]
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text("".join(kept), encoding="utf-8")
    tmp.replace(path)
    return {"path": str(path), "exists": True, "total_lines": total, "kept_lines": len(kept)}


def trim_text_file(path: Path, max_bytes: int) -> dict[str, Any]:
    if not path.exists() or path.stat().st_size <= max_bytes:
        return {"path": str(path), "changed": False}
    data = path.read_bytes()[-max_bytes:]
    marker = b"\n[openclaw backup retention kept tail]\n"
    path.write_bytes(marker + data)
    return {"path": str(path), "changed": True, "bytes": path.stat().st_size}


def prune_old_backups(max_age_days: int, keep_minimum: int) -> list[str]:
    deleted: list[str] = []
    cutoff = utc_now().timestamp() - max_age_days * 86400
    for directory, pattern in ((ARCHIVE_DIR, "*.enc"), (MANIFEST_DIR, "*.json")):
        files = sorted(directory.glob(pattern), key=lambda p: p.stat().st_mtime)
        candidates = files[: max(0, len(files) - keep_minimum)]
        for path in candidates:
            if path.stat().st_mtime < cutoff:
                path.unlink()
                deleted.append(str(path))
    return deleted


def main() -> int:
    for directory in (ARCHIVE_DIR, MANIFEST_DIR, LATEST_DIR, DOCS_DIR, STATUS_DIR):
        directory.mkdir(parents=True, exist_ok=True)

    passphrase = ensure_passphrase()
    stamp = utc_now().strftime("%Y%m%dT%H%M%SZ")
    manifest: dict[str, Any] = {
        "created_at": utc_now().isoformat(),
        "privacy": "Private archive is encrypted. Latest/*.json is redacted for agent use.",
        "onedrive_folder": str(ONEDRIVE),
        "included_files": [],
    }

    latest_copies = []
    for name in ("latest-summary.json", "redacted-summary.json"):
        copied = copy_if_exists(EXPORT / name, LATEST_DIR / name)
        if copied:
            latest_copies.append(copied)
    manifest["latest_copies"] = latest_copies

    readme = DOCS_DIR / "README.md"
    readme.write_text(
        "# OpenClaw Find My Backup\n\n"
        "Latest contains redacted summaries for agents. Archive/Encrypted contains "
        "encrypted private snapshots. The decryption passphrase stays local on the Mac "
        "under the OpenClaw state folder and is not committed to GitHub.\n",
        encoding="utf-8",
    )

    with tempfile.TemporaryDirectory(prefix="findmy-backup-") as tmp_dir:
        tar_path = Path(tmp_dir) / f"findmy-private-{stamp}.tar.gz"
        with tarfile.open(tar_path, "w:gz") as tar:
            add_if_exists(tar, EXPORT / "private-exact.json", "export/private-exact.json", manifest["included_files"])
            add_if_exists(tar, EXPORT / "latest-summary.json", "export/latest-summary.json", manifest["included_files"])
            add_if_exists(tar, FOLLOWMYFRIENDS / "LocalStorage_decrypted.sqlite", "followmyfriends/LocalStorage_decrypted.sqlite", manifest["included_files"])
            add_if_exists(tar, FINDMYSYNC / "events.jsonl", "findmysync/events.jsonl", manifest["included_files"])
            add_if_exists(tar, TRACCAR / "bridge-log.jsonl", "traccar/bridge-log.jsonl", manifest["included_files"])
            add_if_exists(tar, OWNTRACKS / "bridge-log.jsonl", "owntracks/bridge-log.jsonl", manifest["included_files"])
            add_if_exists(tar, GEOPULSE / "bridge-log.jsonl", "geopulse/bridge-log.jsonl", manifest["included_files"])

        encrypted_path = ARCHIVE_DIR / f"findmy-private-{stamp}.tar.gz.enc"
        encrypt_file(tar_path, encrypted_path, passphrase)
        manifest["archive"] = {
            "path": str(encrypted_path),
            "bytes": encrypted_path.stat().st_size,
            "sha256": sha256(encrypted_path),
        }
        manifest["archive_verify"] = verify_encrypted_archive(encrypted_path, passphrase)

    manifest["local_retention"] = {
        "findmysync_events": trim_jsonl(FINDMYSYNC / "events.jsonl", days=14, max_lines=50_000),
        "traccar_bridge_log": trim_jsonl(TRACCAR / "bridge-log.jsonl", days=14, max_lines=20_000),
        "owntracks_bridge_log": trim_jsonl(OWNTRACKS / "bridge-log.jsonl", days=14, max_lines=20_000),
        "geopulse_bridge_log": trim_jsonl(GEOPULSE / "bridge-log.jsonl", days=14, max_lines=20_000),
        "export_stderr": trim_text_file(EXPORT / "launchagent.stderr.log", max_bytes=256_000),
        "traccar_stderr": trim_text_file(TRACCAR / "bridge-launch.stderr.log", max_bytes=256_000),
    }
    manifest["pruned"] = prune_old_backups(max_age_days=90, keep_minimum=24)

    manifest_path = MANIFEST_DIR / f"findmy-private-{stamp}.manifest.json"
    write_json_atomic(manifest_path, manifest)
    copy_if_exists(manifest_path, LATEST_DIR / "latest-manifest.json")
    health = run_healthcheck()
    write_json_atomic(STATUS_DIR / "healthcheck.json", health)
    write_text_atomic(STATUS_DIR / "quality-report.md", render_quality_report(health, manifest))
    print(
        json.dumps(
            {
                "created_at": manifest["created_at"],
                "archive": manifest["archive"]["path"],
                "archive_verify": manifest["archive_verify"].get("ok"),
                "health_status": (health.get("quality") or {}).get("status"),
                "latest_copies": len(latest_copies),
                "included_files": len(manifest["included_files"]),
                "pruned": len(manifest["pruned"]),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
