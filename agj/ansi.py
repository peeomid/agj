from __future__ import annotations

import os
import sys


class Ansi:
    reset = "\033[0m"
    dim = "\033[2m"
    red = "\033[31m"
    green = "\033[32m"
    yellow = "\033[33m"
    blue = "\033[34m"


def color_enabled(mode: str) -> bool:
    if mode == "never":
        return False
    if mode == "always":
        return True
    if os.environ.get("NO_COLOR") is not None:
        return False
    return sys.stdout.isatty()


def paint(text: str, color: str, enabled: bool) -> str:
    if not enabled:
        return text
    return f"{color}{text}{Ansi.reset}"
