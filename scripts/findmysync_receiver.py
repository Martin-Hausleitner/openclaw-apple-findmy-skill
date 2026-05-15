#!/usr/bin/env python3
"""Local FindMySync receiver for OpenClaw/Hermes tests.

The receiver accepts FindMySync-style POSTs and keeps them in Martin's private
state directory. Console/status output is redacted; exact GPS payloads are not
printed.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


STATE_DIR = Path("/Users/mh/.openclaw/workspace/state/apple-find-my/findmysync")
EVENTS_PATH = STATE_DIR / "events.jsonl"
STATUS_PATH = STATE_DIR / "status.json"


def summarize(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {"kind": type(payload).__name__}
    gps = payload.get("gps")
    return {
        "dev_id": payload.get("dev_id"),
        "has_gps": isinstance(gps, list) and len(gps) >= 2,
        "gps_accuracy": payload.get("gps_accuracy"),
        "has_battery": "battery" in payload,
        "has_host_name": bool(payload.get("host_name")),
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "FindMySyncReceiver/1.1"

    def do_GET(self) -> None:
        event_count = 0
        unique_devices: set[str] = set()
        with_gps = 0
        with_battery = 0
        if EVENTS_PATH.exists():
            with EVENTS_PATH.open(encoding="utf-8") as f:
                for line in f:
                    event_count += 1
                    try:
                        payload = json.loads(line).get("payload")
                    except Exception:
                        continue
                    if not isinstance(payload, dict):
                        continue
                    if payload.get("dev_id"):
                        unique_devices.add(str(payload["dev_id"]))
                    gps = payload.get("gps")
                    if isinstance(gps, list) and len(gps) >= 2:
                        with_gps += 1
                    if "battery" in payload:
                        with_battery += 1

        findmysync_status = (
            {
                "status": "ok",
                "source": "patched FindMySync.app using OpenClaw exact local export",
                "events": event_count,
                "unique_dev_ids": len(unique_devices),
                "events_with_gps": with_gps,
                "events_with_battery": with_battery,
            }
            if event_count
            else {"status": "waiting", "reason": "No FindMySync events captured yet."}
        )
        status = {
            "findmysync": findmysync_status,
            "working_path": {
                "status": "ok",
                "source": "OpenClaw local Python exporter plus patched FindMySync sender",
            },
        }
        if STATUS_PATH.exists():
            try:
                status.update(json.loads(STATUS_PATH.read_text(encoding="utf-8")))
            except Exception:
                pass

        status_class = "ok" if event_count else "blocked"
        status_label = "FindMySync: funktioniert" if event_count else "FindMySync: wartet"
        status_text = (
            "FindMySync sendet lokale Events an den Receiver. Exakte Standortdaten bleiben nur in der privaten Capture-Datei."
            if event_count
            else "FindMySync ist installiert und der lokale Receiver läuft, aber es wurden noch keine Events empfangen."
        )

        html = f"""<!doctype html>
<html lang="de">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Find My Sync Teststatus</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 32px; line-height: 1.45; background: #101214; color: #f2f4f7; }}
main {{ max-width: 860px; margin: 0 auto; }}
.panel {{ border: 1px solid #2d333b; border-radius: 8px; padding: 18px; margin: 14px 0; background: #171a1f; }}
.ok {{ color: #53d769; }}
.blocked {{ color: #ffcc66; }}
code, pre {{ background: #0b0d10; border-radius: 6px; padding: 2px 5px; }}
pre {{ padding: 14px; overflow: auto; }}
</style>
<main>
  <h1>Find My Teststatus</h1>
  <section class="panel">
    <h2 class="{status_class}">{status_label}</h2>
    <p>{status_text}</p>
    <p>Empfangene FindMySync-POSTs: <strong>{event_count}</strong></p>
  </section>
  <section class="panel">
    <h2 class="ok">Funktionierender Pfad</h2>
    <p>Die Daten kommen aus dem lokalen Python-Exporter und werden über FindMySync an diesen lokalen Endpoint geschickt.</p>
  </section>
  <section class="panel">
    <h2>Zusammenfassung</h2>
    <pre>{json.dumps(status, ensure_ascii=False, indent=2)}</pre>
  </section>
</main>
</html>
"""
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(length)
        received_at = dt.datetime.now(dt.timezone.utc).isoformat()

        try:
            payload = json.loads(raw.decode("utf-8"))
        except Exception:
            payload = {"_raw_text": raw.decode("utf-8", errors="replace")}

        STATE_DIR.mkdir(parents=True, exist_ok=True)
        with EVENTS_PATH.open("a", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {
                        "received_at": received_at,
                        "path": self.path,
                        "headers": {
                            "authorization_present": bool(
                                self.headers.get("Authorization")
                            ),
                            "content_type": self.headers.get("Content-Type"),
                        },
                        "payload": payload,
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                + "\n"
            )

        print(json.dumps({"received_at": received_at, **summarize(payload)}))
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"ok":true}\n')

    def log_message(self, fmt: str, *args: Any) -> None:
        return


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"listening http://{args.host}:{args.port}/findmysync")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
