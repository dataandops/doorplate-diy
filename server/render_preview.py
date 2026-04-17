"""Hardware-free e-ink simulator.

Renders what the Waveshare 4.2" B&W panel will show, using the same fonts and
layout as the ESPHome display lambda. Useful for iterating on the sign before
you have hardware (or while the ESP32 is in deep sleep).

Usage:
    python server/render_preview.py                  # reads sign_data.json
    python server/render_preview.py --url ...        # fetches /status
    python server/render_preview.py --out sign.png
"""

import argparse
import json
import sys
from pathlib import Path
from urllib.request import urlopen

from PIL import Image, ImageDraw, ImageFont

REPO_ROOT = Path(__file__).resolve().parent.parent
FONTS_DIR = REPO_ROOT / "esphome" / "fonts"
DATA_FILE = Path(__file__).resolve().parent / "sign_data.json"

WIDTH, HEIGHT = 400, 300
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
MUTED = (120, 120, 120)

FONT_FILES = {
    "title": ("RobotoCondensed-Bold.ttf", 36),
    "body": ("RobotoCondensed-Regular.ttf", 20),
    "mono": ("RobotoMono-Regular.ttf", 16),
    "small": ("RobotoCondensed-Regular.ttf", 12),
    "badge": ("RobotoCondensed-Bold.ttf", 14),
}


def _load_fonts() -> dict:
    missing = [f for f, _ in FONT_FILES.values() if not (FONTS_DIR / f).exists()]
    if missing:
        raise FileNotFoundError(
            f"Missing fonts in {FONTS_DIR}: {missing}. "
            "Drop the Roboto TTFs into esphome/fonts/ (Apache-2.0, from google/fonts)."
        )
    return {
        k: ImageFont.truetype(str(FONTS_DIR / fname), size)
        for k, (fname, size) in FONT_FILES.items()
    }


def _load_data(url: str | None) -> dict:
    if url:
        with urlopen(url, timeout=5) as resp:
            return json.load(resp)
    if DATA_FILE.exists():
        return json.loads(DATA_FILE.read_text())
    return {
        "room_name": "Meeting Room",
        "available": True,
        "schedule_display": [],
        "joke_q": "Why did the scarecrow win an award?",
        "joke_a": "He was outstanding in his field.",
        "last_updated": None,
    }


def render(data: dict, out_path: Path) -> None:
    fonts = _load_fonts()
    img = Image.new("RGB", (WIDTH, HEIGHT), WHITE)
    draw = ImageDraw.Draw(img)

    margin = 16
    y = margin

    # Title
    draw.text((margin, y), data.get("room_name", ""), fill=BLACK, font=fonts["title"])
    y += 42

    # Availability badge (B&W: filled black for IN USE, outlined for AVAILABLE)
    available = bool(data.get("available", True))
    label = "AVAILABLE" if available else "IN USE"
    bx0, by0 = margin, y
    pad_x, pad_y = 8, 4
    text_w = int(draw.textlength(label, font=fonts["badge"]))
    bx1 = bx0 + text_w + pad_x * 2
    by1 = by0 + 22
    if available:
        draw.rectangle((bx0, by0, bx1, by1), outline=BLACK, width=2)
        draw.text((bx0 + pad_x, by0 + pad_y - 1), label, fill=BLACK, font=fonts["badge"])
    else:
        draw.rectangle((bx0, by0, bx1, by1), fill=BLACK, outline=BLACK, width=2)
        draw.text((bx0 + pad_x, by0 + pad_y - 1), label, fill=WHITE, font=fonts["badge"])
    y = by1 + 12

    # Schedule
    lines = data.get("schedule_display") or []
    if not lines:
        draw.text((margin, y), "No meetings scheduled", fill=MUTED, font=fonts["body"])
        y += 24
    else:
        for line in lines[:4]:
            draw.text((margin, y), line, fill=BLACK, font=fonts["body"])
            y += 24

    # Divider
    y += 6
    draw.line((margin, y, WIDTH - margin, y), fill=BLACK, width=1)
    y += 10

    # Joke
    joke_q = data.get("joke_q", "")
    joke_a = data.get("joke_a", "")
    if joke_q:
        draw.text((margin, y), f"Q: {joke_q}", fill=BLACK, font=fonts["mono"])
        y += 20
    if joke_a:
        draw.text((margin, y), f"A: {joke_a}", fill=BLACK, font=fonts["mono"])
        y += 20

    # Footer
    footer_y = HEIGHT - margin - 14
    draw.line((margin, footer_y - 6, WIDTH - margin, footer_y - 6), fill=MUTED, width=1)
    updated = data.get("last_updated") or "not pushed yet"
    draw.text((margin, footer_y), updated, fill=MUTED, font=fonts["small"])
    brand = "doorplate-diy"
    brand_w = int(draw.textlength(brand, font=fonts["small"]))
    draw.text((WIDTH - margin - brand_w, footer_y), brand, fill=MUTED, font=fonts["small"])

    img.save(out_path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Render the e-ink sign layout to a PNG without hardware."
    )
    parser.add_argument(
        "--url",
        help="Fetch from a running server's /status endpoint instead of reading sign_data.json.",
    )
    parser.add_argument(
        "--out", default="preview.png", help="Output PNG path (default: preview.png)"
    )
    args = parser.parse_args(argv)

    data = _load_data(args.url)
    out_path = Path(args.out).resolve()
    render(data, out_path)
    print(f"Wrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
