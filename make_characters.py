#!/usr/bin/env python3
"""
One-time tool: creates rig-ready cut-out characters (transparent PNG) for the video bot.

  python make_characters.py                 -> uses env NAMES (comma list or 'all'), PICK, REDO
  NAMES=Krishna,Arjun   -> generate 4 candidates each, auto-pick the best one into characters/<Name>.png
  PICK=Arjun=2          -> just copy candidate 2 as the final Arjun (no generation)
Candidates are saved in characters/_cand/. A contact sheet of each is sent to Telegram.
"""
import json
import os
import shutil
import sys
from pathlib import Path

import numpy as np
import requests
from PIL import Image, ImageDraw

import main as M

CHAR = Path("characters")
CAND = CHAR / "_cand"
N_CAND = 4
POSE = ("full body character design, standing straight, facing the viewer, arms hanging slightly away from the body, "
        "legs slightly apart, whole body from head to feet fully visible with space around, "
        "plain flat solid light grey background, no other objects, no ground, no text")


def cutout(src, dst):
    from rembg import new_session, remove

    global _S
    try:
        _S
    except NameError:
        _S = new_session("isnet-anime")
    im = Image.open(src).convert("RGB")
    out = remove(im, session=_S)
    out.save(dst)
    return out


def score(png):
    a = np.array(Image.open(png))[..., 3] > 128
    if a.sum() < 1000:
        return -1
    ys, xs = np.where(a)
    H, W = a.shape
    sc = 0.0
    sc += 2 if ys.min() > 0.02 * H and ys.max() < 0.98 * H else 0        # whole body inside frame
    aspect = (xs.max() - xs.min()) / (ys.max() - ys.min() + 1)
    sc += 2 if 0.22 < aspect < 0.6 else 0                                # standing, arms not spread wide
    sc += 1 if (ys.max() - ys.min()) > 0.7 * H else 0                    # big enough
    sc += 1 if xs.min() > 0.02 * W and xs.max() < 0.98 * W else 0
    return sc


def sheet(paths, label):
    ims = [Image.open(p).convert("RGBA") for p in paths]
    h = 520
    tiles = []
    for k, im in enumerate(ims, 1):
        im = im.resize((int(im.width * h / im.height), h))
        bg = Image.new("RGBA", im.size, (70, 150, 70, 255))
        bg.alpha_composite(im)
        d = ImageDraw.Draw(bg)
        d.rectangle([0, 0, 60, 40], fill=(0, 0, 0, 255))
        d.text((20, 12), str(k), fill=(255, 255, 255, 255))
        tiles.append(bg.convert("RGB"))
    W = sum(t.width for t in tiles)
    out = Image.new("RGB", (W, h))
    x = 0
    for t in tiles:
        out.paste(t, (x, 0))
        x += t.width
    p = CAND / f"{label}_sheet.jpg"
    out.save(p, quality=85)
    return p


def telegram_photo(path, caption):
    if not (os.getenv("TELEGRAM_BOT_TOKEN") and os.getenv("TELEGRAM_CHAT_ID")):
        return
    with open(path, "rb") as f:
        requests.post(f"https://api.telegram.org/bot{os.environ['TELEGRAM_BOT_TOKEN']}/sendPhoto",
                      data={"chat_id": os.environ["TELEGRAM_CHAT_ID"], "caption": caption[:900]},
                      files={"photo": f}, timeout=120)


def main():
    CAND.mkdir(parents=True, exist_ok=True)
    desc = json.loads(Path("characters.json").read_text(encoding="utf-8"))
    pick = os.getenv("PICK", "").strip()
    if pick:
        for item in pick.split(","):
            name, n = [x.strip() for x in item.split("=")]
            shutil.copy(CAND / f"{name}_{n}.png", CHAR / f"{name}.png")
            print(f"{name}: candidate {n} selected")
        return

    names = os.getenv("NAMES", "Krishna").strip()
    names = list(desc) if names.lower() == "all" else [n.strip() for n in names.split(",") if n.strip()]
    redo = os.getenv("REDO", "false").lower() == "true"
    for name in names:
        if name not in desc:
            print(f"skip {name}: characters.json me nahi hai")
            continue
        if (CHAR / f"{name}.png").exists() and not redo:
            print(f"skip {name}: pehle se hai (REDO=true se dobara banao)")
            continue
        print(f"=== {name}")
        paths = []
        for i in range(1, N_CAND + 1):
            raw = M.WORK / f"{name}_{i}.jpg"
            M.WORK.mkdir(exist_ok=True)
            try:
                M.make_image(f"{desc[name]}. {POSE}. Style: {M.STYLE}", i, raw)
                dst = CAND / f"{name}_{i}.png"
                cutout(raw, dst)
                paths.append(dst)
            except Exception as e:  # noqa: BLE001
                print(f"  candidate {i} failed: {str(e)[:120]}")
        if not paths:
            continue
        best = max(paths, key=score)
        shutil.copy(best, CHAR / f"{name}.png")
        sh = sheet(paths, name)
        telegram_photo(sh, f"{name}: auto-pick = {best.stem.split('_')[-1]}. Dusra chahiye to workflow me pick likho, jaise {name}=2")
        print(f"  auto-picked {best.name}")


if __name__ == "__main__":
    main()
