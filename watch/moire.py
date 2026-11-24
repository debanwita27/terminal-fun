#!/usr/bin/env python3
"""Two glyph ring fields drifting through each other."""
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
from fun import term  # noqa: E402

META = {"name": "moire", "kind": "watch", "blurb": "Two glyph ring fields drifting through each other",
        "credit": [{"type": "inspired by", "who": "Andreas Gysin (@andreasgysin), Moiré Explorer",
                    "url": "https://x.com/andreasgysin/status/2007755844981813567"},
                   {"type": "inspired by", "who": "Sonya Rapoport (via Gysin's Moiré Explorer)",
                    "url": "https://x.com/andreasgysin/status/2007755844981813567"}]}

GLYPHS = " .·:-=+*oO#%@"
LEVELS = 26
TAU = 2 * math.pi
HOLD = (20.0, 30.0)   # seconds a pattern type stays before the next transition
FADE = 6.0
KINDS = ("rings", "lines", "spirals")
# Dark, mid, light anchors (RGB) per palette.
PALETTES = [
    ((10, 14, 48), (40, 120, 200), (235, 245, 255)),
    ((44, 8, 40), (220, 70, 110), (255, 226, 190)),
    ((6, 36, 34), (60, 170, 140), (230, 250, 220)),
    ((30, 20, 10), (200, 130, 40), (255, 240, 200)),
]
sin, cos, hypot, atan2 = math.sin, math.cos, math.hypot, math.atan2


def to256(r, g, b):
    if abs(r - g) < 8 and abs(g - b) < 8:
        v = (r + g + b) // 3
        return 16 if v < 5 else 231 if v > 246 else 232 + (v - 8) * 24 // 240
    return 16 + 36 * round(r / 255 * 5) + 6 * round(g / 255 * 5) + round(b / 255 * 5)


def ramp(pa, pb, m):
    """LEVELS colours from dark to light, blending palette pa into pb by m."""
    out = []
    for i in range(LEVELS):
        f = i / (LEVELS - 1)
        c = []
        for ch in range(3):
            vals = []
            for pal in (pa, pb):
                lo, mid, hi = pal[0][ch], pal[1][ch], pal[2][ch]
                vals.append(lo + (mid - lo) * f * 2 if f < 0.5 else mid + (hi - mid) * (f - 0.5) * 2)
            c.append(int(vals[0] + (vals[1] - vals[0]) * m))
        out.append(to256(*c))
    return out


def smooth(m):
    return m * m * (3 - 2 * m)


def phases(kind, xs, ys, cx, cy, k, ang, arms):
    """Per-cell phase of one pattern centred at (cx, cy)."""
    if kind == "rings":
        return [k * hypot(x - cx, y - cy) for x, y in zip(xs, ys)]
    if kind == "lines":
        ca, sa = cos(ang) * k, sin(ang) * k
        return [(x - cx) * ca + (y - cy) * sa for x, y in zip(xs, ys)]
    # Integer arm count keeps the phase continuous across atan2's branch cut.
    return [k * hypot(x - cx, y - cy) + arms * atan2(y - cy, x - cx) for x, y in zip(xs, ys)]


def main():
    p = term.make_parser("Two glyph ring fields drifting through each other", fps=12)
    p.add_argument("--speed", type=float, default=1.0, help="time multiplier (default 1)")
    p.add_argument("--seed", type=int, default=None, help="random seed")
    args = p.parse_args()
    rng = random.Random(args.seed)
    ph = [rng.uniform(0, TAU) for _ in range(12)]
    st = {"size": None, "xs": None, "ys": None, "kind": 0, "next": rng.uniform(*HOLD), "from": 0, "t0": -99.0,
          "pal": 0, "pal_t0": -99.0, "pal_next": 15.0, "palfrom": 0}

    def step(cv, frame):
        w, h = cv.w, cv.h
        t = frame / 12 * args.speed
        if st["size"] != (w, h):
            st["size"] = (w, h)
            # Units are terminal rows: a cell is half as wide as it is tall.
            st["xs"] = [x * 0.5 for _ in range(h) for x in range(w)]
            st["ys"] = [float(y) for y in range(h) for _ in range(w)]
        xs, ys = st["xs"], st["ys"]
        W, H = w * 0.5, float(h)

        if t >= st["next"]:
            st["from"], st["kind"] = st["kind"], rng.choice([i for i in range(3) if i != st["kind"]])
            st["t0"] = t
            st["next"] = t + FADE + rng.uniform(*HOLD)
        if t >= st["pal_next"]:
            st["palfrom"], st["pal"] = st["pal"], rng.choice([i for i in range(len(PALETTES)) if i != st["pal"]])
            st["pal_t0"] = t
            st["pal_next"] = t + rng.uniform(25, 40)

        k = 1.5 + 0.45 * sin(t * 0.09 + ph[0])
        ang = t * 0.03 + ph[1]
        amp = 0.32
        cs = []
        for i in range(3):
            j = 2 + i * 3
            cs.append((W / 2 + W * amp * sin(t * (0.11 + 0.03 * i) + ph[j]) * (1 + 0.3 * sin(t * 0.05 + ph[j + 1])),
                       H / 2 + H * 0.4 * sin(t * (0.09 + 0.04 * i) * 1.3 + ph[j + 2])))
        w3 = max(0.0, sin(t * 0.06 + ph[11]) * 1.4)
        w3 = min(1.0, w3)

        m = smooth(min(1.0, (t - st["t0"]) / FADE))
        kinds = [KINDS[st["kind"]]] if m >= 1 else [KINDS[st["from"]], KINDS[st["kind"]]]
        angs = (ang, ang + 0.35 + 0.25 * sin(t * 0.07 + ph[10]), ang + 1.1)
        arms = (3, -2, 4)
        fields = []
        for i in range(3 if w3 > 0.02 else 2):
            cx, cy = cs[i]
            if len(kinds) == 1:
                f = phases(kinds[0], xs, ys, cx, cy, k, angs[i], arms[i])
            else:
                fa = phases(kinds[0], xs, ys, cx, cy, k, angs[i], arms[i])
                fb = phases(kinds[1], xs, ys, cx, cy, k, angs[i], arms[i])
                f = [a + (b - a) * m for a, b in zip(fa, fb)]
            fields.append(f)

        if len(fields) == 3:
            v = [sin(a) + sin(b) + w3 * sin(c) for a, b, c in zip(*fields)]
            span = 4 + 2 * w3
        else:
            v = [sin(a) + sin(b) for a, b in zip(*fields)]
            span = 4.0
        q = (LEVELS - 0.001) / span
        off = span / 2

        pm = smooth(min(1.0, (t - st["pal_t0"]) / 12))
        cols = ramp(PALETTES[st["palfrom"]], PALETTES[st["pal"]], pm)
        gl = len(GLYPHS) - 1
        lut = [(GLYPHS[i * gl // (LEVELS - 1)], cols[i], None) for i in range(LEVELS)]
        cells = cv.cells
        for y in range(h):
            row = v[y * w:(y + 1) * w]
            cells[y] = [lut[int((a + off) * q)] for a in row]

    return term.run(args, step, music="moire")


if __name__ == "__main__":
    sys.exit(main())
