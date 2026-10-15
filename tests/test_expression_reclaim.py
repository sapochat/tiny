"""R-01b: boards that never draw the expression video build without its frames.

Only the 466px round companion (``Ui::round_companion()``: a round 466x466 panel, which on
ESP32 is the Waveshare AMOLED-1.75 and 1.75C) decodes and draws the expression pack.
Every other board builds ``Ui::update_expression``/``draw_expression`` but never calls
them, and ``Ui::expression_name`` reports "legacy" there. Those boards therefore compile
against ``expression_stub.hpp``: the same clip table, names and frame geometry, with no
frame bytes. Failure modes covered:

- the stub's metadata drifts from the generated pack (clip timing or names would differ
  if a round board were ever built against it);
- the stub carries frame data (no saving) or the round boards lose the pack;
- the build files stop selecting the pack for the round boards only;
- the generated assets are edited instead of left untouched.

Rendered-pixel identity is checked separately: round captures against the unchanged
library, and non-round simulator boards against a library built with
``-DHG_EXPRESSION_PACK=OFF`` (artifacts/improve/r01b).
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CORE = REPO / "firmware" / "core"
PACK = CORE / "include" / "hg" / "expression_assets.hpp"
STUB = CORE / "include" / "hg" / "expression_stub.hpp"
KCONFIG = REPO / "firmware" / "esp32" / "main" / "Kconfig.projbuild"
# The approved pack as committed before R-01b; it must not be regenerated or edited here.
PACK_SHA256 = "ec64b3d250108eef5666950cc86c9565b48fad19fac4de3edb5a77819a9b4de6"


def _meta(text: str):
    geometry = re.search(r"constexpr int size=(\d+), count=size\*size, ticks_per_frame=(\d+);", text)
    clips = re.search(r"Clip clips\[\] = \{\s*(.*?)\s*\};", text, re.S)
    names = re.search(r"names\[\] = \{\s*(.*?)\s*\};", text, re.S)
    assert geometry and clips and names, "metadata missing"
    return geometry.groups(), re.sub(r"\s", "", clips.group(1)), re.sub(r"\s", "", names.group(1))


def _offsets(text: str) -> int:
    clips = re.findall(r"\{(\d+),(\d+)\}", re.search(r"Clip clips\[\] = \{(.*?)\};", text, re.S).group(1))
    return max(int(a) + int(b) for a, b in clips) + 1


def test_stub_has_the_pack_metadata_without_frames():
    assert STUB.exists(), "no frame-free expression stand-in"
    stub, pack = STUB.read_text(), PACK.read_text()
    assert _meta(stub) == _meta(pack)
    # The offsets table keeps its length (every frame decodes to an empty, fail-closed frame).
    assert re.search(r"offsets\[%d\]\s*=\s*\{\s*\}" % _offsets(pack), stub), "offsets length differs"
    data = re.search(r"uint8_t data\[\]\s*=\s*\{(.*?)\};", stub, re.S)
    assert data and len(data.group(1).split(",")) <= 1, "the stub must carry no frame bytes"
    assert len(stub) < 4000


def test_round_boards_keep_the_pack_and_other_boards_leave_it_out():
    k = KCONFIG.read_text()
    block = re.search(r"config HG_EXPRESSION_PACK\n(.*?)(?:\n\n|\n    (?:config|choice|menu|endmenu))", k, re.S)
    assert block, "no HG_EXPRESSION_PACK option"
    text = block.group(1)
    assert "default y if HG_BOARD_AMOLED_175 || HG_BOARD_AMOLED_175C" in text
    assert re.search(r"^\s+default n$", text, re.M), "every other board leaves the pack out"
    cmake = (CORE / "CMakeLists.txt").read_text()
    assert "CONFIG_HG_EXPRESSION_PACK" in cmake and "HG_EXPRESSION_PACK" in cmake
    ui = (CORE / "src" / "ui.cpp").read_text()
    assert "expression_stub.hpp" in ui and "expression_assets.hpp" in ui


def test_generated_assets_are_untouched():
    assert hashlib.sha256(PACK.read_bytes()).hexdigest() == PACK_SHA256
