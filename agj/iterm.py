from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Protocol

from agj.models import SessionInfo


class ItermBackend(Protocol):
    def list_sessions(self, include_path: bool = False) -> list[SessionInfo]:
        raise NotImplementedError

    def activate(self, session: SessionInfo) -> None:
        raise NotImplementedError

    def capture_output(self, session_id: str, lines: int | None = None) -> str:
        raise NotImplementedError


@dataclass
class Iterm2Backend:
    def list_sessions(self, include_path: bool = False) -> list[SessionInfo]:
        try:
            import iterm2
        except Exception as exc:  # pragma: no cover - import guard
            raise RuntimeError("iterm2 Python package is not available") from exc
        async def _work(conn):
            app = await iterm2.async_get_app(conn)
            sessions: list[SessionInfo] = []
            for window in app.windows:
                for tab in window.tabs:
                    for session in tab.sessions:
                        pid = await session.async_get_variable("pid")
                        title = session.name
                        path = None
                        if include_path:
                            path = await session.async_get_variable("path")
                        sessions.append(
                            SessionInfo(
                                session_id=session.session_id,
                                tab_id=tab.tab_id,
                                window_id=window.window_id,
                                pid=pid,
                                title=title,
                                path=path,
                            )
                        )
            return sessions

        return iterm2.Connection().run_until_complete(_work, retry=False)

    def activate(self, session: SessionInfo) -> None:
        try:
            import iterm2
        except Exception as exc:  # pragma: no cover - import guard
            raise RuntimeError("iterm2 Python package is not available") from exc
        async def _work(conn):
            app = await iterm2.async_get_app(conn)
            await app.async_activate()
            target_session = app.get_session_by_id(session.session_id)
            if target_session is None:
                return
            await target_session.tab.async_activate(order_window_front=True)
            await target_session.tab.window.async_activate()
            await target_session.async_activate()
            await asyncio.sleep(0)

        iterm2.Connection().run_until_complete(_work, retry=False)

    def capture_output(self, session_id: str, lines: int | None = None) -> str:
        try:
            import iterm2
        except Exception as exc:  # pragma: no cover - import guard
            raise RuntimeError("iterm2 Python package is not available") from exc

        async def _work(conn):
            app = await iterm2.async_get_app(conn)
            session = app.get_session_by_id(session_id)
            if session is None:
                return ""
            line_info = await session.async_get_line_info()
            if lines is None:
                start = line_info.first_visible_line_number
                count = line_info.mutable_area_height
            else:
                total = (
                    line_info.overflow
                    + line_info.scrollback_buffer_height
                    + line_info.mutable_area_height
                )
                count = min(lines, max(total - line_info.overflow, 0))
                start = max(line_info.overflow, total - count)

            contents = await session.async_get_contents(start, count)
            output = ""
            for line in contents:
                output += line.string
                if line.hard_eol:
                    output += "\n"
            return output

        return iterm2.Connection().run_until_complete(_work, retry=False)
