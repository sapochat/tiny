"""Native design captures of the 466px round companion, with state checks per shot.

    python tools/design_capture.py capture OUTDIR [--library LIB] [--only GROUP,...] [--transitions]
    python tools/design_capture.py identical DIR_A DIR_B        # byte-identical framebuffers?
    python tools/design_capture.py compare DIR_A DIR_B OUT.png [SHOT ...]   # before/after pairs
    python tools/design_capture.py gaps DIR [DIR2]              # tight vertical gaps (< 12 px)

Every shot runs the production native core (``HGSIM_LIBRARY`` or ``--library``) against the
production ``DeviceHub`` on 127.0.0.1 with a disposable store, synthetic content only. Each
shot names the state it must be in (view, screen, headline, controls, ...) and the run FAILS
if the device is not there, and each shot must differ from the one before it unless marked
``same_ok``: a mislabelled tile (a request id the device rejected, a swipe that did not land)
would otherwise silently repeat the previous frame.

Captures are deterministic: the device runs on a virtual clock that advances only inside
``run_for`` (10 ms per step), its randomness is seeded, so its key and device id are the same
every run, and the host's wall clock is fixed (``HOST_TIME``). Two runs of the same library
give byte-identical framebuffers, so ``identical`` can prove a change renders nothing
differently.

Outputs per shot: NN-name.png (raw panel, corners black as the glass), NN-name.masked.png
(outside r=233 hatched, faint 228 px safe ring), shots.json (state facts + RGB565 hash) and
a masked contact sheet ``contact-sheet-<OUTDIR name>.png`` beside OUTDIR.
Env: TMPDIR (short path; Unix sockets), HERMES_HOME (disposable), PYTHONPATH=python.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
W = 466
HOST_TIME = 1_792_000_000  # 2026-10-15 ~05:46 UTC; the host clock every capture shows
HOST_OFFSET = -7 * 3600   # America/Los_Angeles in October (PDT)
PORTRAIT = (137, 96, 192, 192)  # the animated face's box on Home and the connection screens

SHORT = 'Lamp is on.'
LONG = ('I checked the calendar and moved the dentist appointment to Thursday at 3 pm. '
        'Your sister also asked whether Sunday dinner is still on; I said yes, at six.')
READ = '\n'.join([
    'Here is the summary you asked for.', '',
    'The garden sensors report soil moisture at a comfortable level in all three beds, '
    'so no watering is needed today. The greenhouse peaked at 29 degrees around two.',
    '', 'Tomorrow looks cooler with light rain in the afternoon, which should help the '
    'new seedlings. I will remind you about the compost delivery on Friday morning.'])
APPROVAL = ('Hermes wants to run a command on the desk server: archive the photo folders from 2019 '
            'to 2021, compress them into one file, move that file to the backup drive, then delete '
            'the original folders to free about 40 GB. The backup drive currently has 120 GB free. '
            'Allow Hermes to archive and delete these folders?')
FAILED_TEXT = ('Moved the dentist to Thursday at 3 pm and told your sister yes for Sunday. '
               'Could not reach the calendar for Ana, so her invite was not sent.')


def _imports():
    sys.path.insert(0, str(REPO / 'tests'))
    sys.path.insert(0, str(REPO / 'python'))
    import conftest  # noqa: F401  plugin package shim


# -- deterministic device ---------------------------------------------------------------------

def virtualize(sim, seed=7):
    """Freeze the device clock between run_for steps and seed its randomness."""
    import time as _time
    t = [1000]
    rng = random.Random(seed)
    sim.now_ms = lambda: t[0]
    sim.random_bytes = lambda n: bytes(rng.getrandbits(8) for _ in range(n))

    def run_for(seconds, interval=0.01):
        for _ in range(max(1, round(seconds / interval))):
            t[0] += round(interval * 1000)
            sim.step()
            _time.sleep(0.008)  # let the loopback hub's thread deliver

    def wait_for(predicate, timeout=10.0, interval=0.01):
        # Bounded by wall time (the hub is real). The device clock stands still while a
        # host message is in flight, so its arrival time (and the animation phase it starts)
        # is the same every run; only a wait that needs device time (a reconnect backoff)
        # advances it, after 300 ms of wall time.
        start = _time.monotonic()
        end = start + timeout
        while _time.monotonic() < end:
            if _time.monotonic() - start > 0.3:
                t[0] += round(interval * 1000)
            sim.step()
            if predicate():
                return True
            _time.sleep(0.002)
        return False

    def wait_wall(predicate, timeout=10.0):
        # For host-paced events (speech draining at real time): the device clock never moves.
        end = _time.monotonic() + timeout
        while _time.monotonic() < end:
            sim.step()
            if predicate():
                return True
            _time.sleep(0.005)
        return False

    sim.run_for = run_for
    sim.wait_for = wait_for
    sim.wait_wall = wait_wall
    sim.clock = t
    return sim


class Capture:
    def __init__(self, out: Path, library: str | None):
        _imports()
        self.out = out
        self.library = library
        self.shots: list[dict] = []
        self.open: list = []

    # rig -----------------------------------------------------------------------------------
    def make(self, network=True, host_time=HOST_TIME, offset=HOST_OFFSET, hub_kwargs=None):
        from conftest import LoopThread
        from test_interaction_surface_e2e import Rig, _brain_class, _instrument
        from hermes_gadget.sim import Simulator
        from hermes_gadget_plugin.hub import DeviceHub
        from hermes_gadget_plugin.store import DeviceStore
        tmp = Path(tempfile.mkdtemp(prefix='cap', dir=os.environ.get('TMPDIR')))
        lt = LoopThread()
        brain = _brain_class()()
        kw = dict(hub_kwargs or {})
        if host_time is not None and _hub_takes('clock'):
            kw.setdefault('clock', lambda: (host_time, offset))
        hub = DeviceHub(DeviceStore(tmp / 'server'), brain, host='127.0.0.1', port=0, heartbeat_s=5, **kw)
        brain.hub = hub
        lt.run(hub.start())
        extra = {'library': Path(self.library)} if self.library else {}
        sim = Simulator(url=f'ws://127.0.0.1:{hub.bound_port}/gadget', name='Tiny', board='sim-466x466-round',
                        state_dir=tmp / 'device', **extra)
        virtualize(sim)
        r = Rig(sim, hub, brain, lt, self.out)
        _instrument(r, sim)
        sim.start(network)
        if network:
            # The handshake is host-paced: hold the device clock so Ready lands at the same
            # device time (and portrait phase) every run.
            while sim.status()['phase'] == 'boot':
                sim.clock[0] += 10
                sim.step()
            assert sim.wait_wall(lambda: sim.device.screen() == 'ready', timeout=10)
            r.device_id = sim.status()['device_id']
        self.open.append(r)
        return r

    def close(self, r):
        r.s.close()
        r.lt.run(r.hub.stop())
        r.lt.stop()
        self.open.remove(r)

    # shots ---------------------------------------------------------------------------------
    def shot(self, r, name, settle=0.35, same_ok=False, volatile=None, **expect):
        """Capture after settling and assert the named state was reached."""
        r.s.run_for(settle)
        st = r.s.status()
        u = st.get('ui', {})
        facts = {'view': u.get('view'), 'headline': u.get('headline'), 'detail': u.get('detail'),
                 'activity': u.get('activity'), 'screen': st.get('screen'), 'scroll': u.get('scroll'),
                 'controls': sorted(u.get('controls', {})), 'work': st.get('work'),
                 'title': u.get('title'), 'needs_you': u.get('needs_you'), 'timer': u.get('timer'),
                 'clock': u.get('clock')}
        for key, want in expect.items():
            have = facts.get(key)
            ok = want(have) if callable(want) else have == want
            assert ok, f'{name}: expected {key}={want!r}, device has {have!r}\n{json.dumps(facts, indent=1)}'
        raw = r.s.device.framebuffer_rows()
        h = hashlib.sha256(raw).hexdigest()
        if self.shots and not same_ok:
            assert h != self.shots[-1]['sha256'], f'{name}: identical framebuffer to {self.shots[-1]["name"]}'
        p = self.out / f'{len(self.shots):02d}-{name}.png'
        r.s.screenshot(p)
        mask(p)
        rec = {'name': p.stem, 'sha256': h, **facts}
        if volatile:
            # The portrait's phase here follows a real socket event's arrival, which no
            # virtual clock fixes; `identical` compares this shot outside that box only.
            x, y, w, h_ = volatile
            rows = bytearray(raw)
            for yy in range(y, y + h_):
                rows[(yy * W + x) * 2:(yy * W + x + w) * 2] = bytes(w * 2)
            rec['volatile_box'] = list(volatile)
            rec['sha256_outside_volatile'] = hashlib.sha256(bytes(rows)).hexdigest()
        self.shots.append(rec)
        print(f'{p.stem:34s} view={facts["view"]!s:9s} screen={facts["screen"]!s:10s} head={facts["headline"]!r}')


def _hub_takes(param):
    import inspect
    from hermes_gadget_plugin.hub import DeviceHub
    return param in inspect.signature(DeviceHub.__init__).parameters


def mask(p: Path):
    """Masked preview: real 233 px circle, outside hatched/dimmed, faint safe ring at 228."""
    from PIL import Image
    im = Image.open(p).convert('RGB')
    px = im.load()
    for y in range(W):
        for x in range(W):
            d2 = (x - 232.5) ** 2 + (y - 232.5) ** 2
            if d2 > 233 ** 2:
                px[x, y] = (46, 46, 52) if (x + y) % 8 < 2 else (18, 18, 22)
            elif 227 ** 2 <= d2 <= 228.5 ** 2 and px[x, y] == (0, 0, 0):
                px[x, y] = (40, 60, 40)
    im.save(p.with_suffix('.masked.png'))


# -- gestures (device clock) -------------------------------------------------------------------

def swipe(s, dx=0, dy=0, x=233, y=220):
    s.touch(True, x, y); s.step()
    s.touch(True, x + dx // 3, y + dy // 3); s.step()
    s.touch(True, x + dx, y + dy); s.step()
    s.touch(False, -999, -999); s.step()


def tap(s, x, y):
    s.touch(True, x, y); s.step()
    s.touch(False, -999, -999); s.step()


def hold(s, x, y, seconds):
    s.touch(True, x, y)
    s.run_for(seconds)
    s.touch(False, -999, -999)
    s.step()


def ui(s):
    return s.status()['ui']


def view(r):
    return ui(r.s)['view']


def turn(r, t, text, outcome='success', request=True):
    r.turn_start(t, request=('req-' + t) if request else None)
    if text:
        r.reply(text, turn=t)
    r.turn_end(t, outcome)


def to_home(r):
    for _ in range(4):
        if view(r) == 'home':
            return
        if view(r) in ('recent', 'result', 'response', 'controls'):
            swipe(r.s, dx=100)
        r.s.run_for(0.35)
    assert view(r) == 'home', ui(r.s)


def to_controls(r):
    to_home(r)
    swipe(r.s, dy=100)
    r.s.run_for(0.35)
    assert view(r) == 'controls', ui(r.s)


def to_recent(r):
    to_controls(r)
    tap_ctl(r, 'recent')
    r.s.run_for(0.35)
    assert view(r) == 'recent', ui(r.s)


def tap_ctl(r, name):
    x, y, w, h = ui(r.s)['controls'][name]
    tap(r.s, x + w // 2, y + h // 2)


def hold_title(r):
    hold(r.s, 233, 62, 1.3)


def to_row(r, detail):
    for _ in range(16):
        if ui(r.s)['detail'] == detail:
            return
        swipe(r.s, dy=100)
        r.s.run_for(0.1)
    raise AssertionError(f'settings row {detail!r} not reached')


def tone(seconds, rate=16000, freq=440.0, amp=6000):
    from test_interaction_surface_e2e import tone as _tone
    return _tone(seconds, rate, freq, amp)


# -- the shot list -----------------------------------------------------------------------------

def group_home(c: Capture):
    r = c.make()
    try:
        c.shot(r, 'home-idle', 0.5, view='home')
        r.s.touch(True, 233, 200)
        r.s.run_for(0.5)
        c.shot(r, 'home-listening', 0.1, view='recording', activity='recording')
        r.s.touch(False, -999, -999)
        r.s.step()
        r.s.run_for(0.3)
        assert r.wait(lambda: ui(r.s)['activity'] == 'thinking'), ui(r.s)
        c.shot(r, 'home-thinking', view='home', activity='thinking', headline='Thinking')
        req = r.s.sent[-1].get('id') if r.s.sent else None
        audio = [m for m in r.s.sent if m.get('type') == 'audio.end']
        r.turn_start('t1', request=audio[-1]['id'] if audio else req)
        swipe(r.s, dy=100); r.s.run_for(0.35)
        swipe(r.s, dx=100); r.s.run_for(0.35)
        r.delta('Streaming the first words of a reply', turn='t1')
        c.shot(r, 'home-new-text', view='home', headline=lambda h: h in ('New text', 'New reply text'),
               controls=lambda cs: 'reply' in cs)
        r.play(tone(2.0), turn='t1')
        assert r.wait(lambda: ui(r.s)['speaking'])
        c.shot(r, 'home-speaking', 0.2, view='home', headline='Speaking',
               controls=lambda cs: 'silence' in cs and 'stop' in cs)
        swipe(r.s, dy=100)
        c.shot(r, 'controls-busy', 0.3, view='controls')
        swipe(r.s, dx=100)
        assert r.s.wait_wall(lambda: not ui(r.s)['speaking'], timeout=8)
        r.reply(READ, turn='t1')
        r.turn_end('t1', 'success')
        c.shot(r, 'home-reply-ready', view='home', headline='Reply ready', activity='idle',
               controls=lambda cs: 'reply' in cs)
        tap_ctl(r, 'reply')
        c.shot(r, 'reader-end', view='response', activity='idle')
        swipe(r.s, dy=150)
        c.shot(r, 'reader-scrolled-up', view='response', scroll=lambda s: s is not None and s >= 0)
        swipe(r.s, dx=100); r.s.run_for(0.35)
        swipe(r.s, dy=100)
        c.shot(r, 'controls-idle-finished', view='controls', controls=lambda cs: 'settings' in cs)
        swipe(r.s, dx=100); r.s.run_for(0.35)
        c.shot(r, 'home-last-task', view='home', activity='idle')
        r.s.type_text('draft the email to Ana')
        req = [m for m in r.s.sent if m.get('type') == 'text'][-1]['id']
        r.turn_start('t2', request=req)
        r.s.run_for(0.3)
        assert view(r) == 'home', ui(r.s)
        tap_ctl(r, 'stop')
        c.shot(r, 'home-stop-requested', view='home', headline='Stop requested')
        r.turn_end('t2', 'cancelled')
        c.shot(r, 'home-stopped', view='home', headline='Stopped', activity='idle')
        swipe(r.s, dy=100)
        c.shot(r, 'controls-after-stop', view='controls')
        swipe(r.s, dx=100); r.s.run_for(0.35)
        r.send('prompt', id='q1', title='Permission', text='Allow turning on the desk lamp?')
        c.shot(r, 'approval-short', 0.7, view='approval')
        tap_ctl(r, 'no')
        r.s.run_for(0.3)
        r.send('prompt', id='q2', title='Approval needed', text=APPROVAL)
        c.shot(r, 'approval-long-unread', 0.7, view='approval', controls=[])
        for _ in range(6):
            swipe(r.s, dy=-100)
            r.s.run_for(0.05)
        c.shot(r, 'approval-long-read-end', 0.1, view='approval', controls=['no', 'yes'])
        swipe(r.s, dy=100)
        c.shot(r, 'approval-long-read-back', 0.1, view='approval', controls=['no', 'yes'])
        tap_ctl(r, 'yes')
        r.s.run_for(0.3)
        r.s.type_text('fix the invites')
        req = [m for m in r.s.sent if m.get('type') == 'text'][-1]['id']
        r.turn_start('t3', request=req)
        r.reply(FAILED_TEXT, turn='t3')
        r.turn_end('t3', 'failure')
        r.s.run_for(0.3)
        to_home(r)
        c.shot(r, 'home-failed', view='home', activity='idle')
    finally:
        c.close(r)


def group_connection(c: Capture):
    r = c.make()
    try:
        r.turn_start('busy')
        r.s.set_network(False)
        r.s.run_for(0.3)
        assert r.s.status()['screen'] == 'offline', r.s.status()['screen']
        c.shot(r, 'offline-task-unknown', screen='offline')
        r.s.set_network(True)
        assert r.s.wait_screen('ready', timeout=10)
        r.s.run_for(0.5)
        to_home(r)
        c.shot(r, 'home-connection-lost', view='home')
        assert r.s.console('set server ws://127.0.0.1:9/gadget').startswith('@ok')
        assert r.s.wait_for(lambda: r.s.status()['phase'] in ('connecting', 'handshake'), timeout=5)
        r.s.run_for(2.5)
        c.shot(r, 'connecting-retry', screen='connecting', volatile=PORTRAIT)
        assert r.s.console('set server ws://127.0.0.1:%d/gadget' % r.hub.bound_port).startswith('@ok')
        for _ in range(100):
            if r.s.status()['screen'] == 'ready':
                break
            r.s.run_for(0.1)
        assert r.s.status()['screen'] == 'ready'
        r.send('error', code='auth_failed', message='Device token rejected')
        c.shot(r, 'setup-needed', 0.5, screen='error')
    finally:
        c.close(r)
    r = c.make()
    try:
        r.s.set_network(False)
        r.s.run_for(0.3)
        c.shot(r, 'offline-plain', screen='offline')
        r.s.set_network(True)
        assert r.s.wait_screen('ready', timeout=10)
        r.run(r.session.send_pairing('482913', 'hermes gadget pair 482913'))
        r.run(r.session.set_paired(False))
        assert r.s.wait_for(lambda: not r.s.status()['paired'], timeout=5)
        r.run(r.session.send_pairing('482913', 'hermes gadget pair 482913'))
        r.s.wait_for(lambda: r.s.status()['screen'] == 'pairing', timeout=5)
        r.s.run_for(0.4)
        c.shot(r, 'pairing', screen='pairing')
        r.run(r.session.set_paired(True))
        assert r.s.wait_screen('ready', timeout=5)
        r.s.run_for(0.3)
        hold_title(r)
        c.shot(r, 'settings-volume', 0.3, screen='settings', detail='Speaker volume')
        swipe(r.s, dy=100)
        c.shot(r, 'settings-brightness', 0.2, screen='settings', detail='Screen brightness')
        swipe(r.s, dy=100)
        c.shot(r, 'settings-talk-mode', 0.2, screen='settings', detail='Talk mode')
        to_row(r, 'Display check')
        tap(r.s, 233, 220)
        c.shot(r, 'settings-display-check', 0.2, screen='settings', detail='Display check')
        tap(r.s, 233, 220)
        to_row(r, 'Device information')
        c.shot(r, 'settings-info', 0.2, screen='settings', detail='Device information')
        to_row(r, 'Screen timeout')
        c.shot(r, 'settings-timeout', 0.2, screen='settings', detail='Screen timeout')
        to_row(r, 'Wi-Fi setup')
        c.shot(r, 'settings-wifi-row', 0.2, screen='settings', detail='Wi-Fi setup')
        tap(r.s, 233, 220)
        c.shot(r, 'wifi-setup', 0.3, screen='setup')
        swipe(r.s, dy=100)
        c.shot(r, 'wifi-setup-closed', 0.3, screen='ready')
    finally:
        c.close(r)


def group_recent(c: Capture):
    r = c.make()
    try:
        to_recent(r)
        c.shot(r, 'recent-empty', view='recent')
    finally:
        c.close(r)
    r = c.make()
    try:
        turn(r, 'one', SHORT)
        turn(r, 'two', FAILED_TEXT, 'failure')
        turn(r, 'three', 'Stopped while drafting the email to Ana.', 'cancelled')
        r.s.run_for(0.3)
        to_recent(r)
        c.shot(r, 'recent-3', view='recent')
        tap_ctl(r, 'work1')
        c.shot(r, 'result-failed', view='result')
        swipe(r.s, dx=100)
        c.shot(r, 'back-to-recent', view='recent')
    finally:
        c.close(r)
    r = c.make()
    try:
        for name, text, outcome in [('one', SHORT, 'success'), ('two', LONG, 'failure'),
                                    ('three', 'Stopped while drafting the email to Ana.', 'cancelled'),
                                    ('four', 'Thermostat set to 20 degrees for the evening.', 'success'),
                                    ('five', READ, 'success'),
                                    ('six', 'Groceries added: oat milk, lemons, basil.', 'success'),
                                    ('seven', 'Reminder saved for Friday 9 am: compost delivery.', 'success'),
                                    ('eight', '', 'success')]:
            turn(r, name, text, outcome)
        r.s.run_for(0.4)
        to_recent(r)
        c.shot(r, 'recent-8-page1', view='recent')
        tap_ctl(r, 'next')
        c.shot(r, 'recent-8-page2', view='recent')
        tap_ctl(r, 'next')
        c.shot(r, 'recent-8-page3', view='recent')
        tap_ctl(r, 'next')
        c.shot(r, 'recent-8-back-to-top', view='recent')
        tap_ctl(r, 'next')
        tap_ctl(r, 'work0')
        c.shot(r, 'result-long-top', view='result')
        swipe(r.s, dy=-150)
        c.shot(r, 'result-long-scrolled', view='result', scroll=lambda s: s and s > 0)
        swipe(r.s, dx=100)
        c.shot(r, 'back-recent', view='recent')
        swipe(r.s, dx=100)
        c.shot(r, 'back-controls', view='controls')
        swipe(r.s, dx=100)
        c.shot(r, 'back-home', view='home')
    finally:
        c.close(r)


GROUPS = {'home': group_home, 'connection': group_connection, 'recent': group_recent}


def transitions(c: Capture):
    """Mid-transition frames sampled on the device clock after each navigation."""
    from hermes_gadget import png
    tdir = c.out / 'transitions'
    tdir.mkdir(exist_ok=True)
    r = c.make()
    try:
        turn(r, 'one', SHORT)
        turn(r, 'two', READ)
        r.s.run_for(0.3)
        to_home(r)
        r.s.run_for(0.4)
        seqs = [('home-to-controls', lambda: swipe(r.s, dy=100)),
                ('controls-to-recent', lambda: tap_ctl(r, 'recent')),
                ('recent-to-result', lambda: tap_ctl(r, 'work0')),
                ('result-back-recent', lambda: swipe(r.s, dx=100)),
                ('recent-back-controls', lambda: swipe(r.s, dx=100)),
                ('controls-back-home', lambda: swipe(r.s, dx=100)),
                ('home-to-reader', lambda: swipe(r.s, dy=-100))]
        meta = []
        for name, act in seqs:
            t0 = r.s.now_ms()
            act()
            frames, want = [], [40, 80, 120, 160, 400]
            while want:
                r.s.run_for(0.01)
                t = r.s.now_ms() - t0
                if t >= want[0]:
                    want.pop(0)
                    frames.append((t, png.encode_png(r.s.rgb888(), W, W)))
            for i, (t, im) in enumerate(frames):
                p = tdir / f'{name}-{i}-{t}ms.png'
                p.write_bytes(im)
                mask(p)
            meta.append({'name': name, 'samples_ms': [t for t, _ in frames]})
        (tdir / 'transitions.json').write_text(json.dumps(meta, indent=1))
        sheet(tdir, sorted(p.stem for p in tdir.glob('*.png') if not p.stem.endswith('.masked')),
              name='transitions-sheet')
    finally:
        c.close(r)


def sheet(out: Path, names, cols=5, name=None):
    from PIL import Image, ImageDraw
    w, h = W // 2 + 10, W // 2 + 28
    rows = (len(names) + cols - 1) // cols
    S = Image.new('RGB', (cols * w + 10, rows * h + 10), (24, 24, 26))
    d = ImageDraw.Draw(S)
    for i, n in enumerate(names):
        p = out / f'{n}.masked.png'
        im = Image.open(p if p.exists() else out / f'{n}.png')
        x, y = 10 + (i % cols) * w, 10 + (i // cols) * h
        S.paste(im.resize((233, 233), Image.LANCZOS), (x, y))
        d.text((x, y + 236), n, fill=(200, 200, 200))
    S.save(out.parent / f'{name or "contact-sheet-" + out.name}.png')


# -- analysis -----------------------------------------------------------------------------------

def identical(a: Path, b: Path) -> int:
    key = lambda s: s.get('sha256_outside_volatile') or s['sha256']
    sa = {s['name']: key(s) for s in json.loads((a / 'shots.json').read_text())}
    sb = {s['name']: key(s) for s in json.loads((b / 'shots.json').read_text())}
    names = sorted(set(sa) | set(sb))
    diff = [n for n in names if sa.get(n) != sb.get(n)]
    print(json.dumps({'shots': len(names), 'identical': len(names) - len(diff), 'different': diff}, indent=1))
    return 1 if diff else 0


def bands(path):
    import numpy as np
    from PIL import Image
    a = np.asarray(Image.open(path).convert('L')).astype(int)
    lit = (a[:, 70:396] > 12).any(axis=1)
    out, y = [], 0
    while y < W:
        if lit[y]:
            s = y
            while y < W and lit[y]:
                y += 1
            out.append((s, y))
        else:
            y += 1
    return out


def gaps(dirs):
    names = sorted(p.name for p in dirs[0].glob('[0-9][0-9]-*.png') if 'masked' not in p.name)
    for n in names:
        row = []
        for d in dirs:
            p = d / n
            if p.exists():
                b = [x for x in bands(p) if x[1] - x[0] > 6]
                row.append([b[i + 1][0] - b[i][1] for i in range(len(b) - 1) if b[i + 1][0] - b[i][1] < 12])
            else:
                row.append(None)
        if any(row):
            print(n.ljust(34), ' | '.join(str(r) if r is not None else '-' for r in row))


def compare(before: Path, after: Path, out: Path, names):
    from PIL import Image, ImageDraw
    if not names:
        names = sorted(p.stem for p in after.glob('[0-9][0-9]-*.png') if '.masked' not in p.name)
    S, PAD, LAB = 300, 16, 26
    rows = (len(names) + 1) // 2
    sheet_ = Image.new('RGB', (4 * (S + PAD) + PAD, rows * (S + LAB + PAD) + PAD), (18, 18, 20))
    d = ImageDraw.Draw(sheet_)
    m = Image.new('L', (S, S), 0)
    ImageDraw.Draw(m).ellipse((0, 0, S - 1, S - 1), fill=255)

    def find(src, name):
        exact = src / f'{name}.png'
        if exact.exists():
            return exact
        hits = sorted(p for p in src.glob(f'[0-9][0-9]-{name.split("-", 1)[-1]}.png'))
        return hits[0] if hits else None

    for i, name in enumerate(names):
        col, row = i % 2, i // 2
        for j, (label, src) in enumerate((('before', before), ('after', after))):
            x = PAD + (col * 2 + j) * (S + PAD)
            y = PAD + row * (S + LAB + PAD)
            p = find(src, name)
            if p is None:
                d.text((x + 4, y + 6), f'{name}  {label}: (none)', fill=(130, 130, 136))
                continue
            img = Image.open(p).convert('RGB').resize((S, S), Image.LANCZOS)
            disc = Image.new('RGB', (S, S), (18, 18, 20))
            disc.paste(img, (0, 0), m)
            sheet_.paste(disc, (x, y + LAB))
            d.ellipse((x, y + LAB, x + S - 1, y + LAB + S - 1), outline=(60, 60, 66))
            d.text((x + 4, y + 6), f'{name}  {label}', fill=(200, 200, 205) if j else (130, 130, 136))
    sheet_.save(out)
    print(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    sub = ap.add_subparsers(dest='cmd', required=True)
    cp = sub.add_parser('capture')
    cp.add_argument('out')
    cp.add_argument('--library')
    cp.add_argument('--only', default='')
    cp.add_argument('--transitions', action='store_true')
    ip = sub.add_parser('identical')
    ip.add_argument('a')
    ip.add_argument('b')
    mp = sub.add_parser('compare')
    mp.add_argument('before')
    mp.add_argument('after')
    mp.add_argument('png')
    mp.add_argument('shots', nargs='*')
    gp = sub.add_parser('gaps')
    gp.add_argument('dirs', nargs='+')
    a = ap.parse_args(argv)
    if a.cmd == 'identical':
        return identical(Path(a.a), Path(a.b))
    if a.cmd == 'compare':
        compare(Path(a.before), Path(a.after), Path(a.png), a.shots)
        return 0
    if a.cmd == 'gaps':
        gaps([Path(d) for d in a.dirs])
        return 0
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    c = Capture(out, a.library)
    chosen = [g for g in a.only.split(',') if g] or list(GROUPS)
    try:
        for g in chosen:
            GROUPS[g](c)
        if a.transitions:
            transitions(c)
    finally:
        for r in list(c.open):
            c.close(r)
        (out / 'shots.json').write_text(json.dumps(c.shots, indent=1))
    sheet(out, [s['name'] for s in c.shots])
    print(f'{len(c.shots)} shots, all states reached, no repeated neighbour')
    return 0


if __name__ == '__main__':
    sys.exit(main())
