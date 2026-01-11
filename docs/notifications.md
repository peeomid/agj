# Notification Spec (TUI)

## Summary
When the TUI is running, AGJ sends a macOS notification the first time a session
starts asking for permission. It sends only once per prompt and fires again only
after the prompt disappears and returns.

## Trigger rules
- Detect transitions from `no/unknown` → `yes` for `permission_prompt`.
- Send exactly one notification per session per prompt.
- Clear the “notified” state once the prompt is no longer present.

## Notification content
- **Title:** `AGJ - Agent needs approval`
- **Subtitle:** `{Agent} #1 - {Iterm session name} - {Working dir base name or repo name}`
- **Body:** A few lines from the prompt output (trimmed)
- **Action button:** `Go to session` (focuses the iTerm pane)

## Content rules
- Agent is `Codex` or `Claude` (fallback: `Agent`).
- `#1` is the list index from the current TUI list (1-based).
- Working dir uses the path basename when available.
- Body uses the last 3 non-empty lines of prompt output, trimmed to a max size.

## Implementation plan (updated)
- Drop `macos-notifications` because Notification Center delegates are not
  available in a pure CLI/TUI process (causes runtime errors and no display).
- Use `alerter` as the action-button backend. It works from the CLI and returns
  which action was clicked.
- Trigger notification only on transition to `permission_prompt = yes`.
- Use `alerter -actions "Go to session" -json` and call the focus action when
  the action is clicked.

## Requirements / behavior
- Requires `alerter` on PATH for action buttons.
- The TUI process must remain running to receive action callbacks.
- Notifications are triggered from the TUI refresh loop.
