#!/usr/bin/env python3
"""Reef: a sunlit coral reef seen through layers of water.

God rays sway down from a rippling surface and caustics crawl over the sand; fog turns
far things blue and dim. Schools of small fish flock (boids) and flash silver as they
turn broadside; a few larger fish, drawn as solid tile mosaics, cruise the near layer;
kelp and anemones sway; bubbles rise from vents and pop at the surface. Now and then a
manta ray, a sea turtle or a far-off whale glides through.

Usage: python3 reef.py [--fps 12] [--frames N] [--seed N] [--visitor KIND] [--mute]
  --visitor KIND   manta, turtle or whale: bring that visitor on screen at once
                   (otherwise one drifts by every minute or so)
"""

META = {'name': 'reef',
 'kind': 'watch',
 'blurb': 'A sunlit reef: god rays, flocking schools that flash silver, swaying kelp and rare visitors',
 'credit': [{'type': 'inspired by',
             'who': 'asciiquarium by Kirk Baucom',
             'url': 'https://robobunny.com/projects/asciiquarium/html/'},
            {'type': 'inspired by',
             'who': 'Craig Reynolds, Boids (flocking)',
             'url': 'https://www.red3d.com/cwr/boids/'},
            {'type': 'inspired by',
             'who': 'Steven Worley, A Cellular Texture Basis Function (caustics)',
             'url': 'https://dl.acm.org/doi/10.1145/237170.237267'}]}

import math
import os
import random
import sys
from operator import add

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

from fun import audio, term

TAU = 2 * math.pi
UP, DN, LH, RH = "▀", "▄", "▌", "▐"

# Water by depth (0 surface .. 1 bottom row), the light the rays add, and the haze that
# far silhouettes, the vignette and the whale fade the water toward.
WATER = ((0.0, (54, 166, 176)), (0.15, (28, 128, 152)), (0.42, (14, 80, 120)),
         (0.72, (8, 48, 88)), (1.0, (6, 30, 62)))
RAY = (182, 242, 230)
HAZE = (4, 18, 40)
SURFACE = ((96, 196, 204), (150, 224, 226), (200, 246, 240), (236, 255, 250))
SAND = (214, 196, 156)
CAUSTIC = (236, 255, 240)
CAUSTIC_K = (0.0, 0.08, 0.18, 0.3, 0.42, 0.54, 0.66)  # by summed network level 0..6
Q = 10        # ray light levels
QB = Q + 3    # LUT entries per haze level; the top three are surface shimmer
M = 8         # haze levels
MID_FOG, NEAR_FOG, FAR_FOG = 0.42, 0.06, 0.66

KELP_MID = (70, 140, 104)
KELP_NEAR = (30, 74, 58)
ROCK = (136, 136, 128)
CORAL = ((236, 122, 128), (242, 152, 96), (232, 170, 146))  # pink, orange, peach

# Feature-fish pixel codes.
BODY, DARK, LIGHT, FIN, FINDARK, EYE, ACCENT = 1, 2, 3, 4, 5, 6, 7
SOLID = (BODY, DARK, LIGHT, ACCENT)


def put_pixels(cells, px, w, h):
    """Draw half-row pixels {(x, py): colour} as half blocks over the live background."""
    get = px.get
    for x, y in {(x, py >> 1) for x, py in px}:
        if 0 <= x < w and 0 <= y < h:
            a, b = get((x, 2 * y)), get((x, 2 * y + 1))
            row = cells[y]
            if a and b:
                row[x] = (UP, a, b)
            elif a:
                row[x] = (UP, a, row[x][2])
            else:
                row[x] = (DN, b, row[x][2])


def mix(a, b, t):
    return (int(a[0] + (b[0] - a[0]) * t + 0.5), int(a[1] + (b[1] - a[1]) * t + 0.5),
            int(a[2] + (b[2] - a[2]) * t + 0.5))


def mul(a, k):
    k = max(0.0, k)
    return (min(255, int(a[0] * k + 0.5)), min(255, int(a[1] * k + 0.5)), min(255, int(a[2] * k + 0.5)))


def grad(stops, u):
    u = min(1.0, max(0.0, u))
    for (p0, c0), (p1, c1) in zip(stops, stops[1:]):
        if u <= p1:
            return mix(c0, c1, (u - p0) / (p1 - p0))
    return stops[-1][1]


def smooth(e0, e1, x):
    t = min(1.0, max(0.0, (x - e0) / (e1 - e0)))
    return t * t * (3 - 2 * t)


def in_tri(u, v, a, b, c):
    d1 = (u - b[0]) * (a[1] - b[1]) - (a[0] - b[0]) * (v - b[1])
    d2 = (u - c[0]) * (b[1] - c[1]) - (b[0] - c[0]) * (v - c[1])
    d3 = (u - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (v - a[1])
    return not ((d1 < 0 or d2 < 0 or d3 < 0) and (d1 > 0 or d2 > 0 or d3 > 0))


def seg_dist(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    k = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy or 1)))
    return math.hypot(px - ax - dx * k, py - ay - dy * k), k


# ------------------------------------------------------------------ creature shapes
# Each maps body coordinates (u 0 nose .. 1 tail, v -1 top .. 1 bottom) and a pose
# (tail beat, wing flap or stroke phase, in radians) to a pixel code, 0 for empty.

def shape_angel(u, v, pose):
    e = ((u - 0.35) / 0.3) ** 2 + (v / 0.4) ** 2
    if e <= 1.0:
        for s in (0.17, 0.41, 0.6):
            if abs(u - s) < 0.045:
                return DARK
        return LIGHT if v > 0.18 else BODY
    if in_tri(u, v, (0.18, -0.34), (0.76, -1.0), (0.6, -0.22)) or in_tri(u, v, (0.24, 0.34), (0.8, 1.0), (0.6, 0.22)):
        return FINDARK if abs(u - 0.6) < 0.045 or abs(u - 0.41) < 0.045 or abs(v) > 0.9 else FIN
    if 0.62 <= u <= 0.95 and abs(v) <= 0.06 + 0.3 * (u - 0.62) / 0.33:
        return FINDARK if u > 0.9 else FIN
    return 0


def shape_tang(u, v, pose):
    e = ((u - 0.42) / 0.4) ** 2 + (v / 0.78) ** 2
    if e <= 1.0:
        c = -0.22 + 0.42 * (u - 0.15)
        if 0.14 < u < 0.74 and abs(v - c) < 0.15 + 0.08 * math.sin(u * 9):
            return DARK
        if ((u - 0.5) / 0.15) ** 2 + ((v + 0.5) / 0.2) ** 2 <= 1:
            return DARK
        if 0.3 < u < 0.42 and 0.15 < v < 0.55:
            return ACCENT
        return BODY
    if v < 0 and e <= 1.28 and 0.22 < u < 0.82:
        return FINDARK
    if v > 0 and e <= 1.2 and 0.35 < u < 0.8:
        return FINDARK
    if 0.76 <= u <= 0.86 and abs(v) < 0.24:
        return ACCENT
    if 0.84 <= u <= 1.0:
        k = (u - 0.84) / 0.16
        if abs(v) < 0.22 + 0.62 * k and not (u > 0.95 and abs(v) < 0.4 * (u - 0.95) / 0.05):
            return ACCENT
    return 0


def shape_clown(u, v, pose):
    e = ((u - 0.42) / 0.4) ** 2 + (v / 0.76) ** 2
    if e <= 1.0:
        for s, wd in ((0.24, 0.07), (0.53, 0.075)):
            d = abs(u - s)
            if d < wd:
                return LIGHT
            if d < wd + 0.045:
                return DARK
        return BODY
    if e <= 1.4 and ((v < 0 and 0.2 < u < 0.78) or (v > 0 and 0.32 < u < 0.66)):
        return FINDARK if e > 1.25 else FIN
    if 0.78 <= u <= 0.99 and abs(v) < 0.26 + 0.5 * (u - 0.78) / 0.21:
        if u < 0.84:
            return LIGHT
        return FINDARK if u > 0.93 else FIN
    return 0


def shape_manta(u, v, pose):
    span = 0.86 + 0.14 * math.sin(pose)
    a = abs(v) / span
    a -= 0.12 * math.cos(pose) * a * a  # the tips lag the flap
    if u < 0.09:
        return BODY if u > 0.01 and 0.1 < abs(v) < 0.24 else 0  # cephalic lobes
    if u > 0.66:
        return DARK if 0 < v < 0.06 and u < 0.99 else 0
    lead = 0.2 + 0.8 * math.sin(min(1.0, (u - 0.09) / 0.5) * math.pi / 2)
    trail = 0.66 if a < 0.14 else 0.46 + 0.16 * ((a - 0.14) / 0.86) ** 1.6  # tips swept back
    if a > lead or u > trail:
        return 0
    if a > lead - 0.08 and u < 0.5:
        return ACCENT
    if u > trail - 0.03 or a > 0.93:
        return DARK
    if 0.15 < u < 0.32 and 0.26 < a < 0.5:
        return LIGHT  # pale shoulder patches
    return BODY


def shape_turtle(u, v, pose):
    lx, ly = u * 26, v * 10  # roughly square units: columns and half-rows
    du, dv = (u - 0.52) / 0.34, (v - 0.22) / 0.95
    e = du * du + dv * dv
    if e <= 1.0 and v <= 0.22:
        # Scutes: a vertebral ring, costal plates split radially, and a pale marginal rim.
        if e > 0.8:
            return LIGHT if (math.atan2(dv, du) * 7) % 1.0 > 0.15 else DARK
        if abs(e - 0.42) < 0.06:
            return DARK
        th = math.atan2(dv, du) * (3 if e < 0.42 else 5) / math.pi
        return DARK if th % 1.0 < 0.12 else BODY
    if 0.22 < v <= 0.36 and ((u - 0.52) / 0.3) ** 2 < 1:
        return ACCENT
    if ((u - 0.1) / 0.09) ** 2 + ((v - 0.1) / 0.22) ** 2 <= 1 or ((u - 0.19) / 0.08) ** 2 + ((v - 0.18) / 0.16) ** 2 <= 1:
        return FIN
    ang = 0.85 + 0.5 * math.sin(pose)
    d, k = seg_dist(lx, ly, 0.32 * 26, 0.3 * 10, 0.32 * 26 + 9.0 * math.cos(ang), 0.3 * 10 + 9.0 * math.sin(ang))
    if d < 1.8 - 1.2 * k:
        return FIN
    ang2 = 0.6 + 0.35 * math.sin(pose + 1.4)
    d, k = seg_dist(lx, ly, 0.8 * 26, 0.3 * 10, 0.8 * 26 + 4.0 * math.cos(ang2), 0.3 * 10 + 4.0 * math.sin(ang2))
    if d < 1.3 - 0.7 * k:
        return FIN
    return 0


def shape_whale(u, v, pose):
    v -= 0.2 * math.sin(pose) * max(0.0, (u - 0.5) / 0.5) ** 2
    if u < 0.88:
        d = 0.5 * (u / 0.3) ** 0.5 if u < 0.3 else max(0.07, 0.5 * (1 - ((u - 0.3) / 0.6) ** 1.5))
        c = 0.08 * (1 - min(1.0, u / 0.3))
        if c - d * 0.8 <= v <= c + d:
            return BODY
        if seg_dist(u * 64, v * 13, 0.24 * 64, 0.35 * 13, 0.42 * 64, 1.0 * 13)[0] < 1.6:
            return BODY
        return 0
    k = (u - 0.88) / 0.12
    return BODY if abs(v) < 0.07 + 0.85 * k ** 1.5 and not (k > 0.75 and abs(v) < 0.3 * (k - 0.75) / 0.25) else 0


# Species: shape, size (columns, half-row pixels), palette code -> (colour, extra fog),
# texture glyph for body tiles, swim speed and tail-beat rate.
SPECIES = {
    "angel": dict(shape=shape_angel, L=16, H=26, speed=2.4, beat=3.0, amp=0.2, tex="(", eye=(0.11, -0.1),
                  pal={BODY: ((214, 218, 206), 0), DARK: ((34, 38, 48), 0), LIGHT: ((232, 226, 196), 0),
                       FIN: ((170, 188, 200), 0.3), FINDARK: ((40, 46, 58), 0.12), EYE: ((14, 16, 24), 0)}),
    "tang": dict(shape=shape_tang, L=16, H=11, speed=3.6, beat=4.2, amp=0.22, tex="(", eye=(0.12, -0.2),
                 pal={BODY: ((44, 104, 214), 0), DARK: ((14, 20, 46), 0), ACCENT: ((248, 206, 64), 0),
                      FINDARK: ((22, 34, 80), 0.1), EYE: ((10, 10, 20), 0)}),
    "clown": dict(shape=shape_clown, L=10, H=7, speed=2.0, beat=6.0, amp=0.25, eye=(0.1, -0.15),
                  pal={BODY: ((246, 122, 40), 0), DARK: ((24, 18, 20), 0), LIGHT: ((246, 244, 236), 0),
                       FIN: ((246, 140, 60), 0.15), FINDARK: ((30, 22, 24), 0.1), EYE: ((10, 10, 14), 0)}),
}
VISITORS = {
    "manta": dict(shape=shape_manta, L=26, H=36, speed=3.0, beat=0.9, fog=MID_FOG - 0.08,
                  pal={BODY: ((40, 54, 76), 0), DARK: ((22, 30, 46), 0), LIGHT: ((132, 152, 168), 0),
                       ACCENT: ((96, 120, 140), 0)}),
    "turtle": dict(shape=shape_turtle, L=26, H=20, speed=2.2, beat=1.3, fog=0.2, eye=(0.07, 0.05),
                   pal={BODY: ((146, 114, 62), 0), DARK: ((66, 48, 28), 0), LIGHT: ((186, 156, 96), 0),
                        ACCENT: ((218, 200, 150), 0), FIN: ((150, 150, 118), 0), EYE: ((14, 14, 14), 0)}),
    "whale": dict(shape=shape_whale, L=64, H=26, speed=2.0, beat=0.5),
}


def raster(spec, sx, parity, pose, bend, fog):
    """Pixel-sample a creature into cell entries (dx, dy, ch, fg, fg_fog, bg, bg_fog, kind):
    kind 0 is a solid tile, 1 an upper half block and 2 a lower one over whatever is below.
    sx in -1..1 is the facing and the squash of a turn; parity shifts it down half a row."""
    shape, L, H, pal, tex = spec["shape"], spec["L"], spec["H"], spec["pal"], spec.get("tex")
    sxa = max(0.18, abs(sx))
    sgn = 1 if sx >= 0 else -1
    rows = (H + parity + 1) // 2
    lit = 0.55 + 0.45 * sxa
    px = []
    for j in range(rows * 2):
        jj = j - parity
        v = (jj + 0.5) / H * 2 - 1
        line = []
        for i in range(L):
            if jj < 0 or jj >= H:
                line.append(None)
                continue
            u = 0.5 - sgn * ((i + 0.5) / L * 2 - 1) / sxa / 2
            if u < 0 or u > 1:
                line.append(None)
                continue
            code = shape(u, v - bend * max(0.0, u - 0.45) ** 2 * 3.3, pose)
            if not code:
                line.append(None)
                continue
            col, f = pal[code]
            if code in SOLID:
                col = mul(col, (1.1 - 0.12 * v - 0.22 * v * v) * lit)
            line.append((code, col, f + fog))
        px.append(line)
    eye = None
    if "eye" in spec:
        eu, ev = spec["eye"]
        xr = (0.5 - eu) * 2 * sgn * sxa
        eye = (int((xr + 1) / 2 * L), int(((ev + 1) / 2 * H + parity)) // 2)
    out = []
    for cy in range(rows):
        top, bot = px[2 * cy], px[2 * cy + 1]
        for i in range(L):
            a, b = top[i], bot[i]
            if a is None and b is None:
                continue
            if (i, cy) == eye and a and b:
                body = a if a[0] in SOLID else b
                out.append((i, cy, "●", pal[EYE][0], fog, body[1], body[2], 0))
            elif a and b:
                if a[0] == b[0] and a[0] in SOLID:
                    bg = mix(a[1], b[1], 0.5)
                    ch = tex if tex and a[0] == BODY and (i + cy) % 2 == 0 else " "
                    if ch == "(" and sgn < 0:
                        ch = ")"
                    out.append((i, cy, ch, mul(bg, 0.86), a[2], bg, a[2], 0))
                else:
                    out.append((i, cy, UP, a[1], a[2], b[1], b[2], 0))
            elif a:
                out.append((i, cy, UP, a[1], a[2], None, 0, 1))
            else:
                out.append((i, cy, DN, b[1], b[2], None, 0, 2))
    return out


# ------------------------------------------------------------------ flocking schools

class School:
    """Boids in (x columns, y half-rows, z depth): cohesion and alignment against the
    school's centre and mean heading, separation through a spatial hash, and a slowly
    wandering target whose z swings make the school turn edge-on and back."""

    def __init__(self, rng, n, w, y0, y1, vmax, far):
        self.rng, self.w, self.y0, self.y1, self.vmax, self.far = rng, w, y0, y1, vmax, far
        cx, cy = rng.uniform(w * 0.2, w * 0.8), rng.uniform(y0 + 4, max(y0 + 5, y1 - 4))
        d = rng.choice((-1, 1))
        self.f = [[cx + rng.gauss(0, 4), cy + rng.gauss(0, 3), rng.gauss(0, 2),
                   d * vmax * 0.7, rng.gauss(0, 0.3), rng.gauss(0, 0.3), rng.random()] for _ in range(n)]
        self.ph = [rng.random() * TAU for _ in range(4)]
        self.rate = rng.uniform(0.8, 1.2)
        self.dash = 0.0

    def target(self, t):
        p, r, w = self.ph, self.rate, self.w
        tx = w * (0.5 + 0.42 * math.sin(t * 0.045 * r + p[0]) + 0.08 * math.sin(t * 0.13 * r + p[1]))
        mid, amp = (self.y0 + self.y1) / 2, (self.y1 - self.y0) * 0.35
        ty = mid + amp * math.sin(t * 0.07 * r + p[2])
        tz = 5.0 * math.sin(t * 0.11 * r + p[3])
        return tx, ty, tz

    def step(self, dt, t):
        f, n = self.f, len(self.f)
        tx, ty, tz = self.target(t)
        if self.dash <= 0 and self.rng.random() < dt / 25:
            self.dash = 2.5  # a sudden collective swerve
        self.dash -= dt
        cx = sum(p[0] for p in f) / n
        cy = sum(p[1] for p in f) / n
        cz = sum(p[2] for p in f) / n
        mvx = sum(p[3] for p in f) / n
        mvy = sum(p[4] for p in f) / n
        mvz = sum(p[5] for p in f) / n
        if self.dash > 0:
            tx, tz = cx - (tx - cx), -tz
        dx, dy, dz = tx - cx, ty - cy, tz - cz
        dn = math.sqrt(dx * dx + dy * dy + dz * dz) or 1.0
        seek = 2.2 if self.dash <= 0 else 5.0
        gx, gy, gz = dx / dn * seek, dy / dn * seek, dz / dn * seek
        grid = {}
        for p in f:
            k = (int(p[0] * 0.5), int(p[1] * 0.5))
            if k in grid:
                grid[k].append(p)
            else:
                grid[k] = [p]
        vmax, vmin = self.vmax, self.vmax * 0.45
        y0, y1 = self.y0, self.y1
        for p in f:
            x, y, z, vx, vy, vz = p[0], p[1], p[2], p[3], p[4], p[5]
            sx = sy = sz = 0.0
            kx, ky = int(x * 0.5), int(y * 0.5)
            for ox in (kx - 1, kx, kx + 1):
                for oy in (ky - 1, ky, ky + 1):
                    cell = grid.get((ox, oy))
                    if cell is None:
                        continue
                    for q in cell:
                        ex, ey, ez = x - q[0], y - q[1], z - q[2]
                        d2 = ex * ex + ey * ey + ez * ez
                        if 1e-6 < d2 < 4.0:
                            sx += ex / d2
                            sy += ey / d2
                            sz += ez / d2
            ax = (cx - x) * 0.35 + (mvx - vx) * 1.2 + sx * 3.0 + gx
            ay = (cy - y) * 0.35 + (mvy - vy) * 1.2 + sy * 3.0 + gy
            az = (cz - z) * 0.35 + (mvz - vz) * 1.2 + sz * 3.0 + gz
            if y < y0:
                ay += (y0 - y) * 3.0
            elif y > y1:
                ay -= (y - y1) * 3.0
            vx += ax * dt
            vy += ay * dt
            vz += az * dt
            s = math.sqrt(vx * vx + vy * vy + vz * vz) or 1.0
            k = vmax / s if s > vmax else vmin / s if s < vmin else 1.0
            vx, vy, vz = vx * k, vy * k * 0.8, vz * k
            p[0], p[1], p[2], p[3], p[4], p[5] = x + vx * dt, y + vy * dt, z + vz * dt, vx, vy, vz


# ------------------------------------------------------------------ the scene

class Reef:
    def __init__(self, w, h, rng, visitor=None):
        self.w, self.h, self.rng = w, h, rng
        self.t = 0.0
        self._tint = {}
        self._sprites = {}
        self._lit = {}
        # Creatures scale with the screen; one table holds fish and visitors alike.
        k = self.k = min(1.25, max(0.55, min(w / 120, h / 40)))
        self.spec = {name: dict(v, L=max(6, round(v["L"] * k)), H=max(5, round(v["H"] * k)),
                                speed=v["speed"] * max(0.7, k))
                     for name, v in list(SPECIES.items()) + list(VISITORS.items())}
        sb = max(3, round(h * 0.17))
        self.sand_row = h - sb
        self.water = [grad(WATER, y / max(1, h - 1)) for y in range(h)]
        self.light = [1.0 - 0.24 * y / max(1, h - 1) for y in range(h)]
        self.build_sand()
        self.build_water()
        self.build_caustics()
        self.build_props()
        self.build_life()
        self.visitor = None
        self.next_visitor = rng.uniform(35, 70)
        if visitor:
            self.spawn_visitor(visitor, True)
        self.pop_at = -1.0
        self.pops = []

    # ---------------------------------------------------------- colour helpers
    def tint(self, col, y, f):
        """col lit for row y and faded f of the way into that row's water."""
        key = (col, y, f)
        c = self._tint.get(key)
        if c is None:
            c = self._tint[key] = mix(mul(col, self.light[y]), self.water[y], min(1.0, f))
        return c

    # ---------------------------------------------------------- static layers
    def build_sand(self):
        w, h, rng = self.w, self.h, self.rng
        a, b = rng.random() * TAU, rng.random() * TAU
        base = 2 * self.sand_row
        self.sp = [base + int(round(1.3 * math.sin(x * 0.07 + a) + 0.8 * math.sin(x * 0.19 + b))) for x in range(w)]
        self.p0 = min(self.sp)
        span = max(1, 2 * h - self.p0)
        pal = []
        for py in range(self.p0, 2 * h):
            s = (py - self.p0) / span
            y = py >> 1
            fog = 0.62 - 0.3 * s
            row = []
            for x in range(w):
                n = math.sin(x * 12.9898 + py * 78.233) * 43758.5453
                n = (n - math.floor(n)) * 2 - 1
                patch = 0.5 * math.sin(x * 0.083 + py * 0.31 + a) + 0.5 * math.sin(x * 0.21 - py * 0.17 + b)
                rip = math.sin(py * 1.9 + 1.3 * math.sin(x * 0.1 + a) + x * 0.04)
                k = (0.84 + 0.22 * s) * (1 + 0.03 * patch + 0.022 * rip + 0.006 * n)
                c = mix(mul(SAND, k), mix(self.water[y], (64, 136, 150), 0.45), fog)
                ck = 0.75 + 0.25 * s
                row.append(tuple(mix(c, CAUSTIC, kk * ck) for kk in CAUSTIC_K))
            pal.append(row)
        self.sand_pal = pal
        # Texture row per sand pixel row: the grazing view flattens the far caustics.
        self.sand_trow = [int(1.6 * r - 0.25 * r * r / span) for r in range(2 * h - self.p0)]

    def build_water(self):
        w, h, rng = self.w, self.h, self.rng
        luts = []
        for y in range(h):
            u = y / max(1, h - 1)
            wy = self.water[y]
            rk = 0.44 * (1 - u) ** 1.5 + 0.05
            lut = []
            for m in range(M):
                base = mix(wy, HAZE, 0.62 * m / (M - 1))
                for q in range(QB):
                    k = rk * min(1.0, q / (Q - 1)) + 0.07 * max(0, q - Q + 1)
                    lut.append((" ", None, mix(base, RAY, min(0.9, k))))
            luts.append(lut)
        self.luts = luts
        # Rays fan out from a point above the surface; each cell looks up its bin.
        self.sun = w * rng.uniform(0.3, 0.55)
        self.sun_glow = [0.3 * max(0.0, 1 - abs(x - self.sun) / (w * 0.3)) ** 2 for x in range(w)]
        y0 = h * 0.9
        off = int(self.sun) + 8
        self.idx = [[max(0, int((x - self.sun) * y0 / (y + y0) + off)) for x in range(w)] for y in range(h)]
        self.nb = w + 20
        n = max(5, w // 12)
        self.shafts = [(rng.uniform(4, self.nb - 4), rng.uniform(1.0, 4.5), rng.uniform(0.35, 1.0),
                        rng.uniform(1.5, 5.0), rng.uniform(0.05, 0.16), rng.random() * TAU) for _ in range(n)]
        # Haze per cell (times QB): a soft side vignette plus the far reef silhouette.
        far = [[0.0] * w for _ in range(h)]
        hr = self.sand_row + 1
        ph = [rng.random() * TAU for _ in range(3)]
        domes = [(rng.uniform(0, w), rng.uniform(3, 8), rng.uniform(3, 10)) for _ in range(max(2, w // 25))]
        for x in range(w):
            top = hr - (4.5 + 2.2 * math.sin(x * 0.045 + ph[0]) + 1.2 * math.sin(x * 0.12 + ph[1])
                        + 0.5 * math.sin(x * 0.31 + ph[2]))
            for dx, dh, dw in domes:
                top = min(top, hr - dh * max(0.0, 1 - ((x - dx) / dw) ** 2) ** 0.5 - 4.0)
            for y in range(max(0, int(top) - 2), min(h, hr + 1)):
                cov = min(1.0, max(0.0, y + 1 - top))
                far[y][x] = max(far[y][x], 4.5 * cov + 1.5 * smooth(top - 3.0, top, y + 0.5) * (1 - cov))
        self.mrow = []
        for y in range(h):
            row = []
            for x in range(w):
                e = abs(x - w / 2) / (w / 2)
                vig = 2.2 * smooth(0.55, 1.05, e)
                row.append(min(M - 1, int(far[y][x] + vig + 0.5)) * QB)
            self.mrow.append(row)

    def build_caustics(self):
        """Two tileable Voronoi-edge networks (F2 - F1 small near cell borders), as
        brightness levels 0..3, each row repeated so a w-wide slice never wraps."""
        rng, w = self.rng, self.w
        tw, th, g = 84, 42, 14
        self.tw, self.th = tw, th
        gx, gy = tw // g, th // g
        reps = w // tw + 2
        sqrt, sin = math.sqrt, math.sin
        tex = []
        for _ in range(2):
            jit = {(i, j): ((i + rng.random()) * g, (j + rng.random()) * g) for i in range(gx) for j in range(gy)}
            # Each grid cell's 3x3 neighbourhood of feature points, unwrapped around it.
            near = {(ci, cj): [(jit[((ci + di) % gx, (cj + dj) % gy)][0] + ((ci + di) - (ci + di) % gx) * g,
                                jit[((ci + di) % gx, (cj + dj) % gy)][1] + ((cj + dj) - (cj + dj) % gy) * g)
                               for di in (-1, 0, 1) for dj in (-1, 0, 1)]
                    for ci in range(-1, gx + 1) for cj in range(-1, gy + 1)}
            rows = []
            for py in range(th):
                row = []
                for px in range(tw):
                    # A tileable warp bends the straight Voronoi borders into caustic curves.
                    wx = px + 1.6 * sin(py * TAU / th * 2 + g) + 0.5
                    wy = py + 1.6 * sin(px * TAU / tw * 3) + 0.5
                    d1 = d2 = 1e9
                    for qx, qy in near[(int(wx // g), int(wy // g))]:
                        d = (wx - qx) ** 2 + (wy - qy) ** 2
                        if d < d1:
                            d1, d2 = d, d1
                        elif d < d2:
                            d2 = d
                    v = max(0.0, 1 - (sqrt(d2) - sqrt(d1)) / 4.0) ** 1.8
                    row.append(min(3, int(v * 3.99)))
                rows.append(row * reps)
            tex.append(rows)
        self.ctex = tex

    def put_blob(self, px, solid, half, tex=None):
        """Pixel dict (x, py) -> (colour, material) into static cell entries: textured tiles
        where tex gives a glyph for both halves' material, half blocks elsewhere (over the
        live background when only one half is set)."""
        h, w = self.h, self.w
        for (x, y) in sorted({(x, py >> 1) for (x, py) in px}):
            if not (0 <= x < w and 0 <= y < h):
                continue
            a, b = px.get((x, 2 * y)), px.get((x, 2 * y + 1))
            if a and b:
                g = tex(x, y, a[1]) if tex and a[1] == b[1] else None
                if g is not None:
                    bg = mix(a[0], b[0], 0.5)
                    solid.append((x, y, (g, mul(bg, 1.14), bg)))
                else:
                    solid.append((x, y, (UP, a[0], b[0])))
            elif a:
                half.append((x, y, UP, a[0]))
            else:
                half.append((x, y, DN, b[0]))

    def rock(self, px, cx, rx, ry, col, fog, base, enc):
        """A lumpy top-lit boulder of half-row pixels, with coral crusts near the crown."""
        rng, w, h = self.rng, self.w, self.h
        c1, c2, skew = rng.random() * TAU, rng.random() * TAU, rng.uniform(-0.3, 0.3)
        crusts = [(cx + rng.uniform(-rx, rx) * 0.8, rng.uniform(0.0, 0.35), rng.uniform(0.8, 1.8), rng.choice(CORAL))
                  for _ in range(int(enc * rx))]
        for x in range(int(cx - rx) - 1, int(cx + rx) + 2):
            if not 0 <= x < w:
                continue
            d = (x + 0.5 - cx) / rx
            if abs(d) >= 1:
                continue
            hgt = ry * (1 - d * d) ** 0.5 * (1 + 0.1 * math.sin(x * 0.9 + c1) + 0.06 * math.sin(x * 2.3 + c2) + skew * d)
            b = base(x)
            top = int(b - hgt)
            for py in range(top, b + 1):
                yy = py >> 1
                if not 0 <= yy < h:
                    continue
                lv = min(1.0, (py - top) / max(1.0, hgt))
                mott = 0.07 * math.sin(x * 0.7 + py * 0.9 + c1) * math.sin(x * 0.31 - py * 0.5 + c2)
                k = (1.22 - 0.48 * lv - 0.16 * abs(d) + mott)
                c = mul(col, k)
                if py == top:
                    c = mix(c, RAY, 0.22)
                for ex, ev, er, ec in crusts:
                    if (x - ex) ** 2 + ((lv - ev) * hgt) ** 2 < er * er:
                        c = mul(ec, 1.05 - 0.5 * lv)
                        break
                px[(x, py)] = (self.tint(c, yy, fog), "rock")

    def staghorn(self, px, cx, hgt, col, fog, base_py):
        """Branching coral: forking strokes of pixels, tips lighter."""
        rng, w, h = self.rng, self.w, self.h
        stack = [(cx, float(base_py), -math.pi / 2 + rng.uniform(-0.2, 0.2), hgt * 0.4, 0)]
        while stack:
            x, y, a, ln, d = stack.pop()
            n = max(1, int(ln))
            for s in range(n + 1):
                xx, yy = x + math.cos(a) * s, y + math.sin(a) * s
                f = min(1.0, (base_py - yy) / max(1.0, hgt))
                c = mix(mul(col, 0.78 + 0.3 * f), (255, 232, 222), 0.35 if s >= n - 1 and d >= 2 else 0.0)
                xi, yi = int(round(xx)), int(round(yy))
                if 0 <= xi < w and 0 <= yi >> 1 < h:
                    px[(xi, yi)] = (self.tint(c, yi >> 1, fog), "coral")
                    if d == 0 and 0 <= xi + 1 < w:
                        px[(xi + 1, yi)] = (self.tint(mul(c, 0.86), yi >> 1, fog), "coral")
            x, y = x + math.cos(a) * ln, y + math.sin(a) * ln
            if d < 3:
                for da in (-0.55, 0.5):
                    stack.append((x, y, a + da + rng.uniform(-0.2, 0.2), ln * rng.uniform(0.6, 0.8), d + 1))

    def build_props(self):
        w, h, rng = self.w, self.h, self.rng
        self.back, self.back_half, self.back_dots = [], [], []
        self.front, self.front_half = [], []
        sp = self.sp

        def tex(x, y, mat):
            return ("≈" if (x + y) % 2 else "~") if mat == "brain" else None

        def brain(px, cx, rx, ry, col, fog, base):
            for x in range(int(cx - rx), int(cx + rx) + 1):
                d = (x + 0.5 - cx) / rx
                if not 0 <= x < w or abs(d) >= 1:
                    continue
                hgt = ry * (1 - d * d) ** 0.6
                b = base(x)
                for py in range(int(b - hgt), b + 1):
                    if 0 <= py >> 1 < h:
                        lv = (py - (b - hgt)) / max(1.0, hgt)
                        px[(x, py)] = (self.tint(mul(col, 1.15 - 0.45 * lv - 0.15 * abs(d)), py >> 1, fog), "brain")

        on_sand = lambda off: (lambda x: sp[x] + off)  # noqa: E731
        # Back row, faded into the water: rocks, brain corals, staghorn, braille sea fans.
        px = {}
        n = max(3, w // 22)
        slots = [(i + rng.uniform(0.2, 0.8)) / n * w for i in range(n)]
        rng.shuffle(slots)
        for i, cx in enumerate(slots):
            kind = i % 4
            if kind == 0 or kind == 2:
                rx = rng.uniform(3.5, 6)
                self.rock(px, cx, rx, rx * rng.uniform(1.1, 1.6), ROCK, MID_FOG, on_sand(1), 0.6)
                side = rng.choice((-1, 1))
                self.rock(px, cx + side * rx * 0.9, rx * 0.6, rx * 0.8, mul(ROCK, 0.92), MID_FOG, on_sand(1), 0.6)
            elif kind == 1:
                brain(px, cx, rng.uniform(2.5, 4), rng.uniform(3, 4.5), mul(CORAL[2], 0.92), MID_FOG, on_sand(1))
            else:
                self.staghorn(px, cx, rng.uniform(8, 12), CORAL[0], MID_FOG - 0.04, sp[int(cx) % w] + 1)
        self.put_blob(px, self.back, self.back_half, tex)
        for _ in range(max(1, w // 45)):
            self.sea_fan(rng.uniform(0.1, 0.9) * w, rng.uniform(6, 9), mul(CORAL[0], 0.95), MID_FOG - 0.05)
        # Front row: a big boulder with a brain coral at its foot, a staghorn and tube corals.
        px = {}
        bx = rng.choice((rng.uniform(0.12, 0.28), rng.uniform(0.72, 0.88))) * w
        self.rock(px, bx, rng.uniform(8, 11), rng.uniform(8, 11), mul(ROCK, 1.08), NEAR_FOG + 0.12, lambda x: 2 * h - 1, 0.7)
        brain(px, bx + rng.choice((-1, 1)) * rng.uniform(8, 10), rng.uniform(3.5, 5), rng.uniform(4, 5.5),
              CORAL[2], NEAR_FOG + 0.1, lambda x: 2 * h - 1)
        self.boulder = bx
        tx = bx + w * 0.42 if bx < w / 2 else bx - w * 0.42
        for k in range(rng.randint(4, 6)):
            x0 = int(tx + k * 2.2 + rng.uniform(-0.3, 0.3))
            hgt = rng.uniform(5, 12) * (1 - abs(k - 2.5) / 6)
            b = 2 * h - 1
            col = CORAL[1] if k % 2 else mul(CORAL[1], 0.9)
            for x in (x0, x0 + 1):
                if not 0 <= x < w:
                    continue
                side = 1.12 if x == x0 else 0.86
                top = int(b - hgt) + (1 if x == x0 + 1 else 0)
                for py in range(top, b + 1):
                    lv = (py - top) / max(1.0, hgt)
                    c = mul(col, (1.12 - 0.42 * lv) * side)
                    if py - top < 2:
                        c = mix(c, (255, 232, 206), 0.4)
                    px[(x, py)] = (self.tint(c, py >> 1, NEAR_FOG + 0.08), "tube")
        self.tube = tx
        sx = (bx + tx) / 2 + rng.uniform(-6, 6)
        self.staghorn(px, sx, rng.uniform(10, 13), CORAL[0], NEAR_FOG + 0.1, 2 * h - 1)
        self.put_blob(px, self.front, self.front_half)

    def sea_fan(self, cx, hgt, col, fog):
        """Braille sea fan rooted on the sand at column cx, about hgt rows tall."""
        rng, w, h = self.rng, self.w, self.h
        if not 0 <= int(cx) < w:
            return
        bits = {}
        base = self.sp[int(cx)] * 2  # braille rows are 4 per cell, sand pixels 2
        stack = [(cx * 2, base, -math.pi / 2, hgt * 4 * 0.32, 0)]
        while stack:
            x, y, a, ln, d = stack.pop()
            steps = int(ln) + 1
            for s in range(steps):
                xx, yy = x + math.cos(a) * s, y + math.sin(a) * s
                bx, by = int(xx), int(yy)
                if 0 <= bx < w * 2 and 0 <= by < h * 4:
                    k = (bx >> 1, by >> 2)
                    bits[k] = bits.get(k, 0) | (0x01, 0x08, 0x02, 0x10, 0x04, 0x20, 0x40, 0x80)[(by & 3) * 2 + (bx & 1)]
            x, y = x + math.cos(a) * ln, y + math.sin(a) * ln
            if d < 5:
                for da in (-0.45, 0.4):
                    stack.append((x, y, a + da + rng.uniform(-0.15, 0.15), ln * rng.uniform(0.62, 0.78), d + 1))
        for (x, y), b in bits.items():
            if 0 <= y < h:
                lv = 1 - min(1.0, (self.sand_row - y) / max(1.0, hgt))
                self.back_dots.append((x, y, chr(0x2800 + b), self.tint(mul(col, 1.1 - 0.3 * lv), y, fog)))

    def build_life(self):
        w, h, rng = self.w, self.h, self.rng
        sr = self.sand_row
        # Kelp: (base x, height rows, width, phase, amplitude, lean, colours by row, near?)
        self.kelp = []
        groups = [rng.uniform(0.2, 0.4) * w, rng.uniform(0.62, 0.85) * w]
        for g in groups:
            for _ in range(rng.randint(2, 4)):
                self.kelp.append(self.new_kelp(g + rng.uniform(-6, 6), rng.uniform(0.45, 0.75) * sr,
                                               rng.uniform(0.9, 1.3), False))
        for g in (rng.uniform(0.0, 0.08) * w, rng.uniform(0.9, 1.0) * w):
            for _ in range(2):
                self.kelp.append(self.new_kelp(g + rng.uniform(-3, 3), rng.uniform(0.7, 0.95) * h,
                                               rng.uniform(1.8, 2.6), True))
        # Anemone and its clownfish, away from the boulder.
        ax = self.boulder + (w * 0.3 if self.boulder < w / 2 else -w * 0.3)
        self.anemone = (ax, h - 1)
        self.tent = [((k / 21 - 0.5) * 2.3 + rng.uniform(-0.05, 0.05), rng.uniform(7, 11), rng.random() * TAU)
                     for k in range(22)]
        # Two tones, alternating by tentacle, so neighbouring strands stay apart.
        self.tent_cols = []
        for k in (1.0, 0.78):
            cols = [self.tint(mul(mix((238, 200, 176), (238, 110, 146), i / 9), k), h - 3, NEAR_FOG) for i in range(10)]
            self.tent_cols.append(cols + [self.tint(mul((255, 196, 214), k), h - 3, NEAR_FOG)])
        # Schools: one far, one or two mid.
        top = 3
        self.far_school = School(rng, max(12, w // 5), w, top * 2 + 4, (sr - 5) * 2, 4.0, True)
        self.schools = [School(rng, max(16, min(60, w * h // 110)), w, top * 2 + 2, (sr - 3) * 2, 7.5, False)]
        if w >= 90:
            self.schools.append(School(rng, max(12, w // 4), w, top * 2 + 6, (sr - 6) * 2, 6.5, False))
        self.school_luts = {}
        # Feature fish.
        self.fish = []
        a = rng.uniform(0.2, 0.35)
        for kind, slot in (("angel", a), ("tang", a + rng.uniform(0.3, 0.45))):
            self.fish.append(self.new_fish(kind, slot))
        self.clown = dict(kind="clown", x=ax - 6, y=float(h - 8), sx=1.0, turn=0.0, tail=0.0, tx=ax, ty=h - 8.0,
                          dir=1, bubble=rng.uniform(5, 12))
        # Bubble vents and live bubbles [x, y (rows), vy, size, phase].
        self.vents = [[rng.uniform(0.08, 0.92) * w, rng.uniform(1, 6), 0, 0.0] for _ in range(max(2, w // 45))]
        self.bubbles = []

    def new_kelp(self, x, hgt, width, near):
        """A strand as per-row constants: draw_kelp only adds the travelling sway."""
        h, rng = self.h, self.rng
        n = max(3, int(hgt))
        base = h - 1 if near else self.sand_row + 1
        ph, amp = rng.random() * TAU, rng.uniform(1.2, 2.6) * (1.3 if near else 1)
        lean, om = rng.uniform(-2, 2), rng.uniform(0.5, 0.8)
        col, fog = (KELP_NEAR, NEAR_FOG) if near else (KELP_MID, MID_FOG)
        bulb = self.tint((150, 142, 76), max(0, base - n // 2), fog)
        blen, bw = (9, 1.3) if near else (5, 1.0)
        steps = [(math.cos(0.1 * j), math.sin(0.1 * j), math.cos(0.1 * (j + 1)), math.sin(0.1 * (j + 1)),
                  bw * math.sin(math.pi * (j + 0.7) / (blen + 0.4))) for j in range(blen)]
        rows = []
        for r in range(n):
            y = base - r
            if not 0 <= y < h:
                continue
            f = r / n
            body = mul(col, 0.8 + 0.5 * f)
            c = self.tint(body, y, fog)
            hi, lo = self.tint(mul(body, 1.35), y, fog), self.tint(mul(body, 0.7), y, fog)
            blade = None
            if r % 5 == 2 and r < n - 2:
                # A blade on alternating sides, streaming up and out with the current.
                blade = (1 if (r // 5) % 2 else -1, r * 0.7 + ph, steps, r % 10 == 2)
            rows.append((y, lean * f, amp * f ** 1.4, r * 0.32, 0.5 * amp * f * f, r * 0.6,
                         width * (0.5 if r < n - 2 else 0.32), c, hi, lo, (" ", None, c), ("│", hi, c), blade))
        return dict(x=x, ph=ph, om=om, rows=rows, near=near, vein=near and width > 1.6, bulb=bulb)

    def free_y(self, sp, me=None):
        """A swimming depth for a feature fish, the best of a few tries at staying clear of the others."""
        rng = self.rng
        hi = max(4.0, self.sand_row - sp["H"] / 2 - 3)
        others = [f["ty"] for f in getattr(self, "fish", ()) if f is not me]
        tries = [rng.uniform(3, hi) for _ in range(5)]
        return max(tries, key=lambda y: min([abs(y - o) for o in others] or [0]))

    def new_fish(self, kind, slot=None):
        """slot (0..1 across the screen) places a fish on screen; otherwise it swims in from a side."""
        rng, w = self.rng, self.w
        sp = self.spec[kind]
        d = rng.choice((-1, 1))
        x = w * slot - sp["L"] / 2 if slot is not None else (-sp["L"] - 2 if d > 0 else w + 2)
        y = self.free_y(sp)
        return dict(kind=kind, x=x, y=y, dir=d, sx=float(d), turn=0.0, tail=rng.random() * TAU,
                    ty=y, wait=0.0, bubble=rng.uniform(4, 12), speed=sp["speed"] * rng.uniform(0.8, 1.2))

    def spawn_visitor(self, kind, on_screen=False):
        """Start a visitor at a side, or (on_screen) wherever the feature fish crowd it least."""
        rng, w, h = self.rng, self.w, self.h
        v = self.spec[kind]
        d = rng.choice((-1, 1))
        if kind == "whale":
            ys = [max(1.0, self.sand_row * 0.38 - v["H"] / 4)]
        elif kind == "manta":
            ys = [max(1.0, h * k) for k in (0.08, 0.16, 0.24)]
        else:
            ys = [max(1.0, h * k) for k in (0.25, 0.35, 0.45)]
        fish = [(f["x"] + self.spec[f["kind"]]["L"] / 2, f["y"] + self.spec[f["kind"]]["H"] / 4) for f in self.fish]

        def room(p):
            cx, cy = p[0] + v["L"] / 2, p[1] + v["H"] / 4
            return min([abs(cx - fx) / 2 + abs(cy - fy) for fx, fy in fish] or [0])
        if on_screen:
            x, y = max(((w * c - v["L"] / 2, y) for c in (0.3, 0.5, 0.7) for y in ys), key=room)
        else:
            x, y = (-v["L"] - 1 if d > 0 else w + 1), rng.choice(ys)
        self.visitor = dict(kind=kind, x=x, y=y, dir=d, pose=0.0, called=False)

    def sprite(self, key, make):
        s = self._sprites.get(key)
        if s is None:
            if len(self._sprites) > 3000:
                self._sprites.clear()
            s = self._sprites[key] = make()
        return s

    # ---------------------------------------------------------- per frame
    def frame(self, cv, dt):
        self.t += dt
        t, w, h = self.t, self.w, self.h
        cells = cv.cells
        color = term.COLOR
        self.update(dt)

        # Water: one ray bin per cell, haze per cell, shimmer near the surface.
        nb = self.nb
        rays = [0.0] * nb
        for c0, sw, a, amp, om, ph in self.shafts:
            c = c0 + amp * math.sin(t * om + ph)
            a *= 0.75 + 0.25 * math.sin(t * om * 2.3 + ph * 1.7)
            r = sw * 1.8
            for b in range(max(0, int(c - r)), min(nb, int(c + r) + 2)):
                d = (b - c) / r
                if d * d < 1:
                    rays[b] += a * (1 - d * d) ** 2
        rq = [min(Q - 1, int(v * (Q - 1) + 0.5)) for v in rays]
        mrow = self.mrow
        whale = self.visitor if self.visitor and self.visitor["kind"] == "whale" else None
        if whale:
            mrow = self.whale_haze(whale)
        tex1, tex2 = self.ctex
        tw, th = self.tw, self.th
        o1x, o1y = int(t * 2.0) % tw, int(t * 0.8) % th
        o2x, o2y = int(-t * 1.5) % tw, int(t * 1.2) % th
        luts, idx = self.luts, self.idx
        shimmer_rows = min(3, self.sand_row - 2)
        for y in range(h):
            lut, mr = luts[y], mrow[y]
            if 1 <= y <= shimmer_rows:
                c1 = tex1[(y * 2 + o1y) % th][o1x:o1x + w]
                c2 = tex2[(y * 2 + o2y) % th][o2x:o2x + w]
                k = shimmer_rows + 1 - y
                cells[y] = [lut[min(QB - 1, rq[i] + ((a + b) * k) // 6) + m] for i, m, a, b in zip(idx[y], mr, c1, c2)]
            else:
                cells[y] = [lut[rq[i] + m] for i, m in zip(idx[y], mr)]

        if color:
            self.draw_school(cells, self.far_school)
        self.draw_sand(cells, o1x, o1y, o2x, o2y)
        for k in self.kelp:
            if not k["near"]:
                self.draw_kelp(cells, k, t)
        for x, y, cell in self.back:
            cells[y][x] = cell
        for x, y, ch, fg in self.back_half:
            row = cells[y]
            row[x] = (ch, fg, row[x][2])
        for x, y, ch, fg in self.back_dots:
            row = cells[y]
            row[x] = (ch, fg, row[x][2])
        vis = self.visitor
        if vis and vis["kind"] == "manta":
            self.draw_visitor(cells, vis)
        for s in self.schools:
            self.draw_school(cells, s)
        if vis and vis["kind"] == "turtle":
            self.draw_visitor(cells, vis)
        for f in self.fish:
            self.draw_fish(cells, f)
        for x, y, cell in self.front:
            cells[y][x] = cell
        for x, y, ch, fg in self.front_half:
            row = cells[y]
            row[x] = (ch, fg, row[x][2])
        self.draw_fish(cells, self.clown)
        self.draw_anemone(cells, t)  # tentacles in front: the clownfish nestles among them
        for k in self.kelp:
            if k["near"]:
                self.draw_kelp(cells, k, t)
        self.draw_bubbles(cells, t)
        if color:
            self.draw_surface(cells, t)

    def update(self, dt):
        t, w, rng = self.t, self.w, self.rng
        self.far_school.step(dt, t)
        for s in self.schools:
            s.step(dt, t)
        for i, f in enumerate(self.fish):
            self.swim(f, dt)
            sp = self.spec[f["kind"]]
            if (f["dir"] > 0 and f["x"] > w + 2) or (f["dir"] < 0 and f["x"] < -sp["L"] - 2):
                f["wait"] += dt
                if f["wait"] > 4:
                    others = {g["kind"] for g in self.fish if g is not f}
                    self.fish[i] = self.new_fish(rng.choice([k for k in ("angel", "tang") if k not in others] or ["tang"]))
        self.swim_clown(dt)
        self.move_bubbles(dt)
        # Vents puff bursts of bubbles.
        for v in self.vents:
            v[1] -= dt
            if v[1] <= 0 and v[2] == 0:
                v[2] = rng.randint(4, 9)
                v[3] = 0.0
                if rng.random() < 0.6:
                    audio.sfx("gurgle", 0.18)
            if v[2] > 0:
                v[3] -= dt
                if v[3] <= 0:
                    x = int(v[0]) % w
                    self.add_bubble(v[0] + rng.uniform(-0.4, 0.4), self.sp[x] / 2 - 0.5, rng.uniform(0.2, 0.6))
                    v[2] -= 1
                    v[3] = rng.uniform(0.12, 0.35)
                    if v[2] == 0:
                        v[1] = rng.uniform(3, 9)
        # Visitors.
        vis = self.visitor
        if vis is None:
            self.next_visitor -= dt
            if self.next_visitor <= 0:
                self.spawn_visitor(rng.choice(("manta", "turtle", "whale")))
                self.next_visitor = rng.uniform(45, 90)
        else:
            v = self.spec[vis["kind"]]
            vis["x"] += vis["dir"] * v["speed"] * dt
            vis["pose"] += v["beat"] * dt * TAU / 4
            vis["y"] += math.sin(t * 0.2) * 0.15 * dt
            if vis["kind"] == "whale" and not vis["called"]:
                cx = vis["x"] + v["L"] / 2
                if w * 0.25 < cx < w * 0.75:
                    vis["called"] = True
                    audio.sfx("whalecall", 0.5)
            if (vis["dir"] > 0 and vis["x"] > w + 1) or (vis["dir"] < 0 and vis["x"] < -v["L"] - 1):
                self.visitor = None

    def swim(self, f, dt):
        sp = self.spec[f["kind"]]
        rng, w = self.rng, self.w
        f["tail"] += sp["beat"] * dt * (1.6 if f["turn"] > 0 else 1.0)
        if f["turn"] > 0:
            f["turn"] -= dt / 1.4
            k = max(0.0, f["turn"])
            f["sx"] = -f["dir"] * math.cos(math.pi * k)  # dir already flipped; sx eases through 0
            if k <= 0:
                f["sx"] = float(f["dir"])
        else:
            f["x"] += f["dir"] * f["speed"] * dt
            inside = sp["L"] < f["x"] < w - 2 * sp["L"]
            if inside and rng.random() < dt / 30:
                f["dir"] = -f["dir"]
                f["turn"] = 1.0
        if rng.random() < dt / 6:
            f["ty"] = self.free_y(sp, f)
        f["y"] += (f["ty"] - f["y"]) * min(1.0, dt * 0.25)
        f["bubble"] -= dt
        if f["bubble"] <= 0:
            f["bubble"] = rng.uniform(6, 14)
            nose = f["x"] + (sp["L"] if f["dir"] > 0 else 0)
            self.add_bubble(nose, f["y"] + sp["H"] / 4 - 0.5, rng.uniform(0.1, 0.3))

    def swim_clown(self, dt):
        c, rng = self.clown, self.rng
        sp = self.spec["clown"]
        c["tail"] += sp["beat"] * dt
        ax, ay = self.anemone
        if rng.random() < dt / 3:
            c["tx"] = ax + rng.uniform(-9, 3)
            c["ty"] = ay - rng.uniform(6.0, 9.0) * self.k
        dx = c["tx"] - c["x"]
        if c["turn"] > 0:
            c["turn"] -= dt / 0.8
            k = max(0.0, c["turn"])
            c["sx"] = -c["dir"] * math.cos(math.pi * k)
            if k <= 0:
                c["sx"] = float(c["dir"])
        elif dx * c["dir"] < -1.5:
            c["dir"] = -c["dir"]
            c["turn"] = 1.0
        else:
            c["x"] += max(-2.5, min(2.5, dx)) * dt * 0.9
        c["y"] += (c["ty"] - c["y"]) * min(1.0, dt * 0.8)

    def add_bubble(self, x, y, size):
        self.bubbles.append([x, y, self.rng.uniform(2.5, 4.0), size, self.rng.random() * TAU])

    # ---------------------------------------------------------- drawing
    def whale_haze(self, vis):
        v = self.spec["whale"]
        ox, oy = int(vis["x"]), int(vis["y"])
        frame = int(vis["pose"] / TAU * 8) % 8
        key = ("whale", frame, vis["dir"])

        def make():
            L, H = v["L"], v["H"]
            rows = H // 2
            out = []
            sgn = vis["dir"]
            pose = frame / 8 * TAU
            for cy in range(rows):
                for i in range(L):
                    cov = 0
                    for sx_ in (0.25, 0.75):
                        for sy_ in (0.25, 0.75):
                            u = (i + sx_) / L
                            u = 1 - u if sgn > 0 else u
                            vv = (cy + sy_) / rows * 2 - 1
                            cov += 1 if shape_whale(u, vv, pose) else 0
                    if cov:
                        out.append((i, cy, int(cov * 1.4 + 0.5) * QB))
            return out
        ents = self.sprite(key, make)
        mrow = list(self.mrow)
        w = self.w
        touched = {}
        for dx, dy, m in ents:
            y, x = oy + dy, ox + dx
            if 0 <= y < self.sand_row + 1 and 0 <= x < w:
                row = touched.get(y)
                if row is None:
                    row = touched[y] = mrow[y] = list(mrow[y])
                row[x] = min((M - 1) * QB, row[x] + m)
        return mrow

    def draw_sand(self, cells, o1x, o1y, o2x, o2y):
        w, h = self.w, self.h
        tex1, tex2 = self.ctex
        th = self.th
        sp, p0, pal, trow = self.sp, self.p0, self.sand_pal, self.sand_trow
        y0 = p0 >> 1
        cols = {}
        for py in range(y0 * 2, 2 * h):
            if py < p0:
                continue
            tr = trow[py - p0]
            c = map(add, tex1[(tr + o1y) % th][o1x:o1x + w], tex2[(tr + o2y) % th][o2x:o2x + w])
            cols[py] = [p[k] for p, k in zip(pal[py - p0], c)]
        color = term.COLOR
        for y in range(y0, h):
            top, bot = cols.get(2 * y), cols.get(2 * y + 1)
            row = cells[y]
            if top is not None and all(s <= 2 * y for s in sp):
                if color:
                    cells[y] = [(UP, a, b) for a, b in zip(top, bot)]
                else:
                    cells[y] = [(" ", None, None)] * w
                continue
            for x in range(w):
                s = sp[x]
                if s <= 2 * y:
                    row[x] = (UP, top[x], bot[x]) if color else (" ", None, None)
                elif s == 2 * y + 1:
                    row[x] = (DN, bot[x], row[x][2]) if color else ("_", None, None)

    def draw_kelp(self, cells, k, t):
        w = self.w
        sin, cos = math.sin, math.cos
        x0, vein, bulb = k["x"], k["vein"], k["bulb"]
        tom, tom2 = t * k["om"] + k["ph"], t * k["om"] * 1.9 + k["ph"]
        t13 = t * 1.3
        px = {}
        for y, lf, a1, p1, a2, p2, hw, body, hi, lo, solid, veined, blade in k["rows"]:
            xc = x0 + lf + a1 * sin(tom - p1) + a2 * sin(tom2 - p2)
            left, right = xc - hw, xc + hw
            row = cells[y]
            c0 = int(left // 1)
            for cx in range(c0, int(right // 1) + 1):
                if not 0 <= cx < w:
                    continue
                a = left if left > cx else cx
                b = right if right < cx + 1 else cx + 1
                cov = b - a
                if cov <= 0.3:
                    continue
                if cov >= 0.7:
                    row[cx] = veined if vein and cx == c0 + 1 else solid
                else:
                    m = (a + b) / 2
                    row[cx] = (LH if m < cx + 0.5 else RH, hi if m < xc else lo, row[cx][2])
            if blade:
                side, bph, steps, has_bulb = blade
                a0 = 0.75 + 0.3 * sin(t13 + bph)
                sa, ca = sin(a0), cos(a0)
                bx0 = xc + side * (hw + 0.3)
                bx, by = bx0, 2.0 * y + 1
                for cj, sj, cj1, sj1, half in steps:
                    bx += side * (sa * cj - ca * sj) * 0.9  # sin/cos of a0 - 0.1 j: the blade curls up
                    by -= (ca * cj + sa * sj) * 0.9
                    if half > 0.6:
                        nx, ny = (ca * cj1 + sa * sj1) * half * 0.8, side * (sa * cj1 - ca * sj1) * half * 0.8
                        px[(int(bx - nx), int(by - ny))] = body
                        px[(int(bx), int(by))] = hi
                        px[(int(bx + nx), int(by + ny))] = body
                    else:
                        px[(int(bx), int(by))] = hi
                if has_bulb:
                    px[(int(bx0), 2 * y)] = bulb
        if px:
            put_pixels(cells, px, w, self.h)

    def draw_school(self, cells, s):
        """Each fish is a two-pixel sliver (one pixel edge-on), silver when broadside."""
        w, h = self.w, self.h
        lim = 2 * (self.sand_row + (1 if s.far else 0))
        lut = self.school_luts.get(id(s))
        if lut is None:
            lut = []
            fog = FAR_FOG if s.far else 0.1
            for y in range(h):
                lv = []
                for i in range(10):
                    b = i / 9
                    c = (mix((34, 56, 82), (170, 196, 208), b / 0.8) if b < 0.8
                         else mix((170, 196, 208), (248, 254, 252), (b - 0.8) / 0.2))
                    lv.append(self.tint(c, y, fog))
                lut.append(lv)
            self.school_luts[id(s)] = lut
        px = {}
        sin = math.sin
        for p in s.f:
            x, py = int(p[0]), int(p[1])
            if not (0 <= x < w and 2 <= py < lim):
                continue
            vx, vy, vz = p[3], p[4], p[5]
            b2 = vx * vx + vy * vy
            br = b2 / (b2 + vz * vz + 1e-9)
            lvl = int(min(1.0, br * br * (0.92 + 0.16 * sin(p[6] * 20 + vx))) * 9)
            col = lut[py >> 1][lvl]
            px[(x, py)] = col
            if br > 0.45 and not s.far:
                tx = x - 1 if vx > 0 else x + 1
                if 0 <= tx < w:
                    px.setdefault((tx, py), lut[py >> 1][max(0, lvl - 3)])
        put_pixels(cells, px, w, h)

    def blit(self, cells, key, ents, ox, oy):
        """Draw raster entries at (ox, oy); the depth-tinted cells are cached per sprite and row."""
        lit = self._lit.get((key, oy))
        if lit is None:
            if len(self._lit) > 4000:
                self._lit.clear()
            h, tint = self.h, self.tint
            lit = self._lit[(key, oy)] = [
                (dx, oy + dy, (ch, tint(ca, oy + dy, fa), tint(cb, oy + dy, fb)) if kind == 0 else None,
                 ch, tint(ca, oy + dy, fa))
                for dx, dy, ch, ca, fa, cb, fb, kind in ents if 0 <= oy + dy < h]
        w = self.w
        for dx, y, cell, ch, fg in lit:
            x = ox + dx
            if 0 <= x < w:
                row = cells[y]
                row[x] = cell or (ch, fg, row[x][2])

    def draw_fish(self, cells, f):
        sp = self.spec[f["kind"]]
        sx = round(f["sx"] * 8) / 8
        py = int(round(f["y"] * 2))
        parity = py & 1
        tail = int(f["tail"] / TAU * 8) % 8
        key = (f["kind"], sx, parity, tail)
        bend = sp["amp"] * math.sin(tail / 8 * TAU)
        ents = self.sprite(key, lambda: raster(sp, sx, parity, 0.0, bend, NEAR_FOG))
        self.blit(cells, key, ents, int(round(f["x"])), py >> 1)

    def draw_visitor(self, cells, vis):
        v = self.spec[vis["kind"]]
        py = int(round(vis["y"] * 2))
        parity = py & 1
        frame = int(vis["pose"] / TAU * 12) % 12
        key = (vis["kind"], vis["dir"], parity, frame)
        ents = self.sprite(key, lambda: raster(v, float(vis["dir"]), parity, frame / 12 * TAU, 0.0, v["fog"]))
        self.blit(cells, key, ents, int(round(vis["x"])), py >> 1)

    def draw_anemone(self, cells, t):
        w, h, tint = self.w, self.h, self.tint
        ax, ay = self.anemone
        base = 2 * ay + 1
        sway = 0.35 * math.sin(t * 0.8) + 0.15 * math.sin(t * 1.9)
        px = {}
        for x in range(int(ax) - 2, int(ax) + 3):
            for py in range(base - 3, base + 1):
                px[(x, py)] = tint(mul((232, 176, 156), 1.05 - 0.1 * abs(x + 0.5 - ax) - 0.06 * (py - base + 3)), py >> 1, NEAR_FOG)
        sin, cos = math.sin, math.cos
        for i, (a0, ln, ph) in enumerate(self.tent):
            cols = self.tent_cols[i & 1]
            x, y = ax + a0 * 1.6, base - 3.0
            n = int(ln)
            for s in range(n):
                f = (s + 1) / n
                a = a0 * (0.55 + 0.6 * f) + (sway + 0.3 * sin(t * 1.3 + ph)) * f * f
                x += sin(a) * 0.85
                y -= cos(a) * 0.85
                px[(int(round(x)), int(round(y)))] = cols[min(9, int(f * 9.99)) if s < n - 1 else 10]
        put_pixels(cells, px, w, h)

    def move_bubbles(self, dt):
        """Rise and wobble; a bubble reaching the surface pops (with a rate-limited sound)."""
        t, keep, pops = self.t, [], []
        for b in self.bubbles:
            b[1] -= b[2] * dt
            b[3] = min(1.0, b[3] + 0.04 * dt)
            b[0] += math.sin(t * 3.1 + b[4]) * 1.8 * dt
            if b[1] < 1:
                pops.append(int(b[0]))
                if t - self.pop_at > 0.35:
                    self.pop_at = t
                    audio.sfx("bubblepop", 0.14 + 0.1 * b[3])
            else:
                keep.append(b)
        self.bubbles, self.pops = keep, pops

    def draw_bubbles(self, cells, t):
        w, h = self.w, self.h
        glyphs = ("·", "°", "o", "○")
        for b in self.bubbles:
            x, y = int(b[0]), int(b[1])
            if not (0 <= x < w and y < h):
                continue
            size = b[3] + 0.5 * (1 - y / max(1, self.sand_row))
            row = cells[y]
            bg = row[x][2] or self.water[y]
            sh = 0.55 + 0.3 * math.sin(t * 7 + b[4])
            row[x] = (glyphs[min(3, int(size * 3))], mix(bg, (236, 255, 252), sh), bg)
        row = cells[1]
        for x in self.pops:
            if 0 <= x < w:
                row[x] = ("˙", (236, 255, 250), row[x][2])

    def draw_surface(self, cells, t):
        """The underside of the surface: a rippling bright band, brightest toward the sun;
        where a trough dips below the first half row the whole cell is surface."""
        w, row, sin = self.w, cells[0], math.sin
        glow = self.sun_glow
        for x in range(w):
            s = 0.4 + 0.24 * sin(x * 0.33 + t * 1.2) + 0.18 * sin(x * 0.11 - t * 0.7 + 1.3) + glow[x]
            lv = max(0, min(3, int(s * 3.99)))
            if sin(x * 0.21 - t * 0.9) + 0.6 * sin(x * 0.47 + t * 1.5) > 1.05:
                row[x] = (" ", None, SURFACE[max(0, lv - 1)])
            else:
                row[x] = (UP, SURFACE[lv], row[x][2])


def main():
    p = term.make_parser(__doc__.splitlines()[0], fps=12)
    p.add_argument("--seed", type=int, default=None, help="random seed")
    p.add_argument("--visitor", choices=sorted(VISITORS), default=None,
                   help="bring this visitor on screen at once")
    args = p.parse_args()
    rng = random.Random(args.seed)
    dt = 1 / max(1.0, args.fps)
    st = {"reef": None}

    def step(cv, frame):
        r = st["reef"]
        if r is None or (r.w, r.h) != (cv.w, cv.h):
            r = st["reef"] = Reef(cv.w, cv.h, rng, args.visitor if r is None else None)
        r.frame(cv, dt)

    return term.run(args, step, music="undersea")


if __name__ == "__main__":
    raise SystemExit(main())
