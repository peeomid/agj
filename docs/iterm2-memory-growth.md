# iTerm2 Memory Growth: Background + Architecture Goal

## Summary
We observed iTerm2 memory growing over time when AGJ runs with the Python API.
The Script Console log shows many short-lived RPC connections. This doc captures
the issue, why it matters, and how the new architecture reduces RPC churn.

## What we see
- Script Console log shows repeated entries like:
  - “Connection accepted: Script launched by user action”
  - “Connection closed”
- Many “running” script entries accumulate.
- iTerm2 memory grows during heavy/continuous AGJ usage.

## Hypothesis
Frequent, short-lived RPC connections and repeated screen captures contribute to
log growth and memory pressure in iTerm2. We can’t change iTerm2 internals, so
we reduce how often we connect and how many calls we make.

## Architecture response (goal)
Reduce the number of iTerm2 API calls while keeping full TUI functionality:
- **Two connections only:** one for list/focus/output, one for permission scans.
- **Connection reuse:** single `Connection` per backend, reused across calls.
- **Refresh cadence:** list every 5s, output every 3s, scan every 5s (current).
- **Caching:** reuse recent output to avoid extra `get_screen_contents`.
- **Priority:** focus (`o`) should preempt UI work.

## Current state (implementation)
- TUI uses two backends: main + scan.
- Each backend keeps one `Connection` with a lock.
- Permission scan runs after list mapping, fan-out in threads.
- Output cache reduces repeated calls on selection changes.

## Why this should help
Fewer connections + fewer calls → fewer Script Console entries → lower memory
growth risk while still keeping the big-picture refresh.

## Follow-ups
- Measure Script Console entries per minute before/after.
- Track iTerm2 memory growth rate under same workload.
- Tune cadence (increase scan interval) if still too chatty.
