// Which saved Wi-Fi network to try next, apart from ESP-IDF so it can be tested
// on the host (firmware/esp32/main/port_wifi.cpp). The saved list is in the
// order hg::WifiNetworks keeps it: the network that last worked comes first.
//
// A network gets kTries attempts in a row (a lost link counts as one, so it is
// retried once). After that the port scans, and choose() picks the first saved
// network if the scan saw it, else the strongest saved network it saw. One that
// already failed kTries times is passed over while another saved network is in
// range. When the scan sees no saved network (hidden, or just missed), the next
// one in the list is tried.
#pragma once
#include <cstddef>
#include <cstdint>
#include <string>
#include <string_view>
#include <vector>

namespace hg {

class WifiPick {
 public:
  static constexpr unsigned kTries = 2;
  struct Seen {
    std::string_view ssid;
    int8_t rssi;
  };

  // A new list of `count` networks; `current` is the one being joined.
  void reset(size_t count, size_t current = 0) {
    failures_.assign(count, 0);
    current_ = current < count ? current : 0;
  }
  size_t current() const { return current_; }
  void connected() { failures_.assign(failures_.size(), 0); }
  // An attempt on the current network failed, or its link was lost.
  void failed() {
    if (current_ < failures_.size()) ++failures_[current_];
  }
  // Scan before the next attempt instead of retrying the same network.
  bool should_scan() const { return failures_.size() > 1 && failures_[current_] >= kTries; }

  // After a scan: the index of the saved network to try next (it becomes current).
  size_t choose(const std::vector<std::string>& saved, const std::vector<Seen>& seen) {
    if (saved.size() != failures_.size() || saved.empty()) return current_;
    constexpr int kUnseen = -1000;
    std::vector<int> best(saved.size(), kUnseen);
    for (const auto& s : seen)
      for (size_t i = 0; i < saved.size(); ++i)
        if (saved[i] == s.ssid && s.rssi > best[i]) best[i] = s.rssi;
    size_t pick = saved.size();
    for (int pass = 0; pass < 2 && pick == saved.size(); ++pass) {
      for (size_t i = 0; i < saved.size(); ++i) {
        if (best[i] == kUnseen || (pass == 0 && failures_[i] >= kTries)) continue;
        if (pick == saved.size() || (pick != 0 && best[i] > best[pick])) pick = i;
      }
      if (pick != saved.size() && pass == 1) {
        // Every saved network in range has failed: start them over.
        for (size_t i = 0; i < saved.size(); ++i)
          if (best[i] != kUnseen) failures_[i] = 0;
      }
    }
    if (pick == saved.size()) {
      pick = (current_ + 1) % saved.size();
      failures_[pick] = 0;
    }
    current_ = pick;
    return pick;
  }

 private:
  std::vector<unsigned> failures_;
  size_t current_ = 0;
};

}  // namespace hg
