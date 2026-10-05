"""Offline deterministic expression compositor. No providers or video playback.
Existing generated eyes/mouth are transplanted only inside bounded facial masks;
shared master geometry and native-resolution static pixels remain identical.
"""
from pathlib import Path
import hashlib,json
import numpy as np
from PIL import Image,ImageDraw,ImageFilter
R=Path(__file__).resolve().parents[1]
A=R/'artifacts/mascot-motion'; O=R/'artifacts/expressions/assets';O.mkdir(parents=True,exist_ok=True)
base=Image.open(A/'reference-black.png').convert('L')
eyes=Image.open(A/'expression-states-v4/selected/eye-brow-mask.png').convert('L')
mouth=Image.new('L',base.size);ImageDraw.Draw(mouth).polygon([(233,604),(319,604),(327,634),(316,672),(239,672),(230,638)],fill=255)
mouth=mouth.filter(ImageFilter.GaussianBlur(2))
sources={'idle':A/'reference-black.png','listening':A/'expression-states-v4/selected/listening.png','thinking':A/'expression-states-v3/keyframes/thinking-replacement/image.png','ready':A/'expression-states-v3/keyframes/ready/image.png'}
masters={'idle':base}
for name in ('listening','thinking','ready'):
    donor=Image.open(sources[name]).convert('L').resize(base.size)
    if name!='listening':
        donor=donor.point(lambda v:255 if v>=150 else 0)
        # Local landmark registration; donor face geometry never replaces base.
        shifted=Image.new('L',base.size,255)
        shifted.paste(donor,(-28,29) if name=='ready' else (-10,30))
        donor=shifted
    masters[name]=Image.composite(donor,base,mouth if name=='ready' else eyes)
# Keep old closed-eye linework as blink source, with unchanged outline.
# Parse generated mascot through a tiny compiled helper, passed by build script.
blink_path=O/'legacy-blink.pgm'
if blink_path.exists():
    blink=Image.open(blink_path).convert('L')
else:raise SystemExit('first export legacy blink using tools/export_blink.cpp')
size=(192,192); native={k:np.array(v.resize(size,Image.Resampling.LANCZOS)) for k,v in masters.items()}
support=np.zeros((192,192),bool);support[72:105,34:94]=True;support[111:130,41:64]=True
for name in native:native[name][~support]=native['idle'][~support]
# Only eye pixels come from the proven closed-eye asset, never its outline.
bm=np.array(eyes.resize(size,Image.Resampling.LANCZOS))/255
native['blink']=np.rint(np.array(blink)*bm+native['idle']*(1-bm)).astype('uint8')
native['blink'][~support]=native['idle'][~support]
eyes.save(O/'eye-brow-mask.png');mouth.save(O/'mouth-mask.png')
master_checks={}
for name,im in masters.items():
    mask = mouth if name=='ready' else eyes
    outside=np.array(mask)==0
    master_checks[name]=int(np.count_nonzero(np.array(im)[outside]!=np.array(base)[outside]))
    assert master_checks[name]==0
    im.save(O/f'{name}-master.png')
(O/'master-invariants.json').write_text(json.dumps(master_checks,indent=2))
for name,im in native.items():Image.fromarray(im).save(O/f'{name}-192.png')
# One 8-bit shared master plus five compact 60x58 facial patches (54 KB flash).
x,y,w,h=34,72,60,58
out=['// Generated offline by tools/build_expressions.py; see artifacts/expressions/README.md.','#pragma once','#include <cstdint>','namespace hg::expression {',f'constexpr int x={x}, y={y}, w={w}, h={h}, count=w*h;']
def emit(name,im):
    vals=im.flatten().tolist();out.append('inline constexpr uint8_t '+name+'[] = {')
    out.extend(','.join(map(str,vals[i:i+32]))+',' for i in range(0,len(vals),32));out.append('};')
emit('base',native['idle'])
for name,im in native.items():emit(name,im[y:y+h,x:x+w])
out.append('inline constexpr const uint8_t* poses[] = {idle,listening,thinking,ready,blink};\n}')
(R/'firmware/core/include/hg/expression_assets.hpp').write_text('\n'.join(out)+'\n')
meta={'sources':{k:{'path':str(v.relative_to(R)),'sha256':hashlib.sha256(v.read_bytes()).hexdigest()} for k,v in sources.items()},'native_size':192,'patch':[x,y,w,h],'flash_bytes':192*192+5*w*h,'static_changed_pixels':{k:int(np.count_nonzero(im[~support]!=native['idle'][~support])) for k,im in native.items()},'method':'Offline feathered local feature transplant; original common base. V3 ready still, not MP4.'}
(O/'manifest.json').write_text(json.dumps(meta,indent=2))
sheet=Image.new('RGB',(5*384,448))
for i,(name,im) in enumerate(native.items()):
    sheet.paste(Image.fromarray(im).resize((384,384)),(i*384,32));ImageDraw.Draw(sheet).text((i*384+10,10),name,fill='white')
sheet.save(O/'selection.png')
print(json.dumps(meta,indent=2))
