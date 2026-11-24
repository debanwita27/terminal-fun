#!/usr/bin/env python3
"""Excuses: a 3-reel slot machine that spins up a dev excuse, or (--progress) a
deadpan progress bar that stalls, reverses and lies about being done.

Usage: python3 excuses.py [--fps 20] [--frames N] [--progress]
"""

META = {"name": "excuses", "kind": "watch", "blurb": "A slot machine of dev excuses, or a progress bar that lies",
        "credit": None,
        "variants": {"excuses-progress": ["--progress"]}}

import random

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

from fun import term

SUBJECTS = ["the cache", "DNS", "a race condition", "Mercury in retrograde", "the load balancer",
            "a stale lockfile", "timezones", "cosmic rays", "legacy code", "a rogue semicolon",
            "YAML indentation", "a floating point error", "the monorepo", "a misplaced comma",
            "npm"]
VERBS = ["is flaky on", "only breaks on", "was fine in", "never fails on", "is haunted by",
         "has opinions about", "timed out on", "ghosted us on", "only reproduces on",
         "got lost in", "is allergic to", "was never tested on", "works great on"]
CONTEXTS = ["Fridays", "staging", "my machine", "prod at 3am", "a full moon", "the demo",
            "Monday morning", "Node 14", "the CI runners", "a Tuesday", "Docker Desktop",
            "leap years", "the VPN", "the third retry"]
REELS = [SUBJECTS, VERBS, CONTEXTS]

STAGES = ["Reticulating splines", "Aligning chakras of the build cache", "Calibrating the flux compiler",
          "Negotiating with the linter", "Warming up the hamsters", "Defragmenting the semicolons",
          "Convincing the tests to pass", "Untangling dependency spaghetti", "Polishing the bits",
          "Consulting the rubber duck", "Buffering the buffer", "Bribing the garbage collector",
          "Downloading more RAM", "Reversing the polarity", "Asking Stack Overflow nicely"]
BACKWARDS = ["Un-reticulating splines", "Rolling back optimism", "Reconsidering everything",
             "Re-tangling the dependencies"]
STALLS = ["Finalising the finalisation", "Waiting for the last 1%", "Still 99%, hang tight",
          "Any second now", "Counting to 100 again"]

HOLD_SECONDS = 3.0
FLASH_FRAMES = 6


def ease_out(u):
    return 1 - (1 - u) ** 3


def slot_machine(args):
    dt = 1 / max(1.0, args.fps)
    dur = [int((1.4 + 0.9 * i) / dt) for i in range(3)]
    hold = int(HOLD_SECONDS / dt)
    s = {"t": 0, "start": [random.randrange(len(r)) for r in REELS], "travel": None}

    def new_round():
        s["start"] = [(a + t) % len(r) for a, t, r in zip(s["start"], s["travel"], REELS)] \
            if s["travel"] else s["start"]
        s["travel"] = [len(r) * 2 + random.randrange(len(r)) for r in REELS]
        s["t"] = 0

    new_round()

    def step(c, frame):
        w, h = c.w, c.h
        if s["t"] >= dur[2] + hold:
            new_round()
        t = s["t"]
        s["t"] += 1
        compact = h < 8
        rw = [max(len(e) for e in r) + 2 for r in REELS]
        if sum(rw) + 12 > w:
            rw = [max(1, (w - 8) // 3)] * 3
        x0 = max(0, (w - (sum(rw) + 3 * 2 + 2)) // 2)
        cy = h // 2 - (1 if compact else 0)
        words = []
        for i, reel in enumerate(REELS):
            u = min(1.0, t / dur[i])
            pos = s["start"][i] + s["travel"][i] * ease_out(u)
            speed = s["travel"][i] * 3 * (1 - u) ** 2 / dur[i]
            stopped = u >= 1.0
            idx = round(pos) % len(reel)
            words.append(reel[idx])
            x = x0 + sum(r + 3 for r in rw[:i])
            flash = stopped and t - dur[i] < FLASH_FRAMES
            frame_col = 231 if flash else 94
            for dy in (-1, 0, 1):
                if compact and dy:
                    continue
                txt = reel[(idx + dy) % len(reel)][:rw[i]].center(rw[i])
                if stopped:
                    col = 226 if dy == 0 else 240
                else:
                    col = 244 if speed > 0.8 else (250 if dy == 0 else 240)
                    if speed > 0.8:
                        txt = random.choice(reel)[:rw[i]].center(rw[i])
                if not compact:
                    c.put(x, cy + dy, "│", frame_col)
                    c.put(x + rw[i] + 1, cy + dy, "│", frame_col)
                c.text(x + 1, cy + dy, txt, col)
            if not compact:
                c.text(x, cy - 2, "┌" + "─" * rw[i] + "┐", frame_col)
                c.text(x, cy + 2, "└" + "─" * rw[i] + "┘", frame_col)
        if not compact:
            c.text(max(0, (w - 20) // 2), cy - 4, "== EXCUSE-O-MATIC ==", 178)
        done = t >= dur[2]
        msg = " ".join(words) + "." if done else "spinning" + "." * (frame // 4 % 4)
        c.text(max(0, (w - len(msg)) // 2), cy + (4 if not compact else 2), msg,
               (51 if (frame // 5) % 2 else 231) if done and t - dur[2] < 20 else 214 if done else 244)

    return step


def progress_script(fps):
    """Yields (percent, label, note) once per frame, forever."""
    def ramp(p0, p1, secs, label, note=""):
        n = max(1, int(secs * fps))
        for i in range(1, n + 1):
            yield p0 + (p1 - p0) * (i / n) + random.uniform(-0.3, 0.3) * (i < n), label, note

    def wait(p, secs, labels, note=""):
        n = max(1, int(secs * fps))
        per = max(1, n // len(labels))
        for i in range(n):
            yield p, labels[min(len(labels) - 1, i // per)], note

    while True:
        stages = random.sample(STAGES, len(STAGES))
        p = 0.0
        yield from wait(p, 1.0, ["Initialising initialisation"])
        for target in (random.uniform(25, 40), random.uniform(55, 75)):
            yield from ramp(p, target, random.uniform(3, 6), stages.pop())
            p = target
            if random.random() < 0.5:
                back = max(0.0, p - random.uniform(8, 22))
                yield from ramp(p, back, random.uniform(1, 2), random.choice(BACKWARDS), "(this is fine)")
                p = back
        if random.random() < 0.6:
            yield from ramp(p, 100, 1.0, stages.pop())
            yield from wait(100, 1.5, ["Done!"])
            yield from wait(100, 1.5, ["just kidding"], "(that was a different 100%)")
            yield from ramp(100, 62, 0.8, "Reconsidering")
            p = 62.0
        yield from ramp(p, 99, random.uniform(4, 7), stages.pop())
        yield from wait(99, random.uniform(5, 8), random.sample(STALLS, 3), "ETA: soon")
        yield from ramp(99, 100, 0.3, "Complete")
        yield from wait(100, 3.0, ["Complete (probably)"])


def progress_bar(args):
    gen = progress_script(max(1.0, args.fps))

    def step(c, frame):
        p, label, note = next(gen)
        w, h = c.w, c.h
        bw = max(1, min(40, w - 10))
        pct = int(min(100, max(0, p)))
        filled = int(bw * pct / 100)
        bar = "█" * filled + "░" * (bw - filled)
        y0 = max(0, (h - 5) // 2)
        rows = ({"title": y0, "bar": y0 + 2, "label": y0 + 3, "note": y0 + 4} if h >= 5
                else {"title": -1, "bar": 0, "label": 1, "note": 2})
        x0 = max(0, (w - (bw + 8)) // 2)
        spin = "|/-\\"[frame // 2 % 4]
        c.text(max(0, (w - 14) // 2), rows["title"], "Build progress", 178)
        c.text(x0, rows["bar"], bar + f" {pct:3d}%", 46 if pct < 100 else 51)
        c.text(x0, rows["label"], f"{spin} {label}", 231)
        c.text(x0, rows["note"], note, 244)

    return step


def main():
    parser = term.make_parser(__doc__.splitlines()[0])
    parser.add_argument("--progress", action="store_true", help="deadpan progress bar mode")
    args = parser.parse_args()
    return term.run(args, progress_bar(args) if args.progress else slot_machine(args),
                    music="default")


if __name__ == "__main__":
    raise SystemExit(main())
