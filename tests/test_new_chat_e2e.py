"""New chat from quick controls: real native core, production loopback hub, touch only.

Failure modes this covers (each is a way the control could hurt more than help):
- a passing tap or a swipe across the target starts a new conversation by accident;
- it fires while Hermes is working, speaking, recording or asking, silently dropping that context;
- it fires offline, when nothing can reach Hermes;
- a finger that went down while it was available still fires after work began (stale contact);
- one hold sends more than one ``session.new``;
- the target is drawn off the round glass, overlaps a neighbour, or its label is clipped;
- after it fires, the screen still shows quick controls, so nothing confirms it happened.
"""
from conftest import requires_sim
from test_design_pass3_e2e import quick_controls
from test_face_first_font import rgb
from test_interaction_surface_e2e import ix, ix_run, inside_circle, overlap, TEXT, DIM, SURFACE  # noqa: F401
from test_touch_navigation import tap, ui

LIT = rgb(56, 56, 61)

pytestmark = requires_sim

HOLD_S = 1.0


def new_requests(r, mark=None):
    return r.sent_since(mark or {'sent': 0}, 'session.new')


def hold(s, x, y, seconds):
    s.touch(True, x, y)
    s.run_for(seconds)
    s.touch(False)
    s.step()
    s.run_for(0.3)


def test_new_chat_sits_in_the_action_row_on_the_glass(ix):
    r, s = ix, ix.s
    quick_controls(r)
    c = ui(s)['controls']
    assert 'new_chat' in c, ('no New chat target', c)
    rect = c['new_chat']
    assert inside_circle(rect), rect
    r.require_label('new_chat', 'New chat')
    # One row with Mute voice and Stop task, same height, no overlaps with anything.
    for name in ('silence', 'stop'):
        assert c[name][1] == rect[1] and c[name][3] == rect[3], (name, c[name], rect)
        r.require_label(name, 'Mute voice' if name == 'silence' else 'Stop task', fg=DIM, bg=0)
    for name, other in c.items():
        if name != 'new_chat':
            assert not overlap(rect, other), (name, other, rect)
    r.snap('controls-idle')


def test_a_tap_or_a_swipe_never_starts_a_new_chat(ix):
    r, s = ix, ix.s
    quick_controls(r)
    m = r.mark()
    x, y = r.control('new_chat')
    tap(s, x, y)
    s.run_for(HOLD_S + 0.3)
    assert not new_requests(r, m), 'a tap started a new chat'
    assert ui(s)['view'] == 'controls'
    # A tap says how to use it instead, then the label comes back.
    s.touch(True, x, y)
    s.step()
    s.touch(False)
    s.step()
    s.run_for(0.2)
    r.require_label('new_chat', 'Hold 1 sec')
    r.snap('tap-hint')
    s.run_for(2.2)
    r.require_label('new_chat', 'New chat')
    assert not new_requests(r, m), 'a tap started a new chat'
    # A finger that slides off before the hold completes does nothing either.
    s.touch(True, x, y)
    s.run_for(0.4)
    s.touch(True, x, y - 120)
    s.run_for(HOLD_S)
    s.touch(False)
    s.step()
    s.run_for(0.3)
    assert not new_requests(r, m), 'a moving finger started a new chat'


def test_holding_new_chat_sends_one_request_and_returns_home(ix):
    r, s = ix, ix.s
    quick_controls(r)
    m = r.mark()
    x, y = r.control('new_chat')
    s.touch(True, x, y)
    s.run_for(0.5)
    assert ui(s)['pressed'] == 'new_chat'
    r.require_label('new_chat', 'Hold 1 sec', bg=LIT)  # lit, and says how long
    assert not new_requests(r, m), 'fired before the hold completed'
    r.snap('holding')
    s.run_for(HOLD_S)  # past the hold, finger still down
    assert len(new_requests(r, m)) == 1
    s.run_for(0.5)  # a long hold still sends once
    s.touch(False)
    s.step()
    s.run_for(0.3)
    assert len(new_requests(r, m)) == 1, new_requests(r, m)
    assert r.brain.count('new_session') == 1
    assert ui(s)['view'] == 'home', 'quick controls stayed up after a new chat started'
    r.snap('after-new-chat')


def test_new_chat_is_inert_while_hermes_is_busy(ix):
    r, s = ix, ix.s
    r.turn_start('busy', request='req-busy')
    quick_controls(r)
    c = ui(s)['controls']
    assert 'new_chat' not in c, 'New chat is a live target during work'
    # Still drawn, in place and outlined, so the row does not jump around.
    r.turn_end('busy', 'success')
    assert r.wait(lambda: not s.status()['work']['active'])
    s.run_for(0.3)
    idle_rect = ui(s)['controls']['new_chat']
    r.turn_start('busy2', request='req-busy2')
    s.run_for(0.3)
    assert r.shows('New chat', 18, DIM, 0, tuple(idle_rect)), 'inert New chat is not drawn in place'
    m = r.mark()
    hold(s, idle_rect[0] + idle_rect[2] // 2, idle_rect[1] + idle_rect[3] // 2, HOLD_S + 0.4)
    assert not new_requests(r, m), 'New chat fired during work'
    r.snap('busy-inert')


def test_a_hold_that_began_idle_does_not_fire_once_work_starts(ix):
    r, s = ix, ix.s
    quick_controls(r)
    m = r.mark()
    x, y = r.control('new_chat')
    s.touch(True, x, y)
    s.run_for(0.4)
    r.turn_start('late', request='req-late')  # Hermes starts work under the finger
    s.run_for(HOLD_S)
    s.touch(False)
    s.step()
    s.run_for(0.3)
    assert not new_requests(r, m), 'a stale contact started a new chat during work'


def test_new_chat_is_inert_while_a_question_waits(ix):
    r, s = ix, ix.s
    quick_controls(r)
    rect = ui(s)['controls']['new_chat']
    r.send('prompt', id='q', title='Permission', text='Allow?')
    s.run_for(0.8)
    m = r.mark()
    hold(s, rect[0] + rect[2] // 2, rect[1] + rect[3] // 2, HOLD_S + 0.4)
    assert not new_requests(r, m)

