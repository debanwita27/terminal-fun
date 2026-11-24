#!/usr/bin/env python3
"""Bullet Hell: a twin-stick dungeon roguelite. Clear locked rooms, beat three bosses.

Usage: python3 bullethell.py [--fps 30] [--frames N] [--seed S | --daily]
                             [--difficulty easy|normal|hard] [--demo] [--floor N]
A run is three biomes of three floors; the third floor of each ends in a boss. Rooms lock
until their waves are cleared. Between floors you pick one of three upgrades.

  WASD           move (tap the opposite key to stop short)
  arrow keys     shoot; two arrows together aim diagonally
  mouse          aim at the cursor, hold the button to shoot (if the terminal reports it)
  space          dash: a short burst with invulnerability
  f / tab        swap weapons          e / enter  buy, open, pick up
  p / esc        pause (lists the controls)    r  new run (paused or after a run)
  q              quit
  --seed S       fixed run seed; --daily uses today's date. Rooms are sized to the terminal
                 when a run starts, so a seed replays the same run at the same terminal size
  --difficulty   easy (more health, slower bullets), normal, hard
  --demo         an autopilot plays (also the default without a tty)
  --floor N      start on floor N (1-9) with a few random upgrades
"""

META = {'name': 'bullethell',
        'kind': 'play',
        'blurb': 'Twin-stick dungeon roguelite: locked rooms, bullet patterns, builds and three bosses',
        'credit': [{'type': 'inspired by',
                    'who': 'bullet_hell by Srijan Paul (injuly)',
                    'url': 'https://github.com/srijan-paul/bullet_hell'},
                   {'type': 'taken from',
                    'who': 'bullet_hell pixel art (player, fly, stinger, corpses, ball bullet, door, '
                           'barrel, explosion, cursor, handgun, tilesheet) by Srijan Paul (injuly), MIT',
                    'url': 'https://github.com/srijan-paul/bullet_hell/tree/master/assets/image'},
                   {'type': 'taken from',
                    'who': 'bullet_hell sound assets (hurt, hit, explosion, laser, spaceship music) '
                           'via Srijan Paul (injuly), MIT',
                    'url': 'https://github.com/srijan-paul/bullet_hell/tree/master/assets/sound'},
                   {'type': 'taken from',
                    'who': 'SFX Laser Shoot 02 by bolkmar, CC BY 4.0',
                    'url': 'https://freesound.org/people/bolkmar/sounds/421704/'},
                   {'type': 'taken from',
                    'who': 'Attack.ogg by MortisBlack, CC BY 4.0',
                    'url': 'https://freesound.org/people/MortisBlack/sounds/385049/'},
                   {'type': 'taken from',
                    'who': 'Retro video game sfx - Explode by OwlStorm (Ashe Kirk), CC0',
                    'url': 'https://freesound.org/people/OwlStorm/sounds/404754/'}]}

import argparse
import hashlib
import math
import os
import random
import re
import struct
import sys
import threading
import time
import urllib.request
import zlib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

from fun import audio, game, synth, term

NAME = "bullethell"

# ------------------------------------------------------------------------------ assets
# Srijan Paul's art and sounds are never vendored: they load from a local clone of
# bullet_hell when there is one, else download once into the cache in the background.
# Until they arrive (or if they never do) the game draws its own stand-ins.

ASSET_BASE = os.environ.get("CLAUDE_FUN_BULLETHELL_ASSETS_URL",
                            "https://raw.githubusercontent.com/srijan-paul/bullet_hell/master/assets/")
LOCAL_DIRS = [os.path.expanduser(p) for p in (
    os.environ.get("CLAUDE_FUN_BULLETHELL_ASSETS", ""),
    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__)))),
                 "bullet_hell", "assets")) if p]
IMAGE_CACHE = os.path.join(os.path.dirname(synth.CACHE_DIR), "bullethell", "images")
IMAGES = ("player_yellow", "fly", "stinger", "fly_corpse", "stinger_corpse", "ball", "door",
          "explosive_barrel", "explosion_red", "cursor", "handgun", "tilesheet")
SOUND_FILES = {
    "shoot": "421704__bolkmar__sfx-laser-shoot-02.wav",
    "beam": "laser.mp3",
    "ehurt": "enemy_hurt.wav",
    "phurt": "player_hurt.wav",
    "wall": "bullet_hit_wall.wav",
    "exit": "bullet_world_exit.wav",
    "boom": "explosion_2.wav",
    "bigboom": "404754__owlstorm__retro-video-game-sfx-explode.wav",
    "attack": "385049__mortisblack__attack.ogg",
    "music": "spaceship.wav",
}
# Synth recipes (fun/synth.py) that stand in for a sound until or unless its file arrives.
SYNTH_STANDIN = {"shoot": "tick", "beam": "glitch", "ehurt": "swat", "phurt": "bonk", "wall": "plip",
                 "exit": "swoosh", "boom": "boom", "bigboom": "boom", "attack": "frogsnap",
                 "music": "blackhole"}


def read_png(data):
    """(w, h, rows of (r, g, b, a)) from 8-bit RGBA, RGB, grey or palette PNG bytes."""
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG")
    i, idat, plte, trns = 8, bytearray(), b"", b""
    w = h = ct = 0
    while i + 8 <= len(data):
        n, kind = struct.unpack(">I4s", data[i:i + 8])
        body = data[i + 8:i + 8 + n]
        i += 12 + n
        if kind == b"IHDR":
            w, h, depth, ct, _, _, lace = struct.unpack(">IIBBBBB", body)
            if depth != 8 or lace:
                raise ValueError("only 8-bit, non-interlaced PNGs")
        elif kind == b"PLTE":
            plte = body
        elif kind == b"tRNS":
            trns = body
        elif kind == b"IDAT":
            idat += body
        elif kind == b"IEND":
            break
    bpp = {6: 4, 2: 3, 3: 1, 0: 1, 4: 2}[ct]
    raw, stride, p = zlib.decompress(bytes(idat)), w * bpp, 0
    prev, rows = bytearray(stride), []
    for _ in range(h):
        f, line = raw[p], bytearray(raw[p + 1:p + 1 + stride])
        p += 1 + stride
        for x in range(stride):
            a = line[x - bpp] if x >= bpp else 0
            b = prev[x]
            if f == 1:
                line[x] = (line[x] + a) & 255
            elif f == 2:
                line[x] = (line[x] + b) & 255
            elif f == 3:
                line[x] = (line[x] + (a + b) // 2) & 255
            elif f == 4:
                c = prev[x - bpp] if x >= bpp else 0
                pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                line[x] = (line[x] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        if ct == 6:
            row = [tuple(line[k:k + 4]) for k in range(0, stride, 4)]
        elif ct == 2:
            row = [tuple(line[k:k + 3]) + (255,) for k in range(0, stride, 3)]
        elif ct == 3:
            row = [tuple(plte[3 * k:3 * k + 3]) + (trns[k] if k < len(trns) else 255,) for k in line]
        elif ct == 0:
            row = [(v, v, v, 255) for v in line]
        else:
            row = [(line[k], line[k], line[k], line[k + 1]) for k in range(0, stride, 2)]
        rows.append(row)
        prev = line
    return w, h, rows


class Art:
    """Srijan's PNGs as {name: (w, h, rows)}. `version` bumps whenever images arrive, so
    sprite caches know to rebuild."""

    def __init__(self, fetch=True):
        self.img, self.version, self.state, self.errors = {}, 0, "loading", []
        for d in LOCAL_DIRS:
            if all(os.path.exists(os.path.join(d, "image", n + ".png")) for n in IMAGES):
                self._load_dir(os.path.join(d, "image"))
                self.state = "ready"
                return
        if all(os.path.exists(os.path.join(IMAGE_CACHE, n + ".png")) for n in IMAGES):
            self._load_dir(IMAGE_CACHE)
            self.state = "ready"
        elif fetch:
            threading.Thread(target=self._fetch, daemon=True).start()
        else:
            self.state = "failed"

    def _load_dir(self, d):
        for n in IMAGES:
            try:
                with open(os.path.join(d, n + ".png"), "rb") as f:
                    self.img[n] = read_png(f.read())
            except (OSError, ValueError, KeyError, zlib.error) as e:
                self.errors.append(f"{n}.png: {e}")
        self.version += 1

    def _fetch(self):
        try:
            os.makedirs(IMAGE_CACHE, exist_ok=True)
        except OSError as e:
            self.errors.append(str(e))
            self.state = "failed"
            return
        for n in IMAGES:
            path = os.path.join(IMAGE_CACHE, n + ".png")
            if os.path.exists(path):
                continue
            tmp = f"{path}.{os.getpid()}.part"
            try:
                with urllib.request.urlopen(ASSET_BASE + "image/" + n + ".png", timeout=20) as r:
                    data = r.read()
                read_png(data)  # never cache a file we cannot decode
                with open(tmp, "wb") as f:
                    f.write(data)
                os.replace(tmp, path)
            except Exception as e:  # offline or HTTP error: the stand-in art stays
                self.errors.append(f"{n}.png: {e}")
                if os.path.exists(tmp):
                    os.remove(tmp)
                self.state = "failed"
                return
        self._load_dir(IMAGE_CACHE)
        self.state = "ready"


class Sounds:
    """Srijan's sound files: local clone first, else an audio.Pack download, else synth."""

    def __init__(self):
        self.local, self.pack, self.music_on, self.last = {}, None, False, {}
        for d in LOCAL_DIRS:
            for k, fn in SOUND_FILES.items():
                p = os.path.join(d, "sound", fn)
                if k not in self.local and os.path.exists(p):
                    self.local[k] = p
        self.noted = False

    def path(self, key):
        if key in self.local:
            return self.local[key]
        return self.pack.path(key) if self.pack else None

    def poll(self):
        """Once per frame: start the download if needed, and the music when it can play."""
        if not audio.enabled():
            return
        if self.pack is None and len(self.local) < len(SOUND_FILES):
            self.pack = audio.Pack(NAME, ASSET_BASE + "sound/",
                                   {k: v for k, v in SOUND_FILES.items() if k not in self.local},
                                   convert=("music",))
        if not self.music_on:
            p = self.path("music")
            if p:
                audio.music(p)
                self.music_on = True
            elif self.pack and self.pack.state == "failed":
                audio.music(SYNTH_STANDIN["music"])
                self.music_on = True
        if self.pack and self.pack.errors and not self.noted:
            self.noted = True
            game.toast("couldn't fetch bullet_hell sounds; using stand-ins", 4)
            audio.note(f"bullethell: couldn't download {len(self.pack.errors)} sound(s) from {ASSET_BASE} "
                       f"({self.pack.errors[0].split(': ', 1)[-1]}); used synthesized stand-ins")

    def play(self, key, vol=1.0, gap=0.0):
        """One-shot sound; gap (seconds) rate-limits a key so rapid fire can't hog the
        player slots."""
        if not audio.enabled():
            return
        now = time.monotonic()
        if gap and now - self.last.get(key, -9.0) < gap:
            return
        self.last[key] = now
        if key in SOUND_FILES:
            audio.sfx(self.path(key) or SYNTH_STANDIN[key], vol)
        else:
            audio.sfx(key, vol)  # a fun/synth.py recipe


# ------------------------------------------------------------------------------ colour
def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


def clamp01(t):
    return 0.0 if t < 0 else 1.0 if t > 1 else t


def mix(a, b, t):
    return (int(a[0] + (b[0] - a[0]) * t), int(a[1] + (b[1] - a[1]) * t), int(a[2] + (b[2] - a[2]) * t))


def mul(c, k):
    return (min(255, int(c[0] * k)), min(255, int(c[1] * k)), min(255, int(c[2] * k)))


def add(c, d, k=1.0):
    return (min(255, int(c[0] + d[0] * k)), min(255, int(c[1] + d[1] * k)), min(255, int(c[2] + d[2] * k)))


def hexc(s):
    s = s.lstrip("#")
    return int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)


def ease_out(t):
    t = clamp01(t)
    return 1 - (1 - t) ** 3


def back_out(t):
    t = clamp01(t) - 1
    return 1 + 2.70158 * t * t * t + 1.70158 * t * t


WHITE, BLACK = (255, 255, 255), (0, 0, 0)
VOID, VOID_EDGE = (10, 12, 20), (6, 7, 12)
HUD_BG, HUD_LINE = (20, 16, 32), (40, 32, 62)
TEXT, DIM, FAINT, INK = (236, 238, 255), (156, 162, 204), (100, 106, 148), (16, 12, 26)
PANEL, CARD, KEYCAP = (30, 24, 50), (40, 32, 66), (60, 52, 96)
HP_COL, HP_TRAIL, HP_EMPTY = hexc("ED4C67"), hexc("c52f23"), (58, 28, 44)
GOLD, GOLD_LIT, GOLD_DARK = (255, 204, 70), (255, 244, 170), (196, 120, 24)
P_YELLOW, P_RED, P_EYE, P_FILL = hexc("facf52"), hexc("fa5f52"), hexc("fcfffd"), (38, 32, 56)
CYAN, CYAN_LIT, CYAN_DARK = hexc("2ce8f5"), (190, 252, 255), hexc("0095e9")
SHIELD = (120, 200, 255)

# Enemy bullet colours: every type has its own, all warm or violet, so they never read as
# the player's cyan shots or the gold coins.
BULLET_COL = {
    "fly": (255, 45, 122), "stinger": (255, 96, 74), "turret": (178, 107, 255),
    "sniper": (255, 150, 40), "blob": (141, 255, 79), "dasher": (255, 112, 34),
    "brute": (255, 48, 72), "summoner": (233, 77, 255), "boss1": (255, 40, 130),
    "boss2": (196, 146, 255), "boss3": (255, 70, 200), "barrel": (255, 120, 60),
}

BIOMES = [
    {"name": "Neon Crypt", "floor": (hexc("101e2f"), hexc("0c1822")), "cap": hexc("ad1457"),
     "rim": hexc("b55088"), "speck": hexc("880e4f"), "face": (hexc("20384a"), hexc("1a2f3f")),
     "moss": (hexc("204a30"), hexc("1a7a3e"), hexc("056f00")), "accent": (255, 60, 140),
     "decal": (64, 20, 60), "void": (8, 10, 20)},
    {"name": "Verdant Sewer", "floor": ((14, 34, 33), (10, 26, 27)), "cap": (22, 138, 118),
     "rim": (96, 206, 176), "speck": (12, 92, 82), "face": ((40, 46, 72), (32, 37, 60)),
     "moss": ((50, 90, 30), (110, 190, 50), (150, 230, 70)), "accent": (120, 255, 150),
     "decal": (40, 80, 30), "void": (6, 14, 14)},
    {"name": "Ember Foundry", "floor": ((38, 22, 20), (29, 16, 16)), "cap": (186, 88, 30),
     "rim": (240, 158, 72), "speck": (128, 50, 20), "face": ((54, 38, 50), (44, 30, 42)),
     "moss": ((120, 40, 20), (255, 110, 30), (255, 190, 70)), "accent": (255, 150, 60),
     "decal": (90, 34, 14), "void": (16, 8, 8)},
]
# The tilesheet's own colours, remapped per biome so every biome reuses Srijan's wall art.
SHEET_ROLE = {hexc("b55088"): "rim", hexc("ad1457"): "cap", hexc("880e4f"): "speck",
              hexc("68386c"): "speck", hexc("204a30"): "moss0", hexc("1a7a3e"): "moss1",
              hexc("056f00"): "moss2", hexc("204a36"): "moss0", hexc("20384a"): "face0",
              hexc("1a2f3f"): "face1", hexc("081418"): "floor"}


def biome_role(bio, role):
    if role.startswith("moss"):
        return bio["moss"][int(role[4])]
    if role.startswith("face"):
        return bio["face"][int(role[4])]
    if role == "floor":
        return bio["floor"][1]
    return bio[role]


# ------------------------------------------------------------------------------ sprites
# A sprite is rows of rgb-or-None pixels; Sprite flattens it to the opaque pixels relative
# to its anchor (the centre unless given), which is all the blitter needs.

class Sprite:
    __slots__ = ("w", "h", "ox", "oy", "px", "rows")

    def __init__(self, rows, ox=None, oy=None):
        self.rows = rows
        self.h, self.w = len(rows), max((len(r) for r in rows), default=0)
        self.ox = self.w // 2 if ox is None else ox
        self.oy = self.h // 2 if oy is None else oy
        self.px = [(x - self.ox, y - self.oy, c) for y, r in enumerate(rows) for x, c in enumerate(r)
                   if c is not None]


def rows_from(lines, pal):
    return [[pal.get(ch) for ch in line] for line in lines]


def rows_png(img, x0, y0, w, h, keep=128):
    _, _, src = img
    return [[(p[0], p[1], p[2]) if p[3] >= keep else None for p in src[y][x0:x0 + w]]
            for y in range(y0, y0 + h)]


def trim(rows):
    """Crop transparent margins."""
    ys = [y for y, r in enumerate(rows) if any(c is not None for c in r)]
    if not ys:
        return [[None]]
    xs = [x for r in rows for x, c in enumerate(r) if c is not None]
    return [r[min(xs):max(xs) + 1] for r in rows[ys[0]:ys[-1] + 1]]


def flip_rows(rows):
    return [r[::-1] for r in rows]


def map_rows(rows, fn):
    return [[None if c is None else fn(c) for c in r] for r in rows]


def scale_rows(rows, k):
    """Nearest-neighbour rescale by k (any positive factor)."""
    h, w = len(rows), len(rows[0])
    nw, nh = max(1, round(w * k)), max(1, round(h * k))
    return [[rows[min(h - 1, int(y / k))][min(w - 1, int(x / k))] for x in range(nw)] for y in range(nh)]


def shrink_rows(rows):
    """Half size, keeping a pixel wherever any of its 2x2 source pixels is set (so one-pixel
    outlines survive)."""
    h, w = len(rows), len(rows[0])
    out = []
    for y in range(0, h, 2):
        row = []
        for x in range(0, w, 2):
            cs = [rows[yy][xx] for yy in (y, y + 1) for xx in (x, x + 1) if yy < h and xx < w
                  and rows[yy][xx] is not None]
            row.append(max(cs, key=sum) if cs else None)
        out.append(row)
    return out


def rotate_rows(rows, ang):
    """Rotate by ang radians about the centre (nearest neighbour), on a canvas big enough."""
    h, w = len(rows), len(rows[0])
    n = int(math.ceil(math.hypot(w, h))) | 1
    cx, cy, c, s = (w - 1) / 2, (h - 1) / 2, math.cos(ang), math.sin(ang)
    out = []
    for y in range(n):
        row = []
        for x in range(n):
            dx, dy = x - (n - 1) / 2, y - (n - 1) / 2
            sx, sy = c * dx + s * dy + cx, -s * dx + c * dy + cy
            ix, iy = int(round(sx)), int(round(sy))
            row.append(rows[iy][ix] if 0 <= ix < w and 0 <= iy < h else None)
        out.append(row)
    return trim(out) if any(cc is not None for r in out for cc in r) else out


def canvas_rows(w, h):
    return [[None] * w for _ in range(h)]


def put_px(rows, x, y, col):
    if 0 <= y < len(rows) and 0 <= x < len(rows[0]):
        rows[y][x] = col


def fill_ellipse(rows, cx, cy, rx, ry, colfn):
    for y in range(len(rows)):
        for x in range(len(rows[0])):
            u, v = (x - cx) / rx, (y - cy) / ry
            if u * u + v * v <= 1.0:
                rows[y][x] = colfn(u, v)


def draw_line_rows(rows, x0, y0, x1, y1, col):
    n = max(abs(x1 - x0), abs(y1 - y0), 1)
    for i in range(n + 1):
        put_px(rows, round(x0 + (x1 - x0) * i / n), round(y0 + (y1 - y0) * i / n), col)


def ring_outline(rows, col):
    """Paint col on transparent pixels that touch an opaque one (in place, same size)."""
    h, w = len(rows), len(rows[0])
    hits = [(x, y) for y in range(h) for x in range(w) if rows[y][x] is None and any(
        0 <= x + a < w and 0 <= y + b < h and rows[y + b][x + a] is not None
        for a, b in ((-1, 0), (1, 0), (0, -1), (0, 1)))]
    for x, y in hits:
        rows[y][x] = col


# Pixel art for everything the original doesn't have, in its style: white outlines around a
# saturated fill, a dark core, glowing eyes.
OWN_ART = {
    "turret": (["...WWWWW...",
                "..WvvvvvW..",
                ".WvVVVVVvW.",
                "WvVWWWWWVvW",
                "WvVWkkkWVvW",
                "WvVWkkkWVvW",
                "WvVWkkkWVvW",
                "WvVWWWWWVvW",
                ".WvVVVVVvW.",
                "..WvvvvvW..",
                ".WWWWWWWWW.",
                "WsssssssssW",
                ".WWWWWWWWW."],
               {"W": (236, 228, 255), "v": (74, 40, 120), "V": (150, 96, 224), "k": (20, 12, 34),
                "s": (96, 80, 130)}),
    "sniper": (["....W....",
                "...WaW...",
                "..WaAaW..",
                ".WaAAAaW.",
                "WaAAkAAaW",
                ".WaAAAaW.",
                "..WaAaW..",
                "...WaW...",
                "....W....",
                "...a.a...",
                "..a...a.."],
               {"W": (255, 240, 210), "a": (150, 84, 18), "A": (250, 168, 50), "k": (40, 16, 6)}),
    "blob": (["....WWW....",
              "..WWgggWW..",
              ".WgGGGGGgW.",
              "WgGEkGEkGgW",
              "WgGEEGEEGgW",
              "WgGGGGGGGgW",
              "WgGGmmmGGgW",
              ".WggggggggW",
              "..WWWWWWWW."],
             {"W": (230, 255, 210), "g": (44, 120, 40), "G": (140, 230, 80), "E": (250, 255, 240),
              "k": (18, 40, 14), "m": (30, 70, 24)}),
    "blobling": (["..WWW..",
                  ".WGGGW.",
                  "WGEGEGW",
                  "WGGGGGW",
                  ".WWWWW."],
                 {"W": (230, 255, 210), "G": (140, 230, 80), "E": (18, 40, 14)}),
    "dasher": (["W.........W",
                ".W.......W.",
                "..WWWWWWW..",
                ".WoOOOOOoW.",
                "WoOEkOEkOoW",
                "WoOOOOOOOoW",
                "WooOOOOOooW",
                ".WWWWWWWWW.",
                "..W.W.W.W.."],
               {"W": (255, 236, 210), "o": (150, 56, 16), "O": (255, 128, 48), "E": (255, 250, 230),
                "k": (60, 20, 6)}),
    "brute": (["...WWWWW...",
               "..WrrrrrW..",
               ".WrRRRRRrW.",
               ".WrWWWWWrW.",
               ".WrWEkEWrW.",
               ".WrWWWWWrW.",
               "WWrRRRRRrWW",
               "WrRRRRRRRrW",
               "WrRRWWWRRrW",
               "WrRRRRRRRrW",
               ".WWWWWWWWW.",
               "..WW...WW.."],
              {"W": (255, 226, 230), "r": (120, 18, 40), "R": (226, 48, 74), "E": (255, 220, 90),
               "k": (60, 8, 20)}),
    "summoner": (["....WWW....",
                  "..WWmmmWW..",
                  ".WmMMMMMmW.",
                  ".WMkMMMkMW.",
                  "WmMMMMMMMmW",
                  "WmMkMEMkMmW",
                  "WmMMMMMMMmW",
                  ".WMkMMMkMW.",
                  ".WmMMMMMmW.",
                  "..WWmmmWW..",
                  "....WWW...."],
                 {"W": (255, 220, 255), "m": (110, 30, 124), "M": (216, 80, 230), "k": (30, 6, 36),
                  "E": (255, 250, 255)}),
    "gnat": (["W.m.W",
              ".mMm.",
              "..m.."],
             {"W": (255, 220, 255), "m": (150, 40, 160), "M": (240, 120, 250)}),
    "heart": ([".RR.RR.",
               "RLRRRRR",
               "RRRRRRR",
               ".RRRRR.",
               "..RRR..",
               "...R..."],
              {"R": (255, 70, 100), "L": (255, 200, 210)}),
    "chest": ([".WWWWWWWWW.",
               "WbBBBGBBBbW",
               "WbBBGgGBBbW",
               "WWWWWGWWWWW",
               "WbBBBBBBBbW",
               "WbBBBBBBBbW",
               ".WWWWWWWWW."],
              {"W": (255, 236, 190), "b": (120, 64, 30), "B": (186, 108, 46), "G": GOLD, "g": GOLD_LIT}),
    "pedestal": (["WWWWWWWWWWW",
                  "WsSSSSSSSsW",
                  ".WWWWWWWWW."],
                 {"W": (190, 186, 220), "s": (70, 64, 100), "S": (110, 104, 150)}),
}
# Weapon pickups and HUD icons, 8x5.
WEAPON_ART = {
    "pistol": ["WWWWWWW.", "WkCCCCW.", "WWWWWWW.", "WkW.....", "WWW....."],
    "shotgun": ["WWWWWWWW", "WkkkkkkW", "WWWWWWWW", ".WkW....", ".WWW...."],
    "burst": ["WWWWWWWW", "WkCkCkCW", "WWWWWWWW", "WkWWkW..", "WWW.WW.."],
    "laser": ["..WWWWWW", "WWCCCCCW", "WkWWWWWW", "WkW.....", "WWW....."],
    "orbs": [".WWWWW..", "WkCCCkW.", "WCCWCCWW", "WkCCCkW.", ".WWWWW.."],
    "bouncer": ["WWWWWW.W", "WkCkCWW.", "WWWWWW.W", "WkW.....", "WWW....."],
}
WEAPON_PAL = {"W": (232, 236, 250), "k": (60, 64, 84), "C": (102, 255, 227)}


def player_frames():
    """The hero, a compact remix of Srijan's square-headed robot: (idle x2, run x4) facing
    right. Fill is dark so the outline reads over bullets."""
    head = [".YYYYYY.",
            "YkkkkkkY",
            "YkEEkkEY",
            "YkEEkkEY",
            "YkkkkkkY",
            ".YYYYYY."]
    body = [".YkkkkY.", ".YYYYYY."]
    legs = {"stand": ".Y....Y.", "a": "Y.....Y.", "b": "..Y..Y..", "c": ".Y...Y.."}
    pal = {"Y": P_YELLOW, "k": P_FILL, "E": P_EYE}
    out = {}
    out["idle"] = [rows_from(["........"] + head + body + [legs["stand"]], pal),
                   rows_from(["........"] + head[:5] + [".YYYYYY.", ".YYYYYY."] + [legs["stand"]], pal)]
    out["run"] = [rows_from(["........"] + head + body + [legs[k]], pal) for k in ("a", "c", "b", "c")]
    out["run"][1] = rows_from(head + body + [legs["c"], "........"], pal)  # bounces up a pixel
    out["blink"] = rows_from(["........"] + [head[0], head[1], "YkkkkkkY", "YkYYkkYY", head[4], head[5]]
                             + body + [legs["stand"]], pal)
    return out


def fallback_fly():
    pal = {"W": (255, 255, 255), "p": (213, 29, 94), "P": (227, 52, 114), "k": (90, 10, 40)}
    up = ["W.................W",
          ".W......ppp......W.",
          "..WW...pPPPp...WW..",
          "....WWpPkPkPpWW....",
          "......pPPPPPp......",
          "......pPkPkPp......",
          ".......pPPPp.......",
          "........ppp........"]
    mid = ["...................",
           ".......ppp.........",
           "......pPPPp........",
           "WWWWWWpPkPkPpWWWWWW",
           "......pPPPPPp......",
           "......pPkPkPp......",
           ".......pPPPp.......",
           "........ppp........"]
    down = list(mid)
    down[3] = "....WWpPkPkPpWW...."
    down[4] = "..WW..pPPPPPp..WW.."
    down[5] = "W.....pPkPkPp.....W"
    return [rows_from(f, pal) for f in (up, mid, down)]


def fallback_stinger():
    return rows_from(["R.......",
                      "RRR.....",
                      ".RWWR...",
                      "..RWWWWR",
                      ".RWWR...",
                      "RRR.....",
                      "R......."], {"R": P_RED, "W": WHITE})


def orb_rows(d, core, mid, rim):
    rows = canvas_rows(d, d)
    r = d / 2
    fill_ellipse(rows, r - 0.5, r - 0.5, r, r, lambda u, v: core if u * u + v * v < 0.3 else
                 mid if u * u + v * v < 0.7 else rim)
    return rows


def door_rows():
    rows = canvas_rows(16, 14)
    for x in range(4, 12):
        rows[0][x] = WHITE
    for y in range(1, 13):
        rows[y][2 if y > 2 else 3] = WHITE
        rows[y][13 if y > 2 else 12] = WHITE
    for x in range(1, 15):
        rows[12][x] = WHITE
    return rows


def boss1_frames():
    """The Brood Mother: a crowned fly queen, four wing poses."""
    frames = []
    body_hi, body_lo, stripe = (255, 96, 156), (166, 18, 78), (120, 8, 52)
    for k in range(4):
        rows = canvas_rows(35, 23)
        flap = (-0.9, -0.35, 0.25, -0.35)[k]
        for side in (-1, 1):  # wings: two white strokes per side, like the small fly's
            for j, (ln, off) in enumerate(((15, 0.0), (11, 0.42))):
                a = flap + off
                x0, y0 = 17 + side * 5, 9
                x1, y1 = x0 + side * math.cos(a) * ln, y0 + math.sin(a) * ln * 0.8
                draw_line_rows(rows, x0, y0, round(x1), round(y1), (255, 255, 255))
                mx, my = (x0 + x1) / 2, (y0 + y1) / 2
                for t in range(3):  # a speckled membrane between the strokes
                    put_px(rows, round(mx + side * (t - 1) * 2), round(my + 2 + j), (255, 190, 220))
        fill_ellipse(rows, 17, 12, 7.5, 7, lambda u, v: stripe if (int((v + 1) * 5) % 3 == 2 and v > 0)
                     else mix(body_hi, body_lo, clamp01((v + 1) / 2 + u * 0.15)))
        fill_ellipse(rows, 17, 6, 4.5, 3.2, lambda u, v: mix((255, 130, 180), body_lo, clamp01((v + 1) / 2)))
        for ex in (14, 19):  # big eyes
            for dx in range(2):
                for dy in range(2):
                    put_px(rows, ex + dx, 5 + dy, WHITE)
            put_px(rows, ex + (1 if ex > 17 else 0), 6, (60, 0, 30))
        for x, h in ((14, 2), (17, 3), (20, 2)):  # crown
            for y in range(h):
                put_px(rows, x, 2 - y, GOLD if y < h - 1 else GOLD_LIT)
        put_px(rows, 15, 2, GOLD)
        put_px(rows, 16, 2, GOLD)
        put_px(rows, 18, 2, GOLD)
        put_px(rows, 19, 2, GOLD)
        for lx in (13, 16, 18, 21):  # legs
            put_px(rows, lx, 19, (255, 220, 235))
            put_px(rows, lx + (1 if lx > 17 else -1), 20, (255, 220, 235))
        ring_outline(rows, (255, 240, 248))
        frames.append(rows)
    return frames


def boss2_rows():
    """The Warden: a floating stone obelisk with one great eye (the eye is drawn live)."""
    w, h = 23, 29
    rows = canvas_rows(w, h)
    stone, lit, dark = (66, 96, 110), (128, 168, 176), (36, 54, 66)
    for y in range(2, 24):
        half = 9 if y > 4 else 5 + y
        for x in range(11 - half, 12 + half):
            u = (x - 11) / 9
            col = lit if y < 5 or u < -0.75 else dark if u > 0.7 else stone
            if (x * 3 + y * 7) % 11 == 0:
                col = mul(col, 0.85)
            rows[y][x] = col
    for y in range(24, 27):  # a floating keel
        for x in range(8 + (y - 24), 15 - (y - 24)):
            rows[y][x] = (70, 110, 120)
    rune = (196, 146, 255)
    for x, y in ((5, 17), (5, 18), (6, 19), (17, 17), (17, 18), (16, 19), (9, 21), (10, 21), (12, 21),
                 (13, 21), (11, 3), (11, 4)):
        rows[y][x] = rune
    for y in range(7, 14):  # eye socket
        for x in range(5, 18):
            u, v = (x - 11) / 6.5, (y - 10) / 3.6
            if u * u + v * v <= 1:
                rows[y][x] = (20, 26, 34)
    ring_outline(rows, (214, 250, 244))
    return rows


def boss3_rows():
    """Mad Carbon: a faceted carbon crystal around a live core (drawn at runtime)."""
    n = 27
    rows = canvas_rows(n, n)
    c = (n - 1) / 2
    for y in range(n):
        for x in range(n):
            dx, dy = x - c, y - c
            if abs(dx) + abs(dy) * 0.85 <= 13 and abs(dx) <= 10 and abs(dy) <= 12.5:
                facet = (math.floor((math.atan2(dy, dx) + math.pi) / (math.pi / 4))) % 8
                base = ((44, 40, 58), (62, 56, 82), (34, 30, 46), (78, 70, 104), (40, 36, 52),
                        (56, 50, 74), (30, 28, 40), (70, 62, 96))[facet]
                if abs(dx) + abs(dy) > 10:
                    base = mul(base, 1.25)
                rows[y][x] = base
    crack = (255, 70, 200)
    for pts in (((13, 4), (12, 7), (13, 9)), ((5, 12), (8, 13), (9, 12)), ((20, 15), (17, 14), (16, 15)),
                ((13, 22), (14, 19), (13, 17))):
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            draw_line_rows(rows, x0, y0, x1, y1, crack)
    ring_outline(rows, (240, 226, 255))
    return rows


def build_sprites(art):
    """Every sprite as base rows, from Srijan's PNGs where they exist, else stand-ins."""
    img = art.img
    S = {}
    pf = player_frames()
    S["player_idle"], S["player_run"], S["player_blink"] = pf["idle"], pf["run"], [pf["blink"]]
    if "player_yellow" in img:  # the title screen shows the original hero at full size
        S["hero"] = [rows_png(img["player_yellow"], 12 * i, 0, 12, 18) for i in range(12)]
    else:
        S["hero"] = [scale_rows(f, 2) for f in pf["idle"]] * 5 + [scale_rows(f, 2) for f in pf["run"]][:2]
    if "fly" in img:
        fly = [trim(rows_png(img["fly"], 19 * i, 0, 19, 13)) for i in range(5)]
        S["fly"], S["fly_hurt"] = fly[:3], [fly[3]]
    else:
        S["fly"] = fallback_fly()
        S["fly_hurt"] = [map_rows(S["fly"][1], lambda c: WHITE)]
    S["stinger"] = [trim(rows_png(img["stinger"], 0, 0, 8, 7))] if "stinger" in img else [fallback_stinger()]
    if "fly_corpse" in img:
        S["fly_corpse"] = [trim(rows_png(img["fly_corpse"], 0, 0, 14, 13))]
    else:
        S["fly_corpse"] = [map_rows(S["fly"][1], lambda c: mul(c, 0.45))]
    if "stinger_corpse" in img:
        S["stinger_corpse"] = [trim(rows_png(img["stinger_corpse"], 0, 0, 8, 7))]
    else:
        S["stinger_corpse"] = [map_rows(S["stinger"][0], lambda c: mul(c, 0.45))]
    S["ball"] = [rows_png(img["ball"], 0, 0, 12, 12)] if "ball" in img else [
        orb_rows(12, WHITE, (255, 0, 90), (168, 50, 92))]
    S["ball_small"] = [shrink_rows(S["ball"][0])]
    S["door"] = [rows_png(img["door"], 0, 0, 16, 14)] if "door" in img else [door_rows()]
    if "explosive_barrel" in img:
        S["barrel"] = [trim(rows_png(img["explosive_barrel"], 0, 0, 16, 16))]
    else:
        S["barrel"] = [orb_rows(11, (255, 255, 255), (250, 95, 82), (120, 30, 30))]
    S["barrel"] = [scale_rows(S["barrel"][0], 0.6)] if len(S["barrel"][0]) > 12 else S["barrel"]
    if "explosion_red" in img:
        S["explosion"] = [rows_png(img["explosion_red"], 25 * i, 0, 25, 25) for i in range(14)]
    else:
        S["explosion"] = []
        for i in range(14):
            rows = canvas_rows(25, 25)
            r = 3 + i * 0.75
            fill_ellipse(rows, 12, 12, r, r, lambda u, v, i=i: (WHITE if i < 4 or u * u + v * v > 0.8
                                                                 else hexc("ff0044")) if
                         (i < 9 or u * u + v * v > 0.75) else None)
            S["explosion"].append(rows)
    S["cursor"] = [rows_png(img["cursor"], 0, 0, 9, 9)] if "cursor" in img else [rows_from(
        ["WWW...WWW", "W.......W", "W.......W", ".........", "....W....", ".........", "W.......W",
         "W.......W", "WWW...WWW"], {"W": WHITE})]
    S["handgun"] = [rows_png(img["handgun"], 0, 0, 8, 8)] if "handgun" in img else [
        rows_from(WEAPON_ART["pistol"], WEAPON_PAL)]
    for name, (lines, pal) in OWN_ART.items():
        S[name] = [rows_from(lines, pal)]
    for name, lines in WEAPON_ART.items():
        S["w_" + name] = [rows_from(lines, WEAPON_PAL)]
    S["boss1"] = boss1_frames()
    S["boss2"] = [boss2_rows()]
    S["boss3"] = [boss3_rows()]
    S["coin"] = [rows_from(f, {"G": GOLD, "L": GOLD_LIT, "D": GOLD_DARK}) for f in
                 ([".LG.", "LGGD", "GGGD", ".GD."], [".L.", "LGD", "GGD", ".D."], [".L", "GD", "GD", "D."],
                  [".L.", "LGD", "GGD", ".D."])]
    return S


class SpriteBank:
    """Sprites by (name, frame, flip, mode); mode None, "white" (hit flash), "dark"
    (corpses and shadows) or "hurt" (player red). Built lazily and kept."""

    def __init__(self, art):
        self.art, self.version, self.cache = art, -1, {}
        self.refresh()

    def refresh(self):
        if self.version != self.art.version:
            self.version = self.art.version
            self.base = build_sprites(self.art)
            self.cache = {}

    def frames(self, name):
        return len(self.base[name])

    def get(self, name, frame=0, flip=False, mode=None, rot=None):
        key = (name, frame, flip, mode, rot)
        spr = self.cache.get(key)
        if spr is None:
            fr = self.base[name]
            rows = fr[frame % len(fr)]
            if rot is not None and rot % 4 == 0:  # quarter turns are exact
                for _ in range(rot // 4):
                    rows = [list(r) for r in zip(*rows[::-1])]
            elif rot is not None:
                rows = rotate_rows(rows, rot * math.pi / 8)
            if flip:
                rows = flip_rows(rows)
            if mode == "white":
                rows = map_rows(rows, lambda c: WHITE)
            elif mode == "hurt":
                rows = map_rows(rows, lambda c: P_RED if c == P_YELLOW else c)
            elif mode == "dark":
                rows = map_rows(rows, lambda c: mul(c, 0.42))
            elif mode == "ghost":
                rows = map_rows(rows, lambda c: mix(c, CYAN, 0.6))
            elif mode == "lit":
                rows = map_rows(rows, lambda c: mix(c, WHITE, 0.4))
            spr = self.cache[key] = Sprite(rows)
        return spr


# ------------------------------------------------------------------------------ dungeon
# Units are pixels: one half-block, so a terminal cell is 1x2 of them and they look square.
# A floor is a few rooms on a grid joined by doors (a random walk from the start room, like
# the original's level generator). Every room has the same box for the whole run, sized to
# the terminal when the run starts, so it fits on screen without scrolling.

T = 8          # interior tile size
BX = 4         # side wall thickness
TOP, BOT = 8, 4  # top wall (cap plus brick face) and bottom wall thickness
DIRS4 = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}
OPP = {"up": "down", "down": "up", "left": "right", "right": "left"}
FLOORS = 9      # three biomes of three floors; the third floor of each has the boss
BOSS_KIND = ("boss1", "boss2", "boss3")
BOSS_NAME = {"boss1": "THE BROOD MOTHER", "boss2": "THE WARDEN", "boss3": "MAD CARBON"}


def sub_rng(seed, *tag):
    # sha256, not hash(): str hashing is salted per process, which would break shared seeds.
    h = hashlib.sha256(":".join(["bullethell", str(seed)] + [str(t) for t in tag]).encode()).digest()
    return random.Random(int.from_bytes(h[:8], "big"))


class Geo:
    """The room box: iw x ih interior tiles inside walls, with a door gap mid-side."""

    def __init__(self, iw, ih):
        self.iw, self.ih = iw, ih
        self.W, self.H = iw * T + 2 * BX, ih * T + TOP + BOT
        self.x0, self.y0, self.x1, self.y1 = BX, TOP, BX + iw * T, TOP + ih * T
        tx, ty = iw // 2 - 1, ih // 2 - 1
        self.door_t = {"up": [(tx, 0), (tx + 1, 0)], "down": [(tx, ih - 1), (tx + 1, ih - 1)],
                       "left": [(0, ty), (0, ty + 1)], "right": [(iw - 1, ty), (iw - 1, ty + 1)]}
        dx, dy = BX + tx * T, TOP + ty * T
        self.door = {"up": (dx, 0, dx + 2 * T, TOP), "down": (dx, self.y1, dx + 2 * T, self.H),
                     "left": (0, dy, BX, dy + 2 * T), "right": (self.x1, dy, self.W, dy + 2 * T)}

    def tile_px(self, tx, ty):
        """Centre pixel of an interior tile."""
        return BX + tx * T + T / 2, TOP + ty * T + T / 2

    def entry(self, d):
        """Where the player stands after coming in through door d."""
        x0, y0, x1, y1 = self.door[d]
        if d == "up":
            return (x0 + x1) / 2, TOP + 6
        if d == "down":
            return (x0 + x1) / 2, self.y1 - 5
        if d == "left":
            return BX + 5, (y0 + y1) / 2
        return self.x1 - 5, (y0 + y1) / 2


class Room:
    def __init__(self, gx, gy):
        self.gx, self.gy = gx, gy
        self.kind = "combat"
        self.doors = {}          # dir -> neighbour (gx, gy)
        self.pillars = set()     # interior tiles that are solid
        self.barrels = []        # [x, y, hp]
        self.pickups = []
        self.decals = []         # (sprite name, frame, flip, x, y) baked into the floor
        self.visited = self.cleared = self.locked = False
        self.waves, self.wave_i = None, 0
        self.layout = "empty"
        self.bg = None           # render cache, rebuilt when the room changes look


PILLAR_LAYOUTS = ("empty", "pillars4", "center", "bars", "scatter", "corners", "cross", "posts")


def layout_pillars(rng, iw, ih, name):
    """A symmetric set of solid interior tiles for the named layout."""
    p = set()
    cx, cy = iw // 2, ih // 2
    if name == "pillars4":
        a, b = max(2, iw // 4), max(1, ih // 4)
        for x in (a, iw - 1 - a):
            for y in (b, ih - 1 - b):
                p.add((x, y))
    elif name == "center":
        for x in range(cx - 1, cx + 1):
            for y in range(cy - 1, cy + 1 if ih > 6 else cy):
                p.add((x, y))
    elif name == "bars":
        x = max(2, iw // 3)
        for y in range(2, ih - 2):
            p.add((x, y))
            p.add((iw - 1 - x, y))
    elif name == "scatter":
        for _ in range(rng.randint(2, 3)):
            x, y = rng.randint(2, cx - 2), rng.randint(1, ih - 2)
            p.add((x, y))
            p.add((iw - 1 - x, y))
    elif name == "corners":
        for x, y in ((1, 1), (2, 1), (1, 2)):
            for fx in (False, True):
                for fy in (False, True):
                    p.add((iw - 1 - x if fx else x, ih - 1 - y if fy else y))
    elif name == "cross":
        for d in range(-1, 2):
            p.add((cx + d - (1 if d < 0 else 0), cy))
        p.add((cx - 1, cy - 1))
        p.add((cx, cy - 1))
    elif name == "posts":
        for x in range(2, iw - 2, 3):
            p.add((x, 2 if (x // 3) % 2 else ih - 3))
    return p


def reachable(iw, ih, solid, start):
    seen, todo = {start}, [start]
    while todo:
        x, y = todo.pop()
        for dx, dy in DIRS4.values():
            q = (x + dx, y + dy)
            if 0 <= q[0] < iw and 0 <= q[1] < ih and q not in solid and q not in seen:
                seen.add(q)
                todo.append(q)
    return seen


def place_pillars(room, geo, rng, name):
    """Use the layout if it keeps every door reachable and its approach clear; else empty."""
    iw, ih = geo.iw, geo.ih
    p = layout_pillars(rng, iw, ih, name)
    keep = set()
    for d in DIRS4:
        for tx, ty in geo.door_t[d]:
            for k in range(3):
                ddx, ddy = DIRS4[OPP[d]]
                keep.add((tx + ddx * k, ty + ddy * k))
    p -= keep
    if p:
        start = geo.door_t["up"][0]
        free = reachable(iw, ih, p, start)
        if any(t not in free for d in DIRS4 for t in geo.door_t[d]) or len(free) < iw * ih - len(p):
            p, name = set(), "empty"
    room.pillars, room.layout = p, name if p else "empty"


def gen_floor(seed, fi, geo):
    """{(gx, gy): Room} for floor fi (0-based), plus the start position."""
    rng = sub_rng(seed, "floor", fi)
    biome, sub = divmod(fi, 3)
    n = 5 + sub + (1 if biome else 0) + (1 if biome == 2 else 0)
    cells, edges = [(0, 0)], set()
    tries = 0
    while len(cells) < n and tries < 500:
        tries += 1
        base = rng.choice(cells[-2:]) if rng.random() < 0.55 else rng.choice(cells)
        d = rng.choice(list(DIRS4))
        q = (base[0] + DIRS4[d][0], base[1] + DIRS4[d][1])
        if q in cells:
            continue
        # Keep it branchy rather than a blob: few cells may touch three others.
        if sum((q[0] + dx, q[1] + dy) in cells for dx, dy in DIRS4.values()) > 1 and rng.random() < 0.7:
            continue
        cells.append(q)
        edges.add(frozenset((base, q)))
    rooms = {c: Room(*c) for c in cells}
    for c in cells:  # a few loops between neighbours
        for d, (dx, dy) in DIRS4.items():
            q = (c[0] + dx, c[1] + dy)
            if q in rooms and frozenset((c, q)) not in edges and rng.random() < 0.18:
                edges.add(frozenset((c, q)))
    for e in edges:
        a, b = tuple(e)
        for d, (dx, dy) in DIRS4.items():
            if (a[0] + dx, a[1] + dy) == b:
                rooms[a].doors[d] = b
                rooms[b].doors[OPP[d]] = a
    dist, todo = {(0, 0): 0}, [(0, 0)]
    while todo:
        c = todo.pop(0)
        for q in rooms[c].doors.values():
            if q not in dist:
                dist[q] = dist[c] + 1
                todo.append(q)
    order = sorted(cells, key=lambda c: (-dist[c], c))
    leaves = [c for c in order if len(rooms[c].doors) == 1 and c != (0, 0)]
    rooms[(0, 0)].kind = "start"
    last = (leaves or order)[0]
    rooms[last].kind = "boss" if sub == 2 else "exit"
    rest = [c for c in (leaves[1:] + [c for c in order if c not in leaves]) if rooms[c].kind == "combat"]
    if rest:
        rooms[rest.pop(0)].kind = "treasure"
    if rest and fi > 0 and (sub == 1 or rng.random() < 0.5):
        rooms[rest.pop(0)].kind = "shop"
    for c in cells:
        r = rooms[c]
        lay = "empty"
        if r.kind in ("combat", "exit"):
            lay = rng.choice(PILLAR_LAYOUTS[1:] if fi or dist[c] > 1 else ("empty", "pillars4"))
        place_pillars(r, geo, rng, lay)
        if r.kind in ("combat", "exit") and rng.random() < 0.5 + 0.1 * biome:
            doors = [t for d in DIRS4 for t in geo.door_t[d]]
            free = [(x, y) for x in range(1, geo.iw - 1) for y in range(1, geo.ih - 1)
                    if abs(x - geo.iw / 2) > 2
                    and not any(abs(x - px) + abs(y - py) <= 1 for px, py in r.pillars)
                    and not any(abs(x - dx) + abs(y - dy) <= 3 for dx, dy in doors)]
            for _ in range(rng.randint(1, 2)):
                if free:
                    tx, ty = free.pop(rng.randrange(len(free)))
                    x, y = geo.tile_px(tx, ty)
                    r.barrels.append([x, y, 6])
    return rooms


# Wave recipes: enemy kinds per biome with their cost against a wave budget.
COST = {"fly": 2, "stinger": 2, "turret": 3, "sniper": 3, "blob": 3, "dasher": 3, "brute": 4,
        "summoner": 4}
POOLS = (
    (("fly", 5), ("stinger", 4), ("turret", 2)),
    (("blob", 4), ("sniper", 3), ("dasher", 3), ("fly", 2), ("turret", 2), ("stinger", 1)),
    (("brute", 4), ("summoner", 3), ("dasher", 3), ("sniper", 2), ("stinger", 2), ("turret", 2),
     ("blob", 1)),
)


def make_waves(seed, fi, room, diff, first_fight):
    """Kinds to spawn per wave, fixed per room and seed."""
    rng = sub_rng(seed, "waves", fi, room.gx, room.gy)
    biome, sub = divmod(fi, 3)
    if first_fight:
        return [["fly", "fly"], ["stinger", "fly"]]
    n = 1 + (rng.random() < 0.6 + 0.15 * fi) + (fi >= 3 and rng.random() < 0.35 + 0.05 * fi)
    if room.kind == "exit":
        n += 1
    waves = []
    pool = POOLS[biome]
    if fi == 0:
        pool = (("fly", 5), ("stinger", 4), ("turret", 1))
    for w in range(n):
        budget = (4 + fi * 0.85 + w * 1.2 + rng.random() * 2) * diff["count"]
        kinds, turrets = [], 0
        while budget >= 2 and len(kinds) < 8:
            opts = [(k, wt) for k, wt in pool if COST[k] <= budget + 0.5 and not (k == "turret" and turrets >= 2)]
            if not opts:
                break
            r = rng.random() * sum(wt for _, wt in opts)
            for k, wt in opts:
                r -= wt
                if r <= 0:
                    break
            kinds.append(k)
            turrets += k == "turret"
            budget -= COST[k]
        waves.append(kinds or ["fly"])
    return waves


# ------------------------------------------------------------------------------ rules
DIFFS = {
    "easy": {"hp": 14, "bspeed": 0.82, "fire": 1.3, "ehp": 0.8, "count": 0.8, "boss": 0.8, "score": 0.6,
             "blurb": "more health, slower bullets"},
    "normal": {"hp": 10, "bspeed": 1.0, "fire": 1.0, "ehp": 1.0, "count": 1.0, "boss": 1.0, "score": 1.0,
               "blurb": "the intended run"},
    "hard": {"hp": 8, "bspeed": 1.12, "fire": 0.85, "ehp": 1.2, "count": 1.2, "boss": 1.2, "score": 1.5,
             "blurb": "faster bullets, tougher rooms"},
}
DIFF_ORDER = ("easy", "normal", "hard")

# cd: seconds between shots; spd px/s; life s; n shots per pull over spread radians.
WEAPONS = {
    "pistol": {"name": "pistol", "cd": 0.17, "dmg": 3.0, "spd": 150, "life": 1.2, "n": 1, "spread": 0.03,
               "st": "pb", "r": 1.6, "knock": 30},
    "shotgun": {"name": "shotgun", "cd": 0.58, "dmg": 2.3, "spd": 135, "life": 0.42, "n": 6, "spread": 0.5,
                "st": "pellet", "r": 1.4, "knock": 60},
    "burst": {"name": "burst rifle", "cd": 0.5, "dmg": 3.2, "spd": 175, "life": 1.1, "n": 1, "spread": 0.04,
              "st": "pb", "r": 1.6, "knock": 25, "burst": 3, "gap": 0.06},
    "laser": {"name": "laser", "cd": 0.0, "dmg": 18.0, "beam": True, "st": "beam", "r": 1.6, "knock": 6},
    "orbs": {"name": "seeker orbs", "cd": 0.32, "dmg": 4.0, "spd": 88, "life": 2.2, "n": 1, "spread": 0.1,
             "st": "porb", "r": 2.2, "knock": 20, "home": 5.0},
    "bouncer": {"name": "bouncer", "cd": 0.24, "dmg": 2.7, "spd": 125, "life": 2.0, "n": 1, "spread": 0.05,
                "st": "pbounce", "r": 1.6, "knock": 20, "bounce": 3},
}
WEAPON_ORDER = ("pistol", "shotgun", "burst", "laser", "orbs", "bouncer")

# key: (name, description, glyph, colour, max level)
UPGRADES = {
    "rapid": ("Rapid Fire", "fire 20% faster", "»", (255, 210, 90), 5),
    "heavy": ("Heavy Rounds", "+25% damage", "♦", (255, 110, 90), 5),
    "pierce": ("Piercing", "shots pass through +1 enemy", "→", (140, 220, 255), 3),
    "ricochet": ("Ricochet", "shots bounce off walls +1", "↺", (120, 255, 200), 3),
    "big": ("Big Shots", "bigger shots, +10% damage", "●", (200, 160, 255), 3),
    "split": ("Split Shot", "+2 side shots at half damage", "≡", (255, 160, 220), 2),
    "dash": ("Extra Dash", "+1 dash charge", "⇉", (90, 230, 255), 2),
    "shield": ("Aegis", "a shield soaks one hit; recharges in 12 s", "◈", SHIELD, 3),
    "vamp": ("Vampire Fang", "heal 1 every 12 kills", "♥", (255, 70, 110), 3),
    "blades": ("Orbit Blades", "+2 blades circle you, cutting foes and bullets", "✦", (255, 240, 160), 2),
    "vital": ("Vitality", "+4 max health, heal to full", "✚", (120, 255, 140), 3),
    "boots": ("Swift Boots", "move 12% faster, dash recharges sooner", "⇢", (180, 255, 120), 3),
    "midas": ("Midas Touch", "+50% coins and a wider magnet", "◎", GOLD, 2),
    "phase": ("Phase Dash", "dashing erases nearby bullets", "○", (170, 200, 255), 1),
    "crit": ("Crit Lens", "+15% chance of 2.5x damage", "✧", (255, 255, 140), 3),
    "homing": ("Seeker Rounds", "shots curve toward enemies", "⊕", (255, 150, 255), 2),
}
RARE = {"blades": 0.6, "split": 0.7, "phase": 0.7, "vamp": 0.8, "shield": 0.8, "homing": 0.8}

ENEMY = {  # hp, hit radius, sprite, coins dropped (min, max)
    "fly": (10, 4.5, (1, 2)), "stinger": (8, 3.5, (1, 2)), "turret": (20, 5.0, (2, 3)),
    "sniper": (11, 4.0, (2, 3)), "blob": (18, 5.0, (1, 3)), "blobling": (5, 3.0, (0, 1)),
    "dasher": (16, 5.0, (2, 3)), "brute": (30, 5.5, (3, 4)), "summoner": (22, 5.0, (3, 4)),
    "gnat": (3, 2.0, (0, 0)), "boss1": (850, 9.0, (0, 0)), "boss2": (1350, 9.5, (0, 0)),
    "boss3": (1900, 10.0, (0, 0)),
}
CORPSE = {"fly": "fly_corpse", "stinger": "stinger_corpse"}

PLAYER_SPEED = 44.0
DASH_SPEED, DASH_TIME, DASH_CD = 175.0, 0.17, 0.85
HIT_R = 1.6          # the player's bullet hitbox radius, much smaller than the sprite
INVULN = 1.0
MAX_EBULLETS = 420


class Bullet:
    __slots__ = ("x", "y", "vx", "vy", "st", "r", "dmg", "t", "life", "acc", "turn", "bounce", "pierce",
                 "home", "hits", "delay", "crit", "kind", "dead")

    def __init__(self, x, y, vx, vy, st, r, dmg, life):
        self.x, self.y, self.vx, self.vy, self.st, self.r, self.dmg = x, y, vx, vy, st, r, dmg
        self.t, self.life, self.acc, self.turn, self.bounce, self.pierce = 0.0, life, 0.0, 0.0, 0, 0
        self.home, self.hits, self.delay, self.crit, self.kind, self.dead = 0.0, None, 0.0, False, "", False


class Enemy:
    __slots__ = ("kind", "x", "y", "vx", "vy", "hp", "maxhp", "r", "t", "cd", "state", "st", "face",
                 "flash", "spawn", "kx", "ky", "data", "brain", "dead", "ang", "inv", "boss")

    def __init__(self, kind, x, y, hp_mult=1.0):
        hp, r, _ = ENEMY[kind]
        self.kind, self.x, self.y, self.vx, self.vy = kind, x, y, 0.0, 0.0
        self.hp = self.maxhp = hp * hp_mult
        self.r, self.t, self.cd, self.state, self.st = r, 0.0, 1.0, "idle", 0.0
        self.face, self.flash, self.spawn, self.kx, self.ky = 1, 0.0, 0.0, 0.0, 0.0
        self.data, self.brain, self.dead, self.ang, self.inv = {}, None, False, 0.0, 0.0
        self.boss = kind.startswith("boss")


class Pickup:
    __slots__ = ("kind", "x", "y", "vx", "vy", "t", "val", "price", "dead")

    def __init__(self, kind, x, y, val=None, price=0):
        self.kind, self.x, self.y, self.vx, self.vy = kind, x, y, 0.0, 0.0
        self.t, self.val, self.price, self.dead = 0.0, val, price, False


class Player:
    def __init__(self, x, y, hp):
        self.x, self.y, self.vx, self.vy = x, y, 0.0, 0.0
        self.hp = self.maxhp = hp
        self.hp_shown = float(hp)   # the health bar's trailing segment eases toward hp
        self.aim, self.face, self.moving, self.anim = 0.0, 1, False, 0.0
        self.inv, self.hurt_t, self.dash_t, self.dash_dx, self.dash_dy = 0.0, 9.0, 0.0, 0.0, 0.0
        self.charges, self.recharge = 1, 0.0
        self.weapons, self.wi = ["pistol"], 0
        self.fire_cd, self.burst_left, self.burst_t = 0.0, 0, 0.0
        self.beam, self.beam_tick, self.firing = None, 0.0, False
        self.shield, self.shield_t = False, 0.0
        self.coins, self.kill_heal, self.blade_tick = 0, 0, 0.0
        self.alive, self.trail = True, []


class Intent:
    """What the player (or the autopilot) wants this frame."""

    def __init__(self):
        self.mx = self.my = 0.0
        self.aim, self.fire, self.dash, self.interact, self.swap = None, False, False, False, False


class Game:
    """One run's world and rules. Rendering reads it; it never reads the renderer. Sound and
    particles go out through self.sfx and the fx lists."""

    def __init__(self, seed, diff="normal", start_floor=1, cols=120, rows=40, sounds=None, fx=True):
        self.seed, self.diff_name, self.D = seed, diff, DIFFS[diff]
        self.rng = sub_rng(seed, "play")
        self.fxr = sub_rng(seed, "fx")
        self.sounds, self.fx_on = sounds, fx
        iw = clamp((cols - 2 * BX) // T, 12, 22)
        ih = clamp((2 * (rows - 2) - TOP - BOT) // T, 7, 13)
        self.geo = Geo(iw, ih)
        self.time = 0.0
        self.stats = {"kills": 0, "coins": 0, "time": 0.0, "dmg": 0, "rooms": 0, "bosses": 0, "shots": 0}
        self.ups = {}
        self.mode, self.sub, self.sub_t = "play", None, 0.0
        self.freeze, self.slow_t, self.shake_t, self.shake_k = 0, 0.0, 0.0, 0.0
        self.parts, self.rings, self.lights, self.texts, self.marks = [], [], [], [], []
        self.lines, self.beams = [], []
        self.pb, self.eb, self.enemies = [], [], []
        self.choice, self.choice_from, self.prompt, self.banner = None, None, None, None
        self.won = False
        self.first_fight_done = False
        self.player = Player(0, 0, self.D["hp"])
        self.fi = -1
        self.trans = None
        self.booms = []
        self.vacuum = False
        self.event_log = []
        self.next_floor(start_floor - 1, boost=start_floor > 1)

    # -------------------------------------------------------------- helpers
    def sfx(self, key, vol=1.0, gap=0.0):
        if self.sounds:
            self.sounds.play(key, vol, gap)

    def biome(self):
        return BIOMES[self.fi // 3]

    def up(self, k):
        return self.ups.get(k, 0)

    def bs(self):
        """Enemy bullet speed multiplier for this floor."""
        return self.D["bspeed"] * (0.86 if self.fi == 0 else 1.0 + 0.025 * self.fi)

    def fire_mult(self):
        """Enemy attack interval multiplier (bigger is slower)."""
        return self.D["fire"] * (1.3 if self.fi == 0 else max(0.75, 1.0 - 0.035 * self.fi))

    def shake(self, k, t=0.3):
        if k >= self.shake_k * (self.shake_t / 0.3 if self.shake_t > 0 else 0):
            self.shake_k, self.shake_t = k, t

    def text(self, x, y, s, col, life=0.9, rise=10.0):
        self.texts.append([x, y, s, col, 0.0, life, rise])

    # -------------------------------------------------------------- floors and rooms
    def next_floor(self, fi, boost=False):
        self.fi = fi
        self.rooms = gen_floor(self.seed, fi, self.geo)
        if boost:  # --floor N: a few upgrades and a weapon so a deep start is fair
            r = sub_rng(self.seed, "boost", fi)
            for _ in range(fi):
                k = r.choice(list(UPGRADES))
                if self.up(k) < UPGRADES[k][4]:
                    self.apply_upgrade(k, quiet=True)
            if fi >= 2:
                self.player.weapons.append(r.choice(WEAPON_ORDER[1:]))
            self.player.coins += 10 * fi
        self.pos = (0, 0)
        self.enter_room((0, 0), None)
        self.banner = (f"{fi // 3 + 1}-{fi % 3 + 1}", self.biome()["name"], self.time)

    def cur(self):
        return self.rooms[self.pos]

    def enter_room(self, pos, came_from):
        self.pos = pos
        room = self.cur()
        g, p = self.geo, self.player
        if came_from is None:
            p.x, p.y = g.W / 2, g.y0 + g.ih * T * 0.6
        else:
            p.x, p.y = g.entry(came_from)
        p.vx = p.vy = 0.0
        self.entry_xy = (p.x, p.y)
        self.vacuum = False
        self.pb, self.eb, self.beams, self.lines, self.marks = [], [], [], [], []
        self.enemies = []
        self.parts, self.rings, self.lights, self.texts = [], [], [], []
        first = not room.visited
        room.visited = True
        if room.kind in ("start", "treasure", "shop"):
            room.cleared = True
        if first:
            self.stock_room(room)
        self.solid = self.build_solid(room)
        self.lock_pending = not room.cleared

    def stock_room(self, room):
        g = self.geo
        cx, cy = g.W / 2, (g.y0 + g.y1) / 2
        r = sub_rng(self.seed, "stock", self.fi, room.gx, room.gy)
        if room.kind == "treasure":
            room.pickups.append(Pickup("chest", cx, cy))
        elif room.kind == "shop":
            b = self.fi // 3
            have = set(self.player.weapons)
            spare = [w for w in WEAPON_ORDER if w not in have]
            items = [("heart", None, 10 + 3 * b), ("upgrade", None, 30 + 8 * b)]
            items.append(("weapon", r.choice(spare), 24 + 5 * b) if spare else ("maxhp", None, 22 + 4 * b))
            for i, (k, v, price) in enumerate(items):
                room.pickups.append(Pickup("shop", cx + (i - 1) * 26, cy, (k, v), price))

    def build_solid(self, room):
        g = self.geo
        W, H = g.W, g.H
        s = bytearray(b"\x01") * (W * H)
        for y in range(g.y0, g.y1):
            s[y * W + g.x0:y * W + g.x1] = b"\x00" * (g.x1 - g.x0)
        for d in room.doors:
            if room.locked:
                continue
            x0, y0, x1, y1 = g.door[d]
            for y in range(y0, y1):
                s[y * W + x0:y * W + x1] = b"\x00" * (x1 - x0)
        for tx, ty in room.pillars:
            x0, y0 = BX + tx * T, TOP + ty * T
            for y in range(y0, y0 + T):
                s[y * W + x0:y * W + x0 + T] = b"\x01" * T
        return s

    def is_solid(self, x, y):
        ix, iy = int(x), int(y)
        if ix < 0 or iy < 0 or ix >= self.geo.W or iy >= self.geo.H:
            return True
        return self.solid[iy * self.geo.W + ix] == 1

    def box_hits(self, x, y, hw, hh):
        s, W, Hh = self.solid, self.geo.W, self.geo.H
        for px in (x - hw, x, x + hw):
            for py in (y - hh, y, y + hh):
                ix, iy = int(px), int(py)
                if ix < 0 or iy < 0 or ix >= W or iy >= Hh or s[iy * W + ix]:
                    return True
        return False

    def barrel_hit(self, x, y, rad):
        for b in self.cur().barrels:
            if (b[0] - x) ** 2 + (b[1] - y) ** 2 < (rad + 3.5) ** 2:
                return b
        return None

    def move_body(self, x, y, dx, dy, hw, hh, oy=0.0):
        """Axis-separated move against walls and barrels; returns (x, y, hit_x, hit_y)."""
        hx = hy = False
        if dx:
            nx = x + dx
            if self.box_hits(nx, y + oy, hw, hh) or self.barrel_hit(nx, y + oy, hw):
                hx = True
            else:
                x = nx
        if dy:
            ny = y + dy
            if self.box_hits(x, ny + oy, hw, hh) or self.barrel_hit(x, ny + oy, hw):
                hy = True
            else:
                y = ny
        return x, y, hx, hy

    def lock_room(self):
        room = self.cur()
        room.locked = True
        self.lock_pending = False
        self.solid = self.build_solid(room)
        self.sfx("exit", 0.8)
        self.shake(0.6, 0.18)
        for d in room.doors:
            x0, y0, x1, y1 = self.geo.door[d]
            for k in range(6):
                self.dust((x0 + x1) / 2 + self.fxr.uniform(-6, 6), (y0 + y1) / 2, (150, 140, 170))
        if room.kind == "boss":
            self.sub, self.sub_t = "intro", 0.0
            self.sfx("attack", 0.7)
        else:
            if room.waves is None:
                first = not self.first_fight_done and self.fi == 0
                room.waves = make_waves(self.seed, self.fi, room, self.D, first)
                self.first_fight_done = True
            room.wave_i = 0
            self.start_wave()

    def unlock_room(self):
        room = self.cur()
        room.locked, room.cleared = False, True
        self.solid = self.build_solid(room)
        self.stats["rooms"] += 1
        self.sfx("clear", 0.6)
        self.clear_bullets()
        self.vacuum = True
        for d in room.doors:  # the bars drop in a shower of sparks
            x0, y0, x1, y1 = self.geo.door[d]
            self.spark((x0 + x1) / 2, (y0 + y1) / 2, BIOMES[self.fi // 3]["accent"], 10, 45, 0.45)
        g = self.geo
        if room.kind in ("exit", "boss"):
            cx, cy = g.W / 2, (g.y0 + g.y1) / 2
            spot = self.free_spot_near(cx, cy)
            room.pickups.append(Pickup("portal", *spot))
        elif self.rng.random() < 0.22 + (0.15 if self.player.hp <= self.player.maxhp * 0.4 else 0):
            room.pickups.append(Pickup("heart", *self.free_spot_near(g.W / 2, (g.y0 + g.y1) / 2)))
        self.text(g.W / 2, g.y0 + 10, "ROOM CLEAR", (190, 255, 210), 1.4, 6)

    def free_spot_near(self, x, y):
        g = self.geo
        best = None
        for r in range(0, 40, 2):
            for k in range(12):
                a = k * math.pi / 6
                px, py = x + math.cos(a) * r, y + math.sin(a) * r * 0.6
                if not self.box_hits(px, py, 4, 4) and not self.barrel_hit(px, py, 4):
                    return px, py
        return best or (x, y)

    def spawn_points(self, n):
        g, p = self.geo, self.player
        room = self.cur()
        cand = []
        for tx in range(g.iw):
            for ty in range(g.ih):
                if (tx, ty) in room.pillars:
                    continue
                x, y = g.tile_px(tx, ty)
                if (x - p.x) ** 2 + (y - p.y) ** 2 < 38 ** 2 or self.barrel_hit(x, y, 5):
                    continue
                near_door = any(abs(tx - dx) + abs(ty - dy) <= 1 for d in room.doors for dx, dy in g.door_t[d])
                if not near_door:
                    cand.append((x, y))
        self.rng.shuffle(cand)
        return cand[:n] if cand else [(g.W / 2, g.y0 + 12)] * n

    def start_wave(self):
        room = self.cur()
        kinds = room.waves[room.wave_i]
        pts = self.spawn_points(len(kinds))
        hpm = self.D["ehp"] * (1 + 0.16 * self.fi)
        for i, k in enumerate(kinds):
            x, y = pts[i % len(pts)]
            self.add_enemy(k, x + self.rng.uniform(-1.5, 1.5), y, hpm, delay=0.75 + 0.12 * i)
        self.wave_t = 0.0

    def add_enemy(self, kind, x, y, hpm=1.0, delay=0.8):
        if self.box_hits(x, y, 3, 3):
            x, y = self.free_spot_near(x, y)
        e = Enemy(kind, x, y, hpm)
        e.spawn = delay
        e.cd = self.rng.uniform(0.8, 1.6)
        e.t = self.rng.uniform(0, 6)
        if e.boss:
            e.maxhp = e.hp = ENEMY[kind][0] * self.D["boss"]
            e.brain = Brain(self, e)
        self.enemies.append(e)
        if delay > 0:
            self.marks.append([x, y, 0.0, delay, BULLET_COL.get(kind, (255, 80, 140))])
        return e

    # -------------------------------------------------------------- upgrades
    def offer(self, src):
        """Three distinct upgrade keys, weighted, skipping maxed ones."""
        r = self.rng
        pool = [k for k in UPGRADES if self.up(k) < UPGRADES[k][4]]
        pick = []
        while pool and len(pick) < 3:
            ws = [RARE.get(k, 1.0) for k in pool]
            x = r.random() * sum(ws)
            for k, wt in zip(pool, ws):
                x -= wt
                if x <= 0:
                    break
            pick.append(k)
            pool.remove(k)
        self.choice, self.choice_from, self.choice_t, self.choice_sel = pick, src, self.time, 1 if len(pick) > 1 else 0
        self.mode = "choice"

    def apply_upgrade(self, k, quiet=False):
        self.ups[k] = self.up(k) + 1
        p = self.player
        if k == "vital":
            p.maxhp += 4
            p.hp = p.maxhp
        elif k == "dash":
            p.charges += 1
        elif k == "shield":
            p.shield = True
        if not quiet:
            self.event_log.append(f"took {UPGRADES[k][0]}")

    def choose(self, i):
        if not self.choice or not 0 <= i < len(self.choice):
            return
        k = self.choice[i]
        self.apply_upgrade(k)
        src = self.choice_from
        self.choice = None
        self.mode = "play"
        p = self.player
        self.text(p.x, p.y - 8, UPGRADES[k][0], UPGRADES[k][3], 1.4, 8)
        self.sfx("coin", 0.7)
        if src == "floor":
            self.next_floor(self.fi + 1)

    # -------------------------------------------------------------- effects (data only)
    def spark(self, x, y, col, n=6, spd=40.0, life=0.35, drag=4.0, grav=0.0):
        if not self.fx_on:
            return
        r = self.fxr
        for _ in range(n):
            a, v = r.uniform(0, 6.283), r.uniform(0.3, 1.0) * spd
            self.parts.append([x, y, math.cos(a) * v, math.sin(a) * v, 0.0, life * r.uniform(0.6, 1.2), col, 0,
                               drag, grav])

    def dust(self, x, y, col=(120, 116, 140), n=1):
        if not self.fx_on:
            return
        r = self.fxr
        for _ in range(n):
            self.parts.append([x + r.uniform(-1.5, 1.5), y, r.uniform(-8, 8), r.uniform(-10, -3), 0.0,
                               r.uniform(0.3, 0.6), col, 1, 3.0, 0.0])

    def ring(self, x, y, col, r1=10.0, dur=0.3, r0=1.0):
        if self.fx_on:
            self.rings.append([x, y, 0.0, dur, r0, r1, col])

    def light(self, x, y, col, rad=8.0, dur=0.12, k=0.6):
        if self.fx_on:
            self.lights.append([x, y, 0.0, dur, rad, col, k])

    def boom(self, x, y, big=False):
        self.booms.append([x, y, 0.0, 1.0 if not big else 1.3])
        self.light(x, y, (255, 120, 90), 18 if big else 12, 0.3, 0.7)
        self.spark(x, y, (255, 200, 120), 14 if big else 8, 70 if big else 50, 0.5)

    def decal(self, name, x, y, flip=False, frame=0):
        room = self.cur()
        room.decals.append((name, frame, flip, x, y))

    # -------------------------------------------------------------- bullets
    def aim(self, x, y):
        p = self.player
        return math.atan2(p.y + 1 - y, p.x - x)

    def eshoot(self, x, y, ang, spd, st, dmg=2, r=1.8, life=7.0, acc=0.0, turn=0.0, delay=0.0):
        if len(self.eb) >= MAX_EBULLETS:
            return None
        s = spd * self.bs()
        b = Bullet(x, y, math.cos(ang) * s, math.sin(ang) * s, st, r, dmg, life)
        b.acc, b.turn, b.delay = acc, turn, delay
        self.eb.append(b)
        return b

    def ering(self, x, y, n, spd, st, off=0.0, gap=None, gapw=0.0, **kw):
        for i in range(n):
            a = off + i * 2 * math.pi / n
            if gap is not None and abs((a - gap + math.pi) % (2 * math.pi) - math.pi) < gapw:
                continue
            self.eshoot(x, y, a, spd, st, **kw)

    def efan(self, x, y, ang, n, spread, spd, st, **kw):
        for i in range(n):
            a = ang + (i - (n - 1) / 2) * (spread / max(1, n - 1)) if n > 1 else ang
            self.eshoot(x, y, a, spd, st, **kw)

    def clear_bullets(self, x=None, y=None, rad=1e9, coins=False):
        keep, n = [], 0
        for b in self.eb:
            if (b.x - (x or 0)) ** 2 + (b.y - (y or 0)) ** 2 < rad * rad or x is None:
                if coins and n < 40 and self.rng.random() < 0.5:
                    self.cur().pickups.append(Pickup("coin", b.x, b.y))
                    n += 1
                if self.fxr.random() < 0.5:
                    self.spark(b.x, b.y, BULLET_COL.get(b.kind, WHITE), 2, 20, 0.25)
            else:
                keep.append(b)
        self.eb = keep

    # -------------------------------------------------------------- damage
    def hurt_player(self, dmg, sx, sy):
        p = self.player
        if p.inv > 0 or not p.alive or self.mode != "play" or self.trans:
            return False
        if p.shield:
            p.shield, p.shield_t, p.inv = False, 0.0, 0.8
            self.ring(p.x, p.y, SHIELD, 16, 0.4)
            self.sfx("bonk", 0.7)
            self.clear_bullets(p.x, p.y, 16)
            self.text(p.x, p.y - 8, "shield!", SHIELD)
            return True
        p.hp -= dmg
        self.stats["dmg"] += dmg
        p.inv, p.hurt_t = INVULN, 0.0
        self.freeze = 4
        self.shake(1.0, 0.35)
        self.sfx("phurt", 0.9)
        a = math.atan2(p.y - sy, p.x - sx)
        p.vx, p.vy = math.cos(a) * 90, math.sin(a) * 90
        self.spark(p.x, p.y, P_RED, 10, 50, 0.4)
        self.light(p.x, p.y, (255, 60, 60), 14, 0.2, 0.6)
        self.clear_bullets(p.x, p.y, 12)
        if p.hp <= 0:
            p.hp = 0
            self.die()
        return True

    def die(self):
        p = self.player
        p.alive = False
        self.mode, self.sub_t = "dying", 0.0
        self.slow_t = 1.2
        self.boom(p.x, p.y, True)
        self.ring(p.x, p.y, P_YELLOW, 30, 0.7)
        self.shake(1.4, 0.6)
        self.sfx("bigboom", 1.0)
        self.sfx("gameover", 0.6)
        self.event_log.append(f"died on floor {self.floor_label()}")

    def floor_label(self):
        return f"{self.fi // 3 + 1}-{self.fi % 3 + 1}"

    def dmg_mult(self):
        return (1 + 0.25 * self.up("heavy")) * (1 + 0.1 * self.up("big"))

    def hit_enemy(self, e, dmg, sx, sy, knock=20.0, crit=False):
        if e.dead or e.spawn > 0 or e.inv > 0:
            return False
        e.hp -= dmg
        e.flash = 0.035 if e.boss else 0.08
        if not e.boss:
            a = math.atan2(e.y - sy, e.x - sx)
            e.kx, e.ky = math.cos(a) * knock, math.sin(a) * knock
        # Hits in quick succession add up on one number instead of stacking new ones.
        dn = e.data.get("dn")
        if dn and self.time - dn[1] < 0.25 and dn[0][4] < dn[0][5]:
            dn[2] += dmg
            dn[0][2] = str(max(1, int(round(dn[2]))))
            dn[0][4] = min(dn[0][4], 0.12)
            if crit:
                dn[0][3] = (255, 236, 110)
        else:
            entry = [e.x + self.fxr.uniform(-3, 3), e.y - e.r - 3, str(max(1, int(round(dmg)))),
                     (255, 236, 110) if crit else (236, 236, 255), 0.0, 0.65, 12.0]
            self.texts.append(entry)
            e.data["dn"] = [entry, self.time, dmg]
        self.sfx("ehurt", 0.45, 0.07)
        if e.hp <= 0:
            if e.boss:
                self.boss_down(e)
            else:
                self.kill_enemy(e)
        return True

    def kill_enemy(self, e):
        e.dead = True
        st, p = self.stats, self.player
        st["kills"] += 1
        col = BULLET_COL.get(e.kind, (255, 120, 160))
        r = self.rng
        lo, hi = ENEMY[e.kind][2]
        n = r.randint(lo, hi)
        if self.up("midas"):
            n = int(n * (1 + 0.5 * self.up("midas")) + 0.5)
        for _ in range(n):
            c = Pickup("coin", e.x, e.y)
            a = r.uniform(0, 6.283)
            c.vx, c.vy = math.cos(a) * r.uniform(20, 50), math.sin(a) * r.uniform(20, 50)
            self.cur().pickups.append(c)
        if r.random() < 0.03 and e.kind != "gnat":
            self.cur().pickups.append(Pickup("heart", *self.free_spot_near(e.x, e.y)))
        self.spark(e.x, e.y, col, 12, 60, 0.45)
        self.spark(e.x, e.y, WHITE, 4, 40, 0.25)
        self.ring(e.x, e.y, col, 9 + e.r, 0.25)
        self.light(e.x, e.y, col, 10 + e.r, 0.18, 0.7)
        if e.kind in CORPSE:
            self.decal(CORPSE[e.kind], e.x, e.y + 2, e.face < 0)
        elif e.kind != "gnat":
            self.decal("splat", e.x, e.y + 2, frame=hash((round(e.x), round(e.y))) % 3)
        self.freeze = max(self.freeze, 2 if e.r < 5 else 3)
        self.sfx("boom", 0.45, 0.06)
        if e.kind == "blob":
            for s in (-1, 1):
                b = self.add_enemy("blobling", e.x + 4 * s, e.y, self.D["ehp"] * (1 + 0.16 * self.fi), 0.0)
                b.kx, b.ky = 60 * s, -20
                b.cd = 1.0
            self.ering(e.x, e.y, 6, 26, "o_blob", off=r.uniform(0, 1))
        if e.kind == "summoner":
            for g2 in self.enemies:
                if g2.kind == "gnat" and not g2.dead:
                    g2.hp = 0.1
        if self.up("vamp"):
            p.kill_heal += 1
            if p.kill_heal >= 12 - 3 * (self.up("vamp") - 1):
                p.kill_heal = 0
                if p.hp < p.maxhp:
                    p.hp += 1
                    self.text(p.x, p.y - 8, "+1", (255, 110, 140))

    def boss_down(self, e):
        e.hp, e.inv = 0, 99
        e.data["dying"] = 0.0
        self.sub, self.sub_t = "bossdeath", 0.0
        self.freeze = 10
        self.slow_t = 0.8
        self.beams, self.lines = [], []
        self.clear_bullets(coins=True)
        for o in self.enemies:
            if o is not e and not o.dead:
                self.kill_enemy(o)
        self.shake(1.5, 0.6)
        self.sfx("bigboom", 1.0)

    def explode_barrel(self, b):
        room = self.cur()
        if b not in room.barrels:
            return
        room.barrels.remove(b)
        x, y = b[0], b[1]
        self.boom(x, y, True)
        self.shake(1.0, 0.35)
        self.sfx("bigboom", 0.8, 0.1)
        self.decal("scorch", x, y + 1)
        for e in self.enemies:
            if not e.dead and e.spawn <= 0 and (e.x - x) ** 2 + (e.y - y) ** 2 < 20 ** 2:
                self.hit_enemy(e, 20 * self.dmg_mult(), x, y, 90)
        p = self.player
        if (p.x - x) ** 2 + (p.y - y) ** 2 < 15 ** 2:
            self.hurt_player(2, x, y)
        for o in list(room.barrels):
            if (o[0] - x) ** 2 + (o[1] - y) ** 2 < 20 ** 2:
                o[2] -= 10
                if o[2] <= 0:
                    self.explode_barrel(o)

    # -------------------------------------------------------------- frame
    def update(self, dt, it):
        p = self.player
        if self.mode in ("choice", "dead", "won"):
            self.time += dt
            self.update_fx(dt)
            return
        if self.freeze > 0:
            self.freeze -= 1
            return
        if self.slow_t > 0:
            self.slow_t -= dt
            dt *= 0.35
        self.time += dt
        if self.shake_t > 0:
            self.shake_t -= dt
        if self.mode == "dying":
            self.sub_t += dt
            self.update_fx(dt)
            if self.sub_t > 1.3:
                self.mode = "dead"
            return
        if self.trans:
            self.trans[0] += dt
            if self.trans[0] >= 0.14 and not self.trans[2]:
                self.trans[2] = True
                d = self.trans[1]
                self.enter_room(self.cur().doors[d], OPP[d])
            if self.trans[0] >= 0.34:
                self.trans = None
            return
        self.stats["time"] += dt
        self.prompt = None
        p = self.player
        if p.hp <= max(2, p.maxhp * 0.3) and int(self.time / 0.85) != int((self.time - dt) / 0.85):
            self.sfx("thud", 0.4)  # a heartbeat while health is low
        self.update_player(dt, it)
        if self.trans or self.mode != "play":
            return
        self.update_enemies(dt)
        self.update_bullets(dt)
        self.update_beams(dt)
        self.update_pickups(dt, it)
        self.update_fx(dt)
        self.update_room(dt)

    def update_room(self, dt):
        room = self.cur()
        if self.sub == "intro":
            self.sub_t += dt
            if self.sub_t >= 0.7 and not any(e.boss for e in self.enemies):
                g = self.geo
                e = self.add_enemy(BOSS_KIND[self.fi // 3], g.W / 2, g.y0 + 18, 1.0, 0.0)
                e.data["appear"] = 0.0
                self.boom(e.x, e.y, True)
                self.shake(1.2, 0.5)
                self.sfx("bigboom", 0.8)
            if self.sub_t >= 2.6:
                self.sub = None
            return
        if self.sub == "bossdeath":
            self.sub_t += dt
            e = next((o for o in self.enemies if o.boss), None)
            if e and self.sub_t < 2.0:
                e.data["dying"] = self.sub_t
                if int(self.sub_t * 9) != int((self.sub_t - dt) * 9):
                    a, rr = self.fxr.uniform(0, 6.283), self.fxr.uniform(0, e.r * 1.2)
                    self.boom(e.x + math.cos(a) * rr, e.y + math.sin(a) * rr * 0.8)
                    self.sfx("boom", 0.6, 0.05)
                    self.shake(0.7, 0.2)
            elif e:
                e.dead = True
                self.boom(e.x, e.y, True)
                self.ring(e.x, e.y, WHITE, 60, 0.8)
                self.light(e.x, e.y, WHITE, 40, 0.5, 0.9)
                self.shake(1.6, 0.7)
                self.sfx("bigboom", 1.0)
                self.stats["bosses"] += 1
                r = self.rng
                for _ in range(24):
                    c = Pickup("coin", e.x, e.y)
                    a = r.uniform(0, 6.283)
                    c.vx, c.vy = math.cos(a) * r.uniform(30, 90), math.sin(a) * r.uniform(30, 90)
                    room.pickups.append(c)
                room.pickups.append(Pickup("heart", e.x - 8, e.y + 10))
                room.pickups.append(Pickup("heart", e.x + 8, e.y + 10))
                self.text(e.x, e.y - 14, "BOSS DEFEATED", GOLD, 2.4, 6)
                self.event_log.append(f"beat {BOSS_NAME[e.kind].title()} after {e.data.get('fight', 0):.0f}s")
                self.sub = None
                self.unlock_room()
            return
        if not room.locked:
            return
        if room.kind == "boss":
            return
        alive = [e for e in self.enemies if not e.dead and e.kind != "gnat"]
        self.wave_t += dt
        if room.wave_i + 1 < len(room.waves):
            if (not alive and self.wave_t > 0.6) or (len(alive) <= 1 and self.wave_t > 5.0):
                room.wave_i += 1
                self.start_wave()
        elif not alive:
            for e in self.enemies:
                if not e.dead:
                    self.kill_enemy(e)
            self.unlock_room()

    def update_player(self, dt, it):
        p, g = self.player, self.geo
        p.inv -= dt
        p.hurt_t += dt
        if p.hp < p.hp_shown:
            p.hp_shown += (p.hp - p.hp_shown) * min(1.0, dt * 3.0)
        else:
            p.hp_shown = float(p.hp)
        maxc = 1 + self.up("dash")
        if p.charges < maxc:
            p.recharge += dt
            if p.recharge >= DASH_CD * (1 - 0.15 * self.up("boots")):
                p.charges += 1
                p.recharge = 0.0
                if p.charges == maxc:
                    self.spark(p.x, p.y, CYAN, 4, 20, 0.3)
        mx, my = it.mx, it.my
        n = math.hypot(mx, my)
        if n > 1:
            mx, my = mx / n, my / n
        if it.dash and p.charges > 0 and p.dash_t <= 0:
            dx, dy = (mx, my) if n > 0.1 else (math.cos(p.aim), math.sin(p.aim))
            k = math.hypot(dx, dy) or 1.0
            p.dash_dx, p.dash_dy = dx / k, dy / k
            p.dash_t = DASH_TIME
            p.charges -= 1
            p.inv = max(p.inv, DASH_TIME + 0.08)
            self.sfx("swoosh", 0.6)
            for _ in range(4):
                self.dust(p.x, p.y + 4, (170, 200, 230))
            if self.up("phase"):
                self.clear_bullets(p.x, p.y, 18)
                self.ring(p.x, p.y, (170, 200, 255), 18, 0.3)
        speed = PLAYER_SPEED * (1 + 0.12 * self.up("boots"))
        if p.dash_t > 0:
            p.dash_t -= dt
            p.vx, p.vy = p.dash_dx * DASH_SPEED, p.dash_dy * DASH_SPEED
            p.trail.append((p.x, p.y, self.time, p.face))
        else:
            k = min(1.0, dt * 22)
            p.vx += (mx * speed - p.vx) * k
            p.vy += (my * speed - p.vy) * k
        del p.trail[:-6]
        p.x, p.y, _, _ = self.move_body(p.x, p.y, p.vx * dt, p.vy * dt, 2.5, 2.0, 2.5)
        sp = math.hypot(p.vx, p.vy)
        was = p.moving
        p.moving = sp > 8
        p.anim += dt * (sp / 18 if p.moving else 1.0)
        if p.moving and not was or (p.moving and self.fxr.random() < dt * 4):
            self.dust(p.x - p.vx * 0.05, p.y + 5)
        if it.aim is not None:
            p.aim = it.aim
        if it.fire or it.aim is not None:
            p.face = 1 if math.cos(p.aim) >= 0 else -1
        elif abs(p.vx) > 5:
            p.face = 1 if p.vx > 0 else -1
            p.aim = 0.0 if p.vx > 0 else math.pi
        room = self.cur()
        if not room.locked:
            d = None
            if p.y < g.y0 - 1.5 and "up" in room.doors:
                d = "up"
            elif p.y > g.y1 - 3 and "down" in room.doors:
                d = "down"
            elif p.x < g.x0 - 0.5 and "left" in room.doors:
                d = "left"
            elif p.x > g.x1 + 0.5 and "right" in room.doors:
                d = "right"
            if d:
                self.trans = [0.0, d, False]
                self.sfx("exit", 0.4)
                if self.vacuum:  # coins still flying home count as caught
                    for k in room.pickups:
                        if k.kind == "coin" and not k.dead:
                            k.dead = True
                            p.coins += 1
                            self.stats["coins"] += 1
                    room.pickups = [k for k in room.pickups if not k.dead]
                return
        if (self.lock_pending and g.x0 + 2 < p.x < g.x1 - 2 and g.y0 + 1 < p.y < g.y1 - 5
                and math.hypot(p.x - self.entry_xy[0], p.y - self.entry_xy[1]) > 9):
            self.lock_room()
        if it.swap and len(p.weapons) > 1:
            p.wi = 1 - p.wi
            p.fire_cd = max(p.fire_cd, 0.12)
            p.burst_left = 0
            self.sfx("tick", 0.6)
            self.text(p.x, p.y - 9, WEAPONS[p.weapons[p.wi]]["name"], CYAN_LIT, 0.8, 6)
        self.player_fire(dt, it)
        if self.up("shield") and not p.shield:
            p.shield_t += dt
            if p.shield_t >= 12 - 2.5 * (self.up("shield") - 1):
                p.shield = True
                self.ring(p.x, p.y, SHIELD, 12, 0.35)
                self.sfx("tick", 0.5)
        nb = 2 * self.up("blades")
        if nb:
            p.blade_tick -= dt
            for i in range(nb):
                a = self.time * 4.2 + i * 2 * math.pi / nb
                bx, by = p.x + math.cos(a) * 12, p.y + 1 + math.sin(a) * 9
                for b in self.eb:
                    if not b.dead and b.delay <= 0 and abs(b.x - bx) < 3 and abs(b.y - by) < 3:
                        b.dead = True
                        self.spark(b.x, b.y, (255, 240, 170), 2, 25, 0.2)
                if p.blade_tick <= 0:
                    for e in self.enemies:
                        if not e.dead and e.spawn <= 0 and (e.x - bx) ** 2 + (e.y - by) ** 2 < (e.r + 3) ** 2:
                            self.hit_enemy(e, 1.2 * self.dmg_mult(), p.x, p.y, 10)
            if p.blade_tick <= 0:
                p.blade_tick = 0.12

    def muzzle(self):
        p = self.player
        return p.x + math.cos(p.aim) * 6, p.y + 1.5 + math.sin(p.aim) * 4.5

    def player_fire(self, dt, it):
        p = self.player
        w = WEAPONS[p.weapons[p.wi]]
        p.fire_cd -= dt
        firing = it.fire and p.dash_t <= 0
        p.firing = firing
        if w.get("beam"):
            if firing:
                self.fire_beam(dt, w)
            else:
                p.beam = None
            return
        p.beam = None
        if p.burst_left > 0:
            p.burst_t -= dt
            if p.burst_t <= 0:
                self.shoot(w)
                p.burst_left -= 1
                p.burst_t = w["gap"]
        if firing and p.fire_cd <= 0:
            p.fire_cd = w["cd"] * 0.83 ** self.up("rapid")
            if w.get("burst"):
                p.burst_left, p.burst_t = w["burst"] - 1, w["gap"]
            self.shoot(w)

    def shoot(self, w):
        p, r = self.player, self.rng
        mx, my = self.muzzle()
        a = p.aim
        dmg = w["dmg"] * self.dmg_mult()
        size = 1 + 0.4 * self.up("big")
        n = w["n"]
        shots = []
        for i in range(n):
            if n > 1:
                off = (i - (n - 1) / 2) * (w["spread"] / (n - 1)) + r.uniform(-0.06, 0.06)
            else:
                off = r.uniform(-w["spread"], w["spread"])
            shots.append((a + off, w["spd"] * (r.uniform(0.82, 1.08) if n > 1 else 1.0), dmg))
        if self.up("split"):
            for s in (-0.22, 0.22):
                shots.append((a + s, w["spd"] * 0.95, dmg * 0.5))
        for ang, spd, d in shots:
            b = Bullet(mx, my, math.cos(ang) * spd, math.sin(ang) * spd, w["st"], w["r"] * size, d, w["life"])
            b.pierce = self.up("pierce")
            b.bounce = w.get("bounce", 0) + self.up("ricochet")
            b.home = w.get("home", 0.0) + 2.5 * self.up("homing")
            b.hits = set()
            if self.up("crit") and r.random() < 0.15 * self.up("crit"):
                b.dmg *= 2.5
                b.crit = True
            b.kind = w["knock"]
            self.pb.append(b)
        self.stats["shots"] += 1
        self.light(mx, my, CYAN, 7, 0.07, 0.8)
        self.spark(mx, my, CYAN_LIT, 2, 35, 0.12)
        p.vx -= math.cos(a) * 6
        p.vy -= math.sin(a) * 6
        if w["st"] == "pellet":
            self.sfx("boom", 0.3, 0.1)
        else:
            self.sfx("shoot", 0.28, 0.13)

    def ray(self, x, y, dx, dy, maxlen=260.0, step=1.5):
        """March from (x, y) along a unit direction to the first solid pixel; returns the end."""
        L = 0.0
        while L < maxlen:
            nx, ny = x + dx * step, y + dy * step
            if self.is_solid(nx, ny):
                break
            x, y, L = nx, ny, L + step
        return x, y

    def fire_beam(self, dt, w):
        p = self.player
        x, y = self.muzzle()
        dx, dy = math.cos(p.aim), math.sin(p.aim)
        segs = []
        for _ in range(1 + self.up("ricochet")):
            ex, ey = self.ray(x, y, dx, dy)
            segs.append((x, y, ex, ey))
            hx, hy = self.is_solid(ex + dx * 1.6, ey), self.is_solid(ex, ey + dy * 1.6)
            if hx:
                dx = -dx
            if hy or not hx:
                dy = -dy if hy else dy
            if not hx and not hy:
                break
            x, y = ex, ey
        p.beam = segs
        p.beam_tick -= dt
        self.sfx("beam", 0.25, 0.5)
        if p.beam_tick > 0:
            return
        p.beam_tick = 0.08
        width = 1.6 + 0.8 * self.up("big")
        dmg = w["dmg"] * 0.08 * self.dmg_mult()
        ex, ey = segs[-1][2], segs[-1][3]
        self.spark(ex, ey, CYAN_LIT, 2, 30, 0.2)
        for e in self.enemies:
            if e.dead or e.spawn > 0:
                continue
            for x0, y0, x1, y1 in segs:
                if seg_dist(e.x, e.y, x0, y0, x1, y1) < e.r + width:
                    crit = self.up("crit") and self.rng.random() < 0.15 * self.up("crit")
                    self.hit_enemy(e, dmg * (2.5 if crit else 1), p.x, p.y, w["knock"], crit)
                    break
        for b in list(self.cur().barrels):
            if any(seg_dist(b[0], b[1], *s) < 5 for s in segs):
                b[2] -= dmg
                if b[2] <= 0:
                    self.explode_barrel(b)

    def nearest_enemy(self, x, y, maxd=1e9):
        best, bd = None, maxd * maxd
        for e in self.enemies:
            if e.dead or e.spawn > 0:
                continue
            d = (e.x - x) ** 2 + (e.y - y) ** 2
            if d < bd:
                best, bd = e, d
        return best

    def update_bullets(self, dt):
        p = self.player
        room = self.cur()
        live = []
        for b in self.pb:
            b.t += dt
            if b.t > b.life or b.dead:
                continue
            if b.home:
                e = self.nearest_enemy(b.x, b.y, 80)
                if e:
                    want = math.atan2(e.y - b.y, e.x - b.x)
                    cur = math.atan2(b.vy, b.vx)
                    da = (want - cur + math.pi) % (2 * math.pi) - math.pi
                    cur += clamp(da, -b.home * dt, b.home * dt)
                    s = math.hypot(b.vx, b.vy)
                    b.vx, b.vy = math.cos(cur) * s, math.sin(cur) * s
            steps = int(math.hypot(b.vx, b.vy) * dt / 3) + 1
            sdt = dt / steps
            for _ in range(steps):
                ox, oy = b.x, b.y
                b.x += b.vx * sdt
                b.y += b.vy * sdt
                if self.is_solid(b.x, b.y):
                    if b.bounce > 0:
                        b.bounce -= 1
                        if self.is_solid(b.x, oy):
                            b.vx = -b.vx
                        if self.is_solid(ox, b.y):
                            b.vy = -b.vy
                        b.x, b.y = ox, oy
                        self.spark(b.x, b.y, CYAN, 2, 25, 0.15)
                        continue
                    b.dead = True
                    self.spark(ox, oy, CYAN_LIT, 3, 30, 0.2)
                    self.sfx("wall", 0.25, 0.1)
                    break
                bar = self.barrel_hit(b.x, b.y, b.r)
                if bar:
                    bar[2] -= b.dmg
                    b.dead = True
                    self.spark(b.x, b.y, (255, 200, 120), 3, 30, 0.2)
                    if bar[2] <= 0:
                        self.explode_barrel(bar)
                    break
                for e in self.enemies:
                    if e.dead or e.spawn > 0 or e in b.hits:
                        continue
                    rr = e.r + b.r
                    if abs(e.x - b.x) < rr and abs(e.y - b.y) < rr and (e.x - b.x) ** 2 + (e.y - b.y) ** 2 < rr * rr:
                        if self.hit_enemy(e, b.dmg, b.x - b.vx * 0.02, b.y - b.vy * 0.02, b.kind, b.crit):
                            self.spark(b.x, b.y, WHITE, 2, 30, 0.15)
                            self.light(b.x, b.y, CYAN, 5, 0.06, 0.5)
                        if b.pierce > 0:
                            b.pierce -= 1
                            b.hits.add(e)
                        else:
                            b.dead = True
                        break
                if b.dead:
                    break
            if not b.dead:
                live.append(b)
        self.pb = live
        hx, hy = p.x, p.y + 1
        inv = p.inv > 0 or not p.alive
        live = []
        for b in self.eb:
            if b.dead:
                continue
            if b.delay > 0:
                b.delay -= dt
                live.append(b)
                continue
            b.t += dt
            if b.t > b.life:
                continue
            if b.acc:
                k = 1 + b.acc * dt
                if k < 1 and b.vx * b.vx + b.vy * b.vy < 9:
                    k = 1.0
                b.vx *= k
                b.vy *= k
            if b.turn:
                c, s = math.cos(b.turn * dt), math.sin(b.turn * dt)
                b.vx, b.vy = b.vx * c - b.vy * s, b.vx * s + b.vy * c
            b.x += b.vx * dt
            b.y += b.vy * dt
            if self.is_solid(b.x, b.y):
                if self.fxr.random() < 0.6:
                    self.spark(b.x - b.vx * dt, b.y - b.vy * dt, BULLET_COL.get(b.kind, WHITE), 2, 20, 0.2)
                continue
            if room.barrels:
                bar = self.barrel_hit(b.x, b.y, b.r * 0.6)
                if bar:
                    bar[2] -= 1
                    if bar[2] <= 0:
                        self.explode_barrel(bar)
                    continue
            if not inv:
                dx, dy = b.x - hx, b.y - hy
                rr = b.r * 0.75 + HIT_R
                if dx * dx + dy * dy < rr * rr:
                    if self.hurt_player(b.dmg, b.x - b.vx, b.y - b.vy):
                        inv = True
                        continue
            live.append(b)
        self.eb = live

    def update_beams(self, dt):
        p = self.player
        keep = []
        for bm in self.beams:
            bm["t"] += dt
            if bm["t"] > bm["warm"] + bm["dur"]:
                continue
            o = bm["owner"]
            if o is not None:
                if o.dead or o.data.get("dying") is not None:
                    continue
                bm["x"], bm["y"] = o.x, o.y
            if bm["t"] > bm["warm"]:
                bm["ang"] += bm["angv"] * dt
            dx, dy = math.cos(bm["ang"]), math.sin(bm["ang"])
            sx, sy = bm["x"] + dx * bm.get("start", 0), bm["y"] + dy * bm.get("start", 0)
            ex, ey = self.ray(sx, sy, dx, dy, step=2.0)
            bm["seg"] = (sx, sy, ex, ey)
            if bm["t"] > bm["warm"] and p.alive and p.inv <= 0:
                if seg_dist(p.x, p.y + 1, sx, sy, ex, ey) < bm["w"] / 2 + 0.8:
                    self.hurt_player(2, ex, ey)
            keep.append(bm)
        self.beams = keep
        keep = []
        for ln in self.lines:
            ln["t"] += dt
            if ln["t"] <= ln["dur"]:
                o = ln.get("owner")
                if o is not None and o.dead:
                    continue
                if o is not None and ln.get("follow"):
                    ln["x"], ln["y"] = o.x, o.y
                    if ln.get("track"):
                        ln["ang"] = self.aim(o.x, o.y)
                keep.append(ln)
        self.lines = keep

    def update_enemies(self, dt):
        p = self.player
        for e in self.enemies:
            if e.dead:
                continue
            if e.spawn > 0:
                e.spawn -= dt
                if e.spawn <= 0:
                    col = BULLET_COL.get(e.kind, WHITE)
                    self.ring(e.x, e.y, col, 12, 0.25)
                    self.spark(e.x, e.y, col, 8, 40, 0.3)
                    e.data["pop"] = self.time
                continue
            e.t += dt
            e.flash -= dt
            e.inv -= dt
            if e.kx or e.ky:
                e.x, e.y, _, _ = self.move_body(e.x, e.y, e.kx * dt, e.ky * dt, e.r * 0.6, e.r * 0.6)
                e.kx *= max(0.0, 1 - dt * 9)
                e.ky *= max(0.0, 1 - dt * 9)
                if abs(e.kx) + abs(e.ky) < 1:
                    e.kx = e.ky = 0.0
            if e.boss:
                if e.data.get("dying") is None:
                    e.data["fight"] = e.data.get("fight", 0.0) + dt
                    e.brain.update(dt)
            else:
                AI[e.kind](self, e, dt)
            if p.alive and p.inv <= 0 and e.data.get("dying") is None:
                rr = e.r * 0.8 + 2.0
                if (e.x - p.x) ** 2 + (e.y - p.y - 1) ** 2 < rr * rr:
                    self.hurt_player(2, e.x, e.y)
        alive = [e for e in self.enemies if not e.dead]
        for i, a in enumerate(alive):  # keep them from stacking into one blob
            if a.boss or a.spawn > 0:
                continue
            for b in alive[i + 1:]:
                if b.boss or b.spawn > 0:
                    continue
                dx, dy = b.x - a.x, b.y - a.y
                rr = a.r + b.r
                d2 = dx * dx + dy * dy
                if d2 < rr * rr and d2 > 0.01:
                    d = math.sqrt(d2)
                    push = (rr - d) * 0.5 * min(1.0, dt * 10) / d
                    if a.kind != "turret":
                        a.x, a.y, _, _ = self.move_body(a.x, a.y, -dx * push, -dy * push, a.r * 0.6, a.r * 0.6)
                    if b.kind != "turret":
                        b.x, b.y, _, _ = self.move_body(b.x, b.y, dx * push, dy * push, b.r * 0.6, b.r * 0.6)
        self.enemies = [e for e in self.enemies if not e.dead or e.boss and self.sub == "bossdeath"]

    def walk(self, e, vx, vy, dt):
        e.vx, e.vy = vx, vy
        e.x, e.y, hx, hy = self.move_body(e.x, e.y, vx * dt, vy * dt, e.r * 0.6, e.r * 0.6)
        return hx or hy

    def update_pickups(self, dt, it):
        p, room = self.player, self.cur()
        mag = 16 + 10 * self.up("midas")
        near, nd = None, 13.0
        for k in room.pickups:
            if k.dead:
                continue
            k.t += dt
            dx, dy = p.x - k.x, p.y + 1 - k.y
            d = math.hypot(dx, dy)
            if k.kind == "coin":
                pull = self.vacuum and not room.locked and k.t > 0.4
                if p.alive and (d < mag or pull) and k.t > 0.25:
                    s = 150 if d > mag else 110
                    k.vx += dx / max(d, 1) * s * dt * 6
                    k.vy += dy / max(d, 1) * s * dt * 6
                    k.vx *= 0.9
                    k.vy *= 0.9
                else:
                    k.vx *= max(0.0, 1 - dt * 5)
                    k.vy *= max(0.0, 1 - dt * 5)
                nx, ny = k.x + k.vx * dt, k.y + k.vy * dt
                if pull:  # after a clear every coin flies home, over pillars too
                    k.x = clamp(nx, self.geo.x0 + 1, self.geo.x1 - 2)
                    k.y = clamp(ny, self.geo.y0 + 1, self.geo.y1 - 2)
                elif not self.is_solid(nx, k.y):
                    k.x = nx
                else:
                    k.vx = -k.vx * 0.5
                if not self.is_solid(k.x, ny):
                    k.y = ny
                else:
                    k.vy = -k.vy * 0.5
                if d < 4.5 and p.alive:
                    k.dead = True
                    p.coins += 1
                    self.stats["coins"] += 1
                    self.spark(k.x, k.y, GOLD_LIT, 2, 20, 0.2)
                    self.sfx("coin", 0.25, 0.06)
                continue
            if k.kind == "heart" and d < 6 and p.hp < p.maxhp:
                k.dead = True
                p.hp = min(p.maxhp, p.hp + 2)
                self.text(k.x, k.y - 6, "+2", (255, 120, 150))
                self.ring(k.x, k.y, (255, 90, 130), 10, 0.3)
                self.sfx("coin", 0.6)
            elif k.kind == "orb" and d < 6:
                k.dead = True
                self.ring(k.x, k.y, (255, 220, 120), 14, 0.35)
                self.offer("orb")
            elif k.kind == "chest" and d < 9:
                k.dead = True
                self.open_chest(k)
            elif k.kind == "portal" and d < 6 and k.t > 0.8:
                if self.fi >= FLOORS - 1:
                    self.win()
                else:
                    self.sfx("clear", 0.7)
                    self.offer("floor")
                return
            elif k.kind == "weapon" and d < 8:
                if len(p.weapons) < 2:
                    self.take_weapon(k)
                elif d < nd:
                    near, nd = k, d
            elif k.kind == "shop" and d < 12 and d < nd:
                near, nd = k, d
        if near is not None:
            if near.kind == "weapon":
                self.prompt = (near.x, near.y - 8, f"e: swap for {WEAPONS[near.val]['name']}")
            else:
                kind, val = near.val
                self.prompt = (near.x, near.y - 10, f"e: {shop_label(kind, val)}  {near.price}●")
            if it.interact:
                if near.kind == "weapon":
                    self.take_weapon(near)
                else:
                    self.buy(near)
        room.pickups = [k for k in room.pickups if not k.dead]

    def take_weapon(self, k):
        p = self.player
        if len(p.weapons) >= 2:
            old = p.weapons[1]
            p.weapons[1] = k.val
            k.val, k.t = old, 0.0
        else:
            p.weapons.append(k.val)
            k.dead = True
        p.wi = 1
        p.beam = None
        self.text(p.x, p.y - 9, WEAPONS[p.weapons[1]]["name"] + "!", CYAN_LIT, 1.2, 8)
        self.sfx("coin", 0.7)

    def open_chest(self, k):
        r = sub_rng(self.seed, "chest", self.fi, self.pos)
        have = set(self.player.weapons)
        spare = [w for w in WEAPON_ORDER if w not in have]
        self.ring(k.x, k.y, GOLD, 16, 0.4)
        self.spark(k.x, k.y, GOLD_LIT, 14, 50, 0.5)
        self.sfx("coin", 0.8)
        room = self.cur()
        if spare and r.random() < 0.6:
            room.pickups.append(Pickup("weapon", k.x, k.y + 2, r.choice(spare)))
        else:
            room.pickups.append(Pickup("orb", k.x, k.y + 2))
        for _ in range(4):
            c = Pickup("coin", k.x, k.y)
            a = r.uniform(0, 6.283)
            c.vx, c.vy = math.cos(a) * 40, math.sin(a) * 40
            room.pickups.append(c)

    def buy(self, k):
        p = self.player
        kind, val = k.val
        if p.coins < k.price:
            self.text(k.x, k.y - 12, f"need {k.price - p.coins} more", (255, 120, 120))
            self.sfx("bonk", 0.5, 0.2)
            return
        if kind == "heart" and p.hp >= p.maxhp:
            self.text(k.x, k.y - 12, "already healthy", DIM)
            return
        p.coins -= k.price
        k.dead = True
        self.ring(k.x, k.y, GOLD, 14, 0.35)
        self.sfx("coin", 0.8)
        if kind == "heart":
            p.hp = min(p.maxhp, p.hp + 4)
        elif kind == "maxhp":
            p.maxhp += 2
            p.hp += 2
        elif kind == "weapon":
            self.cur().pickups.append(Pickup("weapon", k.x, k.y, val))
        elif kind == "upgrade":
            self.offer("shop")

    def win(self):
        self.won = True
        self.mode = "won"
        self.event_log.append("won the run")

    def update_fx(self, dt):
        keep = []
        for q in self.parts:
            q[4] += dt
            if q[4] >= q[5]:
                continue
            k = max(0.0, 1 - q[8] * dt)
            q[2] *= k
            q[3] = q[3] * k + q[9] * dt
            q[0] += q[2] * dt
            q[1] += q[3] * dt
            keep.append(q)
        self.parts = keep[-600:]
        self.rings = [r for r in self.rings if self._age(r, dt)]
        self.lights = [r for r in self.lights if self._age(r, dt)]
        self.marks = [r for r in self.marks if self._age(r, dt)]
        self.texts = [r for r in self.texts if self._age(r, dt, 4, 5)]
        self.booms = [b for b in self.booms if self._age(b, dt, 2, 3, 0.42)]

    @staticmethod
    def _age(r, dt, ti=2, di=3, scale=None):
        r[ti] += dt
        return r[ti] < (r[di] * scale if scale else r[di])


def seg_dist(px, py, x0, y0, x1, y1):
    dx, dy = x1 - x0, y1 - y0
    L = dx * dx + dy * dy
    t = 0.0 if L == 0 else clamp(((px - x0) * dx + (py - y0) * dy) / L, 0.0, 1.0)
    return math.hypot(px - x0 - dx * t, py - y0 - dy * t)


def shop_label(kind, val):
    return {"heart": "heal 4", "upgrade": "an upgrade", "maxhp": "+2 max health"}.get(
        kind, WEAPONS[val]["name"] if val else kind)


# ------------------------------------------------------------------------------ enemy AI
# Each takes (game, enemy, dt). e.cd counts down to the next attack; the renderer makes an
# enemy glow during its last 0.35 s so every volley is telegraphed.

def toward(e, x, y, speed):
    dx, dy = x - e.x, y - e.y
    d = math.hypot(dx, dy) or 1.0
    return dx / d * speed, dy / d * speed, d


def ai_fly(g, e, dt):
    p, r = g.player, g.rng
    e.st -= dt
    if e.st <= 0 or "tx" not in e.data:
        a = r.uniform(0, 6.283)
        rad = r.uniform(30, 55)
        gx = clamp(p.x + math.cos(a) * rad, g.geo.x0 + 8, g.geo.x1 - 8)
        gy = clamp(p.y + math.sin(a) * rad * 0.7, g.geo.y0 + 6, g.geo.y1 - 8)
        e.data["tx"], e.data["ty"], e.st = gx, gy, r.uniform(1.5, 3.0)
    vx, vy, d = toward(e, e.data["tx"], e.data["ty"], 16 if g.fi else 12)
    if d < 3:
        vx = vy = 0.0
    if g.walk(e, vx, vy + math.sin(e.t * 5) * 6, dt):
        e.st = 0
    e.face = 1 if p.x > e.x else -1
    e.cd -= dt
    if e.cd <= 0:
        e.cd = r.uniform(1.8, 2.5) * g.fire_mult()
        a = g.aim(e.x, e.y) + r.uniform(-0.25, 0.25)
        n = 3 if g.fi == 0 else 4 if g.fi < 3 else 6
        n0 = len(g.eb)
        g.efan(e.x + e.face * 3, e.y + 1, a, n, 0.2 * n / 3 + 0.1, 34, "orb", r=1.8)
        for b in g.eb[n0:]:
            b.kind = "fly"
        g.sfx("attack", 0.3, 0.2)


def ai_stinger(g, e, dt):
    p, r = g.player, g.rng
    vx, vy, d = toward(e, p.x, p.y, 26)
    if d < 28:
        side = 1 if math.sin(e.t * 0.7) > 0 else -1
        vx, vy = -vy * 0.5 * side, vx * 0.5 * side
    g.walk(e, vx, vy, dt)
    want = math.atan2(p.y - e.y, p.x - e.x)
    da = (want - e.ang + math.pi) % (2 * math.pi) - math.pi
    e.ang += clamp(da, -4 * dt, 4 * dt)
    e.cd -= dt
    if e.cd <= 0:
        e.cd = r.uniform(1.2, 1.6) * g.fire_mult()
        shots = (0.0,) if g.fi < 6 else (-0.12, 0.12)
        for s in shots:
            b = g.eshoot(e.x + math.cos(e.ang) * 4, e.y + math.sin(e.ang) * 4, e.ang + s + r.uniform(-0.08, 0.08),
                         60, "sting", r=1.4)
            if b:
                b.kind = "stinger"
        g.sfx("attack", 0.25, 0.2)


def ai_turret(g, e, dt):
    p, r = g.player, g.rng
    e.ang = math.atan2(p.y - e.y, p.x - e.x)
    burst = e.data.get("burst", 0)
    if burst:
        e.data["bt"] -= dt
        if e.data["bt"] <= 0:
            e.data["bt"] = 0.09
            e.data["burst"] = burst - 1
            rot = e.data.get("rot", 0.0) + 0.27
            e.data["rot"] = rot
            for k in range(2):
                b = g.eshoot(e.x, e.y, rot + k * math.pi, 30, "orb", r=1.8)
                if b:
                    b.kind = "turret"
        return
    e.cd -= dt
    if e.cd <= 0:
        e.cd = r.uniform(2.4, 3.0) * g.fire_mult()
        biome = g.fi // 3
        rot = e.data.get("rot", 0.0) + 0.3
        e.data["rot"] = rot
        if biome == 1:
            e.data["burst"], e.data["bt"] = 12, 0.0
        else:
            n = 12 if biome == 0 else 14
            n0 = len(g.eb)
            g.ering(e.x, e.y, n, 27, "orb", off=rot, r=1.8)
            if biome == 2:
                g.ering(e.x, e.y, n, 20, "orb", off=rot + math.pi / n, r=1.8)
            for b in g.eb[n0:]:
                b.kind = "turret"
        g.sfx("attack", 0.3, 0.2)


def ai_sniper(g, e, dt):
    p, r = g.player, g.rng
    vx, vy, d = toward(e, p.x, p.y, 20)
    if e.state == "aim":
        e.st -= dt
        vx = vy = 0.0
        if e.st <= 0:
            a = e.data["lock"]
            b = g.eshoot(e.x, e.y, a, 100, "needle", r=1.3)
            if b:
                b.kind = "sniper"
            for s in (-0.35, 0.35):
                b = g.eshoot(e.x, e.y, a + s, 30, "orb", r=1.6)
                if b:
                    b.kind = "sniper"
            e.state, e.cd = "move", r.uniform(2.2, 2.8) * g.fire_mult()
            g.sfx("shoot", 0.3, 0.2)
        elif e.st < 0.25 and "locked" not in e.data:
            e.data["locked"] = True
            e.data["lock"] = g.aim(e.x, e.y)
            for ln in g.lines:
                if ln.get("owner") is e:
                    ln["track"] = False
                    ln["ang"] = e.data["lock"]
    else:
        if d < 45:
            vx, vy = -vx, -vy
        elif d < 70:
            side = 1 if (e.t // 2) % 2 else -1
            vx, vy = -vy * side, vx * side
        if g.walk(e, vx, vy, dt):
            e.t += 1.0
        e.cd -= dt
        if e.cd <= 0:
            e.state, e.st = "aim", 0.8
            e.data.pop("locked", None)
            e.data["lock"] = g.aim(e.x, e.y)
            g.lines.append({"x": e.x, "y": e.y, "ang": e.data["lock"], "t": 0.0, "dur": 0.8,
                            "col": BULLET_COL["sniper"], "owner": e, "follow": True, "track": True})
    e.face = 1 if p.x > e.x else -1


def ai_blob(g, e, dt, small=False):
    p, r = g.player, g.rng
    e.st -= dt
    if e.state == "hop":
        if g.walk(e, e.vx, e.vy, dt) or e.st <= 0:
            e.state, e.st = "rest", (0.45 if small else 0.75)
            g.dust(e.x, e.y + 3, (110, 170, 90))
    elif e.st <= 0:
        vx, vy, _ = toward(e, p.x + r.uniform(-12, 12), p.y + r.uniform(-8, 8), 44 if small else 34)
        e.vx, e.vy = vx, vy
        e.state, e.st = "hop", 0.35
    e.face = 1 if p.x > e.x else -1
    e.cd -= dt
    if e.cd <= 0:
        e.cd = r.uniform(2.2, 2.8) * g.fire_mult() * (1.6 if small else 1)
        n0 = len(g.eb)
        if small:
            g.eshoot(e.x, e.y, g.aim(e.x, e.y), 30, "orb", r=1.5)
        else:
            g.efan(e.x, e.y, g.aim(e.x, e.y), 4, 0.6, 30, "orb", r=2.0)
        for b in g.eb[n0:]:
            b.kind = "blob"
        g.sfx("attack", 0.25, 0.2)


def ai_blobling(g, e, dt):
    ai_blob(g, e, dt, small=True)


def ai_dasher(g, e, dt):
    p, r = g.player, g.rng
    if e.state == "wind":
        e.st -= dt
        if e.st <= 0:
            e.state, e.st = "dash", 0.5
            a = e.data["lock"]
            e.vx, e.vy = math.cos(a) * 135, math.sin(a) * 135
            e.data["drop"] = 0.0
            g.sfx("swoosh", 0.5, 0.1)
    elif e.state == "dash":
        e.st -= dt
        e.data["drop"] -= dt
        if e.data["drop"] <= 0:
            e.data["drop"] = 0.07
            b = g.eshoot(e.x, e.y, r.uniform(0, 6.283), 9, "mine", r=1.6, life=2.4, acc=-0.6)
            if b:
                b.kind = "dasher"
        if g.walk(e, e.vx, e.vy, dt) or e.st <= 0:
            if e.st > 0:  # hit a wall: a burst and a stagger
                n0 = len(g.eb)
                g.ering(e.x, e.y, 10, 30, "orb", off=r.uniform(0, 1), r=1.8)
                for b in g.eb[n0:]:
                    b.kind = "dasher"
                g.shake(0.4, 0.15)
                g.dust(e.x, e.y, (200, 150, 110), 4)
            e.state, e.st, e.cd = "stun", 0.6, r.uniform(2.2, 3.0) * g.fire_mult()
    elif e.state == "stun":
        e.st -= dt
        if e.st <= 0:
            e.state = "idle"
    else:
        e.st -= dt
        if e.st <= 0 or "tx" not in e.data:
            e.data["tx"] = clamp(e.x + r.uniform(-30, 30), g.geo.x0 + 8, g.geo.x1 - 8)
            e.data["ty"] = clamp(e.y + r.uniform(-20, 20), g.geo.y0 + 8, g.geo.y1 - 8)
            e.st = r.uniform(1.0, 2.0)
        vx, vy, d = toward(e, e.data["tx"], e.data["ty"], 12)
        if d > 2:
            g.walk(e, vx, vy, dt)
        e.cd -= dt
        if e.cd <= 0:
            e.state, e.st = "wind", 0.55
            e.data["lock"] = g.aim(e.x, e.y)
            g.lines.append({"x": e.x, "y": e.y, "ang": e.data["lock"], "t": 0.0, "dur": 0.55,
                            "col": BULLET_COL["dasher"], "owner": e, "follow": True, "len": 70})
    e.face = 1 if (e.vx if e.state == "dash" else p.x - e.x) > 0 else -1


def ai_brute(g, e, dt):
    p, r = g.player, g.rng
    vx, vy, d = toward(e, p.x, p.y, 12)
    if e.state == "wind":
        e.st -= dt
        if e.st <= 0:
            a = g.aim(e.x, e.y)
            for i in range(7):
                b = g.eshoot(e.x, e.y + 1, a + (i - 3) * 0.17, 30 + (i % 3) * 8, "orb", r=2.1)
                if b:
                    b.kind = "brute"
            if g.fi >= 7:
                e.data["second"] = 0.25
            e.state, e.cd = "walk", r.uniform(2.0, 2.5) * g.fire_mult()
            g.shake(0.3, 0.1)
            g.sfx("boom", 0.35, 0.15)
    else:
        if d > 28:
            g.walk(e, vx, vy, dt)
        e.cd -= dt
        if e.cd <= 0:
            e.state, e.st = "wind", 0.4
    sec = e.data.get("second")
    if sec is not None:
        sec -= dt
        e.data["second"] = sec
        if sec <= 0:
            del e.data["second"]
            a = g.aim(e.x, e.y)
            for i in range(6):
                b = g.eshoot(e.x, e.y + 1, a + (i - 2.5) * 0.17, 36, "orb", r=2.1)
                if b:
                    b.kind = "brute"
    e.face = 1 if p.x > e.x else -1


def ai_summoner(g, e, dt):
    p, r = g.player, g.rng
    vx, vy, d = toward(e, p.x, p.y, 15)
    if d < 60:
        vx, vy = -vx, -vy
    else:
        vx, vy = vy * 0.5, -vx * 0.5
    geo = g.geo
    if min(e.x - geo.x0, geo.x1 - e.x) < 16 or min(e.y - geo.y0, geo.y1 - e.y) < 12:
        cx, cy, _ = toward(e, geo.W / 2, (geo.y0 + geo.y1) / 2, 15)  # never cornered
        vx, vy = vx * 0.3 + cx, vy * 0.3 + cy
    if g.walk(e, vx, vy + math.sin(e.t * 3) * 4, dt):
        e.t += 2
    e.cd -= dt
    if e.cd <= 0:
        e.cd = r.uniform(3.2, 4.0) * g.fire_mult()
        gn = sum(1 for o in g.enemies if o.kind == "gnat" and not o.dead)
        if gn < 6:
            for s in (-1, 1):
                gnat = g.add_enemy("gnat", e.x + 6 * s, e.y + 2, 1.0, 0.35)
                gnat.kx = 30 * s
        n0 = len(g.eb)
        g.ering(e.x, e.y, 8, 22, "orb", off=e.t, r=1.8, turn=0.6)
        for b in g.eb[n0:]:
            b.kind = "summoner"
        g.sfx("attack", 0.3, 0.2)
    e.face = 1 if p.x > e.x else -1


def ai_gnat(g, e, dt):
    p = g.player
    vx, vy, _ = toward(e, p.x + math.sin(e.t * 4) * 8, p.y + math.cos(e.t * 3) * 6, 32)
    g.walk(e, vx, vy, dt)
    e.face = 1 if vx > 0 else -1


AI = {"fly": ai_fly, "stinger": ai_stinger, "turret": ai_turret, "sniper": ai_sniper, "blob": ai_blob,
      "blobling": ai_blobling, "dasher": ai_dasher, "brute": ai_brute, "summoner": ai_summoner,
      "gnat": ai_gnat}


# ------------------------------------------------------------------------------ bosses
class Brain:
    """A boss: three phases (66% and 33% health), each a deck of attack patterns. Attacks are
    generators yielding seconds to wait, so a pattern reads top to bottom."""

    def __init__(self, g, e):
        self.g, self.e, self.phase, self.gen, self.wait, self.deck = g, e, 0, None, 1.2, []
        self.home = (g.geo.W / 2, g.geo.y0 + 18)
        self.tx, self.ty, self.retarget = self.home[0], self.home[1], 0.0

    def col(self):
        return BULLET_COL[self.e.kind]

    def update(self, dt):
        e, g = self.e, self.g
        frac = e.hp / e.maxhp
        ph = 0 if frac > 0.66 else 1 if frac > 0.33 else 2
        if ph > self.phase:
            self.phase, self.gen, self.deck, self.wait = ph, None, [], 1.8
            e.inv = 1.6
            e.data["roar"] = g.time
            g.clear_bullets()
            g.beams, g.lines = [], []
            g.shake(1.2, 0.5)
            g.freeze = 6
            g.ring(e.x, e.y, self.col(), 50, 0.6)
            g.text(e.x, e.y - 16, f"PHASE {ph + 1}", self.col(), 1.6, 6)
            g.sfx("bigboom", 0.7)
            return
        self.move(dt)
        self.wait -= dt
        guard = 0
        while self.wait <= 0 and guard < 8:
            guard += 1
            if self.gen is None:
                if not self.deck:
                    self.deck = list(self.attacks()[self.phase])
                    g.rng.shuffle(self.deck)
                self.gen = getattr(self, "a_" + self.deck.pop())()
            try:
                self.wait += next(self.gen)
            except StopIteration:
                self.gen = None
                self.wait += 0.4 - 0.1 * self.phase

    def tele(self, dur):
        self.e.data["charge"] = (self.g.time, dur)
        self.g.sfx("attack", 0.5, 0.3)
        yield dur

    def shots(self, n0, kind=None):
        for b in self.g.eb[n0:]:
            b.kind = kind or self.e.kind

    def go(self, speed, dt):
        e = self.e
        dx, dy = self.tx - e.x, self.ty - e.y
        d = math.hypot(dx, dy)
        if d > 0.5:
            s = min(speed * dt, d)
            e.x += dx / d * s
            e.y += dy / d * s
            e.vx = dx / d * speed

    # ---- shared patterns
    def a_ring_gap(self):
        g, e = self.g, self.e
        yield from self.tele(0.6)
        first = e.kind == "boss1"  # the first boss teaches the patterns, so it is sparser
        for i in range((3 if first else 4) + self.phase):
            n0 = len(g.eb)
            gap = g.aim(e.x, e.y) + (0.6 if i % 2 else -0.6) * (self.phase > 0)
            g.ering(e.x, e.y, 30 if first else 36, 28, "orb", off=i * 0.1, gap=gap, gapw=0.32, r=1.9)
            self.shots(n0)
            g.sfx("attack", 0.4, 0.1)
            yield 0.8 - 0.1 * self.phase
        yield 0.5

    def a_volley(self):
        g, e = self.g, self.e
        yield from self.tele(0.5)
        for i in range(4 + self.phase):
            n0 = len(g.eb)
            n = (5 if e.kind == "boss1" else 7) + 2 * (self.phase > 0)
            g.efan(e.x, e.y + 3, g.aim(e.x, e.y), n, 0.18 * n, 40, "orb", r=1.9)
            self.shots(n0)
            g.sfx("attack", 0.35, 0.1)
            yield 0.34 - 0.04 * self.phase
        yield 0.7

    def a_spiral(self):
        g, e = self.g, self.e
        yield from self.tele(0.4)
        arms = (2 if e.kind == "boss1" else 3) + self.phase
        spin = 0.21 if self.e.kind != "boss3" else 0.17
        rot = g.rng.uniform(0, 6.283)
        for i in range(34):
            n0 = len(g.eb)
            for k in range(arms):
                g.eshoot(e.x, e.y, rot + i * spin + k * 2 * math.pi / arms, 33, "orb", r=1.8)
                if self.phase == 2 and e.kind != "boss1":
                    g.eshoot(e.x, e.y, -rot - i * spin + k * 2 * math.pi / arms, 26, "orb", r=1.6)
            self.shots(n0)
            yield 0.09
        yield 0.8

    def a_flower(self):
        g, e = self.g, self.e
        yield from self.tele(0.5)
        for i in range(8):
            n0 = len(g.eb)
            g.ering(e.x, e.y, 18, 26 if i % 2 else 36, "orb", off=i * 0.11, r=1.8)
            self.shots(n0)
            yield 0.3
        yield 0.7

    def a_summon(self):
        g, e = self.g, self.e
        yield from self.tele(0.6)
        kind = {"boss1": "fly", "boss2": "turret", "boss3": "gnat"}[e.kind]
        n = sum(1 for o in g.enemies if not o.dead and not o.boss)
        want = {"fly": 2, "turret": 1, "gnat": 4}[kind]
        if n < 4:
            for i in range(want):
                a = g.rng.uniform(0, 6.283)
                x = clamp(e.x + math.cos(a) * 24, g.geo.x0 + 10, g.geo.x1 - 10)
                y = clamp(e.y + 14 + math.sin(a) * 10, g.geo.y0 + 10, g.geo.y1 - 12)
                g.add_enemy(kind, x, y, g.D["ehp"] * (1 + 0.16 * g.fi), 0.7)
        yield 1.0

    def a_walls(self):
        """Rows of bullets sweep across the room with a gap to slip through."""
        g, e = self.g, self.e
        geo = g.geo
        yield from self.tele(0.5)
        side = g.rng.choice(("top", "left", "right"))
        gap = g.rng.uniform(0.25, 0.75)
        for i in range(4 + self.phase):
            n0 = len(g.eb)
            gap = clamp(gap + g.rng.uniform(-0.25, 0.25), 0.15, 0.85)
            if side == "top":
                span = geo.x1 - geo.x0
                for x in range(geo.x0 + 2, geo.x1 - 1, 5):
                    if abs((x - geo.x0) / span - gap) > 11 / span:
                        g.eshoot(x, geo.y0 + 1, math.pi / 2, 24, "orb", r=1.7, life=9)
            else:
                span = geo.y1 - geo.y0
                x = geo.x0 + 1 if side == "left" else geo.x1 - 2
                for y in range(geo.y0 + 2, geo.y1 - 1, 4):
                    if abs((y - geo.y0) / span - gap) > 9 / span:
                        g.eshoot(x, y, 0.0 if side == "left" else math.pi, 30, "orb", r=1.7, life=9)
            self.shots(n0)
            g.sfx("attack", 0.3, 0.1)
            yield 1.05 - 0.1 * self.phase
        yield 0.6

    def beam(self, ang, angv, warm, dur, w=3.0, start=6.0):
        self.g.beams.append({"x": self.e.x, "y": self.e.y, "ang": ang, "angv": angv, "t": 0.0, "warm": warm,
                             "dur": dur, "w": w, "col": self.col(), "owner": self.e, "start": start})

    def a_sweep(self):
        g, e = self.g, self.e
        a = g.aim(e.x, e.y)
        sgn = g.rng.choice((-1, 1))
        n = 2 if self.phase < 2 else 3
        for k in range(n):
            self.beam(a + sgn * 1.2 + k * 2 * math.pi / n, -sgn * 0.62, 0.95, 3.4)
        g.sfx("beam", 0.5)
        yield 1.0
        for i in range(3):
            n0 = len(g.eb)
            g.ering(e.x, e.y, 12, 24, "orb", off=i * 0.26, r=1.8)
            self.shots(n0)
            yield 1.1
        yield 0.5

    def a_needles(self):
        g, e = self.g, self.e
        for i in range(3):
            a = g.aim(e.x, e.y)
            for s in (-0.18, 0.0, 0.18):
                g.lines.append({"x": e.x, "y": e.y, "ang": a + s, "t": 0.0, "dur": 0.55, "col": self.col(),
                                "owner": e, "follow": True})
            g.sfx("attack", 0.4, 0.1)
            yield 0.55
            n0 = len(g.eb)
            for s in (-0.18, 0.0, 0.18):
                g.eshoot(e.x, e.y, a + s, 95, "needle", r=1.4)
            self.shots(n0)
            g.sfx("shoot", 0.4)
            yield 0.35
        yield 0.5

    def a_dive(self):
        g, e, p = self.g, self.e, self.g.player
        a = g.aim(e.x, e.y)
        g.lines.append({"x": e.x, "y": e.y, "ang": a, "t": 0.0, "dur": 0.7, "col": self.col(), "owner": e,
                        "follow": True, "len": 90, "wide": True})
        e.data["charge"] = (g.time, 0.7)
        yield 0.7
        e.data["dive"] = (math.cos(a) * 125, math.sin(a) * 125)
        drop = 0
        for i in range(10):
            if drop % 2 == 0:
                b = g.eshoot(e.x, e.y, a + math.pi, 4, "big", r=2.8, life=1.4 + 0.1 * i, acc=-1)
                if b:
                    b.kind = e.kind
                    b.st = "big"
                    e.data.setdefault("bombs", []).append(b)
            drop += 1
            yield 0.05
        e.data.pop("dive", None)
        g.shake(0.6, 0.2)
        yield 0.5
        live = set(map(id, g.eb))
        for b in e.data.pop("bombs", []):  # the eggs still in flight hatch into small rings
            if id(b) in live and not b.dead:
                b.dead = True
                n0 = len(g.eb)
                g.ering(b.x, b.y, 7, 26, "orb", off=g.rng.uniform(0, 1), r=1.6)
                self.shots(n0)
        g.sfx("boom", 0.4)
        yield 0.9

    def a_shards(self):
        g, e = self.g, self.e
        yield from self.tele(0.6)
        n0 = len(g.eb)
        shards = []
        for k in range(6 + 2 * self.phase):
            a = k * 2 * math.pi / (6 + 2 * self.phase) + g.time
            b = g.eshoot(e.x, e.y, a, 50, "big", r=2.6, acc=-1.2, life=6)
            if b:
                shards.append(b)
        self.shots(n0)
        yield 0.9
        live = set(map(id, g.eb))
        for b in shards:  # then they turn and come for you
            if id(b) in live and not b.dead:
                ang = math.atan2(g.player.y - b.y, g.player.x - b.x)
                s = 42 * g.bs()
                b.vx, b.vy, b.acc = math.cos(ang) * s, math.sin(ang) * s, 0.0
        g.sfx("attack", 0.5)
        yield 1.0

    def a_stream(self):
        g, e = self.g, self.e
        yield from self.tele(0.4)
        for i in range(14):
            n0 = len(g.eb)
            a = g.aim(e.x, e.y)
            g.eshoot(e.x, e.y, a + math.sin(i * 0.7) * 0.12, 62, "needle", r=1.4)
            if i % 5 == 4:
                g.efan(e.x, e.y, a, 7, 1.6, 30, "orb", r=1.8)
            self.shots(n0)
            yield 0.07
        yield 0.8

    def a_cross(self):
        g, e = self.g, self.e
        base = g.rng.uniform(0, 1)
        sgn = g.rng.choice((-1, 1))
        for k in range(4):
            self.beam(base + k * math.pi / 2, sgn * 0.5, 1.0, 3.8, 3.0, 8.0)
        g.sfx("beam", 0.5)
        yield 1.2
        for i in range(3):
            n0 = len(g.eb)
            g.efan(e.x, e.y, g.aim(e.x, e.y), 3, 0.3, 40, "orb", r=1.8)
            self.shots(n0)
            yield 1.0
        yield 0.6

    def a_blink(self):
        g, e = self.g, self.e
        geo = g.geo
        e.data["fade"] = (g.time, 0.35, "out")
        yield 0.35
        p = g.player
        for _ in range(12):
            x = g.rng.uniform(geo.x0 + 16, geo.x1 - 16)
            y = g.rng.uniform(geo.y0 + 12, geo.y0 + (geo.y1 - geo.y0) * 0.55)
            if (x - p.x) ** 2 + (y - p.y) ** 2 > 40 ** 2:
                break
        e.x, e.y = x, y
        self.tx, self.ty = x, y
        e.data["fade"] = (g.time, 0.35, "in")
        g.ring(x, y, self.col(), 18, 0.35)
        yield 0.4
        n0 = len(g.eb)
        g.ering(e.x, e.y, 16, 30, "orb", off=g.time, r=1.8)
        self.shots(n0)
        yield 0.5

    # ---- per boss
    def attacks(self):
        k = self.e.kind
        if k == "boss1":
            return (("volley", "ring_gap", "volley", "summon"),
                    ("spiral", "ring_gap", "volley", "summon", "dive"),
                    ("flower", "dive", "spiral", "volley", "dive"))
        if k == "boss2":
            return (("ring_gap", "needles", "ring_gap", "spiral"),
                    ("sweep", "ring_gap", "needles", "sweep", "summon"),
                    ("walls", "sweep", "blink", "walls", "needles", "spiral"))
        return (("spiral", "stream", "shards", "ring_gap"),
                ("cross", "shards", "summon", "spiral", "stream"),
                ("flower", "cross", "walls", "shards", "stream", "spiral"))

    def move(self, dt):
        e, g = self.e, self.g
        geo = g.geo
        dive = e.data.get("dive")
        if dive:
            e.x, e.y, hx, hy = g.move_body(e.x, e.y, dive[0] * dt, dive[1] * dt, e.r * 0.8, e.r * 0.6)
            if hx or hy:
                e.data.pop("dive")
            self.tx, self.ty = e.x, e.y
            return
        t = g.time
        if e.kind == "boss1":
            self.tx = geo.W / 2 + math.sin(t * 0.55) * (geo.x1 - geo.x0) * (0.26 + 0.06 * self.phase)
            self.ty = geo.y0 + 18 + math.sin(t * 1.1) * (5 + 6 * self.phase)
            self.go(26 + 10 * self.phase, dt)
        elif e.kind == "boss2":
            if self.phase < 2:
                self.tx, self.ty = geo.W / 2, geo.y0 + 18 + math.sin(t * 1.3) * 2
            self.go(20, dt)
        else:
            self.retarget -= dt
            if self.retarget <= 0:
                self.retarget = 3.0 - 0.6 * self.phase
                self.tx = g.rng.uniform(geo.x0 + 22, geo.x1 - 22)
                self.ty = g.rng.uniform(geo.y0 + 14, geo.y0 + (geo.y1 - geo.y0) * 0.5)
            self.go(16 + 8 * self.phase, dt)
        e.face = 1 if g.player.x > e.x else -1


# ------------------------------------------------------------------------------ autopilot
class Autopilot:
    """Plays for --demo, the gallery and smoke tests: dodges the bullets it sees coming,
    keeps its distance, shoots the nearest enemy, sweeps up coins and walks the floor."""

    def __init__(self, g):
        self.g, self.side, self.side_t, self.path, self.path_for = g, 1, 0.0, [], None
        self.stuck, self.last, self.skip, self.fight_t = 0.0, (0.0, 0.0), {}, 0.0

    def tiles_path(self, sx, sy, goal):
        g = self.g
        geo, room = g.geo, g.cur()
        start = (int(clamp((sx - BX) // T, 0, geo.iw - 1)), int(clamp((sy - TOP) // T, 0, geo.ih - 1)))
        blocked = set(room.pillars)
        for bx, by, _ in room.barrels:
            blocked.add((int((bx - BX) // T), int((by - TOP) // T)))
        blocked.discard(goal)
        prev, todo = {start: None}, [start]
        while todo:
            c = todo.pop(0)
            if c == goal:
                break
            for dx, dy in DIRS4.values():
                q = (c[0] + dx, c[1] + dy)
                if 0 <= q[0] < geo.iw and 0 <= q[1] < geo.ih and q not in blocked and q not in prev:
                    prev[q] = c
                    todo.append(q)
        if goal not in prev:
            return []
        out, c = [], goal
        while c is not None:
            out.append(geo.tile_px(*c))
            c = prev[c]
        return out[::-1]

    def clear_shot(self, x0, y0, x1, y1):
        n = int(math.hypot(x1 - x0, y1 - y0) / 3) + 1
        for i in range(1, n):
            t = i / n
            if self.g.is_solid(x0 + (x1 - x0) * t, y0 + (y1 - y0) * t):
                return False
        return True

    def next_room_dir(self):
        """Door toward the nearest unvisited room, else toward the exit or boss."""
        g = self.g
        rooms = g.rooms
        start = g.pos
        prev, todo = {start: None}, [start]
        while todo:
            c = todo.pop(0)
            for q in rooms[c].doors.values():
                if q not in prev:
                    prev[q] = c
                    todo.append(q)
        order = [c for c in prev if c != start]  # BFS order: nearest first
        target = next((c for c in order if not rooms[c].visited), None)
        if target is None:
            target = next((c for c in order if rooms[c].kind in ("exit", "boss")), None)
        if target is None:
            return None
        c = target
        while prev.get(c) not in (start, None):
            c = prev[c]
        for d, q in rooms[start].doors.items():
            if q == c:
                return d
        return None

    def steer_to(self, x, y):
        g, p = self.g, self.g.player
        geo = g.geo
        key = (int(x) // T, int(y) // T, g.pos)
        if key != self.path_for or not self.path:
            gx = int(clamp((x - BX) // T, 0, geo.iw - 1))
            gy = int(clamp((y - TOP) // T, 0, geo.ih - 1))
            self.path, self.path_for = self.tiles_path(p.x, p.y + 2, (gx, gy)), key
        while self.path and math.hypot(self.path[0][0] - p.x, self.path[0][1] - p.y - 2) < 4:
            self.path.pop(0)
        tx, ty = self.path[0] if len(self.path) > 1 else (x, y)
        dx, dy = tx - p.x, ty - p.y - 1
        d = math.hypot(dx, dy) or 1
        return dx / d, dy / d

    def think(self, dt):
        g, p = self.g, self.g.player
        it = Intent()
        if g.mode == "choice":
            if g.time - g.choice_t > 1.2:
                it.interact = True
            return it
        if g.mode != "play" or not p.alive or g.trans:
            return it
        geo, room = g.geo, g.cur()
        foes = [e for e in g.enemies if not e.dead and e.spawn <= 0 and e.data.get("dying") is None]
        mx = my = 0.0
        chasing = False
        if foes:
            tgt = min(foes, key=lambda e: (e.x - p.x) ** 2 + (e.y - p.y) ** 2 - (900 if e.boss else 0))
            dx, dy = tgt.x - p.x, tgt.y - p.y
            d = math.hypot(dx, dy) or 1
            it.aim, it.fire = math.atan2(dy, dx), True
            want = 50 if tgt.boss else 40
            self.side_t -= dt
            if self.side_t <= 0:
                self.side, self.side_t = -self.side, g.rng.uniform(1.2, 2.6)
            if self.clear_shot(p.x, p.y + 1, tgt.x, tgt.y) and self.fight_t < 25:
                rad = (d - want) / 20
                mx, my = dx / d * rad - dy / d * 0.8 * self.side, dy / d * rad + dx / d * 0.8 * self.side
                if tgt.boss and p.y < tgt.y + 25:
                    my += 1.0
            else:  # a pillar is in the way: walk round it
                mx, my = self.steer_to(tgt.x, tgt.y)
                chasing = True
        elif g.sub is None:
            coins = [k for k in room.pickups if k.kind in ("coin", "heart", "chest", "orb", "weapon")
                     and not (k.kind == "heart" and p.hp >= p.maxhp)
                     and not (k.kind == "weapon" and len(p.weapons) >= 2)]
            portal = next((k for k in room.pickups if k.kind == "portal"), None)
            shop = [k for k in room.pickups if k.kind == "shop" and k.price <= p.coins
                    and (k.val[0] != "heart" or p.hp < p.maxhp - 3)]
            coins = [k for k in coins if self.skip.get(k, 0) < 4]
            if coins:
                k = min(coins, key=lambda k: (k.x - p.x) ** 2 + (k.y - p.y) ** 2)
                mx, my = self.steer_to(k.x, k.y)
                if self.stuck > 0.3:  # give up on pickups it can't reach
                    self.skip[k] = self.skip.get(k, 0) + dt * 4
            elif shop:
                k = shop[0]
                mx, my = self.steer_to(k.x, k.y)
                if math.hypot(k.x - p.x, k.y - p.y) < 8:
                    it.interact = True
            elif g.lock_pending:
                mx, my = self.steer_to(geo.W / 2, (geo.y0 + geo.y1) / 2)
            elif portal and (self.next_room_dir() is None or all(r.visited for r in g.rooms.values())):
                mx, my = self.steer_to(portal.x, portal.y)
            else:
                d = self.next_room_dir()
                if d is None and portal:
                    mx, my = self.steer_to(portal.x, portal.y)
                elif d is not None:
                    x0, y0, x1, y1 = geo.door[d]
                    tx, ty = (x0 + x1) / 2, (y0 + y1) / 2
                    inner = {"up": (tx, geo.y0 + 3), "down": (tx, geo.y1 - 4), "left": (geo.x0 + 3, ty),
                             "right": (geo.x1 - 3, ty)}[d]
                    if math.hypot(inner[0] - p.x, inner[1] - p.y - 1) < 6:
                        mx, my = DIRS4[d]
                    else:
                        mx, my = self.steer_to(*inner)
        # dodge: push away from bullets that will pass close in the next 0.4 s
        ax = ay = 0.0
        danger = 0.0
        hx, hy = p.x, p.y + 1
        for b in g.eb:
            if b.delay > 0:
                continue
            rx, ry = b.x - hx, b.y - hy
            if rx * rx + ry * ry > 45 * 45:
                continue
            vv = b.vx * b.vx + b.vy * b.vy or 1.0
            tc = clamp(-(rx * b.vx + ry * b.vy) / vv, 0.0, 0.45)
            cx, cy = rx + b.vx * tc, ry + b.vy * tc
            dd = math.hypot(cx, cy)
            lim = b.r + 7
            if dd < lim:
                w = (lim - dd) / lim * (1.4 - tc * 2)
                if dd < 0.5:
                    cx, cy, dd = -b.vy, b.vx, math.hypot(b.vx, b.vy) or 1
                ax -= cx / dd * w
                ay -= cy / dd * w
                danger = max(danger, w)
        for bm in g.beams:
            seg = bm.get("seg")
            if seg and bm["t"] > bm["warm"] - 0.5:
                sx, sy, ex, ey = seg
                if seg_dist(hx, hy, sx, sy, ex, ey) < 14:
                    a = bm["ang"] + math.pi / 2 * (1 if bm["angv"] < 0 else -1)
                    ax += math.cos(a) * 1.5
                    ay += math.sin(a) * 1.5
                    danger = max(danger, 0.8)
        if foes and not chasing:  # in a fight, keep off the walls so dodges have room
            for wx in (geo.x0, geo.x1):
                d = abs(p.x - wx)
                if d < 12:
                    ax += (1 if p.x > wx else -1) * (12 - d) / 12 * 0.8
            for wy in (geo.y0, geo.y1):
                d = abs(p.y - wy)
                if d < 10:
                    ay += (1 if p.y > wy else -1) * (10 - d) / 10 * 0.8
        self.fight_t = self.fight_t + dt if foes and room.locked and room.kind != "boss" else 0.0
        k = 3.0 if self.fight_t < 25 else 1.0  # a long fight: press in rather than kite forever
        mx += ax * k
        my += ay * k
        n = math.hypot(mx, my)
        if n < 0.2 and self.fight_t > 25 and foes:  # dodging and chasing cancelled out: chase
            mx, my = self.steer_to(tgt.x, tgt.y)
            n = 1.0
        if n > 1:
            mx, my = mx / n, my / n
        # in a fight, slide along walls instead of being pinned against them
        if foes and g.box_hits(p.x + mx * 2, p.y + 2.5 + my * 2, 2.5, 2.0):
            if not g.box_hits(p.x + mx * 2, p.y + 2.5, 2.5, 2.0):
                my = 0.0
            elif not g.box_hits(p.x, p.y + 2.5 + my * 2, 2.5, 2.0):
                mx = 0.0
        it.mx, it.my = mx, my
        if danger > 0.9 and p.charges > 0 and p.dash_t <= 0:
            it.dash = True
        moved = math.hypot(p.x - self.last[0], p.y - self.last[1])
        self.last = (p.x, p.y)
        self.stuck = self.stuck + dt if moved < 0.05 and n > 0.3 else 0.0
        if self.stuck > 0.6:
            it.mx, it.my = -my, mx
            self.path = []
        return it


# ------------------------------------------------------------------------------ look
# Presentation only: everything below reads the game and never changes it. Pixels are
# half-block cells ("▀", fg = top pixel, bg = bottom). A room's static art (floor, walls,
# decals) is cached as pixel rows plus the cells they compose to; each frame copies the
# rows, draws the moving things on top and recomposes only the cell rows it touched.

def px_cells(top, bot):
    return [(" ", None, t) if t == b else ("▀", t, b) for t, b in zip(top, bot)]


def hash01(x, y, k=0):
    h = (x * 374761393 + y * 668265263 + k * 2147483647) & 0xFFFFFFFF
    h = ((h ^ (h >> 13)) * 1274126177) & 0xFFFFFFFF
    return (h & 0xFFFF) / 65536.0


def sheet_textures(art, bio):
    """(cap, face) texture rows from Srijan's tilesheet, recoloured for the biome; None
    without the sheet."""
    img = art.img.get("tilesheet")
    if not img:
        return None
    _, _, src = img

    def col(p, moss=1.0):
        role = SHEET_ROLE.get((p[0], p[1], p[2]))
        if role and role.startswith("moss"):  # moss stays a hint on the bricks
            return mix(bio["face"][0], biome_role(bio, role), moss)
        return biome_role(bio, role) if role else bio["cap"]
    cap = [[col(src[y][x]) for x in range(1, 47)] for y in range(1, 39)]
    face = [[col(src[y][x], 0.45) for x in range(0, 47)] for y in range(41, 48)]
    return cap, face


def cap_color(tex, bio, x, y):
    if tex:
        cap = tex[0]
        return cap[y % len(cap)][x % len(cap[0])]
    h = hash01(x, y, 3)
    return bio["speck"] if h < 0.06 else bio["cap"]


def face_color(tex, bio, x, j, rows):
    """Brick face pixel at column x, j rows below the face's top edge (of `rows`)."""
    if tex:
        face = tex[1]
        return face[min(len(face) - 1, j + (len(face) - rows))][x % len(face[0])]
    course = j // 2
    if (x + 3 * (course & 1)) % 6 == 0:
        return mul(bio["face"][1], 0.8)
    return bio["face"][(course + x // 6) & 1]


FONT5 = {
    "A": ".###.#...##...#######...##...##...#", "B": "####.#...#####.#...##...##...#####.",
    "C": ".####...##....#....#....#.....####", "D": "####.#...##...##...##...##...#####.",
    "E": "######....####.#....#....#....#####", "F": "######....####.#....#....#....#....",
    "G": ".####....#....#..###...##...#.####.", "H": "#...##...#######...##...##...##...#",
    "I": "#####..#....#....#....#....#..#####", "K": "#...##..#.###..#..#.#...##...##...#",
    "L": "#....#....#....#....#....#....#####", "M": "#...###.###.#.##...##...##...##...#",
    "N": "#...###..##.#.##..###...##...##...#", "O": ".###.#...##...##...##...##...#.###.",
    "P": "####.#...##...#####.#....#....#....", "R": "####.#...##...#####.#..#.#...##...#",
    "S": ".#####....#.....###.....#....######", "T": "#####..#....#....#....#....#....#..",
    "U": "#...##...##...##...##...##...#.###.", "V": "#...##...##...##...#.#.#..#.#...#..",
    "W": "#...##...##...##.#.##.#.###.###...#", "Y": "#...##...#.#.#...#....#....#....#..",
    "!": "..#....#....#....#....#.........#..", " ": "." * 35, "-": "." * 15 + "#####" + "." * 15,
}
FONT5 = {k: [v[i * 5:i * 5 + 5].ljust(5, ".") for i in range(7)] for k, v in FONT5.items()}


def word_px(word, L=1):
    """Pixel set {(x, y)} for word in the 5x7 font scaled by L, letters 1 pixel apart."""
    out, x = set(), 0
    for ch in word:
        g = FONT5.get(ch, FONT5[" "])
        for j, row in enumerate(g):
            for i, c in enumerate(row):
                if c == "#":
                    for a in range(L):
                        for b in range(L):
                            out.add((x + i * L + a, j * L + b))
        x += 6 * L
    return out, x - L, 7 * L


class Stamps:
    """Precomputed bullet, light and ring pixel offsets."""

    def __init__(self, sprites):
        self.sprites = sprites
        self.cache = {}

    def orb(self, r, col, q):
        """Round glowing bullet: (solid [(dx, dy, rgb)], halo [(dx, dy, r, g, b)]), for the
        sub-pixel phase q = (qx, qy) in halves."""
        key = ("orb", round(r * 4), col, q)
        s = self.cache.get(key)
        if s is None:
            cx, cy = 0.25 + 0.5 * q[0], 0.25 + 0.5 * q[1]
            core, rim = mix(col, WHITE, 0.82), mix(col, WHITE, 0.18)
            solid, halo = [], []
            R = int(r + 4)
            for dy in range(-R, R + 1):
                for dx in range(-R, R + 1):
                    d = math.hypot(dx + 0.5 - cx, dy + 0.5 - cy)
                    if d <= r * 0.5:
                        solid.append((dx, dy, core))
                    elif d <= r:
                        solid.append((dx, dy, rim if d < r * 0.78 else col))
                    elif d <= r + 2.6:
                        k = 0.55 * (1 - (d - r) / 2.6) ** 1.5
                        halo.append((dx, dy, int(col[0] * k), int(col[1] * k), int(col[2] * k)))
            s = self.cache[key] = (solid, halo)
        return s

    def streak(self, length, width, col, k16, core=WHITE, glow=0.5):
        """Elongated bullet along direction k16 (of 16), centred on the bullet."""
        key = ("streak", length, width, col, k16, core, glow)
        s = self.cache.get(key)
        if s is None:
            a = k16 * math.pi / 8
            ux, uy = math.cos(a), math.sin(a)
            solid, halo = [], []
            R = int(length + width + 3)
            for dy in range(-R, R + 1):
                for dx in range(-R, R + 1):
                    px, py = dx + 0.5, dy + 0.5
                    t = clamp(px * ux + py * uy, -length / 2, length / 2)
                    d = math.hypot(px - ux * t, py - uy * t)
                    if d <= width * 0.55:
                        solid.append((dx, dy, core if t > -length * 0.2 else mix(core, col, 0.5)))
                    elif d <= width:
                        solid.append((dx, dy, col))
                    elif d <= width + 2.2:
                        k = glow * (1 - (d - width) / 2.2) ** 1.5
                        halo.append((dx, dy, int(col[0] * k), int(col[1] * k), int(col[2] * k)))
            s = self.cache[key] = (solid, halo)
        return s

    def sprite_glow(self, name, frame, k16, col, recolor=None):
        """A sprite (rotated to k16 when given) with a soft additive halo of col."""
        key = ("spr", name, frame, k16, col, recolor)
        s = self.cache.get(key)
        if s is None:
            rows = self.sprites.base[name][frame]
            if recolor:
                rows = map_rows(rows, recolor)
            if k16 is not None:
                rows = rotate_rows(rows, k16 * math.pi / 8)
            spr = Sprite(rows)
            solid = list(spr.px)
            have = {(x, y) for x, y, _ in solid}
            halo = []
            for x, y, _ in solid:
                for a in range(-2, 3):
                    for b in range(-2, 3):
                        q = (x + a, y + b)
                        if q not in have:
                            have.add(q)
                            k = 0.42 * (1 - (abs(a) + abs(b)) / 5)
                            halo.append((q[0], q[1], int(col[0] * k), int(col[1] * k), int(col[2] * k)))
            s = self.cache[key] = (solid, halo)
        return s

    def light(self, rad):
        key = ("light", rad)
        s = self.cache.get(key)
        if s is None:
            s = []
            for dy in range(-rad, rad + 1):
                for dx in range(-rad, rad + 1):
                    d = math.hypot(dx, dy) / rad
                    if d < 1:
                        s.append((dx, dy, (1 - d) ** 2))
            self.cache[key] = s
        return s

    def circle(self, r):
        key = ("circle", r)
        s = self.cache.get(key)
        if s is None:
            n = max(8, int(2 * math.pi * r))
            s = sorted({(round(math.cos(i * 2 * math.pi / n) * r), round(math.sin(i * 2 * math.pi / n) * r))
                        for i in range(n)})
            self.cache[key] = s
        return s


def build_room_bg(g, room, sprites, art, tex_cache):
    """The room's static pixels: floor, walls with depth, door frames, decals."""
    geo, bio = g.geo, BIOMES[g.fi // 3]
    W, H = geo.W, geo.H
    key = g.fi // 3
    if key not in tex_cache:
        tex_cache[key] = sheet_textures(art, bio)
    tex = tex_cache[key]
    f0, f1 = bio["floor"]
    rows = [[f1] * W for _ in range(H)]
    cx, cy = W / 2, (geo.y0 + geo.y1) / 2
    for y in range(geo.y0, geo.y1):
        row = rows[y]
        ty, jy = divmod(y - geo.y0, T)
        for x in range(geo.x0, geo.x1):
            tx, jx = divmod(x - geo.x0, T)
            c = f0 if (tx + ty) & 1 else f1
            k = 1.0
            if jx == 0 or jy == 0:
                k = 1.09
            elif jx == T - 1 or jy == T - 1:
                k = 0.86
            k *= 0.97 + 0.06 * hash01(x, y)
            if hash01(tx, ty, 9) < 0.08 and 2 <= jx <= 5 and 2 <= jy <= 5 and hash01(x, y, 4) < 0.25:
                k *= 0.82  # an odd chipped tile
            dx, dy = (x - cx) / (W * 0.62), (y - cy) / (H * 0.62)
            k *= 1.12 - 0.35 * (dx * dx + dy * dy)
            row[x] = mul(c, k)
    # ambient occlusion along the walls; the top wall's face throws a longer shadow
    for y in range(geo.y0, geo.y1):
        for x in range(geo.x0, geo.x1):
            k = 1.0
            dt_ = y - geo.y0
            if dt_ < 5:
                k *= 0.55 + 0.09 * dt_
            for d in (x - geo.x0, geo.x1 - 1 - x, geo.y1 - 1 - y):
                if d < 2:
                    k *= 0.75 + 0.12 * d
            if k < 1:
                rows[y][x] = mul(rows[y][x], k)
    # lamps on the top wall pool light on the floor below
    lamps = [geo.x0 + (geo.x1 - geo.x0) * f for f in (0.16, 0.84)]
    for lx in lamps:
        for y in range(geo.y0, min(geo.y1, geo.y0 + 26)):
            for x in range(int(lx - 22), int(lx + 22)):
                if geo.x0 <= x < geo.x1:
                    d = math.hypot((x - lx) / 22, (y - geo.y0) / 24)
                    if d < 1:
                        rows[y][x] = add(rows[y][x], bio["accent"], 0.07 * (1 - d) ** 2)
    # outer walls: cap with a lit rim on the inner edge, brick face under the top cap
    capH = TOP - 5
    for y in range(H):
        for x in range(W):
            inside_x = geo.x0 <= x < geo.x1
            if y < TOP and (inside_x or y < capH):
                if y < capH:
                    c = cap_color(tex, bio, x, y)
                    if y == capH - 1:
                        c = mix(c, bio["rim"], 0.8)
                    rows[y][x] = c
                else:
                    j = y - capH
                    c = face_color(tex, bio, x, j, 5)
                    rows[y][x] = mul(c, 1.12 - 0.08 * j)
            elif not (geo.y0 <= y < geo.y1 and inside_x):
                c = cap_color(tex, bio, x, y)
                inner = (x == geo.x0 - 1 and geo.y0 <= y < geo.y1 + 1) or (x == geo.x1 and geo.y0 <= y < geo.y1 + 1) \
                    or (y == geo.y1 and geo.x0 - 1 <= x <= geo.x1)
                if inner:
                    c = mix(c, bio["rim"], 0.85)
                elif x == 0 or x == W - 1 or y == H - 1 or y == 0:
                    c = mul(c, 0.7)
                rows[y][x] = c
    for lx in lamps:  # the lamps themselves
        x0 = int(lx)
        for (dx, dy, col) in ((0, 0, WHITE), (-1, 0, bio["accent"]), (1, 0, bio["accent"]),
                              (0, 1, bio["accent"]), (0, -1, mix(bio["accent"], WHITE, 0.5))):
            y = capH + 2 + dy
            if 0 <= x0 + dx < W:
                rows[y][x0 + dx] = col
    # doors: open gaps lead into the dark; frames from the original's door arch
    door = sprites.base["door"][0]
    post = WHITE
    for d in room.doors:
        x0, y0, x1, y1 = geo.door[d]
        for y in range(y0, y1):
            for x in range(x0, x1):
                if d == "up":
                    u = y / TOP
                    c = mix((4, 4, 8), mul(f1, 0.7), u * u)
                elif d == "down":
                    u = (y - geo.y1) / BOT
                    c = mix(mul(f1, 0.7), (4, 4, 8), u)
                elif d == "left":
                    u = x / BX
                    c = mix((4, 4, 8), mul(f1, 0.7), u)
                else:
                    u = (x - geo.x1) / BX
                    c = mix(mul(f1, 0.7), (4, 4, 8), u)
                rows[y][x] = c
        if d in ("up", "down"):
            dh = len(door)
            for j in range(dh):  # the arch's posts, cropped to the wall
                yy = (y1 - dh + j) if d == "up" else (y0 + j)
                if not (y0 <= yy < y1):
                    continue
                for i, c in enumerate(door[j]):
                    if c is not None and (i < 4 or i > 11):
                        rows[yy][x0 + i] = mix(post, bio["rim"], 0.25)
            for x in (x0 - 1, x1):
                for y in range(y0, y1):
                    rows[y][x] = mul(rows[y][x], 0.6)
        else:
            for y in (y0 - 1, y1):
                for x in range(x0, x1):
                    rows[y][x] = mix(post, bio["rim"], 0.25)
    # pillars: the cap rises above its footprint, a brick face below, a shadow on the floor
    for tx, ty in sorted(room.pillars, key=lambda t: (t[1], t[0])):
        x0, y0 = BX + tx * T, TOP + ty * T
        below = (tx, ty + 1) in room.pillars
        for j in range(T + 3):
            y = y0 + j
            if not 0 <= y < H:
                continue
            if j >= T and not below:
                for i in range(T + 1):  # drop shadow
                    if geo.x0 <= x0 + i < geo.x1 and y < geo.y1:
                        rows[y][x0 + i] = mul(rows[y][x0 + i], 0.5 + 0.15 * (j - T))
                continue
            for i in range(T):
                x = x0 + i
                yy = y - 3
                if j < T - 3 or below:
                    c = cap_color(tex, bio, x, yy)
                    if j == 0 and (tx, ty - 1) not in room.pillars:
                        c = mix(c, bio["rim"], 0.9)
                    elif i == 0 and (tx - 1, ty) not in room.pillars:
                        c = mix(c, bio["rim"], 0.45)
                    elif i == T - 1 and (tx + 1, ty) not in room.pillars:
                        c = mul(c, 0.8)
                    if 0 <= yy < H:
                        rows[yy][x] = c
                else:
                    jj = j - (T - 3)
                    c = mul(face_color(tex, bio, x, jj + 1, 5), 1.1 - 0.1 * jj)
                    if 0 <= yy < H:
                        rows[yy][x] = c
            if (tx + 1, ty) not in room.pillars and j < T:
                x = x0 + T
                if geo.x0 <= x < geo.x1 and geo.y0 <= y < geo.y1:
                    rows[y][x] = mul(rows[y][x], 0.7)
    # decals
    for name, frame, flip, x, y in room.decals:
        if name == "splat":
            r = random.Random(frame * 7919 + int(x) * 31 + int(y))
            col = mul(bio["decal"], 1.0)
            for _ in range(10):
                a, d = r.uniform(0, 6.283), r.uniform(0, 4)
                px, py = int(x + math.cos(a) * d), int(y + math.sin(a) * d * 0.7)
                if geo.x0 <= px < geo.x1 and geo.y0 <= py < geo.y1:
                    rows[py][px] = mix(rows[py][px], col, 0.6)
            continue
        if name == "scorch":
            for dy in range(-5, 6):
                for dx in range(-8, 9):
                    d = math.hypot(dx / 8, dy / 5)
                    px, py = int(x + dx), int(y + dy)
                    if d < 1 and geo.x0 <= px < geo.x1 and geo.y0 <= py < geo.y1:
                        rows[py][px] = mul(rows[py][px], 0.45 + 0.5 * d)
            continue
        spr = sprites.get(name, frame, flip, "dark")
        for dx, dy, c in spr.px:
            px, py = int(x) + dx, int(y) + dy
            if geo.x0 <= px < geo.x1 and geo.y0 <= py < geo.y1:
                rows[py][px] = mix(rows[py][px], c, 0.85)
    if room.kind == "start" and g.fi == 0:
        tutorial_decals(rows, geo, bio)
    return rows


TUTORIAL = (("WASD", "MOVE"), ("ARROWS", "SHOOT"), ("SPACE", "DASH"))
def tiny_text(rows, x0, y0, s, col, alpha, geo):
    pat = {"A": [".#.", "#.#", "###", "#.#", "#.#"], "C": ["###", "#..", "#..", "#..", "###"],
           "D": ["##.", "#.#", "#.#", "#.#", "##."], "E": ["###", "#..", "##.", "#..", "###"],
           "H": ["#.#", "#.#", "###", "#.#", "#.#"], "M": ["#.#", "###", "###", "#.#", "#.#"],
           "O": ["###", "#.#", "#.#", "#.#", "###"], "P": ["###", "#.#", "###", "#..", "#.."],
           "R": ["##.", "#.#", "##.", "#.#", "#.#"], "S": [".##", "#..", ".#.", "..#", "##."],
           "T": ["###", ".#.", ".#.", ".#.", ".#."], "V": ["#.#", "#.#", "#.#", "#.#", ".#."],
           "W": ["#.#", "#.#", "###", "###", "#.#"], " ": ["...", "...", "...", "...", "..."]}
    x = x0
    for ch in s:
        g = pat.get(ch, pat[" "])
        for j, line in enumerate(g):
            for i, c in enumerate(line):
                if c == "#":
                    px, py = x + i, y0 + j
                    if geo.x0 <= px < geo.x1 and geo.y0 <= py < geo.y1:
                        rows[py][px] = mix(rows[py][px], col, alpha)
        x += 4
    return x


def tutorial_decals(rows, geo, bio):
    """Faint floor paint in the very first room: which keys do what."""
    n = len(TUTORIAL)
    span = geo.x1 - geo.x0
    for i, (a, b) in enumerate(TUTORIAL):
        cx = geo.x0 + span * (i + 0.5) / n
        wa, wb = len(a) * 4 - 1, len(b) * 4 - 1
        y = geo.y0 + 8
        tiny_text(rows, int(cx - wa / 2), y, a, (200, 210, 255), 0.42, geo)
        tiny_text(rows, int(cx - wb / 2), y + 7, b, bio["accent"], 0.34, geo)


def ball_recolor(col):
    """Srijan's pink ball bullet, recoloured to another bullet colour."""
    lit, dark = mix(col, WHITE, 0.45), mul(col, 0.62)

    def f(c):
        if c[0] > 240 and c[1] > 240:
            return WHITE
        if c == (168, 50, 92):
            return dark
        if c == (246, 117, 162):
            return lit
        return col
    return f


ENEMY_LIGHT = {"fly", "stinger", "turret", "blob", "blobling", "summoner", "brute"}


def fade_text(c, x, y, s, col, u, back=VOID):
    """Text whose colour fades into the cell behind it as u goes 0 -> 1."""
    x, y = int(x), int(y)
    if 0 <= y < c.h:
        row = c.cells[y]
        for i, ch in enumerate(s):
            if 0 <= x + i < c.w:
                bg = row[x + i][2] or back
                c.put(x + i, y, ch, mix(col, bg, clamp01(u)) if u > 0 else col)


def pill(c, x, y, text, fg, bg):
    c.put(x, y, "▐", bg)
    c.text(x + 1, y, text, fg, bg)
    c.put(x + 1 + len(text), y, "▌", bg)
    return x + len(text) + 2


def box(c, x, y, w, h, col):
    """A filled card with half-block soft caps on rows y and y + h - 1."""
    c.text(x, y, "▗" + "▄" * (w - 2) + "▖", col)
    for r in range(y + 1, y + h - 1):
        c.text(x, r, " " * w, None, col)
    c.text(x, y + h - 1, "▝" + "▀" * (w - 2) + "▘", col)


def wrap(s, width):
    lines, cur = [], ""
    for word in s.split():
        if cur and len(cur) + 1 + len(word) > width:
            lines.append(cur)
            cur = word
        else:
            cur = f"{cur} {word}" if cur else word
    return lines + [cur] if cur else lines


def stamp_decal(rows, geo, bio, sprites, decal):
    name, frame, flip, x, y = decal
    if name == "splat":
        r = random.Random(frame * 7919 + int(x) * 31 + int(y))
        for _ in range(12):
            a, d = r.uniform(0, 6.283), r.uniform(0, 4.5)
            px, py = int(x + math.cos(a) * d), int(y + math.sin(a) * d * 0.7)
            if geo.x0 <= px < geo.x1 and geo.y0 <= py < geo.y1:
                rows[py][px] = mix(rows[py][px], bio["decal"], 0.65)
        return int(y) - 4, int(y) + 4
    if name == "scorch":
        for dy in range(-5, 6):
            for dx in range(-8, 9):
                d = math.hypot(dx / 8, dy / 5)
                px, py = int(x + dx), int(y + dy)
                if d < 1 and geo.x0 <= px < geo.x1 and geo.y0 <= py < geo.y1:
                    rows[py][px] = mul(rows[py][px], 0.45 + 0.5 * d)
        return int(y) - 5, int(y) + 6
    spr = sprites.get(name, frame, flip, "dark")
    for dx, dy, c in spr.px:
        px, py = int(x) + dx, int(y) + dy
        if geo.x0 <= px < geo.x1 and geo.y0 <= py < geo.y1:
            rows[py][px] = mix(rows[py][px], c, 0.85)
    return int(y) - spr.oy, int(y) - spr.oy + spr.h


class View:
    def __init__(self, sprites, art):
        self.S, self.art = sprites, art
        self.st = Stamps(sprites)
        self.tex = {}
        self.void = None
        self._title = None
        self.dim = None
        self.mm = None

    # ---------------------------------------------------------------- caches
    def room_cache(self, g):
        room, geo = g.cur(), g.geo
        bio = BIOMES[g.fi // 3]
        key = (room.locked, self.S.version, g.fi)
        if room.bg is None or room.bg[0] != key:
            rows = build_room_bg(g, room, self.S, self.art, self.tex)
            for dec in room.decals:
                stamp_decal(rows, geo, bio, self.S, dec)
            if room.locked:
                self.draw_bars(rows, g, room)
            room.bg = [key, rows, self.cells_of(rows), len(room.decals)]
        bg = room.bg
        if bg[3] < len(room.decals):  # new corpses: stamp them and recompose their rows
            rows, cells = bg[1], bg[2]
            for dec in room.decals[bg[3]:]:
                y0, y1 = stamp_decal(rows, geo, bio, self.S, dec)
                for r in range(max(0, y0 >> 1), min(len(cells), (y1 >> 1) + 1)):
                    cells[r] = px_cells(rows[2 * r], rows[2 * r + 1] if 2 * r + 1 < len(rows) else rows[2 * r])
            bg[3] = len(room.decals)
        return bg

    @staticmethod
    def cells_of(rows):
        out = []
        for r in range(0, len(rows), 2):
            out.append(px_cells(rows[r], rows[r + 1] if r + 1 < len(rows) else rows[r]))
        return out

    def draw_bars(self, rows, g, room):
        geo = g.geo
        bio = BIOMES[g.fi // 3]
        hot = mix(bio["accent"], (255, 60, 90), 0.5)
        for d in room.doors:
            x0, y0, x1, y1 = geo.door[d]
            if d in ("up", "down"):
                for x in range(x0, x1):
                    for y in range(y0, y1):
                        on = (x - x0) % 3 == 1
                        rows[y][x] = mix(hot, WHITE, 0.3) if on else mul(rows[y][x], 0.6)
                yb = y1 - 1 if d == "up" else y0
                for x in range(x0 - 1, x1 + 1):
                    rows[yb][x] = hot
            else:
                for y in range(y0, y1):
                    for x in range(x0, x1):
                        on = (y - y0) % 3 == 1
                        rows[y][x] = mix(hot, WHITE, 0.3) if on else mul(rows[y][x], 0.6)

    def void_cells(self, c, g):
        bio = BIOMES[max(0, g.fi) // 3] if g else BIOMES[0]
        key = (c.w, c.h, bio["name"], term.TRUECOLOR)
        if self.void is None or self.void[0] != key:
            base = bio["void"]
            rows = []
            for y in range(c.h):
                u = y / max(1, c.h - 1)
                row = []
                for x in range(c.w):
                    if term.TRUECOLOR:
                        v = (x / max(1, c.w - 1) - 0.5) ** 2 + (u - 0.5) ** 2
                        col = mul(base, 1.25 - 0.9 * v)
                    else:
                        col = base
                    row.append((" ", None, col))
                rows.append(row)
            self.void = (key, rows)
        return self.void[1]

    # ---------------------------------------------------------------- the world
    def draw_world(self, c, g, now, ui):
        """Room, actors and effects into the canvas; returns (ox, oy) of the room's
        top-left cell on screen."""
        geo, S, st = g.geo, self.S, self.st
        W, H = geo.W, geo.H
        bg = self.room_cache(g)
        buf = [r[:] for r in bg[1]]
        p = g.player
        bio = BIOMES[g.fi // 3]

        def blit(spr, x, y):
            x, y = int(x), int(y)
            if x - spr.ox >= 0 and y - spr.oy >= 0 and x - spr.ox + spr.w <= W and y - spr.oy + spr.h <= H:
                for dx, dy, col in spr.px:
                    buf[y + dy][x + dx] = col
            else:
                for dx, dy, col in spr.px:
                    px, py = x + dx, y + dy
                    if 0 <= px < W and 0 <= py < H:
                        buf[py][px] = col

        def blit_a(spr, x, y, a, dither=False):
            x, y = int(x), int(y)
            for dx, dy, col in spr.px:
                px, py = x + dx, y + dy
                if 0 <= px < W and 0 <= py < H:
                    if dither:
                        if hash01(px, py, int(now * 20)) < a:
                            buf[py][px] = col
                    else:
                        buf[py][px] = mix(buf[py][px], col, a)

        def glow(solid, halo, x, y):
            ix, iy = int(x), int(y)
            for dx, dy, r, gg, b in halo:
                px, py = ix + dx, iy + dy
                if 0 <= px < W and 0 <= py < H:
                    row = buf[py]
                    q = row[px]
                    v0, v1, v2 = q[0] + r, q[1] + gg, q[2] + b
                    row[px] = (v0 if v0 < 256 else 255, v1 if v1 < 256 else 255, v2 if v2 < 256 else 255)
            for dx, dy, col in solid:
                px, py = ix + dx, iy + dy
                if 0 <= px < W and 0 <= py < H:
                    buf[py][px] = col

        def light(x, y, rad, col, k):
            ix, iy = int(x), int(y)
            for dx, dy, w in st.light(max(2, int(rad))):
                px, py = ix + dx, iy + dy
                if 0 <= px < W and 0 <= py < H:
                    row = buf[py]
                    q = row[px]
                    f = w * k
                    v0, v1, v2 = q[0] + col[0] * f, q[1] + col[1] * f, q[2] + col[2] * f
                    row[px] = (int(v0) if v0 < 255 else 255, int(v1) if v1 < 255 else 255,
                               int(v2) if v2 < 255 else 255)

        def blend(x, y, col, a):
            x, y = int(x), int(y)
            if 0 <= x < W and 0 <= y < H:
                buf[y][x] = mix(buf[y][x], col, a)

        def addp(x, y, col, k):
            x, y = int(x), int(y)
            if 0 <= x < W and 0 <= y < H:
                q = buf[y][x]
                v0, v1, v2 = int(q[0] + col[0] * k), int(q[1] + col[1] * k), int(q[2] + col[2] * k)
                buf[y][x] = (v0 if v0 < 255 else 255, v1 if v1 < 255 else 255, v2 if v2 < 255 else 255)

        def shadow(x, y, rx, k=0.55):
            ix, iy = int(x), int(y)
            for dx in range(-rx, rx + 1):
                for dy in (0, 1):
                    if dy and abs(dx) >= rx - 1:
                        continue
                    px, py = ix + dx, iy + dy
                    if 0 <= px < W and 0 <= py < H:
                        q = buf[py][px]
                        buf[py][px] = (int(q[0] * k), int(q[1] * k), int(q[2] * k))

        def line(x0, y0, x1, y1, col, a=1.0, every=1, phase=0):
            n = int(max(abs(x1 - x0), abs(y1 - y0))) + 1
            for i in range(0, n, every):
                if (i // every + phase) % 2 and every > 1:
                    continue
                t = i / n
                x, y = int(x0 + (x1 - x0) * t), int(y0 + (y1 - y0) * t)
                if 0 <= x < W and 0 <= y < H:
                    buf[y][x] = col if a >= 1 else mix(buf[y][x], col, a)

        # lights under everything
        for lx, ly, t, dur, rad, col, k in g.lights:
            light(lx, ly, rad, col, k * (1 - t / dur))
        # pickups
        for k in g.cur().pickups:
            self.draw_pickup(k, now, blit, glow, light, shadow, addp, blend)
        for b in g.cur().barrels:
            shadow(b[0], b[1] + 4, 3)
            blit(S.get("barrel"), b[0], b[1])
            if int(now * 3 + b[0]) % 3 == 0:
                addp(b[0], b[1] - 2, (255, 60, 40), 0.8)
        # spawn markers
        for x, y, t, dur, col in g.marks:
            u = t / dur
            r = int((1 - u) * 9) + 2
            for dx, dy in st.circle(r):
                blend(x + dx, y + dy * 0.7, col, 0.25 + 0.55 * u)
            light(x, y, 4 + 3 * u, col, 0.5 * u)
            for k2 in range(4):
                a = now * 5 + k2 * math.pi / 2
                addp(x + math.cos(a) * r, y + math.sin(a) * r * 0.7, WHITE, 0.8)
        # actors, back to front
        actors = [e for e in g.enemies if e.spawn <= 0 and not (e.dead and not e.boss)]
        actors.sort(key=lambda e: e.y)
        drawn_player = False
        for e in actors:
            if not drawn_player and p.y < e.y:
                self.draw_player(g, p, now, blit, blit_a, shadow, line, addp, light, ui)
                drawn_player = True
            self.draw_enemy(g, e, now, blit, blit_a, shadow, light, addp, blend)
        if not drawn_player:
            self.draw_player(g, p, now, blit, blit_a, shadow, line, addp, light, ui)
        # explosions (Srijan's 14-frame red blast)
        ex = S.base["explosion"]
        for x, y, t, scale in g.booms:
            f = min(len(ex) - 1, int(t / 0.03))
            blit(S.get("explosion", f), x, y)
        # sparks and dust
        for q in g.parts:
            u = q[4] / q[5]
            if q[7] == 0:
                addp(q[0], q[1], q[6], 1.0 - u)
            else:
                blend(q[0], q[1], q[6], 0.5 * (1 - u))
        # player shots
        for b in g.pb:
            if b.st == "pb":  # player shots stay slimmer and dimmer than enemy bullets
                k16 = int(round(math.atan2(b.vy, b.vx) / (math.pi / 8))) % 16
                solid, halo = st.streak(4 + (b.r > 2), 0.55 + 0.25 * (b.r > 2), (255, 220, 110) if b.crit else CYAN,
                                        k16, CYAN_LIT, 0.22)
            elif b.st == "porb":
                solid, halo = st.orb(round(b.r * 0.8 * 4) / 4, (120, 236, 255), (int(b.x % 1 * 2), int(b.y % 1 * 2)))
            elif b.st == "pbounce":
                solid, halo = st.orb(round(b.r * 0.7 * 4) / 4, (110, 255, 214), (int(b.x % 1 * 2), int(b.y % 1 * 2)))
            else:
                solid, halo = st.orb(round(b.r * 0.7 * 4) / 4, (255, 230, 120) if b.crit else CYAN,
                                     (int(b.x % 1 * 2), int(b.y % 1 * 2)))
            glow(solid, halo, b.x, b.y)
        if p.beam:
            self.draw_laser(p.beam, now, buf, W, H, 1.0 + 0.8 * g.up("big"))
        # telegraphs and beams
        for ln in g.lines:
            u = ln["t"] / ln["dur"]
            a = ln["ang"]
            dx, dy = math.cos(a), math.sin(a)
            L = ln.get("len")
            if L:
                ex2, ey2 = ln["x"] + dx * L, ln["y"] + dy * L
            else:
                ex2, ey2 = g.ray(ln["x"], ln["y"], dx, dy, step=2.0)
            blink = u > 0.7 and int(now * 20) % 2
            col = WHITE if blink else ln["col"]
            line(ln["x"] + dx * 5, ln["y"] + dy * 5, ex2, ey2, col, 0.35 + 0.5 * u, 2, int(now * 12))
            if ln.get("wide"):
                line(ln["x"] - dy * 3, ln["y"] + dx * 3, ex2 - dy * 3, ey2 + dx * 3, col, 0.25 + 0.4 * u, 3)
                line(ln["x"] + dy * 3, ln["y"] - dx * 3, ex2 + dy * 3, ey2 - dx * 3, col, 0.25 + 0.4 * u, 3)
        for bm in g.beams:
            seg = bm.get("seg")
            if seg:
                self.draw_beam(bm, seg, now, buf, W, H, line, light)
        # enemy bullets on top of everything that moves: they must always read
        for b in g.eb:
            col = BULLET_COL.get(b.kind, (255, 80, 140))
            if b.delay > 0:
                if int(now * 12) % 2:
                    addp(b.x, b.y, col, 0.7)
                continue
            s_ = b.st
            if s_ == "orb" or s_ == "mine":
                r = b.r * (0.55 if b.t < 0.05 else 1.0)
                if s_ == "mine":
                    r *= 0.85 + 0.25 * math.sin(now * 14 + b.x)
                solid, halo = st.orb(round(r * 4) / 4, col, (int(b.x % 1 * 2), int(b.y % 1 * 2)))
            elif s_ == "sting" or s_ == "needle":
                k16 = int(round(math.atan2(b.vy, b.vx) / (math.pi / 8))) % 16
                solid, halo = st.streak(4 if s_ == "sting" else 6, 0.9 if s_ == "sting" else 0.8, col, k16)
            else:
                solid, halo = st.sprite_glow("ball_small", 0, None, col, ball_recolor(col))
            glow(solid, halo, b.x, b.y)
        # rings
        for x, y, t, dur, r0, r1, col in g.rings:
            u = t / dur
            r = int(r0 + (r1 - r0) * ease_out(u))
            for dx, dy in st.circle(max(1, r)):
                blend(x + dx, y + dy * 0.8, col, 0.85 * (1 - u))
        base, bcells = bg[1], bg[2]
        if ui.get("minimap", True):
            self.draw_minimap(g, buf, W, H, now, base)
        cells = []
        for r in range(0, H, 2):  # rows nothing drew on reuse the cached cells
            top = buf[r]
            bot = buf[r + 1] if r + 1 < H else top
            if top == base[r] and (r + 1 >= H or bot == base[r + 1]):
                cells.append(bcells[r >> 1])
            else:
                cells.append(px_cells(top, bot))
        return cells

    def draw_laser(self, segs, now, buf, W, H, width):
        for x0, y0, x1, y1 in segs:
            n = int(max(abs(x1 - x0), abs(y1 - y0))) + 1
            dx, dy = (x1 - x0) / n, (y1 - y0) / n
            L = math.hypot(dx, dy) or 1
            nx, ny = -dy / L, dx / L
            wob = 0.5 + 0.5 * math.sin(now * 40)
            for i in range(n):
                x, y = x0 + dx * i, y0 + dy * i
                for o, col, a in ((0, WHITE, 1.0), (1, CYAN_LIT, 0.9), (-1, CYAN_LIT, 0.9), (2, CYAN, 0.5 + 0.2 * wob),
                                  (-2, CYAN, 0.5 + 0.2 * wob), (3, CYAN_DARK, 0.25), (-3, CYAN_DARK, 0.25)):
                    if abs(o) > width + 1.5:
                        continue
                    px, py = int(x + nx * o * 0.6), int(y + ny * o * 0.6)
                    if 0 <= px < W and 0 <= py < H:
                        buf[py][px] = col if a >= 1 else mix(buf[py][px], col, a)

    def draw_beam(self, bm, seg, now, buf, W, H, line, light):
        sx, sy, ex, ey = seg
        col = bm["col"]
        if bm["t"] < bm["warm"]:
            u = bm["t"] / bm["warm"]
            line(sx, sy, ex, ey, WHITE if u > 0.75 and int(now * 24) % 2 else col, 0.3 + 0.5 * u, 2, int(now * 15))
            return
        n = int(max(abs(ex - sx), abs(ey - sy))) + 1
        dx, dy = (ex - sx) / n, (ey - sy) / n
        L = math.hypot(dx, dy) or 1
        nx, ny = -dy / L, dx / L
        w = bm["w"]
        fl = 0.8 + 0.2 * math.sin(now * 50)
        for i in range(n):
            x, y = sx + dx * i, sy + dy * i
            for o in range(-int(w) - 2, int(w) + 3):
                d = abs(o)
                px, py = int(x + nx * o * 0.7), int(y + ny * o * 0.7)
                if not (0 <= px < W and 0 <= py < H):
                    continue
                if d <= w * 0.3:
                    buf[py][px] = WHITE
                elif d <= w * 0.75:
                    buf[py][px] = mix(col, WHITE, 0.45)
                elif d <= w:
                    buf[py][px] = col
                else:
                    buf[py][px] = mix(buf[py][px], col, 0.35 * fl / (d - w + 0.5))
        light(ex, ey, 6, col, 0.7)

    def draw_pickup(self, k, now, blit, glow, light, shadow, addp, blend):
        S, st = self.S, self.st
        bob = math.sin(now * 4 + k.x * 0.3)
        if k.kind == "coin":
            f = int(now * 9 + k.x * 0.7) % 4
            shadow(k.x, k.y + 2, 1, 0.6)
            blit(S.get("coin", f), k.x, k.y + (bob > 0.6) * -1)
            if (now * 1.3 + k.x * 0.05) % 1 < 0.06:
                addp(k.x + 1, k.y - 2, WHITE, 1.0)
        elif k.kind == "heart":
            shadow(k.x, k.y + 4, 3)
            light(k.x, k.y, 6, (255, 60, 100), 0.35 + 0.15 * bob)
            blit(S.get("heart"), k.x, k.y + round(bob))
        elif k.kind == "weapon":
            shadow(k.x, k.y + 5, 4)
            light(k.x, k.y, 8, CYAN, 0.3 + 0.1 * bob)
            solid, halo = st.sprite_glow("w_" + k.val, 0, None, CYAN)
            glow(solid, halo, k.x, k.y - 1 + round(bob))
        elif k.kind == "chest":
            shadow(k.x, k.y + 4, 5)
            blit(S.get("chest"), k.x, k.y)
            if (now * 0.8) % 1 < 0.08:
                addp(k.x + 3, k.y - 3, WHITE, 1.0)
            light(k.x, k.y, 9, GOLD, 0.25)
        elif k.kind == "orb":
            light(k.x, k.y, 10, GOLD, 0.5)
            solid, halo = st.orb(2.6 + 0.4 * bob, GOLD, (0, 0))
            glow(solid, halo, k.x, k.y + round(bob))
            for i in range(3):
                a = now * 3 + i * 2.09
                addp(k.x + math.cos(a) * 6, k.y + math.sin(a) * 4, GOLD_LIT, 0.9)
        elif k.kind == "portal":
            light(k.x, k.y, 14, (120, 200, 255), 0.45)
            for ring in range(3):
                rx, ry = 7 - ring * 2, 4 - ring
                n = 18 - ring * 4
                for i in range(n):
                    a = i * 2 * math.pi / n + now * (2.5 + ring) * (1 if ring % 2 == 0 else -1)
                    col = mix((90, 160, 255), (230, 140, 255), (i / n + now * 0.3) % 1)
                    blend(k.x + math.cos(a) * rx, k.y + math.sin(a) * ry, col, 0.9)
            blend(k.x, k.y, (10, 10, 30), 0.8)
            for i in range(4):
                h = (now * 0.9 + i * 0.25) % 1
                addp(k.x + math.sin(i * 7 + now) * 4, k.y - h * 14, (160, 210, 255), 1 - h)
        elif k.kind == "shop":
            kind, val = k.val
            shadow(k.x, k.y + 6, 5)
            blit(S.get("pedestal"), k.x, k.y + 4)
            y = k.y - 3 + round(bob)
            if kind in ("heart", "maxhp"):
                blit(S.get("heart"), k.x, y)
                if kind == "maxhp":
                    addp(k.x + 4, y - 3, WHITE, 1.0)
            elif kind == "weapon":
                solid, halo = st.sprite_glow("w_" + val, 0, None, CYAN)
                glow(solid, halo, k.x, y)
            else:
                solid, halo = st.orb(2.4, GOLD, (0, 0))
                glow(solid, halo, k.x, y)

    def draw_player(self, g, p, now, blit, blit_a, shadow, line, addp, light, ui):
        S = self.S
        if not p.alive:
            return
        for x, y, t, face in p.trail:  # dash afterimages
            age = g.time - t
            if age < 0.16:
                blit_a(S.get("player_run", 0, face < 0, "ghost"), x, y, 0.55 * (1 - age / 0.16))
        shadow(p.x, p.y + 5, 3)
        if p.inv > 0 and p.dash_t <= 0 and p.hurt_t < INVULN and int(now * 16) % 2 == 0:
            return
        if p.dash_t > 0:
            name, fr = "player_run", 1
        elif p.moving:
            name, fr = "player_run", int(p.anim * 1.7) % 4
        elif (now % 3.3) < 0.12:
            name, fr = "player_blink", 0
        else:
            name, fr = "player_idle", int(now * 2.2) % 2
        mode = "white" if p.hurt_t < 0.06 else "hurt" if p.hurt_t < 0.35 else None
        ca, sa = math.cos(p.aim), math.sin(p.aim)
        gx, gy = p.x + p.face * 1.5, p.y + 2.5

        def gun():
            for i in range(2, 6):
                col = (102, 255, 227) if i == 5 else (224, 228, 244) if i > 2 else (150, 154, 176)
                x, y = int(gx + ca * i), int(gy + sa * i * 0.8)
                line(x, y, x, y, col)
        if sa < -0.3:
            gun()
        blit(S.get(name, fr, p.face < 0, mode), p.x, p.y)
        if sa >= -0.3:
            gun()
        if p.firing and p.fire_cd > WEAPONS[p.weapons[p.wi]]["cd"] * 0.6:
            mx, my = g.muzzle()
            addp(mx, my, WHITE, 1.0)
            addp(mx + ca, my + sa, CYAN_LIT, 1.0)
        maxc = 1 + g.up("dash")
        if p.charges < maxc and p.dash_t <= 0:  # dash recharge, under the feet
            u = p.recharge / (DASH_CD * (1 - 0.15 * g.up("boots")))
            for i in range(6):
                line(p.x - 3 + i, p.y + 7, p.x - 3 + i, p.y + 7, CYAN if i < u * 6 else (40, 60, 80))
        if p.shield:
            for i in range(10):
                a = i * math.pi / 5 + now * 1.5
                addp(p.x + math.cos(a) * 7, p.y + 1 + math.sin(a) * 6, SHIELD, 0.45)
        nb = 2 * g.up("blades")
        for i in range(nb):
            a = g.time * 4.2 + i * 2 * math.pi / nb
            bx, by = p.x + math.cos(a) * 12, p.y + 1 + math.sin(a) * 9
            light(bx, by, 3, (255, 240, 160), 0.5)
            for dx, dy in ((0, 0), (1, 0), (-1, 0), (0, 1), (0, -1)):
                line(bx + dx, by + dy, bx + dx, by + dy, WHITE if dx == dy == 0 else (255, 230, 140))
        if ui.get("aim_hint") and p.alive:
            ax, ay = p.x + ca * 16, p.y + 1 + sa * 16
            for dx, dy in ((-2, 0), (2, 0), (0, -2), (0, 2)):
                addp(ax + dx, ay + dy, (200, 220, 255), 0.5)

    def draw_enemy(self, g, e, now, blit, blit_a, shadow, light, addp, blend):
        S = self.S
        k = e.kind
        flash = e.flash > 0 or (g.time - e.data.get("pop", -9) < 0.07)
        mode = "white" if flash else None
        col = BULLET_COL.get(k, WHITE)
        if e.boss:
            return self.draw_boss(g, e, now, blit, blit_a, shadow, light, addp, blend)
        size = {"gnat": 1, "blobling": 2, "stinger": 3}.get(k, 4)
        shadow(e.x, e.y + e.r + 1, size)
        if k in ENEMY_LIGHT and e.cd < 0.35 and e.state not in ("aim", "wind", "dash"):
            light(e.x, e.y, 6, col, 0.5 * (1 - e.cd / 0.35))
        if k == "fly":
            spr = S.get("fly", int(now / 0.06 + e.t * 3) % 3 if not flash else 1, e.face < 0, mode)
            if flash and "fly_hurt" in S.base:
                spr = S.get("fly_hurt", 0, e.face < 0)
            blit(spr, e.x, e.y)
        elif k == "stinger":  # four exact headings: pixel art doesn't survive odd angles
            rot = (int(round(e.ang / (math.pi / 2))) % 4) * 4
            blit(S.get("stinger", 0, False, mode, rot), e.x, e.y)
        elif k == "turret":
            blit(S.get("turret", 0, False, mode), e.x, e.y)
            if not flash:
                ex, ey = e.x + round(math.cos(e.ang)), e.y - 1 + round(math.sin(e.ang))
                eye = col if e.cd > 0.35 else mix(col, WHITE, 0.7)
                blend(ex, ey, eye, 1.0)
                blend(ex + 1, ey, mul(eye, 0.7), 1.0)
        elif k == "dasher":
            jit = (1 if int(now * 30) % 2 else -1) if e.state == "wind" else 0
            blit(S.get("dasher", 0, e.face < 0, mode), e.x + jit, e.y)
            if e.state == "dash":
                light(e.x, e.y, 7, col, 0.5)
        elif k in ("blob", "blobling"):
            lift = -1 if e.state == "hop" else 0
            blit(S.get(k, 0, e.face < 0, mode), e.x, e.y + lift)
        elif k == "sniper":
            blit(S.get("sniper", 0, False, mode), e.x, e.y + round(math.sin(now * 3 + e.t)))
            if e.state == "aim":
                light(e.x, e.y, 5, col, 0.6)
        elif k == "brute":
            blit(S.get("brute", 0, e.face < 0, "white" if flash or (e.state == "wind" and int(now * 20) % 2) else None),
                 e.x, e.y)
        else:
            blit(S.get(k, 0, e.face < 0, mode), e.x, e.y)

    def draw_boss(self, g, e, now, blit, blit_a, shadow, light, addp, blend):
        S = self.S
        col = BULLET_COL[e.kind]
        dying = e.data.get("dying")
        flash = e.flash > 0 or (dying is not None and int(now * 16) % 2)
        mode = ("white" if dying is not None else "lit") if flash else None
        jx = jy = 0
        roar = g.time - e.data.get("roar", -9)
        if roar < 0.8 or dying is not None:
            jx, jy = (1 if int(now * 40) % 2 else -1), (1 if int(now * 33) % 2 else 0)
        x, y = e.x + jx, e.y + jy
        ch = e.data.get("charge")
        if ch and g.time - ch[0] < ch[1]:
            u = (g.time - ch[0]) / ch[1]
            light(x, y, 10 + 6 * u, col, 0.4 + 0.4 * u)
            for i in range(6):  # sparks pulled in toward the boss
                a = i * 1.047 + now * 2
                rr = (1 - u) * 20 + 4
                addp(x + math.cos(a) * rr, y + math.sin(a) * rr * 0.7, mix(col, WHITE, 0.5), 0.9)
        fade = e.data.get("fade")
        alpha = 1.0
        if fade:
            u = clamp01((g.time - fade[0]) / fade[1])
            alpha = 1 - u if fade[2] == "out" else u
        shadow(x, y + e.r + 4, 8, 0.5)
        if e.kind == "boss1":
            spr = S.get("boss1", int(now / 0.07) % 4, False, mode)
        else:
            spr = S.get(e.kind, 0, False, mode)
        if alpha < 1:
            blit_a(spr, x, y, alpha, dither=True)
            return
        blit(spr, x, y)
        if dying is not None and flash:
            return
        p = g.player
        a = math.atan2(p.y - y, p.x - x)
        if e.kind == "boss2":
            cx, cy = x - spr.ox + 11, y - spr.oy + 10
            charge = ch and g.time - ch[0] < ch[1]
            for dy in range(-3, 4):
                for dx in range(-6, 7):
                    if (dx / 6.2) ** 2 + (dy / 3.4) ** 2 <= 1:
                        blend(cx + dx, cy + dy, (236, 232, 255) if not charge else mix(col, WHITE, 0.5), 1.0)
            ix, iy = cx + round(math.cos(a) * 3), cy + round(math.sin(a) * 1.2)
            for dy in range(-1, 2):
                for dx in range(-1, 2):
                    blend(ix + dx, iy + dy, col, 1.0)
            blend(ix, iy, (20, 10, 40), 1.0)
            for i in range(3):  # runes pulse
                light(x - spr.ox + (5, 17, 11)[i], y - spr.oy + (18, 18, 21)[i], 3, col,
                      0.3 + 0.3 * math.sin(now * 3 + i))
        elif e.kind == "boss3":
            cx, cy = x - spr.ox + 13, y - spr.oy + 13
            pulse = 0.5 + 0.5 * math.sin(now * 6)
            for dy in range(-4, 5):
                for dx in range(-4, 5):
                    d = math.hypot(dx, dy)
                    if d <= 3.6:
                        blend(cx + dx, cy + dy, mix(col, WHITE, clamp01(1 - d / 3.6 + pulse * 0.3)), 1.0)
            light(cx, cy, 9, col, 0.4 + 0.3 * pulse)
            n = 6
            for i in range(n):
                aa = now * 1.4 + i * 2 * math.pi / n
                sx, sy = cx + math.cos(aa) * 17, cy + math.sin(aa) * 13
                for dx, dy, cc in ((0, -1, (240, 226, 255)), (-1, 0, (90, 80, 120)), (1, 0, (140, 126, 180)),
                                   (0, 1, (70, 60, 96)), (0, 0, col)):
                    blend(sx + dx, sy + dy, cc, 1.0)
        elif e.kind == "boss1":
            light(x, y + 2, 8, col, 0.25)

    def draw_minimap(self, g, buf, W, H, now, base):
        """Discovered rooms as little blocks in the top-right corner, over a darkened patch;
        it fades when the player walks under it. Cached as pixels per state."""
        rooms, geo, p = g.rooms, g.geo, g.player
        known = {c for c, r in rooms.items() if r.visited}
        for c in list(known):
            known.update(rooms[c].doors.values())
        xs = [c[0] for c in known]
        ys = [c[1] for c in known]
        gx0, gy0 = min(xs), min(ys)
        cw, chh, pw, ph = 4, 2, 5, 3
        mw = (max(xs) - gx0) * pw + cw
        mh = (max(ys) - gy0) * ph + chh
        x0, y0 = geo.x1 - mw - 3, geo.y0 + 2
        a = 0.35 if (x0 - 8 < p.x < x0 + mw + 8 and p.y < y0 + mh + 10) else 1.0
        blink = int(now * 3) % 3 == 0
        key = (id(rooms), g.pos, a, blink, id(base), len(g.cur().decals),
               tuple(sorted((c, r.visited, r.cleared) for c, r in rooms.items())))
        if self.mm is None or self.mm[0] != key:
            px = {}
            for y in range(y0 - 1, y0 + mh + 1):
                for x in range(x0 - 1, x0 + mw + 1):
                    if 0 <= x < W and 0 <= y < H:
                        px[(x, y)] = mul(base[y][x], 1 - 0.55 * a)
            icon = {"boss": (255, 70, 90), "exit": (120, 200, 255), "treasure": GOLD, "shop": (120, 230, 140)}
            for c in known:
                r = rooms[c]
                rx, ry = x0 + (c[0] - gx0) * pw, y0 + (c[1] - gy0) * ph
                if c == g.pos:
                    col = (200, 210, 255) if blink else WHITE
                elif r.kind in icon and (r.visited or r.kind == "boss"):
                    col = icon[r.kind]
                elif r.visited:
                    col = (130, 122, 172) if r.cleared or r.kind == "start" else (190, 110, 140)
                else:
                    col = (64, 60, 92)
                for j in range(chh):
                    for i in range(cw):
                        q = (rx + i, ry + j)
                        if q in px:
                            px[q] = mix(px[q], col, a)
                if r.visited:
                    for d in r.doors:
                        links = {"right": ((rx + cw, ry),), "down": ((rx + 1, ry + chh), (rx + 2, ry + chh))}.get(d, ())
                        for q in links:
                            if q in px:
                                px[q] = mix(px[q], (110, 104, 150), a)
            self.mm = (key, [(x, y, col) for (x, y), col in px.items()])
        for x, y, col in self.mm[1]:
            buf[y][x] = col

    # ---------------------------------------------------------------- the screen
    def layout(self, c, g):
        """(ox, oy, status_row?) placing the room's top-left cell; rooms bigger than the
        terminal scroll with the player."""
        geo, p = g.geo, g.player
        RH = (geo.H + 1) // 2
        avail = c.h - 1
        status = avail - RH >= 1
        if status:
            avail -= 1
        if geo.W <= c.w:
            ox = (c.w - geo.W) // 2
        else:
            ox = -int(clamp(p.x - c.w / 2, 0, geo.W - c.w))
        if RH <= avail:
            oy = 1 + (avail - RH) // 2
        else:
            oy = 1 - int(clamp(p.y / 2 - avail / 2, 0, RH - avail))
        return ox, oy, status

    def place(self, c, cells, ox, oy, top, bottom):
        for r, row in enumerate(cells):
            y = oy + r
            if top <= y < bottom:
                a, b = max(0, -ox), min(len(row), c.w - ox)
                if a < b:
                    c.cells[y][ox + a:ox + b] = row[a:b]

    def draw_play(self, c, g, now, ui):
        cells = self.draw_world(c, g, now, ui)
        c.cells = [row[:] for row in self.void_cells(c, g)]
        ox, oy, status = self.layout(c, g)
        bottom = c.h - 1 if status else c.h
        sx = sy = 0
        if g.shake_t > 0 and ui.get("shake", True):
            k = g.shake_k * min(1.0, g.shake_t / 0.3)
            sx, sy = round(math.sin(now * 91) * 2 * k), round(math.sin(now * 67 + 1) * 0.8 * k)
        self.place(c, cells, ox + sx, oy + sy, 1, bottom)
        geo, p = g.geo, g.player
        RH = len(cells)
        if g.trans:
            self.shutter(c, g, ox, oy, RH, bottom)
        if p.alive and p.hp <= max(2, p.maxhp * 0.3) and g.mode == "play":
            self.vignette(c, ox, oy, geo.W, RH, bottom, 0.25 + 0.2 * math.sin(now * 7))
        for x, y, s, col, t, life, rise in g.texts:
            u = t / life
            fade_text(c, ox + sx + x - len(s) / 2, oy + sy + (y - rise * ease_out(u)) / 2, s, col,
                      max(0.0, (u - 0.6) / 0.4))
        if g.prompt and g.mode == "play":
            x, y, s = g.prompt
            pill(c, int(ox + x - len(s) / 2) - 1, int(oy + y / 2) - 1, s, INK, (255, 226, 120))
        for k in g.cur().pickups:
            if k.kind == "shop":
                s = f"{k.price}●"
                c.text(int(ox + k.x - len(s) / 2), int(oy + (k.y + 9) / 2), s,
                       GOLD if p.coins >= k.price else (200, 110, 110))
        self.banners(c, g, now, ox, oy, geo, RH)
        self.draw_hud(c, g, now, ui)
        if status or any(e.boss for e in g.enemies):  # the boss bar is never left out
            self.draw_status(c, g, now, ui)
        if ui.get("mouse_at") and ui.get("mouse_seen") and g.mode == "play":
            mx, my = ui["mouse_at"]
            spr = self.S.get("cursor")
            px, py = mx - ox, 2 * (my - oy) + 1
            for dx, dy, col in spr.px:
                X, Y = px + dx, py + dy
                cx, cy = ox + X, oy + (Y >> 1)
                if 1 <= cy < bottom and 0 <= cx < c.w and dy % 2 == 0:
                    c.put(cx, cy, "▀" if Y % 2 == 0 else "▄", WHITE)
        return ox, oy

    def shutter(self, c, g, ox, oy, RH, bottom):
        t, d, _ = g.trans
        u = t / 0.14 if t < 0.14 else 1 - (t - 0.14) / 0.2
        u = clamp01(u)
        geo = g.geo
        col = BIOMES[g.fi // 3]["void"]
        edge = BIOMES[g.fi // 3]["accent"]
        W = min(c.w, geo.W)
        x0 = max(0, ox)
        if d in ("up", "down"):
            n = int(RH * u)
            rows = range(oy, oy + n) if (d == "up") == (t < 0.14) else range(oy + RH - n, oy + RH)
            for y in rows:
                if 1 <= y < bottom:
                    c.cells[y][x0:x0 + W] = [(" ", None, col)] * W
            ye = (oy + n) if (d == "up") == (t < 0.14) else (oy + RH - n - 1)
            if 1 <= ye < bottom and 0 < n < RH:
                c.cells[ye][x0:x0 + W] = [("▀", edge, c.cells[ye][x0 + i][2] or col) for i in range(W)]
        else:
            n = int(W * u)
            cols = range(x0, x0 + n) if (d == "left") == (t < 0.14) else range(x0 + W - n, x0 + W)
            for y in range(max(1, oy), min(bottom, oy + RH)):
                row = c.cells[y]
                for x in cols:
                    if 0 <= x < c.w:
                        row[x] = (" ", None, col)

    def vignette(self, c, ox, oy, W, RH, bottom, k):
        red = (220, 20, 40)
        x0, x1 = max(0, ox), min(c.w, ox + W)
        y0, y1 = max(1, oy), min(bottom, oy + RH)
        for y in range(y0, y1):
            row = c.cells[y]
            for x in range(x0, x1):
                d = min(x - x0, x1 - 1 - x, (y - y0) * 2, (y1 - 1 - y) * 2)
                if d >= 4:
                    if x - x0 >= 4 and x1 - 1 - x >= 4:
                        continue
                a = k * (1 - d / 4)
                if a <= 0:
                    continue
                ch, fg, bg = row[x]
                row[x] = (ch, mix(fg, red, a) if isinstance(fg, tuple) else fg, mix(bg, red, a) if isinstance(bg, tuple) else bg)

    def banners(self, c, g, now, ox, oy, geo, RH):
        if g.banner:
            label, name, t0 = g.banner
            tau = g.time - t0
            if tau < 2.6:
                u = clamp01(min(tau / 0.3, (2.6 - tau) / 0.5))
                y = clamp(oy + RH - 7, 1, c.h - 2)
                s1, s2 = f" FLOOR {label} ", f" {name.upper()} "
                x = (c.w - len(s1) - len(s2)) // 2
                back = c.cells[y][c.w // 2][2] or VOID
                acc = BIOMES[g.fi // 3]["accent"]
                c.text(x, y, s1, mix(back, INK, u), mix(back, acc, u))
                c.text(x + len(s1), y, s2, mix(back, TEXT, u), mix(back, PANEL, u))
        if g.sub == "intro":
            name = BOSS_NAME[BOSS_KIND[g.fi // 3]]
            tau = g.sub_t
            u = clamp01(min(tau / 0.4, (2.6 - tau) / 0.4))
            col = BULLET_COL[BOSS_KIND[g.fi // 3]]
            y = clamp(oy + RH // 2 + 2, 1, c.h - 3)
            slide = int((1 - ease_out(tau / 0.5)) * 30)
            s = f"  {name}  "
            x = (c.w - len(s)) // 2 - slide
            back = c.cells[y][c.w // 2][2] or VOID
            c.text(x, y, s, mix(back, WHITE, u), mix(back, mul(col, 0.55), u))
            sub = "biome boss" if g.fi < FLOORS - 1 else "the heart of the dungeon"
            c.text((c.w - len(sub)) // 2 + slide, y + 1, sub, mix(back, col, u))

    def draw_hud(self, c, g, now, ui):
        p = g.player
        w = c.w
        c.cells[0] = [(" ", None, HUD_BG)] * w
        low = p.hp <= max(2, p.maxhp * 0.3)
        x = 1
        c.put(x, 0, "♥", WHITE if low and int(now * 6) % 2 else HP_COL)
        x += 2
        bw = 16 if w >= 110 else 12 if w >= 90 else 8
        frac, trail = p.hp / p.maxhp, p.hp_shown / p.maxhp
        for i in range(bw):
            u0, u1 = i / bw, (i + 1) / bw
            back = HP_TRAIL if trail >= u1 - 1e-6 else HP_EMPTY
            if frac >= u1 - 1e-6:
                c.put(x + i, 0, " ", None, HP_COL)
            elif frac > u0 + 1e-6:
                c.put(x + i, 0, "▌", HP_COL, back if trail > (u0 + u1) / 2 else HP_EMPTY)
            else:
                c.put(x + i, 0, " ", None, back)
        x += bw
        s = f" {p.hp}/{p.maxhp}"
        c.text(x, 0, s, TEXT)
        x += len(s) + 1
        if g.up("shield"):
            c.put(x, 0, "◈", SHIELD if p.shield else FAINT)
            x += 2
        c.text(x, 0, "●", GOLD)
        c.text(x + 2, 0, str(p.coins), GOLD_LIT)
        x += 4 + len(str(p.coins))
        maxc = 1 + g.up("dash")
        for i in range(maxc):
            c.put(x + i, 0, "»", CYAN if i < p.charges else (70, 90, 110))
        x += maxc + 2
        for i, wn in enumerate(p.weapons):
            name = WEAPONS[wn]["name"]
            if i == p.wi:
                x = pill(c, x, 0, name, INK, CYAN_LIT)
            else:
                c.text(x, 0, name, FAINT)
                x += len(name)
            x += 1
        right = f"{g.floor_label()} {BIOMES[g.fi // 3]['name']}"
        sc = f"  {score_of(g):,}"
        if x + len(right) + len(sc) + 2 < w:
            c.text(w - len(right) - len(sc) - 1, 0, right, DIM)
            c.text(w - len(sc) - 1, 0, sc, TEXT)
        elif x + len(g.floor_label()) + 2 < w:
            c.text(w - len(g.floor_label()) - 1, 0, g.floor_label(), DIM)

    def draw_status(self, c, g, now, ui):
        y, w = c.h - 1, c.w
        c.cells[y] = [(" ", None, HUD_BG)] * w
        x = 1
        for k, lv in g.ups.items():
            name, _, glyph, col, _ = UPGRADES[k]
            if x + 4 >= w // 3:
                c.text(x, y, "…", FAINT)
                break
            c.put(x, y, glyph, col)
            c.text(x + 1, y, str(lv), FAINT)
            x += 3
        boss = next((e for e in g.enemies if e.boss), None)
        if boss and boss.data.get("dying") is None:
            name = BOSS_NAME[boss.kind]
            bw = min(36, w // 3)
            bx = (w - bw - len(name) - 1) // 2
            c.text(bx, y, name, BULLET_COL[boss.kind])
            bx += len(name) + 1
            frac = boss.hp / boss.maxhp
            col = BULLET_COL[boss.kind]
            for i in range(bw):
                u1 = (i + 1) / bw
                on = frac >= u1 - 1e-6
                half = not on and frac > i / bw
                mark = i in (int(bw * 0.33), int(bw * 0.66))
                c.put(bx + i, y, "▌" if half else "▏" if mark and not on else " ",
                      col if half else (120, 110, 150), col if on else (50, 36, 60))
        else:
            room = g.cur()
            msg = ""
            if room.locked and room.waves:
                alive = sum(1 for e in g.enemies if not e.dead and e.kind != "gnat")
                msg = f"wave {room.wave_i + 1}/{len(room.waves)}  ·  {alive} left"
            elif any(k.kind == "portal" for k in room.pickups):
                msg = "the portal is open: step in"
            elif room.kind == "shop":
                msg = "shop: stand by an item, e to buy"
            elif room.cleared and room.kind not in ("start",):
                msg = "clear"
            c.text((w - len(msg)) // 2, y, msg, DIM)
        hint = "space dash  f swap  p pause"
        if w > len(hint) + 2 * (w // 3):
            c.text(w - len(hint) - 1, y, hint, FAINT)

    def dimmed(self, c, g, now, ui, key):
        """The world, frozen and darkened, as a backdrop for menus (built once per key)."""
        if self.dim is None or self.dim[0] != (key, c.w, c.h):
            self.draw_play(c, g, now, dict(ui, mouse_at=None))
            rows = [[(ch, mul(fg, 0.32) if isinstance(fg, tuple) else fg, mul(bg, 0.32) if isinstance(bg, tuple) else bg)
                     for ch, fg, bg in row] for row in c.cells]
            self.dim = ((key, c.w, c.h), rows)
        c.cells = [row[:] for row in self.dim[1]]

    def draw_choice(self, c, g, now, ui):
        self.dimmed(c, g, now, ui, ("choice", g.choice_t))
        n = len(g.choice)
        cw = min(30, (c.w - 4 - 3 * (n - 1)) // max(1, n))
        ch = 10
        x0 = (c.w - (n * cw + (n - 1) * 3)) // 2
        y0 = max(3, c.h // 2 - ch // 2)
        head = {"floor": f"FLOOR {g.floor_label()} CLEARED", "orb": "A TREASURE", "shop": "BOUGHT"}.get(
            g.choice_from, "")
        title = "choose an upgrade"
        c.text((c.w - len(head)) // 2, y0 - 3, head, GOLD)
        c.text((c.w - len(title)) // 2, y0 - 2, title, TEXT)
        ui["cards"] = []
        tau = g.time - g.choice_t
        for i, k in enumerate(g.choice):
            name, desc, glyph, col, mx = UPGRADES[k]
            t = tau - i * 0.08
            if t < 0:
                continue
            x = x0 + i * (cw + 3)
            y = y0 + int(round((1 - back_out(t / 0.3)) * 3))
            sel = i == g.choice_sel
            back = mix(CARD, col, 0.22) if sel else CARD
            box(c, x, y, cw, ch, back)
            if sel:
                c.text(x, y, "▗" + "▄" * (cw - 2) + "▖", col)
                c.text(x, y + ch - 1, "▝" + "▀" * (cw - 2) + "▘", col)
                for r in range(y + 1, y + ch - 1):
                    c.put(x, r, "▌", col, back)
                    c.put(x + cw - 1, r, "▐", col, back)
            pill(c, x + 2, y + 2, f" {glyph} ", INK, col)
            c.text(x + 8, y + 2, name[:cw - 10], WHITE if sel else TEXT, back)
            lv = g.up(k)
            tag = f"Lv {lv} → {lv + 1}" if lv else "new"
            c.text(x + 8, y + 3, tag, col if lv else (150, 230, 160), back)
            for j, line_ in enumerate(wrap(desc, cw - 4)[:3]):
                c.text(x + 2, y + 5 + j, line_, DIM if not sel else TEXT, back)
            key = f"[{i + 1}]"
            c.text(x + cw - len(key) - 2, y + ch - 2, key, col if sel else FAINT, back)
            ui["cards"].append((x, y, cw, ch))
        hint = "←/→ or 1-3 choose  ·  enter take" + ("  ·  click a card" if ui.get("mouse_seen") else "")
        c.text((c.w - len(hint)) // 2, y0 + ch + 1, hint, FAINT)
        self.draw_hud(c, g, now, ui)

    def build_lines(self, g):
        p = g.player
        ws = " + ".join(WEAPONS[w]["name"] for w in p.weapons)
        ups = ", ".join(f"{UPGRADES[k][0]}{' ' + str(v) if v > 1 else ''}" for k, v in g.ups.items()) or "no upgrades"
        return ws, ups

    def draw_pause(self, c, g, now, ui):
        self.dimmed(c, g, now, ui, ("pause", g.time))
        rows = [("WASD", "move  (tap the other way to stop short)"),
                ("arrow keys", "shoot; two arrows aim diagonally"),
                ("mouse", "aim at the cursor, hold the button to shoot"),
                ("space", "dash through bullets (cyan » charges)"),
                ("f / tab", "swap weapons"), ("e / enter", "buy, pick up"),
                ("m", "mute"), ("r", "abandon run, start a new one"), ("q", "quit")]
        ws, ups = self.build_lines(g)
        bw = min(c.w - 4, 64)
        bh = len(rows) + 9
        x0, y0 = (c.w - bw) // 2, max(1, (c.h - bh) // 2)
        box(c, x0, y0, bw, bh, PANEL)
        t = "PAUSED"
        c.text((c.w - len(t)) // 2, y0 + 1, t, GOLD, PANEL)
        for i, (k, d) in enumerate(rows):
            pill(c, x0 + 15 - len(k), y0 + 3 + i, k, TEXT, KEYCAP)
            c.text(x0 + 18, y0 + 3 + i, d[:bw - 20], DIM, PANEL)
        y = y0 + 4 + len(rows)
        c.text(x0 + 3, y, ("weapons  " + ws)[:bw - 6], TEXT, PANEL)
        for j, ln in enumerate(wrap("build  " + ups, bw - 6)[:2]):
            c.text(x0 + 3, y + 1 + j, ln, DIM, PANEL)
        foot = f"seed {g.seed}  ·  {g.diff_name}  ·  p or esc: resume"
        c.text((c.w - len(foot)) // 2, y0 + bh - 2, foot[:bw - 2], FAINT, PANEL)
        self.draw_hud(c, g, now, ui)

    def pixel_word(self, c, cx, y, word, L, colfn, shadow=None):
        """Draw word in the 5x7 font as half-block pixels centred on column cx, top row y."""
        pts, w, h = word_px(word, L)
        x0 = int(cx - w / 2)
        rows = {}
        for (i, j) in pts:
            rows.setdefault(j, {})[i] = colfn(i / max(1, w - 1), j / max(1, h - 1))
        for r in range((h + 1) // 2):
            yy = y + r
            if not 0 <= yy < c.h:
                continue
            top, bot = rows.get(2 * r, {}), rows.get(2 * r + 1, {})
            for i in range(w):
                xx = x0 + i
                if not 0 <= xx < c.w:
                    continue
                t, b = top.get(i), bot.get(i)
                if t is None and b is None:
                    continue
                back = c.cells[yy][xx][2] or VOID
                if t is not None and b is not None:
                    c.cells[yy][xx] = ("▀", t, b) if t != b else (" ", None, t)
                elif t is not None:
                    c.cells[yy][xx] = ("▀", t, back)
                else:
                    c.cells[yy][xx] = ("▄", b, back)

    def draw_summary(self, c, g, now, ui):
        self.dimmed(c, g, now, ui, ("end", g.won))
        won = g.won
        st = g.stats
        ws, ups = self.build_lines(g)
        best, deep = ui.get("best", 0), ui.get("deepest", 0)
        lines = [
            ("reached", f"floor {g.floor_label()}  ({BIOMES[g.fi // 3]['name']})"),
            ("time", f"{int(st['time']) // 60}:{int(st['time']) % 60:02d}"),
            ("kills", f"{st['kills']}   bosses {st['bosses']}/3"),
            ("coins", f"{st['coins']} picked up"),
            ("damage", f"{st['dmg']} taken"),
            ("weapons", ws),
            ("build", ups),
            ("score", f"{score_of(g):,}" + ("   new best!" if ui.get("new_best") else f"   best {best:,}")),
        ]
        bw = min(c.w - 4, 70)
        body = []
        for k, v in lines:
            for j, ln in enumerate(wrap(v, bw - 16) or [""]):
                body.append((k if j == 0 else "", ln))
        L = 2 if c.w >= 110 and c.h >= 34 else 1
        wh = (7 * L + 1) // 2
        bh = len(body) + 4
        total = wh + 2 + bh
        y0 = max(1, (c.h - total) // 2)
        if won:
            self.pixel_word(c, c.w / 2, y0, "VICTORY", L,
                            lambda u, v: mix(GOLD_LIT, GOLD_DARK, v) if (u * 9 + now * 2) % 3 > 0.3 else WHITE)
        else:
            self.pixel_word(c, c.w / 2, y0, "YOU DIED", L, lambda u, v: mix((255, 120, 130), (170, 20, 50), v))
        y = y0 + wh + 2
        x0 = (c.w - bw) // 2
        box(c, x0, y - 1, bw, bh, PANEL)
        for i, (k, v) in enumerate(body):
            c.text(x0 + 3, y + i, k, FAINT, PANEL)
            c.text(x0 + 13, y + i, v, TEXT if k in ("score", "reached") else DIM, PANEL)
        foot = "r: new run   enter: title   q: quit"
        c.text((c.w - len(foot)) // 2, y + len(body) + 1, foot, mix(FAINT, TEXT, 0.5 + 0.5 * math.sin(now * 4)), PANEL)
        if won and ui.get("confetti") is None:
            r = random.Random(3)
            ui["confetti"] = [(r.random(), r.uniform(3, 7), r.uniform(0, 40),
                               r.choice((GOLD, (255, 92, 152), CYAN, (180, 130, 255), WHITE))) for _ in range(60)]
        if won:
            for xf, sp, ph, col in ui["confetti"]:
                yy = int((now * sp + ph) % (c.h + 2)) - 1
                xx = int(xf * c.w + math.sin(now * 2 + ph) * 1.5)
                if 0 <= yy < c.h and 0 <= xx < c.w:
                    c.put(xx, yy, "▀▐▄▌"[int(now * 10 + ph) % 4], col)

    # ---------------------------------------------------------------- title
    def title_bg(self, c):
        key = (c.w, c.h, term.TRUECOLOR)
        if self._title is None or self._title[0] != key:
            bio = BIOMES[0]
            H = 2 * c.h
            rows = []
            for y in range(H):
                row = []
                for x in range(c.w):
                    tx, ty = x // T, y // T
                    col = bio["floor"][(tx + ty) & 1]
                    jx, jy = x % T, y % T
                    k = 1.08 if jx == 0 or jy == 0 else 0.88 if jx == T - 1 or jy == T - 1 else 1.0
                    dx, dy = x / max(1, c.w - 1) - 0.5, y / max(1, H - 1) - 0.45
                    k *= 1.15 - 1.5 * (dx * dx + dy * dy) if term.TRUECOLOR else 1.0
                    row.append(mul(col, max(0.25, k)))
                rows.append(row)
            self._title = (key, rows)
        return self._title[1]

    def draw_title(self, c, now, ui):
        if c.w < 60 or c.h < 22:
            return self.too_small(c)
        buf = [r[:] for r in self.title_bg(c)]
        W, H = c.w, 2 * c.h
        big = c.w >= 100 and c.h >= 38
        L = 2 if big else 1
        lines = ("BULLET", "HELL") if big else ("BULLET HELL",)
        y_logo = 2 * (1 if c.h < 44 else 3) + 1
        st = self.st
        # a slow bullet bloom behind the logo
        cx, cy = W / 2, y_logo + (16 if big else 4) * L
        pal = [BULLET_COL[k] for k in ("fly", "turret", "summoner", "sniper", "stinger")]
        for k in range(54):
            age = (now * 0.55 + k * 0.61) % 6.0
            ang = k * 2.39996 + now * 0.12 * (1 if k % 2 else -1)
            r = 6 + age * 19
            x, y = cx + math.cos(ang) * r, cy + math.sin(ang) * r * 0.75
            if 0 <= x < W and 0 <= y < H:
                col = mul(pal[k % len(pal)], 0.6 * clamp01(1.2 - age / 6) * clamp01((H * 0.5 - y) / (H * 0.12)))
                if col[0] + col[1] + col[2] < 30:
                    continue
                solid, halo = st.orb(1.6, col, (0, 0))
                ix, iy = int(x), int(y)
                for dx, dy, rr, gg, bb in halo:
                    px, py = ix + dx, iy + dy
                    if 0 <= px < W and 0 <= py < H:
                        q = buf[py][px]
                        buf[py][px] = (min(255, q[0] + rr), min(255, q[1] + gg), min(255, q[2] + bb))
                for dx, dy, cc in solid:
                    px, py = ix + dx, iy + dy
                    if 0 <= px < W and 0 <= py < H:
                        buf[py][px] = cc
        # logo with a chromatic split, like the original's CRT shader
        stops = ((0.0, (255, 236, 246)), (0.3, (255, 70, 140)), (0.65, (230, 0, 90)), (1.0, (150, 14, 78)))

        def grad(u):
            for (p0, c0), (p1, c1) in zip(stops, stops[1:]):
                if u <= p1:
                    return mix(c0, c1, clamp01((u - p0) / (p1 - p0)))
            return stops[-1][1]
        sweep = (now % 4.0) * 60 - 20
        y = y_logo
        boxes = []
        for word in lines:
            pts, w, h = word_px(word, L)
            x0 = int(W / 2 - w / 2)
            bob = round(math.sin(now * 2.2 + y * 0.1) * (1 if big else 0))
            ring = {(i + a, j + b) for i, j in pts for a in (-1, 0, 1) for b in (-1, 0, 1)} - pts
            for i, j in ring:
                X, Y = x0 + i, y + j + bob
                if 0 <= X < W and 0 <= Y < H:
                    buf[Y][X] = (40, 6, 30)
            for i, j in pts:
                for off, tint in ((-1, (40, 220, 255)), (1, (255, 40, 60))):
                    X, Y = x0 + i + off, y + j + bob
                    if 0 <= X < W and 0 <= Y < H and (i + off, j) not in pts:
                        buf[Y][X] = mix(buf[Y][X], tint, 0.7)
            for i, j in pts:
                X, Y = x0 + i, y + j + bob
                if 0 <= X < W and 0 <= Y < H:
                    col = grad(j / max(1, h - 1))
                    if abs(i - sweep + j * 0.6) < 2:
                        col = mix(col, WHITE, 0.7)
                    buf[Y][X] = col
            boxes.append((x0, y, w, h))
            y += h + 3 * L
        logo_bottom = y
        # the original hero and a fly keep watch either side
        S = self.S
        hero = S.base["hero"]
        lx, ly, lw, lh = boxes[0]
        hx = lx - 14
        hy = ly + lh - 2 if big else ly + 4
        if hx > 4:
            spr = S.get("hero", int(now / 0.1) % 5)
            for dx in range(-4, 5):
                X, Y = int(hx) + dx, int(hy) + 10
                if 0 <= X < W and 0 <= Y < H:
                    buf[Y][X] = mul(buf[Y][X], 0.5)
            for dx, dy, col in spr.px:
                X, Y = int(hx) + dx, int(hy) + dy + round(math.sin(now * 3) * 0.6)
                if 0 <= X < W and 0 <= Y < H:
                    buf[Y][X] = col
            gun = S.get("handgun", 0, False)
            for dx, dy, col in gun.px:
                X, Y = int(hx) + 9 + dx, int(hy) + 2 + dy
                if 0 <= X < W and 0 <= Y < H:
                    buf[Y][X] = col
        rx, ry, rw, rh = boxes[-1]
        fx = rx + rw + 14
        if fx < W - 6:
            spr = S.get("fly", int(now / 0.06) % 3, True)
            fy = ry + rh / 2 + math.sin(now * 2.5) * 3
            for dx, dy, col in spr.px:
                X, Y = int(fx) + dx, int(fy) + dy
                if 0 <= X < W and 0 <= Y < H:
                    buf[Y][X] = col
        for i in range(2):  # stingers circling
            a = now * 1.1 + i * math.pi
            sx, sy = W / 2 + math.cos(a) * (W * 0.42), logo_bottom + 6 + math.sin(a) * 5
            rot = (int(round((a + math.pi / 2) / (math.pi / 2))) % 4) * 4
            spr = S.get("stinger", 0, False, None, rot)
            for dx, dy, col in spr.px:
                X, Y = int(sx) + dx, int(sy) + dy
                if 0 <= X < W and 0 <= Y < H:
                    buf[Y][X] = col
        c.cells = [px_cells(buf[2 * r], buf[2 * r + 1]) for r in range(c.h)]
        y = logo_bottom // 2 + 1
        tag = "a twin-stick dungeon roguelite  ·  after Srijan Paul's bullet_hell"
        if len(tag) > c.w - 2:
            tag = "a twin-stick dungeon roguelite"
        c.text((c.w - len(tag)) // 2, y, tag, DIM)
        y += 2
        # difficulty cards
        cw = min(24, (c.w - 8) // 3)
        x0 = (c.w - (3 * cw + 4)) // 2
        cols = {"easy": (120, 230, 150), "normal": CYAN, "hard": (255, 96, 110)}
        for i, d in enumerate(DIFF_ORDER):
            x = x0 + i * (cw + 2)
            on = ui.get("diff") == d
            col = cols[d]
            back = mix(CARD, col, 0.25) if on else CARD
            box(c, x, y, cw, 4, back)
            if on:
                c.text(x, y, "▗" + "▄" * (cw - 2) + "▖", col)
                c.text(x, y + 3, "▝" + "▀" * (cw - 2) + "▘", col)
                c.put(x + 1, y + 1, "▶", col, back)
            c.text(x + 3, y + 1, d.upper(), WHITE if on else TEXT, back)
            c.text(x + 3, y + 2, DIFFS[d]["blurb"][:cw - 4], col if on else FAINT, back)
        y += 5
        rows = [("WASD", "move"), ("arrows", "shoot (2 = diagonal)"), ("mouse", "aim + hold to shoot"),
                ("space", "dash"), ("f", "swap weapon"), ("e", "buy / pick up"), ("p", "pause"), ("q", "quit")]
        half = (len(rows) + 1) // 2
        colw = 30
        bx = (c.w - 2 * colw) // 2
        if y + half + 4 <= c.h:
            for i, (k, d) in enumerate(rows):
                xx = bx + (i // half) * colw
                yy = y + i % half
                pill(c, xx + 9 - len(k), yy, k, TEXT, KEYCAP)
                c.text(xx + 12, yy, d, DIM)
            y += half + 1
        rec = ui.get("records", "")
        if rec and y < c.h - 2:
            c.text((c.w - len(rec)) // 2, y, rec, FAINT)
            y += 1
        pulse = 0.5 + 0.5 * math.sin(now * 4)
        a = "enter: start run"
        b = "d: daily run" + (f" (seed {ui['daily']})" if ui.get("daily") else "")
        x = (c.w - len(a) - len(b) - 7) // 2
        yy = min(c.h - 2, y + 1)
        x = pill(c, x, yy, a, INK, mix((255, 70, 140), (255, 176, 212), pulse)) + 3
        pill(c, x, yy, b, INK, (110, 170, 250))
        nav = "←/→ difficulty" + (f"  ·  seed {ui['seed']}" if ui.get("seed") is not None else "")
        if yy + 1 < c.h:
            c.text((c.w - len(nav)) // 2, yy + 1, nav, FAINT)

    def too_small(self, c):
        c.cells = [[(" ", None, VOID)] * c.w for _ in range(c.h)]
        lines = wrap("make the terminal bigger (60x22 at least)", max(1, c.w))
        y0 = max(0, (c.h - len(lines)) // 2)
        for i, line_ in enumerate(lines):
            c.text(max(0, (c.w - len(line_)) // 2), y0 + i, line_, DIM)


def score_of(g):
    st = g.stats
    s = st["kills"] * 10 + st["coins"] * 2 + g.fi * 200 + st["bosses"] * 1500 + (5000 if g.won else 0)
    return int(s * g.D["score"])


# ------------------------------------------------------------------------------ input
MOUSE_RE = re.compile(r"\x1b\[<(\d+);(\d+);(\d+)([Mm])")
MOUSE_TAIL = re.compile(r"\x1b(\[(<[\d;]*)?)?$")
MOUSE_ON = "\x1b[?1000h\x1b[?1002h\x1b[?1003h\x1b[?1006h"
MOUSE_OFF = "\x1b[?1006l\x1b[?1003l\x1b[?1002l\x1b[?1000l"
LETTER_DIR = {"w": "up", "a": "left", "s": "down", "d": "right"}


class Hold:
    """Held directions from a terminal that sends only key presses and auto-repeat. A fresh
    press holds until the first repeat could arrive, each repeat extends the hold a little,
    and both gaps are learned from the repeats seen. Only the last key pressed repeats, so a
    key on the other axis that was held when it was pressed rides along (a diagonal)."""

    def __init__(self):
        self.until, self.fresh, self.count, self.last = {}, {}, {}, {}
        self.delay, self.rate = 0.5, 0.11

    def press(self, d, t):
        held = self.until.get(d, 0.0) > t
        late = (not held and self.count.get(d) == 1 and 0 < t - self.until.get(d, -9) < 0.3
                and t - self.fresh.get(d, -9) < 1.2)
        if held or late:  # a repeat (late: the first repeat came after the hold ran out)
            n = self.count[d] = self.count.get(d, 1) + 1
            if n == 2:
                self.delay = clamp(0.5 * self.delay + 0.5 * (t - self.fresh[d] + 0.06), 0.18, 0.8)
            else:
                self.rate = clamp(0.7 * self.rate + 0.3 * ((t - self.last[d]) * 1.8 + 0.015), 0.04, 0.22)
            self.until[d] = t + self.rate
        else:
            self.fresh[d], self.count[d] = t, 1
            self.until[d] = t + self.delay
        self.last[d] = t
        self.until[OPP[d]] = 0.0
        for o in ("up", "down", "left", "right"):
            if o not in (d, OPP[d]) and self.until.get(o, 0.0) > t:
                self.until[o] = max(self.until[o], self.until[d])

    def vector(self, t):
        u = self.until
        return ((u.get("right", 0) > t) - (u.get("left", 0) > t), (u.get("down", 0) > t) - (u.get("up", 0) > t))

    def clear(self):
        self.until.clear()


class Input:
    """Keys, plus SGR mouse reports pulled out of the raw input before key parsing."""

    def __init__(self):
        self.move, self.aim = Hold(), Hold()
        self.mouse, self.button, self.seen, self.tail, self.clicks = None, False, False, "", []

    def filter(self, data):
        data = self.tail + data
        self.tail = ""
        m = MOUSE_TAIL.search(data)
        if m and m.group(2) is not None:  # a report cut off mid-sequence: finish it next frame
            self.tail, data = data[m.start():], data[:m.start()]

        def take(m):
            b, x, y, kind = int(m.group(1)), int(m.group(2)) - 1, int(m.group(3)) - 1, m.group(4)
            self.mouse, self.seen = (x, y), True
            if b & 64:
                return ""  # wheel
            if not b & 32 and b & 3 == 0:
                self.button = kind == "M"
                if kind == "M":
                    self.clicks.append((x, y))
            elif b & 3 == 3 and not b & 32:
                self.button = False
            return ""
        return MOUSE_RE.sub(take, data)


def assist(g, ang):
    """Keyboard aim snaps to the enemy nearest the aimed direction, within about 25 degrees."""
    p = g.player
    best, bd = ang, 0.45
    for e in g.enemies:
        if e.dead or e.spawn > 0:
            continue
        dx, dy = e.x - p.x, e.y - p.y - 1
        if dx * dx + dy * dy > 150 * 150:
            continue
        a = math.atan2(dy, dx)
        da = abs((a - ang + math.pi) % (2 * math.pi) - math.pi)
        if da < bd:
            best, bd = a, da
    return best


# ------------------------------------------------------------------------------ main
def main():
    parser = term.make_parser(__doc__.splitlines()[0], fps=30)
    parser.add_argument("--seed", type=int, default=None, help="fixed run seed")
    parser.add_argument("--daily", action="store_true", help="today's seed")
    parser.add_argument("--difficulty", choices=DIFF_ORDER, default=None, help="easy, normal or hard")
    parser.add_argument("--demo", action="store_true", help="autopilot plays (default without a tty)")
    parser.add_argument("--floor", type=int, default=1, help="start on floor N (1-9)")
    # Fast-forward the demo by this many seconds before the first frame (gallery stills).
    parser.add_argument("--warp", type=float, default=0.0, help=argparse.SUPPRESS)
    args = parser.parse_args()
    fps = max(1.0, args.fps)
    dt = 1 / fps
    interactive = os.isatty(0)
    demo = args.demo or not interactive
    daily = int(time.strftime("%Y%m%d"))
    fixed = daily if args.daily else args.seed
    art = Art()
    sprites = SpriteBank(art)
    view = View(sprites, art)
    sounds = Sounds()
    inp = Input()
    ui = {"diff": args.difficulty or "normal", "seed": fixed, "daily": daily if args.daily else None,
          "minimap": True}
    st = {"mode": "title", "g": None, "ap": None, "paused": False, "done": False, "t_end": 0.0, "log": [],
          "mouse_on": False, "seed": fixed, "runs": 0}
    if demo or args.floor > 1 or args.seed is not None or args.daily or args.difficulty:
        st["mode"] = "play"

    def records():
        b, fl, wins = game.best(NAME), game.best(NAME + "_floor"), game.best(NAME + "_wins")
        if not (b or fl):
            return ""
        lab = f"{(fl - 1) // 3 + 1}-{(fl - 1) % 3 + 1}" if fl else "-"
        return f"best score {b:,}  ·  deepest floor {lab}" + (f"  ·  wins {wins}" if wins else "")

    ui["records"] = records()

    def new_run(c, seed=None):
        if seed is None:
            seed = st["seed"] if st["seed"] is not None else random.randrange(1, 10 ** 6)
            if demo and st["seed"] is None and st["runs"] == 0:
                seed = 1
        st["runs"] += 1
        g = Game(seed, ui["diff"], clamp(args.floor, 1, FLOORS), c.w, c.h, sounds)
        st["g"], st["ap"] = g, Autopilot(g) if demo else None
        st["mode"], st["paused"], st["recorded"] = "play", False, False
        ui.pop("confetti", None)
        ui["new_best"] = False
        view.dim = None
        inp.move.clear()
        inp.aim.clear()

    def finish(g):
        if st.get("recorded"):
            return
        st["recorded"] = True
        sc = score_of(g)
        ui["best"] = game.best(NAME)
        if not demo:  # the autopilot's runs never touch the player's records
            ui["new_best"] = game.record(NAME, sc)
            game.record(NAME + "_floor", g.fi + 1)
            if g.won:
                game.record(NAME + "_wins", game.best(NAME + "_wins") + 1)
            ui["records"] = records()
        st["log"].append(f"seed {g.seed} ({g.diff_name}): {'won' if g.won else 'died on ' + g.floor_label()}, "
                         f"score {sc:,}, {g.stats['kills']} kills in {int(g.stats['time']) // 60}:"
                         f"{int(g.stats['time']) % 60:02d}")
        st["t_end"] = g.time

    def step(c, frame, keys):
        now = frame / fps
        sounds.poll()
        sprites.refresh()
        if interactive and not demo and not st["mouse_on"]:
            sys.stdout.write(MOUSE_ON)
            sys.stdout.flush()
            st["mouse_on"] = True
        if frame % 20 == 0 and not st["done"]:
            st["done"] = game.claude_done()
        t = time.monotonic()
        g = st["g"]
        if st["mode"] == "play" and g is None:
            new_run(c)
            g = st["g"]
            if demo and args.warp > 0:
                for _ in range(int(args.warp / dt)):
                    it = st["ap"].think(dt)
                    if g.mode == "choice" and it.interact:
                        g.choose(g.rng.randrange(len(g.choice)))
                    g.update(dt, it)
                    if g.mode in ("dead", "won"):
                        break
        clicks, inp.clicks = inp.clicks, []
        press = {"dash": False, "interact": False, "swap": False}
        skip = False
        for i, k in enumerate(keys):
            if skip:
                skip = False
                continue
            if k in LETTER_DIR and i + 1 < len(keys) and keys[i + 1] == LETTER_DIR[k]:
                skip = True  # the parser sends WASD twice: the letter, then its arrow name
            if k == "q":
                return True
            mode = st["mode"]
            if mode == "title":
                if k in ("left", "right"):
                    j = DIFF_ORDER.index(ui["diff"]) + (1 if k == "right" else -1)
                    ui["diff"] = DIFF_ORDER[j % 3]
                    sounds.play("tick", 0.5)
                elif k == "d" and skip:
                    st["seed"], ui["seed"] = daily, daily
                    new_run(c, daily)
                elif k in ("enter", "space"):
                    st["seed"], ui["seed"] = fixed, fixed
                    new_run(c)
                continue
            if g is None:
                continue
            if g.mode in ("dead", "won"):
                if g.time - st["t_end"] > 0.8:
                    if k == "r":
                        new_run(c)
                    elif k == "enter":
                        st["mode"], st["g"] = "title", None
                continue
            if g.mode == "choice":
                n = len(g.choice or ())
                if k in ("left", "right"):
                    g.choice_sel = (g.choice_sel + (1 if k == "right" else -1)) % max(1, n)
                    sounds.play("tick", 0.4)
                elif k in ("1", "2", "3"):
                    g.choose(int(k) - 1)
                elif k in ("enter", "space", "e") and g.time - g.choice_t > 0.35:
                    g.choose(g.choice_sel)
                continue
            if k in ("p", "esc"):
                st["paused"] = not st["paused"]
                view.dim = None
                continue
            if st["paused"]:
                if k == "r":
                    new_run(c)
                continue
            if k in LETTER_DIR:
                inp.move.press(LETTER_DIR[k], t)
            elif k in ("up", "down", "left", "right"):
                inp.aim.press(k, t)
                ui["aim_hint"] = True
            elif k == "space":
                press["dash"] = True
            elif k in ("e", "enter"):
                press["interact"] = True
            elif k in ("f", "\t"):
                press["swap"] = True
        if st["mode"] == "title" or g is None:
            view.draw_title(c, now, ui)
            return done_pill(c, st)
        if not getattr(term, "_focused", True) and g.mode == "play" and not demo:
            st["paused"] = True
        if c.w < 60 or c.h < 22:
            view.too_small(c)
            return False
        ox, oy, _ = view.layout(c, g)
        if g.mode == "choice":
            for mx, my in clicks:
                for i, (x, y, w, h) in enumerate(ui.get("cards", [])):
                    if x <= mx < x + w and y <= my < y + h:
                        g.choose(i)
                        break
        if st["paused"]:
            view.draw_pause(c, g, now, ui)
            return done_pill(c, st)
        if st["ap"]:
            it = st["ap"].think(dt)
            if g.mode == "choice" and it.interact:
                g.choose(g.rng.randrange(len(g.choice)))
        else:
            it = Intent()
            it.mx, it.my = inp.move.vector(t)
            ax, ay = inp.aim.vector(t)
            if ax or ay:
                it.aim, it.fire = assist(g, math.atan2(ay, ax)), True
            elif inp.seen and inp.mouse:
                mx, my = inp.mouse
                px, py = mx - ox + 0.5, 2 * (my - oy) + 1
                p = g.player
                if abs(px - p.x) + abs(py - p.y) > 2:
                    it.aim = math.atan2(py - p.y - 1, px - p.x)
                it.fire = inp.button
                ui["aim_hint"] = False
            it.dash, it.interact, it.swap = press["dash"], press["interact"], press["swap"]
        ui["mouse_at"], ui["mouse_seen"] = inp.mouse, inp.seen and not demo
        g.update(dt, it)
        if g.mode in ("dead", "won"):
            finish(g)
            if demo and g.time - st["t_end"] > 5:
                new_run(c, g.seed + 1)
                g = st["g"]
        if g.mode == "choice":
            view.draw_choice(c, g, now, ui)
        elif g.mode in ("dead", "won"):
            view.draw_summary(c, g, now, ui)
        else:
            view.draw_play(c, g, now, ui)
        return done_pill(c, st)

    try:
        game.play(args, step, input_filter=inp.filter)
    finally:
        if st["mouse_on"]:
            sys.stdout.write(MOUSE_OFF)
            sys.stdout.flush()
    g = st["g"]
    if g and g.mode not in ("dead", "won") and g.stats["time"] > 5:
        st["log"].append(f"seed {g.seed} ({g.diff_name}): quit on floor {g.floor_label()}, score {score_of(g):,}")
        if not demo:
            game.record(NAME, score_of(g))
            game.record(NAME + "_floor", g.fi + 1)
    for line_ in st["log"]:
        print(f"bullethell: {line_}")
    if art.errors and art.state == "failed":
        print(f"bullethell: couldn't fetch the original art ({art.errors[0]}); drew stand-ins", file=sys.stderr)
    return 0


def done_pill(c, st):
    if st["done"] and c.w >= 18:
        msg = "Claude's done!"
        pill(c, c.w - len(msg) - 3, 1, msg, INK, (120, 222, 140))
    return False


if __name__ == "__main__":
    sys.exit(main())
