"""T2-C9 battery and power controls: real native core, production loopback hub.

The simulator board ``sim-466x466-amoled`` has the 1.75C's gauge and PMIC as a scripted
power HAL: the test sets percent, USB and charging, and the HAL counts power-offs and
restarts instead of cutting power. The core reads the gauge every 5 s, so each step below
advances the device clock by at least that.

Failure modes covered:
- the battery is invisible on Home, shown when it doesn't matter (on USB and full), or
  drawn in the wrong tone at 20% and 10%;
- boards without a gauge grow a battery mark;
- Quick controls don't say how much charge is left;
- the 20% notice is missed on a dark screen, repeats on every reading, or never re-arms;
- a single low reading shuts Tiny down, the 5% shutdown happens without warning, ignores
  USB plugged in during the countdown, or cuts a turn in flight (it waits up to 10 s);
- Restart and Power off fire on one tap, or don't fire at all.
"""
from __future__ import annotations

import numpy as np
import pytest

from conftest import requires_sim
from test_device_time_e2e import Clock, close, make
from test_interaction_surface_e2e import TEXT, find_text, framebuffer
from test_timer_e2e import advance, settle
from test_touch_navigation import swipe, tap, ui

pytestmark = requires_sim

AMOLED = 'sim-466x466-amoled'
ROUND = 'sim-466x466-round'
BATTERY = (140, 428, 186, 30)   # Home's bottom rim, under "Controls"
HEADER = (0, 40, 466, 44)       # a page's title band


def rgb565(r, g, b):
    return ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)


YELLOW, RED, GREEN = rgb565(242, 201, 76), rgb565(242, 95, 92), rgb565(61, 214, 140)


@pytest.fixture
def rig(tmp_path):
    made = []

    def _make(board=AMOLED, freeze=True):
        r = make(tmp_path / f'r{len(made)}', Clock(), board=board)
        made.append(r)
        if freeze:
            r.s.vclock[0] = r.s.now_ms()
            r.s.now_ms = lambda: r.s.vclock[0]
            r.s.step()
            settle(r)
        else:
            r.s.run_for(0.4)
        return r
    yield _make
    for r in made:
        close(r)


def power(r, pct, usb=False, charging=None, frozen=True):
    """The gauge reads ``pct``; the core picks it up at its next 5 s read."""
    r.s.set_power(percent=pct, mv=3300 + pct * 9, usb=usb, charging=usb if charging is None else charging)
    if frozen:
        advance(r, 5)
    else:
        r.s.run_for(5.3)


def hal(r):
    return r.s.device.hal_state()


def pixels(r, box):
    x, y, w, h = box
    return framebuffer(r.s)[y:y + h, x:x + w]


def test_home_shows_the_battery_while_it_matters(rig):
    r = rig()
    power(r, 76)
    u = ui(r.s)
    assert u['battery'] == {'percent': 76, 'tone': 'normal'}, u
    assert int((pixels(r, BATTERY) != 0).sum()) > 60, 'no battery mark on Home'
    r.snap('battery-76')
    power(r, 76, usb=True, charging=True)
    assert ui(r.s)['battery'] == {'percent': 76, 'tone': 'charging'}
    assert (pixels(r, BATTERY) == GREEN).any(), 'charging is not shown'
    r.snap('battery-charging')
    power(r, 100, usb=True, charging=False)
    assert 'battery' not in ui(r.s), 'a full battery on USB needs no mark'
    assert int((pixels(r, BATTERY) != 0).sum()) == 0


@pytest.mark.parametrize('pct,tone,color', [(21, 'normal', None), (20, 'low', YELLOW), (11, 'low', YELLOW),
                                            (10, 'critical', RED), (6, 'critical', RED)])
def test_the_mark_turns_amber_then_red(rig, pct, tone, color):
    r = rig()
    power(r, pct)
    assert ui(r.s)['battery'] == {'percent': pct, 'tone': tone}
    if color is not None:
        assert (pixels(r, BATTERY) == color).any(), f'{tone} drawn in the wrong colour'
    if pct <= 10:
        assert ui(r.s)['detail'] == 'Low battery: connect USB'


def test_boards_without_a_gauge_show_no_battery(rig):
    r = rig(ROUND)
    advance(r, 6)
    assert 'battery' not in ui(r.s)
    assert 'power' not in r.s.status()
    assert int((pixels(r, BATTERY) != 0).sum()) == 0


def test_quick_controls_say_how_much_charge_is_left(rig):
    r = rig(freeze=False)
    power(r, 64, frozen=False)
    swipe(r.s, dy=100)
    r.s.run_for(0.3)
    assert ui(r.s)['view'] == 'controls'
    assert find_text(r.s, '64% · Battery', 24, TEXT, 0, HEADER), 'Quick controls do not show the charge'
    r.snap('controls-battery')
    power(r, 64, usb=True, charging=True, frozen=False)
    assert find_text(r.s, '64% · Charging', 24, TEXT, 0, HEADER)


def test_the_20_percent_notice_is_seen_once(rig):
    r = rig()
    power(r, 22)
    advance(r, 61)
    assert r.s.status()['display']['sleeping']
    power(r, 20)
    assert not r.s.status()['display']['sleeping'], 'the 20% notice arrived on a dark screen'
    assert ui(r.s)['detail'] == 'Battery 20% · charge soon', ui(r.s)
    r.snap('notice-20')
    advance(r, 12)
    assert ui(r.s)['detail'] != 'Battery 20% · charge soon'
    for pct in (19, 18, 17):
        power(r, pct)
        assert 'charge soon' not in ui(r.s)['detail'], 'the notice repeated'
    # Charging re-arms it for the next discharge.
    power(r, 40, usb=True, charging=True)
    power(r, 20)
    assert ui(r.s)['detail'] == 'Battery 20% · charge soon'


def test_at_5_percent_tiny_warns_then_powers_off(rig):
    r = rig()
    power(r, 6)
    power(r, 5)
    assert hal(r)['power_offs'] == 0 and 'shutdown_in_s' not in r.s.status()['power'], \
        'one low reading is not enough'
    power(r, 5)
    st = r.s.status()['power']
    assert 0 < st['shutdown_in_s'] <= 10, st
    u = ui(r.s)
    assert r.s.status()['screen'] == 'card' and u['headline'] == 'Battery empty', u
    r.snap('battery-empty')
    advance(r, 11)
    assert hal(r)['power_offs'] == 1


def test_plugging_in_cancels_the_shutdown(rig):
    r = rig()
    power(r, 5)
    power(r, 5)
    assert 'shutdown_in_s' in r.s.status()['power']
    power(r, 5, usb=True, charging=True)
    assert 'shutdown_in_s' not in r.s.status()['power']
    assert r.s.status()['screen'] != 'card'
    advance(r, 20)
    assert hal(r)['power_offs'] == 0


def test_the_shutdown_waits_for_a_turn_in_flight(rig):
    r = rig()
    power(r, 5)
    r.turn_start('turn-L')
    r.delta('Turning off the lamp', turn='turn-L')
    power(r, 5)
    advance(r, 11)
    assert hal(r)['power_offs'] == 0, 'the shutdown cut a turn in flight'
    r.turn_end('turn-L', 'success')
    settle(r)
    advance(r, 1)
    assert hal(r)['power_offs'] == 1
    # A turn that never ends gets 10 s, not forever.
    r2 = rig()
    power(r2, 5)
    r2.turn_start('turn-M')
    r2.delta('Still going', turn='turn-M')
    power(r2, 5)
    advance(r2, 11)
    assert hal(r2)['power_offs'] == 0
    advance(r2, 10)
    assert hal(r2)['power_offs'] == 1


def to_row(r, name):
    s = r.s
    s.touch(True, 233, 62)
    s.run_for(1.3)
    s.touch(False)
    s.step()
    assert s.status()['screen'] == 'settings'
    for _ in range(20):
        if ui(s)['detail'] == name:
            return
        swipe(s, dy=100)
    raise AssertionError(f'no {name} row in Settings')


def test_restart_and_power_off_take_two_taps(rig):
    r = rig(freeze=False)
    power(r, 50, frozen=False)
    to_row(r, 'Restart')
    tap(r.s, 233, 220)
    assert hal(r)['restarts'] == 0, 'Restart fired on one tap'
    assert ui(r.s)['hint'].startswith('Tap again to restart'), ui(r.s)
    tap(r.s, 233, 220)
    assert hal(r)['restarts'] == 1
    swipe(r.s, dy=100)
    assert ui(r.s)['detail'] == 'Power off'
    tap(r.s, 233, 220)
    assert hal(r)['power_offs'] == 0, 'Power off fired on one tap'
    assert ui(r.s)['hint'].startswith('Tap again to power off'), ui(r.s)
    tap(r.s, 233, 220)
    assert hal(r)['power_offs'] == 1
