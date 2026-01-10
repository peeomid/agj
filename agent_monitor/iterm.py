from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Protocol

from agent_monitor.models import SessionInfo


class ItermBackend(Protocol):
    def list_sessions(self) -> list[SessionInfo]:
        raise NotImplementedError

    def activate(self, session: SessionInfo) -> None:
        raise NotImplementedError


@dataclass
class Iterm2Backend:
    def list_sessions(self) -> list[SessionInfo]:
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
                        sessions.append(
                            SessionInfo(
                                session_id=session.session_id,
                                tab_id=tab.tab_id,
                                window_id=window.window_id,
                                pid=pid,
                                title=title,
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
