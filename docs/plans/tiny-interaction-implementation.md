# Tiny interaction implementation plan

**Goal:** Turn Tiny into a calm, controllable conversational companion, beginning with a verified same-board interaction release and progressing to durable work, authenticated handoff, natural conversation and tactile hardware.

**Architecture:** Preserve the portable C++17 application and deterministic native renderer, the Python DeviceHub and Hermes adapter, and existing pairing/approval boundaries. Separate presentation, local playback, capture and remote work state. Introduce host/protocol extensions only as real, compatibility-tested contracts—not optimistic UI states.

**Stack:** Existing C++17 core, native C ABI simulator, Python >=3.10, websockets, pytest, CMake; configured ESP-IDF/PlatformIO for firmware. No new frontend framework or runtime video engine.

**Execution owner:** Claude Opus 5.5 (`claude-opus-5-5`), coordinated and reviewed by Janus. External CLI execution replaces the writing-plans skill's generic subagent and frequent-commit defaults. No commits or publication authorized.

## Scope and authority

The full recommendation is `~/Documents/Research/tiny-interaction-review/recommendation.md`. It is product direction, not evidence of implemented behavior. This plan authorizes local source/documentation edits and disposable provider-free tests. It does not authorize flashing/OTA, production gateway/plugin installation or restart, live actions, publishing, purchasing, changing provider/config/credentials, or modifying other profiles.

Canonical checkout: `.`, starting commit `d6a06bb260fd998f2d55f94d550a316ec0120440`, main, clean before this plan. Implementation candidate: `.`, detached at the same commit. Work there to avoid changing a possibly linked live plugin. Do not merge back or commit; Janus reviews the candidate and owns integration. Reports: `~/Documents/Research/tiny-interaction-review/implementation/`.

The immediate Opus assignment is **M0–M2**, a complete same-board control/usability milestone, plus concrete dependency contracts for M3–M5. The later product program is not represented as completed by that milestone. Hardware, authenticated Desktop integration and real acoustic validation remain explicit subsequent gates; do not fabricate working stand-ins or broaden into other repositories.

## Mandatory preparation

Read candidate `AGENTS.md`, `CONTRIBUTING.md`, `docs/development.md`, `docs/porting.md`, `docs/hardware-validation.md`, `docs/using-gadget.md`, `docs/protocol.md`, `docs/simulator.md`, `pyproject.toml`. Load/read `~/.hermes/skills/hardware/gadget-touch-workflow-verification/SKILL.md` and `~/.hermes/skills/creative/premium-ui/SKILL.md` as procedural input. Web-specific visual recipes do not override safety, small-screen readability or deterministic firmware.

Read source definitions/usages before editing. Important verified entry points:
- `firmware/core/include/hg/{app,ui,touch}.hpp`: app/model/control contracts.
- `firmware/core/src/{app,app_settings,touch,ui}.cpp`: capture, cancellation, controls, gestures, renderer.
- `plugin/hub.py`: DeviceSession audio output; `_h_audio_end`, `_h_audio_cancel`, `_h_cancel`; handler registry.
- `plugin/adapter.py`: Hermes turn lifecycle/cancellation/approval translation.
- `python/hermes_gadget/devserver.py`: provider-free EchoBrain.
- `tests/conftest.py`: real loopback DeviceHub, temporary store and native simulator fixtures.
- `tests/test_touch_navigation.py`: touch rig, actual control geometry, framebuffers and wire receipts.
- `tests/test_face_first.py`, `tests/test_face_first_font.py`, `tests/test_reply_indicator.py`, `tests/test_stale_title_hold.py`, `tests/test_sim_hub.py`: regression contracts.

Do not regenerate, replace or smooth approved animation assets. Do not change GPIO mappings, microphone gain, partitions or board configuration as an incidental UI fix.

## Invariants and evidence policy

- Navigation never cancels work, submits/discards capture, resets a session or approves.
- A contact belongs to the view/target/revision where it began. Wake touches cannot act. Newly appearing controls cannot consume older contacts.
- Silence, cancel remaining work, discard current capture, microphone isolation and new conversation are distinct operations.
- Local feedback is not a confirmed remote outcome. Stop requests stay pending/unknown until matching lifecycle evidence establishes an outcome.
- Ordinary questions remain ordinary questions; do not infer structured authority from prose. New Talk controls cannot silently inherit legacy Talk-as-Yes.
- Preserve retained reading position and bottom-only streaming follow. No touch auto-paging.
- Current audio samples leave the device during capture; the inspected hub dispatches on audio.end. Discard is not proof that nothing was transmitted or retained.
- No UI claim of electrical mic isolation, authenticated handoff, durable storage or natural full-duplex voice without actual implementation/evidence.
- Character leads at rest and yields to controls/review. True black, existing Geist, warm-white hierarchy, restrained amber. Equal approval emphasis. No fake percentages or motion-gated input.

**Testing:** Write failing end-to-end workflows BEFORE production code, using real native core and production loopback hub with synthetic input and disposable state. Never add unit tests after the code they test. Strongly prefer E2E as the only new test mechanism. If isolation becomes necessary, first enumerate identifiable failure modes and explain why an isolated test is necessary; write it failing before implementation. Existing unit suites may still be run unchanged.

At every E2E run preserve exact command, fixture/source revision or hashes, environment/package versions, exit status/JUnit results, protocol receipts, screenshots/framebuffer hashes and rerun instructions. Failed runs remain evidence; do not overwrite red artifacts with green. Do not weaken assertions to obtain passes. Pixel geometry changes require explicit rationale and continued behavioral assertions.

## M0 — Reproducible baseline and failure inventory

**Deliverable:** baseline evidence, a runnable candidate environment, and failing new interaction workflows.

1. Check status/HEAD in both worktrees; inventory only non-secret tooling. Create a candidate-local environment instead of relying on moved archive shebangs. Existing root has no `.venv` and shell CMake was absent at planning time. `uv` is available. Inspect the manifest, then use `uv venv .venv` and `uv pip install --python .venv/bin/python -e '.[dev,images]' cmake` if needed. These are local development dependencies, not production installation. Add no dependency to pyproject just for convenient tooling.
2. Build native: `PATH="$PWD/.venv/bin:$PATH" PYTHONPATH=python .venv/bin/python -m hermes_gadget build-sim --test`. Require actual CMake/CTest output, not a zero exit from a non-entrypoint module. Discover actual `libhgsim.so` and export `HGSIM_LIBRARY` to it for tests.
3. Set `TMPDIR=$TMPDIR`, and disposable `HERMES_HOME` beneath a short task-owned scratch directory before pytest. Do not inherit production Hermes home for optional gateway imports. Tests in `tests/conftest.py` use loopback and temporary DeviceStore; inspect any extra suite before running it.
4. Run existing relevant baseline suites. Archive or missing video assets can block asset-dependent tests: report exact gaps, preserve assets and assertions, use the known archive only after verifying paths. Never call paid media-generation code.
5. Create **new** `tests/test_interaction_surface_e2e.py`, reusing existing rig conventions rather than copying a large infrastructure layer. Add a run-artifact fixture/report helper only where necessary. Freeze initial failures before production edits.
6. Enumerate failures to exercise: late audio after Silence; new stream same turn vs new turn; stream-ID reuse; stale stop target; stale turn.end; repeated Stop; disconnected request; settings during active work; accidental response hold; capture owner release; second contact during capture; wake/prompt replacement; font/target clipping; legacy board regression.

## M1 — Immediate, truthful control

### 1. Silence without cancelling or opening the microphone

**Files:** modify `app.hpp`, `ui.hpp`, `app.cpp`, `app_settings.cpp`, `touch.cpp`, `ui.cpp`; modify `plugin/hub.py`, protocol documentation and devserver only if the traced path requires it. New tests live in the E2E file.

Write failing workflow: start a real hub audio stream and a text-producing turn; tap an actually rendered Silence control; assert local playback aborts, no audio.start upload/cancel/session.new request is emitted, and text/turn completion continue. Inject later chunks and additional audio.start for the SAME turn; they must not restore sound. Start a distinct next turn; expected playback resumes. Repeat with connection loss and missing/legacy turn identifiers.

Implement a scoped local silence policy, not merely a one-time `stop_playback()` call. Trace stream/turn IDs, playback credit and AudioOut completion so dropping playback cannot deadlock the host. Prefer an additive documented playback-control message only if necessary; gate/compatibility-test it and ensure local silence still works against an old host. Do not rename audio.cancel (microphone upload) to mean speaker silence. No global muted state accidentally carried into future turns.

Expose Silence whenever output is active on the 466px home/response/controls views. Its target and rendering share geometry and version guards. Do not hide it behind a swipe or reassign an arbitrary whole-screen tap.

### 2. Honest Stop work lifecycle

**Files:** `app.hpp`, `ui.hpp`, `app.cpp`, `app_settings.cpp`, `ui.cpp`; inspect `adapter.py`, `hub.py` and `devserver.py` consumers before adding protocol fields.

Write red workflows: Stop on work-only turn; Stop after final text but before turn.end; repeated Stop; matching cancelled/failure/success outcome; old turn.end after a new request; disconnect before outcome. Verify local silence occurs immediately, one cancel intent is sent for the selected work, no fake final outcome is shown, and old events cannot relabel new work.

Expose **Stop work** directly during active work on home, reading and controls without requiring navigation first. Use explicit request-pending state and last-known outcome. The existing `cancel_turn()` prints Cancelled immediately; replace that optimistic feedback with Stop requested. A matching authoritative cancellation can become Stopped; a completed action/turn must not be relabeled cancelled; disconnect is unconfirmed/unknown. Do not synthesize an execution guarantee from host receipt. If current backend lacks sufficient IDs, keep the safe unknown state and document the integration requirement rather than invent an acknowledgement.

### 3. Capture, explicit discard and reading ownership

**Files:** `touch.hpp`, `touch.cpp`, `app.hpp`, `app.cpp`, `app_settings.cpp`, `ui.hpp`, `ui.cpp`.

Write red workflows BEFORE changes for paused scrolling on Response, explicit capture target, no-speech capture, tap-mode discard and stale contacts. Remove hidden hold-to-talk from the reading body; keep reading gestures purely navigational. Define an explicit reachable Talk affordance where supported. Preserve Home PTT and its original contact's release semantics.

Show truthful copy: Release to finish in hold mode; mode-appropriate finish instructions otherwise. Add an explicit visible discard action for tap-to-talk; do not promise a simultaneously tappable button can discard a single-touch held recording. On a single-touch controller, safely support discard via available explicit alternate input or document the limitation. No slide-to-cancel invention and no fake multi-touch capability. Do not silently remap BOOT or physical Talk on legacy boards. New companion input contracts must never approve while presented as clarification. Cross-surface clarification during approval belongs to M4 unless supported safely end to end.

Acceptance: no recording starts from a patient reader; discard emits audio.cancel without audio.end/request dispatch; no UI claims that prior streamed data never left Tiny; legacy physical cancellation remains available.

## M2 — Current-board visual/usability finish

### 4. Discoverable controls and balanced review

**Files:** `ui.hpp`, `ui.cpp`, `app_settings.cpp`, `app.cpp`; documentation `docs/using-gadget.md`.

Before code, add native rendered-touch workflows for entering Controls by visible affordance; idle Settings entry without logo-hold knowledge; return navigation; settings ineligible during capture/approval/update; equal emphasis Yes/No; long question exact tail reachable; explicit work actions on reading without overlap.

Retain swipe shortcuts, add visible tap routes where space allows. Settings must not secretly cancel an active task: refuse with clear safe feedback or expose only safe quick controls until idle. Preserve legacy hardware-diagnostic entry for other boards. Enlarge consequential controls as the existing circle safely allows, reducing portrait/text rows if necessary; do not claim the 9–12mm exploration target is met unless actual rendered geometry supports it. Keep font metrics, row counts, wrapping and scroll bounds shared.

Do not change generic Yes/No into action-specific labels by guessing intent. Remove automatic amber emphasis from Yes. Preserve equal targets, question contents, prompt arming and stale-touch guards. Reading and review stay portrait-free. Existing approved face/video remains intact.

### 5. Honest state and error presentation

**Files:** `app.cpp`, `ui.cpp`, `app_settings.cpp`; existing reply-indicator regressions.

Add E2E cases for successful reply, partial/stopped text, offline during work, reconnect without replay, unavailable settings and active audio plus pending work. Preserve distinct New text / successful completion / stopped outcome states. Promote meaningful host status only when present; do not generate inferred task titles or percentages in firmware. Operational errors must remain readable/actionable; no vanishing toast as the only recovery route. Keep pairing/setup/update safe areas and legacy renderer behavior working.

### 6. Verification, documentation and evidence handoff

Run existing suites (after actual native library build) plus new E2E:

`PATH="$PWD/.venv/bin:$PATH" .venv/bin/python -m pytest tests/test_interaction_surface_e2e.py tests/test_touch_navigation.py tests/test_reply_indicator.py tests/test_face_first.py tests/test_face_first_font.py tests/test_round_amoled.py tests/test_round_amoled_safety.py tests/test_stale_title_hold.py tests/test_sim_hub.py tests/test_protocol.py -v --basetemp=$TMPDIR/ti-e2e --junitxml=artifacts/interaction-v1/green/results.xml`

Ensure `HGSIM_LIBRARY`, disposable `HERMES_HOME`, and artifact-directory variables are explicitly set; record all values in rerun instructions. Environment preparation creates output directories first. Do not claim a skipped native suite passed. Broaden to adapter/gateway E2E only after confirming its temporary home, fake providers and no production access; inspect `tests/test_gateway_e2e.py` before enabling it.

If toolchain is available, build exact board `esp32s3-touch-amoled-175c` via `PLATFORMIO_BUILD_DIR=$PWD/build/interaction-v1-esp32 .venv/bin/python -m platformio run --project-dir firmware/esp32 -e esp32s3-touch-amoled-175c`. Provision only a candidate-local toolchain if needed; no system upgrade. Record failure/blocker honestly. Preserve 10%-free smallest-slot gate; no partition changes. A build is not a physical test. Shared firmware changes need full board CI coverage before release, not falsely represented by this one build.

Update `docs/using-gadget.md`, `docs/protocol.md` for any protocol changes, and `docs/development.md` with reproducible new test instructions. New guide registration is needed only if adding a top-level published guide; this plan lives in docs/plans. Preserve licenses/credit; add no vendor material without notices. Run `git diff --check` and review final diff for unrelated changes.

Required report `~/Documents/Research/tiny-interaction-review/implementation/OPUS-REPORT.md`: requirements matrix, all changed files, red/green exact outcomes, skipped/failed checks, screenshots/contact sheet, fixture inputs, environment and source hashes, rerun commands, firmware budget if built, compatibility/physical limits, and remaining M3–M5 gates. Save candidate diff including new-file inventory. No commits, merging, live installation or claiming activation.

## M3 — Durable Work and structured results (next software release)

**Dependency:** M1/M2 verified plus trace of existing host persistence/session ownership; do not create a second general task orchestrator.

Discovery anchors: `plugin/store.py`, `plugin/hub.py`, `plugin/adapter.py`, `plugin/protocol.py`, current firmware app/model, simulator fixtures. Propose new modules only after checking existing storage facilities. Specify immutable task identity, owner/device association, result revision, bounded history, retention/clear policy, confirmed stage, and unknown-after-interruption behavior. Reuse Hermes durable task records if available; document exact API before integration. Never store raw audio or secrets by default.

Then write failing provider-free restart/reconnect scenarios: result survives process/device restarts; old device cannot read another's result; no replay on reconnect; changed result doesn't steal reading position; history eviction/corruption recovery; unknown execution stays unknown. Implement one compact Work shelf with cursor-based/bounded transport, short structured result and full artifact reference. Schema must preserve caveats; no ungrounded automatic firmware summary. Legacy peer compatibility is required.

Opus initial run delivers the concrete M3 contract/discovery notes, not a fake persistent demo claimed as completed host integration.

## M4 — Structured Review and authenticated continuation

**Dependencies:** M3 stable identifiers; actual authenticated Desktop/mobile client APIs located and separately scoped. Other repositories are not authorized by this local commission.

Trace `plugin/adapter.py` command approvals and downstream resolver before any change. Define execution-bound action/revision/owner/expiry semantics, ordinary-question compatibility, unsupported-glyph fallback, exact target presentation and replay defense. Define a genuine destination acknowledgement with task/result/reading anchor; never send sensitive data or bearer credentials in a visible URL/QR. No automatic posting into an unrelated main chat.

E2E before code: replaced prompt + stale contact, two surfaces authorize same action, expired/unpaired request, wrong owner, unavailable/locked destination, interruption after send before receipt, old revision, failed transfer keeps recoverable source. No live purchase/send/delete fixture. No simulated endpoint is sufficient to claim real Desktop handoff.

Initial run: write integration boundary and acceptance specification, identify exact missing host/client APIs and scope approvals. Do not bypass absent authentication with local-trust assumptions.

## M5 — Conversation mode and tactile hardware

**Voice dependencies:** M1 controls and heard-playback accounting; measured microphone/speaker behavior; approved existing provider route. Prototype explicit opt-in session, visible capture and easy exit, adjustable end-of-turn behavior, local immediate interruption, and independent task lifecycle. First write acoustic/provider-free input fixtures for pauses, first syllable, double talk, backchannels, turn boundary and disconnect. Real acoustic validation and any confidential speech-provider change require separate approval. No wake word by default; no pseudo-full-duplex UI over a half-duplex pipeline.

**Hardware program:** full-size 2.8–3.2-inch circular and wide rounded-rectangle prototypes, weighted angled base, separate Talk/Silence, latching electrical mic-off and only justified fixed-purpose volume control. Require exact schematics/parts and licensing before new board definitions; follow CONTRIBUTING and hardware-validation. Do not map unavailable controls into current board caps. Camera/motor/battery are not default requirements. Fabrication/procurement/flashing are separate authorized actions.

Acceptance targets, not measured claims: local feedback p95 <=100ms, acoustic Silence p95 <=150ms, simple no-tool first-useful audio p50 <=1s/p95 <=2.5s, status recognition >=95% within two-second exposures at intended 50–80cm, exploratory 9–12mm targets, zero unintended authorization/duplicate execution in defined adversarial fixtures. Actual physical studies must measure these; native tick timing and pixel tests cannot.

## Completion and continuation

M0–M2 complete means a working same-board candidate with source changes, real native end-to-end evidence, updated docs, compatibility limits and a reviewable diff—not a plan-only response. A blocked firmware toolchain does not block native work. A blocked physical capability is labeled, not fabricated. M3–M5 remain openly tracked until their host/client/hardware dependencies are resolved and real workflows pass.

Janus reads the report, inspects the diff and reruns key workflows before integrating. Successful CLI exit alone is not acceptance. This plan does not authorize shipping or certify hardware.
