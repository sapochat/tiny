"""R-13 local timer as a device action: real native core, production loopback hub.

Hermes sets timers through its existing device-action tool (``gadget_action``), so the App
actions ``timer.start {seconds, label?}``, ``timer.cancel {id?}`` and ``timer.list`` are the
whole interface; the protocol is unchanged. The countdown and the alarm run on the device's
monotonic clock, so they keep working through Wi-Fi loss and ignore host clock jumps.
Failure modes covered:
- the actions are missing, accept nonsense, or appear on boards without the round UI;
- the countdown is not large on idle Home, or follows the host's wall clock;
- the alarm needs the host (stops when Wi-Fi is lost) or sends anything when it fires;
- expiry shows no takeover, the Dismiss target is small or leaves the safe circle, or a
  swipe/stray tap dismisses it;
- the alarm tone reads as speech (Mute voice / "Speaking"), or beeps forever;
- an unanswered alarm vanishes instead of leaving the needs-you mark on Home;
- the alarm interrupts a recording or replaces an approval;
- cancel guesses which of several timers to cancel.
"""
from __future__ import annotations

import asyncio
from array import array

import numpy as np
import pytest

from conftest import requires_sim
from test_device_time_e2e import Clock, close, make
from test_interaction_surface_e2e import DIM, SURFACE, TEXT, framebuffer, find_text, inside_circle, ix, ix_run  # noqa: F401
from test_needs_you_e2e import BRIGHT, MARK
from test_touch_navigation import tap, ui

pytestmark = requires_sim

COUNTDOWN = (0, 280, 466, 56)   # Home's state-word band under the portrait
LABEL = (0, 326, 466, 40)       # Home's detail line
TITLE = (0, 40, 466, 44)
REQUESTS = {'text', 'audio.start', 'audio.end', 'audio.cancel', 'cancel', 'session.new', 'prompt.reply'}


@pytest.fixture
def rig(tmp_path):
    made = []

    def _make(clock=None):
        r = make(tmp_path / f'r{len(made)}', clock or Clock())
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


def settle(r, seconds=0.4):
    for _ in range(int(seconds / 0.05)):
        r.s.vclock[0] += 50
        r.s.step()


def advance(r, seconds, online=True):
    """Device time moves on; explicit pings keep the session alive across long jumps."""
    left = seconds
    while left > 0:
        step = min(4, left)
        r.s.vclock[0] += int(step * 1000)
        r.s.step()
        if online:
            r.send('ping', ts=1)
        left -= step
    settle(r, 0.1)


def act(r, name, args=None):
    fut = asyncio.run_coroutine_threadsafe(r.session.invoke_action(name, args or {}, timeout=5), r.lt.loop)
    assert r.s.wait_for(fut.done, timeout=7), f'{name} did not answer'
    r.s.step()
    settle(r, 0.2)
    return fut


def ok(r, name, args=None):
    fut = act(r, name, args)
    assert fut.exception() is None, fut.exception()
    return fut.result()


def error(r, name, args=None):
    fut = act(r, name, args)
    assert fut.exception() is not None, (name, args, fut.result())
    return str(fut.exception())


def timer(r):
    return ui(r.s)['timer']


def tone_writes(r, mark):
    return r.hal_since(mark, 'speaker_write')


def is_square_tone(entry):
    a = array('h')
    a.frombytes(entry['data'])
    values = set(a.tolist())
    return len(values) == 2 and min(values) == -max(values) and max(values) > 0


def test_actions_are_offered_with_schemas_and_validate(rig):
    r = rig()
    s = r.session
    assert {'timer.start', 'timer.cancel', 'timer.list'} <= set(s.action_names())
    start = next(a for a in s.actions if a['name'] == 'timer.start')
    assert start['params']['required'] == ['seconds'], start
    assert {'seconds', 'label'} <= set(start['params']['properties']), start
    assert 'Wi-Fi' in start['description'] or 'offline' in start['description'], start
    assert ok(r, 'timer.list') == {'timers': []}
    m = r.mark()
    for bad in ({}, {'seconds': 0}, {'seconds': -5}, {'seconds': 86401}, {'seconds': 'ten'}):
        assert 'seconds' in error(r, 'timer.start', bad), bad
    assert 'no timer' in error(r, 'timer.cancel')
    assert timer(r)['state'] == 'none' and timer(r)['count'] == 0
    assert not r.sent_types(m) & REQUESTS


def test_countdown_is_large_on_idle_home_and_runs_on_the_device_clock(rig):
    host = Clock()
    r = rig(host)
    res = ok(r, 'timer.start', {'seconds': 540, 'label': 'Pasta'})
    assert res['label'] == 'Pasta' and res['seconds'] == 540 and res['remaining_s'] == 540, res
    assert res['id']
    t = timer(r)
    assert t['state'] == 'running' and t['text'] == '9:00' and t['label'] == 'Pasta', t
    assert ui(r.s)['view'] == 'home'
    assert find_text(r.s, '9:00', 44, TEXT, 0, COUNTDOWN), 'countdown not drawn at 44 px on Home'
    assert find_text(r.s, 'Pasta', 24, DIM, 0, LABEL), 'label not on the detail line'
    r.snap('timer-running')
    # A host clock jump (DST, NTP) changes the wall clock, never the countdown.
    host.unix -= 3600
    advance(r, 61)
    assert timer(r)['text'] == '7:59', timer(r)
    assert find_text(r.s, '7:59', 44, TEXT, 0, COUNTDOWN)
    assert not find_text(r.s, '9:00', 44, TEXT, 0, COUNTDOWN)
    listed = ok(r, 'timer.list')['timers']
    assert [(x['id'], x['label'], x['state'], x['remaining_s']) for x in listed] == [(res['id'], 'Pasta', 'running', 479)]
    # Hours read h:mm:ss.
    ok(r, 'timer.cancel', {'id': res['id']})
    ok(r, 'timer.start', {'seconds': 3725})
    assert timer(r)['text'] == '1:02:05' and timer(r)['label'] == '', timer(r)
    assert find_text(r.s, 'Timer', 24, DIM, 0, LABEL), 'an unlabelled timer says Timer'


def test_alarm_rings_offline_with_a_large_dismiss_and_sends_nothing(rig):
    r = rig()
    ok(r, 'timer.start', {'seconds': 30, 'label': 'Tea'})
    m = r.mark()
    r.s.set_network(False)
    settle(r)
    assert r.s.status()['screen'] == 'offline'
    # Offline, the countdown takes the connection screen's title.
    assert timer(r)['state'] == 'running'
    assert find_text(r.s, 'Tea · 0:30', 24, TEXT, 0, TITLE), 'countdown missing on the offline screen'
    r.snap('timer-offline')
    advance(r, 31, online=False)
    u = ui(r.s)
    assert u['view'] == 'alarm' and timer(r)['state'] == 'ringing', (u['view'], timer(r))
    assert find_text(r.s, 'Time’s up', 44, TEXT), 'no alarm headline'
    assert find_text(r.s, 'Tea', 24, DIM, 0, (0, 30, 466, 70)), 'alarm does not name the timer'
    x, y, w, h = u['controls']['dismiss']
    assert h >= 96 and w >= 200 and inside_circle((x, y, w, h)), (x, y, w, h)
    assert find_text(r.s, 'Dismiss', 30, TEXT, SURFACE, (x, y, w, h))
    assert set(u['controls']) == {'dismiss'}, u['controls']
    r.snap('timer-alarm')
    beeps = tone_writes(r, m)
    assert beeps and all(is_square_tone(b) for b in beeps), 'no local alarm tone'
    # The tone is not speech: no Mute voice, no Speaking.
    assert u['speaking'] is False and u['activity'] == 'idle', u
    # It repeats about once a second while it rings (fine 50 ms steps of device time).
    n = len(tone_writes(r, m))
    settle(r, 3.0)
    assert 2 <= len(tone_writes(r, m)) - n <= 4
    assert not r.sent_since(m), r.sent_since(m)
    m2 = r.mark()
    tap(r.s, x + w // 2, y + h // 2)
    settle(r)
    assert ui(r.s)['view'] != 'alarm' and timer(r)['state'] == 'none', (ui(r.s)['view'], timer(r))
    assert r.s.status()['screen'] == 'offline'
    advance(r, 3, online=False)
    assert not tone_writes(r, m2), 'tone continued after Dismiss'


def test_swipes_and_stray_taps_never_dismiss_the_alarm(rig):
    r = rig()
    ok(r, 'timer.start', {'seconds': 2})
    advance(r, 3)
    assert ui(r.s)['view'] == 'alarm'
    for dx, dy in ((100, 0), (-100, 0), (0, 100), (0, -100)):
        r.s.touch(True, 233, 200)
        r.s.touch(True, 233 + dx // 2, 200 + dy // 2)
        r.s.touch(True, 233 + dx, 200 + dy)
        r.s.touch(False)
        settle(r)
        assert ui(r.s)['view'] == 'alarm', (dx, dy)
    tap(r.s, 233, 120)   # above the target
    settle(r)
    assert ui(r.s)['view'] == 'alarm' and timer(r)['state'] == 'ringing'
    # Holding the title does not open Settings over it either.
    r.s.touch(True, 233, 60)
    settle(r, 1.5)
    r.s.touch(False)
    settle(r)
    assert ui(r.s)['view'] == 'alarm' and r.s.status()['screen'] != 'settings'


def test_unanswered_alarm_leaves_the_needs_you_mark_until_dismissed(rig):
    r = rig()
    ok(r, 'timer.start', {'seconds': 5, 'label': 'Laundry'})
    advance(r, 6)
    assert timer(r)['state'] == 'ringing'
    advance(r, 64)
    m = r.mark()
    u = ui(r.s)
    assert u['view'] == 'home' and timer(r)['state'] == 'done', (u['view'], timer(r))
    assert u['needs_you'] == 'timer', u
    assert u['headline'] == 'Timer done', u
    assert 'dismiss' in u['controls'], u['controls']
    x, y, w, h = MARK
    assert (framebuffer(r.s)[y:y + h, x:x + w] == BRIGHT).any(), 'no needs-you mark'
    assert find_text(r.s, 'Laundry', 24, DIM), 'missed timer does not say which'
    r.snap('timer-missed')
    advance(r, 8)
    assert not tone_writes(r, m), 'a missed alarm keeps beeping'
    assert ui(r.s)['needs_you'] == 'timer', 'the mark is a timed toast'
    tap(r.s, *r.control('dismiss'))
    settle(r)
    u = ui(r.s)
    assert u['needs_you'] == '' and timer(r)['state'] == 'none' and 'dismiss' not in u['controls'], u
    assert u['headline'] == 'Hold to talk', u
    assert not r.sent_types(m) & REQUESTS


def test_alarm_waits_for_a_recording_and_an_approval(rig):
    r = rig()
    ok(r, 'timer.start', {'seconds': 2})
    m = r.mark()
    r.s.touch(True, 233, 220)      # hold to talk on Home
    settle(r, 0.4)
    assert ui(r.s)['view'] == 'recording'
    advance(r, 3)
    assert ui(r.s)['view'] == 'recording', 'the alarm took over a recording'
    assert timer(r)['state'] == 'ringing'
    assert not tone_writes(r, m), 'the alarm beeped into the microphone'
    r.s.touch(False)
    settle(r, 0.4)
    assert ui(r.s)['view'] == 'alarm'
    # A question from Hermes still takes the screen; the alarm returns after it.
    r.send('prompt', id='p1', title='Permission', text='Allow the lamp?')
    settle(r)
    assert ui(r.s)['view'] == 'approval'
    r.send('prompt.close', id='p1')
    settle(r)
    assert ui(r.s)['view'] == 'alarm'


def test_several_timers_list_and_cancel_by_id(rig):
    r = rig()
    a = ok(r, 'timer.start', {'seconds': 600, 'label': 'Rice'})
    b = ok(r, 'timer.start', {'seconds': 300, 'label': 'Eggs'})
    assert a['id'] != b['id']
    t = timer(r)
    assert t['count'] == 2 and t['text'] == '5:00' and t['label'] == 'Eggs', t   # the soonest
    assert find_text(r.s, 'Eggs · +1 more', 24, DIM, 0, LABEL)
    assert [x['label'] for x in ok(r, 'timer.list')['timers']] == ['Eggs', 'Rice']
    err = error(r, 'timer.cancel')
    assert a['id'] in err and b['id'] in err, err
    assert 'no timer' in error(r, 'timer.cancel', {'id': 'zzz'})
    got = ok(r, 'timer.cancel', {'id': b['id']})
    assert got['cancelled']['label'] == 'Eggs' and got['timers'] == 1, got
    # 1.2 s of device time has passed since Rice started: a countdown rounds up, as clocks do.
    assert timer(r)['label'] == 'Rice' and timer(r)['text'] == '9:59', timer(r)
    # With one timer left, cancel needs no id; a ringing timer's cancel stops the alarm.
    ok(r, 'timer.start', {'seconds': 1, 'label': 'Now'})
    advance(r, 2)
    assert ui(r.s)['view'] == 'alarm'
    ok(r, 'timer.cancel', {'id': [x for x in ok(r, 'timer.list')['timers'] if x['label'] == 'Now'][0]['id']})
    assert ui(r.s)['view'] == 'home' and timer(r)['state'] == 'running'
    ok(r, 'timer.cancel')
    assert ok(r, 'timer.list') == {'timers': []}
    for i in range(4):
        ok(r, 'timer.start', {'seconds': 60 + i})
    assert 'cancel one' in error(r, 'timer.start', {'seconds': 60})


@pytest.mark.parametrize('ix', ['sim-240x240'], indirect=True)
def test_boards_without_the_round_companion_offer_no_timer(ix):
    assert not {'timer.start', 'timer.cancel', 'timer.list'} & set(ix.session.action_names())
    assert 'timer' not in ix.s.status().get('ui', {})
