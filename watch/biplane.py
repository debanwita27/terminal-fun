#!/usr/bin/env python3
"""Biplane: an ASCII biplane tows a banner past drifting clouds and the odd bird.

Usage: python3 biplane.py [--fps 20] [--frames N] [--text "hello"]
Banner text: --text, else the Claude status file (see fun/term.py), else a random dev quip.
"""

META = {'name': 'biplane',
 'kind': 'watch',
 'blurb': 'A biplane tows a banner past drifting clouds and birds',
 'credit': {'type': 'inspired by',
            'who': 'sl by Toyoda Masashi',
            'url': 'https://github.com/mtoyoda/sl'}}

import math
import random

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

from fun import term

QUIPS = [
    "it works on my machine", "reticulating splines", "have you tried turning it off and on",
    "works in prod, trust me", "TODO: fix later", "git blame says it was you",
    "there are only two hard things", "off by one, again", "it's always DNS",
    "semicolon found, crisis averted", "compiling... (go get coffee)",
    "no tests, no problems", "ship it on friday", "// here be dragons",
    "undefined is not a function", "rm -rf node_modules and pray",
    "one more small refactor", "the cache is lying to you", "merge conflict in my heart",
    "stack overflow, my old friend", "sudo make me a sandwich", "it's not a bug, it's a feature",
    "localhost:3000 is my happy place", "lgtm, did not read",
]

PLANE = [
    "   ==========     ",
    "    |/    |/      ",
    " ~=[_o_____o_]=@  ",
    "      ' '  ' '    ",
]
PROP = "|/-\\"
CLOUD_SHAPES = [
    [" .--.  ", "(    ) ", " `--'  "],
    ["  .-~~-.  ", " (      ) ", "(_.-~~-._)"],
]


def banner_text(args, last):
    if args.text:
        return args.text
    st = term.read_status()
    if st:
        tool = st.get("tool")
        return {"working": f"Claude is running {tool}..." if tool else "Claude is working...",
                "done": "Claude is done!", "idle": "Claude is waiting for you"
                }.get(st.get("state"), "Claude is around")
    return random.choice([q for q in QUIPS if q != last])


def make_cloud(w, h, start=False):
    layer = random.choice([0.25, 0.5, 1.0])  # slower layers sit higher and dimmer
    shape = random.choice(CLOUD_SHAPES)
    x = random.uniform(0, w) if start else w + random.uniform(0, 10)
    return {"x": x, "y": random.uniform(0, max(1, h * 0.7)) * (0.5 + layer / 2),
            "v": 2 + 6 * layer, "shape": shape, "col": {0.25: 240, 0.5: 247, 1.0: 255}[layer]}


def main():
    parser = term.make_parser(__doc__.splitlines()[0])
    parser.add_argument("--text", help="banner text")
    args = parser.parse_args()
    dt = 1 / max(1.0, args.fps)
    st = {"x": None, "text": None, "clouds": None, "bird": None, "t": 0.0}

    def step(c, frame):
        st["t"] += dt
        t = st["t"]
        if st["clouds"] is None:
            st["clouds"] = [make_cloud(c.w, c.h, True) for _ in range(max(2, c.w // 18))]
        if st["text"] is None:
            st["text"] = banner_text(args, None)
        text = st["text"]
        banner_w = len(text) + 4
        plane_w = len(PLANE[0])
        total = banner_w + 6 + plane_w

        if st["x"] is None:
            st["x"] = -total
        st["x"] += 14 * dt
        if st["x"] > c.w:  # pass finished: new quip, back to the left
            st["x"] = -total
            st["text"] = banner_text(args, text)

        for cl in st["clouds"]:
            cl["x"] -= cl["v"] * dt
            if cl["x"] < -12:
                cl.update(make_cloud(c.w, c.h))
            for i, line in enumerate(cl["shape"]):
                c.text(cl["x"], cl["y"] + i, line, cl["col"])

        b = st["bird"]
        if b is None and random.random() < 0.6 * dt:
            st["bird"] = b = {"x": c.w + 2.0, "y": random.uniform(1, max(2, c.h * 0.6)),
                              "v": random.uniform(8, 14), "dy": random.uniform(-1, 1)}
        if b:
            b["x"] -= b["v"] * dt
            b["y"] += b["dy"] * dt
            c.put(b["x"], b["y"], "v" if int(t * 6) % 2 else "^", 250)
            if b["x"] < -2:
                st["bird"] = None

        py = int(c.h * 0.4 + math.sin(t * 1.5) * 1.5)
        px = int(st["x"]) + banner_w + 6
        for i, line in enumerate(PLANE):
            c.text(px, py + i, line, 214 if i == 2 else 178)
        c.put(px + plane_w - 1, py + 2, PROP[frame % 4], 231)

        bx, by = px - 6, py + 2
        c.text(bx, by, "~~~~~~", 245)  # tow rope
        x0 = bx - banner_w
        c.text(x0, by - 1, "," + "-" * (banner_w - 2) + ",", 196)
        c.text(x0, by, "| " + text + " |", 231)
        c.text(x0, by + 1, "`" + "-" * (banner_w - 2) + "'", 196)

    return term.run(args, step, music="default")


if __name__ == "__main__":
    raise SystemExit(main())
