// The mascot's sizes and feature anchors without its pixels, for builds whose screens
// never draw the 1-bit mascot (the 466px round companion draws the expression video).
// The renderer still sizes its hero layout from these entries, so they must match the
// generated mascot_data.cpp exactly; tests/test_mascot_reclaim.py checks that they do.
// Selected by CONFIG_HG_LEGACY_MASCOT=n (ESP-IDF) or -DHG_LEGACY_MASCOT=OFF (host).
#include "hg/mascot.hpp"

namespace hg::mascot {
namespace {

const Bitmap kBitmaps[] = {
    {64, Frame::Idle, nullptr},
    {64, Frame::Blink, nullptr},
    {64, Frame::Talk, nullptr},
    {96, Frame::Idle, nullptr},
    {96, Frame::Blink, nullptr},
    {96, Frame::Talk, nullptr},
    {144, Frame::Idle, nullptr},
    {144, Frame::Blink, nullptr},
    {144, Frame::Talk, nullptr},
    {192, Frame::Idle, nullptr},
    {192, Frame::Blink, nullptr},
    {192, Frame::Talk, nullptr},
};

const Anchors kAnchors = {{607, 293}, {262, 620}, {801, 107}, 396, 508, 586, 649};

}  // namespace

const Anchors& anchors() { return kAnchors; }

const Bitmap* pick(int max_size, Frame frame) {
  const Bitmap* best = nullptr;
  for (const auto& b : kBitmaps) {
    if (b.frame != frame) continue;
    if (b.size <= max_size && (!best || b.size > best->size)) best = &b;
  }
  if (best) return best;
  for (const auto& b : kBitmaps) {
    if (b.frame == frame && (!best || b.size < best->size)) best = &b;
  }
  return best;
}

}  // namespace hg::mascot
