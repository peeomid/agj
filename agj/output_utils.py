from __future__ import annotations


def _line_has_visible_text(line: str) -> bool:
    for ch in line:
        if ch.isprintable() and not ch.isspace():
            return True
    return False


def trim_trailing_blank_lines(text: str) -> str:
    if not text:
        return text
    lines = text.splitlines()
    while lines and not _line_has_visible_text(lines[-1]):
        lines.pop()
    return "\n".join(lines)


def split_and_trim(text: str) -> list[str]:
    trimmed = trim_trailing_blank_lines(text)
    if not trimmed:
        return []
    return trimmed.splitlines()


def has_visible_text(text: str) -> bool:
    if not text:
        return False
    return any(_line_has_visible_text(line) for line in text.splitlines())


def normalize_output(text: str) -> str:
    if not text:
        return text
    return text.replace("\x00", "")
