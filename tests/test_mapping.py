from agent_monitor.mapping import map_instances
from agent_monitor.models import InstanceInfo, ProcessInfo, SessionInfo


def test_map_instances_matches_on_ancestry():
    sessions = [
        SessionInfo(session_id="s1", tab_id="t1", window_id="w1", pid=200, title=None),
        SessionInfo(session_id="s2", tab_id="t2", window_id="w2", pid=300, title=None),
    ]
    processes = [
        ProcessInfo(pid=10, name="codex", cmdline=["codex"], ancestry=[10, 200]),
        ProcessInfo(pid=11, name="claude", cmdline=["claude"], ancestry=[11, 400]),
    ]

    instances = map_instances(processes, sessions)

    assert isinstance(instances[0], InstanceInfo)
    assert instances[0].session == sessions[0]
    assert instances[1].session is None
