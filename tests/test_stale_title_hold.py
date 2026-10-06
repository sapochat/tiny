"""NativeDevice / real loopback DeviceHub regressions for review B1.

Run with the same HGSIM_LIBRARY and SWIPE_ARTIFACTS as touch_navigation.
The imported rig records protocol receipts, framebuffer and final native status.
All inputs are explicit local fixtures; no providers or physical hardware.
"""
import pytest
from test_touch_navigation import rig, ui


def test_stale_title_hold_cannot_cancel_native_recording(rig):
    s = rig
    s.touch(True, 233, 65)
    s.press('talk')
    s.step()
    assert ui(s)['activity'] == 'recording'
    assert any(m['type'] == 'audio.start' for m in s.sent)
    s.run_for(1.2)  # Cato's exact held-contact interleaving
    assert ui(s)['activity'] == 'recording', s.status()
    assert not any(m['type'] == 'audio.cancel' for m in s.sent)
    s.touch(False)
    assert ui(s)['activity'] == 'recording'
    assert not any(m['type'] in ('audio.end', 'audio.cancel') for m in s.sent)
    s.release('talk')  # only the real recording owner submits
    assert any(m['type'] == 'audio.end' for m in s.sent)
    assert not any(m['type'] == 'audio.cancel' for m in s.sent)


@pytest.mark.parametrize('activity', ['thinking', 'speaking'])
def test_stale_title_hold_cannot_interrupt_new_activity(rig, activity):
    s = rig
    s.touch(True, 233, 65)
    if activity == 'thinking':
        s.send_fixture('turn.start', turn='stale-title-thinking')
    else:
        # Audio can arrive without a turn.start epoch change (e.g. speak tool).
        s.send_fixture('audio.start', stream=7, rate=16000, format='pcm16')
    assert ui(s)['activity'] == activity
    s.run_for(1.2)
    s.touch(False)
    assert ui(s)['activity'] == activity
    assert s.device.screen() != 'settings'
    assert not any(m['type'] in ('cancel', 'audio.cancel', 'audio.start') for m in s.sent)
    if activity == 'speaking':
        assert ui(s)['speaking']


def test_stale_title_hold_does_not_revive_after_recording_cancel(rig):
    s = rig
    s.touch(True, 233, 65)
    s.press('talk')
    assert ui(s)['activity'] == 'recording'
    s.tap('cancel')  # explicit supported stop, not the stale contact
    s.release('talk')
    assert ui(s)['activity'] == 'idle'
    assert sum(m['type'] == 'audio.cancel' for m in s.sent) == 1
    s.run_for(1.2)
    s.touch(False)
    assert s.device.screen() != 'settings'
    assert sum(m['type'] == 'audio.cancel' for m in s.sent) == 1
    # A fresh idle title contact remains valid after invalidating the old one.
    s.touch(True, 233, 65)
    s.run_for(1.2)
    s.touch(False)
    assert s.device.screen() == 'settings'


def test_touch_owned_talk_still_submits_on_original_release(rig):
    s = rig
    s.touch(True, 233, 220)
    s.run_for(.3)
    assert ui(s)['activity'] == 'recording'
    s.touch(True, 233, 320)  # movement never cancels/submits
    s.run_for(1.2)
    assert ui(s)['activity'] == 'recording'
    assert not any(m['type'] in ('audio.end', 'audio.cancel') for m in s.sent)
    s.touch(False)
    assert sum(m['type'] == 'audio.start' for m in s.sent) == 1
    assert sum(m['type'] == 'audio.end' for m in s.sent) == 1
    assert not any(m['type'] == 'audio.cancel' for m in s.sent)
