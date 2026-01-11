from __future__ import annotations

import argparse
import asyncio
import sys
import time
from datetime import datetime
from dataclasses import dataclass, field

from agj.iterm import Iterm2Backend, ItermBackend
from agj.models import InstanceInfo
from agj.output_utils import has_visible_text, normalize_output, split_and_trim
from agj.service import ListOptions, list_instances
from agj.tui import MonitorTui, TuiState


@dataclass
class OutputCacheEntry:
    lines: list[str]
    last_output_at: str
    updated_at: float


@dataclass
class MonitorController:
    state: TuiState
    backend: ItermBackend
    patterns: list[str] | None
    output_cache: dict[str, OutputCacheEntry] = field(default_factory=dict, init=False)
    last_selected_session_id: str | None = field(default=None, init=False)
    last_fetch_started: float = field(default=0.0, init=False)
    last_selection_at: float = field(default=0.0, init=False)
    fetch_inflight: bool = field(default=False, init=False)
    last_list_refresh_at: float = field(default=0.0, init=False)
    cache_ttl: float = field(default=6.0, init=False)
    refresh_after: float = field(default=2.0, init=False)
    min_fetch_interval: float = field(default=0.6, init=False)

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
            session_ids = {
                inst.session.session_id
                for inst in instances
                if inst.session is not None
            }
            self.output_cache = {
                sid: entry for sid, entry in self.output_cache.items() if sid in session_ids
            }
            now = time.monotonic()
            for inst in instances:
                if inst.session is None:
                    continue
                if not inst.permission_output:
                    continue
                lines = split_and_trim(inst.permission_output)
                if not lines:
                    continue
                self.output_cache[inst.session.session_id] = OutputCacheEntry(
                    lines=lines,
                    last_output_at=datetime.now().strftime("%H:%M:%S"),
                    updated_at=now,
                )
            self.last_list_refresh_at = now
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
            self.state.output_loading = False
            return
        instance = self.state.instances[self.state.selected_index]
        if instance.session is None:
            self.state.output_lines = []
            self.state.last_output_at = ""
            self.state.output_loading = False
            return
        session_id = instance.session.session_id
        now = time.monotonic()
        selection_changed = session_id != self.last_selected_session_id
        if selection_changed:
            self.last_selected_session_id = session_id
            self.last_selection_at = now
        cached = self.output_cache.get(session_id)
        if cached:
            age = now - cached.updated_at
            if selection_changed:
                self.state.output_lines = cached.lines
                self.state.last_output_at = cached.last_output_at
                self.state.output_loading = True
                if age < self.refresh_after or now - self.last_fetch_started < self.min_fetch_interval:
                    self.state.output_loading = False
                    return
            elif age < self.cache_ttl and now - self.last_fetch_started < self.min_fetch_interval:
                self.state.output_lines = cached.lines
                self.state.last_output_at = cached.last_output_at
                self.state.output_loading = False
                return
            elif age < self.refresh_after:
                self.state.output_lines = cached.lines
                self.state.last_output_at = cached.last_output_at
                self.state.output_loading = False
                return
        elif selection_changed and instance.permission_output:
            lines = split_and_trim(instance.permission_output)
            if lines:
                self.state.output_lines = lines
                self.state.last_output_at = datetime.now().strftime("%H:%M:%S")
                self.output_cache[session_id] = OutputCacheEntry(
                    lines=lines,
                    last_output_at=self.state.last_output_at,
                    updated_at=now,
                )
                self.state.output_loading = True
                if now - self.last_list_refresh_at < self.refresh_after:
                    self.state.output_loading = False
                    return
        if selection_changed and (now - self.last_list_refresh_at) < self.refresh_after:
            self.state.output_loading = False
            return
        if self.fetch_inflight:
            return
        self.fetch_inflight = True
        self.last_fetch_started = now
        try:
            output = await asyncio.to_thread(
                self.backend.capture_output, session_id, 20
            )
            output = normalize_output(output)
            if not has_visible_text(output):
                output = normalize_output(
                    await asyncio.to_thread(
                        self.backend.capture_output, session_id, None
                    )
                )
            lines = split_and_trim(output)
            last_output_at = datetime.now().strftime("%H:%M:%S")
            self.state.output_lines = lines
            self.state.last_output_at = last_output_at
            self.output_cache[session_id] = OutputCacheEntry(
                lines=lines,
                last_output_at=last_output_at,
                updated_at=time.monotonic(),
            )
        except Exception as exc:
            self.state.output_lines = []
            self.state.last_output_at = ""
            self.state.status = f"Output refresh failed: {exc}"
        finally:
            self.state.output_loading = False
            self.fetch_inflight = False

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
