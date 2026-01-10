from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass

from agent_monitor.iterm import Iterm2Backend, ItermBackend
from agent_monitor.mapping import map_instances
from agent_monitor.models import InstanceInfo
from agent_monitor.processes import ProcessFinder, ProcessQuery
from agent_monitor.tui import MonitorTui, TuiState


@dataclass
class MonitorController:
    state: TuiState
    finder: ProcessFinder
    backend: ItermBackend

    async def refresh(self) -> None:
        try:
            processes = self.finder.find()
            sessions = await self.backend.list_sessions()
            instances = map_instances(processes, sessions)
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
            await self.backend.activate(instance.session)
            self.state.status = f"Activated {instance.process.pid}."
        except Exception as exc:
            self.state.status = f"Activation failed: {exc}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Monitor Codex/Claude iTerm2 sessions")
    parser.add_argument(
        "--pattern",
        action="append",
        dest="patterns",
        help="Regex pattern to match process name/cmdline (repeatable)",
    )
    return parser.parse_args()


def build_finder(patterns: list[str] | None) -> ProcessFinder:
    use_patterns = patterns or ["codex", "claude"]
    return ProcessFinder(ProcessQuery(patterns=use_patterns))


def main() -> None:
    args = parse_args()
    finder = build_finder(args.patterns)
    backend = Iterm2Backend()
    state = TuiState(instances=[], selected_index=0, status="Loading...")
    controller = MonitorController(state=state, finder=finder, backend=backend)

    async def _run() -> None:
        await controller.refresh()
        tui = MonitorTui(state, controller.open_selected, controller.refresh)
        await tui.run()

    asyncio.run(_run())


if __name__ == "__main__":
    main()
