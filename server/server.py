import json
import os
import re
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import ics_sync
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("DOORPLATE_DATA_DIR", str(BASE_DIR)))
DATA_FILE = DATA_DIR / "sign_data.json"
ICS_DIR = DATA_DIR / "ics"
STATIC_DIR = BASE_DIR / "static"
PUBLISH_NAME_RE = re.compile(r"^[a-z0-9_-]{1,32}$")
ROOM_ID_RE = re.compile(r"^[a-z0-9_-]{1,32}$")
THEME_NAME_RE = re.compile(r"^[a-z0-9_-]{1,32}$")
DEFAULT_ROOM_ID = "default"
DEFAULT_THEME = "ink"

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

MODES = {
    "meeting_room": {
        "label": "Meeting Room",
        "free": "AVAILABLE",
        "busy": "IN USE",
        "animation": "none",
        "accent": "#c4342a",
    },
    "studio": {
        "label": "Studio",
        "free": "OFF AIR",
        "busy": "ON AIR",
        "animation": "pulse",
        "accent": "#e60000",
    },
    "lab": {
        "label": "Lab",
        "free": "IDLE",
        "busy": "EXPERIMENT RUNNING",
        "animation": "scanline",
        "accent": "#0091ea",
    },
    "focus": {
        "label": "Focus",
        "free": "OPEN",
        "busy": "DO NOT DISTURB",
        "animation": "blink",
        "accent": "#ff6f00",
    },
    "custom": {
        "label": "Custom",
        "free": None,
        "busy": None,
        "animation": "none",
        "accent": "#c4342a",
    },
}

TIME_FORMATS = ("relative", "24h", "12h", "iso", "off")

SOURCE_KEY_RE = re.compile(r"^[a-z0-9_-]{1,16}$")
HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
CUSTOM_LABEL_MAX = 24
SOURCE_LABEL_MAX = 32
SOURCE_SHORT_MAX = 2
ROOM_NAME_MAX = 64

DEFAULT_ROOM_STATE = {
    "room_name": "Meeting Room",
    "available": True,
    "schedule": [],  # manually-entered rows only
    "synced_schedule": {},  # keyed by source: [{time, title, source, synced:True}]
    "joke_index": 0,
    "last_updated": None,
    "mode": "meeting_room",
    "custom_labels": {"free": "AVAILABLE", "busy": "IN USE"},
    "time_format": "relative",
    "sources": {},
    "theme": DEFAULT_THEME,
    "archived": False,
}

DEFAULT_STATE = {
    "rooms": {DEFAULT_ROOM_ID: DEFAULT_ROOM_STATE},
}

# Legacy flat keys we recognize at the top level of sign_data.json for
# migration from pre-multi-room installs.
_LEGACY_ROOM_KEYS = set(DEFAULT_ROOM_STATE.keys())


def _fresh_room_state() -> dict:
    return json.loads(json.dumps(DEFAULT_ROOM_STATE))


def _fresh_state() -> dict:
    return {"rooms": {DEFAULT_ROOM_ID: _fresh_room_state()}}


def _migrate_if_legacy(loaded: dict) -> dict:
    """Wrap a pre-multi-room flat-state dict into the new {rooms: {...}} shape.

    A file written by an older build has `room_name` (etc.) at the top level.
    A file written by this build has `rooms`. We detect the legacy shape by
    absence of `rooms` and presence of any known room-level key.
    """
    if "rooms" in loaded and isinstance(loaded["rooms"], dict):
        return loaded
    if any(k in loaded for k in _LEGACY_ROOM_KEYS):
        merged_room = _fresh_room_state()
        for k in _LEGACY_ROOM_KEYS:
            if k in loaded:
                merged_room[k] = loaded[k]
        return {"rooms": {DEFAULT_ROOM_ID: merged_room}}
    return _fresh_state()


def _normalize_state(state: dict) -> dict:
    """Ensure every room has all expected keys (for forward-compat reads)."""
    rooms = state.get("rooms") or {}
    if not isinstance(rooms, dict) or not rooms:
        return _fresh_state()
    out_rooms = {}
    for rid, room in rooms.items():
        if not isinstance(room, dict):
            continue
        merged = _fresh_room_state()
        merged.update(room)
        out_rooms[rid] = merged
    if DEFAULT_ROOM_ID not in out_rooms:
        out_rooms[DEFAULT_ROOM_ID] = _fresh_room_state()
    return {"rooms": out_rooms}


def _load_state() -> dict:
    if not DATA_FILE.exists():
        return _fresh_state()
    try:
        with open(DATA_FILE, encoding="utf-8") as f:
            loaded = json.load(f)
    except (json.JSONDecodeError, OSError):
        return _fresh_state()
    if not isinstance(loaded, dict):
        return _fresh_state()
    return _normalize_state(_migrate_if_legacy(loaded))


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


def _resolve_mode(room: dict) -> tuple[str, str, str, str]:
    mode_key = room.get("mode") or "meeting_room"
    mode = MODES.get(mode_key) or MODES["meeting_room"]
    if mode_key == "custom":
        cl = room.get("custom_labels") or {}
        free = (cl.get("free") or "AVAILABLE").strip() or "AVAILABLE"
        busy = (cl.get("busy") or "IN USE").strip() or "IN USE"
    else:
        free = mode["free"]
        busy = mode["busy"]
    return free, busy, mode["animation"], mode["accent"]


def _format_time(iso_str: str | None, fmt: str, now: datetime | None = None) -> str:
    if fmt == "off":
        return ""
    if not iso_str:
        return "not pushed yet"
    try:
        dt = datetime.fromisoformat(iso_str)
    except ValueError:
        return iso_str
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)

    if fmt == "iso":
        return iso_str

    local = dt.astimezone()
    if fmt == "24h":
        return local.strftime("%H:%M")
    if fmt == "12h":
        return local.strftime("%I:%M %p").lstrip("0")

    # relative (default)
    now = now or datetime.now(UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    delta = now - dt
    seconds = int(delta.total_seconds())
    if seconds < 0:
        return "just now"
    if seconds < 45:
        return "just now"
    if seconds < 3600:
        mins = max(1, round(seconds / 60))
        return f"{mins} min ago"
    if seconds < 86400:
        hours = max(1, round(seconds / 3600))
        return f"{hours} h ago"
    days = seconds // 86400
    if days <= 7:
        return f"{days} day ago" if days == 1 else f"{days} days ago"
    return local.strftime("%I:%M %p").lstrip("0")


def _format_schedule_time(time_hhmm: str, fmt: str) -> str:
    if fmt != "12h" or not time_hhmm or ":" not in time_hhmm:
        return time_hhmm
    try:
        hh, mm = time_hhmm.split(":", 1)
        h = int(hh)
    except ValueError:
        return time_hhmm
    h12 = ((h + 11) % 12) + 1
    return f"{h12}:{mm} {'AM' if h < 12 else 'PM'}"


def _format_schedule_display(schedule: list, sources: dict, time_format: str = "24h") -> list:
    lines = []
    for row in schedule:
        time = _format_schedule_time(str(row.get("time", "")).strip(), time_format)
        title = str(row.get("title", "")).strip()
        source_key = row.get("source")
        prefix = ""
        if isinstance(source_key, str) and source_key in sources:
            short = str(sources[source_key].get("short", "")).strip()
            if short:
                prefix = f"{short}· "
        if time and title:
            lines.append(f"{prefix}{time}  {title}")
        elif title:
            lines.append(f"{prefix}{title}")
        elif time:
            lines.append(f"{prefix}{time}")
    return lines


def _merged_schedule(room: dict) -> list[dict]:
    manual = list(room.get("schedule") or [])
    synced_by_source = room.get("synced_schedule") or {}
    merged = list(manual)
    for events in synced_by_source.values():
        merged.extend(events)

    def sort_key(row):
        t = str(row.get("time") or "")
        return (not t, t)

    merged.sort(key=sort_key)
    return merged


def _public_room(room: dict) -> dict:
    joke_q, joke_a = JOKES[room["joke_index"] % len(JOKES)]
    free, busy, animation, accent = _resolve_mode(room)
    available = bool(room["available"])
    status_label = free if available else busy
    status_animation = animation if (not available and animation != "none") else "none"
    sources = room.get("sources") or {}
    time_format = room.get("time_format") or "relative"
    merged = _merged_schedule(room)
    return {
        "room_name": room["room_name"],
        "available": available,
        "schedule": merged,
        "schedule_display": _format_schedule_display(merged, sources, time_format),
        "joke_q": joke_q,
        "joke_a": joke_a,
        "last_updated": room["last_updated"],
        "status_label": status_label,
        "status_animation": status_animation,
        "status_accent": accent,
        "mode": room.get("mode") or "meeting_room",
        "modes": [
            {"key": k, "label": v["label"], "free": v["free"], "busy": v["busy"]}
            for k, v in MODES.items()
        ],
        "custom_labels": room.get("custom_labels") or dict(DEFAULT_ROOM_STATE["custom_labels"]),
        "time_format": time_format,
        "time_display": _format_time(room["last_updated"], time_format),
        "sources": sources,
        "theme": room.get("theme") or DEFAULT_THEME,
    }


def _build_ics_body(events: list[dict], cal_name: str) -> str:
    import uuid
    from datetime import timedelta

    blocks = []
    today = datetime.now().astimezone()
    for row in events:
        time_str = str(row.get("time", "")).strip()
        title = str(row.get("title", "")).strip()
        if not time_str or ":" not in time_str or not title:
            continue
        hh, mm = (int(p) for p in time_str.split(":"))
        date_iso = row.get("date")
        base = datetime.fromisoformat(date_iso).astimezone() if date_iso else today
        start = base.replace(hour=hh, minute=mm, second=0, microsecond=0)
        duration = int(row.get("duration_min", 30))
        end = start + timedelta(minutes=duration)
        uid = row.get("uid") or f"{uuid.uuid4()}@doorplate-diy"
        blocks.append(
            "BEGIN:VEVENT\r\n"
            f"UID:{uid}\r\n"
            f"DTSTART:{start.strftime('%Y%m%dT%H%M%S')}\r\n"
            f"DTEND:{end.strftime('%Y%m%dT%H%M%S')}\r\n"
            f"SUMMARY:{title}\r\n"
            "END:VEVENT"
        )
    body = "\r\n".join(blocks)
    return (
        "BEGIN:VCALENDAR\r\n"
        "VERSION:2.0\r\n"
        "PRODID:-//doorplate-diy//publish//EN\r\n"
        f"X-WR-CALNAME:{cal_name}\r\n"
        f"{body}\r\n"
        "END:VCALENDAR\r\n"
    )


def _list_themes() -> list[str]:
    themes_dir = STATIC_DIR / "themes"
    if not themes_dir.is_dir():
        return [DEFAULT_THEME]
    return sorted(p.stem for p in themes_dir.glob("*.css"))


def _check_auth() -> bool:
    expected = os.environ.get("DOORPLATE_TOKEN", "")
    if not expected:
        return True
    provided = request.headers.get("X-Doorplate-Token", "")
    return provided == expected


def _validate_sources(value, existing: dict | None = None):
    if not isinstance(value, dict):
        return None, "sources must be an object"
    existing = existing or {}
    out = {}
    for key, cfg in value.items():
        if not isinstance(key, str) or not SOURCE_KEY_RE.match(key):
            return None, f"source key {key!r} must match [a-z0-9_-]{{1,16}}"
        if not isinstance(cfg, dict):
            return None, f"source {key!r} must be an object"
        label = cfg.get("label", "")
        accent = cfg.get("accent", "")
        short = cfg.get("short", "")
        ics_url = cfg.get("ics_url", "") or ""
        if not isinstance(label, str) or not label.strip() or len(label) > SOURCE_LABEL_MAX:
            return None, f"source {key!r}: label must be 1-{SOURCE_LABEL_MAX} chars"
        if not isinstance(accent, str) or not HEX_COLOR_RE.match(accent):
            return None, f"source {key!r}: accent must be #RRGGBB hex"
        if not isinstance(short, str) or not (1 <= len(short.strip()) <= SOURCE_SHORT_MAX):
            return None, f"source {key!r}: short must be 1-{SOURCE_SHORT_MAX} chars"
        if not isinstance(ics_url, str):
            return None, f"source {key!r}: ics_url must be a string"
        ics_url = ics_url.strip()
        if ics_url and not (
            ics_url.startswith("http://")
            or ics_url.startswith("https://")
            or ics_url.startswith("webcal://")
            or ics_url.startswith("webcals://")
        ):
            return None, f"source {key!r}: ics_url must start with http(s):// or webcal://"

        prev = existing.get(key) or {}
        entry = {
            "label": label,
            "accent": accent.lower(),
            "short": short.strip(),
            "ics_url": ics_url,
            "last_synced": prev.get("last_synced") if ics_url == prev.get("ics_url", "") else None,
            "last_sync_error": (
                prev.get("last_sync_error") if ics_url == prev.get("ics_url", "") else None
            ),
        }
        out[key] = entry
    return out, None


def _apply_update(room: dict, payload: dict) -> tuple[dict | None, tuple[dict, int] | None]:
    """Apply an /update payload to a room dict in place.

    Returns (room, None) on success or (None, (error_json, status)) on failure.
    """
    if "room_name" in payload:
        room_name = payload["room_name"]
        if not isinstance(room_name, str):
            return None, ({"error": "room_name must be a string"}, 400)
        room["room_name"] = room_name

    if "available" in payload:
        available = payload["available"]
        if not isinstance(available, bool):
            return None, ({"error": "available must be a boolean"}, 400)
        room["available"] = available

    if "mode" in payload:
        mode = payload["mode"]
        if not isinstance(mode, str) or mode not in MODES:
            return None, ({"error": f"mode must be one of {list(MODES)}"}, 400)
        room["mode"] = mode

    if "custom_labels" in payload:
        cl = payload["custom_labels"]
        if not isinstance(cl, dict):
            return None, ({"error": "custom_labels must be an object"}, 400)
        for k in ("free", "busy"):
            v = cl.get(k, "")
            if not isinstance(v, str) or not v.strip() or len(v) > CUSTOM_LABEL_MAX:
                return None, (
                    {"error": f"custom_labels.{k} must be 1-{CUSTOM_LABEL_MAX} chars"},
                    400,
                )
        room["custom_labels"] = {"free": cl["free"], "busy": cl["busy"]}

    if "time_format" in payload:
        tf = payload["time_format"]
        if not isinstance(tf, str) or tf not in TIME_FORMATS:
            return None, ({"error": f"time_format must be one of {list(TIME_FORMATS)}"}, 400)
        room["time_format"] = tf

    if "theme" in payload:
        theme = payload["theme"]
        if not isinstance(theme, str) or not THEME_NAME_RE.match(theme):
            return None, ({"error": "theme must match [a-z0-9_-]{1,32}"}, 400)
        if theme not in _list_themes():
            return None, ({"error": f"unknown theme {theme!r}"}, 400)
        room["theme"] = theme

    if "sources" in payload:
        sources, err = _validate_sources(payload["sources"], existing=room.get("sources"))
        if err:
            return None, ({"error": err}, 400)
        room["sources"] = sources
        synced = room.get("synced_schedule") or {}
        for key in list(synced):
            if key not in sources or not sources[key].get("ics_url"):
                synced.pop(key, None)
        room["synced_schedule"] = synced

    if "schedule" in payload:
        schedule = payload["schedule"]
        if not isinstance(schedule, list):
            return None, ({"error": "schedule must be a list"}, 400)
        allowed_sources = set(room.get("sources") or {})
        cleaned = []
        for row in schedule:
            if not isinstance(row, dict) or "time" not in row or "title" not in row:
                return None, ({"error": "schedule rows must have 'time' and 'title'"}, 400)
            if row.get("synced") is True:
                continue
            item = {"time": row["time"], "title": row["title"]}
            source = row.get("source")
            if source is not None:
                if not isinstance(source, str):
                    return None, ({"error": "schedule.source must be a string"}, 400)
                if source not in allowed_sources:
                    return None, ({"error": f"unknown source {source!r}"}, 400)
                item["source"] = source
            cleaned.append(item)
        room["schedule"] = cleaned

    if payload.get("new_joke"):
        room["joke_index"] = (room["joke_index"] + 1) % len(JOKES)

    room["last_updated"] = datetime.now(UTC).isoformat(timespec="seconds")
    return room, None


def _valid_room_id(room_id: str) -> bool:
    return isinstance(room_id, str) and bool(ROOM_ID_RE.match(room_id))


def create_app() -> Flask:
    app = Flask(__name__, static_folder=str(STATIC_DIR), static_url_path="/static")
    CORS(app)

    @app.get("/")
    def dashboard():
        return send_from_directory(STATIC_DIR, "dashboard.html")

    @app.get("/room/<room_id>")
    def control_panel(room_id: str):
        # Always serve the page; the client fetches /status/<id> and shows
        # an error toast for unknown rooms (mirrors the in-app fallback).
        del room_id
        return send_from_directory(STATIC_DIR, "index.html")

    # ---------- status (per-room + legacy alias) ----------

    def _status_for(room_id: str):
        state = _load_state()
        room = state["rooms"].get(room_id)
        if room is None:
            return jsonify({"error": f"unknown room {room_id!r}"}), 404
        return jsonify(_public_room(room))

    @app.get("/status")
    def status_default():
        return _status_for(DEFAULT_ROOM_ID)

    @app.get("/status/<room_id>")
    def status_room(room_id: str):
        if not _valid_room_id(room_id):
            return jsonify({"error": "room_id must match [a-z0-9_-]{1,32}"}), 400
        return _status_for(room_id)

    # ---------- rooms CRUD ----------

    @app.get("/rooms")
    def rooms_list():
        # Archived rooms are hidden by default — pass ?include_archived=1
        # to get them too (the dashboard's "Archived rooms" panel uses this).
        include_archived = request.args.get("include_archived", "").lower() in (
            "1",
            "true",
            "yes",
        )
        state = _load_state()
        rooms = []
        for rid, r in state["rooms"].items():
            archived = bool(r.get("archived"))
            if archived and not include_archived:
                continue
            free, busy, _, _ = _resolve_mode(r)
            available = bool(r.get("available"))
            rooms.append(
                {
                    "id": rid,
                    "room_name": r.get("room_name") or rid,
                    "theme": r.get("theme") or DEFAULT_THEME,
                    "available": available,
                    "status_label": free if available else busy,
                    "archived": archived,
                }
            )
        # Active rooms first (default pinned), then archived.
        rooms.sort(key=lambda r: (r["archived"], r["id"] != DEFAULT_ROOM_ID, r["id"]))
        return jsonify(rooms)

    @app.post("/rooms")
    def rooms_create():
        if not _check_auth():
            return jsonify({"error": "unauthorized"}), 401
        payload = request.get_json(silent=True) or {}
        room_id = payload.get("room_id", "")
        room_name = payload.get("room_name", "")
        if not _valid_room_id(room_id):
            return jsonify({"error": "room_id must match [a-z0-9_-]{1,32}"}), 400
        if not isinstance(room_name, str) or not room_name.strip():
            return jsonify({"error": "room_name is required"}), 400
        if len(room_name) > ROOM_NAME_MAX:
            return jsonify({"error": f"room_name must be 1-{ROOM_NAME_MAX} chars"}), 400
        state = _load_state()
        if room_id in state["rooms"]:
            return jsonify({"error": f"room {room_id!r} already exists"}), 409
        new_room = _fresh_room_state()
        new_room["room_name"] = room_name
        state["rooms"][room_id] = new_room
        _save_state(state)
        return jsonify({"id": room_id, "room_name": room_name}), 201

    def _set_archived(room_id: str, archived: bool):
        if not _check_auth():
            return jsonify({"error": "unauthorized"}), 401
        if not _valid_room_id(room_id):
            return jsonify({"error": "room_id must match [a-z0-9_-]{1,32}"}), 400
        if archived and room_id == DEFAULT_ROOM_ID:
            return jsonify({"error": "cannot archive the default room"}), 400
        state = _load_state()
        if room_id not in state["rooms"]:
            return jsonify({"error": f"unknown room {room_id!r}"}), 404
        state["rooms"][room_id]["archived"] = archived
        _save_state(state)
        return jsonify({"id": room_id, "archived": archived})

    @app.post("/rooms/<room_id>/archive")
    def rooms_archive(room_id: str):
        return _set_archived(room_id, True)

    @app.post("/rooms/<room_id>/unarchive")
    def rooms_unarchive(room_id: str):
        return _set_archived(room_id, False)

    @app.delete("/rooms/<room_id>")
    def rooms_delete(room_id: str):
        if not _check_auth():
            return jsonify({"error": "unauthorized"}), 401
        if not _valid_room_id(room_id):
            return jsonify({"error": "room_id must match [a-z0-9_-]{1,32}"}), 400
        if room_id == DEFAULT_ROOM_ID:
            return jsonify({"error": "cannot delete the default room"}), 400
        state = _load_state()
        if room_id not in state["rooms"]:
            return jsonify({"error": f"unknown room {room_id!r}"}), 404
        del state["rooms"][room_id]
        _save_state(state)
        return jsonify({"ok": True})

    # ---------- update (per-room + legacy alias) ----------

    def _do_update(room_id: str):
        if not _check_auth():
            return jsonify({"error": "unauthorized"}), 401
        payload = request.get_json(silent=True) or {}
        state = _load_state()
        room = state["rooms"].get(room_id)
        if room is None:
            return jsonify({"error": f"unknown room {room_id!r}"}), 404
        _, err = _apply_update(room, payload)
        if err is not None:
            body, status = err
            return jsonify(body), status
        _save_state(state)
        return jsonify(_public_room(room))

    @app.post("/update")
    def update_default():
        return _do_update(DEFAULT_ROOM_ID)

    @app.post("/update/<room_id>")
    def update_room(room_id: str):
        if not _valid_room_id(room_id):
            return jsonify({"error": "room_id must match [a-z0-9_-]{1,32}"}), 400
        return _do_update(room_id)

    # ---------- themes + ICS publishing + sources ----------

    @app.get("/themes")
    def themes():
        return jsonify(_list_themes())

    @app.post("/sources/refresh")
    def sources_refresh():
        if not _check_auth():
            return jsonify({"error": "unauthorized"}), 401
        worker = ics_sync.SyncWorker(_load_state, _save_state)
        worker.poll_once()
        # Return the default room's public state for backward compat.
        state = _load_state()
        return jsonify(_public_room(state["rooms"][DEFAULT_ROOM_ID]))

    @app.post("/ics/<name>")
    def ics_publish(name: str):
        if not _check_auth():
            return jsonify({"error": "unauthorized"}), 401
        if not PUBLISH_NAME_RE.match(name):
            return jsonify({"error": "name must match [a-z0-9_-]{1,32}"}), 400
        payload = request.get_json(silent=True) or {}
        events = payload.get("events", [])
        if not isinstance(events, list):
            return jsonify({"error": "events must be a list"}), 400
        cal_name = payload.get("cal_name", name)

        for row in events:
            if not isinstance(row, dict) or "time" not in row or "title" not in row:
                return jsonify({"error": "each event needs 'time' and 'title'"}), 400

        body = _build_ics_body(events, cal_name)
        ICS_DIR.mkdir(parents=True, exist_ok=True)
        (ICS_DIR / f"{name}.ics").write_text(body, encoding="utf-8")
        base = request.host_url.rstrip("/")
        return jsonify(
            {
                "ok": True,
                "name": name,
                "event_count": len(events),
                "url": f"{base}/ics/{name}.ics",
            }
        )

    @app.get("/ics/<name>.ics")
    def ics_serve(name: str):
        if not PUBLISH_NAME_RE.match(name):
            return "Not Found", 404
        path = ICS_DIR / f"{name}.ics"
        if not path.exists():
            return "Not Found", 404
        return (
            path.read_text(encoding="utf-8"),
            200,
            {"Content-Type": "text/calendar; charset=utf-8"},
        )

    @app.get("/ics")
    def ics_list():
        if not ICS_DIR.is_dir():
            return jsonify([])
        names = sorted(p.stem for p in ICS_DIR.glob("*.ics"))
        return jsonify(names)

    @app.delete("/ics/<name>")
    def ics_delete(name: str):
        if not _check_auth():
            return jsonify({"error": "unauthorized"}), 401
        if not PUBLISH_NAME_RE.match(name):
            return jsonify({"error": "not found"}), 404
        path = ICS_DIR / f"{name}.ics"
        if path.exists():
            path.unlink()
        return jsonify({"ok": True})

    @app.post("/sources/test")
    def sources_test():
        if not _check_auth():
            return jsonify({"error": "unauthorized"}), 401
        payload = request.get_json(silent=True) or {}
        url = payload.get("url", "")
        if not isinstance(url, str) or not url.strip():
            return jsonify({"ok": False, "error": "url is required"}), 400
        url = ics_sync.normalize_url(url)
        if not (url.startswith("http://") or url.startswith("https://")):
            return jsonify({"ok": False, "error": "URL must be http(s):// or webcal://"}), 400
        events, error = ics_sync.sync_source("__probe__", url)
        if error:
            return jsonify({"ok": False, "error": error, "resolved_url": url}), 200
        return jsonify(
            {
                "ok": True,
                "event_count": len(events),
                "events": events[:5],
                "resolved_url": url,
            }
        )

    return app


app = create_app()


def _maybe_start_sync_worker() -> ics_sync.SyncWorker | None:
    if os.environ.get("DOORPLATE_ICS_SYNC", "").strip() not in ("1", "true", "on"):
        return None
    interval = int(os.environ.get("DOORPLATE_ICS_POLL_INTERVAL", ics_sync.DEFAULT_POLL_INTERVAL))
    worker = ics_sync.SyncWorker(_load_state, _save_state, interval=interval)
    worker.start()
    return worker


sync_worker = _maybe_start_sync_worker()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
