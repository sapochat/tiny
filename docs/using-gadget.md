# Talk, type, and interrupt

Wait for the device to show Ready. On the LCD board, BOOT is TALK and PLUS is CANCEL. On the round touchscreen, hold Home to talk. Navigation swipes never cancel a turn or answer a question.

## Touch navigation

Views and activity are independent: you can navigate while Hermes is thinking, streaming, or speaking without stopping it.

| Starting view | Up / down | Right | Left |
|---|---|---|---|
| Home | Up opens the latest reply; down opens quick controls | No action | No action |
| Response | Scroll text, including at either boundary | Home, retaining reading position | No action |
| Quick controls | Adjust only the volume or brightness slider where the gesture starts | Home | No action |
| Approval | Scroll the question | No action | No action |
| Recording | No navigation | No navigation | No navigation |

Tap the rendered **Yes** or **No** button to decide an approval. Existing physical CANCEL and console cancellation remain available; no swipe starts a new session or resets the device.

Several swipes also have a visible tap route on the 466px round display, when there is room for it: **↓ Controls** on the idle face (only when no action fills the action row) opens quick controls, the **‹ Latest reply** and **‹ Quick controls** titles return to Home, and **Read reply** opens unread text. These routes are not universal: while Silence and Stop work fill the two action slots there is no Read reply or Controls target, and a reply you have already read is reopened by swiping up. Swipe down from Home for quick controls at any time.

### Silence, Stop work and Discard

These are separate actions with separate targets:

| Action | What it does | What it never does |
|---|---|---|
| **Silence** | Stops the speaker immediately. Later audio for the same reply stays quiet until a new turn starts or you ask something new. | Send anything to Hermes, open the microphone, or stop Hermes working |
| **Stop work** | Sends one stop request for the current work, quiets its speech, and shows **Stop requested** | Claim the work has stopped |
| **Discard** | Ends a recording without making a request | Recall audio that already streamed |

On the 466px display, **Silence** appears whenever speech is playing and **Stop work** whenever Hermes is working, on Home, the reading view and quick controls, always with Silence on the left and Stop work on the right. Quick controls keep both in place and outline the one that is unavailable. Pressing Stop work again, or CANCEL, sends nothing more. Final reply text is not the end of the work: Stop work stays available until Hermes ends the turn.

**Stop requested** stays until Hermes reports how that work ended:

| Hermes reports | Tiny shows |
|---|---|
| `cancelled` | **Stopped** · Completed steps are not undone |
| `success` | **Finished** · Stop was not confirmed |
| `failure` | **Ended with an error** · Stop was not confirmed |
| Connection lost first | **Outcome unknown** · Connection lost while stopping. A later report for the same turn still updates it. |
| Stop pressed before Hermes named the work | **Outcome unknown** · Sent before Hermes started |
| An ending that does not name the stopped turn | Nothing changes: still **Stop requested** |
| Nothing about the turn for three minutes | **Outcome unknown** · No ending from Hermes |

A stop request is not an undo: actions that already ran stay done. The outcome stays on the idle face until the next activity rather than disappearing after a few seconds. A turn that ends after you have asked something new belongs to the earlier work; it never ends or relabels the new request. Asking something new also leaves an earlier unconfirmed stop behind as unknown: the new request gets its own **Stop work**, never an inherited **Stop requested**. Work that Hermes never ends is not shown as finished; after three minutes without word from Hermes about it, Tiny says **Task status unknown** · No ending from Hermes. If the connection drops while Hermes is working, the offline screen and the idle face say **Task status unknown**; reconnecting does not resend anything.

### Recording

Hold Home anywhere that is not a button to talk. Audio streams to Hermes while you hold; releasing finishes the recording and makes the request, so the face says **Release to finish**. A hold shorter than 350 ms is discarded as too short.

- The reading view never starts a recording from a still finger. Use its **Hold to talk** target (**Tap to talk** in tap mode), or return Home.
- While a finger holds the screen, it owns the only touch contact, so there is no Discard button. To be able to discard, use tap-to-talk mode, or hold the physical BOOT/TALK button and tap **Discard**.
- In tap-to-talk mode, **Discard** and **Finish** appear; a pause also finishes.
- Discard sends `audio.cancel`. The hub drops the partial upload and makes no request, but audio that already streamed during the recording did reach the host.
- Touch Talk targets never answer a question. The physical BOOT/TALK button keeps its existing meaning during a question (yes, after the 0.6 s arm delay); this release does not remap it.

Home shows a quiet tappable reply indicator when text changes while the response is not visible: **New text**. A matching successful `turn.end` changes it to **Reply ready**; a non-success ending shows **Reply stopped** instead. On the 466px face-first display these are the state label above a **Read reply** pill; legacy displays retain the combined footer label. A final text snapshot alone is not completion. A turn without new text cannot mark a retained previous reply complete. Opening the response clears unread status (it does not claim every line was read); later hidden text changes make it unread again. This is local, in-memory status for the latest reply, not a notification history.

Tap that footer to open the response at its retained reading position, without starting audio. It does not replace approval, recording, settings or overlays, and completion does not change your selected view. Holding the footer also does not start recording; hold elsewhere on Home to talk. A contact begun on an older reply cannot open replacement text. The existing up/down navigation remains available while the footer temporarily replaces its hint.

Streaming follows new text only while at the bottom. Scrolling up holds your reading position, including after the final text arrives and when returning from Home. Scroll back to the bottom to follow again. Home retains the current activity indicator, and the previous reply remains readable while the next turn is thinking.

A gesture belongs to its starting view and to the revision of the target it touched: a Silence contact cannot quiet a newer stream, a Stop work contact cannot stop a newer turn, and a Discard or Finish contact cannot act on a later recording. A newly arrived/replaced approval cannot consume an older contact, and a control that appears under a resting finger does not take it. Ambiguous diagonals and drags outside a button do not decide anything. A stationary hold on Home starts push-to-talk after 120 ms; once recording has started, movement is ignored and lifting the original talk contact finishes normally. Another contact during recording does nothing unless it taps a visible Discard or Finish target.

Quick controls are separate from the legacy settings/hardware-check menu. When Tiny is idle, quick controls show **Settings**; otherwise they say **Settings open when idle**. Holding the HERMES title on Home for one second **while idle** still opens the menu, as do the physical chord and console command when idle. On the offline, connecting and pairing screens, holding the title (the top bar on rectangular touch boards) opens it too, because there is no other on-device route to Wi-Fi and server settings there; this works even when the last task's outcome is unknown, and never cancels or resends that work. Settings never stop a recording, speech or work: the chord and console are refused while busy, and a refused chord is consumed rather than acting as CANCEL. A pending title hold is consumed if its view or idle eligibility changes; it cannot cancel a recording or speech that starts later. Starting a recording also invalidates older navigation contacts, without changing the original touch-owned TALK release. Its local item-navigation and Wi-Fi setup gestures are unchanged.

| What you want to do | Control |
|---|---|
| Ask a question | Hold TALK, speak, and release to send |
| Interrupt a spoken reply | Hold TALK to start speaking |
| Discard a recording, close a card, or request a stop | Tap CANCEL. With work running it sends one stop request; with only speech playing it silences locally. |
| Start a fresh conversation | Hold CANCEL for two seconds |
| Answer a confirmation question | TALK means yes; CANCEL means no |
| Type in the simulator | Enter a message in the text box and press Enter |
| Save the simulator's device screen | Press Ctrl+S |

Long replies turn their own pages. Simulated boards with scroll buttons also accept Up and Down.

Try asking Hermes to show a reminder on the screen. The agent can use `gadget_display` to display a card. Devices with actions can also respond to requests such as "Turn the LED purple."

If speech is missing, check [audio setup](connect-hermes.md#4-enable-speech). For connection problems, use [troubleshooting](troubleshooting.md). To change Wi-Fi or install firmware updates, see [Manage an existing gadget](setup-board.md#manage-an-existing-gadget).

## Round AMOLED companion face (466×466)

The local Tiny v2 candidate plays motion from the approved, non-smoothed video pack on a true-black background. The full silhouette can move; this supersedes the earlier fixed-outline facial patches. Offline conversion embeds 96×96, four-level grayscale frames displayed at 192×192, at five frames per second. It does not decode MP4 on the device. Idle, listening and speaking loop; thinking, reply-ready, asking and alert play their authored entries and hold their final poses. Speaking is an authored animation, **not audio-synchronized lip-sync**.

Ready is selected only for successful completed unread text, not streaming, final snapshots or failures. Reading clears it. When a completed hold returns to neutral, its authored exit plays; early interruption skips the incompatible exit. New recording, speech, thinking, approval or alert preempts decorative transitions immediately, rather than waiting five seconds. These cuts are intentionally responsive and are not promised to be pixel-continuous. Hidden views keep animation time; returning shows the current activity rather than replaying a stale entry.

Approval prioritizes the complete scrollable question and existing Yes/No semantics, without a decorative portrait. Network loss/setup errors use the alert animation in the existing safe-area layout. During quiet idle dimming, fall-asleep leads to the sleeping loop; existing screen timeout still turns the display off on schedule and stops rendering. Waking from the sleep pose plays wake, unless a higher-priority activity preempts it. Short timeouts can skip unfinished sleep/wake decoration. The first wake touch still cannot record or approve.

The face-first layout places the original 192px animated character at (137,96),
with smooth proportional Geist text: a small HERMES label, 30px state at y299,
and 17px support at y342. When a support line and action targets share the face,
the two lines move up to y289 and y328 so neither touches the targets. Idle says
**Hold to talk** or **Tap to talk** according to the configured mode, with a
**↓ Controls** link. Listening says **Release to finish** for a touch hold,
**Release BOOT to finish** for a button hold, or **Pause or tap Finish** in
tap mode; its single brackets and meter reflect recording, not fabricated audio.
Speaking has double brackets. Thinking has no fake progress; a host status
phrase appears only when Hermes sends one.

Home, recording and reading share one action row below the text: one
**210×55px** target, or two **138×55px** targets side by side. In priority
order it holds Discard/Finish while recording, otherwise Silence, Stop work
and Read reply (Home), or Hold to talk (reading, when idle). Decorative brackets
stop above it. Unread completion is a **Reply ready** state and a **Read reply**
target; new text and stopped replies remain distinct. Outcomes such as
**Stopped**, **Finished**, **Outcome unknown**, **Discarded**, **Connection
lost** or **Couldn’t finish** replace the idle caption until the next activity.
Where that caption is not visible, the ending is still shown without moving you:
the reading view adds one line under its action row (**Stopped · may be partial**,
**Error · may be partial**, **Unknown · may be partial**, **Finished** or
**Finished · stop unconfirmed**), and quick controls name it on the inert Stop
target (**Stopped**, **Error**, **Unknown**, **Finished**). The reading line
appears only for text from that work (text a newer turn sends for older work is
not shown in its place); your scroll position is kept. Discarding a recording
does not end work that is still open: Stop work stays available.

The reading view removes the face, labels the content **‹ Latest reply** (tap it
to return Home), and uses 24px Geist, measured wrapping, seven 34px rows and a
curved position marker; the seventh row ends above the action row. The complete
reply is scrollable; reading position and bottom-follow behavior are unchanged.
Long approval text uses five rows above equally sized **150×96px No / Yes**
buttons with the same fill and text colour; neither answer is emphasized.
Generic questions are not relabeled as permissions. Unsupported characters have
a visible replacement glyph; full Unicode shaping and browser kerning are not
implemented. Native results do not establish physical readability.

Quick controls use **72×143px** rounded filled tracks labeled **Volume** and
**Brightness**, with actual percentages, then **160×56px Stop work** and
**Silence** targets that stay in place (outlined when unavailable), and
**Settings** when idle. **‹ Quick controls** returns Home. Drawing and hit
testing share the same rectangles; stale contacts still cannot decide
replacement targets. Setup, images and cards retain their safe inscribed area,
and other display sizes keep their renderer.

Assuming the full 1.75-inch circle is active display (0.095 mm per pixel), the
approval buttons are nominally 14.3×9.2 mm, the shared action row 5.2 mm tall,
and the quick-control actions 5.3 mm tall. These are geometric conversions, not
measurements: only the approval buttons reach the 9–12 mm range explored in the
review, and none of these sizes has been checked on a physical board.

The perimeter is not a touch control, audio-volume scale or estimated progress. Idle has no bright ring; configured screen timeout still dims and sleeps normally. These are pixel dimensions verified in native simulation, **not physical touch-target or readability measurements**. No hardware power saving or frame-rate measurement is claimed.

## Device settings and hardware checks

Hold TALK and CANCEL together for one second to open or close device settings. On a touchscreen, tap **Settings** in quick controls or hold the title bar for one second. Settings also work while the device is offline. Settings open only when the device is idle: they never stop a recording, a reply or Hermes's work. While busy the request is refused (the round display says **Settings open when idle**).

Tap CANCEL to move to the next item, then tap TALK to change it. On a touchscreen, swipe down for the next item and tap to select. Boards with Up and Down buttons can move in either direction. Select **Back to Hermes** to leave.

| Item | What it does |
|---|---|
| Speaker volume | Change volume in steps of 10 percent |
| Screen brightness | Choose 10, 25, 50, 75, or 100 percent when the display supports it |
| Talk mode | Choose hold-to-talk or tap-to-talk with silence detection |
| Microphone check | Show the live input level; nothing is saved or sent to Hermes |
| Speaker check | Play a short, quiet tone at the current volume |
| Display check | Show red, green, blue, white, and black bands |
| Input check | Show the last button pressed; release CANCEL to leave the check |
| Device information | Show the board, firmware, device ID, and available audio drivers |
| Battery and power | Show available power readings on boards with a power driver |
| Screen timeout | Choose always on, 30, 60, 120, or 300 seconds |
| Power off | Select twice to shut down a board with a power driver |
| Wi-Fi setup | Start [phone-based setup](setup-board.md#set-up-wi-fi-with-your-phone) on ESP32 boards |

Volume, brightness, talk mode, and screen timeout survive restarts. Unavailable drivers show as unavailable. These checks help you test the hardware; a completed tone does not prove that a physical speaker produced sound.

Screen timeout is off by default. When enabled, a brightness-capable display dims halfway through the idle period, then goes dark. The first button press or touch wakes it without recording or answering a prompt. Incoming replies and prompts wake it too. Recording, playback, settings, pairing and updates keep it awake. The processor and Wi-Fi remain running; this is screen sleep. Use the board's Power off control to shut down the device.

Incoming confirmation prompts and firmware updates close settings. You cannot open settings during a prompt or update. The USB console also accepts `settings`, `settings close`, and `set brightness 50`.
