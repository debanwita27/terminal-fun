#!/usr/bin/env python3
"""Fireworks: rockets rise over a night skyline and burst into peony, chrysanthemum,
ring, willow and crackle shells, reflected in the water below.

Usage: python3 fireworks.py [--fps 20] [--frames N] [--seed N] [--finale [--banner T] [--note T] [--hold]]
  --finale   play a ~6s grand finale and exit (a "Claude finished" signal)
  --hold     after the finale keep a gentle show and the banner up until a key is pressed;
             exits 0 on a key, QUIT_CODE on q (needs a tty, otherwise exits after the finale)
"""

META = {"name": "fireworks", "kind": "watch",
        "blurb": "Rockets burst into peony, chrysanthemum, ring, willow and crackle shells over a skyline",
        "credit": None}

import math
import random

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

from fun import audio, braille, term
from fun.braille import _BITS

# All motion is in braille pixels: a cell is 2x4 of them, so pixels are roughly square.
GRAVITY = 56.0
FINALE_SECONDS = 6.0
QUIT_CODE = 3
MAX_SPARKS = 1400   # live sparks over all shells; the finale's frame cost scales with this
MAX_GLINTS = 90
LEVELS = 16         # colour ramp steps over a spark's life
TRAIL_SAMPLES = 22  # trail points at most; trails are sampled about one pixel apart

WHITE = (255, 248, 236)
HUES = {"pink": (255, 70, 180), "blue": (50, 125, 255), "cyan": (40, 225, 255),
        "gold": (255, 196, 60), "red": (255, 50, 40), "green": (70, 255, 100),
        "violet": (170, 90, 255), "orange": (255, 130, 20), "silver": (215, 225, 255),
        "magenta": (255, 60, 240)}
PAIRS = [("pink", "blue"), ("gold", "red"), ("cyan", "violet"), ("green", "gold"),
         ("silver", "blue"), ("orange", "cyan"), ("magenta", "cyan"), ("red", "silver"),
         ("violet", "pink"), ("gold", "green")]
# drag k (1/s), gravity factor, trail seconds, life range (s), tail fade in ramp steps,
# rays (evenly spaced, 0 = random dots), extra short-trail sparks
SPECS = {
    "peony": (2.4, 1.0, 0.12, (1.1, 1.6), 5, 0, 150),
    "chrysanthemum": (2.0, 0.8, 0.40, (1.3, 1.8), 10, 56, 20),
    "ring": (2.4, 0.6, 0.20, (1.1, 1.5), 6, 72, 24),
    "willow": (1.9, 0.9, 1.0, (2.4, 3.2), 8, 64, 20),
    "crackle": (2.4, 1.0, 0.12, (0.8, 1.2), 4, 0, 110),
}
KINDS = ["peony", "chrysanthemum", "chrysanthemum", "chrysanthemum", "ring", "willow", "crackle"]
TWINKLE = "·+✦+·"
GRID, BUILDING, WINDOW, RIPPLE = (34, 36, 54), (3, 3, 8), (84, 70, 38), (24, 32, 52)
SKY_TOP, SKY_LOW, WATER = (6, 8, 18), (14, 14, 28), (4, 6, 14)

_ramps = {}
_tints = {}


def ramp(hue, bright):
    """LEVELS (luminance, rgb) steps: white-hot, the full hue, then cooling (blue fades first)."""
    key = (hue, bright)
    if key not in _ramps:
        out = []
        for i in range(LEVELS):
            f = i / (LEVELS - 1)
            if f < 0.2:
                u = f / 0.2
                c = [w + (h - w) * u for w, h in zip(WHITE, hue)]
            else:
                k = 1.0 if f < 0.55 else 1 - 0.65 * (f - 0.55) / 0.45
                c = [hue[0] * k ** 0.8, hue[1] * k, hue[2] * k ** 1.15]
            c = tuple(min(255, int(v * bright)) & ~7 for v in c)
            out.append((3 * c[0] + 6 * c[1] + c[2], c))
        _ramps[key] = tuple(out)
    return _ramps[key]


def tint(base, col, k):
    """base plus k of col, cached (reflections, lit rooftops and windows)."""
    key = (base, col, k)
    if key not in _tints:
        _tints[key] = tuple(min(255, int(b + c * k)) & ~3 for b, c in zip(base, col))
    return _tints[key]


def jitter(hue, rng=20):
    return tuple(max(0, min(255, v + random.randint(-rng, rng))) for v in hue)


def draw_banner(c, lines):
    """Centered box in the upper third; lines are (text, fg)."""
    width = min(c.w - 2, max(len(t) for t, _ in lines) + 4)
    if width < 8 or c.h < len(lines) + 4:
        return
    x0, y0 = (c.w - width) // 2, max(1, c.h // 3 - len(lines) // 2 - 1)
    for i in range(len(lines) + 2):
        c.text(x0, y0 + i, " " * width, 231, 236)
    for i, (t, fg) in enumerate(lines):
        t = t if len(t) <= width - 4 else t[:width - 5] + "…"
        c.text(x0 + (width - len(t)) // 2, y0 + 1 + i, t, fg, 236)


class Shell:
    """One burst. Linear drag has a closed form, so every spark's position at time t is
    centre + v * A(t) + (0, B(t)) with A, B shared by the whole shell."""

    def __init__(self, x, y, kind, radius, size, budget):
        self.x, self.y, self.kind, self.t = x, y, kind, 0.0
        self.k, grav, self.tau, (lo, hi), self.fade, rays, extra = SPECS[kind]
        self.g = GRAVITY * grav
        self.size, self.radius = size, radius
        self.bright = round(min(1.0, 0.55 + 0.45 * size), 1)
        v0 = radius * self.k
        inner, outer = (HUES[h] for h in random.choice(PAIRS))
        if kind == "willow":
            inner, outer = (255, 165, 50), (255, 210, 110)
        elif kind == "crackle":
            inner, outer = HUES["silver"], HUES["gold"]
        rin = [ramp(jitter(inner), self.bright) for _ in range(2)]
        rout = [ramp(jitter(outer), self.bright) for _ in range(2)]
        self.core = rout[0]
        self.glow_rgb = tuple((o * 2 + w) // 3 for o, w in zip(outer, WHITE))
        tilt, rot = random.uniform(0.3, 1.0), random.uniform(0, 2 * math.pi)
        scale = max(0.5, min(1.0, budget / (rays * 1.5 + extra + 1)))
        rays, extra = int(rays * scale), int(extra * scale)
        dirs = []  # (dx, dy, speed fraction, ramp, short trail)
        if rays:
            for layer, (n, s0, rps) in enumerate(((rays, 1.0, rout), (rays // 2, 0.55, rin))):
                if kind == "willow" and layer:
                    break
                for i in range(n):
                    # evenly spaced rays keep clear gaps; a little depth varies their length
                    a = rot + 2 * math.pi * (i + random.uniform(-0.2, 0.2) + 0.5 * layer) / n
                    px, py = math.cos(a), math.sin(a)
                    if kind == "ring":
                        px, py = px, py * tilt
                        px, py = px * math.cos(rot) - py * math.sin(rot), px * math.sin(rot) + py * math.cos(rot)
                        z = 0.0
                    else:
                        z = random.uniform(-0.45, 0.45)
                    dirs.append((px, py, s0 * math.sqrt(1 - z * z) * random.uniform(0.97, 1.03),
                                 random.choice(rps), False))
        for i in range(extra):
            # a sphere band, projected: few sparks head at the viewer
            z, a = random.uniform(-0.7, 0.7), random.uniform(0, 2 * math.pi)
            r = math.sqrt(1 - z * z)
            inner_layer = random.random() < 0.38
            dirs.append((r * math.cos(a), r * math.sin(a),
                         random.uniform(0.3, 0.95) if rays else
                         (random.uniform(0.42, 0.58) if inner_layer else random.uniform(0.92, 1.05)),
                         random.choice(rin if inner_layer else rout), bool(rays)))
        sparks = [(dx * s * v0, dy * s * v0, random.uniform(lo, hi), rp, short)
                  for dx, dy, s, rp, short in dirs]
        sparks.sort(key=lambda p: -p[2])  # dead sparks are always a suffix
        self.sparks, self.n = sparks, len(sparks)
        self.vmax = v0 * 1.05
        self.life = hi
        self.max_trail = 34 if kind == "willow" else 18

    def ab(self, t):
        e = math.exp(-self.k * t)
        a = (1 - e) / self.k
        return a, self.g * (t - a) / self.k

    def pos(self, spark, t):
        a, b = self.ab(t)
        return self.x + spark[0] * a, self.y + spark[1] * a + b

    def step(self, dt):
        """Advance; returns sparks that died this step."""
        self.t += dt
        sp, n, died = self.sparks, self.n, []
        while n and sp[n - 1][2] <= self.t:
            n -= 1
            died.append(sp[n])
        self.n = n
        return died

    def draw(self, bits, colors, lums, w, h, heads):
        """Rasterise each spark's trail from tail to head into the braille buffers; a cell
        keeps the colour of its brightest dot."""
        t, tau = self.t, self.tau
        a1, b1 = self.ab(t)
        for _ in range(3):  # shorten the time window until the longest trail fits max_trail px
            a0, b0 = self.ab(max(0.0, t - tau))
            length = self.vmax * (a1 - a0) + b1 - b0
            if length <= self.max_trail:
                break
            tau *= self.max_trail / length
        n = max(1, min(TRAIL_SAMPLES, int(length) + 1))
        samples = []
        for j in range(n):
            back = (n - 1 - j) / (n - 1) if n > 1 else 0.0
            a, b = self.ab(max(0.0, t - tau * back))
            samples.append((a, self.y + b, int(self.fade * back)))
        head = samples[-1:]
        x0, top = self.x, LEVELS - 1
        for vx, vy, life, rp, short in self.sparks[:self.n]:
            base = int(t / life * top)
            for a, yb, off in head if short else samples:
                x, y = int(x0 + vx * a), int(yb + vy * a)
                if 0 <= x < w and 0 <= y < h:
                    cy, cx = y >> 2, x >> 1
                    bits[cy][cx] |= _BITS[y & 3][x & 1]
                    k = base + off
                    lum, col = rp[k if k < top else top]
                    row = lums[cy]
                    if lum >= row[cx]:
                        row[cx] = lum
                        colors[cy][cx] = col
        if t < 0.3:
            # white-hot core, cooling into the outer hue as it shrinks
            lum, col = self.core[int(t / 0.3 * 5)]
            r = 2.5 + self.radius * 0.08 * (1 - t / 0.3)
            for dy in range(-int(r), int(r) + 1):
                for dx in range(-int(r), int(r) + 1):
                    x, y = int(x0 + dx), int(self.y + dy)
                    if dx * dx + dy * dy <= r * r and 0 <= x < w and 0 <= y < h:
                        cy, cx = y >> 2, x >> 1
                        bits[cy][cx] |= _BITS[y & 3][x & 1]
                        lums[cy][cx] = lum
                        colors[cy][cx] = col
        # a few sparks get a full-cell head once clear of the core, while still hot
        if 0.15 < t < 0.5 * self.life:
            a, yb, _ = samples[-1]
            for vx, vy, life, rp, short in self.sparks[:self.n:13]:
                k = int(t / life * top)
                if k < 5 and not short:
                    heads.append((int(x0 + vx * a) >> 1, int(yb + vy * a) >> 2,
                                  "+" if k < 2 else "·", rp[k][1]))

    def glow(self, acc, cw, ch):
        """Soft halo around the core, fading out over the first second."""
        if self.t >= 1.0:
            return
        fade = 0.34 * self.bright * (1 - self.t) ** 2
        rx, ry = max(2.0, self.radius * 0.3), max(1.0, self.radius * 0.15)
        cx, cy = self.x / 2, self.y / 4
        for y in range(max(0, int(cy - ry)), min(ch, int(cy + ry) + 1)):
            for x in range(max(0, int(cx - rx)), min(cw, int(cx + rx) + 1)):
                d = ((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2
                if d < 1:
                    k = fade * (1 - d) ** 2
                    v = acc.get((x, y))
                    if v is None:
                        acc[(x, y)] = [c * k for c in self.glow_rgb]
                    else:
                        for i in range(3):
                            v[i] += self.glow_rgb[i] * k

    def reflection(self):
        """(centre col, half width, colour) for the water, or None once it is dim."""
        f = self.t / self.life
        if f >= 0.9 or not self.n:
            return None
        lum, col = self.sparks[0][3][int(f * (LEVELS - 1))]
        return int(self.x / 2), int(self.radius * (0.3 + min(1.0, self.t * 2)) / 2), lum, col


class Rocket:
    def __init__(self, w, h, top, speed=1.0):
        self.x = random.uniform(w * 0.1, w * 0.9)
        self.y = float(top * 4)
        self.vx = random.uniform(-12, 12)
        self.vy = -random.uniform(72, 104) * speed
        self.kind = random.choice(KINDS)
        # near shells span ~45% of the sky's height; distant ones are smaller and dimmer
        self.size = random.uniform(0.8, 1.1) if random.random() < 0.4 else random.uniform(0.4, 0.65)
        sky = top * 4
        self.radius = max(8.0, min(sky * 0.23 * self.size, w * 0.22))
        self.target = random.uniform(min(self.radius * 0.9, sky * 0.5), sky * 0.55)
        self.hist = []


def scenery(w, h, truecolor):
    """Static backdrop for a w x h canvas, every cell with an explicit background so the
    terminal's own theme never shows through. Returns a dict: rows (sky and water cells),
    sky (skyline (y, x, cell) drawn over the sparks), roofs and windows ((y, x) the bursts
    light up), top (first water row, h when too short for water), ripples (per water row,
    where reflections glint), bg (sky background per row) and water (its background)."""
    rng = random.Random(w * 7919 + h)
    water = h // 9 if h >= 16 else 0
    top = h - water
    if truecolor:
        bg = [tuple(int(a + (b - a) * y / max(1, top - 1)) & ~1 for a, b in zip(SKY_TOP, SKY_LOW))
              for y in range(top)]
        wbg = WATER
    else:
        bg, wbg = [234] * top, 233
    rows = [[("·", GRID, bg[y]) if y % 2 and (x + y) % 6 == 1 else (" ", None, bg[y])
             for x in range(w)] for y in range(top)]
    rows += [[("-", RIPPLE, wbg) if rng.random() < 0.05 else (" ", None, wbg) for x in range(w)]
             for y in range(top, h)]
    ripples = [[rng.random() < 0.4 for _ in range(w)] for _ in range(water)]
    sky, roofs, windows = [], [], []
    if water:
        maxh, x = max(2, h // 8), 0
        while x < w:
            bw = rng.randint(3, 9)
            bh = rng.randint(1, maxh) + (2 if rng.random() < 0.12 else 0)
            for xx in range(x, min(w, x + bw)):
                for y in range(top - bh, top):
                    if rng.random() < 0.04 and y < top - 1:
                        windows.append((y, xx))
                        sky.append((y, xx, (".", WINDOW, BUILDING)))
                    else:
                        sky.append((y, xx, (" ", None, BUILDING)))
                roofs.append((top - bh, xx))
                if bh > 2 and rng.random() < 0.5:
                    sky.append((top - bh - 1, xx, ("▄", BUILDING, bg[top - bh - 1])))
            x += bw
    return dict(rows=rows, sky=sky, roofs=roofs, windows=windows, top=top, ripples=ripples,
                bg=bg, water=wbg)


def main():
    parser = term.make_parser(__doc__.splitlines()[0])
    parser.add_argument("--seed", type=int, default=None, help="random seed")
    parser.add_argument("--finale", action="store_true", help="play a ~6s finale and exit")
    parser.add_argument("--banner", help="headline shown over the finale")
    parser.add_argument("--note", help="smaller line under the banner")
    parser.add_argument("--hold", action="store_true", help="after the finale, wait for a key")
    args = parser.parse_args()
    if args.seed is not None:
        random.seed(args.seed)
    dt = 1 / max(1.0, args.fps)
    rockets, shells, glints = [], [], []
    state = {"t": 0.0, "code": 0, "key": None}
    # term.run only reads keys when it owns a tty; without one a hold could never end.
    hold = args.hold and sys.stdin.isatty() and term.FOCUS_PAUSE
    banner = [(args.banner, 226)] if args.banner else []
    if banner and args.note:
        banner.append((args.note, 250))
    trail = ramp((255, 150, 50), 0.9)
    glow_on = term.COLOR and term.TRUECOLOR

    def step(c, frame):
        state["t"] += dt
        t = state["t"]
        if state["key"] != (c.w, c.h):
            state["key"], state["scene"] = (c.w, c.h), scenery(c.w, c.h, glow_on)
        scene = state["scene"]
        top = scene["top"]
        holding = False
        if args.finale and t > FINALE_SECONDS:
            if not hold:
                return True
            keys = term.take_input()
            if keys:
                state["code"] = QUIT_CODE if keys[:1] in (b"q", b"Q") else 0
                return True
            holding = True
        if holding:
            if random.random() < 0.8 * dt:
                rockets.append(Rocket(c.w * 2, c.h * 4, top))
        elif args.finale:
            # ramps up toward a wall of bursts; launches peak early enough to burst before the end
            rate = 1.5 + 10 * min(1.0, t / (FINALE_SECONDS - 1.2)) ** 2
            for _ in range(int(rate * dt) + (random.random() < rate * dt % 1)):
                rockets.append(Rocket(c.w * 2, c.h * 4, top, 1.3))
        elif random.random() < 1.3 * dt or (frame == 0):
            rockets.append(Rocket(c.w * 2, c.h * 4, top))

        c.cells = [r[:] for r in scene["rows"]]
        w, h = c.w * 2, top * 4  # sparks stop at the waterline
        b = braille.Braille(c.w, c.h)
        lums = [[0] * c.w for _ in range(c.h)]
        live, burst = sum(s.n for s in shells), False
        for r in rockets[:]:
            r.vy += GRAVITY * 0.35 * dt
            r.x += r.vx * dt
            r.y += r.vy * dt
            r.hist = (r.hist + [(r.x, r.y)])[-8:]
            # one burst per frame spreads the cost of building shells
            if (r.y <= r.target or r.vy >= 0) and not burst:
                burst = True
                rockets.remove(r)
                s = Shell(r.x, r.y, r.kind, r.radius, r.size, MAX_SPARKS - live)
                shells.append(s)
                live += s.n
                audio.sfx("boom")
                continue
            for i, (x, y) in enumerate(r.hist):
                col = trail[2 * (len(r.hist) - 1 - i)][1]
                b.dot(x + random.uniform(-0.6, 0.6), y, col)
            b.dot(r.x, r.y, WHITE)

        heads, glow, popped = [], {}, False
        for s in shells[:]:
            for p in s.step(dt):
                if s.kind == "crackle" and len(glints) < MAX_GLINTS and random.random() < 0.3:
                    x, y = s.pos(p, s.t)
                    glints.append([x / 2, y / 4, 0.0, random.uniform(0.25, 0.5), p[3]])
                    popped = True
            if not s.n:
                shells.remove(s)
                continue
            s.draw(b.bits, b.colors, lums, w, h, heads)
            if glow_on:
                s.glow(glow, c.w, c.h)
            if s.kind != "crackle" and 0.3 * s.life < s.t and len(glints) < MAX_GLINTS \
                    and random.random() < 5 * s.size * dt:
                p = s.sparks[random.randrange(s.n)]
                x, y = s.pos(p, s.t)
                glints.append([x / 2, y / 4, 0.0, random.uniform(0.4, 0.8), p[3]])
        if popped:
            audio.sfx("crackle", 0.6)

        cells = c.cells
        for (x, y), (r, g, bl) in glow.items():
            ch, fg, back = cells[y][x]
            if back.__class__ is tuple:  # glow sits on the painted sky, never darker than it
                cells[y][x] = (ch, fg, (back[0] + min(96, int(r)) & ~3, back[1] + min(96, int(g)) & ~3,
                                        back[2] + min(96, int(bl)) & ~3))
        b.blit(c)
        for x, y, ch, col in heads:
            c.put(x, y, ch, col)
        for g in glints[:]:
            g[2] += dt
            f = g[2] / g[3]
            if f >= 1:
                glints.remove(g)
                continue
            c.put(g[0], g[1], TWINKLE[int(f * len(TWINKLE))], g[4][int(f * (LEVELS - 1))][1])

        for y, x, cell in scene["sky"]:
            cells[y][x] = cell
        if top < c.h:
            refl = [None] * c.w
            for s in shells:
                r = s.reflection()
                if r:
                    cx, hw, lum, col = r
                    for x in range(max(0, cx - hw), min(c.w, cx + hw + 1)):
                        if refl[x] is None or refl[x][0] < lum:
                            refl[x] = (lum, col)
            if glow_on:
                # faint burst light on the rooftops; windows catch it more strongly
                for y, x in scene["roofs"]:
                    if refl[x]:
                        cells[y][x] = (" ", None, tint(BUILDING, refl[x][1], 0.07))
                for y, x in scene["windows"]:
                    if refl[x]:
                        cells[y][x] = (".", tint(WINDOW, refl[x][1], 0.5), BUILDING)
            for r in rockets:
                x = int(r.x / 2)
                if 0 <= x < c.w:
                    refl[x] = trail[4]
            wbg = scene["water"]
            for k, y in enumerate(range(top, c.h)):
                shift = int(2 * math.sin(t * 1.3 + k * 1.9))
                mask, drift = scene["ripples"][k], int(t * 2) * (k + 1)
                fade = round(0.42 - 0.26 * k / max(1, c.h - top), 2)
                row = cells[y]
                for x in range(c.w):
                    src = refl[(x + shift) % c.w]
                    if src and mask[(x + drift) % c.w]:
                        row[x] = ("~" if (x + k) % 3 else "-", tint(WATER, src[1], fade), wbg)

        if banner:
            hint = [("any key: keep watching  ·  q: quit", 244)] if holding else []
            draw_banner(c, banner + hint)

    term.run(args, step)
    return state["code"]


if __name__ == "__main__":
    raise SystemExit(main())
