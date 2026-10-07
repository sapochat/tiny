#include "hg/touch.hpp"

#include <cstdlib>

namespace hg {

void TouchGestures::tick(uint32_t now_ms) {
  if (state_ != State::Pending && state_ != State::Settings) return;
  if (epoch_ != app_.touch_epoch()) {
    if (state_ != State::Talk) state_ = State::Ignored;
    return;
  }
  if (state_ == State::Settings) {
    // A title contact cannot carry idle navigation intent into new activity.
    // Consume it as soon as eligibility/ownership changes, not just at timeout.
    if (app_.touch_view() != owner_ || !app_.settings_title_hit(x0_, y0_)) {
      state_ = State::Ignored;
      return;
    }
    if (!moved_ && now_ms - t0_ >= 1000) {
      state_ = State::Ignored;
      app_.open_settings();
    }
  }
  // Push-to-talk starts only from Home's open area or an explicit Talk target. Reading
  // stays purely navigational, so a patient reader's still finger never records.
  const bool talk_target = (owner_ == TouchView::Home && control_ == TouchControl::None) ||
                           (owner_ == TouchView::Response && control_ == TouchControl::Talk);
  if (state_ == State::Pending && !moved_ && talk_target && app_.touch_view() == owner_ &&
      app_.control_revision(control_) == revision_ && now_ms - t0_ >= cfg_.hold_ms) {
    state_ = State::Talk;
    app_.on_touch_talk(true);
  }
}

void TouchGestures::update(bool touching, int x, int y, uint32_t now_ms) {
  if (!touching) {
    if (state_ == State::Talk) app_.on_touch_talk(false);  // normal push-to-talk release only
    else if (state_ == State::Pending && !moved_ && epoch_ == app_.touch_epoch() &&
             app_.control_revision(control_) == revision_)
      app_.touch_tap(owner_, control_, t0_);
    state_ = State::Idle;
    return;
  }
  if (state_ == State::Idle) {
    if (app_.wake_display()) { state_ = State::Ignored; return; }
    owner_ = app_.touch_view();
    epoch_ = app_.touch_epoch();
    control_ = app_.touch_hit(x, y);
    revision_ = app_.control_revision(control_);
    moved_ = false;
    // While recording, only a rendered Discard/Finish target can be tapped; nothing navigates.
    const bool capture_control = control_ == TouchControl::Discard || control_ == TouchControl::Finish;
    state_ = owner_ == TouchView::Recording ? (capture_control ? State::Pending : State::Ignored) :
             app_.settings_title_hit(x, y) ? State::Settings : State::Pending;
    x0_ = x; y0_ = y; t0_ = now_ms;
    return;
  }
  if (epoch_ != app_.touch_epoch() && state_ != State::Talk) { state_ = State::Ignored; return; }
  const int dx = x - x0_, dy = y - y0_;
  if (std::abs(dx) > cfg_.slop_px || std::abs(dy) > cfg_.slop_px) moved_ = true;
  if (state_ == State::Talk) return;  // movement while recording never submits/discards
  if (state_ != State::Pending && state_ != State::Settings) return;
  // Require a clear dominant axis. Ambiguous diagonals cannot become taps/holds.
  bool vertical = std::abs(dy) >= cfg_.swipe_px && std::abs(dy) * 2 > std::abs(dx) * 3;
  bool horizontal = std::abs(dx) >= cfg_.swipe_px && std::abs(dx) * 2 > std::abs(dy) * 3;
  if (vertical || horizontal) {
    state_ = State::Swipe;  // consume once, including no-op/boundary gestures
    app_.touch_swipe(owner_, horizontal ? dx : 0, vertical ? dy : 0, control_);
  } else if (!moved_) tick(now_ms);
}

}  // namespace hg
