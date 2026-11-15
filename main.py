#!/usr/bin/env python3
"""
Topic -> Hindi script -> scene images -> Hindi voiceover -> animated 9:16 video -> Telegram.
Runs fully inside GitHub Actions. No subtitles (by design).

Env vars (set as GitHub Secrets / workflow inputs):
  GEMINI_API_KEY      required (script writing, free tier text model)
  TELEGRAM_BOT_TOKEN  required (to receive the video)
  TELEGRAM_CHAT_ID    required
  HF_TOKEN            optional (fallback image provider)
  TOPIC               optional (else picked from topics.txt)
  SCENES              optional, default 14
  DRY_RUN=1           test the video assembly without any network/AI
"""
import asyncio
import json
import math
import os
import random
import re
import subprocess
import sys
import time
import urllib.parse
from datetime import date
from pathlib import Path

import numpy as np
import requests
from PIL import Image, ImageDraw, ImageFilter

W, H, FPS = 720, 1280, 30
OUT = Path("output")
WORK = Path("work")

TEXT_MODEL = os.getenv("GEMINI_TEXT_MODEL", "gemini-3.8-flash")
GEMINI_IMAGE_MODEL = os.getenv("GEMINI_IMAGE_MODEL", "gemini-2.5-flash-image")
IMAGE_PROVIDERS = [p.strip() for p in os.getenv("IMAGE_PROVIDERS", "cloudflare,pollinations").split(",") if p.strip()]
HF_MODEL_URL = os.getenv("HF_MODEL_URL", "https://router.huggingface.co/hf-inference/models/black-forest-labs/FLUX.1-schnell")
VOICE = os.getenv("TTS_VOICE", "hi-IN-MadhurNeural")
TTS_RATE = os.getenv("TTS_RATE", "-5%")
STYLE = os.getenv(
    "STYLE",
    "flat 2D vector illustration, Indian mythology Mahabharat, cutout puppet style characters, "
    "thick dark outlines, rich warm colours, cinematic dramatic lighting, soft glow, "
    "vertical 9:16 composition, single clear focal point, no text, no letters, no watermark",
)


def log(*a):
    print(*a, flush=True)


def run(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if r.returncode != 0:
        log("CMD FAILED:", " ".join(map(str, cmd))[:300])
        log(r.stderr[-1500:])
        raise RuntimeError("command failed")
    return r.stdout


# --------------------------------------------------------------------------- script
def gemini_text(prompt):
    key = os.environ["GEMINI_API_KEY"]
    models = [TEXT_MODEL, "gemini-3.5-flash-lite", "gemini-3.5-flash", "gemini-flash-latest"]
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.9},
    }
    for model in dict.fromkeys(models):
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
        for attempt in range(3):
            r = requests.post(url, json=body, timeout=120)
            if r.status_code == 429:
                log(f"  {model}: HTTP 429 {r.text[:300]}")
                break  # quota khatam: retry ka fayda nahi, agla model try karo
            if r.status_code in (500, 503):
                log(f"  {model}: HTTP {r.status_code} {r.text[:200]}")
                time.sleep(8 * (attempt + 1))
                continue
            if r.status_code != 200:
                log(f"  {model}: HTTP {r.status_code} {r.text[:300]}")
                break
            txt = r.json()["candidates"][0]["content"]["parts"][0]["text"]
            txt = re.sub(r"^```(?:json)?|```$", "", txt.strip(), flags=re.M).strip()
            return json.loads(txt)
    raise RuntimeError("Gemini text failed on all models")


def write_script(topic, n):
    prompt = (
        "You are a scriptwriter for viral Hindi short-form animated storytelling videos on Indian mythology "
        "(Mahabharat, Ramayan, Puranas).\n"
        f"Topic: {topic}\n"
        f"Write exactly {n} scenes. Rules:\n"
        "- narration: simple conversational Hindi in Devanagari, 1-2 short sentences per scene (max 18 words), "
        "dramatic storytelling tone. Scene 1 must be a strong hook (a question or a shocking secret). "
        "The last scene is a cliffhanger or 'Part 2' tease.\n"
        "- Stay with well-known accounts from the texts. Do not invent facts. Respectful tone; "
        "nothing insulting to any religion, caste or community.\n"
        "- characters: an object mapping each recurring character name (English) to ONE fixed English visual "
        "description (skin tone, clothes colours, crown/ornaments, beard, age). Keep it identical for all scenes.\n"
        "- image_prompt: English. Describe only the setting, action, mood, lighting and camera of that scene. "
        "Refer to characters by the exact names used in 'characters'. No text in the image.\n"
        "- scene.characters: list of character names appearing in that scene.\n"
        'Return ONLY JSON: {"title":"(Hindi)","description":"(Hindi, 2 lines)","hashtags":["#..."],'
        '"characters":{"Name":"visual description"},'
        '"scenes":[{"narration":"...","image_prompt":"...","characters":["Name"]}]}'
    )
    data = gemini_text(prompt)
    assert data.get("scenes"), "empty script"
    return data


# --------------------------------------------------------------------------- images
def _valid_image(b):
    import io

    Image.open(io.BytesIO(b)).verify()
    return b


def img_pollinations(prompt, seed):
    url = "https://image.pollinations.ai/prompt/" + urllib.parse.quote(prompt[:1400])
    r = requests.get(url, params=dict(width=W, height=H, seed=seed, nologo="true", model="flux"), timeout=180)
    r.raise_for_status()
    return _valid_image(r.content)


def img_huggingface(prompt, seed):
    tok = os.environ["HF_TOKEN"]
    r = requests.post(
        HF_MODEL_URL,
        headers={"Authorization": f"Bearer {tok}"},
        json={"inputs": prompt, "parameters": {"width": 720, "height": 1280, "seed": seed}},
        timeout=180,
    )
    r.raise_for_status()
    return _valid_image(r.content)


def img_gemini(prompt, seed):
    import base64

    key = os.environ["GEMINI_API_KEY"]
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_IMAGE_MODEL}:generateContent?key={key}"
    body = {
        "contents": [{"parts": [{"text": prompt + " Vertical 9:16 image."}]}],
        "generationConfig": {"responseModalities": ["IMAGE"]},
    }
    r = requests.post(url, json=body, timeout=180)
    r.raise_for_status()
    for p in r.json()["candidates"][0]["content"]["parts"]:
        d = p.get("inlineData") or p.get("inline_data")
        if d:
            return _valid_image(base64.b64decode(d["data"]))
    raise RuntimeError("no image in Gemini response")


def img_cloudflare(prompt, seed):
    import base64

    acc, tok = os.environ["CF_ACCOUNT_ID"], os.environ["CF_API_TOKEN"]
    url = f"https://api.cloudflare.com/client/v4/accounts/{acc}/ai/run/@cf/black-forest-labs/flux-1-schnell"
    r = requests.post(url, headers={"Authorization": f"Bearer {tok}"},
                      json={"prompt": prompt[:2000], "steps": 6}, timeout=180)
    if r.status_code != 200:
        raise requests.HTTPError(f"{r.status_code} {r.text[:250]}", response=r)
    if r.headers.get("content-type", "").startswith("image/"):
        return _valid_image(r.content)
    return _valid_image(base64.b64decode(r.json()["result"]["image"]))


PROVIDER_FN = {"cloudflare": img_cloudflare, "pollinations": img_pollinations, "huggingface": img_huggingface, "gemini": img_gemini}


def make_image(prompt, idx, path):
    seed = random.randint(1, 10**6)
    last = None
    for name in IMAGE_PROVIDERS:
        if name == "huggingface" and not os.getenv("HF_TOKEN"):
            continue
        if name == "cloudflare" and not (os.getenv("CF_ACCOUNT_ID") and os.getenv("CF_API_TOKEN")):
            log("  cloudflare keys missing, skipping")
            continue
        for attempt in range(3):
            try:
                data = PROVIDER_FN[name](prompt, seed + attempt)
                save_cover(data, path)
                log(f"  image {idx}: {name} ok")
                return
            except Exception as e:  # noqa: BLE001
                last = e
                log(f"  image {idx}: {name} attempt {attempt + 1} failed: {str(e)[:250]}")
                code = getattr(getattr(e, "response", None), "status_code", None)
                if code in (400, 401, 402, 403, 404, 410, 429):
                    break  # retry ka fayda nahi (quota / galat key / band endpoint)
                time.sleep(4 * (attempt + 1))
    raise RuntimeError(f"all image providers failed: {last}")


def save_cover(data, path, scale=2):
    """Crop to 9:16 and upscale (zoompan looks smoother on a larger source)."""
    import io

    im = Image.open(io.BytesIO(data)).convert("RGB")
    tw, th = W * scale, H * scale
    r = max(tw / im.width, th / im.height)
    im = im.resize((math.ceil(im.width * r), math.ceil(im.height * r)), Image.LANCZOS)
    left, top = (im.width - tw) // 2, (im.height - th) // 2
    im.crop((left, top, left + tw, top + th)).save(path, quality=95)


def placeholder_image(idx, path):
    im = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(im)
    for y in range(H):
        c = int(40 + 160 * y / H)
        d.line([(0, y), (W, y)], fill=((c + idx * 25) % 255, 60, 200 - c // 2))
    d.ellipse([W // 2 - 120, H // 2 - 120, W // 2 + 120, H // 2 + 120], fill=(255, 200, 60))
    buf = Path(path).with_suffix(".tmp.png")
    im.save(buf)
    save_cover(buf.read_bytes(), path)
    buf.unlink()


# --------------------------------------------------------------------------- voice
async def _tts(text, path):
    import edge_tts

    await edge_tts.Communicate(text, VOICE, rate=TTS_RATE).save(str(path))


def make_voice(text, path):
    for attempt in range(4):
        try:
            asyncio.run(_tts(text, path))
            if Path(path).stat().st_size > 1000:
                return
        except Exception as e:  # noqa: BLE001
            log(f"  tts attempt {attempt + 1} failed: {str(e)[:120]}")
        time.sleep(3 * (attempt + 1))
    raise RuntimeError("TTS failed")


def silent_voice(path, secs=3.0):
    run(["ffmpeg", "-y", "-f", "lavfi", "-i", f"sine=frequency=220:duration={secs}", "-q:a", "5", str(path)])


def duration(path):
    return float(run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)]).strip())


# --------------------------------------------------------------------------- video
def motion(kind, frames):
    inc = 0.22 / frames
    cy = "ih/2-(ih/zoom/2)"
    if kind == 0:  # slow zoom in
        return f"1+{inc:.7f}*on", "iw/2-(iw/zoom/2)", cy
    if kind == 1:  # slow zoom out
        return f"1.22-{inc:.7f}*on", "iw/2-(iw/zoom/2)", cy
    if kind == 2:  # pan left -> right
        return "1.18", f"(iw-iw/zoom)*on/{frames}", cy
    return "1.18", f"(iw-iw/zoom)*(1-on/{frames})", cy  # pan right -> left


def build_clip(img, audio, idx, out):
    pad = 0.45
    dur = duration(audio) + pad
    frames = math.ceil(dur * FPS)
    z, x, y = motion(idx % 4, frames)
    fc = (
        f"[0:v]zoompan=z='{z}':x='{x}':y='{y}':d={frames}:s={W}x{H}:fps={FPS},"
        f"fade=t=in:st=0:d=0.25,fade=t=out:st={dur - 0.25:.2f}:d=0.25,format=yuv420p[v];"
        f"[1:a]apad=pad_dur={pad},aresample=44100,aformat=channel_layouts=stereo[a]"
    )
    run([
        "ffmpeg", "-y", "-i", str(img), "-i", str(audio), "-filter_complex", fc,
        "-map", "[v]", "-map", "[a]", "-t", f"{dur:.2f}",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-r", str(FPS),
        "-c:a", "aac", "-b:a", "128k", "-ar", "44100", str(out),
    ])
    return dur


def make_particles(path, seconds=20, n=90):
    """Seamless looping golden dust, blended over the final video."""
    rng = np.random.default_rng(7)
    x0, y0 = rng.uniform(0, W, n), rng.uniform(0, H, n)
    k = rng.integers(1, 3, n)  # integer laps -> seamless loop
    m1, m2 = rng.integers(1, 4, n), rng.integers(3, 6, n)
    size, phase = rng.uniform(1.5, 4.2, n), rng.uniform(0, 6.28, n)
    drift = rng.uniform(6, 22, n)
    p = subprocess.Popen(
        ["ffmpeg", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", "-preset", "veryfast", str(path)],
        stdin=subprocess.PIPE, stderr=subprocess.DEVNULL,
    )
    for f in range(seconds * FPS):
        t = f / FPS
        img = Image.new("RGB", (W, H), (0, 0, 0))
        d = ImageDraw.Draw(img)
        for i in range(n):
            y = (y0[i] - H * k[i] * t / seconds) % H
            x = (x0[i] + math.sin(2 * math.pi * m1[i] * t / seconds + phase[i]) * drift[i]) % W
            tw = 0.5 + 0.5 * math.sin(2 * math.pi * m2[i] * t / seconds + phase[i])
            c = int(110 + 145 * tw)
            r = size[i]
            d.ellipse([x - r, y - r, x + r, y + r], fill=(c, int(c * 0.78), int(c * 0.4)))
        p.stdin.write(img.filter(ImageFilter.GaussianBlur(1.1)).tobytes())
    p.stdin.close()
    p.wait()


def assemble(clips, total, out):
    lst = WORK / "clips.txt"
    lst.write_text("".join(f"file '{c.resolve()}'\n" for c in clips))
    joined = WORK / "joined.mp4"
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(joined)])

    particles = WORK / "particles.mp4"
    make_particles(particles)

    music = Path("assets/music.mp3")
    cmd = ["ffmpeg", "-y", "-i", str(joined), "-stream_loop", "-1", "-i", str(particles)]
    fv = ("[1:v]format=yuv420p[p];[0:v][p]blend=all_mode=screen:all_opacity=0.65,"
          "vignette=PI/5,eq=contrast=1.06:saturation=1.1[v]")
    if music.exists():
        cmd += ["-stream_loop", "-1", "-i", str(music)]
        fa = (f";[2:a]volume=0.13,afade=t=out:st={total - 2:.2f}:d=2[m];"
              "[0:a][m]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[a]")
        amap = "[a]"
    else:
        fa, amap = "", "0:a"
    cmd += ["-filter_complex", fv + fa, "-map", "[v]", "-map", amap, "-t", f"{total:.2f}",
            "-c:v", "libx264", "-preset", "medium", "-crf", "24", "-c:a", "aac", "-b:a", "128k",
            "-movflags", "+faststart", str(out)]
    run(cmd)
    # Telegram bot upload limit is 50 MB
    crf = 24
    while out.stat().st_size > 48 * 1024 * 1024 and crf < 36:
        crf += 4
        small = out.with_suffix(".small.mp4")
        run(["ffmpeg", "-y", "-i", str(out), "-c:v", "libx264", "-crf", str(crf), "-preset", "medium",
             "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", str(small)])
        small.replace(out)


# --------------------------------------------------------------------------- telegram
def tg_api(method, **kw):
    tok = os.environ["TELEGRAM_BOT_TOKEN"]
    return requests.post(f"https://api.telegram.org/bot{tok}/{method}", timeout=600, **kw)


def send_telegram(video, meta):
    chat = os.environ["TELEGRAM_CHAT_ID"]
    caption = f"{meta.get('title', '')}\n\n{meta.get('description', '')}\n\n{' '.join(meta.get('hashtags', []))}"[:1000]
    with open(video, "rb") as f:
        r = tg_api("sendVideo", data={"chat_id": chat, "caption": caption, "supports_streaming": "true",
                                      "width": W, "height": H}, files={"video": f})
    log("telegram:", r.status_code, r.text[:200])
    r.raise_for_status()
    narr = "\n".join(f"{i + 1}. {s['narration']}" for i, s in enumerate(meta["scenes"]))
    tg_api("sendMessage", data={"chat_id": chat, "text": ("Script:\n" + narr)[:4000]})


# --------------------------------------------------------------------------- main
def pick_topic():
    t = os.getenv("TOPIC", "").strip()
    if t:
        return t
    f = Path("topics.txt")
    lines = [l.strip() for l in f.read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("#")]
    return lines[date.today().toordinal() % len(lines)]


def main():
    dry = os.getenv("DRY_RUN") == "1"
    OUT.mkdir(exist_ok=True)
    WORK.mkdir(exist_ok=True)

    if dry:
        meta = {"title": "Test", "description": "dry run", "hashtags": ["#test"], "characters": {},
                "scenes": [{"narration": f"scene {i}", "image_prompt": "x", "characters": []} for i in range(1, 5)]}
    else:
        topic = pick_topic()
        n = int(os.getenv("SCENES", "14"))
        log(f"Topic: {topic} | scenes: {n}")
        meta = write_script(topic, n)
    (OUT / "script.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    clips, total = [], 0.0
    chars = meta.get("characters", {})
    for i, sc in enumerate(meta["scenes"]):
        log(f"Scene {i + 1}/{len(meta['scenes'])}")
        img, aud, clip = WORK / f"s{i}.jpg", WORK / f"s{i}.mp3", WORK / f"s{i}.mp4"
        if dry:
            placeholder_image(i, img)
            silent_voice(aud, 2.5 + (i % 2))
        else:
            who = "; ".join(f"{c}: {chars[c]}" for c in sc.get("characters", []) if c in chars)
            prompt = f"{sc['image_prompt']}. Characters: {who}. Style: {STYLE}"
            try:
                make_image(prompt, i + 1, img)
            except Exception as e:  # noqa: BLE001
                prev = WORK / f"s{i - 1}.jpg"
                if i > 0 and prev.exists():
                    log(f"  scene {i + 1}: image fail, pichli scene ki image reuse kar raha hoon")
                    img.write_bytes(prev.read_bytes())
                else:
                    raise
            make_voice(sc["narration"], aud)
            time.sleep(2)
        total += build_clip(img, aud, i, clip)
        clips.append(clip)

    final = OUT / "final.mp4"
    assemble(clips, total, final)
    log(f"Done: {final} ({final.stat().st_size / 1e6:.1f} MB, {total:.0f}s)")

    if dry:
        return
    send_telegram(final, meta)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # noqa: BLE001
        log("ERROR:", e)
        sys.exit(1)
