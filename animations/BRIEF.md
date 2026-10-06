# Tiny Animations — brief

**Goal:** a higher-quality, more expressive set of animated states for Tiny (round 466×466 AMOLED), using the existing Hermes mascot. Video assets only — firmware/code integration is out of scope for this stream.

## Non-negotiables
- **Same mascot.** The Nous/Hermes girl from `ref/original-1024.png`: asymmetric curled hair silhouette, heavy jagged bangs, white headband arc and highlight architecture, half-lidded lash-heavy eye, restrained mouth, earring, flat two-tone black/white negative-space style. No redesigns, no color, no gradients, no shading, no photorealism.
- **Pure black background** (AMOLED true black), no text, no logos, no new objects.
- **Round-safe framing.** Masters are square 1:1; everything important lives inside the inscribed circle (`ref/neutral-roundsafe-1440.png` is the canonical framing).
- **Chainable.** Every clip begins and ends on a defined anchor frame (neutral, or the state's hold pose) so playback can switch states without visible jumps. Final assets get pixel-snapped ends in post.

## State set (v1 proposal)
| State | Trigger | Shape | Motion budget |
|---|---|---|---|
| Idle | nothing happening | loop (exists on Tiny: blink) | minimal |
| Wake / noticed | wake word / tap | entry, ends in listening | medium |
| Listening | mic open | loop | low–medium |
| Thinking | waiting on model/tools | loop | medium |
| Speaking | TTS playing | loop | medium (generic, not lip-sync) |
| Reply ready / pleased | turn complete | entry + hold | medium |
| Asking / approval | approval prompt | entry + hold | low–medium |
| Confused / error | failure | entry + exit | medium |
| Sleep | display dimming | entry + loop | low |

## Production method (what the earlier session proved)
1. **Keyframe first.** Generate each state's hold pose as a still edited from the canonical neutral (Nano Banana Pro preserved structure best; GPT Image redraws drift).
2. **Animate between anchors.** Video model with `start_image` / `end_image` (neutral→state, state→state loop, state→neutral). Asking a model to "be almost still" yields nothing readable; give it a visible destination.
3. **Post.** Snap first/last frames to the exact anchor PNGs, crossfade where needed, export 466 and 192 previews, contact-sheet QA.

Known failure modes: unsolicited blinks (Seedance), prolonged eye closure (Kling), silhouette/hair contour drift, model starting already in the end pose, requested resolution ≠ delivered.

## Layout
- `ref/` — canonical source + anchors
- `rounds/rNN-*/` — each generation round: requests, results, downloads, contact sheets, REVIEW.md
- `picks/` — approved masters per state
- `schemas/` — live Higgsfield model schemas
