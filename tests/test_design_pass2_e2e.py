"""Second design pass: real native core and production loopback hub; no UI mocks."""
import numpy as np
from conftest import requires_sim
from test_interaction_surface_e2e import ix, ix_run, framebuffer, TEXT, DIM, SURFACE, REQUESTS
from test_design_pass_e2e import finish, to_recent
from test_touch_navigation import swipe, tap, ui
from test_face_first_font import rgb
pytestmark = requires_sim


def raw_controls(s):
    s.touch(True, 233, 220)
    s.touch(True, 233, 320)
    s.touch(False)


def test_transition_moves_then_matches_static_exactly(ix):
    r, s = ix, ix.s
    flushes = []
    original = s.display_flush
    def flush(y0,y1):
        flushes.append((y0,y1)); original(y0,y1)
    s.display_flush = flush
    raw_controls(s)
    a = framebuffer(s).copy()
    s.run_for(.08)
    b = framebuffer(s).copy()
    assert not np.array_equal(a, b), 'view change is a hard cut'
    s.run_for(.3)
    final = framebuffer(s).copy()
    assert not np.array_equal(b, final)
    assert flushes and all(0 <= lo < hi <= 466 and hi-lo < 466 for lo,hi in flushes), flushes
    # Force static redraw with unchanged settings through production console.
    s.console('set volume 71'); s.step()
    s.console('set volume 70'); s.step()
    assert np.array_equal(final, framebuffer(s)), 'transition final differs from static'
    s.take_dirty_rows(); s.run_for(.3)
    assert s.take_dirty_rows() is None


def test_input_snaps_to_destination_and_stale_contact_cannot_act(ix):
    r, s = ix, ix.s
    raw_controls(s)
    assert ui(s)['view'] == 'controls'
    rect = ui(s)['controls']['recent']; x,y,w,h = rect
    s.touch(True,x+w//2,y+h//2)
    assert not ui(s)['transition']['active']
    m = r.mark()
    r.send('prompt', id='priority', title='Permission', text='Allow?')
    s.touch(False); s.run_for(.7)
    assert ui(s)['view'] == 'approval'
    assert not (r.sent_types(m) & REQUESTS)


def test_recording_and_approval_preempt_motion(ix):
    r,s = ix,ix.s
    raw_controls(s)
    s.press('talk'); s.step()
    assert ui(s)['view'] == 'recording'
    assert not ui(s)['transition']['active']
    assert r.headline('Listening')
    s.tap('cancel'); s.release('talk'); s.step()
    swipe(s,dx=100); raw_controls(s)
    r.send('prompt',id='q',title='Permission',text='Allow?')
    assert not ui(s)['transition']['active']
    assert r.shows('Allow?',24,TEXT)


def test_mid_motion_tap_uses_destination_without_side_effects(ix):
    r,s=ix,ix.s
    raw_controls(s)
    x,y,w,h=ui(s)['controls']['recent']
    m=r.mark()
    s.touch(True,x+w//2,y+h//2)
    assert not ui(s)['transition']['active']
    s.touch(False); s.step(); s.run_for(.3)
    assert ui(s)['view']=='recent'
    assert r.shows('No recent work',18,TEXT)
    assert not (r.sent_types(m)&REQUESTS)


def test_thinking_with_idle_timeout_does_not_cancel_motion(ix):
    r,s=ix,ix.s
    s.console('set screen_timeout 30')
    r.turn_start('busy')
    raw_controls(s)
    assert ui(s)['transition']['active']
    s.run_for(.06)
    assert ui(s)['transition']['active'], 'routine keep-awake snapped motion'
    s.run_for(.25)
    assert not ui(s)['transition']['active']
    assert ui(s)['view']=='controls'
    assert s.status()['work']['active']


def test_speech_start_preempts_motion(ix):
    r,s=ix,ix.s
    raw_controls(s)
    r.send('audio.start',stream=92,rate=16000,format='pcm16')
    assert ui(s)['speaking']
    assert not ui(s)['transition']['active']
    assert r.shows('Mute voice',18,TEXT,SURFACE,tuple(ui(s)['controls']['silence']))


def test_offline_is_geist_and_recovery_settings_work(ix):
    r,s=ix,ix.s
    s.set_network(False); assert s.wait_screen('offline')
    assert r.shows('No network',30,TEXT)
    assert r.shows('Hold title for Settings',18,DIM)
    s.touch(True,233,62); s.run_for(1.3); s.touch(False); s.step()
    assert s.device.screen()=='settings'


def test_outcome_is_status_not_a_hit_target(ix):
    r,s=ix,ix.s
    finish(r,'one','Lamp is on.')
    swipe(s,dx=100); swipe(s,dy=100); s.run_for(.3)
    assert 'stop' not in ui(s)['controls']
    # Pass 3: the outcome is a status line of its own; the Stop slot only ever holds Stop.
    assert r.shows('Last task: Finished',18,DIM,0,(0,282,466,32))
    assert not r.shows('Finished',18,DIM,0,(238,329,160,60))
    m=r.mark(); tap(s,233,292); tap(s,316,342)
    assert not (r.sent_types(m)&REQUESTS)


def test_result_has_stage_header_above_body(ix):
    r,s=ix,ix.s
    finish(r,'failed','Lamp is on. Calendar did not answer.','failure')
    to_recent(r); tap(s,*r.control('work0')); s.run_for(.3)
    assert r.shows('Failed',18,rgb(226,124,112),0,(78,90,310,45))
    assert not r.shows('Failed',14,DIM,0,(0,400,466,66))


def test_glance_keeps_time_token_together(ix):
    r,s=ix,ix.s
    finish(r,'time','Reminder saved for Friday 9 am: compost delivery.')
    to_recent(r); s.run_for(.3)
    assert r.shows('9 am:',18,TEXT,SURFACE,tuple(ui(s)['controls']['work0']))
