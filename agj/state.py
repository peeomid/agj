from __future__ import annotations

import re
from dataclasses import dataclass
from importlib import resources
from typing import Sequence

from agj.output_utils import has_visible_text
from agj.permissions import detect_permission_prompt_with_reason


@dataclass(frozen=True)
class ErrorPatterns:
    patterns: Sequence[re.Pattern[str]]


def _default_error_patterns() -> ErrorPatterns:
    return ErrorPatterns(
        patterns=(
            re.compile(r"stream disconnected before completion", re.IGNORECASE),
            re.compile(r"response\.failed event received", re.IGNORECASE),
        )
    )


def parse_error_patterns(text: str) -> ErrorPatterns:
    patterns: list[re.Pattern[str]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        patterns.append(re.compile(line, re.IGNORECASE))
    if not patterns:
        return _default_error_patterns()
    return ErrorPatterns(patterns=tuple(patterns))


def load_error_patterns() -> ErrorPatterns:
    try:
        text = resources.files("agj").joinpath("error_patterns.txt").read_text()
    except Exception:
        return _default_error_patterns()
    return parse_error_patterns(text)


DEFAULT_ERROR_PATTERNS = load_error_patterns()


def detect_error_with_reason(
    output: str,
    patterns: ErrorPatterns = DEFAULT_ERROR_PATTERNS,
) -> tuple[bool, str | None]:
    if not output:
        return False, None
    recent = _recent_text(output, 80)
    tail_lines = _last_nonempty_lines(recent, 8)
    for regex in patterns.patterns:
        match = regex.search(tail_lines)
        if match:
            snippet = _line_snippet(tail_lines, match.start())
            return True, f"error matched /{regex.pattern}/ in: {snippet}"
    return False, None


def detect_state_with_reason(
    output: str,
    agent_kind: str | None,
) -> tuple[str, str | None]:
    if not output or not has_visible_text(output):
        return "unknown", None
    permission, perm_reason = detect_permission_prompt_with_reason(output, agent_kind)
    if permission:
        return "permission", perm_reason
    error, err_reason = detect_error_with_reason(output)
    if error:
        return "error", err_reason
    return "running", None


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


def _last_nonempty_lines(text: str, count: int) -> str:
    if not text:
        return ""
    lines = text.splitlines()
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines[-count:])
