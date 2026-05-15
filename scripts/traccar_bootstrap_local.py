#!/usr/bin/env python3
"""Create the local Traccar account if missing."""

from __future__ import annotations

import argparse
import json
import secrets
import string
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import HTTPCookieProcessor, Request, build_opener


STATE_DIR = Path("/Users/mh/.openclaw/workspace/state/apple-find-my/traccar")
LOGIN_ENV = STATE_DIR / "login.env"
DEFAULT_BASE_URL = "http://127.0.0.1:18082"
DEFAULT_EMAIL = "martin.findmy.local@example.com"
DEFAULT_NAME = "Martin FindMy Local"


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
    path.write_text("".join(f"{key}={value}\n" for key, value in values.items()))
    path.chmod(0o600)


def ensure_login_env() -> dict[str, str]:
    values = read_env(LOGIN_ENV)
    if values:
        return values
    values = {
        "TRACCAR_BASE_URL": DEFAULT_BASE_URL,
        "TRACCAR_LOGIN_EMAIL": DEFAULT_EMAIL,
        "TRACCAR_LOGIN_PASSWORD": random_password(),
        "TRACCAR_LOGIN_NAME": DEFAULT_NAME,
    }
    write_env(LOGIN_ENV, values)
    return values


class Client:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.opener = build_opener(HTTPCookieProcessor(CookieJar()))

    def request(self, method: str, path: str, payload: dict | None = None, form: dict | None = None) -> tuple[int, object]:
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


def login_or_create(client: Client, login: dict[str, str]) -> None:
    form = {"email": login["TRACCAR_LOGIN_EMAIL"], "password": login["TRACCAR_LOGIN_PASSWORD"]}
    status, _ = client.request("POST", "/api/session", form=form)
    if status == 200:
        return

    status, _ = client.request(
        "POST",
        "/api/users",
        payload={
            "name": login.get("TRACCAR_LOGIN_NAME", DEFAULT_NAME),
            "email": login["TRACCAR_LOGIN_EMAIL"],
            "password": login["TRACCAR_LOGIN_PASSWORD"],
        },
    )
    if status not in (200, 201):
        raise RuntimeError(f"Traccar user creation failed with HTTP {status}")

    status, _ = client.request("POST", "/api/session", form=form)
    if status != 200:
        raise RuntimeError(f"Traccar login failed with HTTP {status}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--print-summary", action="store_true")
    args = parser.parse_args()

    login = ensure_login_env()
    client = Client(login.get("TRACCAR_BASE_URL", DEFAULT_BASE_URL))
    login_or_create(client, login)
    if args.print_summary:
        print(json.dumps({"login": "ok"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
