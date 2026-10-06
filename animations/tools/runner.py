#!/usr/bin/env python3
"""Generic parallel Higgsfield job runner.
Usage: runner.py <round_dir>   (reads <round_dir>/jobs.json, writes <round_dir>/out/<name>/...)
jobs.json: [{"name":..., "model":..., "prompt":..., "args": {"--flag": "value", ...}}]
Skips jobs whose result file already exists (safe to rerun)."""
import concurrent.futures as cf, json, pathlib, subprocess, sys, urllib.request, hashlib, time

HF = "/home/santi/.npm-global/bin/higgsfield"
rd = pathlib.Path(sys.argv[1]).resolve()
jobs = json.loads((rd / "jobs.json").read_text())
import os
if os.environ.get("ONLY"):
    keep = set(os.environ["ONLY"].split(","))
    jobs = [j for j in jobs if j["name"] in keep]
out = rd / "out"; out.mkdir(exist_ok=True)
MAXW = int(sys.argv[2]) if len(sys.argv) > 2 else 8


def find_url(obj):
    if isinstance(obj, dict):
        for k in ("result_url", "url"):
            v = obj.get(k)
            if isinstance(v, str) and v.startswith("http") and not v.endswith(".webp"):
                return v
        for v in obj.values():
            u = find_url(v)
            if u: return u
    if isinstance(obj, list):
        for v in obj:
            u = find_url(v)
            if u: return u
    return None


def run(job):
    d = out / job["name"]; d.mkdir(exist_ok=True)
    res_file = d / "result.json"
    if res_file.exists():
        return json.loads(res_file.read_text())
    cmd = [HF, "generate", "create", job["model"], "--prompt", job["prompt"]]
    for k, v in job.get("args", {}).items():
        cmd += [k, str(v)]
    cmd += ["--wait", "--wait-timeout", "30m", "--json"]
    (d / "request.json").write_text(json.dumps({"job": job, "cmd": cmd}, indent=2))
    t0 = time.time()
    # account allows 8 concurrent jobs; back off on rate limit / transient 5xx
    for attempt in range(40):
        p = subprocess.run(cmd, capture_output=True, text=True)
        transient = "rate_limit_reached" in p.stderr or "HTTP 503" in p.stderr or "HTTP 502" in p.stderr
        if p.returncode == 0 or not transient:
            break
        time.sleep(20 + attempt * 5)
    (d / "stdout.txt").write_text(p.stdout); (d / "stderr.txt").write_text(p.stderr)
    r = {"name": job["name"], "model": job["model"], "exit_code": p.returncode, "secs": round(time.time() - t0)}
    try:
        data = json.loads(p.stdout)
        url = find_url(data)
        r["url"] = url
        if url:
            ext = pathlib.Path(url.split("?")[0]).suffix or ".bin"
            f = d / f"{job['name']}{ext}"
            urllib.request.urlretrieve(url, f)
            r["file"] = str(f); r["sha256"] = hashlib.sha256(f.read_bytes()).hexdigest()
            r["status"] = "completed"
        else:
            r["status"] = "no_url"
    except Exception as e:
        r["status"] = "error"; r["error"] = f"{e}: {p.stderr[-500:]}"
    if r["status"] == "completed":
        res_file.write_text(json.dumps(r, indent=2))
    else:
        (d / "failed.json").write_text(json.dumps(r, indent=2))
    print(json.dumps(r), flush=True)
    return r


with cf.ThreadPoolExecutor(MAXW) as ex:
    results = list(ex.map(run, jobs))
(rd / "results.json").write_text(json.dumps(results, indent=2))
print("DONE", sum(r.get("status") == "completed" for r in results), "/", len(results))
