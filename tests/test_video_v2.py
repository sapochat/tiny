"""Video v2 acceptance through real native App + disposable loopback DeviceHub.
Rerun: HGSIM_LIBRARY=$PWD/build/video-v2/libhgsim.so .venv/bin/python -m pytest tests/test_video_v2.py -v --junitxml=artifacts/video-v2/results.xml
No providers, production state, OTA, or hardware. Source motion replaces the old
static-outline contract; touch/approval semantics remain independently tested.
"""
import hashlib
import json
import os
import platform
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image
import pytest
from test_touch_navigation import rig, swipe, ui, tap, control

OUT = Path(os.environ.get('VIDEO_ARTIFACTS', 'artifacts/video-v2/green'))
SOURCES = Path(__file__).resolve().parents[2] / 'tiny-animations/picks/states-v2'


def freeze(s):
    t = [s.now_ms()]
    s.now_ms = lambda: t[0]
    ticks = [0]
    def advance(n=1):
        for _ in range(n):
            t[0] += 100
            ticks[0] += 1
            # The hub uses wall time; keep its real transport alive on the
            # accelerated native clock without inventing a new protocol.
            if ticks[0] % 50 == 0 and s.network_up and s.status()['phase'] == 'online':
                s.send_fixture('ping', ts=t[0])
            s.step()
    return advance


def face(s):
    return np.frombuffer(s.rgb888(), dtype=np.uint8).reshape(466,466,3)[96:288,137:329].copy()


@pytest.fixture
def evidence(rig, request):
    s = rig
    frames, checks = [], []
    advance = freeze(s)
    def capture(label, ticks=1):
        advance(ticks)
        frames.append(Image.frombytes('RGB', (466,466), s.rgb888()))
        checks.append({'label': label, 'ui': ui(s), 'face_sha256': hashlib.sha256(face(s).tobytes()).hexdigest()})
        return face(s)
    yield s, advance, capture, checks
    OUT.mkdir(parents=True, exist_ok=True)
    name = request.node.name
    if frames:
        frames[0].save(OUT/f'{name}.gif', save_all=True, append_images=frames[1:], duration=100, loop=0)
    (OUT/f'{name}.json').write_text(json.dumps({'python':platform.python_version(), 'numpy':np.__version__, 'pillow':Image.__version__, 'library':os.environ.get('HGSIM_LIBRARY'), 'rerun':__doc__.splitlines()[1], 'checks':checks, 'sent':s.sent, 'received':s.received, 'source_files':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(SOURCES.glob('*.mp4'))}},indent=2))


def test_video_source_motion_and_routing(evidence):
    s, advance, capture, checks = evidence
    # Sustained idle motion is genuinely sourced from video, not a static patch.
    idle = [capture('idle') for _ in range(60)]
    support = np.zeros((192,192), bool)
    support[72:105,34:94] = True
    support[111:130,41:64] = True
    assert any(np.any(f[~support] != idle[0][~support]) for f in idle[1:]), 'v2 video must animate outside the obsolete facial patch'
    s.press('talk')
    listen = [capture('listening') for _ in range(55)]
    assert len({f.tobytes() for f in listen}) > 8
    animation = ui(s)['animation']
    assert animation['clip'] == 'listening'
    # Independent decode of approved source, not the generated C++ asset.
    raw = subprocess.check_output(['ffmpeg','-v','error','-threads','1','-i',str(SOURCES/'01-listening.mp4'),'-vf','scale=96:96:flags=lanczos,format=gray','-f','rawvideo','-'])
    source = np.frombuffer(raw,dtype=np.uint8).reshape(-1,96,96)
    indices = np.linspace(0,len(source)-1,25).round().astype(int)
    gray = ((source[indices[animation['frame']]].astype(np.uint16)+42)//85*85).clip(0,255).astype(np.uint8)
    gray = gray[np.arange(192)*96//192][:,np.arange(192)*96//192]
    # RGB565 framebuffer unpacked by the simulator uses bit replication.
    expected = np.stack([((gray>>3)<<3)|(gray>>5),((gray>>2)<<2)|(gray>>6),((gray>>3)<<3)|(gray>>5)],axis=-1)
    assert np.array_equal(face(s),expected), 'rendered pixels must match the selected approved MP4 frame'
    assert ui(s)['activity'] == 'recording'
    s.tap('cancel')
    s.send_fixture('turn.start',turn='video')
    thinking = [capture('thinking') for _ in range(65)]
    assert len({f.tobytes() for f in thinking}) > 8
    assert np.array_equal(thinking[-1],thinking[-2]), 'thinking holds its authored endpoint, never loops backwards'
    s.send_fixture('reply.delta', text='Video fixture answer')
    swipe(s,dx=100)
    s.send_fixture('audio.start',stream=9,rate=16000,format='pcm16')
    speech = [capture('speaking') for _ in range(65)]
    assert len({f.tobytes() for f in speech}) > 8, 'speaking must play the approved MP4, not a neutral still'
    s.send_fixture('audio.end',stream=9)
    s.send_fixture('reply',text='Video fixture complete')
    s.send_fixture('turn.end',turn='video',outcome='success')
    ready = [capture('reply-ready') for _ in range(65)]
    assert ui(s)['hint']=='Reply ready - tap to read'
    assert np.array_equal(ready[-1],ready[-2])
    assert not np.array_equal(ready[-1],thinking[-1])
    tap(s,233,390)
    assert ui(s)['view']=='response'
    swipe(s,dx=100)
    [capture('ready-settle') for _ in range(55)]
    # New live activity preempts decorative exits; it never waits five seconds.
    s.send_fixture('turn.start',turn='interrupt')
    s.press('talk')
    capture('interrupt-listening',2)
    assert ui(s)['activity']=='recording'
    s.tap('cancel')


def test_video_approval_sleep_wake(evidence):
    s, advance, capture, checks = evidence
    s.send_fixture('prompt',id='video-prompt',text='Allow the local fixture?',title='Permission')
    [capture('asking') for _ in range(55)]
    assert ui(s)['view']=='approval'
    assert not any(m['type']=='prompt.reply' for m in s.sent)
    tap(s,*control(s,'yes'))
    assert any(m['type']=='prompt.reply' and m['id']=='video-prompt' and m['answer']=='yes' for m in s.sent)
    [capture('asking-answered') for _ in range(55)]
    s.console('set screen_timeout 30')
    [capture('idle-to-sleep') for _ in range(240)]
    assert not s.status()['display_sleeping']
    [capture('sleep-dark') for _ in range(70)]
    assert s.status()['display_sleeping']
    before=len(s.sent)
    tap(s,233,220)
    capture('wake')
    assert not s.status()['display_sleeping']
    assert not any(m['type'] in ('audio.start','prompt.reply') for m in s.sent[before:])
    [capture('wake') for _ in range(55)]
    observed = {c['ui']['animation']['clip'] for c in checks}
    assert {'asking','asking-answered','fall-asleep','sleep','wake'} <= observed


def test_video_resolve_and_network_alert(evidence):
    s, advance, capture, checks = evidence
    s.send_fixture('turn.start',turn='resolve')
    [capture('thinking-hold') for _ in range(55)]
    s.send_fixture('reply.delta',text='Text-only fixture')
    swipe(s,dx=100)
    [capture('thinking-got-it') for _ in range(55)]
    assert 'thinking-got-it' in {c['ui']['animation']['clip'] for c in checks}
    s.tap('cancel')
    s.set_network(False)
    [capture('alert') for _ in range(55)]
    assert ui(s)['animation']['clip']=='alert'
    s.set_network(True)
    capture('alert-settle')
    assert ui(s)['animation']['clip']=='alert-settle'
    assert s.wait_screen('ready')
    [capture('alert-settle') for _ in range(10)]
    assert ui(s)['animation']['clip']=='alert-settle'
