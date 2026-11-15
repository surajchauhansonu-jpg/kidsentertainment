# Mahabharat video bot (GitHub -> Telegram)

Topic do -> Hindi script -> scene images -> Hindi voiceover -> animated 9:16 video (bina subtitle) -> Telegram pe MP4.
Sab kuch GitHub Actions me chalta hai, tumhare PC ki zarurat nahi.

## Setup (ek baar, ~10 min)

1. GitHub pe naya repo banao (**Public** rakho to Actions minutes unlimited free; Private me mahine ke ~2000 min free) aur ye saari files upload karo.
2. Telegram: `@BotFather` -> `/newbot` -> token copy karo. Phir apne bot ko ek message bhejo.
   Chat id ke liye `@userinfobot` ko message karo, wo tumhara numeric id bata dega.
3. Gemini key: https://aistudio.google.com/apikey -> Create API key.
4. Repo me **Settings -> Secrets and variables -> Actions -> New repository secret**:
   - `GEMINI_API_KEY`
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
   - `HF_TOKEN` (optional, image backup ke liye: huggingface.co/settings/tokens, free)
5. **Actions -> Make Video -> Telegram -> Run workflow**. Topic likho (ya khali chhodo) aur Run dabao.
   15-30 min me video Telegram pe aa jayega. Mobile pe GitHub app se bhi Run kar sakte ho.

## Roz apne aap
`.github/workflows/make_video.yml` me `schedule` ki 2 line se `#` hata do.

## Customize
- Music: `assets/music.mp3` daalo.
- Style / voice / model: workflow ke `env` me ye add karo: `STYLE`, `TTS_VOICE` (`hi-IN-SwaraNeural` = female),
  `IMAGE_PROVIDERS` (default `pollinations,huggingface,gemini`), `GEMINI_TEXT_MODEL`.
- Topics: `topics.txt`.

## Dhyan rakho
- Images free AI services se aati hain. Gemini ka image model free tier me band ho sakta hai, isliye default pehle
  Pollinations, phir HuggingFace chalta hai. Quality aur character consistency har video me thodi alag ho sakti hai.
- Mythology ka content: script publish karne se pehle ek baar khud padh lo, AI galti kar sakta hai.
- Telegram bot 50 MB tak ki file bhejta hai, tool khud size chhota kar leta hai.
