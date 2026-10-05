// Native relative-only renderer timing. No device / bus / physical FPS claim.
#include "hg/ui.hpp"
#include <chrono>
#include <cstdio>
#include <vector>
struct Display : hg::Display {
  std::vector<uint16_t> pixels = std::vector<uint16_t>(466*466);
  uint64_t rows = 0;
  hg::DisplayInfo info() const override { return {466,466,false,true,true}; }
  uint16_t* framebuffer() override { return pixels.data(); }
  void flush(uint16_t a,uint16_t b) override { rows += b-a; }
};
int main() {
  for (auto screen : {hg::Screen::Ready,hg::Screen::Listening,hg::Screen::Thinking,hg::Screen::Responding}) {
    Display d; hg::Ui ui(d); hg::UiModel m;
    m.screen=screen; m.hero=true; m.link=hg::Link::Online;
    m.headline="Hermes"; m.detail="A local timing fixture"; m.hint="Down: Controls";
    m.speaking=screen==hg::Screen::Responding;
    auto t=std::chrono::steady_clock::now();
    constexpr int count=1000;
    for (int i=0;i<count;++i) { m.frame=i; m.level=(i%21)*5; ui.render(m); }
    auto us=std::chrono::duration_cast<std::chrono::microseconds>(std::chrono::steady_clock::now()-t).count();
    std::printf("%s: %.2f us/tick, %.2f flushed_rows/tick\n",hg::screen_name(screen),double(us)/count,double(d.rows)/count);
  }
}
