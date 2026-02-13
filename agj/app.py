from __future__ import annotations

import argparse
import asyncio
import sys
import time
from datetime import datetime
from dataclasses import dataclass, field
from typing import Callable

from agj.iterm import Iterm2Backend, ItermBackend
from agj.models import InstanceInfo
from agj.notifications import (
    NotificationSender,
    build_payload,
    build_focus_command,
    default_sender,
    state_transition_events,
)
from agj.output_utils import has_visible_text, normalize_output, split_and_trim
from agj.service import ListOptions, add_state_status, list_instances
from agj.tui import MonitorTui, TuiState


def _tui_sort_key(instance: InstanceInfo) -> tuple:
    session_name = ""
    dir_name = ""
    if instance.session is not None:
        session_name = (instance.session.title or "").strip()
        path = instance.session.path or ""
        if path:
            dir_name = path.rstrip("/").split("/")[-1]
    return (
        session_name == "",
        session_name.lower(),
        dir_name == "",
        dir_name.lower(),
        instance.process.pid,
    )


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
    scan_backend: ItermBackend | None = None
    notify_enabled: bool = True
    notify_sound: str | None = None
    notifier: NotificationSender | None = None
    idle_checks: tuple[float, ...] = (0.3, 0.8)
    output_cache: dict[str, OutputCacheEntry] = field(default_factory=dict, init=False)
    last_selected_session_id: str | None = field(default=None, init=False)
    last_fetch_started: float = field(default=0.0, init=False)
    last_selection_at: float = field(default=0.0, init=False)
    fetch_inflight: bool = field(default=False, init=False)
    last_list_refresh_at: float = field(default=0.0, init=False)
    state_state: dict[str, str] = field(default_factory=dict, init=False)
    notifications_initialized: bool = field(default=False, init=False)
    last_notified_at: dict[str, float] = field(default_factory=dict, init=False)
    notify_cooldown: float = field(default=30.0, init=False)
    cache_ttl: float = field(default=6.0, init=False)
    refresh_after: float = field(default=2.0, init=False)
    min_fetch_interval: float = field(default=0.6, init=False)
    on_update: Callable[[], None] | None = field(default=None, init=False, repr=False)
    suspend_output_until: float = field(default=0.0, init=False)

    def _signal(self) -> None:
        if self.on_update:
            try:
                self.on_update()
            except Exception:
                return

    async def refresh(self) -> None:
        try:
            self.state.status = "Connecting to iTerm2..."
            self._signal()
            self.state.status = "Listing sessions..."
            self._signal()
            selected_session_id = None
            selected_pid = None
            if self.state.instances and 0 <= self.state.selected_index < len(self.state.instances):
                current = self.state.instances[self.state.selected_index]
                selected_pid = current.process.pid
                if current.session is not None:
                    selected_session_id = current.session.session_id
            options = ListOptions(
                patterns=self.patterns,
                include_path=True,
                permission_check=False,
                permission_only=False,
                no_unmapped=self.state.hide_unmapped,
                limit=None,
                idle_checks=self.idle_checks,
            )
            instances = await asyncio.to_thread(list_instances, self.backend, options)
            self.state.instances = sorted(instances, key=_tui_sort_key)
            self._signal()
            if self.state.instances:
                selected_index = None
                if selected_session_id is not None:
                    for idx, inst in enumerate(self.state.instances):
                        if inst.session and inst.session.session_id == selected_session_id:
                            selected_index = idx
                            break
                if selected_index is None and selected_pid is not None:
                    for idx, inst in enumerate(self.state.instances):
                        if inst.process.pid == selected_pid:
                            selected_index = idx
                            break
                if selected_index is not None:
                    self.state.selected_index = selected_index
                elif self.state.selected_index >= len(self.state.instances):
                    self.state.selected_index = max(len(self.state.instances) - 1, 0)
            else:
                self.state.selected_index = 0
            self.state.status = "Checking permissions..."
            self._signal()
            instances = await asyncio.to_thread(
                add_state_status,
                instances,
                self.scan_backend or self.backend,
                options.permission_lines,
                options.idle_checks,
            )
            if self.state.permission_only:
                instances = [inst for inst in instances if inst.state == "permission"]
            if options.limit is not None:
                instances = instances[: options.limit]
            self.state.instances = sorted(instances, key=_tui_sort_key)
            if self.state.instances:
                selected_index = None
                if selected_session_id is not None:
                    for idx, inst in enumerate(self.state.instances):
                        if inst.session and inst.session.session_id == selected_session_id:
                            selected_index = idx
                            break
                if selected_index is None and selected_pid is not None:
                    for idx, inst in enumerate(self.state.instances):
                        if inst.process.pid == selected_pid:
                            selected_index = idx
                            break
                if selected_index is not None:
                    self.state.selected_index = selected_index
                elif self.state.selected_index >= len(self.state.instances):
                    self.state.selected_index = max(len(self.state.instances) - 1, 0)
            else:
                self.state.selected_index = 0
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
                if not inst.state_output:
                    continue
                lines = split_and_trim(inst.state_output)
                if not lines:
                    continue
                self.output_cache[inst.session.session_id] = OutputCacheEntry(
                    lines=lines,
                    last_output_at=datetime.now().strftime("%H:%M:%S"),
                    updated_at=now,
                )
            self.last_list_refresh_at = now
            self._maybe_notify(instances)
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
            self.state.status = f"Focusing {instance.process.pid}..."
            self._signal()
            self.suspend_output_until = time.monotonic() + 1.0
            await asyncio.to_thread(self.backend.activate, instance.session)
            self.state.status = f"Activated {instance.process.pid}."
        except Exception as exc:
            self.state.status = f"Activation failed: {exc}"

    async def update_output(self) -> None:
        if time.monotonic() < self.suspend_output_until:
            return
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
        elif selection_changed and instance.state_output:
            lines = split_and_trim(instance.state_output)
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

    def _maybe_notify(self, instances: list[InstanceInfo]) -> None:
        if not self.notify_enabled:
            self.state_state = {
                inst.session.session_id: inst.state or "idle"
                for inst in instances
                if inst.session is not None
            }
            return
        now = time.monotonic()
        updated, events = state_transition_events(instances, self.state_state)
        self.state_state = updated
        if not self.notifications_initialized:
            self.notifications_initialized = True
            return
        notifier = self.notifier or default_sender()
        notified = False
        for idx, inst in events:
            if inst.session is None:
                continue
            payload = build_payload(inst, idx, sound=self.notify_sound)
            def _action(session=inst.session) -> None:
                try:
                    self.backend.activate(session)
                except Exception:
                    return

            action_command = build_focus_command(inst.session.session_id)
            notifier.send(payload, _action, action_command=action_command)
            self.last_notified_at[inst.session.session_id] = now
            notified = True
        if notified:
            return
        for idx, inst in enumerate(instances, start=1):
            if inst.session is None:
                continue
            if inst.state not in ("permission", "error"):
                continue
            last = self.last_notified_at.get(inst.session.session_id, 0.0)
            if now - last < self.notify_cooldown:
                continue
            payload = build_payload(inst, idx, sound=self.notify_sound)
            def _action(session=inst.session) -> None:
                try:
                    self.backend.activate(session)
                except Exception:
                    return
            action_command = build_focus_command(inst.session.session_id)
            notifier.send(payload, _action, action_command=action_command)
            self.last_notified_at[inst.session.session_id] = now


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Monitor Codex/Claude iTerm2 sessions")
    parser.add_argument(
        "--pattern",
        action="append",
        dest="patterns",
        help="Regex pattern to match process name/cmdline (repeatable)",
    )
    parser.add_argument(
        "--notify",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Send macOS notifications for new permission prompts (default: on)",
    )
    parser.add_argument(
        "--notify-sound",
        help='Play a sound on notifications (examples: "Glass", "Ping", "default", "none")',
    )
    parser.add_argument(
        "--idle-checks",
        default="0.3,0.8",
        help="Comma-separated delays (seconds) to re-check output before marking idle (default: 0.3,0.8)",
    )
    return parser.parse_args(argv)


def _normalize_notify_sound(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    if normalized.lower() in {"none", "off", "false"}:
        return None
    return normalized


def _parse_idle_checks(value: str) -> tuple[float, ...]:
    if not value:
        return ()
    parts = [p.strip() for p in value.split(",") if p.strip()]
    delays: list[float] = []
    for part in parts:
        try:
            delays.append(float(part))
        except ValueError:
            continue
    return tuple(delays)


def main(
    patterns: list[str] | None = None,
    notify: bool | None = None,
    notify_sound: str | None = None,
    idle_checks: str | None = None,
) -> None:
    argv = sys.argv[1:]
    if argv[:1] == ["tui"]:
        argv = argv[1:]
    args = parse_args(argv)
    use_patterns = patterns if patterns is not None else args.patterns
    use_notify = notify if notify is not None else args.notify
    use_notify_sound = (
        _normalize_notify_sound(notify_sound)
        if notify_sound is not None
        else _normalize_notify_sound(args.notify_sound)
    )
    use_idle_checks = (
        _parse_idle_checks(idle_checks)
        if idle_checks is not None
        else _parse_idle_checks(args.idle_checks)
    )
    if not sys.stdin.isatty():
        print("TUI requires an interactive terminal.")
        return
    backend = Iterm2Backend()
    state = TuiState(instances=[], selected_index=0, status="Starting...")
    controller = MonitorController(
        state=state,
        backend=backend,
        scan_backend=Iterm2Backend(),
        patterns=use_patterns,
        notify_enabled=use_notify,
        notify_sound=use_notify_sound,
        notifier=default_sender() if use_notify else None,
        idle_checks=use_idle_checks or (0.3, 0.8),
    )

    async def _run() -> None:
        tui = MonitorTui(
            state,
            controller.open_selected,
            controller.refresh,
            controller.update_output,
            controller.toggle_permission_only,
            controller.toggle_unmapped,
        )
        controller.on_update = tui.app.invalidate
        await tui.run()

    asyncio.run(_run())




if __name__ == "__main__":
    main()
