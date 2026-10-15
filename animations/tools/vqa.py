#!/usr/bin/env python3
"""Video QA for a round: probe, contact sheet, anchor fidelity, silhouette drift, side-by-side grid.
Usage: vqa.py <round_dir> [anchor_png]"""
import sys, json, pathlib, subprocess, tempfile
from PIL import Image
import numpy as np

rd = pathlib.Path(sys.argv[1]).resolve()
root = pathlib.Path(__file__).resolve().parents[1]
anchor = pathlib.Path(sys.argv[2]) if len(sys.argv) > 2 else root / "ref/neutral-roundsafe-1440.png"
A = np.array(Image.open(anchor).convert("L").resize((256, 256), Image.LANCZOS)).astype(float)
Am = A > 128


def frames(mp4, fps=10):
    td = tempfile.mkdtemp()
    subprocess.run(["ffmpeg", "-v", "error", "-i", str(mp4), "-vf", f"fps={fps},scale=256:256", f"{td}/%04d.png"], check=True)
    return sorted(pathlib.Path(td).glob("*.png"))


out = {}
vids = sorted((rd / "out").glob("*/*.mp4"))
for v in vids:
    pr = json.loads(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                    "stream=width,height,r_frame_rate,nb_frames:format=duration", "-of", "json", str(v)],
                                   capture_output=True, text=True).stdout)
    fs = frames(v)
    ious, mads = [], []
    for f in fs:
        g = np.array(Image.open(f).convert("L")).astype(float)
        m = g > 128
        ious.append(float((m & Am).sum() / max(1, (m | Am).sum())))
        mads.append(float(np.abs(g - A).mean()))
    # motion energy between consecutive samples
    arr = [np.array(Image.open(f).convert("L")).astype(float) for f in fs]
    energy = [float(np.abs(arr[i + 1] - arr[i]).mean()) for i in range(len(arr) - 1)]
    out[v.parent.name] = {
        "probe": pr, "samples": len(fs),
        "first_mad_vs_anchor": round(mads[0], 2), "last_mad_vs_anchor": round(mads[-1], 2),
        "min_silhouette_iou": round(min(ious), 3), "mean_silhouette_iou": round(sum(ious) / len(ious), 3),
        "motion_energy_mean": round(sum(energy) / len(energy), 3), "motion_energy_max": round(max(energy), 3),
    }
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(v), "-vf", "fps=5,scale=256:256,tile=5x5", "-frames:v", "1",
                    str(v.parent / "contact.png")], check=True)
(rd / "vqa.json").write_text(json.dumps(out, indent=2))
for k, x in out.items():
    print(f"{k:28s} first {x['first_mad_vs_anchor']:6.2f} last {x['last_mad_vs_anchor']:6.2f} "
          f"minIoU {x['min_silhouette_iou']:.3f} motion {x['motion_energy_mean']:.2f}/{x['motion_energy_max']:.2f} "
          f"{x['probe']['streams'][0]['width']}x{x['probe']['streams'][0]['height']} {x['probe']['format']['duration']}s")

# side-by-side grid (labels via drawtext may be unavailable; order printed instead)
if len(sys.argv) <= 3 and vids:
    n = len(vids); cols = 4 if n > 4 else n; rows = (n + cols - 1) // cols
    inputs = sum([["-i", str(v)] for v in vids], [])
    S = 360
    fl = ";".join(f"[{i}:v]fps=24,scale={S}:{S},setsar=1,trim=duration=5,setpts=PTS-STARTPTS[v{i}]" for i in range(n))
    layout = "|".join(f"{(i % cols) * S}_{(i // cols) * S}" for i in range(n))
    fl += ";" + "".join(f"[v{i}]" for i in range(n)) + f"xstack=inputs={n}:layout={layout}:fill=black[o]"
    subprocess.run(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", fl, "-map", "[o]", "-c:v", "libx264",
                    "-pix_fmt", "yuv420p", "-crf", "18", "-movflags", "+faststart", str(rd / "grid.mp4")], check=True)
    (rd / "grid-order.txt").write_text("\n".join(f"r{i // cols + 1}c{i % cols + 1}: {v.parent.name}" for i, v in enumerate(vids)))
    print((rd / "grid-order.txt").read_text())
