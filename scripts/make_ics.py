#!/usr/bin/env python3
"""Generate an ICS file for testing the doorplate-diy sync path.

Usage (from the command line, JSON stdin):
    echo '{"name":"work","events":[{"time":"09:00","title":"Standup"}]}' \
      | python3 /tmp/make_ics.py

Or import and call:
    from make_ics import write_ics
    write_ics("work", [{"time": "09:00", "title": "Standup"}])

Each call writes /tmp/<name>.ics served by the already-running
`python -m http.server 5556` in /tmp, so events appear immediately at
http://localhost:5556/<name>.ics
"""

from __future__ import annotations

import json
import sys
import uuid
from datetime import datetime, timedelta


def _event(time_hhmm: str, title: str, date_iso: str | None = None, duration_min: int = 30) -> str:
    """Build a VEVENT block for a given HH:MM time on today (or given date)."""
    d = datetime.fromisoformat(date_iso) if date_iso else datetime.now().astimezone()
    hh, mm = (int(p) for p in time_hhmm.split(":"))
    start = d.replace(hour=hh, minute=mm, second=0, microsecond=0).astimezone()
    end = start + timedelta(minutes=duration_min)
    # Format as local time with TZID not set — icalendar parses these as floating,
    # which our server treats as local. Simple and works for dev.
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


def main() -> int:
    payload = json.load(sys.stdin)
    name = payload.get("name", "demo")
    events = payload.get("events") or []
    cal_name = payload.get("cal_name") or name
    url = write_ics(name, events, cal_name)
    print(url)
    return 0


if __name__ == "__main__":
    sys.exit(main())
