from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Awaitable, Callable

from prompt_toolkit.application import Application
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import HSplit, Layout, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.styles import Style

from agent_monitor.models import InstanceInfo
from agent_monitor.processes import summarize_process


@dataclass
class TuiState:
    instances: list[InstanceInfo]
    selected_index: int = 0
    status: str = ""


class MonitorTui:
    def __init__(
        self,
        state: TuiState,
        on_open: Callable[[], Awaitable[None]],
        on_refresh: Callable[[], Awaitable[None]],
    ) -> None:
        self.state = state
        self.on_open = on_open
        self.on_refresh = on_refresh
        self.list_control = FormattedTextControl(self._render_list, focusable=True)
        self.status_control = FormattedTextControl(self._render_status)
        self.kb = self._build_keybindings()
        self.app = Application(
            layout=Layout(
                HSplit(
                    [
                        Window(self.list_control, always_hide_cursor=True),
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
            }
        )

    def _render_list(self):
        lines = []
        if not self.state.instances:
            lines.append(("dim", "No matching instances. Press r to refresh, q to quit."))
            return lines

        for idx, instance in enumerate(self.state.instances):
            prefix = "> " if idx == self.state.selected_index else "  "
            style = "selected" if idx == self.state.selected_index else ""
            proc = summarize_process(instance.process)
            if instance.session:
                session_part = (
                    f"win:{instance.session.window_id} "
                    f"tab:{instance.session.tab_id} "
                    f"session:{instance.session.session_id}"
                )
            else:
                session_part = "unmapped"
            line = f"{prefix}[{idx + 1}] {proc} | {session_part}"
            lines.append((style, line))
            lines.append(("", "\n"))
        if lines:
            lines.pop()
        return lines

    def _render_status(self):
        return self.state.status

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

        @kb.add("q")
        @kb.add("c-c")
        def _quit(event) -> None:
            event.app.exit()

        return kb

    async def _run_and_refresh(self, fn: Callable[[], Awaitable[None]]) -> None:
        await fn()
        self.app.invalidate()

    async def run(self) -> None:
        await self.app.run_async()
