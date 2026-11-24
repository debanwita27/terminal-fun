#!/usr/bin/env python3
"""Bugsquash: shoo the insects off the picnic cake before they eat it.

Usage: python3 bugsquash.py [--fps 20] [--frames N] [--seed N] [--start]
Arrows/WASD move the swatter, space swats, p pauses, q quits, r restarts.
--start skips the title screen. Squash ants, flies and beetles; spare the ladybugs.
"""

META = {"name": "bugsquash", "kind": "play", "blurb": "Swat ants, flies and beetles off the picnic cake; spare the ladybugs",
        "credit": None}

import math
import random
import textwrap

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

from fun import audio, game, term

NAME = "bugsquash"
MIN_W, MIN_H = 40, 16
ROUND = 75.0
BITES = 5
COMBO_WINDOW = 1.3
SWAT_COOLDOWN = 0.3
POINTS = {"ant": 10, "fly": 25, "beetle": 40}
LADYBUG_PENALTY = 30
MAX_BUGS = 30

# Cake rows, bottom-aligned; each bite trims the right edge.
CAKE = ["    ,    ", "    !    ", ".-~~~~~-.", "|:o:o:o:|", "|_______|"]
CAKE_COLOR = {",": 226, "!": 231, ".": 218, "-": 218, "~": 218, ":": 211, "o": 197, "|": 137, "_": 137}
CAKE_CUT = [None, 9, 7, 5, 3]  # visible columns after 0..4 bites
PLATE = "\\___________/"
BUG_COLOR = {"ant": 16, "fly": 16, "beetle": 22}


def cake_rows(bites):
    rows = CAKE[2:] if bites else CAKE
    cut = CAKE_CUT[bites]
    return rows if cut is None else [r[:cut] for r in rows]


def wrap_center(c, msg, color=231):
    lines = textwrap.wrap(msg, max(1, c.w)) or [""]
    for i, ln in enumerate(lines):
        c.text((c.w - len(ln)) // 2, (c.h - len(lines)) // 2 + i, ln, color)


def panel(c, lines):
    """Centered box of (text, color) lines."""
    bw = max(len(t) for t, _ in lines) + 4
    bh = len(lines) + 2
    x0, y0 = (c.w - bw) // 2, (c.h - bh) // 2
    for y in range(bh):
        for x in range(bw):
            c.put(x0 + x, y0 + y, " ", bg=236)
    for i, (t, col) in enumerate(lines):
        c.text(x0 + (bw - len(t)) // 2, y0 + 1 + i, t, col, 236)


class Bug:
    def __init__(self, kind, x, y, tx, ty, speed, rng, hp=1, phase=None):
        self.kind, self.x, self.y, self.tx, self.ty = kind, x, y, tx, ty
        self.speed, self.hp = speed, hp
        self.age, self.flash = 0.0, 0.0
        self.phase = rng.uniform(0, 6.28) if phase is None else phase
        self.zig, self.zig_t, self.dash = 0.0, 0.0, 1.0

    def update(self, dt, rng):
        self.age += dt
        self.flash = max(0.0, self.flash - dt)
        dx, dy = self.tx - self.x, self.ty - self.y
        # Distances are measured in visual units: a cell is twice as tall as wide.
        d = math.hypot(dx, 2 * dy) or 1.0
        ux, uy = dx / d, dy / d
        px, py = -2 * uy, ux / 2
        sp, side = self.speed, 0.0
        if self.kind == "ant":
            side = math.sin(self.age * 4 + self.phase) * 0.5
        elif self.kind == "fly":
            self.zig_t -= dt
            if self.zig_t <= 0:
                self.zig_t = rng.uniform(0.1, 0.35)
                self.zig = rng.uniform(-1, 1)
                self.dash = rng.choice((0.2, 0.8, 1.4, 1.4))
            side, sp = self.zig * 1.6, sp * self.dash
        self.x += (ux + px * side) * sp * dt
        self.y += (uy + py * side) * sp * dt

    def sprite(self):
        flap = int(self.age * (14 if self.kind == "fly" else 8)) % 2
        if self.kind == "ant":
            return ("/o\\", "\\o/")[flap]
        if self.kind == "fly":
            return ("~o~", "-o-")[flap]
        if self.kind == "beetle":
            return "(##)" if self.hp > 1 else "(#%)"
        return "(:)"


class Squash:
    def __init__(self, args):
        self.rng = random.Random(args.seed)
        self.dt = 1 / max(1.0, args.fps)
        self.state = "play" if args.start else "title"
        self.paused = False
        self.new_best = False
        self.best = game.best(NAME)
        self.banner_until = -1
        self.fx = self.fy = 0
        self.reset()

    def reset(self):
        self.t = 0.0
        self.score = self.kills = self.swats = self.bites = 0
        self.combo, self.last_kill = 0, -99.0
        self.bugs, self.splats, self.popups = [], [], []
        self.cx = self.cy = None
        self.cool, self.swat_t = 0.0, 9.0
        self.spawn_in = 1.0
        self.lady_in = 12.0
        self.food_flash = 0.0
        self.result = ""
        self.bonus = 0

    def layout(self, c):
        self.bw, self.bh = min(c.w - 6, 46), min(c.h - 4, 14)
        self.bx, self.by = (c.w - self.bw) // 2, (c.h - self.bh) // 2 + 1
        self.fx, self.fy = c.w // 2, self.by + self.bh // 2 - 1

    def edge_point(self, c):
        side, r = self.rng.randrange(4), self.rng.uniform
        if side == 0:
            return r(2, c.w - 2), -1
        if side == 1:
            return r(2, c.w - 2), c.h
        if side == 2:
            return -2, r(2, c.h - 2)
        return c.w + 1, r(2, c.h - 2)

    def spawn(self, c):
        rng, t = self.rng, self.t
        scale = 1 + t / 100
        kinds = [("ant", 5), ("fly", 0 if t < 12 else 2 + t / 30), ("beetle", 0 if t < 22 else 1 + t / 40)]
        kind = rng.choices([k for k, _ in kinds], [w for _, w in kinds])[0]
        sx, sy = self.edge_point(c)
        tx, ty = self.fx + rng.uniform(-3, 3), self.fy + rng.uniform(-1, 1)
        if kind == "ant":
            d = math.hypot(tx - sx, 2 * (ty - sy)) or 1.0
            ux, uy = (sx - tx) / d, (sy - ty) / d
            phase = rng.uniform(0, 6.28)
            for i in range(rng.randint(3, 5)):
                self.bugs.append(Bug("ant", sx + ux * 3.2 * i, sy + uy * 3.2 * i, tx, ty,
                                     4.5 * scale, rng, phase=phase))
        elif kind == "fly":
            self.bugs.append(Bug("fly", sx, sy, tx, ty, 10 * scale, rng))
        else:
            self.bugs.append(Bug("beetle", sx, sy, tx, ty, 3 * scale, rng, hp=2))

    def spawn_ladybug(self, c):
        sx, sy = self.edge_point(c)
        self.bugs.append(Bug("lady", sx, sy, c.w - sx, c.h - sy, 2.5, self.rng))

    def popup(self, x, y, text, color):
        self.popups.append([x - len(text) / 2, y, text, color, 1.2])

    def swat(self):
        self.cool, self.swat_t = SWAT_COOLDOWN, 0.0
        self.swats += 1
        audio.sfx("swat")
        for b in list(self.bugs):
            if abs(round(b.x) - self.cx) <= 3 and abs(round(b.y) - self.cy) <= 1:
                b.hp -= 1
                if b.hp > 0:
                    b.flash = 0.25
                    self.popup(b.x, b.y - 1, "clunk!", 250)
                    audio.sfx("bonk")
                else:
                    self.kill(b)

    def kill(self, b):
        self.bugs.remove(b)
        self.splats.append([b.x, b.y, 0.0, b.kind])
        audio.sfx("splat")
        if b.kind == "lady":
            self.score = max(0, self.score - LADYBUG_PENALTY)
            self.combo = 0
            self.popup(b.x, b.y - 1, f"aww! -{LADYBUG_PENALTY}", 213)
            audio.sfx("tummy")
            return
        self.combo = self.combo + 1 if self.t - self.last_kill <= COMBO_WINDOW else 1
        self.last_kill = self.t
        pts = POINTS[b.kind] + 5 * (self.combo - 1)
        self.score += pts
        self.kills += 1
        self.popup(b.x, b.y - 1, f"+{pts}", 226)
        if self.combo >= 2:
            self.popup(b.x, b.y - 2, f"x{self.combo} combo!", 208)

    def finish(self, result):
        self.state, self.result = "over", result
        audio.sfx("clear" if result == "saved" else "gameover")
        if result == "saved":
            self.bonus = 50 * (BITES - self.bites)
            self.score += self.bonus
        self.new_best = game.record(NAME, self.score)
        self.best = game.best(NAME)

    def update(self, c, keys):
        dt, rng = self.dt, self.rng
        if self.cx is None:
            self.cx, self.cy = c.w // 2 + 8, self.fy + 3
        for k in keys:
            if k == "left":
                self.cx -= 2
            elif k == "right":
                self.cx += 2
            elif k == "up":
                self.cy -= 1
            elif k == "down":
                self.cy += 1
        self.cx = min(max(self.cx, 3), c.w - 4)
        self.cy = min(max(self.cy, 2), c.h - 3)
        self.cool -= dt
        self.swat_t += dt
        if "space" in keys and self.cool <= 0:
            self.swat()

        self.t += dt
        self.spawn_in -= dt
        if self.spawn_in <= 0 and len(self.bugs) < MAX_BUGS:
            self.spawn(c)
            self.spawn_in = max(0.45, 2.2 - self.t * 0.022) * rng.uniform(0.7, 1.3)
        self.lady_in -= dt
        if self.lady_in <= 0 and self.t > 6:
            if sum(b.kind == "lady" for b in self.bugs) < 2:
                self.spawn_ladybug(c)
            self.lady_in = rng.uniform(10, 16)

        for b in list(self.bugs):
            b.update(dt, rng)
            if b.kind == "lady":
                if b.age > 1 and not (-6 < b.x < c.w + 6 and -4 < b.y < c.h + 4):
                    self.bugs.remove(b)
            elif abs(b.x - self.fx) <= 6 and abs(b.y - self.fy) <= 2:
                self.bugs.remove(b)
                self.bites += 1
                self.food_flash = 0.4
                self.popup(self.fx, self.fy - 3, "munch!", 196)
                audio.sfx("thud")
        for s in self.splats:
            s[2] += dt
        self.splats = [s for s in self.splats if s[2] < 2.5]
        for p in self.popups:
            p[1] -= 3 * dt
            p[4] -= dt
        self.popups = [p for p in self.popups if p[4] > 0]
        self.food_flash = max(0.0, self.food_flash - dt)
        if self.t - self.last_kill > COMBO_WINDOW:
            self.combo = 0

        if self.bites >= BITES:
            self.finish("eaten")
        elif self.t >= ROUND:
            self.finish("saved")

    def draw_scene(self, c, live=True):
        for y in range(c.h):
            for x in range(c.w):
                c.put(x, y, "," if (x * 7 + y * 13) % 17 == 0 else " ", 34, 28)
        for y in range(self.bh):
            for x in range(self.bw):
                red = (x // 4 + y // 2) % 2 == 0
                c.put(self.bx + x, self.by + y, "▒" if red else " ", 160 if red else None, 167 if red else 230)
        rows = cake_rows(min(self.bites, BITES - 1))
        base = self.fy + 1
        c.text(self.fx - 6, base + 1, PLATE, 231)
        for i, row in enumerate(rows):
            y = base - len(rows) + 1 + i
            for j, ch in enumerate(row):
                c.put(self.fx - 4 + j, y, ch, 196 if self.food_flash else CAKE_COLOR.get(ch, 137))
        if not live:
            return
        for s in self.splats:
            x, y, age, kind = s
            if age < 0.2:
                for i, row in enumerate((" \\|/ ", "-=*=-", " /|\\ ")):
                    c.text(round(x) - 2, round(y) - 1 + i, row, 226)
            else:
                col = 160 if kind == "lady" else BUG_COLOR.get(kind, 16)
                c.text(round(x) - 2, round(y), ".%*%.", col)
                c.text(round(x) - 2, round(y) + 1, " '`' ", col)
        for b in self.bugs:
            sp = b.sprite()
            x, y = round(b.x) - len(sp) // 2, round(b.y)
            if b.kind == "lady":
                c.text(x, y, sp, 16, 196)
            else:
                c.text(x, y, sp, 196 if b.flash else BUG_COLOR[b.kind], 252 if b.flash else None)
        for p in self.popups:
            c.text(p[0], p[1], p[2], p[3])
        if self.cx is not None:
            if self.swat_t < 0.1:
                for dy in (-1, 0, 1):
                    for dx in range(-3, 4):
                        c.put(self.cx + dx, self.cy + dy, "#", 16, 231)
            elif self.swat_t < 0.25:
                for dx, dy in ((-3, -1), (3, -1), (-3, 1), (3, 1)):
                    c.put(self.cx + dx, self.cy + dy, "*", 231)
            else:
                for dx, dy, ch in ((-3, -1, "┌"), (3, -1, "┐"), (-3, 1, "└"), (3, 1, "┘"), (0, 0, "+")):
                    c.put(self.cx + dx, self.cy + dy, ch, 226 if self.cool <= 0 else 244)

    def draw_hud(self, c):
        for x in range(c.w):
            c.put(x, 0, " ", bg=235)
        left = self.bites and BITES - self.bites
        cake = "#" * (BITES - self.bites) + "." * self.bites
        c.text(1, 0, f"Score {self.score}", 231, 235)
        c.text(14, 0, f"Time {max(0, int(ROUND - self.t))}s", 250, 235)
        c.text(25, 0, f"Cake [{cake}]", 218 if left != 1 else 196, 235)
        if self.combo >= 2:
            c.text(c.w - 12, 0, f"COMBO x{self.combo}", 208, 235)

    def draw_over(self, c):
        saved = self.result == "saved"
        lines = [("THE PICNIC IS SAVED!" if saved else "THE CAKE IS GONE!", 118 if saved else 196),
                 ("", 231), (f"score {self.score}", 231), (f"best  {self.best}", 226)]
        if saved:
            lines.insert(2, (f"cake bonus +{self.bonus}", 218))
        if self.new_best:
            lines.append(("new best!", 213))
        lines += [("", 231), ("r again   q quit", 250)]
        panel(c, lines)


def main():
    parser = term.make_parser(__doc__.splitlines()[0])
    parser.add_argument("--seed", type=int, default=None, help="random seed")
    parser.add_argument("--start", action="store_true", help="skip the title screen")
    args = parser.parse_args()
    g = Squash(args)

    def step(c, frame, keys):
        if "q" in keys:
            return True
        if c.w < MIN_W or c.h < MIN_H:
            wrap_center(c, "make the terminal bigger")
            return False
        g.layout(c)
        if frame % 10 == 0 and g.banner_until < 0 and game.claude_done():
            g.banner_until = frame + int(8 / g.dt)

        if g.state == "title":
            if "space" in keys or "enter" in keys:
                g.state = "play"
            g.draw_scene(c, live=False)
            panel(c, [("B U G S Q U A S H", 118), ("", 231),
                      ("shoo the bugs off the cake!", 252),
                      ("ants, flies, beetles (2 hits). spare the ladybugs!", 252), ("", 231),
                      ("arrows / WASD   move the swatter", 231),
                      ("space           swat", 231),
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

    rc = game.play(args, step, music="bugsquash")
    if args.frames is not None:
        print(f"{NAME}: state={g.state} score={g.score} swats={g.swats} kills={g.kills} "
              f"bites={g.bites} cursor={g.cx},{g.cy}")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
