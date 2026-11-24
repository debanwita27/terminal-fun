#!/usr/bin/env python3
"""Space colonization: trees, roots, lightning and coral grown from scattered attractors.

Usage: python3 spacecol.py [--mode tree|roots|lightning|coral|veins] [--seed N] [--fps 12] [--frames N]
Each piece grows, holds, fades, and the next one starts; modes rotate unless --mode is given.
"""

META = {'name': 'spacecol',
 'kind': 'watch',
 'blurb': 'Trees, roots, lightning, coral and veins grown from scattered attractors',
 'credit': [{'type': 'inspired by',
             'who': 'Runions, Lane & Prusinkiewicz, Modeling Trees with a Space Colonization '
                    'Algorithm (2007)',
             'url': 'https://www.algorithmicbotany.org/papers/colonization.egwnp2007.html'},
            {'type': 'inspired by',
             'who': 'drawille by asciimoo (braille-dot terminal drawing)',
             'url': 'https://github.com/asciimoo/drawille'}]}

import bisect
import math
import random

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

from fun import braille, term

ROTATION = ["tree", "roots", "lightning", "coral", "tree", "roots", "lightning", "veins"]
MODES = ["tree", "roots", "lightning", "coral", "veins"]

# Per kind: colour and line width (dots) for each descendant-count bracket, thin tips first.
STYLE = {
    "tree": ([143, 137, 130, 94, 58], [1, 1, 2, 3, 4]),
    "roots": ([223, 180, 137, 130, 94], [1, 1, 2, 2, 3]),
    "lightning": ([75, 111, 153, 195, 231], [1, 1, 1, 2, 3]),
    "coral": ([219, 213, 205, 168, 125], [1, 1, 1, 2, 3]),
    "veins": ([157, 114, 77, 35, 29], [1, 1, 1, 2, 2]),
}
ITERS_PER_FRAME = {"tree": 0.6, "roots": 0.6, "lightning": 2.5, "coral": 0.7, "veins": 0.6}
LEAF_DEPTH = 9      # leafy nodes per twig, counted back from each tip
LEAF_DOTS = 7       # braille dots scattered around each leafy node
LEAF_SPREAD = 5.0   # scatter radius, in braille pixels
LEAF_PALETTES = [[34, 40, 46, 76, 112], [205, 211, 218, 225], [166, 172, 208, 214, 160]]
OFFSETS = {1: (0,), 2: (0, 1), 3: (0, -1, 1), 4: (0, -1, 1, 2)}
BASE_THRESH = [3, 10, 35, 100]
SOLID = 99  # a cell bracket no edge can overwrite

_LEVELS = (0, 95, 135, 175, 215, 255)
_dim_cache = {}


def _rgb(i):
    if i >= 232:
        g = 8 + 10 * (i - 232)
        return g, g, g
    if i < 16:
        return 170, 170, 170
    i -= 16
    return _LEVELS[i // 36], _LEVELS[i // 6 % 6], _LEVELS[i % 6]


def dim(col, f):
    """Nearest 256-colour to `col` blended f of the way to black."""
    key = (col, int(f * 12))
    if key not in _dim_cache:
        k = 1 - key[1] / 12
        r, g, b = (v * k for v in _rgb(col))
        near = [min(range(6), key=lambda j: abs(_LEVELS[j] - v)) for v in (r, g, b)]
        cube = (_LEVELS[near[0]], _LEVELS[near[1]], _LEVELS[near[2]])
        gi = max(0, min(23, round(((r + g + b) / 3 - 8) / 10)))
        gv = 8 + 10 * gi

        def err(c):
            return (c[0] - r) ** 2 + (c[1] - g) ** 2 + (c[2] - b) ** 2
        _dim_cache[key] = (16 + 36 * near[0] + 6 * near[1] + near[2]
                           if err(cube) <= err((gv, gv, gv)) else 232 + gi)
    return _dim_cache[key]


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def scatter(kind, W, H, rng):
    """Return (attractors, root, lead direction) for a piece."""
    cx = W / 2
    pts = []
    if kind == "tree":
        n = clamp(int(W * H * 0.04), 12, 600)
        ccy, rx, ry = H * 0.38, W * 0.32, H * 0.25
        p1, p2 = rng.uniform(0, 6.28), rng.uniform(0, 6.28)
        for _ in range(n):
            th, r = rng.uniform(0, 6.283), math.sqrt(rng.random())
            k = 1 + 0.22 * math.sin(3 * th + p1) + 0.12 * math.sin(5 * th + p2)
            pts.append((cx + rx * k * r * math.cos(th), max(1, ccy + ry * k * r * math.sin(th))))
        return pts, (cx, H - 1), (0, -1)
    if kind == "roots":
        y0 = int(H * 0.28)
        n = clamp(int(W * H * 0.02), 12, 350)
        for _ in range(n):
            y = rng.uniform(y0 + 3, H - 1)
            hw = min(W * 0.46, W * 0.10 + (y - y0) * 0.55)
            pts.append((cx + rng.uniform(-hw, hw), y))
        return pts, (cx, y0), (0, 1)
    if kind == "lightning":
        n = clamp(int(W * H * 0.012), 12, 220)
        x1 = rng.uniform(0.2, 0.8) * W
        x0 = clamp(x1 + rng.uniform(-0.25, 0.25) * W, 0.15 * W, 0.85 * W)
        knots = [x0] + [clamp(x0 + (x1 - x0) * i / 6 + rng.uniform(-0.12, 0.12) * W, 0.1 * W, 0.9 * W)
                        for i in range(1, 6)] + [x1]
        bw = max(3, W * 0.06)
        for _ in range(n):
            t = rng.random()
            i = min(5, int(t * 6))
            u = t * 6 - i
            x = knots[i] * (1 - u) + knots[i + 1] * u + rng.uniform(-bw, bw)
            pts.append((clamp(x, 0, W - 1), H * 0.03 + t * H * 0.94))
        return pts, (x0, 0), (0, 1)
    if kind == "coral":
        rad = min(W, H) * 0.46
        n = clamp(int(math.pi * rad * rad * 0.04), 12, 450)
        for _ in range(n):
            th, r = rng.uniform(0, 6.283), rad * math.sqrt(rng.random())
            pts.append((cx + r * math.cos(th), H / 2 + r * math.sin(th)))
        th = rng.uniform(0, 6.283)
        return pts, (cx, H / 2), (math.cos(th), math.sin(th))
    hw = min(W * 0.45, H * 0.38)  # veins: a leaf-shaped lens, root at the stalk
    n = clamp(int(hw * H * 0.05), 12, 450)
    for _ in range(n):
        t = rng.random()
        pts.append((cx + rng.uniform(-1, 1) * hw * math.sin(math.pi * t) ** 0.7, H * 0.97 - t * H * 0.9))
    return pts, (cx, H * 0.97), (0, -1)


class Piece:
    def __init__(self, kind, W, H, rng):
        self.kind, self.W, self.H, self.rng = kind, W, H, rng
        s = clamp(min(W / 160, H / 96), 0.35, 3)
        self.step = max(1.0, 1.15 * s) * (1.4 if kind == "lightning" else 1)
        self.R = max(9.0, 22 * s)
        self.R2 = self.R ** 2
        self.kill2 = max(2.4, 4.2 * s) ** 2
        self.pal, self.wid = STYLE[kind]
        self.br = braille.Braille(W // 2, H // 4)
        self.cb = [[-1] * self.br.cols for _ in range(self.br.rows)]
        pts, root, self.lead = scatter(kind, W, H, rng)
        self.ax = [p[0] for p in pts]
        self.ay = [p[1] for p in pts]
        self.alive = list(range(len(pts)))
        self.live = [True] * len(pts)
        self.agrid = {}
        for a, (x, y) in enumerate(pts):
            self.agrid.setdefault(self._cell(x, y), []).append(a)
        k = clamp(len(pts) / 300, 0.3, 1.5)
        self.thresh = [t * k for t in BASE_THRESH]
        self.nx, self.ny, self.par, self.cnt, self.bk = [], [], [], [], []
        self.grid = {}
        self.leads = 0
        self.lead_limit = int(max(W, H) / self.step)
        self.iters = 0
        self.done = False
        self.leaves = []
        if kind == "roots":
            self._decor(rng)
        self._add(root[0], root[1], -1)

    def _cell(self, x, y):
        return int(x // self.R), int(y // self.R)

    def _static(self, x, y, col):
        self.br.dot(x, y, col)
        if 0 <= x < self.W and 0 <= y < self.H:
            self.cb[int(y) >> 2][int(x) >> 1] = SOLID

    def _decor(self, rng):
        W, H = self.W, self.H
        y0 = int(H * 0.28)
        for x in range(0, W, 2):
            self._static(x, y0, 64)
        for _ in range(int(W * H * 0.012)):
            self.br.dot(rng.uniform(0, W), rng.uniform(y0 + 2, H - 1), 240)
        top, cx = y0 - max(3, int(H * 0.12)), W / 2
        self.br.line(cx, y0, cx, top, 70)
        self.br.line(cx, top + 2, cx - 4, top - 1, 77)
        self.br.line(cx, top + 1, cx + 4, top - 2, 77)
        for x, y in ((cx, y0), (cx, top), (cx - 4, top - 1), (cx + 4, top - 2)):
            if 0 <= x < W and 0 <= y < H:
                self.cb[int(y) >> 2][int(x) >> 1] = SOLID

    def _bracket(self, count):
        return bisect.bisect_right(self.thresh, count)

    def _plot(self, x, y, b):
        x, y = int(x), int(y)
        if 0 <= x < self.W and 0 <= y < self.H:
            row = self.cb[y >> 2]
            if b >= row[x >> 1]:
                row[x >> 1] = b
                self.br.dot(x, y, self.pal[b])
            else:
                self.br.dot(x, y)

    def _edge(self, i):
        p = self.par[i]
        b = self.bk[i]
        x0, y0, x1, y1 = self.nx[p], self.ny[p], self.nx[i], self.ny[i]
        dx, dy = x1 - x0, y1 - y0
        n = int(max(abs(dx), abs(dy))) + 1
        horiz = abs(dx) >= abs(dy)
        for o in OFFSETS[self.wid[b]]:
            ox, oy = (0, o) if horiz else (o, 0)
            for k in range(n + 1):
                t = k / n
                self._plot(x0 + dx * t + ox, y0 + dy * t + oy, b)

    def _add(self, x, y, parent):
        i = len(self.nx)
        self.nx.append(x)
        self.ny.append(y)
        self.par.append(parent)
        self.cnt.append(0)
        self.bk.append(0)
        self.grid.setdefault(self._cell(x, y), []).append(i)
        if parent >= 0:
            self._edge(i)
            p = parent
            while p >= 0:
                self.cnt[p] += 1
                nb = self._bracket(self.cnt[p])
                if nb != self.bk[p]:
                    self.bk[p] = nb
                    if self.par[p] >= 0:
                        self._edge(p)
                p = self.par[p]
        gx, gy = self._cell(x, y)
        for i2 in range(gx - 1, gx + 2):
            for j in range(gy - 1, gy + 2):
                for a in self.agrid.get((i2, j), ()):
                    if self.live[a] and (self.ax[a] - x) ** 2 + (self.ay[a] - y) ** 2 < self.kill2:
                        self.live[a] = False
        return i

    def _crowded(self, x, y):
        gx, gy = self._cell(x, y)
        lim = (0.4 * self.step) ** 2
        for i in range(gx - 1, gx + 2):
            for j in range(gy - 1, gy + 2):
                for n in self.grid.get((i, j), ()):
                    if (self.nx[n] - x) ** 2 + (self.ny[n] - y) ** 2 < lim:
                        return True
        return False

    def iterate(self):
        nx, ny, grid, R, rng = self.nx, self.ny, self.grid, self.R, self.rng
        infl = {}
        for a in self.alive:
            x, y = self.ax[a], self.ay[a]
            gx, gy = int(x // R), int(y // R)
            best, bd = -1, self.R2
            for i in (gx - 1, gx, gx + 1):
                for j in (gy - 1, gy, gy + 1):
                    for n in grid.get((i, j), ()):
                        d = (nx[n] - x) ** 2 + (ny[n] - y) ** 2
                        if d < bd:
                            best, bd = n, d
            if best >= 0:
                d = math.sqrt(bd) or 1e-9
                ux, uy = (x - nx[best]) / d, (y - ny[best]) / d
                e = infl.get(best)
                if e:
                    e[0] += ux
                    e[1] += uy
                else:
                    infl[best] = [ux, uy]
        grew = 0
        W, H = self.W, self.H
        if infl:
            self.lead = None
            for n, (sx, sy) in infl.items():
                m = math.hypot(sx, sy)
                if m < 1e-6:
                    th = rng.uniform(0, 6.283)
                    sx, sy, m = math.cos(th), math.sin(th), 1
                ux, uy = sx / m + rng.uniform(-0.12, 0.12), sy / m + rng.uniform(-0.12, 0.12)
                m = math.hypot(ux, uy) or 1
                x, y = nx[n] + ux / m * self.step, ny[n] + uy / m * self.step
                if 0 <= x < W and 0 <= y < H and not self._crowded(x, y):
                    self._add(x, y, n)
                    grew += 1
        elif self.lead is not None and self.leads < self.lead_limit:
            lx, ly = self.lead
            tip = len(nx) - 1
            x = nx[tip] + (lx + rng.uniform(-0.25, 0.25)) * self.step
            y = ny[tip] + ly * self.step
            if 0 <= x < W and 0 <= y < H:
                self._add(x, y, tip)
                self.leads += 1
                grew = 1
        self.alive = [a for a in self.alive if self.live[a]]
        self.iters += 1
        if not self.alive or not grew or self.iters > 600 or len(nx) > 4000:
            self.done = True

    def grow_leaves(self, rng):
        """Prepare leaf positions on branch tips and the last few nodes behind them,
        in random reveal order."""
        pal = rng.choice(LEAF_PALETTES)
        spots = set()
        for i in range(len(self.nx)):
            if self.cnt[i] == 0 and self.par[i] >= 0:
                j = i
                for _ in range(LEAF_DEPTH):
                    if j < 0:
                        break
                    spots.add(j)
                    j = self.par[j]
        self.leaves = [(self.nx[i], self.ny[i], rng.choice(pal), self.cnt[i] == 0)
                       for i in sorted(spots)]
        rng.shuffle(self.leaves)
        self.leaf_i = 0

    def reveal_leaves(self, k):
        rng = self.rng
        for x, y, col, tip in self.leaves[self.leaf_i:self.leaf_i + k]:
            if tip:
                self.br.disc(x, y, 1.5, col)
            for _ in range(LEAF_DOTS):
                a, r = rng.uniform(0, math.tau), LEAF_SPREAD * rng.random() ** 0.5
                self.br.dot(x + r * math.cos(a), y + r * math.sin(a) * 0.8, col)
        self.leaf_i += k


def step_fn(args):
    rng = random.Random(args.seed)
    fps = max(1.0, args.fps)
    st = {"dim": None, "piece": None, "phase": "grow", "t": 0, "acc": 0.0,
          "slot": rng.randrange(len(ROTATION)), "thr": None}

    def fresh(c):
        st["dim"] = (c.w, c.h)
        st["slot"] += 1
        kind = args.mode if args.mode != "auto" else ROTATION[st["slot"] % len(ROTATION)]
        st["piece"] = Piece(kind, c.w * 2, c.h * 4, rng)
        st["phase"], st["t"], st["acc"] = "grow", 0, 0.0

    def step(c, frame):
        if st["dim"] != (c.w, c.h):
            st["slot"] -= 1
            fresh(c)
        pc = st["piece"]
        kind = pc.kind
        flash = False
        f = 0.0
        if st["phase"] == "grow":
            st["acc"] += ITERS_PER_FRAME[kind] * 20 / fps  # rates are tuned at 20 fps
            while st["acc"] >= 1 and not pc.done:
                st["acc"] -= 1
                pc.iterate()
            if pc.done:
                st["phase"], st["t"] = "hold", 0
                if kind == "tree":
                    pc.grow_leaves(rng)
        elif st["phase"] == "hold":
            st["t"] += 1
            leaf_frames = int(1.5 * fps) if kind == "tree" else 0
            if kind == "tree" and st["t"] <= leaf_frames:
                pc.reveal_leaves(math.ceil(len(pc.leaves) / leaf_frames))
            flash = kind == "lightning" and st["t"] < 8
            if st["t"] > leaf_frames + int((2.0 if kind == "lightning" else 3.0) * fps):
                st["phase"], st["t"] = "fade", 0
                st["thr"] = [[rng.random() for _ in range(pc.br.cols)] for _ in range(pc.br.rows)]
        else:
            st["t"] += 1
            f = st["t"] / max(1, int(2 * fps))
            if f >= 1:
                fresh(c)
                return False

        white = flash and st["t"] % 2 == 0
        if white and term.COLOR:
            for y in range(c.h):
                for x in range(c.w):
                    c.put(x, y, " ", bg=17)
        if flash and not term.COLOR and not white:
            return False
        thr = st["thr"]
        for cy, row in enumerate(pc.br.bits):
            crow = pc.br.colors[cy]
            for cx, b in enumerate(row):
                if not b or (f and thr[cy][cx] < f * f):
                    continue
                col = crow[cx] if crow[cx] is not None else 250
                if white:
                    col = 231
                elif f:
                    col = dim(col, f)
                c.put(cx, cy, chr(0x2800 + b), col)
        return False

    return step


def main():
    parser = term.make_parser(__doc__.splitlines()[0], fps=12)
    parser.add_argument("--mode", choices=["auto"] + MODES, default="auto",
                        help="piece to grow (default: rotate through all)")
    parser.add_argument("--seed", type=int, default=None, help="random seed")
    args = parser.parse_args()
    return term.run(args, step_fn(args), music="spacecol")


if __name__ == "__main__":
    raise SystemExit(main())
