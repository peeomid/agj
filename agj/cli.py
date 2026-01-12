from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict

from agj.iterm import Iterm2Backend, ItermBackend
from agj.mapping import map_instances
from agj.models import InstanceInfo
from agj.output_utils import normalize_output, trim_trailing_blank_lines
from agj.processes import ProcessFinder, summarize_process
from agj.ansi import color_enabled
from agj.formatting import format_detailed, format_session
from agj.service import ListOptions, build_finder, list_instances
from agj.app import main as tui_main

EXIT_NO_MATCHES = 1
EXIT_AMBIGUOUS = 2
EXIT_ITERM_UNAVAILABLE = 3


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


def _truncate(value: str, max_len: int) -> str:
    if len(value) <= max_len:
        return value
    return value[: max_len - 3] + "..."


def format_table(
    instances: list[InstanceInfo],
    stable: bool,
    include_path: bool,
    include_session: bool,
    include_session_name: bool,
    include_permission: bool,
) -> str:
    rows = []
    header = ["id", "pid", "name"]
    if include_session_name:
        header.append("Iterm session name")
    if include_permission:
        header.append("permission")
    header.append("cmd")
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
        session_name = ""
        if include_session_name:
            session_name = inst.session.title if inst.session and inst.session.title else ""
            if not stable:
                session_name = _truncate(session_name, 40)
        permission_value = ""
        if include_permission:
            if inst.permission_prompt is True:
                permission_value = "yes"
            elif inst.permission_prompt is False:
                permission_value = "no"
            else:
                permission_value = "unknown"
        rows.append(
            [
                str(idx),
                str(inst.process.pid),
                inst.process.name,
                *([session_name] if include_session_name else []),
                *([permission_value] if include_permission else []),
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
                "permission_prompt": inst.permission_prompt,
                "permission_reason": inst.permission_reason,
                "permission_output": inst.permission_output,
            }
        )
    return json.dumps(payload, indent=2)


def filter_instances(
    instances: list[InstanceInfo],
    no_unmapped: bool,
    limit: int | None,
    permission_only: bool,
) -> list[InstanceInfo]:
    filtered = [inst for inst in instances if not no_unmapped or inst.session]
    if permission_only:
        filtered = [inst for inst in filtered if inst.permission_prompt is True]
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
    parser = argparse.ArgumentParser(
        description="Monitor Codex/Claude iTerm2 sessions",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  agj list\n"
            "  agj list --no-with-path --with-session\n"
            "  agj focus --match claude\n"
            "  agj focus --id 2\n"
            "  agj capture --id 1 --lines 50\n"
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser(
        "list",
        help="List instances",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="List matching Codex/Claude instances.",
        epilog=(
            "Examples:\n"
            "  agj list\n"
            "  agj list --with-session\n"
            "  agj list --no-with-path --stable\n"
            "  agj list --pattern codex --pattern claude\n"
        ),
    )
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
    list_parser.add_argument(
        "--with-session-name",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Include iTerm session name (default: on)",
    )
    list_parser.add_argument(
        "--permission-only",
        action="store_true",
        help="Show only instances asking for permission",
    )
    list_parser.add_argument(
        "--no-permission-check",
        action="store_true",
        help="Skip permission prompt detection",
    )
    list_parser.add_argument(
        "--permission-debug",
        action="store_true",
        help="Show why a permission prompt was detected",
    )
    list_parser.add_argument(
        "--view",
        choices=["detail", "table"],
        default="detail",
        help="Output format (default: detail)",
    )
    list_parser.add_argument(
        "--color",
        choices=["auto", "always", "never"],
        default="auto",
        help="Colorize output (default: auto)",
    )

    focus_parser = subparsers.add_parser(
        "focus",
        help="Activate a session",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="Activate the iTerm2 pane for a selected instance.",
        epilog=(
            "Examples:\n"
            "  agj focus --id 1\n"
            "  agj focus --pid 20218\n"
            "  agj focus --match claude\n"
            "  agj focus --session 7DCEFA6B-7465-4572-858D-96A407199891\n"
        ),
    )
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
        "capture",
        help="Print current output for a session",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="Print current output for a selected session.",
        epilog=(
            "Examples:\n"
            "  agj capture --id 1\n"
            "  agj capture --match codex --lines 100\n"
        ),
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

    tui_parser = subparsers.add_parser(
        "tui",
        help="Open the interactive TUI",
    )
    tui_parser.add_argument(
        "--pattern",
        action="append",
        dest="patterns",
        help="Regex pattern to match process name/cmdline (repeatable)",
    )
    tui_parser.add_argument(
        "--notify",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Send macOS notifications for new permission prompts (default: on)",
    )
    tui_parser.add_argument(
        "--notify-sound",
        help='Play a sound on notifications (examples: "Glass", "Ping", "default", "none")',
    )

    return parser.parse_args(argv)


def cmd_list(args: argparse.Namespace, backend: ItermBackend) -> int:
    include_path = True if args.with_path is None else args.with_path
    include_session_name = True if args.with_session_name is None else args.with_session_name
    options = ListOptions(
        patterns=args.patterns,
        include_path=include_path,
        permission_check=not args.no_permission_check,
        permission_only=args.permission_only,
        no_unmapped=args.no_unmapped,
        limit=args.max,
    )
    instances = list_instances(backend, options)
    if not instances:
        print("No matching instances.")
        return EXIT_NO_MATCHES

    if args.json:
        print(serialize_instances(instances))
        return 0

    hint = 'Hint: Use "agj focus --id N" (example: agj focus --id 1)'
    color = color_enabled(args.color)
    if args.view == "detail" and not args.stable:
        print(
            format_detailed(
                instances,
                include_session=args.with_session,
                include_session_name=include_session_name,
                include_path=include_path,
                include_permission_reason=args.permission_debug,
                include_permission_output=args.permission_debug,
                color=color,
            )
        )
        print("")
        print(hint)
        return 0

    print(
        format_table(
            instances,
            args.stable,
            include_path,
            args.with_session,
            include_session_name,
            include_permission=True,
        )
    )
    print("")
    print(hint)
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

    sys.stdout.write(trim_trailing_blank_lines(normalize_output(output)))
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
    if args.command == "tui":
        tui_main(
            patterns=getattr(args, "patterns", None),
            notify=args.notify,
            notify_sound=args.notify_sound,
        )
        return 0
    return 0
