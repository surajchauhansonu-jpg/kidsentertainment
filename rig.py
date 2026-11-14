"""Free 2D vector rig: characters (bunny/bear/cat/panda), backgrounds, props - sab code se bante hain.
Koi AI image API nahi chahiye. Characters ke aankh jhapakti hai, muh awaaz ke saath khulta hai,
haath-pair hilte hain (wave / walk / jump / dance / think / surprised)."""
import math, random
import numpy as np
from PIL import Image, ImageDraw

OL = (58, 36, 56)           # outline color (dark plum)
SS = 2                      # supersampling
CW, CH, OX, OY = 520, 700, 260, 680   # character canvas (design units), feet anchor (OX, OY)

CHARACTERS = {
    "bunny": dict(body=(250, 247, 252), belly=(255, 255, 255), limb=(250, 247, 252), hand=(250, 247, 252), inner=(255, 175, 195),
                  nose=(255, 110, 150), cheek=(255, 165, 185), ear="long", tail="puff", patch=None),
    "bear": dict(body=(176, 112, 72), belly=(232, 196, 150), limb=(176, 112, 72), hand=(176, 112, 72), inner=(222, 170, 120),
                 nose=(60, 40, 44), cheek=(240, 140, 120), ear="round", tail="puff", patch=None),
    "cat": dict(body=(255, 163, 64), belly=(255, 232, 190), limb=(255, 163, 64), hand=(255, 163, 64), inner=(255, 170, 180),
                nose=(255, 120, 140), cheek=(255, 140, 130), ear="point", tail="long", patch=None, stripes=(214, 110, 30)),
    "panda": dict(body=(252, 252, 252), belly=(255, 255, 255), limb=(44, 44, 52), hand=(44, 44, 52), inner=(44, 44, 52),
                  nose=(40, 40, 48), cheek=(255, 170, 180), ear="round", tail="puff", patch=(44, 44, 52)),
}
HUMANS = {
    "dad": dict(size=1.00, skin=(222, 170, 128), hair=(38, 30, 36), style="short", top=(70, 120, 205), top_style="shirt",
                bottom=(62, 66, 96), bottom_style="pants", shoe=(50, 40, 44), leg_h=185, sh=400, tw=156, hrx=96, hry=104, mous=True),
    "mom": dict(size=0.93, skin=(226, 176, 136), hair=(34, 26, 32), style="bun", top=(214, 62, 122), top_style="kurta",
                bottom=(255, 238, 200), bottom_style="salwar", shoe=(190, 130, 60), leg_h=180, sh=380, tw=140, hrx=92, hry=100,
                dupatta=(54, 170, 170), bindi=True, gold=True, trim=(255, 205, 70)),
    "boy": dict(size=0.74, skin=(228, 178, 138), hair=(30, 24, 30), style="boy", top=(240, 90, 70), top_style="shirt",
                bottom=(62, 112, 192), bottom_style="shorts", shoe=(250, 250, 250), leg_h=140, sh=300, tw=126, hrx=112, hry=118),
    "girl": dict(size=0.70, skin=(228, 178, 138), hair=(34, 24, 30), style="pigtails", top=(255, 128, 180), top_style="frock",
                 bottom=(255, 128, 180), bottom_style="skirt", shoe=(214, 56, 108), leg_h=140, sh=300, tw=118, hrx=112, hry=118,
                 ribbon=(255, 226, 70), gold=True, trim=(255, 226, 70)),
}
ACTIONS = ["talk", "wave", "walk", "jump", "dance", "think", "surprised"]
BACKGROUNDS = ["meadow", "night", "room", "pond", "forest", "space"]
PROPS = ["sun", "moon", "star", "cloud", "flower", "apple", "fish", "bird", "heart", "balloon", "rainbow", "tree", "butterfly"]
SKY_PROPS = {"sun", "moon", "star", "cloud", "bird", "balloon", "rainbow", "butterfly", "heart"}


# ------------------------------------------------------------------ drawing helper
class Pen:
    def __init__(self, w, h, ox, oy, sc):
        self.sc, self.ox, self.oy = sc, ox, oy
        self.img = Image.new("RGBA", (int(w * sc), int(h * sc)), (0, 0, 0, 0))
        self.d = ImageDraw.Draw(self.img)

    def p(self, x, y):
        return ((self.ox + x) * self.sc, (self.oy + y) * self.sc)

    def ell(self, cx, cy, rx, ry, fill, ow=5, ol=OL):
        x0, y0 = self.p(cx - rx, cy - ry); x1, y1 = self.p(cx + rx, cy + ry)
        self.d.ellipse((x0, y0, x1, y1), fill=fill, outline=ol if ow else None, width=max(1, int(ow * self.sc)))

    def poly(self, pts, fill, ow=5, ol=OL):
        q = [self.p(x, y) for x, y in pts]
        self.d.polygon(q, fill=fill)
        if ow:
            self.d.line(q + [q[0]], fill=ol, width=int(ow * self.sc), joint="curve")

    def chain(self, pts, width, fill, ow=5, ol=OL):
        q = [self.p(x, y) for x, y in pts]; s = self.sc
        for col, wd in ((ol, width + 2 * ow), (fill, width)):
            if ow == 0 and col == ol:
                continue
            self.d.line(q, fill=col, width=int(wd * s), joint="curve")
            r = wd * s / 2
            for x, y in q:
                self.d.ellipse((x - r, y - r, x + r, y + r), fill=col)

    def arc(self, cx, cy, rx, ry, a0, a1, width, color=OL):
        x0, y0 = self.p(cx - rx, cy - ry); x1, y1 = self.p(cx + rx, cy + ry)
        self.d.arc((x0, y0, x1, y1), a0, a1, fill=color, width=int(width * self.sc))

    def line(self, pts, width, color=OL):
        q = [self.p(x, y) for x, y in pts]; self.d.line(q, fill=color, width=int(width * self.sc), joint="curve")
        r = width * self.sc / 2
        for x, y in (q[0], q[-1]):
            self.d.ellipse((x - r, y - r, x + r, y + r), fill=color)


def ell_pts(cx, cy, rx, ry, ang=0, n=40):
    ca, sa = math.cos(math.radians(ang)), math.sin(math.radians(ang)); out = []
    for i in range(n):
        a = 2 * math.pi * i / n; x, y = rx * math.cos(a), ry * math.sin(a)
        out.append((cx + x * ca - y * sa, cy + x * sa + y * ca))
    return out


# ------------------------------------------------------------------ character
def draw_critter(who, pose, sc):
    """Upright RGBA character image. sc = pixels per design unit. Feet anchor = (OX*sc, OY*sc)."""
    if who in HUMANS:
        return draw_human(who, pose, sc)
    spec = CHARACTERS[who]
    body = Pen(CW, CH, OX, OY, sc * SS); head = Pen(CW, CH, OX, OY, sc * SS)
    bob = pose["bob"]

    # tail
    if spec["tail"] == "puff":
        body.ell(112, -105, 36, 36, spec["body"] if who != "panda" else spec["limb"])
    else:
        body.chain([(95, -100), (150, -120), (175, -190), (150, -260)], 24, spec["body"])

    # legs
    for side in (-1, 1):
        phi = pose["phi"] + (0 if side < 0 else math.pi)
        fx = side * 52 + pose["amp"] * 42 * math.sin(phi)
        fy = -10 - pose["amp"] * 26 * max(0.0, math.cos(phi))
        body.chain([(side * 52, -80), (fx, fy)], 50, spec["limb"])
        body.ell(fx + side * 6, fy + 2, 44, 21, spec["limb"])

    # body + belly
    body.ell(0, -150, 108, 122, spec["body"])
    body.ell(0, -135, 68, 86, spec["belly"], ow=0)

    # arms
    for side, a1, a2 in ((-1, pose["aL"], pose["fL"]), (1, pose["aR"], pose["fR"])):
        s = (side * 98, -215 + bob)
        r1, r2 = math.radians(a1), math.radians(a1 + a2)
        e = (s[0] + side * 78 * math.sin(r1), s[1] + 78 * math.cos(r1))
        h = (e[0] + side * 68 * math.sin(r2), e[1] + 68 * math.cos(r2))
        body.chain([s, e, h], 38, spec["limb"])
        body.ell(h[0], h[1], 25, 25, spec["hand"])

    # ----- head layer
    hy = -345 + bob
    ear = pose["ear"]
    if spec["ear"] == "long":
        for side in (-1, 1):
            ang = side * (10 + ear)
            head.poly(ell_pts(side * 62, hy - 170, 38, 100, ang), spec["body"])
            head.poly(ell_pts(side * 62, hy - 165, 20, 72, ang), spec["inner"], ow=0)
    elif spec["ear"] == "round":
        for side in (-1, 1):
            head.ell(side * 104, hy - 92, 44, 44, spec["inner"] if who == "panda" else spec["body"])
            if who != "panda":
                head.ell(side * 104, hy - 92, 22, 22, spec["inner"], ow=0)
    else:
        for side in (-1, 1):
            tri = [(side * 125, hy - 55), (side * 112 + side * ear, hy - 175), (side * 42, hy - 100)]
            head.poly(tri, spec["body"])
            head.poly([(side * 108, hy - 80), (side * 103 + side * ear, hy - 140), (side * 62, hy - 100)], spec["inner"], ow=0)

    head.ell(0, hy, 138, 120, spec["body"])
    if who != "bunny":
        head.ell(0, hy + 38, 62, 44, spec["belly"], ow=0)
    else:
        head.ell(0, hy + 36, 56, 40, (255, 255, 255), ow=0)
    if spec.get("stripes"):
        for dx in (-26, 0, 26):
            head.chain([(dx, hy - 118), (dx * 0.8, hy - 82)], 9, spec["stripes"], ow=0)
    if spec["patch"]:
        for side in (-1, 1):
            head.poly(ell_pts(side * 56, hy + 6, 40, 54, side * 22), spec["patch"], ow=0)

    # eyes
    blink = pose["blink"]
    for side in (-1, 1):
        ex, ey = side * 56, hy + 2
        if pose["eyes"] == "happy" or blink < 0.18:
            head.arc(ex, ey, 30, 24 if pose["eyes"] == "happy" else 14, 200, 340, 8,
                     (255, 255, 255) if who == "panda" and spec["patch"] else OL)
            if who == "panda" and False:
                pass
        else:
            ry = 38 * pose["eyeS"] * blink
            head.ell(ex, ey, 33 * (1 + (pose["eyeS"] - 1) * 0.6), ry, (255, 255, 255), ow=4)
            lx, ly = pose["look"]
            px, py = ex + lx * 12, ey + ly * 12 + (6 if ry > 30 else 0)
            head.ell(px, py, 19 * min(1.0, ry / 34), min(19, ry * 0.55), (30, 24, 44), ow=0)
            head.ell(px - 6, py - 7, 6, 6, (255, 255, 255), ow=0)
    # cheeks, nose, mouth
    for side in (-1, 1):
        head.ell(side * 98, hy + 40, 24, 16, spec["cheek"], ow=0)
    head.ell(0, hy + 24, 17, 12, spec["nose"], ow=3)
    head.line([(0, hy + 34), (0, hy + 48)], 4)
    m = pose["mouth"]
    if m > 0.12:
        mh = 8 + 34 * min(1.0, m)
        head.ell(0, hy + 56 + mh * 0.35, 30, mh, (150, 36, 60), ow=4)
        head.ell(0, hy + 56 + mh * 0.75, 17, mh * 0.38, (255, 120, 140), ow=0)
    else:
        head.arc(0, hy + 40, 36, 20, 15, 165, 6)
    if who == "cat":
        for side in (-1, 1):
            for dy in (-6, 14):
                head.line([(side * 70, hy + 38 + dy * 0.4), (side * 150, hy + 28 + dy)], 3)

    # head tilt around neck, then combine
    pivot = ((OX + 0) * sc * SS, (OY - 235) * sc * SS)
    h_img = head.img.rotate(pose["tilt"], resample=Image.BICUBIC, center=pivot)
    out = Image.alpha_composite(body.img, h_img)
    return out.reduce(SS)



def size_of(who):
    return HUMANS[who]["size"] if who in HUMANS else 1.0


def _dark(c, f=0.86):
    return tuple(int(v * f) for v in c)


def draw_human(who, pose, sc):
    sp = HUMANS[who]
    sc2 = sc * sp["size"]
    body = Pen(CW, CH, OX, OY, sc2 * SS); head = Pen(CW, CH, OX, OY, sc2 * SS)
    skin, bob = sp["skin"], pose["bob"]
    sh, tw, lh, hrx, hry = sp["sh"], sp["tw"], sp["leg_h"], sp["hrx"], sp["hry"]
    hy = -sh - hry + 14 + bob
    kid = who in ("boy", "girl")

    # neck
    body.poly([(-20, hy + hry - 8), (20, hy + hry - 8), (20, -sh + 18), (-20, -sh + 18)], skin, ow=4)

    # legs
    hipx = tw * 0.24
    for side in (-1, 1):
        phi = pose["phi"] + (0 if side < 0 else math.pi)
        fx = side * hipx + pose["amp"] * 38 * math.sin(phi)
        fy = -8 - pose["amp"] * 24 * max(0.0, math.cos(phi))
        hip = (side * hipx, -lh + 20)
        bs = sp["bottom_style"]
        if bs in ("pants", "salwar"):
            body.chain([hip, (fx, fy - 14)], 50 if bs == "pants" else 46, sp["bottom"])
        else:
            body.chain([hip, (fx, fy - 14)], 30, skin)
            if bs == "shorts":
                mid = (hip[0] + (fx - hip[0]) * 0.38, hip[1] + (fy - 14 - hip[1]) * 0.38)
                body.chain([hip, mid], 52, sp["bottom"])
        body.ell(fx + side * 8, fy + 2, 42, 18, sp["shoe"])

    # torso (clothes)
    ts, tc = sp["top_style"], sp["top"]
    y0 = -sh + 8
    if ts == "shirt":
        body.poly([(-tw / 2 + 14, y0), (tw / 2 - 14, y0), (tw / 2, -sh + 32), (tw / 2 * 0.96, -lh + 22), (-tw / 2 * 0.96, -lh + 22), (-tw / 2, -sh + 32)], tc)
        body.poly([(-18, y0 + 2), (18, y0 + 2), (0, -sh + 44)], skin, ow=3)
        if who == "dad":
            body.line([(0, -sh + 44), (0, -lh + 26)], 4, _dark(tc, 0.7))
    elif ts == "kurta":
        yb = -lh * 0.60
        body.poly([(-tw / 2 + 14, y0), (tw / 2 - 14, y0), (tw / 2, -sh + 32), (tw / 2 * 1.12, yb), (-tw / 2 * 1.12, yb), (-tw / 2, -sh + 32)], tc)
        body.poly([(-tw / 2 * 1.12, yb - 16), (tw / 2 * 1.12, yb - 16), (tw / 2 * 1.12, yb), (-tw / 2 * 1.12, yb)], sp["trim"], ow=3)
        body.ell(0, -sh + 16, 24, 15, skin, ow=3)
        body.line([(-26, -sh + 26), (0, -sh + 40), (26, -sh + 26)], 4, sp["trim"])
    else:  # frock
        yb = -lh * 0.52
        body.poly([(-tw / 2 + 14, y0), (tw / 2 - 14, y0), (tw / 2 - 6, -sh + 64), (tw * 0.98, yb), (-tw * 0.98, yb), (-tw / 2 + 6, -sh + 64)], tc)
        body.poly([(-tw * 0.98, yb - 14), (tw * 0.98, yb - 14), (tw * 0.98, yb), (-tw * 0.98, yb)], sp["trim"], ow=3)
        body.line([(-tw / 2 + 8, -sh + 64), (tw / 2 - 8, -sh + 64)], 7, sp["trim"])
        body.ell(0, -sh + 14, 22, 13, skin, ow=3)
    if sp.get("dupatta"):
        dc = sp["dupatta"]
        body.poly([(-tw / 2 + 4, -sh + 16), (-tw / 2 + 46, -sh + 12), (tw / 2 + 4, -lh * 0.95), (tw / 2 - 40, -lh * 0.95 + 18)], dc, ow=4)
        body.poly([(tw / 2 - 40, -lh * 0.95 + 18), (tw / 2 + 4, -lh * 0.95), (tw / 2 + 18, -lh * 0.55), (tw / 2 - 28, -lh * 0.62)], dc, ow=4)

    # arms
    ua, fa = (74, 62) if kid else (86, 72)
    for side, a1, a2 in ((-1, pose["aL"], pose["fL"]), (1, pose["aR"], pose["fR"])):
        s0 = (side * (tw / 2 - 6), -sh + 36 + bob)
        r1, r2 = math.radians(a1), math.radians(a1 + a2)
        e = (s0[0] + side * ua * math.sin(r1), s0[1] + ua * math.cos(r1))
        h = (e[0] + side * fa * math.sin(r2), e[1] + fa * math.cos(r2))
        body.chain([s0, e, h], 30, skin)
        if sp["top_style"] != "shirt" or who == "boy":
            mid = (s0[0] + (e[0] - s0[0]) * 0.62, s0[1] + (e[1] - s0[1]) * 0.62)
            body.chain([s0, mid], 38, tc)
        else:
            mid = (s0[0] + (e[0] - s0[0]) * 0.9, s0[1] + (e[1] - s0[1]) * 0.9)
            body.chain([s0, mid], 38, tc)
        body.ell(h[0], h[1], 21, 21, skin)
        if sp.get("gold"):
            wx, wy = h[0] - (h[0] - e[0]) * 0.28, h[1] - (h[1] - e[1]) * 0.28
            body.ell(wx, wy, 17, 11, (255, 205, 70), ow=2)

    # ---------------- head layer
    st = sp["style"]
    if st == "pigtails":
        for side in (-1, 1):
            sw = pose["ear"] * 1.4 * side
            head.ell(side * (hrx + 30) + sw, hy + 24, 30, 60, sp["hair"])
            head.ell(side * (hrx * 0.86), hy - 22, 20, 15, sp["ribbon"], ow=3)
    if st == "bun":
        head.ell(0, hy - hry - 24, 44, 40, sp["hair"]); head.ell(0, hy - hry + 6, 22, 9, (255, 205, 70), ow=2)
    for side in (-1, 1):
        head.ell(side * hrx, hy + 8, 18, 26, skin)
        if sp.get("gold") and who == "mom":
            head.ell(side * (hrx + 6), hy + hry * 0.34, 8, 11, (255, 205, 70), ow=2)
    head.ell(0, hy, hrx, hry, skin)

    # hair cap over the top of the head
    arc = [(( hrx + 3) * math.cos(math.radians(a)), hy + (hry + 3) * math.sin(math.radians(a))) for a in range(186, 355, 8)]
    if st == "short":
        low = [(hrx * 0.94, hy - hry * 0.26), (hrx * 0.5, hy - hry * 0.50), (0, hy - hry * 0.54), (-hrx * 0.5, hy - hry * 0.50), (-hrx * 0.94, hy - hry * 0.26)]
    elif st == "boy":
        low = [(hrx * 0.94, hy - hry * 0.24), (hrx * 0.64, hy - hry * 0.42), (hrx * 0.5, hy - hry * 0.18), (hrx * 0.22, hy - hry * 0.44),
               (0, hy - hry * 0.16), (-hrx * 0.26, hy - hry * 0.44), (-hrx * 0.5, hy - hry * 0.2), (-hrx * 0.7, hy - hry * 0.42), (-hrx * 0.94, hy - hry * 0.24)]
    elif st == "bun":
        low = [(hrx * 0.96, hy + hry * 0.08), (hrx * 0.62, hy - hry * 0.30), (0, hy - hry * 0.56), (-hrx * 0.62, hy - hry * 0.30), (-hrx * 0.96, hy + hry * 0.08)]
    else:
        low = [(hrx * 0.94, hy - hry * 0.24), (hrx * 0.45, hy - hry * 0.30), (0, hy - hry * 0.26), (-hrx * 0.45, hy - hry * 0.30), (-hrx * 0.94, hy - hry * 0.24)]
    head.poly(arc + low, sp["hair"], ow=4)

    # eyes
    blink = pose["blink"]; re_ = hrx * 0.21
    for side in (-1, 1):
        ex, ey = side * hrx * 0.42, hy + hry * 0.10
        if pose["eyes"] == "happy" or blink < 0.18:
            head.arc(ex, ey, re_ * 0.95, re_ * (0.75 if pose["eyes"] == "happy" else 0.4), 200, 340, 7)
        else:
            ry = re_ * 1.18 * pose["eyeS"] * blink
            head.ell(ex, ey, re_ * (1 + (pose["eyeS"] - 1) * 0.5), ry, (255, 255, 255), ow=4)
            lx, ly = pose["look"]
            px, py = ex + lx * 8, ey + ly * 8 + 3
            head.ell(px, py, re_ * 0.62, min(re_ * 0.62, ry * 0.62), (36, 26, 40), ow=0)
            head.ell(px - 4, py - 5, 4.5, 4.5, (255, 255, 255), ow=0)
        lift = 9 if pose["eyeS"] > 1.1 else 0
        yb = ey - re_ * 1.6 - lift
        pts = [(ex - re_ * 0.9, yb + 3), (ex + re_ * 0.9, yb - 3)] if side < 0 else [(ex - re_ * 0.9, yb - 3), (ex + re_ * 0.9, yb + 3)]
        head.chain(pts, 6, sp["hair"], ow=0)
    # nose / cheeks / mouth
    head.ell(0, hy + hry * 0.34, 9, 7, _dark(skin, 0.84), ow=2)
    for side in (-1, 1):
        head.ell(side * hrx * 0.64, hy + hry * 0.40, 20, 12, (255, 150, 150), ow=0)
    if sp.get("mous"):
        for side in (-1, 1):
            head.ell(side * 17, hy + hry * 0.50, 21, 9, sp["hair"], ow=0)
    if sp.get("bindi"):
        head.ell(0, hy - hry * 0.40, 6, 6, (214, 30, 50), ow=0)
    m = pose["mouth"]; my = hy + hry * 0.62
    if m > 0.12:
        mh = 6 + 26 * min(1.0, m)
        head.ell(0, my + mh * 0.3, 24, mh, (150, 36, 60), ow=4)
        head.ell(0, my + mh * 0.7, 13, mh * 0.36, (255, 120, 140), ow=0)
    else:
        head.arc(0, my - 8, 28, 15, 15, 165, 6)

    pivot = (OX * sc2 * SS, (OY - sh) * sc2 * SS)
    h_img = head.img.rotate(pose["tilt"], resample=Image.BICUBIC, center=pivot)
    return Image.alpha_composite(body.img, h_img).reduce(SS)


def blink_value(t, ph):
    x = (t * 0.42 + ph) % 1.0
    return 0.08 + 0.92 * min(1.0, abs(x - 0.03) / 0.03) if x < 0.06 else 1.0


def make_pose(action, t, env, emo, ph=0.0):
    s = math.sin
    p = dict(bob=3 * s(t * 2.4 + ph), tilt=3 * s(t * 1.6 + ph), aL=14, aR=14, fL=0, fR=0, phi=0.0, amp=0.0,
             jump=0.0, squash=1.0, mouth=env, eyes="open", look=(0.3 * s(t * 0.7 + ph), 0.0), eyeS=1.0,
             ear=4 * s(t * 2.2 + ph), blink=blink_value(t, ph), dx=0.0)
    if action == "talk":
        g = 0.5 + 0.5 * s(t * 2.3 + ph)
        p["aR"] = 28 + 40 * g * min(1.0, env * 2); p["fR"] = 18 * s(t * 5)
        p["aL"] = 16 + 14 * (1 - g) * min(1.0, env * 2)
        p["tilt"] += 3 * s(t * 3.3) * min(1.0, env * 2)
    elif action == "wave":
        p["aR"] = 150; p["fR"] = 30 * s(t * 9); p["aL"] = 12; p["eyes"] = "happy" if emo == "happy" and (t % 2.4) > 1.9 else "open"
        p["tilt"] = 5 * s(t * 2)
    elif action == "walk":
        p["amp"] = 1.0; p["phi"] = t * 7.5
        p["aL"] = 22 + 26 * s(t * 7.5); p["aR"] = 22 - 26 * s(t * 7.5)
        p["bob"] = 3 * s(t * 2) + 7 * abs(s(t * 7.5))
    elif action == "jump":
        ph2 = abs(s(t * 3.6 + ph)); p["jump"] = 120 * ph2
        p["aL"] = 120 * ph2 + 20; p["aR"] = 120 * ph2 + 20; p["fL"] = 10; p["fR"] = 10
        p["squash"] = 0.92 + 0.08 * min(1.0, ph2 * 4)
        p["eyes"] = "happy"; p["mouth"] = max(env, 0.5 * ph2)
        p["amp"] = 0.4 * (1 - ph2); p["phi"] = t * 10
    elif action == "dance":
        p["tilt"] = 8 * s(t * 5 + ph); p["aL"] = 70 + 55 * s(t * 5); p["aR"] = 70 - 55 * s(t * 5)
        p["fL"] = 20 * s(t * 10); p["fR"] = -20 * s(t * 10)
        p["bob"] = 3 + 9 * abs(s(t * 5)); p["amp"] = 0.35; p["phi"] = t * 5
        p["jump"] = 22 * abs(s(t * 5)); p["eyes"] = "happy" if (t % 3) > 1.2 else "open"
    elif action == "think":
        p["aR"] = 40; p["fR"] = -125; p["aL"] = 14; p["tilt"] = 7 + 2 * s(t * 1.5)
        p["look"] = (-0.8, -1.0); p["mouth"] = 0.0
    elif action == "surprised":
        p["eyeS"] = 1.28; p["mouth"] = max(env, 0.8); p["aL"] = 105; p["aR"] = 105; p["fL"] = 15; p["fR"] = 15
        p["jump"] = 14 * abs(s(t * 6)); p["look"] = (0.0, -0.2)
    if emo == "happy" and action in ("talk", "think") and (t % 3.2) > 2.5:
        p["eyes"] = "happy"
    return p


# ------------------------------------------------------------------ backgrounds (1080x1920)
def _grad(top, bot, h=1920, w=1080):
    t = np.linspace(0, 1, h)[:, None, None]
    a = np.array(top, np.float32)[None, None, :]; b = np.array(bot, np.float32)[None, None, :]
    return np.repeat(a * (1 - t) + b * t, w, axis=1).astype(np.uint8)


def _hills(d, color, base, amp, seed, wl=700):
    rng = random.Random(seed); ph = rng.uniform(0, 6)
    pts = [(x, base + amp * math.sin(x / wl * 2 * math.pi + ph) + amp * 0.4 * math.sin(x / (wl * 0.37) + ph * 2)) for x in range(-20, 1110, 20)]
    d.polygon([(-20, 1960)] + pts + [(1110, 1960)], fill=color)


def _cloud(d, cx, cy, s, col=(255, 255, 255)):
    for dx, dy, r in ((-60, 10, 42), (-15, -18, 56), (40, -5, 48), (85, 12, 36), (10, 20, 50)):
        d.ellipse((cx + (dx - r) * s, cy + (dy - r) * s, cx + (dx + r) * s, cy + (dy + r) * s), fill=col)


def _tree(d, x, base, h, trunk=(120, 80, 50), leaf=(70, 170, 80)):
    d.rounded_rectangle((x - h * 0.06, base - h * 0.5, x + h * 0.06, base), radius=8, fill=trunk)
    for dx, dy, r in ((0, -0.62, 0.32), (-0.2, -0.45, 0.26), (0.2, -0.45, 0.26), (0, -0.8, 0.22)):
        d.ellipse((x + (dx - r) * h, base + (dy - r) * h, x + (dx + r) * h, base + (dy + r) * h), fill=leaf)


def _star4(d, x, y, r, col=(255, 255, 255)):
    d.polygon([(x, y - r), (x + r * 0.28, y - r * 0.28), (x + r, y), (x + r * 0.28, y + r * 0.28),
               (x, y + r), (x - r * 0.28, y + r * 0.28), (x - r, y), (x - r * 0.28, y - r * 0.28)], fill=col)


def make_bg(kind, seed=0):
    rng = random.Random(seed * 31 + len(kind))
    S = 2
    big = Image.new("RGBA", (1080 * S, 1920 * S), (0, 0, 0, 0)); d = ImageDraw.Draw(big)
    sc = lambda *a: [v * S for v in a]

    class D:      # draws in 1x coordinates onto 2x canvas
        def polygon(s, pts, fill): d.polygon([(x * S, y * S) for x, y in pts], fill=fill)
        def ellipse(s, box, fill): d.ellipse([v * S for v in box], fill=fill)
        def rounded_rectangle(s, box, radius, fill): d.rounded_rectangle([v * S for v in box], radius=radius * S, fill=fill)
        def rectangle(s, box, fill): d.rectangle([v * S for v in box], fill=fill)
        def line(s, pts, fill, width): d.line([(x * S, y * S) for x, y in pts], fill=fill, width=int(width * S))
    g = D()
    if kind == "night":
        base = _grad((12, 16, 56), (70, 48, 120))
        for _ in range(70):
            _star4(g, rng.uniform(30, 1050), rng.uniform(30, 1100), rng.choice([6, 8, 11, 14]), (255, 250, 220))
        g.ellipse((700, 190, 940, 430), (255, 246, 205)); g.ellipse((770, 150, 1000, 380), (0, 0, 0, 0))
        _hills(g, (34, 52, 98), 1230, 70, seed); _hills(g, (28, 70, 90), 1380, 55, seed + 1, 900)
        g.rectangle((0, 1490, 1080, 1920), (36, 84, 96))
    elif kind == "room":
        base = _grad((255, 226, 180), (255, 214, 160))
        g.rectangle((0, 1380, 1080, 1920), (212, 160, 100))
        for i in range(0, 1080, 135):
            g.line([(i, 1380), (i - 40, 1920)], (190, 140, 84), 5)
        g.rectangle((0, 1360, 1080, 1384), (150, 100, 70))
        g.rounded_rectangle((640, 330, 980, 800), 20, (130, 90, 60)); g.rounded_rectangle((664, 354, 956, 776), 10, (150, 215, 250))
        g.ellipse((780, 410, 880, 510), (255, 232, 120)); _cloud(g, 800, 640, 0.9)
        g.line([(810, 354), (810, 776)], (130, 90, 60), 14); g.line([(664, 565), (956, 565)], (130, 90, 60), 14)
        g.polygon([(600, 300), (700, 300), (690, 820), (600, 840)], (235, 100, 120)); g.polygon([(980, 300), (1080, 300), (1080, 840), (990, 820)], (235, 100, 120))
        g.rounded_rectangle((110, 380, 380, 600), 14, (130, 90, 60)); g.rounded_rectangle((128, 398, 362, 582), 8, (255, 245, 220))
        g.ellipse((200, 440, 290, 530), (255, 170, 80))
        g.ellipse((120, 1440, 960, 1700), (232, 110, 120)); g.ellipse((190, 1470, 890, 1670), (250, 160, 150))
    elif kind == "forest":
        base = _grad((170, 230, 190), (110, 190, 140))
        for i, (col, hh, yb) in enumerate([((90, 160, 110), 700, 1250), ((70, 140, 90), 820, 1330), ((50, 120, 70), 920, 1420)]):
            for k in range(5):
                _tree(g, k * 300 - 40 + rng.uniform(-60, 60) + i * 70, yb, hh, trunk=(100, 70, 50), leaf=col)
        g.rectangle((0, 1490, 1080, 1920), (70, 150, 80))
        for _ in range(14):
            x, y = rng.uniform(0, 1080), rng.uniform(1540, 1900)
            g.ellipse((x - 26, y - 26, x + 26, y - 4), (230, 70, 70)); g.rectangle((x - 7, y - 4, x + 7, y + 16), (250, 240, 220))
    elif kind == "pond":
        base = _grad((135, 205, 250), (225, 245, 255))
        _cloud(g, 250, 300, 1.2); _cloud(g, 800, 460, 0.9)
        _hills(g, (120, 195, 130), 1180, 55, seed); _hills(g, (96, 175, 108), 1340, 45, seed + 2, 900)
        g.rectangle((0, 1490, 1080, 1920), (92, 170, 92))
        g.ellipse((-80, 1640, 1160, 1960), (70, 165, 230)); g.ellipse((60, 1690, 1020, 1900), (110, 195, 245))
        for x, y in ((220, 1760), (700, 1800), (880, 1720)):
            g.ellipse((x - 60, y - 22, x + 60, y + 22), (80, 190, 100))
        for x in (60, 1010, 970):
            g.line([(x, 1640), (x + 6, 1450)], (80, 130, 70), 12)
    elif kind == "space":
        base = _grad((10, 8, 40), (60, 24, 100))
        for _ in range(110):
            _star4(g, rng.uniform(20, 1060), rng.uniform(20, 1400), rng.choice([4, 6, 9, 12]), (255, 250, 230))
        g.ellipse((120, 240, 420, 540), (255, 150, 90)); g.ellipse((150, 280, 250, 360), (255, 190, 130))
        g.ellipse((680, 360, 920, 600), (110, 190, 255)); g.ellipse((620, 450, 980, 510), (255, 230, 160))
        g.ellipse((-200, 1470, 1280, 2300), (150, 150, 185)); g.ellipse((-200, 1490, 1280, 2300), (170, 170, 205))
        for x, y, r in ((200, 1620, 60), (760, 1700, 80), (520, 1810, 50)):
            g.ellipse((x - r, y - r * 0.5, x + r, y + r * 0.5), (135, 135, 170))
    else:  # meadow
        base = _grad((120, 200, 255), (225, 245, 255))
        g.ellipse((780, 150, 980, 350), (255, 235, 90)); g.ellipse((760, 130, 1000, 370), (255, 240, 140))
        _cloud(g, 220, 280, 1.3); _cloud(g, 640, 520, 0.9); _cloud(g, 900, 640, 0.7)
        _hills(g, (135, 210, 125), 1190, 70, seed); _hills(g, (100, 190, 98), 1350, 60, seed + 3, 900)
        _tree(g, 110, 1440, 520); g.rectangle((0, 1490, 1080, 1920), (84, 176, 84))
        for _ in range(26):
            x, y = rng.uniform(0, 1080), rng.uniform(1520, 1900)
            col = rng.choice([(255, 255, 255), (255, 130, 160), (255, 220, 80)])
            for a in range(5):
                ax, ay = x + 11 * math.cos(a * 1.256), y + 11 * math.sin(a * 1.256)
                g.ellipse((ax - 7, ay - 7, ax + 7, ay + 7), col)
            g.ellipse((x - 5, y - 5, x + 5, y + 5), (255, 200, 60))
    layer = big.resize((1080, 1920), Image.LANCZOS)
    bg = Image.fromarray(base, "RGB").convert("RGBA")
    return Image.alpha_composite(bg, layer).convert("RGB")


# ------------------------------------------------------------------ props
def draw_prop(name, size, t):
    """Square RGBA image (size px) with bobbing/animated prop."""
    p = Pen(100, 100, 50, 50, size * SS / 100.0)
    s = math.sin
    if name == "sun":
        for i in range(12):
            a = i * math.pi / 6 + t * 0.6
            p.chain([(30 * math.cos(a), 30 * math.sin(a)), (46 * math.cos(a), 46 * math.sin(a))], 7, (255, 190, 50), ow=2)
        p.ell(0, 0, 28, 28, (255, 226, 70), ow=3)
        p.ell(-9, -4, 3.5, 3.5, OL, ow=0); p.ell(9, -4, 3.5, 3.5, OL, ow=0); p.arc(0, 4, 11, 8, 20, 160, 2.5)
    elif name == "moon":
        p.ell(0, 0, 38, 38, (255, 244, 200), ow=3); p.ell(16, -8, 32, 32, (0, 0, 0, 0), ow=0)
        p.d.ellipse([v for v in (p.p(-6 + 16 - 32, -8 - 32) + p.p(16 + 32 - 6, -8 + 32))], fill=(0, 0, 0, 0))
    elif name == "star":
        a0 = t * 0.8; pts = []
        for i in range(10):
            r = 40 if i % 2 == 0 else 17; a = a0 + i * math.pi / 5 - math.pi / 2
            pts.append((r * math.cos(a), r * math.sin(a)))
        p.poly(pts, (255, 224, 60), ow=3); p.ell(-8, -2, 3, 3, OL, ow=0); p.ell(8, -2, 3, 3, OL, ow=0); p.arc(0, 6, 8, 5, 20, 160, 2)
    elif name == "cloud":
        for dx, dy, r in ((-24, 6, 17), (-6, -8, 23), (16, -2, 20), (30, 8, 15), (4, 8, 20)):
            p.ell(dx, dy, r, r, (255, 255, 255), ow=0)
        p.ell(-20, 10, 4, 4, (255, 150, 170), ow=0); p.ell(22, 10, 4, 4, (255, 150, 170), ow=0)
    elif name == "flower":
        p.chain([(0, 40), (0, 4)], 6, (70, 160, 70), ow=2)
        p.poly([(0, 26), (22, 16), (8, 30)], (90, 190, 90), ow=2)
        for i in range(6):
            a = i * math.pi / 3 + 0.3 * s(t * 1.2)
            p.ell(18 * math.cos(a), -8 + 18 * math.sin(a), 13, 13, (255, 130, 170), ow=2)
        p.ell(0, -8, 11, 11, (255, 214, 60), ow=2)
    elif name == "apple":
        p.ell(0, 6, 32, 30, (230, 50, 60), ow=3); p.chain([(0, -22), (4, -36)], 5, (110, 70, 40), ow=1)
        p.poly(ell_pts(14, -30, 14, 7, -25), (90, 190, 80), ow=2); p.ell(-12, -2, 6, 9, (255, 130, 130), ow=0)
    elif name == "fish":
        w = 12 * s(t * 6)
        p.poly([(24, 0), (46, -16 + w), (46, 16 + w)], (255, 150, 60), ow=3)
        p.ell(0, 0, 32, 20, (255, 170, 70), ow=3); p.ell(-16, -4, 5, 5, (255, 255, 255), ow=2); p.ell(-17, -4, 2, 2, OL, ow=0)
        p.arc(-4, 2, 12, 10, 20, 150, 2)
    elif name == "bird":
        w = 22 * s(t * 9)
        p.ell(0, 4, 26, 19, (90, 170, 255), ow=3); p.ell(-22, -8, 14, 14, (90, 170, 255), ow=3)
        p.poly([(-34, -8), (-46, -4), (-34, -1)], (255, 190, 50), ow=2); p.ell(-24, -10, 3, 3, OL, ow=0)
        p.poly([(-4, 0), (14, -26 - w), (22, 0)], (60, 140, 230), ow=3)
    elif name == "heart":
        sc = 1 + 0.1 * s(t * 5)
        p.ell(-14 * sc, -8 * sc, 20 * sc, 20 * sc, (255, 80, 120), ow=3); p.ell(14 * sc, -8 * sc, 20 * sc, 20 * sc, (255, 80, 120), ow=3)
        p.poly([(-31 * sc, 2 * sc), (31 * sc, 2 * sc), (0, 38 * sc)], (255, 80, 120), ow=3)
        p.ell(-14 * sc, -8 * sc, 17 * sc, 17 * sc, (255, 80, 120), ow=0); p.ell(14 * sc, -8 * sc, 17 * sc, 17 * sc, (255, 80, 120), ow=0)
    elif name == "balloon":
        p.line([(0, 30), (4 * s(t * 2), 46)], 2)
        p.ell(0, -8, 26, 32, (255, 90, 90), ow=3); p.poly([(-5, 24), (5, 24), (0, 31)], (255, 90, 90), ow=2); p.ell(-9, -18, 5, 8, (255, 170, 170), ow=0)
    elif name == "rainbow":
        for i, col in enumerate([(255, 80, 80), (255, 170, 60), (255, 230, 70), (90, 200, 100), (80, 160, 255), (150, 100, 220)]):
            r = 44 - i * 6
            p.arc(0, 18, r, r, 180, 360, 6.5, col)
    elif name == "tree":
        p.d.rectangle([*p.p(-6, 4), *p.p(6, 42)], fill=(120, 80, 50))
        for dx, dy, r in ((0, -18, 24), (-16, -2, 20), (16, -2, 20)):
            p.ell(dx, dy, r, r, (80, 180, 90), ow=3)
    elif name == "butterfly":
        f = abs(s(t * 8)); wx = 10 + 26 * f
        for side in (-1, 1):
            p.ell(side * wx * 0.6, -10, wx * 0.6, 20, (255, 140, 200), ow=3); p.ell(side * wx * 0.5, 12, wx * 0.45, 14, (255, 190, 90), ow=3)
        p.ell(0, 0, 4, 22, (80, 50, 70), ow=0)
    return p.img.reduce(SS)


def prop_bob(name, t, i):
    if name == "fish":
        return 0, 14 * math.sin(t * 2 + i)
    if name in ("butterfly", "bird"):
        return 40 * math.sin(t * 1.1 + i), 20 * math.sin(t * 2.3 + i)
    return 0, 12 * math.sin(t * 1.8 + i * 1.3)


ALL_CHARACTERS = list(CHARACTERS) + list(HUMANS)
