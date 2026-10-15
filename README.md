# Tiny

Tiny is a desk companion that talks to your own [Hermes Agent](https://github.com/NousResearch/hermes-agent). It runs on a Waveshare ESP32-S3 Touch AMOLED 1.75C: a 1.75-inch round 466×466 touchscreen with a microphone and speaker. Hold to talk, let go, and Hermes answers on the screen and out loud, using its own tools, memory and skills.

Tiny is built on [Hermes Gadget](https://github.com/Adolanium/hermes-gadget-sdk) and keeps the SDK's boards, simulator, plugin and tooling. The round-screen interface described below is Tiny's own work.

<p align="center">
  <img src="docs/images/tiny/00-home-idle.png" width="200" alt="Tiny's Home screen, idle">
  <img src="docs/images/tiny/05-controls-busy.png" width="200" alt="Quick controls while Hermes is working">
  <img src="docs/images/tiny/35-recent-3.png" width="200" alt="The Recent shelf with three jobs">
</p>
<p align="center"><sub>Home, quick controls and the Recent shelf, captured from the simulator, which runs the same device core as the firmware.</sub></p>

## What Tiny does

- **Talk.** Hold the screen (or tap, in tap-to-talk mode) and speak; release to send. Replies stream as text and play as speech. Tiny listens only while you hold.
- **A face with moods.** An animated character on true black moves through idle, listening, thinking, speaking, reply-ready, asking, alert and sleep. See [the round companion face](docs/using-gadget.md#round-amoled-companion-face-466466).
- **Approvals you can read.** When Hermes asks before doing something, the whole question scrolls, and equal **Yes** and **No** buttons unlock only once you have read to the end.
- **Recent work.** The last eight jobs (seven days at most) sit on a shelf as cards with a coloured outcome (Finished, Failed, Stopped, Working, Unknown) and an excerpt of the reply. They survive restarts, and opening one never reruns it. See [Recent results](docs/using-gadget.md#recent-results).
- **Quick controls.** Swipe down from Home for volume and brightness sliders, **Mute voice**, **Stop task**, **New chat**, **Recent** and **Settings**.
- **Mute is not Stop.** **Mute voice** quiets the speaker only. **Stop task** sends one stop request and reports what Hermes says happened, including **Outcome unknown** when it never hears back. See [Mute voice, Stop task and Discard](docs/using-gadget.md#mute-voice-stop-task-and-discard).
- **Fresh conversations.** Hold **New chat** for one second, or let the host start a new conversation after a quiet stretch (`idle_reset_minutes`). Memory, Recent results and settings stay. See [New chat](docs/using-gadget.md#new-chat) and [Conversations and idle reset](docs/hermes-integration.md#conversations-and-idle-reset).
- **Knows the time.** Hermes sends its wall clock and timezone when Tiny connects and on every heartbeat. Tiny keeps counting through Wi-Fi drops and stops claiming a time 12 hours after its last sync. No NTP needed. See [the protocol](docs/protocol.md).
- **Updates over the air.** After the first USB flash, `hermes gadget update` installs new firmware over Wi-Fi, and a build that can't reach Hermes rolls itself back.

## In progress

These are being built on the `tiny/improve` branch and are not on `main` yet:

- An idle face with the time (Portrait, Portrait + time or Clock).
- Larger Home text, and a small mark when something needs you.
- Visible **Retry now** and **Settings** on the offline screens, and **Done** in Settings.
- Quick controls in four bands, with taller targets and sliders you can drag from anywhere.
- How long ago each Recent job ran, and a tappable **Last task**.
- A countdown timer Hermes can set, with a local alarm that works without Wi-Fi.

Until the idle face lands, Tiny receives the time but doesn't draw it.

## Flash and memory

The 1.75C has 32 MB of flash. Tiny's firmware uses two 8 MB app slots ([`partitions-32mb.csv`](firmware/esp32/partitions-32mb.csv)), so the running build stays intact while the next one downloads. The current build is about 1.8 MB, leaving the slot about 78% free.

A board still on the SDK's shared table (two 1.94 MB slots) needs **one USB flash** to switch, because an over-the-air update can't change the table. Settings, Wi-Fi and the pairing key sit at the same address in both tables and survive the switch. See [Hardware](docs/hardware.md).

Two build flags keep each board's firmware to what it actually draws:

| Flag | On for | What it holds |
|---|---|---|
| `CONFIG_HG_EXPRESSION_PACK` | Round AMOLED boards | The face video: 14 clips of 96×96 grey frames, about 443 KB |
| `CONFIG_HG_LEGACY_MASCOT` | Every other board | The SDK's 1-bit mascot, about 27 KB |

[Development](docs/development.md) covers both, and why about 220 KB of Wi-Fi mesh code is always linked.

## Try it without hardware

The simulator runs the same C++ core as the firmware. With Python 3.10+, CMake 3.16+ and a C++17 compiler:

```bash
python -m pip install -e ".[dev]"
hermes-gadget build-sim --test
hermes-gadget devserver --pairing
```

In a second terminal:

```bash
hermes-gadget sim --url ws://127.0.0.1:8765/gadget --board sim-466x466-round
```

Type `approve <CODE>` in the first terminal using the code on the simulated screen, then type a message to get a streamed echo. Real conversations need Hermes with the Gadget plugin; see [Connect Hermes](docs/connect-hermes.md). The [desktop guide](docs/desktop.md) covers platform setup and live audio.

## Build and flash Tiny

```bash
python -m platformio run --project-dir firmware/esp32 -e esp32s3-touch-amoled-175c
```

The first install, or the move to 8 MB slots, is over USB: see [Set up a board](docs/setup-board.md). After that, use `hermes gadget update`. The build checks its own size against the slot it's going into.

## Testing

Tests drive the real device core and the production device hub end to end over loopback, with disposable stores, plus a lane against a real Hermes gateway. Run them with `pytest`.

Visual changes are checked with [`tools/design_capture.py`](tools/design_capture.py). It drives the core through every screen, confirms each one reached its intended state, and produces byte-identical captures from run to run, so a before/after comparison shows only real changes. See [Development](docs/development.md).

Simulator results and successful builds are not hardware verification. A port counts as verified only with a complete physical report; see [Hardware verification](docs/hardware-validation.md).

## Guides

| Using Tiny | Building on it |
|---|---|
| [Talk, type and interrupt](docs/using-gadget.md) | [Development and tests](docs/development.md) |
| [Set up a board](docs/setup-board.md) | [Architecture](docs/architecture.md) |
| [Connect Hermes](docs/connect-hermes.md) | [Protocol](docs/protocol.md) |
| [Hermes integration reference](docs/hermes-integration.md) | [Add a board, actions or sensors](docs/porting.md) |
| [Try the simulator](docs/simulator.md) | [Customize the face](docs/faces.md) |
| [Troubleshooting](docs/troubleshooting.md) | [Hardware and wiring](docs/hardware.md) |
| [Remote access with Tailscale Funnel](docs/tailscale-funnel.md) | [Workspace history and recovery](docs/tiny-workspace.md) |

Video-production sources for the face live in [`animations/`](animations/README.md). The original idea is in [`IDEA.md`](IDEA.md).

## Other boards

The SDK's other targets still build from this repository: ESP32-S3 boards from Waveshare, Espressif, M5Stack and LilyGO, the [Raspberry Pi 4/5 Linux client](docs/linux.md), and the desktop simulator. They keep the SDK's original interface; the round-screen work above is for 466×466 round boards. See [Supported hardware](docs/supported-hardware.md).

## Credits

Tiny is built on [Hermes Gadget](https://github.com/Adolanium/hermes-gadget-sdk) by Adolanium and its contributors; the [changelog](CHANGELOG.md) has SDK release notes and contributor credits. Text is set in [Geist](assets/fonts/README.md) under the SIL Open Font License.

Contributions follow [CONTRIBUTING.md](CONTRIBUTING.md). Report security problems privately through [SECURITY.md](SECURITY.md).

## Affiliation and trademarks

Tiny and Hermes Gadget are **independent, community-made projects**. They are not affiliated with, endorsed by, sponsored by or supported by Nous Research.

"Hermes", "Hermes Agent", "Nous Research" and the Hermes Agent mascot (the girl with the headphones, sometimes called "Nous Girl") are trademarks or brand assets of Nous Research. They appear here only to describe compatibility with Hermes Agent.

## License

Project code and documentation are licensed under the [MIT license](LICENSE).

Third-party dependencies, adapted drivers and artwork keep their own licenses. See [Third-party licenses and attribution](THIRD_PARTY_NOTICES.md) and [NOTICE](NOTICE).

The MIT license grants no rights to Nous Research's names or marks.
