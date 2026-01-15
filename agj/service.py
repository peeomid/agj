from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
import shutil
import time
from concurrent.futures import ThreadPoolExecutor

from agj.iterm import ItermBackend
from agj.mapping import map_instances
from agj.models import InstanceInfo
from agj.output_utils import has_visible_text, normalize_output
from agj.permissions import classify_agent, detect_permission_prompt_with_reason
from agj.state import detect_error_with_reason
from agj.processes import ProcessFinder, ProcessQuery


@dataclass(frozen=True)
class ListOptions:
    patterns: list[str] | None = None
    include_path: bool = True
    permission_check: bool = True
    permission_only: bool = False
    no_unmapped: bool = False
    limit: int | None = None
    permission_lines: int = 60
    idle_checks: tuple[float, ...] = (0.3, 0.8)


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
        instances = _with_state_status(
            instances,
            backend,
            options.permission_lines,
            options.idle_checks,
        )

    if options.no_unmapped:
        instances = [inst for inst in instances if inst.session]
    if options.permission_only:
        instances = [inst for inst in instances if inst.state == "permission"]
    if options.limit is not None:
        instances = instances[: options.limit]
    return instances


def _with_state_status(
    instances: list[InstanceInfo],
    backend: ItermBackend,
    permission_lines: int,
    idle_checks: tuple[float, ...],
) -> list[InstanceInfo]:
    if not instances:
        return []
    max_workers = min(8, len(instances))
    results: list[InstanceInfo] = [None] * len(instances)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = []
        for idx, inst in enumerate(instances):
            futures.append(
                executor.submit(_compute_state, inst, backend, permission_lines, idle_checks)
            )
        for idx, future in enumerate(futures):
            results[idx] = future.result()
    return results


def _compute_state(
    inst: InstanceInfo,
    backend: ItermBackend,
    permission_lines: int,
    idle_checks: tuple[float, ...],
) -> InstanceInfo:
    if inst.session is None:
        return replace(inst, state="idle", state_reason=None, state_output=None)
    raw_output = backend.capture_output(inst.session.session_id, lines=permission_lines)
    normalized = normalize_output(raw_output)
    if not has_visible_text(normalized):
        raw_output = backend.capture_output(inst.session.session_id, lines=None)
        normalized = normalize_output(raw_output)
    kind = classify_agent(inst.process)
    permission, perm_reason = detect_permission_prompt_with_reason(normalized, kind)
    if permission:
        last_lines = _last_nonempty_lines(normalized, 20) if normalized else ""
        return replace(
            inst,
            state="permission",
            state_reason=perm_reason,
            state_output=last_lines,
        )
    error, err_reason = detect_error_with_reason(normalized)
    if error:
        last_lines = _last_nonempty_lines(normalized, 20) if normalized else ""
        return replace(
            inst,
            state="error",
            state_reason=err_reason,
            state_output=last_lines,
        )
    for delay in idle_checks:
        if delay > 0:
            time.sleep(delay)
        raw_output_2 = backend.capture_output(inst.session.session_id, lines=permission_lines)
        normalized_2 = normalize_output(raw_output_2)
        if raw_output_2 != raw_output:
            last_lines = _last_nonempty_lines(normalized_2, 20) if normalized_2 else ""
            return replace(
                inst,
                state="running",
                state_reason=None,
                state_output=last_lines,
            )
    last_lines = _last_nonempty_lines(normalized, 20) if normalized else ""
    return replace(
        inst,
        state="idle",
        state_reason=None,
        state_output=last_lines,
    )


def _last_nonempty_lines(output: str, count: int) -> str:
    if not output:
        return ""
    lines = output.splitlines()
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines[-count:])
