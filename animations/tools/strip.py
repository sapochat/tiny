#!/usr/bin/env python3
"""Rows-of-frames contact board for all mp4s in a round. Usage: strip.py <round_dir> [n_frames] [name_filter]"""
import sys, pathlib, subprocess, tempfile
from PIL import Image, ImageDraw, ImageFont
rd = pathlib.Path(sys.argv[1]).resolve(); n = int(sys.argv[2]) if len(sys.argv) > 2 else 12
flt = sys.argv[3] if len(sys.argv) > 3 else ""
vids = [v for v in sorted((rd / "out").glob("*/*.mp4")) if flt in v.parent.name]
T = 200; font = ImageFont.load_default(size=16)
board = Image.new("RGB", (T * n, (T + 22) * len(vids)), (25, 25, 25)); dr = ImageDraw.Draw(board)
for r, v in enumerate(vids):
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(v)], capture_output=True, text=True).stdout)
    td = pathlib.Path(tempfile.mkdtemp())
    for i in range(n):
        t = min(dur - 0.05, i * dur / (n - 1))
        f = td / f"{i:03d}.png"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.3f}", "-i", str(v), "-frames:v", "1", "-vf", f"scale={T}:{T}", str(f)])
        if f.exists(): board.paste(Image.open(f).convert("RGB"), (i * T, r * (T + 22) + 22))
        dr.text((i * T + 4, r * (T + 22) + 3), f"{t:.1f}s", fill=(160, 160, 160), font=font)
    dr.text((T * n - 260, r * (T + 22) + 3), v.parent.name, fill=(255, 210, 0), font=font)
name = f"strip{('-' + flt) if flt else ''}.png"
board.save(rd / name); print(rd / name)
