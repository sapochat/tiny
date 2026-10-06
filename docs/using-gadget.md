# Talk, type, and interrupt

Wait for the device to show Ready. On the LCD board, BOOT is TALK and PLUS is CANCEL. On the round touchscreen, hold the screen to talk. Navigation swipes never cancel a turn or answer a question.

## Touch navigation

Views and activity are independent: you can navigate while Hermes is thinking, streaming, or speaking without stopping it.

| Starting view | Up / down | Right | Left |
|---|---|---|---|
| Home | Up opens the latest reply; down opens quick controls | No action | No action |
| Response | Scroll text, including at either boundary | Home, retaining reading position | No action |
| Quick controls | Adjust only the volume or brightness slider where the gesture starts | Home | No action |
| Approval | Scroll the question | No action | No action |
| Recording | No navigation | No navigation | No navigation |

Tap the rendered **Yes** or **No** button to decide an approval. Tap **Stop** in quick controls to stop work/audio explicitly. Existing physical CANCEL and console cancellation remain available; no swipe starts a new session or resets the device.

Home shows a quiet tappable reply indicator when text changes while the response is not visible: **New text**. A matching successful `turn.end` changes it to **Reply ready**; a non-success ending shows **Reply stopped** instead. On the 466px face-first display these are the state label above a **Read reply** pill; legacy displays retain the combined footer label. A final text snapshot alone is not completion. A turn without new text cannot mark a retained previous reply complete. Opening the response clears unread status (it does not claim every line was read); later hidden text changes make it unread again. This is local, in-memory status for the latest reply, not a notification history.

Tap that footer to open the response at its retained reading position, without starting audio. It does not replace approval, recording, settings or overlays, and completion does not change your selected view. Holding the footer also does not start recording; hold elsewhere on Home to talk. A contact begun on an older reply cannot open replacement text. The existing up/down navigation remains available while the footer temporarily replaces its hint.

Streaming follows new text only while at the bottom. Scrolling up holds your reading position, including after the final text arrives and when returning from Home. Scroll back to the bottom to follow again. Home retains the current activity indicator, and the previous reply remains readable while the next turn is thinking.

A gesture belongs to its starting view. A newly arrived/replaced approval cannot consume an older contact. Ambiguous diagonals and drags outside a button do not decide anything. A stationary hold still starts push-to-talk after 120 ms; once recording has started, movement is ignored and lifting the original talk contact sends normally. A separate navigation contact during recording neither submits nor discards it.

Quick controls are separate from the legacy settings/hardware-check menu. Hold the title for one second **while idle** to enter that menu, or use its existing physical chord/console command. A pending title hold is consumed if its view or idle eligibility changes; it cannot cancel a recording or speech that starts later. Starting a recording also invalidates older navigation contacts, without changing the original touch-owned TALK release. Its local item-navigation and Wi-Fi setup gestures are unchanged.

| What you want to do | Control |
|---|---|
| Ask a question | Hold TALK, speak, and release to send |
| Interrupt a spoken reply | Hold TALK to start speaking |
| Discard a recording, close a card, or stop a turn | Tap CANCEL |
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
and 17px support at y342. Idle says **Hold to talk** or **Tap to talk** according
to the configured mode. Listening says **Release to send** (or **Pause to send**
in silence-detection mode); its single brackets and meter reflect recording,
not fabricated audio. Speaking has double brackets. Thinking has no fake progress.

Unread completion is a **Reply ready** state and a **210×55px Read reply** pill;
new text and stopped replies remain distinct. The reading view removes the face,
labels the content **Latest reply**, and uses 24px Geist, measured wrapping,
eight 34px rows and a curved position marker. The complete reply is scrollable;
reading position and bottom-follow behavior are unchanged. Long approval text
uses five rows above equally sized **146×64px No / Yes** buttons, with amber Yes.
Generic questions are not relabeled as permissions. Unsupported characters have
a visible replacement glyph; full Unicode shaping and browser kerning are not
implemented. Native results do not establish physical readability.

Quick controls use **72×143px** rounded filled tracks labeled **Volume** and
**Brightness**, with actual percentages. **Stop response** is muted and a no-op
when there is no active work/audio. Drawing and hit testing share the same
rectangles; stale contacts still cannot decide replacement targets. Hold the
small **HERMES** title while idle for legacy settings. Setup, images and cards
retain their safe inscribed area, and other display sizes keep their renderer.

The perimeter is not a touch control, audio-volume scale or estimated progress. Idle has no bright ring; configured screen timeout still dims and sleeps normally. These are pixel dimensions verified in native simulation, **not physical touch-target or readability measurements**. No hardware power saving or frame-rate measurement is claimed.

## Device settings and hardware checks

Hold TALK and CANCEL together for one second to open or close device settings. On a touchscreen, hold the title bar for one second. Settings also work while the device is offline. Opening settings stops the current recording or reply.

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
