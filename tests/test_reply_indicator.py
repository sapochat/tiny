"""Provider-free reply indicator workflows; reuses production hub/native rig."""
from test_touch_navigation import rig, swipe, tap, ui, control


def begin(s):
    s.send_fixture('turn.start', turn='indicator')
    swipe(s, dy=100)
    swipe(s, dx=100)  # explicit Home, retain that choice as text arrives


def finish(s, outcome='success'):
    s.send_fixture('reply', text='A quiet completed answer')
    s.send_fixture('turn.end', turn='indicator', outcome=outcome)


def test_unread_completion_is_quiet_and_tappable(rig):
    s = rig
    begin(s)
    before = len(s.sent)
    s.send_fixture('reply.delta', text='A quiet')
    assert ui(s)['view'] == 'home'
    assert ui(s)['hint'] == 'New text - tap to read'
    streaming = s.rgb888(299, 336)
    finish(s)
    assert ui(s)['view'] == 'home'
    assert ui(s)['hint'] == 'Reply ready - tap to read'
    assert s.rgb888(299, 336) != streaming
    x,y = control(s, 'reply')
    assert (x-233)**2 + (y-233)**2 < 228**2  # physical circle, not obsolete square
    s.touch(True,x,y)
    s.run_for(.2)  # indicator does not become hold-to-talk
    s.touch(False)
    s.step()
    assert ui(s)['view'] == 'response'
    swipe(s, dx=100)
    assert 'reply' not in ui(s)['controls']
    assert not any(m['type'] in ('audio.start','cancel','session.new') for m in s.sent[before:])
    assert not ui(s)['speaking']


def test_final_is_not_success_and_errors_are_not_ready(rig):
    s = rig
    begin(s)
    s.send_fixture('reply', text='Partial result')
    assert ui(s)['hint'] == 'New text - tap to read'
    s.send_fixture('turn.end', turn='indicator', outcome='failure')
    assert ui(s)['hint'] == 'Reply stopped - tap to read'
    control(s, 'reply')


def test_completion_preserves_controls_and_approval(rig):
    s = rig
    begin(s)
    swipe(s, dy=100)
    finish(s)
    assert ui(s)['view'] == 'controls'
    assert 'reply' not in ui(s)['controls']
    s.send_fixture('prompt', id='safe', text='Explicit approval only')
    s.send_fixture('turn.end', turn='indicator', outcome='success')
    assert ui(s)['view'] == 'approval'
    assert 'reply' not in ui(s)['controls']
    assert not any(m['type'] == 'prompt.reply' for m in s.sent)


def test_stale_reply_contact_does_not_open_changed_text(rig):
    s = rig
    begin(s)
    finish(s)
    x,y = control(s, 'reply')
    s.touch(True,x,y)
    s.send_fixture('reply', text='Replacement answer')
    s.touch(False)
    s.step()
    assert ui(s)['view'] == 'home'
    tap(s,x,y)
    assert ui(s)['view'] == 'response'


def test_no_text_turn_cannot_complete_retained_previous_reply(rig):
    s = rig
    begin(s)
    finish(s)
    s.send_fixture('turn.start', turn='empty')
    s.send_fixture('turn.end', turn='empty', outcome='success')
    assert ui(s)['hint'] != 'Reply ready - tap to read'
    assert ui(s)['view'] == 'home'


def test_completion_during_recording_does_not_cover_or_release(rig):
    s = rig
    begin(s)
    s.press('talk')
    finish(s)
    assert ui(s)['view'] == 'recording'
    assert 'reply' not in ui(s)['controls']
    assert not any(m['type'] in ('audio.end', 'audio.cancel') for m in s.sent)
    s.tap('cancel')


def test_viewed_reply_completion_is_not_unread(rig):
    s = rig
    begin(s)
    s.send_fixture('reply.delta', text='Visible answer')
    swipe(s, dy=-100)
    finish(s)
    swipe(s, dx=100)
    assert 'reply' not in ui(s)['controls']
