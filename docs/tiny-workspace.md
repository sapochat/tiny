# Tiny workspace and Git checkpoints

Workspace: `/home/santi/projects/tiny/`.

## Repository map

| Directory | Branch | Role |
|---|---|---|
| `hermes-gadget-sdk-tiny-swipes` | `tiny/state-aware-swipes` | Preserved swipe baseline; central local firmware repository |
| `hermes-gadget-sdk-tiny-mic30` | `tiny/mic-gain-30db` | Microphone candidate; linked worktree of swipes |
| `hermes-gadget-sdk-tiny-unread` | `tiny/unread-reply` | Reply-indicator candidate; linked worktree of swipes |
| `hermes-gadget-sdk-tiny-amoled` | `tiny/round-amoled` | AMOLED candidate; separate clone |
| `hermes-gadget-sdk-tiny-expressions` | `tiny/expressions` | Expression-animation firmware candidate; separate clone |
| `tiny-animations` | `main` | Independent video-production source repository |

The central repository holds local branches for all firmware candidates, including
copies of the AMOLED and expressions branches. Both separate clones use the
central repository as their local `origin`. Their candidate branches track the
matching branch there. Existing upstream GitHub and `checkpoint` remote URLs in
the central repository are unchanged. No remote publication is part of this setup.

## Preserved source checkpoints

- Swipe baseline: `ac9a6d5e7431e86c520c55ed152cb9e8d49f77a8`
- Microphone: `b64f03566a4c724d9e7c3591d06abdea57885a4f`
- Unread reply: `a7c3c42629d34a57a2eb3722214cc92e5b16d583`
- Round AMOLED: `e6044d6e7f7c220dadc577d1e1ac25dd632af788`
- Expressions, before this navigation document: `ed4ec36ba10437da6ca3d36a9c383de03624b7e4`
- Animation sources: `91052d65c1bfc364f06e347a6f9ca61e176463a5`

These preserve the pre-existing working files. They are parallel snapshots from
the swipe baseline, not a fabricated sequential merge history. No variants were
merged, no firmware source was rewritten, and no new device validation is implied.
The expressions directory is the expression candidate, not a claim about which
firmware is currently flashed or production-ready.

## Day-to-day work

Work in the directory matching the feature. Stage specific paths and inspect
`git diff --cached` before committing. Keep build directories, private operator
state, and generated evidence excluded by the existing ignore rules. Use fresh
build environments after relocation: old virtual environments, build caches, and
historical evidence scripts may retain the previous absolute paths.

After committing changes in the separate AMOLED or expressions clone, refresh
its branch in the central repository locally (these commands refuse a
non-fast-forward update rather than rewriting history):

```sh
cd /home/santi/projects/tiny/hermes-gadget-sdk-tiny-swipes
git fetch ../hermes-gadget-sdk-tiny-amoled tiny/round-amoled:refs/heads/tiny/round-amoled
git fetch ../hermes-gadget-sdk-tiny-expressions tiny/expressions:refs/heads/tiny/expressions

# Refresh each clone's view of the central branches.
git -C ../hermes-gadget-sdk-tiny-amoled fetch origin
git -C ../hermes-gadget-sdk-tiny-expressions fetch origin
```

The microphone and unread worktrees already share the central object database;
they need no import. Do not force-update a divergent branch; inspect it first.
Remote GitHub publication requires a separate decision about destination and
branches. A local commit is not an off-machine backup.

## Verification and limits

The setup verified committed blob hashes against the original selected files,
clean Git status, branch identities, worktree links, local remote connectivity,
and object integrity. The staged changes passed `git diff --cached --check` and
a basic credential-pattern scan; this is not a full security review.

Repeat the structural checks without executing firmware or paid generation jobs:

```sh
cd /home/santi/projects/tiny
for repo in hermes-gadget-sdk-tiny-* tiny-animations; do
    git -C "$repo" status --short --branch
    git -C "$repo" fsck --full --no-dangling || exit 1
done
git -C hermes-gadget-sdk-tiny-swipes worktree list
git -C hermes-gadget-sdk-tiny-swipes branch -v
```

No application tests, simulator runs, paid media generation, or physical-device
tests were performed for this Git-only setup. Generated media and ignored
firmware artifacts remain on disk and are **not** backed up by these commits.
See `tiny-animations/README.md` in the sibling animation repository for its
source allowlist and portability limitations.
