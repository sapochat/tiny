// State-aware touch navigation shared by firmware and simulator. A contact
// belongs to its starting view; movement never synthesizes Cancel or a decision.
#pragma once

#include <cstdint>

#include "hg/app.hpp"

namespace hg {

class TouchGestures {
 public:
  struct Config {
    uint32_t hold_ms = 120;  // a still finger becomes TALK after this long
    int slop_px = 18;        // movement allowed before a touch stops being a hold or tap
    int swipe_px = 60;       // downward travel that makes a swipe
    bool swipe_cancel = true;
  };

  explicit TouchGestures(App& app) : app_(app) {}
  TouchGestures(App& app, Config config) : app_(app), cfg_(config) {}

  void set_swipe_cancel(bool on) { cfg_.swipe_cancel = on; }

  // Report the touch state. Call for every controller sample and when the
  // finger lifts (`touching` false; x and y are then ignored).
  void update(bool touching, int x, int y, uint32_t now_ms);
  // Promotes a still finger to TALK even when the controller sends no new
  // samples. Call regularly (every app tick is fine).
  void tick(uint32_t now_ms);

 private:
  enum class State : uint8_t { Idle, Pending, Settings, Talk, Swipe, Ignored };

  App& app_;
  Config cfg_;
  State state_ = State::Idle;
  int x0_ = 0, y0_ = 0;
  uint32_t t0_ = 0;
  TouchView owner_ = TouchView::Other;
  TouchControl control_ = TouchControl::None;
  uint32_t epoch_ = 0, revision_ = 0;  // view epoch and the touched control's target revision
  bool moved_ = false;
};

}  // namespace hg
