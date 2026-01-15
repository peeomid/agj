from __future__ import annotations

import re
from dataclasses import dataclass
from importlib import resources
from typing import Sequence

from agj.models import ProcessInfo


@dataclass(frozen=True)
class PermissionPatterns:
    codex: Sequence[re.Pattern[str]]
    claude: Sequence[re.Pattern[str]]


def _default_patterns() -> PermissionPatterns:
    return PermissionPatterns(
        codex=(
            re.compile(r"Would you like to run the following command\?", re.IGNORECASE),
            re.compile(r"Would you like to .+\?", re.IGNORECASE),
            re.compile(r"Would you like (me )?to .+\?", re.IGNORECASE),
            re.compile(r"Do you want to .+\?", re.IGNORECASE),
            re.compile(r"Yes, and don't ask again for this command", re.IGNORECASE),
        ),
        claude=(
            re.compile(r"Do you want to proceed\?", re.IGNORECASE),
            re.compile(r"Do you want to .+\?", re.IGNORECASE),
            re.compile(r"Would you like to .+\?", re.IGNORECASE),
            re.compile(r"Would you like (me )?to .+\?", re.IGNORECASE),
            re.compile(r"Do you want to make this edit to", re.IGNORECASE),
            re.compile(r"No, and tell Claude what to do differently", re.IGNORECASE),
        ),
    )


def parse_pattern_text(text: str) -> PermissionPatterns:
    codex: list[re.Pattern[str]] = []
    claude: list[re.Pattern[str]] = []
    current: str | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            current = line[1:-1].strip().lower()
            continue
        if current == "codex":
            codex.append(re.compile(line, re.IGNORECASE))
        elif current == "claude":
            claude.append(re.compile(line, re.IGNORECASE))
    if not codex or not claude:
        return _default_patterns()
    return PermissionPatterns(codex=tuple(codex), claude=tuple(claude))


def load_patterns() -> PermissionPatterns:
    try:
        text = resources.files("agj").joinpath("permission_patterns.txt").read_text()
    except Exception:
        return _default_patterns()
    return parse_pattern_text(text)


DEFAULT_PATTERNS = load_patterns()


def classify_agent(proc: ProcessInfo) -> str | None:
    haystack = " ".join([proc.name, *proc.cmdline]).lower()
    if "codex" in haystack:
        return "codex"
    if "claude" in haystack:
        return "claude"
    return None


def detect_permission_prompt(
    output: str,
    agent_kind: str | None,
    patterns: PermissionPatterns = DEFAULT_PATTERNS,
) -> bool:
    return detect_permission_prompt_with_reason(output, agent_kind, patterns)[0]


def detect_permission_prompt_with_reason(
    output: str,
    agent_kind: str | None,
    patterns: PermissionPatterns = DEFAULT_PATTERNS,
) -> tuple[bool, str | None]:
    if not output or agent_kind is None:
        return False, None
    recent = _recent_text(output, 200)
    if agent_kind == "codex":
        for regex in patterns.codex:
            match = regex.search(recent)
            if match and _has_codex_confirm(recent):
                snippet = _line_snippet(recent, match.start())
                if '"' in snippet:
                    continue
                return True, f"codex matched /{regex.pattern}/ in: {snippet}"
        return False, None
    if agent_kind == "claude":
        for regex in patterns.claude:
            match = regex.search(recent)
            if match and _has_claude_confirm(recent):
                snippet = _line_snippet(recent, match.start())
                if '"' in snippet:
                    continue
                return True, f"claude matched /{regex.pattern}/ in: {snippet}"
        return False, None
    return False, None


def _line_snippet(text: str, index: int) -> str:
    if not text:
        return ""
    start = text.rfind("\n", 0, index)
    end = text.find("\n", index)
    if start == -1:
        start = 0
    else:
        start += 1
    if end == -1:
        end = len(text)
    snippet = text[start:end].strip()
    if len(snippet) > 120:
        snippet = snippet[:117] + "..."
    return snippet


def _recent_text(text: str, max_lines: int) -> str:
    if not text:
        return ""
    lines = text.splitlines()
    return "\n".join(lines[-max_lines:])


def _has_codex_confirm(text: str) -> bool:
    if re.search(r"\(no menu shown\)", text, re.IGNORECASE):
        # Allow no-menu prompts like "proceed/continue", but not command approvals.
        if "run the following command" in text.lower():
            return False
        return True
    for line in text.splitlines():
        if '"' in line or ":" in line:
            continue
        if re.search(r"^\s*[›>]\s*1\.", line):
            return True
        if re.search(r"^\s*1\.\s*Yes, proceed", line, re.IGNORECASE):
            return True
    return False


def _has_claude_confirm(text: str) -> bool:
    if re.search(r"\(no menu shown\)", text, re.IGNORECASE):
        return True
    for line in text.splitlines():
        if '"' in line or ":" in line:
            continue
        if re.search(r"^\s*Do you want to .+\?\s*$", line, re.IGNORECASE):
            return True
        if re.search(r"^\s*[❯>]\s*1\.", line):
            return True
        if re.search(r"^\s*1\.\s*Yes", line, re.IGNORECASE):
            return True
    return False
