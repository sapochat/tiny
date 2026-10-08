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
CUE = 'Scroll to read all  ↓'


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
    assert r.shows(CUE, 18, TEXT), 'no cue that the question continues'
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
    assert not r.shows(CUE, 18, TEXT)
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
    assert not r.shows(CUE, 18, TEXT)
    yes, no = r.rect('yes'), r.rect('no')
    assert yes[2:] == no[2:]
    tap(s, *r.control('yes'))
    assert [(m['id'], m['answer']) for m in replies(s)] == [('short', 'yes')]


# == M1: pairing, settings and Wi-Fi setup in the companion design ===========================

def legacy_pixels(s, box=(0, 0, 466, 466)):
    """Legacy 5x7 text is drawn in kText/kDim without antialiasing; Geist always blends."""
    x, y, w, h = box
    f = framebuffer(s)[y:y + h, x:x + w]
    legacy = {0xE77E, 0x8494}   # rgb565(232,238,242), rgb565(132,146,160)
    return int(np.isin(f, list(legacy)).sum())


def unpaired_with_code(r, code='482913', command='hermes gadget pair 482913'):
    r.run(r.session.send_pairing(code, command))
    r.run(r.session.set_paired(False))
    assert r.s.wait_for(lambda: not r.s.status()['paired'], timeout=5)
    r.run(r.session.send_pairing(code, command))
    r.s.run_for(0.4)
    assert r.s.device.screen() == 'pairing'


def test_pairing_is_companion_rendered_with_a_large_code(ix):
    r, s = ix, ix.s
    unpaired_with_code(r)
    r.snap('pairing')
    assert r.shows('482913', 44, TEXT), 'pairing code is not large Geist'
    assert r.shows('hermes gadget pair 482913', 18, TEXT), 'command is not readable Geist'
    assert r.shows('Waiting for approval', 18, DIM)
    assert legacy_pixels(s) == 0, 'pairing still uses the legacy pixel font'
    # Title hold still opens local Settings from pairing (recovery path).
    s.touch(True, 233, 62); s.run_for(1.3); s.touch(False); s.step()
    assert s.device.screen() == 'settings'
    s.console('settings close'); s.step()
    r.run(r.session.set_paired(True))
    assert s.wait_screen('ready', timeout=5)


def test_settings_are_companion_rendered_and_operable(ix):
    r, s = ix, ix.s
    s.touch(True, 233, 62); s.run_for(1.3); s.touch(False); s.step()
    assert s.device.screen() == 'settings'
    s.run_for(0.2)
    r.snap('settings-volume')
    assert r.shows('Settings', 24, TEXT, 0, (0, 40, 466, 60))
    assert r.shows('Speaker volume', 24, TEXT, SURFACE)
    assert r.shows('70%', 44, TEXT, SURFACE)   # display face
    assert r.shows('Tap to change · Swipe for next', 18, DIM)
    assert legacy_pixels(s) == 0, 'settings still use the legacy pixel font'
    tap(s, 233, 220)
    assert '"value":"80"' in s.console('get volume')
    assert r.shows('80%', 44, TEXT, SURFACE)
    swipe(s, dy=100)
    assert r.shows('Screen brightness', 24, TEXT, SURFACE)
    r.snap('settings-brightness')
    for _ in range(6):
        swipe(s, dy=100)
    assert legacy_pixels(s) == 0
    # Title hold leaves settings again, without sending anything.
    s.touch(True, 233, 62); s.run_for(1.3); s.touch(False); s.step()
    assert s.device.screen() != 'settings'
    assert not any(m['type'] in ('audio.start', 'cancel', 'session.new') for m in s.sent)


def test_wifi_setup_is_companion_rendered_and_closes(ix):
    r, s = ix, ix.s
    assert s.console('wifi-setup').startswith('@ok')
    s.step()
    assert s.device.screen() == 'setup'
    r.snap('wifi-setup')
    assert r.shows('Wi-Fi setup', 24, TEXT)
    assert r.shows('Swipe down to close', 18, DIM)
    assert legacy_pixels(s) == 0
    swipe(s, dy=100)
    assert s.device.screen() != 'setup'


# == M3: quick-controls status has its own line ==============================================

STATUS_BAND = (0, 302, 466, 32)   # its own line between the sliders/Recent and the action row


def quick_controls(r):
    for _ in range(3):
        if ui(r.s)['view'] == 'controls':
            break
        swipe(r.s, dx=100) if ui(r.s)['view'] != 'home' else swipe(r.s, dy=100)
    r.s.run_for(0.3)
    assert ui(r.s)['view'] == 'controls'


def test_quick_controls_status_never_shares_an_action_slot(ix):
    r, s = ix, ix.s
    slots = {}
    r.turn_start('busy', request='req-busy')
    quick_controls(r)
    slots['busy'] = {k: ui(s)['controls'].get(k) for k in ('silence', 'stop')}
    assert r.shows('Settings open when idle', 18, DIM, 0, STATUS_BAND)
    r.require_label('stop', 'Stop task')
    r.turn_end('busy', 'success')
    assert r.wait(lambda: not s.status()['work']['active'])
    s.run_for(0.3)
    r.snap('controls-after')
    assert r.shows('Last task: Finished', 18, DIM, 0, STATUS_BAND)
    # The action row keeps both actions in their places; an inert Stop is outlined, not a word.
    assert r.shows('Stop task', 18, DIM, 0, tuple(slots['busy']['stop']))
    assert r.shows('Mute voice', 18, DIM, 0, tuple(slots['busy']['silence']))
    for name, rect in ui(s)['controls'].items():
        assert not overlap(rect, STATUS_BAND), (name, rect)
    m = len(s.sent)
    tap(s, 233, STATUS_BAND[1] + 12)
    assert ui(s)['view'] == 'controls' and len(s.sent) == m
