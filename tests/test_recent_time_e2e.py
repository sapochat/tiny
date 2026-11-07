"""R-10 Recent with time and fewer taps: real native core, production loopback hub.

Each Recent card shows how long ago its job last changed ("Just now", "12 min", "3 hr",
"Yesterday", "3 days"), computed on the device from the host's ``updated_at`` and the
host time the device already keeps. Home's "Last task: ..." title opens that job's
result in one tap. Failure modes covered:
- an age invented without a trusted host time (older host): no age is shown;
- ages that never move: they follow the device clock;
- "Yesterday" decided by elapsed hours instead of the host's local calendar day;
- Last task opening the wrong job (an older one, or the newest instead of its own);
- a tap on the title replaying or sending anything;
- the title hold no longer opening Settings, or a hold also opening the result;
- a stale contact (the record changed under the finger) still opening something;
- a target offered when there is no matching record.
"""
from __future__ import annotations

import types

import pytest

from conftest import requires_sim
from test_device_time_e2e import NO_TIME, PDT, T0, Clock, advance, close, make
from test_interaction_surface_e2e import DIM, SURFACE, TEXT, find_text, inside_circle, overlap
from test_touch_navigation import swipe, tap, ui

pytestmark = requires_sim

REQUESTS = {'text', 'audio.start', 'audio.end', 'audio.cancel', 'cancel', 'session.new', 'prompt.reply'}
HOME_TITLE = (0, 40, 466, 56)


@pytest.fixture
def rig(tmp_path, monkeypatch):
    import hermes_gadget_plugin.work as work_mod
    host = [float(T0)]
    # The work journal stamps updated_at from this clock; the device clock is the hub's.
    monkeypatch.setattr(work_mod, 'time', types.SimpleNamespace(time=lambda: host[0]))
    made = []

    def _make(clock=None):
        r = make(tmp_path / f'r{len(made)}', Clock() if clock is None else clock)
        r.host = host
        made.append(r)
        return r
    yield _make
    for r in made:
        close(r)


def job(r, turn, text, at, outcome='success'):
    r.host[0] = float(at)
    r.turn_start(turn, request='req-' + turn)
    r.reply(text, turn=turn)
    r.turn_end(turn, outcome)
    assert r.s.wait_for(lambda: any(m.get('type') == 'work' and any(
        i['origin']['turn'] == turn and i['stage'] != 'running' for i in m['items']) for m in r.s.received), timeout=5)
    r.s.run_for(0.2)


def to_recent(r):
    if ui(r.s)['view'] != 'home':
        swipe(r.s, dx=100)
    swipe(r.s, dy=100)
    tap(r.s, *r.control('recent'))
    r.s.run_for(0.6)  # let the slide finish before reading pixels
    assert ui(r.s)['view'] == 'recent', ui(r.s)


def home(r):
    if ui(r.s)['view'] != 'home':
        swipe(r.s, dx=100)
    r.s.run_for(0.6)
    assert ui(r.s)['view'] == 'home', ui(r.s)


def card_age(r, i, age):
    box = tuple(ui(r.s)['controls'][f'work{i}'])
    return find_text(r.s, age, 18, DIM, SURFACE, box)


def test_cards_show_their_age_from_host_time(rig):
    r = rig()
    # 10:46 PDT on the host. Newest first: the shelf orders by updated_at.
    job(r, 'days', 'Plants watered.', T0 - 3 * 86400)
    job(r, 'yday', 'Package tracked.', T0 - 20 * 3600)      # 14:46 the previous day
    job(r, 'hours', 'Thermostat set.', T0 - 3 * 3600 - 300)  # 07:41 today
    job(r, 'mins', 'Lamp is on.', T0 - 12 * 60)
    job(r, 'now', 'Timer noted.', T0 - 20)
    to_recent(r)
    assert ui(r.s)['work_ages'] == ['Just now', '12 min', '3 hr'], ui(r.s)
    for i, age in enumerate(['Just now', '12 min', '3 hr']):
        assert card_age(r, i, age), (i, age, 'age not drawn on its card')
    tap(r.s, *r.control('next'))
    r.s.run_for(0.6)
    assert ui(r.s)['work_ages'] == ['Yesterday', '3 days'], ui(r.s)
    assert card_age(r, 0, 'Yesterday') and card_age(r, 1, '3 days')


def test_yesterday_is_the_local_calendar_day(rig):
    r = rig()
    # 3 hr 30 min ago is 07:16 today; 11 hr ago is 23:46 the previous local day.
    job(r, 'late', 'Dishwasher started.', T0 - 11 * 3600)
    job(r, 'early', 'Coffee ordered.', T0 - 3 * 3600 - 1800)
    to_recent(r)
    assert ui(r.s)['work_ages'] == ['3 hr', 'Yesterday'], ui(r.s)


def test_ages_follow_the_device_clock(rig):
    host = Clock()
    r = rig(host)
    job(r, 'one', 'Lamp is on.', T0 - 12 * 60 - 55)
    to_recent(r)
    assert ui(r.s)['work_ages'] == ['12 min']
    # The device's own clock: 10 s later the card reads 13 min (below the heartbeat timeout).
    advance(r, 10)
    r.s.run_for(0.3)
    assert ui(r.s)['work_ages'] == ['13 min'], ui(r.s)
    assert card_age(r, 0, '13 min'), 'the drawn age did not move with the clock'
    # A host resync (heartbeat ping) moves it as well.
    # updated_at is T0-775; the host now says T0+600, so the age is 1375 s: "22 min".
    host.unix += 10 * 60
    assert r.s.wait_for(lambda: ui(r.s)['work_ages'] == ['22 min'], timeout=12), ui(r.s)['work_ages']


def test_no_age_without_a_trusted_host_time(rig):
    r = rig(NO_TIME)
    job(r, 'one', 'Lamp is on.', T0 - 12 * 60)
    to_recent(r)
    assert ui(r.s)['work_ages'] == [''], ui(r.s)
    for age in ('Just now', '12 min', '0 min'):
        assert not card_age(r, 0, age)


def test_last_task_opens_its_own_result_in_one_tap(rig):
    r = rig()
    job(r, 'older', 'Older answer.', T0 - 600)
    job(r, 'latest', 'Lamp is on.', T0 - 30)
    home(r)
    assert ui(r.s)['title'] == 'Last task: Finished'
    c = ui(r.s)['controls']
    assert 'last_task' in c, c
    assert inside_circle(c['last_task']) and c['last_task'][3] >= 44, c['last_task']
    assert all(not overlap(c['last_task'], v) for k, v in c.items() if k != 'last_task')
    assert find_text(r.s, 'Last task: Finished', 24, DIM, 0, HOME_TITLE), 'title text changed'
    m = r.mark()
    tap(r.s, *r.control('last_task'))
    r.s.run_for(0.6)
    assert ui(r.s)['view'] == 'result', ui(r.s)
    assert find_text(r.s, 'Lamp is on.', 24, TEXT, 0), 'not the latest job\'s result'
    assert not (r.sent_types(m) & REQUESTS)
    assert not r.brain.calls
    swipe(r.s, dx=100)
    assert ui(r.s)['view'] == 'recent'


def test_last_task_follows_an_unknown_ending_too(rig):
    r = rig()
    job(r, 'bad', 'Partial draft.', T0 - 30, outcome='failure')
    home(r)
    assert ui(r.s)['title'] == 'Last task: Error'
    tap(r.s, *r.control('last_task'))
    r.s.run_for(0.6)
    assert ui(r.s)['view'] == 'result'
    assert find_text(r.s, 'Partial draft.', 24, TEXT, 0)


def test_title_hold_still_opens_settings_and_never_the_result(rig):
    r = rig()
    job(r, 'one', 'Lamp is on.', T0 - 30)
    home(r)
    x, y, w, h = ui(r.s)['controls']['last_task']
    r.s.touch(True, x + w // 2, y + h // 2)
    r.s.step()
    assert ui(r.s)['pressed'] == 'last_task', 'no press feedback on the title'
    r.s.run_for(1.2)
    r.s.touch(False)
    r.s.step()
    r.s.run_for(0.2)
    assert r.s.device.screen() == 'settings', r.s.status()['screen']
    assert ui(r.s)['view'] != 'result'


def test_no_target_without_a_matching_record_and_a_stale_contact_does_nothing(rig):
    r = rig()
    job(r, 'one', 'Lamp is on.', T0 - 30)
    home(r)
    x, y, w, h = ui(r.s)['controls']['last_task']
    # Finger down, then the record disappears under it: the lift opens nothing.
    r.s.touch(True, x + w // 2, y + h // 2)
    r.s.step()
    r.hub.work.clear(r.device_id)
    r.run(r.session.work_snapshot())
    assert r.s.wait_for(lambda: 'last_task' not in ui(r.s)['controls'], timeout=5)
    r.s.touch(False)
    r.s.step()
    r.s.run_for(0.2)
    assert ui(r.s)['view'] == 'home'
    # The title still says how the last task ended; it is just not a route any more.
    assert ui(r.s)['title'] == 'Last task: Finished'
    tap(r.s, x + w // 2, y + h // 2)
    assert ui(r.s)['view'] == 'home'
