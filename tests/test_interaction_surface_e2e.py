"""Interaction surface workflows (plan M0-M2) through production code, end to end.

Every workflow drives the production C++ App, Ui and TouchGestures through the
simulator library, connected over a real 127.0.0.1 WebSocket to the production
DeviceHub with a disposable DeviceStore. The hub delegate is the production
development EchoBrain, recording what the host was asked to do and replying only
when a test drives it. No Hermes, providers, external network, persistent state
or hardware is involved.

Observables, not model enums:
- device->host JSON and binary frames (wire receipts);
- simulator speaker/microphone HAL calls (what the core actually played, aborted
  or captured);
- hub delegate calls (whether a request was dispatched or cancelled);
- RGB565 framebuffer pixels, with safety-relevant copy compared against an
  independent raster of the source Geist TTF (``test_face_first_font.oracle``).

Evidence goes to IX_ARTIFACTS (default artifacts/interaction-v1/local): run.json
(environment, library and source hashes, exact command line), a copy of this
fixture file, and per-test snapshots, receipts, HAL logs and framebuffer hashes.
Rerun instructions: docs/development.md, "Interaction surface E2E".
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import platform
import struct
import subprocess
import sys
import time
from array import array
from pathlib import Path

import numpy as np
import pytest

from conftest import REPO, LoopThread, requires_sim
from test_face_first_font import oracle, rgb
from test_touch_navigation import LONG, swipe, tap, ui

pytestmark = requires_sim

OUT = Path(os.environ.get('IX_ARTIFACTS', 'artifacts/interaction-v1/local'))
TEXT, DIM, SURFACE, AMBER = rgb(240, 239, 235), rgb(164, 164, 169), rgb(32, 32, 35), rgb(212, 164, 92)
SAFE_R = 228                      # the existing safe_target corner radius
PORTRAIT = (137, 96, 192, 192)    # approved face position, compared with MP4 decodes elsewhere
HEADLINE = (0, 286, 466, 56)      # 30px headline band (y299, or y289 above an action row)
DETAIL = (0, 324, 466, 48)        # 17px detail band (y342, or y328 above an action row)
REQUESTS = {'text', 'audio.start', 'audio.end', 'audio.cancel', 'cancel', 'session.new', 'prompt.reply'}


def tone(seconds, rate=16000, freq=440.0, amp=6000):
    n = int(seconds * rate)
    return array('h', (int(amp * math.sin(2 * math.pi * freq * i / rate)) for i in range(n))).tobytes()


# -- host side: the production development delegate, recording ------------------------------

def _brain_class():
    from hermes_gadget.devserver import EchoBrain

    class RecordingBrain(EchoBrain):
        """EchoBrain that records host dispatch; it only replies when ``auto`` is set."""

        def __init__(self):
            super().__init__(word_delay=0.0)
            self.calls: list[dict] = []
            self.auto = False

        def count(self, call):
            return sum(c['call'] == call for c in self.calls)

        async def on_text(self, session, msg_id, text):
            self.calls.append({'call': 'text', 'id': msg_id, 'text': text})
            if self.auto:
                await super().on_text(session, msg_id, text)

        async def on_utterance(self, session, msg_id, wav, seconds):
            self.calls.append({'call': 'utterance', 'id': msg_id, 'wav_bytes': len(wav), 'seconds': round(seconds, 3)})
            if self.auto:
                await super().on_utterance(session, msg_id, wav, seconds)

        async def on_cancel(self, session):
            self.calls.append({'call': 'cancel'})
            if self.auto:
                await super().on_cancel(session)

        async def on_new_session(self, session):
            self.calls.append({'call': 'new_session'})

        async def on_prompt_reply(self, session, prompt_id, yes):
            self.calls.append({'call': 'prompt_reply', 'id': prompt_id, 'yes': yes})

    return RecordingBrain


# -- framebuffer oracle ------------------------------------------------------------------------

def framebuffer(s):
    return np.frombuffer(s.device.framebuffer_rows(), dtype='<u2').reshape(466, 466)


def _tight(label, size, fg, bg):
    _, px = oracle(label, size, fg, bg)
    o = np.array(px, dtype=np.uint16)
    rows = np.where((o != bg).any(axis=1))[0]
    cols = np.where((o != bg).any(axis=0))[0]
    return o[rows[0]:rows[-1] + 1, cols[0]:cols[-1] + 1]


def find_text(s, label, size, fg, bg=0, box=(0, 0, 466, 466)):
    """Exact position of an independent source-TTF raster inside ``box``, or None."""
    o = _tight(label, size, fg, bg)
    h, w = o.shape
    f = framebuffer(s)
    x0, y0, bw, bh = box
    x1, y1 = min(466, x0 + bw), min(466, y0 + bh)
    if x1 - x0 < w or y1 - y0 < h:
        return None
    py, px = (int(v) for v in np.argwhere(o != bg)[0])
    for y in range(y0, y1 - h + 1):
        row = f[y + py, x0 + px: x1 - w + 1 + px]
        for x in np.nonzero(row == o[py, px])[0] + x0:
            if np.array_equal(f[y:y + h, x:x + w], o):
                return int(x), int(y)
    return None


def inside_circle(rect, radius=SAFE_R):
    x, y, w, h = rect
    return all((xx - 233) ** 2 + (yy - 233) ** 2 < radius ** 2 for xx in (x, x + w - 1) for yy in (y, y + h - 1))


def overlap(a, b):
    return a[0] < b[0] + b[2] and b[0] < a[0] + a[2] and a[1] < b[1] + b[3] and b[1] < a[1] + a[3]


# -- rig ---------------------------------------------------------------------------------------

class Rig:
    def __init__(self, sim, hub, brain, lt, out):
        self.s, self.hub, self.brain, self.lt, self.out = sim, hub, brain, lt, out
        self.hal: list[dict] = []   # speaker/mic HAL calls made by the native core
        self.tx: list[dict] = []    # binary frames the device sent
        self.rx: list[dict] = []    # binary frames the device received
        self.snaps: list[str] = []
        self.device_id = ''

    # wire / HAL bookkeeping
    def mark(self):
        return {'sent': len(self.s.sent), 'hal': len(self.hal), 'tx': len(self.tx), 'rx': len(self.rx),
                'received': len(self.s.received)}

    def sent_since(self, mark, kind=None):
        msgs = self.s.sent[mark['sent']:]
        return [m for m in msgs if kind is None or m.get('type') == kind]

    def sent_types(self, mark):
        return {m.get('type') for m in self.s.sent[mark['sent']:]}

    def hal_since(self, mark, call):
        return [h for h in self.hal[mark['hal']:] if h['call'] == call]

    def hal_count(self, call):
        return sum(h['call'] == call for h in self.hal)

    def speaker_bytes(self, mark=None):
        start = mark['hal'] if mark else 0
        return sum(h.get('bytes', 0) for h in self.hal[start:] if h['call'] == 'speaker_write')

    def speaker_payload(self, mark):
        return b''.join(h['data'] for h in self.hal[mark['hal']:] if h['call'] == 'speaker_write')

    def rx_frames(self, mark, stream):
        return sum(1 for f in self.rx[mark['rx']:] if f['channel'] == 1 and f['stream'] == stream)

    def tx_audio_frames(self, mark):
        return sum(1 for f in self.tx[mark['tx']:] if f['channel'] == 1)

    # host side
    @property
    def session(self):
        assert self.s.wait_for(lambda: self.device_id in self.hub.sessions and self.s.status()['phase'] == 'online',
                               timeout=10), 'device is not online on the hub'
        return self.hub.sessions[self.device_id]

    def run(self, coro):
        return self.lt.run(coro)

    def _deliver(self, make, count=1):
        # Count only the fixture's own frames: a host with recent work may also send `work`
        # snapshots, which must not satisfy this fence before the intended frame arrives.
        n = len(self.s.received)
        self.run(make())
        own = lambda: sum(m.get('type') != 'work' for m in self.s.received[n:])
        assert self.s.wait_for(lambda: own() >= count, timeout=5), 'fixture not delivered'
        self.s.step()

    def send(self, kind, **data):
        session = self.session
        self._deliver(lambda: session.send_json({'type': kind, **data}))

    def turn_start(self, turn, request=None):
        session = self.session
        self._deliver(lambda: session.turn_start(turn, request=request))

    def turn_end(self, turn, outcome):
        session = self.session
        self._deliver(lambda: session.turn_end(turn, outcome))

    def delta(self, text, turn=None):
        session = self.session
        self._deliver(lambda: session.send_delta(text, turn=turn))

    def reply(self, text, turn=None):
        session = self.session
        self._deliver(lambda: session.send_reply(text, turn=turn))

    def play(self, pcm, turn=None, rate=16000):
        """A real hub AudioOut: resampled, paced 0.5 s ahead, audio.end from its own pump."""
        session = self.session

        async def go():
            out = await session.open_audio(rate, turn=turn)
            out.write(pcm)
            out.finish()
            return out

        n = len(self.s.received)
        out = self.run(go())
        assert self.s.wait_for(lambda: any(m.get('type') == 'audio.start' and m.get('stream') == out.stream
                                           for m in self.s.received[n:]), timeout=5)
        self.s.step()
        return out

    def wait(self, predicate, timeout=8.0):
        return self.s.wait_for(predicate, timeout=timeout)

    # rendered controls
    def control(self, name):
        rect = ui(self.s)['controls'][name]
        x, y, w, h = rect
        f = framebuffer(self.s)
        assert len(np.unique(f[y:y + h, x:x + w])) >= 2, (name, 'control is not rendered')
        assert inside_circle(rect), (name, rect, 'control leaves the safe circle')
        return x + w // 2, y + h // 2

    def rect(self, name):
        return ui(self.s)['controls'][name]

    def label(self, name, text, size=18, fg=TEXT, bg=SURFACE):
        return find_text(self.s, text, size, fg, bg, tuple(self.rect(name)))

    def require_label(self, name, text, size=18, fg=TEXT, bg=SURFACE):
        assert self.label(name, text, size, fg, bg), (name, text, 'label not rendered exactly (or truncated)')

    def shows(self, text, size, fg, bg=0, box=(0, 0, 466, 466)):
        return find_text(self.s, text, size, fg, bg, box) is not None

    def headline(self, text):
        return self.shows(text, 30, TEXT, 0, HEADLINE)

    def detail(self, text):
        return self.shows(text, 17, DIM, 0, DETAIL)

    # evidence
    def snap(self, label):
        self.out.mkdir(parents=True, exist_ok=True)
        i = len(self.snaps)
        name = f'{i:02d}-{label}'
        self.s.screenshot(self.out / f'{name}.png')
        raw = self.s.device.framebuffer_rows()
        (self.out / f'{name}.json').write_text(json.dumps({
            'label': label, 'status': self.s.status(),
            'framebuffer_rgb565_sha256': hashlib.sha256(raw).hexdigest(),
            'sent_count': len(self.s.sent), 'hal_count': len(self.hal),
        }, indent=2))
        self.snaps.append(name)


def _instrument(rig, sim):
    def wrap(name):
        original = getattr(sim, name)

        def call(*args):
            entry = {'t_ms': sim.now_ms(), 'call': name}
            if name == 'speaker_write':
                entry['bytes'] = len(args[0])
                entry['data'] = bytes(args[0])
            elif name in ('speaker_begin', 'mic_start'):
                entry['rate'] = args[0]
            rig.hal.append(entry)
            return original(*args)

        setattr(sim, name, call)

    for name in ('speaker_begin', 'speaker_write', 'speaker_end', 'speaker_abort', 'mic_start', 'mic_stop'):
        wrap(name)

    def frame(log, data, t):
        if len(data) >= 4:
            channel, stream, seq = struct.unpack_from('<BBH', data)
            log.append({'t_ms': t, 'channel': channel, 'stream': stream, 'seq': seq, 'bytes': len(data) - 4})

    send_binary = sim.transport_send_binary

    def tx(data):
        frame(rig.tx, data, sim.now_ms())
        return send_binary(data)

    sim.transport_send_binary = tx
    transport_binary = sim.device.transport_binary

    def rx(data):
        frame(rig.rx, data, sim.now_ms())
        return transport_binary(data)

    sim.device.transport_binary = rx


def _summary(frames):
    streams: dict[str, dict] = {}
    for f in frames:
        key = f"ch{f['channel']}/stream{f['stream']}"
        s = streams.setdefault(key, {'frames': 0, 'bytes': 0, 'first_ms': f['t_ms'], 'last_ms': f['t_ms']})
        s['frames'] += 1
        s['bytes'] += f['bytes']
        s['last_ms'] = f['t_ms']
    return streams


def _sha(path: Path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


@pytest.fixture(scope='session')
def ix_run():
    """Run-level evidence: environment, library and sources under test, exact command."""
    OUT.mkdir(parents=True, exist_ok=True)
    from hermes_gadget import paths
    lib = paths.find_sim_library()
    sources = {}
    for pattern in ('firmware/core/src/*.cpp', 'firmware/core/include/hg/*.hpp', 'firmware/sim/src/*.cpp',
                    'plugin/*.py', 'python/hermes_gadget/*.py', 'python/hermes_gadget/sim/*.py',
                    'tests/conftest.py', 'tests/test_touch_navigation.py', 'tests/test_face_first_font.py',
                    'tests/test_interaction_surface_e2e.py'):
        for p in sorted(REPO.glob(pattern)):
            if 'assets.hpp' not in p.name:
                sources[str(p.relative_to(REPO))] = _sha(p)
    for p in sorted(REPO.glob('firmware/core/include/hg/*assets.hpp')):
        sources[str(p.relative_to(REPO))] = _sha(p)
    git = lambda *a: subprocess.run(['git', *a], cwd=REPO, capture_output=True, text=True).stdout.strip()
    try:
        import importlib.metadata as md
        packages = {n: md.version(n) for n in ('pytest', 'websockets', 'pillow', 'numpy')}
    except Exception as exc:  # pragma: no cover - evidence only
        packages = {'error': str(exc)}
    env_keys = ('HGSIM_LIBRARY', 'HERMES_HOME', 'HERMES_AGENT_DIR', 'IX_ARTIFACTS', 'TMPDIR', 'SWIPE_ARTIFACTS',
                'FACE_ARTIFACTS', 'AMOLED_ARTIFACTS')
    fixture_copy = OUT / 'fixtures' / 'test_interaction_surface_e2e.py'
    fixture_copy.parent.mkdir(parents=True, exist_ok=True)
    fixture_copy.write_bytes((REPO / 'tests/test_interaction_surface_e2e.py').read_bytes())
    (OUT / 'run.json').write_text(json.dumps({
        'started': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
        'argv': sys.argv, 'cwd': os.getcwd(),
        'environment': {k: os.environ.get(k) for k in env_keys},
        'python': sys.version, 'platform': platform.platform(), 'packages': packages,
        'library': str(lib) if lib else None, 'library_sha256': _sha(Path(lib)) if lib else None,
        'git_head': git('rev-parse', 'HEAD'), 'git_status': git('status', '--short'),
        'sources_sha256': sources,
        'fixtures': 'literal protocol fixtures and real hub APIs in tests/test_interaction_surface_e2e.py '
                    '(copied to fixtures/); no providers, no production state',
    }, indent=2))
    return OUT


@pytest.fixture
def ix(ix_run, tmp_path, request):
    board = getattr(request, 'param', 'sim-466x466-round')
    from hermes_gadget.sim import Simulator
    from hermes_gadget_plugin.hub import DeviceHub
    from hermes_gadget_plugin.store import DeviceStore

    lt = LoopThread()
    brain = _brain_class()()
    hub = DeviceHub(DeviceStore(tmp_path / 'server'), brain, host='127.0.0.1', port=0, heartbeat_s=5)
    brain.hub = hub
    lt.run(hub.start())
    out = ix_run / request.node.name.replace('/', '_').replace('[', '-').replace(']', '')
    sim = Simulator(url=f'ws://127.0.0.1:{hub.bound_port}/gadget', name='Interaction Gadget', board=board,
                    state_dir=tmp_path / 'device')
    rig = Rig(sim, hub, brain, lt, out)
    _instrument(rig, sim)
    try:
        sim.start()
        assert sim.wait_screen('ready', timeout=10)
        rig.device_id = sim.status()['device_id']
        yield rig
    finally:
        try:
            out.mkdir(parents=True, exist_ok=True)
            sim.screenshot(out / 'final.png')
            raw = sim.device.framebuffer_rows()
            (out / 'final.json').write_text(json.dumps({
                'board': board, 'status': sim.status(), 'sent': sim.sent, 'received': sim.received,
                'device_binary_tx': _summary(rig.tx), 'device_binary_rx': _summary(rig.rx),
                'hal': [{k: v for k, v in h.items() if k != 'data'} for h in rig.hal],
                'hub_delegate_calls': brain.calls, 'snapshots': rig.snaps,
                'framebuffer_rgb565_sha256': hashlib.sha256(raw).hexdigest(),
                'framebuffer_rgb888_sha256': hashlib.sha256(sim.rgb888()).hexdigest(),
            }, indent=2, default=str))
        finally:
            sim.close()
            lt.run(hub.stop())
            lt.stop()


def home_with_text(r, turn, text):
    """Select Home explicitly first (as test_reply_indicator does) so new text stays unread."""
    swipe(r.s, dy=100)
    swipe(r.s, dx=100)
    r.delta(text, turn=turn)
    assert ui(r.s)['view'] == 'home'


def completed_reading(r, turn='read', text=LONG):
    r.turn_start(turn)
    r.delta(text, turn=turn)
    r.reply(text, turn=turn)
    r.turn_end(turn, 'success')
    assert r.wait(lambda: ui(r.s)['activity'] == 'idle')
    if ui(r.s)['view'] == 'home':   # an explicit Home choice is retained; open the reply
        swipe(r.s, dy=-100)
    assert ui(r.s)['view'] == 'response'


# == M1.1 Silence ============================================================================

def test_silence_quiets_real_hub_stream_without_cancelling_work(ix):
    """Silence aborts local playback only; host streaming, text and completion continue.

    Late audio for the same turn (new stream, then turn-less as after the adapter
    pops its turn) stays quiet; a distinct next turn plays again, byte for byte.
    """
    r, s = ix, ix.s
    r.turn_start('turn-A')
    home_with_text(r, 'turn-A', 'Answer streaming while Hermes speaks')
    pcm = tone(3.0)
    out = r.play(pcm, turn='turn-A')
    assert r.wait(lambda: r.speaker_bytes() >= 3200 and ui(s)['speaking'])
    r.snap('speaking')
    x, y = r.control('silence')
    r.require_label('silence', 'Silence')
    m = r.mark()
    tap(s, x, y)
    r.snap('silenced')
    assert r.hal_since(m, 'speaker_abort'), 'playback was not aborted locally'
    assert not ui(s)['speaking']
    assert not (r.sent_types(m) & REQUESTS), r.sent_since(m)
    # The host is not told and keeps pacing; dropping frames cannot stall its pump.
    assert r.wait(out.done.is_set, 8), 'host AudioOut pump did not complete'
    assert not out.aborted and out.sent_seconds >= 2.9
    assert r.rx_frames(m, out.stream) > 0, 'frames should keep arriving after local silence'
    assert r.speaker_bytes(m) == 0, 'silenced frames reached the speaker'
    assert r.brain.count('cancel') == 0
    r.reply('Answer streaming while Hermes speaks, complete.', turn='turn-A')
    r.turn_end('turn-A', 'success')
    assert r.wait(lambda: ui(s)['activity'] == 'idle')
    assert r.headline('Reply ready'), 'text completion must continue after Silence'
    r.control('reply')
    begins = r.hal_count('speaker_begin')
    late_same = r.play(tone(0.6), turn='turn-A')
    assert r.wait(late_same.done.is_set, 6)
    late_turnless = r.play(tone(0.6))
    assert r.wait(late_turnless.done.is_set, 6)
    s.run_for(0.2)
    assert r.hal_count('speaker_begin') == begins and r.speaker_bytes(m) == 0 and not ui(s)['speaking']
    r.snap('late-audio-quiet')
    r.turn_start('turn-B')
    pcm_b = tone(0.8, freq=660.0)
    mb = r.mark()
    next_turn = r.play(pcm_b, turn='turn-B')
    assert r.wait(lambda: r.speaker_bytes(mb) > 0 and ui(s)['speaking']), 'a new turn must play again'
    assert r.wait(next_turn.done.is_set, 6)
    assert r.wait(lambda: r.speaker_payload(mb) == pcm_b, 4), 'next turn audio must arrive intact'


@pytest.mark.parametrize('view', ['response', 'controls'])
def test_silence_is_reachable_in_reading_and_controls_views(ix, view):
    """Silence and Stop work are both offered while speaking with work active; Silence keeps work."""
    r, s = ix, ix.s
    r.turn_start('turn-V')
    r.delta(LONG, turn='turn-V')
    if view == 'controls':
        swipe(s, dx=100)
        swipe(s, dy=100)
    out = r.play(tone(2.5), turn='turn-V')
    assert r.wait(lambda: ui(s)['speaking'])
    assert ui(s)['view'] == view
    x, y = r.control('silence')
    r.require_label('silence', 'Silence')
    r.control('stop')
    r.require_label('stop', 'Stop work')
    r.snap(f'{view}-speaking')
    m = r.mark()
    tap(s, x, y)
    assert r.hal_since(m, 'speaker_abort') and not ui(s)['speaking']
    assert ui(s)['view'] == view, 'Silence is not navigation'
    assert ui(s)['activity'] == 'streaming', 'Silence must not end the work'
    assert not (r.sent_types(m) & REQUESTS)
    assert r.wait(out.done.is_set, 8) and not out.aborted
    r.snap(f'{view}-silenced')


def test_silence_holds_across_reconnect_until_a_new_turn(ix):
    """Connection loss does not resurrect a silenced turn; a reused stream id stays quiet."""
    r, s = ix, ix.s
    r.turn_start('turn-R')
    first = r.play(tone(2.5), turn='turn-R')
    assert r.wait(lambda: ui(s)['speaking'])
    tap(s, *r.control('silence'))
    assert not ui(s)['speaking']
    s.set_network(False)
    assert s.wait_screen('offline', timeout=5)
    s.set_network(True)
    assert s.wait_screen('ready', timeout=10)
    r.snap('reconnected')
    m = r.mark()
    begins = r.hal_count('speaker_begin')
    again = r.play(tone(0.6), turn='turn-R')
    assert again.stream == first.stream, 'a fresh hub session reuses stream ids'
    assert r.wait(again.done.is_set, 6)
    s.run_for(0.2)
    assert r.hal_count('speaker_begin') == begins and r.speaker_bytes(m) == 0
    r.turn_start('turn-S')
    later = r.play(tone(0.6), turn='turn-S')
    assert r.wait(lambda: r.speaker_bytes(m) > 0), 'a new turn after reconnect must play'
    assert r.wait(later.done.is_set, 6)


def test_silence_with_turnless_legacy_audio_and_new_request_resumes(ix):
    """Hosts without turn ids: quiet until a new turn starts or the user asks again."""
    r, s = ix, ix.s
    r.send('turn.start')
    r.play(tone(2.5))
    assert r.wait(lambda: ui(s)['speaking'])
    tap(s, *r.control('silence'))
    m = r.mark()
    more = r.play(tone(0.6))
    assert r.wait(more.done.is_set, 6)
    s.run_for(0.2)
    assert r.speaker_bytes(m) == 0 and not ui(s)['speaking']
    r.send('turn.start')
    resumed = r.play(tone(2.5))
    assert r.wait(lambda: r.speaker_bytes(m) > 0 and ui(s)['speaking']), 'a new legacy turn must play'
    tap(s, *r.control('silence'))
    assert r.wait(resumed.done.is_set, 8)
    s.type_text('a new question')
    assert r.wait(lambda: r.brain.count('text') == 1)
    m2 = r.mark()
    answer = r.play(tone(0.6))
    assert r.wait(lambda: r.speaker_bytes(m2) > 0), 'a new request must not inherit silence'
    assert r.wait(answer.done.is_set, 6)


def test_silence_contact_cannot_quiet_replacement_audio(ix):
    """A Silence contact belongs to the output revision where it began."""
    r, s = ix, ix.s
    r.turn_start('turn-C')
    r.play(tone(3.0), turn='turn-C')
    assert r.wait(lambda: ui(s)['speaking'])
    x, y = r.control('silence')
    begins = r.hal_count('speaker_begin')
    s.touch(True, x, y)
    replacement = r.play(tone(3.0), turn='turn-C')
    assert r.wait(lambda: r.hal_count('speaker_begin') > begins and ui(s)['speaking'])
    s.touch(False)
    s.step()
    assert ui(s)['speaking'], 'an older contact silenced replacement audio'
    tap(s, *r.control('silence'))
    assert not ui(s)['speaking']
    assert r.wait(replacement.done.is_set, 8)


# == M1.2 Stop work ==========================================================================

STOP_OUTCOMES = {
    'cancelled': ('Stopped', 'Completed steps are not undone'),
    'success': ('Finished', 'Stop was not confirmed'),
    'failure': ('Ended with an error', 'Stop was not confirmed'),
}


@pytest.mark.parametrize('outcome', list(STOP_OUTCOMES))
def test_stop_work_on_home_requests_once_and_awaits_matching_outcome(ix, outcome):
    """Stop work: one targeted cancel, Stop requested, then only the matching outcome's label."""
    r, s = ix, ix.s
    r.turn_start('work-1')
    assert ui(s)['view'] == 'home'
    x, y = r.control('stop')
    r.require_label('stop', 'Stop work')
    m = r.mark()
    tap(s, x, y)
    cancels = r.sent_since(m, 'cancel')
    assert len(cancels) == 1 and cancels[0].get('turn') == 'work-1', cancels
    assert r.headline('Stop requested') and r.detail('Waiting for Hermes to confirm')
    assert not r.headline('Stopped') and not r.headline('Cancelled')
    assert ui(s)['activity'] == 'thinking', 'work is not assumed stopped'
    r.snap('stop-requested')
    tap(s, x, y)
    s.tap('cancel')
    assert s.console('cancel').startswith('@ok')
    s.step()
    assert len(r.sent_since(m, 'cancel')) == 1, 'repeated Stop must not send another cancel'
    assert r.wait(lambda: r.brain.count('cancel') == 1)
    assert r.headline('Stop requested')
    r.turn_end('work-1', outcome)
    assert r.wait(lambda: ui(s)['activity'] == 'idle')
    head, detail = STOP_OUTCOMES[outcome]
    assert r.headline(head) and r.detail(detail), (outcome, ui(s))
    if outcome != 'cancelled':
        assert not r.headline('Stopped'), 'a completed or failed turn must not be relabelled stopped'
    r.snap(f'outcome-{outcome}')


def test_stop_after_final_text_is_not_relabelled_cancelled(ix):
    """Final text is not completion; a later success after Stop is shown as finished."""
    r, s = ix, ix.s
    r.turn_start('work-2')
    r.delta('Draft', turn='work-2')
    r.reply('Final text before the turn ends.', turn='work-2')
    assert ui(s)['view'] == 'response'
    x, y = r.control('stop')
    r.require_label('stop', 'Stop work')
    m = r.mark()
    tap(s, x, y)
    assert [c.get('turn') for c in r.sent_since(m, 'cancel')] == ['work-2']
    r.turn_end('work-2', 'success')
    assert r.wait(lambda: ui(s)['activity'] == 'idle')
    swipe(s, dx=100)
    assert r.headline('Finished') and r.detail('Stop was not confirmed')
    assert not r.headline('Stopped')
    r.snap('finished-not-stopped')


@pytest.mark.parametrize('view', ['response', 'controls'])
def test_stop_work_reachable_from_reading_and_controls(ix, view):
    """Stop work is a direct action in reading and controls, without navigating first."""
    r, s = ix, ix.s
    r.turn_start('work-3')
    r.delta(LONG, turn='work-3')
    if view == 'controls':
        swipe(s, dx=100)
        swipe(s, dy=100)
    assert ui(s)['view'] == view
    x, y = r.control('stop')
    r.require_label('stop', 'Stop work')
    m = r.mark()
    tap(s, x, y)
    assert [c.get('turn') for c in r.sent_since(m, 'cancel')] == ['work-3']
    assert ui(s)['view'] == view and ui(s)['activity'] == 'streaming'
    r.require_label('stop', 'Stop requested', fg=DIM, bg=0)
    tap(s, x, y)
    assert len(r.sent_since(m, 'cancel')) == 1
    r.snap(f'{view}-pending')


def test_old_turn_end_after_new_request_cannot_end_new_work(ix):
    """A turn.end that arrives after the device sent a new request belongs to older work."""
    r, s = ix, ix.s
    r.turn_start('old-turn')
    s.type_text('a newer question')
    assert r.wait(lambda: r.brain.count('text') == 1)
    r.turn_end('old-turn', 'success')
    s.run_for(0.3)
    assert ui(s)['activity'] == 'thinking', 'an old turn.end ended the new request'
    assert r.headline('Thinking')
    r.require_label('stop', 'Stop work')
    r.turn_start('new-turn')
    r.reply('Newer answer', turn='new-turn')
    r.turn_end('new-turn', 'success')
    assert r.wait(lambda: ui(s)['activity'] == 'idle')


def test_old_stop_outcome_cannot_relabel_new_request(ix):
    """A late cancellation of old work cannot mark the next request stopped."""
    r, s = ix, ix.s
    r.turn_start('old-turn')
    m = r.mark()
    tap(s, *r.control('stop'))
    assert [c.get('turn') for c in r.sent_since(m, 'cancel')] == ['old-turn']
    s.type_text('changed my mind, new question')
    assert r.wait(lambda: r.brain.count('text') == 1)
    assert r.headline('Thinking')
    r.require_label('stop', 'Stop work')
    r.turn_end('old-turn', 'cancelled')
    s.run_for(0.3)
    assert ui(s)['activity'] == 'thinking' and r.headline('Thinking') and not r.headline('Stopped')
    r.turn_start('new-turn')
    r.reply('New answer', turn='new-turn')
    r.turn_end('new-turn', 'success')
    assert r.wait(lambda: ui(s)['activity'] == 'idle')
    swipe(s, dx=100)
    assert r.headline('Hold to talk') and not r.headline('Stopped')


def test_disconnect_before_stop_outcome_is_unknown_until_matching_evidence(ix):
    """Disconnect leaves the stop unconfirmed; only the matching turn.end later confirms it."""
    r, s = ix, ix.s
    r.turn_start('work-d')
    m = r.mark()
    tap(s, *r.control('stop'))
    assert len(r.sent_since(m, 'cancel')) == 1
    s.set_network(False)
    assert s.wait_screen('offline', timeout=5)
    assert ui(s)['headline'] == 'No network' and ui(s)['detail'].startswith('Task status unknown')
    r.snap('offline-pending')
    s.set_network(True)
    assert s.wait_screen('ready', timeout=10)
    m2 = r.mark()
    s.run_for(0.5)
    assert r.headline('Outcome unknown') and r.detail('Connection lost while stopping')
    assert not r.headline('Stopped')
    assert not (r.sent_types(m2) & REQUESTS), 'reconnect must not replay requests'
    r.snap('unknown-after-reconnect')
    r.turn_end('work-d', 'cancelled')
    assert r.headline('Stopped') and r.detail('Completed steps are not undone')


def test_stale_home_stop_contact_cannot_stop_new_turn(ix):
    r, s = ix, ix.s
    r.turn_start('turn-old')
    x, y = r.control('stop')
    s.touch(True, x, y)
    r.turn_start('turn-new')
    s.touch(False)
    s.step()
    assert not any(m['type'] == 'cancel' for m in s.sent)


def test_stop_before_turn_start_stays_unconfirmed(ix):
    """Without a turn id the request cannot be matched; the outcome stays unknown."""
    r, s = ix, ix.s
    s.type_text('quick question')
    assert r.wait(lambda: r.brain.count('text') == 1)
    request = next(m for m in s.sent if m['type'] == 'text')['id']
    m = r.mark()
    tap(s, *r.control('stop'))
    cancels = r.sent_since(m, 'cancel')
    assert len(cancels) == 1 and 'turn' not in cancels[0] and cancels[0].get('request') == request
    r.turn_start('late-turn')
    r.turn_end('late-turn', 'cancelled')
    assert r.wait(lambda: ui(s)['activity'] == 'idle')
    assert r.headline('Outcome unknown') and r.detail('Sent before Hermes started')
    assert not r.headline('Stopped')


# == M1.3 Capture, discard and reading ownership ============================================

def test_reading_hold_is_navigation_only(ix):
    """A patient reader's still finger never starts a recording."""
    r, s = ix, ix.s
    completed_reading(r)
    swipe(s, dy=100)
    pos = ui(s)['scroll']
    assert pos >= 0
    m = r.mark()
    s.touch(True, 233, 220)
    s.run_for(1.5)
    s.touch(False)
    s.step()
    assert 'audio.start' not in r.sent_types(m) and not r.hal_since(m, 'mic_start')
    assert ui(s)['activity'] == 'idle' and ui(s)['view'] == 'response' and ui(s)['scroll'] == pos


def test_reading_talk_control_hold_records_and_owner_release_finishes(ix):
    r, s = ix, ix.s
    completed_reading(r)
    x, y = r.control('talk')
    r.require_label('talk', 'Hold to talk')
    m = r.mark()
    s.touch(True, x, y)
    s.run_for(0.6)
    assert len(r.sent_since(m, 'audio.start')) == 1 and ui(s)['activity'] == 'recording'
    assert r.detail('Release to finish')
    s.touch(True, x + 5, y - 40)    # movement during the hold neither submits nor discards
    s.run_for(0.3)
    assert not (r.sent_types(m) & {'audio.end', 'audio.cancel'})
    s.touch(False)
    s.step()
    assert len(r.sent_since(m, 'audio.end')) == 1 and not r.sent_since(m, 'audio.cancel')
    assert r.wait(lambda: r.brain.count('utterance') == 1), 'release must dispatch the utterance'


def test_touch_hold_copy_is_release_to_finish_without_fake_discard(ix):
    """A single-touch hold cannot offer a simultaneous Discard target."""
    r, s = ix, ix.s
    m = r.mark()
    s.touch(True, 233, 220)
    s.run_for(0.5)
    assert ui(s)['activity'] == 'recording'
    assert r.headline('Listening') and r.detail('Release to finish')
    assert not ({'discard', 'finish'} & set(ui(s)['controls']))
    assert not r.shows('Discard', 18, TEXT, SURFACE)
    r.snap('touch-hold')
    s.touch(False)
    s.step()
    assert len(r.sent_since(m, 'audio.end')) == 1


def test_physical_talk_hold_offers_touch_discard_without_dispatch(ix):
    """BOOT/TALK held leaves the touchscreen free: Discard cancels without a request."""
    r, s = ix, ix.s
    m = r.mark()
    s.press('talk')
    s.run_for(0.4)
    assert ui(s)['activity'] == 'recording'
    assert r.detail('Release SPACE to finish')
    x, y = r.control('discard')
    r.require_label('discard', 'Discard')
    r.snap('button-hold')
    tap(s, 233, 200)                 # a second contact elsewhere does nothing
    assert ui(s)['activity'] == 'recording' and not (r.sent_types(m) & {'audio.end', 'audio.cancel'})
    sent_frames = r.tx_audio_frames(m)
    assert sent_frames > 0, 'samples stream while recording; discard cannot claim nothing left'
    tap(s, x, y)
    assert len(r.sent_since(m, 'audio.cancel')) == 1 and not r.sent_since(m, 'audio.end')
    assert r.hal_since(m, 'mic_stop')
    s.release('talk')
    s.run_for(0.5)
    assert not r.sent_since(m, 'audio.end') and r.brain.count('utterance') == 0
    assert r.session._upload is None, 'the hub must drop the cancelled upload'
    assert r.headline('Discarded') and r.detail('Not sent as a request')
    r.snap('discarded')


def test_tap_mode_discard_and_finish_controls(ix):
    r, s = ix, ix.s
    s.console('set talk_mode tap')
    m = r.mark()
    tap(s, 233, 220)
    assert ui(s)['activity'] == 'recording'
    assert r.detail('Pause or tap Finish')
    discard, finish = r.rect('discard'), r.rect('finish')
    assert discard[2:] == finish[2:], 'Discard and Finish need equal targets'
    r.control('discard')
    r.control('finish')
    r.require_label('discard', 'Discard')
    r.require_label('finish', 'Finish')
    r.snap('tap-recording')
    s.run_for(0.3)
    tap(s, *r.control('discard'))
    assert len(r.sent_since(m, 'audio.cancel')) == 1 and not r.sent_since(m, 'audio.end')
    s.run_for(0.3)
    assert r.brain.count('utterance') == 0
    assert r.headline('Discarded')
    m2 = r.mark()
    s.mic.inject(tone(2.0))
    tap(s, 233, 220)
    s.run_for(1.0)
    tap(s, *r.control('finish'))
    assert len(r.sent_since(m2, 'audio.end')) == 1 and not r.sent_since(m2, 'audio.cancel')
    assert r.wait(lambda: r.brain.count('utterance') == 1)


def test_no_speech_tap_capture_and_stale_finish_contact(ix):
    """VAD may end a capture under a held Finish contact; it cannot finish the next capture."""
    r, s = ix, ix.s
    s.console('set talk_mode tap')
    m = r.mark()
    tap(s, 233, 220)
    x, y = r.control('finish')
    s.touch(True, x, y)
    assert r.wait(lambda: any(c.get('reason') == 'no speech' for c in r.sent_since(m, 'audio.cancel')), 9)
    assert not r.sent_since(m, 'audio.end')
    s.console('talk')
    assert ui(s)['activity'] == 'recording'
    s.touch(False)
    s.step()
    assert not r.sent_since(m, 'audio.end'), 'a stale Finish contact finished a new capture'
    tap(s, *r.control('discard'))
    assert len(r.sent_since(m, 'audio.cancel')) == 2 and r.brain.count('utterance') == 0


def test_new_talk_controls_never_answer_prompts(ix):
    r, s = ix, ix.s
    completed_reading(r)
    x, y = r.control('talk')
    m = r.mark()
    s.touch(True, x, y)
    r.send('prompt', id='p-talk', title='Permission', text='Allow the fixture?')
    s.run_for(0.8)
    s.touch(False)
    s.step()
    assert not (r.sent_types(m) & {'prompt.reply', 'audio.start'})
    assert set(ui(s)['controls']) == {'yes', 'no'}, 'approval offers no talk/discard targets'
    r.send('prompt.close', id='p-talk')
    s.console('set talk_mode tap')
    if ui(s)['view'] != 'home':
        swipe(s, dx=100)
    s.touch(True, 233, 220)
    r.send('prompt', id='p-tap', title='Permission', text='Allow the fixture?')
    s.run_for(0.8)
    s.touch(False)
    s.step()
    assert not (r.sent_types(m) & {'prompt.reply', 'audio.start'})
    assert r.brain.count('prompt_reply') == 0


# == M2.4 Discoverable controls and balanced review =========================================

@pytest.mark.parametrize('talk_mode', ['hold', 'tap'])
def test_controls_and_return_have_visible_tap_routes(ix, talk_mode):
    r, s = ix, ix.s
    s.console(f'set talk_mode {talk_mode}')
    m = r.mark()
    x, y = r.control('controls')
    assert r.label('controls', '↓  Controls', 14, DIM, 0)
    tap(s, x, y)
    assert ui(s)['view'] == 'controls'
    hx, hy = r.control('home')
    assert r.label('home', 'Quick controls', 14, DIM, 0)
    tap(s, hx, hy)
    assert ui(s)['view'] == 'home'
    completed_reading(r)
    assert r.label('home', 'Latest reply', 14, DIM, 0)
    tap(s, *r.control('home'))
    assert ui(s)['view'] == 'home'
    assert not (r.sent_types(m) & {'audio.start', 'cancel', 'session.new'})


def test_idle_settings_entry_without_title_hold(ix):
    r, s = ix, ix.s
    m = r.mark()
    tap(s, *r.control('controls'))
    x, y = r.control('settings')
    r.require_label('settings', 'Settings')
    tap(s, x, y)
    assert s.device.screen() == 'settings' and ui(s)['view'] == 'other'
    assert not (r.sent_types(m) & REQUESTS)


@pytest.mark.parametrize('state', ['thinking', 'speaking'])
def test_settings_never_cancel_active_work(ix, state):
    r, s = ix, ix.s
    if state == 'thinking':
        r.turn_start('busy')
    else:
        out = r.play(tone(3.0))
        assert r.wait(lambda: ui(s)['speaking'])
    swipe(s, dy=100)
    assert ui(s)['view'] == 'controls'
    assert 'settings' not in ui(s)['controls']
    assert r.shows('Settings open when idle', 14, DIM, 0, (0, 380, 466, 60))
    m = r.mark()
    tap(s, 233, 405)
    # Quick controls also report Screen::Settings; the legacy menu would be view 'other'.
    assert ui(s)['view'] == 'controls' and ui(s)['headline'] == 'Quick controls'
    assert s.console('settings').startswith('@error')
    s.step()
    assert not (r.sent_types(m) & REQUESTS), r.sent_since(m)
    assert ui(s)['activity'] == state
    if state == 'speaking':
        assert ui(s)['speaking'] and not r.hal_since(m, 'speaker_abort')
    r.snap(f'settings-refused-{state}')


def test_settings_console_refuses_during_recording(ix):
    r, s = ix, ix.s
    s.press('talk')
    s.run_for(0.2)
    m = r.mark()
    assert s.console('settings').startswith('@error')
    s.step()
    assert ui(s)['activity'] == 'recording' and not r.sent_since(m, 'audio.cancel')
    s.release('talk')


def test_approval_equal_emphasis_and_enlarged_targets(ix):
    r, s = ix, ix.s
    r.send('prompt', id='eq', title='Permission', text='Allow the desk lamp?')
    s.run_for(0.7)
    yes, no = r.rect('yes'), r.rect('no')
    assert yes[2:] == no[2:], 'Yes and No must be equal targets'
    assert yes[3] >= 90 and yes[2] >= 140, ('consequential targets were not enlarged', yes)
    assert inside_circle(yes) and inside_circle(no)
    f = framebuffer(s)
    fills = {int(f[r_[1] + 8, r_[0] + r_[2] // 2]) for r_ in (yes, no)}
    assert fills == {SURFACE}, ('unequal or amber emphasis', [hex(v) for v in fills])
    r.require_label('yes', 'Yes')
    r.require_label('no', 'No')
    r.snap('approval')
    tap(s, *r.control('yes'))
    assert any(m_['type'] == 'prompt.reply' and m_['id'] == 'eq' and m_['answer'] == 'yes' for m_ in s.sent)


def test_long_question_tail_and_generic_labels(ix):
    """Guard: the exact final line is reachable and generic answers are not relabelled."""
    r, s = ix, ix.s
    text = '\n'.join([f'Step {i:02d}: exact wording' for i in range(20)] + ['FINAL: proceed?'])
    r.send('prompt', id='tail', title='Question', text=text)
    s.run_for(0.7)
    for _ in range(12):
        swipe(s, dy=-100)
    assert r.shows('FINAL: proceed?', 24, TEXT, 0, (0, 100, 466, 200))
    assert set(ui(s)['controls']) == {'yes', 'no'}
    assert not any(m['type'] == 'prompt.reply' for m in s.sent)
    tap(s, *r.control('no'))
    assert any(m['type'] == 'prompt.reply' and m['answer'] == 'no' for m in s.sent)


def test_reading_actions_leave_text_and_tail_unobstructed(ix):
    r, s = ix, ix.s
    lines = [f'Row {i:02d}' for i in range(30)] + ['Row 30 end']
    r.turn_start('rows')
    r.delta('\n'.join(lines), turn='rows')
    r.play(tone(3.0), turn='rows')
    assert r.wait(lambda: ui(s)['speaking'])
    actions = [r.rect('silence'), r.rect('stop')]
    top = min(a[1] for a in actions)
    assert not overlap(actions[0], actions[1])
    pos = find_text(s, 'Row 30 end', 24, TEXT, 0, (0, 90, 466, top - 90))
    assert pos is not None, 'the streamed tail must be fully visible above the actions'
    for _ in range(12):
        swipe(s, dy=100)
    assert ui(s)['scroll'] == 0 and r.shows('Row 00', 24, TEXT, 0, (0, 90, 466, top - 90))
    for _ in range(12):
        swipe(s, dy=-100)
    assert ui(s)['scroll'] == -1 and find_text(s, 'Row 30 end', 24, TEXT, 0, (0, 90, 466, top - 90))
    r.snap('reading-actions')


# == M2.5 Honest state and errors ============================================================

def test_partial_text_stopped_outcome_and_reply_remain_readable(ix):
    r, s = ix, ix.s
    r.turn_start('part')
    home_with_text(r, 'part', 'Partial findings so far')
    tap(s, *r.control('stop'))
    r.turn_end('part', 'cancelled')
    assert r.wait(lambda: ui(s)['activity'] == 'idle')
    assert r.headline('Stopped') and ui(s)['hint'] == 'Reply stopped - tap to read'
    r.require_label('reply', 'Read reply  ↑')
    tap(s, *r.control('reply'))
    assert ui(s)['view'] == 'response' and r.shows('Partial findings so far', 24, TEXT, 0)


def test_offline_during_work_reconnects_without_replay(ix):
    r, s = ix, ix.s
    s.type_text('long task please')
    assert r.wait(lambda: r.brain.count('text') == 1)
    r.turn_start('long')
    home_with_text(r, 'long', 'Working notes')
    s.set_network(False)
    assert s.wait_screen('offline', timeout=5)
    assert ui(s)['headline'] == 'No network' and ui(s)['detail'].startswith('Task status unknown')
    r.snap('offline-during-work')
    m = r.mark()
    s.set_network(True)
    assert s.wait_screen('ready', timeout=10)
    s.run_for(0.5)
    assert r.headline('Connection lost') and r.detail('Task status unknown')
    assert not (r.sent_types(m) & REQUESTS) and r.brain.count('text') == 1, 'no replay after reconnect'
    tap(s, *r.control('reply'))
    assert r.shows('Working notes', 24, TEXT, 0)


def test_failure_without_text_persists_beyond_toast(ix):
    r, s = ix, ix.s
    r.turn_start('fails')
    r.turn_end('fails', 'failure')
    assert r.wait(lambda: ui(s)['activity'] == 'idle')
    assert r.headline('Couldn’t finish') and r.detail('Hermes reported a failure')
    s.run_for(9)    # longer than the previous 8 s notice
    assert r.headline('Couldn’t finish') and r.detail('Hermes reported a failure')


def test_active_audio_with_pending_work_shows_both_and_stop_also_silences(ix):
    r, s = ix, ix.s
    r.turn_start('both')
    out = r.play(tone(3.0), turn='both')
    assert r.wait(lambda: ui(s)['speaking'])
    r.require_label('silence', 'Silence')
    r.require_label('stop', 'Stop work')
    assert not overlap(r.rect('silence'), r.rect('stop'))
    m = r.mark()
    tap(s, *r.control('stop'))
    assert r.hal_since(m, 'speaker_abort') and not ui(s)['speaking'], 'Stop work also silences locally'
    assert len(r.sent_since(m, 'cancel')) == 1
    assert r.wait(lambda: out.aborted), 'the hub stops its stream on cancel'
    assert r.headline('Stop requested') and 'silence' not in ui(s)['controls']
    r.turn_end('both', 'cancelled')
    assert r.wait(lambda: ui(s)['activity'] == 'idle') and r.headline('Stopped')


# == Legacy boards, geometry, glyphs and wake ================================================

@pytest.mark.parametrize('ix', ['sim-320x240'], indirect=True)
def test_legacy_rectangular_board_cancel_capture_and_chord(ix):
    r, s = ix, ix.s
    m = r.mark()
    s.press('talk')
    s.run_for(0.5)
    s.release('talk')
    assert len(r.sent_since(m, 'audio.end')) == 1
    s.press('talk')
    s.run_for(0.2)
    s.tap('cancel')
    s.release('talk')
    assert len(r.sent_since(m, 'audio.cancel')) == 1 and len(r.sent_since(m, 'audio.end')) == 1
    r.turn_start('legacy')
    m2 = r.mark()
    s.tap('cancel')
    assert [c.get('turn') for c in r.sent_since(m2, 'cancel')] == ['legacy']
    assert s.status()['work']['stop'] == 'requested' and s.device.screen() == 'thinking'
    s.tap('cancel')
    s.press('cancel')
    s.press('talk')
    s.run_for(1.3)                 # settings chord while busy: refused, never a stop or settings
    s.release('talk')
    s.release('cancel')
    s.step()
    assert s.device.screen() != 'settings' and len(r.sent_since(m2, 'cancel')) == 1
    r.turn_end('legacy', 'cancelled')
    assert s.wait_screen('ready', timeout=5) and s.status()['work']['stop'] == 'stopped'
    r.snap('legacy-stopped')


LABELS = {
    'silence': ('Silence', 18, TEXT, SURFACE), 'stop': ('Stop work', 18, TEXT, SURFACE),
    'discard': ('Discard', 18, TEXT, SURFACE), 'finish': ('Finish', 18, TEXT, SURFACE),
    'talk': ('Hold to talk', 18, TEXT, SURFACE), 'settings': ('Settings', 18, TEXT, SURFACE),
    'reply': ('Read reply  ↑', 18, TEXT, SURFACE), 'controls': ('↓  Controls', 14, DIM, 0),
    'yes': ('Yes', 18, TEXT, SURFACE), 'no': ('No', 18, TEXT, SURFACE),
}


def test_new_controls_fit_safe_circle_and_render_supported_glyphs(ix):
    """Every visible target: inside the circle, no overlap, clear of the portrait, exact labels."""
    from test_round_amoled import safe_circle
    r, s = ix, ix.s
    checked = []

    def check(state, expect, labels=None, hero=True):
        controls = ui(s)['controls']
        assert expect <= set(controls), (state, controls)
        names = [n for n in controls if n not in ('volume', 'brightness')]
        for i, a in enumerate(names):
            assert inside_circle(controls[a]), (state, a, controls[a])
            if hero:
                assert not overlap(controls[a], PORTRAIT), (state, a, 'covers the approved portrait')
            for b in names[i + 1:]:
                assert not overlap(controls[a], controls[b]), (state, a, b)
        for name, spec in {**{n: LABELS[n] for n in names if n in LABELS}, **(labels or {})}.items():
            text, size, fg, bg = spec
            assert r.label(name, text, size, fg, bg), (state, name, text)
        raw = s.device.framebuffer_rows()
        safe_circle(struct.unpack('<' + 'H' * (len(raw) // 2), raw))
        r.snap(state)
        checked.append(state)

    check('home-idle', {'controls'})
    r.turn_start('geo')
    check('home-thinking', {'stop'})
    out = r.play(tone(4.0), turn='geo')
    assert r.wait(lambda: ui(s)['speaking'])
    check('home-speaking-working', {'silence', 'stop'})
    tap(s, *r.control('stop'))
    check('home-stop-pending', {'stop'}, {'stop': ('Requested', 18, DIM, 0)})
    r.turn_end('geo', 'cancelled')
    assert r.wait(lambda: ui(s)['activity'] == 'idle')
    s.press('talk')
    s.run_for(0.2)
    check('recording-button', {'discard'})
    s.tap('cancel')
    s.release('talk')
    s.console('set talk_mode tap')
    tap(s, 233, 220)
    check('recording-tap', {'discard', 'finish'})
    tap(s, *r.control('discard'))
    s.console('set talk_mode hold')
    completed_reading(r, 'geo-read')
    check('reading-idle', {'talk', 'home'}, {'home': ('Latest reply', 14, DIM, 0)}, hero=False)
    tap(s, *r.control('home'))
    tap(s, *r.control('controls'))
    # Remediation F5: once work has ended, the inert Stop target names its ending
    # (completed_reading ends with success), still an exact source-TTF raster.
    check('controls-idle', {'stop', 'silence', 'settings', 'home'},
          {'stop': ('Finished', 18, DIM, 0), 'silence': ('Silence', 18, DIM, 0),
           'home': ('Quick controls', 14, DIM, 0)}, hero=False)
    r.send('prompt', id='geo-q', title='Permission', text='Allow?')
    s.run_for(0.7)
    check('approval', {'yes', 'no'}, hero=False)
    assert len(checked) == 9


def test_wake_touch_on_new_controls_only_wakes(ix):
    r, s = ix, ix.s
    s.console('set screen_timeout 1')
    assert r.wait(lambda: s.status()['display_sleeping'], 4)
    x, y = (lambda q: (q[0] + q[2] // 2, q[1] + q[3] // 2))(r.rect('controls'))
    m = r.mark()
    s.touch(True, x, y)
    s.touch(False)
    s.step()
    assert not s.status()['display_sleeping'] and ui(s)['view'] == 'home'
    assert not (r.sent_types(m) & REQUESTS)
    s.console('set screen_timeout 0')
