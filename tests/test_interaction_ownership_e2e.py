"""Remote-work and reply ownership workflows (CATO V2 review V2-1, V2-2, V2-3), end to end.

Same production path as ``tests/test_interaction_surface_e2e.py``: the native App, Ui
and TouchGestures through the simulator library, the production DeviceHub on
127.0.0.1 with a disposable store, and the recording EchoBrain delegate. Lifecycle and
text fixtures are delivered by the real hub session APIs. Assertions use device->host
wire receipts, hub delegate calls and framebuffer pixels compared with the source-TTF
oracle; ``status()['work']`` diagnostics are secondary evidence only.

Each workflow pins one ownership rule: unresolved remote work is tracked apart from
recording and display modes, a tagged ending or reply for other work never ends or
relabels the current work, and an outcome is only attached to text from the same work.
Evidence: IX_ARTIFACTS (run.json, fixtures/ copies, per-test snapshots).
"""
from __future__ import annotations

import pytest

from conftest import REPO, requires_sim
from test_interaction_surface_e2e import DIM, REQUESTS, TEXT, ix, ix_run  # fixtures and helpers only
from test_touch_navigation import LONG, swipe, tap, ui

pytestmark = requires_sim

OUTCOME_BAND = (0, 90, 466, 45)   # the reading outcome header line on the round board (pass 3)
NEW_TEXT = 'NEW partial answer.'
OLD_TEXT = 'OLD reply for old turn.'
OLD_LATE = 'OLD late text, old turn.'


@pytest.fixture(autouse=True)
def ownership_evidence(ix_run):
    copy = ix_run / 'fixtures' / 'test_interaction_ownership_e2e.py'
    copy.parent.mkdir(parents=True, exist_ok=True)
    copy.write_bytes((REPO / 'tests/test_interaction_ownership_e2e.py').read_bytes())


def work(s):
    return s.status()['work']


def cancel_twice(s):
    """Physical CANCEL twice: the second press must not send a second cancel."""
    for _ in range(2):
        s.tap('cancel')
        s.step()


def settings_refused(s):
    return s.console('settings').startswith('@error')


def settings_open_and_close(s):
    opened = s.console('settings')
    assert not opened.startswith('@error'), opened
    s.console('settings')   # the same command closes them again
    s.step()


def reading_outcome(r, line):
    return r.shows(line, 18, DIM, 0, OUTCOME_BAND)


def open_reading(r):
    if ui(r.s)['view'] == 'home':
        swipe(r.s, dy=-100)
    assert ui(r.s)['view'] == 'response', ui(r.s)


# == V2-1: a tagged ending is never a wildcard for newer unnamed work =========================

@pytest.mark.parametrize('end', ['known-stopped', 'never-seen'])
def test_v2_1_tagged_end_cannot_end_newer_unnamed_work(ix, end):
    r, s = ix, ix.s
    r.turn_start('old-target')
    m = r.mark()
    tap(s, *r.control('stop'))
    assert [c.get('turn') for c in r.sent_since(m, 'cancel')] == ['old-target']
    r.send('turn.start')                     # newer work that Hermes does not name
    r.delta(NEW_TEXT)
    assert r.wait(lambda: work(s)['active'])
    r.require_label('stop', 'Stop task')     # the old stop is not pending for this work
    tag = 'old-target' if end == 'known-stopped' else 'never-seen'
    r.turn_end(tag, 'cancelled')
    s.run_for(0.3)
    r.snap(f'{end}-end-during-unnamed')
    w = work(s)
    assert w['active'] and w['outcome'] == 'none', ('a tagged end ended unnamed work', w)
    assert w['earlier_stop'] == ('stopped' if end == 'known-stopped' else 'unknown'), w
    assert ui(s)['view'] == 'response' and r.shows(NEW_TEXT, 24, TEXT)
    assert not reading_outcome(r, 'Stopped · may be partial'), 'old outcome rendered under new text'
    r.require_label('stop', 'Stop task')
    assert 'talk' not in ui(s)['controls']
    assert settings_refused(s), 'settings opened while new work is open'
    m2 = r.mark()
    cancel_twice(s)
    cancels = r.sent_since(m2, 'cancel')
    assert len(cancels) == 1 and 'turn' not in cancels[0], cancels
    assert r.wait(lambda: r.brain.count('cancel') == 2)
    # Bounded legacy: an end without any turn still ends the unnamed work, unconfirmed.
    r.send('turn.end', outcome='cancelled')
    assert r.wait(lambda: not work(s)['active'])
    s.run_for(0.3)
    r.snap('untagged-end')
    w = work(s)
    assert w['outcome'] == 'unknown' and w['stop'] == 'unknown', w
    assert w['earlier_stop'] == ('stopped' if end == 'known-stopped' else 'unknown'), w
    assert reading_outcome(r, 'Unknown · may be partial') and r.shows(NEW_TEXT, 24, TEXT)


# == V2-2: local capture and presentation never end remote work ===============================

@pytest.mark.parametrize('during', ['nothing', 'button', 'end', 'start'])
def test_v2_2a_discarded_capture_never_ends_open_remote_work(ix, during):
    r, s = ix, ix.s
    if during == 'start':
        s.type_text('open request')          # a request whose turn has not started yet
        assert r.wait(lambda: r.brain.count('text') == 1)
    else:
        r.turn_start('remote-open')
        r.reply(LONG, turn='remote-open')    # final text, but no turn.end
        s.run_for(6.4)
        swipe(s, dx=100)
    assert ui(s)['view'] == 'home' and work(s)['active']
    m = r.mark()
    s.press('talk')
    s.run_for(0.5)
    assert ui(s)['activity'] == 'recording'
    if during == 'end':
        r.turn_end('remote-open', 'success')
    elif during == 'start':
        r.turn_start('late-start')
    r.snap('capture-over-open-work')
    if during == 'button':
        s.tap('cancel')                      # physical CANCEL while TALK is held: one action only
    else:
        tap(s, *r.control('discard'))
    s.release('talk')
    s.run_for(0.3)
    r.snap('after-discard')
    sent = r.sent_types(m) & REQUESTS
    assert sent == {'audio.start', 'audio.cancel'}, r.sent_since(m)
    assert r.brain.count('utterance') == 0 and r.brain.count('cancel') == 0
    if during == 'end':
        # The lifecycle event during the capture still applies to its own work.
        w = work(s)
        assert not w['active'] and w['outcome'] == 'finished', w
        assert 'stop' not in ui(s)['controls']
        assert r.headline('Discarded') and r.detail('Not sent as a request')
        settings_open_and_close(s)
        return
    w = work(s)
    assert w['active'] and w['outcome'] == 'none', ('a discarded capture ended remote work', w)
    r.require_label('stop', 'Stop task')
    assert 'talk' not in ui(s)['controls']
    assert not r.headline('Discarded'), 'Home claims nothing is happening while work is open'
    assert settings_refused(s), 'settings opened over open remote work'
    turn = 'late-start' if during == 'start' else 'remote-open'
    m2 = r.mark()
    cancel_twice(s)
    assert [c.get('turn') for c in r.sent_since(m2, 'cancel')] == [turn], r.sent_since(m2)
    assert r.wait(lambda: r.brain.count('cancel') == 1)
    s.set_network(False)
    assert s.wait_screen('offline', timeout=5)
    assert ui(s)['detail'].startswith('Task status unknown'), ui(s)
    r.snap('offline')
    settings_open_and_close(s)               # recovery stays reachable while offline
    m3 = r.mark()
    s.set_network(True)
    assert s.wait_screen('ready', timeout=10)
    s.run_for(0.5)
    assert not (r.sent_types(m3) & REQUESTS) and r.brain.count('cancel') == 1, 'reconnect replayed'
    w = work(s)
    assert not w['active'] and w['stop'] == 'unknown' and w['outcome'] == 'unknown', w
    r.turn_end(turn, 'cancelled')            # late matching evidence still resolves it
    assert work(s)['stop'] == 'stopped' and work(s)['outcome'] == 'stopped'


@pytest.mark.parametrize('stop_first', [False, True], ids=['no-stop', 'pending-stop'])
def test_v2_2b_final_without_start_never_inherits_an_older_ending(ix, stop_first):
    r, s = ix, ix.s
    r.turn_start('old-done')
    r.reply('Completed old reply.', turn='old-done')
    r.turn_end('old-done', 'success')
    assert r.wait(lambda: ui(s)['activity'] == 'idle')
    s.type_text('second request')
    assert r.wait(lambda: r.brain.count('text') == 1)
    req = [x for x in s.sent if x['type'] == 'text'][-1]['id']
    assert work(s)['active']
    r.reply('New final answer.')             # legacy untagged final; no turn.start or turn.end
    s.run_for(6.4)
    r.snap('final-without-start')
    w = work(s)
    assert w['active'] and w['outcome'] == 'none', ('new work inherited the old ending', w)
    open_reading(r)
    assert r.shows('New final answer.', 24, TEXT), 'legacy untagged text must stay readable'
    assert not reading_outcome(r, 'Finished')
    r.require_label('stop', 'Stop task')
    assert 'talk' not in ui(s)['controls']
    assert settings_refused(s), 'settings opened while the new request is open'
    m = r.mark()
    if stop_first:
        cancel_twice(s)
        c = r.sent_since(m, 'cancel')
        assert len(c) == 1 and c[0].get('request') == req and 'turn' not in c[0], c
        assert r.wait(lambda: r.brain.count('cancel') == 1)
    s.set_network(False)
    assert s.wait_screen('offline', timeout=5)
    assert ui(s)['detail'].startswith('Task status unknown'), ui(s)
    r.snap('offline')
    settings_open_and_close(s)
    m2 = r.mark()
    s.set_network(True)
    assert s.wait_screen('ready', timeout=10)
    s.run_for(0.5)
    assert not (r.sent_types(m2) & REQUESTS), 'reconnect replayed'
    assert r.brain.count('cancel') == (1 if stop_first else 0) and r.brain.count('text') == 1
    w = work(s)
    assert not w['active'] and w['outcome'] == 'unknown', w
    open_reading(r)
    s.run_for(0.3)
    r.snap('reading-after-reconnect')
    assert r.shows('New final answer.', 24, TEXT)
    assert reading_outcome(r, 'Unknown · may be partial')


# == V2-3: displayed text and its outcome belong to the same work =============================

@pytest.mark.parametrize('old', ['final', 'delta', 'request-window'])
def test_v2_3_old_tagged_text_never_carries_the_new_outcome(ix, old):
    r, s = ix, ix.s
    r.turn_start('old-reply')
    r.reply(OLD_TEXT, turn='old-reply')
    r.turn_end('old-reply', 'success')
    s.run_for(0.3)
    if old == 'request-window':
        s.type_text('new request')
        assert r.wait(lambda: r.brain.count('text') == 1)
        r.reply(OLD_LATE, turn='old-reply')  # explicitly old text before the new turn starts
        s.run_for(0.3)
        assert work(s)['active'] and not r.shows(OLD_LATE, 24, TEXT), 'old tagged text was shown'
    r.turn_start('new-reply')
    r.delta(NEW_TEXT, turn='new-reply')
    assert ui(s)['view'] == 'response'
    m = r.mark()
    tap(s, *r.control('stop'))
    assert [c.get('turn') for c in r.sent_since(m, 'cancel')] == ['new-reply']
    if old == 'delta':
        r.delta(OLD_LATE, turn='old-reply')
    else:
        r.reply(OLD_LATE, turn='old-reply')
    s.run_for(0.3)
    r.snap('old-text-during-new-work')
    assert r.shows(NEW_TEXT, 24, TEXT) and not r.shows(OLD_LATE, 24, TEXT), 'old text replaced new text'
    assert work(s)['active'] and work(s)['stop'] == 'requested'
    r.turn_end('new-reply', 'cancelled')
    assert r.wait(lambda: not work(s)['active'])
    s.run_for(0.3)
    r.snap('new-outcome')
    assert ui(s)['view'] == 'response'
    assert r.shows(NEW_TEXT, 24, TEXT) and not r.shows(OLD_LATE, 24, TEXT)
    assert reading_outcome(r, 'Stopped · may be partial'), 'the new outcome is missing under its own text'
    assert r.brain.count('cancel') == 1
