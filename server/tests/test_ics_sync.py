import sys
from datetime import date, datetime, timedelta, UTC
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ics_sync  # noqa: E402


def _ics(events: list[str]) -> bytes:
    body = "\n".join(events)
    return (
        "BEGIN:VCALENDAR\r\n"
        "VERSION:2.0\r\n"
        "PRODID:-//doorplate-diy//test//EN\r\n"
        f"{body}\r\n"
        "END:VCALENDAR\r\n"
    ).encode()


def _vevent(uid: str, dtstart: datetime, summary: str, extra: str = "") -> str:
    fmt = (
        dtstart.strftime("%Y%m%dT%H%M%SZ") if dtstart.tzinfo else dtstart.strftime("%Y%m%dT%H%M%S")
    )
    return (
        "BEGIN:VEVENT\r\n"
        f"UID:{uid}\r\n"
        f"DTSTART:{fmt}\r\n"
        f"SUMMARY:{summary}\r\n"
        f"{extra}"
        "END:VEVENT"
    )


def test_parse_events_today_filters_to_today():
    today = date(2026, 4, 17)
    now_today = datetime(2026, 4, 17, 10, 0, tzinfo=UTC)
    yesterday = datetime(2026, 4, 16, 10, 0, tzinfo=UTC)
    tomorrow = datetime(2026, 4, 18, 10, 0, tzinfo=UTC)

    ics = _ics(
        [
            _vevent("a", yesterday, "Old meeting"),
            _vevent("b", now_today, "Today meeting"),
            _vevent("c", tomorrow, "Future meeting"),
        ]
    )
    events = ics_sync.parse_events_today(ics, today=today)
    titles = [e["title"] for e in events]
    assert titles == ["Today meeting"]


def test_parse_events_today_skips_all_day():
    today = date(2026, 4, 17)
    all_day_line = (
        "BEGIN:VEVENT\r\n"
        "UID:allday\r\n"
        "DTSTART;VALUE=DATE:20260417\r\n"
        "SUMMARY:Company holiday\r\n"
        "END:VEVENT"
    )
    timed = _vevent("t", datetime(2026, 4, 17, 14, 0, tzinfo=UTC), "Timed")
    ics = _ics([all_day_line, timed])
    events = ics_sync.parse_events_today(ics, today=today)
    assert [e["title"] for e in events] == ["Timed"]


def test_parse_events_today_sorts_by_time():
    today = date(2026, 4, 17)
    late = _vevent("late", datetime(2026, 4, 17, 16, 0, tzinfo=UTC), "Afternoon")
    early = _vevent("early", datetime(2026, 4, 17, 9, 0, tzinfo=UTC), "Morning")
    ics = _ics([late, early])
    events = ics_sync.parse_events_today(ics, today=today)
    assert [e["title"] for e in events] == ["Morning", "Afternoon"]


def test_parse_events_today_expands_recurring():
    today = date(2026, 4, 17)
    # Weekly recurring event, started a week ago
    started = datetime(2026, 4, 10, 10, 0, tzinfo=UTC)
    recurring = _vevent(
        "weekly",
        started,
        "Standup",
        extra="RRULE:FREQ=WEEKLY;COUNT=10\r\n",
    )
    ics = _ics([recurring])
    events = ics_sync.parse_events_today(ics, today=today)
    # Today is exactly 7 days after start, so one occurrence should appear
    assert any(e["title"] == "Standup" for e in events)


def test_sync_source_success():
    today = date(2026, 4, 17)
    ics_bytes = _ics([_vevent("a", datetime(2026, 4, 17, 9, 0, tzinfo=UTC), "Standup")])
    events, error = ics_sync.sync_source(
        "work", "https://example.test/a.ics", today=today, fetcher=lambda url: ics_bytes
    )
    assert error is None
    assert len(events) == 1
    assert events[0]["source"] == "work"
    assert events[0]["synced"] is True


def test_sync_source_handles_fetch_failure():
    def boom(url):
        raise OSError("connection refused")

    events, error = ics_sync.sync_source("work", "https://example.test/x.ics", fetcher=boom)
    assert events == []
    assert error is not None
    assert "Network error" in error


def test_sync_source_handles_parse_failure():
    events, error = ics_sync.sync_source(
        "work",
        "https://example.test/x.ics",
        fetcher=lambda url: b"not a calendar",
    )
    assert events == []
    assert error is not None
    assert "parse" in error.lower()


def test_sync_worker_poll_once_updates_state(monkeypatch):
    # Build an ICS file with an event dated today so it survives the filter.
    today_dt = datetime.now().astimezone().replace(hour=9, minute=0, second=0, microsecond=0)
    sample = _ics([_vevent("a", today_dt.astimezone(UTC), "Standup")])

    calls = []

    def fake_fetch(url, timeout=15):
        calls.append(url)
        return sample

    monkeypatch.setattr(ics_sync, "fetch_ics", fake_fetch)

    state = {
        "sources": {
            "work": {
                "label": "Work",
                "accent": "#0091ea",
                "short": "W",
                "ics_url": "https://example.test/w.ics",
            }
        },
        "synced_schedule": {},
    }
    stored = {}

    worker = ics_sync.SyncWorker(lambda: state, lambda s: stored.update(s), interval=3600)
    worker.poll_once()

    assert calls == ["https://example.test/w.ics"]
    assert "work" in stored["synced_schedule"]
    assert stored["sources"]["work"]["last_synced"] is not None
    assert stored["sources"]["work"]["last_sync_error"] is None


def test_sync_worker_clears_synced_for_removed_sources():
    state = {
        "sources": {},  # source was deleted
        "synced_schedule": {"orphan": [{"time": "09:00", "title": "X", "source": "orphan"}]},
    }
    stored = {}
    worker = ics_sync.SyncWorker(lambda: state, lambda s: stored.update(s), interval=3600)
    worker.poll_once()
    assert stored["synced_schedule"] == {}


def test_sync_worker_records_error_on_fetch_failure(monkeypatch):
    def boom(url, timeout=15):
        raise OSError("connection refused")

    monkeypatch.setattr(ics_sync, "fetch_ics", boom)
    state = {
        "sources": {
            "work": {
                "label": "Work",
                "accent": "#0091ea",
                "short": "W",
                "ics_url": "https://example.test/w.ics",
            }
        },
        "synced_schedule": {},
    }
    stored = {}
    worker = ics_sync.SyncWorker(lambda: state, lambda s: stored.update(s), interval=3600)
    worker.poll_once()
    assert stored["sources"]["work"]["last_sync_error"] is not None
    assert stored["synced_schedule"]["work"] == []


def test_sync_worker_construct_does_not_start_thread():
    worker = ics_sync.SyncWorker(lambda: {}, lambda s: None, interval=1)
    assert worker._thread is None


_ = timedelta  # placeholder for future tests


# ---------- robustness: URL normalization + error classification ----------


def test_normalize_url_converts_webcal():
    assert ics_sync.normalize_url("webcal://example.test/c.ics") == "https://example.test/c.ics"
    assert ics_sync.normalize_url("webcals://example.test/c.ics") == "https://example.test/c.ics"
    assert ics_sync.normalize_url("https://example.test/c.ics") == "https://example.test/c.ics"
    assert ics_sync.normalize_url("  webcal://a.test/c.ics  ") == "https://a.test/c.ics"
    assert ics_sync.normalize_url("") == ""


def test_classify_response_404_message_is_actionable():
    msg = ics_sync._classify_response(404, b"")
    assert msg is not None
    assert "404" in msg
    assert "token was rotated" in msg or "regenerate" in msg.lower()


def test_classify_response_403_mentions_secret_vs_public():
    msg = ics_sync._classify_response(403, b"")
    assert msg is not None
    assert "Secret" in msg or "secret" in msg


def test_classify_response_500_suggests_upstream_issue():
    msg = ics_sync._classify_response(500, b"")
    assert msg is not None and "500" in msg


def test_classify_response_html_body_detected():
    for head in (b"<!DOCTYPE html><html>...", b"<html><head>...", b"<?xml version='1.0'?>"):
        msg = ics_sync._classify_response(200, head)
        assert msg is not None
        assert "HTML" in msg or "login" in msg.lower()


def test_classify_response_missing_vcalendar_header():
    msg = ics_sync._classify_response(200, b"just some random bytes, no ICS here")
    assert msg is not None
    assert "BEGIN:VCALENDAR" in msg or "iCalendar" in msg


def test_classify_response_valid_ics_passes():
    body = b"BEGIN:VCALENDAR\r\nVERSION:2.0\r\nEND:VCALENDAR\r\n"
    assert ics_sync._classify_response(200, body) is None


def test_sync_source_returns_friendly_404_message(monkeypatch):
    def fake_fetcher(url):
        raise ics_sync.IcsError(
            "Server returned 404 — URL is wrong or the calendar's secret token was rotated."
        )

    events, error = ics_sync.sync_source(
        "work", "https://example.test/bad.ics", fetcher=fake_fetcher
    )
    assert events == []
    assert error is not None
    assert "404" in error


# ---------- multi-room ----------


def test_sync_worker_iterates_all_rooms(monkeypatch):
    today_dt = datetime.now().astimezone().replace(hour=9, minute=0, second=0, microsecond=0)
    sample = _ics([_vevent("a", today_dt.astimezone(UTC), "Meeting")])

    fetched = []

    def fake_fetch(url, timeout=15):
        fetched.append(url)
        return sample

    monkeypatch.setattr(ics_sync, "fetch_ics", fake_fetch)

    state = {
        "rooms": {
            "default": {
                "sources": {
                    "work": {
                        "label": "Work",
                        "accent": "#0091ea",
                        "short": "W",
                        "ics_url": "https://example.test/default.ics",
                    }
                },
                "synced_schedule": {},
            },
            "acorn": {
                "sources": {
                    "cal": {
                        "label": "Acorn Cal",
                        "accent": "#2e7d32",
                        "short": "A",
                        "ics_url": "https://example.test/acorn.ics",
                    }
                },
                "synced_schedule": {},
            },
        }
    }
    stored = {}
    worker = ics_sync.SyncWorker(lambda: state, lambda s: stored.update(s), interval=3600)
    worker.poll_once()

    assert sorted(fetched) == [
        "https://example.test/acorn.ics",
        "https://example.test/default.ics",
    ]
    assert "work" in stored["rooms"]["default"]["synced_schedule"]
    assert "cal" in stored["rooms"]["acorn"]["synced_schedule"]
