"""Additional native E2E checks for the AMOLED cached animation path."""
import time
import struct
from test_round_amoled import capture, safe_circle
from test_touch_navigation import rig, ui, swipe, tap, LONG


def test_real_sample_level_and_silent_meter(rig):
    s = rig
    s.press('talk')
    assert s.wait_screen('listening')
    def feed(value):
        # Explicit PCM fixtures through the SAME App::on_mic_samples entry point.
        # Avoid Simulator.step here: its automatic microphone would replace these.
        time.sleep(.12)
        s.device.mic_samples(struct.pack('<h',value)*320)
        s.device.tick()
        return s.device.framebuffer_rows(55,65)
    silent = feed(0)
    assert feed(0) == silent, 'silence must not generate fake amplitude'
    loud = feed(12000)
    assert loud != silent
    px = capture(s,'listening-fixture-level')
    safe_circle(px)
    assert feed(0) == silent, 'meter must clear when real samples return to zero'
    s.tap('cancel')


def test_wake_consumes_contact_and_title_still_opens_settings(rig):
    s = rig
    s.console('set screen_timeout 1')
    assert s.wait_for(lambda:s.status()['display_sleeping'],timeout=4)
    before = len(s.sent)
    s.touch(True,233,220)
    s.run_for(.3)
    s.touch(False)
    s.step()
    assert not s.status()['display_sleeping']
    assert not any(m['type']=='audio.start' for m in s.sent[before:])
    s.console('set screen_timeout 0')
    # Press the visible HERMES label, not an obsolete invisible title region.
    s.touch(True,233,78)
    s.run_for(1.1)
    s.touch(False)
    s.step()
    assert s.device.screen() == 'settings'
    assert ui(s)['view'] == 'other'
    capture(s,'legacy-settings')


def test_long_text_and_overlay_clear_perimeter(rig):
    s = rig
    s.send_fixture('turn.start',turn='long')
    s.send_fixture('reply.delta',text=LONG)
    for _ in range(4):
        safe_circle(capture(s,'long-response'))
        swipe(s,dy=100)
    s.send_fixture('prompt',id='long-approval',title='Permission',text=LONG)
    s.run_for(.6)
    for _ in range(4):
        safe_circle(capture(s,'long-approval'))
        swipe(s,dy=-100)
    assert not any(m['type']=='prompt.reply' for m in s.sent)
