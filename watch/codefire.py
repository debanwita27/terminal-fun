#!/usr/bin/env python3
"""Source code slowly burning away into glyph flames, ash and sparks."""
import math
import os
import random
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
sys.path.insert(0, ROOT)
from fun import term  # noqa: E402

META = {"name": "codefire", "kind": "watch", "blurb": "Source code burning away into glyph flames",
        "credit": {"type": "inspired by", "who": "Andreas Gysin (@andreasgysin), Code is fire",
                   "url": "https://x.com/andreasgysin/status/2015832561839206872"}}

FLAME = ".,:;*%#@"
FIRE_COL = [52, 88, 124, 160, 196, 202, 208, 214, 220, 226, 228, 229]
ASH = ".,'"
ASH_COL = [236, 238, 240, 242, 244]
BLANK = (" ", None, None)
FLAME_MIN = 0.12   # heat at which a cell shows flame
BURN_AT = 0.30     # heat at which code is consumed


def source_files():
    out = []
    for d, dirs, files in os.walk(ROOT):
        dirs[:] = [x for x in dirs if not x.startswith(".") and x != "__pycache__"]
        out += [os.path.join(d, f) for f in files if f.endswith(".py")]
    return out


def load_page(rng, files, n):
    """n consecutive lines from a random file at a random offset, tabs expanded, ASCII only."""
    for _ in range(8):
        if not files:
            break
        try:
            with open(rng.choice(files), encoding="utf-8", errors="replace") as f:
                lines = f.read().splitlines()
        except OSError:
            continue
        if len(lines) < 5:
            continue
        a = rng.randrange(max(1, len(lines) - n + 1))
        page = [l.expandtabs(4).rstrip() for l in lines[a:a + n]]
        return ["".join(c if 32 <= ord(c) < 127 else " " for c in l) for l in page]
    return ["# no source files found"] * n


def code_color(ch):
    return 65 if ch.isalnum() or ch == "_" else 240


class Fire:
    def __init__(self, args):
        self.rng = random.Random(args.seed)
        self.files = source_files()
        self.period = max(2, int(args.fps * 1.6))
        self.size = None
        self.feed = []

    def next_line(self, w):
        if not self.feed:
            self.feed = load_page(self.rng, self.files, 40)[::-1]
        return self.feed.pop()[:w].ljust(w)

    def make_row(self, line):
        return [(c, code_color(c), None) if c != " " else BLANK for c in line]

    def layout(self, w, h):
        self.size = (w, h)
        self.feed = []
        lines = [self.next_line(w) for _ in range(h)][::-1]
        self.lines = [list(l) for l in lines]
        self.base = [self.make_row(l) for l in lines]
        self.cons = [[0] * w for _ in range(h)]   # 0 intact, >0 ash timer, -1 gone
        flame_h = max(3.0, h * 0.38)
        self.zn = min(h, int(flame_h * 1.05) + 1)
        self.decay = FLAME_MIN ** (1 / flame_h)
        self.heat = [[0.0] * (w + 2) for _ in range(self.zn)]
        self.sparks = []

    def scroll(self, w):
        line = self.next_line(w)
        self.lines.pop()
        self.lines.insert(0, list(line))
        self.base.pop()
        self.base.insert(0, self.make_row(line))
        self.cons.pop()
        self.cons.insert(0, [0] * w)

    def step(self, cv, frame):
        w, h = cv.w, cv.h
        if self.size != (w, h):
            self.layout(w, h)
        if frame and frame % self.period == 0:
            self.scroll(w)
        rnd = self.rng.random
        heat, zn, decay = self.heat, self.zn, self.decay

        t = frame * 0.06
        seed = [0.5 + 0.3 * (math.sin(x * 0.9 + t * 5) * math.sin(x * 0.37 - t * 3.1) + math.sin(x * 0.23 + t * 1.7))
                + (rnd() - 0.5) * 0.3 for x in range(w)]
        last = heat[zn - 1]
        heat[zn - 1] = [0.0] + [o * 0.5 + s * 0.5 for o, s in zip(last[1:-1], seed)] + [0.0]
        k = 0.55 * decay / 3
        for r in range(zn - 1):
            b = heat[r + 1]
            heat[r] = [0.0] + [o * 0.45 + (p + q + s) * k + (rnd() - 0.5) * 0.05
                               for o, p, q, s in zip(heat[r][1:-1], b, b[1:], b[2:])] + [0.0]

        ash_life = max(6, int(self.period * 0.9))
        for r in range(h):
            cv.cells[r] = self.base[r][:]
        for r in range(zn):
            y = h - zn + r
            row, base, cons, chars, hr = cv.cells[y], self.base[y], self.cons[y], self.lines[y], heat[r]
            for x in range(w):
                hv = hr[x + 1]
                c = cons[x]
                if hv > BURN_AT and c == 0 and chars[x] != " " and rnd() < 0.5:
                    c = cons[x] = ash_life + int(rnd() * ash_life)
                    base[x] = BLANK
                if hv >= FLAME_MIN:
                    row[x] = (FLAME[min(7, int((hv - FLAME_MIN) * 8.5))], FIRE_COL[min(11, int(hv * 11))], None)
                elif c > 0:
                    cons[x] = c - 1 or -1
                    row[x] = (ASH[(x + y) % 3], ASH_COL[min(4, c * 5 // (2 * ash_life))], None)
                elif hv > 0.04 and c == 0 and chars[x] != " ":
                    row[x] = (chars[x], 130 if hv > 0.08 else 94, None)

        top = h - zn
        if rnd() < 0.35 and zn > 2:
            self.sparks.append([rnd() * w, top + rnd() * zn * 0.6, 0.2 + rnd() * 0.5, (rnd() - 0.5) * 0.5,
                                int(self.period * (0.6 + rnd()))])
        live = []
        for s in self.sparks:
            s[0] += s[3] + (rnd() - 0.5) * 0.4
            s[1] -= s[2]
            s[4] -= 1
            if s[4] > 0 and s[1] >= 0:
                live.append(s)
                col = 220 if s[4] > 6 else (208 if s[4] > 3 else 130)
                cv.put(s[0], s[1], "*" if s[4] > 6 else ".", col)
        self.sparks = live


def main():
    p = term.make_parser("source code burning away into glyph flames", fps=12)
    p.add_argument("--seed", type=int, default=None, help="random seed")
    args = p.parse_args()
    return term.run(args, Fire(args).step, music="codefire")


if __name__ == "__main__":
    sys.exit(main())
