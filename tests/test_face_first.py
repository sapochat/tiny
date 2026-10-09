"""Approved face-first requirements on a real loopback hub/native framebuffer.
Run with FACE_ARTIFACTS pointing at a unique evidence directory.
"""
import os
from pathlib import Path
import pytest
from test_touch_navigation import rig, ui, swipe, tap, control
from test_round_amoled import safe_circle

OUT = Path(os.environ.get('FACE_ARTIFACTS', 'artifacts/face-first/green'))

def capture(s, name):
    import hashlib, json, struct
    OUT.mkdir(parents=True, exist_ok=True)
    s.screenshot(OUT / (name+'.png'))
    raw = s.device.framebuffer_rows()
    (OUT / (name+'.json')).write_text(json.dumps({'status':s.status(), 'sent':s.sent,
        'received':s.received, 'sha256':hashlib.sha256(raw).hexdigest()},indent=2))
    safe_circle(struct.unpack('<'+'H'*(len(raw)//2),raw))
    return s.rgb888()

@pytest.mark.parametrize('state',['idle','reply','controls','approval'])
def test_approved_face_first(rig,state):
    s=rig
    if state=='reply':
        s.send_fixture('turn.start',turn='face')
        s.send_fixture('reply.delta',text='The afternoon is clear.\nA good window for a walk before dinner.\nBring a light layer—it may cool down later.')
        capture(s,'reading')
        swipe(s,dx=100)
        s.send_fixture('reply',text='The afternoon is clear.\nA good window for a walk before dinner.\nBring a light layer—it may cool down later.\nConfirmed.')
        s.send_fixture('turn.end',turn='face',outcome='success')
        capture(s,'reply-ready')
        assert ui(s)['controls']['reply']==[128,356,210,55]
        tap(s,*control(s,'reply'))
        assert ui(s)['view']=='response'
    elif state=='controls':
        swipe(s,dy=100)
        capture(s,'controls')
        assert ui(s)['controls']['volume']==[122,130,72,158]   # pass 6: no status row, taller sliders
        assert ui(s)['controls']['brightness']==[272,130,72,158]
    elif state=='approval':
        s.send_fixture('prompt',id='face-question',title='Permission requested',text='Turn on the desk lamp?')
        s.run_for(.6)
        pixels=capture(s,'approval')
        assert not any(pixels[(y*466+x)*3:(y*466+x)*3+3]!=b'\0\0\0' for y in range(10,50) for x in range(180,280)), 'No decorative approval portrait'
        # Superseded geometry (interaction v1): equal-emphasis Yes/No enlarged from 146x64
        # to 150x96 below the same five question rows; explicit-tap semantics unchanged.
        assert ui(s)['controls']['yes']==[238,296,150,96]
        assert ui(s)['controls']['no']==[78,296,150,96]
        tap(s,*control(s,'yes'))
        assert any(m['type']=='prompt.reply' and m['answer']=='yes' for m in s.sent)
    else:
        pixels=capture(s,'idle')
        assert ui(s)['headline']=='Hold to talk'
        # Smooth Geist has intermediate coverage shades, unlike scaled 5x7.
        colors={pixels[(y*466+x)*3:(y*466+x)*3+3] for y in range(299,336) for x in range(70,396)}
        assert len(colors)>8


def test_proportional_long_question_reaches_exact_tail(rig):
    """Approval paging must use glyph widths, not obsolete 17-character cells."""
    s=rig
    # Each wide line wraps to two rows, narrow lines remain one. Unsupported
    # scalar is retained as a visible fallback alongside supported punctuation.
    lines=['W'*20, 'i'*20, 'Café — “yes” ↑ 🦉']*8+['FINAL QUESTION']
    s.send_fixture('prompt',id='long-font',title='Question',text='\n'.join(lines))
    s.run_for(.6)
    capture(s,'long-approval-start')
    for _ in range(30): swipe(s,dy=-100)
    # Widths measured independently from source TTF, integer glyph advances.
    from PIL import ImageFont
    f=ImageFont.truetype(str(Path(__file__).resolve().parents[1]/'assets/fonts/Geist-Regular.ttf'),24)
    wide=sum(round(f.getlength(c)) for c in 'W'*20)
    assert 303<wide<606
    assert sum(round(f.getlength(c)) for c in 'i'*20)<303
    assert ui(s)['scroll']==28  # 8*(2+1+1)+1 total rows, five visible
    capture(s,'long-approval-end')
    assert not any(m['type']=='prompt.reply' for m in s.sent)
    tap(s,*control(s,'no'))
    assert any(m['type']=='prompt.reply' and m['answer']=='no' for m in s.sent)


def test_controls_stop_disabled_and_final_snapshot_still_active(rig):
    s=rig
    swipe(s,dy=100)
    before=len(s.sent)
    disabled=capture(s,'controls-disabled')
    tap(s,*control(s,'stop'))
    assert not any(m['type']=='cancel' for m in s.sent[before:])
    s.send_fixture('turn.start',turn='stop-final')
    s.send_fixture('reply',text='Final snapshot does not finish a turn.')
    active=capture(s,'controls-active')
    assert active!=disabled
    tap(s,*control(s,'stop'))
    assert any(m['type']=='cancel' for m in s.sent[before:])


def test_tap_mode_and_no_reply_speaking_cue(rig):
    s=rig
    s.console('set talk_mode tap')
    capture(s,'tap-idle')
    assert ui(s)['headline']=='Tap to talk'
    s.send_fixture('turn.start',turn='audio-only')
    s.send_fixture('audio.start',stream=91,rate=16000,format='pcm16')
    capture(s,'speaking-no-text')
    # Superseded check (interaction v1): rows 400-430 now hold the Silence / Stop work
    # targets, so "no reply cue without a reply" is asserted semantically instead:
    # no Read reply target and neither old nor new Read reply label anywhere on screen.
    from test_interaction_surface_e2e import find_text
    from test_face_first_font import rgb
    assert 'reply' not in ui(s)['controls'] and {'silence','stop'} <= set(ui(s)['controls'])
    assert find_text(s,'↑  Read reply',14,rgb(164,164,169)) is None
    assert find_text(s,'Read reply  ↑',18,rgb(240,239,235),rgb(32,32,35)) is None
