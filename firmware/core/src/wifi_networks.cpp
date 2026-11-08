#include "hg/wifi_networks.hpp"

#include <algorithm>

#include "hg/json.hpp"

namespace hg {

std::string wifi_network_error(std::string_view ssid, std::string_view password) {
  if (ssid.empty() || ssid.size() > 32 || ssid.find('\0') != std::string_view::npos)
    return "Network name must contain 1..32 bytes";
  const bool hex_key = password.size() == 64 && password.find_first_not_of("0123456789abcdefABCDEF") == std::string_view::npos;
  if ((!password.empty() && !hex_key && (password.size() < 8 || password.size() > 63)) ||
      std::any_of(password.begin(), password.end(), [](unsigned char c) { return c < 0x20 || c > 0x7e; }))
    return "Use an 8..63 character Wi-Fi password, a 64-digit hex key, or leave it empty for an open network";
  return {};
}

WifiNetworks WifiNetworks::load(Storage& storage) {
  WifiNetworks n;
  const auto raw = storage.get("wifi_nets");
  const auto ssid = storage.get("wifi_ssid");
  const std::string password = storage.get("wifi_pass").value_or("");
  json::Value saved;
  if (raw && json::parse(*raw, saved, nullptr, 3) && saved.is_array()) {
    for (const auto& e : saved.elements()) {
      if (n.list_.size() == kMax) break;
      if (!e.is_object() || e["ssid"].as_string().empty() || n.find(e["ssid"].as_string()) != n.size()) continue;
      n.list_.push_back({e["ssid"].as_string(), std::string(e["pass"].str_or("")), e["tested"].as_bool()});
    }
  }
  if (!ssid || ssid->empty()) {
    // Erased through `set wifi_ssid`: forget the first network.
    if (raw && !n.list_.empty()) {
      n.list_.erase(n.list_.begin());
      n.dirty_ = true;
    }
    return n;
  }
  if (n.list_.empty() || n.list_[0].ssid != *ssid || n.list_[0].password != password) {
    // Firmware without the list (or `set wifi_ssid`) changed the first network. Before
    // there was a list, the one network in use counts as tested.
    const size_t at = n.find(*ssid);
    const bool tested = !raw || (at < n.size() && n.list_[at].password == password && n.list_[at].tested);
    n.put_first(*ssid, password, tested);
    n.dirty_ = true;
  }
  return n;
}

bool WifiNetworks::save(Storage& storage) {
  json::Value out = json::Value::array();
  for (const auto& w : list_) {
    json::Value e = json::Value::object();
    e.set("ssid", w.ssid).set("pass", w.password).set("tested", w.tested);
    out.push(std::move(e));
  }
  if (!storage.set("wifi_nets", out.dump())) return false;
  if (list_.empty()) {
    storage.erase("wifi_ssid");
    storage.erase("wifi_pass");
  } else {
    storage.set("wifi_ssid", list_[0].ssid);
    if (list_[0].password.empty()) storage.erase("wifi_pass");
    else storage.set("wifi_pass", list_[0].password);
  }
  dirty_ = false;
  return true;
}

size_t WifiNetworks::find(std::string_view ssid) const {
  for (size_t i = 0; i < list_.size(); ++i)
    if (list_[i].ssid == ssid) return i;
  return list_.size();
}

WifiNetworks::Added WifiNetworks::add(std::string_view ssid, std::string_view password) {
  const size_t at = find(ssid);
  if (at < size()) {
    if (list_[at].password == password) return Added::Unchanged;
    list_[at].password = std::string(password);
    list_[at].tested = false;
    return Added::Updated;
  }
  if (size() == kMax) return Added::Full;
  list_.push_back({std::string(ssid), std::string(password), false});
  return Added::Added;
}

bool WifiNetworks::forget(std::string_view ssid) {
  const size_t at = find(ssid);
  if (at == size()) return false;
  list_.erase(list_.begin() + static_cast<std::ptrdiff_t>(at));
  return true;
}

bool WifiNetworks::move_first(std::string_view ssid) {
  const size_t at = find(ssid);
  if (at == 0 || at == size()) return false;
  std::rotate(list_.begin(), list_.begin() + static_cast<std::ptrdiff_t>(at), list_.begin() + static_cast<std::ptrdiff_t>(at) + 1);
  return true;
}

bool WifiNetworks::joined(std::string_view ssid) {
  const size_t at = find(ssid);
  if (at == size() || (at == 0 && list_[0].tested)) return false;
  move_first(ssid);
  list_[0].tested = true;
  return true;
}

void WifiNetworks::put_first(std::string_view ssid, std::string_view password, bool tested) {
  const size_t at = find(ssid);
  if (at < size()) list_.erase(list_.begin() + static_cast<std::ptrdiff_t>(at));
  else if (size() == kMax) list_.pop_back();
  list_.insert(list_.begin(), {std::string(ssid), std::string(password), tested});
}

}  // namespace hg
