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
    for p in ["/usr/share/fonts/truetype/noto/NotoSansDevanagari-Bold.ttf",
              *glob.glob("/usr/share/fonts/**/NotoSansDevanagari*Bold*.ttf", recursive=True),
              *glob.glob("/usr/share/fonts/**/NotoSansDevanagari*.ttf", recursive=True)]:
        if os.path.exists(p):
            return p
    raise RuntimeError("Devanagari font nahi mila (fonts-noto-core install karo)")


def wrap(draw, text, font, max_w):
    lines, cur = [], ""
    for word in text.split():
        test = (cur + " " + word).strip()
        if draw.textlength(test, font=font) <= max_w:
            cur = test
        else:
            lines.append(cur); cur = word
    if cur:
        lines.append(cur)
    return lines


def base_and_caption(img_path, text, base_out, cap_out):
    img = Image.open(img_path).convert("RGB")
    ratio = max(W / img.width, H / img.height)
    img = img.resize((int(img.width * ratio), int(img.height * ratio)))
    l, t = (img.width - W) // 2, (img.height - H) // 2
    img.crop((l, t, l + W, t + H)).save(base_out)

    cap = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(cap)
    font = ImageFont.truetype(find_font(), 64)
    lines = wrap(d, text, font, W - 160)
    lh = 92
    box_h = lh * len(lines) + 70
    y0 = H - 320 - box_h
    d.rounded_rectangle((50, y0, W - 50, y0 + box_h), radius=40, fill=(0, 0, 0, 165))
    y = y0 + 35
    for ln in lines:
        w = d.textlength(ln, font=font)
        d.text(((W - w) / 2, y), ln, font=font, fill=(255, 235, 59, 255), stroke_width=2, stroke_fill=(0, 0, 0, 255))
        y += lh
    cap.save(cap_out)


async def tts(text, path):
    await edge_tts.Communicate(text, VOICE, rate="-8%").save(str(path))


def duration(path):
    o = subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                 "-of", "default=nk=1:nw=1", str(path)])
    return float(o)


def render_scene(base, cap, audio, out, dur, idx):
    frames = int(dur * 30)
    zoom_in = idx % 2 == 0
    z = "min(zoom+0.0007,1.18)" if zoom_in else "if(eq(on,1),1.18,max(zoom-0.0007,1.0))"
    fc = (f"[0:v]scale=2160:3840,zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={W}x{H}:fps=30[v];"
          f"[v][1:v]overlay=0:0:shortest=1,format=yuv420p[o]")
    subprocess.run(["ffmpeg", "-y", "-i", str(base), "-loop", "1", "-i", str(cap), "-i", str(audio),
                    "-filter_complex", fc, "-map", "[o]", "-map", "2:a", "-af", "apad", "-t", f"{dur:.2f}",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-r", "30",
                    "-c:a", "aac", "-ar", "44100", "-ac", "2", str(out)], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def build_reel(kind, script):
    work = OUT / kind; work.mkdir(exist_ok=True)
    segs = []
    seed = random.randint(1, 10**6)
    for i, sc in enumerate(script["scenes"]):
        img, base, cap = work / f"i{i}.jpg", work / f"b{i}.png", work / f"c{i}.png"
        aud, seg = work / f"a{i}.mp3", work / f"s{i}.mp4"
        make_image(sc["image_prompt"], img, seed)       # same seed = character look thoda consistent
        base_and_caption(img, sc["narration"], base, cap)
        asyncio.run(tts(sc["narration"], aud))
        render_scene(base, cap, aud, seg, duration(aud) + 0.5, i)
        segs.append(seg)
    lst = work / "list.txt"
    lst.write_text("".join(f"file '{s.resolve()}'\n" for s in segs))
    final = OUT / f"{kind}.mp4"
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(final)],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
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
