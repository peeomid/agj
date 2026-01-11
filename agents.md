# AGJ Project Guide

## Overview
AGJ is a CLI to monitor running AI agent processes (Codex/Claude), map them to iTerm2 sessions, and quickly focus or capture their output.

## Commands
- `agj list` — list running instances
- `agj focus --id N|--pid PID|--session ID|--match REGEX` — focus an instance in iTerm2
- `agj capture --id N|--pid PID|--session ID|--match REGEX [--lines N]` — capture output
- `agj tui` — open the interactive TUI

## Common Flags
- `list --with-session` — include iTerm window/tab/session identifiers
- `list --with-session-name / --no-with-session-name` — show/hide iTerm session name
- `list --with-path / --no-with-path` — show/hide working directory (default: on)
- `list --permission-only` — show only instances asking for permission
- `list --permission-debug` — explain why a permission prompt was detected
- `list --json` — JSON output for scripting
- `list --stable` — tab-separated output with header

## How It Works
- Uses `psutil` to find Codex/Claude processes
- Resolves binary paths via `which` to avoid false positives
- Maps processes to iTerm2 sessions by PID ancestry
- Uses iTerm2 Python API to list sessions, activate panes, and read output

## Requirements
- macOS with iTerm2 running
- iTerm2 Python API enabled (iTerm2 Preferences > General > Magic > Enable Python API)
- Python 3.11+ (managed via `uv`)

## Development
- Install deps: `uv sync`
- Run tests: `uv run -- python -m pytest`
- Run locally: `uv run agj list`

## Troubleshooting
- If `list` shows no path: enable iTerm2 shell integration or ensure the session supports `path` variable.
- If `focus` fails: verify the session exists and iTerm2 is running.
- If CLI can’t connect: re-enable Python API and ensure permissions.
- If TUI output is slow to update: it uses cached output and refreshes in the background; use `r` to refresh the list.
