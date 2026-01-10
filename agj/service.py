from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
import shutil

from agj.iterm import ItermBackend
from agj.mapping import map_instances
from agj.models import InstanceInfo
from agj.output_utils import has_visible_text, normalize_output
from agj.permissions import classify_agent, detect_permission_prompt_with_reason
from agj.processes import ProcessFinder, ProcessQuery


@dataclass(frozen=True)
class ListOptions:
    patterns: list[str] | None = None
    include_path: bool = True
    permission_check: bool = True
    permission_only: bool = False
    no_unmapped: bool = False
    limit: int | None = None
    permission_lines: int = 120


def build_finder(patterns: list[str] | None) -> ProcessFinder:
    use_patterns = patterns or ["codex", "claude"]
    exact_paths = [p for p in (_resolve_path("codex"), _resolve_path("claude")) if p]
    return ProcessFinder(ProcessQuery(patterns=use_patterns, exact_paths=exact_paths))


def _resolve_path(cmd: str) -> str | None:
    found = shutil.which(cmd)
    if not found:
        return None
    return str(Path(found).resolve())


def list_instances(backend: ItermBackend, options: ListOptions) -> list[InstanceInfo]:
    finder = build_finder(options.patterns)
    processes = finder.find()
    sessions = backend.list_sessions(include_path=options.include_path)
    instances = map_instances(processes, sessions)
    instances.sort(key=lambda inst: inst.process.pid)

    if options.permission_check:
        instances = _with_permission_status(instances, backend, options.permission_lines)

    if options.no_unmapped:
        instances = [inst for inst in instances if inst.session]
    if options.permission_only:
        instances = [inst for inst in instances if inst.permission_prompt is True]
    if options.limit is not None:
        instances = instances[: options.limit]
    return instances


def _with_permission_status(
    instances: list[InstanceInfo],
    backend: ItermBackend,
    permission_lines: int,
) -> list[InstanceInfo]:
    updated: list[InstanceInfo] = []
    for inst in instances:
        if inst.session is None:
            updated.append(replace(inst, permission_prompt=None, permission_reason=None))
            continue
        output = backend.capture_output(inst.session.session_id, lines=permission_lines)
        output = normalize_output(output)
        if not has_visible_text(output):
            output = normalize_output(
                backend.capture_output(inst.session.session_id, lines=None)
            )
        kind = classify_agent(inst.process)
        permission, reason = detect_permission_prompt_with_reason(output, kind)
        last_lines = _last_nonempty_lines(output, 20) if output else ""
        updated.append(
            replace(
                inst,
                permission_prompt=permission,
                permission_reason=reason,
                permission_output=last_lines,
            )
        )
    return updated


def _last_nonempty_lines(output: str, count: int) -> str:
    if not output:
        return ""
    lines = output.splitlines()
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines[-count:])
