"""Install/uninstall terminal-fun's Claude Code hooks and the `wait-fun` command.

`wait-fun install` merges two hooks into ~/.claude/settings.json without touching any other
entry: claude-fun-status (lets --until-done, catnap, hourglass, campfire and biplane react to
Claude) and claude-fun-nudge (a one-line break suggestion once a prompt runs long). The old
file is copied to settings.json.bak-terminal-fun first. Entries are recognised by their
command path, so install is idempotent and uninstall removes only ours.
"""
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
HOOKS = os.path.join(HERE, "hooks")
STATUS = os.path.join(HOOKS, "claude-fun-status")
NUDGE = os.path.join(HOOKS, "claude-fun-nudge")
SETTINGS = os.path.expanduser("~/.claude/settings.json")
NUDGE_OFF = os.path.expanduser("~/.cache/claude-fun/nudge-off")
BIN = os.path.expanduser("~/.local/bin")
TIMEOUT = 5

# event -> (matcher, scripts); tool events need a matcher, "*" = every tool
WIRING = {
    "UserPromptSubmit": ("", [STATUS, NUDGE]),
    "PreToolUse": ("*", [STATUS, NUDGE]),
    "PostToolUse": ("*", [STATUS]),
    "Stop": ("", [STATUS]),
    "Notification": ("", [STATUS]),
}


def ours(hook):
    return isinstance(hook, dict) and str(hook.get("command", "")).startswith(HOOKS + os.sep)


def load(path):
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        text = f.read()
    data = json.loads(text) if text.strip() else {}
    if not isinstance(data, dict):
        raise SystemExit(f"wait-fun: {path} is not a JSON object; not touching it")
    return data


def strip(settings):
    """Remove our hook commands; drop groups and events left empty. Returns count removed."""
    hooks = settings.get("hooks")
    if not isinstance(hooks, dict):
        return 0
    removed = 0
    for event in list(hooks):
        groups = hooks[event]
        if not isinstance(groups, list):
            continue
        kept = []
        for g in groups:
            if isinstance(g, dict) and isinstance(g.get("hooks"), list):
                before = len(g["hooks"])
                g["hooks"] = [h for h in g["hooks"] if not ours(h)]
                removed += before - len(g["hooks"])
                if not g["hooks"]:
                    continue
            kept.append(g)
        if kept:
            hooks[event] = kept
        else:
            del hooks[event]
    if not hooks:
        del settings["hooks"]
    return removed


def write(path, settings):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.exists(path):
        shutil.copy2(path, path + ".bak-terminal-fun")
    tmp = path + ".tmp-terminal-fun"
    with open(tmp, "w") as f:
        json.dump(settings, f, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def link_launcher():
    """Symlink wait-fun into ~/.local/bin when that dir is on PATH. Returns a status line."""
    target = os.path.join(HERE, "wait-fun")
    if BIN not in os.environ.get("PATH", "").split(os.pathsep):
        return f"wait-fun not linked (~/.local/bin is not on PATH); run it as {target}"
    dest = os.path.join(BIN, "wait-fun")
    if os.path.lexists(dest):
        if os.path.realpath(dest) == target:
            return f"wait-fun already linked: {dest}"
        return f"wait-fun not linked: {dest} already exists and points elsewhere"
    os.makedirs(BIN, exist_ok=True)
    os.symlink(target, dest)
    return f"linked {dest} -> {target}"


def unlink_launcher():
    dest = os.path.join(BIN, "wait-fun")
    if os.path.islink(dest) and os.path.realpath(dest) == os.path.join(HERE, "wait-fun"):
        os.unlink(dest)
        return f"removed {dest}"
    return None


def install(path=SETTINGS, nudge=True, link=True):
    settings = load(path)
    strip(settings)
    hooks = settings.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise SystemExit(f"wait-fun: 'hooks' in {path} is not an object; not touching it")
    for event, (matcher, scripts) in WIRING.items():
        cmds = [s for s in scripts if nudge or s != NUDGE]
        hooks.setdefault(event, []).append(
            {"matcher": matcher,
             "hooks": [{"type": "command", "command": c, "timeout": TIMEOUT} for c in cmds]})
    write(path, settings)
    print(f"installed terminal-fun hooks into {path} (backup: {path}.bak-terminal-fun)")
    print("  status hook: --until-done, catnap, hourglass, campfire, biplane now react to Claude")
    print("  nudge hook:  " + ("on; 'wait-fun nudge off' to silence it" if nudge else "not installed"))
    if link:
        print("  " + link_launcher())
    print("New Claude sessions pick this up; running ones may need /hooks or a restart.")
    return 0


def uninstall(path=SETTINGS):
    if not os.path.exists(path):
        print(f"nothing to remove: {path} does not exist")
        return 0
    settings = load(path)
    n = strip(settings)
    if n:
        write(path, settings)
        print(f"removed {n} terminal-fun hook entries from {path} (backup: {path}.bak-terminal-fun)")
    else:
        print(f"no terminal-fun hooks in {path}")
    msg = unlink_launcher()
    if msg:
        print(msg)
    return 0


def nudge(arg):
    if arg == "off":
        os.makedirs(os.path.dirname(NUDGE_OFF), exist_ok=True)
        open(NUDGE_OFF, "w").close()
        print("nudges off ('wait-fun nudge on' to bring them back)")
    elif arg == "on":
        if os.path.exists(NUDGE_OFF):
            os.unlink(NUDGE_OFF)
        print("nudges on")
    else:
        state = "off" if os.path.exists(NUDGE_OFF) or os.environ.get("CLAUDE_FUN_NUDGE") == "0" else "on"
        print(f"nudges {state}")
    return 0


def main(cmd, rest):
    path = SETTINGS
    if "--settings" in rest:
        i = rest.index("--settings")
        if i + 1 >= len(rest):
            print("wait-fun: --settings needs a path", file=sys.stderr)
            return 2
        path = os.path.expanduser(rest[i + 1])
    if cmd == "install":
        return install(path, nudge="--no-nudge" not in rest, link="--no-link" not in rest)
    if cmd == "uninstall":
        return uninstall(path)
    return nudge(rest[0] if rest else "status")
