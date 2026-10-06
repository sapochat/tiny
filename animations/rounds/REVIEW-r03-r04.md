# r03 (entries) + r04 (exits, holds, v2 fixes) + first chained demo

Spend: r03 4×Seedance (180 credits) + r04 7×Seedance + 3×Wan (405 credits) = 585 credits.
(The account also shows 3× "Genjutsu Motion Transfer" at 308 credits each around 14:37 PDT. That spend is not from this stream.)

## r03 — Seedance entries from the new stills (`r03-entries/strip.png`)
Ranking: thinking 9 > listening 8 > confused 7 ≈ asking 7.
- **thinking**: chin lifts, eyes go up and away, small pout. The clearest state in the set. Keep.
- **listening**: turns frontal with a soft smile. Clear, but close to asking.
- **confused**: readable, but leans annoyed. Has a blink at 0.6s.
- **asking**: a pleasant waiting pose. The question itself is under-signalled. Weakest.
- As in r02, the last frames sit 22–35 MAD from the target stills. Seedance invents its own end pose, so the last frames become the anchors (`ref/anchors/*-hold-1440.png`).

## r04 — exits, holds, v2 fixes
Seams = MAD (0–255) vs the declared anchor.
| clip | end seam | verdict |
|---|---|---|
| exit-alert seedance / **wan** | 3.7 / 1.5 | Seedance ends with eyes closed (fails). **Wan wins.** |
| exit-pleased **seedance** / wan | 0.24 / 1.3 | **Seedance**: a clean smile fade. Wan widens the grin first. |
| exit-sleeping seedance / **wan** | 16.2 / 1.3 | **Wan**: the wake-up is more gradual and lands on neutral. |
| hold-pleased seedance | 0.26 | Pass: gentle sway, smile stable. |
| hold-sleeping seedance | 0.25 | Mostly pass: breathing reads, but the mouth parts mid-loop. |
| enter-alert-v2 | 0.21 | No real head lift. The mouth is still not a clean dark "o" (tooth-like detail). |
| enter-pleased-v2 | 0.32 | Still closes the eyes. "Eyes open" does not survive Seedance. |

**Pattern: exits want Wan, entries want Seedance.** Wan's precise end-frame pinning matters most when returning to the shared neutral.

## Snapping and chaining (`tools/snap.py`, `tools/chain.py`)
- `snap.py` blends the first and last 6 frames into the exact anchor images (smoothstep).
- Raw seams before snapping were at most 1.85 MAD. After snapping, boundary frame-steps measure 0.10–0.13, the same as a static frame. **Seams are invisible by construction.**
- `chain.py` checks that each clip's start anchor equals the previous clip's end anchor.
- **Demo:** `picks/chain/day-in-the-life-v1-466.mp4`, 60s, 12 segments. Sequence: sleep, wake, listening, thinking in/out, speaking, reply-ready enter/hold/exit, alert enter/exit, fall asleep.
- The "thinking - resolve" segment is the entry played in reverse. It works mechanically, but reads as un-thinking rather than a resolution. It needs a real resolve clip ("got it" with a forward gaze and a small smile).

## New finding: the models animate on 2s/3s
Per-frame difference shows held drawings with periodic jumps (median step 0.1–0.3, spikes 12–20 every 2–3 frames):
- Seedance holds-in-3s, so about 8 effective fps.
- Wan at 30fps holds-in-2s, so about 15 effective fps.

This is anime-style limited animation. On a small round screen it can read as choppy.
- Test: `mpdecimate` + `minterpolate` (MCI) gives step median 3.1 and max 10. Vision QA rates it 8/10 clean: mild eyelid/temple shimmer, no ghosting.
- Comparison: `picks/chain/day-in-the-life-v1-466-smooth.mp4`.
- This is a taste call (anime limited animation vs fluid). For better quality, a real interpolator (RIFE on the local RTX 2000E) would beat ffmpeg MCI.
