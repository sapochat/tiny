"""R-09 visible recovery routes on the round companion: real native core, production loopback hub.

The offline, connecting and setup-needed screens show two visible targets, **Retry now** and
**Settings**; Settings shows a visible **Done**. Holding the title stays as a shortcut. Retry
uses the existing reconnect path, brought forward. Failure modes covered:
- the only route out of an offline screen is a hidden title hold;
- Retry while an attempt is already in flight opens a second connection (must be idempotent);
- Retry during a task whose outcome is unknown resends that work (it must never replay);
- Retry while Wi-Fi is down pretends to connect;
- Retry on setup-needed (server rejected the device) keeps the stale error forever;
- Done is missing, outside the circle, or acts on a swipe that started on it;
- rectangular boards grow targets they never had.
"""
from __future__ import annotations

import socket
import time

import pytest

from conftest import LoopThread, requires_sim
from test_device_time_e2e import Clock, close, make
from test_interaction_surface_e2e import DIM, SURFACE, TEXT, Rig, _brain_class, _instrument, find_text, inside_circle
from test_touch_navigation import swipe, tap, ui

pytestmark = requires_sim

REQUESTS = {'text', 'audio.start', 'audio.end', 'audio.cancel', 'cancel', 'session.new', 'prompt.reply'}
ROUTES = ('retry', 'settings')


@pytest.fixture
def rig(tmp_path):
    made = []

    def _make():
        r = make(tmp_path / f'r{len(made)}', Clock())
        r.base = tmp_path / f'r{len(made)}'
        made.append(r)
        r.connects = []
        original = r.s.transport_connect

        def counted(url, sub):
            r.connects.append(url)
            return original(url, sub)
        r.s.transport_connect = counted
        r.s.run_for(0.4)
        return r
    yield _make
    for r in made:
        close(r)


def routes_drawn(r):
    """Both recovery targets are drawn, labelled at 24px and inside the safe circle."""
    controls = ui(r.s)['controls']
    for name, label in (('retry', 'Retry now'), ('settings', 'Settings')):
        assert name in controls, (name, controls)
        rect = tuple(controls[name])
        assert inside_circle(rect), (name, rect)
        assert rect[3] >= 48, (name, rect, 'target too short')
        assert find_text(r.s, label, 24, TEXT, SURFACE, rect) or find_text(r.s, label, 24, DIM, 0, rect), \
            (name, label, 'label not rendered')
    a, b = (tuple(controls[n]) for n in ROUTES)
    assert a[0] + a[2] <= b[0] or b[0] + b[2] <= a[0], 'targets overlap'


def center(rect):
    x, y, w, h = rect
    return x + w // 2, y + h // 2


def test_offline_shows_retry_and_settings_and_done_returns(rig):
    r = rig()
    s = r.s
    s.set_network(False)
    assert s.wait_screen('offline', timeout=5)
    s.run_for(0.3)
    routes_drawn(r)
    m = r.mark()
    # Retry with Wi-Fi down: honest feedback, no socket.
    n = len(r.connects)
    tap(s, *center(ui(s)['controls']['retry']))
    s.run_for(0.2)
    assert len(r.connects) == n and s.device.screen() == 'offline'
    assert ui(s)['hint'] == 'Waiting for Wi-Fi', ui(s)
    # The visible Settings route opens settings; Done is visible there and closes them.
    tap(s, *center(ui(s)['controls']['settings']))
    assert s.device.screen() == 'settings'
    s.run_for(0.2)
    done = tuple(ui(s)['controls']['done'])
    assert inside_circle(done) and done[3] >= 48, done
    assert find_text(s, 'Done', 24, TEXT, SURFACE, done), 'Done label not rendered'
    tap(s, *center(done))
    assert s.device.screen() == 'offline'
    assert not (r.sent_types(m) & REQUESTS)


def test_title_hold_stays_a_shortcut_on_offline(rig):
    r = rig()
    s = r.s
    s.set_network(False)
    assert s.wait_screen('offline', timeout=5)
    s.touch(True, 233, 62)
    s.run_for(1.3)
    s.touch(False)
    s.step()
    assert s.device.screen() == 'settings'


def test_swipe_from_done_changes_row_and_never_closes(rig):
    r = rig()
    s = r.s
    assert s.console('settings').startswith('@ok')
    s.run_for(0.2)
    detail = ui(s)['detail']
    x, y = center(ui(s)['controls']['done'])
    swipe(s, dy=-100, x=x, y=y)
    assert s.device.screen() == 'settings' and ui(s)['detail'] != detail
    # A finger resting on Done lights it; sliding off and lifting does nothing.
    s.touch(True, x, y)
    s.step()
    assert ui(s)['pressed'] == 'done'
    s.touch(True, x + 30, y - 100)
    s.touch(False)
    s.step()
    assert s.device.screen() == 'settings'


def test_retry_while_connecting_is_idempotent_and_never_resends_work(rig):
    r = rig()
    s = r.s
    r.turn_start('busy', request='req-busy')
    m = r.mark()
    port = r.hub.bound_port
    before = len(r.connects)
    # Hermes goes away; a silent listener on its port holds the next attempt in flight.
    r.run(r.hub.stop())
    hole = socket.socket()
    hole.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    hole.bind(('127.0.0.1', port))
    hole.listen(8)
    try:
        assert s.wait_for(lambda: len(r.connects) > before, timeout=5), 'no reconnect attempt'
        s.run_for(0.3)
        assert s.device.screen() == 'connecting'
        assert ui(s)['detail'] == 'Task status unknown', ui(s)
        routes_drawn(r)
        in_flight = len(r.connects)
        for _ in range(2):
            tap(s, *center(ui(s)['controls']['retry']))
            s.run_for(0.2)
        assert len(r.connects) == in_flight, 'Retry opened a second connection'
        assert ui(s)['hint'] == 'Already connecting'
    finally:
        hole.close()
    # The attempt fails; the device waits out its backoff. A new Hermes comes up on the
    # same port, and Retry connects now instead of after the backoff.
    assert s.wait_for(lambda: any('connection closed' in msg for _, msg in s.logs[-20:]), timeout=10)
    s.run_for(0.1)
    lt2 = LoopThread()
    brain = _brain_class()()
    from hermes_gadget_plugin.hub import DeviceHub
    from hermes_gadget_plugin.store import DeviceStore
    hub = DeviceHub(DeviceStore(r.base / 'server'), brain, host='127.0.0.1', port=port, heartbeat_s=5,
                    clock=Clock())
    brain.hub = hub
    lt2.run(hub.start())
    old_lt = r.lt
    r.hub, r.brain, r.lt = hub, brain, lt2
    old_lt.stop()
    try:
        pending = len(r.connects)
        t0 = time.monotonic()
        tap(s, *center(ui(s)['controls']['retry']))
        assert len(r.connects) == pending + 1, 'Retry did not connect now'
        assert time.monotonic() - t0 < 0.5
        assert s.wait_screen('ready', timeout=10)
        s.run_for(0.5)
        assert not (r.sent_types(m) & REQUESTS), r.sent_since(m)
        assert not [c for c in brain.calls if c['call'] in ('text', 'utterance', 'cancel', 'new_session')]
        assert r.headline('Connection lost') and r.detail('Task status unknown')
    finally:
        pass


def test_retry_on_setup_needed_clears_the_error_and_reconnects(rig):
    r = rig()
    s = r.s
    r.send('error', code='auth_failed', message='Device token rejected')
    assert s.wait_screen('error', timeout=5)
    s.run_for(0.3)
    routes_drawn(r)
    m = r.mark()
    n = len(r.connects)
    tap(s, *center(ui(s)['controls']['retry']))
    assert s.wait_screen('ready', timeout=10)
    assert len(r.connects) == n + 1
    assert not (r.sent_types(m) & REQUESTS)


def test_rectangular_touch_board_has_no_new_targets(tmp_path, monkeypatch):
    from hermes_gadget.sim import Simulator, runner
    monkeypatch.setitem(runner.BOARDS, 'sim-320x240-touch', runner.Board('sim-320x240-touch', 320, 240, touch=True))
    from hermes_gadget_plugin.hub import DeviceHub
    from hermes_gadget_plugin.store import DeviceStore
    lt = LoopThread()
    brain = _brain_class()()
    hub = DeviceHub(DeviceStore(tmp_path / 'server'), brain, host='127.0.0.1', port=0, heartbeat_s=5)
    brain.hub = hub
    lt.run(hub.start())
    sim = Simulator(url=f'ws://127.0.0.1:{hub.bound_port}/gadget', name='Legacy', board='sim-320x240-touch',
                    state_dir=tmp_path / 'device')
    rr = Rig(sim, hub, brain, lt, tmp_path / 'out')
    _instrument(rr, sim)
    try:
        sim.start()
        assert sim.wait_screen('ready', timeout=10)
        sim.set_network(False)
        assert sim.wait_screen('offline', timeout=5)
        assert not set(ui(sim)['controls']) & {'retry', 'done'}
        assert sim.console('settings').startswith('@ok')
        sim.step()
        assert 'done' not in ui(sim)['controls']
    finally:
        sim.close()
        lt.run(hub.stop())
        lt.stop()
