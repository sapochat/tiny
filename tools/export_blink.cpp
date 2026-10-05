#include "hg/mascot.hpp"
#include <cstdio>
int main(){auto b=hg::mascot::pick(192,hg::mascot::Frame::Blink);printf("P5\n192 192\n255\n");for(int y=0;y<192;++y)for(int x=0;x<192;++x)putchar(b->ink(x,y)?255:0);}
