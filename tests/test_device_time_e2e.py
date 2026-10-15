"""Host time on the device: real native core, production loopback hub, disposable store.

The host puts its wall clock and UTC offset in ``welcome`` and refreshes it on every
heartbeat ``ping`` (``time: {unix, utc_offset_s}``); the device keeps an offset from its
own monotonic ``now_ms()``. Failure modes covered:
- an older host that sends no time: the device must show no time rather than invent one;
- a host clock jump (NTP correction, DST change): the next heartbeat corrects the device;
- Wi-Fi loss: the device keeps counting from the last sync, but stops claiming a time
  once the sync is too old to trust;
- malformed time fields are ignored instead of shown;
- an older device ignores the field (protocol stays v1; only additive).
"""
from __future__ import annotations

import pytest

from conftest import LoopThread, requires_sim
from test_interaction_surface_e2e import Rig, _brain_class, _instrument

pytestmark = requires_sim

# 2026-10-15 17:46:40 UTC; 10:46 in Los Angeles (PDT, UTC-7).
T0 = 1_792_000_000
PDT = -7 * 3600


def NO_TIME():
    """An older host: it shares no time, so welcome and ping carry no ``time`` field."""
    return None


class Clock:
    def __init__(self, unix=T0, offset=PDT):
        self.unix, self.offset = unix, offset

    def __call__(self):
        return self.unix, self.offset


def make(tmp_path, clock, heartbeat_s=5):
    from hermes_gadget.sim import Simulator
    from hermes_gadget_plugin.hub import DeviceHub
    from hermes_gadget_plugin.store import DeviceStore
    lt = LoopThread()
    brain = _brain_class()()
    hub = DeviceHub(DeviceStore(tmp_path / 'server'), brain, host='127.0.0.1', port=0,
                    heartbeat_s=heartbeat_s, clock=clock)
    brain.hub = hub
    lt.run(hub.start())
    sim = Simulator(url=f'ws://127.0.0.1:{hub.bound_port}/gadget', name='Tiny', board='sim-466x466-round',
                    state_dir=tmp_path / 'device')
    # The device's monotonic clock runs in real time plus a jump the test can add, so boot
    # and the handshake proceed normally and the test can still skip hours.
    import time as _time
    t0 = _time.monotonic()
    sim.vclock = [5_000]
    sim.now_ms = lambda: sim.vclock[0] + int((_time.monotonic() - t0) * 1000)
    r = Rig(sim, hub, brain, lt, tmp_path / 'out')
    _instrument(r, sim)
    sim.start()
    assert sim.wait_screen('ready', timeout=10)
    r.device_id = sim.status()['device_id']
    return r


def close(r):
    r.s.close()
    r.lt.run(r.hub.stop())
    r.lt.stop()


def clock(r):
    return r.s.status()['clock']


def advance(r, seconds):
    r.s.vclock[0] += int(seconds * 1000)
    r.s.step()


def welcome(r):
    return [m for m in r.s.received if m.get('type') == 'welcome'][-1]


@pytest.fixture
def rig(tmp_path):
    made = []

    def _make(clock=Clock(), **kw):
        r = make(tmp_path / f'r{len(made)}', clock, **kw)
        made.append(r)
        return r
    yield _make
    for r in made:
        close(r)


def test_welcome_carries_host_time_and_the_device_shows_host_local_time(rig):
    r = rig(Clock())
    w = welcome(r)
    assert w['time'] == {'unix': T0, 'utc_offset_s': PDT}, w
    assert w['proto'] == 1
    c = clock(r)
    assert c['known'] is True and c['local'] == '10:46', c
    # The device clock runs on its own between heartbeats.
    advance(r, 14 * 60)
    assert clock(r)['local'] == '11:00'


def test_an_older_host_without_time_leaves_the_device_without_a_time(rig):
    r = rig(NO_TIME)
    assert 'time' not in welcome(r)
    c = clock(r)
    assert c['known'] is False and 'local' not in c, c
    advance(r, 3600)
    assert clock(r)['known'] is False


def test_a_host_clock_jump_is_corrected_on_the_next_heartbeat(rig):
    host = Clock()
    r = rig(host)
    assert clock(r)['local'] == '10:46'
    # DST ends / NTP corrects: host is now an hour behind what the device believes.
    host.unix -= 3600
    host.offset = -8 * 3600
    pings = len([m for m in r.s.received if m.get('type') == 'ping'])
    assert r.s.wait_for(lambda: len([m for m in r.s.received if m.get('type') == 'ping']) > pings, timeout=12)
    ping = [m for m in r.s.received if m.get('type') == 'ping'][-1]
    assert ping['time'] == {'unix': T0 - 3600, 'utc_offset_s': -8 * 3600}, ping
    assert clock(r)['local'] == '08:46', clock(r)


def test_offline_the_device_counts_from_the_last_sync_then_stops_claiming_a_time(rig):
    r = rig(Clock())
    r.s.set_network(False)
    r.s.run_for(0.2)
    assert r.s.status()['screen'] == 'offline'
    advance(r, 2 * 3600 + 5 * 60)
    c = clock(r)
    assert c['known'] is True and c['local'] == '12:51', c
    # A day without a sync: the device no longer presents its count as the time.
    advance(r, 22 * 3600)
    assert clock(r)['known'] is False, clock(r)


@pytest.mark.parametrize('bad', [
    {'unix': 'soon', 'utc_offset_s': 0},
    {'unix': 0, 'utc_offset_s': 0},
    {'unix': T0, 'utc_offset_s': 30 * 3600},
    'noon',
])
def test_a_malformed_time_is_ignored(rig, bad):
    r = rig(NO_TIME)
    r.send('ping', ts=1, time=bad)
    r.s.run_for(0.2)
    assert clock(r)['known'] is False, (bad, clock(r))
