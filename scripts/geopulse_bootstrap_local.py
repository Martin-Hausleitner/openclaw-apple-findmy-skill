#!/usr/bin/env python3
"""Create the local GeoPulse account and Find My OwnTracks source if missing."""

from __future__ import annotations

import argparse
import json
import os
import secrets
import string
from http.cookiejar import CookieJar
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, Request, build_opener


STATE_DIR = Path("/Users/mh/.openclaw/workspace/state/apple-find-my/geopulse")
LOGIN_ENV = STATE_DIR / "login.env"
BRIDGE_ENV = STATE_DIR / "bridge.env"
DEFAULT_BASE_URL = "http://127.0.0.1:18085"
DEFAULT_EMAIL = "martin.findmy.local@example.com"
DEFAULT_NAME = "Martin FindMy Local"
DEFAULT_TIMEZONE = "Europe/Vienna"


def random_password() -> str:
    alphabet = string.ascii_letters + string.digits + "!-_"
    return "".join(secrets.choice(alphabet) for _ in range(28))


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


def write_env(path: Path, values: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "".join(f"{key}={value}\n" for key, value in values.items())
    path.write_text(text)
    path.chmod(0o600)


def ensure_login_env() -> dict[str, str]:
    values = read_env(LOGIN_ENV)
    if values:
        return values
    values = {
        "GEOPULSE_BASE_URL": DEFAULT_BASE_URL,
        "GEOPULSE_LOGIN_EMAIL": DEFAULT_EMAIL,
        "GEOPULSE_LOGIN_PASSWORD": random_password(),
        "GEOPULSE_LOGIN_FULL_NAME": DEFAULT_NAME,
        "GEOPULSE_LOGIN_TIMEZONE": DEFAULT_TIMEZONE,
    }
    write_env(LOGIN_ENV, values)
    return values


def ensure_bridge_env() -> dict[str, str]:
    values = read_env(BRIDGE_ENV)
    if values:
        return values
    values = {
        "GEOPULSE_OWNTRACKS_ENDPOINT": f"{DEFAULT_BASE_URL}/api/owntracks",
        "GEOPULSE_OWNTRACKS_USERNAME": "findmy",
        "GEOPULSE_OWNTRACKS_PASSWORD": random_password(),
    }
    write_env(BRIDGE_ENV, values)
    return values


class Client:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.opener = build_opener(HTTPCookieProcessor(CookieJar()))

    def request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> tuple[int, Any]:
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        req = Request(
            f"{self.base_url}{path}",
            data=body,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        try:
            with self.opener.open(req, timeout=20) as response:
                raw = response.read().decode("utf-8")
                return response.status, json.loads(raw) if raw else None
        except HTTPError as exc:
            raw = exc.read().decode("utf-8")
            try:
                return exc.code, json.loads(raw) if raw else None
            except json.JSONDecodeError:
                return exc.code, raw


def login_or_register(client: Client, login: dict[str, str]) -> None:
    payload = {
        "email": login["GEOPULSE_LOGIN_EMAIL"],
        "password": login["GEOPULSE_LOGIN_PASSWORD"],
    }
    status, _ = client.request("POST", "/api/auth/login", payload)
    if status == 200:
        return

    status, _ = client.request(
        "POST",
        "/api/users/register",
        {
            **payload,
            "fullName": login.get("GEOPULSE_LOGIN_FULL_NAME", DEFAULT_NAME),
            "timezone": login.get("GEOPULSE_LOGIN_TIMEZONE", DEFAULT_TIMEZONE),
        },
    )
    if status not in (200, 201):
        raise RuntimeError(f"GeoPulse register/login failed with HTTP {status}")

    status, _ = client.request("POST", "/api/auth/login", payload)
    if status != 200:
        raise RuntimeError(f"GeoPulse login after register failed with HTTP {status}")


def ensure_source(client: Client, bridge: dict[str, str]) -> bool:
    username = bridge.get("GEOPULSE_OWNTRACKS_USERNAME", "findmy")
    password = bridge["GEOPULSE_OWNTRACKS_PASSWORD"]
    status, response = client.request("GET", "/api/gps/source")
    if status == 200 and isinstance(response, list):
        if any(source.get("type") == "OWNTRACKS" and source.get("username") == username for source in response):
            return False
    status, _ = client.request(
        "POST",
        "/api/gps/source",
        {
            "type": "OWNTRACKS",
            "username": username,
            "password": password,
            "token": "",
            "deviceId": None,
            "connectionType": "HTTP",
            "filterInaccurateData": False,
            "maxAllowedAccuracy": None,
            "maxAllowedSpeed": None,
            "enableDuplicateDetection": False,
            "duplicateDetectionThresholdMinutes": None,
        },
    )
    if status not in (200, 201):
        raise RuntimeError(f"GeoPulse source creation failed with HTTP {status}")
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--print-summary", action="store_true")
    args = parser.parse_args()

    login = ensure_login_env()
    bridge = ensure_bridge_env()
    client = Client(os.environ.get("GEOPULSE_BASE_URL") or login.get("GEOPULSE_BASE_URL", DEFAULT_BASE_URL))
    login_or_register(client, login)
    created = ensure_source(client, bridge)
    if args.print_summary:
        print(json.dumps({"login": "ok", "source": "created" if created else "exists"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
