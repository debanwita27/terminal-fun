# Wiring terminal-fun to Claude Code

## Install

```sh
./wait-fun install               # both hooks; --no-nudge for status only, --no-link to skip ~/.local/bin
./wait-fun uninstall             # removes only terminal-fun's entries
```

`install` merges the entries below into `~/.claude/settings.json`. It copies the old file to `settings.json.bak-terminal-fun` first and leaves every other hook alone. Entries are recognised by their command path under `hooks/`, so running it again doesn't duplicate them. If `~/.local/bin` is on PATH it also links `wait-fun` there. New sessions pick the hooks up; running ones may need `/hooks` or a restart.

## Nudge hook

`hooks/claude-fun-nudge` runs on UserPromptSubmit (notes when the prompt started) and PreToolUse. Once a prompt has run longer than `CLAUDE_FUN_NUDGE_AFTER` seconds (default 45), it prints one `systemMessage` line. The user sees it; Claude never does. The line suggests `wait-fun --until-done` or a random piece. Limits: one per prompt, and one per `CLAUDE_FUN_NUDGE_EVERY` seconds across all sessions (default 900). It stays quiet if wait-fun or any piece is already running, if `~/.cache/claude-fun/nudge-off` exists (`wait-fun nudge off`), or if `CLAUDE_FUN_NUDGE=0`. State lives in `~/.cache/claude-fun/nudge.json`. It always exits 0.

## settings.json entries (status hook)

Equivalent to what `install` writes for the status hook, if you'd rather merge by hand into the `hooks` key of `~/.claude/settings.json` (or a project `.claude/settings.json`). Schema per https://code.claude.com/docs/en/hooks : event -> list of `{matcher, hooks: [{type, command}]}`. Tool events take a matcher (`""` or `"*"` matches all tools); the others ignore it.

```json
{
  "hooks": {
    "UserPromptSubmit": [{ "matcher": "", "hooks": [{ "type": "command", "command": "/path/to/terminal-fun/hooks/claude-fun-status" }] }],
    "PreToolUse":       [{ "matcher": "*", "hooks": [{ "type": "command", "command": "/path/to/terminal-fun/hooks/claude-fun-status" }] }],
    "PostToolUse":      [{ "matcher": "*", "hooks": [{ "type": "command", "command": "/path/to/terminal-fun/hooks/claude-fun-status" }] }],
    "Stop":             [{ "matcher": "",  "hooks": [{ "type": "command", "command": "/path/to/terminal-fun/hooks/claude-fun-status" }] }],
    "Notification":     [{ "matcher": "",  "hooks": [{ "type": "command", "command": "/path/to/terminal-fun/hooks/claude-fun-status" }] }]
  }
}
```

## Status file protocol

Path: `$CLAUDE_FUN_STATUS`, default `~/.cache/claude-fun/status.json` (see `status_path()` in `fun/term.py`). The hook writes it atomically (temp file + rename):

```json
{"state": "working", "tool": "Bash", "event": "PreToolUse", "ts": 1762040000.5,
 "session": "<session_id>", "cwd": "/Users/you/work/repo", "prompt": "first 80 chars of the last prompt"}
```

It also writes the same record to `sessions/<session_id>.json` next to the status file, so with several Claude sessions running, one busy session can't overwrite another's `done`. `prompt` is carried over from that session's last UserPromptSubmit. Session files older than two days are pruned on Stop.

| Hook event | state | tool |
|---|---|---|
| UserPromptSubmit | working | null |
| PreToolUse / PostToolUse | working | tool name |
| Stop | done | null |
| Notification | idle | null |

Unknown events leave the file unchanged. The hook always exits 0 (errors go to stderr) so it can't block Claude.

## Which animations react

Scripts read it via `read_status()` (returns None if the file is missing or invalid).

- **campfire**: flames burn higher and throw more sparks while state is `working`; settles otherwise.
- **catnap**: when state is `done` with a `ts` newer than its start (once per new `ts`), the cat wakes, stretches and announces it, then dozes off again.
- **hourglass**: on `done` (`ts` newer than its start) the glass flips (once per new `ts`) and shows "done".
- **biplane**: banner reads "Claude is running <tool>..." / "Claude is working..." / "Claude is done!" / "Claude is waiting for you" from the file, chosen when a pass starts; `--text` overrides. With no status file it uses random dev quips.
- **wait-fun `--until-done`**: cycles until any session file (or the status file) is `done` with a `ts` newer than its start, then plays `watch/fireworks.py --finale --hold` with a banner naming that session's folder and prompt. Any key returns to the rotation and waits for the next session to finish (one that finished during the pause is announced next); `q` quits.

catnap and hourglass ignore a `done` whose `ts` is not newer than the script's own start time, so a stale `done` left in the file does not trigger them at startup. catnap additionally reacts once per new `ts`.

## Test manually

```sh
export CLAUDE_FUN_STATUS=/tmp/claude-fun-test.json   # optional, avoids the real file
printf '%s' '{"hook_event_name":"UserPromptSubmit","session_id":"t1","cwd":"'$PWD'","prompt":"try the finale"}' | /path/to/terminal-fun/hooks/claude-fun-status
cat $CLAUDE_FUN_STATUS
printf '%s' '{"hook_event_name":"Stop","session_id":"t1","cwd":"'$PWD'"}' | /path/to/terminal-fun/hooks/claude-fun-status
```

Then in another terminal (same env var): `/path/to/terminal-fun/wait-fun --until-done`, or `python3 watch/catnap.py`.
