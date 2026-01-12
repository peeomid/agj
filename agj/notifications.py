from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import shutil
import subprocess
from threading import Thread
from typing import Callable

from agj.models import InstanceInfo
from agj.output_utils import normalize_output
from agj.permissions import classify_agent


@dataclass(frozen=True)
class NotificationPayload:
    title: str
    subtitle: str
    body: str
    sound: str | None = None


class NotificationSender:
    def send(
        self,
        payload: NotificationPayload,
        on_action: Callable[[], None],
        action_command: str | None = None,
    ) -> None:
        raise NotImplementedError


class NoopNotificationSender(NotificationSender):
    def send(
        self,
        payload: NotificationPayload,
        on_action: Callable[[], None],
        action_command: str | None = None,
    ) -> None:
        return


class AlerterSender(NotificationSender):
    def send(
        self,
        payload: NotificationPayload,
        on_action: Callable[[], None],
        action_command: str | None = None,
    ) -> None:
        alerter = _alerter_path()
        if not alerter:
            return
        args = [
            alerter,
            "-title",
            payload.title,
            "-subtitle",
            payload.subtitle,
            "-message",
            payload.body or "",
            "-closeLabel",
            "Dismiss",
            "-json",
        ]
        if payload.sound:
            args.extend(["-sound", payload.sound])

        def _run() -> None:
            try:
                result = subprocess.run(
                    args,
                    capture_output=True,
                    text=True,
                    check=False,
                )
            except Exception:
                return
            stdout = (result.stdout or "").strip()
            if not stdout:
                return
            if _did_activate_notification(stdout):
                on_action()

        Thread(target=_run, daemon=True).start()


def prompt_snippet(text: str, max_lines: int = 3, max_chars: int = 240) -> str:
    text = normalize_output(text or "")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return ""
    snippet_lines = lines[-max_lines:]
    snippet = "\n".join(snippet_lines)
    if len(snippet) > max_chars:
        return snippet[: max_chars - 1] + "…"
    return snippet


def prompt_summary(text: str, max_chars: int = 180) -> str:
    text = normalize_output(text or "")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return ""
    question = ""
    reason = ""
    for line in lines:
        lower = line.lower()
        if not question and (
            "would you like to run the following command" in lower
            or "do you want to make this edit" in lower
            or "do you want to proceed" in lower
        ):
            question = line
        if not reason and line.lower().startswith("reason:"):
            reason = line
        if question and reason:
            break
    if question and reason:
        summary = f"{question} — {reason}"
    elif question:
        summary = question
    elif reason:
        summary = reason
    else:
        summary = lines[-1]
    if len(summary) > max_chars:
        return summary[: max_chars - 1] + "…"
    return summary


def _agent_name(instance: InstanceInfo) -> str:
    agent = classify_agent(instance.process)
    if not agent:
        return "Agent"
    return agent.capitalize()


def _path_basename(instance: InstanceInfo) -> str:
    if not instance.session or not instance.session.path:
        return ""
    path = Path(instance.session.path)
    if path.name:
        return path.name
    return str(path)


def build_payload(
    instance: InstanceInfo,
    index: int,
    sound: str | None = None,
) -> NotificationPayload:
    agent = _agent_name(instance)
    title = f"ADJ: {agent} needs approval"
    session_name = ""
    if instance.session and instance.session.title:
        session_name = instance.session.title
    path_base = _path_basename(instance)
    subtitle_parts = [f"#{index}"]
    if path_base:
        subtitle_parts.append(path_base)
    if session_name:
        subtitle_parts.append(session_name)
    subtitle = ": ".join(subtitle_parts[:1]) + (" " + " - ".join(subtitle_parts[1:]) if len(subtitle_parts) > 1 else "")
    body = prompt_summary(instance.permission_output or "")
    return NotificationPayload(
        title=title,
        subtitle=subtitle,
        body=body,
        sound=sound,
    )


def default_sender() -> NotificationSender:
    if _alerter_path():
        return AlerterSender()
    return NoopNotificationSender()


def _alerter_path() -> str | None:
    return shutil.which("alerter")


def _did_activate_notification(stdout: str) -> bool:
    try:
        payload = json.loads(stdout)
    except Exception:
        return "activated" in stdout.lower() or "clicked" in stdout.lower()
    activation_type = str(payload.get("activationType", "")).lower()
    if activation_type.isdigit():
        return activation_type in ("1", "2")
    if not activation_type:
        return False
    if "close" in activation_type or "dismiss" in activation_type:
        return False
    if "activated" in activation_type or "clicked" in activation_type:
        return True
    return False


def permission_transition_events(
    instances: list[InstanceInfo],
    previous: dict[str, bool],
) -> tuple[dict[str, bool], list[tuple[int, InstanceInfo]]]:
    updated: dict[str, bool] = {}
    events: list[tuple[int, InstanceInfo]] = []
    for idx, instance in enumerate(instances, start=1):
        if instance.session is None:
            continue
        session_id = instance.session.session_id
        current = instance.permission_prompt is True
        updated[session_id] = current
        if current and not previous.get(session_id, False):
            events.append((idx, instance))
    return updated, events
