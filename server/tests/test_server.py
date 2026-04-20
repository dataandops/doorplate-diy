import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import server as server_module  # noqa: E402


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(server_module, "DATA_FILE", tmp_path / "sign_data.json")
    monkeypatch.setattr(server_module, "ICS_DIR", tmp_path / "ics")
    monkeypatch.delenv("DOORPLATE_TOKEN", raising=False)
    app = server_module.create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


@pytest.fixture
def auth_client(tmp_path, monkeypatch):
    monkeypatch.setattr(server_module, "DATA_FILE", tmp_path / "sign_data.json")
    monkeypatch.setattr(server_module, "ICS_DIR", tmp_path / "ics")
    monkeypatch.setenv("DOORPLATE_TOKEN", "s3cret")
    app = server_module.create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_status_returns_defaults(client):
    res = client.get("/status")
    assert res.status_code == 200
    data = res.get_json()
    assert data["room_name"] == "Meeting Room"
    assert data["available"] is True
    assert data["schedule"] == []
    assert data["schedule_display"] == []
    assert isinstance(data["joke_q"], str) and data["joke_q"]
    assert isinstance(data["joke_a"], str) and data["joke_a"]
    assert data["last_updated"] is None
    # new fields
    assert data["mode"] == "meeting_room"
    assert data["status_label"] == "AVAILABLE"
    assert data["status_animation"] == "none"
    assert data["time_format"] == "relative"
    assert data["time_display"] == "not pushed yet"
    assert data["sources"] == {}


def test_update_persists(client):
    res = client.post("/update", json={"room_name": "Lab A", "available": False})
    assert res.status_code == 200

    res = client.get("/status")
    data = res.get_json()
    assert data["room_name"] == "Lab A"
    assert data["available"] is False
    assert data["last_updated"] is not None


def test_update_new_joke_rotates(client):
    first = client.post("/update", json={"new_joke": True}).get_json()
    second = client.post("/update", json={"new_joke": True}).get_json()
    assert first["joke_q"] != second["joke_q"]


def test_update_validates_required_fields(client):
    assert client.post("/update", json={"room_name": 123}).status_code == 400
    assert client.post("/update", json={"available": "yes"}).status_code == 400
    assert client.post("/update", json={"schedule": "not a list"}).status_code == 400
    assert client.post("/update", json={"schedule": [{"time": "09:00"}]}).status_code == 400


def test_schedule_round_trip(client):
    payload = {
        "schedule": [{"time": "09:00", "title": "Standup"}, {"time": "10:30", "title": "Design"}]
    }
    client.post("/update", json=payload)

    data = client.get("/status").get_json()
    assert data["schedule"] == payload["schedule"]
    # Default time_format is relative → schedule uses 24h
    assert data["schedule_display"] == ["09:00  Standup", "10:30  Design"]


def test_schedule_display_12h_formats_times(client):
    client.post(
        "/update",
        json={
            "time_format": "12h",
            "schedule": [
                {"time": "09:00", "title": "Morning"},
                {"time": "14:30", "title": "Afternoon"},
                {"time": "00:15", "title": "Midnight-ish"},
            ],
        },
    )
    data = client.get("/status").get_json()
    assert data["schedule_display"] == [
        "12:15 AM  Midnight-ish",
        "9:00 AM  Morning",
        "2:30 PM  Afternoon",
    ]


def test_schedule_display_24h_stays_hhmm(client):
    client.post(
        "/update",
        json={
            "time_format": "24h",
            "schedule": [{"time": "14:30", "title": "Afternoon"}],
        },
    )
    data = client.get("/status").get_json()
    assert data["schedule_display"] == ["14:30  Afternoon"]


def test_schedule_display_relative_keeps_24h_for_meetings(client):
    """Relative / iso / off only affect the footer; meetings stay 24h."""
    client.post(
        "/update",
        json={
            "time_format": "relative",
            "schedule": [{"time": "14:30", "title": "Afternoon"}],
        },
    )
    data = client.get("/status").get_json()
    assert data["schedule_display"] == ["14:30  Afternoon"]


def test_persistence_across_restart(tmp_path, monkeypatch):
    data_file = tmp_path / "sign_data.json"
    monkeypatch.setattr(server_module, "DATA_FILE", data_file)
    monkeypatch.delenv("DOORPLATE_TOKEN", raising=False)

    app1 = server_module.create_app()
    with app1.test_client() as c:
        c.post("/update", json={"room_name": "Reload Room", "available": False})

    assert data_file.exists()
    saved = json.loads(data_file.read_text())
    assert saved["rooms"]["default"]["room_name"] == "Reload Room"

    app2 = server_module.create_app()
    with app2.test_client() as c:
        data = c.get("/status").get_json()
        assert data["room_name"] == "Reload Room"
        assert data["available"] is False


def test_auth_token_enforcement(auth_client):
    missing = auth_client.post("/update", json={"room_name": "X"})
    assert missing.status_code == 401

    wrong = auth_client.post(
        "/update", json={"room_name": "X"}, headers={"X-Doorplate-Token": "nope"}
    )
    assert wrong.status_code == 401

    ok = auth_client.post(
        "/update", json={"room_name": "X"}, headers={"X-Doorplate-Token": "s3cret"}
    )
    assert ok.status_code == 200


def test_auth_disabled_when_token_unset(client):
    res = client.post("/update", json={"room_name": "anon"})
    assert res.status_code == 200


def test_themes_endpoint_lists_css_files(client):
    res = client.get("/themes")
    assert res.status_code == 200
    data = res.get_json()
    assert isinstance(data, list)
    for name in ("ink", "terminal", "newsprint"):
        assert name in data


# ---------- modes ----------


def test_status_exposes_modes_catalog(client):
    data = client.get("/status").get_json()
    keys = {m["key"] for m in data["modes"]}
    assert keys == {"meeting_room", "studio", "lab", "focus", "custom"}


def test_update_mode_studio_sets_status_label_when_busy(client):
    data = client.post("/update", json={"mode": "studio", "available": False}).get_json()
    assert data["mode"] == "studio"
    assert data["status_label"] == "ON AIR"
    assert data["status_animation"] == "pulse"
    assert data["status_accent"] == "#e60000"


def test_update_mode_free_has_no_animation(client):
    data = client.post("/update", json={"mode": "studio", "available": True}).get_json()
    assert data["status_label"] == "OFF AIR"
    assert data["status_animation"] == "none"


def test_update_mode_custom_uses_custom_labels(client):
    data = client.post(
        "/update",
        json={
            "mode": "custom",
            "available": False,
            "custom_labels": {"free": "OPEN", "busy": "FIKA IN PROGRESS"},
        },
    ).get_json()
    assert data["mode"] == "custom"
    assert data["status_label"] == "FIKA IN PROGRESS"


def test_update_invalid_mode_returns_400(client):
    res = client.post("/update", json={"mode": "nope"})
    assert res.status_code == 400


def test_update_custom_labels_length_cap_returns_400(client):
    res = client.post(
        "/update",
        json={"custom_labels": {"free": "OK", "busy": "x" * 25}},
    )
    assert res.status_code == 400


def test_update_custom_labels_empty_returns_400(client):
    res = client.post("/update", json={"custom_labels": {"free": "   ", "busy": "BUSY"}})
    assert res.status_code == 400


# ---------- time format ----------


@pytest.mark.parametrize(
    ("delta_seconds", "expected"),
    [
        (5, "just now"),
        (60, "1 min ago"),
        (150, "2 min ago"),
        (4000, "1 h ago"),
        (90000, "1 day ago"),
        (200000, "2 days ago"),
    ],
)
def test_format_time_relative(delta_seconds, expected):
    now = datetime(2026, 4, 17, 12, 0, tzinfo=UTC)
    then = (now - timedelta(seconds=delta_seconds)).isoformat(timespec="seconds")
    assert server_module._format_time(then, "relative", now=now) == expected


def test_format_time_24h_12h_iso_off():
    iso = "2026-04-17T17:08:00+00:00"
    assert server_module._format_time(iso, "iso") == iso
    assert server_module._format_time(iso, "off") == ""
    # 24h / 12h convert to local timezone; just assert format shape rather than value
    out24 = server_module._format_time(iso, "24h")
    assert len(out24) == 5 and out24[2] == ":"
    out12 = server_module._format_time(iso, "12h")
    assert out12.endswith(("AM", "PM"))


def test_format_time_handles_none():
    assert server_module._format_time(None, "relative") == "not pushed yet"
    assert server_module._format_time(None, "off") == ""


def test_update_invalid_time_format_returns_400(client):
    res = client.post("/update", json={"time_format": "yesterday"})
    assert res.status_code == 400


def test_time_format_applied_to_time_display(client):
    client.post("/update", json={"time_format": "iso"})
    data = client.get("/status").get_json()
    assert data["time_format"] == "iso"
    # last_updated was set by the previous POST, so time_display should match it
    assert data["time_display"] == data["last_updated"]


# ---------- sources ----------


def test_sources_default_empty_dict(client):
    data = client.get("/status").get_json()
    assert data["sources"] == {}


def test_update_sources_roundtrip(client):
    payload = {
        "sources": {
            "work": {"label": "Work", "accent": "#0091ea", "short": "W"},
            "personal": {"label": "Personal", "accent": "#2e7d32", "short": "P"},
        }
    }
    data = client.post("/update", json=payload).get_json()
    assert data["sources"]["work"]["label"] == "Work"
    assert data["sources"]["personal"]["accent"] == "#2e7d32"


def test_update_sources_invalid_key_returns_400(client):
    payload = {"sources": {"has spaces": {"label": "X", "accent": "#000000", "short": "X"}}}
    assert client.post("/update", json=payload).status_code == 400


def test_update_sources_invalid_accent_returns_400(client):
    payload = {"sources": {"work": {"label": "X", "accent": "blue", "short": "X"}}}
    assert client.post("/update", json=payload).status_code == 400


def test_update_sources_short_too_long_returns_400(client):
    payload = {"sources": {"work": {"label": "X", "accent": "#000000", "short": "WRK"}}}
    assert client.post("/update", json=payload).status_code == 400


def test_schedule_display_prefixes_source_short(client):
    client.post(
        "/update",
        json={
            "sources": {"work": {"label": "Work", "accent": "#0091ea", "short": "W"}},
        },
    )
    client.post(
        "/update",
        json={
            "schedule": [
                {"time": "09:00", "title": "Standup", "source": "work"},
                {"time": "10:30", "title": "Plain"},
            ]
        },
    )
    data = client.get("/status").get_json()
    assert data["schedule_display"] == ["W· 09:00  Standup", "10:30  Plain"]


def test_schedule_with_unknown_source_returns_400(client):
    res = client.post(
        "/update",
        json={"schedule": [{"time": "09:00", "title": "X", "source": "nope"}]},
    )
    assert res.status_code == 400


def test_schedule_without_source_renders_plain(client):
    # Backward compat: items without "source" render as before.
    client.post("/update", json={"schedule": [{"time": "09:00", "title": "Standup"}]})
    data = client.get("/status").get_json()
    assert data["schedule_display"] == ["09:00  Standup"]


# ---------- ICS sync integration ----------


def test_source_accepts_ics_url(client):
    payload = {
        "sources": {
            "work": {
                "label": "Work",
                "accent": "#0091ea",
                "short": "W",
                "ics_url": "https://example.test/w.ics",
            }
        }
    }
    data = client.post("/update", json=payload).get_json()
    assert data["sources"]["work"]["ics_url"] == "https://example.test/w.ics"


def test_source_rejects_bad_ics_url(client):
    payload = {
        "sources": {
            "work": {
                "label": "Work",
                "accent": "#0091ea",
                "short": "W",
                "ics_url": "javascript:alert(1)",
            }
        }
    }
    assert client.post("/update", json=payload).status_code == 400


def test_merged_schedule_sorts_manual_and_synced(client, monkeypatch):
    # Seed manual schedule + inject synced items directly into state.
    import server as srv

    client.post("/update", json={"schedule": [{"time": "14:00", "title": "Deep work"}]})
    # Write synced entries directly via the same file path.
    state = srv._load_state()
    room = state["rooms"]["default"]
    room["sources"] = {
        "work": {"label": "Work", "accent": "#0091ea", "short": "W", "ics_url": "https://x/w"},
    }
    room["synced_schedule"] = {
        "work": [
            {"time": "09:00", "title": "Standup", "source": "work", "synced": True},
            {"time": "11:30", "title": "Review", "source": "work", "synced": True},
        ]
    }
    srv._save_state(state)

    data = client.get("/status").get_json()
    times = [r["time"] for r in data["schedule"]]
    assert times == ["09:00", "11:30", "14:00"]


def test_schedule_write_drops_synced_items(client):
    """Client echoing synced items back on POST shouldn't duplicate them as manual rows."""
    client.post(
        "/update",
        json={
            "schedule": [
                {"time": "09:00", "title": "Standup", "synced": True, "source": "work"},
                {"time": "14:00", "title": "Manual"},
            ],
            "sources": {
                "work": {"label": "Work", "accent": "#0091ea", "short": "W"},
            },
        },
    )
    import server as srv

    saved = srv._load_state()
    # Only the manual row survives in the default room's schedule
    assert saved["rooms"]["default"]["schedule"] == [{"time": "14:00", "title": "Manual"}]


def test_sources_refresh_endpoint_triggers_poll(client, monkeypatch):
    import ics_sync as ics

    # Pre-seed a source with ICS URL
    client.post(
        "/update",
        json={
            "sources": {
                "work": {
                    "label": "Work",
                    "accent": "#0091ea",
                    "short": "W",
                    "ics_url": "https://example.test/w.ics",
                }
            }
        },
    )

    # Mock the fetch to return empty calendar (valid, just no events)
    monkeypatch.setattr(
        ics,
        "fetch_ics",
        lambda url, timeout=15: b"BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//t//EN\r\nEND:VCALENDAR\r\n",
    )

    res = client.post("/sources/refresh")
    assert res.status_code == 200
    data = res.get_json()
    assert data["sources"]["work"]["last_synced"] is not None
    assert data["sources"]["work"]["last_sync_error"] is None


def test_sources_refresh_requires_auth(auth_client):
    res = auth_client.post("/sources/refresh")
    assert res.status_code == 401


def test_source_accepts_webcal_url(client):
    payload = {
        "sources": {
            "apple": {
                "label": "Apple",
                "accent": "#0091ea",
                "short": "A",
                "ics_url": "webcal://example.test/c.ics",
            }
        }
    }
    assert client.post("/update", json=payload).status_code == 200


def test_sources_test_endpoint_success(client, monkeypatch):
    import ics_sync as ics

    sample = b"BEGIN:VCALENDAR\r\nVERSION:2.0\r\nEND:VCALENDAR\r\n"
    monkeypatch.setattr(ics, "fetch_ics", lambda url, timeout=15: sample)

    res = client.post("/sources/test", json={"url": "https://example.test/c.ics"})
    assert res.status_code == 200
    data = res.get_json()
    assert data["ok"] is True
    assert data["event_count"] == 0
    assert data["resolved_url"] == "https://example.test/c.ics"


def test_sources_test_endpoint_normalizes_webcal(client, monkeypatch):
    import ics_sync as ics

    captured = {}

    def fake_fetch(url, timeout=15):
        captured["url"] = url
        return b"BEGIN:VCALENDAR\r\nVERSION:2.0\r\nEND:VCALENDAR\r\n"

    monkeypatch.setattr(ics, "fetch_ics", fake_fetch)
    res = client.post("/sources/test", json={"url": "webcal://example.test/c.ics"})
    data = res.get_json()
    assert data["ok"] is True
    assert data["resolved_url"] == "https://example.test/c.ics"
    assert captured["url"] == "https://example.test/c.ics"


def test_sources_test_endpoint_returns_error_with_200(client, monkeypatch):
    """Test failures still return HTTP 200 with ok:false — easier for the UI to handle."""
    import ics_sync as ics

    def boom(url, timeout=15):
        raise ics.IcsError("Server returned 404 — URL is wrong or token rotated.")

    monkeypatch.setattr(ics, "fetch_ics", boom)
    res = client.post("/sources/test", json={"url": "https://example.test/bad.ics"})
    assert res.status_code == 200
    data = res.get_json()
    assert data["ok"] is False
    assert "404" in data["error"]


def test_sources_test_endpoint_rejects_empty_url(client):
    res = client.post("/sources/test", json={"url": ""})
    assert res.status_code == 400


def test_sources_test_endpoint_rejects_bad_scheme(client):
    res = client.post("/sources/test", json={"url": "javascript:alert(1)"})
    assert res.status_code == 400


def test_sources_test_endpoint_requires_auth(auth_client):
    res = auth_client.post("/sources/test", json={"url": "https://example.test/c.ics"})
    assert res.status_code == 401


def test_ics_publish_and_serve(client):
    payload = {
        "cal_name": "Work",
        "events": [
            {"time": "09:00", "title": "Standup", "duration_min": 15},
            {"time": "14:00", "title": "Design review"},
        ],
    }
    res = client.post("/ics/work", json=payload)
    assert res.status_code == 200
    data = res.get_json()
    assert data["ok"] is True
    assert data["event_count"] == 2
    assert data["url"].endswith("/ics/work.ics")

    # GET serves the same body back
    res = client.get("/ics/work.ics")
    assert res.status_code == 200
    assert res.headers["Content-Type"].startswith("text/calendar")
    body = res.get_data(as_text=True)
    assert "BEGIN:VCALENDAR" in body
    assert "SUMMARY:Standup" in body
    assert "SUMMARY:Design review" in body


def test_ics_publish_validates_name(client):
    res = client.post("/ics/bad name", json={"events": []})
    assert res.status_code == 400


def test_ics_publish_validates_events(client):
    res = client.post("/ics/work", json={"events": "not a list"})
    assert res.status_code == 400

    res = client.post("/ics/work", json={"events": [{"time": "09:00"}]})
    assert res.status_code == 400


def test_ics_serve_404_for_unknown(client):
    assert client.get("/ics/does-not-exist.ics").status_code == 404


def test_ics_list_returns_published_names(client):
    client.post("/ics/alpha", json={"events": [{"time": "09:00", "title": "A"}]})
    client.post("/ics/beta", json={"events": [{"time": "10:00", "title": "B"}]})
    res = client.get("/ics")
    assert res.status_code == 200
    names = res.get_json()
    assert "alpha" in names and "beta" in names


def test_ics_delete_removes_feed(client):
    client.post("/ics/gamma", json={"events": [{"time": "09:00", "title": "G"}]})
    assert client.get("/ics/gamma.ics").status_code == 200
    res = client.delete("/ics/gamma")
    assert res.status_code == 200
    assert client.get("/ics/gamma.ics").status_code == 404


def test_ics_publish_requires_auth(auth_client):
    res = auth_client.post("/ics/work", json={"events": []})
    assert res.status_code == 401


def test_ics_publish_feed_is_parseable_by_our_sync(client):
    """The feed we publish should be consumable by our own ICS sync path —
    closes the loop for dev/demo flows."""
    import ics_sync

    client.post(
        "/ics/sample",
        json={
            "events": [
                {"time": "09:00", "title": "Sample event"},
                {"time": "13:00", "title": "Another", "duration_min": 60},
            ]
        },
    )
    body = client.get("/ics/sample.ics").get_data()
    events = ics_sync.parse_events_today(body)
    titles = [e["title"] for e in events]
    assert "Sample event" in titles
    assert "Another" in titles


def test_source_removal_clears_synced_schedule(client):
    client.post(
        "/update",
        json={
            "sources": {
                "work": {
                    "label": "Work",
                    "accent": "#0091ea",
                    "short": "W",
                    "ics_url": "https://x/w",
                }
            }
        },
    )
    # Inject a synced entry
    import server as srv

    state = srv._load_state()
    state["rooms"]["default"]["synced_schedule"] = {
        "work": [{"time": "09:00", "title": "X", "source": "work", "synced": True}]
    }
    srv._save_state(state)

    # Remove the source via /update
    client.post("/update", json={"sources": {}})
    saved = srv._load_state()
    assert saved["rooms"]["default"]["synced_schedule"] == {}


# ---------- multi-room ----------


def test_default_room_exists_on_fresh_state(client):
    import server as srv

    state = srv._load_state()
    assert "rooms" in state
    assert "default" in state["rooms"]
    assert state["rooms"]["default"]["room_name"] == "Meeting Room"


def test_migrate_flat_state_wraps_under_default(tmp_path, monkeypatch):
    data_file = tmp_path / "sign_data.json"
    legacy = {
        "room_name": "Old Room",
        "available": False,
        "schedule": [{"time": "09:00", "title": "Legacy"}],
        "joke_index": 3,
        "last_updated": "2026-04-01T00:00:00+00:00",
        "mode": "studio",
        "custom_labels": {"free": "OPEN", "busy": "BUSY"},
        "time_format": "24h",
        "sources": {},
        "synced_schedule": {},
    }
    data_file.write_text(json.dumps(legacy))
    monkeypatch.setattr(server_module, "DATA_FILE", data_file)
    monkeypatch.delenv("DOORPLATE_TOKEN", raising=False)

    state = server_module._load_state()
    assert "rooms" in state
    assert state["rooms"]["default"]["room_name"] == "Old Room"
    assert state["rooms"]["default"]["mode"] == "studio"
    assert state["rooms"]["default"]["schedule"] == [{"time": "09:00", "title": "Legacy"}]


def test_status_alias_returns_default_room(client):
    client.post("/update", json={"room_name": "Alias Room"})
    legacy = client.get("/status").get_json()
    by_id = client.get("/status/default").get_json()
    assert legacy["room_name"] == "Alias Room"
    assert by_id["room_name"] == "Alias Room"


def test_status_by_room_id_returns_that_room(client):
    client.post("/rooms", json={"room_id": "acorn", "room_name": "Acorn"})
    data = client.get("/status/acorn").get_json()
    assert data["room_name"] == "Acorn"


def test_unknown_room_returns_404(client):
    res = client.get("/status/nope")
    assert res.status_code == 404


def test_create_room_succeeds(client):
    res = client.post("/rooms", json={"room_id": "acorn", "room_name": "Acorn"})
    assert res.status_code == 201
    data = res.get_json()
    assert data == {"id": "acorn", "room_name": "Acorn"}

    rooms = client.get("/rooms").get_json()
    ids = [r["id"] for r in rooms]
    assert "default" in ids and "acorn" in ids


def test_create_room_rejects_invalid_id(client):
    for bad in ("Has Space", "UPPER", "a" * 33, "", "bad!"):
        res = client.post("/rooms", json={"room_id": bad, "room_name": "X"})
        assert res.status_code == 400, f"expected 400 for {bad!r}"


def test_create_room_rejects_duplicate(client):
    client.post("/rooms", json={"room_id": "acorn", "room_name": "Acorn"})
    res = client.post("/rooms", json={"room_id": "acorn", "room_name": "Acorn 2"})
    assert res.status_code == 409


def test_delete_room_succeeds(client):
    client.post("/rooms", json={"room_id": "acorn", "room_name": "Acorn"})
    res = client.delete("/rooms/acorn")
    assert res.status_code == 200
    assert client.get("/status/acorn").status_code == 404


def test_delete_default_room_returns_400(client):
    res = client.delete("/rooms/default")
    assert res.status_code == 400


def test_delete_unknown_room_returns_404(client):
    res = client.delete("/rooms/ghost")
    assert res.status_code == 404


def test_list_rooms_returns_id_and_name(client):
    client.post("/rooms", json={"room_id": "acorn", "room_name": "Acorn"})
    rooms = client.get("/rooms").get_json()
    assert isinstance(rooms, list)
    for r in rooms:
        assert {"id", "room_name"} <= set(r)


def test_update_room_isolates_changes(client):
    client.post("/rooms", json={"room_id": "acorn", "room_name": "Acorn"})
    client.post("/update/acorn", json={"room_name": "Acorn Renamed", "available": False})

    default_state = client.get("/status").get_json()
    acorn_state = client.get("/status/acorn").get_json()
    assert default_state["room_name"] == "Meeting Room"
    assert default_state["available"] is True
    assert acorn_state["room_name"] == "Acorn Renamed"
    assert acorn_state["available"] is False


def test_room_ids_must_match_regex(client):
    res = client.get("/status/Has%20Space")
    assert res.status_code in (400, 404)
    res = client.post("/update/BADID", json={"room_name": "x"})
    assert res.status_code == 400


def test_rooms_create_requires_auth(auth_client):
    res = auth_client.post("/rooms", json={"room_id": "acorn", "room_name": "Acorn"})
    assert res.status_code == 401


def test_rooms_delete_requires_auth(auth_client):
    # seed via authed request
    ok = auth_client.post(
        "/rooms",
        json={"room_id": "acorn", "room_name": "Acorn"},
        headers={"X-Doorplate-Token": "s3cret"},
    )
    assert ok.status_code == 201
    res = auth_client.delete("/rooms/acorn")
    assert res.status_code == 401


# ---------- dashboard + per-room theme ----------


def test_root_serves_dashboard(client):
    res = client.get("/")
    assert res.status_code == 200
    body = res.get_data(as_text=True)
    assert "Welcome" in body or "dashboard" in body.lower()


def test_room_route_serves_control_panel(client):
    res = client.get("/room/default")
    assert res.status_code == 200
    body = res.get_data(as_text=True)
    # The control panel HTML page contains "Live Placard Preview".
    assert "Live Placard Preview" in body or "placard" in body.lower()


def test_room_route_serves_for_unknown_room(client):
    # Page should still load — the client handles missing-room toasting.
    res = client.get("/room/ghost")
    assert res.status_code == 200


def test_default_theme_is_ink(client):
    data = client.get("/status").get_json()
    assert data["theme"] == "ink"


def test_update_theme_persists(client):
    res = client.post("/update", json={"theme": "terminal"})
    assert res.status_code == 200
    assert res.get_json()["theme"] == "terminal"
    again = client.get("/status").get_json()
    assert again["theme"] == "terminal"


def test_update_invalid_theme_returns_400(client):
    res = client.post("/update", json={"theme": "nope"})
    assert res.status_code == 400


def test_update_theme_rejects_bad_format(client):
    for bad in ("UPPER", "has space", "../etc", "a" * 33):
        res = client.post("/update", json={"theme": bad})
        assert res.status_code == 400, f"expected 400 for {bad!r}"


def test_rooms_list_includes_theme_and_available(client):
    client.post("/rooms", json={"room_id": "acorn", "room_name": "Acorn"})
    rooms = client.get("/rooms").get_json()
    by_id = {r["id"]: r for r in rooms}
    assert by_id["default"]["theme"] == "ink"
    assert by_id["default"]["available"] is True
    assert by_id["acorn"]["theme"] == "ink"


def test_legacy_state_gets_default_theme(tmp_path, monkeypatch):
    data_file = tmp_path / "sign_data.json"
    legacy = {
        "room_name": "Old",
        "available": True,
        "schedule": [],
        "synced_schedule": {},
        "joke_index": 0,
        "last_updated": None,
        "mode": "meeting_room",
        "custom_labels": {"free": "AVAILABLE", "busy": "IN USE"},
        "time_format": "relative",
        "sources": {},
    }
    data_file.write_text(json.dumps(legacy))
    monkeypatch.setattr(server_module, "DATA_FILE", data_file)
    state = server_module._load_state()
    assert state["rooms"]["default"]["theme"] == "ink"


# ---------- archive (soft delete) ----------


def test_archive_room_sets_flag(client):
    client.post("/rooms", json={"room_id": "acorn", "room_name": "Acorn"})
    res = client.post("/rooms/acorn/archive")
    assert res.status_code == 200
    assert res.get_json() == {"id": "acorn", "archived": True}


def test_archive_excludes_room_from_default_list(client):
    client.post("/rooms", json={"room_id": "acorn", "room_name": "Acorn"})
    client.post("/rooms/acorn/archive")
    rooms = client.get("/rooms").get_json()
    assert all(r["id"] != "acorn" for r in rooms)


def test_archive_visible_with_include_archived(client):
    client.post("/rooms", json={"room_id": "acorn", "room_name": "Acorn"})
    client.post("/rooms/acorn/archive")
    rooms = client.get("/rooms?include_archived=1").get_json()
    by_id = {r["id"]: r for r in rooms}
    assert by_id["acorn"]["archived"] is True
    assert by_id["default"]["archived"] is False


def test_unarchive_restores_room(client):
    client.post("/rooms", json={"room_id": "acorn", "room_name": "Acorn"})
    client.post("/rooms/acorn/archive")
    res = client.post("/rooms/acorn/unarchive")
    assert res.status_code == 200
    rooms = client.get("/rooms").get_json()
    assert any(r["id"] == "acorn" for r in rooms)


def test_archive_default_room_returns_400(client):
    res = client.post("/rooms/default/archive")
    assert res.status_code == 400


def test_archive_unknown_room_returns_404(client):
    res = client.post("/rooms/ghost/archive")
    assert res.status_code == 404


def test_archive_requires_auth(auth_client):
    auth_client.post(
        "/rooms",
        json={"room_id": "acorn", "room_name": "Acorn"},
        headers={"X-Doorplate-Token": "s3cret"},
    )
    res = auth_client.post("/rooms/acorn/archive")
    assert res.status_code == 401


def test_archived_room_status_still_accessible(client):
    """Archive preserves data — /status/<id> still works so Unarchive is non-destructive."""
    client.post("/rooms", json={"room_id": "acorn", "room_name": "Acorn"})
    client.post("/update/acorn", json={"room_name": "Renamed Acorn"})
    client.post("/rooms/acorn/archive")
    res = client.get("/status/acorn")
    assert res.status_code == 200
    assert res.get_json()["room_name"] == "Renamed Acorn"


def test_sync_worker_skips_archived_rooms(monkeypatch):
    import ics_sync as ics

    fetched = []

    def fake_fetch(url, timeout=15):
        fetched.append(url)
        return b"BEGIN:VCALENDAR\r\nVERSION:2.0\r\nEND:VCALENDAR\r\n"

    monkeypatch.setattr(ics, "fetch_ics", fake_fetch)

    state = {
        "rooms": {
            "default": {
                "sources": {
                    "work": {
                        "label": "W",
                        "accent": "#000000",
                        "short": "W",
                        "ics_url": "https://x/default.ics",
                    }
                },
                "synced_schedule": {},
                "archived": False,
            },
            "acorn": {
                "sources": {
                    "cal": {
                        "label": "C",
                        "accent": "#000000",
                        "short": "C",
                        "ics_url": "https://x/acorn.ics",
                    }
                },
                "synced_schedule": {},
                "archived": True,
            },
        }
    }
    stored = {}
    worker = ics.SyncWorker(lambda: state, lambda s: stored.update(s), interval=3600)
    worker.poll_once()
    assert fetched == ["https://x/default.ics"]


# ---------- ESPHome config endpoint ----------


def test_esphome_config_for_default_room_200(client):
    res = client.get("/esphome/default.yaml")
    assert res.status_code == 200
    assert res.headers["Content-Type"].startswith("text/yaml")
    body = res.get_data(as_text=True)
    assert "esphome:" in body
    assert "waveshare_epaper" in body


def test_esphome_config_substitutes_room_id(client):
    client.post("/rooms", json={"room_id": "acorn", "room_name": "Acorn"})
    res = client.get("/esphome/acorn.yaml")
    body = res.get_data(as_text=True)
    assert 'room_id: "acorn"' in body
    # And the placeholder is gone
    assert 'room_id: "default"' not in body


def test_esphome_config_substitutes_server_host(client):
    res = client.get("/esphome/default.yaml", base_url="http://myhost.local:5050")
    body = res.get_data(as_text=True)
    assert 'server_host: "myhost.local"' in body
    assert 'server_host: "your-mac.local"' not in body


def test_esphome_config_preserves_comments(client):
    """Comments in the template survive the substitution — downloaded file
    matches the repo template for everything except the two values."""
    res = client.get("/esphome/default.yaml")
    body = res.get_data(as_text=True)
    # A known comment from the template
    assert "mDNS hostname" in body
    assert "Must match [a-z0-9_-]" in body


def test_esphome_config_unknown_room_404(client):
    res = client.get("/esphome/nosuchroom.yaml")
    assert res.status_code == 404


def test_esphome_config_invalid_room_id_400(client):
    # Routing: dots aren't in the room_id path converter, so "has.dots" matches
    # the <room_id>.yaml pattern as "has" + ".dots.yaml" — which doesn't match.
    # Test the cases Flask actually routes to the handler: uppercase, dash-only.
    for bad in ("UPPER", "a" * 33):
        res = client.get(f"/esphome/{bad}.yaml")
        assert res.status_code in (400, 404), f"{bad!r} got {res.status_code}"


def test_esphome_config_content_disposition_filename(client):
    client.post("/rooms", json={"room_id": "studio", "room_name": "Studio"})
    res = client.get("/esphome/studio.yaml")
    assert 'filename="doorplate-studio.yaml"' in res.headers["Content-Disposition"]


def test_esphome_config_works_for_archived_room(client):
    """Archived rooms should still yield a config — enables re-flash before unarchive."""
    client.post("/rooms", json={"room_id": "acorn", "room_name": "Acorn"})
    client.post("/rooms/acorn/archive")
    res = client.get("/esphome/acorn.yaml")
    assert res.status_code == 200
    assert 'room_id: "acorn"' in res.get_data(as_text=True)


# ---------- room settings page + /config ----------


def test_settings_page_served(client):
    res = client.get("/room/default/settings")
    assert res.status_code == 200
    body = res.get_data(as_text=True)
    assert "Flash this sign" in body
    assert "ESPHome dashboard" in body


def test_settings_page_served_for_unknown_room(client):
    # Mirrors the /room/<id> pattern — page loads, client surfaces the error.
    res = client.get("/room/ghost/settings")
    assert res.status_code == 200


def test_config_endpoint_returns_null_when_unset(client, monkeypatch):
    monkeypatch.delenv("ESPHOME_DASHBOARD_URL", raising=False)
    res = client.get("/config")
    assert res.status_code == 200
    assert res.get_json() == {"esphome_dashboard_url": None}


def test_config_endpoint_exposes_esphome_url(tmp_path, monkeypatch):
    monkeypatch.setattr(server_module, "DATA_FILE", tmp_path / "sign_data.json")
    monkeypatch.setattr(server_module, "ICS_DIR", tmp_path / "ics")
    monkeypatch.delenv("DOORPLATE_TOKEN", raising=False)
    monkeypatch.setenv("ESPHOME_DASHBOARD_URL", "http://localhost:6052")
    app = server_module.create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        res = c.get("/config")
        assert res.get_json() == {"esphome_dashboard_url": "http://localhost:6052"}


def test_config_endpoint_strips_whitespace(tmp_path, monkeypatch):
    monkeypatch.setattr(server_module, "DATA_FILE", tmp_path / "sign_data.json")
    monkeypatch.setenv("ESPHOME_DASHBOARD_URL", "   ")  # blank-ish
    app = server_module.create_app()
    with app.test_client() as c:
        res = c.get("/config")
        assert res.get_json() == {"esphome_dashboard_url": None}
