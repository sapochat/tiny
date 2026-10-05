"""Freeze exact local candidate, read production OTA descriptor, verify rollback."""
from pathlib import Path
import difflib,hashlib,json,subprocess,sys,tarfile
import xml.etree.ElementTree as ET
R=Path(__file__).resolve().parents[1];B=R.with_name('hermes-gadget-sdk-tiny-amoled');O=R/'artifacts/expressions'
sys.path.insert(0,str(R));from plugin.ota import inspect_image
files=sorted(set(subprocess.check_output(['git','ls-files','-co','--exclude-standard'],cwd=R,text=True).splitlines()))
changed=[];patch=[]
for name in files:
    p=R/name
    if not p.is_file():continue
    old=(B/name).read_bytes() if (B/name).is_file() else b'';new=p.read_bytes()
    if old!=new:
        changed.append(name)
        patch.extend(difflib.unified_diff(old.decode().splitlines(True),new.decode().splitlines(True),fromfile='a/'+name,tofile='b/'+name))
(O/'candidate-only.patch').write_text(''.join(patch))
with tarfile.open(O/'candidate-source.tar.gz','w:gz') as t:
    for name in files:
        if (R/name).is_file():t.add(R/name,arcname=name)
# Preserve every preexisting untracked test and all baseline files not intentionally changed.
basefiles=sorted(set(subprocess.check_output(['git','ls-files','-co','--exclude-standard'],cwd=B,text=True).splitlines()))
unchanged=[]
for name in basefiles:
    if (B/name).is_file() and name not in changed:
        assert (R/name).read_bytes()==(B/name).read_bytes(),name
        unchanged.append(name)
assert (R/'firmware/esp32/main/board.cpp').read_bytes()==(B/'firmware/esp32/main/board.cpp').read_bytes()
manifest=json.loads((O/'hardware/dist/manifest.json').read_text());b=manifest['builds'][0]
assert b['flash_size']=='32MB' and b['image_board']=='esp32s3-touch-amoled-1.75c'
app_path=O/'hardware/dist'/b['app']['path'];app=inspect_image(app_path.read_bytes())
assert app.version=='0.2.0-tiny-expr1' and app.board=='esp32s3-touch-amoled-1.75c' and app.sha256==b['app']['sha256']
assert app.data==(R/'firmware/esp32/.pio/build/esp32s3-touch-amoled-175c/firmware.bin').read_bytes()
rollback=B/'artifacts/unread/hardware/dist/hermes-gadget-esp32s3-touch-amoled-175c-0.2.0-tiny-mic30-unread1-app.bin'
r=inspect_image(rollback.read_bytes());assert r.version=='0.2.0-tiny-mic30-unread1' and r.board==app.board
inspection={'candidate':{'path':str(app_path),'version':app.version,'board':app.board,'sha256':app.sha256,'bytes':len(app.data)},'rollback':{'path':str(rollback),'version':r.version,'board':r.board,'sha256':r.sha256,'bytes':len(r.data)},'flash_size':b['flash_size'],'mic_gain_board_identical':True}
(O/'hardware/inspection.json').write_text(json.dumps(inspection,indent=2))
runs={}
for p in O.glob('*.xml'):
    # Trusted local pytest JUnit receipts, not user-supplied XML.
    s=next(ET.parse(p).getroot().iter('testsuite'));runs[p.stem]={k:int(s.attrib[k]) for k in ['tests','failures','errors','skipped']}
meta={'changes_from_amoled':changed,'baseline_files_identical':len(unchanged),'baseline_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=B,text=True).strip(),'tests':runs,'native_library_sha256':hashlib.sha256((R/'build/host/libhgsim.so').read_bytes()).hexdigest(),'inspection':inspection}
(O/'verification.json').write_text(json.dumps(meta,indent=2))
versions={}
for command in [['.venv/bin/python','--version'],['.venv/bin/pio','--version'],['.venv/bin/cmake','--version'],['g++','--version'],['uv','pip','freeze','--python','.venv/bin/python']]:
    p=subprocess.run(command,cwd=R,text=True,capture_output=True);versions[' '.join(command)]=p.stdout+p.stderr
(O/'versions.json').write_text(json.dumps(versions,indent=2))
(O/'SHA256SUMS').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+str(p.relative_to(O))+'\n' for p in sorted(O.rglob('*')) if p.is_file() and p.name!='SHA256SUMS'))
print(json.dumps(meta,indent=2))
