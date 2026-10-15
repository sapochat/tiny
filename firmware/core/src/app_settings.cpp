#include "hg/app.hpp"

#include <algorithm>
#include <vector>

namespace hg {

TouchView App::touch_view() const {
  if (mode_ == Mode::Listening) return TouchView::Recording;
  if (prompt_showing()) return TouchView::Approval;
  if (settings_open() || wifi_setup_open() || !can_talk() || ota_busy() ||
      ota_ == Ota::Restarting || !fatal_.empty()) return TouchView::Other;
  if (overlay_ != Overlay::None) return TouchView::Other;
  if (navigation_ == Navigation::Recent) return TouchView::Recent;
  if (navigation_ == Navigation::Result) return TouchView::Result;
  if (navigation_ == Navigation::Controls) return TouchView::Controls;
  if (navigation_ == Navigation::Home) return TouchView::Home;
  if (navigation_ == Navigation::Response || (!model_.hero &&
      (model_.screen == Screen::Responding || model_.screen == Screen::Ready))) return TouchView::Response;
  return TouchView::Home;
}

TouchControl App::touch_hit(int x, int y) const {
  return ui_ ? ui_->control_hit(x, y, model_) : TouchControl::None;
}

void App::touch_swipe(TouchView owner, int dx, int dy, TouchControl control) {
  const auto previous_navigation = navigation_;
  if (mode_ == Mode::Listening || !ui_) return;
  // Preserve the separate, explicit legacy setup/check workflow. Quick controls
  // never enter this menu and never use its Cancel/new-session button path.
  if (owner == TouchView::Other && wifi_setup_open()) {
    if (dy > 0) close_wifi_setup();
    return;
  }
  if (owner == TouchView::Other && settings_open()) {
    if (dy) settings_input(dy > 0 ? Button::Down : Button::Up, true);
    update_model();
    return;
  }
  if (owner == TouchView::Other && overlay_ != Overlay::None && !prompt_showing()) {
    if (dy > 0) dismiss_overlay();
    update_model();
    return;
  }
  if (prompt_showing()) {
    if (owner != TouchView::Approval || !dy) return;
    int total = static_cast<int>(ui_->body_lines(prompt_text_, model_).size());
    int last = std::max(0, total - ui_->body_rows(model_));
    prompt_scroll_ = std::clamp(prompt_scroll_ + (dy < 0 ? 3 : -3), 0, last);
    prompt_read();
  } else if (!can_talk() || ota_busy() || ota_ == Ota::Restarting) return;
  else if (owner == TouchView::Result) {
    if (dx > 0) navigation_ = Navigation::Recent;
    else if (dy) {
      const int last = std::max(0, int(ui_->body_lines(reading_work_.glance, model_).size()) - ui_->body_rows(model_));
      reading_work_.scroll = std::clamp(reading_work_.scroll + (dy < 0 ? 3 : -3), 0, last);
      for (auto& item : recent_)
        if (item.id == reading_work_.id && item.revision == reading_work_.revision) item.scroll = reading_work_.scroll;
    }
  } else if (owner == TouchView::Recent) {
    if (dx > 0) navigation_ = Navigation::Controls;
  } else if (owner == TouchView::Home) {
    if (dy > 0) navigation_ = Navigation::Controls;
    else if (dy < 0 && !reply_.empty()) navigation_ = Navigation::Response;
  } else if (owner == TouchView::Response) {
    if (dx > 0) navigation_ = Navigation::Home;
    else if (dy) {
      navigation_ = Navigation::Response;
      scroll_body(dy < 0 ? 3 : -3);
    }
  } else if (owner == TouchView::Controls && navigation_ == Navigation::Controls) {
    if (dx > 0) navigation_ = Navigation::Home;
    else if (dy && control == TouchControl::Volume && hal_.speaker)
      console("set volume " + std::to_string(std::clamp(int(volume_) - dy / 4, 0, 100)));
    else if (dy && control == TouchControl::Brightness && hal_.display && hal_.display->info().has_backlight)
      console("set brightness " + std::to_string(std::clamp(int(brightness_) - dy / 4, 10, 100)));
  }
  if (navigation_ != previous_navigation) ++model_.navigation;
  update_model();
}

void App::touch_press(TouchControl control) {
  if (control == pressed_) return;
  pressed_ = control;
  update_model();
}

uint32_t App::control_revision(TouchControl control) const {
  if (control >= TouchControl::Recent) return shelf_epoch_;
  switch (control) {
    case TouchControl::Reply: return reply_epoch_;
    case TouchControl::Silence: return output_epoch_;
    case TouchControl::Stop:
    case TouchControl::NewChat: return work_epoch_;  // new work under the finger voids the hold
    case TouchControl::Discard:
    case TouchControl::Finish: return capture_epoch_;
    default: return 0;
  }
}

void App::on_touch_talk(bool pressed) {
  if (pressed && prompt_showing()) return;  // touch Talk asks or clarifies; it never answers Yes
  touch_talk_ = true;
  on_button(Button::Talk, pressed);
  touch_talk_ = false;
}

void App::touch_tap(TouchView owner, TouchControl control, uint32_t pressed_at) {
  const auto previous_navigation = navigation_;
  if (owner != touch_view()) return;
  if (owner == TouchView::Other && settings_open()) {
    settings_input(Button::Talk, false);
  } else if (owner == TouchView::Approval) {
    if (prompt_read() && prompt_armed(pressed_at) && (control == TouchControl::Yes || control == TouchControl::No))
      answer_prompt(control == TouchControl::Yes);
  } else if (owner == TouchView::Recording) {
    // Only a free hand can tap: tap mode, or a physical TALK hold. A touch hold owns the screen.
    if (control == TouchControl::Discard && model_.capture >= 2) discard_capture();
    else if (control == TouchControl::Finish && model_.capture == 3 && hands_free_) finish_listening();
  } else if (control == TouchControl::Recent && work_available_) {
    navigation_ = Navigation::Recent;
  } else if (owner == TouchView::Recent) {
    if (control == TouchControl::Home) navigation_ = Navigation::Controls;
    else if (control == TouchControl::Next) {
      work_page_ = work_page_ + 3 < recent_.size() ? work_page_ + 3 : 0;
      ++shelf_epoch_;
    } else if (control >= TouchControl::Work0 && control <= TouchControl::Work2) {
      unsigned i = work_page_ + unsigned(control) - unsigned(TouchControl::Work0);
      if (i < recent_.size()) { reading_work_ = recent_[i]; navigation_ = Navigation::Result; }
    }
  } else if (owner == TouchView::Result && control == TouchControl::Home) {
    navigation_ = Navigation::Recent;
  } else if (control == TouchControl::Silence) {
    if (model_.can_silence) silence();
  } else if (control == TouchControl::Stop) {
    if (model_.can_stop) request_stop();
    // A pending stop is already shown on the target; a second tap sends nothing.
  } else if (owner == TouchView::Home && control == TouchControl::Controls) {
    navigation_ = Navigation::Controls;
  } else if ((owner == TouchView::Response || owner == TouchView::Controls) && control == TouchControl::Home) {
    navigation_ = Navigation::Home;
  } else if (owner == TouchView::Controls && control == TouchControl::Settings) {
    open_settings();
  } else if (owner == TouchView::Controls && control == TouchControl::NewChat) {
    new_chat_hint_until_ = now() + 2000;  // a tap never starts over; the target says to hold
  } else if (owner == TouchView::Response && control == TouchControl::Talk) {
    if (model_.talk_control && talk_mode_ == TalkMode::Tap) {
      on_touch_talk(true);
      on_touch_talk(false);
    }  // hold mode: the target itself says "Hold to talk"; a tap does nothing
  } else if (owner == TouchView::Home && control == TouchControl::Reply && model_.unread_reply) {
    navigation_ = Navigation::Response;
  } else if (owner == TouchView::Home && control == TouchControl::None && mode_ == Mode::Idle &&
             talk_mode_ == TalkMode::Tap) {
    on_touch_talk(true);
    on_touch_talk(false);
  }
  if (navigation_ != previous_navigation) ++model_.navigation;
  update_model();
}

bool App::new_chat_allowed() const {
  return settings_allowed() && can_talk() && !speaking();
}

void App::touch_hold(TouchView owner, TouchControl control) {
  // Only New chat acts on a hold, and only while it is still offered: idle, connected,
  // nothing speaking, recording or asking. Anything else under the finger does nothing.
  if (owner != TouchView::Controls || owner != touch_view() || control != TouchControl::NewChat) return;
  if (navigation_ != Navigation::Controls || !new_chat_allowed()) return;
  new_chat_hint_until_ = 0;
  start_new_session();
  navigation_ = Navigation::Home;  // Home shows the fresh start; quick controls never linger
  ++model_.navigation;
  update_model();
}

bool App::settings_title_hit(int x, int y) const {
  // The title opens Settings on Home, and on the offline, connecting and pairing screens,
  // where it is the only on-device route to local recovery. Reading and quick controls
  // use that area for navigation. Settings never cancel or replay remote work.
  if (!ui_ || mode_ != Mode::Idle || speaking() || prompt_showing() || ota_busy() || wifi_setup_open())
    return false;
  const bool local_only = !can_talk() && overlay_ == Overlay::None;
  return (local_only || (navigation_ != Navigation::Controls &&
                         (settings_open() || touch_view() == TouchView::Home))) && ui_->title_hit(x, y);
}

bool App::settings_allowed() const {
  return !work_active() && !speaking() && mode_ != Mode::Listening && !prompt_showing() && !ota_busy() &&
         ota_ != Ota::Restarting && wifi_setup_text_.empty() && !stop_pending_current();
}

bool App::open_settings() {
  if (prompt_showing() || ota_busy() || ota_ == Ota::Restarting || !wifi_setup_text_.empty()) return false;
  wake_display();
  if (settings_open()) { close_settings(); return true; }
  // Settings never cancel a recording, a reply or remote work: they open when idle.
  if (!settings_allowed()) {
    if (!(ui_ && ui_->round_companion())) set_hint_flash("Settings open when idle");
    update_model();
    return false;
  }
  stop_playback();
  dismiss_overlay();
  menu_ = Menu::Volume;
  power_off_armed_ = false;
  check_result_.clear();
  update_model();
  return true;
}

void App::stop_hardware_check() {
  if (hardware_check_ == HardwareCheck::Microphone && hal_.mic) hal_.mic->stop();
  if (hardware_check_ == HardwareCheck::Speaker && hal_.speaker) hal_.speaker->abort();
  hardware_check_ = HardwareCheck::None;
  level_ = 0;
}

void App::close_settings() {
  stop_hardware_check();
  menu_ = Menu::Closed;
  check_result_.clear();
  if (ui_) ui_->invalidate();
  update_model();
}

void App::settings_input(Button button, bool pressed) {
  if (hardware_check_ == HardwareCheck::Inputs) {
    if (pressed) {
      const char* labels[] = {"TALK", "CANCEL", "UP", "DOWN"};
      check_result_ = std::string(labels[static_cast<unsigned>(button)]) + " pressed";
      return;
    }
    if (button != Button::Cancel) return;
  }
  if ((button == Button::Cancel && !pressed) ||
      ((button == Button::Up || button == Button::Down) && pressed)) {
    stop_hardware_check();
    check_result_.clear();
    power_off_armed_ = false;
    int item = static_cast<int>(menu_) + (button == Button::Up ? -1 : 1);
    if (item < static_cast<int>(Menu::Volume)) item = static_cast<int>(Menu::Back);
    if (item > static_cast<int>(Menu::Back)) item = static_cast<int>(Menu::Volume);
    menu_ = static_cast<Menu>(item);
    const bool can_power_off = hal_.power && hal_.power->can_power_off();
    if ((!hal_.power && menu_ == Menu::Power) ||
        (!can_power_off && menu_ == Menu::PowerOff)) {
      menu_ = menu_ == Menu::Power ? (button == Button::Up ? Menu::Info : Menu::IdleTimer)
                                   : (button == Button::Up ? Menu::IdleTimer : Menu::WifiSetup);
    }
    if (!on_wifi_setup && menu_ == Menu::WifiSetup)
      menu_ = button == Button::Up ? (can_power_off ? Menu::PowerOff : Menu::IdleTimer) : Menu::Back;
    return;
  }
  if (button != Button::Talk || pressed) return;
  if (hardware_check_ != HardwareCheck::None) {
    stop_hardware_check();
    check_result_ = "Check stopped";
    return;
  }
  check_result_.clear();
  switch (menu_) {
    case Menu::Volume:
      if (hal_.speaker) console("set volume " + std::to_string(volume_ >= 100 ? 0 : std::min(100, volume_ + 10)));
      break;
    case Menu::Brightness:
      if (hal_.display && hal_.display->info().has_backlight) {
        const int next = brightness_ < 25 ? 25 : brightness_ < 50 ? 50 : brightness_ < 75 ? 75 : brightness_ < 100 ? 100 : 10;
        console("set brightness " + std::to_string(next));
      }
      break;
    case Menu::TalkMode:
      if (hal_.mic) console(talk_mode_ == TalkMode::Hold ? "set talk_mode tap" : "set talk_mode hold");
      break;
    case Menu::Microphone:
      if (hal_.mic && hal_.mic->start(profile_.mic_rate)) hardware_check_ = HardwareCheck::Microphone;
      else check_result_ = "Microphone unavailable";
      break;
    case Menu::Speaker:
      if (hal_.speaker && hal_.speaker->begin(profile_.speaker_rate)) {
        // A quiet quarter-second square tone, entirely local to the device.
        std::vector<int16_t> tone(profile_.speaker_rate / 4);
        const uint32_t half_period = std::max<uint32_t>(1, profile_.speaker_rate / 1000);
        for (size_t i = 0; i < tone.size(); ++i) tone[i] = (i / half_period) % 2 ? 900 : -900;
        hal_.speaker->write(tone.data(), tone.size());
        hal_.speaker->end();
        hardware_check_ = HardwareCheck::Speaker;
        check_result_ = "Listen for a short tone";
      } else check_result_ = "Speaker unavailable";
      break;
    case Menu::Display:
      if (hal_.display) hardware_check_ = HardwareCheck::Display;
      else check_result_ = "Display unavailable";
      break;
    case Menu::Inputs:
      hardware_check_ = HardwareCheck::Inputs;
      check_result_ = "Press a button. Release Cancel to leave.";
      break;
    case Menu::IdleTimer: {
      const uint32_t seconds = screen_timeout_ms_ / 1000;
      const uint32_t next = seconds == 0 ? 30 : seconds < 60 ? 60 : seconds < 120 ? 120 : seconds < 300 ? 300 : 0;
      console("set screen_timeout " + std::to_string(next));
      break;
    }
    case Menu::PowerOff:
      if (!power_off_armed_) {
        power_off_armed_ = true;
        check_result_ = "Select again to power off. Cancel goes back.";
      } else {
        power_off_armed_ = false;
        check_result_ = hal_.power->power_off() ? "Power-off requested" : "Power-off failed. Try the physical PWR key.";
      }
      break;
    case Menu::Back: close_settings(); break;
    case Menu::WifiSetup: start_wifi_setup(); break;
    case Menu::Power:
    case Menu::Info:
    case Menu::Closed: break;
  }
}

void App::settings_tick() {
  if (talk_held_ && cancel_held_ && !settings_chord_fired_ &&
      now() - talk_down_at_ >= 1000 && now() - cancel_down_at_ >= 1000) {
    // The chord is consumed even when settings refuse (busy, question, update), so its
    // release can never fall through to Stop work or a prompt answer.
    open_settings();
    settings_chord_fired_ = true;
    cancel_long_fired_ = true;
  }
  if (hardware_check_ == HardwareCheck::Speaker && !hal_.speaker->busy()) {
    hardware_check_ = HardwareCheck::None;
    check_result_ = "Tone finished. Did you hear it?";
    update_model();
  }
}

void App::settings_model() {
  UiModel& m = model_;
  m.screen = Screen::Settings;
  m.headline = "Settings";
  m.scroll = 0;
  m.speaking = false;
  m.hint = profile_.touch_screen ? "Tap: change | Swipe: next"
                                : profile_.talk_label + ": change | " + profile_.cancel_label + ": next";
  switch (menu_) {
    case Menu::Volume:
      m.detail = "Speaker volume";
      m.body = hal_.speaker ? std::to_string(volume_) + "%\nChanges are saved." : "No speaker driver is active.";
      break;
    case Menu::Brightness:
      m.detail = "Screen brightness";
      m.body = hal_.display && hal_.display->info().has_backlight ? std::to_string(brightness_) + "%\nChanges are saved."
                                                               : "Brightness control is unavailable.";
      break;
    case Menu::TalkMode:
      m.detail = "Talk mode";
      m.body = !hal_.mic ? "No microphone driver is active." : talk_mode_ == TalkMode::Hold ? "Hold to record; release to send."
                                                                                         : "Tap to record; pause or tap to send.";
      break;
    case Menu::Microphone:
      m.detail = "Microphone check";
      m.body = hardware_check_ == HardwareCheck::Microphone ? "Speak now. Level: " + std::to_string(level_) + "%\nLocal only. Nothing is sent."
                                                          : "Start to check the microphone level. No recording is saved or sent.";
      break;
    case Menu::Speaker:
      m.detail = "Speaker check";
      m.body = "Start to play a short tone at the current volume.";
      break;
    case Menu::Display:
      m.detail = "Display check";
      m.body = "Start to show red, green, blue, white and black bands.";
      m.color_test = hardware_check_ == HardwareCheck::Display;
      break;
    case Menu::Inputs:
      m.detail = "Input check";
      m.body = "Start to check the controls. Cancel leaves this check.";
      break;
    case Menu::Info:
      m.detail = "Device information";
      m.body = profile_.board + "\nFirmware " + profile_.firmware + "\n" + device_id_ + "\nMicrophone: " +
               (hal_.mic ? "available" : "unavailable") + "\nSpeaker: " + (hal_.speaker ? "available" : "unavailable");
      break;
    case Menu::Power:
      m.detail = "Battery and power";
      if (!power_status_) m.body = "Power readings unavailable.";
      else {
        const auto& p = *power_status_;
        if (p.battery_present && !*p.battery_present) m.body = "No battery detected.\n";
        if (p.battery_percent) m.body += std::to_string(*p.battery_percent) + "% (gauge estimate)\n";
        if (p.battery_mv) m.body += std::to_string(*p.battery_mv) + " mV\n";
        if (p.charging) m.body += *p.charging ? "Charging\n" : "Not charging\n";
        if (p.external_power) m.body += *p.external_power ? "USB power\n" : "No USB power\n";
        if (p.battery_percent && *p.battery_percent <= 10 && p.external_power == false) m.body += "Low battery: connect USB.";
      }
      break;
    case Menu::IdleTimer:
      m.detail = "Screen timeout";
      m.body = screen_timeout_ms_ ? std::to_string(screen_timeout_ms_ / 1000) + " seconds\nDims halfway; first input wakes."
                                 : "Always on\nSelect to enable automatic dimming and screen sleep.";
      break;
    case Menu::PowerOff:
      m.detail = "Power off";
      m.body = "Shut down the board. Use its PWR key to turn it on again.";
      break;
    case Menu::WifiSetup:
      m.detail = "Wi-Fi setup";
      m.body = "Start a temporary network to configure this device with your phone.";
      break;
    case Menu::Back:
      m.detail = "Back to Hermes";
      m.body = "Select to close settings.";
      break;
    case Menu::Closed: break;
  }
  if (ui_ && ui_->round_companion()) round_settings_model();
  if (!check_result_.empty()) m.body += "\n" + check_result_;
}

void App::round_settings_model() {
  // Same rows and input semantics as the legacy menu; the round face shows the current
  // value large, a one-line description, the row position and the row's own action.
  UiModel& m = model_;
  const bool checking = hardware_check_ != HardwareCheck::None;
  std::string action = "Tap to change";
  switch (menu_) {
    case Menu::Volume:
      if (hal_.speaker) { m.value = std::to_string(volume_) + "%"; m.body = "Changes are saved."; }
      break;
    case Menu::Brightness:
      if (hal_.display && hal_.display->info().has_backlight) {
        m.value = std::to_string(brightness_) + "%";
        m.body = "Changes are saved.";
      }
      break;
    case Menu::TalkMode:
      if (hal_.mic) {
        m.value = talk_mode_ == TalkMode::Hold ? "Hold" : "Tap";
        m.body = talk_mode_ == TalkMode::Hold ? "Hold to record; release to send." : "Tap to record; pause or tap to send.";
      }
      break;
    case Menu::Microphone:
      if (hardware_check_ == HardwareCheck::Microphone) {
        m.value = "Level " + std::to_string(level_) + "%";
        m.body = "Speak now. Local only; nothing is sent.";
      }
      action = checking ? "Tap to stop" : "Tap to start";
      break;
    case Menu::Speaker:
    case Menu::Display:
      action = checking ? "Tap to stop" : "Tap to start";
      break;
    case Menu::Inputs:
      action = checking ? "Hold the title to leave" : "Tap to start";
      break;
    case Menu::IdleTimer:
      m.value = screen_timeout_ms_ ? std::to_string(screen_timeout_ms_ / 1000) + " seconds" : "Always on";
      m.body = screen_timeout_ms_ ? "Dims halfway; first input wakes." : "Tap to enable dimming and screen sleep.";
      break;
    case Menu::PowerOff: action = "Tap to power off"; break;
    case Menu::WifiSetup: action = "Tap to start"; break;
    case Menu::Back: action = "Tap to close"; m.body = "Return to Hermes."; break;
    case Menu::Info:
    case Menu::Power: action.clear(); break;
    case Menu::Closed: break;
  }
  m.hint = action.empty() ? "Swipe for next" : action + " · Swipe for next";
  // Row position among the rows this board actually offers.
  const bool can_power_off = hal_.power && hal_.power->can_power_off();
  unsigned index = 0, count = 0;
  for (int i = static_cast<int>(Menu::Volume); i <= static_cast<int>(Menu::Back); ++i) {
    const auto row = static_cast<Menu>(i);
    if ((row == Menu::Power && !hal_.power) || (row == Menu::PowerOff && !can_power_off) ||
        (row == Menu::WifiSetup && !on_wifi_setup)) continue;
    if (row == menu_) index = count;
    ++count;
  }
  m.work_page = static_cast<uint8_t>(index);
  m.work_pages = static_cast<uint8_t>(count);
}

bool App::start_wifi_setup() {
  if (!on_wifi_setup || prompt_showing() || ota_busy() || ota_ == Ota::Restarting) return false;
  if (mode_ == Mode::Listening) cancel_listening("Wi-Fi setup");
  else if (work_active()) request_stop();  // explicit console action; outcome stays honest
  stop_playback();
  close_settings();
  wake_display();
  talk_held_ = false;
  cancel_held_ = false;
  settings_chord_fired_ = false;
  wake_buttons_ = 0;
  wifi_setup_text_ = on_wifi_setup();
  if (wifi_setup_text_.empty()) set_hint_flash("Wi-Fi setup unavailable; use USB");
  update_model();
  return !wifi_setup_text_.empty();
}

void App::close_wifi_setup() {
  if (wifi_setup_text_.empty()) return;
  wifi_setup_text_.clear();
  if (on_wifi_setup_close) on_wifi_setup_close();
  update_model();
}

}  // namespace hg
