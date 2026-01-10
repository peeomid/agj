from agj.permissions import classify_agent, detect_permission_prompt, detect_permission_prompt_with_reason
from agj.models import ProcessInfo


def test_classify_agent():
    proc = ProcessInfo(pid=1, name="node", cmdline=["claude"], ancestry=[1])
    assert classify_agent(proc) == "claude"
    proc = ProcessInfo(pid=2, name="codex", cmdline=["codex"], ancestry=[2])
    assert classify_agent(proc) == "codex"


def test_detect_permission_prompt_codex():
    output = "Would you like to run the following command?"
    assert detect_permission_prompt(output, "codex") is True
    found, reason = detect_permission_prompt_with_reason(output, "codex")
    assert found is True
    assert reason and "codex matched" in reason


def test_detect_permission_prompt_claude():
    output = "No, and tell Claude what to do differently (esc)"
    assert detect_permission_prompt(output, "claude") is True
    found, reason = detect_permission_prompt_with_reason(output, "claude")
    assert found is True
    assert reason and "claude matched" in reason
