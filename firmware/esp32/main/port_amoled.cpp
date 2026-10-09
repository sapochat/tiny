// QSPI AMOLED panel with a CO5300 controller (e.g. the round 466x466 1.75"
// modules), driven directly through esp_lcd panel IO in quad mode.
//
// Framing on the QSPI link: commands go out as (0x02 << 24) | (cmd << 8) with
// their parameters; pixels as (0x32 << 24) | (RAMWR << 8). The controller only
// accepts windows that start on an even row/column and span an even count.
#include "port.hpp"  // first: pulls in FreeRTOS.h ahead of task.h/queue.h

#include <algorithm>
#include <cstring>

#include "driver/gpio.h"
#include "driver/spi_master.h"
#include "esp_heap_caps.h"
#include "esp_lcd_panel_io.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/task.h"

namespace hgp {
namespace {

const char* TAG = "hg.amoled";
constexpr spi_host_device_t kHost = SPI2_HOST;
// Largest single SPI DMA transaction (2^18 bits); esp_lcd chains these with CS held.
constexpr int kMaxTransfer = 32 * 1024 - 64;
// Two internal-RAM staging buffers of this many rows (even, so every chunk keeps the
// window even). The CPU copies chunk N+1 out of PSRAM while DMA sends chunk N.
constexpr int kBounceRows = 16;

constexpr uint32_t command_word(uint8_t cmd) { return (0x02u << 24) | (static_cast<uint32_t>(cmd) << 8); }
constexpr uint32_t kRamWrite = (0x32u << 24) | (0x2Cu << 8);

struct InitCommand {
  uint8_t cmd;
  uint8_t data[4];
  uint8_t len;
  uint16_t delay_ms;
};

// Panel bring-up for CO5300 1.75" modules: vendor page settings, RGB565,
// tearing line on, full brightness, the 466x466 window (column offset 6),
// then sleep out and display on.
constexpr InitCommand kInit[] = {
    {0x36, {0x00}, 1, 0},  // memory access control: no rotation
    {0x3A, {0x55}, 1, 0},  // 16 bits per pixel
    {0xFE, {0x20}, 1, 0},
    {0x19, {0x10}, 1, 0},
    {0x1C, {0xA0}, 1, 0},
    {0xFE, {0x00}, 1, 0},
    {0xC4, {0x80}, 1, 0},
    {0x3A, {0x55}, 1, 0},
    {0x35, {0x00}, 1, 0},  // tearing effect line on
    {0x53, {0x20}, 1, 0},  // brightness control on
    {0x51, {0xFF}, 1, 0},  // brightness
    {0x63, {0xFF}, 1, 0},
    {0x2A, {0x00, 0x06, 0x01, 0xD7}, 4, 0},
    {0x2B, {0x00, 0x00, 0x01, 0xD1}, 4, 600},
    {0x11, {}, 0, 600},  // sleep out
    {0x29, {}, 0, 0},    // display on
};

}  // namespace

bool AmoledDisplay::on_trans_done(esp_lcd_panel_io_handle_t, esp_lcd_panel_io_event_data_t*, void* ctx) {
  BaseType_t woken = pdFALSE;
  xSemaphoreGiveFromISR(static_cast<AmoledDisplay*>(ctx)->done_, &woken);
  // esp_lcd's SPI path ignores this callback's return value, so request the switch here.
  // Without it the flushing task waits for the next 10 ms tick after every chunk.
  if (woken == pdTRUE && xPortInIsrContext()) portYIELD_FROM_ISR();
  return woken == pdTRUE;
}

void AmoledDisplay::command(uint8_t cmd, const uint8_t* data, size_t len) {
  esp_lcd_panel_io_tx_param(io_, static_cast<int>(command_word(cmd)), len ? data : nullptr, len);
}

bool AmoledDisplay::begin(const AmoledConfig& cfg) {
  cfg_ = cfg;
  const size_t px = static_cast<size_t>(cfg.width) * cfg.height;
  fb_ = static_cast<uint16_t*>(heap_caps_malloc(px * 2, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT));
  if (!fb_) {
    ESP_LOGE(TAG, "not enough memory for a %ux%u framebuffer (is PSRAM enabled?)", cfg.width, cfg.height);
    return false;
  }
  std::memset(fb_, 0, px * 2);
  // Staging rows in internal RAM keep DMA off PSRAM. Without them, DMA reads the
  // framebuffer in PSRAM directly (slower, and it competes with flash writes).
  const size_t bounce_bytes = static_cast<size_t>(cfg.width) * kBounceRows * 2;
  for (auto& b : bounce_) b = static_cast<uint16_t*>(heap_caps_malloc(bounce_bytes, MALLOC_CAP_DMA | MALLOC_CAP_INTERNAL));
  if (!bounce_[0] || !bounce_[1]) {
    ESP_LOGW(TAG, "no internal RAM for display staging rows; DMA reads PSRAM directly");
    for (auto& b : bounce_) { heap_caps_free(b); b = nullptr; }
  }
  done_ = xSemaphoreCreateBinary();

  spi_bus_config_t bus = {};
  bus.sclk_io_num = cfg.sclk;
  bus.data0_io_num = cfg.d0;
  bus.data1_io_num = cfg.d1;
  bus.data2_io_num = cfg.d2;
  bus.data3_io_num = cfg.d3;
  bus.data4_io_num = -1;
  bus.data5_io_num = -1;
  bus.data6_io_num = -1;
  bus.data7_io_num = -1;
  bus.max_transfer_sz = kMaxTransfer;
  bus.flags = SPICOMMON_BUSFLAG_QUAD;
  ESP_ERROR_CHECK(spi_bus_initialize(kHost, &bus, SPI_DMA_CH_AUTO));

  esp_lcd_panel_io_spi_config_t io_cfg = {};
  io_cfg.cs_gpio_num = static_cast<gpio_num_t>(cfg.cs);
  io_cfg.dc_gpio_num = GPIO_NUM_NC;
  io_cfg.spi_mode = 0;
  io_cfg.pclk_hz = static_cast<uint32_t>(cfg.qspi_mhz) * 1000 * 1000;
  io_cfg.trans_queue_depth = 10;
  io_cfg.lcd_cmd_bits = 32;
  io_cfg.lcd_param_bits = 8;
  io_cfg.flags.quad_mode = 1;
  // Only used without staging rows: DMA then reads the PSRAM framebuffer directly.
  io_cfg.flags.psram_dma_direct = 1;
  io_cfg.on_color_trans_done = &AmoledDisplay::on_trans_done;
  io_cfg.user_ctx = this;
  ESP_ERROR_CHECK(esp_lcd_new_panel_io_spi(static_cast<esp_lcd_spi_bus_handle_t>(kHost), &io_cfg, &io_));

  if (cfg.rst >= 0) {
    gpio_config_t rst = {};
    rst.pin_bit_mask = 1ULL << cfg.rst;
    rst.mode = GPIO_MODE_OUTPUT;
    gpio_config(&rst);
    gpio_set_level(static_cast<gpio_num_t>(cfg.rst), 0);
    vTaskDelay(pdMS_TO_TICKS(10));
    gpio_set_level(static_cast<gpio_num_t>(cfg.rst), 1);
    vTaskDelay(pdMS_TO_TICKS(150));
  }
  for (const auto& c : kInit) {
    command(c.cmd, c.data, c.len);
    if (c.delay_ms) vTaskDelay(pdMS_TO_TICKS(c.delay_ms));
  }
  ESP_LOGI(TAG, "CO5300 %ux%u ready", cfg.width, cfg.height);
  return true;
}

hg::DisplayInfo AmoledDisplay::info() const {
  hg::DisplayInfo di;
  di.width = cfg_.width;
  di.height = cfg_.height;
  di.swap_bytes = true;  // big-endian RGB565 on the wire
  di.has_backlight = true;  // brightness command 0x51
  di.round = cfg_.round;
  return di;
}

void AmoledDisplay::flush(uint16_t y0, uint16_t y1) { flush_rect(0, y0, cfg_.width, y1); }

void AmoledDisplay::flush_rect(uint16_t x0, uint16_t y0, uint16_t x1, uint16_t y1) {
  const int64_t started = esp_timer_get_time();
  const int w = cfg_.width, h = cfg_.height;
  // Even start and even span on both axes: widen the dirty area by at most one each side.
  int top = y0 & ~1;
  int bottom = std::min(h, (y1 + 1) & ~1);
  int left = std::min<int>(x0, w) & ~1;
  int right = std::min(w, (x1 + 1) & ~1);
  // Without staging rows DMA reads the framebuffer itself, which needs whole rows.
  if (!bounce_[0] || right <= left) { left = 0; right = w; }
  const int cw = right - left;
  const int xa = cfg_.gap_x + left, xb = cfg_.gap_x + right - 1;
  const uint8_t cols[4] = {static_cast<uint8_t>(xa >> 8), static_cast<uint8_t>(xa), static_cast<uint8_t>(xb >> 8),
                           static_cast<uint8_t>(xb)};
  // Sets the window. esp_lcd sends commands by polling, after every queued
  // pixel transfer has finished, so this also waits for the previous chunk.
  auto window = [&](int y, int rows) {
    const int ya = y + cfg_.gap_y, yb = y + rows - 1 + cfg_.gap_y;
    const uint8_t lines[4] = {static_cast<uint8_t>(ya >> 8), static_cast<uint8_t>(ya), static_cast<uint8_t>(yb >> 8),
                              static_cast<uint8_t>(yb)};
    command(0x2A, cols, 4);
    command(0x2B, lines, 4);
  };
  bool sent = false;
  if (bottom > top && bounce_[0]) {
    // Double-buffered: copy chunk N+1 while chunk N is on the wire. Each chunk has
    // its own window, the framing the panel already accepted with one buffer. A
    // narrow column span packs more rows into each staging buffer (kept even).
    const int chunk = std::min(kMaxTransfer / (cw * 2), (w * kBounceRows) / cw) & ~1;
    auto stage = [&](int b, int y, int rows) {
      if (cw == w) {
        std::memcpy(bounce_[b], fb_ + static_cast<size_t>(y) * w, static_cast<size_t>(rows) * w * 2);
        return;
      }
      for (int r = 0; r < rows; ++r)
        std::memcpy(bounce_[b] + static_cast<size_t>(r) * cw, fb_ + static_cast<size_t>(y + r) * w + left,
                    static_cast<size_t>(cw) * 2);
    };
    int buf = 0;
    int rows = std::min(chunk, bottom - top);
    stage(0, top, rows);
    for (int y = top; y < bottom;) {
      window(y, rows);  // waits until the other buffer's transfer is done
      xSemaphoreTake(done_, 0);  // completions so far are stale: wait for this chunk's
      sent = esp_lcd_panel_io_tx_color(io_, static_cast<int>(kRamWrite), bounce_[buf],
                                       static_cast<size_t>(rows) * cw * 2) == ESP_OK;
      if (!sent) break;
      y += rows;
      if (y >= bottom) break;
      rows = std::min(chunk, bottom - y);
      buf ^= 1;
      stage(buf, y, rows);
    }
  } else if (bottom > top) {
    window(top, bottom - top);
    xSemaphoreTake(done_, 0);
    sent = esp_lcd_panel_io_tx_color(io_, static_cast<int>(kRamWrite), fb_ + static_cast<size_t>(top) * w,
                                     static_cast<size_t>(bottom - top) * w * 2) == ESP_OK;
  }
  // The caller draws into the framebuffer (or reuses a staging buffer) next: wait
  // until DMA has read the last chunk.
  if (sent && xSemaphoreTake(done_, pdMS_TO_TICKS(200)) != pdTRUE) ++perf_.timeouts;
  const auto us = static_cast<uint32_t>(esp_timer_get_time() - started);
  ++perf_.calls;
  perf_.rows += static_cast<uint32_t>(std::max(0, bottom - top));
  perf_.px += static_cast<uint32_t>(std::max(0, bottom - top) * cw);
  perf_.us += us;
  perf_.max_us = std::max(perf_.max_us, us);
  if (bottom - top >= h - 2 && cw == w) perf_.full_us = std::max(perf_.full_us, us);
}

void AmoledDisplay::set_backlight(uint8_t percent) {
  const uint8_t level = static_cast<uint8_t>(255u * std::min<uint8_t>(percent, 100) / 100u);
  command(0x51, &level, 1);
}

}  // namespace hgp
