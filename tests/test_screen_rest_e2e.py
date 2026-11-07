"""T2-C8 screen rest: real native core, production loopback hub, disposable stores.

The AMOLED 1.75C ships with screen rest on: when the stored settings say nothing, it dims
at 30 s idle and goes dark at 60 s, at 80% brightness. Dark means the panel is told to
sleep (display off, sleep in) and no pixels are sent until something wakes it. PWR with
nothing to silence turns the screen off at once and back on. The simulator board
``sim-466x466-amoled`` carries that board's profile; ``sim-466x466-round`` keeps the old
defaults (Always on, 100%).

Failure modes covered:
- the board defaults don't apply, or override a choice Santi stored (including Always on);
- going dark only zeroes brightness: the panel stays awake or frames keep flushing to it;
- waking leaves the panel asleep, the brightness at 0, or the glass stale;
- the first touch on a dark screen does something besides waking it;
- PWR doesn't toggle the screen, or a screen PWR turned off is woken by the same turn's
  text or the idle check, while new work, an approval or input still wake it;
- other boards change behaviour.
"""
from __future__ import annotations

import pytest

from conftest import requires_sim
from test_device_time_e2e import Clock, close, make
from test_timer_e2e import advance, settle
from test_touch_navigation import tap, ui

pytestmark = requires_sim

AMOLED = 'sim-466x466-amoled'
ROUND = 'sim-466x466-round'
SILENCE_KEY = 4  # HGSIM_BUTTON_SILENCE: the 1.75C's PWR key
REQUESTS = {'text', 'audio.start', 'audio.end', 'audio.cancel', 'cancel', 'session.new', 'prompt.reply'}


@pytest.fixture
def rig(tmp_path):
    made = []

    def _make(board=AMOLED):
        r = make(tmp_path / f'r{len(made)}', Clock(), board=board)
        made.append(r)
        # Freeze the device clock: time moves only when the test advances it.
        r.s.vclock[0] = r.s.now_ms()
        r.s.now_ms = lambda: r.s.vclock[0]
        r.s.step()
        settle(r)
        return r
    yield _make
    for r in made:
        close(r)


def display(r):
    return r.s.status()['display']


def hal(r):
    return r.s.device.hal_state()


def backlight(r):
    return r.s.peripherals.backlight


def pwr(r):
    r.s.device.button(SILENCE_KEY, True)
    r.s.device.button(SILENCE_KEY, False)
    r.s.step()
    settle(r, 0.3)


def test_the_amoled_board_rests_by_default(rig):
    r = rig()
    d = display(r)
    assert d['timeout_s'] == 60 and d['brightness'] == 80, d
    assert backlight(r) == 80
    assert r.s.console('get screen_timeout') == '@value {"key":"screen_timeout","value":""}', \
        'the default must not be written into the stored settings'
    advance(r, 28)
    assert not display(r)['dimmed']
    advance(r, 4)
    d = display(r)
    assert d['dimmed'] and not d['sleeping'], d
    assert 0 < backlight(r) <= 10
    advance(r, 30)
    d = display(r)
    assert d['sleeping'], d
    assert backlight(r) == 0
    h = hal(r)
    assert h['panel_asleep'] and h['panel_sleeps'] == 1, h
    px = r.s.device.flushed_px()
    advance(r, 20)  # frame ticks, pings and the clock all keep running
    assert r.s.device.flushed_px() == px, 'pixels sent to a sleeping panel'
    assert hal(r)['flushes_while_asleep'] == 0
    m = r.mark()
    tap(r.s, 233, 233)
    settle(r)
    d = display(r)
    assert not d['sleeping'] and not d['dimmed'], d
    assert backlight(r) == 80
    h = hal(r)
    assert not h['panel_asleep'] and h['panel_wakes'] == 1, h
    assert r.s.device.flushed_px() > px, 'woke without repainting the glass'
    assert ui(r.s)['view'] == 'home'
    assert not (r.sent_types(m) & REQUESTS), 'the waking touch did more than wake'


def test_a_stored_choice_beats_the_board_default(rig):
    r = rig()
    assert r.s.console('set screen_timeout 0').startswith('@ok')
    assert r.s.console('set brightness 100').startswith('@ok')
    advance(r, 120)
    d = display(r)
    assert d['timeout_s'] == 0 and not d['dimmed'] and not d['sleeping'], d
    assert backlight(r) == 100
    # Clearing the stored value goes back to the board's default.
    assert r.s.console('set screen_timeout').startswith('@ok')
    assert r.s.console('set brightness').startswith('@ok')
    d = display(r)
    assert d['timeout_s'] == 60 and d['brightness'] == 80, d


def test_other_boards_keep_always_on(rig):
    r = rig(ROUND)
    d = display(r)
    assert d['timeout_s'] == 0 and d['brightness'] == 100, d
    advance(r, 120)
    assert not display(r)['sleeping'] and backlight(r) == 100


def test_pwr_turns_the_screen_off_and_on(rig):
    r = rig()
    m = r.mark()
    pwr(r)
    d = display(r)
    assert d['sleeping'] and d['rested'], d
    assert backlight(r) == 0 and hal(r)['panel_asleep']
    pwr(r)
    d = display(r)
    assert not d['sleeping'] and not d['rested'], d
    assert backlight(r) == 80 and not hal(r)['panel_asleep']
    # Off again; a touch wakes it too, and that first touch only wakes.
    pwr(r)
    assert display(r)['sleeping']
    tap(r.s, 233, 233)
    settle(r)
    assert not display(r)['sleeping'] and ui(r.s)['view'] == 'home'
    # With Always on stored, PWR still turns it off, and nothing turns it back on by itself.
    assert r.s.console('set screen_timeout 0').startswith('@ok')
    pwr(r)
    advance(r, 30)
    assert display(r)['sleeping'], 'Always on must not undo PWR'
    assert not (r.sent_types(m) & REQUESTS), r.sent_since(m)


def test_a_screen_pwr_turned_off_stays_off_for_the_same_turn(rig):
    r = rig()
    r.turn_start('turn-R')
    r.delta('Working', turn='turn-R')
    settle(r)
    pwr(r)
    assert display(r)['sleeping']
    r.delta('Working on the lamp', turn='turn-R')
    settle(r)
    r.reply('The lamp is on.', turn='turn-R')
    settle(r)
    r.turn_end('turn-R', 'success')
    advance(r, 3)
    assert display(r)['sleeping'], 'the same turn woke a screen PWR turned off'
    # New work wakes it.
    r.turn_start('turn-S')
    settle(r)
    assert not display(r)['sleeping'], 'a new turn must wake the screen'
    r.turn_end('turn-S', 'success')
    settle(r)
    # So does an approval.
    pwr(r)
    assert display(r)['sleeping']
    r.send('prompt', id='p-rest', title='Permission', text='Allow the desk lamp?')
    settle(r)
    assert not display(r)['sleeping'], 'an approval must wake the screen'
    assert set(ui(r.s)['controls']) == {'yes', 'no'}
