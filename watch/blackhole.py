#!/usr/bin/env python3
"""A glyph-shaded black hole with a swirling, gravitationally lensed accretion disk."""
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
from fun import term  # noqa: E402

META = {"name": "blackhole", "kind": "watch", "blurb": "a glyph-shaded black hole with a swirling accretion disk",
        "credit": {"type": "inspired by", "who": "Raunak (@Skirook)",
                   "url": "https://x.com/Skirook/status/2118944082093588748"}}

GLYPHS = " .,:;irsXA253hMHGS#9B&@"
HEAT = [52, 88, 124, 160, 196, 202, 208, 214, 220, 226, 228, 230, 231, 255]
TEX_T = 256        # angular texture resolution (power of two for the & mask)
TEX_R = 64         # radial texture bins
R_MAX = 1.7        # radius (disk units) mapped to the last texture bin
RS = 0.33          # event horizon radius; the disk's outer edge is 1.0
FALL_MAX = 28      # cap on live infalling stars
R_IN = 0.43        # inner edge of the disk
TAU = 2 * math.pi


def build_texture(rng):
    """Streaky turbulence: rapid variation in radius, smooth in angle, with a spiral twist."""
    modes = [(m, rng.random() / m ** 0.6, rng.random() * TAU, rng.uniform(-3, 3)) for m in range(1, 11)]
    rows = []
    for rb in range(TEX_R):
        r = max(0.02, (rb + 0.5) / TEX_R * R_MAX)
        lr = math.log(r)
        jit = [rng.random() * TAU for _ in modes]
        row = []
        for ti in range(TEX_T):
            th = ti * TAU / TEX_T
            s = 0.0
            for (m, a, p, tw), j in zip(modes, jit):
                s += a * (math.sin(m * th + p + tw * lr * 3) * 0.45 + math.sin(m * th + j) * 0.55)
            row.append(s)
        rows.append(row)
    lo = min(map(min, rows))
    hi = max(map(max, rows))
    return [[((v - lo) / (hi - lo)) ** 1.6 for v in row] for row in rows]


class Scene:
    def __init__(self, args):
        self.rng = random.Random(args.seed)
        self.tex = build_texture(self.rng)
        self.cos_i = max(0.12, math.cos(math.radians(args.tilt)))
        self.sin_i = math.sin(math.radians(args.tilt))
        self.size = None
        self.parts = []
        self.fall = []

    def layout(self, w, h):
        """Per-cell polar coordinates in the disk frame; only angle offsets change per frame."""
        self.size = (w, h)
        rout = max(1.0, 0.35 * min(w, 2 * h))
        cx, cy = w / 2, h / 2
        ci, si = self.cos_i, self.sin_i
        cells, stars = [], []
        for y in range(h):
            for x in range(w):
                u = (x + 0.5 - cx) / rout
                v = (y + 0.5 - cy) * 2 / rout
                rho = math.hypot(u, v)
                if rho > 2.2:
                    continue
                phi_s = math.atan2(v, u)
                top = max(0.0, -v / rho) if rho else 0.0
                bot = max(0.0, v / rho) if rho else 0.0

                # Primary disk: invert the tilted-plane projection.
                dv = v / ci
                r = math.hypot(u, dv)
                wd, phid = 0.0, math.atan2(dv, u)
                front = v > 0
                if R_IN * 0.8 < r < 1.0 and (front or rho > RS):
                    edge = min(1.0, (r - R_IN * 0.8) / 0.12, (1.0 - r) / 0.4)
                    wd = edge * (R_IN / r) ** 0.75 * 1.3

                # Lensed copy of the far side, bent over the top and under the bottom.
                wl, rl = 0.0, rho * 1.25
                if rho > RS * 0.98:
                    centre = RS * (1.14 + 0.38 * si * top ** 2)
                    width = 0.04 + 0.055 * si * top ** 2 + 0.03 * bot
                    g = math.exp(-((rho - centre) / width) ** 2)
                    gain = 0.30 + 0.95 * top ** 1.2 + 0.28 * bot
                    wl = g * gain * (0.75 + 0.5 * RS / rho)
                    if front and wd > 0:
                        wl *= 0.4

                photon = math.exp(-((rho - RS * 1.04) / 0.022) ** 2) if rho > RS * 0.9 else 0.0
                if wd or wl or photon:
                    cells.append((x, y, front and wd > 0, rho, photon, phi_s,
                                  wd, r, phid, wl, rl,
                                  int(min(r, R_MAX - 1e-3) / R_MAX * TEX_R),
                                  int(min(rl, R_MAX - 1e-3) / R_MAX * TEX_R)))
        k = TEX_T / TAU
        q = LUT_N / 1.3
        self.disk, self.lens, self.both, self.photon = [], [], [], []
        for x, y, fr, rho, photon, phi_s, wd, r, phid, wl, rl, rbd, rbl in cells:
            d = l = None
            if wd:
                d = (wd * (1.0 - 0.55 * math.cos(phid)) * q, self.tex[rbd],
                     phid * k, 0.45 * max(r, 0.05) ** -1.5 * k)
            if wl:
                l = (wl * (1.0 - 0.55 * math.cos(phi_s)) * q, self.tex[rbl],
                     phi_s * k, 0.45 * max(rl, 0.05) ** -1.5 * k)
            if d and l:
                self.both.append((x, y) + d + l)
            elif d:
                self.disk.append((x, y) + d)
            elif l:
                self.lens.append((x, y) + l)
            if photon > 0.04:
                self.photon.append((x, y, photon))

        star_n = max(0, int(w * h * 0.035))
        for _ in range(star_n):
            sx = self.rng.uniform(-w / 2, w / 2) / rout
            sy = self.rng.uniform(-h, h) / rout
            rho = math.hypot(sx, sy)
            if rho < 0.05:
                continue
            app = rho + (RS * 0.9) ** 2 / rho  # push apparent position away from the hole
            ax, ay = sx / rho * app, sy / rho * app
            col, row = int(cx + ax * rout), int(cy + ay * rout / 2)
            if not (0 <= col < w and 0 <= row < h) or app < RS * 1.5:
                continue
            tang = None
            if app < 0.8:
                tx, ty = -ay / app, ax / app
                tang = (int(round(tx * 1.5)), int(round(ty * 0.75)))
            stars.append((col, row, self.rng.choice(".....:+*"), self.rng.random() * TAU,
                          self.rng.uniform(0.5, 2.0), tang))
        self.stars = stars
        self.rout, self.cx, self.cy = rout, cx, cy
        self.fall = []

    def spawn(self):
        if len(self.parts) < 3 and self.rng.random() < 0.012:
            self.parts.append([self.rng.uniform(1.05, 1.5), self.rng.random() * TAU, []])

    def spawn_fall(self, dt):
        """Stars appear anywhere outside the disk; each is [r, angle, prev_r, prev_angle] in disk units."""
        if len(self.fall) >= FALL_MAX or self.rng.random() > dt * 2.0:
            return
        w, h = self.size
        u = (self.rng.random() * w - self.cx) / self.rout
        v = (self.rng.random() * h - self.cy) * 2 / self.rout
        r = math.hypot(u, v)
        if r > 1.05:
            a = math.atan2(v, u)
            self.fall.append([r, a, r, a])

    def advance_fall(self, dt):
        """Radial speed grows as r^-1.5; the angle advances the same way as the disk's swirl."""
        alive = []
        for p in self.fall:
            r, a = p[0], p[1]
            p[2], p[3] = r, a
            p[0] = r - dt * (0.2 + 0.3 * r ** -1.5)
            p[1] = a + dt * 0.5 * r ** -1.5
            if p[0] > RS:
                alive.append(p)
        self.fall = alive

    def advance(self, dt):
        alive = []
        for p in self.parts:
            r, a, trail = p
            trail.append((r, a))
            del trail[:-5]
            p[0] = r - dt * (0.12 + 0.25 * (1 - r) ** 2 + 0.1)
            p[1] = a + dt * 0.9 * max(r, 0.2) ** -1.5
            if p[0] > RS * 0.8:
                alive.append(p)
        self.parts = alive


LUT_N = 48


def build_lut():
    """Brightness (0..1.3, in LUT_N steps) to a ready-made canvas cell; None where too dim."""
    lut = []
    for i in range(LUT_N + 1):
        b = i / LUT_N * 1.3
        if b < 0.05:
            lut.append(None)
            continue
        gi = min(len(GLYPHS) - 1, int(min(b, 1.25) ** 0.85 * (len(GLYPHS) - 1) / 1.15))
        ci = min(len(HEAT) - 1, int(min(b, 1.3) * 0.76 * (len(HEAT) - 1)))
        lut.append((GLYPHS[max(1, gi)], HEAT[ci], None))
    return lut


def main():
    p = term.make_parser("a glyph-shaded black hole with a swirling accretion disk")
    p.add_argument("--tilt", type=float, default=72, help="disk inclination in degrees (default 72)")
    p.add_argument("--speed", type=float, default=1.0, help="swirl speed multiplier (default 1)")
    p.add_argument("--seed", type=int, default=None, help="random seed")
    args = p.parse_args()
    args.tilt = min(88.0, max(30.0, args.tilt))
    sc = Scene(args)
    tex = sc.tex
    LUT = build_lut()
    mask = TEX_T - 1

    def step(cv, frame):
        if sc.size != (cv.w, cv.h):
            sc.layout(cv.w, cv.h)
        t = frame / max(1.0, args.fps) * args.speed * 1.6
        sc.spawn()
        sc.advance(0.05 * args.speed)
        sc.spawn_fall(0.05 * args.speed)
        sc.advance_fall(0.05 * args.speed)

        for col, row, ch, ph, rate, tang in sc.stars:
            tw = 0.5 + 0.5 * math.sin(t * rate * 1.3 + ph)
            c = 244 + int(tw * 11)
            cv.put(col, row, ch, c)
            if tang:
                cv.put(col + tang[0], row + tang[1], "-" if tang[1] == 0 else ("'" if abs(tang[0]) < 2 else "~"), 240)

        rout, ccx, ccy = sc.rout, sc.cx, sc.cy
        for r, a, r0, a0 in sc.fall:
            x, y = ccx + r * math.cos(a) * rout, ccy + r * math.sin(a) * rout / 2
            if r > 1.5:
                cv.put(x, y, ".", 242 + int((1.9 - min(r, 1.9)) * 12))
                continue
            vx = x - (ccx + r0 * math.cos(a0) * rout)
            vy = (y - (ccy + r0 * math.sin(a0) * rout / 2)) * 2
            ax, ay = abs(vx), abs(vy)
            ch = "-" if ay < 0.4 * ax else "|" if ax < 0.4 * ay else "\\" if vx * vy > 0 else "/"
            heat = (1.5 - r) / (1.5 - RS)
            col = 246 + int(heat * 9) if heat < 0.6 else (229, 231)[heat > 0.85]
            cv.put(x, y, ch, col)
            if heat > 0.35:
                n = math.hypot(vx, vy) or 1.0
                cv.put(x - vx / n * 1.5, y - vy / (n * 2) * 1.5, ch if heat > 0.6 else ".", 240 + int(heat * 8))

        pulse = 1.6 * (0.88 + 0.12 * math.sin(t * 2.1))
        rows = cv.cells
        lut = LUT
        top = LUT_N
        for x, y, a, tr, kp, ko in sc.disk:
            i = int(a * (0.45 + tr[int(kp - ko * t) & mask]))
            c = lut[i if i < top else top]
            if c:
                rows[y][x] = c
        for x, y, a, tr, kp, ko in sc.lens:
            i = int(a * (0.3 + tr[int(kp - ko * t) & mask]))
            c = lut[i if i < top else top]
            if c:
                rows[y][x] = c
        for x, y, a, tr, kp, ko, a2, tr2, kp2, ko2 in sc.both:
            i = int(a * (0.45 + tr[int(kp - ko * t) & mask]))
            j = int(a2 * (0.3 + tr2[int(kp2 - ko2 * t) & mask]))
            if j > i:
                i = j
            c = lut[i if i < top else top]
            if c:
                rows[y][x] = c
        for x, y, ph in sc.photon:
            pb = ph * pulse
            if pb > 0.3:
                rows[y][x] = ("@" if pb > 0.9 else "#", 231 if pb > 1.0 else (229 if pb > 0.6 else 117), None)

        for r, a, trail in sc.parts:
            for i, (tr, ta) in enumerate(trail[-3:]):
                tx = sc.cx + tr * math.cos(ta) * sc.rout
                ty = sc.cy + tr * math.sin(ta) * sc.cos_i * sc.rout / 2
                cv.put(tx, ty, ".", 208 + i * 6 if i < 2 else 226)
            cv.put(sc.cx + r * math.cos(a) * sc.rout, sc.cy + r * math.sin(a) * sc.cos_i * sc.rout / 2, "*", 231)

    return term.run(args, step, music="blackhole")


if __name__ == "__main__":
    sys.exit(main())
