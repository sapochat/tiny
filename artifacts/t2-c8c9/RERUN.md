# T2-C8/C9: screen rest, PWR screen off, battery controls

Run on mini (Linux 7.0.0-43-generic), 2026-11-07, from `main` at `d7a758a` plus the
uncommitted C8/C9 changes (committed right after this receipt).

## What changed

- AMOLED boards rest the screen by default: 60 s timeout, 80% brightness, used only while
  nothing is stored. Dark means CO5300 0x28 + 0x10 and no flushes; wake is 0x11 + 0x29 at
  least 120 ms after sleep in, a full repaint, then brightness.
- PWR with nothing sounding turns the screen off, or back on. While speech or a ringing timer
  sounds it stays Silence and leaves the screen alone.
- Battery: Home rim mark (grey, amber ≤20%, red ≤10%, green charging; hidden on USB when full),
  Quick controls title `NN% · Battery|Charging|Plugged in`, one 20% notice (re-arms on charge or
  >25%), clean PMIC power-off after two readings ≤5% with a 10 s card (USB cancels; a turn in
  flight gets ≤10 s more), `status.power.shutdown_in_s`.
- Settings → Restart (two taps, `esp_restart`). Power off now says "Tap again to power off"
  once armed.
- Simulator ABI 7: `sim-466x466-amoled` board with a scripted gauge (`Simulator.set_power`),
  counted panel sleeps, power-offs and restarts (`device.hal_state()`).

## Results

| Check | Result | Log |
|---|---|---|
| RED before the core changes | 19 failed, 7 passed (six PWR Silence cases shipped in B1, plus the no-gauge guard) | `red.log` |
| C8/C9/PWR E2E | 26 passed in 61.91 s | `green.log`, screenshots in `run/` |
| Full suite | 436 passed, 39 skipped, 0 failed in 1194.52 s | `full-suite/pytest.log` |
| Frozen pre-M3 hub lane (skipped in the full run) | 1 passed in 3.27 s | `legacy-hub/result.txt` |
| ESP build `esp32s3-touch-amoled-175c` | SUCCESS, app 1804 KB, 78% of ota_0 free | `build-175c.log`, `build-175c-t2.2.log` |
| ESP build `esp32s3-lcd-154` | SUCCESS | `build-154.log` |

New skips against the B1 run: `test_debug_bridge_e2e.py` (opt-in, `HERMES_GADGET_E2E=1`) and
`test_new_native_with_frozen_legacy_host` (needs `WORK_LEGACY_HUB`; run separately above).

Candidate: `candidate/tiny-t2.2-175c-app.bin`, `0.2.0-tiny-t2.2`,
SHA-256 `71d44216b1f28a689e5119f2b3e555ed9efb543523fb318ffab127dcaa97ecfc`.

## Rerun

```sh
cd ~/projects/tiny
export PATH=$PWD/.venv/bin:$PATH
cmake -S firmware -B build/t2-c8c9 -DCMAKE_BUILD_TYPE=Release && cmake --build build/t2-c8c9 -j16
HGSIM_LIBRARY=$PWD/build/t2-c8c9/libhgsim.so .venv/bin/python -m pytest \
  tests/test_screen_rest_e2e.py tests/test_battery_power_e2e.py tests/test_pwr_silence_e2e.py \
  -p no:cacheprovider -q --basetemp=$PWD/artifacts/t2-c8c9/run
RUN_NAME=t2-c8c9/full-suite .venv/bin/python artifacts/turn-attribution/full-suite/RERUN.py
git show 2a9eac8^:plugin/hub.py > /tmp/hub-pre-m3.py   # SHA-256 4ff1b127…9104b
WORK_LEGACY_HUB=/tmp/hub-pre-m3.py HGSIM_LIBRARY=$PWD/build/t2-c8c9/libhgsim.so \
  .venv/bin/python -m pytest tests/test_work_shelf_e2e.py -k frozen_legacy_host -q
cd firmware/esp32   # main's venv has no PlatformIO; the interaction-v1 worktree's does
~/projects/tiny-worktrees/interaction-v1/.venv/bin/pio run -e esp32s3-touch-amoled-175c
~/projects/tiny-worktrees/interaction-v1/.venv/bin/pio run -e esp32s3-lcd-154
```

## Not verified here

Everything above is simulator or build evidence. Not yet measured on Tiny 2: panel current
asleep vs awake, wake latency from touch and PWR, the rim mark against the real AXP2101 gauge,
the 20% notice and the 5% shutdown on a draining battery. Standby (Wi-Fi off after 15 min on
battery) is not implemented; it waits on the slow-reconnect diagnosis.
