#!/usr/bin/env python3
"""Endpoint snapping: make a clip begin EXACTLY on start anchor and end EXACTLY on end anchor.
Blends the first/last K frames from the exact anchor into the clip (smoothstep), so chained clips have zero seam.
Usage: snap.py in.mp4 start.png end.png out.mp4 [--size 720] [--k 6] [--reverse]
Reports residual seam (mean abs diff, 0-255) before snapping."""
import sys, subprocess, json, argparse
import numpy as np
from PIL import Image

ap = argparse.ArgumentParser()
ap.add_argument("inp"); ap.add_argument("start"); ap.add_argument("end"); ap.add_argument("out")
ap.add_argument("--size", type=int, default=720); ap.add_argument("--k", type=int, default=6)
ap.add_argument("--reverse", action="store_true"); ap.add_argument("--fps", type=int, default=24)
a = ap.parse_args(); S = a.size

raw = subprocess.run(["ffmpeg", "-v", "error", "-i", a.inp, "-vf", f"fps={a.fps},scale={S}:{S}:flags=lanczos",
                      "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True, check=True).stdout
F = np.frombuffer(raw, np.uint8).reshape(-1, S, S, 3).astype(np.float32)
if a.reverse: F = F[::-1]
ld = lambda p: np.asarray(Image.open(p).convert("RGB").resize((S, S), Image.LANCZOS), np.float32)
A0, A1 = ld(a.start), ld(a.end)
rep = {"frames": len(F), "seam_start_before": float(np.abs(F[0] - A0).mean()), "seam_end_before": float(np.abs(F[-1] - A1).mean())}
k = min(a.k, len(F) // 3)
for i in range(k):
    t = i / k; w = 1 - (t * t * (3 - 2 * t))  # weight of anchor: 1 -> 0
    F[i] = w * A0 + (1 - w) * F[i]
    F[-1 - i] = w * A1 + (1 - w) * F[-1 - i]
F[0] = A0; F[-1] = A1
out = np.clip(F, 0, 255).astype(np.uint8)
p = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{S}x{S}", "-r", str(a.fps),
                      "-i", "-", "-c:v", "libx264", "-crf", "12", "-pix_fmt", "yuv444p", "-preset", "slow", a.out], stdin=subprocess.PIPE)
p.stdin.write(out.tobytes()); p.stdin.close(); p.wait()
print(json.dumps(rep))
