# Tiny

Tiny is Santi's Hermes Gadget: a Waveshare ESP32-S3 Touch AMOLED 1.75C running upstream
[Hermes Gadget](https://github.com/Adolanium/hermes-gadget-sdk) with a small set of patches.
Since 2026-11-08 Tiny tracks upstream's interface, faces and plugin wholesale. The round UI Tiny
built on its own after forking at 0.2.0 (expression video face, Home/quick controls/Recent,
Geist type, request-tagged turns, Tiny's own timers) was retired in that merge. It remains in
git history before the merge commit.

Everything Tiny adds is listed below. Each change is marked `Tiny:` in the source, so the next
upstream merge can find it.

## What Tiny changes

| Area | Change | Where |
| --- | --- | --- |
| Flash layout | The 1.75C uses two 8 MB app slots on its 32 MB flash, instead of upstream's two 1.94 MB slots. NVS, otadata and phy_init keep upstream's offsets, so settings and the device key survive. Over-the-air updates can't change the partition table, so a board still on `partitions.csv` needs one USB flash first. | `firmware/esp32/partitions-32mb.csv`, `platformio.ini`, `boards/esp32s3-touch-amoled-175c/sdkconfig.defaults` |
| PWR is Silence | While something is sounding, a short PWR press quiets it and does nothing else. Speech stops, but the turn and its text continue, and later speech for that turn stays quiet. A ringing timer stops beeping and stays on screen. With nothing sounding, PWR behaves as it does upstream (screen off/on, Back in menus). | `App::silence`, `App::on_power_key`, `DeviceProfile::pwr_silence` |
| Screen rest | The AMOLED rests by default: a 60 s screen timeout at 80% brightness. A stored setting wins, including 0 (always on). | `DeviceProfile::default_screen_timeout_s`, `default_brightness` |
| Battery-empty shutdown | On battery at 5% or less for two readings in a row (5 s apart), a **Battery empty** card counts down 10 s, then the board powers off through the PMIC. A recording, open turn or speech gets up to 10 s more. USB during the countdown cancels it. Upstream's low-battery alerts are unchanged. | `App::shutdown_check`, `DeviceProfile::shutdown_percent` |
| Restart | Settings has **Restart** (select twice). It closes Settings and restarts through the updater. | `Menu::Restart` |
| Status | `status` also reports `screen_timeout_s`, `brightness`, `menu` (the selected Settings item) and `power.shutdown_in_s` during a countdown. | `App::status_json` |
| Diagnostics | `diag` adds `chips`: read-only registers of chips that answered the I2C scan. These are QMI8658 WHO_AM_I/revision at 0x6a/0x6b, plus the AXP2101 chip id, IRQ level, interrupt enables and flags. | `firmware/esp32/main/port_diag.cpp` |
| `hermes gadget debug` | Live diagnostics from the running gateway over a same-user Unix socket, never a network listener. `status` is read-only. `display` and `tone` need `--confirm` and refuse a busy or unapproved device. Turn it off with `platforms.gadget.extra.local_debug: false`. | `plugin/debug.py` |
| Gateway E2E guard | The gateway tests refuse a temporary `HERMES_HOME` inside `~/.hermes`, where it would contend with the real gateway. Pass `--basetemp` outside it. | `tests/test_gateway_e2e.py` |

Display performance needs no patch. Upstream's AMOLED port already flushes through an
internal-RAM DMA bounce buffer, which was the main gain of Tiny's display work. Tiny's slide
optimisations only served the retired UI.

## Firmware version

The 1.75C image is versioned `<upstream>-tiny.<n>` (for example `0.5.0-tiny.1`) in
`platformio.ini`. Bump `n` for each Tiny-only change, and reset it on each upstream merge.

## Simulator

`sim-466x466-amoled` is the 1.75C as Tiny runs it: upstream's round 466 board with a PWR key
(`power` button, simulator ABI 9) and Tiny's defaults. `hgsim_power_offs` counts power-offs.

## Tests

```
hermes-gadget build-sim --test
PYTHONPATH=python pytest tests/test_tiny_e2e.py
HERMES_GADGET_E2E=1 HERMES_AGENT_DIR=~/.hermes/hermes-agent \
  PYTHONPATH=python pytest tests/test_debug_bridge_e2e.py --basetemp=build/pytest-gateway
```

## Taking upstream changes

```
git fetch upstream
git merge upstream/main
```

Conflicts should be limited to the lines marked `Tiny:`. After a merge, run the full suite with
`HERMES_GADGET_E2E=1` and a `--basetemp` outside `~/.hermes`. Build `esp32s3-touch-amoled-175c`
and check `check_size` against the 8 MB slot, then reset the version suffix.
