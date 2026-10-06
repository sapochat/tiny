"""Real native RGB565 renderer + loopback DeviceHub; no external providers."""
import hashlib
import json
import os
import struct
from pathlib import Path

from test_touch_navigation import rig, ui, swipe, tap, control

OUT = Path(os.environ.get('AMOLED_ARTIFACTS', 'artifacts/amoled/green'))


def capture(s, name):
    OUT.mkdir(parents=True, exist_ok=True)
    raw = s.device.framebuffer_rows()
    s.screenshot(OUT / f'{name}.png')
    (OUT / f'{name}.json').write_text(json.dumps({
        'ui': s.status().get('ui', {}), 'sent': s.sent, 'received': s.received,
        'raw_rgb565_sha256': hashlib.sha256(raw).hexdigest(),
        'rgb888_sha256': hashlib.sha256(s.rgb888()).hexdigest(),
        'fixture': 'literal protocol events; simulator microphone, not physical audio',
    }, indent=2))
    return list(struct.unpack('<' + 'H' * (len(raw)//2), raw))


def safe_circle(px):
    # Inspect UNMASKED production framebuffer, not the simulator's circular crop.
    outside = [px[y*466+x] for y in range(466) for x in range(466)
               if (x-233)**2 + (y-233)**2 >= 232**2]
    assert not any(outside), 'lit content outside the physical circular face'


def peripheral(px):
    return sum(px[y*466+x] != 0 for y in range(466) for x in range(466)
               if x < 68 or x >= 397 or y < 68 or y >= 397)


def safe_target(s, name, min_h):
    r = ui(s)['controls'][name]
    x,y,w,h = r
    assert h >= min_h
    for xx in (x, x+w-1):
        for yy in (y, y+h-1):
            assert (xx-233)**2 + (yy-233)**2 < 228**2
    return control(s, name)


def test_round_companion_states_and_readable_response(rig):
    s = rig
    px = capture(s, 'idle')
    assert px[233*466+20] == 0, 'AMOLED background must be actual zero'
    safe_circle(px)
    assert sum(px[y*466+x] != 0 for y in range(466) for x in range(466)
               if (x-233)**2+(y-233)**2 > 215**2) < 100, 'idle must not retain an active perimeter'
    s.press('talk')
    assert s.wait_screen('listening')
    px = capture(s, 'listening')
    safe_circle(px)
    assert peripheral(px) > 100
    s.tap('cancel')
    s.send_fixture('turn.start', turn='amoled')
    px = capture(s, 'thinking')
    safe_circle(px)
    assert peripheral(px) > 100
    s.send_fixture('reply.delta', text='Your next meeting is at noon. Leave ten minutes to walk there.\nBring your notebook.')
    capture(s, 'response')
    # Larger text cells than the old 12px; protocol's advertised columns agree.
    hello = next(m for m in s.sent if m['type'] == 'hello')
    assert hello['caps']['display']['text_cols'] < 26
    swipe(s, dx=100)
    s.send_fixture('audio.start', stream=7, rate=16000, format='pcm16')
    px = capture(s, 'speaking')
    safe_circle(px)
    assert peripheral(px) > 100
    s.send_fixture('audio.end', stream=7)
    s.send_fixture('reply', text='Your next meeting is at noon. Leave ten minutes to walk there.\nBring your notebook.\nConfirmed.')
    s.send_fixture('turn.end', turn='amoled', outcome='success')
    px = capture(s, 'unread')
    safe_circle(px)
    assert peripheral(px) > 20
    x,y = safe_target(s, 'reply', 55)
    before = len(s.sent)
    tap(s,x,y)
    assert ui(s)['view'] == 'response'
    assert not any(m['type'] in ('audio.start','cancel','session.new') for m in s.sent[before:])


def test_round_controls_and_approval_geometry(rig):
    s = rig
    swipe(s, dy=100)
    px = capture(s, 'controls')
    safe_circle(px)
    for name in ('volume','brightness'):
        x,y = safe_target(s,name,100)
        assert ui(s)['controls'][name][2] >= 60
        old = s.console('get '+name)
        swipe(s,dy=-70,x=x,y=y)
        assert s.console('get '+name) != old
    safe_target(s,'stop',48)
    swipe(s,dx=100)
    s.send_fixture('prompt', id='permission', title='Permission', text='Allow Hermes to turn on the desk lamp?')
    s.run_for(.6)
    px = capture(s, 'approval')
    safe_circle(px)
    safe_target(s,'yes',64)
    x,y = safe_target(s,'no',64)
    tap(s,x,y)
    assert any(m['type']=='prompt.reply' and m['answer']=='no' for m in s.sent)


def test_rectangular_baseline_is_unchanged(devserver, make_sim):
    hub, _, url = devserver()
    s = make_sim(url, board='sim-320x240')
    assert s.wait_screen('ready')
    capture(s, 'rectangular-idle')
    hello = next(m for m in s.sent if m['type']=='hello')
    assert hello['caps']['display']['text_cols'] == 25
    assert len(s.rgb888()) == 320*240*3
    s.press('talk')
    assert s.wait_screen('listening')
    capture(s, 'rectangular-listening')
    s.tap('cancel')
