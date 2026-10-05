# Tiny state-aware swipes — local delivery

> Historical pre-install report. Later OTA activation succeeded and the user
> confirmed the working firmware's usability. See [CHECKPOINT.md](CHECKPOINT.md)
> for current status, private-release assets, and the curated evidence inventory.
> Statements below about uncommitted changes, no flash, and Tiny being untouched
> describe the original delivery stage, not the checkpoint. Raw intermediate
> evidence and screenshots referenced below remain local and are not all uploaded.

## Outcome and scope

Implemented in branch `tiny/state-aware-swipes`, based on `323e3303ab68981f810fc3208119cd8a22e64af0`. Changes remain uncommitted. **No flash, OTA, device restart, live plugin/config/voice changes, publish, or production provider requests were performed.**

Exact firmware: **esp32s3-touch-amoled-175c**, ESP32-S3, **32 MB** flash, octal PSRAM. This is not the non-C board. The shared implementation applies to touch profiles; physical behavior on any board remains unverified.

## Verified results

- `delivery.xml` / `delivery.log`: **139 passed, 30 skipped, no failures**, including **22 touch E2E workflows**. Two Tkinter finalizer warnings occur after desktop UI tests (`main thread is not in main loop`); not suppressed or fixed by this change.
- `core-delivery.log`: CTest passed; existing executable contains 60 cases. Two obsolete touch contracts were migrated to the approved behavior (swipe no longer discards/answers), not removed. No new isolated/unit tests were added.
- `firmware-delivery.log`: exact board compilation and config/size checks passed. App binary 1,273,552 bytes; about 37% OTA slot headroom. Existing managed-component Kconfig warning remains; the earlier full compile also reports the existing deprecated touch-coordinate API.
- `site-tests.log`: 29 tests passed. `site-build.log`: 19 documentation pages built; local links/anchors verified. No browser-installer E2E was run because its interaction code was unchanged.
- `firmware/manifest.json`, `firmware/SHA256SUMS`: packaged board identity, 32 MB flash, checksums and licenses verified against file bytes.
- `environment.json`: actual interpreter, packages, compiler, PlatformIO packages, Node/npm, base and branch. Native simulator uses production C++ core and renderer, real loopback hub/WebSocket, and simulated peripherals.

Skips: 24 require importable Hermes classes, one requires explicit gateway E2E opt-in, three require optional MQTT package, two are collection skips. The live Hermes installation was deliberately excluded with `HERMES_AGENT_DIR=/nonexistent`.

## Acceptance table

All PASS below means native-simulator/software evidence, not hardware validation. Test names refer to `tests/test_touch_navigation.py`.

| Requirement | Result / evidence |
|---|---|
| Views independent of activity | PASS: `home_controls_preserve_activity` across idle, thinking, streaming, speaking; navigation never changes work/audio activity |
| HOME up → latest reply, down → controls | PASS: response return/stream-follow workflow and four activity cases |
| HOME left/right no-op | PASS: both horizontal parameter cases in `home_ambiguous_horizontal_and_jitter_never_cancel` |
| RESPONSE vertical scroll only; boundaries never navigate | PASS: repeated top/bottom gestures, framebuffer changes, bounded scroll; `response_scroll_bounds_return_and_stream_follow` |
| RESPONSE right → Home, retained position on return | PASS: same workflow; final/idle retention also covered |
| RESPONSE left no-op | PASS: `response_position_survives_final_and_idle_time` |
| CONTROLS vertical only over hit sliders | PASS: real volume/brightness rectangles have rendered pixels; drags change persisted settings; outside drag leaves view unchanged |
| CONTROLS right closes; left no-op | PASS: four activity cases; left preserves settings |
| APPROVAL vertical scroll; horizontal no-op | PASS: long question framebuffer changes; both horizontals produce no decision |
| APPROVAL explicit Yes/No only | PASS: actual rendered buttons; body taps, swipes, release outside do not answer; explicit buttons do |
| SPEAKING navigation does not stop audio | PASS: status throughout Home/controls/approval; literal PCM travels through native audio path and is recovered byte-for-byte from recorded WAV |
| THINKING navigation does not cancel; Home indicator truthful | PASS: activity/headline and protocol checks; displayed hint no longer says swipe-to-stop |
| Previous reply remains readable while next turn thinks | PASS: `thinking_can_read_last_reply_without_losing_activity`; new reply resets follow position |
| RECORDING suppresses navigation | PASS: four directions cannot end/cancel external recording; recording beginning midgesture is not released; existing hold-to-talk core test still passes |
| STREAMING follows only at bottom | PASS: scroll away holds across deltas; returning to bottom restores follow; final reply/idle time preserve position |
| Gesture belongs to starting view | PASS: response arrives during Home drag yet drag still opens controls |
| Prompt/state changes midgesture safe | PASS: arriving/replaced prompts do not consume old contact; new turn cannot receive old Stop press |
| Diagonals, jitter, release outside | PASS: diagonal/horizontal/jitter cases; out-of-button drags on Stop/approval; invalid release coordinates ignored |
| No new/reset swipe | PASS: protocol assertions; navigation does not call Cancel or session.new; physical/console explicit controls unchanged |
| Explicit Stop retained | PASS: rendered Stop button cancels work; drag away does not |
| Legacy local workflows not stranded | PASS: settings selection/next-item touch; overlay dismiss does not cancel work; long-card auto-page; existing Wi-Fi setup core case |
| Exact board build / no flash | PASS: PlatformIO environment and package manifest; build/package only |

## Artifacts and hashes

Under `firmware/`:

- `hermes-gadget-esp32s3-touch-amoled-175c-0.2.0-app.bin`
  - SHA-256 `00f90b6a52d86f77c8e02de7e3130ca2e00906fef3da742b3d65111359361c17`
- `hermes-gadget-esp32s3-touch-amoled-175c-0.2.0.bin` (merged USB image)
  - SHA-256 `5c7551a817421041698fe2011f420a5226bc1af3f1e2f9181b6ebf7a0fc991a0`
- License archive and its checksum are also included.

Version was intentionally not bumped: these are local candidate images still labeled 0.2.0. Identify them by SHA-256, not version alone.

`delivery/` holds per-workflow PNGs, protocol fixtures/receipts, final UI state and framebuffer SHA-256. `volume-rendered.png`, `brightness-rendered.png`, `stop-rendered.png`, `yes-rendered.png`, `no-rendered.png` show actual controls. Framebuffer review found no clipping or overlap at 466×466; lower-contrast hints and dense long text remain existing visual constraints.

`source.patch` and `source-snapshot.tar.gz` freeze final changes; `fixtures/test_touch_navigation.py` contains exact literal inputs and assertions. `sdkconfig.esp32s3-touch-amoled-175c`, `dependencies.lock` and `environment.json` preserve build settings/dependency versions. `artifact-hashes.json` covers artifacts and the native shared library (excludes itself and the collector's output log).

## Exact final rerun

From `.` with the installed `.venv`:

```bash
PATH="$PWD/.venv/bin:$PATH" .venv/bin/hermes-gadget build-sim --test \
  > artifacts/swipes/core-delivery.log 2>&1
HERMES_AGENT_DIR=/nonexistent HERMES_GADGET_UI_TESTS=1 \
  SWIPE_ARTIFACTS=artifacts/swipes/delivery \
  xvfb-run -a .venv/bin/pytest \
  --basetemp=$TMPDIR/hg-swipes \
  -q --tb=short --junitxml=artifacts/swipes/delivery.xml \
  > artifacts/swipes/delivery.log 2>&1
(cd firmware/esp32 && \
  PATH="./.venv/bin:$PATH" \
  ../../.venv/bin/pio run -e esp32s3-touch-amoled-175c \
  > ../../artifacts/swipes/firmware-delivery.log 2>&1 && \
  ../../.venv/bin/python tools/package_release.py \
  --board esp32s3-touch-amoled-175c --out ../../artifacts/swipes/firmware \
  > ../../artifacts/swipes/package.log 2>&1)
(cd site && npm ci && npm test && npm run build)
.venv/bin/python tools/collect_swipe_evidence.py
(cd artifacts/swipes/firmware && sha256sum -c SHA256SUMS)
```

For focused workflow testing, substitute `tests/test_touch_navigation.py -v` for the full pytest suite. No provider keys or live device are needed. Keep a short explicit basetemp: the first broad run hit an existing AF_UNIX socket-path-length limit with pytest's longer default directory. The shorter scratch path fixed that environmental failure without altering tests.

The final source patch can be applied to a clean checkout at the recorded base with `git apply /absolute/path/source.patch`; then install `.[dev]`, CMake, Ninja and PlatformIO as recorded in `environment.json`. PlatformIO upstream dependencies are not globally pinned by this project; reproduce using the recorded installed package versions and frozen lock/config. Rebuilt binaries may differ in embedded build timestamps/paths, so use the supplied hashes to identify this exact candidate, not as a promise of bit-for-bit reproducible compiler output.

## Test-first chronology and evidence limitations

Initial `red.xml` records 14 failures before production changes, including down-as-Cancel, recording discarded by navigation, and unscrollable approval. Later `red-lifecycle.xml`, `red-last-reply.xml`, `red-overlay.xml`, and `red-hints2.xml` record targeted regressions before their fixes. `results-index.json` enumerates actual counts for every retained JUnit run. All run directories preserve their actual protocol inputs/outputs and screenshots; all used the same installed environment recorded here.

Two harness issues were corrected transparently: an initially missing `ui.hint` diagnostic was added to reveal the real stale rendered instruction (`Swipe down to stop`), then the behavior was fixed; the initial legacy-card wait of 10 seconds was shorter than its row-based dwell and was replaced by an observable condition with a 20-second timeout. Full final suite passes.

Intermediate source states were not individually committed/frozen, so the final source snapshot and rerun are exact, while historical red logs are chronology evidence rather than independently frozen intermediate builds. No fabricated logs or results were substituted.

## Remaining limitations

- No physical CST9217 touch samples, latency, orientation, diagonal ergonomics, round-edge contacts, physical audio, power, Wi-Fi, OTA or endurance validation. Tiny remains untouched and its board's experimental status is unchanged.
- Swipe navigation and push-to-talk still share the existing 120 ms stationary hold threshold. Movement must begin before hold recognition; once recording starts, moving does not navigate, and releasing the original talk contact retains normal send behavior. Physical tuning needs a later authorized hardware trial.
- Sliders adjust once per qualifying vertical gesture, not continuously per sample. Brightness quick control is bounded to 10–100 to avoid accidentally darkening the display; volume is 0–100.
- Legacy full settings may still intentionally interrupt activity when invoked via its explicit console/physical chord. The new quick-controls path never invokes it. Title hold is available only while idle.
- Physical/console CANCEL behavior remains unchanged. This does not invent a CANCEL hardware key on the 1.75C, whose PWR is not mapped to CANCEL.
- Broader physical board matrix and production Hermes provider/gateway E2E were not run. Software native tests cover shared code, not all board drivers.

## Future flashing / rollback — NOT EXECUTED

Only proceed after separate explicit approval, board-label confirmation, power/USB recovery readiness, and selection of a settings-preserving versus destructive route.

1. Verify `firmware/SHA256SUMS` and select only the **175c / 32 MB** artifact.
2. Preferred settings-preserving USB route: use the project's browser installer with this manifest, which writes around the manifest's settings partition. Alternatively use the documented PlatformIO upload of this built environment, after confirming the intended serial port:
   `cd firmware/esp32 && ../../.venv/bin/pio run -e esp32s3-touch-amoled-175c -t upload --upload-port SERIAL_PORT`
   This command uploads/restarts the board; it was **not** run.
3. Do not manually flash the merged image at address 0 without accepting settings erasure. The project's development guide explicitly warns that its merged image includes erased settings space.
4. App-only OTA must use the existing authenticated updater, with approval; do not serve or push this image automatically. OTA/restart/rollback behavior has not been tested in this task.
5. Firmware rollback requires a separately retained known-good **same-board** image, or a separate checkout/build of the recorded base, followed by an explicitly approved recovery upload. No backup of Tiny's current flash was taken, so exact restoration of its present binary cannot be promised. A known base build is not necessarily byte-identical to the currently installed release.
6. Source-only rollback can use `git apply --reverse --check artifacts/swipes/source.patch` followed, after reviewing scope, by `git apply --reverse artifacts/swipes/source.patch`. This removes only the recorded change set when it still applies cleanly. Preserve artifacts and any later user edits. It does not affect the physical device.
