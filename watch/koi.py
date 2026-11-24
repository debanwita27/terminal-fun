#!/usr/bin/env python3
"""Koi circling a quiet ink pond, drawn in glyphs.

Every element has its own small glyph vocabulary, picked by measured ink coverage
(Menlo) and by shape:
  scales    rounded pairs of near-equal ink (c/o, o/e, O/8, 8/@): light picks the pair,
            chevron scale rows locked to body coordinates pick the glyph within it
  outlines  _ lids and floors, . - ' on shallow slopes, / \\ on the cell diagonal, ( ) up
            the sides, all from the silhouette's edge normal, one stroke thick
  fins      braille rays fanning from the root, brighter where they crowd together
  ripples   hand-drawn rings: - along the top and bottom, ( ) at the sides, . ' at the corners
  pads      dense # on an opaque leaf background, rimmed like the koi, with a notch
  petals    a rocking ' - , while falling (their shadow closing in), a c afloat
Koi live under the surface (glyphs only, fogged by depth, a shadow on the pond bed); pads
float on it (opaque, with their own shadow). Colours are truecolor rgb tuples.
"""
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
from fun import audio, term  # noqa: E402

META = {"name": "koi", "kind": "watch", "blurb": "Koi circling a quiet ink pond, drawn in glyphs",
        "credit": {"type": "inspired by", "who": "sucodee (@sucodeee)",
                   "url": "https://x.com/sucodeee/status/2113944922055410008"}}

TAU = 2 * math.pi
NPT = 12                     # spine points from nose to tail root
RASTER = tuple(zip(range(0, NPT - 1, 2), list(range(2, NPT - 1, 2)) + [NPT - 1]))  # body segments
# Pond: deep ink-teal, a touch lighter toward the top-left where the light comes from.
POND_DEEP, POND_LIT = (7, 18, 22), (16, 46, 50)
FOG = (20, 58, 60)           # water colour a fish fades toward with depth
BODY_WASH = 0.16             # body background: this much of the body colour over the pond
SHADOW = 0.7                 # pond-bed brightness under a shadow
# (shadow, light) per koi colour
CREAM = ((128, 120, 106), (242, 234, 216))
RED = ((112, 26, 24), (234, 80, 60))
SUMI = ((20, 22, 26), (76, 80, 88))
GOLD = ((118, 80, 22), (240, 194, 86))
PAD_FG = ((36, 72, 46), (78, 120, 72))
PAD_BG = (18, 44, 30)
PAD_RIM = (150, 186, 118)
PETAL = (244, 192, 200)
BLOOM = ((236, 150, 170), (252, 236, 214))
RIPPLE = (150, 204, 198)
GLINT = (214, 238, 230)
# Rounded pairs of near-equal ink, light to dense (Menlo: c .16 o .21 e .22 O .28 8 .30 @ .35);
# Menlo's dotted 0 is left out, its inner dot reads as noise.
SCALES = (("c", "o"), ("o", "e"), ("O", "8"), ("8", "@"))
LIGHT = (-0.42, -0.55, 0.72)  # toward the light: up-left of the screen, above the water
KINDS = ("kohaku", "showa", "ogon", "sanke", "kohaku", "showa", "ogon", "sanke", "kohaku")
PAT_S, PAT_L = 48, 17        # pattern table resolution along and across the body
BITS = ((0x01, 0x08), (0x02, 0x10), (0x04, 0x20), (0x40, 0x80))  # braille dot (row, col)
BRAILLE = [chr(0x2800 + i) for i in range(256)]


def mix(a, b, t):
    return (int(a[0] + (b[0] - a[0]) * t), int(a[1] + (b[1] - a[1]) * t), int(a[2] + (b[2] - a[2]) * t))


def q4(c):
    """Quantise to steps of 4 so slow fades don't resend every cell every frame."""
    return (c[0] & 0xFC, c[1] & 0xFC, c[2] & 0xFC)


def contour(nx, ny, off):
    """Edge glyph for a silhouette whose outward normal is (nx, ny) in square units; off is
    where the edge crosses the cell, in rows below its centre (-0.5..0.5). Shallow slopes
    step as . - ' by that height, the way a hand-drawn ASCII curve does."""
    ax, ay = abs(nx), abs(ny)
    if ax < 0.58 * ay:                      # within 30 deg of horizontal
        return "_" if off > 0.2 else "-"
    if ax < 1.3 * ay:                       # up to ~52 deg
        return "." if off > 0.1 else ("'" if off < -0.1 else "-")
    if ax < 3.7 * ay:                       # up to ~75 deg: the 1x2 cell's own diagonal
        return "\\" if nx * ny < 0 else "/"
    return "(" if nx < 0 else ")"


def outline(cells, cx, cy, sd, nx, ny):
    """Outline glyph for an inside cell of a silhouette (cells: the set or dict of inside
    cells; (nx, ny) the outward normal, sd the depth inside), as (glyph, cell) or None.
    Flat edges are drawn as _ in the cell whose lower half holds the edge, so a bottom edge
    is floored from inside and a top edge lidded from the open cell above; steep edges need
    open water beside them and shallow ones above or below, so the line stays one stroke
    thick whatever its slope."""
    ax, ay = abs(nx), abs(ny)
    if ax < 0.58 * ay:                      # within 30 deg of horizontal
        if ny > 0:
            return ("_", (cx, cy)) if (cx, cy + 1) not in cells else None
        return ("_", (cx, cy - 1)) if (cx, cy - 1) not in cells else None
    up_down = (cx, cy - 1) not in cells or (cx, cy + 1) not in cells
    side = (cx - 1, cy) not in cells or (cx + 1, cy) not in cells
    if side if ax > 3.7 * ay else (up_down if ax < 1.3 * ay else side or up_down):
        return contour(nx, ny, ny * sd * 0.5), (cx, cy)
    return None


def smooth(e0, e1, x):
    t = min(1.0, max(0.0, (x - e0) / (e1 - e0)))
    return t * t * (3 - 2 * t)


def profile(s):
    """Body half-width (0..1 of the widest) along s, 0 nose .. 1 tail root: blunt head,
    plump shoulders, a slim peduncle."""
    if s < 0.32:
        return 0.55 + 0.45 * math.sin(math.pi / 2 * s / 0.32)
    return 0.34 + 0.66 * (0.5 + 0.5 * math.cos(math.pi * (s - 0.32) / 0.68)) ** 0.8


def make_pattern(rng, kind):
    """(shadow, light) colour table over (s, lat), so the pattern is locked to the body."""
    base = GOLD if kind == "ogon" else CREAM
    reds, sumis = [], []
    if kind in ("kohaku", "sanke", "showa"):
        s0 = rng.uniform(0.02, 0.1)
        while s0 < 0.78:
            ln = rng.uniform(0.09, 0.17)
            reds.append((s0 + ln, rng.uniform(-0.25, 0.25), ln, rng.uniform(0.8, 1.4), rng.random() * TAU))
            s0 += 2 * ln + rng.uniform(0.04, 0.12)
    if kind == "sanke":
        for _ in range(rng.randint(3, 5)):
            sumis.append((rng.uniform(0.3, 0.85), rng.uniform(-0.8, 0.8), rng.uniform(0.04, 0.07),
                          rng.uniform(0.25, 0.4), rng.random() * TAU))
    if kind == "showa":
        sumis.append((0.06, rng.choice((-0.5, 0.5)), 0.09, 0.5, 0.0))  # the menware stroke on the head
        for _ in range(rng.randint(3, 4)):
            sumis.append((rng.uniform(0.25, 0.9), rng.uniform(-0.6, 0.6), rng.uniform(0.08, 0.14),
                          rng.uniform(0.5, 0.9), rng.random() * TAU))

    def field(spots, s, lat):
        best = 0.0
        for s0, l0, rs, rl, ph in spots:
            f = 1 - ((s - s0) / rs) ** 2 - ((lat - l0) / rl) ** 2 + 0.22 * math.sin(s * 31 + lat * 3 + ph)
            best = max(best, smooth(-0.1, 0.1, f))
        return best

    table = []
    for i in range(PAT_S):
        s = i / (PAT_S - 1)
        row = []
        for j in range(PAT_L):
            lat = j / (PAT_L - 1) * 2 - 1
            wr = field(reds, s, lat) if s < 0.86 else 0.0
            wk = field(sumis, s, lat)
            lo, hi = base
            if wr:
                lo, hi = mix(lo, RED[0], wr), mix(hi, RED[1], wr)
            if wk:
                lo, hi = mix(lo, SUMI[0], wk), mix(hi, SUMI[1], wk)
            row.append((lo, hi))
        table.append(row)
    return table


class Koi:
    def __init__(self, rng, idx):
        self.rng = rng
        self.kind = KINDS[idx % len(KINDS)]
        self.pat = make_pattern(rng, self.kind)
        self.fog_key, self.fog_pat = None, None
        self.size = rng.uniform(0.85, 1.12)
        self.z = self.zt = self.home_z = rng.uniform(0.25, 0.6)
        self.wave = rng.random() * TAU
        self.paddle = rng.random() * TAU
        self.omega = 0.0
        self.mood = 1.0
        self.mood_in = rng.uniform(3, 8)
        self.target = None
        self.target_in = 0.0
        self.rise_in = rng.uniform(12, 35)
        self.rise = 0.0          # seconds left at the surface
        self.popped = True
        self.lure = None         # (x, y, seconds left): a petal or a gathering point
        self.orbit = rng.random() * TAU
        self.lap = rng.choice((-1, 1, 1))   # which way round the pond this koi swims

    def fit(self, w, h):
        rng = self.rng
        self.L = max(8.0, min(0.165 * w, 0.9 * h, 30.0) * self.size)
        self.rmax = 0.21 * self.L
        self.seg = 0.8 * self.L / (NPT - 1)
        self.cruise = max(1.6, min(3.4, 0.028 * w)) * rng.uniform(0.85, 1.15)
        self.v = self.cruise
        x, y = rng.uniform(0.2, 0.8) * w, rng.uniform(0.2, 0.8) * 2 * h
        self.psi = rng.random() * TAU
        self.pts = [(x - math.cos(self.psi) * self.seg * i, y - math.sin(self.psi) * self.seg * i)
                    for i in range(NPT)]
        self.radii = [self.rmax * profile(i / (NPT - 1)) for i in range(NPT)]
        self.target = None
        self.scale_rows = max(6.0, 0.8 * self.L / 1.7)

    def new_target(self, w, h):
        """Mostly the next stretch of a lap around the pond (each koi keeps its own sense
        of direction), now and then a detour across it."""
        rng = self.rng
        cx, cy = w / 2, h
        px, py = self.pts[0]
        if rng.random() < 0.75:
            a = math.atan2((py - cy) / h, (px - cx) / (w / 2)) + self.lap * rng.uniform(0.5, 1.1)
            rf = rng.uniform(0.5, 0.82)
            self.target = (cx + math.cos(a) * rf * w / 2, cy + math.sin(a) * rf * h)
        else:
            self.target = (rng.uniform(0.15, 0.85) * w, rng.uniform(0.18, 0.82) * 2 * h)
        self.target_in = rng.uniform(6, 14)

    def step(self, dt, w, h, herd):
        rng = self.rng
        px, py = self.pts[0]
        self.target_in -= dt
        if self.lure:
            lx, ly, left = self.lure
            left -= dt
            self.lure = (lx, ly, left) if left > 0 else None
            r = 0.45 * self.L
            self.orbit += dt * 0.25
            tx, ty = lx + math.cos(self.orbit) * r, ly + math.sin(self.orbit) * r
        else:
            if self.target is None or self.target_in <= 0 or math.hypot(self.target[0] - px, self.target[1] - py) < 0.4 * self.L:
                self.new_target(w, h)
            tx, ty = self.target
        dx, dy = tx - px, ty - py
        d = math.hypot(dx, dy) or 1.0
        dx, dy = dx / d, dy / d
        # keep clear of the other koi's heads and bodies
        for o in herd:
            if o is self:
                continue
            for ox, oy in (o.pts[0], o.pts[NPT // 2], o.pts[-1]):
                ex, ey = px - ox, py - oy
                e = math.hypot(ex, ey)
                gap = 0.5 * (self.L + o.L)
                if 0 < e < gap:
                    k = 2.4 * (1 - e / gap) ** 2
                    dx += ex / e * k
                    dy += ey / e * k
        err = (math.atan2(dy, dx) - self.psi + math.pi) % TAU - math.pi
        wmax = 0.9
        want = max(-wmax, min(wmax, err * 1.1))
        self.omega += (want - self.omega) * min(1.0, dt / 0.9)  # eased turn: rate lags the wish
        self.psi += self.omega * dt
        self.mood_in -= dt
        if self.mood_in <= 0:
            self.mood = rng.choice((0.55, 0.8, 1.0, 1.0, 1.3))
            self.mood_in = rng.uniform(3, 9)
        vt = self.cruise * self.mood * (1 - 0.35 * abs(self.omega) / wmax) * (0.7 if self.lure else 1.0)
        self.v += (vt - self.v) * min(1.0, dt / 1.5)
        self.wave += dt * (2.0 + 1.1 * self.v / self.cruise)
        self.paddle += dt * (1.2 + 0.6 * (1 - self.v / self.cruise))
        px += math.cos(self.psi) * self.v * dt
        py += math.sin(self.psi) * self.v * dt
        pts, seg = self.pts, self.seg
        pts[0] = (px, py)
        for i in range(1, NPT):
            ax, ay = pts[i - 1]
            bx, by = pts[i]
            ex, ey = bx - ax, by - ay
            e = math.hypot(ex, ey) or 1.0
            pts[i] = (ax + ex / e * seg, ay + ey / e * seg)
        # depth: hold at home, rising to the surface now and then
        self.rise_in -= dt
        if self.rise_in <= 0 and self.rise <= 0:
            self.surface(rng.uniform(2.5, 4.0))
        if self.rise > 0:
            self.rise -= dt
            if self.rise <= 0:
                self.zt = self.home_z
                self.rise_in = rng.uniform(25, 60)
        self.z += (self.zt - self.z) * min(1.0, dt / 1.2)

    def surface(self, secs):
        self.zt, self.rise, self.popped = 0.0, secs, False

    def spine(self):
        """Spine points displaced by the swimming wave, with unit tangent and lateral normal."""
        pts, L = self.pts, self.L
        amp = 0.055 * L * (0.6 + 0.4 * min(1.4, self.v / self.cruise))
        out = []
        for i, (x, y) in enumerate(pts):
            j0, j1 = max(0, i - 1), min(NPT - 1, i + 1)
            tx, ty = pts[j0][0] - pts[j1][0], pts[j0][1] - pts[j1][1]
            tl = math.hypot(tx, ty) or 1.0
            tx, ty = tx / tl, ty / tl
            s = i / (NPT - 1)
            o = amp * s ** 1.7 * math.sin(self.wave - 4.5 * s)
            out.append((x - ty * o, y + tx * o, tx, ty, -ty, tx))
        return out

    def fogged(self, fog):
        """The pattern table with depth fog applied, cached per fog step."""
        key = int(fog * 32)
        if self.fog_key != key:
            f = key / 32
            self.fog_key = key
            self.fog_pat = [[(mix(lo, FOG, f), mix(hi, FOG, f)) for lo, hi in row] for row in self.pat]
        return self.fog_pat

    def render(self, buf, shade):
        """Fill buf {(cx, cy): (ch, rgb, alpha, tint)} (tint is a (rgb, amount) background
        wash or None); the fins go in first so the body covers their roots. shade(cx, cy,
        depth) marks the shadow cast on the pond bed."""
        sp = self.spine()
        radii = self.radii
        cells = {}
        get = cells.get
        sqrt = math.sqrt
        # every other spine point: segments shorter than the body's radius would only
        # re-test the same cells
        for i, j in RASTER:
            ax, ay = sp[i][0], sp[i][1]
            bx, by = sp[j][0], sp[j][1]
            ra, rb = radii[i], radii[j]
            dr = rb - ra
            ex, ey = bx - ax, by - ay
            el2 = ex * ex + ey * ey or 1.0
            el = sqrt(el2)
            ux, uy = ex / el, ey / el
            s0, s1 = i / (NPT - 1), (j - i) / (NPT - 1)
            rr = max(ra, rb)
            x0, x1 = int(min(ax, bx) - rr), int(max(ax, bx) + rr) + 1
            y0, y1 = int((min(ay, by) - rr) / 2), int((max(ay, by) + rr) / 2) + 1
            for cy in range(y0, y1 + 1):
                qy = cy * 2 + 1.0 - ay
                # only the columns this row's slice of the capsule can reach
                if ey > 1e-6 or ey < -1e-6:
                    ua, ub = (qy - rr) / ey, (qy + rr) / ey
                    if ua > ub:
                        ua, ub = ub, ua
                    ua = 0.0 if ua < 0 else (1.0 if ua > 1 else ua)
                    ub = 0.0 if ub < 0 else (1.0 if ub > 1 else ub)
                    xa, xb = ax + ex * ua, ax + ex * ub
                    if xa > xb:
                        xa, xb = xb, xa
                    c0, c1 = max(x0, int(xa - rr)), min(x1, int(xb + rr) + 1)
                else:
                    c0, c1 = x0, x1
                for cx in range(c0, c1 + 1):
                    qx = cx + 0.5 - ax
                    u = (qx * ex + qy * ey) / el2
                    u = 0.0 if u < 0 else (1.0 if u > 1 else u)
                    rx, ry = qx - ex * u, qy - ey * u
                    dist = sqrt(rx * rx + ry * ry) or 1e-6
                    sd = ra + dr * u - dist
                    if sd <= 0:
                        continue
                    old = get((cx, cy))
                    if old is None or sd > old[0]:
                        cells[(cx, cy)] = (sd, s0 + s1 * u, (ux * ry - uy * rx) / (sd + dist),
                                           rx / dist, ry / dist, -uy, ux)
        z = self.z
        fog = 0.08 + 0.55 * z
        self.fins(sp, buf, fog)
        pat = self.fogged(fog)
        lx, ly, lz = LIGHT
        rows = self.scale_rows
        sx, sy = 1 + int(3.0 * (1 - z) + 0.5), 1 + int(1.4 * (1 - z) + 0.3)
        for key, (sd, s, lat, nx, ny, px, py) in cells.items():
            cx, cy = key
            line = outline(cells, cx, cy, sd, nx, ny)
            la = -1.0 if lat < -1 else (1.0 if lat > 1 else lat)
            lo, hi = pat[int(s * (PAT_S - 1) + 0.5)][int((la + 1) * 0.5 * (PAT_L - 1) + 0.5)]
            b = la * (px * lx + py * ly) + sqrt(max(0.0, 1 - la * la)) * lz
            b = 0.15 + 0.85 * (b if b > 0 else 0.0)
            shade(cx + sx, cy + sy, sd)
            if line:
                buf[line[1]] = (line[0], q4(mix(lo, hi, 0.35 + 0.4 * b)), 1.0, None)
                if line[1] == key:
                    continue      # else the _ lids the open cell above and this one keeps its scales
            pair = SCALES[min(3, int(b * 3.3))]
            ch = pair[0] if s < 0.17 else pair[int(s * rows + abs(la) * 1.6) & 1]   # smooth head
            # the wash fades out toward the silhouette so the outline sits on open water
            hb = 0.5 * abs(nx) + abs(ny)
            wash = BODY_WASH * min(1.0, (sd - hb) / 2.5) if sd > hb + 0.03 else 0.0
            buf[key] = (ch, q4(mix(lo, hi, b)), 1.0, (hi, wash) if wash else None)

    def fins(self, sp, buf, fog):
        """Pectoral and pelvic fins and the forked tail: fans of braille rays, brighter where
        the rays crowd together at the root and thinning to the tips."""
        L, rmax = self.L, self.rmax
        dots = {}
        flap = math.sin(self.paddle)
        for s_at, size, sweep, half, rays in ((0.24, 1.0, 1.05, 0.5, 6), (0.56, 0.5, 0.85, 0.35, 3)):
            f = s_at * (NPT - 1)
            i = int(f)
            u = f - i
            a, b = sp[i], sp[i + 1]
            x, y = a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u
            tx, ty, nx, ny = a[2], a[3], a[4], a[5]
            r = self.radii[i] * 0.8
            for side in (-1, 1):
                ang = sweep + 0.25 * flap * side * (1 if s_at < 0.3 else 0.5)
                ca, sa = math.cos(ang), math.sin(ang)
                # axis: out from the flank, swept back toward the tail
                rays_fan(dots, x + nx * side * r, y + ny * side * r, nx * side * ca - tx * sa,
                         ny * side * ca - ty * sa, half, size * rmax * 1.1, 0.0, 0.3 * flap * side, rays)
        tail = sp[-1]
        flow = math.sin(self.wave - 5.2)
        root = 0.6 * self.seg   # rooted inside the peduncle so the tail never parts from it
        rays_fan(dots, tail[0] + tail[2] * root, tail[1] + tail[3] * root, -tail[2], -tail[3],
                 0.6, 0.34 * L + root, 0.38, 0.45 * flow, 9)
        fin_col = GOLD[1] if self.kind == "ogon" else CREAM[1]
        root_col = SUMI[1] if self.kind == "showa" else fin_col   # showa fins have dark roots
        ramp = [mix(mix(root_col, fin_col, min(1.0, j / 7 * 2.5)), FOG, fog * 0.7) for j in range(8)]
        for key, (bits, n, us) in dots.items():
            k = us / n
            alpha = min(0.92, 0.32 + 0.09 * n) * (1 - 0.25 * k)
            buf[key] = (BRAILLE[bits], ramp[int(k * 7.99)], alpha, None)


def rays_fan(dots, ox, oy, ax, ay, half, rad, notch, bend, rays):
    """Rasterise a fin into braille dots {cell: [bits, dot count, sum of ray fraction]}: rays
    spread over +-half radians about axis (ax, ay) from (ox, oy), curling by bend toward the
    tip, their tips joined into a rim. notch shortens the middle rays (a forked tail)."""
    al = math.hypot(ax, ay) or 1.0
    ax, ay = ax / al, ay / al
    segs = []
    tips = []
    for j in range(rays):
        phi = -half + 2 * half * j / max(1, rays - 1)
        reach = rad * (1 - notch * math.cos(math.pi / 2 * abs(phi) / half))
        # rays start a little way out: their crowded roots lie under the body
        px, py, pu = None, None, 0.0
        for u in (0.18, 0.45, 0.72, 1.0):
            a = phi + bend * u * u
            c, sn = math.cos(a), math.sin(a)
            qx = ox + (ax * c - ay * sn) * reach * u
            qy = oy + (ay * c + ax * sn) * reach * u
            if px is not None:
                segs.append((px, py, qx, qy, pu, u))
            px, py, pu = qx, qy, u
        tips.append((px, py))
    for (px, py), (qx, qy) in zip(tips, tips[1:]):
        segs.append((px, py, qx, qy, 1.0, 1.0))
    get = dots.get
    # dots are half a world unit square: x * 2 dots across, y * 2 dots down
    for x, y, x1, y1, u, u1 in segs:
        x *= 2
        y *= 2
        dx, dy = x1 * 2 - x, y1 * 2 - y
        n = int(max(abs(dx), abs(dy))) + 1
        dx, dy, du = dx / n, dy / n, (u1 - u) / n
        for _ in range(n):   # each segment's end dot is the next one's start
            X, Y = int(x), int(y)
            key = (X >> 1, Y >> 2)
            bit = BITS[Y & 3][X & 1]
            e = get(key)
            if e is None:
                dots[key] = [bit, 1, u]
            elif not e[0] & bit:
                e[0] |= bit
                e[1] += 1
                e[2] += u
            x += dx
            y += dy
            u += du


class Pad:
    def __init__(self, rng, w, h):
        self.R = rng.uniform(3.6, 5.6) * min(1.2, max(0.55, w / 110))
        self.x, self.y = rng.uniform(0, w), rng.uniform(0, 2 * h)
        a = rng.random() * TAU
        sp = rng.uniform(0.12, 0.3)
        self.bvx, self.bvy = math.cos(a) * sp, math.sin(a) * sp * 0.6
        self.vx, self.vy = self.bvx, self.bvy
        self.th = rng.random() * TAU
        self.spin = rng.uniform(-0.03, 0.03)
        self.wob = rng.random() * TAU
        self.bloom = rng.random() < 0.45
        self.key = None
        self.cells = []

    def step(self, dt, w, h):
        self.vx += (self.bvx - self.vx) * min(1.0, dt / 3.0)
        self.vy += (self.bvy - self.vy) * min(1.0, dt / 3.0)
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.th += self.spin * dt
        m = self.R + 3
        if not -m < self.x < w + m:
            self.x = (self.x + m) % (w + 2 * m) - m
        if not -m < self.y < 2 * h + m:
            self.y = (self.y + m) % (2 * h + 2 * m) - m

    def shape(self):
        """Cells relative to the pad's cell, re-rasterised only when its sub-cell offset or
        turn changes enough to show."""
        fx, fy = self.x - int(self.x), self.y / 2 - int(self.y / 2)
        key = (int(fx * 3), int(fy * 3), int(self.th * 12))
        if key == self.key:
            return self.cells
        self.key = key
        R, th = self.R, key[2] / 12
        ox, oy = (key[0] + 0.5) / 3, ((key[1] + 0.5) / 3) * 2
        cn, sn = math.cos(th), math.sin(th)
        notch = 0.3
        lx, ly = LIGHT[0], LIGHT[1]
        r1 = R + 1
        inside = {}
        for cy in range(-int(r1 / 2) - 1, int(r1 / 2) + 2):
            for cx in range(-int(r1) - 1, int(r1) + 2):
                qx, qy = cx + 0.5 - ox, cy * 2 + 1.0 - oy
                d = math.sqrt(qx * qx + qy * qy) or 1e-6
                ux, uy = qx / d, qy / d
                rim = R * (1 + 0.035 * math.sin(3 * math.atan2(qy, qx) + self.wob)) - d
                ca, sa = ux * cn + uy * sn, uy * cn - ux * sn
                # the notch: a wedge about (cn, sn), as a perpendicular distance from its edge
                wedge = (abs(math.atan2(sa, ca)) - notch) * d if ca > 0 and d > 0.8 else rim
                if min(rim, wedge) <= 0:
                    continue
                if wedge < rim:
                    sg = 1 if sa > 0 else -1
                    inside[(cx, cy)] = (wedge, sg * sn, -sg * cn, d, ux, uy)   # normal into the notch
                else:
                    inside[(cx, cy)] = (rim, ux, uy, d, ux, uy)
        out = []
        for (cx, cy), (sd, nx, ny, d, ux, uy) in inside.items():
            line = outline(inside, cx, cy, sd, nx, ny)
            if line and line[1] != (cx, cy):
                out.append((cx, cy - 1, "_", PAD_RIM, None))   # a lid over open water
                line = None
            if line:
                out.append((cx, cy, line[0], PAD_RIM, PAD_BG))
            else:
                b = 0.5 - 0.5 * (ux * lx + uy * ly) * min(1.0, d / R)
                out.append((cx, cy, "#", mix(PAD_FG[0], PAD_FG[1], b), PAD_BG))
        self.cells = out
        return out


class Scene:
    def __init__(self, args):
        self.rng = random.Random(args.seed)
        self.count = max(1, min(9, args.count))
        self.size = None
        self.koi = None
        self.ripples = []
        self.petals = []
        self.pads = []
        self.petal_in = 4.0
        self.gather_in = self.rng.uniform(35, 60)

    def layout(self, w, h):
        self.size = (w, h)
        rng = self.rng
        if self.koi is None:
            self.koi = [Koi(rng, i) for i in range(self.count)]
        for k in self.koi:
            k.fit(w, h)
        self.ripples, self.petals = [], []
        rows = []
        for y in range(h):
            row = []
            for x in range(w):
                # broad, smooth depth: lit from the top-left, two slow swells for an uneven bed
                u, v = x / max(1, w - 1), y / max(1, h - 1)
                lit = 1 - 0.75 * math.hypot(u * 0.9, v) / 1.35
                lit += 0.12 * math.sin(u * 3.1 + 0.6) * math.sin(v * 2.3 + 1.2)
                # 256 colours have no dark teal ramp, only hard grey steps: keep that pond flat
                lit = min(1.0, max(0.0, lit)) if term.TRUECOLOR else 0.6
                row.append((" ", None, mix(POND_DEEP, POND_LIT, lit * lit)))
            rows.append(row)
        self.base = rows
        self.dark = {}
        n = max(3, w * h // 260)
        self.glints = []
        while len(self.glints) < n:
            x, y = rng.randrange(max(1, w)), rng.randrange(max(1, h))
            if rng.random() < 1.2 - (x / w + y / h):   # gathered where the light falls
                self.glints.append((x, y, rng.uniform(7, 15), rng.random() * 15))
        self.pads = [Pad(rng, w, h) for _ in range(max(1, min(4, w * h // 1500)))]

    def ripple(self, x, y, strength, sound=True):
        self.ripples.append([x, y, 0.0, strength])
        for p in self.pads:
            dx, dy = p.x - x, p.y - y
            d = math.hypot(dx, dy)
            if 0 < d < 14:
                p.vx += dx / d * 0.5 * strength
                p.vy += dy / d * 0.5 * strength
        if sound:
            audio.sfx(self.rng.choice(("koiplop0", "koiplop1", "koiplop2")), 0.35 + 0.4 * strength)

    def step(self, cv, frame, fps):
        w, h = cv.w, cv.h
        if self.size != (w, h):
            self.layout(w, h)
        dt, t = 1.0 / fps, frame / fps
        rng = self.rng
        cells = cv.cells
        for y in range(h):
            cells[y] = self.base[y][:]

        # water glints: a slow swell and fade, each on its own long cycle
        for gx, gy, per, ph in self.glints:
            u = (t + ph) % per
            if u < 1.8:
                i = math.sin(math.pi * u / 1.8)
                bg = cells[gy][gx][2]
                cells[gy][gx] = ("-" if i > 0.6 else ".", q4(mix(bg, GLINT, 0.25 + 0.6 * i)), bg)

        # a gathering: every so often all the koi mill around one spot and one surfaces
        self.gather_in -= dt
        if self.gather_in <= 0:
            self.gather_in = rng.uniform(60, 110)
            gx, gy = rng.uniform(0.3, 0.7) * w, rng.uniform(0.3, 0.7) * 2 * h
            for k in self.koi:
                k.lure = (gx, gy, rng.uniform(10, 16))
            rng.choice(self.koi).rise_in = rng.uniform(4, 7)

        for k in self.koi:
            k.step(dt, w, h, self.koi)
            if not k.popped and k.z < 0.1:
                k.popped = True
                hx, hy = k.pts[0]
                self.ripple(hx + math.cos(k.psi), hy + math.sin(k.psi), 1.0)

        # shadows darken the pond bed's background
        dark = self.dark
        shadowed = {}
        sw = w + 2   # shadow keys are (cy + 1) * sw + cx + 1, so the blur can step off any edge

        def shade(cx, cy, sd):
            if -1 <= cx <= w and -1 <= cy <= h:
                k = (cy + 1) * sw + cx + 1
                v = 0.3 + 0.7 * (sd / 3.0 if sd < 3.0 else 1.0)
                if v > shadowed.get(k, 0.0):
                    shadowed[k] = v

        bufs = []
        for k in sorted(self.koi, key=lambda k: -k.z):   # deepest first
            buf = {}
            k.render(buf, shade)
            bufs.append(buf)
        for p in self.pads:
            ox, oy = int(p.x), int(p.y / 2)
            for cx, cy, *_ in p.shape():
                shade(ox + cx + 2, oy + cy + 1, 2.0)
        # a five-tap cross blur softens the shadow's edge into the pond bed
        soft = {}
        get = soft.get
        for k, v in shadowed.items():
            soft[k] = get(k, 0.0) + v * 0.4
            e = v * 0.15
            for j in (k - 1, k + 1, k - sw, k + sw):
                soft[j] = get(j, 0.0) + e
        for k, v in soft.items():
            cy, cx = divmod(k, sw)
            cy -= 1
            cx -= 1
            if 0 <= cx < w and 0 <= cy < h:
                lv = int(min(1.0, v * 1.2) * 8 + 0.5)
                if not lv:
                    continue
                ch, fg, bg = cells[cy][cx]
                d = dark.get((bg, lv))
                if d is None:
                    d = dark[(bg, lv)] = mix(bg, (0, 0, 0), (1 - SHADOW) * lv / 8)
                cells[cy][cx] = (ch, fg, d)

        # ripples: hand-drawn rings on the surface, fading into the water
        live = []
        for r in self.ripples:
            r[2] += dt
            age = r[2]
            if age >= 4.5:
                continue
            live.append(r)
            fade = (1 - age / 4.5) ** 1.4 * r[3]
            for j in range(3):
                rr = 1.2 + 4.2 * age - 2.8 * j
                if rr < 0.8:
                    continue
                amp = fade * (1 - 0.3 * j) * min(1.0, rr / 2)
                if amp < 0.06:
                    continue
                seen = set()
                n = int(TAU * rr / 0.8) + 8
                for i in range(n):
                    a = TAU * i / n
                    ca, sa = math.cos(a), math.sin(a)
                    px, py = r[0] + ca * rr, r[1] + sa * rr
                    cx, cy = int(px), int(py // 2)
                    if (cx, cy) in seen or not (0 <= cx < w and 0 <= cy < h):
                        continue
                    seen.add((cx, cy))
                    ax, ay = abs(ca), abs(sa)
                    if ax < 0.42 * ay:
                        ch = "-"
                    elif ax < 1.6 * ay:
                        ch = "." if sa < 0 else "'"
                    else:
                        ch = "(" if ca < 0 else ")"
                    if amp < 0.22 and i & 1:
                        continue   # a dying ring breaks up
                    bg = cells[cy][cx][2]
                    cells[cy][cx] = (ch, q4(mix(bg, RIPPLE, 0.85 * amp)), bg)
        self.ripples = live

        for buf in bufs:
            for (cx, cy), (ch, col, alpha, tint) in buf.items():
                if not (0 <= cx < w and 0 <= cy < h):
                    continue
                row = cells[cy]
                bg = row[cx][2]
                if tint:   # a faint wash of the body's own colour gives it volume
                    (r, g, b), t = tint
                    bg = (int(bg[0] + (r - bg[0]) * t) & 0xFC, int(bg[1] + (g - bg[1]) * t) & 0xFC,
                          int(bg[2] + (b - bg[2]) * t) & 0xFC)
                if alpha < 1:
                    r, g, b = col
                    col = (int(bg[0] + (r - bg[0]) * alpha) & 0xFC, int(bg[1] + (g - bg[1]) * alpha) & 0xFC,
                           int(bg[2] + (b - bg[2]) * alpha) & 0xFC)
                row[cx] = (ch, col, bg)

        for p in self.pads:
            p.step(dt, w, h)
            ox, oy = int(p.x), int(p.y / 2)
            for cx, cy, ch, fg, bg in p.shape():
                x, y = ox + cx, oy + cy
                if 0 <= x < w and 0 <= y < h:
                    cells[y][x] = (ch, fg, bg or cells[y][x][2])
            if p.bloom:
                bx, by = ox - 1, oy
                for i, ch in enumerate("(*)"):
                    if 0 <= bx + i < w and 0 <= by < h:
                        cells[by][bx + i] = (ch, BLOOM[1] if ch == "*" else BLOOM[0], PAD_BG)

        self.petals_step(cells, dt, t, w, h)

    def petals_step(self, cells, dt, t, w, h):
        """Sakura petals rock down through the air, their shadows closing in, then float."""
        rng = self.rng
        self.petal_in -= dt
        if self.petal_in <= 0 and len(self.petals) < 3:
            self.petal_in = rng.uniform(8, 20)
            self.petals.append({"x": rng.uniform(0.1, 0.9) * w, "y": rng.uniform(0.15, 0.85) * 2 * h,
                                "alt": 1.0, "fall": rng.uniform(0.11, 0.17), "ph": rng.random() * TAU,
                                "life": 0.0, "vx": rng.uniform(0.6, 1.2), "vy": rng.uniform(-0.2, 0.3)})
        keep = []
        for p in self.petals:
            if p["alt"] > 0:
                p["alt"] -= p["fall"] * dt
                rock = math.sin(t * 1.7 + p["ph"])
                p["x"] += (p["vx"] + 0.9 * rock) * dt
                p["y"] += p["vy"] * dt
                if p["alt"] <= 0:
                    self.ripple(p["x"], p["y"], 0.35, sound=False)
                    if rng.random() < 0.4:   # now and then the nearest koi comes up to nose it
                        k = min(self.koi, key=lambda k: math.hypot(k.pts[0][0] - p["x"], k.pts[0][1] - p["y"]))
                        k.lure = (p["x"], p["y"], 8.0)
                        k.rise_in = min(k.rise_in, 3.0)
            else:
                p["life"] += dt
                p["x"] += 0.25 * dt
            if p["life"] > 24:
                continue
            keep.append(p)
            x, y = int(p["x"]), int(p["y"] / 2)
            if p["alt"] > 0:
                a = p["alt"]
                sx, sy = x + int(6 * a + 0.5), y + int(3 * a + 0.5)
                if 0 <= sx < w and 0 <= sy < h:
                    bg = cells[sy][sx][2]
                    cells[sy][sx] = (".", q4(mix(bg, (0, 0, 0), 0.5)), bg)
                rock = math.sin(t * 1.7 + p["ph"])
                ch = "'" if rock > 0.35 else ("," if rock < -0.35 else "-")
                col = mix(PETAL, (255, 244, 246), a * 0.5)
            else:
                ch = "c"
                col = mix(PETAL, FOG, min(0.6, p["life"] / 40))
            if 0 <= x < w and 0 <= y < h:
                cells[y][x] = (ch, q4(col), cells[y][x][2])
        self.petals = keep


def main():
    p = term.make_parser("koi circling a quiet ink pond, drawn in glyphs", fps=12)
    p.add_argument("--count", type=int, default=5, help="number of koi, 1-9 (default 5)")
    p.add_argument("--seed", type=int, default=None, help="random seed")
    args = p.parse_args()
    sc = Scene(args)
    term.run(args, lambda cv, frame: sc.step(cv, frame, max(1.0, args.fps)), music="koi")


if __name__ == "__main__":
    main()
