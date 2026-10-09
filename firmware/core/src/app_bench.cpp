// display.bench: an on-device measurement of the round companion's slides and full redraws.
// It runs the same render path a swipe does (navigation change, then frames until the slide
// lands) without touching activity state, and only when the device is idle.
#include "hg/app.hpp"

#include <algorithm>

namespace hg {

void App::add_display_bench() {
  if (!ui_ || !ui_->round_companion() || !profile_.touch_screen) return;
  Action bench;
  bench.name = "display.bench";
  bench.description = "Measure screen slide frames and full-redraw time on the device (idle only; "
                      "the screen moves for about two seconds).";
  bench.params.set("type", "object").set("properties", json::Value::object());
  bench.handler = [this](const json::Value&, json::Value& result, std::string& error) {
    return run_display_bench(result, error);
  };
  add_action(std::move(bench));
}

bool App::run_display_bench(json::Value& result, std::string& error) {
  if (!ui_ || !can_talk() || mode_ != Mode::Idle || speaking() || prompt_showing() || ota_busy() ||
      ota_ == Ota::Restarting || settings_open() || wifi_setup_open() || overlay_ != Overlay::None ||
      !fatal_.empty() || talk_held_ || cancel_held_ || display_sleeping_) {
    error = "device is busy or its display is asleep";
    return false;
  }
  ui_->snap_transition();
  (void)ui_->take_motion_frames();
  const auto saved = navigation_;
  json::Value slides = json::Value::array();
  int min_frames = 1 << 30, max_frame_ms = 0;
  auto slide = [&](Navigation to, const char* label) {
    navigation_ = to;
    ++model_.navigation;
    const uint32_t start = now();
    update_model();  // renders the destination into the slide cache; the glass is unchanged
    json::Value frames = json::Value::array();
    uint32_t last = now();
    const int prep_ms = static_cast<int>(last - start);
    while (ui_->transitioning() && now() - start < 1000) {
      model_.time_ms = now();
      ui_->render(model_);
      const uint32_t t = now();
      frames.push(static_cast<int>(t - last));
      max_frame_ms = std::max(max_frame_ms, static_cast<int>(t - last));
      last = t;
    }
    const int n = ui_->take_motion_frames();
    min_frames = std::min(min_frames, n);
    json::Value s = json::Value::object();
    s.set("to", label).set("frames", n).set("ms", static_cast<int>(now() - start)).set("prep_ms", prep_ms)
        .set("frame_ms", frames);
    slides.push(std::move(s));
  };
  slide(Navigation::Controls, "controls");
  slide(Navigation::Home, "home");
  if (work_available_) {
    slide(Navigation::Recent, "recent");
    slide(Navigation::Home, "home");
  }
  json::Value redraws = json::Value::array();
  int redraw_max = 0;
  for (int i = 0; i < 5; ++i) {
    const uint32_t start = now();
    ui_->invalidate();
    ui_->render(model_);
    const int ms = static_cast<int>(now() - start);
    redraw_max = std::max(redraw_max, ms);
    redraws.push(ms);
  }
  // Back where the user left it, without another slide; contacts begun mid-bench are stale.
  navigation_ = saved;
  ++touch_epoch_;
  ui_->invalidate();
  update_model();
  ui_->snap_transition();
  if (min_frames == (1 << 30)) min_frames = 0;
  result.set("slides", slides).set("min_frames", min_frames).set("max_frame_ms", max_frame_ms)
      .set("redraw_ms", redraws).set("redraw_max_ms", redraw_max);
  set_sensor("perf_bench_min_frames", min_frames);
  set_sensor("perf_bench_max_frame_ms", max_frame_ms);
  set_sensor("perf_bench_redraw_max_ms", redraw_max);
  return true;
}

}  // namespace hg
