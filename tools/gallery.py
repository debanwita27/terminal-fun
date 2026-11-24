#!/usr/bin/env python3
"""Generate gallery.html: a cheat sheet of every piece with a colour still of each.

Usage: tools/gallery.py [-o gallery.html] [--only NAME ...]

Each shot runs a piece under a pty (colour on), replays the byte stream into a
virtual screen and keeps the final screen. Status and score files go to a temp dir.
"""
import argparse
import html
import os
import re
import shutil
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.realpath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)
from bench import run_pty  # noqa: E402
from test_render import frame_bodies, replay  # noqa: E402

UP, DOWN, RIGHT, LEFT = "\x1b[A", "\x1b[B", "\x1b[C", "\x1b[D"


def S(piece, label, args=(), frames=200, fps=40, size=(100, 30), keys=(), seeds=None):
    """One capture. keys: (seconds, text) typed into the pty. seeds: retry with each
    --seed and keep the screen whose HUD "Height N" is tallest (blind key presses are luck)."""
    return dict(piece=piece, label=label, args=list(args), frames=frames, fps=fps,
                size=size, keys=list(keys), seeds=seeds)


SHOTS = [
    S("forest", "spring", ["--season", "spring", "--seed", "3"], 500, 100),
    S("forest", "summer", ["--season", "summer", "--seed", "3"], 500, 100),
    S("forest", "autumn", ["--season", "autumn", "--seed", "3"], 500, 100),
    S("forest", "winter", ["--season", "winter", "--seed", "3"], 500, 100),
    S("sandpile", "mandala", ["--seed", "4"], 134, 2),  # time-scaled: the edges at ~64s, then a 6s hold
    S("spacecol", "tree", ["--mode", "tree", "--seed", "2"], 800, 100),
    S("spacecol", "roots", ["--mode", "roots", "--seed", "2"], 700, 100),
    S("spacecol", "lightning", ["--mode", "lightning", "--seed", "2"], 250, 100),
    S("spacecol", "coral", ["--mode", "coral", "--seed", "2"], 450, 100),
    S("spacecol", "veins", ["--mode", "veins", "--seed", "2"], 700, 100),
    S("skyline", "day", ["--start", "0.3", "--no-plane", "--seed", "3"], 60, 40),
    S("skyline", "dusk", ["--start", "0.56", "--seed", "3"], 60, 40),
    S("skyline", "night", ["--start", "0.7", "--seed", "3"], 60, 40),
    S("fireworks", "mid-show", [], 160, 40),
    S("blackhole", "accretion disk", ["--seed", "1"], 80, 40),
    S("jellyfish", "the deep", ["--seed", "1"], 120, 40),
    S("excuses", "excuse", [], 240, 40),
    S("excuses-progress", "progress", ["--progress"], 80, 40),
    S("catnap", "demo", ["--demo"], 60, 40),
    S("campfire", "campfire", [], 120, 40),
    S("reef", "reef", ["--seed", "4"], 200, 40, (110, 34)),
    S("reef", "visitor", ["--seed", "4", "--visitor", "manta"], 80, 40, (110, 34)),
    S("biplane", "banner", ["--text", "hello"], 120, 40),
    S("hourglass", "rainbow sand", ["--sand", "rainbow", "--seed", "1"], 200, 40),
    S("celestial", "saturn", ["--scene", "saturn", "--seed", "1"], 240, 12),
    S("celestial", "moonrise", ["--scene", "moonrise", "--seed", "1"], 360, 12),
    S("celestial", "sunset", ["--scene", "sunset", "--seed", "1"], 360, 12),
    S("sharks", "mosaic", ["--count", "2", "--style", "a", "--seed", "4"], 200, 20, (110, 34)),
    S("sharks", "swarm", ["--count", "2", "--style", "b", "--seed", "3"], 600, 20, (110, 34)),
    S("sharks", "mix", ["--count", "3", "--seed", "4"], 300, 20, (110, 34)),
    S("koi", "pond", ["--count", "5", "--seed", "3"], 160, 20, (110, 34)),
    S("swirl", "jelly", ["--form", "1", "--seed", "1"], 60, 12),
    S("swirl", "ribbon", ["--form", "2", "--seed", "1"], 60, 12),
    S("swirl", "knot", ["--form", "3", "--seed", "1"], 300, 12),
    S("swirl", "original", ["--form", "original", "--seed", "1"], 60, 12),
    S("swirl", "medusa", ["--form", "medusa", "--seed", "1"], 150, 12),
    S("swirl", "torus knot", ["--form", "torusknot", "--seed", "1"], 100, 12),
    S("swirl", "tesseract", ["--form", "tesseract", "--seed", "1"], 100, 12),
    S("swirl", "breathing", ["--form", "breathing", "--seed", "1"], 120, 12),
    S("dyna", "ink", ["--seed", "2"], 160, 12),
    S("moire", "moire", ["--seed", "1"], 80, 12),
    S("codefire", "burning", ["--seed", "1"], 120, 12),
    S("meltdown", "melting", ["--seed", "1"], 200, 12),
    S("tixy", "formula", ["--mode", "tixy", "--seed", "2"], 60, 12),
    S("tixy", "metaballs", ["--mode", "meta", "--seed", "2"], 60, 12),
    S("daisy", "collage", ["--theme", "red", "--seed", "1"], 84, 12),
    S("daisy", "poster", ["--theme", "poster", "--seed", "1"], 36, 12),
    S("daisy", "meadow", ["--theme", "meadow", "--seed", "1"], 72, 12),
    S("ink", "paper", ["--theme", "paper", "--seed", "5"], 60, 12, (120, 40)),
    S("ink", "night", ["--theme", "night", "--seed", "5"], 60, 12, (120, 40)),
    S("bugsquash", "mid-round", ["--start", "--seed", "1"], 140, 30, (80, 30),
      [(1.0, RIGHT), (1.5, " "), (2.5, DOWN), (3.0, " ")]),
    S("catstack", "tower", ["--start"], 160, 20, (60, 30),
      [(0.5 + 0.8 * i, " ") for i in range(8)], seeds=range(1, 9)),
    S("froghop", "demo", ["--demo", "--seed", "1"], 160, 40, (80, 30)),
    S("ducklings", "demo", ["--demo", "--seed", "1"], 160, 40, (80, 30)),
    S("forage", "after a dig", ["--seed", "5"], 120, 30, (100, 30),
      [(0.5, "x"), (1.0, RIGHT), (1.2, DOWN), (1.5, " ")]),
    S("bonkyon", "level 6", ["--level", "6"], 60, 30, (80, 30), [(0.5, "x")]),
    S("bonkyon", "endless", ["--endless", "--seed", "7"], 60, 30, (80, 30), [(0.5, "x")]),
    S("bonkyon", "copy rule", ["--level", "11"], 60, 30, (80, 30), [(0.5, "x")]),
    # --warp fast-forwards the autopilot (hidden flag) so the still lands mid-fight.
    S("bullethell", "mid-fight", ["--demo", "--seed", "4", "--warp", "75.4"], 6, 30, (120, 40)),
    S("typewriter", "autopilot art", ["--auto", "--seed", "8", "--speed", "4"], 560, 40, (110, 42)),
]

# Variants and flags per piece, beyond the META entry; controls only for games.
EXTRA = {
    "forest": dict(flags=["--season spring|summer|autumn|winter", "--season-length S", "--day-length S",
                          "--start P", "--speed X", "--seed N"]),
    "sandpile": dict(flags=["--drops N|random", "--palette NAME", "--seed N"]),
    "spacecol": dict(flags=["--mode tree|roots|lightning|coral|veins", "--seed N"]),
    "skyline": dict(flags=["--cycle S", "--start P", "--no-plane", "--seed N"]),
    "fireworks": dict(flags=["--finale"]),
    "blackhole": dict(flags=["--tilt DEG", "--speed X", "--seed N"]),
    "jellyfish": dict(flags=["--count N", "--seed N"]),
    "reef": dict(flags=["--visitor manta|turtle|whale", "--seed N"]),
    "excuses": dict(flags=["--progress"]),
    "catnap": dict(flags=["--demo"]),
    "biplane": dict(flags=["--text \"hi\""]),
    "sharks": dict(flags=["--count N", "--style a|b|mix", "--seed N"]),
    "koi": dict(flags=["--count N", "--seed N"]),
    "swirl": dict(flags=["--form NAME|1|2|3", "--list-forms", "--palette NAME", "--drift", "--no-drift",
                            "--points N", "--speed X", "--seed N"]),
    "dyna": dict(flags=["--speed X", "--look paper|board|both", "--seed N"]),
    "moire": dict(flags=["--speed X", "--seed N"]),
    "codefire": dict(flags=["--seed N"]),
    "meltdown": dict(flags=["--seed N"]),
    "tixy": dict(flags=["--mode tixy|meta|both", "--seed N"]),
    "daisy": dict(flags=["--theme mono|paper|red|pink|poster|meadow", "--seed N"]),
    "ink": dict(flags=["--theme paper|night", "--count N", "--seed N"]),
    "bugsquash": dict(flags=["--start", "--seed N"],
                      controls="arrows/WASD move, space swat, r restart"),
    "catstack": dict(flags=["--start", "--seed N"], controls="space drops, r restart"),
    "froghop": dict(flags=["--demo", "--seed N"], controls="space charge, space leap, r restart"),
    "ducklings": dict(flags=["--demo", "--seed N"], controls="hold arrows/WASD to swim, r restart"),
    "forage": dict(flags=["--size NAME", "--density D", "--hex", "--daily", "--seed N"],
                   controls="arrows/WASD move, space forage/chord, f flag, t pig, r new board"),
    "bonkyon": dict(flags=["--level N", "--endless", "--daily", "--seed N", "--solve"],
                    controls="arrows/WASD move, u undo, r restart, n/b next/previous level"),
    "bullethell": dict(flags=["--difficulty easy|normal|hard", "--seed N", "--daily", "--floor N", "--demo"],
                       controls="WASD move, arrows shoot (two for diagonals) or mouse aim + hold, space dash, "
                                "f swap weapon, e buy/pick up, p pause, r new run"),
    "typewriter": dict(flags=["--auto", "--speed X", "--finish mint|olive|black|red", "--save FILE", "--seed N"],
                       controls="every key types; Enter return, Backspace back, Tab, up/down platen, "
                                "Esc m mute, Ctrl-C/Ctrl-D quit"),
}
SKIP_PIECES = {"excuses-progress"}  # shown as a shot of excuses


def capture(shot, entries, env):
    if not shot["seeds"]:
        return capture_once(shot, entries, env)
    best, best_h = None, -1
    for seed in shot["seeds"]:
        one = dict(shot, args=shot["args"] + ["--seed", str(seed)])
        scr = capture_once(one, entries, env)
        text = "".join(c[0] for r in scr[:2] for c in r)
        m = re.search(r"Height\s+(\d+)", text)
        h = int(m.group(1)) if m and "GAME" not in text.upper() else -1
        if h > best_h:
            best, best_h = scr, h
    return best


def capture_once(shot, entries, env):
    path = entries[shot["piece"]]["script"] if shot["piece"] in entries else None
    name = shot["piece"]
    if name == "excuses-progress":
        path = entries["excuses"]["script"]
    cols, rows = shot["size"]
    argv = [sys.executable, path, *shot["args"], "--frames", str(shot["frames"]),
            "--fps", str(shot["fps"])]
    pending = sorted(shot["keys"])

    def feed(fd, elapsed, out):
        while pending and elapsed >= pending[0][0]:
            os.write(fd, pending.pop(0)[1].encode())

    t0 = time.monotonic()
    status, _, out, _ = run_pty(argv, cols, rows, env, feed, timeout=120)
    screen = replay(frame_bodies(out), cols, rows)
    code = os.waitstatus_to_exitcode(status)
    cells = sum(1 for r in screen for c in r if c[0] != " " or c[2] is not None)
    print(f"{name:18} {shot['label']:16} exit={code} bytes={len(out):7} "
          f"cells={cells:5} {time.monotonic() - t0:5.1f}s")
    return screen


# xterm-256 palette: 16 system colours, 6x6x6 cube, 24 greys.
def build_palette():
    sysc = ["000000", "cd0000", "00cd00", "cdcd00", "0000ee", "cd00cd", "00cdcd", "e5e5e5",
            "7f7f7f", "ff0000", "00ff00", "ffff00", "5c5cff", "ff00ff", "00ffff", "ffffff"]
    pal = ["#" + c for c in sysc]
    lv = [0, 95, 135, 175, 215, 255]
    pal += ["#%02x%02x%02x" % (lv[r], lv[g], lv[b]) for r in range(6) for g in range(6) for b in range(6)]
    pal += ["#%02x%02x%02x" % ((8 + 10 * i,) * 3) for i in range(24)]
    return pal


PAL = build_palette()


def css(c):
    """256-colour index or (r, g, b) tuple -> CSS colour."""
    return PAL[c] if isinstance(c, int) else "#%02x%02x%02x" % tuple(c)


def screen_html(screen):
    """Rows of cells -> <pre> body, merging runs of identical (fg, bg)."""
    lines = []
    for row in screen:
        end = len(row)
        while end and row[end - 1][0] == " " and row[end - 1][2] is None:
            end -= 1
        parts, run, key = [], [], None
        for ch, fg, bg in row[:end]:
            if ch == " ":
                fg = None  # fg is invisible on a space
            k = (fg, bg)
            if k != key and run:
                parts.append((key, "".join(run)))
                run = []
            key = k
            run.append(ch)
        if run:
            parts.append((key, "".join(run)))
        out = []
        for (fg, bg), text in parts:
            n = len(text)
            text = html.escape(text, quote=False)
            # Braille and block glyphs fall back to fonts with other advance widths;
            # pinning each run to n ch keeps columns aligned whatever font draws them.
            st = f"width:{n}ch" + (f";color:{css(fg)}" if fg is not None else "") + \
                 (f";background:{css(bg)}" if bg is not None else "")
            out.append(f'<span class="r" style="{st}">{text}</span>')
        lines.append("".join(out))
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines)


def esc(s):
    return html.escape(s, quote=True)


def card(entry, shots, quick):
    name = entry["name"]
    ex = EXTRA.get(name, {})
    kind = entry["kind"]
    cmd = f"./wait-fun {kind} {name}"
    h = [f'<article class="card"><h3>{esc(name)}</h3>',
         f'<p class="blurb">{esc(entry.get("blurb", ""))}</p>']
    for c in ([entry["credit"]] if isinstance(entry.get("credit"), dict) else entry.get("credit") or []):
        who = (f'<a href="{esc(c["url"])}">{esc(c["who"])}</a>' if c.get("url")
               else esc(c["who"]))  # some originals (artist unknown) have no link
        h.append(f'<p class="credit">{esc(c["type"])} {who}</p>')
    h.append('<div class="shots">')
    for label, scr in shots:
        h.append(f'<figure><div class="screen" tabindex="0" role="button" aria-label="enlarge {esc(name)} {esc(label)}">'
                 f'<pre>{scr}</pre></div><figcaption>{esc(label)}</figcaption></figure>')
    h.append("</div>")
    h.append(f'<code class="cmd">{esc(cmd)}</code>')
    for v in entry.get("variants") or {}:
        h.append(f'<code class="cmd">{esc("./wait-fun " + v)}</code>')
    if ex.get("flags"):
        h.append('<p class="flags">' + " ".join(f"<code>{esc(f)}</code>" for f in ex["flags"]) + "</p>")
    if ex.get("controls"):
        h.append(f'<p class="controls"><b>Controls</b> {esc(ex["controls"])}</p>')
    h.append("</article>")
    return "\n".join(h)


CSS = """
:root{color-scheme:dark}
*{box-sizing:border-box}
body{margin:0;background:#0d0f14;color:#d6d9e0;font:15px/1.5 -apple-system,"Segoe UI",Helvetica,Arial,sans-serif}
a{color:#7cb7ff}
header,main,footer{max-width:1280px;margin:0 auto;padding:0 20px}
header{padding-top:36px}
h1{margin:0 0 4px;font-size:30px}
h2{margin:40px 0 14px;font-size:22px;border-bottom:1px solid #2a2f3a;padding-bottom:6px}
.sub{margin:0 0 18px;color:#9aa1b0}
.quick{background:#141821;border:1px solid #2a2f3a;border-radius:8px;padding:12px 16px;
 font:13px/1.7 Menlo,"DejaVu Sans Mono",monospace;overflow-x:auto}
.quick span{color:#6b7385}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%,500px),1fr));gap:18px}
.card{background:#141821;border:1px solid #2a2f3a;border-radius:10px;padding:14px;min-width:0}
.card h3{margin:0;font:600 17px Menlo,"DejaVu Sans Mono",monospace;color:#fff}
.blurb{margin:4px 0 2px}
.credit{margin:0 0 8px;font-size:12.5px;color:#8a91a1}
.shots{display:flex;flex-wrap:wrap;gap:10px;margin:8px 0}
figure{margin:0;flex:1 1 auto;min-width:0}
figcaption{font-size:12px;color:#8a91a1;margin-top:3px;text-align:center}
.screen{background:#000;border-radius:4px;overflow:hidden;cursor:zoom-in;display:block}
pre .r{display:inline-block;overflow:hidden;vertical-align:top;white-space:pre;height:1em;line-height:1}
pre{margin:0;font:8px/1 Menlo,"DejaVu Sans Mono","Noto Sans Symbols 2",monospace;color:#c0c0c0;
 background:#000;white-space:pre;width:max-content;max-width:100%;overflow:hidden}
.shots figure:only-child pre{margin:0 auto}
.cmd{display:block;background:#0a0c10;border-radius:4px;padding:3px 8px;margin:4px 0;
 font:12.5px Menlo,"DejaVu Sans Mono",monospace;color:#9be28f;user-select:all}
.flags{margin:6px 0 0;font-size:12px;color:#8a91a1;display:flex;flex-wrap:wrap;gap:4px 6px}
.flags code{background:#1c212c;border-radius:3px;padding:1px 6px;font-family:Menlo,"DejaVu Sans Mono",monospace}
.controls{margin:6px 0 0;font-size:12.5px;color:#b9bfcc}
footer{padding:10px 20px 50px;color:#9aa1b0;font-size:13.5px}
footer code{background:#1c212c;border-radius:3px;padding:1px 6px;font-family:Menlo,"DejaVu Sans Mono",monospace}
#lb{position:fixed;inset:0;background:rgba(0,0,0,.88);display:none;align-items:center;justify-content:center;
 z-index:9;cursor:zoom-out;overflow:auto}
#lb.on{display:flex}
#lb pre{font-size:15px;max-width:none;overflow:visible;border:1px solid #333;margin:auto}
"""

JS = """
(function(){var lb=document.getElementById('lb');
function open(s){lb.innerHTML=s.innerHTML;lb.classList.add('on')}
document.addEventListener('click',function(e){var s=e.target.closest('.screen');
 if(s)open(s);else lb.classList.remove('on')});
document.addEventListener('keydown',function(e){
 if(e.key==='Escape')lb.classList.remove('on');
 else if((e.key==='Enter'||e.key===' ')&&document.activeElement.classList.contains('screen')){
  e.preventDefault();open(document.activeElement)}});})();
"""

QUICK = [
    ("./wait-fun", "random watch piece, switches every 90s"),
    ("./wait-fun --until-done", "cycle until Claude finishes, then a fireworks finale"),
    ("./wait-fun watch [NAME]", "one non-interactive piece"),
    ("./wait-fun play [NAME]", "one game"),
    ("./wait-fun list", "everything, with blurbs"),
    ("./wait-fun credits", "who inspired what"),
]


def render_page(entries, captured):
    h = ['<!doctype html><html lang="en"><head><meta charset="utf-8">',
         '<meta name="viewport" content="width=device-width,initial-scale=1">',
         f"<title>terminal-fun gallery</title><style>{CSS}</style></head><body>",
         "<header><h1>terminal-fun</h1>",
         '<p class="sub">Terminal animations to watch and games to play while Claude Code works '
         "in another window. Stills captured from the real programs, in colour.</p>",
         '<div class="quick">']
    for c, d in QUICK:
        h.append(f"{esc(c)}  <span># {esc(d)}</span><br>")
    h.append('<span># wf is the short alias for wait-fun</span></div></header><main>')
    for kind, title in (("watch", "Watch"), ("play", "Play")):
        h.append(f'<h2>{title}</h2><div class="grid">')
        for name, e in entries[kind].items():
            if e.get("variant") or name in SKIP_PIECES:
                continue
            shots = captured.get(name, [])
            if name == "excuses":
                shots = shots + captured.get("excuses-progress", [])
            if shots:
                h.append(card(e, shots, QUICK))
        h.append("</div>")
    h.append('</main><footer><h2>Shared</h2>'
             "<p>Keys in every piece: <code>p</code> pause, <code>q</code> quit, <code>r</code> restart "
             "(games and some pieces), <code>Ctrl-C</code> quit.</p>"
             "<p>Environment: <code>NO_COLOR=1</code> drops colour; "
             "<code>CLAUDE_FUN_NO_FOCUS_PAUSE=1</code> keeps full speed when the window loses focus.</p>"
             '<p>Credits: <a href="CREDITS.md">CREDITS.md</a></p></footer>'
             f'<div id="lb"></div><script>{JS}</script></body></html>')
    return "\n".join(h)


def load_entries():
    import importlib.machinery
    import importlib.util
    path = os.path.join(ROOT, "wait-fun")
    loader = importlib.machinery.SourceFileLoader("wait_fun", path)
    spec = importlib.util.spec_from_loader("wait_fun", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod.PIECES


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("-o", "--output", default=os.path.join(ROOT, "gallery.html"))
    ap.add_argument("--only", nargs="*", help="capture only these pieces")
    args = ap.parse_args()
    sys.dont_write_bytecode = True

    entries = load_entries()
    flat = {n: e for k in entries.values() for n, e in k.items()}
    tmp = tempfile.mkdtemp(prefix="gallery-")
    env = dict(os.environ, CLAUDE_FUN_STATUS=os.path.join(tmp, "status.json"), PYTHONHASHSEED="0",
               COLORTERM="truecolor",
               PYTHONDONTWRITEBYTECODE="1")
    for k in ("NO_COLOR", "COLUMNS", "LINES"):
        env.pop(k, None)
    captured = {}
    try:
        for shot in SHOTS:
            if args.only and shot["piece"] not in args.only:
                continue
            scr = capture(shot, flat, env)
            captured.setdefault(shot["piece"], []).append((shot["label"], screen_html(scr)))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    page = render_page(entries, captured)
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(page)
    print(f"wrote {args.output} ({len(page) / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
