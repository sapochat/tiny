"""Narrow flush windows: idle and press updates send only the columns they touch.

Failure modes this guards (Ui::render_companion -> Display::flush_rect, work-queue item 3):
- a narrowed flush misses pixels that changed, leaving stale content on the glass
  (the simulator's panel copy receives only flushed rectangles, like the CO5300)
- face, press and recording updates still send whole 466px rows
- full redraws and slides stop reaching the panel after the change
"""
import numpy as np

from test_interaction_surface_e2e import ix, ix_run, framebuffer  # noqa: F401
from test_design_pass2_e2e import raw_controls


def panel(s):
    raw = s.device.panel_rows()
    assert raw, 'simulator library predates the panel copy; rebuild it'
    return np.frombuffer(raw, dtype='<u2').reshape(466, 466)


def watch(s):
    """Record (rows, pixels) for every flush from now on."""
    log = []
    original = s.display_flush

    def flush(y0, y1):
        original(y0, y1)
        log.append((y0, y1, s.device.flushed_px()))
    s.display_flush = flush
    start = s.device.flushed_px()
    return log, start, lambda: setattr(s, 'display_flush', original)


def per_flush(log, start):
    out, prev = [], start
    for y0, y1, total in log:
        out.append((y0, y1, total - prev))
        prev = total
    return out


def assert_glass_current(s, what):
    fb, shown = framebuffer(s), panel(s)
    stale = np.argwhere(fb != shown)
    assert not len(stale), f'{what}: {len(stale)} changed pixels never reached the panel, first {stale[:3].tolist()}'


def test_idle_face_updates_send_only_the_portrait(ix):
    s = ix.s
    s.run_for(.3)
    assert_glass_current(s, 'Home after connect')
    log, start, restore = watch(s)
    for _ in range(40):  # ~4 s of idle expression playback
        s.run_for(.1)
        assert_glass_current(s, 'idle face update')
    restore()
    flushes = per_flush(log, start)
    assert flushes, 'the face never animated on Home'
    for y0, y1, px in flushes:
        rows = y1 - y0
        assert rows <= 192, (y0, y1)
        # The portrait is 192 px wide inside 466 px rows.
        assert px <= rows * 192, f'face update sent {px} px for {rows} rows (whole rows would be {rows * 466})'


def test_press_highlight_sends_only_the_target(ix):
    r, s = ix, ix.s
    raw_controls(s)
    s.run_for(.5)
    assert s.status()['ui']['view'] == 'controls'
    assert_glass_current(s, 'Controls landing')
    x, y, w, h = s.status()['ui']['controls']['settings']
    log, start, restore = watch(s)
    s.touch(True, x + w // 2, y + h // 2)
    s.step()
    assert s.status()['ui']['pressed'] == 'settings'
    assert_glass_current(s, 'press highlight')
    pressed_flushes = len(log)   # judge the press itself; sliding off a narrow pill can become a swipe
    # Slide off the target: the highlight clears, again through a narrow flush.
    s.touch(True, x + w // 2 + 60, y + h // 2)
    s.step()
    assert_glass_current(s, 'press cleared')
    s.touch(False)
    s.run_for(.5)
    assert_glass_current(s, 'after release')
    restore()
    narrow = [f for f in per_flush(log, start)[:pressed_flushes] if f[0] == y and f[1] == y + h]
    assert narrow, 'no flush covered just the pressed target'
    for y0, y1, px in narrow:
        assert px <= (y1 - y0) * (w + 2), f'press flush sent {px} px for a {w}px wide target'


def test_full_redraws_and_slides_still_reach_the_glass(ix):
    s = ix.s
    raw_controls(s)
    for _ in range(30):
        s.run_for(.01)
        assert_glass_current(s, 'slide frame')
    s.touch(True, 233, 60)   # Home target at the top of Controls
    s.touch(False)
    s.run_for(.6)
    assert s.status()['ui']['view'] == 'home'
    assert_glass_current(s, 'back on Home')
    s.press('talk'); s.step(); s.run_for(.3)
    assert s.status()['ui']['view'] == 'recording'
    assert_glass_current(s, 'recording')
    s.tap('cancel'); s.release('talk'); s.run_for(.6)
    assert_glass_current(s, 'after cancel')
