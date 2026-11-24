#!/usr/bin/env python3
"""A family of glowing mathematical point clouds that slowly turn into one another.

Forms (see --list-forms): original, the exact port of @yuruyurau's p5.js tweet; jelly,
ribbon and knot; medusa, ammonite, torus knot (3,8) and tesseract after @crabhive's
Mathematical Art Generator, seen through a slow orbiting 3D camera; and breathing, a
pulsing knotted filigree after @justin_lister.

Points (or, for the strand forms, unbroken rasterised strands) add up per braille cell,
near ones counting more than far ones, and the sum goes through a 1 - exp(-k v) tone
curve, so overlaps glow and sparse strands stay delicate. A cell's colour is that glow plus
the average colour parameter of its points (filament index, knot parameter, 4D depth)
looked up in an OKLab palette. In truecolor the glow is also blurred into a soft coloured
background halo, and the whole canvas is painted dark grey (#1e1e1e) under it.

The palette is a random one on launch, or the form's own (green/cyan for the crabhive
forms, neon for breathing); it slowly cross-fades to another random one every 30-60 s
and to a form's own palette when that form arrives. --palette NAME pins one and
--no-drift holds the launch palette.

Usage: python3 swirl.py [--form NAME|1-3] [--list-forms] [--palette NAME] [--drift|--no-drift]
                        [--points N] [--speed X] [--seed N]
"""
import math
import os
from operator import add as _add
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
from fun import audio, term  # noqa: E402

META = {'name': 'swirl',
        'kind': 'watch',
        'blurb': 'A family of glowing mathematical point clouds that turn into one another',
        'credit': [{'type': 'taken from',
                    'who': 'yuruyurau (@yuruyurau), the original form',
                    'url': 'https://x.com/yuruyurau/status/2080977918914969636'},
                   {'type': 'inspired by',
                    'who': 'Wil.D (@crabhive), Mathematical Art Generator: medusa, ammonite, '
                           'torus knot, tesseract',
                    'url': 'https://x.com/crabhive/status/2081064705905369429'},
                   {'type': 'inspired by',
                    'who': 'Justin Lister (@justin_lister), Pulsating breathing',
                    'url': 'https://x.com/justin_lister/status/2081705225182953560'}]}

TAU = 2 * math.pi
FIBRES = 32
HOLD = 14.0    # seconds each form is shown
CAPTION = 3.0  # seconds the form's name shows at the start of each form
FADE = 6.0     # seconds of cross-fade between forms
LEVELS = 16    # glow levels in the colour table
BINS = 8       # colour-parameter bins in the colour table
QUANT = 4      # frames between colour table updates while anything fades
TONE = 1.2     # default tone curve gain (see Form.tone)
DENSITY = 0.16    # points per braille sub-pixel before a form's own cap
FADE_LEN = (8.0, 15.0)    # seconds a palette cross-fade takes
FADE_GAP = (30.0, 60.0)   # seconds between the end of one fade and the start of the next
# Gradient stops (dim -> bright) in sRGB; the first is the original greyscale look.
PALETTES = {
    "silver": [(48, 48, 48), (140, 140, 140), (238, 238, 238)],
    "ice": [(18, 36, 90), (60, 130, 215), (180, 225, 255), (255, 255, 255)],
    "rose": [(90, 20, 60), (220, 90, 120), (255, 170, 150), (255, 228, 208)],
    "mint": [(8, 56, 62), (24, 150, 140), (120, 228, 178), (222, 255, 236)],
    "violet": [(48, 18, 108), (128, 48, 200), (220, 80, 220), (255, 192, 250)],
    "amber": [(78, 38, 8), (200, 110, 20), (250, 182, 40), (255, 240, 172)],
    "aurora": [(14, 100, 66), (56, 196, 128), (108, 140, 222), (176, 92, 232)],
    "sunset": [(52, 18, 84), (150, 40, 112), (236, 92, 92), (255, 176, 104)],
    "ocean": [(8, 28, 72), (20, 90, 152), (40, 182, 192), (204, 250, 240)],
    "ember": [(70, 10, 12), (190, 40, 20), (255, 120, 30), (255, 222, 144)],
    "jade": [(10, 70, 40), (30, 160, 80), (60, 210, 170), (190, 250, 150), (245, 255, 240)],
    "neon": [(30, 60, 210), (70, 130, 255), (190, 70, 240), (255, 70, 170), (255, 120, 50),
             (255, 190, 110)],
}
SAMPLES = 33   # OKLab samples kept per palette
BG = (30, 30, 30)    # canvas background painted in truecolor, the user's terminal grey
HALO_LEVELS = 6      # background glow levels (truecolor only)
HALO_GAIN = 0.9      # tone curve gain of the blurred glow, relative to TONE
HALO_START = 0.3     # blurred glow below this (after the tone curve) leaves the background alone
HALO_MAX = 0.2       # strongest background tint, as a fraction of the way to the glow colour
BITS = (0x01, 0x08, 0x02, 0x10, 0x04, 0x20, 0x40, 0x80)  # index (y&3)*2 + (x&1)
CHARS = [chr(0x2800 + i) for i in range(256)]
sin, cos, sqrt, exp = math.sin, math.cos, math.sqrt, math.exp


def _lab(rgb):
    """sRGB (0-255) -> OKLab."""
    r, g, b = [(v / 255 / 12.92 if v <= 10.3 else ((v / 255 + 0.055) / 1.055) ** 2.4) for v in rgb]
    l = (0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b) ** (1 / 3)
    m = (0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b) ** (1 / 3)
    s_ = (0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b) ** (1 / 3)
    return (0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s_,
            1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s_,
            0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s_)


def _rgb(lab):
    """OKLab -> sRGB tuple of ints, clamped to the gamut."""
    L, a, b = lab
    l, m, s_ = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3, \
               (L - 0.1055613458 * a - 0.0638541728 * b) ** 3, \
               (L - 0.0894841775 * a - 1.2914855480 * b) ** 3
    out = []
    for v in (4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s_,
              -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s_,
              -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s_):
        v = min(1.0, max(0.0, v))
        out.append(round(255 * (12.92 * v if v <= 0.0031308 else 1.055 * v ** (1 / 2.4) - 0.055)))
    return tuple(out)


def _samples(stops):
    """SAMPLES OKLab colours evenly along a gradient."""
    labs = [_lab(c) for c in stops]
    out = []
    for i in range(SAMPLES):
        x = i / (SAMPLES - 1) * (len(labs) - 1)
        k = min(int(x), len(labs) - 2)
        f = x - k
        out.append(tuple(p + (q - p) * f for p, q in zip(labs[k], labs[k + 1])))
    return out


def _mix(a, b, m):
    return [tuple(p + (q - p) * m for p, q in zip(x, y)) for x, y in zip(a, b)]


def build_lut(samples, hue):
    """LEVELS x BINS colours, flat (level * BINS + bin). The gradient position is the glow,
    pulled towards the colour parameter by `hue`; lightness also follows the glow, with a
    floor so a lone dot still reads on a dark grey terminal, and the brightest levels bloom
    towards white."""
    out = []
    top = SAMPLES - 1
    for lv in range(LEVELS):
        g = (lv + 1) / LEVELS
        for b in range(BINS):
            pos = (1 - hue) * g + hue * (b + 0.5) / BINS
            L, A, B = samples[int(min(1.0, pos) * top + 0.5)]
            L = max(0.62, L * (0.72 + 0.3 * g) + 0.14 * g)
            w = max(0.0, g - 0.62) * 1.1
            out.append(_rgb((L + (0.97 - L) * w, A * (1 - w), B * (1 - w))))
    return out


def build_halo(lut, hue):
    """HALO_LEVELS x BINS background tints: BG moved part way to a bright glow colour."""
    out = []
    for lv in range(HALO_LEVELS):
        m = lv / (HALO_LEVELS - 1) * HALO_MAX
        for b in range(BINS):
            c = lut[(LEVELS // 3) * BINS + b]
            out.append(tuple(round(p + (q - p) * m) for p, q in zip(BG, c)))
    return out


class Drift:
    """The palette: one, or a slow cross-fade to the next. The state only changes every QUANT
    frames, so the colour table (and the bytes the diff renderer sends) changes a few times a
    second at most."""

    def __init__(self, rng, name, drifting):
        self.rng, self.drifting = rng, drifting
        self.tables = {n: _samples(c) for n, c in PALETTES.items()}
        self.cur, self.nxt = name, None
        self.a, self.b = self.tables[name], None
        self.fade_t0 = self.fade_len = 0.0
        self.next_at = rng.uniform(*FADE_GAP)
        self.m = 0.0

    def goto(self, name, t, secs):
        """Start fading to palette `name`, from wherever the current fade has got to."""
        if not self.drifting or name == (self.nxt or self.cur):
            return
        if self.b is not None:
            self.a = _mix(self.a, self.b, self.m * self.m * (3 - 2 * self.m))
        self.nxt, self.b, self.m = name, self.tables[name], 0.0
        self.fade_t0, self.fade_len = t, secs

    def update(self, t, frame):
        """Advance the fade; returns (key, samples), key changing only when the colours do."""
        if self.drifting and not frame % QUANT:
            if self.nxt is None and t >= self.next_at:
                self.goto(self.rng.choice([n for n in PALETTES if n != self.cur]), t,
                          self.rng.uniform(*FADE_LEN))
            if self.nxt is not None:
                self.m = (t - self.fade_t0) / self.fade_len
                if self.m >= 1:
                    self.cur, self.nxt, self.a, self.b, self.m = self.nxt, None, self.b, None, 0.0
                    self.next_at = t + self.rng.uniform(*FADE_GAP)
        if self.b is None:
            return (self.cur,), self.a
        m = self.m * self.m * (3 - 2 * self.m)
        return (self.cur, self.nxt, self.fade_t0, round(m, 3)), _mix(self.a, self.b, m)


def spread(m):
    """Indices 0..m-1 ordered so that every prefix is an even sample of the whole (golden-ratio
    order): a form drawn with its first n points looks like a thinner copy of itself."""
    return sorted(range(m), key=lambda i: (i * 0.6180339887498949) % 1.0)


def permute(order, *lists):
    return [[a[i] for i in order] for a in lists]


class Form:
    """A point cloud: fill(t, n) writes the first n points into the flat lists X, Y, Z
    (and C, the colour parameter in [0, 1), when it moves). Flat forms are 2D and drawn
    without the camera, mapping X, Y through scale and centre."""
    name = ""
    blurb = ""
    flat = False
    lines = False
    palette = None   # suggested palette, used unless --palette pins one
    hue = 0.3        # how much the colour parameter (vs the glow) picks the colour
    cap = 4200       # most points drawn per frame
    yaw = 0.14       # camera orbit speed, radians per second
    swing = 0.0      # nonzero: the camera swings +- this many radians instead of orbiting
    pitch = 0.32
    zoom = 1.0
    tone = TONE      # tone curve gain: a cell at the mean density glows 1 - exp(-tone)
    scale, centre = 1.0, (0.0, 0.0)

    def alloc(self, m):
        self.m = m
        self.X, self.Y, self.Z = [0.0] * m, [0.0] * m, [0.0] * m


class Original(Form):
    """@yuruyurau's tweet, term for term:
        a=(y,d=mag(k=(4+cos(i/9-t*2))*cos(i/35),e=y/7-13)+sin(e/9+t/2)-4)=>point((q=2*sin(k*3)
          -y/35*k*(9+k*sin(cos(e)*9-d*2+t)))+40*cos(c=d-t)+200,q*sin(c)+d*35)
        t=0,draw=$=>{t||createCanvas(w=400,w);background(9).stroke(w,96);for(t+=PI/80,i=1e4;i--;)a(i/235)}
    on its 400x400 canvas, t advancing PI/80 per 60 fps frame. Everything that depends only
    on i is precomputed."""
    name, blurb, flat, palette, hue, cap = "original", "yuruyurau's p5.js tweet, ported exactly", True, "silver", 0.15, 6000
    rate = math.pi / 80 * 60
    scale, centre = 1 / 175, (198.0, 212.0)

    def __init__(self, rng):
        # cos(i/9 - 2t) and sin(e/9 + t/2) are expanded by the angle-sum identities, so the
        # i-only halves are precomputed and a frame needs four trig calls per point, not six.
        order = spread(10000)
        b4, bc, bs, sp, cp, e2, ce9, ye, c = ([] for _ in range(9))
        for i in order:
            y = i / 235
            e = y / 7 - 13
            b = cos(i / 35)
            b4.append(4 * b)
            bc.append(b * cos(i / 9))
            bs.append(b * sin(i / 9))
            sp.append(sin(e / 9))
            cp.append(cos(e / 9))
            e2.append(e * e)
            ce9.append(cos(e) * 9)
            ye.append(y / 35)
            c.append(i / 10000)
        self.k = (b4, bc, bs, sp, cp, e2, ce9, ye)
        self.alloc(10000)
        self.C = c

    def fill(self, t, n):
        t *= self.rate
        c2, s2, ch, sh = cos(t * 2), sin(t * 2), cos(t / 2), sin(t / 2)
        X, Y = self.X, self.Y
        for j, b4, bc, bs, sp, cp, ee, r, s in zip(range(n), *self.k):
            k = b4 + bc * c2 + bs * s2                    # (4 + cos(i/9 - 2t)) * cos(i/35)
            d = sqrt(k * k + ee) + sp * ch + cp * sh - 4  # mag(k, e) + sin(e/9 + t/2) - 4
            q = 2 * sin(k * 3) - s * k * (9 + k * sin(r - d * 2 + t))
            c = d - t
            X[j] = q + 40 * cos(c) + 200
            Y[j] = q * sin(c) + d * 35


class Fibres(Form):
    """Shared layout of the jelly, ribbon and knot forms: FIBRES smooth curves with their dots
    spread along them, so neighbouring fibres read as strands."""
    cap = 6000

    def __init__(self, rng):
        m = 6000
        per = m // FIBRES
        order = spread(per * FIBRES)
        ph = [(i // per) / FIBRES * TAU + rng.uniform(-.02, .02) for i in range(per * FIBRES)]
        u = [(i % per + 0.5) / per for i in range(per * FIBRES)]
        self.ph, self.u = permute(order, ph, u)
        self.cph = [cos(p) for p in self.ph]
        self.sph = [sin(p) for p in self.ph]
        self.th = [x * TAU for x in self.u]
        self.seed = rng.uniform(0, TAU)
        self.alloc(len(self.ph))
        self.C = [p / TAU % 1.0 for p in self.ph]


class Jelly(Fibres):
    name, blurb = "jelly", "a pulsing bell with trailing tentacles"
    pitch, zoom = 0.12, 0.95

    def __init__(self, rng):
        super().__init__(rng)
        # per dot: (in the bell, then sin a, cos a, a 5 + ph 3; else q, q 6 + ph 4)
        self.pre = []
        for ph, u in zip(self.ph, self.u):
            if u < 0.45:
                a = u * 2.9
                self.pre.append((True, sin(a), cos(a), a * 5 + ph * 3))
            else:
                q = (u - 0.45) * 1.818
                self.pre.append((False, q, 0.0, q * 6 + ph * 4))

    def fill(self, t, n):
        pulse = 1 + 0.12 * sin(t * 1.1)
        t16, t14 = t * 1.6, t * 1.4
        bell, rim = 0.75 * (2 - pulse), 0.95 * pulse
        X, Y, Z = self.X, self.Y, self.Z
        for j, (top, p, q, arg), ca, sa in zip(range(n), self.pre, self.cph, self.sph):
            if top:
                rho = p * (1 + 0.08 * sin(arg - t16)) * pulse
                y = -0.55 + q * bell
            else:
                rho = rim * (1 - 0.55 * p) + 0.1 * p * sin(arg - t14)
                y = 0.18 + p * 0.85
            X[j] = rho * ca * 0.85
            Y[j] = y * 0.8 - 0.1
            Z[j] = rho * sa * 0.85


class Ribbon(Fibres):
    name, blurb, flat = "ribbon", "closed rose curves fanning into a twisting ribbon", True
    scale = 1.0

    def fill(self, t, n):
        a, b = t * 0.21 + self.seed, t * 0.3
        X, Y = self.X, self.Y
        for j, ph, th in zip(range(n), self.ph, self.th):
            k = th + 0.7 * sin(ph + a)
            r = 0.62 + 0.3 * sin(3 * k + ph * 0.5 + b) * cos(ph * 0.5 - a)
            X[j] = r * cos(k + a * 0.5)
            Y[j] = r * sin(k + a * 0.5)


class Knot(Fibres):
    name, blurb = "knot", "a trefoil tube of braided strands flowing along it"
    zoom = 0.8

    def __init__(self, rng):
        super().__init__(rng)
        self.tube = frames(trefoil, 720)
        # a strand's angle round the tube is ph + 3 u tau + t / 2; its t-free part is precomputed
        self.ca = [0.07 * cos(ph + 3 * u * TAU) for ph, u in zip(self.ph, self.u)]
        self.sa = [0.07 * sin(ph + 3 * u * TAU) for ph, u in zip(self.ph, self.u)]

    def fill(self, t, n):
        flow = t * 0.05
        tab, m = self.tube, len(self.tube)
        ct, st = cos(t * 0.5), sin(t * 0.5)
        X, Y, Z = self.X, self.Y, self.Z
        for j, u, ca, sa in zip(range(n), self.u, self.ca, self.sa):
            px, py, pz, nx, ny, nz, bx, by, bz = tab[int((u + flow) * m) % m]
            c, s_ = ca * ct - sa * st, sa * ct + ca * st
            X[j] = px + c * nx + s_ * bx
            Y[j] = py + c * ny + s_ * by
            Z[j] = pz + c * nz + s_ * bz


class Medusa(Form):
    """A broad dome of meridians and rings whose pulse runs down long ordered tentacles; a
    slow current bends the tentacles into an S. Colour is the filament index."""
    name, blurb, palette, hue, cap = "medusa", "a pulsing bell with long ordered tentacles", "jade", 0.45, 6000
    pitch, zoom = 0.16, 0.9
    fil, rim_a = 24, 1.45

    def __init__(self, rng):
        fil = self.fil
        canopy, tent = [], []
        for f in range(fil):
            ph = (f + 0.5) / fil * TAU
            for i in range(36):
                canopy.append((ph, (i + 0.5) / 36 * self.rim_a))
            ln, po = rng.uniform(0.55, 1.0), rng.uniform(-1, 1)
            k = int(150 * ln)
            for i in range(k):
                tent.append((ph, (i + 0.5) / k * ln, f / fil, po))
        for a in (0.7, self.rim_a):
            k = int(sin(a) * 300)
            canopy += [((i + 0.5) / k * TAU, a) for i in range(k)]
        cph, ca = permute(spread(len(canopy)), *zip(*canopy))
        tph, tq, tc, tpo = permute(spread(len(tent)), *zip(*tent))
        self.nc = len(canopy)
        self.share = self.nc / (self.nc + len(tent))
        self.alloc(self.nc + len(tent))
        self.cc = [cos(p) for p in cph] + [cos(p) for p in tph]
        self.cs = [sin(p) for p in cph] + [sin(p) for p in tph]
        self.can = [(sin(a), 1 - cos(a), a * 4, p * 8) for p, a in zip(cph, ca)]
        self.tent = (tph, tq, tpo)
        self.C = [p / TAU % 1.0 for p in cph] + list(tc)

    def fill(self, t, n):
        X, Y, Z, cc, cs = self.X, self.Y, self.Z, self.cc, self.cs
        nc = int(n * self.share)
        w = t * 1.25
        R = 0.52 * (1 + 0.1 * sin(w))
        H = 0.4 * (1 - 0.14 * sin(w))
        w15 = w * 1.5
        for j, (sa, ca1, a4, p8), c, s_ in zip(range(nc), self.can, cc, cs):
            rho = R * sa * (1 + 0.05 * sin(a4 - w15) + 0.03 * sin(p8))
            X[j] = rho * c
            Z[j] = rho * s_
            Y[j] = -0.85 + H * ca1
        rim = -0.85 + H * (1 - cos(self.rim_a))
        rr = 0.5 * sin(self.rim_a)
        t2, t06, t045 = t * 2, t * 0.6, t * 0.45
        nc0 = self.nc
        for j, ph, q, po in zip(range(nc0, nc0 + n - nc), *self.tent):
            rho = rr * (1 + 0.12 * sin(w - q * 2.6)) * (1 - 0.35 * q) + 0.05 * q * sin(q * 7 - t2 + ph * 3)
            X[j] = rho * cc[j] + 0.32 * q * q * sin(q * 3.0 - t06 + po)
            Z[j] = rho * cs[j] + 0.22 * q * q * cos(q * 2.4 - t045 + po)
            Y[j] = rim + q * 1.5 - 0.12 * q * q

    def ranges(self, n):
        nc = int(n * self.share)
        return ((0, nc), (self.nc, self.nc + n - nc))


class Strands(Form):
    """A form drawn as continuous strands: consecutive points of a strand are joined by
    rasterised segments, so curves stay unbroken at any zoom. fill(t) writes every point;
    W (per-point brightness) and NX, NY, NZ (a surface normal, lit by how squarely it faces
    the camera) are optional. segs lists each segment's end index in golden-ratio order, so
    a prefix of it is an even thinning of the whole form (used by cross-fades)."""
    lines = True
    W = None
    N = None

    def build(self, strands):
        """strands: (rows of per-point attributes, closed); returns the attribute columns."""
        rows, segs = [], []
        for pts, closed in strands:
            if closed:
                pts = pts + pts[:1]
            start = len(rows)
            rows.extend(pts)
            segs.extend(range(start + 1, start + len(pts)))
        self.segs = [segs[i] for i in spread(len(segs))]
        self.alloc(len(rows))
        self.SX, self.SY, self.SW = [0.0] * self.m, [0.0] * self.m, [0.0] * self.m
        return [list(c) for c in zip(*rows)]


class Ammonite(Strands):
    """A log-spiral shell: ribbed rings and a few spiral strands around a centre line
    r = a e^(b theta), the tube growing with the spiral so each whorl wraps the last. A slow
    swell runs out along the ribs. Colour walks from the centre to the aperture."""
    name, blurb, palette, hue = "ammonite", "a log-spiral shell of ribbed whorls", "jade", 0.5
    yaw, swing, pitch, zoom = 0.11, 0.8, 0.18, 0.95
    bins = 240

    def __init__(self, rng):
        b, lo = 0.125, -4.2 * math.pi
        bins = self.bins

        def pt(th, ps):
            rad = 0.68 * exp(b * th)
            tube = 0.47 * rad
            u = (th - lo) / -lo
            return (min(bins - 1, int(u * bins)), rad * cos(th) - 0.12, rad * sin(th) + 0.03,
                    tube * cos(ps) * cos(th), tube * cos(ps) * sin(th), tube * sin(ps) * 0.85, u * 0.999)
        strands = []
        ribs = 52
        for r in range(ribs):
            th = lo + (r + 0.7) / ribs * -lo
            k = max(8, int(TAU * 0.47 * 0.68 * exp(b * th) * 30))
            strands.append(([pt(th, i / k * TAU) for i in range(k)], True))
        for ps in (0.0, 0.7, -0.7, 1.4, -1.4, 2.2, -2.2, math.pi):
            steps = 260
            strands.append(([pt(lo + (i + 0.5) / steps * -lo, ps) for i in range(steps)], False))
        self.bin, self.cx, self.cy, self.dx, self.dy, self.dz, self.C = self.build(strands)

    def fill(self, t):
        X, Y, Z = self.X, self.Y, self.Z
        t12, k = t * 1.2, 4.2 * math.pi / self.bins * 2.2
        sw = [1 + 0.09 * sin(i * k - t12) for i in range(self.bins)]
        for j, r, cx, cy, dx, dy, dz in zip(range(self.m), self.bin, self.cx, self.cy, self.dx, self.dy, self.dz):
            m = sw[r]
            X[j] = cx + dx * m
            Y[j] = cy + dy * m
            Z[j] = dz * m


class TorusKnot(Strands):
    """The (3,8) torus knot as a twisting ribbon: parallel strands across its width run the
    length of the knot, and the band is lit by how squarely it faces the camera, so its
    twist reads as volume. A swell runs along it; colour walks the knot parameter while a
    slow phase crawls the stripes."""
    name, blurb, palette, hue = "torusknot", "the (3,8) torus knot as a twisting ribbon", "jade", 0.6
    pitch, zoom = 0.9, 0.95
    secs, across = 420, 5

    def __init__(self, rng):
        p, q = 3, 8

        def knot(a):
            r = 0.55 + 0.3 * cos(q * a)
            return r * cos(p * a), 0.3 * sin(q * a), r * sin(p * a)
        tab = frames(knot, self.secs)
        strands = []
        for i in range(self.across):
            w = i / (self.across - 1) - 0.5
            strands.append(([(r, *tab[r], w, (r / self.secs * 3 + 0.02 * i) % 1.0)
                             for r in range(self.secs)], True))
        cols = self.build(strands)
        self.sec, self.px, self.py, self.pz = cols[:4]
        self.fr = list(zip(*cols[4:10]))
        self.w, self.u = cols[10], cols[11]
        self.C = [0.0] * self.m
        self.N = ([0.0] * self.m, [0.0] * self.m, [0.0] * self.m)

    def fill(self, t):
        X, Y, Z, C = self.X, self.Y, self.Z, self.C
        NX, NY, NZ = self.N
        t2, crawl = t * 1.6, t * 0.035
        k, tw = TAU * 12 / self.secs, TAU * 16 / self.secs
        # per section: the band's half-width and its direction angle, which twists along the knot
        cs_ = []
        for r in range(self.secs):
            h, a = 0.065 * (1 + 0.35 * sin(r * k - t2)), r * tw + t * 0.4
            cs_.append((h * cos(a), h * sin(a), cos(a), sin(a)))
        for j, r, px, py, pz, (nx, ny, nz, bx, by, bz), w, u in zip(range(self.m), self.sec, self.px, self.py,
                                                                   self.pz, self.fr, self.w, self.u):
            c, s_, ca, sa = cs_[r]
            c *= w
            s_ *= w
            X[j] = px + c * nx + s_ * bx
            Y[j] = py + c * ny + s_ * by
            Z[j] = pz + c * nz + s_ * bz
            NX[j] = ca * bx - sa * nx
            NY[j] = ca * by - sa * ny
            NZ[j] = ca * bz - sa * nz
            C[j] = (u + crawl) % 1.0


class Tesseract(Strands):
    """A 4D hypercube: 16 vertices and 32 edges, turned by a dual-plane rotation (XY with ZW,
    then XW with YZ) and seen in perspective from 4D. Edge points are placed along the 4D
    edges before projecting, so edges bow as they pass near the eye. A pulse breathes along
    the edges and the vertices flare with short rays; colour is depth in w."""
    name, blurb, palette, hue = "tesseract", "a 4D hypercube in dual-plane rotation", "jade", 0.55
    yaw, pitch, zoom, tone = 0.09, 0.3, 0.7, 2.2
    per, rays = 24, 9

    def __init__(self, rng):
        self.verts = [tuple(0.5 if v >> b & 1 else -0.5 for b in range(4)) for v in range(16)]
        self.edges = [(a, a | 1 << b) for a in range(16) for b in range(4) if not a >> b & 1]
        strands = []
        for e in range(len(self.edges)):
            strands.append(([(e, i / (self.per - 1), 0.0, 0.0, 0.0) for i in range(self.per)], False))
        for v in range(16):
            for i in range(self.rays):
                g = [rng.gauss(0, 1) for _ in range(3)]
                ln = sqrt(sum(x * x for x in g)) or 1
                d = [x / ln * rng.uniform(0.5, 1.0) for x in g]
                strands.append(([(-1 - v, 0.0, 0.0, 0.0, 0.0), (-1 - v, 1.0, *d)], False))
        self.e, self.s, self.dx, self.dy, self.dz = self.build(strands)
        self.C = [0.0] * self.m
        self.W = [1.0] * self.m

    def project(self, t):
        a, b = t * 0.31, t * 0.19
        ca, sa, cb, sb = cos(a), sin(a), cos(b), sin(b)
        out = []
        for x, y, z, w in self.verts:
            x, y = x * ca - y * sa, x * sa + y * ca      # XY
            z, w = z * ca - w * sa, z * sa + w * ca      # ZW
            x, w = x * cb - w * sb, x * sb + w * cb      # XW
            y, z = y * cb - z * sb, y * sb + z * cb      # YZ
            out.append((x, y, z, w))
        return out

    def fill(self, t):
        X, Y, Z, C, W = self.X, self.Y, self.Z, self.C, self.W
        V = self.project(t)
        E = [(*V[a], *(q - p for p, q in zip(V[a], V[b]))) for a, b in self.edges]
        D = 2.0
        P = []
        for v, (x, y, z, w) in enumerate(V):
            f = D / (D - w)
            P.append((x * f, y * f, z * f, 0.06 + 0.12 * max(0.0, sin(t * 1.4 + v * 2.1)) ** 3,
                      min(0.999, max(0.0, w * 0.8 + 0.45))))
        t3 = t * 3.0
        for j, e, s, dx, dy, dz in zip(range(self.m), self.e, self.s, self.dx, self.dy, self.dz):
            if e >= 0:
                ax, ay, az, aw, ex, ey, ez, ew = E[e]
                w = aw + ew * s
                f = D / (D - w)
                X[j] = (ax + ex * s) * f
                Y[j] = (ay + ey * s) * f
                Z[j] = (az + ez * s) * f
                C[j] = min(0.999, max(0.0, w * 0.8 + 0.45))
                W[j] = 0.75 + 0.35 * sin(s * 12.0 - t3 + e)
            else:
                x, y, z, r, c = P[-1 - e]
                X[j] = x + dx * r
                Y[j] = y + dy * r
                Z[j] = z + dz * r
                C[j] = c
                W[j] = 1.6 - s * 1.2


class Breathing(Strands):
    """A knotted tube drawn as fine scalloped rings round a deepened trefoil centre line. Each
    ring is tilted along the tube by a slowly travelling amount, so neighbouring rings fan
    into frills, and the tube swells into lobes. The whole form inhales and exhales; colour
    runs along the tube in bands, so overlapping folds glow and whiten."""
    name, blurb, palette, hue = "breathing", "a pulsing, knotted glowing filigree", "neon", 0.85
    yaw, swing, pitch, zoom, tone = 0.12, 0.75, 0.35, 0.74, 0.8
    rings, per = 120, 34

    def __init__(self, rng):
        def knot(a):
            x, y, z = trefoil(a)
            return x, y, z * 1.4
        tab = frames(knot, self.rings)
        strands = []
        for r, (px, py, pz, nx, ny, nz, bx, by, bz) in enumerate(tab):
            tx, ty, tz = ny * bz - nz * by, nz * bx - nx * bz, nx * by - ny * bx
            u = r / self.rings
            pts = []
            for i in range(self.per):
                a = i / self.per * TAU
                c, s_ = cos(a), sin(a)
                frill = 1 + 0.3 * sin(a * 6 + u * TAU * 7)
                pts.append((r, px, py, pz, (c * nx + s_ * bx) * frill, (c * ny + s_ * by) * frill,
                            (c * nz + s_ * bz) * frill, tx * c, ty * c, tz * c, (u * 2 + 0.06 * c) % 1.0))
            strands.append((pts, True))
        cols = self.build(strands)
        self.ring = cols[0]
        self.pre = list(zip(*cols[1:10]))
        self.C = cols[10]

    def fill(self, t):
        X, Y, Z = self.X, self.Y, self.Z
        breath = sin(t * TAU / 7.0)               # one inhale and exhale every 7 s
        sc = 0.9 + 0.1 * breath
        k = TAU / self.rings
        t6, t3 = t * 0.6, t * 0.3
        rr, tl = [], []
        for r in range(self.rings):
            rr.append((0.05 + 0.22 * (0.5 + 0.5 * sin(r * k * 6 + 1 + 0.7 * sin(r * k * 4 - t6)))) * (1 + 0.15 * breath))
            tl.append(0.9 * sin(r * k * 10 - t3))
        for j, r, (px, py, pz, ox, oy, oz, tx, ty, tz) in zip(range(self.m), self.ring, self.pre):
            m = rr[r]
            q = m * tl[r]
            X[j] = (px + ox * m + tx * q) * sc
            Y[j] = (py + oy * m + ty * q) * sc
            Z[j] = (pz + oz * m + tz * q) * sc


def trefoil(a):
    return ((sin(a) + 2 * sin(2 * a)) / 3.0, (cos(a) - 2 * cos(2 * a)) / 3.0, -sin(3 * a) / 3.0)


def frames(curve, m):
    """m samples of a closed curve on [0, 2pi) as (point, normal, binormal), flattened."""
    h, tab = 1e-4, []
    for i in range(m):
        a = i / m * TAU
        p0, p1, p2 = curve(a - h), curve(a), curve(a + h)
        tv = [q - r for q, r in zip(p2, p0)]
        acc = [q - 2 * r + s_ for q, r, s_ in zip(p2, p1, p0)]
        tl = math.sqrt(sum(v * v for v in tv))
        tv = [v / tl for v in tv]
        d = sum(x * y for x, y in zip(acc, tv))
        nv = [x - d * y for x, y in zip(acc, tv)]
        nl = math.sqrt(sum(v * v for v in nv)) or 1.0
        nv = [v / nl for v in nv]
        bv = (tv[1] * nv[2] - tv[2] * nv[1], tv[2] * nv[0] - tv[0] * nv[2], tv[0] * nv[1] - tv[1] * nv[0])
        tab.append((*p1, *nv, *bv))
    return tab


FORMS = [Original, Jelly, Ribbon, Knot, Medusa, Ammonite, TorusKnot, Tesseract, Breathing]
NUMBERED = {"1": "jelly", "2": "ribbon", "3": "knot"}


class Glow:
    """Per-cell accumulation buffers and the sub-pixel -> (cell, braille bit) tables."""

    def __init__(self):
        self.size = None
        self.mean = None

    def begin(self, cols, rows):
        if self.size != (cols, rows):
            self.size = (cols, rows)
            pw = cols * 2
            self.cell = [(y >> 2) * cols + (x >> 1) for y in range(rows * 4) for x in range(pw)]
            self.bit = [BITS[((y & 3) << 1) | (x & 1)] for y in range(rows * 4) for x in range(pw)]
        n = cols * rows
        self.cnt, self.cs, self.bits = [0.0] * n, [0.0] * n, [0] * n

    def flat(self, form, lo, hi, sc, ox, oy):
        """Splat 2D points through the form's scale and centre."""
        cols, rows = self.size
        pw, ph = cols * 2, rows * 4
        s = sc * form.scale
        ax, ay = ox - form.centre[0] * s, oy - form.centre[1] * s
        CELL, BIT, cnt, cs, bits = self.cell, self.bit, self.cnt, self.cs, self.bits
        for x, y, c in zip(form.X[lo:hi], form.Y[lo:hi], form.C[lo:hi]):
            ix = int(ax + x * s)
            iy = int(ay + y * s)
            if 0 <= ix < pw and 0 <= iy < ph:
                p = iy * pw + ix
                k = CELL[p]
                cnt[k] += 1.0
                cs[k] += c
                bits[k] |= BIT[p]

    def solid(self, form, lo, hi, sc, ox, oy, yaw, pitch):
        """Splat 3D points through the orbit camera; a point's weight is its perspective
        magnification, so near points glow more than far ones."""
        cols, rows = self.size
        pw, ph = cols * 2, rows * 4
        cy, sy, cp, sp = cos(yaw), sin(yaw), cos(pitch), sin(pitch)
        D = 3.4
        Ds = D * sc * form.zoom
        wk = 1 / (sc * form.zoom)
        CELL, BIT, cnt, cs, bits = self.cell, self.bit, self.cnt, self.cs, self.bits
        for x, y, z, c in zip(form.X[lo:hi], form.Y[lo:hi], form.Z[lo:hi], form.C[lo:hi]):
            x1 = x * cy + z * sy
            z1 = z * cy - x * sy
            f = Ds / (D - z1 * cp + y * sp)
            ix = int(ox + x1 * f)
            iy = int(oy + (y * cp + z1 * sp) * f)
            if 0 <= ix < pw and 0 <= iy < ph:
                p = iy * pw + ix
                k = CELL[p]
                f *= wk
                cnt[k] += f
                cs[k] += c * f
                bits[k] |= BIT[p]

    def lines(self, form, keep, sc, ox, oy, yaw, pitch):
        """Project a Strands form through the orbit camera, then rasterise its first `keep`
        segments one sub-pixel step at a time. A step's weight is the segment's mean
        perspective magnification times its brightness (W, and facing when the form has
        normals), so glow measures how many strands cross a cell."""
        cols, rows = self.size
        pw, ph = cols * 2, rows * 4
        cy, sy, cp, sp = cos(yaw), sin(yaw), cos(pitch), sin(pitch)
        D = 3.4
        Ds = D * sc * form.zoom
        wk = 1 / (sc * form.zoom)
        SX, SY, SW, C = form.SX, form.SY, form.SW, form.C
        for j, x, y, z in zip(range(form.m), form.X, form.Y, form.Z):
            x1 = x * cy + z * sy
            z1 = z * cy - x * sy
            f = Ds / (D - z1 * cp + y * sp)
            SX[j] = ox + x1 * f
            SY[j] = oy + (y * cp + z1 * sp) * f
            SW[j] = f * wk
        if form.W is not None:
            for j, w in enumerate(form.W):
                SW[j] *= w
        if form.N is not None:
            # facing = |normal . view| in camera space; edge-on parts of a band stay dim
            for j, nx, ny, nz in zip(range(form.m), *form.N):
                v = (nz * cy - nx * sy) * cp - ny * sp
                SW[j] *= 0.15 + 0.85 * (v if v > 0 else -v)
        CELL, BIT, cnt, cs, bits = self.cell, self.bit, self.cnt, self.cs, self.bits
        for j in form.segs[:keep]:
            i = j - 1
            x, y = SX[i], SY[i]
            dx, dy = SX[j] - x, SY[j] - y
            ax, ay = (dx if dx > 0 else -dx), (dy if dy > 0 else -dy)
            steps = int(ax if ax > ay else ay) + 1
            w = (SW[i] + SW[j]) * 0.5
            wc = w * (C[i] + C[j]) * 0.5
            dx /= steps
            dy /= steps
            for _ in range(steps):
                ix, iy = int(x), int(y)
                if 0 <= ix < pw and 0 <= iy < ph:
                    p = iy * pw + ix
                    k = CELL[p]
                    cnt[k] += w
                    cs[k] += wc
                    bits[k] |= BIT[p]
                x += dx
                y += dy

    def blit(self, cv, lut, halo, tone):
        """Tone-map the buffers into braille cells: glow level from 1 - exp(-k v), k set by
        the (smoothed) mean density of lit cells so the look holds at any size or point count.
        With a halo table (truecolor), the glow is also blurred (3-tap box, twice each way)
        into a dim background tint, and every cell gets an explicit background."""
        cols = self.size[0]
        cnt, cs, bits = self.cnt, self.cs, self.bits
        lit = [k for k, b in enumerate(bits) if b]
        if not lit:
            return
        mean = sum(cnt) / len(lit)
        self.mean = mean if self.mean is None else self.mean + (mean - self.mean) * 0.15
        kk = -tone / self.mean
        cells = cv.cells
        lv, nb, top = LEVELS * 0.9999, BINS, BINS - 1
        if halo is None:
            for k in lit:
                v = cnt[k]
                b = int(cs[k] / v * nb)
                cells[k // cols][k % cols] = (CHARS[bits[k]],
                                              lut[int(lv * (1 - exp(v * kk))) * nb + (b if b < top else top)],
                                              None)
            return
        # glow and colour sums blur together as the real and imaginary parts of one grid
        bz = _blur(list(map(complex, cnt, cs)), cols)
        hk = -TONE * HALO_GAIN / self.mean / 81       # the blur's weights sum to 81
        hl = (HALO_LEVELS - 1) * 0.9999 / (1 - HALO_START)
        floor = math.log(1 - HALO_START) / hk
        blank = (" ", None, BG)
        rows_ = [[blank] * cols for _ in range(cv.h)]
        for k, z in enumerate(bz):
            v = z.real
            if v > floor:
                b = int(z.imag / v * nb)
                rows_[k // cols][k % cols] = (" ", None, halo[(1 + int(hl * (1 - HALO_START - exp(v * hk)))) * nb
                                                              + (b if b < top else top)])
        for k in lit:
            v = cnt[k]
            b = int(cs[k] / v * nb)
            row = rows_[k // cols]
            x = k % cols
            row[x] = (CHARS[bits[k]], lut[int(lv * (1 - exp(v * kk))) * nb + (b if b < top else top)], row[x][2])
        cv.cells = rows_


def _blur(v, cols):
    """Separable 3-tap box blur applied twice each way on a flat row-major grid, as shifted
    list sums (C-speed map). Rows wrap into their neighbours at the left and right edges,
    which only ever touches the margin."""
    for d in (1, 1, cols, cols):
        p = [0j] * d + v + [0j] * d
        v = list(map(_add, map(_add, p[:-2 * d], p[d:-d]), p[2 * d:]))
    return v


def form_count(form, cols, rows, cap):
    n = min(form.cap, int(cols * rows * 8 * DENSITY))
    return max(64, min(form.m, n if cap is None else min(cap, form.m)))


def main():
    p = term.make_parser("A family of glowing mathematical point clouds", fps=12)
    p.add_argument("--points", type=int, default=None,
                   help="points per dot-cloud form (default: sized to the terminal, up to the form's full set)")
    p.add_argument("--speed", type=float, default=1.0, help="time multiplier (default 1)")
    names = [f.name for f in FORMS]
    p.add_argument("--form", default=None, metavar="NAME",
                   help=f"hold one form: {', '.join(names)} (or 1 jelly, 2 ribbon, 3 knot)")
    p.add_argument("--list-forms", action="store_true", help="list the forms and exit")
    p.add_argument("--seed", type=int, default=None, help="random seed")
    p.add_argument("--palette", choices=sorted(PALETTES), default=None,
                   help="pin one palette (no drift unless --drift)")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--drift", action="store_true", help="keep cross-fading between palettes even with --palette")
    g.add_argument("--no-drift", action="store_true", help="hold the launch palette")
    args = p.parse_args()
    if args.list_forms:
        for f in FORMS:
            num = next((k for k, v in NUMBERED.items() if v == f.name), " ")
            print(f"{num} {f.name:<10} {f.blurb}" + (f" ({f.palette})" if f.palette else ""))
        return 0
    if args.form is not None:
        args.form = NUMBERED.get(args.form, args.form)
        if args.form not in names:
            p.error(f"--form: unknown form {args.form!r}; try --list-forms")
    rng = random.Random(args.seed)
    forms = [f(rng) for f in FORMS]
    order = list(range(len(forms)))
    rng.shuffle(order)
    hold = args.form is not None
    if hold:
        order = [names.index(args.form)]
    first = forms[order[0]]
    name = args.palette or first.palette or rng.choice(sorted(PALETTES))
    drift = Drift(rng, name, not args.no_drift and (args.palette is None or args.drift))
    glow = Glow()
    luts = {}
    state = {"k": 0}
    cv_size = [0, 0]
    bloom = term.COLOR and term.TRUECOLOR

    def draw(form, frac, t, sc, ox, oy, yaw, pitch):
        if form.lines:
            keep = round(len(form.segs) * frac)
            if keep > 0:
                form.fill(t)
                glow.lines(form, keep, sc, ox, oy, yaw, pitch)
            return
        n = round(form_count(form, cv_size[0], cv_size[1], args.points) * frac)
        if n <= 0:
            return
        form.fill(t, n)
        spans = form.ranges(n) if hasattr(form, "ranges") else ((0, n),)
        for lo, hi in spans:
            if form.flat:
                glow.flat(form, lo, hi, sc, ox, oy)
            else:
                glow.solid(form, lo, hi, sc, ox, oy, yaw, pitch)

    def step(cv, frame):
        t = frame / 12 * args.speed
        cyc = t / (HOLD + FADE)
        k = int(cyc)
        into = (cyc - k) * (HOLD + FADE) - HOLD
        a = forms[order[k % len(order)]]
        b = forms[order[(k + 1) % len(order)]]
        m = 0.0
        if into > 0 and not hold:
            m = into / FADE
            m = m * m * (3 - 2 * m)
            if state["k"] <= k:
                state["k"] = k + 1
                if b.palette and args.palette is None:
                    drift.goto(b.palette, t, FADE * 1.6)
                audio.sfx("swell", 0.7)
        key, samples = drift.update(t, frame)
        hue = round((a.hue * (1 - m) + b.hue * m) * 20) / 20
        got = luts.get((key, hue))
        if got is None:
            if len(luts) > 64:
                luts.clear()
            lut = build_lut(samples, hue)
            got = luts[(key, hue)] = (lut, build_halo(lut, hue) if bloom else None)
        lut, halo = got

        cols, rows = cv.w, cv.h
        glow.begin(cols, rows)
        pw, ph = cols * 2, rows * 4
        sc = min(pw, ph) * 0.5 * 0.94
        ox, oy = pw / 2, ph / 2
        cv_size[:] = [cols, rows]
        if m < 1:
            yaw, pitch = camera(a, t)
            draw(a, 1 - m, t, sc, ox, oy, yaw, pitch)
        if m > 0:
            yaw, pitch = camera(b, t)
            draw(b, m, t, sc, ox, oy, yaw, pitch)
        glow.blit(cv, lut, halo, a.tone * (1 - m) + b.tone * m)
        shown = t - k * (HOLD + FADE)  # seconds since form a finished fading in
        if shown < CAPTION and rows > 4 and cols > 12:
            cv.text(2, rows - 2, a.name, 244 if shown < CAPTION - 1 else 239)

    def camera(form, t):
        if form.swing:
            yaw = form.swing * sin(t * form.yaw / form.swing)
        else:
            yaw = 0.6 + t * form.yaw
        return yaw, form.pitch + 0.12 * sin(t * 0.21)

    return term.run(args, step, music="swirl")


if __name__ == "__main__":
    sys.exit(main())
