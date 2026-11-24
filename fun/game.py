"""Game helpers on top of term: raw keyboard input, high scores, Claude-done check.

    parser = term.make_parser("my game")
    args = parser.parse_args()
    game.play(args, step)   # step(canvas, frame, keys) -> True to stop

`keys` is the list of key names pressed since the last frame:
"up" "down" "left" "right" "space" "enter" "esc", or the literal character.
WASD is reported as the matching arrow name as well as the letter.
Sound is on by default; `m` toggles mute in every game and never reaches step.

A game where every letter must reach step (a typewriter) passes raw_keys=True and picks
another mute_key; see play().
"""
import json
import os
import sys
import termios
import time
import tty

from fun import audio, term

ARROWS = {"A": "up", "B": "down", "C": "right", "D": "left"}
SS3_F = {"P": "f1", "Q": "f2", "R": "f3", "S": "f4", "H": "home", "F": "end"}
CSI_TILDE = {1: "home", 2: "insert", 3: "delete", 4: "end", 5: "pageup", 6: "pagedown",
             11: "f1", 12: "f2", 13: "f3", 14: "f4", 15: "f5", 17: "f6", 18: "f7", 19: "f8",
             20: "f9", 21: "f10", 23: "f11", 24: "f12"}
ESC_CHORD = 1.5  # seconds after a lone Esc during which the next key reads as Alt+key
WASD = {"w": "up", "a": "left", "s": "down", "d": "right"}
STARTED = time.time()
TOAST_SECS = 2.0
_toast = {"text": "", "until": 0.0}


def toast(text, secs=TOAST_SECS):
    """Show a short message in the top-right corner for a moment."""
    _toast["text"], _toast["until"] = text, time.monotonic() + secs


def _draw_toast(c):
    if time.monotonic() < _toast["until"] and c.w > len(_toast["text"]) + 2:
        msg = f" {_toast['text']} "
        c.text(c.w - len(msg) - 1, 0, msg, 16, 250)


def _parse(data):
    keys, i = [], 0
    while i < len(data):
        ch = data[i]
        if ch == "\x1b" and data[i + 1:i + 2] in ("[", "O") and i + 2 < len(data):
            j = i + 2
            while j < len(data) - 1 and not 0x40 <= ord(data[j]) <= 0x7e:
                j += 1  # skip CSI parameters such as "1;5" in Ctrl+Arrow
            if data[j] in ARROWS:
                keys.append(ARROWS[data[j]])
            i = j + 1
            continue
        if ch == "\x1b":
            keys.append("esc")
        elif ch == " ":
            keys.append("space")
        elif ch in "\r\n":
            keys.append("enter")
        else:
            keys.append(ch.lower())
            if ch.lower() in WASD:
                keys.append(WASD[ch.lower()])
        i += 1
    return keys


def _parse_raw(data):
    """Keys exactly as typed: case kept, no WASD aliases. Adds "tab", "backspace", "delete",
    "home", "end", "pageup", "pagedown", "insert", "f1".."f12", "ctrl-x" and "alt-x"
    (Esc and a key in one read, which is also what Option/Alt+key sends)."""
    keys, i, n = [], 0, len(data)
    while i < n:
        ch = data[i]
        if ch == "\x1b" and data[i + 1:i + 2] in ("[", "O") and i + 2 < n:
            j = i + 2
            while j < n - 1 and not 0x40 <= ord(data[j]) <= 0x7e:
                j += 1
            final, params = data[j], data[i + 2:j]
            if final in ARROWS:
                keys.append(ARROWS[final])
            elif final in SS3_F and (data[i + 1] == "O" or final in "HF"):
                keys.append(SS3_F[final])
            elif final == "~":
                num = params.split(";")[0]
                if num.isdigit() and int(num) in CSI_TILDE:
                    keys.append(CSI_TILDE[int(num)])
            i = j + 1
            continue
        if ch == "\x1b":
            nxt = data[i + 1:i + 2]
            if nxt and nxt != "\x1b" and nxt >= " ":
                keys.append("alt-" + nxt)
                i += 2
                continue
            keys.append("esc")
        elif ch == " ":
            keys.append("space")
        elif ch in "\r\n":
            keys.append("enter")
        elif ch == "\t":
            keys.append("tab")
        elif ch in "\x7f\x08":
            keys.append("backspace")
        elif ch < " ":
            keys.append("ctrl-" + chr(ord(ch) + 96))
        else:
            keys.append(ch)
        i += 1
    return keys


def _read_keys(fd, raw=False, input_filter=None):
    # term owns stdin reads so focus reports never reach the key list.
    term.poll_input(fd)
    data = term.take_input().decode("utf-8", "ignore")
    if input_filter:
        data = input_filter(data)
    return _parse_raw(data) if raw else _parse(data)


def play(args, step, music=None, raw_keys=False, mute_key="m", mute_label=None,
         input_filter=None):
    """term.run with stdin in cbreak mode and sound on. Without a tty (smoke tests) keys
    are always [].

    input_filter(text) -> text sees each frame's raw input before it becomes keys, so a game
    can take out sequences the key parser drops (mouse reports, say) and hand back the rest.

    raw_keys=True reports keys as _parse_raw does, and a lone Esc followed within ESC_CHORD
    seconds by a key also arrives as "alt-<key>" (the Esc itself still reaches step).
    mute_key is the key name that toggles mute and never reaches step (None: no mute key);
    mute_label is how the start-up toast names it."""
    fd = sys.stdin.fileno()
    interactive = os.isatty(fd)
    old = termios.tcgetattr(fd) if interactive else None
    esc_at = [None]

    def chord(keys):
        out = []
        for k in keys:
            if esc_at[0] is not None and k != "esc" and len(k) == 1:
                if time.monotonic() - esc_at[0] <= ESC_CHORD:
                    k = "alt-" + k
                esc_at[0] = None
            elif k == "esc":
                esc_at[0] = time.monotonic()
            else:
                esc_at[0] = None
            out.append(k)
        return out

    def wrapped(c, frame):
        keys = _read_keys(fd, raw_keys, input_filter) if interactive else []
        if raw_keys and keys:
            keys = chord(keys)
        if frame == 0 and audio.enabled() and mute_key:
            toast(f"♪  {mute_label or mute_key}: mute", 2.5)
        if mute_key and mute_key in keys:
            keys = [k for k in keys if k != mute_key]
            if audio.enabled():
                toast("muted" if audio.mute_toggle() else "♪ sound on")
            else:
                toast("sound is off")
        done = step(c, frame, keys)
        _draw_toast(c)
        return done

    try:
        if interactive:
            tty.setcbreak(fd)  # keeps ISIG, so Ctrl-C still raises KeyboardInterrupt
        return term.run(args, wrapped, music=music)
    finally:
        if interactive:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)


def _scores_path():
    return os.path.join(os.path.dirname(term.status_path()), "scores.json")


def best(name):
    try:
        with open(_scores_path()) as f:
            return int(json.load(f).get(name, 0))
    except (OSError, ValueError, AttributeError, TypeError):
        return 0


def record(name, score):
    """Save score if it beats the stored best. Returns True on a new best."""
    if score <= best(name):
        return False
    path = _scores_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        try:
            with open(path) as f:
                data = json.load(f)
            if not isinstance(data, dict):
                data = {}
        except (OSError, ValueError):
            data = {}
        data[name] = score
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(data, f)
        os.replace(tmp, path)
    except OSError as e:
        print(f"could not save score: {e}", file=sys.stderr)
    return True


def claude_done():
    """True once the status file reports a 'done' newer than this process's start."""
    s = term.read_status()
    ts = s.get("ts") if s else None
    return bool(s and s.get("state") == "done" and isinstance(ts, (int, float)) and ts > STARTED)
