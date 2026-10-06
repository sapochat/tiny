# r05 — fixes + full state set v2

Spend: 477 credits (6 Nano Banana Pro stills, 13 videos). Balance after: 1126.

## Strategy change: keyframe-driven Wan
The problem states (reply-ready eyes, alert teeth, asking) got a new keyframe still first:
- Nano Banana Pro edits from neutral. Silhouette match vs neutral (IoU): 0.93–0.96.
- Mouths are then fixed locally: enclosed white regions inside the mouth are flood-filled black (`ref/anchors/alerto-kf`, `askinghm-kf`). This gives a clean solid-black "o" with no teeth.
- Wan 3.0 Prime then animates neutral → keyframe → neutral. Wan pins both endpoints (MAD 0.8–1.1), so the corrected keyframe is exactly what shows on screen during the hold.

## Results
| state | pick | notes |
|---|---|---|
| idle (new) | Seedance loop | Very stable, one mid blink (possibly long). Wan turned the head too much. |
| thinking resolve (new) | Seedance | Eyes come down, small "got it" smile, settles. Replaces the reversed-entry hack. |
| alert | Wan enter + exit | Reaches alert by 1.1s, clean black "o", no teeth at the hold. The exit passes through a toothy mouth briefly (0.6–1.1s). |
| asking | Wan enter + exit | Quicker, more legible tilt. The final mouth is a tiny dark "hm?". The tilt relaxes before the hold. The exit has a blink. |
| reply-ready | Wan enter + exit | **The hold now has open eyes.** The entry still passes through a happy closed-eye squeeze (2.8–3.3s). The exit is a bit step-like. |
| speaking v2 (enthusiastic) | **rejected** | Seedance replaced the start frame with a frontal redraw (start MAD 34.7). Start/end mismatch, teeth. |

Seedance enter-alerto pinned its end frame (0.27) but was late and sluggish. Seedance enter-askinghm drifted (29.4) into a frontal smile.

## Deliverables
- `picks/chain/tiny-states-v2-466.mp4`: 70s, 14 segments, round-masked, labeled. All boundary steps measure 0.11–0.22 (static-frame noise), so no seams.
- `picks/chain/tiny-states-v2-466-smooth.mp4`: the same chain with MCI interpolation.
- `picks/chain/tiny-states-v2-466-clean720.mp4`: unlabeled, unmasked 720px.
- `picks/states-v2/NN-*.mp4`: individual snapped 720px clips, one per state or transition. Each starts and ends on its declared anchor.

## Remaining
- Reply-ready entry: the eye squeeze mid-clip. Options: a Wan retry with a stronger prompt, or trim the clip to its last ~2s (it holds open from 3.9s).
- Asking: hold the tilt into the end pose. Needs a tilted keyframe, as the current keyframe's tilt is weak.
- Exits briefly flash teeth while the mouth closes. A per-frame mouth fill in post is possible, since the mouth region is known.
- Smooth vs held animation: still undecided.
