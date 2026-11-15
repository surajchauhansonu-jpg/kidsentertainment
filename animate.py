"""
2.5D animation for still images (free, CPU only).

1. Depth map: Depth Anything V2 Small (ONNX, Apache-2.0) -> falls back to a pseudo depth if it can't load.
2. Virtual camera: parallax orbit / push / pull / rise, plus a mid-scene "punch-in" cut (wide -> close-up).
3. Life: handheld shake, breathing zoom, flickering light, bloom glow, flash on cuts.
"""
import math
import random
import subprocess
from pathlib import Path

import cv2
import numpy as np
import requests

W, H, FPS = 720, 1280, 30
DEPTH_URL = "https://huggingface.co/onnx-community/depth-anything-v2-small/resolve/main/onnx/model.onnx"
_SESSION = {"s": None, "failed": False}
MEAN = np.array([0.485, 0.456, 0.406], np.float32)
STD = np.array([0.229, 0.224, 0.225], np.float32)


def log(*a):
    print(*a, flush=True)


# --------------------------------------------------------------------------- depth
def _session(cache_dir):
    if _SESSION["s"] is not None or _SESSION["failed"]:
        return _SESSION["s"]
    try:
        import onnxruntime as ort

        p = Path(cache_dir) / "depth_anything_v2_small.onnx"
        p.parent.mkdir(parents=True, exist_ok=True)
        if not p.exists() or p.stat().st_size < 10_000_000:
            log("  downloading depth model (~120 MB, one time)")
            r = requests.get(DEPTH_URL, timeout=600)
            r.raise_for_status()
            p.write_bytes(r.content)
        _SESSION["s"] = ort.InferenceSession(str(p), providers=["CPUExecutionProvider"])
    except Exception as e:  # noqa: BLE001
        log(f"  depth model unavailable ({str(e)[:120]}), using pseudo depth")
        _SESSION["failed"] = True
    return _SESSION["s"]


def pseudo_depth(h, w, bgr):
    """Cheap fallback: centre + lower part of frame is 'nearer', bright areas slightly nearer."""
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    rad = 1 - np.clip(np.hypot((xx - w / 2) / (w / 2), (yy - h * 0.55) / (h / 2)), 0, 1)
    grad = yy / h
    lum = cv2.GaussianBlur(cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY), (0, 0), 25).astype(np.float32) / 255
    return np.clip(0.55 * rad + 0.25 * grad + 0.2 * lum, 0, 1)


def get_depth(bgr, cache_dir="models_cache", use_model=True):
    """Returns float32 HxW at *render* resolution (W x H), 1 = near, 0 = far."""
    small = cv2.resize(bgr, (W, H), interpolation=cv2.INTER_AREA)
    d = None
    sess = _session(cache_dir) if use_model else None
    if sess is not None:
        try:
            rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
            x = cv2.resize(rgb, (518, 518), interpolation=cv2.INTER_CUBIC).astype(np.float32) / 255
            x = ((x - MEAN) / STD).transpose(2, 0, 1)[None]
            out = sess.run(None, {sess.get_inputs()[0].name: x})[0]
            d = cv2.resize(np.squeeze(out).astype(np.float32), (W, H), interpolation=cv2.INTER_CUBIC)
            lo, hi = np.percentile(d, 2), np.percentile(d, 98)
            d = np.clip((d - lo) / (hi - lo + 1e-6), 0, 1)
        except Exception as e:  # noqa: BLE001
            log(f"  depth inference failed ({str(e)[:100]}), using pseudo depth")
            d = None
    if d is None:
        d = pseudo_depth(H, W, small)
    return cv2.GaussianBlur(d, (0, 0), 5).astype(np.float32)  # soft edges -> less tearing


# --------------------------------------------------------------------------- camera plan
def ease(t):
    t = min(max(t, 0.0), 1.0)
    return t * t * (3 - 2 * t)


def plan_shots(idx, dur, energy):
    kinds = ["push", "pull", "orbit_lr", "orbit_rl", "rise", "push_side"]
    k = kinds[idx % len(kinds)]
    a = 0.8 + 0.2 * energy
    base = {
        "push": dict(z0=1.03, z1=1.17, f0=(0.5, 0.52), f1=(0.5, 0.42), amp=14, d=1, tilt=0),
        "pull": dict(z0=1.19, z1=1.04, f0=(0.5, 0.42), f1=(0.5, 0.52), amp=14, d=-1, tilt=0),
        "orbit_lr": dict(z0=1.11, z1=1.14, f0=(0.5, 0.5), f1=(0.5, 0.48), amp=28, d=1, tilt=0),
        "orbit_rl": dict(z0=1.11, z1=1.14, f0=(0.5, 0.5), f1=(0.5, 0.48), amp=28, d=-1, tilt=0),
        "rise": dict(z0=1.10, z1=1.15, f0=(0.5, 0.64), f1=(0.5, 0.38), amp=12, d=1, tilt=18),
        "push_side": dict(z0=1.03, z1=1.17, f0=(0.36, 0.5), f1=(0.44, 0.44), amp=20, d=1, tilt=0),
    }[k]
    base["amp"] *= a
    if dur < 4.6:
        base["t0"], base["t1"] = 0.0, dur
        return [base]
    rng = random.Random(900 + idx)
    cut = dur * rng.uniform(0.42, 0.55)
    s1 = dict(base, t0=0.0, t1=cut)
    s2 = dict(z0=1.34, z1=1.50, f0=(0.5, 0.36), f1=(0.5, 0.40), amp=24 * a, d=-base["d"], tilt=0, t0=cut, t1=dur)
    return [s1, s2]


# --------------------------------------------------------------------------- render
def render_scene(src_bgr, depth, dur, idx, out_path, energy=2):
    """Renders a silent animated clip. Returns the time (s) of the internal cut, or None."""
    sh, sw = src_bgr.shape[:2]
    sx, sy = sw / W, sh / H
    U, V = np.meshgrid(np.arange(W, dtype=np.float32), np.arange(H, dtype=np.float32))
    Dm = depth - 0.45
    n = max(2, int(math.ceil(dur * FPS)))
    shots = plan_shots(idx, dur, energy)
    rng = random.Random(77 + idx)
    ph = [rng.uniform(0, 6.28) for _ in range(6)]
    shake = {1: 0.6, 2: 1.2, 3: 2.6}.get(int(energy), 1.2)

    p = subprocess.Popen(
        ["ffmpeg", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", str(out_path)],
        stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)

    for f in range(n):
        t = f / FPS
        s = shots[-1]
        for cand in shots:
            if t < cand["t1"]:
                s = cand
                break
        local = t - s["t0"]
        pr = (local / max(s["t1"] - s["t0"], 1e-3))
        e = ease(pr)
        z = s["z0"] + (s["z1"] - s["z0"]) * e
        fx = (s["f0"][0] + (s["f1"][0] - s["f0"][0]) * e) * W
        fy = (s["f0"][1] + (s["f1"][1] - s["f0"][1]) * e) * H
        ox = s["d"] * s["amp"] * (2 * e - 1)
        oy = s["tilt"] * (2 * e - 1)

        # punch-in at the start of each shot (hard-cut feel), decays quickly
        z *= 1 + 0.10 * math.exp(-local / 0.14)
        # breathing + handheld
        z *= 1 + 0.004 * math.sin(2 * math.pi * 0.45 * t + ph[0])
        fx += shake * (1.4 * math.sin(2 * math.pi * 1.1 * t + ph[1]) + 0.7 * math.sin(2 * math.pi * 2.7 * t + ph[2]))
        fy += shake * (1.1 * math.sin(2 * math.pi * 0.9 * t + ph[3]) + 0.6 * math.sin(2 * math.pi * 3.1 * t + ph[4]))

        mx = (fx + (U - fx) / z + ox * Dm) * sx
        my = (fy + (V - fy) / z + oy * Dm) * sy
        out = cv2.remap(src_bgr, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT_101)

        # bloom glow
        sm = cv2.resize(out, (W // 4, H // 4), interpolation=cv2.INTER_AREA).astype(np.float32)
        bright = np.clip(sm - 165, 0, None) * 1.6
        bloom = cv2.resize(cv2.GaussianBlur(bright, (0, 0), 7), (W, H), interpolation=cv2.INTER_LINEAR)
        fl = out.astype(np.float32) + bloom * 0.55

        # flickering light + flash on cuts
        gain = 1 + 0.025 * math.sin(2 * math.pi * 3.1 * t + ph[5]) + 0.015 * math.sin(2 * math.pi * 7.3 * t + ph[0])
        fl *= gain
        for cand in shots:
            lt = t - cand["t0"]
            if 0 <= lt < 0.10:
                fl += 55 * (1 - lt / 0.10)
        p.stdin.write(np.clip(fl, 0, 255).astype(np.uint8).tobytes())

    p.stdin.close()
    p.wait()
    return shots[0]["t1"] if len(shots) > 1 else None
