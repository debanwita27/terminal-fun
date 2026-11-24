#!/usr/bin/env python3
"""Mushroom Forage: clear the leaf litter without biting a poisonous mushroom.

Usage: python3 forage.py [--fps 20] [--frames N] [--size small|medium|large]
                         [--density D] [--seed N | --daily] [--hex] [--check N]
Arrows/WASD move, space/enter forages (or chords a satisfied number), f flags,
t sends the truffle pig to sniff the 3x3 under the cursor, p pauses, r new board, q quits.
Every board is checked by a logic solver so it can be cleared without guessing.
--check N generates N boards and prints the no-guess rate and timing.
"""

META = {'name': 'forage',
 'kind': 'play',
 'blurb': 'Minesweeper with mushrooms and a truffle pig; every board is solver-checked',
 'credit': [{'type': 'inspired by',
             'who': 'Minesweeper by Robert Donner & Curt Johnson',
             'url': 'https://en.wikipedia.org/wiki/Minesweeper_(video_game)'},
            {'type': 'inspired by',
             'who': "Simon Tatham's Mines (no-guess board generation)",
             'url': 'https://www.chiark.greenend.org.uk/~sgtatham/puzzles/'}]}

import datetime
import random
import textwrap
import time

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

from fun import audio, game, term

SIZES = {"small": (9, 9), "medium": (16, 14), "large": (30, 16)}
DENSITY = 0.15
HEARTS = 3
PIG_EVERY = 50          # tiles cleared per truffle-pig charge
TRUFFLE_EVERY = 45      # safe tiles per hidden truffle
TRUFFLE_BONUS = 50
HEART_COST = 150
GEN_BUDGET = 0.8        # seconds of no-guess retries before falling back
GEN_TRIES = 2000
MIN_W, MIN_H = 30, 10

SQUARE = ((-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (0, 1), (1, 1))
# Odd rows are drawn shifted right by half a cell, so their neighbours lean right.
HEX_EVEN = ((-1, -1), (0, -1), (-1, 0), (1, 0), (-1, 1), (0, 1))
HEX_ODD = ((0, -1), (1, -1), (-1, 0), (1, 0), (0, 1), (1, 1))

HIDDEN, OPEN, FLAG, PIG, BOOM = range(5)

NUM_COLOR = {1: 117, 2: 156, 3: 210, 4: 183, 5: 215, 6: 123, 7: 225, 8: 231}
SOIL = (236, 237)
LEAF_BG = (22, 28, 29, 64, 22, 28, 58, 94)
LEAF_FG = (70, 107, 142, 149, 136)
LEAF_TX = ("\"`", ",'", "`,", "''", ".,", "\" ", " ,", "'.")
CURSOR_BG = 222
SPARKLE = "*+.'`"


# ---------------------------------------------------------------- board logic

def neighbours(cols, rows, hexgrid):
    out = []
    for y in range(rows):
        for x in range(cols):
            deltas = (HEX_ODD if y % 2 else HEX_EVEN) if hexgrid else SQUARE
            out.append(tuple((y + dy) * cols + x + dx for dx, dy in deltas
                             if 0 <= x + dx < cols and 0 <= y + dy < rows))
    return out


def counts(mine, nbrs):
    return [sum(mine[j] for j in nb) for nb in nbrs]


def solve(nbrs, cnt, mine, start, total):
    """True if pure deduction from opening `start` clears every safe tile.

    Rules: a number's unknown neighbours are all safe / all mushrooms when its
    remaining count is 0 / equals them; for two overlapping numbers A and B, if
    B's surplus over A equals |B-A| then B-A are all mushrooms and A-B all safe
    (this covers the subset rule); finally the global remaining-mushroom count.
    """
    n = len(nbrs)
    state = bytearray(n)  # 0 unknown, 1 open, 2 known mushroom
    frontier = set()
    opened = known = 0

    def open_from(i):
        nonlocal opened
        stack = [i]
        while stack:
            j = stack.pop()
            if state[j]:
                continue
            if mine[j]:
                raise AssertionError("solver deduced a mushroom as safe")
            state[j] = 1
            opened += 1
            if cnt[j]:
                frontier.add(j)
            else:
                stack.extend(k for k in nbrs[j] if not state[k])

    open_from(start)
    goal = n - total
    while opened < goal:
        safe, bad, cons = set(), set(), []
        for i in list(frontier):
            unk, need = [], cnt[i]
            for j in nbrs[i]:
                s = state[j]
                if s == 0:
                    unk.append(j)
                elif s == 2:
                    need -= 1
            if not unk:
                frontier.discard(i)
            elif need == 0:
                safe.update(unk)
            elif need == len(unk):
                bad.update(unk)
            else:
                cons.append((frozenset(unk), need))
        if not safe and not bad:
            by_cell = {}
            for k, (s, _) in enumerate(cons):
                for j in s:
                    by_cell.setdefault(j, []).append(k)
            for k, (a, ca) in enumerate(cons):
                seen = {k}
                for j in a:
                    for m in by_cell[j]:
                        if m in seen:
                            continue
                        seen.add(m)
                        b, cb = cons[m]
                        only_b = b - a
                        if cb - ca == len(only_b):
                            bad |= only_b
                            safe |= a - b
        if not safe and not bad:
            rest = total - known
            if rest == 0:
                safe = {j for j in range(n) if not state[j]}
            elif rest == n - opened - known:
                bad = {j for j in range(n) if not state[j]}
            else:
                return False
        for j in bad:
            if not state[j]:
                state[j] = 2
                known += 1
        for j in safe:
            open_from(j)
    return True


def generate(nbrs, start, total, rng):
    """Place mushrooms away from `start` until the board is no-guess.

    Returns (mine, cnt, no_guess, attempts, seconds)."""
    t0 = time.perf_counter()
    banned = {start, *nbrs[start]}
    pool = [i for i in range(len(nbrs)) if i not in banned]
    total = min(total, len(pool))
    attempts = 0
    while True:
        attempts += 1
        mine = [False] * len(nbrs)
        for i in rng.sample(pool, total):
            mine[i] = True
        cnt = counts(mine, nbrs)
        ok = solve(nbrs, cnt, mine, start, total)
        took = time.perf_counter() - t0
        if ok or attempts >= GEN_TRIES or took > GEN_BUDGET:
            return mine, cnt, ok, attempts, took


def auto_dims(hexgrid):
    w, h = term.size()
    cols = max(8, min(30, (w - 2) // 2 - (1 if hexgrid else 0)))
    rows = max(6, min(16, h - 4))
    return cols, rows


# ---------------------------------------------------------------- game state

class Forage:
    def __init__(self, args, seed):
        self.args = args
        if args.size:
            self.cols, self.rows = SIZES[args.size]
            label = args.size
        else:
            self.cols, self.rows = auto_dims(args.hex)
            label = f"{self.cols}x{self.rows}"
        self.key = f"forage_{label}" + ("_hex" if args.hex else "")
        self.n = self.cols * self.rows
        self.total = max(1, min(self.n - 10, round(self.n * args.density)))
        self.nbrs = neighbours(self.cols, self.rows, args.hex)
        self.rng = random.Random(seed)
        self.seed = seed
        self.state = [HIDDEN] * self.n
        self.show_at = [0] * self.n
        self.mine = [False] * self.n
        self.cnt = [0] * self.n
        self.truffles = set()
        self.generated = False
        self.no_guess = None
        self.cur = (self.rows // 2) * self.cols + self.cols // 2
        self.hearts = HEARTS
        self.opened = 0
        self.found = 0          # truffles collected
        self.pig_used = 0
        self.time = 0.0
        self.paused = False
        self.over = None        # None, "win", "lose"
        self.score = 0
        self.new_best = False
        self.ripple_end = 0
        self.max_ring = 0
        self.pops = []          # (frame, cell) truffle sparkles waiting for the ripple
        self.parts = []         # [x, y, vx, vy, life, ch, color] in grid-relative coords
        self.msg, self.msg_col, self.msg_t = "", 231, 0.0
        self.shake = 0.0
        self.pig = None         # sniff animation: {"cell", "t"}
        self.frame = 0

    @property
    def safe_total(self):
        return self.n - self.total

    @property
    def charges(self):
        return self.opened // PIG_EVERY - self.pig_used

    def say(self, text, color=231, secs=2.5):
        self.msg, self.msg_col, self.msg_t = text, color, secs

    def xy(self, i):
        return i % self.cols, i // self.cols

    def screen_x(self, i):
        x, y = self.xy(i)
        return 2 * x + (y % 2 if self.args.hex else 0)

    def move(self, key):
        x, y = self.xy(self.cur)
        dx, dy = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}[key]
        x = max(0, min(self.cols - 1, x + dx))
        y = max(0, min(self.rows - 1, y + dy))
        self.cur = y * self.cols + x

    def build(self, start):
        self.mine, self.cnt, self.no_guess, attempts, took = generate(
            self.nbrs, start, self.total, self.rng)
        banned = {start, *self.nbrs[start]}
        spots = [i for i in range(self.n) if not self.mine[i] and i not in banned]
        k = min(len(spots), max(1, self.safe_total // TRUFFLE_EVERY))
        self.truffles = set(self.rng.sample(spots, k))
        self.generated = True
        if self.no_guess:
            self.say(f"no-guess board ready ({attempts} tries, {took * 1000:.0f}ms)", 150)
        else:
            self.say("couldn't find a no-guess board: a guess may be needed", 214, 4)

    def forage(self, i):
        if self.state[i] != HIDDEN:
            return
        if not self.generated:
            self.build(i)
        if self.mine[i]:
            self.state[i] = BOOM
            self.hearts -= 1
            audio.sfx("gameover" if self.hearts <= 0 else "tummy")
            self.shake = 0.4
            if self.hearts <= 0:
                self.over = "lose"
                self.say("tummy ache! the forest wins this time", 203, 99)
            else:
                self.say(f"tummy ache! {self.hearts} heart{'s' * (self.hearts > 1)} left", 203)
            return
        self.ripple(i)

    def ripple(self, start):
        """Open start; zeros spread outward in BFS rings, one ring per frame."""
        before = self.charges
        ring = [start]
        dist = 0
        while ring:
            nxt = []
            for j in ring:
                if self.state[j] != HIDDEN:
                    continue
                self.state[j] = OPEN
                self.opened += 1
                self.show_at[j] = self.frame + dist
                if j in self.truffles:
                    self.found += 1
                    self.pops.append((self.frame + dist, j))
                if self.cnt[j] == 0:
                    nxt.extend(k for k in self.nbrs[j] if self.state[k] == HIDDEN)
            if nxt:
                dist += 1
            ring = nxt
        self.max_ring = max(self.max_ring, dist)
        audio.sfx("ripple" if dist > 1 else "dig")
        self.ripple_end = max(self.ripple_end, self.frame + dist)
        if self.charges > before:
            self.say("the truffle pig is ready! press t", 218)

    def act(self):
        i = self.cur
        st = self.state[i]
        if st == HIDDEN:
            self.forage(i)
        elif st == OPEN and self.cnt[i]:
            marked = sum(self.state[j] in (FLAG, PIG, BOOM) for j in self.nbrs[i])
            if marked == self.cnt[i]:
                for j in self.nbrs[i]:
                    if self.over:
                        break
                    self.forage(j)

    def flag(self):
        st = self.state[self.cur]
        audio.sfx("tick")
        if st == HIDDEN:
            self.state[self.cur] = FLAG
        elif st == FLAG:
            self.state[self.cur] = HIDDEN

    def sniff(self):
        if not self.generated:
            self.say("forage first, the pig is still asleep", 218)
            return
        if self.charges <= 0:
            left = PIG_EVERY - self.opened % PIG_EVERY
            self.say(f"the pig needs {left} more cleared tiles", 218)
            return
        self.pig_used += 1
        area = (self.cur, *self.nbrs[self.cur])
        hits = 0
        for j in area:
            if self.mine[j] and self.state[j] in (HIDDEN, FLAG):
                self.state[j] = PIG
                hits += 1
            elif not self.mine[j] and self.state[j] == FLAG:
                self.state[j] = HIDDEN  # the pig noses away wrong flags too
        self.pig = {"cell": self.cur, "t": 1.2, "area": area}
        audio.sfx("sniff")
        self.say(f"snuffle snuffle... {hits} mushroom{'s' * (hits != 1)} found" if hits
                 else "snuffle... nothing but dirt here", 218)

    def marked(self):
        return sum(s in (FLAG, PIG, BOOM) for s in self.state)

    def finish(self):
        self.over = "win"
        audio.sfx("clear")
        base = 600 + 4 * self.safe_total
        self.score = max(0, base - int(self.time) + TRUFFLE_BONUS * self.found
                         - HEART_COST * (HEARTS - self.hearts))
        self.new_best = game.record(self.key, self.score)
        self.say("you cleared the forest floor!", 229, 99)

    def update(self, dt):
        if self.paused:
            return
        if self.generated and not self.over:
            self.time += dt
        self.msg_t -= dt
        self.shake = max(0.0, self.shake - dt)
        if self.pig:
            self.pig["t"] -= dt
            if self.pig["t"] <= 0:
                self.pig = None
        for p in self.pops[:]:
            if self.frame >= p[0]:
                self.pops.remove(p)
                self.burst(p[1], 14, (220, 226, 229, 179))
                self.say(f"a truffle! +{TRUFFLE_BONUS}", 220)
                audio.sfx("coin")
        for p in self.parts:
            p[0] += p[2] * dt
            p[1] += p[3] * dt
            p[3] += 9 * dt
            p[4] -= dt
        self.parts = [p for p in self.parts if p[4] > 0]
        if (not self.over and self.generated and self.opened >= self.safe_total
                and self.frame >= self.ripple_end):
            self.finish()

    def burst(self, i, count, colors):
        x, y = self.screen_x(i) + 0.5, self.xy(i)[1]
        for _ in range(count):
            self.parts.append([x, y, self.rng.uniform(-7, 7), self.rng.uniform(-6, 1),
                               self.rng.uniform(0.4, 1.0), self.rng.choice(SPARKLE),
                               self.rng.choice(colors)])


# ---------------------------------------------------------------- drawing

def leaf_hash(x, y):
    h = (x * 374761393 + y * 668265263) & 0xFFFFFFFF
    h = ((h ^ (h >> 13)) * 1274126177) & 0xFFFFFFFF
    return h >> 12  # low bits of the product repeat along diagonals


def leaf(x, y):
    h = leaf_hash(x, y)
    return (LEAF_TX[h % len(LEAF_TX)], LEAF_FG[(h >> 5) % len(LEAF_FG)],
            LEAF_BG[(h >> 11) % len(LEAF_BG)])


def look(g, i, frame):
    """(two chars, fg, bg) for cell i."""
    x, y = g.xy(i)
    st = g.state[i]
    over = g.over
    if over == "win":
        if g.mine[i]:
            return "()", 223, 130  # harmless now, just part of the clearing
        h = leaf_hash(x, y)
        if h % 9 == 0:
            return "*" + " ", (213, 228, 117, 219)[(h >> 4) % 4], 28
        return (",'", "  ", " ,", "  ")[h % 4], 71, 28
    if st == OPEN and frame >= g.show_at[i]:
        bg = SOIL[(x + y) % 2]
        k = g.cnt[i]
        if k:
            return f"{k} ", NUM_COLOR[k], bg
        return (" ." if leaf_hash(x, y) % 6 == 0 else "  "), 240, bg
    if st == OPEN and g.show_at[i] - frame == 1:
        return "~'", 193, 71  # the leaf lifting just ahead of the ripple
    if st == BOOM:
        return "••", 231, 160
    if st == PIG:
        return "••", 224, 132
    tx, fg, bg = leaf(x, y)
    if st == FLAG:
        if over == "lose" and not g.mine[i]:
            return "x ", 203, bg
        return " !", 226, bg
    if over == "lose" and g.mine[i]:
        return "••", 224, 88
    return tx, fg, bg


def panel(c, lines, top=None):
    bw = max(len(t) for t, _ in lines) + 4
    bh = len(lines) + 2
    x0 = (c.w - bw) // 2
    y0 = (c.h - bh) // 2 if top is None else top
    for y in range(bh):
        for x in range(bw):
            c.put(x0 + x, y0 + y, " ", bg=235)
    for i, (t, col) in enumerate(lines):
        c.text(x0 + (bw - len(t)) // 2, y0 + 1 + i, t, col, 235)
    return y0


def wrap_center(c, msg, color=231):
    lines = textwrap.wrap(msg, max(1, c.w)) or [""]
    for i, ln in enumerate(lines):
        c.text((c.w - len(ln)) // 2, (c.h - len(lines)) // 2 + i, ln, color)


def clock(secs):
    s = int(secs)
    return f"{s // 60}:{s % 60:02d}"


def draw_hud(c, g):
    segs = [("Mushroom Forage", 150),
            ("♥" * g.hearts + "♡" * (HEARTS - g.hearts), 203),
            (clock(g.time), 252),
            (f"truffles {g.found}", 179),
            (f"pig x{max(0, g.charges)}" if g.charges > 0
             else f"pig {g.opened % PIG_EVERY}/{PIG_EVERY}", 218),
            (f"shrooms {g.total - g.marked()}", 210)]
    if g.no_guess is True:
        segs.append(("no-guess", 114))
    elif g.no_guess is False:
        segs.append(("guess may be needed", 214))
    x = 1
    for t, col in segs:
        c.text(x, 0, t, col)
        x += len(t) + 2
    if g.msg_t > 0 and g.msg:
        c.text((c.w - len(g.msg)) // 2, 1, g.msg, g.msg_col)
    elif not g.generated:
        hint = "first forage is always safe"
        c.text((c.w - len(hint)) // 2, 1, hint, 244)
    ctl = "arrows/WASD move  space forage/chord  f flag  t pig  p pause  r new  q quit"
    if len(ctl) > c.w:
        ctl = "move  spc dig  f flag  t pig  p  r  q"
    c.text(max(0, (c.w - len(ctl)) // 2), c.h - 1, ctl, 244)


def draw_pig(c, g, ox, oy, frame):
    p = g.pig
    if not p:
        return
    for j in p["area"]:
        if frame % 4 < 2 and g.state[j] in (HIDDEN, FLAG):
            c.put(ox + g.screen_x(j), oy + g.xy(j)[1], " ", bg=175)
            c.put(ox + g.screen_x(j) + 1, oy + g.xy(j)[1], " ", bg=175)
    sx = ox + g.screen_x(p["cell"]) - 2
    sy = oy + g.xy(p["cell"])[1] - 2
    nose = "(oo)" if frame % 6 < 3 else "(OO)"
    bob = (frame // 3) % 2
    c.text(sx + bob, sy, " ^ ^ ", 218, 52)
    c.text(sx + bob, sy + 1, f"{nose}~", 218, 52)
    c.text(sx + 6 - bob, sy - 1 + bob, "sniff", 225)


def draw_win(c, g, frame):
    best = game.best(g.key)
    lines = [("\\ | /              .   ", 228),
             ("-- ( ) --   ,,  ()  ,,  ", 228),
             ("/ | \\    ,\\|/,     \\|/ ", 113),
             ("~ a sunny clearing ~", 229),
             (f"time {clock(g.time)}  truffles {g.found}  hearts {g.hearts}/{HEARTS}", 252),
             (f"score {g.score}" + ("  NEW BEST!" if g.new_best else f"  best {best}"), 220),
             ("r new board   q quit", 244)]
    rng = random.Random(frame // 3)
    for _ in range(10):
        c.put(rng.randrange(c.w), rng.randrange(2, max(3, c.h - 1)),
              rng.choice(SPARKLE), rng.choice((220, 226, 229, 213, 159)))
    panel(c, lines)


def draw(c, g, frame):
    gw = 2 * g.cols + (1 if g.args.hex else 0)
    if c.w < max(MIN_W, gw + 2) or c.h < max(MIN_H, g.rows + 3):
        wrap_center(c, "make the terminal bigger", 214)
        return
    ox = (c.w - gw) // 2 + (1 if g.shake > 0 and frame % 2 else -1 if g.shake > 0 else 0)
    oy = 2 + max(0, (c.h - 3 - g.rows) // 2)
    draw_hud(c, g)
    for i in range(g.n):
        sx, sy = ox + g.screen_x(i), oy + g.xy(i)[1]
        if g.paused:
            tx, fg, bg = leaf(*g.xy(i))
        else:
            tx, fg, bg = look(g, i, frame)
        if i == g.cur and not g.over and not g.paused:
            bg = CURSOR_BG
            fg = 16 if g.state[i] in (HIDDEN, OPEN) else fg
            if not term.COLOR:
                tx = "[]" if tx[0] in " \"'`,.~" else tx[0] + "<"
        c.put(sx, sy, tx[0], fg, bg)
        c.put(sx + 1, sy, tx[1], fg, bg)
    if g.paused:
        panel(c, [("paused", 229), ("the forest waits for you", 150), ("p resume   q quit", 244)])
        return
    draw_pig(c, g, ox, oy, frame)
    for p in g.parts:
        c.put(ox + p[0], oy + p[1], p[5], p[6])
    if g.over == "win":
        draw_win(c, g, frame)
    elif g.over == "lose":
        panel(c, [("three tummy aches...", 203), ("time to head home", 252),
                  ("r new board   q quit", 244)], top=c.h - 6)


# ---------------------------------------------------------------- main

def check(args, seed):
    if args.size:
        cols, rows = SIZES[args.size]
    else:
        cols, rows = auto_dims(args.hex)
    nbrs = neighbours(cols, rows, args.hex)
    n = cols * rows
    total = max(1, min(n - 10, round(n * args.density)))
    rng = random.Random(seed)
    ok = first = tries = 0
    times = []
    for _ in range(args.check):
        start = rng.randrange(n)
        _, _, good, attempts, took = generate(nbrs, start, total, rng)
        ok += good
        first += good and attempts == 1
        tries += attempts
        times.append(took)
    k = args.check
    grid = "hex" if args.hex else "square"
    print(f"{k} boards, {cols}x{rows} {grid}, {total} mushrooms ({total / n:.0%})")
    print(f"no-guess: {ok}/{k} ({ok / k:.0%}), fallbacks {k - ok}")
    print(f"raw solvable on first try: {first}/{k}; layouts tried: {tries} "
          f"(avg {tries / k:.1f}, single-layout solve rate {ok / max(1, tries):.0%})")
    print(f"generation: avg {sum(times) / k * 1000:.0f}ms, max {max(times) * 1000:.0f}ms")
    return 0 if ok == k else 1


def main():
    parser = term.make_parser(__doc__.splitlines()[0])
    parser.add_argument("--size", choices=sorted(SIZES), help="board size (default: fit terminal)")
    parser.add_argument("--density", type=float, default=DENSITY,
                        help=f"fraction of tiles hiding a mushroom (default {DENSITY})")
    parser.add_argument("--seed", type=int, help="random seed")
    parser.add_argument("--daily", action="store_true", help="seed from today's date")
    parser.add_argument("--hex", action="store_true", help="hex grid with 6 neighbours")
    parser.add_argument("--check", type=int, metavar="N",
                        help="generate N boards, print no-guess rate and timing, exit")
    args = parser.parse_args()
    if not 0.02 <= args.density <= 0.3:
        parser.error("--density must be between 0.02 and 0.3")
    if args.daily:
        seed = int(datetime.date.today().strftime("%Y%m%d"))
    elif args.seed is not None:
        seed = args.seed
    else:
        seed = random.randrange(1 << 30)
    if args.check:
        return check(args, seed)

    fixed = args.daily or args.seed is not None
    dt = 1 / max(1.0, args.fps)
    box = {"g": Forage(args, seed), "claude": False}

    def step(c, frame, keys):
        g = box["g"]
        g.frame = frame
        if frame % 10 == 0 and not box["claude"]:
            box["claude"] = game.claude_done()
        for k in keys:
            if k == "q":
                return True
            if k == "r":
                # A fixed seed replays the same board; otherwise roll a fresh one.
                g = box["g"] = Forage(args, seed if fixed else random.randrange(1 << 30))
                g.frame = frame
                continue
            if g.over:
                continue
            if k == "p":
                g.paused = not g.paused
            elif g.paused:
                if k == "esc":
                    g.paused = False
            elif k in ("up", "down", "left", "right"):
                g.move(k)
            elif k in ("space", "enter"):
                g.act()
            elif k == "f" and g.generated:
                g.flag()
            elif k == "t":
                g.sniff()
        g.update(dt)
        draw(c, g, frame)
        if box["claude"]:
            msg = " Claude's done! "
            c.text(c.w - len(msg) - 1, 1, msg, 231 if frame % 20 < 14 else 189, 25)
        return False

    code = game.play(args, step, music="forage")
    g = box["g"]
    if g.generated:
        result = {"win": "cleared", "lose": "lost"}.get(g.over, "foraging")
        print(f"forage: {result}, opened {g.opened}/{g.safe_total} tiles, "
              f"widest ripple {g.max_ring} rings, hearts {g.hearts}/{HEARTS}, "
              f"truffles {g.found}, no-guess {g.no_guess}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
