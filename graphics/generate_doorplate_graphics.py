#!/usr/bin/env python3
"""Graphics pack for the doorplate-diy README.

Runs inside the modern-graphics Docker container — invoked via:

    docker run --rm --ipc=host --init \
      --entrypoint python \
      -v $(pwd)/graphics:/out \
      modern-graphics /out/generate_doorplate_graphics.py

Outputs land in graphics/ next to this script (/out inside the container).
"""

from __future__ import annotations

import argparse
from pathlib import Path

from modern_graphics import (
    Attribution,
    ModernGraphicsGenerator,
    create_custom_scheme,
    register_scheme,
)
from modern_graphics.diagrams.insight import generate_insight_card

OUT = Path("/out") if Path("/out").exists() else Path(__file__).parent
OUT.mkdir(parents=True, exist_ok=True)

ATTRIBUTION = Attribution(copyright="© 2026 Data and Operations LLC", context="doorplate-diy")

# ── Doorplate theme — matches control panel's ink.css ────────────────
# ink:    #0a0a0a      paper:  #f4f1ea      accent: #c4342a
SCHEME = create_custom_scheme(
    name="doorplate",
    primary="#0a0a0a",
    secondary="#7a7a7a",
    accent="#c4342a",
    google_font_name="Syne",
    font_style="sans-serif",
    description="doorplate-diy: dark ink on warm paper, red accent",
)
register_scheme(SCHEME)


# ── E-ink placard wireframe SVG ──────────────────────────────────────
# Mirrors the real display layout at 648×480. White panel, black stroke,
# red badge for IN USE state. Used in the hero freeform canvas.
EINK_WIREFRAME_SVG = """
<svg viewBox="0 0 648 480" xmlns="http://www.w3.org/2000/svg"
     style="width: 100%; max-width: 720px; height: auto; display: block;
            background: #f4f1ea; filter: drop-shadow(0 18px 50px rgba(10,10,10,.18));">
  <!-- outer bezel -->
  <rect x="4" y="4" width="640" height="472" rx="6"
        fill="#ffffff" stroke="#0a0a0a" stroke-width="3"/>
  <!-- room title -->
  <text x="28" y="82" font-family="DM Sans, Syne, sans-serif"
        font-weight="800" font-size="60"
        letter-spacing="-1.5" fill="#0a0a0a">Acorn</text>
  <!-- IN USE badge (filled red) -->
  <rect x="28" y="104" width="132" height="36" fill="#c4342a"/>
  <text x="42" y="130" font-family="DM Mono, monospace"
        font-weight="700" font-size="18"
        letter-spacing="2" fill="#ffffff">IN USE</text>
  <!-- schedule rows -->
  <g font-family="DM Sans, sans-serif" font-size="22" fill="#0a0a0a">
    <!-- source chip + time + title, per row -->
    <rect x="28" y="168" width="22" height="22" fill="#0091ea"/>
    <text x="35" y="185" font-family="DM Mono, monospace" font-size="13"
          font-weight="700" fill="#ffffff">W</text>
    <text x="62" y="186">09:00</text><text x="142" y="186">Standup</text>

    <rect x="28" y="200" width="22" height="22" fill="#0091ea"/>
    <text x="35" y="217" font-family="DM Mono, monospace" font-size="13"
          font-weight="700" fill="#ffffff">W</text>
    <text x="62" y="218">10:30</text><text x="142" y="218">1:1 with Casey</text>

    <text x="62" y="250">13:00</text><text x="142" y="250">Product sync</text>

    <rect x="28" y="264" width="22" height="22" fill="#2e7d32"/>
    <text x="35" y="281" font-family="DM Mono, monospace" font-size="13"
          font-weight="700" fill="#ffffff">P</text>
    <text x="62" y="282">16:00</text><text x="142" y="282">Customer demo</text>
  </g>
  <!-- divider -->
  <line x1="28" y1="310" x2="620" y2="310" stroke="#0a0a0a" stroke-width="1"/>
  <!-- joke -->
  <g font-family="DM Mono, monospace" font-size="17" fill="#0a0a0a">
    <text x="28" y="340">Q: Why don't scientists trust atoms?</text>
    <text x="28" y="366">A: Because they make up everything.</text>
  </g>
  <!-- footer -->
  <line x1="28" y1="432" x2="620" y2="432" stroke="#7a7a7a" stroke-width="1"/>
  <g font-family="DM Mono, monospace" font-size="14" fill="#7a7a7a">
    <text x="28" y="456">3 min ago</text>
    <text x="620" y="456" text-anchor="end">doorplate-diy</text>
  </g>
</svg>
"""


# ── Builders ──────────────────────────────────────────────────────────


def build_01_hero():
    """Hero: tagline + wireframe of what the sign looks like."""
    g = ModernGraphicsGenerator("doorplate-diy", attribution=ATTRIBUTION)
    html = g.generate_modern_hero(
        headline="A WiFi-connected e-ink meeting room sign",
        subheadline="You build it in an afternoon.",
        eyebrow="doorplate-diy · from Data and Operations",
        highlights=[
            "Kit from $43",
            "Auto-syncs with any iCal URL",
            "Deep-sleep battery friendly",
        ],
        freeform_canvas=EINK_WIREFRAME_SVG,
        color_scheme=SCHEME,
        background_variant="light",
    )
    g.export_to_png(
        html,
        str(OUT / "01-hero-doorplate.png"),
        viewport_width=2400,
        viewport_height=1600,
    )


def build_02_kits_comparison():
    """Kit comparison: two equally valid choices, with panel wireframes."""
    standard_mockup = """
<svg viewBox="0 0 200 110" xmlns="http://www.w3.org/2000/svg">
  <rect x="8" y="8" width="184" height="94" fill="#fff" stroke="#0a0a0a" stroke-width="2"/>
  <text x="18" y="32" font-family="Syne, sans-serif" font-weight="800" font-size="17" fill="#0a0a0a">Acorn</text>
  <rect x="18" y="40" width="54" height="12" fill="#0a0a0a"/>
  <text x="22" y="49" font-family="monospace" font-weight="700" font-size="8" fill="#fff">IN USE</text>
  <g font-family="sans-serif" font-size="9" fill="#0a0a0a">
    <text x="18" y="68">09:00  Standup</text>
    <text x="18" y="81">11:00  Design review</text>
    <text x="18" y="94">14:00  1:1 w/ Priya</text>
  </g>
</svg>
"""
    premium_mockup = """
<svg viewBox="0 0 200 110" xmlns="http://www.w3.org/2000/svg">
  <rect x="8" y="8" width="184" height="94" fill="#fff" stroke="#0a0a0a" stroke-width="2"/>
  <text x="18" y="32" font-family="Syne, sans-serif" font-weight="800" font-size="17" fill="#0a0a0a">Oak</text>
  <rect x="18" y="40" width="54" height="12" fill="#c4342a"/>
  <text x="22" y="49" font-family="monospace" font-weight="700" font-size="8" fill="#fff">ON AIR</text>
  <g font-family="sans-serif" font-size="9" fill="#0a0a0a">
    <rect x="18" y="62" width="8" height="8" fill="#0091ea"/>
    <text x="31" y="69">09:00  Record</text>
    <rect x="18" y="75" width="8" height="8" fill="#2e7d32"/>
    <text x="31" y="82">11:00  Edit pass</text>
    <rect x="18" y="88" width="8" height="8" fill="#ff6f00"/>
    <text x="31" y="95">14:00  Client demo</text>
  </g>
</svg>
"""
    g = ModernGraphicsGenerator("Kits", attribution=ATTRIBUTION)
    html = g.generate_slide_card_diagram(
        cards=[
            {
                "title": "Standard",
                "tagline": "Most meeting rooms",
                "subtext": "Waveshare 4.2\" B&W · 400×300 · crisp text, classic e-ink look.",
                "features": [
                    "Waveshare 4.2\" e-Paper (B&W)",
                    "Waveshare ESP32 Driver Board",
                    "USB-C cable",
                    "IKEA RIBBA 5×7\" frame",
                ],
                "badge": "~$43",
                "color": "blue",
                "custom_mockup": standard_mockup,
            },
            {
                "title": "Premium",
                "tagline": "Style-forward workspaces",
                "subtext": "Waveshare 3.6\" Spectra 6 · full colour · slower refresh, richer visuals.",
                "features": [
                    "Waveshare 3.6\" Spectra 6 (colour)",
                    "Waveshare ESP32 Driver Board",
                    "USB-C cable",
                    "IKEA RIBBA 5×7\" frame",
                ],
                "badge": "~$60",
                "color": "purple",
                "custom_mockup": premium_mockup,
            },
        ],
        arrow_text="or",
        color_scheme=SCHEME,
    )
    g.export_to_png(
        html,
        str(OUT / "02-kits-comparison.png"),
        viewport_width=1800,
        viewport_height=1200,
    )


def build_03_test_without_hardware():
    """Three zero-hardware paths for dogfooding before you flash an ESP32."""
    browser_mockup = """
<svg viewBox="0 0 200 110" xmlns="http://www.w3.org/2000/svg">
  <rect x="8" y="8" width="184" height="94" rx="3" fill="#fff" stroke="#0a0a0a" stroke-width="2"/>
  <rect x="8" y="8" width="184" height="16" fill="#e4e0d6"/>
  <circle cx="16" cy="16" r="2" fill="#ff6f00"/>
  <circle cx="23" cy="16" r="2" fill="#f59e0b"/>
  <circle cx="30" cy="16" r="2" fill="#2e7d32"/>
  <rect x="44" y="12" width="140" height="9" rx="4" fill="#fff" stroke="#c4c4c4"/>
  <text x="48" y="18" font-family="monospace" font-size="6" fill="#7a7a7a">localhost:5000</text>
  <rect x="16" y="32" width="76" height="62" fill="#f4f1ea"/>
  <text x="22" y="46" font-family="monospace" font-size="6" fill="#7a7a7a">CONTROL PANEL</text>
  <rect x="22" y="52" width="64" height="6" fill="#fff" stroke="#c4c4c4"/>
  <rect x="22" y="62" width="40" height="6" fill="#0a0a0a"/>
  <rect x="100" y="32" width="84" height="62" fill="#fff" stroke="#0a0a0a" stroke-width="1.5"/>
  <text x="106" y="46" font-family="Syne, sans-serif" font-weight="800" font-size="12" fill="#0a0a0a">Acorn</text>
  <rect x="106" y="52" width="32" height="8" fill="#0a0a0a"/>
  <g font-family="sans-serif" font-size="6" fill="#0a0a0a">
    <text x="106" y="72">09:00  Standup</text>
    <text x="106" y="82">11:00  Design</text>
  </g>
</svg>
"""
    preview_mockup = """
<svg viewBox="0 0 200 110" xmlns="http://www.w3.org/2000/svg">
  <g transform="translate(40,10)">
    <rect x="0" y="0" width="120" height="90" fill="#fff" stroke="#0a0a0a" stroke-width="2"/>
    <text x="10" y="22" font-family="Syne, sans-serif" font-weight="800" font-size="16" fill="#0a0a0a">Acorn</text>
    <rect x="10" y="28" width="40" height="10" fill="#c4342a"/>
    <text x="14" y="36" font-family="monospace" font-weight="700" font-size="6" fill="#fff">ON AIR</text>
    <g font-family="sans-serif" font-size="7" fill="#0a0a0a">
      <text x="10" y="52">09:00  Record</text>
      <text x="10" y="62">11:00  Edit</text>
      <text x="10" y="72">14:00  Demo</text>
    </g>
    <line x1="10" y1="79" x2="110" y2="79" stroke="#7a7a7a" stroke-width="0.5"/>
    <text x="10" y="86" font-family="monospace" font-size="5" fill="#7a7a7a">3 min ago</text>
    <text x="110" y="86" text-anchor="end" font-family="monospace" font-size="5" fill="#7a7a7a">doorplate-diy</text>
  </g>
  <text x="100" y="106" text-anchor="middle" font-family="monospace" font-size="6" fill="#7a7a7a">preview.png · 400×300 · PIL</text>
</svg>
"""
    compile_mockup = """
<svg viewBox="0 0 200 110" xmlns="http://www.w3.org/2000/svg">
  <rect x="8" y="8" width="184" height="94" rx="3" fill="#0a0a0a"/>
  <rect x="8" y="8" width="184" height="14" fill="#1a1a1a"/>
  <circle cx="16" cy="15" r="2" fill="#ff6f00"/>
  <circle cx="23" cy="15" r="2" fill="#f59e0b"/>
  <circle cx="30" cy="15" r="2" fill="#2e7d32"/>
  <text x="100" y="17" text-anchor="middle" font-family="monospace" font-size="6" fill="#7a7a7a">~ esphome config meeting-sign.yaml</text>
  <g font-family="monospace" font-size="7">
    <text x="14" y="34" fill="#00ff66">$ make esphome-validate</text>
    <text x="14" y="46" fill="#7a7a7a">INFO Reading configuration...</text>
    <text x="14" y="58" fill="#7a7a7a">INFO ESPHome 2026.2</text>
    <text x="14" y="70" fill="#7a7a7a">INFO Loading fonts...</text>
    <text x="14" y="84" fill="#fff">✓ Configuration is valid!</text>
    <text x="14" y="98" fill="#00ff66">$ _</text>
  </g>
</svg>
"""
    g = ModernGraphicsGenerator("Test without hardware", attribution=ATTRIBUTION)
    html = g.generate_slide_card_diagram(
        cards=[
            {
                "title": "Browser preview",
                "tagline": "Live placard, real-time",
                "subtext": "make dev → open http://localhost:5000. Every edit updates the sign preview instantly.",
                "color": "blue",
                "custom_mockup": browser_mockup,
            },
            {
                "title": "Pixel-accurate PNG",
                "tagline": "render_preview.py → 400×300",
                "subtext": "Same fonts, same layout, same code the ESPHome lambda uses. No hardware required.",
                "color": "purple",
                "custom_mockup": preview_mockup,
            },
            {
                "title": "Firmware validation",
                "tagline": "esphome-validate + compile",
                "subtext": "Builds the actual ESP32 binary end-to-end. Catches YAML, pin, and lambda errors before you flash.",
                "color": "green",
                "custom_mockup": compile_mockup,
            },
        ],
        arrow_text="→",
        color_scheme=SCHEME,
    )
    g.export_to_png(
        html,
        str(OUT / "03-test-without-hardware.png"),
        viewport_width=2200,
        viewport_height=1400,
    )


def build_04_modes_insight():
    """Insight card highlighting the mode presets."""
    g = ModernGraphicsGenerator("Modes", attribution=ATTRIBUTION)
    html = generate_insight_card(
        g,
        text=(
            "The same sign serves a meeting room, a recording studio, a lab, "
            "or a focus-mode door. Pick a mode, pick a label, push to sign."
        ),
        svg_content=EINK_WIREFRAME_SVG,
        label="5 built-in modes · unlimited custom",
        layout="side-by-side",
        svg_position="left",
        color_scheme=SCHEME,
    )
    g.export_to_png(
        html,
        str(OUT / "04-modes-insight.png"),
        viewport_width=2200,
        viewport_height=1300,
    )


# ── Variant wireframes (different use cases, fonts, moods) ───────────


def _placard_svg(
    room: str,
    state: str,           # "AVAILABLE" / "ON AIR" / "DO NOT DISTURB" / "EXPERIMENT RUNNING"
    busy: bool,
    schedule: list,       # [(short, short_bg, time, title)] — short can be ""
    joke_q: str,
    joke_a: str,
    footer_left: str = "just now",
    accent: str = "#c4342a",
    title_font: str = "DM Sans, sans-serif",
    body_font: str = "DM Sans, sans-serif",
    mono_font: str = "DM Mono, monospace",
) -> str:
    """Build a placard SVG with configurable content + fonts."""
    rows = []
    y = 168
    for short, short_bg, time, title in schedule:
        if short:
            rows.append(
                f'<rect x="28" y="{y}" width="22" height="22" fill="{short_bg}"/>'
                f'<text x="35" y="{y + 17}" font-family="{mono_font}" font-size="13" '
                f'font-weight="700" fill="#ffffff">{short}</text>'
            )
        rows.append(
            f'<text x="62" y="{y + 18}" font-family="{body_font}" font-size="22" '
            f'fill="#0a0a0a">{time}</text>'
            f'<text x="142" y="{y + 18}" font-family="{body_font}" font-size="22" '
            f'fill="#0a0a0a">{title}</text>'
        )
        y += 32
    rows_svg = "\n    ".join(rows)
    badge_fill = accent if busy else "#ffffff"
    badge_text_color = "#ffffff" if busy else "#0a0a0a"
    badge_stroke = f' stroke="#0a0a0a" stroke-width="2"' if not busy else ""
    return f"""
<svg viewBox="0 0 648 480" xmlns="http://www.w3.org/2000/svg"
     style="width: 100%; max-width: 720px; height: auto; display: block;
            filter: drop-shadow(0 18px 50px rgba(10,10,10,.18));">
  <rect x="4" y="4" width="640" height="472" rx="6"
        fill="#ffffff" stroke="#0a0a0a" stroke-width="3"/>
  <text x="28" y="82" font-family="{title_font}" font-weight="800"
        font-size="60" letter-spacing="-1.5" fill="#0a0a0a">{room}</text>
  <rect x="28" y="104" width="{max(132, 10 + len(state) * 10)}" height="36"
        fill="{badge_fill}"{badge_stroke}/>
  <text x="42" y="130" font-family="{mono_font}" font-weight="700"
        font-size="18" letter-spacing="2" fill="{badge_text_color}">{state}</text>
  <g>
    {rows_svg}
  </g>
  <line x1="28" y1="310" x2="620" y2="310" stroke="#0a0a0a" stroke-width="1"/>
  <g font-family="{mono_font}" font-size="17" fill="#0a0a0a">
    <text x="28" y="340">Q: {joke_q}</text>
    <text x="28" y="366">A: {joke_a}</text>
  </g>
  <line x1="28" y1="432" x2="620" y2="432" stroke="#7a7a7a" stroke-width="1"/>
  <g font-family="{mono_font}" font-size="14" fill="#7a7a7a">
    <text x="28" y="456">{footer_left}</text>
    <text x="620" y="456" text-anchor="end">doorplate-diy</text>
  </g>
</svg>
"""


def build_05_studio():
    """Recording studio — ON AIR state, red-heavy, bold Syne title."""
    svg = _placard_svg(
        room="Podcast Bay",
        state="ON AIR",
        busy=True,
        schedule=[
            ("P", "#e60000", "09:00", "Ep 37 — record w/ Mara"),
            ("P", "#e60000", "11:30", "Edit pass"),
            ("",  "",        "14:00", "Mic calibration"),
            ("C", "#0091ea", "16:00", "Client review call"),
        ],
        joke_q="Why did the microphone go to therapy?",
        joke_a="It had trouble picking things up.",
        footer_left="2 min ago",
        accent="#e60000",
        title_font="Syne, sans-serif",
    )
    g = ModernGraphicsGenerator("Studio mode", attribution=ATTRIBUTION)
    html = g.generate_modern_hero(
        headline="Light the sign before you hit record.",
        subheadline='Switch to Studio mode. "OFF AIR" becomes "ON AIR" with a pulsing badge.',
        eyebrow="use case · recording studio",
        highlights=[
            "ON AIR pulses red",
            "Sync from your session calendar",
            "Quiet hours are self-evident",
        ],
        freeform_canvas=svg,
        color_scheme=SCHEME,
        background_variant="light",
    )
    g.export_to_png(
        html,
        str(OUT / "05-hero-studio.png"),
        viewport_width=2400,
        viewport_height=1600,
    )


def build_06_home_office():
    """Home office — DO NOT DISTURB state, amber mood, friendlier content."""
    svg = _placard_svg(
        room="The Cave",
        state="DO NOT DISTURB",
        busy=True,
        schedule=[
            ("W", "#0091ea", "09:30", "Standup"),
            ("F", "#ff6f00", "10:00", "Deep work — eng doc"),
            ("",  "",        "13:00", "Lunch (real lunch)"),
            ("K", "#2e7d32", "15:00", "School pickup"),
        ],
        joke_q="Why don't home offices ever close?",
        joke_a="The commute is too tempting.",
        footer_left="5 min ago",
        accent="#ff6f00",
        title_font="Syne, sans-serif",
        body_font="DM Sans, sans-serif",
    )
    g = ModernGraphicsGenerator("Home office mode", attribution=ATTRIBUTION)
    html = g.generate_modern_hero(
        headline="A polite door, for the rest of the house.",
        subheadline='Pulls from your work calendar, puts "DO NOT DISTURB" on the door during meetings.',
        eyebrow="use case · home office",
        highlights=[
            "Focus mode blinks on the hour",
            "Kid-calendar sources shown in green",
            "Stays quiet between 5pm and 9am",
        ],
        freeform_canvas=svg,
        color_scheme=SCHEME,
        background_variant="light",
    )
    g.export_to_png(
        html,
        str(OUT / "06-hero-home-office.png"),
        viewport_width=2400,
        viewport_height=1600,
    )


def _mini_placard_svg(room: str, state: str, busy: bool, accent: str) -> str:
    """Smaller placard card for the multi-room grid."""
    badge_fill = accent if busy else "#ffffff"
    badge_text_color = "#ffffff" if busy else "#0a0a0a"
    badge_stroke = f' stroke="#0a0a0a" stroke-width="2"' if not busy else ""
    return f"""
  <g>
    <rect x="0" y="0" width="320" height="220" rx="6"
          fill="#ffffff" stroke="#0a0a0a" stroke-width="3"/>
    <text x="18" y="62" font-family="Syne, sans-serif" font-weight="800"
          font-size="42" letter-spacing="-1.2" fill="#0a0a0a">{room}</text>
    <rect x="18" y="80" width="{max(110, 10 + len(state) * 9)}" height="30"
          fill="{badge_fill}"{badge_stroke}/>
    <text x="30" y="101" font-family="DM Mono, monospace" font-weight="700"
          font-size="14" letter-spacing="1.5" fill="{badge_text_color}">{state}</text>
    <g font-family="DM Sans, sans-serif" font-size="14" fill="#0a0a0a">
      <text x="18" y="145">09:00  Standup</text>
      <text x="18" y="168">11:00  1:1</text>
      <text x="18" y="191">14:00  Demo</text>
    </g>
  </g>
"""


def build_07_multi_room():
    """Multi-room — a grid of four placards, different rooms + states."""
    rooms = [
        ("Acorn",  "AVAILABLE",         False, "#c4342a"),
        ("Oak",    "IN USE",            True,  "#c4342a"),
        ("Maple",  "DO NOT DISTURB",    True,  "#ff6f00"),
        ("Birch",  "AVAILABLE",         False, "#c4342a"),
    ]
    placards = ""
    for i, (room, state, busy, accent) in enumerate(rooms):
        x = (i % 2) * 360
        y = (i // 2) * 260
        placards += f'<g transform="translate({x},{y})">{_mini_placard_svg(room, state, busy, accent)}</g>'
    svg = f"""
<svg viewBox="0 0 680 480" xmlns="http://www.w3.org/2000/svg"
     style="width: 100%; max-width: 760px; height: auto; display: block;
            filter: drop-shadow(0 18px 50px rgba(10,10,10,.18));">
  {placards}
</svg>
"""
    g = ModernGraphicsGenerator("Multi-room", attribution=ATTRIBUTION)
    html = g.generate_modern_hero(
        headline="One server, every door.",
        subheadline="Stand up a fleet in an afternoon — each sign keyed by room.",
        eyebrow="use case · multi-room office",
        highlights=[
            "Same server drives every sign",
            "Mixed modes across rooms",
            "Status visible at a glance",
        ],
        freeform_canvas=svg,
        color_scheme=SCHEME,
        background_variant="light",
    )
    g.export_to_png(
        html,
        str(OUT / "07-hero-multi-room.png"),
        viewport_width=2400,
        viewport_height=1600,
    )


BUILDERS = {
    "01": build_01_hero,
    "02": build_02_kits_comparison,
    "03": build_03_test_without_hardware,
    "04": build_04_modes_insight,
    "05": build_05_studio,
    "06": build_06_home_office,
    "07": build_07_multi_room,
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", help="comma-separated ids (e.g. 01,03)")
    args = parser.parse_args()

    targets = BUILDERS
    if args.only:
        keys = [k.strip() for k in args.only.split(",")]
        targets = {k: v for k, v in BUILDERS.items() if k in keys}

    for key, builder in targets.items():
        print(f"→ {key}")
        builder()
    print(f"done. output: {OUT}")


if __name__ == "__main__":
    main()
