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
    monkeypatch.delenv("DOORPLATE_TOKEN", raising=False)
    app = server_module.create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


@pytest.fixture
def auth_client(tmp_path, monkeypatch):
    monkeypatch.setattr(server_module, "DATA_FILE", tmp_path / "sign_data.json")
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
    assert data["schedule_display"] == ["09:00  Standup", "10:30  Design"]


def test_persistence_across_restart(tmp_path, monkeypatch):
    data_file = tmp_path / "sign_data.json"
    monkeypatch.setattr(server_module, "DATA_FILE", data_file)
    monkeypatch.delenv("DOORPLATE_TOKEN", raising=False)

    app1 = server_module.create_app()
    with app1.test_client() as c:
        c.post("/update", json={"room_name": "Reload Room", "available": False})

    assert data_file.exists()
    saved = json.loads(data_file.read_text())
    assert saved["room_name"] == "Reload Room"

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
    state["sources"] = {
        "work": {"label": "Work", "accent": "#0091ea", "short": "W", "ics_url": "https://x/w"},
    }
    state["synced_schedule"] = {
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
    # Only the manual row survives in state["schedule"]
    assert saved["schedule"] == [{"time": "14:00", "title": "Manual"}]


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
    state["synced_schedule"] = {
        "work": [{"time": "09:00", "title": "X", "source": "work", "synced": True}]
    }
    srv._save_state(state)

    # Remove the source via /update
    client.post("/update", json={"sources": {}})
    saved = srv._load_state()
    assert saved["synced_schedule"] == {}
