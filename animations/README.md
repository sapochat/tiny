# Tiny animation sources

Animation source work described in [BRIEF.md](BRIEF.md), now tracked in the
root Tiny repository under `animations/`. Firmware lives at `../firmware/`.
Original independent Git history is retained on `archive/animations`.

## What is tracked

- `tools/*.py`: generation and post-production scripts.
- `schemas/*.json`: captured model schemas.
- `ref/`: canonical images and pose anchors.
- `rounds/**/jobs.json`: generation prompts and job settings.
- `rounds/REVIEW-*.md`: creative reviews.
- `picks/chain/chain-v*.json`: edit recipes.

Generated videos, contact sheets outside `ref/`, downloaded job outputs, logs,
API results, and render reports remain in the sibling archive described in
[workspace provenance](../docs/tiny-workspace.md), excluded from Git and not
copied into this source-only directory. Cloning does **not** restore that media.
Do not delete the archive on the assumption that Git backs up generated media.

## Working practice

```sh
cd ./animations
git status --short
git diff
# Stage specific source files, review, then commit.
git add tools/example.py
git diff --cached
git commit -m "Describe the animation-source change"
```

The initial commit is a source checkpoint, not a fresh generation or runtime
validation. Some recipes and historical records contain absolute paths from
before the workspace relocation; review those before running. The scripts also
retain machine-local tool/scratch paths. The generation runner invokes paid
Higgsfield jobs: do not use it as a smoke test.

The root repository has only a local archive remote. Nothing has been published
as part of consolidation. Review privacy, asset licensing, media storage, and
path portability before publishing or moving it to another machine.
