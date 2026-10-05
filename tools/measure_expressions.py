"""Read actual production-renderer RGB565 frames; assert exact invariants."""
from pathlib import Path
import hashlib,json
import numpy as np
from PIL import Image
R=Path(__file__).resolve().parents[1];O=R/'artifacts/expressions'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
rect=[]
for p in sorted((O/'native-baseline').glob('*.rgb565')):
    q=O/'native-final'/p.name
    assert p.read_bytes()==q.read_bytes(),p.name
    rect.append({'frame':p.name,'sha256':sha(q)})
assert len(rect)==30
files=sorted((O/'native-final').glob('round-*'),key=lambda p:int(p.name.split('-')[1]))
def raw(p):return np.frombuffer(p.read_bytes(),dtype='<u2').reshape(466,466)
def face(p):return raw(p)[112:304,137:329]
def rgb(a):return np.stack(((a>>11)*255//31,((a>>5)&63)*255//63,(a&31)*255//31),axis=-1).astype('uint8')
base=face(files[0]);support=np.zeros((192,192),bool);support[72:105,34:94]=1;support[111:130,41:64]=1
last=base;entries=[];peak=0;images=[]
for p in files:
    images.append(Image.fromarray(rgb(raw(p))))
    if '-hidden.' in p.name:continue
    a=face(p)
    assert np.array_equal(base[~support],a[~support]),p.name
    if '-entry.' in p.name:
        changed=int(np.count_nonzero(a!=last));entries.append({'frame':p.name,'changed_pixels':changed});assert changed==0,p.name
    else:
        delta=int(np.abs(rgb(a).astype(int)-rgb(last).astype(int)).max());peak=max(peak,delta);assert delta<=40,p.name
    last=a
images[0].save(O/'native-stress.gif',save_all=True,append_images=images[1:],duration=100,loop=0)
meta={'rectangle_frames_exactly_equal':len(rect),'rectangle_frames':rect,'stress_boundary_frames':entries,'max_channel_step_per_render':peak,'static_outside_face_support_changed_pixels':0,'round_frames':len(files),'frame_hashes':{p.name:sha(p) for p in files}}
(O/'native-measurements.json').write_text(json.dumps(meta,indent=2));print(json.dumps({k:v for k,v in meta.items() if k not in ('rectangle_frames','frame_hashes')},indent=2))
