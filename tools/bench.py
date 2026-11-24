#!/usr/bin/env python3
"""Benchmark every piece under a pty: child CPU time and bytes written per frame.

Usage: tools/bench.py [--cols 120] [--rows 40] [--frames 200] [-j 4] [NAME ...]

Each piece runs at its default fps for --frames frames. CPU is the child's
user+sys from os.wait4 (includes interpreter start-up, amortised over the run).
Run with CLAUDE_FUN_FULL_REDRAW=1 to measure the old full-repaint renderer.
"""
import argparse
import ast
import fcntl
import os
import pty
import struct
import sys
import termios
import time
from concurrent.futures import ProcessPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))

# Flags that get games past their title screen into real gameplay rendering.
EXTRA = {
    "bugsquash": ["--start"],
    "catstack": ["--start"],
    "froghop": ["--demo"],
    "ducklings": ["--demo"],
    "typewriter": ["--auto"],
    "bullethell": ["--demo"],
}


def pieces():
    out = []
    for kind in ("watch", "play"):
        d = os.path.join(ROOT, kind)
        for fn in sorted(os.listdir(d)):
            if fn.endswith(".py"):
                out.append((fn[:-3], kind, os.path.join(d, fn)))
    return out


def has_flag(path, flag):
    with open(path) as f:
        tree = ast.parse(f.read(), path)
    return any(isinstance(n, ast.Constant) and n.value == flag for n in ast.walk(tree))


def run_pty(argv, cols, rows, env=None, stdin_feed=None, timeout=120):
    """Run argv under a pty; returns (exit_status, rusage, output_bytes, wall_seconds).

    stdin_feed: optional callable(master_fd, elapsed, total_bytes) called between reads,
    used by tests to type into the pty.
    """
    env = dict(os.environ if env is None else env)
    # Games default to sound on; tooling must never play audio unless a test opts in.
    env.setdefault("CLAUDE_FUN_SOUND", "0")
    t0 = time.monotonic()
    pid, fd = pty.fork()
    if pid == 0:
        try:
            fcntl.ioctl(0, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
            os.execve(argv[0], argv, env)
        finally:
            os._exit(127)
    out = bytearray()
    import select
    while True:
        if time.monotonic() - t0 > timeout:
            os.kill(pid, 9)
        r, _, _ = select.select([fd], [], [], 0.05)
        if stdin_feed:
            stdin_feed(fd, time.monotonic() - t0, out)
        if r:
            try:
                chunk = os.read(fd, 65536)
            except OSError:
                break
            if not chunk:
                break
            out += chunk
    _, status, ru = os.wait4(pid, 0)
    os.close(fd)
    return status, ru, bytes(out), time.monotonic() - t0


def bench_one(piece, args):
    name, kind, path = piece
    argv = [sys.executable, path, "--frames", str(args.frames), *EXTRA.get(name, [])]
    if has_flag(path, "--seed"):
        argv += ["--seed", "1"]
    env = dict(os.environ)
    env.pop("COLUMNS", None)
    env.pop("LINES", None)
    status, ru, out, wall = run_pty(argv, args.cols, args.rows, env)
    cpu = ru.ru_utime + ru.ru_stime
    return {
        "name": name, "kind": kind, "status": os.waitstatus_to_exitcode(status),
        "cpu_ms": cpu * 1000 / args.frames, "kb": len(out) / 1024 / args.frames,
        "wall": wall, "pct": cpu * 100 / wall, "args": " ".join(argv[3:]),
    }


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--cols", type=int, default=120)
    p.add_argument("--rows", type=int, default=40)
    p.add_argument("--frames", type=int, default=200)
    p.add_argument("-j", "--jobs", type=int, default=4, help="pieces benchmarked in parallel")
    p.add_argument("names", nargs="*", help="only these pieces")
    args = p.parse_args()
    todo = [pc for pc in pieces() if not args.names or pc[0] in args.names]
    with ProcessPoolExecutor(args.jobs) as ex:
        rows = list(ex.map(bench_one, todo, [args] * len(todo)))
    rows.sort(key=lambda r: -r["cpu_ms"])
    print(f"# {time.strftime('%Y-%m-%d %H:%M')}  {args.cols}x{args.rows}, {args.frames} frames, "
          f"default fps, python {sys.version.split()[0]}")
    print(f"{'piece':<12} {'kind':<6} {'cpu ms/frame':>12} {'KB/frame':>9} {'cpu %':>6} "
          f"{'wall s':>7} {'exit':>4}  extra args")
    for r in rows:
        print(f"{r['name']:<12} {r['kind']:<6} {r['cpu_ms']:>12.2f} {r['kb']:>9.2f} {r['pct']:>6.1f} "
              f"{r['wall']:>7.1f} {r['status']:>4}  {r['args']}")
    print(f"{'TOTAL':<12} {'':<6} {sum(r['cpu_ms'] for r in rows):>12.2f} "
          f"{sum(r['kb'] for r in rows):>9.2f} {sum(r['pct'] for r in rows):>6.1f} "
          f"{sum(r['wall'] for r in rows):>7.1f}")
    print("cpu % = child user+sys over wall time, including start-up; wall is noisy on a busy machine")
    return 1 if any(r["status"] for r in rows) else 0


if __name__ == "__main__":
    sys.exit(main())
