# r02 — new stills, state entries, speaking loop

Spend: ~312 credits (6 stills, 8 videos). Balance after: 3112.

## Stills (`r02-states/board.png`)
Nano Banana Pro only, with stronger direction. Silhouette match vs neutral (IoU): 0.92–0.97.
- **Picks:** listening-b (warm "go on"), thinking-b (eyes up, recalling; not skeptical), asking-a (polite and expectant).
- Asking still reads more as "waiting" than "asking". A small open mouth would help.

## Entries (neutral → state) and speaking loop
Strip sheets: `strip-enter-*.png`, `strip-loop-speaking.png`.

| | Seedance 2.0 | Wan 3.0 Prime |
|---|---|---|
| pleased | **pick**: clean smile build and hold; eyes close fully (overshoot) | eyes stay soft, but the mouth wobbles mid-clip |
| alert | **pick**: clear wide-eyed "oh" that holds; slight tooth sliver | under-alert; simplified ear |
| sleeping | **pick**: half-lid, then closed by 1.7s, holds | slower, with more facial drift |
| speaking loop | **pick**: reads as talking; head and hair stable | more head and ear drift |

**Key technical finding: endpoint pinning.** Endpoint difference is mean absolute pixel difference on a 0–255 scale; lower means a closer match.

| | first frame vs neutral | last frame vs the end keyframe |
|---|---|---|
| Wan 3.0 Prime | 0.07 | 0.67–0.85 (lands on the keyframe almost exactly) |
| Seedance 2.0 | 0.2–1.1 | **14–28 (does not land on our keyframe)** |

Seedance takes the end image as a suggestion and finishes on its own version of the state. When start and end are the same image (loops), it holds them tightly (~0.2–0.5).

**Workflow consequence:** let the Seedance entry clip *define* each state's anchor. Extract its final frame, then generate that state's hold loop (start = end = anchor) and its exit (anchor → neutral) from it. Use Wan only where an exact predefined end pose matters.

## Picks so far
`picks/reel/reel-v1-466.mp4`: round-masked, labeled, 466px. Covers alert, listening (Wan r01), speaking, reply-ready, delight, sleep.
