from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from dataclasses import asdict
from pathlib import Path

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


def build_instances(
    finder: ProcessFinder,
    backend: ItermBackend,
    *,
    include_path: bool = False,
) -> list[InstanceInfo]:
    processes = finder.find()
    sessions = backend.list_sessions(include_path=include_path)
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


def format_table(
    instances: list[InstanceInfo],
    stable: bool,
    include_path: bool,
    include_session: bool,
) -> str:
    rows = []
    header = ["id", "pid", "name", "cmd"]
    if include_session:
        header.append("session")
    if include_path:
        header.append("path")
    rows.append(header)
    for idx, inst in enumerate(instances, start=1):
        cmd = " ".join(inst.process.cmdline)
        if not stable:
            cmd = _truncate(cmd, 80)
        path_value = ""
        if include_path:
            path_value = inst.session.path if inst.session else ""
            if not stable:
                path_value = _truncate(path_value, 60)
        rows.append(
            [
                str(idx),
                str(inst.process.pid),
                inst.process.name,
                cmd,
                *([format_session(inst)] if include_session else []),
                *([path_value] if include_path else []),
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
    list_parser.add_argument(
        "--with-path",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Include session working directory (requires shell integration)",
    )
    list_parser.add_argument(
        "--with-session",
        action="store_true",
        help="Include iTerm window/tab/session identifiers",
    )

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

    capture_parser = subparsers.add_parser(
        "capture", help="Print current output for a session"
    )
    capture_parser.add_argument(
        "--pattern",
        action="append",
        dest="patterns",
        help="Regex pattern to match process name/cmdline (repeatable)",
    )
    capture_parser.add_argument("--id", type=int, help="ID from list")
    capture_parser.add_argument("--pid", type=int, help="Process PID")
    capture_parser.add_argument("--session", help="iTerm2 session id")
    capture_parser.add_argument(
        "--match",
        help="Regex to match process name/cmdline; must match exactly one",
    )
    capture_parser.add_argument(
        "--lines",
        type=int,
        help="Capture last N lines from scrollback+visible instead of current view",
    )

    return parser.parse_args(argv)


def cmd_list(args: argparse.Namespace, backend: ItermBackend) -> int:
    finder = build_finder(args.patterns)
    include_path = True if args.with_path is None else args.with_path
    instances = build_instances(finder, backend, include_path=include_path)
    instances = filter_instances(instances, args.no_unmapped, args.max)
    if not instances:
        print("No matching instances.")
        return EXIT_NO_MATCHES

    if args.json:
        print(serialize_instances(instances))
        return 0

    print(format_table(instances, args.stable, include_path, args.with_session))
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


def cmd_capture(args: argparse.Namespace, backend: ItermBackend) -> int:
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
        output = backend.capture_output(instance.session.session_id, args.lines)
    except RuntimeError:
        print("iTerm2 API unavailable.")
        return EXIT_ITERM_UNAVAILABLE

    sys.stdout.write(output)
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
    if args.command == "capture":
        if not any([args.id, args.pid, args.session, args.match]):
            print("One of --id/--pid/--session/--match is required.")
            return EXIT_NO_MATCHES
        return cmd_capture(args, backend)
    return 0
