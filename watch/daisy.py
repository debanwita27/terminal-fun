#!/usr/bin/env python3
"""Blooming flowers in three randomised scenes: a glitch collage of daisy panels
(halftone, checker, smear, outline, shaded) with drifting serif letters; a '+'/'-'
glyph poster with a giant word and constellation lines; and a full-coverage
colour-mosaic meadow of small blooms over earth."""
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
from fun import audio, term  # noqa: E402
from fun.braille import Braille  # noqa: E402

META = {"name": "daisy", "kind": "watch",
        "blurb": "glitch-collage daisies, a glyph flower poster and a mosaic meadow",
        "credit": [{"type": "inspired by", "who": "ASCII animation (artist unknown), via Pinterest user mofri_ann",
                    "url": "https://in.pinterest.com/pin/1145462486504468167/"},
                   {"type": "inspired by", "who": "infoitsmostudio, Blooming poster",
                    "url": "https://www.instagram.com/p/DZzbKsrCL6V/"},
                   {"type": "inspired by", "who": "flower mosaic (artist unknown), via Pinterest user kieradxn",
                    "url": "https://in.pinterest.com/pin/125467539611670186/"}]}

TAU = 2 * math.pi
Q = 2                       # radius bins per square unit (a cell is 1 unit wide, 2 tall)
PANEL_THEMES = ("mono", "paper", "red", "pink")
SCENES = PANEL_THEMES + ("poster", "meadow")
GLITCH_SECS = 0.25

# ------------------------------------------------------------------ serif font
# Strokes in em units: x right, y down, cap top 0, baseline 1, x-height 0.4, descender 1.3.
# ("s", x0, y0, x1, y1, w0[, w1]) is a segment; ("a", cx, cy, rx, ry, deg0, deg1, thick, thin)
# an elliptical arc (x = cx + rx cos, y = cy + ry sin), thick where its tangent is vertical.
T, H = 0.15, 0.05
_STEM = ("s", .13, 0, .13, 1, T)
FONT = {
    "C": (.82, [("a", .44, .5, .38, .5, 35, 325, T, H), ("s", .77, .04, .77, .28, H)]),
    "O": (.9, [("a", .45, .5, .39, .5, 0, 360, T, H)]),
    "D": (.88, [_STEM, ("s", 0, 0, .42, 0, H * 1.3), ("s", 0, 1, .42, 1, H * 1.3),
                ("a", .42, .5, .38, .5, -90, 90, T, H)]),
    "E": (.76, [_STEM, ("s", 0, 0, .66, 0, H * 1.3), ("s", .13, .5, .52, .5, H * 1.2),
                ("s", 0, 1, .7, 1, H * 1.3), ("s", .66, 0, .68, .2, H), ("s", .52, .4, .52, .6, H),
                ("s", .7, 1, .72, .78, H)]),
    "B": (.8, [_STEM, ("s", 0, 0, .4, 0, H * 1.3), ("s", .13, .48, .44, .48, H), ("s", 0, 1, .44, 1, H * 1.3),
               ("a", .4, .24, .26, .24, -90, 90, T * .85, H), ("a", .44, .74, .3, .26, -90, 90, T, H)]),
    "P": (.76, [_STEM, ("s", 0, 0, .42, 0, H * 1.3), ("a", .42, .27, .29, .27, -90, 90, T, H),
                ("s", .13, .54, .42, .54, H), ("s", 0, 1, .28, 1, H * 1.3)]),
    "U": (.92, [("s", .15, 0, .15, .62, T), ("s", .77, 0, .77, .62, H * 1.3),
                ("a", .46, .62, .31, .38, 0, 180, T * .9, H),
                ("s", 0, 0, .3, 0, H * 1.3), ("s", .66, 0, .88, 0, H * 1.3)]),
    "o": (.64, [("a", .32, .7, .27, .3, 0, 360, T * .9, H)]),
    "l": (.3, [_STEM, ("s", 0, 0, .13, 0, H * 1.3), ("s", 0, 1, .27, 1, H * 1.3)]),
    "i": (.3, [("s", .13, .4, .13, 1, T), ("s", 0, .4, .13, .4, H * 1.3), ("s", 0, 1, .27, 1, H * 1.3),
               ("s", .13, .16, .13, .2, .17)]),
    "n": (.72, [("s", .13, .4, .13, 1, T), ("s", 0, .4, .13, .4, H * 1.3),
                ("a", .36, .66, .22, .24, 180, 360, T * .8, H), ("s", .58, .66, .58, 1, T),
                ("s", 0, 1, .27, 1, H * 1.3), ("s", .46, 1, .7, 1, H * 1.3)]),
    "m": (1.04, [("s", .13, .4, .13, 1, T), ("s", 0, .4, .13, .4, H * 1.3),
                 ("a", .31, .64, .18, .22, 180, 360, T * .75, H), ("s", .49, .64, .49, 1, T),
                 ("a", .67, .64, .18, .22, 180, 360, T * .75, H), ("s", .85, .64, .85, 1, T),
                 ("s", 0, 1, .26, 1, H * 1.3), ("s", .38, 1, .6, 1, H * 1.3), ("s", .74, 1, .96, 1, H * 1.3)]),
    "g": (.66, [("a", .3, .66, .24, .26, 0, 360, T * .85, H), ("s", .54, .42, .54, 1.1, T * .9),
                ("a", .3, 1.1, .24, .18, 0, 160, T * .7, H), ("s", .54, .42, .66, .4, H)]),
    "d": (.72, [("a", .31, .7, .25, .3, 0, 360, T * .85, H), ("s", .56, 0, .56, 1, T),
                ("s", .44, 0, .56, 0, H * 1.3), ("s", .56, 1, .7, 1, H * 1.3)]),
    "f": (.46, [("s", .2, .22, .2, 1, T), ("a", .38, .22, .18, .2, 180, 300, H * 1.6, H),
                ("s", .02, .42, .42, .42, H * 1.2), ("s", .04, 1, .38, 1, H * 1.3)]),
    "e": (.64, [("s", .06, .66, .58, .66, H * 1.2), ("a", .32, .7, .27, .3, 30, 360, T * .85, H)]),
    "t": (.5, [("s", .2, .18, .2, .88, T * .85), ("a", .34, .88, .14, .12, 90, 180, T * .6, H),
               ("s", .34, 1, .46, .94, H), ("s", .02, .42, .42, .42, H * 1.2)]),
    "a": (.66, [("a", .28, .76, .24, .24, 0, 360, T * .75, H), ("s", .52, .55, .52, 1, T * .9),
                ("a", .3, .56, .22, .16, 190, 360, H * 1.5, H), ("s", .52, 1, .64, 1, H * 1.2)]),
    "p": (.68, [("s", .13, .4, .13, 1.3, T), ("a", .38, .7, .26, .3, 0, 360, T * .85, H),
                ("s", 0, .4, .13, .4, H * 1.3), ("s", 0, 1.3, .27, 1.3, H * 1.3)]),
}
_compiled = {}


def glyph_segments(ch):
    """(advance, [(x0, y0, x1, y1, w0, w1, bbox)]) with arcs flattened into segments."""
    if ch in _compiled:
        return _compiled[ch]
    adv, strokes = FONT[ch]
    segs = []
    for st in strokes:
        if st[0] == "s":
            _, x0, y0, x1, y1, w0, *w1 = st
            segs.append((x0, y0, x1, y1, w0, w1[0] if w1 else w0))
            continue
        _, cx, cy, rx, ry, a0, a1, thick, thin = st
        n = max(6, int(abs(a1 - a0) / 12))
        pts = []
        for k in range(n + 1):
            a = math.radians(a0 + (a1 - a0) * k / n)
            pts.append((cx + rx * math.cos(a), cy + ry * math.sin(a), thin + (thick - thin) * abs(math.cos(a))))
        for (xa, ya, wa), (xb, yb, wb) in zip(pts, pts[1:]):
            segs.append((xa, ya, xb, yb, wa, wb))
    out = []
    for x0, y0, x1, y1, w0, w1 in segs:
        m = max(w0, w1) / 2
        out.append((x0, y0, x1, y1, w0, w1, min(x0, x1) - m, max(x0, x1) + m, min(y0, y1) - m, max(y0, y1) + m))
    _compiled[ch] = (adv, out)
    return _compiled[ch]


def ink(segs, u, v, em, minw):
    """True when em-space point (u, v) is inside a stroke; widths are floored at minw square units."""
    for x0, y0, x1, y1, w0, w1, bx0, bx1, by0, by1 in segs:
        if u < bx0 - minw or u > bx1 + minw or v < by0 - minw or v > by1 + minw:
            continue
        dx, dy = x1 - x0, y1 - y0
        ll = dx * dx + dy * dy
        k = 0.0 if ll == 0 else max(0.0, min(1.0, ((u - x0) * dx + (v - y0) * dy) / ll))
        ex, ey = (u - x0 - dx * k) * em, (v - y0 - dy * k) * em
        hw = max((w0 + (w1 - w0) * k) * em, minw) / 2
        if ex * ex + ey * ey < hw * hw:
            return True
    return False


_BR_BITS = ((0x01, 0x08), (0x02, 0x10), (0x04, 0x20), (0x40, 0x80))
_letter_cache = {}


def letter_cells(ch, size):
    """[(dx, dy, glyph)] for letter ch with cap height `size` rows; braille dots above one row."""
    key = (ch, size)
    if key in _letter_cache:
        return _letter_cache[key]
    if size <= 1:
        out = [(0, 0, ch)]
    else:
        adv, segs = glyph_segments(ch)
        em = 2.0 * size
        cols = max(1, int(math.ceil(adv * em)))
        out = []
        for cy in range(size):
            for cx in range(cols):
                bits = 0
                for j in range(4):
                    for i in range(2):
                        if ink(segs, (cx + 0.25 + 0.5 * i) / em, (cy * 2 + 0.25 + 0.5 * j) / em, em, 0.55):
                            bits |= _BR_BITS[j][i]
                if bits:
                    out.append((cx, cy, chr(0x2800 + bits)))
    _letter_cache[key] = out
    return out


# ------------------------------------------------------------------ flowers

CENTRE = 512                # local codes: petals (pid % 32) * 16 + shade, centre 512 + shade
PER = 528                   # codes per pooled flower
POOL = 6


def _norm(a):
    return a % TAU


def make_petals(species, rng):
    """(petals, centre radius) in local units where the longest petal tip is at radius 1.
    A petal is (angle, base radius, length, half width, z, pid, brightness bias, ruffle)."""
    ps = []
    if species == "daisy":
        rc = rng.uniform(0.14, 0.2)
        n = rng.randint(12, 20)
        for k in range(n):
            a = (k + rng.uniform(-0.1, 0.1)) * TAU / n
            ln = (1 - rc) * rng.uniform(0.82, 1.0)
            ps.append((a, rc * 0.85, ln, ln * rng.uniform(0.075, 0.1), rng.random(),
                       len(ps), rng.uniform(-0.08, 0.06), 0.0))
    elif species in ("peony", "rose"):
        rc = 0.06 if species == "peony" else 0.04
        rings = 4 if species == "peony" else 5
        for j in range(rings):
            f = 1 - j * (0.19 if species == "peony" else 0.16)
            n = rng.randint(6, 9) - j // 2 if species == "peony" else 5
            for k in range(n):
                a = (k + 0.37 * j + rng.uniform(-0.2, 0.2)) * TAU / n
                ln = f * rng.uniform(0.85, 1.0) - 0.02
                ps.append((a, 0.02, ln, ln * rng.uniform(0.38, 0.52), j + rng.random() * 0.5, len(ps),
                           rng.uniform(-0.1, 0.05) - 0.04 * j, rng.uniform(0.05, 0.12)))
    elif species == "tulip":
        rc = 0.02
        n = rng.randint(3, 5)
        for k in range(n):
            off = k - (n - 1) / 2
            a = -math.pi / 2 + off * 0.32 * rng.uniform(0.8, 1.1)
            ln = rng.uniform(0.88, 1.0)
            ps.append((a, 0.0, ln, ln * rng.uniform(0.3, 0.36), -abs(off), len(ps), rng.uniform(-0.1, 0.05), 0.04))
    else:  # orchid / periwinkle: five or six broad petals, one larger lip
        rc = rng.uniform(0.16, 0.22)
        n = rng.choice((5, 5, 6))
        lip = rng.randrange(n)
        for k in range(n):
            a = (k + rng.uniform(-0.1, 0.1)) * TAU / n
            big = 1.0 if k == lip else rng.uniform(0.78, 0.9)
            ln = (1 - 0.05) * big
            ps.append((a, 0.05, ln, ln * rng.uniform(0.24, 0.32) * (1.15 if k == lip else 1.0),
                       1.0 if k == lip else rng.random(), len(ps), rng.uniform(-0.06, 0.06), 0.06))
    return [(_norm(p[0]),) + p[1:] for p in ps], rc


class Flower:
    """One procedural flower and its polar coverage table.

    The table is indexed [row * tt + angle bin]: rows below trc span the centre disc,
    rows trc..tr-1 span centre edge to petal tip, row tr is all zero (outside). Values
    are scene codes: 0 outside, else 1 + slot * PER + local code."""

    CB = 64

    def __init__(self, species, rng, slot, tt=256, tr=40, trc=10):
        self.species, self.slot = species, slot
        self.petals, self.rc = make_petals(species, rng)
        self.tt, self.tr, self.trc = tt, tr, trc
        self.mask = tt - 1
        self.florets = (rng.choice((13, 21)), rng.choice((21, 34)), rng.uniform(0, TAU))
        bins = [[] for _ in range(self.CB)]
        for p in self.petals:
            a, rb, ln, hw, ruf = p[0], p[1], p[2], p[3], p[7]
            c = rb + ln / 2
            span = math.asin(min(1.0, hw * (1.3 + ruf) / c)) * 1.15 if c > hw * (1.3 + ruf) else math.pi
            k0, k1 = int((a - span) / TAU * self.CB) - 1, int((a + span) / TAU * self.CB) + 1
            for k in range(k0, k1 + 1):
                bins[k % self.CB].append(p)
        self.cand = bins
        self.table = None
        self._rmap_key = None

    def petal_coverage(self, x, y):
        """Sample local flower space (tip radius 1): (inside, edge_distance, shade 0..1, part),
        part being the petal id, or -1 for the centre disc."""
        return self._sample(math.hypot(x, y), math.atan2(y, x) % TAU)

    def _sample(self, r, th):
        sp = self.species
        if r < self.rc:
            q = r / self.rc
            if sp == "orchid":
                s = 0.95 - 0.1 * q if q < 0.55 else 0.15 + 0.2 * (1 - q)
            else:
                f1, f2, ph = self.florets
                tex = math.sin(th * f1 + q * 9 + ph) * math.sin(th * f2 - q * 7)
                s = 0.3 + 0.18 * tex + 0.25 * q * q
            return True, self.rc - r, max(0.0, min(1.0, s)), -1
        best = None
        for a, rb, ln, hw, z, pid, bias, ruf in self.cand[int(th / TAU * self.CB) % self.CB]:
            d = (th - a + math.pi) % TAU - math.pi
            hl = ln * 0.5
            al = r * math.cos(d) - rb - hl
            ac = r * math.sin(d)
            if ruf:
                hl *= 1 + ruf * math.sin(ac / hw * 4.0 + pid)
            qq = (al / hl) ** 2 + (ac / hw) ** 2
            if qq < 1 and (best is None or z > best[0] or (z == best[0] and qq < best[1])):
                best = (z, qq, al / hl, ac / hw, bias, pid, min(hl, hw))
        if best is None:
            return False, 0.0, 0.0, -1
        z, qq, al, ac, bias, pid, size = best
        edge = (1 - math.sqrt(qq)) * size
        t = (al + 1) * 0.5
        if sp == "daisy":
            s = 0.6 + 0.4 * min(1.0, t * 2.4) - 0.3 * ac * ac
        elif sp == "tulip":
            s = 0.4 + 0.55 * (1 - abs(ac)) * (0.6 + 0.4 * t)
        elif sp == "orchid":
            s = 0.15 + 0.85 * t - 0.15 * ac * ac
        else:
            s = 0.4 + 0.5 * t - 0.25 * ac * ac
        if edge < 0.012:
            s -= 0.25
        return True, edge, max(0.0, min(1.0, s + bias)), pid

    def build(self):
        if self.table is not None:
            return self.table
        tt, tr, trc = self.tt, self.tr, self.trc
        base = 1 + self.slot * PER
        rows = []
        for row in range(tr):
            if row < trc:
                r = (row + 0.5) / trc * self.rc
            else:
                r = self.rc + (row - trc + 0.5) / (tr - trc) * (1 - self.rc)
            for k in range(tt):
                inside, _, s, part = self._sample(r, (k + 0.5) / tt * TAU)
                if not inside:
                    rows.append(0)
                else:
                    si = min(15, int(s * 16))
                    rows.append(base + (CENTRE + si if part < 0 else (part % 32) * 16 + si))
        rows += [0] * tt
        self.table = rows
        return rows

    def rmap(self, n, rcu, tip):
        """Radius bin (Q per unit) -> table row offset, for centre radius rcu and petal tip `tip`."""
        key = (n, round(rcu * 4), round(tip * 4))
        if key == self._rmap_key:
            return self._rmap
        tt, tr, trc = self.tt, self.tr, self.trc
        span = max(1e-6, tip - rcu)
        out = []
        for i in range(n):
            r = (i + 0.5) / Q
            if r < rcu:
                row = int(r / rcu * trc)
            elif r < tip:
                row = trc + int((r - rcu) / span * (tr - trc))
            else:
                row = tr
            out.append(row * tt)
        self._rmap_key, self._rmap = key, out
        return out


def polar_cells(cells, cx, cy, tilt, axis, tt, nmax, ys=2):
    """Per (x, y) point (radius bin capped at nmax - 1, angle bin) around (cx, cy), with the
    flower foreshortened by `tilt` along `axis`. ys is square units per y step: 2 for cells,
    1 for half-block pixels."""
    ca, sa = math.cos(axis), math.sin(axis)
    it = 1.0 / tilt
    k = tt / TAU
    m = tt - 1
    ri, tb = [], []
    for x, y in cells:
        dx = x + 0.5 - cx
        dy = (y + 0.5 - cy) * ys
        u = dx * ca + dy * sa
        v = (dy * ca - dx * sa) * it
        r = math.hypot(u, v)
        i = int(r * Q)
        ri.append(i if i < nmax else nmax - 1)
        tb.append(int((math.atan2(v, u) + axis) * k) & m)
    return ri, tb


# Decoders for scene codes.
NCODES = 1 + POOL * PER
SH = [0] * NCODES
KIND = [0] * NCODES         # 0 outside, 1 petal, 2 centre
GID = [0] * NCODES
PIDS = [0] * NCODES
for _c in range(1, NCODES):
    _loc = (_c - 1) % PER
    SH[_c] = _loc % 16
    KIND[_c] = 2 if _loc >= CENTRE else 1
    GID[_c] = 1 + (_c - 1) // 16
    PIDS[_c] = _loc // 16


# ------------------------------------------------------------------ panel collage

THEMES = {
    "mono": dict(light=False, bgs=[232, 235, 238, 241, 233],
                 ramp=[238, 240, 242, 244, 246, 248, 249, 250, 251, 252, 253, 254, 255, 231],
                 centre=[233, 235, 237, 239, 241, 243], ink=232, line=252, fill=None,
                 accents=[37, 30, 88], letters=[236, 238, 241, 244, 247, 250],
                 drip=[255, 252, 249, 246, 243, 240, 238]),
    "paper": dict(light=True, bgs=[231, 254, 251, 248],
                  ramp=[242, 244, 246, 248, 249, 250, 251, 252, 253, 254, 255, 231],
                  centre=[236, 238, 240, 242, 244], ink=235, line=235, fill=231,
                  accents=[44, 37, 43], letters=[252, 249, 246, 243, 240, 237],
                  drip=[238, 240, 242, 244, 246, 248, 250]),
    "red": dict(light=False, bgs=[232, 52, 88, 234],
                ramp=[52, 88, 124, 131, 167, 174, 181, 217, 224, 231],
                centre=[232, 52, 88, 124], ink=232, line=217, fill=None,
                accents=[37, 196, 160], letters=[52, 88, 124, 160, 167],
                drip=[224, 210, 203, 196, 160, 124, 88]),
    "pink": dict(light=True, bgs=[231, 254, 252, 249],
                 ramp=[243, 245, 247, 249, 250, 251, 252, 253, 254, 255, 231],
                 centre=[236, 238, 240, 242], ink=236, line=236, fill=231,
                 accents=[211, 218, 44, 43], letters=[252, 249, 246, 242, 239],
                 drip=[238, 240, 242, 244, 246, 248]),
}
TREATS = ("halftone", "checker", "smear", "outline", "solid")
DRIP_CH = "││▌┃"
WORDS4 = ("CODE", "CODE", "CODE", "BODE", "DOPE", "COPE", "DUPE", "CUBE", "BEDO")
HB = [None] * 65536


def halfblock(a, b):
    """Cell with 256-colour a in its top half and b in its bottom half (memoised in HB)."""
    c = HB[(a << 8) | b] = (" ", None, a) if a == b else ("▀", a, b)
    return c


class Panels:
    """The glitch collage. One or two large daisies are rasterised once per update at
    half-block resolution (two square pixels per cell); rectangular panels each render
    that raster with their own treatment, background and drifting letter."""

    def __init__(self, rng, pool):
        self.rng, self.pool = rng, pool
        self.size = None
        self._luts = {}
        self._pix = (None, None)

    def flower(self, slot):
        if self.pool[slot] is None:
            self.pool[slot] = Flower("daisy", random.Random(self.rng.random()), slot, tt=512, tr=48, trc=12)
        return self.pool[slot]

    def cut(self, theme, w, h, t):
        rng = self.rng
        self.theme, self.th, self.size, self.w, self.h = theme, THEMES[theme], (w, h), w, h
        th = self.th
        if self._pix[0] != (w, h):
            self._pix = ((w, h), [(x, py) for py in range(2 * h) for x in range(w)])
        pix = self._pix[1]
        self.flowers = []
        placed = []
        for slot in rng.sample(range(3), rng.choice((1, 2, 2))):
            fl = self.flower(slot)
            fl.build()
            R = rng.uniform(0.5, 0.85) * 2 * h
            for _ in range(20):   # keep a second head clear of the first so both read as flowers
                cx, cpy = rng.uniform(0.12, 0.88) * w, rng.uniform(0.15, 0.85) * 2 * h
                if all(math.hypot(cx - qx, cpy - qy) > 0.9 * max(R, qr) for qx, qy, qr in placed):
                    break
            placed.append((cx, cpy, R))
            n = int(R * Q) + 2
            ri, tb = polar_cells(pix, cx, cpy, rng.uniform(0.72, 1.0), rng.uniform(0, TAU), fl.tt, n, ys=1)
            self.flowers.append(dict(fl=fl, R=R, n=n, ri=ri, tb=tb, rot=rng.uniform(0, TAU),
                                     spin=rng.choice((-1, 1)) * rng.uniform(0.03, 0.07),
                                     period=rng.uniform(14, 24), ph=rng.uniform(0, TAU)))
        self.slots = [f["fl"].slot for f in self.flowers]

        sx_top = int(w * rng.uniform(0.32, 0.68))
        sx_bot = sx_top if rng.random() < 0.5 else int(w * rng.uniform(0.3, 0.7))
        sy = int(h * rng.uniform(0.38, 0.62))
        word = rng.choice(WORDS4)
        treats = rng.sample(TREATS, 4)
        bgs = th["bgs"][:]
        rng.shuffle(bgs)
        quads = [(0, 0, sx_top, sy), (sx_top, 0, w, sy), (0, sy, sx_bot, h), (sx_bot, sy, w, h)]
        self.panels = []
        for i, rect in enumerate(quads):
            self.panels.append(dict(rect=rect, treat=treats[i], bg=bgs[i % len(bgs)], letter=word[i],
                                    accent=rng.choice(th["accents"])))
        for _ in range(rng.randint(0, 2)):
            pw, ph = int(w * rng.uniform(0.12, 0.3)), int(h * rng.uniform(0.2, 0.45))
            if rng.random() < 0.5:   # snap to the vertical split, like a sub-panel
                x0 = sx_top - pw if rng.random() < 0.5 else sx_top
            else:
                x0 = rng.randrange(0, max(1, w - pw))
            y0 = rng.randrange(0, max(1, h - ph))
            self.panels.append(dict(rect=(max(0, x0), y0, min(w, x0 + pw), y0 + ph),
                                    treat=rng.choice(("smear", "halftone", "solid")),
                                    bg=rng.choice(th["bgs"]), letter=None, accent=rng.choice(th["accents"])))
        for p in self.panels:
            x0, y0, x1, y1 = p["rect"]
            ph_ = max(1, y1 - y0)
            p["cols"] = {x: (rng.randint(2, max(3, ph_ // 3)), rng.uniform(0.6, 1.6), rng.uniform(0, TAU),
                             rng.choice(DRIP_CH)) for x in range(x0, x1) if rng.random() < 0.35}
        for p in self.panels[:4]:
            x0, y0, x1, y1 = p["rect"]
            n = max(3, (x1 - x0) * (y1 - y0) // 110)
            p["lets"] = [self.new_letter(p, t, True) for _ in range(n)]
        self.cov_key = None

    def new_letter(self, p, t, fresh=False):
        rng = self.rng
        x0, y0, x1, y1 = p["rect"]
        size = rng.choice((1, 1, 1, 1, 1, 1, 1, 1, 3, 3, 4, 5, 7))
        life = rng.uniform(3, 8)
        return [rng.uniform(x0 - 2, x1), rng.uniform(y0 - 1, y1), rng.uniform(-0.6, 0.6), rng.uniform(-0.3, 0.3),
                size, t - (rng.uniform(0, life) if fresh else 0), life]

    def lut(self, treat, bg, accent):
        """Per-code pixel colours (col), checker accents (alt), outline fill, halftone dot cells."""
        key = (self.theme, treat, bg, accent, tuple(self.slots))
        got = self._luts.get(key)
        if got:
            return got
        th = self.th
        ramp, cen = th["ramp"], th["centre"]
        col = [bg] * NCODES
        codes = [c for s in self.slots for c in range(1 + s * PER, 1 + (s + 1) * PER)]
        for c in codes:
            pal = cen if KIND[c] == 2 else ramp
            col[c] = pal[SH[c] * len(pal) // 16]
        got = dict(col=col)
        if treat == "checker":
            alt = col[:]
            for c in codes:
                if KIND[c] == 1 and (PIDS[c] * 5 + c // PER) % 3 == 0:
                    alt[c] = accent
            got["alt"] = alt
        elif treat == "outline":
            fill = col[:]
            for c in codes:
                if KIND[c] == 1:
                    fill[c] = th["fill"] or bg
            got["fill"], got["line"] = fill, th["line"]
        elif treat == "halftone":
            dot = [None] * NCODES
            for c in codes:
                if KIND[c] == 1 and SH[c] > 4:
                    dot[c] = ("•", th["ink"], col[c])
            got["dot"] = dot
        self._luts[key] = got
        return got

    def compute_cov(self, t):
        parts = []
        for f in self.flowers:
            fl = f["fl"]
            bloom = 0.5 - 0.5 * math.cos(TAU * t / f["period"] + f["ph"])
            rm = fl.rmap(f["n"], f["R"] * fl.rc, f["R"] * (0.62 + 0.38 * bloom))
            off = int((f["rot"] + f["spin"] * t) / TAU * fl.tt) & fl.mask
            parts.append((fl.table, rm, off, f["ri"], f["tb"], fl.mask))
        key = tuple((f["fl"]._rmap_key, p[2]) for f, p in zip(self.flowers, parts))
        if key == self.cov_key:
            return False
        self.cov_key = key
        ta, ma, oa, ra, ba, mk = parts[0]
        cov = [ta[ma[a] + ((b + oa) & mk)] for a, b in zip(ra, ba)]
        for tb_, mb, ob, rb, bb, mk in parts[1:]:
            cov = [v or tb_[mb[a] + ((b + ob) & mk)] for v, a, b in zip(cov, rb, bb)]
        self.cov = cov
        return True

    def build_base(self):
        w, h, cov = self.w, self.h, self.cov
        rows = [[None] * w for _ in range(h)]
        self.G = None
        for p in self.panels:
            x0, y0, x1, y1 = p["rect"]
            if x1 <= x0 or y1 <= y0:
                continue
            L = self.lut(p["treat"], p["bg"], p["accent"])
            treat, col = p["treat"], L["col"]
            for y in range(y0, y1):
                ot, ob = 2 * y * w, (2 * y + 1) * w
                st, sb = cov[ot + x0:ot + x1], cov[ob + x0:ob + x1]
                if treat == "outline":
                    ct, cb = self.outline_row(2 * y, x0, x1, st, L), self.outline_row(2 * y + 1, x0, x1, sb, L)
                else:
                    ct, cb = [col[v] for v in st], [col[v] for v in sb]
                    if treat == "checker":   # pixel checkerboard: odd x on top rows, even x below
                        alt = L["alt"]
                        k = (x0 + 1) & 1
                        ct[k::2] = [alt[v] for v in st[k::2]]
                        cb[1 - k::2] = [alt[v] for v in sb[1 - k::2]]
                seg = [HB[(a << 8) | b] or halfblock(a, b) for a, b in zip(ct, cb)]
                if treat == "halftone":
                    dot = L["dot"]
                    for i in range(x0 & 1, x1 - x0, 2):
                        d = dot[sb[i]]
                        if d and dot[st[i]]:
                            seg[i] = d
                rows[y][x0:x1] = seg
            p["seeds"] = self.seeds(p) if treat == "smear" else []
        self.base = rows

    def outline_row(self, py, x0, x1, sl, L):
        """Pixel colours for one pixel row: line on petal pixels whose 4-neighbour differs."""
        if self.G is None:
            w = self.w
            zero = [0] * (w + 2)
            self.G = [zero] + [[0] + [GID[v] for v in self.cov[r * w:(r + 1) * w]] + [0]
                               for r in range(2 * self.h)] + [zero]
        G = self.G
        g, up, dn = G[py + 1], G[py], G[py + 2]
        fill, line = L["fill"], L["line"]
        return [line if c and (c != lf or c != rt or c != u or c != d) else fill[v]
                for v, c, lf, rt, u, d in zip(sl, g[x0 + 1:x1 + 1], g[x0:x1], g[x0 + 2:x1 + 2],
                                              up[x0 + 1:x1 + 1], dn[x0 + 1:x1 + 1])]

    def seeds(self, p):
        """Drip origins: bright petal pixels with open space below, in the panel's streak columns."""
        x0, y0, x1, y1 = p["rect"]
        w, cov = self.w, self.cov
        out = []
        for x, (mx, sp, ph, ch) in p["cols"].items():
            for py in range(2 * y0, 2 * y1 - 1):
                v = cov[py * w + x]
                if KIND[v] == 1 and SH[v] >= 10 and not cov[(py + 1) * w + x]:
                    cy = (py + 2) // 2
                    if cy < y1:
                        out.append((x, cy, min(mx, y1 - cy), sp, ph, ch))
        p["drip"] = self.th["drip"]
        return out

    def frame(self, cv, t, frame):
        w = self.w
        if frame % 3 == 0 or self.cov_key is None:
            if self.compute_cov(t):
                self.build_base()
        rows = [r[:] for r in self.base]
        cov = self.cov
        for p in self.panels:
            if p["seeds"]:
                drip = p["drip"]
                nd = len(drip)
                for x, y, mx, sp, ph, ch in p["seeds"]:
                    ln = int(mx * max(0.0, math.sin(t * sp + ph + x * 0.7)) ** 2 + 0.5)
                    for k in range(ln):
                        r = rows[y + k]
                        r[x] = (ch, drip[min(nd - 1, k * nd // (mx + 1))], r[x][2])
        tones = self.th["letters"]
        nt = len(tones)
        for p in self.panels[:4]:
            x0, y0, x1, y1 = p["rect"]
            lets = p["lets"]
            for i, L in enumerate(lets):
                age = t - L[5]
                if age > L[6]:
                    L = lets[i] = self.new_letter(p, t)
                    age = 0.0
                ti = int(math.sin(math.pi * age / L[6]) * nt)
                if ti <= 0:
                    continue
                tone = tones[min(nt - 1, ti)]
                lx, ly = int(L[0] + L[2] * age), int(L[1] + L[3] * age)
                for dx, dy, ch in letter_cells(p["letter"], L[4]):
                    x, y = lx + dx, ly + dy
                    if x0 <= x < x1 and y0 <= y < y1 and not cov[2 * y * w + x] and not cov[(2 * y + 1) * w + x]:
                        r = rows[y]
                        r[x] = (ch, tone, r[x][2])
        cv.cells = rows


# ------------------------------------------------------------------ poster

PHRASES = (
    ("nothing opens all at once", "the light will wait for you"),
    ("slow is still a way of moving", "every petal keeps its own time"),
    ("start small and stay soft", "the rest arrives in its season"),
    ("roots first then the rest", "patience is a kind of sun"),
    ("you can be unfinished", "and still be in flower"),
)
POSTER_WORDS = (("Bloom", "ing"), ("Unfold", "ing"), ("Open", "ing"), ("Petal", ""), ("Bloom", ""))
QUAD = " ▘▝▀▖▌▞▛▗▚▐▜▄▙▟"


def q4(c):
    return tuple(max(0, min(252, int(v) // 4 * 4)) for v in c)


def mix(a, b, k):
    return (a[0] + (b[0] - a[0]) * k, a[1] + (b[1] - a[1]) * k, a[2] + (b[2] - a[2]) * k)


class Poster:
    """A '+'/'-' glyph flower over a soft gradient, a giant cropped serif word, constellation
    lines with coordinate labels, guide lines and justified edge text."""

    def __init__(self, rng):
        self.rng = rng
        self.size = None

    def layout(self, w, h, t):
        rng = self.rng
        self.size, self.w, self.h = (w, h), w, h
        sp = rng.choice(("peony", "peony", "rose", "tulip"))
        self.fl = Flower(sp, random.Random(rng.random()), 0)
        self.fl.build()
        self.cx, self.cy = w * rng.uniform(0.4, 0.6), h * rng.uniform(0.52, 0.6)
        self.R = min(w * 0.42, 2 * h * rng.uniform(0.42, 0.5))
        self.tilt = rng.uniform(0.75, 0.95) if sp != "tulip" else 1.0
        axis = rng.uniform(-0.3, 0.3)
        self.rot, self.spin = rng.uniform(0, TAU), rng.choice((-1, 1)) * rng.uniform(0.03, 0.06)
        self.hy = self.cy   # head centre row, for the glow and guides
        self.stem_y = self.cy + self.R * self.tilt / 2 * 0.7
        if sp == "tulip":   # the polar origin is the cup's base: keep it upright, under the head
            self.rot, self.spin = rng.uniform(-0.1, 0.1), 0.0
            self.stem_y = self.cy = self.cy + self.R / 4
        self.n = int(self.R * Q) + 2
        r_cells = self.R / 2 + 1
        self.cells = [(x, y) for y in range(max(0, int(self.cy - r_cells)), min(h, int(self.cy + r_cells) + 1))
                      for x in range(max(0, int(self.cx - self.R - 1)), min(w, int(self.cx + self.R) + 2))]
        self.ri, self.tb = polar_cells(self.cells, self.cx, self.cy, self.tilt, axis, self.fl.tt, self.n)
        # Concentric tangent glyph per cell: '-' runs where the petal rings run sideways.
        ca, sa, it = math.cos(axis), math.sin(axis), 1 / self.tilt

        def rl(dx, dy):
            u, v = dx * ca + dy * sa, (dy * ca - dx * sa) * it
            return math.hypot(u, v)
        self.dash = []
        for x, y in self.cells:
            dx, dy = x + 0.5 - self.cx, (y + 0.5 - self.cy) * 2
            gx, gy = rl(dx + 0.5, dy) - rl(dx - 0.5, dy), rl(dx, dy + 0.5) - rl(dx, dy - 0.5)
            tx, ty = -gy, gx
            ax, ay = abs(tx), abs(ty)
            self.dash.append("-" if ay < 2 * ax else "|" if ay > 5 * ax else "/" if tx * ty < 0 else "\\")

        # Background: soft blobs over a dark olive base, warm glow behind the flower.
        pal = [(64, 118, 52), (96, 104, 40), (168, 146, 58), (30, 38, 22), (118, 148, 62), (52, 84, 40)]
        blobs = [(rng.uniform(0, w), rng.uniform(0, h), rng.uniform(0.25, 0.55) * w, rng.choice(pal),
                  rng.uniform(0.5, 0.9)) for _ in range(rng.randint(4, 6))]
        glow = (232, 192, 86)
        bgrows = []
        for y in range(h):
            row = []
            for x in range(w):
                c = mix((40, 48, 24), (78, 84, 34), y / max(1, h - 1))
                for bx, by, br, bc, bs in blobs:
                    d2 = ((x - bx) ** 2 + ((y - by) * 2) ** 2) / (br * br)
                    if d2 < 4:
                        c = mix(c, bc, bs * math.exp(-d2))
                d2 = ((x - self.cx) ** 2 + ((y - self.hy) * 2) ** 2) / (self.R * 1.15) ** 2
                c = mix(c, glow, 0.8 * math.exp(-d2 * 1.6))
                row.append(q4(c))
            bgrows.append(row)
        self.bg = bgrows

        # Giant word(s), filled with a pastel gradient.
        top, bot = rng.choice(POSTER_WORDS)
        self.letter_mask = [[0] * w for _ in range(h)]
        rows = [[(" ", None, c) for c in r] for r in bgrows]
        pastel = [(238, 228, 200), (228, 184, 192), (176, 190, 204), (230, 222, 186)]
        rng.shuffle(pastel)
        cap_top = 2
        for word, anchor in ((top, "left"), (bot, "right")):
            if not word:
                continue
            adv = sum(FONT[c][0] for c in word) + 0.06 * (len(word) - 1)
            em = min(w * rng.uniform(1.0, 1.2) / adv, 2 * h * 0.3)
            if anchor == "left":
                x0, ytop = w * rng.uniform(0.02, 0.06), cap_top
            else:
                x0, ytop = w - adv * em * rng.uniform(0.85, 0.95), h - 3 - em * 1.3 / 2
            self.word_cells(rows, word, x0, ytop, em, pastel)
        # Guide lines through the flower centre and a dashed box around the head.
        gc = q4((210, 214, 170))
        cxi, cyi = int(self.cx), int(self.hy)
        bx0, bx1 = int(self.cx - self.R * 0.95), int(self.cx + self.R * 0.95)
        by0, by1 = int(self.hy - self.R * self.tilt / 2 * 0.95), int(self.hy + self.R * self.tilt / 2 * 0.95)
        for x in range(0, w):
            if x % 3 != 2:
                self.put(rows, x, cyi, "-", gc)
        for y in range(0, h):
            if y % 3 != 2:
                self.put(rows, cxi, y, "╎", gc)
        for x in range(bx0, bx1 + 1, 2):
            self.put(rows, x, by0, "-", gc)
            self.put(rows, x, by1, "-", gc)
        for y in range(by0, by1 + 1, 2):
            self.put(rows, bx0, y, "╎", gc)
            self.put(rows, bx1, y, "╎", gc)
        # Edge text, justified across the width.
        tc = q4((236, 230, 200))
        pa, pb = rng.choice(PHRASES)
        for yy, phrase in ((1 if h > 12 else 0, pa), (h - 2 if h > 12 else h - 1, pb)):
            ws = phrase.split()
            total = sum(len(s) for s in ws)
            gap = (w - 6 - total) / max(1, len(ws) - 1)
            x = 3.0
            for s in ws:
                for i, ch in enumerate(s):
                    self.put(rows, int(x) + i, yy, ch, tc)
                x += len(s) + gap
        self.base = rows
        # Constellation: drifting points, each joined to its two nearest neighbours.
        npts = rng.randint(14, 22)
        self.pts = [(rng.uniform(2, w - 3), rng.uniform(2, h - 3), rng.uniform(0.5, 2.5), rng.uniform(0.3, 1.2),
                     rng.uniform(0.05, 0.15), rng.uniform(0, TAU)) for _ in range(npts)]
        self.edges = set()
        for i, (xa, ya, *_r) in enumerate(self.pts):
            near = sorted(range(npts), key=lambda j: (self.pts[j][0] - xa) ** 2 + ((self.pts[j][1] - ya) * 2) ** 2)
            for j in near[1:3]:
                self.edges.add((min(i, j), max(i, j)))
        self.rings = rng.sample(range(npts), min(3, npts))
        self.bend = rng.uniform(-0.12, 0.12) * w
        self.key = None

    def put(self, rows, x, y, ch, fg):
        if 0 <= x < self.w and 0 <= y < self.h:
            c = rows[y][x]
            rows[y][x] = (ch, fg, c[2])

    def word_cells(self, rows, word, x0, ytop, em, pastel):
        w, h = self.w, self.h
        glyphs, xo = [], x0
        for ch in word:
            adv, segs = glyph_segments(ch)
            glyphs.append((xo, xo + adv * em, segs))
            xo += (adv + 0.06) * em
        ylo, yhi = int(ytop), int(ytop + em * 1.32 / 2) + 1
        for y in range(max(0, ylo), min(h, yhi)):
            for x in range(max(0, int(x0)), min(w, int(xo) + 1)):
                bits = 0
                for k, (sx, sy) in enumerate(((0.25, 0.25), (0.75, 0.25), (0.25, 0.75), (0.75, 0.75))):
                    px = x + sx
                    v = ((y + sy) - ytop) * 2 / em
                    for gx0, gx1, segs in glyphs:
                        if gx0 - 0.2 * em <= px <= gx1 + 0.2 * em and ink(segs, (px - gx0) / em, v, em, 0.5):
                            bits |= 1 << k
                            break
                if not bits:
                    continue
                u = x / max(1, w - 1)
                seg = u * (len(pastel) - 1)
                i = min(len(pastel) - 2, int(seg))
                col = mix(pastel[i], pastel[i + 1], seg - i)
                col = q4(mix(col, (250, 246, 236), max(0.0, 0.25 - 0.5 * (y - ylo) / max(1, yhi - ylo))))
                self.letter_mask[y][x] = 1
                rows[y][x] = (" ", None, col) if bits == 15 else (QUAD[bits], col, rows[y][x][2])

    def frame(self, cv, t, frame):
        w, h = self.w, self.h
        rows = [r[:] for r in self.base]
        # Constellation.
        br = Braille(w, h)
        pos = []
        for x0, y0, ax, ay, sp, ph in self.pts:
            pos.append((x0 + ax * math.sin(t * sp + ph), y0 + ay * math.cos(t * sp * 1.3 + ph)))
        for i, j in self.edges:
            (xa, ya), (xb, yb) = pos[i], pos[j]
            br.line(xa * 2, ya * 4, xb * 2, yb * 4)
        for k in self.rings:
            x, y = pos[k]
            rr = 4 + k % 4
            for s in range(36):
                a = s * TAU / 36
                br.dot((x + rr * math.cos(a)) * 2, (y + rr * math.sin(a) / 2) * 4)
        lc = q4((168, 176, 132))
        cv.cells = rows
        br.colors = [[lc] * w for _ in range(h)]
        br.blit(cv)
        rows = cv.cells
        for x, y in pos:
            xi, yi = int(x), int(y)
            self.put(rows, xi, yi, "o", q4((214, 218, 186)))
            label = f"{int(x * 8)},{int(y * 16)}"
            for i, ch in enumerate(label):
                self.put(rows, xi + 2 + i, yi, ch, lc)
        # Flower.
        fl = self.fl
        if frame % 2 == 0 or self.key is None:
            bloom = 0.5 - 0.5 * math.cos(TAU * t / 18.0)
            tip = self.R * (0.82 + 0.18 * bloom)
            rm = fl.rmap(self.n, self.R * fl.rc, tip)
            off = int((self.rot + self.spin * t) / TAU * fl.tt) & fl.mask
            key = (fl._rmap_key, off)
            if key != self.key:
                self.key = key
                tab, mk = fl.table, fl.mask
                self.fcov = [tab[rm[a] + ((b + off) & mk)] for a, b in zip(self.ri, self.tb)]
                self.flower_cells()
        mask = self.letter_mask
        white = (246, 242, 226)
        navy = (28, 38, 72)
        for x, y, ch, fg in self.fcells:
            r = rows[y]
            r[x] = (ch, white, navy) if mask[y][x] else (ch, fg, r[x][2])
        cv.cells = rows

    def flower_cells(self):
        gmap = {}
        for (x, y), v in zip(self.cells, self.fcov):
            if v:
                gmap[(x, y)] = GID[v]
        out = []
        for ((x, y), v), dch in zip(zip(self.cells, self.fcov), self.dash):
            if not v:
                continue
            g = GID[v]
            s = SH[v]
            # '+' on the silhouette, and along the lower lip of each overlapping petal.
            edge = (not gmap.get((x - 1, y)) or not gmap.get((x + 1, y)) or not gmap.get((x, y - 1))
                    or gmap.get((x, y + 1)) != g)
            if edge:
                ch = "+"
            elif s < 4:
                continue
            else:
                ch = dch if (x * 7 + y * 3) % 11 else " "
            k = s / 15
            out.append((x, y, ch, q4(mix((214, 196, 140), (252, 248, 232), k))))
        # Stem of '+' from under the head down to the bottom edge.
        x0, y0 = self.cx, self.stem_y
        bend = self.bend
        n = max(1, self.h - int(y0))
        for k in range(n):
            u = k / n
            out.append((int(x0 + bend * u * u), int(y0) + k, "+", (244, 238, 214)))
        self.fcells = [c for c in out if 0 <= c[0] < self.w and 0 <= c[1] < self.h]


# ------------------------------------------------------------------ meadow

EARTH_CH = ".,'`:"


def hb_rgb(a, b):
    return (" ", None, a) if a == b else ("▀", a, b)


class Meadow:
    """A truecolour half-block field: brown earth with leaf strokes and a light glyph
    texture, 20-35 violet blooms with cream centres and dark rims, swaying, breathing,
    opening, while the field pans slowly. World is 1.5 screens wide and wraps."""

    VARIANTS = 6

    def __init__(self, rng):
        self.rng = rng
        self.size = None
        self.flowers = None

    def layout(self, w, h, t):
        rng = self.rng
        self.size, self.w, self.h = (w, h), w, h
        W = self.W = w + max(8, w // 2)
        PH = 2 * h
        if self.flowers is None:
            self.flowers = []
            for v in range(self.VARIANTS):
                fl = Flower("orchid", random.Random(rng.random()), v, tt=256, tr=32, trc=8)
                fl.build()
                hue = rng.uniform(-1, 1)
                base = (88 + 16 * hue, 72 - 8 * hue, 168 + 12 * hue)
                tipc = (196 + 14 * hue, 198, 248)
                lut = [None] * NCODES
                for c in range(1 + v * PER, 1 + (v + 1) * PER):
                    s = SH[c] / 15
                    if KIND[c] == 2:
                        lut[c] = q4(mix((104, 56, 146), (246, 230, 170), min(1.0, max(0.0, (s - 0.3) / 0.5))))
                    else:
                        lut[c] = q4(mix(base, tipc, s))
                self.flowers.append((fl, lut))

        def grid(nx, ny):
            return [[rng.random() for _ in range(nx + 1)] for _ in range(ny + 2)]
        val = [[0.0] * W for _ in range(PH)]
        for sp, amp in ((14, 0.6), (5, 0.3), (2, 0.1)):
            g = grid(W // sp + 1, PH // sp + 1)
            nx = len(g[0]) - 1
            for y in range(PH):
                fy = y / sp
                iy = int(fy)
                ty = fy - iy
                ty = ty * ty * (3 - 2 * ty)
                r0, r1, vr = g[iy], g[iy + 1], val[y]
                for x in range(W):
                    fx = x / sp
                    ix = int(fx)
                    tx = fx - ix
                    tx = tx * tx * (3 - 2 * tx)
                    i0, i1 = ix % nx, (ix + 1) % nx
                    a = r0[i0] + (r0[i1] - r0[i0]) * tx
                    b = r1[i0] + (r1[i1] - r1[i0]) * tx
                    vr[x] += amp * (a + (b - a) * ty)
        px = [[mix((40, 26, 15), (132, 88, 50), v * v) for v in row] for row in val]
        for _ in range(int(W * PH / 160)):
            x, y = rng.uniform(0, W), rng.uniform(0, PH)
            ang = rng.uniform(-2.5, -0.6)
            ln = rng.uniform(8, 28)
            leaf = rng.random() < 0.6
            c0 = rng.choice(((82, 74, 38), (104, 92, 46), (70, 86, 42), (124, 96, 52)))
            steps = int(ln * 1.5)
            for k in range(steps):
                u = k / steps
                cx, cy = x + math.cos(ang) * ln * u, y + math.sin(ang) * ln * u
                wid = math.sin(math.pi * u) * 2.2 if leaf else 0.5
                for dx in range(-int(wid), int(wid) + 1):
                    xi, yi = int(cx + dx) % W, int(cy)
                    if 0 <= yi < PH:
                        k2 = (0.75 + 0.45 * u) * (1.12 if dx == 0 and leaf else 1.0)
                        px[yi][xi] = mix(px[yi][xi], tuple(c * k2 for c in c0), 0.85)
        cells = []
        for y in range(h):
            top, bot = px[2 * y], px[2 * y + 1]
            row = []
            for x in range(W):
                a, b = q4(top[x]), q4(bot[x])
                if rng.random() < 0.3:
                    m = mix(top[x], bot[x], 0.5)
                    row.append((rng.choice(EARTH_CH), q4(tuple(min(250, c * 1.45) for c in m)), q4(m)))
                else:
                    row.append(hb_rgb(a, b))
            cells.append(row + row)
        self.earth = cells
        n = rng.randint(20, 35)
        self.inst = [self.new_inst(t - rng.uniform(3, 20) if rng.random() < 0.8 else t + rng.uniform(0, 15))
                     for _ in range(n)]
        self.inst.sort(key=lambda f: f["wpy"])
        self.next_swap = t + 2.5
        self.cache_key = None

    def new_inst(self, born, wx=None):
        rng = self.rng
        v = rng.randrange(self.VARIANTS)
        R = rng.uniform(10, 20)
        wpy = rng.uniform(-2, 2 * self.h + 2)
        f = dict(v=v, wx=rng.uniform(0, self.W) if wx is None else wx, wpy=wpy, R=R, born=born,
                 rot=rng.uniform(0, TAU), ph=rng.uniform(0, TAU), sway=rng.uniform(0.04, 0.09), key=None, cells=())
        fl = self.flowers[v][0]
        rr = int(R) + 3
        rel = [(dx, dy) for dy in range(-rr, rr + 1) for dx in range(-rr, rr + 1)]
        f["n"] = int(R * Q) + 2
        ri, tb = polar_cells(rel, f["wx"] % 1, wpy % 1, rng.uniform(0.65, 1.0), rng.uniform(0, TAU), fl.tt, f["n"], ys=1)
        f["pre"] = list(zip(rel, ri, tb))
        f["ix"], f["ipy"] = int(f["wx"]), int(math.floor(wpy))
        return f

    def raster(self, f, t):
        """Cells (dx, row, top, bottom, full cell or None) for this bloom: a dark rim and drop
        shadow first, so overlapping blooms stay separate, then the petals."""
        age = t - f["born"]
        op = min(1.0, age / 3.0)
        op = op * op * (3 - 2 * op)
        fl, lut = self.flowers[f["v"]]
        tip = f["R"] * op * (1 + 0.04 * math.sin(t * 0.7 + f["ph"]))
        rot = f["rot"] + f["sway"] * math.sin(t * 0.45 + f["ph"])
        off = int(rot / TAU * fl.tt) & fl.mask
        rcu = f["R"] * fl.rc * min(1.0, 0.4 + op)
        key = (off, round(tip * 2), round(rcu * 2))
        if key == f["key"]:
            return
        f["key"] = key
        rm = fl.rmap(f["n"], rcu, max(rcu + 0.01, tip))
        tab, mk = fl.table, fl.mask
        petal = {}
        for d, a, b in f["pre"]:
            v = tab[rm[a] + ((b + off) & mk)]
            if v:
                petal[d] = lut[v]
        pix = {}
        rim, drop = (16, 10, 8), (26, 18, 12)
        for (dx, dy) in petal:
            for nb, c in (((dx + 1, dy + 2), drop), ((dx + 2, dy + 1), drop), ((dx - 1, dy), rim),
                          ((dx + 1, dy), rim), ((dx, dy - 1), rim), ((dx, dy + 1), rim)):
                if nb not in petal:
                    pix[nb] = c
        pix.update(petal)
        ipy = f["ipy"]
        cells = {}
        for (dx, dy), c in pix.items():
            py = ipy + dy
            cell = cells.setdefault((dx, py >> 1), [None, None])
            cell[py & 1] = c
        f["cells"] = [(dx, cy, a, b, hb_rgb(a, b) if a is not None and b is not None else None)
                      for (dx, cy), (a, b) in cells.items()]

    def frame(self, cv, t, frame):
        w, h, W = self.w, self.h, self.W
        px = int(t * 0.7) % W
        if t >= self.next_swap:   # a hidden bloom moves into view and opens there
            self.next_swap = t + self.rng.uniform(2, 3.5)
            hidden = [i for i, f in enumerate(self.inst) if w + f["R"] < (f["ix"] - px) % W < W - f["R"] - 4]
            if hidden:
                i = self.rng.choice(hidden)
                self.inst[i] = self.new_inst(t, wx=(px + self.rng.uniform(0, w)) % W)
                self.inst.sort(key=lambda f: f["wpy"])
                self.cache_key = None
        key = (px, frame // 3)
        if key == self.cache_key:
            cv.cells = [r[:] for r in self.cached]
            return
        self.cache_key = key
        rows = [r[px:px + w] for r in self.earth]
        for f in self.inst:
            sx = (f["ix"] - px) % W
            if sx > W - f["R"] - 4:
                sx -= W
            if sx < -f["R"] - 4 or sx > w + f["R"] + 4 or t <= f["born"]:
                continue
            self.raster(f, t)
            for dx, cy, a, b, full in f["cells"]:
                x = sx + dx
                if 0 <= x < w and 0 <= cy < h:
                    r = rows[cy]
                    if full:
                        r[x] = full
                    else:
                        ch, fg, bg = r[x]
                        ta, tb = (fg, bg) if ch == "▀" else (bg, bg)
                        r[x] = hb_rgb(ta if a is None else a, tb if b is None else b)
        self.cached = rows
        cv.cells = [r[:] for r in rows]


# ------------------------------------------------------------------ director

class Director:
    def __init__(self, args):
        self.seed = args.seed if args.seed is not None else random.randrange(1 << 30)
        self.rng = random.Random(self.seed)
        self.pinned = args.theme
        self.order = []
        self.pool = [None] * POOL
        self.panels = Panels(self.rng, self.pool)
        self.poster = Poster(self.rng)
        self.meadow = Meadow(self.rng)
        self.scene = None
        self.size = None
        self.last_cut = -10.0
        self.fps = max(1.0, args.fps)

    def next_theme(self):
        if self.pinned:
            return self.pinned
        if not self.order:
            last = getattr(self, "theme", None)
            order = list(SCENES)
            self.rng.shuffle(order)
            if order[0] == last:
                order.append(order.pop(0))
            self.order = order
        return self.order.pop(0)

    def start(self, theme, w, h, t):
        self.theme = theme
        if theme in PANEL_THEMES:
            self.scene = self.panels
            self.cuts_left = 2
            self.panels.cut(theme, w, h, t)
            self.next_cut = t + self.rng.uniform(4, 6)
        else:
            self.scene = self.poster if theme == "poster" else self.meadow
            self.scene.layout(w, h, t)
            self.next_cut = t + self.rng.uniform(10, 14)
        self.mark_cut(t)

    def mark_cut(self, t):
        if t > 0:
            audio.sfx("glitch", vol=0.6)
        self.last_cut = t

    def step(self, cv, frame):
        t = frame / self.fps
        w, h = cv.w, cv.h
        if (w, h) != self.size:
            self.size = (w, h)
            self.start(getattr(self, "theme", None) or self.next_theme(), w, h, t)
        elif t >= self.next_cut:
            if self.scene is self.panels and self.cuts_left > 1:
                self.cuts_left -= 1
                self.panels.cut(self.theme, w, h, t)
                self.next_cut = t + self.rng.uniform(4, 6)
                self.mark_cut(t)
            else:
                self.start(self.next_theme(), w, h, t)
        self.scene.frame(cv, t, frame)
        if t - self.last_cut < GLITCH_SECS:
            g = random.Random(self.seed * 100003 + frame)
            rows = cv.cells
            for _ in range(g.randint(3, 6)):
                y0, hh = g.randrange(h), g.randint(1, max(1, h // 8))
                k = g.randint(2, max(3, w // 10)) * g.choice((-1, 1))
                for y in range(y0, min(h, y0 + hh)):
                    r = rows[y]
                    rows[y] = r[-k:] + r[:-k]


def main():
    p = term.make_parser("glitch-collage daisies, a glyph flower poster and a mosaic meadow", fps=12)
    p.add_argument("--seed", type=int, default=None, help="random seed")
    p.add_argument("--theme", choices=SCENES, default=None,
                   help="stay on one theme or scene (default: cycle through all in random order)")
    args = p.parse_args()
    d = Director(args)
    return term.run(args, d.step, music="daisy")


if __name__ == "__main__":
    sys.exit(main())
