#!/usr/bin/env python3
"""Generate / publish ICS feeds for testing the doorplate-diy sync path.

Two modes:

1. **Publish to the doorplate server** (recommended — one server to run):

       echo '{"name":"work","events":[{"time":"09:00","title":"Standup"}]}' \
         | python3 scripts/make_ics.py --publish

   Posts the events to POST /ics/<name>, served back as
   http://<server>/ics/<name>.ics. No separate http.server needed.
   Override the target with `--server http://host:port`. Auth via
   env var DOORPLATE_TOKEN if the server requires it.

2. **Write a local .ics file** (for use with `python -m http.server`):

       echo '{"name":"work","events":[{"time":"09:00","title":"Standup"}]}' \
         | python3 scripts/make_ics.py

   Writes /tmp/<name>.ics — serve it via `python -m http.server 5556` in
   /tmp, then point a source at http://localhost:5556/<name>.ics.

Event fields: `time` (HH:MM, required), `title` (required),
`duration_min` (default 30), `date` (ISO date, default today).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timedelta


def _event(time_hhmm: str, title: str, date_iso: str | None = None, duration_min: int = 30) -> str:
    """Build a VEVENT block for a given HH:MM time on today (or given date)."""
    d = datetime.fromisoformat(date_iso) if date_iso else datetime.now().astimezone()
    hh, mm = (int(p) for p in time_hhmm.split(":"))
    start = d.replace(hour=hh, minute=mm, second=0, microsecond=0).astimezone()
    end = start + timedelta(minutes=duration_min)
    fmt = "%Y%m%dT%H%M%S"
    return (
        "BEGIN:VEVENT\r\n"
        f"UID:{uuid.uuid4()}@doorplate-diy-demo\r\n"
        f"DTSTART:{start.strftime(fmt)}\r\n"
        f"DTEND:{end.strftime(fmt)}\r\n"
        f"SUMMARY:{title}\r\n"
        "END:VEVENT"
    )


def build_ics(events: list[dict], cal_name: str = "Demo") -> str:
    blocks = [
        _event(
            e["time"],
            e["title"],
            date_iso=e.get("date"),
            duration_min=int(e.get("duration_min", 30)),
        )
        for e in events
    ]
    body = "\r\n".join(blocks)
    return (
        "BEGIN:VCALENDAR\r\n"
        "VERSION:2.0\r\n"
        "PRODID:-//doorplate-diy//make_ics//EN\r\n"
        f"X-WR-CALNAME:{cal_name}\r\n"
        f"{body}\r\n"
        "END:VCALENDAR\r\n"
    )


def write_ics(name: str, events: list[dict], cal_name: str | None = None) -> str:
    """Write /tmp/<name>.ics and return the local URL."""
    path = f"/tmp/{name}.ics"
    with open(path, "w", encoding="utf-8") as f:
        f.write(build_ics(events, cal_name or name))
    return f"http://localhost:5556/{name}.ics"


def publish_ics(
    name: str,
    events: list[dict],
    server: str,
    cal_name: str | None = None,
    token: str | None = None,
) -> str:
    """POST events to doorplate's /ics/<name> endpoint, return the served URL."""
    server = server.rstrip("/")
    payload = json.dumps({"events": events, "cal_name": cal_name or name}).encode()
    req = urllib.request.Request(
        f"{server}/ics/{name}",
        data=payload,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    if token:
        req.add_header("X-Doorplate-Token", token)
    with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310 — local dev
        data = json.loads(resp.read())
    return data["url"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--publish",
        action="store_true",
        help="POST to the doorplate server instead of writing a local /tmp file.",
    )
    parser.add_argument(
        "--server",
        default=os.environ.get("DOORPLATE_SERVER", "http://localhost:5000"),
        help="Doorplate server URL (default: $DOORPLATE_SERVER or http://localhost:5000).",
    )
    args = parser.parse_args(argv)

    payload = json.load(sys.stdin)
    name = payload.get("name", "demo")
    events = payload.get("events") or []
    cal_name = payload.get("cal_name") or name

    if args.publish:
        try:
            url = publish_ics(
                name,
                events,
                server=args.server,
                cal_name=cal_name,
                token=os.environ.get("DOORPLATE_TOKEN"),
            )
        except urllib.error.HTTPError as e:
            body = (e.read() or b"").decode(errors="replace")
            print(f"publish failed: HTTP {e.code} — {body}", file=sys.stderr)
            return 2
        except (urllib.error.URLError, OSError) as e:
            print(f"publish failed: {e}", file=sys.stderr)
            return 2
    else:
        url = write_ics(name, events, cal_name)
    print(url)
    return 0


if __name__ == "__main__":
    sys.exit(main())
