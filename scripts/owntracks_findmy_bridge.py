#!/usr/bin/env python3
"""Publish Martin's local Find My export into the local OwnTracks recorder.

This keeps exact location data on the Mac. It sends OwnTracks-compatible
location payloads only to the local recorder at 127.0.0.1.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen


EXPORT = Path("/Users/mh/.openclaw/workspace/state/apple-find-my/export/private-exact.json")
STATE_DIR = Path("/Users/mh/.openclaw/workspace/state/apple-find-my/owntracks")
LOG_PATH = STATE_DIR / "bridge-log.jsonl"
DEFAULT_ENDPOINT = "http://127.0.0.1:18083/pub"


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
    digest = hashlib.sha1(value.encode("utf-8")).hexdigest().upper()
    return digest[:2]


def parse_timestamp(value: Any) -> int:
    if isinstance(value, (int, float)):
        # Apple plists commonly use seconds; OwnTracks wants Unix seconds.
        return int(value)
    if isinstance(value, str) and value:
        text = value.replace("Z", "+00:00")
        try:
            return int(datetime.fromisoformat(text).timestamp())
        except ValueError:
            pass
    return int(time.time())


def load_export() -> dict[str, Any]:
    return json.loads(EXPORT.read_text())


def make_payload(name: str, loc: dict[str, Any], category: str) -> dict[str, Any] | None:
    lat = loc.get("latitude")
    lon = loc.get("longitude")
    if lat is None or lon is None:
        return None
    payload: dict[str, Any] = {
        "_type": "location",
        "lat": float(lat),
        "lon": float(lon),
        "tst": parse_timestamp(loc.get("timestamp")),
        "tid": short_tid(name),
        "t": "u",
        "conn": "w",
        "inregions": [category],
    }
    for owntracks_key, source_key in (
        ("acc", "horizontalAccuracy"),
        ("alt", "altitude"),
        ("vel", "speed"),
        ("cog", "course"),
        ("vac", "verticalAccuracy"),
    ):
        value = loc.get(source_key)
        if value is not None:
            payload[owntracks_key] = value
    return payload


def iter_points(data: dict[str, Any]) -> list[tuple[str, str, dict[str, Any]]]:
    points: list[tuple[str, str, dict[str, Any]]] = []

    for person in data.get("followmyfriends_people_enriched") or []:
        loc = person.get("location")
        if not isinstance(loc, dict):
            continue
        name = person.get("full_name") or person.get("display_name") or person.get("handle") or "person"
        unique = person.get("handle_server_identifier") or person.get("handle") or name
        payload = make_payload(name, loc, "people")
        if payload:
            points.append(("people", stable_slug(name, unique, "person"), payload))

    for device in data.get("devices") or []:
        loc = device.get("location")
        if not isinstance(loc, dict):
            continue
        name = device.get("name") or device.get("deviceDisplayName") or device.get("id") or "device"
        unique = device.get("id") or device.get("identifier") or device.get("serialNumber") or name
        payload = make_payload(name, loc, "devices")
        if payload:
            points.append(("devices", stable_slug(name, unique, "device"), payload))

    for item in data.get("items") or []:
        loc = item.get("location")
        if not isinstance(loc, dict):
            continue
        name = item.get("name") or item.get("displayName") or item.get("identifier") or "item"
        unique = item.get("identifier") or item.get("id") or item.get("serialNumber") or name
        payload = make_payload(name, loc, "items")
        if payload:
            points.append(("items", stable_slug(name, unique, "item"), payload))

    return points


def post_point(endpoint: str, user: str, device: str, payload: dict[str, Any]) -> None:
    url = f"{endpoint}?{urlencode({'u': user, 'd': device})}"
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    req = Request(url, data=body, headers={"Content-Type": "application/json"})
    with urlopen(req, timeout=10) as response:
        if response.status < 200 or response.status >= 300:
            raise RuntimeError(f"OwnTracks recorder returned HTTP {response.status}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    parser.add_argument("--print-summary", action="store_true")
    args = parser.parse_args()

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    data = load_export()
    points = iter_points(data)
    sent = 0
    errors: list[str] = []
    for user, device, payload in points:
        try:
            post_point(args.endpoint, user, device, payload)
            sent += 1
        except Exception as exc:  # noqa: BLE001 - log local bridge failures compactly
            errors.append(f"{user}/{device}: {exc}")

    summary = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "source_generated_at": data.get("generated_at"),
        "points_seen": len(points),
        "points_sent": sent,
        "errors": errors[:5],
    }
    with LOG_PATH.open("a") as fh:
        fh.write(json.dumps(summary, ensure_ascii=False) + "\n")
    if args.print_summary:
        print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
