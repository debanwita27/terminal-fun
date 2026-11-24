#!/usr/bin/env python3
"""Ducklings: mama duck herds lost ducklings home to the nest.

Usage: python3 ducklings.py [--fps 20] [--frames N] [--seed S]
Arrows/WASD swim mama; she only moves while a key is held. Without a tty an
autopilot plays (for smoke tests).
"""

META = {"name": "ducklings", "kind": "play", "blurb": "Herd lost ducklings home to the nest past a fox and a hawk",
        "credit": None}

import math
import os
import random
import textwrap
import types

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

from fun import audio, term, game

NAME = "ducklings"
MIN_W, MIN_H = 44, 14
ROUND = 90.0
GAP = 3          # history samples between neighbours in the trailing line
HOLD = 0.15      # seconds a key press keeps mama swimming (terminals send no key-up)
SPX, SPY = 18.0, 9.0   # cells per second; rows are about twice as tall as columns
MSG_SMALL = "make the terminal bigger"
DIRS = ("left", "right", "up", "down")
PAD = (7, 2)     # obstacle footprints in cells (w, h)
REED = (3, 2)
NEST_W, NEST_H = 9, 2


def mix(a, b, k):
    """Lerp two rgb tuples; k is clamped to 0..1."""
    k = 0.0 if k < 0 else 1.0 if k > 1 else k
    return (int(a[0] + (b[0] - a[0]) * k + .5), int(a[1] + (b[1] - a[1]) * k + .5),
            int(a[2] + (b[2] - a[2]) * k + .5))


def sprite(rows, pal, flip=False, sink=0):
    """Pixel rows (two per cell row, "." transparent) -> [(dx, dy, ch, fg, bg)] half-block cells.

    bg None keeps the scene behind. flip mirrors left-right; sink drops the sprite that many
    pixels, losing its bottom rows under the waterline."""
    w = len(rows[0])
    assert all(len(r) == w for r in rows) and len(rows) % 2 == 0, rows
    if flip:
        rows = [r[::-1] for r in rows]
    if sink:
        rows = ["." * w] * sink + rows[:-sink]
    out = []
    for cy in range(0, len(rows), 2):
        for x in range(w):
            t, b = pal.get(rows[cy][x]), pal.get(rows[cy + 1][x])
            if t is None and b is None:
                continue
            if t is None:
                out.append((x, cy // 2, "▄", b, None))
            elif b is None or t != b:
                out.append((x, cy // 2, "▀", t, b))
            else:
                out.append((x, cy // 2, " ", None, t))
    return out


# Mama: a plump white duck facing right; eye is 2x2 with a shine pixel.
MAMA_PAL = {"W": (250, 248, 240), "C": (224, 218, 204), "S": (188, 186, 184), "O": (255, 166, 46),
            "o": (224, 118, 36), "D": (36, 30, 46), "w": (255, 255, 255), "K": (255, 168, 170)}
_HEAD = ["..........WWW...",
         ".........WWWWW..",
         "W.......WWWwDWW.",
         "WW....WWWWWDDWOO"]
_BODY = ["WWWWWWWWWWKKWWoo",
         "WWWCCCWWWWWWWW..",
         ".WWWCCCWWWWWWC..",
         "..SSSSSSSSSSS..."]
MAMA_ART = {
    "idle": _HEAD + _BODY,
    "blink": _HEAD[:2] + ["W.......WWWWWWW.", "WW....WWWWWDDWOO"] + _BODY,
    "happy": _HEAD[:2] + ["W.......WWWWDWW.", "WW....WWWWWDWDOO"] + _BODY,
}
MAMA_AX = 8  # sprite column over mama's x when facing right
# Duckling: fluffy yellow, facing right.
DUCK_PAL = {"Y": (255, 214, 64), "y": (234, 168, 42), "h": (255, 244, 176), "O": (255, 136, 36),
            "D": (40, 30, 30)}
DUCK_ART = ["....hYY.",
            "...YYYDO",
            "Y..YYYYo",
            "YYYYYYY.",
            ".YyyYYY.",
            "..yyyy.."]
DUCK_AX = 4
# Fox: side view, bushy white-tipped tail; poses per mode.
FOX_PAL = {"F": (240, 122, 40), "f": (196, 84, 30), "W": (252, 246, 236), "K": (48, 28, 28),
           "D": (24, 16, 16)}
FOX_ART = {
    "a": ["..........K.K.",
          "WW........FFF.",
          "WFFF.....FFDFF",
          ".fFFFFFFFFWWFK",
          "..fFFFFFFFWW..",
          "...K.K..K.K..."],
    "b": ["..........K.K.",
          "WW........FFF.",
          "WFFF.....FFDFF",
          ".fFFFFFFFFWWFK",
          "..fFFFFFFFWW..",
          "..K...K.K...K."],
    "stalk": ["..............",
              "..........K.K.",
              "WW.......FFDFF",
              "WFFFFFFFFFWWFK",
              ".fFFFFFFFFWW..",
              "..KK.KK.KK.KK."],
    "pounce": ["...........K.K",
               "WWW........FFF",
               "..FFFFFFFFFFDF",
               "...fFFFFFFFWWK",
               ".KK.........KK",
               ".............."],
}
FOX_AX = 9
# Hawk seen from above, head toward travel (right); two wingbeat frames.
HAWK_PAL = {"H": (66, 50, 48), "h": (112, 84, 68), "B": (240, 190, 60), "T": (92, 64, 52),
            "o": (196, 172, 160)}
HAWK_ART = {
    "a": ["HH.......",
          ".HHH.....",
          "..HHH....",
          "..HHhH...",
          "TTHHHHHHB",
          "TTHHHHHH.",
          "..HHhH...",
          "..HHH....",
          ".HHH.....",
          "HH......."],
    "b": ["....HH...",
          "...HHH...",
          "...HhH...",
          "..HHhH...",
          "TTHHHHHHB",
          "TTHHHHHH.",
          "..HHhH...",
          "...HhH...",
          "...HHH...",
          "....HH..."],
}
# Lily pad: lit rim, a notch, a darker underside.
PAD_PAL = {"L": (140, 206, 112), "G": (70, 150, 84), "g": (48, 116, 70), "D": (34, 88, 60)}
PAD_ART = [".LLLLL.",
           "LGGGGGL",
           "GGg.gGG",
           ".DD.DD."]
LOTUS = (252, 156, 200)
# Nest: woven straw, three cell rows from the row above the blocked footprint.
NEST_PAL = {"s": (168, 120, 64), "S": (220, 174, 96), "L": (246, 214, 140), "d": (92, 60, 34),
            "Y": (255, 214, 64), "h": (255, 244, 176)}
NEST_ART = [".............",
             ".............",
             "...sLLLLLLs..",
             ".sSLdddddLSs.",
             "sSLsLsLsLsLSs",
             "SLsSLsLsLsSLS",
             ".sSLsLsLsLSs.",
             "...sSSSSSSs.."]
NEST_SLOTS = (2, 4, 6, 8)  # art columns of the tucked-in ducklings' heads
CATTAIL = ((156, 100, 58), (100, 60, 36))  # (lit side, shade)
REED_STEM = (70, 120, 64)

# The scene drifts from golden afternoon to dusk as the round's clock runs down.
DAY = dict(wtop=(110, 190, 196), wdeep=(34, 96, 138), hl=(238, 252, 240), sun=(255, 244, 200),
           grass=(96, 156, 70), grassdk=(66, 124, 58), blade=(156, 206, 106), shore=(196, 180, 124),
           panel=(20, 44, 54), fly=0.0)
GOLD = dict(wtop=(206, 178, 140), wdeep=(52, 84, 128), hl=(255, 236, 200), sun=(255, 226, 150),
            grass=(108, 140, 62), grassdk=(76, 108, 54), blade=(178, 190, 100), shore=(204, 168, 110),
            panel=(36, 38, 56), fly=0.2)
DUSK = dict(wtop=(150, 118, 166), wdeep=(26, 30, 76), hl=(255, 196, 200), sun=(255, 200, 176),
            grass=(52, 84, 70), grassdk=(36, 60, 58), blade=(98, 134, 104), shore=(132, 104, 116),
            panel=(26, 22, 50), fly=1.0)
TOD_STEPS = 24
EVENING = (70, 50, 110)  # statics in the backdrop blend toward this as dusk falls
FIREFLY = (214, 255, 120)
SHADE = (8, 10, 26)
DANGER = (255, 70, 60)
WARN = (255, 130, 120)  # hawk path and shadow rim: readable on day and dusk water
GLOW = (255, 220, 120)
RIPPLE_LIFE = 1.1
CREAM, INK = (244, 238, 220), (24, 26, 34)


def palette(m):
    a, b, k = (DAY, GOLD, m * 2) if m < .5 else (GOLD, DUSK, m * 2 - 1)
    return {key: (mix(a[key], b[key], k) if isinstance(a[key], tuple) else a[key] + (b[key] - a[key]) * k)
            for key in a}


MAMA = {(p, f, s): sprite(rows, MAMA_PAL, f < 0, s) for p, rows in MAMA_ART.items()
        for f in (1, -1) for s in (0, 1)}
DUCK = {(f, s): sprite(DUCK_ART, DUCK_PAL, f < 0, s) for f in (1, -1) for s in (0, 1)}
FOX = {(p, f): sprite(rows, FOX_PAL, f < 0) for p, rows in FOX_ART.items() for f in (1, -1)}
def outlined(rows, key="o"):
    """Pad rows by one pixel and ring every opaque pixel with `key`."""
    w = len(rows[0]) + 2
    g = ["." * w] + ["." + r + "." for r in rows] + ["." * w]
    g = g + ["." * w] if len(g) % 2 else g
    out = []
    for y, r in enumerate(g):
        out.append("".join(ch if ch != "." else key if any(
            0 <= y + dy < len(g) and 0 <= x + dx < w and g[y + dy][x + dx] not in ".o"
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))) else "." for x, ch in enumerate(r)))
    return out


HAWK = {(p, f): sprite(outlined(rows), HAWK_PAL, f < 0) for p, rows in HAWK_ART.items() for f in (1, -1)}
PADSPR = sprite(PAD_ART, PAD_PAL)


def center(c, y, s, color=None, bg=None):
    c.text((c.w - len(s)) // 2, y, s, color, bg)


def blit(c, spr, x0, y0):
    cells, w, h = c.cells, c.w, c.h
    for dx, dy, ch, fg, bg in spr:
        x, y = x0 + dx, y0 + dy
        if 0 <= x < w and 0 <= y < h:
            row = cells[y]
            row[x] = (ch, fg, row[x][2] if bg is None else bg)


_tints = {}


def tint(c, x, y, col, k):
    """Blend the bg (and fg) of one scene cell toward col by k (quantised, cached)."""
    if not (0 <= x < c.w and 0 <= y < c.h):
        return
    row = c.cells[y]
    ch, fg, bg = row[x]
    if bg.__class__ is not tuple:
        return
    kq = int(k * 16 + .5)
    if kq <= 0:
        return
    key = (bg, col, kq)
    nb = _tints.get(key)
    if nb is None:
        if len(_tints) > 20000:
            _tints.clear()
        nb = _tints[key] = mix(bg, col, kq / 16)
    if fg.__class__ is tuple:
        fkey = (fg, col, kq)
        nf = _tints.get(fkey)
        if nf is None:
            nf = _tints[fkey] = mix(fg, col, kq / 16)
        fg = nf
    row[x] = (ch, fg, nb)


def main():
    parser = term.make_parser(__doc__.splitlines()[0])
    parser.add_argument("--seed", type=int, default=None, help="random seed")
    parser.add_argument("--demo", action="store_true", help="autopilot plays (default without a tty)")
    args = parser.parse_args()
    rng = random.Random(args.seed)
    dt = 1 / max(1.0, args.fps)
    demo = args.demo or not os.isatty(0)
    st = types.SimpleNamespace(mode="title", paused=False, done=False, banner=0.0,
                               best=game.best(NAME), newbest=False, size=None, over_t=0.0,
                               t=0.0, clock=0.0, base=None, ripples=[], arrive=[], hap=-9.0,
                               prev=None, moving=False, wake=0.0, layout_n=0)
    srng = random.Random(11)  # scenery only, so the gameplay rng sequence is untouched
    flies = [dict(x=srng.uniform(0, 1), y=srng.uniform(0, 1), ph=srng.uniform(0, 6.28),
                  sp=srng.uniform(.4, .9)) for _ in range(14)]

    def in_pond(x, y):
        return st.x0 <= x <= st.x1 and st.y0 <= y <= st.y1

    def blocked(x, y):
        x, y = int(round(x)), int(round(y))
        return not in_pond(x, y) or (x, y) in st.block

    def place_free(near=None, spread=0):
        for _ in range(60):
            if near:
                x, y = near[0] + rng.randint(-spread, spread), near[1] + rng.randint(-spread // 2, spread // 2)
            else:
                x, y = rng.randint(st.x0 + 1, st.x1 - 1), rng.randint(st.y0 + 1, st.y1 - 1)
            if not blocked(x, y) and (near or math.hypot(x - st.mx, 2 * (y - st.my)) > 14):
                return float(x), float(y)
        return float(st.x0 + 2), float(st.y0 + 2)

    def layout(w, h):
        st.size = (w, h)
        st.layout_n += 1
        st.x0, st.x1, st.y0, st.y1 = 2, w - 3, 3, h - 2
        nx, ny = w * 3 // 4 - NEST_W // 2, h // 2
        st.nest = (nx, ny)
        st.block, st.items = set(), []
        taken = [(nx - 3, ny - 2, NEST_W + 6, NEST_H + 4),
                 (st.x0, st.y0, 14, h - st.y0)]
        for x in range(nx, nx + NEST_W):
            for y in range(ny, ny + NEST_H):
                st.block.add((x, y))

        def free(r):
            return all(r[0] + r[2] + 1 < q[0] or q[0] + q[2] + 1 < r[0] or
                       r[1] + r[3] + 1 < q[1] or q[1] + q[3] + 1 < r[1] for q in taken)

        for kind, (sw, sh), n in (("pad", PAD, 5), ("reed", REED, 4)):
            for _ in range(n):
                for _ in range(40):
                    r = (rng.randint(st.x0 + 1, st.x1 - sw - 1),
                         rng.randint(st.y0 + 1, st.y1 - sh - 1), sw, sh)
                    if free(r):
                        taken.append(r)
                        st.items.append((kind, r[0], r[1]))
                        for dx in range(sw):
                            for dy in range(sh):
                                st.block.add((r[0] + dx, r[1] + dy))
                        break
        st.mx, st.my = float(st.x0 + 6), float((st.y0 + st.y1) // 2)
        st.hist = [(st.mx, st.my)]
        ring = (1, 2, w - 2, h - 1)
        st.ring = ring
        st.ringlen = 2 * (ring[2] - ring[0]) + 4 * (ring[3] - ring[1])

    def ring_point(s):
        x1, y1, x2, y2 = st.ring
        wd, hd = x2 - x1, y2 - y1
        s %= st.ringlen
        if s < wd:
            return x1 + s, y1
        if s < wd + 2 * hd:
            return x2, y1 + (s - wd) / 2
        if s < 2 * wd + 2 * hd:
            return x2 - (s - wd - 2 * hd), y2
        return x1, y2 - (s - 2 * wd - 2 * hd) / 2

    def nearest_ring(x, y):
        return min(range(0, st.ringlen), key=lambda s: math.hypot(ring_point(s)[0] - x,
                                                                     2 * (ring_point(s)[1] - y)))

    def reset():
        layout(*st.size)
        st.t, st.left, st.score, st.banked = 0.0, ROUND, 0, 0
        st.face = 1
        st.until = {k: 0.0 for k in DIRS}
        st.line, st.lost, st.floats = [], [], []
        st.spawn = 0.0
        st.cd = 0.0
        st.nestf = 0.0
        st.fox = dict(s=float(rng.randint(0, st.ringlen - 1)), mode="prowl", t=0.0, cool=4.0, dir=1)
        st.hawk = dict(phase="idle", t=rng.uniform(9, 14))
        st.newbest = False
        for _ in range(5):
            spawn_duck()
        st.stuck, st.wig, st.wdir, st.px_, st.py_ = 0.0, 0.0, "up", 0.0, 0.0
        st.ripples, st.arrive, st.prev = [], [], None

    def spawn_duck():
        x, y = place_free()
        st.lost.append(dict(x=x, y=y, imm=0.0, wt=rng.uniform(.3, 1.2), pp=rng.uniform(.5, 4)))

    def pop(text, x, y, col=229):
        st.floats.append(dict(txt=text, x=x, y=y, ttl=1.4, col=col))

    def fox_pos():
        return ring_point(st.fox["s"])

    def scatter(i):
        victims = st.line[i:]
        del st.line[i:]
        for d in victims:
            for _ in range(10):
                x, y = d["x"] + rng.randint(-5, 5), d["y"] + rng.randint(-2, 2)
                if not blocked(x, y):
                    d["x"], d["y"] = float(x), float(y)
                    break
            d["imm"] = 1.5
            st.lost.append(d)
        st.cd = 1.0
        audio.sfx("quack")
        pop("scattered!", d["x"] - 4, d["y"] - 2, 203)

    def hawk_shadow():
        h = st.hawk
        if h["phase"] != "sweep":
            return None
        u = h["t"] / h["dur"]
        return (h["x0"] + (h["x1"] - h["x0"]) * u, h["y0"] + (h["y1"] - h["y0"]) * u)

    def update(keys):
        w, h = st.size
        st.t += dt
        st.left -= dt
        for k in keys:
            if k in DIRS:
                st.until[k] = st.t + HOLD
        vx = (st.until["right"] > st.t) - (st.until["left"] > st.t)
        vy = (st.until["down"] > st.t) - (st.until["up"] > st.t)
        if vx:
            st.face = vx
        nx = st.mx + vx * SPX * dt
        if not blocked(nx, st.my):
            st.mx = nx
        ny = st.my + vy * SPY * dt
        if not blocked(st.mx, ny):
            st.my = ny
        lx, ly = st.hist[-1]
        if math.hypot(st.mx - lx, 2 * (st.my - ly)) >= 1:
            st.hist.append((st.mx, st.my))
            del st.hist[:-(len(st.line) + 6) * GAP]

        for i, d in enumerate(st.line):
            tx, ty = st.hist[max(0, len(st.hist) - 1 - (i + 1) * GAP)]
            d["x"] += (tx - d["x"]) * .5
            d["y"] += (ty - d["y"]) * .5
        for d in list(st.lost):
            d["imm"] = max(0.0, d["imm"] - dt)
            was = d["pp"]
            d["pp"] -= dt
            if was >= 0 > d["pp"] and d["imm"] <= 0:
                audio.sfx("peep", .3)
            if d["pp"] < -.9:
                d["pp"] = rng.uniform(2, 6)
            d["wt"] -= dt
            if d["wt"] <= 0:
                d["wt"] = rng.uniform(.5, 1.3)
                x, y = d["x"] + rng.choice((-1, 0, 1)), d["y"] + rng.choice((-1, 0, 0, 1))
                if not blocked(x, y):
                    d["x"], d["y"] = x, y
            if d["imm"] <= 0 and abs(d["x"] - st.mx) <= 2.5 and abs(d["y"] - st.my) <= 1.2:
                st.lost.remove(d)
                st.line.append(d)
                d["hop"] = st.clock
                st.hap = st.clock
                audio.sfx("duckpeep")
        st.spawn -= dt
        if st.spawn <= 0:
            st.spawn = rng.uniform(2, 3.5)
            if len(st.lost) < 7:
                spawn_duck()

        nx0, ny0 = st.nest
        if st.line and nx0 - 3 <= st.mx <= nx0 + NEST_W + 2 and ny0 - 2 <= st.my <= ny0 + NEST_H + 1:
            n = len(st.line)
            bonus = n * (n - 1) // 2
            for i, d in enumerate(st.line):
                st.arrive.append(dict(x=d.get("rx", d["x"]), y=d.get("ry", d["y"]), t0=st.clock + i * .07,
                                      slot=NEST_SLOTS[min(st.banked + i, len(NEST_SLOTS) - 1)]))
            st.banked += n
            st.score += n + bonus
            pop(f"+{n}" + (f" +{bonus} combo!" if bonus else ""), nx0, ny0 - 3, 226)
            st.line.clear()
            st.nestf = 1.2
            st.hap = st.clock
            audio.sfx("nestjingle")

        update_hazards(w, h)
        st.cd = max(0.0, st.cd - dt)
        st.nestf = max(0.0, st.nestf - dt)
        if st.cd <= 0:
            fx, fy = fox_pos()
            reach = 8 if st.fox["mode"] == "pounce" else 4
            sh = hawk_shadow()
            for i, d in enumerate(st.line):
                if math.hypot(d["x"] - fx, 2 * (d["y"] - fy)) <= reach or (
                        sh and ((d["x"] - sh[0]) / 8) ** 2 + ((d["y"] - sh[1]) / 2.5) ** 2 <= 1):
                    scatter(i)
                    break
        for f in st.floats:
            f["ttl"] -= dt
            f["y"] -= 1.5 * dt
        st.floats = [f for f in st.floats if f["ttl"] > 0]
        if st.left <= 0:
            st.mode = "over"
            audio.sfx("clear")
            st.over_t = 0.0
            st.newbest = game.record(NAME, st.score)
            st.best = max(st.best, st.score)

    def update_hazards(w, h):
        f = st.fox
        f["t"] += dt
        f["cool"] -= dt
        fx, fy = fox_pos()
        if f["mode"] == "prowl":
            target = nearest_ring(st.mx, st.my)
            diff = (target - f["s"] + st.ringlen / 2) % st.ringlen - st.ringlen / 2
            if abs(diff) > 3:
                f["dir"] = 1 if diff > 0 else -1
                f["s"] += f["dir"] * 9 * dt
            elif f["cool"] <= 0 and math.hypot(st.mx - fx, 2 * (st.my - fy)) < 18:
                f.update(mode="stalk", t=0.0)
                audio.sfx("foxsnarl")
        elif f["mode"] == "stalk" and f["t"] > .8:
            f.update(mode="pounce", t=0.0)
        elif f["mode"] == "pounce" and f["t"] > .5:
            f.update(mode="prowl", t=0.0, cool=rng.uniform(4, 7))
        k = st.hawk
        k["t"] -= dt if k["phase"] == "idle" else 0
        if k["phase"] == "idle" and k["t"] <= 0:
            side = rng.choice((-1, 1))
            k.update(phase="warn", t=0.0, side=side, y0=rng.randint(st.y0, st.y1),
                     y1=rng.randint(st.y0, st.y1))
            audio.sfx("hawkcry", .45)
        elif k["phase"] == "warn":
            k["t"] += dt
            if k["t"] > 1.6:
                x0, x1 = (-10, w + 10) if k["side"] < 0 else (w + 10, -10)
                k.update(phase="sweep", t=0.0, x0=x0, x1=x1, dur=(w + 20) / 16)
                audio.sfx("hawkcry")
        elif k["phase"] == "sweep":
            k["t"] += dt
            if k["t"] >= k["dur"]:
                k.update(phase="idle", t=rng.uniform(12, 20))

    def bot():
        if st.line and (len(st.line) >= 3 or st.left < 20 or not st.lost):
            tx, ty = st.nest[0] - 2, st.nest[1]
        elif st.lost:
            d = min(st.lost, key=lambda d: math.hypot(d["x"] - st.mx, 2 * (d["y"] - st.my)))
            tx, ty = d["x"], d["y"]
        else:
            return []
        if math.hypot(st.mx - st.px_, st.my - st.py_) < .01:
            st.stuck += dt
        else:
            st.stuck = 0.0
        st.px_, st.py_ = st.mx, st.my
        if st.stuck > .5:
            st.wig, st.wdir = .7, rng.choice(DIRS)
            st.stuck = 0.0
        if st.wig > 0:
            st.wig -= dt
            return [st.wdir]
        keys = []
        if abs(tx - st.mx) > 1:
            keys.append("right" if tx > st.mx else "left")
        if abs(ty - st.my) > .6:
            keys.append("down" if ty > st.my else "up")
        return keys

    # ------------------------------------------------------------------ drawing

    def tod():
        """Time-of-day step 0 (afternoon) .. 1 (dusk), following the round clock."""
        if st.mode == "title":
            m = .2
        else:
            m = 1 - max(0.0, st.left) / ROUND
        return round(m * TOD_STEPS) / TOD_STEPS

    def build_base(w, h, m):
        """Static backdrop for one time-of-day step: water gradient, banks, pads and reeds."""
        pal = palette(m)
        y0, y1 = 3, h - 2

        def dim(col):
            return mix(col, EVENING, m * .4) if col else col

        rows, wcol = [], []
        for y in range(h):
            k = ((y - y0) / max(1, y1 - y0)) ** .9 if y0 <= y <= y1 else 0
            wcol.append(mix(pal["wtop"], pal["wdeep"], k))
        shade = mix(pal["wdeep"], SHADE, .3)
        for y in range(h):
            row = []
            for x in range(w):
                hs = ((x * 73856093) ^ (y * 19349663)) & 0xffff
                if 2 <= x <= w - 3 and y0 <= y <= y1:
                    d = min(x - 2, w - 3 - x, 2 * (y - y0), 2 * (y1 - y))
                    bg = wcol[y] if d >= 3 else mix(wcol[y], shade, (1 - d / 3) * .4)
                    row.append((" ", None, bg))
                    continue
                g = mix(pal["grass"], pal["grassdk"], (hs % 9) / 12 + (y == 0) * .25)
                ch, fg = " ", None
                r = hs % 47
                if r < 2:
                    ch, fg = "✿", ((250, 170, 200), (250, 246, 236))[r]
                elif r == 2:
                    ch, fg = "•", (255, 222, 90)
                elif r < 12:
                    ch, fg = "'\",`"[r % 4], mix(g, pal["blade"], .7)
                row.append((ch, fg, g))
            rows.append(row)
        # shoreline: a soft sandy lip where the banks meet the water
        lip = mix(pal["shore"], wcol[y0], .35)
        for x in range(1, w - 1):
            g = rows[2][x][2]
            rows[2][x] = ("▄", lip, g)
            g = rows[h - 1][x][2]
            rows[h - 1][x] = ("▀", mix(pal["shore"], wcol[y1], .35), g)
        for y in range(3, h - 1):
            rows[y][1] = ("▐", mix(pal["shore"], wcol[y], .35), rows[y][1][2])
            rows[y][w - 2] = ("▌", mix(pal["shore"], wcol[y], .35), rows[y][w - 2][2])
        open_ = [[x >= 0 and rows[y][x][0] == " " and 2 <= x <= w - 3 and y0 <= y <= y1
                  for x in range(w)] for y in range(h)]
        for kind, x, y in st.items:
            if kind == "pad":
                for dx in range(1, 6):
                    if y + 2 < h and open_[y + 2][x + dx]:
                        rows[y + 2][x + dx] = (" ", None, mix(rows[y + 2][x + dx][2], shade, .35))
                for dx, dy, ch, fg, bg in PADSPR:
                    X, Y = x + dx, y + dy
                    rows[Y][X] = (ch, dim(fg), rows[Y][X][2] if bg is None else dim(bg))
                if (x * 5 + y) % 3 == 0:
                    rows[y][x + 5] = ("✿", LOTUS, rows[y][x + 5][2])
            else:
                weed = mix(wcol[y], (40, 90, 50), .55)
                for dx in range(3):
                    for dy in range(2):
                        rows[y + dy][x + dx] = (" ", None, mix(rows[y + dy][x + dx][2], weed, .5 + .3 * dy))
                for dx, dy, ch, fg in ((0, 1, "╲", REED_STEM), (1, 1, "│", REED_STEM), (2, 1, "╱", REED_STEM),
                                       (0, 0, "▌", CATTAIL[0]), (2, 0, "▖", CATTAIL[0])):
                    X, Y = x + dx, y + dy
                    rows[Y][X] = (ch, dim(fg), dim(CATTAIL[1]) if ch == "▌" else rows[Y][X][2])
                if y - 1 >= 0:
                    rows[y - 1][x + 1] = ("▌", dim(CATTAIL[0]), dim(CATTAIL[1]))
                    if y - 2 >= 3:
                        rows[y - 2][x + 1] = ("╻", REED_STEM, rows[y - 2][x + 1][2])
            for dx in range(-1, PAD[0] + 1):
                for dy in range(-2, 3):
                    if 0 <= y + dy < h and 0 <= x + dx < w:
                        open_[y + dy][x + dx] = False
        nx, ny = st.nest
        for yy in range(ny - 2, ny + 3):
            for xx in range(nx - 2, nx + NEST_W + 2):
                if 0 <= yy < h and 0 <= xx < w:
                    open_[yy][xx] = False
        return dict(key=(w, h, m, st.layout_n), rows=rows, wcol=wcol, pal=pal, open=open_)

    def draw_scene(c):
        # Writes c.cells rows directly; the static backdrop is cached per time-of-day step.
        w, h, t = c.w, c.h, st.clock
        m = tod()
        if st.base is None or st.base["key"] != (w, h, m, st.layout_n):
            st.base = build_base(w, h, m)
        base = st.base
        pal, wcol, open_ = base["pal"], base["wcol"], base["open"]
        cells = c.cells
        for y, row in enumerate(base["rows"]):
            cells[y] = row[:]
        y0, y1 = 3, h - 2
        # drifting glints, sparser and dimmer with depth
        for y in range(y0, y1 + 1):
            d = y - y0
            per, row, bg, op = 9 + 2 * (d % 4), cells[y], wcol[y], open_[y]
            fg = mix(bg, pal["hl"], .42 / (1 + d * .06))
            off = int(t * (1.2 + .25 * (d % 3))) * (1 if d % 2 else -1) + y * 7
            ch = "─" if d % 3 else "~"
            for x in range(2 + (-off) % per, w - 2, per):
                if op[x]:
                    row[x] = (ch, fg, row[x][2])
        # sun (moon at dusk) reflection: a shimmering column on the far water
        sx, tq = int(w * .42), int(t * 4)
        for y in range(y0, min(y1, y0 + 8) + 1):
            d = y - y0
            half = 1 + d // 2
            jit = int(1.5 * math.sin(tq * .9 + y * 1.7))
            row = cells[y]
            fg = mix(wcol[y], pal["sun"], .75 / (1 + .35 * d))
            for x in range(sx - half + jit, sx + half + jit + 1):
                if 0 <= x < w and open_[y][x] and (x * 3 + y + tq) % 4:
                    row[x] = ("━" if d % 2 else "─", fg, row[x][2])
        # cattail heads sway; reeds already sit in the backdrop
        for kind, x, y in st.items:
            if kind == "reed" and y - 1 >= 0 and math.sin(t * .9 + x * .37) > .6:
                row = cells[y - 1]
                row[x + 1] = ("▐", CATTAIL[0], CATTAIL[1])
        # fireflies come out as dusk falls
        fly = pal["fly"]
        if fly > 0:
            for f in flies:
                g = math.sin(t * f["sp"] * 2 + f["ph"])
                if g < .3:
                    continue
                x = int(2 + (f["x"] * (w - 4) + 5 * math.sin(t * .23 + f["ph"])) % (w - 4))
                y = int(3 + (f["y"] * (h - 5) + 2 * math.sin(t * .31 + f["ph"] * 2)) % (h - 5))
                row = cells[y]
                row[x] = ("•" if g > .7 else "·", mix(row[x][2], FIREFLY, g * fly), row[x][2])

    def ripple(x, y, r0=1.0, amp=1.0, life=RIPPLE_LIFE):
        if len(st.ripples) < 60:
            st.ripples.append(dict(x=x, y=y, t0=st.clock, r0=r0, amp=amp, life=life))

    def draw_ripples(c):
        base, cells, t = st.base, c.cells, st.clock
        open_, hl = base["open"], base["pal"]["hl"]
        keep = []
        for r in st.ripples:
            age = t - r["t0"]
            if age >= r["life"]:
                continue
            keep.append(r)
            k = age / r["life"]
            rad = r["r0"] + age * 5.5
            n = int(6 + rad * 2.2)
            seen = set()
            for i in range(n):
                a = 2 * math.pi * i / n
                x, y = int(round(r["x"] + rad * math.cos(a))), int(round(r["y"] + rad * .5 * math.sin(a)))
                if (x, y) in seen or not (0 <= y < c.h and 0 <= x < c.w) or not open_[y][x]:
                    continue
                seen.add((x, y))
                row = cells[y]
                bg = row[x][2]
                row[x] = ("‿" if math.sin(a) > .4 else "⁀" if math.sin(a) < -.4 else "~",
                          mix(bg, hl, (1 - k) ** 1.3 * .6 * r["amp"]), bg)
        st.ripples = keep

    nest_cache = {}

    def nest_sprite(shown, hops):
        """Nest art with `shown` ducklings tucked in; hops[i] lifts duckling i a pixel."""
        key = (shown, hops)
        spr = nest_cache.get(key)
        if spr is None:
            rows = [list(r) for r in NEST_ART]
            for i in range(shown):
                cx, top = NEST_SLOTS[i], 1 - hops[i]
                for dx, dy, p in ((0, 0, "h"), (1, 0, "Y"), (0, 1, "Y"), (1, 1, "D"), (0, 2, "Y"), (1, 2, "Y"),
                                  (2, 1, "O")):
                    if dx == 2 and i + 1 < shown:
                        continue  # the next duckling's head covers this bill
                    rows[top + dy][cx + dx] = p
            spr = nest_cache[key] = sprite(["".join(r) for r in rows], NEST_PAL)
        return spr

    def draw_nest(c):
        nx, ny = st.nest
        t, f = st.clock, st.nestf
        cx, cy = nx + NEST_W / 2, ny + .5
        if f > 0:
            # warm glow spilling over the water, fading as the celebration ends
            g0 = (f / 1.2) ** .7
            for y in range(ny - 7, ny + 8):
                for x in range(nx - 13, nx + NEST_W + 13):
                    d = math.hypot((x - cx) / 14, (y - cy) / 6.5)
                    if d < 1:
                        tint(c, x, y, GLOW, (1 - d) ** 1.6 * .6 * g0)
        # banked ducklings sit in the bowl; they hop in turn while the nest celebrates
        shown = min(st.banked - sum(1 for a in st.arrive if a["slot"] is not None), len(NEST_SLOTS))
        shown = max(0, shown)
        hops = tuple(int(f > 0 and (int(t * 8) + i) % 2) for i in range(shown))
        blit(c, nest_sprite(shown, hops), nx - 2, ny - 2)
        label = f" nest · {st.banked} " if st.banked else " nest "
        lx, ly = nx + (NEST_W - len(label)) // 2, ny - 3
        if 0 <= ly < c.h:
            row = c.cells[ly]
            for i, ch in enumerate(label):
                x = lx + i
                if 0 <= x < c.w and row[x][2].__class__ is tuple:
                    row[x] = (ch, CREAM, mix(row[x][2], INK, .45))
        if f > 0:
            u = 1.2 - f
            for i in range(10):
                a = t * 2.2 + i * 2 * math.pi / 10
                rad = 5 + u * 9
                x, y = int(cx + rad * math.cos(a)), int(cy - 1 + rad * .45 * math.sin(a) - u * 2)
                c.put(x, y, "✦✧·"[(i + int(t * 6)) % 3], GLOW if i % 2 else CREAM)

    def draw_arrivals(c, items):
        """Banked ducklings hop from the line into their nest slot (visual only)."""
        keep = []
        nx, ny = st.nest
        for a in st.arrive:
            u = (st.clock - a["t0"]) / .45
            if u >= 1:
                continue
            keep.append(a)
            if u < 0:
                items.append((a["y"], DUCK[(1, 0)], int(a["x"]) - DUCK_AX, int(a["y"]) - 2))
                continue
            tx, ty = nx - 2 + a["slot"], ny - 1
            x = a["x"] + (tx - a["x"]) * u
            y = a["y"] + (ty - a["y"]) * u - 3 * math.sin(math.pi * u)
            items.append((99, DUCK[(1 if tx >= a["x"] else -1, 0)], int(round(x)) - DUCK_AX, int(round(y)) - 2))
        st.arrive = keep

    def spring(d):
        """Visual-only spring toward the gameplay position (hitboxes use d['x'], d['y'])."""
        if "rx" not in d:
            d.update(rx=d["x"], ry=d["y"], vx=0.0, vy=0.0, f=1)
        n = max(1, int(dt / .02 + .999))
        h = dt / n
        for _ in range(n):
            d["vx"] += (140 * (d["x"] - d["rx"]) - 16 * d["vx"]) * h
            d["vy"] += (140 * (d["y"] - d["ry"]) - 16 * d["vy"]) * h
            d["rx"] += d["vx"] * h
            d["ry"] += d["vy"] * h
        if d["vx"] > 1.5:
            d["f"] = 1
        elif d["vx"] < -1.5:
            d["f"] = -1

    def duck_item(d, face, lost, items, marks):
        t = st.clock
        hop = t - d.get("hop", -9)
        bob = int(t * (5 if not lost else 2.2) + d["x"] * .7) % 2
        lift = 1 if 0 <= hop < .3 else 0
        x, y = int(round(d["rx"])), int(round(d["ry"]))
        items.append((d["ry"], DUCK[(face, 0 if lift else bob)], x - (DUCK_AX if face > 0 else 7 - DUCK_AX),
                      y - 2 - lift))
        if 0 <= hop < .7:
            marks.append((x, y - 4 - int(hop * 3), "♥", (255, 120, 150), None))

    def draw_actors(c):
        """Mama and ducklings, painted in row order so nearer (lower) swimmers overlap."""
        t = st.clock
        open_ = st.base["open"]
        items, marks = [], []
        for d in st.lost:
            spring(d)
            sx, sy = int(round(d["rx"])), int(round(d["ry"]))
            if d["imm"] > 0:
                if int(t * 10) % 2:
                    continue  # just scattered: blinks until it can be collected again
            else:
                # a soft pulsing halo on the water so lost ducklings are easy to spot
                pulse = .5 + .5 * math.sin(t * 3 + d["x"])
                for yy in range(sy - 3, sy + 2):
                    if not 0 <= yy < c.h:
                        continue
                    for xx in range(sx - 7, sx + 8):
                        k = 1 - math.hypot((xx - sx) / 7, (yy - sy + 1) / 2.4)
                        if k > 0 and 0 <= xx < c.w and open_[yy][xx]:
                            tint(c, xx, yy, GLOW, k * (.16 + .12 * pulse))
                if d["pp"] < 0:
                    for i, ch in enumerate(" peep! "):
                        marks.append((sx - 3 + i, sy - 3, ch, INK, CREAM))
                else:
                    marks.append((sx, sy - 3 - (int(t * 3 + d["x"]) % 2), "!", (255, 236, 120), None))
            face = 1 if int(t * 1.3 + d["x"] * .31) % 2 else -1
            duck_item(d, face, True, items, marks)
        for d in st.line:
            spring(d)
            duck_item(d, d["f"], False, items, marks)
            if st.moving and srng.random() < .08:
                ripple(d["rx"] - d["f"] * 3, d["ry"], .5, .6, .8)
        draw_arrivals(c, items)
        mx, my = int(round(st.mx)), int(round(st.my))
        hap = t - st.hap
        pose = "happy" if 0 <= hap < .7 else "blink" if t % 4.3 > 4.15 else "idle"
        lift = 1 if 0 <= hap < .28 else 0
        bob = int(t * (6 if st.moving else 1.6)) % 2
        face = st.face if st.face else 1
        x0 = mx - (MAMA_AX if face > 0 else 15 - MAMA_AX)
        # ties go to mama so the duckling right behind her tucks under her tail
        items.append((st.my - .01, MAMA[(pose, face, 0 if lift else bob)], x0, my - 3 - lift))
        items.sort(key=lambda it: it[0])
        for _, spr, x, y in items:
            blit(c, spr, x, y)
        for x, y, ch, fg, bg in marks:
            c.put(x, y, ch, fg, bg)

    def draw_fox(c):
        f = st.fox
        fx, fy = fox_pos()
        w, h = c.w, c.h
        if f["mode"] != "prowl":
            # the pounce reach, tinted red so the danger zone is readable before it strikes
            k = .16 + .14 * (int(st.clock * 8) % 2) if f["mode"] == "stalk" else .32
            for y in range(int(fy) - 4, int(fy) + 5):
                for x in range(int(fx) - 8, int(fx) + 9):
                    if 1 <= y < h and 0 <= x < w and math.hypot(x - fx, 2 * (y - fy)) <= 8:
                        tint(c, x, y, DANGER, k * (1 - .5 * math.hypot(x - fx, 2 * (y - fy)) / 8))
        x1, y1, x2, y2 = st.ring
        if fy <= y1 + .01:
            face = f["dir"]
        elif fy >= y2 - .01:
            face = -f["dir"]
        else:
            face = 1 if fx < w / 2 else -1
        if f["mode"] == "prowl":
            pose = "ab"[int(st.clock * 7) % 2]
        else:
            pose = f["mode"]
        ix, iy = int(round(fx)), int(round(fy))
        # the bottom bank is one row deep, so the sprite stands on it rather than below it
        x0 = max(0, min(w - 14, ix - (FOX_AX if face > 0 else 13 - FOX_AX)))
        blit(c, FOX[(pose, face)], x0, min(iy - 1, h - 3))
        if f["mode"] != "prowl":
            msg = " !! " if f["mode"] == "pounce" else " ! "
            mx_ = max(0, min(w - len(msg), ix - len(msg) // 2 + face * 2))
            my_ = max(1, iy - 2)
            c.text(mx_, my_, msg, (255, 255, 255), (214, 48, 48))

    def draw_hawk(c):
        k = st.hawk
        w, h = c.w, c.h
        if k["phase"] == "warn":
            u = min(1.0, k["t"] / 1.6)
            ex = 0 if k["side"] < 0 else w - 1
            x0, x1 = (-10, w + 10) if k["side"] < 0 else (w + 10, -10)
            # the dive path draws itself across the pond
            for i in range(0, int((w + 20) * u), 3):
                px = x0 + (i if x1 > x0 else -i)
                py = k["y0"] + (k["y1"] - k["y0"]) * i / (w + 20)
                if 0 <= px < w and 3 <= py < h - 1:
                    row = c.cells[int(py)]
                    bg = row[int(px)][2]
                    if bg.__class__ is tuple:
                        row[int(px)] = ("•" if i % 6 == 0 else "·", mix(bg, WARN, .6), bg)
            # its shadow gathers at the entry edge, growing as the hawk drops
            cy = k["y0"]
            rx, ry = 8 * u, 2.5 * u
            for y in range(int(cy - ry) - 1, int(cy + ry) + 2):
                for x in range(int(ex - rx) - 1, int(ex + rx) + 2):
                    if rx > 0 and ((x - ex) / rx) ** 2 + ((y - cy) / max(.5, ry)) ** 2 <= 1:
                        tint(c, x, y, SHADE, .25 + .25 * u)
            if int(k["t"] * 6) % 2 == 0:
                for y in range(int(cy) - 1, int(cy) + 2):
                    c.put(ex, y, "!", (255, 255, 255), (214, 48, 48))
            # high up and small: a circling dot over the entry side
            a = k["t"] * 5
            hx = int(ex + (-1 if k["side"] > 0 else 1) * (5 + 3 * math.cos(a)))
            hy = int(cy - 3 + 1.5 * math.sin(a))
            c.put(hx, hy, "v" if int(k["t"] * 8) % 2 else "w", HAWK_PAL["o"])
            msg = " a hawk circles! "
            center(c, h - 1, msg, (255, 255, 255), (178, 44, 52))
        elif k["phase"] == "sweep":
            sx, sy = hawk_shadow()
            # the shadow is the hitbox: darker at its heart, lighter at the rim
            for y in range(int(sy - 3), int(sy + 4)):
                for x in range(int(sx - 9), int(sx + 10)):
                    e = ((x - sx) / 8) ** 2 + ((y - sy) / 2.5) ** 2
                    if e <= 1 and 2 <= y < h:
                        tint(c, x, y, SHADE, .62 - .22 * e)
                        if e > .62:
                            tint(c, x, y, WARN, .3 * (e - .62) / .38)
            face = 1 if k["x1"] > k["x0"] else -1
            frame = "ab"[int(st.clock * 7) % 2]
            blit(c, HAWK[(frame, face)], int(sx) - 4, int(sy) - 7)

    def pill(c, x, y, s, fg, bg, edge, limit):
        """A rounded badge: half-block caps either side of the text; skipped past `limit`."""
        if x < 0 or x + len(s) + 2 > limit:
            return x
        c.put(x, y, "▐", bg, edge)
        c.text(x + 1, y, s, fg, bg)
        c.put(x + len(s) + 1, y, "▌", bg, edge)
        return x + len(s) + 3

    def hud(c):
        w = c.w
        edge = c.cells[0][0][2]
        frac = max(0.0, st.left / ROUND) if st.mode != "title" else 1.0
        col = (130, 220, 110) if frac > .4 else (255, 210, 70) if frac > .15 else (255, 90, 80)
        if frac <= .15 and st.mode == "play" and int(st.clock * 4) % 2:
            col = (255, 160, 150)
        bw = 10 if w >= 70 else 5
        n = int(frac * bw + .999)
        secs = f"{int(math.ceil(max(0.0, st.left))) if st.mode != 'title' else int(ROUND)}s"
        s = " " + "▰" * n + "▱" * (bw - n) + f" {secs:>3} "
        x0 = w - len(s) - 3
        pill(c, x0, 0, s, col, (34, 52, 66), edge, w)
        lim = x0 - 1
        x = pill(c, 1, 0, " ducklings ", INK, (255, 214, 64), edge, lim)
        x = pill(c, x, 0, f" saved {st.banked} ", CREAM, (44, 76, 96), edge, lim)
        x = pill(c, x, 0, f" score {st.score} ", CREAM, (44, 76, 96), edge, lim)
        x = pill(c, x, 0, f" best {st.best} ", (200, 210, 214), (34, 52, 66), edge, lim)
        if st.line:
            n = len(st.line)
            s = " " + "●" * min(n, 8) + (f"+{n - 8}" if n > 8 else "") + " in tow "
            pill(c, x, 0, s, (255, 220, 90), (60, 64, 40), edge, lim)

    def panel(c, lines, y0, colors=None):
        """Rounded card in the palette's panel colour; returns its (x0, width)."""
        pal = st.base["pal"]
        bg = pal["panel"]
        rim = mix(bg, (255, 214, 64), .55)
        bw = max(len(s) for s in lines) + 6
        x0 = (c.w - bw) // 2
        hh = len(lines) + 2
        for i in range(hh):
            y = y0 + i
            for x in range(x0, x0 + bw):
                if i == 0 or i == hh - 1:
                    ch = ("╭" if x == x0 else "╮" if x == x0 + bw - 1 else "─") if i == 0 else \
                         ("╰" if x == x0 else "╯" if x == x0 + bw - 1 else "─")
                else:
                    ch = "│" if x in (x0, x0 + bw - 1) else " "
                c.put(x, y, ch, rim, bg)
        for i, s in enumerate(lines):
            col = (colors or {}).get(i, CREAM)
            c.text(x0 + (bw - len(s)) // 2, y0 + 1 + i, s, col, bg)
        # soft drop shadow along the bottom and right edge
        for x in range(x0 + 1, x0 + bw + 1):
            tint(c, x, y0 + hh, SHADE, .35)
        for y in range(y0 + 1, y0 + hh):
            tint(c, x0 + bw, y, SHADE, .35)
        return x0, bw

    def too_small(c, keys):
        c.clear()
        lines = textwrap.wrap(MSG_SMALL, max(1, c.w)) or [""]
        for i, s in enumerate(lines[:c.h]):
            c.text(max(0, (c.w - len(s)) // 2), max(0, (c.h - len(lines)) // 2) + i, s[:c.w], 226)
        return "q" in keys

    def title(c):
        lines = ["D U C K L I N G S", "herd the lost ducklings home before dusk", "", "", "", "",
                 "arrows / WASD  swim (she stops when you let go)",
                 "touch lost ducklings: they follow in a line",
                 "reach the nest to bank them - big herds = combo",
                 "fox on the bank and hawk shadows scatter the line",
                 "lily pads and reeds block the way",
                 "90 second rounds", "",
                 "p pause   q quit   r restart   m mute", "", "press SPACE to begin"]
        y0 = max(1, (c.h - len(lines) - 2) // 2)
        x0, bw = panel(c, lines, y0, {0: (255, 214, 64), 1: (190, 214, 220), 15: (255, 214, 64)})
        # a little parade swimming across the card
        t = st.clock
        span = bw - 30
        px = x0 + 4 + int((t * 6) % max(1, span))
        bob = int(t * 3) % 2
        # card rows y0+3 .. y0+6 are left blank for it
        for i in range(3):
            blit(c, DUCK[(1, (bob + i) % 2)], px - 7 * (i + 1) + 8, y0 + 4)
        blit(c, MAMA[("happy" if t % 3 < .4 else "idle", 1, bob)], px + 8, y0 + 3)

    def step(c, frame, keys):
        if frame % 10 == 0 and not st.done and game.claude_done():
            st.done, st.banner = True, 8.0
        if st.banner > 0:
            st.banner -= dt
        if c.w < MIN_W or c.h < MIN_H:
            return too_small(c, keys)
        if "q" in keys:
            return True
        if st.size != (c.w, c.h):
            if st.size is None:
                st.size = (c.w, c.h)
                reset()
            else:
                layout(c.w, c.h)
                st.line.clear()
                for d in st.lost:
                    if blocked(d["x"], d["y"]):
                        d["x"], d["y"] = place_free()
        st.clock += dt
        if demo:
            if st.mode == "title":
                keys = ["space"]
            elif st.mode == "over":
                keys = ["r"] if st.over_t > 2 else []
            else:
                keys = bot()
        if st.mode == "title":
            if "space" in keys or "enter" in keys:
                reset()
                st.mode = "play"
                audio.sfx("quack")
        elif st.mode == "play":
            if "p" in keys:
                st.paused = not st.paused
            if not st.paused:
                update(keys)
        else:
            st.over_t += dt
            if "r" in keys:
                reset()
                st.mode = "play"
                audio.sfx("quack")
        pos = (st.mx, st.my)
        st.moving = st.prev is not None and pos != st.prev and not st.paused
        st.prev = pos
        if st.moving and st.clock - st.wake > .16:
            st.wake = st.clock
            ripple(st.mx - st.face * 7, st.my, 1.0, 1.0)
        draw_scene(c)
        draw_ripples(c)
        draw_nest(c)
        draw_actors(c)
        draw_fox(c)
        draw_hawk(c)
        for f in st.floats:
            c.text(int(f["x"]), int(f["y"]), f["txt"], f["col"])
        hud(c)
        if st.mode == "title":
            title(c)
        elif st.paused:
            panel(c, ["PAUSED", "p to resume"], c.h // 2 - 2, {0: (255, 214, 64)})
        elif st.mode == "over":
            lines = ["TIME'S UP", "the sun has set on the pond", "",
                     f"score {st.score}", f"{st.banked} ducklings saved", f"best  {st.best}"]
            if st.newbest:
                lines.append("✦ new best! ✦")
            lines += ["", "r again   q quit"]
            panel(c, lines, max(1, c.h // 2 - 6), {0: (255, 214, 64), 1: (200, 190, 220), 6: (255, 160, 190)})
        if st.done and st.banner > 0:
            center(c, 3, " Claude's done! ", 16, 229 if int(st.banner * 3) % 2 else 222)
        return False

    return game.play(args, step, music="ducklings")


if __name__ == "__main__":
    raise SystemExit(main())
