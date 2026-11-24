#!/usr/bin/env python3
"""Sharks gliding through a deep, sunlit sea, drawn in two looks.

Each shark is a 3D form: a spine carrying a travelling S-wave (the tail sweeps most), an
elliptical cross-section along it, and dorsal, pectoral, pelvic, anal and tail fins as
planes. Sharks cruise side-on (within about 35 degrees, so the outline always reads), climb
and dive, drift nearer or farther (perspective scales them and far ones fade into the haze),
and swing round in quick banking turns. Two species: a great white, and a hammerhead whose
canted cephalofoil shows from the side. The camera sits a little below them.

  style a  a mosaic of pale cyan-white tiles with dark glyphs (a few red or orange), lit
           from the surface, inside a soft bloom halo that is brightest at head and dorsal
  style b  a dark silhouette wrapped in a swarm of glowing glyphs that trace its outline
           and fins; the glyphs shimmer, re-roll and trail a little behind the motion

The sea is a truecolor depth gradient with a faint dot grid, slanting light shafts, drifting
marine snow and the odd school of small fish that scatters when a shark comes close. Sound:
a deep underwater drone, plus a low swell when a shark passes close.

Usage: python3 sharks.py [--count N] [--style a|b|mix] [--seed N] [--fps 12] [--frames N] [--mute]
  --count N        sharks, 1-6 (default 3)
  --style S        a (tile mosaic), b (glyph swarm) or mix (both; default)
"""
import math
import os
import random
import sys
from itertools import accumulate
from operator import add, sub

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
from fun import audio, term  # noqa: E402

META = {"name": "sharks", "kind": "watch",
        "blurb": "3D sharks in glowing tile mosaics or glyph swarms, gliding through a deep sea",
        "credit": {"type": "inspired by", "who": "stacked (@stackedlol)",
                   "url": "https://x.com/stackedlol/status/2112257760628986188"}}

TAU = 2 * math.pi

# ---------------------------------------------------------------- palette (rgb)
SEA = ((0.0, (24, 66, 112)), (0.22, (14, 44, 84)), (0.55, (7, 22, 48)), (1.0, (3, 7, 16)))
LIGHT = (96, 156, 196)        # what a light shaft adds at full strength near the surface
SHAFT_K = 0.42
DOT_ADD = (11, 16, 22)        # dot-grid glyph colour above the water behind it
GLOW = (150, 210, 240)        # bloom halo tint
HALO_MAX = 0.5               # strongest halo blend toward GLOW
SHADOW = (52, 80, 118)        # unlit tile colour
TINTS = ((200, 234, 244), (238, 245, 248), (172, 208, 234))  # cyan, white, blue tiles
INK = ((30, 36, 46), (52, 60, 74))   # tile glyphs: on bright tiles, on dim tiles
ACCENT = ((206, 56, 52), (232, 128, 48))
EYE_BG, EYE_FG = (16, 22, 32), (150, 176, 196)
SIL = (2, 5, 12)              # style b silhouette, before haze
SWARM_LO, SWARM_HI = (64, 128, 170), (240, 252, 255)
SNOW = (176, 200, 214)
FISH = (178, 200, 216)

TILE_GLYPHS = "XX88SS00$1%X8S"
FRINGE = "·:'.,·"
SWARM_GLYPHS = "··..::'+*01x=%$·.:"
RING_GLYPHS = "01:·.+*x=$%:·01"
SNOW_GLYPHS = "..··'`,"

NL = 12      # light-shaft levels baked into the sea
NQ = 28      # halo levels
ND = 10      # silhouette darkness levels
NLUM = 18    # tile brightness levels
NF = 10      # haze levels
NRB = 10     # row buckets for the haze colour
NSW = 16     # swarm brightness levels
HALO_R = (1, 1)   # halo box-blur radius: half-res columns (two cells each), rows
P = 256      # period of the light-shaft pattern along its slanted axis
SLANT = 0.55
DOT_X, DOT_Y = 2, 1
TILT = 0.24  # radians the camera looks up at the sharks from below
DCAM = 1.15  # camera distance in screen widths; scale = D / (D + z)
ZMIN, ZMAX = -0.18, 1.35   # depth range in screen widths
FOG_MAX = 0.78
SBODY = 0.94               # body sections run s = 0..SBODY; the tail fin covers the rest
RING_BANDS = (1.0, 0.72, 0.5, 0.3)   # ring sample sets, by section radius over the maximum
KBINS = 32                 # angle bins around the ring, shared by every band (tile hashing, gills)
GILL_BINS = [abs(math.cos(TAU * k / KBINS)) > 0.5 and -0.4 < math.sin(TAU * k / KBINS) < 0.5
             for k in range(KBINS)]
MAX_OFF = 0.6              # cruising yaw stays within this of side-on (radians)
TURN_S = 1.9               # seconds for a half turn
WAVE_K = 5.0               # S-wave phase change along the body (radians per body length)
NT = 240                   # profile table resolution
LGT = (-0.3, -0.55, -0.78)
_n = math.sqrt(sum(v * v for v in LGT))
LGT = tuple(v / _n for v in LGT)

_hr = random.Random(9187)
HASH = [_hr.random() for _ in range(4096)]
HMASK = 4095


def lerp(a, b, t):
    return (int(a[0] + (b[0] - a[0]) * t + 0.5), int(a[1] + (b[1] - a[1]) * t + 0.5),
            int(a[2] + (b[2] - a[2]) * t + 0.5))


def grad(stops, u):
    for (p0, c0), (p1, c1) in zip(stops, stops[1:]):
        if u <= p1:
            return lerp(c0, c1, (u - p0) / (p1 - p0))
    return stops[-1][1]


def smooth(x):
    x = 0.0 if x < 0 else 1.0 if x > 1 else x
    return x * x * (3 - 2 * x)


# ---------------------------------------------------------------- species

def white_h(s):
    """Great white half-height along the body (fractions of length): rounded conical snout,
    deepest at a third, a slim caudal peduncle."""
    if s < 0.33:
        u = s / 0.33   # a straight-sided cone that rounds into the shoulders
        return 0.1 * u * (1.5 - 0.5 * u)
    if s < 0.88:
        q = (s - 0.33) / 0.55
        return 0.013 + 0.087 * (1 - q) ** 1.5
    return 0.013 * max(0.0, 1 - (s - 0.88) / 0.12)


def hammer_h(s):
    """Hammerhead half-height: a thin flat head (the cephalofoil is a fin), slimmer body."""
    if s < 0.1:
        return 0.016 + 0.3 * s
    if s < 0.36:
        q = (0.36 - s) / 0.26
        return 0.046 + 0.038 * (1 - q * q)
    if s < 0.88:
        q = (s - 0.36) / 0.52
        return 0.011 + 0.073 * (1 - q) ** 1.45
    return 0.011 * max(0.0, 1 - (s - 0.88) / 0.12)


# Fins: (part, lateral, dorsal, rooted, polygon). The polygon is (s, b) with b the reach
# from the body surface along (lateral, dorsal) in body lengths; unrooted fins measure b
# from the spine (the tail, signed: up is positive). A nonzero lateral means a mirrored pair.
WHITE_FINS = (
    ("dorsal", 0.0, 1.0, True, ((0.32, -0.01), (0.37, 0.09), (0.41, 0.17), (0.436, 0.205),
                                (0.446, 0.165), (0.456, 0.08), (0.49, -0.01))),
    ("pec", 0.55, -0.83, True, ((0.26, -0.01), (0.32, 0.07), (0.41, 0.15), (0.49, 0.215),
                                (0.485, 0.19), (0.43, 0.11), (0.38, 0.04), (0.35, -0.01))),
    ("small", 0.6, -0.8, True, ((0.60, -0.005), (0.65, 0.04), (0.668, 0.036), (0.655, -0.005))),
    ("small", 0.0, 1.0, True, ((0.70, -0.005), (0.725, 0.035), (0.738, 0.032), (0.742, -0.005))),
    ("small", 0.0, -1.0, True, ((0.72, -0.005), (0.75, 0.032), (0.762, 0.03), (0.766, -0.005))),
    ("tail", 0.0, 1.0, False, ((0.86, 0.015), (0.93, 0.09), (1.0, 0.19), (1.07, 0.27), (1.055, 0.22),
                               (1.0, 0.11), (0.965, 0.02), (0.985, -0.08), (1.03, -0.19), (1.015, -0.2),
                               (0.95, -0.09), (0.88, -0.018), (0.86, -0.015))),
)
HAMMER_FINS = (
    ("foil", 0.66, 0.75, True, ((0.0, -0.01), (0.004, 0.08), (0.014, 0.17), (0.028, 0.225), (0.06, 0.22),
                                (0.066, 0.17), (0.08, 0.08), (0.10, 0.015), (0.125, -0.01))),
    ("dorsal", 0.0, 1.0, True, ((0.29, -0.01), (0.34, 0.11), (0.375, 0.21), (0.395, 0.245),
                                (0.405, 0.21), (0.402, 0.11), (0.42, 0.03), (0.45, -0.01))),
    ("pec", 0.6, -0.8, True, ((0.27, -0.01), (0.33, 0.07), (0.41, 0.15), (0.46, 0.18),
                              (0.45, 0.14), (0.4, 0.06), (0.36, -0.01))),
    ("small", 0.6, -0.8, True, ((0.60, -0.005), (0.645, 0.036), (0.66, 0.032), (0.65, -0.005))),
    ("small", 0.0, 1.0, True, ((0.71, -0.005), (0.735, 0.045), (0.745, 0.04), (0.75, -0.005))),
    ("small", 0.0, -1.0, True, ((0.72, -0.005), (0.752, 0.045), (0.765, 0.035), (0.768, -0.005))),
    ("tail", 0.0, 1.0, False, ((0.86, 0.013), (0.95, 0.09), (1.04, 0.19), (1.1, 0.25), (1.09, 0.21),
                               (1.03, 0.09), (0.985, 0.014), (0.995, -0.05), (1.02, -0.12), (1.0, -0.125),
                               (0.93, -0.05), (0.87, -0.014), (0.86, -0.013))),
)
# Fins whose pair is canted (one tip up, one down) rather than mirrored: the hammerhead's
# cephalofoil, so its span shows from the side.
CANTED = {"foil"}
PAIRED = {"pec", "small"}   # mirrored fins; only the one on the camera side is drawn


class Species:
    def __init__(self, name, hfun, wratio, fins, scale, eyes, gills, amp):
        self.name, self.scale, self.amp = name, scale, amp
        self.H = [1.08 * hfun(i / NT * SBODY) for i in range(NT + 1)]
        self.W = [h * wratio for h in self.H]
        self.wratio = wratio
        self.gills = gills
        self.fins = []   # (part, normal (l, d), [(s, fwd, lat, dor)] in body lengths, outline count)
        for part, dl, dd, rooted, poly in fins:
            for side in ((1, -1) if dl else (1,)):
                ds = dd * side if part in CANTED else dd
                pts = []
                for s, b in poly:
                    r = self.radius(s, dl * side, ds) if rooted else 0.0
                    b *= 1.15
                    pts.append((s, 0.5 - s, dl * side * (r + b), ds * (r + b)))
                self.fins.append((part, (-ds, dl * side), pts))
        self.eyes = []   # (s, lat, dor) in body lengths
        for s, dl, dd, b in eyes:
            for side in (1, -1):
                ds = dd * side if b else dd   # eyes out on the hammer follow its cant
                r = self.radius(s, dl * side, ds)
                self.eyes.append((s, dl * side * (r + b * 1.15), ds * (r + b * 1.15)))

    def radius(self, s, dl, dd):
        """Distance from spine to the body surface at s in direction (dl, dd)."""
        i = min(NT, int(min(s, SBODY) / SBODY * NT))
        hh, ww = max(1e-4, self.H[i]), max(1e-4, self.W[i])
        return 1.0 / math.sqrt((dl / ww) ** 2 + (dd / hh) ** 2) if (dl or dd) else 0.0


SPECIES = {
    "white": Species("white", white_h, 0.86, WHITE_FINS, 1.0,
                     ((0.075, 0.78, 0.5, 0.0),), (0.20, 0.222, 0.244, 0.266, 0.288), 0.095),
    "hammer": Species("hammer", lambda s: 1.15 * hammer_h(s), 0.9, HAMMER_FINS, 1.02,
                      ((0.042, 0.66, 0.75, 0.215),), (0.17, 0.19, 0.21, 0.23, 0.25), 0.105),
}


# ---------------------------------------------------------------- the sea

class Sea:
    """Precomputed background rows plus the lookup tables halos, silhouettes and snow use."""

    def __init__(self, w, h, rng):
        self.w, self.h = w, h
        span = max(1, h - 1)
        self.base = base = [grad(SEA, y / span) for y in range(h)]
        prof = [0.0] * P
        for _ in range(7):
            c, wd, a = rng.uniform(0, P), rng.uniform(3.5, 11.0), rng.uniform(0.45, 1.0)
            for k in range(P):
                d = (k - c + P / 2) % P - P / 2
                prof[k] += a * math.exp(-(d / wd) ** 2)
        lev = [min(NL - 1, int(min(1.0, v) * (NL - 1) + 0.5)) for v in prof]
        self.sea = sea = []
        for y in range(h):
            u = y / span
            fade = SHAFT_K * (1 - u) ** 1.5
            sea.append([tuple(min(255, int(base[y][c] + LIGHT[c] * fade * l / (NL - 1))) for c in range(3))
                        for l in range(NL)])
        n = w + P
        self.levrows, self.rowcells = [], [[] for _ in range(DOT_X)]
        self.halo, self.halod, self.dark, self.snow = [], [], [], []
        for y in range(h):
            off = int(y * SLANT)
            lr = [lev[(j - off) % P] for j in range(n)]
            self.levrows.append(lr)
            plain = [(" ", None, c) for c in sea[y]]
            dots = [("·", tuple(min(255, v + a) for v, a in zip(c, DOT_ADD)), c) for c in sea[y]]
            for p in range(DOT_X):
                if y % DOT_Y:
                    self.rowcells[p].append([plain[lr[j]] for j in range(n)])
                else:
                    self.rowcells[p].append([dots[lr[j]] if (j - p) % DOT_X == 0 else plain[lr[j]]
                                             for j in range(n)])
            hl, hd, dk = [], [], []
            for l in range(NL):
                c = sea[y][l]
                for q in range(NQ):
                    g = lerp(c, GLOW, HALO_MAX * (q / (NQ - 1)) ** 1.25)
                    hl.append((" ", None, g))
                    hd.append(("·", tuple(min(255, v + a) for v, a in zip(g, DOT_ADD)), g))
                for d in range(ND):
                    dk.append((" ", None, lerp(c, SIL, 0.88 * d / (ND - 1))))
            self.halo.append(hl)
            self.halod.append(hd)
            self.dark.append(dk)
            self.snow.append([lerp(base[y], SNOW, a) for a in (0.16, 0.28, 0.42, 0.58)])
        self.swarm = [lerp(SWARM_LO, SWARM_HI, (i / (NSW - 1)) ** 0.7) for i in range(NSW)]
        self._pal = {}

    def palette(self, fq, rb):
        """Tile colours for haze level fq at row bucket rb (the haze is the sea colour there)."""
        key = (fq, rb)
        pal = self._pal.get(key)
        if pal is None:
            fog = self.base[min(self.h - 1, int((rb + 0.5) / NRB * self.h))]
            f = FOG_MAX * fq / (NF - 1)
            tiles = [[lerp(lerp(SHADOW, tint, (li / (NLUM - 1)) ** 0.85), fog, f) for li in range(NLUM)]
                     for tint in TINTS]
            ink = [lerp(c, fog, f * 0.9) for c in INK]
            acc = [lerp(c, fog, f) for c in ACCENT]
            pal = self._pal[key] = (tiles, ink, acc, lerp(EYE_BG, fog, f), lerp(EYE_FG, fog, f))
        return pal


# ---------------------------------------------------------------- blur

def _box(rows, r):
    pad = [0.0] * r
    d = 2 * r + 1
    out = []
    for row in rows:
        p = list(accumulate(pad + row + pad, initial=0.0))
        out.append(list(map(sub, p[d:], p[:-d])))
    return out


def blur(rows, rx, ry):
    """Three passes of a box blur each way (unnormalised), on a list of equal-length rows."""
    rows = _box(_box(_box(rows, rx), rx), rx)
    cols = _box(_box(_box([list(c) for c in zip(*rows)], ry), ry), ry)
    return [list(r) for r in zip(*cols)]


# ---------------------------------------------------------------- sharks

class Shark:
    def __init__(self, rng, idx, species, style):
        self.rng, self.idx = rng, idx
        self.sp = SPECIES[species]
        self.style = style
        self.seed = rng.randrange(4096)
        self.size = rng.uniform(0.9, 1.08)
        self.phase = rng.random() * TAU
        self.beat = rng.uniform(0.42, 0.58)
        self.band = None
        self.zb = {}
        self.parts = []
        self.next_swell = rng.uniform(4, 12)
        self.next_flip = rng.uniform(30, 60)
        self.offscreen = False
        self.exiting = False
        self.lane = idx
        self.head, self.scale, self.bbox, self.fog = (-1e9, -1e9), 0.0, None, 0.0

    # -- motion

    def fit(self, sc, zf):
        rng, w, h = self.rng, sc.w, sc.h
        self.L = 0.5 * min(w, 2.8 * h) * self.sp.scale * self.size
        self.speed = self.L * rng.uniform(0.12, 0.15)
        self.band = zf
        self.Z = sc.zof(zf)
        half = sc.half(self.Z)
        n = len(sc.sharks)
        self.X = sc.cx + (((self.idx + 0.5) / n) * 2 - 1) * 0.65 * half + rng.uniform(-0.1, 0.1) * half
        vh = h * (sc.D + self.Z) / sc.D
        self.Y = sc.cyw + (self.lane_y(n) + rng.uniform(-0.1, 0.1)) * vh
        self.Y = self.clamp_y(sc, self.Y, self.Z)
        self.dir = 1 if rng.random() < 0.5 else -1
        self.off = rng.uniform(-0.2, 0.2)
        self.yaw = self.off if self.dir > 0 else math.pi - self.off
        self.turn = None
        self.yaw_rate = self.roll = self.vy = 0.0
        self.pick(sc, first=True)
        self.parts = []

    def lane_y(self, n):
        """Centre of this shark's height band, as a fraction of the visible half-height."""
        return ((self.lane + 0.5) / n * 2 - 1) * 0.62 if n > 1 else 0.0

    def clamp_y(self, sc, y, z):
        """Keep the dorsal fin, tail tip and pectorals inside the frame at depth z."""
        vh = sc.h * (sc.D + z) / sc.D
        lo, hi = sc.cyw - vh + 0.52 * self.L, sc.cyw + vh - 0.38 * self.L
        return max(lo, min(hi, y)) if lo < hi else sc.cyw

    def pick(self, sc, first=False):
        rng = self.rng
        tz = sc.zof(min(1.0, max(0.0, self.band + rng.uniform(-0.22, 0.22))))
        half = sc.half(tz)
        side = self.dir
        # one shark at a time may leave the frame to turn out of sight; the rest turn on screen
        others_out = any(o.exiting for o in sc.sharks if o is not self)
        self.exiting = len(sc.sharks) > 1 and not others_out and not first and rng.random() < 0.3
        if self.exiting:
            tx = sc.cx + side * (half + 0.75 * self.L)
        else:
            tx = sc.cx + side * half * rng.uniform(0.15, 0.55)
        vh = sc.h * (sc.D + tz) / sc.D
        if first:   # never start already past the first turning point
            tx = self.X + side * max(side * (tx - self.X), 0.4 * self.L)
        self.tx, self.tz = tx, tz
        ty = sc.cyw + (self.lane_y(len(sc.sharks)) + rng.uniform(-0.16, 0.16)) * vh
        # keep the dorsal fin and the pectorals inside the frame
        self.ty = self.clamp_y(sc, ty, tz)
        self.retarget = sc.t + rng.uniform(22, 34)

    def step(self, sc, dt):
        t = sc.t
        if self.turn is None and ((self.dir > 0 and self.X >= self.tx) or (self.dir < 0 and self.X <= self.tx)
                                  or t > self.retarget):
            self.start_turn(sc)
        if self.turn is not None:
            t0, dur, y0, y1 = self.turn
            u = min(1.0, (t - t0) / dur)
            yaw = y0 + (y1 - y0) * smooth(u)
            rate = (yaw - self.yaw) / dt
            self.yaw = yaw
            if u >= 1.0:
                self.turn = None
                self.yaw = (yaw + math.pi) % TAU - math.pi
                self.off = self.yaw if self.dir > 0 else math.pi - self.yaw
                self.off = (self.off + math.pi) % TAU - math.pi
        else:
            # cruise side-on: the yaw offset from the side view only steers depth
            want = math.atan2(self.tz - self.Z, max(self.L, abs(self.tx - self.X)))
            want = max(-MAX_OFF, min(MAX_OFF, want))
            k = 1 - math.exp(-dt / 2.5)
            old = self.yaw
            self.off += (want - self.off) * k
            self.yaw = self.off if self.dir > 0 else math.pi - self.off
            rate = ((self.yaw - old + math.pi) % TAU - math.pi) / dt
        self.yaw_rate = rate
        self.roll += (max(-0.55, min(0.55, rate * 0.35)) - self.roll) * (1 - math.exp(-dt / 0.5))
        vmax = self.speed * 0.3
        wy = max(-vmax, min(vmax, (self.ty - self.Y) * 0.22))
        for o in sc.sharks:
            # keep apart on screen, whatever the depth: overlapping outlines stop reading
            if o is self or abs(o.Z - self.Z) > 0.7 * sc.w:
                continue
            gap = 0.5 * (self.L + o.L)
            dx, dy = o.X - self.X, o.Y - self.Y
            if abs(dx) < gap and abs(dy) < 0.5 * gap:
                wy -= 1.6 * vmax * (1 if dy >= 0 else -1) * (1 - abs(dx) / gap)
        self.vy += (wy - self.vy) * (1 - math.exp(-dt / 1.4))
        v = self.speed * (0.75 if self.turn is not None else 1.0)
        self.pitch = math.atan2(-self.vy, v)
        cp = math.cos(self.pitch)
        self.X += math.cos(self.yaw) * cp * v * dt
        self.Z += math.sin(self.yaw) * cp * v * dt
        self.Z = max(sc.zof(0.0), min(sc.zof(1.0), self.Z))
        self.Y = self.clamp_y(sc, self.Y + self.vy * dt, self.Z)
        self.wave = TAU * self.beat * t + self.phase

    def start_turn(self, sc):
        """Swing round through the nose-on view quickly (toward the camera), then head back."""
        new = -self.dir
        self.dir = new
        self.pick(sc)
        off = 0.0
        end = off if new > 0 else math.pi - off
        y0 = self.yaw
        if new < 0:            # was heading right: yaw falls through -90 degrees
            while end > y0:
                end -= TAU
            while end < y0 - TAU:
                end += TAU
        else:                  # was heading left: yaw rises through 270 degrees
            while end < y0:
                end += TAU
            while end > y0 + TAU:
                end -= TAU
        self.turn = (sc.t, TURN_S * abs(end - y0) / math.pi, y0, end)

    # -- geometry

    def frame(self):
        """Body axes (forward, lateral, dorsal) in screen space: x right, y down, z away."""
        cp, sp = math.cos(self.pitch), math.sin(self.pitch)
        cr, sr = math.cos(self.roll), math.sin(self.roll)
        f, d, l = (1.0, 0.0, 0.0), (0.0, -1.0, 0.0), (0.0, 0.0, 1.0)
        f, d = (tuple(a * cp + b * sp for a, b in zip(f, d)), tuple(b * cp - a * sp for a, b in zip(f, d)))
        d, l = (tuple(a * cr + b * sr for a, b in zip(d, l)), tuple(b * cr - a * sr for a, b in zip(d, l)))
        cy, sy = math.cos(self.yaw), math.sin(self.yaw)
        ct, st = math.cos(-TILT), math.sin(-TILT)
        out = []
        for x, y, z in (f, l, d):
            x, z = x * cy - z * sy, x * sy + z * cy
            y, z = y * ct - z * st, y * st + z * ct
            out.append((x, y, z))
        return out

    def build(self, sc):
        """Rasterise into self.zb: cell key -> (z, shade, section or -1-fin, ring index)."""
        w, h, D, cxs, cyw = sc.w, sc.h, sc.D, sc.cx, sc.cyw
        sp, L = self.sp, self.L
        (fx, fy, fz), (lx, ly, lz), (dx, dy, dz) = self.axes = self.frame()
        X, Y, Z = self.X, self.Y, self.Z
        sc0 = D / (D + Z)
        self.scale = sc0
        self.fog = smooth((Z - sc.zof(0.12)) / (sc.zof(1.0) - sc.zof(0.12))) if Z > sc.zof(0.12) else 0.0
        amp, wave = sp.amp * L, self.wave
        if abs(cxs + (X - cxs) * sc0 - cxs) > 0.5 * w + 0.75 * L * sc0 or \
                abs(cyw + (Y - cyw) * sc0 - cyw) > h + 0.6 * L * sc0:
            self.zb, self.bbox, self.head = {}, None, (-1e9, -1e9)
            return

        def spine(s):
            wv = amp * (0.1 + 0.9 * s * s) * math.sin(WAVE_K * s - wave)
            fw = L * (0.5 - s)
            return X + fx * fw + lx * wv, Y + fy * fw + ly * wv, Z + fz * fw + lz * wv

        hmax = max(sp.H) * L
        rr = hmax * sc0 * max(math.hypot(lx, dx), 0.5 * math.hypot(ly, dy))
        kn = max(12, min(64, int(TAU * rr / 1.15) + 4))
        proj = L * sc0 * max(abs(fx), 0.5 * abs(fy), 0.25)
        # about one section per column, plus extra when the body points at the camera so the
        # nested rings of the tapering snout and tail still close up
        ns = max(16, min(170, int(proj * 1.2) + int(hmax * sc0 * 4 * abs(fz)) + 6))
        wr = sp.wratio
        # Ring samples, one set per radius band so thin sections aren't oversampled. Each is
        # (lateral xyz, dorsal xyz, shade, angle bin); x and y are already in cells.
        bands = []
        for frac in RING_BANDS:
            kn = max(10, min(64, int(TAU * rr * frac / 1.15) + 4))
            vis = []
            for k in range(kn):
                th = TAU * k / kn
                c, s_ = math.cos(th), math.sin(th)
                nx, ny, nz = c / wr * lx + s_ * dx, c / wr * ly + s_ * dy, c / wr * lz + s_ * dz
                m = math.sqrt(nx * nx + ny * ny + nz * nz)
                nx, ny, nz = nx / m, ny / m, nz / m
                if nz > 0.22:
                    continue
                ndl = nx * LGT[0] + ny * LGT[1] + nz * LGT[2]
                lit = max(0.0, (ndl + 0.6) / 1.6)
                # countershading: a dark back over a pale belly, with a soft frontal light
                alb = 1.0 - 0.62 * smooth((s_ + 0.15) / 0.75)
                rim = 0.8 + 0.2 * min(1.0, -nz * 1.8) if nz < 0 else 0.8
                shade = min(1.0, (0.55 + 0.55 * lit) * alb * rim)
                vis.append((c * lx, c * ly * 0.5, c * lz, s_ * dx, s_ * dy * 0.5, s_ * dz, shade,
                            int(k * KBINS / kn)))
            bands.append(vis)
        zb = {}
        get = zb.get
        secs = []
        Ht, Wt = sp.H, sp.W
        inv = 1.0 / max(Ht)
        nb = len(RING_BANDS)
        for i in range(ns):
            s = SBODY * i / (ns - 1)
            ti = int(s / SBODY * NT)
            H, W = Ht[ti] * L, Wt[ti] * L
            Cx, Cy, Cz = spine(s)
            sc_ = D / (D + Cz)
            Xc = cxs + (Cx - cxs) * sc_
            Yc = (cyw + (Cy - cyw) * sc_) * 0.5
            Ws, Hs = W * sc_, H * sc_
            secs.append((Xc, Yc, Cz, Ws, Hs, W, H))
            f = Ht[ti] * inv
            j = 0
            while j + 1 < nb and RING_BANDS[j + 1] >= f:
                j += 1
            for ax, ay, az, bx, by, bz, shade, k in bands[j]:
                xf = Xc + Ws * ax + Hs * bx
                if xf < 0 or xf >= w:
                    continue
                yf = Yc + Ws * ay + Hs * by
                if yf < 0 or yf >= h:
                    continue
                key = int(yf) * w + int(xf)
                zz = Cz + W * az + H * bz
                o = get(key)
                if o is None or zz < o[0]:
                    zb[key] = (zz, shade, i, k)
        self.secs = secs
        self.gills = {round(g / SBODY * (ns - 1)) for g in sp.gills} if proj > 34 else set()
        # fins: project the outline, then scanline-fill it at one depth with flat shading
        self.fpolys = []
        small_ok = proj > 26
        for fi, (part, (nl, nd), pts) in enumerate(sp.fins):
            if part == "small" and not small_ok:
                self.fpolys.append(None)
                continue
            if part in PAIRED and pts[-2][2] and (pts[-2][2] > 0) == (lz > 0):
                self.fpolys.append(None)   # the far-side fin of a pair: hidden behind the body
                continue
            nx, ny, nz = lx * nl + dx * nd, ly * nl + dy * nd, lz * nl + dz * nd
            ndl = abs(nx * LGT[0] + ny * LGT[1] + nz * LGT[2])
            # fins are dark like the back, the pectorals a little paler underneath
            shade = (0.3 + 0.25 * ndl) * (1.25 if part == "pec" else 1.0)
            spts, zs = [], 0.0
            for s, fw, la, do in pts:
                wv = amp * (0.1 + 0.9 * s * s) * math.sin(WAVE_K * s - wave)
                la, fw, do = la * L + wv, fw * L, do * L
                px, py, pz = X + fx * fw + lx * la + dx * do, Y + fy * fw + ly * la + dy * do, \
                    Z + fz * fw + lz * la + dz * do
                s2 = D / (D + pz)
                spts.append((cxs + (px - cxs) * s2, (cyw + (py - cyw) * s2) * 0.5))
                zs += pz
            zf = zs / len(pts)
            self.fpolys.append((spts, zf, part))
            fill_poly(spts, zb, w, h, (zf, shade, -1 - fi, 0))
        # close one-cell gaps (fin roots, rounding) and keep the cells just outside the outline
        miss = {}
        for key in zb:
            x = key % w
            for n, ok in ((key - 1, x > 0), (key + 1, x < w - 1), (key - w, key >= w), (key + w, key < w * (h - 1))):
                if ok and n not in zb:
                    miss[n] = miss.get(n, 0) + 1
        ring = []
        for n, c in miss.items():
            if c >= 3:
                zb[n] = zb.get(n - 1) or zb.get(n + 1) or zb.get(n - w) or zb[n + w]
            else:
                ring.append(n)
        self.ring = ring
        if zb:
            r = max(max(sec[3], sec[4]) for sec in secs) + 1
            xs = [sec[0] for sec in secs] + [p[0] for f in self.fpolys if f for p in f[0]]
            ys = [sec[1] for sec in secs] + [p[1] for f in self.fpolys if f for p in f[0]]
            self.bbox = (max(0, int(min(xs) - r)), max(0, int(min(ys) - r * 0.5)),
                         min(w - 1, int(max(xs) + r)), min(h - 1, int(max(ys) + r * 0.5)))
        else:
            self.bbox = None
        self.zb = zb
        hx, hy, hz = spine(0.0)
        s2 = D / (D + hz)
        self.head = (cxs + (hx - cxs) * s2, (cyw + (hy - cyw) * s2) * 0.5)
        self.eyes = set()
        for s, la, do in sp.eyes:
            ex, ey, ez = spine(s)
            ex, ey, ez = ex + lx * la * L + dx * do * L, ey + ly * la * L + dy * do * L, ez + lz * la * L + dz * do * L
            s2 = D / (D + ez)
            px, py = cxs + (ex - cxs) * s2, (cyw + (ey - cyw) * s2) * 0.5
            if 0 <= px < w and 0 <= py < h:
                key = int(py) * w + int(px)
                o = zb.get(key)
                if o is not None and ez <= o[0] + 0.12 * L:
                    self.eyes.add(key)

    # -- style a

    def glow_a(self, src, w):
        """Add this body's bloom source: brighter at the head and the dorsal fin."""
        k = 1.0 - 0.8 * self.fog
        fins = self.sp.fins
        head = 0.3 * len(self.secs)   # sections in the front 30% of the body
        for key, (z, sh, i, kk) in self.zb.items():
            if i < 0:
                v = 2.2 if fins[-1 - i][0] == "dorsal" else 0.8
            elif i < head:
                v = 2.6 - 1.6 * i / head
            else:
                v = 1.0
            src[key] += k * v * (0.6 + 0.4 * sh)

    def draw_a(self, cv, sea, t):
        zb, w, cells = self.zb, cv.w, cv.cells
        fq = min(NF - 1, int(self.fog * (NF - 1) + 0.5))
        rb = min(NRB - 1, max(0, int(self.head[1] / cv.h * NRB)))
        tiles, ink, acc, eye_bg, eye_fg = sea.palette(fq, rb)
        seed, gills, gk, eyes = self.seed, self.gills, GILL_BINS, self.eyes
        hx, hy = int(self.head[0]), int(self.head[1])
        roll = int(t * 0.45)
        facing = "(" if math.cos(self.yaw) > 0 else ")"
        nl1 = NLUM - 1
        for key, (z, sh, i, k) in zb.items():
            y, x = divmod(key, w)
            nb = (key - 1 in zb) + (key + 1 in zb) + (key - w in zb) + (key + w in zb)
            if i >= 0:
                b = (i >> 1) * 37 + (k >> 1) * 101 + seed
            else:
                b = (-i) * 211 + ((x - hx) >> 1) * 37 + (y - hy) * 101 + seed
            hv = HASH[b & HMASK]
            tint = 2 if i < 0 and hv < 0.6 else int(hv * 2.99)
            if nb == 0:
                cells[y][x] = (FRINGE[int(hv * 5.99)], tiles[tint][int(sh * nl1)], cells[y][x][2])
                continue
            if key in eyes:
                cells[y][x] = ("•", eye_fg, eye_bg)
                continue
            if nb < 4:   # outline cells: a darker tile so the silhouette edge stays crisp
                sh *= 0.62
            li = int(sh * nl1 + 0.5)
            bg = tiles[tint][li]
            r = HASH[(b + (roll + int(hv * 7)) * 977) & HMASK]
            if i in gills and gk[k]:
                cells[y][x] = (facing, ink[0], tiles[tint][max(0, li - 4)])
            elif r < 0.035:
                cells[y][x] = (TILE_GLYPHS[int(r * 400) % 14], acc[int(r * 1000) & 1], bg)
            else:
                cells[y][x] = (TILE_GLYPHS[int(r * 14)], ink[li < 9], bg)

    # -- style b

    def make_parts(self, dt):
        """Swarm glyphs anchored to the outline (rim of the body) and the fin edges. Each is a
        list: [kind (0 rim, 1 fin), s or fin index, rim side or edge position, rim angle
        jitter, outward push (cells), easing per frame, phase, glyph, next re-roll time,
        x, y, visibility, density rank, brightness]."""
        rng = self.rng
        parts = []
        nrim = int(self.L * 3.0)
        for _ in range(nrim):
            s = rng.random() ** 0.85
            tau = rng.uniform(0.07, 0.4)
            parts.append([0, s, rng.random() < 0.5, rng.uniform(-1, 1), 1.0 + 2.2 * rng.random() ** 1.6,
                          1 - math.exp(-dt / tau), rng.random() * TAU, rng.choice(SWARM_GLYPHS),
                          rng.uniform(0, 3), None, None, 0.0, rng.random(), rng.uniform(0.6, 1.0)])
        nfin = int(self.L * 1.8)
        nf = len(self.sp.fins)
        weights = [0.25 if p == "small" else 1.0 for p, _, _ in self.sp.fins]
        for _ in range(nfin):
            fi = rng.choices(range(nf), weights)[0]
            tau = rng.uniform(0.07, 0.4)
            parts.append([1, fi, rng.random(), 0.0, 1.0 + 1.8 * rng.random() ** 1.6,
                          1 - math.exp(-dt / tau), rng.random() * TAU, rng.choice(SWARM_GLYPHS),
                          rng.uniform(0, 3), None, None, 0.0, rng.random(), rng.uniform(0.7, 1.0)])
        self.parts = parts

    def swarm(self, sc, t, dt, src):
        """Ease the swarm glyphs toward their anchors and add their glow to src; the glyphs
        to draw go to self.swarm_cells as (cell key, glyph, brightness level)."""
        if not self.parts:
            self.make_parts(dt)
        w, h = sc.w, sc.h
        (fx, fy, fz), (lx, ly, lz), (dx, dy, dz) = self.axes
        th0 = math.atan2(-lz, dz)
        spread = 0.1 + 1.2 * fz * fz
        secs, ns, zb = self.secs, len(self.secs), self.zb
        fogk = 1.0 - 0.72 * self.fog
        dens = min(1.0, 0.1 + self.scale ** 2 * 0.9)
        pk = min(1.0, self.scale ** 1.5)
        outl = []
        for fp in self.fpolys:
            if fp is None:
                outl.append(None)
                continue
            spts, zf, part = fp
            n = len(spts) - 1
            cx = sum(p[0] for p in spts) / (n + 1)
            cy = sum(p[1] for p in spts) / (n + 1)
            outl.append((spts, n, cx, cy, zf))
        out = []
        for p in self.parts:
            if p[12] > dens:
                continue
            if p[0] == 0:
                sec = secs[min(ns - 1, int(p[1] * (ns - 1)))]
                Xc, Yc, Cz, Ws, Hs, W, H = sec
                th = th0 + (math.pi if p[2] else 0.0) + p[3] * spread
                c, s_ = math.cos(th), math.sin(th)
                ox = Ws * lx * c + Hs * dx * s_
                oy = Ws * ly * c + Hs * dy * s_
                m = p[4] * pk / (math.hypot(ox, oy) or 1.0)
                tx = Xc + ox * (1.0 + m)
                ty = Yc + oy * (0.5 + m)
                tz = Cz + W * lz * c + H * dz * s_
                bright = p[13] * (1.0 - 0.35 * abs(p[3])) * (1.15 - 0.3 * p[4])
            else:
                fo = outl[p[1]]
                if fo is None:
                    continue
                spts, n, cx, cy, tz = fo
                u = p[2] * n
                j = min(n - 1, int(u))
                f = u - j
                (ax, ay), (bx, by) = spts[j], spts[j + 1]
                tx, ty = ax + (bx - ax) * f, ay + (by - ay) * f
                ox, oy = tx - cx, (ty - cy) * 2
                m = math.hypot(ox, oy) or 1.0
                tx += ox / m * p[4] * pk
                ty += oy / m * p[4] * pk * 0.5
                bright = p[13] * (1.15 - 0.3 * p[4])
            ph = p[6]
            tx += 0.3 * pk * math.sin(t * 1.9 + ph)
            ty += 0.2 * pk * math.sin(t * 1.4 + 2 * ph)
            if p[9] is None:
                p[9], p[10] = tx, ty
            else:
                a = p[5]
                p[9] += (tx - p[9]) * a
                p[10] += (ty - p[10]) * a
            if t >= p[8]:
                p[7] = SWARM_GLYPHS[int(HASH[int(t * 13 + ph * 100) & HMASK] * len(SWARM_GLYPHS))]
                p[8] = t + 0.7 + 2.6 * HASH[int(ph * 1000 + t * 7) & HMASK]
            px, py = p[9], p[10]
            if not (0 <= px < w and 0 <= py < h):
                continue
            key = int(py) * w + int(px)
            o = zb.get(key)
            vis = o is None
            p[11] += ((1.0 if vis else 0.0) - p[11]) * 0.35
            b = bright * p[11] * fogk * (0.74 + 0.26 * math.sin(t * (2.2 + 2 * HASH[int(ph * 651) & HMASK]) + ph))
            if b < 0.1:
                continue
            if src is not None:
                src[key] += b * 0.9
            out.append((key, p[7], min(NSW - 1, int(b * 1.25 * (NSW - 1)))))
        self.swarm_cells = out

    def draw_b(self, cv, sea, shift, t):
        zb, w, h, cells = self.zb, cv.w, cv.h, cv.cells
        dark, levrows = sea.dark, sea.levrows
        d = int((1.0 - 0.5 * self.fog) * (ND - 1) * 0.96)
        for key in zb:
            y, x = divmod(key, w)
            cells[y][x] = dark[y][levrows[y][x + shift] * ND + d]
        ring = self.ring
        # the outline: a dense ring of bright glyphs in the cells just outside the silhouette,
        # each re-rolling on its own slow clock
        sw, top = sea.swarm, NSW - 1
        fogk = 1.0 - 0.72 * self.fog
        seed = self.seed
        for key in ring:
            r = HASH[(key * 7 + seed) & HMASK]
            tick = int(t * (0.4 + r) + r * 9)
            g = HASH[(key * 13 + tick * 977 + seed) & HMASK]
            if g > 0.8:
                continue
            y, x = divmod(key, w)
            lv = int(top * fogk * (0.55 + 0.45 * HASH[(key + tick * 31) & HMASK]))
            cells[y][x] = (RING_GLYPHS[int(g * 1.25 * len(RING_GLYPHS)) % len(RING_GLYPHS)], sw[lv],
                           cells[y][x][2])
        for key, g, lv in self.swarm_cells:
            y, x = divmod(key, w)
            cells[y][x] = (g, sw[lv], cells[y][x][2])


def fill_poly(pts, zb, w, h, val):
    """Scanline-fill a screen polygon into zb (nearer wins); every row and column it
    touches gets at least one cell, so edge-on fins still read as thin lines."""
    ys = [p[1] for p in pts]
    ymin, ymax = min(ys), max(ys)
    if ymax < 0 or ymin >= h:
        return
    n = len(pts)
    z = val[0]
    for row in range(max(0, int(ymin)), min(h - 1, int(ymax)) + 1):
        yc = min(max(row + 0.5, ymin + 1e-3), ymax - 1e-3)
        xs = []
        for j in range(n):
            (ax, ay), (bx, by) = pts[j], pts[(j + 1) % n]
            if (ay <= yc < by) or (by <= yc < ay):
                xs.append(ax + (yc - ay) * (bx - ax) / (by - ay))
        xs.sort()
        base = row * w
        for a, b in zip(xs[::2], xs[1::2]):
            c0, c1 = int(math.ceil(a - 0.5)), int(math.floor(b - 0.5))
            if c1 < c0:
                c0 = c1 = int((a + b) * 0.5)
            for c in range(max(0, c0), min(w - 1, c1) + 1):
                o = zb.get(base + c)
                if o is None or z < o[0]:
                    zb[base + c] = val


# ---------------------------------------------------------------- small fish and snow

class School:
    """A small shoal that cruises across, then bolts when a shark's head gets close."""

    def __init__(self, rng, w, h):
        self.rng = rng
        self.d = rng.choice((-1, 1))
        self.cx = -4.0 if self.d > 0 else w + 4.0
        self.cy = rng.uniform(0.22, 0.7) * h
        self.speed = rng.uniform(4.5, 6.5)
        self.fish = [[rng.gauss(0, 3.2), rng.gauss(0, 1.1), rng.random() * TAU, 0.0, 0.0]
                     for _ in range(rng.randint(9, 16))]
        self.scatter = None
        self.age = 0.0

    def step(self, dt, w, sharks):
        self.age += dt
        if self.scatter is None:
            self.cx += self.d * self.speed * dt
            for sh in sharks:
                hx, hy = sh.head
                if sh.scale > 0.6 and abs(hx - self.cx) < 14 and abs(hy - self.cy) < 6:
                    self.bolt(hx, hy)
                    break
        else:
            self.scatter += dt
            for f in self.fish:
                f[0] += f[3] * dt
                f[1] += f[4] * dt
                f[3] *= 0.94
                f[4] *= 0.94
        gone = self.cx < -20 or self.cx > w + 20
        return gone or (self.scatter is not None and self.scatter > 2.8)

    def bolt(self, hx, hy):
        self.scatter = 0.0
        rng = self.rng
        for f in self.fish:
            a = math.atan2((self.cy + f[1] - hy) * 2, self.cx + f[0] - hx) + rng.gauss(0, 0.5)
            v = rng.uniform(10, 19)
            f[3], f[4] = math.cos(a) * v, math.sin(a) * v * 0.5

    def draw(self, cv, sea, t):
        fade = 0.0 if self.scatter is None else min(1.0, self.scatter / 2.8)
        cells, w, h = cv.cells, cv.w, cv.h
        for f in self.fish:
            x = int(self.cx + f[0])
            y = int(self.cy + f[1] + 0.35 * math.sin(t * 4 + f[2]))
            if 0 <= x < w and 0 <= y < h:
                vx = f[3] if self.scatter is not None else self.d
                flash = 0.3 * max(0.0, math.sin(t * 6 + f[2]))
                c = lerp(sea.base[y], FISH, max(0.0, (0.7 + flash) * (1 - fade)))
                cells[y][x] = (">" if vx > 0 else "<", c, cells[y][x][2])


class Snow:
    def __init__(self, rng, w, h):
        n = max(10, w * h // 46)
        self.p = [[rng.uniform(0, w), rng.uniform(0, h), rng.uniform(0.15, 0.55), rng.random() * TAU,
                   rng.choice(SNOW_GLYPHS), rng.choices((0, 1, 2), (5, 3, 2))[0]] for _ in range(n)]

    def step(self, dt, w, h):
        for m in self.p:
            m[1] += m[2] * (0.6 + 0.4 * m[5]) * dt
            if m[1] >= h:
                m[1] -= h + 1
                m[0] = (m[0] * 7.31 + 13) % w

    def draw(self, cv, sea, t, only):
        cells, w, h = cv.cells, cv.w, cv.h
        for x, y, v, ph, g, layer in self.p:
            if layer != only:
                continue
            xi = int(x + 1.6 * math.sin(t * 0.35 + ph)) % w
            yi = int(y)
            if 0 <= yi < h:
                a = layer + (1 if math.sin(t * 0.8 + ph * 3) > 0.6 else 0)
                cells[yi][xi] = (g, sea.snow[yi][a], cells[yi][xi][2])


# ---------------------------------------------------------------- scene

DEPTHS = (0.1, 0.3, 0.62, 0.2, 0.85, 0.45)


class Scene:
    def __init__(self, args):
        self.rng = random.Random(args.seed)
        self.count = max(1, min(6, args.count))
        self.style = args.style
        self.sharks = []
        for i in range(self.count):
            species = ("white", "hammer")[(i + i // 2) % 2]
            style = {"a": "a", "b": "b"}.get(args.style, "ab"[i % 2])
            self.sharks.append(Shark(self.rng, i, species, style))
        # dark silhouettes read best against the brighter water near the surface
        order = sorted(self.sharks, key=lambda s: (s.style != "b", self.rng.random()))
        for lane, s in enumerate(order):
            s.lane = lane
        self.size = None
        self.school = None
        self.t = 0.0
        self.next_swell = 0.0

    def zof(self, zf):
        return (ZMIN + (ZMAX - ZMIN) * zf) * self.w

    def half(self, z):
        return 0.5 * self.w * (self.D + z) / self.D

    def layout(self, w, h):
        self.size = (w, h)
        self.w, self.h = w, h
        self.cx, self.cyw = w / 2, float(h)
        self.D = DCAM * w
        self.sea = Sea(w, h, random.Random(self.rng.random()))
        # silhouettes take the nearer depth bands: close and large they read best, and the
        # glowing mosaics hold up farther back
        near_first = sorted(self.sharks, key=lambda s: (s.style != "b", s.idx))
        for i, s in enumerate(near_first):
            s.fit(self, min(1.0, max(0.0, DEPTHS[i % 6] + self.rng.uniform(-0.05, 0.05))))
        self.snow = Snow(self.rng, w, h)
        self.school = None
        self.hq = [0] * (w * h)   # halo level last drawn per cell
        self.halo = None

    def step(self, cv, frame, fps):
        w, h = cv.w, cv.h
        if self.size != (w, h):
            self.layout(w, h)
        dt = 1.0 / fps
        self.t = t = frame / fps
        sea = self.sea
        for s in self.sharks:
            s.step(self, dt)
        self.snow.step(dt, w, h)
        if self.school is None:
            if self.rng.random() < 0.06 * dt:
                self.school = School(self.rng, w, h)
        elif self.school.step(dt, w, self.sharks):
            self.school = None

        shift = int(t * 0.45) % P   # light shafts drift one cell every couple of seconds
        rc = sea.rowcells[shift % DOT_X]
        cells = cv.cells
        for y in range(h):
            cells[y] = rc[y][shift:shift + w]

        # the halo is soft, so its blur is redone every other frame and reused in between
        fresh = frame % 2 == 0 or self.halo is None
        src = [0.0] * (w * h) if fresh else None
        box = [w, h, -1, -1]
        order = sorted(self.sharks, key=lambda s: -s.Z)
        for s in order:
            s.build(self)
            onscreen = s.bbox is not None
            if not onscreen and not s.offscreen and self.style == "mix" and t > s.next_flip:
                s.style = "b" if s.style == "a" else "a"
                s.parts = []
                s.next_flip = t + self.rng.uniform(35, 70)
            s.offscreen = not onscreen
            if not onscreen:
                continue
            if s.style == "b":
                s.swarm(self, t, dt, src)
            elif fresh:
                s.glow_a(src, w)
            bx0, by0, bx1, by1 = s.bbox
            box = [min(box[0], bx0 - 3), min(box[1], by0 - 2), max(box[2], bx1 + 3), max(box[3], by1 + 2)]
            if s.scale > 0.92 and abs(s.head[0] - w / 2) < 0.25 * w and t >= max(s.next_swell, self.next_swell):
                audio.sfx("sharkpass", min(0.9, 0.45 + 2.0 * (s.scale - 0.92)))
                s.next_swell, self.next_swell = t + 16, t + 9
        if fresh:
            self.halo = self.blur_halo(src, box) if box[2] >= 0 else ()
        if self.halo:
            self.paint_halo(cv, shift)
        self.snow.draw(cv, sea, t, 0)
        # mid-depth snow and the fish school go between the sharks behind them and in front
        layers = [(self.zof(0.55), lambda: self.snow.draw(cv, sea, t, 1))]
        if self.school:
            layers.append((self.zof(0.5), lambda: self.school.draw(cv, sea, t)))
        for s in order:
            while layers and s.Z < layers[0][0]:
                layers.pop(0)[1]()
            if s.bbox is None:
                continue
            if s.style == "a":
                s.draw_a(cv, sea, t)
            else:
                s.draw_b(cv, sea, shift, t)
        for _, draw in layers:
            draw()
        self.snow.draw(cv, sea, t, 2)

    def blur_halo(self, src, box):
        """Blur the bloom sources inside box at half resolution across; returns the blurred
        rows with their top-left cell."""
        w, h = self.w, self.h
        rx, ry = HALO_R
        x0, y0, x1, y1 = box
        x0, x1 = max(0, x0 - 6 * rx - 2) & ~1, min(w - 1, x1 + 6 * rx + 2)
        y0, y1 = max(0, y0 - 3 * ry), min(h - 1, y1 + 3 * ry)
        rows = []
        for y in range(y0, y1 + 1):
            r = src[y * w + x0:y * w + x1 + 1]
            if len(r) & 1:
                r.append(0.0)
            rows.append(list(map(add, r[0::2], r[1::2])))
        return blur(rows, rx, ry), x0, y0

    def paint_halo(self, cv, shift):
        """Tint the sea cells under the blurred halo."""
        g, x0, y0 = self.halo
        w = cv.w
        rx, ry = HALO_R
        k = 0.5 / ((2 * rx + 1) * (2 * ry + 1)) ** 3 * (NQ - 1) / 2
        thr = 2.0 / k   # level 1 is a ~1% tint: not worth the cells it touches
        sea, cells, hq = self.sea, cv.cells, self.hq
        top = NQ - 1
        n = len(g[0])
        full = [0.0] * (2 * n)
        for j, row in enumerate(g):
            full[0::2] = map(add, row, row)
            full[1::2] = map(add, row, row[1:] + [0.0])
            hot = [x for x, v in enumerate(full) if v > thr]
            if not hot:
                continue
            y = y0 + j
            lr, hl, hd = sea.levrows[y], sea.halo[y], sea.halod[y]
            dots = y % DOT_Y == 0
            crow = cells[y]
            base = y * w
            for x in hot:
                cx = x0 + x
                if cx >= w:
                    break
                q = int(full[x] * k)
                if q > top:
                    q = top
                # hold the last level through one-step wobbles: the halo looks the same and
                # far fewer cells need repainting as it slides along with the shark
                o = hq[base + cx]
                if o - 1 <= q <= o + 1:
                    q = o
                else:
                    hq[base + cx] = q
                i = lr[cx + shift] * NQ + q
                crow[cx] = hd[i] if dots and cx % DOT_X == 0 else hl[i]


def main():
    p = term.make_parser("3D sharks gliding through a deep sea, as tile mosaics or glyph swarms", fps=12)
    p.add_argument("--count", type=int, default=3, help="number of sharks, 1-6 (default 3)")
    p.add_argument("--style", choices=("a", "b", "mix"), default="mix",
                   help="a: tile mosaic with bloom, b: silhouette in a glyph swarm, mix: both (default)")
    p.add_argument("--seed", type=int, default=None, help="random seed")
    args = p.parse_args()
    sc = Scene(args)
    term.run(args, lambda cv, frame: sc.step(cv, frame, max(1.0, args.fps)), music="sharks")


if __name__ == "__main__":
    main()
