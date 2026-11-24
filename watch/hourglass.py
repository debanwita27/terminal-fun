#!/usr/bin/env python3
"""Hourglass: a falling-sand cellular automaton. Grains drain through the neck,
pile into a heap, and the glass flips when the top is empty (or when the Claude
status file says "done", which also shows "✓ done").

Usage: python3 hourglass.py [--fps 12] [--frames N] [--time SECONDS] [--sand PALETTE] [--seed N]

--time SECONDS paces the neck so the top bulb takes about that long to drain
(a flip and a short rest follow each round).
"""

META = {'name': 'hourglass',
 'kind': 'watch',
 'blurb': 'A falling-sand hourglass that flips when empty',
 'credit': {'type': 'inspired by',
            'who': 'falling-sand games',
            'url': 'https://en.wikipedia.org/wiki/Falling-sand_game'}}

import math
import random
import time

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

from fun import term

GLASS, CAP, SAND, DONE = 252, 130, 222, 46
FLIP_FRAMES = 9
IDLE_BEFORE_FLIP = 25   # frames to rest on an empty top bulb
GATE = 0.3              # chance a grain may enter the neck on a given step
STRATUM = 2             # rows per colour band in the starting fill

# Sand palettes (rgb); each grain keeps its colour, so bands stay visible as they pour.
PALETTES = {
    "desert": [(232, 196, 128), (214, 160, 92), (240, 218, 170), (196, 132, 74)],
    "sunset": [(255, 166, 120), (240, 110, 120), (255, 204, 128), (196, 96, 150)],
    "ocean": [(120, 200, 230), (70, 150, 210), (170, 230, 220), (40, 110, 180)],
    "candy": [(255, 170, 200), (180, 160, 255), (150, 230, 210), (255, 230, 150)],
    "forest": [(150, 200, 120), (90, 160, 100), (200, 220, 150), (120, 140, 80)],
    "violet": [(200, 160, 255), (150, 110, 220), (230, 200, 255), (120, 90, 190)],
    "ember": [(255, 120, 60), (230, 80, 50), (255, 180, 90), (180, 60, 40)],
    "rainbow": [(240, 100, 100), (250, 180, 90), (240, 230, 110), (120, 210, 120),
                (100, 170, 240), (170, 130, 230)],
    "mono": [(235, 235, 235), (190, 190, 190), (150, 150, 150)],
}


class Glass:
    def __init__(self, w, h, palette):
        gh = min(h - 2, 23)
        gh -= (gh % 2 == 0)
        self.gh, self.hh = gh, gh // 2
        self.wmax = min(self.hh, (w - 3) // 2) if gh >= 3 else 0
        self.ok = gh >= 3 and self.wmax >= 1
        if not self.ok:
            return
        self.cx = self.wmax
        self.g = [[None] * (2 * self.wmax + 1) for _ in range(gh)]  # grain colour or None
        self.moved = set()
        self.rate, self.budget = None, 0.0
        area = sum(2 * self.hw(y) + 1 for y in range(self.hh))
        n = 0
        start = random.randrange(len(palette))
        for y in range(self.hh - 1, -1, -1):
            band = palette[(start + (self.hh - 1 - y) // STRATUM) % len(palette)]
            for x in range(self.cx - self.hw(y), self.cx + self.hw(y) + 1):
                self.g[y][x] = band if random.random() > 0.08 else random.choice(palette)
            n += 2 * self.hw(y) + 1
            if n >= 0.6 * area:
                break

    def hw(self, y):
        return int(self.wmax * abs(y - self.hh) / self.hh + 0.5)

    def inside(self, y, x):
        return 0 <= y < self.gh and abs(x - self.cx) <= self.hw(y)

    def free(self, y, x):
        return self.inside(y, x) and not self.g[y][x]

    def arm(self, seconds, fps):
        """Pace the neck to drain the grains now in the top bulb in `seconds`."""
        n = sum(c is not None for y in range(self.hh + 1) for c in self.g[y])
        self.rate, self.budget = n / (seconds * fps), 0.0

    def step(self):
        self.moved = set()
        if self.rate is not None:
            self.budget = min(self.budget + self.rate, max(1.0, self.rate) + 1.0)
        xs = list(range(2 * self.wmax + 1))
        for y in range(self.gh - 2, -1, -1):
            random.shuffle(xs)
            for x in xs:
                grain = self.g[y][x]
                if grain is None:
                    continue
                neck = y + 1 == self.hh
                if neck and (self.budget < 1.0 if self.rate is not None else random.random() > GATE):
                    continue
                if self.free(y + 1, x):
                    nx = x
                else:
                    d = random.choice((-1, 1))
                    nx = next((x + k for k in (d, -d) if self.free(y + 1, x + k)), None)
                    if nx is None:
                        continue
                self.g[y][x], self.g[y + 1][nx] = None, grain
                if neck and self.rate is not None:
                    self.budget -= 1.0
                self.moved.add((y + 1, nx))

    def top_empty(self):
        return not any(any(self.g[y]) for y in range(self.hh + 1))

    def flip(self):
        m = 2 * self.wmax
        self.g = [[self.g[self.gh - 1 - y][m - x] for x in range(m + 1)]
                  for y in range(self.gh)]
        self.moved = set()

    def points(self):
        """(dx, dy, glyph, color) relative to the neck centre."""
        hh, pts = self.hh, []
        for dx in range(-self.wmax - 1, self.wmax + 2):
            pts.append((dx, -hh - 1, "═", CAP))
            pts.append((dx, hh + 1, "═", CAP))
        for y in range(self.gh):
            e, dy = self.hw(y) + 1, y - hh
            lc, rc = ("\\", "/") if dy < 0 else ("/", "\\") if dy > 0 else (">", "<")
            pts.append((-e, dy, lc, GLASS))
            pts.append((e, dy, rc, GLASS))
            for x, grain in enumerate(self.g[y]):
                if grain is not None:
                    fall = (y, x) in self.moved
                    pts.append((x - self.cx, dy, "•" if fall else "▒",
                                _lit(grain) if fall else grain))
        return pts


def _lit(c, k=0.35):
    """A falling grain catches the light: blend its colour toward white."""
    return tuple(round(v + (255 - v) * k) for v in c)


def main():
    parser = term.make_parser(__doc__.splitlines()[0], fps=12)
    parser.add_argument("--time", type=float, default=None, metavar="SECONDS",
                        help="seconds for the top bulb to drain (default: free-running)")
    parser.add_argument("--sand", choices=sorted(PALETTES), default=None,
                        help="sand palette (default: random each run)")
    parser.add_argument("--seed", type=int, default=None, help="random seed")
    args = parser.parse_args()
    random.seed(args.seed)
    palette = PALETTES[args.sand or random.choice(sorted(PALETTES))]
    if args.time is not None and args.time <= 0:
        parser.error("--time must be positive")
    s = {"key": None, "glass": None, "flip": -1, "idle": 0, "ts": None, "done": False,
         "start": time.time()}

    def step(c, frame):
        key = (c.w, c.h)
        if s["key"] != key:
            s.update(key=key, glass=Glass(c.w, c.h, palette), flip=-1, idle=0)
            if args.time and s["glass"].ok:
                s["glass"].arm(args.time, args.fps)
        g = s["glass"]
        if frame % 10 == 0:
            st = term.read_status()
            ts = st.get("ts") if st else None
            s["done"] = bool(st and st.get("state") == "done"
                             and isinstance(ts, (int, float)) and ts > s["start"])
            if s["done"] and g.ok and s["flip"] < 0 and st.get("ts") != s["ts"]:
                s["ts"], s["flip"] = st.get("ts"), 0
        if not g.ok:
            c.text(0, c.h // 2, "hourglass"[:c.w], SAND)
            return
        cx, cy = c.w // 2, (c.h - (g.gh + 2)) // 2 + 1 + g.hh
        if s["flip"] >= 0:
            th = math.pi * (s["flip"] + 1) / (FLIP_FRAMES + 1)
            ct, st_ = math.cos(th), math.sin(th)
            for dx, dy, ch, col in g.points():
                px, py = dx * 0.5, dy
                rx, ry = px * ct - py * st_, px * st_ + py * ct
                c.put(cx + round(rx * 2), cy + round(ry), ":" if ch in "▒•" else "o", col)
            s["flip"] += 1
            if s["flip"] >= FLIP_FRAMES:
                g.flip()
                if args.time:
                    g.arm(args.time, args.fps)
                s["flip"], s["idle"] = -1, 0
        else:
            g.step()
            s["idle"] = s["idle"] + 1 if g.top_empty() else 0
            if s["idle"] > IDLE_BEFORE_FLIP:
                s["flip"] = 0
            for dx, dy, ch, col in g.points():
                c.put(cx + dx, cy + dy, ch, col)
        if s["done"]:
            row = cy + g.hh + 2
            c.text(cx - 3, row if row < c.h else 0, "✓ done", DONE)

    return term.run(args, step, music="default")


if __name__ == "__main__":
    raise SystemExit(main())
