"""Touch workflows through production hub, native core and framebuffer; no providers.
Rerun: .venv/bin/pytest tests/test_touch_navigation.py --junitxml=artifacts/swipes/results.xml -v
Inputs are literal protocol fixtures below. UI geometry is read from the same
rendered controls used for hit testing, then verified against framebuffer pixels.
"""
import hashlib
import json
import os
from pathlib import Path

import pytest

LONG = '\n'.join(f'Line {i:02d}: reading position' for i in range(60))
OUT = Path(os.environ.get('SWIPE_ARTIFACTS', 'artifacts/swipes/green'))


@pytest.fixture
def rig(devserver, make_sim, loop_thread, request):
    hub, _, url = devserver()
    sim = make_sim(url, board='sim-466x466-round')
    assert sim.wait_screen('ready')
    session = next(iter(hub.sessions.values()))
    def send(kind, **data):
        n = len(sim.received)
        loop_thread.run(session.send_json({'type': kind, **data}))
        assert sim.wait_for(lambda: len(sim.received) > n)
        sim.step()
    sim.send_fixture = send
    yield sim
    OUT.mkdir(parents=True, exist_ok=True)
    name = request.node.name.replace('/', '_')
    sim.screenshot(OUT / (name + '.png'))
    (OUT / (name + '.json')).write_text(json.dumps({
        'status': sim.status(), 'sent': sim.sent, 'received': sim.received,
        'framebuffer_sha256': hashlib.sha256(sim.rgb888()).hexdigest(),
    }, indent=2))


def swipe(s, dx=0, dy=0, x=233, y=220):
    s.touch(True, x, y)
    s.touch(True, x + dx // 3, y + dy // 3)
    s.touch(True, x + dx, y + dy)
    s.touch(False, -999, -999)  # release coordinates from controllers are undefined
    s.step()


def tap(s, x, y):
    s.touch(True, x, y)
    s.touch(False)
    s.step()


def ui(s):
    return s.status()['ui']


def response(s):
    s.send_fixture('turn.start', turn='fixture')
    s.send_fixture('reply.delta', text=LONG)


def control(s, name):
    r = ui(s)['controls'][name]
    x, y, w, h = r
    # A real rendered rectangular control, not a disconnected enum/hit zone.
    rgb = s.rgb888()
    pixels = {rgb[(yy * 466 + xx)*3:(yy * 466 + xx)*3+3]
              for yy in range(y, y+h) for xx in range(x, x+w)}
    assert len(pixels) >= 2, (name, 'control is blank')
    OUT.mkdir(parents=True, exist_ok=True)
    s.screenshot(OUT / (name + '-rendered.png'))
    return x+w//2, y+h//2


@pytest.mark.parametrize('activity', ['idle', 'thinking', 'streaming', 'speaking'])
def test_home_controls_preserve_activity(rig, activity):
    s = rig
    if activity != 'idle':
        s.send_fixture('turn.start', turn='fixture')
    if activity in ('streaming', 'speaking'):
        s.send_fixture('reply.delta', text=LONG)
        if activity == 'speaking':
            s.send_fixture('audio.start', stream=7, rate=16000, format='pcm16')
        swipe(s, dx=100)
    before = len(s.sent)
    swipe(s, dy=100)
    assert s.device.screen() == 'settings', 'down opens quick controls, never Cancel'
    assert ui(s)['view'] == 'controls'
    assert ui(s)['activity'] == activity
    volume = control(s, 'volume')
    brightness = control(s, 'brightness')
    v = s.console('get volume')
    swipe(s, dy=-70, x=volume[0], y=volume[1])
    assert s.console('get volume') != v
    b = s.console('get brightness')
    swipe(s, dy=70, x=brightness[0], y=brightness[1])
    assert s.console('get brightness') != b
    settings = (s.console('get volume'), s.console('get brightness'))
    swipe(s, dx=-100)
    assert ui(s)['view'] == 'controls'
    assert settings == (s.console('get volume'), s.console('get brightness'))
    swipe(s, dy=100, x=230, y=140)  # outside either slider
    assert ui(s)['view'] == 'controls'
    assert not any(m['type'] in ('cancel', 'session.new', 'audio.cancel') for m in s.sent[before:])
    swipe(s, dx=100)
    assert ui(s)['view'] == 'home'
    assert ui(s)['activity'] == activity
    if activity == 'thinking':
        assert ui(s)['headline'] == 'Thinking'
    if activity == 'speaking':
        assert ui(s)['speaking'] is True


def test_response_scroll_bounds_return_and_stream_follow(rig):
    s = rig
    response(s)
    before = s.rgb888(155, 330)
    swipe(s, dy=100)
    assert ui(s)['view'] == 'response'
    held = ui(s)['scroll']
    assert held >= 0
    assert s.rgb888(155, 330) != before
    s.send_fixture('reply.delta', text=LONG+'\nNEW TAIL')
    assert ui(s)['scroll'] == held
    swipe(s, dx=100)
    assert ui(s)['view'] == 'home'
    swipe(s, dy=-100)
    assert ui(s)['view'] == 'response'
    assert ui(s)['scroll'] == held
    for _ in range(30): swipe(s, dy=100)
    assert ui(s)['scroll'] == 0
    swipe(s, dy=100)
    assert ui(s)['view'] == 'response'
    for _ in range(30): swipe(s, dy=-100)
    assert ui(s)['scroll'] == -1
    s.send_fixture('reply.delta', text=LONG+'\nANOTHER TAIL')
    assert ui(s)['scroll'] == -1
    swipe(s, dy=-100)
    assert ui(s)['view'] == 'response'


@pytest.mark.parametrize('dx,dy', [(100, 100), (100, 0), (-100, 0), (14, 12)])
def test_home_ambiguous_horizontal_and_jitter_never_cancel(rig, dx, dy):
    s = rig
    s.send_fixture('turn.start', turn='fixture')
    before = len(s.sent)
    swipe(s, dx=dx, dy=dy)
    assert ui(s)['view'] == 'home'
    assert ui(s)['activity'] == 'thinking'
    assert not any(m['type'] in ('cancel', 'session.new', 'audio.start') for m in s.sent[before:])


def test_gesture_belongs_to_starting_home_when_reply_arrives(rig):
    s = rig
    s.send_fixture('turn.start', turn='fixture')
    s.touch(True, 233, 200)
    s.touch(True, 233, 225)  # movement disarms hold
    s.send_fixture('reply.delta', text=LONG)
    s.touch(True, 233, 300)
    s.touch(False)
    assert ui(s)['view'] == 'controls'
    assert ui(s)['activity'] == 'streaming'


def test_approval_requires_rendered_button_and_scrolls(rig):
    s = rig
    s.send_fixture('prompt', id='p1', text=LONG, title='Permission')
    s.run_for(0.6)
    before = len(s.sent)
    first = s.rgb888(155, 300)
    swipe(s, dy=-100)
    assert s.rgb888(155, 300) != first
    swipe(s, dx=100)
    swipe(s, dx=-100)
    swipe(s, dy=100)
    tap(s, 233, 200)
    x, y = control(s, 'yes')
    s.touch(True, x, y)
    s.touch(True, 600, 600)
    s.touch(False)
    assert ui(s)['view'] == 'approval'
    assert not any(m['type'] == 'prompt.reply' for m in s.sent[before:])
    x, y = control(s, 'no')
    tap(s, x, y)
    assert any(m['type'] == 'prompt.reply' and m['id'] == 'p1' and m['answer'] == 'no' for m in s.sent)


def test_prompt_replacement_and_arrival_midgesture_do_not_decide(rig):
    s = rig
    s.touch(True, 233, 220)
    s.send_fixture('prompt', id='p1', text='First')
    s.run_for(0.6)
    s.touch(False)
    assert not any(m['type'] == 'prompt.reply' for m in s.sent)
    x,y = control(s, 'yes')
    s.touch(True, x,y)
    s.send_fixture('prompt', id='p2', text='Replacement')
    s.run_for(0.6)
    s.touch(False)
    assert not any(m['type'] == 'prompt.reply' for m in s.sent)
    tap(s, x,y)
    assert any(m['type'] == 'prompt.reply' and m['id'] == 'p2' and m['answer'] == 'yes' for m in s.sent)


def test_recording_navigation_is_suppressed_and_explicit_stop_survives(rig):
    s = rig
    s.press('talk')
    assert s.wait_screen('listening')
    before = len(s.sent)
    for dx,dy in [(0,100),(0,-100),(100,0),(-100,0)]: swipe(s,dx,dy)
    assert s.device.screen() == 'listening'
    assert not any(m['type'] in ('audio.end','audio.cancel','cancel','session.new') for m in s.sent[before:])
    s.tap('cancel')
    assert any(m['type'] == 'audio.cancel' for m in s.sent[before:])


def test_controls_explicit_stop_and_release_outside(rig):
    s = rig
    s.send_fixture('turn.start', turn='fixture')
    swipe(s, dy=100)
    x,y = control(s, 'stop')
    s.touch(True,x,y)
    s.touch(True,600,600)
    s.touch(False)
    assert not any(m['type'] == 'cancel' for m in s.sent)
    tap(s,x,y)
    assert any(m['type'] == 'cancel' for m in s.sent)
    assert not any(m['type'] == 'session.new' for m in s.sent)


def test_legacy_settings_still_operate_locally(rig):
    s = rig
    s.console('settings')
    old = s.console('get volume')
    tap(s, 233, 200)
    assert s.console('get volume') != old
    old = s.console('get brightness')
    swipe(s, dy=100)
    tap(s, 233, 200)
    assert s.console('get brightness') != old
    assert not any(m['type'] == 'audio.start' for m in s.sent)


def test_recording_started_midgesture_does_not_get_released(rig):
    s = rig
    s.touch(True, 233, 220)
    s.press('talk')
    s.touch(True, 233, 320)
    s.touch(False)
    assert s.device.screen() == 'listening'
    assert not any(m['type'] in ('audio.end', 'audio.cancel') for m in s.sent)
    s.tap('cancel')


def test_response_position_survives_final_and_idle_time(rig):
    s = rig
    response(s)
    swipe(s, dy=100)
    pos = ui(s)['scroll']
    s.send_fixture('reply', text=LONG)
    s.send_fixture('turn.end', turn='fixture', outcome='success')
    s.run_for(4)
    assert ui(s)['scroll'] == pos
    swipe(s, dx=-100)
    assert ui(s)['view'] == 'response'
    assert ui(s)['scroll'] == pos


def test_new_turn_cannot_receive_old_stop_contact(rig):
    s = rig
    s.send_fixture('turn.start', turn='old')
    swipe(s, dy=100)
    x,y = control(s, 'stop')
    s.touch(True,x,y)
    s.send_fixture('turn.start', turn='new')
    s.touch(False)
    assert not any(m['type'] == 'cancel' for m in s.sent)


def test_audio_flows_while_navigating_and_approval_is_explicit(rig, loop_thread):
    import struct
    import wave
    from hermes_gadget_plugin.protocol import binary as pack_binary, CHANNEL_AUDIO as CH_AUDIO
    s = rig
    response(s)
    s.send_fixture('audio.start', stream=7, rate=16000, format='pcm16')
    pcm = struct.pack('<h', 1200) * 16000
    # Feed binary through the native transport boundary; PCM is an explicit local fixture.
    s.device.transport_binary(pack_binary(CH_AUDIO, 7, 0, pcm))
    swipe(s, dy=100)
    swipe(s, dx=100)
    swipe(s, dy=100)
    assert ui(s)['speaking']
    s.send_fixture('prompt', id='audio-prompt', text=LONG)
    s.run_for(0.6)
    for dx,dy in [(0,100),(0,-100),(100,0),(-100,0)]: swipe(s,dx,dy)
    assert ui(s)['speaking']
    assert not any(m['type'] in ('cancel','prompt.reply') for m in s.sent)
    s.send_fixture('audio.end', stream=7)
    assert s.speaker.last_file
    with wave.open(str(s.speaker.last_file), 'rb') as f:
        assert f.readframes(16000) == pcm


def test_thinking_can_read_last_reply_without_losing_activity(rig):
    s = rig
    response(s)
    s.send_fixture('reply', text=LONG)
    s.send_fixture('turn.end', turn='fixture', outcome='success')
    swipe(s, dy=100)
    pos = ui(s)['scroll']
    swipe(s, dx=100)
    s.send_fixture('turn.start', turn='next')
    swipe(s, dy=-100)
    assert ui(s)['view'] == 'response'
    assert ui(s)['activity'] == 'thinking'
    assert ui(s)['headline'] == 'Thinking'
    assert ui(s)['scroll'] == pos
    s.send_fixture('reply.delta', text='New answer')
    assert ui(s)['scroll'] == -1


def test_home_hints_never_describe_swipe_as_cancel(rig):
    s = rig
    s.send_fixture('turn.start', turn='fixture')
    assert 'Controls' in ui(s)['hint']
    s.press('talk')
    assert ui(s)['hint'] == 'Recording - no navigation'
    s.tap('cancel')


def test_legacy_overlay_can_close_without_cancelling_work(rig):
    s = rig
    s.send_fixture('turn.start', turn='fixture')
    s.send_fixture('display', title='Notice', body=LONG, ttl_s=0)
    assert s.device.screen() == 'card'
    assert s.wait_for(lambda: ui(s)['scroll'] > 0, timeout=20), 'legacy long cards must still page'
    swipe(s, dy=100)
    assert s.device.screen() == 'thinking'
    assert not any(m['type'] == 'cancel' for m in s.sent)
