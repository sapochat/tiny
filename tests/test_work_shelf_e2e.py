"""Recent work through native App and the production loopback hub.

Synthetic final replies only; disposable stores; no providers or hardware.
Run with IX_ARTIFACTS pointing at a fresh evidence directory.
"""
import json

import pytest

from conftest import requires_sim
from test_interaction_surface_e2e import ix, ix_run, REQUESTS
from test_touch_navigation import tap, swipe, ui

pytestmark = requires_sim


def snapshot(r):
    assert r.wait(lambda: any(m.get('type') == 'work' for m in r.s.received)), 'no negotiated work snapshot'
    return [m for m in r.s.received if m.get('type') == 'work'][-1]['items']


def finish(r, turn='job-1', text='Synthetic final result'):
    r.turn_start(turn, request='request-' + turn)
    r.reply(text, turn=turn)
    r.turn_end(turn, 'success')
    assert r.wait(lambda: any(m.get('type') == 'work' and any(i['origin']['turn'] == turn and i['stage'] == 'finished' for i in m['items']) for m in r.s.received))
    return next(i for i in snapshot(r) if i['origin']['turn'] == turn)


def reconnect(r):
    r.s.set_network(False)
    assert r.s.wait_screen('offline', timeout=5)
    mark = r.mark()
    r.s.set_network(True)
    assert r.s.wait_screen('ready', timeout=10)
    assert r.wait(lambda: any(m.get('type') == 'work' for m in r.s.received[mark['received']:]))
    return mark


def test_recent_snapshot_reconnect_without_replay(ix):
    r = ix
    rec = finish(r)
    assert rec['work_id'] != rec['origin']['turn']
    assert rec['result'] == {'revision': 1, 'glance': 'Synthetic final result'}
    mark = reconnect(r)
    assert snapshot(r) == [rec]
    assert not ({m['type'] for m in r.s.received[mark['received']:]} & {'turn.start', 'turn.end', 'reply', 'reply.delta', 'audio.start'})
    assert not (r.sent_types(mark) & REQUESTS)
    assert not r.brain.calls
    r.snap('reconnected-snapshot')


def test_recent_bounded_eviction(ix):
    r = ix
    records = [finish(r, f'job-{n}') for n in range(9)]
    items = snapshot(r)
    assert len(items) == 8
    assert records[0]['work_id'] not in {i['work_id'] for i in items}
    assert {i['work_id'] for i in items} == {i['work_id'] for i in records[1:]}


def test_recent_unknown_requires_matching_outcome(ix):
    r = ix
    r.turn_start('interrupted', request='request-interrupted')
    reconnect(r)
    assert snapshot(r)[0]['stage'] == 'unknown'
    r.turn_end('unrelated', 'success')
    r.turn_start('interrupted', request='request-interrupted')
    r.s.run_for(.1)
    assert snapshot(r)[0]['stage'] == 'unknown'
    r.turn_end('interrupted', 'failure')
    assert r.wait(lambda: snapshot(r)[0]['stage'] == 'failed')


def test_recent_reading_revision_is_pinned(ix):
    r = ix
    finish(r, text=('Line one\nLine two\n' * 12)[:240])
    swipe(r.s, dx=100)
    swipe(r.s, dy=100)
    tap(r.s, *r.control('recent'))
    r.snap('recent-shelf')
    tap(r.s, *r.control('work0'))
    swipe(r.s, 0, -120)
    before = r.s.status()['ui']
    assert before['scroll'] > 0
    pixels = r.s.device.framebuffer_rows()
    r.reply('Replacement text', turn='job-1')
    r.s.run_for(.2)
    after = r.s.status()['ui']
    assert r.s.device.framebuffer_rows() == pixels
    assert after['scroll'] == before['scroll']
    r.snap('pinned-result')


def test_recent_clear_and_pairing_revocation(ix):
    r = ix
    finish(r)
    r.run(r.session.set_paired(False))
    r.s.run_for(.2)
    assert snapshot(r) == []
    r.run(r.session.set_paired(True))
    r.s.run_for(.2)
    assert len(snapshot(r)) == 1
    r.hub.work.clear(r.device_id)
    reconnect(r)
    assert snapshot(r) == []
    finish(r, 'forgotten')
    assert r.hub.store.forget(r.device_id)
    r.run(r.session.work_snapshot())
    assert r.wait(lambda: snapshot(r) == [])
    reconnect(r)  # automatic re-enrollment cannot recover the old generation
    assert snapshot(r) == []


@pytest.mark.parametrize("interrupted", [False, True])
def test_recent_restart_and_owner_isolation(ix, tmp_path, interrupted):
    from hermes_gadget.sim import Simulator
    from hermes_gadget_plugin.hub import DeviceHub
    from hermes_gadget_plugin.store import DeviceStore
    r = ix
    rec = finish(r)
    if interrupted:
        r.turn_start('interrupted', request='request-i')
        assert r.wait(lambda: len(snapshot(r)) == 2)
    r.s.set_network(False)
    assert r.s.wait_screen('offline', timeout=5)
    port = r.hub.bound_port
    r.run(r.hub.stop())
    new = DeviceHub(DeviceStore(tmp_path / 'server'), r.brain, host='127.0.0.1', port=port)
    r.run(new.start())
    try:
        for state, own in [('device', True), ('other-device', False)]:
            sim = Simulator(url=f'ws://127.0.0.1:{port}/gadget', board='sim-466x466-round', state_dir=tmp_path / state)
            try:
                sim.start()
                assert sim.wait_screen('ready', timeout=10)
                assert sim.wait_for(lambda: any(m.get('type') == 'work' for m in sim.received))
                items = [m for m in sim.received if m.get('type') == 'work'][-1]['items']
                if own and interrupted:
                    assert items[0]['origin']['turn'] == 'interrupted'
                    assert items[0]['stage'] == 'unknown'
                    assert items[1:] == [rec]
                    session = hub_session = new.sessions[sim.status()['device_id']]
                    r.run(session.turn_end('not-interrupted', 'success'))
                    assert new.work.items(session.device_id)[0]['stage'] == 'unknown'
                    r.run(session.turn_end('interrupted', 'success'))
                    assert sim.wait_for(lambda: any(m.get('type') == 'work' and m['items'][0]['stage'] == 'finished' for m in sim.received))
                else:
                    assert items == ([rec] if own else [])
                assert not ({m['type'] for m in sim.received} & {'reply', 'turn.start', 'audio.start'})
            finally:
                sim.close()
    finally:
        r.run(new.stop())


def test_recent_corrupt_store_quarantined(ix, caplog):
    from hermes_gadget_plugin.hub import DeviceHub
    r = ix
    path = r.hub.store.path.with_name('work.json')
    path.write_text('{broken')
    DeviceHub(r.hub.store, r.brain, host='127.0.0.1', port=0)
    saved = list(path.parent.glob('work.json.corrupt-*'))
    assert len(saved) == 1 and saved[0].read_text() == '{broken'
    assert 'corrupt' in caplog.text.lower()


def test_recent_late_delegate_updates_new_connection_without_replay(ix):
    r = ix
    old = r.session
    r.turn_start('late', request='request-late')
    mark = reconnect(r)
    r.run(old.send_reply('Late result', turn='late'))
    r.run(old.turn_end('late', 'success'))
    assert r.wait(lambda: snapshot(r)[0]['stage'] == 'finished')
    assert snapshot(r)[0]['result']['glance'] == 'Late result'
    assert not ({m['type'] for m in r.s.received[mark['received']:]} & {'reply', 'turn.start', 'turn.end', 'audio.start'})


def test_recent_revocation_drops_open_reader_before_repair(ix):
    r = ix
    finish(r)
    swipe(r.s, dx=100)
    swipe(r.s, dy=100)
    tap(r.s, *r.control('recent'))
    tap(r.s, *r.control('work0'))
    r.send('unpaired')
    assert ui(r.s)['view'] != 'result'
    r.send('paired')  # before any newly authorized snapshot arrives
    assert ui(r.s)['view'] != 'result'


def test_recent_closed_session_still_reports_nonjournal_send_failure(ix):
    r = ix
    old = r.session
    reconnect(r)
    with pytest.raises(Exception):
        r.run(old.send_notice('Not delivered'))


def test_recent_delayed_old_shutdown_cannot_interrupt_new_work(ix):
    r = ix
    old = r.session
    r.turn_start('old-job', request='old-request')
    reconnect(r)
    r.turn_start('new-job', request='new-request')
    old._shutdown()  # delayed/stale teardown must not own a new session's turn
    assert next(i for i in r.hub.work.items(r.device_id) if i['origin']['turn'] == 'new-job')['stage'] == 'running'


def test_recent_unpaired_welcome_drops_reader(ix):
    r = ix
    finish(r)
    swipe(r.s, dx=100)
    swipe(r.s, dy=100)
    tap(r.s, *r.control('recent'))
    tap(r.s, *r.control('work0'))
    r.s.set_network(False)
    assert r.s.wait_screen('offline', timeout=5)
    async def denied(session):
        return False
    r.brain.is_paired = denied
    r.s.set_network(True)
    assert r.wait(lambda: any(m.get('type') == 'welcome' and not m['paired'] for m in r.s.received))
    r.send('paired')  # before a newly authorized snapshot
    assert ui(r.s)['view'] != 'result'


def test_recent_late_start_on_closed_session_is_not_running(ix):
    r = ix
    old = r.session
    reconnect(r)
    r.run(old.turn_start('late-start', request='late-request'))
    assert not any(i['stage'] == 'running' for i in r.hub.work.items(r.device_id))


def test_recent_removed_item_closes_reader(ix):
    r = ix
    finish(r)
    swipe(r.s, dx=100)
    swipe(r.s, dy=100)
    tap(r.s, *r.control('recent'))
    tap(r.s, *r.control('work0'))
    assert ui(r.s)['view'] == 'result'
    r.hub.work.clear(r.device_id)
    r.run(r.session.work_snapshot())
    assert r.wait(lambda: ui(r.s)['view'] == 'recent')


def test_recent_stale_contact_cannot_open_replacement(ix):
    r = ix
    finish(r)
    swipe(r.s, dx=100)
    swipe(r.s, dy=100)
    tap(r.s, *r.control('recent'))
    x, y = r.control('work0')
    r.s.touch(True, x, y)
    r.s.run_for(.04)
    finish(r, 'replacement')
    r.s.touch(False, x, y)
    r.s.run_for(.1)
    assert ui(r.s)['view'] == 'recent'
    assert not r.brain.calls


def test_legacy_native_gets_no_work(ix):
    import os
    if os.environ.get('WORK_LEGACY_NATIVE') != '1':
        pytest.skip('run separately with frozen baseline HGSIM_LIBRARY')
    r = ix
    r.turn_start('legacy', request='legacy-request')
    r.reply('legacy reply', turn='legacy')
    r.turn_end('legacy', 'success')
    r.s.run_for(.2)
    assert not any(m.get('type', '').startswith('work') for m in r.s.received + r.s.sent)
    assert 'work' not in next(m for m in r.s.received if m['type'] == 'welcome')
    assert r.hub.work.items(r.device_id) == []


def test_new_native_with_frozen_legacy_host(ix, tmp_path):
    import importlib.util
    import os
    import sys
    from hermes_gadget.sim import Simulator
    from hermes_gadget_plugin.store import DeviceStore
    source = os.environ.get('WORK_LEGACY_HUB')
    if not source:
        pytest.skip('requires frozen baseline hub.py via WORK_LEGACY_HUB')
    spec = importlib.util.spec_from_file_location('hermes_gadget_plugin._legacy_hub', source)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    r = ix
    hub = module.DeviceHub(DeviceStore(tmp_path / 'legacy-server'), r.brain, host='127.0.0.1', port=0)
    r.run(hub.start())
    sim = Simulator(url=f'ws://127.0.0.1:{hub.bound_port}/gadget', board='sim-466x466-round', state_dir=tmp_path / 'legacy-client')
    try:
        sim.start()
        assert sim.wait_screen('ready', timeout=10)
        sim.run_for(.2)
        assert not any(m.get('type', '').startswith('work') for m in sim.sent + sim.received)
        swipe(sim, dy=100)
        assert 'recent' not in ui(sim)['controls']
    finally:
        sim.close()
        r.run(hub.stop())


def test_recent_durable_store_private(ix):
    r = ix
    rec = finish(r)
    path = r.hub.store.path.with_name('work.json')
    assert path.exists()
    assert path.stat().st_mode & 0o777 == 0o600
    data = json.loads(path.read_text())
    assert data['v'] == 1
    assert data['items'] == [rec]
    assert len(rec['result']['glance']) <= 240


def _broken_disk(monkeypatch):
    import errno
    from hermes_gadget_plugin import work

    def full(self):
        raise OSError(errno.ENOSPC, 'No space left on device (injected)')
    monkeypatch.setattr(work.WorkStore, '_save', full)


def test_recent_store_write_failure_never_blocks_live_work(ix, monkeypatch, caplog):
    """A full or read-only disk loses history, never the conversation."""
    r = ix
    _broken_disk(monkeypatch)
    m = r.mark()
    r.turn_start('disk-full', request='request-disk-full')
    r.reply('Delivered despite the disk', turn='disk-full')
    r.turn_end('disk-full', 'success')
    got = [x for x in r.s.received[m['received']:] if x.get('type') in ('turn.start', 'reply', 'turn.end')]
    assert [x['type'] for x in got] == ['turn.start', 'reply', 'turn.end'], got
    assert 'work store' in caplog.text.lower()


def test_recent_store_write_failure_never_blocks_teardown(ix, monkeypatch):
    """Disconnect with running work still tears the session down when the journal can't save."""
    r = ix
    r.turn_start('running', request='request-running')
    _broken_disk(monkeypatch)
    old = r.session
    reconnect(r)
    assert old.closed and r.session is not old


@pytest.mark.parametrize('bad', [
    {'stage': 'exploded'},
    {'result': {'revision': -1, 'glance': 'x'}},
    {'result': {'revision': 1, 'glance': 'x' * 241}},
    {'origin': {'turn': 3, 'request': ''}},
])
def test_recent_invalid_record_is_quarantined_not_loaded(ix, bad, caplog):
    """Schema checks are real checks: they must also hold under `python -O`."""
    from hermes_gadget_plugin.hub import DeviceHub
    r = ix
    rec = finish(r)
    path = r.hub.store.path.with_name('work.json')
    data = json.loads(path.read_text())
    data['items'][0].update(bad)
    path.write_text(json.dumps(data))
    DeviceHub(r.hub.store, r.brain, host='127.0.0.1', port=0)
    assert len(list(path.parent.glob('work.json.corrupt-*'))) == 1
    assert not path.exists() or json.loads(path.read_text())['items'] == []
    assert rec['work_id']
