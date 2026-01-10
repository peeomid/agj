from agj.models import ProcessInfo, SessionInfo
from agj.service import ListOptions, list_instances


class StubFinder:
    def __init__(self, processes):
        self._processes = processes

    def find(self):
        return self._processes


class StubBackend:
    def __init__(self, sessions, outputs=None):
        self._sessions = sessions
        self._outputs = outputs or {}

    def list_sessions(self, include_path=False):
        return self._sessions

    def capture_output(self, session_id: str, lines=None):
        return self._outputs.get(session_id, "")


def test_list_instances_permission_only(monkeypatch):
    processes = [
        ProcessInfo(pid=1, name="codex", cmdline=["codex"], ancestry=[1, 10]),
        ProcessInfo(pid=2, name="claude", cmdline=["claude"], ancestry=[2, 20]),
    ]
    sessions = [
        SessionInfo(session_id="s1", tab_id="t1", window_id="w1", pid=10, title="a"),
        SessionInfo(session_id="s2", tab_id="t2", window_id="w2", pid=20, title="b"),
    ]
    backend = StubBackend(
        sessions,
        outputs={
            "s1": "Would you like to run the following command?",
            "s2": "no prompt",
        },
    )

    import agj.service as service

    monkeypatch.setattr(service, "build_finder", lambda patterns: StubFinder(processes))

    options = ListOptions(permission_only=True)
    instances = list_instances(backend, options)

    assert len(instances) == 1
    assert instances[0].process.pid == 1
    assert instances[0].permission_prompt is True
