# AGJ TUI Memory Leak Analysis

## Summary

Investigation into iTerm2 high memory consumption when running the AGJ TUI. Found multiple memory leak sources in both the application code and in how iTerm2's Python API is being used.

---

## Primary Issues

### 1. iTerm2 Connection Task Accumulation (Critical)

**Location:** `agj/iterm.py:27-39`

```python
def _run(self, work):
    with self._lock:
        if self._connection is None:
            self._connection = iterm2.Connection()
        try:
            return self._connection.run_until_complete(work, retry=False)
        except Exception:
            self._connection = None
            raise
```

**Problem:** iTerm2's `Connection` class internally accumulates asyncio tasks in a `self.__tasks` list. The garbage collection method (`_collect_garbage()`) that cleans up completed tasks only runs inside `_async_dispatch_forever`, which is NOT used by `run_until_complete()`.

Every API call adds tasks that never get cleaned up. Over time, with the TUI refreshing every 3-5 seconds, thousands of task references accumulate.

---

### 2. Infinite Background Loops Without Cancellation

**Location:** `agj/tui.py:267-277`

```python
async def _auto_update_output(self) -> None:
    while True:  # Never exits
        await self.on_update_output()
        self.app.invalidate()
        await asyncio.sleep(3)

async def _auto_refresh_list(self) -> None:
    while True:  # Never exits
        await self.on_refresh()
        self.app.invalidate()
        await asyncio.sleep(5)
```

**Problem:** No cancellation mechanism exists. These tasks:
- Run indefinitely with no exit condition
- Are created via `app.create_background_task()` without storing references
- May continue running even after TUI exit attempts
- Each cycle creates temporary objects and makes network calls to iTerm2

---

### 3. Blocking `time.sleep()` in ThreadPool

**Location:** `agj/service.py:120-132`

```python
for delay in idle_checks:
    if delay > 0:
        time.sleep(delay)  # BLOCKING in thread
    raw_output_2 = backend.capture_output(inst.session.session_id, lines=permission_lines)
```

**Problem:** Each `_compute_state` call:
- Holds a thread with blocking sleeps (0.3s + 0.8s = 1.1s per instance)
- Calls iTerm2 backend multiple times while blocking
- Creates contention when multiple instances are checked simultaneously
- May cause connection pile-up if threads don't exit cleanly

---

### 4. `state_state` Dictionary Never Prunes Old Entries

**Location:** `agj/app.py:252-253`

```python
updated, events = state_transition_events(instances, self.state_state)
self.state_state = updated
```

**Problem:** The `state_transition_events` function in `notifications.py:261-277` only adds entries to `updated` dict—it never removes session IDs that no longer exist. After hours of use with sessions being created/destroyed, thousands of stale entries accumulate.

---

### 5. Unbounded Daemon Thread Creation

**Location:** `agj/notifications.py:87, 125`

```python
Thread(target=_run, daemon=True).start()
```

**Problem:**
- No thread pool limits
- Each notification spawns a new daemon thread
- Rapid state transitions can create unbounded threads
- Daemon threads hold references to lambdas/closures with instance data
- No tracking or cleanup mechanism

---

### 6. Lambda Closures Capturing Controller State

**Location:** `agj/app.py:264-271`

```python
def _action(session=inst.session) -> None:
    try:
        self.backend.activate(session)
    except Exception:
        return

notifier.send(payload, _action, action_command=action_command)
```

**Problem:** Each notification creates a lambda that captures `self.backend` and session data. If notifications queue up before handlers complete, these closures accumulate.

---

## iTerm2 Known Issues

From community reports and GitLab issues:

| Source | Finding |
|--------|---------|
| [GitLab #11261](https://gitlab.com/gnachman/iterm2/-/issues/11261) | High CPU and memory usage reports |
| [GitLab #10766](https://gitlab.com/gnachman/iterm2/-/issues/10766) | 7.6GB memory usage on iTerm2 3.5.0beta9 |
| [Hacker News](https://news.ycombinator.com/item?id=36060580) | Memory leaks "used to be a big issue, still not fully fixed" |
| [GitLab #8128](https://gitlab.com/gnachman/iterm2/-/issues/8128) | High memory usage since specific versions |

**Common causes:**
- Unlimited scrollback buffer (most common)
- Python API websocket connections not properly disposed
- Internal image caching leaks

---

## Recommended Fixes

### High Priority

#### 1. Reset iTerm2 Connection Periodically

```python
# Option A: Create new connection per operation
def _run(self, work):
    import iterm2
    conn = iterm2.Connection()
    try:
        return conn.run_until_complete(work, retry=False)
    finally:
        # Connection closes when it goes out of scope
        pass

# Option B: Reset after N operations
_operation_count: int = 0
_max_operations: int = 50

def _run(self, work):
    with self._lock:
        self._operation_count += 1
        if self._operation_count >= self._max_operations:
            self._connection = None
            self._operation_count = 0
        # ... rest of method
```

#### 2. Add Task Cancellation to Background Loops

```python
class MonitorTui:
    def __init__(self, ...):
        self._background_tasks: list[asyncio.Task] = []

    async def run(self) -> None:
        self._background_tasks = [
            self.app.create_background_task(self._auto_update_output()),
            self.app.create_background_task(self._auto_refresh_list()),
        ]
        try:
            await self.app.run_async()
        finally:
            for task in self._background_tasks:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

    async def _auto_update_output(self) -> None:
        try:
            while True:
                await self.on_update_output()
                self.app.invalidate()
                await asyncio.sleep(3)
        except asyncio.CancelledError:
            return
```

#### 3. Prune `state_state` Dictionary

```python
def _maybe_notify(self, instances: list[InstanceInfo]) -> None:
    # Get current session IDs
    current_session_ids = {
        inst.session.session_id
        for inst in instances
        if inst.session is not None
    }

    # Prune old entries
    self.state_state = {
        sid: state
        for sid, state in self.state_state.items()
        if sid in current_session_ids
    }

    # ... rest of method
```

#### 4. Use Bounded Thread Pool for Notifications

```python
from concurrent.futures import ThreadPoolExecutor

class AlerterSender(NotificationSender):
    _executor: ThreadPoolExecutor = ThreadPoolExecutor(max_workers=4)

    def send(self, payload, on_action, action_command=None) -> None:
        # ... build args ...
        self._executor.submit(self._run, args, on_action)

    def _run(self, args, on_action) -> None:
        # ... existing logic ...
```

### Medium Priority

#### 5. Replace Blocking Sleep with Async

```python
async def _compute_state_async(inst, backend, permission_lines, idle_checks):
    # ... initial check ...
    for delay in idle_checks:
        if delay > 0:
            await asyncio.sleep(delay)  # Non-blocking
        raw_output_2 = await asyncio.to_thread(
            backend.capture_output, inst.session.session_id, permission_lines
        )
        # ... rest of logic ...
```

---

## Verification Steps

### Quick Test: Connection Reset

Modify `agj/iterm.py` to always create a new connection:

```python
def _run(self, work):
    import iterm2
    with self._lock:
        conn = iterm2.Connection()
        return conn.run_until_complete(work, retry=False)
```

Run the TUI and monitor memory. If it stabilizes, the persistent connection is the primary leak source.

### Memory Profiling

```bash
# Install memory profiler
pip install memory_profiler

# Run with profiling
mprof run python -m agj.app

# Plot results
mprof plot
```

### Monitor iTerm2 Process

```bash
# Watch iTerm2 memory usage
while true; do
    ps -o rss,vsz,pid -p $(pgrep -f iTerm2) | tail -1
    sleep 10
done
```

---

## References

- [iTerm2 Python API Connection docs](https://iterm2.com/python-api/connection.html)
- [iTerm2 Connection source code](https://github.com/gnachman/iTerm2/blob/master/api/library/python/iterm2/iterm2/connection.py)
- [GitLab: High CPU and Memory Usage #11261](https://gitlab.com/gnachman/iterm2/-/issues/11261)
- [GitLab: High memory usage #10766](https://gitlab.com/gnachman/iterm2/-/issues/10766)
- [GitLab: Huge Amount of Memory Used #10766](https://gitlab.com/gnachman/iterm2/-/issues/10766)
- [Python asyncio memory leak with run_in_executor](https://github.com/python/cpython/issues/85865)
