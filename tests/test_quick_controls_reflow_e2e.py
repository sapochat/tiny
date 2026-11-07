"""R-08 quick controls reflow on the round companion: real native core, production loopback hub.

Four bands: two sliders, **Mute voice | Stop task** (>= 64 px), **New chat | Recent**
(>= 64 px), then **Settings** as one wide pill. Each slider is draggable along its whole
track (the value follows the finger), draws the same handle on both tracks at every value,
and shows its value inside the track. Failure modes covered:
- action targets shorter than 64 px, outside the circle, overlapping, or sharing a row with
  something other than their pair;
- a slider that only nudges by a fixed step instead of following the finger;
- a handle that disappears at some values or differs between the two sliders;
- a value printed outside its track or cut by the handle;
- a drag that writes settings storage on every sample (flash wear) instead of once;
- a horizontal swipe that starts on a slider changing the value instead of going Home;
- a press that slides off a target and still acts;
- rectangular touch boards changing geometry or slider behaviour.
"""
from __future__ import annotations

import numpy as np
import pytest

from conftest import LoopThread, requires_sim
from test_device_time_e2e import Clock, close, make
from test_interaction_surface_e2e import (AMBER, DIM, SURFACE, TEXT, Rig, _brain_class, _instrument, find_text,
                                          framebuffer, inside_circle, overlap, rgb)
from test_touch_navigation import swipe, tap, ui

pytestmark = requires_sim

INK = rgb(23, 19, 13)
REQUESTS = {'text', 'audio.start', 'audio.end', 'audio.cancel', 'cancel', 'session.new', 'prompt.reply'}
LABELS = {'silence': 'Mute voice', 'stop': 'Stop task', 'new_chat': 'New chat', 'recent': 'Recent',
          'settings': 'Settings'}


@pytest.fixture
def rig(tmp_path):
    made = []

    def _make():
        r = make(tmp_path / f'r{len(made)}', Clock())
        made.append(r)
        r.writes = []
        original = r.s.storage_set

        def counted(key, value):
            r.writes.append((key, value))
            return original(key, value)
        r.s.storage_set = counted
        r.s.run_for(0.4)
        return r
    yield _make
    for r in made:
        close(r)


def to_controls(r):
    s = r.s
    # A shelf-capable host offers Recent once it has sent its first work snapshot.
    r.turn_start('one', request='req-one')
    r.reply('Lamp is on.', turn='one')
    r.turn_end('one', 'success')
    assert s.wait_for(lambda: not s.status()['work']['active'], timeout=5)
    s.run_for(0.3)
    if ui(s)['view'] != 'home':
        swipe(s, dx=100)
    swipe(s, dy=100)
    s.run_for(0.3)
    assert ui(s)['view'] == 'controls', ui(s)
    assert 'recent' in ui(s)['controls'], 'host did not offer the shelf'


def rect(r, name):
    return tuple(ui(r.s)['controls'][name])


def drag(s, x, ys):
    """One contact: down at ys[0], then each sample in turn; returns live values seen."""
    s.touch(True, x, ys[0])
    s.step()
    seen = []
    for y in ys[1:]:
        s.touch(True, x, y)
        s.step()
        seen.append(s.status()['ui'])
    s.touch(False, -999, -999)
    s.step()
    s.run_for(0.1)
    return seen


def value(r, name):
    """The saved setting (what survives a restart); unset reads as the firmware default."""
    import json
    saved = json.loads(r.s.console(f'get {name}').split(' ', 1)[1])['value']
    return int(saved) if saved else {'volume': 70, 'brightness': 100}[name]


def labelled(r, name, label, c):
    """A 24px label: light on a filled pill when available, dim on black when inert."""
    box = tuple(c[name])
    return find_text(r.s, label, 24, TEXT, SURFACE, box) or find_text(r.s, label, 24, DIM, 0, box)


def handle_rows(r, name):
    """Rows inside the track carrying a long run of the light handle colour."""
    x, y, w, h = rect(r, name)
    f = framebuffer(r.s)[y:y + h, x:x + w]
    rows = []
    for i, row in enumerate(f):
        run = best = 0
        for px in row:
            run = run + 1 if px == TEXT else 0
            best = max(best, run)
        if best >= 36:
            rows.append(y + i)
    return rows


def test_four_bands_with_tall_paired_targets(rig):
    r = rig()
    to_controls(r)
    # Stop is a target only while work is open: check it there, then the idle bands.
    r.turn_start('two', request='req-two')
    r.s.run_for(0.3)
    busy = ui(r.s)['controls']
    assert labelled(r, 'stop', 'Stop task', busy), 'Stop task not a 24px label'
    r.turn_end('two', 'success')
    assert r.s.wait_for(lambda: not r.s.status()['work']['active'], timeout=5)
    r.s.run_for(0.3)
    c = dict(ui(r.s)['controls'], stop=busy['stop'])
    for name, label in LABELS.items():
        assert name in c, (name, c)
        assert inside_circle(c[name]), (name, c[name])
        if name != 'stop':
            assert labelled(r, name, label, c), (name, label, 'not a 24px label')
    for a, b in (('silence', 'stop'), ('new_chat', 'recent')):
        assert c[a][1] == c[b][1] and c[a][3] == c[b][3] >= 64, (a, b, c[a], c[b])
        assert c[a][0] + c[a][2] <= c[b][0], (a, b, 'pair order or overlap')
    assert c['silence'][1] + c['silence'][3] <= c['new_chat'][1], 'Mute/Stop band above New chat/Recent'
    assert c['new_chat'][1] + c['new_chat'][3] <= c['settings'][1], 'Settings is its own band, last'
    assert c['settings'][2] >= 160 and c['settings'][3] >= 48, c['settings']
    tracks_bottom = max(c['volume'][1] + c['volume'][3], c['brightness'][1] + c['brightness'][3])
    assert tracks_bottom <= c['silence'][1], 'sliders are the first band'
    names = [n for n in c if n != 'home']
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            assert not overlap(c[a], c[b]), (a, b)


def test_slider_follows_the_finger_along_the_whole_track(rig):
    r = rig()
    to_controls(r)
    x, y, w, h = rect(r, 'volume')
    cx = x + w // 2
    m = r.mark()
    writes = len(r.writes)
    # Grab near the top, drag to below the track: the value follows down to 0.
    seen = drag(r.s, cx, [y + 6, y + 30, y + h // 2, y + h - 20, y + h + 40])
    assert all(u['view'] == 'controls' for u in seen)
    assert value(r, 'volume') == 0
    # Grab at the bottom, drag up past the top: 100.
    drag(r.s, cx, [y + h - 4, y + h - 30, y + h // 2, y + 20, y - 40])
    assert value(r, 'volume') == 100
    # Storage is written once per drag (on release), not on every sample.
    vol_writes = [k for k, _ in r.writes[writes:] if k == 'volume']
    assert len(vol_writes) == 2, r.writes[writes:]
    assert not (r.sent_types(m) & REQUESTS)


def test_the_value_tracks_the_finger_live_before_release(rig):
    r = rig()
    to_controls(r)
    x, y, w, h = rect(r, 'brightness')
    cx = x + w // 2
    r.s.touch(True, cx, y + 8)
    r.s.step()
    seen = []
    for yy in (y + 30, y + h // 2, y + h - 12):
        r.s.touch(True, cx, yy)
        r.s.step()
        seen.append(r.s.peripherals.backlight)
    assert seen == sorted(seen, reverse=True) and seen[0] > seen[-1], seen
    assert len(set(seen)) == 3, 'value moved in fixed steps, not with the finger'
    r.s.touch(False, -999, -999)
    r.s.step()
    assert value(r, 'brightness') == r.s.peripherals.backlight


@pytest.mark.parametrize('level', [0, 10, 50, 66, 67, 90, 100])
def test_same_handle_and_an_inside_value_on_both_sliders_at_every_value(rig, level):
    r = rig()
    assert r.s.console(f'set volume {level}').startswith('@ok')
    assert r.s.console(f'set brightness {max(level, 10)}').startswith('@ok')
    to_controls(r)
    shapes = []
    for name, v in (('volume', level), ('brightness', max(level, 10))):
        rows = handle_rows(r, name)
        assert 4 <= len(rows) <= 6, (name, v, rows, 'handle missing or malformed')
        x, y, w, h = rect(r, name)
        shapes.append((len(rows), rows[0] - y - (h - 16) * (100 - v) // 100))
        label = f'{v}%'
        found = find_text(r.s, label, 24, TEXT, SURFACE, (x, y, w, h)) or find_text(r.s, label, 24, INK, AMBER, (x, y, w, h))
        assert found, (name, label, 'value not inside its track')
        lx, ly = found
        assert not set(range(ly, ly + 18)) & set(rows), (name, 'handle cuts the value')
    if level >= 10:
        assert shapes[0] == shapes[1], ('handles differ', shapes)


def test_horizontal_swipe_from_a_slider_goes_home_and_a_tap_changes_nothing(rig):
    r = rig()
    to_controls(r)
    x, y, w, h = rect(r, 'volume')
    before = value(r, 'volume')
    tap(r.s, x + w // 2, y + 10)
    assert value(r, 'volume') == before and ui(r.s)['view'] == 'controls'
    swipe(r.s, dx=100, x=x + 10, y=y + h // 2)
    assert ui(r.s)['view'] == 'home'
    assert value(r, 'volume') == before


def test_press_lights_and_slide_off_release_does_nothing(rig):
    r = rig()
    to_controls(r)
    m = r.mark()
    for name in ('recent', 'settings', 'new_chat'):
        x, y, w, h = rect(r, name)
        r.s.touch(True, x + w // 2, y + h // 2)
        r.s.step()
        assert ui(r.s)['pressed'] == name
        r.s.touch(True, x + w // 2 + 25, y + h // 2 - 25)
        r.s.step()
        assert ui(r.s)['pressed'] == 'none'
        r.s.touch(False, -999, -999)
        r.s.step()
        assert ui(r.s)['view'] == 'controls' and r.s.device.screen() == 'settings'
    tap(r.s, *[v + d // 2 for v, d in zip(rect(r, 'recent')[:2], rect(r, 'recent')[2:])])
    assert ui(r.s)['view'] == 'recent'
    assert not (r.sent_types(m) & REQUESTS)


def test_rectangular_touch_board_keeps_its_controls(tmp_path, monkeypatch):
    from hermes_gadget.sim import Simulator, runner
    from hermes_gadget_plugin.hub import DeviceHub
    from hermes_gadget_plugin.store import DeviceStore
    monkeypatch.setitem(runner.BOARDS, 'sim-320x240-touch', runner.Board('sim-320x240-touch', 320, 240, touch=True))
    lt = LoopThread()
    brain = _brain_class()()
    hub = DeviceHub(DeviceStore(tmp_path / 'server'), brain, host='127.0.0.1', port=0, heartbeat_s=5)
    brain.hub = hub
    lt.run(hub.start())
    sim = Simulator(url=f'ws://127.0.0.1:{hub.bound_port}/gadget', name='Legacy', board='sim-320x240-touch',
                    state_dir=tmp_path / 'device')
    _instrument(Rig(sim, hub, brain, lt, tmp_path / 'out'), sim)
    try:
        sim.start()
        assert sim.wait_screen('ready', timeout=10)
        swipe(sim, dy=100, x=160, y=100)
        sim.run_for(0.3)
        assert ui(sim)['controls'] == {'volume': [56, 93, 48, 71], 'brightness': [216, 93, 48, 71],
                                       'stop': [80, 180, 160, 34]}
        # Relative swipe, as before: 70 px up from the middle raises volume by 17 from 70.
        swipe(sim, dy=-70, x=80, y=128)
        assert '"87"' in sim.console('get volume').replace(' ', ''), sim.console('get volume')
    finally:
        sim.close()
        lt.run(hub.stop())
        lt.stop()
