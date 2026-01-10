# Permission Prompt Texts (User Reports)

This document captures user-reported prompt text shown by Codex CLI and Claude Code when asking for permission. These strings are used to build detection regexes.

Patterns are loaded from:
```
agj/permission_patterns.txt
```

## Claude Code

Reported prompt text (example):

> "Do you want to proceed?"

> "No, and tell Claude what to do differently (esc)"

Source:
```
https://github.com/anthropics/claude-code/issues/10732
```

## Codex CLI

Reported prompt text (example):

> "Would you like to run the following command?"

> "Yes, and don't ask again for this command"

Source:
```
https://github.com/openai/codex/issues/5639
```
