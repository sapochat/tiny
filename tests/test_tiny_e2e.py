"""Tiny's behaviour on top of upstream Hermes Gadget, end to end.

Each test drives the native device core in the simulator against the real device hub
(the development brain), the same path the firmware takes on the Waveshare AMOLED 1.75C.

- PWR is Silence while something is sounding (speech or a ringing timer), and the
  screen stays as it is; with nothing sounding it keeps upstream's screen off/on.
- An AMOLED rests by default: 60 s screen timeout at 80% brightness unless a value is stored.
- On battery at 5% (two readings in a row) the device warns, then powers off cleanly;
  USB during the countdown cancels it.
- Settings has Restart (select twice), which restarts the device.
"""

from __future__ import annotations

import asyncio
import math
import struct

from conftest import requires_sim

pytestmark = requires_sim

AMOLED = "sim-466x466-amoled"


def _tone(seconds: float, rate: int = 16000) -> bytes:
    n = int(seconds * rate)
    return struct.pack(f"<{n}h", *(int(6000 * math.sin(2 * math.pi * 440 * i / rate)) for i in range(n)))


def _ready(make_sim, url, **kw):
    sim = make_sim(url, board=AMOLED, name="Tiny", **kw)
    assert sim.wait_screen("ready", timeout=10)
    return sim


def _session(hub):
    return next(iter(hub.sessions.values()))


def _sounding(sim) -> bool:
    return sim.speaker._open


def _play(loop_thread, sim, session, seconds: float, turn: str | None):
    fut = asyncio.run_coroutine_threadsafe(session.play_pcm(_tone(seconds), 16000, turn=turn), loop_thread.loop)
    assert sim.wait_for(fut.done, timeout=10)
    return fut.result()


def test_pwr_silences_speech_and_late_audio_for_that_turn_stays_quiet(loop_thread, devserver, make_sim):
    hub, _brain, url = devserver()
    sim = _ready(make_sim, url)
    session = _session(hub)
    _play(loop_thread, sim, session, 4.0, turn="t1")
    assert sim.wait_for(lambda: _sounding(sim), timeout=3)

    sim.tap("power")
    assert sim.wait_for(lambda: not _sounding(sim), timeout=2)
    sim.run_for(0.3)
    assert sim.status()["display_sleeping"] is False  # Silence leaves the screen as it is

    _play(loop_thread, sim, session, 1.0, turn="t1")  # more speech for the silenced turn
    sim.run_for(0.4)
    assert not _sounding(sim)

    _play(loop_thread, sim, session, 2.0, turn="t2")  # a new turn is heard again
    assert sim.wait_for(lambda: _sounding(sim), timeout=3)


def test_pwr_with_nothing_sounding_turns_the_screen_off_and_on(devserver, make_sim):
    _hub, _brain, url = devserver()
    sim = _ready(make_sim, url)
    sim.tap("power")
    assert sim.wait_for(lambda: sim.status()["display_sleeping"] is True, timeout=2)
    sim.tap("power")
    assert sim.wait_for(lambda: sim.status()["display_sleeping"] is False, timeout=2)


def test_pwr_silences_a_ringing_timer_and_the_alarm_stays_up(loop_thread, devserver, make_sim):
    hub, _brain, url = devserver()
    sim = _ready(make_sim, url)
    session = _session(hub)
    fut = asyncio.run_coroutine_threadsafe(session.invoke_action("timer.start", {"seconds": 1}), loop_thread.loop)
    assert sim.wait_for(fut.done, timeout=5)
    assert sim.wait_screen("alarm", timeout=5)
    assert sim.wait_for(lambda: _sounding(sim) or sim.device.status().get("timer", {}).get("ringing"), timeout=3)

    sim.tap("power")
    sim.run_for(1.5)  # past the next beep cycle
    assert not _sounding(sim)
    assert sim.device.screen() == "alarm"
    assert sim.status()["display_sleeping"] is False


def test_amoled_rests_by_default_and_a_stored_setting_wins(devserver, make_sim):
    _hub, _brain, url = devserver()
    sim = _ready(make_sim, url)
    assert (sim.status()["screen_timeout_s"], sim.status()["brightness"]) == (60, 80)
    assert sim.console("set screen_timeout 0").startswith("@ok")
    assert sim.status()["screen_timeout_s"] == 0  # Always on, stored, wins

    other = make_sim(url, board="sim-466x466-round", name="Upstream", state="other")
    assert other.wait_screen("ready", timeout=10)
    assert (other.status()["screen_timeout_s"], other.status()["brightness"]) == (0, 100)  # upstream boards unchanged


def test_battery_empty_warns_then_powers_off_cleanly(devserver, make_sim):
    _hub, _brain, url = devserver()
    sim = _ready(make_sim, url)
    sim.set_power({"battery_present": True, "battery_percent": 5, "battery_mv": 3400, "charging": False,
                   "external_power": False})
    assert sim.wait_for(lambda: "shutdown_in_s" in sim.status().get("power", {}), timeout=15)
    assert sim.device.power_offs() == 0
    assert sim.wait_for(lambda: sim.device.power_offs() == 1, timeout=15)


def test_usb_during_the_countdown_keeps_the_device_on(devserver, make_sim):
    _hub, _brain, url = devserver()
    sim = _ready(make_sim, url)
    sim.set_power({"battery_present": True, "battery_percent": 4, "battery_mv": 3390, "charging": False,
                   "external_power": False})
    assert sim.wait_for(lambda: "shutdown_in_s" in sim.status().get("power", {}), timeout=15)
    sim.set_power({"battery_present": True, "battery_percent": 4, "battery_mv": 3600, "charging": True,
                   "external_power": True})
    assert sim.wait_for(lambda: "shutdown_in_s" not in sim.status().get("power", {}), timeout=8)
    sim.run_for(12)
    assert sim.device.power_offs() == 0


def test_restart_from_settings(devserver, make_sim):
    _hub, _brain, url = devserver()
    sim = _ready(make_sim, url)
    assert sim.console("settings").startswith("@ok")
    for _ in range(60):
        if sim.status().get("menu") == "Restart":
            break
        sim.console("cancel")
    assert sim.status().get("menu") == "Restart"
    sim.console("talk"); sim.console("release")
    sim.run_for(0.2)
    assert sim.restarts == 0  # the first select asks to confirm
    sim.console("talk"); sim.console("release")
    assert sim.wait_for(lambda: sim.restarts == 1, timeout=5)
    assert sim.wait_screen("ready", timeout=15)
