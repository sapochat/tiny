"""Slides are shifted copies of one destination render, masked to the round glass.

Failure modes this guards (cached-frame motion, firmware/core/src/ui.cpp render_motion):
- an in-between frame is not the destination shifted (stale cache, wrong offset sign)
- pixels outside the 466px circle light up while moving
- a flush range misses rows that changed (ghost of the previous view left on glass)
- the landing frame differs from a static render of the same view
"""
import numpy as np

from test_interaction_surface_e2e import ix, ix_run, framebuffer  # noqa: F401
from test_design_pass2_e2e import raw_controls

Y, X = np.mgrid[0:466, 0:466]
OUTSIDE = (X - 233) ** 2 + (Y - 233) ** 2 > 233 * 233


def test_slide_frames_are_masked_shifts_and_flush_every_change(ix):
    s = ix.s
    shown = framebuffer(s).copy()   # what the glass shows, updated only by flushes
    panel = {'rows': shown}
    original = s.display_flush

    def flush(y0, y1):
        panel['rows'][y0:y1] = framebuffer(s)[y0:y1]
        original(y0, y1)
    s.display_flush = flush
    raw_controls(s)
    frames = []
    for _ in range(30):
        s.run_for(.01)
        fb = framebuffer(s).copy()
        assert not fb[OUTSIDE].any(), 'lit pixel outside the round glass mid-slide'
        assert np.array_equal(panel['rows'], fb), 'a changed row was never flushed'
        frames.append(fb)
    final = frames[-1]
    s.console('set volume 71'); s.step()
    s.console('set volume 70'); s.step()
    assert np.array_equal(final, framebuffer(s)), 'landing differs from static render'
    moving = [f for f in frames if not np.array_equal(f, final)]
    assert len(moving) >= 3, 'slide produced too few distinct frames'
    # Every in-between frame is the final frame shifted vertically and re-masked.
    for f in moving:
        ok = False
        for dy in range(-32, 33):
            shifted = np.zeros_like(final)
            if dy >= 0:
                shifted[dy:] = final[:466 - dy]
            else:
                shifted[:466 + dy] = final[-dy:]
            shifted[OUTSIDE] = 0
            if np.array_equal(shifted, f):
                ok = True
                break
        assert ok, 'in-between frame is not a shifted copy of the destination'
