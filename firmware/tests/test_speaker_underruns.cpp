#include <cstdint>

#include "check.hpp"
#include "speaker_underruns.hpp"

TEST("speaker underruns: each gap while the stream is open is counted, timed and kept as longest") {
  hg::SpeakerUnderruns u;
  u.resumed(0);  // the first frame: nothing was missing yet
  u.ran_dry(100);
  u.ran_dry(120);  // still the same gap, polled again
  u.resumed(276);
  u.ran_dry(500);
  u.resumed(536);
  const auto t = u.finish();
  CHECK_EQ(t.count, 2u);
  CHECK_EQ(t.total_ms, 212u);
  CHECK_EQ(t.longest_ms, 176u);
}

TEST("speaker underruns: the silence after the last frame is the end of the reply, not a gap") {
  hg::SpeakerUnderruns u;
  u.resumed(0);
  u.ran_dry(7000);  // the stream is still open, but the server has nothing more to send
  const auto t = u.finish();
  CHECK_EQ(t.count, 0u);
  CHECK_EQ(t.total_ms, 0u);
}

TEST("speaker underruns: each stream starts from zero, after an end or an abort") {
  hg::SpeakerUnderruns u;
  u.ran_dry(10);
  u.resumed(60);
  CHECK_EQ(u.finish().count, 1u);
  u.ran_dry(100);  // an abort cut this one short
  u.finish();
  u.resumed(5000);  // the next stream's first frame
  const auto t = u.finish();
  CHECK_EQ(t.count, 0u);
  CHECK_EQ(t.longest_ms, 0u);
}

TEST("speaker underruns: the millisecond clock wrapping inside a gap still gives its length") {
  hg::SpeakerUnderruns u;
  u.ran_dry(0xFFFFFFF0u);
  u.resumed(0x20u);
  CHECK_EQ(u.finish().total_ms, 0x30u);
}
