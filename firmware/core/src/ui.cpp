#include "hg/ui.hpp"

#include <algorithm>
#include <cstring>
#include <new>
#include <vector>

#include "hg/font.hpp"
#include "hg/geist.hpp"
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

uint16_t stage_color(const std::string& stage) {
  if (stage == "finished") return rgb565(132,196,152);
  if (stage == "failed") return rgb565(226,124,112);
  if (stage == "cancelled") return rgb565(212,164,92);
  if (stage == "running") return rgb565(128,168,224);
  return rgb565(164,164,169);
}

}  // namespace

const char* stage_word(const std::string& stage) {
  if (stage == "finished") return "Finished";
  if (stage == "failed") return "Failed";
  if (stage == "cancelled") return "Stopped";
  if (stage == "running") return "Working";
  return "Unknown";
}

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

const char* control_name(TouchControl c) {
  static const char* const names[kTouchControls] = {"none", "volume", "brightness", "stop", "yes", "no", "reply",
      "silence", "discard", "finish", "talk", "controls", "home", "settings", "recent", "work0", "work1", "work2", "next"};
  const auto i = static_cast<unsigned>(c);
  return i < kTouchControls ? names[i] : "none";
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
    layout_.body_rows = 7;  // reading keeps the bottom action row (Talk, Silence, Stop work) clear
  }
}

void Ui::invalidate() { valid_ = false; }

Canvas Ui::canvas() {
  return Canvas(display_.framebuffer() + oy_ * panel_.width + ox_, info_.width, info_.height, info_.swap_bytes,
                panel_.width);
}

void Ui::flush(int y0, int y1) {
  display_.flush(static_cast<uint16_t>(y0 + oy_), static_cast<uint16_t>(y1 + oy_));
}

bool Ui::companion_model(const UiModel& m) const {
  return round_companion() && (m.quick_controls || m.touch_prompt || local_screen(m) ||
      m.screen == Screen::Ready || m.screen == Screen::Listening ||
      m.screen == Screen::Thinking || m.screen == Screen::Responding ||
      m.screen == Screen::Offline || m.screen == Screen::Connecting || m.screen == Screen::Error);
}

const char* Ui::expression_name() const {
  return round_companion() && face_index_ >= 0 ? expression::names[face_clip_] : "legacy";
}

void Ui::update_expression(const UiModel& m) {
  using namespace expression;
  face_changed_ = false;
  const int target = m.expression;
  auto start = [&](int clip) {
    face_clip_ = clip;
    face_index_ = -1;
    face_frame_ = m.frame;
  };
  if (target != face_target_) {
    // Exit clips require the authored hold anchor. Never finish a stale entry
    // just to earn an exit, and never delay live recording/speech/approval.
    const bool held = face_index_ == clips[face_clip_].count-1;
    int exit = -1;
    if (held && face_clip_ == 2) exit = 3;
    if (held && face_clip_ == 5) exit = 6;
    if (held && face_clip_ == 7) exit = 8;
    if (held && face_clip_ == 9) exit = 10;
    if (face_clip_ == 12 || (held && face_clip_ == 11)) exit = 13;
    face_target_ = target;
    start((target == 0 && exit >= 0) ? exit : target);
  }
  auto elapsed = (m.frame-face_frame_)/ticks_per_frame;
  auto clip = clips[face_clip_];
  if (elapsed >= clip.count) {
    if (face_clip_ == 11) {
      start(12);  // asleep loop, only during existing dimmed idle period
    } else if (face_clip_ == 3 || face_clip_ == 6 || face_clip_ == 8 ||
               face_clip_ == 10 || face_clip_ == 13) {
      start(face_target_);
    }
    clip = clips[face_clip_];
    elapsed = (m.frame-face_frame_)/ticks_per_frame;
  }
  const bool loop = face_clip_ == 0 || face_clip_ == 1 || face_clip_ == 4 || face_clip_ == 12;
  const int index = loop ? elapsed % clip.count : std::min<uint32_t>(elapsed,clip.count-1);
  if (index == face_index_) return;
  face_index_ = index;
  if (face_current_.empty()) face_current_.resize(count/4);
  const auto frame = clip.first+index;
  auto p = offsets[frame];
  const auto end = offsets[frame+1];
  size_t pos = 0;
  // Bounded independent-frame LZ decoder. No allocation after the first frame,
  // no recursion, no MP4 decoder and no previous-frame dependency.
  while (p < end && pos < face_current_.size()) {
    const uint8_t token = data[p++];
    const size_t len = token < 128 ? token+1 : (token&127)+3;
    if (len > face_current_.size()-pos) break;
    if (token < 128) {
      if (len > end-p) break;
      std::memcpy(face_current_.data()+pos,data+p,len);
      p += len; pos += len;
    } else {
      if (end-p < 2) break;
      const size_t distance = data[p] | (static_cast<size_t>(data[p+1])<<8);
      p += 2;
      if (!distance || distance > pos) break;
      for (size_t j=0;j<len;++j,++pos) face_current_[pos] = face_current_[pos-distance];
    }
  }
  if (pos != face_current_.size() || p != end)
    std::fill(face_current_.begin(),face_current_.end(),0);  // fail closed
  face_changed_ = true;
}

void Ui::draw_expression(Canvas& c, int x, int y, int size) const {
  for (int yy=0;yy<size;++yy) for (int xx=0;xx<size;++xx) {
    const int index = (yy*expression::size/size)*expression::size+xx*expression::size/size;
    const uint8_t packed = face_current_[index/4];
    const uint8_t value = ((packed >> (6-2*(index&3))) & 3)*85;
    c.pixel(x+xx,y+yy,rgb565(value,value,value));
  }
}

void Ui::snap_transition() {
  if (motion_active_) { motion_active_ = false; valid_ = false; }
}

void Ui::render_motion(const UiModel& m) {
  // Arrival motion, not a second scene: destination owns input from the first tick.
  // 220ms cubic ease-out, 32px travel. The destination is drawn once; frames are shifted copies.
  const bool urgent = m.capture || m.touch_prompt || m.speaking || m.screen == Screen::Error ||
      m.screen == Screen::Offline || m.screen == Screen::Connecting || local_screen(m);
  const int view = urgent ? -1 : m.recent ? 3 : m.result ? 4 : m.quick_controls ? 2 : m.hero ? 0 : 1;
  if (view != motion_view_) {
    if (view >= 0 && motion_view_ >= 0 && valid_ && m.navigation != motion_navigation_) {
      motion_active_ = true; motion_start_ = m.time_ms; motion_frames_ = 0; motion_cache_ready_ = false;
      const bool vertical = view == 0 || motion_view_ == 0;
      motion_dx_ = vertical ? 0 : (view > motion_view_ ? 32 : -32);
      motion_dy_ = vertical ? (view == 2 || motion_view_ == 1 ? -32 : 32) : 0;
    } else snap_transition();
    motion_view_ = view;
  }
  motion_navigation_ = m.navigation;
  if (urgent) snap_transition();
  if (!motion_active_) { render_companion(m); return; }
  constexpr int W = 466;
  auto* fb = display_.framebuffer();
  // Lit columns [lo, hi) of every row of `buf`; lo == hi when the row is black.
  auto lit = [](const uint16_t* buf, int16_t* lo, int16_t* hi) {
    for (int y = 0; y < W; ++y) {
      const auto* r = buf + y * W;
      int a = 0; while (a < W && !r[a]) ++a;
      int b = W; while (b > a && !r[b-1]) --b;
      lo[y] = static_cast<int16_t>(a); hi[y] = static_cast<int16_t>(a == W ? a : b);
    }
  };
  const bool first = !motion_cache_ready_;
  if (first) {
    if (!motion_cache_) motion_cache_.reset(new (std::nothrow) uint16_t[W*W]);
    if (!motion_cache_) { snap_transition(); render_companion(m); return; }
    lit(fb, shown_lo_, shown_hi_);  // what the glass shows now
    valid_ = false; motion_flush_ = true;
    render_companion(m);
    motion_flush_ = false;
    std::memcpy(motion_cache_.get(), fb, W*W*2);
    lit(motion_cache_.get(), motion_lo_, motion_hi_);
    if (!motion_span_[W/2]) for (int y=0;y<W;++y) {
      const int d = y-233, r2 = 233*233-d*d;
      int h = 0; while ((h+1)*(h+1) <= r2) ++h;
      motion_span_[y] = static_cast<int16_t>(h);
    }
    motion_cache_ready_ = true;
  }
  const uint32_t elapsed = std::min<uint32_t>(220,m.time_ms-motion_start_);
  const int remaining = 220-elapsed;
  const int dx = motion_dx_*remaining*remaining*remaining/(220*220*220);
  const int dy = motion_dy_*remaining*remaining*remaining/(220*220*220);
  if (elapsed == 220) {
    // Land on a fresh static render, so live changes during the slide are not lost.
    valid_ = false; motion_flush_ = true;
    render_companion(m);
    motion_flush_ = false;
    int16_t lo[W], hi[W];
    lit(fb, lo, hi);
    for (int y = 0; y < W; ++y) {
      const int16_t a = lo[y], b = hi[y];
      if (shown_hi_[y] > shown_lo_[y]) {
        lo[y] = b > a ? std::min(a, shown_lo_[y]) : shown_lo_[y];
        hi[y] = b > a ? std::max(b, shown_hi_[y]) : shown_hi_[y];
      }
    }
    flush_bands(lo, hi);
  } else {
    compose_motion(dx, dy, first);
  }
  ++motion_frames_;
  if (elapsed==220) { motion_active_=false; motion_cache_ready_=false; motion_report_=motion_frames_; }
}

void Ui::compose_motion(int dx, int dy, bool dirty) {
  // The panel becomes the cache shifted by (dx,dy). Pixels outside the round glass stay
  // true black. Only columns lit before or after this frame are rewritten and sent; with
  // `dirty` the destination's own (unshifted) columns are rewritten too, since the first
  // frame drew the destination straight into the framebuffer.
  constexpr int W = 466;
  auto* fb = display_.framebuffer();
  const uint16_t* cache = motion_cache_.get();
  int16_t send_lo[W], send_hi[W];
  for (int y = 0; y < W; ++y) {
    auto* row = fb + y * W;
    const int sy = y - dy, h = motion_span_[y];
    int lo = W, hi = W;  // new lit columns
    if (sy >= 0 && sy < W && motion_hi_[sy] > motion_lo_[sy]) {
      lo = std::max({233 - h, motion_lo_[sy] + dx, 0});
      hi = std::min({233 + h + 1, motion_hi_[sy] + dx, W});
      if (hi <= lo) lo = hi = W;
    }
    // Columns to send: the new content plus whatever was lit on the glass.
    int s0 = lo, s1 = hi;
    if (shown_hi_[y] > shown_lo_[y]) {
      s0 = hi > lo ? std::min<int>(lo, shown_lo_[y]) : shown_lo_[y];
      s1 = hi > lo ? std::max<int>(hi, shown_hi_[y]) : shown_hi_[y];
    }
    // Columns to rewrite: those, plus the unshifted destination on the first frame.
    int w0 = s0, w1 = s1;
    if (dirty && motion_hi_[y] > motion_lo_[y]) {
      const bool any = w1 > w0;
      w0 = any ? std::min<int>(w0, motion_lo_[y]) : motion_lo_[y];
      w1 = any ? std::max<int>(w1, motion_hi_[y]) : motion_hi_[y];
    }
    if (w1 > w0) {
      std::fill(row + w0, row + w1, 0);
      if (hi > lo) std::memcpy(row + lo, cache + sy * W + lo - dx, static_cast<size_t>(hi - lo) * 2);
    }
    send_lo[y] = static_cast<int16_t>(s0); send_hi[y] = static_cast<int16_t>(s1);
    shown_lo_[y] = static_cast<int16_t>(lo); shown_hi_[y] = static_cast<int16_t>(hi);
  }
  flush_bands(send_lo, send_hi);
}

void Ui::flush_bands(const int16_t* lo, const int16_t* hi) {
  // Group rows into bands of similar column spans and send each band's rectangle.
  // A few wide rectangles beat many narrow ones: every flush costs a window setup.
  constexpr int W = 466, kSlack = 48, kMaxRows = 96;
  int b0 = -1, blo = 0, bhi = 0;
  auto send = [&](int y1) {
    if (b0 >= 0) display_.flush_rect(static_cast<uint16_t>(blo), static_cast<uint16_t>(b0),
                                     static_cast<uint16_t>(bhi), static_cast<uint16_t>(y1));
    b0 = -1;
  };
  for (int y = 0; y < W; ++y) {
    if (hi[y] <= lo[y]) { send(y); continue; }
    if (b0 >= 0 && (y - b0 >= kMaxRows || std::abs(lo[y] - blo) > kSlack || std::abs(hi[y] - bhi) > kSlack))
      send(y);
    if (b0 < 0) { b0 = y; blo = lo[y]; bhi = hi[y]; }
    else { blo = std::min<int>(blo, lo[y]); bhi = std::max<int>(bhi, hi[y]); }
  }
  send(W);
}

void Ui::render_companion(const UiModel& m) {
  constexpr uint16_t text = rgb565(240,239,235), dim = rgb565(164,164,169);
  constexpr uint16_t surface = rgb565(32,32,35), amber = rgb565(212,164,92);
  constexpr uint16_t lit = rgb565(56,56,61), ink = rgb565(23,19,13);
  const bool visible = m.hero && !m.quick_controls && !m.touch_prompt;
  const uint32_t key = Hash().val(m.screen).val(m.link).val(m.hero)
      .add(m.headline).add(m.detail).add(m.body).add(m.hint).val(m.scroll)
      .val(m.quick_controls).val(m.touch_prompt).val(m.prompt_unread).val(m.unread_reply).val(m.reply_ready)
      .val(m.volume).val(m.brightness).val(m.speaking).val(m.has_reply).val(m.can_stop)
      .val(m.can_silence).val(m.stop_pending).val(m.capture).val(m.talk_control).val(m.tap_talk)
      .val(m.settings_ready).val(m.work_available).val(m.recent).val(m.result)
      .val(m.work_page).val(m.work_pages)
      .add(m.work_rows.empty() ? "" : m.work_rows[0]).add(m.work_rows.size()>1 ? m.work_rows[1] : "")
      .add(m.work_rows.size()>2 ? m.work_rows[2] : "").add(m.outcome).add(m.outcome_word)
      .add(m.code).add(m.value).val(m.color_test).add(m.title).get();
  Canvas c(display_.framebuffer(),panel_.width,panel_.height,panel_.swap_bytes);
  const int level = (m.level/5)*5;
  auto portrait = [&]() { draw_expression(c,137,96,192); };
  auto meter = [&]() {
    c.fill_rect(183,78,100,4,0);
    if(level) c.fill_round_rect(183,78,level,4,2,amber);
  };
  // A press changes only the touched target: redraw the frame, flush just its rows.
  const bool same = valid_ && companion_valid_ && key==companion_hash_;
  const bool press_only = same && m.pressed!=companion_pressed_;
  if(same && !press_only) {
    // Idle updates send only the columns they touch, not whole panel rows.
    if(visible && face_changed_ && m.screen!=Screen::Pairing) { portrait(); display_.flush_rect(137,96,329,288); }
    if(m.screen==Screen::Pairing && face_changed_) { draw_expression(c,185,92,96); display_.flush_rect(185,92,281,188); }
    if(m.screen==Screen::Listening && level!=companion_level_) { meter(); display_.flush_rect(183,78,283,82); }
    companion_level_=level;
    return;
  }
  c.fill_rect(0,0,466,466,0);
  auto center = [&](int y,std::string_view label,int size,uint16_t color,uint16_t bg=0) {
    const auto fitted=geist::fit(label,320,size);
    geist::text(c,(466-geist::width(fitted,size))/2,y,fitted,size,color,bg);
  };
  // Every target is drawn from control_rect, the same rectangle hit testing uses.
  // Available actions are filled; unavailable ones stay in place, outlined and dimmed.
  // A finger resting on an available target lights it until it moves or lifts.
  auto pill_at = [&](UiRect r,TouchControl control,std::string_view label,bool enabled) {
    if(!r.w) return;
    const int radius=r.h/2;
    const uint16_t fill=control==m.pressed ? lit : surface;
    if(enabled) c.fill_round_rect(r.x,r.y,r.w,r.h,radius,fill);
    else {
      c.fill_round_rect(r.x,r.y,r.w,r.h,radius,kFaint);
      c.fill_round_rect(r.x+2,r.y+2,r.w-4,r.h-4,radius-2,0);
    }
    geist::text(c,r.x+(r.w-geist::width(label,18))/2,r.y+(r.h-22)/2,label,18,
                enabled?text:dim,enabled?fill:0);
  };
  auto pill = [&](TouchControl control,std::string_view label,bool enabled) {
    pill_at(control_rect(control,m),control,label,enabled);
  };
  UiRect slot_rect{};
  auto draw_control = [&](TouchControl control) {
    switch(control) {
      case TouchControl::Silence: pill_at(slot_rect,control,"Mute voice",m.can_silence); break;
      case TouchControl::Stop: {
        // Requested is not stopped: the target stays inert until an outcome arrives. Home
        // already says "Stop requested" in its headline, so its target just says "Requested".
        // Requested is not stopped: the target stays in place, inert, naming the request.
        // Quick controls keep it in place too; how work ended goes on the status line.
        const auto r=m.quick_controls ? kQuickStop : slot_rect.w ? slot_rect : control_rect(control,m);
        pill_at(r,control,"Stop task",m.can_stop);
        break;
      }
      case TouchControl::Discard: pill(control,"Discard",true); break;
      case TouchControl::Finish: pill(control,"Finish",true); break;
      case TouchControl::Talk: pill(control,m.tap_talk?"Tap to talk":"Hold to talk",true); break;
      case TouchControl::Reply: pill(control,"Read reply  ↑",true); break;
      case TouchControl::Settings: pill(control,"Settings",true); break;
      case TouchControl::Yes: pill(control,"Yes",true); break;  // equal emphasis: no assent colour
      case TouchControl::No: pill(control,"No",true); break;
      default: break;
    }
  };
  // Return to Home: the view title with a drawn chevron (the atlas has no ‹ glyph).
  auto back = [&](std::string_view title) {
    center(55,title,24,text);
    const int x=(466-geist::width(title,24))/2-24;
    for(int i=0;i<10;++i) { c.fill_rect(x+i,70-i,3,3,text); c.fill_rect(x+i,70+i,3,3,text); }
  };
  if (local_screen(m)) {
    render_local(c,m);
  } else if (m.recent) {
    back("Recent");
    if (m.work_rows.empty()) {
      center(196,"No recent work",18,text);
      center(228,"Your requests appear here",18,dim);
    }
    for (unsigned i=0;i<m.work_rows.size() && i<3;++i) {
      const auto control=static_cast<TouchControl>(unsigned(TouchControl::Work0)+i);
      const auto r=control_rect(control,m);
      const uint16_t fill=control==m.pressed ? lit : surface;
      c.fill_round_rect(r.x,r.y,r.w,r.h,20,fill);
      // Status: one restrained mark and word per stage. Body: the host's own glance.
      const auto& row=m.work_rows[i];
      const auto cut=row.find('\n');
      const std::string stage=row.substr(0,cut);
      const std::string glance=cut==std::string::npos?std::string():row.substr(cut+1);
      const uint16_t tone=stage_color(stage);
      c.fill_circle(r.x+26,r.y+22,4,tone);
      geist::text(c,r.x+38,r.y+9,stage_word(stage),18,tone,fill);
      const int inner=r.w-44;
      if(glance.empty()) {
        geist::text(c,r.x+22,r.y+35,"No reply text",18,dim,fill);
        continue;
      }
      // At most two lines of the host's glance; a longer one ends at a word with an ellipsis.
      auto lines=geist::wrap(glance,inner,18);
      if(lines.size()>2) {
        std::string tail=lines[1];
        while(!tail.empty() && geist::width(tail+"…",18)>inner) {
          const auto cut=tail.find_last_of(' ');
          tail.resize(cut==std::string::npos||cut==0 ? 0 : cut);
        }
        lines[1]=tail.empty() ? geist::fit(lines[1],inner,18) : tail+"…";
      }
      for(unsigned j=0;j<lines.size() && j<2;++j)
        geist::text(c,r.x+22,r.y+35+j*23,geist::fit(lines[j],inner,18),18,text,fill);
    }
    if (m.work_pages>1) {
      pill(TouchControl::Next,m.work_page+1>=m.work_pages?"Back to top":"More  ›",true);
      // Where you are in the shelf: one dot per page, the current one lit.
      const int x0=233-(m.work_pages-1)*7;
      for(int p=0;p<m.work_pages;++p)
        c.fill_circle(x0+p*14,442,p==m.work_page?4:3,p==m.work_page?text:dim);
    }
  } else {
  if (m.quick_controls && m.work_available) pill(TouchControl::Recent,"Recent",true);
  TouchControl slots[2];
  const int n=action_slots(m,slots);
  // Decorative perimeter marks stop above an action row instead of crossing its targets.
  if(visible && n>0) c.set_clip_rows(0,350);
  if(visible && m.screen==Screen::Listening) {
    c.arc(233,233,218,2,-1,kAccentDim); c.arc(233,233,218,2,1,kAccentDim);
  } else if(visible && m.speaking) {
    for(int r:{206,218}) { c.arc(233,233,r,2,-1,kAccentDim);c.arc(233,233,r,2,1,kAccentDim); }
  }
  c.set_clip_rows(0,466);
  if(visible && m.screen==Screen::Listening) meter();
  const bool connection = m.screen==Screen::Offline || m.screen==Screen::Connecting || m.screen==Screen::Error;
  if(connection) {
    center(53,"HERMES",18,dim);
    portrait();
    center(286,m.headline,30,text);
    center(327,m.detail,18,dim);
    auto next=geist::wrap(m.hint,300,18);
    for(unsigned i=0;i<next.size() && i<2;++i) center(365+i*24,next[i],18,dim);
  } else if(visible) {
    // With both a support line and actions, the caption stack tightens to keep clearances.
    const bool tight=n>0 && !m.detail.empty();
    center(53,m.link==Link::Online?"HERMES":"OFFLINE",18,dim);
    portrait();
    center(tight?289:299,m.headline,30,text);
    if(!m.detail.empty()) center(tight?328:342,m.detail,18,dim);
    for(int i=0;i<n;++i) {
      slot_rect = n==1 ? UiRect{128,356,210,55} : i==0 ? UiRect{91,356,138,55} : UiRect{237,356,138,55};
      draw_control(slots[i]);
      slot_rect = {};
    }
    if(control_rect(TouchControl::Controls,m).w) center(402,"↓  Controls",18,dim);
  } else {
    if(m.quick_controls) back("Quick controls");
    else if(m.touch_prompt) center(55,m.headline,24,text);
    else back(m.result ? "Recent result" : "Latest reply");
    if(!m.quick_controls) {
      const auto lines=body_lines(m.body,m);
      const int rows=body_rows(m),total=static_cast<int>(lines.size());
      const int last=std::max(0,total-rows), first=m.scroll<0?last:std::min(m.scroll,last);
      const bool header=m.result || !m.outcome.empty() || (m.stop_pending && !m.touch_prompt);
      const int y=m.touch_prompt?119:header?142:108;
      if(header) {
        const std::string_view o=m.outcome;
        const auto tone = o.rfind("Failed",0)==0||o.rfind("Error",0)==0?stage_color("failed"):
                          o.rfind("Finished",0)==0?stage_color("finished"):
                          o.rfind("Stopped",0)==0?stage_color("cancelled"):dim;
        const std::string_view line=m.outcome.empty() ? std::string_view("Stop requested · waiting for Hermes") : o;
        c.fill_circle(84,115,4,tone);
        geist::text(c,98,103,line,18,m.result?tone:dim);
      }
      for(int i=0;i<rows && first+i<total;++i) geist::text(c,78,y+i*34,lines[first+i],24,text);
      if(total>rows) {
        // Curved position track inside the circular edge; bounded 140 pixels.
        for(int yy=163;yy<303;++yy) {
          const int dy=yy-233;
          const int xx=438-(dy*dy)/410;
          c.fill_rect(xx,yy,3,1,kFaint);
        }
        const int thumb=std::max(10,140*rows/total);
        const int top=163+(140-thumb)*first/std::max(1,last);
        for(int yy=top;yy<top+thumb;++yy) {
          const int dy=yy-233; c.fill_rect(438-(dy*dy)/410,yy,3,1,dim);
        }
      }
    }
    if(m.quick_controls) {
      for(auto control:{TouchControl::Volume,TouchControl::Brightness}) {
        const auto r=control_rect(control,m);
        if(!r.w) continue;
        const int value=control==TouchControl::Volume?m.volume:m.brightness;
        const char* label=control==TouchControl::Volume?"Volume":"Brightness";
        geist::text(c,r.x+(r.w-geist::width(label,18))/2,r.y-30,label,18,dim);
        c.fill_round_rect(r.x,r.y,r.w,r.h,30,surface);
        // Clip the fill to the same rounded track without a scratch framebuffer.
        const int fill=r.h*value/100;
        c.set_clip_rows(r.y+r.h-fill,r.y+r.h);
        c.fill_round_rect(r.x,r.y,r.w,r.h,30,amber);
        c.set_clip_rows(0,466);
        // The value reads inside its own track: dark on the fill once it is tall enough,
        // otherwise light at the empty top. Nothing crowds the row below the tracks.
        const auto pct=std::to_string(value)+"%";
        const bool on_fill=fill>=60;
        if(fill>8 && !(on_fill && fill>r.h-8)) c.fill_round_rect(r.x+23,r.y+r.h-std::max(7,fill)+3,26,4,2,ink);
        geist::text(c,r.x+(r.w-geist::width(pct,18))/2,on_fill?r.y+r.h-36:r.y+16,pct,18,
                    on_fill?ink:text,on_fill?amber:surface);
      }
      pill_at(kQuickSilence,TouchControl::Silence,"Mute voice",m.can_silence);
      draw_control(TouchControl::Stop);
      // Settings never interrupt work, speech or a recording: the target stays in place,
      // inert. Status has its own line above the actions and is never a target.
      pill_at(kQuickSettings,TouchControl::Settings,"Settings",m.settings_ready);
      const std::string status = m.stop_pending ? std::string("Stop requested · waiting for Hermes") :
          !m.settings_ready ? std::string("Settings open when idle") :
          m.outcome_word.empty() ? std::string() : "Last task: " + m.outcome_word;
      if(!status.empty()) center(310,status,18,dim);
    } else if(m.touch_prompt) {
      if(m.prompt_unread) {
        // Unread question: both answers stay in place, equally inert, until its end is shown.
        pill_at(prompt_answer_rect(false),TouchControl::None,"No",false);
        pill_at(prompt_answer_rect(true),TouchControl::None,"Yes",false);
        center(404,"Scroll to read all  ↓",18,text);
      } else {
        draw_control(TouchControl::No);
        draw_control(TouchControl::Yes);
      }
    } else {
      for(int i=0;i<n;++i) {
      slot_rect = n==1 ? UiRect{128,356,210,55} : i==0 ? UiRect{91,356,138,55} : UiRect{237,356,138,55};
      draw_control(slots[i]);
      slot_rect = {};
    }
    }
  }
  }
  if(press_only) {
    for(auto control:{companion_pressed_,m.pressed}) {
      const auto r=control_rect(control,m);
      if(r.w) display_.flush_rect(static_cast<uint16_t>(r.x),static_cast<uint16_t>(r.y),
                                  static_cast<uint16_t>(r.x+r.w),static_cast<uint16_t>(r.y+r.h));
    }
    if(visible && face_changed_) display_.flush_rect(137,96,329,288);
  } else {
    if (!motion_flush_) display_.flush(0,panel_.height);
  }
  companion_hash_=key; companion_level_=level; companion_pressed_=m.pressed;
  companion_valid_=valid_=true; hero_valid_=false;
}

void Ui::render_local(Canvas& c, const UiModel& m) {
  // Pairing, Settings and Wi-Fi setup in the companion's language: Geist on true black,
  // one surface card for the content, dim instructions. Input semantics stay in the app.
  constexpr uint16_t text = rgb565(240,239,235), dim = rgb565(164,164,169), surface = rgb565(32,32,35);
  auto center = [&](int y,std::string_view label,int size,uint16_t color,uint16_t bg=0) {
    const auto fitted=geist::fit(label,330,size);
    geist::text(c,(466-geist::width(fitted,size))/2,y,fitted,size,color,bg);
  };
  if (m.color_test) {
    // Display check: five full-height bands, as the legacy check draws them.
    const uint16_t colors[] = {rgb565(255,0,0),rgb565(0,255,0),rgb565(0,0,255),rgb565(255,255,255),0};
    for (int i=0;i<5;++i) c.fill_rect(466*i/5,0,466*(i+1)/5-466*i/5,466,colors[i]);
    return;
  }
  if (m.screen == Screen::Pairing) {
    center(55,"Pair with Hermes",24,text);
    draw_expression(c,185,92,96);
    if (!m.code.empty()) {
      center(204,"Pairing code",18,dim);
      const int w=geist::display_width(m.code);
      if (w>0 && w<=380) geist::display_text(c,(466-w)/2,224,m.code,text);
      else center(236,m.code,30,text);
      center(292,m.detail,18,dim);
      const auto lines=geist::wrap(m.body,330,18);
      for (unsigned i=0;i<lines.size() && i<2;++i) center(318+i*24,lines[i],18,text);
    } else {
      center(214,m.headline,30,text);
      center(258,m.detail,18,dim);
    }
    center(m.body.find(' ')!=std::string::npos && geist::width(m.body,18)>330 ? 378 : 360,m.hint,18,dim);
    return;
  }
  const bool settings = m.screen == Screen::Settings;
  center(55,settings ? "Settings" : m.headline,24,text);
  // Content card: a row's name, its value large, then its description.
  const int top=settings?104:124, bottom=settings?330:334;
  c.fill_round_rect(68,top,330,bottom-top,24,surface);
  int y=top+20;
  if (settings) {
    center(y,m.detail,24,text,surface);
    y+=42;
    const int vw=geist::display_width(m.value);
    if (vw>0 && vw<=290) { geist::display_text(c,(466-vw)/2,y-6,m.value,text,surface); y+=58; }
    else if (!m.value.empty()) { center(y,m.value,30,text,surface); y+=48; }
  } else {
    center(92,m.detail,18,dim);
    y+=6;
  }
  int size=settings?18:24, step=settings?24:36;
  auto lines=geist::wrap(m.body,290,size);
  int fits=std::max(1,(bottom-14-y)/step);
  if (!settings && static_cast<int>(lines.size())>fits) {
    // Setup instructions are never cut: step down to the 18px reading size first.
    size=18; step=26; lines=geist::wrap(m.body,290,size); fits=std::max(1,(bottom-14-y)/step);
  }
  if (static_cast<int>(lines.size())>fits) {
    lines.resize(fits);
    lines.back()=geist::fit(lines.back()+" …",290,size);
  }
  for (const auto& line:lines) { center(y,line,size,settings?dim:text,surface); y+=step; }
  if (settings && m.work_pages>1) {
    // Where you are among the rows: one dot per row, the current one lit.
    const int x0=233-(m.work_pages-1)*7;
    for (int p=0;p<m.work_pages;++p) c.fill_circle(x0+p*14,348,p==m.work_page?4:3,p==m.work_page?text:dim);
  }
  center(settings?366:352,m.hint,18,dim);
  if (settings) center(394,"Hold the title to close",18,dim);
}

void Ui::render(const UiModel& m) {
  if (round_companion()) update_expression(m);
  if (companion_model(m)) { render_motion(m); return; }
  motion_active_ = false; motion_view_ = -1;
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
    uint32_t anim = round_companion() ? Hash().val(face_clip_).val(face_index_).get() : hero_anim_key(m);
    int y0 = y_header, y1 = y_bottom;
    bool redraw = !valid_ || !hero_valid_ || stat != hero_static_;
    if (!redraw && anim != hero_anim_) {
      if (round_companion()) {
        const auto g = hero_geom(m);
        y0 = g.y; y1 = g.y+g.size;
      } else hero_anim_rows(m, y0, y1);  // legacy bitmap's bounded motion
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

std::vector<std::string> Ui::body_lines(std::string_view text, const UiModel& m) const {
  return companion_model(m) ? geist::wrap(text,303) : wrap_text(text,layout_.body_cols);
}

int Ui::body_rows(const UiModel& m) const {
  if (companion_model(m)) return m.touch_prompt ? 5 : (m.result || !m.outcome.empty() || m.stop_pending) ? 6 : 7;
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
  if (round_companion()) draw_expression(c,mx,my,size);
  else if (const mascot::Bitmap* b = mascot::pick(size, mascot_frame(m))) {
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
    if (!companion_model(m)) return {};
    if (m.touch_prompt) {
      // Equal targets, as large as the circle allows below five readable rows; none
      // while the question has not been read to its end.
      if (m.prompt_unread) return {};
      if (control == TouchControl::Yes) return prompt_answer_rect(true);
      if (control == TouchControl::No) return prompt_answer_rect(false);
      return {};
    }
    if (local_screen(m)) return {};  // pairing, settings and Wi-Fi setup keep their own input
    if (m.recent) {
      if (control == TouchControl::Home) return {108,44,250,52};
      if (control == TouchControl::Next && m.work_pages > 1) return {163,392,140,38};
      int i = int(control) - int(TouchControl::Work0);
      if (i >= 0 && i < int(m.work_rows.size()) && i < 3) return {78,92+i*100,310,92};
      return {};
    }
    if (m.quick_controls) {
      if (control == TouchControl::Recent && m.work_available) return {163,258,140,40};
      if (control == TouchControl::Volume && m.volume >= 0) return {122,126,72,124};
      if (control == TouchControl::Brightness && m.brightness >= 0) return {272,126,72,124};
      // Stable positions: unavailable actions stay visible but inert. Silence, then Stop,
      // in the same order as the Home and reading action row.
      if (control == TouchControl::Silence) return kQuickSilence;
      if (control == TouchControl::Stop && (m.can_stop || m.stop_pending || m.outcome_word.empty())) return kQuickStop;
      if (control == TouchControl::Settings && m.settings_ready) return kQuickSettings;
      if (control == TouchControl::Home) return {108,44,250,52};
      return {};
    }
    TouchControl slots[2];
    const int n = action_slots(m, slots);
    for (int i = 0; i < n; ++i) {
      if (slots[i] != control) continue;
      // An inert Mute placeholder is drawn but is never a target.
      if (control == TouchControl::Silence && !m.can_silence) return {};
      if (n == 1) return {128,356,210,55};
      return i == 0 ? UiRect{91,356,138,55} : UiRect{237,356,138,55};
    }
    if (control == TouchControl::Home && !m.hero) return {108,44,250,52};
    if (control == TouchControl::Controls && m.hero && n == 0 && m.capture == 0 && m.screen == Screen::Ready)
      return {153,388,160,48};
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

int Ui::action_slots(const UiModel& m, TouchControl (&slots)[2]) const {
  int n = 0;
  auto add = [&](TouchControl c) { if (n < 2) slots[n++] = c; };
  if (!round_companion() || !companion_model(m) || m.quick_controls || m.touch_prompt || local_screen(m)) return 0;
  if (m.capture == 2) add(TouchControl::Discard);  // physical TALK held: the screen is free
  else if (m.capture == 3) {
    add(TouchControl::Discard);
    add(TouchControl::Finish);
  } else if (m.capture == 0) {  // a touch hold (1) owns the only contact: no fake second tap
    if (m.can_stop || m.stop_pending) {
      // Work is open: Stop always holds the right slot, as in quick controls. The left slot
      // is Mute voice while speaking, else Read reply when one waits, else an inert Mute.
      if (!m.can_silence && m.hero && m.unread_reply) add(TouchControl::Reply);
      else add(TouchControl::Silence);
      add(TouchControl::Stop);
    } else {
      if (m.can_silence) add(TouchControl::Silence);
      if (m.hero && m.unread_reply) add(TouchControl::Reply);
      if (!m.hero && n == 0 && m.talk_control) add(TouchControl::Talk);
    }
  }
  return n;
}

TouchControl Ui::control_hit(int x, int y, const UiModel& m) const {
  for (unsigned i = 1; i < kTouchControls; ++i) {
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
