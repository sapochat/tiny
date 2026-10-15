"""R-05 idle face modes: real native core, production loopback hub, disposable stores.

A device setting ``idle_face`` chooses what idle Home shows: ``portrait`` (the animated face
only, as before), ``portrait_time`` (default: the face, plus the host-supplied local time at
44 px in Home's title slot when no status occupies it) or ``clock`` (72 px digits with a small
face). Failure modes covered:
- a time is drawn when the device does not know it (older host, or a sync too old to trust);
- the time pushes out status: "Last task: ..." outranks it in the title slot;
- the minute rolls over without the glass changing, or the update repaints more than the slot;
- boards without the round UI change (covered by test_round_only_build.py and r05 renders);
- the settings row does not cycle/persist the choice, or navigating it sends anything;
- an invalid value is accepted.
Time comes from welcome/ping ``time`` (R-04); 2026-10-15 17:46:40 UTC is 10:46 in PDT.
"""
from __future__ import annotations

import numpy as np
import pytest

from conftest import requires_sim
from test_device_time_e2e import Clock, NO_TIME, T0, advance, close, make
from test_interaction_surface_e2e import TEXT, DIM, SURFACE, framebuffer, find_text
from test_touch_navigation import swipe, tap, ui

pytestmark = requires_sim

TITLE = (0, 30, 466, 66)          # Home's title slot, above the portrait
FACE = (137, 96, 192, 192)         # the full portrait box
SMALL_FACE = (185, 100, 96, 96)    # Clock mode's small portrait
CLOCK_BAND = (60, 196, 346, 84)    # Clock mode's digits, between the small face and headline
REQUESTS = {'audio.start', 'cancel', 'session.new', 'prompt.reply', 'utterance'}


@pytest.fixture
def rig(tmp_path):
    made = []

    def _make(clock=Clock(), face=None):
        r = make(tmp_path / f'r{len(made)}', clock)
        made.append(r)
        if face is not None:
            assert r.s.console(f'set idle_face {face}').startswith('@ok')
        r.s.run_for(0.4)
        return r
    yield _make
    for r in made:
        close(r)


def shows(r, label, size, fg, box):
    return find_text(r.s, label, size, fg, 0, box) is not None


def lit(r, box):
    x, y, w, h = box
    return int((framebuffer(r.s)[y:y + h, x:x + w] != 0).sum())


def test_default_is_portrait_plus_time_in_the_title_slot(rig):
    r = rig(Clock())
    u = ui(r.s)
    assert u['idle_face'] == 'portrait_time', u
    assert u['title'] == '10:46', u
    assert shows(r, '10:46', 44, TEXT, TITLE), 'host time not drawn at 44 px in the title slot'
    assert lit(r, FACE) > 4000, 'the portrait is still the idle face'
    r.snap('portrait-time')


def test_twelve_hour_digits_without_a_leading_zero(rig):
    r = rig(Clock(unix=T0 + 2 * 3600 + 19 * 60))  # 13:05 PDT
    assert ui(r.s)['title'] == '1:05'
    assert shows(r, '1:05', 44, TEXT, TITLE)


def test_no_time_is_drawn_when_the_device_does_not_know_it(rig):
    r = rig(NO_TIME)
    assert ui(r.s)['title'] == ''
    assert lit(r, TITLE) == 0, 'something drawn in an empty title slot'
    # Clock mode without a time falls back to the full portrait, never to empty digits.
    assert r.s.console('set idle_face clock').startswith('@ok')
    r.s.run_for(0.4)
    assert ui(r.s)['idle_face'] == 'clock' and ui(r.s)['title'] == ''
    x, y, w, h = FACE
    assert lit(r, (x, y, 40, h)) > 0, 'clock mode drew the small face without a time'


def test_status_outranks_the_time(rig):
    r = rig(Clock())
    r.turn_start('t1', request='req-1')
    r.reply('Lamp is on.', turn='t1')
    r.turn_end('t1', 'success')
    assert r.wait(lambda: not r.s.status()['work']['active'])
    swipe(r.s, dx=100)  # back to Home if the reply opened
    r.s.run_for(0.4)
    assert ui(r.s)['view'] == 'home'
    assert ui(r.s)['title'] == 'Last task: Finished'
    assert not shows(r, '10:46', 44, TEXT, TITLE), 'time drawn over status'
    assert shows(r, 'Last task: Finished', 18, DIM, TITLE)
    # Clock mode keeps the status in the title slot and the time in its own band.
    assert r.s.console('set idle_face clock').startswith('@ok')
    r.s.run_for(0.4)
    assert ui(r.s)['title'] == 'Last task: Finished' and ui(r.s)['clock'] == '10:46'
    assert shows(r, '10:46', 72, TEXT, CLOCK_BAND)


def test_minute_rollover_repaints_only_the_title_slot(rig):
    # 10:46:57 PDT: the minute turns over in real time, while heartbeats keep the link up.
    r = rig(Clock(unix=T0 + 17))
    assert ui(r.s)['title'] == '10:46'
    before = framebuffer(r.s).copy()
    flushes = []
    original = r.s.display_flush
    r.s.display_flush = lambda y0, y1: (original(y0, y1), flushes.append((y0, y1)))
    assert r.s.wait_for(lambda: ui(r.s)['title'] == '10:47', timeout=8)
    r.s.run_for(0.2)
    r.s.display_flush = original
    assert ui(r.s)['title'] == '10:47'
    assert shows(r, '10:47', 44, TEXT, TITLE)
    after = framebuffer(r.s)
    x, y, w, h = FACE
    changed = np.argwhere((after != before))
    outside = [p for p in changed if not (y <= p[0] < y + h and x <= p[1] < x + w)]
    assert outside and min(p[0] for p in outside) >= TITLE[1] and max(p[0] for p in outside) < TITLE[1] + TITLE[3], \
        'the minute change repainted beyond the title slot'
    panel = np.frombuffer(r.s.device.panel_rows(), dtype='<u2').reshape(466, 466)
    assert not np.argwhere(panel != after).size, 'the new minute never reached the glass'


def test_portrait_mode_draws_no_time(rig):
    r = rig(Clock(), face='portrait')
    assert ui(r.s)['idle_face'] == 'portrait' and ui(r.s)['title'] == ''
    assert lit(r, TITLE) == 0
    assert lit(r, FACE) > 4000


def test_clock_mode_draws_large_digits_and_a_small_face(rig):
    r = rig(Clock(), face='clock')
    u = ui(r.s)
    assert u['idle_face'] == 'clock' and u['title'] == '', u
    assert u['clock'] == '10:46', u
    assert shows(r, '10:46', 72, TEXT, CLOCK_BAND), 'no 72 px digits'
    assert lit(r, SMALL_FACE) > 1000, 'no small face'
    assert lit(r, (137, 96, 40, 100)) == 0, 'the full-size face is still drawn'
    assert u['headline'] in ('Hold to talk', 'Tap to talk')
    r.snap('clock')


def test_settings_row_cycles_and_persists_without_sending(rig):
    r = rig(Clock())
    m = r.mark()
    r.s.touch(True, 233, 62); r.s.run_for(1.3); r.s.touch(False); r.s.step()
    assert r.s.status()['screen'] == 'settings'
    for _ in range(16):
        if ui(r.s)['detail'] == 'Idle face':
            break
        swipe(r.s, dy=100)
    assert ui(r.s)['detail'] == 'Idle face'
    assert find_text(r.s, 'Portrait + time', 30, TEXT, SURFACE, (68, 104, 330, 214)), 'current choice not shown'
    seen = []
    for _ in range(3):
        tap(r.s, 233, 220)
        seen.append(r.s.console('get idle_face'))
    assert [s.split('"value":"')[1].split('"')[0] for s in seen] == ['clock', 'portrait', 'portrait_time']
    assert not (r.sent_types(m) & REQUESTS), r.sent_types(m)


@pytest.mark.parametrize('bad', ['analog', 'Clock', 'portrait time', '1'])
def test_an_invalid_value_is_refused(rig, bad):
    r = rig(Clock())
    assert r.s.console(f'set idle_face {bad}').startswith('@error')
    assert ui(r.s)['idle_face'] == 'portrait_time'
