#!/usr/bin/env python3
"""Bonkyon: steer two friends with one set of keys; grab every coin without a bonk.

Usage: python3 bonkyon.py [--fps 30] [--frames N] [--level N] [--solve]
       python3 bonkyon.py --endless [--seed S | --daily] [--rule R]   |   --gen-check N
Each level has a movement rule for Pop, shown in the HUD:
  mirror  left moves Pip left and Pop right; up moves Pip up and Pop down
  copy    Pop moves the same way as Pip
  flip-x  left/right mirrored, up/down copied
  flip-y  up/down mirrored, left/right copied
A friend blocked by a wall stays put while the other still moves. Bumping into
each other restarts.
  --level N      start at level N (skips the title screen)
  --solve        BFS every level, print its minimum moves, and exit
  --endless      endless generated levels, 3 lives
Title screen: ←/→ (a/d) or 1-4 pick a rule card; enter/space plays that rule's first
unlocked level; `e` endless with that rule, `x` mixed endless; any other key plays the
offered level.
  --seed S       endless seed (default random, shown in the HUD); --daily uses today's
  --rule R       endless with one rule throughout (default: mirror first, then mixed)
  --gen-check N  generate endless depths 1..N, print par/size/ms, check all solvable
"""

META = {'name': 'bonkyon',
 'kind': 'play',
 'blurb': 'Steer two friends who mirror or copy your moves and grab every coin',
 'credit': [{'type': 'inspired by',
             'who': 'Bonkyon by Srijan Paul (injuly)',
             'url': 'https://injuly.itch.io/bonkyon'},
            {'type': 'taken from',
             'who': 'Bonkyon sound assets via Srijan Paul (injuly), MIT',
             'url': 'https://github.com/srijan-paul/Bonkyon'},
            {'type': 'taken from',
             'who': '8bit blix (aka Lost Moons) by Questiion / Micah Young, CC BY 4.0, converted to AAC',
             'url': 'https://freesound.org/people/Questiion/sounds/166392/'},
            {'type': 'taken from',
             'who': '8-bit Game Over by Euphrosyyn, CC BY 4.0',
             'url': 'https://freesound.org/people/Euphrosyyn/sounds/442127/'},
            {'type': 'taken from',
             'who': 'button-04 by JarredGibb, CC0',
             'url': 'https://freesound.org/people/JarredGibb/sounds/219477/'},
            {'type': 'taken from',
             'who': 'positive-beeps by themusicalnomad, CC0',
             'url': 'https://freesound.org/people/themusicalnomad/sounds/253887/'},
            {'type': 'taken from',
             'who': 'swosh-01 by qubodup, CC0',
             'url': 'https://freesound.org/people/qubodup/sounds/59988/'},
            {'type': 'taken from',
             'who': 'Swosh 42 by qubodup, CC0',
             'url': 'https://freesound.org/people/qubodup/sounds/60029/'}]}

import argparse
import hashlib
import math
import random
import statistics
import sys
import time
from collections import deque

import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

from fun import audio, game, term

# Srijan Paul's original sounds, fetched on first run with sound (never vendored here).
SOUND_BASE = os.environ.get("CLAUDE_FUN_BONKYON_SOUNDS",
                            "https://raw.githubusercontent.com/srijan-paul/Bonkyon/master/assets/sounds/")
SOUND_FILES = {
    "music": "166392__questiion__8bit-blix-aka-lost-moons-make-me-a-game-snippet-notify-if-longer-version-is-needed.wav",
    "gameover": "442127__euphrosyyn__8-bit-game-over.wav",
    "button": "219477__jarredgibb__button-04.wav",
    "beeps": "253887__themusicalnomad__positive-beeps.wav",
    "undo": "59988__qubodup__swosh-01-44-1khz.flac",
    "restart": "60029__qubodup__swosh-42.flac",
    "jump": "Jump.wav",
}
SYNTH_STANDIN = {"music": "bonkyon", "gameover": "gameover", "button": "tick", "beeps": "coin",
                 "undo": "swoosh", "restart": "swoosh", "jump": "hop"}

DIRS = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}
ARROW = {"up": "^", "down": "v", "left": "<", "right": ">"}

# Movement rules: (x, y) multipliers applied to Pip's step to get Pop's, plus HUD glyph
# and a one-line description.
RULES = {
    "mirror": ((-1, -1), "⇄⇅", "Pop mirrors Pip"),
    "copy": ((1, 1), "⇉", "Pop copies Pip"),
    "flip-x": ((-1, 1), "⇄", "Pop mirrors left/right, copies up/down"),
    "flip-y": ((1, -1), "⇅", "Pop mirrors up/down, copies left/right"),
}

# Legend: # wall  . floor  o coin  A Pip  B Pop  ^ spikes  % cracked floor
# (name, hint, par, rows[, rule]). rule defaults to "mirror". par is the BFS minimum;
# --solve checks it. Unlocks and stars are saved by index, so only append levels.
LEVELS = [
    ("mirror", "left sends Pip left and Pop right", 2, [
        "##########",
        "#o.A..B.o#",
        "##########",
    ]),
    ("corners", "up sends Pip up and Pop down", 6, [
        "#########",
        "#o.....o#",
        "#..A....#",
        "#....B..#",
        "#o.....o#",
        "#########",
    ]),
    ("lean on it", "a friend against a wall stays put while the other moves", 5, [
        "#######",
        "#.....#",
        "#.....#",
        "#A.o.B#",
        "#.....#",
        "#######",
    ]),
    ("two rooms", "either friend can grab any coin", 6, [
        "#############",
        "#o....#....o#",
        "#..A..#.....#",
        "#.....#.#B..#",
        "#o....#.....#",
        "#############",
    ]),
    ("pointy", "spikes hurt, whoever steps on them", 9, [
        "#########",
        "#o.....o#",
        "#.......#",
        "#^.A.B..#",
        "#.....^.#",
        "#########",
    ]),
    ("hedgehogs", "where will the other one land?", 12, [
        "###########",
        "#o.......o#",
        "#.#.......#",
        "#...A.B..^#",
        "#^........#",
        "#o.......o#",
        "###########",
    ]),
    ("pillars", "two rooms, one plan", 15, [
        "###############",
        "#.....#......o#",
        "#.....#.......#",
        "#.A...#..o#B..#",
        "#...#o#o......#",
        "###############",
    ]),
    ("thin ice", "cracked floor falls away once you step off it", 9, [
        "#############",
        "#.o.#...#...#",
        "#.%.#.A.#...#",
        "#...%...%.B.#",
        "#...#...#.%.#",
        "#...#...#.o.#",
        "#############",
    ]),
    ("crumbs", "a fallen tile is a brand new wall", 16, [
        "#############",
        "#o....#....o#",
        "#.....#..o%.#",
        "#.........A.#",
        "#.....#.%B..#",
        "#.....#..o..#",
        "#############",
    ]),
    ("long way round", "take your time", 18, [
        "#############",
        "#.....#.....#",
        "#.....#.%A%.#",
        "#.........B.#",
        "#.....#.o..##",
        "#o....#o...o#",
        "#############",
    ]),
    ("in step", "new rule: Pop copies Pip, so you march in step", 6, [
        "##########",
        "#A..o..o.#",
        "#B..o..o.#",
        "##########",
    ], "copy"),
    ("squeeze", "a wall holds one back while the other walks on", 7, [
        "#########",
        "#A.B....#",
        "#.......#",
        "######.##",
        "######o##",
        "######o##",
        "#########",
    ], "copy"),
    ("formation", "lean on a wall to change formation and dodge the spikes", 15, [
        "###########",
        "#........o#",
        "#..^......#",
        "#.....#...#",
        "#...#....B#",
        "#o.....^..#",
        "#......A.o#",
        "###########",
    ], "copy"),
    ("side by side", "new rule: left/right mirrored, up/down together", 4, [
        "#########",
        "#o.....o#",
        "#.......#",
        "#..A.B..#",
        "#########",
    ], "flip-x"),
    ("crossing", "up and down move you both the same way", 14, [
        "#############",
        "#o....#...o.#",
        "#..#......^.#",
        "#.....#....B#",
        "#.^...#..#..#",
        "#..A..#o.o..#",
        "#############",
    ], "flip-x"),
    ("up and over", "new rule: up/down mirrored, left/right together", 6, [
        "#######",
        "#o...o#",
        "#.A...#",
        "#.....#",
        "#.B...#",
        "#o...o#",
        "#######",
    ], "flip-y"),
    ("tide", "last one: up is down, left is left", 14, [
        "###########",
        "#.....A...#",
        "#..#...^..#",
        "#o......B.#",
        "####.####o#",
        "#.o.......#",
        "#..^...#..#",
        "#.o.......#",
        "###########",
    ], "flip-y"),
]

WALL, FLOOR, COIN, SPIKE, CRACK = "#", ".", "o", "^", "%"


class Level:
    def __init__(self, idx, name, hint, par, rows, rule="mirror"):
        self.idx, self.name, self.hint, self.par = idx, name, hint, par
        self.rule = rule
        self.mx, self.my = RULES[rule][0]
        self.h, self.w = len(rows), max(len(r) for r in rows)
        self.tiles = {}
        coins, cracks = [], []
        for y, row in enumerate(rows):
            for x, ch in enumerate(row):
                p = (x, y)
                if ch == "A":
                    self.a, ch = p, FLOOR
                elif ch == "B":
                    self.b, ch = p, FLOOR
                elif ch == COIN:
                    coins.append(p)
                    ch = FLOOR
                elif ch == CRACK:
                    cracks.append(p)
                self.tiles[p] = ch
        self.coin_bit = {p: 1 << i for i, p in enumerate(coins)}
        self.crack_bit = {p: 1 << i for i, p in enumerate(cracks)}
        self.start = (self.a, self.b, (1 << len(coins)) - 1, 0)

    def blocked(self, p, fallen):
        t = self.tiles.get(p, WALL)
        return t == WALL or (t == CRACK and fallen & self.crack_bit[p])

    def go(self, p, dx, dy, fallen):
        q = (p[0] + dx, p[1] + dy)
        return p if self.blocked(q, fallen) else q

    def move(self, st, d):
        """Apply one input. Returns (new_state, outcome); outcome is None, "bonk", "ouch" or "clear"."""
        a, b, coins, fallen = st
        dx, dy = DIRS[d]
        na, nb = self.go(a, dx, dy, fallen), self.go(b, self.mx * dx, self.my * dy, fallen)
        if na == nb or (na == b and nb == a):
            return (na, nb, coins, fallen), "bonk"
        if self.tiles[na] == SPIKE or self.tiles[nb] == SPIKE:
            return (na, nb, coins, fallen), "ouch"
        for old, new in ((a, na), (b, nb)):
            if old != new and old in self.crack_bit:
                fallen |= self.crack_bit[old]
            coins &= ~self.coin_bit.get(new, 0)
        return (na, nb, coins, fallen), ("clear" if coins == 0 else None)


LV = [Level(i, *spec) for i, spec in enumerate(LEVELS)]


def solve(lv, limit=None, max_depth=None):
    """BFS over (pip, pop, coins, fallen). Returns (moves list or None, states seen).
    Gives up (None) past `limit` states or `max_depth` moves."""
    prev = {lv.start: None}
    q = deque([(lv.start, 0)])
    while q:
        st, n = q.popleft()
        if (max_depth is not None and n >= max_depth) or (limit and len(prev) > limit):
            break
        for d in DIRS:
            nst, out = lv.move(st, d)
            if out in ("bonk", "ouch") or nst in prev or nst == st:
                continue
            prev[nst] = (st, d)
            if out == "clear":
                path = []
                while prev[nst]:
                    nst, d = prev[nst]
                    path.append(d)
                return path[::-1], len(prev)
            q.append((nst, n + 1))
    return None, len(prev)


def run_solver():
    ok = True
    for lv in LV:
        path, seen = solve(lv)
        if path is None:
            ok = False
            print(f"{lv.idx + 1:2} {lv.name:<14} {lv.rule:<6} UNSOLVABLE ({seen} states)")
            continue
        flag = "" if len(path) == lv.par else f"  <- par says {lv.par}"
        ok &= not flag
        print(f"{lv.idx + 1:2} {lv.name:<14} {lv.rule:<6} par {len(path):2}  {seen:6} states  "
              f"{''.join(ARROW[d] for d in path)}{flag}")
    return 0 if ok else 1


# Wall shapes as (dx, dy) offsets, stamped at random interior spots.
SHAPES = [
    [(0, 0)], [(0, 0)], [(0, 0), (1, 0)], [(0, 0), (0, 1)], [(0, 0), (1, 0), (2, 0)],
    [(0, 0), (0, 1), (0, 2)], [(0, 0), (1, 0), (0, 1)], [(0, 0), (1, 0), (1, 1)],
    [(0, 0), (1, 0), (0, 1), (1, 1)],
]
UNDO_COST = 5  # endless points lost per undo
GEN_LIMIT = 12000  # BFS states per attempt; bigger spaces are rejected


def depth_rng(seed, depth):
    # sha256, not hash(): str hashing is salted per process, which would break shared seeds.
    h = hashlib.sha256(f"bonkyon:{seed}:{depth}".encode()).digest()
    return random.Random(int.from_bytes(h[:8], "big"))


def depth_rule(seed, depth):
    """Endless rule for a depth: mirror until depth 4, then others grow more likely.
    Its own hash stream, so mirror depths generate the same boards as a mirror-only game."""
    if depth < 4:
        return "mirror"
    h = hashlib.sha256(f"bonkyon-rule:{seed}:{depth}".encode()).digest()
    r = random.Random(int.from_bytes(h[:8], "big"))
    if r.random() < max(0.35, 0.8 - 0.05 * depth):
        return "mirror"
    return r.choice(["copy", "flip-x", "flip-y"])


def par_window(depth):
    return min(15, 3 + round(0.8 * depth)), min(25, 6 + round(1.25 * depth))


def desyncs(lv, path):
    """Moves on the path where exactly one friend is held back by a wall."""
    st, n = lv.start, 0
    for d in path:
        nst, _ = lv.move(st, d)
        n += (nst[0] == st[0]) != (nst[1] == st[1])
        st = nst
    return n


def reach(tiles, p):
    seen, todo = {p}, [p]
    while todo:
        x, y = todo.pop()
        for dx, dy in DIRS.values():
            q = (x + dx, y + dy)
            if q not in seen and tiles.get(q, WALL) not in (WALL, SPIKE):
                seen.add(q)
                todo.append(q)
    return seen


def gen_rows(rng, depth):
    """One random candidate: walls plus a few stamped shapes, then starts, coins, hazards."""
    w = min(13, 5 + depth // 2 + rng.randint(0, 1))
    h = min(6, 3 + depth // 4 + rng.randint(0, 1))
    grid = [[FLOOR] * w for _ in range(h)]
    cells = [(x, y) for y in range(h) for x in range(w)]
    for _ in range(rng.randint(1, 2) + w * h // max(6, 14 - depth // 2)):
        if rng.random() < 0.6:
            ox, oy = rng.choice(cells)
            for dx, dy in rng.choice(SHAPES):
                if 0 <= ox + dx < w and 0 <= oy + dy < h:
                    grid[oy + dy][ox + dx] = WALL
        else:
            x, y = rng.choice(cells)
            grid[y][x] = WALL
    free = [(x, y) for x, y in cells if grid[y][x] == FLOOR]
    ncoin = min(6, 2 + depth // 4 + rng.randint(0, 1))
    nspike = rng.randint(1, min(4, 1 + depth // 6)) if depth >= 4 and rng.random() < 0.6 else 0
    ncrack = rng.randint(1, 2 + (depth >= 12)) if depth >= 7 and rng.random() < 0.5 else 0
    if len(free) < ncoin + nspike + ncrack + 4:
        return None
    picks = rng.sample(free, ncoin + nspike + ncrack + 2)
    for i, (x, y) in enumerate(picks):
        grid[y][x] = ("A" if i == 0 else "B" if i == 1 else COIN if i < 2 + ncoin
                      else SPIKE if i < 2 + ncoin + nspike else CRACK)
    return ["#" * (w + 2)] + ["#" + "".join(r) + "#" for r in grid] + ["#" * (w + 2)]


def gen_level(seed, depth, rule=None):
    """Deterministic level for (seed, depth). rule=None picks depth_rule's.
    Returns (Level, attempts, states searched)."""
    rule = rule or depth_rule(seed, depth)
    rng = depth_rng(seed, depth)
    lo, hi = par_window(depth)
    need = 1 + (depth >= 8)
    tries = states = 0
    while True:
        tries += 1
        # Loosen the window gradually so an unlucky seed can't spin for long.
        slack = tries // 60
        rows = gen_rows(rng, depth)
        if rows is None:
            continue
        lv = Level(depth, f"depth {depth}", "", 0, rows, rule)
        ok = reach(lv.tiles, lv.a) | reach(lv.tiles, lv.b)
        if any(p not in ok for p in lv.coin_bit):
            continue
        path, seen = solve(lv, GEN_LIMIT, hi + slack)
        states += seen
        if path is None or len(path) < lo - slack or desyncs(lv, path) < need:
            continue
        lv.par = len(path)
        kinds = [n for t, n in ((SPIKE, "spikes"), (CRACK, "cracked floor"))
                 if t in lv.tiles.values()]
        lv.hint = (f"{len(lv.coin_bit)} coins, mind the " + " and ".join(kinds) if kinds
                   else f"{len(lv.coin_bit)} coins: lean on walls to desync")
        return lv, tries, states


def run_gen_check(n, seed, rule=None):
    times, ok = [], True
    print(f"seed {seed}" + (f"  rule {rule}" if rule else ""))
    for k in range(1, n + 1):
        t = time.perf_counter()
        lv, tries, states = gen_level(seed, k, rule)
        ms = (time.perf_counter() - t) * 1000
        times.append(ms)
        path, _ = solve(lv)
        lo, hi = par_window(k)
        good = path is not None and len(path) == lv.par
        ok &= good
        tiles = "".join(sorted(t for t in lv.tiles.values() if t in (SPIKE, CRACK)))
        print(f"depth {k:2}  {lv.rule:<6}  par {lv.par:2} (window {lo:2}-{hi:2})  {lv.w - 2:2}x{lv.h - 2}  "
              f"coins {len(lv.coin_bit)}  {tiles:<7} desync {desyncs(lv, path or []):2}  "
              f"tries {tries:3}  states {states:6}  {ms:6.1f} ms{'' if good else '  FAIL'}")
    q = statistics.quantiles(times, n=10) if len(times) > 1 else times * 9
    print(f"gen ms: min {min(times):.1f}  median {statistics.median(times):.1f}  "
          f"p90 {q[-1]:.1f}  max {max(times):.1f}")
    assert ok, "some generated level failed to re-solve"
    return 0


def stars(moves, par):
    return 3 if moves <= par else 2 if moves <= par + max(2, par // 4) else 1


# ------------------------------------------------------------------------------ look
# Presentation only: everything from here to main() reads game state and never changes it.
# Pixels are half-block cells ("▀", fg = top pixel, bg = bottom), so a cell is 1x2 pixels
# and a tile of th rows is S = 2*th pixels (and columns) square.

SLIDE, BUMP, UNDO_T, DROP_T = 0.12, 0.16, 0.14, 0.42  # animation lengths, seconds


def clamp01(t):
    return 0.0 if t < 0 else 1.0 if t > 1 else t


def ease_out(t):
    t = clamp01(t)
    return 1 - (1 - t) ** 3


def back_out(t):
    t = clamp01(t) - 1
    return 1 + 2.70158 * t * t * t + 1.70158 * t * t


def bounce_out(t):
    t = clamp01(t)
    if t < 1 / 2.75:
        return 7.5625 * t * t
    if t < 2 / 2.75:
        t -= 1.5 / 2.75
        return 7.5625 * t * t + .75
    if t < 2.5 / 2.75:
        t -= 2.25 / 2.75
        return 7.5625 * t * t + .9375
    t -= 2.625 / 2.75
    return 7.5625 * t * t + .984375


def mix(a, b, t):
    return (int(a[0] + (b[0] - a[0]) * t), int(a[1] + (b[1] - a[1]) * t), int(a[2] + (b[2] - a[2]) * t))


def mul(c, k):
    return (min(255, int(c[0] * k)), min(255, int(c[1] * k)), min(255, int(c[2] * k)))


def grad(stops, u):
    for (p0, c0), (p1, c1) in zip(stops, stops[1:]):
        if u <= p1:
            return mix(c0, c1, clamp01((u - p0) / (p1 - p0)))
    return stops[-1][1]


BG_TOP, BG_BOT, BG_FLAT = (38, 50, 92), (17, 21, 44), (24, 29, 56)
FLOOR_RGB = ((68, 74, 114), (59, 65, 101))
WALL_CAP = ((112, 104, 162), (106, 98, 154))
WALL_LIT, WALL_FACE, WALL_MORTAR = (164, 154, 212), (78, 70, 120), (54, 48, 88)
PLATE, STEEL_LIT, STEEL_DARK = (96, 44, 62), (232, 236, 246), (124, 130, 156)
SAND, CRACK_INK = ((172, 136, 96), (162, 128, 90)), (82, 58, 42)
PIT, PIT_WALL = (10, 9, 18), (92, 70, 52)
GOLD = ((255, 200, 54), (255, 240, 164), (206, 132, 26), (176, 104, 20), (232, 160, 34))
PINK = (240, 92, 152)
INK, TEXT, DIM, FAINT = (24, 18, 36), (236, 238, 255), (150, 158, 200), (104, 112, 156)
KEYCAP, CARD, PANEL = (58, 66, 112), (40, 48, 90), (34, 28, 66)
STAR_ON, STAR_OFF = (255, 214, 72), (84, 84, 120)
EYE_W, EYE_P = (250, 250, 255), (24, 22, 38)
LEAF, LEAF_LIT, STEM = (104, 196, 84), (168, 232, 120), (120, 84, 46)
RULE_COL = {"mirror": (240, 92, 152), "copy": (92, 204, 132), "flip-x": (244, 172, 64),
            "flip-y": (156, 126, 244)}
CONFETTI = ((255, 92, 152), (255, 210, 72), (92, 214, 240), (120, 222, 120), (180, 130, 255),
            (255, 150, 70), (250, 250, 255))
# Pip is a tangerine with a leaf, Pop a teal critter with ears.
FRIEND = (
    {"body": (255, 146, 58), "lit": (255, 200, 124), "dark": (210, 88, 36), "spec": (255, 240, 210),
     "feat": "leaf", "ink": (255, 166, 90)},
    {"body": (62, 196, 230), "lit": (156, 236, 252), "dark": (30, 122, 180), "spec": (226, 252, 255),
     "feat": "ears", "ink": (110, 214, 240)},
)
# S: (width, height, rows under the body for its shadow, eye pixel row from the tile top,
# eye columns). The eye row is even so eyes sit on whole cells when the friend is at rest.
BODY = {2: (2, 2, 0, 0, (0, 1)), 4: (4, 3, 0, 2, (1, 2)), 6: (6, 4, 1, 2, (1, 4)),
        8: (6, 5, 1, 4, (2, 5))}
COIN_D = {4: 2, 6: 4, 8: 6}

_bg = {}


def bg_px(w, hp):
    """Background pixels: a vertical gradient with a soft vignette (flat without truecolor,
    where nearest-256 gradients band). Only the latest size is kept."""
    key = (w, hp, term.TRUECOLOR)
    if key not in _bg:
        _bg.clear()
        rows = []
        for y in range(hp):
            u = y / max(1, hp - 1)
            if not term.TRUECOLOR:
                rows.append([BG_FLAT] * w)
                continue
            base, vy = mix(BG_TOP, BG_BOT, u), (u - 0.42) ** 2 * 0.9
            rows.append([mul(base, 1 - 0.55 * ((x / max(1, w - 1) - 0.5) ** 2 * 1.6 + vy))
                         for x in range(w)])
        _bg[key] = rows
    return _bg[key]


def px_cells(top, bot):
    return [(" ", None, t) if t == b else ("▀", t, b) for t, b in zip(top, bot)]


# Spike pixel art per tile size: a pyramid with a lit (L) and shaded (D) face, a glinting
# tip (H), dim back spikes (b) and a shadow (s) on the plate.
SPIKE_PX = {
    4: [".HD.", ".LD.", "LLDD", "ssss"],
    6: ["..HD..", "b.LD.b", "bLLDDb", ".LLDD.", "LLLDDD", "ssssss"],
    8: ["...HD...", "...LD...", "b.LLDD.b", "b.LLDD.b", ".LLLDDD.", ".LLLDDD.", "LLLLDDDD", "ssssssss"],
}


def crack_cells(x, y, th):
    """Crack glyphs for one tile as {(col, row): glyph}: random walks down the cell corners,
    so neighbouring diagonals join up. Seeded by position, so a tile keeps its cracks."""
    rng = random.Random(x * 131 + y * 17 + th)
    tw, out = 2 * th, {}
    starts = [rng.randint(1, tw - 1)] + ([rng.randint(0, tw)] if th >= 2 else [])
    for cx in starts:
        for cy in range(th):
            if (rng.random() < 0.5 or cx == 0) and cx < tw:
                cell, ch, cx = (cx, cy), "╲", cx + 1
            else:
                cell, ch, cx = (cx - 1, cy), "╱", cx - 1
            out[cell] = "╳" if out.get(cell, ch) != ch else ch
    return out


def build_board(w, h, lv, fallen, th, ox, oy):
    """Static frame for a level: background, board drop shadow and every tile.
    Returns (pixel rows, cell rows)."""
    S, hp = 2 * th, 2 * h
    base = [r[:] for r in bg_px(w, hp)]
    X0, Y0, W, H = ox, 2 * oy, lv.w * S, lv.h * S
    for y in range(max(0, Y0 + 2), min(hp, Y0 + H + 3)):
        row = base[y]
        for x in range(max(0, X0 + 2), min(w, X0 + W + 2)):
            row[x] = mul(row[x], 0.5 if y < Y0 + H + 2 and x < X0 + W + 1 else 0.72)
    tiles, glyphs = lv.tiles, {}

    def wall(x, y):
        return tiles.get((x, y)) == WALL

    def put(x, y, col):
        if 0 <= x < w and 0 <= y < hp:
            base[y][x] = col

    for (x, y), t in tiles.items():
        px, py = X0 + x * S, Y0 + y * S
        if t == WALL:
            up, down, left, right = wall(x, y - 1), wall(x, y + 1), wall(x - 1, y), wall(x + 1, y)
            face = 0 if down else max(1, S // 2)
            cap = WALL_CAP[(x + y) & 1]
            for j in range(S):
                for i in range(S):
                    if j < S - face:
                        if j == 0 and not up:
                            col = WALL_LIT
                        elif i == 0 and not left:
                            col = mul(cap, 1.07)
                        elif i == S - 1 and not right:
                            col = mul(cap, 0.88)
                        else:
                            col = cap
                    else:
                        jj = j - (S - face)
                        col = mul(WALL_FACE, 1.18) if jj == 0 else mul(WALL_FACE, 1 - 0.14 * jj / face)
                        course = (jj - 1) // 2
                        if S >= 6 and jj > 0 and (px + i + 3 * (course & 1)) % 6 == 0:
                            col = WALL_MORTAR
                        elif S >= 8 and jj > 1 and (jj - 1) % 2 == 0:
                            col = mul(col, 0.86)
                    put(px + i, py + j, col)
            continue
        if t == CRACK and fallen & lv.crack_bit[(x, y)]:
            rim = max(1, S // 3)
            for j in range(S):
                for i in range(S):
                    col = (mix(PIT_WALL, mul(PIT_WALL, 0.5), j / rim) if j < rim
                           else mix(PIT, (30, 22, 30), (j - rim) / S))
                    put(px + i, py + j, mul(col, 0.8) if i in (0, S - 1) else col)
            continue
        sand = t == CRACK
        c0 = SAND[(x + y) & 1] if sand else FLOOR_RGB[(x + y) & 1]
        ao_top, ao_left = wall(x, y - 1), wall(x - 1, y)
        for j in range(S):
            for i in range(S):
                if S >= 4 and (i == S - 1 or j == S - 1):
                    k = 0.88
                else:
                    k = 1.04 - 0.08 * (i + j) / max(1, 2 * S - 2)
                    if S >= 6 and (i == 0 or j == 0):
                        k += 0.05
                if ao_top and j < max(1, S // 3):
                    k *= 0.6 + 0.3 * j / max(1, S // 3)
                if ao_left and i == 0 and S >= 4:
                    k *= 0.85
                put(px + i, py + j, mul(c0, k))
        if t == SPIKE:
            inset = 1 if S >= 4 else 0
            for j in range(inset, S - inset):
                for i in range(inset, S - inset):
                    rim = i in (inset, S - 1 - inset) or j in (inset, S - 1 - inset)
                    put(px + i, py + j, mix(base[py + j][px + i], mul(PLATE, 0.8 if rim else 1), 0.7))
        cy0 = oy + y * th
        if t == SPIKE and S == 2:
            if 0 <= px + 1 < w and 0 <= cy0 < h:
                glyphs[(px, cy0)] = ("▟", STEEL_LIT, base[2 * cy0 + 1][px])
                glyphs[(px + 1, cy0)] = ("▙", STEEL_DARK, base[2 * cy0 + 1][px + 1])
        elif t == SPIKE:
            for j, row in enumerate(SPIKE_PX[S]):
                for i, ch in enumerate(row):
                    if ch == "s":
                        put(px + i, py + j, mul(base[py + j][px + i], 0.6))
                    elif ch == "b":
                        put(px + i, py + j, mul(STEEL_DARK, 0.72))
                    elif ch != ".":
                        put(px + i, py + j, (255, 255, 255) if ch == "H" else
                            mul(STEEL_LIT if ch == "L" else STEEL_DARK, 0.84 + 0.16 * j / S))
        elif sand:
            for (ci, r), ch in crack_cells(x, y, th).items():
                cx, cy = px + ci, cy0 + r
                if 0 <= cx < w and 0 <= cy < h:
                    glyphs[(cx, cy)] = (ch, CRACK_INK, mix(base[2 * cy][cx], base[2 * cy + 1][cx], 0.5))
    cells = [px_cells(base[2 * r], base[2 * r + 1]) for r in range(h)]
    for (cx, cy), cell in glyphs.items():
        cells[cy][cx] = cell
    return base, cells


class Layer:
    """Sprites over a cached static frame. px() sets one half-block pixel; compose() rebuilds
    only the cells those pixels touch, then glyph() cells go on top."""

    __slots__ = ("base", "cells", "ov", "gl", "w", "hp")

    def __init__(self, base, cells):
        self.base, self.cells, self.ov, self.gl = base, cells, {}, []
        self.w, self.hp = len(base[0]), len(base)

    def get(self, x, y):
        c = self.ov.get((x, y))
        return self.base[y][x] if c is None else c

    def px(self, x, y, col):
        if 0 <= x < self.w and 0 <= y < self.hp:
            self.ov[(x, y)] = col

    def blend(self, x, y, col, a):
        if 0 <= x < self.w and 0 <= y < self.hp:
            self.ov[(x, y)] = mix(self.get(x, y), col, a)

    def dark(self, x, y, k):
        if 0 <= x < self.w and 0 <= y < self.hp:
            self.ov[(x, y)] = mul(self.get(x, y), k)

    def glyph(self, x, y, ch, fg, bg=None):
        self.gl.append((x, y, ch, fg, bg))

    def compose(self, c):
        cells, base, ov, done = self.cells, self.base, self.ov, set()
        for x, y in ov:
            r = y >> 1
            if (x, r) in done:
                continue
            done.add((x, r))
            t, b = ov.get((x, 2 * r)), ov.get((x, 2 * r + 1))
            t = base[2 * r][x] if t is None else t
            b = base[2 * r + 1][x] if b is None else b
            cells[r][x] = (" ", None, t) if t == b else ("▀", t, b)
        for x, y, ch, fg, bg in self.gl:
            c.put(x, y, ch, fg, bg)


def eye_cell(S, side, eyes, look, body):
    big = S >= 6
    sclera = EYE_W if big else body
    if eyes == "blink":
        return "─", EYE_P, body
    if eyes == "happy":
        return "^", EYE_P, body
    if eyes == "dizzy":
        return "@", EYE_P, sclera
    if eyes == "ouch":
        return (">" if side == 0 else "<"), EYE_P, body
    dx, dy = look
    if not big:  # pupils on the body itself: keep them high, or they read as feet
        ch = "▝" if dx > 0 else "▘" if dx < 0 else ("▖", "▗")[side] if dy > 0 else ("▘", "▝")[side]
    elif dx > 0:
        ch = "▝" if dy < 0 else "▗"
    elif dx < 0:
        ch = "▘" if dy < 0 else "▖"
    elif dy < 0:
        ch = ("▝", "▘")[side]
    else:
        ch = ("▗", "▖")[side]
    return ch, EYE_P, sclera


def draw_friend(L, who, X, Y, S, dw=0, dh=0, lift=0, eyes="open", look=(0, 0), alpha=1.0,
                tint=0.0):
    """One friend with its tile's top-left pixel at (X, Y). dw/dh squash or stretch the body
    (bottom-anchored), lift raises it off its shadow, alpha < 1 draws a faint ghost, tint
    flushes it red."""
    F = FRIEND[who]
    bw, bh, foot, erow, ecols = BODY[S]
    if S == 2:
        dw = dh = 0
    w, h = bw + dw, max(2, bh + dh)
    ground = Y + S - 1 - foot
    bottom = ground - lift
    top = bottom - h + 1
    left = X + (S - w) // 2
    body, lit, dark = F["body"], F["lit"], F["dark"]
    if tint:
        body, lit, dark = (mix(body, (255, 60, 60), tint), mix(lit, (255, 140, 140), tint),
                           mix(dark, (170, 20, 30), tint))
    edge_l, edge_r = mix(body, lit, .45), mix(body, dark, .45)
    if foot and alpha >= 1:
        sw = max(2, w - 2 - lift // 2)
        sl = X + (S - sw) // 2
        for i in range(sw):
            L.dark(sl + i, ground + 1, 0.55)
    corners = w >= 4 and h >= 3
    px = L.px if alpha >= 1 else (lambda x, y, col: L.blend(x, y, col, alpha))
    for j in range(h):
        y = top + j
        for i in range(w):
            if corners and (i == 0 or i == w - 1) and (j == 0 or j == h - 1):
                continue
            px(left + i, y, lit if j == 0 else dark if j == h - 1 else
               edge_l if i == 0 else edge_r if i == w - 1 else body)
    if alpha < 1:
        return
    if S >= 6:
        L.px(left + 1, top, F["spec"])
    cx = left + w // 2
    if F["feat"] == "leaf" and S >= 4:
        if S >= 6:
            L.px(cx - 1, top - 1, STEM)
            L.px(cx, top - 2, LEAF)
            L.px(cx + 1, top - 2, LEAF_LIT)
            L.px(cx, top - 1, LEAF)
        else:
            L.px(cx - 1, top - 1, LEAF)
    elif F["feat"] == "ears" and S >= 4:
        L.px(left + 1, top - 1, lit)
        L.px(left + w - 2, top - 1, lit)
        if S >= 8:
            L.px(left + 1, top - 2, lit)
            L.px(left + w - 2, top - 2, lit)
    ey = bottom - ((S - 1 - foot) - erow)
    if ey & 1:
        ey = ey - 1 if ey - 1 >= top else ey + 1
    if ey < top or ey + 1 > bottom:
        return
    for side, ex in enumerate(ecols):
        L.glyph(X + ex, ey >> 1, *eye_cell(S, side, eyes, look, body))


_coin_cache = {}


def coin_px(D, k):
    """Coin pixels at spin step k (8 = face on, 0 = edge on) as [(i, j, tone)]; tones index GOLD."""
    key = (D, k)
    if key not in _coin_cache and k / 8 < 0.4:  # edge on: a thin centred bar
        bar = range(D // 2 - 1, D // 2 + 1) if D >= 6 else (max(0, D // 2 - 1),)
        _coin_cache[key] = [(i, j, 3) for j in range(D) for i in bar]
    if key not in _coin_cache:
        kk, r, out = k / 8, D / 2, []
        for j in range(D):
            dy = (j + 0.5 - r) / r
            row = []
            for i in range(D):
                dx = (i + 0.5 - r) / r
                if (dx / kk) ** 2 + dy * dy > 1.0:
                    continue
                if dy < -0.5 or dx < -0.45 * kk:
                    tone = 1
                elif dx > 0.45 * kk or dy > 0.55:
                    tone = 2
                elif D >= 4 and k >= 5 and (dx / kk) ** 2 + dy * dy < 0.3:
                    tone = 4
                else:
                    tone = 0
                row.append((i, j, tone))
            out += row or [(D // 2 - 1, j, 3)]
        _coin_cache[key] = out
    return _coin_cache[key]


def draw_coin(L, X, Y, S, now, idx, grow=1.0, flash=0.0):
    """A spinning, bobbing coin on the tile whose top-left pixel is (X, Y)."""
    spin = abs(math.cos(now * 3.2 + idx * 0.9))
    if S == 2:
        lit, dark = (GOLD[1], GOLD[2]) if spin > .4 else (GOLD[3], GOLD[3])
        L.glyph(X, Y // 2, "▐", mix(lit, (255, 255, 255), flash))
        L.glyph(X + 1, Y // 2, "▌", mix(dark, (255, 255, 255), flash))
        return
    D = max(1, round(COIN_D[S] * grow))
    bob = 1 if math.sin(now * 3 + idx * 1.3) > 0 else 0
    x0, y0 = X + (S - D) // 2, Y + (S - D) // 2 - bob
    sw = max(1, round(COIN_D[S] * max(spin, 0.4)) - 1)
    for i in range(sw):
        L.dark(X + (S - sw) // 2 + i, Y + S - 1 - (S >= 8), 0.7)
    for i, j, tone in coin_px(D, round(spin * 8)):
        col = GOLD[tone]
        L.px(x0 + i, y0 + j, mix(col, (255, 255, 255), flash) if flash else col)


LOGO_FONT = {
    "B": ["#####.", "##..##", "##..##", "#####.", "##..##", "##..##", "#####."],
    "O": [".####.", "##..##", "##..##", "##..##", "##..##", "##..##", ".####."],
    "N": ["##..##", "###.##", "###.##", "######", "##.###", "##.###", "##..##"],
    "K": ["##..##", "##.##.", "####..", "###...", "####..", "##.##.", "##..##"],
    "Y": ["##..##", "##..##", "##..##", ".####.", "..##..", "..##..", "..##.."],
}
LOGO_STOPS = ((0.0, (255, 230, 242)), (0.2, (255, 134, 186)), (0.62, (236, 62, 140)),
              (1.0, (150, 26, 92)))
LOGO_LINE = (52, 14, 46)
_logo = {}


def logo_sprites(L):
    """"BONKYON" at pixel scale L: per letter ([(i, j, rgb, is_fill)] with the outline, and
    the drop-shadow pixels the letter itself doesn't cover)."""
    if L not in _logo:
        H, out = 7 * L, []
        for ch in "BONKYON":
            rows = LOGO_FONT[ch]
            fill = {(i, j) for j in range(H) for i in range(6 * L) if rows[j // L][i // L] == "#"}
            ring = ({(i + a, j + b) for i, j in fill for a in (-1, 0, 1) for b in (-1, 0, 1)} - fill
                    if L > 1 else set())
            px = ([(i + 1, j + 1, LOGO_LINE, False) for i, j in ring] +
                  [(i + 1, j + 1, grad(LOGO_STOPS, j / (H - 1)), True) for i, j in fill])
            own = {(i, j) for i, j, _, _ in px}
            out.append((px, sorted({(i + 1, j + 2) for i, j in own} - own)))
        _logo[L] = out
    return _logo[L]


def logo_size(L):
    return 48 * L + 2, 7 * L + 3  # pixels, including the outline and drop shadow


def draw_logo(Lyr, X, Y, L, now, shade):
    """Letters bob in a wave; a glint sweeps across every few seconds. shade holds the
    background's drop-shadow colour per pixel."""
    sweep = (now % 4.5) * 70 - 20
    for k, (letter, shadow) in enumerate(logo_sprites(L)):
        lx = X + k * 7 * L
        ly = Y + round(math.sin(now * 2.6 - k * 0.7) * (0.6 if L == 1 else 1.4))
        for i, j in shadow:
            x, y = lx + i, ly + j
            if 0 <= x < Lyr.w and 0 <= y < Lyr.hp:
                Lyr.ov[(x, y)] = shade[y][x]
        for i, j, col, fill in letter:
            if fill and abs(lx + i - X + j * 0.6 - sweep) < 2:
                col = mix(col, (255, 255, 255), 0.6)
            Lyr.px(lx + i, ly + j, col)


def pill(c, x, y, text, fg, bg):
    """Text on a rounded badge; returns the column after it."""
    c.put(x, y, "▐", bg)
    c.text(x + 1, y, text, fg, bg)
    c.put(x + 1 + len(text), y, "▌", bg)
    return x + len(text) + 2


def box(c, x, y, w, h, col):
    """A filled card with half-block rounded edges: rows y and y + h - 1 are the soft caps."""
    c.text(x, y, "▗" + "▄" * (w - 2) + "▖", col)
    for r in range(y + 1, y + h - 1):
        c.text(x, r, " " * w, None, col)
    c.text(x, y + h - 1, "▝" + "▀" * (w - 2) + "▘", col)


def segs(c, x, y, parts):
    """Draw [(text, fg)] runs left to right; returns the end column."""
    for text, fg in parts:
        c.text(x, y, text, fg)
        x += len(text)
    return x


def seg_len(parts):
    return sum(len(t) for t, _ in parts)


def rule_arrows(rule):
    mx, my = RULES[rule][0]
    return "→" if mx > 0 else "←", "↑" if my > 0 else "↓"


TITLE = [
    "  _                 _                       ",
    " | |__   ___  _ __ | | ___   _  ___  _ __   ",
    " | '_ \\ / _ \\| '_ \\| |/ / | | |/ _ \\| '_ \\  ",
    " | |_) | (_) | | | |   <| |_| | (_) | | | | ",
    " |_.__/ \\___/|_| |_|_|\\_\\\\__, |\\___/|_| |_| ",
    "                         |___/              ",
]
CONTROLS = [
    ("arrows / wasd", "move (Pop follows the level's rule)"),
    ("u", "undo last move"),
    ("r", "restart level"),
    ("n / b", "next / prev unlocked level"),
    ("p", "pause"),
    ("q", "quit"),
]
LEGEND = [("()", "coin: grab them all", 220), ("^^", "spikes", 196),
          ("%%", "cracked floor: falls away behind you", 137)]


def wrap(s, width):
    lines, cur = [], ""
    for word in s.split():
        if cur and len(cur) + 1 + len(word) > width:
            lines.append(cur)
            cur = word
        else:
            cur = f"{cur} {word}" if cur else word
    return lines + [cur]


def too_small(c):
    c.cells = [[(" ", None, BG_FLAT)] * c.w for _ in range(c.h)]
    lines = wrap("make the terminal bigger", max(1, c.w))
    y0 = max(0, (c.h - len(lines)) // 2)
    for i, line in enumerate(lines):
        c.text(max(0, (c.w - len(line)) // 2), y0 + i, line, DIM)


def main():
    parser = term.make_parser(__doc__.splitlines()[0], fps=30)
    parser.add_argument("--level", type=int, default=None, help="start at level N")
    parser.add_argument("--solve", action="store_true", help="solve every level and exit")
    parser.add_argument("--endless", action="store_true", help="endless generated levels")
    parser.add_argument("--seed", type=int, default=None, help="endless seed (default random)")
    parser.add_argument("--daily", action="store_true", help="endless with today's seed")
    parser.add_argument("--gen-check", type=int, metavar="N", help="generate depths 1..N and exit")
    parser.add_argument("--rule", choices=list(RULES), default=None,
                        help="force one movement rule in endless mode")
    parser.add_argument("--depth", type=int, default=1, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.rule and (args.level is not None or args.solve):
        parser.error("--rule only applies to endless mode; hand-made levels have their own rule")
    if args.solve:
        return run_solver()
    fixed_seed = int(time.strftime("%Y%m%d")) if args.daily else args.seed
    if args.gen_check:
        return run_gen_check(args.gen_check, 1 if fixed_seed is None else fixed_seed, args.rule)
    fps = max(1.0, args.fps)
    stars0 = [game.best(f"bonkyon_stars{i + 1}") for i in range(len(LV))]
    # bonkyon_level is never saved past the last level, so saves that finished a shorter
    # LEVELS list rely on their stars to unlock the levels appended after it.
    unlocked = min(len(LV), max(1, game.best("bonkyon_level"),
                                *(i + 2 for i, n in enumerate(stars0) if n)))
    st = {"mode": "title", "lv": min(unlocked, len(LV)) - 1, "pos": None, "moves": 0, "hist": [],
          "t0": 0, "fx": None, "paused": False, "done": False, "unlocked": unlocked, "log": [],
          "tick": 0, "stars": stars0, "end": None, "elv": None, "intro": None, "rule": None,
          "sel": None, "erule": args.rule}
    if args.level is not None:
        st["lv"] = min(len(LV), max(1, args.level)) - 1
        st["unlocked"] = max(unlocked, st["lv"] + 1)
        st["mode"] = "play"
    snd = {"pack": None, "music": False}
    # Animation state. The hooks in load/handle/won write it; only the draw code reads it,
    # so no animation ever holds up a move.
    fx = {"mv": None, "pops": [], "parts": [], "appear": {}, "crumble": [], "shake": None,
          "burst": None, "confetti": [], "rain": None}
    view = {"lv": None, "key": None, "geo": None, "title": None}
    fxr = random.Random(7)

    def anim_t(frame):
        # A key arrived somewhere in the last frame; starting the clock just before now
        # puts the first visible step of a slide on this very frame.
        return (frame - 0.6) / fps

    def anim_load():
        t, s0 = st["tick"] / fps, cur().start
        fx["mv"] = {"kind": "drop", "t": t, "a0": s0[0], "a1": s0[0], "b0": s0[1], "b1": s0[1],
                    "da": (0, 0), "db": (0, 0)}
        for key in ("pops", "parts", "crumble", "confetti"):
            fx[key] = []
        fx["appear"], fx["shake"], fx["burst"] = {}, None, None

    def anim_move(lv, old, new, k, out, frame):
        t = anim_t(frame)
        dx, dy = DIRS[k]
        m = fx["mv"] = {"kind": out or "move", "t": t, "a0": old[0], "a1": new[0], "b0": old[1],
                        "b1": new[1], "da": (dx, dy), "db": (lv.mx * dx, lv.my * dy)}
        if out == "bonk":
            f = 0.5 if new[0] == new[1] and old[0] != new[0] and old[1] != new[1] else 0.14
            m["ma"], m["mb"] = [(p0[0] + (p1[0] - p0[0]) * f, p0[1] + (p1[1] - p0[1]) * f)
                                for p0, p1 in ((old[0], new[0]), (old[1], new[1]))]
            fx["burst"] = (t + 0.06, (m["ma"][0] + m["mb"][0]) / 2, (m["ma"][1] + m["mb"][1]) / 2)
            fx["shake"] = (t + 0.06, 1.0)
        elif out == "ouch":
            fx["shake"] = (t + SLIDE, 0.6)
        for p, bit in lv.coin_bit.items():
            if old[2] & bit and not new[2] & bit:
                fx["pops"].append((p, t + SLIDE * 0.7))
        for p, bit in lv.crack_bit.items():
            if new[3] & bit and not old[3] & bit:
                fx["crumble"].append((p, t + SLIDE * 0.8))

    def anim_undo(lv, old, new, frame):
        t = anim_t(frame)
        fx["mv"] = {"kind": "undo", "t": t, "a0": old[0], "a1": new[0], "b0": old[1], "b1": new[1],
                    "da": (old[0][0] - new[0][0], old[0][1] - new[0][1]),
                    "db": (old[1][0] - new[1][0], old[1][1] - new[1][1])}
        for p, bit in lv.coin_bit.items():
            if new[2] & bit and not old[2] & bit:
                fx["appear"][p] = t

    def anim_puffs(old, frame):
        t = anim_t(frame)
        for p in old[:2]:
            for k in range(10):
                ang = k * math.pi / 5 + fxr.random() * 0.5
                sp = fxr.uniform(1.2, 2.4)
                fx["parts"].append((t, fxr.uniform(0.3, 0.5), p[0] + 0.5, p[1] + 0.6,
                                    math.cos(ang) * sp, math.sin(ang) * sp * 0.7 - 0.6, 0.0,
                                    (220, 224, 240)))

    def celebrate(frame):
        t, g = anim_t(frame), view["geo"]
        cx, cy, half = (g[1] + g[3] / 2, g[2] + g[4] / 2, g[3] / 2) if g else (40, 12, 20)
        fx["confetti"] = [(t + fxr.uniform(0, 0.3), cx + fxr.uniform(-half, half), cy,
                           fxr.uniform(-30, 30), fxr.uniform(-26, -8), fxr.choice(CONFETTI),
                           fxr.uniform(0, 6.3)) for _ in range(130)]

    def sound(key, vol=1.0):
        path = snd["pack"].path(key) if snd["pack"] else None
        audio.sfx(path or SYNTH_STANDIN[key], vol)

    def sound_poll():
        if not audio.enabled() or snd["music"]:
            return
        if snd["pack"] is None:
            snd["pack"] = audio.Pack("bonkyon", SOUND_BASE, SOUND_FILES, convert=("music",))
        pack = snd["pack"]
        if pack.path("music"):
            audio.music(pack.path("music"))
            snd["music"] = True
        elif pack.state == "failed":
            audio.music(SYNTH_STANDIN["music"])
            snd["music"] = True
        if pack.errors:
            game.toast("couldn't fetch bonkyon sounds; using stand-ins", 4)
            audio.note(f"bonkyon: couldn't download {len(pack.errors)} sound(s) from {SOUND_BASE} "
                       f"({pack.errors[0].split(': ', 1)[-1]}); used synthesized stand-ins")

    def cur():
        return st["elv"] if st["end"] else LV[st["lv"]]

    def load(i=None):
        if i is not None:
            st["lv"] = i
        st["pos"], st["moves"], st["hist"] = cur().start, 0, []
        st["mode"], st["fx"] = "play", None
        if cur().rule != st["rule"]:
            st["rule"], st["intro"] = cur().rule, st["tick"]
        if st["end"]:
            st["end"]["undos"] = 0
        anim_load()

    def start_endless(rule=None):
        st["erule"] = rule
        seed = random.randrange(1, 10 ** 6) if fixed_seed is None else fixed_seed
        st["end"] = {"seed": seed, "depth": max(1, args.depth) - 1, "lives": 3, "score": 0,
                     "undos": 0, "gain": 0, "next": None, "best": 0, "new_best": False}
        st["rule"] = None
        next_depth()

    def next_depth():
        e = st["end"]
        e["depth"] += 1
        st["elv"] = e["next"] or gen_level(e["seed"], e["depth"], st["erule"])[0]
        e["next"] = None
        load()

    def lose_life(frame, skip=False):
        e = st["end"]
        e["lives"] -= 1
        if e["lives"] > 0:
            return next_depth() if skip else load()
        st["mode"], st["t0"] = "over", frame
        st["log"].append(f"endless seed {e['seed']}: game over at depth {e['depth']}, "
                         f"score {e['score']}")
        save_endless()

    def save_endless():
        e = st["end"]
        e["new_best"] = game.record("bonkyon_endless", e["score"])
        e["best"] = game.best("bonkyon_endless")

    load(st["lv"])
    st["mode"] = "title" if args.level is None else "play"
    if args.endless or args.daily or args.seed is not None or args.depth > 1 or args.rule:
        start_endless(args.rule)

    def sel_rule():
        """The rule card highlighted on the title; by default the offered level's rule."""
        return LV[st["lv"]].rule if st["sel"] is None else list(RULES)[st["sel"]]

    def rule_target(rule):
        """Level index the title plays for a rule, or None while every level of it is locked.
        The rule of the offered level resumes at that level."""
        if LV[st["lv"]].rule == rule:
            return st["lv"]
        idxs = [i for i, l in enumerate(LV) if l.rule == rule]
        if idxs[0] < st["unlocked"]:
            return idxs[0]
        return max((i for i in idxs if i < st["unlocked"]), default=None)

    def locked_msg(rule):
        first = next(i for i, l in enumerate(LV) if l.rule == rule)
        return f"{rule} levels unlock after level {first}"

    def title_key(k):
        st["rule"] = None  # so the first level played announces its rule
        names = list(RULES)
        cur_i = names.index(sel_rule())
        if k in ("left", "right"):
            st["sel"] = (cur_i + (1 if k == "right" else -1)) % len(names)
        elif k in ("1", "2", "3", "4"):
            st["sel"] = int(k) - 1
        elif k in ("up", "down", "w", "a", "s", "d"):
            pass  # the letters arrive beside their arrow names, which already moved the selection
        elif k == "x":
            start_endless()
        elif k == "e":
            start_endless(names[cur_i])
        elif k in ("enter", "space"):
            t = rule_target(names[cur_i])
            if t is None:
                return game.toast(locked_msg(names[cur_i]), 3)
            load(t)
        else:
            load(st["lv"])
        if st["mode"] != "title":
            st["sel"] = None

    def handle(k, frame):
        lv = cur()
        if st["mode"] == "title":
            title_key(k)
        elif st["mode"] == "won":
            st["mode"] = "title"
        elif st["mode"] == "over":
            if frame - st["t0"] > fps * 0.5:
                st["end"] = None
                st["mode"] = "title"
        elif st["mode"] == "clear":
            if frame - st["t0"] > fps * 0.4:
                advance()
        elif st["mode"] != "play":
            return
        elif k == "p":
            st["paused"] = not st["paused"]
        elif st["paused"]:
            return
        elif k in DIRS:
            nst, out = lv.move(st["pos"], k)
            if nst == st["pos"]:
                anim_move(lv, nst, nst, k, None, frame)  # both bump a wall
                return
            got_coin = nst[2] != st["pos"][2]
            anim_move(lv, st["pos"], nst, k, out, frame)
            st["hist"].append((st["pos"], st["moves"]))
            st["pos"], st["moves"] = nst, st["moves"] + 1
            if out in ("bonk", "ouch"):
                st["mode"], st["fx"], st["t0"] = "bonk", out, frame
                sound("gameover")
            elif out == "clear":
                won(frame)
                audio.sfx("clear")
            elif got_coin:
                sound("beeps")
            else:
                sound("button", 0.4)
        elif k == "u" and st["hist"]:
            old = st["pos"]
            st["pos"], st["moves"] = st["hist"].pop()
            anim_undo(lv, old, st["pos"], frame)
            sound("undo")
            if st["end"]:
                st["end"]["undos"] += 1
        elif k == "r":
            old = st["pos"]
            load()
            anim_puffs(old, frame)
            sound("restart")
        elif st["end"]:
            if k == "n":
                lose_life(frame, skip=True)
                sound("restart")
        elif k == "n" and st["lv"] + 1 < st["unlocked"]:
            load(st["lv"] + 1)
            sound("restart")
        elif k == "b" and st["lv"] > 0:
            load(st["lv"] - 1)
            sound("restart")

    def won(frame):
        lv = cur()
        n = stars(st["moves"], lv.par)
        st["mode"], st["t0"], st["fx"] = "clear", frame, n
        celebrate(frame)
        if st["end"]:
            e = st["end"]
            e["gain"] = max(0, 10 * e["depth"] * n - UNDO_COST * e["undos"])
            e["score"] += e["gain"]
            st["log"].append(f"endless depth {e['depth']} cleared in {st['moves']} moves, "
                             f"par {lv.par}, stars {n}/3, +{e['gain']}")
            return
        st["log"].append(f"level {lv.idx + 1} ({lv.name}) cleared in {st['moves']} moves, "
                         f"par {lv.par}, stars {n}/3")
        game.record(f"bonkyon_stars{lv.idx + 1}", n)
        st["stars"][lv.idx] = max(st["stars"][lv.idx], n)
        if lv.idx + 2 <= len(LV):
            st["unlocked"] = max(st["unlocked"], lv.idx + 2)
            game.record("bonkyon_level", lv.idx + 2)

    def advance():
        sound("jump")
        if st["end"]:
            next_depth()
        elif st["lv"] + 1 < len(LV):
            load(st["lv"] + 1)
        else:
            st["mode"] = "won"

    def layout(c, lv):
        """(th, ox, oy, board cols, board rows): the biggest tiles that leave room for the
        HUD and banner, or None when even 2x1 tiles don't fit."""
        for th in (4, 3, 2):
            if lv.w * 2 * th + 4 <= c.w and lv.h * th + 6 <= c.h:
                break
        else:
            th = 1
            if c.w < max(lv.w * 2 + 2, 24) or c.h < lv.h + 4:
                return None
        gw, gh = lv.w * 2 * th, lv.h * th
        return th, (c.w - gw) // 2, 2 + max(0, (c.h - 4 - gh) // 2), gw, gh

    def board_layer(c, lv, fallen, g):
        key = (c.w, c.h, g, fallen, term.TRUECOLOR)
        if view["lv"] is not lv or view["key"] != key:
            view["lv"], view["key"] = lv, key
            view["base"], view["cells"] = build_board(c.w, c.h, lv, fallen, *g[:3])
        L = Layer(view["base"], [r[:] for r in view["cells"]])
        c.cells = L.cells
        return L

    def bg_layer(c):
        key = (c.w, c.h, term.TRUECOLOR)
        if view["title"] is None or view["title"][0] != key:
            base = bg_px(c.w, 2 * c.h)
            view["title"] = (key, base, [px_cells(base[2 * r], base[2 * r + 1]) for r in range(c.h)],
                             [[mul(p, 0.45) for p in row] for row in base])
        _, base, cells, view["shade"] = view["title"]
        L = Layer(base, [r[:] for r in cells])
        c.cells = L.cells
        return L

    def fade_text(c, x, y, s, col, u):
        """Text whose colour fades into the cell behind it as u goes 0 -> 1."""
        if 0 <= y < c.h:
            for i, ch in enumerate(s):
                if 0 <= x + i < c.w:
                    c.put(x + i, y, ch, mix(col, c.cells[y][x + i][2] or BG_FLAT, clamp01(u)))

    def pose(i, now, S, lv):
        """Where friend i is drawn this frame: (x, y in tiles, lift px, dw, dh, eyes, look,
        tint, ghost trail)."""
        m = fx["mv"]
        p0, p1, d = (m["a0"], m["a1"], m["da"]) if i == 0 else (m["b0"], m["b1"], m["db"])
        kind, tau = m["kind"], now - m["t"]
        x, y = float(p1[0]), float(p1[1])
        lift = dw = dh = 0
        eyes, tint, trail = "open", 0.0, None
        look = d if tau < 1.8 else (0, 0)
        along = (2, -1) if d[0] else (-2, 1)  # stretched along the motion
        across = (-along[0], -along[1])  # squashed against it

        def at(e):
            return p0[0] + (p1[0] - p0[0]) * e, p0[1] + (p1[1] - p0[1]) * e

        if kind == "drop":
            u = (tau - 0.08 * i) / DROP_T
            lift = int((1 - bounce_out(u)) * S * 1.8)
            if 0.36 < u < 0.5:
                dw, dh = 2, -1
            look = (0, 0)
        elif kind == "bonk":
            meet = m["ma"] if i == 0 else m["mb"]
            if tau < 0.06:
                e = clamp01(tau / 0.06) ** 2
                x, y = p0[0] + (meet[0] - p0[0]) * e, p0[1] + (meet[1] - p0[1]) * e
            else:
                e = back_out((tau - 0.06) / 0.3)
                x, y = meet[0] + (p0[0] - meet[0]) * e, meet[1] + (p0[1] - meet[1]) * e
                if tau < 0.16:
                    dw, dh = across
                eyes = "dizzy"
        elif kind == "undo":
            e = ease_out(tau / UNDO_T)
            x, y = at(e)
            if tau < UNDO_T * 1.5 and p0 != p1:
                trail = [(*at(max(0.0, e - 0.3 * k)), a) for k, a in ((2, 0.18), (1, 0.38))]
        else:
            if p0 != p1:
                u = tau / SLIDE
                if u < 1:
                    e = ease_out(u)
                    x, y = at(e)
                    if math.sin(math.pi * u) > 0.35:
                        dw, dh = along
                    trail = [(*at(max(0.0, e - 0.4)), 0.25)]
                elif tau - SLIDE < 0.09:
                    dw, dh = across
            elif d != (0, 0):
                u = tau / BUMP
                if u < 1:
                    off = math.sin(math.pi * u) * 0.22
                    x, y = x + d[0] * off, y + d[1] * off
                    if 0.3 < u < 0.75:
                        dw, dh = across
            if kind == "ouch" and lv.tiles.get(p1) == SPIKE and tau >= SLIDE:
                v = tau - SLIDE
                eyes, tint = "ouch", 0.35 + 0.3 * math.cos(v * 24)
                if v < 0.32:
                    lift = int(math.sin(math.pi * v / 0.32) * S * 0.7)
        if st["mode"] == "clear" and tau > SLIDE + 0.12:
            eyes = "happy"
            lift = int(abs(math.sin((now - st["t0"] / fps) * 6.5 + i * 1.3)) * S * 0.5)
        if eyes == "open":
            if (now + i * 1.7) % (3.6 + 0.8 * i) < 0.13:
                eyes = "blink"
            if not (dw or dh or lift) and kind != "drop":
                b = math.sin(now * 2.3 + i * 2.1)  # idle bob
                if S >= 6 and b > 0.35:
                    lift = 1
                elif S == 4 and b > 0.5:
                    dh = -1
        return x, y, lift, dw, dh, eyes, look, tint, trail

    def draw_friends(L, lv, now, S, X0, Y0):
        poses = [pose(i, now, S, lv) for i in (0, 1)]
        heads = []
        for i in sorted((0, 1), key=lambda i: poses[i][1]):
            x, y, lift, dw, dh, eyes, look, tint, trail = poses[i]
            for tx, ty, a in trail or ():
                draw_friend(L, i, X0 + round(tx * S), Y0 + round(ty * S), S, alpha=a)
            X, Y = X0 + round(x * S), Y0 + round(y * S)
            draw_friend(L, i, X, Y, S, dw, dh, lift, eyes, look, tint=tint)
            heads.append((X, Y - lift, eyes))
        return heads

    def draw_coins(L, lv, coins, now, S, X0, Y0):
        pending = dict(fx["pops"])
        for idx, (p, bit) in enumerate(lv.coin_bit.items()):
            X, Y = X0 + p[0] * S, Y0 + p[1] * S
            if coins & bit:
                t_ap = fx["appear"].get(p)
                grow = back_out((now - t_ap) / 0.25) if t_ap is not None and now - t_ap < 0.25 else 1.0
                draw_coin(L, X, Y, S, now, idx, grow)
            elif p in pending:
                tau = now - pending[p]
                if tau < 0:
                    draw_coin(L, X, Y, S, now, idx)
                elif tau < 0.09:
                    draw_coin(L, X, Y, S, now, idx, 1.4, 0.75)

    def draw_pops(L, lv, coins, now, S, X0, Y0, texts):
        keep = []
        for p, t0 in fx["pops"]:
            tau = now - t0
            if tau > 1.0 or coins & lv.coin_bit[p]:
                continue
            keep.append((p, t0))
            if tau < 0:
                continue
            cx, cy = X0 + p[0] * S + S / 2, Y0 + p[1] * S + S / 2
            if tau < 0.4:
                u = tau / 0.4
                r = S * 0.3 + ease_out(u) * S * 0.8 + 1
                col = mix((255, 250, 200), GOLD[0], u)
                for k in range(8):
                    ca, sa = math.cos(k * math.pi / 4 + 0.39), math.sin(k * math.pi / 4 + 0.39)
                    L.blend(int(cx + ca * r), int(cy + sa * r), col, 1 - u * u)
                    if S >= 6:
                        L.blend(int(cx + ca * (r - 1.5)), int(cy + sa * (r - 1.5)), col, 0.6 * (1 - u))
            if tau < 0.9:
                texts.append((int(cx) - 1, (Y0 + p[1] * S) // 2 - 1 - int(tau * 3.5), "+1",
                              (255, 236, 120), tau / 0.9))
        fx["pops"] = keep

    def draw_crumble(L, lv, fallen, now, S, X0, Y0):
        keep = []
        for p, t0 in fx["crumble"]:
            tau = now - t0
            if tau > 0.6 or not fallen & lv.crack_bit[p]:
                continue
            keep.append((p, t0))
            u = clamp01(tau / 0.5)
            X, Y = X0 + p[0] * S, Y0 + p[1] * S
            sand = SAND[(p[0] + p[1]) & 1]
            bs = max(1, S // 4)  # debris chunks sink, shrink toward the middle and darken
            for cj in range(0, S, bs):
                for ci in range(0, S, bs):
                    h = ((ci * 7 + cj * 13 + p[0] * 5 + p[1] * 3) % 17) / 17
                    v = clamp01(u * 1.6 - h * 0.6)
                    if v >= 1:
                        continue
                    ox_ = int((S / 2 - ci - bs / 2) * v * 0.5)
                    oy_ = int(v * v * S * 0.5)
                    col = mix(mul(sand, 1.05 - 0.1 * ((ci + cj) // bs & 1)), PIT, v * 0.9)
                    n = bs if v < 0.5 else max(1, bs - 1)
                    for dj in range(n):
                        for di in range(n):
                            yy = cj + dj + oy_
                            if yy < S:
                                L.px(X + ci + di + ox_, Y + yy, col)
            if 0 < u < 1:
                for k in range(6):
                    a = k * 1.1 + p[0]
                    L.blend(int(X + S / 2 + math.cos(a) * (S / 2 + u * S * 0.6)),
                            int(Y + S / 2 + math.sin(a) * S * 0.3 - u * S * 0.6), (200, 180, 150), 0.6 * (1 - u))
        fx["crumble"] = keep

    def draw_parts(L, now, S, X0, Y0):
        keep = []
        for prt in fx["parts"]:
            t0, life, x, y, vx, vy, g, col = prt
            tau = now - t0
            if tau > life:
                continue
            keep.append(prt)
            if tau >= 0:
                L.blend(int(X0 + (x + vx * tau) * S), int(Y0 + (y + vy * tau + 0.5 * g * tau * tau) * S),
                        col, 0.85 * (1 - tau / life))
        fx["parts"] = keep

    def draw_confetti(c, now):
        keep = []
        for prt in fx["confetti"]:
            t0, x0, y0, vx, vy, col, ph = prt
            tau = now - t0
            if tau < 0:
                keep.append(prt)
                continue
            drag = (1 - math.exp(-tau * 2.5)) / 2.5  # air drag, falling to 6 rows/s
            x = x0 + vx * drag + math.sin(tau * 5 + ph) * 0.8
            y = y0 + 6 * tau + (vy - 6) * drag
            if y < c.h + 1 and tau < 4:
                keep.append(prt)
                c.put(x, y, "▀▐▄▌"[int(tau * 12 + ph) % 4], col)
        fx["confetti"] = keep

    def draw_burst(c, now, S, X0, Y0):
        t0, bx, by = fx["burst"]
        tau = now - t0
        if not 0 <= tau < 0.9:
            return
        cx, cy = X0 + (bx + 0.5) * S, (Y0 + (by + 0.5) * S) / 2
        if tau < 0.4:
            u = tau / 0.4
            r = 1.5 + ease_out(u) * (S + 3)
            for k in range(8):
                a = k * math.pi / 4 + 0.39
                c.put(cx + math.cos(a) * r, cy + math.sin(a) * r * 0.5, "✦" if k % 2 else "*",
                      mix((255, 244, 140), (255, 110, 60), u))
            if tau < 0.12:
                c.put(cx, cy, "✦", (255, 255, 255), (255, 214, 90))
        if tau > 0.02:
            jig = (1 if int(tau * 30) % 2 else -1) if tau < 0.2 else 0
            word = "BONK!"
            pill(c, int(cx) - len(word) // 2 - 1 + jig, int(cy) - max(2, S // 2 + 1), word,
                 (186, 22, 44), (255, 226, 80))

    def draw_stars_orbit(c, heads, now, S):
        for X, Y, eyes in heads:
            if eyes not in ("dizzy", "ouch"):
                continue
            row, mid = Y // 2 - 1, X + S / 2 - 0.5
            for k in range(2):
                a = now * 8 + k * math.pi
                front = math.sin(a) > 0
                c.put(mid + math.cos(a) * (S * 0.45 + 1), row,
                      "✦" if front else "·", (255, 232, 96) if front else (190, 170, 90))

    def draw_level(c, frame, now):
        lv = cur()
        a, b, coins, fallen = st["pos"]
        g = layout(c, lv)
        view["geo"] = g
        if g is None:
            return too_small(c)
        th, ox, oy, gw, gh = g
        S, X0, Y0 = 2 * th, ox, 2 * oy
        L = board_layer(c, lv, fallen, g)
        texts = []
        draw_crumble(L, lv, fallen, now, S, X0, Y0)
        draw_coins(L, lv, coins, now, S, X0, Y0)
        heads = draw_friends(L, lv, now, S, X0, Y0)
        draw_pops(L, lv, coins, now, S, X0, Y0, texts)
        draw_parts(L, now, S, X0, Y0)
        L.compose(c)
        for idx, (p, bit) in enumerate(lv.coin_bit.items()):
            ph = (now * 0.45 + idx * 0.31) % 1  # each coin glints now and then
            if coins & bit and ph < 0.12 and S >= 4:
                D = COIN_D[S]
                c.put(X0 + p[0] * S + (S + D) // 2, oy + p[1] * th + (S - D) // 4 - 1 + (S >= 6),
                      "·+✦+·"[int(ph / 0.12 * 5)], (255, 250, 214))
        for x, y, s, col, u in texts:
            fade_text(c, x, y, s, col, u)
        draw_stars_orbit(c, heads, now, S)
        bonking = st["mode"] == "bonk"
        if bonking and st["fx"] == "bonk" and fx["burst"]:
            draw_burst(c, now, S, X0, Y0)
        elif bonking:
            p = a if lv.tiles[a] == SPIKE else b
            tau = (frame - st["t0"]) / fps
            if tau > SLIDE:
                pill(c, ox + p[0] * S + S // 2 - 4, oy + p[1] * th - 1 - (th > 1), "OUCH!",
                     (255, 255, 255), (220, 40, 64))
        if st["mode"] == "clear":
            draw_confetti(c, now)
            draw_clear_panel(c, g)
        if (st["mode"] == "play" and st["intro"] is not None and not st["moves"]
                and frame - st["intro"] < fps * 3):
            tau = (frame - st["intro"]) / fps
            al = clamp01(min(tau / 0.25, (3 - tau) / 0.4))
            badge, desc = f"{RULES[lv.rule][1]} {lv.rule}", f" {RULES[lv.rule][2]}"
            if c.w < len(badge) + len(desc) + 4:
                desc = ""
            y = oy + gh + (1 if th > 1 and oy + gh + 1 < c.h - 1 else 0)
            x = (c.w - len(badge) - len(desc) - 3) // 2
            back = c.cells[min(y, c.h - 1)][c.w // 2][2] or BG_FLAT
            rc, pc = mix(back, RULE_COL[lv.rule], al), mix(back, PANEL, al)
            c.put(x, y, "▐", rc)
            c.text(x + 1, y, f"{badge} ", mix(back, INK, al), rc)
            c.text(x + 2 + len(badge), y, desc, mix(back, TEXT, al), pc)
            c.put(x + 2 + len(badge) + len(desc), y, "▌", pc if desc else rc)
        if st["paused"] and st["mode"] == "play":
            msg = "paused: p to resume"
            pill(c, (c.w - len(msg) - 2) // 2, oy + gh // 2, msg, TEXT, PANEL)

    def draw_clear_panel(c, g):
        lv, e, n = cur(), st["end"], st["fx"]
        tau = (st["tick"] - st["t0"]) / fps
        title = f"depth {e['depth']} clear!" if e else "level clear!"
        info = f"moves {st['moves']}  par {lv.par}" + (f"   +{e['gain']}" if e else "")
        bw = max(len(title), len(info), 15) + 10
        cy, x0 = g[2] + g[4] // 2, (c.w - bw) // 2
        if tau < 0.1:  # the panel pops open
            box(c, x0 + 4, cy - 1, bw - 8, 3, PANEL)
            return
        box(c, x0, cy - 3, bw, 7, PANEL)
        shine = int(tau * 18) % (len(title) + 8) - 4  # a highlight runs along the title
        for i, ch in enumerate(title):
            c.put((c.w - len(title)) // 2 + i, cy - 2, ch,
                  (255, 255, 255) if abs(i - shine) < 2 else (255, 226, 110))
        sx = c.w // 2 - 5
        for i in range(3):
            ti, x = tau - (0.2 + 0.18 * i), sx + 5 * i
            if ti < 0:
                c.put(x, cy, "·", FAINT)
                continue
            on = i < n
            c.put(x, cy, "★", (255, 255, 255) if on and ti < 0.08 else STAR_ON if on else STAR_OFF)
            if on and ti < 0.3:
                spark = "✦" if ti < 0.15 else "·"
                for dx, dy in ((-2, 0), (2, 0), (0, -1), (0, 1)):
                    c.put(x + dx, cy + dy, spark, (255, 244, 170))
        c.text((c.w - len(info)) // 2, cy + 2, info, DIM)

    def draw_hud(c):
        lv, e = cur(), st["end"]
        badge = f"{RULES[lv.rule][1]} {lv.rule}"
        lab = FAINT
        if e:
            mids = [f"depth {e['depth']}  seed {e['seed']}", f"depth {e['depth']}", ""]
            right = [("moves ", lab), (str(st["moves"]), TEXT), ("  par ", lab), (str(lv.par), TEXT),
                     ("  lives ", lab), ("♥" * e["lives"], (255, 96, 120)), ("  score ", lab),
                     (str(e["score"]), (255, 226, 110))]
            short = [(f"{st['moves']}/{lv.par} ", TEXT), ("♥" * e["lives"], (255, 96, 120))]
            keys = f"arrows/wasd move  u undo (-{UNDO_COST})  r restart  n skip (-1 life)  q quit"
            skeys = "u undo n skip q quit"
        else:
            n = st["stars"][lv.idx]
            mids = [f"{lv.idx + 1}/{len(LV)}  {lv.name}", f"{lv.idx + 1}/{len(LV)}", ""]
            right = [("moves ", lab), (str(st["moves"]), TEXT), ("  par ", lab), (str(lv.par), TEXT),
                     ("  best ", lab), ("★" * n, STAR_ON), ("★" * (3 - n), STAR_OFF)]
            short = [(f"{st['moves']}/{lv.par} ", TEXT), ("★" * n, STAR_ON), ("★" * (3 - n), STAR_OFF)]
            keys = "arrows/wasd move  u undo  r restart  n/b level  p pause  q quit"
            skeys = "u undo r reset q quit"
        tries = [(True, mids[0], right), (False, mids[0], right), (False, mids[1], right),
                 (False, mids[2], right), (False, mids[1], short), (False, "", short)]
        for logo, mid, rt in tries:
            width = 1 + 10 * logo + (len(mid) + 1 if mid else 0) + len(badge) + 2
            if width + seg_len(rt) + 2 <= c.w:
                break
        x = 1
        if logo:
            x = pill(c, x, 0, "bonkyon", INK, PINK) + 1
        if mid:
            c.text(x, 0, mid, TEXT)
            x += len(mid) + 1
        x = pill(c, x, 0, badge, INK, RULE_COL[lv.rule])
        segs(c, max(x + 1, c.w - seg_len(rt) - 1), 0, rt)
        hint = lv.hint if c.w > len(lv.hint) + 2 else ""
        c.text((c.w - len(hint)) // 2, 1, hint, DIM)
        if c.w < len(keys):
            keys = skeys
            items = [" ".join(p) for p in zip(*[iter(keys.split())] * 2)]
            gap = 1
        else:
            items, gap = keys.split("  "), 2
        x = max(0, (c.w - len(keys)) // 2)
        for item in items:
            k, _, rest = item.partition(" ")
            x = segs(c, x, c.h - 1, [(k, (206, 212, 246)), (" " + rest, FAINT)]) + gap

    def hop(now, i, S, period=1.25):
        """Title/won-screen hopping: (lift px, dw, dh)."""
        ph = (now / period + i * 0.5) % 1
        if ph < 0.42:
            return int(math.sin(math.pi * ph / 0.42) * S * 0.9), *((-2, 1) if 0.1 < ph < 0.32 else (0, 0))
        if ph < 0.52 or ph > 0.92:
            return 0, 2, -1
        return 0, 0, 0

    def title_friends(L, now, S, xl, xr, yg, mood="open"):
        """Pip at column xl and Pop at xr, both standing on pixel row yg."""
        for i, X in ((0, xl), (1, xr)):
            if mood == "dizzy":
                lift, dw, dh = 0, 0, 0
            else:
                lift, dw, dh = hop(now, i, S)
            eyes = mood
            if mood == "open" and (now + i * 1.7) % (3.6 + 0.8 * i) < 0.13:
                eyes = "blink"
            draw_friend(L, i, X, yg - S + 1 + BODY[S][2], S, dw, dh, lift, eyes,
                        (1, -1 if lift > S // 3 else 0) if i == 0 else (-1, -1 if lift > S // 3 else 0))
        return [(xl, yg - S + 1, mood), (xr, yg - S + 1, mood)]

    def legend_icon(c, x, y, k):
        if k == 0:
            c.put(x, y, "▐", GOLD[1])
            c.put(x + 1, y, "▌", GOLD[2])
        elif k == 1:
            c.put(x, y, "▟", STEEL_LIT, PLATE)
            c.put(x + 1, y, "▙", STEEL_DARK, PLATE)
        else:
            c.put(x, y, "╲", CRACK_INK, SAND[0])
            c.put(x + 1, y, "╱", CRACK_INK, SAND[1])

    def title_actions():
        """(enter label, endless label) for the selected rule."""
        rule = sel_rule()
        t = rule_target(rule)
        play = f"enter: play level {t + 1}" if t is not None else "enter: locked"
        return play, f"e: endless ({rule})"

    def nav_line(c, y, col):
        """Selection help, in the longest wording that fits the width."""
        for nav in (f"←/→ or 1-4: choose a rule · x: mixed endless · other key: play level {st['lv'] + 1}",
                    "←/→ or 1-4: choose a rule · x: mixed endless", "←/→ choose rule · x: mixed"):
            if len(nav) <= c.w:
                break
        c.text((c.w - len(nav)) // 2, y, nav, col)

    def draw_title(c, now):
        big = c.w >= 112 and c.h >= 34
        if not big and not (c.w >= 64 and c.h >= 30):
            return draw_title_compact(c, now)
        Lg = 2 if big else 1
        lw, lhp = logo_size(Lg)
        lrows = (lhp + 2) // 2
        cw, ch, gap = (26, 6, 2) if big else (15, 4, 1)
        info_h = max(len(CONTROLS), len(LEGEND)) if big else len(CONTROLS) + 1 + len(LEGEND)
        total = lrows + 1 + 1 + 1 + ch + 1 + info_h + 1 + 2
        y = max(0, (c.h - total) // 2)
        L = bg_layer(c)
        lx = (c.w - lw) // 2
        draw_logo(L, lx, 2 * y + 1, Lg, now, view["shade"])
        S = 6 if big else 4
        if (c.w - lw) // 2 >= S + 5:
            title_friends(L, now, S, lx - S - 3, lx + lw + 2, 2 * y + lhp - 1)
        L.compose(c)
        y += lrows + 1
        tag = [("Pip", FRIEND[0]["ink"]), (" and ", DIM), ("Pop", FRIEND[1]["ink"]),
               (" move together, by the level's rule:", DIM)]
        segs(c, (c.w - seg_len(tag)) // 2, y, tag)
        y += 2
        x0 = (c.w - (4 * cw + 3 * gap)) // 2
        for i, (name, (_, glyph, desc)) in enumerate(RULES.items()):
            x = x0 + i * (cw + gap)
            on = name == sel_rule()
            col = RULE_COL[name]
            box(c, x, y, cw, ch, mix(CARD, col, 0.3) if on else CARD)
            if on:
                c.text(x, y, "▗" + "▄" * (cw - 2) + "▖", col)
                c.text(x, y + ch - 1, "▝" + "▀" * (cw - 2) + "▘", col)
                for r in range(y + 1, y + ch - 1):
                    c.put(x, r, "▎", col, mix(CARD, col, 0.3))
                    c.put(x + cw - 1, r, "▕", col, mix(CARD, col, 0.3))
                c.put(x + 1, y + 1, "▶", col, mix(CARD, col, 0.3))
            segs(c, x + 2, y + 1, [(glyph, RULE_COL[name]), (" " + name, TEXT)])
            ax, ay = rule_arrows(name)
            segs(c, x + 2, y + 2, [("Pip ", FRIEND[0]["ink"]), ("→↑", TEXT), (" Pop ", FRIEND[1]["ink"]),
                                   (ax + ay, RULE_COL[name])])
            if big:
                for j, line in enumerate(wrap(desc, cw - 3)[:2]):
                    c.text(x + 2, y + 3 + j, line, FAINT)
        y += ch + 1
        if big:
            cx, lx2 = (c.w - 100) // 2, (c.w - 100) // 2 + 58
            ly = y
        else:
            cx = lx2 = (c.w - 52) // 2
            ly = y + len(CONTROLS) + 1
        for i, (key, what) in enumerate(CONTROLS):
            pill(c, cx + 14 - len(key), y + i, key, TEXT, KEYCAP)
            c.text(cx + 18, y + i, what, DIM)
        for i, (_, what, _) in enumerate(LEGEND):
            legend_icon(c, lx2 + 1, ly + i, i)
            c.text(lx2 + 5, ly + i, what, DIM)
        y += info_h + 1
        play, endless = title_actions()
        x = (c.w - len(play) - len(endless) - 7) // 2
        pulse = 0.5 + 0.5 * math.sin(now * 4)
        x = pill(c, x, y, play, INK, mix(PINK, (255, 176, 212), pulse)) + 3
        pill(c, x, y, endless, INK, (110, 160, 250))
        nav_line(c, y + 1, DIM)

    def draw_title_compact(c, now):
        h = len(TITLE) + len(CONTROLS) + len(LEGEND) + 9
        if c.w < len(TITLE[0]) + 2 or c.h < h:
            return too_small(c)
        bg_layer(c)
        y = (c.h - h) // 2
        x = (c.w - len(TITLE[0])) // 2
        for i, line in enumerate(TITLE):
            c.text(x, y + i, line, PINK if i < 3 else FRIEND[1]["body"])
        y += len(TITLE) + 1
        segs(c, x + 2, y, [("(: Pip", FRIEND[0]["ink"]), ("  ", DIM), (":) Pop", FRIEND[1]["ink"]),
                           ("  move together, by the level's rule:", DIM)])
        y += 1
        for i, (name, (_, glyph, _)) in enumerate(RULES.items()):
            if name == sel_rule():
                c.put(x + 2 + 11 * i, y, "▶", RULE_COL[name])
                c.text(x + 3 + 11 * i, y, f"{glyph} {name}", INK, RULE_COL[name])
            else:
                segs(c, x + 4 + 11 * i, y, [(glyph, RULE_COL[name]), (" " + name, TEXT)])
        y += 2
        for i, (key, what) in enumerate(CONTROLS):
            c.text(x + 2, y + i, f"{key:>14}", (206, 212, 246))
            c.text(x + 18, y + i, what, DIM)
        y += len(CONTROLS) + 1
        for i, (_, what, _) in enumerate(LEGEND):
            legend_icon(c, x + 14, y + i, i)
            c.text(x + 18, y + i, what, FAINT)
        play, endless = title_actions()
        msg = f"{play}   {endless}"
        yy = y + len(LEGEND) + 1
        c.text((c.w - len(msg)) // 2, yy, msg, mix(FAINT, TEXT, 0.5 + 0.5 * math.sin(now * 4)))
        nav_line(c, yy + 1, FAINT)

    def draw_end(c, now, lines, y0, won):
        L = bg_layer(c)
        bw = max(len(s) for s in lines) + 8
        S = 6 if c.h >= 22 else 4 if c.h >= 12 else 0
        mood = "happy" if won else "dizzy"
        if won and c.w >= logo_size(1)[0] + 2 and y0 - 8 >= 0:
            draw_logo(L, (c.w - logo_size(1)[0]) // 2, 2 * (y0 - 8), 1, now, view["shade"])
        heads = []
        if S and c.w >= bw + 2 * (S + 5):
            heads = title_friends(L, now, S, (c.w - bw) // 2 - S - 3, (c.w + bw) // 2 + 3,
                                  2 * (y0 + len(lines) // 2) + 2, mood)
        L.compose(c)
        if won:
            if fx["rain"] is None:
                fx["rain"] = [(fxr.random(), fxr.uniform(3, 7), fxr.uniform(0, 40), fxr.choice(CONFETTI))
                              for _ in range(70)]
            for xf, sp, ph, col in fx["rain"]:
                c.put(xf * c.w + math.sin(now * 2 + ph) * 1.5, (now * sp + ph) % (c.h + 2) - 1,
                      "▀▐▄▌"[int(now * 10 + ph) % 4], col)
        draw_stars_orbit(c, heads, now, S or 2)
        box(c, (c.w - bw) // 2, y0 - 1, bw, len(lines) + 2, PANEL)
        for i, line in enumerate(lines):
            c.text((c.w - len(line)) // 2, y0 + i, line,
                   ((255, 226, 110) if won else (255, 116, 146)) if i == 0 else DIM)

    def step(c, frame, keys):
        st["tick"] = frame
        sound_poll()
        if frame % 20 == 0 and not st["done"]:
            st["done"] = game.claude_done()
        for k in keys:
            if k == "q":
                return True
            handle(k, frame)
        if st["mode"] == "bonk" and frame - st["t0"] > fps * 0.9:
            if st["end"]:
                lose_life(frame)
            else:
                load()
        elif st["mode"] == "clear" and frame - st["t0"] > fps * 1.8:
            advance()
        elif st["mode"] == "clear" and st["end"] and st["end"]["next"] is None and frame > st["t0"]:
            # Build the next depth while the sparkle plays, after its first frame is on screen.
            e = st["end"]
            e["next"] = gen_level(e["seed"], e["depth"] + 1, st["erule"])[0]
        now = frame / fps
        if st["mode"] == "title":
            draw_title(c, now)
        elif st["mode"] == "over":
            e = st["end"]
            lines = ["game over", f"reached depth {e['depth']}   score {e['score']}",
                     "new best!" if e["new_best"] else f"best {e['best']}",
                     f"seed {e['seed']}", "any key: title   q: quit"]
            draw_end(c, now, lines, c.h // 2 - 2, False)
        elif st["mode"] == "won":
            total = sum(st["stars"])
            lines = ["all levels cleared!", f"stars {total}/{len(LV) * 3}", "any key: title   q: quit"]
            draw_end(c, now, lines, c.h // 2 - 1, True)
        else:
            draw_level(c, frame, now)
            if c.w >= 24 and c.h >= 6:
                draw_hud(c)
            g = view["geo"]
            if fx["shake"] and g:
                tau = now - fx["shake"][0]
                if 0 <= tau < 0.3:
                    # Only the board's box shakes, so the HUD and background need no repaint.
                    k = (1 - tau / 0.3) * fx["shake"][1]
                    sx, sy = round(math.sin(tau * 90) * 2 * k), round(math.sin(tau * 60 + 1) * k)
                    x0, x1 = max(0, g[1] - 3), min(c.w, g[1] + g[3] + 3)
                    y0, y1 = max(2, g[2] - 2), min(c.h - 1, g[2] + g[4] + 2)
                    old = [r[x0:x1] for r in c.cells[y0:y1]]
                    for j, seg in enumerate(old):
                        src = old[min(len(old) - 1, max(0, j - sy))]
                        c.cells[y0 + j][x0:x1] = src[-sx:] + src[:-sx] if sx else src
        if st["done"] and c.w >= 18:
            msg = "Claude's done!"
            pill(c, c.w - len(msg) - 3, 1 if st["mode"] != "title" else 0, msg, INK, (120, 222, 140))

    game.play(args, step)
    e = st["end"]
    if e and st["mode"] != "over":
        save_endless()
        st["log"].append(f"endless seed {e['seed']}: quit at depth {e['depth']}, score {e['score']}")
    for line in st["log"]:
        print(f"bonkyon: {line}")
    print(f"bonkyon: furthest level unlocked {st['unlocked']}/{len(LV)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
