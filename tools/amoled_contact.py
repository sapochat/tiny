"""Assemble unscaled native framebuffer PNGs; annotations live OUTSIDE each frame."""
from pathlib import Path
import sys
from PIL import Image, ImageDraw
p = Path(sys.argv[1])
names = ['idle','listening','thinking','speaking','unread','response','controls','approval']
im = Image.new('RGB',(466*4,496*2),(20,20,20))
d = ImageDraw.Draw(im)
for i,name in enumerate(names):
    src = Image.open(p/(name+'.png'))
    assert src.size == (466,466)
    x,y=(i%4)*466,(i//4)*496
    im.paste(src,(x,y+30))
    d.text((x+12,y+8),name,fill='white')
im.save(p/'contact.png')
print(p/'contact.png')
