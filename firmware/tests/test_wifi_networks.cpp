#include <map>
#include <string>

#include "check.hpp"
#include "hg/console_args.hpp"
#include "hg/json.hpp"
#include "hg/wifi_networks.hpp"

namespace {

struct MemoryStorage : hg::Storage {
  std::map<std::string, std::string> kv;
  bool full = false;
  std::optional<std::string> get(std::string_view key) override {
    auto it = kv.find(std::string(key));
    if (it == kv.end()) return std::nullopt;
    return it->second;
  }
  bool set(std::string_view key, std::string_view value) override {
    if (full) return false;
    kv[std::string(key)] = std::string(value);
    return true;
  }
  void erase(std::string_view key) override { kv.erase(std::string(key)); }
};

std::string names(const hg::WifiNetworks& n) {
  std::string out;
  for (const auto& w : n.all()) out += (out.empty() ? "" : ",") + w.ssid + (w.tested ? "*" : "");
  return out;
}

}  // namespace

TEST("wifi networks: the one network from before the list is kept, tested") {
  MemoryStorage s;
  s.kv = {{"wifi_ssid", "Home"}, {"wifi_pass", "password1"}};
  auto n = hg::WifiNetworks::load(s);
  CHECK(n.dirty());
  CHECK_EQ(names(n), std::string("Home*"));
  CHECK_EQ(n.all()[0].password, std::string("password1"));
  CHECK(n.save(s));
  CHECK(!hg::WifiNetworks::load(s).dirty());
}

TEST("wifi networks: nothing saved loads empty and writes nothing") {
  MemoryStorage s;
  auto n = hg::WifiNetworks::load(s);
  CHECK(n.empty());
  CHECK(!n.dirty());
}

TEST("wifi networks: the first network is mirrored into wifi_ssid and wifi_pass") {
  MemoryStorage s;
  hg::WifiNetworks n;
  CHECK(n.add("Home", "password1") == hg::WifiNetworks::Added::Added);
  CHECK(n.add("Phone", "") == hg::WifiNetworks::Added::Added);
  CHECK(n.save(s));
  CHECK_EQ(s.kv["wifi_ssid"], std::string("Home"));
  CHECK_EQ(s.kv["wifi_pass"], std::string("password1"));
  CHECK(n.move_first("Phone"));
  CHECK(n.save(s));
  CHECK_EQ(s.kv["wifi_ssid"], std::string("Phone"));
  CHECK(!s.kv.count("wifi_pass"));  // open network
  CHECK(n.forget("Phone") && n.forget("Home"));
  CHECK(n.save(s));
  CHECK(!s.kv.count("wifi_ssid"));
  CHECK_EQ(names(hg::WifiNetworks::load(s)), std::string(""));
}

TEST("wifi networks: set wifi_ssid puts a network first and keeps the others") {
  MemoryStorage s;
  hg::WifiNetworks n;
  n.add("Home", "password1");
  n.add("Office", "password2");
  n.joined("Home");
  n.save(s);
  s.kv["wifi_ssid"] = "Cafe";  // old firmware, or `set wifi_ssid`, then `set wifi_pass`
  s.kv["wifi_pass"] = "password3";
  auto loaded = hg::WifiNetworks::load(s);
  CHECK(loaded.dirty());
  CHECK_EQ(names(loaded), std::string("Cafe,Home*,Office"));
  // A saved network named again keeps its tested mark only with the same password.
  s.kv["wifi_ssid"] = "Home";
  s.kv["wifi_pass"] = "password1";
  CHECK_EQ(names(hg::WifiNetworks::load(s)), std::string("Home*,Office"));
  s.kv["wifi_pass"] = "changed!";
  CHECK_EQ(names(hg::WifiNetworks::load(s)), std::string("Home,Office"));
}

TEST("wifi networks: erasing wifi_ssid forgets the first network") {
  MemoryStorage s;
  hg::WifiNetworks n;
  n.add("Home", "password1");
  n.add("Office", "password2");
  n.save(s);
  s.kv.erase("wifi_ssid");
  auto loaded = hg::WifiNetworks::load(s);
  CHECK(loaded.dirty());
  CHECK_EQ(names(loaded), std::string("Office"));
  loaded.save(s);
  CHECK_EQ(s.kv["wifi_ssid"], std::string("Office"));
  CHECK_EQ(names(hg::WifiNetworks::load(s)), std::string("Office"));
}

TEST("wifi networks: a damaged list falls back to the mirrored first network") {
  MemoryStorage s;
  s.kv = {{"wifi_nets", "[{\"ssid\":"}, {"wifi_ssid", "Home"}, {"wifi_pass", "password1"}};
  CHECK_EQ(names(hg::WifiNetworks::load(s)), std::string("Home"));
  s.kv["wifi_nets"] = R"([{"ssid":"Home","pass":"password1"},{"ssid":""},{"ssid":"Home"},7,{"ssid":"Office"}])";
  CHECK_EQ(names(hg::WifiNetworks::load(s)), std::string("Home,Office"));
}

TEST("wifi networks: at most five, and a sixth is refused") {
  hg::WifiNetworks n;
  for (int i = 0; i < 5; ++i) CHECK(n.add("Net" + std::to_string(i), "") == hg::WifiNetworks::Added::Added);
  CHECK(n.add("Net5", "") == hg::WifiNetworks::Added::Full);
  CHECK_EQ(n.size(), size_t(5));
  // Saving again with a new password updates in place and needs a new test.
  n.joined("Net3");
  CHECK(n.add("Net3", "password9") == hg::WifiNetworks::Added::Updated);
  CHECK_EQ(names(n), std::string("Net3,Net0,Net1,Net2,Net4"));
  CHECK(n.add("Net3", "password9") == hg::WifiNetworks::Added::Unchanged);
  // The setup page's network goes first even when the list is full; the last one drops.
  n.put_first("Setup", "password8", true);
  CHECK_EQ(names(n), std::string("Setup*,Net3,Net0,Net1,Net2"));
}

TEST("wifi networks: joining moves a network first once and marks it tested") {
  hg::WifiNetworks n;
  n.add("Home", "password1");
  n.add("Phone", "password2");
  CHECK(n.joined("Phone"));
  CHECK_EQ(names(n), std::string("Phone*,Home"));
  CHECK(!n.joined("Phone"));  // nothing to save on the next reconnect
  CHECK(!n.joined("Elsewhere"));
}

TEST("wifi networks: a list that can't be saved leaves the mirror alone") {
  MemoryStorage s;
  s.kv = {{"wifi_ssid", "Home"}};
  hg::WifiNetworks n;
  n.add("Other", "");
  s.full = true;
  CHECK(!n.save(s));
  CHECK_EQ(s.kv["wifi_ssid"], std::string("Home"));
}

TEST("wifi networks: names and passwords follow the setup page's rules") {
  CHECK(hg::wifi_network_error("Home", "").empty());
  CHECK(hg::wifi_network_error("Home", "12345678").empty());
  CHECK(hg::wifi_network_error("Home", std::string(64, 'a')).empty());
  CHECK(!hg::wifi_network_error("", "12345678").empty());
  CHECK(!hg::wifi_network_error(std::string(33, 'n'), "").empty());
  CHECK(!hg::wifi_network_error("Home", "short").empty());
  CHECK(!hg::wifi_network_error("Home", std::string(64, 'z')).empty());
  CHECK(!hg::wifi_network_error("Home", "tab\tin password").empty());
}

TEST("console args: split like ESP-IDF's console, and quote_arg round-trips") {
  using V = std::vector<std::string>;
  CHECK(hg::split_args("add  Home   secret") == V({"add", "Home", "secret"}));
  CHECK(hg::split_args(R"(add "My Home" "pass word")") == V({"add", "My Home", "pass word"}));
  CHECK(hg::split_args(R"(add "" a\ b\"c d\\e)") == V({"add", "", "a b\"c", "d\\e"}));
  CHECK(hg::split_args(R"(x"y" "a"b)") == V({"x\"y\"", "a", "b"}));
  CHECK(hg::split_args(R"("unterminated)") == V({"unterminated"}));
  for (std::string value : {"", "plain", "two  spaces", R"(q"u\o"te\)", " edge "})
    CHECK(hg::split_args(hg::quote_arg(value)) == V({value}));
}
