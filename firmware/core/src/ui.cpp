#include "hg/ui.hpp"

#include <algorithm>
#include <cstring>
#include <vector>

#include "hg/font.hpp"
#include "hg/expression_assets.hpp"

namespace hg {
namespace {

constexpr uint16_t kBar = rgb565(24, 31, 42);
constexpr uint16_t kText = rgb565(232, 238, 242);
constexpr uint16_t kDim = rgb565(132, 146, 160);
constexpr uint16_t kFaint = rgb565(52, 62, 76);
constexpr uint16_t kAccent = rgb565(242, 179, 61);
constexpr uint16_t kGreen = rgb565(61, 214, 140);
constexpr uint16_t kBlue = rgb565(90, 169, 242);
constexpr uint16_t kRed = rgb565(242, 95, 92);
constexpr uint16_t kYellow = rgb565(242, 201, 76);
constexpr uint16_t kGreenDim = rgb565(28, 92, 62);
constexpr uint16_t kBlueDim = rgb565(52, 96, 140);
constexpr uint16_t kAccentDim = rgb565(110, 82, 30);
constexpr uint16_t kRedDim = rgb565(122, 44, 44);

class Hash {
 public:
  Hash& add(const void* data, size_t len) {
    const uint8_t* p = static_cast<const uint8_t*>(data);
    for (size_t i = 0; i < len; ++i) {
      h_ ^= p[i];
      h_ *= 16777619u;
    }
    return *this;
  }
  Hash& add(const std::string& s) {
    add(s.data(), s.size());
    uint8_t sep = 0xFF;
    return add(&sep, 1);
  }
  template <typename T>
  Hash& val(T v) {
    return add(&v, sizeof(v));
  }
  uint32_t get() const { return h_; }

 private:
  uint32_t h_ = 2166136261u;
};

std::string fit(std::string_view s, int max_chars) {
  if (max_chars <= 0) return {};
  if (static_cast<int>(s.size()) <= max_chars) return std::string(s);
  if (max_chars <= 2) return std::string(s.substr(0, static_cast<size_t>(max_chars)));
  return std::string(s.substr(0, static_cast<size_t>(max_chars - 2))) + "..";
}

int cols_for(int width_px, int scale) { return width_px / (font::kCellWidth * scale); }

bool animated(Screen s) {
  switch (s) {
    case Screen::Boot:
    case Screen::Connecting:
    case Screen::Updating:
    case Screen::Ready:
    case Screen::Listening:
    case Screen::Thinking:
    case Screen::Responding:
      return true;
    default:
      return false;
  }
}

// Triangle wave in [0, period/2] for gentle pulsing.
int tri(uint32_t frame, int period) {
  int p = static_cast<int>(frame % static_cast<uint32_t>(period));
  return p < period / 2 ? p : period - p;
}

mascot::Frame mascot_frame(const UiModel& m) {
  if (m.screen == Screen::Responding && m.speaking) {
    return (m.frame / 2) % 2 ? mascot::Frame::Talk : mascot::Frame::Idle;
  }
  return m.frame % 45 < 2 ? mascot::Frame::Blink : mascot::Frame::Idle;  // blink every ~4.5 s
}

// Everything that changes hero pixels between frames, and nothing else, so
// a still mascot never triggers a redraw.
uint32_t hero_anim_key(const UiModel& m) {
  Hash h;
  h.val(mascot_frame(m));
  switch (m.screen) {
    case Screen::Listening: h.val(m.frame % 3).val(m.level / 20); break;
    case Screen::Thinking:
    case Screen::Connecting:
    case Screen::Updating: h.val((m.frame / 2) % 4); break;
    case Screen::Responding: h.val((m.frame / 2) % 3); break;
    default: break;
  }
  return h.get();
}

uint16_t caption_color(Screen s) {
  switch (s) {
    case Screen::Listening: return kGreen;
    case Screen::Thinking: return kBlue;
    case Screen::Responding:
    case Screen::Connecting:
    case Screen::Updating:
    case Screen::Pairing:
    case Screen::Prompt: return kAccent;
    case Screen::Offline:
    case Screen::Error: return kRed;
    default: return kText;
  }
}

}  // namespace

const char* screen_name(Screen s) {
  switch (s) {
    case Screen::Boot: return "boot";
    case Screen::Offline: return "offline";
    case Screen::Connecting: return "connecting";
    case Screen::Pairing: return "pairing";
    case Screen::Ready: return "ready";
    case Screen::Listening: return "listening";
    case Screen::Thinking: return "thinking";
    case Screen::Responding: return "responding";
    case Screen::Card: return "card";
    case Screen::Image: return "image";
    case Screen::Error: return "error";
    case Screen::Prompt: return "prompt";
    case Screen::Updating: return "updating";
    case Screen::Settings: return "settings";
    case Screen::Setup: return "setup";
  }
  return "unknown";
}

Ui::Ui(Display& display) : display_(display), panel_(display.info()), info_(panel_) {
  if (panel_.round) {
    // The largest square inside the circle; the corners of the panel do not exist.
    const int side = std::min(panel_.width, panel_.height) * 707 / 1000;
    ox_ = (panel_.width - side) / 2;
    oy_ = (panel_.height - side) / 2;
    info_.width = info_.height = static_cast<uint16_t>(side);
  }
  int w = info_.width, h = info_.height;
  int s = std::max(1, std::min(4, std::min(w / 160, h / 120)));
  layout_.scale = s;
  layout_.top_h = Canvas::line_height(s) + 2 * s;
  layout_.bottom_h = layout_.top_h;
  layout_.header_h = Canvas::line_height(s + 1) + 4 * s;
  layout_.main_y = layout_.top_h;
  layout_.main_h = h - layout_.top_h - layout_.bottom_h;
  int margin = 4 * s;
  int content_h = h - layout_.top_h - layout_.header_h - layout_.bottom_h;
  layout_.body_cols = cols_for(w - 2 * margin, s);
  layout_.body_rows = std::max(1, (content_h - margin) / Canvas::line_height(s));

  // Hero layout: the mascot is sized per screen (see hero_geom).
  layout_.hero_cols = cols_for(w - 4 * s, s);
  if (round_companion()) {
    // Shared wrapping/scrolling contract, including legacy cards/settings.
    layout_.body_cols = cols_for(w - 16, 3);
    layout_.body_rows = 8;
  }
}

void Ui::invalidate() { valid_ = false; face_visible_ = false; }

Canvas Ui::canvas() {
  return Canvas(display_.framebuffer() + oy_ * panel_.width + ox_, info_.width, info_.height, info_.swap_bytes,
                panel_.width);
}

void Ui::flush(int y0, int y1) {
  display_.flush(static_cast<uint16_t>(y0 + oy_), static_cast<uint16_t>(y1 + oy_));
}

bool Ui::companion_model(const UiModel& m) const {
  return round_companion() && (m.quick_controls || m.touch_prompt ||
      m.screen == Screen::Ready || m.screen == Screen::Listening ||
      m.screen == Screen::Thinking || m.screen == Screen::Responding);
}

void Ui::render_companion(const UiModel& m) {
  // Expression entries blend from the LAST DRAWN pose. A target change always
  // renders the identical boundary frame, including reversal during a blend.
  using namespace expression;
  const bool visible = m.hero && !m.quick_controls && !m.touch_prompt;
  int target = m.screen == Screen::Listening ? 1 :
      m.speaking ? 0 : m.screen == Screen::Thinking ? 2 : m.reply_ready ? 3 : 0;
  // Retain a quiet periodic blink only at idle; never fake speech lip-sync.
  if (target == 0 && !m.speaking && m.screen == Screen::Ready && m.frame % 60 >= 44 && m.frame % 60 < 52)
    target = 4;
  bool face_changed = false;
  if (face_current_.empty()) {
    face_current_.assign(idle,idle+count);
    face_start_ = face_current_;
    face_target_ = 0;
    face_frame_ = m.frame;
  }
  if (visible) {
    if (target != face_target_) {
      face_start_ = face_current_;
      face_target_ = target;
      face_step_ = 0;
      face_frame_ = m.frame;
    } else if (face_visible_ && face_step_ < 8 && m.frame != face_frame_) {
      // Do not catch up skipped/sleep ticks in one frame: bounded visible delta.
      ++face_step_;
      const auto* dest = poses[target];
      for (int i=0;i<count;++i)
        face_current_[i] = (face_start_[i]*(8-face_step_) + dest[i]*face_step_ + 4)/8;
      face_changed = true;
    }
  }
  face_frame_ = m.frame;
  face_visible_ = visible;
  const uint32_t key = Hash().val(m.screen).val(m.link).val(m.hero)
      .add(m.headline).add(m.detail).add(m.body).add(m.hint).val(m.scroll)
      .val(m.quick_controls).val(m.touch_prompt).val(m.unread_reply).val(m.reply_ready)
      .val(m.volume).val(m.brightness).val(m.speaking).get();
  Canvas c(display_.framebuffer(), panel_.width, panel_.height, panel_.swap_bytes);
  const int level = (m.level/5)*5;
  auto draw_mascot = [&](bool patch_only = false) {
    const int y0 = patch_only ? expression::y : 0, y1 = patch_only ? expression::y+h : 192;
    const int x0 = patch_only ? expression::x : 0, x1 = patch_only ? expression::x+w : 192;
    for (int yy=y0;yy<y1;++yy) for (int xx=x0;xx<x1;++xx) {
      const bool patch = xx>=expression::x && xx<expression::x+w && yy>=expression::y && yy<expression::y+h;
      const uint8_t v = patch ? face_current_[(yy-expression::y)*w+xx-expression::x] : base[yy*192+xx];
      // One fixed neutral palette in every state, including idle and ready.
      c.pixel(137+xx,112+yy,rgb565(v,v,v));
    }
  };
  auto draw_level = [&]() {
    c.fill_rect(183,58,100,5,0);
    if (level) c.fill_round_rect(183,58,level,5,2,kAccent);
  };
  if (valid_ && companion_valid_ && key == companion_hash_) {
    // Static perimeter / typography are not redrawn for animation. No wrapping,
    // temporary strings, large arc rasterization or full-frame flush here.
    if (visible && face_changed) {
      draw_mascot(true);  // opaque patch writes erase every prior facial pixel
      display_.flush(112+expression::y,112+expression::y+h);
    }
    if (m.screen == Screen::Listening && level != companion_level_) {
      draw_level();
      display_.flush(58,63);
    }
    companion_level_ = level;
    return;
  }
  c.fill_rect(0, 0, 466, 466, 0);
  auto center = [&](int y, std::string_view text, int scale, uint16_t color) {
    c.text((466 - Canvas::text_width(text, scale))/2, y, text, scale, color);
  };
  // All marks lie inside radius 222. They are status, not touch targets.
  if (m.screen == Screen::Listening) {
    c.arc(233,233,218,3,-1,kAccentDim);
    c.arc(233,233,218,3, 1,kAccentDim);
    // Actual App::on_mic_samples level, quantized to reduce redraw churn.
    draw_level();
  } else if (m.speaking) {
    for (int r : {211,218}) {
      c.arc(233,233,r,2,-1,kAccentDim);
      c.arc(233,233,r,2, 1,kAccentDim);
    }
  } else if (m.screen == Screen::Thinking) {
    for (int x : {185,233,281}) c.fill_circle(x, x == 233 ? 19 : 25, 4, kAccentDim);
  }
  if (m.unread_reply) c.fill_round_rect(213,440,40,4,2,kAccentDim);

  if (m.hero) {
    center(72, m.link == Link::Online ? "HERMES" : "OFFLINE", 2, kDim);
    draw_mascot();
    center(310, fit(m.headline, 19), 3, kText);
    center(343, fit(m.detail, 28), 2, kDim);
    if (m.unread_reply) {
      const auto r = control_rect(TouchControl::Reply,m);
      c.fill_round_rect(r.x,r.y,r.w,r.h,16,kBar);
      const char* label = m.hint.find("Reply ready") == 0 ? "Reply ready" :
          m.hint.find("Reply stopped") == 0 ? "Reply stopped" : "New text";
      center(r.y+9,label,2,kText);
      center(r.y+32,"Tap to read",2,kDim);
    } else if (m.screen == Screen::Listening) {
      center(386,"Recording",2,kDim);
    } else if (m.hint.find("Up: Reply") == 0) {
      center(380,"Up: Reply",2,kDim);
      center(409,"Down: Controls",2,kDim);
    } else {
      center(386, fit(m.hint, 25), 2, kDim);
      if (m.screen == Screen::Ready) center(415,"Down: Controls",2,kDim);
    }
  } else {
    center(83, m.quick_controls ? "Controls" : fit(m.headline,19),3,kText);
    if (!m.quick_controls) {
      const int rows = body_rows(m), lh = Canvas::line_height(3);
      auto lines = wrap_text(m.body,layout_.body_cols);
      const int total = static_cast<int>(lines.size());
      const int last = std::max(0,total-rows);
      const int first = m.scroll < 0 ? last : std::min(m.scroll,last);
      int y = 126;
      if (!m.detail.empty()) {
        auto detail = wrap_text(m.detail,layout_.body_cols);
        const int count = std::min<int>(layout_.body_rows-rows,detail.size());
        for (int i=0; i<count; ++i, y+=lh) c.text(80,y,detail[i],3,kDim);
      }
      for (int i=0; i<rows && first+i<total; ++i)
        c.text(80,y+i*lh,lines[first+i],3,kText);
      if (total > rows) {
        const int height = rows*lh;
        const int thumb = std::max(8,height*rows/total);
        c.fill_rect(395,y,3,height,kFaint);
        c.fill_rect(395,y+(height-thumb)*first/std::max(1,last),3,thumb,kDim);
      }
    }
    // Use the exact same geometry as hit testing; this canvas is panel-local.
    for (unsigned i=1;i<=5;++i) {
      auto control = static_cast<TouchControl>(i);
      const auto r = control_rect(control,m);
      if (!r.w) continue;
      if (control == TouchControl::Volume || control == TouchControl::Brightness) {
        const int value = control == TouchControl::Volume ? m.volume : m.brightness;
        const char* label = control == TouchControl::Volume ? "Volume" : "Screen";
        c.text(r.x+(r.w-Canvas::text_width(label,2))/2,r.y-28,label,2,kText);
        c.fill_round_rect(r.x,r.y,r.w,r.h,14,kBar);
        const int travel = r.h-28;
        const int yy = r.y+14+travel*(100-value)/100;
        c.fill_rect(r.x+r.w/2-2,r.y+14,4,travel,kFaint);
        c.fill_round_rect(r.x+8,yy-5,r.w-16,10,5,kAccent);
        const auto pct = std::to_string(value);
        c.text(r.x+(r.w-Canvas::text_width(pct,2))/2,r.y+r.h+8,pct,2,kDim);
      } else {
        const char* label = control == TouchControl::Stop ? "Stop turn" : control == TouchControl::Yes ? "Yes" : "No";
        c.fill_round_rect(r.x,r.y,r.w,r.h,14,control == TouchControl::Yes ? kAccentDim : kBar);
        c.text(r.x+(r.w-Canvas::text_width(label,3))/2,r.y+(r.h-21)/2,label,3,kText);
      }
    }
    center(409,m.touch_prompt ? "Tap Yes or No" : "Right: Home",2,kDim);
  }
  display_.flush(0,panel_.height);
  companion_hash_ = key;
  companion_level_ = level;
  companion_valid_ = valid_ = true;
  hero_valid_ = false;
}

void Ui::render(const UiModel& m) {
  if (companion_model(m)) { render_companion(m); return; }
  face_visible_ = false;
  if (companion_valid_) { valid_ = false; companion_valid_ = false; }
  const int h = info_.height;
  if (!valid_ && (ox_ || oy_)) {
    // Round panel: everything outside the UI area stays the background colour.
    Canvas panel(display_.framebuffer(), panel_.width, panel_.height, panel_.swap_bytes);
    panel.fill_rect(0, 0, panel_.width, panel_.height, background());
    display_.flush(0, panel_.height);
  }
  Canvas c = canvas();
  const int y_header = layout_.top_h;
  const int y_content = y_header + layout_.header_h;
  const int y_bottom = h - layout_.bottom_h;

  uint32_t hashes[4];
  hashes[0] = Hash().add(m.title).val(m.link).get();
  hashes[1] = Hash()
                  .val(m.screen)
                  .add(m.headline)
                  .val(animated(m.screen) ? m.frame : 0u)
                  .val(m.screen == Screen::Listening ? m.level : uint8_t(0))
                  .val(m.speaking)
                  .get();
  hashes[2] = Hash().val(m.screen).add(m.detail).add(m.body).add(m.code).val(m.scroll).val(m.color_test)
      .val(m.quick_controls).val(m.touch_prompt).val(m.volume).val(m.brightness).get();
  hashes[3] = Hash().add(m.hint).val(m.unread_reply).get();

  if (m.hero) {
    // Hero mode: top bar, one mascot band, bottom bar.
    for (int i : {0, 3}) {
      if (valid_ && hash_[i] == hashes[i]) continue;
      int y0 = i == 0 ? 0 : y_bottom, y1 = i == 0 ? y_header : h;
      c.set_clip_rows(y0, y1);
      if (i == 0) draw_top(c, m);
      else draw_bottom(c, m);
      flush(y0, y1);
      hash_[i] = hashes[i];
    }
    uint32_t stat = Hash().val(m.screen).add(m.headline).add(m.detail).add(m.yes).add(m.no).val(m.caption_lines).get();
    uint32_t anim = hero_anim_key(m);
    int y0 = y_header, y1 = y_bottom;
    bool redraw = !valid_ || !hero_valid_ || stat != hero_static_;
    if (!redraw && anim != hero_anim_) {
      hero_anim_rows(m, y0, y1);  // only what can move
      redraw = true;
    }
    if (redraw) {
      c.set_clip_rows(y0, y1);
      draw_hero(c, m);
      flush(y0, y1);
    }
    hero_static_ = stat;
    hero_anim_ = anim;
    hero_valid_ = true;
    hash_[1] = hash_[2] = 0;  // header and content must repaint when hero mode ends
    valid_ = true;
    return;
  }
  hero_valid_ = false;

  struct Band {
    int y0, y1;
    void (Ui::*draw)(Canvas&, const UiModel&);
  };
  const Band bands[4] = {
      {0, y_header, &Ui::draw_top},
      {y_header, y_content, &Ui::draw_header},
      {y_content, y_bottom, &Ui::draw_content},
      {y_bottom, h, &Ui::draw_bottom},
  };
  for (int i = 0; i < 4; ++i) {
    // An image owns the area between the bars; the app draws and flushes it.
    if (m.screen == Screen::Image && (i == 1 || i == 2)) {
      hash_[i] = 0;
      continue;
    }
    if (valid_ && hash_[i] == hashes[i]) continue;
    c.set_clip_rows(bands[i].y0, bands[i].y1);
    (this->*bands[i].draw)(c, m);
    flush(bands[i].y0, bands[i].y1);
    hash_[i] = hashes[i];
  }
  valid_ = true;
}

void Ui::draw_top(Canvas& c, const UiModel& m) {
  const int s = layout_.scale;
  const int w = info_.width;
  c.fill_rect(0, 0, w, layout_.top_h, panel_.round ? background() : kBar);
  uint16_t dot = kRed;
  const char* label = "OFFLINE";
  switch (m.link) {
    case Link::Offline: dot = kRed; label = "NO NET"; break;
    case Link::Network: dot = kYellow; label = "NET"; break;
    case Link::Connecting: dot = kYellow; label = "LINK"; break;
    case Link::Online: dot = kGreen; label = "ONLINE"; break;
  }
  int ty = s;
  if (panel_.round) {
    // A round face stays quiet: just the link dot, centred, like a watch's status mark.
    int r = std::max(2, 3 * s / 2 + 1);
    c.fill_circle(w / 2, layout_.top_h / 2, r, dot);
    return;
  }
  int label_w = Canvas::text_width(label, s);
  int label_x = w - 3 * s - label_w;
  c.text(label_x, ty, label, s, kDim);
  int r = std::max(2, 3 * s / 2 + 1);
  c.fill_circle(label_x - 3 * s - r, layout_.top_h / 2, r, dot);
  int title_cols = cols_for(label_x - 6 * s - 2 * r - 3 * s, s);
  c.text(3 * s, ty, fit(m.title, title_cols), s, kText);
}

void Ui::draw_indicator(Canvas& c, const UiModel& m, int cx, int cy, int r) {
  const int s = layout_.scale;
  auto spinner = [&](uint16_t color) {
    int dot_r = std::max(1, r / 5);
    // Eight positions around the circle; precomputed unit vectors * 100.
    static const int kDx[8] = {0, 71, 100, 71, 0, -71, -100, -71};
    static const int kDy[8] = {-100, -71, 0, 71, 100, 71, 0, -71};
    int ring_r = r - dot_r;
    int head = static_cast<int>(m.frame % 8);
    for (int i = 0; i < 8; ++i) {
      int age = (head - i + 8) % 8;
      uint16_t col = age == 0 ? color : (age < 3 ? kDim : kFaint);
      c.fill_circle(cx + kDx[i] * ring_r / 100, cy + kDy[i] * ring_r / 100, dot_r, col);
    }
  };
  auto bars = [&](uint16_t color, int level_pct) {
    const int n = 5;
    int bw = std::max(3, (2 * r) / (2 * n - 1));
    int x0 = cx - (n * bw + (n - 1) * bw) / 2;
    for (int i = 0; i < n; ++i) {
      int jitter = static_cast<int>((m.frame * 3 + static_cast<uint32_t>(i) * 5) % 7);
      int pct = std::max(10, level_pct * (4 + jitter) / 10);
      int bh = std::max(2 * s, std::min(2 * r, 2 * r * pct / 100));
      c.fill_rect(x0 + i * 2 * bw, cy - bh / 2, bw, bh, color);
    }
  };

  switch (m.screen) {
    case Screen::Boot:
    case Screen::Connecting:
    case Screen::Updating:
      spinner(kAccent);
      break;
    case Screen::Thinking:
      spinner(kBlue);
      break;
    case Screen::Offline:
    case Screen::Error: {
      c.fill_circle(cx, cy, r, kRed);
      int tw = Canvas::text_width("!", s);
      c.text(cx - tw / 2, cy - (7 * s) / 2, "!", s, background());
      break;
    }
    case Screen::Pairing:
      c.ring(cx, cy, r, s + 1, kAccent);
      c.fill_circle(cx, cy, r / 3, kAccent);
      break;
    case Screen::Ready: {
      int pulse = tri(m.frame, 24);  // 0..12
      c.fill_circle(cx, cy, r * (8 + pulse / 3) / 12, kAccent);
      break;
    }
    case Screen::Listening:
      bars(kGreen, std::max<int>(m.level, 8));
      break;
    case Screen::Responding:
      if (m.speaking) {
        bars(kAccent, 40 + tri(m.frame, 8) * 10);
      } else {
        c.fill_circle(cx, cy, r * 2 / 3, kAccent);
      }
      break;
    case Screen::Card:
      c.fill_round_rect(cx - r, cy - r, 2 * r, 2 * r, r / 3, kAccent);
      break;
    case Screen::Prompt: {
      c.fill_circle(cx, cy, r, kAccent);
      int tw = Canvas::text_width("?", s);
      c.text(cx - tw / 2, cy - (7 * s) / 2, "?", s, background());
      break;
    }
    case Screen::Image:
    case Screen::Settings:
    case Screen::Setup:
      break;
  }
}

void Ui::draw_header(Canvas& c, const UiModel& m) {
  const int s = layout_.scale;
  const int y0 = layout_.top_h;
  const int hh = layout_.header_h;
  c.fill_rect(0, y0, info_.width, hh, background());
  int r = hh / 2 - 2 * s;
  int cx = 4 * s + r;
  int cy = y0 + hh / 2;
  draw_indicator(c, m, cx, cy, r);
  int tx = cx + r + 4 * s;
  int hs = s + 1;
  int cols = cols_for(info_.width - tx - 2 * s, hs);
  c.text(tx, cy - (font::kGlyphHeight * hs) / 2, fit(m.headline, cols), hs, kText);
  c.fill_rect(4 * s, y0 + hh - 1, info_.width - 8 * s, 1, kFaint);
}

int Ui::body_rows(const UiModel& m) const {
  int rows = layout_.body_rows;
  if (m.touch_prompt) rows = std::max(1, rows - (round_companion() ? 2 : 3));
  if (m.detail.empty()) return rows;
  int detail = static_cast<int>(wrap_text(m.detail, layout_.body_cols).size());
  int max_detail = m.body.empty() ? rows : std::min(2, rows - 1);
  return rows - std::max(0, std::min(detail, max_detail));
}

void Ui::draw_content(Canvas& c, const UiModel& m) {
  const int s = round_companion() ? 3 : layout_.scale;
  const int w = info_.width;
  const int y0 = layout_.top_h + layout_.header_h;
  const int y1 = info_.height - layout_.bottom_h;
  const int margin = 4 * s;
  const int lh = Canvas::line_height(s);
  c.fill_rect(0, y0, w, y1 - y0, background());
  int y = y0 + margin;

  if (m.quick_controls || m.touch_prompt) draw_touch_controls(c, m);
  if (m.quick_controls) return;

  if (m.color_test) {
    const uint16_t colors[] = {rgb565(255, 0, 0), rgb565(0, 255, 0), rgb565(0, 0, 255),
                               rgb565(255, 255, 255), rgb565(0, 0, 0)};
    for (int i = 0; i < 5; ++i) {
      const int left = w * i / 5, right = w * (i + 1) / 5;
      c.fill_rect(left, y0, right - left, y1 - y0, colors[i]);
    }
    return;
  }

  if (m.screen == Screen::Boot) {
    int big = s + 2;
    const char* name = "HERMES";
    int cy = (y0 + y1) / 2 - Canvas::line_height(big) / 2;
    c.text((w - Canvas::text_width(name, big)) / 2, cy, name, big, kAccent);
    int sy = cy + Canvas::line_height(big);
    c.text((w - Canvas::text_width("gadget", s)) / 2, sy, "gadget", s, kDim);
    if (!m.detail.empty()) {
      std::string d = fit(m.detail, layout_.body_cols);
      c.text((w - Canvas::text_width(d, s)) / 2, y1 - lh, d, s, kFaint);
    }
    return;
  }

  int rows = body_rows(m);
  if (!m.detail.empty()) {
    uint16_t dcol = m.screen == Screen::Error || m.screen == Screen::Offline ? kRed : kDim;
    if (m.screen == Screen::Thinking) dcol = kBlue;
    auto detail_lines = wrap_text(m.detail, layout_.body_cols);
    int shown = layout_.body_rows - rows;
    for (int i = 0; i < shown; ++i) {
      c.text(margin, y, detail_lines[static_cast<size_t>(i)], s, dcol);
      y += lh;
    }
  }
  if (m.body.empty() || rows <= 0) return;

  auto lines = wrap_text(m.body, layout_.body_cols);
  int total = static_cast<int>(lines.size());
  int max_first = std::max(0, total - rows);
  int first = m.scroll < 0 ? max_first : std::min(m.scroll, max_first);
  uint16_t col = m.screen == Screen::Ready ? kDim : kText;
  for (int i = 0; i < rows && first + i < total; ++i) {
    c.text(margin, y + i * lh, lines[static_cast<size_t>(first + i)], s, col);
  }
  if (total > rows) {
    // Scroll indicator along the right edge.
    int track_y = y, track_h = rows * lh;
    int thumb_h = std::max(2 * s, track_h * rows / total);
    int thumb_y = track_y + (track_h - thumb_h) * first / std::max(1, max_first);
    c.fill_rect(w - 2 * s, track_y, s, track_h, kFaint);
    c.fill_rect(w - 2 * s, thumb_y, s, thumb_h, kDim);
  }
}

Ui::HeroGeom Ui::hero_geom(const UiModel& m) const {
  HeroGeom g;
  const int s = layout_.scale, w = info_.width, lh = Canvas::line_height(s);
  const int cols = layout_.hero_cols;
  if (!m.detail.empty()) g.detail = wrap_text(m.detail, cols);
  const int buttons_h = m.yes.empty() && m.no.empty() ? 0 : lh + 6 * s;
  auto caption_h = [&](int lines) { return (1 + lines) * lh + s; };
  // Never shrink the mascot below the smallest bitmap: drop caption lines instead.
  const int smallest = mascot::pick(0, mascot::Frame::Idle)->size;
  int max_lines = std::max(1, static_cast<int>(m.caption_lines));
  while (max_lines > 1 && layout_.main_h - caption_h(max_lines) - buttons_h - 4 * s < smallest) --max_lines;
  if (static_cast<int>(g.detail.size()) > max_lines) {
    g.detail.resize(static_cast<size_t>(max_lines));
    std::string& last = g.detail.back();
    if (static_cast<int>(last.size()) + 2 > cols) last.resize(static_cast<size_t>(std::max(0, cols - 2)));
    last += "..";
  }
  // Reserve one detail line even when there is none, so the mascot keeps its size.
  const int ch = caption_h(std::max<int>(1, static_cast<int>(g.detail.size())));
  const int avail = std::min(w - 8 * s, layout_.main_h - ch - buttons_h - 4 * s);
  g.size = mascot::pick(avail, mascot::Frame::Idle)->size;
  const int block = g.size + 2 * s + ch + buttons_h;
  g.x = (w - g.size) / 2;
  g.y = layout_.main_y + std::max(s, (layout_.main_h - block) / 2);
  g.caption_y = g.y + g.size + 2 * s;
  g.buttons_y = g.caption_y + ch + 2 * s;
  return g;
}

void Ui::hero_anim_rows(const UiModel& m, int& y0, int& y1) const {
  const HeroGeom g = hero_geom(m);
  const int size = g.size, my = g.y;
  const mascot::Anchors& a = mascot::anchors();
  int top = my + size * a.eyes_y0 / 1000, bottom = my + size * a.eyes_y1 / 1000;
  auto add = [&](int lo, int hi) {
    top = std::min(top, lo);
    bottom = std::max(bottom, hi);
  };
  const int reach = size * 280 / 1000;  // outermost wave radius + stroke
  switch (m.screen) {
    case Screen::Listening: {
      int ey = my + size * a.ear_cup.y / 1000;
      add(ey - reach, ey + reach);
      break;
    }
    case Screen::Responding: {
      int mouth = my + size * a.mouth.y / 1000;
      add(my + size * a.mouth_y0 / 1000, my + size * a.mouth_y1 / 1000);
      add(mouth - reach, mouth + reach);
      break;
    }
    case Screen::Thinking:
    case Screen::Connecting:
    case Screen::Updating: {
      int ty = my + size * a.head_top_right.y / 1000;
      add(ty - size / 6, ty + size / 12);
      break;
    }
    default: break;
  }
  y0 = std::max(top - 1, layout_.top_h);
  y1 = std::min(bottom + 2, static_cast<int>(info_.height) - layout_.bottom_h);
}

void Ui::draw_hero(Canvas& c, const UiModel& m) {
  const int s = layout_.scale;
  const int w = info_.width;
  const int y0 = layout_.top_h;
  const int y1 = info_.height - layout_.bottom_h;
  const int lh = Canvas::line_height(s);
  c.fill_rect(0, y0, w, y1 - y0, background());

  const HeroGeom g = hero_geom(m);
  const int size = g.size, mx = g.x, my = g.y;
  const mascot::Anchors& a = mascot::anchors();
  if (const mascot::Bitmap* b = mascot::pick(size, mascot_frame(m))) {
    c.bitmap1(mx, my, b->size, b->size, b->bits, kText);
  }
  const int stroke = std::max(2, size / 48);
  auto waves = [&](int cx, int cy, int dir, int lit, int phase, uint16_t on, uint16_t dim, int r0) {
    for (int i = 0; i < 3; ++i) {
      int r = size * (r0 + 60 * i) / 1000;
      uint16_t col = i >= lit ? kFaint : (i == phase ? on : dim);
      c.arc(cx, cy, r, stroke, dir, col);
    }
  };
  auto dots = [&](uint16_t on, uint16_t dim) {
    int r = std::max(2, size / 30);
    int gap = 3 * r;
    int tx = mx + size * a.head_top_right.x / 1000;
    int ty = my + size * a.head_top_right.y / 1000;
    int active = static_cast<int>((m.frame / 2) % 4);
    for (int i = 0; i < 3; ++i) {
      c.fill_circle(tx + i * gap, ty - i * gap / 2, r, i == active ? on : dim);
    }
  };
  switch (m.screen) {
    case Screen::Listening: {
      int lit = 1 + std::min(2, m.level / 34);
      waves(mx + size * a.ear_cup.x / 1000, my + size * a.ear_cup.y / 1000, +1, lit,
            static_cast<int>(m.frame % 3), kGreen, kGreenDim, 90);
      break;
    }
    case Screen::Responding:
      if (m.speaking) {
        // Start outside the face outline so the waves read as sound, not as lines on her cheek.
        waves(mx + size * a.mouth.x / 1000, my + size * a.mouth.y / 1000, -1, 3,
              static_cast<int>((m.frame / 2) % 3), kAccent, kAccentDim, 130);
      }
      break;
    case Screen::Thinking: dots(kBlue, kBlueDim); break;
    case Screen::Connecting:
    case Screen::Updating: dots(kAccent, kAccentDim); break;
    default: break;
  }

  // Caption: headline, then the detail lines, centred.
  const int cols = layout_.hero_cols;
  std::string head = fit(m.headline, cols);
  int cy = g.caption_y;
  c.text((w - Canvas::text_width(head, s)) / 2, cy, head, s, caption_color(m.screen));
  for (const auto& line : g.detail) {
    cy += lh;
    c.text((w - Canvas::text_width(line, s)) / 2, cy, line, s, kDim);
  }

  // Answer buttons (Prompt screen): TALK on the left, CANCEL on the right.
  if (!m.yes.empty() || !m.no.empty()) {
    const int bh = lh + 4 * s, gap = 4 * s, margin = 4 * s;
    const int bw = (w - 2 * margin - gap) / 2;
    auto button = [&](int x, const std::string& label, uint16_t fill) {
      c.fill_round_rect(x, g.buttons_y, bw, bh, 3 * s, fill);
      std::string t = fit(label, cols_for(bw - 2 * s, s));
      c.text(x + (bw - Canvas::text_width(t, s)) / 2, g.buttons_y + 2 * s + s / 2, t, s, kText);
    };
    if (!m.yes.empty()) button(margin, m.yes, kGreenDim);
    if (!m.no.empty()) button(margin + bw + gap, m.no, kRedDim);
  }
}

UiRect Ui::control_rect(TouchControl control, const UiModel& m) const {
  if (round_companion()) {
    if (control == TouchControl::Reply && m.unread_reply) return {117,370,232,56};
    if (m.quick_controls) {
      if (control == TouchControl::Volume && m.volume >= 0) return {121,170,68,136};
      if (control == TouchControl::Brightness && m.brightness >= 0) return {277,170,68,136};
      if (control == TouchControl::Stop) return {145,340,176,56};
    }
    if (m.touch_prompt) {
      if (control == TouchControl::Yes) return {83,322,144,64};
      if (control == TouchControl::No) return {239,322,144,64};
    }
    return {};
  }
  const int s = layout_.scale, w = info_.width;
  const int bottom = info_.height - layout_.bottom_h;
  const int bh = Canvas::line_height(s) + 8*s, margin = 4*s;
  if (control == TouchControl::Reply && m.unread_reply)
    return {ox_, oy_+bottom, w, layout_.bottom_h};
  if (m.quick_controls) {
    if ((control == TouchControl::Volume && m.volume >= 0) ||
        (control == TouchControl::Brightness && m.brightness >= 0)) {
      const int x = control == TouchControl::Volume ? w/4 : w*3/4;
      const int top = layout_.top_h + layout_.header_h + 18*s;
      return {ox_+x-12*s, oy_+top, 24*s, std::max(12*s, bottom-bh-10*s-top)};
    }
    if (control == TouchControl::Stop) return {ox_+w/4, oy_+bottom-bh-2*s, w/2, bh};
  }
  if (m.touch_prompt && (control == TouchControl::Yes || control == TouchControl::No)) {
    const int bw = (w-3*margin)/2;
    return {ox_+margin+(control == TouchControl::No ? bw+margin : 0), oy_+bottom-bh-2*s, bw, bh};
  }
  return {};
}

TouchControl Ui::control_hit(int x, int y, const UiModel& m) const {
  for (unsigned i = 1; i <= 6; ++i) {
    auto control = static_cast<TouchControl>(i);
    if (control_rect(control, m).contains(x,y)) return control;
  }
  return TouchControl::None;
}

void Ui::draw_touch_controls(Canvas& c, const UiModel& m) {
  const int s = layout_.scale;
  for (unsigned i = 1; i <= 5; ++i) {
    auto control = static_cast<TouchControl>(i);
    auto r = control_rect(control, m);
    if (!r.w || !r.h) continue;
    r.x -= ox_; r.y -= oy_;
    if (control == TouchControl::Volume || control == TouchControl::Brightness) {
      int value = control == TouchControl::Volume ? m.volume : m.brightness;
      const char* label = control == TouchControl::Volume ? "Volume" : "Light";
      c.text(r.x+(r.w-Canvas::text_width(label,s))/2, r.y-14*s, label, s, kText);
      c.fill_round_rect(r.x,r.y,r.w,r.h,3*s,kFaint);
      int fill = std::max(2, r.h*value/100);
      c.fill_rect(r.x+2*s,r.y+r.h-fill,r.w-4*s,fill,kAccentDim);
      c.fill_rect(r.x+2*s,r.y+r.h-fill,r.w-4*s,2*s,kAccent);
      std::string pct = std::to_string(value);
      c.text(r.x+(r.w-Canvas::text_width(pct,s))/2,r.y+r.h/2-4*s,pct,s,kText);
    } else {
      const char* label = control == TouchControl::Stop ? "Stop" : control == TouchControl::Yes ? "Yes" : "No";
      c.fill_round_rect(r.x,r.y,r.w,r.h,3*s,control == TouchControl::Yes ? kGreenDim : kRedDim);
      c.text(r.x+(r.w-Canvas::text_width(label,s))/2,r.y+(r.h-7*s)/2,label,s,kText);
    }
  }
}

void Ui::draw_bottom(Canvas& c, const UiModel& m) {
  const int s = layout_.scale;
  const int y0 = info_.height - layout_.bottom_h;
  c.fill_rect(0, y0, info_.width, layout_.bottom_h, m.unread_reply ? kBar : panel_.round ? background() : kBar);
  std::string hint = fit(m.hint, cols_for(info_.width - 4 * s, s));
  c.text((info_.width - Canvas::text_width(hint, s)) / 2, y0 + s, hint, s, m.unread_reply ? kText : kDim);
}

}  // namespace hg
