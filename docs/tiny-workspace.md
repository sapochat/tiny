# Tiny: canonical workspace

Work in `/home/santi/projects/tiny`, on `main`. This is now one Git repository, not a container of firmware candidates.

## Layout

- `firmware/`: ESP32 firmware, portable C++ core, and simulator.
- `python/`, `plugin/`, `linux/`, `site/`: inherited SDK tooling and integrations.
- `animations/`: video-production source scripts, reference inputs, and recipes; tracked by the root repository, not a nested repository.
- `tests/`, `tools/`, `assets/`, `docs/`: tests, supporting tools, assets, and documentation.
- `IDEA.md`: original Tiny concept.

## Selected baseline

The expressions checkout at `c79b62c44e8221a12864f934f56f1b68a9b0f04b`, plus all its tracked modifications and non-ignored untracked source files, is the canonical development baseline. This includes the face-first UI, Geist font assets, touch updates, and associated tests/report tools. No product source was rewritten during consolidation.

The other firmware candidates are parallel snapshots from the swipe baseline, not successive releases. They remain available as branches rather than being blindly merged. "Latest" means this selected development working tree, not the firmware currently flashed on a device or a verified release.

## Retained history

Full original firmware history is retained. Local branches preserve:

| Branch | Original checkpoint |
|---|---|
| `archive/main` | `323e330` (upstream baseline) |
| `archive/tiny/state-aware-swipes` | `ac9a6d5e7431e86c520c55ed152cb9e8d49f77a8` |
| `archive/tiny/mic-gain-30db` | `b64f03566a4c724d9e7c3591d06abdea57885a4f` |
| `archive/tiny/unread-reply` | `a7c3c42629d34a57a2eb3722214cc92e5b16d583` |
| `archive/tiny/round-amoled` | `e6044d6e7f7c220dadc577d1e1ac25dd632af788` |
| `archive/tiny/expressions` | `c79b62c44e8221a12864f934f56f1b68a9b0f04b` |
| `archive/animations` | `91052d65c1bfc364f06e347a6f9ca61e176463a5` |

Animation sources are copied into `animations/`; their original independent history remains on `archive/animations` (not fabricated as firmware ancestry).

## Archive and recovery

The complete former workspace is retained at:

`/home/santi/projects/tiny-archive-20261005-211341/`

It includes all original checkouts, the old parent README, uncommitted files, ignored generated media, build outputs, and virtual environments. Linked worktrees and local clone remotes were repaired to refer to this archive. No candidate directories were deleted. `consolidation-before.json` records original revisions, statuses, and source SHA-256 hashes. `consolidate.py` records the migration procedure; it is a one-shot historical script, not a command to rerun.

The root checkout is an independent clone with copied source files, not a symlink to the archive. `source-archive` is its only configured remote and points locally to the archived expressions clone. No GitHub publishing destination is configured in the new checkout, and nothing was pushed. Local copies are not off-machine backups.

To recover a candidate, inspect its `archive/*` branch in a new worktree. To recover uncommitted or generated material, copy the required files from the sibling archive. Do not overwrite the new working tree or delete the archive as a cleanup shortcut.

## Builds, media, and verification limits

Use fresh build directories and environments at the root; relocated old build caches and virtual environments may embed stale absolute paths. They were deliberately not copied here. Existing generated expression/font headers are included.

Ignored videos and render evidence remain in the archive, not in Git or the new `animations/` directory. Historical recipes and report scripts may retain absolute paths to earlier workspaces. Media regeneration and archived environment executables are **not** claimed portable. The animation runner can spend money; do not use generation as a smoke test.

This consolidation verifies source preservation and Git integrity, not firmware correctness, simulator behavior, or physical hardware readiness. No live services were restarted, devices flashed, paid jobs run, or product behavior altered by the consolidation itself.

Routine structural checks:

```sh
cd /home/santi/projects/tiny
git status --short --branch
git fsck --full --no-dangling
git branch -v
git diff --check
```

For application development and tests, see [development.md](development.md). Review scripts and fixture safety before running hardware, network, or media-generation checks.
