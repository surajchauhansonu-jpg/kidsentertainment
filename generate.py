import os, sys, json, asyncio, random, subprocess, time, glob, requests
from pathlib import Path
from urllib.parse import quote
from PIL import Image, ImageDraw, ImageFont
import edge_tts

GEMINI_KEY = os.environ["GEMINI_API_KEY"]
TG_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TG_CHAT = os.environ["TELEGRAM_CHAT_ID"]
# Pehla model fail (404) ho to agla try hoga. gemini-2.5-flash Oct 2026 me band ho chuka hai.
MODELS = [m for m in [os.environ.get("GEMINI_MODEL"), "gemini-3.8-flash", "gemini-4-hydrogen", "gemini-3.1-flash-lite"] if m]
VOICE = os.environ.get("TTS_VOICE", "hi-IN-SwaraNeural")     # male: hi-IN-MadhurNeural

W, H = 1080, 1920
OUT = Path("out"); OUT.mkdir(exist_ok=True)
HISTORY = Path("history.json")

STYLE = ("cute colorful 3D Pixar-style cartoon illustration for kids, bright happy colors, "
         "soft lighting, friendly characters, vertical 9:16, no text, no words, no letters")

TASKS = {
    "fact": {
        "scenes": 5,
        "brief": "6 se 10 saal ke bachon ke liye ek hairat-angez, sachchha FUN FACT (science, janwar, space, body, nature). "
                 "Shuru me ek sawaal/hook, phir 3-4 chhote majedar vakya, ant me 'Kya aapko pata tha?' type line.",
    },
    "poem": {
        "scenes": 4,
        "brief": "6 se 10 saal ke bachon ke liye ek chhoti, tukbandi wali BAAL KAVITA (8-12 lines, rhyme zaroori, mazedaar aur lay wali).",
    },
    "story": {
        "scenes": 6,
        "brief": "6 se 10 saal ke bachon ke liye ek chhoti MORAL STORY (jaanwar/bachche character), saaf seekh ke saath. Ant me ek line ki moral.",
    },
}


def load_history():
    return json.loads(HISTORY.read_text()) if HISTORY.exists() else []


def gemini(prompt):
    base_cfg = {"responseMimeType": "application/json", "temperature": 1.0}
    headers = {"x-goog-api-key": GEMINI_KEY}  # key URL me nahi, taaki error message me leak na ho
    last = ""
    for model in MODELS:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        use_think = True  # thinking kam rakhne se jawab jaldi aata hai
        for attempt in range(3):
            cfg = dict(base_cfg)
            if use_think:
                cfg["thinkingConfig"] = {"thinkingLevel": "low"}
            body = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": cfg}
            try:
                r = requests.post(url, json=body, headers=headers, timeout=90)
            except requests.exceptions.RequestException as e:
                last = f"{model}: {type(e).__name__} (timeout/network)"
                print("Gemini error", last)
                time.sleep(5)
                continue
            if r.ok:
                try:
                    return json.loads(r.json()["candidates"][0]["content"]["parts"][0]["text"])
                except Exception as e:
                    last = f"{model}: bad JSON ({type(e).__name__})"
                    print("Gemini error", last)
                    continue
            last = f"{model}: HTTP {r.status_code} {r.text[:150]}"
            print("Gemini error", last)
            if r.status_code == 404:
                break  # ye model nahi mila, agla model try karo
            if r.status_code == 400 and use_think:
                use_think = False  # thinkingConfig is model par accept nahi hua, bina uske try karo
                continue
            time.sleep(10)
    raise RuntimeError("Gemini fail: " + last)


def make_script(kind, used):
    t = TASKS[kind]
    seed_topic = random.choice(["jungle", "samundar", "aasman", "khana", "school", "dosti", "mausam", "insaan ka sharir",
                                "kisan", "train/gaadi", "tyohar", "chidiya", "machhli", "chand-taare", "ped-paudhe"])
    prompt = f"""Tum bachon ki YouTube/Instagram reels ke scriptwriter ho.
Kaam: {t['brief']}
Topic ka hint (zaroori nahi): {seed_topic}
In titles ko REPEAT mat karna: {used[-40:]}
Bhasha: saral Hindi (Devanagari), bachon ko samajh aane wali. Total narration 25-40 second ki ho.
Exactly {t['scenes']} scenes do. Har scene me:
 - "narration": us scene ka Hindi voiceover (1-2 chhote vakya, Devanagari)
 - "image_prompt": English me us scene ki cartoon image ka description. Har scene me same main character ka same look repeat karo (rang, kapde, janwar ka type).
JSON me hi jawab do:
{{"title": "...", "caption": "Instagram caption Hindi me 1-2 line + emoji", "hashtags": ["#..",".."], "scenes": [{{"narration": "...", "image_prompt": "..."}}]}}"""
    return gemini(prompt)


_last_img_call = 0.0
POLL_KEY = os.environ.get("POLLINATIONS_API_KEY", "").strip()


def make_image(prompt, path, seed):
    """Pollinations se image. Key ho to gen.pollinations.ai (fast), warna free anonymous endpoint
    (anonymous me 15 sec me sirf 1 request allowed hai, isliye gap rakha hai)."""
    global _last_img_call
    full = f"{STYLE}. {prompt}"
    if POLL_KEY:
        url = "https://gen.pollinations.ai/image/" + quote(full)
        params = {"width": 720, "height": 1280, "seed": seed, "model": "flux", "key": POLL_KEY}
    else:
        url = "https://image.pollinations.ai/prompt/" + quote(full)
        params = {"width": 720, "height": 1280, "seed": seed, "nologo": "true", "model": "flux"}
    last = "no response"
    for i in range(6):
        if not POLL_KEY:
            wait = 17 - (time.time() - _last_img_call)
            if wait > 0:
                time.sleep(wait)
            _last_img_call = time.time()
        try:
            r = requests.get(url, params=params, timeout=150)
            if r.ok and r.headers.get("content-type", "").startswith("image"):
                path.write_bytes(r.content)
                return
            last = f"HTTP {r.status_code} {r.text[:80]!r}"
        except requests.exceptions.RequestException as e:
            last = type(e).__name__
        print("image fail:", last)
        time.sleep(15 * (i + 1))
    raise RuntimeError(f"Image generate nahi hui ({last})")


def find_font():
    if os.environ.get("FONT_PATH"):
        return os.environ["FONT_PATH"]
    for p in ["/usr/share/fonts/truetype/noto/NotoSansDevanagari-Bold.ttf",
              *glob.glob("/usr/share/fonts/**/NotoSansDevanagari*Bold*.ttf", recursive=True),
              *glob.glob("/usr/share/fonts/**/NotoSansDevanagari*.ttf", recursive=True)]:
        if os.path.exists(p):
            return p
    raise RuntimeError("Devanagari font nahi mila (fonts-noto-core install karo)")


# ======================= V2 RENDERER: full-motion look =======================
import math
import numpy as np

FPS = 30
SR = 44100
_FONT_CACHE = {}


def font(size):
    if size not in _FONT_CACHE:
        _FONT_CACHE[size] = ImageFont.truetype(find_font(), size)
    return _FONT_CACHE[size]


def ease(x):                      # smoothstep
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


def ease_out_back(x):
    x = max(0.0, min(1.0, x))
    c1, c3 = 1.70158, 2.70158
    return 1 + c3 * (x - 1) ** 3 + c1 * (x - 1) ** 2


# ---------- captions: chhote chunks, word-by-word highlight, bina bhaari box ----------
CAP_FONT = 78
CAP_CENTER_Y = 1330               # Instagram ke neeche wale buttons se upar


def split_chunks(words, max_words=4):
    chunks, cur = [], []
    for w in words:
        cur.append(w)
        if len(cur) >= max_words or w[-1] in ",.?!।":
            chunks.append(cur); cur = []
    if cur:
        chunks.append(cur)
    return chunks


def render_caption(chunk, active):
    f = font(CAP_FONT)
    tmp = ImageDraw.Draw(Image.new("RGBA", (10, 10)))
    space = tmp.textlength(" ", font=f)
    max_w = W - 200
    lines, cur, cur_w = [], [], 0
    for i, w in enumerate(chunk):
        ww = tmp.textlength(w, font=f)
        if cur and cur_w + space + ww > max_w:
            lines.append(cur); cur, cur_w = [], 0
        cur.append((i, w, ww)); cur_w += ww + (space if len(cur) > 1 else 0)
    if cur:
        lines.append(cur)
    lh = int(CAP_FONT * 1.45)
    img = Image.new("RGBA", (W, lh * len(lines) + 60), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    y = 30
    for ln in lines:
        total = sum(x[2] for x in ln) + space * (len(ln) - 1)
        x = (W - total) / 2
        for i, w, ww in ln:
            col = (255, 214, 10, 255) if i == active else (255, 255, 255, 255)
            d.text((x, y), w, font=f, fill=col, stroke_width=9, stroke_fill=(20, 20, 40, 255))
            x += ww + space
        y += lh
    return img


def word_timeline(text, voice_len):
    words = text.split()
    wts = [len(w) + 2 + (5 if w[-1] in ",.?!।" else 0) for w in words]
    total = sum(wts)
    t0, span = 0.12, max(0.5, voice_len - 0.1)
    out, t = [], t0
    for w, wt in zip(words, wts):
        dt = span * wt / total
        out.append((w, t, t + dt)); t += dt
    return out


# ---------- visual extras ----------
def make_sprite(size):
    a = np.zeros((size, size), dtype=np.float32)
    c = (size - 1) / 2
    yy, xx = np.mgrid[0:size, 0:size]
    r = np.sqrt((xx - c) ** 2 + (yy - c) ** 2) / c
    a = np.clip(1 - r, 0, 1) ** 2.2
    rgba = np.zeros((size, size, 4), dtype=np.uint8)
    rgba[..., 0] = 255; rgba[..., 1] = 244; rgba[..., 2] = 200
    rgba[..., 3] = (a * 255).astype(np.uint8)
    return Image.fromarray(rgba, "RGBA")


def make_vignette():
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    r = np.sqrt(((xx - W / 2) / (W / 2)) ** 2 + ((yy - H / 2) / (H / 2)) ** 2) / 1.41
    a = np.clip((r - 0.55) / 0.45, 0, 1) ** 1.8 * 120
    return Image.fromarray(a.astype(np.uint8), "L")


_RNG = random.Random(7)
PARTICLES = [dict(x=_RNG.uniform(0, W), y=_RNG.uniform(0, H), sp=_RNG.uniform(40, 130),
                  sz=_RNG.choice([16, 22, 30, 40]), ph=_RNG.uniform(0, 6.28), sw=_RNG.uniform(15, 45))
             for _ in range(24)]
SPRITES = {}
VIGNETTE = None
BLACK = None

CAM = [  # (zoom0, zoom1, pan0, pan1, tilt0, tilt1)  pan/tilt -1..1
    (1.00, 1.17, -0.3, 0.5, 0.0, 0.2),
    (1.17, 1.02, 0.5, -0.4, 0.2, -0.2),
    (1.02, 1.20, 0.0, 0.0, 0.5, -0.4),
    (1.15, 1.00, -0.5, 0.4, -0.3, 0.3),
]


def camera_frame(base, idx, t, dur):
    z0, z1, p0, p1, q0, q1 = CAM[idx % len(CAM)]
    e = ease(t / dur)
    z = z0 + (z1 - z0) * e
    px = p0 + (p1 - p0) * e + 0.04 * math.sin(t * 2.1)     # halka handheld sway
    py = q0 + (q1 - q0) * e + 0.04 * math.sin(t * 1.7 + 1)
    bw, bh = W / z, H / z
    sx, sy = (W - bw) / 2, (H - bh) / 2
    left = sx + max(-1, min(1, px)) * sx
    top = sy + max(-1, min(1, py)) * sy
    return base.resize((W, H), Image.BICUBIC, box=(left, top, left + bw, top + bh))


def draw_particles(frame, t):
    for pt in PARTICLES:
        y = (pt["y"] - pt["sp"] * t) % (H + 120) - 60
        x = pt["x"] + pt["sw"] * math.sin(t * 1.3 + pt["ph"])
        tw = 0.5 + 0.5 * math.sin(t * 3 + pt["ph"])
        sz = max(8, int(pt["sz"] * (0.7 + 0.5 * tw)))
        sp = SPRITES.setdefault(sz, make_sprite(sz))
        frame.paste(sp, (int(x - sz / 2), int(y - sz / 2)), sp)


def scene_frames(img_path, text, voice_len, idx, prev_last):
    """Generator: is scene ki sab frames (PIL RGB) deta hai."""
    global VIGNETTE, BLACK
    if VIGNETTE is None:
        VIGNETTE = make_vignette(); BLACK = Image.new("RGB", (W, H), (0, 0, 0))
    img = Image.open(img_path).convert("RGB")
    ratio = max(W / img.width, H / img.height)
    img = img.resize((int(img.width * ratio) + 1, int(img.height * ratio) + 1), Image.LANCZOS)
    l, tp = (img.width - W) // 2, (img.height - H) // 2
    base = img.crop((l, tp, l + W, tp + H))

    dur = voice_len + 0.45
    n = int(dur * FPS)
    words = word_timeline(text, voice_len)
    chunks, k = [], 0
    for ch in split_chunks([w for w, _, _ in words]):
        chunks.append((ch, words[k][1], words[k + len(ch) - 1][2], k)); k += len(ch)
    cache = {}
    TR = 9  # transition frames
    for f in range(n):
        t = f / FPS
        frame = camera_frame(base, idx, t, dur)
        draw_particles(frame, t + idx * 3.1)
        frame.paste(BLACK, (0, 0), VIGNETTE)
        for ch, ts, te, k0 in chunks:
            if ts <= t <= te + 0.12:
                active = -1
                for j in range(len(ch)):
                    if words[k0 + j][1] <= t < words[k0 + j][2]:
                        active = j
                key = (k0, active)
                if key not in cache:
                    cache[key] = render_caption(ch, active)
                cap = cache[key]
                sc = 0.78 + 0.22 * ease_out_back((t - ts) / 0.22)
                if sc < 0.995 or sc > 1.005:
                    cap = cap.resize((max(1, int(cap.width * sc)), max(1, int(cap.height * sc))), Image.BILINEAR)
                frame.paste(cap, ((W - cap.width) // 2, int(CAP_CENTER_Y - cap.height / 2)), cap)
                break
        if prev_last is not None and f < TR:
            frame = Image.blend(prev_last, frame, ease((f + 1) / TR))
        yield frame


# ---------- audio ----------
def load_voice(mp3):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(mp3), "-f", "s16le", "-ac", "1", "-ar", str(SR), "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0


def whoosh(d=0.4):
    n = int(SR * d)
    rng = np.random.default_rng(3)
    noise = rng.standard_normal(n).astype(np.float32)
    out = np.zeros(n, dtype=np.float32); y = 0.0
    for i in range(n):                      # low-pass jiska cutoff sweep hota hai
        a = 0.015 + 0.35 * (i / n)
        y += a * (noise[i] - y); out[i] = y
    env = np.sin(np.pi * np.linspace(0, 1, n)) ** 2
    out = out * env
    return out / (np.abs(out).max() + 1e-6) * 0.22


def write_wav(path, x):
    import wave
    x = np.clip(x, -1, 1)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((x * 32767).astype(np.int16).tobytes())


def render_reel(scenes, out_path, work):
    """scenes = [{img, text, voice(np float32)}]; out_path = final mp4."""
    durs = [len(s["voice"]) / SR + 0.45 for s in scenes]
    total = int(sum(durs) * SR) + SR // 2
    audio = np.zeros(total, dtype=np.float32)
    wh = whoosh()
    pos = 0.0
    for i, (s, d) in enumerate(zip(scenes, durs)):
        a = int(pos * SR)
        audio[a:a + len(s["voice"])] += s["voice"]
        if i > 0:
            b = max(0, a - int(0.05 * SR))
            audio[b:b + len(wh)] += wh[:max(0, total - b)]
        pos += d
    wav = Path(work) / "voice.wav"; write_wav(wav, audio)

    music = sorted(glob.glob("music/*.mp3") + glob.glob("music/*.wav"))
    cmd = ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
           "-i", str(wav)]
    if music:
        cmd += ["-stream_loop", "-1", "-i", random.choice(music),
                "-filter_complex", "[2:a]volume=0.10[m];[1:a][m]amix=inputs=2:duration=first:dropout_transition=0[a]",
                "-map", "0:v", "-map", "[a]"]
    else:
        cmd += ["-map", "0:v", "-map", "1:a"]
    cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "160k", "-shortest", str(out_path)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    prev = None
    for i, s in enumerate(scenes):
        last = None
        for fr in scene_frames(s["img"], s["text"], len(s["voice"]) / SR, i, prev):
            proc.stdin.write(fr.tobytes()); last = fr
        prev = last
    proc.stdin.close()
    if proc.wait() != 0:
        raise RuntimeError("ffmpeg final render fail")


async def tts(text, path):
    await edge_tts.Communicate(text, VOICE, rate="-5%").save(str(path))


def build_reel(kind, script):
    work = OUT / kind; work.mkdir(exist_ok=True)
    seed = random.randint(1, 10**6)
    scenes = []
    for i, sc in enumerate(script["scenes"]):
        img, aud = work / f"i{i}.jpg", work / f"a{i}.mp3"
        make_image(sc["image_prompt"], img, seed)       # same seed = character look thoda consistent
        asyncio.run(tts(sc["narration"], aud))
        scenes.append({"img": img, "text": sc["narration"], "voice": load_voice(aud)})
    final = OUT / f"{kind}.mp4"
    render_reel(scenes, final, work)
    return final


def send_telegram(video, script, kind):
    label = {"fact": "🤯 Fun Fact", "poem": "🎵 Kavita", "story": "📖 Moral Story"}[kind]
    cap = f"{label}: {script['title']}\n\n{script['caption']}\n\n{' '.join(script.get('hashtags', []))}"
    with open(video, "rb") as f:
        r = requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendVideo",
                          data={"chat_id": TG_CHAT, "caption": cap[:1024], "supports_streaming": "true"},
                          files={"video": f}, timeout=300)
    print("telegram", r.status_code, r.text[:150])


def main():
    kinds = sys.argv[1:] or ["fact", "poem", "story"]
    hist = load_history()
    for kind in kinds:
        try:
            script = make_script(kind, [h["title"] for h in hist])
            video = build_reel(kind, script)
            send_telegram(video, script, kind)
            hist.append({"kind": kind, "title": script["title"], "date": time.strftime("%Y-%m-%d")})
            HISTORY.write_text(json.dumps(hist[-200:], ensure_ascii=False, indent=1))
        except Exception as e:
            print(f"[{kind}] FAILED:", e)
            requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                          data={"chat_id": TG_CHAT, "text": f"⚠️ Kids reel ({kind}) fail hui: {str(e)[:300]}"})


if __name__ == "__main__":
    main()
