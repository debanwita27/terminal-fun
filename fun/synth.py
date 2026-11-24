"""Original synthesized sounds: chiptune loops for the games, ambient beds for the
watch pieces, and short effects. Stdlib only (wave, math, array, random).

Everything renders at 22050 Hz mono 16-bit and is cached as
~/.cache/claude-fun/sounds/NAME-VERSION.wav, where VERSION hashes this file, so
editing any recipe regenerates each sound once.

    python3 fun/synth.py [NAME ...]    render (all by default) into a temp dir, print timings
    python3 fun/synth.py --cache NAME...   render into the cache (what fun/audio.py runs)
"""
import array
import hashlib
import math
import operator
import os
import random
import re
import sys
import tempfile
import time
import wave

RATE = 22050
TL = 4096
MASK = TL - 1
CACHE_DIR = os.path.expanduser(os.path.join("~", ".cache", "claude-fun", "sounds"))
with open(__file__, "rb") as _f:
    VERSION = hashlib.sha1(_f.read()).hexdigest()[:10]


# ------------------------------------------------------------------ primitives

_tables = {}


def table(shape):
    """One band-limited cycle; few harmonics plus sigma smoothing keep it soft."""
    t = _tables.get(shape)
    if t is not None:
        return t
    if shape == "sine":
        harm = [(1, 1.0)]
    elif shape == "tri":
        harm = [(k, (-1) ** ((k - 1) // 2) / k ** 2) for k in (1, 3, 5, 7, 9)]
    elif shape == "bell":
        harm = [(1, 1.0), (2, 0.22), (3, 0.08), (5, 0.03)]
    elif shape == "ep":
        harm = [(1, 1.0), (2, 0.35), (3, 0.12), (4, 0.05)]
    else:
        duty = {"square": 0.5, "pulse25": 0.25, "pulse12": 0.125}[shape]
        n = 9
        harm = [(k, math.sin(math.pi * k * duty) / k * _sigma(k, n)) for k in range(1, n + 1)]
    t = [0.0] * TL
    for k, a in harm:
        w = 2 * math.pi * k / TL
        for i in range(TL):
            t[i] += a * math.sin(w * i)
    peak = max(abs(v) for v in t) or 1.0
    t = _tables[shape] = [v / peak for v in t]
    return t


def _sigma(k, n):
    x = math.pi * k / (n + 1)
    return math.sin(x) / x


def hz(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def lowpass(buf, fc):
    a = 1 - math.exp(-2 * math.pi * fc / RATE)
    y, out = 0.0, []
    app = out.append
    for x in buf:
        y += a * (x - y)
        app(y)
    return out


def highpass(buf, fc):
    return list(map(operator.sub, buf, lowpass(buf, fc)))


def osc(freq, n, shape="sine", phase=0.0):
    tbl, inc = table(shape), freq * TL / RATE
    p0 = phase * TL
    return [tbl[int(p0 + i * inc) & MASK] for i in range(n)]


def sweep(f0, f1, n, shape="sine", vib=0.0, vib_hz=6.0):
    """Oscillator gliding exponentially from f0 to f1 over n samples."""
    tbl, out, ph = table(shape), [], 0.0
    ratio = (f1 / f0) ** (1 / max(1, n))
    f = f0
    k = 2 * math.pi * vib_hz / RATE
    for i in range(n):
        out.append(tbl[int(ph) & MASK])
        ff = f * (1 + vib * math.sin(k * i)) if vib else f
        ph += ff * TL / RATE
        f *= ratio
    return out


def env(n_on, n_rel, a=0.005, d=0.1, s=0.6):
    """Attack, exponential decay toward sustain s (time constant d), then a smooth release."""
    na = max(1, min(n_on, int(a * RATE)))
    kd = 1 / max(1.0, d * RATE)
    e = [i / na for i in range(na)]
    e += [s + (1 - s) * math.exp(-i * kd) for i in range(n_on - na)]
    last = e[-1] if e else 0.0
    if n_rel:
        e += [last * (1 - j / n_rel) ** 2 for j in range(n_rel)]
    return e


def mul(a, b):
    return list(map(operator.mul, a, b))


def gain(buf, g):
    return [v * g for v in buf]


def noise(n, rng):
    r = rng.random
    return [r() * 2 - 1 for _ in range(n)]


def decay(n, tau):
    k = 1 / max(1.0, tau * RATE)
    return [math.exp(-i * k) for i in range(n)]


def add_at(mix, buf, at, wrap=True):
    """Mix buf into mix starting at sample `at`; the overhang wraps to the start so loops
    keep ringing tails across the seam."""
    n = len(mix)
    at %= n
    while buf:
        end = min(n, at + len(buf))
        k = end - at
        mix[at:end] = map(operator.add, mix[at:end], buf[:k])
        if not wrap:
            return
        buf, at = buf[k:], 0


_note_cache = {}


class Inst:
    def __init__(self, shape, vol, a=0.005, d=0.12, s=0.5, r=0.06, gate=0.9, lp=None):
        self.shape, self.vol, self.a, self.d, self.s, self.r = shape, vol, a, d, s, r
        self.gate, self.lp = gate, lp

    def __call__(self, m, dur):
        key = (id(self), m, round(dur, 4))
        buf = _note_cache.get(key)
        if buf is None:
            n_on, n_r = max(1, int(dur * self.gate * RATE)), int(self.r * RATE)
            o = osc(hz(m), n_on + n_r, self.shape)
            buf = mul(o, env(n_on, n_r, self.a, self.d, self.s))
            if self.lp:
                buf = lowpass(buf, self.lp)
            buf = _note_cache[key] = gain(buf, self.vol)
        return buf


# ------------------------------------------------------------------ drums

_drum_cache = {}


def drum(name):
    if name in _drum_cache:
        return _drum_cache[name]
    rng = random.Random(name)
    if name == "k":
        n = int(0.28 * RATE)
        buf = mul(sweep(140, 42, n), decay(n, 0.09))
        buf = gain(buf, 0.55)
    elif name == "s":
        n = int(0.2 * RATE)
        nz = lowpass(highpass(noise(n, rng), 600), 5000)
        buf = list(map(operator.add, mul(nz, decay(n, 0.045)),
                       mul(gain(osc(190, n), 0.5), decay(n, 0.03))))
        buf = gain(buf, 0.28)
    elif name == "h":
        n = int(0.06 * RATE)
        buf = gain(mul(lowpass(highpass(noise(n, rng), 5000), 9000), decay(n, 0.012)), 0.16)
    elif name == "b":  # brush
        n = int(0.16 * RATE)
        buf = gain(mul(lowpass(highpass(noise(n, rng), 1500), 4000),
                       env(n, 0, a=0.02, d=0.05, s=0)), 0.16)
    elif name == "w":  # woodblock
        n = int(0.08 * RATE)
        buf = gain(mul(osc(1100, n, "tri"), decay(n, 0.018)), 0.18)
    else:
        raise ValueError(f"unknown drum {name!r}")
    _drum_cache[name] = buf
    return buf


# ------------------------------------------------------------------ sequencing

PC = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
QUAL = {"": (0, 4, 7), "m": (0, 3, 7), "7": (0, 4, 7, 10), "m7": (0, 3, 7, 10),
        "maj7": (0, 4, 7, 11), "m9": (0, 3, 7, 10, 14), "maj9": (0, 4, 7, 11, 14),
        "9": (0, 4, 7, 10, 14), "13": (0, 4, 10, 14, 21), "sus2": (0, 2, 7), "6": (0, 4, 7, 9)}


def note(tok):
    if tok.isdigit():
        return int(tok)
    m = re.fullmatch(r"([A-G])([#b]?)(\d)", tok)
    if not m:
        raise ValueError(f"bad note {tok!r}")
    acc = {"#": 1, "b": -1}.get(m.group(2), 0)
    return 12 * (int(m.group(3)) + 1) + PC[m.group(1)] + acc


def chord(name, octave):
    m = re.fullmatch(r"([A-G][#b]?)(.*)", name)
    root = note(m.group(1) + str(octave))
    return [root + i for i in QUAL[m.group(2)]]


def figure(chords, fig, octave):
    """Spell a figure per bar over a chord list. Tokens: R root, 3/5/7 chord tones,
    O root up an octave, T third up an octave, C whole chord, '.' rest, '-' hold.
    A bar given as a tuple of chords splits the figure between them."""
    figt, out = fig.split(), []
    for bar in chords:
        parts = bar if isinstance(bar, tuple) else (bar,)
        seg = len(figt) // len(parts)
        for j, name in enumerate(parts):
            c = chord(name, octave)
            for tok in figt[j * seg:(j + 1) * seg]:
                if tok in (".", "-"):
                    out.append(tok)
                elif tok == "C":
                    out.append("+".join(str(x) for x in c[:4]))
                else:
                    idx = {"R": 0, "3": 1, "5": 2, "7": 3}.get(tok)
                    m = (c[0] + 12 if tok == "O" else c[1] + 12 if tok == "T"
                         else c[idx] if idx < len(c) else c[0] + 12)
                    out.append(str(m))
    return " ".join(out)


def song(bpm, bars, parts, spb=2, beats=4, swing=0.0, lp=6500, peak=0.45):
    """parts: [(pattern, inst)] where inst is an Inst or "drums". A short pattern repeats."""
    step = 60 / bpm / spb
    total = bars * beats * spb
    n = int(round(total * step * RATE))
    mix = [0.0] * n
    for pattern, inst in parts:
        toks = [t for t in pattern.split() if t != "|"]
        toks = (toks * (total // len(toks) + 1))[:total]
        for i, tok in enumerate(toks):
            if tok in (".", "-"):
                continue
            j = i + 1
            while j < total and toks[j] == "-":
                j += 1
            t = i * step + (swing * step if swing and i % 2 else 0)
            at = int(t * RATE)
            for sub in tok.split("+"):
                buf = drum(sub) if inst == "drums" else inst(note(sub), (j - i) * step)
                add_at(mix, buf, at)
    if lp:
        mix = lowpass(mix, lp)
    return mix, peak


# ------------------------------------------------------------------ game music

def m_bugsquash():
    ch = ["C", "Am", "F", "G", "C", "Am", "Dm", "G"]
    mel = ("E5 - G5 - C6 - G5 E5 | A5 - G5 E5 C5 - E5 . | F5 - A5 - C6 - A5 F5 | G5 - D5 - B4 - D5 . | "
           "E5 G5 C6 - B5 G5 E5 - | A5 - C6 - B5 A5 E5 - | F5 - A5 - D6 - C6 A5 | G5 - B5 - D6 - . .")
    return song(126, 8, [
        (mel, Inst("pulse25", 0.30, d=0.12, s=0.45, lp=4500)),
        (figure(ch, "R . O . 5 . O .", 3), Inst("tri", 0.55, d=0.15, s=0.3, gate=0.8)),
        (figure(ch, ". C . C . C . C", 4), Inst("pulse12", 0.07, d=0.05, s=0, gate=0.5, lp=3000)),
        ("k h s h k h s h", "drums")])


def m_catstack():
    ch = ["F", "Dm", "Bb", "C", "F", "Dm", "Gm", "C"]
    mel = ("C5 . F5 . A5 . G5 F5 | D5 . F5 . A5 - . . | Bb4 . D5 . F5 . D5 C5 | C5 . E5 . G5 - . . | "
           "A5 . C6 . A5 . F5 G5 | A5 . F5 . D5 - . . | Bb4 . D5 . G5 . F5 E5 | E5 . G5 . C6 - . .")
    return song(108, 8, [
        (mel, Inst("pulse25", 0.28, d=0.08, s=0.15, r=0.05, gate=0.7, lp=4000)),
        (figure(ch, "R 3 5 O 5 3 R 3", 4), Inst("square", 0.10, a=0.002, d=0.07, s=0, lp=2800)),
        (figure(ch, "R . . . 5 . . .", 2), Inst("tri", 0.5, d=0.25, s=0.2)),
        ("k . w . s . w .", "drums")])


def m_froghop():
    ch = ["G", "Em", "C", "D", "G", "Em", "Am", "D"]
    mel = ("D5 - B4 - D5 E5 D5 B4 | G5 - E5 - . B4 D5 E5 | G5 - E5 C5 - . E5 G5 | F#5 - A5 - F#5 E5 D5 . | "
           "B5 - A5 G5 - D5 E5 G5 | B5 - G5 - E5 . D5 E5 | C6 - B5 A5 - E5 G5 A5 | F#5 - E5 - D5 . . .")
    return song(104, 8, [
        (mel, Inst("tri", 0.42, a=0.01, d=0.2, s=0.55, lp=5000)),
        (figure(ch, "R - 5 - O - 5 -", 2), Inst("sine", 0.5, d=0.3, s=0.4, gate=0.85)),
        (figure(ch, ". . C - . . C -", 4), Inst("square", 0.06, a=0.01, d=0.1, s=0.3, lp=1800)),
        ("k+h . h+b h h . h+b h", "drums")], swing=0.33)


def m_ducklings():
    ch = ["D", "G", "A", "D", "Bm", "G", "Em", "A"]
    mel = ("F#5 - F#5 A5 D6 - A5 . | B5 - B5 A5 G5 - . . | E5 - E5 F#5 G5 - E5 . | F#5 - D5 - A4 - . . | "
           "D5 - F#5 - B5 - A5 . | G5 - B5 - D6 - B5 . | G5 - F#5 - E5 - G5 . | A5 - C#6 - E6 - . .")
    return song(112, 8, [
        (mel, Inst("square", 0.24, d=0.08, s=0.35, gate=0.6, lp=4200)),
        (figure(ch, "R . 5 . R . 5 .", 2), Inst("tri", 0.55, d=0.12, s=0.2, gate=0.6)),
        (figure(ch, ". C . C . C . C", 4), Inst("pulse12", 0.07, d=0.05, s=0, gate=0.45, lp=2800)),
        ("k . s s k . s .", "drums")])


def m_forage():
    ch = ["Am7", "Fmaj7", "C", "G", "Am7", "Dm7", "Fmaj7", "E"]
    mel = ("E5 - - - C5 - D5 - | E5 - - - . . A4 - | G5 - - - E5 - D5 - | D5 - - - . . B4 - | "
           "C5 - E5 - A5 - - - | F5 - - - E5 - D5 - | C5 - - - A4 - C5 - | B4 - - - G#4 - - -")
    return song(80, 8, [
        (mel, Inst("bell", 0.32, a=0.004, d=0.6, s=0.15, r=0.6, lp=4000)),
        (figure(ch, "R 5 O T 7 5 O 5", 3), Inst("tri", 0.16, a=0.01, d=0.35, s=0.25, r=0.3, lp=2500)),
        (figure(ch, "R - - - - - - -", 2), Inst("sine", 0.34, a=0.05, d=1.0, s=0.5, r=0.4))],
        lp=5000)


def m_bonkyon():
    ch = ["Em", "C", "G", "D", "Em", "C", "G", "D"]
    mel = ("B4 - E5 - G5 - F#5 E5 | G5 - E5 - C5 - E5 . | D5 - G5 - B5 - A5 G5 | F#5 - A5 - D5 - . . | "
           "E5 G5 B5 - A5 G5 F#5 G5 | E5 - C6 - B5 - G5 . | D5 G5 B5 - D6 - B5 . | A5 - F#5 - D5 - . .")
    return song(120, 8, [
        (mel, Inst("pulse25", 0.28, d=0.1, s=0.45, lp=4500)),
        (figure(ch, "R O R O R O R O", 2), Inst("pulse25", 0.22, d=0.08, s=0.3, gate=0.5, lp=1500)),
        ("k h s h k k s h", "drums")])


# ------------------------------------------------------------------ ambient beds

def seamless(buf, n, fade):
    """Crossfade buf[n:n+fade] into the head so a buffer of n+fade samples loops cleanly."""
    out = buf[:n]
    for i in range(fade):
        x = i / fade * math.pi / 2
        out[i] = buf[i] * math.sin(x) + buf[n + i] * math.cos(x)
    return out


def loop_hz(f, secs):
    """Nearest frequency with a whole number of cycles in secs, so drones loop seamlessly."""
    return max(1, round(f * secs)) / secs


def bells(secs, scale, rng, rate, octave_span, vol=0.25, decay_s=2.5, base_oct=5):
    n = int(secs * RATE)
    mix = [0.0] * n
    cache = {}
    t = rng.uniform(0, 0.5)
    while t < secs:
        m = note(rng.choice(scale) + str(base_oct + rng.randrange(octave_span)))
        if m not in cache:
            ln = int(decay_s * 1.6 * RATE)
            f = hz(m)
            body = mul(osc(f, ln, "bell"), env(ln, 0, a=0.003, d=decay_s, s=0))
            shimmer = mul(osc(f * 2.76, ln), decay(ln, decay_s * 0.25))
            cache[m] = list(map(operator.add, body, gain(shimmer, 0.18)))
        add_at(mix, gain(cache[m], vol * rng.uniform(0.5, 1.0)), int(t * RATE))
        t += rng.expovariate(rate)
    return mix


def pad(chords, secs_each, octave, vol, attack, release, shape="tri", detune=0.0025):
    """Chord pads, one per segment, swelling in and overlapping into the next (wrapping)."""
    n = int(secs_each * len(chords) * RATE)
    mix = [0.0] * n
    seg = int(secs_each * RATE)
    for k, name in enumerate(chords):
        ln = seg + int(release * RATE)
        voice = [0.0] * ln
        for m in chord(name, octave):
            for d in (-detune, detune):
                voice = list(map(operator.add, voice, osc(hz(m) * (1 + d), ln, shape, phase=random.random())))
        e = env(seg, int(release * RATE), a=attack, d=secs_each, s=0.7)
        add_at(mix, gain(mul(voice, e), vol), k * seg)
    return mix


def a_campfire():
    rng, secs, fade = random.Random(7), 24, RATE
    n = int(secs * RATE)
    nz = noise(n + fade, rng)
    rumble = lowpass(lowpass(nz, 90), 120)
    rumble = gain(rumble, 9.0)
    hiss = gain(lowpass(highpass(nz, 1200), 3000), 0.05)
    bed = seamless(list(map(operator.add, rumble, hiss)), n, fade)
    crack = [0.0] * n
    t = 0.0
    while t < secs:
        for _ in range(rng.choice((1, 1, 2, 3))):
            ln = int(rng.uniform(0.003, 0.012) * RATE)
            burst = mul(noise(ln, rng), decay(ln, ln / RATE / 3))
            add_at(crack, gain(burst, rng.uniform(0.2, 0.9)), int((t + rng.uniform(0, 0.04)) * RATE))
        t += rng.expovariate(5)
    crack = lowpass(highpass(crack, 700), 6000)
    return list(map(operator.add, bed, crack)), 0.5


def a_reef():
    rng, secs = random.Random(3), 32
    mix = pad(["Dmaj7", "Bm7", "Gmaj7", "A6"], secs / 4, 3, 0.07, 2.5, 3.5, shape="sine")
    mix = lowpass(mix, 1800)
    n = len(mix)
    t = 1.0
    while t < secs:
        for j in range(rng.randint(2, 6)):
            ln = int(rng.uniform(0.03, 0.07) * RATE)
            f0 = rng.uniform(450, 900)
            b = mul(sweep(f0, f0 * rng.uniform(1.8, 2.6), ln), env(ln, 0, a=0.004, d=0.02, s=0))
            add_at(mix, gain(b, rng.uniform(0.05, 0.12)), int((t + j * rng.uniform(0.07, 0.18)) * RATE))
        t += rng.uniform(2.0, 5.0)
    return mix[:n], 0.45


def a_forest():
    rng, secs, fade = random.Random(11), 30, RATE
    n = int(secs * RATE)
    nz = noise(n + fade, rng)
    # cutoff and level breathe on LFOs with whole cycles per loop
    w1, w2 = 2 * math.pi * 2 / secs / RATE, 2 * math.pi * 3 / secs / RATE
    a_coef = [1 - math.exp(-2 * math.pi * (350 + 250 * math.sin(w1 * i) + 120 * math.sin(w2 * i)) / RATE)
              for i in range(n + fade)]
    y, wind = 0.0, []
    for x, a in zip(nz, a_coef):
        y += a * (x - y)
        wind.append(y)
    lvl = [0.6 + 0.4 * math.sin(w1 * i + 1.0) for i in range(n + fade)]
    mix = seamless(gain(mul(wind, lvl), 2.2), n, fade)
    t = 2.0
    while t < secs - 1:
        f = rng.uniform(2600, 3800)
        for j in range(rng.randint(2, 5)):
            ln = int(rng.uniform(0.05, 0.11) * RATE)
            chirp = mul(sweep(f, f * rng.uniform(0.7, 1.3), ln), env(ln, 0, a=0.01, d=0.04, s=0))
            add_at(mix, gain(chirp, 0.12), int((t + j * 0.14) * RATE))
        t += rng.uniform(3.0, 7.0)
    return mix, 0.45


def a_jellyfish():
    rng, secs = random.Random(5), 32
    mix = pad(["Cmaj9", "Am9", "Fmaj9", "G6"], secs / 4, 3, 0.06, 3.5, 5.0, shape="tri", detune=0.004)
    mix = lowpass(mix, 1400)
    sh = bells(secs, ["E", "G", "B", "D"], rng, 0.25, 1, vol=0.08, decay_s=3.0, base_oct=6)
    return list(map(operator.add, mix, sh)), 0.45


def a_blackhole():
    rng, secs = random.Random(13), 24
    n = int(secs * RATE)
    f1, f2, f3 = loop_hz(41.2, secs), loop_hz(82.4, secs), loop_hz(82.4, secs) + 0.5
    drone = [a + 0.5 * b + 0.5 * c for a, b, c in zip(osc(f1, n), osc(f2, n, "tri"), osc(f3, n, "tri"))]
    drone = lowpass(drone, 300)
    swell = [0.75 + 0.25 * math.sin(2 * math.pi * 2 * i / n) for i in range(n)]
    mix = gain(mul(drone, swell), 0.5)
    beat_len = int(0.5 * RATE)
    thump = mul(sweep(70, 34, beat_len), decay(beat_len, 0.12))
    for k in range(int(secs / 2)):
        add_at(mix, gain(thump, 0.55), int(k * 2 * RATE))
        add_at(mix, gain(thump, 0.35), int((k * 2 + 0.32) * RATE))
    wash = seamless(lowpass(noise(n + RATE, rng), 200), n, RATE)
    return list(map(operator.add, mix, gain(wash, 1.5))), 0.5


def a_skyline():
    ch = ["Dm9", "G13", "Cmaj9", "A7"] * 2
    ep = Inst("ep", 0.13, a=0.004, d=0.9, s=0.25, r=0.5, lp=2200)
    mix, peak = song(72, 8, [
        (figure(ch, "C - - C - - - -", 3), ep),
        (figure(ch, "R - - - - - 5 -", 2), Inst("sine", 0.4, a=0.02, d=0.6, s=0.4)),
        ("k . . k s . . .", "drums"),
        (". h . h . h . h", "drums")], swing=0.25, lp=3500, peak=0.45)
    rng = random.Random(17)
    for _ in range(60):
        add_at(mix, [rng.uniform(-0.15, 0.15) for _ in range(6)], rng.randrange(len(mix)))
    # distant traffic under the piano: a low hush breathing three times a loop, and far cars swelling past
    n, fade = len(mix), RATE
    hush = highpass(seamless(lowpass(lowpass(noise(n + fade, rng), 420), 300), n, fade), 60)
    rms = (sum(v * v for v in mix) / n) ** 0.5
    hk = 0.3 * rms / ((sum(v * v for v in hush) / n) ** 0.5 or 1.0)
    w1 = 2 * math.pi * 3 / n
    mix = [m + h * hk * (0.75 + 0.25 * math.sin(w1 * i)) for i, (m, h) in enumerate(zip(mix, hush))]
    for _ in range(4):
        ln = _n(rng.uniform(2.5, 4.0))
        whoosh = lowpass(lowpass(mul(noise(ln, rng), [math.sin(math.pi * i / ln) ** 2 for i in range(ln)]), 700), 500)
        add_at(mix, gain(whoosh, hk * 2.5), rng.randrange(n))
    return mix, peak


def fx_siren():
    """skyline: a far-off siren wailing across the city, muffled by distance and drifting away."""
    n = _n(5.0)
    tbl, ph, out = table("tri"), 0.0, []
    k = 2 * math.pi * 0.55 / RATE
    for i in range(n):
        f = (760 + 180 * math.sin(k * i)) * (1 - 0.025 * i / n)
        out.append(tbl[int(ph) & MASK])
        ph += f * TL / RATE
    out = mul(out, env(n - _n(1.5), _n(1.5), a=1.2, d=2.0, s=0.7))
    return lowpass(lowpass(out, 1300), 1500), 0.22


def fx_train():
    """skyline: a distant train, a low rumble with wheel clacks in pairs and a soft two-note horn."""
    rng, n = random.Random(81), _n(7.0)
    shape = [math.sin(math.pi * i / n) ** 1.5 for i in range(n)]
    out = mul(lowpass(lowpass(noise(n, rng), 160), 160), shape)
    lvl = (sum(v * v for v in out) / n) ** 0.5 or 1.0
    out = gain(out, 0.25 / lvl)
    cl = _n(0.05)
    clack = lowpass(mul(noise(cl, rng), decay(cl, 0.012)), 900)
    t = 0.4
    while t < 6.4:
        k = shape[_n(t)]
        add_at(out, gain(clack, 0.5 * k), _n(t), wrap=False)
        add_at(out, gain(clack, 0.4 * k), _n(t + 0.13), wrap=False)
        t += 0.62
    hl = _n(1.6)
    horn = list(map(operator.add, osc(311.1, hl, "tri"), osc(370.0, hl, "tri")))
    horn = lowpass(mul(horn, env(hl - _n(0.5), _n(0.5), a=0.15, d=1.0, s=0.7)), 900)
    add_at(out, gain(horn, 0.12), _n(1.0), wrap=False)
    return lowpass(out, 1800), 0.3


def fx_dawnbirds():
    """skyline: a few small birds greeting the dawn, chirping in short runs."""
    rng, out = random.Random(83), [0.0] * _n(2.6)
    t = 0.05
    for _ in range(3):
        f = rng.uniform(2800, 4200)
        for j in range(rng.randint(2, 4)):
            ln = _n(rng.uniform(0.05, 0.1))
            chirp = mul(sweep(f, f * rng.uniform(0.75, 1.3), ln), env(ln, 0, a=0.008, d=0.035, s=0))
            add_at(out, gain(chirp, rng.uniform(0.6, 1.0)), _n(t + j * 0.13), wrap=False)
        t += rng.uniform(0.6, 0.8)
    return lowpass(out, 6000), 0.25


def a_sandpile():
    return bells(30, ["C", "D", "E", "G", "A"], random.Random(21), 1.4, 2, vol=0.22, decay_s=2.2), 0.45


def a_spacecol():
    rng = random.Random(23)
    mix = bells(30, ["D", "E", "F#", "A", "B"], rng, 0.9, 2, vol=0.22, decay_s=3.0, base_oct=4)
    drone = osc(loop_hz(hz(note("D2")), 30), len(mix))
    return list(map(operator.add, mix, gain(drone, 0.05))), 0.45


def a_default():
    return bells(30, ["F", "G", "A", "C", "D"], random.Random(31), 0.5, 2, vol=0.2, decay_s=3.2, base_oct=4), 0.4


def a_catnap():
    rng, secs, fade = random.Random(41), 24, RATE // 2
    n = int(secs * RATE)
    nz = lowpass(lowpass(noise(n + fade, rng), 260), 260)
    flutter = [0.55 + 0.45 * math.sin(2 * math.pi * 26 * i / RATE) for i in range(n + fade)]
    breath = [max(0.0, math.sin(2 * math.pi * 8 * i / (n))) ** 0.7 for i in range(n)] + [0.0] * fade
    mix = seamless(mul(mul(nz, flutter), breath), n, fade)
    return mix, 0.4


def a_sharks():
    rng, secs, fade = random.Random(51), 24, RATE
    n = int(secs * RATE)
    f1, f2 = loop_hz(36.7, secs), loop_hz(55.0, secs)
    drone = [a + 0.4 * b for a, b in zip(osc(f1, n), osc(f2, n, "tri"))]
    swell = [0.7 + 0.3 * math.sin(2 * math.pi * 3 * i / n) for i in range(n)]
    mix = gain(mul(lowpass(drone, 220), swell), 0.5)
    wash = seamless(lowpass(lowpass(noise(n + fade, rng), 180), 180), n, fade)
    mix = list(map(operator.add, mix, gain(wash, 3.0)))
    for at, f0, f1_ in ((3.0, 95, 150), (12.5, 120, 80), (19.0, 80, 130)):
        ln = int(5.0 * RATE)
        call = sweep(f0, f1_, ln, "sine", vib=0.012, vib_hz=0.7)
        call = lowpass(mul(call, env(ln, 0, a=1.8, d=1.6, s=0.0)), 420)
        add_at(mix, gain(call, 0.35), int(at * RATE))
    return mix, 0.5


def a_koi():
    rng, secs, fade = random.Random(53), 24, RATE
    n = int(secs * RATE)
    nz = noise(n + fade, rng)
    lvl = [0.65 + 0.35 * math.sin(2 * math.pi * 5 * i / n) for i in range(n)]
    water = mul(seamless(lowpass(highpass(nz, 250), 700), n, fade), lvl)
    mix = gain(water, 0.5)
    drip = seamless(lowpass(highpass(noise(n + fade, rng), 2500), 4200), n, fade)
    mix = list(map(operator.add, mix, gain(mul(drip, [v * v for v in lvl]), 0.04)))
    koto = Inst("ep", 0.20, a=0.002, d=0.45, s=0.0, r=0.35, gate=1.0, lp=3200)
    scale = ["D", "E", "F#", "A", "B"]
    t = 1.0
    while t < secs - 1.5:
        run = rng.choice((1, 1, 2, 3))
        for j in range(run):
            m = note(rng.choice(scale) + str(rng.choice((4, 4, 5))))
            add_at(mix, gain(koto(m, 1.2), rng.uniform(0.5, 1.0)), int((t + j * 0.22) * RATE))
        t += rng.uniform(1.6, 3.4)
    return mix, 0.45


def a_swirl():
    secs = 24
    mix = pad(["Dsus2", "Bm7", "Gmaj7", "Em9"], secs / 4, 3, 0.07, 3.0, 4.0, shape="sine", detune=0.005)
    mix = lowpass(mix, 1500)
    n = len(mix)
    slow = [0.8 + 0.2 * math.sin(2 * math.pi * 2 * i / n) for i in range(n)]
    return mul(mix, slow), 0.45


def a_dyna():
    rng, secs = random.Random(57), 20
    n = int(secs * RATE)
    mix = [0.0] * n
    for at in (1.5, 5.5, 9.0, 13.0, 16.5):
        ln = int(rng.uniform(0.5, 0.8) * RATE)
        nz = lowpass(highpass(noise(ln, rng), 1300), rng.uniform(3500, 5500))
        e = env(ln, 0, a=0.35, d=0.12, s=0.0)
        add_at(mix, gain(mul(nz, e), 0.55), int(at * RATE))
    bell = Inst("bell", 0.16, a=0.004, d=1.4, s=0.0, r=0.8, gate=1.0, lp=3500)
    for at, m in ((2.4, "E5"), (6.3, "G5"), (9.9, "D5"), (14.0, "A5"), (17.2, "G5")):
        add_at(mix, bell(note(m), 2.0), int(at * RATE))
    return mix, 0.4


def a_moire():
    secs = 24
    n = int(secs * RATE)
    f1 = loop_hz(196.0, secs)
    f2 = loop_hz(294.0, secs)
    pair_a = [a + b for a, b in zip(osc(f1, n), osc(f1 + 6 / secs, n))]
    pair_b = [a + b for a, b in zip(osc(f2, n), osc(f2 + 4 / secs, n))]
    sub = osc(loop_hz(98.0, secs), n)
    mix = [a + 0.45 * b + 0.3 * c for a, b, c in zip(pair_a, pair_b, sub)]
    return mix, 0.4


def a_codefire():
    rng, secs, fade = random.Random(59), 24, RATE
    n = int(secs * RATE)
    hum = [a + 0.5 * b for a, b in zip(osc(loop_hz(55.0, secs), n, "tri"), osc(loop_hz(110.0, secs), n))]
    mix = gain(lowpass(hum, 260), 0.45)
    hiss = seamless(lowpass(highpass(noise(n + fade, rng), 3000), 7000), n, fade)
    mix = list(map(operator.add, mix, gain(hiss, 0.03)))
    crack = [0.0] * n
    t = 0.0
    while t < secs:
        for _ in range(rng.choice((1, 1, 2, 4))):
            ln = int(rng.uniform(0.001, 0.006) * RATE)
            burst = mul(noise(ln, rng), decay(ln, ln / RATE / 3))
            add_at(crack, gain(burst, rng.uniform(0.2, 1.0)), int((t + rng.uniform(0, 0.05)) * RATE))
        t += rng.expovariate(9)
    crack = highpass(crack, 1200)
    return list(map(operator.add, mix, gain(crack, 0.8))), 0.5


def a_meltdown():
    rng, secs, fade = random.Random(61), 20, RATE
    n = int(secs * RATE)
    mix = [0.0] * n
    for m, g in ((45, 1.0), (52, 0.7), (57, 0.6), (60, 0.35)):
        f = loop_hz(hz(m), secs)
        v = sweep(f, f, n, "tri", vib=0.006, vib_hz=5 / secs)
        mix = [a + g * b for a, b in zip(mix, v)]
    mix = lowpass(mix, 650)
    wobble = [0.85 + 0.15 * math.sin(2 * math.pi * 7 * i / n) for i in range(n)]
    mix = mul(mix, wobble)
    hiss = seamless(lowpass(highpass(noise(n + fade, rng), 2000), 5000), n, fade)
    mix = list(map(operator.add, mix, gain(hiss, 0.05)))
    for _ in range(25):
        ln = int(0.003 * RATE)
        add_at(mix, gain(mul(noise(ln, rng), decay(ln, 0.001)), rng.uniform(0.1, 0.4)), rng.randrange(n))
    return mix, 0.45


def a_tixy():
    ch = ["Cmaj9", "Am9", "Fmaj9", "G6"] * 2
    pluck = Inst("ep", 0.2, a=0.003, d=0.35, s=0.0, r=0.25, gate=0.9, lp=3500)
    mix, peak = song(84, 8, [
        (figure(ch, "R 5 O T O 5 T 5", 4), pluck),
        (figure(ch, "R . . . . . . .", 2), Inst("sine", 0.35, a=0.03, d=0.8, s=0.3))], lp=4500)
    return mix, peak


def a_celestial():
    rng, secs = random.Random(67), 32
    mix = pad(["Dsus2", "Gmaj7", "Bm7", "Asus2"], secs / 4, 3, 0.05, 4.0, 5.0, shape="sine", detune=0.003)
    mix = lowpass(mix, 1100)
    n = len(mix)
    drone = [a + 0.5 * b for a, b in zip(osc(loop_hz(hz(note("D2")), secs), n),
                                         osc(loop_hz(hz(note("A2")), secs), n, "tri"))]
    swell = [0.7 + 0.3 * math.sin(2 * math.pi * 2 * i / n) for i in range(n)]
    mix = list(map(operator.add, mix, gain(mul(lowpass(drone, 240), swell), 0.22)))
    sh = bells(secs, ["D", "E", "A", "B"], rng, 0.18, 1, vol=0.06, decay_s=3.5, base_oct=5)
    return list(map(operator.add, mix, sh)), 0.45


def a_daisy():
    """Soft pad under sparse glitch clicks and the odd high bell."""
    rng, secs, fade = random.Random(71), 24, RATE
    mix = pad(["Fmaj9", "Dm9", "Bbmaj7", "C6"], secs / 4, 3, 0.05, 3.0, 4.0, shape="sine", detune=0.004)
    mix = lowpass(mix, 1200)
    n = len(mix)
    hiss = seamless(lowpass(highpass(noise(n + fade, rng), 2500), 6000), n, fade)
    mix = list(map(operator.add, mix, gain(hiss, 0.015)))
    clicks = [0.0] * n
    t = 0.5
    while t < secs:
        for j in range(rng.choice((1, 1, 2, 3))):
            ln = int(rng.uniform(0.002, 0.008) * RATE)
            burst = mul(noise(ln, rng), decay(ln, ln / RATE / 3))
            add_at(clicks, gain(burst, rng.uniform(0.3, 1.0)), int((t + j * 0.07) * RATE))
        t += rng.uniform(0.6, 2.2)
    mix = list(map(operator.add, mix, gain(highpass(clicks, 1800), 0.5)))
    sh = bells(secs, ["F", "A", "C", "E"], rng, 0.15, 1, vol=0.05, decay_s=2.5, base_oct=6)
    return list(map(operator.add, mix, sh)), 0.45


# ------------------------------------------------------------------ effects

def _n(secs):
    return int(secs * RATE)


def fx_swat():
    n, rng = _n(0.14), random.Random(1)
    nz = lowpass(highpass(noise(n, rng), 900), 4000)
    return mul(nz, env(n, 0, a=0.05, d=0.03, s=0)), 0.55


def fx_swoosh():
    n, rng = _n(0.3), random.Random(2)
    nz = lowpass(highpass(noise(n, rng), 500), 2500)
    return mul(nz, env(n, 0, a=0.12, d=0.06, s=0)), 0.45


def fx_splat():
    n, rng = _n(0.18), random.Random(3)
    body = mul(sweep(260, 70, n), decay(n, 0.05))
    sq = mul(lowpass(noise(n, rng), 1800), decay(n, 0.035))
    return list(map(operator.add, body, sq)), 0.65


def fx_drop():
    n = _n(0.14)
    return lowpass(mul(sweep(700, 330, n, "square"), env(n, 0, a=0.004, d=0.06, s=0.2)), 2500), 0.4


def fx_thud():
    n, rng = _n(0.2), random.Random(4)
    body = mul(sweep(130, 55, n), decay(n, 0.06))
    knock = mul(lowpass(noise(n, rng), 900), decay(n, 0.015))
    return list(map(operator.add, body, gain(knock, 0.6))), 0.7


def fx_purr():
    n, rng = _n(0.45), random.Random(5)
    nz = lowpass(lowpass(noise(n, rng), 300), 300)
    flutter = [0.5 + 0.5 * math.sin(2 * math.pi * 24 * i / RATE) for i in range(n)]
    chirp = mul(sweep(520, 780, _n(0.12), "tri"), env(_n(0.12), 0, a=0.01, d=0.05, s=0))
    out = mul(mul(nz, flutter), env(n, 0, a=0.05, d=0.2, s=0))
    out = gain(out, 4.0)
    add_at(out, gain(chirp, 0.25), _n(0.2), wrap=False)
    return out, 0.55


def fx_mrrow():
    n = _n(0.4)
    up = _n(0.15)
    a = sweep(380, 640, up, "pulse25", vib=0.02)
    b = sweep(640, 420, n - up, "pulse25", vib=0.03)
    return lowpass(mul(a + b, env(n, 0, a=0.02, d=0.3, s=0.2)), 1600), 0.5


def fx_hop():
    n = _n(0.13)
    return lowpass(mul(sweep(300, 820, n, "square"), env(n, 0, a=0.003, d=0.07, s=0.3)), 3000), 0.4


def fx_plip():
    n = _n(0.09)
    return mul(sweep(900, 1300, n), decay(n, 0.025)), 0.4


def fx_splash():
    n, rng = _n(0.55), random.Random(6)
    nz = noise(n, rng)
    cut = [1 - math.exp(-2 * math.pi * (3500 * math.exp(-i / (0.15 * RATE)) + 300) / RATE) for i in range(n)]
    y, out = 0.0, []
    for x, a in zip(nz, cut):
        y += a * (x - y)
        out.append(y)
    out = mul(out, env(n, 0, a=0.005, d=0.15, s=0))
    for j in range(4):
        ln = _n(0.04)
        add_at(out, gain(mul(sweep(600 + 150 * j, 1400, ln), decay(ln, 0.012)), 0.15),
               _n(0.18 + j * 0.07), wrap=False)
    return out, 0.55


def fx_peep():
    n = _n(0.09)
    return mul(sweep(1900, 2500, n, "tri"), env(n, 0, a=0.006, d=0.04, s=0)), 0.4


def fx_duckpeep():
    """ducklings join: a happy rising 'pi-peep' from the newest duckling in the line."""
    out = [0.0] * _n(0.26)
    for at, f0, f1, dur in ((0.0, 1900, 2500, 0.06), (0.09, 2200, 3100, 0.11)):
        m = _n(dur)
        v = mul(sweep(f0, f1, m, "tri", vib=0.03, vib_hz=40), env(m, 0, a=0.004, d=0.05, s=0.3))
        add_at(out, v, _n(at), wrap=False)
    return lowpass(out, 5000), 0.38


def fx_quack():
    """ducklings mama: a warm nasal 'quack', a buzzy glide through two formants."""
    n = _n(0.24)
    src = sweep(560, 360, n, "pulse25", vib=0.015, vib_hz=9)
    buzz = [0.6 + 0.4 * math.sin(2 * math.pi * 31 * i / RATE) for i in range(n)]
    src = mul(mul(src, buzz), env(n, 0, a=0.01, d=0.09, s=0.45))
    v = list(map(operator.add, gain(_reson(src, 1150, 2.5), 1.6), gain(_reson(src, 2500, 4), 0.8)))
    return lowpass(list(map(operator.add, v, gain(lowpass(src, 900), 0.4))), 4200), 0.45


def fx_foxsnarl():
    """ducklings fox: a low raspy snarl that swells as the fox crouches to pounce."""
    n, rng = _n(0.6), random.Random(31)
    rasp = [0.45 + 0.55 * abs(math.sin(math.pi * 27 * i / RATE)) for i in range(n)]
    shape = [math.sin(math.pi * min(1.0, i / (0.75 * n))) ** 0.8 for i in range(n)]
    tone = lowpass(sweep(92, 128, n, "pulse25"), 700)
    growl = _reson(mul(noise(n, rng), rasp), 420, 1.8)
    out = [(0.7 * a + 2.2 * b) * r * s for a, b, r, s in zip(tone, growl, rasp, shape)]
    return lowpass(out, 1800), 0.5


def fx_hawkcry():
    """ducklings hawk: a raspy descending 'kee-eeer' screech as it dives."""
    n, rng = _n(0.75), random.Random(41)
    rasp = [0.6 + 0.4 * math.sin(2 * math.pi * 63 * i / RATE) for i in range(n)]
    e = env(n, 0, a=0.03, d=0.35, s=0.15)
    cry = mul(mul(sweep(2900, 1900, n, "tri", vib=0.025, vib_hz=34), rasp), e)
    air = mul(highpass(noise(n, rng), 2400), e)
    return lowpass(list(map(operator.add, cry, gain(air, 0.12))), 6000), 0.36


def fx_nestjingle():
    """ducklings nest: a bright bell arpeggio and a little chorus of peeps as the brood gets home."""
    out = [0.0] * _n(0.9)
    for j, m in enumerate(("D6", "F#6", "A6", "D7")):
        k = _n(0.5 if j == 3 else 0.22)
        add_at(out, gain(mul(osc(hz(note(m)), k, "bell"), decay(k, 0.16 if j == 3 else 0.06)), 0.5),
               _n(j * 0.075), wrap=False)
    for at in (0.36, 0.46):
        m = _n(0.06)
        add_at(out, gain(mul(sweep(2300, 3000, m, "tri"), env(m, 0, a=0.004, d=0.03, s=0)), 0.25),
               _n(at), wrap=False)
    return lowpass(out, 6500), 0.42


def fx_frogleap():
    """froghop takeoff: a springy rising 'bwoip' with a soft wobble."""
    n = _n(0.17)
    body = mul(sweep(240, 760, n, "tri", vib=0.04, vib_hz=28), env(n, 0, a=0.004, d=0.07, s=0.15))
    top = gain(mul(sweep(480, 1520, n), decay(n, 0.04)), 0.25)
    return lowpass(list(map(operator.add, body, top)), 3200), 0.42


def fx_frogland():
    """froghop landing: a soft padded pat on the lily pad and a tiny water plink."""
    n, rng = _n(0.16), random.Random(12)
    pat = mul(sweep(210, 90, n), decay(n, 0.03))
    add_at(pat, gain(mul(lowpass(noise(_n(0.03), rng), 1200), decay(_n(0.03), 0.008)), 0.5), 0, wrap=False)
    m = _n(0.07)
    add_at(pat, gain(mul(sweep(1150, 1750, m), decay(m, 0.018)), 0.35), _n(0.03), wrap=False)
    return pat, 0.45


def fx_ribbit():
    """froghop idle croak: two short raspy chirps, 'rib-bit'."""
    out = [0.0] * _n(0.32)
    for at, f0, f1, dur in ((0.0, 230, 300, 0.1), (0.15, 280, 220, 0.13)):
        m = _n(dur)
        rasp = [0.55 + 0.45 * math.sin(2 * math.pi * 38 * i / RATE) for i in range(m)]
        v = mul(mul(sweep(f0, f1, m, "pulse25"), rasp), env(m, 0, a=0.008, d=0.05, s=0.3))
        add_at(out, lowpass(v, 1500), _n(at), wrap=False)
    return out, 0.35


def fx_frogsnap():
    """froghop bug catch: a quick tongue 'thwip' and a happy two-note gulp."""
    out = [0.0] * _n(0.3)
    n = _n(0.06)
    add_at(out, mul(sweep(2200, 700, n, "tri"), env(n, 0, a=0.002, d=0.03, s=0)), 0, wrap=False)
    for at, m in ((0.08, "E6"), (0.15, "B6")):
        k = _n(0.12)
        add_at(out, gain(mul(osc(hz(note(m)), k, "bell"), decay(k, 0.04)), 0.5), _n(at), wrap=False)
    return out, 0.42


def fx_frogsad():
    """froghop fall-in: a soft sad 'wah-wah' slide after the splash."""
    out = [0.0] * _n(0.75)
    for at, f0, f1, dur in ((0.2, 520, 440, 0.2), (0.42, 440, 300, 0.32)):
        m = _n(dur)
        v = mul(sweep(f0, f1, m, "tri", vib=0.02, vib_hz=7), env(m, 0, a=0.02, d=0.12, s=0.5))
        add_at(out, lowpass(v, 1800), _n(at), wrap=False)
    return out, 0.3


def fx_dig():
    rng = random.Random(7)
    out = [0.0] * _n(0.16)
    for at in (0.0, 0.07):
        ln = _n(0.06)
        add_at(out, mul(lowpass(noise(ln, rng), 1400), decay(ln, 0.015)), _n(at), wrap=False)
    return out, 0.5


def fx_ripple():
    out = [0.0] * _n(0.45)
    for j, m in enumerate(("C6", "D6", "E6", "G6", "A6")):
        ln = _n(0.25)
        add_at(out, gain(mul(osc(hz(note(m)), ln, "bell"), decay(ln, 0.07)), 0.4), _n(j * 0.04), wrap=False)
    return out, 0.35


def fx_sniff():
    rng = random.Random(8)
    out = [0.0] * _n(0.42)
    for j in range(3):
        ln = _n(0.08)
        add_at(out, mul(lowpass(highpass(noise(ln, rng), 1200), 3500), env(ln, 0, a=0.02, d=0.02, s=0)),
               _n(j * 0.12), wrap=False)
    return out, 0.4


def fx_tummy():
    n = _n(0.75)
    w = sweep(420, 190, n, "tri", vib=0.05, vib_hz=7)
    return lowpass(mul(w, env(n, 0, a=0.02, d=0.5, s=0.3)), 1500), 0.55


def fx_coin():
    i = Inst("pulse25", 1.0, a=0.002, d=0.12, s=0.0, r=0.04, gate=1.0, lp=5000)
    out = [0.0] * _n(0.36)
    add_at(out, i(note("B5"), 0.06), 0, wrap=False)
    add_at(out, i(note("E6"), 0.28), _n(0.06), wrap=False)
    return out, 0.45


def fx_bonk():
    n, rng = _n(0.16), random.Random(9)
    body = mul(sweep(240, 110, n, "tri"), decay(n, 0.05))
    click = mul(lowpass(noise(n, rng), 3000), decay(n, 0.006))
    return list(map(operator.add, body, gain(click, 0.5))), 0.6


def fx_tick():
    n = _n(0.03)
    return mul(osc(1800, n), decay(n, 0.006)), 0.18


def fx_clear():
    i = Inst("pulse25", 1.0, a=0.003, d=0.15, s=0.4, r=0.08, gate=0.9, lp=4500)
    out = [0.0] * _n(1.2)
    for j, m in enumerate(("C5", "E5", "G5", "C6")):
        add_at(out, i(note(m), 0.1), _n(j * 0.09), wrap=False)
    for m in ("C5", "E5", "G5", "C6"):
        add_at(out, gain(i(note(m), 0.6), 0.5), _n(0.4), wrap=False)
    return out, 0.5


def fx_gameover():
    i = Inst("tri", 1.0, a=0.01, d=0.3, s=0.6, r=0.15, gate=0.95, lp=2500)
    out = [0.0] * _n(1.9)
    for j, m in enumerate(("G4", "F#4", "F4")):
        add_at(out, i(note(m), 0.3), _n(j * 0.33), wrap=False)
    n = _n(0.8)
    last = mul(sweep(hz(note("E4")), hz(note("E4")), n, "tri", vib=0.012, vib_hz=6),
               env(n, _n(0.1), a=0.01, d=0.6, s=0.4)[:n])
    add_at(out, last, _n(0.99), wrap=False)
    return out, 0.5


def fx_boom():
    n, rng = _n(1.0), random.Random(10)
    body = mul(sweep(90, 38, n), decay(n, 0.25))
    nz = mul(lowpass(noise(n, rng), 700), decay(n, 0.18))
    return list(map(operator.add, body, gain(nz, 1.4))), 0.7


def fx_crackle():
    rng = random.Random(11)
    out = [0.0] * _n(0.5)
    for _ in range(14):
        ln = _n(0.006)
        add_at(out, gain(mul(noise(ln, rng), decay(ln, 0.0015)), rng.uniform(0.3, 1.0)),
               rng.randrange(_n(0.45)), wrap=False)
    return highpass(out, 1500), 0.4


def fx_glitch():
    """A short digital stutter: gated noise bursts over a falling square blip."""
    n, rng = _n(0.16), random.Random(12)
    blip = lowpass(mul(sweep(1400, 500, n, "square"), decay(n, 0.04)), 3500)
    gate = [1.0 if (i // _n(0.012)) % 2 == 0 else 0.0 for i in range(n)]
    nz = mul(mul(highpass(noise(n, rng), 1500), gate), decay(n, 0.06))
    return list(map(operator.add, gain(blip, 0.5), nz)), 0.35


# ------------------------------------------------------------------ cat voice (catnap)

def _curve(pts, u):
    """Smoothstep between (u, value) breakpoints."""
    for (u0, v0), (u1, v1) in zip(pts, pts[1:]):
        if u <= u1:
            t = (u - u0) / (u1 - u0) if u1 > u0 else 1.0
            t = min(1.0, max(0.0, t))
            return v0 + (v1 - v0) * t * t * (3 - 2 * t)
    return pts[-1][1]


def _voice(dur, f0, f1, f2, f3, opening, amp, breath=0.12, am=(0.0, 0.0, 1.0), seed=0):
    """Voiced cat call: harmonics of a gliding f0 weighted by three moving formant peaks
    (additive, so nothing aliases), plus breath noise through a resonance that tracks F2.
    Curves are (u, value) breakpoints over u in [0, 1]; opening scales F2/F3 (closed mouth
    = muffled "m"); am = (rate Hz, depth, until u) rolls an "rrr" trill."""
    n, rng = _n(dur), random.Random(seed)
    tbl = table("sine")
    out = [0.0] * n
    ph = 0.0
    blk = 32
    drift = 0.0
    bws = (180.0, 260.0, 420.0)
    for b0 in range(0, n, blk):
        u = b0 / n
        drift += (rng.uniform(-1, 1) * 0.004 - drift * 0.08)
        fo = _curve(f0, u) * (1 + drift + 0.012 * math.sin(TAU_ * 5.5 * b0 / RATE))
        op = _curve(opening, u)
        forms = ((_curve(f1, u), 1.0), (_curve(f2, u), 0.75 * op), (_curve(f3, u), 0.35 * op * op))
        harms = []
        k = 1
        while k * fo < 7500:
            f = k * fo
            g = sum(gi / (1 + ((f - fi) / (bw / 2)) ** 2) for (fi, gi), bw in zip(forms, bws))
            harms.append((k, (g + 0.006) / k ** 0.55))
            k += 1
        a = _curve(amp, u)
        if am[1] and u < am[2]:
            a *= 1 - am[1] * (0.5 + 0.5 * math.cos(TAU_ * am[0] * b0 / RATE))
        inc = fo * TL / RATE
        for i in range(b0, min(n, b0 + blk)):
            ip = int(ph)
            out[i] = a * sum(h * tbl[(k * ip) & MASK] for k, h in harms)
            ph += inc
    # breath: noise through a state-variable bandpass following F2
    lo = bp = 0.0
    nz = noise(n, rng)
    air = [0.0] * n
    for i in range(n):
        u = i / n
        fc = min(3400.0, _curve(f2, u) * 0.9)
        fq = 2 * math.sin(math.pi * fc / RATE)
        hp_ = nz[i] - lo - 0.5 * bp
        bp += fq * hp_
        lo += fq * bp
        air[i] = bp * (_curve(amp, u) ** 0.7)
    air = lowpass(lowpass(air, 3500), 3500)
    return highpass(list(map(operator.add, out, gain(air, breath * 2.5))), 180)


TAU_ = 2 * math.pi


def fx_meow():
    """"mi-aow": rising then falling pitch while the mouth opens from "i" to "a" to "ow"."""
    return _voice(0.62,
                  f0=[(0, 560), (0.12, 700), (0.35, 820), (0.7, 680), (1, 470)],
                  f1=[(0, 450), (0.15, 900), (0.4, 1300), (0.75, 900), (1, 650)],
                  f2=[(0, 2300), (0.2, 2500), (0.45, 1900), (0.8, 1400), (1, 1150)],
                  f3=[(0, 3600), (0.5, 3300), (1, 3000)],
                  opening=[(0, 0.15), (0.15, 0.8), (0.4, 1.0), (0.8, 0.7), (1, 0.4)],
                  amp=[(0, 0.0), (0.06, 0.55), (0.3, 1.0), (0.7, 0.85), (1, 0.0)],
                  breath=0.12, seed=41), 0.5


def fx_trill():
    """Rolled "brrrp?" greeting: rising pitch, closed mouth, fast amplitude roll."""
    return _voice(0.34,
                  f0=[(0, 480), (0.6, 700), (1, 780)],
                  f1=[(0, 650), (1, 950)],
                  f2=[(0, 1700), (0.7, 1900), (1, 2300)],
                  f3=[(0, 3200), (1, 3400)],
                  opening=[(0, 0.3), (0.7, 0.55), (1, 0.9)],
                  amp=[(0, 0.0), (0.08, 1.0), (0.8, 0.85), (1, 0.0)],
                  breath=0.06, am=(27.0, 0.8, 0.72), seed=42), 0.45


def fx_yawn():
    """Long airy "mraaaow" for the stretch."""
    return _voice(0.95,
                  f0=[(0, 430), (0.25, 560), (0.6, 470), (1, 300)],
                  f1=[(0, 500), (0.3, 1200), (0.7, 1100), (1, 600)],
                  f2=[(0, 1900), (0.35, 1700), (1, 1100)],
                  f3=[(0, 3300), (1, 2900)],
                  opening=[(0, 0.3), (0.3, 1.0), (0.8, 0.8), (1, 0.3)],
                  amp=[(0, 0.0), (0.1, 0.7), (0.35, 1.0), (0.75, 0.6), (1, 0.0)],
                  breath=0.3, seed=43), 0.45


def _paw(seed, cut):
    n, rng = _n(0.11), random.Random(seed)
    nz = highpass(lowpass(lowpass(noise(n, rng), cut), cut * 1.4), 140)
    tap = mul(nz, env(n, 0, a=0.002, d=0.014, s=0))
    thump = mul(sweep(150, 70, n), decay(n, 0.022))
    return list(map(operator.add, tap, gain(thump, 0.35)))


def fx_paw():
    """Soft padded footfall."""
    return _paw(44, 1300), 0.3


def fx_paw2():
    return _paw(45, 1100), 0.28


def _pilebell(m):
    """Soft sandpile bell: a bell partial with a faint octave above, long decay."""
    n = _n(1.8)
    f = hz(note(m))
    body = mul(osc(f, n, "bell"), env(n, 0, a=0.004, d=1.2, s=0))
    shine = mul(osc(2 * f, n), decay(n, 0.25))
    return list(map(operator.add, body, gain(shine, 0.15))), 0.22


# Sandpile avalanche bells, high (small avalanche) to low (large), in the ambient's scale.
def fx_pilebell0():
    return _pilebell("E6")


def fx_pilebell1():
    return _pilebell("C6")


def fx_pilebell2():
    return _pilebell("A5")


def fx_pilebell3():
    return _pilebell("G5")


def fx_pilebell4():
    return _pilebell("E5")


def a_undersea():
    """reef: a low ocean bed, a filtered wash that swells three times per loop under a faint sine pad."""
    rng, secs, fade = random.Random(61), 32, RATE
    n = int(secs * RATE)
    nz = noise(n + fade, rng)
    w1, w2 = 2 * math.pi * 3 / secs / RATE, 2 * math.pi * 5 / secs / RATE
    y, wash = 0.0, []
    for i, x in enumerate(nz):
        a = 1 - math.exp(-2 * math.pi * (170 + 90 * math.sin(w1 * i) + 40 * math.sin(w2 * i)) / RATE)
        y += a * (x - y)
        wash.append(y * (0.55 + 0.45 * math.sin(w1 * i - 0.6)))
    wash = seamless(lowpass(wash, 400), n, fade)
    mix = pad(["Dmaj9", "Bm9"], secs / 2, 2, 0.05, 5.0, 7.0, shape="sine")
    mix = lowpass(mix, 520)
    return list(map(operator.add, gain(wash, 5.0), mix)), 0.45


def fx_bubblepop():
    """reef: a soft pop as a bubble breaks the surface."""
    n = _n(0.07)
    return lowpass(mul(sweep(520, 1500, n), decay(n, 0.016)), 3200), 0.3


def fx_gurgle():
    """reef: a vent burping a handful of bubbles."""
    rng = random.Random(62)
    out = [0.0] * _n(0.9)
    t = 0.0
    for _ in range(6):
        ln = _n(rng.uniform(0.04, 0.08))
        f0 = rng.uniform(260, 520)
        b = mul(sweep(f0, f0 * rng.uniform(1.6, 2.2), ln), env(ln, 0, a=0.004, d=0.025, s=0))
        add_at(out, gain(b, rng.uniform(0.5, 1.0)), _n(t), wrap=False)
        t += rng.uniform(0.06, 0.13)
    return lowpass(out, 1800), 0.35


def fx_whalecall():
    """reef: a distant humpback moan, rising then sinking, with a faint echo."""
    n = _n(3.8)
    pts = ((0.0, 170.0), (0.4, 310.0), (0.55, 300.0), (1.0, 135.0))
    tbl, ph, out = table("sine"), 0.0, []
    k = 2 * math.pi * 4.0 / RATE
    for i in range(n):
        f = _curve(pts, i / n) * (1 + 0.012 * math.sin(k * i))
        out.append(tbl[int(ph) & MASK] + 0.3 * tbl[int(ph * 0.5) & MASK])
        ph += f * TL / RATE
    call = lowpass(mul(out, env(n - _n(1.0), _n(1.0), a=0.7, d=1.6, s=0.5)), 750)
    mix = call + [0.0] * _n(1.2)
    add_at(mix, gain(call, 0.3), _n(1.0), wrap=False)
    return lowpass(mix, 600), 0.45


# ------------------------------------------------------------------ typewriter

def _reson(buf, f, q):
    """Two-pole bandpass (RBJ, 0 dB peak): a struck-metal ring when fed a short burst."""
    w0 = 2 * math.pi * f / RATE
    al = math.sin(w0) / (2 * q)
    a0 = 1 + al
    b0, a1, a2 = al / a0, -2 * math.cos(w0) / a0, (1 - al) / a0
    x1 = x2 = y1 = y2 = 0.0
    out = []
    app = out.append
    for x in buf:
        y = b0 * (x - x2) - a1 * y1 - a2 * y2
        x2, x1, y2, y1 = x1, x, y1, y
        app(y)
    return out


def _burst(n, tau, rng):
    return mul(noise(n, rng), decay(n, tau))


def _tw_click(n, f, q, tau, rng):
    return _reson(_burst(n, tau, rng), f, q)


def _tw_clack(seed, ring, body, esc_at):
    """A typebar strike: a bright slug-on-platen crack, the bar's ring, a woody body
    knock and, a beat later, the escapement letting the carriage step."""
    n, rng = _n(0.12), random.Random(seed)
    crack = gain(highpass(_burst(n, 0.0012, rng), 2500), 0.9)
    ring_ = gain(_tw_click(n, ring, 14, 0.002, rng), 2.2)
    knock = gain(_tw_click(n, body, 3.5, 0.004, rng), 2.6)
    thock = gain(mul(sweep(210, 120, n), decay(n, 0.014)), 0.35)
    out = [a + b + c + d for a, b, c, d in zip(crack, ring_, knock, thock)]
    tick = gain(_tw_click(_n(0.03), 3600 + 300 * rng.random(), 8, 0.0015, rng), 0.9)
    add_at(out, tick, _n(esc_at), wrap=False)
    return out


def fx_tw_clack0():
    return _tw_clack(71, 2900, 420, 0.032), 0.6


def fx_tw_clack1():
    return _tw_clack(72, 3250, 380, 0.036), 0.58


def fx_tw_clack2():
    return _tw_clack(73, 2650, 460, 0.029), 0.6


def fx_tw_clack3():
    return _tw_clack(74, 3500, 400, 0.04), 0.56


def fx_tw_space():
    """The space bar: a heavier, duller thunk and the escapement, no typebar."""
    n, rng = _n(0.16), random.Random(75)
    body = gain(mul(sweep(150, 85, n), decay(n, 0.035)), 0.8)
    knock = gain(_tw_click(n, 240, 2.5, 0.006, rng), 2.4)
    out = [a + b for a, b in zip(body, knock)]
    add_at(out, gain(_tw_click(_n(0.03), 3300, 8, 0.0015, rng), 0.5), _n(0.045), wrap=False)
    return lowpass(out, 5000), 0.62


def fx_tw_back():
    """Backspace or tab: a soft, low click of the carriage being nudged."""
    n, rng = _n(0.06), random.Random(76)
    out = [a + b for a, b in zip(gain(_tw_click(n, 1500, 5, 0.0015, rng), 1.6),
                                 gain(mul(osc(360, n), decay(n, 0.008)), 0.25))]
    return lowpass(out, 3500), 0.32


def fx_tw_bell():
    """The margin bell: a small struck bell, inharmonic partials with slow beating."""
    n, rng = _n(1.4), random.Random(77)
    f0 = 2380.0
    out = [0.0] * n
    for ratio, amp, tau in ((1.0, 1.0, 0.55), (2.32, 0.42, 0.28), (4.25, 0.2, 0.14), (6.63, 0.1, 0.07)):
        f = f0 * ratio
        if f > RATE / 2.2:
            continue
        tone = [a + 0.5 * b for a, b in zip(osc(f, n), osc(f * 1.0013, n))]
        add_at(out, gain(mul(tone, decay(n, tau)), amp), 0, wrap=False)
    add_at(out, gain(highpass(_burst(_n(0.01), 0.001, rng), 3000), 0.6), 0, wrap=False)
    return out, 0.42


def fx_tw_return():
    """Carriage return: a falling filtered-noise zip as the carriage slides, a run of
    pawl clicks, then the thunk of the carriage hitting the margin stop."""
    rng = random.Random(78)
    slide, n = _n(0.34), _n(0.5)
    nz = noise(slide, rng)
    low = band = 0.0
    zip_ = []
    for i, x in enumerate(nz):
        u = i / slide
        fc = 2600 * (1 - u) + 650 * u
        f = 2 * math.sin(math.pi * fc / RATE)
        low += f * band
        high = x - low - 0.25 * band
        band += f * high
        zip_.append(band * (min(1.0, i / _n(0.03)) * (1 - u) ** 0.4))
    out = gain(zip_, 0.55) + [0.0] * (n - slide)
    t = 0.0
    while t < 0.3:
        add_at(out, gain(_tw_click(_n(0.02), 2400 + 600 * rng.random(), 9, 0.001, rng), 0.35), _n(t), wrap=False)
        t += 0.016 + 0.05 * t
    stop = _n(0.335)
    add_at(out, gain(mul(sweep(130, 70, _n(0.15)), decay(_n(0.15), 0.035)), 1.0), stop, wrap=False)
    add_at(out, gain(_tw_click(_n(0.12), 300, 2.5, 0.006, rng), 2.4), stop, wrap=False)
    return out, 0.6


def fx_tw_feed():
    """Line feed: the platen ratchet clicking over one notch, with a low clunk."""
    n, rng = _n(0.16), random.Random(79)
    out = gain(mul(sweep(180, 95, n), decay(n, 0.03)), 0.6)
    for at, g in ((0.0, 1.0), (0.032, 0.7)):
        add_at(out, gain(_tw_click(_n(0.04), 2700, 7, 0.0012, rng), g), _n(at), wrap=False)
    add_at(out, gain(_tw_click(n, 520, 3, 0.004, rng), 1.6), 0, wrap=False)
    return out, 0.5


# ------------------------------------------------------------------ registry / cache


def fx_swell():
    """swirl: a soft rising-and-falling pad swell with a breath of filtered noise."""
    n, rng = _n(3.0), random.Random(11)
    shape = [math.sin(math.pi * i / n) ** 2 for i in range(n)]
    mix = [0.0] * n
    for m, g in (("D4", 0.5), ("A4", 0.35), ("E5", 0.22)):
        f = hz(note(m))
        add_at(mix, gain(mul(osc(f, n), shape), g), 0, wrap=False)
        add_at(mix, gain(mul(osc(f * 1.004, n), shape), g * 0.6), 0, wrap=False)
    air = lowpass(highpass(noise(n, rng), 600), 2200)
    add_at(mix, gain(mul(air, shape), 0.08), 0, wrap=False)
    return lowpass(mix, 2400), 0.3


def a_ink():
    """ink: a faint water hush whose filter breathes slowly, under an airy open-fifth pad."""
    rng, secs, fade = random.Random(71), 32, RATE
    n = int(secs * RATE)
    nz = noise(n + fade, rng)
    w1, w2 = 2 * math.pi * 2 / secs / RATE, 2 * math.pi * 5 / secs / RATE
    y, hush = 0.0, []
    for i, x in enumerate(nz):
        a = 1 - math.exp(-2 * math.pi * (520 + 220 * math.sin(w1 * i) + 90 * math.sin(w2 * i)) / RATE)
        y += a * (x - y)
        hush.append(y * (0.6 + 0.4 * math.sin(w1 * i + 1.1)))
    hush = seamless(highpass(hush, 160), n, fade)
    air = seamless(lowpass(highpass(noise(n + fade, rng), 2400), 5200), n, fade)
    mix = pad(["Fsus2", "Csus2", "Dm7", "Bbmaj7"], secs / 4, 3, 0.05, 5.0, 6.0, shape="sine", detune=0.004)
    mix = lowpass(mix, 1100)
    slow = [0.75 + 0.25 * math.sin(w1 * i - 0.4) for i in range(n)]
    return [p * s + h * 2.2 + a * 0.05 for p, s, h, a in zip(mix, slow, hush, air)], 0.3


def fx_inkdrip():
    """ink: a soft low bloop and a faint high plink as a stalled head pools into a blot."""
    n = _n(0.32)
    bloop = mul(sweep(520, 240, n), env(n, 0, a=0.006, d=0.07, s=0))
    ln = _n(0.12)
    add_at(bloop, gain(mul(sweep(1500, 1750, ln), decay(ln, 0.03)), 0.18), _n(0.03), wrap=False)
    return lowpass(bloop, 2200), 0.3


def fx_sharkpass():
    """sharks: a low swell of displaced water as a shark glides close, the tone sagging as it passes."""
    n, rng = _n(4.5), random.Random(81)
    shape = [math.sin(math.pi * i / n) ** 2 * (1 - 0.3 * i / n) for i in range(n)]
    tone = [a + 0.45 * b for a, b in zip(sweep(64, 47, n), sweep(128, 94, n, "tri"))]
    mix = gain(mul(lowpass(tone, 260), shape), 0.7)
    push = lowpass(lowpass(highpass(noise(n, rng), 50), 320), 320)
    add_at(mix, gain(mul(push, shape), 2.6), 0, wrap=False)
    rush = lowpass(highpass(noise(n, rng), 300), 900)
    add_at(mix, gain(mul(rush, [v ** 3 for v in shape]), 0.12), 0, wrap=False)
    return mix, 0.4


def fx_jellyglow():
    """jellyfish: a soft glassy chime as a jelly flashes, three notes of the pad's Cmaj9
    rolled upward, each with an inharmonic shimmer partial, over a faint airy breath."""
    n, rng = _n(3.2), random.Random(91)
    mix = [0.0] * n
    for k, (m, g) in enumerate((("B5", 0.5), ("E6", 0.42), ("G6", 0.32))):
        f = hz(note(m))
        ln = n - _n(0.09 * k)
        body = mul(osc(f, ln, "bell"), env(ln, 0, a=0.018, d=1.3, s=0))
        trem = [1 + 0.25 * math.sin(2 * math.pi * 5.5 * i / RATE) for i in range(ln)]
        glass = mul(mul(osc(f * 2.76, ln), decay(ln, 0.5)), trem)
        add_at(mix, gain(list(map(operator.add, body, gain(glass, 0.22))), g), _n(0.09 * k), wrap=False)
    air = lowpass(highpass(noise(n, rng), 2500), 6000)
    swell = [math.sin(math.pi * min(1.0, i / (0.7 * n))) ** 2 for i in range(n)]
    add_at(mix, gain(mul(air, swell), 0.03), 0, wrap=False)
    tail = _n(0.5)
    for i in range(tail):
        mix[n - tail + i] *= (1 - i / tail) ** 2
    return lowpass(mix, 5000), 0.28


def _koiplop(f0, f1, seed):
    """koi: a soft water plop as a koi breaks the surface: a rising bubble tone over a low
    thump and a breath of splash, then one small drip."""
    n, rng = _n(0.5), random.Random(seed)
    mix = [0.0] * n
    ln = _n(0.16)
    add_at(mix, mul(sweep(f0, f1, ln), env(ln, 0, a=0.004, d=0.05, s=0)), _n(0.015), wrap=False)
    lt = _n(0.12)
    add_at(mix, gain(mul(sweep(140, 70, lt), decay(lt, 0.03)), 0.6), 0, wrap=False)
    splash = lowpass(highpass(noise(n, rng), 700), 2600)
    add_at(mix, gain(mul(splash, decay(n, 0.05)), 0.16), 0, wrap=False)
    ld = _n(0.06)
    add_at(mix, gain(mul(sweep(f1 * 0.9, f1 * 1.3, ld), decay(ld, 0.015)), 0.22), _n(0.22), wrap=False)
    return lowpass(mix, 3000), 0.32


def fx_koiplop0():
    return _koiplop(380, 900, 101)


def fx_koiplop1():
    return _koiplop(320, 760, 102)


def fx_koiplop2():
    return _koiplop(440, 1020, 103)

MUSIC = {"bugsquash": m_bugsquash, "catstack": m_catstack, "froghop": m_froghop,
         "ducklings": m_ducklings, "forage": m_forage, "bonkyon": m_bonkyon}
AMBIENT = {"campfire": a_campfire, "reef": a_reef, "forest": a_forest, "jellyfish": a_jellyfish,
           "blackhole": a_blackhole, "skyline": a_skyline, "sandpile": a_sandpile,
           "spacecol": a_spacecol, "default": a_default, "catnap": a_catnap,
           "sharks": a_sharks, "koi": a_koi, "swirl": a_swirl, "dyna": a_dyna, "moire": a_moire,
           "codefire": a_codefire, "meltdown": a_meltdown, "tixy": a_tixy,
           "celestial": a_celestial, "daisy": a_daisy, "undersea": a_undersea,
           "ink": a_ink}
LOOP_OVERLAP = 0.12  # seconds
SFX = {name[3:]: fn for name, fn in globals().items() if name.startswith("fx_")}
RECIPES = {**MUSIC, **AMBIENT, **SFX}


def _file(name):
    return os.path.join(CACHE_DIR, f"{name}-{VERSION}.wav")


def cached(name):
    p = _file(name)
    return p if os.path.exists(p) else None


def render(name):
    """Return 16-bit PCM bytes for a recipe."""
    buf, peak = RECIPES[name]()
    top = max(map(abs, buf)) or 1.0
    k = peak * 32767 / top
    fade = min(len(buf) // 4, 44)  # 2 ms to zero at both ends so restarts never click
    for i in range(fade):
        buf[i] *= i / fade
        buf[-1 - i] *= i / fade
    if name in AMBIENT:  # audio.py overlaps consecutive loops by LOOP_OVERLAP; these ramps blend them
        ramp = int(LOOP_OVERLAP * RATE)
        for i in range(ramp):
            g = math.sin(i / ramp * math.pi / 2)
            buf[i] *= g
            buf[-1 - i] *= g
    return array.array("h", [int(v * k) for v in buf]).tobytes()


def write(name, path):
    tmp = f"{path}.{os.getpid()}.part"
    with wave.open(tmp, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(render(name))
    os.replace(tmp, path)


def path(name):
    """Cached WAV path for a recipe, rendering it first if needed; None if unknown."""
    if name not in RECIPES:
        return None
    p = _file(name)
    if os.path.exists(p):
        return p
    os.makedirs(CACHE_DIR, exist_ok=True)
    write(name, p)
    pat = re.compile(re.escape(name) + r"-[0-9a-f]{10}\.wav(\.\d+\.part)?$")
    now = time.time()
    for fn in os.listdir(CACHE_DIR):
        old = os.path.join(CACHE_DIR, fn)
        if pat.match(fn) and old != p and (not fn.endswith(".part") or now - os.path.getmtime(old) > 60):
            try:
                os.remove(old)
            except OSError:
                pass
    return p


def main(argv):
    if argv[:1] == ["--cache"]:
        for name in argv[1:]:
            path(name)
        return 0
    names = argv or list(RECIPES)
    out = tempfile.mkdtemp(prefix="claude-fun-synth-")
    worst = 0.0
    for name in names:
        t0 = time.perf_counter()
        write(name, os.path.join(out, name + ".wav"))
        dt = time.perf_counter() - t0
        worst = max(worst, dt)
        with wave.open(os.path.join(out, name + ".wav")) as w:
            secs = w.getnframes() / RATE
        print(f"{name:10} {dt:5.2f}s to render  {secs:5.1f}s long")
    print(f"worst {worst:.2f}s; files in {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
