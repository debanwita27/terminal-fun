"""Sound through a system player subprocess (afplay, paplay, ffplay or aplay).

    audio.start(True)          # once; no-op when CLAUDE_FUN_SOUND=0 or no player exists
    audio.music("campfire")    # a synth recipe name or a file path; loops by default
    audio.sfx("coin")          # one-shot, non-blocking, at most MAX_SFX at once
    audio.tick()               # every frame: restarts the music loop, reaps finished players
    audio.stop_all()

term.run does start/tick/stop_all and pauses on focus loss; game.play binds `m` to mute.
Loops are gapless: the next instance starts OVERLAP seconds before the current one ends
(by the file's known length), hiding the player's start-up delay. At most two music players
exist at once, both tracked so stop_all and the exit hook reap them.
Synth sounds render once in a separate python process (so frames never stall and the
cache still fills if we quit first); a sound that is not ready yet is skipped.
"""
import atexit
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import wave

from fun import synth

MAX_SFX = 3
SFX_GAP = 0.05  # seconds before the same effect may play again
OVERLAP = 0.06  # next music loop starts this long before the current one ends
_durations = {}

_on = False
_muted = False
_paused = False
_paused_at = 0.0
_cmd = None
_music = None      # {"name", "loop", "proc"}
_sfx = []
_last = {}
_notes = []
_requested = set()
_renders = []      # renderer processes, polled so a failure gets reported
_hooked = False


def _volume():
    try:
        v = float(os.environ.get("CLAUDE_FUN_VOLUME", "0.5"))
    except ValueError:
        v = 0.5
    return min(1.0, max(0.0, v))


def _find_player():
    """Return argv(path, volume) for the first player found, or None."""
    if shutil.which("afplay"):
        return lambda p, v: ["afplay", "-v", f"{v:.3f}", p]
    if shutil.which("paplay"):
        return lambda p, v: ["paplay", f"--volume={int(v * 65536)}", p]
    if shutil.which("ffplay"):
        return lambda p, v: ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet",
                             "-volume", str(int(v * 100)), p]
    if shutil.which("aplay"):
        return lambda p, v: ["aplay", "-q", p]  # aplay has no volume control
    return None


def start(on=True):
    """Turn sound on for this process if asked, allowed by CLAUDE_FUN_SOUND and possible."""
    global _on, _cmd, _hooked
    env = os.environ.get("CLAUDE_FUN_SOUND")
    if env == "0" or not on:
        return False
    _cmd = _find_player()
    if _cmd is None:
        note("terminal-fun: no audio player found (afplay, paplay, ffplay or aplay); sound is off")
        _register_exit()
        return False
    _on = True
    _register_exit()
    if not _hooked and signal.getsignal(signal.SIGHUP) == signal.SIG_DFL:
        # A closed terminal would otherwise kill us without cleanup and orphan the players.
        signal.signal(signal.SIGHUP, lambda *_: sys.exit(129))
        _hooked = True
    _want(*synth.SFX)
    return True


def enabled():
    return _on


def note(msg):
    """Queue a line for stderr at exit, once the screen is restored."""
    if msg not in _notes:
        _notes.append(msg)
    _register_exit()


def _want(*names):
    names = [n for n in names if n in synth.RECIPES and n not in _requested and not synth.cached(n)]
    if not names:
        return
    _requested.update(names)
    try:
        proc = subprocess.Popen([sys.executable, synth.__file__, "--cache", *names],
                                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                stderr=subprocess.PIPE, start_new_session=True)
    except OSError as e:
        note(f"terminal-fun: could not render sounds: {e}")
        return
    _renders.append((proc, names))


def _check_renders():
    for item in _renders[:]:
        proc, names = item
        if proc.poll() is None:
            continue
        _renders.remove(item)
        err = proc.stderr.read().decode("utf-8", "replace").strip().splitlines()
        proc.stderr.close()
        if proc.returncode:
            note(f"terminal-fun: could not render {', '.join(names)}: {err[-1] if err else proc.returncode}")


def _resolve(name):
    if os.sep in name and os.path.exists(name):
        return name
    p = synth.cached(name)
    if p is None:
        _want(name)
    return p


def _duration(path):
    """Length in seconds of a WAV (header) or other file (afinfo); None if unknown."""
    if path in _durations:
        return _durations[path]
    d = None
    try:
        with wave.open(path) as w:
            d = w.getnframes() / w.getframerate()
    except (wave.Error, EOFError, OSError):
        if shutil.which("afinfo"):
            try:
                out = subprocess.run(["afinfo", path], stdin=subprocess.DEVNULL, capture_output=True,
                                     text=True, timeout=3).stdout
                m = re.search(r"estimated duration:\s*([0-9.]+)", out)
                d = float(m.group(1)) if m else None
            except (OSError, subprocess.SubprocessError, ValueError):
                d = None
    _durations[path] = d if d and d > 1.0 else None
    return _durations[path]


def _overlap(name):
    return synth.LOOP_OVERLAP if name in synth.AMBIENT else OVERLAP


def _spawn(path, vol=1.0):
    try:
        return subprocess.Popen(_cmd(path, _volume() * vol), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL)
    except OSError as e:
        note(f"terminal-fun: could not start the audio player: {e}")
        return None


def _kill(proc):
    if proc is None or proc.poll() is not None:
        return
    try:
        proc.kill()  # SIGKILL also ends a SIGSTOPped player
        proc.wait(timeout=1)
    except (OSError, subprocess.TimeoutExpired):
        pass


def _signal_all(sig):
    for p in _procs():
        try:
            p.send_signal(sig)
        except OSError:
            pass


def _procs():
    ps = [p for p in _sfx if p.poll() is None]
    if _music:
        ps += [p for p in (_music["proc"], _music["next"]) if p is not None and p.poll() is None]
    return ps


def music(name, loop=True):
    """Play a looping track (or once with loop=False), replacing the current one."""
    global _music
    if _music:
        _kill(_music["proc"])
    _music = {"name": name, "loop": loop, "proc": None, "next": None, "played": False,
              "due": None, "path": None}
    if _on:
        _resolve(name)
        tick()


def music_stop():
    """Stop the music loop; effects keep playing."""
    global _music
    if _music:
        _kill(_music["proc"])
        _kill(_music["next"])
    _music = None


def sfx(name, vol=1.0):
    """One-shot effect; vol scales CLAUDE_FUN_VOLUME for this sound only."""
    if not _on or _muted or _paused:
        return
    now = time.monotonic()
    if now - _last.get(name, -1.0) < SFX_GAP:
        return
    _sfx[:] = [p for p in _sfx if p.poll() is None]
    if len(_sfx) >= MAX_SFX:
        return
    path = _resolve(name)
    if path:
        proc = _spawn(path, vol)
        if proc:
            _sfx.append(proc)
            _last[name] = now


def tick():
    """Call once per frame: (re)starts the music when its player has exited."""
    if not _on:
        return
    _sfx[:] = [p for p in _sfx if p.poll() is None]
    if _renders:
        _check_renders()
    m = _music
    if not m or _muted or _paused:
        return
    now = time.monotonic()
    nxt = m["next"]
    if m["proc"] is not None and m["proc"].poll() is not None:
        m["proc"], m["next"] = nxt, None  # the queued loop takes over (or None: restart below)
        nxt = None
    proc = m["proc"]
    if proc is not None:
        if m["due"] is not None and nxt is None and now >= m["due"]:
            m["next"] = _spawn(m["path"])
            m["due"] = m["due"] + m["dur"] - _overlap(m["name"]) if m["next"] else None
        return
    if m["played"] and not m["loop"]:
        return
    path = _resolve(m["name"])
    if path:
        m["proc"] = _spawn(path)
        m["played"] = True
        m["path"] = path
        dur = _duration(path) if m["loop"] else None
        m["dur"] = dur
        m["due"] = now + dur - _overlap(m["name"]) if dur and m["proc"] else None


def mute_toggle():
    """Returns True when now muted. Unmuting restarts the music from the top."""
    global _muted
    _muted = not _muted
    if _muted:
        _stop_players()
    else:
        tick()
    return _muted


def pause():
    global _paused, _paused_at
    if _on and not _paused:
        _paused, _paused_at = True, time.monotonic()
        _signal_all(signal.SIGSTOP)


def resume():
    global _paused
    if _paused:
        _paused = False
        if _music and _music["due"] is not None:
            _music["due"] += time.monotonic() - _paused_at  # stopped players don't advance
        _signal_all(signal.SIGCONT)


def _stop_players():
    for p in _procs():
        _kill(p)
    _sfx.clear()
    if _music:
        _music["proc"] = _music["next"] = _music["due"] = None


def stop_all():
    global _music
    _stop_players()
    _music = None


def _shutdown():
    stop_all()
    for msg in _notes:
        print(msg, file=sys.stderr)
    _notes.clear()


_exit_registered = False


def _register_exit():
    global _exit_registered
    if not _exit_registered:
        atexit.register(_shutdown)
        _exit_registered = True


class Pack:
    """Files fetched once into ~/.cache/claude-fun/sounds/<subdir>/ on a background thread.

    files maps a key to a remote filename. convert holds keys to turn into AAC with
    afconvert (macOS only; others keep the original). state: "loading", "ready", "failed".
    """

    def __init__(self, subdir, base_url, files, convert=()):
        self.dir = os.path.join(synth.CACHE_DIR, subdir)
        self.base, self.files, self.convert = base_url.rstrip("/") + "/", files, set(convert)
        self.paths, self.errors = {}, []
        self.state = "loading"
        if all(self._have(k) for k in files):
            self.state = "ready"
        else:
            threading.Thread(target=self._fetch, daemon=True).start()

    def _local(self, key):
        fn = self.files[key]
        if key in self.convert and shutil.which("afconvert"):
            fn = os.path.splitext(fn)[0] + ".m4a"
        return os.path.join(self.dir, fn)

    def _have(self, key):
        raw = os.path.join(self.dir, self.files[key])
        for p in (self._local(key), raw):
            if os.path.exists(p):
                self.paths[key] = p
                return True
        return False

    def _fetch(self):
        os.makedirs(self.dir, exist_ok=True)
        order = sorted(self.files, key=lambda k: k in self.convert)  # small files first
        for key in order:
            if self._have(key):
                continue
            fn = self.files[key]
            raw = os.path.join(self.dir, fn)
            tmp = f"{raw}.{os.getpid()}.part"
            try:
                url = self.base + urllib.request.quote(fn)
                with urllib.request.urlopen(url, timeout=20) as r, open(tmp, "wb") as f:
                    shutil.copyfileobj(r, f, 1 << 16)
                os.replace(tmp, raw)
            except Exception as e:  # offline or HTTP error: the caller falls back per key
                self.errors.append(f"{fn}: {e}")
                if os.path.exists(tmp):
                    os.remove(tmp)
                if isinstance(e, OSError) and not isinstance(e, urllib.error.HTTPError):
                    break  # unreachable: don't wait out a timeout for every file
                continue
            final = self._local(key)
            if final != raw:
                ctmp = f"{final}.{os.getpid()}.part.m4a"
                try:
                    subprocess.run(["afconvert", "-f", "m4af", "-d", "aac", raw, ctmp],
                                   check=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL, timeout=300)
                    os.replace(ctmp, final)
                    os.remove(raw)
                except (OSError, subprocess.SubprocessError):
                    final = raw  # keep the WAV; it plays just the same
                    if os.path.exists(ctmp):
                        os.remove(ctmp)
            self.paths[key] = final
        self.state = "failed" if self.errors else "ready"

    def path(self, key):
        return self.paths.get(key)
