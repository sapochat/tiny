// Proportional gray4 text, bounded static atlas, no draw-time allocation.
#pragma once
#include "hg/canvas.hpp"
#include "hg/geist_assets.hpp"
#include <algorithm>
#include <string>
#include <string_view>
#include <vector>
namespace hg::geist {
inline uint32_t next(std::string_view s, size_t& p) {
  const auto first=static_cast<uint8_t>(s[p++]);
  if (first<128) return first;
  int n=first>=0xc2 && first<=0xdf?1:first>=0xe0 && first<=0xef?2:first>=0xf0 && first<=0xf4?3:0;
  if (!n) return 0xfffd;
  uint32_t cp=first & ((1u<<(6-n))-1);
  const size_t start=p;
  for(int i=0;i<n;++i) {
    if(p>=s.size() || (static_cast<uint8_t>(s[p])&0xc0)!=0x80) return 0xfffd;
    cp=(cp<<6)|(static_cast<uint8_t>(s[p++])&63);
  }
  if ((p-start==1 && cp<128) || (p-start==2 && cp<2048) ||
      (p-start==3 && cp<65536) || cp>0x10ffff || (cp>=0xd800 && cp<=0xdfff)) return 0xfffd;
  return cp;
}
inline const geist_data::Glyph& glyph(uint32_t cp,int size) {
  unsigned face=0;
  while(face+1<sizeof(geist_data::sizes)/sizeof(geist_data::sizes[0]) && geist_data::sizes[face]<static_cast<unsigned>(size)) ++face;
  auto first=geist_data::codes, last=first+geist_data::count;
  auto it=std::lower_bound(first,last,cp);
  unsigned index=it!=last && *it==cp?static_cast<unsigned>(it-first):geist_data::fallback_index;
  return geist_data::glyphs[face*geist_data::count+index];
}
inline int width(std::string_view s,int size) {
  int w=0; size_t p=0;
  while(p<s.size()) w+=glyph(next(s,p),size).advance;
  return w;
}
inline uint16_t blend(uint16_t fg,uint16_t bg,unsigned a) {
  const unsigned b=15-a;
  return static_cast<uint16_t>(((((fg>>11)*a+(bg>>11)*b+7)/15)<<11)|
      (((((fg>>5)&63)*a+((bg>>5)&63)*b+7)/15)<<5)|(((fg&31)*a+(bg&31)*b+7)/15));
}
inline void draw(Canvas& c,int x,int y,const geist_data::Glyph& g,uint16_t fg,uint16_t bg) {
  unsigned i=0, offset=g.offset;
  while(i<g.w*g.h) {
    const unsigned token=geist_data::pixels[offset++], a=token&15;
    const unsigned end=std::min<unsigned>(g.w*g.h,i+(token>>4)+1);
    for(;i<end;++i) if(a) c.pixel(x+g.x+i%g.w,y+g.y+i/g.w,blend(fg,bg,a));
  }
}
inline void text(Canvas& c,int x,int y,std::string_view s,int size,uint16_t fg,uint16_t bg=0) {
  size_t p=0;
  while(p<s.size()) {
    const auto& g=glyph(next(s,p),size);
    draw(c,x,y,g,fg,bg);
    x+=g.advance;
  }
}
// The large display face holds only code characters (digits, capitals, '-').
inline const geist_data::Glyph* display_glyph(uint32_t cp) {
  auto first=geist_data::display_codes, last=first+geist_data::display_count;
  auto it=std::lower_bound(first,last,cp);
  return it!=last && *it==cp ? &geist_data::display_glyphs[it-first] : nullptr;
}
// Width of `s` in the display face, or -1 when any character is not in it.
inline int display_width(std::string_view s) {
  int w=0; size_t p=0;
  while(p<s.size()) { const auto* g=display_glyph(next(s,p)); if(!g) return -1; w+=g->advance; }
  return w;
}
inline void display_text(Canvas& c,int x,int y,std::string_view s,uint16_t fg,uint16_t bg=0) {
  size_t p=0;
  while(p<s.size()) {
    const auto* g=display_glyph(next(s,p));
    if(!g) return;
    draw(c,x,y,*g,fg,bg);
    x+=g->advance;
  }
}
// Every source byte is retained in a line (except explicit newline delimiters).
// Prefer word boundaries; long words and unsupported UTF-8 remain scrollable.
inline std::vector<std::string> wrap(std::string_view s,int max_width,int size=24) {
  std::vector<std::string> out;
  size_t start=0,p=0,space=std::string_view::npos;
  int w=0;
  while(p<s.size()) {
    const size_t before=p;
    const auto cp=next(s,p);
    if(cp=='\n') { out.emplace_back(s.substr(start,before-start)); start=p; w=0; space=std::string_view::npos; continue; }
    const int advance=glyph(cp,size).advance;
    if(w+advance>max_width && before>start) {
      const size_t end=space!=std::string_view::npos?space:before;
      out.emplace_back(s.substr(start,end-start));
      start=end; p=end; w=0; space=std::string_view::npos; continue;
    }
    w+=advance;
    if(cp==' ' && before>start) {
      // Keep short number+unit tokens together where they fit on a line.
      // Preserve source bytes; no NBSP substitution or new glyph needed.
      size_t n=before;
      while(n>start && s[n-1]!=' ' && s[n-1]!='\n') --n;
      size_t end=p;
      while(end<s.size() && s[end]!=' ' && s[end]!='\n') ++end;
      auto unit=s.substr(p,end-p);
      while(!unit.empty() && (unit.back()==':' || unit.back()==',' || unit.back()=='.')) unit.remove_suffix(1);
      const bool number=n<before && s[n]>='0' && s[n]<='9';
      const bool paired=number && (unit=="am" || unit=="pm" || unit=="AM" || unit=="PM" ||
          unit=="min" || unit=="minutes" || unit=="hours" || unit=="degrees" || unit=="kg" || unit=="km");
      if(!paired || width(s.substr(n,end-n),size)>max_width) space=p;
    }
  }
  if(start<s.size() || out.empty() || (!s.empty() && s.back()=='\n')) out.emplace_back(s.substr(start));
  return out;
}
inline std::string fit(std::string_view s,int max_width,int size) {
  if(width(s,size)<=max_width) return std::string(s);
  size_t p=0,end=0;int w=width("…",size);
  while(p<s.size()) {auto cp=next(s,p);w+=glyph(cp,size).advance;if(w>max_width)break;end=p;}
  return std::string(s.substr(0,end))+"…";
}
}
