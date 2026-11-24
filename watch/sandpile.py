#!/usr/bin/env python3
"""Abelian sandpile: grains pile up at the centre, 4+ topples to the neighbours, a mandala emerges.

Usage: python3 sandpile.py [--drops N|random] [--palette NAME] [--seed N] [--fps 12] [--frames N]
Only fully stable piles are shown, each revealed by a ripple from the centre, two grains per
cell in half blocks. At the edges it holds, then restarts with a new palette.
"""

META = {'name': 'sandpile',
 'kind': 'watch',
 'blurb': 'An abelian sandpile growing into a mandala',
 'credit': {'type': 'inspired by',
            'who': 'Bak, Tang & Wiesenfeld, Abelian sandpile model (1987)',
            'url': 'https://doi.org/10.1103/PhysRevLett.59.381'}}

import math
import random
import time
from collections import deque

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

from fun import audio, term

# Colours for sites holding 0, 1, 2 and 3 grains.
PALETTES = {
    "ember": [(22, 12, 24), (138, 28, 58), (236, 104, 34), (255, 222, 130)],
    "ocean": [(6, 16, 38), (28, 78, 172), (56, 196, 170), (220, 250, 238)],
    "orchid": [(26, 10, 40), (112, 40, 150), (222, 96, 178), (252, 218, 242)],
    "forest": [(10, 24, 18), (34, 104, 62), (150, 186, 50), (244, 240, 196)],
    "candy": [(36, 18, 52), (236, 82, 140), (96, 204, 236), (255, 240, 160)],
    "gold": [(28, 20, 10), (128, 70, 20), (216, 160, 44), (255, 244, 196)],
    "aurora": [(8, 12, 32), (54, 70, 190), (40, 214, 150), (236, 252, 140)],
    "sunset": [(32, 14, 46), (190, 52, 84), (250, 146, 58), (255, 232, 168)],
}
SHADES = " ░▒▓"  # NO_COLOR: one glyph per grain count, each site two columns wide
BUILD_SECONDS = 60  # time for the pile to grow to its estimated edge size
GROWTH = 1.5  # grains ~ t ** GROWTH; relaxation work ~ grains ** 2, so this spreads it evenly
HOLD_SECONDS = 6
BUDGET = 0.003  # seconds of relaxation per frame at 12 fps; scaled so it is per second constant
REVEAL_SECONDS = 0.3
DENSITY = 2.125  # mean grains per site of a large stable pile
# Largest simulated grid (sites). Relaxation work grows ~ radius ** 4, and this cap keeps
# a full build within ~90 s; bigger terminals show the mandala centred on a plain field.
MAX_W, MAX_H = 224, 112
BELLS = ["pilebell0", "pilebell1", "pilebell2", "pilebell3", "pilebell4"]  # high to low
BELL_GAP = 1.6  # seconds between avalanche bells


class Pile:
    """Grid padded by a one-site sink ring; flat list indexed y * stride + x."""

    def __init__(self, gw, gh, points):
        self.gw, self.gh = gw, gh
        s = self.stride = gw + 2
        self.g = [0] * (s * (gh + 2))
        # queued[i]: i is in the work queue. Sinks stay True so they never topple.
        self.queued = [False] * len(self.g)
        for y in range(gh + 2):
            for x in range(s):
                if x in (0, gw + 1) or y in (0, gh + 1):
                    self.queued[y * s + x] = True
        self.points = [(1 + min(gw - 1, max(0, px)) + (1 + min(gh - 1, max(0, py))) * s)
                       for px, py in points]
        self.work = deque()
        self.grains = 0
        self.topples = 0

    def add(self, n):
        """Drop n grains, spread round-robin over the drop points."""
        g, q, work, pts = self.g, self.queued, self.work, self.points
        m = len(pts)
        base, extra = divmod(n, m)
        for j in range(m):
            i = pts[(self.grains + j) % m]
            g[i] += base + (j < extra)
            if g[i] > 3 and not q[i]:
                q[i] = True
                work.append(i)
        self.grains += n

    def relax(self, deadline):
        """Batch-topple queued sites until stable (True) or past deadline (False)."""
        g, q, s, work = self.g, self.queued, self.stride, self.work
        pop, push, clock = work.popleft, work.append, time.perf_counter
        top = 0
        try:
            while clock() < deadline:
                for _ in range(2048):
                    i = pop()
                    q[i] = False
                    v = g[i]
                    k = v >> 2
                    if not k:
                        continue
                    top += k
                    g[i] = v & 3
                    j = i - 1
                    w = g[j] = g[j] + k
                    if w > 3 and not q[j]:
                        q[j] = True
                        push(j)
                    j = i + 1
                    w = g[j] = g[j] + k
                    if w > 3 and not q[j]:
                        q[j] = True
                        push(j)
                    j = i - s
                    w = g[j] = g[j] + k
                    if w > 3 and not q[j]:
                        q[j] = True
                        push(j)
                    j = i + s
                    w = g[j] = g[j] + k
                    if w > 3 and not q[j]:
                        q[j] = True
                        push(j)
            return False
        except IndexError:  # work queue empty: stable
            return True
        finally:
            self.topples += top

    def lost(self):
        """Grains that fell into the sink ring."""
        g, s, gw, gh = self.g, self.stride, self.gw, self.gh
        return (sum(g[1:1 + gw]) + sum(g[s * (gh + 1) + 1:s * (gh + 1) + 1 + gw])
                + sum(g[y * s] + g[y * s + gw + 1] for y in range(1, gh + 1)))


def layout(count, gw, gh, rng):
    if count == "random":
        count = rng.randint(1, 4)
        return [(rng.randrange(gw), rng.randrange(gh)) for _ in range(count)]
    n = int(count)
    if n <= 1:
        return [(gw // 2, gh // 2)]
    # Circular ring (sites are square) aligned to the axes, and rounded symmetrically about
    # the centre site, so the piles interfere into a mirror-symmetric pattern.
    r = min(gw, gh) * 0.25
    ph = math.pi / 2 + rng.randrange(2) * math.pi / n
    cx, cy = gw // 2, gh // 2
    return [(cx + round(r * math.cos(ph + 2 * math.pi * i / n)),
             cy - round(r * math.sin(ph + 2 * math.pi * i / n))) for i in range(n)]


def step_fn(args):
    rng = random.Random(args.seed)
    fps = max(1.0, args.fps)
    budget = min(0.05, BUDGET * 12 / fps)
    reveal_frames = max(1, round(REVEAL_SECONDS * fps))
    names = sorted(PALETTES)
    st = {"dim": None, "pal": None}

    def pick_palette():
        if args.palette != "random":
            return args.palette
        return rng.choice([n for n in names if n != st["pal"]])

    def restart(c):
        st["dim"] = (c.w, c.h)
        st["pal"] = pick_palette()
        # Colour: one site per column and half a row ('▀' fg = top site, bg = bottom site).
        # NO_COLOR: one site per two columns and one row.
        if term.COLOR:
            gw, gh = min(c.w, MAX_W), min(2 * c.h, MAX_H)
            cps, rps = 1, 0.5
        else:
            gw, gh = min(c.w // 2, MAX_W), min(c.h, MAX_H)
            cps, rps = 2, 1
        gw, gh = max(1, gw), max(2, gh - gh % 2 if term.COLOR else gh)
        pts = layout(args.drops, gw, gh, rng)
        p = st["pile"] = Pile(gw, gh, pts)
        # Grains when the pile should reach an edge: one disc touching the shorter side, or
        # fewer when the drop points sit close to the edges.
        st["est"] = max(60.0, min(DENSITY * math.pi * (min(gw, gh) / 2) ** 2,
                                  sum(DENSITY * math.pi * min(x + 1, gw - x, y + 1, gh - y) ** 2
                                      for x, y in pts)))
        st["edge"] = max(2, min(gw, gh) // 2)
        st["geo"] = (gw, gh, cps, rps, (c.w - gw * cps) // 2, int((c.h - gh * rps) // 2))
        st["reach"] = max(math.hypot(x - gw / 2, y - gh / 2) for x, y in pts)
        st["luts"] = luts(PALETTES[st["pal"]])
        st["shown"] = st["new"] = snapshot(p)
        st["rk"] = None  # ripple frame, or None when no reveal is running
        st["revealed"] = 0  # grains in the state on screen
        st["done"], st["t"], st["hold"], st["bell_t"], st["bell_top"] = False, 0, 0, -1e9, 0

    def luts(cols):
        if term.COLOR:
            cell = [(" ", None, cols[t]) if t == b else ("▀", cols[t], cols[b])
                    for t in range(4) for b in range(4)]
            return cell, (" ", None, cols[0])
        return [(SHADES[v], None, None) for v in range(4)], term.Canvas.BLANK

    def snapshot(p):
        """Full-width screen rows of the pile's current (stable) state."""
        gw, gh, cps, rps, ox, oy = st["geo"]
        cell, pad = st["luts"]
        w, h = st["dim"]
        g, s = p.g, p.stride
        left, right = [pad] * ox, [pad] * (w - ox - gw * cps)
        rows = [[pad] * w for _ in range(h)]
        if term.COLOR:
            for y in range(gh // 2):
                if 0 <= oy + y < h:
                    a = (2 * y + 1) * s + 1
                    b = a + s
                    rows[oy + y] = left + [cell[(g[a + x] << 2) | g[b + x]] for x in range(gw)] + right
        else:
            for y in range(gh):
                if 0 <= oy + y < h:
                    a = (y + 1) * s + 1
                    rows[oy + y] = left + [cell[g[a + x]] for x in range(gw) for _ in (0, 1)] + right
        return rows

    def reveal(p):
        st["new"] = snapshot(p)
        st["rk"] = 0
        st["revealed"] = p.grains
        if p.lost() >= st["edge"] or st["t"] > 4 * BUILD_SECONDS * fps:
            st["done"] = True
        top = p.topples - st["bell_top"]
        if top and (st["done"] or st["t"] - st["bell_t"] >= BELL_GAP * fps):
            # Bigger avalanches ring lower: one step per decade of topples from 100.
            idx = 4 if st["done"] else min(4, max(0, int(math.log10(top)) - 1))
            audio.sfx(BELLS[idx], 0.5)
            st["bell_t"], st["bell_top"] = st["t"], p.topples

    def advance(deadline):
        p = st["pile"]
        if p.work and not p.relax(deadline):
            return
        if st["revealed"] < p.grains:
            if st["rk"] is not None:
                return  # previous reveal still rippling; this state waits
            reveal(p)
        if st["done"]:
            return
        u = st["t"] / (BUILD_SECONDS * fps)
        want = int(st["est"] * u ** GROWTH)
        if want >= p.grains * 1.03 + 1:  # skip steps too small to see
            p.add(want - p.grains)
            p.relax(deadline)

    def ripple_rows():
        """Screen rows with the new state inside a circle growing from the centre."""
        p, new, old = st["pile"], st["new"], st["shown"]
        gw, gh, cps, rps, ox, oy = st["geo"]
        k = st["rk"] + 1
        if k >= reveal_frames:
            st["shown"], st["rk"] = new, None
            return new
        st["rk"] = k
        per = p.grains / len(p.points)
        r = (st["reach"] + 1.2 * math.sqrt(per / (DENSITY * math.pi)) + 2) * k / reveal_frames
        cx, cy = ox + gw * cps / 2, oy + gh * rps / 2
        rows = []
        for y in range(len(new)):
            d = (y + 0.5 - cy) / rps
            if abs(d) >= r:
                rows.append(old[y])
                continue
            hw = math.sqrt(r * r - d * d) * cps
            x0, x1 = max(0, int(cx - hw)), max(0, int(cx + hw) + 1)
            rows.append(old[y][:x0] + new[y][x0:x1] + old[y][x1:])
        return rows

    def step(c, frame):
        if st["dim"] != (c.w, c.h):
            restart(c)
        if not st["done"] or st["rk"] is not None or st["revealed"] < st["pile"].grains:
            st["t"] += 1
            advance(time.perf_counter() + budget)
        else:
            st["hold"] += 1
            if st["hold"] > HOLD_SECONDS * fps:
                restart(c)
        c.cells = list(st["shown"] if st["rk"] is None else ripple_rows())
        return False

    return step


def main():
    parser = term.make_parser(__doc__.splitlines()[0], fps=12)
    parser.add_argument("--drops", default="1",
                        help="number of drop points (symmetric ring), or 'random' (default 1, centre)")
    parser.add_argument("--palette", choices=["random"] + sorted(PALETTES), default="random")
    parser.add_argument("--seed", type=int, default=None, help="random seed")
    args = parser.parse_args()
    if args.drops != "random" and not (args.drops.isdigit() and int(args.drops) >= 1):
        parser.error("--drops must be a positive integer or 'random'")
    return term.run(args, step_fn(args), music="sandpile")


if __name__ == "__main__":
    raise SystemExit(main())
