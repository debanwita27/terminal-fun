#!/usr/bin/env python3
"""Froghop: a one-button, endless, side-view pond hopper.

Usage: python3 froghop.py [--fps 20] [--frames N] [--seed S]
Tap SPACE to start a power meter, tap SPACE again to leap. Land on lily pads,
catch dragonflies mid-arc. Without a tty an autopilot plays (for smoke tests).
"""

META = {"name": "froghop", "kind": "play", "blurb": "A one-button pond hopper: charge a leap and land on lily pads",
        "credit": [{"type": "inspired by",
                    "who": "Joan Stark (jgs) ASCII frogs",
                    "url": "https://www.asciiart.eu/animals/frogs"}]}

import math
import os
import random
import textwrap
import types

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

from fun import audio, term, game

NAME = "froghop"
MIN_W, MIN_H = 44, 14
LIVES = 3
SWEEP = 1.1  # seconds for the meter to run empty -> full -> empty
MIN_D, MAX_D = 6, 32
MSG_SMALL = "make the terminal bigger"

# Frog palette. Sprite rows below are (chars, fg, bg) strings of equal width; each
# fg/bg letter keys this dict and "." means none (a space with no bg is transparent).
FROG_PAL = {"G": (112, 196, 70), "L": (170, 228, 112), "D": (56, 140, 60), "B": (232, 238, 182),
            "Q": (250, 250, 214), "W": (250, 250, 244), "P": (24, 30, 34), "K": (238, 136, 150),
            "M": (30, 78, 40)}
# Rows may differ in (odd) width; each is centred on the frog's x, bottom row last.
EYES = ("   ' ▄  '  ", "...W.G..W..", ".GWPG.GWPG.")
DOME = (" ▗▄▄▖ ▗▄▄▖ ", ".LLLL.LLLL.", "...........")
FROG_ART = {
    "idle": [DOME, EYES,
             ("   ╰───╯   ", "...MMMMM...", ".GKGGGGGKG."),
             ("▟ ▄     ▄ ▙", "D.G.....G.D", ".DBBBBBBBD.")],
    "blink": [DOME,
              ("  ── ▄ ──  ", "..MM.G.MM..", ".GLLG.GLLG."),
              ("   ╰───╯   ", "...MMMMM...", ".GKGGGGGKG."),
              ("▟ ▄     ▄ ▙", "D.G.....G.D", ".DBBBBBBBD.")],
    "puff": [DOME, EYES,
             ("   ╰▄▄▄╯   ", "...MQQQM...", ".GKGGGGGKG."),
             ("▟ ▄     ▄ ▙", "D.G.....G.D", ".DBQQQQQBD.")],
    "crouch": [DOME, EYES,
               ("▟  ╰───╯  ▙", "D..MMMMM..D", ".GKBBBBBKG.")],
    "squint": [DOME,
               ("   > ▄ <   ", "...P.G.P...", ".GLLG.GLLG."),
               ("▄▟  ╰───╯  ▙▄", "DD..MMMMM..DD", "..GKBBBBBKG..")],
    "leap": [DOME, EYES,
             ("   ╰───╯   ", "...MMMMM...", ".GKGGGGGKG."),
             ("  ▜     ▛  ", "..D.....D..", "...GBBBG..."),
             ("  ▐▌   ▐▌  ", "..DD...DD..", "..........."),
             (" ▀▀▘   ▝▀▀ ", ".DDD...DDD.", "...........")],
    "fall": [DOME, EYES,
             ("   ╰───╯   ", "...MMMMM...", ".GKGGGGGKG."),
             ("▄▀         ▀▄", "DD.........DD", "..DGBBBBBGD..")],
    "land": [DOME,
             ("  ╱╲ ▄ ╱╲  ", "..MM.G.MM..", ".GGGG.GGGG."),
             ("▄▟ ╰─────╯ ▙▄", "DD.MMMMMMM.DD", "..KBBBBBBBK..")],
}


def _compile(rows):
    """Sprite rows -> [(dx, dy, ch, fg, bg)], dy 0 on the bottom row, transparent cells dropped."""
    out = []
    for i, (chs, fgs, bgs) in enumerate(rows):
        w = len(chs)
        assert w % 2 and len(fgs) == len(bgs) == w, (chs, fgs, bgs)
        for x, (ch, fg, bg) in enumerate(zip(chs, fgs, bgs)):
            if ch != " " or bg != ".":
                out.append((x - w // 2, i - len(rows) + 1, ch, FROG_PAL.get(fg), FROG_PAL.get(bg)))
    return out


FROG = {name: _compile(rows) for name, rows in FROG_ART.items()}
PAD_OK = ((118, 196, 104), (40, 116, 70))  # (lit rim, body)
PAD_WARN = (((206, 184, 84), (150, 118, 46)), ((172, 150, 70), (118, 92, 40)))
PAD_SHADOW, LOTUS = (0, 62, 92), (250, 150, 196)
DROPLET, DROPLET_DIM = (190, 232, 250), (110, 170, 200)
PUFF_EVERY, PUFF_AT = 5.5, 1.6  # idle seconds: the throat puffs (and ribbits) once per cycle
# Fail pose: wide worried eyes and a wobbly frown, drawn sinking below the surface row.
FROG["sad"] = _compile([DOME,
                        ("   • ▄ •   ", "...P.G.P...", ".GWWG.GWWG."),
                        ("   ╭───╮   ", "...MMMMM...", ".GKGGGGGKG."),
                        ("▟ ▄     ▄ ▙", "D.G.....G.D", ".DBBBBBBBD.")])
MOUTH_DY = {"leap": -3, "fall": -1}  # mouth row relative to the sprite's bottom row

# Pond time of day: the scene lerps between these keyframes as `m` goes 0 (night) -> 1 (dusk).
NIGHT = dict(top=(10, 10, 34), hor=(58, 40, 104), wtop=(34, 50, 100), wdeep=(5, 10, 28),
             moon=(250, 244, 216), glow=(150, 136, 214), stem=(46, 78, 52), star=1.0)
DUSK = dict(top=(34, 30, 86), hor=(228, 146, 156), wtop=(96, 84, 140), wdeep=(18, 18, 50),
            moon=(255, 242, 226), glow=(255, 196, 190), stem=(58, 62, 64), star=.35)
TOD_CYCLE, TOD_STEPS, TOD_MAX = 180.0, 24, .85  # seconds per night-dusk-night, palette steps
CATTAIL = ((156, 100, 58), (100, 60, 36))  # (lit side, shade)
REED_FG = (8, 10, 22)
FIREFLY = (214, 255, 120)
SPRAY = (196, 232, 250)
BUBBLE = (176, 228, 248)
TONGUE = (240, 112, 142)
RIPPLE_LIFE = 1.4
# Dragonfly, seen from above and flying left: wings above and below the body row.
# Wing cells are tinted toward the sky behind them so they read as translucent.
DFLY_WINGS = ((" ▗▆▖▗▆▖", " ▝▀▘▝▀▘"), ("  ▄▄▄▄ ", "  ▀▀▀▀ "))  # (above, below) from dx -3
DFLY_WING = (170, 222, 255)
DFLY_EYE, DFLY_THORAX = (110, 240, 214), (44, 150, 160)


def mix(a, b, k):
    """Lerp two rgb tuples; k is clamped to 0..1."""
    k = 0.0 if k < 0 else 1.0 if k > 1 else k
    return (int(a[0] + (b[0] - a[0]) * k + .5), int(a[1] + (b[1] - a[1]) * k + .5),
            int(a[2] + (b[2] - a[2]) * k + .5))


def hue(h):
    """Iridescent rgb for h in 0..1 (teal -> blue -> violet)."""
    h = .47 + .33 * tri(2 * h)
    k = h * 6
    i, f = int(k) % 6, k - int(k)
    v, p, q, t = 1.0, .25, 1 - .75 * f, .25 + .75 * f
    r, g, b = ((v, t, p), (q, v, p), (p, v, t), (p, q, v), (t, p, v), (v, p, q))[i]
    return int(r * 235), int(g * 235), int(b * 235)


def tri(x):
    x %= 2.0
    return x if x <= 1 else 2 - x


def center(c, y, s, color=None, bg=None):
    c.text((c.w - len(s)) // 2, y, s, color, bg)


def main():
    parser = term.make_parser(__doc__.splitlines()[0])
    parser.add_argument("--seed", type=int, default=None, help="random seed")
    parser.add_argument("--demo", action="store_true", help="autopilot plays (default without a tty)")
    args = parser.parse_args()
    rng = random.Random(args.seed)
    dt = 1 / max(1.0, args.fps)
    demo = args.demo or not os.isatty(0)
    st = types.SimpleNamespace(mode="title", paused=False, done=False, banner=0.0,
                               best=game.best(NAME), newbest=False, wy=19, cam=0.0,
                               t=0.0, over_t=0.0, w=80, clock=0.0, base=None, ripples=[])
    srng = random.Random(7)  # scenery only, so the gameplay rng sequence is untouched
    flies = [dict(wx=srng.uniform(0, 200), y=srng.uniform(1.5, 6), ph=srng.uniform(0, 6.28),
                  sp=srng.uniform(.4, .9)) for _ in range(8)]

    def make_pad(prev, n):
        half = rng.choice((3, 4, 4))
        p = dict(bx=0.0 if n == 0 else prev["bx"] + rng.randint(13, min(22, 14 + n // 2)),
                 half=half, amp=0, spd=0, ph=0, per=0, sph=0, n=n, seen=n == 0,
                 fl=rng.randint(1 - half, half - 1) if rng.random() < .4 else None)
        if n >= 2:
            r = rng.random()
            if r < .3 and not prev["amp"]:
                p.update(amp=rng.uniform(2, 3), spd=rng.uniform(.5, 1), ph=rng.uniform(0, 6.28))
            elif .3 <= r < .5:
                p.update(per=rng.uniform(7, 10), sph=rng.uniform(0, 10))
        return p

    def px(p):
        return p["bx"] + p["amp"] * math.sin(st.t * p["spd"] + p["ph"])

    def pad_state(p):
        if not p["per"]:
            return "ok"
        c = (st.t + p["sph"]) % p["per"]
        if c >= p["per"] - 1.2:
            return "sunk"
        return "warn" if c >= p["per"] - 3.2 else "ok"

    def reset():
        st.t, st.lives, st.score = 0.0, LIVES, 0
        first = make_pad(None, 0)
        st.pads = [first]
        st.f = dict(mode="idle", pad=first, last=first, off=0.0, x=0.0, y=st.wy - 2.0, p=0.0,
                    t0=0.0, j=None, since=0.0, at=0.0, lt=-9.0,
                    tongue=None)
        st.ripples = []
        st.bugs, st.floats = [], []
        st.bugt = 2.0
        st.newbest = False
        st.cam = -st.w // 3

    def pop(text, x, y, col=229):
        st.floats.append(dict(txt=text, x=x, y=y, ttl=1.2, col=col))

    def ripple(x, amp=1.0):
        st.ripples.append(dict(x=x, t0=st.t, amp=amp))

    def splash(x):
        f = st.f
        f.update(mode="splash", pad=None, at=0.0, x=x)
        ripple(x, 1.6)
        audio.sfx("splash")
        audio.sfx("frogsad")
        st.lives -= 1

    def launch():
        f = st.f
        d = MIN_D + f["p"] * (MAX_D - MIN_D)
        audio.sfx("frogleap")
        f.update(mode="air", pad=None,
                 j=dict(x0=f["x"], D=d, H=min(2 + d * .22, st.wy - 4), T=.55 + d * .012, u=0.0))

    def land():
        f, j = st.f, st.f["j"]
        lx = j["x0"] + j["D"]
        for p in st.pads:
            if pad_state(p) != "sunk" and abs(lx - px(p)) <= p["half"] + .5:
                f.update(mode="idle", pad=p, last=p, off=lx - px(p), since=st.t, lt=st.t)
                ripple(lx, .8)
                audio.sfx("frogland")
                if not p["seen"]:
                    p["seen"] = True
                    st.score += 1
                    pop("+1", lx, st.wy - 4, 120)
                return
        splash(lx)

    def finish():
        st.mode = "over"
        audio.sfx("gameover")
        st.over_t = 0.0
        st.newbest = game.record(NAME, st.score)
        st.best = max(st.best, st.score)

    def update(keys):
        wy, f = st.wy, st.f
        st.t += dt
        while st.pads[-1]["bx"] < st.cam + 160:
            st.pads.append(make_pad(st.pads[-1], st.pads[-1]["n"] + 1))
        st.pads = [p for p in st.pads if p["bx"] > st.cam - 40 or p is f["last"]]
        for p in st.pads:
            sunk = pad_state(p) == "sunk"
            if sunk and not p.get("was"):
                ripple(px(p), 1.2)
            p["was"] = sunk
        st.ripples = [r for r in st.ripples if st.t - r["t0"] < RIPPLE_LIFE]
        space = "space" in keys
        if f["mode"] in ("idle", "meter"):
            pad = f["pad"]
            f["x"], f["y"] = px(pad) + f["off"], wy - 2
            if f["mode"] == "idle" and space:
                f.update(mode="meter", t0=st.t, p=0.0)
            elif f["mode"] == "meter":
                if space:
                    launch()
                else:
                    f["p"] = tri(2 * (st.t - f["t0"]) / SWEEP)
            it = st.t - f["since"]
            if f["mode"] == "idle" and (it - dt) % PUFF_EVERY < PUFF_AT <= it % PUFF_EVERY:
                audio.sfx("ribbit", .7)
            if f["mode"] != "air" and pad_state(pad) == "sunk":
                splash(f["x"])
        elif f["mode"] == "air":
            j = f["j"]
            j["u"] += dt / j["T"]
            u = min(j["u"], 1.0)
            f["x"] = j["x0"] + j["D"] * u
            f["y"] = wy - 2 - j["H"] * 4 * u * (1 - u)
            for b in st.bugs:
                if b["on"] and abs(b["x"] - f["x"]) <= 3 and abs(b["y"] - f["y"] - .5) <= 1.5:
                    b["on"] = False
                    st.score += 5
                    f["tongue"] = (st.t, b["x"] - f["x"], b["y"])
                    pop("+5 bug!", b["x"] - 2, b["y"] - 5, 51)
                    audio.sfx("frogsnap")
            if j["u"] >= 1:
                land()
        else:
            f["at"] += dt
            if f["at"] > 1.3:
                if st.lives <= 0:
                    finish()
                    return
                pad = f["last"]
                if pad["per"]:
                    pad["sph"] = -st.t % pad["per"]
                f.update(mode="idle", pad=pad, off=0.0, since=st.t)
        st.bugt -= dt
        if st.bugt <= 0:
            st.bugt = rng.uniform(2.5, 5)
            st.bugs.append(dict(x=st.cam + st.w + 3, y=rng.randint(2, max(2, wy - 4)),
                                vx=-rng.uniform(3, 6), ph=rng.uniform(0, 6.28), on=True, y0=0))
            st.bugs[-1]["y0"] = st.bugs[-1]["y"]
        for b in st.bugs:
            b["x"] += b["vx"] * dt
            b["y"] = max(2, min(wy - 3, b["y0"] + 1.6 * math.sin(st.t * 2.2 + b["ph"])))
        st.bugs = [b for b in st.bugs if b["x"] > st.cam - 8 and b["on"]]
        for fl in st.floats:
            fl["ttl"] -= dt
            fl["y"] -= 3 * dt
        st.floats = [fl for fl in st.floats if fl["ttl"] > 0]
        st.cam += (f["x"] - st.w // 3 - st.cam) * .12

    def bot():
        f = st.f
        if f["mode"] == "idle" and st.t - f["since"] > .5:
            return ["space"]
        if f["mode"] == "meter":
            nxt = next((p for p in st.pads if p["n"] == f["pad"]["n"] + 1), None)
            if nxt:
                want = (px(nxt) - f["x"] - MIN_D) / (MAX_D - MIN_D)
                if 0 <= want <= 1 and abs(f["p"] - want) <= .06:
                    return ["space"]
        return []

    def palette(m):
        return {k: (mix(NIGHT[k], DUSK[k], m) if isinstance(NIGHT[k], tuple)
                    else NIGHT[k] + (DUSK[k] - NIGHT[k]) * m) for k in NIGHT}

    def build_base(w, h, wy, m):
        """Static backdrop for one time-of-day step: sky and water gradients, moon and halo."""
        pal = palette(m)
        sky = [mix(pal["top"], pal["hor"], (y / max(1, wy - 1)) ** 1.5) for y in range(wy)]
        water = [mix(pal["wtop"], pal["hor"], .22)] + [
            mix(pal["wtop"], pal["wdeep"], ((y - wy) / max(1, h - 1 - wy)) ** .8) for y in range(wy + 1, h)]
        cols = sky + water
        rows = [[(" ", None, col)] * w for col in cols]
        mx, my, r, halo = w - 12, 7.0, 3.3, 9.0  # moon centre and radii in half-cell pixels
        moon, glow, dark = pal["moon"], pal["glow"], mix(pal["moon"], pal["glow"], .35)

        def pix(x, py):
            """Colour of one half-cell pixel, or None outside the halo."""
            d = math.hypot(x + .5 - mx, py + .5 - my)
            if d < r:
                crater = math.hypot(x - mx + 1.0, py - my + .6) < 1.1
                return mix(moon, dark, .3 if crater else (d / r) ** 3 * .35), True
            g = 1 - (d - r) / halo
            return (mix(cols[min(int(py) // 2, wy - 1)], glow, g ** 2.4 * .45) if g > 0 else None), False

        for y in range(max(0, int(my - r - halo) // 2), min(wy, int(my + r + halo) // 2 + 1)):
            for x in range(max(0, int(mx - r - halo)), min(w, int(mx + r + halo) + 1)):
                (top, tin), (bot, bin_) = pix(x, 2 * y), pix(x, 2 * y + 1)
                top, bot = top or cols[y], bot or cols[y]
                if tin and not bin_:
                    rows[y][x] = ("▀", top, bot)
                elif bin_ and not tin:
                    rows[y][x] = ("▄", bot, top)
                else:
                    rows[y][x] = (" ", None, mix(top, bot, .5))
        return dict(key=(w, h, wy, m), rows=rows, cols=cols, pal=pal, mx=mx)

    def draw_scene(c):
        # Writes c.cells rows directly; the static backdrop is cached per time-of-day step.
        w, h, wy, cam, t = c.w, c.h, st.wy, st.cam, st.clock
        m = round(TOD_MAX * (.5 - .5 * math.cos(2 * math.pi * t / TOD_CYCLE)) * TOD_STEPS) / TOD_STEPS
        if st.base is None or st.base["key"] != (w, h, wy, m):
            st.base = build_base(w, h, wy, m)
        base = st.base
        cols, pal = base["cols"], base["pal"]
        cells = c.cells
        for y, row in enumerate(base["rows"]):
            cells[y] = row[:]
        icam, tq = int(cam), int(t * 5)
        # twinkling stars, fainter at dusk; skipped on the moon and its halo
        span, sv = max(1, wy - 6), pal["star"]
        for x in range(w):
            wx = x + int(cam * .1)
            hsh = wx * 2654435761
            if (hsh >> 7) % 17 == 0:
                y = 1 + ((wx * 40503) >> 3) % span
                row = cells[y]
                if row[x][0] == " " and row[x][2] == cols[y]:
                    lv = (tq + (hsh >> 11)) % 23
                    ch, k = ("+", 1.0) if lv == 0 else ("·", .8) if lv < 8 else (".", .5)
                    row[x] = (ch, mix(cols[y], (255, 250, 236), k * sv), cols[y])
        # cattails: slim stems, a solid two-tone head, swaying a column at the top
        stem = pal["stem"]
        for x in range(w):
            wx = x + int(cam * .5)
            hh = ((wx * 2246822519) & 0xffffffff) >> 20 & 31
            if hh < 4:
                hgt = 2 + (wx * 13) % 4
                sway = math.sin(t * .8 + wx * .37)
                off = 1 if sway > .65 else -1 if sway < -.65 else 0
                for k in range(1, hgt):
                    row = cells[wy - k]
                    ch = "│" if not off or k < hgt - 1 else ("╱" if off > 0 else "╲")
                    row[x] = (ch, stem, row[x][2])
                hx = x + off
                if 0 <= hx < w:
                    for k, ch in ((hgt, "▌"), (hgt + 1, "▖")):
                        row = cells[wy - k]
                        row[hx] = (ch, CATTAIL[0], CATTAIL[1] if ch == "▌" else row[hx][2])
                    if wy - hgt - 2 >= 1:
                        row = cells[wy - hgt - 2]
                        row[hx] = ("╻", stem, row[hx][2])
            elif hh < 8:
                row = cells[wy - 1]
                row[x] = ("╿" if hh == 6 else "▏", stem, row[x][2])
        # fireflies drifting over the bank, pulsing on and off
        for fl in flies:
            g = math.sin(t * fl["sp"] * 2 + fl["ph"])
            if g < .2:
                continue
            g = round(g * 3) / 3
            x = int((fl["wx"] + 6 * math.sin(t * .3 + fl["ph"]) - cam * .8) % (w + 20)) - 10
            y = wy - 1 - int(fl["y"] + 1.2 * math.sin(t * .5 + fl["ph"] * 2))
            if 0 <= x < w and 1 <= y < wy:
                row = cells[y]
                row[x] = ("•" if g > .5 else "·", mix(cols[y], FIREFLY, g), row[x][2])
        # water: glints drifting along the surface and the rows below, sparser with depth
        srow, sb = cells[wy], cols[wy]
        glint = mix(sb, pal["hor"], .7)
        for x in range(-(icam + int(t * 2)) % 6, w, 6):
            srow[x] = ("~", glint, sb)
        for y in range(wy + 1, h):
            d = y - wy
            per, row, bg = 7 + 3 * d, cells[y], cols[y]
            fg = mix(bg, pal["hor"], .45 / d ** .5)
            for x in range(-(icam + y * 5 + int(t * (2.5 - .3 * d)) * (1 if d % 2 else -1)) % per, w, per):
                row[x] = ("─" if d % 3 else "~", fg, bg)
        # moon reflection: a shimmering column under the moon, widening with depth
        mx, mq = base["mx"], int(t * 4)
        for y in range(wy, h):
            d = y - wy
            jit = int(1.6 * math.sin(mq * .9 + y * 1.7))
            half = 1 + d // 2
            row, bg = cells[y], cols[y]
            fg = mix(bg, pal["moon"], .6 / (1 + .3 * d))
            for x in range(mx - half + jit, mx + half + jit + 1):
                if 0 <= x < w and (x * 3 + y + mq) % 4:
                    row[x] = ("━" if d else "~", fg, bg)
        # ripple rings spreading from landings, splashes and sinking pads
        for rp in st.ripples:
            age = st.t - rp["t0"]
            k, cx = age / RIPPLE_LIFE, rp["x"] - cam
            for y, rad, ch in ((wy, 1.5 + age * 8, "~"), (wy + 1, 1 + age * 6, "‿")):
                if y >= h:
                    continue
                row, bg = cells[y], cols[y]
                fg = mix(SPRAY, bg, k ** .7 / min(1.0, rp["amp"]))
                for x in (int(cx - rad), int(cx + rad)):
                    if 0 <= x < w:
                        row[x] = (ch, fg, bg)

    def draw_reeds(c):
        """Foreground silhouettes rising out of the near water, in front of everything."""
        w, h, wy, t = c.w, c.h, st.wy, st.clock
        cells = c.cells
        for x in range(w):
            wx = x + int(st.cam * 1.5)
            hh = (((wx * 2654435761) & 0xffffffff) >> 18) % 59
            if hh < 3:
                top = wy + 1 + hh - (1 if wx % 3 == 0 else 0)
                lean = 1 if math.sin(t * .7 + wx * .5) > .4 else 0
                for y in range(max(wy, top), h):
                    xx = x + (lean if y == top else 0)
                    if 0 <= xx < w:
                        row = cells[y]
                        row[xx] = ("╻" if y == top else "▐" if hh != 1 else "█", REED_FG, row[xx][2])

    def draw_pad(c, p):
        wy, sx, s = st.wy, int(round(px(p) - st.cam)), pad_state(p)
        n = 2 * p["half"] + 1
        if sx + p["half"] < 0 or sx - p["half"] >= c.w:
            return
        cols, row, x0 = st.base["cols"], c.cells[wy], sx - p["half"]
        if s == "sunk":
            fg = mix(cols[wy], SPRAY, .35)
            for x in range(max(0, x0), min(c.w, x0 + n)):
                row[x] = ("~", fg, cols[wy])
            return
        if s == "ok":
            top, body = PAD_OK
        else:
            # time into the 2 s warning; the flashing and bubbling speed up toward the sink
            sw = (st.t + p["sph"]) % p["per"] - (p["per"] - 3.2)
            top, body = PAD_WARN[int(sw * (3 + 4 * sw)) % 2]
        for i in range(n):
            x = x0 + i
            if 0 <= x < c.w:
                # lit rim on top, rounded ends
                if i == 0 or i == n - 1:
                    row[x] = ("▟" if i == 0 else "▙", body, row[x][2])
                else:
                    row[x] = ("▀", top, body)
        if wy + 1 < c.h:
            c.text(x0 + 1, wy + 1, "▀" * (n - 2), mix(cols[wy + 1], body, .45))
        if p["fl"] is not None:
            c.put(sx + p["fl"], wy - 1, "✿", LOTUS)
        if s == "warn":
            ph = 1.5 * sw + 1.6 * sw * sw
            for i in range(3 + int(sw * 1.5)):
                k = (ph + i * .73) % 2.6
                bx = x0 + 1 + (i * 3 + int((ph + i * .73) / 2.6)) % (n - 2)
                c.put(bx, wy - 1 - int(k), "o" if k < 1 else "°" if k < 2 else "·", BUBBLE)

    def draw_frog(c):
        f, wy = st.f, st.wy
        sx = int(round(f["x"] - st.cam))
        if f["mode"] == "splash":
            a = f["at"]
            sink = int(max(0.0, a - .35) * 4.5)
            cells, cw = c.cells, c.w
            for dx, dy, g, fg, bg in FROG["sad"]:
                x, y = sx + dx, wy - 1 + sink + dy
                if 0 <= x < cw and 0 <= y < wy:
                    row = cells[y]
                    row[x] = (g, fg, row[x][2] if bg is None else bg)
            # a crown of spray on both sides, then droplets falling back
            env = math.sin(math.pi * min(a / .9, 1.0))
            for side in (-1, 1):
                for i, hmax in enumerate((5.5, 3.8, 2.2)):
                    x = sx + side * (6 + i)
                    hh = int(hmax * env + .5)
                    if not 0 <= x < cw:
                        continue
                    for k in range(1, hh + 1):
                        row = cells[wy - k]
                        top = k == hh
                        row[x] = ("°" if top else "│", SPRAY if top else mix(row[x][2], SPRAY, .85),
                                  row[x][2] if top else mix(row[x][2], SPRAY, .4))
            if a < 1.0:
                for i, (dx, v) in enumerate(((-2, 5), (1, 6.5), (3, 4))):
                    y = wy - 4 - int(v * a - 6 * a * a)
                    if 1 <= y < wy:
                        c.put(sx + dx, y, "°" if i % 2 else "·", SPRAY)
            if int(a * 6) % 2 == 0:
                c.text(sx - 3, max(1, wy - 9), "SPLASH!", (236, 244, 255))
            return
        by = int(round(f["y"])) + 1  # sprite bottom row; the pad is the row below at rest
        if f["mode"] == "air":
            pose = "leap" if f["j"]["u"] < .5 else "fall"
            by += pose == "leap"  # trailing legs hang below the body
        elif f["mode"] == "meter":
            pose = "crouch" if f["p"] < .6 else "squint"
        else:
            it = st.t - f["since"]
            if it < .16:
                pose = "land"
            elif it % 3.3 > 3.16:
                pose = "blink"
            elif PUFF_AT < it % PUFF_EVERY < PUFF_AT + .5 and int((it % PUFF_EVERY) * 8) % 2:
                pose = "puff"
            else:
                pose = "idle"
        cells, cw, ch_ = c.cells, c.w, c.h
        for dx, dy, g, fg, bg in FROG[pose]:
            x, y = sx + dx, by + dy
            if 0 <= x < cw and 0 <= y < ch_:
                row = cells[y]
                row[x] = (g, fg, row[x][2] if bg is None else bg)
        tg = f.get("tongue")
        if tg and pose in MOUTH_DY and st.t - tg[0] < .22:
            # tongue flicks out to where the dragonfly was, then snaps back
            reach = math.sin(math.pi * (st.t - tg[0]) / .22)
            x0, y0 = sx, by + MOUTH_DY[pose]
            # the catch box is narrower than the frog, so always reach past its edge
            ddx, ddy = (tg[1] if abs(tg[1]) >= 7 else (7 if tg[1] >= 0 else -7)), int(round(tg[2])) + 1 - y0
            n = max(1, int(max(abs(ddx), abs(ddy)) * reach))
            steps = max(abs(ddx), abs(ddy), 1)
            ch = "━" if abs(ddx) >= 2 * abs(ddy) else "│" if abs(ddy) >= 2 * abs(ddx) else (
                "╲" if (ddx > 0) == (ddy > 0) else "╱")
            for i in range(1, n + 1):
                c.put(x0 + int(round(ddx * i / steps)), y0 + int(round(ddy * i / steps)),
                      "●" if i == n else ch, TONGUE)
        lt = st.t - f["lt"]
        if lt < .4 and f["mode"] != "air":
            # droplets flicked off the pad on landing, arcing out to both sides
            k = lt / .4
            for side in (-1, 1):
                for i, (reach, lift) in enumerate(((5, 1.6), (7, 2.2), (9, 1.2))):
                    x = sx + side * int(reach * (.45 + .55 * k))
                    y = wy - 1 - int(lift * 4 * k * (1 - k) + .5)
                    c.put(x, y, "°" if i == 1 else "·", DROPLET if k < .7 else DROPLET_DIM)

    def draw_bug(c, b):
        sx, y = int(round(b["x"] - st.cam)), int(round(b["y"]))
        cells, cw, cols = c.cells, c.w, st.base["cols"]
        if not 0 <= y < st.wy:
            return
        flap = int(st.clock * 14 + b["ph"]) % 2
        shine = int(st.clock * 6 + b["ph"]) % 9  # a glint sliding along the wings
        for wy_, wings in ((y, DFLY_WINGS[flap][0]), (y + 2, DFLY_WINGS[flap][1])):
            if not 0 <= wy_ < st.wy:
                continue
            row = cells[wy_]
            for i, ch in enumerate(wings):
                x = sx - 3 + i
                if ch != " " and 0 <= x < cw:
                    bg = row[x][2]
                    row[x] = (ch, mix(bg, DFLY_WING, .8 if i == shine else .45), bg)
        if y + 1 >= st.wy:
            return
        row = cells[y + 1]
        body = [(-3, "●", DFLY_EYE), (-2, "▆", DFLY_THORAX)] + [
            (dx, "━", hue(st.clock * .25 + b["ph"] + dx * .09)) for dx in range(-1, 3)] + [(3, "╸", hue(st.clock * .25 + b["ph"] + .3))]
        for dx, ch, fg in body:
            x = sx + dx
            if 0 <= x < cw:
                row[x] = (ch, fg, row[x][2])

    def hud(c):
        wy, f = st.wy, st.f
        c.text(1, 0, f"froghop  score {st.score}  best {st.best}", 231)
        lv = "".join("<3 " if i < st.lives else "   " for i in range(LIVES))
        c.text(c.w - len(lv) - 1, 0, lv, 203)
        if f["mode"] == "meter":
            p, bw = f["p"], 24
            col = 46 if p < .45 else (226 if p < .8 else 196)
            fill = int(p * bw)
            c.text(1, c.h - 1, "power [" + "#" * fill + ">" * (fill < bw) + " " * (bw - fill - 1) + "]", col)
            lx = f["x"] + MIN_D + p * (MAX_D - MIN_D)
            c.put(int(round(lx - st.cam)), wy + 1, "^", 226)
            c.put(int(round(lx - st.cam)), wy + 2, "|", 226)
        elif f["mode"] == "idle":
            c.text(1, c.h - 1, "SPACE: charge the leap", 250)
        elif f["mode"] == "air":
            c.text(1, c.h - 1, "catch a dragonfly!", 250)

    def box(c, lines, y0, colors=None):
        bw = max(len(s) for s in lines) + 4
        x0 = (c.w - bw) // 2
        for i, s in enumerate(lines):
            c.text(x0, y0 + i, " " * bw, 231, 0)
            c.text(x0 + 2, y0 + i, s, (colors or {}).get(i, 252), 0)

    def banner(c):
        if st.done and st.banner > 0:
            msg = " Claude's done! "
            center(c, 2, msg, 16, 229 if int(st.banner * 3) % 2 else 222)

    def too_small(c, keys):
        c.clear()
        lines = textwrap.wrap(MSG_SMALL, max(1, c.w)) or [""]
        for i, s in enumerate(lines[:c.h]):
            c.text(max(0, (c.w - len(s)) // 2), max(0, (c.h - len(lines)) // 2) + i, s[:c.w], 226)
        return "q" in keys

    def step(c, frame, keys):
        if frame % 10 == 0 and not st.done and game.claude_done():
            st.done, st.banner = True, 8.0
        if st.banner > 0:
            st.banner -= dt
        if c.w < MIN_W or c.h < MIN_H:
            return too_small(c, keys)
        if "q" in keys:
            return True
        st.w, st.wy = c.w, c.h - 5
        st.clock += dt
        if demo:
            if st.mode == "title":
                keys = ["space"]
            elif st.mode == "over":
                keys = ["r"] if st.over_t > 2 else []
            else:
                keys = bot()
        if not hasattr(st, "f"):
            reset()
        if st.mode == "title":
            if "space" in keys:
                reset()
                st.mode = "play"
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
        draw_scene(c)
        for p in st.pads:
            draw_pad(c, p)
        for b in st.bugs:
            draw_bug(c, b)
        draw_frog(c)
        draw_reeds(c)
        for fl in st.floats:
            c.text(int(fl["x"] - st.cam) - 2, int(fl["y"]), fl["txt"], fl["col"])
        hud(c)
        if st.mode == "title":
            box(c, ["F R O G H O P", "", "SPACE  start the power meter",
                    "SPACE again  leap (more power = farther)",
                    "land on pads, snap dragonflies mid-leap",
                    "bubbling pads are about to sink!", "",
                    "p pause   q quit   r restart", "", "press SPACE to begin"],
                2, {0: 120, 9: 226})
        elif st.paused:
            box(c, ["PAUSED", "p to resume"], c.h // 2 - 3, {0: 226})
        elif st.mode == "over":
            lines = ["GAME OVER", "", f"score {st.score}", f"best  {st.best}"]
            if st.newbest:
                lines.append("new best!")
            lines += ["", "r again   q quit"]
            box(c, lines, 3, {0: 203, 4: 226})
        banner(c)
        return False

    return game.play(args, step, music="froghop")


if __name__ == "__main__":
    raise SystemExit(main())
