"""Remediation workflows for review findings F1-F5 and control order (plan M1/M2), end to end.

Same production path as ``tests/test_interaction_surface_e2e.py``: the native App, Ui
and TouchGestures through the simulator library, the production DeviceHub on
127.0.0.1 with a disposable store, and the recording EchoBrain delegate. Each
workflow reproduces one independently reported failure (CATO implementation
review, F1-F5) and asserts the corrected observable behaviour: device->host wire
receipts, hub delegate calls, HAL calls and framebuffer pixels compared with the
source-TTF oracle. ``status()['work']`` diagnostics are secondary evidence only.

The 320x240 touch profile below is test-local: the simulator registers no
rectangular touch board, but the experimental ESP32-S3-BOX-3 and M5Stack CoreS3
(320x240 touchscreens) take the same non-round touch path in the core.
Evidence: IX_ARTIFACTS (run.json, fixtures/ copies, per-test snapshots).
"""
from __future__ import annotations

import pytest

from conftest import REPO, requires_sim
from test_interaction_surface_e2e import (  # fixtures and helpers only; no tests are imported
    DIM, REQUESTS, _tight, completed_reading, find_text, inside_circle, ix, ix_run, overlap, tone)
from test_touch_navigation import LONG, swipe, tap, ui

pytestmark = requires_sim

TOUCH_RECT = 'sim-320x240-touch'


@pytest.fixture(autouse=True)
def remediation_evidence(ix_run, monkeypatch):
    copy = ix_run / 'fixtures' / 'test_interaction_remediation_e2e.py'
    copy.parent.mkdir(parents=True, exist_ok=True)
    copy.write_bytes((REPO / 'tests/test_interaction_remediation_e2e.py').read_bytes())
    from hermes_gadget.sim import runner
    monkeypatch.setitem(runner.BOARDS, TOUCH_RECT, runner.Board(TOUCH_RECT, 320, 240, touch=True))


def work(s):
    return s.status()['work']


def stop_count(r, mark):
    return len(r.sent_since(mark, 'cancel'))


def hold(s, x, y, seconds=1.2):
    s.touch(True, x, y)
    s.run_for(seconds)
    s.touch(False)
    s.step()


def text_rect(s, label, size, fg, box):
    pos = find_text(s, label, size, fg, 0, box)
    if pos is None:
        return None
    h, w = _tight(label, size, fg, 0).shape
    return (pos[0], pos[1], w, h)


# == F1: a pre-start Stop belongs to its own request =========================================

@pytest.mark.parametrize('old_events', ['none', 'before_second', 'after_second'])
def test_f1_prestart_stop_never_owns_the_next_request(ix, old_events):
    """Stop t1 before turn.start, then ask t2: t2's turn is cancellable exactly once."""
    r, s = ix, ix.s
    s.type_text('first')
    assert r.wait(lambda: r.brain.count('text') == 1)
    t1 = next(m for m in s.sent if m['type'] == 'text')['id']
    m = r.mark()
    tap(s, *r.control('stop'))
    first = r.sent_since(m, 'cancel')
    assert len(first) == 1 and first[0].get('request') == t1 and 'turn' not in first[0], first
    if old_events == 'before_second':
        r.turn_start('first-turn')   # this request's own turn: still pending, no second cancel
        assert r.headline('Stop requested') and stop_count(r, m) == 1
        r.turn_end('first-turn', 'cancelled')
        assert r.wait(lambda: not work(s)['active'])
        assert r.headline('Outcome unknown') and not r.headline('Stopped')
    s.type_text('second')
    assert r.wait(lambda: r.brain.count('text') == 2)
    assert not r.headline('Stop requested'), 'the old stop is pending for the new request'
    if old_events == 'after_second':
        # Hermes names t1's turn only now. The device cannot tell it from t2's, so the old
        # request-scoped stop must not become pending for it either.
        r.turn_start('first-turn')
        assert not r.headline('Stop requested')
        r.turn_end('first-turn', 'cancelled')
    r.turn_start('second-turn')
    assert r.wait(lambda: work(s)['active'])
    r.snap(f'{old_events}-second-turn')
    assert not r.headline('Stop requested'), 'new work inherited the old pending stop'
    r.require_label('stop', 'Stop task')
    m2 = r.mark()
    tap(s, *r.control('stop'))
    assert [c.get('turn') for c in r.sent_since(m2, 'cancel')] == ['second-turn'], r.sent_since(m2)
    assert r.headline('Stop requested')
    tap(s, *r.control('stop'))
    s.tap('cancel')
    s.step()
    assert stop_count(r, m2) == 1, 'the second turn must be cancellable exactly once'
    assert r.wait(lambda: r.brain.count('cancel') == 2)
    assert work(s)['earlier_stop'] == 'unknown', work(s)
    r.turn_end('second-turn', 'cancelled')
    assert r.wait(lambda: not work(s)['active'])
    assert r.headline('Stopped') and work(s)['stop'] == 'stopped'
    assert work(s)['earlier_stop'] == 'unknown', 'the unmatched old stop must stay unknown'


# == F2: only an exact turn identity confirms a turn-targeted Stop ===========================

@pytest.mark.parametrize('end', ['untagged', 'malformed', 'older'])
def test_f2_unmatched_end_cannot_confirm_or_end_known_work(ix, end):
    r, s = ix, ix.s
    if end == 'older':
        r.turn_start('older-turn')
    r.turn_start('known-target')
    m = r.mark()
    tap(s, *r.control('stop'))
    assert [c.get('turn') for c in r.sent_since(m, 'cancel')] == ['known-target']
    if end == 'untagged':
        r.send('turn.end', outcome='cancelled')
    elif end == 'malformed':
        r.send('turn.end', turn=7, outcome='cancelled')
    else:
        r.turn_end('older-turn', 'cancelled')
    s.run_for(0.3)
    r.snap(f'{end}-end')
    assert not r.headline('Stopped'), 'an end without the selected turn id confirmed the stop'
    assert work(s)['active'] and work(s)['stop'] == 'requested', work(s)
    assert r.headline('Stop requested') and r.detail('Waiting for Hermes to confirm')
    r.turn_end('known-target', 'success')
    assert r.wait(lambda: not work(s)['active'])
    assert r.headline('Finished') and r.detail('Stop was not confirmed')


# == F3: work lifecycle is not a presentation timer ==========================================

@pytest.mark.parametrize('stop_first', [False, True], ids=['no-stop', 'pending-stop'])
def test_f3_final_text_without_turn_end_keeps_work_open_past_settle(ix, stop_first):
    r, s = ix, ix.s
    r.turn_start('unfinished')
    r.delta(LONG, turn='unfinished')
    r.reply(LONG, turn='unfinished')
    assert ui(s)['view'] == 'response'
    swipe(s, dy=100)    # read back: the position must survive
    scroll = ui(s)['scroll']
    m = r.mark()
    if stop_first:
        tap(s, *r.control('stop'))
        assert [c.get('turn') for c in r.sent_since(m, 'cancel')] == ['unfinished']
    s.run_for(6.4)      # longer than the old six-second settle
    r.snap('after-settle')
    assert work(s)['active'], 'final text without turn.end was treated as finished'
    assert ui(s)['view'] == 'response' and ui(s)['scroll'] == scroll
    assert 'talk' not in ui(s)['controls'], 'reading offers Talk while work is open'
    assert s.console('settings').startswith('@error'), 'busy settings were re-enabled'
    s.step()
    if stop_first:
        r.require_label('stop', 'Stop task', fg=DIM, bg=0)   # pass 3: inert pill keeps its action name
        assert r.shows('Stop requested · waiting for Hermes', 18, DIM)   # status on its own line
    else:
        r.require_label('stop', 'Stop task')
    s.tap('cancel')
    s.step()
    assert [c.get('turn') for c in r.sent_since(m, 'cancel')] == ['unfinished']
    s.set_network(False)
    assert s.wait_screen('offline', timeout=5)
    assert ui(s)['detail'].startswith('Task status unknown'), ui(s)
    r.snap('offline')
    m2 = r.mark()
    s.set_network(True)
    assert s.wait_screen('ready', timeout=10)
    s.run_for(0.5)
    assert not (r.sent_types(m2) & REQUESTS) and r.brain.count('cancel') == 1, 'reconnect replayed'
    assert work(s)['stop'] == 'unknown' and not work(s)['active']
    assert ui(s)['view'] == 'response' and ui(s)['scroll'] == scroll
    r.turn_end('unfinished', 'cancelled')   # late matching evidence still resolves it
    assert work(s)['stop'] == 'stopped'


def test_f3_unended_work_expires_to_explicit_unknown_not_completion(ix):
    """No turn.end and no lifecycle activity: bounded expiry to unknown, never 'finished'."""
    r, s = ix, ix.s
    r.turn_start('silent-end')
    r.reply('Final text; Hermes never ends this turn.', turn='silent-end')
    s.run_for(30)
    assert work(s)['active'] and 'stop' in ui(s)['controls']
    s.run_for(152)      # > kThinkingTimeoutMs (180 s) since the last lifecycle message
    assert s.status()['phase'] == 'online', 'hub heartbeats keep the link up'
    w = work(s)
    assert not w['active'] and w['outcome'] == 'unknown', w
    assert 'stop' not in ui(s)['controls']
    r.snap('expired-reading')
    swipe(s, dx=100)
    assert r.headline('Task status unknown') and r.detail('No ending from Hermes')
    assert not r.headline('Reply ready') and not r.headline('Finished')
    r.snap('expired-home')


# == F4: local Settings stay reachable while not connected ===================================

@pytest.mark.parametrize('ix', ['sim-466x466-round', TOUCH_RECT], indirect=True)
@pytest.mark.parametrize('state', ['offline', 'connecting', 'pairing'])
def test_f4_title_hold_opens_local_settings_when_not_connected(ix, state):
    r, s = ix, ix.s
    title = (233, 62) if s.status()['board'] == 'sim-466x466-round' else (160, 6)
    r.turn_start('busy')    # remote work whose outcome becomes unknown
    if state == 'offline':
        s.set_network(False)
        assert s.wait_screen('offline', timeout=5)
    elif state == 'connecting':
        assert s.console('set server ws://127.0.0.1:9/gadget').startswith('@ok')
        assert s.wait_for(lambda: s.status()['phase'] in ('connecting', 'handshake'), timeout=5)
    else:
        r.run(r.session.set_paired(False))
        assert s.wait_for(lambda: not s.status()['paired'], timeout=5)
    s.run_for(0.3)
    m = r.mark()
    hold(s, *title)
    r.snap(f'{state}-title-hold')
    assert s.device.screen() == 'settings', (state, s.status()['screen'])
    assert not r.hal_since(m, 'mic_start'), 'a title hold started recording'
    assert not (r.sent_types(m) & REQUESTS), r.sent_since(m)


def test_f4_reading_title_hold_never_opens_settings_or_records(ix):
    """Guard: restoring offline entry must not re-arm title holds over reading navigation."""
    r, s = ix, ix.s
    completed_reading(r)
    m = r.mark()
    hold(s, 233, 62)
    assert s.device.screen() != 'settings'
    assert not r.hal_since(m, 'mic_start') and not (r.sent_types(m) & REQUESTS)


# == F5: the outcome is visible where the user is ===========================================

OUTCOMES = {   # end, Stop pressed, reading line, quick-controls word
    'stopped': ('cancelled', True, 'Stopped · may be partial', 'Stopped'),
    'error': ('failure', True, 'Error · may be partial', 'Error'),
    'finished-after-stop': ('success', True, 'Finished · stop unconfirmed', 'Finished'),
    'finished': ('success', False, 'Finished', 'Finished'),
    'unknown': ('disconnect', True, 'Unknown · may be partial', 'Unknown'),
}


@pytest.mark.parametrize('case', list(OUTCOMES))
def test_f5_reading_and_controls_show_compact_outcome_in_place(ix, case):
    end, press_stop, line, word = OUTCOMES[case]
    r, s = ix, ix.s
    r.turn_start('rd')
    r.delta(LONG, turn='rd')
    assert ui(s)['view'] == 'response'
    swipe(s, dy=100)
    scroll = ui(s)['scroll']
    if press_stop:
        tap(s, *r.control('stop'))
    if end == 'disconnect':
        s.set_network(False)
        assert s.wait_screen('offline', timeout=5)
        s.set_network(True)
        assert s.wait_for(lambda: s.status()['phase'] == 'online', timeout=10)
    else:
        r.turn_end('rd', end)
    assert r.wait(lambda: not work(s)['active'])
    s.run_for(0.3)
    r.snap(f'reading-{case}')
    assert ui(s)['view'] == 'response' and ui(s)['scroll'] == scroll, 'outcome moved the reader'
    rect = text_rect(s, line, 18, DIM, (0, 90, 466, 45))   # pass 3: 18px header line above the text
    assert rect, (case, line, 'compact outcome not rendered exactly in reading')
    assert inside_circle(rect), rect
    for name, other in ui(s)['controls'].items():
        assert not overlap(rect, other), (name, other, rect)
    swipe(s, dx=100)
    swipe(s, dy=100)
    assert ui(s)['view'] == 'controls'
    r.snap(f'controls-{case}')
    assert 'stop' not in ui(s)['controls']
    assert r.shows('Last task: ' + word, 18, DIM, 0, (0, 302, 466, 32))   # pass 3: own status line
    assert not r.shows(word, 18, DIM, 0, (238, 329, 160, 60)), 'outcome word in the Stop slot'


# == Order: Silence and Stop keep one position across views ===================================

def test_silence_and_stop_keep_one_order_across_views(ix):
    r, s = ix, ix.s
    r.turn_start('both')
    r.delta(LONG, turn='both')
    r.play(tone(4.0), turn='both')
    assert r.wait(lambda: ui(s)['speaking'])
    order = {}
    for view, move in (('response', None), ('home', {'dx': 100}), ('controls', {'dy': 100})):
        if move:
            swipe(s, **move)
        assert ui(s)['view'] == view
        sil, stop = r.rect('silence'), r.rect('stop')
        order[view] = (sil, stop)
        assert sil[0] + sil[2] <= stop[0], (view, sil, stop)
    r.snap('controls-order')
