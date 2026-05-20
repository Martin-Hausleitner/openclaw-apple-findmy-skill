#!/usr/bin/env python3
"""Verify the latest encrypted OneDrive Find My backup without extracting it."""

from __future__ import annotations

import json
import subprocess
import tarfile
import tempfile
from pathlib import Path


STATE = Path("/Users/mh/.openclaw/workspace/state/apple-find-my/backup")
PASSPHRASE_FILE = STATE / "onedrive-backup-passphrase.txt"
ONEDRIVE = (
    Path.home() / "Library/CloudStorage/OneDrive-Personal/Anlagen/Backup/OpenClaw-FindMy"
)
ARCHIVE_DIR = ONEDRIVE / "Archive/Encrypted"


def main() -> int:
    archives = sorted(ARCHIVE_DIR.glob("*.enc"))
    if not archives:
        print(json.dumps({"ok": False, "error": "no_archives"}, indent=2))
        return 1
    if not PASSPHRASE_FILE.exists():
        print(json.dumps({"ok": False, "error": "missing_passphrase"}, indent=2))
        return 1

    latest = archives[-1]
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
                str(latest),
                "-out",
                str(tar_path),
                "-pass",
                f"file:{PASSPHRASE_FILE}",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            print(json.dumps({"ok": False, "archive": str(latest), "error": "decrypt_failed"}, indent=2))
            return 1
        with tarfile.open(tar_path, "r:gz") as tar:
            names = tar.getnames()

    required = {
        "export/private-exact.json",
        "export/latest-summary.json",
        "findmysync/events.jsonl",
    }
    payload = {
        "ok": required.issubset(set(names)),
        "archive": str(latest),
        "file_count": len(names),
        "contains_required": sorted(required.intersection(names)),
        "privacy": "Verified by listing archive members only; no private rows or coordinates printed.",
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
