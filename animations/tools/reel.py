#!/usr/bin/env python3
"""Labeled round-masked 466px reel. Usage: reel.py <out.mp4> <clip.mp4>|<label> ...  (paths relative to project root)"""
import sys, subprocess, pathlib
from PIL import Image, ImageDraw
root = pathlib.Path(__file__).resolve().parents[1]
mask = root / "ref/round-mask-outline-466.png"
if not mask.exists():
    m = Image.new("RGBA", (466, 466), (0, 0, 0, 255)); d = ImageDraw.Draw(m)
    d.ellipse([0, 0, 465, 465], fill=(0, 0, 0, 0)); d.ellipse([0, 0, 465, 465], outline=(70, 70, 70, 255), width=2)
    m.save(mask)
out = sys.argv[1]; items = [a.split("|", 1) for a in sys.argv[2:]]
inp, fl, cat = [], [], ""
for i, (p, lab) in enumerate(items):
    inp += ["-i", str(root / p)]
    lab = lab.replace("'", "").replace(":", " ")
    fl.append(f"[{i}:v]fps=30,scale=466:466,setsar=1,setpts=PTS-STARTPTS[s{i}];"
              f"[s{i}][{len(items)}:v]overlay=0:0:shortest=1,pad=466:506:0:40:black,"
              f"drawtext=text='{lab}':x=12:y=10:fontsize=22:fontcolor=white[v{i}]")
    cat += f"[v{i}]"
# one image input per clip use: reuse the same mask by listing it once per overlay via movie filter is fiddly; add N copies
for _ in items:
    pass
fc = ";".join(fl)
# each overlay consumes the mask stream; give each its own input copy
inp2 = list(inp)
for i in range(len(items)):
    inp2 += ["-loop", "1", "-i", str(mask)]
fc = ";".join(f.replace(f"[{len(items)}:v]", f"[{len(items) + i}:v]") for i, f in enumerate(fl))
fc += f";{cat}concat=n={len(items)}:v=1:a=0[o]"
subprocess.run(["ffmpeg", "-v", "error", "-y", *inp2, "-filter_complex", fc, "-map", "[o]", "-c:v", "libx264",
                "-pix_fmt", "yuv420p", "-crf", "18", "-movflags", "+faststart", out], check=True)
print(out)
