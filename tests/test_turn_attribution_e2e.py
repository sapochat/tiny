"""Turn attribution: a ``turn.start`` that names the device request it serves.

Same production path as ``tests/test_interaction_surface_e2e.py``: native App/Ui through the
simulator library, the production DeviceHub on loopback with a disposable store, and the
recording EchoBrain. The host now sends ``turn.start {"turn", "request"}``; these workflows
pin what the device does with that name, and that a host without it behaves as before.
Evidence: IX_ARTIFACTS (run.json, fixtures/, per-test snapshots).
"""
from __future__ import annotations

import pytest

from conftest import REPO, requires_sim
from test_interaction_surface_e2e import ix, ix_run  # noqa: F401  fixtures only
from test_touch_navigation import tap

pytestmark = requires_sim


@pytest.fixture(autouse=True)
def attribution_evidence(ix_run):
    copy = ix_run / 'fixtures' / 'test_turn_attribution_e2e.py'
    copy.parent.mkdir(parents=True, exist_ok=True)
    copy.write_bytes((REPO / 'tests/test_turn_attribution_e2e.py').read_bytes())


def work(s):
    return s.status()['work']


def ask(r, text, n):
    r.s.type_text(text)
    assert r.wait(lambda: r.brain.count('text') == n)
    return [m for m in r.s.sent if m['type'] == 'text'][-1]['id']


def test_prestart_stop_is_confirmed_when_the_turn_names_its_request(ix):
    """Stop before Hermes starts; the turn that names this request settles it as Stopped."""
    r, s = ix, ix.s
    t1 = ask(r, 'first', 1)
    m = r.mark()
    tap(s, *r.control('stop'))
    assert [c.get('request') for c in r.sent_since(m, 'cancel')] == [t1]
    r.turn_start('first-turn', request=t1)
    assert r.headline('Stop requested') and len(r.sent_since(m, 'cancel')) == 1
    r.turn_end('first-turn', 'cancelled')
    assert r.wait(lambda: not work(s)['active'])
    r.snap('prestart-stop-confirmed')
    assert work(s)['stop'] == 'stopped' and work(s)['outcome'] == 'stopped', work(s)
    assert r.headline('Stopped') and not r.headline('Outcome unknown')


def test_prestart_stop_with_a_finished_turn_is_not_called_stopped(ix):
    r, s = ix, ix.s
    t1 = ask(r, 'first', 1)
    tap(s, *r.control('stop'))
    r.turn_start('first-turn', request=t1)
    r.turn_end('first-turn', 'success')
    assert r.wait(lambda: not work(s)['active'])
    assert work(s)['stop'] == 'finished' and r.headline('Finished') and not r.headline('Stopped'), work(s)


def test_an_older_requests_late_turn_never_becomes_the_new_requests_work(ix):
    """Stop t1 before it starts, ask t2, then t1's turn starts late: it is older work."""
    r, s = ix, ix.s
    t1 = ask(r, 'first', 1)
    tap(s, *r.control('stop'))
    t2 = ask(r, 'second', 2)
    r.turn_start('first-turn', request=t1)       # late start for the stopped request
    assert work(s)['lifecycle'] == 'requested', 'older work was adopted as the new request'
    r.reply('first answer', turn='first-turn')   # its text is not this request's reply
    r.turn_end('first-turn', 'cancelled')
    assert work(s)['lifecycle'] == 'requested' and work(s)['outcome'] == 'none', work(s)
    assert work(s)['earlier_stop'] == 'stopped', 'the named late end settles the earlier stop'
    r.turn_start('second-turn', request=t2)
    assert r.wait(lambda: work(s)['active'] and work(s)['lifecycle'] == 'started')
    m = r.mark()
    tap(s, *r.control('stop'))
    assert [c.get('turn') for c in r.sent_since(m, 'cancel')] == ['second-turn']
    r.reply('second answer', turn='second-turn')
    r.turn_end('second-turn', 'success')
    assert r.wait(lambda: not work(s)['active'])
    r.snap('late-older-turn')
    assert work(s)['stop'] == 'finished' and work(s)['earlier_stop'] == 'stopped', work(s)


def test_a_turn_for_a_request_this_device_never_sent_is_other_work(ix):
    """A turn naming some other client's request (shared session) is new, unrequested work."""
    r, s = ix, ix.s
    ask(r, 'mine', 1)
    r.turn_start('their-turn', request='not-this-device')
    assert work(s)['lifecycle'] == 'requested', work(s)


def test_a_host_that_does_not_name_requests_keeps_the_old_binding(ix):
    """Legacy host: the first turn.start after a request is still that request's turn."""
    r, s = ix, ix.s
    ask(r, 'first', 1)
    tap(s, *r.control('stop'))
    r.turn_start('first-turn')
    r.turn_end('first-turn', 'cancelled')
    assert r.wait(lambda: not work(s)['active'])
    assert work(s)['stop'] == 'unknown' and r.headline('Outcome unknown'), work(s)
