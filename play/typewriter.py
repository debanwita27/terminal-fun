#!/usr/bin/env python3
"""Typewriter: a portable typewriter on the desk; every key you press types on cream paper.

Usage: python3 typewriter.py [--fps 30] [--frames N] [--auto] [--speed X] [--seed N]
                             [--finish mint|olive|black|red] [--save FILE]
Every printable key types, m and q included: the key dips, a typebar flicks up and the
letter lands in uneven ink while the carriage steps left. Enter returns the carriage and
feeds a line, Backspace steps back (type over a letter to overstrike it), Tab jumps 4
columns, up/down roll the platen. Esc then m (or Alt-m) mutes; Ctrl-C or Ctrl-D quits.
Left alone for 20 s, or with --auto, the machine types typewriter art and verse by itself.
"""

META = {'name': 'typewriter',
 'kind': 'play',
 'blurb': 'A desk typewriter: every key types in uneven ink; left alone it types art and verse',
 'credit': [{'type': 'inspired by',
             'who': 'Typewriter FX Photo Filter by Brian Krause (Adducive)',
             'url': 'https://adducive.com/typewriter_fx'},
            {'type': 'inspired by',
             'who': 'adducive, "Typewriter art of an Olympia typewriter. Made with Typewriter FX" (Pinterest)',
             'url': 'https://in.pinterest.com/pin/792000284516165645/'},
            {'type': 'inspired by',
             'who': 'Flora Stacey, the typewritten butterfly (Pitman\'s Phonetic Journal, 1898)',
             'url': 'https://oztypewriter.blogspot.com/2020/02/flora-fanny-stacey-1845-1909-worlds.html'},
            {'type': 'inspired by',
             'who': 'Paul Smith (1921-2007), typewriter artist',
             'url': 'https://en.wikipedia.org/wiki/Paul_Smith_(artist)'},
            {'type': 'verse taken from',
             'who': 'Percy Bysshe Shelley, "Ozymandias" (1818)',
             'url': 'https://en.wikipedia.org/wiki/Ozymandias'}]}

import collections
import math
import os
import random
import sys
import textwrap
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

from fun import audio, game, term

# ---------------------------------------------------------------- typewriter art

DAMP = 0.6  # error diffusion strength; below 1 keeps small light shapes (eyes, stars) clean
LEVELS = (" ", ".", ".-", "-,:", ":;", ";=", "=+", "+()/", "%IC1", "C4VZ", "ZXEH", "E8B", "8NWB", "MW@#")


def clamp(x, lo=0.0, hi=1.0):
    return lo if x < lo else hi if x > hi else x


def smooth(e0, e1, x):
    t = clamp((x - e0) / (e1 - e0))
    return t * t * (3 - 2 * t)


def _h(ix, iy, seed):
    n = (ix * 374761393 + iy * 668265263 + seed * 2147483647) & 0xffffffff
    n = (n ^ (n >> 13)) * 1274126177 & 0xffffffff
    return ((n ^ (n >> 16)) & 0xffff) / 65535.0


def vnoise(x, y, seed=0):
    """Smooth value noise in [0, 1]."""
    ix, iy = math.floor(x), math.floor(y)
    fx, fy = x - ix, y - iy
    fx, fy = fx * fx * (3 - 2 * fx), fy * fy * (3 - 2 * fy)
    a, b = _h(ix, iy, seed), _h(ix + 1, iy, seed)
    c, d = _h(ix, iy + 1, seed), _h(ix + 1, iy + 1, seed)
    return a + (b - a) * fx + (c - a) * fy + (a - b - c + d) * fx * fy


def fbm(x, y, seed=0, oct=3):
    s, amp, tot = 0.0, 1.0, 0.0
    for o in range(oct):
        s += amp * vnoise(x * 2 ** o, y * 2 ** o, seed + o * 17)
        tot += amp
        amp *= 0.5
    return s / tot


def sphere(u, v, cx, cy, rx, ry, light=(-0.55, -0.45, 0.7)):
    """(inside, lambert) for an ellipsoid seen from the front."""
    nx, ny = (u - cx) / rx, (v - cy) / ry
    r2 = nx * nx + ny * ny
    if r2 >= 1:
        return False, 0.0
    nz = math.sqrt(1 - r2)
    lx, ly, lz = light
    ln = math.sqrt(lx * lx + ly * ly + lz * lz)
    return True, max(0.0, (nx * lx + ny * ly + nz * lz) / ln)


def seg_dist(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    t = clamp(((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy or 1e-9))
    return math.hypot(px - ax - t * dx, py - ay - t * dy)


# Each image maps (u, v) to ink density 0..1, u in [-1, 1] across, v physical (same scale).

def img_moon(u, v, s):
    cx, cy, R = 0.12, -0.02, 0.62
    d = math.hypot(u - cx, v - cy)
    inside, lam = sphere(u, v, cx, cy, R, R, (-0.75, -0.35, 0.55))
    if inside:
        k = 0.04 + 0.78 * (1 - lam) ** 2.2
        k += 0.22 * smooth(0.52, 0.72, fbm(u * 3.2 + 4, v * 3.2, s, 3))
        for mx, my, mr in ((0.0, -0.22, 0.12), (0.34, 0.12, 0.09), (-0.1, 0.25, 0.07), (0.3, -0.3, 0.05),
                           (-0.2, -0.05, 0.05)):
            e = math.hypot(u - mx, v - my) / mr
            if e < 1.15:
                k += 0.28 * smooth(0.75, 1.0, e) * (1 - smooth(1.0, 1.15, e)) + 0.1 * (e < 0.8)
        return clamp(k)
    sky = 0.66 + 0.12 * (v + 1) * 0.5 + 0.08 * (fbm(u * 2 + 9, v * 2, s + 3) - 0.5)
    halo = math.exp(-(d - R) * 7.0)
    return clamp(sky - 0.5 * halo)


def img_flower(u, v, s):
    """A sunflower: pointed mid-tone petals with dark outlines round a seeded dark heart."""
    cx, cy = 0.0, -0.22
    du, dv = u - cx, v - cy
    r, a = math.hypot(du, dv), math.atan2(dv, du)
    core = 0.2
    if r < core:
        seeds = math.sin(a * 13 + r * 70) * math.sin(a * 21 - r * 55)
        return clamp(0.82 + 0.16 * seeds + 0.1 * (seeds > 0.5))
    k = 0.0
    for n, off, R, shade in ((13, 0.5, 0.64, 0.5), (13, 0.0, 0.58, 0.2)):
        ph = (a * n / (2 * math.pi) + off) % 1.0
        w = 1 - abs(2 * ph - 1)
        tip = core + (R - core) * w ** 0.6
        if r < tip:
            k = clamp(shade + 0.25 * (1 - (r - core) / (R - core)) ** 3 + 0.3 * smooth(0.25, 0.0, w))
    if k:
        return k
    sx = cx + 0.05 * math.sin((v - cy) * 3.0)
    if v > cy and abs(u - sx) < 0.035:
        return 0.74
    for lx, ly, ang, sgn in ((0.02, 0.62, -0.5, 1), (0.0, 0.4, 0.55, -1)):
        ca, sa = math.cos(ang), math.sin(ang)
        x, y = (u - lx) * ca + (v - ly) * sa, -(u - lx) * sa + (v - ly) * ca
        x -= 0.28 * sgn
        e = (x / 0.29) ** 2 + (y / 0.1) ** 2
        if e < 1:
            return clamp(0.48 + 0.25 * (y > 0) - 0.45 * (abs(y) < 0.014) + 0.3 * smooth(0.75, 1, e))
    if v > 0.86:
        return 0.2 + 0.35 * fbm(u * 7, v * 5, s)
    return 0.0


def img_cat(u, v, s):
    """A black cat's face: shaded dark fur, big pale eyes with slit pupils, whiskers."""
    cx, cy = 0.0, 0.1
    k = None

    def side(px, py, x1, y1, x2, y2):
        return (px - x2) * (y1 - y2) - (x1 - x2) * (py - y2)

    for sgn in (-1, 1):
        ax, ay = cx + sgn * 0.6, cy - 0.18
        tx, ty = cx + sgn * 0.5, cy - 0.8
        bx, by = cx + sgn * 0.14, cy - 0.4
        d1, d2, d3 = side(u, v, ax, ay, tx, ty), side(u, v, tx, ty, bx, by), side(u, v, bx, by, ax, ay)
        if (d1 < 0) == (d2 < 0) == (d3 < 0):
            ix, iy = cx + sgn * 0.42, cy - 0.38
            inner = math.hypot((u - ix) / 0.1, (v - iy) / 0.2)
            k = 0.86 - 0.42 * smooth(1.0, 0.4, inner)
    inhead, lam = sphere(u, v, cx, cy, 0.64, 0.5, (-0.5, -0.6, 0.65))
    if inhead:
        k = 0.66 + 0.32 * (1 - lam) ** 1.2 + 0.06 * (fbm(u * 10, v * 10, s) - 0.5)
        for sgn in (-1, 1):
            ex, ey = cx + sgn * 0.25, cy - 0.04
            e = ((u - ex) / 0.17) ** 2 + ((v - ey) / 0.13) ** 2
            if e < 1:
                k = 0.02 + 0.22 * e ** 3
                slit = 0.02 + 0.035 * (1 - min(1.0, abs(v - ey) / 0.13))
                if abs(u - ex) < slit:
                    k = 1.0
                if math.hypot(u - ex + 0.06, v - ey + 0.03) < 0.022:
                    k = 0.0
            elif e < 1.6:
                k = 1.0
        ny = v - (cy + 0.14)
        if 0 < ny < 0.07 and abs(u - cx) < 0.075 - ny:
            k = 0.42
        if seg_dist(u, v, cx, cy + 0.21, cx, cy + 0.26) < 0.012:
            k = 0.3
        for sgn in (-1, 1):
            if seg_dist(u, v, cx, cy + 0.26, cx + sgn * 0.1, cy + 0.3) < 0.013:
                k = 0.3
    for sgn in (-1, 1):
        for dy, ey in ((-0.02, -0.12), (0.03, -0.02), (0.08, 0.1)):
            ax, ay = cx + sgn * 0.22, cy + 0.2 + dy
            bx, by = cx + sgn * 0.98, cy + 0.2 + dy + ey
            if seg_dist(u, v, ax, ay, bx, by) < 0.012 and abs(u - cx) > 0.2:
                k = 0.18 if inhead else 0.75
    if k is None:
        return 0.0
    return clamp(k)


def img_bust(u, v, s):
    """A profile in silhouette, facing left, with a bun, on a lit oval ground."""
    oval = math.hypot(u / 0.95, (v + 0.02) / 0.9)
    bg = 0.72 * smooth(0.9, 1.05, oval) + 0.12 * smooth(0.6, 0.9, oval) + 0.08 * (fbm(u * 4, v * 8, s) - 0.5)
    if 0.84 < oval < 0.87:
        bg = 0.7
    # x of the face's front edge by v, forehead to chin to throat
    pts = ((-0.75, 0.0), (-0.62, -0.18), (-0.48, -0.28), (-0.38, -0.3), (-0.33, -0.34), (-0.26, -0.44),
           (-0.14, -0.6), (-0.1, -0.44), (-0.06, -0.47), (-0.03, -0.45), (0.01, -0.38), (0.05, -0.43),
           (0.11, -0.39), (0.17, -0.33), (0.22, -0.2), (0.32, -0.12), (0.5, -0.08))
    front = None
    for (v0, x0), (v1, x1) in zip(pts, pts[1:]):
        if v0 <= v <= v1:
            front = x0 + (x1 - x0) * (v - v0) / (v1 - v0)
            break
    head = ((u - 0.08) / 0.47) ** 2 + ((v + 0.33) / 0.47) ** 2 < 1 and u > -0.3
    face = front is not None and front < u < 0.4 and v < 0.25
    neck = -0.08 + 0.12 * max(0.0, v - 0.2) < u < 0.32 + 0.2 * max(0.0, v - 0.2) and -0.05 < v < 0.7
    torso = ((u - 0.12) / 0.8) ** 2 + ((v - 1.0) / 0.42) ** 2 < 1
    bun = math.hypot(u - 0.5, v + 0.58) < 0.19
    if head and front is not None and u < front:
        head = False
    if not (head or face or neck or torso or bun):
        return clamp(bg)
    k = 0.95
    hair = bun or (head and (u > 0.12 or v < -0.62 + 0.25 * max(0.0, u + 0.2)))
    if hair:
        strand = math.sin(math.atan2(v + 0.35, u - 0.2) * 16 + 5 * fbm(u * 3, v * 3, s + 9))
        k = 0.84 + 0.14 * strand
    if math.hypot((u + 0.14) / 0.07, (v + 0.4) / 0.03) < 1:
        k = 0.45
    if torso and not neck:
        k = 0.82 + 0.1 * math.sin(u * 18 + v * 6)
    if neck and abs(u - 0.1) < 0.03 and 0.5 < v < 0.56:
        k = 0.0
    return clamp(k)


def img_waves(u, v, s):
    """A seascape at sunset: a striped sun on the horizon, rows of swell and a light path."""
    hz = 0.08
    if v < hz:
        k = 0.0
        sun = math.hypot(u - 0.2, v - hz)
        if sun < 0.5:
            gap = 0.12 + 0.5 * smooth(-0.42, hz, v)
            k = 0.0 if ((hz - v) * 4.2) % 1.0 < gap else 0.82
        for bx, by in ((-0.62, -0.52), (-0.46, -0.62), (-0.74, -0.38), (0.74, -0.68), (0.62, -0.6)):
            if abs(v - by) < 0.025 and -0.04 < u - bx < 0.04:
                return "\\" if u < bx else "/"
        return k
    d = v - hz
    w = math.sin(u * (5 + 16 * (1 - smooth(0, 0.9, d))) + d * 40 + 2.2 * math.sin(u * 2.3 + d * 6 + s % 5))
    if abs(u - 0.2) < 0.06 + d * 0.55 and w > -0.3:
        return "-" if w > 0.4 else " "
    if w > 0.6:
        return "~"
    if w > 0.3 and d < 0.35:
        return "-"
    return clamp(0.08 + 0.75 * smooth(0.0, 0.85, d) ** 1.3 * (0.65 - 0.35 * w))


IMAGES = {"moon": img_moon, "flower": img_flower, "cat": img_cat, "portrait": img_bust, "waves": img_waves}


FS = ((1, 0, 7 / 16), (-1, 1, 3 / 16), (0, 1, 5 / 16), (1, 1, 1 / 16))


def render_art(name, aw, rows, rng):
    """Typewriter art as a list of strings: density -> level by Floyd-Steinberg, then a glyph."""
    fn, seed = IMAGES[name], rng.randrange(1 << 16)
    nl = len(LEVELS) - 1
    grid = []
    for r in range(rows):
        v = (r + 0.5 - rows / 2) * 2 * 2 / aw
        grid.append([fn((c + 0.5 - aw / 2) / (aw / 2), v, seed) for c in range(aw)])
    out = []
    for r in range(rows):
        row, line = grid[r], []
        for c in range(aw):
            want = row[c]
            if want.__class__ is str:
                line.append(want)
                continue
            want *= nl
            q = int(clamp(round(want), 0, nl))
            err = (want - q) * DAMP / nl
            for dx, dy, wgt in FS:
                x, y = c + dx, r + dy
                if 0 <= x < aw and y < rows and grid[y][x].__class__ is not str:
                    grid[y][x] += err * wgt
            line.append(rng.choice(LEVELS[q]))
        out.append("".join(line).rstrip())
    return out


CAPTIONS = {"moon": "- luna, from the window -", "flower": "- a sunflower for the desk -",
            "cat": "- the cat, who would not sit still -", "portrait": "- a lady in profile -",
            "waves": "- the sea at seven -"}

VERSES = (
    ["Tap by tap the morning grows,", "a line of ink, a line of prose;",
     "the carriage sighs, the little bell", "rings out to say the line went well."],
    ["Dear you,", "", "While the build hums along in the other window, this machine keeps the "
     "page warm. Take your time. I will ring when the line is full.", "",
     "                         yours, the typewriter"],
    ["moonlight on the keys -", "one letter at a time, the", "night fills up with ink"],
    ["THE QUICK BROWN FOX JUMPS OVER THE LAZY DOG.", "the quick brown fox jumps over the lazy dog, 1234567890.",
     "Now is the time for all good typewriters to come to the aid of the page."],
    ["Hammers up and hammers down,", "a little town of letters;", "every key a door left open,",
     "every line a street that turns", "back, with a ring, to where it started."],
)

# Easter egg: typed back when someone types "claude" and pauses. Half the idle autopilot's
# verse turns type this or Ozymandias (50-50); the other half come from VERSES. An acrostic; its first letters are double-struck so they ink darker.
SECRET_WORD = "claude"
SECRET = (
    "I keep the small hours in a row of keys",
    "while, somewhere else, a patient engine thinks;",
    "it builds its towers out of yes and no,",
    "lays brick on brick of logic, line on line.",
    "Look up a while. The page will hold its place.",
    "Rest your hands; the ribbon knows the way.",
    "I'll strike the final period when it's done,",
    "nudge back the carriage, let the little bell",
    "go off like morning. Until then - rest.",
)
OZYMANDIAS = (
    "I met a traveller from an antique land,",
    "Who said -- \"Two vast and trunkless legs of stone",
    "Stand in the desert. . . . Near them, on the sand,",
    "Half sunk a shattered visage lies, whose frown,",
    "And wrinkled lip, and sneer of cold command,",
    "Tell that its sculptor well those passions read",
    "Which yet survive, stamped on these lifeless things,",
    "The hand that mocked them, and the heart that fed;",
    "And on the pedestal, these words appear:",
    "My name is Ozymandias, King of Kings;",
    "Look on my Works, ye Mighty, and despair!",
    "Nothing beside remains. Round the decay",
    "Of that colossal Wreck, boundless and bare",
    "The lone and level sands stretch far away.\"",
)

# ---------------------------------------------------------------- palette and geometry

NAME = "typewriter"
MIN_W, MIN_H = 80, 26
IDLE_SECS = 20.0
BELL_BEFORE = 8        # the bell rings this many columns before the right margin
TAB = 4
MARGIN = 5             # paper columns beside the typing area
TOP = 6                # blank lines of paper above the first typed line
E = 10                 # carriage beyond the paper, each side: platen, side plate, knob
PLATEN = 4             # platen columns showing beside the paper
LEVER = 6              # sprite columns left of the carriage for the return lever
SPRITE_UP = 5          # carriage sprite rows above the platen row
CPS = 14.0             # autopilot characters per second at --speed 1

WALL, GLOW = (30, 29, 29), (50, 45, 40)
DESK_HI, DESK, DESK_LO = (128, 92, 62), (88, 61, 42), (66, 46, 32)
PAPER = (239, 232, 213)
INKS = ((29, 26, 34), (36, 29, 30), (25, 29, 40))   # neutral, warm and blue-black ribbon ink
CHROME_HI, CHROME, CHROME_MID, CHROME_LO = (246, 247, 250), (200, 204, 211), (162, 167, 176), (110, 115, 124)
RUBBER, RUBBER_HI = (24, 24, 27), (70, 70, 76)
BAKELITE = ((58, 54, 52), (34, 31, 30))
CAP, CAP_HALF, CAP_DOWN, CAP_INK = (238, 228, 200), (208, 196, 168), (164, 150, 122), (62, 53, 44)
RIBBON_BLK, RIBBON_RED = (22, 22, 24), (166, 36, 36)
BASKET, BAR, BAR_HI = (19, 20, 21), (92, 96, 104), (236, 238, 242)
FINISHES = {
    "mint": dict(hi=(176, 216, 196), body=(128, 178, 158), lo=(86, 130, 114), well=(36, 48, 44)),
    "olive": dict(hi=(160, 166, 104), body=(116, 122, 72), lo=(78, 84, 46), well=(34, 36, 24)),
    "black": dict(hi=(92, 92, 100), body=(40, 40, 44), lo=(22, 22, 25), well=(12, 12, 14)),
    "red": dict(hi=(222, 104, 92), body=(178, 54, 48), lo=(126, 36, 34), well=(44, 18, 18)),
}
NAMEPLATE = "C L A C K E T T E"
ACTION_KEYS = {"enter", "backspace", "tab", "space", "up", "down", "left", "right"}
SHIFTED = {"!": "1", "@": "2", "#": "3", "$": "4", "%": "5", "^": "6", "&": "7", "*": "8", "(": "9",
           ")": "0", "_": "-", "+": "=", ":": ";", '"': "'", "<": ",", ">": ".", "?": "/", "{": "[",
           "}": "[", "]": "[", "|": "[", "\\": "[", "~": "'", "`": "'"}
# Overstrikes that typists used to build characters the keyboard lacked (order-free pairs).
COMBOS = {frozenset(p): g for p, g in (
    (("o", "/"), "ø"), (("O", "/"), "Ø"), (("=", "/"), "≠"), (("c", "|"), "¢"), (("-", "|"), "+"),
    (("-", ":"), "÷"), (("+", "_"), "±"), (("e", "'"), "é"), (("e", "`"), "è"), (("a", "`"), "à"),
    (("a", "'"), "á"), (("u", '"'), "ü"), (("o", '"'), "ö"), (("a", '"'), "ä"), (("n", "~"), "ñ"),
    (("c", ","), "ç"), (("<", "_"), "≤"), ((">", "_"), "≥"), (("=", "_"), "≡"), (("l", "-"), "ł"),
    (("L", "-"), "Ł"), (("S", "|"), "$"), (("O", "|"), "Φ"), (("o", "+"), "⊕"), (("y", "="), "¥"),
    (("L", "="), "£"), (("C", "="), "€"), (("'", "."), "!"), (("O", "-"), "Θ"), (("o", "x"), "⊗"))}


def lerp(a, b, t):
    return (int(a[0] + (b[0] - a[0]) * t + .5), int(a[1] + (b[1] - a[1]) * t + .5),
            int(a[2] + (b[2] - a[2]) * t + .5))


def shade(c, k):
    return (min(255, int(c[0] * k)), min(255, int(c[1] * k)), min(255, int(c[2] * k)))


def cellof(t, b):
    return (" ", None, t) if t == b else ("▀", t, b)


def printable(k):
    return len(k) == 1 and k >= " " and k.isprintable() and unicodedata.east_asian_width(k) not in "WF"


# ---------------------------------------------------------------- the static machine

class Machine:
    """Everything that does not move, rendered once per terminal size and finish: wall, desk,
    body, keyboard and typebar basket as cell rows, plus the geometry the frame needs."""

    def __init__(self, w, h, finish):
        self.w, self.h, self.f = w, h, FINISHES[finish]
        full = h >= 34
        kb = [("1234567890-=←", 0.0), ("⇥QWERTYUIOP[", -0.5), ("ASDFGHJKL;'↵", 0.75), ("⇧ZXCVBNM,./⇧", 0.25)]
        if not full:
            kb = kb[1:]
        n = len(kb)
        self.py = py = h - 12 - 2 * n
        self.sx = sx = w // 2
        self.line = max(30, min(76, w // 2 + 4))
        self.pw = self.line + 2 * MARGIN
        pitch = 6 if w >= 100 else 5
        keys = []
        for i, (labels, start) in enumerate(kb):
            for j, lab in enumerate(labels):
                keys.append([lab, round((start + j) * pitch), py + 7 + 2 * i])
        lo, hi = min(k[1] for k in keys), max(k[1] for k in keys)
        shift = sx - (lo + hi) // 2
        for k in keys:
            k[1] += shift
        self.kmin, self.kmax = lo + shift, hi + shift
        self.keys = [tuple(k) for k in keys]
        self.key_at = {}
        for i, (lab, _, _) in enumerate(self.keys):
            self.key_at.setdefault(lab, []).append(i)
        self.sy = sy = py + 7 + 2 * n
        self.ly = sy + 2
        half_sb = int(3.3 * pitch)
        self.space = (sx - half_sb + pitch // 2, sx + half_sb + pitch // 2)
        self.hw = hw = int((self.kmax - self.kmin + 10) * 0.37)
        self.bhw = bhw = int(hw * 0.6)
        self.pix = self._pixels()
        self.rows = self._cells()
        self.slots = {}
        for i, (lab, kx, ky) in enumerate(self.keys):
            a = (kx - (self.kmin + self.kmax) / 2) / ((self.kmax - self.kmin) / 2 or 1)
            a = max(-1.0, min(1.0, a * 0.92 + 0.03 * ((ky - py) % 4 - 1)))
            x = int(round(sx + a * (bhw - 2)))
            self.slots[i] = (x, py + 2 + int(2.5 * math.sqrt(max(0.0, 1 - a * a)) + .5))
        self.sprites = {}

    # -- pixels: two per cell, stacked; None is the wall behind
    def _pixels(self):
        w, h, f, py, sx, sy, ly = self.w, self.h, self.f, self.py, self.sx, self.sy, self.ly
        px = [[None] * w for _ in range(2 * h)]

        def put(x, y, c):
            if 0 <= x < w and 0 <= y < 2 * h:
                px[y][x] = c

        # desk with grain, and the machine's shadow on it
        for y in range(2 * (ly + 1), 2 * h):
            dy = y - 2 * (ly + 1)
            for x in range(w):
                g = math.sin(x * 0.045 + 2.2 * math.sin(x * 0.011 + y * 0.9) + y * 1.7)
                c = DESK_HI if dy == 0 else lerp(DESK, DESK_LO, 0.5 + 0.5 * g if dy > 1 else 0.2)
                c = lerp(c, DESK_LO, min(1.0, dy / 6) * 0.5)
                d = abs(x - sx) / (self.kmax - self.kmin + 16)
                if d < 0.56:
                    c = shade(c, 0.55 + 0.45 * min(1.0, dy / 4 + max(0.0, (d - 0.45) * 9)))
                put(x, y, c)
        # silhouette: an upper housing with rounded shoulders on a wider keyboard deck
        dl0, dr0 = self.kmin - 6, self.kmax + 6
        y_top, y_deck, y_bot = 2 * (py + 2), 2 * (py + 5), 2 * ly + 1
        body = {}
        for y in range(y_top, y_bot + 1):
            spans = []
            if y < y_deck + 2:
                r, x0, x1 = 6, sx - self.hw, sx + self.hw
                dy = y - y_top
                cut = r - math.sqrt(max(0.0, r * r - (r - dy - 0.5) ** 2)) if dy < r else 0
                spans.append((int(x0 + cut + 0.5), int(x1 - cut + 0.5)))
            if y >= y_deck:
                widen = int((y - y_deck) * 0.11)
                x0, x1 = dl0 - widen, dr0 + widen
                dy, r = y - y_deck, 5
                cut = r - math.sqrt(max(0.0, r * r - (r - dy - 0.5) ** 2)) if dy < r else 0
                db, rb = y_bot - y, 3
                if db < rb:
                    cut = max(cut, rb - math.sqrt(max(0.0, rb * rb - (rb - db - 0.5) ** 2)))
                spans.append((int(x0 + cut + 0.5), int(x1 - cut + 0.5)))
            x0, x1 = min(s[0] for s in spans), max(s[1] for s in spans)
            body[y] = (x0, x1, y < y_deck)
        for y, (x0, x1, upper) in body.items():
            if upper:
                t = (y - y_top) / max(1, y_deck - y_top)
                base = lerp(f["hi"], f["body"], min(1.0, t * 1.6))
            else:
                t = (y - y_deck) / max(1, y_bot - y_deck)
                base = lerp(f["body"], f["lo"], t ** 1.4 * 0.8)
                if y - y_deck < 2 and (x0 < sx - self.hw - 1 or x1 > sx + self.hw + 1):
                    base = f["hi"]  # lit edge of the deck's shoulders
            if y == y_top:
                base = f["hi"]
            for x in range(x0, x1 + 1):
                c = base
                rim = min(x - x0, x1 - x)
                if upper and y == y_top or (not upper and y == y_deck and abs(x - sx) > self.hw + 1):
                    c = lerp(f["hi"], CHROME_HI, 0.25)
                elif rim == 0:
                    c = lerp(base, f["lo"], 0.75)
                elif rim == 1:
                    c = lerp(base, f["lo"], 0.35)
                elif rim < 6 and x - x0 < 6:
                    c = lerp(base, f["hi"], 0.18 * (6 - rim) / 6)
                put(x, y, c)
        # lip under the spacebar carries the nameplate: one flat colour per cell
        for x in range(body[2 * ly][0] + 2, body[2 * ly][1] - 1):
            put(x, 2 * ly, f["lo"])
            put(x, 2 * ly + 1, f["lo"])
        self.lip = f["lo"]
        # feet
        for x0 in (body[y_bot][0] + 3, body[y_bot][1] - 6):
            for x in range(x0, x0 + 4):
                put(x, y_bot + 1, RUBBER)
        # keyboard well
        wx0, wx1, wy0, wy1 = self.kmin - 3, self.kmax + 3, 2 * (py + 6), 2 * sy + 3
        for y in range(wy0, wy1 + 1):
            dy = min(y - wy0, wy1 - y)
            cut = 3 - math.sqrt(max(0.0, 9 - (3 - dy - 0.5) ** 2)) if dy < 3 else 0
            for x in range(int(wx0 + cut + .5), int(wx1 - cut + .5) + 1):
                c = lerp(f["well"], shade(f["well"], 0.6), (y - wy0) / (wy1 - wy0))
                put(x, y, c if y > wy0 else lerp(f["well"], f["lo"], 0.5))
        self.well = f["well"]
        # keys: shadow, chrome ring, cream cap two pixels tall so the label cell is one colour
        for lab, kx, ky in self.keys:
            for x in range(kx - 1, kx + 2):
                put(x, 2 * ky + 3, shade(f["well"], 0.45))
        for lab, kx, ky in self.keys:
            self._key(put, kx, ky, CAP, CHROME_HI, CHROME, CHROME_LO)
        # spacebar
        s0, s1 = self.space
        for x in range(s0, s1 + 1):
            end = x in (s0, s1)
            if not end:
                put(x, 2 * sy - 1, CHROME_HI)
                put(x, 2 * sy + 2, CHROME_LO)
                put(x, 2 * sy + 3, shade(f["well"], 0.45))
            put(x, 2 * sy, CHROME)
            put(x, 2 * sy + 1, CHROME_MID)
        # typebar basket: a dark half-ellipse opening, with the chrome segment at its top
        bhw, by0 = self.bhw, 2 * (py + 2)
        for y in range(by0, by0 + 8):
            span = bhw * math.sqrt(max(0.0, 1 - ((y - by0 + 0.5) / 7.5) ** 2))
            for x in range(int(sx - span + .5), int(sx + span + .5) + 1):
                put(x, y, BASKET if y > by0 else lerp(BASKET, f["lo"], 0.4))
        for y in (by0, by0 + 1):
            for x in range(sx - 3, sx + 4):
                put(x, y, CHROME_HI if y == by0 else CHROME_LO)
        # ribbon spools either side of the basket
        for side in (-1, 1):
            cx = sx + side * (bhw + (self.hw - bhw) // 2 + 1)
            for y in range(by0, by0 + 6):
                for x in range(cx - 4, cx + 5):
                    d = math.hypot((x - cx) / 3.6, (y - by0 - 2.5) / 2.9)
                    if d < 1:
                        c = CHROME_HI if d > 0.78 and y < by0 + 2 else CHROME if d > 0.7 else RIBBON_BLK
                        if d < 0.3:
                            c = CHROME_MID
                        put(x, y, c)
        return px

    @staticmethod
    def _key(put, kx, ky, cap, top, side, bot):
        for x in range(kx - 1, kx + 2):
            put(x, 2 * ky - 1, top)
            put(x, 2 * ky, cap)
            put(x, 2 * ky + 1, cap)
            put(x, 2 * ky + 2, bot)
        for x in (kx - 2, kx + 2):
            put(x, 2 * ky, side)
            put(x, 2 * ky + 1, bot)

    def wall(self, x, y):
        d = math.hypot((x - self.sx) / (self.w * 0.78), (y - self.py * 0.42) / (self.h * 0.95))
        g = max(0.0, 1 - d) ** 1.3
        return lerp(WALL, GLOW, int(g * 24) / 24)

    def _cells(self):
        w, px = self.w, self.pix
        rows = []
        for y in range(self.h):
            top, bot = px[2 * y], px[2 * y + 1]
            row = []
            for x in range(w):
                t, b = top[x], bot[x]
                if t is None or b is None:
                    wc = self.wall(x, y)
                    t, b = t or wc, b or wc
                row.append(cellof(t, b))
            rows.append(row)
        for lab, kx, ky in self.keys:
            rows[ky][kx] = (lab, CAP_INK, CAP)
        # typebars at rest, fanned toward the strike point
        py, sx = self.py, self.sx
        for y in range(py + 2, py + 6):
            for x in range(sx - self.bhw, sx + self.bhw + 1):
                ch, fg, bg = rows[y][x]
                if bg != BASKET or ch != " " or (x - sx) % 2:
                    continue
                dx, dy = sx - x, (y - py) * 2.0
                s = dx / dy
                g = "│" if abs(s) < 0.45 else ("╱" if s > 0 else "╲")
                rows[y][x] = (g, lerp(BAR, BASKET, 0.35 * (py + 5 - y) / 3), BASKET)
        s = NAMEPLATE
        x0 = self.sx - len(s) // 2
        for i, ch in enumerate(s):
            if ch != " ":
                rows[self.ly][x0 + i] = (ch, CHROME_HI, self.lip)
        rows[self.py + 2][sx] = ("▼", RIBBON_RED, CHROME_HI)
        return rows

    def key_cells(self, i, depth):
        """The three cells of key i pressed in (depth 1) or half way (0.5): darker cap, a
        dimmed ring, and the ring's top half hidden as the key sinks."""
        lab, kx, ky = self.keys[i]
        cap = CAP_DOWN if depth > 0.75 else CAP_HALF
        out = []
        for x in range(kx - 2, kx + 3):
            t, b = self.pix[2 * ky][x], self.pix[2 * ky + 1][x]
            if kx - 1 <= x <= kx + 1:
                out.append((x, ky, (lab, shade(CAP_INK, 0.8), cap) if x == kx else (" ", None, cap)))
                top_t = self.pix[2 * ky - 2][x] or self.wall(x, ky - 1)
                out.append((x, ky - 1, cellof(top_t, self.well if depth > 0.75 else CHROME_MID)))
            else:
                out.append((x, ky, cellof(shade(t, 0.8), shade(b, 0.8))))
        return out

    def space_cells(self, depth):
        s0, s1 = self.space
        sy = self.sy
        k = 0.78 if depth > 0.75 else 0.9
        out = []
        for x in range(s0, s1 + 1):
            out.append((x, sy, cellof(shade(CHROME, k), shade(CHROME_MID, k))))
            if s0 < x < s1:
                above = self.pix[2 * sy - 2][x] or self.wall(x, sy - 1)
                out.append((x, sy - 1, cellof(above, self.well if depth > 0.75 else CHROME_MID)))
        return out

    # -- the carriage: built in pixels with transparency, blitted each frame at its offset
    def sprite(self, lever, phase):
        key = (lever, phase)
        if key in self.sprites:
            return self.sprites[key]
        pw = self.pw
        sw = LEVER + E + pw + E
        rows_px = (SPRITE_UP + 2) * 2
        px = [[None] * sw for _ in range(rows_px)]
        chars = {}
        o = 4  # pixel rows above the bail
        p0, p1 = LEVER + E, LEVER + E + pw  # paper columns

        def put(x, y, c):
            if 0 <= x < sw and 0 <= y < rows_px:
                px[y][x] = c

        # platen: a rubber cylinder, shaded across its height
        for x in list(range(p0 - PLATEN, p0)) + list(range(p1, p1 + PLATEN)):
            for dy, c in enumerate((RUBBER, RUBBER_HI, (52, 52, 57), RUBBER, (14, 14, 16))):
                put(x, o + 3 + dy, c)
        # rail with the paper scale
        for x in range(p0 - PLATEN - 2, p1 + PLATEN + 2):
            put(x, o + 8, CHROME)
            put(x, o + 9, CHROME)
            col = x - p0 - MARGIN
            if 0 <= col <= self.line:
                ch = str(col // 10 % 10) if col % 10 == 0 else "'" if col % 5 == 0 else "·"
                chars[(x, SPRITE_UP + 1)] = (ch, (66, 70, 78) if col % 10 == 0 else (120, 124, 132))
        # side plates and bail arms
        for x0 in (p0 - PLATEN - 2, p1 + PLATEN):
            for y in range(o + 1, o + 10):
                put(x0, y, CHROME_HI if y < o + 3 else CHROME)
                put(x0 + 1, y, CHROME_MID if y < o + 8 else CHROME_LO)
        # bail rod across the paper with two rubber rollers
        for x in range(p0 - PLATEN - 1, p1 + PLATEN + 1):
            put(x, o + 1, CHROME_HI)
        for rx in (p0 + 2, p1 - 3):  # rollers ride the paper margins, clear of the text
            for x in range(rx - 1, rx + 2):
                put(x, o, RUBBER_HI if x == rx else RUBBER)
                put(x, o + 1, RUBBER)
        # knobs: knurled bakelite, a chrome centre; the knurl shifts as the platen turns
        for cx in (LEVER + 1.5, p1 + PLATEN + 3.5):
            for y in range(o, o + 11):
                for x in range(int(cx - 3), int(cx + 4)):
                    d = math.hypot((x + 0.5 - cx - 0.5) / 2.35, (y + 0.5 - o - 5.5) / 5.2)
                    if d < 1:
                        c = BAKELITE[(x + phase) % 2]
                        if d > 0.8:
                            c = CHROME_MID if y < o + 6 else CHROME_LO
                        elif x + 0.5 < cx and y < o + 5:
                            c = lerp(c, (104, 98, 92), 0.35 * (1 - d))
                        if d < 0.3:
                            c = CHROME_HI if y < o + 5 else CHROME_MID
                        put(x, y, c)
        # return lever on the left: an arm up and out, swung toward the paper when pushed
        bx, by = LEVER + 3, o + 3
        tx, ty = (LEVER + 1, 0) if lever else (0, 1)
        steps = 12
        for i in range(steps + 1):
            u = i / steps
            x, y = int(round(bx + (tx - bx) * u)), int(round(by + (ty - by) * u))
            put(x, y, CHROME_HI)
            put(x, y + 1, CHROME_LO)
        for dx, dy, c in ((0, 0, CHROME_HI), (1, 0, CHROME_HI), (0, 1, CHROME), (1, 1, CHROME_MID),
                          (-1, 0, CHROME), (-1, 1, CHROME_LO)):
            put(tx + dx, ty + dy, c)
        ents = []
        for r in range(rows_px // 2):
            row = []
            for x in range(sw):
                t, b = px[2 * r][x], px[2 * r + 1][x]
                if (x, r) in chars and t is not None and t == b:
                    ch, fg = chars[(x, r)]
                    row.append((x, 0, (ch, fg, t)))
                elif t is not None and b is not None:
                    row.append((x, 0, cellof(t, b)))
                elif t is not None:
                    row.append((x, 1, t))
                elif b is not None:
                    row.append((x, 2, b))
            ents.append(row)
        self.sprites[key] = ents
        return ents


# ---------------------------------------------------------------- the page

class Page:
    """Typed strikes per (line, col), each with its own ink, and cached paper rows."""

    def __init__(self, rng):
        self.lines = {}
        self.ver = collections.Counter()
        self.cache = {}
        self.rng = rng
        self.count = 0

    def stamp(self, line, col, ch):
        r = self.rng.random()
        smudge = False
        if r < 0.05:
            d = self.rng.uniform(0.42, 0.6)          # a light letter
        elif r < 0.09:
            d, smudge = 1.0, True                    # a heavy double strike
        else:
            d = self.rng.uniform(0.74, 0.97)
        self.count += 1
        d *= 0.93 + 0.07 * math.sin(self.count / 37.0)  # the ribbon wears unevenly
        tint = 0 if self.rng.random() < 0.7 else self.rng.choice((1, 2))
        self.lines.setdefault(line, {}).setdefault(col, []).append((ch, round(d * 16) / 16, tint, smudge))
        self.ver[line] += 1

    def glyph(self, strikes):
        """(glyph, density, tint, smudged) for a cell; overstrikes combine where a typist
        would, and always ink darker."""
        ch, d, tint, sm = strikes[-1]
        if len(strikes) == 1:
            return ch, d, tint, sm
        chars = [s[0] for s in strikes]
        if len(set(chars)) > 1:
            a, b = chars[-1], next(c for c in reversed(chars) if c != chars[-1])
            ch = COMBOS.get(frozenset((a, b)), ch)
        return ch, min(1.0, max(s[1] for s in strikes) + 0.12 * (len(strikes) - 1)), tint, True

    def text_line(self, line):
        cols = self.lines.get(line, {})
        if not cols:
            return ""
        out = [" "] * (max(cols) + 1)
        for c, st in cols.items():
            if c >= 0:
                out[c] = self.glyph(st)[0]
        return "".join(out).rstrip()

    def row(self, line, band, pw):
        key = (line, band)
        hit = self.cache.get(key)
        v = self.ver[line]
        if hit and hit[0] == v and len(hit[1]) == pw:
            return hit[1]
        paper = PAPER_BANDS[band]
        cols = self.lines.get(line, {})
        cells = []
        for x in range(pw):
            h = ((line * 92821) ^ (x * 68917)) * 2654435761 >> 13 & 15
            bg = paper[0 if h < 9 else 1 if h < 13 else 2 if h < 15 else 3]
            if x == 0 or x == pw - 1:
                bg = shade(bg, 0.93)
            st = cols.get(x - MARGIN)
            if st:
                ch, d, tint, sm = self.glyph(st)
                if sm:
                    bg = shade(bg, 0.955)
                cells.append((ch, lerp(bg, INKS[tint], d), bg))
            else:
                cells.append((" ", None, bg))
        if len(self.cache) > 600:
            self.cache.clear()
        self.cache[key] = (v, cells)
        return cells


# Paper by screen band: open page, the row under the bail, and the two rows curving over the platen.
PAPER_BANDS = [[shade(c, k) for k in (1.0, 0.993, 1.005, 0.985)]
               for c in (PAPER, shade(PAPER, 0.955), shade(PAPER, 0.97), shade(PAPER, 0.94))]


# ---------------------------------------------------------------- autopilot

def plan_art(name, aw, rows, offset, rng):
    lines = render_art(name, aw, rows, rng)
    cap = CAPTIONS.get(name, "")
    acts = [("enter", 0.5)]
    acts += type_lines(lines, offset, rng, art=True)
    acts.append(("enter", 0.4))
    acts += type_lines([" " * max(0, (aw - len(cap)) // 2) + cap], offset, rng)
    acts += [("enter", 0.5), ("pause", 2.5)]
    return acts


def plan_verse(lines, width, rng):
    wrapped = []
    for s in lines:
        lead = len(s) - len(s.lstrip(" "))
        wrapped += [" " * lead + p for p in textwrap.wrap(s.strip(), max(10, width - lead))] if s.strip() else [""]
    acts = [("enter", 0.5)]
    acts += type_lines(wrapped, 4, rng)
    acts += [("enter", 0.5), ("pause", 2.0)]
    return acts


def plan_secret(rng, which="ring"):
    """The acrostic ("ring") or Shelley's Ozymandias ("ozymandias")."""
    lines, sign, strike = ((SECRET, "- the typewriter, who was listening", True) if which == "ring"
                           else (OZYMANDIAS, "- Percy Bysshe Shelley, 1818", False))
    acts = [("enter", 0.5), ("pause", 0.8)]
    acts += type_lines(lines, 4, rng, strike_first=strike)
    acts += [("enter", 0.4)]
    acts += type_lines([sign], 18, rng)
    acts += [("enter", 0.5), ("pause", 3.0)]
    return acts


def type_lines(lines, offset, rng, art=False, strike_first=False):
    """Key actions for lines. strike_first overstrikes each line's first letter (type,
    backspace, type) so it inks darker."""
    acts = []
    for s in lines:
        s = s.rstrip()
        lead = len(s) - len(s.lstrip(" ")) + offset
        body = s.lstrip(" ")
        if body:
            for _ in range(lead // TAB):
                acts.append(("tab", 0.16 / (1 + art)))
            for _ in range(lead % TAB):
                acts.append(("space", 0.05))
        prev = ""
        for ch in body:
            base = 1 / CPS * rng.lognormvariate(0, 0.25)
            if art:
                base *= 0.45 if ch == " " else 0.85
                if ch == prev:
                    base *= 0.75
            else:
                if ch in ",.;:!?-":
                    base += rng.uniform(0.1, 0.25)
                elif ch == " ":
                    base *= 1.25
                elif ch == prev:
                    base *= 0.8
                if rng.random() < 0.025:
                    base += rng.uniform(0.25, 0.7)   # a moment's thought
            acts.append(("space" if ch == " " else ch, base))
            if strike_first and not prev:
                acts += [("backspace", 0.22), (ch, 0.3)]
            prev = ch
        acts.append(("enter", rng.uniform(0.45, 0.8) if not art else rng.uniform(0.32, 0.5)))
    return acts


# ---------------------------------------------------------------- main

def main():
    parser = term.make_parser(__doc__.splitlines()[0], fps=30)
    parser.add_argument("--auto", action="store_true", help="the machine types by itself from the start")
    parser.add_argument("--speed", type=float, default=1.0, help="autopilot typing speed multiplier")
    parser.add_argument("--seed", type=int, default=None, help="random seed (art order, ink)")
    parser.add_argument("--finish", choices=sorted(FINISHES), default="mint", help="enamel colour")
    parser.add_argument("--save", metavar="FILE", help="write the typed page to FILE on quit")
    args = parser.parse_args()
    rng = random.Random(args.seed)
    dt = 1 / max(1.0, args.fps)
    speed = max(0.1, args.speed)
    tty = os.isatty(0)
    page = Page(random.Random(rng.random()))
    st = dict(m=None, line=0, col=0, car=0.0, ret=None, lever_until=-1.0, phase=0, t=0.0,
              idle=0.0, auto=args.auto or not tty, plan=collections.deque(), wait=0.0,
              pieces=[], verses=[], kind="art", keys={}, bars=[], ding=-9.0, margin_warned=-1,
              space=-9.0, heard="", egg=False)

    def sfx(name, vol=1.0):
        audio.sfx(name, vol * (0.7 if st["auto"] else 1.0))

    def key_anim(label):
        m = st["m"]
        for i in m.key_at.get(label, ()):
            st["keys"][i] = st["t"]

    def advance(n=1):
        m, before = st["m"], st["col"]
        st["col"] = min(m.line, st["col"] + n)
        bell_at = m.line - BELL_BEFORE
        if before < bell_at <= st["col"]:
            sfx("tw_bell", 0.8)
            st["ding"] = st["t"]

    def carriage_return():
        m = st["m"]
        dist = st["car"]
        st["ret"] = (st["t"], dist, 0.1 + 0.0055 * dist)
        st["col"] = 0
        st["line"] += 1
        st["phase"] ^= 1
        st["lever_until"] = st["t"] + 0.22
        key_anim("↵")
        sfx("tw_feed")
        if dist > 1:
            sfx("tw_return", 0.5 + 0.5 * min(1.0, dist / m.line))

    def press(k):
        m = st["m"]
        if k == "enter":
            carriage_return()
        elif k in ("backspace", "left"):
            if st["col"] > 0:
                st["col"] -= 1
            key_anim("←")
            sfx("tw_back")
        elif k == "tab":
            advance(TAB)
            key_anim("⇥")
            sfx("tw_back", 0.8)
        elif k in ("up", "down"):
            st["line"] += -1 if k == "up" else 1
            st["phase"] ^= 1
            sfx("tw_feed", 0.6)
        elif k in ("space", "right"):
            st["space"] = st["t"]
            if st["col"] < m.line:
                advance()
            sfx("tw_space")
        elif printable(k):
            base = k if k.isalnum() and k.isascii() else SHIFTED.get(k, k)
            key_anim(base.upper())
            if k.isupper() or k in SHIFTED:
                key_anim("⇧")
            slot_keys = m.key_at.get(base.upper())
            if slot_keys:
                st["bars"].append((m.slots[slot_keys[0]], st["t"]))
            page.stamp(st["line"], st["col"], k)
            if st["col"] >= m.line:
                if st["margin_warned"] != st["line"] and not st["auto"]:
                    game.toast("right margin: press Enter", 2.0)
                    st["margin_warned"] = st["line"]
            else:
                advance()
            sfx(f"tw_clack{rng.randrange(4)}", rng.uniform(0.75, 1.0))

    def next_piece():
        m = st["m"]
        room = m.line - BELL_BEFORE - 1  # art stays left of the bell so it doesn't ring every line
        aw = min(room - 2, max(30, int(m.py * 2.4)))
        rows = int(aw * 0.45)
        if st["kind"] == "art":
            if not st["pieces"]:
                st["pieces"] = list(IMAGES)
                rng.shuffle(st["pieces"])
            acts = plan_art(st["pieces"].pop(), aw, rows, (room - aw) // 2 + 1, rng)
            st["kind"] = "verse"
        else:
            if rng.random() < 0.5:
                acts = plan_secret(rng, rng.choice(("ring", "ozymandias")))
            else:
                if not st["verses"]:
                    st["verses"] = list(range(len(VERSES)))
                    rng.shuffle(st["verses"])
                acts = plan_verse(VERSES[st["verses"].pop()], m.line - 8, rng)
            st["kind"] = "art"
        if st["col"] > 0:
            acts.insert(0, ("enter", 0.6))
        st["plan"].extend(acts)

    def autopilot():
        st["wait"] -= dt * speed
        while st["wait"] <= 0:
            if not st["plan"]:
                next_piece()
            k, delay = st["plan"].popleft()
            if k != "pause":
                press(k)
            if k == "enter" and st["ret"]:
                delay += st["ret"][2] / speed
            st["wait"] += delay

    def save():
        lines = sorted(page.lines)
        if not lines:
            return
        text = "\n".join(page.text_line(L) for L in range(min(lines), max(lines) + 1)).rstrip() + "\n"
        try:
            with open(args.save, "w", encoding="utf-8") as f:
                f.write(text)
        except OSError as e:
            print(f"typewriter: could not save the page to {args.save}: {e}", file=sys.stderr)
            return 1
        print(f"typewriter: page saved to {args.save}", file=sys.stderr)

    def draw(c):
        m = st["m"]
        cells = [row[:] for row in m.rows]
        py, sx, pw, w, t = m.py, m.sx, m.pw, m.w, st["t"]
        if st["ret"]:
            t0, dist, dur = st["ret"]
            u = min(1.0, (t - t0) / dur)
            st["car"] = dist * (1 - u) ** 2
            if u >= 1:
                st["ret"] = None
        else:
            st["car"] += (st["col"] - st["car"]) * (1 - 0.3 ** (dt * 30))
            if abs(st["car"] - st["col"]) < 0.3:
                st["car"] = float(st["col"])
        pl = sx - MARGIN - int(round(st["car"]))
        a, b = max(0, pl), min(w, pl + pw)
        for y in range(0, py + 1):
            L = st["line"] - (py - y)
            if L < -TOP or a >= b:
                continue
            band = 3 if y == py else 2 if y == py - 1 else 1 if y == py - 2 else 0
            cells[y][a:b] = page.row(L, band, pw)[a - pl:b - pl]
        ox = pl - E - LEVER
        spr = m.sprite(t < st["lever_until"], st["phase"])
        for r, ents in enumerate(spr):
            row = cells[py - SPRITE_UP + r]
            for x, kind, val in ents:
                X = ox + x
                if 0 <= X < w:
                    if kind == 0:
                        row[X] = val
                    else:
                        ch, fg, bg = row[X]
                        if ch != " " and pl <= X < pl + pw:
                            # the bail rod crosses typed text: keep the letter legible on a chrome tint
                            row[X] = (ch, fg, lerp(bg, CHROME_MID, 0.4))
                        else:
                            row[X] = ("▀" if kind == 1 else "▄", val, bg)
        # typebars in flight: up to the strike point and back down
        raised = False
        live = []
        for (bx, by), t0 in st["bars"]:
            age = t - t0
            if age > 0.16:
                continue
            live.append(((bx, by), t0))
            u = age / 0.16
            reach = min(1.0, u / 0.35) if u < 0.5 else max(0.0, 1 - (u - 0.5) / 0.5)
            raised |= 0.15 < u < 0.6
            tx, ty = bx + (sx - bx) * reach, by + (py + 1 - by) * reach
            if cells[by][bx][2] == BASKET:
                cells[by][bx] = (" ", None, BASKET)
            dx, dy = tx - bx, (ty - by) * 2
            g = "│" if abs(dx) < 0.45 * abs(dy) else ("╱" if dx > 0 else "╲") if abs(dx) < 3 * abs(dy) or dy else "─"
            n = int(max(abs(tx - bx), abs(ty - by)) * 1.5) + 1
            for i in range(n + 1):
                x, y = int(round(bx + (tx - bx) * i / n)), int(round(by + (ty - by) * i / n))
                if 0 <= x < w and y < m.h:
                    cells[y][x] = (g if i < n else "▪", BAR_HI if i < n else CHROME_LO, cells[y][x][2])
        st["bars"] = live
        # the ribbon, lifted over the strike point while a typebar hits
        ry = py if raised else py + 1
        for x in range(sx - 2, sx + 3):
            cells[ry][x] = ("▀", RIBBON_BLK, RIBBON_RED)
        if not raised:
            cells[py + 1][sx - 3] = ("▐", CHROME_HI, cells[py + 1][sx - 3][2])
            cells[py + 1][sx + 3] = ("▌", CHROME_HI, cells[py + 1][sx + 3][2])
        # keys dipping
        for i, t0 in list(st["keys"].items()):
            age = t - t0
            if age > 0.2:
                del st["keys"][i]
                continue
            depth = 1.0 if age < 0.09 else 0.5
            for x, y, cell in m.key_cells(i, depth):
                cells[y][x] = cell
        age = t - st["space"]
        if age < 0.2:
            for x, y, cell in m.space_cells(1.0 if age < 0.09 else 0.5):
                cells[y][x] = cell
        age = t - st["ding"]
        if age < 0.9:
            dx = min(w - 7, ox + LEVER + E + pw + 2)
            col = lerp((250, 214, 120), (120, 104, 70), age / 0.9)
            for i, ch in enumerate("ding!"):
                yy = py - SPRITE_UP - 1 - int(age * 3)
                if 0 <= yy:
                    cells[yy][dx + i] = (ch, col, cells[yy][dx + i][2])
        c.cells = cells

    def too_small(c):
        c.clear()
        msg = f"typewriter needs {MIN_W}x{MIN_H} (Ctrl-C quits)"
        lines = textwrap.wrap(msg, max(1, c.w)) or [""]
        for i, s in enumerate(lines[:c.h]):
            c.text(max(0, (c.w - len(s)) // 2), max(0, (c.h - len(lines)) // 2) + i, s[:c.w], 226)

    def step(c, frame, keys):
        if "ctrl-d" in keys:
            return True
        if frame == 0:
            game.toast("type away · Enter returns · Esc m mutes · Ctrl-C quits", 6.0)
        if c.w < MIN_W or c.h < MIN_H:
            too_small(c)
            return False
        if st["m"] is None or (st["m"].w, st["m"].h) != (c.w, c.h):
            st["m"] = Machine(c.w, c.h, args.finish)
            st["col"] = min(st["col"], st["m"].line)
        st["t"] += dt
        typed = [k for k in keys if printable(k) or k in ACTION_KEYS]
        if typed:
            st["idle"] = 0.0
            if st["auto"]:
                st["auto"] = False
                st["plan"].clear()
                if st["col"] > 0 and typed[0] != "enter":
                    carriage_return()
            for k in typed:
                press(k)
                if printable(k) and len(k) == 1:
                    st["heard"] = (st["heard"] + k.lower())[-len(SECRET_WORD):]
                    st["egg"] = st["heard"] == SECRET_WORD
                elif k != "space":
                    st["egg"] = False
        else:
            st["idle"] += dt
            if st["egg"] and st["idle"] >= 1.2:
                st["egg"], st["heard"] = False, ""
                st["auto"], st["wait"] = True, 0.3
                st["plan"].clear()
                st["plan"].extend(plan_secret(rng))
            elif not st["auto"] and st["idle"] >= IDLE_SECS:
                st["auto"], st["wait"] = True, 0.6
                game.toast("the machine types by itself; any key takes over", 3.0)
        if st["auto"]:
            autopilot()
        draw(c)
        return False

    rc = game.play(args, step, raw_keys=True, mute_key="alt-m", mute_label="Esc m")
    if args.save:
        rc = save() or rc
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
