// Local timers (R-13): timer.start / timer.cancel / timer.list device actions.
//
// Hermes sets them through its existing device-action tool; everything after that is local.
// A timer counts on the monotonic now_ms(), never the host's wall clock, so it keeps running
// through Wi-Fi loss and ignores host clock changes. When one ends the device takes over the
// screen with a large Dismiss and beeps (the speaker check's square tone) about once a
// second for a minute; unanswered, it leaves Home's needs-you mark and a Dismiss until the
// user clears it. Nothing is sent to the host when a timer ends. A reboot loses timers.
#include "hg/app.hpp"

#ifdef HG_ROUND_UI

#include <algorithm>
#include <cstdio>

namespace hg {
namespace {

constexpr uint32_t kMaxTimerS = 24 * 3600;
constexpr size_t kMaxTimers = 4;
constexpr size_t kMaxLabelBytes = 32;
constexpr uint32_t kRingMs = 60000;   // the alarm rings this long, then waits on Home
constexpr uint32_t kBeepEveryMs = 1000;
constexpr uint32_t kBeepMs = 300;
constexpr int16_t kBeepLevel = 3000;

std::string countdown(uint32_t left_ms) {
  const uint32_t s = (left_ms + 999) / 1000;  // a countdown rounds up, as clocks do
  char buf[16];
  if (s >= 3600) std::snprintf(buf, sizeof buf, "%u:%02u:%02u", unsigned(s / 3600), unsigned(s / 60 % 60), unsigned(s % 60));
  else std::snprintf(buf, sizeof buf, "%u:%02u", unsigned(s / 60), unsigned(s % 60));
  return buf;
}

}  // namespace

void App::add_timer_actions() {
  if (!ui_ || !ui_->round_companion() || !profile_.touch_screen) return;
  Action start;
  start.name = "timer.start";
  start.description = "Start a countdown timer on the device. It runs on the device itself, keeps "
                      "working without Wi-Fi, and rings with a tone and a Dismiss button when it ends. "
                      "Up to 4 at once; a restart of the device loses them.";
  {
    json::Value props = json::Value::object(), secs = json::Value::object(), label = json::Value::object();
    secs.set("type", "integer").set("minimum", 1).set("maximum", static_cast<int>(kMaxTimerS))
        .set("description", "Duration in seconds");
    label.set("type", "string").set("description", "Short name shown on the screen, e.g. Pasta");
    props.set("seconds", secs).set("label", label);
    json::Value req = json::Value::array();
    req.push("seconds");
    start.params.set("type", "object").set("properties", props).set("required", req);
  }
  start.handler = [this](const json::Value& args, json::Value& result, std::string& error) {
    if (!args["seconds"].is_number()) {
      error = "seconds is required (1 to 86400)";
      return false;
    }
    const double secs = args["seconds"].as_number();
    if (!(secs >= 1 && secs <= kMaxTimerS)) {
      error = "seconds must be 1 to 86400";
      return false;
    }
    if (timers_.size() >= kMaxTimers) {
      error = "4 timers are already set; cancel one first";
      return false;
    }
    std::string label(args["label"].str_or(""));
    for (char& ch : label) if (ch == '\n' || ch == '\r' || ch == '\t') ch = ' ';
    const size_t a = label.find_first_not_of(' '), b = label.find_last_not_of(' ');
    label = a == std::string::npos ? std::string() : label.substr(a, b - a + 1);
    if (label.size() > kMaxLabelBytes) {  // cut at a character boundary
      size_t n = kMaxLabelBytes;
      while (n > 0 && (static_cast<unsigned char>(label[n]) & 0xC0) == 0x80) --n;
      label.resize(n);
    }
    LocalTimer t;
    t.id = "t" + std::to_string(++timer_seq_);
    t.label = label;
    t.start = now();
    t.duration = static_cast<uint32_t>(secs * 1000 + 0.5) / 1000 * 1000;
    timers_.push_back(t);
    timers_changed();
    result = timer_value(timers_.back());
    return true;
  };
  add_action(std::move(start));

  Action cancel;
  cancel.name = "timer.cancel";
  cancel.description = "Cancel a device timer (also silences it if it is ringing). Pass the id from "
                       "timer.start or timer.list; it may be omitted when only one timer is set.";
  {
    json::Value props = json::Value::object(), id = json::Value::object();
    id.set("type", "string").set("description", "Timer id");
    props.set("id", id);
    cancel.params.set("type", "object").set("properties", props);
  }
  cancel.handler = [this](const json::Value& args, json::Value& result, std::string& error) {
    const std::string id(args["id"].str_or(""));
    if (timers_.empty()) {
      error = "no timer is set";
      return false;
    }
    auto it = timers_.end();
    if (id.empty()) {
      if (timers_.size() > 1) {
        error = "which timer? pass an id:";
        for (const auto& t : timers_) error += " " + t.id + (t.label.empty() ? "" : " (" + t.label + ")");
        return false;
      }
      it = timers_.begin();
    } else {
      it = std::find_if(timers_.begin(), timers_.end(), [&](const LocalTimer& t) { return t.id == id; });
      if (it == timers_.end()) {
        error = "no timer with id " + id;
        return false;
      }
    }
    result.set("cancelled", timer_value(*it));
    timers_.erase(it);
    result.set("timers", static_cast<int>(timers_.size()));
    timers_changed();
    return true;
  };
  add_action(std::move(cancel));

  Action list;
  list.name = "timer.list";
  list.description = "List the device's timers, soonest first, with the seconds left.";
  list.params.set("type", "object").set("properties", json::Value::object());
  list.handler = [this](const json::Value&, json::Value& result, std::string&) {
    std::vector<const LocalTimer*> order;
    for (const auto& t : timers_) order.push_back(&t);
    std::stable_sort(order.begin(), order.end(), [&](const LocalTimer* a, const LocalTimer* b) {
      return timer_left_ms(*a) < timer_left_ms(*b);
    });
    json::Value items = json::Value::array();
    for (const auto* t : order) items.push(timer_value(*t));
    result.set("timers", items);
    return true;
  };
  add_action(std::move(list));
}

uint32_t App::timer_left_ms(const LocalTimer& t) const {
  if (t.expired) return 0;
  const uint32_t gone = now() - t.start;
  return gone >= t.duration ? 0 : t.duration - gone;
}

json::Value App::timer_value(const LocalTimer& t) const {
  json::Value v = json::Value::object();
  const uint32_t left = timer_left_ms(t);
  const auto state = !t.expired ? "running" : timer_state() == TimerState::Ringing ? "ringing" : "done";
  v.set("id", t.id).set("label", t.label).set("seconds", static_cast<int64_t>(t.duration / 1000))
      .set("remaining_s", static_cast<int64_t>((left + 999) / 1000)).set("state", state);
  return v;
}

const App::LocalTimer* App::next_timer() const {
  const LocalTimer* best = nullptr;
  for (const auto& t : timers_)
    if (!t.expired && (!best || timer_left_ms(t) < timer_left_ms(*best))) best = &t;
  return best;
}

App::TimerState App::timer_state() const {
  bool running = false, fired = false;
  for (const auto& t : timers_) (t.expired ? fired : running) = true;
  if (fired) return static_cast<int32_t>(alarm_until_ - now()) > 0 ? TimerState::Ringing : TimerState::Done;
  return running ? TimerState::Running : TimerState::None;
}

bool App::alarm_showing() const {
  // A recording keeps the screen (and the microphone hears no beep); a question from Hermes
  // still takes over. The alarm returns when either ends, while it still rings.
  return timer_state() == TimerState::Ringing && mode_ != Mode::Listening && !prompt_showing() &&
         !settings_open() && !wifi_setup_open() && ota_ != Ota::Receiving && ota_ != Ota::Restarting;
}

std::string App::timer_line(bool expired) const {
  std::string first;
  int more = -1;
  if (!expired) {
    if (const LocalTimer* t = next_timer()) first = t->label;
    for (const auto& t : timers_) more += !t.expired;
  } else {
    for (const auto& t : timers_) {
      if (!t.expired) continue;
      if (++more == 0) first = t.label;
    }
  }
  if (more < 0) return {};
  std::string line = first.empty() ? std::string("Timer") : first;
  if (more > 0) line += " · +" + std::to_string(more) + " more";
  return line;
}

void App::timers_changed() {
  if (timer_state() != TimerState::Ringing && tone_out_) {
    if (hal_.speaker && in_stream_ < 0) hal_.speaker->abort();
    tone_out_ = false;
  }
  if (std::none_of(timers_.begin(), timers_.end(), [](const LocalTimer& t) { return t.expired; })) alarm_until_ = 0;
  ++timer_epoch_;
  timer_tick();
  update_model();
}

void App::dismiss_timers() {
  timers_.erase(std::remove_if(timers_.begin(), timers_.end(), [](const LocalTimer& t) { return t.expired; }),
                timers_.end());
  alarm_until_ = 0;
  timers_changed();
}

void App::timer_tick() {
  const uint32_t t = now();
  bool fired = false;
  for (auto& timer : timers_) {
    if (!timer.expired && t - timer.start >= timer.duration) {
      timer.expired = true;
      fired = true;
    }
  }
  if (fired) {
    alarm_until_ = t + kRingMs;
    beep_at_ = t;
    // The alarm takes the screen: local menus close, the display wakes. Nothing is sent.
    if (settings_open()) close_settings();
    close_wifi_setup();
    wake_display();
  }
  if (tone_out_ && hal_.speaker && !hal_.speaker->busy()) tone_out_ = false;
  const TimerState state = timer_state();
  if (state == TimerState::Ringing && alarm_showing() && in_stream_ < 0 && static_cast<int32_t>(t - beep_at_) >= 0) {
    if (play_tone(kBeepLevel, kBeepMs)) tone_out_ = true;
    beep_at_ = t + kBeepEveryMs;
  }
  if (state != timer_shown_) {
    // Contacts begun on the old screen never act on the alarm or its Dismiss.
    if (state == TimerState::Ringing || timer_shown_ == TimerState::Ringing) ++touch_epoch_;
    if (state != TimerState::Ringing && tone_out_) {
      if (hal_.speaker && in_stream_ < 0) hal_.speaker->abort();
      tone_out_ = false;
    }
    timer_shown_ = state;
    ++timer_epoch_;
    update_model();
  }
}

void App::timer_model(UiModel& m) {
  // Called at the end of update_model on the round companion. Home's countdown replaces the
  // idle state word; a connection screen shows it in its title. A fired timer nobody
  // dismissed takes Home's state word with a Dismiss target and the needs-you mark.
  m.timer_done = false;
  m.timer_slot = 0;
  m.timer_text.clear();
  const TimerState state = timer_state();
  if (state == TimerState::None) return;
  const bool idle_home = m.hero && m.screen == Screen::Ready && touch_view() == TouchView::Home &&
                         mode_ == Mode::Idle && !speaking();
  if (idle_home && state == TimerState::Done && !m.can_stop && !m.stop_pending && note_head_.empty()) {
    m.timer_done = true;
    m.headline = "Timer done";
    m.detail = timer_line(true);
    return;
  }
  const LocalTimer* t = next_timer();
  if (!t) return;
  const std::string left = countdown(timer_left_ms(*t));
  const bool idle_word = m.detail.empty() && (m.headline == "Hold to talk" || m.headline == "Tap to talk");
  if (idle_home && idle_word) {
    m.timer_slot = 1;
    m.timer_text = m.headline = left;
    m.detail = timer_line(false);
  } else if (m.screen == Screen::Offline || m.screen == Screen::Connecting || m.screen == Screen::Error) {
    m.timer_slot = 2;
    m.timer_text = (t->label.empty() ? std::string("Timer") : t->label) + " · " + left;
  }
}

json::Value App::timer_status() const {
  const char* states[] = {"none", "running", "ringing", "done"};
  const TimerState state = timer_state();
  json::Value v = json::Value::object();
  std::string text, label;
  if (state == TimerState::Running) {
    if (const LocalTimer* t = next_timer()) { text = countdown(timer_left_ms(*t)); label = t->label; }
  } else if (state != TimerState::None) {
    for (const auto& t : timers_) if (t.expired) { label = t.label; break; }
  }
  v.set("state", states[static_cast<unsigned>(state)]).set("count", static_cast<int>(timers_.size()))
      .set("text", text).set("label", label);
  return v;
}

}  // namespace hg

#endif  // HG_ROUND_UI
