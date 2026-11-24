#!/usr/bin/env python3
"""A spring-loaded brush painting fading ink strokes."""
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
from fun import term  # noqa: E402

META = {"name": "dyna", "kind": "watch", "blurb": "A spring-loaded brush painting fading ink strokes",
        "credit": [{"type": "inspired by", "who": "Andreas Gysin (@andreasgysin), Dyna",
                    "url": "https://x.com/andreasgysin/status/1957692884292968520"},
                   {"type": "inspired by", "who": "Paul Haeberli, DynaDraw (1989)",
                    "url": "https://www.graficaobscura.com/dyna/"}]}

GLYPHS = " .:░▒▓Ñ#"
# Paper (dark ink on light) and chalkboard (light ink on dark) ink ramps, faint to full.
PAPER = (254, [253, 251, 249, 246, 243, 240, 237, 234])
BOARD = (233, [235, 238, 241, 244, 247, 250, 253, 255])
MASS, DRAG = 1.0, 0.82   # spring pulls toward the hand; DRAG keeps this fraction of velocity per step
STIFF = 0.09
INK_HALF_LIFE = 5.0      # seconds for a cell's ink to halve
sin, cos = math.sin, math.cos


class Hand:
    """The target: a sum of slow sines in two axes with drifting frequencies, so the path
    never exactly repeats."""

    def __init__(self, rng):
        self.fx = [rng.uniform(0.5, 1.5) for _ in range(3)]
        self.fy = [rng.uniform(0.5, 1.5) for _ in range(3)]
        self.px = [rng.uniform(0, 6.3) for _ in range(3)]
        self.py = [rng.uniform(0, 6.3) for _ in range(3)]
        self.ax, self.ay = (0.5, 0.3, 0.2), (0.5, 0.3, 0.2)

    def at(self, t):
        x = sum(a * sin(f * t * (1 + 0.15 * sin(t * 0.05 + i)) + p)
                for i, (a, f, p) in enumerate(zip(self.ax, self.fx, self.px)))
        y = sum(a * sin(f * t * (1 + 0.15 * cos(t * 0.04 + i)) + p)
                for i, (a, f, p) in enumerate(zip(self.ay, self.fy, self.py)))
        return x, y


def main():
    p = term.make_parser("A spring-loaded brush painting fading ink strokes", fps=12)
    p.add_argument("--speed", type=float, default=1.0, help="hand speed multiplier (default 1)")
    p.add_argument("--look", choices=("paper", "board", "both"), default="both",
                   help="ink look; both alternates (default both)")
    p.add_argument("--seed", type=int, default=None, help="random seed")
    args = p.parse_args()
    rng = random.Random(args.seed)
    hand = Hand(rng)
    st = {"x": 0.0, "y": 0.0, "vx": 0.0, "vy": 0.0, "ink": None, "size": None, "look": 0.0}
    substeps = 6
    n_look = {"paper": [0], "board": [1], "both": [0, 1]}[args.look]

    def step(cv, frame):
        w, h = cv.w, cv.h
        if st["size"] != (w, h):
            st["size"] = (w, h)
            st["ink"] = [[0.0] * w for _ in range(h)]
            st["x"], st["y"] = w / 2, h / 2
        ink = st["ink"]
        dt = 1 / 12
        t = frame * dt * args.speed

        decay = 0.5 ** (dt / INK_HALF_LIFE)
        for row in ink:
            for x in range(w):
                if row[x]:
                    v = row[x] * decay
                    row[x] = v if v > 0.04 else 0.0

        # Pen state is in cell units; y is doubled so motion looks isotropic on screen.
        sx, sy = (w - 1) / 2, (h - 1) / 2
        x, y, vx, vy = st["x"], st["y"], st["vx"], st["vy"]
        for s in range(substeps):
            tx, ty = hand.at(t + s * dt * args.speed / substeps)
            tx, ty = sx + tx * sx * 0.95, sy + ty * sy * 0.95
            ax, ay = (tx - x) * STIFF / MASS, (ty - y) * STIFF / MASS * 2
            vx = (vx + ax) * DRAG
            vy = (vy + ay) * DRAG
            x += vx
            y += vy / 2
            x = min(max(x, 0.0), w - 1.0)
            y = min(max(y, 0.0), h - 1.0)
            speed = math.hypot(vx, vy)
            # DynaDraw: the faster the pen, the thinner the line.
            width = 0.4 + 2.6 / (1 + speed * 1.3)
            r = width
            for yy in range(int(y - r / 2), int(y + r / 2) + 2):
                if not 0 <= yy < h:
                    continue
                for xx in range(int(x - r), int(x + r) + 2):
                    if 0 <= xx < w:
                        d = math.hypot((xx - x) / r, (yy - y) / (r / 2 + 0.01))
                        if d < 1.0:
                            val = (1 - d) * 0.7 + 0.35
                            if val > ink[yy][xx]:
                                ink[yy][xx] = min(1.0, val)
        st["x"], st["y"], st["vx"], st["vy"] = x, y, vx, vy

        # Ink look changes slowly; `look` eases between the two ramps so the switch is soft.
        period = 60.0
        idx = n_look[int(t / period) % len(n_look)]
        target = float(idx)
        st["look"] += (target - st["look"]) * min(1.0, dt * 0.6)
        mix = st["look"]
        bgp, rp = PAPER
        bgb, rb = BOARD
        bg = round(bgp + (bgb - bgp) * mix)
        ramp = [round(a + (b - a) * mix) for a, b in zip(rp, rb)]
        top = len(GLYPHS) - 1
        cells = cv.cells
        for yy in range(h):
            row, crow = ink[yy], cells[yy]
            for xx in range(w):
                v = row[xx]
                if v:
                    k = int(v * top + 0.5)
                    crow[xx] = (GLYPHS[k], ramp[k], bg) if k else (" ", None, bg)
                else:
                    crow[xx] = (" ", None, bg)

    return term.run(args, step, music="dyna")


if __name__ == "__main__":
    sys.exit(main())
