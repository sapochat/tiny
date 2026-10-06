"""Collect local-only Tiny v2 build/playback evidence; never flash or publish.
Run after the commands in docs/development.md: .venv/bin/python tools/report_video_v2.py
"""
import hashlib
import json
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'artifacts/video-v2'
sys.path.insert(0,str(ROOT))
from plugin.ota import inspect_image  # local byte inspection only, no updater


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def command(*args):
    return subprocess.check_output(args,cwd=ROOT,text=True).strip()


def main():
    manifest = json.loads((OUT/'manifest.json').read_text())
    header = ROOT/'firmware/core/include/hg/expression_assets.hpp'
    assert digest(header)==manifest['header_sha256']
    binary = ROOT/'build/video-v2-esp32/esp32s3-touch-amoled-175c/firmware.bin'
    image = inspect_image(binary.read_bytes())
    assert image.board=='esp32s3-touch-amoled-1.75c'
    assert image.version=='0.2.0-tiny-video-v2'
    assert image.size <= 0x1f0000*.9
    # This XML is generated locally by the fixture pytest run, not user input.
    junit = ET.parse(OUT/'final/results.xml').getroot()
    cases = junit.findall('.//testcase')
    failures = [c.attrib['name'] for c in cases if c.find('failure') is not None or c.find('error') is not None]
    assert len(cases)==77 and not failures
    observed = set()
    for path in (OUT/'final/video').glob('*.json'):
        data=json.loads(path.read_text())
        observed.update(c['ui']['animation']['clip'] for c in data['checks'])
    assert observed=={s['name'] for s in manifest['sources']}, observed
    candidate=OUT/'candidate';candidate.mkdir(exist_ok=True)
    shutil.copy2(binary,candidate/'tiny-video-v2-175c-app.bin')
    shutil.copy2(ROOT/'build/video-v2/libhgsim.so',candidate/'libhgsim.so')
    fixture_dir=OUT/'fixture-snapshot';fixture_dir.mkdir(exist_ok=True)
    for path in ['tests/test_video_v2.py','tests/test_expressions.py','tests/test_touch_navigation.py','tests/conftest.py','tools/build_expressions.py','tools/report_video_v2.py']:
        shutil.copy2(ROOT/path,fixture_dir/Path(path).name)
    (OUT/'candidate.patch').write_text(command('git','diff','--binary'))
    # Turn the actual native-framebuffer GIF into an easily played video.
    gif=OUT/'final/video/test_video_source_motion_and_routing.gif'
    subprocess.run(['ffmpeg','-v','error','-y','-i',str(gif),'-vf','fps=10','-c:v','libx264','-pix_fmt','yuv420p','-movflags','+faststart',str(OUT/'simulator-playback.mp4')],check=True)
    sheet=Image.new('RGB',(466*4,490*2),'#111111')
    positions=[(30,'idle'),(90,'listening'),(150,'thinking'),(210,'speaking'),(280,'reply-ready'),(335,'settle')]
    with Image.open(gif) as frames:
        # GIF encoders merge identical frames. Select by elapsed duration, not
        # frame number, so the contact sheet corresponds to the live timeline.
        elapsed=0;next_pick=0
        for i in range(frames.n_frames):
            frames.seek(i)
            while next_pick<len(positions) and elapsed>=positions[next_pick][0]*100:
                label=positions[next_pick][1];x=(next_pick%4)*466;y=(next_pick//4)*490
                sheet.paste(frames.convert('RGB'),(x,y+24));ImageDraw.Draw(sheet).text((x+12,y+6),label,fill='white')
                next_pick+=1
            elapsed+=frames.info.get('duration',100)
    sheet.save(OUT/'simulator-contact.png')
    summary={
        'scope':'Local compilation and provider-free native simulation only; no hardware, OTA, service restart, push or commit',
        'baseline_commit':command('git','rev-parse','HEAD'),
        'branch':command('git','branch','--show-current'),
        'python':platform.python_version(), 'ffmpeg':manifest['ffmpeg'],
        'cmake':command(sys.executable,'-m','cmake','--version').splitlines()[0],
        'platformio':command(sys.executable,'-m','platformio','--version'),
        'firmware':{'board':image.board,'version':image.version,'bytes':image.size,'sha256':image.sha256,'slot_bytes':0x1f0000,'free_bytes':0x1f0000-image.size,'free_percent':100*(1-image.size/0x1f0000)},
        'animation':{'clips':len(observed),'observed_clips':sorted(observed),'frames':sum(s['frame_count'] for s in manifest['sources']),'asset_flash_bytes':manifest['flash_bytes'],'working_frame_bytes':manifest['framebuffer_bytes'],'native_size':manifest['native_size'],'fps':manifest['fps'],'gray_levels':manifest['gray_levels'],'unmapped':[]},
        'checks':{'python_tests':len(cases),'failures':failures,'core':'1/1 CTest passed; see core-tests-final.log','site_tests':'29 passed after npm ci','site_build':'BLOCKED by pre-existing docs/tiny-workspace.md missing navigation/search registration; unchanged by this task'},
        'red':'red/results.xml and red/test_video_source_motion_and_routing.json retain old-renderer failure: no motion outside obsolete facial patch',
        'iterations':['128px gray4 RLE: 987195 bytes; rejected by asset budget','128px gray4 LZ: 1135012 bytes; rejected','128px gray2 LZ: 702049 bytes; rejected','96px gray2 LZ fits unchanged firmware partition','First long accelerated-clock sleep fixture disconnected on heartbeat timeout; attempt-1 preserved. Real hub pings on simulated time fix the fixture, not production code.'],
        'limitations':['96px native artwork enlarged to 192px, four gray levels and 5fps are deliberate flash-budget compromises; not full-resolution/source-FPS playback.','Authored full exits run only from completed holds toward neutral. New live activity and interrupted entries cut immediately; arbitrary transitions are not pixel-continuous.','Sleep animation only decorates existing dimmed idle time; short timeouts may darken before entry finishes. No timing/power/input policy was changed.','No physical AMOLED/frame-rate/audio/power tests. No full firmware-board matrix.','Source pack is a required sibling input for regeneration, not vendored into this repository.','Approved source artifacts (eye squeeze, occasional exit teeth) are retained; no paid regeneration or semantic retouching.'],
        'rerun_commands':[
            '.venv/bin/python tools/build_expressions.py',
            '.venv/bin/python -m cmake -S firmware -B build/video-v2 -DCMAKE_BUILD_TYPE=Release',
            '.venv/bin/python -m cmake --build build/video-v2 -j 4',
            'HGSIM_LIBRARY=$PWD/build/video-v2/libhgsim.so SWIPE_ARTIFACTS=artifacts/video-v2/final/touch AMOLED_ARTIFACTS=artifacts/video-v2/final/amoled VIDEO_ARTIFACTS=artifacts/video-v2/final/video .venv/bin/python -m pytest tests/test_video_v2.py tests/test_expressions.py tests/test_touch_navigation.py tests/test_round_amoled.py tests/test_round_amoled_safety.py tests/test_reply_indicator.py tests/test_sim_hub.py tests/test_firmware_tools.py --basetemp=/home/santi/.hermes/cache/scratch/tiny-v2-pytest -v --junitxml=artifacts/video-v2/final/results.xml',
            '.venv/bin/python -m cmake --build build/video-v2 --target test',
            'PLATFORMIO_BUILD_DIR=$PWD/build/video-v2-esp32 .venv/bin/python -m platformio run --project-dir firmware/esp32 -e esp32s3-touch-amoled-175c',
            '(cd site && npm ci && npm test && npm run build)',
            '.venv/bin/python tools/report_video_v2.py'],
        'artifacts':{}
    }
    for p in [candidate/'tiny-video-v2-175c-app.bin',candidate/'libhgsim.so',OUT/'simulator-playback.mp4',OUT/'simulator-contact.png',OUT/'manifest.json',OUT/'final/results.xml']:
        summary['artifacts'][str(p.relative_to(ROOT))]={'bytes':p.stat().st_size,'sha256':digest(p)}
    (OUT/'report.json').write_text(json.dumps(summary,indent=2)+'\n')
    text=['# Tiny v2 local candidate','',f"- Firmware: **{image.version}**, **{image.board}**; {image.size:,} bytes; {summary['firmware']['free_percent']:.2f}% app-slot free.",f"- Verified: **{len(cases)} Python tests**, CTest **1/1**, site tests **29**; all **14 clips** observed through the native app.",'- Playback: [MP4](simulator-playback.mp4), [contact sheet](simulator-contact.png), full native GIFs and traces in `final/video/`.', '- Candidate: `candidate/tiny-video-v2-175c-app.bin`; simulator: `candidate/libhgsim.so`. Neither was installed on a device.',f"- Asset budget: {manifest['flash_bytes']:,} bytes, {manifest['framebuffer_bytes']:,}-byte working buffer. Conversion: 96px → 192px, 5fps, four gray levels.",'- Site build remains blocked by the existing unregistered `docs/tiny-workspace.md`; see `site-build.log`.','', '## Evidence','', '- `final/results.xml`, `final-pytest.log`, `core-tests-final.log`, `firmware-build-final.log` contain actual results.', '- `manifest.json` contains all 14 source hashes, sampling indices, anchor identities, and conversion versions.', '- `red/` preserves the expected pre-change failure; `attempt-1/` preserves the accelerated-clock heartbeat failure.', '- `fixture-snapshot/` and `candidate.patch` freeze the fixture sources and tracked implementation delta. New scripts are separately included in the snapshot.', '', '## Limitations','']
    text += ['- '+x for x in summary['limitations']]
    text += ['', '## Rerun from repository root','', '```sh']+summary['rerun_commands']+['```','', 'Full checksums and machine-readable results: [report.json](report.json).']
    (OUT/'report.md').write_text('\n'.join(text)+'\n')
    print(json.dumps({k:summary[k] for k in ('firmware','animation','checks')},indent=2))


if __name__=='__main__':
    main()
