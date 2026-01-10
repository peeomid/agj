from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Awaitable, Callable

from prompt_toolkit.application import Application
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import HSplit, Layout, VSplit, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.styles import Style

from agj.models import InstanceInfo
from agj.processes import summarize_process


@dataclass
class TuiState:
    instances: list[InstanceInfo]
    selected_index: int = 0
    status: str = ""
    permission_only: bool = False
    hide_unmapped: bool = False
    output_lines: list[str] = None
    last_output_at: str = ""

    def __post_init__(self) -> None:
        if self.output_lines is None:
            self.output_lines = []


class MonitorTui:
    def __init__(
        self,
        state: TuiState,
        on_open: Callable[[], Awaitable[None]],
        on_refresh: Callable[[], Awaitable[None]],
        on_update_output: Callable[[], Awaitable[None]],
        on_toggle_permission: Callable[[], Awaitable[None]],
        on_toggle_unmapped: Callable[[], Awaitable[None]],
    ) -> None:
        self.state = state
        self.on_open = on_open
        self.on_refresh = on_refresh
        self.on_update_output = on_update_output
        self.on_toggle_permission = on_toggle_permission
        self.on_toggle_unmapped = on_toggle_unmapped
        self.header_control = FormattedTextControl(self._render_header)
        self.list_control = FormattedTextControl(self._render_list, focusable=True)
        self.detail_control = FormattedTextControl(self._render_detail)
        self.output_control = FormattedTextControl(self._render_output)
        self.status_control = FormattedTextControl(self._render_status)
        self.kb = self._build_keybindings()
        self.app = Application(
            layout=Layout(
                HSplit(
                    [
                        Window(self.header_control, height=1),
                        Window(
                            self.list_control,
                            always_hide_cursor=True,
                            height=10,
                            wrap_lines=False,
                        ),
                        HSplit(
                            [
                                Window(self.detail_control, height=7, wrap_lines=True),
                                Window(self.output_control),
                            ]
                        ),
                        Window(height=1, content=self.status_control),
                    ]
                )
            ),
            key_bindings=self.kb,
            style=self._style(),
            full_screen=True,
        )

    def _style(self) -> Style:
        return Style.from_dict(
            {
                "title": "bold",
                "selected": "reverse",
                "dim": "#888888",
                "header": "bold",
                "label": "#6fa8dc",
                "perm_yes": "fg:#ff5f5f bold",
                "perm_no": "fg:#5fd75f bold",
                "perm_unknown": "fg:#d7af00 bold",
            }
        )

    def _render_header(self):
        timestamp = datetime.now().strftime("%H:%M:%S")
        filters = []
        if self.state.permission_only:
            filters.append("perm-only")
        if self.state.hide_unmapped:
            filters.append("hide-unmapped")
        filter_text = ", ".join(filters) if filters else "none"
        return [
            ("class:header", "AGJ "),
            ("", f"({timestamp})  "),
            ("class:label", "filters:"),
            ("", f" {filter_text}"),
        ]

    def _render_list(self):
        lines = []
        if not self.state.instances:
            lines.append(
                (
                    "class:dim",
                    "No matching instances. Press r to refresh, q to quit.",
                )
            )
            return lines

        for idx, instance in enumerate(self.state.instances):
            prefix = "> " if idx == self.state.selected_index else "  "
            style = "class:selected" if idx == self.state.selected_index else ""
            proc = summarize_process(instance.process)
            session_name = (
                instance.session.title if instance.session and instance.session.title else ""
            )
            perm = _permission_value(instance.permission_prompt)
            perm_style = _permission_style(instance.permission_prompt)
            max_width = 48
            suffix = " | perm: "
            base = f"{prefix}[ID {idx + 1}] {proc} | session: {session_name}"
            base = _truncate_to_fit(base, max_width - len(suffix) - len(perm))
            line = base + suffix
            lines.append((style, line))
            lines.append((perm_style, perm))
            lines.append(("", "\n"))
        if lines:
            lines.pop()
        return lines

    def _render_detail(self):
        instance = self._selected_instance()
        if instance is None:
            return [("class:dim", "No selection")]
        session_name = (
            instance.session.title if instance.session and instance.session.title else ""
        )
        path = instance.session.path if instance.session and instance.session.path else ""
        perm = _permission_value(instance.permission_prompt)
        perm_style = _permission_style(instance.permission_prompt)
        return [
            ("class:label", "Iterm session name: "),
            ("", session_name),
            ("", "\n"),
            ("class:label", "Permission prompt: "),
            (perm_style, perm),
            ("", "\n"),
            ("class:label", "Path: "),
            ("", path),
            ("", "\n"),
            ("class:label", "Cmd: "),
            ("", " ".join(instance.process.cmdline)),
        ]

    def _render_output(self):
        header = f"Output (last 20 lines) • {self.state.last_output_at}"
        lines = [("class:label", header), ("", "\n")]
        if not self.state.output_lines:
            lines.append(("class:dim", "(empty)"))
            return lines
        for line in self.state.output_lines:
            lines.append(("", line))
            lines.append(("", "\n"))
        if lines:
            lines.pop()
        return lines

    def _render_status(self):
        return (
            "j/k move  o focus  r refresh  p perm-only  u hide-unmapped  q quit"
        )

    def _build_keybindings(self) -> KeyBindings:
        kb = KeyBindings()

        @kb.add("j")
        @kb.add("down")
        def _down(event) -> None:
            if not self.state.instances:
                return
            self.state.selected_index = min(
                self.state.selected_index + 1, len(self.state.instances) - 1
            )
            event.app.invalidate()

        @kb.add("k")
        @kb.add("up")
        def _up(event) -> None:
            if not self.state.instances:
                return
            self.state.selected_index = max(self.state.selected_index - 1, 0)
            event.app.invalidate()

        @kb.add("o")
        def _open(event) -> None:
            event.app.create_background_task(self._run_and_refresh(self.on_open))

        @kb.add("r")
        def _refresh(event) -> None:
            event.app.create_background_task(self._run_and_refresh(self.on_refresh))

        @kb.add("p")
        def _perm_only(event) -> None:
            event.app.create_background_task(self._run_and_refresh(self.on_toggle_permission))

        @kb.add("u")
        def _hide_unmapped(event) -> None:
            event.app.create_background_task(self._run_and_refresh(self.on_toggle_unmapped))

        @kb.add("q")
        @kb.add("c-c")
        def _quit(event) -> None:
            event.app.exit()

        return kb

    async def _run_and_refresh(self, fn: Callable[[], Awaitable[None]]) -> None:
        await fn()
        self.app.invalidate()

    async def run(self) -> None:
        self.app.create_background_task(self._auto_update_output())
        await self.app.run_async()

    async def _auto_update_output(self) -> None:
        while True:
            await self.on_update_output()
            self.app.invalidate()
            await asyncio.sleep(3)

    def _selected_instance(self) -> InstanceInfo | None:
        if not self.state.instances:
            return None
        if self.state.selected_index < 0 or self.state.selected_index >= len(self.state.instances):
            return None
        return self.state.instances[self.state.selected_index]


def _permission_value(value: bool | None) -> str:
    if value is True:
        return "yes"
    if value is False:
        return "no"
    return "unknown"


def _permission_style(value: bool | None) -> str:
    if value is True:
        return "class:perm_yes"
    if value is False:
        return "class:perm_no"
    return "class:perm_unknown"


def _truncate_to_fit(value: str, max_len: int) -> str:
    if max_len < 0:
        return ""
    if len(value) <= max_len:
        return value
    if max_len <= 3:
        return value[:max_len]
    return value[: max_len - 3] + "..."
