# AGJ

AGJ monitors Codex/Claude sessions in iTerm2 so you never miss a permission prompt while multitasking. It shows which agent is waiting for approval, sends actionable macOS notifications, and lets you go to the right pane fast.

![AGJ TUI screenshot](agj.png)

## What it does
- Lists active agent sessions in iTerm2
- Detects Codex/Claude permission prompts
- Goes to the right pane instantly
- Captures recent output for quick context
- Sends actionable notifications and lets you jump straight to the session that needs approval

## Use cases
- You’re juggling multiple agent sessions and miss permission prompts.
- You want a quick status view of all active Codex/Claude instances.
- You need a fast way to go to the pane that’s waiting on you.
- You want a notification when an agent starts waiting for approval.

## Keywords
codex permission prompt, claude permission prompt, monitor multiple codex sessions, track claude windows, iTerm2 agent status, focus iTerm pane by process, AI agent monitor, agent approval notification, macOS notification for codex

## Install

Recommended (isolated):
```
pipx install agj
```

Standard pip:
```
pip install agj
```

## Quick start

List active agents:
```
agj list
```

Only show agents asking for permission:
```
agj list --permission-only
```

Open the TUI:
```
agj tui
```

Disable notifications if needed:
```
agj tui --no-notify
```

Jump to one:
```
agj focus --id 1
```

Capture recent output:
```
agj capture --id 1 --lines 50
```

## Requirements
- macOS
- iTerm2 running with Python API enabled
- Python 3.11+
- `alerter` installed for actionable notifications (install from GitHub releases):
  `https://github.com/vjeantet/alerter`

## Development
```
uv sync
uv run -- python -m pytest
uv run agj list
```
