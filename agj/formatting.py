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
    include_state_reason: bool,
    include_state_output: bool,
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
        state_value = _state_value(inst.state)
        state_label = paint("    State:", Ansi.blue, color)
        state_value_colored = _color_state(state_value, color)
        lines.append(f"{state_label} {state_value_colored}")
        if include_state_reason:
            reason = inst.state_reason or ""
            label = paint("    State reason:", Ansi.blue, color)
            lines.append(f"{label} {reason}")
        if include_state_output:
            output = inst.state_output or ""
            label = paint("    State output (last 20 lines):", Ansi.blue, color)
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


def _state_value(value: str | None) -> str:
    if not value:
        return "idle"
    return value


def _color_state(value: str, color: bool) -> str:
    if not color:
        return value
    if value in ("permission", "error"):
        return paint(value, Ansi.red, color)
    if value == "running":
        return paint(value, Ansi.green, color)
    return paint(value, Ansi.yellow, color)
