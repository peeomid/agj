# Notification Spec (TUI)

## Summary
When the TUI is running, AGJ sends a macOS notification when a session first
enters `permission` (or `error`). It will also re-notify if the prompt stays
active for a long time, using a cooldown.

## Trigger rules
- Detect transitions to `permission` or `error`.
- Send exactly one notification per session per transition.
- Maintain a per-session cooldown timer to re-notify if still blocked.
- Clear the “notified” state once the prompt is no longer present.

## Notification content
- **Title:** `AGJ - Agent needs approval` (or error)
- **Subtitle:** `{Agent} #1 - {Iterm tab title} - {Working dir base name or repo name}`
- **Body:** A few lines from the prompt output (trimmed)
- Clicking the notification focuses the iTerm pane.
- Optional sound (`--notify-sound`) plays when the notification fires.

## Content rules
- Agent is `Codex` or `Claude` (fallback: `Agent`).
- `#1` is the list index from the current TUI list (1-based).
- Working dir uses the path basename when available.
- Body uses the last 3 non-empty lines of prompt output, trimmed to a max size.

## Implementation plan (updated)
- Drop `macos-notifications` because Notification Center delegates are not
  available in a pure CLI/TUI process (causes runtime errors and no display).
- Use `alerter` as the notification backend. It works from the CLI and returns
  activation events from Notification Center.
- Trigger notification only on transition to `permission_prompt = yes`.
- Use `alerter -json` and call the focus action when the notification is clicked.
- Pass `-sound` when a notification sound is configured.

## Requirements / behavior
- Requires `alerter` on PATH for notifications.
- The TUI process must remain running to receive action callbacks.
- Notifications are triggered from the TUI refresh loop.
- Cooldown is currently 30s per session (TUI only).
