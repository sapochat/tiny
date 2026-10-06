"""Freeze actual face-first evidence after the documented native/ESP32 runs.
Does not build, flash, stage OTA, contact hardware or modify services.
"""
from pathlib import Path
import difflib, hashlib, importlib, json, platform, shutil, struct, subprocess, sys, tarfile, types
from PIL import Image, ImageDraw, ImageFont
R=Path(__file__).resolve().parents[1]
O=R/'artifacts/face-first'
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def git(*args): return subprocess.check_output(['git',*args],cwd=R)
# Only load image inspection: no OTA session/queue is created.
p=types.ModuleType('hermes_gadget_plugin');p.__path__=[str(R/'plugin')];sys.modules[p.__name__]=p
inspect_image=importlib.import_module('hermes_gadget_plugin.ota').inspect_image
build=R/'build/face-first-esp32/esp32s3-touch-amoled-175c'
image=inspect_image((build/'firmware.bin').read_bytes())
assert image.board=='esp32s3-touch-amoled-1.75c'
assert image.data[3]>>4==5, '32MB flash image required for exact board'
parts=(build/'partitions.bin').read_bytes();entries=[]
for i in range(0,len(parts),32):
    if parts[i:i+2]!=b'\xaaP':continue
    _,typ,sub,offset,size,name,_=struct.unpack('<HBBII16sI',parts[i:i+32])
    entries.append(dict(type=typ,subtype=sub,offset=offset,size=size,label=name.split(b'\0')[0].decode()))
slot=min(x['size'] for x in entries if x['type']==0)
assert image.size<=slot*.9
meta=dict(board=image.board,version=image.version,sha256=image.sha256,bytes=image.size,
          slot_bytes=slot,free_bytes=slot-image.size,free_percent=100*(slot-image.size)/slot,
          flash_bytes=32*1024*1024,partitions=entries)
(O/'firmware-metadata.json').write_text(json.dumps(meta,indent=2)+'\n')
(O/'firmware').mkdir(exist_ok=True)
for n in ['firmware.bin','firmware.elf','partitions.bin']:shutil.copy(build/n,O/'firmware'/n)
names=['idle','listening','thinking','speaking','reply-ready','reading','controls','approval','long-approval-end']
canvas=Image.new('RGB',(466*3,510*3),(20,20,22));draw=ImageDraw.Draw(canvas)
font=ImageFont.truetype(str(R/'assets/fonts/Geist-Regular.ttf'),22)
for i,n in enumerate(names):
    im=Image.open(O/'green'/f'{n}.png').convert('RGB');x=i%3*466;y=i//3*510
    canvas.paste(im,(x,y));draw.text((x+24,y+473),n,font=font,fill='white')
canvas.save(O/'contact-sheet.png')
files=sorted(set(git('ls-files','--modified','--others','--exclude-standard').decode().splitlines()))
initial=json.loads((O/'baseline/hashes.json').read_text())
tracked=set(git('ls-tree','-r','--name-only','HEAD').decode().splitlines())
patch=[]
for f in files:
    target=R/f
    if not target.is_file():continue
    original=O/'baseline/files'/f
    before=original.read_bytes() if original.exists() else git('show','HEAD:'+f) if f in tracked else b''
    after=target.read_bytes()
    if before==after:continue
    try: patch.extend(difflib.unified_diff(before.decode().splitlines(True),after.decode().splitlines(True),fromfile='baseline/'+f,tofile='face-first/'+f))
    except UnicodeDecodeError:patch.append(f'Binary addition/change: {f}; sha256={sha(target)}\n')
(O/'implementation.patch').write_text(''.join(patch))
(O/'working-tree.patch').write_bytes(git('diff','--binary'))
(O/'source-hashes.json').write_text(json.dumps({f:sha(R/f) for f in files if (R/f).is_file()},indent=2)+'\n')
(O/'preserved-initial.json').write_text(json.dumps({f:sha(R/f)==h for f,h in initial.items()},indent=2)+'\n')
# Complete tracked source + additions; excludes build outputs, .git and ignored secrets.
with tarfile.open(O/'source.tar.gz','w:gz') as t:
    for f in sorted(set(git('ls-files').decode().splitlines()+files)):
        if (R/f).is_file():t.add(R/f,arcname=f)
env={'python':sys.version,'platform':platform.platform(),'git_head':git('rev-parse','HEAD').decode().strip(),
     'pillow':Image.__version__,'native_library_sha256':sha(R/'build/face-first/libhgsim.so')}
(O/'environment.json').write_text(json.dumps(env,indent=2)+'\n')
# Verify the exact archived source and binary before publishing final hashes.
import xml.etree.ElementTree as ET
with tarfile.open(O/'source.tar.gz') as t:
    members=[m for m in t.getmembers() if m.isfile()]
    for m in members:
        archived=t.extractfile(m)
        assert archived is not None
        assert archived.read()==(R/m.name).read_bytes()
assert (O/'firmware/firmware.bin').read_bytes()==(build/'firmware.bin').read_bytes()
assert sha(O/'firmware/firmware.bin')==meta['sha256']
# Trusted locally generated pytest JUnit only; never parses downloaded XML.
suite=ET.parse(O/'results.xml').getroot().find('testsuite')
assert suite is not None
result=suite.attrib
assert all(result[k]=='0' for k in ['failures','errors','skipped'])
evidence=['REPORT.md','contact-sheet.png','source.tar.gz','source-hashes.json',
          'implementation.patch','working-tree.patch','results.xml','firmware-metadata.json',
          'native-build.log','ctest.log','pytest.log','esp32-build.log',
          'stale-title-regression/red.log','stale-title-regression/red.xml',
          'stale-title-regression/green.log','stale-title-regression/green.xml',
          'stale-title-regression/run.py','stale-title-regression/preservation.json',
          'stale-title-regression/contact-sheet-review.md',
          'stale-title-regression/pre-fix-source.tar.gz',
          'stale-title-regression/pre-fix-source-hashes.json',
          'stale-title-regression/pre-fix-libhgsim.so',
          'firmware/firmware.bin','firmware/firmware.elf','firmware/partitions.bin']
(O/'final-verification.json').write_text(json.dumps(dict(
    archive_matches_final_tree=True,archive_files=len(members),
    firmware_matches_build_and_metadata=True,pytest=result,
    sha256={f:sha(O/f) for f in evidence}),indent=2)+'\n')
print(json.dumps(meta,indent=2));print('Report evidence:',O)
