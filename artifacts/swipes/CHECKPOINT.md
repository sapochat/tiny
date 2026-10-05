# Tiny working-firmware checkpoint

Private repository: https://github.com/sapochat/hermes-gadget-tiny

Checkpoint tag: `tiny-swipes-20261005`. The commit resolved by this annotated tag
is the checkpoint source commit (`git rev-parse tiny-swipes-20261005^{commit}`).
The release body records its full SHA. This is an independent private repository,
not a GitHub fork. Upstream history, attribution and licenses are retained from
https://github.com/Adolanium/hermes-gadget-sdk at
`323e3303ab68981f810fc3208119cd8a22e64af0`.

## Identity and validation

Board: **esp32s3-touch-amoled-175c**, ESP32-S3, 32 MB flash, octal PSRAM.
Both images report **0.2.0**; no version bump was made after building. Use hashes,
not version labels. The user confirmed working physical usability after OTA;
this is not exhaustive testing of every gesture, hardware feature or rollback.

- Installed candidate app SHA-256:
  `00f90b6a52d86f77c8e02de7e3130ca2e00906fef3da742b3d65111359361c17`
- Official recovery app SHA-256 (retained, not flashed):
  `3d592d1dc0f54153759f8bf991dad663e5abf441b21c0d86cac3d1cf24aa9f2e`
- Candidate merged USB image:
  `5c7551a817421041698fe2011f420a5226bc1af3f1e2f9181b6ebf7a0fc991a0`
- Official recovery merged USB image:
  `6805f5e13a73e4adaf2ed901615f6490607f6f8e95139f10292440f0c0b066ac`

Official recovery provenance:
https://github.com/Adolanium/hermes-gadget-sdk/releases/tag/v0.2.0
(app asset `hermes-gadget-esp32s3-touch-amoled-175c-0.2.0-app.bin`).
The recovery is the official same-board release, not a dump of the previous flash.

The OTA evidence links exact staged bytes/hash to successful authenticated,
hash-checked completion and a stable paired reconnect over five minutes. There
is no independent running-flash hash attestation or fault-injected rollback test.

Recorded final suite: **139 passed, 30 skipped**, including **22 gesture E2E**;
CTest passed, exact-board build passed, site tests **29 passed** and site build
completed. At checkpoint, the **22 gesture E2E tests were rerun and passed**.
All 17 frozen source-snapshot files matched current code byte-for-byte before
commit. `checkpoint/source-input-sha256.json` records those inputs.

## Evidence and release assets

`README.md` and `activation/README.md` are historical stage reports with prominent
checkpoint corrections. `checkpoint/` contains final build/test logs, JUnit,
config/lock/environment, source hashes, release-asset manifest, and redacted
staged-image/completion/stability receipts. Paths in copied logs/environment are
redacted; raw local evidence is retained but not uploaded.

The private release contains exact candidate/recovery app and merged images,
the candidate license archive, original candidate/recovery manifests and checksum
files (prefixed `candidate-` / `recovery-` to avoid name collisions), and a combined
`SHA256SUMS`. Original manifests describe original unprefixed names; the combined
manifest is authoritative for the renamed release downloads. Verify downloads:

```sh
sha256sum -c SHA256SUMS
```

Binaries are release assets, not committed build directories. No pairing keys,
credentials, private operator config, raw chats, raw device-status dumps, caches,
venvs, node_modules or intermediate screenshots are intentionally included.
Actions are disabled at repository level before the first push; Pages is not
configured. Original upstream workflow source is retained but does not execute.

## Rerun without a device or live provider

Install development dependencies and build prerequisites from the upstream setup
instructions and `checkpoint/environment.json`; use the recorded build lock and
sdkconfig for investigating rebuild differences. From the checkout:

```sh
PATH="$PWD/.venv/bin:$PATH" .venv/bin/hermes-gadget build-sim --test
HERMES_AGENT_DIR=/nonexistent HERMES_GADGET_UI_TESTS=1 \
  xvfb-run -a .venv/bin/pytest tests/test_touch_navigation.py \
  --basetemp="$HOME/.cache/tiny-tests" -q --tb=short
# Omit the test-file argument to run the broader suite.
(cd firmware/esp32 && PATH="$PWD/../../.venv/bin:$PATH" \
  ../../.venv/bin/pio run -e esp32s3-touch-amoled-175c)
(cd site && npm ci && npm test && npm run build)
```

Build timestamps/paths may prevent byte-identical rebuilds; preserve the released
bytes to identify the installed image. No flashing or runtime changes were made
while creating this checkpoint. Future recovery requires separate authorization.
Never flash the merged image at address zero casually: this erases settings; use
an explicitly approved settings-preserving documented route.
