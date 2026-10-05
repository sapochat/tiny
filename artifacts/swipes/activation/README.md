# Tiny OTA trial — installed and reconnected

> Historical activation report; subsequently the user confirmed the firmware
> works well physically. That is a usability confirmation, not an exhaustive
> hardware acceptance run. See [../CHECKPOINT.md](../CHECKPOINT.md).
> Only redacted digest/completion/stability receipts are committed under
> `../checkpoint/`; raw device status, install scripts and observations stay local.
> Device identifier below is redacted in this repository copy.

This activation supersedes the earlier `../README.md` statement that Tiny was untouched. User approved a settings-preserving single candidate app-only OTA and resulting device reboot. No gateway restart, plugin/config change, factory erase, merged-image flash, pairing change, or settings command was performed.

## Result

- Target: `[device-id-redacted]`, name `Tiny`, image board `esp32s3-touch-amoled-1.75c` (175c / 32MB).
- Native authenticated `hermes gadget update` completed with exit 0, all 1,273,552 bytes acknowledged, then gateway status `done` at Unix timestamp `1791215917.9289`. Single invocation; no observed retry or failure; staged metadata attempts remained 0.
- Captured exact staged image SHA-256 before the gateway removed the completed queue entry: `00f90b6a52d86f77c8e02de7e3130ca2e00906fef3da742b3d65111359361c17`.
- Tiny reconnected as the same paired identity/name/board. First post-install observation showed connection age 4 seconds. Final observation showed 328 seconds, increasing monotonically across 19 stability observations. Gateway PID remained `984188`.
- Final telemetry retained external power 1, battery present 0, fresh sensor/receive timestamps. Queue receipt remained `done`, with no pending image.
- Both stock and candidate report version `0.2.0`: **version alone is not installation evidence**. Identification is captured staged bytes/hash + native hash-checked OTA completion + new stable connection.

## Exact artifacts

Candidate (installed):
`/home/santi/hermes-gadget-sdk-tiny-swipes/artifacts/swipes/firmware/hermes-gadget-esp32s3-touch-amoled-175c-0.2.0-app.bin`

SHA-256: `00f90b6a52d86f77c8e02de7e3130ca2e00906fef3da742b3d65111359361c17`

Stock recovery (retained, NOT installed):
`/home/santi/hermes-gadget-sdk-tiny-swipes/artifacts/swipes/activation/recovery/hermes-gadget-esp32s3-touch-amoled-175c-0.2.0-app.bin`

SHA-256: `3d592d1dc0f54153759f8bf991dad663e5abf441b21c0d86cac3d1cf24aa9f2e`

Source: https://github.com/Adolanium/hermes-gadget-sdk/releases/download/v0.2.0/hermes-gadget-esp32s3-touch-amoled-175c-0.2.0-app.bin

Official release: https://github.com/Adolanium/hermes-gadget-sdk/releases/tag/v0.2.0

Retained release API metadata, manifest and SHA256SUMS under `recovery/`. Downloads matched GitHub asset digests; candidate and recovery matched their respective manifest sizes/hashes and checksum files. Installed plugin `ota.inspect_image` verified project/board/version of both app images. Manifest selects ESP32-S3, 32MB, octal PSRAM.

Also retained official stock merged image `recovery/hermes-gadget-esp32s3-touch-amoled-175c-0.2.0.bin`, SHA-256 `6805f5e13a73e4adaf2ed901615f6490607f6f8e95139f10292440f0c0b066ac`. **Do not flash it at address 0: that erases settings.** It is retained for the documented settings-preserving browser-installer route with its matching manifest if USB recovery is later needed.

## Recovery and safety basis

The reviewed installed plugin `ota.py` authorizes OTA using the paired key, fresh nonce, image digest and size; firmware checks full received size/hash before selecting the new boot partition. `firmware/esp32/main/port_ota.cpp` writes the inactive app slot and does not write NVS. Its new-image confirmation timer permits five minutes to reach Hermes before rollback; core `App::h_welcome` confirms on handshake. Build configuration enables bootloader rollback. Physical rollback was not fault-injected.

A later explicitly approved recovery, if Tiny remains reachable, can use the native updater with the retained stock **app** path above. Do not run another update merely because labels match. If unreachable and rollback does not recover it, USB/data-cable access and a settings-preserving installer route need user physical assistance. USB was not connected for this trial. There is no backup of the previously running flash, so the retained official stock release cannot be claimed byte-identical to the original installed image.

## Evidence index

- `preflight.json`, `before-status.json`: image verification, exact target, pairing, power and empty queue.
- `ota-invocation.json`: exact command, target and candidate digest. Exclusive marker prevents accidental script rerun.
- `exact-staged-image.json`: queue metadata plus hash and size computed from actual staged bytes.
- `queue-observations.jsonl`: persisted progress/digest linkage through completion and queue removal.
- `update.log`, `cli-result.json`: actual native CLI output and exit status.
- `receipt-readback.json`: readback of exact target status file after completion.
- `after-status.json`: first post-reboot paired connection.
- `reconnect-observations.jsonl`, `stable-status.json`, `verification.json`: stability beyond five minutes.
- `preflight.py`, `install_once.py`, `verify_stability.py`: exact executed evidence scripts. Do not rerun installer without new authorization; the invocation marker deliberately blocks it.

## Evidence limits / remaining physical check

The remote protocol does not expose running-app hash, boot-slot/probation state or a serial startup log. The reported installation uses the OTA evidence chain above, not independent running-flash attestation. Wi-Fi reconnection, pairing, identity and name survived; brightness/volume/other persisted values are not exposed by debug status and were not physically compared.

Physical swipe ergonomics, screen rendering, audio and microphone remain unverified. Ask the user to try Home down → controls, right → Home; Home up → retained response if available, right → Home. Start movement promptly because stationary hold is push-to-talk. Do not claim on-device usability from the successful install or native-simulator tests.

Minor preparation discrepancy: `hermes gadget info` printed `platform enabled: False` despite a healthy live debug hub. Live PID/status and actual native OTA completion establish runtime availability; no configuration was changed to resolve the stale/default CLI view. A generic Python import of Hermes core failed because that interpreter did not include it; preflight loaded only installed plugin image/queue helpers using stdlib imports, while the actual update used the native Hermes CLI.
