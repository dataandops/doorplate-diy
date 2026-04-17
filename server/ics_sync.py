"""ICS (iCalendar) subscription sync.

Polls ICS URLs attached to sources and converts today's events into
schedule rows. Pure functions + a simple threaded worker; no Flask
dependency so it's straightforward to unit-test.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import icalendar
import recurring_ical_events

logger = logging.getLogger("doorplate.ics")

FETCH_TIMEOUT = 15
DEFAULT_POLL_INTERVAL = 600  # 10 minutes

# Browser-like UA avoids Google Calendar's bot filter that sometimes 404s
# private-ICS endpoints for non-browser clients.
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.0 Safari/605.1.15 doorplate-diy/1.0"
)


class IcsError(Exception):
    """Raised when an ICS URL can't be turned into events. Message is user-safe."""


def normalize_url(url: str) -> str:
    """Convert webcal:// to https:// (calendar apps commonly hand out webcal URLs)."""
    url = (url or "").strip()
    if url.startswith("webcal://"):
        return "https://" + url[len("webcal://") :]
    if url.startswith("webcals://"):
        return "https://" + url[len("webcals://") :]
    return url


def _classify_response(status: int, body_head: bytes) -> str | None:
    """Return an actionable error message, or None if the response looks OK."""
    if status == 401 or status == 403:
        return (
            f"Server returned {status} — the URL needs auth. For Google Calendar, "
            "use the 'Secret address in iCal format', not the 'Public address'."
        )
    if status == 404:
        return (
            "Server returned 404 — URL is wrong or the calendar's secret token "
            "was rotated. Regenerate it in Google Calendar Settings → Integrate "
            "calendar, then paste the fresh URL."
        )
    if status == 429:
        return "Server returned 429 — rate-limited. The next auto-poll will retry."
    if status >= 500:
        return f"Server returned {status} — upstream calendar service is having a moment."
    if status >= 400:
        return f"Server returned {status}. Double-check the URL."
    # 2xx: sanity-check we actually got ICS, not an HTML login page.
    head = body_head.lstrip().upper()
    if head.startswith(b"<!DOCTYPE") or head.startswith(b"<HTML") or head.startswith(b"<?XML"):
        return (
            "Server returned an HTML page, not an ICS file. The URL likely "
            "points at a login/consent screen — use the private/secret iCal "
            "URL from your calendar's export settings."
        )
    if b"BEGIN:VCALENDAR" not in head[:256]:
        return "Response doesn't look like an iCalendar file (no BEGIN:VCALENDAR header)."
    return None


def fetch_ics(url: str, timeout: int = FETCH_TIMEOUT) -> bytes:
    """Fetch an ICS URL with diagnostic errors.

    Raises:
        IcsError: with a user-friendly message for any non-OK state (404, HTML,
            timeout, etc.). Original exception text is appended to server logs.
    """
    url = normalize_url(url)
    req = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/calendar, */*"})
    try:
        with urlopen(req, timeout=timeout) as resp:  # noqa: S310 — user-provided URL by design
            body = resp.read()
            status = resp.status
    except HTTPError as e:
        # HTTPError exposes status + partial body
        body = e.read() or b""
        msg = _classify_response(e.code, body[:512]) or f"HTTP {e.code} {e.reason}"
        raise IcsError(msg) from e
    except (URLError, TimeoutError, OSError) as e:
        raise IcsError(f"Network error: {e}") from e

    err = _classify_response(status, body[:512])
    if err:
        logger.warning("ICS fetch classified error for %s: %s", url, err)
        raise IcsError(err)
    return body


def parse_events_today(
    ics_bytes: bytes,
    today: date | None = None,
) -> list[dict[str, str]]:
    """Parse ICS bytes and return today's events as [{time, title}] sorted by time.

    - Recurring events are expanded via recurring_ical_events.
    - All-day events are skipped (no sensible `HH:MM` to render).
    - Floating-timezone events are interpreted as local time.
    """
    cal = icalendar.Calendar.from_ical(ics_bytes)
    today = today or datetime.now().astimezone().date()
    start = datetime.combine(today, datetime.min.time()).astimezone()
    end = start + timedelta(days=1)

    events = recurring_ical_events.of(cal).between(start, end)
    out: list[dict[str, str]] = []
    for ev in events:
        dtstart_raw = ev.get("DTSTART")
        if dtstart_raw is None:
            continue
        dtstart = dtstart_raw.dt
        # All-day events: dtstart is a `date`, not `datetime`. Skip.
        if not isinstance(dtstart, datetime):
            continue
        # Floating (naive) → treat as local time.
        if dtstart.tzinfo is None:
            dtstart = dtstart.astimezone()
        local = dtstart.astimezone()
        summary = str(ev.get("SUMMARY", "") or "").strip()
        if not summary:
            continue
        out.append({"time": local.strftime("%H:%M"), "title": summary})

    out.sort(key=lambda x: x["time"])
    return out


def sync_source(
    source_key: str,
    ics_url: str,
    today: date | None = None,
    fetcher: Callable[[str], bytes] | None = None,
) -> tuple[list[dict[str, str]], str | None]:
    """Fetch + parse one source's ICS feed.

    Returns `(events, error)` where `events` carries `source=source_key`
    and `synced=True`, and `error` is None on success or a short error
    string on failure. `fetcher` resolves at call time so tests can
    monkeypatch `ics_sync.fetch_ics`.
    """
    if fetcher is None:
        fetcher = fetch_ics
    try:
        raw = fetcher(ics_url)
    except IcsError as e:
        return [], str(e)
    except (URLError, TimeoutError, OSError) as e:
        return [], f"Network error: {e}"
    try:
        events = parse_events_today(raw, today=today)
    except Exception as e:  # noqa: BLE001 — ICS parsing libs raise a zoo of exceptions
        return [], f"Couldn't parse ICS: {e}"
    for ev in events:
        ev["source"] = source_key
        ev["synced"] = True
    return events, None


class SyncWorker:
    """Daemon-thread worker that polls all sources with an `ics_url` periodically.

    The worker is intentionally naive: one pass every `interval` seconds, all
    sources sequentially. For v1 this is fine — a handful of sources take
    seconds to fetch. We can revisit with per-source cadence or async later.
    """

    def __init__(
        self,
        load_state: Callable[[], dict[str, Any]],
        save_state: Callable[[dict[str, Any]], None],
        interval: int = DEFAULT_POLL_INTERVAL,
    ) -> None:
        self.load_state = load_state
        self.save_state = save_state
        self.interval = interval
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="ics-sync")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        # First pass runs immediately so users don't wait `interval` seconds.
        while not self._stop.is_set():
            try:
                self.poll_once()
            except Exception:  # noqa: BLE001 — never let the worker die
                logger.exception("ICS poll pass raised")
            self._stop.wait(self.interval)

    def poll_once(self) -> None:
        """Run one full poll pass: sync every source with an ics_url, save state."""
        state = self.load_state()
        sources = state.get("sources") or {}
        synced_schedule = state.get("synced_schedule") or {}
        changed = False

        # Drop synced entries whose source was deleted or lost its URL.
        for key in list(synced_schedule):
            cfg = sources.get(key) or {}
            if key not in sources or not cfg.get("ics_url"):
                synced_schedule.pop(key, None)
                changed = True

        # Fetch each configured URL.
        for key, cfg in sources.items():
            ics_url = (cfg or {}).get("ics_url", "")
            if not ics_url:
                continue
            events, error = sync_source(key, ics_url)
            synced_schedule[key] = events
            cfg["last_synced"] = datetime.now(UTC).isoformat(timespec="seconds")
            cfg["last_sync_error"] = error
            changed = True

        if changed:
            state["synced_schedule"] = synced_schedule
            state["sources"] = sources
            self.save_state(state)
