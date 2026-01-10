from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime
from dataclasses import dataclass

from agj.iterm import Iterm2Backend, ItermBackend
from agj.models import InstanceInfo
from agj.service import ListOptions, list_instances
from agj.tui import MonitorTui, TuiState


@dataclass
class MonitorController:
    state: TuiState
    backend: ItermBackend
    patterns: list[str] | None

    async def refresh(self) -> None:
        try:
            options = ListOptions(
                patterns=self.patterns,
                include_path=True,
                permission_check=True,
                permission_only=self.state.permission_only,
                no_unmapped=self.state.hide_unmapped,
                limit=None,
            )
            instances = await asyncio.to_thread(list_instances, self.backend, options)
            self.state.instances = instances
            if self.state.selected_index >= len(instances):
                self.state.selected_index = max(len(instances) - 1, 0)
            self.state.status = f"Found {len(instances)} instance(s)."
        except Exception as exc:
            self.state.status = f"Refresh failed: {exc}"

    async def open_selected(self) -> None:
        if not self.state.instances:
            self.state.status = "No instances to open."
            return
        instance = self.state.instances[self.state.selected_index]
        if instance.session is None:
            self.state.status = "No iTerm session mapped for selection."
            return
        try:
            await asyncio.to_thread(self.backend.activate, instance.session)
            self.state.status = f"Activated {instance.process.pid}."
        except Exception as exc:
            self.state.status = f"Activation failed: {exc}"

    async def update_output(self) -> None:
        if not self.state.instances:
            self.state.output_lines = []
            self.state.last_output_at = ""
            return
        instance = self.state.instances[self.state.selected_index]
        if instance.session is None:
            self.state.output_lines = []
            self.state.last_output_at = ""
            return
        output = await asyncio.to_thread(
            self.backend.capture_output, instance.session.session_id, 20
        )
        self.state.output_lines = output.splitlines()
        self.state.last_output_at = datetime.now().strftime("%H:%M:%S")

    async def toggle_permission_only(self) -> None:
        self.state.permission_only = not self.state.permission_only
        await self.refresh()

    async def toggle_unmapped(self) -> None:
        self.state.hide_unmapped = not self.state.hide_unmapped
        await self.refresh()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Monitor Codex/Claude iTerm2 sessions")
    parser.add_argument(
        "--pattern",
        action="append",
        dest="patterns",
        help="Regex pattern to match process name/cmdline (repeatable)",
    )
    return parser.parse_args(argv)


def main(patterns: list[str] | None = None) -> None:
    argv = sys.argv[1:]
    if argv[:1] == ["tui"]:
        argv = argv[1:]
    args = parse_args(argv)
    use_patterns = patterns if patterns is not None else args.patterns
    if not sys.stdin.isatty():
        print("TUI requires an interactive terminal.")
        return
    backend = Iterm2Backend()
    state = TuiState(instances=[], selected_index=0, status="Loading...")
    controller = MonitorController(state=state, backend=backend, patterns=use_patterns)

    async def _run() -> None:
        await controller.refresh()
        tui = MonitorTui(
            state,
            controller.open_selected,
            controller.refresh,
            controller.update_output,
            controller.toggle_permission_only,
            controller.toggle_unmapped,
        )
        await tui.run()

    asyncio.run(_run())




if __name__ == "__main__":
    main()
