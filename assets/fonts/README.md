# Embedded Geist font

Copyright 2024 The Geist Project Authors (https://github.com/vercel/geist-font).
SIL Open Font License 1.1; full text: `../../LICENSES/Geist-OFL.txt`.
The atlas remains OFL font data; the renderer is original project code.

`Geist-Regular.ttf` is **Version 1.800**, extracted byte-for-byte from the
user-approved face-first `tiny-premium-preview/index.html` embedded font.
SHA256: `ccce59465ae5c61930ada5453834f60500fbd95084d85db63e0e65fad0125455`.
This exact file, rather than a moving upstream download, is the reproducible
source of the embedded atlas. The approved HTML and gallery are frozen under
`artifacts/face-first/reference/`. Upstream attribution and licensing come from
https://github.com/vercel/geist-font; the license text was retrieved from the
pinned `1.4.2/OFL.txt` tag (the font's internal version is independently 1.800).

Regenerate offline with `.venv/bin/python tools/build_geist.py` (Pillow 12.3.0).
`manifest.json` records version, input/output hashes, glyph inventory and sizes.
The four sizes are 14, 18, 24 and 30 pixels (17 was folded into 18 to reclaim flash). Coverage has 16 levels, encoded
as one-byte runs (high nibble = length minus one, low nibble = coverage).
No runtime font file, font engine, download, texture allocation or glyph cache
is required. Each draw decodes directly into the existing RGB565 framebuffer.

The inventory includes ASCII, Latin-1 and selected typographic punctuation and
navigation arrows. Unsupported Unicode scalars render a visible replacement
glyph, not a silent deletion; source UTF-8 remains intact in wrapped lines.
This is not full Unicode shaping, bidi or CJK support. Advances are integer
hinted per-glyph measurements, without browser subpixel positioning or kerning.
Those are genuine embedded differences from the approved browser reference.
