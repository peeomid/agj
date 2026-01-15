# AGJ

AGJ monitors Codex/Claude sessions in iTerm2 so you never miss a permission prompt while multitasking. It shows which agent is waiting for approval, sends macOS notifications, and lets you go to the right pane fast.

![AGJ TUI screenshot](agj.png)
![AGJ notification screenshot](notification.png)

## What it does
- Lists active agent sessions in iTerm2
- Detects Codex/Claude permission prompts and error states
- Shows agent state: permission, error, running, or idle
- Goes to the right pane instantly
- Captures recent output for quick context
- Sends notifications and lets you jump straight to the session that needs approval

## iTerm tab titles
AGJ uses the iTerm2 tab title in the TUI and notifications. You can customize this in iTerm2 to make the display more meaningful:
https://iterm2.com/documentation-session-title.html

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

Tune idle detection delays (re-check output before marking idle):
```
agj list --idle-checks 0.3,0.8
```

Open the TUI:
```
agj tui
```

Disable notifications if needed:
```
agj tui --no-notify
```

Enable a notification sound:
```
agj tui --notify-sound Glass
```
Use `default` for the system default sound or `none` to disable sound.

TUI idle detection delays:
```
agj tui --idle-checks 0.3,0.8
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
- `alerter` installed for notifications (install from GitHub releases):
  `https://github.com/vjeantet/alerter`

## Development
```
uv sync
uv run -- python -m pytest
uv run agj list
```
