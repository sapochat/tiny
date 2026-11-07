#pragma once

#include <functional>
#include <utility>

#include "hg/hal.hpp"

namespace hg {

// Register definitions follow X-Powers AXP2101 SWcharge v1.0, section 6.13.
// The port owns I2C. Reading never changes charging, rails, or gauge parameters.
// The PWR key: the chip flags a press shorter than its IRQ level (reg 0x27, untouched) as a
// short press in INTSTS2 bit 3. Long presses and the hard power-off stay the chip's own.
class Axp2101 final : public Power {
 public:
  using Read = std::function<bool(uint8_t, uint8_t*, size_t)>;
  using Write = std::function<bool(uint8_t, uint8_t)>;
  Axp2101(Read read, Write write) : read_(std::move(read)), write_(std::move(write)) {}
  std::optional<PowerStatus> read() override;
  bool power_off() override;
  bool enable_aldo1_3v3();  // Only for boards whose audio circuit requires this rail.
  bool enable_key_short_press();  // sets only the short-press enable bit and clears its flag
  bool take_key_short_press();    // true once per short press since the last call

 private:
  Read read_;
  Write write_;
};

}  // namespace hg
