import re

from agj.models import ProcessInfo
from agj.processes import ProcessQuery, process_matches, summarize_process


def test_process_matches_by_name_and_cmdline():
    regexes = ProcessQuery(patterns=["codex", "claude"]).regexes()
    assert process_matches(regexes, "codex", ["run"], None, []) is True
    assert process_matches(regexes, "python", ["-m", "claude"], None, []) is True
    assert process_matches(regexes, "python", ["-m", "other"], None, []) is False


def test_summarize_process_truncates_cmdline():
    proc = ProcessInfo(pid=123, name="codex", cmdline=["cmd"] * 50, ancestry=[123])
    summary = summarize_process(proc, max_cmd=20)
    assert "codex" in summary
    assert summary.endswith("...")


def test_process_matches_exact_path():
    regexes = ProcessQuery(patterns=["codex"]).regexes()
    assert (
        process_matches(
            regexes,
            "codex",
            ["/opt/homebrew/bin/codex"],
            "/opt/homebrew/bin/codex",
            ["/opt/homebrew/bin/codex"],
        )
        is True
    )
    assert (
        process_matches(
            regexes,
            "codex",
            ["/opt/homebrew/bin/codex"],
            "/opt/homebrew/bin/codex",
            ["/other/bin/codex"],
        )
        is False
    )


def test_process_matches_exact_path_via_which(monkeypatch):
    regexes = ProcessQuery(patterns=["claude"]).regexes()

    def fake_which(cmd):
        if cmd == "claude":
            return "/Users/test/.nvm/bin/claude"
        return None

    monkeypatch.setattr("agj.processes.shutil.which", fake_which)
    assert (
        process_matches(
            regexes,
            "node",
            ["claude"],
            "/usr/bin/node",
            ["/Users/test/.nvm/bin/claude"],
        )
        is True
    )
