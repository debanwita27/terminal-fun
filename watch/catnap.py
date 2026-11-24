#!/usr/bin/env python3
"""Catnap: a big cat walks in, sits, grooms, curls up and sleeps.

Usage: python3 catnap.py [--fps 12] [--frames N] [--style glyph|dots|mix] [--demo] [--mute]
When the Claude status file reports "done" the cat wakes, stretches and announces it,
then dozes off again. --demo cycles through every state quickly.
--style: dots (solid braille, the default), glyph (dense ASCII texture) or mix (switches on
each wake).
"""

META = {"name": "catnap", "kind": "watch",
        "blurb": "A big cat walks in, grooms, curls up and sleeps; wakes to say Claude is done",
        "credit": None}

import math
import random
import time

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

from fun import audio, term

TAU = 2 * math.pi
SAY = "claude's done!"

# ------------------------------------------------------------------ poses
# Cat units: y up from the ground, x toward where the cat faces, sitting height ~1.
# Joints: fs front shoulder, fn*/ff* near/far front wrist (j) and paw (p),
# hn*/hf* near/far hind hock and paw (the hind leg hangs from the haunch disc).

SIT = dict(
    hip=(0.0, 0.24), hip_r=0.21, chest=(0.14, 0.50), chest_r=0.16,
    back=(-0.11, 0.46), back_r=0.16, haunch=(-0.07, 0.20), haunch_r=0.20,
    head=(0.17, 0.75), head_r=0.15, face=1.0, eye=1.0, mouth=0.0, tw=0.0, rel=0.0,
    fs=(0.165, 0.45), fnj=(0.19, 0.24), fnp=(0.205, 0.04), ffj=(0.135, 0.24), ffp=(0.13, 0.04),
    hnj=(-0.14, 0.055), hnp=(0.06, 0.04), hfj=(-0.10, 0.055), hfp=(0.01, 0.04),
    tail=((-0.2, 0.1), (-0.33, 0.04), (-0.47, 0.03), (-0.58, 0.07), (-0.6, 0.17)),
)

CURL = dict(SIT,
    hip=(-0.13, 0.16), hip_r=0.16, chest=(0.11, 0.15), chest_r=0.15,
    back=(-0.05, 0.2), back_r=0.19, haunch=(-0.17, 0.2), haunch_r=0.18,
    head=(0.33, 0.215), head_r=0.14, face=0.9, eye=0.0, rel=0.25,
    fs=(0.18, 0.13), fnj=(0.28, 0.05), fnp=(0.37, 0.04), ffj=(0.25, 0.05), ffp=(0.33, 0.04),
    hnj=(-0.2, 0.06), hnp=(0.0, 0.04), hfj=(-0.17, 0.06), hfp=(0.03, 0.04),
    tail=((-0.3, 0.1), (-0.35, 0.04), (-0.05, 0.035), (0.28, 0.04), (0.44, 0.1)),
)

STRETCH = dict(SIT,
    hip=(-0.16, 0.42), hip_r=0.14, chest=(0.14, 0.22), chest_r=0.14,
    back=(-0.02, 0.36), back_r=0.13, haunch=(-0.18, 0.40), haunch_r=0.15,
    head=(0.36, 0.26), head_r=0.14, face=0.55, eye=0.15, mouth=0.0,
    fs=(0.16, 0.17), fnj=(0.33, 0.065), fnp=(0.52, 0.04), ffj=(0.3, 0.065), ffp=(0.47, 0.04),
    hnj=(-0.25, 0.18), hnp=(-0.16, 0.04), hfj=(-0.22, 0.18), hfp=(-0.12, 0.04),
    tail=((-0.28, 0.5), (-0.38, 0.62), (-0.43, 0.78), (-0.39, 0.92), (-0.32, 0.97)),
)

# Lying with the head up and eyes open: the first beat of waking.
ALERT = dict(CURL, head=(0.28, 0.35), face=1.0, eye=1.0, rel=0.0)

GROOM = dict(SIT, head=(0.2, 0.71), face=0.55, eye=0.08,
             fnj=(0.31, 0.45), fnp=(0.27, 0.61))

MEOW = dict(SIT, head=(0.17, 0.775), eye=0.55, mouth=1.0)

WALK_CYCLE = 0.66   # seconds per stride
WALK_SPEED = 0.55   # cat units per second; matches the stance sweep so paws don't slide
STRIDE_A = WALK_SPEED * WALK_CYCLE / 4


def _ik(a, t, ln, bend):
    """Joint of a two-bone leg (equal bones) from anchor a to paw t; bend +1 puts it in front."""
    dx, dy = t[0] - a[0], t[1] - a[1]
    d = math.hypot(dx, dy) or 1e-6
    mx, my = (a[0] + t[0]) / 2, (a[1] + t[1]) / 2
    if d >= 2 * ln:
        return mx, my
    h = math.sqrt(ln * ln - d * d / 4) * bend
    return mx - dy / d * h, my + dx / d * h


def _foot(q, lift):
    """Paw x offset and lift for leg phase q: stance sweeps back, swing arcs forward."""
    if q < 0.5:
        return STRIDE_A * (1 - 4 * q), 0.0
    s = (q - 0.5) * 2
    return -STRIDE_A + 2 * STRIDE_A * (0.5 - 0.5 * math.cos(math.pi * s)), lift * math.sin(math.pi * s)


def walk_pose(ph):
    v = TAU * ph
    bob = 0.012 * math.cos(2 * v)
    p = dict(SIT,
             hip=(-0.24, 0.45 + bob), hip_r=0.155, chest=(0.2, 0.46 + bob), chest_r=0.165,
             back=(-0.02, 0.5 + bob), back_r=0.15, haunch=(-0.25, 0.42 + bob), haunch_r=0.165,
             head=(0.44, 0.71 + bob * 0.6), head_r=0.145, face=0.12, eye=1.0, mouth=0.0)
    fs = (0.22, 0.40 + bob)
    p["fs"] = fs
    for key, base, q, bend, ln, lift in (("fn", 0.22, ph, 1, 0.19, 0.07),
                                        ("ff", 0.19, ph + 0.5, 1, 0.19, 0.07),
                                        ("hn", -0.25, ph + 0.54, -1, 0.21, 0.06),
                                        ("hf", -0.22, ph + 0.04, -1, 0.21, 0.06)):
        dx, up = _foot(q % 1, lift)
        paw = (base + dx, 0.04 + up)
        anchor = fs if key[0] == "f" else (p["haunch"][0] + (0.03 if key == "hf" else 0), p["haunch"][1])
        p[key + "p"] = paw
        p[key + "j"] = _ik(anchor, paw, ln, bend)
    sw = 0.035 * math.sin(v)
    p["tail"] = ((-0.36, 0.52 + bob), (-0.49 + sw * 0.3, 0.62), (-0.56 + sw * 0.7, 0.77),
                 (-0.53 + sw, 0.91), (-0.46 + sw * 1.2, 0.97))
    return p


def _lerp(a, b, u):
    if isinstance(a, tuple):
        return tuple(_lerp(x, y, u) for x, y in zip(a, b))
    return a + (b - a) * u


def blend(a, b, u):
    if u <= 0:
        return a
    if u >= 1:
        return b
    return {k: _lerp(a[k], b[k], u) for k in a}


def ease(u):
    u = min(1.0, max(0.0, u))
    return u * u * (3 - 2 * u)


def bump(t, a, b, edge=0.12):
    """0 outside [a, b], 1 inside, with eased shoulders of width edge."""
    return ease((t - a) / edge) * (1 - ease((t - b + edge) / edge))


# ------------------------------------------------------------------ rasteriser
# Shapes become convex polygons in a square sample grid (2 x 4 samples per cell, the
# braille dot grid); each sample row is one Python int bitmask, bit c = column c.

_RINGS = {}


def _ring(n):
    r = _RINGS.get(n)
    if r is None:
        r = _RINGS[n] = [(math.cos(TAU * i / n), math.sin(TAU * i / n)) for i in range(n)]
    return r


def _circ(x, y, r):
    n = 8 if r < 3 else 12 if r < 7 else 18 if r < 16 else 26
    return [(x + r * c, y + r * s) for c, s in _ring(n)]


def _hull(pts):
    pts = sorted(pts)
    lo, hi = [], []
    for p in pts:
        while len(lo) >= 2 and (lo[-1][0] - lo[-2][0]) * (p[1] - lo[-2][1]) - (lo[-1][1] - lo[-2][1]) * (p[0] - lo[-2][0]) <= 0:
            lo.pop()
        lo.append(p)
    for p in reversed(pts):
        while len(hi) >= 2 and (hi[-1][0] - hi[-2][0]) * (p[1] - hi[-2][1]) - (hi[-1][1] - hi[-2][1]) * (p[0] - hi[-2][0]) <= 0:
            hi.pop()
        hi.append(p)
    return lo[:-1] + hi[:-1]


class Mask:
    def __init__(self, nc, nr):
        self.nc, self.nr = nc, nr
        self.rows = [0] * nr

    def _spans(self, pts):
        ys = [p[1] for p in pts]
        r0 = max(0, math.ceil(min(ys) - 0.5))
        r1 = min(self.nr - 1, math.floor(max(ys) - 0.5))
        if r1 < r0:
            return
        n = r1 - r0 + 1
        lo, hi = [1e9] * n, [-1e9] * n
        m = len(pts)
        for i in range(m):
            x0, y0 = pts[i]
            x1, y1 = pts[(i + 1) % m]
            if y0 == y1:
                continue
            if y0 > y1:
                x0, y0, x1, y1 = x1, y1, x0, y0
            a = max(r0, math.ceil(y0 - 0.5))
            b = min(r1, math.ceil(y1 - 0.5) - 1)
            if a > b:
                continue
            k = (x1 - x0) / (y1 - y0)
            x = x0 + (a + 0.5 - y0) * k
            for j in range(a - r0, b - r0 + 1):
                if x < lo[j]:
                    lo[j] = x
                if x > hi[j]:
                    hi[j] = x
                x += k
        nc = self.nc
        for j in range(n):
            c0 = max(0, math.ceil(lo[j] - 0.5))
            c1 = min(nc - 1, math.floor(hi[j] - 0.5))
            if c0 <= c1:
                yield r0 + j, ((1 << (c1 - c0 + 1)) - 1) << c0

    def fill(self, pts):
        rows = self.rows
        for r, bits in self._spans(pts):
            rows[r] |= bits

    def cut(self, pts):
        rows = self.rows
        for r, bits in self._spans(pts):
            rows[r] &= ~bits

    def dots(self, pts, step, mode):
        """Samples along a polyline every `step` samples: mode 'cut', 'set' or 'xor'."""
        rows, nc, nr = self.rows, self.nc, self.nr
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            n = max(1, int(math.hypot(x1 - x0, y1 - y0) / step))
            for i in range(n + (pts[-1] == (x1, y1))):
                x, y = int(x0 + (x1 - x0) * i / n), int(y0 + (y1 - y0) * i / n)
                if 0 <= x < nc and 0 <= y < nr:
                    if mode == "cut":
                        rows[y] &= ~(1 << x)
                    elif mode == "set":
                        rows[y] |= 1 << x
                    else:
                        rows[y] ^= 1 << x


def _catmull(pts, k=3):
    out = []
    ext = [pts[0]] + list(pts) + [pts[-1]]
    for i in range(1, len(ext) - 2):
        p0, p1, p2, p3 = ext[i - 1], ext[i], ext[i + 1], ext[i + 2]
        for s in range(k):
            t = s / k
            t2, t3 = t * t, t * t * t
            out.append(tuple(0.5 * (2 * b + (-a + c) * t + (2 * a - 5 * b + 4 * c - d) * t2
                                    + (-a + 3 * b - 3 * c + d) * t3)
                             for a, b, c, d in zip(p0, p1, p2, p3)))
    out.append(pts[-1])
    return out


def _rot(p, c, th):
    s, co = math.sin(th), math.cos(th)
    x, y = p[0] - c[0], p[1] - c[1]
    return c[0] + x * co - y * s, c[1] + x * s + y * co


def draw_cat(p, S, bx, gy, d, nc, nr, style):
    """Rasterise pose p into (near, far) masks. bx, gy: sample column of the origin and
    sample row of the ground; d = +1 faces right, -1 faces left."""
    near, far = Mask(nc, nr), Mask(nc, nr)

    def X(pt):
        return bx + d * pt[0] * S, gy - pt[1] * S

    def blob(*cs):
        pts = []
        for pt, r in cs:
            x, y = X(pt)
            pts += _circ(x, y, r * S)
        return _hull(pts) if len(cs) > 1 else pts

    def ellipse(c, rx, ry, n=16):
        x, y = X(c)
        return [(x + rx * S * a, y - ry * S * b) for a, b in _ring(n)]

    def add(pt, off):
        return pt[0] + off[0], pt[1] + off[1]

    f = p["face"]
    head, hr = p["head"], p["head_r"]

    def hp(prof, front):
        return add(head, _lerp(prof, front, f))

    def limb(mask, a, ra, j, rj, q, rq):
        mask.fill(blob((a, ra), (j, rj)))
        mask.fill(blob((j, rj), (q, rq)))
        mask.fill(blob((q, rq), (add(q, (0.035, -0.004)), rq * 0.85)))

    # far side first; the classifier gives near coverage priority
    limb(far, add(p["fs"], (-0.03, 0)), 0.055, p["ffj"], 0.045, p["ffp"], 0.04)
    limb(far, add(p["haunch"], (0.03, -0.04)), 0.07, p["hfj"], 0.043, p["hfp"], 0.038)

    near.fill(blob((p["hip"], p["hip_r"]), (p["back"], p["back_r"]), (p["chest"], p["chest_r"])))
    near.fill(blob((p["haunch"], p["haunch_r"]),))
    neck = add(p["chest"], (-0.01, p["chest_r"] * 0.45))
    near.fill(blob((neck, p["chest_r"] * 0.9), (add(head, (-0.04, -0.05)), hr * 0.9)))
    near.fill(blob((head, hr),
                   (hp((0.03, -0.05), (-0.065, -0.045)), _lerp(0.1, 0.095, f)),
                   (hp((0.075, -0.04), (0.065, -0.045)), _lerp(0.085, 0.095, f)),
                   (hp((0.125, -0.045), (0.0, -0.06)), _lerp(0.055, 0.06, f))))
    for prof, front, sgn in ((((-0.075, 0.07), (0.0, 0.11), (-0.06, 0.235)),
                              ((-0.115, 0.055), (-0.035, 0.11), (-0.105, 0.235)), 1),
                             (((0.005, 0.105), (0.065, 0.085), (0.035, 0.215)),
                              ((0.035, 0.11), (0.115, 0.055), (0.105, 0.235)), -1)):
        b0, b1, tip = (hp(a, b) for a, b in zip(prof, front))
        mid = ((b0[0] + b1[0]) / 2, (b0[1] + b1[1]) / 2)
        th = sgn * 0.5 * p["rel"] - (0.55 * p["tw"] if sgn < 0 else 0)
        tip = _rot(tip, mid, th)
        tip = _lerp(tip, mid, 0.2 * p["rel"])
        near.fill(blob((b0, 0.026), (b1, 0.026), (tip, 0.012)))

    limb(near, p["fs"], 0.06, p["fnj"], 0.047, p["fnp"], 0.042)
    limb(near, p["haunch"], 0.08, p["hnj"], 0.045, p["hnp"], 0.04)
    tail = _catmull(p["tail"])
    n = len(tail)
    for i in range(n - 1):
        near.fill(blob((tail[i], 0.048 - 0.02 * i / n), (tail[i + 1], 0.048 - 0.02 * (i + 1) / n)))

    # seams: thigh outline and the near front leg against the chest
    hc, hrr = p["haunch"], p["haunch_r"] * 0.97
    arc = [X((hc[0] + hrr * math.cos(a), hc[1] + hrr * math.sin(a)))
           for a in (-0.35 + 2.3 * i / 14 for i in range(15))]
    near.dots(arc, 0.8, "cut")
    fs, fj = p["fs"], p["fnj"]
    near.dots([X(add(fs, (-0.055, 0.02))), X(add(fj, (-0.04, 0.0)))], 0.8, "cut")
    low = ease((0.45 - head[1]) / 0.15)  # lying down: outline the head and tail against the body
    if low > 0:
        top = [X((x, y + 0.04)) for x, y in tail[n // 3:] if y < 0.12]
        near.dots(top, 0.8, "cut")
        a0, a1 = 1.4, 1.4 + 2.6 * low
        near.dots([X((head[0] + hr * 1.02 * math.cos(a), head[1] + hr * 1.02 * math.sin(a)))
                   for a in (a0 + (a1 - a0) * i / 16 for i in range(17))], 0.8, "cut")

    # eyes, nose, mouth
    eyes = ((hp((0.08, 0.02), (0.062, 0.005)), _lerp(0.028, 0.048, f), 1.0),
            (hp((0.08, 0.02), (-0.062, 0.005)), 0.048, ease((f - 0.35) / 0.4)))
    for c, rx, vis in eyes:
        if vis <= 0.05:
            continue
        rx *= vis
        if p["eye"] > 0.22:
            ry = 0.056 * p["eye"] * vis
            near.cut(ellipse(c, rx, ry))
            if style == "dots":
                near.fill(ellipse(c, max(0.009, rx * 0.3), ry * 0.72, 10))
        else:
            near.dots([X(add(c, (rx * 1.3 * math.cos(a), -0.008 + 0.02 * math.sin(a))))
                       for a in (math.pi + math.pi * i / 6 for i in range(7))][::-1], 0.8, "cut")
    if f > 0.5 and style == "dots":
        near.cut([X(hp((0.1, -0.03), (-0.02, -0.03))), X(hp((0.13, -0.03), (0.02, -0.03))),
                  X(hp((0.12, -0.05), (0.0, -0.05)))])
    if p["mouth"] > 0.05:
        near.cut(ellipse(hp((0.11, -0.08), (0.0, -0.092)), 0.03, 0.035 * p["mouth"], 12))

    # whiskers: dotted, XOR so they read as gaps on the face and dots past it
    for side, vis in ((1, 1.0), (-1, ease((f - 0.4) / 0.4))):
        if vis <= 0.05:
            continue
        o = hp((0.11, -0.055), (side * 0.045, -0.06))
        for dy in (-0.005, -0.05, -0.1):
            e = hp((0.36, dy - 0.01), (side * 0.31, dy - 0.02))
            e = _lerp(o, e, vis)
            near.dots([X(_lerp(o, e, 0.3)), X(e)], 2.1, "xor" if style == "dots" else "set")
    return near, far


# ------------------------------------------------------------------ cell conversion
# A cell's code packs its 2x4 samples as bit (2*row + col), rows top to bottom.

_PAIRS4 = [tuple((b >> s) & 3 for s in (0, 2, 4, 6)) for b in range(256)]
_BR_BITS = ((0x01, 0x08), (0x02, 0x10), (0x04, 0x20), (0x40, 0x80))
BRAILLE = []
for _i in range(256):
    BRAILLE.append(chr(0x2800 + sum(_BR_BITS[k][c] for k in range(4) for c in range(2)
                                    if _i >> (2 * k + c) & 1)))
POP = [bin(i).count("1") for i in range(256)]


def _edge_glyphs(i):
    """Light glyphs for a partially covered edge cell, picked by which side is empty."""
    pc = POP[i]
    rows = [(i >> (2 * k)) & 3 for k in range(4)]
    left = sum(r & 1 for r in rows)
    right = sum(r >> 1 for r in rows)
    top = POP[rows[0]] + POP[rows[1]]
    bot = POP[rows[2]] + POP[rows[3]]
    gx, gy = right - left, bot - top
    if pc <= 2:
        return "'`" if top > bot else ".," if bot > top else ".'"
    if abs(gy) >= 2 * abs(gx) and gy:
        return "~^-" if gy > 0 else "-_~"
    if abs(gx) >= 2 * abs(gy) and gx:
        return "(|(" if gx > 0 else ")|)"
    if gx and gy:
        return "/" if (gx > 0) == (gy > 0) else "\\"
    return ":;"


def _seam_glyphs(i):
    """Glyph for an interior cell crossed by a gap (a contour seam, eyelid or whisker)."""
    miss = [(c, k) for k in range(4) for c in range(2) if not i >> (2 * k + c) & 1]
    if len(miss) >= 7:
        return " "
    if len(miss) <= 1:
        return ":"
    xs = [c * 1.0 for c, _ in miss]
    ys = [k * 1.0 for _, k in miss]
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    vx = sum((x - mx) ** 2 for x in xs)
    vy = sum((y - my) ** 2 for y in ys)
    cv = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    if vx < 0.01:
        return "|"
    if vy <= 0.25 * vx + 0.01:
        return "-"
    return "\\" if cv > 0 else "/"


EDGE = [_edge_glyphs(i) for i in range(256)]
SEAM = [_seam_glyphs(i) for i in range(256)]
DENSE = "@%RKSCOQG#B8&$@%MW0D#@N%HE"
MEDIUM = "t(/73~^Cc{s?)"
FARG = "%#*+=x"
_RNG = random.Random(7)
_HASH = [_RNG.randrange(1 << 16) for _ in range(4096)]


def cells_from(near, far, style, ncr, ncc):
    """Masks -> (static cells [(x, y, ch, col)], shimmer cells [(x, y, h, col)], shadow span)."""
    nrows, frows = near.rows, far.rows
    nb = (ncc + 3) // 4
    nmap, fmap = [], []
    for cy in range(ncr):
        rn = nrows[4 * cy:4 * cy + 4]
        rf = frows[4 * cy:4 * cy + 4]
        for codes, rr in ((nmap, rn), (fmap, rf)):
            if not (rr[0] | rr[1] | rr[2] | rr[3]):
                codes.append(None)
                continue
            p = [[q for b in r.to_bytes(nb, "little") for q in _PAIRS4[b]] for r in rr]
            codes.append([a | b << 2 | c << 4 | e << 6 for a, b, c, e in zip(*p)] + [0])
    static, shim = [], []
    zero = [0] * (nb * 4 + 1)
    top = next((y for y in range(ncr) if nmap[y] or fmap[y]), 0)
    span = max(1, ncr - top)
    for cy in range(ncr):
        rn, rf = nmap[cy], fmap[cy]
        if rn is None and rf is None:
            continue
        rn = rn or zero
        rf = rf or zero
        up = nmap[cy - 1] if cy and nmap[cy - 1] else zero
        dn = nmap[cy + 1] if cy + 1 < ncr and nmap[cy + 1] else zero
        upf = fmap[cy - 1] if cy and fmap[cy - 1] else zero
        dnf = fmap[cy + 1] if cy + 1 < ncr and fmap[cy + 1] else zero
        shade = (cy - top) * 5 // span
        for cx in range(ncc):
            n, fa = rn[cx], rf[cx]
            if not (n | fa):
                continue
            h = _HASH[(cx * 61 + cy * 4093) & 4095]
            if style == "dots":
                if n:
                    col = 255 - shade if POP[n] > 3 else 251 - shade
                    static.append((cx, cy, BRAILLE[n | (fa if POP[n] > 5 else 0)], col))
                else:
                    static.append((cx, cy, BRAILLE[fa], 244 - shade // 2))
                continue
            if n:
                l = rn[cx - 1] if cx else 0
                r = rn[cx + 1] if cx + 1 < ncc else 0
                if n == 255:
                    if (up[cx] or upf[cx]) and (dn[cx] or dnf[cx]) and (l or rf[cx - 1]) and (r or rf[cx + 1]):
                        shim.append((cx, cy, h, 255 - shade - (h & 1) * 2))
                    else:
                        g = DENSE if h & 3 else MEDIUM
                        static.append((cx, cy, g[h % len(g)], 253 - shade))
                elif up[cx] and dn[cx] and l and r:
                    static.append((cx, cy, SEAM[n], 240 - shade // 2))
                else:
                    g = EDGE[n]
                    static.append((cx, cy, g[h % len(g)], (251 if POP[n] > 3 else 247) - shade // 2))
            else:
                if fa == 255:
                    static.append((cx, cy, FARG[h % len(FARG)], 242 - shade // 2))
                else:
                    g = EDGE[fa]
                    static.append((cx, cy, g[h % len(g)], 240 - shade // 2))
    # shadow: under the bottom row of the cat
    bottom = nmap[ncr - 1] or [0]
    xs = [i for i, v in enumerate(bottom) if v] + [i for i, v in enumerate(fmap[ncr - 1] or []) if v]
    shadow = (min(xs), max(xs)) if xs else None
    return static, shim, shadow


# ------------------------------------------------------------------ renderer

class Renderer:
    def __init__(self):
        self.cache = {}
        self.geom = None

    def setup(self, w, h):
        g = (w, h)
        if g == self.geom:
            return
        self.geom = g
        self.cache.clear()
        self.S = S = max(12.0, min(0.72 * (h - 3) * 4, w * 2 / 1.75))
        self.bx = 2 * math.ceil(0.9 * S / 2)
        self.nc = 2 * self.bx + 4
        self.gy = 4 * math.ceil(1.08 * S / 4)
        self.ground = h - 2  # screen row just below the paws

    def frame(self, p, ox, d, style):
        """Cached (static, shimmer, shadow, screen x of local cell 0, top screen row)."""
        S = self.S
        frac = ox & 1
        key = (style, d, frac) + tuple(round(v * S * 1.5) for v in _flat(p))
        hit = self.cache.get(key)
        if hit is None:
            if len(self.cache) > 400:
                self.cache.clear()
            near, far = draw_cat(p, S, self.bx + frac, self.gy, d, self.nc, self.gy, style)
            hit = self.cache[key] = cells_from(near, far, style, self.gy // 4, self.nc // 2)
        return hit, (ox - frac - self.bx) // 2, self.ground - self.gy // 4


def _flat(p):
    out = []
    for k in sorted(p):
        v = p[k]
        if isinstance(v, tuple):
            for x in v:
                if isinstance(x, tuple):
                    out.extend(x)
                else:
                    out.append(x)
        else:
            out.append(v)
    return out


def draw_shadow(c, x0, x1, y, style):
    if y >= c.h:
        return
    mid, half = (x0 + x1) / 2, max(1.0, (x1 - x0) / 2 + 3)
    for x in range(int(mid - half), int(mid + half) + 1):
        u = abs(x - mid) / half
        if u < 1:
            col = 232 + int(6 * (1 - u * u))
            c.put(x, y, "⠉" if style == "dots" else "~" if u < 0.6 else "-", col)


def draw_bubble(c, x, y, text, d, shown):
    """Speech bubble whose tail ends at (x, y), opening up and away from the cat (side d)."""
    msg = text[:shown]
    w = len(text) + 8
    bx = x + 2 if d > 0 else x - 2 - w
    bx = max(0, min(c.w - w, bx))
    by = max(0, y - 9)
    edge = 250
    c.text(bx, by, "╭" + "─" * (w - 2) + "╮", edge)
    for i in (1, 2, 3):
        c.text(bx, by + i, "│" + " " * (w - 2) + "│", edge)
    c.text(bx + 4, by + 2, msg, 255)
    c.text(bx, by + 4, "╰" + "─" * (w - 2) + "╯", edge)
    tx = bx + 3 if d > 0 else bx + w - 4
    c.put(tx, by + 4, "┬" , edge)
    for i in range(5, max(6, y - by + 1)):
        tx2, ty = tx - d * (i - 4), by + i
        if 0 <= tx2 < c.w and 0 <= ty < c.h and c.cells[ty][tx2][0] != " ":
            break
        c.put(tx2, ty, "╱" if d > 0 else "╲", edge)


def main():
    parser = term.make_parser(__doc__.splitlines()[0], fps=12)
    parser.add_argument("--demo", action="store_true", help="cycle through all states quickly")
    parser.add_argument("--style", choices=("dots", "glyph", "mix"), default="dots",
                        help="braille dots, glyph texture, or switch on each wake (default dots)")
    args = parser.parse_args()
    dt = 1 / max(1.0, args.fps)
    k = 0.55 if args.demo else 1.0
    R = Renderer()
    st = {"s": "walk", "t": 0.0, "src": None, "bd": 0.0, "pose": None, "x": None, "d": 1,
          "ph": 0.0, "last": None, "start": time.time(), "pending": False,
          "fired": set(), "tw": None, "flick": None, "blink": 2.0, "style": args.style,
          "sleep_t0": 0.0, "music": False, "now": 0.0}
    if st["style"] == "mix":
        st["style"] = "dots"

    def goto(s, bd):
        st["s"], st["t"], st["src"], st["bd"] = s, 0.0, st["pose"], bd
        st["fired"] = set()

    def once(tag, at):
        if st["t"] >= at and tag not in st["fired"]:
            st["fired"].add(tag)
            return True
        return False

    def check_done(frame):
        if frame % 10:
            return False
        data = term.read_status()
        key = (data.get("state"), data.get("ts")) if data else None
        fire = bool(key and key[0] == "done" and key != st["last"]
                    and isinstance(key[1], (int, float)) and key[1] > st["start"])
        st["last"] = key
        return fire

    def music(on):
        if on != st["music"]:
            st["music"] = on
            if on:
                audio.music("catnap")
                st["sleep_t0"] = st["now"]
            else:
                audio.music_stop()

    def step(c, frame):
        R.setup(c.w, c.h)
        S = R.S
        st["t"] += dt
        st["now"] += dt
        t, s = st["t"], st["s"]
        st["pending"] |= check_done(frame)  # held until the cat is in a state that can wake
        if args.demo and s == "sleep" and t > 7.0:
            st["pending"] = True
        if st["pending"] and s in ("sleep", "curl", "sit", "groom"):
            st["pending"] = False
            if args.style == "mix":
                st["style"] = "dots" if st["style"] == "glyph" else "glyph"
            goto("wake", 0.9)
            s, t = "wake", 0.0
        home = int(c.w * 2 * 0.42)  # origin sample column where the cat settles
        off = int(0.95 * S)
        if st["x"] is None:
            st["x"] = float(-off if st["d"] > 0 else c.w * 2 + off)
        bubble = None

        if s in ("walk", "leave"):
            ph0 = st["ph"]
            st["ph"] = (ph0 + dt / WALK_CYCLE) % 1
            q1 = int(st["ph"] * 16)
            if int(ph0 * 2) != int(st["ph"] * 2):  # a diagonal pair of paws touched down
                audio.sfx("paw" if st["ph"] < 0.5 else "paw2", random.uniform(0.55, 0.85))
            target = walk_pose(q1 / 16)
            st["x"] += st["d"] * WALK_SPEED * S * dt
            if s == "walk" and (st["x"] - home) * st["d"] >= 0:
                st["x"] = float(home)
                goto("sit", 1.1)
            elif s == "leave" and not -off <= st["x"] <= c.w * 2 + off:
                st["d"] = -st["d"]
                goto("walk", 0.0)
        elif s == "sit":
            target = SIT
            if t > 3.0 * k:
                goto("groom", 0.9)
        elif s == "groom":
            meow = max(bump(t, 0.0, 1.3 * k, 0.3), bump(t, 4.6 * k, 5.9 * k, 0.3))
            lick = 0.5 + 0.5 * math.sin(TAU * 2.2 * t)
            g = dict(GROOM, head=_lerp(GROOM["head"], (0.215, 0.685), lick), mouth=0.35 * lick)
            target = blend(g, MEOW, meow)
            if once("m1", 0.35 * k) or once("m2", 4.95 * k):
                audio.sfx("meow", 0.9)
            if t > 8.0 * k:
                goto("curl", 2.6)
        elif s == "curl":
            target = CURL
            if t > 2.6:
                goto("sleep", 0.0)
                music(True)
        elif s == "sleep":
            b = math.sin(TAU * (st["now"] - st["sleep_t0"]) / 3.0)
            b = round(b * 6) / 6
            r = 1 + 0.035 * b
            target = dict(CURL, hip_r=CURL["hip_r"] * r, chest_r=CURL["chest_r"] * r,
                          haunch_r=CURL["haunch_r"] * r,
                          head=(CURL["head"][0], CURL["head"][1] + 0.006 * b))
        elif s == "wake":
            music(False)
            target = ALERT
            if once("trill", 0.25):
                audio.sfx("trill", 0.9)
            if t > 1.4:
                goto("stretch", 1.2)
        elif s == "stretch":
            yawn = bump(t, 1.0, 2.3, 0.35)
            target = dict(STRETCH, mouth=yawn, eye=0.15 * (1 - yawn))
            if once("yawn", 1.0):
                audio.sfx("yawn", 0.8)
            if t > 3.0:
                goto("say", 1.2)
        elif s == "say":
            target = SIT
            if once("mew", 1.2):
                audio.sfx("meow", 1.0)
            if t > 1.2:
                bubble = int((t - 1.2) * 18)
            if t > 6.5 * k + 1.2:
                goto("sit2", 0.6)
        else:  # sit2: calm down, then back to sleep (demo: walk off and back in)
            target = SIT
            if t > 2.5 * k:
                if args.demo:
                    goto("leave", 0.4)
                else:
                    goto("curl", 2.6)

        # small life: blinks, ear twitches, tail flicks
        now = st["now"]
        if s in ("sit", "say", "sit2", "walk") and now > st["blink"]:
            target = dict(target, eye=0.0) if now < st["blink"] + 0.16 else target
            if now >= st["blink"] + 0.16:
                st["blink"] = now + random.uniform(2.5, 5.0)
        if s in ("sleep", "sit", "sit2"):
            if st["tw"] is None and random.random() < dt / (3 if args.demo else 7):
                st["tw"] = now
            if st["flick"] is None and random.random() < dt / (4 if args.demo else 9):
                st["flick"] = now
        if st["tw"] is not None:
            u = (now - st["tw"]) / 0.35
            if u >= 1:
                st["tw"] = None
            else:
                target = dict(target, tw=math.sin(math.pi * u))
        if st["flick"] is not None:
            u = (now - st["flick"]) / 0.8
            if u >= 1:
                st["flick"] = None
            else:
                lift = math.sin(math.pi * u) * 0.06
                tl = list(target["tail"])
                tl[-1] = (tl[-1][0] + 0.02 * math.sin(math.pi * u), tl[-1][1] + lift * 1.6)
                tl[-2] = (tl[-2][0], tl[-2][1] + lift * 0.6)
                target = dict(target, tail=tuple(tl))

        src = st["src"] or target
        pose = blend(src, target, ease(st["t"] / st["bd"]) if st["bd"] else 1.0)
        st["pose"] = pose
        ox = int(round(st["x"]))
        d = st["d"]
        (static, shim, shadow), x0, y0 = R.frame(pose, ox, d, st["style"])

        if shadow:
            draw_shadow(c, x0 + shadow[0], x0 + shadow[1], R.ground, st["style"])
        cells, w, h = c.cells, c.w, c.h
        for x, y, ch, col in static:
            x += x0
            y += y0
            if 0 <= x < w and 0 <= y < h:
                cells[y][x] = (ch, col, None)
        if shim:
            tt = now * 0.3
            nd = len(DENSE)
            for x, y, hh, col in shim:
                x += x0
                y += y0
                if 0 <= x < w and 0 <= y < h:
                    e = int(tt + (hh & 255) / 256)
                    cells[y][x] = (DENSE[(hh + e * 7) % nd], col, None)

        head = pose["head"]
        hx = (ox + d * (head[0] + 0.05) * S) / 2
        hy = y0 + (R.gy - (head[1] + pose["head_r"]) * S) / 4
        if s == "sleep" and t > 1.0:
            for i in range(3):
                ph = (now * 0.22 + i / 3) % 1
                gch = "zzZ"[min(2, int(ph * 3))]
                col = 236 + int(16 * math.sin(math.pi * ph))
                c.put(hx + d * (3 + ph * 10 + math.sin(ph * 5 + i) * 1.5), hy - 1 - ph * 7, gch, col)
        if bubble is not None:
            draw_bubble(c, int(hx + d * 2), int(hy) + 2, SAY, d, bubble)

    return term.run(args, step)


if __name__ == "__main__":
    raise SystemExit(main())
