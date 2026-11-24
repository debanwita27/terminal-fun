#!/usr/bin/env python3
"""Amber CRT source code that slowly smears and melts down the screen, then types itself back."""
import math
import os
import random
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
sys.path.insert(0, ROOT)
from fun import term  # noqa: E402

META = {"name": "meltdown", "kind": "watch", "blurb": "Amber source code slowly smearing and melting down the screen",
        "credit": {"type": "inspired by", "who": "Andreas Gysin (@andreasgysin), Meltdown",
                   "url": "https://x.com/andreasgysin/status/2025601644826628115"}}

BG = 52
HEAD = 223
# Smear glyph and colour per fade stage, with each stage's length in seconds.
TRAIL = [("|", 208, 0.5), (":", 172, 0.7), (".", 130, 0.9), ("'", 94, 1.2)]
BRIGHT = {214: 221, 208: 214, 172: 208, 130: 172, 94: 130}
BLANK = (" ", None, BG)
INTACT, HEADING, TRAILING = 0, 1, 2


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


def amber(ch):
    if ch.isalpha() or ch == "_":
        return 214
    return 208 if ch.isdigit() else 172


class Melt:
    def __init__(self, args):
        self.rng = random.Random(args.seed)
        self.files = source_files()
        self.fps = args.fps
        self.size = None
        self.stage_len = [max(1, int(s * args.fps)) for _, _, s in TRAIL]

    def layout(self, w, h):
        self.size = (w, h)
        self.cur = [[BLANK] * w for _ in range(h)]
        self.st = [[INTACT] * w for _ in range(h)]
        self.born = [[-1] * w for _ in range(h)]
        self.sched = {}
        self.drips = []
        self.waves = []
        self.start_typing()

    def start_typing(self):
        h = self.size[1]
        for x, yf, _, _, _ in self.drips:
            self.leave_trail(x, int(yf), self.frame)
        self.drips = []
        self.waves = []
        self.page = load_page(self.rng, self.files, h)
        self.phase = "type"
        self.row = self.col = 0
        self.total = 0

    def leave_trail(self, x, y, f):
        g, c, _ = TRAIL[0]
        self.cur[y][x] = (g if self.rng.random() < 0.7 else ":", c, BG)
        self.st[y][x] = TRAILING
        self.born[y][x] = f
        at = f
        for s in range(1, len(TRAIL) + 1):
            at += self.stage_len[s - 1]
            self.sched.setdefault(at, []).append((x, y, f, s))

    def fade(self, f):
        for x, y, born, s in self.sched.pop(f, ()):
            if self.born[y][x] != born or self.st[y][x] != TRAILING:
                continue
            if s < len(TRAIL):
                self.cur[y][x] = (TRAIL[s][0], TRAIL[s][1], BG)
            else:
                self.cur[y][x] = BLANK
                self.st[y][x] = INTACT

    def type_chars(self, budget):
        w, h = self.size
        while budget > 0 and self.row < h:
            line = self.page[self.row]
            y = self.row
            if self.col == 0:
                self.cur[y] = [BLANK] * w
                self.st[y] = [INTACT] * w
                self.born[y] = [-1] * w
            if self.col < min(len(line), w):
                ch = line[self.col]
                if ch != " ":
                    self.cur[y][self.col] = (ch, amber(ch), BG)
                    self.total += 1
                self.col += 1
                budget -= 1
            else:
                self.row += 1
                self.col = 0
                budget -= 3
        return self.row >= h

    def start_drip(self, x, y):
        ch = self.cur[y][x][0]
        self.cur[y][x] = (ch, HEAD, BG)
        self.st[y][x] = HEADING
        self.intact -= 1
        rnd = self.rng.random
        self.drips.append([x, float(y), 0.08 + rnd() * 0.3, 3 + int(rnd() * 12), ch])

    def move_drips(self, f):
        w, h = self.size
        live = []
        for d in self.drips:
            x, yf, sp, left, ch = d
            yo = int(yf)
            d[1] = yf + sp
            yn = int(d[1])
            if yn == yo:
                live.append(d)
                continue
            self.leave_trail(x, yo, f)
            if yn >= h or left <= 1 or self.st[yn][x] == HEADING:
                continue
            if self.st[yn][x] == INTACT and self.cur[yn][x][0] != " ":
                self.intact -= 1
            self.cur[yn][x] = (ch, HEAD, BG)
            self.st[yn][x] = HEADING
            d[3] = left - 1
            live.append(d)
        self.drips = live

    def melt(self, f):
        w, h = self.size
        rnd = self.rng.random
        if not self.waves or (f - self.wave_t > self.fps * 3.5 and len(self.waves) < 4):
            self.waves.append([self.rng.randrange(w), self.rng.randrange(h), 0.0])
            self.wave_t = f
        for wv in self.waves:
            wv[2] += 0.55
        st, cur = self.st, self.cur
        for _ in range(max(4, int(w * h * 0.008))):
            x, y = self.rng.randrange(w), self.rng.randrange(h)
            if st[y][x] != INTACT or cur[y][x][0] == " ":
                continue
            for ox, oy, r in self.waves:
                d = math.hypot((x - ox) * 0.5, y - oy)
                if d < r and (r - d < 14 or rnd() < 0.1):
                    self.start_drip(x, y)
                    break

    def step(self, cv, f):
        w, h = cv.w, cv.h
        self.frame = f
        if self.size != (w, h):
            self.layout(w, h)
        self.fade(f)
        self.move_drips(f)
        cursor = None
        if self.phase == "type":
            if self.type_chars(max(8, int(w * 0.7))):
                self.intact = self.total
                self.phase, self.until = "read", f + int(self.fps * 6)
            else:
                cursor = (self.col, self.row)
        elif self.phase == "read":
            if f >= self.until:
                self.phase, self.limit, self.wave_t = "melt", f + int(self.fps * 45), f
        else:
            self.melt(f)
            if self.intact < self.total * 0.2 or f > self.limit:
                self.start_typing()

        for y in range(h):
            cv.cells[y] = self.cur[y][:]
        for y in ((f // 2) % (h + 8) - 4, (f // 2) % (h + 8) - 3):
            if 0 <= y < h:
                cv.cells[y] = [(ch, BRIGHT.get(c, c), b) for ch, c, b in cv.cells[y]]
        if cursor:
            cv.put(cursor[0], cursor[1], "█", 214, BG)


def main():
    p = term.make_parser("amber source code slowly melting down the screen", fps=12)
    p.add_argument("--seed", type=int, default=None, help="random seed")
    args = p.parse_args()
    return term.run(args, Melt(args).step, music="meltdown")


if __name__ == "__main__":
    sys.exit(main())
