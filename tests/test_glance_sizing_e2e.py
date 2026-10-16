"""R-06 glance sizing on the round companion: real native core, production loopback hub.

Tiny is glanced at from ~60 cm. Home's state word is drawn at 44 px where it fits, and no
functional Home text is below 24 px: the title-slot status, the detail line, the action-row
labels and the "Controls" route. No new rows: when an action row and a detail line both
need the space under the portrait, the state word stays at 30 px. Failure modes covered:
- the word is still 30 px on an idle Home (or the status/detail/labels still 18 px);
- a 44 px word collides with the portrait box (repainted by every animation frame) or the
  action row, or leaves the safe circle;
- a word too wide for 44 px (or with a glyph the face lacks) is clipped instead of 30 px;
- an action label is cut off inside its pill.
Glyphs are compared with an independent raster of the Geist source TTF (find_text).
"""
from __future__ import annotations

from array import array
import math

import pytest

from conftest import requires_sim
from test_device_time_e2e import Clock, close, make
from test_interaction_surface_e2e import DIM, SURFACE, TEXT, _tight, find_text, inside_circle, ix, ix_run  # noqa: F401
from test_touch_navigation import swipe, tap, ui

pytestmark = requires_sim

PORTRAIT_BOTTOM = 288            # the animated face's box ends here; it is repainted whole
TITLE = (0, 44, 466, 40)
BAND = (0, 280, 466, 92)         # state word + detail, between the portrait and the action row
ROW_TOP = 356                    # Home's action row


def tone(seconds, rate=16000, freq=440.0, amp=6000):
    n = int(seconds * rate)
    return array('h', (int(amp * math.sin(2 * math.pi * freq * i / rate)) for i in range(n))).tobytes()


@pytest.fixture
def rig(tmp_path):
    made = []

    def _make():
        r = make(tmp_path / f'r{len(made)}', Clock())
        made.append(r)
        r.s.run_for(0.4)
        return r
    yield _make
    for r in made:
        close(r)


def rect(r, label, size, fg, bg=0, box=(0, 0, 466, 466)):
    pos = find_text(r.s, label, size, fg, bg, box)
    if pos is None:
        return None
    h, w = _tight(label, size, fg, bg).shape
    return pos[0], pos[1], w, h


def word(r, label, size):
    got = rect(r, label, size, TEXT, 0, BAND)
    assert got, f'{label!r} not drawn at {size} px under the portrait'
    assert got[1] >= PORTRAIT_BOTTOM, (label, got, 'reaches into the portrait box')
    assert inside_circle(got), (label, got)
    return got


def test_idle_home_word_is_44px_and_controls_route_24px(rig):
    r = rig()
    u = ui(r.s)
    assert u['view'] == 'home' and u['headline'] == 'Hold to talk'
    word(r, 'Hold to talk', 44)
    assert not rect(r, 'Hold to talk', 30, TEXT, 0, BAND)
    c = tuple(u['controls']['controls'])
    assert rect(r, '↓  Controls', 24, DIM, 0, c), 'Controls route is not 24 px'
    assert not rect(r, '↓  Controls', 18, DIM, 0, c)
    r.snap('idle')


def test_title_slot_status_is_24px(rig):
    r = rig()
    r.turn_start('t1', request='req-1')
    r.reply('Lamp is on.', turn='t1')
    r.turn_end('t1', 'success')
    assert r.wait(lambda: not r.s.status()['work']['active'])
    if ui(r.s)['view'] != 'home':
        swipe(r.s, dx=100)
    r.s.run_for(0.4)
    assert ui(r.s)['title'] == 'Last task: Finished'
    got = rect(r, 'Last task: Finished', 24, DIM, 0, TITLE)
    assert got and inside_circle(got), 'title-slot status is not 24 px'
    assert not rect(r, 'Last task: Finished', 18, DIM, 0, TITLE)
    word(r, 'Hold to talk', 44)


def test_speaking_word_44px_above_24px_action_labels(rig):
    r = rig()
    r.turn_start('t1', request='req-1')
    r.play(tone(3.0), turn='t1')
    assert r.wait(lambda: ui(r.s)['speaking'])
    r.s.run_for(0.3)
    u = ui(r.s)
    assert u['headline'] == 'Speaking' and {'silence', 'stop'} <= set(u['controls'])
    w = word(r, 'Speaking', 44)
    assert w[1] + w[3] < ROW_TOP, ('word runs into the action row', w)
    for name, label in (('silence', 'Mute voice'), ('stop', 'Stop task')):
        box = tuple(u['controls'][name])
        assert rect(r, label, 24, TEXT, SURFACE, box), f'{label} is not a 24 px label'
        assert not rect(r, label, 18, TEXT, SURFACE, box)


def test_action_row_with_detail_keeps_30px_word_and_24px_detail(rig):
    r = rig()
    r.s.type_text('draft the email to Ana')
    assert r.wait(lambda: any(m.get('type') == 'text' for m in r.s.sent))
    req = [m for m in r.s.sent if m.get('type') == 'text'][-1]['id']
    r.turn_start('t2', request=req)
    r.s.run_for(0.3)
    tap(r.s, *r.control('stop'))
    r.s.run_for(0.3)
    u = ui(r.s)
    assert u['headline'] == 'Stop requested' and u['detail'] == 'Waiting for Hermes to confirm', u
    w = word(r, 'Stop requested', 30)          # no new rows: 44 px would not leave room
    d = rect(r, 'Waiting for Hermes to confirm', 24, DIM, 0, BAND)
    assert d, 'detail is not 24 px'
    assert d[1] > w[1] + w[3] and d[1] + d[3] < ROW_TOP, (w, d, 'stack overlaps')
    assert inside_circle(d)
    box = tuple(u['controls']['stop'])
    assert rect(r, 'Stop task', 24, DIM, 0, box), 'inert Stop keeps its 24 px name'


def test_connection_lost_home_44px_word_24px_detail(rig):
    r = rig()
    r.turn_start('busy', request='req-1')
    r.s.set_network(False)
    r.s.run_for(0.3)
    r.s.set_network(True)
    assert r.s.wait_screen('ready', timeout=10)
    r.s.run_for(0.5)
    if ui(r.s)['view'] != 'home':
        swipe(r.s, dx=100)
    u = ui(r.s)
    assert u['headline'] == 'Connection lost' and u['detail'] == 'Task status unknown', u
    w = word(r, 'Connection lost', 44)
    d = rect(r, 'Task status unknown', 24, DIM, 0, BAND)
    assert d and d[1] > w[1] + w[3], (w, d)
    c = tuple(u['controls']['controls'])
    assert d[1] + d[3] < c[1] + 8, ('detail runs into the Controls route', d, c)


def test_too_wide_word_falls_back_to_30px(ix):
    # "Task status unknown" is 425 px at 44 px: wider than the 400 px measure under the
    # portrait, so it stays 30 px rather than being cut (same expiry path as remediation F3).
    r, s = ix, ix.s
    r.turn_start('silent-end')
    r.reply('Final text; Hermes never ends this turn.', turn='silent-end')
    s.run_for(182)
    assert not s.status()['work']['active']
    swipe(s, dx=100)
    assert ui(s)['view'] == 'home' and ui(s)['headline'] == 'Task status unknown', ui(s)
    word(r, 'Task status unknown', 30)
    assert not rect(r, 'Task status', 44, TEXT, 0, BAND)
    assert rect(r, 'No ending from Hermes', 24, DIM, 0, BAND), 'detail is not 24 px'
