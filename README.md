# Polished kids reel generator

Run `generate.py` from this folder so it imports the matching `rig.py`. The renderer now adds Hindi subtitles and a scene progress rail by default, richer foreground/background details, a more specific per-scene visual brief, and higher-quality H.264 encoding.

## Requirements

- Python 3 with `numpy`, `Pillow`, and `requests`
- `ffmpeg` available on PATH
- `GEMINI_API_KEY` set for script generation and narration
- Optional `edge-tts` if Gemini narration is unavailable

Set `REEL_SUBTITLES=0` to hide captions. Set `REEL_FONT` to a Devanagari-capable `.ttf` file if the system font is not found automatically. Output reels are saved under `out/`.

Telegram posting is off by default. Set `SEND_TELEGRAM=1` plus `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` only when you want the generated reel posted.
