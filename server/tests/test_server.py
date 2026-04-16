import json
import sys
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
    payload = {"schedule": [{"time": "09:00", "title": "Standup"}, {"time": "10:30", "title": "Design"}]}
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

    wrong = auth_client.post("/update", json={"room_name": "X"}, headers={"X-Doorplate-Token": "nope"})
    assert wrong.status_code == 401

    ok = auth_client.post("/update", json={"room_name": "X"}, headers={"X-Doorplate-Token": "s3cret"})
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
