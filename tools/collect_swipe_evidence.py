"""Freeze local verification inputs/versions and hash artifacts; never contacts a device.
Run after verification: .venv/bin/python tools/collect_swipe_evidence.py
"""
import hashlib
import json
import platform
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'artifacts/swipes'
OUT.mkdir(parents=True, exist_ok=True)


def command(*args):
    p = subprocess.run(args, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return {'argv': args, 'exit_code': p.returncode, 'output': p.stdout}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


env = {
    'python': sys.version, 'platform': platform.platform(),
    'base': command('git', 'rev-parse', 'HEAD'),
    'branch': command('git', 'branch', '--show-current'),
    'compiler': command('c++', '--version'),
    'cmake': command(str(ROOT/'.venv/bin/cmake'), '--version'),
    'ninja': command(str(ROOT/'.venv/bin/ninja'), '--version'),
    'packages': command(sys.executable, '-m', 'pip', 'freeze'),
    'platformio': command(str(ROOT/'.venv/bin/pio'), 'pkg', 'list', '-d', 'firmware/esp32', '-e', 'esp32s3-touch-amoled-175c'),
    'node': command('node', '--version'),
    'npm': command('npm', '--version'),
    'provider_policy': 'Only loopback development hub and literal local fixtures; HERMES_AGENT_DIR=/nonexistent for full regression.',
    'physical_validation': 'Not performed. No flashing, OTA, restart or live configuration writes.',
}
(OUT/'environment.json').write_text(json.dumps(env, indent=2)+'\n')
patch = command('git', 'diff', '--binary')['output']
patch += command('git', 'diff', '--no-index', '--', '/dev/null', 'tests/test_touch_navigation.py')['output']
patch += command('git', 'diff', '--no-index', '--', '/dev/null', 'tools/collect_swipe_evidence.py')['output']
(OUT/'source.patch').write_text(patch)
changed = command('git', 'diff', '--name-only')['output'].splitlines()
changed += ['tests/test_touch_navigation.py', 'tools/collect_swipe_evidence.py']
with tarfile.open(OUT/'source-snapshot.tar.gz', 'w:gz') as archive:
    for name in changed:
        archive.add(ROOT/name, arcname=name)
(OUT/'fixtures').mkdir(exist_ok=True)
shutil.copy2(ROOT/'tests/test_touch_navigation.py', OUT/'fixtures/test_touch_navigation.py')
shutil.copy2(ROOT/'firmware/esp32/sdkconfig.esp32s3-touch-amoled-175c', OUT/'sdkconfig.esp32s3-touch-amoled-175c')
shutil.copy2(ROOT/'firmware/esp32/dependencies.lock', OUT/'dependencies.lock')
results = {}
for path in sorted(OUT.glob('*.xml')):
    # Trusted local pytest output only; never parse uploaded or remote XML here.
    tree = ET.parse(path)
    cases = tree.findall('.//testcase')
    results[path.name] = {
        'cases': len(cases),
        'passed': sum(c.find('failure') is None and c.find('error') is None and c.find('skipped') is None for c in cases),
        'failed': sum(c.find('failure') is not None or c.find('error') is not None for c in cases),
        'skipped': sum(c.find('skipped') is not None for c in cases),
        'touch_cases': [c.attrib['name'] for c in cases if 'test_touch_navigation' in c.attrib.get('classname', '')],
    }
(OUT/'results-index.json').write_text(json.dumps(results, indent=2)+'\n')
hashes = {str(p.relative_to(ROOT)): digest(p) for p in sorted(OUT.rglob('*'))
          if p.is_file() and p.name not in ('artifact-hashes.json', 'collection.log')}
hashes['build/host/libhgsim.so'] = digest(ROOT/'build/host/libhgsim.so')
(OUT/'artifact-hashes.json').write_text(json.dumps(hashes, indent=2)+'\n')
manifest = json.loads((OUT/'firmware/manifest.json').read_text())
assert len(manifest['builds']) == 1
build = manifest['builds'][0]
assert build['board'] == 'esp32s3-touch-amoled-175c' and build['flash_size'] == '32MB'
for kind in ('image', 'app'):
    item = build[kind]
    p = OUT/'firmware'/item['path']
    assert p.stat().st_size == item['size'] and digest(p) == item['sha256']
print(json.dumps({'environment': str(OUT/'environment.json'), 'results': results,
                  'firmware': build, 'changed_paths': changed}, indent=2))
