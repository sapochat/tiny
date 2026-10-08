"""Design pass workflows on the round companion, end to end.

Production C++ App, Ui and TouchGestures through the simulator library, connected over
a real 127.0.0.1 WebSocket to the production DeviceHub with disposable stores.
Synthetic text only. Evidence goes to IX_ARTIFACTS like the other interaction suites.
"""
import numpy as np

from conftest import requires_sim
from test_interaction_surface_e2e import (DIM, SURFACE, TEXT, find_text, framebuffer, inside_circle, ix, ix_run,
                                          REQUESTS)
from test_face_first_font import rgb
from test_touch_navigation import swipe, tap, ui

pytestmark = requires_sim

PRESSED = rgb(56, 56, 61)          # a touched target's fill while the finger is down
STAGES = {                          # host stage -> (word, colour) on shelf cards
    'finished': ('Finished', rgb(132, 196, 152)),
    'failed': ('Failed', rgb(226, 124, 112)),
    'cancelled': ('Stopped', rgb(212, 164, 92)),
}


def finish(r, turn, text, outcome='success'):
    r.turn_start(turn, request='req-' + turn)
    r.reply(text, turn=turn)
    r.turn_end(turn, outcome)
    stage = {'success': 'finished', 'failure': 'failed', 'cancelled': 'cancelled'}[outcome]
    assert r.wait(lambda: any(m.get('type') == 'work' and any(
        i['origin']['turn'] == turn and i['stage'] == stage for i in m['items']) for m in r.s.received))


def to_controls(r):
    for _ in range(3):
        if ui(r.s)['view'] == 'controls':
            return
        if ui(r.s)['view'] != 'home':
            swipe(r.s, dx=100)
        else:
            swipe(r.s, dy=100)
    assert ui(r.s)['view'] == 'controls', ui(r.s)


def to_recent(r):
    to_controls(r)
    tap(r.s, *r.control('recent'))
    assert ui(r.s)['view'] == 'recent'


def test_leaving_recent_redraws_the_destination(ix):
    """Back from the shelf must show Quick controls, not a stale shelf frame."""
    r = ix
    finish(r, 'one', 'Lamp is on.')
    to_controls(r)
    r.s.run_for(0.3)
    controls = framebuffer(r.s).copy()
    tap(r.s, *r.control('recent'))
    assert ui(r.s)['view'] == 'recent'
    assert (framebuffer(r.s) != controls).any()
    swipe(r.s, dx=100)
    r.s.run_for(0.3)
    assert ui(r.s)['view'] == 'controls'
    r.snap('back-from-recent')
    assert np.array_equal(framebuffer(r.s), controls), 'leaving Recent left a stale frame on screen'


def test_still_shelf_and_result_do_not_repaint(ix):
    """A still shelf or result is drawn once; the 10 Hz animation tick must not repaint it."""
    r = ix
    finish(r, 'one', 'Lamp is on.')
    to_recent(r)
    r.s.run_for(0.3)
    r.s.take_dirty_rows()
    r.s.run_for(0.6)
    assert r.s.take_dirty_rows() is None, 'the idle shelf repainted without a change'
    tap(r.s, *r.control('work0'))
    assert ui(r.s)['view'] == 'result'
    r.s.run_for(0.3)
    r.s.take_dirty_rows()
    r.s.run_for(0.6)
    assert r.s.take_dirty_rows() is None, 'the idle result repainted without a change'


def test_press_feedback_on_touch_down_and_gone_after_release(ix):
    """Touch-down lights the touched target only; sliding off and lifting acts on nothing."""
    r = ix
    s = r.s
    finish(r, 'one', 'Lamp is on.')
    to_controls(r)
    s.run_for(0.3)
    before = framebuffer(s).copy()
    x, y, w, h = ui(s)['controls']['recent']
    m = r.mark()
    s.touch(True, x + w // 2, y + h // 2)
    s.step()
    assert ui(s)['pressed'] == 'recent'
    f = framebuffer(s)
    inside = f[y:y + h, x:x + w]
    assert (inside == PRESSED).sum() > w * h // 3, 'touched target is not highlighted'
    assert find_text(s, 'Recent', 18, TEXT, PRESSED, (x, y, w, h)), 'label lost on the pressed fill'
    changed = np.argwhere(f != before)
    assert changed.size and changed[:, 0].min() >= y and changed[:, 0].max() < y + h, 'press repainted beyond its target'
    # Slide well away (a cancelled press), then lift: highlight gone, nothing happened.
    s.touch(True, x + w // 2 + 40, y + h // 2 + 30)
    s.step()
    assert ui(s)['pressed'] == 'none'
    s.touch(False)
    s.step()
    s.run_for(0.2)
    assert ui(s)['view'] == 'controls'
    assert np.array_equal(framebuffer(s), before)
    assert not (r.sent_types(m) & REQUESTS)


def test_press_feedback_on_shelf_card_then_tap_opens_it(ix):
    r = ix
    s = r.s
    finish(r, 'one', 'Lamp is on.')
    to_recent(r)
    x, y, w, h = ui(s)['controls']['work0']
    s.touch(True, x + w // 2, y + h // 2)
    s.step()
    assert ui(s)['pressed'] == 'work0'
    assert (framebuffer(s)[y:y + h, x:x + w] == PRESSED).sum() > w * h // 3
    r.snap('card-pressed')
    s.touch(False)
    s.step()
    assert ui(s)['view'] == 'result' and ui(s)['pressed'] == 'none'


def test_shelf_cards_have_status_hierarchy(ix):
    """Stage is a small coloured word; the host glance is the readable body."""
    r = ix
    finish(r, 'ok', 'Lamp is on.')
    finish(r, 'bad', 'Thermostat did not answer.', 'failure')
    finish(r, 'halt', 'Stopped drafting the email.', 'cancelled')
    to_recent(r)
    r.snap('shelf-hierarchy')
    rows = {'work0': ('cancelled', 'Stopped drafting the email.'),
            'work1': ('failed', 'Thermostat did not answer.'),
            'work2': ('finished', 'Lamp is on.')}
    for name, (stage, glance) in rows.items():
        rect = tuple(ui(r.s)['controls'][name])
        word, colour = STAGES[stage]
        assert find_text(r.s, word, 18, colour, SURFACE, rect), (name, word)
        assert find_text(r.s, glance, 18, TEXT, SURFACE, rect), (name, glance)
        assert not find_text(r.s, stage, 18, TEXT, SURFACE, rect), (name, 'raw lowercase stage still shown')
    assert 'next' not in ui(r.s)['controls'], 'a single page needs no paging control'


def test_shelf_paging_is_labelled_and_reaches_all_eight(ix):
    r = ix
    s = r.s
    texts = [f'Result number {i}' for i in range(8)]
    for i, t in enumerate(texts):
        finish(r, f'job{i}', t)
    to_recent(r)
    seen = []
    labels = []
    for page in range(3):
        controls = ui(s)['controls']
        assert 'next' in controls and inside_circle(controls['next'])
        for i in range(3):
            name = f'work{i}'
            if name not in controls:
                continue
            seen += [t for t in texts if find_text(s, t, 18, TEXT, SURFACE, tuple(controls[name]))]
        label = 'Back to top' if page == 2 else 'More  ›'
        assert r.label('next', label), (page, label)
        labels.append(label)
        r.snap(f'shelf-page{page + 1}')
        tap(s, *r.control('next'))
    assert sorted(seen) == sorted(texts), seen
    assert find_text(s, texts[-1], 18, TEXT, SURFACE, tuple(ui(s)['controls']['work0'])), 'paging did not wrap'


def test_result_outcome_reads_as_a_word(ix):
    r = ix
    finish(r, 'bad', 'Thermostat did not answer.', 'failure')
    to_recent(r)
    tap(r.s, *r.control('work0'))
    assert ui(r.s)['view'] == 'result'
    assert r.shows('Failed', 18, STAGES['failed'][1], 0, (78, 90, 310, 45))
    assert not r.shows('failed', 14, DIM, 0, (0, 400, 466, 66))


def test_quick_control_values_do_not_collide_with_recent(ix):
    """Slider values live inside their tracks, clear of the Recent target."""
    r = ix
    finish(r, 'one', 'Lamp is on.')
    to_controls(r)
    c = ui(r.s)['controls']
    rx, ry, rw, rh = c['recent']
    assert find_text(r.s, '70%', 18, rgb(23, 19, 13), rgb(212, 164, 92), tuple(c['volume'])), 'volume value not in track'
    f = framebuffer(r.s)
    left, right = c['volume'], c['brightness']
    # Nothing but black between the tracks and the Recent target on its row.
    for x0, x1 in ((left[0], rx), (rx + rw, right[0] + right[2])):
        band = f[ry:ry + rh, x0:x1]
        assert not band.any(), 'text crowds the Recent target'
