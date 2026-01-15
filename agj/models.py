from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class ProcessInfo:
    pid: int
    name: str
    cmdline: Sequence[str]
    ancestry: Sequence[int]


@dataclass(frozen=True)
class SessionInfo:
    session_id: str
    tab_id: str
    window_id: str
    pid: int | None
    title: str | None
    path: str | None = None


@dataclass(frozen=True)
class InstanceInfo:
    process: ProcessInfo
    session: SessionInfo | None
    state: str | None = None
    state_reason: str | None = None
    state_output: str | None = None
