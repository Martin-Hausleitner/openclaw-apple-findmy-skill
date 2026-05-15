#!/usr/bin/env python3
"""Publish Martin's local Find My export into the local GeoPulse OwnTracks API."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


EXPORT = Path("/Users/mh/.openclaw/workspace/state/apple-find-my/export/private-exact.json")
STATE_DIR = Path("/Users/mh/.openclaw/workspace/state/apple-find-my/geopulse")
ENV_PATH = STATE_DIR / "bridge.env"
LOG_PATH = STATE_DIR / "bridge-log.jsonl"
DEFAULT_ENDPOINT = "http://127.0.0.1:18085/api/owntracks"


def load_dotenv(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def env_value(name: str, default: str | None = None) -> str | None:
    return os.environ.get(name) or load_dotenv(ENV_PATH).get(name) or default


def slug(value: str, fallback: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "-", value.strip()).strip("-").lower()
    return cleaned[:48] or fallback


def stable_slug(name: str, unique_value: str | None, fallback: str) -> str:
    base = slug(name, fallback)
    if unique_value:
        digest = hashlib.sha1(unique_value.encode("utf-8")).hexdigest()[:8]
        return f"{base[:39]}-{digest}"
    return base


def short_tid(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]", "", value.upper())
    if len(cleaned) >= 2:
        return cleaned[:2]
    return hashlib.sha1(value.encode("utf-8")).hexdigest().upper()[:2]


def parse_timestamp(value: Any) -> int:
    if isinstance(value, (int, float)):
        return int(value / 1000) if value > 100_000_000_000 else int(value)
    if isinstance(value, str) and value:
        try:
            return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp())
        except ValueError:
            return int(time.time())
    return int(time.time())


def load_export() -> dict[str, Any]:
    if not EXPORT.exists():
        raise FileNotFoundError(f"Missing private export: {EXPORT}")
    return json.loads(EXPORT.read_text())


def make_payload(name: str, loc: dict[str, Any], category: str, device: str, username: str) -> dict[str, Any] | None:
    lat = loc.get("latitude")
    lon = loc.get("longitude")
    if lat is None or lon is None:
        return None

    payload: dict[str, Any] = {
        "_type": "location",
        "lat": float(lat),
        "lon": float(lon),
        "tst": parse_timestamp(loc.get("timeStamp") or loc.get("timestamp") or loc.get("location_timestamp")),
        "tid": short_tid(name),
        "t": "u",
        "conn": "w",
        "inregions": [category],
        "topic": f"owntracks/{username}/{device}",
        "username": username,
        "device": device,
    }
    for owntracks_key, source_key in (
        ("acc", "horizontalAccuracy"),
        ("acc", "horizontal_accuracy"),
        ("alt", "altitude"),
        ("vel", "speed"),
        ("cog", "course"),
        ("vac", "verticalAccuracy"),
    ):
        value = loc.get(source_key)
        if value is not None:
            payload[owntracks_key] = value
    return payload


def iter_points(data: dict[str, Any], username: str, preserve_duplicates: bool = True) -> list[tuple[str, str, dict[str, Any]]]:
    points: list[tuple[str, str, dict[str, Any]]] = []

    for person in data.get("followmyfriends_people_enriched") or []:
        loc = person.get("location")
        if not isinstance(loc, dict):
            continue
        name = person.get("full_name") or person.get("display_name") or person.get("handle") or "person"
        unique = person.get("handle_server_identifier") or person.get("handle") or name
        device = stable_slug(name, unique, "person")
        payload = make_payload(name, loc, "people", device, username)
        if payload:
            points.append(("people", device, payload))

    for device_row in data.get("devices") or []:
        loc = device_row.get("location")
        if not isinstance(loc, dict):
            continue
        name = device_row.get("name") or device_row.get("deviceDisplayName") or device_row.get("id") or "device"
        unique = device_row.get("id") or device_row.get("identifier") or device_row.get("serialNumber") or name
        device = stable_slug(name, unique, "device")
        payload = make_payload(name, loc, "devices", device, username)
        if payload:
            points.append(("devices", device, payload))

    for item in data.get("items") or []:
        loc = item.get("location")
        if not isinstance(loc, dict):
            continue
        name = item.get("name") or item.get("displayName") or item.get("identifier") or "item"
        unique = item.get("identifier") or item.get("id") or item.get("serialNumber") or name
        device = stable_slug(name, unique, "item")
        payload = make_payload(name, loc, "items", device, username)
        if payload:
            points.append(("items", device, payload))

    seen_devices: dict[tuple[str, str], int] = {}
    unique_points: list[tuple[str, str, dict[str, Any]]] = []
    for category, device, payload in points:
        key = (category, device)
        count = seen_devices.get(key, 0) + 1
        seen_devices[key] = count
        if count > 1:
            device = f"{device[:45]}-{count}"
            payload["device"] = device
            payload["topic"] = f"owntracks/{username}/{device}"
        unique_points.append((category, device, payload))

    points = unique_points

    if preserve_duplicates:
        seen: dict[tuple[float, float, int], int] = {}
        for _category, _device, payload in points:
            key = (round(float(payload["lat"]), 8), round(float(payload["lon"]), 8), int(payload["tst"]))
            offset = seen.get(key, 0)
            seen[key] = offset + 1
            if offset:
                # GeoPulse stores a user timeline and collapses identical
                # coordinate+timestamp rows. A tiny offset keeps separate
                # Find My entities visible without changing the place.
                payload["tst"] = int(payload["tst"]) + offset

    return points


def post_point(endpoint: str, username: str, password: str, payload: dict[str, Any]) -> None:
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
    req = Request(
        endpoint,
        data=body,
        headers={
            "Authorization": f"Basic {token}",
            "Content-Type": "application/json",
            "User-Agent": "openclaw-findmy-geopulse-bridge/1.0",
        },
    )
    with urlopen(req, timeout=10) as response:
        if response.status < 200 or response.status >= 300:
            raise RuntimeError(f"GeoPulse returned HTTP {response.status}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--endpoint", default=env_value("GEOPULSE_OWNTRACKS_ENDPOINT", DEFAULT_ENDPOINT))
    parser.add_argument("--username", default=env_value("GEOPULSE_OWNTRACKS_USERNAME", "findmy"))
    parser.add_argument("--password", default=env_value("GEOPULSE_OWNTRACKS_PASSWORD"))
    parser.add_argument("--no-preserve-duplicates", action="store_true")
    parser.add_argument("--print-summary", action="store_true")
    args = parser.parse_args()

    if not args.password:
        print(f"Missing GEOPULSE_OWNTRACKS_PASSWORD in environment or {ENV_PATH}", file=sys.stderr)
        return 2

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    data = load_export()
    points = iter_points(data, args.username, preserve_duplicates=not args.no_preserve_duplicates)
    sent = 0
    errors: list[str] = []
    per_category = {"people": 0, "devices": 0, "items": 0}

    for category, _device, payload in points:
        try:
            post_point(args.endpoint, args.username, args.password, payload)
            sent += 1
            per_category[category] = per_category.get(category, 0) + 1
        except (HTTPError, URLError, TimeoutError, RuntimeError) as exc:
            errors.append(f"{category}: {exc}")

    summary = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "source_generated_at": data.get("generated_at"),
        "points_seen": len(points),
        "points_sent": sent,
        "sent_by_category": per_category,
        "errors": errors[:5],
    }
    with LOG_PATH.open("a") as fh:
        fh.write(json.dumps(summary, ensure_ascii=False) + "\n")
    if args.print_summary:
        print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
