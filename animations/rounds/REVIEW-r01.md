# r01 — keyframes + motion bakeoff

Spend: ~700 credits (16 stills, 8 videos). Balance after: 3424.

## Keyframes (`r01-keyframes/board.png`)
Nano Banana Pro vs Grok Image 2.0, 8 states, edited from `ref/neutral-roundsafe-1440.png`.

- **Nano Banana Pro holds identity much better.** Silhouette IoU vs neutral was 0.93–0.97 for NBP and 0.45–0.90 for Grok; Grok reshapes the face and jaw and shifts the framing.
- Clear NBP winners: **alert, pleased, sleeping, speaking**.
- Weak: **listening** (reads as neutral), **asking** (looks smug), **thinking** (NBP reads as skeptical; Grok's upward glance reads better).
- Neither model added color, gray or text.

## Motion bakeoff (`r01-motion-bakeoff/grid-labeled.mp4`)
Start = end = neutral. Two performances (delight, listen) × Kling 3.0 pro, Seedance 2.0, Seedance 2.5 (omni_reference), Wan 3.0 Prime. All return 1440×1440. Evidence: `vqa.json` and `strip-*.png`. These are sampled-frame reviews only (`video_analyze` is unavailable on the current provider).

| | delight | listen | endpoint fidelity (MAD vs anchor) |
|---|---|---|---|
| Seedance 2.0 | **best**: restrained, on-model, sustained smiling eyes; small earring/ear redraw | engaging, but redraws the face more frontally, eyelid narrowing, slightly toothy | ~0.5 (tight) |
| Wan 3.0 Prime | strongest bob, but overshoots: biggest redraw, open-looking grin | **best**: clear tilt/nod with eyes kept on the viewer, no blink | 0.5 first, 0.75–0.8 last |
| Kling 3.0 pro | clear smile, but the hair flares too wide | weakest: mostly an eye-closed dip (the same long-closure habit as before) | ~0.5 (tight) |
| Seedance 2.5 | readable, stable design, slight tooth slit | under-expressive, late blink | **1.5–2.9 (loose)**: omni_reference doesn't pin frames |

**Takeaways**
1. Once motion is allowed, all models produce readable states. The earlier failures came from asking for near-stillness.
2. Use **Seedance 2.0 + Wan 3.0 Prime** as the working pair. Drop Kling (habitual eye closure). Seedance 2.5 only works with start/end in omni_reference mode, and it misses the endpoints.
3. Every model still tends to add stray blinks and tooth slits. Post-processing needs endpoint snapping and possibly local eye/mouth fixes.

## CLI notes
- The account allows 8 concurrent jobs. The runner backs off on `rate_limit_reached` and 503 errors.
- `seedance_2_5` requires `--mode omni_reference` for start/end images.
