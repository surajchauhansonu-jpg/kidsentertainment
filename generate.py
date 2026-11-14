"""Kids reels bot v4 (100% free): code-drawn 2D vector characters with real rig animation
(blink, lip-sync, wave, walk, jump, dance), procedural backgrounds + props, expressive Gemini TTS,
background music, Telegram delivery. Koi AI image API nahi chahiye. Screen par text nahi."""
import os, sys, re, json, asyncio, random, subprocess, time, glob, base64, math, requests
from pathlib import Path
import numpy as np
from PIL import Image
import rig

GEMINI_KEY = os.environ["GEMINI_API_KEY"]
TG_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TG_CHAT = os.environ["TELEGRAM_CHAT_ID"]
MODELS = [m for m in [os.environ.get("GEMINI_MODEL"), "gemini-3.8-flash", "gemini-4-hydrogen", "gemini-3.1-flash-lite"] if m]
TTS_MODELS = [m for m in [os.environ.get("GEMINI_TTS_MODEL"), "gemini-3.1-flash-tts-preview", "gemini-2.5-flash-preview-tts"] if m]
G_VOICE = os.environ.get("GEMINI_VOICE", "Zephyr")          # Zephyr / Puck / Leda / Kore
EDGE_VOICE = os.environ.get("TTS_VOICE", "hi-IN-SwaraNeural")

W, H, FPS, SR = 1080, 1920, 30, 44100
GROUND = 1500
OUT = Path("out"); OUT.mkdir(exist_ok=True)
HISTORY = Path("history.json")

TASKS = {
    "fact": {"scenes": 8, "brief": "6 se 10 saal ke bachon ke liye ek hairat-angez, sachchha FUN FACT (science, janwar, space, body, nature). "
                                   "Pehle scene me sawaal/hook, beech me 5 chhote majedar vakya, ant me 'Kya aapko pata tha?'."},
    "poem": {"scenes": 8, "brief": "6 se 10 saal ke bachon ke liye ek chhoti, lay wali BAAL KAVITA (rhyme zaroori, har scene me 2 line, mazedaar)."},
    "story": {"scenes": 9, "brief": "6 se 10 saal ke bachon ke liye ek chhoti MORAL STORY (do dost jaanwar), saaf seekh ke saath, ant me moral ek line me."},
}


def load_history():
    return json.loads(HISTORY.read_text()) if HISTORY.exists() else []


# ----------------------------- Gemini text -----------------------------
def gemini(prompt):
    base_cfg = {"responseMimeType": "application/json", "temperature": 1.0}
    headers = {"x-goog-api-key": GEMINI_KEY}
    last = ""
    for model in MODELS:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        use_think = True
        for attempt in range(3):
            cfg = dict(base_cfg)
            if use_think:
                cfg["thinkingConfig"] = {"thinkingLevel": "low"}
            body = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": cfg}
            try:
                r = requests.post(url, json=body, headers=headers, timeout=90)
            except requests.exceptions.RequestException as e:
                last = f"{model}: {type(e).__name__}"; print("Gemini error", last); time.sleep(5); continue
            if r.ok:
                try:
                    return json.loads(r.json()["candidates"][0]["content"]["parts"][0]["text"])
                except Exception as e:
                    last = f"{model}: bad JSON ({type(e).__name__})"; print("Gemini error", last); continue
            last = f"{model}: HTTP {r.status_code} {r.text[:150]}"; print("Gemini error", last)
            if r.status_code == 404:
                break
            if r.status_code == 400 and use_think:
                use_think = False; continue
            time.sleep(10)
    raise RuntimeError("Gemini fail: " + last)


def make_script(kind, used):
    t = TASKS[kind]
    topic = random.choice(["jungle", "samundar", "aasman", "khana", "school", "dosti", "mausam", "insaan ka sharir",
                           "kisan", "tyohar", "chidiya", "machhli", "chand-taare", "ped-paudhe", "titli", "baarish"])
    prompt = f"""Tum bachon ki cartoon reels (Hindi nursery-rhyme channels jaisi) ke scriptwriter ho.
Kaam: {t['brief']}
Topic ka hint (zaroori nahi): {topic}
In titles ko REPEAT mat karna: {used[-40:]}
Bhasha: saral Hindi (Devanagari). Exactly {t['scenes']} chhote scenes (har scene 2-4 second).

Reel ke host cartoon characters sirf in me se chuno: {list(rig.CHARACTERS)}. "cast" me 1 ya 2 characters do.
Har scene me:
 - "narration": voiceover, SIRF 1 chhota vakya (8-12 shabd), Devanagari. Screen par likha nahi jayega.
 - "bg": {rig.BACKGROUNDS} me se ek (kahani ke mood ke hisaab se, scenes me badalte raho).
 - "chars": 1 ya 2 characters [{{"who": cast me se, "action": {rig.ACTIONS} me se, "emotion": "happy"|"neutral"|"surprised"}}]. Pehla character wahi hai jiska muh voice ke saath hilta hai. Actions har scene me badalte raho. Pehle scene me "wave", ant me "jump" ya "dance".
 - "props": 0 se 3 cheezein {rig.PROPS} me se jo narration se milti hon (jaise machhli ki baat ho to "fish", raat ho to "moon","star").
Sirf JSON me jawab do:
{{"title": "...", "caption": "Instagram caption Hindi me 1-2 line + emoji", "hashtags": ["#..",".."], "cast": ["bunny"], "scenes": [{{"narration": "...", "bg": "meadow", "chars": [{{"who": "bunny", "action": "wave", "emotion": "happy"}}], "props": ["sun"]}}]}}"""
    return sanitize(gemini(prompt))


def sanitize(script):
    cast = [c for c in script.get("cast", []) if c in rig.CHARACTERS][:2] or ["bunny"]
    scenes = []
    for sc in script.get("scenes", []):
        chars = []
        for c in sc.get("chars", [])[:2]:
            chars.append({"who": c.get("who") if c.get("who") in rig.CHARACTERS else cast[0],
                          "action": c.get("action") if c.get("action") in rig.ACTIONS else "talk",
                          "emotion": c.get("emotion") if c.get("emotion") in ("happy", "neutral", "surprised") else "happy"})
        if not chars:
            chars = [{"who": cast[0], "action": "talk", "emotion": "happy"}]
        scenes.append({"narration": str(sc.get("narration", "")).strip() or "...",
                       "bg": sc.get("bg") if sc.get("bg") in rig.BACKGROUNDS else "meadow",
                       "chars": chars,
                       "props": [p for p in sc.get("props", []) if p in rig.PROPS][:3]})
    if not scenes:
        raise RuntimeError("Script me scenes nahi aaye")
    script["cast"], script["scenes"] = cast, scenes
    script.setdefault("title", "Kids reel"); script.setdefault("caption", ""); script.setdefault("hashtags", [])
    return script


# ----------------------------- voice -----------------------------
def pcm_to_voice(pcm, rate):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-f", "s16le", "-ar", str(rate), "-ac", "1", "-i", "-",
                          "-f", "s16le", "-ac", "1", "-ar", str(SR), "-"], input=pcm, capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0


def load_audio(path):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-f", "s16le", "-ac", "1", "-ar", str(SR), "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0


def trim_voice(x):
    idx = np.where(np.abs(x) > 0.012)[0]
    if len(idx) == 0:
        return x
    x = x[max(0, idx[0] - int(0.04 * SR)): min(len(x), idx[-1] + int(0.10 * SR))]
    return x / (np.abs(x).max() + 1e-6) * 0.9


def gemini_tts(text):
    prompt = ("Hindi me ye line ek khush, energetic, mazedaar kahani sunane wale andaaz me bolo, chhote bachon ke liye, "
              "saaf uchcharan, thodi expression ke saath: " + text)
    body = {"contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseModalities": ["AUDIO"],
                                 "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": G_VOICE}}}}}
    headers = {"x-goog-api-key": GEMINI_KEY}
    last = ""
    for model in TTS_MODELS:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        for attempt in range(3):
            try:
                r = requests.post(url, json=body, headers=headers, timeout=120)
            except requests.exceptions.RequestException as e:
                last = f"{model}: {type(e).__name__}"; time.sleep(5); continue
            if r.ok:
                try:
                    part = r.json()["candidates"][0]["content"]["parts"][0]["inlineData"]
                    m = re.search(r"rate=(\d+)", part.get("mimeType", ""))
                    return pcm_to_voice(base64.b64decode(part["data"]), int(m.group(1)) if m else 24000)
                except Exception as e:
                    last = f"{model}: bad audio ({type(e).__name__})"; continue
            last = f"{model}: HTTP {r.status_code} {r.text[:120]}"; print("TTS error", last)
            if r.status_code == 404:
                break
            time.sleep(20 if r.status_code == 429 else 8)
    raise RuntimeError("Gemini TTS fail: " + last)


def edge_voice(text, path):
    import edge_tts
    asyncio.run(edge_tts.Communicate(text, EDGE_VOICE, rate="-5%").save(str(path)))
    return load_audio(path)


def make_voices(texts, work):
    try:
        out = []
        for t in texts:
            out.append(trim_voice(gemini_tts(t))); time.sleep(3)
        return out, "gemini"
    except Exception as e:
        print("Gemini TTS nahi chali, Edge-TTS use hoga:", e)
        return [trim_voice(edge_voice(t, work / f"a{i}.mp3")) for i, t in enumerate(texts)], "edge"


# ----------------------------- music / audio mix -----------------------------
def synth_music(dur):
    """Halka marimba loop (built-in placeholder). Asli music ke liye music/ folder me mp3 daalo."""
    bpm = 104; beat = 60 / bpm; n = int((dur + 2) * SR)
    out = np.zeros(n, dtype=np.float32); rng = np.random.default_rng(11)
    mid = lambda m: 440.0 * 2 ** ((m - 69) / 12)

    def pluck(f, length, amp):
        t = np.arange(int(length * SR)) / SR
        return ((np.sin(2 * np.pi * f * t) + 0.35 * np.sin(4 * np.pi * f * t) + 0.12 * np.sin(6 * np.pi * f * t)) * np.exp(-t * 5.5) * amp).astype(np.float32)

    def put(sig, at):
        a = int(at * SR)
        if a < n:
            out[a:a + len(sig)] += sig[:max(0, n - a)]
    chords = [(48, 0, 4, 7), (43, 0, 4, 7), (45, 0, 3, 7), (41, 0, 4, 7)]
    penta = [0, 2, 4, 7, 9]; bar, t = 0, 0.0
    while t < dur + 1:
        root, *tones = chords[bar % 4]
        put(pluck(mid(root), beat * 1.8, 0.5), t); put(pluck(mid(root + 12), beat * 1.2, 0.25), t + 2 * beat)
        for k in range(8):
            at = t + k * beat / 2
            if rng.random() < 0.72:
                put(pluck(mid(72 + root % 12 + int(rng.choice(tones if k % 2 == 0 else penta))), beat * 0.9, 0.22), at)
            nz = rng.standard_normal(int(0.05 * SR)).astype(np.float32) * np.exp(-np.arange(int(0.05 * SR)) / (0.012 * SR))
            put(nz * 0.03, at)
        bar += 1; t += 4 * beat
    return out / (np.abs(out).max() + 1e-6) * 0.7


def get_music(dur):
    files = sorted(glob.glob("music/*.mp3") + glob.glob("music/*.wav"))
    if files:
        m = load_audio(random.choice(files))
        if len(m) > 0:
            start = random.randint(0, max(0, len(m) - int(dur * SR))) if len(m) > dur * SR * 1.5 else 0
            m = m[start:]
            return (np.tile(m, int(np.ceil((dur * SR + 1) / len(m))))[:int(dur * SR) + SR] / (np.abs(m).max() + 1e-6)) * 0.8
    return synth_music(dur)


def whoosh(d=0.4):
    n = int(SR * d); noise = np.random.default_rng(3).standard_normal(n).astype(np.float32)
    out = np.zeros(n, dtype=np.float32); y = 0.0
    for i in range(n):
        y += (0.015 + 0.35 * (i / n)) * (noise[i] - y); out[i] = y
    out *= np.sin(np.pi * np.linspace(0, 1, n)) ** 2
    return out / (np.abs(out).max() + 1e-6) * 0.2


def write_wav(path, x):
    import wave
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype(np.int16).tobytes())


def mix_track(voice_track, music):
    n = len(voice_track); music = np.pad(music, (0, max(0, n - len(music))))[:n]
    win = int(0.05 * SR); env = np.convolve(np.abs(voice_track), np.ones(win) / win, mode="same")
    env = np.clip(env / 0.12, 0, 1); sm = int(0.3 * SR); env = np.convolve(env, np.ones(sm) / sm, mode="same")
    mix = voice_track + music * (0.24 - 0.13 * env)           # voice ke waqt music dheema
    fi, fo = int(0.4 * SR), int(1.2 * SR)
    mix[:fi] *= np.linspace(0, 1, fi); mix[-fo:] *= np.linspace(1, 0, fo)
    return np.clip(mix / max(1.0, np.abs(mix).max() / 0.92), -1, 1).astype(np.float32)


# ----------------------------- animation / render -----------------------------
def ease(x):
    x = max(0.0, min(1.0, x)); return x * x * (3 - 2 * x)


def ease_out_back(x):
    x = max(0.0, min(1.0, x)); c1, c3 = 1.70158, 2.70158
    return 1 + c3 * (x - 1) ** 3 + c1 * (x - 1) ** 2


CAM = [(1.00, 1.10, -0.3, 0.4, 0.0, 0.1), (1.10, 1.01, 0.4, -0.3, 0.1, -0.1),
       (1.02, 1.14, 0.0, 0.0, 0.3, -0.2), (1.12, 1.00, -0.4, 0.3, -0.2, 0.2)]


def camera_box(idx, t, dur):
    z0, z1, p0, p1, q0, q1 = CAM[idx % len(CAM)]
    e = ease(t / dur); z = z0 + (z1 - z0) * e
    px = p0 + (p1 - p0) * e + 0.03 * math.sin(t * 2.1); py = q0 + (q1 - q0) * e + 0.03 * math.sin(t * 1.7 + 1)
    bw, bh = W / z, H / z; sx, sy = (W - bw) / 2, (H - bh) / 2
    return sx + max(-1, min(1, px)) * sx, sy + max(-1, min(1, py)) * sy, bw, bh, z


def voice_envelope(voice, n):
    hop = SR // FPS
    e = np.array([np.sqrt(np.mean(voice[i * hop:(i + 1) * hop] ** 2) + 1e-9) if i * hop < len(voice) else 0.0 for i in range(n)])
    e = np.clip(e / (np.percentile(e, 92) + 1e-6), 0, 1)
    return np.convolve(e, [0.25, 0.5, 0.25], mode="same")


PROP_SIZE = {"sun": 250, "moon": 230, "star": 150, "cloud": 330, "bird": 170, "balloon": 230, "rainbow": 400, "butterfly": 150,
             "heart": 150, "flower": 170, "apple": 150, "fish": 240, "tree": 400}
SKY_SLOTS = [(210, 330), (860, 400), (540, 190)]
GROUND_SLOTS = [(140, 1400), (950, 1400), (540, 1250)]
_STATE = {}


def _assets():
    if "vig" not in _STATE:
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        r = np.sqrt(((xx - W / 2) / (W / 2)) ** 2 + ((yy - H / 2) / (H / 2)) ** 2) / 1.41
        _STATE["vig"] = Image.fromarray((np.clip((r - 0.62) / 0.38, 0, 1) ** 1.8 * 70).astype(np.uint8), "L")
        _STATE["black"] = Image.new("RGB", (W, H), (0, 0, 0))
        sh = np.zeros((60, 240, 4), np.uint8); yy, xx = np.mgrid[0:60, 0:240]
        a = np.clip(1 - np.sqrt(((xx - 120) / 120) ** 2 + ((yy - 30) / 30) ** 2), 0, 1)
        sh[..., 3] = (a * 110).astype(np.uint8)
        _STATE["shadow"] = Image.fromarray(sh, "RGBA")
    return _STATE


def scene_frames(sc, bg, voice, idx, prev_last):
    A = _assets()
    dur = len(voice) / SR + 0.35
    n = int(dur * FPS)
    env = voice_envelope(voice, n)
    chars = sc["chars"]
    if len(chars) == 1:
        xs, base = [540], 1.40
    else:
        xs, base = [330, 770], 1.10
    props = []
    s_i = g_i = 0
    for p in sc["props"]:
        if p in rig.SKY_PROPS:
            pos = SKY_SLOTS[s_i % 3]; s_i += 1
        else:
            pos = GROUND_SLOTS[g_i % 3]; g_i += 1
        props.append((p, pos))
    for f in range(n):
        t = f / FPS
        left, top, bw, bh, z = camera_box(idx, t, dur)
        k = W / bw
        frame = bg.resize((W, H), Image.BICUBIC, box=(left, top, left + bw, top + bh))
        # props
        for i, (name, (px, py)) in enumerate(props):
            sz = int(PROP_SIZE[name] * k * (0.35 + 0.65 * ease_out_back((t - 0.1 * i) / 0.45)))
            if sz < 12:
                continue
            im = rig.draw_prop(name, sz, t + i)
            bx, by = rig.prop_bob(name, t, i)
            X, Y = (px + bx - left) * k, (py + by - top) * H / bh
            frame.paste(im, (int(X - im.width / 2), int(Y - im.height / 2)), im)
        # characters (back to front: speaker last so mouth is on top)
        order = list(range(len(chars)))[::-1]
        for ci in order:
            c = chars[ci]
            pose = rig.make_pose(c["action"], t, float(env[f]) if ci == 0 else 0.0, c["emotion"], ph=ci * 1.9)
            wx = xs[ci] + (-170 + 340 * ease(t / dur) if c["action"] == "walk" else 0)
            spx = base * k
            im = rig.draw_critter(c["who"], pose, spx)
            sq = pose["squash"]
            if abs(sq - 1) > 0.005:
                im = im.resize((int(im.width * (1 + (1 - sq) * 0.7)), int(im.height * sq)), Image.BICUBIC)
            ax, ay = im.width * rig.OX / rig.CW, im.height * rig.OY / rig.CH
            X, Y = (wx - left) * k, (GROUND - top) * H / bh
            jump = pose["jump"] * spx
            shw = int(250 * spx * (1 - 0.35 * pose["jump"] / 120))
            shd = A["shadow"].resize((max(10, shw), max(4, shw // 4)))
            frame.paste(shd, (int(X - shd.width / 2), int(Y - shd.height / 2 + 6)), shd)
            frame.paste(im, (int(X - ax), int(Y - ay - jump)), im)
        frame.paste(A["black"], (0, 0), A["vig"])
        if prev_last is not None and f < 6:
            frame = Image.blend(prev_last, frame, ease((f + 1) / 6))
        yield frame


def render_reel(script, voices, out_path, work):
    scenes = script["scenes"]
    durs = [len(v) / SR + 0.35 for v in voices]
    total = int(sum(durs) * SR) + SR // 2
    track = np.zeros(total, dtype=np.float32); wh = whoosh(); pos = 0.0
    for i, (v, d) in enumerate(zip(voices, durs)):
        a = int(pos * SR); track[a:a + len(v)] += v
        if i > 0 and i % 2 == 1:
            b = max(0, a - int(0.05 * SR)); track[b:b + len(wh)] += wh[:max(0, total - b)]
        pos += d
    audio = mix_track(track, get_music(total / SR))
    wav = Path(work) / "mix.wav"; write_wav(wav, audio)
    cmd = ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
           "-i", str(wav), "-map", "0:v", "-map", "1:a", "-af", "loudnorm=I=-14:TP=-1.5:LRA=11",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "160k", "-shortest", str(out_path)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    prev, seed = None, random.randint(1, 999)
    for i, sc in enumerate(scenes):
        bg = rig.make_bg(sc["bg"], seed + i)
        last = None
        for fr in scene_frames(sc, bg, voices[i], i, prev):
            proc.stdin.write(fr.tobytes()); last = fr
        prev = last
    proc.stdin.close()
    if proc.wait() != 0:
        raise RuntimeError("ffmpeg final render fail")


def build_reel(kind, script):
    work = OUT / kind; work.mkdir(exist_ok=True)
    voices, engine = make_voices([sc["narration"] for sc in script["scenes"]], work)
    print("voice engine:", engine)
    final = OUT / f"{kind}.mp4"
    render_reel(script, voices, final, work)
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
