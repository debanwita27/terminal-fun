#!/usr/bin/env python3
"""Ink: short streaks of ink drifting and curling on a slow current over paper.

Each streak is a chain of square half-block pixels, a near-black navy head fading through
royal and light blue to pale cyan and then the paper. The current is a divergence-free
flow (the curl of a few drifting plane waves plus wandering vortices) whose overall
direction swings every half minute or so. Streaks hook, curl and now and then split; a
head that stalls pools into a soft blot that spreads and fades. A rare cell is orange or
yellow.

Usage: python3 ink.py [--fps 12] [--frames N] [--theme paper|night] [--count N] [--seed N] [--mute]
  --theme night   glowing cyan streaks on deep navy
  --count N       streaks alive at once (default: sized to the terminal, 30-60)
"""

META = {'name': 'ink',
        'kind': 'watch',
        'blurb': 'Streaks of blue ink curling on a slow current over paper, now and then pooling into a blot',
        'credit': {'type': 'inspired by',
                   'who': 'fluid ink animation (artist unknown), via Pinterest user asa01200',
                   'url': 'https://in.pinterest.com/pin/757519599867416526/'}}

import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

from fun import audio, term  # noqa: E402

TAU = 2 * math.pi
UP = "▀"

# Palettes: paper, grain tint, ink stops by ink strength (1 head .. 0 gone), halo tint,
# accent hues. Ink stops end on the paper itself so the faintest ink never reads darker
# than intended.
THEMES = {
    "paper": dict(
        paper=(246, 244, 238), grain=(-3, 1),
        ink=((1.0, (10, 12, 34)), (0.86, (14, 22, 74)), (0.72, (20, 48, 150)), (0.56, (46, 98, 214)),
             (0.40, (104, 158, 236)), (0.24, (166, 208, 246)), (0.10, (214, 238, 248)), (0.0, None)),
        halo=(118, 128, 152), halo_k=0.2,
        accent=((236, 104, 24), (244, 196, 36))),
    "night": dict(
        paper=(10, 16, 36), grain=(-1, 1),
        ink=((1.0, (236, 252, 255)), (0.86, (168, 244, 252)), (0.72, (80, 214, 240)), (0.56, (36, 150, 222)),
             (0.40, (28, 96, 180)), (0.24, (22, 58, 120)), (0.10, (16, 32, 70)), (0.0, None)),
        halo=(40, 150, 210), halo_k=0.34,
        accent=((255, 140, 50), (255, 214, 80))),
}
G = 6     # paper grain levels
HL = 6    # halo levels
N = 14    # ink levels: few, like the reference's handful of distinct tones, so cells repaint rarely
NA = 5    # levels per accent hue
I_HALO, I_INK = G, G + HL
I_ACC = I_INK + N + 1
K = I_ACC + 2 * NA


def mix(a, b, t):
    return (int(a[0] + (b[0] - a[0]) * t + 0.5), int(a[1] + (b[1] - a[1]) * t + 0.5),
            int(a[2] + (b[2] - a[2]) * t + 0.5))


def grad(stops, u, paper):
    """Colour at ink strength u along stops given high to low."""
    for (p1, c1), (p0, c0) in zip(stops, stops[1:]):
        if u >= p0:
            c0 = c0 or paper
            return mix(c0, c1 or paper, (u - p0) / (p1 - p0))
    return paper


def smooth(x):
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


def value_noise(w, h, cell, rng):
    """Smooth value noise on a w x h grid, lattice spacing `cell`, values 0..1."""
    gw, gh = int(w / cell) + 2, int(h / cell) + 2
    lat = [[rng.random() for _ in range(gw)] for _ in range(gh)]
    out = []
    for y in range(h):
        fy = y / cell
        j = int(fy)
        ty = smooth(fy - j)
        row = []
        for x in range(w):
            fx = x / cell
            i = int(fx)
            tx = smooth(fx - i)
            a = lat[j][i] + (lat[j][i + 1] - lat[j][i]) * tx
            b = lat[j + 1][i] + (lat[j + 1][i + 1] - lat[j + 1][i]) * tx
            row.append(a + (b - a) * ty)
        out.append(row)
    return out


# ------------------------------------------------------------------ the current

class Flow:
    """Velocity in pixels/s: the curl of drifting plane waves (stream function
    sum A sin(k.x + phase)), point vortices with soft cores, and a uniform current whose
    heading eases to a new target every 20-45 s. Every term is divergence-free."""

    def __init__(self, W, H, rng):
        self.W, self.H, self.rng = W, H, rng
        span = max(40.0, min(W, H * 1.6))
        self.waves = []
        for _ in range(6):
            L = rng.uniform(0.45, 1.4) * span
            s = 1.5 * (L / span) ** 0.5           # peak speed this wave adds
            self.waves.append([rng.random() * TAU, rng.uniform(-0.025, 0.025), TAU / L, s,
                               rng.random() * TAU, rng.uniform(0.08, 0.22) * rng.choice((-1, 1))])
        nv = max(2, min(6, W * H // 2600))
        self.vort = [[rng.uniform(0, W), rng.uniform(0, H), rng.uniform(70, 150) * rng.choice((-1, 1)),
                      rng.uniform(4.0, 9.0), rng.random() * TAU] for _ in range(nv)]
        self.cang = rng.random() * TAU
        self.ctarget = self.cang
        self.cmag = 1.2
        self.cmag_target = 1.2
        self.next_turn = rng.uniform(12, 25)
        self.t = 0.0
        self.step(0.0)

    def step(self, dt):
        rng, W, H = self.rng, self.W, self.H
        self.t += dt
        t = self.t
        self.next_turn -= dt
        if self.next_turn <= 0:
            self.next_turn = rng.uniform(20, 45)
            self.ctarget = self.cang + rng.uniform(0.7, 2.4) * rng.choice((-1, 1))
            self.cmag_target = rng.uniform(0.7, 1.9)
        k = min(1.0, dt * 0.09)
        self.cang += (self.ctarget - self.cang) * k
        self.cmag += (self.cmag_target - self.cmag) * k
        self.cu, self.cv = self.cmag * math.cos(self.cang), self.cmag * math.sin(self.cang)
        # Per-frame wave constants: (A*ky, -A*kx, kx, ky, phase) so velocity is one cos each.
        wc = []
        for wv in self.waves:
            a0, drift, kk, s, ph, om = wv
            a = a0 + drift * t
            kx, ky = kk * math.cos(a), kk * math.sin(a)
            wc.append((s * math.sin(a), -s * math.cos(a), kx, ky, ph + om * t))
        self.wc = wc
        m = 14.0
        for v in self.vort:
            v[4] += dt * 0.07
            v[0] += (self.cu * 0.8 + 0.6 * math.cos(v[4] * 1.3)) * dt
            v[1] += (self.cv * 0.8 + 0.6 * math.sin(v[4])) * dt
            # Vortices wrap through a margin wide enough that the jump is never seen.
            if v[0] < -m:
                v[0] += W + 2 * m
            elif v[0] > W + m:
                v[0] -= W + 2 * m
            if v[1] < -m:
                v[1] += H + 2 * m
            elif v[1] > H + m:
                v[1] -= H + 2 * m
        self.vc = [(v[0], v[1], v[2] * (0.65 + 0.35 * math.sin(t * 0.05 + v[4] * 3)) / TAU, v[3] * v[3])
                   for v in self.vort]

    def vel(self, x, y):
        cos, exp = math.cos, math.exp
        u, v = self.cu, self.cv
        for au, av, kx, ky, ph in self.wc:
            c = cos(kx * x + ky * y + ph)
            u += au * c
            v += av * c
        for vx, vy, g, rc2 in self.vc:
            dx, dy = x - vx, y - vy
            r2 = dx * dx + dy * dy + 1e-6
            if r2 < 900:
                f = g * (1 - exp(-r2 / rc2)) / r2
                u -= dy * f
                v += dx * f
        return u, v


# ------------------------------------------------------------------ streaks and blots

class Streak:
    __slots__ = ("x", "y", "ix", "iy", "age", "life", "T", "pts", "alive", "speed", "theta",
                 "spin", "spin_t", "pause", "pause_len", "pooled", "thick", "strength", "wph", "wamp",
                 "wf", "dead_at")

    def __init__(self, x, y, rng, life=None, theta=0.0):
        self.x, self.y = x, y
        self.ix, self.iy = int(x), int(y)
        self.age = 0.0
        self.life = life or rng.uniform(6.0, 20.0)
        self.T = rng.uniform(2.6, 6.5)              # seconds a trail cell takes to fade
        self.pts = []                                # [x, y, t_enter, extras, accent, k, u_drop]
        self.alive = True
        self.speed = rng.uniform(0.75, 1.3)
        self.theta = theta                           # heading offset from the flow; relaxes to 0
        self.spin = 0.0
        self.spin_t = 0.0
        self.pause = self.pause_len = 0.0
        self.dead_at = 0.0
        self.pooled = False
        self.thick = rng.uniform(0.12, 0.5)
        self.strength = 1.0 if rng.random() < 0.82 else rng.uniform(0.55, 0.8)
        self.wph = rng.random() * TAU
        self.wamp = rng.uniform(0.15, 0.7)
        self.wf = rng.uniform(0.3, 1.1)


class Ink:
    def __init__(self, w, h, rng, theme, count, quiet=False):
        self.w, self.h, self.rng = w, h, rng
        self.W, self.H = w, 2 * h
        self.t = 0.0
        self.quiet = quiet
        self.count = count or max(30, min(60, w * h // 150))
        self.flow = Flow(self.W, self.H, rng)
        self.streaks = []
        self.blots = []
        self.build_palette(THEMES[theme])
        self.build_paper(THEMES[theme])
        n = self.W * self.H
        self.hash = [rng.random() for _ in range(n)]

    # ---------------------------------------------------------- static
    def build_palette(self, th):
        paper = th["paper"]
        cols = []
        lo, hi = th["grain"]
        for g in range(G):
            d = lo + (hi - lo) * g / (G - 1)
            cols.append(tuple(max(0, min(255, int(c + d * k + 0.5))) for c, k in zip(paper, (1.0, 1.0, 1.15))))
        for i in range(HL):
            cols.append(mix(paper, th["halo"], th["halo_k"] * (i + 1) / HL))
        for i in range(N + 1):
            cols.append(grad(th["ink"], i / N, paper))
        for hue in th["accent"]:
            for i in range(NA):
                cols.append(mix(paper, hue, ((i + 1) / NA) ** 0.6))
        self.cols = cols
        cl = []
        for a in range(K):
            ca = cols[a]
            for b in range(K):
                cb = cols[b]
                cl.append((" ", None, ca) if ca == cb else (UP, ca, cb))
        self.cl = cl
        # NO_COLOR: one glyph per cell from the stronger of its two pixels.
        gl = [" "] * K
        for i in range(N + 1):
            f = i / N
            gl[I_INK + i] = " " if f < 0.1 else "·" if f < 0.4 else "•" if f < 0.75 else "●"
        for i in range(2 * NA):
            gl[I_ACC + i] = "*"
        self.gl = gl

    def build_paper(self, th):
        """Per-pixel grain level: two octaves of value noise and a hash; flat under 256
        colours, where near-white shades quantize into blotches."""
        W, H, rng = self.W, self.H, self.rng
        if not term.TRUECOLOR:
            self.paper = [G // 2] * (W * H)
            return
        n1 = value_noise(W, H, 9.0, rng)
        n2 = value_noise(W, H, 2.5, rng)
        out = []
        for y in range(H):
            r1, r2 = n1[y], n2[y]
            for x in range(W):
                v = 0.5 * r1[x] + 0.3 * r2[x] + 0.2 * rng.random()
                out.append(max(0, min(G - 1, int(v * G + 0.5) - 1)))
        self.paper = out

    # ---------------------------------------------------------- simulation
    def spawn(self, x=None, y=None, life=None, theta=0.0):
        rng, W, H = self.rng, self.W, self.H
        if x is None:
            heads = [(s.x, s.y) for s in self.streaks if s.alive]
            best, bd = None, -1.0
            for _ in range(5):
                cx, cy = rng.uniform(2, W - 2), rng.uniform(2, H - 2)
                d = min([(cx - a) ** 2 + (cy - b) ** 2 for a, b in heads] or [1e9])
                if d > bd:
                    best, bd = (cx, cy), d
            x, y = best
        s = Streak(x, y, rng, life, theta)
        self.record(s, s.ix, s.iy, 0, 0)
        self.streaks.append(s)
        return s

    def record(self, s, ix, iy, dx, dy):
        """Append pixel (ix, iy) to s's trail with its thickening and speckle cells."""
        rng = self.rng
        px, py = -dy, dx                      # perpendicular to the step
        if px == 0 and py == 0:
            px, py = rng.choice(((1, 0), (0, 1)))
        side = 1 if rng.random() < 0.5 else -1
        ex = []
        if rng.random() < s.thick:
            ex.append((ix + px * side, iy + py * side, rng.uniform(0.8, 0.95)))
        if rng.random() < 0.22:
            k = rng.choice((1, 2, 2))
            ex.append((ix - px * side * k - dx * rng.randint(0, 1), iy - py * side * k - dy * rng.randint(0, 1),
                       rng.uniform(0.28, 0.55)))
        acc = -1
        if rng.random() < 0.0035:
            acc = 0 if rng.random() < 0.7 else 1
        s.pts.append([ix, iy, self.t, ex, acc, rng.uniform(0.86, 1.0), 0.45 + 0.65 * rng.random()])

    def update(self, dt):
        rng, W, H = self.rng, self.W, self.H
        self.t += dt
        t = self.t
        flow = self.flow
        flow.step(dt)
        alive = 0
        parents = []
        for s in self.streaks:
            if not s.alive:
                continue
            s.age += dt
            # Steering events: a hook (a burst of spin, then a slow relax back onto the
            # flow), a stall that pools into a blot, and a split.
            if s.spin_t > 0:
                s.spin_t -= dt
                s.theta += s.spin * dt
            else:
                s.theta *= max(0.0, 1 - dt * 0.35)
                if rng.random() < dt / 14:
                    s.spin = rng.uniform(1.0, 2.0) * rng.choice((-1, 1))
                    s.spin_t = rng.uniform(0.6, 1.4)
            slow = 1.0
            if s.pause > 0:
                s.pause -= dt
                f = max(0.0, s.pause / s.pause_len)   # 1 at the stall's start .. 0 at its end
                slow = 1 - 0.96 * smooth((1 - f) * 4) * smooth(f * 4)
            elif s.age > 2.0 and not s.pooled and len(self.blots) < 3 and rng.random() < dt / 45:
                s.pause = s.pause_len = rng.uniform(2.5, 4.5)
                s.pooled = True
                R0 = rng.uniform(1.8, 3.0)
                lobes = [(0.0, 0.0, 1.0)] + [(rng.gauss(0, R0 * 0.5), rng.gauss(0, R0 * 0.5), rng.uniform(0.45, 0.8))
                                             for _ in range(rng.randint(1, 3))]
                self.blots.append([s.x, s.y, t, R0, rng.randrange(W * H), lobes])
                if not self.quiet:
                    audio.sfx("inkdrip", 0.12)
                if rng.random() < 0.55:
                    s.life = min(s.life, s.age + s.pause_len * 0.7)
            if s.age > 1.5 and s.pause <= 0 and rng.random() < dt / 55 and len(self.streaks) < self.count * 1.6:
                parents.append(s)
            u, v = flow.vel(s.x, s.y)
            a = s.theta + s.wamp * math.sin(t * s.wf + s.wph)
            c, sn = math.cos(a), math.sin(a)
            k = s.speed * slow * dt
            nx = s.x + (u * c - v * sn) * k
            ny = s.y + (u * sn + v * c) * k
            s.x, s.y = nx, ny
            ix, iy = math.floor(nx), math.floor(ny)
            while ix != s.ix or iy != s.iy:
                dx = (ix > s.ix) - (ix < s.ix)
                dy = (iy > s.iy) - (iy < s.iy)
                s.ix += dx
                s.iy += dy
                self.record(s, s.ix, s.iy, dx, dy)
            if s.age > s.life or not (-2 < nx < W + 2 and -2 < ny < H + 2):
                s.alive = False
                s.dead_at = t
            else:
                alive += 1
        for p in parents:
            c = self.spawn(p.x, p.y, rng.uniform(3.0, 9.0), rng.uniform(0.6, 1.1) * rng.choice((-1, 1)))
            c.T = min(c.T, p.T)
            alive += 1
        # Trails age out from the tail; a dead streak goes once its newest cell has faded.
        keep = []
        for s in self.streaks:
            pts = s.pts
            T = s.T
            while len(pts) > 1 and t - pts[1][2] > T:
                del pts[0]
            if s.alive or t - s.dead_at < T:
                keep.append(s)
        self.streaks = keep
        if alive < self.count and rng.random() < 0.5:
            self.spawn()
        self.blots = [b for b in self.blots if self.blot_state(b, t)[1] > 0.03]

    def blot_state(self, b, t):
        """(radius, intensity) of a blot: it swells over 1.5 s, holds, then spreads and fades."""
        a = t - b[2]
        R0 = b[3]
        if a < 1.5:
            return 0.8 + (R0 - 0.8) * smooth(a / 1.5), 1.0
        f = a - 1.5
        return R0 * (1 + 0.05 * f), (1.0 if f < 2.0 else math.exp(-(f - 2.0) / 3.5))

    # ---------------------------------------------------------- drawing
    def frame(self, cv, dt):
        self.update(dt)
        t, W, H = self.t, self.W, self.H
        buf = self.paper[:]
        hsh = self.hash
        n = W * H
        hi0 = I_HALO - 1
        exp = math.exp

        # Blots: a few overlapping gaussian lobes, speckled by a fixed per-pixel hash so
        # the core reads as clustered dark cells, inside a wide soft halo.
        for b in self.blots:
            R, I = self.blot_state(b, t)
            bx, by, seed, lobes = b[0], b[1], b[4], b[5]
            Rh = R * 2.3
            ih2 = 1.0 / (Rh * Rh * 0.4)
            lob = [(bx + ox * R / b[3], by + oy * R / b[3], 1.0 / (R * R * rs * rs)) for ox, oy, rs in lobes]
            for py in range(max(0, int(by - Rh)), min(H, int(by + Rh) + 2)):
                cy = py + 0.5
                row = py * W
                for px in range(max(0, int(bx - Rh)), min(W, int(bx + Rh) + 2)):
                    cx = px + 0.5
                    g = 0.0
                    for lx, ly, ir2 in lob:
                        e = ((cx - lx) ** 2 + (cy - ly) ** 2) * ir2
                        if e < 6.0:
                            q = exp(-e)
                            if q > g:
                                g = q
                    i = row + px
                    core = I * g * (0.5 + 0.9 * hsh[(i + seed) % n])
                    if core > 0.2:
                        v = I_INK + min(N, int((0.3 + core) * N + 0.5))
                    else:
                        d2 = (cx - bx) ** 2 + (cy - by) ** 2
                        hl = int(I * exp(-d2 * ih2) * HL * 1.35 + core * 6)
                        if hl <= 0:
                            continue
                        v = hi0 + min(HL, hl)
                    if v > buf[i]:
                        buf[i] = v

        # Streaks: cell j's age is the time since the head left it.
        for s in self.streaks:
            pts = s.pts
            m = len(pts)
            if not m:
                continue
            T = s.T
            st = s.strength * min(1.0, s.age / 0.5)
            end = t if s.alive else s.dead_at
            for j in range(m):
                p = pts[j]
                u = (t - (pts[j + 1][2] if j + 1 < m else end)) / T
                if u >= p[6]:
                    continue  # the tail thins out cell by cell before it fades away
                ink = st * p[5] * (1.0 - u ** 1.6)
                x, y = p[0], p[1]
                if 0 <= x < W and 0 <= y < H:
                    i = y * W + x
                    if p[4] >= 0 and ink > 0.4:
                        v = I_ACC + p[4] * NA + min(NA - 1, int((ink - 0.4) / 0.6 * NA + 2))
                    else:
                        v = I_INK + int(ink * N + 0.5)
                    if v > buf[i]:
                        buf[i] = v
                    if ink > 0.62:
                        hv = hi0 + int((ink - 0.5) * 2 * HL * 0.8 + 0.5)
                        for xx, yy in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                            if 0 <= xx < W and 0 <= yy < H:
                                k = yy * W + xx
                                if hv > buf[k]:
                                    buf[k] = hv
                for xx, yy, sc in p[3]:
                    if 0 <= xx < W and 0 <= yy < H:
                        k = yy * W + xx
                        v = I_INK + int(ink * sc * N + 0.5)
                        if v > buf[k]:
                            buf[k] = v

        cells = cv.cells
        if term.COLOR:
            cl = self.cl
            for y in range(self.h):
                r = 2 * y * W
                cells[y] = [cl[a * K + b] for a, b in zip(buf[r:r + W], buf[r + W:r + 2 * W])]
        else:
            gl = self.gl
            for y in range(self.h):
                r = 2 * y * W
                cells[y] = [(gl[a if a > b else b], None, None) for a, b in zip(buf[r:r + W], buf[r + W:r + 2 * W])]


def main():
    p = term.make_parser(__doc__.splitlines()[0], fps=12)
    p.add_argument("--theme", choices=sorted(THEMES), default="paper", help="paper (default) or night")
    p.add_argument("--count", type=int, default=None, help="streaks alive at once (default: sized to the terminal)")
    p.add_argument("--seed", type=int, default=None, help="random seed")
    args = p.parse_args()
    rng = random.Random(args.seed)
    dt = 1 / max(1.0, args.fps)
    count = None if args.count is None else max(1, min(200, args.count))
    st = {"ink": None}

    def step(cv, frame):
        k = st["ink"]
        if k is None or (k.w, k.h) != (cv.w, cv.h):
            k = st["ink"] = Ink(cv.w, cv.h, rng, args.theme, count, quiet=True)
            for _ in range(int(9 / dt)):  # start mid-flow rather than on blank paper
                k.update(dt)
            k.quiet = False
        k.frame(cv, dt)

    return term.run(args, step, music="ink")


if __name__ == "__main__":
    raise SystemExit(main())
