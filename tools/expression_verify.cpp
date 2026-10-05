// Deterministic production Ui framebuffer evidence, no alternate renderer.
#include "hg/ui.hpp"
#include <cstdio>
#include <cstdlib>
#include <string>
#include <vector>
struct Display : hg::Display {
  int w,h; bool round; std::vector<uint16_t> p;
  Display(int w,int h,bool r):w(w),h(h),round(r),p(w*h){}
  hg::DisplayInfo info() const override {return {uint16_t(w),uint16_t(h),false,true,round};}
  uint16_t* framebuffer() override{return p.data();}
  void flush(uint16_t,uint16_t) override{}
  void save(const std::string& f) {FILE* o=fopen(f.c_str(),"wb");if(!o)abort();fwrite(p.data(),2,p.size(),o);fclose(o);}
};
int main(int argc,char** argv){
  const std::string out=argv[1];
  Display d(320,240,false);hg::Ui u(d);hg::UiModel m;
  m.link=hg::Link::Online;m.title="Fixture";m.headline="Hermes";m.detail="Local fixture";m.body="This is a deterministic rectangular regression.\nSecond line.";m.hint="Talk to Hermes";
  int n=0;
  for(auto screen:{hg::Screen::Ready,hg::Screen::Listening,hg::Screen::Thinking,hg::Screen::Responding,hg::Screen::Prompt,hg::Screen::Settings}){
    m.screen=screen;m.hero=screen!=hg::Screen::Responding && screen!=hg::Screen::Settings;m.speaking=screen==hg::Screen::Responding;m.yes="Yes";m.no="No";
    for(int f:{2,44,45,46,50}){m.frame=f;u.render(m);d.save(out+"/rect-"+std::to_string(n++)+".rgb565");}
  }
#ifdef EXPRESSION_VERIFY
  Display r(466,466,true);hg::Ui v(r);hg::UiModel q;q.hero=true;q.screen=hg::Screen::Ready;q.link=hg::Link::Online;q.frame=10;
  int k=0;auto snap=[&](const char* label){v.render(q);r.save(out+"/round-"+std::to_string(k++)+"-"+label+".rgb565");};
  auto tick=[&](){++q.frame;snap("tick");};
  snap("base");q.frame=44;snap("blink-entry");tick();tick();
  q.screen=hg::Screen::Listening;snap("listening-entry");tick();tick();
  q.screen=hg::Screen::Thinking;snap("thinking-entry");tick();
  q.screen=hg::Screen::Listening;snap("reversal-entry");tick();
  q.screen=hg::Screen::Thinking;snap("thinking-entry");for(int i=0;i<8;++i)tick();
  q.screen=hg::Screen::Responding;q.speaking=true;snap("speaking-entry");for(int i=0;i<8;++i)tick();
  q.speaking=false;q.screen=hg::Screen::Ready;q.reply_ready=true;snap("ready-entry");for(int i=0;i<8;++i)tick();
  // Hidden controls and approval must not advance the last visible pose.
  q.hero=false;q.quick_controls=true;snap("hidden");q.frame+=20;snap("hidden");q.quick_controls=false;q.touch_prompt=true;snap("hidden");
  q.touch_prompt=false;q.hero=true;snap("return-entry");
  v.invalidate();q.frame+=600;snap("wake-entry");
  q.reply_ready=false;snap("idle-entry");for(int i=0;i<8;++i)tick();
#endif
}
