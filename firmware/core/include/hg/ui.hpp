// Screen model and renderer.
//
// The app fills a UiModel; Ui renders it into the framebuffer in horizontal
// bands and flushes only the bands whose inputs changed. The renderer is
// deterministic (no clocks, no randomness): the same model always produces the
// same pixels, which is what the simulator's screenshot tests rely on.
#pragma once

#include <cstdint>
#include <string>
#include <vector>

#include "hg/canvas.hpp"
#include "hg/hal.hpp"
#include "hg/mascot.hpp"

namespace hg {

enum class Screen : uint8_t {
  Boot,
  Offline,
  Connecting,
  Pairing,
  Ready,
  Listening,
  Thinking,
  Responding,
  Card,
  Image,
  Error,
  Prompt,  // a yes/no question from Hermes, answered with the buttons
  Updating,  // installing a firmware update
  Settings,
  Setup,
};

enum class Link : uint8_t { Offline, Network, Connecting, Online };

enum class TouchView : uint8_t { Home, Response, Controls, Approval, Recording, Other, Recent, Result };
// Stop means "Stop work" (a cancellation request). Silence only quiets local playback.
enum class TouchControl : uint8_t { None, Volume, Brightness, Stop, Yes, No, Reply, Silence, Discard, Finish,
                                    Talk, Controls, Home, Settings, Recent, Work0, Work1, Work2, Next };
constexpr unsigned kTouchControls = static_cast<unsigned>(TouchControl::Next) + 1;
const char* control_name(TouchControl c);
// The word a host work stage reads as on screen (\"cancelled\" reads \"Stopped\").
const char* stage_word(const std::string& stage);
struct UiRect {
  int x = 0, y = 0, w = 0, h = 0;
  bool contains(int px, int py) const { return px >= x && py >= y && px < x+w && py < y+h; }
};

const char* screen_name(Screen s);

struct UiModel {
  Screen screen = Screen::Boot;
  Link link = Link::Offline;
  std::string title;     // top bar (device name)
  std::string headline;  // header band, next to the indicator
  std::string detail;    // secondary line (status phrase, URL, error)
  std::string body;      // main text (reply, card body)
  std::string code;      // pairing code
  std::string value;     // round settings: the current row's value, shown large
  int scroll = -1;       // first visible body line; -1 pins to the end
  uint8_t level = 0;     // microphone level 0..100
  bool speaking = false;
  bool color_test = false;
  bool quick_controls = false, touch_prompt = false;
  bool prompt_unread = false;  // touch question not yet read to its end: answers are inert
  bool work_available = false, recent = false, result = false;
  std::vector<std::string> work_rows;   // "stage\nglance" for the visible shelf page
  uint8_t work_page = 0, work_pages = 0;  // shelf page index and count (paging shows when > 1);
                                          // round settings reuse them for the row position
  // The target under a finger that has not yet moved or lifted; drawn lit, flushed alone.
  TouchControl pressed = TouchControl::None;
  bool unread_reply = false;
  bool has_reply = false, can_stop = false;
  bool reply_ready = false;  // success-only completed text; never inferred from a label
  // Independent facts: local playback, a pending stop request for the current work,
  // capture ownership (0 none, 1 touch hold, 2 physical TALK hold, 3 tap mode) and
  // whether an explicit reading Talk target or idle settings entry is offered.
  bool can_silence = false, stop_pending = false;
  uint8_t capture = 0;
  bool talk_control = false, tap_talk = false, settings_ready = false;
  // How the latest work ended, once it has: a compact reading line (only for text from
  // that work) and a word for the inert Stop target in quick controls. Empty while open.
  std::string outcome, outcome_word;
  // Authored clip entry, selected from activity BEFORE navigation overrides.
  uint8_t expression = 0;
  int volume = 0, brightness = 0;
  uint32_t navigation = 0;  // explicit navigation generation
  uint32_t time_ms = 0;  // app clock; motion never sleeps or owns input
  uint32_t frame = 0;    // animation frame, advanced by the app
  std::string hint;      // bottom bar
  std::string yes, no;   // answer buttons under the hero caption (Prompt screen)
  // Show the mascot as large as fits, with headline/detail as a caption,
  // instead of the header + text layout.
  bool hero = false;
  uint8_t caption_lines = 1;  // hero: lines the detail may wrap to (then "..")
};

struct UiLayout {
  int scale = 1;  // base text scale
  int top_h = 0, header_h = 0, bottom_h = 0;
  int body_cols = 0, body_rows = 0;
  int main_y = 0, main_h = 0;  // area between the bars (used for images)
  int hero_cols = 0;  // characters per hero caption line
};

class Ui {
 public:
  explicit Ui(Display& display);

  // Renders bands whose inputs changed since the last call and flushes them.
  void render(const UiModel& model);
  // Forces a full redraw on the next render (after something else drew).
  void invalidate();
  void snap_transition();
  bool transitioning() const { return motion_active_; }
  const UiLayout& layout() const { return layout_; }
  // The legacy/image safe area: whole rectangular panel, or inscribed square.
  // The 466px round companion face additionally draws in the safe perimeter.
  const DisplayInfo& area() const { return info_; }
  // A canvas over that area, and a flush of its rows [y0, y1).
  Canvas canvas();
  void flush(int y0, int y1);
  // Body text rows visible on a text screen for this model (after detail lines).
  int body_rows(const UiModel& m) const;
  UiRect control_rect(TouchControl control, const UiModel& m) const;
  TouchControl control_hit(int x, int y, const UiModel& m) const;
  // Diagnostics expose the actual decoded frame, not the requested activity.
  const char* expression_name() const;
  int expression_frame() const { return face_index_; }
  std::vector<std::string> body_lines(std::string_view text, const UiModel& m) const;
  bool round_companion() const { return panel_.round && panel_.width == 466 && panel_.height == 466; }
  bool title_hit(int x, int y) const {
    if (round_companion()) return x >= 150 && x < 316 && y >= 45 && y < 92;
    return x >= ox_ && x < ox_ + info_.width && y >= oy_ && y < oy_ + layout_.top_h;
  }

 private:
  uint16_t background() const { return panel_.round ? 0 : rgb565(10, 14, 20); }
  bool companion_model(const UiModel& m) const;
  // Pairing, local settings (not quick controls) and Wi-Fi setup: local screens that keep
  // their own input semantics; the round companion draws them in its own design.
  static bool local_screen(const UiModel& m) {
    return !m.quick_controls && (m.screen == Screen::Pairing || m.screen == Screen::Settings || m.screen == Screen::Setup);
  }
  void render_local(Canvas& c, const UiModel& m);
  static constexpr UiRect kQuickSilence{74,340,154,48}, kQuickStop{238,340,154,48}, kQuickSettings{163,398,140,40};
  static UiRect prompt_answer_rect(bool yes) { return yes ? UiRect{238,296,150,96} : UiRect{78,296,150,96}; }
  // The 466px companion's shared bottom action row (Home, recording and reading):
  // at most two targets, in priority order. Drawing and hit testing both use it.
  int action_slots(const UiModel& m, TouchControl (&slots)[2]) const;
  void render_companion(const UiModel& m);
  void draw_top(Canvas& c, const UiModel& m);
  void draw_header(Canvas& c, const UiModel& m);
  void draw_content(Canvas& c, const UiModel& m);
  void draw_bottom(Canvas& c, const UiModel& m);
  void draw_touch_controls(Canvas& c, const UiModel& m);
  void draw_indicator(Canvas& c, const UiModel& m, int cx, int cy, int r);
  struct HeroGeom {
    int size = 0, x = 0, y = 0;  // mascot
    int caption_y = 0, buttons_y = 0;
    std::vector<std::string> detail;  // wrapped, already truncated
  };
  HeroGeom hero_geom(const UiModel& m) const;
  void draw_hero(Canvas& c, const UiModel& m);
  // Rows [y0, y1) that hero animations may touch for this screen.
  void hero_anim_rows(const UiModel& m, int& y0, int& y1) const;

  Display& display_;
  DisplayInfo panel_;
  DisplayInfo info_;
  int ox_ = 0, oy_ = 0;  // area origin on the panel
  UiLayout layout_;
  uint32_t hash_[4] = {0, 0, 0, 0};
  uint32_t hero_static_ = 0, hero_anim_ = 0;
  bool hero_valid_ = false;
  bool companion_valid_ = false;
  // One packed gray2 frame, allocated only for the round companion.
  std::vector<uint8_t> face_current_;
  int face_target_ = -1, face_clip_ = 0, face_index_ = -1;
  uint32_t face_frame_ = 0;
  bool face_changed_ = false;
  void update_expression(const UiModel& m);
  void draw_expression(Canvas& c, int x, int y, int size) const;
  int motion_view_ = -1, motion_dx_ = 0, motion_dy_ = 0;
  uint32_t motion_start_ = 0, motion_navigation_ = 0;
  bool motion_active_ = false, motion_flush_ = false;
  uint32_t row_hash_[466] = {};  // 1,864 bytes, no second framebuffer
  void render_motion(const UiModel& m);
  uint32_t companion_hash_ = 0;
  TouchControl companion_pressed_ = TouchControl::None;
  int companion_level_ = -1;
  bool valid_ = false;
};

}  // namespace hg
