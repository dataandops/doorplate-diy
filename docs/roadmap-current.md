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
  IKEA RIBBA 5×7" shadow-box hack, BOM + assembly notes in README.
- **Kit BOM tables** — done / S
  Self-source instructions for Standard and Premium kit tiers.
- **Opt-in shared-secret auth** — done / S
  `DOORPLATE_TOKEN` env var enables `X-Doorplate-Token` enforcement on
  `POST /update`.
- **Optional Docker deploy path** — done / S
  Dockerfile + docker-compose.yml as an alternative to pip install. Both
  paths are first-class; users pick whichever they prefer.

## Next — committed, not yet built

- **Google Calendar integration** — idea / L
  Auto-populate `schedule` from a Google Calendar feed so users stop typing
  meetings manually. Server-side OAuth, token refresh, and a mapping config
  (calendar ID → room).
- **Multiple signs from one server** — idea / M
  Key each sign by `room_id`; `/status/<room_id>` and `/update/<room_id>`.
  Control panel grows a room selector. ESPHome substitutes `room_id` into
  the request URL.
- **Home Assistant integration** — idea / M
  Either MQTT publish on state change (HA consumes) or a native HA component
  that wraps the REST API. Lets HA automations flip "In Use" based on
  presence sensors, calendar, etc.
- **Physical-sign theming** — idea / M
  Swappable ESPHome lambda blocks for the display layout (mirror of the
  control-panel CSS theme system). Requires factoring the lambda into
  includable fragments.

## Later — exploring

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
- **Battery + LiPo power option** — idea / M
  USB-C powered v1 is fine for rooms with outlets. A LiPo option unlocks
  stick-anywhere placement; requires power-management circuitry review.
