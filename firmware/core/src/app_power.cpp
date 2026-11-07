#include "hg/app.hpp"

#include <algorithm>

namespace hg {

namespace {
constexpr uint32_t kPowerReadMs = 5000;
constexpr uint32_t kNoticeMs = 10000;
constexpr uint32_t kShutdownWarnMs = 10000;   // the "Battery empty" card, then power-off
constexpr uint32_t kShutdownGraceMs = 10000;  // at most this much longer for a turn in flight
constexpr const char* kEmptyTitle = "Battery empty";
}  // namespace

bool App::wake_display(bool input) {
  if (input && ui_ && ui_->transitioning()) { ui_->snap_transition(); update_model(); }
  activity_at_ = now();
  display_rested_ = false;
  rested_turn_.clear();
  const bool sleeping = display_sleeping_;
  if (display_dimmed_ || sleeping) {
    display_dimmed_ = display_sleeping_ = false;
    // The panel wakes dark and is repainted before it lights: nothing stale shows.
    if (sleeping) hal_.display->set_sleep(false);
    if (ui_) ui_->invalidate();
    update_model();
    hal_.display->set_backlight(brightness_);
  }
  return sleeping;
}

void App::dark_display() {
  display_sleeping_ = true;
  display_dimmed_ = false;
  hal_.display->set_backlight(0);
  hal_.display->set_sleep(true);
}

void App::rest_display() {
  if (!hal_.display) return;
  if (!display_sleeping_) dark_display();
  display_rested_ = true;
  rested_turn_ = active_turn_;
}

bool App::rest_holds(const std::string& turn) const {
  return display_rested_ && (turn.empty() || turn == rested_turn_);
}

void App::pwr_key() {
  bool sounding = speaking();
#ifdef HG_ROUND_UI
  sounding = sounding || timer_state() == TimerState::Ringing;
#endif
  // Something sounding: PWR is Silence, and the screen stays as it is.
  if (sounding) { silence_key(); return; }
  if (!hal_.display) return;
  if (display_sleeping_) { wake_display(true); return; }
  rest_display();
  update_model();
}

void App::power_tick() {
  if (hal_.power && (!power_read_at_ || now() - power_read_at_ >= kPowerReadMs)) {
    power_status_ = hal_.power->read();
    power_read_at_ = now();
    sensors_dirty_ = true;
    battery_tick();
    update_model();  // Home's battery mark, Quick controls' title, Settings → Power
  }
  if (shutdown_at_ && !shutdown_sent_ && static_cast<int32_t>(now() - shutdown_at_) >= 0) {
    // Never mid-turn: a recording, open work or speech gets up to kShutdownGraceMs more.
    const bool busy = mode_ == Mode::Listening || work_open() || speaking();
    if (!busy || static_cast<int32_t>(now() - shutdown_at_) >= static_cast<int32_t>(kShutdownGraceMs)) {
      shutdown_sent_ = true;
      log(LogLevel::Warn, "battery empty: powering off");
      if (!hal_.power->power_off()) {
        notice_ = "Power-off failed: connect USB";
        notice_until_ = now() + kNoticeMs;
        update_model();
      }
    }
  }
  if (!hal_.display || !hal_.display->info().has_backlight || !screen_timeout_ms_) return;
  const bool idle = mode_ == Mode::Idle && !speaking() && !settings_open() && !talk_held_ && !cancel_held_ &&
                    !prompt_showing() && wifi_setup_text_.empty() && !ota_busy() && ota_ != Ota::Restarting && overlay_ == Overlay::None &&
                    (phase_ == Phase::NoNetwork || (phase_ == Phase::Online && paired_))
#ifdef HG_ROUND_UI
                    && !alarm_showing()  // a ringing timer keeps the screen awake
#endif
                    ;
  // A screen PWR turned off stays off while the work it was pressed over runs on.
  if (!idle) { if (!display_rested_) wake_display(); return; }
  const uint32_t elapsed = now() - activity_at_;
  if (elapsed >= screen_timeout_ms_ && !display_sleeping_) {
    dark_display();
  } else if (elapsed >= screen_timeout_ms_ / 2 && !display_dimmed_ && !display_sleeping_) {
    display_dimmed_ = true;
    hal_.display->set_backlight(std::min<uint8_t>(brightness_, 10));
  }
}

bool App::on_battery() const {
  return power_status_ && power_status_->external_power == false && power_status_->battery_percent &&
         power_status_->battery_present != false;
}

void App::battery_tick() {
  if (!power_status_) return;  // a failed read changes nothing
  const bool battery = on_battery();
  const int pct = battery ? *power_status_->battery_percent : -1;
  if (!battery || pct > 25) battery_notice_armed_ = true;
  if (battery && pct <= 20 && battery_notice_armed_) {
    battery_notice_armed_ = false;
    notice_ = "Battery " + std::to_string(pct) + "% · charge soon";
    notice_until_ = now() + kNoticeMs;
    wake_display();
  }
  // One reading can be a gauge glitch; two in a row (5 s apart) start the shutdown.
  empty_reads_ = battery && pct <= 5 ? static_cast<uint8_t>(std::min(2, empty_reads_ + 1)) : 0;
  if (empty_reads_ >= 2 && !shutdown_at_) {
    shutdown_at_ = now() + kShutdownWarnMs;
    if (!shutdown_at_) shutdown_at_ = 1;
    card_title_ = kEmptyTitle;
    card_body_ = "Turning off in 10 seconds. Plug in USB to stay on.";
    card_scroll_ = 0;
    page_at_ = now() + page_dwell_ms();
    overlay_ = Overlay::Card;
    overlay_until_ = shutdown_at_ + kShutdownGraceMs;
    wake_display();
    log(LogLevel::Warn, "battery empty: power-off in 10 s unless USB is connected");
  }
  if (!battery && shutdown_at_) {
    // Plugged in during the countdown: stay on.
    shutdown_at_ = 0;
    shutdown_sent_ = false;
    if (overlay_ == Overlay::Card && card_title_ == kEmptyTitle) dismiss_overlay();
    notice_ = "Charging · staying on";
    notice_until_ = now() + kNoticeMs / 2;
    wake_display();
  }
}

void App::battery_model(UiModel& m) const {
  m.battery = -1;
  m.battery_tone = 0;
  if (!power_status_ || !power_status_->battery_percent || power_status_->battery_present == false ||
      !power_status_->external_power)
    return;
  const int pct = std::clamp<int>(*power_status_->battery_percent, 0, 100);
  const bool usb = *power_status_->external_power;
  const bool charging = power_status_->charging.value_or(false);
  if (usb && !charging) return;  // plugged in and full: nothing worth a mark
  m.battery = static_cast<int8_t>(pct);
  m.battery_tone = usb ? 3 : pct <= 10 ? 2 : pct <= 20 ? 1 : 0;
}

json::Value App::power_value() const {
  json::Value value = json::Value::object();
  value.set("available", power_status_.has_value());
  if (shutdown_at_ && !shutdown_sent_) {
    const int32_t left = static_cast<int32_t>(shutdown_at_ - now());
    value.set("shutdown_in_s", std::max<int32_t>(0, (left + 999) / 1000));
  }
  if (!power_status_) return value;
  const auto& p = *power_status_;
  if (p.battery_present) value.set("battery_present", *p.battery_present);
  if (p.battery_mv) value.set("battery_mv", *p.battery_mv);
  if (p.battery_percent) value.set("battery_percent", *p.battery_percent);
  if (p.charging) value.set("charging", *p.charging);
  if (p.external_power) value.set("external_power", *p.external_power);
  return value;
}

}  // namespace hg
