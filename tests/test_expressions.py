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
    s=rig; advance=freeze(s); advance(10)
    base=face(s)
    # Strict approved support: eyes/brows and mouth only; hair/jaw never animate.
    support=np.zeros((192,192),bool)
    support[72:105,34:94]=True
    support[111:130,41:64]=True
    captures=[]; deltas=[]; boundary=[]
    def capture():
        captures.append(Image.frombytes('RGB',(466,466),s.rgb888()))
    def event(fn):
        before=face(s); fn(); after=face(s)
        boundary.append(int(np.count_nonzero(before!=after)))
        assert np.array_equal(before,after), 'state entry must preserve exact rendered face'
    def settle():
        before=face(s)
        for _ in range(10):
            advance(); after=face(s); capture()
            assert np.array_equal(after[~support],base[~support]), 'static original contour/palette moved'
            delta=int(np.abs(after.astype(int)-before.astype(int)).max())
            deltas.append(delta)
            assert delta<=40, '100ms channel step must be <=40/255, not binary popping'
            before=after
        return before
    capture()
    event(lambda:s.press('talk')); listening=settle()
    assert not np.array_equal(listening,base), 'listening needs receptive eyes, not unchanged idle'
    event(lambda:s.tap('cancel'))
    advance(2)
    event(lambda:s.send_fixture('turn.start',turn='expression'))
    thinking=settle()
    assert not np.array_equal(thinking,listening)
    # Choose Home before text arrives; preserve activity and source semantics.
    swipe(s,dy=100); swipe(s,dx=100)
    s.send_fixture('reply.delta',text='Expression fixture answer')
    event(lambda:s.send_fixture('audio.start',stream=9,rate=16000,format='pcm16'))
    settle()
    event(lambda:s.send_fixture('audio.end',stream=9))
    s.send_fixture('reply',text='Expression fixture complete')
    event(lambda:s.send_fixture('turn.end',turn='expression',outcome='success'))
    ready=settle()
    assert ui(s)['hint']=='Reply ready - tap to read'
    assert not np.array_equal(ready,thinking)
    # Navigation hides face but cannot reset its pose or revive old dirty pixels.
    retained=face(s); swipe(s,dy=100); advance(3); swipe(s,dx=100)
    assert np.array_equal(retained,face(s))
    OUT.mkdir(parents=True,exist_ok=True)
    captures[0].save(OUT/'native-transitions.gif',save_all=True,append_images=captures[1:],duration=100,loop=0)
    sheet=Image.new('RGB',(466*5,466))
    for i,im in enumerate([captures[0],captures[10],captures[20],captures[30],captures[-1]]):sheet.paste(im,(466*i,0))
    sheet.save(OUT/'native-contact.png')
    (OUT/'continuity.json').write_text(json.dumps({'boundary_changed_channels':boundary,'max_channel_step_100ms':max(deltas),'outside_support_changed_channels':0,'fixture':'production DeviceHub + NativeDevice; deterministic 100ms clock','sent':s.sent,'received':s.received},indent=2))

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
