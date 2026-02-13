# AGJ POC Spec

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
- Launch via CLI: `agj`.
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

## Architecture (Current)
- **TUI loop:** `agj/tui.py` runs three background tasks:
  - List refresh every 5s.
  - Selected output refresh every 3s.
  - Initial refresh on startup (non-blocking).
- **Controller:** `agj/app.py` owns state, caching, and notifications.
  - Two-phase refresh: list/mapping first, permission/error scan second.
  - Output cache (per session) with TTL + “refresh-after” window.
  - Focus (`o`) uses a short output pause to feel immediate.
- **State detection:** `agj/service.py`
  - ThreadPoolExecutor fan-out per instance.
  - Capture last 60 lines; fallback to visible screen if empty.
  - Idle detection via re-checks (`--idle-checks`).
- **Backends:** `agj/iterm.py` uses iTerm2 Python API.
  - Two backend instances are used in TUI:
    - **Main backend:** list + focus + output.
    - **Scan backend:** permission/error scan.
  - Each backend holds a single iTerm2 `Connection` guarded by a lock.
- **Process mapping:** `agj/processes.py` + `agj/mapping.py`.
  - Processes found via regex (codex/claude) + resolved binary paths.
  - Sessions mapped by PID ancestry → iTerm2 session PID.

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

---

# iTerm2 RPC Scheduler Spec (Target)

## Goal
Make `o` focus feel immediate, keep full-list refresh, and prevent Script Console connection explosion.

## Constraints
- No iTerm2 source changes.
- TUI still shows full big-picture refresh.
- Connections must be bounded and reused.

## Architecture
### Connection Pool (fixed size = 2)
- **Conn A**: list + output + focus (high priority)
- **Conn B**: permission scan (low priority)
- No per-call connection creation.
- No fallback connection storm.

### Priority Scheduling
- High: focus (`o`)
- Normal: list + selected output
- Low: permission scan

### Cadence
- Output refresh: 3s
- List refresh: 5s
- Permission scan: 10–15s (configurable)

### Backoff / Health
- On connection failure: reconnect with backoff (1s → 2s → 4s → 30s).
- Tasks queue until connection returns.
- Status shows connection state (connecting/retrying).

### Batching
- Use iTerm2 transactions for `line_info + get_contents` to reduce round trips.

## UX Status
- “Connecting to iTerm2…”
- “Listing sessions…”
- “Scanning permissions…”
- “Focusing PID…”

## Success Criteria
- Script Console shows ≤2 running entries per TUI process.
- `o` focus feels immediate (<1s under normal load).
- No “Too many open files” errors.
