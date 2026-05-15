#!/usr/bin/env python3
"""Private Apple Find My exporter for OpenClaw/Hermes.

The script reads locally extracted Find My keys and macOS Find My caches,
decrypts them on-device, writes exact data to a private state directory, and
writes a redacted summary for agents and dashboards.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import plistlib
import shutil
import sqlite3
import tempfile
from pathlib import Path
from typing import Any

try:
    from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
except Exception as exc:  # pragma: no cover - dependency preflight path
    raise SystemExit(
        "Missing dependency: cryptography. Install with "
        "`python3 -m pip install cryptography`."
    ) from exc


HOME = Path.home()
KEY_DIR = Path(
    "/Users/mh/.openclaw/workspace/skills/apple-find-my/vendor/findmy-key-extractor/keys"
)
FMIP_CACHE = HOME / "Library/Caches/com.apple.findmy.fmipcore"
FMF_CACHE = HOME / "Library/Caches/com.apple.findmy.fmfcore"
FMF_LOCAL_DB = (
    HOME
    / "Library/Group Containers/group.com.apple.findmy.findmylocateagent/Library/Application Support/LocalStorage.db"
)
FMF_DECRYPTED_DB = Path(
    "/Users/mh/.openclaw/workspace/state/apple-find-my/followmyfriends/LocalStorage_decrypted.sqlite"
)
STATE_DIR = Path("/Users/mh/.openclaw/workspace/state/apple-find-my/export")


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def load_symmetric_key(path: Path) -> bytes:
    with path.open("rb") as f:
        data = plistlib.load(f)
    key = data["symmetricKey"]["key"]["data"]
    if not isinstance(key, bytes) or len(key) != 32:
        raise ValueError(f"Unexpected key format in {path}")
    return key


def decrypt_cache_file(path: Path, key: bytes) -> Any:
    with path.open("rb") as f:
        envelope = plistlib.load(f)
    encrypted = envelope["encryptedData"]
    if not isinstance(encrypted, bytes) or len(encrypted) < 29:
        raise ValueError(f"Unexpected encryptedData in {path}")
    nonce = encrypted[:12]
    ciphertext_and_tag = encrypted[12:]
    plaintext = ChaCha20Poly1305(key).decrypt(nonce, ciphertext_and_tag, None)
    return plistlib.loads(plaintext)


def copy_sqlite_live(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(src))
    try:
        backup = sqlite3.connect(str(dst))
        try:
            con.backup(backup)
        finally:
            backup.close()
    finally:
        con.close()
    dst.chmod(0o600)


def count_location_rows(rows: list[dict[str, Any]]) -> int:
    return sum(1 for row in rows if isinstance(row, dict) and row.get("location"))


def coarse_address(row: dict[str, Any]) -> str | None:
    address = row.get("address")
    if not isinstance(address, dict):
        return None
    for key in ("locality", "coarseAddressModern", "administrativeArea", "country"):
        value = address.get(key)
        if value:
            return str(value)
    return None


def redacted_rows(rows: list[dict[str, Any]], limit: int = 40) -> list[dict[str, Any]]:
    out = []
    for row in rows[:limit]:
        if not isinstance(row, dict):
            continue
        label = (
            row.get("name")
            or row.get("deviceDisplayName")
            or row.get("deviceName")
            or row.get("modelDisplayName")
            or row.get("identifier")
            or row.get("baUUID")
        )
        loc = row.get("location") if isinstance(row.get("location"), dict) else {}
        out.append(
            {
                "label": str(label)[:120] if label is not None else None,
                "kind": str(row.get("productType") or row.get("deviceClass") or "")[:80],
                "has_location": bool(loc),
                "coarse_place": coarse_address(row),
                "battery_present": any(
                    k in row for k in ("batteryLevel", "batteryStatus", "battery")
                ),
                "location_age_raw_present": any(
                    k in loc for k in ("timeStamp", "timestamp", "locationTimestamp")
                )
                if isinstance(loc, dict)
                else False,
            }
        )
    return out


def anonymize_handle(value: Any) -> str | None:
    if value is None:
        return None
    digest = hashlib.sha256(str(value).encode("utf-8")).hexdigest()[:10]
    return f"handle_{digest}"


def summarize_friends_cache(cache: Any) -> dict[str, Any]:
    summary: dict[str, Any] = {"type": type(cache).__name__}
    if not isinstance(cache, dict):
        return summary
    for key in (
        "followers",
        "following",
        "futureFollowers",
        "futureFollowing",
        "pendingFollowers",
        "devices",
        "contacts",
    ):
        value = cache.get(key)
        if isinstance(value, list):
            summary[f"{key}_count"] = len(value)
    following = cache.get("following")
    if isinstance(following, list):
        summary["following_sample"] = [
            {
                "handle": anonymize_handle(
                    row.get("id") or row.get("email") or row.get("phones")
                )
                if isinstance(row, dict)
                else None,
                "label_present": bool(isinstance(row, dict) and row.get("name")),
            }
            for row in following[:20]
        ]
    return summary


def sqlite_summary(db_path: Path) -> dict[str, Any]:
    if not db_path.exists():
        return {"exists": False}
    con = sqlite3.connect(str(db_path))
    try:
        cur = con.cursor()
        tables = [
            row[0]
            for row in cur.execute(
                "select name from sqlite_master where type='table' order by name"
            )
        ]
        counts = {}
        for table in tables:
            try:
                counts[table] = cur.execute(f'select count(*) from "{table}"').fetchone()[0]
            except sqlite3.DatabaseError:
                pass
        return {"exists": True, "tables": tables, "counts": counts}
    finally:
        con.close()


def write_json(path: Path, data: Any, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(to_jsonable(data), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    tmp.chmod(mode)
    tmp.replace(path)
    path.chmod(mode)


def to_jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): to_jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [to_jsonable(v) for v in value]
    if isinstance(value, tuple):
        return [to_jsonable(v) for v in value]
    if isinstance(value, (dt.datetime, dt.date)):
        return value.isoformat()
    if isinstance(value, bytes):
        return {"_bytes": len(value), "sha256": hashlib.sha256(value).hexdigest()}
    return value


def export(args: argparse.Namespace) -> int:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    STATE_DIR.chmod(0o700)

    fmip_key = load_symmetric_key(KEY_DIR / "FMIPDataManager.bplist")
    fmf_key = load_symmetric_key(KEY_DIR / "FMFDataManager.bplist")

    exact: dict[str, Any] = {"generated_at": now_iso(), "source": "local_findmy_cache"}
    exact["items"] = decrypt_cache_file(FMIP_CACHE / "Items.data", fmip_key)
    exact["devices"] = decrypt_cache_file(FMIP_CACHE / "Devices.data", fmip_key)
    exact["family_members"] = decrypt_cache_file(FMIP_CACHE / "FamilyMembers.data", fmip_key)
    exact["item_groups"] = decrypt_cache_file(FMIP_CACHE / "ItemGroups.data", fmip_key)
    exact["safe_locations"] = decrypt_cache_file(FMIP_CACHE / "SafeLocations.data", fmip_key)
    exact["owner"] = decrypt_cache_file(FMIP_CACHE / "Owner.data", fmip_key)
    if (FMF_CACHE / "FriendCacheData.data").exists():
        exact["friends_cache"] = decrypt_cache_file(FMF_CACHE / "FriendCacheData.data", fmf_key)

    summary = {
        "generated_at": exact["generated_at"],
        "privacy": "Redacted summary. Exact private data is stored only in private-exact.json with mode 0600.",
        "counts": {
            "items": len(exact["items"]) if isinstance(exact["items"], list) else None,
            "items_with_location": count_location_rows(exact["items"])
            if isinstance(exact["items"], list)
            else None,
            "devices": len(exact["devices"]) if isinstance(exact["devices"], list) else None,
            "devices_with_location": count_location_rows(exact["devices"])
            if isinstance(exact["devices"], list)
            else None,
            "family_members": len(exact["family_members"])
            if isinstance(exact["family_members"], list)
            else None,
            "item_groups": len(exact["item_groups"])
            if isinstance(exact["item_groups"], list)
            else None,
        },
        "items_sample": redacted_rows(exact["items"]) if isinstance(exact["items"], list) else [],
        "devices_sample": redacted_rows(exact["devices"])
        if isinstance(exact["devices"], list)
        else [],
        "friends_cache": summarize_friends_cache(exact.get("friends_cache")),
    }

    private_exact = STATE_DIR / "private-exact.json"
    redacted_summary = STATE_DIR / "redacted-summary.json"
    write_json(private_exact, exact, 0o600)
    write_json(redacted_summary, summary, 0o644)

    if FMF_DECRYPTED_DB.exists():
        summary["followmyfriends_sqlite"] = sqlite_summary(FMF_DECRYPTED_DB)
        write_json(redacted_summary, summary, 0o644)
    elif FMF_LOCAL_DB.exists():
        copied = STATE_DIR / "followmyfriends-localstorage.sqlite"
        try:
            copy_sqlite_live(FMF_LOCAL_DB, copied)
            summary["followmyfriends_sqlite"] = sqlite_summary(copied)
            write_json(redacted_summary, summary, 0o644)
        except sqlite3.DatabaseError as exc:
            summary["followmyfriends_sqlite"] = {
                "exists": True,
                "encrypted_or_unreadable": True,
                "error": str(exc),
            }
            write_json(redacted_summary, summary, 0o644)

    latest = STATE_DIR / "latest-summary.json"
    shutil.copy2(redacted_summary, latest)
    latest.chmod(0o644)

    if args.print_summary:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(f"Wrote {redacted_summary}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--print-summary", action="store_true")
    args = parser.parse_args()
    return export(args)


if __name__ == "__main__":
    raise SystemExit(main())
