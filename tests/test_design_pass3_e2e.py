"""Third design pass: real native core and production loopback hub; no UI mocks.

B1: a long question cannot be answered (touch or physical buttons) until the reader has
reached its end at least once. M1: pairing and settings use the companion renderer.
M3: quick-controls status never occupies an action slot.
"""
import numpy as np
from conftest import requires_sim
from test_interaction_surface_e2e import ix, ix_run, framebuffer, find_text, inside_circle, overlap, \
    TEXT, DIM, SURFACE
from test_design_pass_e2e import finish
from test_touch_navigation import swipe, tap, ui

pytestmark = requires_sim

LONG_Q = '\n'.join([f'Step {i:02d}: exact wording' for i in range(12)] + ['FINAL: proceed?'])
CUE = 'Scroll to read all'


def replies(s):
    return [m for m in s.sent if m.get('type') == 'prompt.reply']


def long_prompt(r, pid='long'):
    r.send('prompt', id=pid, title='Question', text=LONG_Q)
    r.s.run_for(0.8)   # past the existing 600 ms arm delay
    assert ui(r.s)['view'] == 'approval'


def to_end(r):
    for _ in range(8):
        swipe(r.s, dy=-100)
    assert r.shows('FINAL: proceed?', 24, TEXT)


# == B1 ======================================================================================

def test_long_question_answers_are_inert_until_read(ix):
    r, s = ix, ix.s
    long_prompt(r)
    assert not r.shows('FINAL: proceed?', 24, TEXT), 'fixture must overflow the reader'
    controls = ui(s)['controls']
    assert 'yes' not in controls and 'no' not in controls, ('answers are live before reading', controls)
    assert r.shows(CUE, 18, DIM), 'no cue that the question continues'
    # Inert answers keep their places and equal emphasis, visibly unavailable (no fill).
    f = framebuffer(s)
    assert int(f[296 + 48, 78 + 20]) == 0 and int(f[296 + 48, 238 + 20]) == 0
    assert r.shows('Yes', 18, DIM) and r.shows('No', 18, DIM)
    tap(s, 238 + 75, 296 + 48)
    tap(s, 78 + 75, 296 + 48)
    s.run_for(0.2)
    assert not replies(s), 'a tap answered an unread question'
    r.snap('long-unread')
    to_end(r)
    assert set(ui(s)['controls']) == {'yes', 'no'}
    assert not r.shows(CUE, 18, DIM)
    r.require_label('yes', 'Yes')
    r.require_label('no', 'No')
    # Reaching the end once is enough: scrolling back up keeps the answers live.
    swipe(s, dy=100)
    assert set(ui(s)['controls']) == {'yes', 'no'}
    r.snap('long-read')
    tap(s, *r.control('no'))
    assert [(m['id'], m['answer']) for m in replies(s)] == [('long', 'no')]


def test_long_question_physical_buttons_follow_the_same_rule(ix):
    r, s = ix, ix.s
    long_prompt(r, 'phys')
    s.tap('talk'); s.step()
    s.tap('cancel'); s.step()
    s.run_for(0.2)
    assert not replies(s), 'a physical button answered an unread question'
    assert ui(s)['view'] == 'approval' and s.status().get('prompt') == 'phys'
    to_end(r)
    s.tap('talk'); s.step()
    assert [(m['id'], m['answer']) for m in replies(s)] == [('phys', 'yes')]


def test_short_question_is_answerable_and_arm_delay_kept(ix):
    r, s = ix, ix.s
    r.send('prompt', id='short', title='Permission', text='Allow the desk lamp?')
    s.step()
    tap(s, 238 + 75, 296 + 48)          # inside the arm delay: ignored
    assert not replies(s)
    s.run_for(0.8)
    assert set(ui(s)['controls']) == {'yes', 'no'}
    assert not r.shows(CUE, 18, DIM)
    yes, no = r.rect('yes'), r.rect('no')
    assert yes[2:] == no[2:]
    tap(s, *r.control('yes'))
    assert [(m['id'], m['answer']) for m in replies(s)] == [('short', 'yes')]
