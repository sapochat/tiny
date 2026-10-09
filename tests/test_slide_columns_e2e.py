"""Slide frames send only the columns that are lit before or after the frame.

Failure modes this guards (Ui::compose_motion / Ui::flush_bands, firmware/core/src/ui.cpp):
- a narrowed slide frame leaves a ghost of the previous view or of the unshifted
  destination on the glass (the simulator panel copy receives only flushed rectangles)
- a column band misses the trailing edge of content moving sideways or up/down
- slides keep sending whole 466px rows, so the device pays for black glass
"""
from test_interaction_surface_e2e import ix, ix_run, framebuffer  # noqa: F401
from test_design_pass2_e2e import raw_controls
from test_flush_window_e2e import assert_glass_current, watch, per_flush

FULL = 466 * 466


def _slide_frames(s, what):
    log, start, restore = watch(s)
    for _ in range(30):
        s.run_for(.01)
        assert_glass_current(s, what)
    restore()
    return per_flush(log, start)


def test_slides_both_ways_leave_no_stale_pixels_and_send_less_than_whole_rows(ix):
    s = ix.s
    s.run_for(.3)
    assert_glass_current(s, 'Home before the slide')
    raw_controls(s)                       # Home -> Quick controls (vertical)
    to_controls = _slide_frames(s, 'slide to controls')
    assert s.status()['ui']['view'] == 'controls'
    s.touch(True, 233, 60)                # Home target at the top of Controls
    s.touch(False)
    to_home = _slide_frames(s, 'slide back to Home')
    assert s.status()['ui']['view'] == 'home'
    for name, flushes in (('controls', to_controls), ('home', to_home)):
        sent = sum(px for _, _, px in flushes)
        rows = sum(y1 - y0 for y0, y1, _ in flushes)
        assert flushes, f'slide to {name} sent nothing'
        # Whole-row flushing would send rows * 466 px; content inside the circle is narrower.
        assert sent < rows * 466 * 0.85, f'slide to {name} sent {sent} px for {rows} rows (whole rows: {rows * 466})'
    s.run_for(.5)
    assert_glass_current(s, 'settled on Home')
