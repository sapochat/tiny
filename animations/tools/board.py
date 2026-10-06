#!/usr/bin/env python3
"""Keyframe review board: rows = states, cols = neutral + each model. Also silhouette-drift metric.
Usage: board.py <round_dir> <model_suffix,...>"""
import sys, json, pathlib
from PIL import Image, ImageDraw, ImageFont
import numpy as np

rd = pathlib.Path(sys.argv[1]); sufs = sys.argv[2].split(",")
root = pathlib.Path(__file__).resolve().parents[1]
neutral = Image.open(root / "ref/neutral-roundsafe-1440.png").convert("L")
T = 300
font = ImageFont.load_default(size=18) if hasattr(ImageFont, "load_default") else None


def mask(im, n=256):
    a = np.array(im.convert("L").resize((n, n), Image.LANCZOS)) > 128
    return a


def iou(a, b):
    return float((a & b).sum() / max(1, (a | b).sum()))


nm = mask(neutral)
files = {}
for d in sorted((rd / "out").iterdir()):
    for f in d.glob("*.png"):
        state, suf = d.name.rsplit("-", 1)
        files.setdefault(state, {})[suf] = f
states = sorted(files)
W = T * (1 + len(sufs)); H = (T + 30) * len(states) + 30
board = Image.new("RGB", (W, H), (20, 20, 20)); dr = ImageDraw.Draw(board)
metrics = {}
for c, lab in enumerate(["neutral"] + sufs):
    dr.text((c * T + 8, 6), lab, fill=(255, 200, 0), font=font)
for r, s in enumerate(states):
    y = 30 + r * (T + 30)
    dr.text((8, y + 4), s, fill=(255, 255, 255), font=font)
    board.paste(neutral.convert("RGB").resize((T, T), Image.LANCZOS), (0, y + 28))
    for c, suf in enumerate(sufs, 1):
        f = files[s].get(suf)
        if not f: continue
        im = Image.open(f).convert("RGB")
        m = iou(nm, mask(im)); metrics[f"{s}-{suf}"] = {"size": im.size, "silhouette_iou_vs_neutral": round(m, 3)}
        board.paste(im.resize((T, T), Image.LANCZOS), (c * T, y + 28))
        dr.text((c * T + 8, y + 4), f"IoU {m:.2f}  {im.size[0]}px", fill=(150, 220, 150), font=font)
board.save(rd / "board.png")
(rd / "metrics.json").write_text(json.dumps(metrics, indent=2))
print(json.dumps(metrics, indent=1))
