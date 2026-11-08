#include <string>
#include <vector>

#include "check.hpp"
#include "wifi_pick.hpp"

namespace {
const std::vector<std::string> kSaved = {"Home", "Office", "Phone"};
}

TEST("wifi pick: a lost link is retried once before scanning") {
  hg::WifiPick p;
  p.reset(kSaved.size());
  CHECK(!p.should_scan());
  p.failed();  // the link dropped
  CHECK(!p.should_scan());
  p.failed();  // the retry failed
  CHECK(p.should_scan());
  p.connected();
  CHECK(!p.should_scan());
}

TEST("wifi pick: one saved network never scans") {
  hg::WifiPick p;
  p.reset(1);
  for (int i = 0; i < 5; ++i) p.failed();
  CHECK(!p.should_scan());
}

TEST("wifi pick: the first network wins when the scan sees it, else the strongest") {
  hg::WifiPick p;
  p.reset(kSaved.size());
  CHECK_EQ(p.choose(kSaved, {{"Phone", -40}, {"Home", -80}, {"Office", -60}}), size_t(0));
  p.reset(kSaved.size());
  CHECK_EQ(p.choose(kSaved, {{"Neighbour", -30}, {"Phone", -70}, {"Office", -55}, {"Office", -75}}), size_t(1));
  CHECK_EQ(p.current(), size_t(1));
}

TEST("wifi pick: a network that keeps failing is passed over while another is in range") {
  hg::WifiPick p;
  p.reset(kSaved.size());
  p.failed();
  p.failed();  // Home is in range but refuses us (a changed password)
  CHECK_EQ(p.choose(kSaved, {{"Home", -40}, {"Phone", -80}}), size_t(2));
  p.failed();
  p.failed();
  // Both in range have now failed twice: start them over, first network first.
  CHECK_EQ(p.choose(kSaved, {{"Home", -40}, {"Phone", -80}}), size_t(0));
  CHECK(!p.should_scan());
}

TEST("wifi pick: with no saved network in sight it tries the next one in turn") {
  hg::WifiPick p;
  p.reset(kSaved.size());
  CHECK_EQ(p.choose(kSaved, {}), size_t(1));
  CHECK(!p.should_scan());  // the next network gets its own tries
  CHECK_EQ(p.choose(kSaved, {{"Neighbour", -30}}), size_t(2));
  CHECK_EQ(p.choose(kSaved, {}), size_t(0));
  // Round again: a network that failed on the last round gets fresh tries.
  for (size_t expect : {size_t(1), size_t(2), size_t(0)}) {
    p.failed();
    p.failed();
    CHECK(p.should_scan());
    CHECK_EQ(p.choose(kSaved, {}), expect);
    CHECK(!p.should_scan());
  }
}

TEST("wifi pick: a list that changed under it keeps the current network") {
  hg::WifiPick p;
  p.reset(2, 1);
  CHECK_EQ(p.choose(kSaved, {{"Home", -40}}), size_t(1));
}
