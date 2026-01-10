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
            re.compile(r"Yes, and don't ask again for this command", re.IGNORECASE),
        ),
        claude=(
            re.compile(r"Do you want to proceed\?", re.IGNORECASE),
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
    if agent_kind == "codex":
        for regex in patterns.codex:
            if regex.search(output):
                return True, f"codex matched /{regex.pattern}/"
        return False, None
    if agent_kind == "claude":
        for regex in patterns.claude:
            if regex.search(output):
                return True, f"claude matched /{regex.pattern}/"
        return False, None
    return False, None
