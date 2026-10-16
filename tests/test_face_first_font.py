"""Native hub/touch/framebuffer regression; oracle is the source TTF, not atlas.
Rerun commands and RED/GREEN results: artifacts/face-first/font-regression/.
"""
import json
import struct
from pathlib import Path
import pytest
from PIL import Image, ImageDraw, ImageFont
from test_touch_navigation import rig, swipe
from test_face_first import capture, OUT

ROOT = Path(__file__).resolve().parents[1]
CODES = sorted(set(range(32,127)) | set(range(160,256)) | {
    0x2013,0x2014,0x2018,0x2019,0x201c,0x201d,0x2026,0x203a,0x2191,0x2193,0xfffd})

def rgb(r,g,b):
    return ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)

def oracle(label, size, fg, bg=0):
    font = ImageFont.truetype(str(ROOT/'assets/fonts/Geist-Regular.ttf'), size)
    width = sum(round(font.getlength(ch)) for ch in label)
    pixels = [[bg]*max(1,width+4) for _ in range(size+10)]
    cursor = 0
    for ch in label:
        x,y,x1,y1 = font.getbbox(ch,anchor='la')
        mask = Image.new('L',(max(1,x1-x),max(1,y1-y)))
        ImageDraw.Draw(mask).text((-x,-y),ch,font=font,fill=255,anchor='la')
        for yy in range(y1-y):
            for xx in range(x1-x):
                a=(mask.getpixel((xx,yy))+8)//17
                if a and 0 <= cursor+x+xx < len(pixels[0]):
                    channels=[(((fg>>shift)&bits)*a+((bg>>shift)&bits)*(15-a)+7)//15
                              for shift,bits in [(11,31),(5,63),(0,31)]]
                    pixels[y+yy][cursor+x+xx]=(channels[0]<<11)|(channels[1]<<5)|channels[2]
        cursor += round(font.getlength(ch))
    return width,pixels

def _in_pill(px,py,rect):
    # Inside the rounded pill (radius h/2) that the renderer fills.
    x,y,w,h=rect; r=h//2
    if not (x<=px<x+w and y<=py<y+h): return False
    cx=min(max(px,x+r),x+w-1-r); cy=min(max(py,y+r),y+h-1-r)
    return (px-cx)**2+(py-cy)**2<=r*r
def assert_text(s,label,size,y,fg,bg=0,x=None,pill=None):
    width,expected=oracle(label,size,fg,bg)
    if x is None: x=(466-width)//2
    actual=struct.unpack('<'+'H'*(466*466),s.device.framebuffer_rows())
    # Include blank margins so extra fallback-box pixels cannot go unnoticed. On a pill, a
    # blank margin pixel outside its rounded fill is the glass, not the label (R-06: a 24px
    # label's margin reaches the corner of a 138px pill); every glyph pixel is still compared.
    mismatches=[(xx,yy,actual[(y+yy)*466+x+xx],value)
                for yy,row in enumerate(expected) for xx,value in enumerate(row)
                if actual[(y+yy)*466+x+xx]!=value
                and not (pill and value==bg and not _in_pill(x+xx,y+yy,pill))]
    OUT.mkdir(parents=True,exist_ok=True)
    with (OUT/'font-comparisons.jsonl').open('a') as f:
        f.write(json.dumps(dict(label=label,size=size,x=x,y=y,mismatches=len(mismatches),
                               first=mismatches[:8]))+'\n')
    assert not mismatches, (label, 'source TTF/framebuffer mismatch', mismatches[:8])

@pytest.mark.parametrize('view',['reading','controls','idle','reply-ready','speaking'])
def test_native_ui_known_symbols_match_source_font(rig,view):
    s=rig
    if view=='controls': swipe(s,dy=100)
    elif view!='idle':
        s.send_fixture('turn.start',turn='font')
        s.send_fixture('reply.delta',text='Known arrows ↑ ↓ and chevron ›')
        if view in ('reply-ready','speaking'):
            swipe(s,dx=100)
            if view=='reply-ready':
                s.send_fixture('reply',text='Known arrows ↑ ↓ and chevron › confirmed')
                s.send_fixture('turn.end',turn='font',outcome='success')
            else: s.send_fixture('audio.start',stream=92,rate=16000,format='pcm16')
    capture(s,'font-'+view)
    dim,text,surface=rgb(164,164,169),rgb(240,239,235),rgb(32,32,35)
    def pill(name,label):
        from PIL import ImageFont
        x,y,w,h=s.status()['ui']['controls'][name]
        # R-06: Home/reader action row labels are 24px; R-08: so are quick controls' bands.
        size=24 if y==356 or (view=='controls' and y in (250,322,394)) else 18
        width=sum(round(ImageFont.truetype(str(ROOT/'assets/fonts/Geist-Regular.ttf'),size).getlength(c)) for c in label)
        assert_text(s,label,size,y+(h-(30 if size==24 else 22))//2,text,surface,x=x+(w-width)//2,pill=(x,y,w,h))
    # Interaction v1 replaced the swipe-only footers with visible tap routes; the same
    # source-TTF oracle now checks their labels, and the reply body keeps ↑ ↓ › coverage.
    if view=='reading':
        assert_text(s,'Latest reply',24,55,text)
        # Measured 24px wrapping (303px) splits the fixture after "and".
        assert_text(s,'Known arrows ↑ ↓ and',24,108,text,x=78)
        assert_text(s,'chevron ›',24,142,text,x=78)
        pill('stop','Stop task')
    elif view=='controls':
        assert_text(s,'Quick controls',24,55,text)
        pill('settings','Settings')
    elif view=='idle': assert_text(s,'↓  Controls',24,395,dim)  # R-06: 24px (was 18px at y402)
    elif view=='reply-ready': assert_text(s,'Read reply  ↑',24,368,text,surface)  # R-06: 24px (was 18px at y372)
    else:
        pill('silence','Mute voice')
        pill('stop','Stop task')

def test_native_reply_entire_intended_glyph_coverage(rig):
    s=rig
    s.send_fixture('turn.start',turn='font-coverage')
    # Short lines, one visible page at a time; no wrap or scrolling changes the oracle.
    # The page size is the advertised row count (seven since interaction v1 reserved the
    # bottom action row), so every intended codepoint is still compared.
    rows=next(m for m in s.sent if m['type']=='hello')['caps']['display']['text_rows']
    lines=[''.join(map(chr,CODES[i:i+8])) for i in range(0,len(CODES),8)]
    for start in range(0,len(lines),rows):
        page=lines[start:start+rows]
        s.send_fixture('reply',text='\n'.join(page))
        capture(s,'font-coverage-'+str(start))
        for row,label in enumerate(page):
            assert_text(s,label,24,108+34*row,rgb(240,239,235),x=78)
    # A genuinely unsupported scalar must retain the deliberately visible fallback.
    s.send_fixture('reply',text='🦉')
    capture(s,'font-unsupported-fallback')
    assert_text(s,'�',24,108,rgb(240,239,235),x=78)
