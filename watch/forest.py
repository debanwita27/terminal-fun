#!/usr/bin/env python3
"""Forest: an endless, slowly drifting forest of braille fractal trees that grow in
real time, sway in the wind and live through the seasons and a day/night cycle.

Trees are a port of the H-tree canvas fractal: each branch is a bezier curve (a bow
when it leans right, an S-curve otherwise) that forks twice (len*0.75, width*0.6,
angle +- a random 10-40 degrees), with a quarter-disc leaf at the tips. As in the
original, every tree has its own bold bark colour and a contrasting leaf colour, thick
limbs are solid strokes, and canopies glow softly (in truecolor terminals).

Usage: python3 forest.py [--fps 12] [--frames N] [--seed N] [--speed 1.0]
                         [--season spring|summer|autumn|winter] [--season-length 60]
                         [--day-length 120] [--start 0.1]
  --speed X          drift speed multiplier (default 1)
  --season NAME      pin one season instead of cycling
  --season-length S  seconds per season (default 60)
  --day-length S     seconds per day (default 120)
  --start P          initial day phase 0..1 (0 sunrise, 0.4 dusk, 0.5 night)
"""

META = {'name': 'forest',
 'kind': 'watch',
 'blurb': 'A drifting braille fractal forest with seasons, day/night and wind',
 'credit': [{'type': 'taken from',
             'who': 'H_TreeFractal by debanwita27',
             'url': 'https://github.com/debanwita27/Canvas_Stuff/tree/main/H_TreeFractal'},
            {'type': 'taken from',
             'who': "Frank's Laboratory, Random Fractal Tree Generator",
             'url': 'https://codepen.io/franksLaboratory/pen/ZEbGoPB'},
            {'type': 'inspired by',
             'who': 'drawille by asciimoo (braille-dot terminal drawing)',
             'url': 'https://github.com/asciimoo/drawille'}]}

import colorsys
import math
import random
from array import array
from bisect import bisect_left
from functools import lru_cache

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

from fun import braille, term
from fun.braille import _BITS, _CHARS

SEASONS = ("spring", "summer", "autumn", "winter")

# (phase, sky top rgb, horizon rgb); phase 1.0 repeats 0.0 so the cycle wraps. The day
# sky is a soft slate blue rather than bright blue so the trees' colours carry, and
# night (where the piece is closest to the original on black) takes over a third.
KEYS = [
    (0.00, (62, 66, 128), (205, 140, 135)),
    (0.07, (36, 54, 100), (104, 112, 158)),
    (0.30, (36, 54, 100), (104, 112, 158)),
    (0.40, (58, 38, 96), (225, 118, 76)),
    (0.50, (4, 5, 14), (14, 15, 36)),
    (0.88, (4, 5, 14), (14, 15, 36)),
    (0.96, (36, 40, 92), (200, 128, 112)),
    (1.00, (62, 66, 128), (205, 140, 135)),
]
SUNSET = 0.46  # day phase at which the sun sets and the moon rises
GROUND = [(62, 120, 46), (40, 100, 36), (120, 88, 40), (200, 205, 222)]

# Leaf hue families per season: (weight, hue lo, hue hi, sat lo, sat hi, val lo, val hi).
# A tree keeps one random position u in each family, so its colour shifts with the
# seasons but stays its own.
LEAF_FAMILIES = (
    ((4, 325, 350, .55, .80, .97, 1.0), (2, 275, 300, .50, .70, .95, 1.0),
     (2, 2, 18, .60, .75, .97, 1.0), (1, 0, 360, .08, .18, .97, 1.0)),
    ((6, 78, 140, .75, 1.0, .85, 1.0), (2, 160, 190, .70, .90, .80, .95)),
    ((6, 12, 48, .85, 1.0, .95, 1.0), (1, 345, 360, .80, .95, .85, 1.0)),
)
FALL_COLORS = {0: ((255, 120, 185), (250, 170, 215), (255, 225, 238), (210, 140, 255)),
               2: ((255, 115, 20), (255, 175, 30), (235, 55, 35), (215, 25, 70), (255, 210, 60))}
SNOW = (238, 243, 255)
# sprite tokens: 4 wood shades, snow, 2 x 8 leaf, then the 4 wood shades again for
# strokes thick enough to turn into solid blocks
WOOD_TOK, SNOW_TOK, LEAF_TOK, THICK_TOK = 0, 4, 5, 21
CONTRAST = 2.1  # min ratio of a tree colour to the horizon, the lightest sky, before haze

DOTS = [bin(i).count("1") for i in range(256)]
# Solid wood cells carry a block flag above the 8 dot bits; flags OR together when
# trees overlap, so every combination maps to a glyph.
FULL, LEFT, RIGHT, TOP, BOTTOM = 1 << 8, 2 << 8, 4 << 8, 8 << 8, 16 << 8


def _block_char(f):
    if f & FULL or (f & LEFT and f & RIGHT) or (f & TOP and f & BOTTOM):
        return "█"
    return "▌" if f & LEFT else "▐" if f & RIGHT else "▀" if f & TOP else "▄"


GLYPH = _CHARS + [_block_char(f << 8) for f in range(1, 32) for _ in range(256)]
SOLID = [g == "█" for g in GLYPH]  # drawn with bg = fg too, so rows join without gaps
WOOD_FLAG = [0] * 256
for _v in range(256):
    WOOD_FLAG[_v] = (FULL if DOTS[_v] >= 5 else LEFT if _v & 0x47 == 0x47 else RIGHT if _v & 0xB8 == 0xB8
                     else TOP if _v & 0x1B == 0x1B else BOTTOM if _v & 0xE4 == 0xE4 else 0)

DT20 = 1 / 20
TAU = 2 * math.pi
GUST_LO, GUST_N = 0.3, 3  # gust ranges over 0.3..1.0; sprites are cached at GUST_N levels
GUST_STEP = 0.7 / (GUST_N - 1)
MAX_SPRITES = 64
# halo blur over cells (cells are about twice as tall as wide, so it is wider than tall)
HALO_K = [(dy, dx, (1.0 if abs(dx) <= 1 else 0.5) * (1.0 if dy == 0 else 0.5))
          for dy in (-1, 0, 1) for dx in (-2, -1, 0, 1, 2)]
HALO_LEVELS = (3, 8, 16, 26, 38)  # blurred leaf-dot sums for halo levels 1..5
HALO_ALPHA = (0.035, 0.07, 0.11, 0.15, 0.19)  # night tint strength per level; daytime 40%


class Layer:
    def __init__(self, f, depth, haze, cw, md, count, amp, rate, skip, nph):
        self.f, self.depth, self.haze = f, depth, haze
        self.cw, self.md, self.count = cw, md, count
        self.amp, self.rate, self.skip = amp, rate, skip
        self.nph = nph


# parallax, fork levels, haze/8, chunk px, min trunk gap px, tree attempts, sway rad,
# growth nodes/s, chance a chunk is empty, cached sway phases. The near layer holds
# one hero tree per chunk, a little under a screen width apart at 120 columns.
LAYERS = [
    Layer(0.25, 6, 3, 200, 40, 4, 0.014, 60, 0.1, 4),
    Layer(0.55, 7, 1, 230, 70, 2, 0.018, 90, 0.2, 6),
    Layer(1.00, 8, 0, 190, 60, 1, 0.020, 110, 0.1, 8),
]


def lerp(a, b, t):
    return tuple(x + (y - x) * t for x, y in zip(a, b))


def mix(a, b, t):
    return tuple(int(x + (y - x) * t) for x, y in zip(a, b))


def hsv(h, s, v):
    return tuple(round(c * 255) for c in colorsys.hsv_to_rgb(h / 360 % 1.0, min(1.0, s), min(1.0, v)))


def lum(rgb):
    """WCAG relative luminance."""
    out = 0.0
    for k, v in zip((0.2126, 0.7152, 0.0722), rgb):
        v /= 255
        out += k * (v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4)
    return out


def tree_colours(rng):
    """(bark rgb, twig rgb, leaf palettes for spring/summer/autumn). Bark is an earthy
    brown or a bold hue far from the leaf hues; each leaf palette is five vivid shades
    of one hue."""
    pals, hues = [], []
    for fams in LEAF_FAMILIES:
        _, h0, h1, s0, s1, v0, v1 = rng.choices(fams, weights=[f[0] for f in fams])[0]
        u = rng.random()
        h, sat, v = h0 + (h1 - h0) * u, s0 + (s1 - s0) * u, v0 + (v1 - v0) * rng.random()
        hues.append(h)
        pals.append((hsv(h, sat, v), hsv(h + 12, sat * 0.85, 1.0), hsv(h - 10, sat, v * 0.85),
                     hsv(h + 5, sat * 0.7, 1.0), hsv(h - 4, sat * 1.1, v * 0.95)))
    kind = rng.random()
    if kind < 0.3:
        bark = hsv(rng.uniform(18, 32), rng.uniform(.55, .75), rng.uniform(.45, .62))
    else:
        if kind < 0.8:  # the hue farthest from all three seasons' leaves
            h = max(range(0, 360, 5), key=lambda c: min(abs((c - x + 180) % 360 - 180) for x in hues))
            h += rng.uniform(-35, 35)
        else:  # opposite one season only: striking then, a near match in another
            h = rng.choice(hues) + 180 + rng.uniform(-30, 30)
        bark = hsv(h, rng.uniform(.6, .9), rng.uniform(.7, .95))
    twig = mix(bark, (255, 255, 255), 0.2)
    return bark, twig, tuple(pals)


def c256(rgb):
    r, g, b = (max(0, min(255, v)) for v in rgb)
    if max(r, g, b) - min(r, g, b) < 10 and 20 < r < 245:
        return 232 + max(0, min(23, round((r - 8) / 10)))
    r, g, b = (bisect_left(_CUBE_EDGES, v) for v in (r, g, b))
    return 16 + 36 * r + 6 * g + b


_CUBE_EDGES = (47, 114, 154, 194, 234)  # midpoints between 256-colour cube levels


@lru_cache(maxsize=4096)
def shade(rgb, haze, nq, fog, ref):
    """rgb tuple lifted a touch toward white at night (nq/8), pushed away from the sky
    colour ref until they differ by CONTRAST (lighter on a dark sky, raising value before
    giving up saturation; darker on a light one), then faded toward fog by haze/8."""
    k = nq / 8 * 0.06
    r, g, b = (v + (255 - v) * k for v in rgb)
    lr = lum(ref) + 0.05
    darken = lum((r, g, b)) + 0.05 < lr and lr >= 0.3
    for _ in range(40):
        lc = lum((r, g, b)) + 0.05
        if lc >= lr * CONTRAST or lr >= lc * CONTRAST:
            break
        if darken:
            r, g, b = r * 0.92, g * 0.92, b * 0.92
        else:
            hh, ss, vv = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
            if vv < 0.99:
                vv = min(1.0, vv * 1.06 + 0.02)
            else:
                ss *= 0.92
            r, g, b = (c * 255 for c in colorsys.hsv_to_rgb(hh, ss, vv))
    h = haze / 8
    return (int(r + (fog[0] - r) * h), int(g + (fog[1] - g) * h), int(b + (fog[2] - b) * h))


def sky_at(p):
    for (p0, t0, h0), (p1, t1, h1) in zip(KEYS, KEYS[1:]):
        if p0 <= p <= p1:
            u = (p - p0) / (p1 - p0)
            return lerp(t0, t1, u), lerp(h0, h1, u)
    return KEYS[0][1], KEYS[0][2]


def night_amount(p):
    if p < 0.34 or p > 0.98:
        return 0.0
    if p < 0.5:
        return (p - 0.34) / 0.16
    return 1.0 if p < 0.88 else (0.98 - p) / 0.1


def leaf_density(idx, u):
    if idx == 0:
        return min(0.95, u * 1.6)
    if idx == 1:
        return 1.0
    if idx == 2:
        return 1 - 0.85 * u ** 1.2
    return max(0.0, 0.15 * (1 - u / 0.2))


def fall_weight(idx, u):
    """Falling-leaf/petal and snow particle weights (0..1)."""
    edge = min(1.0, u * 8) * min(1.0, (1 - u) * 8)
    if idx == 2:
        return edge, 0.0
    if idx == 3:
        return 0.0, min(1.0, u * 8) * min(1.0, (1 - u) * 6)
    if idx == 0:
        return 0.25 * edge, 0.0
    return 0.0, 0.0


@lru_cache(maxsize=None)
def wedge_stamps(r2, rot):
    """The original's leaf, ctx.arc(0, -len, r, 0, PI/2) filled: a quarter disc hung off
    the tip on the branch's right-hand, rootward side, here with the corner by the tip
    cut away so it reads as a petal. r2 is twice the radius in dots, rot the branch
    angle in 16ths of a turn. Per sub-cell position of the tip dot (x & 1 | (y & 3) << 1):
    the (cell dx, cell dy, bits) cells it covers."""
    r = r2 / 2
    a = rot * TAU / 16
    ca, sa = math.cos(a), math.sin(a)
    offs = set()
    n = int(r * 2) + 1
    for i in range(n + 1):
        for j in range(n + 1):
            u, v = i / 2, j / 2
            if u * u + v * v <= r * r and u + v >= 0.4 * r:
                offs.add((round(u * ca - v * sa), round(u * sa + v * ca)))
    out = []
    for sub in range(8):
        cells = {}
        for dx, dy in offs:
            x, y = (sub & 1) + dx, (sub >> 1) + dy
            key = (x >> 1, y >> 2)
            cells[key] = cells.get(key, 0) | _BITS[y & 3][x & 1]
        out.append(tuple((cx, cy, bt) for (cx, cy), bt in cells.items()))
    return tuple(out)


class Tree:
    """Branch structure is built once, breadth-first. Every pose is rasterised into a
    packed sprite: growing trees get a fresh one each frame (relative angles, so the
    wind bends every level), finished trees reuse cached ones at the nearest sway phase."""

    def __init__(self, rng, wx, by, layer, target, delay):
        self.wx, self.by, self.layer, self.delay = wx, by, layer, delay
        lay = LAYERS[layer]
        # one draw, so the colours get their own stream and the structure's is unchanged
        crng = random.Random(rng.random())
        bark, twig, self.leafpal = tree_colours(crng)
        self.wood_rgb = tuple(mix(bark, twig, b / 3) for b in range(4))
        self.cmkey = None
        par, dep, rel, lfrac = [-1], [0], [rng.uniform(-0.06, 0.06)], [1.0]
        level = prev = [0]
        for d in range(lay.depth):
            prev, nxt = level, []
            for i in level:
                curve = math.radians(rng.uniform(10, 40))
                for sgn in (-1, 1):
                    par.append(i)
                    dep.append(d + 1)
                    rel.append(sgn * curve)
                    lfrac.append(lfrac[i] * 0.75)
                    nxt.append(len(par) - 1)
            level = nxt
        # leaves on the last two fork levels fill the crown, not just its rim
        self.par, self.dep, self.rel, self.tips = par, dep, rel, prev + level
        n = len(par)

        # unit-length rest pose, to fit the tree to the target height
        ang, ex, ey = [0.0] * n, [0.0] * n, [0.0] * n
        for i in range(n):
            p = par[i]
            a = (ang[p] if p >= 0 else 0.0) + rel[i]
            ang[i] = a
            ex[i] = (ex[p] if p >= 0 else 0.0) + math.sin(a) * lfrac[i]
            ey[i] = (ey[p] if p >= 0 else 0.0) - math.cos(a) * lfrac[i]
        scale = target / max(0.5, -min(ey))
        self.len = [f * scale for f in lfrac]
        # the original's bezier bow and leaf radius are both 10px on a ~110px trunk
        self.bow = 0.09 * scale
        self.leafr2 = max(2, min(9, round(0.18 * scale)))
        w0 = crng.uniform(0.12, 0.2) * scale
        self.wid = [w0 * 0.6 ** d for d in dep]
        self.reach = max(abs(x) for x in ex) * scale + self.bow + self.leafr2 + w0 + 4
        # wood shade per branch: trunk 0 .. twig 3
        self.shadei = [min(3, d * 4 // (lay.depth + 1)) for d in dep]
        self.n = n
        self.ang, self.ex, self.ey = [0.0] * n, [0.0] * n, [0.0] * n
        nt = len(self.tips)
        self.lthr = [rng.random() for _ in range(nt)]
        self.kthr = [rng.random() for _ in range(nt)]
        self.lcol = [rng.randrange(8) for _ in range(nt)]
        self.ljit = [(rng.randint(-1, 1), rng.randint(-1, 1)) for _ in range(nt)]
        self.sthr = [rng.random() for _ in range(n)]
        self.phase = rng.uniform(0, 6.28)
        # Fraction of the screen width the trunk must drift past before growth starts,
        # so growth happens on screen. Derived from phase to leave the rng stream alone.
        self.enter = 0.5 + 0.4 * (self.phase * 7.31 % 1.0)
        self.start = None
        self.shown = 0.0
        self.leafprog = 0.0

        # Threshold ranks: "thr < amt" picks the same set as "rank < bisect_left(sorted thr, amt)".
        self.lsort, self.lrank = self._ranks(self.lthr)
        self.ksort, self.krank = self._ranks(self.kthr)
        elig = [i for i in range(1, n) if dep[i] > 1]
        self.sorder = sorted(elig, key=self.sthr.__getitem__)
        self.ssort = [self.sthr[i] for i in self.sorder]
        self.target = target
        self.pad = int(self.reach / 2) + 4
        self.up = int((target + self.leafr2 + self.bow + 8) / 4) + 1
        self.cache, self.wood, self.sig = {}, {}, None
        nt = len(self.lthr)
        self.steps = (max(1, nt // 16), max(1, nt // 8), max(1, len(self.ssort) // 8))
        self.exact, self.counts_cur, self.still = None, None, 0

    @staticmethod
    def _ranks(thr):
        order = sorted(range(len(thr)), key=thr.__getitem__)
        rank = [0] * len(thr)
        for r, k in enumerate(order):
            rank[k] = r
        return [thr[k] for k in order], rank

    def _wood(self, b, sx, by, sway, n, shown):
        """Rasterise branches 0..n-1 (the last one shown - int(shown) grown) into b with
        wood tokens. Each branch is the original's cubic bezier in its own frame:
        controls (bow, -L/2) and (+-bow, -L/2), a bow when it leans right and an S-curve
        otherwise. Strokes wider than a dot are filled with spans across their width."""
        par, dep, rel, ln, wid, shadei = self.par, self.dep, self.rel, self.len, self.wid, self.shadei
        ang, ex, ey = self.ang, self.ex, self.ey
        sin, cos = math.sin, math.cos
        W, H, bits, colors, BITS = b.w, b.h, b.bits, b.colors, _BITS
        bow0 = self.bow
        for i in range(n):
            p = par[i]
            if p < 0:
                x0, y0, a0 = sx, by, 0.0
            else:
                x0, y0, a0 = ex[p], ey[p], ang[p]
            a = a0 + rel[i] + sway[dep[i]]
            ang[i] = a
            L = ln[i]
            bow = bow0
            if i + 1 > shown:
                L *= shown - i
                bow *= shown - i
            sa, ca = sin(a), cos(a)
            ex[i], ey[i] = x0 + sa * L, y0 - ca * L
            w = wid[i]
            tok = shadei[i] + (THICK_TOK if w >= 1.5 else 0)
            c2 = bow if a > 0 else -bow
            segs = 6 if L > 20 else 4 if L > 6 else 2
            px, py = x0, y0
            for s in range(1, segs + 1):
                t = s / segs
                u = 1 - t
                lx = 3 * u * u * t * bow + 3 * u * t * t * c2
                lu = L * (1.5 * u * u * t + 1.5 * u * t * t + t * t * t)
                qx, qy = x0 + lx * ca + lu * sa, y0 + lx * sa - lu * ca
                dx, dy = qx - px, qy - py
                steps = int(max(abs(dx), abs(dy))) + 1
                if w < 1.5:
                    for k in range(steps + 1):
                        f = k / steps
                        x, y = int(px + dx * f), int(py + dy * f)
                        if 0 <= x < W and 0 <= y < H:
                            bits[y >> 2][x >> 1] |= BITS[y & 3][x & 1]
                            colors[y >> 2][x >> 1] = tok
                else:
                    seg = math.hypot(dx, dy) or 1.0
                    vert = abs(dy) >= abs(dx)
                    hs = min(w, w / 2 * seg / max(abs(dy) if vert else abs(dx), 0.01))
                    for k in range(steps + 1):
                        f = k / steps
                        cx, cy = px + dx * f, py + dy * f
                        if vert:
                            y = int(cy)
                            if 0 <= y < H:
                                brow, crow, bt = bits[y >> 2], colors[y >> 2], BITS[y & 3]
                                for x in range(max(0, int(cx - hs + 0.5)), min(W, int(cx + hs + 0.5))):
                                    brow[x >> 1] |= bt[x & 1]
                                    crow[x >> 1] = tok
                        else:
                            x = int(cx)
                            if 0 <= x < W:
                                for y in range(max(0, int(cy - hs + 0.5)), min(H, int(cy + hs + 0.5))):
                                    bits[y >> 2][x >> 1] |= BITS[y & 3][x & 1]
                                    colors[y >> 2][x >> 1] = tok
                px, py = qx, qy

    def _canvas(self):
        return braille.Braille(2 * self.pad + 2, self.up + 3)

    def grow_sprite(self, sway, par):
        """Packed wood-only sprite of the tree as grown so far."""
        n = min(self.n, int(self.shown) + 1)
        b = self._canvas()
        self._wood(b, 2 * self.pad + par, self.up * 4 + (int(self.by) & 3), sway, n, self.shown)
        return self._pack(b, self.pad, self.up, False)

    def counts(self, leaf_amt, kmix, snow_amt):
        """(leaf, palette-mix, snow) counts that select what a sprite contains. During a
        seasonal ramp the adopted counts lag the exact ones by a few steps so cached
        sprites stay valid; once the exact counts hold still they are adopted outright."""
        exact = (bisect_left(self.lsort, leaf_amt), bisect_left(self.ksort, kmix),
                 bisect_left(self.ssort, snow_amt))
        if exact != self.exact:
            self.exact, self.still = exact, 0
        else:
            self.still += 1
        cur = self.counts_cur
        if exact != cur and (cur is None or self.still >= 12
                             or any(abs(x - y) >= st for x, y, st in zip(exact, cur, self.steps))):
            self.counts_cur = exact
        return self.counts_cur

    def sprite(self, lay, gi, q, par, sig):
        """Cached rendering of the finished tree at sway phase q, gust level gi and
        sub-cell x parity par. Cell colours are tokens: WOOD_TOK or THICK_TOK + shade (0..3),
        SNOW_TOK, LEAF_TOK + 8 * palette + index. See _pack_grid for the layout."""
        key = (gi, q, par)
        sp = self.cache.get(key)
        if sp is not None:
            return sp
        kinds, lc, kc, sc = sig
        pad, up = self.pad, self.up
        wood = self.wood.get(key)
        if wood is None:
            if len(self.wood) >= MAX_SPRITES:
                self.wood.clear()
            theta = q * TAU / lay.nph
            g = GUST_LO + gi * GUST_STEP
            depth = lay.depth
            sway = [lay.amp * g * (0.25 + d / depth) * math.sin(theta + d * 0.55)
                    for d in range(depth + 1)]
            b = self._canvas()
            self._wood(b, 2 * pad + par, up * 4 + (int(self.by) & 3), sway, self.n, self.n)
            rot = array('b', [int(a % TAU / TAU * 16 + 0.5) % 16 for a in self.ang])
            wood = self.wood[key] = (b.bits, b.colors, array('h', map(int, self.ex)),
                                     array('h', map(int, self.ey)), rot)
        wbits, wcols, exi, eyi, rot = wood
        if not lc and not sc:
            sp = self.cache[key] = self._pack_grid(wbits, wcols, pad, up, False)
            return sp
        bits = [row[:] for row in wbits]
        colors = [row[:] for row in wcols]
        for i in self.sorder[:sc]:
            x, y = exi[i], eyi[i] - 1
            if 0 <= y:
                bits[y >> 2][x >> 1] |= _BITS[y & 3][x & 1]
                colors[y >> 2][x >> 1] = SNOW_TOK
        if lc:
            pals = [self.leafpal[min(k, 2)] for k in kinds]
            lrank, krank, lcol, ljit, r2 = self.lrank, self.krank, self.lcol, self.ljit, self.leafr2
            nrows, ncols = len(bits), len(bits[0])
            for k, i in enumerate(self.tips):
                if lrank[k] < lc:
                    w = 0 if krank[k] < kc else 1
                    tok = LEAF_TOK + w * 8 + lcol[k] % len(pals[w])
                    x, y = exi[i] + ljit[k][0], eyi[i] + ljit[k][1]
                    bx, by = x >> 1, y >> 2
                    for dcx, dcy, bt in wedge_stamps(r2, rot[i])[(x & 1) | (y & 3) << 1]:
                        cy, cx = by + dcy, bx + dcx
                        if 0 <= cy < nrows and 0 <= cx < ncols:
                            bits[cy][cx] |= bt
                            colors[cy][cx] = tok
        sp = self.cache[key] = self._pack_grid(bits, colors, pad, up, True)
        return sp

    @staticmethod
    def _pack(b, pad, up, halo):
        return Tree._pack_grid(b.bits, b.colors, pad, up, halo)

    @staticmethod
    def _pack_grid(bits, colors, pad, up, halo):
        """(rows, lo, hi, base row, halo rows). rows: per row (row, cell x, dot bits plus
        any block flag, token) tuples, x relative to the base cell. Thick-stroke cells whose
        dots (nearly) fill a whole cell, column or half become solid blocks. halo rows: (row, cell x,
        level 1..5) from a blur of the leaf dots, for the glow around canopies."""
        rows, lo, hi = [], len(bits[0]), 0
        acc = {} if halo else None
        for cy, row in enumerate(bits):
            xs = [x for x, v in enumerate(row) if v]
            if xs:
                crow = colors[cy]
                vals = []
                for x in xs:
                    v, tk = row[x], crow[x]
                    if tk >= THICK_TOK:
                        v |= WOOD_FLAG[v]
                    elif acc is not None and tk >= LEAF_TOK:
                        dn = DOTS[v]
                        for dy, dx, kw in HALO_K:
                            kk = (cy + dy, x + dx)
                            acc[kk] = acc.get(kk, 0.0) + dn * kw
                    vals.append(v)
                rows.append((cy, tuple([x - pad for x in xs]), tuple(vals),
                             tuple([crow[x] for x in xs])))
                lo, hi = min(lo, xs[0]), max(hi, xs[-1])
        hrows = []
        if acc:
            byrow = {}
            for (cy, x), s in acc.items():
                lv = bisect_left(HALO_LEVELS, s + 1e-9)
                if lv:
                    byrow.setdefault(cy, []).append((x - pad, lv))
            for cy in sorted(byrow):
                xl = sorted(byrow[cy])
                hrows.append((cy, tuple([x for x, _ in xl]), tuple([lv for _, lv in xl])))
        return rows, lo - pad, hi - pad, up, hrows


def blit_sprite(sp, layer, cell_x, cell_y, cm, gl=None, glow=None):
    """OR a Tree.sprite into a braille layer; the tree's base cell is (cell_x, cell_y).
    With glow (a rows x cols grid shared by all layers, written in draw order) the
    sprite's halo cells record gl[level], a (colour, strength) pair."""
    rows, lo, hi, up, halo = sp
    bits, colors, nrows, ncols = layer.bits, layer.colors, layer.rows, layer.cols
    oy = cell_y - up
    if cell_x + lo >= 0 and cell_x + hi < ncols:
        for cy, cxs, bts, tks in rows:
            y = cy + oy
            if 0 <= y < nrows:
                br, cr = bits[y], colors[y]
                for x, bt, tk in zip(cxs, bts, tks):
                    x += cell_x
                    br[x] |= bt
                    cr[x] = cm[tk]
    else:
        for cy, cxs, bts, tks in rows:
            y = cy + oy
            if 0 <= y < nrows:
                br, cr = bits[y], colors[y]
                for x, bt, tk in zip(cxs, bts, tks):
                    x += cell_x
                    if 0 <= x < ncols:
                        br[x] |= bt
                        cr[x] = cm[tk]
    if glow is not None and halo:
        for cy, cxs, lvs in halo:
            y = cy + oy
            if 0 <= y < nrows:
                gr = glow[y]
                for x, lv in zip(cxs, lvs):
                    x += cell_x
                    if 0 <= x < ncols:
                        gr[x] = gl[lv]


def blit_layer(b, canvas):
    """Draw a tree layer's non-empty cells onto the canvas, keeping each cell's bg;
    block-flagged cells become block glyphs."""
    cells = canvas.cells
    for cy, row in enumerate(b.bits):
        if any(row):
            colors, crow = b.colors[cy], cells[cy]
            for cx, v in enumerate(row):
                if v:
                    col = colors[cx]
                    crow[cx] = ("█", col, col) if SOLID[v] else (GLYPH[v], col, crow[cx][2])


class World:
    def __init__(self, seed, w, h, first_delay):
        self.seed, self.w, self.h = seed, w, h
        self.first_delay = first_delay
        self.gr = max(1, h // 5)
        self.gy = max(0, h - self.gr)
        self.chunks = [dict() for _ in LAYERS]
        self.hp = h * 4

    def bases(self):
        gy4 = self.gy * 4
        # (base px, base band px, target height range px) per layer. Every trunk is
        # rooted on the last pixel row above the ground line so none overlaps the grass.
        # Hero trees are 60-82% of the screen tall, so the tallest crowns leave the top.
        root = max(0, gy4 - 1)
        sky = max(8, gy4)
        far = (root, 0, (0.2 * sky, 0.32 * sky))
        mid = (root, 0, (0.36 * sky, 0.5 * sky))
        near = (root, 0, (0.6 * self.hp, 0.82 * self.hp))
        return far, mid, near

    def make_chunk(self, li, cx):
        lay = LAYERS[li]
        rng = random.Random(hash((self.seed, li, cx)))
        if rng.random() < lay.skip:
            return []
        base, band, (t0, t1) = self.bases()[li]
        xs = []
        for _ in range(lay.count * 4):
            if len(xs) >= lay.count:
                break
            x = cx * lay.cw + rng.uniform(lay.md / 2, max(lay.md / 2 + 1, lay.cw - lay.md / 2))
            if all(abs(x - o) >= lay.md for o in xs):
                xs.append(x)
        trees = []
        for x in sorted(xs):
            by = min(self.hp - 1, base + rng.uniform(0, band))
            target = max(6.0, rng.uniform(t0, t1))
            delay = rng.uniform(0, 8) if self.first_delay else 0.2
            trees.append(Tree(rng, x, by, li, target, delay))
        return trees

    def visible(self, li, cam):
        lay = LAYERS[li]
        off = cam * lay.f
        margin = 200
        c0 = math.floor((off - margin) / lay.cw)
        c1 = math.floor((off + self.w * 2 + margin) / lay.cw)
        d = self.chunks[li]
        for k in [k for k in d if k < c0 or k > c1]:
            del d[k]
        out = []
        for cx in range(c0, c1 + 1):
            if cx not in d:
                d[cx] = self.make_chunk(li, cx)
            out.extend(d[cx])
        return out, off


def ground_rgb(sp, n):
    idx, u = int(sp) % 4, sp - int(sp)
    t = max(0.0, (u - 0.85) / 0.15)
    t = t * t * (3 - 2 * t)
    g = lerp(GROUND[idx], GROUND[(idx + 1) % 4], t)
    k = n * 0.7
    return g[0] * (1 - k), g[1] * (1 - k * 0.95), g[2] * (1 - k * 0.6)


def main():
    parser = term.make_parser(__doc__.splitlines()[0], fps=12)
    parser.add_argument("--seed", type=int, default=None, help="world seed (default random)")
    parser.add_argument("--speed", type=float, default=1.0, help="drift speed multiplier")
    parser.add_argument("--season", choices=SEASONS, default=None, help="pin one season")
    parser.add_argument("--season-length", type=float, default=60, help="seconds per season")
    parser.add_argument("--day-length", type=float, default=120, help="seconds per day")
    parser.add_argument("--start", type=float, default=0.1, help="initial day phase 0..1")
    args = parser.parse_args()
    seed = args.seed if args.seed is not None else random.randrange(2 ** 31)
    fps = max(1.0, args.fps)
    dt = 1 / fps
    season_len = max(1.0, args.season_length)
    day_len = max(1.0, args.day_length)
    prng = random.Random(seed + 7)
    s = {"key": None}

    def reset(w, h):
        s.update(key=(w, h), world=World(seed, w, h, True), parts=[], flies=[],
                 acc_leaf=0.0, acc_snow=0.0, prefilled=False,
                 layers=[braille.Braille(w, h) for _ in range(3)],
                 top=braille.Braille(w, h),
                 stars=[(prng.randrange(w), prng.randrange(max(1, int(h * 0.6))),
                         prng.random(), prng.random()) for _ in range(w * h // 45)])
        hp = h * 4
        s["flies"] = [[prng.uniform(0, w * 2), prng.uniform(hp * 0.45, hp - 2),
                       prng.uniform(-3, 3), prng.uniform(-2, 2), prng.uniform(0, 6.28),
                       prng.uniform(1.5, 4)] for _ in range(max(2, w // 7))]

    def step(c, frame):
        w, h = c.w, c.h
        if s["key"] != (w, h):
            reset(w, h)
        world = s["world"]
        gy, gr, hp, wp = world.gy, world.gr, h * 4, w * 2
        t = frame * dt
        cam = t * 5.0 * args.speed

        if args.season:
            sp = SEASONS.index(args.season) + 0.55
        else:
            sp = (t / season_len) % 4
        sidx, su = int(sp) % 4, sp - int(sp)
        dens = leaf_density(sidx, su)
        kmix = su * 4
        kinds = (sidx, (sidx - 1) % 4)
        leaf_w, snow_w = fall_weight(sidx, su)
        snow_amt = min(1.0, su * 5) if sidx == 3 else max(0.0, 1 - su * 6) if sidx == 0 else 0.0

        p = (args.start + t / day_len) % 1.0
        top, hor = sky_at(p)
        n = night_amount(p)
        nq = round(n * 8)
        # quantised so shade()'s cache and the per-tree colour maps stay warm
        fog = tuple(int(v) // 24 * 24 for v in hor)
        fog = tuple(int(v * (0.75 - nq / 20)) for v in fog)
        ref = tuple(int(v) // 16 * 16 for v in hor)

        span = max(1, gy - 1)
        rowbg = [mix(top, hor, min(1.0, y / span) ** 1.3) for y in range(gy + 1)]
        if term.TRUECOLOR:
            key = (rowbg[0], rowbg[-1], gy, w)
            if s.get("skykey") != key:
                s["skykey"], s["sky"] = key, [((" ", None, bg),) * w for bg in rowbg]
            sky = s["sky"]
        else:
            sky = term.sky_rows(top, hor, max(1, gy + 1), w, span=gy - 1)
        for y in range(h):
            c.cells[y] = list(sky[min(y, gy)])

        for i, (x, y, th, ph) in enumerate(s["stars"]):
            if n > th and y < gy:
                tw = (frame // 6 + i) % 3
                c.put(x, y, "*" if tw == 0 and th < 0.4 else ".", (231, 250, 245)[tw])

        horizon = max(2, int(gy * 0.9))
        if p < SUNSET:
            u, body, col = p / SUNSET, ["O"] if h < 14 or w < 20 else [" ▄█▄ ", "█████", " ▀█▀ "], None
        else:
            u, body, col = (p - SUNSET) / (1 - SUNSET), ["O"] if h < 14 or w < 20 else ["▄██▄", "▀██▀"], 254
        sxp, alt = 2 + u * (w - 5), math.sin(math.pi * u)
        syp = horizon - alt * (horizon - 2)
        if col is None:
            col = 226 if alt > 0.5 else 208 if alt > 0.2 else 196
        for r, ln in enumerate(body):
            for k, ch in enumerate(ln):
                c.put(int(sxp) + k - len(ln) // 2, int(syp) + r - len(body) // 2, ch, col)

        grgb = ground_rgb(sp, n)
        gc = (lambda v: tuple(int(x) for x in v)) if term.TRUECOLOR else c256
        gcols = [gc(tuple(v * (1 - 0.3 * r / max(1, gr)) for v in grgb)) for r in range(gr)]
        tuft = gc(tuple(v * 0.62 for v in grgb)) if sidx != 3 or su < 0.15 else gc((150, 165, 195))
        rowbg = (rowbg + gcols[1:] + [gcols[-1]] * h)[:h]
        for r in range(gr):
            if 0 <= gy + r < h:
                c.cells[gy + r] = [(" ", None, gcols[r])] * w
        if 0 <= gy < h:
            c.cells[gy] = [("▄", gcols[0], cell[2]) for cell in sky[min(gy, len(sky) - 1)]]
        scroll = int(cam)
        sd = seed & 0xffff
        for r in range(1, gr):
            f = 0.5 + 0.5 * r / max(1, gr - 1)
            off = int(scroll * f / 2)
            for x in range(w):
                hv = ((x + off) * 73856093 ^ r * 19349663 ^ sd * 83492791) & 0xffff
                if hv % 9 == 0 and (sidx != 3 or hv & 16):
                    c.put(x, gy + r, ",'\"^;"[(hv >> 5) % 5], tuft)

        for b in s["layers"]:
            b.clear()
        top_b = s["top"]
        top_b.clear()
        # halo around canopies, the terminal stand-in for the original's soft white shadow
        glow = [[None] * w for _ in range(h)] if term.TRUECOLOR and term.COLOR else None
        gscale = 0.4 + 0.6 * nq / 8

        for li, lay in enumerate(LAYERS):
            b = s["layers"][li]
            trees, off = world.visible(li, cam)
            haze = lay.haze
            snow_col = shade(SNOW, haze // 2, nq, fog, ref)
            gust = 0.65 + 0.35 * math.sin(t * 0.23 + 1.3)
            gi = round((gust - GUST_LO) / GUST_STEP)
            for tr in sorted(trees, key=lambda q: q.by):
                sx = int(round(tr.wx - off))
                if not -tr.reach <= sx <= wp + tr.reach:
                    continue
                if tr.start is None:
                    # trees on the opening screen grow at once; later ones wait to be in view
                    if not (sx <= wp * tr.enter or (t < 1.0 and sx <= wp)):
                        continue
                    tr.start = t + tr.delay
                if t < tr.start:
                    continue
                if tr.shown < tr.n:
                    tr.shown = min(tr.n, tr.shown + lay.rate * dt)
                elif tr.leafprog < 1:
                    tr.leafprog = min(1.0, tr.leafprog + dt / 2.5)
                ckey = (nq, fog, ref, kinds)
                if tr.cmkey != ckey:
                    tr.cmkey = ckey
                    wood = [shade(v, haze, nq, fog, ref) for v in tr.wood_rgb]
                    cm = tr.cm = wood + [snow_col] + [None] * 16 + wood
                    for wi, k in enumerate(kinds):
                        for j, cc in enumerate(tr.leafpal[min(k, 2)]):
                            cm[LEAF_TOK + wi * 8 + j] = shade(cc, haze, nq, fog, ref)
                    gcol = mix(tr.leafpal[min(kinds[0], 2)][0], (255, 255, 255), 0.55)
                    fade = gscale * (1 - haze / 5)
                    tr.gl = [None] + [(gcol, a * fade) for a in HALO_ALPHA]
                ph = tr.phase + tr.wx * 0.012
                if tr.shown < tr.n:
                    depth = lay.depth
                    sway = [lay.amp * gust * (0.25 + d / depth) * math.sin(t * 1.4 + d * 0.55 + ph)
                            for d in range(depth + 1)]
                    blit_sprite(tr.grow_sprite(sway, sx & 1), b, sx >> 1, int(tr.by) >> 2, tr.cm)
                    continue
                sig = (kinds, *tr.counts(dens * tr.leafprog, kmix, snow_amt))
                if sig != tr.sig:
                    tr.sig = sig
                    tr.cache.clear()
                q = int((t * 1.4 + ph) % TAU / TAU * lay.nph + 0.5) % lay.nph
                blit_sprite(tr.sprite(lay, gi, q, sx & 1, sig), b, sx >> 1, int(tr.by) >> 2,
                            tr.cm, tr.gl, glow)

        # falling leaves, petals and snow
        parts = s["parts"]
        cap_leaf = max(4, w // 3)
        cap_snow = max(6, w * h // 25)
        wind = 3 + 2 * math.sin(t * 0.3)
        if not s["prefilled"]:
            s["prefilled"] = True
            for _ in range(int(cap_leaf * leaf_w)):
                parts.append([prng.uniform(0, wp), prng.uniform(0, hp * 0.9), 0, prng.uniform(5, 9),
                              0, prng.uniform(0, 6.28), prng.choice(FALL_COLORS.get(sidx, FALL_COLORS[2]))])
            for _ in range(int(cap_snow * snow_w)):
                parts.append([prng.uniform(0, wp), prng.uniform(0, hp * 0.9), 0, prng.uniform(4, 8),
                              1, prng.uniform(0, 6.28), SNOW])
        nl = sum(1 for q in parts if q[4] == 0)
        ns = len(parts) - nl
        s["acc_leaf"] += (cap_leaf * leaf_w / 20) * dt * 3 if nl < cap_leaf * leaf_w else 0
        s["acc_snow"] += (cap_snow * snow_w / 20) * dt * 3 if ns < cap_snow * snow_w else 0
        while s["acc_leaf"] >= 1:
            s["acc_leaf"] -= 1
            parts.append([prng.uniform(0, wp), -1, 0, prng.uniform(5, 9), 0, prng.uniform(0, 6.28),
                          prng.choice(FALL_COLORS.get(sidx, FALL_COLORS[2]))])
        while s["acc_snow"] >= 1:
            s["acc_snow"] -= 1
            parts.append([prng.uniform(0, wp), -1, 0, prng.uniform(4, 8), 1, prng.uniform(0, 6.28), SNOW])
        alive = []
        for q in parts:
            q[5] += dt * 2
            q[0] += (wind * (1.0 if q[4] == 0 else 0.6) + 3 * math.sin(q[5])) * dt
            q[1] += q[3] * dt
            if q[1] < hp - 2 and q[1] < gy * 4 + 4 + (q[3] * 5) % (gr * 4 - 2 if gr > 1 else 1):
                alive.append(q)
                col = shade(q[6], 0, nq, fog, ref)
                x, y = q[0] % max(1, wp), q[1]
                top_b.dot(x, y, col)
                if q[4] == 0:
                    top_b.dot(x + 1, y, col)
        s["parts"] = alive

        # fireflies
        if n > 0.3:
            active = int(len(s["flies"]) * min(1.0, n))
            for fl in s["flies"][:active]:
                fl[2] = max(-4, min(4, fl[2] + prng.uniform(-1, 1)))
                fl[3] = max(-3, min(3, fl[3] + prng.uniform(-1, 1)))
                fl[0] = (fl[0] + fl[2] * dt) % max(1, wp)
                fl[1] = max(hp * 0.4, min(hp - 2, fl[1] + fl[3] * dt))
                if math.sin(t * fl[5] + fl[4]) > 0.1:
                    top_b.dot(fl[0], fl[1], 226 if fl[4] > 3 else 190)

        if glow is not None:
            tint = {}
            for y, grow in enumerate(glow):
                if any(grow):
                    crow, bg0 = c.cells[y], rowbg[y]
                    for x, g in enumerate(grow):
                        if g is not None:
                            bg = tint.get((y, g))
                            if bg is None:
                                bg = tint[y, g] = mix(bg0, g[0], g[1])
                            ch, fg, _ = crow[x]
                            crow[x] = (ch, fg, bg)
        for b in s["layers"]:
            blit_layer(b, c)
        top_b.blit(c)

    return term.run(args, step, music="forest")


if __name__ == "__main__":
    raise SystemExit(main())
