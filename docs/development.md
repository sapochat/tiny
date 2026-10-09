# Developing the SDK

## Recent work E2E

`tests/test_work_shelf_e2e.py` uses the existing interaction rig: real native core,
production loopback DeviceHub, synthetic text and disposable state directories.
`tests/test_adapter_hermes.py::test_recent_outcome_after_disconnect_is_durable`
exercises real Hermes base classes without a provider.

```sh
export TMPDIR=$TMPDIR/workshelf
mkdir -p "$TMPDIR"
export HERMES_HOME="$TMPDIR/test-home"
PATH="$PWD/.venv/bin:$PATH" PYTHONPATH=python .venv/bin/python -m hermes_gadget build-sim --test
export HGSIM_LIBRARY="$PWD/build/host/libhgsim.so"
IX_ARTIFACTS=artifacts/work-shelf/fresh .venv/bin/python -m pytest tests/test_work_shelf_e2e.py -v --junitxml=artifacts/work-shelf/fresh.xml
```

Compatibility lanes require a frozen pre-M3 native library (`WORK_LEGACY_NATIVE=1`
with `HGSIM_LIBRARY` pointing to it, run only `-k legacy_native_gets`) and a frozen
pre-M3 `plugin/hub.py` (`WORK_LEGACY_HUB=/absolute/path/hub.py`, current native library).
The compatibility tests skip without these explicit fixtures. Do not substitute a
new library for the frozen one. The evidence directory contains the baseline hash,
red logs, later fixture corrections, native receipts/captures, and final JUnit.



## Layout

```
plugin/                 Hermes platform plugin (installed into ~/.hermes/plugins/gadget)
python/hermes_gadget/   Tools: simulator host, development server, provisioning, CLI
firmware/core/          Portable device core (C++17), shared by the ESP32 and the simulator
firmware/sim/           C ABI wrapper the simulator loads (hgsim.dll / libhgsim.so)
firmware/esp32/         ESP-IDF application and board configurations
firmware/tests/         Core unit tests (no dependencies)
site/                   Product homepage, hosted guides, and browser installer (GitHub Pages)
tests/                  Python tests: plugin units, simulator ↔ hub, adapter on Hermes, gateway E2E
docs/                   Architecture, protocol, integration, guides
tools/                  make_logo.py (the logo), check_versions.py (the release version check), capture_window.py (README screenshots of the simulator window)
assets/mascot/          The mascot master image and its attribution
```

## Test suites

| Suite | Command | Needs |
|---|---|---|
| Core (C++) | `hermes-gadget build-sim --test`, or `ctest --test-dir build/host -C Release` | CMake + compiler |
| Plugin units, simulator ↔ hub, desktop controls | `pytest` | Built simulator library; a desktop or Xvfb for window tests |
| Adapter on real Hermes classes | `HERMES_AGENT_DIR=../hermes-agent ../hermes-agent/.venv/bin/python -m pytest tests/test_adapter_hermes.py` | A Hermes checkout and its virtualenv |
| Full gateway end to end | `HERMES_GADGET_E2E=1 pytest tests/test_gateway_e2e.py` | The above; spawns `hermes gateway run` with a temporary `HERMES_HOME` |
| Browser installer | `npm ci && npm test` in `site/` | Node.js 22 |
| Home Assistant / MQTT examples | `pytest tests/test_automation_examples.py` | Built native library and the `mqtt` extra; local peers need no external accounts |

The Python jobs in `.github/workflows/ci.yml` run under `xvfb-run` so the desktop controls run against the simulator core and development hub. On a headless Linux machine, use `xvfb-run -a pytest`. Without a display, the window tests skip; set `HERMES_GADGET_UI_TESTS=1` to require them.

CI runs the adapter and gateway suites in `.github/workflows/hermes.yml`: against the Hermes commit pinned there (`HERMES_REF`) on every push and pull request, and against Hermes `main` once a day. To move the pin, run that workflow by hand with `hermes_ref: main`. When it passes, put the commit it printed into `HERMES_REF` and the README's status line.

The Linux jobs run on `ubuntu-24.04` rather than `ubuntu-latest`, so a new runner image arrives as a deliberate change instead of a surprise. Dependabot proposes the workflows' actions, the installer's npm packages and the Python dependencies weekly, a week after each release.

The end-to-end test runs a real gateway with the plugin installed and a fake OpenAI-compatible server (`tests/fakes/fake_openai.py`) standing in for the model, STT and TTS. It then:

- pairs a simulated device with `hermes pairing approve`;
- sends text and voice;
- checks that transcripts, spoken replies and both agent tools reach the device.

It costs nothing and needs no API keys.

Cross-language guarantees:

- `tests/test_protocol.py` and `firmware/tests/test_basics.cpp` share identity and HMAC vectors.
- `test_sim_hub.py` runs the C++ core against the Python hub, including hostile handshakes.
- `test_installer_console.py` runs the installer's console client (`site/src/lib/console.js`) against the C++ core, through a model of ESP-IDF's console (`tests/fakes/esp_console.py`): its echo, its ASCII-only input and its argument splitting.

### The browser installer

`site/` contains the product homepage, browser installer, and documentation, published to GitHub Pages by `.github/workflows/pages.yml` with the latest release's firmware. The build renders `docs/*.md` into the hosted guides with `marked`; edit the Markdown rather than the generated pages. Search runs in the browser and sends no queries to a server.

The installer flashes boards with [esptool-js](https://github.com/espressif/esptool-js) over Web Serial (Chrome and Edge), checks the chip against the release manifest first, and then talks to the firmware's serial console to set Wi-Fi, the Hermes address, and the name. To try it locally with your own builds:

```bash
cd site && npm ci
node scripts/build.mjs --firmware ../firmware/esp32/dist   # from tools/package_release.py
python -m http.server 8000 --directory _site               # then open http://localhost:8000
```

Web Serial needs a secure context, which `localhost` counts as.

For homepage and docs work, `npm run build` works without firmware. Run `npm run preview` to serve it at `http://127.0.0.1:8768`. The installer is at `installer.html`; old root links with `#server=...` still reach it with the address intact.

Run `npm test` for the Node tests. After building, run `npx playwright install chromium` and `npm run test:browser` for browser tests. CI installs Chromium and runs both suites. Set `BROWSER_EXECUTABLE` to use an existing Chromium binary locally.

The site build checks relative links and Markdown section anchors in root Markdown files and `docs/*.md`, including Markdown images and quoted HTML `href`/`src` attributes. Fenced examples, external URLs, and URLs starting with `/` are not checked. Every top-level guide in `docs/` must be registered once in `site/scripts/docs.mjs`; that registration publishes the page in navigation and search. Failures name the source file and missing target or registration.

CI discovers firmware profiles from `firmware/esp32/platformio.ini` using the release packager's environment reader. Adding a profile includes it in the firmware build/package matrix without maintaining a second list. Firmware tooling tests also check installer metadata and verify that every file under `LICENSES/` reaches the release license archive.

## Working on the plugin against a live Hermes

```bash
hermes-gadget plugin install --link   # symlink, so edits apply after a gateway restart
hermes gateway run
```

`--link` falls back to copying where symlinks need extra privileges (Windows without Developer Mode). Re-run the install after editing in that case.

If your Hermes is a source checkout whose virtualenv Python differs from the Python Hermes's package manager prepares for plugins, `hermes plugins enable` can create an environment the gateway cannot import from. Adding `plugins: {enabled: [gadget]}` to `config.yaml` directly avoids that; the plugin has no Python dependencies of its own.

## Working on the firmware

Almost everything in `firmware/core` can be developed with the simulator and the core tests:

1. Change `firmware/core`.
2. Run `hermes-gadget build-sim --test`.
3. Run `hermes-gadget sim`.
4. Flash hardware only for driver work in `firmware/esp32/main/port_*.cpp`.

### Build checks

Two checks stop a firmware build that would run with settings nobody asked for. Both run in every PlatformIO build, locally and in CI:

- **`tools/check_config.py`**, from `CMakeLists.txt` after the configuration is generated (so `idf.py` builds run it too). It fails when a line of `sdkconfig.defaults` or the board's defaults didn't reach the generated sdkconfig. That happens when a symbol is misspelled, belongs to another chip, or has an unmet dependency, and when an sdkconfig from an older checkout outlives a change to the defaults. In the last case, delete `sdkconfig.<board>` (PlatformIO) or the build directory, then build again. A board file that picks another option of a choice the base file sets says so with `# CONFIG_<base option> is not set`.
- **`tools/check_size.py`**, after linking (`tools/pio_checks.py`). It fails when the app leaves less than 10% of its smallest app partition free. For `idf.py` builds, run it by hand: `python tools/check_size.py --app build/hermes_gadget.bin --partitions build/partition_table/partition-table.bin`.

### Tiny v2 local animation candidate

The round 466px renderer uses the existing approved sources in the sibling
`../tiny-animations/picks/states-v2/` directory. The exact 14 numbered MP4s
and `../tiny-animations/picks/chain/chain-v2.json` are required for regeneration;
firmware builds only need the checked-in generated header. No paid generation,
network asset lookup, runtime video codec or smoothing is involved.

```sh
.venv/bin/python tools/build_expressions.py
.venv/bin/python -m cmake -S firmware -B build/video-v2 -DCMAKE_BUILD_TYPE=Release
.venv/bin/python -m cmake --build build/video-v2 -j 4
HGSIM_LIBRARY=$PWD/build/video-v2/libhgsim.so .venv/bin/python -m pytest tests/test_video_v2.py tests/test_expressions.py tests/test_touch_navigation.py tests/test_round_amoled.py tests/test_round_amoled_safety.py tests/test_reply_indicator.py -v --junitxml=artifacts/video-v2/results.xml
PLATFORMIO_BUILD_DIR=$PWD/build/video-v2-esp32 .venv/bin/python -m platformio run --project-dir firmware/esp32 -e esp32s3-touch-amoled-175c
```

Conversion uses FFmpeg and NumPy, samples each five-second clip to 25 frames,
retains the exact first/last source frame, Lanczos-resizes to 96px and quantizes
to four gray levels. Independent packed-gray2 LZ frames bound working storage to
2,304 bytes, with no per-frame allocation. The converter enforces its asset
budget; the actual firmware must also pass the unchanged 10%-free partition
size gate. Do not enlarge partitions to fit the pack.

`artifacts/video-v2/manifest.json` records input hashes, source frame indices,
anchor names, conversion versions and generated-header hash. The E2E fixtures
use a real local DeviceHub and native App, save protocol receipts and playback
GIFs, and compare rendered listening pixels against an independent MP4 decode.
The app's local `status` JSON includes `ui.animation.clip` and `frame`; these are
diagnostics, not a new host-controlled animation protocol. Evidence and build
outputs are ignored artifacts, not a release or a physical validation report.
The old static-outline/channel-step assertions are explicitly superseded; touch,
reading, success-only readiness and approval semantics remain enforced.

### Tiny face-first circular UI candidate

The 466px face-first renderer uses the original video motion with offline
proportional antialiased Geist. Source TTF, OFL, exact version/hash, glyph list
and regeneration notes live in `assets/fonts/`. `tools/build_geist.py` produces
the bounded static RLE gray4 atlas; firmware needs no runtime font library.
The browser reference uses subpixel typography; this embedded implementation
uses integer advances and a visible fallback for unsupported Unicode scalars.

The glyph table must be sorted and duplicate-free for `std::lower_bound`.
The generator canonicalizes codepoints and validates the explicit replacement
index; insertion order is not lookup order. `test_face_first_font.py` drives real
reading/controls/readiness/speaking workflows and compares RGB565 pixels with an
independent source-TTF raster, including every intended codepoint in replies.
The known return chevron must never be confused with the deliberately unsupported
owl replacement in the long-approval fixture. Preserve the approved pixel-art
portrait and original motion; neither is part of a typography correction.

`Ui::body_lines` and `body_rows` are the shared drawing/scroll contracts.
Response and approval must use them in both `app.cpp` and `app_settings.cpp`;
legacy cards keep fixed-cell wrapping. Do not replace only the drawn font while
leaving scroll/page counts based on the previous 18px cells.

```sh
.venv/bin/python tools/build_geist.py
.venv/bin/python -m cmake -S firmware -B build/face-first -DCMAKE_BUILD_TYPE=Release
.venv/bin/python -m cmake --build build/face-first -j 4
# Run the ctest binary from the installed CMake package; relocated venv script
# shebangs may still refer to an old checkout. Do not alter host configuration.
.venv/lib/python3.14/site-packages/cmake/data/bin/ctest --test-dir build/face-first --output-on-failure
HGSIM_LIBRARY=$PWD/build/face-first/libhgsim.so FACE_ARTIFACTS=artifacts/face-first/green AMOLED_ARTIFACTS=artifacts/face-first/green SWIPE_ARTIFACTS=artifacts/face-first/workflows VIDEO_ARTIFACTS=artifacts/face-first/video .venv/bin/python -m pytest tests/test_face_first.py tests/test_face_first_font.py tests/test_touch_navigation.py tests/test_reply_indicator.py tests/test_round_amoled.py tests/test_round_amoled_safety.py tests/test_video_v2.py tests/test_expressions.py tests/test_sim_hub.py tests/test_firmware_tools.py tests/test_protocol.py tests/test_installer_console.py tests/test_stale_title_hold.py -v --basetemp=$TMPDIR/tstitle --junitxml=artifacts/face-first/results.xml
PLATFORMIO_BUILD_DIR=$PWD/build/face-first-esp32 .venv/bin/python -m platformio run --project-dir firmware/esp32 -e esp32s3-touch-amoled-175c
.venv/bin/python tools/report_face_first.py
```

`artifacts/face-first/REPORT.md` records the initial dirty-tree snapshot, failing
native baseline, fixture corrections, exact final runs, framebuffer contact sheet,
image inspection and limitations. `source.tar.gz` freezes the final source and
`implementation.patch` separates this work from preexisting video-v2 changes.
The report tool expects that baseline snapshot and successful test/build outputs;
it never starts a gateway, flashes, stages OTA or touches a physical device.
Existing visual tests change only their crop/target dimensions to the approved
layout: headline instead of old reply footer, meter y78, portrait y96, 55px read
pill and 48px Stop. Approval, stale contacts, scroll-follow, wake, live preemption
and independent MP4 pixel comparisons remain intact.

### Interaction surface E2E

`tests/test_interaction_surface_e2e.py` covers Silence, Stop work, capture
ownership/Discard, visible tap routes, idle-only settings, equal-emphasis review
and persistent outcomes. `tests/test_interaction_remediation_e2e.py` adds the
review regressions: stop ownership across requests, unattributable `turn.end`,
final text without `turn.end` (including the three-minute expiry, so that file
takes about four minutes), offline/connecting/pairing Settings on round and
rectangular touch profiles, outcome lines in reading and quick controls, and
Silence/Stop order. `tests/test_interaction_ownership_e2e.py` covers remote-work
ownership: a tagged end of earlier work never ends newer unnamed work, a
discarded capture or final text without `turn.start` never ends open work (Stop
once, busy Settings, offline uncertainty, no replay), and text tagged for older
work never replaces the current work's text or carries its outcome. Each workflow runs the native core (App, Ui and
TouchGestures) against the production `DeviceHub` on 127.0.0.1 with a
disposable store; its delegate is the development `EchoBrain`, recording what the
host was asked to do and replying only when the test drives it. Assertions use
device→host wire receipts, the simulator's speaker/microphone HAL calls, hub
delegate calls and RGB565 pixels compared with an independent raster of the
source Geist TTF. No Hermes checkout, provider, gateway or hardware is used.

```sh
uv venv .venv --python 3.14
uv pip install --python .venv/bin/python -e '.[dev,images]' cmake
PATH="$PWD/.venv/bin:$PATH" PYTHONPATH=python .venv/bin/python -m hermes_gadget build-sim --test
mkdir -p /tmp/ti/home && export HGSIM_LIBRARY=$PWD/build/host/libhgsim.so \
  HERMES_HOME=/tmp/ti/home HERMES_AGENT_DIR=/nonexistent IX_ARTIFACTS=$PWD/artifacts/interaction-v1/local
PATH="$PWD/.venv/bin:$PATH" .venv/bin/python -m pytest tests/test_interaction_surface_e2e.py \
  tests/test_interaction_remediation_e2e.py tests/test_interaction_ownership_e2e.py tests/test_touch_navigation.py tests/test_reply_indicator.py tests/test_face_first.py \
  tests/test_face_first_font.py tests/test_round_amoled.py tests/test_round_amoled_safety.py \
  tests/test_stale_title_hold.py tests/test_sim_hub.py tests/test_protocol.py -v \
  --basetemp=/tmp/ti/bt --junitxml=artifacts/interaction-v1/local/results.xml
```

Keep `--basetemp` short; Unix socket paths have a length limit. `IX_ARTIFACTS`
receives `run.json` (environment, library and source hashes, exact command
line), a copy of the fixture file, and per-test snapshots, receipts, HAL logs and
framebuffer hashes. `tests/test_video_v2.py` resolves its MP4 sources at
`../tiny-animations/picks/states-v2/` relative to the checkout's parent; run it
from a copy whose parent contains that directory rather than editing the test.

This work supersedes some face-first geometry, each with its behavioral check
kept: approval Yes/No are equal-emphasis 150×96 targets (no amber Yes); quick
controls show 160×56 Stop work and Silence plus Settings; the reading view has
seven rows above a shared 55px action row; and the swipe-only footers became
visible tap routes. `test_face_first.py` and `test_face_first_font.py` assert the
new rectangles and labels against the same source-TTF oracle, and the glyph
coverage test pages by the advertised `text_rows`.

### Round companion navigation motion

The 466px renderer uses a 220ms integer cubic ease-out arrival translation,
32 pixels vertically for Home/Controls/Reader and horizontally for the Recent
stack. Only explicit user navigation starts motion. The destination is the sole
input model from the first frame; input or a priority activity snaps immediately.
The app tick supplies milliseconds independently of the 100ms expression tick.

A slide renders the destination once into a cache (one extra 466×466 RGB565
buffer, about 434 KB, allocated in PSRAM on first use; the slide snaps if the
allocation fails). Each later frame is the cache shifted and masked to the round
glass, and only the rows that held content in this or the previous frame are
flushed. The last frame is a fresh static render, pixel-identical to the static
view. While a slide runs, the ESP32 main loop polls events without its 10 ms
idle wait. No animation sleep or input lock is introduced.

The AMOLED port stages each flush through two 16-row internal-RAM DMA buffers:
the CPU copies the next chunk out of PSRAM while the previous one is on the
wire, so SPI DMA never reads PSRAM. Direct PSRAM DMA (`psram_dma_direct`) is
kept only as a fallback when internal RAM for the staging rows is unavailable.
Direct PSRAM reads are suspected of stalling the app task during OTA flash
writes. That is unconfirmed on hardware.

The ESP32 port reports display timing as `perf_*` sensors every 2 s while the
screen is drawing: `perf_full_flush_ms` (slowest full-screen flush),
`perf_flush_timeouts` (flushes whose DMA did not finish within 200 ms),
`perf_flush_max_ms`, `perf_flush_ms`/`perf_flush_calls`/`perf_flush_rows`
(totals for the window), `perf_tick_max_ms`, `perf_event_max_ms`,
`perf_busy_ms`, and `perf_motion_frames` (frames drawn by the last slide).
Read them with `hermes gadget debug status`. Measured on the 1.75C at 40 MHz
QSPI: a full-screen flush took 180 ms before the flush-completion interrupt
woke the waiting task, 37 ms after that fix, and 41 ms with direct PSRAM DMA.
Slide frame rates on hardware have not been measured yet.

Round-companion touch boards also offer a `display.bench` device action. When
the device is idle and its screen is awake, it runs Home → Quick controls →
Home slides (plus Recent → Home when the host offers work) and five full
redraws through the normal render path, then returns per-slide frame counts
and per-frame milliseconds, the redraw times, and `min_frames`,
`max_frame_ms`, `redraw_max_ms`. The same three values are also reported as
`perf_bench_*` sensors. The device returns to the view it started on. It
refuses while recording, speaking, answering a question, in settings or during
an update. Invoke it like any device action (the `gadget_action` tool, or
`DeviceSession.invoke_action("display.bench")`). The screen moves for about two
seconds. `tests/test_display_bench_e2e.py` runs it through the loopback DeviceHub.

`tests/test_smooth_motion_e2e.py` checks that every slide frame is a masked
shift of the destination and that every changed row is flushed.

`tests/test_design_pass2_e2e.py` exercises motion, static convergence, row flushes,
mid-motion input, stale approval contact, speech/recording preemption, offline
recovery, outcome hit targets, time-token wrapping and result headers against
the native core plus production loopback DeviceHub. Older navigation helpers
wait on observable transition completion before pixel assertions; raw-contact
workflows test interruption without waiting.

### Releases

`tools/package_release.py` turns PlatformIO builds into release files. For each board:

- **`hermes-gadget-<board>-<version>.bin`:** bootloader, partition table, OTA data and app in one image, from address 0. It is byte for byte what `esptool merge_bin` makes from the same build. Flashed at `0x0`, it also erases the device's settings.
- **`hermes-gadget-<board>-<version>-app.bin`:** the app alone, for `hermes gadget update`.

It also writes `SHA256SUMS` and `manifest.json`, which tells the browser installer each board's chip, flash size and PSRAM, and where the settings partition is. The installer writes everything around the settings, so a device you reinstall keeps its Wi-Fi, server and key. CI packages every board on every change and keeps the files as workflow artifacts.

To publish a release:

1. Set the new version in all four files that carry it: `PROJECT_VER` in `firmware/esp32/CMakeLists.txt`, `pyproject.toml`, `python/hermes_gadget/__init__.py` and `plugin/plugin.yaml`. `python tools/check_versions.py` says whether they agree, and CI fails when they don't.
2. Merge, then push a tag: `git tag v0.2.0 && git push origin v0.2.0`.
3. The **Release** workflow checks the four files against the tag, builds every board in `platformio.ini`, and publishes the files as a GitHub release. Its notes include the command that installs the plugin from the same commit (`hermes plugins install … --ref <commit>`).

To package local builds: `pio run && python tools/package_release.py --all --out dist`.

Each package also includes `hermes-gadget-<version>-licenses.zip`. It contains `LICENSE`, `NOTICE`, `THIRD_PARTY_NOTICES.md`, `LICENSES/`, and license/notice files from the installed managed components and ESP-IDF source. Packaging finds ESP-IDF through `IDF_PATH`, or the PlatformIO framework directory under `PLATFORMIO_CORE_DIR`/`~/.platformio`. Keep the matching dependency sources installed when packaging release binaries. The archive has a checksum in the manifest and `SHA256SUMS`; the site copies it and links it from the installer. When adding a driver, update [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md) and [NOTICE](../NOTICE) in the same PR.

Conventions:

- **The core is single-threaded.** Ports marshal driver events onto the app thread; never call `hg::App` from an ISR or another task.
- **No exceptions, no RTTI.** Prefer `std::string`, `std::vector` and `std::function`; avoid per-frame heap churn in hot paths (mic, audio, rendering).
- **The UI is deterministic.** Anything time-based goes through `UiModel::frame`, which the app advances.
- **New protocol messages** are additive. Update [protocol.md](protocol.md), the route table in `app.cpp`, the hub's `_routes`, and tests on both sides.
