from __future__ import annotations

from agj.ansi import Ansi, paint
from agj.models import InstanceInfo


def format_session(instance: InstanceInfo) -> str:
    if instance.session is None:
        return "unmapped"
    return (
        f"w:{instance.session.window_id} "
        f"t:{instance.session.tab_id} "
        f"s:{instance.session.session_id}"
    )


def format_detailed(
    instances: list[InstanceInfo],
    *,
    include_session: bool,
    include_session_name: bool,
    include_path: bool,
    include_permission_reason: bool,
    include_permission_output: bool,
    color: bool,
) -> str:
    if not instances:
        return ""

    lines: list[str] = []
    for idx, inst in enumerate(instances, start=1):
        proc = inst.process
        header = f"[ID {idx}] PID {proc.pid}  {proc.name}"
        lines.append(header)
        if include_session_name:
            session_name = inst.session.title if inst.session and inst.session.title else ""
            label = paint("    Iterm tab title:", Ansi.blue, color)
            lines.append(f"{label} {session_name}")
            tab_id = inst.session.tab_id if inst.session and inst.session.tab_id else ""
            label = paint("    Iterm tab id:", Ansi.blue, color)
            lines.append(f"{label} {tab_id}")
        permission_value = _permission_value(inst.permission_prompt)
        perm_label = paint("    Permission prompt:", Ansi.blue, color)
        perm_value = _color_permission(permission_value, color)
        lines.append(f"{perm_label} {perm_value}")
        if include_permission_reason:
            reason = inst.permission_reason or ""
            label = paint("    Permission reason:", Ansi.blue, color)
            lines.append(f"{label} {reason}")
        if include_permission_output:
            output = inst.permission_output or ""
            label = paint("    Permission output (last 20 lines):", Ansi.blue, color)
            separator = paint(
                "    ────────────────────────────────────────────────────────────",
                Ansi.dim,
                color,
            )
            lines.append(label)
            lines.append(separator)
            if output:
                for line in output.splitlines():
                    lines.append(
                        paint(f"      {line}", Ansi.dim, color)
                    )
            else:
                lines.append(paint("      (empty)", Ansi.dim, color))
            lines.append(separator)
        if include_session:
            session_value = format_session(inst)
            label = paint("    Session:", Ansi.blue, color)
            lines.append(f"{label} {session_value}")
        if include_path:
            path_value = inst.session.path if inst.session and inst.session.path else ""
            label = paint("    Path:", Ansi.blue, color)
            lines.append(f"{label} {path_value}")
        cmd_label = paint("    Cmd:", Ansi.blue, color)
        lines.append(f"{cmd_label} {' '.join(proc.cmdline)}")
        if idx != len(instances):
            lines.append("")
    return "\n".join(lines)


def _permission_value(value: bool | None) -> str:
    if value is True:
        return "yes"
    if value is False:
        return "no"
    return "unknown"


def _color_permission(value: str, color: bool) -> str:
    if not color:
        return value
    if value == "yes":
        return paint(value, Ansi.red, color)
    if value == "no":
        return paint(value, Ansi.green, color)
    return paint(value, Ansi.yellow, color)
