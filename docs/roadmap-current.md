# Roadmap

Living, canonical view of where doorplate-diy is headed. For private scratch
(rough notes, half-baked ideas), see the gitignored `plans/` directory.

Each item has a **status** (idea / speccing / in-progress / done) and a rough
**size** (S / M / L).

## Now — shipping today

- **Flask control panel + `/status` + `/update` + `/themes`** — done / M
  Single-room meeting sign driven from a Mac. Dark ink/paper control panel,
  live placard preview, swappable CSS themes.
- **ESPHome config for Waveshare 4.2" B&W** — done / M
  Deep-sleep wake → HTTP GET → render → sleep. 15-minute refresh cadence.
  Tri-color 4.2" (`4.20in-bv2-bwr`) and 7.5" tri-color are the next supported
  sizes when we want to upgrade.
- **CI status checks** — done / S
  `ruff` + `black --check`, `pytest`, `html5validator`, `esphome config`. Runs
  on every push and PR, blocks merge on failure.
- **Hardware-free rendering via `render_preview.py`** — done / S
  Pillow renderer that produces a pixel-accurate PNG of the e-ink layout so
  you can iterate without owning hardware.
- **Picture-frame case documentation** — done / S
  IKEA RÖDALM 5×7" birch-effect frame, BOM + assembly notes in README.
- **Kit BOM tables** — done / S
  Self-source instructions for Standard and Premium kit tiers.
- **Opt-in shared-secret auth** — done / S
  `DOORPLATE_TOKEN` env var enables `X-Doorplate-Token` enforcement on
  `POST /update`.
- **Optional Docker deploy path** — done / S
  Dockerfile + docker-compose.yml as an alternative to pip install. Both
  paths are first-class; users pick whichever they prefer.
- **Modes + animation** — done / M
  Built-in presets (Meeting Room, Studio, Lab, Focus) plus Custom. Each
  preset defines free/busy labels, accent colour, and a browser animation
  (pulse / blink / scanline). E-ink gets a crude 2-frame flash on wake for
  busy + animated modes.
- **Configurable time format** — done / S
  Footer rendering: Relative / 24h / 12h / ISO / Off. Rendered server-side.
- **Calendar sources + ICS sync** — done / L
  Central source catalog (`{label, accent, short, ics_url}`). Schedule rows
  reference a source and render a colour chip in the browser / letter prefix
  on e-ink. When a source has an ICS URL, a background worker polls every
  10 min and auto-populates today's events. Works with Google, Apple,
  Outlook, Calendly, Notion — anything that exports iCal. No OAuth.
- **Multiple signs from one server** — done / M
  State now nests under `rooms[room_id]`. One server instance drives any
  number of signs via `/status/<room_id>` and `/update/<room_id>`. The
  control panel has a room selector in the top bar; ESPHome carries a
  `room_id` substitution per physical sign. Legacy flat state auto-migrates
  into `rooms["default"]` on first load.

## Next — committed, not yet built

- **Home Assistant integration** — idea / M
  Either MQTT publish on state change (HA consumes) or a native HA component
  that wraps the REST API. Lets HA automations flip busy based on presence
  sensors, calendar, etc.
- **Physical-sign layout theming** — idea / M
  Swappable ESPHome lambda fragments for the display layout (mirror of the
  control-panel CSS theme system).

## Later — exploring

- **Weather widget, alternating with jokes** — idea / S
  Below the divider: rotate between the dad joke and a weather readout
  (temp + condition + maybe tomorrow's forecast). Use `wttr.in` for
  zero-auth fetch, or OpenWeatherMap for richer data with an API key.
  Fits the whimsy-meets-utility vibe. Rotation controlled by a state
  counter that flips each sign wake.
- **Google Calendar OAuth** — idea / L
  For users who want richer data than ICS (attendees, response status,
  conference links). Requires OAuth flow + token refresh.
- **3D-printable custom case** — idea / M
  STL files for a purpose-built enclosure, checked into `case/`. Would
  replace the picture-frame hack as the default for pre-assembled kits.
- **Waveshare Spectra 6 color rendering path** — idea / M
  The Premium kit uses a 6-color panel. Extend `render_preview.py` and the
  ESPHome lambda to target the full palette.
- **`dataandoperations.com/doorplate` landing page + pre-orders** — idea / L
  Product marketing page, kit SKUs, checkout. Feeds the "Coming soon" promise
  in the README.
- **Presence-sensor auto-flip** — idea / M
  mmWave or PIR sensor in the room; ESP32 listens and flips `available` to
  false when it detects occupancy. Requires a second data path (currently
  the sign is one-way pull-only).
- **Optimise battery life for the LiPo option** — idea / S
  Basic LiPo support already works out of the box (the ESP32 Driver Board
  has charging + JST-PH connector built in; documented in README). Next
  step: tune `sleep_duration`, disable WiFi power-save to WAKE_NO_BEACON
  during sync, benchmark real-world battery life, and publish a
  per-cadence life table.
