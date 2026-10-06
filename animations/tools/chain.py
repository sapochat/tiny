#!/usr/bin/env python3
"""Build a seamless chained state demo: snap every clip to its declared start/end anchor, concat, round-mask at 466.
Usage: chain.py <chain.json> <out.mp4>
chain.json: [{"clip": path, "start": anchor_png, "end": anchor_png, "label": str, "reverse": bool}, ...]"""
import sys, json, subprocess, pathlib
root = pathlib.Path(__file__).resolve().parents[1]
py = sys.executable
spec = json.loads(pathlib.Path(sys.argv[1]).read_text()); out = pathlib.Path(sys.argv[2])
tmp = out.parent / (out.stem + "-parts"); tmp.mkdir(parents=True, exist_ok=True)
parts, report = [], []
for i, s in enumerate(spec):
    p = tmp / f"{i:02d}.mp4"
    args = [py, str(root / "tools/snap.py"), str(root / s["clip"]), str(root / s["start"]), str(root / s["end"]), str(p), "--size", "720"]
    if s.get("reverse"): args.append("--reverse")
    r = json.loads(subprocess.run(args, capture_output=True, text=True, check=True).stdout.strip().splitlines()[-1])
    # check adjacency: this start anchor must equal previous end anchor
    seam_ok = i == 0 or spec[i - 1]["end"] == s["start"]
    report.append({"i": i, "label": s["label"], **r, "anchor_chain_ok": seam_ok}); parts.append(p)
lst = tmp / "list.txt"; lst.write_text("".join(f"file '{p.name}'\n" for p in parts))
joined = tmp / "joined.mp4"
subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(joined)], check=True)
mask = root / "ref/round-mask-outline-466.png"
# label timeline via drawtext enable windows (24fps * 121 frames each, measure actual)
durs = [float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)],
                             capture_output=True, text=True).stdout) for p in parts]
t, dt = 0.0, []
for s, d in zip(spec, durs):
    lab = s["label"].replace("'", "").replace(":", " ")
    dt.append(f"drawtext=text='{lab}':x=12:y=10:fontsize=22:fontcolor=white:enable='between(t,{t:.3f},{t + d - 0.001:.3f})'"); t += d
SMOOTH = "mpdecimate=hi=64*12:lo=64*5:frac=0.33,minterpolate=fps=30:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1,"
pre = SMOOTH if "--smooth" in sys.argv else ""
if pre: out = out.with_name(out.stem + "-smooth.mp4")
fc = f"[0:v]{pre}scale=466:466:flags=lanczos,setsar=1[s];[s][1:v]overlay=0:0:shortest=1,pad=466:506:0:40:black,{','.join(dt)}[o]"
subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(joined), "-loop", "1", "-i", str(mask), "-filter_complex", fc, "-map", "[o]",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", "-movflags", "+faststart", str(out)], check=True)
clean = out.with_name(out.stem + "-clean720.mp4")
subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(joined), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "16", "-movflags", "+faststart", str(clean)], check=True)
(out.with_suffix(".report.json")).write_text(json.dumps(report, indent=1))
print(json.dumps({"out": str(out), "clean": str(clean), "seconds": round(t, 2), "all_anchor_chain_ok": all(r["anchor_chain_ok"] for r in report),
                  "max_seam_before_snap": round(max(max(r["seam_start_before"], r["seam_end_before"]) for r in report), 2)}))
