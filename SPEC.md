# AGX POC Spec

## Goal
Provide a Python TUI that lists running Codex and Claude instances, lets the user navigate with vim keys, and activates the corresponding iTerm2 pane when `o` is pressed.

## Scope
- **Discovery**: Find running processes that look like Codex/Claude.
- **Mapping**: Map those processes to iTerm2 sessions by matching process ancestry to session PIDs.
- **TUI**: Render a list and enable vim-style navigation (`j`/`k`).
- **Activation**: When `o` is pressed, bring iTerm2 to front and activate the selected session.

## Out of Scope
- Non-iTerm terminals (e.g., Terminal.app, tmux-only).
- Multi-host discovery (remote sessions, SSH-only enumeration).
- Persistent state or background daemon.

## User Experience
- Launch via CLI: `agx`.
- UI shows a list of matched instances with metadata:
  - Index
  - Process name / command
  - PID
  - iTerm window/tab/session identifiers (best-effort)
- Controls:
  - `j` / `k`: move selection
  - `o`: activate selected iTerm2 session
  - `r`: refresh list
  - `q`: quit

## Data Model
- `ProcessInfo`: pid, name, cmdline, parent_pids
- `SessionInfo`: session_id, tab_id, window_id, pid, title
- `InstanceInfo`: process + mapped session

## Process Discovery
- Use `psutil.process_iter` to gather processes.
- Match by regex on `name` and `cmdline` (defaults: `codex`, `claude`).
- Build parent PID chain for each candidate.

## iTerm2 Session Mapping
- Use iTerm2 Python API to enumerate windows → tabs → sessions.
- For each session, retrieve `pid` via `session.async_get_variable("pid")`.
- Map an instance to a session if any PID in the process ancestry matches the session PID.

## Activation Flow
When `o` is pressed for a selected instance:
1) Activate iTerm2 app.
2) Activate session’s window and tab (order front).
3) Activate the session itself.

## Architecture
- `agx/processes.py`: process discovery + filtering.
- `agx/iterm.py`: iTerm2 API backend.
- `agx/tui.py`: prompt_toolkit UI.
- `agx/app.py`: orchestration + refresh.

## Dependencies
- `psutil`
- `prompt_toolkit`
- `iterm2`
- `pytest`

## Testing
- Unit tests for process filtering and session mapping (pure functions).
- Mocked iTerm backend for activation calls.
- No live iTerm2 or psutil dependency in tests.

## Non-Functional
- Works on macOS with iTerm2 running.
- Clear error message if iTerm2 API is not available or no sessions found.
