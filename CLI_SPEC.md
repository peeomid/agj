# Agent Monitor CLI Spec

## Goal
Provide a non-interactive CLI for listing Codex/Claude instances and focusing the corresponding iTerm2 pane.

## Commands
### `list`
List instances with optional formatting and filters.

**Flags**
- `--pattern` (repeatable): regex to match process name/cmdline. Default: `codex`, `claude`.
- `--json`: output JSON array of instances.
- `--stable`: output tab-separated, scripting-friendly rows with a header.
- `--no-unmapped`: exclude processes that do not map to iTerm sessions.
- `--max N`: limit number of rows.

**Default output**
Human-friendly aligned table:
```
ID  PID   NAME    COMMAND                 SESSION
1   1234  codex   codex --foo             w:1 t:2 s:ABCD
2   5678  claude  python -m claude        unmapped
```

**Stable output**
```
id	pid	name	cmd	session
1	1234	codex	codex --foo	w:1 t:2 s:ABCD
2	5678	claude	python -m claude	unmapped
```

### `focus`
Activate an iTerm2 session for a selected instance. Non-interactive.

**Selection flags** (one required)
- `--id N`: ID from the `list` output (assigned by sorted PID order at runtime).
- `--pid PID`: process PID.
- `--session SESSION_ID`: iTerm2 session ID.
- `--match REGEX`: regex match on process name/cmdline; must resolve to exactly one instance.

**Behavior**
- If selection resolves to no or multiple instances, exit non-zero with an error message.
- If the selected instance is unmapped, return non-zero and explain.

## Data Model
- `ProcessInfo`: pid, name, cmdline, ancestry.
- `SessionInfo`: session_id, tab_id, window_id, pid, title.
- `InstanceInfo`: process + mapped session.

## Mapping
- Enumerate iTerm2 sessions and read each session PID.
- Map if any PID in process ancestry matches a session PID.

## Exit Codes
- `0`: success.
- `1`: no matches.
- `2`: ambiguous selection.
- `3`: iTerm2 API unavailable.

## Dependencies
- `psutil`
- `iterm2`
- `pytest`

## Testing
- Pure tests for selection and formatting helpers.
- Mock backend for `focus` path.
