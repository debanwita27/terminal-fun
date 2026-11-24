#!/usr/bin/env python3
"""Jellyfish: moon jellies pulse upward through a deep-sea gradient, drawn in deliberate glyphs.

Usage: python3 jellyfish.py [--count 4] [--seed N] [--fps 20] [--frames N]

Each part of a jelly has its own small glyph vocabulary, ordered by measured ink coverage
(Menlo, share of lit pixels in a cell):
  bell        "·:;toS8@" shading on tinted tiles, meridian canals and the silhouette in
              contour glyphs ( ) / \\ | picked by the local slope, a scalloped rim \\_/
  gonads      o and 0 rings in the accent hue, four horseshoes inside the bell
  oral arms   frilly ribbons: ( ) edges, { } at frill crests, S s § inside, , at the tip
  tentacles   orientation glyphs that thin toward the tip: | / \\ ( )  then ¦ then : ' .
  far layer   "  ·:;" on soft tiles: blank in the middle, dots toward the limb, no outline
  plankton    sparse · and . dots
Texture is a function of body coordinates (azimuth, height on the bell, arc length down an
arm or tentacle), so it moves with the pulse and never re-rolls; only the glints travelling
down the tentacles and the occasional bioluminescent flash change brightness over time.
In truecolor every cell is painted (a smooth gradient, no dither) and the bells glow onto it.
In 256 colours the background is one flat colour, colours map to their nearest palette
entries, and there is no glow.
"""

META = {"name": "jellyfish", "kind": "watch", "blurb": "moon jellies pulsing upward through the deep, in glyphs",
        "credit": {"type": "inspired by", "who": "Marcelo Design X (@MarceloDesignX)",
                   "url": "https://x.com/MarceloDesignX/status/2114611049702011197"}}

import math
import os
import random
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

from fun import audio, term

ASP = 2.0      # a cell is about twice as tall as wide; body maths runs in square units (rows * ASP)
TILT = 0.30    # depth of the front rim arc below the rim line, as a fraction of the rim radius
TAU = 2 * math.pi
STRAND_FOLLOW = 2.2  # how fast arms and tentacles settle back under the bell, 1/s

BELL_RAMP = "·:;toS8@"   # coverage .03 .08 .11 .15 .19 .22 .27 .31
NB = len(BELL_RAMP)
GONAD = "o0"            # ring glyphs for the four horseshoe gonads (accent hue)
FAR_RAMP = "  ·:;"      # out-of-focus bells: blank tiles in the middle, dots toward the limb

# Two hues only (teal and violet); each jelly takes one and uses the other as its accent.
TEAL = ((74, 150, 142), (200, 244, 234))      # (body, pale highlight)
VIOLET = ((118, 100, 170), (222, 210, 250))
BG_TOP, BG_BOT = (15, 31, 40), (6, 9, 15)
SNOW_TINT = (120, 150, 165)
NL = 48        # emission levels per colour table
HL = 40        # glow levels
HALO_MAX = 0.24


def lerp(a, b, k):
    return (round(a[0] + (b[0] - a[0]) * k), round(a[1] + (b[1] - a[1]) * k), round(a[2] + (b[2] - a[2]) * k))


_luts = {}


def lut(hue, z, bg):
    """NL colours for emission 0..1: bg -> body hue -> pale. Far jellies (z near 1) are fogged
    toward bg and lose their brightest steps."""
    zq = round(z * 8)
    key = (hue, zq, bg)
    got = _luts.get(key)
    if got is None:
        body, pale = hue
        zz = zq / 8
        body = lerp(body, bg, 0.5 * zz)
        pale = lerp(pale, body, 0.65 * zz)
        got = []
        for i in range(NL):
            a = i / (NL - 1)
            got.append(lerp(bg, body, (a / 0.6) ** 1.15) if a < 0.6 else lerp(body, pale, (a - 0.6) / 0.4))
        _luts[key] = got
    return got


_halos = {}


def halo_lut(hue, z, bg):
    """HL colours for the soft glow around a bell: bg moved up to HALO_MAX of the way to the body hue."""
    zq = round(z * 8)
    key = (hue, zq, bg)
    got = _halos.get(key)
    if got is None:
        body = lerp(hue[0], bg, 0.4 * zq / 8)
        got = _halos[key] = [lerp(bg, body, HALO_MAX * i / (HL - 1)) for i in range(HL)]
    return got


_adds = {}


def add_light(c, lit, ref):
    """c brightened by the light that lit adds over ref (all rgb); cached, and every input
    comes from a small fixed set, so the cache stays small."""
    key = (c, lit, ref)
    got = _adds.get(key)
    if got is None:
        got = _adds[key] = tuple(min(255, max(0, x + y - z)) for x, y, z in zip(c, lit, ref))
    return got


def base_rows(w, h):
    """Static background cells: a vertical deep-sea gradient (one colour per row, so colour
    tables keyed by row stay few) with a faint dot grid. Every cell gets a bg. In 256 colours
    the gradient would band, so it is one flat colour there."""
    rows = []
    for y in range(h):
        v = (y / max(1, h - 1)) if term.TRUECOLOR else 0.55
        bg = lerp(BG_TOP, BG_BOT, v ** 0.8)
        grid = lerp(bg, SNOW_TINT, 0.09)
        rows.append([("·", grid, bg) if term.COLOR and x % 6 == 3 and y % 3 == 1 else (" ", None, bg)
                     for x in range(w)])
    return rows


def flash_env(tau):
    """Bioluminescent flash brightness tau seconds after it starts: fast rise, slow fade."""
    if tau < 0 or tau > 4.5:
        return 0.0
    if tau < 0.35:
        return (tau / 0.35) ** 2
    return math.exp(-(tau - 0.35) / 0.9)


def strand_glyphs(dx, dy, cross):
    """Glyphs for one strand segment (dx cols, dy rows, cross = its turn) at four weights,
    root to tip; None means pick by sub-row: ' in the upper half of a cell, . in the lower.
    Heavy: | ( ) / \\ -   medium: ¦ / \\ -   thin: : or a dotted ' .   tip: dotted only."""
    a = dx / (abs(dy) + 1e-6)
    aa = abs(a)
    if aa < 0.3:
        heavy = "(" if cross < -0.12 else ")" if cross > 0.12 else "|"
        mid = "¦"
    elif aa < 2.2:
        heavy = mid = "\\" if a > 0 else "/"
    else:
        heavy = mid = "-"
    return heavy, mid, ":" if aa < 0.45 else None, None


class Strand:
    """A chain of points hanging from an anchor (square units). Each point eases toward a spot
    one segment below its parent, tilted by a sway angle whose phase lags further down the
    chain, then is held at segment length. The lag makes strands trail behind the bell when
    it jets and carries each sway down the strand with delay; there is no velocity state, so
    nothing can build up energy."""

    def __init__(self, n, seg, phase, amp, arm=False, w0=0.0, glint=0.0):
        self.n, self.seg, self.phase, self.amp, self.arm, self.w0 = n, seg, phase, amp, arm, w0
        self.wt = w0
        self.pts = None
        self.glint = glint

    def reset(self, ax, ay):
        self.pts = [[ax, ay + i * self.seg] for i in range(self.n + 1)]

    def update(self, ax, ay, t, dt, drift):
        if self.pts is None:
            self.reset(ax, ay)
        pts, seg, n = self.pts, self.seg, self.n
        pts[0][0], pts[0][1] = ax, ay
        k = 1 - math.exp(-(STRAND_FOLLOW * (0.7 if self.arm else 1.0)) * dt)
        amp, ph, w = self.amp, self.phase, t * 1.1
        lean = drift * 0.08
        for i in range(1, n + 1):
            p, q = pts[i], pts[i - 1]
            ang = lean + amp * (0.08 + 0.32 * i / n) * math.sin(w + ph - i * 0.22)
            tx, ty = q[0] + seg * math.sin(ang), q[1] + seg * math.cos(ang)
            px, py = p[0] + (tx - p[0]) * k, p[1] + (ty - p[1]) * k
            ddx, ddy = px - q[0], py - q[1]
            d = math.sqrt(ddx * ddx + ddy * ddy) or 1.0
            p[0], p[1] = q[0] + ddx * seg / d, q[1] + ddy * seg / d


class Jelly:
    def __init__(self, rng, w, h, z, first, peers):
        self.rng = rng
        self.z = z
        self.peers = peers
        self.spawn(w, h, first)

    def spawn(self, w, h, first):
        r, z = self.rng, self.z
        smax = max(4.0, min(14.0, w / 7.5, h * ASP / 4.8))
        self.W0 = r.uniform(0.75, 1.0) * smax * (1 - 0.5 * z)
        self.H0 = self.W0 * r.uniform(1.0, 1.15)
        self.hue, self.acc = (TEAL, VIOLET) if r.random() < 0.6 else (VIOLET, TEAL)
        self.period = r.uniform(2.6, 3.4) * (1 + 0.35 * z)
        self.p = r.random()
        self.c = 0.0
        self.spin = r.random() * TAU
        self.spin_v = r.choice((-1, 1)) * r.uniform(0.05, 0.11)
        self.x = self.lane(w)
        self.vy = 0.0
        self.drift = r.uniform(-0.6, 0.6)
        self.lobes = max(8, round(TAU * self.W0 / 3.6))   # each scallop about 3.6 cols wide face-on
        self.flash_t = -99.0
        self.halo_key = None
        # A few long primary tentacles that start heavy, between finer marginal ones.
        nt = int(5 + self.W0 * 0.4) if z < 0.55 else 5
        tlen = self.H0 * r.uniform(2.6, 3.4)
        seg = 1.7
        self.tent = []
        for k in range(nt):
            th = (k + 0.5) / nt * TAU + r.uniform(-0.15, 0.15)
            primary = k % 3 == 0
            ln = tlen * (r.uniform(0.85, 1.0) if primary else r.uniform(0.45, 0.8))
            self.tent.append((th, Strand(max(4, int(ln / seg)), seg, r.random() * TAU, r.uniform(0.6, 1.3),
                                         w0=0.0 if primary else 0.3, glint=r.random() * 10)))
        na = 4 if z < 0.55 else 2
        alen = self.H0 * r.uniform(1.3, 1.7)
        self.arms = [((k + 0.5) / na * TAU, Strand(max(3, int(alen / 1.1)), 1.1, r.random() * TAU, 0.5, True))
                     for k in range(na)]
        self.reach = tlen + 2
        hs = h * ASP
        self.y = r.uniform(self.H0 + 2, hs + self.reach * 0.2) if first else hs + self.H0 + 2
        for _, s in self.tent + self.arms:
            s.pts = None

    def lane(self, w):
        """A start column away from the other jellies of the same layer (set by main)."""
        others = [j.x for j in self.peers if j is not self and (j.z > 0.55) == (self.z > 0.55)]
        best, score = 0.0, -1.0
        for _ in range(8):
            x = self.rng.uniform(w * 0.1, w * 0.9)
            d = min((abs(x - o) for o in others), default=w)
            if d > score:
                best, score = x, d
        return best

    def step(self, t, dt, w, h):
        self.p = (self.p + dt / self.period) % 1.0
        p = self.p
        # Contraction is quick (first 30% of the cycle), relaxation slow.
        if p < 0.3:
            e = p / 0.3
            c = e * e * (3 - 2 * e)
        else:
            e = (p - 0.3) / 0.7
            c = 1 - e * e * (3 - 2 * e)
        dc = (c - self.c) / dt if dt else 0.0
        self.c = c
        sc = 1 - 0.45 * self.z
        thrust = max(0.0, dc) * self.W0 * 0.85
        self.vy += (-thrust + 1.45 * sc - 1.4 * self.vy) * dt
        self.y += self.vy * dt
        self.x += (self.drift + 0.6 * math.sin(t * 0.21 + self.spin)) * sc * dt
        self.spin += self.spin_v * dt
        self.W = self.W0 * (1 - 0.2 * c)
        self.H = self.H0 * (1 + 0.28 * c)
        self.flare = 0.07 - 0.17 * c
        self.Wr = self.W * (1 + self.flare)
        cx, cy, Wr = self.x, self.y, self.Wr
        for th, s in self.tent:
            a = th + self.spin
            s.update(cx + Wr * math.sin(a), cy + TILT * Wr * math.cos(a), t, dt, self.drift)
        for th, s in self.arms:
            a = th + self.spin
            s.update(cx + Wr * 0.14 * math.sin(a), cy + TILT * Wr * 0.25, t, dt, self.drift)
        if self.y + self.reach < 0 or self.x < -self.W0 * 3 or self.x > w + self.W0 * 3:
            self.spawn(w, h, False)

    # -- drawing ---------------------------------------------------------------------------

    def R(self, hh):
        """Bell radius (cols) at height hh (0 rim .. 1 apex); the margin flares when relaxed
        and pinches in on contraction."""
        if hh >= 1.0:
            return -1.0
        if hh <= 0.0:
            return self.Wr
        m = 1 - hh
        return self.W * math.sqrt(1 - hh * hh) * (1 + self.flare * m ** 4)

    def prep(self, cv, base, t):
        """Per-frame colour tables, keyed by the background row at the bell."""
        ry = min(cv.h - 1, max(0, int(self.y / ASP)))
        self.bg = bg = base[ry][0][2]
        self.L = lut(self.hue, self.z, bg)
        self.A = lut(self.acc, self.z, bg)
        self.fl = flash_env(t - self.flash_t)
        self.vis = 1 - 0.45 * self.z

    def glow(self, cv, base):
        self._halo(cv, base, self.bg, self.fl)

    def draw(self, cv, base, t):
        L, A, fl, vis = self.L, self.A, self.fl, self.vis
        self.own = set()
        front = []
        for th, s in self.tent:
            sa = math.sin(th + self.spin)
            # Strands seen at the bell's sides crowd into one column, so they draw thinner.
            s.wt = min(0.6, s.w0 + 0.45 * sa * sa)
            if math.cos(th + self.spin) < 0:
                self._strand(cv, base, s, L, t, fl, vis * 0.62)
            else:
                front.append(s)
        self._bell(cv, L, A, fl, vis, self.bg)
        for _, s in self.arms:
            self._arm(cv, base, s, L, t, fl, vis)
        for s in front:
            self._strand(cv, base, s, L, t, fl, vis)

    def _halo(self, cv, base, bg, fl):
        """Soft light around the bell, lerped from the painted background. It only touches
        cells still showing plain background; glows are painted nearest first, before any
        body, so a nearer glow wins and far bodies then add their light on top of it."""
        # Rest-size shape on a half-cell grid and a coarse gain, so the glow (and the bytes
        # sent for it) only changes when that is visible.
        cx, Wr = round(self.x * 2) / 2, self.W0 * 1.05
        hr = self.H0 / ASP
        cyr = round((self.y / ASP - hr * 0.3) * 2) / 2
        ry = hr * 0.8 + 1.0
        spread = 0.28 + 0.45 * self.z
        g = round(min(1.0, (0.42 + 0.12 * self.c + 0.6 * fl) * (1 - 0.3 * self.z)) * 12) / 12
        reach = 0.75 + spread * 2.2
        key = (cx, cyr, g, bg, cv.w, cv.h)
        if self.halo_key != key:
            self.halo_key, self.halo_cells = key, self._halo_cells(cv, bg, cx, cyr, Wr, ry, spread, g, reach)
        cells = cv.cells
        for yi, xi, col in self.halo_cells:
            row = cells[yi]
            cell = row[xi]
            if cell[2] is base[yi][xi][2]:
                row[xi] = (cell[0], cell[1], col)

    def _halo_cells(self, cv, bg, cx, cyr, Wr, ry, spread, g, reach):
        """(row, col, colour) of every glow cell brighter than bg, for one halo shape."""
        top = HL - 1
        L = halo_lut(self.hue, self.z, bg)
        r2max = reach * reach
        nt = 96
        tab = []   # glow colour by squared elliptical radius
        for i in range(nt + 1):
            rho = math.sqrt(r2max * i / nt)
            tab.append(L[int(g * math.exp(-((max(0.0, rho - 0.7)) / spread) ** 2) * top + 0.5)])
        kq = nt / r2max
        zero = L[0]
        iw = 1 / Wr
        out = []
        for yi in range(max(0, int(cyr - ry * reach)), min(cv.h - 1, int(cyr + ry * reach) + 1) + 1):
            v = (yi + 0.5 - cyr) / ry
            v2 = v * v
            if v2 > r2max:
                continue
            half = Wr * math.sqrt(r2max - v2)
            for xi in range(max(0, int(cx - half)), min(cv.w, int(cx + half) + 1)):
                u = (xi + 0.5 - cx) * iw
                k = int((u * u + v2) * kq)
                if k <= nt and tab[k] is not zero:
                    out.append((yi, xi, tab[k]))
        return out

    def _bell(self, cv, L, A, fl, vis, bg):
        cx, cy = self.x, self.y
        W, H, Wr, c, spin = self.W, self.H, self.Wr, self.c, self.spin
        far = self.z > 0.55
        cells, cw, ch = cv.cells, cv.w, cv.h
        top = NL - 1
        tiltd = TILT * Wr
        lob_d = 0.6
        nlob = self.lobes
        xa = int(cx - Wr) - 1
        ncol = int(cx + Wr) + 2 - xa
        # Rim depth below the rim line (square units) at two sub-columns per cell, and the
        # scallop phase at each cell centre (0 at a notch between two lappets).
        rim, subax = [], []
        for sx in range(ncol * 2):
            dx = abs(xa + (sx + 0.5) / 2 - cx)
            subax.append(dx)
            rim.append(math.sqrt(1 - (dx / Wr) ** 2) * tiltd + lob_d if dx < Wr else -1.0)
        rimlo = [min(rim[2 * col], rim[2 * col + 1]) for col in range(ncol)]
        rimhi = [max(rim[2 * col], rim[2 * col + 1]) for col in range(ncol)]
        lobe = []
        for col in range(ncol):
            q = (xa + col + 0.5 - cx) / Wr
            lobe.append(((math.asin(q) - spin) * nlob / TAU) % 1.0 if -1 < q < 1 else 0.5)
        # Front-facing meridian canals (8), as screen offsets per unit radius.
        ribs = []
        for k in range(8):
            a = spin + k * TAU / 8 + 0.2
            if math.cos(a) > 0.25:
                ribs.append(math.sin(a))
        gon = [spin + k * TAU / 4 + 0.6 for k in range(4)]
        gon = [math.atan2(math.sin(g), math.cos(g)) for g in gon if math.cos(g) > 0.1]
        y0 = max(0, int((cy - H) / ASP))
        y1 = min(ch - 1, int((cy + tiltd + lob_d) / ASP) + 1)
        k_em = 0.32 * fl + 0.07 * c
        R = self.R
        own = self.own
        asin, sin = math.asin, math.sin
        iw = 1 / W
        # One tile tone and glyph tone per ramp step, so runs of a glyph share colours.
        nb = 5 if far else NB
        tile, tfg, rfg, gfg = [], [], [], []
        for i in range(nb):
            d = (i + 0.5) / nb
            bga = ((0.08 + 0.24 * d) if far else (0.15 + 0.34 * d)) + 0.15 * fl
            fga = bga + 0.3 + 0.3 * d
            tile.append(L[int(min(1.0, bga) * vis * top)])
            tfg.append(L[int(min(1.0, fga) * vis * top)])
            rfg.append(L[int(min(1.0, fga + 0.15) * vis * top)])
            gfg.append(A[int(min(1.0, fga + 0.1) * vis * top)])
        if far:
            # Glow-table levels whose tint ramps from bg up to the first tile tone over n/8.
            hl = halo_lut(self.hue, self.z, bg)
            kf = min(1.0, ((0.08 + 0.24 * 0.5 / nb + 0.15 * fl) * vis / 0.6) ** 1.15 / HALO_MAX)
            soft = [hl[int(min(HL - 1, kf * (HL - 1) * m / 8))] for m in range(9)]
        for yi in range(y0, y1 + 1):
            sy = [yi + (k + 0.5) / 4 for k in range(4)]
            sd = [s * ASP - cy for s in sy]                 # below the rim line, square units
            shh = [-d / H for d in sd]
            sr = [R(hh) for hh in shh]
            rmax = max(sr)
            if rmax <= 0:
                continue
            rmin = min(sr)
            rimrow = sd[3] > 0
            hc = (cy - (yi + 0.5) * ASP) / H
            rc = R(hc) if hc < 1 else 0.0
            # Rib columns and slopes for this row (cols per row).
            ribrow = {}
            if not far and -0.3 < hc < 0.84 and rc > 0:
                slope_k = (sr[3] - sr[0]) * 4 / 3
                for sk in ribs:
                    xr = int(cx + rc * sk)
                    s = slope_k * sk
                    if abs(s) < 0.28:
                        g = "|"
                    elif abs(s) < 0.95:
                        g = ")" if s > 0 else "("
                    elif abs(s) < 3.0:
                        g = "\\" if s > 0 else "/"
                    else:
                        continue
                    ribrow[xr] = g
            gh2 = ((hc - 0.44) / 0.17) ** 2
            hp = hc if hc > 0 else 0.0
            hp2 = hp * hp
            d_row = 0.16 + k_em + (0.22 * (1 - hp / 0.2) if hc < 0.2 else 0.0)   # + ring canal
            tex = hc * 7 - spin * 2
            irc = 1 / rc if rc > 0.3 else 0.0
            gonrow = not far and gh2 < 1
            row = cells[yi]
            rowbase = yi * cw
            xl, xr_ = max(0, int(cx - rmax - 0.5)), min(cw - 1, int(cx + rmax + 0.5))
            for xi in range(xl, xr_ + 1):
                dxc = xi + 0.5 - cx
                adx = abs(dxc)
                inner = adx + 0.25 < rmin
                if inner and (not rimrow or sd[3] < rimlo[xi - xa]):
                    n = 8
                elif rimrow and sd[0] >= rimhi[xi - xa] > -1:
                    continue
                else:
                    n = 0
                    mx = my = 0.0
                    j0 = (xi - xa) * 2
                    for j in (0, 1):
                        ax = subax[j0 + j]
                        rd = rim[j0 + j]
                        for k in (0, 1, 2, 3):
                            if ax < sr[k] and (sd[k] <= 0 or sd[k] < rd):
                                n += 1
                                mx += j - 0.5
                                my += k - 1.5
                    if n == 0:
                        continue
                own.add(rowbase + xi)
                if n < 7:
                    if far:
                        if not term.TRUECOLOR:
                            continue
                        # Out of focus: edge cells take a tint in proportion to coverage.
                        cell = row[xi]
                        row[xi] = (cell[0], cell[1], add_light(cell[2], soft[n], bg))
                        continue
                    # Silhouette: the glyph follows the edge. (mx, my) points into the body.
                    ny = my * 0.5 * ASP
                    if ny < 0 and abs(ny) > 2.0 * abs(mx):
                        # Scalloped margin: each lappet reads \_/ across the rim.
                        fr = lobe[xi - xa]
                        g = "\\" if fr < 0.3 else "/" if fr > 0.7 else "_"
                    elif abs(ny) > 2.2 * abs(mx):
                        pos = 1 - n / 8
                        g = "_" if pos > 0.6 else "-" if pos > 0.3 else "'"
                    elif abs(ny) < 0.45 * abs(mx):
                        g = "(" if mx > 0 else ")"
                    elif n <= 2:
                        g = "." if ny > 0 else "'"
                    else:
                        g = "/" if mx * ny > 0 else "\\"
                    row[xi] = (g, L[int(min(1.0, (0.5 + 0.1 * c + 0.35 * fl)) * vis * top)], row[xi][2])
                    continue
                # Interior: limb-brightened translucent dome, ring canal at the margin, gonads.
                q = dxc * irc
                q = -1.0 if q < -1 else 1.0 if q > 1 else q
                uw = dxc * iw
                rho2 = uw * uw + hp2
                d = d_row + 0.36 * rho2 * rho2 * rho2
                th = asin(q)
                d += 0.05 * sin(th * 6 + tex)
                acc = False
                if gonrow:
                    for gk in gon:
                        dth = (th - gk) / 0.36
                        e = math.sqrt(dth * dth + gh2)
                        if 0.6 < e < 0.92:
                            d += 0.38 * (1 - abs(e - 0.76) / 0.16)
                            acc = True
                            break
                gi = int(d * nb) if d < 1 else nb - 1
                if acc:
                    row[xi] = (GONAD[gi >= NB - 2], gfg[gi], tile[gi])
                    continue
                g = ribrow.get(xi)
                if g is not None:
                    row[xi] = (g, rfg[gi], tile[gi])
                elif far:
                    b = row[xi][2]
                    row[xi] = (FAR_RAMP[gi], tfg[gi], add_light(b, tile[gi], bg) if term.TRUECOLOR else b)
                else:
                    row[xi] = (BELL_RAMP[gi], tfg[gi], tile[gi])

    def _strand(self, cv, base, s, L, t, fl, vis):
        pts, n = s.pts, s.n
        cells, cw, ch = cv.cells, cv.w, cv.h
        top = NL - 1
        w0 = 0.6 if self.z > 0.55 else s.wt     # where on the thinning scale the root starts
        own = self.own
        gl = (t * 0.16 + s.glint) % 1.6        # glint head position along the strand
        flashing = t - self.flash_t < 6.0
        last = -1
        ox, oy = pts[0][0], pts[0][1] / ASP
        pdx, pdy = 0.0, 1.0
        flash_t, exp = self.flash_t, math.exp
        tint = L[int(0.07 * vis * top) + 1]
        for i in range(n):
            bx, by = pts[i + 1][0], pts[i + 1][1] / ASP
            dx, dy = bx - ox, by - oy
            if oy > ch + 1 and by > ch + 1:
                break
            ln = math.sqrt(dx * dx + dy * dy * 4) or 1.0
            gs = strand_glyphs(dx, dy, (pdx * dy - pdy * dx) / ln)
            steps = int(max(abs(dx), abs(dy)) * 2) + 1
            for k in range(steps):
                f = k / steps
                y = oy + dy * f
                xi, yi = int(ox + dx * f), int(y)
                key = yi * cw + xi
                if key == last or not (0 <= xi < cw and 0 <= yi < ch) or key in own:
                    continue
                last = key
                sp = (i + f) / n
                if sp > 0.86 and (i + yi) & 1:
                    continue
                w = w0 + (1 - w0) * sp
                g = gs[0 if w < 0.25 else 1 if w < 0.55 else 2 if w < 0.82 else 3]
                if g is None:
                    g = "'" if y - yi < 0.5 else "."
                a = 0.62 - 0.42 * sp
                e = sp - gl
                if -0.2 < e < 0.2:
                    a += 0.4 * exp(-(e / 0.06) ** 2)
                if flashing:
                    a += 0.45 * flash_env(t - flash_t - sp * 1.1)
                a *= vis
                row = cells[yi]
                b = row[xi][2]
                if sp < 0.3 and b is base[yi][xi][2]:
                    b = tint
                row[xi] = (g, L[int(min(1.0, a) * 10) * top // 10], b)
            ox, oy = bx, by
            pdx, pdy = dx / ln, dy * 2 / ln

    def _arm(self, cv, base, s, L, t, fl, vis):
        """Oral arm: a frilly ribbon that twists as it hangs. Face-on it shows its frilled edge
        and face, ( S or S ), with { } at frill crests; edge-on it folds to a single §."""
        pts, n = s.pts, s.n
        cells, cw, ch = cv.cells, cv.w, cv.h
        top = NL - 1
        far = self.z > 0.55
        own = self.own
        last_row = None
        for i in range(n + 1):
            x, y = pts[i][0], pts[i][1] / ASP
            yi = int(y)
            if yi == last_row or not 0 <= yi < ch:
                continue
            last_row = yi
            sp = i / n
            frill = math.sin(sp * 9 - t * 1.8 + s.phase)
            twist = math.sin(sp * 5.5 + t * 0.7 + s.phase)
            a = ((0.72 - 0.4 * sp) + 0.45 * flash_env(t - self.flash_t - sp * 0.6)) * vis
            fg = L[int(min(1.0, a) * top)]
            xc = int(x)
            if far:
                run = ((xc, ":" if sp < 0.6 else "'"),)
            elif sp > 0.86:
                run = ((xc, "," if sp > 0.95 else "s"),)
            elif sp < 0.22:
                run = ((xc - 1, "{" if frill > 0.5 else "("), (xc, "§"), (xc + 1, "}" if frill > 0.5 else ")"))
            elif abs(twist) < 0.3:
                run = ((xc, "§"),)
            elif twist > 0:
                run = ((xc, "{" if frill > 0.5 else "("), (xc + 1, "S"))
            else:
                run = ((xc, "S"), (xc + 1, "}" if frill > 0.5 else ")"))
            row, brow = cells[yi], base[yi]
            for xi, g in run:
                if 0 <= xi < cw and yi * cw + xi not in own:
                    b = row[xi][2]
                    if b is brow[xi][2]:
                        b = L[int((0.12 - 0.07 * sp) * vis * top)]
                    row[xi] = (g, fg, b)


def main():
    p = term.make_parser("jellyfish drifting in the deep")
    p.add_argument("--count", type=int, default=4, help="number of near jellyfish (default 4); a far layer is added")
    p.add_argument("--seed", type=int, default=None, help="random seed")
    args = p.parse_args()
    rng = random.Random(args.seed)
    dt = 1 / max(1.0, args.fps)
    state = {}

    def step(cv, frame):
        w, h = cv.w, cv.h
        t = frame * dt
        if "jellies" not in state:
            n = max(1, args.count)
            nfar = max(1, (n + 1) // 2)
            zs = [rng.uniform(0.0, 0.45) for _ in range(n)] + [rng.uniform(0.62, 0.92) for _ in range(nfar)]
            jellies = []
            for z in zs:
                jellies.append(Jelly(rng, w, h, z, True, jellies))
            jellies.sort(key=lambda j: -j.z)
            state["jellies"] = jellies
            state["snow"] = [[rng.uniform(0, w), rng.uniform(0, h), rng.uniform(0.15, 0.6), rng.random() * TAU,
                              rng.random()] for _ in range(max(6, w * h // 90))]
            state["next_flash"] = rng.uniform(3, 7)
        if state.get("base_key") != (w, h, term.COLOR):
            state["base_key"], state["base"] = (w, h, term.COLOR), base_rows(w, h)
        base = state["base"]
        for y in range(h):
            cv.cells[y] = list(base[y])
        cells = cv.cells
        if term.COLOR:
            for sn in state["snow"]:
                sn[1] += sn[2] * dt * 0.5
                sn[0] += math.sin(t * 0.3 + sn[3]) * 0.25 * dt
                if sn[1] >= h:
                    sn[1], sn[0] = 0.0, rng.uniform(0, w)
                xi, yi = int(sn[0]) % w, int(sn[1])
                if 0 <= yi < h:
                    b = base[yi][xi][2]
                    lit = round((0.18 + 0.2 * sn[4] + 0.08 * math.sin(t * 0.7 + sn[3])) * 25) / 25
                    cells[yi][xi] = ("." if sn[4] > 0.75 else "·", lerp(b, SNOW_TINT, lit), b)
        jellies = state["jellies"]
        for j in jellies:
            j.step(t, dt, w, h)
        if t >= state["next_flash"]:
            state["next_flash"] = t + rng.uniform(6, 14)
            j = rng.choice(jellies)
            j.flash_t = t
            if j.z < 0.6:
                audio.sfx("jellyglow", 0.35 + 0.45 * (1 - j.z / 0.6))
        for j in jellies:
            j.prep(cv, base, t)
        if term.COLOR and term.TRUECOLOR:
            for j in reversed(jellies):
                j.glow(cv, base)
        for j in jellies:
            j.draw(cv, base, t)

    return term.run(args, step, music="jellyfish")


if __name__ == "__main__":
    sys.exit(main())
