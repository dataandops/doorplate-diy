import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from render_preview import FONTS_DIR, FONT_FILES, render  # noqa: E402


FONTS_AVAILABLE = all((FONTS_DIR / fname).exists() for fname, _ in FONT_FILES.values())

pytestmark = pytest.mark.skipif(
    not FONTS_AVAILABLE, reason="Roboto fonts not present in esphome/fonts/; skipping renderer smoke test."
)


def test_render_produces_valid_png(tmp_path):
    data = {
        "room_name": "Lab A",
        "available": False,
        "schedule_display": ["09:00  Standup", "10:30  Design review"],
        "joke_q": "Why did the coffee file a police report?",
        "joke_a": "It got mugged.",
        "last_updated": "2026-04-16T14:00:00+00:00",
    }
    out = tmp_path / "preview.png"
    render(data, out)

    assert out.exists()

    from PIL import Image
    with Image.open(out) as img:
        assert img.size == (648, 480)
        assert img.mode == "RGB"


def test_render_handles_empty_schedule(tmp_path):
    data = {"room_name": "Empty", "available": True, "schedule_display": [], "joke_q": "", "joke_a": "", "last_updated": None}
    out = tmp_path / "preview.png"
    render(data, out)
    assert out.exists()
