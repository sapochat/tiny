// Frame-free stand-in for expression_assets.hpp, for boards that never draw the expression
// video (everything but the 466px round companion; CONFIG_HG_EXPRESSION_PACK=n). Same clip
// table, names and frame geometry as the generated pack, no frame bytes: Ui only decodes a
// frame when round_companion() is true, which these boards never are. A decode here would
// fail closed to a black frame. tests/test_expression_reclaim.py keeps this in step.
#pragma once
#include <cstdint>
namespace hg::expression {
constexpr int size=96, count=size*size, ticks_per_frame=2;
struct Clip { uint16_t first, count; };
inline constexpr uint8_t data[] = {0};
inline constexpr uint32_t offsets[351] = {};
inline constexpr Clip clips[] = {
{0,25},{25,25},{50,25},{75,25},{100,25},{125,25},{150,25},{175,25},{200,25},{225,25},{250,25},{275,25},{300,25},{325,25}
};
inline constexpr const char* names[] = {
"idle","listening","thinking","thinking-got-it","speaking","reply-ready","reply-ready-settle","asking","asking-answered","alert","alert-settle","fall-asleep","sleep","wake"
};
}
