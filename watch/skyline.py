#!/usr/bin/env python3
"""Skyline: a harbour city through a compressed dawn, day, dusk and night.

Three layers of half-block silhouettes (hazy far towers, mid-rise blocks with small
windows, crisp near buildings) with spires, domes, water towers and blinking antenna
lights stand on a quay over water that mirrors them with a shimmer. The truecolor sky
drifts from pastel dawn through soft blue day, golden hour and rose-violet dusk into deep
indigo night; the sun and moon are solid discs with soft halos, and cloud bands drift and
catch the light. Windows come on a few at a time at dusk (warm lamps, office white, TV
blue, blinds) and go dark late at night, under a city glow and bright streetlights. A
plane passes (a contrail by day, nav lights by night), birds cross at dawn and cars
streak along the quay. Sound: lo-fi electric piano over a distant traffic hush, with a
far siren or train at night and birdsong at dawn.

Usage: python3 skyline.py [--fps 12] [--frames N] [--cycle 90] [--start 0.0] [--no-plane] [--seed N]
  --cycle S    seconds per full day (default 90)
  --start P    initial phase 0..1 (0 sunrise, 0.3 day, 0.47 golden hour, 0.56 dusk,
               0.7 night, 0.97 dawn)
  --seed N     city layout and events (random by default)
"""

META = {"name": "skyline", "kind": "watch", "blurb": "City silhouettes through a day, dusk, night and dawn cycle",
        "credit": None}

import math
import os
import random
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

from fun import audio, term

MONO = not term.COLOR
DITHER = term.COLOR and not term.TRUECOLOR

# Day keyframes: (phase, sky top, mid sky, horizon, shade, cloud, cloud underside, dark).
# shade is the tone silhouettes fall toward with nearness; dark runs 0 (day) .. 1 (night).
KEYS = [
    (0.000, (112, 116, 184), (198, 162, 198), (255, 194, 164), (54, 46, 86), (222, 176, 206), (255, 204, 176), .3),
    (0.070, (96, 150, 218), (172, 198, 232), (232, 222, 226), (52, 62, 98), (246, 242, 248), (255, 230, 214), 0.),
    (0.160, (70, 138, 222), (126, 180, 238), (186, 218, 242), (44, 58, 92), (252, 252, 255), (208, 220, 238), 0.),
    (0.380, (72, 136, 220), (130, 182, 236), (196, 222, 240), (44, 58, 92), (252, 252, 255), (208, 220, 238), 0.),
    (0.470, (104, 140, 204), (232, 198, 164), (255, 190, 112), (72, 54, 70), (252, 232, 208), (255, 186, 108), .04),
    (0.535, (86, 76, 160), (214, 122, 152), (255, 150, 98), (54, 32, 64), (204, 130, 172), (255, 154, 102), .2),
    (0.585, (50, 42, 116), (148, 80, 150), (236, 122, 138), (34, 22, 54), (132, 84, 146), (240, 130, 144), .45),
    (0.640, (22, 24, 72), (64, 46, 108), (122, 76, 130), (16, 14, 38), (56, 46, 94), (116, 76, 122), .78),
    (0.720, (8, 9, 30), (20, 18, 54), (40, 32, 82), (6, 6, 16), (30, 28, 60), (66, 46, 72), 1.),
    (0.880, (8, 9, 30), (20, 18, 54), (40, 32, 82), (6, 6, 16), (30, 28, 60), (66, 46, 72), 1.),
    (0.945, (30, 32, 86), (76, 64, 130), (152, 104, 150), (22, 20, 46), (74, 64, 114), (152, 112, 150), .7),
]
KEYS.append((1.0,) + KEYS[0][1:])
FIELDS = ("top", "mid", "hor", "shade", "cloud", "under", "dark")

SUN_HI, SUN_LO = (255, 250, 232), (255, 150, 80)
GLOW_HI, GLOW_LO = (255, 240, 214), (255, 132, 90)
MOON, MOON_GLOW = (250, 244, 216), (150, 136, 214)
SUNSET = .565             # the sun rises at phase 0 and is down by SUNSET
MOONRISE = .6             # the moon crosses from MOONRISE to 1.0
LPOL = (255, 150, 96)     # city light pollution on the low sky
LAMP = (255, 222, 164)
STAR = (255, 250, 236)
BEACON, BEACON_OFF = (255, 64, 56), (110, 34, 40)
WARM = ((255, 206, 128), (255, 188, 104), (255, 222, 162), (248, 170, 92))
COOL, TV = (210, 228, 255), (96, 140, 255)
HEAD, TAIL = (255, 244, 214), (255, 64, 54)
CAR_DAY = ((198, 72, 62), (62, 108, 176), (226, 226, 230), (44, 44, 50), (220, 178, 72))
BIRD = (26, 24, 42)
TRAIL_LIFE = 14.0         # seconds a contrail takes to dissolve

FAR, MID, NEAR = 1, 2, 3
# (height lo, hi as a fraction of the city's pixel height, width lo, hi, gap choices, roofs)
LAYERS = {
    FAR: (.28, .54, 3, 8, (0,), ("flat", "flat", "spire", "stepped", "antenna", "slant", "pyramid")),
    MID: (.2, .42, 5, 11, (0, 0, 1), ("flat", "stepped", "dome", "tower", "antenna", "pyramid", "box", "spire")),
    NEAR: (.08, .3, 6, 13, (0, 0, 1, 2), ("flat", "tower", "box", "parapet", "gable", "antenna", "flat")),
}


def mix(a, b, k):
    """Lerp two rgb tuples; k is clamped to 0..1."""
    k = 0.0 if k < 0 else 1.0 if k > 1 else k
    return (int(a[0] + (b[0] - a[0]) * k + .5), int(a[1] + (b[1] - a[1]) * k + .5),
            int(a[2] + (b[2] - a[2]) * k + .5))


def smooth(e0, e1, x):
    t = (x - e0) / (e1 - e0)
    t = 0.0 if t < 0 else 1.0 if t > 1 else t
    return t * t * (3 - 2 * t)


def palette(p):
    for k0, k1 in zip(KEYS, KEYS[1:]):
        if k0[0] <= p <= k1[0]:
            u = smooth(k0[0], k1[0], p)
            pal = {}
            for i, name in enumerate(FIELDS, 1):
                a, b = k0[i], k1[i]
                # quantised so slow stretches of the day leave most cells untouched between steps
                pal[name] = (tuple(v & ~3 for v in mix(a, b, u)) if isinstance(a, tuple)
                             else round((a + (b - a) * u) * 64) / 64)
            return pal
    return dict(zip(FIELDS, KEYS[0][1:]))


def sun_at(p):
    """(u along the arc, altitude 0..1) while the sun is up, else None."""
    u = p / SUNSET
    return (u, math.sin(math.pi * u)) if 0 <= u <= 1 else None


def moon_at(p):
    u = (p - MOONRISE) / (1 - MOONRISE)
    return (u, math.sin(math.pi * u)) if 0 <= u <= 1 else None


def lights_on(dark):
    return .07 + .93 * smooth(.08, .72, dark)


def lights_off(p):
    """Late-night switch-off level: windows whose off threshold is below it go dark."""
    if .74 <= p < .97:
        return .85 * smooth(.74, .97, p)
    if p >= .97 or p < .09:
        return .85
    return .85 * (1 - smooth(.09, .15, p))


class City:
    """Static layout for one terminal size: building pixels, windows, masts, lamps, stars, clouds.

    Pixels are half cells: column x, pixel row py (two per cell row). lay[x][py] holds
    layer | side << 2 (side 1 = left wall, 2 = right wall) or 0 for open sky.
    """

    def __init__(self, w, h, rng):
        self.w, self.h = w, h
        self.wh = max(3, round(h * .2)) if h >= 16 else 0      # water rows
        self.sh = max(1, h - 1 - self.wh)                     # sky and city rows; the quay is row sh
        B = self.B = 2 * self.sh
        self.lay = [[0] * B for _ in range(w)]
        self.masts, self.bld = [], []
        for layer in (FAR, MID, NEAR):
            self._row(layer, rng)
        self.open = [[not self.lay[x][2 * y] and not self.lay[x][2 * y + 1] for x in range(w)]
                     for y in range(self.sh)]
        self.lamps = list(range(rng.randint(2, 7), w, 9)) if self.sh >= 4 else []
        self._windows(rng)
        self.stars = [(rng.randrange(w), rng.randrange(max(1, int(self.sh * .8))), rng.randrange(1 << 20))
                      for _ in range(w * self.sh // 26)]
        self.cw = w + 70  # cloud world width; blobs drift across it and wrap
        self.blobs = []
        for _ in range(rng.randint(2, 3)):
            cy0 = rng.uniform(.08, .42) * B
            for _ in range(max(2, self.cw // 40)):
                # one bank: a long soft base with a few puffs stacked on its top
                cx, rx = rng.uniform(0, self.cw), rng.uniform(12, 24)
                self.blobs.append((cx, cy0 + rng.uniform(-1, 1), rx, rng.uniform(3.5, 5.5), rng.uniform(.35, .55)))
                for _ in range(rng.randint(1, 3)):
                    self.blobs.append((cx + rng.uniform(-.6, .6) * rx, cy0 - rng.uniform(2.5, 5),
                                       rng.uniform(5, 10), rng.uniform(3, 4.5), rng.uniform(.25, .45)))

    def _row(self, layer, rng):
        lo, hi, wmin, wmax, gaps, roofs = LAYERS[layer]
        B, w = self.B, self.w
        mark = rng.uniform(.25, .75) * w if layer == MID else None  # a landmark spire
        x = -rng.randint(0, 3)
        while x < w:
            bw, f, kind = rng.randint(wmin, wmax), rng.uniform(lo, hi), rng.choice(roofs)
            if layer == FAR and rng.random() < .15:
                f, bw = hi + .08, max(wmin, bw - 2)
            if mark is not None and x <= mark < x + 12:
                kind, bw, f, mark = "spire", max(bw, 9), .5, None
            self._building(layer, x, bw, int(B - f * B), kind, rng)
            x += bw + rng.choice(gaps)

    def _building(self, layer, x0, bw, top, kind, rng):
        B = self.B
        top = max(4, top)
        tops = [top] * bw
        extra, masts = [], []
        if kind == "stepped":
            l, r, t = 0, bw, top
            for _ in range(rng.randint(1, 3)):
                ins = rng.randint(1, 2)
                if r - l - 2 * ins < 2:
                    break
                l, r, t = l + ins, r - ins, t - rng.randint(3, 6)
                for i in range(l, r):
                    tops[i] = t
            if rng.random() < .4:
                masts.append(((l + r) // 2, t - rng.randint(3, 6)))
        elif kind == "spire":
            l, r, t = 1, bw - 1, top - rng.randint(3, 5)
            for i in range(l, r):
                tops[i] = t
            while r - l > 2:
                l, r, t = l + 1, r - 1, t - 2
                for i in range(l, r):
                    tops[i] = t
            masts.append((l, t - rng.randint(4, 8)))
        elif kind == "dome" and bw >= 5:
            rad, c = (bw - 2) / 2, bw / 2
            for i in range(1, bw - 1):
                dx = i + .5 - c
                tops[i] = top - int(round(math.sqrt(max(0.0, rad * rad - dx * dx)) * .9))
            if rng.random() < .7:
                masts.append((bw // 2, min(tops) - 3))
        elif kind in ("pyramid", "gable"):
            div = 1 if kind == "pyramid" else 2
            for i in range(bw):
                tops[i] = top - min(i, bw - 1 - i) // div
        elif kind == "slant":
            rise, left = rng.randint(3, max(3, bw)), rng.random() < .5
            for i in range(bw):
                k = i / max(1, bw - 1)
                tops[i] = top - int(round(rise * (1 - k if left else k)))
        elif kind == "tower" and bw >= 6:
            o = rng.randint(1, bw - 5)
            tops[o] = tops[o + 3] = top - 2
            extra += [(o + i, top - 6, top - 2) for i in range(4)]
            extra += [(o + 1, top - 7, top - 6), (o + 2, top - 7, top - 6)]
        elif kind == "box" and bw >= 4:
            o, n = rng.randint(1, bw - 3), rng.randint(2, 3)
            for i in range(o, min(bw - 1, o + n)):
                tops[i] = top - rng.choice((2, 3))
        elif kind == "parapet":
            tops[0] = tops[-1] = top - 1
        elif kind == "antenna":
            masts.append((rng.randint(1, max(1, bw - 2)), top - rng.randint(4, 9)))
        for i, tip in masts:
            if tops[i] % 2:
                tops[i] -= 1  # the mast starts on a cell boundary, so no half-cell gap shows
            x = x0 + i
            if 0 <= x < self.w and tip // 2 < tops[i] // 2 <= self.sh:
                self.masts.append((x, max(0, tip // 2), tops[i] // 2, layer, rng.random() < .75,
                                   rng.uniform(0, 1.6)))
        for i, t in enumerate(tops):
            x = x0 + i
            if 0 <= x < self.w:
                side = 1 if i == 0 else 2 if i == bw - 1 else 0
                col = self.lay[x]
                t = max(0, t)
                col[t:B] = [layer | side << 2] * (B - t)
                if t < B:
                    col[t] = layer | 3 << 2  # the lit roof edge
        for i, a, b in extra:
            x = x0 + i
            if 0 <= x < self.w and a >= 0:
                self.lay[x][a:b] = [layer] * (b - a)
        use = rng.choice(("home", "home", "office", "mixed") if layer == NEAR else ("office", "home", "office"))
        style = rng.choice(("single", "pair", "band", "sparse") if layer == NEAR else ("single", "band"))
        if use == "office" and layer == NEAR and rng.random() < .6:
            style = "band"
        self.bld.append((layer, x0, bw, tops, style, use))

    def _windows(self, rng):
        """Window cells that end up visible (not hidden by a nearer layer), sorted by switch-on level."""
        lay, sh, out, lamps = self.lay, self.sh, [], set(self.lamps)
        for layer, x0, bw, tops, style, use in self.bld:
            last = sh - 2 if layer == NEAR else sh - 1
            for i in range(1, bw - 1):
                x = x0 + i
                if not 0 <= x < self.w:
                    continue
                if layer == FAR:
                    cols = True
                elif style == "single":
                    cols = i % 2 == 1
                elif style == "pair":
                    cols = (i - 1) % 3 != 2
                elif style == "sparse":
                    cols = i % 3 == 1
                else:
                    cols = True
                if not cols:
                    continue
                col = lay[x]
                for y in range(max(0, (tops[i] + 3) // 2), last + 1):
                    if col[2 * y] & 3 != layer or col[2 * y + 1] & 3 != layer:
                        continue
                    if layer == FAR and rng.random() > .05:
                        continue
                    if style == "sparse" and y % 2:
                        continue
                    out.append(self._window(rng, x, y, layer, use))
            if layer == NEAR and sh >= 3:
                y = sh - 1
                lit = rng.random() < .5
                for i in range(1, bw - 1):
                    x = x0 + i
                    if rng.random() < .25:
                        lit = not lit
                    if lit and x not in lamps and 0 <= x < self.w and lay[x][2 * y] & 3 == NEAR and lay[x][2 * y + 1] & 3 == NEAR:
                        out.append((rng.uniform(.05, .5), rng.uniform(.2, .6), x, y, NEAR, "shop",
                                    rng.choice(WARM), "▄"))
        out.sort(key=lambda wn: wn[0])
        self.windows = out

    def _window(self, rng, x, y, layer, use):
        if layer == FAR:
            return (rng.uniform(.1, 1), rng.uniform(.1, 1), x, y, layer, "far",
                    mix(rng.choice(WARM), (255, 255, 255), .2), "·")
        if use == "mixed":
            use = rng.choice(("home", "office"))
        r = rng.random()
        if use == "office":
            kind = "cool" if r < .75 else "warm" if r < .985 else "flicker"
            on, off = rng.uniform(0, .55), rng.uniform(0, .5)
        else:
            kind = ("warm" if r < .5 else "blind" if r < .65 else "curtain" if r < .78
                    else "tv" if r < .92 else "cool")
            on, off = rng.uniform(.08, 1), rng.uniform(.15, 1)
        lamp = COOL if kind in ("cool", "flicker") else TV if kind == "tv" else rng.choice(WARM)
        if kind == "blind":
            lamp = mix(lamp, (196, 112, 58), .35)
        if layer == MID:
            glyph = "▘"
        else:
            glyph = rng.choice("▘▝") if kind == "curtain" else "▀"
        return (on, off, x, y, layer, kind, lamp, glyph)


class Base:
    """Everything static for one palette step: rows of cells plus what the overlays need."""

    def __init__(self, city, p):
        w, sh, B, wh, lay = city.w, city.sh, city.B, city.wh, city.lay
        pal = self.pal = palette(p)
        top, hor, shade, dark = pal["top"], pal["hor"], pal["shade"], pal["dark"]
        self.dark = dark
        sun = sun_at(p)
        self.gold = gold = (1 - sun[1]) ** 3 if sun and dark < .5 else 0.0
        suncol = mix(SUN_LO, SUN_HI, sun[1] ** .5) if sun else SUN_HI
        # sky per cell row (plain spaces); the warm horizon colour is reached just above the roofline
        span = max(1.0, sh * .8)
        midc = pal["mid"]

        def grad(u):
            return mix(top, midc, u / .55) if u < .55 else mix(midc, hor, (u - .55) / .45)
        rowcol = self.rowcol = [mix(grad(min(1.0, (y + .5) / span) ** 1.15), LPOL,
                                    .34 * dark * ((y + .5) / sh) ** 4) for y in range(sh)]
        skypx = self.skypx = [rowcol[py // 2] for py in range(B)]
        haze, mid_sky = skypx[-1], skypx[int(B * .45)]
        # building colours by layer and pixel row: nearer is darker, far layers fade into the haze
        base_col = {FAR: mix(mid_sky, shade, .24 + .3 * dark), MID: mix(mid_sky, shade, .55 + .25 * dark),
                    NEAR: mix(mix(mid_sky, hor, .3), shade, .82 + .14 * dark)}
        fade = {FAR: .55, MID: .25, NEAR: 0.0}
        rim_side = 1 if sun and sun[0] < .5 else 2
        ramps = [None] * 16
        for layer, bc in base_col.items():
            ramp = [mix(bc, haze, (py / B) ** 2.5 * fade[layer]) for py in range(B)]
            if layer == NEAR and dark:
                ramp = [mix(c, LAMP, (py / B) ** 10 * .14 * dark) for py, c in enumerate(ramp)]
            rk = gold * (.3, .2, .12)[NEAR - layer]
            lit = [mix(c, suncol, rk) for c in ramp] if rk > .01 else ramp
            roof = [mix(c, mix(top, suncol, gold), .14 + .1 * gold - .08 * dark) for c in ramp]
            for side in (0, 1, 2):
                ramps[layer | side << 2] = lit if side == rim_side else ramp
            ramps[layer | 3 << 2] = roof
        occ = self.occ = []
        for x in range(w):
            col = lay[x]
            occ.append([ramps[c][py] if c else None for py, c in enumerate(col)] if any(col) else [None] * B)
        # cloud bands: summed gaussian puffs with flatter, lit undersides, over open sky only
        cover = .85 - .35 * dark
        acc = [None] * w
        off = p * city.cw * .35
        for cx, cy, rx, ry, a in (() if DITHER or MONO else city.blobs):  # blotchy in 256 colours
            sx = (cx + off) % city.cw - 35
            x0, x1 = max(0, int(sx - 2.2 * rx)), min(w, int(sx + 2.2 * rx) + 1)
            gys = []
            for py in range(max(0, int(cy - 2.2 * ry)), min(B, int(cy + 1.6 * ry) + 1)):
                dy = (py + .5 - cy) / ry
                e = dy * dy * (2.2 if dy > 0 else 1.0)
                gys.append((py, a * math.exp(-e), .5 + .5 * max(-1.0, min(1.0, dy * 1.4))))
            for x in range(x0, x1):
                dx = (x + .5 - sx) / rx
                gx = math.exp(-dx * dx)
                if gx < .03:
                    continue
                d = acc[x]
                if d is None:
                    d = acc[x] = {}
                for py, gy, un in gys:
                    v = gx * gy
                    if v > .02:
                        q = d.get(py)
                        if q is None:
                            d[py] = [v, v * un]
                        else:
                            q[0] += v
                            q[1] += v * un
        cloud, under = pal["cloud"], pal["under"]
        clp = self.clp = [None] * w    # per column {py: (alpha, cloud colour)} for the disc patch
        clc = [None] * w               # per column {py: composited colour}
        for x, d in enumerate(acc):
            if not d:
                continue
            pa, pc = {}, {}
            clp[x], clc[x] = pa, pc
            for py, (v, vu) in d.items():
                if py >= B or occ[x][py] is not None:
                    continue
                al = (1 - math.exp(-1.6 * v)) * cover
                if al < .04:
                    continue
                cc = mix(cloud, under, vu / v)
                pa[py] = (al, cc)
                pc[py] = mix(skypx[py], cc, al)
        # cells
        dith = None
        if DITHER:
            # dithered in two runs (top -> mid sky, mid sky -> horizon) to follow the three-stop gradient
            ym = max(1, min(sh - 1, int(span * .55 ** (1 / 1.15))))
            dith = list(term.sky_rows(top, midc, ym, w, gamma=1.0)) if ym < sh else []
            dith += list(term.sky_rows(midc, haze, sh - len(dith), w, gamma=1.0))
        rows = self.rows = []
        mono = MONO and (" ", "░", "▒", "█")
        for y in range(sh):
            pa, pb = 2 * y, 2 * y + 1
            sa, sb = skypx[pa], skypx[pb]
            plain = (" ", None, sa) if sa == sb else ("▀", sa, sb)
            drow = dith[y] if dith else None
            row = []
            app = row.append
            for x in range(w):
                o = occ[x]
                a, b = o[pa], o[pb]
                if mono:
                    la, lb = lay[x][pa] & 3, lay[x][pb] & 3
                    if la == lb:
                        app((mono[la], None, None) if la else (" ", None, None))
                    elif not la:
                        app(("▄", None, None) if lb == NEAR else (mono[lb], None, None))
                    else:
                        app(("▀", None, None) if la == NEAR and not lb else (mono[max(la, lb)], None, None))
                    continue
                cc = clc[x]
                if a is None:
                    a = cc.get(pa, sa) if cc else sa
                if b is None:
                    b = cc.get(pb, sb) if cc else sb
                if a is sa and b is sb:
                    app(drow[x] if drow else plain)
                elif o[pa] is None and o[pb] is None:
                    app((" ", None, mix(a, b, .5)))  # soft cloud: one colour per cell
                else:
                    app((" ", None, a) if a == b else ("▀", a, b))
            rows.append(row)
        # antenna masts and their beacon tips
        self.mastcells, self.beacons = {}, []
        for x, r0, r1, layer, light, ph in city.masts:
            for y in range(r0, r1):
                if lay[x][2 * y] or lay[x][2 * y + 1]:
                    continue
                cell = rows[y][x]
                bg = None if MONO else self.rgb(y, cell)
                ch = "╷" if y == r0 else "│"
                rows[y][x] = (ch, None if MONO else occ[x][r1 * 2] or base_col[layer], bg)
                self.mastcells[(x, y)] = ch
                if y == r0 and light:
                    self.beacons.append((x, y, ph, bg))
        self.stars = []
        for x, y, hs in city.stars:
            cc = clc[x]
            if city.open[y][x] and not (cc and (2 * y in cc or 2 * y + 1 in cc)) and (x, y) not in self.mastcells:
                self.stars.append((x, y, hs, rows[y][x][2], rowcol[y]))
        near = base_col[NEAR]
        # quay row: road surface over the quay wall, warmed under each streetlight at night
        if sh < city.h:
            road, wall = mix(near, hor, .14), mix(near, (0, 0, 0), .35)
            quay = [("▀", None, None) if MONO else ("▀", road, wall)] * w
            if dark and not MONO:
                quay = quay[:]
                for lx in city.lamps:
                    for dx in (-2, -1, 0, 1, 2):
                        if 0 <= lx + dx < w:
                            quay[lx + dx] = ("▀", mix(road, LAMP, (.35 - .12 * abs(dx)) * dark), wall)
            rows.append(quay)
            self.road, self.wall = road, wall
        # streetlight heads on the bottom city row
        self.lamp_cells = {}
        if city.lamps and sh >= 2:
            row = rows[sh - 1]
            for lx in city.lamps:
                for dx in (-1, 1):
                    if 0 <= lx + dx < w and row[lx + dx][0] == " " and not MONO:
                        row[lx + dx] = (" ", None, mix(self.rgb(sh - 1, row[lx + dx]), LAMP, .14 * dark))
                bg = None if MONO else self.rgb(sh - 1, row[lx])
                head = ("•", None, None) if MONO else ("•", mix((60, 60, 70), LAMP, dark), mix(bg, LAMP, .3 * dark))
                row[lx] = head
                self.lamp_cells[lx] = head
        # water: a gradient from the low sky to the high sky, with the city mirrored into it
        self.refl = []
        for j in range(wh):
            k = (j / max(1, wh - 1)) ** .8
            wc = mix(mix(hor, shade, .3 + .3 * dark), mix(top, shade, .55), k)
            src = rows[sh - 1 - j] if sh - 1 - j >= 0 else rows[0]
            s = .6 - .25 * j / wh
            pad = []
            for x in range(-2, w + 2):
                xx = 0 if x < 0 else w - 1 if x >= w else x
                if MONO:
                    pad.append((" ", None, None))
                else:
                    pad.append((" ", None, mix(wc, mix(self.rgb(sh - 1 - j, src[xx]), shade, .3), s)))
            self.refl.append(pad)
            rows.append(pad[2:w + 2])
        # windows: unlit glass goes into the base; lit variants are drawn per frame
        vis = .3 + .7 * dark
        self.lit = []
        for on, off, x, y, layer, kind, lamp, glyph in city.windows:
            if MONO:
                cell = (" " if layer != FAR else "·", None, None)  # lit windows are holes in solid walls
                self.lit.append((cell,) * 3 if kind in ("tv", "flicker") else cell)
                continue
            o = occ[x]
            wt, wb = o[2 * y], o[2 * y + 1]
            if layer == NEAR:
                if kind == "shop":
                    glass = mix(wb, top, .15)
                    rows[y][x] = ("▄", glass, wt)
                    self.lit.append(("▄", mix(glass, lamp, vis), mix(wt, lamp, .12 * dark)))
                    continue
                glass = mix(wt, top, .22 - .1 * dark)
                if gold and (x * 7 + y * 13) % 17 < gold * 7:
                    glass = mix(wt, suncol, .25 + .4 * gold)
                rows[y][x] = (glyph, glass, wb)
                bg = mix(wb, lamp, .13 * dark)
                if kind in ("tv", "flicker"):
                    self.lit.append(tuple((glyph, mix(glass, mix(lamp, (0, 0, 0), dim), vis), bg)
                                          for dim in (0.0, .3, .55)))
                else:
                    self.lit.append((glyph, mix(glass, lamp, vis), bg))
            elif layer == MID:
                fg = mix(wt, lamp, vis * .75)
                self.lit.append(tuple((glyph, mix(wt, fg, 1 - dim), wb) for dim in (0.0, .3, .55))
                                if kind in ("tv", "flicker") else (glyph, fg, wb))
            else:
                self.lit.append(("·", mix(wt, lamp, .65 * dark), wb))
        self.glint = mix(hor, (255, 255, 255), .2) if dark < .5 else mix(hor, LPOL, .25)

    def rgb(self, y, cell):
        """An rgb colour for blending over this cell (dithered sky cells carry 256-colour ints)."""
        if cell[0] == "▀" and cell[1].__class__ is tuple:
            return mix(cell[1], cell[2], .5)
        bg = cell[2]
        return bg if bg.__class__ is tuple else self.rowcol[min(y, len(self.rowcol) - 1)]


def body_patch(city, base, cx, cy, r, halo, core, glow, k, moon):
    """Cells around a sun or moon disc at pixel (cx, cy): the solid disc with a halo blended
    from the sky row, clouds composited in front, buildings left in front of both."""
    occ, clp, skypx, sh, w = base.occ, base.clp, base.skypx, city.sh, city.w
    if DITHER:
        halo *= .5  # a wide halo bands into rings in 256 colours
    R = r + (0 if MONO else halo)
    out = []
    rim = mix(core, glow, .4)
    dark = mix(core, glow, .3)
    for y in range(max(0, int(cy - R) // 2), min(sh, int(cy + R) // 2 + 1)):
        for x in range(max(0, int(cx - R)), min(w, int(cx + R) + 1)):
            o, cl = occ[x], clp[x]
            px, hit, discs = [], False, 0
            for py in (2 * y, 2 * y + 1):
                if o[py] is not None:
                    px.append(o[py])
                    continue
                c = cl.get(py) if cl else None
                sc = skypx[py]
                d = math.hypot(x + .5 - cx, py + .5 - cy)
                if d < r:
                    hit, discs = True, discs + (1 if py & 1 else 2)
                    if moon and math.hypot(x - cx + 1.0, py - cy + .6) < 1.1:
                        col = mix(core, dark, .3)
                    else:
                        col = mix(core, rim, (d / r) ** 3 * .45)
                    if c:
                        col = mix(col, mix(c[1], glow, .5), c[0] * .8)
                else:
                    g = 1 - (d - r) / halo
                    if g > 0:
                        hit = True
                        col = mix(sc, glow, g ** 1.9 * k)
                        if c:
                            col = mix(col, mix(c[1], glow, g * .7), c[0])
                        # coarse steps: a one-pixel move of the disc leaves most halo cells alone
                        col = (col[0] & ~3, col[1] & ~3, col[2] & ~3)
                    else:
                        col = mix(sc, c[1], c[0]) if c else sc
                px.append(col)
            if not hit:
                continue
            if MONO:
                if discs:
                    out.append((y, x, ("█" if discs == 3 else "▀" if discs == 2 else "▄", None, None)))
                continue
            a, b = px
            ch = base.mastcells.get((x, y))
            if ch:
                cell = (ch, base.rows[y][x][1], mix(a, b, .5))
            else:
                cell = (" ", None, a) if a == b else ("▀", a, b)
            out.append((y, x, cell))
    return out


def main():
    parser = term.make_parser(__doc__.splitlines()[0], fps=12)
    parser.add_argument("--cycle", type=float, default=90, help="seconds per day (default 90)")
    parser.add_argument("--start", type=float, default=0.0, help="initial phase 0..1")
    parser.add_argument("--no-plane", action="store_true", help="no plane")
    parser.add_argument("--seed", type=int, default=None, help="city layout and events")
    args = parser.parse_args()
    dt = 1 / max(1.0, args.fps)
    cycle = max(1.0, args.cycle)
    steps = int(max(40, min(400, cycle / 1.2)))  # palette steps per day; the scene repaints once per step
    ev = random.Random(None if args.seed is None else args.seed + 1)
    s = {"key": None, "city": None, "base": None, "patch": None, "plane": None, "trail": [],
         "star": None, "cars": [], "birds": None, "flips": {}, "siren": -99.0, "train": -99.0}

    def step(c, frame):
        w, h = c.w, c.h
        t = frame * dt
        if s["key"] != (w, h):
            rng = random.Random(None if args.seed is None else args.seed * 7919 + w * 131 + h)
            s.update(key=(w, h), city=City(w, h, rng), base=None, patch=None, plane=None, trail=[],
                     star=None, cars=[], birds=None, flips={})
        city = s["city"]
        sh, wh = city.sh, city.wh
        p = (args.start + t / cycle) % 1.0
        q = round(p * steps) % steps
        base = s["base"]
        if base is None or base.q != q:
            base = s["base"] = Base(city, q / steps)
            base.q = q
            s["patch"] = None
        dark, pal = base.dark, base.pal
        rows = c.cells = [r[:] for r in base.rows]
        tq = int(t * 5)

        # twinkling stars, fading in with the dark
        sv = smooth(.35, .95, dark)
        if sv > .02 and not MONO:
            for x, y, hs, bg, sc in base.stars:
                lv = (tq + hs) % 23
                ch, k = ("+", 1.0) if lv == 0 and hs & 3 == 0 else ("·", .8) if lv < 8 else (".", .5)
                rows[y][x] = (ch, mix(sc, STAR, k * sv * (.6 + .4 * (hs >> 4 & 1))), bg)
        elif sv > .02:
            for x, y, hs, bg, sc in base.stars:
                rows[y][x] = ("." if (tq + hs) % 23 > 3 else "+", None, None)

        # sun or moon, as a disc and halo patch cached per pixel position
        sun, moon = sun_at(p), moon_at(p)
        disc = None
        if sun:
            u, alt = sun
            low = 1 - alt
            r = 3.0 + 3.0 * low ** 1.5
            disc = ("sun", round(w * (.06 + .88 * u)), round(city.B * (1 - .9 * alt ** .6)), round(r * 2) / 2,
                    9 + 16 * low ** 1.5, mix(SUN_LO, SUN_HI, alt ** 1.4), mix(GLOW_LO, GLOW_HI, alt ** 1.2),
                    .4 + .35 * low)
        elif moon:
            u, alt = moon
            disc = ("moon", round(w * (.1 + .8 * u)), round(city.B - alt * city.B * .84), 3.8, 10.0,
                    MOON, MOON_GLOW, .45)
        if disc:
            key = disc[:4]
            if s["patch"] is None or s["patch"][0] != key:
                s["patch"] = (key, body_patch(city, base, disc[1] + .5, disc[2], disc[3], disc[4], disc[5],
                                              disc[6], disc[7], disc[0] == "moon"))
            for y, x, cell in s["patch"][1]:
                rows[y][x] = cell

        # antenna beacons blink at night
        if dark > .45:
            for x, y, ph, bg in base.beacons:
                on = (t + ph) % 1.6 < .45
                if MONO:
                    rows[y][x] = ("•" if on else "·", None, None)
                else:
                    rows[y][x] = ("•", BEACON if on else BEACON_OFF, mix(bg, BEACON, .12) if on else bg)

        # windows: switched on in order of their threshold, off late at night, a few flipping
        lvl, late = lights_on(dark), lights_off(p)
        flips = s["flips"]
        if ev.random() < .25 and city.windows:
            i = ev.randrange(len(city.windows))
            flips[i] = t + ev.uniform(3, 15)
        for i in [i for i, until in flips.items() if until < t]:
            del flips[i]
        wins, lit = city.windows, base.lit
        # odd water rows sway a column either way, slowly, so the mirrored city shimmers
        offs = [int(round(math.sin(int(t * 1.5 + j * .37) * 1.3 + j * 1.9) * (.6 + .1 * j))) if j % 2 else 0
                for j in range(wh)]
        reflect = []
        n = len(wins)
        i = 0
        while i < n and wins[i][0] < lvl:
            wn = wins[i]
            on = (wn[1] > late) != (i in flips)
            if on:
                cell = lit[i]
                kind = wn[5]
                if kind == "tv":
                    cell = cell[(((tq >> 1) + i) * 2654435761 >> 9) % 3]
                elif kind == "flicker":
                    cell = cell[0 if ((frame + i) * 40503 >> 5) % 7 else 2]
                rows[wn[3]][wn[2]] = cell
                if wn[4] == NEAR and sh - 1 - wn[3] < wh:
                    reflect.append((wn[2], sh - 1 - wn[3], wn[6]))
            i += 1
        for i in flips:
            if i < n and wins[i][0] >= lvl and dark > .3:
                wn = wins[i]
                cell = lit[i]
                rows[wn[3]][wn[2]] = cell[0] if isinstance(cell[0], tuple) else cell

        # cars streaking along the quay
        if sh < h:
            if ev.random() < dt / 3.2 and len(s["cars"]) < 3:
                d = ev.choice((1, -1))
                s["cars"].append({"x": -2.0 if d > 0 else w + 1.0, "d": d, "v": ev.uniform(7, 13),
                                  "col": ev.choice(CAR_DAY), "n": ev.randint(3, 5)})
            qrow = rows[sh]
            for car in s["cars"]:
                car["x"] += car["d"] * car["v"] * dt
                x0, d = int(car["x"]), car["d"]
                light = HEAD if d > 0 else TAIL
                for k in range(car["n"] if dark > .4 else 1):
                    x = x0 - k * d
                    if 0 <= x < w:
                        if MONO:
                            qrow[x] = ("━" if k == 0 else "─", None, None)
                        elif dark > .4:
                            qrow[x] = ("▀", mix(base.road, light, (1 - k / car["n"]) ** 1.5), qrow[x][2])
                        else:
                            qrow[x] = ("▀", mix(mix(car["col"], base.road, .35), light, .4 * dark), qrow[x][2])
            s["cars"] = [car for car in s["cars"] if -6 < car["x"] < w + 6]

        # water: the mirrored city shimmers row by row, with glints, a light path and lit windows
        if wh:
            mq = int(t * 4)
            for j in range(wh):
                y = sh + 1 + j
                o = offs[j]
                row = rows[y] = base.refl[j][2 + o:2 + o + w]
                per = 7 + 3 * j
                if MONO:
                    for x in range(-(int(t * 2) + j * 5) % per, w, per):
                        row[x] = ("~" if j % 2 else "─", None, None)
                    continue
                gk = .3 / (1 + j) ** .5
                for x in range(-(j * 5 + int(t * (2.5 - .2 * j)) * (1 if j % 2 else -1)) % per, w, per):
                    bg = row[x][2]
                    row[x] = ("─" if j % 3 else "~", mix(bg, base.glint, gk), bg)
            if disc and not MONO:
                dx, alt = disc[1], (sun or moon)[1]
                strength = (.75 * (1 - alt) ** .5 + .1) if disc[0] == "sun" else .6
                for j in range(wh):
                    y = sh + 1 + j
                    row = rows[y]
                    jit = int(1.6 * math.sin(mq * .9 + y * 1.7))
                    half = 1 + j // 2 + int(2 * (1 - alt))
                    for x in range(dx - half + jit, dx + half + jit + 1):
                        if 0 <= x < w and (x * 3 + y + mq) % 4:
                            bg = row[x][2]
                            row[x] = ("━" if j else "~", mix(bg, disc[5], strength / (1 + .3 * j)), bg)
            if dark > .2:
                for x, j, lamp in reflect:
                    x += offs[j]
                    if 0 <= x < w and (x * 5 + j * 3 + mq) % 5:
                        row = rows[sh + 1 + j]
                        bg = row[x][2]
                        row[x] = ("▄", None, None) if MONO else ("▄", mix(bg, lamp, .55 * dark * (1 - .5 * j / wh)), bg)
                for lx in city.lamps:
                    for j in range(wh):
                        x = lx + offs[j]
                        if 0 <= x < w and (j + mq + lx) % 3:
                            row = rows[sh + 1 + j]
                            bg = row[x][2]
                            if not MONO:
                                row[x] = ("▬" if j % 2 else "━", mix(bg, LAMP, .5 * dark / (1 + .25 * j)), bg)

        # a plane: a contrail by day, blinking nav lights by night
        trail = s["trail"]
        if not args.no_plane:
            pl = s["plane"]
            if pl is None and ev.random() < dt / 22 and sh > 8:
                d = ev.choice((1, -1))
                pl = s["plane"] = {"x": -2.0 if d > 0 else w + 1.0, "d": d,
                                   "y": ev.randint(1, max(1, int(sh * .3))), "last": None}
            if pl:
                pl["x"] += pl["d"] * 5 * dt
                x, y = int(pl["x"]), pl["y"]
                if not -3 < pl["x"] < w + 3:
                    s["plane"] = None
                else:
                    if dark < .55 and x != pl["last"] and 0 <= x < w:
                        trail.append((x - pl["d"], y, t))
                    pl["last"] = x
                    if 0 <= x < w:
                        bg = rows[y][x][2]
                        sc = None if MONO else base.rgb(y, rows[y][x])
                        if MONO:
                            rows[y][x] = ("•", None, None)
                        elif dark < .55:
                            rows[y][x] = ("•", (236, 238, 246), bg)
                        else:
                            ph = t % 1.2
                            col = (255, 255, 255) if ph < .08 else BEACON if .5 < ph < .7 else (90, 90, 110)
                            rows[y][x] = ("•" if col != (90, 90, 110) else "·", col, mix(sc, col, .25) if ph < .08 else bg)
        if trail:
            tc = pal["cloud"]
            keep = []
            for x, y, tb in trail:
                age = t - tb
                if age > TRAIL_LIFE:
                    continue
                keep.append((x, y, tb))
                if 0 <= x < w and city.open[y][x]:
                    bg = rows[y][x][2]
                    if MONO:
                        rows[y][x] = ("─" if age < 6 else "╌", None, None)
                    else:
                        rows[y][x] = ("─" if age < 6 else "╌", mix(base.rgb(y, rows[y][x]), tc, .6 * (1 - age / TRAIL_LIFE) * (1 - dark)), bg)
            s["trail"] = keep

        # birds crossing at dawn, with a little song
        dawn = p > .965 or p < .1
        fl = s["birds"]
        if fl is None and dawn and ev.random() < dt / 8 and sh > 8:
            d = ev.choice((1, -1))
            fl = s["birds"] = {"x": -4.0 if d > 0 else w + 4.0, "d": d, "y": ev.uniform(2, sh * .45),
                               "n": ev.randint(4, 8), "ph": ev.uniform(0, 6)}
            audio.sfx("dawnbirds", .35)
        if fl:
            fl["x"] += fl["d"] * 3.2 * dt
            for k in range(fl["n"]):
                # a loose V seen from the side: two arms trailing back from the leader
                side, rank = (1 if k % 2 else -1), (k + 1) // 2
                x = int(fl["x"] - fl["d"] * (rank * 2 + (side > 0)))
                y = int(fl["y"] + side * rank * .45 + .5 * math.sin(t * 1.3 + k * 1.7))
                if 0 <= x < w and 0 <= y < sh:
                    ch = "vv-^-"[(frame // 2 + k * 3) % 5]
                    bg = rows[y][x][2]
                    rows[y][x] = (ch, None if MONO else mix(base.rgb(y, rows[y][x]), BIRD, .8), bg)
            if not -12 < fl["x"] < w + 12:
                s["birds"] = None
        if dawn and ev.random() < dt / 9:
            audio.sfx("dawnbirds", .22)

        # shooting stars on dark nights
        ss = s["star"]
        if ss is None and dark > .9 and ev.random() < dt / 8:
            ss = s["star"] = {"x": ev.uniform(w * .3, w), "y": ev.uniform(0, sh * .3), "life": 14}
        if ss:
            ss["x"] -= 2.4
            ss["y"] += .8
            ss["life"] -= 1
            if ss["life"] <= 0:
                s["star"] = None
            else:
                for k in range(6, -1, -1):
                    x, y = int(ss["x"] + 2.4 * k), int(ss["y"] - .8 * k)
                    if 0 <= x < w and 0 <= y < sh and city.open[y][x]:
                        bg = rows[y][x][2]
                        if MONO:
                            rows[y][x] = ("*" if k == 0 else "-" if k < 3 else ".", None, None)
                        else:
                            rows[y][x] = ("*" if k == 0 else "─" if k < 3 else "·",
                                          mix(base.rgb(y, rows[y][x]), STAR, 1 - k / 7), bg)

        # distant city sounds at night
        if dark > .75:
            if t - s["siren"] > 45 and ev.random() < dt / 70:
                s["siren"] = t
                audio.sfx("siren", .2)
            if t - s["train"] > 40 and ev.random() < dt / 80:
                s["train"] = t
                audio.sfx("train", .3)

    return term.run(args, step, music="skyline")


if __name__ == "__main__":
    raise SystemExit(main())
