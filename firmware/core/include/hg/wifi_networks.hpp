// The Wi-Fi networks the device keeps, first one tried first.
//
// Storage: the list lives in "wifi_nets" as JSON. The first network is also
// mirrored into the older "wifi_ssid" / "wifi_pass" keys, so `set wifi_ssid`
// keeps working and firmware without this list (an update rolled back, an
// older image flashed) still finds a network. When the mirror disagrees with
// the list, it was changed through those keys, and load() puts it first; an
// erased "wifi_ssid" forgets the first network.
#pragma once

#include <cstddef>
#include <string>
#include <string_view>
#include <vector>

#include "hg/hal.hpp"

namespace hg {

struct WifiNetwork {
  std::string ssid, password;
  bool tested = false;  // the device has joined it with this password
};

// Why a network can't be saved, or empty when it can. Same rules as the setup page.
std::string wifi_network_error(std::string_view ssid, std::string_view password);

class WifiNetworks {
 public:
  static constexpr size_t kMax = 5;

  static WifiNetworks load(Storage& storage);
  // Writes the list, then the mirror keys. False when the list could not be saved.
  bool save(Storage& storage);
  // True when load() changed what was stored (a first load, a mirror edit).
  bool dirty() const { return dirty_; }

  const std::vector<WifiNetwork>& all() const { return list_; }
  bool empty() const { return list_.empty(); }
  size_t size() const { return list_.size(); }
  // Index of the network, or size() when it isn't saved.
  size_t find(std::string_view ssid) const;

  enum class Added { Added, Updated, Unchanged, Full };
  // A new network goes last; a saved one keeps its place and takes the new password.
  Added add(std::string_view ssid, std::string_view password);
  bool forget(std::string_view ssid);
  // Moves a saved network first. False when it isn't saved or already first.
  bool move_first(std::string_view ssid);
  // The device joined this network: it goes first and counts as tested.
  // False when nothing changed (or it isn't saved).
  bool joined(std::string_view ssid);
  // Saves the network first, dropping the last one when the list is full.
  void put_first(std::string_view ssid, std::string_view password, bool tested);

 private:
  std::vector<WifiNetwork> list_;
  bool dirty_ = false;
};

}  // namespace hg
