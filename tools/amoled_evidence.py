"""Freeze each local run BEFORE tests; no device access."""
import os
from pathlib import Path
import subprocess
import sys
import tarfile

root = Path(__file__).resolve().parents[1]
os.chdir(root)
run = sys.argv[1]
out = root / 'artifacts/amoled' / run
out.mkdir(parents=True, exist_ok=False)
with tarfile.open(out/'source.tar.gz','w:gz') as t:
    for name in ['firmware/core','firmware/sim','firmware/tests','tests','python','plugin','tools/amoled_evidence.py','firmware/CMakeLists.txt','firmware/esp32/platformio.ini']:
        t.add(name, filter=lambda i: None if '__pycache__' in i.name else i)
(out/'source.patch').write_bytes(subprocess.check_output(['git','diff']))
(out/'versions.txt').write_bytes(subprocess.check_output([sys.executable,'-m','pip','freeze']) + subprocess.check_output(['c++','--version']) + subprocess.check_output(['git','rev-parse','HEAD']))
env = os.environ.copy()
env['PYTHONPATH']='python'
env['SWIPE_ARTIFACTS']=str(out)
env['AMOLED_ARTIFACTS']=str(out)
commands = [[sys.executable,'-m','hermes_gadget','build-sim','--test'], [sys.executable,'-m','pytest',*sys.argv[2:],'--basetemp='+os.path.join(os.environ.get('TMPDIR','/tmp'),'am-'+run),'--junitxml='+str(out/'results.xml'),'-v']]
(out/'commands.txt').write_text('PATH=./.venv/bin:$PATH PYTHONPATH=python\nSWIPE_ARTIFACTS='+str(out)+' AMOLED_ARTIFACTS='+str(out)+'\n'+'\n'.join(' '.join(c) for c in commands))
for name, command in zip(['build.log','tests.log'], commands):
    with (out/name).open('w') as f:
        result = subprocess.run(command,env=env,stdout=f,stderr=subprocess.STDOUT)
    print(name, result.returncode, flush=True)
    if result.returncode:
        print((out/name).read_text()[-15000:])
        sys.exit(result.returncode)
print((out/'tests.log').read_text()[-1200:])
