#!/usr/bin/env python3
"""Celestial scenes: a rotating glyph-shaded Saturn, and the sun and moon rising and setting over a calm sea."""
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
from fun import term  # noqa: E402

META = {"name": "celestial", "kind": "watch",
        "blurb": "a rotating glyph-shaded Saturn, then sun and moon rising and setting over the sea",
        "credit": [{"type": "inspired by", "who": "the classic ASCII Saturn (artist unknown)",
                    "url": "https://ascii.co.uk/art/saturn"},
                   {"type": "inspired by", "who": "a text-poem moon reflected in water (artist unknown)"}]}

TAU = 2 * math.pi
ORDER = ("saturn", "sunset", "moonrise", "moonset", "sunrise")
FADE = 1.5          # seconds of dissolve at each end of a scene
SATURN_SECS = 60.0
MOVE_SECS = 45.0    # a full rise or set
HOLD_SECS = 9.0

# ------------------------------------------------------------------ saturn

PLANET_GLYPHS = " .,-:;~/[[uUU888NNMM"
# Ring glyphs by which thirds of the cell (top, middle, bottom) the ring covers, dim to bright,
# so the ring's edges draw as strokes like the reference's .o@P^ runs.
RING_STROKES = {(1, 0, 0): "'^^", (1, 1, 0): '"PP', (0, 1, 0): "-oo", (0, 1, 1): ".od",
                (0, 0, 1): "..o", (1, 0, 1): "::8", (1, 1, 1): ":@M"}
GREYS = list(range(234, 256))
RING_GREYS = list(range(238, 256))
BUTTER = [58, 94, 94, 130, 136, 136, 137, 172, 179, 179, 180, 180, 186, 186, 222, 222, 223, 223, 229, 230, 230, 231]
RING_TAN = [238, 239, 240, 101, 101, 137, 138, 144, 144, 180, 181, 187, 187, 223, 224, 224, 230, 230, 231, 231, 231, 231]
LUT_N = 64
TT = 128            # longitude / ring-azimuth texture bins (power of two for the & mask)
TL = 64             # planet latitude bins
RB = 96             # ring radial bins
R_IN, R_OUT = 1.28, 2.04   # ring radii in planet radii
LIGHT = (-0.55, 0.5, 0.67)


def norm(v):
    n = math.sqrt(sum(c * c for c in v))
    return tuple(c / n for c in v)


def ring_density(r):
    """Stylised Saturn rings: a near-invisible C ring (the dark gap by the planet), bright B ring,
    Cassini division, A ring with the Encke gap."""
    if r < 1.30 or r > 2.02:
        return 0.0
    if r < 1.45:
        return 0.06
    if r < 1.78:
        d = 0.75 + 0.25 * math.sin(math.pi * (r - 1.45) / 0.33)
    elif r < 1.83:
        return 0.04
    elif 1.955 < r < 1.972:
        return 0.1
    else:
        d = 0.62
    return d * (0.9 + 0.1 * math.sin(r * 31.0))


def planet_texture(rng):
    """Latitude bands with wavy edges and a few storm ovals, so longitude scrolling shows."""
    bands = [(rng.uniform(5, 15), rng.uniform(0.02, 0.06), rng.random() * TAU) for _ in range(5)]
    waves = [(rng.choice((3, 4, 5, 6)), rng.uniform(0.015, 0.04), rng.random() * TAU) for _ in range(3)]
    ovals = [(rng.uniform(-1.0, 1.0), rng.random() * TAU, rng.uniform(0.06, 0.12),
              rng.uniform(0.25, 0.5), rng.choice((-1, 1)) * rng.uniform(0.12, 0.22)) for _ in range(4)]
    tex = []
    for li in range(TL):
        lat0 = (li + 0.5) / TL * math.pi - math.pi / 2
        row = []
        for ti in range(TT):
            lon = ti * TAU / TT
            lat = lat0 + sum(a * math.sin(m * lon + p + lat0 * 3) for m, a, p in waves)
            v = 0.80 + 0.16 * math.exp(-(lat / 0.2) ** 2)
            v -= 0.14 * math.exp(-((abs(lat) - 0.38) / 0.09) ** 2)
            v += sum(a * math.sin(f * lat + p) for f, a, p in bands)
            v -= 0.18 * max(0.0, abs(lat) - 1.05)
            for olat, olon, osz, ow, amp in ovals:
                dl = (lon - olon + math.pi) % TAU - math.pi
                v += amp * math.exp(-((lat - olat) / osz) ** 2 - (dl / ow) ** 2)
            row.append(max(0.35, v))
        tex.append(row)
    return tex


def ring_texture(rng):
    """Radial density times smooth azimuthal clumping (correlated across neighbouring bins)."""
    modes = [(m, rng.uniform(0.04, 0.1), rng.random() * TAU, rng.uniform(-12, 12)) for m in range(3, 9)]
    tex = []
    for rb in range(RB):
        r = R_IN + (rb + 0.5) / RB * (R_OUT - R_IN)
        d = ring_density(r)
        row = []
        for ti in range(TT):
            th = ti * TAU / TT
            c = sum(a * math.sin(m * th + p + k * r) for m, a, p, k in modes)
            row.append(d * max(0.2, 0.95 + c))
        tex.append(row)
    return tex


def pose_basis(b_deg, psi_deg):
    """Ring-plane axes e1, e2 and spin axis n for opening angle B and on-screen roll psi.
    The camera looks down -z; screen x is right, y is up."""
    b, p = math.radians(b_deg), math.radians(psi_deg)
    e1 = (math.cos(p), math.sin(p), 0.0)
    n = (-math.sin(p) * math.cos(b), math.cos(p) * math.cos(b), math.sin(b))
    e2 = (n[1] * e1[2] - n[2] * e1[1], n[2] * e1[0] - n[0] * e1[2], n[0] * e1[1] - n[1] * e1[0])
    return e1, e2, n


def dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def saturn_geometry(w, h, scale, b_deg, psi_deg, ring_luts, out):
    """Fill out[...] with per-cell lists for one pose; yields every few rows so a rebuild
    can be spread over several frames. scale = cells per planet radius horizontally;
    a cell is ~2x taller than wide, so one row spans 2/scale radii."""
    e1, e2, n = pose_basis(b_deg, psi_deg)
    L = norm(LIGHT)
    nl = dot(n, L)
    lit_face = 0.6 + 0.4 * abs(nl) if nl * n[2] > 0 else 0.25 + 0.2 * abs(nl)
    cx, cy = w / 2, h / 2
    kt = TT / TAU
    row_v = 2 / scale
    planet, ring, front = [], [], []
    for y in range(h):
        v = -(y + 0.5 - cy) * row_v
        for x in range(w):
            u = (x + 0.5 - cx) / scale
            rr = u * u + v * v
            pl = None
            if rr < 1.0:
                zs = math.sqrt(1.0 - rr)
                s = (u, v, zs)
                lam = dot(s, L)
                if lam > 0:
                    shade = lam ** 0.85 * (0.78 + 0.22 * zs)
                    t = -dot(n, s) / nl if nl else -1
                    if t > 0:
                        q = (u + t * L[0], v + t * L[1], zs + t * L[2])
                        shade *= 1.0 - 0.45 * min(1.0, ring_density(math.sqrt(dot(q, q))))
                else:
                    shade = 0.0
                sn = max(-1.0, min(1.0, dot(s, n)))
                lb = min(TL - 1, int((math.asin(sn) + math.pi / 2) / math.pi * TL))
                lon = math.atan2(dot(s, e2), dot(s, e1))
                pl = (shade, lb, lon * kt)
            # Three vertical samples per cell (top, middle, bottom third) on the ring plane n.p = 0.
            bits, hit = [], None
            for k in (-0.33, 0.0, 0.33):
                vk = v - k * row_v
                rk = u * u + vk * vk
                zr = -(n[0] * u + n[1] * vk) / n[2]
                r = math.sqrt(rk + zr * zr)
                on = (ring_density(r) > 0.15 and (rk >= 1.0 or zr > math.sqrt(1.0 - rk)))
                bits.append(1 if on else 0)
                if on and (hit is None or k == 0.0):
                    hit = (u, vk, zr, r)
            rg = None
            if hit:
                p = hit[:3]
                r = hit[3]
                pl_dot = dot(p, L)
                lit = lit_face
                if pl_dot < 0 and r * r - pl_dot * pl_dot < 1.0:
                    lit *= 0.12
                rb = min(RB - 1, int((r - R_IN) / (R_OUT - R_IN) * RB))
                th = math.atan2(dot(p, e2), dot(p, e1))
                rg = (lit, rb, th * kt, ring_luts[tuple(bits)])
            if rg and pl:
                front.append((x, y) + rg + pl)
            elif rg:
                ring.append((x, y) + rg)
            elif pl:
                planet.append((x, y) + pl)
        if y % 4 == 3:
            yield
    out["planet"], out["ring"], out["front"] = planet, ring, front
    out["basis"] = (e1, e2, n)
    out["pose"] = (b_deg, psi_deg)


def stroke_lut(strokes, colours):
    """Ring brightness (0..1 in LUT_N steps) to a cell: glyph tier from the stroke set, grey by level."""
    lut = []
    for i in range(LUT_N + 1):
        b = i / LUT_N
        if b < 0.1:
            lut.append(None)
            continue
        tier = 0 if b < 0.3 else 1 if b < 0.55 else 2
        lut.append((strokes[tier], colours[min(len(colours) - 1, int(b * (len(colours) - 1) + 0.5))], None))
    return lut


def build_lut(glyphs, colours, gamma):
    lut = []
    for i in range(LUT_N + 1):
        b = min(1.0, i / LUT_N) ** gamma
        gi = int(b * (len(glyphs) - 1) + 0.5)
        if gi == 0:
            lut.append(None)
            continue
        lut.append((glyphs[gi], colours[min(len(colours) - 1, int(b * (len(colours) - 1) + 0.5))], None))
    return lut


class Saturn:
    def __init__(self, args, rng):
        self.args = args
        self.rng = rng
        self.ptex = planet_texture(rng)
        self.rtex = ring_texture(rng)
        pal = BUTTER if args.color else GREYS
        rpal = RING_TAN if args.color else RING_GREYS
        self.plut = build_lut(PLANET_GLYPHS, pal, 1.05)
        self.ring_luts = {bits: stroke_lut(st, rpal) for bits, st in RING_STROKES.items()}
        # Longitude speed per latitude bin (bins/s): one turn in ~32 s, equator a little faster.
        self.pw = [TT / 32.0 * (1.0 + 0.18 * math.cos((li + 0.5) / TL * math.pi - math.pi / 2) ** 2)
                   for li in range(TL)]
        # Keplerian azimuth speed per radial bin: omega ~ r^-1.5, ~45 s per orbit at r=1.5.
        self.rw = [TT / 45.0 * (1.5 / (R_IN + (rb + 0.5) / RB * (R_OUT - R_IN))) ** 1.5 for rb in range(RB)]
        self.size = None
        self.geom = None
        self.pending = None
        self.parts = [[rng.uniform(1.58, 2.24), rng.random() * TAU, rng.choice("o*@.")]
                      for _ in range(18)]

    def pose(self, t):
        a = self.args
        return (a.tilt + 3.0 * math.sin(TAU * t / 47.0), 32.0 + 6.0 * math.sin(TAU * t / 71.0 + 1.0))

    def layout(self, w, h, t):
        self.size = (w, h)
        worst = 0.0
        for k in range(16):
            bb = min(80.0, self.args.tilt + 3.0 * math.sin(TAU * k / 16))
            for j in range(16):
                ps = math.radians(32.0 + 6.0 * math.sin(TAU * j / 16))
                sb = math.sin(math.radians(bb))
                hx = math.sqrt(math.cos(ps) ** 2 + sb * sb * math.sin(ps) ** 2)
                hy = math.sqrt(math.sin(ps) ** 2 + sb * sb * math.cos(ps) ** 2)
                worst = max(worst, hx / max(1.0, w / 2 - 1), hy / max(1.0, h - 1))
        self.scale = max(2.0, 0.97 / (R_OUT * worst))
        self.geom = {}
        for _ in saturn_geometry(w, h, self.scale, *self.pose(t), self.ring_luts, self.geom):
            pass
        self.pending = None
        self.stars = []
        for _ in range(int(w * h * 0.012)):
            sx, sy = self.rng.randrange(w), self.rng.randrange(h)
            u, v = (sx - w / 2) / self.scale, (sy - h / 2) * 2 / self.scale
            if u * u + v * v > 1.1:
                self.stars.append((sx, sy, self.rng.choice("..'`+"), self.rng.random() * TAU,
                                   self.rng.uniform(0.3, 1.2)))

    def tick_geometry(self, t):
        """Rebuild for a slowly precessing pose in the background, a few rows per frame."""
        if self.pending is None:
            b, p = self.pose(t)
            ob, op = self.geom["pose"]
            if abs(b - ob) + abs(p - op) > 0.6:
                nxt = {}
                self.pending = (saturn_geometry(self.size[0], self.size[1], self.scale, b, p, self.ring_luts, nxt), nxt)
            return
        gen, nxt = self.pending
        for _ in range(2):
            try:
                next(gen)
            except StopIteration:
                self.geom = nxt
                self.pending = None
                return

    def draw(self, cv, t):
        w, h = cv.w, cv.h
        if self.size != (w, h):
            self.layout(w, h, t)
        self.tick_geometry(t)
        rows = cv.cells
        for x, y, ch, ph, rate in self.stars:
            tw = 0.5 + 0.5 * math.sin(t * rate + ph)
            if tw > 0.25:
                rows[y][x] = (ch, 236 + int(tw * 6), None)
        g = self.geom
        mask = TT - 1
        ptex, rtex, plut = self.ptex, self.rtex, self.plut
        pph = [int(w_ * t) for w_ in self.pw]
        rph = [int(-w_ * t) for w_ in self.rw]
        top = LUT_N
        for x, y, shade, lb, lk in g["planet"]:
            i = int(shade * ptex[lb][(int(lk) + pph[lb]) & mask] * top)
            c = plut[i if i < top else top]
            if c:
                rows[y][x] = c
        for x, y, lit, rb, tk, lut in g["ring"]:
            i = int(lit * rtex[rb][(int(tk) + rph[rb]) & mask] * top)
            c = lut[i if i < top else top]
            if c:
                rows[y][x] = c
        # Ring strokes in front of the planet win; where the ring is too dim the planet shows.
        for x, y, lit, rb, tk, lut, shade, lb, lk in g["front"]:
            i = int(lit * rtex[rb][(int(tk) + rph[rb]) & mask] * top)
            c = lut[i if i < top else top]
            if c is None:
                i = int(shade * ptex[lb][(int(lk) + pph[lb]) & mask] * top)
                c = plut[i if i < top else top] or (" ", None, None)
            rows[y][x] = c

        e1, e2, n = g["basis"]
        L = norm(LIGHT)
        s = self.scale
        cx, cy = w / 2, h / 2
        for p in self.parts:
            r, th, ch = p
            ang = th - self.rw[min(RB - 1, int((r - R_IN) / (R_OUT - R_IN) * RB))] * TAU / TT * t
            c, sn = math.cos(ang) * r, math.sin(ang) * r
            q = (c * e1[0] + sn * e2[0], c * e1[1] + sn * e2[1], c * e1[2] + sn * e2[2])
            rr = q[0] * q[0] + q[1] * q[1]
            if rr < 1.0 and q[2] < math.sqrt(1.0 - rr):
                continue
            ql = dot(q, L)
            dim = ql < 0 and r * r - ql * ql < 1.0
            x, y = int(cx + q[0] * s), int(cy - q[1] * s / 2)
            if 0 <= x < w and 0 <= y < h:
                rows[y][x] = (ch, 240 if dim else 255, None)


# ------------------------------------------------------------------ sea scenes

MOON_POEM = ("pale lantern of the tide, keeper of the quiet hours, you pour your silver on the "
             "sleeping sea and ask for nothing back. ")
SUN_POEM = ("slow gold out of the water, the day unfolds its warm hands and the whole sea "
            "remembers how to shine. ")
# Rough nearside maria in disc units (x right, y up): (x, y, radius).
MARIA = ((-0.32, 0.42, 0.26), (0.16, 0.40, 0.16), (0.30, 0.14, 0.19), (0.63, 0.30, 0.11),
         (-0.58, 0.02, 0.30), (-0.42, -0.30, 0.17), (-0.12, -0.36, 0.14), (0.50, -0.12, 0.13),
         (0.05, 0.62, 0.10))
MOON_FG = (60, 67, 110, 153, 189, 195, 231)   # dark dots .. bright text
SEA_STARS = ".'`.+"

# Sky keyframes: (sun altitude, top rgb, horizon rgb); altitude 0 = on the horizon, 1 = high.
DAWN = ((-0.25, (0, 0, 40), (40, 20, 70)), (-0.05, (20, 20, 80), (175, 95, 135)),
        (0.08, (40, 40, 120), (255, 135, 95)), (0.3, (60, 95, 175), (255, 175, 95)),
        (0.65, (95, 135, 215), (255, 215, 175)), (1.0, (95, 155, 235), (175, 215, 255)))
DUSK = ((-0.25, (0, 0, 20), (30, 0, 40)), (-0.05, (30, 10, 70), (175, 40, 80)),
        (0.08, (60, 30, 110), (255, 95, 40)), (0.3, (80, 80, 160), (255, 150, 60)),
        (0.65, (95, 130, 210), (250, 200, 140)), (1.0, (95, 155, 235), (190, 215, 240)))
_CUBE = (0, 95, 135, 175, 215, 255)


def cube(rgb):
    """Nearest 6x6x6 cube entry per channel (coarse, used only for glyph foregrounds)."""
    idx = [min(range(6), key=lambda i: abs(_CUBE[i] - v)) for v in rgb]
    return 16 + 36 * idx[0] + 6 * idx[1] + idx[2]


SWELL_LEVELS = 6


def rgb_int(c):
    return (min(255, int(c[0])), min(255, int(c[1])), min(255, int(c[2])))


def lerp3(a, b, t):
    return tuple(p + (q - p) * t for p, q in zip(a, b))


def sky_at(keys, alt):
    if alt <= keys[0][0]:
        return keys[0][1], keys[0][2]
    for (a0, t0, h0), (a1, t1, h1) in zip(keys, keys[1:]):
        if alt <= a1:
            f = (alt - a0) / (a1 - a0)
            return lerp3(t0, t1, f), lerp3(h0, h1, f)
    return keys[-1][1], keys[-1][2]


def sun_colours(alt):
    """(bg, text fg) per disc level, rim (0) to centre (4), for a sun at this altitude."""
    if alt < 0.12:
        return ((202, 166), (208, 202), (214, 208), (215, 209), (222, 215))
    if alt < 0.35:
        return ((208, 202), (214, 208), (220, 214), (221, 215), (228, 222))
    return ((214, 208), (220, 214), (221, 215), (228, 222), (230, 223))


def disc_template(rc, rr, poem, moon, rng):
    """{(dx, dy): (ch, level)} for a disc of rc cols x rr rows radius; text flows row to row.
    Moon levels: 0 '.', 1 'o', 2..6 text (limb to centre); sun levels: 0..4 rim to centre."""
    out = {}
    k = 0
    craters = [(rng.uniform(-0.9, 0.9), rng.uniform(-0.9, 0.9), rng.uniform(0.03, 0.08)) for _ in range(22)]
    ry = int(rr + 0.5)
    for dy in range(-ry, ry + 1):
        for dx in range(-int(rc + 1), int(rc + 2)):
            ux, uy = dx / rc, -dy / rr
            d2 = ux * ux + uy * uy
            if d2 > 1.0:
                continue
            ch = poem[k % len(poem)]
            k += 1
            rad = math.sqrt(d2)
            if moon:
                dark = sum(math.exp(-((ux - mx) ** 2 + (uy - my) ** 2) / (mr * mr)) for mx, my, mr in MARIA)
                dark += sum(0.7 * math.exp(-((ux - cx) ** 2 + (uy - cy) ** 2) / (cr * cr)) for cx, cy, cr in craters)
                dark = min(1.0, dark * 0.72) + rng.uniform(-0.08, 0.08)
                if dark > 0.72:
                    out[(dx, dy)] = (rng.choice(".·."), 0)
                elif dark > 0.42:
                    out[(dx, dy)] = ("o" if rng.random() < 0.7 else ".", 1)
                elif ch != " ":
                    out[(dx, dy)] = (ch, 6 - min(4, int(rad ** 2 * 4.5)))
            else:
                out[(dx, dy)] = (ch, 4 - min(4, int(rad ** 1.6 * 5)))
    return out


class Sea:
    """A body rising above, or sinking below, a calm sea horizon, with a rippling reflection."""

    def __init__(self, args, rng):
        self.args = args
        self.rng = rng
        self.size = None
        self.sky_cache = {}

    def layout(self, w, h):
        self.size = (w, h)
        self.hz = max(3, int(h * 0.62))
        self.rr = max(2.0, min(0.23 * h, 0.09 * w))
        self.rc = 2 * self.rr
        rng = random.Random(self.args.seed)
        self.moon = disc_template(self.rc, self.rr, MOON_POEM, True, rng)
        self.sun = disc_template(self.rc, self.rr, SUN_POEM, False, rng)
        self.stars = [(rng.randrange(w), rng.randrange(max(1, self.hz - 1)), rng.choice(SEA_STARS),
                       rng.random() * TAU, rng.uniform(0.3, 1.1)) for _ in range(int(w * self.hz * 0.012))]
        self.sky_cache = {}

    def skies(self, keys, alt):
        """Sky rows and water rows (SWELL_LEVELS brightness variants per row), cached per
        quantised altitude. Smooth rgb gradients in truecolor, Bayer-dithered 256 otherwise."""
        q = round(alt * 80) / 80
        key = (id(keys), q, self.size)
        got = self.sky_cache.get(key)
        if got is None:
            top, hor = sky_at(keys, q)
            w, h = self.size
            wh = max(1, h - self.hz)
            near = tuple(0.8 * (p + (r - p) * 0.5) for p, r in zip(hor, (20, 60, 130)))
            deep = tuple(0.5 * (p + (r - p) * 0.6) for p, r in zip(top, (5, 15, 40)))
            if term.TRUECOLOR:
                sky = [[(" ", None, rgb_int(lerp3(top, hor, (y / max(1, self.hz - 1)) ** 1.3)))] * w
                       for y in range(self.hz)]
                water = []
                for y in range(wh):
                    base = lerp3(near, deep, (y / max(1, wh - 1)) ** 0.8)
                    water.append([[(" ", None, rgb_int(tuple(c * (0.9 + 0.2 * k / (SWELL_LEVELS - 1))
                                                            for c in base)))] * w
                                  for k in range(SWELL_LEVELS)])
            else:
                sky = [list(r) for r in term.sky_rows(top, hor, self.hz, w)]
                water = [[list(r)] * SWELL_LEVELS for r in term.sky_rows(near, deep, wh, w)]
            fg = cube(tuple(min(255, c * 0.8 + 40) for c in hor))
            got = self.sky_cache[key] = (sky, water, fg)
            if len(self.sky_cache) > 200:
                self.sky_cache.clear()
                self.sky_cache[key] = got
        return got

    def draw(self, cv, t, body, rising, motion):
        """motion in [0, 1]: 0 = below the horizon, 1 = fully risen (inverted when setting)."""
        w, h = cv.w, cv.h
        if self.size != (w, h):
            self.layout(w, h)
        hz, rr, rc = self.hz, self.rr, self.rc
        m = motion * motion * (3 - 2 * motion)
        low, high = hz + rr + 1, hz - rr - max(2.0, 0.12 * h)
        cyf = low + (high - low) * m
        cyi = int(round(cyf))
        drift = (m - 0.5) * 0.08 * w * (1 if rising else -1)
        cxi = int(round(w / 2 + drift))
        alt = (hz - cyf) / max(1.0, hz - high)  # 0 when the centre sits on the horizon
        rows = cv.cells
        moon = body == "moon"
        wh = h - hz

        if moon:
            sky = water = None
            sea_fg = 23
            night = 1.0
        else:
            sky, water, sea_fg = self.skies(DAWN if rising else DUSK, alt)
            for y in range(hz):
                rows[y] = sky[y][:]
            # Slow brightness swells rolling toward the viewer, spacing widening with depth.
            for y in range(wh):
                k = 0.5 + 0.5 * math.sin(2.4 * math.sqrt(y + 1) - 0.45 * t)
                rows[hz + y] = water[y][min(SWELL_LEVELS - 1, int(k * SWELL_LEVELS))][:]
            night = max(0.0, min(1.0, 0.2 - alt) / 0.45)

        if night > 0.05:
            for x, y, ch, ph, rate in self.stars:
                tw = (0.5 + 0.5 * math.sin(t * rate + ph)) * night
                if tw > 0.25:
                    bg = rows[y][x][2]
                    rows[y][x] = (ch, 237 + int(tw * 10), bg)

        # Swell crests travel toward the viewer; sqrt spacing packs them tighter near the horizon.
        swell_fg = (17, 23, 24) if moon else (238, 240, sea_fg)
        cos, sin, floor = math.cos, math.sin, math.floor
        for d in range(1, wh):
            crest = sin(2.4 * math.sqrt(d) - 0.45 * t)
            if crest < 0.5:
                continue
            lvl = (crest - 0.5) * 2.0
            row = rows[hz + d]
            kx = 0.9 / (1.0 + 0.18 * d)
            ph = 0.37 * d + 0.15 * t
            for x in range(w):
                v = cos(kx * x + ph + 1.3 * sin(0.067 * x + 0.21 * t + d)) * (0.5 + 0.5 * cos(0.043 * x - 0.11 * t + 1.7 * d)) * lvl
                if v > 0.35:
                    row[x] = ("─" if v > 0.7 else "-" if v > 0.45 else "·", swell_fg[min(2, int(v * 3))], row[x][2])

        tmpl = self.moon if moon else self.sun
        if moon:
            fgs = MOON_FG
            glint = (60, 67, 110, 153, 189)
        else:
            sun = sun_colours(alt)
            glint = tuple(c[0] for c in sun)
        for (dx, dy), (ch, lv) in tmpl.items():
            y = cyi + dy
            if 0 <= y < hz:
                x = cxi + dx
                if 0 <= x < w:
                    if moon:
                        rows[y][x] = (ch, fgs[lv], None)
                    else:
                        bg, fg = sun[lv]
                        rows[y][x] = (ch, fg, bg)

        # Reflection: every water cell samples the mirrored disc at a continuously displaced,
        # sub-cell position (x in cells, rows stretched downward), so it flows instead of jumping.
        ry = int(rr + 0.5)
        vis = max(0.0, min(1.0, (hz - (cyi - ry)) / (2 * ry + 1)))
        stretch = 1.3 + 0.12 * sin(0.35 * t)
        band = int(rc * 1.6) + 6
        lo, hi = max(0, cxi - band), min(w, cxi + band + 1)
        dashes = "·-~─="
        for d in range(wh):
            f = d / max(1, wh - 1)
            src = (d + 0.5) / stretch + 0.35 * sin(0.7 * d - 0.9 * t)
            dy = hz - 1 - int(src) - cyi
            amp = 0.4 + 2.6 * f
            s0 = amp * (sin(0.55 * d - 1.1 * t) + 0.55 * sin(0.23 * d + 0.6 * t + 1.0)
                        + 0.3 * sin(1.4 * d - 1.9 * t + 2.0))
            thr = -0.75 + 0.9 * f
            gw = rc * (0.3 + 0.85 * f) + 1.0
            gx = cxi + 0.5 * s0
            kd = 2.1 * d
            row = rows[hz + d]
            for x in range(lo, hi):
                xf = x - s0 - 0.6 * amp * sin(0.17 * x + 0.8 * t + d)
                xs = floor(xf + 0.5)
                soft = abs(xf - xs) > 0.32  # sample falls near a cell edge: draw it dimmer
                crest = 0.6 * sin(0.62 * x + kd - 1.3 * t) + 0.4 * sin(0.21 * x - 0.4 * kd + 0.7 * t)
                cell = tmpl.get((cxi - xs, dy)) if crest > thr else None
                bg = row[x][2]
                if cell is not None:
                    ch, lv = cell
                    broken = crest - thr < 0.1 + 0.35 * f
                    if moon:
                        if broken and lv > 1:
                            ch, lv = ("o", 1) if crest > 0 else (".", 0)
                        row[x] = (ch, fgs[max(0, lv - 1 - int(f * 2) - soft)], bg)
                    else:
                        if broken:
                            ch = "~" if crest > 0 else "-"
                        row[x] = (ch, glint[max(0, lv - int(f * 2) - soft)], bg)
                elif vis > 0:
                    off = abs(x - gx)
                    if off < gw:
                        g = cos(0.45 * (x - cxi) - 0.7 * t + 1.9 * d) * cos(0.13 * x + 1.1 * d + 0.4 * t)
                        g *= (1.0 - off / gw) * vis
                        if g > 0.16:
                            k = min(4, int((g - 0.16) * 7))
                            row[x] = (dashes[k], glint[k], bg)


# ------------------------------------------------------------------ timeline

def scene_length(name):
    if name == "saturn":
        return SATURN_SECS
    return MOVE_SECS + HOLD_SECS + 2 * FADE + 1.0


def main():
    p = term.make_parser("a rotating glyph-shaded Saturn, then sun and moon rising and setting over the sea", fps=12)
    p.add_argument("--scene", default="all",
                   help="saturn, sunrise, sunset, moonrise, moonset, a comma list, or all (default: cycle)")
    p.add_argument("--tilt", type=float, default=16.0, help="Saturn ring opening angle in degrees (default 16)")
    p.add_argument("--speed", type=float, default=1.0, help="time multiplier (default 1)")
    p.add_argument("--seed", type=int, default=None, help="random seed")
    p.add_argument("--color", action="store_true", help="pale butterscotch Saturn instead of greys")
    args = p.parse_args()
    names = list(ORDER) if args.scene == "all" else [s.strip() for s in args.scene.split(",") if s.strip()]
    bad = [s for s in names if s not in ORDER]
    if bad or not names:
        p.error(f"unknown scene {', '.join(bad) or args.scene!r}; choose from {', '.join(ORDER)}")
    args.tilt = min(75.0, max(6.0, args.tilt))
    rng = random.Random(args.seed)
    saturn = Saturn(args, rng)
    sea = Sea(args, rng)
    plan = [(n, scene_length(n)) for n in names]
    cycle = sum(d for _, d in plan)
    dissolve = {"size": None}

    def step(cv, frame):
        t = frame / max(1.0, args.fps) * args.speed
        tc = t % cycle
        for name, dur in plan:
            if tc < dur:
                break
            tc -= dur
        if name == "saturn":
            saturn.draw(cv, t)
        else:
            motion = max(0.0, min(1.0, (tc - FADE - 0.5) / MOVE_SECS))
            rising = name.endswith("rise")
            if not rising:
                motion = 1.0 - max(0.0, min(1.0, (tc - FADE - HOLD_SECS) / MOVE_SECS))
            sea.draw(cv, t, "moon" if name.startswith("moon") else "sun", rising, motion)

        fade = min(tc, dur - tc) / FADE
        if fade < 1.0 and len(plan) + (name != "saturn") > 1:
            if dissolve["size"] != (cv.w, cv.h):
                r = random.Random(7)
                dissolve["mask"] = [[r.random() for _ in range(cv.w)] for _ in range(cv.h)]
                dissolve["size"] = (cv.w, cv.h)
            blank = cv.BLANK
            for row, mrow in zip(cv.cells, dissolve["mask"]):
                for x, mv in enumerate(mrow):
                    if mv > fade:
                        row[x] = blank

    return term.run(args, step, music="celestial")


if __name__ == "__main__":
    sys.exit(main())
