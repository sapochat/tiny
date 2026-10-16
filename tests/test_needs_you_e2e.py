"""R-07 needs-you mark on the round companion: real native core, production loopback hub.

Idle Home carries one persistent, content-free mark when something waits for the user:
unread reply text (and, from R-13, a timer that has fired). It is a bright dot centred above
the title slot, so it never displaces the slot's status or time, and it shows nothing of what
is waiting (private when visitors are around). An approval needs no mark: a question already
takes over the screen until it is answered. No protocol change: the mark reuses state the
device already has. Failure modes covered:
- the mark is missing when unread text waits on idle Home, or remains after it was read;
- the mark replaces the time or "Last task: ..." instead of sitting beside them;
- the mark carries content (text/glyphs) rather than one solid shape;
- the mark leaves the safe circle, or shows during activity (speaking/thinking);
- the mark is a timed toast: it must persist until the reason clears;
- marking or clearing sends anything to the host.
"""
from __future__ import annotations

import numpy as np
import pytest

from conftest import requires_sim
from test_device_time_e2e import Clock, advance, close, make
from test_interaction_surface_e2e import DIM, TEXT, framebuffer, find_text, inside_circle, rgb, tone
from test_touch_navigation import swipe, tap, ui

pytestmark = requires_sim

MARK = (213, 4, 40, 40)            # around the dot, above the title slot
TITLE = (0, 30, 466, 66)
BRIGHT = rgb(242, 179, 61)          # the bright accent; nothing else on Home uses it
REQUESTS = {'text', 'audio.start', 'audio.end', 'audio.cancel', 'cancel', 'session.new', 'prompt.reply'}


@pytest.fixture
def rig(tmp_path):
    made = []

    def _make(face=None):
        r = make(tmp_path / f'r{len(made)}', Clock())
        made.append(r)
        if face:
            assert r.s.console(f'set idle_face {face}').startswith('@ok')
        r.s.run_for(0.4)
        return r
    yield _make
    for r in made:
        close(r)


def mark_pixels(r):
    x, y, w, h = MARK
    return framebuffer(r.s)[y:y + h, x:x + w]


def mark_rect(r):
    px = np.argwhere(mark_pixels(r) == BRIGHT)
    if not len(px):
        return None
    (y0, x0), (y1, x1) = px.min(axis=0), px.max(axis=0)
    return int(MARK[0] + x0), int(MARK[1] + y0), int(x1 - x0 + 1), int(y1 - y0 + 1)


def home(r):
    if ui(r.s)['view'] != 'home':
        swipe(r.s, dx=100)
    r.s.run_for(0.4)
    assert ui(r.s)['view'] == 'home', ui(r.s)


def unread_reply(r, turn='t1', text='Lamp is on and the blinds are down.'):
    r.turn_start(turn, request='req-' + turn)
    swipe(r.s, dy=100)
    swipe(r.s, dx=100)          # explicit Home: the text arrives while the reader is hidden
    r.reply(text, turn=turn)
    r.turn_end(turn, 'success')
    assert r.wait(lambda: not r.s.status()['work']['active'] and ui(r.s)['activity'] == 'idle')
    home(r)


def test_idle_home_without_anything_waiting_has_no_mark(rig):
    r = rig()
    assert ui(r.s)['needs_you'] == ''
    assert mark_rect(r) is None
    assert not (mark_pixels(r) != 0).any(), 'something drawn where the mark goes'


def test_unread_reply_marks_idle_home_beside_status_and_time(rig):
    r = rig()
    m = r.mark()
    unread_reply(r)
    u = ui(r.s)
    assert u['needs_you'] == 'reply', u
    assert u['headline'] == 'Reply ready' and 'reply' in u['controls'], u
    got = mark_rect(r)
    assert got, 'no bright mark on idle Home'
    assert inside_circle(got), got
    assert got[2] >= 16 and got[3] >= 16, ('mark too small to see from the desk', got)
    assert got[1] + got[3] <= TITLE[1] + 14, ('mark runs into the title slot', got)
    # One solid shape, no content: only the mark colour and black in its box.
    assert set(np.unique(mark_pixels(r)).tolist()) <= {0, BRIGHT}
    # The title slot keeps its status: the mark sits beside it, never replaces it.
    assert u['title'] == 'Last task: Finished', u
    assert find_text(r.s, 'Last task: Finished', 24, DIM, 0, TITLE)
    assert not (r.sent_types(m) & REQUESTS) - {'text'}, r.sent_types(m)
    r.snap('needs-you-reply')


def test_mark_persists_until_the_reply_is_read_then_clears(rig):
    r = rig()
    unread_reply(r)
    assert mark_rect(r)
    # Well past the 20 s reply linger: not a timed toast. Explicit ping fixtures between
    # 4 s jumps keep the device's server-silent timeout (3 heartbeats) from firing.
    for _ in range(10):
        advance(r, 4)
        r.send('ping', ts=1)
    r.s.run_for(0.3)
    assert ui(r.s)['needs_you'] == 'reply' and mark_rect(r), ui(r.s)
    m = r.mark()
    tap(r.s, *r.control('reply'))
    assert ui(r.s)['view'] == 'response'
    swipe(r.s, dx=100)
    r.s.run_for(0.4)
    u = ui(r.s)
    assert u['view'] == 'home' and u['needs_you'] == '', u
    assert mark_rect(r) is None, 'mark left after the reply was read'
    assert not (r.sent_types(m) & REQUESTS), r.sent_types(m)


def test_mark_shows_with_the_time_when_no_status_holds_the_slot(rig):
    r = rig()
    # Text without a lifecycle end (a legacy host): unread, no "Last task" status.
    swipe(r.s, dy=100)
    swipe(r.s, dx=100)
    r.send('reply', text='Reminder: the oven is preheated.')
    assert r.wait(lambda: ui(r.s)['activity'] == 'idle')
    home(r)
    u = ui(r.s)
    assert u['needs_you'] == 'reply' and u['title'] == '10:46', u
    assert mark_rect(r)
    assert find_text(r.s, '10:46', 44, TEXT, 0, TITLE), 'the time was displaced by the mark'


def test_clock_face_keeps_the_mark(rig):
    r = rig('clock')
    unread_reply(r)
    assert ui(r.s)['needs_you'] == 'reply'
    assert mark_rect(r), 'Clock idle face lost the mark'


def test_no_mark_while_hermes_is_speaking(rig):
    r = rig()
    unread_reply(r)
    assert mark_rect(r)
    r.turn_start('t2')
    r.play(tone(2.0), turn='t2')
    assert r.wait(lambda: ui(r.s)['speaking'])
    r.s.run_for(0.3)
    home(r)
    assert ui(r.s)['needs_you'] == '', ui(r.s)
    assert mark_rect(r) is None, 'mark drawn during activity'
