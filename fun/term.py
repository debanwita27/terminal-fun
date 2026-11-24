"""Shared terminal helpers: alt screen, canvas, frame loop, status file.

Plain ANSI escapes, stdlib only. Typical use:

    parser = term.make_parser("my animation")
    args = parser.parse_args()
    term.run(args, step)        # step(canvas, frame) -> True to stop early
"""
import argparse
import contextlib
import json
import os
import select
import shutil
import signal
import sys
import time

from fun import audio

COLOR = "NO_COLOR" not in os.environ
# Colours are 256-colour ints or (r, g, b) tuples; tuples go out as 24-bit SGR only when
# the terminal advertises it, otherwise as their nearest 256-colour entry.
TRUECOLOR = os.environ.get("COLORTERM", "").lower() in ("truecolor", "24bit")
# Hidden switch: repaint every cell each frame (used to test the diff renderer).
FULL_REDRAW = os.environ.get("CLAUDE_FUN_FULL_REDRAW") == "1"
FOCUS_PAUSE = os.environ.get("CLAUDE_FUN_NO_FOCUS_PAUSE") != "1"
UNFOCUSED_FPS = 1.0
SYNC_BEGIN, SYNC_END = "\x1b[?2026h", "\x1b[?2026l"
FOCUS_IN, FOCUS_OUT = b"\x1b[I", b"\x1b[O"


_CUBE = (0, 95, 135, 175, 215, 255)
_BAYER4 = ((0, 8, 2, 10), (12, 4, 14, 6), (3, 11, 1, 9), (15, 7, 13, 5))
_WEIGHT = (2, 4, 3)
_sky_last = [None, None]


def _rgb256(i):
    if i >= 232:
        v = 8 + 10 * (i - 232)
        return v, v, v
    i -= 16
    return _CUBE[i // 36], _CUBE[i // 6 % 6], _CUBE[i % 6]


def _nearest(rgb):
    """Closest 256-colour entry (cube or greyscale ramp) by weighted rgb distance."""
    chans = []
    for v in rgb:
        lo = max(i for i, c in enumerate(_CUBE) if c <= v)
        chans.append((lo, min(5, lo + 1)))
    gl = max(0, min(23, int((sum(rgb) / 3 - 8) // 10)))
    cands = {16 + 36 * r + 6 * g + b for r in chans[0] for g in chans[1] for b in chans[2]}
    cands |= {232 + gl, 232 + min(23, gl + 1)}
    return min(cands, key=lambda i: sum(k * (x - y) ** 2 for k, x, y in zip(_WEIGHT, rgb, _rgb256(i))))


def _ramp(top, hor, steps=16):
    """(position along top -> hor, 256-colour index) in increasing position: the entry
    nearest to each of steps + 1 evenly spaced points of the gradient, skipping entries that
    sit too close to the previous one along it (they differ in hue, not brightness)."""
    d = [q - p for p, q in zip(top, hor)]
    den = sum(k * x * x for k, x in zip(_WEIGHT, d))
    ramp = []
    for j in range(steps + 1):
        i = _nearest(tuple(round(p + x * j / steps) for p, x in zip(top, d)))
        p = _rgb256(i)
        pos = sum(k * (v - o) * x for k, v, o, x in zip(_WEIGHT, p, top, d)) / den if den else 0.0
        if not ramp or pos >= ramp[-1][0] + 0.08:
            ramp.append((pos, i))
    return ramp


def sky_rows(top, hor, rows, w, span=None, gamma=1.3):
    """Cells (" ", None, bg) for a vertical sky gradient from top to horizon (rgb tuples).
    Each row's colour is ordered-dithered (4x4 Bayer, fixed per cell) between the two
    neighbouring 256-colour entries of a ramp along the gradient, so the diff renderer only
    resends a cell when its colour pair changes. The returned rows are shared between calls
    with the same inputs: copy before mutating."""
    top = tuple(int(v) // 2 * 2 for v in top)
    hor = tuple(int(v) // 2 * 2 for v in hor)
    span = max(1, rows - 1 if span is None else span)
    key = (top, hor, rows, w, span, gamma)
    if _sky_last[0] == key:
        return _sky_last[1]
    ramp = _ramp(top, hor)
    out = []
    for y in range(rows):
        u = min(1.0, y / span) ** gamma
        k = 0
        while k + 1 < len(ramp) and ramp[k + 1][0] <= u:
            k += 1
        (p0, a), (p1, b) = ramp[k], ramp[min(k + 1, len(ramp) - 1)]
        t = min(1.0, max(0.0, (u - p0) / (p1 - p0))) if p1 > p0 else 0.0
        pats = [(" ", None, b if t > (by + 0.5) / 16 else a) for by in _BAYER4[y & 3]]
        out.append(tuple((pats * (w // 4 + 1))[:w]))
    _sky_last[:] = [key, out]
    return out


def size():
    """Current (cols, rows); honours COLUMNS/LINES, falls back to 80x24."""
    s = shutil.get_terminal_size((80, 24))
    return max(1, s.columns), max(1, s.lines)


@contextlib.contextmanager
def screen():
    """Alternate screen with hidden cursor, restored on exit, Ctrl-C or error."""
    out = sys.stdout
    old_term = signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
    out.write("\x1b[?1049h\x1b[?25l\x1b[2J")
    out.flush()
    try:
        yield
    finally:
        out.write("\x1b[0m\x1b[?25h\x1b[?1049l")
        out.flush()
        signal.signal(signal.SIGTERM, old_term)


_sgr_cache = {}


def _sgr(base, c):
    """SGR parameters for fg (base 38) or bg (base 48) colour c, an int or an rgb tuple."""
    if c.__class__ is int:
        return f"{base};5;{c}"
    key = (base, c)
    s = _sgr_cache.get(key)
    if s is None:
        s = _sgr_cache[key] = (f"{base};2;{c[0]};{c[1]};{c[2]}" if TRUECOLOR
                               else f"{base};5;{_nearest(tuple(c))}")
    return s


class Canvas:
    """Character grid drawn off-screen, flushed in a single write."""

    BLANK = (" ", None, None)

    def __init__(self):
        self.w = self.h = None
        self._prev = None  # cells as last flushed; None forces a full repaint
        self.resize()

    def resize(self):
        """Re-read the terminal size and clear; a size change forces a full repaint."""
        w, h = size()
        if (w, h) != (self.w, self.h):
            self.w, self.h = w, h
            self._prev = None
        self.clear()

    def clear(self):
        blank = getattr(self, "_blank", None)
        if blank is None or len(blank) != self.w:
            blank = self._blank = [self.BLANK] * self.w
        self.cells = [blank[:] for _ in range(self.h)]

    def put(self, x, y, ch, color=None, bg=None):
        """Draw ch with fg `color` (256-colour int or rgb tuple). A space is skipped unless bg is given;
        bg=None keeps the cell's existing background."""
        x, y = int(x), int(y)
        if 0 <= x < self.w and 0 <= y < self.h and (ch != " " or bg is not None):
            if bg is None:
                bg = self.cells[y][x][2]
            self.cells[y][x] = (ch, color, bg)

    def text(self, x, y, s, color=None, bg=None):
        for i, ch in enumerate(s):
            self.put(x + i, y, ch, color, bg)

    def render(self):
        rows = []
        for y, row in enumerate(self.cells):
            parts, cur = [f"\x1b[{y + 1};1H"], (None, None)
            for ch, color, bg in row:
                if COLOR and (color, bg) != cur:
                    parts.append("\x1b[0m")
                    if color is not None:
                        parts.append(f"\x1b[{_sgr(38, color)}m")
                    if bg is not None:
                        parts.append(f"\x1b[{_sgr(48, bg)}m")
                    cur = (color, bg)
                parts.append(ch)
            if cur != (None, None):
                parts.append("\x1b[0m")
            rows.append("".join(parts))
        return "".join(rows)

    def render_diff(self):
        """Escapes that turn the last flushed frame into this one ("" if unchanged).

        Changed cells on a row are grouped into runs (one cursor move each), and
        SGR codes are only emitted when the colour state actually changes.
        """
        cells, prev, w = self.cells, self._prev, self.w
        full = prev is None or len(prev) != len(cells)
        parts, fg, bg = [], None, None
        for y, row in enumerate(cells):
            if full or len(row) != len(prev[y]):
                spans = [(0, len(row))]
            else:
                old = prev[y]
                if row == old:
                    continue
                changed = [x for x in range(min(w, len(row))) if row[x] != old[x]]
                spans, start, end = [], changed[0], changed[0] + 1
                for x in changed[1:]:
                    if x - end > 4:  # a cursor move is cheaper than repainting the gap
                        spans.append((start, end))
                        start = x
                    end = x + 1
                spans.append((start, end))
            for a, b in spans:
                parts.append(f"\x1b[{y + 1};{a + 1}H")
                for ch, color, back in row[a:b]:
                    if COLOR and (color != fg or back != bg):
                        codes = []
                        if color != fg:
                            codes.append("39" if color is None else _sgr(38, color))
                        if back != bg:
                            codes.append("49" if back is None else _sgr(48, back))
                        parts.append(f"\x1b[{';'.join(codes)}m")
                        fg, bg = color, back
                    parts.append(ch)
        if fg is not None or bg is not None:
            parts.append("\x1b[0m")
        return "".join(parts)

    def flush(self):
        out = self.render() if FULL_REDRAW else self.render_diff()
        self._prev = [row[:] for row in self.cells]
        if out:
            sys.stdout.write(SYNC_BEGIN + out + SYNC_END)
            sys.stdout.flush()


def make_parser(description, fps=20):
    p = argparse.ArgumentParser(description=description)
    p.add_argument("--fps", type=float, default=fps, help=f"frames per second (default {fps:g})")
    p.add_argument("--frames", type=int, default=None, help="render N frames then exit")
    p.add_argument("--mute", action="store_true",
                   help="no sound (CLAUDE_FUN_SOUND=0 mutes everything)")
    return p


_focused = True
_pending = bytearray()  # keystrokes read by poll_input, waiting for take_input


def poll_input(fd):
    """Read whatever stdin has without blocking, consume focus reports and keep the
    rest for take_input(). Returns False once fd hits EOF."""
    global _focused
    data = b""
    while select.select([fd], [], [], 0)[0]:
        chunk = os.read(fd, 1024)
        if not chunk:
            _pending.extend(data)
            return False
        data += chunk
    if data:
        i, o = data.rfind(FOCUS_IN), data.rfind(FOCUS_OUT)
        if i != o:
            _focused = i > o
        _pending.extend(data.replace(FOCUS_IN, b"").replace(FOCUS_OUT, b""))
    return True


def take_input():
    """Bytes typed since the last call, with focus reports removed."""
    data = bytes(_pending)
    _pending.clear()
    return data


@contextlib.contextmanager
def _focus_reporting():
    """Yield stdin's fd in cbreak mode with focus reporting on, or None when stdin
    isn't a tty or CLAUDE_FUN_NO_FOCUS_PAUSE=1."""
    global _focused
    fd = sys.stdin.fileno() if sys.stdin else -1
    if not FOCUS_PAUSE or fd < 0 or not os.isatty(fd):
        yield None
        return
    import termios
    import tty
    old = termios.tcgetattr(fd)
    _focused = True
    try:
        tty.setcbreak(fd)  # keeps ISIG, so Ctrl-C still raises KeyboardInterrupt
        sys.stdout.write("\x1b[?1004h")
        sys.stdout.flush()
        yield fd
    finally:
        sys.stdout.write("\x1b[?1004l")
        sys.stdout.flush()
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
        _focused = True


def _wait(fd, nxt):
    """Sleep until nxt, waking early on input; focus regained means draw now."""
    while fd is not None:
        delay = nxt - time.monotonic()
        if delay <= 0:
            break
        if select.select([fd], [], [], delay)[0]:
            was = _focused
            if not poll_input(fd):
                time.sleep(max(0.0, nxt - time.monotonic()))
                return None, nxt
            if _focused and not was:
                return fd, time.monotonic()
    return fd, nxt


def run(args, step, music=None, sound=None):
    """Run step(canvas, frame) each frame until --frames, step returns True, or Ctrl-C.

    While the terminal reports focus lost, frames drop to UNFOCUSED_FPS and sound pauses.
    `music` names a looping track (see fun/audio.py); sound is on unless args.mute.
    """
    fps = max(1.0, args.fps)
    canvas = Canvas()
    audio.start(not getattr(args, "mute", False) if sound is None else sound)
    if music:
        audio.music(music)
    heard = True
    try:
        with screen(), _focus_reporting() as fd:
            frame, nxt = 0, time.monotonic()
            while args.frames is None or frame < args.frames:
                if fd is not None and not poll_input(fd):
                    fd = None
                if _focused != heard:
                    heard = _focused
                    if heard:
                        audio.resume()
                    else:
                        audio.pause()
                audio.tick()
                canvas.resize()  # re-read size every frame so resizing works
                if step(canvas, frame):
                    break
                canvas.flush()
                _pending.clear()  # games took their keys inside step
                frame += 1
                nxt += 1 / (fps if _focused else min(fps, UNFOCUSED_FPS))
                delay = nxt - time.monotonic()
                if delay <= 0:
                    nxt = time.monotonic()
                elif fd is None:
                    time.sleep(delay)
                else:
                    fd, nxt = _wait(fd, nxt)
    except KeyboardInterrupt:
        pass
    finally:
        audio.stop_all()
    return 0


def status_path():
    return os.path.expanduser(
        os.environ.get("CLAUDE_FUN_STATUS", "~/.cache/claude-fun/status.json"))


def read_status():
    """Return {"state", "tool", "ts"} from the status file, or None if absent/invalid."""
    try:
        with open(status_path()) as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) and "state" in data else None
