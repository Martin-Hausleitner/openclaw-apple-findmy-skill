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
import subprocess
import sys
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
LOCALSTORAGE_KEY = KEY_DIR / "LocalStorage.key"
LOCALSTORAGE_DECRYPTOR = KEY_DIR.parent / "decrypt_localstorage.py"
STATE_DIR = Path("/Users/mh/.openclaw/workspace/state/apple-find-my/export")
ADDRESSBOOK_ROOT = HOME / "Library/Application Support/AddressBook"


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


def refresh_followmyfriends_sqlite() -> dict[str, Any]:
    status: dict[str, Any] = {
        "source": str(FMF_LOCAL_DB),
        "output": str(FMF_DECRYPTED_DB),
        "refreshed": False,
    }
    if not FMF_LOCAL_DB.exists():
        status["error"] = "encrypted LocalStorage.db missing"
        return status
    if not LOCALSTORAGE_KEY.exists():
        status["error"] = "LocalStorage.key missing"
        return status
    if not LOCALSTORAGE_DECRYPTOR.exists():
        status["error"] = "decrypt_localstorage.py missing"
        return status

    FMF_DECRYPTED_DB.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        prefix="LocalStorage_decrypted.",
        suffix=".sqlite",
        dir=str(FMF_DECRYPTED_DB.parent),
        delete=False,
    ) as tmp:
        tmp_path = Path(tmp.name)

    try:
        result = subprocess.run(
            [
                sys.executable,
                str(LOCALSTORAGE_DECRYPTOR),
                str(LOCALSTORAGE_KEY),
                "--db",
                str(FMF_LOCAL_DB),
                "-o",
                str(tmp_path),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        status["returncode"] = result.returncode
        if result.returncode != 0:
            status["error"] = (result.stderr or result.stdout).strip()[-500:]
            tmp_path.unlink(missing_ok=True)
            return status
        sqlite3.connect(str(tmp_path)).close()
        tmp_path.chmod(0o600)
        tmp_path.replace(FMF_DECRYPTED_DB)
        FMF_DECRYPTED_DB.chmod(0o600)
        status["refreshed"] = True
        return status
    except Exception as exc:  # noqa: BLE001 - exporter should fall back with status
        status["error"] = str(exc)
        tmp_path.unlink(missing_ok=True)
        return status


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
        product_type = row.get("productType")
        if isinstance(product_type, dict):
            kind = product_type.get("type") or product_type.get("productInformation", {}).get(
                "productIdentifier"
            )
        else:
            kind = product_type or row.get("deviceClass")
        loc = row.get("location") if isinstance(row.get("location"), dict) else {}
        out.append(
            {
                "label": str(label)[:120] if label is not None else None,
                "kind": str(kind or "")[:80],
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


def normalize_phone(value: str) -> str:
    digits = "".join(ch for ch in value if ch.isdigit())
    if value.strip().startswith("+"):
        return "+" + digits
    if digits.startswith("00"):
        return "+" + digits[2:]
    if digits.startswith("0") and len(digits) > 6:
        # Martin's current contacts are mostly AT numbers; keep this as a
        # conservative helper, while also indexing raw digits below.
        return "+43" + digits[1:]
    return digits


def contact_display_name(row: sqlite3.Row) -> str | None:
    parts = [
        row["ZFIRSTNAME"],
        row["ZMIDDLENAME"],
        row["ZLASTNAME"],
    ]
    name = " ".join(str(part).strip() for part in parts if part)
    if name:
        return name
    for key in ("ZNAME", "ZORGANIZATION", "ZNICKNAME"):
        if row[key]:
            return str(row[key]).strip()
    return None


def contact_base(row: sqlite3.Row) -> dict[str, Any] | None:
    display = contact_display_name(row)
    if not display:
        return None
    photo_blob = row["ZTHUMBNAILIMAGEDATA"] or row["ZIMAGEDATA"]
    photo_sha = hashlib.sha256(photo_blob).hexdigest() if photo_blob else None
    return {
        "display_name": display,
        "full_name": display,
        "given_name": row["ZFIRSTNAME"],
        "family_name": row["ZLASTNAME"],
        "contact_unique_id": row["ZUNIQUEID"],
        "emails": [],
        "phones": [],
        "has_photo": bool(photo_blob or row["ZIMAGEREFERENCE"] or row["ZEXTERNALIMAGEURI"]),
        "photo_sha256": photo_sha,
        "photo_bytes": len(photo_blob) if photo_blob else 0,
        "photo_reference_present": bool(row["ZIMAGEREFERENCE"] or row["ZEXTERNALIMAGEURI"]),
    }


def add_contact_index(index: dict[str, dict[str, Any]], key: str, contact: dict[str, Any]) -> None:
    if key and key not in index:
        index[key] = contact


def load_contacts_index() -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    dbs = [ADDRESSBOOK_ROOT / "AddressBook-v22.abcddb"]
    dbs.extend(ADDRESSBOOK_ROOT.glob("Sources/*/AddressBook-v22.abcddb"))
    index: dict[str, dict[str, Any]] = {}
    stats = {"databases": 0, "contacts_indexed": 0, "emails_indexed": 0, "phones_indexed": 0}

    for db in dbs:
        if not db.exists():
            continue
        stats["databases"] += 1
        con = sqlite3.connect(str(db))
        con.row_factory = sqlite3.Row
        try:
            people = {}
            contacts_by_pk: dict[int, dict[str, Any]] = {}
            for row in con.execute(
                """
                select Z_PK, ZUNIQUEID, ZFIRSTNAME, ZMIDDLENAME, ZLASTNAME,
                       ZNAME, ZORGANIZATION, ZNICKNAME, ZIMAGEREFERENCE,
                       ZEXTERNALIMAGEURI, ZIMAGEDATA, ZTHUMBNAILIMAGEDATA
                from ZABCDRECORD
                """
            ):
                people[row["Z_PK"]] = row
                contact = contact_base(row)
                if contact:
                    contacts_by_pk[row["Z_PK"]] = contact
            stats["contacts_indexed"] += len(people)
            for row in con.execute(
                "select ZOWNER, ZADDRESS, ZADDRESSNORMALIZED from ZABCDEMAILADDRESS"
            ):
                contact = contacts_by_pk.get(row["ZOWNER"])
                if not contact:
                    continue
                values = []
                for value in (row["ZADDRESS"], row["ZADDRESSNORMALIZED"]):
                    if value:
                        normalized = str(value).strip().lower()
                        values.append(normalized)
                        indexed = dict(contact)
                        indexed["match_type"] = "email"
                        add_contact_index(index, normalized, indexed)
                        stats["emails_indexed"] += 1
                for value in sorted(set(values)):
                    if value not in contact["emails"]:
                        contact["emails"].append(value)
            for row in con.execute("select ZOWNER, ZFULLNUMBER, ZLOCALNUMBER from ZABCDPHONENUMBER"):
                contact = contacts_by_pk.get(row["ZOWNER"])
                if not contact:
                    continue
                display_values = []
                for value in (row["ZFULLNUMBER"], row["ZLOCALNUMBER"]):
                    if not value:
                        continue
                    raw = str(value).strip()
                    display_values.append(raw)
                    for key in {raw, normalize_phone(raw), "".join(ch for ch in raw if ch.isdigit())}:
                        indexed = dict(contact)
                        indexed["match_type"] = "phone"
                        add_contact_index(index, key, indexed)
                    stats["phones_indexed"] += 1
                for value in sorted(set(display_values)):
                    if value not in contact["phones"]:
                        contact["phones"].append(value)
        finally:
            con.close()
    return index, stats


def lookup_contact(handle: str, index: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    raw = handle.strip()
    keys = [raw, raw.lower()]
    if "@" not in raw:
        keys.extend([normalize_phone(raw), "".join(ch for ch in raw if ch.isdigit())])
    for key in keys:
        if key in index:
            return dict(index[key])
    return None


def followmyfriends_people(db_path: Path, contacts: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    if not db_path.exists():
        return []
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    try:
        rows = []
        locations = followmyfriends_secure_locations(con)
        for row in con.execute(
            """
            select handleIdentifier, handleQualifiedID, handlePrettyName,
                   ownerHandlePrettyName, handleContactIdentifier, handleServerIdentifier
            from friends
            order by handleIdentifier
            """
        ):
            handle = row["handleIdentifier"]
            contact = lookup_contact(handle, contacts) if handle else None
            display = row["handlePrettyName"] or (contact or {}).get("display_name")
            location = locations.get(row["handleServerIdentifier"])
            rows.append(
                {
                    "handle": handle,
                    "display_name": display or handle,
                    "full_name": (contact or {}).get("full_name") or display or handle,
                    "given_name": (contact or {}).get("given_name"),
                    "family_name": (contact or {}).get("family_name"),
                    "emails": (contact or {}).get("emails") or [],
                    "phones": (contact or {}).get("phones") or [],
                    "has_photo": bool((contact or {}).get("has_photo")),
                    "photo_sha256": (contact or {}).get("photo_sha256"),
                    "photo_bytes": (contact or {}).get("photo_bytes") or 0,
                    "photo_reference_present": bool(
                        (contact or {}).get("photo_reference_present")
                    ),
                    "contact_unique_id": (contact or {}).get("contact_unique_id"),
                    "match_type": (contact or {}).get("match_type") or "handle",
                    "has_contact_match": bool(contact),
                    "handle_contact_identifier": row["handleContactIdentifier"],
                    "handle_server_identifier": row["handleServerIdentifier"],
                    "location": location,
                    "has_location": bool(location),
                    "location_timestamp": (location or {}).get("timestamp"),
                    "location_label": (location or {}).get("locationLabel"),
                    "horizontal_accuracy": (location or {}).get("horizontalAccuracy"),
                }
            )
        by_server: dict[str, dict[str, Any]] = {}
        for person in rows:
            server_id = person.get("handle_server_identifier")
            if server_id and person.get("has_contact_match"):
                by_server.setdefault(str(server_id), person)
        for person in rows:
            if person.get("has_contact_match"):
                continue
            server_id = person.get("handle_server_identifier")
            matched = by_server.get(str(server_id)) if server_id else None
            if not matched:
                continue
            for key in (
                "display_name",
                "full_name",
                "given_name",
                "family_name",
                "emails",
                "phones",
                "has_photo",
                "photo_sha256",
                "photo_bytes",
                "photo_reference_present",
                "contact_unique_id",
            ):
                person[key] = matched.get(key)
            person["match_type"] = "same_person_location"
            person["has_contact_match"] = True
        return rows
    finally:
        con.close()


def followmyfriends_secure_locations(con: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    locations: dict[str, dict[str, Any]] = {}
    try:
        rows = con.execute("select serverUserID, value from secureLocations")
    except sqlite3.DatabaseError:
        return locations
    for row in rows:
        try:
            payload = plistlib.loads(row["value"])
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        key = str(row["serverUserID"])
        locations[key] = {
            "findMyId": payload.get("findMyId"),
            "latitude": payload.get("latitude"),
            "longitude": payload.get("longitude"),
            "horizontalAccuracy": payload.get("horizontalAccuracy"),
            "verticalAccuracy": payload.get("verticalAccuracy"),
            "altitude": payload.get("altitude"),
            "speed": payload.get("speed"),
            "course": payload.get("course"),
            "timestamp": payload.get("timestamp"),
            "locationLabel": payload.get("locationLabel"),
            "publishReason": payload.get("publishReason"),
            "motionActivityState": payload.get("motionActivityState"),
        }
    return locations


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
    contacts, contacts_stats = load_contacts_index()

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
        "contacts_index": contacts_stats,
    }

    private_exact = STATE_DIR / "private-exact.json"
    redacted_summary = STATE_DIR / "redacted-summary.json"

    summary["followmyfriends_decrypt"] = refresh_followmyfriends_sqlite()
    if FMF_DECRYPTED_DB.exists():
        summary["followmyfriends_sqlite"] = sqlite_summary(FMF_DECRYPTED_DB)
        people = followmyfriends_people(FMF_DECRYPTED_DB, contacts)
        exact["followmyfriends_people_enriched"] = people
        summary["followmyfriends_people"] = [
            {
                key: person.get(key)
                for key in (
                    "display_name",
                    "full_name",
                    "given_name",
                    "family_name",
                    "emails",
                    "phones",
                    "has_photo",
                    "photo_sha256",
                    "photo_bytes",
                    "photo_reference_present",
                    "match_type",
                    "has_contact_match",
                    "has_location",
                    "location_timestamp",
                    "location_label",
                    "horizontal_accuracy",
                )
            }
            for person in people
        ]
    elif FMF_LOCAL_DB.exists():
        copied = STATE_DIR / "followmyfriends-localstorage.sqlite"
        try:
            copy_sqlite_live(FMF_LOCAL_DB, copied)
            summary["followmyfriends_sqlite"] = sqlite_summary(copied)
        except sqlite3.DatabaseError as exc:
            summary["followmyfriends_sqlite"] = {
                "exists": True,
                "encrypted_or_unreadable": True,
                "error": str(exc),
            }

    write_json(private_exact, exact, 0o600)
    write_json(redacted_summary, summary, 0o644)

    latest = STATE_DIR / "latest-summary.json"
    shutil.copy2(redacted_summary, latest)
    latest.chmod(0o644)

    if args.print_summary:
        print(json.dumps(to_jsonable(summary), ensure_ascii=False, indent=2))
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
