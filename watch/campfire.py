#!/usr/bin/env python3
"""Campfire: heat-diffusion flames over a log pile, sparks, and a twinkling night sky.

Usage: python3 campfire.py [--fps 12] [--frames N]
Burns higher and throws more sparks while the Claude status file says "working".
"""

META = {'name': 'campfire',
 'kind': 'watch',
 'blurb': 'Heat-diffusion flames over logs, sparks and a starry sky',
 'credit': {'type': 'inspired by',
            'who': "Lode Vandevenne's fire effect tutorial",
            'url': 'https://lodev.org/cgtutor/fire.html'}}

import random

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

from fun import term

RAMP = " .:-=+*#%@"
COLORS = [0, 52, 88, 124, 160, 196, 202, 208, 214, 220, 226, 229]
LOGS = [
    r"   _.-=======-._   ",
    r" (_)=[=======]=(_) ",
    r"  `-=[_______]=-'  ",
]
STAR_CH = ".*+'`"


def step_fn():
    st = {"heat": [], "fw": 0, "fh": 0, "sparks": [], "stars": [], "dim": None, "power": 0.5}

    def step(c, frame):
        w, h = c.w, c.h
        status = term.read_status() if frame % 10 == 0 else None
        if frame % 10 == 0:
            st["working"] = bool(status and status.get("state") == "working")
        target = 1.0 if st.get("working") else 0.5
        st["power"] += (target - st["power"]) * 0.08
        power = st["power"]

        if st["dim"] != (w, h):
            st["dim"] = (w, h)
            st["stars"] = [[random.randrange(w), random.randrange(max(1, h * 2 // 3)),
                            random.choice(STAR_CH), random.random() * 6.28]
                           for _ in range(max(1, w * h // 40))]
            st["sparks"] = []
            st["heat"] = []

        for sx, sy, ch, ph in st["stars"]:
            tw = (frame * 0.05 + ph) % 6.28
            if tw < 0.9:
                c.put(sx, sy, "+" if tw < 0.45 else ".", 231)
            else:
                c.put(sx, sy, ch, 244 if ch in ".'`" else 250)

        # Fire field sits above the logs; its height scales with power.
        log_h = min(len(LOGS), max(1, h // 4))
        base = h - log_h
        fw = max(1, min(w - 2, 26))
        fh = max(1, int(min(base, h * 0.75) * (0.55 + 0.45 * power)))
        if (fw, fh) != (st["fw"], st["fh"]):
            st["fw"], st["fh"] = fw, fh
            st["heat"] = [[0.0] * fw for _ in range(fh + 1)]
        heat = st["heat"]
        # Row fh is the fuel bed; rows above diffuse upward with cooling.
        for x in range(fw):
            edge = 1 - abs(x - (fw - 1) / 2) / (fw / 2 + 0.01)
            heat[fh][x] = min(1.0, random.random() * 0.5 + 0.55 * edge + 0.15 * power)
        cool = 1.9 / (fh + 1) + 0.01
        for y in range(fh):
            below, row = heat[y + 1], heat[y]
            for x in range(fw):
                a = below[x] * 2 + below[x - 1 if x else 0] + below[x + 1 if x < fw - 1 else fw - 1]
                row[x] = max(0.0, a / 4 - random.random() * cool)

        fx = (w - fw) // 2
        for y in range(fh):
            for x in range(fw):
                v = heat[y][x]
                if v > 0.04:
                    i = min(len(RAMP) - 1, int(v * len(RAMP)))
                    col = COLORS[min(len(COLORS) - 1, int(v * len(COLORS)))]
                    c.put(fx + x, base - fh + y, RAMP[i], col)

        lx = (w - len(LOGS[0])) // 2
        for i in range(log_h):
            c.text(lx, base + i, LOGS[i + len(LOGS) - log_h], 94 if i < 2 else 58)

        # Sparks: born in the flame, drift up with sideways wobble, then fade.
        if random.random() < 0.25 + 0.7 * power * power and base > 1:
            st["sparks"].append({"x": fx + random.uniform(fw * 0.25, fw * 0.75),
                                 "y": float(base - fh // 2), "vy": random.uniform(0.3, 0.9) * (0.7 + power),
                                 "vx": random.uniform(-0.25, 0.25), "life": random.randint(15, 40)})
        alive = []
        for s in st["sparks"]:
            s["x"] += s["vx"] + random.uniform(-0.2, 0.2)
            s["y"] -= s["vy"]
            s["life"] -= 1
            if s["life"] > 0 and s["y"] >= 0:
                col = 226 if s["life"] > 25 else 208 if s["life"] > 12 else 160
                c.put(s["x"], s["y"], "*" if s["life"] > 20 else "'" if s["life"] > 8 else ".", col)
                alive.append(s)
        st["sparks"] = alive[-120:]

    return step


def main():
    parser = term.make_parser(__doc__.splitlines()[0], fps=12)
    args = parser.parse_args()
    return term.run(args, step_fn(), music="campfire")


if __name__ == "__main__":
    raise SystemExit(main())
