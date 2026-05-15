#!/usr/bin/env python3
"""Publish Martin's local Find My export into the local Traccar instance."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from datetime import datetime, timezone
from http.cookiejar import CookieJar
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import HTTPCookieProcessor, Request, build_opener, urlopen


EXPORT = Path("/Users/mh/.openclaw/workspace/state/apple-find-my/export/private-exact.json")
STATE_DIR = Path("/Users/mh/.openclaw/workspace/state/apple-find-my/traccar")
LOGIN_ENV = STATE_DIR / "login.env"
LOG_PATH = STATE_DIR / "bridge-log.jsonl"
DEFAULT_BASE_URL = "http://127.0.0.1:18082"
DEFAULT_OSMAND_URL = "http://127.0.0.1:15055"


def read_env(path: Path) -> dict[str, str]:
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


def slug(value: str, fallback: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "-", value.strip()).strip("-").lower()
    return cleaned[:48] or fallback


def stable_slug(name: str, unique_value: str | None, fallback: str) -> str:
    base = slug(name, fallback)
    if unique_value:
        digest = hashlib.sha1(unique_value.encode("utf-8")).hexdigest()[:8]
        return f"{base[:39]}-{digest}"
    return base


def parse_timestamp(value: Any) -> int:
    if isinstance(value, (int, float)):
        return int(value / 1000) if value > 100_000_000_000 else int(value)
    if isinstance(value, str) and value:
        try:
            return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp())
        except ValueError:
            return int(time.time())
    return int(time.time())


class Client:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.opener = build_opener(HTTPCookieProcessor(CookieJar()))

    def request(self, method: str, path: str, payload: dict | None = None, form: dict | None = None) -> tuple[int, Any]:
        data = None
        headers = {}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if form is not None:
            data = urlencode(form).encode("utf-8")
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        req = Request(f"{self.base_url}{path}", data=data, method=method, headers=headers)
        try:
            with self.opener.open(req, timeout=20) as response:
                raw = response.read().decode("utf-8")
                return response.status, json.loads(raw) if raw else None
        except HTTPError as exc:
            raw = exc.read().decode("utf-8")
            try:
                return exc.code, json.loads(raw) if raw else raw
            except json.JSONDecodeError:
                return exc.code, raw


def load_export() -> dict[str, Any]:
    return json.loads(EXPORT.read_text())


def iter_points(data: dict[str, Any]) -> list[dict[str, Any]]:
    points: list[dict[str, Any]] = []

    def add(category: str, name: str, unique: str | None, loc: dict[str, Any]) -> None:
        if loc.get("latitude") is None or loc.get("longitude") is None:
            return
        unique_id = f"findmy-{category}-{stable_slug(name, unique, category)}"
        points.append(
            {
                "category": category,
                "name": name,
                "uniqueId": unique_id[:120],
                "lat": float(loc["latitude"]),
                "lon": float(loc["longitude"]),
                "timestamp": parse_timestamp(loc.get("timeStamp") or loc.get("timestamp") or loc.get("location_timestamp")),
                "accuracy": loc.get("horizontalAccuracy") or loc.get("horizontal_accuracy"),
                "altitude": loc.get("altitude"),
                "speed": loc.get("speed"),
            }
        )

    for person in data.get("followmyfriends_people_enriched") or []:
        loc = person.get("location")
        if isinstance(loc, dict):
            name = person.get("full_name") or person.get("display_name") or person.get("handle") or "person"
            unique = person.get("handle_server_identifier") or person.get("handle") or name
            add("people", name, unique, loc)

    for device in data.get("devices") or []:
        loc = device.get("location")
        if isinstance(loc, dict):
            name = device.get("name") or device.get("deviceDisplayName") or device.get("id") or "device"
            unique = device.get("id") or device.get("identifier") or device.get("serialNumber") or name
            add("devices", name, unique, loc)

    for item in data.get("items") or []:
        loc = item.get("location")
        if isinstance(loc, dict):
            name = item.get("name") or item.get("displayName") or item.get("identifier") or "item"
            unique = item.get("identifier") or item.get("id") or item.get("serialNumber") or name
            add("items", name, unique, loc)

    merged: dict[str, dict[str, Any]] = {}
    for point in points:
        unique_id = point["uniqueId"]
        existing = merged.get(unique_id)
        if existing is None or point["timestamp"] >= existing["timestamp"]:
            merged[unique_id] = point

    return list(merged.values())


def login(client: Client, env: dict[str, str]) -> None:
    status, _ = client.request(
        "POST",
        "/api/session",
        form={"email": env["TRACCAR_LOGIN_EMAIL"], "password": env["TRACCAR_LOGIN_PASSWORD"]},
    )
    if status != 200:
        raise RuntimeError(f"Traccar login failed with HTTP {status}")


def ensure_devices(client: Client, points: list[dict[str, Any]]) -> int:
    status, existing = client.request("GET", "/api/devices")
    if status != 200 or not isinstance(existing, list):
        raise RuntimeError(f"Traccar devices query failed with HTTP {status}")
    by_unique = {row.get("uniqueId"): row for row in existing}
    created = 0
    for point in points:
        if point["uniqueId"] in by_unique:
            continue
        status, _ = client.request(
            "POST",
            "/api/devices",
            payload={
                "name": f"{point['category']}: {point['name']}",
                "uniqueId": point["uniqueId"],
                "category": "person" if point["category"] == "people" else "default",
                "attributes": {"findmyCategory": point["category"]},
            },
        )
        if status not in (200, 201):
            raise RuntimeError(f"Traccar device creation failed with HTTP {status}")
        created += 1
    return created


def send_position(osmand_url: str, point: dict[str, Any]) -> None:
    params = {
        "id": point["uniqueId"],
        "lat": f"{point['lat']:.8f}",
        "lon": f"{point['lon']:.8f}",
        "timestamp": datetime.fromtimestamp(point["timestamp"], tz=timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    if point.get("accuracy") is not None:
        params["accuracy"] = str(point["accuracy"])
    if point.get("altitude") is not None:
        params["altitude"] = str(point["altitude"])
    if point.get("speed") is not None:
        params["speed"] = str(point["speed"])
    with urlopen(f"{osmand_url.rstrip('/')}/?{urlencode(params)}", timeout=10) as response:
        if response.status < 200 or response.status >= 300:
            raise RuntimeError(f"Traccar OsmAnd endpoint returned HTTP {response.status}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--osmand-url", default=DEFAULT_OSMAND_URL)
    parser.add_argument("--print-summary", action="store_true")
    args = parser.parse_args()

    env = read_env(LOGIN_ENV)
    if not env:
        raise RuntimeError(f"Missing Traccar login env: {LOGIN_ENV}")
    client = Client(args.base_url or env.get("TRACCAR_BASE_URL", DEFAULT_BASE_URL))
    login(client, env)
    data = load_export()
    points = iter_points(data)
    created = ensure_devices(client, points)

    sent = 0
    errors: list[str] = []
    for point in points:
        try:
            send_position(args.osmand_url, point)
            sent += 1
        except Exception as exc:  # noqa: BLE001 - local bridge should summarize all failures
            errors.append(f"{point['category']}: {exc}")

    summary = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "source_generated_at": data.get("generated_at"),
        "points_seen": len(points),
        "devices_created": created,
        "positions_sent": sent,
        "errors": errors[:5],
    }
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a") as fh:
        fh.write(json.dumps(summary, ensure_ascii=False) + "\n")
    if args.print_summary:
        print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
