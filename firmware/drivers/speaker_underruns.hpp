// Counts the times the speaker ran out of audio in the middle of a stream, apart
// from FreeRTOS so it can be tested on the host (port_codec.cpp, port_audio.cpp).
// A gap is the time the speaker task found its queue empty while the stream was
// still open; it ends when audio arrives again. Stretches before the first frame
// and after the stream ended are not gaps. The I2S DMA ring still holds tens of
// milliseconds when the queue empties, so the shortest gaps may not be audible.
#pragma once
#include <cstdint>

namespace hg {

class SpeakerUnderruns {
 public:
  struct Totals {
    uint32_t count = 0, total_ms = 0, longest_ms = 0;
  };

  // The queue was empty and the stream is still open.
  void ran_dry(uint32_t now) {
    if (!dry_) {
      dry_ = true;
      dry_at_ = now;
    }
  }
  // Audio was taken from the queue: a gap in progress ends here.
  void resumed(uint32_t now) {
    if (!dry_) return;
    dry_ = false;
    const uint32_t gap = now - dry_at_;
    ++totals_.count;
    totals_.total_ms += gap;
    if (gap > totals_.longest_ms) totals_.longest_ms = gap;
  }
  // The stream ended or was aborted: its totals, and a clean slate for the next one.
  // A gap still open is the end of the reply, not an underrun.
  Totals finish() {
    const Totals t = totals_;
    totals_ = {};
    dry_ = false;
    return t;
  }

 private:
  Totals totals_;
  bool dry_ = false;
  uint32_t dry_at_ = 0;
};

}  // namespace hg
