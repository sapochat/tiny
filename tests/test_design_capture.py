"""tools/design_capture.py: the capture harness must refuse mislabelled shots.

Failure modes covered (each has silently produced a wrong contact sheet before):
- a shot is labelled with a state the device is not in (a swipe that did not land, a
  request id that turn attribution rejected);
- a shot repeats its neighbour's framebuffer, so two "different" states look identical;
- two runs of the same library differ, so a byte-identity claim would mean nothing.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from conftest import requires_sim

pytestmark = requires_sim
REPO = Path(__file__).resolve().parents[1]


def _tool():
    spec = importlib.util.spec_from_file_location('design_capture', REPO / 'tools' / 'design_capture.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules['design_capture'] = module
    spec.loader.exec_module(module)
    return module


def test_a_shot_in_the_wrong_state_or_repeating_its_neighbour_fails(tmp_path):
    dc = _tool()
    c = dc.Capture(tmp_path / 'shots', None)
    c.out.mkdir()
    r = c.make()
    try:
        c.shot(r, 'home', 0.3, view='home')
        with pytest.raises(AssertionError, match='expected view'):
            c.shot(r, 'mislabelled', 0.1, view='controls')
        # Quick controls have no animated portrait, so a second shot repeats the first.
        dc.swipe(r.s, dy=100)
        c.shot(r, 'controls', 0.4, view='controls')
        with pytest.raises(AssertionError, match='identical framebuffer'):
            c.shot(r, 'repeat', 0.1, view='controls')
        c.shot(r, 'repeat-allowed', 0.1, same_ok=True, view='controls')
    finally:
        c.close(r)
    assert [s['name'] for s in c.shots] == ['00-home', '01-controls', '02-repeat-allowed']
    assert (tmp_path / 'shots' / '01-controls.masked.png').exists()


def test_two_runs_of_one_library_are_byte_identical(tmp_path):
    dc = _tool()
    runs = []
    for i in range(2):
        out = tmp_path / f'run{i}'
        assert dc.main(['capture', str(out), '--only', 'recent']) == 0
        runs.append(out)
    assert dc.identical(*runs) == 0
    shots = json.loads((runs[0] / 'shots.json').read_text())
    h = {s['name'].split('-', 1)[1]: s['sha256'] for s in shots}
    assert len(shots) == 13
    # Returning to a view renders it exactly as it was; every other state is distinct.
    assert h['back-to-recent'] == h['recent-3'] and h['recent-8-back-to-top'] == h['recent-8-page1']
    assert h['back-recent'] == h['recent-8-page2']
    assert len(set(h.values())) == 10
