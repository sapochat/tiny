"""T2-B1 PWR = Silence: real native core, production loopback hub.

On the AMOLED 1.75C the PWR key is wired to the AXP2101, which reports a short press as an
interrupt flag; the port turns that flag into ``Button::Silence`` (sim button 4). The key
quiets whatever is sounding. With nothing sounding it turns the screen off, or back on
(T2-C8; screen behaviour itself is in test_screen_rest_e2e.py). Long presses stay the
PMIC's own power-off and never reach the app, so they are not modelled here.

Failure modes covered:
- the device does not advertise the key, so Hermes cannot know it exists;
- PWR silences speech but also stops the work, sends a request, or navigates;
- PWR acts like Cancel: discards a recording, answers an approval with No, or stops work
  when nothing is sounding;
- PWR on a sleeping screen does more than wake it;
- a silenced turn resumes speaking on late audio (it must behave like Mute voice);
- a ringing timer keeps beeping, or PWR dismisses it outright instead of leaving the
  needs-you mark and the Dismiss target on Home.
"""
from __future__ import annotations

import pytest

from conftest import requires_sim
from test_interaction_surface_e2e import REQUESTS, home_with_text, ix, ix_run, tone  # noqa: F401
from test_timer_e2e import advance, ok, rig, settle, timer, tone_writes  # noqa: F401
from test_touch_navigation import ui

pytestmark = requires_sim

SILENCE_KEY = 4  # HGSIM_BUTTON_SILENCE


def pwr(s, run=0.2):
    """One short press of PWR, as the port reports it: a press and a release together."""
    s.device.button(SILENCE_KEY, True)
    s.device.button(SILENCE_KEY, False)
    s.step()
    if run:
        s.run_for(run)


def test_round_touch_board_advertises_the_silence_key(ix):
    inputs = ix.session.caps['inputs']
    assert 'silence' in inputs, inputs
    assert 'talk' in inputs and 'touch' in inputs, inputs


def test_pwr_quiets_speech_and_keeps_the_work(ix):
    r, s = ix, ix.s
    r.turn_start('turn-P')
    home_with_text(r, 'turn-P', 'Answer streaming while Hermes speaks')
    view = ui(s)['view']
    out = r.play(tone(3.0), turn='turn-P')
    assert r.wait(lambda: r.speaker_bytes() >= 3200 and ui(s)['speaking'])
    m = r.mark()
    pwr(s)
    r.snap('pwr-silenced')
    assert r.hal_since(m, 'speaker_abort'), 'PWR did not abort playback'
    assert not ui(s)['speaking']
    assert ui(s)['view'] == view, 'PWR is not navigation'
    assert ui(s)['activity'] == 'streaming', 'PWR must not end the work'
    assert not (r.sent_types(m) & REQUESTS), r.sent_since(m)
    assert r.brain.count('cancel') == 0
    assert r.wait(out.done.is_set, 8) and not out.aborted
    assert r.speaker_bytes(m) == 0, 'silenced frames reached the speaker'
    # Late audio for the same turn stays quiet, exactly as after Mute voice.
    begins = r.hal_count('speaker_begin')
    late = r.play(tone(0.6), turn='turn-P')
    assert r.wait(late.done.is_set, 6)
    s.run_for(0.2)
    assert r.hal_count('speaker_begin') == begins and not ui(s)['speaking']
    # A new turn speaks again.
    r.turn_end('turn-P', 'success')
    r.turn_start('turn-Q')
    mq = r.mark()
    nxt = r.play(tone(0.6, freq=660.0), turn='turn-Q')
    assert r.wait(lambda: r.speaker_bytes(mq) > 0), 'the next turn must play'
    assert r.wait(nxt.done.is_set, 6)


def test_pwr_with_nothing_sounding_turns_the_screen_off(ix):
    # Santi, 2026-11-07: with nothing to silence, PWR turns the screen off, like a phone.
    r, s = ix, ix.s
    r.turn_start('turn-W')
    r.delta('Working on it', turn='turn-W')
    s.run_for(0.3)
    before = ui(s)
    m = r.mark()
    pwr(s, 0.5)
    after = ui(s)
    assert s.status()['display']['sleeping'], 'PWR with nothing sounding must turn the screen off'
    assert after['view'] == before['view'] and after['activity'] == before['activity'] == 'streaming'
    assert not r.sent_since(m), r.sent_since(m)
    assert not r.hal_since(m, 'speaker_abort')


def test_pwr_in_the_dark_silences_speech_and_stays_dark(ix):
    r, s = ix, ix.s
    r.turn_start('turn-D')
    r.delta('Thinking about it', turn='turn-D')
    s.run_for(0.3)
    pwr(s)
    assert s.status()['display']['sleeping']
    out = r.play(tone(3.0), turn='turn-D')
    assert r.wait(lambda: r.speaker_bytes() >= 3200 and ui(s)['speaking'])
    assert s.status()['display']['sleeping'], "the same turn's speech woke the screen"
    m = r.mark()
    pwr(s)
    assert r.hal_since(m, 'speaker_abort'), 'PWR in the dark must still silence'
    assert not ui(s)['speaking']
    assert s.status()['display']['sleeping'], 'silencing must not wake the screen'
    assert r.wait(out.done.is_set, 8)


def test_pwr_never_discards_a_recording(ix):
    r, s = ix, ix.s
    m = r.mark()
    s.press('talk')
    s.run_for(0.4)
    assert ui(s)['activity'] == 'recording'
    pwr(s)
    assert ui(s)['activity'] == 'recording', 'PWR discarded the recording'
    assert not r.sent_since(m, 'audio.cancel') and not r.hal_since(m, 'mic_stop')
    s.release('talk')
    s.run_for(0.5)
    assert len(r.sent_since(m, 'audio.end')) == 1, 'the recording must still be sent'


def test_pwr_never_answers_an_approval(ix):
    r, s = ix, ix.s
    m = r.mark()
    r.send('prompt', id='p-pwr', title='Permission', text='Allow the desk lamp?')
    s.run_for(1.5)
    assert set(ui(s)['controls']) == {'yes', 'no'}
    pwr(s, 0.5)
    assert set(ui(s)['controls']) == {'yes', 'no'}, 'PWR closed the approval'
    assert not r.sent_since(m, 'prompt.reply') and r.brain.count('prompt_reply') == 0


def test_pwr_on_a_sleeping_screen_only_wakes(ix):
    r, s = ix, ix.s
    s.console('set screen_timeout 1')
    assert r.wait(lambda: s.status()['display_sleeping'], 4)
    m = r.mark()
    pwr(s, 0.3)
    assert not s.status()['display_sleeping'], 'PWR did not wake the screen'
    assert ui(s)['view'] == 'home'
    assert not (r.sent_types(m) & REQUESTS)
    s.console('set screen_timeout 0')


def test_pwr_quiets_a_ringing_timer_and_leaves_it_waiting(rig):
    r = rig()
    ok(r, 'timer.start', {'seconds': 2, 'label': 'Tea'})
    advance(r, 3)
    assert timer(r)['state'] == 'ringing' and ui(r.s)['view'] == 'alarm'
    m = r.mark()
    r.s.device.button(SILENCE_KEY, True)
    r.s.device.button(SILENCE_KEY, False)
    r.s.step()
    settle(r)
    assert timer(r)['state'] == 'done', timer(r)
    u = ui(r.s)
    assert u['view'] == 'home' and u['needs_you'] == 'timer', u
    assert 'dismiss' in u['controls'], 'the missed timer still needs Dismiss'
    r.snap('pwr-timer-quiet')
    m2 = r.mark()
    advance(r, 5)
    assert not tone_writes(r, m2), 'the alarm kept beeping after PWR'
    assert not (r.sent_types(m) & REQUESTS)
