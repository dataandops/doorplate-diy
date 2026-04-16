import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("DOORPLATE_DATA_DIR", str(BASE_DIR)))
DATA_FILE = DATA_DIR / "sign_data.json"
STATIC_DIR = BASE_DIR / "static"

JOKES = [
    ("Why don't scientists trust atoms?", "Because they make up everything."),
    ("What do you call a fake noodle?", "An impasta."),
    ("Why did the scarecrow win an award?", "He was outstanding in his field."),
    ("How do you organize a space party?", "You planet."),
    ("Why don't eggs tell jokes?", "They'd crack each other up."),
    ("What do you call cheese that isn't yours?", "Nacho cheese."),
    ("Why did the math book look sad?", "It had too many problems."),
    ("What's orange and sounds like a parrot?", "A carrot."),
    ("Why can't your nose be 12 inches long?", "Then it'd be a foot."),
    ("What do you call a bear with no teeth?", "A gummy bear."),
    ("Why did the coffee file a police report?", "It got mugged."),
    ("How do you make a tissue dance?", "Put a little boogie in it."),
    ("What lies at the bottom of the ocean twitching?", "A nervous wreck."),
    ("Why did the bicycle fall over?", "It was two tired."),
    ("What do you call a sleeping bull?", "A bulldozer."),
]

DEFAULT_STATE = {
    "room_name": "Meeting Room",
    "available": True,
    "schedule": [],
    "joke_index": 0,
    "last_updated": None,
}


def _load_state() -> dict:
    if not DATA_FILE.exists():
        return dict(DEFAULT_STATE)
    try:
        with open(DATA_FILE, encoding="utf-8") as f:
            loaded = json.load(f)
    except (json.JSONDecodeError, OSError):
        return dict(DEFAULT_STATE)
    merged = dict(DEFAULT_STATE)
    merged.update(loaded)
    return merged


def _save_state(state: dict) -> None:
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=str(DATA_FILE.parent), prefix=".sign_data.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
        os.replace(tmp_path, DATA_FILE)
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


def _format_schedule_display(schedule: list) -> list:
    lines = []
    for row in schedule:
        time = str(row.get("time", "")).strip()
        title = str(row.get("title", "")).strip()
        if time and title:
            lines.append(f"{time}  {title}")
        elif title:
            lines.append(title)
        elif time:
            lines.append(time)
    return lines


def _public_state(state: dict) -> dict:
    joke_q, joke_a = JOKES[state["joke_index"] % len(JOKES)]
    return {
        "room_name": state["room_name"],
        "available": bool(state["available"]),
        "schedule": state["schedule"],
        "schedule_display": _format_schedule_display(state["schedule"]),
        "joke_q": joke_q,
        "joke_a": joke_a,
        "last_updated": state["last_updated"],
    }


def _check_auth() -> bool:
    expected = os.environ.get("DOORPLATE_TOKEN", "")
    if not expected:
        return True
    provided = request.headers.get("X-Doorplate-Token", "")
    return provided == expected


def create_app() -> Flask:
    app = Flask(__name__, static_folder=str(STATIC_DIR), static_url_path="/static")
    CORS(app)

    @app.get("/")
    def index():
        return send_from_directory(STATIC_DIR, "index.html")

    @app.get("/status")
    def status():
        return jsonify(_public_state(_load_state()))

    @app.get("/themes")
    def themes():
        themes_dir = STATIC_DIR / "themes"
        if not themes_dir.is_dir():
            return jsonify([])
        names = sorted(p.stem for p in themes_dir.glob("*.css"))
        return jsonify(names)

    @app.post("/update")
    def update():
        if not _check_auth():
            return jsonify({"error": "unauthorized"}), 401

        payload = request.get_json(silent=True) or {}
        state = _load_state()

        if "room_name" in payload:
            room_name = payload["room_name"]
            if not isinstance(room_name, str):
                return jsonify({"error": "room_name must be a string"}), 400
            state["room_name"] = room_name

        if "available" in payload:
            available = payload["available"]
            if not isinstance(available, bool):
                return jsonify({"error": "available must be a boolean"}), 400
            state["available"] = available

        if "schedule" in payload:
            schedule = payload["schedule"]
            if not isinstance(schedule, list):
                return jsonify({"error": "schedule must be a list"}), 400
            for row in schedule:
                if not isinstance(row, dict) or "time" not in row or "title" not in row:
                    return jsonify({"error": "schedule rows must have 'time' and 'title'"}), 400
            state["schedule"] = schedule

        if payload.get("new_joke"):
            state["joke_index"] = (state["joke_index"] + 1) % len(JOKES)

        state["last_updated"] = datetime.now(UTC).isoformat(timespec="seconds")
        _save_state(state)
        return jsonify(_public_state(state))

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
