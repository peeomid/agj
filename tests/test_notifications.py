from agj.models import InstanceInfo, ProcessInfo, SessionInfo
from agj.notifications import (
    build_payload,
    permission_transition_events,
    prompt_snippet,
    prompt_summary,
)


def _instance(
    *,
    session_id: str = "s1",
    title: str | None = "Session",
    path: str | None = "/Users/me/project",
    cmdline: list[str] | None = None,
    permission_prompt: bool | None = None,
    permission_output: str | None = None,
) -> InstanceInfo:
    proc = ProcessInfo(
        pid=123,
        name="codex",
        cmdline=cmdline or ["codex", "--help"],
        ancestry=[1],
    )
    session = SessionInfo(
        session_id=session_id,
        tab_id="t1",
        window_id="w1",
        pid=123,
        title=title,
        path=path,
    )
    return InstanceInfo(
        process=proc,
        session=session,
        permission_prompt=permission_prompt,
        permission_output=permission_output,
    )


def test_prompt_snippet_trims_and_limits_lines():
    text = "\n\nfirst line\n\nsecond line\n\nthird line\nfourth line\n"
    snippet = prompt_snippet(text, max_lines=3)
    assert snippet == "second line\nthird line\nfourth line"


def test_prompt_snippet_trims_max_chars():
    text = "a" * 300
    snippet = prompt_snippet(text, max_lines=1, max_chars=50)
    assert len(snippet) == 50
    assert snippet.endswith("…")


def test_prompt_summary_prefers_question_and_reason():
    text = """

Would you like to run the following command?

Reason: Requesting escalation

$ echo test
"""
    summary = prompt_summary(text, max_chars=200)
    assert "Would you like to run the following command?" in summary
    assert "Reason: Requesting escalation" in summary


def test_prompt_summary_falls_back():
    text = """

Line 1

Line 2
"""
    summary = prompt_summary(text, max_chars=200)
    assert summary == "Line 2"


def test_build_payload_fields():
    inst = _instance(permission_output="line1\nline2\nline3\n")
    payload = build_payload(inst, 2)
    assert payload.title == "ADJ: Codex needs approval"
    assert payload.subtitle.startswith("#2 project - Session")
    assert payload.body == "line3"


def test_permission_transition_events():
    inst1 = _instance(session_id="s1", permission_prompt=True)
    inst2 = _instance(session_id="s2", permission_prompt=False)
    previous = {"s1": False, "s2": False}
    updated, events = permission_transition_events([inst1, inst2], previous)
    assert updated["s1"] is True
    assert updated["s2"] is False
    assert events == [(1, inst1)]
