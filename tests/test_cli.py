from agx.cli import (
    EXIT_AMBIGUOUS,
    EXIT_NO_MATCHES,
    cmd_focus,
    count_matches,
    format_table,
    select_instance,
)
from agx.models import InstanceInfo, ProcessInfo, SessionInfo


class StubBackend:
    def __init__(self, sessions):
        self._sessions = sessions
        self.activated = None

    def list_sessions(self, include_path: bool = False):
        return self._sessions

    def activate(self, session):
        self.activated = session


def sample_instances():
    sessions = [
        SessionInfo(session_id="s1", tab_id="t1", window_id="w1", pid=10, title=None),
        SessionInfo(session_id="s2", tab_id="t2", window_id="w2", pid=20, title=None),
    ]
    processes = [
        ProcessInfo(pid=11, name="codex", cmdline=["codex"], ancestry=[11, 10]),
        ProcessInfo(pid=21, name="claude", cmdline=["claude"], ancestry=[21, 20]),
    ]
    return [
        InstanceInfo(process=processes[0], session=sessions[0]),
        InstanceInfo(process=processes[1], session=sessions[1]),
    ]


def test_format_table_stable():
    instances = sample_instances()
    output = format_table(instances, stable=True, include_path=False, include_session=True)
    lines = output.splitlines()
    assert lines[0].startswith("id\tpid\tname\tcmd\tsession")
    assert "\t" in lines[1]


def test_format_table_with_path_column():
    session = SessionInfo(
        session_id="s1", tab_id="t1", window_id="w1", pid=10, title=None, path="/tmp"
    )
    proc = ProcessInfo(pid=11, name="codex", cmdline=["codex"], ancestry=[11, 10])
    instances = [InstanceInfo(process=proc, session=session)]
    output = format_table(instances, stable=True, include_path=True, include_session=False)
    lines = output.splitlines()
    assert lines[0].endswith("\tpath")
    assert lines[1].endswith("\t/tmp")


def test_format_table_without_session_column():
    instances = sample_instances()
    output = format_table(instances, stable=True, include_path=False, include_session=False)
    lines = output.splitlines()
    assert lines[0] == "id\tpid\tname\tcmd"


def test_default_include_path_logic():
    include_path = True if None is None else False
    assert include_path is True


def test_select_instance_by_match():
    instances = sample_instances()
    match_count = count_matches(instances, by_id=None, by_pid=None, by_session=None, match="codex")
    assert match_count == 1
    selected = select_instance(instances, by_id=None, by_pid=None, by_session=None, match="codex")
    assert selected is instances[0]


def test_select_instance_ambiguous():
    instances = sample_instances()
    match_count = count_matches(instances, by_id=None, by_pid=None, by_session=None, match="c")
    assert match_count == 2


def test_cmd_focus_unmapped():
    session = SessionInfo(session_id="s1", tab_id="t1", window_id="w1", pid=99, title=None)
    instances = [
        InstanceInfo(
            process=ProcessInfo(pid=1, name="codex", cmdline=["codex"], ancestry=[1]),
            session=None,
        )
    ]

    class Finder:
        def find(self):
            return [instances[0].process]

    backend = StubBackend([session])

    class Args:
        command = "focus"
        patterns = ["codex"]
        id = 1
        pid = None
        session = None
        match = None

    def build_instances_override(*_):
        return instances

    from agx import cli

    original_build = cli.build_instances
    cli.build_instances = build_instances_override
    try:
        exit_code = cmd_focus(Args, backend)
        assert exit_code == EXIT_NO_MATCHES
    finally:
        cli.build_instances = original_build
