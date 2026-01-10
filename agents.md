# AGX Project Guide

## Overview
AGX is a CLI to monitor running AI agent processes (Codex/Claude), map them to iTerm2 sessions, and quickly focus or capture their output.

## Commands
- `agj list` — list running instances
- `agj focus --id N|--pid PID|--session ID|--match REGEX` — focus an instance in iTerm2
- `agj capture --id N|--pid PID|--session ID|--match REGEX [--lines N]` — capture output

## Common Flags
- `list --with-session` — include iTerm window/tab/session identifiers
- `list --with-path / --no-with-path` — show/hide working directory (default: on)
- `list --stable` — tab-separated output for scripting

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
- Run tests: `uv run pytest`
- Run locally: `uv run agj list`

## Troubleshooting
- If `list` shows no path: enable iTerm2 shell integration or ensure the session supports `path` variable.
- If `focus` fails: verify the session exists and iTerm2 is running.
- If CLI can’t connect: re-enable Python API and ensure permissions.
