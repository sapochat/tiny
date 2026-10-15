"""R-01: the round companion build ships without the legacy mascot bitmaps.

The 466px round boards draw the expression video, never the 1-bit mascot, but the
renderer still sizes its hero layout with ``mascot::pick`` and places effects with
``mascot::anchors``. The round build therefore links ``mascot_stub.cpp``: the same sizes
and anchors as ``mascot_data.cpp`` with no pixel data. Failure modes covered:

- the stub drifts from the generated data (a different hero size or anchor would move
  pixels on the round board);
- the round board configuration keeps the 27 KB mascot, or a legacy board loses it;
- the build files stop selecting the stub for the round boards only.

Rendered-pixel identity of every round state is checked by the capture harness against a
simulator library built with ``-DHG_LEGACY_MASCOT=OFF`` (artifacts/improve/r01).
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CORE = REPO / "firmware" / "core"
DATA = CORE / "src" / "mascot_data.cpp"
STUB = CORE / "src" / "mascot_stub.cpp"
KCONFIG = REPO / "firmware" / "esp32" / "main" / "Kconfig.projbuild"


def _table(text: str):
    sizes = re.findall(r"\{(\d+), Frame::(\w+), (?:k\w+|nullptr)\}", text)
    found = re.search(r"const Anchors kAnchors = (\{.*?\});", text)
    assert found, "no anchors"
    anchors = found.group(1)
    return sorted((int(s), f) for s, f in sizes), anchors


def test_stub_has_the_generated_sizes_and_anchors_without_pixels():
    assert STUB.exists(), "no size-only mascot for the round build"
    stub = STUB.read_text()
    assert _table(stub) == _table(DATA.read_text())
    assert "0x" not in stub and "const uint8_t" not in stub, "the stub must carry no bitmap data"
    # pick() must choose exactly as the generated one does.
    picks = [re.search(r"const Bitmap\* pick\(.*?\n\}\n", t, re.S) for t in (stub, DATA.read_text())]
    assert all(picks) and picks[0].group(0) == picks[1].group(0)


def test_round_boards_select_the_stub_and_legacy_boards_keep_the_mascot():
    k = KCONFIG.read_text()
    block = re.search(r"config HG_LEGACY_MASCOT\n(.*?)(?:\n\n|\n    (?:config|choice|menu|endmenu))", k, re.S)
    assert block, "no HG_LEGACY_MASCOT option"
    text = block.group(1)
    assert "default n if HG_BOARD_AMOLED_175 || HG_BOARD_AMOLED_175C" in text
    assert re.search(r"^\s+default y$", text, re.M), "every other board keeps the mascot"
    cmake = (CORE / "CMakeLists.txt").read_text()
    assert "mascot_stub.cpp" in cmake and "CONFIG_HG_LEGACY_MASCOT" in cmake and "HG_LEGACY_MASCOT" in cmake

