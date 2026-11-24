#!/usr/bin/env python3
"""Catstack: drop sliding cats onto a wobbly tower without letting any tumble off.

Usage: python3 catstack.py [--fps 20] [--frames N] [--seed N] [--start]
Space drops the cat, p pauses, q quits, r restarts. --start skips the title screen.
"""

META = {"name": "catstack", "kind": "play", "blurb": "Drop sliding cats into a wobbly tower",
        "credit": None}

import math
import random
import textwrap

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

from fun import audio, game, term

NAME = "catstack"
MIN_W, MIN_H = 30, 12
LIVES = 3
CAT_H = 3
PERFECT = 1  # centre distance (columns) that counts as a perfect drop
HUD_ROWS = 2
FALL_ACCEL, FALL_MAX = 90.0, 45.0


def _wide(w):
    mid = w - 2
    return ["/\\" + "_" * (w - 4) + "/\\",
            "(  o" + " " * (w - 8) + "o  )",
            "(" + " " * ((mid - 3) // 2) + "=w=" + " " * (mid - 3 - (mid - 3) // 2) + ")"]


# name: (sprite rows, colour, spawn weight)
CATS = {
    "kitten": (["/\\_/\\", "(o.o)", "(_u_)"], 252, 30),
    "tabby": (["/\\_|||_/\\", "( o   o )", "(  =w=  )"], 214, 40),
    "chonk": (_wide(15), 173, 25),
    "loaf": ([" .-^^^^^-. ", "( -  .  - )", "(___|_|___)"], 223, 5),
}
for _name, (_rows, _, _) in CATS.items():
    assert len({len(r) for r in _rows}) == 1, _name


def wrap_center(c, msg, color=231):
    lines = textwrap.wrap(msg, max(1, c.w)) or [""]
    for i, ln in enumerate(lines):
        c.text((c.w - len(ln)) // 2, (c.h - len(lines)) // 2 + i, ln, color)


def panel(c, lines):
    bw = max(len(t) for t, _ in lines) + 4
    bh = len(lines) + 2
    x0, y0 = (c.w - bw) // 2, (c.h - bh) // 2
    for y in range(bh):
        for x in range(bw):
            c.put(x0 + x, y0 + y, " ", bg=236)
    for i, (t, col) in enumerate(lines):
        c.text(x0 + (bw - len(t)) // 2, y0 + 1 + i, t, col, 236)


class Cat:
    def __init__(self, kind, x=0.0):
        self.kind, self.x = kind, x
        self.rows, self.color, _ = CATS[kind]
        self.w = len(self.rows[0])
        self.tilt = 0

    @property
    def cx(self):
        return self.x + (self.w - 1) / 2


class Stack:
    def __init__(self, args):
        self.rng = random.Random(args.seed)
        self.dt = 1 / max(1.0, args.fps)
        self.state = "play" if args.start else "title"
        self.paused = False
        self.new_best = False
        self.best = game.best(NAME)
        self.banner_until = -1
        self.stars = [(self.rng.random(), self.rng.random()) for _ in range(40)]
        self.reset()

    def reset(self):
        self.t = 0.0
        self.tower = []
        self.lives = LIVES
        self.purrs = 0
        self.cam = 0.0
        self.popups = []
        self.falling = None      # dropped cat in flight: [cat, world_y, vy]
        self.tumbling = None     # cat that missed: [cat, world_y, vy, vx, age]
        self.wait = 0.0          # pause before the next cat appears
        self.dir = 1
        self.mover = None
        self.mover_y = 0.0
        self.drops = 0

    @property
    def score(self):
        return len(self.tower) + self.purrs

    def pick(self):
        names = list(CATS)
        return self.rng.choices(names, [CATS[n][2] for n in names])[0]

    def speed(self, c):
        return min(55.0, 14 + 0.9 * len(self.tower)) * min(1.0, c.w / 80)

    def popup(self, x, wy, text, color):
        self.popups.append([x, wy, text, color, 1.3])

    def top_world(self):
        return -CAT_H * (len(self.tower) + 1)

    def gy(self, c):
        return c.h - 2

    def drop(self):
        m = self.mover
        self.falling = [m, self.mover_y, 6.0]
        self.mover = None
        self.drops += 1
        audio.sfx("drop")

    def land(self, c):
        cat = self.falling[0]
        self.falling = None
        below = self.tower[-1] if self.tower else None
        if below and not (below.x <= cat.cx <= below.x + below.w - 1):
            away = 1 if cat.cx > below.cx else -1
            self.tumbling = [cat, self.top_world(), 0.0, away * 14.0, 0.0]
            self.lives -= 1
            self.popup(cat.x + cat.w / 2, self.top_world() - 1, "mrrow!", 213)
            audio.sfx("mrrow")
            return
        if below:
            off = cat.cx - below.cx
            if abs(off) <= PERFECT:
                cat.x = below.x + (below.w - cat.w) / 2
                self.purrs += 1
                self.popup(cat.x + cat.w / 2, self.top_world() - 1, "purr~ +1", 118)
                audio.sfx("purr")
            elif cat.x < below.x or cat.x + cat.w > below.x + below.w:
                cat.tilt = 1 if off > 0 else -1
        self.tower.append(cat)
        audio.sfx("thud")
        self.wait = 0.25

    def update(self, c, keys):
        dt = self.dt
        self.t += dt
        gy = self.gy(c)
        target = max(0.0, CAT_H * len(self.tower) - (gy - (c.h // 2 + 1)))
        self.cam += (target - self.cam) * min(1.0, dt * 4)
        self.mover_y = HUD_ROWS + 1 - gy - self.cam  # world row of the sliding cat

        if self.mover is None and self.falling is None and self.tumbling is None and self.wait <= 0:
            if self.lives <= 0:
                self.finish()
                return
            self.dir = self.rng.choice((1, -1))
            self.mover = Cat(self.pick())
            self.mover.x = 0.0 if self.dir > 0 else c.w - self.mover.w
        self.wait -= dt

        m = self.mover
        if m:
            m.x += self.dir * self.speed(c) * dt
            if m.x <= 0:
                m.x, self.dir = 0.0, 1
            elif m.x >= c.w - m.w:
                m.x, self.dir = float(c.w - m.w), -1
            if "space" in keys:
                self.drop()
        if self.falling:
            f = self.falling
            f[2] = min(FALL_MAX, f[2] + FALL_ACCEL * dt)
            f[1] += f[2] * dt
            if f[1] >= self.top_world():
                f[1] = self.top_world()
                self.land(c)
        if self.tumbling:
            tm = self.tumbling
            tm[2] += FALL_ACCEL * dt
            tm[1] += tm[2] * dt
            tm[0].x += tm[3] * dt
            tm[4] += dt
            if tm[4] > 1.2:
                self.tumbling = None
                self.wait = 0.3
        for p in self.popups:
            p[1] -= 2 * dt
            p[4] -= dt
        self.popups = [p for p in self.popups if p[4] > 0]

    def finish(self):
        self.state = "over"
        audio.sfx("gameover")
        self.new_best = game.record(NAME, self.score)
        self.best = game.best(NAME)

    def sy(self, c, wy):
        return round(self.gy(c) + wy + self.cam)

    def sway(self, i):
        n = len(self.tower)
        if n < 8:
            return 0
        amp = min(2.4, (n - 7) * 0.15)
        return round(math.sin(self.t * 1.4) * amp * (i / n) ** 1.5)

    def draw_cat(self, c, cat, wy, dx=0):
        y0 = self.sy(c, wy)
        for r, row in enumerate(cat.rows):
            shift = cat.tilt if r == 0 else 0
            x0 = round(cat.x) + dx + shift
            lo, hi = len(row) - len(row.lstrip()), len(row.rstrip())
            for i, ch in enumerate(row):
                c.put(x0 + i, y0 + r, ch, cat.color, 16 if lo <= i < hi else None)

    def draw_scene(self, c):
        gy = self.gy(c)
        for sx, sy in self.stars:
            y = int((sy * (c.h - 2) + self.cam * 0.3) % (c.h - 2))
            c.put(int(sx * c.w), y, "." if sx < 0.5 else "*", 245 if sx < 0.7 else 250)
        gl = gy + self.cam
        if gl < c.h:
            c.text(0, round(gl), "=" * c.w, 94)
            c.text(0, round(gl) + 1, "#" * c.w, 58)
        for i, cat in enumerate(self.tower):
            self.draw_cat(c, cat, -CAT_H * (i + 1), self.sway(i))
        if self.mover:
            self.draw_cat(c, self.mover, self.mover_y)
        if self.falling:
            self.draw_cat(c, self.falling[0], self.falling[1])
        if self.tumbling:
            self.draw_cat(c, self.tumbling[0], self.tumbling[1])
        for p in self.popups:
            c.text(p[0] - len(p[2]) / 2, self.sy(c, p[1]), p[2], p[3])

    def draw_hud(self, c):
        for y in range(HUD_ROWS - 1):
            for x in range(c.w):
                c.put(x, y, " ", bg=235)
        c.text(1, 0, f"Height {len(self.tower)}", 231, 235)
        c.text(14, 0, f"Purrs {self.purrs}", 118, 235)
        c.text(25, 0, "<3 " * self.lives, 204, 235)
        c.text(max(25, c.w - 10), 0, f"best {self.best}", 226, 235)

    def draw_over(self, c):
        lines = [("THE TOWER FELL!", 196), ("", 231), (f"score {self.score}", 231),
                 (f"  height {len(self.tower)} + purrs {self.purrs}", 250), (f"best  {self.best}", 226)]
        if self.new_best:
            lines.append(("new best!", 213))
        lines += [("", 231), ("r again   q quit", 250)]
        panel(c, lines)


def main():
    parser = term.make_parser(__doc__.splitlines()[0])
    parser.add_argument("--seed", type=int, default=None, help="random seed")
    parser.add_argument("--start", action="store_true", help="skip the title screen")
    args = parser.parse_args()
    g = Stack(args)

    def step(c, frame, keys):
        if "q" in keys:
            return True
        if c.w < MIN_W or c.h < MIN_H:
            wrap_center(c, "make the terminal bigger")
            return False
        if frame % 10 == 0 and g.banner_until < 0 and game.claude_done():
            g.banner_until = frame + int(8 / g.dt)

        if g.state == "title":
            if "space" in keys or "enter" in keys:
                g.state = "play"
            g.t += g.dt
            g.mover_y = HUD_ROWS + 1 - g.gy(c)
            g.draw_scene(c)
            panel(c, [("C A T S T A C K", 214), ("", 231),
                      ("stack the cats into a tower!", 252),
                      ("centre outside the cat below = tumble", 252),
                      ("dead-centre drops purr for bonus", 252), ("", 231),
                      ("space   drop the cat", 231),
                      ("p pause    q quit    r restart after game over", 250), ("", 231),
                      ("press space to start", 226)])
        elif g.state == "play":
            if "p" in keys:
                g.paused = not g.paused
            if not g.paused:
                g.update(c, keys)
            g.draw_scene(c)
            g.draw_hud(c)
            if g.paused:
                panel(c, [("PAUSED", 226), ("p to resume", 250)])
            if g.state == "over":
                g.draw_over(c)
        else:
            if "r" in keys:
                g.reset()
                g.state = "play"
            g.draw_scene(c)
            g.draw_hud(c)
            g.draw_over(c)
        if frame < g.banner_until:
            msg = " Claude's done! "
            c.text((c.w - len(msg)) // 2, 1, msg, 16, 118)
        return False

    rc = game.play(args, step, music="catstack")
    if args.frames is not None:
        print(f"{NAME}: state={g.state} score={g.score} height={len(g.tower)} purrs={g.purrs} "
              f"lives={g.lives} drops={g.drops}")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
