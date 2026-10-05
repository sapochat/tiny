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

Home shows a quiet tappable footer when reply text changes while the response is not visible: **New text - tap to read**. A matching successful `turn.end` changes it to **Reply ready - tap to read**; a non-success ending shows **Reply stopped - tap to read** instead. A final text snapshot alone is not completion. A turn without new text cannot mark a retained previous reply complete. Opening the response clears unread status (it does not claim every line was read); later hidden text changes make it unread again. This is local, in-memory status for the latest reply, not a notification history.

Tap that footer to open the response at its retained reading position, without starting audio. It does not replace approval, recording, settings or overlays, and completion does not change your selected view. Holding the footer also does not start recording; hold elsewhere on Home to talk. A contact begun on an older reply cannot open replacement text. The existing up/down navigation remains available while the footer temporarily replaces its hint.

Streaming follows new text only while at the bottom. Scrolling up holds your reading position, including after the final text arrives and when returning from Home. Scroll back to the bottom to follow again. Home retains the current activity indicator, and the previous reply remains readable while the next turn is thinking.

A gesture belongs to its starting view. A newly arrived/replaced approval cannot consume an older contact. Ambiguous diagonals and drags outside a button do not decide anything. A stationary hold still starts push-to-talk after 120 ms; once recording has started, movement is ignored and lifting the original talk contact sends normally. A separate navigation contact during recording neither submits nor discards it.

Quick controls are separate from the legacy settings/hardware-check menu. Hold the title for one second **while idle** to enter that menu, or use its existing physical chord/console command. Its local item-navigation and Wi-Fi setup gestures are unchanged.

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

The local Tiny expression candidate uses a true-black background, a fixed neutral mascot palette, and a single central focus. Its 192px original outline never moves: receptive listening eyes, an upward thinking gaze, and a small closed-lip ready smile are locally composited from existing expression artwork. Ready is selected only for successful completed unread text, not streaming, final snapshots or failures. Reading clears it. Entries blend from the last rendered facial pose over eight 100ms animation ticks; interruption/reversal keeps the identical boundary frame. Hidden views pause the pose; idle has a softened periodic blink, while listening/thinking/ready hold still. Speaking uses the neutral face and perimeter indicator, not fabricated lip-sync. Listening has single perimeter brackets; thinking has three stationary dots (not progress); speaking has double brackets. The listening meter above the mascot uses actual captured sample levels, not a decorative waveform. An unread reply adds a quiet lower marker and a **232×56px** read target; the completion rules above are unchanged. Response text uses **18px cells** rather than 12px, with retained manual scrolling and a visible scroll track for long replies.

Quick controls keep predictable vertical gestures in **68×136px** slider targets. **Screen** means display brightness; **Stop turn** explicitly stops current work/audio, and is a no-op when idle. Approval remains explicit Yes/No with **144×64px** targets; no gesture means approval. The same rectangles are used by drawing and hit testing. Hold the small **HERMES** label while idle for the legacy settings menu. Existing setup, image and card overlays retain their safe inscribed area.

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
