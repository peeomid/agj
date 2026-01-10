from __future__ import annotations

import re
import shutil
from pathlib import Path
from dataclasses import dataclass
from typing import Sequence

import psutil

from agx.models import ProcessInfo


@dataclass(frozen=True)
class ProcessQuery:
    patterns: Sequence[str]
    exact_paths: Sequence[str] = ()

    def regexes(self) -> Sequence[re.Pattern[str]]:
        return [re.compile(pat, re.IGNORECASE) for pat in self.patterns]


def process_matches(
    patterns: Sequence[re.Pattern[str]],
    name: str,
    cmdline: Sequence[str],
    exe_path: str | None,
    exact_paths: Sequence[str],
) -> bool:
    if exact_paths:
        candidates = []
        if exe_path:
            candidates.append(exe_path)
        if cmdline:
            candidates.append(cmdline[0])
            resolved = shutil.which(cmdline[0])
            if resolved:
                candidates.append(str(Path(resolved).resolve()))
        for candidate in candidates:
            if candidate in exact_paths:
                return True
        return False
    haystack = " ".join([name, *cmdline])
    return any(regex.search(haystack) for regex in patterns)


def build_ancestry(proc: psutil.Process, max_depth: int = 20) -> list[int]:
    ancestry: list[int] = []
    current = proc
    depth = 0
    while depth < max_depth:
        try:
            pid = current.pid
            ancestry.append(pid)
            if current.ppid() == 0:
                break
            current = current.parent()
            if current is None:
                break
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            break
        depth += 1
    return ancestry


class ProcessFinder:
    def __init__(self, query: ProcessQuery) -> None:
        self.query = query
        self._regexes = query.regexes()
        self._exact_paths = list(query.exact_paths)

    def find(self) -> list[ProcessInfo]:
        matches: list[ProcessInfo] = []
        for proc in psutil.process_iter(attrs=["pid", "name", "cmdline"]):
            try:
                name = proc.info.get("name") or ""
                cmdline = proc.info.get("cmdline") or []
                exe_path = None
                try:
                    exe_path = proc.exe()
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    exe_path = None
                if not process_matches(
                    self._regexes, name, cmdline, exe_path, self._exact_paths
                ):
                    continue
                ancestry = build_ancestry(proc)
                matches.append(
                    ProcessInfo(
                        pid=proc.pid,
                        name=name,
                        cmdline=cmdline,
                        ancestry=ancestry,
                    )
                )
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return matches


def summarize_process(proc: ProcessInfo, max_cmd: int = 80) -> str:
    cmd = " ".join(proc.cmdline)
    if len(cmd) > max_cmd:
        cmd = cmd[: max_cmd - 3] + "..."
    return f"{proc.name} ({proc.pid}) {cmd}".strip()
