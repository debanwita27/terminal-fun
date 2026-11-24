#!/usr/bin/env python3
"""Check the diff renderer against the full-redraw renderer, and the focus pause.

Usage: tools/test_render.py [--frames 1,9,60] [NAME ...]

Every seeded piece runs twice under a pty (CLAUDE_FUN_FULL_REDRAW=1 and the default
diff path); both byte streams are replayed into a tiny virtual screen and the final
screens must match cell for cell, colours included.
"""
import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
from bench import EXTRA, has_flag, pieces, run_pty  # noqa: E402

COLS, ROWS = 120, 40
TOKEN = re.compile(r"\x1b\[([?]?)([0-9;]*)([A-Za-z])|(.)", re.S)


def replay(data, cols=COLS, rows=ROWS):
    """Final screen as rows of (ch, fg, bg) after interpreting CUP, SGR, ED and text."""
    blank = (" ", None, None)
    scr = [[blank] * cols for _ in range(rows)]
    x = y = 0
    fg = bg = None
    pending_wrap = False
    for m in TOKEN.finditer(data.decode("utf-8", "replace")):
        priv, params, final, ch = m.groups()
        if ch is not None:
            if ch == "\x1b" or ord(ch) < 0x20:
                continue
            if pending_wrap:
                x, y, pending_wrap = 0, min(y + 1, rows - 1), False
            scr[y][x] = (ch, fg, bg)
            if x == cols - 1:
                pending_wrap = True
            else:
                x += 1
            continue
        if priv:
            continue
        nums = [int(n) if n else 0 for n in params.split(";")] if params else []
        if final == "H":
            y = min(max((nums[0] if nums else 1) or 1, 1), rows) - 1
            x = min(max((nums[1] if len(nums) > 1 else 1) or 1, 1), cols) - 1
            pending_wrap = False
        elif final == "J" and nums == [2]:
            scr = [[(" ", None, bg)] * cols for _ in range(rows)]
        elif final == "m":
            nums = nums or [0]
            i = 0
            while i < len(nums):
                n = nums[i]
                if n == 0:
                    fg = bg = None
                elif n == 39:
                    fg = None
                elif n == 49:
                    bg = None
                elif n in (38, 48) and i + 2 < len(nums) and nums[i + 1] == 5:
                    if n == 38:
                        fg = nums[i + 2]
                    else:
                        bg = nums[i + 2]
                    i += 2
                elif n in (38, 48) and i + 4 < len(nums) and nums[i + 1] == 2:
                    if n == 38:
                        fg = tuple(nums[i + 2:i + 5])
                    else:
                        bg = tuple(nums[i + 2:i + 5])
                    i += 4
                i += 1
    return scr


def frame_bodies(data):
    """Bytes inside the alt screen, before the exit sequence restores the main screen."""
    start = data.find(b"\x1b[?1049h")
    end = data.rfind(b"\x1b[?1049l")
    return data[start:end if end > 0 else len(data)]


def run_piece(path, extra, frames, full, no_color=False):
    argv = [sys.executable, path, "--frames", str(frames), "--fps", "100", *extra]
    env = dict(os.environ, PYTHONHASHSEED="0")
    env.pop("COLUMNS", None)
    env.pop("LINES", None)
    env.pop("NO_COLOR", None)
    if full:
        env["CLAUDE_FUN_FULL_REDRAW"] = "1"
    if no_color:
        env["NO_COLOR"] = "1"
    status, _, out, _ = run_pty(argv, COLS, ROWS, env)
    return os.waitstatus_to_exitcode(status), frame_bodies(out)


def first_diff(a, b):
    for y, (ra, rb) in enumerate(zip(a, b)):
        for x, (ca, cb) in enumerate(zip(ra, rb)):
            if ca != cb:
                return f"first mismatch at col {x + 1}, row {y + 1}: full={ca} diff={cb}"
    return "same"


def test_equivalence(names, frame_counts):
    failures = 0
    for name, _, path in pieces():
        if names and name not in names:
            continue
        if not has_flag(path, "--seed"):
            continue
        extra = ["--seed", "7", *EXTRA.get(name, [])]
        for n in frame_counts:
            for no_color in (False, True) if n == frame_counts[-1] else (False,):
                rc1, full = run_piece(path, extra, n, True, no_color)
                rc2, diff = run_piece(path, extra, n, False, no_color)
                same = replay(full) == replay(diff)
                tag = f"{name} frames={n}{' NO_COLOR' if no_color else ''}"
                ratio = len(diff) / max(1, len(full))
                if rc1 or rc2 or not same:
                    failures += 1
                    print(f"FAIL {tag}: exit {rc1}/{rc2}, {first_diff(replay(full), replay(diff))}")
                else:
                    print(f"ok   {tag}: diff stream is {ratio:.0%} of full ({len(diff)}/{len(full)} bytes)")
    return failures


def test_focus_pause():
    """Focus-out must cut output to near zero; focus-in must bring it back."""
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))),
                        "watch", "fireworks.py")
    marks = {}

    def feed(fd, t, out):
        if "out" not in marks and t > 2.0:
            os.write(fd, b"\x1b[O")
            marks["out"] = len(out)
        elif "settled" not in marks and t > 2.5:
            marks["settled"] = len(out)
        elif "in" not in marks and t > 5.5:
            marks["in"] = len(out)
            os.write(fd, b"\x1b[I")
        elif "end" not in marks and t > 7.5:
            marks["end"] = len(out)
            os.kill(marks["pid"], 2)

    env = dict(os.environ)
    env.pop("CLAUDE_FUN_NO_FOCUS_PAUSE", None)
    import pty as _pty
    real_fork = _pty.fork

    def fork():
        pid, fd = real_fork()
        marks["pid"] = pid
        return pid, fd
    _pty.fork = fork
    try:
        status, _, out, wall = run_pty([sys.executable, path, "--seed", "3"] if has_flag(path, "--seed")
                                       else [sys.executable, path], COLS, ROWS, env, feed, timeout=20)
    finally:
        _pty.fork = real_fork
    focused_rate = marks["out"] / 2.0
    paused_rate = (marks["in"] - marks["settled"]) / 3.0
    resumed_rate = (marks["end"] - marks["in"]) / 2.0
    enabled = b"\x1b[?1004h" in out and b"\x1b[?1004l" in out
    print(f"focus: focused {focused_rate / 1024:.1f} KB/s, unfocused {paused_rate / 1024:.2f} KB/s, "
          f"refocused {resumed_rate / 1024:.1f} KB/s, 1004h/l emitted: {enabled}")
    # The first 2s can be a near-empty sky, so the paused rate is judged against both windows.
    ok = enabled and paused_rate < max(focused_rate, resumed_rate) * 0.1 \
        and resumed_rate > focused_rate * 0.5
    print("ok   focus pause" if ok else "FAIL focus pause")
    return 0 if ok else 1


def test_tuple_colours():
    """rgb-tuple colours (mixed with ints and None) through render and render_diff: the same
    final screen either way, 24-bit SGR under TRUECOLOR, nearest 256-colour entries otherwise,
    and no SGR at all without COLOR."""
    import random
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
    from fun import term
    saved = term.TRUECOLOR, term.COLOR
    failures = 0
    try:
        for truecolor, color in ((True, True), (False, True), (True, False)):
            term.TRUECOLOR, term.COLOR = truecolor, color
            term._sgr_cache.clear()
            rng = random.Random(5)
            pool = [None, 196, 231, (255, 84, 168), (64, 130, 255), (12, 12, 20), (250, 250, 250)]
            c = term.Canvas()
            c.w, c.h, c._prev = 30, 8, None
            full = diff = ""
            for _ in range(12):
                c.clear()
                for _ in range(90):
                    c.put(rng.randrange(c.w), rng.randrange(c.h), rng.choice("*.⠿ "),
                          rng.choice(pool), rng.choice(pool))
                full += c.render()
                diff += c.render_diff()
                c._prev = [row[:] for row in c.cells]

            def want(col):
                if not color or col is None or isinstance(col, int):
                    return col if color else None
                return col if truecolor else term._nearest(col)
            expect = [[(ch, want(fg), want(bg)) for ch, fg, bg in row] for row in c.cells]
            a, b = replay(full.encode(), c.w, c.h), replay(diff.encode(), c.w, c.h)
            tag = f"tuple colours truecolor={truecolor} color={color}"
            ok = a == b == expect and (truecolor or "38;2" not in diff) and (color or not re.search("\x1b\\[[0-9;]*m", full + diff))
            if ok:
                print(f"ok   {tag}")
            else:
                failures += 1
                print(f"FAIL {tag}: full/diff {first_diff(a, b)}, full/expected {first_diff(a, expect)}")
    finally:
        term.TRUECOLOR, term.COLOR = saved
        term._sgr_cache.clear()
    return failures


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--frames", default="1,9,60", help="comma-separated frame counts")
    p.add_argument("--no-focus", action="store_true", help="skip the focus pause test")
    p.add_argument("names", nargs="*")
    args = p.parse_args()
    failures = test_tuple_colours()
    failures += test_equivalence(args.names, [int(n) for n in args.frames.split(",")])
    if not args.no_focus:
        failures += test_focus_pause()
    print("all passed" if not failures else f"{failures} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
