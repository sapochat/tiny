"""Freeze candidate sources, compare the preserved baseline, verify local artifacts."""
from pathlib import Path
import difflib
import hashlib
import json
import subprocess
import tarfile
import xml.etree.ElementTree as ET
import sys

root = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root))
from plugin.ota import inspect_image
old = root.with_name('hermes-gadget-sdk-tiny-unread')
out = root/'artifacts/amoled'
files = subprocess.check_output(['git','ls-files','-co','--exclude-standard'],cwd=root,text=True).splitlines()
files = sorted(set(files))
changes=[]
patch=[]
for name in files:
    p=root/name
    if not p.is_file(): continue
    previous=(old/name).read_bytes() if (old/name).is_file() else b''
    current=p.read_bytes()
    if current==previous: continue
    changes.append(name)
    patch.extend(difflib.unified_diff(previous.decode().splitlines(True),current.decode().splitlines(True),fromfile='a/'+name,tofile='b/'+name))
(out/'candidate-only.patch').write_text(''.join(patch))
with tarfile.open(out/'candidate-source.tar.gz','w:gz') as t:
    for name in files:
        p=root/name
        if p.is_file(): t.add(p,arcname=name)

unchanged=0
with tarfile.open(old/'artifacts/unread/candidate-source.tar.gz') as t:
    for m in t.getmembers():
        p=old/m.name
        if m.isfile() and p.is_file() and '__pycache__' not in m.name and m.name.startswith(('firmware/','tests/')):
            stored=t.extractfile(m)
            assert stored is not None
            assert p.read_bytes()==stored.read(),m.name
            unchanged+=1
assert (root/'firmware/esp32/main/board.cpp').read_bytes()==(old/'firmware/esp32/main/board.cpp').read_bytes()
manifest=json.loads((out/'hardware/dist/manifest.json').read_text())
b=manifest['builds'][0]
assert b['flash_size']=='32MB'
app=inspect_image((out/'hardware/dist'/b['app']['path']).read_bytes())
assert app.board=='esp32s3-touch-amoled-1.75c'
assert app.version=='0.2.0-tiny-mic30-amoled1' and len(app.version.encode())<32
assert app.sha256==b['app']['sha256']
assert app.data==(root/'firmware/esp32/.pio/build/esp32s3-touch-amoled-175c/firmware.bin').read_bytes()
for item in [b['app'],b['image'],manifest['licenses']]:
    data=(out/'hardware/dist'/item['path']).read_bytes()
    assert len(data)==item['size']
    assert hashlib.sha256(data).hexdigest()==item['sha256']
rect={}
for name in ['rectangular-idle','rectangular-listening']:
    hashes=[json.loads((out/r/(name+'.json')).read_text())['raw_rgb565_sha256'] for r in ['red2','green4']]
    assert hashes[0]==hashes[1]
    rect[name]=hashes[0]
runs={}
for p in sorted(out.glob('*/results.xml')):
    # These are our own local pytest receipts, not untrusted XML uploads.
    s=next(ET.parse(p).getroot().iter('testsuite'))
    runs[p.parent.name]={k:int(s.attrib[k]) for k in ['tests','failures','errors','skipped']}
(out/'verification.json').write_text(json.dumps({'changed_from_unread':changes,'baseline_files_verified_unchanged':unchanged,'mic_board_file_byte_identical':True,'app_sha256':app.sha256,'rectangular_framebuffer_identical':rect,'runs':runs,'native_library_sha256':hashlib.sha256((root/'build/host/libhgsim.so').read_bytes()).hexdigest()},indent=2))
entries=[]
for p in sorted(out.rglob('*')):
    if p.is_file() and p.name!='SHA256SUMS':
        entries.append(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+str(p.relative_to(out)))
(out/'SHA256SUMS').write_text('\n'.join(entries)+'\n')
print(json.dumps({'changed_files':changes,'baseline_verified':unchanged,'runs':runs,'app_sha256':app.sha256},indent=2))
