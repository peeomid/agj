from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path
from dataclasses import asdict
from typing import Iterable

from agent_monitor.iterm import Iterm2Backend, ItermBackend
from agent_monitor.mapping import map_instances
from agent_monitor.models import InstanceInfo
from agent_monitor.processes import ProcessFinder, ProcessQuery, summarize_process

EXIT_NO_MATCHES = 1
EXIT_AMBIGUOUS = 2
EXIT_ITERM_UNAVAILABLE = 3


def _resolve_path(cmd: str) -> str | None:
    found = shutil.which(cmd)
    if not found:
        return None
    return str(Path(found).resolve())


def build_finder(patterns: list[str] | None) -> ProcessFinder:
    use_patterns = patterns or ["codex", "claude"]
    exact_paths = [p for p in (_resolve_path("codex"), _resolve_path("claude")) if p]
    return ProcessFinder(ProcessQuery(patterns=use_patterns, exact_paths=exact_paths))


def build_instances(finder: ProcessFinder, backend: ItermBackend) -> list[InstanceInfo]:
    processes = finder.find()
    sessions = backend.list_sessions()
    instances = map_instances(processes, sessions)
    instances.sort(key=lambda inst: inst.process.pid)
    return instances


def format_session(instance: InstanceInfo) -> str:
    if instance.session is None:
        return "unmapped"
    return (
        f"w:{instance.session.window_id} "
        f"t:{instance.session.tab_id} "
        f"s:{instance.session.session_id}"
    )


def _truncate(value: str, max_len: int) -> str:
    if len(value) <= max_len:
        return value
    return value[: max_len - 3] + "..."


def format_table(instances: list[InstanceInfo], stable: bool) -> str:
    rows = []
    header = ["id", "pid", "name", "cmd", "session"]
    rows.append(header)
    for idx, inst in enumerate(instances, start=1):
        cmd = " ".join(inst.process.cmdline)
        if not stable:
            cmd = _truncate(cmd, 80)
        rows.append(
            [
                str(idx),
                str(inst.process.pid),
                inst.process.name,
                cmd,
                format_session(inst),
            ]
        )

    if stable:
        return "\n".join("\t".join(row) for row in rows)

    widths = [0] * len(header)
    for row in rows:
        for i, value in enumerate(row):
            widths[i] = max(widths[i], len(value))

    lines = []
    for row in rows:
        padded = [value.ljust(widths[i]) for i, value in enumerate(row)]
        lines.append("  ".join(padded).rstrip())
    return "\n".join(lines)


def serialize_instances(instances: list[InstanceInfo]) -> str:
    payload = []
    for idx, inst in enumerate(instances, start=1):
        payload.append(
            {
                "id": idx,
                "process": asdict(inst.process),
                "session": asdict(inst.session) if inst.session else None,
            }
        )
    return json.dumps(payload, indent=2)


def filter_instances(
    instances: list[InstanceInfo],
    no_unmapped: bool,
    limit: int | None,
) -> list[InstanceInfo]:
    filtered = [inst for inst in instances if not no_unmapped or inst.session]
    if limit is not None:
        filtered = filtered[:limit]
    return filtered


def select_instance(
    instances: list[InstanceInfo],
    *,
    by_id: int | None,
    by_pid: int | None,
    by_session: str | None,
    match: str | None,
) -> InstanceInfo | None:
    if by_id is not None:
        if 1 <= by_id <= len(instances):
            return instances[by_id - 1]
        return None

    if by_pid is not None:
        matches = [inst for inst in instances if inst.process.pid == by_pid]
        return matches[0] if len(matches) == 1 else None

    if by_session is not None:
        matches = [
            inst
            for inst in instances
            if inst.session is not None and inst.session.session_id == by_session
        ]
        return matches[0] if len(matches) == 1 else None

    if match is not None:
        regex = re.compile(match, re.IGNORECASE)
        matches = [
            inst
            for inst in instances
            if regex.search(summarize_process(inst.process))
        ]
        return matches[0] if len(matches) == 1 else None

    return None


def count_matches(
    instances: list[InstanceInfo],
    *,
    by_id: int | None,
    by_pid: int | None,
    by_session: str | None,
    match: str | None,
) -> int:
    if by_id is not None:
        return 1 if 1 <= by_id <= len(instances) else 0
    if by_pid is not None:
        return sum(1 for inst in instances if inst.process.pid == by_pid)
    if by_session is not None:
        return sum(
            1
            for inst in instances
            if inst.session is not None and inst.session.session_id == by_session
        )
    if match is not None:
        regex = re.compile(match, re.IGNORECASE)
        return sum(1 for inst in instances if regex.search(summarize_process(inst.process)))
    return 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Monitor Codex/Claude iTerm2 sessions")
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="List instances")
    list_parser.add_argument(
        "--pattern",
        action="append",
        dest="patterns",
        help="Regex pattern to match process name/cmdline (repeatable)",
    )
    list_parser.add_argument("--json", action="store_true", help="Output JSON")
    list_parser.add_argument(
        "--stable",
        action="store_true",
        help="Output tab-separated rows with header",
    )
    list_parser.add_argument(
        "--no-unmapped", action="store_true", help="Hide unmapped processes"
    )
    list_parser.add_argument("--max", type=int, help="Limit number of rows")

    focus_parser = subparsers.add_parser("focus", help="Activate a session")
    focus_parser.add_argument(
        "--pattern",
        action="append",
        dest="patterns",
        help="Regex pattern to match process name/cmdline (repeatable)",
    )
    focus_parser.add_argument("--id", type=int, help="ID from list")
    focus_parser.add_argument("--pid", type=int, help="Process PID")
    focus_parser.add_argument("--session", help="iTerm2 session id")
    focus_parser.add_argument(
        "--match",
        help="Regex to match process name/cmdline; must match exactly one",
    )

    return parser.parse_args(argv)


def cmd_list(args: argparse.Namespace, backend: ItermBackend) -> int:
    finder = build_finder(args.patterns)
    instances = build_instances(finder, backend)
    instances = filter_instances(instances, args.no_unmapped, args.max)
    if not instances:
        print("No matching instances.")
        return EXIT_NO_MATCHES

    if args.json:
        print(serialize_instances(instances))
        return 0

    print(format_table(instances, args.stable))
    return 0


def cmd_focus(args: argparse.Namespace, backend: ItermBackend) -> int:
    finder = build_finder(args.patterns)
    instances = build_instances(finder, backend)
    if not instances:
        print("No matching instances.")
        return EXIT_NO_MATCHES

    match_count = count_matches(
        instances,
        by_id=args.id,
        by_pid=args.pid,
        by_session=args.session,
        match=args.match,
    )
    if match_count == 0:
        print("No matching selection.")
        return EXIT_NO_MATCHES
    if match_count > 1:
        print("Selection is ambiguous.")
        return EXIT_AMBIGUOUS

    instance = select_instance(
        instances,
        by_id=args.id,
        by_pid=args.pid,
        by_session=args.session,
        match=args.match,
    )
    if instance is None:
        print("No matching selection.")
        return EXIT_NO_MATCHES
    if instance.session is None:
        print("No iTerm session mapped for selection.")
        return EXIT_NO_MATCHES

    try:
        backend.activate(instance.session)
    except RuntimeError:
        print("iTerm2 API unavailable.")
        return EXIT_ITERM_UNAVAILABLE

    print(f"Activated PID {instance.process.pid}.")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    backend = Iterm2Backend()
    if args.command == "list":
        return cmd_list(args, backend)
    if args.command == "focus":
        if not any([args.id, args.pid, args.session, args.match]):
            print("One of --id/--pid/--session/--match is required.")
            return EXIT_NO_MATCHES
        return cmd_focus(args, backend)
    return 0
