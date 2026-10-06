"""Production hub/native expression acceptance, deterministic app clock, no providers."""
import hashlib
import json
from pathlib import Path
import numpy as np
from PIL import Image
from test_touch_navigation import rig, swipe, ui

OUT = Path('artifacts/expressions')

def freeze(s):
    t = [s.now_ms()]
    s.now_ms = lambda: t[0]
    def advance(n=1):
        for _ in range(n):
            t[0] += 100
            s.device.tick()
    return advance

def face(s):
    return np.frombuffer(s.rgb888(),dtype=np.uint8).reshape(466,466,3)[112:304,137:329].copy()

def test_expression_hub_workflow_and_static_outline(rig):
    """Historical name retained; v2 explicitly supersedes the frozen outline.

    State/read semantics survive. Video now owns every mascot pixel; entries
    are authored motion, not the old eight-tick bounded facial crossfade.
    """
    from test_video_v2 import freeze
    s=rig; advance=freeze(s)
    captures=[]
    def settle():
        frames=[]
        for _ in range(55):
            advance()
            f=face(s); frames.append(f)
            captures.append(Image.frombytes('RGB',(466,466),s.rgb888()))
        assert len({f.tobytes() for f in frames}) > 8, 'approved entry/loop needs actual motion'
        return frames[-1]
    base=settle()
    s.press('talk'); listening=settle()
    assert not np.array_equal(listening,base)
    s.tap('cancel')
    s.send_fixture('turn.start',turn='expression')
    thinking=settle()
    assert not np.array_equal(thinking,listening)
    swipe(s,dy=100); swipe(s,dx=100)
    s.send_fixture('reply.delta',text='Expression fixture answer')
    s.send_fixture('audio.start',stream=9,rate=16000,format='pcm16')
    settle()
    s.send_fixture('audio.end',stream=9)
    s.send_fixture('reply',text='Expression fixture complete')
    s.send_fixture('turn.end',turn='expression',outcome='success')
    ready=settle()
    assert ui(s)['hint']=='Reply ready - tap to read'
    assert not np.array_equal(ready,thinking)
    # Hidden controls do not reset a completed hold or consume unread status.
    retained=face(s); swipe(s,dy=100); advance(3); swipe(s,dx=100)
    assert np.array_equal(retained,face(s))
    out=Path('artifacts/video-v2/expression-regressions');out.mkdir(parents=True,exist_ok=True)
    captures[0].save(out/'native-transitions.gif',save_all=True,append_images=captures[1:],duration=100,loop=0)
    (out/'workflow.json').write_text(json.dumps({'superseded':'static original contour; <=40 channel step; identical boundary pose', 'fixture':'production DeviceHub + NativeDevice; deterministic 100ms clock with hub pings','sent':s.sent,'received':s.received,'rerun':'HGSIM_LIBRARY=$PWD/build/video-v2/libhgsim.so .venv/bin/python -m pytest tests/test_expressions.py -v'},indent=2))

def test_failure_does_not_choose_ready_expression(rig):
    s=rig; advance=freeze(s);advance(10)
    s.send_fixture('turn.start',turn='failed');swipe(s,dy=100);swipe(s,dx=100)
    s.send_fixture('reply',text='Partial answer')
    s.send_fixture('turn.end',turn='failed',outcome='failure');advance(10)
    failed=face(s)
    s.send_fixture('turn.start',turn='success')
    s.send_fixture('reply',text='Complete answer')
    s.send_fixture('turn.end',turn='success',outcome='success');advance(10)
    assert not np.array_equal(failed,face(s)), 'success-only ready mouth must differ from failure'
