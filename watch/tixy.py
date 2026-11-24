#!/usr/bin/env python3
"""Tiny (t,i,x,y) formulas pulsing on a dot grid, alternating with ASCII glyph metaballs."""
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
from fun import term  # noqa: E402

META = {"name": "tixy", "kind": "watch", "blurb": "Tiny (t,i,x,y) formulas pulsing on a dot grid, plus glyph metaballs",
        "credit": [{"type": "inspired by", "who": "Martin Kleppe (@aemkei), tixy.land", "url": "https://tixy.land"},
                   {"type": "inspired by", "who": "Martin Kleppe (@aemkei), 187 bytes ASCII Meta Balls",
                    "url": "https://aem1k.com/meta/"}]}

N = 16
HOLD = 8.0         # seconds per formula
MODE_SECS = 60.0
FADE = 0.7         # seconds a formula takes to grow in and out

# Each formula is evaluated as lambda t, i, x, y: <source>; the same text is shown on screen.
FORMULAS = [
    "sin(t)",
    "sin(t - hypot(x - 7.5, y - 7.5) * .6)",
    "sin(x * .5 + t) * sin(y * .5 - t)",
    "sin(t * 2) * ((x + y) % 2 * 2 - 1)",
    "sin(i / 9 + t)",
    "sin(atan2(y - 7.5, x - 7.5) * 2 + hypot(x - 7.5, y - 7.5) * .5 - t * 2)",
    "random() * sin(t)",
    "sin(t + x * .4) * cos(t + y * .4)",
    "max(0, 1.2 - abs(y - 8 - sin(x * .5 + t) * 4))",
    "sin(hypot(x - 7.5, y - 7.5) * 1.2 - t * 3)",
    "sin((x - y) * .6 + t * 2)",
    "sin(t + (int(x) ^ int(y)) * .5)",
    "sin(t * 1.5 + i * i)",
    "1 - hypot(x - 7.5 - 5 * sin(t), y - 7.5 - 5 * cos(t * 1.3)) * .3",
    "((sin(t) + 1) * 4 - hypot(x - 7.5, y - 7.5)) / 3",
    "max(0, (sin(x * .7 + t * 2) * 6 + 7) - (15 - y)) / 3",
    "(sin(x * .4 + t) + sin(y * .4 + t * 1.3) + sin((x + y) * .3 - t)) / 2",
    "(int(x + t * 3) + int(y)) % 2 * 2 - 1",
    "sin(t * 2 - abs(x - 7.5) * .8 - abs(y - 7.5) * .8)",
    "((t * .3 + x / 16) % 1) * 2 - 1",
    "sin(atan2(y - 7.5, x - 7.5) - t * 2)",
    "sin(x * y * .05 - t)",
    "(x - 7.5) / 8 * sin(t)",
    "sin(t * 3) * sin(x * .8) * sin(y * .8)",
    "(sin(hypot(x - 3, y - 3) * .9 - t * 2) + sin(hypot(x - 12, y - 12) * .9 - t * 2)) / 2",
    "sin(y * .5 - t * 2) * cos(x * .3 + t)",
    "sin(i * .05 + t) * sin(t * .5) * 1.5",
]

POS_COL, NEG_COL, GRID_COL = 255, 203, 238
# Metaball field bands: (upper bound, glyph, colour).
BANDS = [(0.22, " ", None), (0.4, ".", 17), (0.6, ":", 24), (0.8, "-", 30), (0.97, "=", 37),
         (1.15, "#", 231), (1.6, "%", 183), (2.4, "@", 177), (99, "@", 141)]
QUANT = 12   # field quantisation steps per unit
QMAX = 47


def build_formulas(rng):
    env = {k: getattr(math, k) for k in ("sin", "cos", "tan", "atan2", "hypot", "sqrt", "floor", "pi", "exp")}
    env.update(abs=abs, int=int, min=min, max=max, random=rng.random)
    return [(src, eval("lambda t, i, x, y: " + src, {"__builtins__": {}, **env})) for src in FORMULAS]


def make_lut():
    lut = []
    for q in range(QMAX + 1):
        v = q / QUANT
        for hi, g, c in BANDS:
            if v < hi:
                lut.append((g, c, None))
                break
    return lut


class Tixy:
    def __init__(self, args):
        self.rng = random.Random(args.seed)
        self.args = args
        self.formulas = build_formulas(self.rng)
        self.order = list(range(len(self.formulas)))
        self.rng.shuffle(self.order)
        self.lut = make_lut()
        self.balls = [(self.rng.uniform(0.2, 0.6), self.rng.uniform(0.2, 0.6), self.rng.uniform(0, 6.28),
                       self.rng.uniform(0, 6.28), self.rng.uniform(0.7, 1.3)) for _ in range(5)]
        self.fps = args.fps

    def mode_at(self, t):
        if self.args.mode != "both":
            return self.args.mode
        return "tixy" if int(t / MODE_SECS) % 2 == 0 else "meta"

    def step(self, cv, frame):
        t = frame / self.fps
        if self.mode_at(t) == "tixy":
            self.draw_tixy(cv, t)
        else:
            self.draw_meta(cv, t)

    def dot(self, cv, ox, oy, s, v, fade):
        r = min(1.0, abs(v) * fade)
        pos = v >= 0
        col = POS_COL if pos else NEG_COL
        if not term.COLOR and not pos:
            small, mid, big, fill = "·", "◦", "○", "▒"
        else:
            small, mid, big, fill = "·", "•", "●", "█"
        cw = 2 * s
        cx, cy = ox + (cw - 1) // 2, oy + (s - 1) // 2
        if r < 0.08:
            cv.put(cx, cy, "·", GRID_COL)
        elif r < 0.25:
            cv.put(cx, cy, small, col)
        elif r < 0.45:
            cv.put(cx, cy, mid, col)
        elif r < 0.65 or s == 1 and r < 0.8:
            cv.put(cx, cy, big, col)
        elif s == 1:
            cv.put(ox, oy, fill, col)
            cv.put(ox + 1, oy, fill, col)
        else:
            rr = r * s / 2 + 0.2
            for j in range(s):
                ey = j + 0.5 - s / 2
                for i in range(cw):
                    ex = (i + 0.5 - s) / 2
                    if ex * ex + ey * ey <= rr * rr:
                        cv.put(ox + i, oy + j, fill, col)

    def draw_tixy(self, cv, t):
        w, h = cv.w, cv.h
        slot = int(t / HOLD)
        src, fn = self.formulas[self.order[slot % len(self.order)]]
        lt = t - slot * HOLD
        fade = min(1.0, lt / FADE, (HOLD - lt) / FADE)
        fade = max(0.0, fade) ** 0.7
        avail = h - 2 if h >= 20 else h
        nx, ny = min(N, max(1, w // 2)), min(N, max(1, avail))
        s = max(1, min(w // (2 * nx), avail // ny))
        ox0, oy0 = (w - nx * 2 * s) // 2, (avail - ny * s) // 2
        kx = (N - 1) / max(1, nx - 1)
        ky = (N - 1) / max(1, ny - 1)
        for gy in range(ny):
            y = gy * ky
            for gx in range(nx):
                x = gx * kx
                try:
                    v = fn(t, int(gy * ky) * N + int(x), x, y)
                except (ValueError, ZeroDivisionError, OverflowError):
                    v = 0.0
                self.dot(cv, ox0 + gx * 2 * s, oy0 + gy * s, s, v, fade)
        if h >= 20:
            label = "(t,i,x,y) => " + src
            cv.text((w - len(label)) // 2, h - 1, label[:w], 231)

    def draw_meta(self, cv, t):
        w, h = cv.w, cv.h
        lut = self.lut
        rows_by_ball = []
        rad = max(1.5, h * 0.1)
        xs = range(w)
        for fx, fy, px, py, sz in self.balls:
            bx = w / 2 + math.sin(t * 0.25 * fx * 2 + px) * w * fx * 0.8
            by = h / 2 + math.sin(t * 0.21 * fy * 2 + py) * h * fy * 0.75
            c = (rad * sz) ** 2
            cx2 = [(x - bx) * (x - bx) * 0.25 + 0.4 for x in xs]
            rows_by_ball.append((c, cx2, by))
        cells = cv.cells
        per_ball = []
        for y in range(h):
            per_ball = [[c / (a + (y - by) * (y - by)) for a in cx2] for c, cx2, by in rows_by_ball]
            cells[y] = [lut[min(int((a + b + c + d + e) * QUANT), QMAX)] for a, b, c, d, e in zip(*per_ball)]


def main():
    p = term.make_parser("tixy formula dot grids and ASCII metaballs", fps=12)
    p.add_argument("--mode", choices=("tixy", "meta", "both"), default="both",
                   help="tixy grid, metaballs, or alternate every ~60s (default both)")
    p.add_argument("--seed", type=int, default=None, help="random seed")
    args = p.parse_args()
    return term.run(args, Tixy(args).step, music="tixy")


if __name__ == "__main__":
    sys.exit(main())
