"""display.bench: the host can measure slides and full redraws on the device itself.

Failure modes this guards (firmware/core/src/app_bench.cpp):
- the bench is not offered, or is offered on boards without the round companion
- a slide in the bench is not a real slide (0-1 frames, no distinct in-between pixels)
- the bench leaves the device somewhere other than where the user was, or mid-transition
- the bench runs while the device is busy (recording) instead of refusing
"""
import numpy as np

from test_interaction_surface_e2e import ix, ix_run, framebuffer  # noqa: F401


def _bench(r, timeout=10):
    import asyncio
    session = r.session
    fut = asyncio.run_coroutine_threadsafe(session.invoke_action('display.bench', {}, timeout=timeout), r.lt.loop)
    assert r.s.wait_for(fut.done, timeout=timeout + 2), 'bench did not answer'
    return fut


def test_bench_reports_real_slides_and_restores_home(ix):
    r, s = ix, ix.s
    assert 'display.bench' in r.session.action_names()
    before = framebuffer(s).copy()
    distinct = set()
    original = s.display_flush

    def flush(y0, y1):
        distinct.add(framebuffer(s).tobytes())
        original(y0, y1)
    s.display_flush = flush
    result = _bench(r).result()
    s.display_flush = original
    # Recent joins the sequence only when the host offers work (this fixture host does).
    assert [x['to'] for x in result['slides']] in (['controls', 'home'], ['controls', 'home', 'recent', 'home'])
    for slide in result['slides']:
        assert slide['frames'] >= 3, slide
        assert len(slide['frame_ms']) == slide['frames']
        assert 200 <= slide['ms'] < 1000, slide
    assert result['min_frames'] == min(x['frames'] for x in result['slides'])
    assert len(result['redraw_ms']) == 5 and result['redraw_max_ms'] == max(result['redraw_ms'])
    assert len(distinct) >= 6, 'bench slides drew too few distinct frames'
    s.step()
    assert s.status()['phase'] == 'online'
    assert not s.status()['ui']['transition']['active']
    after = framebuffer(s)
    # The face animates on its own clock; everything outside the portrait must be Home again.
    still = np.ones((466, 466), bool)
    still[96:288, 137:329] = False
    assert np.array_equal(after[still], before[still]), 'bench did not land back on the same Home render'
    sensors = {}
    assert s.wait_for(lambda: sensors.update(r.session.sensors) or 'perf_bench_min_frames' in sensors, timeout=5)
    assert sensors['perf_bench_min_frames'] == result['min_frames']


def test_bench_refuses_while_recording(ix):
    r, s = ix, ix.s
    s.touch(True, 233, 220)  # hold-to-talk on Home
    s.run_for(0.5)
    assert s.status()['ui']['activity'] == 'recording'
    fut = _bench(r)
    assert fut.exception() is not None and 'busy' in str(fut.exception())
    assert s.status()['ui']['activity'] == 'recording', 'a refused bench must not disturb the capture'
    s.touch(False)
